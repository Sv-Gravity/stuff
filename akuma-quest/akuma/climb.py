"""Level 11: a Fall Guys style climbing race up a tall obstacle course.

Akuma and four Street Fighter rivals start together on the floor of a huge
candy-coloured tower and race to the crown on top: whoever touches the
FINISH first wins. The climb is mostly medium (steps, moving platforms,
conveyors, bounce pads, swinging hammers, sweeper bars, boxing-glove pistons
and fruit cannons) with three hard spots on the way (a crumbling bridge
under a sweeper, a row of thin pillars between pistons, and blinking ghost
blocks under fire) and a hard final summit.

Everyone fights like in the Smash level (smash.py): the same fighters,
moves, shield, grabs and damage %. Hits and obstacles add %, and the higher
it is the further everything knocks you. Get knocked off the side of the
tower and you respawn back on the floor at 0% and have to catch up.

Three tries: reach the crown first on any of them to clear the level.
"""

import math
import random

import pygame

from . import audio
from . import fight as F
from . import smash as S
from .art import shade, mix, OUTLINE
from .config import W, H, AKUMA_MAX_HP
from .font import draw_text, text_width
from .pause import PauseMenu

LEVEL_NAME = "THE CLIMB"

# --------------------------------------------------------------------------
# tuning
# --------------------------------------------------------------------------
TRIES = 3
RIVALS = 4
CW = W                  # the tower is one screen wide ...
CH = 2240               # ... and this tall
FLOOR = CH - 18         # top of the start floor
BLAST_L, BLAST_R, BLAST_B, BLAST_T = -30, CW + 30, CH + 40, -120
RESPAWN_INVULN = 110
INTRO = 300             # the camera flies down the tower, then 3-2-1
FLY = 190               # frames of the fly-down
GAME_LEN = 230
FINAL_LEN = 240
BOUNCE_V = -8.7         # what a bounce pad launches you at
HAZARD_CD = 34          # frames before the same obstacle can hit the same fighter again
SLOT_COLORS = [(232, 52, 44), (64, 110, 240), (240, 200, 40), (56, 190, 80), (200, 90, 230)]
CPU_POOL = ["ryu", "ken", "sakura", "chunli", "zangief", "morrigan", "felicia", "hsienko", "drdoom"]

CONTROLS = [
    "CLIMB TO THE CROWN BEFORE THE OTHERS!",
    "LEFT / RIGHT: MOVE   UP: JUMP (TWICE)",
    "HOLD TOWARD A LEDGE TO GRAB IT",
    "DOWN: CROUCH / DROP THROUGH A LEDGE",
    "J: JAB   K: KICK   DOWN+K: SWEEP",
    "L: HADOUKEN   L+J: SHORYUKEN",
    "L+K: HURRICANE KICK   I: SHIELD",
    "I+J OR J+K: GRAB",
    "KNOCKED OFF? BACK TO THE BOTTOM",
    "3 TRIES: WIN ONE TO CLEAR",
]

# obstacle hits: like an attack's damage / base knockback / growth / angle
SWEEP_HIT = dict(dmg=5, kb=3.4, kg=2.8, ang=40)
HAMMER_HIT = dict(dmg=6, kb=3.6, kg=3.0, ang=35)
GLOVE_HIT = dict(dmg=4, kb=3.4, kg=2.8, ang=22)
FRUIT_HIT = dict(dmg=4, kb=2.8, kg=2.4, ang=30)
KB_SCALE = 0.85         # fighters' own hits launch a bit less than on the Smash stage (it's narrow)


def R(rise):
    """World y of a height above the start floor."""
    return FLOOR - rise


# --------------------------------------------------------------------------
# platforms: everything is one-way (jump up through it, land on top)
# --------------------------------------------------------------------------
class Plat:
    def __init__(self, x0, x1, rise, kind="static", col=None, ax=0.0, ay=0.0, period=240, phase=0.0,
                 belt=0.0, on=60, off=60, ledges=None, nodrop=False):
        self.bx0, self.w = float(x0), float(x1 - x0)
        self.by = float(R(rise)) if kind != "floor" else float(FLOOR)
        self.kind = kind
        self.ax, self.ay, self.period, self.phase = ax, ay, period, phase
        self.belt = belt
        self.on_t, self.off_t = on, off
        self.col = col
        self.idx = 0
        self.ledges = (kind == "static") if ledges is None else ledges
        self.nodrop = nodrop or kind in ("floor", "finish")     # DOWN doesn't drop through it
        self.crumble = -1          # frames until it falls (crumble tiles), -1 = untouched
        self.gone = 0              # frames until it comes back
        self.x0, self.y = self.bx0, self.by
        self.px0, self.py = self.x0, self.y
        self.dx = self.dy = 0.0
        self.at(0)

    @property
    def x1(self):
        return self.x0 + self.w

    @property
    def cx(self):
        return self.x0 + self.w / 2

    def pos(self, t):
        """(x0, y) of the platform at frame t (moving platforms follow a sine)."""
        if self.ax or self.ay:
            s = math.sin(math.tau * t / self.period + self.phase)
            return self.bx0 + self.ax * s, self.by + self.ay * s
        return self.bx0, self.by

    def lit(self, t):
        """Blinking ghost blocks are only there part of the cycle."""
        if self.kind != "blink":
            return True
        return (t + int(self.phase)) % (self.on_t + self.off_t) < self.on_t

    def at(self, t):
        self.px0, self.py = self.x0, self.y
        self.x0, self.y = self.pos(t)
        self.dx, self.dy = self.x0 - self.px0, self.y - self.py

    def active(self, t):
        return self.gone <= 0 and self.lit(t)

    def update(self, t):
        self.at(t)
        if self.kind == "crumble":
            if self.gone > 0:
                self.gone -= 1
            elif self.crumble > 0:
                self.crumble -= 1
                if self.crumble == 0:
                    self.gone = 200
                    self.crumble = -1
                    audio.play("land", 0.8)


# --------------------------------------------------------------------------
# obstacles
# --------------------------------------------------------------------------
class Sweeper:
    """A bar spinning around a hub: one arm or two (both ways from the hub)."""
    kind = "sweep"

    def __init__(self, x, rise, length, speed, arms=1, phase=0.0):
        self.x, self.y = float(x), float(R(rise))
        self.len, self.speed, self.arms, self.phase = length, speed, arms, phase
        self.t = 0

    def update(self, t):
        self.t = t

    def segments(self, t=None):
        ang = self.phase + self.speed * (self.t if t is None else t)
        out = []
        for k in range(self.arms):
            a = ang + k * math.pi
            out.append((self.x, self.y, self.x + math.cos(a) * self.len, self.y + math.sin(a) * self.len))
        return out

    def hit(self, box, t=None):
        x0, y0, x1, y1 = box
        if y1 < self.y - self.len - 3 or y0 > self.y + self.len + 3:
            return None
        for sx, sy, ex, ey in self.segments(t):
            for k in range(0, 11):
                px = sx + (ex - sx) * k / 10
                py = sy + (ey - sy) * k / 10
                if x0 - 3 <= px <= x1 + 3 and y0 - 3 <= py <= y1 + 3:
                    # pushed the way the bar is moving at that point
                    tx = -math.sin(math.atan2(py - self.y, px - self.x)) * self.speed
                    return SWEEP_HIT, (1 if tx > 0 else -1), (px, py)
        return None


class Pendulum:
    """A big ball on a chain swinging from a pivot."""
    kind = "pend"

    def __init__(self, x, rise, length, amp, period, phase=0.0, r=9):
        self.x, self.y = float(x), float(R(rise))
        self.len, self.amp, self.period, self.phase, self.r = length, amp, period, phase, r
        self.t = 0

    def update(self, t):
        self.t = t

    def swing(self, t=None):
        """(angle from straight down, which way it is moving)."""
        a = math.tau * (self.t if t is None else t) / self.period + self.phase
        return self.amp * math.sin(a), math.cos(a)

    @property
    def ang(self):
        return self.swing()[0]

    def ball(self, t=None):
        ang = self.swing(t)[0]
        return self.x + math.sin(ang) * self.len, self.y + math.cos(ang) * self.len

    def hit(self, box, t=None):
        bx, by = self.ball(t)
        x0, y0, x1, y1 = box
        nx, ny = max(x0, min(x1, bx)), max(y0, min(y1, by))
        if (nx - bx) ** 2 + (ny - by) ** 2 <= self.r ** 2:
            vel = self.swing(t)[1]
            d = (1 if vel > 0 else -1) if abs(vel) > 0.25 else (1 if (x0 + x1) / 2 > bx else -1)
            return HAMMER_HIT, d, (nx, ny)
        return None


