"""Level 13, the last level: KNEE-DEEP IN THE DEMON. A Doom clone where the
gun is a hadouken.

A Wolfenstein/Doom style raycaster drawn into the 320x180 canvas: the 3D view
fills the top VIEW_H rows and a Doom status bar (ki, health, Akuma's face,
kills, keys) the rest. Rendering is numpy all the way: one vectorised DDA
pass casts every screen column at once (sliding doors are hit at their
mid-plane), then walls, floor, ceiling and sky are gathered per pixel from
procedurally generated 64x64 textures, shaded by each cell's (flickering)
light, distance fog and the glow of every flying hadouken, and blitted with
pygame.surfarray. The wall distance of every column is kept as a z-buffer so
billboard sprites (demons, fireballs, snacks) hide behind walls.

The demons (imp, pinky, cacodemon, lost soul, zombieman) are drawn in code
from shaded "capsules" (see rig_render). Akuma's first-person hands (idle
claws, the two-handed hadouken charge and release, the claw swipe) come from
Toshi's sheet (assets/doom_hands/, tools/make_doom_hands.py); the kick foot
and the shoryuken fist are still capsules, in the same colours. The red/purple
hadouken, its impacts and explosions come from the fx sheet (akuma/fx.py).
Fireballs pick a back / side / front view from their direction of flight
relative to the camera.

The map is a hand-laid hell fortress of green-grey stone under a red sky: a
tech-base start room, a demon hall, a blue key room, a red key cavern (with a
secret wall), and a sky-lit arena
where CYBER-GIEF waits in front of the sealed exit portal.
"""

import json
import math
import os
import random

import numpy as np
import pygame

from . import audio, fx
from .akuma_sprites import CharArt, asset_dir, portrait
from .config import W, H
from .font import draw_text, text_surface
from .pause import PauseMenu
from .snacks import heal_amount, random_snack, snack_image

LEVEL_NAME = "KNEE-DEEP IN THE DEMON"
VIEW_H = 148                  # rows of 3D view; the status bar takes the rest
BAR_H = H - VIEW_H
PLANE = 0.66                  # camera plane half-width (about 67 degree FOV)
PROJ = (W / 2) / PLANE        # px per world unit at distance 1
TS = 64                       # texture size

INTRO = 120
MOVE_SPEED = 0.055
STRAFE_SPEED = 0.05
TURN_SPEED = 0.05
PLAYER_R = 0.22
HADO_COST, SHINKU_COST = 2, 16
HADO_DMG, HADO_SPLASH = 25, 10
SHINKU_DMG, SHINKU_SPLASH = 90, 45
KICK_DMG = 30
PUNCH_DMG = 18
SHORYU_DMG = 50
TATSU_DMG = 28
KI_START, KI_MAX = 60, 200
KI_ORB, BIG_KI_ORB = 12, 50
HADO_SPEED = 0.17
ENEMY_SHOT_SPEED = 0.075
COMBO_WINDOW = 4              # special + punch / kick within this many frames = shoryuken / tatsumaki
EXTRA_SNACKS = 8              # snacks scattered at random on top of the hand-placed ones
CONTROLS = [
    "UP / DOWN: WALK FORWARD / BACK",
    "LEFT / RIGHT: TURN",
    "HOLD I (SHIELD) + LEFT / RIGHT: STRAFE",
    "L: HADOUKEN (2 KI), HOLD TO KEEP FIRING",
    "I + L: SHINKU HADOUKEN (16 KI), PIERCES",
    "L + J: SHORYUKEN    L + K: TATSUMAKI",
    "J: PUNCH    K: KICK (BOTH OPEN DOORS)",
    "BLUE AND RED DOORS NEED THEIR KEY",
    "SNACKS HEAL. BLUE KI ORBS REFILL KI",
    "KILL CYBER-GIEF, THEN TAKE THE PORTAL",
]

# ---- textures ------------------------------------------------------------
(T_HELL, T_FACE, T_TECH, T_COMP, T_FLESH, T_DOOR, T_DOOR_B, T_DOOR_R, T_BOSSDOOR, T_JAMB,
 T_SECRET, F_STONE, F_METAL, F_LAVA, C_STONE, C_LIGHT, F_EXIT, C_FLESH, T_BAND) = range(1, 20)
N_TEX = 20                    # T_HELL is the green-grey fortress stone, T_BAND the same with an iron band
SKY = 99                      # ceiling id: open sky
DOOR = 100                    # grid marker for a door cell
MAP_W, MAP_H = 40, 32


def _smooth(rng, cells, ts=TS):
    """Tileable value noise in 0..1, shape (ts, ts)."""
    g = rng.random((cells, cells))
    idx = np.arange(ts) * cells / ts
    i0 = idx.astype(int)
    f = idx - i0
    f = f * f * (3 - 2 * f)
    i1 = (i0 + 1) % cells
    a = g[i0] * (1 - f)[:, None] + g[i1] * f[:, None]
    return a[:, i0] * (1 - f)[None, :] + a[:, i1] * f[None, :]


def _fbm(rng, ts=TS, octaves=(4, 8, 16, 32)):
    n = sum(_smooth(rng, c, ts) / (k + 1) for k, c in enumerate(octaves))
    n -= n.min()
    return n / max(1e-6, n.max())


_BAYER_T = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) + 0.5) / 16 - 0.5


def _col(base, mult):
    return np.clip(np.array(base, np.float32)[None, None, :] * mult[..., None], 0, 255)


def _tex_from_surface(s):
    return pygame.surfarray.array3d(s).astype(np.float32)


def _surface(img):
    return pygame.surfarray.make_surface(np.clip(img, 0, 255).astype(np.uint8))


def _tex_tech(rng, computer=False):
    X, Y = np.meshgrid(np.arange(TS), np.arange(TS), indexing="ij")
    n = _fbm(rng)
    img = _col((104, 108, 118), 0.75 + 0.35 * n)
    s = _surface(img)
    for py in (0, 32):
        pygame.draw.rect(s, (60, 62, 70), (0, py, 64, 32), 1)
        pygame.draw.line(s, (150, 155, 168), (1, py + 1), (62, py + 1))
        pygame.draw.line(s, (150, 155, 168), (1, py + 1), (1, py + 30))
        for rx, ry in ((4, py + 4), (59, py + 4), (4, py + 27), (59, py + 27)):
            pygame.draw.rect(s, (170, 175, 185), (rx, ry, 2, 2))
            pygame.draw.rect(s, (50, 50, 56), (rx + 1, ry + 1, 1, 1))
    if computer:
        pygame.draw.rect(s, (20, 24, 22), (10, 8, 44, 20))
        pygame.draw.rect(s, (80, 84, 92), (10, 8, 44, 20), 1)
        for k in range(5):
            w = rng.randint(10, 34)
            pygame.draw.line(s, (60, 220, 90), (13, 11 + k * 3), (13 + w, 11 + k * 3))
        for k in range(6):
            c = rng.choice([(255, 40, 30), (40, 255, 60), (255, 210, 40), (60, 140, 255)])
            pygame.draw.rect(s, c, (12 + k * 7, 40, 4, 3))
        for k in range(4):
            pygame.draw.line(s, (40, 40, 46), (12, 48 + k * 3), (52, 48 + k * 3))
    else:
        for k in range(4):
            pygame.draw.line(s, (40, 40, 46), (20, 12 + k * 3), (44, 12 + k * 3))
        # hazard stripe along the bottom
        for k in range(-8, 72, 8):
            pygame.draw.polygon(s, (220, 180, 30), [(k, 63), (k + 4, 63), (k + 8, 57), (k + 4, 57)])
        pygame.draw.line(s, (30, 30, 30), (0, 56), (63, 56))
    return _tex_from_surface(s)


def _tex_flesh(rng):
    n = _fbm(rng)
    v1 = np.abs(_smooth(rng, 8) - 0.5) < 0.04
    v2 = np.abs(_smooth(rng, 4) - 0.5) < 0.03
    img = _col((150, 34, 38), 0.55 + 0.6 * n)
    img[v1] = _col((70, 8, 20), 0.8 + 0.3 * n)[v1]
    img[v2] = _col((200, 70, 80), 0.8 + 0.3 * n)[v2]
    hi = n > 0.82
    img[hi] = np.minimum(255, img[hi] * 1.3)
    return img


