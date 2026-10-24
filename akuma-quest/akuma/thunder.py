"""Geldra's Hideout: a Rolling Thunder (NES) style side-scroller.

One long street front with two floors: the ground and a balcony walkway above
it. Hooded Geldra maskers (fighters from the sprite pack, tinted by rank) step
out of the doors along both floors and open fire. Akuma has no gun: his
hadouken is the gun, paid for with ki (ki doors refill it, rapid-fire doors
make it free for a while) and his shoryuken and hurricane kick are the close
range answer. Standing shooters fire at head height (DOWN ducks under it),
crouching shooters fire at the shins (jump it). UP under a balcony vaults up to
the walkway with a flip, DOWN + UP on the walkway drops back down, I ducks into
a door (hidden while inside; ki / food / rapid doors give their item once).
At the far end Dr. Doom, master of Geldra, waits in a locked courtyard.

Whole-level scene like metroid.py: game.level_done(self, hp) when Doom falls,
game.level_failed(self) when the last life is lost.
"""

import math
import random

import pygame

from . import audio
from . import metroid as _mt
from .akuma_sprites import hado_frames
from .art import OUTLINE
from .config import W, H
from .fighters import touches, rect_area, image_area
from .font import draw_text, text_width
from .metroid import SmallArt, _shrink
from .pause import PauseMenu
from .snacks import random_snack, heal_amount, snack_image

# ---------------------------------------------------------------------------
# tuning
# ---------------------------------------------------------------------------
SCALE = 0.6                  # fight sprites at street size (Akuma ~42 px tall, ~32 ducking)
GROUND = 168                 # feet on the street
UPPER = 96                   # feet on the balcony walkway
LW = 3360                    # level width, px
ARENA_X = LW - W             # Doom's courtyard: the last screen
AREA2_X = 1720               # warehouse -> Geldra base

GRAV = 0.34
MAX_FALL = 7.0
RUN = 1.7
ACC_GROUND, ACC_AIR = 0.45, 0.28
JUMP_V = -5.4                # ~43 px: clears a shin-high shot
VAULT_V = -7.7               # ~87 px: up onto the walkway (it is 72 px up)
JUMP_BUFFER = 6
PW = 10
DUCK_KEY = "f87_2"           # Akuma's lowest kneeling drawing: the duck
HIGH, LOW = 36, 8            # enemy shot heights above the shooter's feet
HURT_T, INVULN = 14, 50
LIVES = 3
RESPAWN_INV = 120
KI_MAX, HADO_COST, KI_REGEN, KI_ON_HIT = 100, 25, 0.06, 4
RAPID_T = 60 * 12
DOOR_T = 46                  # frames Akuma hides in a door
DOOR_W, DOOR_H = 24, 48
MAX_ACTIVE = 4
INTRO = 160
SPECIAL_WINDOW = 4           # frames: special + punch / kick together = shoryuken / tatsu
DIAG = 2.7                   # air hadouken speed on each axis (45 degrees down)
SHOT_V = 2.3
DMG = dict(shot=12, punch=14, kick=16, beam=26, wave=18, boss_punch=22)
BOSS_HP = 520
BOSS_SCALE = 0.85

CONTROLS = [
    "ARROWS / WASD: WALK   UP: JUMP   DOWN: DUCK",
    "UP UNDER A BALCONY: VAULT UP TO THE WALKWAY",
    "DOWN + UP ON THE WALKWAY: DROP DOWN",
    "J PUNCH (3-HIT STRING)   K KICK   DOWN: LOW",
    "L SPECIAL: HADOUKEN, COSTS KI (IN THE AIR: 45 DOWN)",
    "L + J TOGETHER: SHORYUKEN   L + K: HURRICANE",
    "I IN FRONT OF A DOOR: DUCK INSIDE AND HIDE",
    "KI / FOOD / RAPID DOORS GIVE THEIR ITEM ONCE",
    "STANDING SHOOTERS AIM HIGH: DUCK",
    "CROUCHING SHOOTERS AIM LOW: JUMP",
]

# Geldra's maskers wear their rank's colour (like the NES hoods)
_mt.TINTS.setdefault("rt_blue", ((120, 150, 255), 70, (0, 2, 22)))
_mt.TINTS.setdefault("rt_red", ((255, 110, 100), 70, (22, 0, 0)))
_mt.TINTS.setdefault("rt_green", ((120, 235, 120), 70, (0, 14, 0)))
_mt.TINTS.setdefault("rt_purple", ((205, 120, 255), 80, (14, 0, 24)))

GRUNT_CIDS = ["ryu", "ken", "sakura", "felicia", "hsienko", "chunli"]
KINDS = {
    #            hp, walk speed, tint, shots per volley (0 = melee), points
    "masker": dict(hp=20, speed=0.7, tint="rt_blue", shots=1, pts=100),
    "brawler": dict(hp=30, speed=1.25, tint="rt_red", shots=0, pts=200),
    "leaper": dict(hp=30, speed=1.0, tint="rt_green", shots=0, pts=300, leaps=True),
    "gunner": dict(hp=50, speed=0.6, tint="rt_purple", shots=3, pts=400),
}
SPAWN_WEIGHTS = {1: [("masker", 55), ("brawler", 30), ("leaper", 15)],
                 2: [("masker", 35), ("brawler", 20), ("leaper", 25), ("gunner", 20)]}

# Akuma's moves: phases (kind, frames, pose); kind s(tartup) a(ctive) r(ecovery)
MOVES = {
    "jab1": dict(ph=[("s", 4, "punch_prep"), ("a", 5, "punch"), ("r", 9, "punch_rec")], dmg=10, kb=1.4, lunge=1.2),
    "jab2": dict(ph=[("s", 3, "punch_prep"), ("a", 5, "punch"), ("r", 9, "punch_rec")], dmg=11, kb=1.4, lunge=1.2),
    "jab3": dict(ph=[("s", 6, "sho_crouch"), ("a", 9, "sho_rise"), ("r", 14, "sho_fall")], dmg=18, kb=3.0,
                 lunge=1.6, hop=-2.6, heavy=True),
    "cjab": dict(ph=[("s", 3, "cr_punch_prep"), ("a", 5, "crouch_jab"), ("r", 8, "cr_punch_rec")], dmg=9, kb=1.2,
                 low=True),
    "kick": dict(ph=[("s", 8, "kick_prep"), ("a", 7, "kick"), ("r", 13, "kick_rec")], dmg=18, kb=3.2,
                 lunge=0.8, heavy=True),
    "sweep": dict(ph=[("s", 6, "sweep_prep"), ("a", 7, "sweep"), ("r", 14, "sweep_rec")], dmg=14, kb=2.2,
                  lunge=1.0, low=True),
    "ajab": dict(ph=[("s", 2, "jpunch_prep"), ("a", 10, "jump_jab"), ("r", 4, "jump")], dmg=10, kb=1.4, air=True),
    "akick": dict(ph=[("s", 3, "jkick_prep"), ("a", 12, "jump_kick"), ("r", 4, "jump")], dmg=16, kb=2.4, air=True),
    "dive": dict(ph=[("s", 5, "jump"), ("a", 90, "dive"), ("r", 10, "land")], dmg=20, kb=2.0, air=True, dive=True),
    "hado": dict(ph=[("s", 9, "hado_prep"), ("a", 4, "hado_fire"), ("r", 12, "hado_fire")], dmg=20, kb=1.6,
                 proj=True),
    # a rapid-fire door's gift: free and fast, a little weaker
    "rhado": dict(ph=[("s", 3, "hado_prep"), ("a", 2, "hado_fire"), ("r", 6, "hado_fire")], dmg=14, kb=1.2,
                  proj=True),
    "ahado": dict(ph=[("s", 6, "air_hado_prep"), ("a", 4, "air_hado"), ("r", 10, "jump")], dmg=18, kb=1.6,
                  proj=True, air=True),
    # special + punch: rising dragon punch, invincible on the way up
    "shoryu": dict(ph=[("s", 3, "sho_crouch"), ("a", 14, "sho_rise"), ("r", 18, "sho_fall")], dmg=30, kb=3.2,
                   lunge=1.6, hop=-6.4, heavy=True, inv=(0, 12), body=True),
    # special + kick: hurricane kick, travels forward hitting both sides
    "tatsu": dict(ph=[("s", 5, "tatsu_start"), ("a", 32, "tatsu"), ("r", 10, "tatsu_end")], dmg=9, kb=1.8,
                  spin=True, rehit=8),
}
COMBO = {"jab1": "jab2", "jab2": "jab3"}


