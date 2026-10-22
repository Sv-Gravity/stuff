"""Level 4: the car park, Bomberman style. No side-view fights here.

Akuma plants hadoukens as bombs: they pulse, flash faster, then burst in a
cross that stops at pillars and blows up the first crate it reaches. The cars
from level 3 cruise the lanes and fight back two ways: they stop and blink
their headlights, then switch them on in a beam down the lane, or they beep
and flash and then honk, a small round blast around the car. A single blast
wrecks a car; blow up every car to clear the level.
"""

import math
import random

import pygame

from . import audio
from . import fight as F
from .akuma_sprites import MapArt, hado_frames
from .art import shade, _outlined, OUTLINE
from .cars import CAR_MODELS, car_topdown
from .config import W, H, FPS
from .font import draw_text
from .pause import PauseMenu

T = 16                          # grid cell
COLS, ROWS = 19, 9              # outer wall included
OX, OY = (W - COLS * T) // 2, H - ROWS * T - 1
SPEED = 1.25                    # Akuma, px / frame
CAR_SPEED = 0.7
FUSE = 150                      # frames until a bomb goes off
BLAST_LIFE = 26
START_BOMBS, START_FIRE = 2, 2
MAX_BOMBS, MAX_FIRE = 5, 6
CAR_HP = 1                      # blasts to wreck a car (one blast does it)
LIGHTS_WARN, LIGHTS_ON = 60, 36
HONK_WARN, HONK_ON, HONK_R = 54, 14, 26
DMG_BEAM, DMG_HONK, DMG_BUMP, DMG_BLAST = 24, 20, 12, 32
INVULN = 80
CRATE_DENSITY = 0.36

EMPTY, WALL, PILLAR, CRATE = 0, 1, 2, 3
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
REVERSE = {"up": "down", "down": "up", "left": "right", "right": "left"}
ROT = {"up": 0, "left": 90, "down": 180, "right": -90}

CONTROLS = [
    "ARROWS / WASD: MOVE",
    "J / K / L / SPACE: PLANT A HADOUKEN BOMB",
    "BOMBS BURST IN A CROSS AFTER A FEW SECONDS",
    "BLINKING HEADLIGHTS: GET OUT OF THAT LANE!",
    "BEEPING CAR: STEP AWAY BEFORE IT HONKS",
    "ORBS: +B MORE BOMBS   +F BIGGER BLASTS",
    "YOUR OWN BLAST HURTS TOO",
    "BLOW UP EVERY CAR TO CLEAR THE LEVEL",
]


def center(c):
    return c * T + T // 2


# --------------------------------------------------------------------------
# art
# --------------------------------------------------------------------------
def _tiles(rng):
    t = {}
    floors = []
    for v in range(4):
        s = pygame.Surface((T, T))
        s.fill((52, 52, 60))
        for _ in range(14):
            s.set_at((rng.randrange(T), rng.randrange(T)), shade((52, 52, 60), rng.choice((0.8, 1.2))))
        if v == 1:
            pygame.draw.line(s, (196, 196, 180), (0, 1), (0, 14))       # parking bay line
        if v == 2:
            pygame.draw.line(s, (40, 40, 46), (3, 9), (9, 12))           # crack
        floors.append(s)
    t["floor"] = floors
    wall = pygame.Surface((T, T))
    wall.fill((92, 92, 104))
    pygame.draw.rect(wall, (120, 120, 132), (0, 0, T, 4))
    for x in range(-T, T, 6):                                            # hazard stripe
        pygame.draw.polygon(wall, (230, 190, 40), [(x, T), (x + 3, T), (x + 7, T - 4), (x + 4, T - 4)])
    pygame.draw.rect(wall, (20, 20, 26), (0, T - 5, T, 1))
    t["wall"] = wall
    pil = pygame.Surface((T, T + 6), pygame.SRCALPHA)
    pil.fill((150, 150, 160), (1, 0, T - 2, 8))                          # top
    pil.fill((112, 112, 124), (1, 8, T - 2, T - 2))                      # face
    for x in range(-T, T, 6):
        pygame.draw.polygon(pil, (230, 190, 40), [(x, T + 4), (x + 3, T + 4), (x + 7, T), (x + 4, T)])
    pil.fill((40, 40, 46), (1, T + 4, T - 2, 2))
    t["pillar"] = _outlined(pil)
    crates = []
    # a wooden crate, an oil drum, a stack of traffic cones
    c = pygame.Surface((T, T + 4), pygame.SRCALPHA)
    c.fill((176, 120, 64), (1, 1, T - 2, 6))
    c.fill((140, 92, 46), (1, 7, T - 2, T - 4))
    pygame.draw.line(c, (100, 64, 30), (2, 8), (T - 3, T + 1))
    pygame.draw.line(c, (100, 64, 30), (T - 3, 8), (2, T + 1))
    crates.append(_outlined(c))
    d = pygame.Surface((T, T + 4), pygame.SRCALPHA)
    pygame.draw.ellipse(d, (60, 110, 170), (2, 0, T - 4, 7))
    d.fill((44, 84, 140), (2, 3, T - 4, T - 1))
    d.fill((80, 140, 200), (2, 7, T - 4, 2))
    d.fill((80, 140, 200), (2, 13, T - 4, 2))
    pygame.draw.ellipse(d, (34, 60, 100), (5, 1, 4, 3))
    crates.append(_outlined(d))
    k = pygame.Surface((T, T + 4), pygame.SRCALPHA)
    for i, x in enumerate((3, 9)):
        pygame.draw.polygon(k, (240, 110, 30), [(x - 3, 17), (x + 4, 17), (x + 1, 4 + i * 2)])
        k.fill((240, 240, 240), (x - 1, 11 + i, 3, 2))
    k.fill((50, 50, 56), (0, 17, T, 2))
    crates.append(_outlined(k))
    t["crates"] = crates
    return t


