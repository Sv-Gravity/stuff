"""Level 3: the car-smashing level (Street Fighter II bonus-stage style).

Cars drive around the map instead of enemies. Touching one starts a timed
bonus round: the car never fights back, and it has to be smashed on both
sides (jump over it to reach the other side) before the timer runs out.

The boss is THE TETRIS MASTER, a guy at an arcade cabinet playing the
falling-block puzzle on a giant well that fills the right of the stage. He
steers each piece like a real player and stacks toward a 4-line TETRIS, which
blasts Akuma. Akuma breaks his stacked blocks (and smashes pieces in mid-air)
to wreck his lines and drain his health; the blocks are solid to stand on,
and a falling piece that lands on Akuma hurts.
"""

import math
import os
import random

import pygame

from . import audio
from . import fight as F
from .art import shade, mix, _outlined, OUTLINE
from .config import W, H, FPS, GROUND_Y, HITSTOP, STAGE_LEFT, STAGE_RIGHT
from .fighters import Fighter, overlap, contact, image_area, rect_area, CANCEL_WINDOW, HIT, STEP_UP
from .font import draw_text
from .pause import PauseMenu
from .akuma_sprites import asset_dir

try:                    # Akuma's explosion frames (assets/fx); the old sparks if missing
    from . import fx as _fx
except Exception:       # pragma: no cover
    _fx = None

# The original code-drawn line-up. Side profiles are drawn facing right in a
# 108 x 50 box, tyres touching y = 47. Only used now if the painted car sprites
# (assets/cars, cut by tools/make_cars.py) are missing.
DRAWN_MODELS = [
    dict(name="TOYOTA AE86", color=(236, 236, 232), lower=(30, 30, 34),     # panda Trueno
         body=[(4, 24), (14, 23), (78, 24), (101, 27), (103, 30), (103, 40), (4, 40)],
         cabin=[(14, 24), (36, 12), (64, 12), (78, 24)],
         windows=[[(20, 23), (37, 14), (46, 14), (46, 23)], [(49, 14), (62, 14), (74, 23), (49, 23)]],
         wheels=(24, 84, 8), popups=(86, 98, 25), head=None, tail=(4, 25, 3, 5),
         extras=["amber"]),
    dict(name="TOYOTA MR2", color=(206, 30, 36), lower=(30, 30, 34),        # first-gen AW11
         body=[(6, 27), (30, 25), (70, 25), (100, 29), (101, 31), (100, 40), (6, 40)],
         cabin=[(30, 25), (44, 16), (60, 16), (74, 25)],
         windows=[[(37, 24), (46, 18), (52, 18), (52, 24)], [(55, 18), (60, 18), (70, 24), (55, 24)]],
         wheels=(22, 82, 8), popups=(84, 96, 26), head=None, tail=(6, 27, 3, 4),
         extras=["intake", "lip"]),
    dict(name="'99 MUSTANG GT", color=(200, 24, 30), lower=None,             # New Edge
         body=[(2, 25), (30, 23), (72, 23), (96, 24), (104, 28), (104, 40), (2, 40)],
         cabin=[(26, 23), (40, 12), (62, 12), (76, 23)],
         windows=[[(32, 22), (42, 14), (50, 14), (50, 22)], [(53, 14), (61, 14), (72, 22), (53, 22)]],
         wheels=(22, 86, 9), popups=None, head=(97, 25, 6, 3), tail=(2, 25, 3, 5),
         extras=["scoop", "hood", "spoiler", "stripe"]),
    dict(name="EAGLE TALON TSI", color=(30, 110, 80), lower=None,
         body=[(4, 26), (22, 24), (74, 24), (98, 28), (102, 32), (102, 40), (4, 40)],
         cabin=[(14, 25), (40, 12), (62, 12), (80, 25)],
         windows=[[(24, 23), (41, 14), (50, 14), (50, 23)], [(53, 14), (61, 14), (74, 23), (53, 23)]],
         wheels=(22, 84, 8), popups=None, head=(94, 27, 6, 3), tail=(4, 27, 3, 4),
         extras=["wing"]),
    dict(name="'65 COUGAR XLR", color=(110, 24, 36), lower=None,
         body=[(1, 26), (24, 25), (80, 25), (104, 26), (106, 29), (106, 40), (1, 40)],
         cabin=[(30, 25), (42, 13), (66, 13), (76, 25)],
         windows=[[(36, 24), (43, 15), (53, 15), (53, 24)], [(56, 15), (65, 15), (73, 24), (56, 24)]],
         wheels=(24, 86, 8), popups=None, head=None, tail=(1, 27, 3, 4),
         extras=["chrome", "vinyl", "grille", "whitewall"]),
]

# Toshi's line-up, painted (art_source/akuma_car_damage_sheet.png): one side
# view per damage stage in assets/cars/<key>_<stage>.png, facing right.
# color/roof: their top-down map sprite; drawn: the fallback drawn model.
CAR_MODELS = [
    dict(name="TOYOTA AE86", key="ae86", color=(236, 236, 232), roof=None, drawn=0),
    dict(name="TOYOTA MR2 SW20", key="mr2", color=(206, 30, 36), roof=None, drawn=1),
    dict(name="MAZDA MIATA NA", key="miata", color=(222, 40, 40), roof=(40, 34, 38), drawn=2),
    dict(name="HONDA S2000 AP1", key="s2000", color=(240, 196, 30), roof=(28, 28, 32), drawn=3),
    dict(name="VW GTI MK2", key="gti", color=(232, 232, 228), roof=None, drawn=0),
    dict(name="MAZDA RX-7 FC35", key="rx7", color=(242, 240, 236), roof=None, drawn=3),
    dict(name="'65 MERCURY COUGAR", key="cougar", color=(40, 130, 136), roof=None, drawn=4),
]
MODEL_BY_NAME = {m["name"]: m for m in CAR_MODELS}
STAGES = 5          # pristine, light, medium, heavy, destroyed
_SPRITES = {}


def car_sprite(model, stage):
    """The painted side view of a model at damage stage 0-4 (facing right), or None."""
    key = (model.get("key"), stage)
    if key not in _SPRITES:
        img = None
        if model.get("key"):
            path = os.path.join(asset_dir(), "cars", "%s_%d.png" % key)
            try:
                img = pygame.image.load(path)
                try:
                    img = img.convert_alpha()
                except pygame.error:        # no display yet
                    pass
            except (pygame.error, FileNotFoundError):
                img = None
        _SPRITES[key] = img
    return _SPRITES[key]


