"""Overhead roguelike map: generation, exploration, enemies, pickups."""

import math
import random
from types import SimpleNamespace

import pygame

from . import audio
from .akuma_sprites import MapArt, MAP_SCALE
from .art import BOSS_LOOK, BOSS2_LOOK, random_look, make_tiles
from .config import W, H, TILE, MAP_W, MAP_H, PLAYER_SPEED
from .fighters import random_moveset, boss_moveset, boss2_moveset, scale_damage, HIT
from .font import draw_text
from .fight import CONTROLS
from .pause import PauseMenu, MAP_LINE
from . import cars

WALL, FLOOR = 0, 1

# Per-level setup. Hits are normal hits (a kick; a punch is half). A grunt takes
# grunt_hits + its level (1-4) hits, so level 1 grunts average about 7 and
# level 2 a little more; boss_hits is how many hits the boss takes.
LEVELS = {
    1: dict(name="THE CAVES OF GOKUENTOU", ambient=(150, 136, 170), enemies=12,
            weights=[35, 30, 22, 13], grunt_hits=5, boss_name="ZANGIEF", boss_look=BOSS_LOOK,
            grunts=["ryu", "ken", "sakura", "felicia"], boss="zangief",
            boss_hits=15, boss_dmg=3.0, boss_ai=dict(aggression=0.7, block=0.3, jumpiness=0.15, reaction=3)),
    # every level 2 grunt brings a partner: two on one (the boss still fights alone)
    2: dict(name="THE BURNING TEMPLE", ambient=(175, 130, 120), enemies=10, squad=(2, 2),
            weights=[10, 25, 35, 30], grunt_hits=4, boss_name="MORRIGAN", boss_look=BOSS2_LOOK,
            grunts=["ryu", "ken", "sakura", "felicia", "hsienko"], boss="morrigan",
            boss_hits=18, boss_dmg=3.5, boss_ai=dict(aggression=0.85, block=0.35, jumpiness=0.3, reaction=2)),
    # bonus-stage level: a few cars drive around a small garage; smash them before the timer
    3: dict(name="THE WRECKING YARD", ambient=(150, 150, 178), enemies=5, cars=True,
            rooms=6, area=(38, 28), boss_name="THE BLOCK CRUISER"),
    # no overworld: these levels are whole scenes of their own (game.start_level)
    4: dict(name="THE CAR PARK", mode="bomber", boss_name="EVERY CAR IN THE LOT"),
    5: dict(name="THE FIGHTER MAZE", mode="pacman", boss_name="THE FIGHTER SQUAD"),
    6: dict(name="HYRULE CASTLE", mode="smash", boss_name="THREE CHALLENGERS"),
    # Dynasty Warriors: whole armies of one- or two-hit soldiers, then Lu Bu
    7: dict(name="HU LAO GATE", ambient=(185, 150, 110), enemies=9, musou=True, squad=(5, 10),
            weights=[40, 35, 20, 5], grunt_hits=0, boss_name="LU BU", boss_look=BOSS_LOOK,
            grunts=["ryu", "ken", "sakura", "chunli", "felicia", "hsienko"], boss="lubu",
            boss_hits=24, boss_dmg=4.5, boss_ai=dict(aggression=0.95, block=0.45, jumpiness=0.25, reaction=2)),
    8: dict(name="THE FROZEN COMPOUND", mode="stealth", boss_name="THE GENOME SQUAD"),
    9: dict(name="SKATE OR DIE", mode="skate", boss_name="100 POINTS"),
    10: dict(name="CONNECT FOUR", mode="connect4", boss_name="RYU"),
    # Nidhogg: every battle is a one-hit sabre duel; Akuma has 5 hearts for the level
    11: dict(name="THE HALL OF BLADES", ambient=(130, 140, 160), enemies=8, nidhogg=True,
             weights=[30, 30, 25, 15], grunt_hits=1, boss_name="THE SWORD SAINT RYU", boss_look=BOSS_LOOK,
             grunts=["ryu", "ken", "sakura", "chunli", "felicia", "hsienko", "morrigan"], boss="ryu",
             boss_hits=1, boss_dmg=1.0, boss_ai=dict(aggression=0.9, block=0.6, jumpiness=0.3, reaction=2)),
    12: dict(name="THE PRISONERS' QUARTERS", mode="metroid", boss_name="THE WARDEN"),
    13: dict(name="KNEE-DEEP IN THE DEMON", mode="doom", boss_name="CYBER-GIEF"),
}