def _orb(kind):
    s = pygame.Surface((14, 14), pygame.SRCALPHA)
    col = (170, 90, 255) if kind == "bomb" else (255, 140, 40)
    pygame.draw.circle(s, shade(col, 0.6), (7, 7), 6)
    pygame.draw.circle(s, col, (7, 7), 5)
    pygame.draw.circle(s, (255, 255, 255), (5, 5), 1)
    out = _outlined(s)
    draw_text(out, "B" if kind == "bomb" else "F", 7, 4, (255, 255, 255), align="center")
    return out


def _bomb_frames():
    """The hadouken ball shrunk to a cell, plus a white flash version."""
    src = hado_frames()[1]
    k = 15 / src.get_height()
    img = pygame.transform.smoothscale(src, (max(1, round(src.get_width() * k)), 15))
    # keep the round head of the fireball, not its trail
    w = img.get_width()
    ball = img.subsurface((max(0, w - 16), 0, min(16, w), 15)).copy()
    flash = pygame.mask.from_surface(ball).to_surface(setcolor=(255, 240, 255, 255),
                                                      unsetcolor=(0, 0, 0, 0))
    return ball, flash


# --------------------------------------------------------------------------
# things on the grid
# --------------------------------------------------------------------------
class Bomb:
    def __init__(self, cx, cy, fire):
        self.cx, self.cy, self.fire = cx, cy, fire
        self.t = 0
        self.passable = True     # Akuma can step off the bomb he just planted
        self.done = False


class Car:
    def __init__(self, model, cx, cy, rng):
        self.model = model
        self.name = model["name"]
        roof = (24, 22, 26) if "vinyl" in model["extras"] else None
        up = car_topdown(model["color"], roof)
        self.frames = {d: pygame.transform.rotate(up, ROT[d]) for d in DIRS}
        white = pygame.mask.from_surface(up).to_surface(setcolor=(255, 255, 255, 255),
                                                        unsetcolor=(0, 0, 0, 0))
        self.white = {d: pygame.transform.rotate(white, ROT[d]) for d in DIRS}
        self.cx, self.cy = cx, cy
        self.x, self.y = float(center(cx)), float(center(cy))
        self.target = None
        self.dir = rng.choice(list(DIRS))
        self.hp = CAR_HP
        self.state = "drive"     # drive, lights, honk, wreck
        self.t = 0
        self.cool = rng.randrange(120, 260)
        self.flash = 0
        self.speed = CAR_SPEED * rng.uniform(0.85, 1.1)
        self.beam = []

    @property
    def alive(self):
        return self.state != "wreck"


