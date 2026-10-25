"""Level 12: DUST II. A Counter-Strike round on a Dust 2 style map, built on
the Doom level's engine (doom.py: raycaster, hadoukens, punches, kicks,
shoryuken, tatsumaki, snacks, ki orbs, status bar).

Akuma plays the terrorist side alone, 1 vs 3. He spawns at T spawn carrying
the bomb and has to plant it on bomb site A or B (stand on the site and hold
I / shield for PLANT_T frames) before the round clock runs out. Once it is
planted the clock is the bomb's: the counter-terrorists drop everything and
run to it, and one that crouches over it for DEFUSE_T frames defuses it.
Any hit on the defuser stops the defuse (and it starts over). The bomb going
off wins the round; dying, the clock running out before the plant or a
finished defuse lose it.

The map is Dust 2 squeezed into the Doom grid (40 x 32 cells), north up like
the radar: T spawn at the bottom; Long A up the east side through the long
doors; the catwalk (short A) from mid; mid itself up the middle to the mid
doors and CT spawn; the dark B tunnels (upper and lower) on the west into B
site, whose wooden double doors lead to CT spawn. Sandstone, plaster, blue
shutters, crates and the red A / B site letters are painted in code, like the
Doom textures.

The CTs are Third Strike fighters: Chun-Li holds B, Ken (Ryu's sprites
repainted by tools/make_ken3s.py) holds A, and Ryu sits at the mid doors and
rotates to wherever Akuma is first spotted.
"""

import math

import numpy as np
import pygame

from . import doom as D
from .akuma_sprites import portrait
from .config import W
from .doom import (C_LIGHT, C_STONE, F_EXIT, F_LAVA, F_METAL, F_STONE, MAP_H, MAP_W, T_BAND, T_COMP, T_DOOR,
                   T_FACE, T_FLESH, T_HELL, T_TECH, TS, VIEW_H, SKY, DOOR)
from .font import draw_text, text_surface
from .pause import PauseMenu

LEVEL_NAME = "DUST II"
ROUND_T = 60 * 115            # 1:55 to plant, like a real round
PLANT_T = 60 * 3 + 12         # holding still on a site
BOMB_T = 60 * 40              # the C4 timer
DEFUSE_T = 60 * 6             # a CT crouched over the bomb (between kit and no kit)
ROTATE_DELAY = 150            # frames from the first sighting until the mid CT rotates
SITES = {"asite": "A", "bsite": "B"}
CODE = "7355608"
CONTROLS = [
    "UP / DOWN: WALK FORWARD / BACK",
    "LEFT / RIGHT: TURN",
    "HOLD I (SHIELD) + LEFT / RIGHT: STRAFE",
    "L: HADOUKEN    I + L: SHINKU HADOUKEN",
    "L + J: SHORYUKEN    L + K: TATSUMAKI",
    "J: PUNCH    K: KICK (KICK DOORS OPEN)",
    "ON SITE A OR B: HOLD I, STAND STILL = PLANT",
    "THEN KEEP THE CTS OFF THE BOMB",
    "HIT A DEFUSING CT TO STOP THE DEFUSE",
    "SNACKS HEAL. BLUE KI ORBS REFILL KI",
]

# the counter-terrorists (Third Strike sprites, tools/make_doom_fighters.py, tools/make_ken3s.py)
CT_KINDS = {
    "ryu": dict(cid="ryu3s", wpp=0.0095, shot_wpp=0.0075, hp=170, speed=0.03, melee=16, ranged=14, pain=0.45,
                shot="ki", radius=0.32, melee_pose="punch", name="RYU"),
    "ken": dict(cid="ken3s", wpp=0.0095, shot_wpp=0.0075, hp=160, speed=0.032, melee=18, ranged=13, pain=0.45,
                shot="ki", radius=0.32, melee_pose="kick", ranged_every=2, name="KEN"),
    "chunli": dict(cid="chunli3s", wpp=0.0095, shot_wpp=0.0085, hp=140, speed=0.042, melee=16, ranged=10,
                   pain=0.4, shot="ki", radius=0.3, melee_pose="kick", ranged_every=3, name="CHUN-LI"),
}
ICONS = {"ryu": "ryu", "ken": "ken", "chunli": "chunli"}


# ---- textures ----------------------------------------------------------------
_col, _fbm, _smooth, _blocks, _surface, _tex = D._col, D._fbm, D._smooth, D._blocks, D._surface, D._tex_from_surface