HEARTS = 5      # level 11: Akuma's hits for the whole level

# fighters from Toshi's sprite pack (akuma/assets/chars/<id>)
CHAR_NAMES = {"ryu": "RYU", "ken": "KEN", "sakura": "SAKURA", "felicia": "FELICIA",
              "hsienko": "HSIEN-KO", "morrigan": "MORRIGAN", "zangief": "ZANGIEF", "chunli": "CHUN-LI", "lubu": "LU BU"}

# Three Kingdoms rank and file for Hu Lao Gate
MUSOU_PREFIX = ["YELLOW TURBAN", "WEI", "SHU", "WU", "DONG ZHUO'S", "YUAN SHAO'S", "LU BU'S"]
MUSOU_RANK = ["FOOT SOLDIER", "SPEARMAN", "ARCHER", "GUARD", "BANNERMAN", "CAPTAIN"]

PREFIX = ["Mad", "Iron", "Red", "Wild", "Shadow", "Crazy", "Big", "Silent", "Dirty",
          "Stone", "Lucky", "Steel", "Mean", "Swift", "Rabid", "Grim"]

def make_grunt(rng, cfg, stage, level=None):
    """One rank-and-file fighter: character, name, moves, health."""
    g = SimpleNamespace(boss=False, car=False)
    g.cid = rng.choice(cfg["grunts"])
    if cfg.get("musou"):
        g.name = "%s %s" % (rng.choice(MUSOU_PREFIX), rng.choice(MUSOU_RANK))
    else:
        g.name = ("%s %s" % (rng.choice(PREFIX), CHAR_NAMES[g.cid])).upper()
    g.look = random_look(rng)
    # level 1-4 shown on the map: tougher and harder hitting
    g.level = level or rng.choices([1, 2, 3, 4], weights=cfg["weights"])[0]
    n = 1 if g.level == 1 else 2 if g.level == 4 else rng.choice([1, 2])
    g.moves = scale_damage(random_moveset(rng, n), 0.55 + 0.15 * g.level + 0.2 * min(stage, 2))
    size = {"small": 0.85, "slim": 0.9, "normal": 1.0, "big": 1.15, "huge": 1.3}[g.look["build"]]
    if cfg.get("musou"):
        g.hp = HIT if rng.random() < 0.5 else HIT * 2   # one or two hits
    else:
        g.hp = HIT * (cfg["grunt_hits"] + g.level)
    g.walk = round(rng.uniform(1.1, 1.8) / size ** 0.5, 2)
    g.ai = dict(aggression=rng.uniform(0.2, 0.7), block=rng.uniform(0.1, 0.5),
                jumpiness=rng.uniform(0.0, 0.4), reaction=rng.randint(4, 10))
    return g