def _tex_door(rng, stripe=None, boss=False):
    n = _fbm(rng)
    img = _col((118, 104, 92), 0.7 + 0.4 * n)
    s = _surface(img)
    if boss:
        s.fill((60, 10, 4))
        g = _surface(_col((255, 90, 20), 0.3 + 0.7 * _fbm(rng)))
        s.blit(g, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        for x in range(2, 64, 10):
            pygame.draw.rect(s, (40, 40, 44), (x, 0, 5, 64))
            pygame.draw.line(s, (110, 110, 120), (x + 1, 0), (x + 1, 63))
        pygame.draw.rect(s, (40, 40, 44), (0, 6, 64, 4))
        pygame.draw.rect(s, (40, 40, 44), (0, 54, 64, 4))
        pygame.draw.circle(s, (190, 170, 130), (32, 32), 9)
        pygame.draw.rect(s, (10, 0, 0), (27, 29, 4, 4))
        pygame.draw.rect(s, (10, 0, 0), (33, 29, 4, 4))
        return _tex_from_surface(s)
    pygame.draw.rect(s, (50, 44, 40), (0, 0, 64, 64), 2)
    for y in (12, 50):
        pygame.draw.line(s, (60, 52, 46), (2, y), (61, y))
        pygame.draw.line(s, (160, 146, 130), (2, y + 1), (61, y + 1))
    # a red sigil in the middle
    pygame.draw.circle(s, (120, 10, 8), (32, 31), 13, 2)
    pts = [(32 + 12 * math.cos(-math.pi / 2 + k * 4 * math.pi / 5),
            31 + 12 * math.sin(-math.pi / 2 + k * 4 * math.pi / 5)) for k in range(5)]
    pygame.draw.lines(s, (150, 16, 10), True, pts, 1)
    if stripe:
        dark = tuple(c // 3 for c in stripe)
        pygame.draw.rect(s, stripe, (0, 2, 64, 7))
        pygame.draw.rect(s, stripe, (0, 55, 64, 7))
        pygame.draw.rect(s, dark, (0, 2, 64, 7), 1)
        pygame.draw.rect(s, dark, (0, 55, 64, 7), 1)
        pygame.draw.circle(s, stripe, (32, 31), 6)
        pygame.draw.circle(s, (255, 255, 255), (30, 29), 2)
    return _tex_from_surface(s)


def _tex_jamb(rng):
    n = _fbm(rng)
    img = _col((70, 70, 78), 0.7 + 0.4 * n)
    s = _surface(img)
    for y in range(-8, 72, 10):
        pygame.draw.polygon(s, (220, 180, 30), [(20, y), (44, y + 8), (44, y + 13), (20, y + 5)])
    pygame.draw.rect(s, (30, 30, 34), (18, 0, 28, 64), 1)
    return _tex_from_surface(s)


def _blocks(rng, base, bw, bh, stagger=True, bevel=2, mortar=(22, 24, 20), vary=0.16, moss=True):
    """Big bevelled stone blocks (bw x bh texels) in rows: the green-grey
    fortress masonry. Returns (img, block id array)."""
    X, Y = np.meshgrid(np.arange(TS), np.arange(TS), indexing="ij")
    n = _fbm(rng)
    fine = rng.random((TS, TS))
    row = Y // bh
    off = np.where((row % 2 == 1) & stagger, bw // 2, 0)
    bx = (X + off) % bw
    by = Y % bh
    bid = ((X + off) // bw) % (TS // bw) + row * (TS // bw + 1)
    tint = np.array([rng.uniform(1 - vary, 1 + vary) for _ in range(64)])[bid % 64]
    hue = np.array([rng.uniform(-0.06, 0.06) for _ in range(64)])[bid % 64]
    mult = (0.62 + 0.42 * n + 0.1 * fine) * tint
    img = _col(base, mult)
    img[..., 1] *= 1 + (hue if moss else hue * 0.3)
    # bevels: light top/left, dark bottom/right, then the mortar
    top = (by < bevel) | (bx < bevel)
    bot = (by >= bh - bevel - 1) | (bx >= bw - bevel - 1)
    img[top] = np.minimum(255, img[top] * 1.28)
    img[bot] *= 0.62
    mort = (by == bh - 1) | (bx == bw - 1)
    img[mort] = np.array(mortar, np.float32) * (0.8 + 0.4 * n[mort, None])
    # chips and cracks
    cr = (np.abs(_smooth(rng, 7) - 0.5) < 0.012) & (_smooth(rng, 5) > 0.5)
    img[cr] *= 0.45
    if moss:
        mm = _smooth(rng, 6) > 0.72
        img[mm] = img[mm] * np.array((0.8, 0.95, 0.7))
    return img, bid


def _tex_stone(rng, support=False):
    img, _ = _blocks(rng, (104, 114, 94), 32, 16)
    if support:
        # a riveted iron band down the middle, like the fortress corners
        s = _surface(img)
        pygame.draw.rect(s, (46, 48, 46), (24, 0, 16, 64))
        pygame.draw.line(s, (92, 96, 92), (25, 0), (25, 63))
        pygame.draw.line(s, (24, 24, 24), (39, 0), (39, 63))
        for y in range(4, 64, 10):
            pygame.draw.rect(s, (120, 124, 118), (28, y, 2, 2))
            pygame.draw.rect(s, (120, 124, 118), (34, y, 2, 2))
            pygame.draw.rect(s, (20, 20, 20), (29, y + 1, 1, 1))
            pygame.draw.rect(s, (20, 20, 20), (35, y + 1, 1, 1))
        return _tex_from_surface(s)
    return img


def _tex_face(rng):
    """A skull plaque set in the stone (the framed skull of the reference)."""
    s = _surface(_tex_stone(rng))
    pygame.draw.rect(s, (30, 22, 16), (12, 8, 40, 48))
    pygame.draw.rect(s, (92, 70, 46), (13, 9, 38, 46))
    pygame.draw.rect(s, (64, 46, 30), (13, 9, 38, 46), 3)
    pygame.draw.line(s, (130, 104, 70), (13, 9), (50, 9))
    pygame.draw.line(s, (130, 104, 70), (13, 9), (13, 54))
    pygame.draw.rect(s, (40, 30, 22), (17, 13, 30, 38))
    bone, dark, lite = (186, 170, 140), (100, 86, 70), (230, 220, 196)
    pygame.draw.ellipse(s, bone, (21, 16, 22, 22))
    pygame.draw.rect(s, bone, (25, 33, 14, 9))
    pygame.draw.ellipse(s, lite, (24, 18, 10, 8))
    pygame.draw.ellipse(s, (16, 8, 6), (24, 25, 7, 7))
    pygame.draw.ellipse(s, (16, 8, 6), (33, 25, 7, 7))
    pygame.draw.rect(s, (220, 40, 20), (27, 28, 2, 2))
    pygame.draw.rect(s, (220, 40, 20), (36, 28, 2, 2))
    pygame.draw.polygon(s, (30, 16, 10), [(32, 31), (30, 35), (34, 35)])
    for k in range(4):
        pygame.draw.rect(s, lite, (26 + k * 3, 38, 2, 4))
    pygame.draw.ellipse(s, dark, (21, 16, 22, 22), 1)
    return _tex_from_surface(s)


def _tex_floor(rng, kind):
    X, Y = np.meshgrid(np.arange(TS), np.arange(TS), indexing="ij")
    n = _fbm(rng)
    if kind == "stone":
        # big brown flagstones, a little uneven
        img, bid = _blocks(rng, (130, 98, 66), 32, 32, stagger=False, bevel=2, mortar=(34, 26, 20), vary=0.2,
                           moss=False)
        stain = _smooth(rng, 5) > 0.68
        img[stain] *= 0.82
    elif kind == "metal":
        img = _col((92, 96, 104), 0.7 + 0.4 * n)
        grid = ((X % 8) < 1) | ((Y % 8) < 1)
        img[grid] = _col((40, 42, 48), 1 + 0 * n)[grid]
        hl = ((X % 8) == 1) | ((Y % 8) == 1)
        img[hl] = np.minimum(255, img[hl] * 1.25)
    elif kind == "lava":
        img = _col((52, 40, 38), 0.6 + 0.6 * n)
        cr = np.abs(_smooth(rng, 5) - 0.5) < 0.03
        cr |= np.abs(_smooth(rng, 9) - 0.5) < 0.02
        img[cr] = _col((255, 110, 20), 0.8 + 0.2 * n)[cr]
    elif kind == "ceil":
        img, _ = _blocks(rng, (70, 70, 62), 32, 32, stagger=False, mortar=(20, 20, 18))
    elif kind == "light":
        img = _col((80, 82, 90), 0.7 + 0.3 * n)
        lamp = (X >= 16) & (X < 48) & (Y >= 16) & (Y < 48)
        img[lamp] = np.array((255, 250, 220))
        edge = lamp & ((X == 16) | (X == 47) | (Y == 16) | (Y == 47))
        img[edge] = np.array((150, 150, 140))
    elif kind == "exit":
        r = np.hypot(X - 31.5, Y - 31.5)
        img = _col((90, 30, 160), 0.5 + 0.5 * np.cos(r * 0.6) ** 2)
    else:   # flesh ceiling
        img = _tex_flesh(rng) * 0.7
    return img


def _sky(rng, w=512, h=84):
    """Blood-red sky over jagged red mountains (lit from the left)."""
    X, Y = np.meshgrid(np.arange(w), np.arange(h), indexing="ij")
    t = Y / (h - 1)
    img = np.zeros((w, h, 3), np.float32)
    img[..., 0] = 120 + 110 * t
    img[..., 1] = 8 + 30 * t ** 2
    img[..., 2] = 10 + 12 * t
    cl = _smooth(rng, 16, w)[:, :h] * 0.6 + _smooth(rng, 32, w)[:, :h] * 0.4
    streak = np.clip((cl - 0.45) * 3, 0, 1)
    img *= (0.72 + 0.4 * streak)[..., None]
    img[..., 0] = np.where(streak > 0.6, img[..., 0] * 1.12, img[..., 0])

    def ridge(seed_f, amp, base):
        r = np.zeros(w)
        xs = np.arange(w)
        for f, a in seed_f:
            ph = rng.uniform(0, 6.28)
            saw = np.abs(((xs * f / w + ph) % 1.0) - 0.5) * 2         # triangle peaks
            r += a * (1 - saw)
        return base - r * amp

    for layer, (spec, amp, base, col_lit, col_dark) in enumerate((
            (((3, 1.0), (7, 0.5), (17, 0.25)), 14, h - 16, (170, 40, 34), (96, 16, 16)),
            (((5, 1.0), (11, 0.45), (29, 0.2)), 16, h - 2, (120, 22, 20), (52, 6, 8)))):
        top = ridge(spec, amp, base)
        slope = np.gradient(top)
        lit = slope < 0                                  # faces the light (left)
        m = Y > top[:, None]
        depth = np.clip((Y - top[:, None]) / 22.0, 0, 1)
        col = np.where(lit[:, None, None], np.array(col_lit, np.float32), np.array(col_dark, np.float32))
        col = col * (1 - 0.45 * depth[..., None])
        snow = m & (Y < top[:, None] + 2)
        img[m] = col[m]
        img[snow] = np.minimum(255, col[snow] * 1.35)
    dith = np.tile(_BAYER_T, (w // 4 + 1, h // 4 + 1))[:w, :h]
    img = np.floor(img / 12 + dith[..., None]) * 12
    return np.clip(img, 0, 255)


def build_textures(seed=13):
    rng = np.random.default_rng(seed)
    prng = random.Random(seed)
    T = np.zeros((N_TEX, TS, TS, 3), np.float32)
    T[T_HELL] = _tex_stone(rng)
    T[T_BAND] = _tex_stone(rng, support=True)
    T[T_FACE] = _tex_face(rng)
    T[T_TECH] = _tex_tech(_PR(prng, rng))
    T[T_COMP] = _tex_tech(_PR(prng, rng), computer=True)
    T[T_FLESH] = _tex_flesh(rng)
    T[T_DOOR] = _tex_door(_PR(prng, rng))
    T[T_DOOR_B] = _tex_door(_PR(prng, rng), (40, 90, 255))
    T[T_DOOR_R] = _tex_door(_PR(prng, rng), (230, 30, 30))
    T[T_BOSSDOOR] = _tex_door(_PR(prng, rng), boss=True)
    T[T_JAMB] = _tex_jamb(rng)
    T[T_SECRET] = T[T_HELL] * 0.96
    T[F_STONE] = _tex_floor(rng, "stone")
    T[F_METAL] = _tex_floor(rng, "metal")
    T[F_LAVA] = _tex_floor(rng, "lava")
    T[C_STONE] = _tex_floor(rng, "ceil")
    T[C_LIGHT] = _tex_floor(rng, "light")
    T[F_EXIT] = _tex_floor(rng, "exit")
    T[C_FLESH] = _tex_floor(rng, "fleshceil")
    return T, _sky(rng)


class _PR:
    """numpy Generator plus the random.Random calls the texture painters use."""

    def __init__(self, prng, rng):
        self.prng, self.rng = prng, rng

    def random(self, shape):
        return self.rng.random(shape)

    def randint(self, a, b):
        return self.prng.randint(a, b)

    def choice(self, seq):
        return self.prng.choice(seq)


# ---- the map ---------------------------------------------------------------
class Door:
    def __init__(self, x, y, orient, tex, key=None):
        self.x, self.y = x, y
        self.orient = orient         # 0: plane at x+0.5 (walk through east-west); 1: at y+0.5
        self.tex = tex
        self.key = key               # None | "blue" | "red" | "boss"
        self.open = 0.0
        self.opening = False


class LevelMap:
    def __init__(self, rng):
        self.grid = np.full((MAP_H, MAP_W), T_HELL, np.int16)     # [y, x]
        self.floor = np.full((MAP_H, MAP_W), F_STONE, np.int16)
        self.ceil = np.full((MAP_H, MAP_W), C_STONE, np.int16)
        self.light = np.full((MAP_H, MAP_W), 0.7, np.float32)
        self.flicker = np.zeros((MAP_H, MAP_W), np.int8)
        self.phase = np.random.default_rng(7).random((MAP_H, MAP_W)).astype(np.float32) * 100
        self.door_open = np.zeros((MAP_H, MAP_W), np.float32)
        self.door_orient = np.zeros((MAP_H, MAP_W), np.int8)
        self.door_tex = np.zeros((MAP_H, MAP_W), np.int16)
        self.doors = {}
        self.secrets = set()
        self.rng = rng
        self.things = []             # (kind, x, y)
        self.areas = {}
        self._build()

    def room(self, name, x0, y0, x1, y1, wall, floor, ceil, light, flicker=0, faces=0.0):
        self.areas[name] = (x0, y0, x1, y1)
        for y in range(y0 - 1, y1 + 2):
            for x in range(x0 - 1, x1 + 2):
                if 0 <= x < MAP_W and 0 <= y < MAP_H and self.grid[y, x] not in (0, DOOR):
                    on_ring = not (x0 <= x <= x1 and y0 <= y <= y1)
                    if on_ring:
                        self.grid[y, x] = T_FACE if (faces and self.rng.random() < faces) else wall
        self.grid[y0:y1 + 1, x0:x1 + 1] = 0
        self.floor[y0:y1 + 1, x0:x1 + 1] = floor
        self.ceil[y0:y1 + 1, x0:x1 + 1] = ceil
        self.light[y0:y1 + 1, x0:x1 + 1] = light
        self.flicker[y0:y1 + 1, x0:x1 + 1] = flicker

    def door(self, x, y, tex=T_DOOR, key=None):
        orient = 0 if self.grid[y - 1, x] != 0 and self.grid[y + 1, x] != 0 else 1
        self.grid[y, x] = DOOR
        self.door_orient[y, x] = orient
        self.door_tex[y, x] = tex
        self.doors[(x, y)] = Door(x, y, orient, tex, key)
        nb = [self.light[y + dy, x + dx] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
              if self.grid[y + dy, x + dx] == 0]
        self.light[y, x] = max(nb) if nb else 0.7
        self.floor[y, x] = F_METAL
        self.ceil[y, x] = C_STONE

    def _build(self):
        R = self.room
        # A: the tech-base airlock where Akuma arrives
        R("start", 3, 25, 10, 29, T_TECH, F_METAL, C_LIGHT, 1.0)
        self.grid[29, 3] = self.grid[29, 10] = T_COMP
        for x in (2, 11):
            for y in (26, 28):
                self.grid[y, x] = T_COMP
        # B: the corridor north, its lights failing
        R("corridor", 5, 16, 8, 23, T_HELL, F_STONE, C_STONE, 0.6, flicker=1)
        self.grid[24, 5] = self.grid[24, 7] = self.grid[24, 8] = T_TECH
        # C: the demon hall
        R("hall", 2, 8, 17, 15, T_HELL, F_STONE, SKY, 0.8, faces=0.08)
        for x, y in ((6, 11), (6, 12), (12, 11), (12, 12)):
            self.grid[y, x] = T_FACE
        R("corridor", 5, 16, 8, 23, T_HELL, F_STONE, C_STONE, 0.6, flicker=1)
        # D: the blue key room (tech)
        R("bluekey", 19, 9, 26, 16, T_TECH, F_METAL, C_LIGHT, 0.85)
        for x, y in ((22, 9), (23, 9)):
            self.grid[y - 1, x] = T_COMP
        # E: the red key cavern (flesh and lava), and a secret stash west of it
        R("redkey", 3, 1, 16, 6, T_FLESH, F_LAVA, C_FLESH, 0.55, flicker=2, faces=0.1)
        R("stash", 1, 2, 1, 4, T_HELL, F_STONE, C_STONE, 0.9)
        self.grid[3, 2] = T_SECRET
        self.secrets.add((2, 3))
        # F: the antechamber and the arena under the burning sky
        R("ante", 28, 11, 29, 13, T_TECH, F_METAL, C_STONE, 0.6, flicker=3)
        R("arena", 30, 3, 38, 26, T_HELL, F_STONE, SKY, 0.85, faces=0.08)
        self.floor[12:15, 31:38] = F_LAVA                  # a lava pit round the arena's centre pillar
        for x, y in ((32, 9), (36, 9), (32, 17), (36, 17), (34, 13)):
            self.grid[y, x] = T_FACE
        self.grid[11:14, 29] = 0
        self.floor[11:14, 29] = F_METAL
        # G: the exit pocket behind the boss seal
        R("exit", 33, 28, 35, 30, T_TECH, F_EXIT, C_LIGHT, 1.0)
        self.light[28:31, 33:36] = 1.0
        # doors
        self.door(6, 24)                                   # start -> corridor
        self.door(18, 12)                                  # hall -> blue key room
        self.door(9, 7, T_DOOR_B, "blue")                  # hall -> red key cavern
        self.door(27, 12, T_DOOR_R, "red")                 # blue key room -> arena
        self.door(34, 27, T_BOSSDOOR, "boss")              # arena -> exit
        # iron bands on some of the fortress stone
        for (y, x) in zip(*np.nonzero(self.grid == T_HELL)):
            if (x * 7 + y * 13) % 5 == 0 and (x, y) not in self.secrets:
                self.grid[y, x] = T_BAND
        th = self.things
        th += [("ki", 4, 26), ("snack", 9, 26), ("ki", 9, 29), ("torch", 4, 29), ("torch", 9, 25)]
        th += [("zombie", 7, 18), ("ki", 5, 20)]
        th += [("pinky", 4, 10), ("zombie", 15, 14), ("imp", 13, 9), ("caco", 3, 14),
               ("snack", 16, 9), ("ki", 2, 15), ("torch", 2, 8), ("torch", 17, 8),
               ("torch", 2, 15), ("torch", 17, 15)]
        th += [("imp", 24, 10), ("zombie", 21, 15), ("soul", 25, 13), ("bluekey", 25, 15),
               ("ki", 20, 10), ("snack", 26, 9)]
        th += [("pinky", 12, 3), ("caco", 5, 2), ("imp", 14, 5), ("soul", 8, 4),
               ("redkey", 15, 2), ("snack", 4, 5), ("ki", 10, 6), ("torch", 3, 1), ("torch", 16, 6)]
        th += [("bigki", 1, 2), ("snack", 1, 3), ("snack", 1, 4)]
        th += [("boss", 34, 6), ("imp", 31, 4), ("caco", 37, 4), ("soul", 31, 20),
               ("snack", 31, 25), ("snack", 37, 25), ("bigki", 31, 12), ("bigki", 37, 20),
               ("torch", 30, 3), ("torch", 38, 3), ("torch", 30, 26), ("torch", 38, 26),
               ("portal", 34, 29)]

    def area_of(self, x, y):
        for name, (x0, y0, x1, y1) in self.areas.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return name
        return None

    def solid(self, cx, cy):
        if not (0 <= cx < MAP_W and 0 <= cy < MAP_H):
            return True
        c = self.grid[cy, cx]
        if c == 0:
            return False
        if c == DOOR:
            return self.door_open[cy, cx] < 0.95
        return True

    def los(self, x0, y0, x1, y1):
        d = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(d / 0.2))
        for k in range(1, n):
            t = k / n
            if self.solid(int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)):
                return False
        return True


# ---- the renderer ------------------------------------------------------------
def fog(d):
    return np.clip(1.25 - 0.085 * d, 0.07, 1.0)


class Renderer:
    def __init__(self, lmap):
        self.m = lmap
        self.tex, self.sky = build_textures()
        # every texel of every texture, then the sky, in one flat (N, 3) table
        self.sky_base = N_TEX * TS * TS
        flat = np.concatenate([self.tex.reshape(-1, 3), self.sky.reshape(-1, 3)]).astype(np.uint8)
        flat4 = np.zeros((len(flat), 4), np.uint8)
        flat4[:, :3] = flat
        self.flat32 = flat4.view(np.uint32).ravel()      # packed texels: one gather per frame
        self.fc = np.concatenate([lmap.ceil.ravel(), lmap.floor.ravel()]).astype(np.int32)
        self.camx = (2 * (np.arange(W) + 0.5) / W - 1).astype(np.float64)
        self.rows = np.arange(VIEW_H, dtype=np.float32) + 0.5
        self.view = pygame.Surface((W, VIEW_H)).convert()
        self.zbuf = np.full(W, 1e9)
        self.ms = 0.0

    def cast(self, px, py, ang):
        """Vectorised DDA: every column at once (rays that have hit drop out of
        the working set). Returns perpendicular distance, texture id, texture u
        (0..1), side, the cell in front of the wall, ray dirs and hit points."""
        m = self.m
        dx, dy = math.cos(ang), math.sin(ang)
        plx, ply = -dy * PLANE, dx * PLANE
        rdx = dx + plx * self.camx
        rdy = dy + ply * self.camx
        rdx = np.where(np.abs(rdx) < 1e-9, 1e-9, rdx)
        rdy = np.where(np.abs(rdy) < 1e-9, 1e-9, rdy)
        ddx_all, ddy_all = np.abs(1 / rdx), np.abs(1 / rdy)
        stx_all = np.where(rdx < 0, -1, 1).astype(np.int32)
        sty_all = np.where(rdy < 0, -1, 1).astype(np.int32)
        ipx, ipy = int(px), int(py)
        sdx = np.where(rdx < 0, (px - ipx) * ddx_all, (ipx + 1 - px) * ddx_all)
        sdy = np.where(rdy < 0, (py - ipy) * ddy_all, (ipy + 1 - py) * ddy_all)
        dist = np.full(W, 40.0)
        side_out = np.zeros(W, np.int8)
        tid = np.full(W, T_HELL, np.int32)
        du = np.full(W, -1.0)
        mx_out = np.full(W, ipx, np.int32)
        my_out = np.full(W, ipy, np.int32)
        # the working set
        idx = np.arange(W)
        mx = np.full(W, ipx, np.int32)
        my = np.full(W, ipy, np.int32)
        ddx, ddy, stx, sty = ddx_all, ddy_all, stx_all, sty_all
        rx, ry = rdx, rdy
        grid = m.grid
        for _ in range(MAP_W + MAP_H + 8):
            xs = sdx < sdy
            enter = np.where(xs, sdx, sdy)
            mx = mx + np.where(xs, stx, 0)
            my = my + np.where(xs, 0, sty)
            sdx = np.where(xs, sdx + ddx, sdx)
            sdy = np.where(xs, sdy, sdy + ddy)
            np.clip(mx, 0, MAP_W - 1, out=mx)
            np.clip(my, 0, MAP_H - 1, out=my)
            c = grid[my, mx]
            done = (c > 0) & (c < DOOR)
            if done.any():
                j = idx[done]
                dist[j] = enter[done]
                tid[j] = c[done]
                side_out[j] = np.where(xs[done], 0, 1)
                mx_out[j] = mx[done]
                my_out[j] = my[done]
            dm = c == DOOR
            if dm.any():
                sd = np.where(xs[dm], 0, 1)
                ix, iy = mx[dm], my[dm]
                half = np.where(sd == 0, ddx[dm], ddy[dm]) * 0.5
                mid = enter[dm] + half
                nxt = np.where(sd == 0, sdy[dm], sdx[dm])
                pos = np.where(sd == 0, py + mid * ry[dm], px + mid * rx[dm])
                frac = pos - np.floor(pos)
                op = m.door_open[iy, ix]
                ok = (m.door_orient[iy, ix] == sd) & (mid < nxt) & (frac >= op)
                if ok.any():
                    j = idx[dm][ok]
                    dist[j] = mid[ok]
                    tid[j] = m.door_tex[iy[ok], ix[ok]]
                    du[j] = frac[ok] - op[ok]
                    side_out[j] = sd[ok]
                    mx_out[j] = ix[ok]
                    my_out[j] = iy[ok]
                    hitd = np.zeros_like(dm)
                    hitd[np.flatnonzero(dm)[ok]] = True
                    done = done | hitd
            if done.any():
                keep = ~done
                if not keep.any():
                    break
                idx, mx, my, sdx, sdy = idx[keep], mx[keep], my[keep], sdx[keep], sdy[keep]
                ddx, ddy, stx, sty, rx, ry = ddx[keep], ddy[keep], stx[keep], sty[keep], rx[keep], ry[keep]
        side = side_out
        mx, my = mx_out, my_out
        wx = px + dist * rdx
        wy = py + dist * rdy
        u = np.where(side == 0, wy, wx)
        u = u - np.floor(u)
        flip = ((side == 0) & (rdx > 0)) | ((side == 1) & (rdy < 0))
        u = np.where(flip, 1 - u, u)
        isdoor = du >= 0
        u = np.where(isdoor, du, u)
        # the cell the ray was in before the wall: its light, and door frames
        prx = np.where(isdoor | (side == 1), mx, mx - stx_all)
        pry = np.where(isdoor | (side == 0), my, my - sty_all)
        np.clip(prx, 0, MAP_W - 1, out=prx)
        np.clip(pry, 0, MAP_H - 1, out=pry)
        jamb = (~isdoor) & (grid[pry, prx] == DOOR)
        tid = np.where(jamb, T_JAMB, tid)
        return dist, tid, u, side, prx, pry, rdx, rdy, wx, wy

    def render(self, px, py, ang, camz, light_now, lights, flash=0.0):
        """Draws the walls, floor, ceiling and sky into self.view."""
        m = self.m
        dist, tid, u, side, prx, pry, rdx, rdy, wx, wy = self.cast(px, py, ang)
        dist = np.maximum(dist, 1e-3)
        self.zbuf = dist
        h = VIEW_H / 2
        rows = self.rows
        lineh = (PROJ / dist).astype(np.float32)
        top = h - (1 - camz) * lineh
        v = (rows[None, :] - top[:, None]) / lineh[:, None]          # (W, VH)
        wallm = (v >= 0) & (v < 1)
        tv = np.clip((v * TS).astype(np.int32), 0, TS - 1)
        tu = np.clip((u * TS).astype(np.int32), 0, TS - 1)
        # floor and ceiling
        dyr = rows - h
        isfloor = dyr > 0
        rd = np.where(isfloor, camz * PROJ / np.maximum(dyr, 0.25),
                      (1 - camz) * PROJ / np.maximum(-dyr, 0.25)).astype(np.float32)
        fx = px + rd[None, :] * rdx[:, None].astype(np.float32)
        fy = py + rd[None, :] * rdy[:, None].astype(np.float32)
        cx = np.clip(fx.astype(np.int32), 0, MAP_W - 1)
        cy = np.clip(fy.astype(np.int32), 0, MAP_H - 1)
        cell = cy * MAP_W + cx
        fid = np.take(self.fc, cell + isfloor[None, :] * (MAP_W * MAP_H))
        sky = (fid == SKY) & ~wallm
        ftu = (fx * TS).astype(np.int32) & (TS - 1)
        ftv = (fy * TS).astype(np.int32) & (TS - 1)
        flat_idx = (np.where(fid == SKY, C_STONE, fid) * TS + ftu) * TS + ftv
        wall_idx = ((tid * TS + tu) * TS)[:, None] + tv
        index = np.where(wallm, wall_idx, flat_idx)
        has_sky = bool(sky.any())
        if has_sky:
            sw, shh = self.sky.shape[:2]
            ang_col = np.arctan2(rdy, rdx)
            su = ((ang_col / (2 * math.pi)) * 1024).astype(np.int32) % sw
            sv = np.clip((rows + (shh - h) - 4).astype(np.int32), 0, shh - 1)
            sky_idx = self.sky_base + su[:, None] * shh + sv[None, :]
            index = np.where(sky, sky_idx, index)
        img = np.take(self.flat32, index).view(np.uint8).reshape(W, VIEW_H, 4)[..., :3]
        # light: the cell's own light times distance fog
        wl = (light_now[pry, prx] * fog(dist) * np.where(side == 1, 0.8, 1.0)).astype(np.float32)
        fl = np.take(light_now.ravel(), cell) * fog(rd)[None, :]
        shade = np.where(wallm, wl[:, None], fl)
        if flash:
            shade += np.float32(flash * 0.25)
        if has_sky:
            shade = np.where(sky, np.float32(1.0), shade)
        if lights:
            # glow of flying fireballs / the palm flash, at half resolution (it is smooth)
            wh = wallm[::2, ::2]
            gx = np.where(wh, wx[::2, None].astype(np.float32), fx[::2, ::2])
            gy = np.where(wh, wy[::2, None].astype(np.float32), fy[::2, ::2])
            glow = None
            for lx, ly, inten, tint in lights[:3]:
                ddx = gx - np.float32(lx)
                ddy = gy - np.float32(ly)
                ddx *= ddx
                ddy *= ddy
                ddx += ddy
                ddx *= np.float32(2.5)
                ddx += np.float32(1.0)
                g = (np.float32(inten) / ddx)[..., None] * np.asarray(tint, np.float32)
                glow = g if glow is None else glow + g
            glow = glow.repeat(2, 0).repeat(2, 1)
            if has_sky:
                glow[sky] = 0
            glow += shade[..., None]
            out = img * glow
        else:
            out = img * shade[..., None]
        np.clip(out, 0, 255, out=out)
        pygame.surfarray.blit_array(self.view, out.astype(np.uint8))
        return self.view


# ---- art ---------------------------------------------------------------------
TINT_MULT = (255, 120, 110)
TINT_ADD = (64, 0, 0)
BOSS_MULT = (230, 170, 190)
BOSS_ADD = (40, 0, 30)
LIGHT_LEVELS = 10


def _burst_frames(core, edge, n=7, r=14):
    out = []
    rnd = random.Random(core[0] * 7 + edge[2])
    for k in range(n):
        t = k / (n - 1)
        s = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        rad = int(3 + (r - 2) * t ** 0.6)
        a = int(255 * (1 - t) ** 0.8)
        pygame.draw.circle(s, edge + (a // 2,), (r + 2, r + 2), rad)
        pygame.draw.circle(s, core + (a,), (r + 2, r + 2), max(1, int(rad * (0.8 - 0.6 * t))))
        for _ in range(10):
            an = rnd.uniform(0, 6.28)
            d = rad * rnd.uniform(0.6, 1.1)
            pygame.draw.circle(s, (255, 255, 255, a), (int(r + 2 + math.cos(an) * d), int(r + 2 + math.sin(an) * d)), 1)
        out.append(s)
    return out


def _keycard(col):
    s = pygame.Surface((10, 14), pygame.SRCALPHA)
    pygame.draw.rect(s, (20, 20, 20), (0, 0, 10, 14))
    pygame.draw.rect(s, col, (1, 1, 8, 12))
    pygame.draw.rect(s, (255, 255, 255), (2, 3, 6, 2))
    pygame.draw.circle(s, (250, 240, 220), (5, 9), 2)
    pygame.draw.rect(s, (0, 0, 0), (4, 9, 1, 1))
    pygame.draw.rect(s, (0, 0, 0), (6, 9, 1, 1))
    return s


def _torch_frames():
    out = []
    rnd = random.Random(3)
    for k in range(4):
        s = pygame.Surface((12, 40), pygame.SRCALPHA)
        pygame.draw.rect(s, (40, 36, 40), (4, 18, 4, 22))
        pygame.draw.rect(s, (90, 84, 90), (5, 18, 1, 22))
        pygame.draw.rect(s, (60, 54, 60), (2, 16, 8, 3))
        for j in range(14):
            y = 15 - j
            w = max(1, int((5 - j * 0.33) + rnd.uniform(-1, 1)))
            x = 6 + rnd.choice((-1, 0, 0, 1))
            c = (255, 240, 160) if j < 4 else ((255, 150, 40) if j < 9 else (220, 50, 20))
            pygame.draw.line(s, c, (x - w // 2, y), (x + w // 2, y))
        out.append(s)
    return out


def _portal_frames():
    out = []
    for k in range(8):
        s = pygame.Surface((30, 40), pygame.SRCALPHA)
        for r in range(7, 0, -1):
            ph = (k / 8 + r / 7) * math.tau
            c = (int(140 + 100 * math.sin(ph)), int(40 + 30 * math.sin(ph + 2)), 255, 200)
            pygame.draw.ellipse(s, c, (15 - r * 2, 20 - r * 3 + 1, r * 4, r * 6 - 2))
        pygame.draw.ellipse(s, (255, 255, 255, 230), (12, 15, 6, 10))
        out.append(s)
    return out


def _tinted(img, mult, add):
    s = img.copy()
    s.fill(mult + (255,), special_flags=pygame.BLEND_RGBA_MULT)
    s.fill(add + (0,), special_flags=pygame.BLEND_RGBA_ADD)
    return s


# ---- shaded pixel-art rigs ---------------------------------------------------
# First-person hands and feet, the demons and the fireballs are built from
# "capsules" (a line segment with a radius at each end, at a depth): every
# pixel gets the nearest capsule's surface normal, which is lit from the top
# left and snapped to a small palette with a little ordered dither, then
# outlined - a cheap way to get chunky, rounded, hand-shaded looking sprites.
_BAYER = _BAYER_T
PALETTES = {
    "skin": [(40, 14, 12), (88, 36, 30), (150, 62, 38), (190, 84, 46), (214, 102, 56), (234, 128, 68)],
    "claw": [(30, 6, 6), (70, 12, 12), (130, 24, 20), (190, 60, 50)],
    "nail": [(40, 16, 18), (86, 44, 42), (140, 92, 86)],
    "bead": [(22, 6, 6), (40, 14, 12), (62, 22, 20), (90, 34, 32), (140, 66, 60), (210, 150, 130)],
    "cord": [(20, 8, 8), (40, 16, 14), (60, 26, 20)],
    "gi": [(18, 14, 26), (34, 28, 48), (54, 44, 72), (78, 64, 100), (104, 88, 130)],
    "pink": [(62, 14, 30), (112, 34, 56), (162, 64, 86), (206, 104, 120), (238, 152, 160)],
    "brown": [(34, 18, 10), (66, 40, 22), (104, 68, 40), (142, 100, 60), (180, 138, 90)],
    "red": [(48, 4, 8), (92, 12, 16), (146, 26, 26), (196, 50, 44), (234, 100, 84)],
    "bone": [(58, 50, 42), (106, 94, 78), (156, 144, 120), (202, 192, 166), (238, 232, 212)],
    "horn": [(70, 60, 50), (130, 118, 100), (196, 186, 160), (236, 230, 210)],
    "mouth": [(14, 0, 4), (44, 4, 10), (80, 10, 16)],
    "bluemouth": [(10, 6, 30), (24, 20, 70), (40, 44, 120)],
    "fatigue": [(18, 28, 12), (36, 54, 24), (60, 82, 38), (88, 112, 56), (118, 142, 80)],
    "pale": [(52, 36, 30), (100, 74, 62), (150, 116, 98), (196, 160, 136), (226, 196, 170)],
    "metal": [(20, 20, 24), (48, 48, 56), (86, 86, 96), (136, 136, 148), (190, 190, 200)],
    "loin": [(14, 26, 10), (30, 52, 20), (52, 80, 32)],
    "blood": [(60, 0, 0), (110, 6, 6), (150, 14, 12)],
    "hoof": [(20, 14, 14), (44, 34, 32), (74, 62, 56)],
    "eye_y": [(255, 214, 40)],
    "eye_r": [(255, 40, 20)],
    "eye_g": [(110, 255, 70)],
    "pupil": [(10, 0, 0)],
    "fire": [(255, 250, 200)],
    "flash": [(255, 255, 210)],
    "flash2": [(255, 190, 60)],
}
_MAT_NAMES = list(PALETTES)
_MAT_PAL = [np.array(PALETTES[n], np.float32) for n in _MAT_NAMES]
_SHINY = {"bead": 0.9, "claw": 0.7, "skin": 0.25, "metal": 0.8, "red": 0.35, "bone": 0.3, "pink": 0.25}
_FLAT = {n for n in PALETTES if len(PALETTES[n]) == 1}
_NO_RIM = _FLAT | {"blood"}


def rig_render(parts, w, h, light=(-0.5, -0.7, 0.55), rim=None, rim_k=0.55, outline=(14, 4, 6)):
    """parts: (x0, y0, x1, y1, r0, r1, z, material). Returns an RGBA surface (w, h)."""
    X, Y = np.meshgrid(np.arange(w, dtype=np.float32) + 0.5, np.arange(h, dtype=np.float32) + 0.5, indexing="ij")
    Z = np.full((w, h), -1e9, np.float32)
    NX = np.zeros((w, h), np.float32)
    NY = np.zeros((w, h), np.float32)
    NZ = np.ones((w, h), np.float32)
    M = np.full((w, h), -1, np.int16)
    for x0, y0, x1, y1, r0, r1, z, mat in parts:
        rr = max(r0, r1) + 1
        bx0, bx1 = max(0, int(min(x0, x1) - rr)), min(w, int(max(x0, x1) + rr) + 1)
        by0, by1 = max(0, int(min(y0, y1) - rr)), min(h, int(max(y0, y1) + rr) + 1)
        if bx0 >= bx1 or by0 >= by1:
            continue
        xs, ys = X[bx0:bx1, by0:by1], Y[bx0:bx1, by0:by1]
        dx, dy = x1 - x0, y1 - y0
        l2 = dx * dx + dy * dy
        t = np.clip(((xs - x0) * dx + (ys - y0) * dy) / l2, 0, 1) if l2 > 1e-6 else np.zeros_like(xs)
        ex = xs - (x0 + t * dx)
        ey = ys - (y0 + t * dy)
        r = r0 + (r1 - r0) * t
        d2 = ex * ex + ey * ey
        hz = np.sqrt(np.maximum(r * r - d2, 0))
        zz = z + hz
        sub = Z[bx0:bx1, by0:by1]
        upd = (d2 < r * r) & (zz > sub)
        if not upd.any():
            continue
        sub[upd] = zz[upd]
        rs = np.maximum(r, 0.3)
        NX[bx0:bx1, by0:by1][upd] = (ex / rs)[upd]
        NY[bx0:bx1, by0:by1][upd] = (ey / rs)[upd]
        NZ[bx0:bx1, by0:by1][upd] = (hz / rs)[upd]
        M[bx0:bx1, by0:by1][upd] = _MAT_NAMES.index(mat)
    l = np.array(light, np.float32)
    l /= np.linalg.norm(l)
    diff = np.clip(NX * l[0] + NY * l[1] + NZ * l[2], 0, 1)
    hv = l + np.array((0, 0, 1), np.float32)
    hv /= np.linalg.norm(hv)
    spec = np.clip(NX * hv[0] + NY * hv[1] + NZ * hv[2], 0, 1) ** 24
    dith = np.tile(_BAYER, (w // 4 + 1, h // 4 + 1))[:w, :h]
    out = np.zeros((w, h, 3), np.float32)
    mask = M >= 0
    rimm = np.zeros((w, h), bool)
    for i in np.unique(M[mask]):
        m = M == i
        name = _MAT_NAMES[i]
        pal = _MAT_PAL[i]
        n = len(pal)
        if n == 1:
            out[m] = pal[0]
            continue
        if name == "bead":
            v = 0.08 + 0.62 * diff[m] + 0.9 * spec[m]
        else:
            v = 0.18 + 0.82 * diff[m] + _SHINY.get(name, 0) * spec[m]
        idx = np.clip((v * (n - 0.01) + dith[m] * 0.5).astype(np.int32), 0, n - 1)
        out[m] = pal[idx]
        if name not in _NO_RIM:
            rimm |= m
    if rim is not None:
        # the red ki glow catches the undersides and edges
        rk = np.clip(NY * 0.6 - NZ * 0.8 + 0.35, 0, 1) * rim_k
        rk = np.where((rk + dith * 0.3 > 0.32) & rimm, rk, 0)
        out = out * (1 - rk[..., None]) + np.asarray(rim, np.float32) * rk[..., None]
    mask[0, :] = mask[-1, :] = False
    mask[:, 0] = mask[:, -1] = False
    # creases: a pixel well behind its neighbour gets an ink line
    crease = np.zeros_like(mask)
    for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        crease |= mask & (np.roll(np.roll(Z, sx, 0), sy, 1) - Z > 2.6)
    flat = np.isin(M, [_MAT_NAMES.index(f) for f in _FLAT])
    crease &= ~flat
    out[crease] = out[crease] * 0.35 + np.asarray(outline, np.float32) * 0.65
    edge = np.zeros_like(mask)
    for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        edge |= np.roll(np.roll(mask, sx, 0), sy, 1)
    edge &= ~mask
    out[edge] = outline
    alpha = np.where(mask | edge, 255, 0).astype(np.uint8)
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.surfarray.blit_array(s, np.clip(out, 0, 255).astype(np.uint8))
    pygame.surfarray.pixels_alpha(s)[:] = alpha
    return s


KI_FLAME = ((255, 110, 70), (246, 40, 24), (226, 22, 16), (206, 14, 12), (178, 8, 8), (148, 4, 6), (118, 0, 4),
            (90, 0, 0))
HOT_FLAME = ((255, 255, 210), (255, 236, 120), (255, 190, 60), (255, 130, 30), (240, 70, 20), (200, 30, 10),
             (150, 10, 6), (100, 0, 0))


def flame_aura(sprite, phase, reach=7, cols=KI_FLAME, fade_y=None, pad=None):
    """Flames licking up around a sprite's silhouette (returns a padded copy;
    the sprite sits at (pad, pad) in it). fade_y: below this row of the
    sprite the flames die out."""
    a0 = pygame.surfarray.array_alpha(sprite) > 0
    w, h = a0.shape
    P = reach + 2 if pad is None else pad
    a = np.zeros((w + 2 * P, h + 2 * P), bool)
    a[P:P + w, P:P + h] = a0
    W2, H2 = a.shape
    rng = np.random.default_rng(phase * 7 + 1)
    dist = np.full(a.shape, 99, np.int16)
    cur = a.copy()
    dist[a] = 0
    for k in range(1, reach + 1):
        nxt = cur.copy()
        nxt[:, :-1] |= cur[:, 1:]
        if k % 2:
            nxt[:, :-2] |= cur[:, 2:]
        nxt[1:, :] |= cur[:-1, :]
        nxt[:-1, :] |= cur[1:, :]
        if k % 3 == 0:
            nxt[:, 1:] |= cur[:, :-1]
        dist[nxt & ~cur] = k
        cur = nxt
    n = rng.random((W2 + 2, H2 // 5 + 3)).repeat(5, 1)
    sh = phase % 5
    n = n[:W2, sh:sh + H2]
    n2 = rng.random((W2, H2))
    lim = (dist - 0.5) / (reach + 1) * 1.05
    if fade_y is not None:
        yy = np.arange(H2)[None, :] - P
        lim = lim + np.clip((yy - fade_y) / 20.0, 0, 2)
    keep = (dist > 0) & (dist <= reach) & (((n * 0.85 + n2 * 0.15) > lim) | ((dist == 1) & (lim < 1)))
    out = np.zeros((W2, H2, 3), np.uint8)
    al = np.zeros((W2, H2), np.uint8)
    for k in range(1, reach + 1):
        m = keep & (dist == k)
        out[m] = cols[min(len(cols) - 1, k - 1)]
        al[m] = 255
    s = pygame.Surface((W2, H2), pygame.SRCALPHA)
    pygame.surfarray.blit_array(s, out)
    pygame.surfarray.pixels_alpha(s)[:] = al
    s.blit(sprite, (P, P))
    return s


def rig_place(parts, ox, oy, s=1.0, rot=0.0, mirror=False, sy=None):
    """Moves, turns, scales (and mirrors) a list of capsules."""
    c, sn = math.cos(rot), math.sin(rot)
    sy = s if sy is None else sy
    out = []
    for x0, y0, x1, y1, r0, r1, z, m in parts:
        if mirror:
            x0, x1 = -x0, -x1
        out.append((ox + s * (x0 * c - y0 * sn), oy + sy * (x0 * sn + y0 * c),
                    ox + s * (x1 * c - y1 * sn), oy + sy * (x1 * sn + y1 * c), r0 * s, r1 * s, z * s, m))
    return out


def _mirror_x(parts, cx):
    return [(2 * cx - x0, y0, 2 * cx - x1, y1, r0, r1, z, m) for x0, y0, x1, y1, r0, r1, z, m in parts]


# ---- Akuma's own hands and feet ------------------------------------------------
def hand_parts(curl=0.6, spread=0.0, fist=0.0):
    """Akuma's right hand seen from behind, wrist at (0, 0), fingers up:
    claws hooked round a ball of ki (curl), splayed (spread) or a fist."""
    P = [(3, 8, 14, 90, 10.5, 15, 0, "skin"), (0, -2, 2, 8, 9.5, 10, 1, "skin")]   # forearm, wrist
    for x0, y0, x1, y1, r in ((-7, -6, -8, -17, 6.5), (-1, -5, -2, -20, 7.5), (5, -5, 5, -19, 7.0),
                              (10, -4, 11, -15, 5.5)):
        P.append((x0, y0, x1, y1, r, r * 0.9, 3, "skin"))                              # back of the hand
    fingers = ((-9, -21.5, 1.0, -118), (-2.5, -24.5, 1.1, -98), (4.5, -23.5, 1.04, -78), (10.5, -19, 0.84, -58))
    for i, (kx, ky, ls, a0) in enumerate(fingers):
        a = math.radians(a0 + spread * (i - 1.5) * 8 - curl * (i - 1.5) * 4)
        sgn = 1 if a0 < -90 else -1
        x, y, z = kx, ky, 5
        P.append((x, y + 1, x, y + 1, 4.2, 4.2, 5.5, "skin"))                         # knuckle
        if fist >= 0.5:
            P.append((x, y, x + math.cos(a) * 3, y + math.sin(a) * 3 - 1, 4.0, 3.8, 7, "skin"))
            continue
        for j, (L, r0, r1) in enumerate(((10 * ls, 4.0, 3.5), (7.5 * ls, 3.5, 3.0), (5.5 * ls, 3.0, 2.4))):
            if j:
                a += sgn * math.radians(20 + 30 * curl)
            fore = 1 - curl * 0.18 * j
            nx, ny = x + math.cos(a) * L * fore, y + math.sin(a) * L * fore
            nz = z + (1.5 + 2 * curl) * j
            P.append((x, y, nx, ny, r0, r1, nz, "skin"))
            x, y, z = nx, ny, nz
        a += sgn * math.radians(25 * curl)
        P.append((x, y, x + math.cos(a) * 5.5, y + math.sin(a) * 5.5, 2.4, 0.3, z + 1.5, "claw"))
    ta = math.radians(-138 + 20 * curl + 40 * fist)                                    # thumb
    x, y = -10, -5
    for L, r0, r1 in ((8, 4.6, 3.9), (6.5, 3.8, 3.0)):
        nx, ny = x + math.cos(ta) * L, y + math.sin(ta) * L
        P.append((x, y, nx, ny, r0, r1, 6, "skin"))
        x, y = nx, ny
        ta += math.radians(28 + 25 * curl)
    if fist < 0.5:
        P.append((x, y, x + math.cos(ta) * 4.0, y + math.sin(ta) * 4.0, 1.9, 0.4, 7, "claw"))
    cx, cy, ax, ay = 1, 4, 13, 4.5                                                     # prayer beads
    for k in range(28):
        th = k / 28 * math.tau
        P.append((cx + ax * math.cos(th), cy + ay * math.sin(th), cx + ax * math.cos(th + 0.25),
                  cy + ay * math.sin(th + 0.25), 1.6, 1.6, 2 + 8 * math.sin(th), "cord"))
    for k in range(10):
        th = k / 10 * math.tau + 0.3
        bx, by = cx + ax * math.cos(th), cy + ay * math.sin(th)
        P.append((bx, by, bx, by, 4.3, 4.3, 3 + 9 * math.sin(th), "bead"))
    return P


def leg_parts():
    """Akuma's right leg kicking away from the camera: ankle at (0, 0), toes up."""
    P = [(3, 22, 16, 140, 15, 32, 0, "gi"), (16, 140, 30, 300, 32, 40, 0, "gi")]          # baggy gi trousers
    cx, cy, ax, ay = 1, 21, 15, 5                                                      # torn cuff
    for k in range(16):
        th = k / 16 * math.tau
        bx, by = cx + ax * math.cos(th), cy + ay * math.sin(th)
        L = (5, 9, 4, 7, 10, 5, 8, 3, 6, 9, 4, 7, 5, 8, 6, 4)[k] * max(0.0, math.sin(th) * 0.8 + 0.4)
        P.append((bx, by, bx + 0.6 * math.cos(th), by - L, 3.2, 1.2, 4 + 9 * math.sin(th), "gi"))
    P += [(0, 0, 1, 20, 8.5, 10, 2, "skin"),                                           # shin
          (-8.5, 1, -8.5, 1, 3.4, 3.4, 7, "skin"), (8.5, 0, 8.5, 0, 3.2, 3.2, 7, "skin")]  # ankle bones
    cx, cy, ax, ay = 0.5, 7, 11.5, 3.6                                                 # bead anklet
    for k in range(9):
        th = k / 9 * math.tau + 0.2
        bx, by = cx + ax * math.cos(th), cy + ay * math.sin(th)
        P.append((bx, by, bx, by, 3.3, 3.3, 3 + 9 * math.sin(th), "bead"))
    L = 20
    P += [(0, -2, 0, -L, 10, 11.5, 6, "skin"), (-6, -4, -7, -L, 5, 6, 8, "skin"), (6, -3, 8, -L + 3, 4.5, 5, 7.5, "skin")]
    for x, y, r in ((-7.5, -L - 8, 5.6), (1, -L - 9.5, 4.2), (6.5, -L - 8.2, 3.8), (11, -L - 6, 3.4), (14.5, -L - 2.5, 3.0)):
        P.append((x * 0.85, y + 7, x, y, r, r * 0.95, 10, "skin"))
        P.append((x, y + r * 0.1, x, y - r * 0.2, r * 0.38, r * 0.3, 10 + r, "nail"))
    return P


# ---- fireballs seen from behind / in front -------------------------------------------
FIRE_KI = ((255, 255, 220), (255, 236, 130), (255, 180, 60), (250, 110, 30), (220, 50, 16), (150, 16, 8))
# Akuma's own ki, the colours of the fx sheet: white core, lilac, magenta, blood red
AKUMA_KI = ((255, 255, 255), (250, 214, 250), (226, 120, 230), (240, 40, 96), (196, 14, 40), (120, 4, 24))
SHINKU_KI = ((255, 255, 255), (246, 206, 255), (206, 120, 255), (196, 40, 170), (140, 12, 96), (76, 0, 52))


def ball_view(cols, view, phase, r=11):
    """A ki ball seen from behind (view "back": core ringed by the flame
    trail streaming toward the camera) or in front ("front": a hot core with
    a short corona). Returns a (4r x 4r) RGBA surface."""
    size = r * 4
    X, Y = np.meshgrid(np.arange(size) + 0.5 - size / 2, np.arange(size) + 0.5 - size / 2, indexing="ij")
    rad = np.hypot(X, Y)
    th = np.arctan2(Y, X)
    t = phase * 0.7
    if view == "back":
        core = r * 0.55
        sw = th + rad * 0.09 + t * 0.6                       # swirl
        tongue = (np.sin(sw * 5) * 0.5 + 0.5) ** 2 * 0.6 + (np.sin(sw * 9 + 1.3 + t) * 0.5 + 0.5) * 0.4
        reach = core + r * (0.55 + 0.95 * tongue)
        lvl = np.where(rad < core, (rad / core) * 1.6, 1.6 + (rad - core) / np.maximum(reach - core, 0.5) * 3.4)
        inside = rad < reach
    else:
        core = r * 0.75
        flick = (np.sin(th * 7 + t * 2) * 0.5 + 0.5) * 0.6 + (np.sin(th * 13 - t * 3) * 0.5 + 0.5) * 0.4
        reach = core + r * (0.15 + 0.35 * flick)
        lvl = np.where(rad < core, (rad / core) * 2.2, 2.2 + (rad - core) / np.maximum(reach - core, 0.5) * 2.8)
        inside = rad < reach
    dith = np.tile(_BAYER, (size // 4 + 1, size // 4 + 1))[:size, :size]
    idx = np.clip((lvl + dith * 0.8).astype(np.int32), 0, len(cols) - 1)
    out = np.asarray(cols, np.uint8)[idx]
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.surfarray.blit_array(s, out)
    pygame.surfarray.pixels_alpha(s)[:] = np.where(inside, 255, 0).astype(np.uint8)
    return s


def _ball_core(img, size):
    """The round head of a side-view fireball frame (its right end), scaled
    to size x size: the ball seen head-on, its tail hidden behind it."""
    w, h = img.get_size()
    side = min(w, h)
    core = img.subsurface(pygame.Rect(w - side, (h - side) // 2, side, side)).copy()
    return pygame.transform.smoothscale(core, (size, size))


def fx_ball_views(row, height, ring, ring_r, core):
    """Side / back / front views of a sheet fireball. side: the sheet's fly
    frames; front: the round head of the ball, swirling; back: the flame
    trail streaming toward the camera (ball_view in the sheet's colours)
    round that same head."""
    side = fx.fx_frames(row, height)
    heads = [_ball_core(f, int(height * 0.9)) for f in fx.fx_frames(core)]
    n = len(heads)
    back, front = [], []
    for k in range(4):
        b = ball_view(ring, "back", k, ring_r)
        h = pygame.transform.smoothscale(heads[(k * 2) % n], (ring_r * 2, ring_r * 2))
        b.blit(h, ((b.get_width() - h.get_width()) // 2, (b.get_height() - h.get_height()) // 2))
        back.append(b)
        f = ball_view(ring, "front", k, ring_r)
        h = heads[(k * 2 + 1) % n]
        f.blit(h, ((f.get_width() - h.get_width()) // 2, (f.get_height() - h.get_height()) // 2))
        front.append(f)
    return {"side": side, "back": back, "front": front}


def load_hands():
    """Toshi's first-person hands: {row: [(surface, (ax, ay))]}, the anchor
    being the centre of the arm's base on the sheet's bottom edge."""
    d = os.path.join(asset_dir(), "doom_hands")
    with open(os.path.join(d, "anchors.json")) as f:
        anchors = json.load(f)
    out = {}
    for row, ancs in anchors.items():
        frames = []
        for i, (ax, ay) in enumerate(ancs):
            img = pygame.image.load(os.path.join(d, "%s_%d.png" % (row, i)))
            try:
                img = img.convert_alpha()
            except pygame.error:
                pass
            frames.append((img, (ax, ay)))
        out[row] = frames
    return out


# ---- the demons -----------------------------------------------------------------
# Front views (they always face Akuma) on a canvas with the feet at the bottom
# centre. Each builder gives the capsules for a pose: "walk" (phase 0..3),
# "attack" (0 wind-up, 1 strike), "pain".
def _sym(parts, cx):
    """Both sides of a symmetric body from its left half."""
    return parts + _mirror_x(parts, cx)


def _imp(pose, ph):
    cx, P = 32, []
    step = (0, 1, 0, -1)[ph % 4] if pose == "walk" else 0
    for side, lift in ((-1, step), (1, -step)):
        hx = cx + side * 7
        kx, ky = cx + side * 9, 58 - max(0, lift) * 3
        fx, fy = cx + side * 8, 73 - max(0, lift) * 4
        P += [(hx, 46, kx, ky, 5.5, 5, 2, "brown"), (kx, ky, fx, fy - 2, 4.6, 3.8, 3, "brown"),
              (fx, fy - 1, fx + side * 1, fy, 3.6, 3.2, 4, "brown")]
        for c in (-2, 0, 2):
            P.append((fx + c * 1.4, fy, fx + c * 2.2, fy + 1.5, 1.2, 0.4, 6, "horn"))
    P += [(cx, 44, cx, 44, 8, 8, 4, "loin"), (cx - 3, 46, cx - 4, 53, 4, 2.5, 6, "loin"),
          (cx + 3, 46, cx + 4, 53, 4, 2.5, 6, "loin")]
    P.append((cx, 40, cx, 26, 10.5, 12, 3, "brown"))                                 # torso
    P += _sym([(cx - 5, 27, cx - 5, 27, 6, 6, 8, "brown"), (cx - 3, 34, cx - 3, 34, 3.4, 3.4, 9, "brown"),
               (cx - 3, 39, cx - 3, 39, 3.2, 3.2, 8, "brown"), (cx - 13, 23, cx - 13, 23, 6.5, 6.5, 6, "brown"),
               (cx - 14, 20, cx - 17, 13, 2.2, 0.3, 10, "horn"), (cx - 10, 20, cx - 11, 14, 1.8, 0.3, 10, "horn"),
               (cx - 6, 31, cx - 6, 31, 1.5, 1.5, 11, "horn")], cx)
    arms = []
    for side in (-1, 1):
        sx = cx + side * 14
        if pose == "attack" and side == 1:
            up = ph == 0
            ex, ey = (sx + 6, 12) if up else (sx + 2, 24)
            hx, hy = (sx + 2, 3) if up else (cx + 6, 22)
        elif pose == "pain":
            ex, ey, hx, hy = sx + side * 7, 20, sx + side * 6, 9
        else:
            sway = (0, 1, 0, -1)[ph % 4] * side if pose == "walk" else 0
            ex, ey, hx, hy = sx + side * 5, 36 + sway, sx + side * 3 - sway, 47
        arms += [(sx, 25, ex, ey, 4.8, 4.2, 5, "brown"), (ex, ey, hx, hy, 4.2, 3.4, 7, "brown"),
                 (hx, hy, hx, hy, 3.8, 3.8, 8, "brown")]
        for c in (-1, 0, 1):
            arms.append((hx + c * 2, hy + 2, hx + c * 3, hy + 5, 1.1, 0.3, 9, "horn"))
    P += arms
    hx = cx + (3 if pose == "pain" else 0)
    P += [(hx, 15, hx, 15, 7.8, 7.8, 6, "brown"), (hx, 19, hx, 21, 5, 4.5, 7, "brown")]  # head, jaw
    P += [(hx - 4, 11, hx - 8, 6, 2.2, 0.3, 12, "horn"), (hx + 4, 11, hx + 8, 6, 2.2, 0.3, 12, "horn"),
          (hx - 6, 14, hx - 2, 12, 1.6, 1.6, 12, "brown"), (hx + 6, 14, hx + 2, 12, 1.6, 1.6, 12, "brown"),
          (hx - 3, 15, hx - 3, 15, 1.5, 1.5, 14, "eye_r"), (hx + 3, 15, hx + 3, 15, 1.5, 1.5, 14, "eye_r"),
          (hx, 20.5, hx, 21.5, 3.0 if pose == "attack" else 2.2, 2.6, 13, "mouth")]
    P += [(hx - 1.6, 19, hx - 1.6, 20.5, 0.7, 0.3, 15, "horn"), (hx + 1.6, 19, hx + 1.6, 20.5, 0.7, 0.3, 15, "horn")]
    if pose == "attack":
        bx, by = (cx + 16, -1) if ph == 0 else (cx + 6, 20)
        P += [(bx, by, bx, by, 4.5, 4.5, 20, "flash2"), (bx, by, bx, by, 2.6, 2.6, 22, "flash")]
    return P


def _pinky(pose, ph):
    cx, P = 36, []
    step = (0, 1, 0, -1)[ph % 4] if pose == "walk" else 0
    lunge = 3 if pose == "attack" and ph == 1 else 0
    for side, lift in ((-1, step), (1, -step)):
        hx, kx, ky = cx + side * 11, cx + side * 17, 57 - max(0, lift) * 3
        fx, fy = cx + side * 14, 71 - max(0, lift) * 3
        P += [(hx, 46, kx, ky, 8.5, 6.5, 3, "pink"), (kx, ky, fx, fy - 3, 5.5, 4.4, 4, "pink"),
              (fx, fy - 1, fx, fy + 1, 4.8, 4.6, 5, "hoof")]
    P += [(cx, 44, cx, 44, 13, 13, 4, "pink"), (cx, 40, cx, 28 + lunge, 16, 18, 3, "pink")]
    P += _sym([(cx - 7, 30 + lunge, cx - 7, 30 + lunge, 8, 8, 10, "pink"),
               (cx - 4, 41, cx - 4, 41, 4.5, 4.5, 11, "pink"), (cx - 18, 26 + lunge, cx - 18, 26 + lunge, 9.5, 9.5, 8, "pink")], cx)
    for side in (-1, 1):
        sx = cx + side * 20
        if pose == "attack" and ph == 1:
            ex, ey, hx, hy = sx + side * 4, 30, cx + side * 9, 32
        elif pose == "pain":
            ex, ey, hx, hy = sx + side * 9, 22, sx + side * 7, 12
        else:
            sway = (0, 1, 0, -1)[ph % 4] * side if pose == "walk" else 0
            ex, ey, hx, hy = sx + side * 6, 40 + sway, sx + side * 3, 53 - sway
        P += [(sx, 28 + lunge, ex, ey, 7.5, 6.2, 6, "pink"), (ex, ey, hx, hy, 6.2, 5.2, 8, "pink"),
              (hx, hy, hx, hy, 6.0, 6.0, 10, "pink")]
        for c in (-1, 0, 1):
            P.append((hx + c * 3, hy + 4, hx + c * 4, hy + 7, 1.3, 0.3, 12, "horn"))
    hy = 22 + lunge * 2
    hx = cx + (3 if pose == "pain" else 0)
    jaw = 9 if pose == "attack" else (6 if pose == "pain" else 4.5)
    P += [(hx, hy - 4, hx, hy, 11, 12, 10, "pink"),
          (hx - 13, hy - 6, hx - 19, hy - 13, 3.2, 0.5, 16, "horn"), (hx + 13, hy - 6, hx + 19, hy - 13, 3.2, 0.5, 16, "horn"),
          (hx - 6, hy - 6, hx - 2, hy - 8, 2.2, 2.2, 19, "pink"), (hx + 6, hy - 6, hx + 2, hy - 8, 2.2, 2.2, 19, "pink"),
          (hx - 5, hy - 4, hx - 5, hy - 4, 1.6, 1.6, 21, "eye_y"), (hx + 5, hy - 4, hx + 5, hy - 4, 1.6, 1.6, 21, "eye_y"),
          (hx - 4, hy + 4, hx + 4, hy + 4, jaw * 0.7, jaw * 0.7, 20, "mouth")]
    for k in range(5):                                                                 # fangs
        tx = hx - 6 + k * 3
        P.append((tx, hy + 4 - jaw * 0.6, tx, hy + 4 - jaw * 0.6 + 2.6, 1.2, 0.3, 24, "bone"))
        P.append((tx + 1.5, hy + 4 + jaw * 0.6, tx + 1.5, hy + 4 + jaw * 0.6 - 2.4, 1.1, 0.3, 24, "bone"))
    return P


def _caco(pose, ph):
    cx, cy, P = 30, 30, []
    bob = (0, 1, 1, 0)[ph % 4]
    cy += bob
    P.append((cx, cy, cx, cy, 22, 22, 0, "red"))
    for k in range(9):                                                                 # warty bumps
        a = k * 2.4 + 0.5
        rr = 14 + (k % 3) * 2
        P.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.9, cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.9,
                  2.8, 2.8, 14, "red"))
    for k in range(5):                                                                 # horns
        a = math.radians(-150 + k * 30)
        x0, y0 = cx + math.cos(a) * 19, cy + math.sin(a) * 19
        P.append((x0, y0, cx + math.cos(a) * 27, cy + math.sin(a) * 27, 2.6, 0.4, 8, "horn"))
    op = {"attack": 1.4 if ph else 1.0, "pain": 0.8}.get(pose, 0.65)
    my = cy + 9
    P.append((cx - 11, my, cx + 11, my, 5 * op, 5 * op, 18, "bluemouth"))
    P.append((cx, my + 1, cx, my + 1, 7 * op, 7 * op, 17, "bluemouth"))
    for k in range(9):
        tx = cx - 12 + k * 3
        dy = 4.6 * op
        P.append((tx, my - dy, tx, my - dy + 3.4, 1.4, 0.3, 26, "bone"))
        P.append((tx + 1.5, my + dy + 1, tx + 1.5, my + dy - 2.2, 1.3, 0.3, 26, "bone"))
    if pose == "attack" and ph:
        P += [(cx, my + 1, cx, my + 1, 4.5, 4.5, 30, "flash2"), (cx, my + 1, cx, my + 1, 2.5, 2.5, 32, "flash")]
    ey = cy - 8
    if pose == "pain":
        P.append((cx - 6, ey, cx + 6, ey, 2.6, 2.6, 24, "red"))
    else:
        P += [(cx, ey, cx, ey, 6.5, 6.5, 18, "bone"), (cx, ey, cx, ey, 3.6, 3.6, 25, "eye_g"),
              (cx, ey, cx, ey + 0.5, 1.6, 1.2, 27, "pupil"), (cx - 7, ey - 6, cx + 7, ey - 6, 2.6, 2.6, 23, "red")]
    return P


def _soul(pose, ph):
    cx, cy, P = 18, 20, []
    P += [(cx, cy, cx, cy - 2, 9, 9.5, 2, "bone"), (cx, cy + 6, cx, cy + 8, 6, 5, 5, "bone"),
          (cx - 9, cy - 4, cx - 14, cy - 10, 2.4, 0.4, 8, "horn"), (cx + 9, cy - 4, cx + 14, cy - 10, 2.4, 0.4, 8, "horn"),
          (cx - 4, cy - 1, cx - 4, cy, 2.8, 2.8, 12, "mouth"), (cx + 4, cy - 1, cx + 4, cy, 2.8, 2.8, 12, "mouth"),
          (cx - 4, cy - 0.5, cx - 4, cy - 0.5, 1.3, 1.3, 15, "eye_r"), (cx + 4, cy - 0.5, cx + 4, cy - 0.5, 1.3, 1.3, 15, "eye_r"),
          (cx, cy + 3.5, cx, cy + 3.5, 1.3, 1.0, 14, "mouth")]
    jaw = 3.0 if pose == "attack" else 1.6
    P.append((cx - 3, cy + 8, cx + 3, cy + 8, jaw, jaw, 13, "mouth"))
    for k in range(4):
        P.append((cx - 3 + k * 2, cy + 8 - jaw, cx - 3 + k * 2, cy + 8 - jaw + 1.6, 0.9, 0.3, 16, "bone"))
    return P


def _zombie(pose, ph):
    cx, P = 30, []
    step = (0, 1, 0, -1)[ph % 4] if pose == "walk" else 0
    for side, lift in ((-1, step), (1, -step)):
        hx, kx, ky = cx + side * 5, cx + side * 6, 58 - max(0, lift) * 3
        fx, fy = cx + side * 6, 71 - max(0, lift) * 3
        P += [(hx, 44, kx, ky, 5, 4.6, 2, "fatigue"), (kx, ky, fx, fy - 2, 4.4, 4, 3, "fatigue"),
              (fx, fy - 1, fx + side, fy + 1, 3.8, 3.6, 5, "hoof")]
    P += [(cx, 43, cx, 43, 7.5, 7.5, 3, "fatigue"), (cx, 40, cx, 27, 9.5, 10.5, 3, "fatigue"),
          (cx - 9, 42, cx + 9, 42, 1.8, 1.8, 10, "hoof"),
          (cx - 4, 32, cx - 1, 36, 2.6, 2.6, 12, "blood"), (cx + 3, 27, cx + 3, 27, 2.2, 2.2, 12, "blood")]
    P += _sym([(cx - 11, 25, cx - 11, 25, 5, 5, 6, "fatigue")], cx)
    aim = pose == "attack"
    # the rifle, held across the hips (raised at Akuma to fire)
    gy = 30 if aim else 37
    P += [(cx - 10, gy + 4, cx + 14, gy - 1, 2.6, 2.2, 14, "metal"), (cx + 2, gy + 2, cx + 3, gy + 7, 1.8, 1.6, 13, "metal")]
    P += [(cx - 11, 25, cx - 13, 34, 4.2, 3.8, 6, "fatigue"), (cx - 13, 34, cx - 8, gy + 4, 3.8, 3.2, 15, "pale"),
          (cx + 11, 25, cx + 13, 33, 4.2, 3.8, 6, "fatigue"), (cx + 13, 33, cx + 8, gy + 1, 3.8, 3.2, 15, "pale")]
    if aim and ph:
        P += [(cx + 17, gy - 2, cx + 17, gy - 2, 5, 5, 20, "flash2"), (cx + 17, gy - 2, cx + 17, gy - 2, 3, 3, 22, "flash")]
    hx = cx + (3 if pose == "pain" else 0)
    P += [(hx, 19, hx, 19, 3.5, 3.5, 4, "pale"), (hx, 14, hx, 15, 6.5, 6, 6, "pale"),
          (hx - 2.5, 14, hx - 2.5, 14, 1.2, 1.2, 13, "eye_r"), (hx + 2.5, 14, hx + 2.5, 14, 1.2, 1.2, 13, "eye_r"),
          (hx - 2, 18, hx + 2, 18, 1.2, 1.0, 12, "mouth"), (hx + 3, 11, hx + 4, 13, 1.6, 1.4, 12, "blood")]
    return P


DEMONS = {
    "imp": (_imp, 64, 76),
    "pinky": (_pinky, 72, 76),
    "caco": (_caco, 60, 62),
    "soul": (_soul, 36, 36),
    "zombie": (_zombie, 60, 76),
}


def _blood_pool(w, h, cx, size):
    return [(cx - size, h - 4, cx + size, h - 4, 3.2, 2.6, -5, "blood"),
            (cx - size * 0.4, h - 3, cx + size * 0.6, h - 3, 3.5, 3.0, -4, "blood")]


def demon_frames(kind):
    """{"walk": [4], "attack": [2], "pain": [1], "die": [4]} surfaces, plus the corpse."""
    fn, w, h = DEMONS[kind]
    out = {"walk": [rig_render(fn("walk", k), w, h) for k in range(4)],
           "attack": [rig_render(fn("attack", k), w, h) for k in range(2)],
           "pain": [rig_render(fn("pain", 0), w, h)]}
    base = fn("pain", 0)
    die = []
    floating = kind in ("caco", "soul")
    for k, (rot, sq) in enumerate(((0.25, 0.9), (0.6, 0.7), (1.1, 0.5), (1.5, 0.35))):
        if floating:
            rot = 0.0                       # drops out of the air and splats
        if True:
            # topples backwards: squash toward the feet and lean over
            parts = [(w / 2 + (x0 - w / 2) * (1 + k * 0.08) + (h - y0) * rot * 0.25,
                      h - (h - y0) * sq, w / 2 + (x1 - w / 2) * (1 + k * 0.08) + (h - y1) * rot * 0.25,
                      h - (h - y1) * sq, r0, r1, z, m) for x0, y0, x1, y1, r0, r1, z, m in base]
        if k >= 1:
            parts += _blood_pool(w, h, w / 2, 6 + k * 4)
        die.append(rig_render(parts, w, h))
    out["die"] = die
    out["dead"] = die[-1]
    return out


# ---- actors ----------------------------------------------------------------
KINDS = {
    "imp": dict(hp=45, speed=0.026, ranged=12, pain=0.7, wpp=0.0118, shot="fire", name="IMP"),
    "zombie": dict(hp=30, speed=0.02, ranged=8, pain=0.9, wpp=0.0115, shot="bullet", name="ZOMBIEMAN"),
    "pinky": dict(hp=110, speed=0.034, melee=20, pain=0.4, wpp=0.0118, radius=0.36, name="PINKY"),
    "caco": dict(hp=110, speed=0.018, ranged=15, pain=0.5, wpp=0.0112, fly=0.22, radius=0.36, shot="fire",
                 name="CACODEMON"),
    "soul": dict(hp=30, speed=0.05, melee=10, pain=0.9, wpp=0.0105, fly=0.32, radius=0.25, name="LOST SOUL"),
    "boss": dict(cid="zangief", hp=900, speed=0.022, melee=28, ranged=14, pain=0.0, boss=True,
                 wpp=0.02, radius=0.6, name="CYBER-GIEF"),
}
WPP = 0.0125                  # world units per sprite pixel for fighters


class Enemy:
    def __init__(self, kind, x, y, rng):
        spec = KINDS[kind]
        self.kind = kind
        self.spec = spec
        self.cid = spec.get("cid", kind)
        self.art = CharArt(self.cid) if "cid" in spec else None       # the demons are drawn in code
        self.fly = spec.get("fly", 0.0)
        self.z = self.fly
        self.x, self.y = x + 0.5, y + 0.5
        self.hp = self.max_hp = spec["hp"]
        self.speed = spec["speed"]
        self.boss = spec.get("boss", False)
        self.radius = spec.get("radius", 0.3)
        self.wpp = spec.get("wpp", WPP)
        self.state = "idle"
        self.st = 0
        self.alert = False
        self.cool = rng.randint(40, 100)
        self.flash = 0
        self.walked = 0.0
        self.volley = 0
        self.see = False
        self.look_t = rng.randint(0, 9)

    @property
    def alive(self):
        return self.state not in ("dying", "dead")

    def set(self, state):
        self.state, self.st = state, 0


class Shot:
    def __init__(self, x, y, ang, speed, owner, dmg, splash, radius, big=False, frames=None, wpp=0.012,
                 tint=(0.5, 0.7, 1.4), z=0.5):
        self.x, self.y, self.z = x, y, z
        self.vx, self.vy = math.cos(ang) * speed, math.sin(ang) * speed
        self.owner = owner           # "akuma" or an Enemy
        self.dmg, self.splash = dmg, splash
        self.radius = radius
        self.big = big
        self.frames = frames
        self.wpp = wpp
        self.tint = tint
        self.t = 0
        self.alive = True
        self.hit = set()


class Effect:
    def __init__(self, x, y, z, frames, wpp, speed=3):
        self.x, self.y, self.z = x, y, z
        self.frames, self.wpp, self.speed = frames, wpp, speed
        self.t = 0

    @property
    def alive(self):
        return self.t < len(self.frames) * self.speed


class Thing:
    def __init__(self, kind, x, y):
        self.kind = kind
        self.x, self.y = x + 0.5, y + 0.5
        self.taken = False


# ---- the scene ---------------------------------------------------------------
class DoomScene:
    def __init__(self, game, seed=None, level=13, hp=None):
        self.game = game
        self.level = level
        self.rng = random.Random(seed if seed is not None else 1313)
        self.menu = PauseMenu(game, CONTROLS)
        self.max_hp = game.akuma_max
        self.hp = self.max_hp if hp is None else hp
        self.power = getattr(game, "power", 1.0) or 1.0
        self.map = LevelMap(random.Random(13))
        self.r = Renderer(self.map)
        self.light_now = self.map.light.copy()
        self.px, self.py, self.ang = 6.5, 28.3, -math.pi / 2
        self.ki = KI_START
        self.keys = set()
        self.enemies, self.things = [], []
        for kind, x, y in self.map.things:
            if kind in KINDS:
                self.enemies.append(Enemy(kind, x, y, self.rng))
            else:
                self.things.append(Thing(kind, x, y))
        self._scatter_snacks()
        for t in self.things:
            if t.kind == "snack":
                t.snack = random_snack(self.rng)
        self.boss = next(e for e in self.enemies if e.boss)
        self.total = len(self.enemies)
        self.kills = 0
        self.shots, self.effects = [], []
        self.phase = "intro"
        self.t = 0
        self.end_t = 0
        self.result = None
        self.walk = 0.0
        self.moving = 0.0
        self.weapon = None           # None | "hado" | "shinku" | "punch" | "kick" | "shoryu" | "tatsu"
        self.wt = 0
        self.punch_side = 1
        self.spin_from = 0.0
        self.move_hit = set()
        self.flash = 0.0
        self.hurt = 0
        self.bonus = 0
        self.face_t = 0
        self.face_look = 0
        self.face_hurt = 0
        self.face_grin = 0
        self.msg, self.msg_t = "", 0
        self.banner, self.banner_t = "", 0
        self.flow = {}
        self.flow_cell = None
        self.boss_awake = False
        self.camz = 0.5
        self.ms = 0.0
        self._art()
        self._lit = {}
        self._sounds()

    # ---- assets --------------------------------------------------------
    def _art(self):
        # every fireball has a side view (the fx sheet's fly frames), a back view
        # (flying away: the flame trail streams toward the camera) and a front view
        self.hado_views = fx_ball_views("fly", 34, AKUMA_KI, 10, "fly_alt")
        self.shinku_views = fx_ball_views("var_large", 30, SHINKU_KI, 13, "var_regular")
        self.shinku_views["side"] = self.shinku_views["side"][:4]     # the lit frames, not the fade-out
        self.hado = self.hado_views["side"]
        # impacts: on a demon, on a wall, and the shinku's big blast
        self.hit_small = fx.fx_frames("hit_small", 64)
        self.hit_large = fx.fx_frames("hit_large", 72)
        self.hit_wall = fx.fx_frames("hit_wall", 56)
        self.hands = load_hands()
        self.fire_burst = _burst_frames((255, 230, 120), (255, 80, 20))
        self.ki_orb = pygame.transform.scale_by(self.hado_views["front"][0], 0.5)
        self.bigki = pygame.transform.scale_by(self.hado_views["front"][1], 0.8)
        self.cards = {"bluekey": _keycard((40, 90, 255)), "redkey": _keycard((230, 30, 30))}
        self.torch = _torch_frames()
        self.portal = _portal_frames()
        self.face = portrait("akuma")
        self.face_flip = pygame.transform.flip(self.face, True, False)
        rocket = [_tinted(f, (255, 140, 80), (60, 10, 0)) for f in (CharArt("ryu").projectile_frames() or self.hado)]
        fire_side = [_tinted(f, (255, 170, 120), (50, 0, 0)) for f in rocket]
        self.fire_views = {"side": fire_side, "back": [ball_view(FIRE_KI, "back", k, 9) for k in range(4)],
                           "front": [ball_view(FIRE_KI, "front", k, 8) for k in range(4)]}
        self.rocket_views = dict(self.fire_views, side=rocket)
        self.demon_art = {}
        for e in self.enemies:
            if e.art is None and e.kind not in self.demon_art:
                self.demon_art[e.kind] = demon_frames(e.kind)
        if "soul" in self.demon_art:
            # the lost soul burns: flames round every frame
            da = self.demon_art["soul"]
            self.soul_fire = {k: [[flame_aura(f, ph, 6, HOT_FLAME, pad=10) for ph in range(3)] for f in v]
                              for k, v in da.items() if k in ("walk", "attack", "pain")}
        self.fp = {}                 # first-person hand and foot sprites, built on first use
        self.bar_bg = self._bar_bg()

    def _scatter_snacks(self):
        """Japanese snacks at random spots all over the fortress (health)."""
        m = self.map
        taken = {(int(t.x), int(t.y)) for t in self.things} | {(int(e.x), int(e.y)) for e in self.enemies}
        cells = [(x, y) for y in range(MAP_H) for x in range(MAP_W)
                 if m.grid[y, x] == 0 and (x, y) not in taken and m.area_of(x, y) not in (None, "exit", "start")]
        for x, y in self.rng.sample(cells, min(EXTRA_SNACKS, len(cells))):
            t = Thing("snack", x, y)
            t.x += self.rng.uniform(-0.2, 0.2)
            t.y += self.rng.uniform(-0.2, 0.2)
            self.things.append(t)

    def _sounds(self):
        try:
            if getattr(audio, "_ok", False) and "doom_door" not in audio._sfx and hasattr(audio, "_build_doom"):
                audio._build_doom(audio._sfx)
        except Exception:
            pass

    @staticmethod
    def _play(name, fallback=None, vol=1.0):
        if name in getattr(audio, "_sfx", {}):
            audio.play(name, vol)
        elif fallback:
            audio.play(fallback, vol)

    BAR_PANELS = ((1, 35), (37, 99), (101, 147), (149, 181), (183, 245), (247, 318))
    TEN = ["...........", ".#########.", ".....#.....", ".....#.....", "###########", ".....#.....",
           "....#.#....", "...#...#...", "..#.....#..", ".#.......#.", "#.........#"]

    def _bar_bg(self):
        """The grey stone status bar with sunken panels (Doom style), and the
        heaven kanji on Akuma's back in the middle."""
        n = _fbm(np.random.default_rng(4), 64)
        tile = _surface(_col((112, 110, 104), 0.55 + 0.45 * n))
        s = pygame.Surface((W, BAR_H))
        for x in range(0, W, 64):
            s.blit(tile, (x, 0))
        pygame.draw.line(s, (170, 166, 158), (0, 0), (W, 0))
        pygame.draw.line(s, (60, 58, 54), (0, 1), (W, 1))
        for x0, x1 in self.BAR_PANELS:
            r = pygame.Rect(x0, 3, x1 - x0, BAR_H - 5)
            sub = s.subsurface(r)
            sub.fill((150, 150, 150), special_flags=pygame.BLEND_RGB_MULT)
            pygame.draw.line(s, (40, 38, 36), r.topleft, r.topright)
            pygame.draw.line(s, (40, 38, 36), r.topleft, r.bottomleft)
            pygame.draw.line(s, (176, 172, 164), (r.left, r.bottom), r.bottomright)
            pygame.draw.line(s, (176, 172, 164), (r.right, r.top), r.bottomright)
        # arms grid
        for i in range(6):
            cx, cy = 106 + (i % 3) * 13, 3 + (i // 3) * 9
            pygame.draw.rect(s, (54, 52, 48), (cx, cy, 11, 9))
            pygame.draw.line(s, (30, 28, 26), (cx, cy), (cx + 10, cy))
        # the kanji emblem
        e = pygame.Rect(152, 4, 27, 25)
        pygame.draw.ellipse(s, (16, 14, 14), e)
        pygame.draw.ellipse(s, (60, 56, 52), e, 1)
        for y, row in enumerate(self.TEN):
            for x, c in enumerate(row):
                if c == "#":
                    s.fill((196, 20, 16), (155 + x * 2, 6 + y * 2, 2, 2))
                    s.fill((90, 0, 0), (155 + x * 2 + 1, 6 + y * 2 + 1, 1, 1))
        return s

    @staticmethod
    def _big(text):
        """Doom status bar numbers: chunky red digits, lit from above."""
        img = text_surface(text, (255, 255, 255), 2).copy()
        w, h = img.get_size()
        g = pygame.Surface((w, h))
        for y in range(h):
            t = y / max(1, h - 1)
            g.fill((int(250 - 110 * t), int(60 - 50 * t), int(40 - 30 * t)), (0, y, w, 1))
        img.blit(g, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        out = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
        sh = text_surface(text, (30, 0, 0), 2)
        out.blit(sh, (2, 2))
        out.blit(sh, (1, 1))
        out.blit(img, (0, 0))
        return out

    # ---- interface -------------------------------------------------------
    @property
    def paused(self):
        return self.menu.open

    def say(self, text, frames=150):
        self.msg, self.msg_t = text, frames

    def update(self, inp):
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.phase == "play" and self.menu.toggle(inp):
            return
        self.t += 1
        for v in ("msg_t", "banner_t", "hurt", "bonus", "face_hurt", "face_grin"):
            if getattr(self, v) > 0:
                setattr(self, v, getattr(self, v) - 1)
        self.flash *= 0.8
        self._lights()
        self._doors()
        for ef in self.effects:
            ef.t += 1
        self.effects = [ef for ef in self.effects if ef.alive]
        if self.phase == "intro":
            self.end_t += 1
            if self.end_t == 20:
                self._play("doom_rip", "fight")
            if self.end_t >= INTRO:
                self.phase, self.end_t = "play", 0
            return
        if self.phase in ("won", "lost"):
            self.end_t += 1
            if self.phase == "lost":
                self.camz = max(0.12, self.camz - 0.012)
            self._shots()
            skip = self.end_t > 50 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= 170 or skip:
                if self.phase == "won":
                    self.result = "win"
                    self.game.level_done(self, max(1, int(self.hp)))
                else:
                    self.result = "lose"
                    self.game.level_failed(self)
            return
        self._move(inp)
        self._weapon(inp)
        self._shots()
        self._flowfield()
        for e in self.enemies:
            self._enemy(e)
        self._separate()
        self._pickups()
        self._triggers()
        if self.hp <= 0:
            self.hp = 0
            self.phase, self.end_t = "lost", 0
            self.weapon = None
            self._play("doom_death", "ko")
            self.say("AKUMA HAS FALLEN", 400)

    # ---- world upkeep ------------------------------------------------------
    def _lights(self):
        m = self.map
        t = self.t
        f = np.ones_like(m.light)
        if (m.flicker == 1).any():
            r = (np.sin(m.phase * 3.1 + t * 0.9) * np.sin(m.phase + t * 0.23)) > 0.3
            f = np.where(m.flicker == 1, np.where(r, 0.45, 1.0), f)
        f = np.where(m.flicker == 2, 0.8 + 0.25 * math.sin(t * 0.05), f)
        f = np.where(m.flicker == 3, 0.4 if (t // 20) % 3 == 0 else 1.0, f)
        self.light_now = (m.light * f).astype(np.float32)

    def _doors(self):
        for d in self.map.doors.values():
            if d.opening and d.open < 1:
                d.open = min(1.0, d.open + 1 / 24)
                self.map.door_open[d.y, d.x] = d.open

    def open_door(self, d, by_player=True):
        if d.opening:
            return True
        if d.key == "boss" and self.boss.alive:
            if by_player:
                self.say("THE SEAL HOLDS WHILE CYBER-GIEF LIVES")
                self._play("doom_locked", "block")
            return False
        if d.key in ("blue", "red") and d.key not in self.keys:
            if by_player:
                self.say("YOU NEED A %s KEY TO OPEN THIS DOOR" % d.key.upper())
                self._play("doom_locked", "block")
            return False
        d.opening = True
        self._play("doom_door", "land")
        return True

    def _flowfield(self):
        cell = (int(self.px), int(self.py))
        if cell == self.flow_cell and self.t % 30:
            return
        self.flow_cell = cell
        m = self.map
        dist = {cell: 0}
        q = [cell]
        for c in q:
            if dist[c] > 40:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + dx, c[1] + dy)
                if n in dist or not (0 <= n[0] < MAP_W and 0 <= n[1] < MAP_H):
                    continue
                g = m.grid[n[1], n[0]]
                if g == 0 or (g == DOOR and (m.doors[n].key is None or m.doors[n].open > 0.95)):
                    dist[n] = dist[c] + 1
                    q.append(n)
        self.flow = dist

    # ---- player ------------------------------------------------------------
    def _free(self, x, y, r=PLAYER_R, who=None):
        m = self.map
        for cx, cy in ((x - r, y - r), (x + r, y - r), (x - r, y + r), (x + r, y + r)):
            if m.solid(int(cx), int(cy)):
                return False
        return True

    def _blocked_by_enemy(self, x, y):
        for e in self.enemies:
            if e.alive and (e.x - x) ** 2 + (e.y - y) ** 2 < (e.radius + PLAYER_R) ** 2:
                if (e.x - x) ** 2 + (e.y - y) ** 2 < (e.x - self.px) ** 2 + (e.y - self.py) ** 2:
                    return True
        return False

    def _move(self, inp):
        strafe = inp.held("shield")
        turn = (inp.held("right") - inp.held("left"))
        fwd = (inp.held("up") - inp.held("down"))
        side = 0
        if strafe:
            side, turn = turn, 0
        spinning = self.weapon == "tatsu"
        if spinning:
            # the hurricane kick carries Akuma forward while the view whirls round
            turn, fwd, side = 0, max(fwd, 0) * 0.6 + 0.5, 0
        self.ang = (self.ang + turn * TURN_SPEED) % (2 * math.pi)
        head = self.spin_from if spinning else self.ang
        dx, dy = math.cos(head), math.sin(head)
        mx = dx * fwd * MOVE_SPEED - dy * side * STRAFE_SPEED
        my = dy * fwd * MOVE_SPEED + dx * side * STRAFE_SPEED
        if fwd and side:
            mx *= 0.75
            my *= 0.75
        moved = 0.0
        if mx and self._free(self.px + mx, self.py) and not self._blocked_by_enemy(self.px + mx, self.py):
            self.px += mx
            moved += abs(mx)
        if my and self._free(self.px, self.py + my) and not self._blocked_by_enemy(self.px, self.py + my):
            self.py += my
            moved += abs(my)
        self.walk += moved
        self.moving = min(1.0, self.moving + 0.1) if moved > 0.01 else max(0.0, self.moving - 0.08)
        self.camz = 0.5 + math.sin(self.walk * 6.0) * 0.022 * self.moving + self._jump()

    def _jump(self):
        """Camera height offset of the shoryuken's leap (and its crouch)."""
        if self.weapon != "shoryu":
            return 0.0
        t = self.wt
        if t < 4:
            return -0.06 * t / 4
        f = min(1.0, (t - 4) / 26)
        return -0.06 * (1 - f) + 0.26 * math.sin(math.pi * f)

    MOVE_LEN = {"hado": 20, "shinku": 40, "punch": 16, "kick": 22, "shoryu": 32, "tatsu": 40}

    def _start(self, move):
        self.weapon, self.wt = move, 0
        self.move_hit = set()
        if move == "punch":
            self.punch_side = -self.punch_side
            self._use()
            self._play("whiff")
        elif move == "kick":
            self._use()
            self._play("whiff")
        elif move == "shoryu":
            self._play("shoryu", "heavy")
            self.face_grin = 40
        elif move == "tatsu":
            self.spin_from = self.ang
            self._play("tatsu", "whiff")

    def _weapon(self, inp):
        P, K, S = inp.pressed("punch"), inp.pressed("kick"), inp.pressed("special")
        # special + punch / kick pressed together (within COMBO_WINDOW frames,
        # either order) turns the move that just started into the combo
        if self.weapon and self.wt < COMBO_WINDOW:
            if self.weapon == "hado" and (P or K):
                self.ki = min(KI_MAX, self.ki + HADO_COST)          # the fireball never left the hands
                self._start("shoryu" if P else "tatsu")
                return
            if self.weapon in ("punch", "kick") and S:
                self._start("shoryu" if self.weapon == "punch" else "tatsu")
                return
        if self.weapon:
            self.wt += 1
            w, t = self.weapon, self.wt
            if w == "hado" and t == 7:
                self._fire(False)
            elif w == "shinku" and t == 18:
                self._fire(True)
            elif w == "punch" and t == 4:
                self._melee(1.0, 0.75, PUNCH_DMG, 0.15, "heavy")
            elif w == "kick" and t == 6:
                self._melee(1.0, 0.6, KICK_DMG, 0.3, "heavy")
            elif w == "shoryu" and 4 <= t <= 12 and t % 4 == 0:
                self._melee(1.25, 0.55, SHORYU_DMG / 3, 0.25, "heavy", flame=True)
            elif w == "tatsu":
                f = min(1.0, max(0.0, (t - 4) / 32))
                f = f * f * (3 - 2 * f)
                self.ang = (self.spin_from + 2 * math.pi * f) % (2 * math.pi)
                if 6 <= t <= 34 and t % 3 == 0:
                    self._melee(1.4, -1.0, TATSU_DMG, 0.3, "heavy")
                if t >= self.MOVE_LEN["tatsu"] - 1:
                    self.ang = self.spin_from
            if t >= self.MOVE_LEN[w]:
                self.weapon = None
            else:
                return
        if S and (P or K):
            self._start("shoryu" if P else "tatsu")
        elif S and inp.held("shield"):
            if self.ki >= SHINKU_COST:
                self.ki -= SHINKU_COST
                self._start("shinku")
                self._play("doom_charge", "shoryu")
                self._alert_near(10)
            else:
                self.say("NOT ENOUGH KI FOR A SHINKU HADOUKEN", 90)
        elif S or (inp.held("special") and not inp.held("shield")):
            if self.ki >= HADO_COST:
                self.ki -= HADO_COST
                self._start("hado")
                self._alert_near(8)
            elif S:
                self.say("OUT OF KI! PUNCH AND KICK THEM", 90)
        elif P:
            self._start("punch")
        elif K:
            self._start("kick")

    def _fire(self, big):
        dx, dy = math.cos(self.ang), math.sin(self.ang)
        x, y = self.px + dx * 0.45, self.py + dy * 0.45
        if big:
            s = Shot(x, y, self.ang, HADO_SPEED * 0.85, "akuma", SHINKU_DMG * self.power,
                     SHINKU_SPLASH * self.power, 0.4, True, self.shinku_views, 0.016, (1.6, 0.4, 1.5), 0.45)
            self.flash = 1.6
            self.face_grin = 50
            self._play("doom_shinku", "hadouken")
        else:
            s = Shot(x, y, self.ang, HADO_SPEED, "akuma", HADO_DMG * self.power, HADO_SPLASH * self.power,
                     0.2, False, self.hado_views, 0.0085, (1.6, 0.45, 0.8), 0.42)
            self.flash = 1.0
            self._play("hadouken")
        self.shots.append(s)

    def _ahead(self, reach=1.3):
        """The first non-empty cell straight ahead within reach."""
        dx, dy = math.cos(self.ang), math.sin(self.ang)
        d = 0.1
        while d <= reach:
            cx, cy = int(self.px + dx * d), int(self.py + dy * d)
            if self.map.grid[cy, cx] != 0:
                return cx, cy
            d += 0.05
        return None

    def _use(self):
        c = self._ahead()
        if c is None:
            return
        m = self.map
        g = m.grid[c[1], c[0]]
        if g == DOOR:
            d = m.doors[c]
            if d.open < 1:
                self.open_door(d)
        elif c in m.secrets:
            m.grid[c[1], c[0]] = 0
            m.floor[c[1], c[0]] = F_STONE
            m.light[c[1], c[0]] = 0.8
            m.secrets.discard(c)
            self.r.fc = np.concatenate([m.ceil.ravel(), m.floor.ravel()]).astype(np.int32)
            self.say("A SECRET IS REVEALED!")
            self._play("doom_secret", "pickup")
        else:
            self._play("doom_oof", "block", 0.5)

    def _melee(self, reach, cone, dmg, push, sound, flame=False):
        """Hits every demon within reach whose direction is inside the cone
        (cos of the half angle; -1 = all round). Each move hits a demon once
        per swing, except the multi-hit shoryuken."""
        dx, dy = math.cos(self.ang), math.sin(self.ang)
        hit = False
        for e in self.enemies:
            if not e.alive or (e in self.move_hit and not flame):
                continue
            ex, ey = e.x - self.px, e.y - self.py
            d = math.hypot(ex, ey) or 1e-6
            if d < reach + e.radius and (ex * dx + ey * dy) > d * cone:
                self.move_hit.add(e)
                self._damage(e, dmg * self.power, (ex / d, ey / d))
                if not e.boss and self._free(e.x + ex / d * push, e.y + ey / d * push, min(e.radius, 0.3)):
                    e.x += ex / d * push
                    e.y += ey / d * push
                if flame:
                    self.effects.append(Effect(e.x, e.y, 0.5 + e.z, self.fire_burst, 0.02, 2))
                hit = True
        if hit:
            self._play(sound)

    def _alert_near(self, r):
        for e in self.enemies:
            if e.alive and not e.alert and (e.x - self.px) ** 2 + (e.y - self.py) ** 2 < r * r:
                if self.flow.get((int(e.x), int(e.y)), 99) < r * 1.5:
                    e.alert = True

    def hurt_player(self, dmg, src=None):
        if self.phase != "play":
            return
        self.hp -= dmg
        self.hurt = min(40, self.hurt + 12 + int(dmg))
        self.face_hurt = 30
        if src is not None:
            a = math.atan2(src[1] - self.py, src[0] - self.px) - self.ang
            a = (a + math.pi) % (2 * math.pi) - math.pi
            self.face_look = 0 if abs(a) < 0.5 else (1 if a > 0 else -1)
        self._play("doom_ouch", "hit")

    # ---- shots -----------------------------------------------------------------
    def _shots(self):
        for s in self.shots:
            if not s.alive:
                continue
            s.t += 1
            steps = 2
            for _ in range(steps):
                s.x += s.vx / steps
                s.y += s.vy / steps
                if self.map.solid(int(s.x), int(s.y)):
                    self._explode(s, None)
                    break
                if s.owner == "akuma":
                    for e in self.enemies:
                        if e.alive and e not in s.hit and \
                                (e.x - s.x) ** 2 + (e.y - s.y) ** 2 < (e.radius + s.radius) ** 2:
                            self._damage(e, s.dmg, (s.vx, s.vy))
                            s.hit.add(e)
                            if not s.big:
                                self._explode(s, e)
                                break
                            self.effects.append(Effect(s.x, s.y, 0.45, self.hit_small, 0.014, 2))
                    if not s.alive:
                        break
                elif (self.px - s.x) ** 2 + (self.py - s.y) ** 2 < (PLAYER_R + s.radius) ** 2:
                    self.hurt_player(s.dmg, (s.x - s.vx * 5, s.y - s.vy * 5))
                    self._explode(s, None)
                    break
            if s.t > 400:
                s.alive = False
        self.shots = [s for s in self.shots if s.alive]

    def _explode(self, s, direct):
        s.alive = False
        x, y = s.x - s.vx * 0.5, s.y - s.vy * 0.5
        if s.owner == "akuma":
            if s.big:
                frames, wpp = self.hit_large, 0.025
            elif direct is None:
                frames, wpp = self.hit_wall, 0.0125     # splashed on the wall
            else:
                frames, wpp = self.hit_small, 0.014
            self.effects.append(Effect(x, y, s.z, frames, wpp, 3))
            rad = 1.8 if s.big else 1.0
            for e in self.enemies:
                if e.alive and e is not direct and e not in s.hit and (e.x - x) ** 2 + (e.y - y) ** 2 < rad * rad:
                    self._damage(e, s.splash, (e.x - x, e.y - y))
            self._play("doom_boom", "hit", 0.6)
        else:
            self.effects.append(Effect(x, y, s.z, self.fire_burst, 0.025, 3))

    def _damage(self, e, dmg, push=(0, 0)):
        if not e.alive:
            return
        e.hp -= dmg
        e.flash = 4
        e.alert = True
        if e.hp <= 0:
            e.set("dying")
            self.kills += 1
            self.game.kills = getattr(self.game, "kills", 0) + 1
            if e.boss:
                self._play("doom_bossdie", "ko")
                self.banner, self.banner_t = "CYBER-GIEF IS SCRAP METAL", 240
                self.say("THE SEAL IS BROKEN. FIND THE PORTAL!", 300)
                for d in self.map.doors.values():
                    if d.key == "boss":
                        d.opening = True
                self._play("doom_door", "land")
            else:
                self._play("doom_die", "ko", 0.7)
                if self.rng.random() < 0.5:
                    t = Thing("ki", 0, 0)
                    t.x, t.y = e.x, e.y
                    self.things.append(t)
            return
        if e.state != "pain" and self.rng.random() < e.spec.get("pain", 0.5):
            e.set("pain")
            self._play("doom_pain", "hit", 0.6)

    # ---- enemies -----------------------------------------------------------------
    def _enemy(self, e):
        e.st += 1
        if e.flash:
            e.flash -= 1
        if e.state == "dying":
            e.z = max(0.0, e.z - 0.02)           # fliers drop out of the air
            if e.st > 40:
                e.set("dead")
            return
        if e.state == "dead":
            return
        dx, dy = self.px - e.x, self.py - e.y
        dist = math.hypot(dx, dy)
        if (self.t + e.look_t) % 8 == 0:
            e.see = dist < 16 and self.map.los(e.x, e.y, self.px, self.py)
            if e.see and not e.alert and (not e.boss or self.boss_awake):
                e.alert = True
                if e.boss:
                    self._play("doom_roar", "encounter")
                else:
                    self._play("doom_sight", "encounter", 0.5)
        if e.boss and not self.boss_awake:
            e.alert = False
        if not e.alert:
            return
        if e.state == "pain":
            if e.st > 14:
                e.set("chase")
            return
        if e.state == "attack":
            self._attack(e, dist)
            return
        if e.cool > 0:
            e.cool -= 1
        melee = e.spec.get("melee", 0)
        ranged = e.spec.get("ranged", 0)
        if melee and dist < 0.9 + e.radius and e.cool <= 30:
            e.set("attack")
            e.mode = "melee"
            return
        if ranged and e.see and e.cool <= 0 and dist < 13:
            e.set("attack")
            e.mode = "ranged"
            return
        # walk: straight at Akuma when in view, else down the flow field
        e.state = "chase"
        if e.see and dist < 5:
            tx, ty = self.px, self.py
        else:
            c = (int(e.x), int(e.y))
            best, bd = None, self.flow.get(c, 999)
            for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + ddx, c[1] + ddy)
                if self.flow.get(n, 999) < bd:
                    best, bd = n, self.flow[n]
            if best is None:
                return
            g = self.map.grid[best[1], best[0]]
            if g == DOOR:
                d = self.map.doors[best]
                if d.open < 0.95:
                    self.open_door(d, by_player=False)
            tx, ty = best[0] + 0.5, best[1] + 0.5
        if dist < e.radius + PLAYER_R + 0.05:
            return
        ax, ay = tx - e.x, ty - e.y
        al = math.hypot(ax, ay) or 1
        sp = e.speed
        mx, my = ax / al * sp, ay / al * sp
        r = min(e.radius, 0.3)
        if self._free(e.x + mx, e.y, r) and not self._near_player(e.x + mx, e.y, e):
            e.x += mx
        if self._free(e.x, e.y + my, r) and not self._near_player(e.x, e.y + my, e):
            e.y += my
        e.walked += sp

    def _near_player(self, x, y, e):
        return (x - self.px) ** 2 + (y - self.py) ** 2 < (e.radius + PLAYER_R) ** 2

    def _attack(self, e, dist):
        span = 30 if e.boss else 22
        if e.mode == "melee":
            if e.st == span * 2 // 3:
                if dist < 1.2 + e.radius:
                    self.hurt_player(e.spec["melee"], (e.x, e.y))
                    self._play("heavy")
                else:
                    self._play("whiff")
            if e.st >= span:
                e.set("chase")
                e.cool = 50
            return
        if e.st == span * 2 // 3:
            a = math.atan2(self.py - e.y, self.px - e.x)
            bullet = e.spec.get("shot") == "bullet"
            if e.boss:
                frames, angs = self.rocket_views, (a - 0.22, a, a + 0.22)
            else:
                frames, angs = self.fire_views, (a + self.rng.uniform(-0.05, 0.05),)
            wpp = 0.014 if e.boss else (0.004 if bullet else 0.0095)
            z = 0.75 if e.boss else (0.42 if bullet else 0.35 + e.z + (0.1 if e.kind == "caco" else 0.15))
            for an in angs:
                self.shots.append(Shot(e.x + math.cos(an) * (e.radius + 0.1), e.y + math.sin(an) * (e.radius + 0.1),
                                       an, ENEMY_SHOT_SPEED * (1.15 if e.boss else (2.2 if bullet else 1)), e,
                                       e.spec["ranged"], 0, 0.15 if bullet else 0.18, False, frames, wpp,
                                       (1.5, 0.6, 0.2), z))
            self._play("doom_imp", "fireball", 0.6) if not e.spec.get("shot") == "bullet" else self._play("doom_pistol", "hit", 0.5)
        if e.st >= span:
            e.set("chase")
            if e.boss:
                e.volley += 1
                e.cool = 25 if e.volley % 3 else 110
            else:
                e.cool = self.rng.randint(70, 150)

    def _separate(self):
        live = [e for e in self.enemies if e.alive and e.alert]
        for i, a in enumerate(live):
            for b in live[i + 1:]:
                dx, dy = b.x - a.x, b.y - a.y
                d2 = dx * dx + dy * dy
                rr = (min(a.radius, 0.3) + min(b.radius, 0.3)) ** 2
                if 1e-6 < d2 < rr:
                    d = math.sqrt(d2)
                    push = (math.sqrt(rr) - d) * 0.5
                    ux, uy = dx / d * push, dy / d * push
                    if self._free(b.x + ux, b.y + uy, 0.25):
                        b.x += ux
                        b.y += uy
                    if self._free(a.x - ux, a.y - uy, 0.25):
                        a.x -= ux
                        a.y -= uy

    # ---- pickups & triggers ----------------------------------------------------
    def _pickups(self):
        for t in self.things:
            if t.taken or t.kind in ("torch", "portal"):
                continue
            if (t.x - self.px) ** 2 + (t.y - self.py) ** 2 > 0.45 ** 2:
                continue
            if t.kind == "snack":
                if self.hp >= self.max_hp:
                    continue
                n = heal_amount(t.snack, self.max_hp)
                self.hp = min(self.max_hp, self.hp + n)
                self.say("%s +%d" % (t.snack, n), 90)
            elif t.kind in ("ki", "bigki"):
                if self.ki >= KI_MAX:
                    continue
                n = KI_ORB if t.kind == "ki" else BIG_KI_ORB
                self.ki = min(KI_MAX, self.ki + n)
                self.say("KI ORB +%d" % n if t.kind == "ki" else "BIG KI ORB +%d!" % n, 90)
            elif t.kind in ("bluekey", "redkey"):
                k = t.kind[:-3]
                self.keys.add(k)
                self.say("PICKED UP A %s KEYCARD." % k.upper())
                self._play("doom_key", "pickup")
            t.taken = True
            self.bonus = 10
            if t.kind not in ("bluekey", "redkey"):
                self._play("doom_item", "pickup")

    def _triggers(self):
        if not self.boss_awake and self.map.area_of(int(self.px), int(self.py)) == "arena":
            self.boss_awake = True
            self.boss.alert = True
            self.banner, self.banner_t = "CYBER-GIEF", 150
            self._play("doom_roar", "encounter")
        if not self.boss.alive:
            for t in self.things:
                if t.kind == "portal" and (t.x - self.px) ** 2 + (t.y - self.py) ** 2 < 0.6 ** 2:
                    self.phase, self.end_t = "won", 0
                    self.banner, self.banner_t = "HELL IS CONQUERED", 999
                    self._play("doom_portal", "encounter")

    # ---- drawing ------------------------------------------------------------------
    def draw(self, surf):
        lights = []
        for s in self.shots:
            if s.owner == "akuma":
                lights.append((s.x, s.y, 1.6 if s.big else 0.7, s.tint))
        for s in self.shots:
            if s.owner != "akuma":
                lights.append((s.x, s.y, 0.6, s.tint))
        if self.flash > 0.05:
            dx, dy = math.cos(self.ang), math.sin(self.ang)
            lights.insert(0, (self.px + dx * 0.6, self.py + dy * 0.6, self.flash * 0.9, (1.5, 0.5, 0.9)))
        lights.sort(key=lambda l: (l[0] - self.px) ** 2 + (l[1] - self.py) ** 2)
        import time
        c0 = time.perf_counter()
        view = self.r.render(self.px, self.py, self.ang, self.camz, self.light_now, lights, self.flash)
        surf.blit(view, (0, 0))
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, 0, W, VIEW_H))
        self._draw_sprites(surf)
        self.ms = (time.perf_counter() - c0) * 1000
        if self.phase != "lost":
            self._draw_hands(surf)
        if self.hurt:
            a = min(100, self.hurt * 4)
            surf.fill((a, 0, 0), (0, 0, W, VIEW_H), special_flags=pygame.BLEND_RGB_ADD)
            surf.fill((255, 255 - a, 255 - a), (0, 0, W, VIEW_H), special_flags=pygame.BLEND_RGB_MULT)
        if self.phase == "lost":
            surf.fill((255, 90, 90), (0, 0, W, VIEW_H), special_flags=pygame.BLEND_RGB_MULT)
        if self.bonus:
            a = self.bonus * 5
            surf.fill((a, a, a // 3), (0, 0, W, VIEW_H), special_flags=pygame.BLEND_RGB_ADD)
        if self.phase == "won":
            a = min(255, self.end_t * 3)
            surf.fill((a, a, a), (0, 0, W, VIEW_H), special_flags=pygame.BLEND_RGB_ADD)
        surf.set_clip(clip)
        self._draw_bar(surf)
        self._draw_text(surf)
        if self.menu.open:
            self.menu.draw(surf)

    def project(self, x, y):
        """(screen x, depth) of a world point, or None behind the camera."""
        dx, dy = math.cos(self.ang), math.sin(self.ang)
        plx, ply = -dy * PLANE, dx * PLANE
        inv = 1.0 / (plx * dy - dx * ply)
        sx, sy = x - self.px, y - self.py
        tx = inv * (dy * sx - dx * sy)
        tz = inv * (-ply * sx + plx * sy)
        if tz < 0.15:
            return None
        return (W / 2) * (1 + tx / tz), tz

    def _lit_img(self, key, img, level):
        ck = (key, level)
        s = self._lit.get(ck)
        if s is None:
            if level >= LIGHT_LEVELS:
                s = img
            else:
                v = int(255 * level / LIGHT_LEVELS)
                s = img.copy()
                s.fill((v, v, v, 255), special_flags=pygame.BLEND_RGBA_MULT)
            if len(self._lit) > 4000:
                self._lit.clear()
            self._lit[ck] = s
        return s

    def _demon_image(self, e):
        fr = self.demon_art[e.kind]
        st = e.state
        if st == "chase" and e.alert:
            pose, k = "walk", int(e.walked * 7) % 4
        elif st == "attack":
            pose, k = "attack", 0 if e.st < (22 * 2 // 3) else 1
        elif st == "pain":
            pose, k = "pain", 0
        elif st == "dying":
            pose, k = "die", min(3, e.st // 9)
        elif st == "dead":
            pose, k = "dead", 0
        else:
            pose, k = "walk", 0 if e.fly == 0 else (self.t // 12 + e.look_t) % 4
        img = fr[pose][k] if pose != "dead" else fr["dead"]
        pad = 0
        if e.kind == "soul" and pose in self.soul_fire:
            img = self.soul_fire[pose][k][(self.t // 4 + e.look_t) % 3]
            pad = 10
        flash = e.flash > 0
        ck = (e.kind, pose, k, pad and (self.t // 4 + e.look_t) % 3, flash)
        if flash:
            out = self._lit.get(ck)
            if out is None:
                out = img.copy()
                out.fill((120, 110, 100, 0), special_flags=pygame.BLEND_RGBA_ADD)
                self._lit[ck] = out
            img = out
        w, h = img.get_size()
        return ck, img, (w // 2, h - pad)

    def _enemy_image(self, e, flip):
        if e.art is None:
            return self._demon_image(e)
        art = e.art
        st = e.state
        clock = self.t
        if st == "idle" or (st == "chase" and not e.alert):
            key = art.resolve("idle", clock, clock)
        elif st == "chase":
            key = art.resolve("walk", int(e.walked * 300), int(e.walked * 300))
        elif st == "attack":
            span = 30 if e.boss else 22
            if e.mode == "melee":
                pose = "hammer_down" if e.boss else ("kick" if e.cid == "felicia" else "punch")
                prep = "hammer_up" if e.boss else pose + "_prep"
            else:
                pose, prep = ("punch", "punch_prep") if e.boss else ("hado_fire", "hado_prep")
            k = span * 2 // 3
            key = art.resolve(prep, e.st, span=k) if e.st < k else art.resolve(pose, e.st - k, span=span - k)
        elif st == "pain":
            key = art.resolve("hurt", e.st, span=14)
        elif st == "dying":
            key = art.resolve("launch", e.st, span=20) if e.st < 20 else art.resolve("down", e.st - 20, span=20)
        else:
            key = art.resolve("down", 999, span=1)
        flash = e.flash > 0
        ck = (e.cid, e.boss, key, flip, flash)
        img = self._lit.get(ck)
        if img is None:
            base, anc = art.entry(key, flip, flash)
            img = base if flash else _tinted(base, BOSS_MULT if e.boss else TINT_MULT, BOSS_ADD if e.boss else TINT_ADD)
            self._lit[ck] = img
        return ck, img, art.anchor(key, flip)

    def _sprites(self):
        """(depth, screen x, key, image, anchor, wpp, z, lit) for everything in view."""
        out = []
        for e in self.enemies:
            p = self.project(e.x, e.y)
            if p is None:
                continue
            flip = p[0] > W / 2
            ck, img, anc = self._enemy_image(e, flip)
            z = e.z + (0.03 * math.sin(self.t * 0.07 + e.look_t) if e.fly and e.alive else 0.0)
            out.append((p[1], p[0], ck, img, anc, e.wpp, z, e.flash == 0 and e.kind != "soul", e.x, e.y))
        for t in self.things:
            if t.taken:
                continue
            p = self.project(t.x, t.y)
            if p is None:
                continue
            bob = 0.04 * math.sin(self.t * 0.08 + t.x)
            if t.kind == "torch":
                k = (self.t // 6 + int(t.x * 3)) % len(self.torch)
                img, wpp, z, lit = self.torch[k], 0.022, 0.0, False
            elif t.kind == "portal":
                k = (self.t // 4) % len(self.portal)
                img, wpp, z, lit = self.portal[k], 0.028, 0.0, False
                if self.boss.alive:
                    img = self._lit_img(("portal", k), img, 3)
            elif t.kind == "snack":
                img, wpp, z, lit = snack_image(t.snack, 2), 0.011, 0.0, True
            elif t.kind == "ki":
                img, wpp, z, lit = self.ki_orb, 0.016, 0.12 + bob, False
            elif t.kind == "bigki":
                img, wpp, z, lit = self.bigki, 0.016, 0.15 + bob, False
            else:
                img, wpp, z, lit = self.cards[t.kind], 0.02, 0.08 + bob, True
            out.append((p[1], p[0], (t.kind, id(img)), img, (img.get_width() // 2, img.get_height()),
                        wpp, z, lit, t.x, t.y))
        for s in self.shots:
            p = self.project(s.x, s.y)
            if p is None or (s.owner == "akuma" and s.t < (6 if s.big else 3)):   # still in the hands
                continue
            # pick the view from the direction of flight relative to the camera:
            # flying away shows the back (trail toward us), coming at us the front
            rx, ry = s.x - self.px, s.y - self.py
            c = (s.vx * rx + s.vy * ry) / ((math.hypot(s.vx, s.vy) * math.hypot(rx, ry)) or 1)
            view = "back" if c > 0.72 else ("front" if c < -0.72 else "side")
            frames = s.frames[view]
            fr = frames[(s.t // 3) % len(frames)]
            if view == "side":
                lat = s.vx * -math.sin(self.ang) + s.vy * math.cos(self.ang)
                if lat < 0:
                    fr = pygame.transform.flip(fr, True, False)
            s.view = view
            h = fr.get_height()
            out.append((p[1], p[0], None, fr, (fr.get_width() // 2, h // 2), s.wpp, s.z, False, s.x, s.y))
        for ef in self.effects:
            p = self.project(ef.x, ef.y)
            if p is None:
                continue
            fr = ef.frames[min(len(ef.frames) - 1, ef.t // ef.speed)]
            out.append((p[1], p[0], None, fr, (fr.get_width() // 2, fr.get_height() // 2), ef.wpp, ef.z, False,
                        ef.x, ef.y))
        out.sort(key=lambda s: -s[0])
        return out

    def _draw_sprites(self, surf):
        zbuf = self.r.zbuf
        h = VIEW_H / 2
        self.drawn = []
        for depth, sx, key, img, anc, wpp, z, lit, wx, wy in self._sprites():
            k = PROJ / depth * wpp
            iw, ih = img.get_size()
            sw, sh = max(1, int(iw * k)), max(1, int(ih * k))
            if sw > W * 3 or sh > VIEW_H * 4:
                continue
            left = int(sx - anc[0] * k)
            footy = h + (self.camz - z) * PROJ / depth
            top = int(footy - anc[1] * k)
            x0, x1 = max(0, left), min(W, left + sw)
            if x0 >= x1 or top >= VIEW_H or top + sh <= 0:
                continue
            vis = depth < zbuf[x0:x1]
            if not vis.any():
                continue
            if lit and key is not None:
                cx, cy = min(MAP_W - 1, max(0, int(wx))), min(MAP_H - 1, max(0, int(wy)))
                lv = float(self.light_now[cy, cx]) * float(fog(depth)) + self.flash * 0.25
                level = max(1, min(LIGHT_LEVELS, int(round(lv * LIGHT_LEVELS))))
                img = self._lit_img(key, img, level)
            scaled = pygame.transform.scale(img, (sw, sh))
            self.drawn.append((key, x0, x1))
            # blit the runs of columns the walls don't cover
            edges = np.flatnonzero(np.diff(np.concatenate(([0], vis.view(np.int8), [0]))))
            for a, b in zip(edges[::2], edges[1::2]):
                ca, cb = x0 + a, x0 + b
                surf.blit(scaled, (ca, top), pygame.Rect(ca - left, 0, cb - ca, sh))

    # ---- first-person view -------------------------------------------------------------
    # Capsule-drawn poses the sheet has no drawing for (the kick's foot, the
    # shoryuken fist). name: (rig, rig args, scale, turn, wrist bend, flames)
    FP_POSES = {
        "fist": ("hand", dict(fist=1.0), 1.05, 0.0, 0.0, "ki"),
        "upper": ("hand", dict(fist=1.0), 1.15, -0.12, 0.0, "fire"),
        "leg_up": ("leg", {}, 1.25, 0.22, 0.0, "ki"),
        "leg_out": ("leg", {}, 1.05, 0.1, 0.0, "ki"),
        "leg_side": ("leg", {}, 0.6, 1.15, 0.0, "ki"),
    }
    IDLE_SEQ = (0, 1, 2, 3, 4, 3, 2, 1)       # the sheet's idle claws 0-4 drawn as a ping-pong loop
    SWIPE_SEQ = (0, 0, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5)   # punch tick -> swipe frame
    HAND_GAP = 60                             # idle claws: arm bases this far either side of centre

    def _fp_sprite(self, name, phase, left=False):
        """A first-person sprite with its flames, and where its wrist (or
        ankle) sits in it. Built once per pose and flame phase."""
        key = (name, phase, left)
        got = self.fp.get(key)
        if got is not None:
            return got
        base = self.fp.get((name, None, False))
        if base is None:
            rig, args, k, rot, bend, _fl = self.FP_POSES[name]
            parts = hand_parts(**args) if rig == "hand" else leg_parts()
            if bend:
                # bend the hand at the wrist, not the forearm
                parts = parts[:1] + rig_place(parts[1:], 0, 0, 1.0, bend)
            parts = rig_place(parts, 0, 0, k, rot)
            xs = [p[0] for p in parts] + [p[2] for p in parts]
            ys = [p[1] for p in parts] + [p[3] for p in parts]
            x0, y0 = int(min(xs)) - 18, int(min(ys)) - 18
            w, h = min(int(max(xs)) - x0 + 18, 420), min(int(max(ys)) - y0 + 18, 260)
            img = rig_render(rig_place(parts, -x0, -y0), w, h, rim=(255, 40, 20) if _fl == "ki" else (255, 140, 40))
            base = (img, (-x0, -y0))
            self.fp[(name, None, False)] = base
        img, (ax, ay) = base
        fl = self.FP_POSES[name][5]
        pad = 12
        out = flame_aura(img, phase, 9 if fl == "fire" else 7, HOT_FLAME if fl == "fire" else KI_FLAME,
                         fade_y=ay + 26, pad=pad)
        ax, ay = ax + pad, ay + pad
        if left:
            out = pygame.transform.flip(out, True, False)
            ax = out.get_width() - ax
        got = (out, (ax, ay))
        self.fp[key] = got
        return got

    def _put(self, surf, name, x, y, left=False):
        img, (ax, ay) = self._fp_sprite(name, (self.t // 5) % 4, left)
        surf.blit(img, (int(x - ax), int(y - ay)))

    ONE_HAND_ROWS = ("idle_a", "idle_b", "idle_c", "swipe")

    def _hand(self, surf, row, i, x, y, left=False):
        """Frame i of a hand-sheet row with its arm's base at (x, y). The
        single-hand rows are drawn as a left hand (thumb on the right), so the
        right hand is the mirrored one."""
        key = ("sheet", row, i, left)
        got = self.fp.get(key)
        if got is None:
            img, (ax, ay) = self.hands[row][i]
            if row in self.ONE_HAND_ROWS and not left:
                img = pygame.transform.flip(img, True, False)
                ax = img.get_width() - ax
            got = self.fp[key] = (img, (ax, ay))
        img, (ax, ay) = got
        surf.blit(img, (int(x - ax), int(y - ay)))

    def _idle(self, surf, x, y, left=False):
        """An idle claw (the sheet's loop; every third beat the other claw)."""
        row = "idle_b" if (self.t // 50) % 3 == 2 else "idle_a"
        k = self.IDLE_SEQ[(self.t // 7 + (3 if left else 0)) % len(self.IDLE_SEQ)]
        self._hand(surf, row, k, x, y, left)

    def _draw_hands(self, surf):
        bobx = math.sin(self.walk * 3.0) * 5 * self.moving
        boby = abs(math.cos(self.walk * 3.0)) * 4 * self.moving
        cx, by = W // 2 + bobx, VIEW_H - 12 + boby
        base = VIEW_H + 2 + boby                       # the sheet's arms are cut at the screen's bottom edge
        w, t = self.weapon, self.wt

        def pair(gap, y):
            self._idle(surf, cx - gap, y, left=True)
            self._idle(surf, cx + gap, y)

        def lerp(a, b, f):
            return a + (b - a) * max(0.0, min(1.0, f))

        if w in ("hado", "shinku"):
            fire = 7 if w == "hado" else 18
            big = w == "shinku"
            rel = 6 if not big else 14                    # ticks the release row takes
            if t < fire:                                   # hands come together, the ki gathers
                n = 6 if not big else 5
                k = min(5, t * n // fire) if not big or t < 12 else 4 + (t // 2) % 2
                self._hand(surf, "charge", k, cx, base)
                if big and t >= 6:                         # the shinku's ball keeps swelling
                    key = ("glow", t, (t // 2) % 2)
                    g = self.fp.get(key)
                    if g is None:          # additive, so premultiply: transparent pixels add nothing
                        g = self.fp[key] = fx.fx_frames("explode_small", 20 + (t - 6) * 3)[1 + (t // 2) % 2].premul_alpha()
                    surf.blit(g, (int(cx - g.get_width() / 2), int(base - 66 - g.get_height() / 2)),
                              special_flags=pygame.BLEND_RGB_ADD)
            elif t < fire + rel:                           # palms out, the ball leaves
                k = min(7, (t - fire) * 8 // rel)
                self._hand(surf, "release", k, cx, base)
            else:                                          # back to the guard
                f = (t - fire - rel) / max(1, self.MOVE_LEN[w] - fire - rel)
                pair(lerp(22, self.HAND_GAP, f), base + lerp(14, 0, f))
        elif w == "punch":
            s = self.punch_side
            self._idle(surf, cx - s * (self.HAND_GAP + 14), base + 12, left=s > 0)
            k = self.SWIPE_SEQ[min(t, len(self.SWIPE_SEQ) - 1)]
            self._hand(surf, "swipe", k, cx + s * 18, base, left=s < 0)
        elif w == "shoryu":
            self._idle(surf, cx - 64, base + 22, left=True)
            if t < 4:
                self._put(surf, "fist", cx + 34, by + 18)
            else:
                f = min(1.0, (t - 4) / 12)
                y = lerp(by + 10, by - 70, f) + max(0, t - 20) * 7
                self._put(surf, "upper", lerp(cx + 30, cx + 8, f), y)
        elif w == "kick":
            pair(self.HAND_GAP + 22, base + 22)
            if t < 4:
                self._put(surf, "leg_up", cx + 30, VIEW_H + 40 - t * 8)
            elif t < 13:
                f = min(1.0, (t - 4) / 3)
                self._put(surf, "leg_out", lerp(cx + 26, cx + 12, f), lerp(VIEW_H + 8, VIEW_H - 46, f))
            else:
                f = (t - 13) / 9
                self._put(surf, "leg_up", lerp(cx + 14, cx + 34, f), lerp(VIEW_H - 30, VIEW_H + 70, f))
        elif w == "tatsu":
            pair(self.HAND_GAP + 28, base + 28)
            if 3 <= t < 37:
                # the leg sticks straight out while the world whirls past; streaks
                for k in range(5):
                    yy = 58 + k * 9
                    pygame.draw.line(surf, (255, 255, 255) if k % 2 else (255, 120, 160),
                                     (int(cx - 140 + (t * 23 + k * 40) % 120), yy),
                                     (int(cx - 90 + (t * 23 + k * 40) % 120), yy))
                self._put(surf, "leg_side", W - 58, 90)
        else:
            pair(self.HAND_GAP, base)

    # ---- status bar ------------------------------------------------------------------
    def _draw_bar(self, surf):
        y0 = VIEW_H
        surf.blit(self.bar_bg, (0, y0))
        grey = (200, 196, 188)
        pct = max(0, int(round(100 * self.hp / self.max_hp)))
        for text, cx in (("%d%%" % pct, 68), ("%d%%" % int(self.ki), 214)):
            img = self._big(text)
            surf.blit(img, (cx - img.get_width() // 2, y0 + 4))
        draw_text(surf, "HEALTH", 68, y0 + 21, grey, align="center")
        draw_text(surf, "KI", 214, y0 + 21, grey, align="center")
        # ARMS: 2 hadouken, 3 shoryuken, 4 tatsumaki, 5 shinku (lit when there is the ki), 6/7 the keys
        ready = self.ki >= SHINKU_COST
        lit = {2: self.ki >= HADO_COST, 3: True, 4: True, 5: ready}
        for i in range(6):
            n = i + 2
            x, y = 106 + (i % 3) * 13 + 3, y0 + 4 + (i // 3) * 9
            if n in (6, 7):
                k = "blue" if n == 6 else "red"
                col = ((70, 120, 255) if k == "blue" else (240, 50, 40)) if k in self.keys else (96, 90, 84)
            else:
                col = (255, 214, 60) if lit[n] else (96, 90, 84)
                if n == 5 and ready and (self.t // 15) % 2:
                    col = (255, 250, 190)
            draw_text(surf, str(n), x, y, col, shadow=(20, 16, 12))
        draw_text(surf, "ARMS", 124, y0 + 23, grey, align="center")
        # the ammo panel: what the ki buys, kills, keys
        yel, lab = (236, 200, 60), (190, 186, 178)
        rows = (("HADO", "%d/%d" % (self.ki // HADO_COST, KI_MAX // HADO_COST)),
                ("SHNK", "%d/%d" % (self.ki // SHINKU_COST, KI_MAX // SHINKU_COST)),
                ("KILL", "%d/%d" % (self.kills, self.total)))
        for i, (a, b) in enumerate(rows):
            draw_text(surf, a, 250, y0 + 5 + i * 8, lab, shadow=(30, 28, 26))
            draw_text(surf, b, 316, y0 + 5 + i * 8, yel, shadow=(30, 28, 26), align="right")
        self._draw_face(surf, 3, y0 + 2)

    def _draw_face(self, surf, x, y):
        self.face_t += 1
        if self.face_t % 70 == 0 and not self.face_hurt:
            self.face_look = self.rng.choice((-1, 0, 0, 1))
        img = self.face_flip if self.face_look < 0 else self.face
        ox = self.face_look if self.face_look else 0
        r = pygame.Rect(x, y, 30, 30)
        pygame.draw.rect(surf, (10, 6, 6), r.inflate(2, 2))
        clip = surf.get_clip()
        surf.set_clip(r)
        hp = self.hp / self.max_hp
        if self.phase == "lost":
            f = _tinted(img, (120, 60, 60), (0, 0, 0))
            surf.blit(pygame.transform.scale(f, (30, 22)), (x, y + 8))
        elif self.face_hurt:
            # grimace: squashed, shaking, flushed red
            f = _tinted(img, (255, 150, 150), (70, 0, 0))
            sq = pygame.transform.scale(f, (32, 27))
            surf.blit(sq, (x - 1 + self.rng.choice((-1, 0, 1)), y + 3))
        else:
            surf.blit(img, (x + ox, y))
            if self.face_grin:
                surf.fill((50, 30, 60), r, special_flags=pygame.BLEND_RGB_ADD)
        if hp < 0.6 and self.phase != "lost":
            # bloodier the lower Akuma's health
            n = int((0.6 - hp) * 30)
            rr = random.Random(7)
            for _ in range(n):
                surf.fill((150, 0, 0), (x + rr.randint(3, 26), y + rr.randint(8, 28), 2, 1))
        surf.set_clip(clip)

    def _draw_text(self, surf):
        if self.msg_t:
            draw_text(surf, self.msg, 3, 3, (255, 60, 50))
        if self.boss_awake and self.boss.alive:
            draw_text(surf, "CYBER-GIEF", W // 2, 12, (255, 200, 200), align="center")
            w = 120
            pygame.draw.rect(surf, (0, 0, 0), (W // 2 - w // 2 - 1, 21, w + 2, 5))
            pygame.draw.rect(surf, (200, 20, 20), (W // 2 - w // 2, 22, int(w * self.boss.hp / self.boss.max_hp), 3))
        if self.phase == "intro":
            shake = self.rng.choice((-1, 0, 1)) if self.end_t < 60 else 0
            draw_text(surf, "RIP AND TEAR", W // 2 + shake, 34, (230, 20, 10), scale=3, align="center")
            draw_text(surf, "LEVEL %d: %s" % (self.level, LEVEL_NAME), W // 2, 66, (255, 220, 160), align="center")
            draw_text(surf, "FIND THE KEYS. KILL CYBER-GIEF. ESCAPE.", W // 2, 80, (220, 210, 230), align="center")
        elif self.banner_t:
            draw_text(surf, self.banner, W // 2, 44, (255, 60, 40) if self.phase != "won" else (255, 230, 120),
                      scale=2, align="center")
            if self.phase == "won" and self.end_t > 40:
                draw_text(surf, "AKUMA LEAVES HELL STRONGER THAN EVER", W // 2, 70, (90, 30, 20), align="center")
        if self.phase == "lost":
            draw_text(surf, "AKUMA HAS FALLEN", W // 2, 60, (255, 60, 40), scale=2, align="center")