def _sandstone(rng, base=(214, 180, 122)):
    img, _ = _blocks(rng, base, 32, 16, bevel=1, mortar=(150, 122, 84), vary=0.07, moss=False)
    Y = np.arange(TS)[None, :]
    img *= (1.0 - 0.18 * np.clip((Y - 44) / 20, 0, 1))[..., None]      # dust kicked up the foot of the wall
    return img


def _plaster(rng):
    """Cracked render over brick, the plaster flaked off in patches."""
    n = _fbm(rng)
    img = _col((218, 190, 140), 0.8 + 0.24 * n)
    brick, _ = _blocks(rng, (178, 122, 78), 16, 8, bevel=1, mortar=(120, 96, 70), vary=0.1, moss=False)
    off = _smooth(rng, 4) > 0.68
    img[off] = brick[off]
    rim = (_smooth(rng, 4) > 0.655) & ~off
    img[rim] *= 0.78
    cr = (np.abs(_smooth(rng, 6) - 0.5) < 0.01) & (_smooth(rng, 3) > 0.45)
    img[cr] *= 0.6
    Y = np.arange(TS)[None, :]
    img *= (1.0 - 0.2 * np.clip((Y - 46) / 18, 0, 1))[..., None]
    return img


def _shutter(rng):
    """Plaster with a blue wooden shutter, the Dust 2 blue."""
    s = _surface(_plaster(rng))
    wood = _fbm(rng)
    blue = _surface(_col((52, 112, 150), 0.75 + 0.35 * wood))
    s.blit(blue, (18, 10), pygame.Rect(0, 0, 28, 40))
    pygame.draw.rect(s, (96, 72, 48), (16, 8, 32, 44), 2)
    for x in range(22, 46, 5):
        pygame.draw.line(s, (30, 70, 100), (x, 10), (x, 49))
    pygame.draw.line(s, (30, 70, 100), (32, 10), (32, 49), 2)
    pygame.draw.line(s, (120, 170, 200), (19, 11), (44, 11))
    pygame.draw.rect(s, (40, 36, 30), (35, 29, 2, 3))
    return _tex(s)


