"""Level 3: the car-smashing level (Street Fighter II bonus-stage style).

Cars drive around the map instead of enemies. Touching one starts a timed
bonus round: the car never fights back, and it has to be smashed on both
sides (jump over it to reach the other side) before the timer runs out. The
boss is a car built out of falling-block puzzle pieces that sheds blocks as it
is hit. During the boss fight random pieces rain down as if someone were playing
the puzzle game in the background: they hurt Akuma, and any that land on the
car lock into place and repair it.
"""

import math
import os
import random

import pygame

from . import audio
from . import fight as F
from .art import shade, mix, _outlined, OUTLINE
from .config import W, H, FPS, GROUND_Y, HITSTOP, STAGE_LEFT, STAGE_RIGHT
from .fighters import Fighter, overlap, contact, image_area, rect_area, CANCEL_WINDOW, HIT
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
BOSS_SIDE_HITS = 9
BOSS_TIME = 45
TIMEOUT_DMG = 20           # Akuma's penalty when a car gets away
BOSS_TIMEOUT_DMG = 30
DROP_DMG = 10              # a falling puzzle piece landing on Akuma
TETRO_EVERY = (150, 240)   # frames between pieces (2.5-4 s), random
TETRO_EVERY_MAD = (130, 200)   # once the boss is below half health
TETRO_STEP = 6             # frames per one-cell step down (5 when enraged)
TETRO_LOCK = 14            # a piece blinks this long on the car before repairing it
TETRO_SETTLE = 40          # a piece on the street lingers this long, then blinks out
REPAIR_FRAC = 0.04         # of the boss's max HP restored per piece that lands on it

# falling-block pieces (cells as (col, row))
PIECES = {
    "I": ((0, 0), (1, 0), (2, 0), (3, 0)), "O": ((0, 0), (1, 0), (0, 1), (1, 1)),
    "T": ((0, 0), (1, 0), (2, 0), (1, 1)), "S": ((1, 0), (2, 0), (0, 1), (1, 1)),
    "Z": ((0, 0), (1, 0), (1, 1), (2, 1)), "J": ((0, 0), (0, 1), (1, 1), (2, 1)),
    "L": ((2, 0), (0, 1), (1, 1), (2, 1)),
}
PIECE_COLORS = {"I": (40, 210, 230), "O": (240, 210, 40), "T": (170, 60, 200), "S": (60, 200, 80),
                "Z": (230, 50, 50), "J": (50, 90, 230), "L": (250, 140, 30)}
WHEEL = (64, 62, 72)

# the boss: a car silhouette 16 x 8 cells
BOSS_MASK = ["......#####.....",
             ".....#######....",
             "....#########...",
             "################",
             "################",
             "################",
             ".##.........##..",
             ".##.........##.."]
CELL = 7


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
# the block-car boss
# --------------------------------------------------------------------------
def _block(surf, color, x, y, c=CELL):
    surf.fill(OUTLINE, (x, y, c, c))
    surf.fill(color, (x + 1, y + 1, c - 2, c - 2))
    surf.fill(shade(color, 1.35), (x + 1, y + 1, c - 2, 1))
    surf.fill(shade(color, 1.35), (x + 1, y + 1, 1, c - 2))
    surf.fill(shade(color, 0.65), (x + 1, y + c - 2, c - 2, 1))
    surf.fill(shade(color, 0.65), (x + c - 2, y + 1, 1, c - 2))


