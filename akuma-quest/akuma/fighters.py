"""Side-view fighting engine: moves, fighters, projectiles and enemy AI.

All timing is in whole frames at a fixed 60 fps, like an arcade fighter, so
the feel is identical on every machine.

A move is a dict:
  phases     list of (kind, frames, pose or [poses]) where kind is
             "startup" | "active" | "recovery"; the hitbox is live during
             "active" phases only
  hold_last  the last phase lasts until the fighter lands (air moves)
  land_rec   recovery frames after landing from a hold_last move
  events     {frame: {...}} velocity changes / projectile spawns / sounds
  hitbox     (x, y, w, h) relative to the feet, facing right
  dmg, hitstun, blockstun, height ("mid" | "low" | "high"), knockdown
  invuln     (first, last) frames with no hurtbox
  rehit      frames between hits for multi-hit moves (max_hits caps them)
  cat        "punch" | "kick" | "special" (damage tier and cancel rules)
  opener     jump-ins: a hit always gives hitstun (never a knockdown), so the
             attacker can land and keep comboing
"""


from . import audio
from .art import FighterArt, BUILDS, CHX, CHY, make_fireball
from .config import GROUND_Y, STAGE_LEFT, STAGE_RIGHT, GRAVITY

STEP_UP = 4      # px a fighter can step up or down without it counting as a wall or ledge

JUMP_VY = -7.4
JUMP_VX = 2.2
LAND_FRAMES = 3


# --------------------------------------------------------------------------
# Akuma's moves
# --------------------------------------------------------------------------
AKUMA_HADO_COLORS = ((255, 230, 255), (230, 80, 200), (150, 20, 60))

# Damage tiers: a kick is one "normal hit"; punches are half a hit but come out
# faster; specials are a hit and a half.
HIT = 14
PUNCH_DMG, KICK_DMG, SPECIAL_DMG = HIT // 2, HIT, HIT * 3 // 2

# Street Fighter style cancels: while a normal is connecting (hit or block)
# the next button press interrupts its recovery. Punches chain into anything,
# kicks into a different kick or a special, specials end the string.
CANCELS = {"punch": ("punch", "kick", "special"), "kick": ("kick", "special")}
CANCEL_WINDOW = 12     # frames after contact to input the next move
MAX_CHAIN = 5          # moves in one string
MAX_COMBO = 5          # the 5th hit of a combo always knocks down
THROW_RANGE = 40       # feet-to-feet distance a grab reaches
THROW_LINK = 3         # punch and kick count as "together" within this many frames
SPECIAL_LINK = 4       # special + punch/kick count as "together" within this many frames
SPECIAL_COMBOS = {"punch": "shoryuken", "kick": "tatsu"}