class Piston:
    """A boxing glove that punches out from the side of the tower now and then."""
    kind = "piston"

    def __init__(self, side, rise, reach, period=150, phase=0):
        self.side = side                 # -1: comes from the left wall, 1: from the right
        self.y = float(R(rise))
        self.reach, self.period, self.phase = reach, period, phase
        self.t = 0

    def update(self, t):
        self.t = t
        if (t + self.phase) % self.period == 40:
            audio.play("whiff", 0.25)

    def stroke(self, t=None):
        """(how far out the glove is, whether it is punching)."""
        k = ((self.t if t is None else t) + self.phase) % self.period
        if k < 40:                       # tucked in
            return 0.0, False
        if k < 48:                       # punch!
            return self.reach * (k - 39) / 9, True
        if k < 80:
            return self.reach, False
        if k < 110:
            return self.reach * (1 - (k - 80) / 30), False
        return 0.0, False

    @property
    def out(self):
        return self.stroke()[0]

    def glove(self, t=None):
        """Rect of the glove head."""
        out = self.stroke(t)[0]
        w, h = 16, 14
        x = out - w if self.side < 0 else CW - out
        return pygame.Rect(round(x), round(self.y - h), w, h)

    def hit(self, box, t=None):
        out, moving = self.stroke(t)
        if out <= 0:
            return None
        g = self.glove(t)
        x0, y0, x1, y1 = box
        if g.right > x0 and g.left < x1 and g.bottom > y0 and g.top < y1:
            if moving:
                return GLOVE_HIT, -self.side, ((g.left if self.side > 0 else g.right), g.centery)
        return None