def build_block_car(seed):
    """Tile the car silhouette with falling-block pieces.
    Returns [(cells, color)] for every piece."""
    rng = random.Random(seed)
    free = {(c, r) for r, row in enumerate(BOSS_MASK) for c, ch in enumerate(row) if ch == "#"}
    pieces = []
    # wheels are grey O pieces
    for c0 in (1, 12):
        cells = ((c0, 6), (c0 + 1, 6), (c0, 7), (c0 + 1, 7))
        pieces.append((cells, WHEEL))
        free -= set(cells)
    shapes = [(k, rot) for k, cells in PIECES.items() for rot in _rotations(cells)]
    order = sorted(free, key=lambda p: (p[1], p[0]))
    for cell in order:
        if cell not in free:
            continue
        rng.shuffle(shapes)
        placed = False
        for k, rot in shapes:
            # anchor the piece so its first cell lands on this one
            ax, ay = rot[0]
            cells = tuple((cell[0] + c - ax, cell[1] + r - ay) for c, r in rot)
            if all(p in free for p in cells):
                pieces.append((cells, PIECE_COLORS[k]))
                free -= set(cells)
                placed = True
                break
        if not placed:
            pieces.append(((cell,), rng.choice(list(PIECE_COLORS.values()))))
            free.discard(cell)
    return pieces