# Akuma's hitboxes ("hitbox_px") are in real sprite pixels, measured from the
# sheet frames: (x forward of the feet, y up from the feet, w, h).
AKUMA_MOVES = {
    # ---- special button ----
    "hadouken": dict(
        name="Gou Hadouken", cat="special",
        phases=[("startup", 4, "hado_prep"), ("startup", 6, "hado_fire"),
                ("recovery", 18, "hado_fire")],
        events={4: dict(sound="hadouken"),
                9: dict(proj=dict(speed=3.8, dmg=SPECIAL_DMG, hitstun=20, blockstun=14, chip=2,
                                  colors=AKUMA_HADO_COLORS, y=-38, px=True, x=30, sheet=True))}),
    "shoryuken": dict(
        name="Goshoryuken", cat="special",
        phases=[("startup", 3, "sho_crouch"), ("active", 8, "sho_rise"),
                ("active", 3, "sho_top"), ("recovery", 1, "sho_fall")],
        hold_last=True, land_rec=14, invuln=(0, 8), air=True,
        hitbox_px=(0, -84, 26, 70), dmg=SPECIAL_DMG, hitstun=30, blockstun=18, height="mid",
        knockdown=True, launch=-6.0,
        events={3: dict(vy=-7.9, vxf=1.5, sound="shoryu")}),
    "tatsu": dict(
        name="Tatsumaki", cat="special",
        phases=[("startup", 5, "tatsu_start"), ("active", 30, "tatsu"),
                ("recovery", 1, "tatsu_end")],
        hold_last=True, land_rec=10, air=True, no_gravity=35, rehit=8, max_hits=3,
        hitbox_px=(-34, -46, 68, 18), dmg=SPECIAL_DMG // 3, hitstun=18, blockstun=10,
        height="mid", push=1.5,
        events={4: dict(vy=-3.2, vxf=2.0, sound="sweep"), 9: dict(vy=0.0),
                13: dict(sound="whiff"), 21: dict(sound="whiff"), 29: dict(sound="whiff"),
                35: dict(vy=0.5)}),
    # ---- punch button: half damage, fast ----
    "jab": dict(
        name="Jab", cat="punch",
        phases=[("startup", 2, "punch_prep"), ("active", 3, "punch"), ("recovery", 6, "punch_rec")],
        hitbox_px=(14, -46, 22, 14), dmg=PUNCH_DMG, hitstun=16, blockstun=10, height="mid",
        push=0.9, events={1: dict(sound="whiff")}),
    "crouch_jab": dict(
        name="Crouching Jab", cat="punch",
        phases=[("startup", 2, "cr_punch_prep"), ("active", 3, "crouch_jab"),
                ("recovery", 6, "cr_punch_rec")],
        crouching=True, hitbox_px=(10, -34, 18, 14), dmg=PUNCH_DMG, hitstun=16, blockstun=10,
        height="mid", push=0.9, events={1: dict(sound="whiff")}),
    "jump_jab": dict(
        name="Jumping Jab", cat="punch",
        phases=[("startup", 2, "jpunch_prep"), ("active", 10, "jump_jab"), ("recovery", 1, "jump")],
        hold_last=True, land_rec=2, air=True, opener=True,
        hitbox_px=(8, -32, 26, 32), dmg=PUNCH_DMG, hitstun=26, blockstun=12, height="high",
        push=0.8, events={1: dict(sound="whiff")}),
    "air_hado": dict(
        name="Zanku Hadouken", cat="special",
        phases=[("startup", 6, "air_hado_prep"), ("startup", 6, "air_hado"),
                ("recovery", 1, "fall")],
        hold_last=True, land_rec=8, air=True, no_gravity=12,
        events={0: dict(vy=-0.6, vxf=0.6), 5: dict(sound="hadouken"),
                6: dict(proj=dict(speed=3.0, vy=1.7, dmg=SPECIAL_DMG, hitstun=20, blockstun=14,
                                  chip=2, colors=AKUMA_HADO_COLORS, y=-34, px=True, x=24,
                                  sheet=True))}),
    # ---- punch + kick together: throw, tossed whichever way is held ----
    "throw": dict(
        name="Throw", cat="throw", grab=True, dmg=HIT * 2,
        phases=[("startup", 3, "grab"), ("active", 3, "grab"), ("recovery", 20, "grab_miss")],
        events={2: dict(sound="whiff")}),
    # Third Strike style: grab, lift them up over the head, then fling them
    "toss": dict(
        name="Throw", cat="throw",
        phases=[("recovery", 5, "grab"), ("recovery", 11, "lift"),
                ("recovery", 18, "fling")]),
    # ---- kick button: one hit, normal speed ----
    "front_kick": dict(
        name="Front Kick", cat="kick",
        phases=[("startup", 5, "front_kick_prep"), ("active", 4, "front_kick"),
                ("recovery", 11, "front_kick_rec")],
        hitbox_px=(12, -42, 22, 16), dmg=KICK_DMG, hitstun=18, blockstun=11, height="mid",
        push=1.4, events={3: dict(sound="whiff")}),
    "roundhouse": dict(
        name="Roundhouse", cat="kick",
        phases=[("startup", 9, "kick_prep"), ("active", 5, "kick"), ("recovery", 16, "kick_rec")],
        hitbox_px=(14, -44, 28, 18), dmg=KICK_DMG, hitstun=20, blockstun=13, height="mid",
        push=2.4, events={7: dict(sound="whiff")}),
    "sweep": dict(
        name="Sweep", cat="kick",
        phases=[("startup", 6, "sweep_prep"), ("active", 6, "sweep"), ("recovery", 16, "sweep_rec")],
        crouching=True, hitbox_px=(10, -14, 28, 14), dmg=KICK_DMG, hitstun=20, blockstun=12,
        height="low", knockdown=True, launch=-3.0,
        events={4: dict(sound="sweep")}),
    "crouch_kick": dict(
        name="Crouching Kick", cat="kick",
        phases=[("startup", 4, "crkick_prep"), ("active", 4, "crkick"), ("recovery", 9, "crkick_rec")],
        crouching=True, hitbox_px=(10, -16, 26, 14), dmg=KICK_DMG, hitstun=18, blockstun=11,
        height="low", push=1.0, events={2: dict(sound="whiff")}),
    "jump_kick": dict(
        name="Jumping Kick", cat="kick",
        phases=[("startup", 3, "jkick_prep"), ("active", 10, "jump_kick"), ("recovery", 1, "jump")],
        hold_last=True, land_rec=2, air=True, opener=True,
        hitbox_px=(6, -30, 30, 30), dmg=KICK_DMG, hitstun=26, blockstun=12, height="high",
        push=0.8, events={2: dict(sound="whiff")}),
    "dive": dict(
        name="Dive Kick", cat="kick",
        phases=[("active", 1, "dive")], hold_last=True, land_rec=8, air=True, opener=True,
        no_gravity=True, hitbox_px=(8, -22, 26, 22), dmg=KICK_DMG, hitstun=28, blockstun=12,
        height="high", bounce=True, push=0.8,
        events={0: dict(vy=4.6, vxf=3.4, sound="dive")}),
}


def scale_damage(moves, k):
    """Copy a move list with every hit's damage multiplied by k."""
    out = []
    for m in moves:
        m = dict(m)
        if "dmg" in m:
            m["dmg"] = max(1, round(m["dmg"] * k))
        evs = {}
        for t, ev in m.get("events", {}).items():
            if "proj" in ev:
                ev = dict(ev)
                ev["proj"] = dict(ev["proj"], dmg=max(1, round(ev["proj"]["dmg"] * k)))
            evs[t] = ev
        m["events"] = evs
        out.append(m)
    return out


# --------------------------------------------------------------------------
# Enemy move pool. Each factory takes an rng so every grunt is a bit different.
# "range" is the distance band where the AI likes to throw the move.
# --------------------------------------------------------------------------
def _v(rng, base, spread=0.2):
    return max(1, int(round(base * rng.uniform(1 - spread, 1 + spread))))


def m_jab(rng):
    return dict(name="Jab", range=(0, 34), phases=[("startup", _v(rng, 5), "punch_prep"),
                ("active", 3, "punch"), ("recovery", _v(rng, 11), "punch_prep")],
                hitbox=(8, -38, 20, 9), dmg=_v(rng, 6), hitstun=14, blockstun=10,
                height="mid", push=2.2, events={2: dict(sound="whiff")})


def m_kick(rng):
    return dict(name="Roundhouse", range=(10, 44), phases=[("startup", _v(rng, 8), "kick_prep"),
                ("active", 4, "kick"), ("recovery", _v(rng, 16), "kick_prep")],
                hitbox=(10, -36, 24, 12), dmg=_v(rng, 9), hitstun=17, blockstun=12,
                height="mid", push=2.8, events={4: dict(sound="whiff")})


FIRE_COLORS = [((255, 255, 220), (120, 200, 255), (40, 80, 220)),
               ((255, 255, 200), (255, 200, 60), (220, 90, 20)),
               ((240, 255, 240), (100, 240, 120), (20, 140, 60)),
               ((255, 255, 255), (200, 200, 255), (120, 100, 240))]


def m_fireball(rng, big=False):
    return dict(name="Fireball", range=(70, 400), phases=[("startup", 7, "hado_prep"),
                ("startup", _v(rng, 8), "hado_fire"), ("recovery", _v(rng, 24), "hado_fire")],
                projectile=True,
                events={6: dict(sound="fireball"),
                        7: dict(proj=dict(speed=rng.uniform(2.2, 3.1) if not big else 3.5,
                                          dmg=_v(rng, 8) if not big else 14,
                                          hitstun=18, blockstun=12, chip=1 if not big else 3,
                                          colors=rng.choice(FIRE_COLORS) if not big else
                                          ((255, 255, 230), (255, 230, 80), (200, 40, 20)),
                                          y=-30, big=big))})


