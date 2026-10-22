"""Level 12: the Prisoners' Quarters, a side-scrolling souls-like ("think Dead Cells").

A dungeon bigger than the screen both ways, put together per seed from
hand-made room chunks on a 6 x 3 grid: the main path runs from the start cell
on the left to the Warden's arena on the right, climbing ladders between rows;
a few dead-end side rooms hold scrolls of power or a chest. Undead fighters from
the sprite pack (grunts, shield bearers, fireball casters) and skull bats guard
it; every enemy flashes before it swings, and they hit hard. Akuma runs, jumps
(coyote time, jump buffer, variable height), rolls through attacks, punches in
a 3-hit string, kicks, throws hadoukens and dive-kicks. Checkpoint shrines
refill the health flasks; dying costs one of three lives and sends him back to
the last shrine. Cells dropped by enemies buy strength or vitality at the altar
room. The Warden guards the exit: beat him and the gate opens.

Whole-level scene like pacman.py / bomber.py: game.level_done(self, hp) when
Akuma walks out of the exit, game.level_failed(self) when his lives run out.
"""

import math
import random
from collections import deque

import pygame

from . import audio
from .akuma_sprites import CharArt, hado_frames
from .art import OUTLINE
from .config import W, H
from .fighters import touches, rect_area, image_area
from .font import draw_text, text_width
from .pause import PauseMenu

# ---------------------------------------------------------------------------
# tuning
# ---------------------------------------------------------------------------
T = 16                       # tile, px
RW, RH = 20, 12              # room chunk, tiles (one screen)
GW, GH = 6, 3                # room grid of the main level
AW = 2                       # the boss arena is two rooms wide, right of the grid
COLS, ROWS = (GW + AW) * RW, GH * RH
LW, LH = COLS * T, ROWS * T

SCALE = 0.5                  # Akuma's fight sprites at platformer size
GRAV = 0.34
MAX_FALL = 6.5
RUN = 1.9                    # px / frame
ACC_GROUND, ACC_AIR = 0.5, 0.3
JUMP_V = -6.1                # ~3.3 tiles high
JUMP_CUT = -2.0              # letting go of UP early caps the rise speed here
COYOTE = 6                   # frames a jump still works after running off a ledge
JUMP_BUFFER = 7              # frames an early UP press is remembered
CLIMB = 1.5
PW, PH, ROLL_H = 10, 26, 14  # Akuma's body box (feet-centred)
ROLL_T, ROLL_V = 24, 3.3
ROLL_IFRAMES = (1, 18)       # roll frames during which nothing can hurt him
ROLL_CD = 8
HURT_T, INVULN = 16, 45
LIVES = 3
FLASKS = 3
FLASK_HEAL = 0.45            # fraction of max hp
DRINK_T, DRINK_AT = 48, 30
KI_MAX, HADO_COST, KI_REGEN, KI_ON_HIT = 100, 40, 0.22, 5
SPIKE_DMG = 24
INTRO = 170
SHOP_COST = (25, 40, 60, 85)
STR_UP, VIT_UP = 0.2, 30
CAM_LOOK = 46

DMG = dict(grunt=22, shield=32, bolt=18, bat=14, swing=38, charge=30, slam=34, wave=24, fire=20)
TELEGRAPH = dict(grunt=28, shield=36, caster=40, bat=26, boss=34)
BOSS_HP = 640
BOSS_SCALE = 0.75            # 1.5 x Akuma's size here

CONTROLS = [
    "ARROWS / WASD: RUN   UP: JUMP (HOLD = HIGHER)",
    "UP / DOWN ON A LADDER: CLIMB",
    "DOWN + UP ON A PLANK: DROP THROUGH",
    "J PUNCH: 3-HIT STRING   K KICK: HEAVY, BREAKS SHIELDS",
    "L SPECIAL: HADOUKEN (USES KI)   DOWN + L: DRINK FLASK",
    "IN THE AIR: J / K, DOWN + K = DIVE KICK",
    "I: DODGE ROLL - INVINCIBLE WHILE ROLLING",
    "SHRINES REFILL FLASKS. DEATH COSTS A LIFE",
    "SPEND CELLS AT THE ALTARS: STAND + DOWN",
    "ENEMIES FLASH BEFORE THEY STRIKE. ROLL!",
]

# ---------------------------------------------------------------------------
# room chunks: 20 x 12 tiles.  # wall  . air  = plank (one-way)  H ladder
# ^ spikes.  Markers (air): t torch, g grunt, s shield, a caster, b bat,
# ? any ground foe, @ start, k shrine, $ / % strength / vitality altar, c reward.
# Rules (checked at import): doors at rows 6-8 of the side walls over a floor
# at row 9; column 9 is the ladder shaft, rows 9-11 under it solid.
# ---------------------------------------------------------------------------
_FLOOR = ["####################"] * 3
NORMAL = [
    ["####################",
     "#..................#",
     "#...t..........t...#",
     "#....====..====....#",
     "#..................#",
     "#.........b........#",
     "#...===......===...#",
     "#..................#",
     "#....g.......?.....#"] + _FLOOR,
    ["####################",
     "#..................#",
     "#...t..........t...#",
     "#..................#",
     "#..................#",
     "#.......b..........#",
     "#......====........#",
     "#..................#",
     "#..g........a......#",
     "####...######...####",
     "####^^^######^^^####",
     "####################"],
    ["####################",
     "#..................#",
     "#.t..............t.#",
     "#...===.....===....#",
     "#..................#",
     "#.....b......b.....#",
     "#.......====.......#",
     "#..................#",
     "#.s.........?......#"] + _FLOOR,
    ["####################",
     "#..................#",
     "#...t.........t....#",
     "#..................#",
     "#.............===..#",
     "#..................#",
     "#.............a....#",
     "#....##......###...#",
     "#....##..g...###...#"] + _FLOOR,
    ["####################",
     "#..................#",
     "#..t.....t.....t...#",
     "#..................#",
     "#..................#",
     "#.....b.......b....#",
     "#...====...====....#",
     "#..................#",
     "#..g............?..#",
     "####....###....#####",
     "####^^^^###^^^^#####",
     "####################"],
    ["####################",
     "#..................#",
     "#.t..............t.#",
     "#..==H=......=H==..#",
     "#....H........H....#",
     "#....H...b....H....#",
     "#....H........H....#",
     "#....H........H....#",
     "#..g.H......?.H....#"] + _FLOOR,
    ["####################",
     "#..................#",
     "#..t.....b......t..#",
     "#..................#",
     "#.===..........===.#",
     "#..................#",
     "#.............a....#",
     "#...###......###...#",
     "#...###..g...###...#"] + _FLOOR,
    ["####################",
     "#..................#",
     "#.t......t.......t.#",
     "#..................#",
     "#..................#",
     "#..................#",
     "#......======......#",
     "#..................#",
     "#......?.....s.....#",
     "###...########...###",
     "###^^^########^^^###",
     "####################"],
]
START = [
    ["####################",
     "#..................#",
     "#..t.....t.....t...#",
     "#..................#",
     "#..................#",
     "#..................#",
     "#.......====.......#",
     "#..................#",
     "#..@..k............#"] + _FLOOR,
]
SHOP = [
    ["####################",
     "#..................#",
     "#..t....t..t....t..#",
     "#..................#",
     "#..................#",
     "#..................#",
     "#..................#",
     "#..................#",
     "#...$...k....%.....#"] + _FLOOR,
]
SHRINE = [
    ["####################",
     "#..................#",
     "#..t.....t.....t...#",
     "#..................#",
     "#..................#",
     "#....====..====....#",
     "#..................#",
     "#..................#",
     "#.....k.......b....#"] + _FLOOR,
]
TREASURE = [
    ["####################",
     "#..................#",
     "#..t...........t...#",
     "#..................#",
     "#..................#",
     "#..................#",
     "#...===......===...#",
     "#..................#",
     "#...?.........c....#"] + _FLOOR,
    ["####################",
     "#..................#",
     "#...t..........t...#",
     "#..................#",
     "#..................#",
     "#.......b..........#",
     "#..................#",
     "#..................#",
     "#..c.........a.....#",
     "####..######..######",
     "####^^######^^######",
     "####################"],
]
MARKERS = "tgsab?@k$%c"


def _check_template(tpl):
    assert len(tpl) == RH and all(len(r) == RW for r in tpl), tpl
    assert tpl[0] == "#" * RW and tpl[-1] == "#" * RW
    for r in range(RH):
        assert tpl[r][0] == "#" and tpl[r][-1] == "#"
    for r in (6, 7, 8):
        for c in (1, 2, 17, 18):
            assert tpl[r][c] not in "#^", (r, c)
    for c in (0, 1, 2, 8, 9, 10, 17, 18, 19):
        assert tpl[9][c] == "#", c
    for r in range(1, 9):
        assert tpl[r][9] in ".=" or tpl[r][9] in MARKERS, (r, tpl[r][9])
    for r in (7, 8):
        for c in (8, 9, 10):
            assert tpl[r][c] not in "#^=H", (r, c)


for _t in NORMAL + START + SHOP + SHRINE + TREASURE:
    _check_template(_t)


def _arena():
    rows = []
    for r in range(RH):
        if r == 0 or r >= 9:
            rows.append(["#"] * (AW * RW))
            continue
        row = ["#"] + ["."] * (AW * RW - 2) + ["#"]
        rows.append(row)
    for c in list(range(8, 12)) + list(range(28, 32)):
        rows[6][c] = "="
    for r in (6, 7, 8):
        rows[r][2] = "G"             # slams shut behind Akuma
    for r in range(1, 9):
        rows[r][35] = "X"            # opens when the Warden falls
    return ["".join(r) for r in rows]


ARENA = _arena()

# ---------------------------------------------------------------------------
# level
# ---------------------------------------------------------------------------