def _letter(rng, ch):
    """Sandstone with a big site letter sprayed on in red, and an arrow under it."""
    s = _surface(_sandstone(rng))
    t = text_surface(ch, (176, 34, 22), 5)
    w, h = t.get_size()
    paint = pygame.Surface((64, 64), pygame.SRCALPHA)
    for dx in range(3):
        for dy in range(3):
            paint.blit(t, (31 - w // 2 + dx, 7 + dy))         # fat strokes: a spray can, not a pen
    pygame.draw.polygon(paint, (176, 34, 22), [(18, 50), (40, 50), (40, 46), (48, 52), (40, 58), (40, 54), (18, 54)])
    a = pygame.surfarray.pixels_alpha(paint)
    spray = np.asarray(rng.random((64, 64)) < 0.9)
    a[...] = (a * spray).astype(np.uint8)
    del a
    s.blit(paint, (0, 0))
    return _tex(s)


def _crate(rng):
    n = _fbm(rng)
    X, Y = np.meshgrid(np.arange(TS), np.arange(TS), indexing="ij")
    grain = 0.8 + 0.25 * n + 0.08 * np.sin(Y * 0.9 + n * 6)
    s = _surface(_col((168, 118, 64), grain))
    for y in (15, 31, 47):
        pygame.draw.line(s, (92, 60, 30), (0, y), (63, y))
    dark, lite = (86, 56, 28), (204, 156, 96)
    pygame.draw.rect(s, dark, (0, 0, 64, 64), 6)
    pygame.draw.rect(s, lite, (1, 1, 62, 62), 1)
    pygame.draw.line(s, dark, (5, 5), (58, 58), 6)
    pygame.draw.line(s, lite, (6, 4), (59, 57), 1)
    for x, y in ((3, 3), (60, 3), (3, 60), (60, 60)):
        pygame.draw.rect(s, (60, 60, 64), (x - 1, y - 1, 3, 3))
    return _tex(s)


def _door(rng):
    """B doors: two weathered wooden leaves with iron studs."""
    n = _fbm(rng)
    X, Y = np.meshgrid(np.arange(TS), np.arange(TS), indexing="ij")
    grain = 0.72 + 0.3 * n + 0.06 * np.sin(X * 1.7 + n * 5)
    s = _surface(_col((132, 88, 48), grain))
    for x in range(0, 64, 8):
        pygame.draw.line(s, (70, 44, 22), (x, 0), (x, 63))
    pygame.draw.line(s, (36, 22, 10), (31, 0), (31, 63), 2)
    for y in (10, 52):
        pygame.draw.rect(s, (58, 56, 54), (0, y, 64, 4))
        for x in range(4, 64, 9):
            pygame.draw.rect(s, (150, 146, 140), (x, y + 1, 2, 2))
    pygame.draw.circle(s, (40, 38, 36), (27, 34), 2)
    pygame.draw.circle(s, (40, 38, 36), (36, 34), 2)
    return _tex(s)


def _floor(rng, kind):
    n = _fbm(rng)
    if kind == "sand":
        img = _col((200, 166, 112), 0.78 + 0.26 * n)
        peb = rng.random((TS, TS))
        img[peb > 0.985] *= 0.7
        img[peb < 0.012] = np.minimum(255, img[peb < 0.012] * 1.18)
        rip = np.abs(_smooth(rng, 8) - 0.5) < 0.02
        img[rip] *= 0.9
    elif kind == "pave":
        img, _ = _blocks(rng, (190, 156, 108), 32, 32, stagger=False, bevel=1, mortar=(132, 108, 74), vary=0.08,
                         moss=False)
        sand = _smooth(rng, 5) > 0.6
        img[sand] = _col((200, 166, 112), 0.8 + 0.2 * n)[sand]
    elif kind == "site":
        img, _ = _blocks(rng, (176, 140, 98), 16, 16, stagger=False, bevel=1, mortar=(118, 92, 62), vary=0.1,
                         moss=False)
        X, Y = np.meshgrid(np.arange(TS), np.arange(TS), indexing="ij")
        img[(X + Y) % 32 < 3] *= 0.86
    elif kind == "planks":
        X, Y = np.meshgrid(np.arange(TS), np.arange(TS), indexing="ij")
        img = _col((92, 64, 38), 0.75 + 0.3 * n + 0.05 * np.sin(X * 0.8))
        img[(Y % 16) < 1] *= 0.45
        img[(X % 32) < 2] = _col((50, 36, 22), 1 + 0 * n)[(X % 32) < 2]
    else:   # plaster ceiling
        img = _col((200, 174, 128), 0.75 + 0.2 * n)
    return img


def _sky(rng, w=512, h=84):
    """Pale desert sky, a haze on the horizon, low tan hills and the town's roofs."""
    X, Y = np.meshgrid(np.arange(w), np.arange(h), indexing="ij")
    t = Y / (h - 1)
    img = np.zeros((w, h, 3), np.float32)
    img[..., 0] = 96 + 126 * t ** 1.4
    img[..., 1] = 150 + 74 * t ** 1.4
    img[..., 2] = 214 + 18 * t
    cl = _smooth(rng, 16, w)[:, :h] * 0.6 + _smooth(rng, 32, w)[:, :h] * 0.4
    puff = np.clip((cl - 0.55) * 4, 0, 1) * np.clip(1.2 - t * 1.4, 0, 1)
    img += (puff * 60)[..., None]
    xs = np.arange(w)
    hills = h - 10 - 6 * np.sin(xs * 2 * np.pi * 3 / w + 1.0) - 3 * np.sin(xs * 2 * np.pi * 7 / w)
    m = Y > hills[:, None]
    img[m] = np.array((206, 178, 136), np.float32) * (0.95 + 0.05 * np.sin(Y[m] * 0.7))[:, None]
    # flat roofs and a dome or two, far off
    prng = np.random.default_rng(5)
    x = 0
    while x < w:
        bw = int(prng.integers(10, 26))
        bh = int(prng.integers(4, 12))
        top = h - 2 - bh
        if prng.random() < 0.65:
            col = np.array((188, 160, 118), np.float32) * prng.uniform(0.85, 1.0)
            img[x:x + bw, top:] = col
            img[x:x + bw, top] *= 1.12
            if prng.random() < 0.25:
                cx, r = x + bw // 2, bw // 3
                for k in range(-r, r + 1):
                    dh = int(math.sqrt(max(0, r * r - k * k)))
                    if 0 <= cx + k < w:
                        img[cx + k, max(0, top - dh):top] = col * 1.05
        x += bw + int(prng.integers(0, 14))
    dith = np.tile(D._BAYER_T, (w // 4 + 1, h // 4 + 1))[:w, :h]
    img = np.floor(img / 8 + dith[..., None]) * 8
    return np.clip(img, 0, 255)


def dust_textures(seed=2):
    """Same texture slots as doom.py's, repainted for the desert."""
    rng = np.random.default_rng(seed)
    T = np.zeros((D.N_TEX, TS, TS, 3), np.float32)
    T[T_HELL] = _sandstone(rng)
    T[T_BAND] = _plaster(rng)
    T[T_TECH] = _shutter(rng)
    # the raycaster lays every wall texture down mirrored (doom.py's symmetric
    # textures never show it), so the letters are painted back to front
    T[T_FACE] = _letter(rng, "A")[::-1]
    T[T_FLESH] = _letter(rng, "B")[::-1]
    T[T_COMP] = _crate(rng)
    T[T_DOOR] = _door(rng)
    T[D.T_JAMB] = _sandstone(rng, (180, 150, 104))
    T[F_STONE] = _floor(rng, "sand")
    T[F_METAL] = _floor(rng, "pave")
    T[F_EXIT] = _floor(rng, "site")
    T[F_LAVA] = _floor(rng, "sand")
    T[C_STONE] = _floor(rng, "planks")
    T[C_LIGHT] = _floor(rng, "ceil")
    return T, _sky(rng)


# ---- the map ---------------------------------------------------------------------
class DustMap(D.LevelMap):
    """Dust 2, north up like the radar (see the module docstring)."""

    def _build(self):
        R = self.room
        OUT, PAVE, SITE, TUN = F_STONE, F_METAL, F_EXIT, C_STONE
        # (the first matching rectangle names a cell, so the sites go first)
        R("bsite", 2, 2, 11, 9, T_HELL, SITE, SKY, 1.0)
        R("asite", 28, 1, 37, 9, T_HELL, SITE, SKY, 1.0)
        R("ctspawn", 15, 1, 25, 5, T_BAND, PAVE, SKY, 1.0)
        R("bdoors", 12, 4, 14, 4, T_BAND, PAVE, C_LIGHT, 0.75)
        R("ct_to_a", 26, 2, 27, 4, T_HELL, PAVE, SKY, 1.0)
        R("middoors", 18, 6, 20, 7, T_HELL, PAVE, SKY, 0.95)
        R("mid", 17, 8, 21, 24, T_HELL, OUT, SKY, 0.95)
        R("catwalk", 22, 11, 24, 12, T_BAND, PAVE, SKY, 0.95)
        R("short", 25, 7, 27, 12, T_HELL, PAVE, SKY, 0.95)
        R("longa", 34, 10, 37, 20, T_HELL, OUT, SKY, 0.95)
        R("longdoors", 34, 21, 35, 22, T_HELL, PAVE, C_LIGHT, 0.7)
        R("outsidelong", 27, 23, 37, 25, T_BAND, OUT, SKY, 0.95)
        R("start", 12, 25, 26, 30, T_HELL, OUT, SKY, 1.0)
        R("outsidetuns", 7, 26, 11, 29, T_BAND, OUT, SKY, 0.95)
        R("tunnels", 3, 10, 6, 28, T_HELL, PAVE, TUN, 0.5)
        R("lowertuns", 7, 16, 16, 17, T_HELL, PAVE, TUN, 0.45)
        # the B doors
        self.door(13, 4, T_DOOR)
        # crates and cover
        for x, y in ((4, 3), (5, 3), (9, 6), (3, 7), (10, 2),           # B site
                     (30, 3), (31, 3), (35, 6), (36, 2), (32, 7),       # A site (goose, the boxes)
                     (19, 13),                                          # mid: xbox
                     (36, 15), (34, 18),                                # long A
                     (17, 2), (24, 4),                                  # CT spawn
                     (30, 24), (14, 27), (24, 29), (9, 28)):            # outside long, T spawn, outside tunnels
            self.grid[y, x] = T_COMP
        # the sprayed site letters
        for x, y in ((38, 4), (33, 0), (33, 10), (27, 6)):
            self.grid[y, x] = T_FACE
        for x, y in ((0, 5), (7, 1), (7, 10), (12, 8)):
            self.grid[y, x] = T_FLESH
        # plaster and blue shutters among the sandstone
        for (y, x) in zip(*np.nonzero(self.grid == T_HELL)):
            h = (x * 7 + y * 13) % 11
            if h < 3:
                self.grid[y, x] = T_BAND
            elif h == 3 and 0 < x < MAP_W - 1 and 0 < y < MAP_H - 1 and \
                    any(self.grid[y + dy, x + dx] == 0 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                self.grid[y, x] = T_TECH
        th = self.things
        th += [("chunli", 7, 5), ("ken", 33, 5), ("ryu", 19, 5)]
        th += [("ki", 13, 26), ("ki", 25, 26), ("ki", 4, 21), ("ki", 18, 19), ("ki", 36, 19), ("ki", 23, 12),
               ("bigki", 8, 27), ("ki", 12, 17)]


class DustRenderer(D.Renderer):
    @staticmethod
    def fog(d):
        """Sunlight: far walls only fade a little."""
        return np.clip(1.08 - 0.02 * d, 0.5, 1.0)

    def __init__(self, lmap):
        super().__init__(lmap, dust_textures())


def _c4_world():
    """The planted bomb, lying on the ground: LED off / on."""
    out = []
    for on in (False, True):
        s = pygame.Surface((26, 12), pygame.SRCALPHA)
        pygame.draw.rect(s, (70, 64, 40), (0, 4, 26, 8))
        pygame.draw.rect(s, (120, 110, 70), (1, 4, 24, 2))
        for x in (3, 9, 15, 21):
            pygame.draw.rect(s, (150, 140, 96), (x, 6, 4, 5))
        pygame.draw.rect(s, (30, 30, 30), (8, 0, 10, 5))
        pygame.draw.rect(s, (90, 200, 90) if not on else (120, 255, 120), (9, 1, 8, 2))
        pygame.draw.rect(s, (255, 40, 30) if on else (90, 10, 10), (20, 1, 3, 3))
        pygame.draw.line(s, (200, 30, 30), (2, 5), (8, 1))
        out.append(s)
    return out


# ---- the scene ---------------------------------------------------------------------
class CsScene(D.DoomScene):
    MAP, RENDERER, KINDS = DustMap, DustRenderer, CT_KINDS
    START = (19.5, 28.5, -math.pi / 2)
    EXTRA_SNACKS = 5
    FIXTURES = ("torch", "portal", "c4")
    FIGHTER_TINT = ((255, 255, 255), (0, 0, 0))      # soldiers, not possessed: their own colours

    def __init__(self, game, seed=None, level=12, hp=None):
        super().__init__(game, seed, level, hp)
        self.menu = PauseMenu(game, CONTROLS)
        self.round_t = ROUND_T
        self.plant = 0
        self.bomb = None
        self.bomb_t = 0
        self.bomb_flow = {}
        self.defuser = None
        self.defuse = 0
        self.spotted = False
        self.rotate_t = 0
        self.site_hint = None
        self.why = ""
        self.feed = []               # kill feed: (text, frames left)
        self.inp = None
        self.c4 = _c4_world()
        self.boom = D._burst_frames((255, 244, 190), (255, 96, 20), n=10, r=40)
        self.icons = {}
        for k, cid in dict(ICONS, akuma="akuma").items():
            img = portrait(cid)
            self.icons[k] = pygame.transform.smoothscale(img, (14, 14)) if img else None
        for e in self.enemies:
            e.role = {"chunli": "B", "ken": "A", "ryu": "mid"}[e.kind]

    # ---- the round ---------------------------------------------------------------
    def update(self, inp):
        self.inp = inp
        if self.phase == "ctwin":
            self.t += 1
            self.end_t += 1
            for v in ("msg_t", "banner_t", "hurt"):
                if getattr(self, v) > 0:
                    setattr(self, v, getattr(self, v) - 1)
            self.flash *= 0.8
            self._lights()
            self._doors()
            for ef in self.effects:
                ef.t += 1
            self.effects = [ef for ef in self.effects if ef.alive]
            self._shots()
            skip = self.end_t > 50 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= 200 or skip:
                self.result = "lose"
                self.game.level_failed(self)
            return
        was = self.phase
        super().update(inp)
        if was == "intro" and self.phase == "play":
            self.banner, self.banner_t = "GO! GO! GO!", 90
            self._play("encounter")
        self.feed = [(s, n - 1) for s, n in self.feed if n > 1]

    def _triggers(self):
        if self.bomb is None:
            self.round_t -= 1
            if self.round_t <= 0:
                self._ct_win("THE TERRORISTS RAN OUT OF TIME")
                return
            self._planting()
        else:
            self.bomb_t -= 1
            if not any(e.alive for e in self.enemies) and self.bomb_t > 150:
                self.bomb_t = 150                   # nobody left to defuse it: no need to wait
            left = self.bomb_t
            every = 60 if left > 60 * 20 else (30 if left > 60 * 10 else (15 if left > 60 * 4 else 7))
            if left % every == 0:
                self._play("beep", None, 0.6)
            if left <= 0:
                self._detonate()
                return
        if self.spotted and self.rotate_t > 0:
            self.rotate_t -= 1
            if self.rotate_t == 0:
                for e in self.enemies:
                    if e.alive and e.role == "mid" and not e.alert:
                        e.alert = True
                        self.say("RYU IS ROTATING", 90)
        if not self.spotted and any(e.alert and e.alive for e in self.enemies):
            self.spotted = True
            self.rotate_t = ROTATE_DELAY

    def _planting(self):
        inp = self.inp
        site = SITES.get(self.map.area_of(int(self.px), int(self.py)))
        if site != self.site_hint:
            self.site_hint = site
            if site:
                self.say("BOMB SITE %s: HOLD I AND STAND STILL TO PLANT" % site, 150)
        busy = inp is None or any(inp.held(k) for k in ("up", "down", "left", "right", "special"))
        if site and inp is not None and inp.held("shield") and not busy and self.weapon is None:
            if self.plant == 0:
                self._play("plant")
            self.plant += 1
            if self.plant % (PLANT_T // len(CODE)) == 0:
                self._play("beep", None, 0.4)
            if self.plant >= PLANT_T:
                self._planted(site)
        else:
            self.plant = 0

    def _planted(self, site):
        self.plant = 0
        b = D.Thing("c4", 0, 0)
        b.x = self.px + math.cos(self.ang) * 0.3
        b.y = self.py + math.sin(self.ang) * 0.3
        if self.map.solid(int(b.x), int(b.y)):
            b.x, b.y = self.px, self.py
        b.site = site
        self.things.append(b)
        self.bomb = b
        self.bomb_t = BOMB_T
        self.banner, self.banner_t = "THE BOMB HAS BEEN PLANTED", 180
        self.say("DEFEND SITE %s" % site, 150)
        self._play("doom_key", "pickup")
        # every CT now knows where it is
        start = (int(b.x), int(b.y))
        dist = {start: 0}
        q = [start]
        m = self.map
        for c in q:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + dx, c[1] + dy)
                if n in dist or not (0 <= n[0] < MAP_W and 0 <= n[1] < MAP_H):
                    continue
                g = m.grid[n[1], n[0]]
                if g == 0 or (g == DOOR and m.doors[n].key is None):
                    dist[n] = dist[c] + 1
                    q.append(n)
        self.bomb_flow = dist
        for e in self.enemies:
            if e.alive:
                e.alert = True

    def _detonate(self):
        b = self.bomb
        self.phase, self.end_t = "won", 0
        self.banner, self.banner_t = "TERRORISTS WIN", 999
        self.flash = 3.0
        self._play("doom_bossdie", "ko")
        self._play("boom")
        # a fireball where it lay, and a ring of them rolling out
        self.effects.append(D.Effect(b.x, b.y, 0.6, self.boom, 0.05, 5))
        for k in range(8):
            a = k * math.pi / 4
            self.effects.append(D.Effect(b.x + math.cos(a) * 1.4, b.y + math.sin(a) * 1.4, 0.4, self.boom, 0.03, 4))
        for e in self.enemies:
            if e.alive and (e.x - b.x) ** 2 + (e.y - b.y) ** 2 < 6 ** 2:
                e.set("dying")
        b.taken = True

    def _ct_win(self, why):
        self.phase, self.end_t = "ctwin", 0
        self.why = why
        self.weapon = None
        self.plant = 0
        self.banner, self.banner_t = "COUNTER-TERRORISTS WIN", 999
        self._play("doom_death", "ko")

    # ---- the CTs ---------------------------------------------------------------------
    def _damage(self, e, dmg, push=(0, 0)):
        if e is self.defuser and e.alive:
            self.defuser = None
            self.defuse = 0
            e.set("chase")
            self.say("DEFUSE STOPPED!", 90)
        alive = e.alive
        super()._damage(e, dmg, push)
        if alive and not e.alive:
            self.feed.append(("AKUMA > %s" % e.spec["name"], 240))
            left = sum(1 for x in self.enemies if x.alive)
            if left:
                self.say("%d CT%s LEFT" % (left, "S" if left > 1 else ""), 120)
            elif self.bomb is None:
                self.say("ALL CTS DOWN. NOW PLANT THE BOMB!", 200)

    def _enemy(self, e):
        """Before the plant the CTs fight like the Doom fighters (doom.py). After
        it every one runs to the bomb, fighting only when Akuma is right in
        its way, and crouches over it to defuse."""
        if self.bomb is None or not e.alive or e.state in ("pain", "attack"):
            return super()._enemy(e)
        dx, dy = self.px - e.x, self.py - e.y
        dist = math.hypot(dx, dy)
        if (self.t + e.look_t) % 8 == 0:
            e.see = dist < 16 and self.map.los(e.x, e.y, self.px, self.py)
        b = self.bomb
        bd = math.hypot(b.x - e.x, b.y - e.y)
        if e.state == "defuse":
            e.st += 1
            if e.flash:
                e.flash -= 1
            self.defuse += 1
            if self.defuse % 40 == 0:
                self._play("doom_item", "pickup", 0.4)
            if self.defuse >= DEFUSE_T:
                self._ct_win("THE BOMB HAS BEEN DEFUSED")
            return
        if e.see and dist < 3.5 and (bd > 1.0 or self.defuser is not None):
            return super()._enemy(e)
        e.st += 1
        if e.flash:
            e.flash -= 1
        if e.cool > 0:
            e.cool -= 1
        if bd < 0.55 and self.defuser is None:
            e.set("defuse")
            self.defuser = e
            self.defuse = 0
            self.say("%s IS DEFUSING THE BOMB!" % e.spec["name"], 150)
            self._play("doom_sight", "encounter", 0.6)
            return
        if bd < 0.9 and self.defuser is not None:
            # someone's on it already: guard the defuser, throw at Akuma
            if e.see and e.cool <= 0 and dist < 13:
                e.set("attack")
                e.mode = "ranged"
            return
        if bd < 2.5 and self.map.los(e.x, e.y, b.x, b.y):
            tx, ty = b.x, b.y
        else:
            c = (int(e.x), int(e.y))
            best, bdist = None, self.bomb_flow.get(c, 999)
            for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + ddx, c[1] + ddy)
                if self.bomb_flow.get(n, 999) < bdist:
                    best, bdist = n, self.bomb_flow[n]
            if best is None:
                tx, ty = b.x, b.y
            else:
                if self.map.grid[best[1], best[0]] == DOOR:
                    d = self.map.doors[best]
                    if d.open < 0.95:
                        self.open_door(d, by_player=False)
                tx, ty = best[0] + 0.5, best[1] + 0.5
        e.state = "chase"
        ax, ay = tx - e.x, ty - e.y
        al = math.hypot(ax, ay) or 1
        sp = e.speed * 1.2                          # running for the bomb
        mx, my = ax / al * min(sp, al), ay / al * min(sp, al)
        r = min(e.radius, 0.3)
        if self._free(e.x + mx, e.y, r) and not self._near_player(e.x + mx, e.y, e):
            e.x += mx
        if self._free(e.x, e.y + my, r) and not self._near_player(e.x, e.y + my, e):
            e.y += my
        e.walked += sp

    def _enemy_image(self, e, flip):
        if e.state != "defuse":
            return super()._enemy_image(e, flip)
        art = e.art
        key = art.resolve("hado_prep", 0, span=1)        # bent over the bomb, hands on it
        flash = e.flash > 0
        ck = (e.cid, False, key, flip, flash)
        img = self._lit.get(ck)
        if img is None:
            img, _ = art.entry(key, flip, flash)
            self._lit[ck] = img
        return ck, img, art.anchor(key, flip)

    def _thing_sprite(self, t, bob):
        if t.kind == "c4":
            on = self.bomb_t % 60 < 8 or (self.bomb_t < 60 * 10 and self.bomb_t % 14 < 6)
            return self.c4[1 if on else 0], 0.012, 0.0, True
        return super()._thing_sprite(t, bob)

    # ---- drawing ---------------------------------------------------------------------
    def _draw_hands(self, surf):
        if not self.plant:
            return super()._draw_hands(surf)
        # the C4 held low between both claws, its code typed in as the plant goes on
        cx, top = W // 2, VIEW_H - 40
        self._idle(surf, cx - 66, VIEW_H + 30, left=True)
        self._idle(surf, cx + 66, VIEW_H + 30)
        pygame.draw.rect(surf, (60, 56, 36), (cx - 40, top + 14, 80, 40))
        pygame.draw.rect(surf, (104, 96, 62), (cx - 40, top + 14, 80, 40), 2)
        for k in range(4):
            pygame.draw.rect(surf, (150, 140, 96), (cx - 36 + k * 19, top + 30, 15, 16))
        pygame.draw.rect(surf, (24, 24, 24), (cx - 26, top, 52, 22))
        pygame.draw.rect(surf, (70, 160, 70), (cx - 22, top + 3, 44, 9))
        n = min(len(CODE), self.plant * len(CODE) // PLANT_T)
        draw_text(surf, CODE[:n] + ("_" if (self.t // 8) % 2 else " "), cx - 20, top + 4, (20, 50, 20), shadow=None)
        for i in range(6):
            pygame.draw.rect(surf, (200, 196, 180), (cx - 22 + i * 7, top + 14, 5, 3))
        pygame.draw.rect(surf, (255, 40, 30) if (self.t // 10) % 2 else (90, 10, 10), (cx + 16, top + 14, 4, 4))
        pygame.draw.line(surf, (200, 30, 30), (cx - 40, top + 20), (cx - 26, top + 8), 2)

    def _clock(self):
        if self.bomb is not None:
            return "%d" % max(0, math.ceil(self.bomb_t / 60))
        s = max(0, math.ceil(self.round_t / 60))
        return "%d:%02d" % (s // 60, s % 60)

    def _draw_text(self, surf):
        # the scoreboard: T (Akuma) on the left, the three CTs on the right, the clock between
        y = 2
        clock = self._clock()
        bomb = self.bomb is not None
        col = (255, 60, 40) if bomb and (self.t // 15) % 2 else ((255, 230, 120) if not bomb else (200, 40, 30))
        pygame.draw.rect(surf, (0, 0, 0), (W // 2 - 20, y - 1, 40, 11))
        draw_text(surf, clock, W // 2, y + 1, col, align="center")
        if bomb:
            pygame.draw.rect(surf, (200, 40, 30), (W // 2 - 19, y, 4, 9))
        x = W // 2 - 26
        self._icon(surf, "akuma", x - 14, y - 1, self.phase != "lost", (230, 170, 60))
        draw_text(surf, "T", x - 20, y + 2, (230, 170, 60), align="right")
        x = W // 2 + 24
        for i, e in enumerate(self.enemies):
            self._icon(surf, e.kind, x + i * 16, y - 1, e.alive, (90, 140, 230))
        draw_text(surf, "CT", x + 3 * 16 + 2, y + 2, (90, 140, 230))
        # the kill feed
        for i, (s, n) in enumerate(self.feed[-3:]):
            draw_text(surf, s, W - 3, 18 + i * 9, (255, 255, 255), align="right")
        if self.msg_t:
            draw_text(surf, self.msg, 3, VIEW_H - 11, (255, 220, 120))
        if self.plant:
            w = 100
            f = self.plant / PLANT_T
            draw_text(surf, "PLANTING THE BOMB", W // 2, 40, (255, 230, 120), align="center")
            pygame.draw.rect(surf, (0, 0, 0), (W // 2 - w // 2 - 1, 50, w + 2, 6))
            pygame.draw.rect(surf, (230, 170, 60), (W // 2 - w // 2, 51, int(w * f), 4))
        if self.defuser is not None and self.phase == "play":
            w = 100
            f = self.defuse / DEFUSE_T
            if (self.t // 10) % 2:
                draw_text(surf, "%s IS DEFUSING!" % self.defuser.spec["name"], W // 2, 40, (120, 170, 255),
                          align="center")
            pygame.draw.rect(surf, (0, 0, 0), (W // 2 - w // 2 - 1, 50, w + 2, 6))
            pygame.draw.rect(surf, (90, 140, 230), (W // 2 - w // 2, 51, int(w * f), 4))
        if self.phase == "intro":
            draw_text(surf, "COUNTER-STRIKE", W // 2, 26, (230, 170, 60), scale=2, align="center")
            draw_text(surf, "LEVEL %d: %s" % (self.level, LEVEL_NAME), W // 2, 52, (255, 230, 180), align="center")
            draw_text(surf, "1 VS 3. YOU ARE THE TERRORIST.", W // 2, 68, (230, 220, 210), align="center")
            draw_text(surf, "PLANT THE BOMB ON A OR B.", W // 2, 80, (230, 220, 210), align="center")
        elif self.banner_t:
            win = self.phase == "won" or self.banner.startswith("TERR")
            colr = (255, 210, 90) if win else ((120, 170, 255) if "COUNTER" in self.banner else (255, 230, 120))
            draw_text(surf, self.banner, W // 2, 30, colr, scale=2 if len(self.banner) < 20 else 1, align="center")
        if self.phase == "won" and self.end_t > 40:
            draw_text(surf, "THE TARGET HAS BEEN BOMBED", W // 2, 70, (90, 40, 10), align="center")
        if self.phase == "ctwin":
            draw_text(surf, self.why, W // 2, 50, (200, 220, 255), align="center")
        if self.phase == "lost":
            draw_text(surf, "COUNTER-TERRORISTS WIN", W // 2, 40, (120, 170, 255), align="center")
            draw_text(surf, "AKUMA HAS FALLEN", W // 2, 60, (255, 60, 40), scale=2, align="center")

    def _icon(self, surf, kind, x, y, alive, col):
        r = pygame.Rect(x, y, 14, 14)
        pygame.draw.rect(surf, (0, 0, 0), r.inflate(2, 2))
        pygame.draw.rect(surf, col, r.inflate(2, 2), 1)
        img = self.icons.get(kind)
        if img is not None:
            surf.blit(img, r)
        if not alive:
            surf.fill((90, 90, 90), r, special_flags=pygame.BLEND_RGB_MULT)
            pygame.draw.line(surf, (220, 30, 20), r.topleft, r.bottomright, 2)
            pygame.draw.line(surf, (220, 30, 20), r.topright, r.bottomleft, 2)