def m_upper(rng):
    return dict(name="Rising Upper", range=(0, 30), anti_air=True,
                phases=[("startup", _v(rng, 4), "sho_crouch"), ("active", 8, "sho_rise"),
                        ("recovery", 1, "fall")],
                hold_last=True, land_rec=_v(rng, 18), invuln=(0, 5), air=True,
                hitbox=(0, -58, 18, 44), dmg=_v(rng, 12), hitstun=26, blockstun=16,
                height="mid", knockdown=True, launch=-5.0,
                events={4: dict(vy=-6.6, vxf=1.0, sound="shoryu")})


def m_rush(rng):
    sp = rng.uniform(3.6, 4.6)
    return dict(name="Rush Punch", range=(50, 140),
                phases=[("startup", _v(rng, 10), "punch_prep"), ("active", 16, "dash"),
                        ("recovery", _v(rng, 18), "punch_prep")],
                keep_vx=True, hitbox=(6, -36, 22, 12), dmg=_v(rng, 10), hitstun=18,
                blockstun=14, height="mid", push=3.0,
                events={6: dict(sound="whiff"), "a": dict(vxf=sp), "r": dict(vx=0)})


def m_leap(rng):
    return dict(name="Leap Kick", range=(55, 120), air=True,
                phases=[("startup", 6, "crouch"), ("startup", 8, "jump"), ("active", 1, "leap_kick")],
                hold_last=True, land_rec=_v(rng, 12),
                hitbox=(8, -24, 22, 14), dmg=_v(rng, 10), hitstun=16, blockstun=12,
                height="high", events={6: dict(vy=-5.6, vxf=rng.uniform(2.4, 3.2), sound="jump")})


def m_sweep(rng):
    return dict(name="Low Sweep", range=(8, 42), crouching=True,
                phases=[("startup", _v(rng, 7), "sweep_prep"), ("active", 5, "sweep"),
                        ("recovery", _v(rng, 20), "sweep_prep")],
                hitbox=(6, -10, 28, 10), dmg=_v(rng, 9), hitstun=18, blockstun=12,
                height="low", knockdown=True, launch=-3.0, events={4: dict(sound="sweep")})


def m_hammer(rng):
    return dict(name="Hammer Fist", range=(0, 34),
                phases=[("startup", _v(rng, 16), "hammer_up"), ("active", 4, "hammer_down"),
                        ("recovery", _v(rng, 16), "hammer_down")],
                hitbox=(6, -34, 22, 30), dmg=_v(rng, 13), hitstun=20, blockstun=14,
                height="high", push=2.5, events={14: dict(sound="whiff")})


def m_lariat(rng):
    return dict(name="Spinning Lariat", range=(0, 50),
                phases=[("startup", 8, "intro"), ("active", 40, ["lariat_a", "lariat_b"]),
                        ("recovery", 20, "idle0")],
                keep_vx=True, rehit=9, hitbox=(-24, -40, 48, 14), dmg=5, hitstun=14,
                blockstun=10, height="mid", push=1.5,
                events={8: dict(vxf=1.1, sound="whiff"), 20: dict(sound="whiff"),
                        32: dict(sound="whiff"), 48: dict(vx=0)})


ENEMY_POOL = [(m_jab, 3), (m_kick, 3), (m_fireball, 2), (m_upper, 2), (m_rush, 2),
              (m_leap, 2), (m_sweep, 2), (m_hammer, 2)]


def random_moveset(rng, n):
    pool = list(ENEMY_POOL)
    out = []
    while len(out) < n and pool:
        tot = sum(w for _, w in pool)
        r = rng.uniform(0, tot)
        for i, (f, w) in enumerate(pool):
            r -= w
            if r <= 0:
                out.append(f(rng))
                pool.pop(i)
                break
    return out


def boss_moveset(rng):
    return [m_fireball(rng, big=True), m_rush(rng), m_lariat(rng), m_upper(rng),
            m_hammer(rng), m_sweep(rng), m_kick(rng)]


def boss2_moveset(rng):
    return [m_fireball(rng, big=True), m_leap(rng), m_rush(rng), m_lariat(rng), m_upper(rng),
            m_hammer(rng), m_sweep(rng), m_jab(rng)]