class Level:
    """The tile grid plus where everything goes."""

    def __init__(self, seed):
        self.seed = seed
        rng = random.Random("metroid %s" % seed)
        for _ in range(80):
            if self._build(rng):
                return
        raise RuntimeError("no completable layout for seed %s" % seed)

    # ---- tiles ------------------------------------------------------------
    def tile(self, c, r):
        if 0 <= r < ROWS and 0 <= c < COLS:
            return self.grid[r][c]
        return "#"

    def solid(self, c, r):
        t = self.tile(c, r)
        return t == "#" or (t == "G" and self.gate_in) or (t == "X" and self.gate_out)

    def ladder(self, c, r):
        return self.tile(c, r) in "Hh"

    def platform(self, c, r):
        t = self.tile(c, r)
        return t in "=h" or (t == "H" and self.tile(c, r - 1) not in "Hh")

    def support(self, c, r):
        return self.solid(c, r) or self.platform(c, r)

    def spike(self, c, r):
        return self.tile(c, r) == "^"

    def solid_px(self, x, y):
        return self.solid(int(x // T), int(y // T))

    # ---- build ------------------------------------------------------------
    def _build(self, rng):
        self.grid = [["#"] * COLS for _ in range(ROWS)]
        self.gate_in = False
        self.gate_out = True
        links = set()

        def link(a, b):
            links.add((min(a, b), max(a, b)))

        r = rng.randrange(GH)
        start = (0, r)
        path = [start]
        for c in range(GW):
            if 1 <= c <= GW - 2 and rng.random() < 0.55:
                r2 = rng.choice([x for x in range(GH) if x != r])
                d = 1 if r2 > r else -1
                for rr in range(r + d, r2 + d, d):
                    path.append((c, rr))
                    link((c, rr - d), (c, rr))
                r = r2
            if c < GW - 1:
                path.append((c + 1, r))
                link((c, r), (c + 1, r))
        pre = (GW - 1, r)
        self.arena_cell = (GW, r)
        link(pre, self.arena_cell)
        shop = next(p for p in path if p[0] == 3)
        roles = {p: "normal" for p in path}
        roles[start], roles[shop], roles[pre] = "start", "shop", "shrine"
        # dead-end side rooms
        cand = []
        for p in path:
            if roles[p] in ("start", "shrine"):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (p[0] + dx, p[1] + dy)
                if 0 <= q[0] < GW and 0 <= q[1] < GH and q not in roles:
                    cand.append((q, p))
        rng.shuffle(cand)
        branches = []
        for q, p in cand:
            if q in roles or len(branches) >= 3:
                continue
            roles[q] = "branch"
            branches.append(q)
            link(q, p)
        if len(branches) < 2:
            return False
        self.path, self.roles, self.links, self.branches = path, roles, links, branches
        # stamp the chunks
        self.spawns, self.torches, self.shrines, self.altars, self.rewards = [], [], [], [], []
        self.windows = []
        last = None
        for cell, role in roles.items():
            pool = {"start": START, "shop": SHOP, "shrine": SHRINE, "branch": TREASURE}.get(role, NORMAL)
            choices = [t for t in pool if t is not last] or pool
            tpl = rng.choice(choices)
            last = tpl
            self._stamp(cell, tpl, role, rng)
        self._stamp_arena(rng)
        for a, b in links:
            self._door(a, b)
        # order: shrines by distance along the path
        order = {p: i for i, p in enumerate(path)}
        self.shrines.sort(key=lambda s: order.get(s["cell"], 99))
        for i, s in enumerate(self.shrines):
            s["i"] = i
        kinds = ["str", "vit"]
        rng.shuffle(kinds)
        for i, rw in enumerate(sorted(self.rewards, key=lambda w: w["cell"])):
            rw["kind"] = kinds[i] if i < 2 else "chest"
        # completable? (every shrine, altar, reward and the boss can be walked to)
        reach = self.reachable(self.start_cell)
        need = [s["tile"] for s in self.shrines] + [a["tile"] for a in self.altars] + \
               [w["tile"] for w in self.rewards] + [self.boss_tile]
        return all(n in reach for n in need)

    def _stamp(self, cell, tpl, role, rng):
        ox, oy = cell[0] * RW, cell[1] * RH
        keep = 1.0 if role == "branch" else 0.8
        hard = cell[0] >= 3
        for r, row in enumerate(tpl):
            for c, ch in enumerate(row):
                gx, gy = ox + c, oy + r
                if ch in MARKERS:
                    self.grid[gy][gx] = "."
                    pos = (gx * T + T // 2, (gy + 1) * T)
                    if ch == "t":
                        self.torches.append((gx * T + T // 2, gy * T + T // 2))
                    elif ch == "@":
                        self.start = pos
                        self.start_cell = (gx, gy)
                    elif ch == "k":
                        self.shrines.append(dict(pos=pos, tile=(gx, gy), cell=cell))
                    elif ch in "$%":
                        self.altars.append(dict(pos=pos, tile=(gx, gy), kind="str" if ch == "$" else "vit"))
                    elif ch == "c":
                        self.rewards.append(dict(pos=pos, tile=(gx, gy), cell=cell))
                    elif rng.random() < keep and role not in ("start", "shop"):
                        kind = {"g": "grunt", "s": "shield", "a": "caster", "b": "bat"}.get(ch)
                        if kind is None:
                            kind = rng.choice(["grunt", "grunt", "shield", "caster"] if hard else
                                              ["grunt", "grunt", "grunt", "caster"])
                        if kind == "bat":
                            pos = (gx * T + T // 2, gy * T + T // 2)
                        self.spawns.append((kind, pos))
                else:
                    self.grid[gy][gx] = ch
        # one barred window per room high on the back wall
        for _ in range(rng.choice((1, 2))):
            self.windows.append((ox + rng.randrange(3, RW - 4), oy + rng.randrange(1, 4)))

    def _stamp_arena(self, rng):
        ox, oy = self.arena_cell[0] * RW, self.arena_cell[1] * RH
        for r, row in enumerate(ARENA):
            for c, ch in enumerate(row):
                self.grid[oy + r][ox + c] = ch
        for c in (5, 14, 25, 33):
            self.torches.append(((ox + c) * T + T // 2, (oy + 2) * T + T // 2))
        self.arena_x0 = ox * T
        self.arena_x1 = (ox + AW * RW) * T
        self.arena_floor = (oy + 9) * T
        self.boss_tile = (ox + 24, oy + 8)
        self.boss_pos = ((ox + 24) * T + T // 2, (oy + 9) * T)
        self.trigger_x = (ox + 7) * T
        self.exit_pos = ((ox + 37) * T + T // 2, (oy + 9) * T)
        self.exit_tile = (ox + 37, oy + 8)
        self.windows += [(ox + 10, oy + 2), (ox + 20, oy + 2), (ox + 30, oy + 2)]

    def _door(self, a, b):
        if a[1] == b[1]:            # a left of b
            for r in (6, 7, 8):
                self.grid[a[1] * RH + r][a[0] * RW + RW - 1] = "."
                self.grid[b[1] * RH + r][b[0] * RW] = "."
        else:                       # a above b: ladder through a's floor, down b's height
            c = a[0] * RW + 9
            top = a[1] * RH
            self.grid[top + 9][c] = "h"
            self.grid[top + 10][c] = "H"
            self.grid[top + 11][c] = "H"
            bt = b[1] * RH
            for r in range(0, 9):
                self.grid[bt + r][c] = "H"

    def room_of(self, x, y):
        return (int(x // (RW * T)), int(y // (RH * T)))

    # ---- walkability (used to keep layouts completable, and by the tests) --
    def stand(self, c, r):
        if self.solid(c, r) or self.solid(c, r - 1) or self.spike(c, r) or self.spike(c, r - 1):
            return False
        return self.support(c, r + 1) or self.ladder(c, r)

    def _fall(self, c, r):
        """Where a fall down column c starting in row r ends (None: spikes or nowhere)."""
        for rr in range(r, ROWS):
            if self.solid(c, rr) or self.spike(c, rr):
                return None
            if self.support(c, rr + 1) or self.ladder(c, rr):
                return (c, rr) if self.stand(c, rr) else None
        return None

    def moves(self, cell):
        c, r = cell
        out = []
        for dc in (-1, 1):
            if self.stand(c + dc, r):
                out.append((c + dc, r))
            elif not self.solid(c + dc, r) and not self.solid(c + dc, r - 1):
                f = self._fall(c + dc, r)
                if f:
                    out.append(f)
        if self.ladder(c, r) or self.ladder(c, r + 1):
            if self.ladder(c, r) and not self.solid(c, r - 2) and (self.ladder(c, r - 1) or self.stand(c, r - 1)):
                out.append((c, r - 1))
            if self.ladder(c, r + 1):
                out.append((c, r + 1))
        if self.platform(c, r + 1) and not self.solid(c, r + 1):
            f = self._fall(c, r + 2) if not self.ladder(c, r + 1) else None
            if f:
                out.append(f)
        if self.support(c, r + 1):          # jumps
            for rise, reach in ((0, 4), (1, 4), (2, 3), (3, 2)):
                if any(self.solid(c, r - 1 - k) for k in range(1, rise + 1)):
                    break
                tr = r - rise
                for dc in range(-reach, reach + 1):
                    if not dc and not rise:
                        continue
                    tc = c + dc
                    if not self.stand(tc, tr):
                        continue
                    step = 1 if dc >= 0 else -1
                    if all(not self.solid(x, tr) and not self.solid(x, tr - 1)
                           for x in range(c, tc + step, step)):
                        out.append((tc, tr))
        return out

    def reachable(self, start):
        seen = {start}
        q = deque([start])
        while q:
            cur = q.popleft()
            for n in self.moves(cur):
                if n not in seen:
                    seen.add(n)
                    q.append(n)
        return seen

    def path_to(self, start, goal):
        prev = {start: None}
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur == goal:
                out = []
                while cur is not None:
                    out.append(cur)
                    cur = prev[cur]
                return out[::-1]
            for n in self.moves(cur):
                if n not in prev:
                    prev[n] = cur
                    q.append(n)
        return None


# ---------------------------------------------------------------------------
# physics
# ---------------------------------------------------------------------------
def move_body(lv, b, w, h, drop=False):
    """Move a feet-anchored box by (vx, vy) against the tiles. Returns the side
    of a wall it ran into (-1 / 1) or 0."""
    hw = w / 2
    wall = 0
    if b.vx:
        b.x += b.vx
        r0, r1 = int((b.y - h) // T), int((b.y - 0.01) // T)
        if b.vx > 0:
            c = int((b.x + hw - 0.01) // T)
            if any(lv.solid(c, r) for r in range(r0, r1 + 1)):
                b.x, b.vx, wall = c * T - hw, 0.0, 1
        else:
            c = int((b.x - hw) // T)
            if any(lv.solid(c, r) for r in range(r0, r1 + 1)):
                b.x, b.vx, wall = (c + 1) * T + hw, 0.0, -1
    old = b.y
    b.y += b.vy
    b.on_ground = False
    c0, c1 = int((b.x - hw) // T), int((b.x + hw - 0.01) // T)
    if b.vy >= 0:
        r = int(b.y // T)
        top = r * T
        for c in range(c0, c1 + 1):
            if lv.solid(c, r) or (not drop and old <= top + 0.01 and lv.platform(c, r)):
                b.y, b.vy, b.on_ground = float(top), 0.0, True
                break
    else:
        r = int((b.y - h) // T)
        if any(lv.solid(c, r) for c in range(c0, c1 + 1)):
            b.y, b.vy = float((r + 1) * T + h), 0.0
    return wall


def line_of_sight(lv, x0, y0, x1, y1):
    n = int(max(abs(x1 - x0), abs(y1 - y0)) // 6) + 1
    for i in range(1, n):
        k = i / n
        if lv.solid_px(x0 + (x1 - x0) * k, y0 + (y1 - y0) * k):
            return False
    return True


# ---------------------------------------------------------------------------
# sprites
# ---------------------------------------------------------------------------
def _shrink(img, k, tint=None):
    w, h = img.get_size()
    size = (max(1, round(w * k)), max(1, round(h * k)))
    out = pygame.transform.smoothscale(img, size) if k != 1 else img.copy()
    m = pygame.mask.from_surface(out, 127)
    rgb = pygame.Surface(size, pygame.SRCALPHA)
    rgb.blit(out.convert(), (0, 0))
    clean = m.to_surface(setsurface=rgb, unsetcolor=(0, 0, 0, 0))
    if tint:
        mult, keep, add = tint
        g = pygame.transform.grayscale(clean)
        g.fill(mult, special_flags=pygame.BLEND_RGB_MULT)
        if keep:
            orig = clean.copy()
            orig.set_alpha(keep)
            g.blit(orig, (0, 0))
        if add:
            g.fill(add, special_flags=pygame.BLEND_RGB_ADD)
        clean = m.to_surface(setsurface=g, unsetcolor=(0, 0, 0, 0))
    return clean


TINTS = {
    "undead": ((150, 205, 140), 70, (6, 14, 4)),
    "steel": ((150, 170, 205), 60, (0, 4, 14)),
    "witch": ((200, 140, 230), 80, (16, 0, 24)),
    "warden": ((230, 120, 110), 110, (20, 0, 6)),
}


class SmallArt:
    """A sprite-pack character at platformer scale: smooth-scaled, alpha
    snapped to hard pixels, optionally tinted, cached per drawing."""

    _store = {}

    def __init__(self, cid, scale=SCALE, tint=None):
        self.char = CharArt(cid)
        self.cid = cid
        self.k = scale
        self.tint = tint
        self.c = SmallArt._store.setdefault((self.char.cid, scale, tint), {})

    def resolve(self, pose, t=0, clock=0, span=None):
        return self.char.resolve(pose, t, clock, span)

    def entry(self, key, flip=False):
        e = self.c.get((key, flip))
        if e is None:
            if flip:
                img, (ax, ay) = self.entry(key)
                e = (pygame.transform.flip(img, True, False), (img.get_width() - ax, ay))
            else:
                img, (ax, ay) = self.char.entry(key)
                e = (_shrink(img, self.k, TINTS.get(self.tint)), (round(ax * self.k), round(ay * self.k)))
            self.c[(key, flip)] = e
        return e

    def frame(self, key, flip=False):
        return self.entry(key, flip)[0]

    def flash(self, key, flip=False, color=(255, 255, 255)):
        ck = ("flash", key, flip, color)
        s = self.c.get(ck)
        if s is None:
            s = self.c[ck] = pygame.mask.from_surface(self.frame(key, flip), 127).to_surface(
                setcolor=color + (255,), unsetcolor=(0, 0, 0, 0))
        return s

    def mask(self, key, flip=False):
        ck = ("mask", key, flip)
        m = self.c.get(ck)
        if m is None:
            m = self.c[ck] = pygame.mask.from_surface(self.frame(key, flip), 127)
        return m

    def strike(self, key, flip=False, both=False):
        """The hitting part of an attack drawing (the sprite pack's strike mask,
        scaled down), or None when the drawing has no fist or foot sticking out."""
        ck = ("strike", key, flip, both)
        if ck not in self.c:
            m = self.char.strike_mask(key, flip, both).scale(self.frame(key, flip).get_size())
            self.c[ck] = m if m.count() >= 4 else None
        return self.c[ck]

    def rotated(self, key, flip, deg):
        ck = ("rot", key, flip, deg)
        s = self.c.get(ck)
        if s is None:
            s = self.c[ck] = pygame.transform.rotate(self.frame(key, flip), deg)
        return s


_PROJ = {}


def _proj_frames(cid, k, tint=None):
    key = (cid, k, tint)
    if key not in _PROJ:
        _PROJ[key] = [_shrink(f, k, TINTS.get(tint)) for f in hado_frames(cid)]
    return _PROJ[key]


# ---------------------------------------------------------------------------
# pixel art made in code
# ---------------------------------------------------------------------------
_ART = {}


def _px(s, pts, col):
    for x, y in pts:
        s.set_at((x, y), col)


def _bat_frames():
    out = []
    bone, dark, wing, wing2 = (226, 214, 190), (40, 26, 30), (70, 34, 80), (110, 56, 120)
    for wy in (-3, 0, 3):
        s = pygame.Surface((22, 14), pygame.SRCALPHA)
        for side in (-1, 1):
            cx = 11 + side * 3
            tip = (11 + side * 10, 5 + wy)
            pygame.draw.polygon(s, wing, [(cx, 4), tip, (11 + side * 8, 8 + wy // 2), (cx, 8)])
            pygame.draw.line(s, wing2, (cx, 4), tip)
        pygame.draw.ellipse(s, bone, (7, 2, 8, 8))
        s.fill(bone, (8, 8, 6, 3))
        s.fill(dark, (8, 5, 2, 2))
        s.fill(dark, (12, 5, 2, 2))
        s.set_at((9, 6), (255, 60, 40))
        s.set_at((13, 6), (255, 60, 40))
        _px(s, [(9, 10), (11, 10), (13, 10)], dark)
        out.append(_outline(s))
    return out


def _outline(s):
    m = pygame.mask.from_surface(s, 1)
    out = pygame.Surface((s.get_width() + 2, s.get_height() + 2), pygame.SRCALPHA)
    sil = m.to_surface(setcolor=OUTLINE + (255,), unsetcolor=(0, 0, 0, 0))
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
        out.blit(sil, (dx, dy))
    out.blit(s, (1, 1))
    return out


def _shield_img():
    s = pygame.Surface((9, 24), pygame.SRCALPHA)
    pygame.draw.rect(s, (70, 76, 92), (0, 0, 9, 24), border_radius=2)
    pygame.draw.rect(s, (120, 128, 146), (1, 1, 7, 22), border_radius=2)
    s.fill((92, 98, 116), (3, 2, 3, 20))
    for y in (3, 11, 20):
        s.set_at((2, y), (200, 200, 210))
        s.set_at((6, y), (200, 200, 210))
    s.fill((150, 40, 40), (3, 9, 3, 5))
    return _outline(s)


def _chest(open_):
    s = pygame.Surface((18, 14), pygame.SRCALPHA)
    wood, band, gold = (110, 66, 36), (60, 40, 30), (230, 190, 70)
    s.fill(wood, (1, 6, 16, 8))
    s.fill(band, (1, 9, 16, 1))
    if open_:
        s.fill((40, 20, 12), (2, 4, 14, 3))
        s.fill(wood, (1, 0, 16, 4))
        s.fill((255, 230, 120), (4, 5, 10, 1))
    else:
        s.fill(wood, (1, 2, 16, 5))
        s.fill((140, 86, 48), (2, 2, 14, 1))
        s.fill(gold, (8, 6, 2, 3))
    s.fill(band, (4, 2, 1, 12))
    s.fill(band, (13, 2, 1, 12))
    return _outline(s)


def _shrine(lit):
    s = pygame.Surface((18, 30), pygame.SRCALPHA)
    stone, dark, hi = (88, 82, 100), (50, 46, 60), (130, 124, 140)
    s.fill(dark, (2, 22, 14, 8))
    s.fill(stone, (3, 22, 12, 7))
    s.fill(stone, (6, 10, 6, 12))
    s.fill(hi, (6, 10, 1, 12))
    pygame.draw.polygon(s, stone, [(1, 10), (17, 10), (14, 6), (4, 6)])
    s.fill(hi, (4, 6, 10, 1))
    rune = (120, 230, 255) if lit else (60, 60, 80)
    s.fill(rune, (8, 13, 2, 2))
    s.fill(rune, (8, 17, 2, 3))
    s.fill(rune, (5, 25, 8, 1))
    return _outline(s)


def _altar(kind):
    s = pygame.Surface((18, 22), pygame.SRCALPHA)
    stone, hi = (80, 74, 92), (124, 118, 134)
    s.fill(stone, (2, 8, 14, 14))
    s.fill(hi, (2, 8, 14, 1))
    s.fill(stone, (0, 6, 18, 3))
    s.fill(hi, (0, 6, 18, 1))
    if kind == "str":   # a red fist
        s.fill((230, 60, 50), (6, 12, 6, 6))
        s.fill((255, 140, 120), (6, 12, 6, 1))
        s.fill((150, 30, 30), (7, 14, 1, 3))
        s.fill((150, 30, 30), (9, 14, 1, 3))
    else:               # a green heart
        col = (80, 220, 110)
        s.fill(col, (6, 12, 2, 2))
        s.fill(col, (10, 12, 2, 2))
        s.fill(col, (5, 13, 8, 2))
        s.fill(col, (6, 15, 6, 1))
        s.fill(col, (7, 16, 4, 1))
        s.fill(col, (8, 17, 2, 1))
    return _outline(s)


def _scroll(kind):
    s = pygame.Surface((12, 12), pygame.SRCALPHA)
    s.fill((236, 216, 170), (2, 2, 8, 8))
    s.fill((200, 170, 120), (1, 1, 10, 2))
    s.fill((200, 170, 120), (1, 9, 10, 2))
    seal = (230, 60, 50) if kind == "str" else (70, 210, 100)
    s.fill(seal, (4, 4, 4, 4))
    s.fill((255, 255, 255), (4, 4, 1, 1))
    return _outline(s)


def _flask(full):
    s = pygame.Surface((7, 10), pygame.SRCALPHA)
    glass = (150, 150, 170)
    s.fill((120, 80, 50), (2, 0, 3, 2))
    s.fill(glass, (2, 2, 3, 2))
    pygame.draw.circle(s, glass, (3, 6), 3)
    if full:
        pygame.draw.circle(s, (220, 30, 50), (3, 6), 2)
        s.set_at((2, 5), (255, 160, 170))
    else:
        pygame.draw.circle(s, (30, 26, 40), (3, 6), 2)
    return s


def _cell():
    s = pygame.Surface((6, 6), pygame.SRCALPHA)
    pygame.draw.circle(s, (40, 120, 255, 140), (3, 3), 3)
    s.fill((120, 200, 255), (2, 2, 2, 2))
    s.set_at((2, 2), (240, 250, 255))
    return s


def _glow(r, col):
    s = pygame.Surface((r * 2, r * 2))
    s.fill((0, 0, 0))
    for i in range(r, 0, -1):
        k = (1 - i / r) ** 1.6
        pygame.draw.circle(s, tuple(int(c * k) for c in col), (r, r), i)
    return s


def _gate_tile():
    s = pygame.Surface((T, T), pygame.SRCALPHA)
    for x in (2, 7, 12):
        s.fill((40, 38, 48), (x, 0, 3, T))
        s.fill((110, 106, 120), (x, 0, 1, T))
    s.fill((60, 56, 70), (0, 6, T, 2))
    return s


def _door(open_):
    s = pygame.Surface((30, 48), pygame.SRCALPHA)
    pygame.draw.rect(s, (60, 54, 72), (0, 8, 30, 40))
    pygame.draw.ellipse(s, (60, 54, 72), (0, 0, 30, 18))
    inner = (255, 230, 150) if open_ else (14, 10, 20)
    pygame.draw.rect(s, inner, (4, 10, 22, 38))
    pygame.draw.ellipse(s, inner, (4, 3, 22, 16))
    if open_:
        pygame.draw.rect(s, (255, 250, 220), (9, 14, 12, 34))
    return s


def _far_layer(rng):
    s = pygame.Surface((W, H))
    for y in range(H):
        k = y / H
        s.fill((int(10 + 22 * k), int(8 + 10 * k), int(22 + 22 * k)), (0, y, W, 1))
    for _ in range(40):
        s.set_at((rng.randrange(W), rng.randrange(H // 2)), (90, 80, 120))
    pygame.draw.circle(s, (40, 34, 58), (248, 36), 22)
    pygame.draw.circle(s, (206, 196, 176), (248, 36), 13)
    pygame.draw.circle(s, (176, 166, 150), (252, 32), 4)
    sil = (24, 18, 36)
    x = 0
    while x < W:
        w = rng.randrange(14, 34)
        top = rng.randrange(70, 120)
        for xx in range(x, x + w):
            s.fill(sil, (xx % W, top, 1, H - top))
        for cx in range(x, x + w, 4):
            s.fill(sil, (cx % W, top - 3, 2, 3))
        if rng.random() < 0.4:
            s.fill(sil, ((x + w // 2 - 4) % W, top - 18, 8, 18))
            pygame.draw.polygon(s, sil, [((x + w // 2 - 6) % W, top - 18), ((x + w // 2) % W, top - 30),
                                         ((x + w // 2 + 6) % W, top - 18)])
        for _ in range(rng.randrange(0, 3)):
            s.fill((150, 110, 50), ((x + rng.randrange(2, max(3, w - 2))) % W, top + rng.randrange(6, 30), 1, 2))
        x += w + rng.randrange(0, 10)
    return s


def _mid_layer(rng):
    w = 480
    s = pygame.Surface((w, H + 60), pygame.SRCALPHA)
    col, hi = (30, 24, 42, 255), (44, 36, 58, 255)
    for i in range(4):
        px = i * 120 + 10
        s.fill(col, (px, 0, 22, H + 60))
        s.fill(hi, (px, 0, 3, H + 60))
        for y in range(0, H + 60, 12):
            s.fill((24, 18, 34, 255), (px, y, 22, 1))
        pygame.draw.arc(s, col, (px + 11, -40, 120, 120), 0, math.pi, 10)
        cx = px + 70
        for y in range(0, rng.randrange(40, 90), 4):
            s.fill((50, 46, 60, 255), (cx + (y // 4) % 2, y, 2, 3))
    return s


def _vignette():
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    for i in range(24):
        a = int(110 * (1 - i / 24) ** 2)
        pygame.draw.rect(s, (0, 0, 0, a), (i, i, W - 2 * i, H - 2 * i), 1)
    return s


def _level_surface(lv, rng):
    """Every tile drawn once: back wall, stone, planks, ladders, spikes."""
    s = pygame.Surface((LW, LH), pygame.SRCALPHA)
    brick, mortar = (30, 24, 40, 205), (20, 16, 28, 225)
    for r in range(ROWS):
        for c in range(COLS):
            if lv.grid[r][c] == "#":
                continue
            x, y = c * T, r * T
            s.fill(brick, (x, y, T, T))
            s.fill(mortar, (x, y + 7, T, 1))
            s.fill(mortar, (x, y + 15, T, 1))
            s.fill(mortar, (x + (0 if (r % 2) else 8), y, 1, 7))
            s.fill(mortar, (x + (8 if (r % 2) else 0), y + 8, 1, 7))
            if rng.random() < 0.06:
                s.fill((36, 44, 34, 200), (x + rng.randrange(12), y + rng.randrange(12), 3, 2))
    for c, r in lv.windows:
        if lv.grid[r][c] != "#" and lv.grid[r + 1][c] != "#":
            x, y = c * T + 2, r * T + 2
            s.fill((0, 0, 0, 0), (x, y, 12, 22))
            pygame.draw.rect(s, (60, 52, 70, 255), (x - 1, y - 1, 14, 24), 1)
            for bx in (x + 3, x + 7):
                s.fill((50, 44, 60, 255), (bx, y, 2, 22))
    stone, stone2, mort = (52, 46, 64), (60, 54, 72), (30, 26, 38)
    deep = (20, 16, 26)
    for r in range(ROWS):
        for c in range(COLS):
            t = lv.grid[r][c]
            x, y = c * T, r * T
            if t == "#":
                exposed = [lv.tile(c, r - 1) != "#", lv.tile(c, r + 1) != "#",
                           lv.tile(c - 1, r) != "#", lv.tile(c + 1, r) != "#"]
                near = any(lv.tile(c + dx, r + dy) != "#" for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                if not near:
                    s.fill(deep, (x, y, T, T))
                    if rng.random() < 0.05:
                        s.fill((26, 22, 34), (x + rng.randrange(10), y + rng.randrange(10), 4, 3))
                    continue
                s.fill(stone if (c + r) % 3 else stone2, (x, y, T, T))
                s.fill(mort, (x, y + 7, T, 1))
                s.fill(mort, (x, y + 15, T, 1))
                s.fill(mort, (x + (4 if r % 2 else 12), y, 1, 7))
                s.fill(mort, (x + (12 if r % 2 else 4), y + 8, 1, 7))
                if rng.random() < 0.3:
                    s.fill((44, 38, 54), (x + 1, y + 1 + 8 * rng.randrange(2), 6, 5))
                if exposed[0]:
                    s.fill((104, 96, 118), (x, y, T, 2))
                    s.fill((76, 70, 90), (x, y + 2, T, 1))
                    for _ in range(3):
                        if rng.random() < 0.6:
                            mx = x + rng.randrange(T - 2)
                            s.fill((58, 100, 60), (mx, y, rng.randrange(2, 5), 1))
                            if rng.random() < 0.3:
                                s.fill((48, 84, 52), (mx + 1, y + 1, 1, rng.randrange(2, 5)))
                if exposed[1]:
                    s.fill((18, 14, 22), (x, y + T - 2, T, 2))
                if exposed[2]:
                    s.fill((80, 72, 94), (x, y, 1, T))
                if exposed[3]:
                    s.fill((28, 22, 34), (x + T - 1, y, 1, T))
            elif t == "=":
                s.fill((112, 74, 44), (x, y, T, 4))
                s.fill((150, 104, 62), (x, y, T, 1))
                s.fill((70, 44, 28), (x, y + 4, T, 1))
                s.fill((70, 44, 28), (x + 7, y, 1, 4))
                if lv.tile(c - 1, r) != "=":
                    s.fill((60, 40, 26), (x + 1, y + 4, 2, 5))
                if lv.tile(c + 1, r) != "=":
                    s.fill((60, 40, 26), (x + T - 3, y + 4, 2, 5))
            elif t in "Hh":
                s.fill((92, 62, 36), (x + 3, y, 2, T))
                s.fill((92, 62, 36), (x + 11, y, 2, T))
                s.fill((126, 88, 52), (x + 3, y, 1, T))
                for ry in (2, 7, 12):
                    s.fill((120, 84, 48), (x + 3, y + ry, 10, 2))
                if t == "h":
                    s.fill((80, 70, 90), (x, y, 3, 2))
                    s.fill((80, 70, 90), (x + T - 3, y, 3, 2))
            elif t == "^":
                for k in range(4):
                    bx = x + k * 4
                    pygame.draw.polygon(s, (150, 150, 165), [(bx, y + T), (bx + 2, y + 6), (bx + 4, y + T)])
                    s.set_at((bx + 2, y + 6), (230, 70, 60))
                    s.set_at((bx + 2, y + 7), (190, 60, 60))
    return s


def _art():
    if not _ART:
        a = _ART
        a["bat"] = _bat_frames()
        a["shield"] = _shield_img()
        a["chest"] = (_chest(False), _chest(True))
        a["shrine"] = (_shrine(False), _shrine(True))
        a["altar"] = {"str": _altar("str"), "vit": _altar("vit")}
        a["scroll"] = {"str": _scroll("str"), "vit": _scroll("vit")}
        a["flask"] = (_flask(False), _flask(True))
        a["cell"] = _cell()
        a["glow"] = [_glow(r, (120, 64, 22)) for r in (34, 37, 40)]
        a["glow_blue"] = _glow(22, (20, 60, 110))
        a["glow_red"] = _glow(30, (120, 20, 20))
        a["gate"] = _gate_tile()
        a["door"] = (_door(False), _door(True))
        a["vignette"] = _vignette()
        a["hado"] = _proj_frames("akuma", 0.5)
        a["fire"] = _proj_frames("lubu", 0.55, "warden")
    return _ART


_SFX_DONE = False


def _build_sounds():
    """This level's own synthesised cues, added to the shared table once
    (audio.play() of a missing name is silent, so this is optional)."""
    global _SFX_DONE
    if _SFX_DONE or not getattr(audio, "_ok", False):
        return
    _SFX_DONE = True
    S, tone, noise, add = audio._sfx, audio._tone, audio._noise, audio._add
    try:
        S.setdefault("mv_roll", audio._sound(noise(0.16, 0.25, 1.2, 0.12)))
        S.setdefault("mv_flask", audio._sound(add(tone(500, 900, 0.18, 0.18, "tri"), tone(750, 1300, 0.22, 0.12, "tri"))))
        S.setdefault("mv_shrine", audio._sound(add(tone(440, 440, 0.5, 0.15, "tri"), tone(660, 660, 0.5, 0.12, "tri"))))
        S.setdefault("mv_cell", audio._sound(tone(1500, 2100, 0.05, 0.08, "square", 0, 0.25)))
        S.setdefault("mv_gate", audio._sound(add(noise(0.4, 0.45, 1.5, 0.15), tone(90, 50, 0.4, 0.3, "square", 0.3))))
        S.setdefault("mv_roar", audio._sound(add(tone(120, 70, 0.8, 0.35, "square", 0.45, 0.4), noise(0.8, 0.3, 1.0, 0.2))))
        S.setdefault("mv_slam", audio._sound(add(noise(0.35, 0.7, 1.8, 0.2), tone(80, 30, 0.3, 0.5, "square", 0.2))))
        S.setdefault("mv_tell", audio._sound(tone(1200, 1250, 0.05, 0.1, "square", 0, 0.5)))
        S.setdefault("mv_buy", audio._sound(add(tone(660, 660, 0.08, 0.2), tone(990, 990, 0.2, 0.2, "tri"))))
        S.setdefault("mv_bolt", audio._sound(tone(700, 300, 0.2, 0.15, "tri", 0.2)))
    except Exception:       # never let a sound break the level
        pass


# ---------------------------------------------------------------------------
# actors
# ---------------------------------------------------------------------------
# Akuma's moves: phases (kind, frames, pose); kind s(tartup) a(ctive) r(ecovery)
MOVES = {
    "jab1": dict(ph=[("s", 4, "punch_prep"), ("a", 5, "punch"), ("r", 9, "punch_rec")], dmg=10, kb=1.4, lunge=1.3),
    "jab2": dict(ph=[("s", 3, "punch_prep"), ("a", 5, "punch"), ("r", 9, "punch_rec")], dmg=11, kb=1.4, lunge=1.3),
    "jab3": dict(ph=[("s", 6, "sho_crouch"), ("a", 9, "sho_rise"), ("r", 14, "sho_fall")], dmg=18, kb=3.0,
                 lunge=1.8, hop=-2.6, heavy=True),
    "kick": dict(ph=[("s", 10, "kick_prep"), ("a", 7, "kick"), ("r", 14, "kick_rec")], dmg=26, kb=3.4,
                 lunge=0.8, heavy=True, guard_break=True),
    "sweep": dict(ph=[("s", 6, "sweep_prep"), ("a", 7, "sweep"), ("r", 14, "sweep_rec")], dmg=16, kb=2.2, lunge=1.0),
    "ajab": dict(ph=[("s", 2, "jpunch_prep"), ("a", 10, "jump_jab"), ("r", 4, "jump")], dmg=10, kb=1.4, air=True),
    "akick": dict(ph=[("s", 3, "jkick_prep"), ("a", 12, "jump_kick"), ("r", 4, "jump")], dmg=16, kb=2.4, air=True),
    "dive": dict(ph=[("s", 5, "jump"), ("a", 90, "dive"), ("r", 10, "land")], dmg=22, kb=2.0, air=True, dive=True,
                 guard_break=True),
    "hado": dict(ph=[("s", 10, "hado_prep"), ("a", 4, "hado_fire"), ("r", 14, "hado_fire")], dmg=20, proj=True),
    "ahado": dict(ph=[("s", 6, "air_hado_prep"), ("a", 4, "air_hado"), ("r", 10, "jump")], dmg=18, proj=True,
                  air=True),
}
COMBO = {"jab1": "jab2", "jab2": "jab3"}


class Hero:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.face = 1
        self.on_ground = False
        self.state = "move"         # move ladder roll attack hurt drink dead
        self.t = 0
        self.coyote = 0
        self.jbuf = 0
        self.drop = 0
        self.roll_cd = 0
        self.roll_dir = 1
        self.inv = 0
        self.move = None
        self.ph = 0
        self.ph_t = 0
        self.hit_set = set()
        self.abuf = None
        self.combo_t = 0
        self.last = None
        self.walked = 0.0
        self.air_t = 0
        self.climbed = 0.0
        self.down_tap = 0
        self.safe = (x, y)

    @property
    def h(self):
        return ROLL_H if self.state == "roll" else PH

    def rolling_safe(self):
        return self.state == "roll" and ROLL_IFRAMES[0] <= self.t < ROLL_IFRAMES[1]


class Enemy:
    kind = "grunt"
    HP, BW, BH, SPEED, CELLS, REACH = 45, 12, 26, 0.85, 3, 26
    SIGHT = 130

    def __init__(self, sc, x, y, cid, scale=SCALE, tint="undead"):
        self.sc = sc
        self.art = SmallArt(cid, scale, tint) if cid else None
        self.x, self.y = float(x), float(y)
        self.home = (x, y)
        self.vx = self.vy = 0.0
        self.face = sc.rng.choice((-1, 1))
        self.on_ground = False
        self.hp = self.max_hp = self.HP
        self.state = "patrol"
        self.t = 0
        self.pose, self.pose_t, self.span = "walk", 0, None
        self.flash = 0
        self.cd = sc.rng.randrange(20, 60)
        self.hit_done = False
        self.dead_t = 0
        self.gone = False
        self.aggro = False
        self.uid = sc.next_uid()

    # ---- drawing / areas --------------------------------------------------
    def key(self):
        return self.art.resolve(self.pose, self.pose_t, self.sc.t, self.span)

    def body_area(self):
        key = self.key()
        img, (ax, ay) = self.art.entry(key, self.face < 0)
        return self.art.mask(key, self.face < 0), round(self.x - ax), round(self.y - ay)

    def strike_area(self, both=False):
        key = self.key()
        flip = self.face < 0
        m = self.art.strike(key, flip, both)
        if m is None:
            return rect_area((self.x + (4 if self.face > 0 else -4 - self.REACH), self.y - 22, self.REACH, 14))
        img, (ax, ay) = self.art.entry(key, flip)
        return m, round(self.x - ax), round(self.y - ay)

    @property
    def alive(self):
        return self.state != "dead"

    def set_pose(self, pose, span=None):
        if pose != self.pose:
            self.pose, self.pose_t = pose, 0
        self.span = span

    def telegraphing(self):
        return self.state == "windup"

    # ---- behaviour --------------------------------------------------------
    def sees(self, rng=None):
        p = self.sc.p
        rng = rng or self.SIGHT
        dx, dy = p.x - self.x, p.y - self.y
        if abs(dx) > rng or abs(dy) > 56 or self.sc.p.state == "dead":
            return False
        if dx * self.face < -40 and not self.aggro:
            return False
        return line_of_sight(self.sc.lv, self.x, self.y - 18, p.x, p.y - 18)

    def ground_ahead(self, d):
        lv = self.sc.lv
        c = int((self.x + d * (self.BW / 2 + 2)) // T)
        r = int(self.y // T)
        return lv.support(c, r) and not lv.spike(c, r - 1) and not lv.solid(c, r - 1) and not lv.solid(c, r - 2)

    def walk(self, d, speed):
        if d and self.ground_ahead(d):
            self.vx = d * speed
        else:
            self.vx = 0.0

    def physics(self):
        self.vy = min(MAX_FALL, self.vy + GRAV)
        move_body(self.sc.lv, self, self.BW, self.BH)
        self.vx *= 0.8 if self.on_ground else 0.98
        lv = self.sc.lv
        if lv.spike(int(self.x // T), int((self.y - 1) // T)) and self.alive:
            self.hurt(999, 0, None)

    def update(self):
        self.t += 1
        self.pose_t += 1
        if self.flash:
            self.flash -= 1
        if self.state == "dead":
            self.dead_t += 1
            self.set_pose("down" if self.dead_t > 12 else "launch")
            self.physics()
            if self.dead_t > 70:
                self.gone = True
            return
        if self.state == "hurt":
            self.set_pose("hurt", 14)
            self.physics()
            if self.t >= 14:
                self.state, self.t = "chase", 0
            return
        self.think()
        self.physics()

    def think(self):
        p = self.sc.p
        dx = p.x - self.x
        if self.cd:
            self.cd -= 1
        st = self.state
        if st == "patrol":
            self.set_pose("walk")
            if not self.ground_ahead(self.face) or self.t > 160:
                self.face = -self.face
                self.t = 0
            self.walk(self.face, self.SPEED * 0.5)
            if self.sees():
                self.aggro = True
                self.state, self.t = "chase", 0
        elif st == "chase":
            self.face = 1 if dx > 0 else -1
            if not self.sees(self.SIGHT + 70):
                if self.t > 120:
                    self.state, self.t, self.aggro = "patrol", 0, False
            else:
                self.t = 0
            if abs(dx) > self.REACH + 4 or abs(p.y - self.y) > 30:
                self.set_pose("walk")
                self.walk(self.face, self.SPEED)
            else:
                self.set_pose("idle")
                if not self.cd and abs(p.y - self.y) < 30 and p.state != "dead":
                    self.start_windup()
        elif st == "windup":
            self.windup()
        elif st == "attack":
            self.attack()
        elif st == "recover":
            self.set_pose(self.rec_pose, self.rec_t)
            if self.t >= self.rec_t:
                self.state, self.t, self.cd = "chase", 0, self.sc.rng.randrange(20, 50)

    # melee: windup (flashing) -> active -> recover
    WIND_POSE, HIT_POSE, REC_POSE, ACTIVE = "punch_prep", "punch", "punch_rec", 8

    def start_windup(self):
        self.state, self.t = "windup", 0
        self.wind_t = TELEGRAPH[self.kind]
        self.sc.event("windup", self)
        audio.play("mv_tell", 0.5)

    def windup(self):
        self.set_pose(self.WIND_POSE, self.wind_t)
        self.vx = 0
        if self.t >= self.wind_t:
            self.state, self.t = "attack", 0
            self.hit_done = False
            self.vx = self.face * 1.6
            audio.play("whiff", 0.6)

    def attack(self):
        self.set_pose(self.HIT_POSE, self.ACTIVE)
        if not self.hit_done and touches(self.strike_area(), self.sc.hero_area()):
            if self.sc.hurt_player(DMG[self.kind], self):
                self.hit_done = True
        if self.t >= self.ACTIVE:
            self.state, self.t = "recover", 0
            self.rec_pose, self.rec_t = self.REC_POSE, 30

    def hurt(self, dmg, kb, move):
        """Returns the damage dealt."""
        self.hp -= dmg
        self.flash = 6
        self.aggro = True
        if self.hp <= 0:
            self.state, self.t = "dead", 0
            self.vx, self.vy = kb * 1.2, -2.5
            self.sc.enemy_died(self)
        else:
            self.state, self.t = "hurt", 0
            self.vx = kb
            if move and MOVES[move].get("hop"):
                self.vy = -2.0
        return dmg

    def draw(self, surf, ox, oy):
        key = self.key()
        flip = self.face < 0
        img, (ax, ay) = self.art.entry(key, flip)
        if self.state == "dead" and self.dead_t > 40 and (self.dead_t // 3) % 2:
            return
        if self.flash and self.flash % 2:
            img = self.art.flash(key, flip)
        elif self.state == "windup" and self.tell_flash():
            img = self.art.flash(key, flip, (255, 236, 160))
        surf.blit(img, (round(self.x - ax - ox), round(self.y - ay - oy)))
        if self.state == "windup" and self.t < 18:
            self.sc.draw_alert(surf, self.x - ox, self.y - img.get_height() - 6 - oy)
        if self.alive and self.hp < self.max_hp:
            w = 18
            bx, by = round(self.x - w / 2 - ox), round(self.y - img.get_height() - 4 - oy)
            surf.fill((30, 8, 10), (bx, by, w, 2))
            surf.fill((220, 50, 40), (bx, by, round(w * self.hp / self.max_hp), 2))

    def tell_flash(self):
        left = self.wind_t - self.t
        return (left < self.wind_t * 0.6 and (self.t // 3) % 2 == 0) or left < 4


class Grunt(Enemy):
    kind = "grunt"


class Shield(Enemy):
    kind = "shield"
    HP, BW, BH, SPEED, CELLS, REACH = 90, 16, 30, 0.55, 6, 30
    WIND_POSE, HIT_POSE, REC_POSE, ACTIVE = "hammer_up", "hammer_down", "punch_rec", 9

    def __init__(self, sc, x, y):
        super().__init__(sc, x, y, "zangief", 0.42, "steel")
        self.broken = 0

    def guarding(self):
        return self.state in ("patrol", "chase", "recover") and not self.broken

    def update(self):
        if self.broken:
            self.broken -= 1
        super().update()

    def think(self):
        if self.broken:
            self.set_pose("hurt", 20)
            self.vx = 0
            return
        super().think()

    def draw(self, surf, ox, oy):
        sh = _art()["shield"]
        if self.guarding() and self.alive:
            if self.face > 0:
                pos = (round(self.x + 6 - ox), round(self.y - 30 - oy))
            else:
                pos = (round(self.x - 6 - sh.get_width() - ox), round(self.y - 30 - oy))
            surf.blit(sh if self.face > 0 else pygame.transform.flip(sh, True, False), pos)
            super().draw(surf, ox, oy)
            surf.blit(sh if self.face > 0 else pygame.transform.flip(sh, True, False), pos)
        else:
            super().draw(surf, ox, oy)


class Caster(Enemy):
    kind = "caster"
    HP, BW, BH, SPEED, CELLS, REACH = 32, 12, 26, 0.6, 4, 20
    SIGHT = 190

    def __init__(self, sc, x, y):
        super().__init__(sc, x, y, "hsienko", SCALE, "witch")

    def think(self):
        p = self.sc.p
        dx = p.x - self.x
        if self.cd:
            self.cd -= 1
        st = self.state
        if st in ("patrol", "chase"):
            seen = self.sees()
            if seen:
                self.aggro = True
            if self.aggro and seen:
                self.face = 1 if dx > 0 else -1
                if abs(dx) < 56:
                    self.set_pose("walk_back")
                    self.walk(-self.face, self.SPEED)
                else:
                    self.set_pose("idle")
                    self.vx = 0
                if not self.cd:
                    self.start_windup()
            else:
                self.set_pose("idle")
                self.vx = 0
                if self.t > 200:
                    self.aggro = False
        elif st == "windup":
            self.set_pose("hado_prep", self.wind_t)
            self.vx = 0
            if self.t >= self.wind_t:
                self.state, self.t = "attack", 0
                hx, hy = self.x + self.face * 10, self.y - 18
                tx, ty = p.x, p.y - 14
                a = math.atan2(ty - hy, tx - hx)
                self.sc.spawn_proj(hx, hy, math.cos(a) * 1.9, math.sin(a) * 1.9, "bolt", DMG["bolt"], False, self)
                audio.play("mv_bolt")
        elif st == "attack":
            self.set_pose("hado_fire", 10)
            if self.t >= 10:
                self.state, self.t, self.cd = "recover", 0, 110
                self.rec_pose, self.rec_t = "idle", 24
        elif st == "recover":
            self.set_pose("idle")
            if self.t >= self.rec_t:
                self.state, self.t = "chase", 0

    def draw(self, surf, ox, oy):
        super().draw(surf, ox, oy)
        if self.state == "windup" and self.alive:
            k = self.t / max(1, self.wind_t)
            r = 1 + round(4 * k)
            cx, cy = round(self.x + self.face * 10 - ox), round(self.y - 18 - oy)
            pygame.draw.circle(surf, (120, 40, 160), (cx, cy), r + 1)
            pygame.draw.circle(surf, (230, 150, 255), (cx, cy), r)


class Bat(Enemy):
    kind = "bat"
    HP, BW, BH, CELLS = 16, 12, 10, 2

    def __init__(self, sc, x, y):
        super().__init__(sc, x, y, None)
        self.state = "sleep"
        self.y0 = y
        self.cd = 60

    def body_area(self):
        return rect_area((self.x - 7, self.y - 6, 14, 10))

    def strike_area(self, both=False):
        return rect_area((self.x - 5, self.y - 4, 10, 8))

    def physics(self):
        self.x += self.vx
        self.y += self.vy
        self.x = max(4, min(LW - 4, self.x))
        self.y = max(4, min(LH - 4, self.y))

    def update(self):
        self.t += 1
        if self.flash:
            self.flash -= 1
        if self.state == "dead":
            self.dead_t += 1
            self.vy = min(4, self.vy + 0.25)
            self.y += self.vy
            if self.dead_t > 40:
                self.gone = True
            return
        if self.state == "hurt":
            self.vx *= 0.85
            self.vy *= 0.85
            self.physics()
            if self.t > 12:
                self.state, self.t = "hover", 0
            return
        p = self.sc.p
        tx, ty = p.x, p.y - 14
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy)
        if self.state == "sleep":
            self.y = self.y0 + math.sin(self.sc.t / 20) * 1.5
            if dist < 110 and p.state != "dead":
                self.state, self.t = "hover", 0
            return
        if self.state == "hover":
            gx = tx - (36 if self.x < tx else -36)
            gy = ty - 34
            ax, ay = gx - self.x, gy - self.y
            d = math.hypot(ax, ay) or 1
            self.vx += ax / d * 0.09
            self.vy += ay / d * 0.09 + math.sin(self.t / 6) * 0.05
            sp = math.hypot(self.vx, self.vy)
            if sp > 1.3:
                self.vx, self.vy = self.vx / sp * 1.3, self.vy / sp * 1.3
            self.face = 1 if dx > 0 else -1
            if self.cd:
                self.cd -= 1
            elif dist < 90 and p.state != "dead":
                self.start_windup()
            if dist > 260:
                self.state = "sleep"
                self.x, self.y = self.home
        elif self.state == "windup":
            self.vx *= 0.8
            self.vy *= 0.8
            if self.t >= self.wind_t:
                a = math.atan2(dy, dx)
                self.vx, self.vy = math.cos(a) * 3.6, math.sin(a) * 3.6
                self.state, self.t = "attack", 0
                self.hit_done = False
                audio.play("dive", 0.5)
        elif self.state == "attack":
            if not self.hit_done and touches(self.strike_area(), self.sc.hero_area()):
                if self.sc.hurt_player(DMG["bat"], self):
                    self.hit_done = True
            if self.t > 34:
                self.state, self.t = "recover", 0
        elif self.state == "recover":
            self.vx *= 0.9
            self.vy = self.vy * 0.85 - 0.12
            if self.t > 40:
                self.state, self.t, self.cd = "hover", 0, self.sc.rng.randrange(60, 110)
        self.physics()

    def hurt(self, dmg, kb, move):
        self.hp -= dmg
        self.flash = 6
        if self.hp <= 0:
            self.state, self.t = "dead", 0
            self.vy = -1
            self.sc.enemy_died(self)
        else:
            self.state, self.t = "hurt", 0
            self.vx, self.vy = kb * 1.2, -1.0
        return dmg

    def draw(self, surf, ox, oy):
        fr = _art()["bat"]
        if self.state == "sleep":
            img = fr[1]
        else:
            img = fr[(self.sc.t // (3 if self.state == "attack" else 5)) % 3]
        if self.face < 0:
            img = pygame.transform.flip(img, True, False)
        if self.state == "dead" and (self.dead_t // 3) % 2:
            return
        if (self.flash and self.flash % 2) or (self.state == "windup" and (self.t // 3) % 2 == 0):
            col = (255, 255, 255) if self.flash else (255, 90, 70)
            img = pygame.mask.from_surface(img).to_surface(setcolor=col + (255,), unsetcolor=(0, 0, 0, 0))
        x, y = round(self.x - img.get_width() / 2 - ox), round(self.y - img.get_height() / 2 - oy)
        if self.state == "windup":
            x += self.sc.rng.choice((-1, 0, 1))
        surf.blit(img, (x, y))
        if self.state == "windup" and self.t < 16:
            self.sc.draw_alert(surf, self.x - ox, self.y - 14 - oy)


class Warden(Enemy):
    """The boss: Lu Bu from the sprite pack at 1.5x Akuma's size, three phases."""
    kind = "boss"
    HP, BW, BH, CELLS = BOSS_HP, 24, 56, 40

    def __init__(self, sc, x, y):
        super().__init__(sc, x, y, "lubu", BOSS_SCALE, "warden")
        self.state = "sleep"
        self.face = -1
        self.poise = 0
        self.act = None
        self.target_x = x
        self.charges = 0

    @property
    def phase(self):
        f = self.hp / self.max_hp
        return 1 if f > 0.6 else 2 if f > 0.3 else 3

    def telegraphing(self):
        return self.state == "windup"

    def wind_len(self, base):
        return round(base * (0.75 if self.phase == 3 else 1.0))

    def update(self):
        self.t += 1
        self.pose_t += 1
        if self.flash:
            self.flash -= 1
        if self.poise > 0:
            self.poise -= 0.25
        sc = self.sc
        lv = sc.lv
        p = sc.p
        dx = p.x - self.x
        st = self.state
        if st == "sleep":
            self.set_pose("idle")
        elif st == "intro":
            self.set_pose("taunt" if self.t > 20 else "intro", 70)
            if self.t >= 90:
                self.state, self.t, self.cd = "idle", 0, 30
        elif st == "dead":
            self.dead_t += 1
            self.set_pose("down" if self.dead_t > 20 else "launch", 20)
        elif st == "stagger":
            self.set_pose("hurt", 50)
            if self.t >= 50:
                self.state, self.t, self.cd = "idle", 0, 10
        elif st == "idle":
            self.face = 1 if dx > 0 else -1
            if self.cd:
                self.cd -= 1
                if abs(dx) > 46:
                    self.set_pose("walk")
                    self.vx = self.face * (0.7 + 0.15 * self.phase)
                else:
                    self.set_pose("idle")
            elif p.state != "dead":
                self.choose(abs(dx))
        elif st == "windup":
            self.vx = 0
            self.set_pose(self.wind_pose, self.wind_t)
            if self.act == "slam":
                self.target_x = p.x
            if self.t >= self.wind_t:
                self.begin()
        elif st == "swing":
            self.set_pose("hammer_down", 12)
            if self.t == 1:
                self.vx = self.face * 2.2
                audio.play("heavy", 0.7)
            self.melee(DMG["swing"])
            if self.t >= 12:
                self.recover(34)
        elif st == "charge":
            self.set_pose("lariat_a" if (self.t // 12) % 2 == 0 else "lariat_b")
            self.vx = self.face * (4.0 + 0.3 * self.phase)
            self.melee(DMG["charge"], both=True)
            if self.t > 80 or self.hit_wall:
                sc.shake = 8
                if self.hit_wall:
                    audio.play("mv_slam", 0.6)
                if self.phase == 3 and self.charges < 1:
                    self.charges += 1
                    self.face = 1 if dx > 0 else -1
                    self.start("charge", "crouch", 22)
                else:
                    self.charges = 0
                    self.recover(50, "hurt")
        elif st == "leap":
            self.set_pose("jump" if self.vy < 0 else "fall")
            if self.on_ground and self.t > 4:
                sc.shake = 12
                audio.play("mv_slam")
                self.melee(DMG["slam"], both=True, force=True)
                for d in (-1, 1):
                    sc.spawn_proj(self.x + d * 16, lv.arena_floor - 7, d * (2.6 + 0.4 * self.phase), 0, "wave",
                                  DMG["wave"], False, self)
                sc.dust(self.x, self.y, 12)
                self.recover(36, "land")
        elif st == "cast":
            self.set_pose("hado_fire", 16)
            if self.t == 2:
                hx, hy = self.x + self.face * 22, self.y - 40
                base = math.atan2(p.y - 14 - hy, p.x - hx)
                for k in ((-1, 0, 1) if self.phase < 3 else (-2, -1, 0, 1, 2)):
                    a = base + k * 0.22
                    sc.spawn_proj(hx, hy, math.cos(a) * 2.3, math.sin(a) * 2.3, "fire", DMG["fire"], False, self)
                audio.play("fireball")
            if self.t >= 16:
                self.recover(28)
        elif st == "recover":
            self.set_pose(self.rec_pose, self.rec_t)
            if self.t >= self.rec_t:
                self.state, self.t, self.cd = "idle", 0, max(8, 40 - 10 * self.phase)
        # physics
        self.vy = min(MAX_FALL + 2, self.vy + GRAV)
        self.hit_wall = move_body(lv, self, self.BW, self.BH)
        lo, hi = lv.arena_x0 + 3 * T + 14, lv.arena_x1 - 5 * T - 14
        if self.x < lo or self.x > hi:
            self.x = max(lo, min(hi, self.x))
            self.hit_wall = 1
        if st not in ("charge", "leap"):
            self.vx *= 0.8

    def choose(self, dist):
        rng = self.sc.rng
        opts = []
        if dist < 64:
            opts += [("swing", 5), ("slam", 2)]
        else:
            opts += [("charge", 3), ("slam", 3)]
        if self.phase >= 2:
            opts += [("cast", 2 if dist > 64 else 1)]
        if dist < 64 and self.phase >= 2:
            opts += [("charge", 1)]
        tot = sum(w for _, w in opts)
        pick = rng.uniform(0, tot)
        for act, w in opts:
            pick -= w
            if pick <= 0:
                break
        pose, n = {"swing": ("hammer_up", 34), "charge": ("crouch", 38), "slam": ("crouch", 30),
                   "cast": ("hado_prep", 36)}[act]
        self.start(act, pose, n)

    def start(self, act, pose, n):
        self.act = act
        self.state, self.t = "windup", 0
        self.wind_pose, self.wind_t = pose, self.wind_len(n)
        self.sc.event("windup", self)
        audio.play("mv_tell", 0.7)

    def begin(self):
        self.t = 0
        self.hit_done = False
        if self.act == "swing":
            self.state = "swing"
        elif self.act == "charge":
            self.state = "charge"
            audio.play("mv_roar", 0.4)
        elif self.act == "slam":
            self.state = "leap"
            self.vy = -7.6
            air = 2 * 7.6 / GRAV
            self.vx = max(-4.0, min(4.0, (self.target_x - self.x) / air))
            self.leap_x = self.target_x
            audio.play("jump")
        elif self.act == "cast":
            self.state = "cast"

    def recover(self, n, pose="idle"):
        self.state, self.t = "recover", 0
        self.rec_t, self.rec_pose = n, pose

    def melee(self, dmg, both=False, force=False):
        if self.hit_done:
            return
        area = self.body_area() if force else self.strike_area(both)
        if touches(area, self.sc.hero_area()):
            if self.sc.hurt_player(dmg, self):
                self.hit_done = True

    def strike_area(self, both=False):
        key = self.key()
        flip = self.face < 0
        m = self.art.strike(key, flip, both)
        if m is None:
            return self.body_area()
        img, (ax, ay) = self.art.entry(key, flip)
        return m, round(self.x - ax), round(self.y - ay)

    def hurt(self, dmg, kb, move):
        if self.state in ("sleep", "intro", "dead"):
            return 0
        if self.state == "stagger":
            dmg = round(dmg * 1.25)
        self.hp -= dmg
        self.flash = 5
        self.poise += dmg
        if self.hp <= 0:
            self.hp = 0
            self.state, self.t = "dead", 0
            self.vx = 0
            self.sc.boss_died(self)
        elif self.poise >= 110 and self.state in ("idle", "recover", "windup"):
            self.poise = 0
            self.state, self.t = "stagger", 0
            self.vx = kb
            self.sc.popup("STAGGER!", self.x, self.y - 70, (255, 230, 90))
        return dmg

    def draw(self, surf, ox, oy):
        sc = self.sc
        if self.state == "leap":
            fx = round(self.leap_x - ox)
            fy = round(sc.lv.arena_floor - oy)
            if (sc.t // 4) % 2:
                pygame.draw.ellipse(surf, (200, 40, 30), (fx - 16, fy - 3, 32, 6), 1)
            pygame.draw.ellipse(surf, (120, 20, 20), (fx - 10, fy - 2, 20, 4))
        key = self.key()
        flip = self.face < 0
        img, (ax, ay) = self.art.entry(key, flip)
        if self.state == "dead" and self.dead_t > 60 and (self.dead_t // 3) % 2:
            return
        if self.state in ("windup", "charge") or (self.phase == 3 and self.alive):
            g = _art()["glow_red"]
            surf.blit(g, (round(self.x - 30 - ox), round(self.y - 60 - oy)), special_flags=pygame.BLEND_RGB_ADD)
        if self.flash and self.flash % 2:
            img = self.art.flash(key, flip)
        elif self.state == "windup" and self.tell_flash():
            img = self.art.flash(key, flip, (255, 200, 120))
        surf.blit(img, (round(self.x - ax - ox), round(self.y - ay - oy)))
        if self.state == "windup" and self.t < 20:
            sc.draw_alert(surf, self.x - ox, self.y - img.get_height() - 8 - oy)


ENEMY_TYPES = {"grunt": Grunt, "shield": Shield, "caster": Caster, "bat": Bat}
GRUNT_CIDS = ("ryu", "ken", "sakura", "chunli")


class Proj:
    def __init__(self, x, y, vx, vy, kind, dmg, friendly, owner):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.kind, self.dmg, self.friendly, self.owner = kind, dmg, friendly, owner
        self.t = 0
        self.dead = False
        self.life = {"wave": 90, "hado": 90}.get(kind, 220)

    def image(self, clock):
        a = _art()
        if self.kind == "hado":
            fr = a["hado"]
            img = fr[min(len(fr) - 1, 2 + (self.t // 3) % (len(fr) - 2))]
            return pygame.transform.flip(img, True, False) if self.vx < 0 else img
        if self.kind == "fire":
            fr = a["fire"]
            img = fr[(self.t // 3) % len(fr)]
            return pygame.transform.flip(img, True, False) if self.vx < 0 else img
        return None

    def area(self, clock):
        img = self.image(clock)
        if img is not None:
            return image_area(img, self.x - img.get_width() / 2, self.y - img.get_height() / 2)
        if self.kind == "wave":
            return rect_area((self.x - 6, self.y - 7, 12, 14))
        return rect_area((self.x - 3, self.y - 3, 7, 7))


class Pickup:
    def __init__(self, kind, x, y, vx=0.0, vy=0.0):
        self.kind, self.x, self.y, self.vx, self.vy = kind, float(x), float(y), vx, vy
        self.on_ground = False
        self.t = 0
        self.taken = False


# ---------------------------------------------------------------------------
# the scene
# ---------------------------------------------------------------------------
class MetroidScene:
    LEVEL_NAME = "THE PRISONERS' QUARTERS"

    def __init__(self, game, seed=None, level=12, hp=None):
        self.game = game
        self.level = level
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed * 7 + 1)
        _build_sounds()
        self.lv = Level(self.seed)
        art_rng = random.Random(self.seed + 99)
        self.art = _art()
        self.surf = _level_surface(self.lv, art_rng)
        self.far = _far_layer(art_rng)
        self.mid = _mid_layer(art_rng)
        self.akuma = SmallArt("akuma", SCALE)
        self.menu = PauseMenu(game, CONTROLS)
        self.max_hp = game.akuma_max
        self.hp = self.max_hp if hp is None else min(hp, self.max_hp)
        self.hp_lag = self.hp
        self.lives = LIVES
        self.flasks = self.max_flasks = FLASKS
        self.cells = 0
        self.ki = KI_MAX
        self.dmg_mult = 1.0
        self.buys = {"str": 0, "vit": 0}
        self.scrolls = 0
        self._uid = 0
        self.t = 0
        self.frame = 0
        self.phase = "intro"
        self.end_t = 0
        self.result = None
        self.hitstop = 0
        self.shake = 0
        self.events = []
        self.particles = []
        self.popups = []
        self.projs = []
        self.pickups = []
        self.banner = None          # (text, sub, frames)
        self.dead_t = 0
        self.god = False            # tests
        self.p = Hero(*self.lv.start)
        self.respawn = 0
        self.shrines = [dict(s, lit=False, inside=False) for s in self.lv.shrines]
        self.altars = [dict(a, inside=False) for a in self.lv.altars]
        self.rewards = []
        for rw in self.lv.rewards:
            self.rewards.append(dict(rw, open=False))
        self.enemies = []
        for kind, (x, y) in self.lv.spawns:
            self.enemies.append(self.make_enemy(kind, x, y))
        self.boss = Warden(self, *self.lv.boss_pos)
        self.boss_on = False
        self.boss_dealt = 0         # damage Akuma's hits did to the Warden (tests)
        self.exit_open = False
        self.visited = set()
        self.cam_look = CAM_LOOK
        self.camx, self.camy = self._cam_target()
        self._touch_shrines()

    def make_enemy(self, kind, x, y):
        if kind == "grunt":
            return Grunt(self, x, y, self.rng.choice(GRUNT_CIDS))
        return ENEMY_TYPES[kind](self, x, y)

    def next_uid(self):
        self._uid += 1
        return self._uid

    @property
    def paused(self):
        return self.menu.open

    def event(self, kind, who, *extra):
        self.events.append((self.frame, kind, getattr(who, "uid", who), getattr(who, "kind", None)) + extra)
        if len(self.events) > 400:
            del self.events[:100]

    # ---- helpers ----------------------------------------------------------
    def popup(self, text, x, y, col=(255, 255, 255), n=50):
        self.popups.append([text, x, y, n, col])

    def dust(self, x, y, n=5):
        for _ in range(n):
            self.particles.append([x + self.rng.uniform(-6, 6), y - 1, self.rng.uniform(-0.8, 0.8),
                                   self.rng.uniform(-0.8, -0.1), 18, (120, 110, 130), 2, 0.02])

    def sparks(self, x, y, col=(255, 220, 120), n=8):
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            s = self.rng.uniform(1, 3)
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s, 12, col, 1, 0.1])

    def draw_alert(self, surf, x, y):
        x, y = round(x), round(y)
        surf.fill(OUTLINE, (x - 2, y - 9, 5, 12))
        surf.fill((255, 60, 40), (x - 1, y - 8, 3, 6))
        surf.fill((255, 60, 40), (x - 1, y, 3, 2))

    def hero_area(self):
        p = self.p
        key, deg = self._hero_pose()
        flip = p.face < 0
        if deg:
            img = self.akuma.rotated(key, flip, deg)
            return image_area(img, p.x - img.get_width() / 2, p.y - 9 - img.get_height() / 2)
        img, (ax, ay) = self.akuma.entry(key, flip)
        return self.akuma.mask(key, flip), round(p.x - ax), round(p.y - ay)

    def spawn_proj(self, x, y, vx, vy, kind, dmg, friendly, owner):
        self.projs.append(Proj(x, y, vx, vy, kind, dmg, friendly, owner))

    # ---- update -----------------------------------------------------------
    def update(self, inp):
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.phase == "play" and self.menu.toggle(inp):
            return
        self.t += 1
        self.frame += 1
        self.hp_lag = max(self.hp, self.hp_lag - 0.7) if self.hp_lag > self.hp else self.hp
        if self.shake:
            self.shake -= 1
        for pu in self.popups:
            pu[3] -= 1
            pu[2] -= 0.3
        self.popups = [pu for pu in self.popups if pu[3] > 0]
        for pt in self.particles:
            pt[0] += pt[2]
            pt[1] += pt[3]
            pt[3] += pt[7]
            pt[4] -= 1
        self.particles = [pt for pt in self.particles if pt[4] > 0]
        if self.banner:
            self.banner[2] -= 1
            if self.banner[2] <= 0:
                self.banner = None
        if self.phase == "intro":
            self.end_t += 1
            self._camera(snap=True)
            if self.end_t >= INTRO or (self.end_t > 40 and inp.any_pressed("punch", "kick", "special", "start")):
                self.phase, self.end_t = "play", 0
            return
        if self.phase in ("won", "lost"):
            self.end_t += 1
            skip = self.end_t > 50 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= 170 or skip:
                if self.phase == "won":
                    self.result = "win"
                    self.game.level_done(self, max(1, min(self.hp, self.game.akuma_max)))
                else:
                    self.result = "lose"
                    self.game.level_failed(self)
            return
        if self.hitstop:
            self.hitstop -= 1
            return
        self._update_hero(inp)
        self._update_enemies()
        self._update_projs()
        self._update_pickups()
        self._update_objects(inp)
        self._camera()

    # ---- Akuma --------------------------------------------------------------
    def _update_hero(self, inp):
        p = self.p
        lv = self.lv
        if p.inv:
            p.inv -= 1
        if p.roll_cd:
            p.roll_cd -= 1
        if p.combo_t:
            p.combo_t -= 1
        if p.down_tap:
            p.down_tap -= 1
        if p.drop:
            p.drop -= 1
        self.ki = min(KI_MAX, self.ki + KI_REGEN)
        p.t += 1
        if p.state == "dead":
            self._dead_update()
            return
        frozen = self.boss.state == "intro"
        left = inp.held("left") and not frozen
        right = inp.held("right") and not frozen
        up = inp.held("up") and not frozen
        down = inp.held("down") and not frozen
        dirx = (1 if right else 0) - (1 if left else 0)
        pressed = (lambda a: inp.pressed(a) and not frozen)
        if pressed("up"):
            p.jbuf = JUMP_BUFFER
        elif p.jbuf:
            p.jbuf -= 1
        for a in ("punch", "kick", "special"):
            if pressed(a):
                p.abuf = [a, 8, down]
        if p.abuf:
            p.abuf[1] -= 1
            if p.abuf[1] <= 0:
                p.abuf = None
        cc = int(p.x // T)
        # ---- ladder
        if p.state == "move":
            mid = int((p.y - 10) // T)
            near = abs(p.x - (cc * T + T / 2)) < 7
            if up and near and (lv.ladder(cc, mid) or lv.ladder(cc, int((p.y - 1) // T))):
                p.state, p.vx, p.vy, p.jbuf = "ladder", 0.0, 0.0, 0
            elif down and p.on_ground and near and lv.ladder(cc, int(p.y // T)) and \
                    not lv.ladder(cc, int((p.y - 1) // T)):
                p.state, p.vx, p.vy = "ladder", 0.0, 0.0
                p.y += 3
        if p.state == "ladder":
            self._ladder(p, up, down, dirx)
            return
        if p.on_ground:
            p.coyote = COYOTE
        elif p.coyote:
            p.coyote -= 1
        if p.on_ground and pressed("down"):
            if p.down_tap:
                self._try_drop(p)
            p.down_tap = 14
        # ---- start actions
        can_act = p.state == "move" or (p.state == "attack" and MOVES[p.move]["ph"][p.ph][0] == "r")
        if pressed("shield") and p.roll_cd == 0 and (p.on_ground or p.coyote) and can_act:
            p.state, p.t = "roll", 0
            p.roll_dir = dirx or p.face
            p.face = p.roll_dir
            p.vx = p.roll_dir * ROLL_V
            p.abuf = None
            audio.play("mv_roll", 0.7)
            self.dust(p.x, p.y, 3)
        elif p.abuf and can_act:
            self._start_attack(p, *p.abuf)
        # jump (also cancels ground recovery)
        if p.jbuf and p.coyote and (p.state == "move" or (p.state == "attack" and not MOVES[p.move].get("air")
                                                          and MOVES[p.move]["ph"][p.ph][0] == "r")):
            if down and p.on_ground and self._on_plank(p):
                self._try_drop(p)
            else:
                p.state = "move"
                p.vy = JUMP_V
                p.coyote = 0
                p.jbuf = 0
                p.on_ground = False
                audio.play("jump", 0.5)
        st = p.state
        # ---- per state
        if st == "move":
            target = dirx * RUN
            if down and p.on_ground and not dirx:
                target = 0
            acc = ACC_GROUND if p.on_ground else ACC_AIR
            p.vx += max(-acc, min(acc, target - p.vx))
            if dirx:
                p.face = dirx
        elif st == "roll":
            if p.t > ROLL_T - 6:
                p.vx *= 0.8
            if p.t >= ROLL_T:
                p.state, p.t = "move", 0
                p.roll_cd = ROLL_CD
        elif st == "hurt":
            p.vx *= 0.9
            if p.t >= HURT_T:
                p.state, p.t = "move", 0
        elif st == "drink":
            p.vx *= 0.7
            if p.t == DRINK_AT:
                heal = round(self.max_hp * FLASK_HEAL)
                self.hp = min(self.max_hp, self.hp + heal)
                self.popup("+%d" % heal, p.x, p.y - 34, (120, 255, 140))
                audio.play("mv_flask")
                for _ in range(10):
                    self.particles.append([p.x + self.rng.uniform(-8, 8), p.y - self.rng.uniform(0, 26), 0,
                                           -self.rng.uniform(0.3, 0.9), 26, (110, 255, 140), 1, 0])
            if p.t >= DRINK_T:
                p.state, p.t = "move", 0
        elif st == "attack":
            self._attack_update(p, dirx)
        # ---- physics
        if p.state == "attack" and MOVES[p.move].get("dive") and p.ph == 1:
            pass                                    # fixed dive velocity
        elif p.state == "attack" and p.move == "ahado" and p.ph < 2:
            p.vy = min(p.vy + GRAV * 0.3, 1.0)
        else:
            g = GRAV * (0.6 if (abs(p.vy) < 1.2 and up and p.state == "move") else 1)
            p.vy = min(MAX_FALL, p.vy + g)
            if p.state == "move" and p.vy < JUMP_CUT and not up:
                p.vy = JUMP_CUT
        was = p.on_ground
        oldx = p.x
        move_body(lv, p, PW, p.h, drop=p.drop > 0)
        p.walked += abs(p.x - oldx)
        if p.on_ground:
            if not was and p.air_t > 6:
                audio.play("land", 0.5)
                self.dust(p.x, p.y, 4)
            p.air_t = 0
            self._remember_safe(p)
        else:
            p.air_t += 1
        # landing ends air moves
        if p.state == "attack" and MOVES[p.move].get("air") and p.on_ground:
            if MOVES[p.move].get("dive"):
                if p.ph == 1:
                    p.ph, p.ph_t = 2, 0
                    p.vx = 0
                    self.shake = 4
                    self.dust(p.x, p.y, 8)
                    audio.play("land")
            else:
                p.state, p.t = "move", 0
        # spikes
        if lv.spike(int(p.x // T), int((p.y - 1) // T)) or lv.spike(int(p.x // T), int((p.y - 8) // T)):
            self._spiked()

    def _on_plank(self, p):
        lv = self.lv
        r = int(p.y // T)
        cs = range(int((p.x - PW / 2) // T), int((p.x + PW / 2 - 0.01) // T) + 1)
        return all(not lv.solid(c, r) and not lv.ladder(c, r) for c in cs) and \
            any(lv.platform(c, r) for c in cs)

    def _try_drop(self, p):
        if self._on_plank(p):
            p.y += 2
            p.drop = 8
            p.on_ground = False
            p.coyote = 0
            p.jbuf = 0

    def _remember_safe(self, p):
        lv = self.lv
        r = int(p.y // T)
        ok = all(lv.solid(c, r) for c in (int((p.x - 8) // T), int((p.x + 8) // T)))
        if ok and not any(lv.spike(c, r - 1) for c in range(int(p.x // T) - 1, int(p.x // T) + 2)):
            p.safe = (p.x, p.y)

    def _ladder(self, p, up, down, dirx):
        lv = self.lv
        cc = int(p.x // T)
        p.x += (cc * T + T / 2 - p.x) * 0.5
        p.vx = 0.0
        p.vy = 0.0
        dy = -CLIMB if up else CLIMB if down else 0.0
        p.climbed += abs(dy)
        p.y += dy
        p.on_ground = False
        if dy < 0:
            r = int((p.y - 0.01) // T)
            if not lv.ladder(cc, r):
                p.y = float((r + 1) * T)
                p.state, p.on_ground = "move", True
            elif lv.solid(cc, int((p.y - PH) // T)):
                p.y -= dy
        elif dy > 0:
            r = int(p.y // T)
            if lv.solid(cc, r):
                p.y = float(r * T)
                p.state, p.on_ground = "move", True
            elif not lv.ladder(cc, r) and not lv.ladder(cc, int((p.y - 1) // T)):
                p.state = "move"
        if dirx and p.state == "ladder":
            p.state = "move"
            p.face = dirx
            p.vx = dirx * 1.2

    def _start_attack(self, p, btn, n, down):
        air = not p.on_ground
        name = None
        if btn == "punch":
            if air:
                name = "ajab"
            else:
                name = COMBO.get(p.last) if (p.combo_t and p.last in COMBO) else "jab1"
        elif btn == "kick":
            name = ("dive" if down else "akick") if air else ("sweep" if down else "kick")
        else:
            if down and not air:
                if self.flasks > 0 and self.hp < self.max_hp:
                    self.flasks -= 1
                    p.state, p.t = "drink", 0
                    p.abuf = None
                    self.event("drink", p)
                    return
                p.abuf = None
                return
            if self.ki < HADO_COST:
                self.popup("NO KI", p.x, p.y - 34, (180, 160, 220), 30)
                p.abuf = None
                return
            self.ki -= HADO_COST
            name = "ahado" if air else "hado"
        p.abuf = None
        p.state, p.t = "attack", 0
        p.move, p.ph, p.ph_t = name, 0, 0
        p.hit_set = set()
        p.last = name
        p.combo_t = 0
        if name in ("jab1", "jab2", "jab3", "kick", "sweep", "hado"):
            p.vx *= 0.4
        if p.move == "dive":
            p.vx, p.vy = 0.0, -1.0

    def _attack_update(self, p, dirx):
        mv = MOVES[p.move]
        kind, n, pose = mv["ph"][p.ph]
        p.ph_t += 1
        if not mv.get("air") and p.on_ground:
            p.vx *= 0.75
        if p.ph_t >= n:
            p.ph += 1
            p.ph_t = 0
            if p.ph >= len(mv["ph"]):
                p.state, p.t = "move", 0
                return
            kind = mv["ph"][p.ph][0]
            if kind == "a":
                self._active_start(p, mv)
            elif kind == "r" and p.move in COMBO:
                p.combo_t = mv["ph"][p.ph][1] + 12
        if mv["ph"][p.ph][0] == "a":
            self._hero_strikes(p, mv)

    def _active_start(self, p, mv):
        if mv.get("lunge") and p.on_ground:
            p.vx = p.face * mv["lunge"]
        if mv.get("hop") and p.on_ground:
            p.vy = mv["hop"]
            p.on_ground = False
        if mv.get("dive"):
            p.vy, p.vx = 6.0, p.face * 2.8
            audio.play("dive")
        elif mv.get("proj"):
            k = self.dmg_mult
            self.spawn_proj(p.x + p.face * 16, p.y - 17, p.face * 3.6, 0, "hado", round(mv["dmg"] * k), True, p)
            audio.play("hadouken")
        else:
            audio.play("whiff", 0.5)

    def _strike_area(self, p):
        key, deg = self._hero_pose()
        flip = p.face < 0
        m = self.akuma.strike(key, flip)
        if m is None:
            return rect_area((p.x + (2 if p.face > 0 else -24), p.y - 24, 22, 16))
        img, (ax, ay) = self.akuma.entry(key, flip)
        return m, round(p.x - ax), round(p.y - ay)

    def _targets(self):
        out = [e for e in self.enemies if e.alive and abs(e.x - self.p.x) < 200]
        if self.boss_on and self.boss.alive:
            out.append(self.boss)
        return out

    def _hero_strikes(self, p, mv):
        if mv.get("proj"):
            return
        area = self._strike_area(p)
        for e in self._targets():
            if e in p.hit_set:
                continue
            if touches(area, e.body_area()):
                p.hit_set.add(e)
                self._hit_enemy(e, p.move, p.x, area)

    def _hit_enemy(self, e, move, src_x, area=None):
        mv = MOVES[move]
        d = 1 if e.x > src_x else -1
        hx, hy = (e.x + self.p.x) / 2, e.y - 18
        if isinstance(e, Shield) and e.guarding() and (src_x - e.x) * e.face > 0 \
                and not mv.get("guard_break"):
            audio.play("block")
            self.sparks(e.x + e.face * 8, e.y - 18, (140, 190, 255), 6)
            self.popup("BLOCKED", e.x, e.y - 40, (150, 190, 255), 30)
            if move != "hado" and move != "ahado":
                self.p.vx = -d * 2.0
            self.hitstop = 3
            self.event("blocked", e, move)
            return 0
        if isinstance(e, Shield) and e.guarding() and mv.get("guard_break") and (src_x - e.x) * e.face > 0:
            e.broken = 70
            self.popup("GUARD BREAK", e.x, e.y - 44, (255, 220, 90), 40)
        dmg = round(mv["dmg"] * self.dmg_mult)
        if isinstance(e, Warden):
            kb = 0.0
        else:
            kb = d * mv["kb"]
        dealt = e.hurt(dmg, kb, move)
        if dealt:
            self.event("dealt", e, move, dealt)
            if isinstance(e, Warden):
                self.boss_dealt += dealt
            self.popup(str(dealt), e.x + self.rng.uniform(-4, 4), e.y - (70 if isinstance(e, Warden) else 36),
                       (255, 240, 120) if mv.get("heavy") else (255, 255, 255), 36)
            self.sparks(hx, hy)
            self.hitstop = 6 if mv.get("heavy") else 3
            if mv.get("heavy"):
                self.shake = 4
            audio.play("heavy" if mv.get("heavy") else "hit", 0.8)
            self.ki = min(KI_MAX, self.ki + KI_ON_HIT)
            if mv.get("dive") and self.p.state == "attack" and self.p.move == "dive":
                self.p.state, self.p.t = "move", 0
                self.p.vy = -5.0
                self.p.vx = -self.p.face * 0.6
        return dealt

    def hurt_player(self, dmg, src):
        """An enemy attack connects. False when Akuma rolled through it or is
        still flashing from the last hit."""
        p = self.p
        if p.state == "dead":
            return False
        if p.rolling_safe():
            if not getattr(p, "dodged", None) == (getattr(src, "uid", 0), p.t // 50):
                self.event("dodge", src)
            return False
        if p.inv or self.god:
            return False
        self.hp -= dmg
        self.event("hurt", src, dmg)
        p.inv = INVULN
        d = 1 if p.x > getattr(src, "x", p.x - p.face) else -1
        if p.state == "drink" and p.t < DRINK_AT:
            self.popup("SPILLED!", p.x, p.y - 40, (255, 140, 140), 30)
        p.state, p.t = "hurt", 0
        p.vx, p.vy = d * 2.4, -2.6
        p.on_ground = False
        self.shake = 6
        self.hitstop = 5
        self.popup("-%d" % dmg, p.x, p.y - 34, (255, 90, 70), 40)
        self.sparks(p.x, p.y - 16, (255, 120, 90), 8)
        audio.play("heavy")
        if self.hp <= 0:
            self._die()
        return True

    def _spiked(self):
        p = self.p
        if p.state == "dead":
            return
        self.hp -= SPIKE_DMG
        self.event("spikes", p, SPIKE_DMG)
        self.popup("-%d" % SPIKE_DMG, p.x, p.y - 34, (255, 90, 70), 40)
        self.shake = 6
        audio.play("hit")
        if self.hp <= 0:
            self._die()
            return
        p.x, p.y = p.safe
        p.vx = p.vy = 0.0
        p.state, p.t = "hurt", 0
        p.inv = INVULN

    def _die(self):
        p = self.p
        self.hp = 0
        p.state, p.t = "dead", 0
        p.vy = -3.0
        p.vx = -p.face * 1.0
        self.dead_t = 0
        audio.play("ko")
        self.event("death", p)

    def _dead_update(self):
        p = self.p
        self.dead_t += 1
        p.vy = min(MAX_FALL, p.vy + GRAV)
        move_body(self.lv, p, PW, PH)
        p.vx *= 0.9
        if self.dead_t == 30:
            self.banner = ["AKUMA HAS FALLEN", "%d %s LEFT" % (max(0, self.lives - 1),
                                                                  "LIFE" if self.lives - 1 == 1 else "LIVES"), 90]
            if self.lives - 1 <= 0:
                self.banner[1] = "NO LIVES LEFT"
        if self.dead_t >= 120:
            self.lives -= 1
            if self.lives <= 0:
                self.phase, self.end_t = "lost", 0
                return
            self._respawn()

    def _respawn(self):
        s = self.shrines[self.respawn]
        p = Hero(*s["pos"])
        p.face = 1
        p.inv = 60
        self.p = p
        self.hp = self.hp_lag = self.max_hp
        self.flasks = self.max_flasks
        self.ki = KI_MAX
        self.projs = []
        for s2 in self.shrines:
            s2["inside"] = s2 is s
        if self.boss_on and self.boss.alive:
            self.boss = Warden(self, *self.lv.boss_pos)
            self.boss_on = False
            self.lv.gate_in = False
        self.event("respawn", p, self.respawn)
        self._camera(snap=True)

    # ---- enemies ------------------------------------------------------------
    def _update_enemies(self):
        p = self.p
        for e in self.enemies:
            if abs(e.x - p.x) > 420 or abs(e.y - p.y) > 260:
                continue
            e.update()
        self.enemies = [e for e in self.enemies if not e.gone]
        if self.boss_on or self.boss.state == "dead":
            self.boss.update()

    def enemy_died(self, e):
        self.event("kill", e)
        self.game.kills = getattr(self.game, "kills", 0) + 1
        self.drop_cells(e.x, e.y - 10, e.CELLS)
        audio.play("ko", 0.4)

    def boss_died(self, b):
        self.event("boss_dead", b)
        self.drop_cells(b.x, b.y - 30, b.CELLS)
        self.banner = ["THE WARDEN HAS FALLEN", "THE WAY OUT IS OPEN", 150]
        self.lv.gate_out = False
        self.lv.gate_in = False
        self.exit_open = True
        self.shake = 20
        audio.play("ko")
        audio.play("mv_gate")
        self.game.kills = getattr(self.game, "kills", 0) + 1

    def drop_cells(self, x, y, n):
        for _ in range(n):
            self.pickups.append(Pickup("cell", x, y, self.rng.uniform(-1.6, 1.6), self.rng.uniform(-3.5, -1.5)))

    # ---- projectiles --------------------------------------------------------
    def _update_projs(self):
        lv = self.lv
        for pr in self.projs:
            pr.t += 1
            pr.x += pr.vx
            pr.y += pr.vy
            if pr.kind == "wave":
                if lv.solid_px(pr.x + (8 if pr.vx > 0 else -8), pr.y) or pr.t > pr.life:
                    pr.dead = True
                if pr.t % 3 == 0:
                    self.particles.append([pr.x, pr.y + 6, -pr.vx * 0.1, -0.6, 14, (255, 150, 80), 2, 0.05])
            elif lv.solid_px(pr.x, pr.y) or pr.t > pr.life:
                pr.dead = True
                self.sparks(pr.x, pr.y, (200, 140, 255) if pr.kind == "bolt" else (255, 180, 80), 5)
            if pr.dead:
                continue
            area = pr.area(self.t)
            if pr.friendly:
                for e in self._targets():
                    if touches(area, e.body_area()):
                        self._hit_enemy(e, "hado" if self.p.on_ground else "ahado", pr.x - pr.vx * 10)
                        pr.dead = True
                        break
            elif touches(area, self.hero_area()):
                if self.hurt_player(pr.dmg, pr.owner) and pr.kind != "wave":
                    pr.dead = True
        self.projs = [pr for pr in self.projs if not pr.dead]

    # ---- pickups & objects ----------------------------------------------------
    def _update_pickups(self):
        p = self.p
        got = 0
        for c in self.pickups:
            c.t += 1
            dx, dy = p.x - c.x, (p.y - 14) - c.y
            dist = math.hypot(dx, dy)
            if c.t > 25 and dist < 70 and p.state != "dead":
                c.vx += dx / (dist or 1) * 0.5
                c.vy += dy / (dist or 1) * 0.5
                c.vx *= 0.9
                c.vy *= 0.9
                c.x += c.vx
                c.y += c.vy
            else:
                c.vy = min(4, c.vy + 0.2)
                move_body(self.lv, c, 4, 4)
                if c.on_ground:
                    c.vx *= 0.8
            if dist < 9 and c.t > 15:
                c.taken = True
                got += 1
        if got:
            self.cells += got
            audio.play("mv_cell", 0.6)
        self.pickups = [c for c in self.pickups if not c.taken]

    def _touch_shrines(self):
        p = self.p
        for s in self.shrines:
            x, y = s["pos"]
            inside = abs(p.x - x) < 14 and abs(p.y - y) < 24 and p.state != "dead"
            if inside and not s["inside"]:
                first = not s["lit"]
                s["lit"] = True
                self.respawn = s["i"]
                if self.flasks < self.max_flasks or first:
                    self.flasks = self.max_flasks
                    if self.t > 1:
                        self.popup("FLASKS REFILLED", x, y - 40, (120, 230, 255), 60)
                if first and self.t > 1:
                    self.banner = ["SHRINE LIT", "CHECKPOINT", 70]
                if self.t > 1:
                    audio.play("mv_shrine")
                    self.event("shrine", p, s["i"])
            s["inside"] = inside

    def _update_objects(self, inp):
        p = self.p
        lv = self.lv
        self._touch_shrines()
        room = lv.room_of(p.x, p.y - 8)
        self.visited.add(room)
        for a in self.altars:
            x, y = a["pos"]
            a["inside"] = abs(p.x - x) < 12 and abs(p.y - y) < 20 and p.state == "move" and p.on_ground
            if a["inside"] and inp.pressed("down"):
                self.buy(a["kind"])
        for rw in self.rewards:
            if rw["open"]:
                continue
            x, y = rw["pos"]
            if abs(p.x - x) < 12 and abs(p.y - y) < 24 and p.state != "dead":
                rw["open"] = True
                if rw["kind"] == "chest":
                    self.drop_cells(x, y - 12, 15)
                    self.popup("TREASURE!", x, y - 30, (255, 220, 90), 60)
                    audio.play("pickup")
                else:
                    self.take_scroll(rw["kind"], x, y)
        # the arena
        if not self.boss_on and self.boss.alive and p.x > lv.trigger_x and \
                lv.room_of(p.x, p.y - 8)[0] >= GW and p.state != "dead":
            self.boss_on = True
            self.boss.state, self.boss.t = "intro", 0
            lv.gate_in = True
            self.shake = 10
            self.banner = ["THE WARDEN", "KEEPER OF THE QUARTERS", 110]
            audio.play("mv_gate")
            audio.play("mv_roar")
            self.event("boss_start", self.boss)
        if self.exit_open:
            ex, ey = lv.exit_pos
            if abs(p.x - ex) < 12 and abs(p.y - ey) < 24 and p.state != "dead":
                self.phase, self.end_t = "won", 0
                audio.play("encounter")

    def buy(self, kind):
        cost = SHOP_COST[min(self.buys[kind], len(SHOP_COST) - 1)]
        a = next(a for a in self.altars if a["kind"] == kind)
        x, y = a["pos"]
        if self.cells < cost:
            self.popup("NEED %d CELLS" % cost, x, y - 34, (255, 140, 140), 40)
            audio.play("block", 0.5)
            return False
        self.cells -= cost
        self.buys[kind] += 1
        self._boost(kind, x, y)
        audio.play("mv_buy")
        self.event("buy", self.p, kind)
        return True

    def take_scroll(self, kind, x, y):
        self.scrolls += 1
        self._boost(kind, x, y)
        self.banner = ["SCROLL OF POWER", "+20% DAMAGE" if kind == "str" else "+%d MAX HEALTH" % VIT_UP, 90]
        audio.play("pickup")
        self.event("scroll", self.p, kind)

    def _boost(self, kind, x, y):
        if kind == "str":
            self.dmg_mult = round(self.dmg_mult + STR_UP, 2)
            self.popup("STRENGTH +20%", x, y - 34, (255, 120, 100), 60)
        else:
            self.max_hp += VIT_UP
            self.hp = min(self.max_hp, self.hp + VIT_UP)
            self.popup("MAX HEALTH +%d" % VIT_UP, x, y - 34, (120, 255, 140), 60)

    # ---- camera -------------------------------------------------------------
    def _cam_target(self):
        p = self.p
        look = getattr(self, "cam_look", CAM_LOOK * p.face)
        x = p.x + look - W / 2
        y = p.y - 20 - H * 0.55
        if self.boss_on and self.boss.alive:
            x = (p.x + self.boss.x) / 2 - W / 2
        return max(0, min(LW - W, x)), max(0, min(LH - H, y))

    def _camera(self, snap=False):
        p = self.p
        self.cam_look += (CAM_LOOK * p.face - self.cam_look) * 0.04
        tx, ty = self._cam_target()
        if snap:
            self.camx, self.camy = tx, ty
        else:
            self.camx += (tx - self.camx) * 0.12
            self.camy += (ty - self.camy) * 0.1

    # ---- drawing ------------------------------------------------------------
    def _hero_pose(self):
        """(sprite key, rotation) for Akuma right now."""
        p = self.p
        a = self.akuma
        st = p.state
        if st == "attack":
            kind, n, pose = MOVES[p.move]["ph"][p.ph]
            return a.resolve(pose, p.ph_t, self.t, n), 0
        if st == "roll":
            key = a.resolve("crouch", 2)
            return key, (-90 * ((p.t // 4) % 4)) * p.face % 360
        if st == "hurt":
            return a.resolve("hurt", p.t, self.t, HURT_T), 0
        if st == "dead":
            return a.resolve("launch" if self.dead_t < 20 else "down", self.dead_t, self.t, 40), 0
        if st == "drink":
            return a.resolve("taunt", p.t, self.t, DRINK_T), 0
        if st == "ladder":
            return a.resolve("jump_up", 0), 0
        if not p.on_ground:
            pose = "jump_up" if p.vy < -2.5 else "jump" if p.vy < 1.5 else "fall"
            return a.resolve(pose, p.air_t, self.t, 30), 0
        if abs(p.vx) > 0.4:
            return a.resolve("dash", 0, int(p.walked * 0.55)), 0
        if self.phase == "play" and p.on_ground and getattr(self.game.input, "held", None) and \
                self.game.input.held("down"):
            return a.resolve("crouch", 30, self.t), 0
        return a.resolve("idle", 0, self.t), 0

    def draw(self, surf):
        sh = (0, 0)
        if self.shake:
            sh = (self.rng.choice((-2, -1, 1, 2)), self.rng.choice((-1, 0, 1)))
        ox, oy = round(self.camx) - sh[0], round(self.camy) - sh[1]
        # parallax
        fx = -int(ox * 0.08) % W
        surf.blit(self.far, (fx - W, 0))
        surf.blit(self.far, (fx, 0))
        mw = self.mid.get_width()
        mx = -int(ox * 0.3) % mw
        my = -int(oy * 0.15) % 30 - 30
        for k in (-1, 0, 1):
            surf.blit(self.mid, (mx + k * mw, my))
        surf.blit(self.surf, (0, 0), pygame.Rect(ox, oy, W, H))
        lv = self.lv
        # gates
        gate = self.art["gate"]
        for flag, ch in ((lv.gate_in, "G"), (lv.gate_out, "X")):
            if not flag:
                continue
            c0 = (lv.arena_cell[0]) * RW
            r0 = lv.arena_cell[1] * RH
            for r in range(r0, r0 + RH):
                for c in range(c0, c0 + AW * RW):
                    if lv.grid[r][c] == ch:
                        surf.blit(gate, (c * T - ox, r * T - oy))
        # torches
        glows = self.art["glow"]
        for x, y in lv.torches:
            sx, sy = x - ox, y - oy
            if -50 < sx < W + 50 and -50 < sy < H + 50:
                g = glows[(self.t // 5 + x) % 3]
                surf.blit(g, (sx - g.get_width() // 2, sy - g.get_height() // 2 - 2),
                          special_flags=pygame.BLEND_RGB_ADD)
                surf.fill((60, 50, 40), (sx - 2, sy + 2, 5, 2))
                surf.fill((80, 60, 40), (sx - 1, sy, 3, 3))
                fl = (self.t // 4 + x) % 3
                surf.fill((255, 140, 40), (sx - 1, sy - 4 - fl // 2, 3, 4 + fl // 2))
                surf.fill((255, 230, 140), (sx, sy - 2, 1, 2))
        self._draw_objects(surf, ox, oy)
        for c in self.pickups:
            img = self.art["cell"]
            surf.blit(img, (round(c.x - 3 - ox), round(c.y - 3 - oy + math.sin((self.t + c.t) / 5))))
        for e in self.enemies:
            if -60 < e.x - ox < W + 60 and -80 < e.y - oy < H + 80:
                e.draw(surf, ox, oy)
        if self.boss_on or self.boss.state == "dead" or abs(self.boss.x - ox - W / 2) < W:
            self.boss.draw(surf, ox, oy)
        self._draw_hero(surf, ox, oy)
        for pr in self.projs:
            self._draw_proj(surf, pr, ox, oy)
        for pt in self.particles:
            s = pt[6]
            surf.fill(pt[5], (round(pt[0] - ox), round(pt[1] - oy), s, s))
        for text, x, y, n, col in self.popups:
            draw_text(surf, text, x - ox, y - oy, col, align="center")
        surf.blit(self.art["vignette"], (0, 0))
        self._hud(surf)
        if self.menu.open:
            self.menu.draw(surf)

    def _draw_objects(self, surf, ox, oy):
        lv = self.lv
        for s in self.shrines:
            x, y = s["pos"]
            img = self.art["shrine"][1 if s["lit"] else 0]
            if s["lit"]:
                g = self.art["glow_blue"]
                surf.blit(g, (x - 22 - ox, y - 40 - oy), special_flags=pygame.BLEND_RGB_ADD)
            surf.blit(img, (x - img.get_width() // 2 - ox, y - img.get_height() - oy))
            if s["lit"]:
                fl = (self.t // 5) % 3
                surf.fill((120, 220, 255), (x - 2 - ox, y - 30 - fl - oy, 4, 4 + fl))
                surf.fill((230, 250, 255), (x - 1 - ox, y - 28 - oy, 2, 2))
        for a in self.altars:
            x, y = a["pos"]
            img = self.art["altar"][a["kind"]]
            surf.blit(img, (x - img.get_width() // 2 - ox, y - img.get_height() - oy))
            cost = SHOP_COST[min(self.buys[a["kind"]], len(SHOP_COST) - 1)]
            label = "STRENGTH" if a["kind"] == "str" else "VITALITY"
            if a["inside"]:
                draw_text(surf, label, x - ox, y - 46 - oy, (255, 230, 150), align="center")
                draw_text(surf, "DOWN: %d CELLS" % cost, x - ox, y - 36 - oy,
                          (140, 200, 255) if self.cells >= cost else (200, 120, 120), align="center")
            else:
                draw_text(surf, str(cost), x - ox, y - 32 - oy, (140, 200, 255), align="center")
        for rw in self.rewards:
            x, y = rw["pos"]
            if rw["kind"] == "chest":
                img = self.art["chest"][1 if rw["open"] else 0]
                surf.blit(img, (x - img.get_width() // 2 - ox, y - img.get_height() - oy))
            elif not rw["open"]:
                img = self.art["scroll"][rw["kind"]]
                bob = round(math.sin(self.t / 12) * 2)
                g = self.art["glow_blue"]
                surf.blit(g, (x - 22 - ox, y - 38 - oy + bob), special_flags=pygame.BLEND_RGB_ADD)
                surf.blit(img, (x - img.get_width() // 2 - ox, y - 22 - oy + bob))
                surf.fill((70, 64, 84), (x - 6 - ox, y - 6 - oy, 12, 6))
                surf.fill((100, 94, 114), (x - 6 - ox, y - 6 - oy, 12, 1))
        ex, ey = lv.exit_pos
        img = self.art["door"][1 if self.exit_open else 0]
        surf.blit(img, (ex - img.get_width() // 2 - ox, ey - img.get_height() - oy))
        if self.exit_open and (self.t // 20) % 2:
            draw_text(surf, "EXIT", ex - ox, ey - 58 - oy, (255, 230, 150), align="center")

    def _draw_hero(self, surf, ox, oy):
        p = self.p
        if p.inv and p.state != "dead" and (p.inv // 3) % 2:
            return
        key, deg = self._hero_pose()
        flip = p.face < 0
        x, y = round(p.x - ox), round(p.y - oy)
        pygame.draw.ellipse(surf, (6, 4, 10), (x - 7, y - 2, 14, 4))
        if deg:
            img = self.akuma.rotated(key, flip, deg)
            surf.blit(img, (x - img.get_width() // 2, y - 9 - img.get_height() // 2))
            return
        img, (ax, ay) = self.akuma.entry(key, flip)
        if p.state == "ladder":
            flip2 = (int(p.climbed) // 10) % 2 == 1
            img, (ax, ay) = self.akuma.entry(key, flip2)
        if p.state == "drink" and p.t < DRINK_AT:
            surf.blit(img, (x - ax, y - ay))
            f = self.art["flask"][1]
            surf.blit(f, (x + p.face * 5 - 3, y - 30 - min(6, p.t // 3)))
            return
        surf.blit(img, (x - ax, y - ay))

    def _draw_proj(self, surf, pr, ox, oy):
        img = pr.image(self.t)
        x, y = pr.x - ox, pr.y - oy
        if img is not None:
            surf.blit(img, (round(x - img.get_width() / 2), round(y - img.get_height() / 2)))
        elif pr.kind == "bolt":
            r = 3 + (self.t // 4) % 2
            pygame.draw.circle(surf, (110, 30, 150), (round(x), round(y)), r + 1)
            pygame.draw.circle(surf, (220, 140, 255), (round(x), round(y)), r)
            surf.fill((255, 255, 255), (round(x) - 1, round(y) - 1, 2, 2))
        elif pr.kind == "wave":
            h = 12 + (self.t // 3) % 3
            for k in range(3):
                col = ((255, 220, 120), (255, 140, 50), (200, 50, 30))[k]
                surf.fill(col, (round(x - 5 + k * 2 * (1 if pr.vx < 0 else -1) + k), round(y + 7 - h + k * 3),
                                10 - k * 3, h - k * 3))

    def _hud(self, surf):
        # health
        bw = 96
        mh = self.max_hp
        surf.fill(OUTLINE, (3, 3, bw + 4, 9))
        surf.fill((70, 14, 20), (5, 5, bw, 5))
        surf.fill((230, 60, 40), (5, 5, round(bw * self.hp_lag / mh), 5))
        surf.fill((90, 220, 90) if self.hp > mh * 0.3 else (240, 200, 60), (5, 5, round(bw * max(0, self.hp) / mh), 5))
        draw_text(surf, "%d/%d" % (max(0, self.hp), mh), bw + 10, 4, (230, 230, 240))
        # ki
        surf.fill(OUTLINE, (3, 12, 52, 5))
        surf.fill((40, 20, 60), (4, 13, 50, 3))
        col = (230, 120, 255) if self.ki >= HADO_COST else (130, 80, 160)
        surf.fill(col, (4, 13, round(50 * self.ki / KI_MAX), 3))
        surf.fill((255, 255, 255), (4 + round(50 * HADO_COST / KI_MAX), 13, 1, 3))
        # flasks
        for i in range(self.max_flasks):
            surf.blit(self.art["flask"][1 if i < self.flasks else 0], (58 + i * 8, 11))
        # lives: Akuma's prayer beads
        for i in range(LIVES):
            c = (255, 70, 50) if i < self.lives else (60, 40, 50)
            pygame.draw.circle(surf, OUTLINE, (90 + i * 7, 15), 3)
            pygame.draw.circle(surf, c, (90 + i * 7, 15), 2)
        # cells
        surf.blit(self.art["cell"], (W - 30, 4))
        draw_text(surf, str(self.cells), W - 22, 4, (140, 200, 255))
        if self.dmg_mult > 1:
            draw_text(surf, "x%.1f" % self.dmg_mult, W - 50, 4, (255, 140, 120), align="right")
        self._minimap(surf, W - 4 - (GW + AW) * 6, 14)
        # boss bar
        b = self.boss
        if self.boss_on and b.state != "dead":
            bw2 = 200
            x0 = (W - bw2) // 2
            draw_text(surf, "THE WARDEN", W // 2, H - 20, (255, 160, 140), align="center")
            surf.fill(OUTLINE, (x0 - 2, H - 11, bw2 + 4, 7))
            surf.fill((50, 10, 14), (x0, H - 9, bw2, 3))
            surf.fill((220, 40, 40), (x0, H - 9, round(bw2 * b.hp / b.max_hp), 3))
            for f in (0.6, 0.3):
                surf.fill((255, 230, 150), (x0 + round(bw2 * f), H - 9, 1, 3))
        # prompts / banners
        if self.phase == "intro":
            self._title_card(surf)
        if self.banner and self.phase == "play":
            text, sub, n = self.banner
            a = min(1, n / 20)
            band = pygame.Surface((W, 34), pygame.SRCALPHA)
            band.fill((6, 4, 12, int(170 * a)))
            surf.blit(band, (0, 58))
            draw_text(surf, text, W // 2, 62, (255, 230, 150), scale=2, align="center")
            draw_text(surf, sub, W // 2, 80, (200, 190, 220), align="center")
        if self.phase == "won" and self.end_t > 10:
            band = pygame.Surface((W, 46), pygame.SRCALPHA)
            band.fill((6, 4, 12, 200))
            surf.blit(band, (0, 54))
            draw_text(surf, "BIOME CLEARED", W // 2, 60, (255, 220, 60), scale=2, align="center")
            draw_text(surf, "AKUMA LEAVES THE PRISONERS' QUARTERS", W // 2, 82, (255, 255, 255), align="center")
        if self.phase == "lost" and self.end_t > 10:
            band = pygame.Surface((W, 40), pygame.SRCALPHA)
            band.fill((20, 0, 4, 210))
            surf.blit(band, (0, 60))
            draw_text(surf, "YOU DIED", W // 2, 66, (220, 30, 30), scale=3, align="center")

    def _title_card(self, surf):
        n = self.end_t
        a = min(1, n / 20, max(0, (INTRO - n) / 25))
        band = pygame.Surface((W, 70), pygame.SRCALPHA)
        band.fill((4, 2, 10, int(200 * a)))
        surf.blit(band, (0, 50))
        if a > 0.3:
            name = self.LEVEL_NAME
            draw_text(surf, "LEVEL %d" % self.level, W // 2, 56, (200, 180, 140), align="center")
            draw_text(surf, name, W // 2, 72, (255, 230, 170), scale=2, align="center")
            w = min(text_width(name, 2) + 20, int((n / 40) * W))
            surf.fill((200, 160, 90), (W // 2 - w // 2, 92, w, 1))
            draw_text(surf, "FIND THE WARDEN. BREAK OUT.", W // 2, 100, (190, 180, 210), align="center")

    def _minimap(self, surf, x0, y0):
        lv = self.lv
        cw, ch = 6, 4
        bg = pygame.Surface(((GW + AW) * cw + 2, GH * ch + 2), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 140))
        surf.blit(bg, (x0 - 1, y0 - 1))
        for cell, role in lv.roles.items():
            seen = cell in self.visited
            col = {"start": (120, 200, 255), "shop": (255, 220, 90), "shrine": (120, 200, 255),
                   "branch": (200, 120, 255)}.get(role, (150, 140, 170))
            if not seen:
                col = (60, 56, 72)
            surf.fill(col, (x0 + cell[0] * cw, y0 + cell[1] * ch, cw - 1, ch - 1))
        ac = lv.arena_cell
        surf.fill((200, 60, 50) if (ac in self.visited or (ac[0] + 1, ac[1]) in self.visited) else (90, 40, 40),
                  (x0 + ac[0] * cw, y0 + ac[1] * ch, cw * 2 - 1, ch - 1))
        px = x0 + int(self.p.x / (RW * T) * cw)
        py = y0 + int((self.p.y - 8) / (RH * T) * ch)
        if (self.t // 10) % 2:
            surf.fill((255, 255, 255), (px, py, 1, 1))
