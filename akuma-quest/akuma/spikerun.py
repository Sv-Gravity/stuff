"""Level 11, round 2 of The Climb: THE SPIKE RUN, a side-scrolling race.

Whoever wins the tower race (climb.py) moves on here with the same four
rivals. A huge wall of spikes grinds in from the left and never stops, a
little faster as time goes on; touch it and you are out of the try. The
course runs left to right on three lanes (a high, a middle and a low one)
that braid into each other: they split into a fast risky top route, a middle
one with walls and swinging hammers, and a slow safe bottom one with crushers,
spike strips and backward belts, then cross over in X-shaped staircases and
squeeze together on big arena platforms, so the racers keep running into each
other and fighting. ? boxes hand out snacks (heal %) or a star.

Same fighters, moves and damage % as the tower. Fall off the bottom and you
come back just ahead of the spikes with a moment of invincibility; knock a
rival back into the spikes and they're out. First through the gate at the
far right wins. Three tries; win one to clear the level.
"""

import math
import random

import pygame

from . import audio
from . import climb as C
from . import smash as S
from .art import shade, mix, OUTLINE
from .config import W, H
from .font import draw_text, text_width
from .pause import PauseMenu
from .snacks import random_snack

LEVEL_NAME = "THE SPIKE RUN"

# the camera shows this much of the world, scaled down to the canvas: all three lanes at once
VW, VH = 384, 216
TOP, MID, LOW = 56, 112, 168            # the three lanes (platform tops)
TRIES = 3
WALL_X0 = -70.0                         # where the spikes start
WALL_V = 0.85                           # their speed (px/frame) at GO ...
WALL_ACC = 0.00006                      # ... picking up this much every frame
WALL_GRACE = 90                         # frames after GO before the wall moves
FALL_Y = VH + 30                        # below this you've fallen off
RESPAWN_AHEAD = 96                      # how far in front of the spikes you come back
RESPAWN_INVULN = 120
INTRO = 290
FLY = 180
STAR_TIME = 6 * 60
QBOX_COOL = 8 * 60

CRUSH_HIT = dict(dmg=10, kb=4.2, kg=2.6, ang=70)
SPIKE_HIT = dict(dmg=8, kb=5.4, kg=1.4, ang=82)
BALL_HIT = dict(dmg=4, kb=2.8, kg=2.4, ang=30)

CONTROLS = [
    "OUTRUN THE SPIKE WALL TO THE GATE!",
    "LEFT / RIGHT: MOVE   UP: JUMP (TWICE)",
    "DOWN: CROUCH / DROP TO THE LANE BELOW",
    "J: JAB   K: KICK   DOWN+K: SWEEP",
    "L: HADOUKEN   L+J: SHORYUKEN",
    "L+K: HURRICANE KICK   I: SHIELD",
    "I+J OR J+K: GRAB",
    "? BOXES: SNACKS AND STARS",
    "TOUCH THE SPIKES AND YOU'RE OUT",
    "3 TRIES: WIN ONE TO CLEAR",
]


# --------------------------------------------------------------------------
# obstacles of the run (the tower's sweepers and hammers come along too)
# --------------------------------------------------------------------------
class Crusher:
    """A heavy block hanging under a lane that slams down onto the one below."""
    kind = "crusher"

    def __init__(self, x, w, top, floor, period=170, phase=0):
        self.x, self.w, self.top, self.floor = float(x), w, float(top), float(floor)
        self.h = 24
        self.period, self.phase = period, phase
        self.y = floor
        self.t = 0

    def update(self, t):
        self.t = t
        if (t + self.phase) % self.period == 98:
            audio.play("land", 0.9)

    def bottom(self, t=None):
        """(the block's lower edge, whether it is slamming)."""
        k = ((self.t if t is None else t) + self.phase) % self.period
        hi, lo = self.top + self.h, self.floor
        if k < 90:                                   # up (shaking for the last 20)
            return hi, False
        if k < 98:                                   # SLAM
            return hi + (lo - hi) * (k - 89) / 9, True
        if k < 140:
            return lo, k < 104
        return lo + (hi - lo) * (k - 140) / 30, False

    def shaking(self):
        k = (self.t + self.phase) % self.period
        return 70 <= k < 90

    def hit(self, box, t=None):
        b, slam = self.bottom(t)
        if not slam:
            return None
        x0, y0, x1, y1 = box
        if x1 > self.x and x0 < self.x + self.w and y1 > b - self.h and y0 < b:
            d = 1 if (x0 + x1) / 2 > self.x + self.w / 2 else -1
            return CRUSH_HIT, d, ((x0 + x1) / 2, b)
        return None


class Spikes:
    """A strip of spikes along a floor: they bounce you up and forward."""
    kind = "spikes"

    def __init__(self, x0, x1, y):
        self.x0, self.x1, self.y = float(x0), float(x1), float(y)

    def update(self, t):
        pass

    def hit(self, box, t=None):
        x0, y0, x1, y1 = box
        if x1 > self.x0 + 2 and x0 < self.x1 - 2 and self.y - 7 < y1 <= self.y + 1:
            return SPIKE_HIT, 1, ((x0 + x1) / 2, self.y - 3)
        return None


