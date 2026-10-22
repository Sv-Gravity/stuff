"""Level 8: the frozen compound, a top-down sneaking level.

Akuma has to cross a snowy yard and a hangar to the elevator without being
seen. Genome soldiers patrol with vision cones (much shorter when Akuma is in
a shadow), hear him walking nearby, and look around at their patrol stops;
security cameras sweep the hangar and a laser fence guards the elevator.

A soldier who half sees him (far end of the cone, or a cardboard box moving)
goes "?" and walks over to look. Seen properly: "!", the ALERT phase starts
with its countdown (reset whenever someone sees him again), every soldier
converges, then EVASION (searching), then CAUTION, then back to normal.
A soldier who catches him starts a side-view fight against rifles
(game.start_fight); a soldier touched from behind before he knows Akuma is
there is a sneak attack instead.

A cardboard box is hidden in the dark storage room in the west wing: picked
up it is worn at once, and standing still in it Akuma cannot be seen at all.
"""

import math
import random
from collections import deque

import pygame

from . import audio
from . import fight as F
from .akuma_sprites import MapArt, MAP_SCALE, portrait
from .art import random_look, shade
from .config import W, H
from .fighters import HIT
from .font import draw_text, wrap
from .pause import PauseMenu

T = 16
# ---------------------------------------------------------------------------
# the map: # wall  . floor  : floor in shadow  , snow  ; snow in shadow
#          C crate  T truck  E elevator (the goal)  B cardboard box  P start
# ---------------------------------------------------------------------------
MAP = """
########################################################
#::::::::######::::..........................#....EEE..#
#::::::::######::::..........................#.........#
#:::B::::######::::..CC...........CC...................#
#::::::::######::::..CC...........CC...................#
#::::::::######::::.::::.........::::........###########
#::::::::######::::.::::.........::::..................#
#####::########::::....................................#
#:::::::::::::#::::........CC..........................#
#:::::::::::::#::::........CC..........CC.......CC.....#
#::::::::::::::::::.......::::.........CC.......CC.....#
#::::::::::::::::::.......::::........::::.....::::....#
#:::::::::::::#::::...................::::.....::::....#
######::######################..########################
#;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;#
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,CC,,,,,,,,,#
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,CC,,,,,,,,,#
#,,,,,,,,,,,TTTT,,,,,,,,,,,,,,,,,,,,,,,,,,,;;;;,,,,,,,,#
#,,,,,,,,,,,TTTT,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#
#,,,,,,,,,,;;;;;;,,,,,,,,,,,,,,,,,,,TTTT,,,,,,,,,,,CC,,#
#,,,,,,,,,,;;;;;;,,C,,,,,,,,,,,,,,,,TTTT,,,,,,,,,,;;;;,#
#,,,,,,,C,,,,,,,,,,C,,,,,,,,,,,,,,,;;;;;;,,,,,,,,,,,,,,#
#,,,,,,;;;,,,,,,,,;;;,,,,,,,,,,,,,,;;;;;;,,,,,,,,,,,,,,#
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#
#,,,,,,,,,,,,,,,,,,,,,,,TTTT,,,,,,,,,,,,,,,,,,,,,,,,,,,#
#,,,,,,,,,,,,,,,,,,,,,,,TTTT,,,,,,,,,,,,,,,,,,CC,,,,,,,#
#,,,,,,,,,,,,,,,,,,,,,,;;;;;;,,,,,,,,,,,,,,,,,CC,,,,,,,#
#,,,,,,P,,,,,,,,,,,,,,,;;;;;;,,,,C,,,,,,,,,,,;;;;,,,,,,#
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,;;;,,,,,,,,,,,,,,,,,,,,#
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#
########################################################
"""
SOLID = set("#CT")
SHADOW = set(":;B")
SNOW = set(",;P")
HELIPAD = (7, 28)            # tile the painted H sits on

# patrol routes in tiles: (tx, ty, frames to stand and look around there)
ROUTES = [
    [(4, 22, 100), (33, 23, 100)],                                     # yard, west-east
    [(42, 16, 70), (51, 24, 60), (42, 31, 70), (32, 31, 60)],          # yard, east loop
    [(29, 16, 200), (34, 16, 200)],                                    # outside the main door
    [(20, 7, 60), (43, 7, 60), (43, 12, 40), (24, 12, 60)],            # hangar hall loop
    [(44, 2, 220), (44, 9, 120)],                                      # by the elevator room
    [(2, 10, 140), (12, 10, 140)],                                     # dark west corridor
]
# security cameras: wall tile, direction looked at (degrees, 90 = down), sweep +-, period
CAMERAS = [((36, 13), 90, 50, 400), ((25, 0), 90, 55, 460), ((17, 13), 90, 45, 360)]
# laser fence across the elevator room door: tile column, rows, frames on, frames off
LASERS = [((45, 3), (45, 4), 150, 80)]

# ---- tuning ----------------------------------------------------------------
WALK, SNEAK, BOX_SPEED = 1.35, 0.6, 0.8        # Akuma, px / frame
VIEW_RANGE, VIEW_HALF = 84, math.radians(32)    # a soldier's cone
CAM_RANGE, CAM_HALF = 82, math.radians(20)
SHADOW_K = 0.33              # cone reach on a target standing in a shadow
CAUTION_K = 1.15             # longer looks while on CAUTION
NEAR_K = 0.55                # seen inside this part of the cone: "!" at once
NOTICE_T = 40                # frames kept in a far view before "?" becomes "!"
BOX_SPOT = 26                # a moving box this close to a soldier is found out
HEAR = 44                    # px a normal step is heard over (sneaking is silent)
KNOCK_HEAR = 120
G_WALK, G_CAUTION, G_RUN, G_SEARCH = 0.5, 0.7, 1.25, 0.85
ALERT_T, EVASION_T, CAUTION_T = 60 * 15, 60 * 20, 60 * 25
FREEZE = 26                  # the world stops for the "!" sting
INVULN = 120                 # after a fight, before another can start

# ---- the soldiers in a fight -------------------------------------------------
GUARD_HITS = 5               # normal hits a soldier takes
SHOT_DMG, BURST_DMG, LOW_DMG, BUTT_DMG = 34, 20, 28, 22
BULLET_SPEED = 7.5
GUARD_AI = dict(aggression=0.85, block=0.3, jumpiness=0.1, reaction=4)

CONTROLS = [
    "ARROWS / WASD: MOVE",
    "HOLD K: SNEAK (SLOW AND SILENT)",
    "J BY A WALL: KNOCK TO LURE A GUARD",
    "L / SPACE: CARDBOARD BOX ON / OFF",
    "STAND STILL IN THE BOX: INVISIBLE",
    "SHADOWS HIDE YOU, CONES SHOW WHERE THEY LOOK",
    "CAUGHT: FIGHT RIFLES. JUMP OR BLOCK THE SHOTS",
    "REACH THE ELEVATOR (TOP RIGHT)",
]

CODEC = [
    ("CHUN-LI", "AKUMA, DO YOU READ ME? YOU'RE INSIDE THE FROZEN COMPOUND."),
    ("AKUMA", "..."),
    ("CHUN-LI", "GENOME SOLDIERS GUARD EVERY YARD AND CORRIDOR. THEIR RIFLES WILL TEAR YOU APART."),
    ("CHUN-LI", "STAY IN THE SHADOWS, WATCH WHERE THEY LOOK, AND GET TO THE ELEVATOR."),
    ("AKUMA", "A DEMON DOES NOT HIDE."),
    ("CHUN-LI", "THIS ONE DOES. OH, AND SOMEONE LEFT A CARDBOARD BOX IN STORAGE. DON'T ASK."),
]
CALLER = "chunli"
FREQ = "140.85"

DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def _rows():
    return [r for r in MAP.strip("\n").split("\n")]


# ---------------------------------------------------------------------------
# guns: the soldiers' fight moves (akuma/fighters.py enemy move format)
# ---------------------------------------------------------------------------
_TRACER = None


def tracer_frames():
    """A bullet: a hot white core with an orange tail, facing right."""
    global _TRACER
    if _TRACER is None:
        out = []
        for k in range(2):
            s = pygame.Surface((14, 3), pygame.SRCALPHA)
            for x in range(14):
                t = x / 13
                a = int(255 * t ** 1.4)
                col = (255, 120 + int(100 * t), 40) if x < 10 else (255, 250, 210)
                s.fill(col + (a,), (x, 1, 1, 1))
                if x >= 9 + k:
                    s.fill((255, 220, 140, a // 2), (x, 0, 1, 1))
                    s.fill((255, 220, 140, a // 2), (x, 2, 1, 1))
            out.append(s)
        _TRACER = out
    return _TRACER


def _bullet(dmg, y, chip, x=24):
    return dict(speed=BULLET_SPEED, dmg=dmg, hitstun=22, blockstun=12, chip=chip,
                colors=((255, 255, 230), (255, 220, 120), (230, 120, 40)),
                y=y, px=True, x=x, tracer=True, frames=tracer_frames(), size=(12, 5))


def m_rifle(rng):
    return dict(name="Rifle Shot", range=(30, 400), gun=True,
                phases=[("startup", 9 + rng.randint(0, 3), "hado_prep"), ("startup", 4, "hado_fire"),
                        ("recovery", 20, "hado_fire")],
                events={10: dict(sound="gunshot", proj=_bullet(SHOT_DMG, -44, 5))})


def m_burst(rng):
    return dict(name="Burst Fire", range=(40, 400), gun=True,
                phases=[("startup", 14, "hado_prep"), ("startup", 12, "hado_fire"),
                        ("recovery", 26, "hado_fire")],
                events={14: dict(sound="gunshot", proj=_bullet(BURST_DMG, -44, 3)),
                        19: dict(sound="gunshot", proj=_bullet(BURST_DMG, -42, 3)),
                        24: dict(sound="gunshot", proj=_bullet(BURST_DMG, -46, 3))})


def m_low_shot(rng):
    return dict(name="Kneeling Shot", range=(40, 400), gun=True, crouching=True,
                phases=[("startup", 12, "crouch"), ("startup", 4, "crouch_jab"),
                        ("recovery", 22, "crouch")],
                events={13: dict(sound="gunshot", proj=_bullet(LOW_DMG, -22, 4, x=22))})


def m_butt(rng):
    return dict(name="Rifle Butt", range=(0, 34),
                phases=[("startup", 6, "punch_prep"), ("active", 4, "punch"), ("recovery", 14, "punch_prep")],
                hitbox=(8, -38, 22, 12), dmg=BUTT_DMG, hitstun=20, blockstun=12, height="mid",
                knockdown=True, launch=-4.0, push=2.6, events={4: dict(sound="whiff")})


def guard_moveset(rng):
    return [m_rifle(rng), m_burst(rng), m_low_shot(rng), m_butt(rng)]


_ART = {}


def _map_art(cid):
    if cid not in _ART:
        _ART[cid] = MapArt(cid, MAP_SCALE)
    return _ART[cid]


class Guard:
    """A patrolling soldier, and the enemy namespace handed to game.start_fight."""

    def __init__(self, rng, route, index):
        self.route = [((tx + 0.5) * T, (ty + 0.5) * T, wait) for tx, ty, wait in route]
        self.x, self.y = self.route[0][0], self.route[0][1]
        self.ri = 0
        self.wait = self.route[0][2] // 2
        self.angle = rng.uniform(0, math.tau)
        self.look_base = self.angle
        self.look_t = rng.randrange(200)
        self.state = "patrol"        # patrol, suspicious, alert, search
        self.sub = None
        self.t = 0
        self.stim = None
        self.notice = 0
        self.exclaim = 0
        self.huh = 0
        self.search_to = None
        self.alive = True
        self.moving = False
        self.walked = 0.0
        self.face = 1
        self.anim = rng.randrange(60)
        # --- fight namespace (like dungeon.MapEnemy) ---
        self.name = "GENOME SOLDIER"
        self.cid = "ryu" if index % 2 == 0 else "ken"
        self.look = random_look(rng)
        self.boss = False
        self.car = False
        self.level = 4
        self.hp = HIT * GUARD_HITS
        self.walk = 1.5
        self.moves = guard_moveset(rng)
        self.ai = dict(GUARD_AI)
        self.allies = []
        self.map_art = _map_art(self.cid)

    def rect(self):
        return pygame.Rect(round(self.x) - 5, round(self.y) - 4, 10, 8)


# ---------------------------------------------------------------------------
# art
# ---------------------------------------------------------------------------
SNOW_C = (206, 214, 230)
METAL_C = (74, 82, 98)
WALL_TOP_C = (30, 34, 48)
PANEL_C = (92, 100, 120)


def _make_tiles(rng):
    t = {}
    snow = []
    for v in range(4):
        s = pygame.Surface((T, T))
        s.fill(SNOW_C)
        for _ in range(10):
            s.set_at((rng.randrange(T), rng.randrange(T)), rng.choice(((236, 242, 252), (184, 194, 214))))
        if v == 3:
            for x in range(2, 14, 3):
                s.set_at((x, 9 + (x % 2)), (176, 186, 206))
        snow.append(s)
    t["snow"] = snow
    metal = []
    for v in range(3):
        s = pygame.Surface((T, T))
        s.fill(METAL_C)
        g = shade(METAL_C, 0.8)
        for y in range(2, 16, 4):
            pygame.draw.line(s, g, (1, y), (14, y))
        pygame.draw.line(s, shade(METAL_C, 1.18), (0, 0), (15, 0))
        pygame.draw.line(s, shade(METAL_C, 0.7), (0, 15), (15, 15))
        for p in ((1, 1), (14, 1), (1, 14), (14, 14)):
            s.set_at(p, (120, 128, 146))
        if v == 2:
            pygame.draw.line(s, (60, 66, 80), (4, 6), (9, 10))
        metal.append(s)
    t["metal"] = metal
    top = pygame.Surface((T, T))
    top.fill(WALL_TOP_C)
    for _ in range(6):
        top.set_at((rng.randrange(T), rng.randrange(T)), (60, 66, 84))
    t["wall_top"] = top
    snowy = top.copy()
    for _ in range(14):
        snowy.set_at((rng.randrange(T), rng.randrange(T)), (200, 208, 226))
    t["wall_top_snow"] = snowy
    face = pygame.Surface((T, T))
    face.fill(PANEL_C)
    pygame.draw.line(face, shade(PANEL_C, 0.7), (7, 0), (7, 15))
    pygame.draw.line(face, shade(PANEL_C, 0.7), (0, 9), (15, 9))
    pygame.draw.line(face, shade(PANEL_C, 1.3), (0, 0), (15, 0))
    pygame.draw.line(face, shade(PANEL_C, 0.55), (0, 15), (15, 15))
    for p in ((2, 3), (12, 3), (2, 12), (12, 12)):
        face.set_at(p, (140, 148, 166))
    t["wall_face"] = face
    # an olive army crate seen from above, front edge showing
    crate = pygame.Surface((T, T), pygame.SRCALPHA)
    crate.fill((92, 98, 62), (0, 0, 16, 12))
    crate.fill((64, 70, 42), (0, 12, 16, 4))
    pygame.draw.rect(crate, (50, 54, 32), (0, 0, 16, 16), 1)
    pygame.draw.line(crate, (112, 120, 78), (1, 1), (14, 1))
    pygame.draw.line(crate, (70, 76, 46), (2, 2), (13, 10))
    pygame.draw.line(crate, (70, 76, 46), (13, 2), (2, 10))
    crate.fill((220, 220, 200), (6, 13, 4, 1))
    t["crate"] = crate
    t["truck"] = _truck()
    return t


def _truck():
    s = pygame.Surface((64, 32), pygame.SRCALPHA)
    for x in (6, 16, 34, 52):
        s.fill((18, 18, 22), (x, 0, 7, 3))
        s.fill((18, 18, 22), (x, 29, 7, 3))
    s.fill((92, 100, 70), (1, 2, 46, 28))                  # canvas back
    for x in range(5, 46, 6):
        pygame.draw.line(s, (72, 80, 54), (x, 3), (x, 28))
    pygame.draw.rect(s, (52, 58, 38), (1, 2, 46, 28), 1)
    rng = random.Random(8)
    for _ in range(26):                                     # snow on the canvas
        s.fill((226, 232, 242), (rng.randrange(3, 44), rng.randrange(4, 27), 2, 1))
    s.fill((70, 78, 58), (48, 4, 15, 24))                  # cab
    pygame.draw.rect(s, (44, 50, 34), (48, 4, 15, 24), 1)
    s.fill((150, 182, 204), (58, 7, 3, 18))                # windscreen
    s.fill((210, 230, 240), (59, 8, 1, 6))
    s.fill((255, 230, 140), (62, 5, 1, 3))
    s.fill((255, 230, 140), (62, 24, 1, 3))
    return s


def _box_sprites():
    """The cardboard box Akuma wears: still, and two shuffle frames."""
    out = []
    for k in range(3):
        s = pygame.Surface((20, 18), pygame.SRCALPHA)
        y0 = 2 if k == 0 else (1 if k == 1 else 3)
        s.fill((176, 132, 78), (1, y0 + 4, 18, 11))        # front
        s.fill((198, 156, 98), (1, y0, 18, 5))              # top
        pygame.draw.line(s, (150, 110, 62), (10, y0), (10, y0 + 4))
        pygame.draw.rect(s, (110, 76, 40), (1, y0, 18, 15), 1)
        s.fill((30, 20, 14), (5, y0 + 7, 10, 2))            # the slit
        if k:
            s.set_at((8, y0 + 7), (255, 255, 255))
            s.set_at((11, y0 + 7), (255, 255, 255))
        s.fill((120, 160, 210), (13, y0 + 11, 4, 2))        # a printed label
        out.append(s)
    pick = pygame.Surface((16, 12), pygame.SRCALPHA)
    pick.fill((176, 132, 78), (1, 3, 14, 8))
    pick.fill((198, 156, 98), (1, 1, 14, 3))
    pygame.draw.rect(pick, (110, 76, 40), (1, 1, 14, 10), 1)
    out.append(pick)
    return out


def _codec_portrait(cid):
    img = pygame.transform.scale(portrait(cid), (60, 60))
    img.fill((150, 255, 170), special_flags=pygame.BLEND_RGB_MULT)
    for y in range(0, 60, 2):                                # scanlines
        img.fill((200, 210, 200), (0, y, 60, 1), special_flags=pygame.BLEND_RGB_MULT)
    return img


# ---------------------------------------------------------------------------
class StealthScene:
    def __init__(self, game, seed=None, level=8, hp=None):
        F.init_shared()
        self.game = game
        self.level = level
        self.rng = random.Random(seed)
        self.grid = _rows()
        self.gw, self.gh = len(self.grid[0]), len(self.grid)
        self.mw, self.mh = self.gw * T, self.gh * T
        self.tiles = _make_tiles(random.Random(seed or 0))
        self.box_img = _box_sprites()
        self.art = _map_art("akuma")
        self.menu = PauseMenu(game, CONTROLS)
        self.passable = [(x, y) for y in range(self.gh) for x in range(self.gw) if not self.solid(x, y)]
        self.exit_tiles = set()
        for y, row in enumerate(self.grid):
            for x, c in enumerate(row):
                if c == "P":
                    self.px, self.py = (x + 0.5) * T, (y + 0.5) * T
                elif c == "B":
                    self.box_pickup = [(x + 0.5) * T, (y + 0.5) * T]
                elif c == "E":
                    self.exit_tiles.add((x, y))
        self._render()
        self.radar_map = self._render_radar()
        self.guards = [Guard(self.rng, r, i) for i, r in enumerate(ROUTES)]
        self.cameras = [dict(x=(tx + 0.5) * T, y=(ty + 1) * T - 2, base=math.radians(b), sweep=math.radians(s),
                             period=p, angle=math.radians(b), t=self.rng.randrange(p), flash=0)
                        for (tx, ty), b, s, p in CAMERAS]
        self.lasers = [dict(x=(a[0] + 0.5) * T, y0=a[1] * T, y1=(b[1] + 1) * T, on=on, off=off,
                            t=self.rng.randrange(on + off)) for a, b, on, off in LASERS]
        self.hp = game.akuma_max if hp is None else hp
        self.pface = 1
        self.pvx = self.pvy = 0.0
        self.walked = 0.0
        self.moving = False
        self.still = 99            # frames Akuma has not moved
        self.sneaking = False
        self.has_box = False
        self.box_on = False
        self.invuln = 0
        self.steps = 0
        self.footprints = deque(maxlen=120)
        self.flakes = [[self.rng.uniform(0, W), self.rng.uniform(0, H), self.rng.uniform(0.2, 0.6)]
                       for _ in range(46)]
        self.ripples = []
        # alert state: normal, alert, evasion, caution
        self.phase = "normal"
        self.timer = 0
        self.lkp = (self.px, self.py)
        self.freeze = 0
        self.ignore_player = False  # tests / bots
        self.messages = []
        self.encounter = None
        self.encounter_t = 0
        self._fields = {}
        # intro: codec call, then the level card
        self.stage = "ring"         # ring, codec, card, play, won
        self.t = 0
        self.line = 0
        self.chars = 0
        self.result = None
        self.anim = 0
        self.caller_img = _codec_portrait(CALLER)
        self.akuma_img = _codec_portrait("akuma")

    # ---- map queries ------------------------------------------------------
    def tile(self, tx, ty):
        if 0 <= tx < self.gw and 0 <= ty < self.gh:
            return self.grid[ty][tx]
        return "#"

    def solid(self, tx, ty):
        return self.tile(tx, ty) in SOLID

    def in_shadow(self, x, y):
        return self.tile(int(x // T), int(y // T)) in SHADOW

    def rect_hits(self, r):
        for ty in range(r.top // T, (r.bottom - 1) // T + 1):
            for tx in range(r.left // T, (r.right - 1) // T + 1):
                if self.solid(tx, ty):
                    return True
        return False

    def line_of_sight(self, x0, y0, x1, y1):
        d = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(d / 4))
        for i in range(1, n + 1):
            t = i / n
            if self.solid(int((x0 + (x1 - x0) * t) // T), int((y0 + (y1 - y0) * t) // T)):
                return False
        return True

    def player_rect(self):
        return pygame.Rect(round(self.px) - 5, round(self.py) - 4, 10, 8)

    @property
    def paused(self):
        return self.menu.open

    def message(self, text, frames=120):
        if not self.messages or self.messages[-1][0] != text:
            self.messages.append([text, frames])

    # ---- art --------------------------------------------------------------
    def _render(self):
        rng = random.Random(77)
        surf = pygame.Surface((self.mw, self.mh))
        dark = pygame.Surface((self.mw, self.mh), pygame.SRCALPHA)
        trucks = []
        for ty in range(self.gh):
            for tx in range(self.gw):
                c = self.tile(tx, ty)
                x, y = tx * T, ty * T
                outdoor = ty >= 13
                if c == "#":
                    if not self.solid(tx, ty + 1) and ty + 1 < self.gh:
                        surf.blit(self.tiles["wall_face"], (x, y))
                    else:
                        surf.blit(self.tiles["wall_top_snow" if ty in (0, 13) or ty > 13 or tx in (0, 55)
                                             else "wall_top"], (x, y))
                    continue
                floor = self.tiles["snow"][rng.choice((0, 0, 1, 2, 3))] if outdoor else \
                    self.tiles["metal"][rng.choice((0, 0, 1, 2))]
                surf.blit(floor, (x, y))
                if c == "C":
                    surf.blit(self.tiles["crate"], (x, y))
                elif c == "T" and self.tile(tx - 1, ty) != "T" and self.tile(tx, ty - 1) != "T":
                    trucks.append((x, y))
                elif c == "E":
                    for k in range(0, T, 4):
                        surf.fill((220, 190, 40) if (k // 4 + tx) % 2 else (30, 30, 30), (x + k, y + 12, 4, 4))
                if c in SHADOW:
                    dark.fill((6, 10, 26, 135), (x, y, T, T))
                if self.solid(tx, ty - 1) and not outdoor:
                    surf.fill((40, 44, 58), (x, y, T, 3))
        for x, y in trucks:
            surf.blit(self.tiles["truck"], (x, y))
        # the helipad
        hx, hy = (HELIPAD[0] + 0.5) * T, (HELIPAD[1] + 0.5) * T
        pygame.draw.circle(surf, (176, 180, 190), (hx, hy), 34, 3)
        pygame.draw.circle(surf, (226, 196, 70), (hx, hy), 30, 1)
        for dx in (-9, 9):
            surf.fill((226, 196, 70), (hx + dx - 2, hy - 12, 4, 24))
        surf.fill((226, 196, 70), (hx - 9, hy - 2, 18, 4))
        # elevator doors in the wall above the goal
        ex = min(x for x, _ in self.exit_tiles) * T
        surf.fill((120, 130, 150), (ex, 0, 3 * T, T))
        pygame.draw.line(surf, (60, 66, 80), (ex + 24, 2), (ex + 24, 15))
        pygame.draw.rect(surf, (50, 56, 70), (ex, 0, 3 * T, T), 1)
        surf.fill((80, 255, 120), (ex + 22, 2, 4, 2))
        self.map_surf = surf
        self.dark = dark

    def _render_radar(self):
        s = pygame.Surface((self.gw * 4, self.gh * 4))
        s.fill((4, 26, 14))
        for ty in range(self.gh):
            for tx in range(self.gw):
                if self.solid(tx, ty):
                    s.fill((40, 120, 66), (tx * 4, ty * 4, 4, 4))
        for tx, ty in self.exit_tiles:
            s.fill((200, 255, 200), (tx * 4, ty * 4, 4, 4))
        return s

    # ---- pathing -----------------------------------------------------------
    def _field(self, goal):
        f = self._fields.get(goal)
        if f is None:
            if len(self._fields) > 48:
                self._fields.clear()
            f = {goal: 0}
            q = deque([goal])
            while q:
                c = q.popleft()
                d = f[c] + 1
                for dx, dy in DIRS8:
                    n = (c[0] + dx, c[1] + dy)
                    if n in f or self.solid(*n):
                        continue
                    if dx and dy and (self.solid(c[0] + dx, c[1]) or self.solid(c[0], c[1] + dy)):
                        continue
                    f[n] = d
                    q.append(n)
            self._fields[goal] = f
        return f

    def _step_toward(self, g, tx, ty, speed):
        """Walk a soldier one frame along the shortest path to (tx, ty).
        Returns True once he is there."""
        d = math.hypot(tx - g.x, ty - g.y)
        if d < max(1.5, speed):
            g.x, g.y = tx, ty
            g.moving = False
            return True
        goal = (int(tx // T), int(ty // T))
        here = (int(g.x // T), int(g.y // T))
        if here == goal or (d < 20 and self.line_of_sight(g.x, g.y, tx, ty)):
            nx, ny = tx, ty
        else:
            f = self._field(goal)
            best, bd = None, f.get(here, 10 ** 6)
            for dx, dy in DIRS8:
                n = (here[0] + dx, here[1] + dy)
                v = f.get(n)
                if v is not None and v < bd:
                    if dx and dy and (self.solid(here[0] + dx, here[1]) or self.solid(here[0], here[1] + dy)):
                        continue
                    best, bd = n, v
            if best is None:
                nx, ny = tx, ty
            else:
                nx, ny = (best[0] + 0.5) * T, (best[1] + 0.5) * T
        dd = math.hypot(nx - g.x, ny - g.y) or 1
        vx, vy = (nx - g.x) / dd * speed, (ny - g.y) / dd * speed
        g.x += vx
        g.y += vy
        g.moving = True
        g.walked += speed
        if abs(vx) > 0.05:
            g.face = 1 if vx > 0 else -1
        self._turn(g, math.atan2(vy, vx), 0.15)
        return False

    @staticmethod
    def _turn(g, target, rate):
        diff = (target - g.angle + math.pi) % math.tau - math.pi
        g.angle += max(-rate, min(rate, diff))

    # ---- seeing and hearing ------------------------------------------------
    def visibility(self):
        """What a watcher can see of Akuma: 'hidden' (still in the box),
        'box' (a box shuffling along) or 'full'."""
        if self.ignore_player:
            return "hidden"
        if self.box_on:
            return "hidden" if self.still >= 3 else "box"
        return "full"

    def in_view(self, x, y, angle, half, reach, tx=None, ty=None):
        """Is the point (Akuma by default) inside this cone, in reach and in sight?"""
        if tx is None:
            tx, ty = self.px, self.py - 4
        d = math.hypot(tx - x, ty - y)
        if self.in_shadow(tx, ty + 4):
            reach *= SHADOW_K
        if self.phase == "caution":
            reach *= CAUTION_K
        if d > reach:
            return False
        if d > 6:
            diff = abs((math.atan2(ty - y, tx - x) - angle + math.pi) % math.tau - math.pi)
            if diff > half:
                return False
        return self.line_of_sight(x, y, tx, ty)

    def guard_sees(self, g):
        return self.in_view(g.x, g.y - 4, g.angle, VIEW_HALF, VIEW_RANGE)

    def _cone(self, x, y, angle, half, reach, cx, cy):
        pts = [(x - cx, y - cy)]
        n = 12
        for i in range(n + 1):
            a = angle - half + 2 * half * i / n
            ca, sa = math.cos(a), math.sin(a)
            r = 4
            while r < reach and not self.solid(int((x + ca * r) // T), int((y + sa * r) // T)):
                r += 4
            r = min(r, reach)
            pts.append((x + ca * r - cx, y + sa * r - cy))
        return pts

    # ---- alert phases ------------------------------------------------------
    def spotted(self, by=None):
        """Someone saw Akuma properly: ALERT (or keep it going)."""
        self.lkp = (self.px, self.py)
        if self.phase != "alert":
            audio.play("mgs_alert")
            self.phase = "alert"
            self.freeze = FREEZE
            self.message("ALERT!", 90)
            for g in self.guards:
                if g.alive:
                    g.state = "alert"
                    g.huh = 0
        if by is not None:
            if not by.exclaim:
                by.exclaim = 60
        self.timer = ALERT_T

    def _phases(self):
        if self.phase == "alert":
            if self.t % 44 == 0:
                audio.play("alarm", 0.45)
            self.timer -= 1
            if self.timer <= 0:
                self.phase = "evasion"
                self.timer = EVASION_T
                audio.play("mgs_evasion")
                self.message("EVASION", 90)
                for g in self.guards:
                    if g.alive:
                        g.state = "search"
                        g.search_to = None
        elif self.phase == "evasion":
            self.timer -= 1
            if self.timer <= 0:
                self.phase = "caution"
                self.timer = CAUTION_T
                audio.play("mgs_evasion", 0.6)
                self.message("CAUTION", 90)
                for g in self.guards:
                    if g.alive:
                        self._back_to_patrol(g)
        elif self.phase == "caution":
            self.timer -= 1
            if self.timer <= 0:
                self.phase = "normal"
                self.timer = 0
                audio.play("mgs_clear")
                self.message("ALL CLEAR", 80)

    def _back_to_patrol(self, g):
        g.state = "patrol"
        g.stim = None
        g.notice = 0
        # rejoin the route at its nearest stop
        g.ri = min(range(len(g.route)), key=lambda i: math.hypot(g.route[i][0] - g.x, g.route[i][1] - g.y))
        g.wait = 0

    def _suspect(self, g, x, y, sound=True):
        if g.state not in ("patrol", "suspicious"):
            return
        if g.state != "suspicious" or g.sub == "search":
            g.sub = "look"
            g.t = 0
            if sound:
                audio.play("mgs_huh", 0.8)
            g.huh = 50
        g.state = "suspicious"
        g.stim = (x, y)

    # ---- update ------------------------------------------------------------
    def update(self, inp):
        if self.encounter:
            self.encounter_t += 1
            if self.encounter_t >= 14:
                g, ambush = self.encounter
                self.encounter = None
                self.game.start_fight(g, self.hp, ambush)
            return
        if self.menu.open:
            self.menu.update(inp)
            return
        self.t += 1
        self.anim += 1
        if self.stage == "ring":
            if self.t in (1, 34):
                audio.play("codec")
            if self.t >= 60 or (self.t > 10 and inp.any_pressed("punch", "kick", "special", "start")):
                self.stage, self.t = "codec", 0
                audio.play("codec_beep")
            return
        if self.stage == "codec":
            self._codec(inp)
            return
        if self.stage == "card":
            if self.t >= 100 or (self.t > 20 and inp.any_pressed("punch", "kick", "special", "start")):
                self.stage, self.t = "play", 0
            return
        if self.stage == "won":
            if self.t >= 110 or (self.t > 40 and inp.any_pressed("punch", "kick", "special", "start")):
                if self.result is None:
                    self.result = "win"
                    self.game.level_done(self, max(1, self.hp))
            return
        if self.menu.toggle(inp):
            return
        for m in self.messages[:1]:
            m[1] -= 1
        self.messages = [m for m in self.messages if m[1] > 0]
        self._weather()
        if self.freeze:
            self.freeze -= 1          # the world holds still for the "!" sting
            return
        if self.invuln:
            self.invuln -= 1
        self._move(inp)
        self._items(inp)
        for c in self.cameras:
            self._camera(c)
        for lz in self.lasers:
            self._laser(lz)
        vis = self.visibility()
        for g in self.guards:
            if g.alive:
                self._guard(g, vis)
        self._phases()
        self._touch()
        if (int(self.px // T), int(self.py // T)) in self.exit_tiles and self.stage == "play":
            self.stage, self.t = "won", 0
            audio.play("mgs_item")

    def _codec(self, inp):
        who, text = CODEC[self.line]
        if self.chars < len(text):
            self.chars += 1 if self.t % 2 == 0 else 0
            if self.t % 6 == 0 and text[min(self.chars, len(text) - 1)] != " ":
                audio.play("codec_beep", 0.4)
        if inp.any_pressed("punch", "kick", "special", "start"):
            if self.chars < len(text):
                self.chars = len(text)
            else:
                self.line += 1
                self.chars = 0
                audio.play("codec_beep")
                if self.line >= len(CODEC):
                    self.stage, self.t = "card", 0
                    audio.play("fight")
        if inp.pressed("back"):
            self.stage, self.t = "card", 0

    def _weather(self):
        for f in self.flakes:
            f[1] += f[2]
            f[0] += math.sin((self.anim + f[1]) / 30) * 0.2
            if f[1] > H:
                f[1] = -2
                f[0] = self.rng.uniform(0, W)
        for r in self.ripples:
            r[2] += 1
        self.ripples = [r for r in self.ripples if r[2] < 30]

    def _move(self, inp):
        dx = (1 if inp.held("right") else 0) - (1 if inp.held("left") else 0)
        dy = (1 if inp.held("down") else 0) - (1 if inp.held("up") else 0)
        self.sneaking = inp.held("kick") and not self.box_on
        base = BOX_SPEED if self.box_on else SNEAK if self.sneaking else WALK
        sp = base * (0.7071 if dx and dy else 1)
        self.pvx += (dx * sp - self.pvx) * 0.3
        self.pvy += (dy * sp - self.pvy) * 0.3
        if not dx and abs(self.pvx) < 0.05:
            self.pvx = 0.0
        if not dy and abs(self.pvy) < 0.05:
            self.pvy = 0.0
        moved = 0.0
        if self.pvx or self.pvy:
            ox, oy = self.px, self.py
            self._slide(self.pvx, 0)
            self._slide(0, self.pvy)
            moved = math.hypot(self.px - ox, self.py - oy)
            self.walked += moved
        self.moving = moved > 0.2
        self.still = 0 if self.moving else self.still + 1
        if dx:
            self.pface = dx
        if self.moving:
            self.steps += 1
            loud = not self.sneaking and not self.box_on
            if self.steps % (18 if loud else 30) == 0:
                audio.play("step", 0.5 if loud else 0.15)
                if not self.box_on and (self.py // T) >= 13:
                    self.footprints.append([self.px + (2 if (self.steps // 18) % 2 else -2), self.py + 2, 700])
            if loud and self.steps % 10 == 0:
                self._noise(HEAR)

    def _slide(self, dx, dy):
        nx, ny = self.px + dx, self.py + dy
        r = pygame.Rect(round(nx) - 5, round(ny) - 4, 10, 8)
        if not self.rect_hits(r):
            self.px, self.py = nx, ny
            return
        for nudge in (1, -1, 2, -2, 3, -3):
            r2 = r.move(0, nudge) if dx else r.move(nudge, 0)
            if not self.rect_hits(r2):
                if dx:
                    self.py += nudge * 0.5
                else:
                    self.px += nudge * 0.5
                return

    def _noise(self, radius, x=None, y=None):
        if self.ignore_player:
            return
        x = self.px if x is None else x
        y = self.py if y is None else y
        for g in self.guards:
            if g.alive and g.state in ("patrol", "suspicious") and math.hypot(g.x - x, g.y - y) < radius:
                self._suspect(g, x, y)

    def _items(self, inp):
        bp = self.box_pickup
        if bp and self.player_rect().colliderect(pygame.Rect(bp[0] - 7, bp[1] - 6, 14, 12)):
            self.box_pickup = None
            self.has_box = True
            self.box_on = True
            self.still = 0
            audio.play("mgs_item")
            self.message("CARDBOARD BOX: EQUIPPED", 150)
            self.message("L / SPACE: TAKE IT OFF AND ON", 120)
        if self.has_box and inp.pressed("special"):
            self.box_on = not self.box_on
            audio.play("box_on" if self.box_on else "box_off")
        if inp.pressed("punch") and not self.box_on:
            r = self.player_rect().inflate(10, 10)
            if self.rect_hits(r):
                audio.play("knock")
                self.ripples.append([self.px, self.py - 6, 0])
                self._noise(KNOCK_HEAR)

    def _camera(self, c):
        c["t"] += 1
        c["angle"] = c["base"] + math.sin(c["t"] * math.tau / c["period"]) * c["sweep"]
        if c["flash"]:
            c["flash"] -= 1
        if self.visibility() == "full" and self.in_view(c["x"], c["y"], c["angle"], CAM_HALF, CAM_RANGE):
            c["flash"] = 40
            if self.phase != "alert":
                self.message("SPOTTED BY A CAMERA", 90)
            self.spotted()

    def _laser(self, lz):
        lz["t"] = (lz["t"] + 1) % (lz["on"] + lz["off"])
        if lz["t"] < lz["on"] and not self.ignore_player:
            if self.player_rect().colliderect(pygame.Rect(lz["x"] - 1, lz["y0"], 2, lz["y1"] - lz["y0"])):
                if self.phase != "alert":
                    self.message("INFRARED SENSOR TRIPPED", 90)
                self.spotted()

    def _guard(self, g, vis):
        g.anim += 1
        if g.exclaim:
            g.exclaim -= 1
        if g.huh:
            g.huh -= 1
        sees = vis != "hidden" and self.guard_sees(g)
        d = math.hypot(self.px - g.x, self.py - g.y)
        # ---- noticing ----
        if sees:
            if g.state in ("alert", "search"):
                self.spotted(g)
            elif vis == "box":
                if d < BOX_SPOT:
                    self.message("IT'S AKUMA IN A BOX!", 100)
                    self.spotted(g)
                else:
                    self._suspect(g, self.px, self.py)
            else:
                reach = VIEW_RANGE * (SHADOW_K if self.in_shadow(self.px, self.py) else 1)
                g.notice += 2 if d < reach * 0.8 else 1
                if d < reach * NEAR_K or g.notice >= NOTICE_T or self.phase in ("evasion", "caution") \
                        and g.notice > NOTICE_T // 2:
                    self.spotted(g)
                else:
                    self._suspect(g, self.px, self.py)
        elif g.notice:
            g.notice -= 0.25 if g.state == "suspicious" else 1
            g.notice = max(0, g.notice)
        # ---- acting ----
        if g.state == "patrol":
            self._patrol(g)
        elif g.state == "suspicious":
            self._investigate(g)
        elif g.state == "alert":
            if sees:
                tx, ty = self.px, self.py
            else:
                tx, ty = self.lkp
            if self._step_toward(g, tx, ty, G_RUN) and not sees:
                g.state = "search"            # lost him at the last known spot: look around
                g.search_to = None
        elif g.state == "search":
            self._search(g)

    def _patrol(self, g):
        x, y, wait = g.route[g.ri]
        if g.wait > 0:
            g.wait -= 1
            g.moving = False
            g.look_t += 1
            # stopped: turn the head left and right
            self._turn(g, g.look_base + math.sin(g.look_t / 34) * 1.1, 0.05)
            if g.wait == 0:
                g.ri = (g.ri + 1) % len(g.route)
            return
        speed = G_CAUTION if self.phase == "caution" else G_WALK
        if self._step_toward(g, x, y, speed):
            g.wait = wait if len(g.route) > 1 else 10 ** 9
            g.look_base = g.angle
            g.look_t = 0

    def _investigate(self, g):
        g.t += 1
        sx, sy = g.stim
        if g.sub == "look":
            g.moving = False
            self._turn(g, math.atan2(sy - g.y, sx - g.x), 0.12)
            if g.t >= 36:
                g.sub, g.t = "go", 0
        elif g.sub == "go":
            d = math.hypot(sx - g.x, sy - g.y)
            if d < 18:
                g.sub, g.t = "search", 0
                g.moving = False
                g.look_base = math.atan2(sy - g.y, sx - g.x) if d > 1 else g.angle
            else:
                # stop beside the spot, not on it (a box gets looked at, not walked into)
                ang = math.atan2(g.y - sy, g.x - sx)
                self._step_toward(g, sx + math.cos(ang) * 16, sy + math.sin(ang) * 16, G_WALK + 0.2)
                if g.t > 60 * 12:
                    g.sub, g.t = "search", 0
        else:
            g.moving = False
            self._turn(g, g.look_base + math.sin(g.t / 26) * 1.0, 0.07)
            if g.t >= 150:
                self._back_to_patrol(g)

    def _search(self, g):
        if g.search_to is None:
            lx, ly = int(self.lkp[0] // T), int(self.lkp[1] // T)
            f = self._field((lx, ly))
            near = [c for c, v in f.items() if v <= 7]
            c = self.rng.choice(near) if near else (lx, ly)
            g.search_to = ((c[0] + 0.5) * T, (c[1] + 0.5) * T)
            g.t = 0
        if g.t:
            g.t -= 1
            g.moving = False
            self._turn(g, g.look_base + math.sin(g.t / 20) * 1.2, 0.09)
            if g.t == 0:
                g.search_to = None
            return
        if self._step_toward(g, *g.search_to, G_SEARCH):
            g.t = 70
            g.look_base = g.angle

    def _touch(self):
        if self.invuln or self.ignore_player:
            return
        pr = self.player_rect()
        for g in self.guards:
            if not g.alive or not pr.colliderect(g.rect()):
                continue
            aware = g.state in ("alert", "search") or self.phase in ("alert", "evasion")
            if self.box_on and not aware:
                self.message("IT'S AKUMA IN A BOX!", 100)
                self.spotted(g)
                aware = True
            g.allies = []
            if aware:
                if self.phase != "alert":
                    self.spotted(g)
                near = sorted((o for o in self.guards if o is not g and o.alive and o.state == "alert"),
                              key=lambda o: math.hypot(o.x - self.px, o.y - self.py))
                g.allies = [o for o in near if math.hypot(o.x - self.px, o.y - self.py) < 110][:2]
                for o in g.allies:
                    o.allies = []
            self.encounter = (g, not aware)
            self.encounter_t = 0
            audio.play("encounter")
            return

    def after_fight(self, result, hp, enemy):
        self.hp = hp
        self.invuln = INVULN
        if result == "win":
            down = [enemy] + list(getattr(enemy, "allies", []) or [])
            for g in down:
                g.alive = False
                g.allies = []
            self.message("%d GENOME SOLDIER%s DOWN" % (len(down), "S" if len(down) > 1 else ""), 110)
            if self.phase == "alert":
                self.phase = "evasion"
                self.timer = EVASION_T
                for g in self.guards:
                    if g.alive:
                        g.state = "search"
                        g.search_to = None
        elif result == "escape":
            if self.phase == "alert":
                self.phase, self.timer = "evasion", EVASION_T

    # ---- drawing -----------------------------------------------------------
    def camera(self):
        cx = int(self.px - W / 2)
        cy = int(self.py - H / 2)
        return max(0, min(self.mw - W, cx)), max(0, min(self.mh - H, cy))

    def draw(self, surf):
        if self.stage in ("ring", "codec"):
            self._draw_codec(surf)
            return
        cx, cy = self.camera()
        surf.blit(self.map_surf, (0, 0), (cx, cy, W, H))
        view = pygame.Rect(cx - 100, cy - 100, W + 200, H + 200)
        for fx, fy, life in self.footprints:
            surf.fill((150, 162, 190), (round(fx) - cx, round(fy) - cy, 2, 1))
        # vision cones on the floor
        cones = pygame.Surface((W, H), pygame.SRCALPHA)
        for g in self.guards:
            if g.alive and view.collidepoint(g.x, g.y):
                col = (255, 40, 30, 96) if g.state in ("alert",) else \
                    (255, 190, 30, 96) if g.state in ("suspicious", "search") else (40, 120, 255, 84)
                reach = VIEW_RANGE * (CAUTION_K if self.phase == "caution" else 1)
                pygame.draw.polygon(cones, col, self._cone(g.x, g.y - 4, g.angle, VIEW_HALF, reach, cx, cy))
        for c in self.cameras:
            if view.collidepoint(c["x"], c["y"]):
                col = (255, 40, 30, 100) if c["flash"] else (255, 200, 40, 80)
                pygame.draw.polygon(cones, col, self._cone(c["x"], c["y"], c["angle"], CAM_HALF, CAM_RANGE, cx, cy))
        surf.blit(cones, (0, 0))
        # lasers
        for lz in self.lasers:
            if lz["t"] < lz["on"]:
                x = round(lz["x"]) - cx
                col = (255, 40, 40) if (self.anim // 2) % 3 else (255, 160, 160)
                pygame.draw.line(surf, col, (x, lz["y0"] - cy), (x, lz["y1"] - cy))
            for yy in (lz["y0"] - 3, lz["y1"]):
                surf.fill((60, 60, 70), (round(lz["x"]) - 2 - cx, yy - cy, 4, 3))
        # the box waiting in storage
        if self.box_pickup:
            bx, by = self.box_pickup
            img = self.box_img[3]
            surf.blit(img, (round(bx) - 8 - cx, round(by) - 6 - cy))
            if (self.anim // 12) % 3 == 0:
                surf.fill((255, 255, 255), (round(bx) + 5 - cx, round(by) - 7 - cy, 1, 1))
        # y-sorted actors
        actors = [(self.py, None)] + [(g.y, g) for g in self.guards if g.alive and view.collidepoint(g.x, g.y)]
        actors.sort(key=lambda a: a[0])
        for _, g in actors:
            if g is None:
                self._draw_akuma(surf, cx, cy)
            else:
                img, (ax, ay) = g.map_art.frame(g.face, g.moving, g.walked, g.anim)
                pygame.draw.ellipse(surf, (40, 46, 70), (round(g.x) - 7 - cx, round(g.y) - cy - 1, 14, 4))
                surf.blit(img, (round(g.x) - ax - cx, round(g.y) - ay + 2 - cy))
                # gun barrel pointing where he looks
                hx, hy = round(g.x) - cx, round(g.y) - 12 - cy
                pygame.draw.line(surf, (30, 30, 34), (hx, hy), (hx + round(math.cos(g.angle) * 8),
                                                               hy + round(math.sin(g.angle) * 8)), 2)
        # shadows darken whoever stands in them
        surf.blit(self.dark, (0, 0), (cx, cy, W, H))
        for c in self.cameras:
            x, y = round(c["x"]) - cx, round(c["y"]) - cy
            if -10 < x < W + 10 and -10 < y < H + 10:
                pygame.draw.rect(surf, (40, 40, 48), (x - 4, y - 4, 8, 6))
                pygame.draw.line(surf, (80, 80, 92), (x, y), (x + round(math.cos(c["angle"]) * 6),
                                                              y + round(math.sin(c["angle"]) * 6)), 3)
                surf.fill((255, 40, 40) if c["flash"] or (self.anim // 20) % 2 else (90, 20, 20), (x - 1, y - 3, 2, 2))
        # marks over heads (drawn above the shadow so they always read)
        for g in self.guards:
            if not g.alive:
                continue
            x, y = round(g.x) - cx, round(g.y) - 36 - cy
            if g.exclaim:
                k = 3 if g.exclaim > 50 else 2
                draw_text(surf, "!", x, y - 6 * (k - 2), (255, 50, 30), scale=k, shadow=(255, 255, 255), align="center")
            elif g.huh:
                draw_text(surf, "?", x, y, (255, 230, 70), scale=2, align="center")
            elif g.state == "suspicious" and g.sub == "search" and (self.anim // 20) % 2:
                draw_text(surf, "...", x, y + 6, (230, 230, 240), align="center")
        for x, y, t in self.ripples:
            pygame.draw.circle(surf, (230, 240, 255), (round(x) - cx, round(y) - cy), 6 + t * 2, 1)
        # snow over the yard
        for fx, fy, sp in self.flakes:
            if (fy + cy) // T >= 13:
                surf.fill((240, 246, 255), (round(fx), round(fy), 1 if sp < 0.4 else 2, 1))
        self._hud(surf)
        if self.freeze:
            self._freeze_fx(surf)
        if self.stage == "card":
            self._card(surf)
        if self.stage == "won":
            s = pygame.Surface((W, 40), pygame.SRCALPHA)
            s.fill((0, 0, 0, 170))
            surf.blit(s, (0, 62))
            draw_text(surf, "ELEVATOR REACHED", W // 2, 68, (140, 255, 170), scale=2, align="center")
            draw_text(surf, "AKUMA SLIPS OUT OF THE COMPOUND", W // 2, 88, (220, 230, 220), align="center")
        if self.menu.open:
            self.menu.draw(surf)
        if self.encounter:
            self._encounter_fx(surf)

    def _draw_akuma(self, surf, cx, cy):
        if self.invuln and (self.invuln // 4) % 2:
            return
        x, y = round(self.px) - cx, round(self.py) - cy
        if self.box_on:
            k = 0 if not self.moving else 1 + int(self.walked / 4) % 2
            img = self.box_img[k]
            pygame.draw.ellipse(surf, (40, 46, 70), (x - 9, y - 1, 18, 5))
            surf.blit(img, (x - 10, y - 15))
            return
        img, (ax, ay) = self.art.frame(self.pface, self.moving, self.walked, self.anim)
        pygame.draw.ellipse(surf, (40, 46, 70), (x - 7, y - 1, 14, 4))
        surf.blit(img, (x - ax, y - ay + 2))

    def _freeze_fx(self, surf):
        t = FREEZE - self.freeze
        if t < 3:
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            s.fill((255, 255, 255, 120))
            surf.blit(s, (0, 0))
        for k in range(10):
            a = k * math.tau / 10 + t * 0.02
            r0, r1 = 150 - t * 2, 190
            pygame.draw.line(surf, (255, 80, 60), (W // 2 + math.cos(a) * r0, H // 2 + math.sin(a) * r0),
                             (W // 2 + math.cos(a) * r1, H // 2 + math.sin(a) * r1), 2)

    def _hud(self, surf):
        # LIFE
        mx = self.game.akuma_max
        draw_text(surf, "LIFE", 6, 4, (200, 230, 255))
        pygame.draw.rect(surf, (10, 14, 24), (5, 12, 84, 7))
        pygame.draw.rect(surf, (40, 50, 60), (6, 13, 82, 5))
        frac = max(0, self.hp) / mx
        col = (100, 220, 140) if frac > 0.3 else (255, 90, 60)
        pygame.draw.rect(surf, col, (6, 13, int(82 * frac), 5))
        pygame.draw.rect(surf, (230, 255, 230), (6, 13, int(82 * frac), 1))
        if self.sneaking and self.stage == "play":
            draw_text(surf, "SNEAKING", 6, 22, (160, 190, 230))
        self._radar(surf)
        # item box
        bx, by = W - 38, H - 30
        pygame.draw.rect(surf, (10, 14, 24), (bx, by, 34, 26))
        pygame.draw.rect(surf, (120, 140, 170), (bx, by, 34, 26), 1)
        if self.has_box:
            surf.blit(self.box_img[3], (bx + 9, by + 3))
            col = (255, 230, 120) if self.box_on and (self.anim // 20) % 2 else (200, 210, 230)
            draw_text(surf, "BOX", bx + 17, by + 17, col, align="center")
        else:
            draw_text(surf, "NO", bx + 17, by + 6, (90, 100, 120), align="center")
            draw_text(surf, "ITEM", bx + 17, by + 15, (90, 100, 120), align="center")
        if self.messages:
            draw_text(surf, self.messages[0][0], W // 2, H - 12, (255, 240, 200), align="center")

    def _radar(self, surf):
        rw, rh = 64, 44
        ox, oy = W - rw - 4, 4
        pygame.draw.rect(surf, (6, 10, 8), (ox - 1, oy - 1, rw + 2, rh + 2))
        jammed = self.phase in ("alert", "evasion")
        box = pygame.Rect(ox, oy, rw, rh)
        if jammed:
            surf.fill((10, 30, 16), box)
            for _ in range(140):
                surf.fill(self.rng.choice(((40, 120, 66), (120, 200, 140), (6, 20, 10))),
                          (ox + self.rng.randrange(rw), oy + self.rng.randrange(rh), 2, 1))
            draw_text(surf, "JAMMING", ox + rw // 2, oy + rh // 2 - 3, (180, 255, 190), align="center")
        else:
            sx = round(self.px / 4) - rw // 2
            sy = round(self.py / 4) - rh // 2
            surf.blit(self.radar_map, (ox, oy), (sx, sy, rw, rh))
            clip = surf.get_clip()
            surf.set_clip(box)
            for g in self.guards:
                if not g.alive:
                    continue
                gx, gy = ox + g.x / 4 - sx, oy + g.y / 4 - sy
                r = VIEW_RANGE / 4
                pts = [(gx, gy), (gx + math.cos(g.angle - VIEW_HALF) * r, gy + math.sin(g.angle - VIEW_HALF) * r),
                       (gx + math.cos(g.angle + VIEW_HALF) * r, gy + math.sin(g.angle + VIEW_HALF) * r)]
                pygame.draw.polygon(surf, (60, 150, 90) if g.state == "patrol" else (170, 160, 60), pts, 1)
                surf.fill((255, 60, 60), (round(gx) - 1, round(gy) - 1, 3, 3))
            for c in self.cameras:
                surf.fill((255, 230, 90), (round(ox + c["x"] / 4 - sx) - 1, round(oy + c["y"] / 4 - sy) - 1, 2, 2))
            if (self.anim // 10) % 3:
                surf.fill((255, 255, 255), (ox + rw // 2 - 1, oy + rh // 2 - 1, 3, 3))
            surf.set_clip(clip)
        pygame.draw.rect(surf, (120, 200, 140), (ox - 1, oy - 1, rw + 2, rh + 2), 1)
        # phase + countdown under the radar
        if self.phase != "normal":
            col = {"alert": (255, 60, 40), "evasion": (255, 200, 60), "caution": (255, 160, 60)}[self.phase]
            secs = self.timer / 60
            draw_text(surf, self.phase.upper(), ox + rw // 2, oy + rh + 4, col, align="center")
            draw_text(surf, "%05.2f" % min(99.99, secs), ox + rw // 2, oy + rh + 13, col, scale=1, align="center")
            if self.phase == "alert":
                pygame.draw.rect(surf, col, (ox - 1, oy - 1, rw + 2, rh + 2), 1)

    def _card(self, surf):
        s = pygame.Surface((W, 56), pygame.SRCALPHA)
        s.fill((0, 0, 0, 180))
        surf.blit(s, (0, 52))
        draw_text(surf, "LEVEL %d" % self.level, W // 2, 58, (255, 220, 80), scale=2, align="center")
        draw_text(surf, "THE FROZEN COMPOUND", W // 2, 78, (230, 240, 255), align="center")
        draw_text(surf, "SNEAK TO THE ELEVATOR. DON'T GET SEEN.", W // 2, 92, (180, 200, 230), align="center")

    def _draw_codec(self, surf):
        surf.fill((4, 12, 8))
        for y in range(0, H, 3):
            surf.fill((8, 20, 12), (0, y, W, 1))
        if self.stage == "ring":
            if (self.t // 8) % 2 == 0:
                draw_text(surf, "CALL", W // 2, 60, (150, 255, 170), scale=3, align="center")
            draw_text(surf, "PUSH ANY BUTTON", W // 2, 96, (90, 180, 110), align="center")
            draw_text(surf, FREQ, W // 2, 110, (150, 255, 170), scale=2, align="center")
            return
        who, text = CODEC[self.line]
        lx, rx, py = 30, W - 90, 20
        for img, x, talking in ((self.akuma_img, lx, who == "AKUMA"), (self.caller_img, rx, who != "AKUMA")):
            surf.blit(img, (x, py))
            if not talking:
                dim = pygame.Surface((60, 60), pygame.SRCALPHA)
                dim.fill((0, 0, 0, 110))
                surf.blit(dim, (x, py))
            pygame.draw.rect(surf, (120, 220, 140), (x - 2, py - 2, 64, 64), 1)
        draw_text(surf, "AKUMA", lx + 30, py + 66, (150, 255, 170), align="center")
        draw_text(surf, "CHUN-LI", rx + 30, py + 66, (150, 255, 170), align="center")
        # frequency readout and signal bars
        draw_text(surf, "PTT", W // 2, py + 2, (90, 180, 110), align="center")
        draw_text(surf, FREQ, W // 2, py + 14, (150, 255, 170), scale=2, align="center")
        for k in range(8):
            h = 3 + k * 2
            on = k < 3 + (self.anim // 4 + k) % 6 if who != "AKUMA" else k < 2
            surf.fill((120, 240, 150) if on else (20, 50, 30), (W // 2 - 24 + k * 6, py + 50 - h, 4, h))
        pygame.draw.rect(surf, (60, 140, 80), (8, 112, W - 16, 62), 1)
        shown = text[:self.chars]
        draw_text(surf, who + ":", 14, 117, (255, 255, 255))
        for i, line in enumerate(wrap(shown, 48)):
            draw_text(surf, line, 14, 129 + i * 10, (190, 255, 200))
        if self.chars >= len(text) and (self.anim // 20) % 2:
            draw_text(surf, ">", W - 18, 162, (150, 255, 170))

    def _encounter_fx(self, surf):
        t = self.encounter_t
        if t < 4 and t % 2 == 0:
            surf.fill((255, 255, 255))
            return
        n = 12
        bh = H // n + 1
        prog = max(0, (t - 3) / 10)
        for i in range(n):
            w = int(W * min(1, prog * 1.6 - (i % 3) * 0.15))
            if w > 0:
                pygame.draw.rect(surf, (6, 10, 20), (W - w if i % 2 else 0, i * bh, w, bh))