class Cannon:
    """Shoots big fruit straight across the tower from one side."""
    kind = "cannon"
    FRUITS = ("orange", "melon", "apple")

    def __init__(self, side, rise, period=130, phase=0, speed=2.2):
        self.side = side
        self.y = float(R(rise))
        self.period, self.phase, self.speed = period, phase, speed
        self.balls = []                  # [x, y, vx, fruit, spin]
        self.recoil = 0
        self.t = 0

    def update(self, t):
        self.t = t
        if (t + self.phase) % self.period == 0:
            x = 6.0 if self.side < 0 else CW - 6.0
            self.balls.append([x, self.y - 7, -self.side * self.speed, self.FRUITS[(t // self.period) % 3], 0])
            self.recoil = 8
        if self.recoil:
            self.recoil -= 1
        for b in self.balls:
            b[0] += b[2]
            b[4] += 1
        self.balls = [b for b in self.balls if -20 < b[0] < CW + 20]

    def hit(self, box, t=None):
        k = 0 if t is None else t - self.t
        x0, y0, x1, y1 = box
        for b in self.balls:
            bx = b[0] + b[2] * k
            nx, ny = max(x0, min(x1, bx)), max(y0, min(y1, b[1]))
            if (nx - bx) ** 2 + (ny - b[1]) ** 2 <= 36:
                return FRUIT_HIT, (1 if b[2] > 0 else -1), (nx, ny)
        return None


# --------------------------------------------------------------------------
# the course, bottom to top. Rises are heights above the start floor.
# --------------------------------------------------------------------------
PINK, YELLOW, BLUE, MINT, ORANGE, PURPLE = ((246, 110, 170), (250, 210, 70), (90, 170, 250),
                                            (110, 220, 170), (250, 150, 70), (170, 120, 240))
GOLD = (250, 200, 60)

# hard spots: (rise from, rise to, label) - shown on the progress bar and announced
HARD = [(540, 700, "CRUMBLE BRIDGE"), (1000, 1200, "PILLARS"), (1500, 1720, "GHOST BLOCKS"),
        (1900, 2150, "THE SUMMIT")]
FINISH_RISE = 2150


def build_course():
    """(platforms in climbing order, obstacles, the finish platform)."""
    P = []
    hz = []

    def p(*a, **kw):
        P.append(Plat(*a, **kw))
        return P[-1]

    p(-40, CW + 40, 0, "floor", col=MINT)
    # -- warm-up: steps, one swinging hammer, a moving step
    p(30, 110, 46, col=PINK)
    p(130, 205, 92, col=YELLOW)
    hz.append(Pendulum(168, 170, 56, 1.0, 170))
    p(222, 302, 138, col=BLUE)
    p(110, 160, 184, "move", col=ORANGE, ax=50, period=260)
    p(14, 96, 230, col=PINK)
    # -- conveyors and boxing gloves
    p(60, 250, 276, "belt", col=PURPLE, belt=-0.7)
    hz.append(Piston(1, 276, 150, period=160))
    p(232, 310, 322, col=YELLOW)
    p(150, 212, 368, col=MINT)
    p(36, 126, 414, col=BLUE)
    hz.append(Cannon(1, 414, period=150, phase=40))
    p(116, 166, 460, "move", col=ORANGE, ay=22, period=200)
    p(200, 300, 506, col=PINK)
    # -- HARD 1: crumbling bridge under a sweeper
    for k, x in enumerate((206, 150, 94, 38)):
        p(x, x + 28, 548 + k * 30, "crumble", col=(226, 190, 140))
    hz.append(Sweeper(122, 600, 64, 0.022))
    p(8, 70, 670, col=YELLOW)
    # -- moving platforms
    p(90, 140, 716, "move", col=ORANGE, ax=40, period=220)
    p(200, 290, 760, col=BLUE)
    p(150, 196, 806, "move", col=ORANGE, ay=26, period=190)
    p(40, 130, 852, col=MINT)
    hz.append(Pendulum(62, 920, 50, 0.7, 150, phase=1.2))
    p(140, 188, 898, "move", col=ORANGE, ax=80, period=300)
    p(240, 312, 944, col=PINK)
    hz.append(Cannon(-1, 958, period=140))
    # -- HARD 2: a spinning double bar, then thin pillars between pistons
    p(30, 290, 992, col=YELLOW)
    hz.append(Sweeper(160, 1012, 64, 0.03, arms=2))
    p(150, 172, 1040, col=BLUE)
    p(86, 108, 1086, col=PINK)
    hz.append(Piston(-1, 1086, 110, period=140))
    p(200, 222, 1132, col=MINT)
    hz.append(Piston(1, 1132, 120, period=140, phase=70))
    p(124, 146, 1178, col=YELLOW)
    p(30, 120, 1222, col=BLUE)
    # -- bounce pads and belts
    p(130, 156, 1238, "bounce", col=(90, 220, 90))
    p(176, 290, 1340, "belt", col=PURPLE, belt=0.6)
    hz.append(Pendulum(232, 1410, 52, 1.0, 160, phase=2.0))
    p(60, 150, 1386, "move", col=ORANGE, ax=34, period=240)
    p(170, 240, 1432, col=PINK)
    p(240, 310, 1478, col=MINT)
    # -- HARD 3: ghost blocks that blink in turn, with fruit flying through
    for k, x in enumerate((186, 116, 46, 116, 190)):
        p(x, x + 40, 1524 + k * 44, "blink", col=PURPLE, on=110, off=60, phase=170 - k * 34)
    hz.append(Cannon(-1, 1590, period=110, speed=2.4))
    hz.append(Cannon(1, 1678, period=120, phase=55, speed=2.4))
    # -- one more medium stretch
    p(228, 310, 1750, col=YELLOW)
    p(150, 194, 1796, "move", col=ORANGE, ax=60, period=260)
    p(40, 120, 1842, col=BLUE)
    hz.append(Sweeper(36, 1872, 40, -0.028))
    p(140, 210, 1888, col=PINK)
    # -- HARD 4, the summit: a lift, crumbling steps, gloves, fruit, and a double bar round the crown
    p(232, 270, 1930, "move", col=ORANGE, ay=32, period=200)
    p(176, 200, 1996, "crumble", col=(226, 190, 140))
    hz.append(Piston(1, 1996, 120, period=150))
    p(110, 134, 2040, "crumble", col=(226, 190, 140))
    p(40, 72, 2084, col=BLUE)
    hz.append(Cannon(-1, 2124, period=100, phase=30, speed=2.6))
    hz.append(Sweeper(160, 2172, 62, 0.034, arms=2))
    finish = p(112, 208, FINISH_RISE, "finish", col=GOLD, ledges=True)
    for i, pl in enumerate(P):
        pl.idx = i
    return P, hz, finish


# --------------------------------------------------------------------------
# a racer: the Smash fighter, standing on the course's platforms
# --------------------------------------------------------------------------
class Climber(S.Smasher):
    def __init__(self, scene, cid, slot, is_player=False):
        super().__init__(scene, cid, slot % len(S.SLOT_COLORS), is_player)
        self.slot = slot
        self.color = SLOT_COLORS[slot]
        # everyone climbs alike (like Fall Guys): same jumps, about the same speed
        self.jump_v, self.djump_v, self.grav_k = -5.6, -5.2, 1.0
        self.walk = max(1.6, min(1.85, self.walk))
        self.air_max = max(1.7, min(1.9, self.air_max))
        self.on = None                # the platform stood on
        self.best = 0.0               # highest rise reached this try
        self.falls = 0
        self.done = False

    @property
    def rise(self):
        return FLOOR - self.y

    def _st_stand(self, it):
        if it.shield and not self.airborne:
            self.state, self.t = "shield", 0
            return
        if self._consume_attack(it):
            return
        if self.jbuf:
            self.jbuf = 0
            self.state, self.t = "prejump", 0
            return
        if it.down_p and self.on is not None and not self.on.nodrop:
            self.drop = 14
            self.airborne = True
            self.on = None
            self.y += 1
            self.state, self.t = "air", 0
            return
        d = it.dir
        self.crouch = it.down
        if d:
            self.facing = d
        if d and not it.down:
            self.vx = d * self.walk
        else:
            self.vx *= S.FRICTION
            if abs(self.vx) < 0.05:
                self.vx = 0.0

    def _st_roll(self, it):
        self.vx = self.roll_dir * (2.6 if self.t < 14 else 0.8)
        p = self.on
        if p is None or not (p.x0 <= self.x + self.vx * 2 <= p.x1):
            self.vx = 0.0
        if self.t >= S.ROLL_LEN:
            self.state, self.t = "stand", 0

    def _physics(self, it):
        sc = self.sc
        if self.lvx or self.lvy:
            sp = math.hypot(self.lvx, self.lvy)
            nsp = sp - S.KB_DECAY
            if nsp <= 0:
                self.lvx = self.lvy = 0.0
            else:
                self.lvx *= nsp / sp
                self.lvy *= nsp / sp
        if self.airborne and self._gravity_on():
            cap = S.FASTFALL if self.fastfall else S.FALL_MAX
            if self.vy < cap:
                self.vy = min(cap, self.vy + S.GRAV * self.grav_k)
        dx = self.vx + self.lvx
        dy = (self.vy + self.lvy) if self.airborne else 0.0
        if not self.airborne and self.on is not None:     # ride the platform
            p = self.on
            self.x += p.dx + p.belt
            self.y = p.y
        self.x += dx
        for r in sc.solids:                               # walls you can't walk through
            if self.x + S.BODY_W > r.left and self.x - S.BODY_W < r.right and self.y > r.top + 1 \
                    and self.y - S.BODY_H < r.bottom:
                if dx + (self.on.dx if self.on is not None and not self.airborne else 0) >= 0 \
                        and self.x < r.centerx:
                    self.x = r.left - S.BODY_W
                else:
                    self.x = r.right + S.BODY_W
                self.vx = 0.0
                self.lvx *= -0.4
        if self.airborne:
            py = self.y
            self.y += dy
            if dy >= 0:
                land = sc.landing(self.x, py, self.y, self.drop)
                if land is not None:
                    self.y = land.y
                    self.on = land
                    self._land(dy)
                    sc.stepped(self, land)
            if self.airborne:
                self._ledge_snap(it)
        else:
            p = self.on
            if p is None or not sc.stands(p, self.x, self.y):
                p = sc.ground(self.x, self.y)
            self.on = p
            if p is None:
                self.airborne = True
                if self.state in ("stand", "land", "prejump", "shield", "roll", "getup", "down", "ledge"):
                    self.state, self.t = "air", 0
        if self.on is not None and not self.airborne:
            self.best = max(self.best, self.rise)

    def _ledge_snap(self, it):
        if self.state not in ("air", "move") or self.vy + self.lvy < -1.5:
            return
        if self.state == "move" and not (self.move.get("upb") or self.helpless):
            return
        if not self.is_player and not getattr(self.sc, "cpu_ledges", True) and not self.helpless:
            return
        for p in self.sc.ledges():
            for lx, side in ((p.x0, -1), (p.x1, 1)):
                inward = -side
                if not (p.y + 6 <= self.y <= p.y + 26):        # a little below it, not walking off it
                    continue
                off = (self.x - lx) * side
                if -2 <= off <= 14 and (it.dir == inward or self.vx * inward > 0.2 or self.helpless):
                    if self.state == "move":
                        self.move = None
                        self.move_vx = None
                    self.x = lx + inward * 6
                    self.y = p.y
                    self.on = p
                    self.vx = self.vy = self.lvx = self.lvy = 0.0
                    self._landed_reset()
                    self.state, self.t = "ledge", 0
                    self.facing = inward
                    audio.play("land", 0.6)
                    return


class ClimbShot(S.Shot):
    def update(self):
        self.t += 1
        self.x += self.vx
        self.y += self.vy
        self.vy += self.grav
        if self.t >= self.life or not (-40 < self.x < CW + 40):
            self.alive = False


# --------------------------------------------------------------------------
# CPU racers: plan jumps by simulating them, scrap with whoever is near
# --------------------------------------------------------------------------
DJ_OPTIONS = (None, 4, 8, 12, 16, 20, 26)
SKILLS = [0.95, 0.85, 0.75, 0.65]   # the four rivals: sharp ... sloppy
LEAD = 300                          # a rival this far above Akuma dawdles more


class ClimbBrain(S.Brain):
    def __init__(self, scene, me, rng, skill=1.0):
        super().__init__(scene, me, rng, focus=0.3)
        self.skill = skill              # 0.6 (sloppy) .. 1.0 (sharp)
        self.plan = None                # dict(tx: callable, dj: frame, t: frames since takeoff, goal: plat)
        self.think_t = 0
        self.dawdle = 0
        self.aim = rng.uniform(-0.25, 0.25)
        self.stood = None
        self.settle = 0
        self._dodging = None

    # --- jump prediction ----------------------------------------------------
    def simulate(self, x, y, vx, vy, jumps, airborne, goal, dj, cands, frames=110, hazards=()):
        """Where a jump (or the rest of a fall) ends: the platform it lands on, or
        None (falls short, or flies into one of the given obstacles)."""
        me = self.me
        sc = self.sc
        t0 = sc.course_t
        hw, hh = me.half_w, me.hgt
        xmin, xmax, ymax = sc.sim_box
        g = S.GRAV * me.grav_k
        k = 0
        if not airborne:
            for _ in range(3):              # prejump crouch
                k += 1
                vx *= 0.9
                x += vx
            vy = me.jump_v
        fired = 0
        while k < frames:
            k += 1
            fired += 1
            if dj is not None and fired == dj and jumps > 0:
                vy = me.djump_v
                jumps -= 1
            gx = goal.pos(t0 + k)[0] + goal.w * (0.5 + self.aim)
            d = gx - x
            if abs(d) > 2:
                vx = max(-me.air_max, min(me.air_max, vx + S.AIR_ACC * (1 if d > 0 else -1)))
            else:
                vx *= 0.96
            if vy < S.FALL_MAX:
                vy = min(S.FALL_MAX, vy + g)
            py = y
            x += vx
            y += vy
            if hazards and k % 2 == 0:
                box = (x - hw, y - hh, x + hw, y)
                for h in hazards:
                    if h.hit(box, t0 + k) is not None:
                        return None
            if vy >= 0:
                best = None
                for p in cands:
                    px0, pyy = p.pos(t0 + k)
                    ppy = p.pos(t0 + k - 1)[1]
                    if px0 + 2 <= x <= px0 + p.w - 2 and py <= ppy + 0.01 and y >= pyy and p.lit(t0 + k):
                        if best is None or pyy < best[1]:
                            best = (p, pyy)
                if best is not None:
                    return best[0]
            if y > ymax or x < xmin or x > xmax:
                return None
        return None

    def _cands(self, y):
        return [p for p in self.sc.plats if p.active(self.sc.course_t) and y - 140 < p.y < y + 240]

    def _hazards(self, y):
        """The obstacles this racer bothers to look out for (sloppy ones miss some)."""
        if self.rng.random() > 0.35 + 0.65 * self.skill:
            return ()
        return [h for h in self.sc.hazards if y - 170 < h.y < y + 60]

    def _hurts(self, x, hz, ahead):
        me = self.me
        box = (x - me.half_w, me.y - me.hgt, x + me.half_w, me.y)
        t = self.sc.course_t
        return any(h.hit(box, t + k) is not None for h in hz for k in ahead)

    def _dodge(self, cur):
        """Standing in the way of something about to swing through: step aside (-1/1), or None."""
        me = self.me
        if self.sc.course_t % 3 or self.rng.random() > 0.4 + 0.6 * self.skill:
            return self._dodging
        self._dodging = None
        hz = [h for h in self.sc.hazards if abs(h.y - me.y) < 110]
        ahead = (3, 6, 9, 12, 16, 20)
        if not hz or not self._hurts(me.x, hz, ahead):
            return None
        for dx in (14, -14, 28, -28, 44, -44):
            x = me.x + dx
            if cur.x0 + 4 <= x <= cur.x1 - 4 and not self._hurts(x, hz, ahead):
                self._dodging = 1 if dx > 0 else -1
                return self._dodging
        return 0                        # nowhere to step: hop over it

    def _try_jump(self, from_plat):
        """A jump from here that lands further up the course: (goal, dj) or None."""
        me = self.me
        sc = self.sc
        cands = self._cands(me.y)
        hz = self._hazards(me.y)
        goals = [p for p in sc.plats[from_plat.idx + 1:from_plat.idx + 3]
                 if p.active(sc.course_t) and p.y < me.y + 30]
        for goal in goals:
            for dj in DJ_OPTIONS:
                hit = self.simulate(me.x, me.y, me.vx, 0.0, 1, False, goal, dj, cands, hazards=hz)
                if hit is not None and hit.idx > from_plat.idx and hit.kind != "crumble" or \
                        hit is not None and hit.kind == "crumble" and hit.idx > from_plat.idx and hit.crumble < 0:
                    return hit, dj
        return None

    def _air_plan(self):
        me = self.me
        cands = self._cands(me.y)
        best = None
        for goal in sorted(cands, key=lambda p: -p.idx)[:5]:
            for dj in ((None, 1, 6, 12) if me.jumps else (None,)):
                hit = self.simulate(me.x, me.y, me.vx + me.lvx, me.vy + me.lvy, me.jumps, True, goal, dj, cands)
                if hit is not None and (best is None or hit.idx > best[0].idx):
                    best = (hit, dj)
            if best is not None and best[0] is goal:
                break
        return best

    # --- the brain ------------------------------------------------------------
    def _think(self):
        me, rng, sc = self.me, self.rng, self.sc
        it = S.Intent()
        if me.out or me.state in ("dead", "intro", "win", "respawn") or me.done:
            return it
        if self.cool:
            self.cool -= 1
        if me.state == "prejump":
            it.up = True                        # full jump: hold up through the crouch
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
            self.stood = cur                        # just landed: take a moment
            self.settle = int(rng.randint(18, 44) * (1.6 - self.skill))
            if cur.kind in ("crumble", "blink"):
                self.settle = 0                     # no time to stand around
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
        lazy = 0.006 * (1.6 - self.skill)
        if me.rise - sc.akuma.rise > LEAD:
            lazy *= 4                               # way out in front: eases off a little
        if rng.random() < lazy:
            self.dawdle = rng.randint(10, 40)       # looks around, hesitates
        goal = sc.plats[min(len(sc.plats) - 1, cur.idx + 1)]
        self.think_t -= 1
        if self.settle:
            self.settle -= 1
        elif self.think_t <= 0:
            self.think_t = 2 if self.skill > 0.85 else 3
            if rng.random() < 0.5 + 0.5 * self.skill:
                r = self._try_jump(cur)
                if r is not None:
                    hit, dj = r
                    self.plan = dict(goal=hit, dj=dj, t=0)
                    it.up_p = it.up = True
                    self.aim = rng.uniform(-0.3, 0.3) * (1.2 - self.skill)
                    return it
        # walk to the end of this platform nearest the next one, then wait for it
        gx = goal.cx
        lo, hi = cur.x0 + 7, cur.x1 - 7
        if cur.kind == "floor":
            lo, hi = 6, CW - 6
        tx = max(lo, min(hi, gx))
        if cur.kind == "crumble" and cur.crumble >= 0:
            tx = gx                                  # it's going: just go
        if abs(tx - me.x) > 3:
            d = 1 if tx > me.x else -1
            it.left, it.right = d < 0, d > 0
        elif cur.belt:
            d = -1 if cur.belt > 0 else 1
            it.left, it.right = d < 0, d > 0
        return it

    def _fly(self, it):
        me = self.me
        if me.helpless:
            d = 1 if CW / 2 > me.x else -1
            it.left, it.right = d < 0, d > 0
            return it
        p = self.plan
        if p is not None:
            p["t"] += 1
            goal = p["goal"]
            gx = goal.pos(self.sc.course_t)[0] + goal.w * (0.5 + self.aim)
            if p["dj"] is not None and p["t"] == p["dj"] and me.jumps:
                it.up_p = it.up = True
            if me.lvx or me.lvy or p["t"] > 160:
                self.plan = None
        else:
            if self.sc.t % 4 == 0 or me.t < 2:
                r = self._air_plan()
                if r is not None:
                    hit, dj = r
                    self.plan = dict(goal=hit, dj=dj, t=0)
                    if dj == 1 and me.jumps:
                        it.up_p = it.up = True
                    gx = hit.cx
                else:
                    gx = CW / 2
                    if me.jumps and me.vy > 0 and not me.lvx:
                        it.up_p = it.up = True
                    elif (not me.upb_used and me.vy > 1.5 and (me.x < 30 or me.x > CW - 30)
                          and self.rng.random() < 0.3):
                        d = 1 if CW / 2 > me.x else -1
                        it.left, it.right = d < 0, d > 0
                        self._special(it, "up")
                        return it
            else:
                gx = CW / 2
        d = gx - me.x
        if abs(d) > 2:
            it.left, it.right = d < 0, d > 0
        return it

    def _fight(self, it):
        """Take a swing at a rival who is right there (not too often: it's a race)."""
        me, rng = self.me, self.rng
        if self.cool or me.state not in ("stand", "air"):
            return False
        near = None
        for o in self.sc.fighters:
            if o is me or not o.on_field or o.invulnerable() or o.done:
                continue
            if abs(o.y - me.y) < 22 and abs(o.x - me.x) < 40:
                if near is None or abs(o.x - me.x) < abs(near.x - me.x):
                    near = o
        if near is None:
            return False
        if rng.random() > 0.025 * self.aggr * (1.6 if near.is_player else 1.0):
            return False
        adx = abs(near.x - me.x)
        d = (1 if near.x > me.x else -1)
        if me.airborne:
            if me.helpless or self.plan is None:
                return False
            it.left, it.right = d < 0, d > 0
            setattr(it, rng.choice(("punch", "kick")), True)
            self.cool = rng.randint(30, 60)
            return True
        if self._ground_attack(it, near, adx, d):
            self.cool = max(self.cool, rng.randint(24, 60))
            return True
        return False


# --------------------------------------------------------------------------
# art
# --------------------------------------------------------------------------
_ART = None


def _sky():
    """The tall backdrop: sky that gets brighter higher up, clouds, distant balloons."""
    s = pygame.Surface((CW, CH))
    top, mid, bot = (120, 200, 255), (160, 140, 240), (250, 150, 190)
    for y in range(CH):
        k = y / CH
        c = mix(top, mid, k / 0.6) if k < 0.6 else mix(mid, bot, (k - 0.6) / 0.4)
        s.fill(c, (0, y, CW, 1))
    rng = random.Random(7)
    for _ in range(46):                 # puffy clouds
        x, y = rng.randint(-30, CW), rng.randint(0, CH)
        w = rng.randint(40, 90)
        c = mix(s.get_at((max(0, min(CW - 1, x)), y))[:3], (255, 255, 255), 0.55)
        for k in range(5):
            r = rng.randint(8, 16)
            pygame.draw.circle(s, c, (x + k * w // 5, y + rng.randint(-4, 4)), r)
    for _ in range(26):                 # balloons drifting in the distance
        x, y = rng.randint(8, CW - 8), rng.randint(40, CH - 100)
        c = rng.choice((PINK, YELLOW, BLUE, MINT, ORANGE, PURPLE))
        c = mix(c, s.get_at((x, y))[:3], 0.45)
        pygame.draw.ellipse(s, c, (x - 4, y - 5, 8, 10))
        pygame.draw.line(s, shade(c, 0.7), (x, y + 5), (x + 1, y + 13))
    # the tower's back wall: faint scaffolding down both sides
    for x in (4, CW - 6):
        for y in range(0, CH, 6):
            s.fill(mix(s.get_at((x, y))[:3], (90, 70, 120), 0.3), (x, y, 2, 3))
    return s


def art():
    global _ART
    if _ART is None:
        _ART = dict(sky=_sky())
    return _ART


def _plat_img(p, t):
    """Draw a platform (foamy candy block) at its current place."""
    w = max(2, round(p.w))
    col = p.col or PINK
    h = 30 if p.kind == "floor" else 8
    s = pygame.Surface((w, h + 2), pygame.SRCALPHA)
    alpha = 255
    if p.kind == "blink":
        cyc = p.on_t + p.off_t
        k = (t + int(p.phase)) % cyc
        if k >= p.on_t:
            alpha = 60
        elif k > p.on_t - 24 and (k // 3) % 2:
            alpha = 150
    pygame.draw.rect(s, shade(col, 0.6), (0, 2, w, h), border_radius=3)
    pygame.draw.rect(s, col, (0, 0, w, h - 1), border_radius=3)
    pygame.draw.rect(s, shade(col, 1.25), (1, 0, w - 2, 2), border_radius=2)
    if p.kind == "belt":
        off = int(t * p.belt * 2) % 8
        for x in range(-8 + off, w, 8):
            pts = [(x, 3), (x + 3, 5), (x, 7)] if p.belt > 0 else [(x + 3, 3), (x, 5), (x + 3, 7)]
            pygame.draw.lines(s, shade(col, 1.5), False, pts)
    elif p.kind == "bounce":
        pygame.draw.ellipse(s, (240, 255, 240), (2, 0, w - 4, 5))
        for x in range(4, w - 3, 6):
            s.fill(shade(col, 0.5), (x, 4, 2, h - 4))
    elif p.kind == "crumble":
        for x in range(5, w - 2, 9):
            pygame.draw.line(s, shade(col, 0.55), (x, 1), (x + 2, h - 2))
    elif p.kind == "finish":
        for x in range(0, w, 6):
            for y in (2, 5):
                if ((x // 6) + (y // 3)) % 2:
                    s.fill((40, 30, 30), (x, y, 3, 3))
    elif p.kind == "floor":
        for x in range(0, w, 10):
            s.fill(shade(col, 0.8), (x, 4 + (x // 10) % 2 * 6, 6, 2))
    else:
        for x in range(4, w - 3, 10):
            s.fill(shade(col, 1.12), (x, 3, 4, 3))
    if alpha < 255:
        s.set_alpha(alpha)
    return s


def ordinal(n):
    return "%d%s" % (n, {1: "ST", 2: "ND", 3: "RD"}.get(n, "TH"))


def _fruit(surf, x, y, kind, spin):
    x, y = round(x), round(y)
    if kind == "melon":
        pygame.draw.circle(surf, OUTLINE, (x, y), 7)
        pygame.draw.circle(surf, (60, 170, 60), (x, y), 6)
        for k in range(3):
            a = spin / 6 + k * 2.1
            pygame.draw.line(surf, (30, 110, 40), (x, y), (x + round(math.cos(a) * 5), y + round(math.sin(a) * 5)))
    elif kind == "apple":
        pygame.draw.circle(surf, OUTLINE, (x, y), 6)
        pygame.draw.circle(surf, (220, 40, 40), (x, y), 5)
        surf.fill((90, 60, 30), (x, y - 7, 1, 3))
        surf.fill((255, 160, 160), (x - 2, y - 3, 2, 2))
    else:
        pygame.draw.circle(surf, OUTLINE, (x, y), 6)
        pygame.draw.circle(surf, (255, 150, 30), (x, y), 5)
        surf.fill((255, 210, 120), (x - 2, y - 3, 2, 2))
        surf.fill((60, 150, 50), (x, y - 6, 2, 2))


# --------------------------------------------------------------------------
# the level
# --------------------------------------------------------------------------
class ClimbScene(S.SmashScene):
    def __init__(self, game, seed=None, level=11, hp=None):
        F.init_shared()
        self.game = game
        self.level = level
        self.rng = random.Random(seed)
        self.max_hp = getattr(game, "akuma_max", AKUMA_MAX_HP)
        self.hp = self.max_hp if hp is None else hp
        self.menu = PauseMenu(game, CONTROLS)
        self.art = S.stage_art()                # hit sparks etc. from the Smash level
        self.look = art()
        self.roster = self.rng.sample(CPU_POOL, RIVALS)
        self.cpu_enabled = True
        self.items_enabled = False
        self.items = []
        self.round = 1
        self.tries = []                         # winner's name per finished try
        self._reach = {}
        self.t = 0
        self.result = None
        self.fighters = []
        self._start_round()

    def _start_round(self):
        self.plats, self.hazards, self.finish = build_course()
        self.solids = []
        self.sim_box = (-20, CW + 20, FLOOR + 10)          # the jump planner gives up outside this
        self._ledges = [p for p in self.plats if p.ledges]
        cast = ["akuma"] + list(self.roster)
        self.fighters = [Climber(self, c, i, i == 0) for i, c in enumerate(cast)]
        self.akuma = self.fighters[0]
        n = len(self.fighters)
        order = list(range(n))
        self.rng.shuffle(order)
        for k, f in zip(order, self.fighters):
            f.x, f.y = 40.0 + k * (CW - 80) / (n - 1), float(FLOOR)
            f.on = self.plats[0]
            f.facing = 1 if f.x < CW / 2 else -1
        skills = SKILLS[:n - 1]
        self.rng.shuffle(skills)
        self.brains = {f: ClimbBrain(self, f, random.Random(self.rng.random()), sk)
                       for f, sk in zip(self.fighters[1:], skills)}
        self.shots = []
        self.effects = []
        self.parts = []
        self.blasts = []
        self.booms = []
        self.popups = []
        self.phase = "intro"
        self.end_t = 0
        self.shake = 0
        self.flash = 0
        self.won = None
        self.winner = None
        self.hits = {}                          # (obstacle, fighter) -> frame of the last hit
        self.announced = set()
        self.camy = float(R(FINISH_RISE) - 70)
        self.play_t = -999
        self.course_t = 0
        for f in self.fighters:
            f.refresh()

    @property
    def intro_len(self):
        return INTRO if self.round == 1 else INTRO - 120

    @property
    def cpus(self):
        return self.fighters[1:]

    # ---- the course ------------------------------------------------------------
    def stands(self, p, x, y):
        return p.active(self.course_t) and p.x0 - 3 <= x <= p.x1 + 3 and abs(y - p.y) < 0.5

    def ground(self, x, y):
        for p in self.plats:
            if self.stands(p, x, y):
                return p
        return None

    def landing(self, x, py, y, drop=False):
        """The platform a fall from py to y (at x) lands on, if any."""
        best = None
        for p in self.plats:
            if drop and p.kind != "floor":
                continue
            if not p.active(self.course_t) or not (p.x0 - 3 <= x <= p.x1 + 3):
                continue
            if py <= p.py + 0.01 and y >= p.y:
                if best is None or p.y < best.y:
                    best = p
        return best

    def ledges(self):
        return [p for p in self._ledges if p.active(self.course_t)]

    def stepped(self, f, p):
        """Someone landed on p."""
        if p.kind == "crumble" and p.crumble < 0:
            p.crumble = 34
        elif p.kind == "bounce":
            if f.state == "move":
                f.move = None
                f.move_vx = None
            f.vy = BOUNCE_V
            f.airborne = True
            f.on = None
            f.state, f.t = "air", 0
            f.jumps = 1
            audio.play("jump", 0.9)
            self.puff(f.x, f.y)
        elif p is self.finish and self.winner is None and self.phase == "play" and f.on_field:
            self.cross(f)

    def cross(self, f):
        self.winner = f
        f.done = True
        self.won = f.is_player
        self.phase, self.end_t = "game", 0
        audio.play("encounter")
        for _ in range(40):
            self.parts.append([f.x + self.rng.uniform(-20, 20), f.y - self.rng.uniform(10, 40),
                               self.rng.uniform(-1.5, 1.5), self.rng.uniform(-3, -0.5), self.rng.randint(20, 50),
                               self.rng.choice((PINK, YELLOW, BLUE, MINT, ORANGE, PURPLE, GOLD))])

    def spawn_shot(self, f, spec):
        self.shots.append(ClimbShot(f, spec))

    def _apply_hit(self, att, vic, spec, dirx, point, grab_ok=False):
        if att is not None and "kb" in spec:
            spec = dict(spec, kb=spec["kb"] * KB_SCALE, kg=spec["kg"] * KB_SCALE)
        return super()._apply_hit(att, vic, spec, dirx, point, grab_ok)

    def respawn(self, f):
        """Back on the floor at 0%, a little way above it."""
        f.x = self.rng.uniform(40, CW - 40)
        f.y = float(FLOOR - 50)
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
        if f in self.brains:
            self.brains[f].plan = None

    def ko(self, f):
        """Knocked off the tower: a blast where they left the screen, then back to the bottom."""
        rc = self.cam_rect()
        bx = max(rc.left, min(rc.right, f.x))
        by = max(rc.top, min(rc.bottom, f.y - f.hgt / 2))
        ang = math.atan2(rc.centery - by, rc.centerx - bx)
        if rc.collidepoint(bx, by) or abs(f.y - rc.centery) < H:
            self.blasts.append([bx, by, ang, f.color, 0])
            for _ in range(20):
                a = ang + self.rng.uniform(-0.7, 0.7)
                sp = self.rng.uniform(1.5, 5)
                self.parts.append([bx, by, math.cos(a) * sp, math.sin(a) * sp, self.rng.randint(14, 30),
                                   self.rng.choice((f.color, (255, 255, 255), (255, 230, 120)))])
            self.shake = 10
            audio.play("boom", 0.7)
        if f.is_player:
            audio.play("ko", 0.6)
        if f.grabbed:
            self.drop_grab(f)
        if f.held_by is not None:
            f.held_by.grabbed = None
            f.held_by = None
        if f.last_hit_by is not None and self.t - getattr(f, "hit_t", -9999) <= 600:
            f.last_hit_by.ko_count += 1
        f.falls += 1
        f.state, f.t = "dead", 0
        f.move = None
        f.draw_key = None
        f.on = None
        f.last_hit_by = None

    def _blast_zones(self):
        for f in self.fighters:
            if f.state in ("dead", "intro"):
                continue
            if f.x < BLAST_L or f.x > BLAST_R or f.y > BLAST_B or f.y < BLAST_T:
                self.ko(f)

    def _separate(self):
        fs = [f for f in self.fighters if f.on_field and not f.airborne
              and f.state not in ("held", "move", "hitstun")]
        for i, a in enumerate(fs):
            for b in fs[i + 1:]:
                dx = b.x - a.x
                if abs(dx) < 10 and abs(a.y - b.y) < 1:
                    push = 0.5 * (S.sign(dx) or (1 if a.slot < b.slot else -1))
                    for f, d in ((a, -push), (b, push)):
                        nx = f.x + d
                        if f.on is not None and self.stands(f.on, nx, f.y):
                            f.x = nx

    def _obstacles(self):
        for h in self.hazards:
            h.update(self.course_t)
        for f in self.fighters:
            if not f.on_field or f.invulnerable() or f.done or f.state == "held":
                continue
            box = (f.x - f.half_w, f.y - f.hgt, f.x + f.half_w, f.y)
            for h in self.hazards:
                if abs(getattr(h, "y", f.y) - f.y) > 120:
                    continue
                last = self.hits.get((id(h), f))
                if last is not None and self.course_t - last < HAZARD_CD:
                    continue
                r = h.hit(box)
                if r is None:
                    continue
                spec, d, pt = r
                self.hits[(id(h), f)] = self.course_t
                self._apply_hit(None, f, spec, d, pt)
                if h.kind == "cannon":
                    h.balls = [b for b in h.balls if abs(b[0] - pt[0]) > 9 or abs(b[1] - pt[1]) > 9]
                    self.effects.append(F.Effect(F.DUST, pt[0], pt[1], 3))

    def standings(self):
        """Racers, leader first: the winner, then by height up the tower."""
        def key(f):
            if f is self.winner:
                return -1e9
            if f.state == "dead":
                return 0.0
            return -f.rise
        return sorted(self.fighters, key=key)

    def place(self, f):
        return self.standings().index(f) + 1

    # ---- update --------------------------------------------------------------
    def update(self, inp):
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.phase == "play" and self.menu.toggle(inp):
            return
        self.t += 1
        if self.shake:
            self.shake -= 1
        if self.flash:
            self.flash -= 1
        if self.phase == "final":
            self.end_t += 1
            for f in self.fighters:
                f.refresh()
            self._fx()
            skip = self.end_t > 80 and inp.any_pressed("punch", "kick", "special", "start")
            if (self.end_t >= FINAL_LEN or skip) and self.result is None:
                self._finish()
            return
        self.course_t += 1
        for p in self.plats:
            p.update(self.course_t)
        if self.phase == "intro":
            self.end_t += 1
            n = self.intro_len
            if self.end_t in (n - 90, n - 60, n - 30):
                audio.play("beep")
            for h in self.hazards:
                h.update(self.course_t)
            for f in self.fighters:
                f.x += f.on.dx if f.on else 0.0
                f.refresh()
            if self.end_t >= n:
                self.phase, self.end_t = "play", 0
                self.play_t = self.t
                audio.play("fight")
                for f in self.fighters:
                    f.state, f.t = "stand", 0
            self._fx()
            self._camera()
            return
        intents = {}
        if self.phase in ("play", "game"):
            if self.phase == "play":
                intents[self.akuma] = S.Intent.from_input(inp)
            if self.cpu_enabled:
                for f, b in self.brains.items():
                    if self.phase == "play" or not f.done:
                        intents[f] = b.think()
        for f in self.fighters:
            f.update(intents.get(f, S.NO_INPUT))
        self._holds()
        self._separate()
        for s in self.shots:
            s.update()
        for f in self.fighters:
            f.refresh()
        self._hits()
        self.shots = [s for s in self.shots if s.alive]
        self._obstacles()
        self._blast_zones()
        self._announce()
        self._fx()
        self._camera()
        if self.phase == "game":
            self.end_t += 1
            w = self.winner
            if w is not None and w.state == "stand" and not w.airborne and self.end_t > 20:
                w.state, w.t = "win", 0
                w.vx = 0.0
            skip = self.end_t > 120 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= GAME_LEN or skip:
                self.tries.append(w.name if w else "")
                if self.won or self.round >= TRIES:
                    self.phase, self.end_t = "final", 0
                    audio.play("encounter" if self.won else "ko", 0.7)
                else:
                    self.round += 1
                    self._start_round()

    def _announce(self):
        """Call out the hard spots the first time Akuma reaches one."""
        ak = self.akuma
        for lo, hi, name in HARD:
            if name not in self.announced and ak.on_field and lo - 30 <= ak.rise <= hi:
                self.announced.add(name)
                self.popups.append(["HARD: " + name, ak.x, ak.y - ak.hgt - 10, 90, (255, 120, 90)])

    def _finish(self):
        if self.won:                            # round 2: the spike run, same rivals
            self.result = "win"
            from .spikerun import SpikeRunScene
            self.game.scene = SpikeRunScene(self.game, self.rng.random(), self.level, self.hp, self.roster)
        else:
            self.result = "lose"
            self.game.level_failed(self)

    # ---- camera ----------------------------------------------------------------
    def _cam_goal(self):
        if self.phase == "intro":
            k = min(1.0, self.end_t / FLY)
            k = k * k * (3 - 2 * k)
            top = R(FINISH_RISE) - 70
            return top + (FLOOR - H / 2 - 20 - top) * k
        f = self.akuma
        if self.phase in ("game", "final") and self.winner is not None and not self.won:
            f = self.winner if self.end_t < 120 else self.akuma
        if f.state == "dead":
            return self.camy
        return f.y - 44

    def _camera(self):
        goal = self._cam_goal()
        if self.phase == "intro":
            self.camy = goal
        else:
            d = goal - self.camy
            self.camy += d * (0.12 if abs(d) < 200 else 0.3)
        self.camy = max(H / 2 - 40, min(FLOOR - 62, self.camy))
        self.cam = [CW / 2, self.camy, float(W)]

    def cam_rect(self):
        y = int(round(self.camy - H / 2))
        return pygame.Rect(0, y, W, H)

    def to_screen(self, x, y, rect=None):
        r = rect or self.cam_rect()
        return x - r.x, y - r.y

    # ---- draw ----------------------------------------------------------------
    def draw(self, surf):
        sh = [0, 0]
        if self.shake:
            m = 1 + self.shake // 5
            sh = [self.rng.randint(-m, m), self.rng.randint(-m, m)]
        rc = self.cam_rect()
        sky = self.look["sky"]
        top = max(0, rc.y)
        surf.fill((120, 200, 255))
        surf.blit(sky, (0, top - rc.y), pygame.Rect(0, top, W, min(H, CH - top)))
        o = (sh[0] - rc.x, sh[1] - rc.y)          # world -> screen offset
        t = self.course_t
        lo, hi = rc.top - 40, rc.bottom + 40
        for p in self.plats:
            if lo < p.y < hi:
                self._draw_plat(surf, p, o, t)
        self._draw_finish_gate(surf, o)
        for h in self.hazards:
            self._draw_hazard(surf, h, o, lo, hi)
        order = sorted(self.fighters, key=lambda f: (f.is_player, f.state == "held"))
        for f in order:
            if lo - 40 < f.y < hi + 40:
                self._draw_fighter(surf, f, o)
        for s in self.shots:
            img, _, (px, py) = s.frame()
            surf.blit(img, (px + o[0], py + o[1]))
        for fx in self.effects:
            fx.draw(surf, o)
        for p in self.parts:
            surf.fill(p[5], (round(p[0]) + o[0], round(p[1]) + o[1], 2, 2))
        self._draw_blasts_screen(surf, rc)
        for f in self.fighters:
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

    def _draw_plat(self, surf, p, o, t):
        if p.kind == "crumble" and p.gone > 0:
            if p.gone > 170:                      # falling bits
                k = 200 - p.gone
                for i in range(4):
                    surf.fill(shade(p.col, 0.8), (round(p.x0 + i * p.w / 4) + o[0], round(p.y + k * k * 0.05) + o[1],
                                                  round(p.w / 4) - 1, 5))
            return
        img = _plat_img(p, t)
        x, y = round(p.x0) + o[0], round(p.y) + o[1]
        if p.kind == "crumble" and p.crumble > 0:
            x += (1, -1, 0)[t % 3]
        surf.blit(img, (x, y))

    def _draw_finish_gate(self, surf, o):
        p = self.finish
        x0, x1, y = round(p.x0) + o[0], round(p.x1) + o[0], round(p.y) + o[1]
        if y < -80 or y > H + 10:
            return
        for x in (x0 + 4, x1 - 8):
            for k in range(0, 54, 6):
                surf.fill((250, 250, 250) if (k // 6) % 2 else (30, 30, 40), (x, y - 54 + k, 4, 6))
        pygame.draw.rect(surf, OUTLINE, (x0 + 2, y - 66, x1 - x0 - 4, 13))
        pygame.draw.rect(surf, (240, 60, 120), (x0 + 3, y - 65, x1 - x0 - 6, 11))
        draw_text(surf, "FINISH", (x0 + x1) // 2, y - 63, (255, 255, 255), align="center")
        # the crown, bobbing above the gate
        cx = (x0 + x1) // 2
        cy = y - 84 + round(math.sin(self.t / 14) * 2)
        pts = [(cx - 9, cy + 6), (cx - 9, cy - 3), (cx - 4, cy + 1), (cx, cy - 6), (cx + 4, cy + 1),
               (cx + 9, cy - 3), (cx + 9, cy + 6)]
        pygame.draw.polygon(surf, OUTLINE, [(a, b + 1) for a, b in pts])
        pygame.draw.polygon(surf, GOLD, pts)
        surf.fill((255, 250, 180), (cx - 7, cy + 2, 14, 2))
        surf.fill((230, 40, 60), (cx - 1, cy - 1, 2, 2))
        if (self.t // 6) % 4 == 0:
            surf.fill((255, 255, 255), (cx + 5, cy - 6, 1, 3))
            surf.fill((255, 255, 255), (cx + 4, cy - 5, 3, 1))

    def _draw_hazard(self, surf, h, o, lo, hi):
        if not (lo - 80 < h.y < hi + 80):
            return
        if h.kind == "sweep":
            for sx, sy, ex, ey in h.segments():
                a, b = (round(sx) + o[0], round(sy) + o[1]), (round(ex) + o[0], round(ey) + o[1])
                pygame.draw.line(surf, OUTLINE, a, b, 7)
                pygame.draw.line(surf, (240, 70, 70), a, b, 5)
                for k in range(1, 5, 2):          # white stripes
                    p0 = (round(sx + (ex - sx) * k / 5) + o[0], round(sy + (ey - sy) * k / 5) + o[1])
                    p1 = (round(sx + (ex - sx) * (k + 1) / 5) + o[0], round(sy + (ey - sy) * (k + 1) / 5) + o[1])
                    pygame.draw.line(surf, (255, 240, 240), p0, p1, 5)
                pygame.draw.circle(surf, OUTLINE, b, 4)
                pygame.draw.circle(surf, (250, 210, 70), b, 3)
            c = (round(h.x) + o[0], round(h.y) + o[1])
            pygame.draw.circle(surf, OUTLINE, c, 6)
            pygame.draw.circle(surf, (90, 170, 250), c, 5)
            surf.fill((255, 255, 255), (c[0] - 1, c[1] - 1, 2, 2))
        elif h.kind == "pend":
            bx, by = h.ball()
            a = (round(h.x) + o[0], round(h.y) + o[1])
            b = (round(bx) + o[0], round(by) + o[1])
            pygame.draw.line(surf, (90, 80, 100), a, b, 2)
            surf.fill((60, 60, 70), (a[0] - 3, a[1] - 2, 6, 4))
            pygame.draw.circle(surf, OUTLINE, b, h.r + 1)
            pygame.draw.circle(surf, PINK, b, h.r)
            pygame.draw.circle(surf, shade(PINK, 1.3), (b[0] - 3, b[1] - 3), 3)
            for k in range(4):                    # little foam spikes
                ang = h.ang + k * math.pi / 2
                tip = (b[0] + round(math.cos(ang) * (h.r + 3)), b[1] + round(math.sin(ang) * (h.r + 3)))
                pygame.draw.line(surf, (250, 210, 70), b, tip, 2)
        elif h.kind == "piston":
            g = h.glove().move(o)
            y = round(h.y) + o[1]
            # the housing on the wall and the arm
            if h.side < 0:
                surf.fill(OUTLINE, (0, y - 16, 8, 18))
                surf.fill((120, 110, 140), (0, y - 15, 7, 16))
                if h.out > 0:
                    surf.fill((200, 200, 210), (6, y - 9, max(0, g.left - 6), 4))
            else:
                surf.fill(OUTLINE, (W - 8, y - 16, 8, 18))
                surf.fill((120, 110, 140), (W - 7, y - 15, 7, 16))
                if h.out > 0:
                    surf.fill((200, 200, 210), (g.right, y - 9, max(0, W - 6 - g.right), 4))
            if h.out > 0:
                pygame.draw.ellipse(surf, OUTLINE, g.inflate(2, 2))
                pygame.draw.ellipse(surf, (230, 40, 50), g)
                pygame.draw.ellipse(surf, (255, 120, 120), (g.x + 3, g.y + 2, 6, 4))
        elif h.kind == "cannon":
            y = round(h.y) + o[1]
            r = h.recoil // 3
            if h.side < 0:
                body = pygame.Rect(-4 - r, y - 13, 18, 12)
            else:
                body = pygame.Rect(W - 14 + r, y - 13, 18, 12)
            pygame.draw.rect(surf, OUTLINE, body.inflate(2, 2), border_radius=3)
            pygame.draw.rect(surf, (70, 70, 90), body, border_radius=3)
            surf.fill((140, 140, 170), (body.x + 2, body.y + 2, body.w - 4, 2))
            for b in h.balls:
                _fruit(surf, b[0] + o[0], b[1] + o[1], b[3], b[4])

    def _draw_fighter(self, surf, f, o):
        if f.draw_key is None:
            return
        if f.on is not None and not f.airborne:
            w = max(8, round(f.half_w * 2.4))
            pygame.draw.ellipse(surf, (30, 26, 40), (round(f.x) - w // 2 + o[0], round(f.y) - 2 + o[1], w, 4))
        img, _, _ = S.sprite(f.art, f.draw_key, f.flip, f.k)
        x, y = f.draw_pos[0] + o[0], f.draw_pos[1] + o[1]
        if f.state == "roll" and f.t % 4 < 2:
            ghost = img.copy()
            ghost.set_alpha(130)
            surf.blit(ghost, (x, y))
        elif f.flash and f.flash % 4 >= 2:
            surf.blit(S.flash_of(f.art, f.draw_key, f.flip, f.k), (x, y))
        else:
            surf.blit(img, (x, y))
            if f.helpless:
                dk = img.copy()
                dk.fill((150, 150, 170, 255), special_flags=pygame.BLEND_RGBA_MULT)
                surf.blit(dk, (x, y))
            if f.star:
                tint = S.flash_of(f.art, f.draw_key, f.flip, f.k).copy()
                tint.fill(S.STAR_COLORS[(self.t // 3) % len(S.STAR_COLORS)] + (255,),
                          special_flags=pygame.BLEND_RGBA_MULT)
                tint.set_alpha(120 if f.star > 90 or (f.star // 4) % 2 else 40)
                surf.blit(tint, (x, y))
            elif f.invuln and (self.t // 3) % 2:
                wh = S.flash_of(f.art, f.draw_key, f.flip, f.k).copy()
                wh.set_alpha(110)
                surf.blit(wh, (x, y))
        if f.state == "shield":
            r = f.shield_radius()
            cx, cy = f.center
            bub = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            hp = max(0.0, f.shield) / S.SHIELD_MAX
            col = mix((255, 60, 40), f.color, hp) if hp < 0.5 else f.color
            pygame.draw.circle(bub, col + (95,), (r + 1, r + 1), r)
            pygame.draw.circle(bub, shade(col, 1.5) + (200,), (r + 1, r + 1), r, 1)
            surf.blit(bub, (round(cx) - r - 1 + o[0], round(cy) - r - 1 + o[1]))
        if f.state == "dizzy":
            for k in range(3):
                ang = self.t / 6 + k * math.tau / 3
                sx = round(f.x + math.cos(ang) * 9) + o[0]
                sy = round(f.y - f.hgt - 4 + math.sin(ang) * 3) + o[1]
                surf.fill((255, 230, 90), (sx - 1, sy, 3, 1))
                surf.fill((255, 230, 90), (sx, sy - 1, 1, 3))

    def _draw_blasts_screen(self, surf, rc):
        if not self.blasts:
            return
        layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        for bx, by, ang, col, t in self.blasts:
            bx, by = bx - rc.x, by - rc.y
            ln = min(250, 30 + t * 16)
            wd = 6 + t * 1.2
            fade = max(0, 255 - t * 6)
            ca, sa = math.cos(ang), math.sin(ang)
            px, py = -sa, ca
            for wmul, c in ((1.0, col), (0.5, (255, 255, 200)), (0.18, (255, 255, 255))):
                w2 = wd * wmul
                pts = [(bx + px * w2 * 0.3, by + py * w2 * 0.3), (bx - px * w2 * 0.3, by - py * w2 * 0.3),
                       (bx + ca * ln - px * w2, by + sa * ln - py * w2),
                       (bx + ca * ln + px * w2, by + sa * ln + py * w2)]
                pygame.draw.polygon(layer, c + (fade,), pts)
        surf.blit(layer, (0, 0))

    def _hud(self, surf):
        places = self._panels(surf)
        self._tower_bar(surf)
        if self.phase in ("play", "game"):
            draw_text(surf, "TRY %d/%d" % (self.round, TRIES), 4, 3, (255, 255, 255))
            ak = self.akuma
            draw_text(surf, "%s PLACE" % ordinal(places[ak]), W - 14, 3, (255, 230, 120), align="right")

    def _panels(self, surf):
        """Bottom: everyone's damage %, in their colour, with their place."""
        n = len(self.fighters)
        pw = 60
        gap = (W - 8 - pw * n) // max(1, n - 1)
        y0 = H - 22
        places = {f: i + 1 for i, f in enumerate(self.standings())}
        for i, f in enumerate(self.fighters):
            x0 = 4 + i * (pw + gap)
            panel = pygame.Surface((pw, 20), pygame.SRCALPHA)
            panel.fill((12, 10, 20, 170))
            surf.blit(panel, (x0, y0))
            pygame.draw.rect(surf, f.color, (x0, y0, pw, 20), 1)
            surf.blit(S.small_portrait(f.cid, 16), (x0 + 2, y0 + 2))
            draw_text(surf, ordinal(places[f]), x0 + 21, y0 + 2, f.color)
            p = int(f.pct)
            jx = self.rng.randint(-1, 1) if f.dmg_shake else 0
            if f.out:
                draw_text(surf, "OUT", x0 + pw - 3, y0 + 11, (150, 150, 160), align="right")
            elif f.state == "dead":
                draw_text(surf, "OFF!", x0 + pw - 3, y0 + 11, (255, 120, 120), align="right")
            else:
                draw_text(surf, "%d%%" % p, x0 + pw - 3 + jx, y0 + 11, S.pct_color(p), align="right")
        return places

    def _tower_bar(self, surf):
        """Right edge: the tower, with a dot for each racer and the hard spots marked."""
        bx, by0, by1 = W - 8, 18, H - 30
        pygame.draw.rect(surf, OUTLINE, (bx - 2, by0 - 2, 5, by1 - by0 + 4))
        surf.fill((70, 60, 100), (bx - 1, by0 - 1, 3, by1 - by0 + 2))

        def ry(rise):
            return round(by1 - (by1 - by0) * max(0.0, min(1.0, rise / FINISH_RISE)))
        for lo, hi, _ in HARD:
            surf.fill((240, 80, 80), (bx - 1, ry(hi), 3, max(1, ry(lo) - ry(hi))))
        surf.fill(GOLD, (bx - 3, by0 - 4, 7, 3))
        for f in sorted(self.fighters, key=lambda f: f.is_player):
            if f.state == "dead":
                continue
            yy = ry(f.rise)
            pygame.draw.rect(surf, OUTLINE, (bx - 4, yy - 2, 9, 5))
            surf.fill(f.color, (bx - 3, yy - 1, 7, 3))

    def _overlays(self, surf):
        cx = W // 2
        if self.phase == "intro":
            n = self.end_t
            L = self.intro_len
            if n < L - 90:
                self._band(surf, 26, 54)
                if self.round == 1:
                    draw_text(surf, "LEVEL %d" % self.level, cx, 30, (255, 220, 80), scale=2, align="center")
                    draw_text(surf, LEVEL_NAME, cx, 48, (255, 255, 255), align="center")
                    draw_text(surf, "RACE TO THE CROWN AT THE TOP", cx, 59, (180, 220, 255), align="center")
                    draw_text(surf, "KNOCKED OFF? BACK TO THE BOTTOM", cx, 69, (255, 190, 150), align="center")
                else:
                    draw_text(surf, "TRY %d OF %d" % (self.round, TRIES), cx, 34, (255, 220, 80), scale=3,
                              align="center")
                    draw_text(surf, "WIN THE CROWN THIS TIME", cx, 62, (255, 255, 255), align="center")
            else:
                k = 3 - (n - (L - 90)) // 30
                if k >= 1:
                    draw_text(surf, str(k), cx, 50, (255, 230, 90), scale=5, align="center")
        if self.phase == "play" and self.t - self.play_t < 45:
            draw_text(surf, "GO!", cx, 46, (255, 70, 40), scale=5, align="center")
        if self.phase == "game":
            w = self.winner
            self._band(surf, 40, 40)
            if self.won:
                draw_text(surf, "QUALIFIED!", cx, 44, (255, 230, 80), scale=3, align="center")
                draw_text(surf, "AKUMA TAKES THE CROWN", cx, 68, (255, 255, 255), align="center")
            else:
                draw_text(surf, "%s WINS" % (w.name if w else "NOBODY"), cx, 44, (255, 255, 255), scale=2,
                          align="center")
                nxt = "TRY AGAIN!" if self.round < TRIES else "OUT OF TRIES"
                draw_text(surf, "AKUMA IS ELIMINATED - " + nxt, cx, 66, (255, 140, 120), align="center")
        if self.phase == "final":
            self._band(surf, 22, 78, 205)
            draw_text(surf, "RESULTS", cx, 26, (255, 220, 80), scale=2, align="center")
            for k, name in enumerate(self.tries):
                txt = "TRY %d:  %s" % (k + 1, (name or "-") + " WINS")
                draw_text(surf, txt, cx, 45 + k * 9, (255, 120, 90) if name == "AKUMA" else (170, 170, 190),
                          align="center")
            if self.won:
                draw_text(surf, "ON TO ROUND 2!", cx, 80, (255, 80, 60), scale=2, align="center")
            else:
                draw_text(surf, "AKUMA IS ELIMINATED", cx, 80, (200, 200, 220), scale=2, align="center")