def car_anchor(model):
    """Anchor of a model's sprites: centre of the pristine car, tyres on the ground."""
    key = (model.get("key"), "anchor")
    if key not in _SPRITES:
        img = car_sprite(model, 0)
        r = img.get_bounding_rect()
        _SPRITES[key] = (r.centerx, r.bottom - 2, r.width // 2)
    return _SPRITES[key]


def sheet_stage(frac):
    """Painted damage stage for the share of HP left: pristine .. destroyed."""
    if frac <= 0:
        return 4
    return 0 if frac > 0.8 else 1 if frac > 0.6 else 2 if frac > 0.35 else 3


def explosion(kind, x, y, height, rate=4):
    """A fx explosion Effect centred on (x, y), or None without the fx frames."""
    if _fx is None:
        return None
    try:
        return F.Effect(_fx.fx_frames(kind, scale_height=height), x, y, rate)
    except Exception:
        return None

CAR_SIDE_HITS = 5          # kicks (normal hits) to wreck one side of a car
CAR_TIME = 30              # seconds
TIMEOUT_DMG = 20           # Akuma's penalty when a car gets away

# falling-block pieces (cells as (col, row))
PIECES = {
    "I": ((0, 0), (1, 0), (2, 0), (3, 0)), "O": ((0, 0), (1, 0), (0, 1), (1, 1)),
    "T": ((0, 0), (1, 0), (2, 0), (1, 1)), "S": ((1, 0), (2, 0), (0, 1), (1, 1)),
    "Z": ((0, 0), (1, 0), (1, 1), (2, 1)), "J": ((0, 0), (0, 1), (1, 1), (2, 1)),
    "L": ((2, 0), (0, 1), (1, 1), (2, 1)),
}
PIECE_COLORS = {"I": (40, 210, 230), "O": (240, 210, 40), "T": (170, 60, 200), "S": (60, 200, 80),
                "Z": (230, 50, 50), "J": (50, 90, 230), "L": (250, 140, 30)}



def _rotations(cells):
    out = []
    cur = list(cells)
    for _ in range(4):
        mx = min(c for c, _ in cur)
        my = min(r for _, r in cur)
        norm = tuple(sorted((c - mx, r - my) for c, r in cur))
        if norm not in out:
            out.append(norm)
        cur = [(-r, c) for c, r in cur]
    return out


# --------------------------------------------------------------------------
# side-view car art
# --------------------------------------------------------------------------
CAR_W, CAR_H = 108, 50
CAR_ANCHOR = (54, 47)
TATSU_CAR_DMG = 0.5   # per hit; a spin through the whole car lands about a dozen
FOOT = 6          # half the width of Akuma's feet, for standing on roofs


def _stage_of(frac):
    if frac <= 0:
        return 3
    return 0 if frac > 0.7 else 1 if frac > 0.35 else 2


def car_side(model, ldmg, rdmg, seed=0):
    """A side-view car facing right. ldmg/rdmg: damage stage 0-3 of the rear/front half."""
    if "drawn" in model:
        model = DRAWN_MODELS[model["drawn"]]
    rng = random.Random(seed * 13 + ldmg * 4 + rdmg)
    s = pygame.Surface((CAR_W, CAR_H), pygame.SRCALPHA)
    color = model["color"]
    dark = shade(color, 0.62)
    lite = shade(color, 1.18) if sum(color) < 600 else (255, 255, 255)
    chrome = (200, 204, 214)
    ex = model["extras"]
    mid = 54

    def crushed(pts):     # a wrecked half has its roof caved in
        return [(x, y + (6 if (ldmg >= 3 and x < mid) or (rdmg >= 3 and x >= mid) else 0)) for x, y in pts]

    pygame.draw.polygon(s, color, model["body"])
    cabin = crushed(model["cabin"])
    pygame.draw.polygon(s, color, cabin)
    if "vinyl" in ex:
        pygame.draw.lines(s, (24, 22, 26), False, cabin[:3], 3)
    # highlight along the shoulder line
    top = min(y for _, y in model["body"][1:3])
    pygame.draw.line(s, lite, (model["body"][1][0], top + 1), (model["body"][2][0], top + 1))
    if model["lower"]:
        s.fill(model["lower"], (min(x for x, _ in model["body"]), 32, 102, 6))
    pygame.draw.rect(s, dark, (2, 37, 104, 3))
    # windows
    for k, win in enumerate(model["windows"]):
        win = crushed(win)
        d = ldmg if k == 0 else rdmg
        if d >= 2:
            pygame.draw.polygon(s, (30, 36, 48), win)
            cx = sum(p[0] for p in win) // len(win)
            cy = sum(p[1] for p in win) // len(win)
            for _ in range(4):
                a = rng.uniform(0, math.tau)
                pygame.draw.line(s, (200, 220, 235), (cx, cy), (cx + int(math.cos(a) * 7), cy + int(math.sin(a) * 4)))
        else:
            pygame.draw.polygon(s, (110, 170, 215), win)
            pygame.draw.line(s, (220, 240, 255), (win[1][0], win[1][1] + 1), (win[1][0] - 3, win[0][1] - 1))
    # door seams and handles
    for x in (model["windows"][0][2][0] + 1, model["windows"][1][2][0] + 2):
        pygame.draw.line(s, dark, (x, top + 1), (x, 34))
    pygame.draw.rect(s, chrome, (model["windows"][1][0][0] + 3, top + 3, 4, 1))
    # model details
    if "stripe" in ex:
        pygame.draw.line(s, (20, 20, 24), (6, 30), (100, 30))
    if "scoop" in ex:
        pygame.draw.polygon(s, (24, 22, 28), [(30, 27), (38, 26), (38, 31)])
    if "intake" in ex:
        s.fill((24, 22, 28), (28, 26, 5, 6))
    if "hood" in ex:
        pygame.draw.rect(s, shade(color, 0.8), (82, 22, 10, 2))
    if "spoiler" in ex:
        pygame.draw.line(s, dark, (2, 23), (10, 22), 2)
    if "lip" in ex:
        pygame.draw.line(s, (40, 40, 44), (6, 26), (16, 25), 2)
    if "wing" in ex:
        for x in (8, 15):
            pygame.draw.line(s, dark, (x, 25), (x, 20))
        pygame.draw.line(s, color, (2, 19), (20, 19), 2)
    if "chrome" in ex:
        pygame.draw.line(s, chrome, (4, 30), (102, 30))
    if "grille" in ex:
        s.fill((30, 30, 34), (102, 27, 4, 7))
        for y in (28, 30, 32):
            pygame.draw.line(s, chrome, (102, y), (105, y))
    # lights
    if model["popups"]:
        x0, x1, y = model["popups"]
        pygame.draw.line(s, dark, (x0, y), (x1, y))
        pygame.draw.line(s, dark, (x0, y), (x0, y + 2))
    if "amber" in ex:
        s.fill((255, 170, 40) if rdmg < 2 else (90, 70, 40), (100, 29, 3, 2))
    if model["head"]:
        s.fill((255, 240, 150) if rdmg < 2 else (90, 80, 60), model["head"])
    s.fill((230, 30, 30) if ldmg < 2 else (80, 30, 30), model["tail"])
    # bumpers
    bum = chrome if "chrome" in ex else (40, 40, 46) if model["lower"] else shade(color, 0.85)
    xs = [x for x, _ in model["body"]]
    for x, d in ((min(xs) - 1, ldmg), (max(xs) - 7, rdmg)):
        if d >= 2:
            pygame.draw.line(s, bum, (x, 34), (x + 6, 39), 2)
        else:
            pygame.draw.rect(s, bum, (x, 33, 8, 3))
    # wheels
    rx, fx, r = model["wheels"]
    for wx, d in ((rx, ldmg), (fx, rdmg)):
        pygame.draw.circle(s, (18, 16, 22), (wx, 47 - r), r + 2)      # wheel arch
        if d >= 3:
            pygame.draw.ellipse(s, (20, 20, 24), (wx - r - 1, 47 - 7, 2 * r + 2, 8))
            pygame.draw.ellipse(s, (90, 90, 100), (wx - 4, 41, 8, 5))
        else:
            pygame.draw.circle(s, (20, 20, 24), (wx, 47 - r), r)
            if "whitewall" in ex:
                pygame.draw.circle(s, (230, 230, 225), (wx, 47 - r), r - 2, 1)
            pygame.draw.circle(s, (150, 150, 160), (wx, 47 - r), r // 2)
            pygame.draw.circle(s, (70, 70, 80), (wx, 47 - r), 2)
    # dents, scratches and a torn-off door
    for half, d in ((0, ldmg), (1, rdmg)):
        x0 = 6 if half == 0 else mid + 2
        for _ in range(d * 5):
            x = rng.randint(x0, x0 + 44)
            y = rng.randint(top + 1, 35)
            pygame.draw.line(s, shade(dark, 0.7), (x, y), (x + rng.randint(-4, 4), y + rng.randint(1, 3)))
        if d >= 3:
            door = pygame.Rect(mid - 19, top + 1, 18, 33 - top) if half == 0 else pygame.Rect(mid + 1, top + 1, 20, 33 - top)
            s.fill((26, 22, 30), door)
            pygame.draw.rect(s, (60, 54, 64), door, 1)
    return _outlined(s)


def scarred(img, ldmg, rdmg, seed=0):
    """The painted car with fresh dents and scrapes on whichever half took the
    beating (ldmg/rdmg: 0-3 for the rear/front half), so a one-sided pounding shows."""
    if not ldmg and not rdmg:
        return img
    out = img.copy()
    m = pygame.mask.from_surface(img, 127)
    w, h = img.get_size()
    r = img.get_bounding_rect()
    mid = r.centerx
    rng = random.Random(seed * 31 + ldmg * 5 + rdmg)
    for half, d in ((0, ldmg), (1, rdmg)):
        if d <= 0:
            continue
        x0, x1 = (r.left + 4, mid - 2) if half == 0 else (mid + 2, r.right - 5)
        for _ in range(d * 6):
            x, y = rng.randint(x0, x1), rng.randint(r.top + r.height // 3, r.bottom - 10)
            if not m.get_at((x, y)):
                continue
            dx, dy = rng.randint(-3, 3), rng.randint(1, 2)
            if not (0 <= x + dx < w and m.get_at((x + dx, min(h - 1, y + dy)))):
                continue
            pygame.draw.line(out, (30, 24, 30), (x, y), (x + dx, y + dy))
            out.set_at((x, max(0, y - 1)), (235, 235, 240))       # bare metal glint
    return out


# --------------------------------------------------------------------------
# puzzle blocks
# --------------------------------------------------------------------------
TCELL = 12                 # px per block in the boss's well


def _block(surf, color, x, y, c=TCELL):
    surf.fill(OUTLINE, (x, y, c, c))
    surf.fill(color, (x + 1, y + 1, c - 2, c - 2))
    surf.fill(shade(color, 1.35), (x + 1, y + 1, c - 2, 1))
    surf.fill(shade(color, 1.35), (x + 1, y + 1, 1, c - 2))
    surf.fill(shade(color, 0.65), (x + 1, y + c - 2, c - 2, 1))
    surf.fill(shade(color, 0.65), (x + c - 2, y + 1, 1, c - 2))
    if c >= 8:      # a glossy glint in the corner
        surf.fill(shade(color, 1.7), (x + 2, y + 2, 2, 1))


def piece_surface(cells, color, c=TCELL):
    mx = max(x for x, _ in cells) + 1
    my = max(y for _, y in cells) + 1
    s = pygame.Surface((mx * c, my * c), pygame.SRCALPHA)
    for x, y in cells:
        _block(s, color, x * c, y * c, c)
    return s


# --------------------------------------------------------------------------
# map sprites
# --------------------------------------------------------------------------
def car_topdown(color, roof=None):
    """Map car facing up, 14 x 22."""
    s = pygame.Surface((14, 22), pygame.SRCALPHA)
    for x, y in ((0, 3), (11, 3), (0, 15), (11, 15)):
        s.fill((20, 20, 24), (x, y, 3, 5))
    pygame.draw.rect(s, color, (1, 1, 12, 20), border_radius=3)
    pygame.draw.rect(s, roof or shade(color, 1.25), (3, 9, 8, 6))
    s.fill((60, 90, 130), (3, 5, 8, 3))
    s.fill((50, 70, 100), (3, 15, 8, 2))
    s.fill((255, 240, 150), (2, 1, 2, 1))
    s.fill((255, 240, 150), (10, 1, 2, 1))
    s.fill((220, 30, 30), (2, 20, 2, 1))
    s.fill((220, 30, 30), (10, 20, 2, 1))
    return _outlined(s)


def car_map_frames(color, roof=None):
    up = car_topdown(color, roof)
    frames = {}
    for d, deg in (("up", 0), ("left", 90), ("down", 180), ("right", -90)):
        img = pygame.transform.rotate(up, deg)
        frames[(d, 0)] = img
        frames[(d, 1)] = img
    return frames


def tetris_map_frames():
    """The boss on the map: an arcade cabinet with blocks on its screen."""
    s = pygame.Surface((18, 24), pygame.SRCALPHA)
    pygame.draw.rect(s, (70, 30, 110), (1, 2, 16, 21))
    s.fill((240, 60, 200), (1, 1, 16, 3))
    s.fill((16, 12, 26), (3, 6, 12, 9))
    cols = list(PIECE_COLORS.values())
    for i, (x, y) in enumerate(((4, 13), (6, 13), (8, 13), (8, 11), (12, 13), (12, 11), (10, 7))):
        s.fill(cols[i % len(cols)], (x, y, 2, 2))
    s.fill((40, 40, 50), (2, 16, 14, 3))
    s.fill((230, 40, 40), (5, 16, 2, 2))
    s.fill((60, 160, 255), (10, 16, 2, 2))
    s = _outlined(s)
    return {(d, k): s for d in ("up", "down", "left", "right") for k in (0, 1)}


# --------------------------------------------------------------------------
# stage + map tiles
# --------------------------------------------------------------------------
def make_car_stage(boss=False):
    rng = random.Random(33)
    s = pygame.Surface((W, H))
    top, bot = ((10, 4, 30), (120, 30, 110)) if boss else ((8, 10, 30), (60, 40, 90))   # boss: the Tetris yard sky
    for y in range(GROUND_Y):
        t = round(y / GROUND_Y * 10) / 10
        pygame.draw.line(s, mix(top, bot, t), (0, y), (W, y))
    for _ in range(40):
        s.set_at((rng.randrange(W), rng.randrange(70)), (200, 200, 230))
    # city skyline with lit windows
    for layer, (col, base) in enumerate((((30, 24, 52), 70), ((18, 14, 34), 96))):
        x = -10
        while x < W:
            bw = rng.randint(18, 36)
            top_y = base + rng.randint(-30, 20)
            pygame.draw.rect(s, col, (x, top_y, bw, GROUND_Y - top_y))
            for wy in range(top_y + 4, GROUND_Y - 30, 6):
                for wx in range(x + 3, x + bw - 3, 5):
                    if rng.random() < 0.3:
                        s.fill((240, 210, 120) if layer else (150, 130, 90), (wx, wy, 2, 2))
            x += bw + rng.randint(0, 6)
    # fence + street lamps
    for x in range(0, W, 4):
        pygame.draw.line(s, (40, 40, 56), (x, GROUND_Y - 34), (x + 6, GROUND_Y - 22))
        pygame.draw.line(s, (40, 40, 56), (x + 6, GROUND_Y - 34), (x, GROUND_Y - 22))
    pygame.draw.line(s, (70, 70, 90), (0, GROUND_Y - 35), (W, GROUND_Y - 35))
    for lx in (40, 280):
        pygame.draw.rect(s, (60, 60, 76), (lx, GROUND_Y - 90, 3, 90))
        pygame.draw.rect(s, (60, 60, 76), (lx - 8, GROUND_Y - 90, 12, 3))
        pygame.draw.rect(s, (255, 230, 150), (lx - 8, GROUND_Y - 87, 8, 2))
    # asphalt
    gnd = (52, 52, 60)
    pygame.draw.rect(s, gnd, (0, GROUND_Y, W, H - GROUND_Y))
    pygame.draw.line(s, (90, 90, 100), (0, GROUND_Y), (W, GROUND_Y))
    for x in range(0, W, 30):
        pygame.draw.rect(s, (220, 190, 60), (x, GROUND_Y + 11, 16, 2))
    for _ in range(60):
        s.set_at((rng.randrange(W), rng.randrange(GROUND_Y + 2, H)), shade(gnd, rng.choice((0.8, 1.2))))
    return s


def car_tiles(t, rng):
    """Turn the level tiles into a parking garage / scrapyard."""
    asphalt = (56, 56, 64)
    floors = []
    for v in range(4):
        s = pygame.Surface((16, 16))
        s.fill(asphalt)
        for _ in range(10):
            s.set_at((rng.randrange(16), rng.randrange(16)), shade(asphalt, rng.choice((0.8, 1.2))))
        if v == 3:
            pygame.draw.lines(s, shade(asphalt, 0.88), False, [(3, 4), (6, 7), (6, 11), (10, 13)])
        floors.append(s)
    t["floor"] = floors
    face = pygame.Surface((16, 16))
    face.fill((96, 96, 104))
    for y in (0, 8):
        pygame.draw.line(face, (70, 70, 78), (0, y), (15, y))
    pygame.draw.line(face, (70, 70, 78), (8, 0), (8, 7))
    pygame.draw.line(face, (70, 70, 78), (3, 8), (3, 15))
    for x in range(0, 16, 8):       # hazard stripe along the top
        face.fill((230, 190, 40), (x, 0, 4, 2))
        face.fill((30, 30, 30), (x + 4, 0, 4, 2))
    t["wall_face"] = face
    top = pygame.Surface((16, 16))
    top.fill((30, 30, 38))
    t["wall_top"] = top
    lamps = []
    for i in range(3):
        f = pygame.Surface((16, 16), pygame.SRCALPHA)
        pygame.draw.rect(f, (70, 70, 80), (7, 6, 2, 9))
        pygame.draw.rect(f, (255, 235, 160) if i != 2 else (240, 215, 140), (5, 3, 6, 3))
        lamps.append(f)
    t["torch"] = lamps
    cone = pygame.Surface((16, 16), pygame.SRCALPHA)
    pygame.draw.polygon(cone, (250, 120, 30), [(8, 3), (11, 13), (5, 13)])
    pygame.draw.line(cone, (240, 240, 240), (6, 9), (10, 9))
    pygame.draw.rect(cone, (200, 90, 20), (3, 13, 10, 2))
    t["lantern"] = cone
    tires = pygame.Surface((16, 16), pygame.SRCALPHA)
    for x, y in ((5, 10), (11, 10), (8, 5)):
        pygame.draw.circle(tires, (24, 24, 28), (x, y), 4)
        pygame.draw.circle(tires, (70, 70, 80), (x, y), 1)
    t["rubble"] = tires
    oil = pygame.Surface((16, 16), pygame.SRCALPHA)
    pygame.draw.ellipse(oil, (26, 26, 34), (2, 6, 12, 7))
    pygame.draw.ellipse(oil, (60, 40, 90), (5, 8, 3, 2))
    t["bones"] = oil
    spot = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.rect(spot, (230, 230, 230), (2, 2, 28, 28), 1)
    draw_text(spot, "P", 16, 12, (230, 230, 230), align="center")
    t["throne"] = spot
    return t


# --------------------------------------------------------------------------
# the bonus-round target
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# the bonus-round target
# --------------------------------------------------------------------------
class CarTarget:
    """Stands in for the opponent Fighter: Akuma faces it and hits it."""

    def __init__(self, enemy, power_hint=1.0):
        self.name = enemy.name
        self.boss = False
        self.x = W / 2
        self.y = float(GROUND_Y)
        self.side_max = enemy.side_hp
        self.side_hp = [enemy.side_hp, enemy.side_hp]
        self.max_hp = self.side_max * 2
        self.state = "stand"
        self.move = None
        self.airborne = False
        self.on_ground = True
        self.ko = False
        self.flash = 0
        self.wobble = 0
        self.vx = 0.0
        self.color = enemy.color
        self.model = getattr(enemy, "model", None)
        self.seed = enemy.seed
        self.half, self.height = CAR_W // 2 - 4, 36
        if self.model and car_sprite(self.model, 0) is not None:
            ax, ay, hw = car_anchor(self.model)
            top = car_sprite(self.model, 0).get_bounding_rect().top
            self.half, self.height = hw - 4, ay - top - 2
        self._cache = {}

    @property
    def hp(self):
        return self.side_hp[0] + self.side_hp[1]

    def phase(self):
        return None, None

    def hurtbox(self):
        if self.ko:
            return None
        return (self.x - self.half, self.y - self.height, self.half * 2, self.height)

    def stages(self):
        return tuple(_stage_of(h / self.side_max) for h in self.side_hp)

    def image(self):
        st = self.stages()
        painted = self.model is not None and car_sprite(self.model, 0) is not None
        key = (self.sheet_stage(),) + st if painted else st
        img = self._cache.get(key)
        if img is None:
            if painted:
                img = scarred(car_sprite(self.model, key[0]), st[0], st[1], self.seed)
            else:
                img = car_side(self.model, st[0], st[1], self.seed)
            self._cache[key] = img
        if painted:
            ax, ay, _ = car_anchor(self.model)
            return img, (ax, ay)
        return img, CAR_ANCHOR

    def sheet_stage(self):
        """The painted stage follows the HP left on the whole car."""
        return sheet_stage(self.hp / self.max_hp)


class Debris:
    def __init__(self, img, x, y, vx, vy, life=70):
        self.img, self.x, self.y, self.vx, self.vy, self.life = img, x, y, vx, vy, life

    def update(self):
        self.vy += 0.3
        self.x += self.vx
        self.y += self.vy
        if self.y > GROUND_Y + 4:
            self.y = GROUND_Y + 4
            self.vy *= -0.35
            self.vx *= 0.6
        self.life -= 1

    def draw(self, surf, sh):
        if self.life > 12 or self.life % 2:
            surf.blit(self.img, (round(self.x - self.img.get_width() / 2) + sh[0],
                                 round(self.y - self.img.get_height()) + sh[1]))

class CarScene:
    """Timed bonus round against a car that never fights back. The level's boss
    (enemy.boss) gets the Tetris fight instead: CarScene(...) hands back a TetrisScene."""

    def __new__(cls, game=None, enemy=None, *args, **kw):
        if cls is CarScene and getattr(enemy, "boss", False):
            cls = TetrisScene
        return super().__new__(cls)

    def __init__(self, game, enemy, akuma_hp, akuma_max, power=1.0, seed=None):
        F.init_shared()
        self.game = game
        self.enemy_ref = enemy
        self.rng = random.Random(seed)
        self.boss = False
        key = ("car", False)
        if key not in F._STAGES:
            F._STAGES[key] = make_car_stage()
        self.stage = F._STAGES[key]
        p = Fighter("AKUMA", F.AKUMA_LOOK, {}, akuma_max, walk=1.75, back_walk=1.35,
                    is_player=True, art=F._AKUMA_ART)
        p.hp = akuma_hp
        p.x, p.facing = 70.0, 1
        self.car = car = CarTarget(enemy)
        p.opponent = car
        self._tops = {}
        self.spin_hold = 0
        p.floor = self._floor
        p.ghost = self._spinning
        p.multi_hit = {"Tatsumaki": (6, 99)}    # spins through a car hitting it all the way
        self.projectiles = []
        car.projectiles = self.projectiles
        self.effects = []
        self.debris = []
        p.projectiles = self.projectiles
        p.effects = self._spawn_effect
        p.state = "intro"
        self.p = p
        self.power = power
        self.time_limit = CAR_TIME * FPS
        self.timer = self.time_limit
        self.intro_len = 50
        self.phase = "intro"
        self.t = 0
        self.end_t = 0
        self.hitstop = 0
        self.shake = 0
        self.combo = 0
        self.combo_show = 0
        self.last_hit = -99
        self.hint = 0
        self.banner = None
        self.menu = PauseMenu(game, F.CONTROLS)
        self.lag = car.hp
        self.p_lag = p.hp
        self.result = None

    # --------------------------------------------------------------------
    def _spawn_effect(self, kind, x, y):
        if kind == "dust":
            self.effects.append(F.Effect(F.DUST, x, y - 4, 4))

    def _intent(self, inp):
        return dict(left=inp.held("left"), right=inp.held("right"), up=inp.held("up"),
                    down=inp.held("down"), punch=inp.pressed("punch"), kick=inp.pressed("kick"),
                    special=inp.pressed("special"))

    @property
    def paused(self):
        return self.menu.open

    def update(self, inp):
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.phase == "fight" and self.menu.toggle(inp):
            return
        self.t += 1
        p, car = self.p, self.car
        self.lag = max(car.hp, self.lag - 0.8) if self.lag > car.hp else car.hp
        self.p_lag = max(p.hp, self.p_lag - 0.6) if self.p_lag > p.hp else p.hp
        for v in ("shake", "combo_show", "hint"):
            if getattr(self, v):
                setattr(self, v, getattr(self, v) - 1)
        if p.flash:
            p.flash -= 1
        if car.flash:
            car.flash -= 1
        if car.wobble:
            car.wobble -= 1
        for fx in self.effects:
            fx.update()
        self.effects = [fx for fx in self.effects if fx.alive]
        for d in self.debris:
            d.update()
        self.debris = [d for d in self.debris if d.life > 0]
        if self.banner:
            self.banner[1] -= 1
            if self.banner[1] <= 0:
                self.banner = None

        if self.phase == "intro":
            p.update({})
            if self.t == self.intro_len - 18:
                audio.play("fight")
            if self.t >= self.intro_len:
                self.phase = "fight"
                p._to_stand()
            return
        if self.hitstop > 0:
            self.hitstop -= 1
            if self.phase == "fight":
                p.feed_buffer(self._intent(inp))
            return
        if self.phase in ("won", "escape", "lost"):
            self.end_t += 1
            p.update({})
            if self.phase == "escape":
                car.vx = min(4.0, car.vx + 0.15)
                car.x += car.vx
            if self.phase == "won" and self.end_t == 40:
                p._to_stand()
                p.state = "win"
            skip = self.end_t > 30 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= 90 or skip:
                self.result = {"won": "win", "escape": "escape", "lost": "lose"}[self.phase]
                self.game.end_fight(self, self.result, max(0, p.hp))
            return

        self.timer -= 1
        p.update(self._intent(inp))
        self._hold_tatsu()
        self._projectiles()
        self._melee()
        if car.hp <= 0:
            self._destroyed()
        elif self.timer <= 0:
            self._time_over()

    def _floor(self, x):
        """Car roof under x (the top of the car's current, dented drawing)."""
        car = self.car
        if car.ko or self.phase == "escape":
            return float(GROUND_Y)
        img, (ax, ay) = car.image()
        tops = self._tops.get(id(img))
        if tops is None:
            m = pygame.mask.from_surface(img)
            w, h = img.get_size()
            col = []
            for cx in range(w):
                top = next((cy for cy in range(h) if m.get_at((cx, cy))), None)
                col.append(GROUND_Y if top is None else car.y - ay + top)
            # feet have width: the highest point under them counts
            tops = [min(col[max(0, i - FOOT):i + FOOT + 1]) for i in range(w)]
            self._tops = {id(img): tops}
            self._tops_img = img        # keep it alive so id() stays unique
        i = round(x - car.x + ax)
        return float(tops[i]) if 0 <= i < len(tops) else float(GROUND_Y)

    def _spinning(self):
        p = self.p
        return (p.state == "move" and p.move is not None and p.move.get("name") == "Tatsumaki"
                and p.phase()[0] != "recovery")

    def _hold_tatsu(self):
        """A hurricane kick ending inside the car keeps spinning until it comes out."""
        p = self.p
        if not self._spinning() or p.y <= self._floor(p.x) + 4:
            self.spin_hold = 0
            return
        last = 34
        if p.move_t >= last - 1 and self.spin_hold < 90:
            self.spin_hold += 1
            p.move_t -= 1
            p.last_hit_t -= 1
            if abs(p.vx) < 1.5:
                p.vx = 2.0 * p.facing

    def _side_of(self, x):
        return 0 if x < self.car.x else 1

    def _car_drawn(self):
        img, (ax, ay) = self.car.image()
        return img, self.car.x - ax, self.car.y - ay

    def _projectiles(self):
        car = self.car
        for pr in self.projectiles:
            pr.update()
            if pr.alive and car.hurtbox() and contact(pr.area(), image_area(*self._car_drawn())):
                pr.alive = False
                side = 0 if pr.vx > 0 else 1
                self._hit(side, pr.dmg * self.power, (pr.x, pr.y), heavy=True)
        self.projectiles[:] = [pr for pr in self.projectiles if pr.alive]

    def _melee(self):
        p, car = self.p, self.car
        hu = car.hurtbox()
        strike = p.strike_area() if hu else None
        if strike is None:
            return
        # the fist or foot has to touch the car's actual bodywork
        img, (ax, ay) = car.image()
        at = contact(strike, image_area(img, car.x - ax, car.y - ay))
        if at is None and p.y < GROUND_Y - 6:
            # standing (or landing) on the car: stomps and low kicks reach it
            at = contact(strike, rect_area((hu[0], hu[1] - 40, hu[2], hu[3] + 40)))
        if at is None:
            return
        m = p.move
        p.hits_done += 1
        p.last_hit_t = p.move_t
        if m.get("cat") in ("punch", "kick"):
            p.cancel = CANCEL_WINDOW
        cx, cy = at
        dmg = m["dmg"] * self.power
        if m.get("name") == "Tatsumaki":
            dmg *= TATSU_CAR_DMG       # it hits many times on the way through
        self._hit(self._side_of(p.x), dmg, (cx, cy), heavy=m["dmg"] >= HIT)
        if m.get("bounce"):
            p.vy = -2.2
            p.vx = -0.4 * p.facing
            p.bounced = True

    def _hit(self, side, dmg, at, heavy=False):
        car = self.car
        self.effects.append(F.Effect(F.SPARK_HIT, at[0], at[1], 2))
        if car.side_hp[side] <= 0:
            # that side is already scrap: tell the player to go round
            self.hint = 90
            audio.play("block")
            self.hitstop = max(self.hitstop, 4)
            return
        before = car.stages()[side]
        before_sheet = car.sheet_stage()
        car.side_hp[side] = max(0, car.side_hp[side] - round(dmg))
        car.flash = 6
        car.wobble = 8
        if self.t - self.last_hit < 50:
            self.combo += 1
        else:
            self.combo = 1
        self.last_hit = self.t
        if self.combo >= 2:
            self.combo_show = 70
        audio.play("heavy" if heavy else "hit")
        self.hitstop = max(self.hitstop, HITSTOP + (3 if heavy else 0))
        self.shake = max(self.shake, 6 if heavy else 3)
        if car.stages()[side] != before or car.sheet_stage() != before_sheet:
            audio.play("sweep")
            self._shards(side)
            if car.hp > 0:
                self._boom("explode_small", at[0], at[1], 28)

    def _boom(self, kind, x, y, height, rate=4):
        fx = explosion(kind, x, y, height, rate)
        if fx is not None:
            self.effects.append(fx)

    def _shards(self, side, n=10):
        car = self.car
        for _ in range(n):
            img = pygame.Surface((2, 2))
            img.fill(self.rng.choice(((200, 230, 255), (150, 190, 220), car.color, shade(car.color, 0.6))))
            x = car.x + (-24 if side == 0 else 24) + self.rng.uniform(-14, 14)
            away = -1 if side == 0 else 1
            self.debris.append(Debris(img, x, car.y - 30, away * self.rng.uniform(0.3, 2.5),
                                      self.rng.uniform(-4, -1), 60))

    def _destroyed(self):
        car = self.car
        car.ko = True
        self.phase = "won"
        self.end_t = 0
        self.hitstop = 14
        self.shake = 16
        audio.play("ko")
        for side in (0, 1):
            self._shards(side, 16)
        # the tank goes up: one big fireball over the car, a smaller one each end
        top = car.y - car.height
        self._boom("explode_large", car.x, top + 4, 64, 5)
        self._boom("explode_medium", car.x - car.half * 0.7, top + 14, 40)
        self._boom("explode_medium", car.x + car.half * 0.7, top + 16, 36, 5)
    def _time_over(self):
        p = self.p
        audio.play("ko")
        p.hp = max(1, p.hp - TIMEOUT_DMG)
        p.flash = 20
        self.phase = "escape"
        self.end_t = 0
        p.cancel = 0

    # --------------------------------------------------------------------
    def draw(self, surf):
        sh = (0, 0)
        if self.shake:
            sh = (self.rng.choice((-2, -1, 1, 2)), self.rng.choice((-1, 0, 1)))
        surf.blit(self.stage, sh)
        car = self.car
        # a painted car stays on the street as a smoking wreck; the old drawn ones vanish
        painted = car.model is not None and car_sprite(car.model, 0) is not None
        if not (car.ko and self.end_t > 50 and not painted):
            img, (ax, ay) = car.image()
            wob = (1 if car.wobble % 4 < 2 else -1) if car.wobble else 0
            x = round(car.x) - ax + sh[0] + wob
            y = round(car.y) - ay + sh[1]
            pygame.draw.ellipse(surf, (20, 18, 26), (x + 6, GROUND_Y - 3 + sh[1], img.get_width() - 12, 6))
            if car.flash and car.flash % 3 == 0:
                img = pygame.mask.from_surface(img).to_surface(setcolor=(255, 255, 255, 255),
                                                               unsetcolor=(0, 0, 0, 0))
            surf.blit(img, (x, y))
            self._smoke(surf, sh)
        self.p.draw(surf, sh)
        for pr in self.projectiles:
            pr.draw(surf, sh)
        for d in self.debris:
            d.draw(surf, sh)
        for fx in self.effects:
            fx.draw(surf, sh)
        self._hud(surf)

    def _smoke(self, surf, sh):
        car = self.car
        for side, st in enumerate(car.stages()):
            if st < 2:
                continue
            bx = car.x + (-30 if side == 0 else 30)
            for k in range(3 if st == 3 else 2):
                ph = (self.t + k * 17 + side * 9) % 50
                r = 2 + ph // 12
                c = (90, 90, 100) if st == 2 else (50, 46, 56)
                pygame.draw.circle(surf, c, (round(bx + k * 4 - ph * 0.2) + sh[0],
                                             round(car.y - car.height + 2 - ph * 0.8) + sh[1]), r)
            if st == 3 and (self.t // 3) % 2:
                pygame.draw.circle(surf, (255, 150, 40), (round(bx) + sh[0], round(car.y - car.height + 6) + sh[1]), 3)

    def _bar(self, surf, x, y, w, val, lag, mx, right, col=(250, 210, 40)):
        pygame.draw.rect(surf, (10, 6, 14), (x - 1, y - 1, w + 2, 10))
        pygame.draw.rect(surf, (90, 16, 20), (x, y, w, 8))
        lw = int(w * lag / mx)
        cw = int(w * val / mx)
        if right:
            pygame.draw.rect(surf, (230, 60, 40), (x + w - lw, y, lw, 8))
            pygame.draw.rect(surf, col, (x + w - cw, y, cw, 8))
        else:
            pygame.draw.rect(surf, (230, 60, 40), (x, y, lw, 8))
            pygame.draw.rect(surf, col, (x, y, cw, 8))

    def _hud(self, surf):
        p, car = self.p, self.car
        surf.blit(F._PORTRAIT, (4, 4))
        pygame.draw.rect(surf, (10, 6, 14), (3, 3, F._PORTRAIT.get_width() + 2, F._PORTRAIT.get_height() + 2), 1)
        bw = F.BAR_W
        self._bar(surf, 40, 10, bw, p.hp, self.p_lag, p.max_hp, False)
        self._bar(surf, W - 8 - bw, 10, bw, car.hp, self.lag, car.max_hp, True)
        draw_text(surf, "AKUMA", 40, 21, (255, 90, 90))
        draw_text(surf, car.name, W - 8, 21, (220, 220, 255), align="right")
        # each side's own little gauge
        sw = bw // 2 - 4
        for side in (0, 1):
            x = W - 8 - bw + side * (sw + 8)
            hp = car.side_hp[side]
            self._bar(surf, x, 31, sw, hp, hp, car.side_max, False,
                      col=(120, 220, 255) if hp else (90, 90, 100))
        draw_text(surf, "L", W - 8 - bw - 7, 31, (180, 180, 200))
        draw_text(surf, "R", W - 4, 31, (180, 180, 200), align="right")
        secs = max(0, (self.timer + FPS - 1) // FPS)
        col = (255, 60, 40) if secs <= 5 and (self.t // 8) % 2 else (255, 230, 120)
        draw_text(surf, "%02d" % secs, W // 2, 6, col, scale=2, align="center")
        if self.phase == "intro":
            if self.t < self.intro_len - 18:
                draw_text(surf, "BONUS ROUND", W // 2, 64, (255, 220, 80),
                          scale=2, align="center")
                draw_text(surf, car.name, W // 2, 84, (255, 255, 255), align="center")
                draw_text(surf, "WRECK BOTH SIDES BEFORE TIME RUNS OUT", W // 2, 96,
                          (200, 200, 230), align="center")
            else:
                draw_text(surf, "SMASH IT!", W // 2, 70, (255, 60, 40), scale=3, align="center")
        if self.combo_show and self.combo >= 2:
            draw_text(surf, "%d HIT COMBO" % self.combo, 6, 46, (255, 200, 40), scale=2)
        if self.hint and self.phase == "fight":
            draw_text(surf, "THIS SIDE IS WRECKED! JUMP OVER!", W // 2, 52, (255, 255, 255), align="center")
        if self.banner:
            draw_text(surf, self.banner[0], W // 2, 64, (255, 80, 60), scale=2, align="center")
        if self.phase == "won" and self.end_t > 10:
            draw_text(surf, "DESTROYED!", W // 2, 60, (255, 220, 60), scale=3, align="center")
        if self.phase == "escape":
            draw_text(surf, "TIME OVER", W // 2, 56, (255, 60, 40), scale=3, align="center")
            draw_text(surf, "THE CAR GOT AWAY  -%d HP" % TIMEOUT_DMG, W // 2, 84, (255, 255, 255),
                      align="center")
        if self.phase == "lost" and self.end_t > 10:
            draw_text(surf, "AKUMA FALLS...", W // 2, 64, (255, 255, 255), scale=2, align="center")
        if self.menu.open:
            self.menu.draw(surf)


# --------------------------------------------------------------------------
# the boss: THE TETRIS MASTER
# --------------------------------------------------------------------------
# He plays the falling-block puzzle at an arcade cabinet on the left; his well
# fills the right of the stage. The pieces are real blocks: they fall on Akuma,
# lock into a stack he can stand on, and break when he hits them.
COLS, ROWS = 10, 9
WELL_W, WELL_H = COLS * TCELL, ROWS * TCELL
WELL_X = STAGE_RIGHT - WELL_W      # 186: the well's right wall is the stage edge
WELL_TOP = GROUND_Y - WELL_H       # 50
WELL_COL = COLS - 1                # the column he keeps open for the long I piece
BOSS_HP = 40                       # blocks to break; a piece smashed in mid-air counts SMASH_HP
SMASH_HP = 2
BLOCK_HP = 2                       # a punch cracks a block, a kick or a special breaks it
BOSS_TIME = 60                     # seconds; running out costs Akuma BOSS_TIMEOUT_DMG
BOSS_TIMEOUT_DMG = 30
DROP_DMG = 12                      # a falling piece landing on Akuma
CLEAR_DMG = {1: 0, 2: 0, 3: 10, 4: 40}       # his line clears hit Akuma: a TETRIS hits hard
CLEAR_NAMES = {1: "SINGLE", 2: "DOUBLE", 3: "TRIPLE!", 4: "TETRIS!"}
GRAV, GRAV_MAD = 18, 13            # frames per row while he lines a piece up
SOFT, SOFT_MAD = 5, 4              # frames per row once it is lined up (soft drop)
SHIFT = 6                          # frames per sideways step or turn
ARE, ARE_MAD = 26, 18              # pause before the next piece
CLEAR_FLASH = 24                   # full rows flash this long, then vanish
LOCK_DELAY = 6                     # gravity ticks a resting piece can still be slid along
TOPOUT_DMG = 6                     # if he ever tops out his board is wiped and he loses this
MASTER_X = 34                      # his feet, at the cabinet on the left (background)
CAB_X = MASTER_X + 12              # the cabinet's left edge


def _width(cells):
    return max(c for c, _ in cells) + 1


def _place(occ, cells, col, row):
    """The well after dropping `cells` at (col, row) and clearing full rows:
    (new occupancy, lines cleared, cells in the open column, landing height), or None if it tops out."""
    occ = [line[:] for line in occ]
    for c, r in cells:
        if row + r < 0:
            return None
        occ[row + r][col + c] = True
    full = [r for r in range(ROWS) if all(occ[r])]
    if full:
        occ = [[False] * COLS for _ in full] + [occ[r] for r in range(ROWS) if r not in full]
    land = ROWS - row - sum(r for _, r in cells) / len(cells)     # how high it sits
    return occ, len(full), sum(1 for c, _ in cells if col + c == WELL_COL), land


def _score(occ, lines, in_well, land=0.0):
    """How much the Tetris Master likes a board: flat and hole-free, the right-hand
    column kept open, rows lined up for it, and above all a 4-line clear."""
    heights, holes = [], 0
    for c in range(COLS):
        h = 0
        for r in range(ROWS):
            if occ[r][c]:
                if not h:
                    h = ROWS - r
            elif h:
                holes += 1
        heights.append(h)
    play = heights[:WELL_COL]
    bump = sum(abs(a - b) for a, b in zip(play, play[1:]))
    tallest = max(heights)
    ready = sum(1 for r in range(ROWS) if not occ[r][WELL_COL]
                and all(occ[r][c] for c in range(COLS) if c != WELL_COL))
    score = (-0.5 * sum(play) - 4.0 * holes - 0.35 * bump + 1.2 * ready - 1.0 * land
             - 3.0 * max(0, tallest - (ROWS - 4)) - 2.0 * heights[WELL_COL])
    if lines >= 4:
        score += 60
    else:   # burning the well on less is a waste, unless the height penalty says otherwise
        score -= 3 * lines + 4 * in_well
    return score


def _placements(occ, cells_list, spawn_row):
    """Every (rot, col, row) a piece can be dropped to straight down from the top."""
    def fits(cells, col, row):
        for c, r in cells:
            cc, rr = col + c, row + r
            if cc < 0 or cc >= COLS or rr >= ROWS or (rr >= 0 and occ[rr][cc]):
                return False
        return True
    for rot, cells in enumerate(cells_list):
        for col in range(COLS - _width(cells) + 1):
            if not fits(cells, col, spawn_row):
                continue
            row = spawn_row
            while fits(cells, col, row + 1):
                row += 1
            yield rot, col, row


class Piece:
    """The piece he is steering: (rot, col) is where he wants it."""

    def __init__(self, kind):
        self.kind = kind
        self.color = PIECE_COLORS[kind]
        self.rots = _rotations(PIECES[kind])
        self.rot = 0
        self.col = (COLS - 1 - _width(self.rots[0])) // 2
        self.row = -1
        self.trot, self.tcol = 0, self.col
        self.fall_t = GRAV
        self.shift_t = SHIFT + 4      # a beat to "think" before moving
        self.stuck = 0                # gravity ticks spent resting on the stack before it locks

    @property
    def cells(self):
        return self.rots[self.rot]

    @property
    def x(self):
        return WELL_X + (self.col + _width(self.cells) / 2) * TCELL


class _Aim:
    """Akuma's 'opponent' while he fights the stack: the point he turns to face."""
    state, move, airborne, on_ground, ko = "stand", None, False, True, False

    def __init__(self):
        self.x, self.y = WELL_X + WELL_W / 2, float(GROUND_Y)

    def hurtbox(self):
        return None

    def phase(self):
        return None, None


def draw_master(surf, x, g, pose, t):
    """THE TETRIS MASTER, side on, facing his cabinet on the right."""
    skin, hood, jeans, cap = (236, 186, 146), (210, 44, 70), (44, 64, 128), (40, 50, 210)
    slump = 3 if pose == "lose" else 0
    # legs and shoes
    surf.fill(jeans, (x - 5, g - 16, 4, 15))
    surf.fill(jeans, (x + 1, g - 16, 4, 15))
    surf.fill((235, 235, 235), (x - 6, g - 2, 6, 2))
    surf.fill((235, 235, 235), (x + 1, g - 2, 6, 2))
    # hoodie
    pygame.draw.rect(surf, hood, (x - 6, g - 33 + slump, 12, 18), border_radius=2)
    surf.fill(shade(hood, 0.7), (x - 7, g - 32 + slump, 3, 8))          # the hood down his back
    surf.fill(shade(hood, 0.7), (x - 6, g - 17, 12, 2))
    # head, backwards cap, an eye on the screen
    hx, hy = x - 4 + slump, g - 42 + slump * 2
    surf.fill(skin, (hx, hy, 9, 9))
    surf.fill(cap, (hx - 1, hy - 2, 10, 4))
    surf.fill(cap, (hx - 4, hy, 4, 2))                                     # brim at the back
    surf.fill((20, 20, 20), (hx + 6, hy + (5 if pose == "lose" else 3), 2, 1 if pose == "lose" else 2))
    if pose == "mad":
        surf.fill((20, 20, 20), (hx + 5, hy + 2, 3, 1))                    # angry brow
    if pose == "cheer":
        surf.fill((120, 20, 20), (hx + 6, hy + 6, 2, 2))                   # yelling
    sx, sy = x + 2, g - 30 + slump
    def arm(ex, ey):
        pygame.draw.line(surf, hood, (sx, sy), (ex, ey), 3)
        surf.fill(skin, (ex - 1, ey - 1, 3, 3))
    if pose == "cheer":
        jump = 1 if (t // 5) % 2 else 0
        arm(x - 4, g - 50 - jump)
        arm(x + 8, g - 51 + jump)
    elif pose == "mad":
        arm(x + 11, g - 27)
        arm(x + 9 + (t // 3) % 2 * 2, g - 46)                               # shaking his fist
    elif pose == "lose":
        arm(x + 4, g - 16)
    else:   # mashing the stick and buttons
        arm(x + 11, g - 27 - ((t // 6) % 2))
        arm(x + 9, g - 26 + ((t // 4) % 2))


def make_tetris_stage():
    s = make_car_stage(True)
    # the giant well on the right
    panel = pygame.Surface((WELL_W, WELL_H), pygame.SRCALPHA)
    panel.fill((10, 6, 26, 215))
    for gx in range(0, WELL_W, TCELL):
        pygame.draw.line(panel, (110, 80, 190, 70), (gx, 0), (gx, WELL_H))
    for gy in range(0, WELL_H, TCELL):
        pygame.draw.line(panel, (110, 80, 190, 50), (0, gy), (WELL_W, gy))
    s.blit(panel, (WELL_X, WELL_TOP))
    s.fill((22, 14, 40), (STAGE_RIGHT + 3, WELL_TOP - 6, W - STAGE_RIGHT, GROUND_Y - WELL_TOP + 6))
    for x in (WELL_X - 3, STAGE_RIGHT):
        s.fill((120, 30, 110), (x - 1, WELL_TOP - 6, 5, GROUND_Y - WELL_TOP + 6))
        s.fill((255, 90, 220), (x, WELL_TOP - 6, 3, GROUND_Y - WELL_TOP + 6))
        s.fill((255, 210, 250), (x + 1, WELL_TOP - 6, 1, GROUND_Y - WELL_TOP + 6))
    # his cabinet, its screen drawn live; a cable runs from it to the well
    g = GROUND_Y
    pygame.draw.line(s, (20, 16, 30), (CAB_X + 26, g - 2), (WELL_X - 4, g - 2), 2)
    pygame.draw.rect(s, (64, 26, 104), (CAB_X, g - 74, 26, 74))
    s.fill((92, 44, 140), (CAB_X, g - 74, 3, 74))
    s.fill((36, 14, 60), (CAB_X + 23, g - 74, 3, 74))
    s.fill((255, 70, 200), (CAB_X - 2, g - 80, 30, 8))
    s.fill((255, 190, 240), (CAB_X - 2, g - 80, 30, 1))
    for i, k in enumerate("TOIJ"):
        s.fill(PIECE_COLORS[k], (CAB_X + 3 + i * 6, g - 77, 4, 3))
    s.fill((12, 10, 18), (CAB_X + 1, g - 64, 24, 22))
    s.fill((30, 30, 44), (CAB_X - 8, g - 40, 12, 5))                      # control panel
    s.fill((220, 40, 40), (CAB_X - 6, g - 45, 3, 3))                      # stick
    s.fill((70, 70, 80), (CAB_X - 5, g - 42, 1, 2))
    s.fill((60, 170, 255), (CAB_X - 1, g - 41, 2, 1))
    s.fill((30, 20, 44), (CAB_X + 4, g - 20, 18, 10))                     # coin door
    s.fill((255, 200, 60), (CAB_X + 8, g - 17, 3, 3))
    s.fill((255, 200, 60), (CAB_X + 15, g - 17, 3, 3))
    return s


_TSTAGE = []


class TetrisScene(CarScene):
    """Level 3 boss: break THE TETRIS MASTER's blocks before he scores a TETRIS."""

    def __init__(self, game, enemy, akuma_hp, akuma_max, power=1.0, seed=None):
        F.init_shared()
        self.game = game
        self.enemy_ref = enemy
        self.rng = random.Random(seed)
        self.boss = True
        self.name = enemy.name
        if not _TSTAGE:
            _TSTAGE.append(make_tetris_stage())
        self.stage = _TSTAGE[0]
        p = Fighter("AKUMA", F.AKUMA_LOOK, {}, akuma_max, walk=1.75, back_walk=1.35,
                    is_player=True, art=F._AKUMA_ART)
        p.hp = akuma_hp
        p.x, p.facing = 112.0, 1
        self.aim = _Aim()
        p.opponent = self.aim
        p.floor = self._floor
        p.multi_hit = {"Tatsumaki": (6, 99)}
        self.projectiles = []
        self.effects = []
        self.debris = []
        self.waves = []               # TETRIS shockwaves: [x, y, radius]
        p.projectiles = self.projectiles
        p.effects = self._spawn_effect
        p.state = "intro"
        self.p = p
        self.power = power
        self.time_limit = BOSS_TIME * FPS
        self.timer = self.time_limit
        self.intro_len = 100
        self.phase = "intro"
        self.t = self.end_t = self.hitstop = self.shake = self.flash = 0
        self.combo = self.combo_show = self.hint = 0
        self.last_hit = -99
        self.banner = None            # [text, frames left, color]
        self.max_hp = self.hp = BOSS_HP
        self.lag = self.hp
        self.p_lag = p.hp
        self.grid = [[None] * COLS for _ in range(ROWS)]
        self._runs = None
        self.lines = 0
        self.tetrises = 0
        self.piece = None
        self.are = 30
        self.clearing = None          # [full rows, frames left]
        self.mood, self.mood_t = "play", 0
        self.menu = PauseMenu(game, F.CONTROLS)
        self.result = None
        self._garbage()
        self.bag = []
        self.next = self._draw_kind()

    # ---- the board ---------------------------------------------------------
    def _draw_kind(self):
        # he's the master: with rows lined up the long I piece has a way of turning up
        if len(self.ready_rows()) >= 3 and "I" in self.bag and self.rng.random() < 0.4:
            self.bag.remove("I")
            return "I"
        if not self.bag:
            self.bag = list(PIECES)
            self.rng.shuffle(self.bag)
        return self.bag.pop()

    def _garbage(self):
        """He's mid-game when Akuma walks in: two rows ready for a TETRIS, a few blocks on top."""
        cols = list(PIECE_COLORS.values())
        for r in (ROWS - 1, ROWS - 2):
            for c in range(WELL_COL):
                self.grid[r][c] = [self.rng.choice(cols), BLOCK_HP]
        for c in range(4):
            self.grid[ROWS - 3][c] = [PIECE_COLORS["L" if c < 3 else "J"], BLOCK_HP]
        self._changed()

    def _changed(self):
        self._runs = None

    def cell_rect(self, c, r):
        return (WELL_X + c * TCELL, WELL_TOP + r * TCELL, TCELL, TCELL)

    def cells(self):
        return [(c, r) for r in range(ROWS) for c in range(COLS) if self.grid[r][c] is not None]

    def fits(self, cells, col, row):
        for c, r in cells:
            cc, rr = col + c, row + r
            if cc < 0 or cc >= COLS or rr >= ROWS:
                return False
            if rr >= 0 and self.grid[rr][cc] is not None:
                return False
        return True

    def drop_row(self, cells, col, row):
        while self.fits(cells, col, row + 1):
            row += 1
        return row

    def ready_rows(self):
        """Rows full but for the open column: one I piece away from clearing."""
        return [r for r in range(ROWS) if self.grid[r][WELL_COL] is None
                and all(self.grid[r][c] is not None for c in range(COLS) if c != WELL_COL)]

    def _choose(self, pc):
        """Pick where this piece goes, looking one piece ahead (the NEXT box)."""
        occ = [[v is not None for v in line] for line in self.grid]
        nxt = _rotations(PIECES[self.next])
        best, pick = None, (0, pc.col)
        for rot, col, row in _placements(occ, pc.rots, pc.row):
            first = _place(occ, pc.rots[rot], col, row)
            if first is None:
                continue
            score = _score(*first)
            occ1 = first[0]
            ahead = None
            for r2, c2, row2 in _placements(occ1, nxt, -1):
                second = _place(occ1, nxt[r2], c2, row2)
                if second is not None:
                    v = _score(*second)
                    ahead = v if ahead is None else max(ahead, v)
            score = score * 0.4 + (ahead if ahead is not None else score - 50) * 0.6
            score += self.rng.uniform(0, 0.15)
            if best is None or score > best:
                best, pick = score, (rot, col)
        pc.trot, pc.tcol = pick

    # ---- Akuma on the stack -------------------------------------------------
    def _runs_of(self):
        if self._runs is None:
            runs = []
            for c in range(COLS):
                col, r = [], 0
                while r < ROWS:
                    if self.grid[r][c] is None:
                        r += 1
                        continue
                    top = r
                    while r < ROWS and self.grid[r][c] is not None:
                        r += 1
                    col.append((WELL_TOP + top * TCELL, WELL_TOP + r * TCELL))
                runs.append(col)
            self._runs = runs
        return self._runs

    def _floor(self, x):
        """Floor under x for Akuma's feet: the top of the block pile he stands on,
        or of one right at his feet (so the stack is a wall he can't walk into).
        Blocks hanging above his head don't count: he can walk under them."""
        feet = self.p.y - STEP_UP
        best = float(GROUND_Y)
        runs = self._runs_of()
        c0 = math.floor((x - FOOT - WELL_X) / TCELL)
        c1 = math.floor((x + FOOT - 1 - WELL_X) / TCELL)
        for c in range(max(0, c0), min(COLS - 1, c1) + 1):
            for top, bot in runs[c]:
                if top <= feet < bot or top >= feet:
                    best = min(best, float(top))
                    break
        return best

    def _spinning(self):
        return False

    def _face(self):
        """Akuma turns to the nearest block at body height (else the falling piece)."""
        p = self.p
        best, bx = None, None
        for c, r in self.cells():
            x, y, w, h = self.cell_rect(c, r)
            if y + h <= p.y - 70 or y >= p.y - 2:
                continue
            d = abs(x + w / 2 - p.x)
            if best is None or d < best:
                best, bx = d, x + w / 2
        if bx is None:
            bx = self.piece.x if self.piece else WELL_X + WELL_W / 2
        self.aim.x = bx

    # ---- update ------------------------------------------------------------
    def update(self, inp):
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.phase == "fight" and self.menu.toggle(inp):
            return
        self.t += 1
        p = self.p
        self.lag = max(self.hp, self.lag - 0.3) if self.lag > self.hp else self.hp
        self.p_lag = max(p.hp, self.p_lag - 0.6) if self.p_lag > p.hp else p.hp
        for v in ("shake", "combo_show", "flash", "mood_t"):
            if getattr(self, v):
                setattr(self, v, getattr(self, v) - 1)
        if not self.mood_t and self.phase == "fight":
            self.mood = "play"
        if p.flash:
            p.flash -= 1
        for fx in self.effects:
            fx.update()
        self.effects = [fx for fx in self.effects if fx.alive]
        for d in self.debris:
            d.update()
        self.debris = [d for d in self.debris if d.life > 0]
        for wv in self.waves:
            wv[2] += 7
        self.waves = [wv for wv in self.waves if wv[2] < 360]
        if self.banner:
            self.banner[1] -= 1
            if self.banner[1] <= 0:
                self.banner = None

        if self.phase == "intro":
            p.update({})
            if self.t == self.intro_len - 18:
                audio.play("fight")
            if self.t >= self.intro_len:
                self.phase = "fight"
                p._to_stand()
            return
        if self.hitstop > 0:
            self.hitstop -= 1
            if self.phase == "fight":
                p.feed_buffer(self._intent(inp))
            return
        if self.phase in ("won", "lost"):
            self.end_t += 1
            p.update({})
            if self.phase == "won" and self.end_t == 40:
                p._to_stand()
                p.state = "win"
            skip = self.end_t > 30 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= 150 or skip:
                self.result = "win" if self.phase == "won" else "lose"
                self.game.end_fight(self, self.result, max(0, p.hp))
            return

        self.timer -= 1
        self._face()
        p.update(self._intent(inp))
        self._projectiles()
        self._melee()
        self._play()
        if self.hp <= 0:
            self._beaten()
        elif p.hp <= 0:
            self._lose()
        elif self.timer <= 0:
            self._time_over()

    # ---- Akuma's attacks ---------------------------------------------------
    def _piece_rects(self, pc=None, shrink=0):
        pc = pc or self.piece
        out = []
        for c, r in pc.cells:
            x, y, w, h = self.cell_rect(pc.col + c, pc.row + r)
            out.append((x + shrink, y + shrink, w - 2 * shrink, h - 2 * shrink))
        return out

    def _touched_cells(self, area):
        busy = set(self.clearing[0]) if self.clearing else ()
        return [(c, r) for c, r in self.cells()
                if r not in busy and contact(area, rect_area(self.cell_rect(c, r)))]

    def _projectiles(self):
        for pr in self.projectiles:
            pr.update()
            if not pr.alive:
                continue
            a = pr.area()
            if self.piece and any(contact(a, rect_area(rc)) for rc in self._piece_rects()):
                pr.alive = False
                self._smash_piece()
                continue
            hit = self._touched_cells(a)
            if hit:
                hit.sort(key=lambda cr: abs(self.cell_rect(*cr)[0] + TCELL / 2 - pr.x))
                self._damage_block(*hit[0], BLOCK_HP, heavy=True)
                pr.pierce = getattr(pr, "pierce", 2) - 1       # a fireball goes through two blocks
                if pr.pierce <= 0:
                    pr.alive = False
        self.projectiles[:] = [pr for pr in self.projectiles if pr.alive]

    def _connect(self, m):
        p = self.p
        p.hits_done += 1
        p.last_hit_t = p.move_t
        if m.get("cat") in ("punch", "kick"):
            p.cancel = CANCEL_WINDOW
        if m.get("bounce"):
            p.vy = -2.2
            p.vx = -0.4 * p.facing
            p.bounced = True

    def _melee(self):
        p = self.p
        strike = p.strike_area()
        if strike is None:
            return
        m = p.move
        if self.piece and any(contact(strike, rect_area(rc)) for rc in self._piece_rects()):
            self._connect(m)
            self._smash_piece()
            return
        touched = self._touched_cells(strike)
        if not touched:
            return
        self._connect(m)
        ax, ay = p.x + p.facing * 18, p.y - 30
        touched.sort(key=lambda cr: (self.cell_rect(*cr)[0] + TCELL / 2 - ax) ** 2
                     + (self.cell_rect(*cr)[1] + TCELL / 2 - ay) ** 2)
        if m.get("name") == "Tatsumaki" or m["dmg"] < HIT:
            n, dmg = 1, 1                 # punches and each spin of the hurricane kick crack one
        elif m["dmg"] > HIT:
            n, dmg = 3, BLOCK_HP          # a shoryuken ploughs through up to three
        else:
            n, dmg = 1, BLOCK_HP          # a kick breaks one
        for c, r in touched[:n]:
            self._damage_block(c, r, dmg, heavy=dmg >= BLOCK_HP)

    def _damage_block(self, c, r, dmg, heavy=False):
        cell = self.grid[r][c]
        if cell is None:
            return
        x, y, w, h = self.cell_rect(c, r)
        self.effects.append(F.Effect(F.SPARK_HIT, x + w / 2, y + h / 2, 2))
        cell[1] -= dmg
        if self.t - self.last_hit < 50:
            self.combo += 1
        else:
            self.combo = 1
        self.last_hit = self.t
        if self.combo >= 2:
            self.combo_show = 70
        self.hitstop = max(self.hitstop, HITSTOP - 2 + (2 if heavy else 0))
        self.shake = max(self.shake, 4 if heavy else 2)
        if cell[1] > 0:
            audio.play("hit")
            return
        self.grid[r][c] = None
        self._changed()
        self.hp = max(0, self.hp - 1)
        audio.play("heavy" if heavy else "hit")
        self._shatter(cell[0], x, y)
        self.mood, self.mood_t = "mad", 40

    def _shatter(self, color, x, y, n=4, life=50):
        for k in range(n):
            img = piece_surface(((0, 0),), color, TCELL // 2)
            self.debris.append(Debris(img, x + (k % 2 + 0.5) * TCELL / 2, y + (k // 2 + 1) * TCELL / 2,
                                      self.rng.uniform(-2.5, 2.5), self.rng.uniform(-5, -1.5), life))

    def _smash_piece(self):
        pc = self.piece
        for x, y, w, h in self._piece_rects():
            self._shatter(pc.color, x, y, 2, 40)
        self.piece = None
        self.are = self._are()
        self.hp = max(0, self.hp - SMASH_HP)
        audio.play("heavy")
        self.hitstop = max(self.hitstop, 6)
        self.shake = max(self.shake, 5)
        self.mood, self.mood_t = "mad", 50

    # ---- his play ------------------------------------------------------------
    def _mad(self):
        return self.hp <= self.max_hp // 2

    def _are(self):
        return ARE_MAD if self._mad() else ARE

    def _spawn(self):
        pc = Piece(self.next)
        self.next = self._draw_kind()
        if not self.fits(pc.cells, pc.col, pc.row):
            self._top_out()
            return
        self._choose(pc)
        self.piece = pc

    def _play(self):
        if self.clearing:
            self.clearing[1] -= 1
            if self.clearing[1] <= 0:
                self._collapse(self.clearing[0])
                self.clearing = None
                self.are = self._are()
            return
        pc = self.piece
        if pc is None:
            self.are -= 1
            if self.are <= 0:
                self._spawn()
            return
        pc.shift_t -= 1
        if pc.shift_t <= 0:
            pc.shift_t = SHIFT
            step = 1 if pc.tcol > pc.col else -1
            if pc.col != pc.tcol and 0 <= pc.col + step <= COLS - _width(pc.cells) \
                    and self.fits(pc.cells, pc.col + step, pc.row):
                pc.col += step              # slide it over while it's still high up
            elif pc.rot != pc.trot:
                # turn it, nudging it sideways (toward where it's going) if it has to
                rot = (pc.rot + 1) % len(pc.rots)
                cells = pc.rots[rot]
                cols = [c for c in range(pc.col - 3, pc.col + 4) if 0 <= c <= COLS - _width(cells)]
                cols.sort(key=lambda c: (abs(c - pc.tcol), abs(c - pc.col)))
                col = next((c for c in cols if self.fits(cells, c, pc.row)), None)
                if col is None:
                    pc.trot = pc.rot            # boxed in: settle for what it is
                else:
                    pc.rot, pc.col = rot, col
            elif pc.col != pc.tcol:
                pc.tcol = pc.col
        aligned = pc.rot == pc.trot and pc.col == pc.tcol
        pc.fall_t -= 1
        if pc.fall_t <= 0:
            mad = self._mad()
            pc.fall_t = (SOFT_MAD if mad else SOFT) if aligned else (GRAV_MAD if mad else GRAV)
            if self.fits(pc.cells, pc.col, pc.row + 1):
                pc.row += 1
                pc.stuck = 0
            elif aligned or pc.stuck >= LOCK_DELAY:
                self._lock()
                return
            else:
                pc.stuck += 1               # resting on the stack: he still slides it into place
                pc.fall_t = SHIFT
        self._crush()

    def _crush(self):
        """A falling piece that reaches Akuma lands on him and breaks."""
        p = self.p
        if p.ko or p.state in ("launched", "down", "ko"):
            return
        hu = p.hurt_area()
        if hu is None or not any(contact(rect_area(rc), hu) for rc in self._piece_rects(shrink=1)):
            return
        pc = self.piece
        p.take_hit(DROP_DMG, 24, pc.x, knockdown=True, launch=-3.5)
        for x, y, w, h in self._piece_rects():
            self._shatter(pc.color, x, y, 2, 40)
        self.piece = None
        self.are = self._are()
        audio.play("heavy")
        self.hitstop = max(self.hitstop, HITSTOP)
        self.shake = max(self.shake, 8)
        self.effects.append(F.Effect(F.SPARK_HIT, p.x, p.y - 40, 2))
        self.mood, self.mood_t = "cheer", 50

    def _lock(self):
        pc = self.piece
        self.piece = None
        if any(pc.row + r < 0 for _, r in pc.cells):
            self._top_out()
            return
        for c, r in pc.cells:
            self.grid[pc.row + r][pc.col + c] = [pc.color, BLOCK_HP]
        self._changed()
        audio.play("land")
        full = [r for r in range(ROWS) if all(self.grid[r])]
        if not full:
            self.are = self._are()
            return
        n = min(4, len(full))
        self.clearing = [full, CLEAR_FLASH]
        self.lines += len(full)
        dmg = CLEAR_DMG[n]
        col = (255, 255, 255) if n == 4 else (255, 220, 80)
        self.banner = [CLEAR_NAMES[n], 110 if n == 4 else 60, col]
        audio.play("pickup")
        if n == 4:
            self.tetrises += 1
            self.flash = 16
            self.shake = 24
            audio.play("boom")
            self.waves.append([WELL_X + WELL_W / 2, WELL_TOP + min(full) * TCELL + 24, 0])
            self.mood, self.mood_t = "cheer", 120
        elif n == 3:
            self.shake = 10
            self.mood, self.mood_t = "cheer", 60
        p = self.p
        if dmg and not p.ko:
            p.take_hit(dmg, 40 if n == 4 else 20, WELL_X + WELL_W, knockdown=n == 4, launch=-5.0)
            p.flash = 20
            self.hitstop = max(self.hitstop, 10)
            self.effects.append(F.Effect(F.SPARK_HIT, p.x, p.y - 40, 2))

    def _collapse(self, rows):
        keep = [self.grid[r] for r in range(ROWS) if r not in rows]
        self.grid = [[None] * COLS for _ in rows] + keep
        self._changed()

    def _top_out(self):
        """He stacked to the ceiling: his game is over, the board is wiped, he starts again."""
        for c, r in self.cells():
            x, y, _, _ = self.cell_rect(c, r)
            self._shatter(self.grid[r][c][0], x, y, 1, 40)
        self.grid = [[None] * COLS for _ in range(ROWS)]
        self._changed()
        self.piece = None
        self.hp = max(0, self.hp - TOPOUT_DMG)
        self.banner = ["HE TOPPED OUT!", 90, (120, 255, 140)]
        self.are = 60
        audio.play("ko")
        self.mood, self.mood_t = "mad", 90

    # ---- endings -------------------------------------------------------------
    def _beaten(self):
        self.phase = "won"
        self.end_t = 0
        self.hitstop = 14
        self.shake = 16
        self.mood, self.mood_t = "lose", 10 ** 6
        self.banner = None
        audio.play("ko")
        for c, r in self.cells():
            x, y, _, _ = self.cell_rect(c, r)
            self._shatter(self.grid[r][c][0], x, y, 2, 110)
        if self.piece:
            for x, y, w, h in self._piece_rects():
                self._shatter(self.piece.color, x, y, 2, 110)
        self.grid = [[None] * COLS for _ in range(ROWS)]
        self._changed()
        self.piece = None
        self.clearing = None
        self._boom("explode_large", WELL_X + WELL_W / 2, GROUND_Y - 40, 80, 5)
        self._boom("explode_medium", WELL_X + 24, GROUND_Y - 20, 40)
        self._boom("explode_medium", WELL_X + WELL_W - 24, GROUND_Y - 24, 36, 5)

    def _lose(self):
        p = self.p
        p.hp = 0
        p.ko = True
        self.phase = "lost"
        self.end_t = 0
        self.mood, self.mood_t = "cheer", 10 ** 6
        audio.play("ko")

    def _time_over(self):
        p = self.p
        audio.play("ko")
        p.hp -= BOSS_TIMEOUT_DMG
        p.flash = 20
        if p.hp <= 0:
            self._lose()
            return
        self.timer = self.time_limit
        self.banner = ["TIME OVER! -%d HP" % BOSS_TIMEOUT_DMG, 100, (255, 80, 60)]

    # ---- drawing -------------------------------------------------------------
    def draw(self, surf):
        sh = (0, 0)
        if self.shake:
            sh = (self.rng.choice((-2, -1, 1, 2)), self.rng.choice((-1, 0, 1)))
        surf.blit(self.stage, sh)
        self._draw_master(surf, sh)
        # the open column glows next to every row that's ready for a TETRIS
        ready = self.ready_rows() if self.phase == "fight" else []
        if ready:
            glow = 90 + int(60 * math.sin(self.t / 5))
            g = pygame.Surface((TCELL, TCELL), pygame.SRCALPHA)
            g.fill((255, 140, 230, max(0, min(255, glow // (1 if len(ready) >= 3 else 2)))))
            for r in ready:
                x, y, _, _ = self.cell_rect(WELL_COL, r)
                surf.blit(g, (x + sh[0], y + sh[1]))
        clearing = set(self.clearing[0]) if self.clearing else ()
        for c, r in self.cells():
            color, hp = self.grid[r][c]
            x, y, _, _ = self.cell_rect(c, r)
            x, y = x + sh[0], y + sh[1]
            if r in clearing:
                color = (255, 255, 255) if (self.clearing[1] // 3) % 2 else shade(color, 1.4)
            _block(surf, color, x, y)
            if hp < BLOCK_HP:     # cracked
                dark = shade(color, 0.35)
                pygame.draw.lines(surf, dark, False, [(x + 2, y + 3), (x + 5, y + 6), (x + 4, y + 9), (x + 8, y + 10)])
                pygame.draw.line(surf, dark, (x + 5, y + 6), (x + 9, y + 4))
        pc = self.piece
        if pc:
            # where it's going to land: a faint ghost, and a shadow if Akuma's under it
            row = self.drop_row(pc.cells, pc.col, pc.row)
            for c, r in pc.cells:
                if row + r >= 0:
                    x, y, w, h = self.cell_rect(pc.col + c, row + r)
                    pygame.draw.rect(surf, shade(pc.color, 0.8), (x + 1 + sh[0], y + 1 + sh[1], w - 2, h - 2), 1)
            for c, r in pc.cells:
                x, y, _, _ = self.cell_rect(pc.col + c, pc.row + r)
                _block(surf, pc.color, x + sh[0], y + sh[1])
        self.p.draw(surf, sh)
        for pr in self.projectiles:
            pr.draw(surf, sh)
        for d in self.debris:
            d.draw(surf, sh)
        for fx in self.effects:
            fx.draw(surf, sh)
        for x, y, rad in self.waves:
            for k, col in ((0, (255, 255, 255)), (6, (120, 230, 255)), (12, (255, 90, 220))):
                if rad - k > 2:
                    pygame.draw.circle(surf, col, (round(x) + sh[0], round(y) + sh[1]), round(rad - k), 2)
        if self.flash and self.flash % 4 < 2:
            fl = pygame.Surface((W, H), pygame.SRCALPHA)
            fl.fill((255, 255, 255, 150))
            surf.blit(fl, (0, 0))
        self._hud(surf)

    def _draw_master(self, surf, sh):
        g = GROUND_Y + sh[1]
        # his screen shows the same game, small
        sx, sy = CAB_X + 3 + sh[0], g - 62
        surf.fill((8, 6, 16), (sx, sy, COLS * 2, ROWS * 2))
        for c, r in self.cells():
            surf.fill(self.grid[r][c][0], (sx + c * 2, sy + r * 2, 2, 2))
        if self.piece:
            for c, r in self.piece.cells:
                if self.piece.row + r >= 0:
                    surf.fill(self.piece.color, (sx + (self.piece.col + c) * 2, sy + (self.piece.row + r) * 2, 2, 2))
        if self.phase == "won" and (self.t // 10) % 2:
            surf.fill((200, 20, 30), (sx, sy + 7, COLS * 2, 4))
        pose = self.mood if self.phase != "intro" else "play"
        draw_master(surf, MASTER_X + sh[0], g, pose, self.t)

    def _hud(self, surf):
        p = self.p
        surf.blit(F._PORTRAIT, (4, 4))
        pygame.draw.rect(surf, (10, 6, 14), (3, 3, F._PORTRAIT.get_width() + 2, F._PORTRAIT.get_height() + 2), 1)
        bw = F.BAR_W
        self._bar(surf, 40, 10, bw, p.hp, self.p_lag, p.max_hp, False)
        self._bar(surf, W - 8 - bw, 10, bw, self.hp, self.lag, self.max_hp, True, col=(120, 230, 255))
        draw_text(surf, "AKUMA", 40, 21, (255, 90, 90))
        draw_text(surf, self.name, W - 8, 21, (255, 230, 120), align="right")
        draw_text(surf, "LINES %d" % self.lines, W - 8 - bw, 31, (200, 200, 230))
        # the next piece, under the clock
        bx, by = W // 2 - 4, 26
        pygame.draw.rect(surf, (10, 6, 14), (bx - 1, by - 1, 24, 14))
        pygame.draw.rect(surf, (120, 90, 200), (bx - 1, by - 1, 24, 14), 1)
        draw_text(surf, "NEXT", bx - 4, by + 3, (200, 200, 230), align="right")
        cells = PIECES[self.next]
        w, h = _width(cells), max(r for _, r in cells) + 1
        ox, oy = bx + 11 - w * 2, by + 6 - h * 2
        for c, r in cells:
            _block(surf, PIECE_COLORS[self.next], ox + c * 4, oy + r * 4, 4)
        secs = max(0, (self.timer + FPS - 1) // FPS)
        col = (255, 60, 40) if secs <= 5 and (self.t // 8) % 2 else (255, 230, 120)
        draw_text(surf, "%02d" % secs, W // 2, 6, col, scale=2, align="center")
        if self.phase == "intro":
            if self.t < self.intro_len - 18:
                draw_text(surf, "BOSS!", W // 2, 56, (255, 220, 80), scale=2, align="center")
                draw_text(surf, self.name, W // 2, 76, (255, 255, 255), align="center")
                draw_text(surf, "BREAK HIS BLOCKS BEFORE HE", W // 2, 88, (200, 200, 230), align="center")
                draw_text(surf, "SCORES A TETRIS!", W // 2, 97, (200, 200, 230), align="center")
            else:
                draw_text(surf, "SMASH IT!", W // 2, 70, (255, 60, 40), scale=3, align="center")
        elif self.phase == "fight" and len(self.ready_rows()) >= 3 and (self.t // 10) % 2:
            draw_text(surf, "TETRIS READY!" if len(self.ready_rows()) >= 4 else "TETRIS DANGER!",
                      100, 50, (255, 120, 220), align="center")
        if self.combo_show and self.combo >= 2:
            draw_text(surf, "%d HIT COMBO" % self.combo, 6, 40, (255, 200, 40), scale=2)
        if self.banner:
            text, left, col = self.banner
            if text == "TETRIS!":
                cols = list(PIECE_COLORS.values())
                col = cols[(self.t // 4) % len(cols)]
                draw_text(surf, text, W // 2, 60, col, scale=4, align="center")
                draw_text(surf, "-%d HP" % CLEAR_DMG[4], W // 2, 92, (255, 255, 255), align="center")
            else:
                draw_text(surf, text, W // 2, 64, col, scale=2, align="center")
        if self.phase == "won" and self.end_t > 10:
            draw_text(surf, "GAME OVER!", W // 2, 60, (255, 220, 60), scale=3, align="center")
            draw_text(surf, "THE MASTER IS BEATEN", W // 2, 88, (255, 255, 255), align="center")
        if self.phase == "lost" and self.end_t > 10:
            draw_text(surf, "AKUMA FALLS...", W // 2, 64, (255, 255, 255), scale=2, align="center")
        if self.menu.open:
            self.menu.draw(surf)


# --------------------------------------------------------------------------
# map side
# --------------------------------------------------------------------------
_MODEL_OFFSET = 0


def setup_map_car(e, rng, boss, cfg, index=0):
    """Fill in a MapEnemy as a car (called from dungeon.MapEnemy)."""
    e.car = True
    e.seed = rng.randrange(1 << 20)
    if boss:
        e.name = cfg["boss_name"]
        e.side_hp = BOSS_HP // 2         # (the fight itself counts blocks: TetrisScene)
        e.color = (240, 70, 200)
        e.frames = tetris_map_frames()
        e.speed = 0.0
    else:
        global _MODEL_OFFSET
        if index == 0:      # a new map: start the line-up somewhere new, so all seven turn up over runs
            _MODEL_OFFSET = e.seed % len(CAR_MODELS)
        e.model = CAR_MODELS[(index + _MODEL_OFFSET) % len(CAR_MODELS)]
        e.name = e.model["name"]
        e.color = e.model["color"]
        e.side_hp = HIT * CAR_SIDE_HITS
        e.frames = car_map_frames(e.color, e.model.get("roof"))
        e.speed = rng.uniform(0.7, 1.0)
    e.hp = e.side_hp * 2
    e.level = 0
    e.aware = True      # no sneak attacks on a parked car
    e.drive = None


DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
REVERSE = {"up": "down", "down": "up", "left": "right", "right": "left"}


def drive(e, dg, rng):
    """Cars cruise the corridors, turning at walls and now and then at junctions."""
    e.anim += 1
    if e.speed <= 0:
        e.moving = False
        return

    def free(d, dist=6):
        dx, dy = DIRS[d]
        return not dg.rect_hits_wall(e.rect().move(dx * dist, dy * dist))

    if e.drive is None or not free(e.drive, 2) or (e.anim % 50 == 0 and rng.random() < 0.35):
        options = [d for d in DIRS if d != REVERSE.get(e.drive) and free(d)]
        if not options:
            options = [d for d in DIRS if free(d, 2)]
        e.drive = rng.choice(options) if options else None
    if e.drive is None:
        e.moving = False
        return
    dx, dy = DIRS[e.drive]
    e.x += dx * e.speed
    e.y += dy * e.speed
    if dg.rect_hits_wall(e.rect()):
        e.x -= dx * e.speed
        e.y -= dy * e.speed
        e.drive = None
    e.dir = e.drive or e.dir
    e.moving = True