# --------------------------------------------------------------------------
# the level
# --------------------------------------------------------------------------
class BomberScene:
    def __init__(self, game, seed, level=4):
        F.init_shared()
        self.game = game
        self.level = level
        self.rng = random.Random(seed)
        self.tiles = _tiles(random.Random(seed + 1))
        self.bomb_img, self.bomb_flash = _bomb_frames()
        self.orbs = {k: _orb(k) for k in ("bomb", "fire")}
        self.art = MapArt()
        self.menu = PauseMenu(game, CONTROLS)
        self._build()
        self.px, self.py = float(center(1)), float(center(1))
        self.face = 1
        self.walked = 0.0
        self.moving = False
        self.hp = game.akuma_max
        self.max_hp = game.akuma_max
        self.hp_lag = self.hp
        self.invuln = 0
        self.max_bombs, self.fire = START_BOMBS, START_FIRE
        self.bombs = []
        self.blasts = {}         # (cx, cy) -> [life, shape, blast id]
        self.blast_id = 0
        self.burning = []        # crates on fire: [cx, cy, t]
        self.items = {}          # (cx, cy) -> "bomb" / "fire"
        self.rings = []          # honk rings: [x, y, t]
        self.sparks = []
        self.debris = []
        self.phase = "intro"
        self.t = 0
        self.end_t = 0
        self.shake = 0
        self.banner = None
        self.result = None

    def _build(self):
        rng = self.rng
        g = [[EMPTY] * COLS for _ in range(ROWS)]
        for y in range(ROWS):
            for x in range(COLS):
                if x in (0, COLS - 1) or y in (0, ROWS - 1):
                    g[y][x] = WALL
                elif x % 2 == 0 and y % 2 == 0:
                    g[y][x] = PILLAR
        open_cells = [(x, y) for y in range(ROWS) for x in range(COLS) if g[y][x] == EMPTY]
        # five cars, far from Akuma's corner, spread over the lot
        far = [c for c in open_cells if c[0] + c[1] >= 9]
        rng.shuffle(far)
        spots = []
        for c in far:
            if all(abs(c[0] - s[0]) + abs(c[1] - s[1]) >= 4 for s in spots):
                spots.append(c)
            if len(spots) == len(CAR_MODELS):
                break
        keep = {(1, 1), (2, 1), (1, 2), (3, 1), (1, 3)}
        for sx, sy in spots:
            keep |= {(sx, sy), (sx + 1, sy), (sx - 1, sy), (sx, sy + 1), (sx, sy - 1)}
        for x, y in open_cells:
            if (x, y) not in keep and rng.random() < CRATE_DENSITY:
                g[y][x] = CRATE
        self.grid = g
        self.crate_kind = {(x, y): rng.randrange(3) for x, y in open_cells}
        self.floor_kind = [[rng.choice((0, 0, 0, 1, 2, 3)) for _ in range(COLS)] for _ in range(ROWS)]
        self.cars = [Car(m, sx, sy, rng) for m, (sx, sy) in zip(CAR_MODELS, spots)]

    # ---- grid queries ----------------------------------------------------
    def _cell(self, cx, cy):
        if 0 <= cx < COLS and 0 <= cy < ROWS:
            return self.grid[cy][cx]
        return WALL

    def _bomb_at(self, cx, cy):
        return next((b for b in self.bombs if b.cx == cx and b.cy == cy), None)

    def _free_for_akuma(self, cx, cy):
        if self._cell(cx, cy) != EMPTY:
            return False
        b = self._bomb_at(cx, cy)
        return b is None or b.passable

    def _free_for_car(self, cx, cy, me):
        if self._cell(cx, cy) != EMPTY or self._bomb_at(cx, cy):
            return False
        for c in self.cars:
            if c is me or not c.alive:
                continue
            if (c.cx, c.cy) == (cx, cy) or (c.target and c.target == (cx, cy)):
                return False
        return True

    def _danger(self):
        """Cells about to be (or being) blasted, so cars can try to dodge."""
        d = set(self.blasts)
        for b in self.bombs:
            d.add((b.cx, b.cy))
            for dx, dy in DIRS.values():
                for k in range(1, b.fire + 1):
                    c = (b.cx + dx * k, b.cy + dy * k)
                    if self._cell(*c) != EMPTY:
                        break
                    d.add(c)
        return d

    @property
    def akuma_cell(self):
        return int(self.px // T), int(self.py // T)

    @property
    def paused(self):
        return self.menu.open

    # ---- update ----------------------------------------------------------
    def update(self, inp):
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.phase == "play" and self.menu.toggle(inp):
            return
        self.t += 1
        self.hp_lag = max(self.hp, self.hp_lag - 0.6) if self.hp_lag > self.hp else self.hp
        if self.shake:
            self.shake -= 1
        if self.banner:
            self.banner[1] -= 1
            if self.banner[1] <= 0:
                self.banner = None
        self._fx()
        if self.phase == "intro":
            if self.t == 70:
                audio.play("fight")
            if self.t >= 90:
                self.phase = "play"
            return
        if self.phase in ("won", "lost"):
            self.end_t += 1
            self._bombs()
            self._blasts()
            skip = self.end_t > 40 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= 140 or skip:
                if self.phase == "won":
                    self.result = "win"
                    self.game.level_done(self, max(1, self.hp))
                else:
                    self.result = "lose"
                    self.game.level_failed(self)
            return
        if self.invuln:
            self.invuln -= 1
        self._move(inp)
        if inp.any_pressed("punch", "kick", "special"):
            self._plant()
        self._bombs()
        self._blasts()
        for car in self.cars:
            self._car(car)
        self._pickups()
        if self.hp <= 0:
            self.phase, self.end_t = "lost", 0
            audio.play("ko")
        elif not any(c.alive for c in self.cars):
            self.phase, self.end_t = "won", 0
            audio.play("fight")

    def _fx(self):
        for s in self.sparks:
            s.update()
        self.sparks = [s for s in self.sparks if s.alive]
        for d in self.debris:
            d[0] += d[2]
            d[1] += d[3]
            d[3] += 0.25
            d[4] -= 1
        self.debris = [d for d in self.debris if d[4] > 0]
        for r in self.rings:
            r[2] += 1
        self.rings = [r for r in self.rings if r[2] < 18]
        for b in self.burning:
            b[2] += 1
        self.burning = [b for b in self.burning if b[2] < 20]

    # ---- Akuma -----------------------------------------------------------
    def _move(self, inp):
        dx = (1 if inp.held("right") else 0) - (1 if inp.held("left") else 0)
        dy = (1 if inp.held("down") else 0) - (1 if inp.held("up") else 0)
        if dx and dy:
            # both held: keep going the way we were already lined up for
            if abs(self.py - center(int(self.py // T))) < 1:
                dy = 0
            else:
                dx = 0
        ox, oy = self.px, self.py
        if dx:
            self.px, self.py = self._step(self.px, self.py, dx, axis=0)
            self.face = dx
        elif dy:
            self.py, self.px = self._step(self.py, self.px, dy, axis=1)
        moved = math.hypot(self.px - ox, self.py - oy)
        self.walked += moved
        self.moving = moved > 0.2
        if self.moving and int(self.walked / 12) != int((self.walked - moved) / 12):
            audio.play("step", 0.5)
        # the bomb under Akuma turns solid once he has stepped clear of it
        for b in self.bombs:
            if b.passable and (abs(self.px - center(b.cx)) >= T or abs(self.py - center(b.cy)) >= T):
                b.passable = False

    def _step(self, a, b, d, axis):
        """Move along one axis with Bomberman corner sliding.

        a = position along the move, b = across it. Returns the new (a, b)."""
        sp = SPEED

        def free(ca, cb):
            return self._free_for_akuma(ca, cb) if axis == 0 else self._free_for_akuma(cb, ca)
        lane = int(b // T)
        here = int(a // T)
        off = center(lane) - b
        if abs(off) > 0.01:
            if free(here + d, lane):
                s = min(sp, abs(off))
                b += s if off > 0 else -s
                sp -= s
            elif abs(off) > 3 and free(here + d, lane + (1 if off < 0 else -1)):
                # nearly past a pillar corner: slide round it into the next lane
                b += -sp if off > 0 else sp
                return a, b
            else:
                sp = 0
        if sp > 0:
            na = a + d * sp
            front = na + d * (T / 2)
            col = math.floor(front / T)
            if col != here and not free(col, lane):
                na = col * T - T / 2 if d > 0 else (col + 1) * T + T / 2
                if (na - a) * d < 0:
                    na = a
            a = na
        return a, b

    def _plant(self):
        cx, cy = self.akuma_cell
        if self._bomb_at(cx, cy) or self._cell(cx, cy) != EMPTY:
            return
        if sum(1 for b in self.bombs if not b.done) >= self.max_bombs:
            return
        self.bombs.append(Bomb(cx, cy, self.fire))
        audio.play("plant")

    def _hurt(self, dmg, why):
        if self.invuln or self.phase != "play":
            return
        self.hp = max(0, self.hp - dmg)
        self.invuln = INVULN
        self.shake = 8
        audio.play("heavy")
        self.sparks.append(F.Effect(F.SPARK_HIT, OX + self.px, OY + self.py - 10, 2))
        self.banner = [why, 50]

    def _pickups(self):
        c = self.akuma_cell
        kind = self.items.pop(c, None)
        if kind == "bomb":
            self.max_bombs = min(MAX_BOMBS, self.max_bombs + 1)
            audio.play("pickup")
            self.banner = ["+1 BOMB", 40]
        elif kind == "fire":
            self.fire = min(MAX_FIRE, self.fire + 1)
            audio.play("pickup")
            self.banner = ["BIGGER BLASTS", 40]

    # ---- bombs and blasts ------------------------------------------------
    def _bombs(self):
        for b in list(self.bombs):
            b.t += 1
            if b.t >= FUSE and not b.done:
                self._explode(b)
        self.bombs = [b for b in self.bombs if not b.done]

    def _explode(self, b):
        b.done = True
        self.blast_id += 1
        bid = self.blast_id
        audio.play("boom")
        self.shake = max(self.shake, 6)
        cells = {(b.cx, b.cy): "c"}
        for name, (dx, dy) in DIRS.items():
            for k in range(1, b.fire + 1):
                c = (b.cx + dx * k, b.cy + dy * k)
                kind = self._cell(*c)
                if kind in (WALL, PILLAR):
                    break
                if kind == CRATE:
                    self.grid[c[1]][c[0]] = EMPTY
                    self.burning.append([c[0], c[1], 0])
                    roll = self.rng.random()
                    if roll < 0.14:
                        self.items[c] = "bomb"
                    elif roll < 0.28:
                        self.items[c] = "fire"
                    break
                cells[c] = ("h" if dx else "v") + ("e" if k == b.fire else "")
                if c in self.items:
                    del self.items[c]            # blasts burn up power-ups
                other = self._bomb_at(*c)
                if other and not other.done:
                    other.t = FUSE - 4           # chain reaction
        for c, shape in cells.items():
            self.blasts[c] = [BLAST_LIFE, shape, bid]

    def _blasts(self):
        for c in list(self.blasts):
            self.blasts[c][0] -= 1
            if self.blasts[c][0] <= 0:
                del self.blasts[c]
        if self.phase != "play":
            return
        if self.akuma_cell in self.blasts:
            self._hurt(DMG_BLAST, "OUCH! YOUR OWN BLAST!")
        for car in self.cars:
            if not car.alive:
                continue
            hit = self.blasts.get((round((car.x - T / 2) / T), round((car.y - T / 2) / T)))
            if hit and getattr(car, "last_blast", 0) != hit[2]:
                car.last_blast = hit[2]
                self._car_hit(car)

    # ---- cars ------------------------------------------------------------
    def _car_hit(self, car):
        car.hp -= 1
        car.flash = 24
        self.sparks.append(F.Effect(F.SPARK_HIT, OX + car.x, OY + car.y, 2))
        for _ in range(8):
            self.debris.append([car.x, car.y, self.rng.uniform(-1.5, 1.5), self.rng.uniform(-3, -1),
                                40, self.rng.choice((car.model["color"], (200, 230, 255)))])
        if car.hp <= 0:
            car.state = "wreck"
            car.t = 0
            car.beam = []
            car.target = None
            self.game.kills += 1
            audio.play("ko")
            self.shake = 12
            self.banner = ["%s WRECKED!" % car.name, 70]
            for _ in range(18):
                self.debris.append([car.x, car.y, self.rng.uniform(-2.5, 2.5), self.rng.uniform(-4, -1),
                                    60, self.rng.choice((car.model["color"], (60, 60, 64), (255, 200, 60)))])
        else:
            audio.play("hit")
            # a hit car stops whatever it was doing
            if car.state != "drive":
                car.state, car.beam, car.cool = "drive", [], 120

    def _car(self, car):
        if not car.alive:
            car.t += 1
            return
        if car.flash:
            car.flash -= 1
        car.t += 1
        if car.cool:
            car.cool -= 1
        if car.state == "drive":
            self._drive(car)
        elif car.state == "lights":
            if car.t == LIGHTS_WARN:
                car.beam = self._beam(car)
                audio.play("lights")
            if car.t >= LIGHTS_WARN and self.akuma_cell in car.beam:
                self._hurt(DMG_BEAM, "BLINDED BY THE HEADLIGHTS!")
            if car.t >= LIGHTS_WARN + LIGHTS_ON:
                car.state, car.beam, car.cool = "drive", [], self.rng.randrange(150, 260)
        elif car.state == "honk":
            if car.t < HONK_WARN and car.t % 12 == 0:
                audio.play("beep", 0.6)
            if car.t == HONK_WARN:
                audio.play("honk")
                self.rings.append([car.x, car.y, 0])
                self.shake = max(self.shake, 4)
            if HONK_WARN <= car.t < HONK_WARN + HONK_ON:
                if math.hypot(self.px - car.x, self.py - car.y) <= HONK_R + 4:
                    self._hurt(DMG_HONK, "HONK! BLOWN AWAY!")
            if car.t >= HONK_WARN + HONK_ON:
                car.state, car.cool = "drive", self.rng.randrange(150, 260)
        # bumping into a car hurts a little
        if math.hypot(self.px - car.x, self.py - car.y) < 11:
            self._hurt(DMG_BUMP, "RUN OVER!")

    def _beam(self, car):
        dx, dy = DIRS[car.dir]
        cells = []
        c = (car.cx + dx, car.cy + dy)
        while self._cell(*c) == EMPTY:
            cells.append(c)
            c = (c[0] + dx, c[1] + dy)
        return cells

    def _sees(self, car):
        """Direction from the car straight down a clear lane to Akuma, if any."""
        ax, ay = self.akuma_cell
        if ax != car.cx and ay != car.cy:
            return None
        if (ax, ay) == (car.cx, car.cy):
            return None
        d = ("right" if ax > car.cx else "left") if ay == car.cy else ("down" if ay > car.cy else "up")
        dx, dy = DIRS[d]
        c = (car.cx + dx, car.cy + dy)
        n = 0
        while c != (ax, ay):
            if self._cell(*c) != EMPTY or n > 12:
                return None
            c = (c[0] + dx, c[1] + dy)
            n += 1
        return d

    def _drive(self, car):
        if car.target:
            tx, ty = center(car.target[0]), center(car.target[1])
            ddx, ddy = tx - car.x, ty - car.y
            dist = math.hypot(ddx, ddy)
            if dist <= car.speed:
                car.x, car.y = float(tx), float(ty)
                car.cx, car.cy = car.target
                car.target = None
            else:
                car.x += ddx / dist * car.speed
                car.y += ddy / dist * car.speed
                return
        # at a cell centre: attack, or pick the next cell
        if not car.cool and self.phase == "play":
            seen = self._sees(car)
            near = math.hypot(self.px - car.x, self.py - car.y) < HONK_R + T
            if near and self.rng.random() < 0.6:
                car.state, car.t = "honk", 0
                return
            if seen and self.rng.random() < 0.7:
                car.dir = seen
                car.state, car.t = "lights", 0
                return
            if self.rng.random() < 0.01:
                car.state, car.t = self.rng.choice(("honk", "lights")), 0
                return
        danger = self._danger()
        opts = [d for d, (dx, dy) in DIRS.items() if self._free_for_car(car.cx + dx, car.cy + dy, car)]
        if not opts:
            return
        safe = [d for d in opts if (car.cx + DIRS[d][0], car.cy + DIRS[d][1]) not in danger]
        if safe and (car.cx, car.cy) not in danger or safe and self.rng.random() < 0.7:
            opts = safe
        fwd = [d for d in opts if d != REVERSE[car.dir]]
        if car.dir in opts and self.rng.random() < 0.7:
            d = car.dir
        else:
            d = self.rng.choice(fwd or opts)
        car.dir = d
        car.target = (car.cx + DIRS[d][0], car.cy + DIRS[d][1])

    # ---- drawing ---------------------------------------------------------
    def draw(self, surf):
        sh = (0, 0)
        if self.shake:
            sh = (self.rng.choice((-2, -1, 1, 2)), self.rng.choice((-1, 0, 1)))
        surf.fill((16, 14, 22))
        ox, oy = OX + sh[0], OY + sh[1]
        for y in range(ROWS):
            for x in range(COLS):
                k = self.grid[y][x]
                pos = (ox + x * T, oy + y * T)
                if k == WALL:
                    surf.blit(self.tiles["wall"], pos)
                else:
                    surf.blit(self.tiles["floor"][self.floor_kind[y][x]], pos)
        for (cx, cy), kind in self.items.items():
            bob = 1 if (self.t // 15) % 2 else 0
            surf.blit(self.orbs[kind], (ox + cx * T + 1, oy + cy * T + 1 - bob))
        self._draw_blasts(surf, ox, oy)
        for c in self.cars:
            if c.beam:
                self._draw_beam(surf, c, ox, oy)
        # everything with height, back to front
        things = []
        for y in range(ROWS):
            for x in range(COLS):
                k = self.grid[y][x]
                if k == PILLAR:
                    things.append((y * T + T, 0, "pillar", x, y))
                elif k == CRATE:
                    things.append((y * T + T, 0, "crate", x, y))
        for b in self.bombs:
            things.append((b.cy * T + T - 1, 1, "bomb", b))
        for c in self.cars:
            things.append((c.y + 6, 2, "car", c))
        things.append((self.py + 6, 3, "akuma", None))
        things.sort(key=lambda t: (t[0], t[1]))
        for th in things:
            kind = th[2]
            if kind == "pillar":
                surf.blit(self.tiles["pillar"], (ox + th[3] * T, oy + th[4] * T - 6))
            elif kind == "crate":
                img = self.tiles["crates"][self.crate_kind[(th[3], th[4])]]
                surf.blit(img, (ox + th[3] * T, oy + th[4] * T - 4))
            elif kind == "bomb":
                self._draw_bomb(surf, th[3], ox, oy)
            elif kind == "car":
                self._draw_car(surf, th[3], ox, oy)
            else:
                self._draw_akuma(surf, ox, oy)
        for cx, cy, t in self.burning:
            r = 8 - t // 3
            if r > 0:
                pygame.draw.circle(surf, (255, 160, 60), (ox + center(cx), oy + center(cy)), r)
                pygame.draw.circle(surf, (255, 240, 180), (ox + center(cx), oy + center(cy)), max(1, r - 3))
        for x, y, t in self.rings:
            r = int(6 + (HONK_R - 6) * min(1, t / 8))
            col = (255, 240, 150) if t < 10 else (200, 160, 80)
            pygame.draw.circle(surf, col, (round(ox + x), round(oy + y)), r, 2)
            if t < 6:
                pygame.draw.circle(surf, (255, 255, 220), (round(ox + x), round(oy + y)), r - 4, 1)
        for d in self.debris:
            surf.fill(d[5], (round(ox + d[0]), round(oy + d[1]), 2, 2))
        for s in self.sparks:
            s.draw(surf, (0, 0))
        self._hud(surf)

    def _draw_bomb(self, surf, b, ox, oy):
        left = FUSE - b.t
        rate = 16 if left > 70 else 8 if left > 30 else 3
        flash = (b.t // rate) % 2 == 1
        pulse = 1 + 0.12 * math.sin(b.t * (0.25 if left > 50 else 0.6))
        img = self.bomb_flash if flash else self.bomb_img
        img = pygame.transform.scale_by(img, pulse)
        x = ox + center(b.cx) - img.get_width() // 2
        y = oy + center(b.cy) - img.get_height() // 2
        pygame.draw.ellipse(surf, (20, 14, 26), (ox + b.cx * T + 3, oy + b.cy * T + 12, 10, 4))
        surf.blit(img, (x, y))

    def _draw_blasts(self, surf, ox, oy):
        for (cx, cy), (life, shape, _) in self.blasts.items():
            k = life / BLAST_LIFE
            w = max(2, round(14 * min(1, k * 1.6)))
            x, y = ox + cx * T, oy + cy * T
            outer, inner, core = (150, 60, 230), (220, 150, 255), (255, 245, 255)
            for col, ww in ((outer, w), (inner, max(1, w - 5)), (core, max(1, w - 9))):
                if shape == "c":
                    pygame.draw.circle(surf, col, (x + 8, y + 8), max(1, ww // 2 + 1))
                elif shape[0] == "h":
                    surf.fill(col, (x, y + 8 - ww // 2, T, ww))
                else:
                    surf.fill(col, (x + 8 - ww // 2, y, ww, T))

    def _draw_beam(self, surf, car, ox, oy):
        if not car.beam:
            return
        dx, dy = DIRS[car.dir]
        x0, y0 = ox + center(car.cx) + dx * 9, oy + center(car.cy) + dy * 9
        last = car.beam[-1]
        x1, y1 = ox + center(last[0]) + dx * 8, oy + center(last[1]) + dy * 8
        glow = pygame.Surface((W, H), pygame.SRCALPHA)
        flick = 30 if (self.t // 2) % 2 else 0
        if dx:
            xa, xb = sorted((x0, x1))
            glow.fill((255, 250, 170, 90 + flick), (xa, y0 - 7, xb - xa, 14))
            glow.fill((255, 255, 230, 170), (xa, y0 - 3, xb - xa, 6))
        else:
            ya, yb = sorted((y0, y1))
            glow.fill((255, 250, 170, 90 + flick), (x0 - 7, ya, 14, yb - ya))
            glow.fill((255, 255, 230, 170), (x0 - 3, ya, 6, yb - ya))
        surf.blit(glow, (0, 0))

    def _draw_car(self, surf, car, ox, oy):
        if not car.alive:
            if car.t > 90 and (car.t // 3) % 2:
                return
            if car.t > 110:
                return
            img = car.frames[car.dir].copy()
            img.fill((60, 50, 50), special_flags=pygame.BLEND_RGB_MULT)
            surf.blit(img, (round(ox + car.x - img.get_width() / 2), round(oy + car.y - img.get_height() / 2)))
            if car.t % 6 < 3:
                pygame.draw.circle(surf, (90, 90, 96), (round(ox + car.x), round(oy + car.y - 8 - car.t % 12)), 3)
            return
        wob = 0
        if car.state == "honk" and car.t < HONK_WARN:
            wob = 1 if (car.t // 3) % 2 else -1
        img = car.white[car.dir] if (car.flash and car.flash % 4 < 2) else car.frames[car.dir]
        if car.state == "honk" and car.t < HONK_WARN and (car.t // 6) % 2:
            img = img.copy()
            img.fill((70, 70, 20), special_flags=pygame.BLEND_RGB_ADD)
        x = round(ox + car.x - img.get_width() / 2) + wob
        y = round(oy + car.y - img.get_height() / 2)
        pygame.draw.ellipse(surf, (16, 12, 20), (x + 1, y + img.get_height() - 5, img.get_width() - 2, 6))
        surf.blit(img, (x, y))
        # headlights: blink while warning, blaze while on
        lit = car.state == "lights" and (car.t >= LIGHTS_WARN or (car.t // 6) % 2 == 0)
        if lit:
            dx, dy = DIRS[car.dir]
            cx, cy = ox + car.x + dx * 10, oy + car.y + dy * 10
            for side in (-1, 1):
                hx, hy = round(cx + side * 4 * abs(dy)), round(cy + side * 4 * abs(dx))
                pygame.draw.circle(surf, (255, 250, 190), (hx, hy), 3 if car.t >= LIGHTS_WARN else 2)
                surf.set_at((hx, hy), (255, 255, 255))
        if car.state == "honk" and car.t < HONK_WARN and (car.t // 12) % 2 == 0:
            draw_text(surf, "BEEP", round(ox + car.x), round(oy + car.y - 18), (255, 240, 120), align="center")
        if car.state == "honk" and HONK_WARN <= car.t < HONK_WARN + HONK_ON:
            draw_text(surf, "HONK!", round(ox + car.x), round(oy + car.y - 20), (255, 255, 255), align="center")

    def _draw_akuma(self, surf, ox, oy):
        if self.invuln and (self.invuln // 3) % 2:
            return
        img, (ax, ay) = self.art.frame(self.face, self.moving, self.walked, self.t)
        x = round(ox + self.px) - ax
        y = round(oy + self.py + 6) - ay
        pygame.draw.ellipse(surf, (16, 12, 20), (round(ox + self.px) - 6, round(oy + self.py) + 3, 12, 5))
        surf.blit(img, (x, y))

    def _hud(self, surf):
        surf.fill((10, 8, 16), (0, 0, W, OY - 1))
        surf.blit(F._PORTRAIT, (3, 2))
        x0 = 6 + F._PORTRAIT.get_width()
        bw = 96
        pygame.draw.rect(surf, (20, 10, 14), (x0, 4, bw + 2, 8))
        lag = round(bw * self.hp_lag / self.max_hp)
        cur = round(bw * self.hp / self.max_hp)
        surf.fill((230, 60, 40), (x0 + 1, 5, lag, 6))
        surf.fill((250, 210, 40), (x0 + 1, 5, cur, 6))
        draw_text(surf, "AKUMA", x0, 15, (255, 90, 90))
        draw_text(surf, "BOMBS %d  FIRE %d" % (self.max_bombs, self.fire), x0 + 40, 15, (200, 170, 255))
        draw_text(surf, "THE CAR PARK", W - 4, 3, (255, 220, 160), align="right")
        for i, c in enumerate(self.cars):
            x = W - 4 - (len(self.cars) - i) * 18
            icon = pygame.transform.rotate(c.frames["up"], -90)
            if not c.alive:
                icon = icon.copy()
                icon.fill((70, 60, 60), special_flags=pygame.BLEND_RGB_MULT)
            surf.blit(icon, (x, 15))
            if c.alive and c.hp < CAR_HP:
                surf.fill((255, 120, 40), (x + 9, 24, 3, 2))
            if not c.alive:
                draw_text(surf, "X", x + 11, 15, (255, 60, 40), align="center")
        if self.phase == "intro":
            draw_text(surf, "LEVEL %d" % self.level, W // 2, 60, (255, 220, 80), scale=2, align="center")
            draw_text(surf, "THE CAR PARK", W // 2, 80, (255, 255, 255), align="center")
            draw_text(surf, "PLANT HADOUKENS. BLOW UP EVERY CAR!", W // 2, 94, (200, 200, 230), align="center")
            if self.t > 70:
                draw_text(surf, "GO!", W // 2, 112, (255, 60, 40), scale=3, align="center")
        if self.banner and self.phase == "play":
            draw_text(surf, self.banner[0], W // 2, OY + 4, (255, 240, 200), align="center")
        if self.phase == "won" and self.end_t > 10:
            draw_text(surf, "LOT CLEARED!", W // 2, 70, (255, 220, 60), scale=3, align="center")
        if self.phase == "lost" and self.end_t > 10:
            draw_text(surf, "AKUMA FALLS...", W // 2, 74, (255, 255, 255), scale=2, align="center")
        if self.menu.open:
            self.menu.draw(surf)
