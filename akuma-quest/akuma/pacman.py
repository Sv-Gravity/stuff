"""Level 5: the fighter maze, Pac-Man style. No side-view fights here.

Akuma eats his way round a maze while four fighters from the sprite pack hunt
him. Each run picks four of them at random from ROSTER and gives each one of
the classic chase habits (chaser, ambusher, flanker, shy one); they switch
between scatter and chase. A power pellet wakes Akuma's killing intent for a
few seconds: the chasers panic, and touching one KOs them back to the pen,
where they tag out and a fresh fighter from the bench comes out instead.
Getting caught costs a quarter of Akuma's health. Eat every pellet to clear
the level.
"""

import math
import random

import pygame

from . import audio
from . import fight as F
from .akuma_sprites import MapArt, AkumaArt, CharArt, MAP_SCALE, _half
from .art import shade, OUTLINE
from .config import W, H, FPS
from .font import draw_text
from .pause import PauseMenu

MAZE = [
    "###############################",
    "#o.........#.......#.........o#",
    "#.###.####.#.#####.#.####.###.#",
    "#.............................#",
    "#.###.#.#####.###.#####.#.###.#",
    "#.....#.......   .......#.....#",
    "####.#####.####-####.#####.####",
    "    .#####.#GGGGGGG#.#####.    ",
    "####.#####.#GGGGGGG#.#####.####",
    "####.#####.#########.#####.####",
    "#.............................#",
    "#.####.#.###.#####.###.#.####.#",
    "#o.....#.....#...#.....#.....o#",
    "#.###.####.#.#.#.#.#.####.###.#",
    "#.............................#",
    "###############################",
]
T = 10                              # tile size, px
COLS, ROWS = len(MAZE[0]), len(MAZE)
MW, MH = COLS * T, ROWS * T         # 310 x 160
OX, OY = (W - MW) // 2, H - MH - 2  # maze origin on screen
HUD_H = OY

LEVEL_NAME = "THE FIGHTER MAZE"
START = (15, 14)                    # Akuma
EXIT = (15, 5)                      # the tile above the pen door
PEN_Y = 8 * T                       # pen middle, px
PEN_X = (13, 15, 17)                # pen columns of the three chasers that start inside
TUNNEL = {(x, 7) for x in (0, 1, 2, 3, 27, 28, 29, 30)}

SPEED = 1.0                         # px / frame
POWER_SPEED = 1.1
CHUN_SPEED = 0.92
SCARED_SPEED = 0.55
TUNNEL_SPEED = 0.5
EYES_SPEED = 2.0
PEN_SPEED = 0.6
FRIGHT = 6 * FPS
BLINK = 2 * FPS
RELEASE = (0, 60, 240, 420)         # frames after a (re)start before each chaser leaves the pen
MODES = ((7, "scatter"), (20, "chase"), (7, "scatter"), (20, "chase"), (5, "scatter"), (0, "chase"))
PELLET_PTS, POWER_PTS = 10, 50
KO_PTS = (200, 400, 800, 1600)
CATCH_FREEZE = 70
KO_FREEZE = 30
INTRO, REINTRO = 130, 70
AKUMA_SCALE = 0.34

DIRS = {"up": (0, -1), "left": (-1, 0), "down": (0, 1), "right": (1, 0)}   # tie order up, left, down
REVERSE = {"up": "down", "down": "up", "left": "right", "right": "left"}

CONTROLS = [
    "ARROWS / WASD: MOVE",
    "PRESS A TURN EARLY: AKUMA TAKES IT AT THE NEXT GAP",
    "EAT EVERY PELLET TO CLEAR THE LEVEL",
    "POWER PELLETS: AKUMA POWERS UP FOR A FEW SECONDS",
    "  THE CHASERS FLEE. TOUCH ONE TO KO THEM",
    "  KO MORE IN A ROW FOR BIGGER BONUSES",
    "  A KO'D FIGHTER TAGS OUT FOR A FRESH ONE",
    "CAUGHT BY A CHASER: -1/4 HEALTH",
    "THE SIDE TUNNELS WRAP AROUND",
]