# ---------------------------------------------------------------------------
# the street: balconies and doors, per seed
# ---------------------------------------------------------------------------
class Street:
    def __init__(self, seed):
        rng = random.Random(seed * 31 + 7)
        self.balconies = []          # (x0, x1) walkway spans at UPPER
        x = 230
        while x < ARENA_X - 160:
            w = rng.randrange(260, 520)
            x1 = min(x + w, ARENA_X - 60)
            if x1 - x >= 160:
                self.balconies.append((x, x1))
            x = x1 + rng.randrange(70, 130)
        self.balconies.append((ARENA_X + 70, LW - 70))
        self.doors = []
        for floor in (GROUND, UPPER):
            x = 300 + (0 if floor == GROUND else 60)
            while x < ARENA_X - 40:
                if floor == GROUND or self.covered(x, 26):
                    self.doors.append(dict(x=x, y=floor, kind="spawn", stock=rng.choice((1, 2, 2)),
                                           cd=rng.randrange(0, 90), open=0.0, opening=0, used=False))
                x += rng.randrange(150, 230)
        # item doors: a few of the street doors hold something instead of a masker
        street = [d for d in self.doors if 500 < d["x"] < ARENA_X - 80]
        rng.shuffle(street)
        for kind, n in (("ki", 3), ("food", 3), ("rapid", 2)):
            for _ in range(n):
                if street:
                    d = street.pop()
                    d["kind"], d["stock"] = kind, 0
        # the courtyard: two doors Doom calls his men out of
        for x, y in ((ARENA_X + 34, GROUND), (LW - 34, GROUND), (ARENA_X + 110, UPPER), (LW - 110, UPPER)):
            self.doors.append(dict(x=x, y=y, kind="arena", stock=0, cd=0, open=0.0, opening=0, used=False))
        self.doors.sort(key=lambda d: d["x"])

    def covered(self, x, margin=0):
        """Is there walkway over x (with margin px of it either side)?"""
        return any(x0 + margin <= x <= x1 - margin for x0, x1 in self.balconies)

    def span(self, x):
        for s in self.balconies:
            if s[0] <= x <= s[1]:
                return s
        return None


def fall(st, b, lo=0, hi=LW):
    """Gravity and the one-way walkway for a feet-anchored body."""
    b.vy = min(MAX_FALL, b.vy + GRAV)
    ny = b.y + b.vy
    land = None
    if b.vy >= 0:
        if b.y <= UPPER + 0.01 and ny >= UPPER and st.covered(b.x):
            land = UPPER
        elif ny >= GROUND:
            land = GROUND
    if land is not None:
        b.y, b.vy, b.on_ground = float(land), 0.0, True
    else:
        b.y, b.on_ground = ny, False
    b.x = max(lo, min(hi, b.x + b.vx))
    if b.on_ground and b.y == UPPER and not st.covered(b.x):
        b.on_ground = False           # walked off the end of the walkway


# ---------------------------------------------------------------------------
# art
# ---------------------------------------------------------------------------
_ART = {}
AREA_COLS = {
    1: dict(wall=(92, 58, 48), mortar=(64, 38, 34), dark=(52, 32, 30), trim=(150, 104, 70),
            door=(112, 70, 40), door2=(84, 50, 30), floor=(96, 88, 84), rail=(160, 150, 140)),
    2: dict(wall=(52, 64, 92), mortar=(36, 44, 66), dark=(30, 36, 54), trim=(120, 140, 170),
            door=(70, 84, 110), door2=(48, 58, 80), floor=(74, 80, 96), rail=(150, 170, 200)),
    3: dict(wall=(74, 34, 46), mortar=(50, 22, 30), dark=(38, 16, 24), trim=(170, 80, 80),
            door=(96, 40, 46), door2=(70, 26, 32), floor=(84, 64, 70), rail=(200, 120, 120)),
}


def area_of(x):
    return 3 if x >= ARENA_X else 2 if x >= AREA2_X else 1


def _street_surface(st, rng):
    s = pygame.Surface((LW, H))
    s.fill((10, 8, 22))
    top = UPPER - 58
    for area, x0, x1 in ((1, 0, AREA2_X), (2, AREA2_X, ARENA_X), (3, ARENA_X, LW)):
        c = AREA_COLS[area]
        s.fill(c["wall"], (x0, top, x1 - x0, GROUND - top))
        # bricks / panels
        if area == 2:
            for x in range(x0, x1, 40):
                s.fill(c["mortar"], (x, top, 2, GROUND - top))
            for y in range(top + 14, GROUND, 18):
                s.fill(c["mortar"], (x0, y, x1 - x0, 1))
            for x in range(x0 + 8, x1, 40):
                for y in range(top + 6, GROUND - 6, 18):
                    s.fill(c["trim"], (x, y, 2, 2))
        else:
            for row, y in enumerate(range(top, GROUND, 7)):
                s.fill(c["mortar"], (x0, y, x1 - x0, 1))
                off = 0 if row % 2 else 8
                for x in range(x0 + off, x1, 16):
                    s.fill(c["mortar"], (x, y, 1, 7))
        # roof line and a dark band under the walkway
        s.fill(c["trim"], (x0, top - 4, x1 - x0, 4))
        s.fill(OUTLINE, (x0, top - 5, x1 - x0, 1))
        s.fill(c["dark"], (x0, UPPER + 6, x1 - x0, 8))
        # windows on the upper storey where there is no walkway
        for x in range(x0 + 20, x1 - 30, 64):
            if not st.covered(x + 12, -20):
                s.fill(OUTLINE, (x, top + 12, 26, 30))
                s.fill((30, 40, 70) if area != 3 else (60, 20, 30), (x + 2, top + 14, 22, 26))
                if rng.random() < 0.4:
                    s.fill((200, 190, 120), (x + 4, top + 16, 4, 4))
                s.fill(c["trim"], (x - 2, top + 42, 30, 3))
        # lamps and Geldra posters
        for x in range(x0 + 90, x1 - 20, rng.randrange(170, 260)):
            y = GROUND - 66
            s.fill(OUTLINE, (x - 1, y - 1, 12, 16))
            s.fill((150, 30, 30) if area != 2 else (120, 30, 140), (x, y, 10, 14))
            pygame.draw.circle(s, (230, 220, 200), (x + 5, y + 5), 3)
            s.fill((20, 10, 10), (x + 3, y + 4, 1, 2))
            s.fill((20, 10, 10), (x + 6, y + 4, 1, 2))
            s.fill((230, 220, 200), (x + 3, y + 9, 5, 2))
    # the street
    for area, x0, x1 in ((1, 0, AREA2_X), (2, AREA2_X, ARENA_X), (3, ARENA_X, LW)):
        c = AREA_COLS[area]
        s.fill(OUTLINE, (x0, GROUND, x1 - x0, 1))
        s.fill(c["floor"], (x0, GROUND + 1, x1 - x0, H - GROUND))
        s.fill(tuple(min(255, v + 30) for v in c["floor"]), (x0, GROUND + 1, x1 - x0, 1))
        for x in range(x0, x1, 32):
            s.fill(tuple(max(0, v - 22) for v in c["floor"]), (x, GROUND + 3, 1, H - GROUND))
    # walkways: slab, posts and a railing behind the walker
    for x0, x1 in st.balconies:
        c = AREA_COLS[area_of(x0)]
        s.fill(c["dark"], (x0, UPPER - 18, x1 - x0, 1))
        s.fill(c["rail"], (x0, UPPER - 17, x1 - x0, 2))
        for x in range(x0 + 2, x1, 12):
            s.fill(c["rail"], (x, UPPER - 15, 1, 15))
        s.fill(OUTLINE, (x0 - 1, UPPER, x1 - x0 + 2, 7))
        s.fill(c["trim"], (x0, UPPER + 1, x1 - x0, 5))
        s.fill(tuple(min(255, v + 40) for v in c["trim"]), (x0, UPPER + 1, x1 - x0, 1))
        for x in (x0 + 6, x1 - 10) + tuple(range(x0 + 120, x1 - 60, 120)):
            s.fill(OUTLINE, (x - 1, UPPER + 6, 6, GROUND - UPPER - 6))
            s.fill(c["dark"], (x, UPPER + 6, 4, GROUND - UPPER - 6))
            s.fill(c["rail"], (x, UPPER + 6, 1, GROUND - UPPER - 6))
    return s


def _sky():
    s = pygame.Surface((W, H))
    for y in range(H):
        k = y / H
        s.fill((round(8 + 20 * k), round(6 + 10 * k), round(26 + 30 * k)), (0, y, W, 1))
    rng = random.Random(4)
    for _ in range(40):
        s.fill((200, 200, 230), (rng.randrange(W), rng.randrange(40), 1, 1))
    pygame.draw.circle(s, (240, 230, 190), (250, 18), 9)
    pygame.draw.circle(s, (18, 12, 36), (254, 16), 8)
    return s


def _ki_ball(col):
    s = pygame.Surface((9, 7), pygame.SRCALPHA)
    pygame.draw.ellipse(s, col + (255,), (0, 0, 9, 7))
    pygame.draw.ellipse(s, (255, 255, 230, 255), (2, 2, 5, 3))
    return s


def _beam_img():
    s = pygame.Surface((34, 12), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (90, 255, 120, 255), (0, 0, 34, 12))
    pygame.draw.ellipse(s, (220, 255, 220, 255), (6, 3, 24, 6))
    return s


def _wave_img():
    s = pygame.Surface((10, 13), pygame.SRCALPHA)
    for k, col in enumerate(((90, 255, 120), (40, 180, 80), (20, 90, 40))):
        s.fill(col + (255,), (k, k * 3, 10 - k * 2, 13 - k * 3))
    return s


def _art():
    if not _ART:
        a = _ART
        a["hado"] = [_shrink(f, SCALE) for f in hado_frames("akuma")]
        a["ki"] = {"rt_blue": _ki_ball((110, 150, 255)), "rt_purple": _ki_ball((210, 110, 255)),
                   "boss": _ki_ball((90, 255, 120))}
        a["beam"] = _beam_img()
        a["wave"] = _wave_img()
        a["sky"] = _sky()
    return _ART


_ROT_HADO = {}
_SFX_DONE = False


