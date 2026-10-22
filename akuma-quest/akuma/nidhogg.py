"""Level 11, the Hall of Blades: every battle is a Nidhogg-style sabre duel.

One touch of a blade kills. The enemy dies once and the duel is won; Akuma
has 5 hearts for the whole level (his map hp, in fifths): each death costs a
heart and the duel restarts from en garde, and at 0 hearts the run is lost.

Rules (keys as everywhere else: arrows/WASD, J punch, K kick):
  left/right walk (disarmed fighters run faster), down ducks, up+move jumps;
  standing still, tap up/down to carry the sabre high/mid/low, hold up at high
  to raise it aloft; at low, down ducks; move+down rolls, and ducking moves crawl.
  J  lunge (armed) / dive-kick (air) / punch (disarmed) / snap the neck of a
     downed foe; J while aloft throws.
  K  throw the sabre / trip when ducked or rolling.
  Blades at the same height clink and push apart; a lunge into a sabre held at
  its height is parried; moving your blade onto theirs when it is more than
  half-way past yours disarms them; anything that runs, rolls or jumps into a
  blade is skewered. Thrown sabres fly straight until they hit a wall, a body
  or a mid/high guard. Dive kicks and two punches knock down; a high sabre
  skewers dive kicks. Downed fighters get up with up or roll up with
  left/right (rolling over a sabre picks it up).

Hits are pixel exact: the drawn blade line against the drawn sprite's mask.
"""

import math
import random
from collections import deque

import pygame

from . import audio
from .akuma_sprites import CharArt
from .config import W, H
from .fighters import touches
from .font import draw_text
from .pause import PauseMenu

# ---- arena and body geometry (px; heights measured up from the feet) -------
FLOOR_Y = 154
WALL_L, WALL_R = 16, W - 16        # where feet stop
HS = 44                            # a fighter's standing height on screen
BOSS_HS = 49
HAND = 14                          # feet to sword hand, forward
BLADE = 20                         # blade length
LUNGE_EXT = 24                     # how far a lunge thrusts the hand: from blades
                                   # crossed at the tips it reaches the body
HEIGHT_Y = (12, 27, 37)            # sabre low / mid / high
DUCK_Y = 9                         # the sabre of a ducking fighter
DUCK_H = 28                        # a ducking body is no taller than this
ROLL_D = 18                        # a rolling body is a ball this big
THROW_MIN_Y = 31                   # thrown sabres fly at least this high (ducking dodges)
FOOT = 13                          # dive-kick foot box

WALK = 1.1
RUN = 2.0
CRAWL = 0.55
ROLL_V = 2.3
ROLL_T = 22
JUMP_VY = -4.6
GRAV = 0.25
DIVE_V = 2.7
LUNGE_PROFILE = (9, 17, 22, 24, 24, 24, 22, 18, 14, 10, 6, 3, 1, 0, 0)
LUNGE_RELUNGE = 8                  # frames before another lunge can inch forward
LUNGE_STEP = 0.6                   # advance per frame over the first 5 frames
THROW_V = 4.0
STUN = 30                          # pancake flop before a downed fighter may get up
SNAP_RANGE = 22
SNAP_KILL = 9
ALOFT_HOLD = 10
PUNCH_COMBO = 60                   # second punch within this many frames knocks down
HEARTS = 5
P_START, E_START = 92.0, 228.0

CONTROLS = ["LEFT/RIGHT MOVE  DOWN DUCK  UP + MOVE JUMP",
            "STANDING: TAP UP/DOWN = SABRE HIGH/MID/LOW",
            "HOLD UP AT HIGH = SABRE ALOFT (J THROWS)",
            "J: LUNGE / AIR: DIVE KICK / UNARMED: PUNCH",
            "J BY A DOWNED FOE: SNAP NECK",
            "K: THROW SABRE / DUCKED OR ROLLING: TRIP",
            "MOVE + DOWN: ROLL   DOWN ON A SABRE: PICK UP",
            "SAME HEIGHT PARRIES - CROSS OVER TO DISARM",
            "KNOCKED DOWN: UP STANDS, LEFT/RIGHT ROLLS",
            "ONE TOUCH KILLS - AKUMA HAS 5 HEARTS"]

SABRE_C = (226, 236, 255)
SABRE_HI = (255, 255, 255)
GUARD_C = (230, 182, 60)
GRIP_C = (90, 52, 36)


def sign(v):
    return (v > 0) - (v < 0)


# ---- sounds (built here so audio.py stays untouched) ------------------------
_SFX_DONE = False


def _build_sfx():
    global _SFX_DONE
    if _SFX_DONE:
        return
    _SFX_DONE = True
    if not getattr(audio, "_ok", False):
        return
    try:
        A, S = audio, audio._sfx
        S["nid_clink"] = A._sound(A._add(A._tone(2650, 2500, 0.16, 0.16, "sine"),
                                         A._add(A._tone(3970, 3800, 0.11, 0.1, "sine"),
                                                A._noise(0.03, 0.25, 3.0, 0.95))))
        S["nid_parry"] = A._sound(A._add(A._tone(1900, 1700, 0.2, 0.2, "sine"),
                                         A._add(A._tone(2850, 2600, 0.14, 0.12, "sine"),
                                                A._noise(0.05, 0.35, 2.5, 0.9))))
        S["nid_disarm"] = A._sound(A._seq(A._tone(3100, 2900, 0.07, 0.18, "sine"),
                                          A._tone(1500, 900, 0.18, 0.18, "square", 0.1, 0.3)))
        S["nid_stab"] = A._sound(A._add(A._noise(0.18, 0.6, 2.2, 0.7), A._tone(900, 120, 0.16, 0.3, "square", 0.2)))
        S["nid_throw"] = A._sound(A._add(A._noise(0.2, 0.3, 1.0, 0.12), A._tone(500, 900, 0.18, 0.12, "tri")))
        S["nid_snap"] = A._sound(A._seq(A._noise(0.03, 0.6, 4.0, 0.95), A._noise(0.05, 0.4, 3.0, 0.6)))
        S["nid_heart"] = A._sound(A._seq(A._tone(660, 640, 0.12, 0.22, "tri"), A._tone(440, 420, 0.12, 0.22, "tri"),
                                         A._tone(294, 280, 0.3, 0.22, "tri")))
        S["nid_garde"] = A._sound(A._seq(A._tone(2650, 2500, 0.08, 0.14, "sine"),
                                         A._tone(3200, 3050, 0.2, 0.14, "sine")))
    except Exception:       # a sound we could not build just stays silent
        pass


def play(name, vol=1.0):
    audio.play(name, vol)


# ---- art ------------------------------------------------------------------
def _snap(img):
    """Hard pixel edges after a smooth scale: alpha > 127 becomes solid."""
    m = pygame.mask.from_surface(img, 127)
    rgb = img.copy()
    rgb.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MAX)
    return m.to_surface(setsurface=rgb, unsetcolor=(0, 0, 0, 0)), m


def _bbox(m):
    rs = m.get_bounding_rects()
    return rs[0].unionall(rs) if rs else pygame.Rect(0, 0, 1, 1)