# the four chase habits (Blinky, Pinky, Inky, Clyde): name and scatter corner
GHOSTS = [
    dict(name="CHASER", corner=(28, -2)),
    dict(name="AMBUSHER", corner=(2, -2)),
    dict(name="FLANKER", corner=(30, 17)),
    dict(name="SHY ONE", corner=(0, 17)),
]
CHUNS = GHOSTS                      # old name

# fighters from the sprite pack (assets/chars/<cid>/) who can chase Akuma
ROSTER = {
    "chunli": "CHUN-LI", "zangief": "ZANGIEF", "morrigan": "MORRIGAN", "felicia": "FELICIA",
    "ryu": "RYU", "ken": "KEN", "sakura": "SAKURA", "hsienko": "HSIEN-KO", "drdoom": "DR. DOOM",
}
CHASER_H, CHASER_W = 22, 26         # map sprite box (px) every fighter is scaled to fit

SCARED = (40, 46, 200)


def step(tile, d):
    dx, dy = DIRS[d]
    return ((tile[0] + dx) % COLS, tile[1] + dy)


def open_tile(tile):
    """Floor Akuma and the chasers can walk on (not walls, the pen or its door)."""
    x, y = tile
    return 0 <= y < ROWS and MAZE[y][x % COLS] in ". o"


def neighbors(tile):
    """(direction, tile) pairs reachable from tile in one step; tests use this for bots."""
    return [(d, step(tile, d)) for d in DIRS if open_tile(step(tile, d))]


def center(c):
    return c * T + T // 2


def _home_dist():
    """Steps from every floor tile to the pen exit, so KO'd chasers always find home."""
    dist = {EXIT: 0}
    q = [EXIT]
    for t in q:
        for _, n in neighbors(t):
            if n not in dist:
                dist[n] = dist[t] + 1
                q.append(n)
    return dist


HOME = _home_dist()