# --------------------------------------------------------------------------
class Projectile:
    def __init__(self, owner, x, y, spec):
        self.owner = owner
        self.dir = owner.facing
        self.x, self.y = x, y
        self.vx = spec["speed"] * self.dir
        self.dmg = spec["dmg"]
        self.hitstun = spec["hitstun"]
        self.blockstun = spec["blockstun"]
        self.chip = spec.get("chip", 0)
        self.vy = spec.get("vy", 0.0)
        big = spec.get("big", False)
        self.w, self.h = (18, 16) if big else (14, 12)
        # a character's own fireball from its sheet, if it has one
        art = getattr(owner, "art", None)
        sheet = art.projectile_frames(air=bool(self.vy)) if hasattr(art, "projectile_frames") else []
        if spec.get("frames"):
            # bullets and other drawn shots bring their own images
            self.frames = spec["frames"]
            self.w, self.h = spec.get("size", (12, 6))
        elif sheet:
            if spec.get("sheet"):
                self.w, self.h = 22, 16
            # the sheet draws its air fireball already tilted down
            self.frames = sheet if self.vy else _angled(sheet, self.vx * self.dir, self.vy)
            if big:
                self.frames = [pygame_scale(f, 1.3) for f in self.frames]
        else:
            self.frames = make_fireball(spec["colors"], big)
        self._flips = {}
        self.t = 0
        self.alive = True
        self.height = "mid"

    def rect(self):
        return (self.x - self.w / 2, self.y - self.h / 2, self.w, self.h)

    def update(self):
        self.t += 1
        self.x += self.vx
        self.y += self.vy
        if self.x < -40 or self.x > 360 or self.y > GROUND_Y - 3:
            self.alive = False

    def _shown(self):
        import pygame
        img = self.frames[(self.t // 3) % len(self.frames)]
        if self.dir < 0:
            flipped = self._flips.get(id(img))
            if flipped is None:
                flipped = self._flips[id(img)] = pygame.transform.flip(img, True, False)
            img = flipped
        w, h = img.get_size()
        cx = w - 9 if self.dir > 0 else 9
        return img, round(self.x - cx), round(self.y - h / 2)

    def area(self):
        """The fireball's drawn pixels, for hit detection."""
        return image_area(*self._shown())

    def draw(self, surf, shake=(0, 0)):
        img, x, y = self._shown()
        surf.blit(img, (x + shake[0], y + shake[1]))


def pygame_scale(img, k):
    import pygame
    return pygame.transform.scale(img, (round(img.get_width() * k), round(img.get_height() * k)))


def _angled(frames, vx, vy):
    """Tilt right-facing fireball frames to fly along (vx, vy)."""
    if not vy:
        return frames
    import math
    import pygame
    deg = -math.degrees(math.atan2(vy, vx))
    return [pygame.transform.rotate(f, deg) for f in frames]


def overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


# Hit detection is pixel exact: an "area" is (mask, x, y), a pygame mask placed
# on the stage. A hit lands when the attack's area touches the target's area.
MIN_STRIKE = 6     # px; an attack drawing with less sticking out uses its box
STRIKE_SLACK = 14  # px the drawn fist or foot may reach past the move's aim box


def rect_area(r):
    import pygame
    x, y, w, h = r
    return pygame.Mask((max(1, round(w)), max(1, round(h))), fill=True), round(x), round(y)


def contact(a, b):
    """Where two areas first touch on the stage, or None."""
    if a is None or b is None:
        return None
    pt = a[0].overlap(b[0], (b[1] - a[1], b[2] - a[2]))
    return None if pt is None else (a[1] + pt[0], a[2] + pt[1])


def touches(a, b):
    if a is None or b is None:
        return False
    return a[0].overlap(b[0], (b[1] - a[1], b[2] - a[2])) is not None


_img_masks = {}


def image_area(img, x, y):
    import pygame
    m = _img_masks.get(id(img))
    if m is None or m[0] is not img:
        m = _img_masks[id(img)] = (img, pygame.mask.from_surface(img, 127))
    return m[1], round(x), round(y)


class Fighter:
    def __init__(self, name, look, moves, hp, walk=1.6, back_walk=1.25, is_player=False, art=None):
        self.name = name
        self.art = art or FighterArt(look)
        self.build = look["build"]
        self.sx, self.sy = BUILDS[self.build][:2]
        self._measure_hurtbox()
        self.moves = moves
        self.max_hp = hp
        self.hp = hp
        self.walk_speed = walk
        self.back_speed = back_walk
        self.is_player = is_player
        self.x = 100.0
        self.y = float(GROUND_Y)
        self.floor = None        # callable(x) -> floor y, for platforms (car roofs)
        self.ghost = None        # callable() -> True while walls should not block
        self.multi_hit = {}      # move name -> (rehit, max_hits) overrides
        self.vx = self.vy = 0.0
        self.facing = 1
        self.state = "stand"     # stand, prejump, air, land, move, hitstun, blockstun,
        self.t = 0               # launched, down, getup, ko, win, intro
        self.pose = "idle0"
        self.move = None
        self.move_t = 0
        self.hits_done = 0
        self.last_hit_t = -99
        self.air_attack_used = False
        self.crouching = False
        self.guard = None
        self.flash = 0
        self.opponent = None
        self.projectiles = None  # list owned by the scene
        self.effects = None      # callback(name, x, y) for dust etc.
        self.buffer = 0
        self.buffer_btn = None
        self.buffer_dirs = (False, False, False)
        self.airborne = False
        self.stun = 0
        self.bounced = False
        self._a_fired = self._r_fired = False
        self.ko = False
        self.tint = None
        self.speed_mul = 1.0
        self.anim = 0
        self.pose_t = 0          # frames the current pose has been showing
        self._last_pose = None
        self.cancel = 0
        self.chain = 0
        self.throw_dir = 1
        self.rot = 0             # degrees the drawing is turned (spinning through the air after a throw)
        self._clock = 0
        self._pressed_at = {"punch": -99, "kick": -99, "special": -99}

    def _measure_hurtbox(self):
        """Hurtbox size comes from the actual standing and crouching sprites."""
        import pygame

        def box(pose):
            m = pygame.mask.from_surface(self.art.frame(pose))
            rects = m.get_bounding_rects()
            return rects[0].unionall(rects)
        st, cr = box("idle0"), box("crouch")
        self.hurt_w = st.w * 0.3
        self.hurt_h = st.h - 2
        self.hurt_ch = cr.h - 2

    # ---- queries ---------------------------------------------------------
    @property
    def on_ground(self):
        return not self.airborne

    @property
    def actionable(self):
        return self.state in ("stand",) or (self.state == "air" and not self.air_attack_used)

    def phase(self):
        if not self.move:
            return None, None
        t = self.move_t
        phases = self.move["phases"]
        for i, (kind, n, pose) in enumerate(phases):
            if t < n:
                return kind, pose
            t -= n
        if self.move.get("hold_last") and self.state == "move":
            kind, n, pose = phases[-1]
            return kind, pose
        return None, None

    def pose_span(self):
        """Frames the current move pose lasts (its run of phases), else None."""
        if self.state != "move" or not self.move or self.move.get("hold_last") and \
                self.move_t >= self.move_length() - 1:
            return None
        t = self.move_t
        phases = self.move["phases"]
        for i, (kind, n, pose) in enumerate(phases):
            if t < n:
                span = n
                j = i + 1
                while j < len(phases) and phases[j][2] == pose:
                    span += phases[j][1]
                    j += 1
                k = i - 1
                while k >= 0 and phases[k][2] == pose:
                    span += phases[k][1]
                    k -= 1
                return span if isinstance(pose, str) else None
            t -= n
        return None

    def move_length(self):
        return sum(n for _, n, _ in self.move["phases"])

    def hurtbox(self):
        if self.state in ("down", "getup", "ko", "held") or self.ko:
            return None
        if self.state == "move":
            inv = self.move.get("invuln")
            if inv and inv[0] <= self.move_t <= inv[1]:
                return None
        w = self.hurt_w
        h = self.hurt_h
        if not self.on_ground:
            return (self.x - w, self.y - h, w * 2, h - 4)
        if self.crouching or (self.move and self.move.get("crouching")) or self.pose in ("crouch", "crouch_block", "hurt_low"):
            h = self.hurt_ch
        return (self.x - w, self.y - h, w * 2, h)

    def hitbox(self):
        if self.state != "move" or not self.move:
            return None
        if "hitbox" not in self.move and "hitbox_px" not in self.move:
            return None
        kind, _ = self.phase()
        if kind != "active":
            return None
        rehit, max_hits = self.multi_hit.get(self.move.get("name"),
                                             (self.move.get("rehit"), self.move.get("max_hits", 99)))
        if rehit:
            if self.hits_done and self.move_t - self.last_hit_t < rehit:
                return None
            if self.hits_done >= max_hits:
                return None
        elif self.hits_done:
            return None
        if "hitbox_px" in self.move:
            hx, hy, hw, hh = self.move["hitbox_px"]
        else:
            hx, hy, hw, hh = self.move["hitbox"]
            hx *= self.sx * CHX
            hw *= self.sx * CHX
            hy *= self.sy * CHY
            hh *= self.sy * CHY
        x = self.x + hx if self.facing > 0 else self.x - hx - hw
        return (x, self.y + hy, hw, hh)

    def shown(self):
        """The drawing on screen this frame."""
        if hasattr(self.art, "resolve"):
            return self.art.resolve(self.pose, self.pose_t, self.anim, self.pose_span())
        return self.pose

    def _placed(self, m, key):
        ax, ay = self.art.anchor(key, self.facing < 0)
        return m, round(self.x) - ax, round(self.y) - ay

    def hurt_area(self):
        """Where this fighter can be hit: exactly the pixels of its drawing."""
        box = self.hurtbox()
        if box is None:
            return None
        if not hasattr(self.art, "mask"):
            return rect_area(box)
        key = self.shown()
        return self._placed(self.art.mask(key, self.facing < 0), key)

    def strike_area(self):
        """What the attack hits with: the fist, foot or flame of the drawing on
        screen (the part reaching out of the body), only on active frames."""
        box = self.hitbox()
        if box is None:
            return None
        if hasattr(self.art, "strike_mask"):
            key = self.shown()
            spin = box[0] < self.x - 4 and box[0] + box[2] > self.x + 4
            m = self.art.strike_mask(key, self.facing < 0, both_sides=spin)
            if m.count() >= MIN_STRIKE and "hitbox" in self.move:
                return self._placed(m, key)
            if m.count() >= MIN_STRIKE:
                # Akuma's moves name the spot they aim at in real pixels: only
                # near there; a hair tip or back foot moving doesn't count: a hair tip or a back foot
                # sliding about during a punch doesn't count as the punch
                m, x, y = self._placed(m, key)
                aim, ax, ay = rect_area((box[0] - STRIKE_SLACK, box[1] - STRIKE_SLACK,
                                         box[2] + 2 * STRIKE_SLACK, box[3] + 2 * STRIKE_SLACK))
                m = m.overlap_mask(aim, (ax - x, ay - y))
                if m.count() >= MIN_STRIKE:
                    return m, x, y
        return rect_area(box)

    def connects(self, other):
        return touches(self.strike_area(), other.hurt_area())

    def threatened(self):
        o = self.opponent
        if o is None:
            return False
        d = abs(o.x - self.x)
        if o.state == "move" and d < 110 and o.move and ("hitbox" in o.move or "hitbox_px" in o.move):
            kind, _ = o.phase()
            if kind in ("startup", "active"):
                return True
        for p in self.projectiles or ():
            if p.owner is not self and abs(p.x - self.x) < 120 and (p.x - self.x) * p.vx < 0:
                return True
        return False

    # ---- actions ---------------------------------------------------------
    def start_move(self, mv, chained=False):
        if not chained:
            self.chain = 1
        self.cancel = 0
        self.move = mv
        self.move_t = 0
        self.hits_done = 0
        self.last_hit_t = -99
        self.state = "move"
        self._a_fired = self._r_fired = False
        self.bounced = False
        if mv.get("air") and not self.on_ground and mv.get("hold_last"):
            self.air_attack_used = True
        if not mv.get("air"):
            self.vx = 0
        self._fire_events(0)

    def _fire_events(self, t):
        ev = self.move.get("events", {}).get(t)
        if ev:
            self._apply(ev)

    def _apply(self, ev):
        if "vx" in ev:
            self.vx = ev["vx"] * self.facing
        if "vxf" in ev:
            self.vx = ev["vxf"] * self.facing * self.speed_mul
        if "vy" in ev:
            self.vy = ev["vy"]
        if "sound" in ev:
            audio.play(ev["sound"])
        if "proj" in ev and self.projectiles is not None:
            spec = ev["proj"]
            if spec.get("px"):
                sx, sy = self.x + self.facing * spec["x"], self.y + spec["y"]
            else:
                sx = self.x + self.facing * 22 * CHX * self.sx
                sy = self.y + spec["y"] * CHY * self.sy
            self.projectiles.append(Projectile(self, sx, sy, spec))

    def choose_player_move(self, button, fwd, back, down):
        """One button per family; the held direction picks the move."""
        M = AKUMA_MOVES
        if self.airborne:
            if self.state != "air" or self.air_attack_used or self.t < 2:
                return None
            if button == "punch":
                return M["jump_jab"]
            if button == "kick":
                return M["dive"] if down else M["jump_kick"]
            if button in ("special", "shoryuken", "tatsu") and not self._own_projectile():
                return M["air_hado"]
            return None
        if button == "throw":
            # held direction picks where they get tossed (neutral = forward)
            self.throw_dir = -self.facing if back else self.facing
            return M["throw"]
        # special + punch = shoryuken, special + kick = tatsu, special alone = fireball
        if button in ("shoryuken", "tatsu"):
            return M[button]
        if button == "special":
            if self._own_projectile():
                return None
            return M["hadouken"]
        if button == "punch":
            return M["crouch_jab"] if down else M["jab"]
        if button == "kick":
            if down:
                return M["crouch_kick"] if fwd else M["sweep"]
            return M["roundhouse"] if back else M["front_kick"]
        return None

    def _own_projectile(self):
        return any(p.owner is self for p in self.projectiles or ())

    def _try_throw(self):
        """Two buttons a frame or two apart: the first button's move is still
        starting up, so turn it into the two-button move (punch+kick = throw,
        special+punch = shoryuken, special+kick = tatsu)."""
        if not (self.is_player and self.buffer and self.on_ground and self.move):
            return False
        btn, cat = self.buffer_btn, self.move.get("cat")
        if btn == "throw":
            if cat not in ("punch", "kick") or self.move_t > THROW_LINK:
                return False
        elif btn in ("shoryuken", "tatsu"):
            first = self.move is AKUMA_MOVES["hadouken"] or cat in ("punch", "kick")
            if not first or self.move_t > SPECIAL_LINK:
                return False
        else:
            return False
        self.buffer = 0
        self.start_move(self.choose_player_move(*self._buffered()))
        return True

    def _try_cancel(self, fwd, back, down):
        """Inside the cancel window a buffered press interrupts the current move."""
        if not (self.cancel > 0 and self.buffer and self.is_player and self.on_ground):
            return False
        if self.chain >= MAX_CHAIN or not self.move:
            return False
        nxt = self.choose_player_move(*self._buffered())
        if nxt is None or nxt.get("cat") not in CANCELS.get(self.move.get("cat"), ()):
            return False
        if nxt is self.move and nxt["cat"] != "punch":
            return False
        self.buffer = 0
        self.chain += 1
        self.crouching = False
        self.start_move(nxt, chained=True)
        return True

    def feed_buffer(self, intent):
        """Remember the latest button press for a few frames. Also called during
        hitstop, so presses made while the screen is frozen still come out."""
        hit = False
        self._clock += 1
        for b in ("punch", "kick", "special"):
            if intent.get(b):
                self.buffer = 8
                self.buffer_btn = b
                self._pressed_at[b] = self._clock
                if b in ("punch", "kick"):
                    other = "kick" if b == "punch" else "punch"
                    # punch + kick together (or a couple of frames apart) = throw
                    if self._clock - self._pressed_at[other] <= THROW_LINK:
                        self.buffer_btn = "throw"
                    # special + punch / kick together = shoryuken / tatsu
                    elif self._clock - self._pressed_at["special"] <= SPECIAL_LINK:
                        self.buffer_btn = SPECIAL_COMBOS[b]
                elif b == "special":
                    for o in ("punch", "kick"):
                        if self._clock - self._pressed_at[o] <= SPECIAL_LINK:
                            self.buffer_btn = SPECIAL_COMBOS[o]
                # directions are read when the button is pressed, like an arcade
                # input buffer, so a press made during hitstop keeps its direction
                self.buffer_dirs = (intent.get("left", False), intent.get("right", False),
                                    intent.get("down", False))
                hit = True
        return hit

    def _buffered(self):
        """(button, fwd, back, down) of the buffered press, relative to facing now."""
        left, right, down = self.buffer_dirs
        fwd, back = (right, left) if self.facing > 0 else (left, right)
        return self.buffer_btn, fwd, back, down

    def face_opponent(self):
        o = self.opponent
        if o and abs(o.x - self.x) > 2:
            self.facing = 1 if o.x > self.x else -1

    # ---- per-frame -------------------------------------------------------
    def update(self, intent):
        """intent: dict with left/right/up/down (held), punch/kick/special (pressed) or
        move (a move dict chosen by AI)."""
        self.anim += 1
        if self.state == "held":
            # being carried by a thrower: the scene places us each frame
            self.buffer = 0
            self.pose_t += 1
            return
        fwd_key = "right" if self.facing > 0 else "left"
        back_key = "left" if self.facing > 0 else "right"
        fwd = intent.get(fwd_key, False)
        back = intent.get(back_key, False)
        down = intent.get("down", False)
        up = intent.get("up", False)
        if not self.feed_buffer(intent) and self.buffer:
            self.buffer -= 1
        self.t += 1
        st = self.state

        if st in ("stand", "land") or (st == "blockstun" and self.t > 0):
            # guard is evaluated every grounded frame so blocking feels instant
            self.guard = ("low" if down else "high") if back else None

        if st == "intro" or st == "win":
            self.vx = 0
            self.pose = "intro" if st == "intro" else "victory"
        elif st == "stand":
            self.face_opponent()
            fwd_key = "right" if self.facing > 0 else "left"
            back_key = "left" if self.facing > 0 else "right"
            fwd = intent.get(fwd_key, False)
            back = intent.get(back_key, False)
            self.guard = ("low" if down else "high") if back else None
            mv = intent.get("move")
            if mv is None and self.buffer and self.is_player:
                mv = self.choose_player_move(*self._buffered())
            if mv is not None:
                self.buffer = 0
                self.crouching = False
                self.start_move(mv)
            elif up:
                self.state = "prejump"
                self.t = 0
                self.vx = (JUMP_VX if fwd else -JUMP_VX if back else 0) * self.facing
                self.pose = "crouch"
            elif down:
                self.crouching = True
                self.vx = 0
                self.pose = "crouch_block" if back and self.threatened() else "crouch"
            else:
                self.crouching = False
                if fwd:
                    self.vx = self.walk_speed * self.facing * self.speed_mul
                    self.pose = "walk"
                elif back:
                    if self.threatened():
                        self.vx = 0
                        self.pose = "block"
                    else:
                        self.vx = -self.back_speed * self.facing * self.speed_mul
                        self.pose = "walk_back"
                else:
                    self.vx = 0
                    self.pose = "idle"
        elif st == "prejump":
            self.crouching = False
            self.pose = "prejump"
            if self.t >= 2:
                self.state = "air"
                self.t = 0
                self.vy = JUMP_VY
                self.air_attack_used = False
                audio.play("jump", 0.6)
        elif st == "air":
            self.pose = "jump_up" if self.vy < -3 else "jump" if self.vy < 1.5 else "fall"
            mv = intent.get("move")
            if mv is None and self.buffer and self.is_player:
                mv = self.choose_player_move(*self._buffered())
            if mv is not None and not self.air_attack_used:
                self.buffer = 0
                self.start_move(mv)
        elif st == "land":
            self.vx = 0
            self.pose = "land"
            if self.t >= LAND_FRAMES:
                self._to_stand()
        elif st == "move" and (self._try_throw() or self._try_cancel(fwd, back, down)):
            kind, pose = self.phase()
            self.pose = pose if not isinstance(pose, list) else pose[0]
        elif st == "move":
            if self.cancel:
                self.cancel -= 1
            self.move_t += 1
            self._fire_events(self.move_t)
            kind, pose = self.phase()
            evs = self.move.get("events", {})
            if kind == "active" and "a" in evs and not getattr(self, "_a_fired", False):
                self._apply(evs["a"])
                self._a_fired = True
            if kind == "recovery" and "r" in evs and not getattr(self, "_r_fired", False):
                self._apply(evs["r"])
                self._r_fired = True
            if kind is None:
                self._a_fired = self._r_fired = False
                if self.move.get("_landing"):
                    self.move = None
                    self._to_stand()
                else:
                    self.move = None
                    self._to_stand() if self.on_ground else self._to_air()
            else:
                if isinstance(pose, list):
                    pose = pose[(self.move_t // 4) % len(pose)]
                self.pose = pose
                if self.on_ground and not self.move.get("keep_vx") and not self.move.get("air"):
                    self.vx *= 0.8
        elif st in ("hitstun", "blockstun"):
            if self.on_ground:
                self.vx *= 0.82
            if self.t >= self.stun and self.on_ground:
                self._to_stand()
                self.guard = ("low" if down else "high") if back else None
        elif st == "launched":
            self.pose = "launch"
        elif st == "down":
            self.vx *= 0.8
            self.pose = "down"
            if self.t >= (38 if not self.ko else 10 ** 9):
                self.state = "getup"
                self.t = 0
        elif st == "getup":
            self.pose = "getup"
            if self.t >= 14:
                self._to_stand()
        elif st == "ko":
            self.pose = "down"
            self.vx *= 0.85

        self._physics()
        if self.pose != self._last_pose:
            self._last_pose = self.pose
            self.pose_t = 0
        else:
            self.pose_t += 1

    def _to_stand(self):
        self.state = "stand"
        self.t = 0
        self.move = None
        self.vx = 0 if self.on_ground else self.vx
        self.pose = "idle0"

    def _to_air(self):
        self.state = "air"
        self.air_attack_used = True
        self.t = 10

    def _gravity_on(self):
        if self.state != "move" or not self.move or self.bounced:
            return True
        ng = self.move.get("no_gravity")
        if ng is True:
            return False
        if type(ng) is int:
            return self.move_t >= ng
        return True

    def _ground(self, x=None):
        """Floor height under x: the stage floor, or a platform (a car roof)."""
        if self.floor is None:
            return float(GROUND_Y)
        return self.floor(self.x if x is None else x)

    def _physics(self):
        # an explicit airborne flag (not a y threshold) decides when we land, so
        # float rounding can never leave an air move sliding along the floor
        if self.vy < 0 and not self.airborne:
            self.airborne = True
        ox, oy = self.x, self.y
        ghost = self.ghost is not None and self.ghost()
        if self.airborne:
            if self._gravity_on():
                self.vy += GRAVITY
            self.y += self.vy
            self.x = max(STAGE_LEFT, min(STAGE_RIGHT, self.x + self.vx))
            g = self._ground()
            # flew into the side of a platform from below its top: stop short
            if not ghost and self.y > g + STEP_UP and oy > g + STEP_UP:
                self.x = ox
                g = self._ground()
            if self.y >= g and self.vy >= 0:
                if oy > g + max(self.vy, 0) + STEP_UP and not ghost:
                    self._eject()       # ended inside a platform: pop out sideways
                    g = self._ground()
                if not ghost or self.y - self.vy <= g + STEP_UP:
                    self.y = g
                    self.airborne = False
                    self._land()
                elif self.y > GROUND_Y:
                    self.y, self.vy = float(GROUND_Y), 0.0   # spinning through a car
        else:
            self.x = max(STAGE_LEFT, min(STAGE_RIGHT, self.x + self.vx))
            g = self._ground()
            if g < self.y - STEP_UP and not ghost:
                self.x = ox             # a wall (the side of a car)
                g = self._ground()
            if g < self.y - STEP_UP:
                self._eject()           # the floor rose under us
                g = self._ground()
            if g > self.y + STEP_UP:
                # walked off a ledge
                self.airborne = True
                self.vy = 0.0
                if self.state in ("stand", "land", "prejump", "crouch"):
                    self.state = "air"
                    self.t = 10
                    self.air_attack_used = False
                    self.crouching = False
                return
            self.y = g
            if self.state == "air" or (self.state == "move" and self.move and self.move.get("air")
                                       and self.move.get("hold_last") and self.vy >= 0
                                       and self.move_t >= self.move_length() - 1):
                self._land()

    def _eject(self):
        """Nearest spot left or right whose floor is not above our feet."""
        for d in range(1, 240):
            for x in (self.x + d * self.facing, self.x - d * self.facing):
                if STAGE_LEFT <= x <= STAGE_RIGHT and self._ground(x) >= self.y - STEP_UP:
                    self.x = x
                    return

    def _land(self):
        self.vy = 0
        if self.state == "air":
            self.state = "land"
            self.t = 0
            self.vx = 0
            audio.play("land", 0.5)
            if self.effects:
                self.effects("dust", self.x, self.y)
        elif self.state == "move" and self.move:
            rec = self.move.get("land_rec", 6)
            if self.bounced:
                rec = 2
            self.move = dict(name="Landing", phases=[("recovery", rec, "land")], _landing=True)
            self.move_t = 0
            self.vx = 0
            if self.effects:
                self.effects("dust", self.x, self.y)
        elif self.state == "launched":
            self.state = "ko" if self.ko else "down"
            self.t = 0
            self.vx *= 0.5
            audio.play("land")
            if self.effects:
                self.effects("dust", self.x, self.y)
        else:
            self.vx = 0

    # ---- being hit -------------------------------------------------------
    def can_block(self, height):
        if self.state not in ("stand", "blockstun", "land") or not self.on_ground:
            return False
        if not self.guard:
            return False
        if height == "low" and self.guard != "low":
            return False
        if height == "high" and self.guard != "high":
            return False
        return True

    def take_block(self, blockstun, push, from_x, chip=0):
        self.state = "blockstun"
        self.stun = blockstun
        self.t = 0
        self.move = None
        self.pose = "crouch_block" if self.guard == "low" else "block"
        away = 1 if self.x > from_x else -1
        self.vx = push * away
        if chip and self.hp - chip > 0:
            self.hp -= chip

    def take_hit(self, dmg, hitstun, from_x, knockdown=False, launch=-4.5, push=2.5, opener=False):
        self.hp = max(0, self.hp - dmg)
        self.flash = 10
        self.move = None
        away = 1 if self.x > from_x else -1
        crouched = self.crouching
        self.crouching = False
        if self.hp <= 0:
            self.ko = True
            self.state = "launched"
            self.vy = -6.0
            self.vx = 2.4 * away
            self.y = min(self.y, self._ground() - 1)
            return
        if knockdown or self.state == "launched" or (not self.on_ground and not opener):
            self.state = "launched"
            self.vy = launch if launch else -4.5
            self.vx = 1.8 * away
            self.y = min(self.y, self._ground() - 1)
            self.t = 0
            return
        self.state = "hitstun"
        self.stun = hitstun
        self.t = 0
        self.vx = push * away
        self.pose = "hurt_low" if crouched else "hurt"

    # ---- drawing ---------------------------------------------------------
    def draw(self, surf, shake=(0, 0)):
        import pygame
        flip = self.facing < 0
        pose = self.shown()
        img = self.art.frame(pose, flip, flash=self.flash > 0 and self.flash % 4 >= 2)
        ax, ay = self.art.anchor(pose, flip)
        x = round(self.x) - ax + shake[0]
        y = round(self.y) - ay + shake[1]
        # shadow
        sw = int(self.hurt_w * 2.2)
        pygame.draw.ellipse(surf, (20, 14, 24),
                            (round(self.x) - sw // 2 + shake[0], round(self._ground()) - 2 + shake[1], sw, 5))
        if self.rot:
            # spun while being thrown: turn the drawing about its middle
            w, h = img.get_size()
            img = pygame.transform.rotate(img, self.rot)
            x += (w - img.get_width()) // 2
            y += (h - img.get_height()) // 2
            surf.blit(img, (x, y))
            return
        if self.tint:
            aura = self.art.frame(pose, flip, flash=True).copy()
            aura.fill(self.tint + (255,), special_flags=pygame.BLEND_RGBA_MULT)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                surf.blit(aura, (x + dx, y + dy))
        surf.blit(img, (x, y))


# --------------------------------------------------------------------------
class AI:
    """Simple but readable fighting-game brain driven by a few personality
    numbers, so grunts with the same moves still behave differently."""

    def __init__(self, rng, aggression, block, jumpiness, reaction, boss=False):
        self.rng = rng
        self.aggr = aggression
        self.block = block
        self.jumpy = jumpiness
        self.react = reaction
        self.boss = boss
        self.cool = 40
        self.walk_dir = 0
        self.walk_t = 0
        self.guarding = 0
        self.guard_low = False
        self.seen_threat = None
        self.pref = 40

    def setup(self, f):
        rs = [m["range"] for m in f.moves]
        mids = sorted((a + min(b, 160)) / 2 for a, b in rs)
        self.pref = mids[len(mids) // 2]

    def think(self, f):
        o = f.opponent
        rng = self.rng
        intent = {}
        dist = abs(o.x - f.x)
        toward = "right" if o.x > f.x else "left"
        away = "left" if toward == "right" else "right"
        if self.cool > 0:
            self.cool -= 1

        # --- defend -------------------------------------------------------
        threat = None
        if o.state == "move" and o.move and ("hitbox" in o.move or "hitbox_px" in o.move) and dist < 100 and o.move_t >= self.react:
            kind, _ = o.phase()
            if kind in ("startup", "active"):
                threat = ("m", id(o.move), o.move.get("height", "mid"))
        pdist = 999
        for p in f.projectiles:
            if p.owner is o and abs(p.x - f.x) < 110 and (p.x - f.x) * p.vx < 0:
                threat = ("p", id(p), "mid")
                pdist = abs(p.x - f.x)
        if threat and threat[:2] != self.seen_threat:
            self.seen_threat = threat[:2]
            if threat[0] == "p" and rng.random() < self.jumpy and pdist > 50:
                intent["up"] = True
                intent[toward] = True
                return intent
            if rng.random() < self.block:
                self.guarding = 26
                h = threat[2]
                self.guard_low = (h == "low") if rng.random() < 0.8 else (h != "low")
            else:
                self.guarding = 0
        if self.guarding > 0:
            self.guarding -= 1
            intent[away] = True
            if self.guard_low:
                intent["down"] = True
            return intent

        if f.state != "stand":
            return intent

        # --- anti-air ----------------------------------------------------
        if not o.on_ground and dist < 70 and o.vy > -2:
            for m in f.moves:
                if m.get("anti_air") and rng.random() < 0.12 + self.aggr * 0.25:
                    intent["move"] = m
                    self.cool = rng.randint(25, 50)
                    return intent

        # --- attack ------------------------------------------------------
        if self.cool == 0 and o.state not in ("down", "getup", "ko"):
            options = [m for m in f.moves if m["range"][0] <= dist <= m["range"][1]]
            if options and rng.random() < 0.05 + self.aggr * 0.12:
                m = rng.choice(options)
                if not (m.get("projectile") and any(p.owner is f for p in f.projectiles)):
                    intent["move"] = m
                    self.cool = int(rng.randint(30, 80) / (0.6 + self.aggr))
                    return intent

        # --- footsies ----------------------------------------------------
        if self.walk_t <= 0:
            self.walk_t = rng.randint(10, 35)
            if dist > self.pref + 12:
                self.walk_dir = 1 if rng.random() < 0.6 + self.aggr * 0.4 else 0
            elif dist < self.pref - 12:
                self.walk_dir = -1 if rng.random() < 0.7 else 0
            else:
                self.walk_dir = rng.choice([-1, 0, 0, 1])
            if rng.random() < self.jumpy * 0.15 and dist < 150:
                intent["up"] = True
                intent[toward] = True
        self.walk_t -= 1
        if self.walk_dir > 0:
            intent[toward] = True
        elif self.walk_dir < 0:
            intent[away] = True
        return intent