def _build_sounds():
    """This level's own synthesised cues (audio.play() of a missing one is silent)."""
    global _SFX_DONE
    if _SFX_DONE or not getattr(audio, "_ok", False):
        return
    _SFX_DONE = True
    S, tone, noise, add = audio._sfx, audio._tone, audio._noise, audio._add
    try:
        S.setdefault("rt_door", audio._sound(add(noise(0.18, 0.2, 1.4, 0.2), tone(160, 120, 0.18, 0.15, "square"))))
        S.setdefault("rt_shot", audio._sound(tone(900, 500, 0.08, 0.14, "square", 0, 0.25)))
        S.setdefault("rt_beam", audio._sound(add(tone(300, 1200, 0.4, 0.2, "saw"), noise(0.4, 0.15, 0.8, 0.3))))
        S.setdefault("rt_tell", audio._sound(tone(1200, 1250, 0.05, 0.1, "square", 0, 0.5)))
        S.setdefault("rt_item", audio._sound(add(tone(660, 990, 0.12, 0.2, "tri"), tone(990, 1320, 0.2, 0.15, "tri"))))
        S.setdefault("rt_tatsu", audio._sound(add(noise(0.3, 0.3, 1.0, 0.1), tone(300, 520, 0.3, 0.15, "tri"))))
        S.setdefault("rt_slam", audio._sound(add(noise(0.35, 0.7, 1.8, 0.2), tone(80, 30, 0.3, 0.5, "square", 0.2))))
    except Exception:       # never let a sound break the level
        pass


# ---------------------------------------------------------------------------
# actors
# ---------------------------------------------------------------------------
class Hero:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.face = 1
        self.on_ground = True
        self.state = "move"          # move attack hurt door dead
        self.t = 0
        self.jbuf = 0
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
        self.ducking = False
        self.vault = 0               # frames into a vault flip (0 = not vaulting)
        self.door = None
        self.since = {"punch": 99, "kick": 99, "special": 99}