class DuelArt:
    """A sprite-pack character drawn small for the duel. get() returns
    (image, anchor, mask) for a drawing; modes: None, "duck" (squashed to
    DUCK_H), ("roll", step) (a ball rotated step*30 degrees)."""

    _shared = {}

    def __init__(self, cid, target_h=HS):
        self.src = CharArt(cid)
        self.cid = self.src.cid
        idle = self.src.resolve("idle")
        self.k = target_h / max(1, self.src.anchor(idle)[1] - _bbox(self.src.mask(idle)).top)
        key = (self.cid, target_h)
        if key not in DuelArt._shared:
            DuelArt._shared[key] = {}
        self._c = DuelArt._shared[key]

    def key(self, pose, t=0, clock=0):
        return self.src.resolve(pose, t, clock)

    def get(self, key, flip=False, mode=None):
        ck = (key, flip, mode)
        e = self._c.get(ck)
        if e is not None:
            return e
        if flip:
            img, (ax, ay), _ = self.get(key, False, mode)
            img = pygame.transform.flip(img, True, False)
            e = (img, (img.get_width() - ax, ay), pygame.mask.from_surface(img, 127))
        else:
            img0, (ax0, ay0) = self.src.base[key]
            w0, h0 = img0.get_size()
            r = _bbox(pygame.mask.from_surface(img0, 127))
            if mode is None or mode == "duck":
                kx = ky = self.k
                if mode == "duck":
                    ky = min(self.k, DUCK_H / max(1, ay0 - r.top))
                img = pygame.transform.smoothscale(img0, (max(1, round(w0 * kx)), max(1, round(h0 * ky))))
                anchor = (round(ax0 * kx), round(ay0 * ky))
                img, m = _snap(img)
            else:
                crop = img0.subsurface(r).copy()
                s = (ROLL_D + 2) / max(r.w, r.h)
                img = pygame.transform.smoothscale(crop, (max(1, round(r.w * s)), max(1, round(r.h * s))))
                img, _ = _snap(img)
                img = pygame.transform.rotate(img, -30 * mode[1])
                m = pygame.mask.from_surface(img, 127)
                anchor = (img.get_width() // 2, img.get_height() // 2 + ROLL_D // 2)
            e = (img, anchor, m)
        self._c[ck] = e
        return e

    def white(self, key, flip=False, mode=None):
        ck = ("white", key, flip, mode)
        e = self._c.get(ck)
        if e is None:
            img, anc, m = self.get(key, flip, mode)
            e = self._c[ck] = m.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
        return e


# ---- input ------------------------------------------------------------------
class Ctrl:
    """What a fighter is told to do this frame (the player's Input has the same
    held()/pressed() interface)."""

    def __init__(self, held=(), pressed=()):
        self.h = set(held)
        self.p = set(pressed)

    def held(self, a):
        return a in self.h

    def pressed(self, a):
        return a in self.p


NO_INPUT = Ctrl()


# ---- one fighter -------------------------------------------------------------
class Duelist:
    BLADE_STATES = ("stand", "duck", "lunge", "parried", "air", "land", "throw", "hurt", "intro", "win")

    def __init__(self, name, art, is_player=False, speed=1.0):
        self.name = name
        self.art = art
        self.is_player = is_player
        self.speed = speed
        self.reset(P_START if is_player else E_START, 1 if is_player else -1)

    def reset(self, x, facing):
        self.x, self.y = float(x), float(FLOOR_Y)
        self.vx = self.vy = 0.0
        self.facing = facing
        self.state, self.t = "intro", 0
        self.armed = True
        self.height = 1
        self.aloft = False
        self.up_hold = self.down_hold = 0
        self.ext = 0
        self.punched = 0          # punches taken recently
        self.punch_clock = 0
        self.dead = False
        self.roll_dir = 0
        self.dove = False
        self.hit_done = False
        self.blade_flash = 0
        self.flash = 0
        self.walked = 0.0
        self.victim = None

    # ---- geometry --------------------------------------------------------
    @property
    def on_ground(self):
        return self.state not in ("air", "dive")

    @property
    def ducking(self):
        return self.state == "duck"

    @property
    def blade_active(self):
        return self.armed and not self.dead and not self.aloft and self.state in self.BLADE_STATES

    @property
    def guard(self):
        """Height index the blade guards at (a ducking fighter's is low)."""
        return 0 if self.ducking else self.height

    def hand(self):
        if self.ducking:
            hy = self.y - DUCK_Y
        else:
            hy = self.y - HEIGHT_Y[self.height]
        return self.x + self.facing * (HAND + self.ext), hy

    def tip(self):
        hx, hy = self.hand()
        return hx + self.facing * BLADE, hy

    def reach(self):
        """Distance from the feet to the blade tip, forward."""
        return HAND + self.ext + BLADE

    def blade_area(self):
        if not self.blade_active:
            return None
        hx, hy = self.hand()
        x0 = hx if self.facing > 0 else hx - BLADE
        return pygame.Mask((BLADE, 2), fill=True), round(x0), round(hy) - 1

    def look(self, clock):
        """(pose key, drawing mode) for what is on screen now."""
        s, t, a = self.state, self.t, self.art
        if s == "stand":
            if abs(self.vx) > 0.2:
                pose = "walk" if sign(self.vx) == self.facing else "walk_back"
                return a.key(pose, int(self.walked * 2), clock), None
            return a.key("idle", 0, clock), None
        if s == "duck":
            return a.key("crouch", t, clock), "duck"
        if s == "roll":
            return a.key("crouch", 0, 0), ("roll", (t // 2) % 12)
        if s == "air":
            return a.key("jump" if self.vy < 0 else "fall", t, clock), None
        if s == "dive":
            return a.key("jump_kick", 99, 0), None
        if s == "land":
            return a.key("land", t, clock), None
        if s in ("lunge", "throw"):
            return a.key("punch", 99 if self.ext >= 12 or s == "throw" else 0, 0), None
        if s == "punch":
            return a.key("punch" if 2 <= t <= 8 else "punch_prep", t, clock), None
        if s == "trip":
            return a.key("sweep", 99 if t >= 3 else 0, 0), None
        if s in ("hurt", "parried"):
            return a.key("hurt", t, clock), None
        if s == "down":
            return a.key("launch" if t < 6 else "down", t if t < 6 else 99, 0), None
        if s == "getup":
            return a.key("getup", t * 2, 0), None
        if s == "snap":
            return a.key("grab" if t < SNAP_KILL else "toss", t, 0), None
        if s == "dead":
            return a.key("launch", t, 0), None
        if s == "win":
            return a.key("victory", t, clock), None
        return a.key("idle", 0, clock), None

    def body_area(self, clock=0):
        """Where this fighter can be stabbed: the pixels of its drawing. A lunge
        and a throw are hit as the stance (the thrusting arm is the blade's);
        a dive kick's foot is a weapon, not a target."""
        if self.dead:
            return None
        if self.state in ("lunge", "throw"):
            key, mode = self.art.key("idle", 0, 0), None
        else:
            key, mode = self.look(clock)
        img, (ax, ay), m = self.art.get(key, self.facing < 0, mode)
        left, top = round(self.x) - ax, round(self.y) - ay
        if self.state == "dive":
            fx, fy, fw, fh = self.foot_rect()
            m = m.copy()
            m.erase(pygame.Mask((fw, fh), fill=True), (fx - left, fy - top))
        return m, left, top

    def foot_rect(self):
        x = self.x + (2 if self.facing > 0 else -2 - FOOT)
        return round(x), round(self.y - FOOT), FOOT + 4, FOOT

    # ---- actions -----------------------------------------------------------
    def set_state(self, s):
        self.state, self.t = s, 0
        if s != "lunge":
            self.ext = 0

    def control(self, c, sc):
        """One frame of what the fighter wants to do, per state."""
        opp = sc.other(self)
        dirx = (1 if c.held("right") else 0) - (1 if c.held("left") else 0)
        s = self.state
        self.up_hold = self.up_hold + 1 if c.held("up") else 0
        self.down_hold = self.down_hold + 1 if c.held("down") else 0
        if s == "stand":
            self._stand(c, sc, opp, dirx)
        elif s == "duck":
            self._duck(c, sc, opp, dirx)
        elif s == "air":
            if self.vx == 0 and dirx:
                self.vx = dirx * 0.6
            if c.pressed("punch") and not self.dove:
                self.facing = sign(opp.x - self.x) or self.facing
                self.dove = True
                self.set_state("dive")
                self.vx, self.vy = self.facing * DIVE_V, DIVE_V
                play("dive")
            elif c.pressed("kick") and self.armed:
                sc.throw(self)
        elif s == "lunge":
            self.ext = LUNGE_PROFILE[min(self.t, len(LUNGE_PROFILE) - 1)]
            self.vx = self.facing * LUNGE_STEP if self.t < 5 else 0.0
            if self.t >= LUNGE_RELUNGE and c.pressed("punch"):
                self.lunge(sc)
            elif self.t >= LUNGE_RELUNGE and c.pressed("kick"):
                sc.throw(self)
            elif self.t >= len(LUNGE_PROFILE):
                self.set_state("stand")
        elif s == "roll":
            self.vx = self.roll_dir * ROLL_V * self.speed
            if c.pressed("kick"):
                self.facing = self.roll_dir
                self.set_state("trip")
                self.vx = self.roll_dir * 1.2
            elif self.t >= ROLL_T:
                self.set_state("stand")
                if self.armed:
                    self.height = 0
        elif s == "trip":
            self.vx *= 0.85
            if self.t >= 18:
                self.set_state("duck" if c.held("down") else "stand")
        elif s == "punch":
            self.vx = 0.0
            if self.t >= 12:
                self.set_state("stand")
        elif s in ("throw", "land", "hurt", "parried", "getup"):
            self.vx *= 0.8
            if self.t >= {"throw": 10, "land": 14, "hurt": 16, "parried": 9, "getup": 12}[s]:
                self.set_state("stand")
        elif s == "down":
            self.vx *= 0.8
            if self.t >= STUN:
                if c.pressed("up") or c.held("up"):
                    self.set_state("getup")
                elif dirx:
                    self.roll(dirx)
        elif s == "snap":
            self.vx = 0.0
            if self.t == SNAP_KILL and self.victim is not None and self.victim.state == "down":
                play("nid_snap")
                sc.kill(self.victim, self, "snap")
            if self.t >= 26:
                self.set_state("stand")

    def _stand(self, c, sc, opp, dirx):
        if self.armed or not dirx:
            self.facing = sign(opp.x - self.x) or self.facing
        else:
            self.facing = dirx
        moving = dirx != 0
        sp = (WALK if self.armed else RUN) * self.speed
        self.vx = dirx * sp
        if not (self.armed and self.height == 2 and c.held("up") and not moving):
            self.aloft = False
        elif self.up_hold >= ALOFT_HOLD and not self.aloft:
            self.aloft = True
        if c.pressed("punch"):
            if self._near_downed(opp):
                self.snap(opp)
            elif self.aloft or not self.armed:
                if self.aloft:
                    sc.throw(self)
                else:
                    self.punch()
            else:
                self.lunge(sc)
        elif c.pressed("kick"):
            if self._near_downed(opp):
                self.snap(opp)
            elif self.armed:
                sc.throw(self)
            else:
                self.punch()
        elif c.pressed("down"):
            if moving:
                self.roll(dirx)
            elif not self.armed and sc.floor_sabre_near(self):
                sc.pick_up(self)
                self.set_state("duck")
            elif self.armed and self.height > 0 and not self.aloft:
                sc.change_height(self, self.height - 1)
            else:
                self.set_state("duck")
        elif c.pressed("up"):
            if moving or not self.armed:
                self.jump(dirx * sp)
            elif self.height < 2:
                sc.change_height(self, self.height + 1)
        elif c.held("down") and self.down_hold >= 12 and not moving and (not self.armed or self.height == 0):
            self.set_state("duck")

    def _duck(self, c, sc, opp, dirx):
        if self.armed:
            self.facing = sign(opp.x - self.x) or self.facing
        elif dirx:
            self.facing = dirx
        self.vx = dirx * CRAWL * self.speed
        if c.pressed("punch"):
            if self._near_downed(opp):
                self.snap(opp)
            elif self.armed:
                self.height = 0
                self.lunge(sc)
            else:
                self.punch()
        elif c.pressed("kick"):
            self.set_state("trip")
            self.vx = 0.0
        elif c.pressed("down") and not self.armed and sc.floor_sabre_near(self):
            sc.pick_up(self)
        elif c.pressed("up") or not c.held("down"):
            self.set_state("stand")
            if self.armed:
                self.height = 0

    def _near_downed(self, opp):
        return opp.state == "down" and not opp.dead and abs(opp.x - self.x) < SNAP_RANGE

    def lunge(self, sc):
        self.set_state("lunge")
        self.hit_done = False
        self.ext = LUNGE_PROFILE[0]
        play("whiff", 0.6)

    def punch(self):
        self.set_state("punch")
        self.hit_done = False
        play("whiff", 0.5)

    def roll(self, d):
        self.roll_dir = d
        self.facing = d
        self.aloft = False
        self.set_state("roll")
        play("sweep", 0.6)

    def jump(self, vx):
        self.set_state("air")
        self.vx, self.vy = vx, JUMP_VY
        self.dove = False
        play("jump")

    def snap(self, opp):
        self.facing = sign(opp.x - self.x) or self.facing
        self.victim = opp
        self.set_state("snap")

    def knock_down(self, sc, from_x):
        if self.dead:
            return
        if self.armed:
            sc.drop_sabre(self, toss=True)
        self.aloft = False
        self.set_state("down")
        self.y = float(FLOOR_Y)
        self.vy = 0.0
        self.vx = 1.6 * sign(self.x - from_x)
        self.punched = 0

    def physics(self):
        if self.state in ("air", "dive"):
            self.x += self.vx
            self.vy += GRAV if self.state == "air" else 0.0
            self.y += self.vy
            if self.y >= FLOOR_Y:
                self.y = float(FLOOR_Y)
                self.vy = 0.0
                if self.state == "dive":
                    self.set_state("land")
                    self.vx *= 0.3
                else:
                    self.set_state("stand")
                play("land", 0.6)
        else:
            self.x += self.vx
            if self.state == "stand":
                self.walked += abs(self.vx)
        if self.x < WALL_L or self.x > WALL_R:
            self.x = min(WALL_R, max(WALL_L, self.x))
            if self.state == "dive":
                self.vx = 0.0

    def tick(self):
        self.t += 1
        if self.blade_flash:
            self.blade_flash -= 1
        if self.flash:
            self.flash -= 1
        if self.punch_clock:
            self.punch_clock -= 1
            if not self.punch_clock:
                self.punched = 0


# ---- sabres off the hand --------------------------------------------------
class Sabre:
    """A thrown sabre (flies straight, no gravity) or a loose one (spins up,
    falls, lies on the floor waiting to be picked up)."""

    def __init__(self, x, y, vx, vy=0.0, thrown=False, owner=None):
        self.x, self.y, self.vx, self.vy = float(x), float(y), vx, vy
        self.thrown = thrown
        self.owner = owner
        self.rest = False
        self.ang = 0.0
        self.alive = True

    def drop(self, vx=None):
        self.thrown = False
        self.vx = -self.vx * 0.25 if vx is None else vx
        self.vy = -2.2

    def update(self):
        if self.rest:
            return
        self.x += self.vx
        if self.thrown:
            if self.x < WALL_L - 10 or self.x > WALL_R + 10:
                self.x = min(WALL_R + 8, max(WALL_L - 8, self.x))
                play("nid_clink", 0.6)
                self.drop()
            return
        self.vy += GRAV
        self.y += self.vy
        self.ang += 0.45
        if self.x < WALL_L or self.x > WALL_R:
            self.x = min(WALL_R, max(WALL_L, self.x))
            self.vx = -self.vx * 0.4
        if self.y >= FLOOR_Y - 1 and self.vy > 0:
            self.y = FLOOR_Y - 1
            self.rest = True
            self.ang = 0.0
            play("nid_clink", 0.4)

    def area(self):
        d = sign(self.vx) or 1
        x0 = self.x - BLADE if d > 0 else self.x
        return pygame.Mask((BLADE, 2), fill=True), round(x0), round(self.y) - 1


# ---- the CPU ----------------------------------------------------------------
class DuelAI:
    """Sees the opponent `react` frames late. Matches heights to parry, picks
    a different height to strike, lunges from just outside the other blade's
    reach, throws now and then, dive-kicks and rolls when disarmed."""

    def __init__(self, rng, boss=False, ai=None):
        ai = ai or {}
        self.rng = rng
        self.boss = boss
        r = ai.get("reaction", 6)
        self.react = 9 if boss else int(13 + r * 1.2)
        self.jumpy = 0.4 if boss else ai.get("jumpiness", 0.2)
        self.aggr = 0.9 if boss else 0.3 + 0.5 * ai.get("aggression", 0.5)
        self.parry = 0.8 if boss else 0.25 + 0.4 * ai.get("block", 0.3)
        self.throw_p = 0.006 if boss else 0.002
        self.hist = deque(maxlen=64)
        self.mode = "guard"
        self.mode_t = 0
        self.patience = self._patience()
        self.cd = 0
        self.want = 1
        self.ready = 0
        self.hesitate = self._hesitate()
        self.wait = 0

    def _hesitate(self):
        return self.rng.randint(4, 12) if self.boss else self.rng.randint(10, 28)

    def _patience(self):
        return int(self.rng.uniform(30, 110) / self.aggr)

    def seen(self):
        i = max(0, len(self.hist) - 1 - self.react)
        return self.hist[i]

    def think(self, me, opp, sc):
        self.hist.append(dict(x=opp.x, y=opp.y, h=opp.guard, armed=opp.armed, state=opp.state,
                              ext=opp.ext, vx=opp.vx, aloft=opp.aloft))
        o = self.seen()
        held, pressed = set(), set()
        if self.cd:
            self.cd -= 1
        self.mode_t += 1
        dx = o["x"] - me.x
        d = abs(dx)
        toward = "right" if dx > 0 else "left"
        away = "left" if dx > 0 else "right"
        rng = self.rng

        if me.state == "down":
            self.wait += 1
            if me.t >= STUN and self.wait > self.react:
                sab = sc.nearest_floor_sabre(me)
                if not me.armed and sab is not None and abs(sab.x - me.x) < 70:
                    held.add("right" if sab.x > me.x else "left")
                else:
                    pressed.add("up")
            return Ctrl(held, pressed)
        self.wait = 0
        if me.state not in ("stand", "duck", "air", "lunge", "roll"):
            return Ctrl(held, pressed)

        # an incoming thrown sabre: guard mid, or duck when unarmed
        for sb in sc.sabres:
            if sb.thrown and sb.owner is not me and sign(me.x - sb.x) == sign(sb.vx):
                if abs(sb.x - me.x) < THROW_V * self.react * 0.7 + 30:
                    if me.armed and me.state == "stand":
                        if me.guard == 0:
                            pressed.add("up")
                        return Ctrl(held, pressed)
                    if not me.armed and me.on_ground:
                        held.add("down")
                        return Ctrl(held, pressed)

        if me.state == "air":
            if (o["state"] != "dead" and d < 46 and me.vy > -1 and not me.dove
                    and (not o["armed"] or o["h"] < 2)):
                pressed.add("punch")
            return Ctrl(held, pressed)
        if me.state == "roll":
            if not me.armed and d < 26 and o["state"] not in ("air", "down"):
                pressed.add("kick")
            return Ctrl(held, pressed)

        # a downed opponent: walk over and finish him
        if o["state"] == "down" and opp.state == "down":
            if d < SNAP_RANGE - 4:
                if me.state == "duck":
                    pressed.add("up")
                else:
                    pressed.add("punch")
            elif me.state == "stand":
                held.add(toward)
            elif me.state == "duck":
                pressed.add("up")
            return Ctrl(held, pressed)

        if not me.armed:
            return self._unarmed(me, opp, o, sc, d, toward, away, held, pressed)

        if me.state == "duck":
            pressed.add("up")
            return Ctrl(held, pressed)
        if me.state == "lunge":
            # inch forward with another thrust while the heights still differ
            if me.t >= LUNGE_RELUNGE and o["h"] != me.guard and d < me.reach() + 30 and rng.random() < self.aggr * 0.5:
                pressed.add("punch")
            return Ctrl(held, pressed)

        # ---- armed, standing --------------------------------------------
        reach_kill = HAND + LUNGE_EXT + BLADE + 9       # where a lunge lands
        safe = HAND + BLADE + 20                          # never closer at a different height
        want = None
        move = None
        if not o["armed"]:
            want = 0 if o["state"] in ("roll", "duck") else 1
            if o["state"] == "air" and d < 90:
                want = 2
            if d > reach_kill - 2:
                move = toward
            elif me.height == want:
                pressed.add("punch")
            if d > 70 and rng.random() < self.throw_p * 6:
                pressed.add("kick")
        else:
            if o["state"] == "air" and d < 100:
                want = 2
            elif o["state"] == "roll":
                want = 0
            elif o["ext"] > 8 and d < reach_kill + 12 and rng.random() < self.parry:
                want = o["h"]          # match the lunge: parry, or disarm it
            elif self.mode == "guard":
                want = o["h"]
                self.ready = 0
                if d > 2 * (HAND + BLADE) + 3:
                    move = toward
                elif d < safe + 8 and o["h"] != me.guard:
                    move = away
                if self.mode_t > self.patience:
                    self.mode, self.mode_t = "attack", 0
                    opts = [h for h in (0, 1, 2) if h != o["h"]]
                    self.attack_h = rng.choice(opts)
                if d > 95 and rng.random() < self.throw_p * (4 if o["h"] == 0 else 1):
                    pressed.add("kick")
                elif 74 < d < 96 and o["h"] < 2 and rng.random() < self.jumpy * 0.012:
                    held.add(toward)       # leap in for a dive kick
                    pressed.add("up")
                    return Ctrl(held, pressed)
            else:   # attack: a different height, step into range, thrust
                want = self.attack_h
                if want == o["h"]:
                    self.attack_h = want = rng.choice([h for h in (0, 1, 2) if h != o["h"]])
                if me.height == want:
                    self.ready += 1
                    # a grunt hesitates once his blade is set: time to see it and match
                    if d <= reach_kill and self.ready >= self.hesitate:
                        pressed.add("punch")
                        self.mode, self.mode_t = "guard", 0
                        self.patience = self._patience()
                        self.hesitate = self._hesitate()
                    elif d > reach_kill - 2:
                        move = toward
                else:
                    self.ready = 0
                if self.mode_t > 90:
                    self.mode, self.mode_t = "guard", 0
        if want is not None and want != me.height and not pressed and self.cd == 0:
            pressed.add("up" if want > me.height else "down")
            self.cd = 3 if self.boss else 5
            move = None
        if move and not pressed & {"up", "down"}:
            held.add(move)
        return Ctrl(held, pressed)

    def _unarmed(self, me, opp, o, sc, d, toward, away, held, pressed):
        rng = self.rng
        if me.state == "duck":
            if d < 26 and o["state"] not in ("air",):
                pressed.add("kick")
                return Ctrl(held, pressed)
            if not sc.floor_sabre_near(me):
                pressed.add("up")
                return Ctrl(held, pressed)
        sab = sc.nearest_floor_sabre(me)
        if sab is not None:
            sd = sab.x - me.x
            if abs(sd) < 8:
                held.add("down")
                pressed.add("down")
                return Ctrl(held, pressed)
            go = "right" if sd > 0 else "left"
            # the sabre lies past the opponent's blade: roll under it, or dive at him
            between = sign(sd) == sign(o["x"] - me.x) and abs(sd) > d
            if o["armed"] and between and d < 76:
                if o["h"] > 0:
                    held.add(go)
                    pressed.add("down")
                else:
                    held.add(go)
                    pressed.add("up")
                return Ctrl(held, pressed)
            held.add(go)
            return Ctrl(held, pressed)
        if o["armed"]:
            if d < 80 and rng.random() < 0.5:
                held.add(toward)
                pressed.add("up" if o["h"] < 2 else "down")
            else:
                held.add(toward)
            return Ctrl(held, pressed)
        if d < 24:
            pressed.add("punch")
        else:
            held.add(toward)
        return Ctrl(held, pressed)


# ---- backdrop --------------------------------------------------------------
def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


_HALL = {}


def make_hall(boss=False):
    """A dark stone hall in the dungeon's level 11 stone, pillars and banners."""
    if boss in _HALL:
        return _HALL[boss]
    rng = random.Random(1111 + boss)
    floor_c, top_c, brick, mortar = (70, 76, 92), (22, 24, 34), (104, 110, 130), (48, 52, 66)
    banner = (150, 24, 40) if not boss else (120, 20, 120)
    s = pygame.Surface((W, H))
    s.fill(top_c)
    for row, y in enumerate(range(14, FLOOR_Y, 5)):
        light = 0.28 + 0.42 * (y / FLOOR_Y)
        pygame.draw.line(s, _shade(mortar, light), (0, y), (W, y))
        offs = 0 if row % 2 == 0 else 6
        for bx in range(-12, W, 12):
            r = pygame.Rect(bx + offs, y + 1, 11, 4)
            s.fill(_shade(brick, light * rng.choice((0.78, 0.88, 1.0))), r)
    # arches along the ceiling
    for cx in (97, 223, -29, 349):
        pygame.draw.ellipse(s, top_c, (cx - 52, -18, 104, 50))
        pygame.draw.arc(s, _shade(brick, 0.5), (cx - 52, -18, 104, 50), math.pi, 2 * math.pi, 2)
    # pillars
    for px in (34, 160, 286):
        pygame.draw.rect(s, _shade(brick, 0.55), (px - 9, 10, 18, FLOOR_Y - 10))
        pygame.draw.rect(s, _shade(brick, 0.72), (px - 7, 10, 4, FLOOR_Y - 10))
        pygame.draw.rect(s, _shade(brick, 0.38), (px + 5, 10, 4, FLOOR_Y - 10))
        for y in range(18, FLOOR_Y, 14):
            pygame.draw.line(s, _shade(mortar, 0.6), (px - 9, y), (px + 8, y))
        pygame.draw.rect(s, _shade(brick, 0.8), (px - 12, 10, 24, 5))
        pygame.draw.rect(s, _shade(brick, 0.7), (px - 12, FLOOR_Y - 6, 24, 6))
        # torch bracket
        pygame.draw.rect(s, (60, 44, 34), (px - 2, 82, 4, 8))
        pygame.draw.rect(s, (110, 80, 50), (px - 4, 80, 8, 3))
    # banners between the pillars, crossed sabres on them
    for bx in (97, 223):
        pygame.draw.rect(s, _shade(banner, 0.55), (bx - 13, 22, 26, 52))
        pygame.draw.polygon(s, _shade(banner, 0.55), [(bx - 13, 74), (bx + 13, 74), (bx, 84)])
        pygame.draw.rect(s, _shade(banner, 0.8), (bx - 11, 24, 22, 48))
        pygame.draw.polygon(s, _shade(banner, 0.8), [(bx - 11, 72), (bx + 11, 72), (bx, 81)])
        pygame.draw.rect(s, (90, 70, 40), (bx - 16, 20, 32, 3))
        for d in (-1, 1):
            pygame.draw.line(s, (200, 205, 220), (bx - 8 * d, 34), (bx + 8 * d, 58))
            pygame.draw.line(s, GUARD_C, (bx - 8 * d - 2, 54), (bx - 8 * d + 2 + 0, 56))
    # floor
    pygame.draw.rect(s, _shade(floor_c, 0.7), (0, FLOOR_Y, W, H - FLOOR_Y))
    for row, y in enumerate(range(FLOOR_Y, H, 7)):
        k = 0.85 - row * 0.1
        pygame.draw.line(s, _shade(floor_c, k * 0.6), (0, y), (W, y))
        offs = (row * 9) % 22
        for x in range(-22 + offs, W, 22):
            pygame.draw.line(s, _shade(floor_c, k * 0.6), (x, y), (x - 3, y + 6))
    pygame.draw.line(s, _shade(floor_c, 1.25), (0, FLOOR_Y), (W, FLOOR_Y))
    for _ in range(40):
        s.set_at((rng.randrange(W), rng.randrange(FLOOR_Y + 2, H)), _shade(floor_c, rng.choice((0.5, 1.1))))
    # walls at the ends
    for x0 in (0, W - 10):
        pygame.draw.rect(s, _shade(brick, 0.32), (x0, 0, 10, H))
        pygame.draw.line(s, _shade(brick, 0.6), (x0 + (9 if x0 == 0 else 0), 0), (x0 + (9 if x0 == 0 else 0), H))
    glow = pygame.Surface((64, 64))       # added on top: black adds nothing
    for r in range(32, 0, -2):
        k = 0.22 * (1 - r / 32) ** 1.6
        pygame.draw.circle(glow, (int(255 * k), int(140 * k), int(50 * k)), (32, 32), r)
    _HALL[boss] = (s, glow)
    return _HALL[boss]


HEART = [".##.##.", "#######", "#######", ".#####.", "..###..", "...#..."]


def draw_heart(surf, x, y, full, blink=False):
    col = (255, 60, 70) if full else (60, 30, 40)
    if blink:
        col = (255, 255, 255)
    for ry, row in enumerate(HEART):
        for rx, ch in enumerate(row):
            if ch == "#":
                surf.fill(col, (x + rx, y + ry, 1, 1))
    if full and not blink:
        surf.fill((255, 200, 200), (x + 1, y + 1, 1, 1))


# ---- the scene -------------------------------------------------------------
class NidhoggScene:
    INTRO = 80
    RESPAWN_INTRO = 46
    KILL_LEN = 110
    DIED_LEN = 96

    def __init__(self, game, enemy, akuma_hp, akuma_max, seed=None):
        _build_sfx()
        self.game = game
        self.enemy_ref = enemy
        self.rng = random.Random(seed)
        self.boss = bool(getattr(enemy, "boss", False))
        self.akuma_max = akuma_max
        self.seg = akuma_max / HEARTS
        self.hp = akuma_hp
        self.p = Duelist("AKUMA", DuelArt("akuma", HS), is_player=True)
        cid = getattr(enemy, "cid", "ryu")
        walk = getattr(enemy, "walk", 1.4)
        speed = 1.25 if self.boss else max(0.85, min(1.15, walk / 1.4))
        self.e = Duelist(getattr(enemy, "name", "FOE"), DuelArt(cid, BOSS_HS if self.boss else HS), speed=speed)
        self.ai = DuelAI(self.rng, self.boss, getattr(enemy, "ai", None))
        self.ai_enabled = True
        self.bg, self.glow = make_hall(self.boss)
        self.menu = PauseMenu(game, CONTROLS)
        self.sabres = []
        self.particles = []
        self.sparks = []
        self.events = []          # (frame, name) log, for tests and debugging
        self.result = None
        self.clock = 0
        self.hitstop = 0
        self.shake = 0
        self.heart_blink = 0
        self.banner = None
        self._begin(self.INTRO)

    # ---- hearts ----------------------------------------------------------
    @property
    def hearts(self):
        return max(0, math.ceil(self.hp / self.seg - 1e-6))

    @property
    def paused(self):
        return self.menu.open

    def other(self, f):
        return self.e if f is self.p else self.p

    def _begin(self, intro):
        self.p.reset(P_START, 1)
        self.e.reset(E_START, -1)
        self.sabres = []
        self.phase = "intro"
        self.phase_t = 0
        self.intro_len = intro
        self.ai.hist.clear()
        self.ai.mode, self.ai.mode_t = "guard", 0

    def log(self, name):
        self.events.append((self.clock, name))

    # ---- frame -----------------------------------------------------------
    def update(self, inp):
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.phase == "duel" and self.menu.toggle(inp):
            return
        self.clock += 1
        self.phase_t += 1
        if self.shake:
            self.shake -= 1
        if self.heart_blink:
            self.heart_blink -= 1
        self._particles()
        if self.hitstop:
            self.hitstop -= 1
            return
        if self.phase == "intro":
            for f in (self.p, self.e):
                f.tick()
            if self.phase_t == self.intro_len - 22:
                play("nid_garde")
            if self.phase_t >= self.intro_len:
                self.phase = "duel"
                self.phase_t = 0
                for f in (self.p, self.e):
                    f.set_state("stand")
            return
        if self.phase == "duel":
            ec = self.ai.think(self.e, self.p, self) if self.ai_enabled else NO_INPUT
            self._step(inp, ec)
            return
        # kill / died / lost: the world keeps moving, nobody fights
        self._step(NO_INPUT, NO_INPUT)
        skip = self.phase_t > 40 and inp.any_pressed("punch", "kick", "start")
        if self.phase == "kill":
            if self.phase_t == 40:
                self.p.set_state("win")
            if self.phase_t >= self.KILL_LEN or skip:
                self.result = "win"
                self.game.end_fight(self, "win", self.hp)
        elif self.phase == "died":
            if self.phase_t >= self.DIED_LEN or skip:
                self._begin(self.RESPAWN_INTRO)
        elif self.phase == "lost":
            if self.phase_t == 40:
                self.e.set_state("win")
            if self.phase_t >= self.KILL_LEN + 20 or (skip and self.phase_t > 60):
                self.result = "lose"
                self.game.end_fight(self, "lose", 0)

    def _step(self, pc, ec):
        """One frame of the duel with the two fighters' controls."""
        p, e = self.p, self.e
        for f, c in ((p, pc), (e, ec)):
            if not f.dead and f.state not in ("win",):
                f.control(c, self)
        for f in (p, e):
            if not f.dead:
                f.physics()
        self._separate()
        self._blades_meet()
        self._strikes()
        self._sabres()
        self._stabs()
        for f in (p, e):
            f.tick()
        for sp in self.sparks:
            sp[2] -= 1
        self.sparks = [sp for sp in self.sparks if sp[2] > 0]

    # ---- rules -----------------------------------------------------------
    def _separate(self):
        a, b = self.p, self.e
        solid = ("stand", "duck", "lunge", "punch", "trip", "hurt", "parried", "throw", "land", "getup", "snap")
        if a.dead or b.dead or a.state not in solid or b.state not in solid:
            return
        dx = b.x - a.x
        if abs(dx) < 16:
            s = sign(dx) or -a.facing
            over = (16 - abs(dx)) / 2
            a.x = min(WALL_R, max(WALL_L, a.x - s * over))
            b.x = min(WALL_R, max(WALL_L, b.x + s * over))

    def _facing_each_other(self, a, b):
        return a.facing == sign(b.x - a.x) and b.facing == sign(a.x - b.x)

    def blade_overlap(self, a, b):
        """How far the two blades lie past each other's tips (px), if they face."""
        if not (a.blade_active and b.blade_active and self._facing_each_other(a, b)):
            return 0.0
        return a.reach() + b.reach() - abs(b.x - a.x)

    def change_height(self, f, h):
        """Move f's sabre to height h. Arriving on the other blade when it is
        more than half-way past yours knocks it out of his hand."""
        f.height = h
        f.blade_flash = 0
        opp = self.other(f)
        if opp.blade_active and opp.guard == f.guard and f.blade_active:
            ov = self.blade_overlap(f, opp)
            if ov > BLADE / 2:
                self.disarm(opp, f)
            elif ov > 0:
                self._clink(f, opp, push=False)

    def disarm(self, f, by):
        self.log("disarm")
        hx, hy = f.tip()
        self._spark(hx - f.facing * BLADE // 2, hy, (255, 255, 200))
        f.blade_flash = by.blade_flash = 8
        self.drop_sabre(f, toss=True)
        if f.state == "lunge":
            f.set_state("parried")
            f.vx = -f.facing * 1.2
        play("nid_disarm")

    def drop_sabre(self, f, toss=False):
        if not f.armed:
            return
        f.armed = False
        f.aloft = False
        hx, hy = f.hand()
        vx = -f.facing * self.rng.uniform(0.9, 1.7) if toss else f.facing * 0.3
        self.sabres.append(Sabre(hx, hy, vx, -3.6 if toss else -1.0))

    def throw(self, f):
        if not f.armed:
            return
        self.log("throw")
        hx, hy = f.hand()
        y = min(hy, f.y - THROW_MIN_Y) if f.on_ground else hy
        if f.aloft:
            y = f.y - HEIGHT_Y[2]
        f.armed = False
        f.aloft = False
        tip = hx + f.facing * BLADE
        self.sabres.append(Sabre(tip, y, f.facing * THROW_V, thrown=True, owner=f))
        if f.on_ground:
            f.set_state("throw")
            f.vx = 0.0
        play("nid_throw")

    def floor_sabre_near(self, f, r=12):
        return any(sb.rest and abs(sb.x - f.x) < r for sb in self.sabres)

    def nearest_floor_sabre(self, f):
        rest = [sb for sb in self.sabres if sb.rest or (not sb.thrown)]
        return min(rest, key=lambda sb: abs(sb.x - f.x)) if rest else None

    def pick_up(self, f, r=12):
        if f.armed:
            return False
        near = [sb for sb in self.sabres if sb.rest and abs(sb.x - f.x) < r]
        if not near:
            return False
        sb = min(near, key=lambda s: abs(s.x - f.x))
        self.sabres.remove(sb)
        f.armed = True
        f.height = 0
        self.log("pickup")
        play("pickup", 0.6)
        return True

    def _clink(self, a, b, push=True):
        hx, hy = a.tip()
        x = (hx + b.tip()[0]) / 2
        if not (a.blade_flash or b.blade_flash):
            play("nid_clink")
            self._spark(x, hy, (190, 220, 255))
        a.blade_flash = b.blade_flash = 5

    def _blades_meet(self):
        """Same-height blades: a lunge into one is parried, otherwise they
        clink and push each other apart."""
        a, b = self.p, self.e
        if not (a.blade_active and b.blade_active) or a.guard != b.guard:
            return
        ov = self.blade_overlap(a, b)
        if ov <= 0:
            return
        lunging = [f for f in (a, b) if f.state == "lunge" and f.ext > 0]
        if lunging:
            self.log("parry")
            hx, hy = a.tip()
            self._spark((hx + b.tip()[0]) / 2, hy, (255, 255, 220), big=True)
            for f in (a, b):
                f.set_state("parried")
                f.vx = -f.facing * 1.7
                f.blade_flash = 9
            play("nid_parry")
            self.hitstop = max(self.hitstop, 3)
        else:
            self._clink(a, b)
        # never leave the blades overlapped
        ov = self.blade_overlap(a, b)
        if ov > 0:
            s = sign(b.x - a.x) or 1
            a.x = min(WALL_R, max(WALL_L, a.x - s * ov / 2))
            b.x = min(WALL_R, max(WALL_L, b.x + s * ov / 2))

    def _strikes(self):
        """Dive kicks, punches, trips."""
        for att in (self.p, self.e):
            dfn = self.other(att)
            if att.dead or dfn.dead:
                continue
            if att.state == "dive":
                body = dfn.body_area(self.clock)
                fx, fy, fw, fh = att.foot_rect()
                foot = (pygame.Mask((fw, fh), fill=True), fx, fy)
                # a high sabre skewers the diver before the foot lands
                if dfn.blade_active and dfn.guard == 2 and touches(dfn.blade_area(), att.body_area(self.clock)):
                    self.kill(att, dfn, "skewered")
                    continue
                if dfn.state not in ("down", "roll") and touches(foot, body):
                    self.log("divekick")
                    play("heavy")
                    self._spark(fx + fw // 2, fy, (255, 200, 80), big=True)
                    dfn.knock_down(self, att.x)
                    att.set_state("air")
                    att.dove = True
                    att.vx, att.vy = -att.facing * 1.0, -2.6
                    self.shake = 6
                    self.hitstop = 5
            elif att.state == "punch" and 2 <= att.t <= 6 and not att.hit_done:
                x0 = att.x + (8 if att.facing > 0 else -28)
                fist = (pygame.Mask((20, 8), fill=True), round(x0), round(att.y - 34))
                if dfn.state not in ("down", "roll", "dead") and touches(fist, dfn.body_area(self.clock)):
                    att.hit_done = True
                    dfn.punched += 1
                    dfn.punch_clock = PUNCH_COMBO
                    self._spark(x0 + (16 if att.facing > 0 else 4), att.y - 30, (255, 220, 120))
                    if dfn.punched >= 2:
                        self.log("punch_ko")
                        play("heavy")
                        dfn.knock_down(self, att.x)
                    else:
                        self.log("punch")
                        play("hit")
                        if dfn.on_ground:
                            dfn.set_state("hurt")
                        dfn.vx = att.facing * 1.6
            elif att.state == "trip" and 3 <= att.t <= 10 and not att.hit_done:
                x0 = att.x + (4 if att.facing > 0 else -30)
                sweep = (pygame.Mask((26, 8), fill=True), round(x0), round(att.y - 8))
                if dfn.on_ground and dfn.state not in ("down", "dead") and touches(sweep, dfn.body_area(self.clock)):
                    att.hit_done = True
                    self.log("trip")
                    play("heavy")
                    self._spark(x0 + 13, att.y - 5, (255, 220, 120))
                    dfn.knock_down(self, att.x)

    def _sabres(self):
        fighters = (self.p, self.e)
        for sb in self.sabres:
            sb.update()
        # two thrown sabres meeting knock each other down
        flying = [sb for sb in self.sabres if sb.thrown]
        for i, a in enumerate(flying):
            for b in flying[i + 1:]:
                if a.thrown and b.thrown and abs(a.x - b.x) < 8 and abs(a.y - b.y) < 6:
                    a.drop()
                    b.drop()
                    self._spark((a.x + b.x) / 2, a.y, (190, 220, 255))
                    play("nid_clink")
        for sb in self.sabres:
            if not sb.thrown:
                continue
            for f in fighters:
                if f is sb.owner or f.dead:
                    continue
                d = sign(sb.vx)
                facing_it = f.facing == -d and sign(f.x - sb.x) == d
                if (f.blade_active and f.on_ground and f.guard >= 1 and facing_it
                        and f.state in ("stand", "lunge", "parried", "throw", "land")
                        and abs(f.x - sb.x) < f.reach() + 2):
                    self.log("throw_parried")
                    f.blade_flash = 8
                    self._spark(sb.x, sb.y, (255, 255, 220), big=True)
                    play("nid_parry")
                    sb.drop()
                    break
                if touches(sb.area(), f.body_area(self.clock)):
                    sb.drop(vx=-d * 0.6)
                    self.kill(f, sb.owner, "thrown")
                    break
        # rolling over a sabre picks it up
        for f in fighters:
            if f.state == "roll" and not f.armed:
                self.pick_up(f, r=10)

    def _stabs(self):
        """A blade touching a body kills it. If both land the same frame, the
        deeper one wins."""
        p, e = self.p, self.e
        if p.dead or e.dead:
            return
        hits = []
        for att, dfn in ((p, e), (e, p)):
            ba = att.blade_area()
            if ba is None:
                continue
            body = dfn.body_area(self.clock)
            if body is None:
                continue
            n = ba[0].overlap_area(body[0], (body[1] - ba[1], body[2] - ba[2]))
            if n:
                hits.append((n + (100 if att.state == "lunge" else 0), att, dfn))
        if hits:
            hits.sort(key=lambda h: -h[0])
            _, att, dfn = hits[0]
            self.kill(dfn, att, "stab")

    def kill(self, victim, killer, how):
        if victim.dead:
            return
        self.log("kill_" + ("akuma" if victim is self.p else "enemy") + "_" + how)
        self._burst(victim)
        if victim.armed:
            self.drop_sabre(victim, toss=True)
        victim.dead = True
        victim.set_state("dead")
        victim.vx = victim.vy = 0.0
        play("nid_stab")
        self.hitstop = 8
        self.shake = 12
        if self.phase != "duel":
            return
        self.phase_t = 0
        if victim is self.e:
            self.phase = "kill"
            play("ko")
        else:
            self.hp = round(max(0, self.hearts - 1) * self.seg)
            self.heart_blink = 60
            play("nid_heart")
            self.phase = "died" if self.hearts > 0 else "lost"
            if self.phase == "lost":
                play("ko")

    # ---- effects -----------------------------------------------------------
    def _spark(self, x, y, col, big=False):
        self.sparks.append([x, y, 10 if big else 6, col, big])

    def _burst(self, f):
        """The body comes apart into its own coloured pixels."""
        key, mode = f.look(self.clock)
        img, (ax, ay), m = f.art.get(key, f.facing < 0, mode)
        left, top = round(f.x) - ax, round(f.y) - ay
        pts = []
        w, h = img.get_size()
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                if m.get_at((x, y)):
                    pts.append((x, y))
        self.rng.shuffle(pts)
        cx, cy = f.x, f.y - HS / 2
        for (x, y) in pts[:110]:
            c = img.get_at((x, y))
            px, py = left + x, top + y
            ang = math.atan2(py - cy, px - cx)
            sp = self.rng.uniform(0.6, 2.8)
            self.particles.append([float(px), float(py), math.cos(ang) * sp, math.sin(ang) * sp - 1.2,
                                   self.rng.randint(40, 90), (c.r, c.g, c.b)])
        for _ in range(26):
            ang = self.rng.uniform(0, math.tau)
            sp = self.rng.uniform(1.5, 4.0)
            self.particles.append([cx, cy, math.cos(ang) * sp, math.sin(ang) * sp - 1, self.rng.randint(14, 30),
                                   (255, 255, 230)])
        self.sparks.append([cx, cy, 12, (255, 255, 255), True])

    def _particles(self):
        for pt in self.particles:
            pt[0] += pt[2]
            pt[1] += pt[3]
            pt[3] += 0.12
            pt[4] -= 1
            if pt[1] >= FLOOR_Y + 1:
                pt[1] = FLOOR_Y + 1
                pt[3] *= -0.35
                pt[2] *= 0.6
        self.particles = [pt for pt in self.particles if pt[4] > 0]

    # ---- drawing -----------------------------------------------------------
    def draw(self, surf):
        ox = oy = 0
        if self.shake:
            ox, oy = self.rng.choice((-2, -1, 1, 2)), self.rng.choice((-1, 0, 1))
        surf.blit(self.bg, (ox, oy))
        self._torches(surf, ox, oy)
        for sb in self.sabres:
            if sb.rest:
                self._draw_sabre_item(surf, sb, ox, oy)
        for f in sorted((self.p, self.e), key=lambda f: 0 if f.state in ("down",) else 1):
            self._draw_fighter(surf, f, ox, oy)
        for sb in self.sabres:
            if not sb.rest:
                self._draw_sabre_item(surf, sb, ox, oy)
        for pt in self.particles:
            a = pt[4]
            col = pt[5] if a > 10 else tuple(v // 2 for v in pt[5])
            surf.fill(col, (round(pt[0]) + ox, round(pt[1]) + oy, 1, 1))
        for x, y, life, col, big in self.sparks:
            self._draw_spark(surf, x + ox, y + oy, life, col, big)
        self._hud(surf)
        if self.menu.open:
            self.menu.draw(surf)

    def _torches(self, surf, ox, oy):
        for px in (34, 160, 286):
            fl = 0.85 + 0.15 * math.sin(self.clock * 0.31 + px) + self.rng.uniform(-0.05, 0.05)
            g = pygame.transform.scale(self.glow, (int(64 * fl), int(64 * fl)))
            surf.blit(g, (px - g.get_width() // 2 + ox, 76 - g.get_height() // 2 + oy), special_flags=pygame.BLEND_ADD)
            h = 5 + (self.clock // 5 + px) % 3
            pygame.draw.ellipse(surf, (240, 120, 30), (px - 3 + ox, 79 - h + oy, 6, h + 1))
            pygame.draw.ellipse(surf, (255, 230, 120), (px - 1 + ox, 80 - h + 2 + oy, 3, max(1, h - 2)))

    def _draw_fighter(self, surf, f, ox, oy):
        if f.dead and f.t > 3:
            return
        key, mode = f.look(self.clock)
        flip = f.facing < 0
        img, (ax, ay), _ = f.art.get(key, flip, mode)
        if f.dead or f.flash:
            img = f.art.white(key, flip, mode)
        x, y = round(f.x) - ax + ox, round(f.y) - ay + oy
        # shadow
        pygame.draw.ellipse(surf, (14, 14, 22), (round(f.x) - 11 + ox, FLOOR_Y - 2 + oy, 22, 4))
        surf.blit(img, (x, y))
        if f.armed and not f.dead:
            self._draw_blade(surf, f, ox, oy)

    def _draw_blade(self, surf, f, ox, oy):
        if f.state in ("roll", "down", "getup", "dive", "trip", "snap") or not f.armed:
            if f.armed and f.state in ("roll", "dive", "trip"):
                # carried along the back
                hx, hy = f.x - f.facing * 4 + ox, f.y - 14 + oy
                pygame.draw.line(surf, (150, 160, 180), (hx, hy), (hx - f.facing * 12, hy - 6))
            return
        flash = f.blade_flash > 0 and (f.blade_flash % 2 == 0)
        col = SABRE_HI if flash else SABRE_C
        if f.aloft:
            hx, hy = round(f.x) + f.facing * 2 + ox, round(f.y - HS - 1) + oy
            tx, ty = hx - f.facing * 15, hy - 11
            pygame.draw.line(surf, col, (hx, hy), (tx, ty))
            pygame.draw.line(surf, GUARD_C, (hx - 2, hy + 1), (hx + 2, hy - 1))
            return
        hx, hy = f.hand()
        hx, hy = round(hx) + ox, round(hy) + oy
        tx = hx + f.facing * BLADE
        pygame.draw.line(surf, GRIP_C, (hx - f.facing * 3, hy), (hx, hy))
        pygame.draw.line(surf, col, (hx + f.facing, hy), (tx, hy))
        pygame.draw.line(surf, (120, 130, 160) if not flash else (255, 250, 200), (hx + f.facing, hy + 1),
                         (tx - f.facing * 2, hy + 1))
        pygame.draw.line(surf, GUARD_C, (hx, hy - 2), (hx, hy + 2))
        if f.state == "lunge" and f.ext >= 16:
            for k in (6, 12):
                pygame.draw.line(surf, (120, 140, 190), (hx - f.facing * k, hy - 2), (hx - f.facing * (k + 4), hy - 2))

    def _draw_sabre_item(self, surf, sb, ox, oy):
        if sb.thrown:
            d = sign(sb.vx)
            x, y = round(sb.x) + ox, round(sb.y) + oy
            pygame.draw.line(surf, SABRE_HI, (x, y), (x - d * BLADE, y))
            pygame.draw.line(surf, GUARD_C, (x - d * BLADE, y - 2), (x - d * BLADE, y + 2))
            pygame.draw.line(surf, GRIP_C, (x - d * BLADE, y), (x - d * (BLADE + 3), y))
            for k in (6, 13, 20):
                pygame.draw.line(surf, (110, 130, 180), (x - d * (BLADE + k), y - 1), (x - d * (BLADE + k + 3), y - 1))
            return
        cx, cy = sb.x + ox, sb.y + oy
        ca, sa = math.cos(sb.ang), math.sin(sb.ang)
        hw = (BLADE + 3) / 2
        a = (round(cx - ca * hw), round(cy - sa * hw))
        b = (round(cx + ca * hw), round(cy + sa * hw))
        pygame.draw.line(surf, SABRE_C, a, b)
        gx, gy = cx - ca * (hw - 4), cy - sa * (hw - 4)
        pygame.draw.line(surf, GUARD_C, (round(gx - sa * 2), round(gy + ca * 2)), (round(gx + sa * 2), round(gy - ca * 2)))
        if sb.rest and (self.clock // 20) % 3 == 0:
            surf.fill((255, 255, 255), (b[0] - 2, b[1], 1, 1))

    def _draw_spark(self, surf, x, y, life, col, big):
        x, y = round(x), round(y)
        n = 8 if big else 4
        for k in range(n):
            ang = k * math.tau / n + 0.3
            r0 = max(1, (12 - life) // 2)
            r1 = r0 + (5 if big else 3)
            pygame.draw.line(surf, col, (x + round(math.cos(ang) * r0), y + round(math.sin(ang) * r0)),
                             (x + round(math.cos(ang) * r1), y + round(math.sin(ang) * r1)))
        if life > 6:
            surf.fill((255, 255, 255), (x - 1, y - 1, 3, 3))

    def _band(self, surf, y, h):
        band = pygame.Surface((W, h), pygame.SRCALPHA)
        band.fill((6, 4, 12, 150))
        surf.blit(band, (0, y))

    def _hud(self, surf):
        draw_text(surf, "AKUMA", 6, 5, (255, 90, 90))
        n = self.hearts
        for i in range(HEARTS):
            blink = self.heart_blink and i == n and (self.heart_blink // 4) % 2 == 0
            draw_heart(surf, 6 + i * 10, 15, i < n, blink)
        name = self.e.name
        draw_text(surf, name, W - 6, 5, (255, 230, 120) if self.boss else (220, 220, 255), align="right")
        draw_text(surf, "BOSS DUEL" if self.boss else "ONE TOUCH KILLS", W - 6, 15, (150, 150, 170), align="right")
        if self.phase != "duel" and not (self.phase in ("kill", "died", "lost") and self.phase_t <= 4):
            self._band(surf, 44, 64)
        if self.phase == "intro":
            if self.phase_t < self.intro_len - 22:
                draw_text(surf, "EN GARDE!", W // 2, 52, (230, 236, 255), scale=3, align="center")
                draw_text(surf, "AKUMA  VS  %s" % name, W // 2, 80, (255, 230, 150), align="center")
            else:
                draw_text(surf, "PRET? ALLEZ!", W // 2, 56, (255, 220, 80), scale=2, align="center")
        elif self.phase == "kill":
            if self.phase_t > 4 and ((self.phase_t // 5) % 2 == 0 or self.phase_t > 30):
                draw_text(surf, "KILL", W // 2, 50, (255, 60, 50), scale=4, align="center")
            if self.phase_t > 40:
                draw_text(surf, "%s FALLS" % name, W // 2, 86, (255, 255, 255), align="center")
        elif self.phase == "died":
            if self.phase_t > 4:
                draw_text(surf, "YOU DIED", W // 2, 48, (255, 60, 50), scale=3, align="center")
                draw_text(surf, "(-1 HEART)", W // 2, 76, (255, 160, 160), scale=2, align="center")
            if self.phase_t > 40:
                draw_text(surf, "%d HEART%s LEFT" % (n, "" if n == 1 else "S"), W // 2, 98, (255, 255, 255),
                          align="center")
        elif self.phase == "lost":
            if self.phase_t > 4:
                draw_text(surf, "YOU DIED", W // 2, 48, (255, 60, 50), scale=3, align="center")
                draw_text(surf, "AKUMA HAS NO HEARTS LEFT", W // 2, 80, (255, 255, 255), align="center")