class MapEnemy:
    def __init__(self, rng, x, y, boss=False, cfg=LEVELS[1], stage=1, index=0):
        self.x, self.y = float(x), float(y)
        self.home = (x, y)
        self.boss = boss
        self.car = False
        self.dir = "down"
        self.aware = False
        self.wander_t = 0
        self.vx = self.vy = 0.0
        self.anim = 0
        self.alive = True
        self.alert = 0
        if cfg.get("cars"):
            cars.setup_map_car(self, rng, boss, cfg, index)
            return
        if boss:
            self.name = cfg["boss_name"]
            self.cid = cfg["boss"]
            self.look = cfg["boss_look"]
            # dies to boss_hits normal hits, but hits several times harder than a grunt
            moves = boss_moveset(rng) if stage == 1 else boss2_moveset(rng)
            self.moves = scale_damage(moves, cfg["boss_dmg"])
            self.hp = HIT * cfg["boss_hits"]
            self.level = 5
            self.walk = 1.35 if stage == 1 else 1.55
            self.ai = dict(cfg["boss_ai"], boss=True)
            self.speed = 0.7 if stage == 1 else 0.85
            if cfg.get("musou"):
                # Lu Bu never rides out alone: his bodyguards come first
                self.allies = [make_grunt(rng, cfg, 2, 4) for _ in range(4)]
                for g in self.allies:
                    g.name = "LU BU'S BODYGUARD"
                    g.hp = HIT * 2
        else:
            self.__dict__.update(make_grunt(rng, cfg, stage).__dict__)
            # the rest of the squad this one leads into the fight
            lo, hi = cfg.get("squad", (1, 1))
            self.allies = [make_grunt(rng, cfg, stage, self.level) for _ in range(rng.randint(lo, hi) - 1)]
            self.speed = rng.uniform(0.6, 1.05)
        # same palette swap as in the fights, walking with the sheet's own stride
        self.map_art = MapArt(self.cid, MAP_SCALE * (1.15 if boss else 1.0))
        self.face = -1
        self.walked = 0.0

    def rect(self):
        s = 1.6 if self.boss else 1
        return pygame.Rect(self.x - 5 * s, self.y - 4 * s, 10 * s, 8 * s)