class Gun:
    """A cannon on a post that lobs fruit back toward the spikes."""
    kind = "cannon"
    FRUITS = ("orange", "melon", "apple")

    def __init__(self, x, y, period=120, phase=0, speed=2.2, reach=300):
        self.x, self.y = float(x), float(y)
        self.period, self.phase, self.speed, self.reach = period, phase, speed, reach
        self.balls = []
        self.recoil = 0
        self.t = 0

    def update(self, t):
        self.t = t
        if (t + self.phase) % self.period == 0:
            self.balls.append([self.x - 10, self.y - 7, -self.speed, self.FRUITS[(t // self.period) % 3], 0])
            self.recoil = 8
        if self.recoil:
            self.recoil -= 1
        for b in self.balls:
            b[0] += b[2]
            b[4] += 1
        self.balls = [b for b in self.balls if self.x - self.reach < b[0]]

    def hit(self, box, t=None):
        k = 0 if t is None else t - self.t
        x0, y0, x1, y1 = box
        for b in self.balls:
            bx = b[0] + b[2] * k
            if bx < self.x - self.reach:
                continue
            nx, ny = max(x0, min(x1, bx)), max(y0, min(y1, b[1]))
            if (nx - bx) ** 2 + (ny - b[1]) ** 2 <= 36:
                return BALL_HIT, (1 if b[2] > 0 else -1), (nx, ny)
        return None


def _at(h, y):
    """Put a tower obstacle (built from a rise) at a world y instead."""
    h.y = float(y)
    return h


class QBox:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.cool = 0
        self.bump = 0

    @property
    def rect(self):
        return pygame.Rect(round(self.x) - 6, round(self.y) - 6 - (2 if self.bump else 0), 12, 12)


class RunPlat(C.Plat):
    def __init__(self, x0, x1, y, kind="static", **kw):
        super().__init__(x0, x1, 0, kind, **kw)
        self.by = float(y)
        self.at(0)
        self.at(0)


# --------------------------------------------------------------------------
# the course: three lanes braiding left to right
# --------------------------------------------------------------------------
PATTERN = ["split", "cross", "split", "arena", "split", "cross", "split", "arena", "split"]


def build_run(rng):
    """(platforms, obstacles, walls, ? boxes, gate x, course length)."""
    P, hz, solids, boxes = [], [], [], []

    def plat(x0, x1, y, kind="static", **kw):
        P.append(RunPlat(x0, x1, y, kind, **kw))
        return P[-1]

    def ground(x0, x1, **kw):
        kw.setdefault("col", C.MINT)
        return plat(x0, x1, LOW, "floor", **kw)

    def wall(x, floor, w=16, h=20):
        plat(x, x + w, floor - h, "block", col=(150, 130, 170), ledges=False, nodrop=True)
        solids.append(pygame.Rect(x, floor - h, w, h))

    cols = [C.PINK, C.YELLOW, C.BLUE, C.ORANGE, C.PURPLE]

    def split(x, w=420):
        # top: short hops over gaps, a sweeper halfway (fast and risky)
        cx = x
        while cx < x + w - 70:
            pw = rng.randint(42, 62)
            plat(cx, cx + pw, TOP + rng.choice((-8, 0, 0, 6)), col=rng.choice(cols))
            cx += pw + rng.randint(30, 44)
        plat(cx, x + w, TOP, col=rng.choice(cols))
        if rng.random() < 0.7:
            hz.append(_at(C.Sweeper(x + w * rng.uniform(0.35, 0.65), 0, 30, rng.choice((0.03, -0.03))), TOP - 56))
        # middle: a wall to vault and a swinging hammer
        a = rng.randint(160, 200)
        plat(x, x + a, MID, col=C.BLUE)
        wall(x + a // 2 + rng.randint(-20, 20), MID)
        plat(x + a + 34, x + w, MID, col=C.YELLOW)
        # it swings over the gap, just above head height: time the jump across
        hz.append(_at(C.Pendulum(x + a + 17, 0, 56, 0.7, rng.randint(130, 170),
                                 phase=rng.uniform(0, 6)), MID - 108))
        # bottom: belt that drags you back, spikes, a crusher and a pit to jump
        b = rng.randint(130, 170)
        ground(x, x + b)
        plat(x + b, x + b + 90, LOW, "floor", col=C.PURPLE, belt=-0.45)
        P[-1].kind, P[-1].belt = "belt", -0.45
        P[-1].nodrop = True
        ground(x + b + 90, x + b + 170)
        hz.append(Spikes(x + b + 110, x + b + 140, LOW))
        gap = rng.randint(34, 42)
        ground(x + b + 170 + gap, x + w)
        hz.append(Crusher(x + w - 70, 30, MID + 8, LOW, period=rng.randint(150, 190), phase=rng.randint(0, 150)))
        return x + w

    def cross(x, w=360):
        # an X of stairs: the top lane steps down to the bottom while the bottom one climbs to the top
        n, dx = 6, 56
        for k in range(n):
            y = TOP + (LOW - TOP) * k / (n - 1)
            if 0 < k < n - 1:
                plat(x + 8 + k * dx, x + 8 + k * dx + 40, y, col=C.ORANGE)
            y2 = LOW - (LOW - TOP) * k / (n - 1)
            if 0 < k < n - 1:
                plat(x + 34 + k * dx, x + 34 + k * dx + 40, y2, col=C.PINK)
        plat(x, x + 48, TOP, col=C.ORANGE)
        plat(x + 34 + (n - 1) * dx, x + w, TOP, col=C.PINK)
        ground(x, x + w)
        plat(x, x + 40, MID, col=C.BLUE)
        plat(x + w - 40, x + w, MID, col=C.BLUE)
        boxes.append(QBox(x + w / 2, MID - 46))
        hz.append(Gun(x + w - 10, LOW, period=rng.randint(110, 140), phase=rng.randint(0, 100), reach=230))
        return x + w

    def arena(x, w=330):
        # everyone squeezed onto one big platform: the low road is all spikes
        # (the high road stops here: everyone drops in, and climbs back out at the far end)
        plat(x, x + 70, TOP, col=C.YELLOW)
        plat(x + w - 70, x + w, TOP, col=C.YELLOW)
        plat(x + 24, x + w - 24, MID, col=C.GOLD if False else C.ORANGE, nodrop=True)
        ground(x, x + w)
        plat(x + 8, x + 34, LOW - 2, "bounce", col=(90, 220, 90))
        hz.append(Spikes(x + 50, x + w - 40, LOW))
        boxes.append(QBox(x + w / 2, MID - 46))
        if rng.random() < 0.6:
            hz.append(_at(C.Sweeper(x + w / 2, 0, 40, rng.choice((0.025, -0.025))), MID - 70))
        return x + w

    # the start: a wide pad on the middle lane, with the other lanes starting just ahead
    plat(-200, 330, MID, col=C.MINT, nodrop=True, ledges=False)
    ground(-200, 340)
    plat(250, 330, TOP, col=C.PINK)
    x = 340
    for kind in PATTERN:
        x = {"split": split, "cross": cross, "arena": arena}[kind](x)
    # the finish: all lanes funnel onto the gate platform
    plat(x, x + 60, TOP, col=C.YELLOW)
    ground(x, x + 120)
    plat(x + 30, x + 56, LOW - 2, "bounce", col=(90, 220, 90))
    fin = plat(x + 40, x + 420, MID, "finish", col=C.GOLD)
    fin.nodrop = True
    gate = x + 300
    for i, p in enumerate(P):
        p.idx = i
    return P, hz, solids, boxes, gate, x + 420


class RunShot(C.ClimbShot):
    def update(self):
        self.t += 1
        self.x += self.vx
        self.y += self.vy
        self.vy += self.grav
        if self.t >= self.life or self.y > FALL_Y:
            self.alive = False


# --------------------------------------------------------------------------
# CPU racers: run right, pick a lane, jump what's in the way
# --------------------------------------------------------------------------
class RunBrain(C.ClimbBrain):
    def __init__(self, scene, me, rng, skill=1.0):
        super().__init__(scene, me, rng, skill)
        self.high = rng.uniform(-0.3, 0.3) + (skill - 0.8)    # likes the high routes (risky) or not
        self.lane_t = rng.randint(20, 60)

    def _cands(self, y, x=None):
        x = self.me.x if x is None else x
        t = self.sc.course_t
        return [p for p in self.sc.plats if p.active(t) and p.x1 > x - 30 and p.x0 < x + 260
                and y - 150 < p.y < y + 240]

    def _score(self, p):
        return min(p.x1, p.x0 + 260) + self.high * (MID - p.y) * 0.6

    def _aim(self, goal):
        """Land early on the platform, but never behind where we are now."""
        gx = max(goal.x0 + min(goal.w * 0.5, 26), self.me.x + 14)
        gx = max(goal.x0 + 4, min(goal.x1 - 6, gx))
        self.aim = (gx - goal.x0) / max(1.0, goal.w) - 0.5

    def _options(self, cur, walk_off):
        """The best jump (or walk off the end) from here: (score, platform, dj, how) or None."""
        me = self.me
        cands = self._cands(me.y)
        hz = self._hazards(me.y)
        here = self._score(cur)
        goals = [p for p in cands if p is not cur and self._score(p) > here + 6]
        goals.sort(key=lambda p: -self._score(p))
        best = None
        for goal in goals[:4]:
            self._aim(goal)
            for dj in (None, 6, 12, 18, 24):
                hit = self.simulate(me.x, me.y, me.vx, 0.0, 1, False, goal, dj, cands, hazards=hz)
                if hit is not None and hit is not cur and self._score(hit) > here + 6:
                    sc = self._score(hit)
                    if best is None or sc > best[0]:
                        best = (sc, hit, dj, "jump")
                    break
            if walk_off:
                hit = self.simulate(cur.x1 + 2, me.y, me.walk, 0.0, 1, True, goal, None, cands, hazards=hz)
                if hit is not None and hit is not cur and self._score(hit) > here + 6:
                    sc = self._score(hit) + 4                # no jump needed: slightly better
                    if best is None or sc > best[0]:
                        best = (sc, hit, None, "walk")
            if best is not None and best[1] is goal:
                break
        return best

    def _dodge(self, cur):
        """The tower's dodge, but floor spikes don't move and fruit can't be outrun: hop those."""
        me, hz = self.me, self.sc.hazards
        guns = [h for h in hz if h.kind == "cannon" and abs(h.y - me.y) < 40]
        if guns and self.rng.random() < 0.5 + 0.5 * self.skill and self._hurts(me.x, guns, (7, 9, 11)):
            return 0
        self.sc.hazards = [h for h in hz if h.kind not in ("spikes", "cannon")]
        try:
            return super()._dodge(cur)
        finally:
            self.sc.hazards = hz

    def _blocker(self, cur):
        """The nearest wall or spike strip in our way on this floor: (left edge, vault-to x) or None."""
        me, best = self.me, None
        for r in self.sc.solids:
            if 0 <= r.left - me.x < 24 and r.top < me.y <= r.bottom + 1:
                best = min(best or (r.left, r.right + 24), (r.left, r.right + 24))
        for h in self.sc.hazards:
            if h.kind == "spikes" and abs(h.y - me.y) < 2 and 0 <= h.x0 - me.x < 26 and h.x1 - h.x0 < 70:
                best = min(best or (h.x0, h.x1 + 20), (h.x0, h.x1 + 20))
        return best

    def _path_clear(self, edge):
        """Nothing that swings, slams or flies is about to meet us if we walk on."""
        me, t = self.me, self.sc.course_t
        hz = [h for h in self.sc.hazards if h.kind not in ("spikes", "cannon") and abs(h.y - me.y) < 110]
        if not hz:
            return True
        for k in range(4, 76, 4):
            x = me.x + me.walk * k
            if x > edge + me.half_w:
                break                           # off the end: the jump planner's job
            box = (x - me.half_w, me.y - me.hgt, x + me.half_w, me.y)
            if any(h.hit(box, t + k) is not None for h in hz):
                return False
        return True

    def _air_plan(self):
        me = self.me
        cands = self._cands(me.y)
        best = None
        for goal in sorted(cands, key=lambda p: -self._score(p))[:5]:
            self._aim(goal)
            for dj in ((None, 1, 6, 12) if me.jumps else (None,)):
                hit = self.simulate(me.x, me.y, me.vx + me.lvx, me.vy + me.lvy, me.jumps, True, goal, dj, cands)
                if hit is not None and (best is None or self._score(hit) > self._score(best[0])):
                    best = (hit, dj)
            if best is not None and best[0] is goal:
                break
        return best

    def _think(self):
        me, rng, sc = self.me, self.rng, self.sc
        it = S.Intent()
        if me.out or me.state in ("dead", "intro", "win") or me.done:
            return it
        if self.cool:
            self.cool -= 1
        if me.state == "prejump":
            it.up = True
            return it
        if self._shielding(it):
            return it
        if self._fight(it):
            return it
        if me.state not in ("stand", "air"):
            return it
        if me.airborne:
            return self._fly(it)
        self.plan = None
        cur = me.on
        if cur is None:
            return it
        if cur is not self.stood:
            self.stood = cur
            self.settle = int(rng.randint(3, 14) * (1.6 - self.skill))
        dodge = self._dodge(cur)
        if dodge == 0:
            it.up_p = it.up = True
            self.plan = dict(goal=cur, dj=None, t=0)
            return it
        if dodge is not None:
            it.left, it.right = dodge < 0, dodge > 0
            return it
        if self.dawdle:
            self.dawdle -= 1
            return it
        lazy = 0.003 * (1.6 - self.skill)
        if me.x - sc.akuma.x > 420:
            lazy *= 4
        if rng.random() < lazy:
            self.dawdle = rng.randint(8, 30)
        # how far can we walk: the end of this platform, or a wall in the way
        edge, blocked = cur.x1, False
        blocker = self._blocker(cur)
        if blocker is not None and blocker[0] < edge:
            edge, blocked = blocker[0], True
        near = me.x > edge - 20
        danger = sc.wall_x > me.x - 70
        self.lane_t -= 1
        self.think_t -= 1
        if blocked and near and not self.settle:          # vault the wall
            self.plan = dict(goal=cur, dj=None, t=0, gx=blocker[1])
            it.up_p = it.up = True
            return it
        if self.settle and not danger:
            self.settle -= 1
        elif self.think_t <= 0 and (near or self.lane_t <= 0):
            self.think_t = 2 if self.skill > 0.85 else 3
            if self.lane_t <= 0:
                self.lane_t = rng.randint(30, 70)
            if rng.random() < 0.55 + 0.45 * self.skill or danger:
                best = self._options(cur, near and not blocked)
                if best is not None and best[3] == "jump" and (near or best[0] > self._score(cur) + 60):
                    _, hit, dj, _ = best
                    self.plan = dict(goal=hit, dj=dj, t=0)
                    self._aim(hit)
                    it.up_p = it.up = True
                    it.right = True
                    return it
                if near and (best is None or best[3] != "walk") and not danger:
                    return it                       # wait at the edge for a way across
        if sc.wall_x < me.x - 36 and not self._path_clear(edge):
            return it                               # let it swing past first
        it.right = True
        return it

    def _fly(self, it):
        me = self.me
        p = self.plan
        gx = me.x + 40
        if me.helpless:
            it.right = True
            return it
        if p is not None:
            p["t"] += 1
            goal = p["goal"]
            gx = p.get("gx") or goal.pos(self.sc.course_t)[0] + goal.w * (0.5 + self.aim)
            if p["dj"] is not None and p["t"] == p["dj"] and me.jumps:
                it.up_p = it.up = True
            if me.lvx or me.lvy or p["t"] > 160:
                self.plan = None
        elif self.sc.course_t % 4 == 0 or me.t < 2:
            r = self._air_plan()
            if r is not None:
                hit, dj = r
                self.plan = dict(goal=hit, dj=dj, t=0)
                self._aim(hit)
                if dj == 1 and me.jumps:
                    it.up_p = it.up = True
                gx = hit.cx
            elif me.jumps and me.vy > 0 and not me.lvx:
                it.up_p = it.up = True
            elif not me.upb_used and me.vy > 1.5 and me.y > LOW - 4:
                it.right = True
                self._special(it, "up")
                return it
        d = gx - me.x
        if abs(d) > 2:
            it.left, it.right = d < 0, d > 0
        return it


# --------------------------------------------------------------------------
# art
# --------------------------------------------------------------------------
_ART = None


def art():
    global _ART
    if _ART is None:
        sky = pygame.Surface((VW, VH))
        top, bot = (255, 170, 120), (130, 120, 220)
        for y in range(VH):
            sky.fill(mix(top, bot, y / VH), (0, y, VW, 1))
        rng = random.Random(11)
        hills = pygame.Surface((VW * 2, VH), pygame.SRCALPHA)
        for k in range(14):                # far candy hills, scrolled slowly
            x = k * VW * 2 // 14 + rng.randint(-10, 10)
            r = rng.randint(40, 70)
            pygame.draw.circle(hills, (200, 130, 190, 255), (x, VH - 20), r)
            pygame.draw.circle(hills, (215, 150, 205, 255), (x - r // 4, VH - 20 - r // 4), r // 3)
        clouds = []
        for _ in range(10):
            c = pygame.Surface((70, 24), pygame.SRCALPHA)
            for k in range(5):
                pygame.draw.circle(c, (255, 240, 240, 220), (8 + k * 13, 14 + rng.randint(-3, 3)), rng.randint(7, 11))
            clouds.append((c, rng.randint(0, VW * 2), rng.randint(4, 70)))
        _ART = dict(sky=sky, hills=hills, clouds=clouds)
    return _ART


# --------------------------------------------------------------------------
# the scene
# --------------------------------------------------------------------------
class SpikeRunScene(C.ClimbScene):
    def __init__(self, game, seed=None, level=11, hp=None, roster=None):
        C.F.init_shared()
        self.game = game
        self.level = level
        self.rng = random.Random(seed)
        self.max_hp = getattr(game, "akuma_max", C.AKUMA_MAX_HP)
        self.hp = self.max_hp if hp is None else hp
        self.menu = PauseMenu(game, CONTROLS)
        self.art = S.stage_art()
        self.look = art()
        self.roster = list(roster) if roster else self.rng.sample(C.CPU_POOL, C.RIVALS)
        self.cpu_enabled = True
        self.items_enabled = False
        self.items = []
        self.round = 1
        self.tries = []
        self._reach = {}
        self.t = 0
        self.result = None
        self.fighters = []
        self.view = pygame.Surface((VW, VH))
        self._start_round()

    def _start_round(self):
        (self.plats, self.hazards, self.solids, self.boxes,
         self.gate_x, self.length) = build_run(random.Random(self.rng.random()))
        self.finish = None
        self._ledges = [p for p in self.plats if p.ledges]
        self.sim_box = (-60, self.length + 40, FALL_Y)
        self.cpu_ledges = False                 # CPUs walking off an edge shouldn't grab it
        cast = ["akuma"] + list(self.roster)
        self.fighters = [C.Climber(self, c, i, i == 0) for i, c in enumerate(cast)]
        self.akuma = self.fighters[0]
        start = self.plats[0]
        order = list(range(len(self.fighters)))
        self.rng.shuffle(order)
        for k, f in zip(order, self.fighters):
            f.x, f.y = 60.0 + k * 40, start.y
            f.on = start
            f.facing = 1
        self.brains = {f: RunBrain(self, f, random.Random(self.rng.random()), sk)
                       for f, sk in zip(self.fighters[1:], C.SKILLS)}
        self.shots, self.effects, self.parts, self.blasts, self.booms, self.popups = [], [], [], [], [], []
        self.phase = "intro"
        self.end_t = 0
        self.shake = self.flash = 0
        self.won = None
        self.winner = None
        self.hits = {}
        self.announced = set()
        self.wall_x = WALL_X0
        self.wall_v = WALL_V
        self.camx = float(self.length - VW)
        self.camy = VH / 2
        self.play_t = -999
        self.course_t = 0
        for f in self.fighters:
            f.refresh()

    # ---- rules ---------------------------------------------------------------
    def spawn_shot(self, f, spec):
        self.shots.append(RunShot(f, spec))

    def stepped(self, f, p):
        if p.kind == "bounce":
            super().stepped(f, p)

    def respawn(self, f):
        """Back in the race just ahead of the spikes, dropped in from above."""
        x = max(40.0, self.wall_x + RESPAWN_AHEAD)
        for _ in range(60):
            if any(p.x0 + 6 <= x <= p.x1 - 6 and p.kind != "block" for p in self.plats):
                break
            x += 10
        f.x, f.y = x, 0.0
        f.vx = f.vy = f.lvx = f.lvy = 0.0
        f.pct = 0.0
        f.airborne = True
        f.on = None
        f.state, f.t = "air", 0
        f.jumps = 1
        f.upb_used = f.helpless = f.fastfall = False
        f.shield = S.SHIELD_MAX
        f.move = None
        f.grabbed = f.held_by = None
        f.star = 0
        f.invuln = RESPAWN_INVULN
        f.facing = 1
        if f in self.brains:
            self.brains[f].plan = None

    def spiked(self, f):
        """Caught by the wall: out of this try."""
        self.parts += [[f.x, f.y - f.hgt / 2, self.rng.uniform(0.5, 4), self.rng.uniform(-3, 1),
                        self.rng.randint(14, 30), self.rng.choice((f.color, (255, 255, 255), (200, 200, 220)))]
                       for _ in range(30)]
        self.popups.append(["SPIKED!", f.x + 30, f.y - f.hgt - 6, 70, (255, 90, 80)])
        self.shake = 12
        audio.play("boom", 0.8)
        if f.grabbed:
            self.drop_grab(f)
        if f.held_by is not None:
            f.held_by.grabbed = None
            f.held_by = None
        if f.last_hit_by is not None and self.t - getattr(f, "hit_t", -9999) <= 600:
            f.last_hit_by.ko_count += 1
        f.out = True
        f.state, f.t = "dead", 0
        f.move = None
        f.draw_key = None
        f.on = None
        if f.is_player and self.phase == "play":
            self.won = False
            self.phase, self.end_t = "game", 0
            audio.play("ko", 0.7)

    def _blast_zones(self):
        for f in self.fighters:
            if f.out or f.state in ("dead", "intro"):
                continue
            if f.y > FALL_Y or f.y < -140 or f.x > self.length + 60:
                self.ko(f)
            elif f.x - f.half_w * 0.5 < self.wall_x + 4:
                self.spiked(f)

    def _announce(self):
        """Runs every frame of play: the wall, the ? boxes and the gate."""
        if self.phase == "play" and self.t - self.play_t > WALL_GRACE:
            self.wall_x += self.wall_v
            self.wall_v += WALL_ACC
            if self.t % 7 == 0:
                self.parts.append([self.wall_x + 4, self.rng.uniform(20, VH - 20), self.rng.uniform(0.3, 1.2),
                                   self.rng.uniform(-0.6, 0.2), 16, (190, 180, 200)])
        for b in self.boxes:
            if b.cool:
                b.cool -= 1
            if b.bump:
                b.bump -= 1
            if b.cool:
                continue
            for f in self.fighters:
                if not f.on_field:
                    continue
                body = pygame.Rect(round(f.x - f.half_w), round(f.y - f.hgt), round(f.half_w * 2), round(f.hgt))
                if body.colliderect(b.rect):
                    self._prize(f, b)
                    break
        if self.phase == "play":
            for f in self.fighters:
                if f.on_field and not f.airborne and f.x >= self.gate_x and self.winner is None:
                    self.cross(f)

    def _prize(self, f, b):
        b.cool, b.bump = QBOX_COOL, 8
        if self.rng.random() < 0.35:
            f.star = STAR_TIME
            S.sfx("star", 0.7)
            self.popups.append(["STAR!", f.x, f.y - f.hgt - 6, 60, (255, 230, 80)])
        else:
            name = random_snack(self.rng)
            heal = min(int(f.pct), 35)
            f.pct = max(0.0, f.pct - 35)
            S.sfx("eat", 0.7)
            self.popups.append(["%s -%d%%" % (name, heal), f.x, f.y - f.hgt - 6, 70, (140, 255, 140)])
            b.snack = name

    def standings(self):
        def key(f):
            if f is self.winner:
                return -1e9
            if f.out:
                return 1e9 - f.slot
            return -f.x
        return sorted(self.fighters, key=key)

    def _finish(self):
        if self.won:
            self.result = "win"
            self.game.level_done(self, self.hp)
        else:
            self.result = "lose"
            self.game.level_failed(self)

    # ---- camera ----------------------------------------------------------------
    def _cam_goal(self):
        if self.phase == "intro":
            k = min(1.0, self.end_t / FLY)
            k = k * k * (3 - 2 * k)
            return (self.length - VW) * (1 - k)
        f = self.akuma
        if self.phase in ("game", "final") and self.winner is not None and not self.won and self.end_t < 120:
            f = self.winner
        if f.state == "dead" and not f.out:
            return max(self.camx, self.wall_x)
        if f.out:
            return self.camx
        return f.x - VW * 0.38

    def _camera(self):
        goal = self._cam_goal()
        if self.phase == "intro":
            self.camx = goal
        else:
            d = goal - self.camx
            self.camx += d * (0.12 if abs(d) < 250 else 0.3)
        self.camx = max(-60.0, min(self.length - VW, self.camx))
        self.cam = [self.camx + VW / 2, VH / 2, float(VW)]

    def cam_rect(self):
        return pygame.Rect(int(round(self.camx)), 0, VW, VH)

    def to_screen(self, x, y, rect=None):
        r = rect or self.cam_rect()
        return (x - r.x) * W / VW, (y - r.y) * H / VH

    # ---- draw ----------------------------------------------------------------
    def draw(self, surf):
        sh = [0, 0]
        if self.shake:
            m = 1 + self.shake // 5
            sh = [self.rng.randint(-m, m), self.rng.randint(-m, m)]
        rc = self.cam_rect()
        v = self.view
        a = self.look
        v.blit(a["sky"], (0, 0))
        hx = -(rc.x * 0.25) % (VW * 2)
        v.blit(a["hills"], (round(hx) - VW * 2, 0))
        v.blit(a["hills"], (round(hx), 0))
        for img, x, y in a["clouds"]:
            cx = (x - rc.x * 0.12) % (VW * 2 + 70) - 70
            v.blit(img, (round(cx), y))
        o = (sh[0] - rc.x, sh[1])
        t = self.course_t
        lo, hi = rc.left - 60, rc.right + 60
        for r in self.solids:
            if lo < r.x < hi:
                body = r.move(o)
                pygame.draw.rect(v, OUTLINE, body.inflate(2, 2))
                v.fill((150, 130, 170), body)
                for yy in range(body.top + 4, body.bottom - 2, 6):
                    v.fill((120, 100, 140), (body.x + 2, yy, body.w - 4, 2))
        for h in self.hazards:
            if h.kind == "crusher" and lo - 40 < h.x < hi:
                self._draw_crusher(v, h, o)
        for p in self.plats:
            if p.x1 > lo and p.x0 < hi:
                if p.kind == "belt" and p.y >= LOW:          # the low road's belt sits in the ground
                    v.fill(shade(C.MINT, 0.62), (round(p.x0) + o[0], round(p.y) + o[1] + 4, round(p.w), 30))
                self._draw_plat(v, p, o, t)
        self._draw_gate(v, o)
        for h in self.hazards:
            if h.kind in ("sweep", "pend") and lo - 60 < h.x < hi + 60:
                self._draw_hazard(v, h, o, -1e9, 1e9)
            elif h.kind == "spikes" and h.x1 > lo and h.x0 < hi:
                self._draw_spikes(v, h, o)
            elif h.kind == "cannon" and lo - 300 < h.x < hi + 40:
                self._draw_gun(v, h, o)
        for b in self.boxes:
            if lo < b.x < hi:
                self._draw_box(v, b, o)
        order = sorted(self.fighters, key=lambda f: (f.is_player, f.state == "held"))
        for f in order:
            if lo - 40 < f.x < hi + 40:
                self._draw_fighter(v, f, o)
        for s in self.shots:
            img, _, (px, py) = s.frame()
            v.blit(img, (px + o[0], py + o[1]))
        for fx in self.effects:
            fx.draw(v, o)
        for p in self.parts:
            v.fill(p[5], (round(p[0]) + o[0], round(p[1]) + o[1], 2, 2))
        self._draw_wall(v, o)
        self._draw_blasts_screen(v, rc)
        pygame.transform.scale(v, (W, H), surf)
        self._wall_warning(surf, rc)
        for f in self.fighters:
            if not f.out:
                self._tag(surf, f, (0, 0), rc)
        for text, x, y, n, col in self.popups:
            sx, sy = self.to_screen(x, y, rc)
            sx = max(text_width(text) // 2 + 2, min(W - text_width(text) // 2 - 2, sx))
            sy = max(14, min(H - 40, sy))
            draw_text(surf, text, round(sx), round(sy) - (60 - min(60, n)) // 5, col, align="center")
        if self.flash:
            fl = pygame.Surface((W, H), pygame.SRCALPHA)
            fl.fill((255, 255, 255, 90))
            surf.blit(fl, (0, 0))
        self._hud(surf)
        self._overlays(surf)
        if self.menu.open:
            self.menu.draw(surf)

    def _draw_wall(self, v, o):
        x = round(self.wall_x) + o[0]
        if x < -40:
            return
        rumble = (self.t // 2) % 2 if self.phase == "play" else 0
        v.fill((40, 34, 52), (0, 0, max(0, x - 6), VH))
        v.fill((70, 62, 86), (max(0, x - 10), 0, 6, VH))
        for k in range(0, VH + 16, 16):                 # rows of spikes pointing right
            yy = k - (self.t // 3) % 16 if self.phase == "play" else k
            tip = x + 14 + rumble
            pygame.draw.polygon(v, OUTLINE, [(x - 5, yy - 1), (tip + 1, yy + 8), (x - 5, yy + 17)])
            pygame.draw.polygon(v, (200, 200, 215), [(x - 4, yy), (tip, yy + 8), (x - 4, yy + 16)])
            pygame.draw.line(v, (250, 250, 255), (x - 3, yy + 3), (tip - 3, yy + 8))
        for k in range(8, VH, 40):                      # rivets
            v.fill((120, 110, 140), (max(0, x - 20), k, 3, 3))

    def _wall_warning(self, surf, rc):
        """The spikes are off the left of the screen: a red glow that grows as they close in."""
        gap = rc.x - self.wall_x
        if gap <= 0 or self.phase not in ("play", "game") or self.akuma.out:
            return
        k = max(0.0, 1 - gap / 260)
        if k <= 0:
            return
        glow = pygame.Surface((14, H), pygame.SRCALPHA)
        a = int(60 + 140 * k * (0.7 + 0.3 * math.sin(self.t / 4)))
        for x in range(14):
            glow.fill((255, 40, 30, max(0, a - x * a // 14)), (x, 0, 1, H))
        surf.blit(glow, (0, 0))
        draw_text(surf, "SPIKES!", 3, H // 2 - 30, (255, 120, 100) if (self.t // 8) % 2 else (255, 230, 200))
        draw_text(surf, "%dM" % max(1, gap // 16), 3, H // 2 - 20, (255, 200, 180))

    def _draw_crusher(self, v, h, o):
        b, _ = h.bottom()
        x = round(h.x) + o[0] + ((1, -1)[self.t % 2] if h.shaking() else 0)
        top = round(h.top) + o[1]
        bot = round(b) + o[1]
        v.fill((90, 90, 100), (x + h.w // 2 - 2, top, 4, max(0, bot - h.h - top)))
        r = pygame.Rect(x, bot - h.h, h.w, h.h)
        pygame.draw.rect(v, OUTLINE, r.inflate(2, 2))
        v.fill((110, 110, 130), r)
        v.fill((150, 150, 170), (r.x + 2, r.y + 2, r.w - 4, 3))
        for k in range(3):                              # angry teeth on the bottom
            sx = r.x + 2 + k * (r.w - 4) // 3
            pygame.draw.polygon(v, (230, 230, 240), [(sx, r.bottom), (sx + 4, r.bottom + 4), (sx + 8, r.bottom)])
        v.fill((255, 220, 60), (r.x + 7, r.y + 9, 4, 4))
        v.fill((255, 220, 60), (r.right - 11, r.y + 9, 4, 4))

    def _draw_spikes(self, v, h, o):
        y = round(h.y) + o[1]
        for x in range(round(h.x0), round(h.x1) - 5, 6):
            sx = x + o[0]
            pygame.draw.polygon(v, OUTLINE, [(sx - 1, y + 1), (sx + 3, y - 8), (sx + 7, y + 1)])
            pygame.draw.polygon(v, (220, 220, 235), [(sx, y), (sx + 3, y - 7), (sx + 6, y)])

    def _draw_gun(self, v, h, o):
        x, y = round(h.x) + o[0], round(h.y) + o[1]
        r = h.recoil // 3
        v.fill(OUTLINE, (x - 3, y - 10, 6, 10))
        body = pygame.Rect(x - 14 + r, y - 20, 20, 12)
        pygame.draw.rect(v, OUTLINE, body.inflate(2, 2), border_radius=3)
        pygame.draw.rect(v, (70, 70, 90), body, border_radius=3)
        v.fill((140, 140, 170), (body.x + 2, body.y + 2, body.w - 4, 2))
        for b in h.balls:
            C._fruit(v, b[0] + o[0], b[1] + o[1] - 6, b[3], b[4])

    def _draw_box(self, v, b, o):
        r = b.rect.move(o)
        if b.cool:
            pygame.draw.rect(v, OUTLINE, r.inflate(2, 2))
            v.fill((150, 120, 90), r)
            return
        pygame.draw.rect(v, OUTLINE, r.inflate(2, 2))
        v.fill((250, 200, 60), r)
        v.fill((255, 240, 160), (r.x + 1, r.y + 1, r.w - 2, 2))
        draw_text(v, "?", r.x + 4, r.y + 3, (255, 255, 255) if (self.t // 12) % 2 else (200, 90, 40), shadow=None)

    def _draw_gate(self, v, o):
        x = round(self.gate_x) + o[0]
        y = MID + o[1]
        if x < -30 or x > VW + 30:
            return
        for px in (x - 2, x + 22):
            for k in range(0, 60, 6):
                v.fill((250, 250, 250) if (k // 6) % 2 else (30, 30, 40), (px, y - 60 + k, 4, 6))
        pygame.draw.rect(v, OUTLINE, (x - 10, y - 74, 46, 13))
        pygame.draw.rect(v, (240, 60, 120), (x - 9, y - 73, 44, 11))
        draw_text(v, "GOAL", x + 13, y - 71, (255, 255, 255), align="center")

    def _hud(self, surf):
        places = self._panels(surf)
        if self.phase not in ("play", "game"):
            return
        draw_text(surf, "TRY %d/%d" % (self.round, TRIES), 4, 3, (255, 255, 255))
        draw_text(surf, "%s PLACE" % C.ordinal(places[self.akuma]), W - 4, 3, (255, 230, 120), align="right")
        # the course as a strip: the wall, everyone, the goal
        x0, x1, y = 62, W - 70, 5
        pygame.draw.rect(surf, OUTLINE, (x0 - 1, y - 1, x1 - x0 + 2, 5))
        surf.fill((70, 60, 100), (x0, y, x1 - x0, 3))

        def sx(x):
            return x0 + round((x1 - x0) * max(0.0, min(1.0, x / self.gate_x)))
        surf.fill(C.GOLD, (x1 - 1, y - 3, 3, 9))
        surf.fill((200, 60, 60), (x0, y, max(0, sx(self.wall_x) - x0), 3))
        for f in sorted(self.fighters, key=lambda f: f.is_player):
            if f.out or f.state == "dead":
                continue
            px = sx(f.x)
            pygame.draw.rect(surf, OUTLINE, (px - 2, y - 2, 5, 7))
            surf.fill(f.color, (px - 1, y - 1, 3, 5))

    def _overlays(self, surf):
        cx = W // 2
        if self.phase == "intro":
            n = self.end_t
            L = self.intro_len
            if n < L - 90:
                self._band(surf, 26, 54)
                if self.round == 1:
                    draw_text(surf, "ROUND 2", cx, 30, (255, 220, 80), scale=2, align="center")
                    draw_text(surf, LEVEL_NAME, cx, 48, (255, 255, 255), align="center")
                    draw_text(surf, "RUN FOR THE GOAL - THE SPIKES ARE COMING", cx, 59, (180, 220, 255),
                              align="center")
                    draw_text(surf, "KNOCK RIVALS BACK INTO THEM", cx, 69, (255, 190, 150), align="center")
                else:
                    draw_text(surf, "TRY %d OF %d" % (self.round, TRIES), cx, 34, (255, 220, 80), scale=3,
                              align="center")
                    draw_text(surf, "STAY AHEAD OF THE SPIKES", cx, 62, (255, 255, 255), align="center")
            else:
                k = 3 - (n - (L - 90)) // 30
                if k >= 1:
                    draw_text(surf, str(k), cx, 50, (255, 230, 90), scale=5, align="center")
        if self.phase == "play" and self.t - self.play_t < 45:
            draw_text(surf, "RUN!", cx, 46, (255, 70, 40), scale=5, align="center")
        if self.phase == "game":
            w = self.winner
            self._band(surf, 40, 40)
            nxt = "TRY AGAIN!" if self.round < TRIES else "OUT OF TRIES"
            if self.won:
                draw_text(surf, "QUALIFIED!", cx, 44, (255, 230, 80), scale=3, align="center")
                draw_text(surf, "AKUMA OUTRAN THE SPIKES", cx, 68, (255, 255, 255), align="center")
            elif w is not None:
                draw_text(surf, "%s WINS" % w.name, cx, 44, (255, 255, 255), scale=2, align="center")
                draw_text(surf, "AKUMA IS ELIMINATED - " + nxt, cx, 66, (255, 140, 120), align="center")
            else:
                draw_text(surf, "SPIKED!", cx, 44, (255, 90, 80), scale=3, align="center")
                draw_text(surf, "AKUMA IS ELIMINATED - " + nxt, cx, 68, (255, 140, 120), align="center")
        if self.phase == "final":
            self._band(surf, 22, 78, 205)
            draw_text(surf, "RESULTS", cx, 26, (255, 220, 80), scale=2, align="center")
            for k, name in enumerate(self.tries):
                txt = "TRY %d:  %s" % (k + 1, (name + " WINS") if name else "SPIKED")
                draw_text(surf, txt, cx, 45 + k * 9, (255, 120, 90) if name == "AKUMA" else (170, 170, 190),
                          align="center")
            if self.won:
                draw_text(surf, "LEVEL CLEAR!", cx, 80, (255, 80, 60), scale=2, align="center")
            else:
                draw_text(surf, "AKUMA IS ELIMINATED", cx, 80, (200, 200, 220), scale=2, align="center")