BOSS_W, BOSS_H = len(BOSS_MASK[0]) * CELL, len(BOSS_MASK) * CELL
BOSS_ANCHOR = (BOSS_W // 2, BOSS_H)


def piece_surface(cells, color, c=CELL):
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


def boss_map_frames(pieces):
    s = pygame.Surface((BOSS_W // CELL * 2 + 2, BOSS_H // CELL * 2 + 2), pygame.SRCALPHA)
    for cells, color in pieces:
        for x, y in cells:
            s.fill(color, (1 + x * 2, 1 + y * 2, 2, 2))
    s = pygame.transform.scale_by(_outlined(s), 1.5)
    return {(d, k): s for d in ("up", "down", "left", "right") for k in (0, 1)}


# --------------------------------------------------------------------------
# stage + map tiles
# --------------------------------------------------------------------------
def make_car_stage(boss=False):
    rng = random.Random(77 if boss else 33)
    s = pygame.Surface((W, H))
    top, bot = ((10, 4, 30), (120, 30, 110)) if boss else ((8, 10, 30), (60, 40, 90))
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
    if boss:     # the puzzle game being played behind the fight: a faint well grid
        grid = pygame.Surface((W, GROUND_Y), pygame.SRCALPHA)
        for gx in range(0, W + 1, CELL):
            pygame.draw.line(grid, (180, 160, 255, 34), (gx, 7), (gx, GROUND_Y - 1))
        for gy in range(7, GROUND_Y, CELL):
            pygame.draw.line(grid, (180, 160, 255, 18), (0, gy), (W, gy))
        s.blit(grid, (0, 0))
        # a few dim leftover rows stacked at the bottom of the well, half hidden by the fence
        for row in range(2):
            for gx in range(0, W, CELL):
                if rng.random() < 0.55 - row * 0.2:
                    blk = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                    _block(blk, shade(rng.choice(list(PIECE_COLORS.values())), 0.45), 0, 0)
                    blk.set_alpha(110)
                    s.blit(blk, (gx, GROUND_Y - 36 - (row + 1) * CELL))
    if boss:     # neon frame of falling blocks along the top
        x = 0
        cols = list(PIECE_COLORS.values())
        while x < W:
            _block(s, cols[(x // 7) % len(cols)], x, 0)
            x += 7
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
class CarTarget:
    """Stands in for the opponent Fighter: Akuma faces it and hits it."""

    def __init__(self, enemy, power_hint=1.0):
        self.name = enemy.name
        self.boss = enemy.boss
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
        if self.boss:
            self.half, self.height = BOSS_W // 2 - 4, BOSS_H - 6
            self.pieces = enemy.pieces
            sides = ([], [])
            mid = len(BOSS_MASK[0]) / 2
            for i, (cells, color) in enumerate(self.pieces):
                cx = sum(c for c, _ in cells) / len(cells) + 0.5
                cy = sum(r for _, r in cells) / len(cells)
                side = 0 if cx < mid else 1
                # outer and upper blocks fly off first, wheels last
                key = (color == WHEEL, -abs(cx - mid), cy)
                sides[side].append((key, i))
            self.order = [[i for _, i in sorted(lst)] for lst in sides]
            self.gone = set()
        else:
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

    def boss_shed(self):
        """Pieces that should be gone now, by side damage. Returns newly lost pieces."""
        lost = []
        for side in (0, 1):
            frac = self.side_hp[side] / self.side_max
            order = self.order[side]
            n = len(order) if frac <= 0 else min(len(order) - 1, int(len(order) * (1 - frac)))
            for i in order[:n]:
                if i not in self.gone:
                    self.gone.add(i)
                    lost.append(i)
        return lost

    def repair(self, side, amount):
        """A puzzle piece locked onto this side: heal it (or the other side if this
        one is whole) and put its lost blocks back. Returns (healed, restored pieces)."""
        if self.side_hp[side] >= self.side_max:
            side = 1 - side
        before = self.hp
        self.side_hp[side] = min(self.side_max, self.side_hp[side] + amount)
        restored = []
        for s in (0, 1):
            frac = self.side_hp[s] / self.side_max
            order = self.order[s]
            n = len(order) if frac <= 0 else min(len(order) - 1, int(len(order) * (1 - frac)))
            for i in order[n:]:
                if i in self.gone:
                    self.gone.discard(i)
                    restored.append(i)
        return self.hp - before, restored

    def image(self):
        if self.boss:
            key = frozenset(self.gone)
            img = self._cache.get(key)
            if img is None:
                img = pygame.Surface((BOSS_W, BOSS_H), pygame.SRCALPHA)
                for i, (cells, color) in enumerate(self.pieces):
                    if i not in self.gone:
                        for c, r in cells:
                            _block(img, color, c * CELL, r * CELL)
                self._cache = {key: img}
            return img, BOSS_ANCHOR
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


class FallingPiece:
    """A random puzzle piece falling in one-cell steps, as if someone were playing
    the puzzle game behind the fight: it drifts sideways and spins on the way down."""

    def __init__(self, kind, rng, step=TETRO_STEP):
        self.kind = kind
        self.color = PIECE_COLORS[kind]
        self.rots = _rotations(PIECES[kind])
        self.rot = rng.randrange(len(self.rots))
        self.rng = rng
        self.step = step
        cols = W // CELL
        self.col = rng.randrange(0, cols - 3)
        self.goal = rng.randrange(0, cols - 3)      # where the "player" is steering it
        self.y = -4 * CELL                          # top of the piece
        self.t = step
        self.state = "fall"                         # fall / lock (on the car) / settle (street)
        self.timer = 0
        self.alive = True
        self._imgs = {}

    @property
    def cells(self):
        return self.rots[self.rot]

    @property
    def img(self):
        img = self._imgs.get(self.rot)
        if img is None:
            img = self._imgs[self.rot] = piece_surface(self.cells, self.color)
        return img

    @property
    def x(self):
        """Centre x of the piece."""
        w = max(c for c, _ in self.cells) + 1
        return (self.col + w / 2) * CELL

    def cell_rects(self, cells=None, col=None, y=None):
        cells = self.cells if cells is None else cells
        col = self.col if col is None else col
        y = self.y if y is None else y
        return [((col + c) * CELL, y + r * CELL, CELL, CELL) for c, r in cells]

    def rect(self):
        w, h = self.img.get_size()
        return (self.col * CELL, self.y, w, h)

    def _gap(self, floor, cells=None, col=None, y=None):
        """Smallest distance from a cell's bottom to the floor under it."""
        return min(floor(x + w / 2) - (yy + h) for x, yy, w, h in self.cell_rects(cells, col, y))

    def update(self, floor):
        """Falls one cell every `step` frames. Returns "car"/"ground" on the frame it lands."""
        if self.state != "fall":
            self.timer -= 1
            if self.timer <= 0:
                self.alive = False
            return None
        self.t -= 1
        if self.t > 0:
            return None
        self.t = self.step
        rng = self.rng
        # the unseen player: spin now and then, slide toward where they want it
        if rng.random() < 0.18 and len(self.rots) > 1:
            rot = (self.rot + 1) % len(self.rots)
            w = max(c for c, _ in self.rots[rot]) + 1
            col = min(self.col, W // CELL - w)
            if self._gap(floor, self.rots[rot], col) >= 0:
                self.rot, self.col = rot, col
        if self.col != self.goal and rng.random() < 0.6:
            col = self.col + (1 if self.goal > self.col else -1)
            w = max(c for c, _ in self.cells) + 1
            if 0 <= col <= W // CELL - w and self._gap(floor, col=col) >= 0:
                self.col = col
        elif rng.random() < 0.04:
            self.goal = rng.randrange(0, W // CELL - 3)
        gap = self._gap(floor)
        if gap > CELL:
            self.y += CELL
            return None
        # touch down: rest exactly on whatever is below
        self.y += max(0, gap)
        on_car = any(floor(x + w / 2) < GROUND_Y - 1 and abs(floor(x + w / 2) - (y + h)) < 1
                     for x, y, w, h in self.cell_rects())
        if on_car:
            self.state, self.timer = "lock", TETRO_LOCK
            return "car"
        self.state, self.timer = "settle", TETRO_SETTLE
        return "ground"


class CarScene:
    """Timed bonus round against a car that never fights back."""

    def __init__(self, game, enemy, akuma_hp, akuma_max, power=1.0, seed=None):
        F.init_shared()
        self.game = game
        self.enemy_ref = enemy
        self.rng = random.Random(seed)
        self.boss = enemy.boss
        key = ("car", self.boss)
        if key not in F._STAGES:
            F._STAGES[key] = make_car_stage(self.boss)
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
        self.drops = []
        p.projectiles = self.projectiles
        p.effects = self._spawn_effect
        p.state = "intro"
        self.p = p
        self.power = power
        self.time_limit = (BOSS_TIME if self.boss else CAR_TIME) * FPS
        self.timer = self.time_limit
        self.intro_len = 70 if self.boss else 50
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
        self.drop_t = 120
        self.repair_fx = []       # [restored piece indices, frames left]
        self.popups = []          # [text, x, y, frames left]
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
            if self.end_t >= (130 if self.boss else 90) or skip:
                self.result = {"won": "win", "escape": "escape", "lost": "lose"}[self.phase]
                self.game.end_fight(self, self.result, max(0, p.hp))
            return

        self.timer -= 1
        p.update(self._intent(inp))
        self._hold_tatsu()
        self._projectiles()
        self._melee()
        if self.boss:
            self._boss_drops()
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
        if car.boss:
            for i in car.boss_shed():
                cells, color = car.pieces[i]
                img = piece_surface(cells, color)
                mx = sum(c for c, _ in cells) / len(cells) * CELL
                my = sum(r for _, r in cells) / len(cells) * CELL
                x = car.x - BOSS_ANCHOR[0] + mx
                y = car.y - BOSS_ANCHOR[1] + my + CELL
                away = -1 if side == 0 else 1
                self.debris.append(Debris(img, x, y, away * self.rng.uniform(-0.5, 3.0),
                                          self.rng.uniform(-6, -2), 80))
        elif car.stages()[side] != before or car.sheet_stage() != before_sheet:
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

    def _boss_drops(self):
        """Puzzle pieces rain down: they hurt Akuma, lock onto the car to repair
        it, and can be smashed in mid-air."""
        p, car = self.p, self.car
        enraged = car.hp <= car.max_hp // 2
        self.drop_t -= 1
        if self.drop_t <= 0:
            self.drop_t = self.rng.randint(*(TETRO_EVERY_MAD if enraged else TETRO_EVERY))
            self.drops.append(FallingPiece(self.rng.choice(list(PIECES)), self.rng,
                                           TETRO_STEP - 1 if enraged else TETRO_STEP))
        hb = p.strike_area()
        for d in self.drops:
            was = d.state
            landed = d.update(self._floor)
            if landed == "car":
                audio.play("land")
                self.shake = max(self.shake, 2)
            elif landed == "ground":
                audio.play("land")
            if was == "lock" and not d.alive:
                self._repair(d)
            if d.state != "fall" or not d.alive:
                continue
            rects = d.cell_rects()
            # a punch or kick (or a fireball) smashes it before it lands
            pr = next((pr for pr in self.projectiles if pr.alive
                       and any(contact(pr.area(), rect_area(r)) for r in rects)), None)
            if pr is not None or (hb and any(contact(hb, rect_area(r)) for r in rects)):
                if pr is not None:
                    pr.alive = False
                else:
                    p.hits_done += 1
                    p.last_hit_t = p.move_t
                    hb = None
                self._break(d)
                audio.play("hit")
                self.hitstop = max(self.hitstop, 4)
                continue
            hu = p.hurt_area()
            if hu and any(contact(rect_area(r), hu) for r in rects) and p.state not in ("hitstun", "launched", "down"):
                self._break(d)
                p.take_hit(DROP_DMG, 24, d.x, knockdown=True, launch=-3.5)
                audio.play("heavy")
                self.hitstop = max(self.hitstop, HITSTOP)
                self.shake = max(self.shake, 8)
                self.effects.append(F.Effect(F.SPARK_HIT, p.x, p.y - 40, 2))
        self.drops = [d for d in self.drops if d.alive]
        for fx in self.repair_fx:
            fx[1] -= 1
        self.repair_fx = [fx for fx in self.repair_fx if fx[1] > 0]
        for pp in self.popups:
            pp[1] -= 0.3
            pp[3] -= 1
        self.popups = [pp for pp in self.popups if pp[3] > 0]
        if p.hp <= 0:
            self.phase = "lost"
            self.end_t = 0
            p.ko = True
            audio.play("ko")

    def _break(self, d):
        d.alive = False
        for x, y, w, h in d.cell_rects():
            self.debris.append(Debris(piece_surface(((0, 0),), d.color), x + w / 2, y + h,
                                      self.rng.uniform(-2, 2), self.rng.uniform(-4, -1), 40))

    def _repair(self, d):
        """A piece that locked onto the car becomes part of it again."""
        car = self.car
        if car.ko or self.phase != "fight":
            return
        healed, restored = car.repair(self._side_of(d.x), max(1, round(car.max_hp * REPAIR_FRAC)))
        if healed <= 0:
            return
        self.lag = car.hp
        if restored:
            self.repair_fx.append([restored, 24])
        self.popups.append(["REPAIR +%d" % healed, d.x, d.y - 4, 45])
        audio.play("pickup")

    def _destroyed(self):
        car = self.car
        car.ko = True
        self.phase = "won"
        self.end_t = 0
        self.hitstop = 14
        self.shake = 16
        self.drops.clear()
        audio.play("ko")
        for side in (0, 1):
            self._shards(side, 16)
        # the tank goes up: one big fireball over the car, a smaller one each end
        top = car.y - car.height
        self._boom("explode_large", car.x, top + 4, 76 if car.boss else 64, 5)
        self._boom("explode_medium", car.x - car.half * 0.7, top + 14, 40)
        self._boom("explode_medium", car.x + car.half * 0.7, top + 16, 36, 5)
        if car.boss:
            for i, (cells, color) in enumerate(car.pieces):
                if i not in car.gone:
                    car.gone.add(i)
                    mx = sum(c for c, _ in cells) / len(cells) * CELL
                    self.debris.append(Debris(piece_surface(cells, color),
                                              car.x - BOSS_ANCHOR[0] + mx, car.y - 10,
                                              self.rng.uniform(-3, 3), self.rng.uniform(-7, -2), 120))

    def _time_over(self):
        p = self.p
        audio.play("ko")
        if self.boss:
            p.hp -= BOSS_TIMEOUT_DMG
            p.flash = 20
            if p.hp <= 0:
                p.hp = 0
                p.ko = True
                self.phase = "lost"
                self.end_t = 0
                return
            self.timer = self.time_limit
            self.banner = ["TIME OVER! -%d HP" % BOSS_TIMEOUT_DMG, 100]
            return
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
        if not (car.ko and not car.boss and self.end_t > 50 and not painted):
            img, (ax, ay) = car.image()
            wob = (1 if car.wobble % 4 < 2 else -1) if car.wobble else 0
            x = round(car.x) - ax + sh[0] + wob
            y = round(car.y) - ay + sh[1]
            pygame.draw.ellipse(surf, (20, 18, 26), (x + 6, GROUND_Y - 3 + sh[1], img.get_width() - 12, 6))
            if car.flash and car.flash % 3 == 0:
                img = pygame.mask.from_surface(img).to_surface(setcolor=(255, 255, 255, 255),
                                                               unsetcolor=(0, 0, 0, 0))
            surf.blit(img, (x, y))
            if not car.boss:
                self._smoke(surf, sh)
        if self.repair_fx and car.boss and not car.ko:
            ox = round(car.x) - BOSS_ANCHOR[0] + sh[0]
            oy = round(car.y) - BOSS_ANCHOR[1] + sh[1]
            for idx, left in self.repair_fx:
                if (left // 3) % 2 == 0:
                    for i in idx:
                        for c, r in car.pieces[i][0]:
                            _block(surf, (255, 255, 255), ox + c * CELL, oy + r * CELL)
        for d in self.drops:
            if d.state == "fall":
                # a little shadow on the street below warns where it is
                w = d.img.get_width()
                if d.y > -3 * CELL:
                    pygame.draw.ellipse(surf, (20, 18, 26), (d.col * CELL + 1 + sh[0], GROUND_Y - 2 + sh[1], w - 2, 4))
            elif d.state == "lock" and d.timer % 4 < 2:
                img = pygame.mask.from_surface(d.img).to_surface(setcolor=(255, 255, 255, 255),
                                                                 unsetcolor=(0, 0, 0, 0))
                surf.blit(img, (d.col * CELL + sh[0], round(d.y) + sh[1]))
                continue
            elif d.state == "settle" and d.timer < 18 and d.timer % 4 < 2:
                continue
            surf.blit(d.img, (d.col * CELL + sh[0], round(d.y) + sh[1]))
        self.p.draw(surf, sh)
        for pr in self.projectiles:
            pr.draw(surf, sh)
        for d in self.debris:
            d.draw(surf, sh)
        for fx in self.effects:
            fx.draw(surf, sh)
        for text, x, y, left in self.popups:
            if left > 10 or left % 2:
                draw_text(surf, text, round(x), round(y), (120, 255, 140), align="center")
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
        draw_text(surf, car.name, W - 8, 21, (255, 230, 120) if car.boss else (220, 220, 255), align="right")
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
                draw_text(surf, "BOSS!" if car.boss else "BONUS ROUND", W // 2, 64, (255, 220, 80),
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
# map side
# --------------------------------------------------------------------------
_MODEL_OFFSET = 0


def setup_map_car(e, rng, boss, cfg, index=0):
    """Fill in a MapEnemy as a car (called from dungeon.MapEnemy)."""
    e.car = True
    e.seed = rng.randrange(1 << 20)
    if boss:
        e.name = cfg["boss_name"]
        e.pieces = build_block_car(e.seed)
        e.side_hp = HIT * BOSS_SIDE_HITS
        e.color = (200, 200, 200)
        e.frames = boss_map_frames(e.pieces)
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