# --------------------------------------------------------------------------
# art
# --------------------------------------------------------------------------
def _maze_surface(edge, fill, door):
    wall = [[MAZE[y][x] == "#" for x in range(COLS)] for y in range(ROWS)]

    def solid(x, y):
        return 0 <= x < COLS and 0 <= y < ROWS and wall[y][x]

    s = pygame.Surface((MW, MH), pygame.SRCALPHA)
    k = 3
    for y in range(ROWS):
        for x in range(COLS):
            if not wall[y][x]:
                continue
            l = 0 if solid(x - 1, y) or x == 0 else k
            r = 0 if solid(x + 1, y) or x == COLS - 1 else k
            u = 0 if solid(x, y - 1) or y == 0 else k
            d = 0 if solid(x, y + 1) or y == ROWS - 1 else k
            s.fill(fill, (x * T + l, y * T + u, T - l - r, T - u - d))
    m = pygame.mask.from_surface(s)

    def on(px, py):
        return 0 <= px < MW and 0 <= py < MH and m.get_at((px, py))

    # cut convex corners, then outline in neon
    for py in range(MH):
        for px in range(MW):
            if on(px, py) and sum(not on(px + dx, py + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) >= 2:
                if (not on(px - 1, py) or not on(px + 1, py)) and (not on(px, py - 1) or not on(px, py + 1)):
                    s.set_at((px, py), (0, 0, 0, 0))
    m = pygame.mask.from_surface(s)
    inner = shade(edge, 0.55)
    for py in range(MH):
        for px in range(MW):
            if not on(px, py):
                continue
            n4 = [on(px + dx, py + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            if not all(n4):
                s.set_at((px, py), edge)
            elif not all(on(px + dx, py + dy) for dx in (-2, 0, 2) for dy in (-2, 0, 2)):
                s.set_at((px, py), inner)
    dx = center(15)
    s.fill(door, (dx - 4, 6 * T + 4, 9, 2))
    return s


def _scared(img, d, blink):
    """A panicking chaser: their drawing in Pac-Man fright blue (white when blinking),
    keeping its shading so they still read as themselves."""
    body = SCARED if not blink else (236, 236, 246)
    out = img.copy()
    for y in range(out.get_height()):
        for x in range(out.get_width()):
            c = out.get_at((x, y))
            if c.a:
                k = 0.35 + 0.9 * (c.r * 0.3 + c.g * 0.55 + c.b * 0.15) / 255
                out.set_at((x, y), shade(body, k) + (255,))
    return out


def _aura_ring(img):
    m = pygame.mask.from_surface(img)
    sil = m.to_surface(setcolor=(255, 40, 30, 255), unsetcolor=(0, 0, 0, 0))
    w, h = img.get_size()
    out = pygame.Surface((w + 4, h + 4), pygame.SRCALPHA)
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            if abs(dx) + abs(dy) in (2, 3):
                out.blit(sil, (2 + dx, 2 + dy))
    hot = m.to_surface(setcolor=(255, 190, 80, 255), unsetcolor=(0, 0, 0, 0))
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        out.blit(hot, (2 + dx, 2 + dy))
    return out


_ART = None


def _art():
    global _ART
    if _ART is None:
        a = {}
        a["maze"] = _maze_surface((236, 70, 60), (54, 14, 30), (255, 170, 200))
        a["maze_flash"] = _maze_surface((255, 255, 255), (60, 50, 90), (255, 170, 200))
        a["akuma"] = MapArt(scale=AKUMA_SCALE)
        a["akuma_ko"] = _half(*AkumaArt().entry("down"), AKUMA_SCALE)
        _ART = a
    return _ART


def chaser_scale(cid):
    """Map scale that fits a fighter's idle drawing in the CHASER_H x CHASER_W box
    (Chun-Li comes out at the old 0.34; big Zangief gets shrunk to fit the lanes)."""
    art = CharArt(cid)
    img = art.base[art.resolve("idle")][0]
    w, h = img.get_size()
    return min(CHASER_H / h, CHASER_W / w)


def chaser_art(cid):
    """MapArt for one chaser, scaled to fit the 10px-tile maze (loaded on first use)."""
    a = _art()
    key = ("chaser", cid)
    if key not in a:
        k = chaser_scale(cid)
        a[key] = MapArt(cid, scale=k)
        a[key].scale = k
    return a[key]


# --------------------------------------------------------------------------
# actors
# --------------------------------------------------------------------------
class Mover:
    """Tile-to-tile movement: on `tile`, `p` px along `d` towards the next one."""

    def __init__(self, tile, d):
        self.tile, self.d, self.p = tile, d, 0.0

    @property
    def pos(self):
        dx, dy = DIRS[self.d] if self.d else (0, 0)
        return center(self.tile[0]) + dx * self.p, center(self.tile[1]) + dy * self.p

    def ahead(self):
        return step(self.tile, self.d) if self.d and self.p > 0 else self.tile

    def turn_back(self):
        if self.d and self.p > 0:
            self.tile, self.p = step(self.tile, self.d), T - self.p
        if self.d:
            self.d = REVERSE[self.d]


class Akuma(Mover):
    def __init__(self):
        super().__init__(START, None)
        self.face = -1
        self.moving = False
        self.walked = 0.0


class Chun(Mover):
    """One chaser: ghost habit i (GHOSTS[i]) played by fighter cid."""

    def __init__(self, i, cid="chunli"):
        self.i = i
        self.cfg = GHOSTS[i]
        self.cid = cid
        self.reset()

    @property
    def name(self):
        return ROSTER.get(self.cid, self.cid.upper())

    def reset(self):
        self.bob = 1
        if self.i == 0:
            super().__init__(EXIT, "left")
            self.state = "out"
        else:
            super().__init__(EXIT, None)
            self.state = "pen"
            self.x, self.y = float(center(PEN_X[self.i - 1])), float(PEN_Y)
            self.bob = -1 if self.i % 2 else 1
        self.home_x = center(PEN_X[self.i - 1]) if self.i else center(15)
        self.release = RELEASE[self.i]
        self.scared = False
        self.walked = 0.0

    @property
    def pos(self):
        if self.state in ("pen", "leave", "enter"):
            return self.x, self.y
        return Mover.pos.fget(self)

    @property
    def facing(self):
        if self.state in ("pen", "leave", "enter"):
            return "up" if self.bob < 0 else "down"
        return self.d or "left"


# --------------------------------------------------------------------------
# the level
# --------------------------------------------------------------------------
class PacmanScene:
    def __init__(self, game, seed, level=5, hp=None):
        F.init_shared()
        self.game = game
        self.level = level
        self.rng = random.Random(seed)
        self.art = _art()
        self.menu = PauseMenu(game, CONTROLS)
        self.max_hp = game.akuma_max
        self.hp = self.max_hp if hp is None else hp
        self.hp_lag = self.hp
        self.dmg = max(1, round(self.max_hp / 4))
        self.pellets = {(x, y) for y in range(ROWS) for x in range(COLS) if MAZE[y][x] in ".o"}
        self.power = {(x, y) for x, y in self.pellets if MAZE[y][x] == "o"}
        self.total = len(self.pellets)
        self.score = 0
        self.effects = []
        self.popups = []           # [text, x, y, frames]
        self.phase = "intro"
        self.t = 0
        self.end_t = 0
        self.freeze = 0
        self.flash = 0
        self.shake = 0
        self.catches = 0
        self.result = None
        # this run's four chasers, one per habit; the rest wait on the bench
        # (its own rng, so who is cast never changes how they move)
        self.cast_rng = random.Random("cast %s" % seed)
        pool = list(ROSTER)
        self.cast_rng.shuffle(pool)
        self.roster, self.bench = pool[:4], pool[4:]
        self.tagged = 0
        self._reset_actors()

    def _reset_actors(self):
        self.akuma = Akuma()
        self.want = None
        self.chuns = [Chun(i, self.roster[i]) for i in range(4)]
        self.fright = 0
        self.combo = 0
        self.mode_i, self.mode_t = 0, 0
        self.play_t = 0

    @property
    def paused(self):
        return self.menu.open

    @property
    def mode(self):
        return MODES[self.mode_i][1]

    def passable(self, tile):
        return open_tile(tile)

    def neighbors(self, tile):
        return neighbors(tile)

    # ---- update ----------------------------------------------------------
    def update(self, inp):
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.phase in ("play", "ready") and self.menu.toggle(inp):
            return
        self.t += 1
        self.hp_lag = max(self.hp, self.hp_lag - 0.6) if self.hp_lag > self.hp else self.hp
        for v in ("shake", "flash"):
            if getattr(self, v):
                setattr(self, v, getattr(self, v) - 1)
        for fx in self.effects:
            fx.update()
        self.effects = [fx for fx in self.effects if fx.alive]
        for pu in self.popups:
            pu[3] -= 1
        self.popups = [pu for pu in self.popups if pu[3] > 0]
        self._read_input(inp)
        if self.phase in ("intro", "ready"):
            self.end_t += 1
            n = INTRO if self.phase == "intro" else REINTRO
            if self.end_t == n - 30:
                audio.play("fight")
            if self.end_t >= n:
                self.phase, self.end_t = "play", 0
                self._eat()
            return
        if self.phase == "caught":
            self.end_t += 1
            if self.end_t >= CATCH_FREEZE:
                if self.hp <= 0:
                    self.phase, self.end_t = "lost", 0
                    audio.play("ko")
                else:
                    self._reset_actors()
                    self.phase, self.end_t = "ready", 0
            return
        if self.phase in ("won", "lost"):
            self.end_t += 1
            skip = self.end_t > 40 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= 150 or skip:
                if self.phase == "won":
                    self.result = "win"
                    self.game.level_done(self, max(1, self.hp))
                else:
                    self.result = "lose"
                    self.game.level_failed(self)
            return
        if self.freeze:                       # the short pause after a KO
            self.freeze -= 1
            for c in self.chuns:
                if c.state == "eyes":
                    self._move_chun(c)
            return
        self.play_t += 1
        if self.fright:
            self.fright -= 1
            if not self.fright:
                for c in self.chuns:
                    c.scared = False
        else:
            self._modes()
        self._move_akuma()
        if self._collide():
            return
        for c in self.chuns:
            self._move_chun(c)
        if self._collide():
            return
        if not self.pellets:
            self.phase, self.end_t = "won", 0
            audio.play("encounter")

    def _read_input(self, inp):
        for d in DIRS:
            if inp.pressed(d):
                self.want = d
        if self.want is None or not inp.held(self.want):
            held = [d for d in DIRS if inp.held(d)]
            if len(held) == 1:
                self.want = held[0]

    def _modes(self):
        secs = MODES[self.mode_i][0]
        if not secs:
            return
        self.mode_t += 1
        if self.mode_t >= secs * FPS:
            self.mode_i, self.mode_t = self.mode_i + 1, 0
            for c in self.chuns:
                if c.state == "out":
                    c.turn_back()

    # ---- Akuma -----------------------------------------------------------
    def _move_akuma(self):
        a = self.akuma
        want = self.want
        if want and a.d and a.p > 0:
            if want == REVERSE[a.d]:
                a.turn_back()
            elif want != a.d and a.p <= 2 and open_tile(step(a.tile, want)):
                a.p, a.d = 0.0, want              # cornering: a late press still takes the turn
        dist = POWER_SPEED if self.fright else SPEED
        moved = 0.0
        while dist > 1e-6:
            if a.p == 0:
                if want and open_tile(step(a.tile, want)):
                    a.d = want
                elif not (a.d and open_tile(step(a.tile, a.d))):
                    break
            s = min(dist, T - a.p)
            a.p += s
            dist -= s
            moved += s
            if a.p >= T - 1e-6:
                a.tile, a.p = step(a.tile, a.d), 0.0
                self._eat()
        a.moving = moved > 0
        a.walked += moved
        if a.d in ("left", "right"):
            a.face = -1 if a.d == "left" else 1

    def _eat(self):
        tile = self.akuma.tile
        if tile not in self.pellets:
            return
        self.pellets.discard(tile)
        if tile in self.power:
            self.score += POWER_PTS
            self.power_up()
        else:
            self.score += PELLET_PTS
            if len(self.pellets) % 2 == 0:
                audio.play("step", 0.7)

    def power_up(self):
        """Akuma's killing intent: every chaser panics for FRIGHT frames."""
        self.fright = FRIGHT
        self.combo = 0
        audio.play("shoryu")
        for c in self.chuns:
            if c.state != "eyes" and c.state != "enter":
                if c.state == "out" and not c.scared:
                    c.turn_back()
                c.scared = True

    # ---- the chasers -----------------------------------------------------------
    def _tag_out(self, c):
        """A KO'd chaser back in the pen swaps with a fighter from the bench."""
        if not self.bench:
            return
        new = self.bench.pop(self.cast_rng.randrange(len(self.bench)))
        self.bench.append(c.cid)
        self.roster[c.i] = c.cid = new
        self.tagged += 1
        x, y = c.pos
        self.popups.append([ROSTER.get(new, new.upper()), x, y - 16, 50])

    def _target(self, c):
        a = self.akuma
        if self.mode == "scatter":
            return c.cfg["corner"]
        ax, ay = a.tile
        d = a.d or ("left" if a.face < 0 else "right")
        dx, dy = DIRS[d]
        if c.i == 0:                                     # chaser: straight at him
            return ax, ay
        if c.i == 1:                                     # ambusher: four tiles ahead
            return ax + dx * 4, ay + dy * 4
        if c.i == 2:                                     # flanker: mirror the chaser past him
            bx, by = self.chuns[0].tile
            px, py = ax + dx * 2, ay + dy * 2
            return px * 2 - bx, py * 2 - by
        cx, cy = c.tile                                  # shy one: backs off when close
        if (cx - ax) ** 2 + (cy - ay) ** 2 > 64:
            return ax, ay
        return c.cfg["corner"]

    def _choose(self, c):
        options = [d for d in DIRS if open_tile(step(c.tile, d))]
        if c.state == "eyes":
            return min(options, key=lambda d: HOME.get(step(c.tile, d), 999))
        if c.d and len(options) > 1 and REVERSE[c.d] in options:
            options.remove(REVERSE[c.d])
        if not options:
            return REVERSE[c.d] if c.d else "left"
        if c.scared and c.state == "out":
            return self.rng.choice(options)
        tx, ty = self._target(c)

        def dist(d):
            nx, ny = step(c.tile, d)
            return (nx - tx) ** 2 + (ny - ty) ** 2
        return min(options, key=dist)

    def _chun_speed(self, c):
        if c.state == "eyes":
            return EYES_SPEED
        if c.state in ("pen", "leave", "enter"):
            return PEN_SPEED
        if c.tile in TUNNEL:
            return TUNNEL_SPEED
        if c.scared:
            return SCARED_SPEED
        left = len(self.pellets)
        return CHUN_SPEED + (0.06 if left < 40 else 0) + (0.04 if left < 15 else 0)

    def _move_chun(self, c):
        sp = self._chun_speed(c)
        c.walked += sp
        if c.state == "pen":
            c.y += c.bob * 0.4
            if abs(c.y - PEN_Y) >= 2:
                c.bob = -c.bob
            if self.play_t >= c.release:
                c.state = "leave"
            return
        if c.state == "leave":
            ex = center(EXIT[0])
            if abs(c.x - ex) > 0.01:
                c.x += max(-sp, min(sp, ex - c.x))
                c.bob = 1
            else:
                c.y -= sp
                c.bob = -1
                if c.y <= center(EXIT[1]):
                    c.tile, c.p, c.d = EXIT, 0.0, "up"
                    c.state = "out"
                    c.d = "left" if c.i % 2 == 0 else "right"
            return
        if c.state == "enter":
            c.y += sp
            c.bob = 1
            if c.y >= PEN_Y:
                c.state, c.release = "pen", self.play_t + 20
                self._tag_out(c)
            return
        dist = sp
        while dist > 1e-6:
            if c.d is None:
                c.d = self._choose(c)
            s = min(dist, T - c.p)
            c.p += s
            dist -= s
            if c.p >= T - 1e-6:
                c.tile, c.p = step(c.tile, c.d), 0.0
                if c.state == "eyes" and c.tile == EXIT:
                    c.state = "enter"
                    c.x, c.y = float(center(EXIT[0])), float(center(EXIT[1]))
                    return
                c.d = self._choose(c)

    def _collide(self):
        ax, ay = self.akuma.pos
        for c in self.chuns:
            if c.state in ("eyes", "enter"):
                continue
            cx, cy = c.pos
            dx = abs(cx - ax)
            dx = min(dx, MW - dx)
            if dx < 6 and abs(cy - ay) < 6:
                if c.scared:
                    self._ko(c)
                else:
                    self._caught(c)
                    return True
        return False

    def _ko(self, c):
        pts = KO_PTS[min(self.combo, len(KO_PTS) - 1)]
        self.combo += 1
        self.score += pts
        x, y = c.pos
        self.effects.append(F.Effect(F.SPARK_HIT, OX + x, OY + y - 6, 3))
        self.popups.append([str(pts), x, y - 14, 50])
        c.state, c.scared = "eyes", False
        if c.p == 0 and c.d is None:
            c.d = "left"
        self.freeze = KO_FREEZE
        self.shake = 8
        audio.play("heavy")

    def _caught(self, c):
        self.hp = max(0, self.hp - self.dmg)
        self.catches += 1
        x, y = self.akuma.pos
        self.effects.append(F.Effect(F.SPARK_HIT, OX + x, OY + y - 8, 3))
        self.popups.append(["-%d" % self.dmg, x, y - 22, 60])
        self.phase, self.end_t = "caught", 0
        self.flash = 24
        self.shake = 12
        self.fright = 0
        audio.play("hit")

    # ---- draw ------------------------------------------------------------
    def draw(self, surf):
        surf.fill((8, 6, 14))
        sh = (0, 0)
        if self.shake:
            sh = (self.rng.choice((-2, -1, 1, 2)), self.rng.choice((-1, 0, 1)))
        ox, oy = OX + sh[0], OY + sh[1]
        won_flash = self.phase == "won" and (self.end_t // 12) % 2 == 1 and self.end_t < 100
        surf.blit(self.art["maze_flash" if won_flash else "maze"], (ox, oy))
        self._draw_pellets(surf, ox, oy)
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(OX, 0, MW, H))
        actors = [(self.akuma.pos[1], 0, None)]
        if self.phase not in ("won", "lost"):
            for c in self.chuns:
                actors.append((c.pos[1] - (0.5 if c.state == "eyes" else 0), 1, c))
        actors.sort(key=lambda a: (a[0], a[1]))
        for _, kind, c in actors:
            x, y = self.akuma.pos if c is None else c.pos
            for wrap in (0, -MW, MW):
                if wrap and not (x < T and wrap > 0 or x > MW - T and wrap < 0):
                    continue
                if c is None:
                    self._draw_akuma(surf, ox + wrap, oy)
                else:
                    self._draw_chun(surf, c, ox + wrap, oy)
        surf.set_clip(clip)
        for fx in self.effects:
            fx.draw(surf, sh)
        for text, x, y, f in self.popups:
            col = (255, 90, 70) if text.startswith("-") else (120, 230, 255)
            draw_text(surf, text, ox + x, oy + y - (50 - f) // 6, col, align="center")
        self._hud(surf)

    def _draw_pellets(self, surf, ox, oy):
        pc = (255, 214, 170)
        for x, y in self.pellets:
            cx, cy = ox + center(x), oy + center(y)
            if (x, y) in self.power:
                if self.phase == "play" and (self.t // 10) % 2:
                    continue
                pygame.draw.circle(surf, (120, 20, 40), (cx, cy), 4)
                pygame.draw.circle(surf, (255, 60, 70), (cx, cy), 3)
                surf.fill((255, 200, 210), (cx - 1, cy - 2, 2, 2))
            else:
                surf.fill(pc, (cx - 1, cy - 1, 2, 2))

    def _draw_akuma(self, surf, ox, oy):
        a = self.akuma
        x, y = a.pos
        x, y = round(ox + x), round(oy + y)
        if self.phase == "lost" or (self.phase == "caught" and self.hp <= 0 and self.end_t > 20):
            img, (ax, ay) = self.art["akuma_ko"]
            surf.blit(img, (x - ax, y + 5 - ay))
            return
        k = MAP_SCALE / AKUMA_SCALE          # same stride per drawn pixel as the map
        img, (ax, ay) = self.art["akuma"].frame(a.face, a.moving and self.phase == "play",
                                                a.walked * k, self.t)
        pygame.draw.ellipse(surf, (4, 2, 8), (x - 6, y + 2, 12, 4))
        if self.fright and (self.fright > BLINK or (self.t // 6) % 2 == 0) and (self.t // 3) % 3:
            ring = self.art.get(("aura", id(img)))
            if ring is None:
                ring = self.art[("aura", id(img))] = _aura_ring(img)
            surf.blit(ring, (x - ax - 2, y + 5 - ay - 2))
        if self.flash and (self.flash // 3) % 2 and self.phase == "caught":
            img = pygame.mask.from_surface(img).to_surface(setcolor=(255, 255, 255, 255),
                                                           unsetcolor=(0, 0, 0, 0))
        surf.blit(img, (x - ax, y + 5 - ay))

    def _draw_chun(self, surf, c, ox, oy):
        x, y = c.pos
        x, y = round(ox + x), round(oy + y)
        d = c.facing
        if c.state in ("eyes", "enter"):
            dx, dy = DIRS[d]
            for ex in (-4, 1):
                surf.fill(OUTLINE, (x + ex - 1, y - 10, 6, 7))
                surf.fill((255, 255, 255), (x + ex, y - 9, 4, 5))
                surf.fill((30, 40, 150), (x + ex + 1 + dx, y - 7 + dy, 2, 2))
            for k in range(3):                    # dizzy stars
                a = self.t / 7 + k * math.tau / 3
                sx, sy = x + round(math.cos(a) * 6), y - 14 + round(math.sin(a) * 2)
                surf.fill((255, 230, 90), (sx, sy, 1, 1))
                surf.fill((255, 230, 90), (sx - 1, sy + 1, 3, 1))
                surf.fill((255, 230, 90), (sx, sy + 2, 1, 1))
            return
        # the sheets are side-on: going up or down they keep their last side
        if d in ("left", "right"):
            c.side = 1 if d == "right" else -1
        art = chaser_art(c.cid)
        k = MAP_SCALE / art.scale            # same stride per drawn pixel as the map
        img, (ax, ay) = art.frame(getattr(c, "side", 1), True, c.walked * k, self.t)
        if c.scared:
            blink = self.fright < BLINK and (self.fright // 8) % 2 == 0
            key = ("scared", id(img), blink)
            if key not in self.art:
                self.art[key] = _scared(img, "up", blink)
            img = self.art[key]
        pygame.draw.ellipse(surf, (4, 2, 8), (x - 5, y + 2, 10, 4))
        surf.blit(img, (x - ax, y + 5 - ay))

    def _band(self, surf, y, h):
        band = self.art.get(("band", h))
        if band is None:
            band = self.art[("band", h)] = pygame.Surface((MW, h), pygame.SRCALPHA)
            band.fill((6, 4, 12, 190))
        surf.blit(band, (OX, y))

    def _hud(self, surf):
        surf.fill((10, 8, 16), (0, 0, W, HUD_H - 1))
        bw = 80
        pygame.draw.rect(surf, (20, 10, 14), (4, 2, bw + 2, 8))
        surf.fill((90, 16, 20), (5, 3, bw, 6))
        surf.fill((230, 60, 40), (5, 3, round(bw * self.hp_lag / self.max_hp), 6))
        surf.fill((250, 210, 40), (5, 3, round(bw * self.hp / self.max_hp), 6))
        draw_text(surf, "AKUMA", 90, 2, (255, 90, 90))
        draw_text(surf, LEVEL_NAME, W // 2 + 30, 2, (255, 220, 160), align="center")
        draw_text(surf, "PELLETS %d" % len(self.pellets), W - 4, 2, (255, 214, 170), align="right")
        if self.fright:
            col = (255, 60, 40) if self.fright > BLINK or (self.t // 6) % 2 else (255, 255, 255)
            draw_text(surf, "POWER", 4, 10, col)
            surf.fill(col, (36, 11, round(50 * self.fright / FRIGHT), 4))
        draw_text(surf, "SCORE %d" % self.score, W - 4, 10, (200, 200, 230), align="right")
        cx, cy = OX + center(15), OY + center(10) - 3
        if self.phase in ("intro", "ready"):
            n = INTRO if self.phase == "intro" else REINTRO
            if self.phase == "intro" and self.end_t < n - 30:
                self._band(surf, OY + 26, 32)
                self._band(surf, OY + 108, 15)
                draw_text(surf, "LEVEL %d" % self.level, W // 2, OY + 30, (255, 220, 80), scale=2,
                          align="center")
                draw_text(surf, "VS " + "  ".join(c.name for c in self.chuns), W // 2, OY + 48,
                          (255, 170, 200), align="center")
                draw_text(surf, "EAT EVERY PELLET. DON'T GET CAUGHT!", W // 2, OY + 112,
                          (255, 255, 255), align="center")
            self._band(surf, cy - 6, 19)
            if self.end_t < n - 30:
                draw_text(surf, "READY!", cx, cy, (255, 230, 60), align="center")
            else:
                draw_text(surf, "FIGHT!", cx, cy - 4, (255, 60, 40), scale=2, align="center")
        if self.phase == "won" and self.end_t > 10:
            self._band(surf, OY + 46, 48)
            draw_text(surf, "MAZE CLEARED!", W // 2, OY + 52, (255, 220, 60), scale=3, align="center")
            draw_text(surf, "THE FIGHTER SQUAD IS BEATEN", W // 2, OY + 82, (255, 255, 255), align="center")
        if self.phase == "lost" and self.end_t > 10:
            self._band(surf, OY + 54, 26)
            draw_text(surf, "AKUMA FALLS...", W // 2, OY + 60, (255, 255, 255), scale=2, align="center")
        if self.menu.open:
            self.menu.draw(surf)