class Shot:
    def __init__(self, x, y, vx, vy, kind, dmg, friendly, owner=None, move=None, tint=None):
        self.x, self.y, self.vx, self.vy = float(x), float(y), vx, vy
        self.kind, self.dmg, self.friendly, self.owner = kind, dmg, friendly, owner
        self.move, self.tint = move, tint
        self.t = 0
        self.dead = False
        self.hit = set()

    def image(self):
        a = _art()
        if self.kind == "hado":
            fr = a["hado"]
            i = min(len(fr) - 1, 2 + (self.t // 3) % max(1, len(fr) - 2))
            if self.vy:
                ang = round(-math.degrees(math.atan2(self.vy, abs(self.vx) or 0.001)))
                key = (i, ang, self.vx < 0)
                img = _ROT_HADO.get(key)
                if img is None:
                    img = pygame.transform.rotate(fr[i], ang)
                    if self.vx < 0:
                        img = pygame.transform.flip(img, True, False)
                    _ROT_HADO[key] = img
                return img
            return pygame.transform.flip(fr[i], True, False) if self.vx < 0 else fr[i]
        if self.kind == "beam":
            return a["beam"]
        if self.kind == "wave":
            return a["wave"]
        return a["ki"].get(self.tint, a["ki"]["rt_blue"])

    def area(self):
        img = self.image()
        if self.kind == "wave":            # stands on the floor
            return image_area(img, self.x - img.get_width() / 2, self.y - img.get_height())
        return image_area(img, self.x - img.get_width() / 2, self.y - img.get_height() / 2)


class Enemy:
    REACH = 22
    TELL = 30

    def __init__(self, sc, x, y, kind, cid=None, door=None):
        cfg = KINDS[kind]
        self.sc = sc
        self.kind = kind
        self.cfg = cfg
        self.cid = cid or sc.rng.choice(GRUNT_CIDS)
        self.art = SmallArt(self.cid, SCALE, cfg["tint"])
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.on_ground = True
        self.face = -1 if sc.p.x < x else 1
        self.hp = self.max_hp = cfg["hp"]
        self.state = "emerge" if door else "walk"
        self.t = 0
        self.pose, self.pose_t, self.span = "idle", 0, None
        self.flash = 0
        self.cd = sc.rng.randrange(30, 80)
        self.hit_done = False
        self.dead_t = 0
        self.gone = False
        self.door = door
        self.shots_left = 0
        self.low = False
        self.other_t = 0             # frames Akuma has been on the other floor
        self.uid = sc.next_uid()

    # ---- areas ------------------------------------------------------------
    def key(self):
        return self.art.resolve(self.pose, self.pose_t, self.sc.t, self.span)

    def body_area(self):
        if self.state == "emerge" and self.t < 8:
            return None
        key = self.key()
        img, (ax, ay) = self.art.entry(key, self.face < 0)
        return self.art.mask(key, self.face < 0), round(self.x - ax), round(self.y - ay)

    def strike_area(self):
        key = self.key()
        flip = self.face < 0
        m = self.art.strike(key, flip)
        if m is None:
            return rect_area((self.x + (4 if self.face > 0 else -4 - self.REACH), self.y - 26, self.REACH, 14))
        img, (ax, ay) = self.art.entry(key, flip)
        return m, round(self.x - ax), round(self.y - ay)

    @property
    def alive(self):
        return self.state != "dead"

    def set_pose(self, pose, span=None):
        if pose != self.pose:
            self.pose, self.pose_t = pose, 0
        self.span = span

    def same_floor(self):
        p = self.sc.p
        return abs(p.y - self.y) < 24 and p.state not in ("door", "dead")

    # ---- behaviour --------------------------------------------------------
    def update(self):
        self.t += 1
        self.pose_t += 1
        if self.flash:
            self.flash -= 1
        if self.state == "dead":
            self.dead_t += 1
            self.set_pose("down" if self.dead_t > 12 else "launch")
            self.vx *= 0.95
            fall(self.sc.st, self)
            if self.dead_t > 60:
                self.gone = True
            return
        if self.state == "hurt":
            self.set_pose("hurt", 14)
            self.vx *= 0.85
            fall(self.sc.st, self)
            if self.t >= 14:
                self.state, self.t = "walk", 0
            return
        if self.state == "emerge":
            self.set_pose("walk")
            self.face = 1 if self.sc.p.x > self.x else -1
            if self.t > 10:
                self.vx = self.face * 0.6
            fall(self.sc.st, self)
            if self.t >= 26:
                self.state, self.t = "walk", 0
            return
        self.think()
        lo, hi = self.sc.bounds(self)
        fall(self.sc.st, self, lo, hi)

    def edge_ok(self, d):
        """Walking d (-1 / 1) keeps a walkway walker on the walkway."""
        if self.y > UPPER + 1:
            return True
        return self.sc.st.covered(self.x + d * 8)

    def walk(self, d, speed):
        self.vx = d * speed if d and self.edge_ok(d) else 0.0
        self.set_pose("walk" if self.vx else "idle")

    def think(self):
        sc, p = self.sc, self.sc.p
        dx = p.x - self.x
        dist = abs(dx)
        if self.cd:
            self.cd -= 1
        st = self.state
        if st == "walk":
            if not self.on_ground:
                self.set_pose("jump")
                return
            self.face = 1 if dx > 0 else -1
            if not self.same_floor():
                self.other_t += 1
                if self.cfg.get("leaps") and p.state not in ("door", "dead") and dist < 110 and self.other_t > 40:
                    if p.y < self.y - 30 and sc.st.covered(self.x, 6):
                        self.vy, self.vx, self.on_ground = VAULT_V, 0.0, False
                        self.other_t = 0
                        return
                    if p.y > self.y + 30 and self.y <= UPPER + 1:
                        # step off the walkway's edge or straight down through it
                        self.y += 2
                        self.vx = self.face * 0.8
                        self.on_ground = False
                        self.other_t = 0
                        return
                # wander about on our own floor, drifting with Akuma
                self.walk(self.face if dist > 60 else 0, self.cfg["speed"] * 0.6)
                return
            self.other_t = 0
            if self.cfg["shots"]:
                if dist > 150:
                    self.walk(self.face, self.cfg["speed"])
                elif dist < 56 and self.edge_ok(-self.face):
                    self.vx = -self.face * self.cfg["speed"] * 0.7
                    self.set_pose("walk_back")
                else:
                    self.vx = 0.0
                    self.set_pose("idle")
                    if not self.cd:
                        self.start_aim()
            else:
                if self.cfg.get("leaps") and 46 < dist < 90 and not self.cd:
                    self.state, self.t = "leap", 0
                    self.vy, self.vx, self.on_ground = -4.2, self.face * 2.0, False
                    self.hit_done = False
                    return
                if dist > self.REACH + 6:
                    self.walk(self.face, self.cfg["speed"])
                else:
                    self.vx = 0.0
                    self.set_pose("idle")
                    if not self.cd:
                        self.state, self.t = "windup", 0
                        sc.event("windup", self)
                        audio.play("rt_tell", 0.5)
        elif st == "aim":
            self.vx = 0.0
            self.set_pose("crouch" if self.low else "hado_prep", 10)
            if self.t >= self.TELL:
                self.fire()
        elif st == "fire":
            self.set_pose("crouch_jab" if self.low else "hado_fire", 10)
            if self.t >= 14:
                if self.shots_left > 0:
                    self.state, self.t = "aim", self.TELL - 10
                else:
                    self.state, self.t = "walk", 0
                    self.cd = sc.rng.randrange(70, 140)
        elif st == "windup":
            self.vx = 0.0
            self.set_pose("punch_prep", 22)
            if self.t >= 22:
                self.state, self.t = "attack", 0
                self.hit_done = False
                self.vx = self.face * 1.6
                audio.play("whiff", 0.6)
        elif st == "attack":
            self.set_pose("punch", 8)
            self.vx *= 0.85
            if not self.hit_done and touches(self.strike_area(), sc.hero_area()):
                if sc.hurt_player(DMG["punch"], self):
                    self.hit_done = True
            if self.t >= 8:
                self.state, self.t = "walk", 0
                self.cd = sc.rng.randrange(40, 80)
        elif st == "leap":
            self.set_pose("jump_kick")
            if not self.hit_done and touches(self.strike_area(), sc.hero_area()):
                if sc.hurt_player(DMG["kick"], self):
                    self.hit_done = True
            if self.on_ground and self.t > 3:
                self.vx = 0.0
                self.state, self.t = "walk", 0
                self.cd = sc.rng.randrange(60, 110)

    def start_aim(self):
        self.state, self.t = "aim", 0
        self.shots_left = self.cfg["shots"]
        self.low = self.sc.rng.random() < 0.45
        self.sc.event("aim", self, "low" if self.low else "high")
        audio.play("rt_tell", 0.4)

    def fire(self):
        self.shots_left -= 1
        h = LOW if self.low else HIGH
        self.sc.shots.append(Shot(self.x + self.face * 10, self.y - h, self.face * SHOT_V, 0, "ki", DMG["shot"],
                                  False, self, tint=self.cfg["tint"]))
        self.sc.event("fire", self, "low" if self.low else "high")
        audio.play("rt_shot", 0.5)
        self.state, self.t = "fire", 0

    def hurt(self, dmg, kb, move):
        self.hp -= dmg
        self.flash = 6
        if self.hp <= 0:
            self.state, self.t = "dead", 0
            self.vx, self.vy = kb * 1.2, -2.5
            self.on_ground = False
            self.sc.enemy_died(self)
        else:
            self.state, self.t = "hurt", 0
            self.vx = kb
            if move and MOVES.get(move, {}).get("hop"):
                self.vy, self.on_ground = -2.0, False
        return dmg

    def telegraphing(self):
        return self.state in ("aim", "windup")

    def draw(self, surf, ox, oy):
        key = self.key()
        flip = self.face < 0
        img, (ax, ay) = self.art.entry(key, flip)
        if self.state == "dead" and self.dead_t > 36 and (self.dead_t // 3) % 2:
            return
        if self.flash and self.flash % 2:
            img = self.art.flash(key, flip)
        elif self.telegraphing() and (self.t // 3) % 2 == 0:
            img = self.art.flash(key, flip, (255, 236, 160))
        surf.blit(img, (round(self.x - ax - ox), round(self.y - ay - oy)))
        if self.state == "aim" and self.t < 18:
            self.sc.draw_alert(surf, self.x - ox, self.y - img.get_height() - 6 - oy)


class Doom:
    """Dr. Doom, master of Geldra: volleys of ki shots high and low, a charged
    beam, hops between the two floors (landing sends shockwaves along the
    floor) and calls maskers out of the courtyard doors."""

    kind = "boss"
    REACH = 26

    def __init__(self, sc, x, y):
        self.sc = sc
        self.art = SmallArt("drdoom", BOSS_SCALE)
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.on_ground = False
        self.face = -1
        self.hp = self.max_hp = BOSS_HP
        self.state = "asleep"
        self.t = 0
        self.pose, self.pose_t, self.span = "idle", 0, None
        self.flash = 0
        self.cd = 60
        self.hit_done = False
        self.dead_t = 0
        self.gone = False
        self.plan = []               # shot heights of the current volley (True = low)
        self.low = self.fired_low = False
        self.tell = 24
        self.hop_to = GROUND
        self.other_t = 0
        self.summons = [0.66, 0.33]
        self.uid = sc.next_uid()

    key = Enemy.key
    body_area = Enemy.body_area
    strike_area = Enemy.strike_area
    set_pose = Enemy.set_pose
    same_floor = Enemy.same_floor

    @property
    def alive(self):
        return self.state != "dead"

    @property
    def phase2(self):
        return self.hp < self.max_hp * 0.5

    def telegraphing(self):
        return self.state in ("aim", "charge", "windup")

    def update(self):
        sc, p = self.sc, self.sc.p
        self.t += 1
        self.pose_t += 1
        if self.flash:
            self.flash -= 1
        if self.state == "asleep":
            return
        if self.state == "dead":
            self.dead_t += 1
            self.set_pose("down" if self.dead_t > 16 else "launch")
            self.vx *= 0.9
            fall(sc.st, self, ARENA_X + 8, LW - 8)
            if self.dead_t % 6 == 0 and self.dead_t < 90:
                sc.sparks(self.x + sc.rng.uniform(-14, 14), self.y - sc.rng.uniform(4, 40), (140, 255, 140), 10)
                audio.play("boom", 0.5)
            return
        if self.state == "intro":
            self.set_pose("jump" if not self.on_ground else "intro")
            fall(sc.st, self, ARENA_X + 8, LW - 8)
            if self.on_ground and self.t > 90:
                self.state, self.t = "walk", 0
            return
        dx = p.x - self.x
        dist = abs(dx)
        if self.cd:
            self.cd -= 1
        st = self.state
        if self.summons and self.hp < self.max_hp * self.summons[0] and st == "walk":
            self.summons.pop(0)
            sc.summon(2 if not self.phase2 else 3)
            self.state, self.t = "taunt", 0
        st = self.state
        if st == "taunt":
            self.set_pose("taunt", 40)
            self.vx = 0.0
            if self.t >= 40:
                self.state, self.t = "walk", 0
        elif st == "walk":
            if self.on_ground:
                self.face = 1 if dx > 0 else -1
            if not self.same_floor() and p.state != "dead":
                self.other_t += 1
            else:
                self.other_t = 0
            if self.other_t > (70 if self.phase2 else 110) and self.on_ground:
                self.start_hop()
            elif self.same_floor() and dist < self.REACH + 8 and not self.cd:
                self.state, self.t = "windup", 0
                self.vx = 0.0
                sc.event("windup", self)
                audio.play("rt_tell", 0.6)
            elif not self.cd:
                if sc.rng.random() < 0.65:
                    self.state, self.t = "aim", 0
                    n = 5 if self.phase2 else 3
                    self.plan = [sc.rng.random() < 0.5 for _ in range(n)]
                    self.low = self.plan[0]
                    self.tell = 16 if self.phase2 else 24
                else:
                    self.state, self.t = "charge", 0
                    self.low = sc.rng.random() < 0.5
                    audio.play("rt_tell", 0.7)
                sc.event(self.state, self, "low" if self.low else "high")
                self.vx = 0.0
            else:
                want = 70 if dist > 70 else -1 if dist < 40 else 0
                d = (1 if dx > 0 else -1) * (1 if want > 0 else -1 if want < 0 else 0)
                if d and (self.y > UPPER + 1 or sc.st.covered(self.x + d * 12)):
                    self.vx = d * (0.9 if self.phase2 else 0.7)
                    self.set_pose("walk" if d == self.face else "walk_back")
                else:
                    self.vx = 0.0
                    self.set_pose("idle")
        elif st == "aim":
            # each shot: a readable stance (crouch = low, standing = high), then the shot
            self.set_pose("crouch" if self.low else "hado_prep", 10)
            if self.t >= self.tell:
                h = LOW if self.low else HIGH
                sc.shots.append(Shot(self.x + self.face * 14, self.y - h, self.face * (SHOT_V + 0.6), 0, "ki",
                                     DMG["shot"], False, self, tint="boss"))
                sc.event("fire", self, "low" if self.low else "high")
                audio.play("rt_shot", 0.6)
                self.fired_low = self.plan.pop(0)
                self.state, self.t = ("between", 0) if self.plan else ("recover", 0)
        elif st == "between":                       # the follow-through between volley shots
            self.set_pose("crouch_jab" if self.fired_low else "hado_fire", 6)
            if self.t >= 6:
                self.low = self.plan[0]
                self.state, self.t, self.tell = "aim", 0, 12
        elif st == "charge":
            n = 40 if self.phase2 else 54
            self.set_pose("crouch" if self.low else "hado_prep", n)
            if self.t % 6 == 0:
                sc.sparks(self.x + self.face * 14, self.y - (LOW if self.low else HIGH), (120, 255, 140), 3)
            if self.t >= n:
                h = LOW if self.low else HIGH
                sc.shots.append(Shot(self.x + self.face * 18, self.y - h, self.face * 4.6, 0, "beam", DMG["beam"],
                                     False, self))
                sc.event("beam", self, "low" if self.low else "high")
                audio.play("rt_beam")
                self.state, self.t = "recover", 0
        elif st == "windup":
            self.set_pose("punch_prep", 20 if self.phase2 else 26)
            if self.t >= (20 if self.phase2 else 26):
                self.state, self.t = "attack", 0
                self.hit_done = False
                self.vx = self.face * 2.0
                audio.play("whiff")
        elif st == "attack":
            self.set_pose("punch", 10)
            self.vx *= 0.85
            if not self.hit_done and touches(self.strike_area(), sc.hero_area()):
                if sc.hurt_player(DMG["boss_punch"], self):
                    self.hit_done = True
            if self.t >= 10:
                self.state, self.t = "recover", 0
        elif st == "hop":
            self.set_pose("jump_up" if self.vy < 0 else "fall")
            if self.on_ground and self.t > 4:
                self.vx = 0.0
                self.state, self.t = "recover", 0
                sc.shake = 8
                audio.play("rt_slam")
                for d in (-1, 1):
                    sc.shots.append(Shot(self.x + d * 14, self.y, d * 2.6, 0, "wave", DMG["wave"], False, self))
                sc.event("slam", self)
        elif st == "recover":
            self.set_pose("idle")
            self.vx *= 0.8
            if self.t >= (22 if self.phase2 else 34):
                self.state, self.t = "walk", 0
                self.cd = sc.rng.randrange(30, 60) if self.phase2 else sc.rng.randrange(50, 90)
        if self.state != "hop" or self.on_ground:
            fall(sc.st, self, ARENA_X + 8, LW - 8)
        else:
            self.vy = min(MAX_FALL, self.vy + GRAV)
            self.y += self.vy
            self.x = max(ARENA_X + 8, min(LW - 8, self.x + self.vx))
            if self.vy >= 0:
                target = UPPER if self.hop_to == UPPER else GROUND
                if self.y >= target:
                    self.y, self.vy, self.on_ground = float(target), 0.0, True

    def start_hop(self):
        """Fly to Akuma's floor (landing above or below him)."""
        sc, p = self.sc, self.sc.p
        self.other_t = 0
        if p.y < self.y - 30:
            self.hop_to = UPPER
            tx = max(sc.st.balconies[-1][0] + 16, min(sc.st.balconies[-1][1] - 16, p.x - self.face * 50))
            self.vy = -8.2
        else:
            self.hop_to = GROUND
            tx = max(ARENA_X + 30, min(LW - 30, p.x + (60 if p.x < (ARENA_X + LW) / 2 else -60)))
            self.vy = -3.0
        air = 2 * abs(self.vy) / GRAV
        self.vx = (tx - self.x) / max(20, air)
        self.on_ground = False
        self.state, self.t = "hop", 0
        sc.event("hop", self)
        audio.play("jump")

    def hurt(self, dmg, kb, move):
        self.hp -= dmg
        self.flash = 6
        if self.hp <= 0:
            self.hp = 0
            self.state, self.t = "dead", 0
            self.vx, self.vy = kb, -3.0
            self.on_ground = False
            self.sc.boss_died(self)
        return dmg

    def draw(self, surf, ox, oy):
        if self.state == "asleep":
            return
        Enemy.draw(self, surf, ox, oy)
        if self.state == "charge":
            r = 3 + (self.t // 4) % 3 + self.t // 14
            cx, cy = round(self.x + self.face * 16 - ox), round(self.y - (LOW if self.low else HIGH) - oy)
            pygame.draw.circle(surf, (40, 160, 70), (cx, cy), r + 1)
            pygame.draw.circle(surf, (190, 255, 200), (cx, cy), r)


# ---------------------------------------------------------------------------
# the scene
# ---------------------------------------------------------------------------
class ThunderScene:
    LEVEL_NAME = "GELDRA'S HIDEOUT"

    def __init__(self, game, seed=None, level=10, hp=None):
        self.game = game
        self.level = level
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed * 5 + 3)
        _build_sounds()
        self.st = Street(self.seed)
        self.art = _art()
        self.surf = _street_surface(self.st, random.Random(self.seed + 17))
        self.akuma = SmallArt("akuma", SCALE)
        self.menu = PauseMenu(game, CONTROLS)
        self.max_hp = game.akuma_max
        self.hp = self.max_hp if hp is None else min(hp, self.max_hp)
        self.hp_lag = self.hp
        self.lives = LIVES
        self.ki = KI_MAX
        self.rapid = 0
        self.score = 0
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
        self.shots = []
        self.snacks = []
        self.banner = None
        self.dead_t = 0
        self.god = False             # tests
        self.spawning = True         # tests turn the doors off
        self.p = Hero(60, GROUND)
        self.enemies = []
        self.boss = Doom(self, LW - 70, -40)
        self.boss_on = False
        self.boss_dealt = 0
        self.area = 1
        self.camx = 0.0
        self.cam_look = 40.0

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

    def popup(self, text, x, y, col=(255, 255, 255), n=50):
        self.popups.append([text, x, y, n, col])

    def sparks(self, x, y, col=(255, 220, 120), n=8):
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            s = self.rng.uniform(1, 3)
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s, 12, col, 1, 0.1])

    def dust(self, x, y, n=5):
        for _ in range(n):
            self.particles.append([x + self.rng.uniform(-6, 6), y - 1, self.rng.uniform(-0.8, 0.8),
                                   self.rng.uniform(-0.8, -0.1), 18, (140, 130, 140), 2, 0.02])

    def draw_alert(self, surf, x, y):
        x, y = round(x), round(y)
        surf.fill(OUTLINE, (x - 2, y - 9, 5, 12))
        surf.fill((255, 60, 40), (x - 1, y - 8, 3, 6))
        surf.fill((255, 60, 40), (x - 1, y, 3, 2))

    def bounds(self, b):
        if self.boss_on:
            return ARENA_X + 6, LW - 6
        return 6, LW - 6

    # ---- Akuma's body -------------------------------------------------------
    def _hero_pose(self):
        """(sprite key, rotation) for Akuma right now."""
        p = self.p
        a = self.akuma
        st = p.state
        if st == "attack":
            kind, n, pose = MOVES[p.move]["ph"][p.ph]
            return a.resolve(pose, p.ph_t, self.t, n), 0
        if st == "hurt":
            return a.resolve("hurt", p.t, self.t, HURT_T), 0
        if st == "dead":
            return a.resolve("launch" if self.dead_t < 20 else "down", self.dead_t, self.t, 40), 0
        if p.vault and not p.on_ground:
            # the walkway vault is a forward flip
            return a.resolve("crouch", 2), (-360 * min(1.0, p.vault / 30) * p.face) % 360 // 15 * 15
        if not p.on_ground:
            pose = "jump_up" if p.vy < -2.5 else "jump" if p.vy < 1.5 else "fall"
            return a.resolve(pose, p.air_t, self.t, 30), 0
        if p.ducking:
            return DUCK_KEY, 0
        if abs(p.vx) > 0.4:
            return a.resolve("walk", 0, int(p.walked * 0.6)), 0
        return a.resolve("idle", 0, self.t), 0

    def hero_area(self):
        p = self.p
        if p.state in ("door", "dead"):
            return None
        key, deg = self._hero_pose()
        flip = p.face < 0
        if deg:
            img = self.akuma.rotated(key, flip, deg)
            return image_area(img, p.x - img.get_width() / 2, p.y - 16 - img.get_height() / 2)
        img, (ax, ay) = self.akuma.entry(key, flip)
        return self.akuma.mask(key, flip), round(p.x - ax), round(p.y - ay)

    # ---- update ---------------------------------------------------------------
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
                self.banner = ["AREA 1", "THE WAREHOUSE DISTRICT", 110]
            return
        if self.phase in ("won", "lost"):
            self.end_t += 1
            skip = self.end_t > 50 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= 200 or skip:
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
        if self.rapid:
            self.rapid -= 1
        self._update_hero(inp)
        self._update_doors()
        for e in self.enemies:
            e.update()
        self.enemies = [e for e in self.enemies if not e.gone and (self.boss_on or e.x > self.camx - 140
                                                                     or not e.alive)]
        self.boss.update()
        self._update_shots()
        self._update_snacks()
        self._update_progress()
        self._camera()

    def _update_progress(self):
        p = self.p
        area = area_of(p.x)
        if area == 2 and self.area == 1:
            self.area = 2
            self.banner = ["AREA 2", "GELDRA BASE", 110]
        if not self.boss_on and p.x > ARENA_X + 40 and p.state not in ("dead", "door"):
            self.boss_on = True
            self.area = 3
            for e in self.enemies:
                if e.x < ARENA_X and e.alive:
                    e.gone = True
            self.enemies = [e for e in self.enemies if not e.gone]
            self.shots = [s for s in self.shots if s.x > ARENA_X]
            b = self.boss
            b.state, b.t = "intro", 0
            b.x, b.y, b.vy = LW - 70.0, -40.0, 0.0
            self.banner = ["DR. DOOM", "MASTER OF GELDRA", 120]
            self.event("boss", b)
            audio.play("doom_roar" if "doom_roar" in getattr(audio, "_sfx", {}) else "encounter")

    def _update_hero(self, inp):
        p = self.p
        st = self.st
        if p.inv:
            p.inv -= 1
        if p.combo_t:
            p.combo_t -= 1
        self.ki = min(KI_MAX, self.ki + KI_REGEN)
        p.t += 1
        if p.state == "dead":
            self._dead_update()
            return
        frozen = self.boss.state == "intro"
        left = inp.held("left") and not frozen
        right = inp.held("right") and not frozen
        down = inp.held("down") and not frozen
        dirx = (1 if right else 0) - (1 if left else 0)
        pressed = (lambda a: inp.pressed(a) and not frozen)
        if p.state == "door":
            p.vx = 0.0
            if p.t >= DOOR_T or (p.t > 14 and (dirx or pressed("shield"))):
                p.state, p.t = "move", 0
                p.door["opening"] = 14
                p.door = None
                p.inv = max(p.inv, 12)
                audio.play("rt_door", 0.5)
            return
        if pressed("up"):
            p.jbuf = JUMP_BUFFER
        elif p.jbuf:
            p.jbuf -= 1
        chord = None
        for a in ("punch", "kick", "special"):
            p.since[a] = min(99, p.since[a] + 1)
        for a in ("punch", "kick", "special"):
            if pressed(a):
                p.since[a] = 0
        if pressed("special"):
            if p.since["punch"] <= SPECIAL_WINDOW:
                chord = "shoryu"
            elif p.since["kick"] <= SPECIAL_WINDOW:
                chord = "tatsu"
            else:
                p.abuf = ["special", 8, down]
        for a in ("punch", "kick"):
            if pressed(a) and not chord:
                if p.since["special"] <= SPECIAL_WINDOW and not pressed("special"):
                    chord = "shoryu" if a == "punch" else "tatsu"
                elif not pressed("special"):
                    p.abuf = [a, 8, down]
        if chord:
            p.abuf = [chord, 8, down]
            # the fireball / punch / kick that started a frame or two ago turns into the special
            if p.state == "attack" and p.t <= SPECIAL_WINDOW + 1 and p.ph == 0 and p.move not in ("shoryu", "tatsu"):
                if p.move in ("hado", "ahado") and not self.rapid:
                    self.ki = min(KI_MAX, self.ki + HADO_COST)
                p.state, p.t = "move", 0
        if p.abuf:
            p.abuf[1] -= 1
            if p.abuf[1] <= 0:
                p.abuf = None
        can_act = p.state == "move" or (p.state == "attack" and MOVES[p.move]["ph"][p.ph][0] == "r")
        # duck into a door
        if pressed("shield") and p.state == "move" and p.on_ground:
            d = self.door_at(p.x, p.y)
            if d is not None:
                self._enter_door(d)
                return
        if p.abuf and can_act:
            self._start_attack(p, *p.abuf)
        p.ducking = p.state == "move" and p.on_ground and down
        # jump, vault up, or drop through the walkway
        if p.jbuf and p.on_ground and (p.state == "move" or (p.state == "attack" and not MOVES[p.move].get("air")
                                                           and MOVES[p.move]["ph"][p.ph][0] == "r")):
            p.state, p.jbuf, p.ducking = "move", 0, False
            p.on_ground = False
            if down and p.y == UPPER:
                p.y += 2
                p.vy = 0.5
                p.vault = 0
                self.event("drop", p)
            elif p.y == GROUND and st.covered(p.x, 4):
                p.vy = VAULT_V
                p.vault = 1
                p.vx *= 0.6
                self.event("vault", p)
                audio.play("jump", 0.6)
            else:
                p.vy = JUMP_V
                p.vault = 0
                audio.play("jump", 0.5)
        s = p.state
        if s == "move":
            target = 0 if p.ducking else dirx * RUN
            acc = ACC_GROUND if p.on_ground else ACC_AIR
            p.vx += max(-acc, min(acc, target - p.vx))
            if dirx and (p.on_ground or not p.vault):
                p.face = dirx
        elif s == "hurt":
            p.vx *= 0.9
            if p.t >= HURT_T:
                p.state, p.t = "move", 0
        elif s == "attack":
            self._attack_update(p)
        # physics
        if p.state == "attack" and MOVES[p.move].get("dive") and p.ph == 1:
            p.vy = min(p.vy, 6.0) - GRAV
        elif p.state == "attack" and p.move == "ahado" and p.ph < 2:
            p.vy = min(p.vy + GRAV * 0.3, 1.0) - GRAV
        elif p.state == "attack" and MOVES[p.move].get("spin") and p.ph == 1:
            p.vy = min(p.vy + GRAV * 0.25, 0.6) - GRAV
        was = p.on_ground
        ox = p.x
        lo, hi = self.bounds(p)
        lo = max(lo, self.camx + 6)
        fall(st, p, lo, hi)
        p.walked += abs(p.x - ox)
        if p.vault:
            p.vault += 1
        if p.on_ground:
            if not was and p.air_t > 6:
                audio.play("land", 0.5)
                self.dust(p.x, p.y, 4)
                if p.vault and p.y == UPPER:
                    self.event("vaulted", p)
            p.air_t = 0
            p.vault = 0
        else:
            p.air_t += 1
        if p.state == "attack" and MOVES[p.move].get("air") and p.on_ground:
            if MOVES[p.move].get("dive"):
                if p.ph == 1:
                    p.ph, p.ph_t = 2, 0
                    p.vx = 0
                    self.shake = 3
                    self.dust(p.x, p.y, 6)
            else:
                p.state, p.t = "move", 0

    def door_at(self, x, y):
        for d in self.st.doors:
            if abs(d["x"] - x) < 11 and abs(d["y"] - y) < 2 and d["opening"] == 0 and \
                    not (d["kind"] == "arena" and not self.boss_on):
                return d
        return None

    def _enter_door(self, d):
        p = self.p
        p.state, p.t, p.door = "door", 0, d
        p.x, p.vx, p.vy = float(d["x"]), 0.0, 0.0
        p.ducking = False
        p.abuf = None
        d["opening"] = 14
        audio.play("rt_door", 0.6)
        self.event("door", p, d["kind"])
        if d["used"]:
            return
        if d["kind"] == "ki":
            d["used"] = True
            self.ki = KI_MAX
            self.popup("KI RESTORED", p.x, p.y - 56, (220, 150, 255), 60)
            audio.play("rt_item")
        elif d["kind"] == "food":
            d["used"] = True
            name = random_snack(self.rng)
            heal = min(heal_amount(name, self.max_hp), self.max_hp - self.hp)
            self.hp = min(self.max_hp, self.hp + max(heal, 0))
            self.popup("%s +%d" % (name, max(heal, 0)), p.x, p.y - 56, (120, 255, 140), 60)
            self.event("snack", p, name, heal)
            audio.play("rt_item")
        elif d["kind"] == "rapid":
            d["used"] = True
            self.rapid = RAPID_T
            self.popup("RAPID FIRE!", p.x, p.y - 56, (255, 220, 90), 60)
            audio.play("rt_item")

    def _start_attack(self, p, btn, n, down):
        air = not p.on_ground
        if btn in ("shoryu", "tatsu"):
            name = btn
        elif btn == "punch":
            if air:
                name = "ajab"
            elif down:
                name = "cjab"
            else:
                name = COMBO.get(p.last) if (p.combo_t and p.last in COMBO) else "jab1"
        elif btn == "kick":
            name = ("dive" if down else "akick") if air else ("sweep" if down else "kick")
        else:
            if self.rapid and not air:
                name = "rhado"
            else:
                if not self.rapid:
                    if self.ki < HADO_COST:
                        self.popup("NO KI", p.x, p.y - 50, (180, 160, 220), 30)
                        p.abuf = None
                        return
                    self.ki -= HADO_COST
                name = "ahado" if air else "hado"
        p.abuf = None
        p.state, p.t = "attack", 0
        p.ducking = False
        p.move, p.ph, p.ph_t = name, 0, 0
        p.hit_set = set()
        p.last = name
        p.combo_t = 0
        p.vault = 0
        if name in ("jab1", "jab2", "jab3", "kick", "sweep", "hado", "rhado", "cjab"):
            p.vx *= 0.4
        if name == "dive":
            p.vx, p.vy = 0.0, -1.0
        if name in ("shoryu", "tatsu"):
            self.event("special", p, name)
            if name == "shoryu":
                p.vx *= 0.3

    def _attack_update(self, p):
        mv = MOVES[p.move]
        p.ph_t += 1
        if not mv.get("air") and p.on_ground:
            p.vx *= 0.75
        if p.ph_t >= mv["ph"][p.ph][1]:
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
            if mv.get("spin"):
                p.vx = p.face * 2.2
            if mv.get("rehit") and p.ph_t % mv["rehit"] == 0:
                p.hit_set = set()
            self._hero_strikes(p, mv)

    def _active_start(self, p, mv):
        if mv.get("lunge") and p.on_ground:
            p.vx = p.face * mv["lunge"]
        if mv.get("hop") and (p.on_ground or p.move == "shoryu"):
            p.vy = mv["hop"] * (1 if p.on_ground else 0.75)
            p.on_ground = False
        if mv.get("spin") and p.on_ground:
            p.vy = -2.0
            p.on_ground = False
        if mv.get("dive"):
            p.vy, p.vx = 6.0, p.face * 2.8
            audio.play("dive")
        elif mv.get("proj"):
            dmg = mv["dmg"]
            if p.move == "ahado":
                self.shots.append(Shot(p.x + p.face * 14, p.y - 16, p.face * DIAG, DIAG, "hado", dmg, True, p, "ahado"))
            else:
                self.shots.append(Shot(p.x + p.face * 18, p.y - 22, p.face * 3.8, 0, "hado", dmg, True, p, p.move))
            self.event("hado", p, p.move)
            audio.play("hadouken", 0.6 if p.move == "rhado" else 1.0)
        elif p.move == "shoryu":
            audio.play("shoryu")
        elif p.move == "tatsu":
            audio.play("rt_tatsu")
        else:
            audio.play("whiff", 0.5)

    def _strike_area(self, p):
        mv = MOVES[p.move]
        if mv.get("spin"):
            return rect_area((p.x - 26, p.y - 34, 52, 18))     # the spinning legs reach both sides
        key, deg = self._hero_pose()
        flip = p.face < 0
        if mv.get("body"):                                     # the shoryuken hits with his whole rising body
            img, (ax, ay) = self.akuma.entry(key, flip)
            return self.akuma.mask(key, flip), round(p.x - ax), round(p.y - ay)
        m = self.akuma.strike(key, flip)
        if m is None:
            return rect_area((p.x + (2 if p.face > 0 else -26), p.y - (16 if mv.get("low") else 30), 24, 16))
        img, (ax, ay) = self.akuma.entry(key, flip)
        return m, round(p.x - ax), round(p.y - ay)

    def _targets(self):
        out = [e for e in self.enemies if e.alive and abs(e.x - self.p.x) < 220]
        if self.boss_on and self.boss.alive and self.boss.state not in ("asleep", "intro"):
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
                self._hit_enemy(e, p.move, p.x)

    def _hit_enemy(self, e, move, src_x):
        mv = MOVES.get(move, {})
        d = 1 if e.x > src_x else -1
        dmg = mv.get("dmg", 10)
        kb = 0.0 if e is self.boss else d * mv.get("kb", 1.5)
        dealt = e.hurt(dmg, kb, move)
        if dealt:
            self.event("dealt", e, move, dealt)
            if e is self.boss:
                self.boss_dealt += dealt
            self.popup(str(dealt), e.x + self.rng.uniform(-4, 4), e.y - (66 if e is self.boss else 50),
                       (255, 240, 120) if mv.get("heavy") else (255, 255, 255), 36)
            self.sparks((e.x + self.p.x) / 2 if not mv.get("proj") else e.x, e.y - 22)
            self.hitstop = 5 if mv.get("heavy") else 2
            if mv.get("heavy"):
                self.shake = 3
            audio.play("heavy" if mv.get("heavy") else "hit", 0.8)
            if not mv.get("proj"):
                self.ki = min(KI_MAX, self.ki + KI_ON_HIT)
            if mv.get("dive") and self.p.state == "attack" and self.p.move == "dive":
                self.p.state, self.p.t = "move", 0
                self.p.vy = -5.0
                self.p.vx = -self.p.face * 0.6
        return dealt

    def hurt_player(self, dmg, src):
        """An enemy attack connects. False when Akuma is hidden, flashing or in
        the invincible start of a shoryuken."""
        p = self.p
        if p.state in ("dead", "door") or p.inv or self.god:
            return False
        if p.state == "attack":
            inv = MOVES[p.move].get("inv")
            if inv and p.ph <= 1 and (p.ph == 0 or p.ph_t < inv[1]):
                return False
        self.hp -= dmg
        self.event("hurt", src, dmg)
        self.popup(str(dmg), p.x, p.y - 50, (255, 90, 80), 36)
        audio.play("heavy" if dmg >= 20 else "hit")
        self.shake = 4
        self.hitstop = 4
        p.inv = INVULN
        if self.hp <= 0:
            self.hp = 0
            self._die()
            return True
        p.state, p.t = "hurt", 0
        p.vx = (2.0 if p.x > src.x else -2.0)
        p.ducking = False
        p.vault = 0
        return True

    def _die(self):
        p = self.p
        p.state, p.t = "dead", 0
        p.vx, p.vy = -p.face * 1.5, -3.5
        p.on_ground = False
        self.dead_t = 0
        self.lives -= 1
        self.event("die", p, self.lives)
        audio.play("ko")

    def _dead_update(self):
        p = self.p
        self.dead_t += 1
        p.vx *= 0.95
        fall(self.st, p, *self.bounds(p))
        if self.dead_t >= 90:
            if self.lives <= 0:
                self.phase, self.end_t = "lost", 0
                return
            # back up where he fell, with a full bar and a moment of grace
            self.hp = self.max_hp
            self.hp_lag = self.hp
            p.state, p.t = "move", 0
            p.inv = RESPAWN_INV
            p.vx = p.vy = 0.0
            self.shots = [s for s in self.shots if s.friendly]
            for e in self.enemies:
                if e.alive and abs(e.x - p.x) < 50 and abs(e.y - p.y) < 24:
                    e.x += 50 if e.x >= p.x else -50
            self.event("respawn", p)

    # ---- doors ------------------------------------------------------------------
    def _update_doors(self):
        p = self.p
        active = sum(1 for e in self.enemies if e.alive)
        for d in self.st.doors:
            if d["opening"]:
                d["opening"] -= 1
                d["open"] = min(1.0, d["open"] + 0.15)
            else:
                d["open"] = max(0.0, d["open"] - 0.08)
            if p.state == "door" and p.door is d:
                d["open"] = 1.0 if p.t < 10 else max(0.0, d["open"] - 0.1)
            if d["cd"]:
                d["cd"] -= 1
            if not self.spawning or d["kind"] != "spawn" or d["stock"] <= 0 or self.boss_on:
                continue
            on_screen = self.camx + 8 < d["x"] < self.camx + W - 8
            if on_screen and not d["cd"] and active < MAX_ACTIVE and abs(d["x"] - p.x) > 46 \
                    and not (p.door is d):
                self.spawn_from(d)
                active += 1

    def spawn_from(self, d, kind=None):
        area = area_of(d["x"])
        if kind is None:
            kinds = SPAWN_WEIGHTS[min(area, 2)]
            kind = self.rng.choices([k for k, _ in kinds], weights=[w for _, w in kinds])[0]
        e = Enemy(self, d["x"], d["y"], kind, door=d)
        self.enemies.append(e)
        d["stock"] = max(0, d["stock"] - 1)
        d["cd"] = self.rng.randrange(150, 260)
        d["opening"] = 22
        self.event("spawn", e, d["x"])
        audio.play("rt_door", 0.5)
        return e

    def summon(self, n):
        doors = [d for d in self.st.doors if d["kind"] == "arena"]
        self.rng.shuffle(doors)
        for d in doors[:n]:
            if abs(d["x"] - self.p.x) > 30:
                self.spawn_from(d, self.rng.choice(("masker", "brawler", "leaper")))
        self.event("summon", self.boss, n)

    def enemy_died(self, e):
        self.score += e.cfg["pts"]
        self.event("died", e)
        self.popup(str(e.cfg["pts"]), e.x, e.y - 60, (255, 220, 120), 40)
        audio.play("ko", 0.5)

    def boss_died(self, b):
        self.score += 10000
        self.event("boss_died", b)
        self.hitstop = 20
        self.shake = 20
        audio.play("ko")
        self.enemies = [e for e in self.enemies if not e.alive]
        for e in self.enemies:
            e.gone = True
        self.shots = []
        self.phase, self.end_t = "won", 0

    # ---- shots, snacks ----------------------------------------------------------
    def _update_shots(self):
        hero = None
        for s in self.shots:
            s.t += 1
            s.x += s.vx
            s.y += s.vy
            if s.x < self.camx - 30 or s.x > self.camx + W + 30 or s.y > GROUND + 4 or s.t > 400:
                s.dead = True
                continue
            if s.friendly:
                if s.move == "ahado" and s.vy and s.y >= UPPER and s.y - s.vy < UPPER and self.st.covered(s.x):
                    s.dead = True           # the diagonal fireball bursts on the walkway
                    self.sparks(s.x, UPPER, (200, 160, 255), 5)
                    continue
                area = s.area()
                for e in self._targets():
                    if e not in s.hit and touches(area, e.body_area()):
                        s.hit.add(e)
                        self._hit_enemy(e, s.move, s.x - s.vx * 4)
                        s.dead = True
                        break
                if s.dead:
                    continue
                # a hadouken eats the maskers' little ki shots
                for o in self.shots:
                    if not o.friendly and not o.dead and o.kind == "ki" and touches(area, o.area()):
                        o.dead = True
                        self.sparks(o.x, o.y, (200, 200, 255), 5)
                        self.event("cancel", s.owner)
            else:
                if hero is None:
                    hero = self.hero_area() or False
                if hero and touches(s.area(), hero):
                    if self.hurt_player(s.dmg, s):
                        s.dead = True
                        hero = None
        self.shots = [s for s in self.shots if not s.dead]

    def _update_snacks(self):
        p = self.p
        for sn in self.snacks:
            if not sn["taken"] and abs(sn["x"] - p.x) < 10 and abs(sn["y"] - p.y) < 8 and p.state != "dead":
                sn["taken"] = True
                heal = min(heal_amount(sn["name"], self.max_hp), self.max_hp - self.hp)
                self.hp += heal
                self.popup("%s +%d" % (sn["name"], heal), sn["x"], sn["y"] - 24, (120, 255, 140), 60)
                audio.play("rt_item")
        self.snacks = [sn for sn in self.snacks if not sn["taken"]]

    # ---- camera -----------------------------------------------------------------
    def _camera(self, snap=False):
        p = self.p
        if self.boss_on:
            tx = ARENA_X
        else:
            self.cam_look += (40 * p.face - self.cam_look) * 0.04
            tx = max(0, min(LW - W, p.x + self.cam_look - W / 2))
        if snap:
            self.camx = tx
        else:
            self.camx += (tx - self.camx) * 0.12
            if abs(tx - self.camx) < 0.3:
                self.camx = tx

    # ---- drawing ----------------------------------------------------------------
    def draw(self, surf):
        sh = (0, 0)
        if self.shake:
            sh = (self.rng.choice((-2, -1, 1, 2)), self.rng.choice((-1, 0, 1)))
        ox, oy = round(self.camx) - sh[0], -sh[1]
        surf.blit(self.art["sky"], (0, 0))
        surf.blit(self.surf, (0, 0), pygame.Rect(ox, oy, W, H))
        for d in self.st.doors:
            if -30 < d["x"] - ox < W + 30:
                self._draw_door(surf, d, ox, oy)
        if self.boss_on:
            # the courtyard's shutter, down behind Akuma
            x = ARENA_X - ox
            surf.fill(OUTLINE, (x - 6, UPPER - 58, 8, GROUND - UPPER + 58))
            for y in range(UPPER - 56, GROUND, 6):
                surf.fill((120, 110, 120), (x - 5, y, 6, 4))
        for sn in self.snacks:
            img = snack_image(sn["name"])
            surf.blit(img, (round(sn["x"] - 6 - ox), round(sn["y"] - 13 - oy)))
        for e in self.enemies:
            if -60 < e.x - ox < W + 60:
                e.draw(surf, ox, oy)
        self.boss.draw(surf, ox, oy)
        self._draw_hero(surf, ox, oy)
        for s in self.shots:
            img = s.image()
            if s.kind == "wave":
                surf.blit(img, (round(s.x - img.get_width() / 2 - ox), round(s.y - img.get_height() - oy)))
            else:
                if s.kind == "beam":
                    tail = pygame.Rect(0, 0, 40, 4)
                    tail.midright = (round(s.x - ox) - (14 if s.vx > 0 else -54), round(s.y - oy))
                    surf.fill((60, 200, 90), tail)
                surf.blit(img, (round(s.x - img.get_width() / 2 - ox), round(s.y - img.get_height() / 2 - oy)))
        for pt in self.particles:
            surf.fill(pt[5], (round(pt[0] - ox), round(pt[1] - oy), pt[6], pt[6]))
        for text, x, y, n, col in self.popups:
            draw_text(surf, text, x - ox, y - oy, col, align="center")
        self._hud(surf)
        if self.menu.open:
            self.menu.draw(surf)

    def _draw_door(self, surf, d, ox, oy):
        c = AREA_COLS[area_of(d["x"])]
        x, y = round(d["x"] - DOOR_W / 2 - ox), round(d["y"] - DOOR_H - oy)
        surf.fill(OUTLINE, (x - 3, y - 3, DOOR_W + 6, DOOR_H + 3))
        surf.fill(c["trim"], (x - 2, y - 2, DOOR_W + 4, DOOR_H + 2))
        surf.fill((6, 4, 10), (x, y, DOOR_W, DOOR_H))
        # the shutter slides up into the frame
        h = round(DOOR_H * (1 - d["open"]))
        if h > 0:
            surf.fill(c["door"], (x, y, DOOR_W, h))
            for k in range(3, h, 5):
                surf.fill(c["door2"], (x, y + k, DOOR_W, 1))
            surf.fill(OUTLINE, (x, y + h - 1, DOOR_W, 1))
        if d["kind"] in ("ki", "food", "rapid"):
            label = {"ki": "KI", "food": "FOOD", "rapid": "RAPID"}[d["kind"]]
            col = (110, 100, 110) if d["used"] else {"ki": (230, 150, 255), "food": (130, 255, 140),
                                                     "rapid": (255, 220, 90)}[d["kind"]]
            w = text_width(label) + 6
            surf.fill(OUTLINE, (x + DOOR_W // 2 - w // 2, y - 13, w, 10))
            draw_text(surf, label, x + DOOR_W // 2, y - 12, col, align="center")
        p = self.p
        if p.state == "move" and p.on_ground and abs(d["x"] - p.x) < 11 and abs(d["y"] - p.y) < 2 \
                and (self.t // 20) % 2 and self.phase == "play":
            draw_text(surf, "I", x + DOOR_W // 2, y + 6, (255, 255, 255), align="center")

    def _draw_hero(self, surf, ox, oy):
        p = self.p
        if p.state == "door":
            return
        if p.inv and p.state != "dead" and (p.inv // 3) % 2:
            return
        key, deg = self._hero_pose()
        flip = p.face < 0
        x, y = round(p.x - ox), round(p.y - oy)
        if p.on_ground:
            pygame.draw.ellipse(surf, (6, 4, 10), (x - 8, y - 2, 16, 4))
        if deg:
            img = self.akuma.rotated(key, flip, deg)
            surf.blit(img, (x - img.get_width() // 2, y - 16 - img.get_height() // 2))
            return
        img, (ax, ay) = self.akuma.entry(key, flip)
        surf.blit(img, (x - ax, y - ay))

    def _hud(self, surf):
        bw = 90
        mh = self.max_hp
        surf.fill(OUTLINE, (3, 3, bw + 4, 9))
        surf.fill((70, 14, 20), (5, 5, bw, 5))
        surf.fill((230, 60, 40), (5, 5, round(bw * self.hp_lag / mh), 5))
        surf.fill((90, 220, 90) if self.hp > mh * 0.3 else (240, 200, 60), (5, 5, round(bw * max(0, self.hp) / mh), 5))
        # ki is Akuma's ammunition
        surf.fill(OUTLINE, (3, 12, 52, 5))
        surf.fill((40, 20, 60), (4, 13, 50, 3))
        if self.rapid:
            col = (255, 220, 90) if (self.t // 6) % 2 else (255, 160, 60)
            surf.fill(col, (4, 13, round(50 * self.rapid / RAPID_T), 3))
            draw_text(surf, "RAPID", 58, 11, col)
        else:
            col = (230, 120, 255) if self.ki >= HADO_COST else (130, 80, 160)
            surf.fill(col, (4, 13, round(50 * self.ki / KI_MAX), 3))
            for k in range(1, KI_MAX // HADO_COST):
                surf.fill(OUTLINE, (4 + round(50 * k * HADO_COST / KI_MAX), 13, 1, 3))
            draw_text(surf, "KI %d" % int(self.ki // HADO_COST), 58, 11, (200, 170, 230))
        for i in range(LIVES):
            c = (255, 70, 50) if i < self.lives else (60, 40, 50)
            pygame.draw.circle(surf, OUTLINE, (bw + 14 + i * 7, 7), 3)
            pygame.draw.circle(surf, c, (bw + 14 + i * 7, 7), 2)
        draw_text(surf, "%07d" % self.score, W - 4, 4, (255, 255, 255), align="right")
        # how far along the street
        x0, w = W - 74, 70
        surf.fill(OUTLINE, (x0, 14, w, 3))
        surf.fill((90, 80, 110), (x0 + 1, 15, w - 2, 1))
        surf.fill((255, 80, 60), (x0 + round((w - 3) * min(1, self.p.x / LW)), 13, 2, 5))
        b = self.boss
        if self.boss_on and b.state != "dead":
            bw2 = 200
            x0 = (W - bw2) // 2
            draw_text(surf, "DR. DOOM", W // 2, H - 21, (150, 255, 160), align="center")
            surf.fill(OUTLINE, (x0 - 2, H - 11, bw2 + 4, 7))
            surf.fill((10, 40, 14), (x0, H - 9, bw2, 3))
            surf.fill((80, 220, 90), (x0, H - 9, round(bw2 * b.hp / b.max_hp), 3))
        if self.phase == "intro":
            self._title_card(surf)
        if self.banner and self.phase == "play":
            text, sub, n = self.banner
            a = min(1, n / 20)
            band = pygame.Surface((W, 34), pygame.SRCALPHA)
            band.fill((6, 4, 12, int(170 * a)))
            surf.blit(band, (0, 40))
            draw_text(surf, text, W // 2, 44, (255, 230, 150), scale=2, align="center")
            draw_text(surf, sub, W // 2, 62, (200, 190, 220), align="center")
        if self.phase == "won" and self.end_t > 10:
            band = pygame.Surface((W, 46), pygame.SRCALPHA)
            band.fill((6, 4, 12, 200))
            surf.blit(band, (0, 40))
            draw_text(surf, "MISSION COMPLETE", W // 2, 46, (255, 220, 60), scale=2, align="center")
            draw_text(surf, "GELDRA HAS FALLEN", W // 2, 68, (255, 255, 255), align="center")
        if self.phase == "lost" and self.end_t > 10:
            band = pygame.Surface((W, 40), pygame.SRCALPHA)
            band.fill((20, 0, 4, 210))
            surf.blit(band, (0, 50))
            draw_text(surf, "GAME OVER", W // 2, 56, (220, 30, 30), scale=3, align="center")

    def _title_card(self, surf):
        n = self.end_t
        a = min(1, n / 20, max(0, (INTRO - n) / 25))
        band = pygame.Surface((W, 70), pygame.SRCALPHA)
        band.fill((4, 2, 10, int(200 * a)))
        surf.blit(band, (0, 40))
        if a > 0.3:
            name = self.LEVEL_NAME
            draw_text(surf, "LEVEL %d" % self.level, W // 2, 46, (200, 180, 140), align="center")
            draw_text(surf, name, W // 2, 62, (255, 230, 170), scale=2, align="center")
            w = min(text_width(name, 2) + 20, int((n / 40) * W))
            surf.fill((200, 160, 90), (W // 2 - w // 2, 82, w, 1))
            draw_text(surf, "NO GUNS. ONLY HADOUKENS.", W // 2, 90, (190, 180, 210), align="center")
