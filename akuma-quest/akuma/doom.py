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
billboard sprites (fighters from the sprite pack, fireballs, pickups) hide
behind walls.

The map is a hand-laid hell fortress: a tech-base start room, a demon hall,
a blue key room, a red key cavern (with a secret wall), and a sky-lit arena
where CYBER-GIEF waits in front of the sealed exit portal.
"""

import math
import random

import numpy as np
import pygame

from . import audio
from .akuma_sprites import CharArt, portrait
from .config import W, H
from .font import draw_text
from .pause import PauseMenu

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
HADO_COST, SHINKU_COST = 1, 8
HADO_DMG, HADO_SPLASH = 25, 10
SHINKU_DMG, SHINKU_SPLASH = 90, 45
KICK_DMG = 30
KI_START, KI_MAX = 30, 99
HADO_SPEED = 0.17
ENEMY_SHOT_SPEED = 0.075
ONIGIRI_HEAL = 40
CONTROLS = [
    "UP / DOWN: WALK FORWARD / BACK",
    "LEFT / RIGHT: TURN",
    "HOLD I (SHIELD) + LEFT / RIGHT: STRAFE",
    "J: HADOUKEN (1 KI), HOLD TO KEEP FIRING",
    "L: SHINKU HADOUKEN (8 KI), PIERCES",
    "K: KICK, OPEN DOORS, PUSH SECRET WALLS",
    "BLUE AND RED DOORS NEED THEIR KEY",
    "ONIGIRI HEAL. BLUE KI ORBS REFILL KI",
    "KILL CYBER-GIEF, THEN TAKE THE PORTAL",
]

# ---- textures ------------------------------------------------------------
(T_HELL, T_FACE, T_TECH, T_COMP, T_FLESH, T_DOOR, T_DOOR_B, T_DOOR_R, T_BOSSDOOR, T_JAMB,
 T_SECRET, F_STONE, F_METAL, F_LAVA, C_STONE, C_LIGHT, F_EXIT, C_FLESH) = range(1, 19)
N_TEX = 19
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


def _col(base, mult):
    return np.clip(np.array(base, np.float32)[None, None, :] * mult[..., None], 0, 255)


def _tex_hell(rng, glow=True):
    X, Y = np.meshgrid(np.arange(TS), np.arange(TS), indexing="ij")
    n = _fbm(rng)
    row = Y // 16
    off = np.where(row % 2 == 1, 16, 0)
    bx = (X + off) % 32
    by = Y % 16
    mortar = (bx < 2) | (by < 2)
    brick_id = ((X + off) // 32) % 2 + row * 2
    tint = np.array([rng.uniform(0.75, 1.15) for _ in range(16)])[brick_id % 16]
    img = _col((110, 48, 34), (0.55 + 0.6 * n) * tint)
    img[mortar] = _col((30, 12, 10), 0.7 + 0.5 * n)[mortar]
    if glow:
        # lava glowing through a few cracks
        cr = np.abs(_smooth(rng, 6) - 0.5) < 0.018
        cr &= _smooth(rng, 4) > 0.55
        img[cr] = np.array((255, 120, 30))
    return img


def _tex_from_surface(s):
    return pygame.surfarray.array3d(s).astype(np.float32)


def _surface(img):
    return pygame.surfarray.make_surface(np.clip(img, 0, 255).astype(np.uint8))


def _tex_face(rng):
    s = _surface(_tex_hell(rng, glow=False))
    pygame.draw.rect(s, (40, 16, 12), (6, 4, 52, 56))
    pygame.draw.rect(s, (70, 30, 22), (8, 6, 48, 52))
    pygame.draw.rect(s, (20, 8, 6), (8, 6, 48, 52), 1)
    bone, dark = (176, 150, 116), (96, 74, 56)
    pygame.draw.polygon(s, bone, [(16, 22), (8, 8), (20, 18)])      # horns
    pygame.draw.polygon(s, bone, [(48, 22), (56, 8), (44, 18)])
    pygame.draw.ellipse(s, bone, (16, 14, 32, 34))
    pygame.draw.ellipse(s, dark, (16, 14, 32, 34), 1)
    pygame.draw.rect(s, bone, (22, 40, 20, 12))
    pygame.draw.ellipse(s, (10, 0, 0), (20, 24, 10, 9))             # eyes
    pygame.draw.ellipse(s, (10, 0, 0), (34, 24, 10, 9))
    pygame.draw.rect(s, (255, 40, 20), (24, 27, 3, 3))
    pygame.draw.rect(s, (255, 40, 20), (38, 27, 3, 3))
    pygame.draw.polygon(s, (20, 4, 2), [(32, 33), (29, 39), (35, 39)])
    for k in range(5):
        pygame.draw.rect(s, (230, 220, 190), (23 + k * 4, 44, 3, 6))
        pygame.draw.line(s, dark, (23 + k * 4, 44), (23 + k * 4, 49))
    pygame.draw.polygon(s, (240, 230, 200), [(25, 44), (27, 52), (29, 44)])   # fangs
    pygame.draw.polygon(s, (240, 230, 200), [(35, 44), (37, 52), (39, 44)])
    return _tex_from_surface(s)


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


def _tex_floor(rng, kind):
    X, Y = np.meshgrid(np.arange(TS), np.arange(TS), indexing="ij")
    n = _fbm(rng)
    if kind == "stone":
        img = _col((88, 70, 62), 0.6 + 0.5 * n)
        grout = (X % 32 < 1) | (Y % 32 < 1)
        img[grout] = _col((30, 24, 22), 1 + 0 * n)[grout]
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
        img = _col((60, 48, 44), 0.6 + 0.5 * n)
        grout = (X % 16 < 1) | (Y % 16 < 1)
        img[grout] = _col((24, 18, 16), 1 + 0 * n)[grout]
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


def _sky(rng, w=256, h=84):
    X, Y = np.meshgrid(np.arange(w), np.arange(h), indexing="ij")
    t = Y / (h - 1)
    img = np.zeros((w, h, 3), np.float32)
    img[..., 0] = 40 + 200 * t ** 1.5
    img[..., 1] = 6 + 70 * t ** 3
    img[..., 2] = 14 + 10 * t
    cl = _smooth(rng, 8, w)[:, :h]
    img *= (0.7 + 0.5 * cl)[..., None]
    # jagged mountains
    ridge = np.zeros(w)
    for f, a in ((1, 12), (3, 6), (9, 3)):
        ph = rng.uniform(0, 6.28)
        ridge += a * np.abs(np.sin(np.arange(w) * f * 2 * math.pi / w + ph))
    ridge = h - 6 - ridge
    m = Y > ridge[:, None]
    img[m] = np.array((28, 6, 8))
    return np.clip(img, 0, 255)


def build_textures(seed=13):
    rng = np.random.default_rng(seed)
    prng = random.Random(seed)
    T = np.zeros((N_TEX, TS, TS, 3), np.float32)
    T[T_HELL] = _tex_hell(rng)
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
        R("hall", 2, 8, 17, 15, T_HELL, F_STONE, C_STONE, 0.75, faces=0.22)
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
        R("arena", 30, 3, 38, 26, T_FLESH, F_LAVA, SKY, 0.85, faces=0.2)
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
        th = self.things
        th += [("ki", 4, 26), ("onigiri", 9, 26), ("ki", 9, 29), ("torch", 4, 29), ("torch", 9, 25)]
        th += [("ryu", 7, 18), ("ki", 5, 20)]
        th += [("zangief", 4, 10), ("felicia", 15, 14), ("ryu", 13, 9), ("hsienko", 3, 14),
               ("onigiri", 16, 9), ("ki", 2, 15), ("torch", 2, 8), ("torch", 17, 8),
               ("torch", 2, 15), ("torch", 17, 15)]
        th += [("ken", 24, 10), ("felicia", 21, 15), ("morrigan", 25, 13), ("bluekey", 25, 15),
               ("ki", 20, 10), ("onigiri", 26, 9)]
        th += [("zangief", 12, 3), ("hsienko", 5, 2), ("ryu", 14, 5), ("morrigan", 8, 4),
               ("redkey", 15, 2), ("onigiri", 4, 5), ("ki", 10, 6), ("torch", 3, 1), ("torch", 16, 6)]
        th += [("bigki", 1, 2), ("onigiri", 1, 3), ("onigiri", 1, 4)]
        th += [("boss", 34, 6), ("ken", 31, 4), ("hsienko", 37, 4),
               ("onigiri", 31, 25), ("onigiri", 37, 25), ("bigki", 31, 12), ("bigki", 37, 20),
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


def _glow_ball(r, core, edge):
    s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
    for k in range(r, 0, -1):
        t = k / r
        c = [int(core[i] * (1 - t) + edge[i] * t) for i in range(3)]
        pygame.draw.circle(s, c + [int(255 * (1 - t * t * 0.7))], (r + 1, r + 1), k)
    return s


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


def _onigiri():
    s = pygame.Surface((16, 15), pygame.SRCALPHA)
    pygame.draw.polygon(s, (30, 30, 30), [(8, 0), (15, 13), (1, 13)])
    pygame.draw.polygon(s, (250, 250, 245), [(8, 1), (14, 12), (2, 12)])
    pygame.draw.rect(s, (16, 40, 24), (5, 8, 6, 6))
    pygame.draw.line(s, (255, 255, 255), (7, 3), (5, 6))
    return s


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


# ---- actors ----------------------------------------------------------------
KINDS = {
    "ryu": dict(cid="ryu", hp=45, speed=0.024, ranged=12, pain=0.7, name="IMP RYU"),
    "ken": dict(cid="ken", hp=45, speed=0.027, ranged=12, pain=0.7, name="IMP KEN"),
    "hsienko": dict(cid="hsienko", hp=60, speed=0.02, ranged=14, pain=0.5, name="HSIEN-KO"),
    "morrigan": dict(cid="morrigan", hp=55, speed=0.032, ranged=12, pain=0.6, name="MORRIGAN"),
    "zangief": dict(cid="zangief", hp=110, speed=0.021, melee=20, pain=0.35, name="ZANGIEF"),
    "felicia": dict(cid="felicia", hp=45, speed=0.045, melee=10, pain=0.8, name="FELICIA"),
    "boss": dict(cid="zangief", hp=900, speed=0.022, melee=28, ranged=14, pain=0.0, boss=True,
                 wpp=0.02, radius=0.6, name="CYBER-GIEF"),
}
WPP = 0.0125                  # world units per sprite pixel for fighters


class Enemy:
    def __init__(self, kind, x, y, rng):
        spec = KINDS[kind]
        self.kind = kind
        self.spec = spec
        self.cid = spec["cid"]
        self.art = CharArt(self.cid)
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
        self.weapon = None           # None | "hado" | "shinku" | "kick"
        self.wt = 0
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
        akuma = CharArt("akuma")
        balls = akuma.projectile_frames()
        self.hado = [balls[i] for i in range(1, len(balls), 2)] or balls
        self.shinku = [_tinted(pygame.transform.scale_by(b, 1.0), (255, 200, 255), (60, 0, 60)) for b in self.hado]
        self.hado_burst = _burst_frames((230, 240, 255), (90, 120, 255))
        self.fire_burst = _burst_frames((255, 230, 120), (255, 80, 20))
        self.onigiri = _onigiri()
        self.ki_orb = pygame.transform.scale_by(self.hado[0], 0.45)
        self.bigki = pygame.transform.scale_by(self.hado[1 % len(self.hado)], 0.8)
        self.cards = {"bluekey": _keycard((40, 90, 255)), "redkey": _keycard((230, 30, 30))}
        self.torch = _torch_frames()
        self.portal = _portal_frames()
        self.face = portrait("akuma")
        self.face_flip = pygame.transform.flip(self.face, True, False)
        rocket = CharArt("ryu").projectile_frames() or self.hado
        self.rocket = [_tinted(f, (255, 140, 80), (60, 10, 0)) for f in rocket]
        self.proj = {}
        for e in self.enemies:
            if e.cid not in self.proj:
                fr = CharArt(e.cid).projectile_frames() or rocket
                self.proj[e.cid] = [_tinted(f, (255, 170, 120), (50, 0, 0)) for f in fr]
        self.bar_bg = self._bar_bg()

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

    def _bar_bg(self):
        n = _fbm(np.random.default_rng(4), 64)
        tile = _surface(_col((96, 92, 88), 0.6 + 0.4 * n))
        s = pygame.Surface((W, BAR_H))
        for x in range(0, W, 64):
            s.blit(tile, (x, 0))
        pygame.draw.line(s, (150, 146, 140), (0, 0), (W, 0))
        for x0, x1 in ((1, 54), (56, 118), (202, 254), (256, 278), (280, 318)):
            pygame.draw.rect(s, (40, 38, 36), (x0, 3, x1 - x0, BAR_H - 6))
            pygame.draw.line(s, (150, 146, 140), (x0, BAR_H - 3), (x1, BAR_H - 3))
            pygame.draw.line(s, (150, 146, 140), (x1, 3), (x1, BAR_H - 3))
        pygame.draw.rect(s, (24, 22, 20), (143, 0, 34, BAR_H))
        return s

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
        for fx in self.effects:
            fx.t += 1
        self.effects = [fx for fx in self.effects if fx.alive]
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
        self.ang = (self.ang + turn * TURN_SPEED) % (2 * math.pi)
        dx, dy = math.cos(self.ang), math.sin(self.ang)
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
        self.camz = 0.5 + math.sin(self.walk * 6.0) * 0.022 * self.moving

    def _weapon(self, inp):
        if self.weapon:
            self.wt += 1
            if self.weapon == "hado" and self.wt == 7:
                self._fire(False)
            elif self.weapon == "shinku" and self.wt == 18:
                self._fire(True)
            elif self.weapon == "kick" and self.wt == 6:
                self._kick()
            done = {"hado": 20, "shinku": 40, "kick": 22}[self.weapon]
            if self.wt >= done:
                self.weapon = None
            else:
                return
        if inp.pressed("kick"):
            self.weapon, self.wt = "kick", 0
            self._use()
            self._play("whiff")
        elif inp.pressed("special") or (inp.held("special") and self.t % 2 == 0 and False):
            if self.ki >= SHINKU_COST:
                self.ki -= SHINKU_COST
                self.weapon, self.wt = "shinku", 0
                self._play("doom_charge", "shoryu")
                self._alert_near(10)
            else:
                self.say("NOT ENOUGH KI FOR A SHINKU HADOUKEN", 90)
        elif inp.pressed("punch") or inp.held("punch"):
            if self.ki >= HADO_COST:
                self.ki -= HADO_COST
                self.weapon, self.wt = "hado", 0
                self._alert_near(8)
            elif inp.pressed("punch"):
                self.say("OUT OF KI! KICK THEM (K)", 90)

    def _fire(self, big):
        dx, dy = math.cos(self.ang), math.sin(self.ang)
        x, y = self.px + dx * 0.45, self.py + dy * 0.45
        if big:
            s = Shot(x, y, self.ang, HADO_SPEED * 0.85, "akuma", SHINKU_DMG * self.power,
                     SHINKU_SPLASH * self.power, 0.4, True, self.shinku, 0.018, (1.2, 0.6, 1.8), 0.45)
            self.flash = 1.6
            self.face_grin = 50
            self._play("doom_shinku", "hadouken")
        else:
            s = Shot(x, y, self.ang, HADO_SPEED, "akuma", HADO_DMG * self.power, HADO_SPLASH * self.power,
                     0.2, False, self.hado, 0.008, (0.5, 0.7, 1.5), 0.42)
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

    def _kick(self):
        dx, dy = math.cos(self.ang), math.sin(self.ang)
        for e in self.enemies:
            if not e.alive:
                continue
            ex, ey = e.x - self.px, e.y - self.py
            d = math.hypot(ex, ey)
            if d < 1.0 + e.radius and (ex * dx + ey * dy) > d * 0.6:
                self._damage(e, KICK_DMG * self.power, (dx, dy))
                if not e.boss and self._free(e.x + dx * 0.3, e.y + dy * 0.3, e.radius):
                    e.x += dx * 0.3
                    e.y += dy * 0.3
                self._play("heavy")

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
                            self.effects.append(Effect(s.x, s.y, 0.45, self.hado_burst, 0.03, 2))
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
            self.effects.append(Effect(x, y, s.z, self.hado_burst, 0.05 if s.big else 0.03, 3))
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
            if e.boss:
                frames, angs = self.rocket, (a - 0.22, a, a + 0.22)
            else:
                frames, angs = self.proj.get(e.cid) or self.rocket, (a + self.rng.uniform(-0.05, 0.05),)
            for an in angs:
                self.shots.append(Shot(e.x + math.cos(an) * (e.radius + 0.1), e.y + math.sin(an) * (e.radius + 0.1),
                                       an, ENEMY_SHOT_SPEED * (1.15 if e.boss else 1), e, e.spec["ranged"], 0,
                                       0.18, False, frames, 0.014 if e.boss else 0.011, (1.5, 0.6, 0.2),
                                       0.75 if e.boss else 0.5))
            self._play("doom_imp", "fireball", 0.6)
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
            if t.kind == "onigiri":
                if self.hp >= self.max_hp:
                    continue
                self.hp = min(self.max_hp, self.hp + ONIGIRI_HEAL)
                self.say("PICKED UP AN ONIGIRI.")
            elif t.kind in ("ki", "bigki"):
                if self.ki >= KI_MAX:
                    continue
                n = 6 if t.kind == "ki" else 25
                self.ki = min(KI_MAX, self.ki + n)
                self.say("PICKED UP A KI ORB." if n == 6 else "PICKED UP A BIG KI ORB!")
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
            lights.insert(0, (self.px + dx * 0.6, self.py + dy * 0.6, self.flash * 0.9, (0.6, 0.8, 1.4)))
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

    def _enemy_image(self, e, flip):
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
            out.append((p[1], p[0], ck, img, anc, e.wpp, 0.0, e.flash == 0, e.x, e.y))
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
            elif t.kind == "onigiri":
                img, wpp, z, lit = self.onigiri, 0.018, 0.0, True
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
            if p is None or (s.owner == "akuma" and s.t < 3):
                continue
            fr = s.frames[(s.t // 3) % len(s.frames)]
            if s.owner != "akuma":
                lat = s.vx * -math.sin(self.ang) + s.vy * math.cos(self.ang)
                if lat < 0:
                    fr = pygame.transform.flip(fr, True, False)
            h = fr.get_height()
            out.append((p[1], p[0], None, fr, (fr.get_width() // 2, h // 2), s.wpp, s.z, False, s.x, s.y))
        for fx in self.effects:
            p = self.project(fx.x, fx.y)
            if p is None:
                continue
            fr = fx.frames[min(len(fx.frames) - 1, fx.t // fx.speed)]
            out.append((p[1], p[0], None, fr, (fr.get_width() // 2, fr.get_height() // 2), fx.wpp, fx.z, False,
                        fx.x, fx.y))
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

    # ---- weapon view -----------------------------------------------------------------
    SKIN = (186, 104, 70)
    SKIN_D = (124, 60, 40)
    SKIN_L = (226, 150, 108)
    INK = (36, 14, 10)
    BAND = (120, 22, 22)
    BAND_D = (62, 8, 8)

    def _hand(self, surf, wx, wy, s, k):
        """One hand seen from behind, wrist at (wx, wy); s=+1 right hand, -1 left; k scale."""
        def P(pts):
            return [(wx + s * x * k, wy + y * k) for x, y in pts]
        arm = P([(-6, 0), (8, 0), (30, 60), (6, 60)])
        pygame.draw.polygon(surf, self.SKIN, arm)
        pygame.draw.polygon(surf, self.SKIN_D, P([(4, 4), (8, 0), (30, 60), (18, 60)]))
        pygame.draw.polygon(surf, self.INK, arm, 1)
        band = P([(-7, -2), (9, -2), (12, 9), (-4, 9)])
        pygame.draw.polygon(surf, self.BAND, band)
        pygame.draw.polygon(surf, self.BAND_D, P([(-5, 5), (11, 5), (12, 9), (-4, 9)]))
        pygame.draw.polygon(surf, self.INK, band, 1)
        for fx, fh in ((-8, 13), (-3, 15), (2, 14), (7, 11)):
            f = P([(fx, -14), (fx + 4, -14), (fx + 4 - s * 0, -14 - fh), (fx + 2, -16 - fh), (fx, -14 - fh)])
            pygame.draw.polygon(surf, self.SKIN, f)
            pygame.draw.polygon(surf, self.INK, f, 1)
            pygame.draw.line(surf, self.SKIN_L, (wx + s * (fx + 1) * k, wy + (-15) * k),
                             (wx + s * (fx + 1) * k, wy + (-12 - fh) * k))
        palm = P([(-9, -1), (-10, -12), (-7, -17), (10, -16), (12, -8), (10, -1)])
        pygame.draw.polygon(surf, self.SKIN, palm)
        pygame.draw.polygon(surf, self.SKIN_L, P([(-6, -14), (6, -14), (4, -10), (-5, -10)]))
        pygame.draw.polygon(surf, self.INK, palm, 1)
        for kx in (-6, -1, 4, 8):
            pygame.draw.rect(surf, self.SKIN_D, (wx + s * kx * k, wy - 15 * k, max(1, k), max(1, k)))
        thumb = P([(-9, -4), (-17, -10), (-19, -16), (-14, -15), (-8, -10)])
        pygame.draw.polygon(surf, self.SKIN, thumb)
        pygame.draw.polygon(surf, self.INK, thumb, 1)

    def _draw_hands(self, surf):
        bobx = math.sin(self.walk * 3.0) * 6 * self.moving
        boby = abs(math.cos(self.walk * 3.0)) * 4 * self.moving
        cx, cy = W // 2 + bobx, VIEW_H - 4 + boby
        gap, k, ball = 26, 1.2, 0.0
        w, t = self.weapon, self.wt
        if w == "hado":
            if t < 7:                       # pull back, ki gathers
                f = t / 7
                gap, cy, ball = 26 + 12 * f, cy + 10 * f, f
            else:                           # thrust out and back
                f = max(0.0, 1 - (t - 7) / 13)
                gap, cy, k, ball = 12 + 14 * (1 - f), cy - 20 * f, 1.2 - 0.2 * f, 0
        elif w == "shinku":
            if t < 18:
                f = t / 18
                gap, cy, ball = 26 + 18 * f, cy + 12 * f + math.sin(t) * f * 2, 1.6 * f
            else:
                f = max(0.0, 1 - (t - 18) / 22)
                gap, cy, k, ball = 10 + 16 * (1 - f), cy - 26 * f, 1.2 - 0.25 * f, 0
        elif w == "kick":
            gap, cy = 40, cy + 18
        if ball > 0.05:
            b = self.hado[(self.t // 3) % len(self.hado)]
            bs = pygame.transform.scale_by(b, 0.25 + 0.45 * ball)
            surf.blit(bs, (cx - bs.get_width() // 2, cy - 32 - bs.get_height() // 2))
        self._hand(surf, cx - gap, cy, -1, k)
        self._hand(surf, cx + gap, cy, 1, k)
        if w in ("hado", "shinku") and ((w == "hado" and 7 <= t < 11) or (w == "shinku" and 18 <= t < 23)):
            b = self.hado[0] if w == "hado" else self.shinku[0]
            bs = pygame.transform.scale_by(b, 0.6 if w == "hado" else 1.1)
            surf.blit(bs, (cx - bs.get_width() // 2, cy - 40 - bs.get_height() // 2))
        if w == "kick":
            f = 1 - abs(t - 6) / 16 if t < 22 else 0
            self._foot(surf, cx + 20, VIEW_H + 40 - f * 75)

    def _foot(self, surf, x, y):
        leg = [(x - 14, y + 30), (x + 18, y + 30), (x + 34, y + 120), (x - 10, y + 120)]
        pygame.draw.polygon(surf, (70, 70, 80), leg)
        pygame.draw.polygon(surf, (40, 40, 48), [(x + 6, y + 30), (x + 18, y + 30), (x + 34, y + 120), (x + 18, y + 120)])
        pygame.draw.polygon(surf, self.INK, leg, 1)
        sole = pygame.Rect(x - 13, y - 14, 28, 44)
        pygame.draw.ellipse(surf, self.SKIN, sole)
        pygame.draw.ellipse(surf, self.SKIN_D, sole.inflate(-10, -16).move(2, 8))
        pygame.draw.ellipse(surf, self.INK, sole, 1)
        for i, tx in enumerate((-9, -3, 3, 8, 12)):
            r = 4 if i == 0 else 3
            pygame.draw.circle(surf, self.SKIN, (x + tx, y - 15 + abs(i - 1)), r)
            pygame.draw.circle(surf, self.INK, (x + tx, y - 15 + abs(i - 1)), r, 1)

    # ---- status bar ------------------------------------------------------------------
    def _draw_bar(self, surf):
        y0 = VIEW_H
        surf.blit(self.bar_bg, (0, y0))
        red = (220, 30, 20)
        draw_text(surf, "%d" % self.ki, 28, y0 + 6, red, scale=2, align="center")
        draw_text(surf, "KI", 28, y0 + 22, (230, 230, 230), align="center")
        pct = max(0, int(round(100 * self.hp / self.max_hp)))
        draw_text(surf, "%d%%" % pct, 87, y0 + 6, red, scale=2, align="center")
        draw_text(surf, "HEALTH", 87, y0 + 22, (230, 230, 230), align="center")
        draw_text(surf, "%d/%d" % (self.kills, self.total), 228, y0 + 6, red, scale=2, align="center")
        draw_text(surf, "KILLS", 228, y0 + 22, (230, 230, 230), align="center")
        for i, (k, col) in enumerate((("blue", (40, 90, 255)), ("red", (230, 30, 30)))):
            r = pygame.Rect(262, y0 + 5 + i * 11, 10, 9)
            if k in self.keys:
                pygame.draw.rect(surf, col, r)
                pygame.draw.rect(surf, (255, 255, 255), (r.x + 2, r.y + 2, 6, 1))
            else:
                pygame.draw.rect(surf, (70, 66, 62), r, 1)
        ready = self.ki >= SHINKU_COST
        draw_text(surf, "SHINKU", 299, y0 + 6, (230, 230, 230), align="center")
        col = (120, 200, 255) if ready and (self.t // 15) % 2 else ((90, 150, 220) if ready else (90, 80, 80))
        draw_text(surf, "READY" if ready else "%d KI" % SHINKU_COST, 299, y0 + 17, col, align="center")
        self._draw_face(surf, 145, y0 + 1)

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