class Dungeon:
    def __init__(self, seed, rooms=13, area=(MAP_W, MAP_H)):
        self.rng = random.Random(seed)
        self.grid = [[WALL] * MAP_W for _ in range(MAP_H)]
        self.rooms = []
        self.n_rooms = rooms
        self.area = area
        self._generate()

    def _carve(self, r):
        for y in range(r.top, r.bottom):
            for x in range(r.left, r.right):
                self.grid[y][x] = FLOOR

    def _generate(self):
        rng = self.rng
        tries = 0
        aw, ah = self.area
        while len(self.rooms) < self.n_rooms and tries < 600:
            tries += 1
            big = len(self.rooms) == 0
            w = rng.randint(14, 16) if big else rng.randint(7, 12)
            h = rng.randint(10, 12) if big else rng.randint(6, 9)
            x = rng.randint(2, aw - w - 2)
            y = rng.randint(3, ah - h - 2)
            r = pygame.Rect(x, y, w, h)
            if any(r.inflate(4, 4).colliderect(o) for o in self.rooms):
                continue
            self.rooms.append(r)
        self.boss_room = self.rooms[0]
        # connect rooms in nearest-neighbour order so corridors stay short
        order = [self.rooms[0]]
        rest = self.rooms[1:]
        while rest:
            last = order[-1]
            nxt = min(rest, key=lambda o: abs(o.centerx - last.centerx) + abs(o.centery - last.centery))
            rest.remove(nxt)
            order.append(nxt)
        for r in self.rooms:
            self._carve(r)
        for a, b in zip(order, order[1:]):
            self._corridor(a.center, b.center)
        # a couple of extra loops make the map less linear
        for _ in range(2):
            a, b = rng.sample(self.rooms[1:], 2)
            self._corridor(a.center, b.center)
        # start = the room farthest from the boss room along the chain
        self.start_room = order[-1]

    def _corridor(self, a, b):
        (x1, y1), (x2, y2) = a, b
        if self.rng.random() < 0.5:
            self._h(x1, x2, y1)
            self._v(y1, y2, x2)
        else:
            self._v(y1, y2, x1)
            self._h(x1, x2, y2)

    def _h(self, x1, x2, y):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for yy in (y, y + 1):
                if 1 <= yy < MAP_H - 1 and 1 <= x < MAP_W - 1:
                    self.grid[yy][x] = FLOOR

    def _v(self, y1, y2, x):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            for xx in (x, x + 1):
                if 1 <= y < MAP_H - 1 and 1 <= xx < MAP_W - 1:
                    self.grid[y][xx] = FLOOR

    def solid(self, tx, ty):
        if tx < 0 or ty < 0 or tx >= MAP_W or ty >= MAP_H:
            return True
        return self.grid[ty][tx] == WALL

    def rect_hits_wall(self, r):
        for ty in range(r.top // TILE, (r.bottom - 1) // TILE + 1):
            for tx in range(r.left // TILE, (r.right - 1) // TILE + 1):
                if self.solid(tx, ty):
                    return True
        return False

    def line_of_sight(self, x0, y0, x1, y1):
        d = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(d / 6))
        for i in range(n + 1):
            t = i / n
            if self.solid(int((x0 + (x1 - x0) * t) // TILE), int((y0 + (y1 - y0) * t) // TILE)):
                return False
        return True

    def random_floor_in(self, r, margin=1):
        return ((self.rng.randint(r.left + margin, r.right - 1 - margin) + 0.5) * TILE,
                (self.rng.randint(r.top + margin, r.bottom - 1 - margin) + 0.5) * TILE)


class Overworld:
    def __init__(self, game, seed, level=1):
        self.game = game
        self.seed = seed
        self.level = level
        self.cfg = cfg = LEVELS[level]
        self.dg = Dungeon(seed, cfg.get("rooms", 13), cfg.get("area", (MAP_W, MAP_H)))
        rng = self.dg.rng
        self.tiles = make_tiles(seed, level)
        if cfg.get("cars"):
            cars.car_tiles(self.tiles, random.Random(seed))
        self.akuma_art = MapArt()
        self.pface = 1
        self.pvx = self.pvy = 0.0
        self.walked = 0.0
        sr = self.dg.start_room
        self.px, self.py = (sr.centerx + 0.5) * TILE, (sr.centery + 0.5) * TILE
        self.pdir = "down"
        self.anim = 0
        self.moving = False
        self.hp = game.akuma_max
        self.invuln = 60
        self.enemies = []
        rooms = [r for r in self.dg.rooms if r is not sr and r is not self.dg.boss_room]
        rng.shuffle(rooms)
        i = 0
        while len(self.enemies) < cfg["enemies"]:
            r = rooms[i % len(rooms)]
            i += 1
            x, y = self.dg.random_floor_in(r)
            self.enemies.append(MapEnemy(rng, x, y, cfg=cfg, stage=level, index=len(self.enemies)))
        br = self.dg.boss_room
        self.boss = MapEnemy(rng, (br.centerx + 0.5) * TILE, (br.top + 2.5) * TILE, boss=True,
                             cfg=cfg, stage=level)
        self.enemies.append(self.boss)
        self.throne = ((br.centerx - 0.5) * TILE, (br.top + 0.6) * TILE)
        # pickups
        self.pickups = []
        for k, r in enumerate(rooms[:7]):
            x, y = self.dg.random_floor_in(r)
            self.pickups.append(["orb" if k < 2 else "onigiri", x, y])
        # explored map
        self.seen = [[False] * MAP_W for _ in range(MAP_H)]
        self._render_map()
        self.light = self._make_light(110)
        self.small_light = self._make_light(36)
        self.encounter = None
        self.encounter_t = 0
        self.messages = []
        self.message("LEVEL %d: %s" % (level, cfg["name"]), 150)
        self.message(("WRECK %s" if cfg.get("cars") else "DEFEAT %s") % cfg["boss_name"], 150)
        if cfg.get("musou"):
            self.message("DON'T PURSUE LU BU!", 150)
            game.musou_kos = 0
            game.musou_gauge = 0.0
        self.menu = PauseMenu(game, [MAP_LINE] + CONTROLS)
        self.steps = 0

    # ------------------------------------------------------------------
    def message(self, text, frames=120):
        self.messages.append([text, frames])

    def _render_map(self):
        g = self.dg.grid
        rng = random.Random(self.seed + 5)
        surf = pygame.Surface((MAP_W * TILE, MAP_H * TILE))
        self.torches = []
        decor = []
        for ty in range(MAP_H):
            for tx in range(MAP_W):
                x, y = tx * TILE, ty * TILE
                if g[ty][tx] == FLOOR:
                    surf.blit(self.tiles["floor"][rng.choice((0, 0, 1, 1, 2, 3))], (x, y))
                    if ty > 0 and g[ty - 1][tx] == WALL:
                        surf.blit(self.tiles["shadow"], (x, y))
                    if rng.random() < 0.03:
                        decor.append((rng.choice(("bones", "rubble", "rubble", "lantern")), x, y))
                else:
                    below_floor = ty + 1 < MAP_H and g[ty + 1][tx] == FLOOR
                    if below_floor:
                        surf.blit(self.tiles["wall_face"], (x, y))
                        if rng.random() < 0.14:
                            self.torches.append((x, y))
                    else:
                        surf.blit(self.tiles["wall_top"], (x, y))
        for kind, x, y in decor:
            surf.blit(self.tiles[kind], (x, y))
        surf.blit(self.tiles["throne"], self.throne)
        self.map_surf = surf

    @staticmethod
    def _make_light(radius):
        s = pygame.Surface((radius * 2, radius * 2))
        s.fill((0, 0, 0))
        steps = 8
        for i in range(steps, 0, -1):
            r = int(radius * i / steps)
            v = int(255 * (1 - (i - 1) / steps) ** 0.8)
            pygame.draw.circle(s, (v, int(v * 0.92), int(v * 0.85)), (radius, radius), r)
        return s

    # ------------------------------------------------------------------
    def update(self, inp):
        if self.encounter:
            self.encounter_t += 1
            if self.encounter_t >= 14:
                e, ambush = self.encounter
                self.encounter = None
                self.game.start_fight(e, self.hp, ambush)
            return
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.menu.toggle(inp):
            return
        self.anim += 1
        for m in self.messages[:1]:
            m[1] -= 1
        self.messages = [m for m in self.messages if m[1] > 0]
        if self.invuln:
            self.invuln -= 1
        # --- player movement (axis separated for clean wall sliding) ---
        dx = (1 if inp.held("right") else 0) - (1 if inp.held("left") else 0)
        dy = (1 if inp.held("down") else 0) - (1 if inp.held("up") else 0)
        sp = PLAYER_SPEED * (0.7071 if dx and dy else 1)
        # ease into and out of a walk instead of starting and stopping dead
        self.pvx += (dx * sp - self.pvx) * 0.3
        self.pvy += (dy * sp - self.pvy) * 0.3
        if not dx and abs(self.pvx) < 0.05:
            self.pvx = 0.0
        if not dy and abs(self.pvy) < 0.05:
            self.pvy = 0.0
        moved = 0.0
        if self.pvx or self.pvy:
            ox, oy = self.px, self.py
            self._move_player(self.pvx, 0)
            self._move_player(0, self.pvy)
            moved = math.hypot(self.px - ox, self.py - oy)
            self.walked += moved
        self.moving = moved > 0.25
        if dx:
            self.pface = dx
        if self.moving:
            self.steps += 1
            if self.steps % 18 == 0:
                audio.play("step", 0.5)
        self._reveal()
        # --- pickups ---
        prect = self.player_rect()
        for pk in self.pickups[:]:
            if prect.colliderect(pygame.Rect(pk[1] - 6, pk[2] - 6, 12, 12)):
                self.pickups.remove(pk)
                audio.play("pickup")
                if pk[0] == "onigiri" and self.cfg.get("nidhogg"):
                    heart = self.game.akuma_max / HEARTS
                    self.hp = min(self.game.akuma_max, self.hp + heart)
                    self.message("ONIGIRI! +1 HEART", 90)
                elif pk[0] == "onigiri":
                    heal = min(40, self.game.akuma_max - self.hp)
                    self.hp += heal
                    self.message("ONIGIRI! +%d HP" % heal, 90)
                else:
                    self.game.akuma_max += 15
                    self.hp = min(self.game.akuma_max, self.hp + 15)
                    self.game.power += 0.1
                    self.message("SATSUI ORB! POWER UP", 90)
        # --- enemies ---
        for e in self.enemies:
            if e.alive:
                self._update_enemy(e)
        if not self.invuln:
            for e in self.enemies:
                if e.alive and prect.colliderect(e.rect()):
                    ambush = not e.aware
                    self.encounter = (e, ambush)
                    self.encounter_t = 0
                    audio.play("encounter")
                    break

    def player_rect(self):
        return pygame.Rect(round(self.px) - 5, round(self.py) - 4, 10, 8)

    def _move_player(self, dx, dy):
        nx, ny = self.px + dx, self.py + dy
        r = pygame.Rect(round(nx) - 5, round(ny) - 4, 10, 8)
        if not self.dg.rect_hits_wall(r):
            self.px, self.py = nx, ny
            return
        # corner assist: nudge around corners so movement never feels sticky
        for nudge in (1, -1, 2, -2, 3, -3):
            if dx:
                r2 = r.move(0, nudge)
            else:
                r2 = r.move(nudge, 0)
            if not self.dg.rect_hits_wall(r2):
                if dx:
                    self.py += nudge * 0.5
                else:
                    self.px += nudge * 0.5
                return

    def _reveal(self):
        tx, ty = int(self.px // TILE), int(self.py // TILE)
        for y in range(max(0, ty - 6), min(MAP_H, ty + 7)):
            row = self.seen[y]
            for x in range(max(0, tx - 8), min(MAP_W, tx + 9)):
                row[x] = True

    def _update_enemy(self, e):
        if e.car:
            cars.drive(e, self.dg, self.dg.rng)
            return
        e.anim += 1
        d = math.hypot(self.px - e.x, self.py - e.y)
        sees = d < (80 if e.boss else 96) and self.dg.line_of_sight(e.x, e.y, self.px, self.py)
        if sees and not e.aware:
            e.aware = True
            e.alert = 40
        elif e.aware and d > 170:
            e.aware = False
        if e.alert:
            e.alert -= 1
        if e.aware and not self.invuln:
            if e.alert > 25:
                vx = vy = 0  # "!" pause before the chase
            else:
                vx = (self.px - e.x) / max(d, 1) * e.speed
                vy = (self.py - e.y) / max(d, 1) * e.speed
        elif e.boss:
            vx = vy = 0
        else:
            e.wander_t -= 1
            if e.wander_t <= 0:
                e.wander_t = self.dg.rng.randint(40, 120)
                if self.dg.rng.random() < 0.4:
                    e.vx = e.vy = 0
                else:
                    a = self.dg.rng.uniform(0, math.tau)
                    e.vx, e.vy = math.cos(a) * 0.45, math.sin(a) * 0.45
            vx, vy = e.vx, e.vy
            hx, hy = e.home
            if math.hypot(e.x - hx, e.y - hy) > 56:
                vx = (hx - e.x) / 60
                vy = (hy - e.y) / 60
        for ax, ay in ((vx, 0), (0, vy)):
            if not ax and not ay:
                continue
            e.x += ax
            e.y += ay
            if self.dg.rect_hits_wall(e.rect()):
                e.x -= ax
                e.y -= ay
                if not e.aware:
                    e.wander_t = 0
        if abs(vx) > abs(vy):
            e.dir = "right" if vx > 0 else "left"
        elif vy:
            e.dir = "down" if vy > 0 else "up"
        e.moving = bool(vx or vy)
        if abs(vx) > 0.05:
            e.face = 1 if vx > 0 else -1
        e.walked += math.hypot(vx, vy)

    def after_fight(self, result, hp, enemy):
        self.hp = hp
        if result == "escape":      # a car outlasted the timer and drove off
            enemy.alive = False
            self.message("THE %s GOT AWAY" % enemy.name, 100)
            self.invuln = 90
        if result == "win":
            enemy.alive = False
            # fights are longer now; heal a bit more (level 11's hearts only come from onigiri)
            heal = 0 if self.cfg.get("nidhogg") else int(self.game.akuma_max * 0.25)
            self.hp = min(self.game.akuma_max, self.hp + heal)
            left = sum(1 for e in self.enemies if e.alive and not e.boss)
            self.message("%s %s" % (enemy.name, "WRECKED" if enemy.car else "DEFEATED"), 100)
            if left:
                self.message("%d FOES REMAIN" % left, 80)
            self.invuln = 90

    # ------------------------------------------------------------------
    def camera(self):
        cx = int(self.px - W / 2)
        cy = int(self.py - H / 2)
        cx = max(0, min(MAP_W * TILE - W, cx))
        cy = max(0, min(MAP_H * TILE - H, cy))
        return cx, cy

    def draw(self, surf):
        cx, cy = self.camera()
        surf.blit(self.map_surf, (0, 0), (cx, cy, W, H))
        view = pygame.Rect(cx - 16, cy - 16, W + 32, H + 32)
        fl = self.tiles["torch"][(self.anim // 6) % 3]
        for tx, ty in self.torches:
            if view.collidepoint(tx, ty):
                surf.blit(fl, (tx - cx, ty - cy))
        for kind, x, y in self.pickups:
            if view.collidepoint(x, y):
                img = self.tiles["orb"][(self.anim // 8) % 4] if kind == "orb" else self.tiles["onigiri"]
                bob = int(math.sin(self.anim / 10) * 2)
                surf.blit(img, (round(x - 6 - cx), round(y - 8 - cy + bob)))
        # y-sorted actors
        actors = [(self.py, "p", None)]
        for e in self.enemies:
            if e.alive and view.collidepoint(e.x, e.y):
                actors.append((e.y, "e", e))
        actors.sort(key=lambda a: a[0])
        for _, kind, e in actors:
            if kind == "p":
                if self.invuln and (self.invuln // 4) % 2:
                    continue
                img, (ax, ay) = self.akuma_art.frame(self.pface, self.moving, self.walked, self.anim)
                pygame.draw.ellipse(surf, (16, 12, 20), (round(self.px) - 7 - cx, round(self.py) - cy - 1, 14, 4))
                surf.blit(img, (round(self.px) - ax - cx, round(self.py) - ay + 2 - cy))
            else:
                if e.car:
                    img = e.frames[(e.dir, 0)]
                    w, h = img.get_size()
                    pygame.draw.ellipse(surf, (16, 12, 20), (round(e.x) - w // 2 - cx, round(e.y) + h // 2 - 4 - cy, w, 5))
                    surf.blit(img, (round(e.x) - w // 2 - cx, round(e.y) - h // 2 - cy))
                    continue
                img, (ax, ay) = e.map_art.frame(e.face, getattr(e, "moving", False), e.walked, e.anim)
                w, h = img.get_size()
                pygame.draw.ellipse(surf, (16, 12, 20), (round(e.x) - w // 3 - cx, round(e.y) - cy - 2, w * 2 // 3, 5))
                surf.blit(img, (round(e.x) - ax - cx, round(e.y) - ay + 2 - cy))
                top = round(e.y) - ay - cy
                if not e.boss:
                    lc = ((140, 230, 140), (240, 230, 120), (255, 160, 60), (255, 70, 60))[e.level - 1]
                    draw_text(surf, str(e.level), round(e.x) - cx, top - 7, lc, align="center")
                if e.alert:
                    draw_text(surf, "!", round(e.x) - cx, top - 16, (255, 60, 40), align="center")
        self._lighting(surf, cx, cy, view)
        self._hud(surf)
        if self.encounter:
            self._encounter_fx(surf)

    def _lighting(self, surf, cx, cy, view):
        dark = pygame.Surface((W, H))
        dark.fill(self.cfg["ambient"])
        r = self.light.get_width() // 2
        flick = (self.anim // 5) % 2
        dark.blit(self.light, (round(self.px) - cx - r, round(self.py) - 8 - cy - r),
                  special_flags=pygame.BLEND_RGB_MAX)
        sr = self.small_light.get_width() // 2
        for tx, ty in self.torches:
            if view.collidepoint(tx, ty):
                dark.blit(self.small_light, (tx + 8 - cx - sr, ty + 4 - cy - sr + flick),
                          special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(dark, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    def _hud(self, surf):
        mx = self.game.akuma_max
        if self.cfg.get("nidhogg"):
            from .nidhogg import draw_heart
            hearts = math.ceil(self.hp / (mx / HEARTS) - 1e-6)
            for i in range(HEARTS):
                draw_heart(surf, 6 + i * 10, 6, i < hearts)
            draw_text(surf, "AKUMA", 6, 15, (255, 120, 120))
        else:
            pygame.draw.rect(surf, (10, 6, 14), (5, 5, 82, 8))
            pygame.draw.rect(surf, (90, 16, 20), (6, 6, 80, 6))
            pygame.draw.rect(surf, (250, 210, 40), (6, 6, int(80 * self.hp / mx), 6))
            draw_text(surf, "AKUMA %d/%d" % (self.hp, mx), 6, 15, (255, 120, 120))
        left = sum(1 for e in self.enemies if e.alive and not e.boss)
        draw_text(surf, "%s %d" % ("CARS" if self.cfg.get("cars") else "FOES", left), 6, 24, (200, 200, 220))
        if self.game.power > 1.0:
            draw_text(surf, "POWER x%.1f" % self.game.power, 6, 33, (255, 120, 200))
        # minimap
        ox, oy = W - MAP_W - 4, 4
        mm = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
        mm.fill((0, 0, 0, 120))
        g = self.dg.grid
        for y in range(MAP_H):
            row, srow = g[y], self.seen[y]
            for x in range(MAP_W):
                if srow[x] and row[x] == FLOOR:
                    mm.set_at((x, y), (110, 100, 130, 220))
        for e in self.enemies:
            if e.alive:
                tx, ty = int(e.x // TILE), int(e.y // TILE)
                if self.seen[ty][tx]:
                    mm.fill((255, 200, 40) if e.boss else (230, 60, 60), (tx, ty, 2 if e.boss else 1, 2 if e.boss else 1))
        mm.fill((255, 255, 255), (int(self.px // TILE), int(self.py // TILE), 1, 1))
        surf.blit(mm, (ox, oy))
        pygame.draw.rect(surf, (20, 14, 26), (ox - 1, oy - 1, MAP_W + 2, MAP_H + 2), 1)
        if self.messages:
            text = self.messages[0][0]
            draw_text(surf, text, W // 2, H - 18, (255, 230, 150), align="center")
        if self.menu.open:
            self.menu.draw(surf)

    def _encounter_fx(self, surf):
        t = self.encounter_t
        if t < 4 and t % 2 == 0:
            surf.fill((255, 255, 255))
            return
        # shattering bars wipe
        n = 12
        bh = H // n + 1
        prog = max(0, (t - 3) / 10)
        for i in range(n):
            w = int(W * min(1, prog * 1.6 - (i % 3) * 0.15))
            if w <= 0:
                continue
            if i % 2:
                pygame.draw.rect(surf, (10, 4, 12), (W - w, i * bh, w, bh))
            else:
                pygame.draw.rect(surf, (10, 4, 12), (0, i * bh, w, bh))
