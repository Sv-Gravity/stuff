"""Level 6: a Smash Bros. style free-for-all at a little pixel Hyrule Castle.

Akuma and three challengers from Toshi's sprite pack fight on a castle roof:
a big main floor, a raised tower, and pass-through ledges. Hits add damage %
(0-200) instead of taking health; the higher it is, the further a hit sends
you and the likelier one strong blow launches you clean off the screen. Fly
past the edge of the screen (any side) and you lose a stock. Three stocks
each; knock all three challengers out to clear the level.

Hit detection is pixel accurate: a fighter can be hit wherever the frame it
is showing has pixels, and an attack strikes with the pixels of its frame
that stick out from the fighter's resting body (the fist, the leg, the
flame), so what you see is what hits.
"""

import math
import random

import pygame

from . import audio
from . import fight as F
from .akuma_sprites import CharArt, portrait
from .art import shade, mix, OUTLINE, make_fireball, make_spark
from .config import W, H, AKUMA_MAX_HP
from .font import draw_text, text_width
from .pause import PauseMenu

LEVEL_NAME = "HYRULE CASTLE"

# --------------------------------------------------------------------------
# tuning (all per frame at 60 fps; distances in canvas pixels)
# --------------------------------------------------------------------------
SCALE = 0.58            # fighters are drawn at this fraction of their sheet size
GRAV = 0.30
FALL_MAX = 4.2
FASTFALL = 5.6
AIR_ACC = 0.22
FRICTION = 0.72
KB_DECAY = 0.17         # launch speed lost per frame (linear, like Smash)
TUMBLE_KB = 4.5         # launches faster than this tumble
HITSTUN_K = 3.4         # hitstun frames per unit of knockback
CRIT = 0.35             # chance of a x1.45 "smash" launch at 200% (scales with %^2)
CRIT_K = 1.45
STOCKS = 3
MAX_PCT = 200
SHIELD_MAX = 60.0
SHIELD_DRAIN = 0.14     # per frame held
SHIELD_REGEN = 0.10
SHIELD_DMG_K = 1.25     # shield health lost per % of a blocked hit
SHIELD_BREAK = 150      # frames dizzy after the shield breaks
ROLL_LEN = 22
RESPAWN_WAIT = 70
RESPAWN_HOLD = 150
RESPAWN_INVULN = 100
INTRO = 190
GAME_LEN = 200
CPU_FOCUS = 0.6         # chance a CPU picks Akuma when it chooses a target
CPU_ON_AKUMA = 0.85     # CPU hits on Akuma do this much of their damage (3 on 1 is rough)
BODY_W, BODY_H = 6, 30  # terrain collision box (half width, height)

BLAST_L, BLAST_R, BLAST_T, BLAST_B = -40, W + 40, -70, H + 50

# --------------------------------------------------------------------------
# the stage
# --------------------------------------------------------------------------
FLOOR_Y = 130
STAGE_L, STAGE_R = 52, 268
TOWER = pygame.Rect(200, 98, 42, 33)
SOLIDS = [pygame.Rect(STAGE_L, FLOOR_Y, STAGE_R - STAGE_L, 200), TOWER]
SOFTS = [(70, 118, 100), (124, 172, 74), (198, 244, 66)]      # x0, x1, y: drop-through
LEDGES = [(STAGE_L, FLOOR_Y, -1), (STAGE_R, FLOOR_Y, 1),
          (TOWER.left, TOWER.top, -1), (TOWER.right, TOWER.top, 1)]
SPAWNS = [(90, FLOOR_Y), (146, 74), (184, FLOOR_Y), (222, TOWER.top)]
HALO_Y = 40

SLOT_COLORS = [(232, 52, 44), (64, 110, 240), (240, 200, 40), (56, 190, 80)]
CPU_POOL = ["ryu", "ken", "sakura", "chunli", "zangief", "morrigan", "felicia", "hsienko"]
NAMES = {"akuma": "AKUMA", "ryu": "RYU", "ken": "KEN", "sakura": "SAKURA", "chunli": "CHUN-LI",
         "zangief": "ZANGIEF", "morrigan": "MORRIGAN", "felicia": "FELICIA", "hsienko": "HSIEN-KO"}

CONTROLS = [
    "LEFT / RIGHT: MOVE AND FACE THAT WAY",
    "UP: JUMP, AGAIN IN THE AIR: DOUBLE JUMP",
    "DOWN: CROUCH / DROP THROUGH A LEDGE",
    "J: JAB   K: KICK   DOWN+K: SWEEP",
    "AIR: J / K ATTACKS, DOWN+K: DIVE KICK",
    "L: HADOUKEN   UP+L: SHORYUKEN (RECOVER)",
    "DOWN+L: HURRICANE KICK",
    "HOLD I: SHIELD  I+LEFT/RIGHT: ROLL  I+J: GRAB",
    "HIGHER DAMAGE % = FLY FARTHER",
    "KNOCK FOES OFF SCREEN. 3 STOCKS EACH",
]


# --------------------------------------------------------------------------
# movesets. Phases are (kind, frames, pose): s=startup, a=active, r=recovery.
# Positions (x, y, box) are in sheet pixels from the feet, facing right;
# box is only a fallback when a frame has no limb sticking out.
# --------------------------------------------------------------------------
KINDS = {"s": "startup", "a": "active", "r": "recovery"}


def M(phases, dmg=0, kb=0.0, kg=0.0, ang=40, **kw):
    mv = dict(phases=[(KINDS[k], n, p) for k, n, p in phases], dmg=dmg, kb=kb, kg=kg, ang=ang)
    mv.update(kw)
    mv.setdefault("ev", {})
    if "throw" in mv:
        th = mv["throw"]
        th["phases"] = [(KINDS[k], n, p) for k, n, p in th["phases"]]
        th.setdefault("ev", {})
    return mv


def normals(p=1.0, k=1.0):
    return dict(
        jab=M([("s", 3, "punch_prep"), ("a", 4, "punch"), ("r", 8, "punch_rec")],
              round(4 * p), 1.8 * k, 1.6 * k, 35, box=(10, -48, 24, 14)),
        crjab=M([("s", 3, "cr_punch_prep"), ("a", 3, "crouch_jab"), ("r", 7, "cr_punch_rec")],
                round(3 * p), 1.6 * k, 1.4 * k, 55, base="crouch", box=(8, -32, 22, 14)),
        kick=M([("s", 9, "kick_prep"), ("a", 5, "kick"), ("r", 14, "kick_rec")],
               round(10 * p), 2.8 * k, 6.0 * k, 38, box=(12, -46, 30, 18)),
        sweep=M([("s", 6, "sweep_prep"), ("a", 6, "sweep"), ("r", 14, "sweep_rec")],
                round(8 * p), 2.4 * k, 4.2 * k, 25, base="crouch", box=(10, -16, 32, 16)),
        nair=M([("s", 3, "jpunch_prep"), ("a", 8, "jump_jab"), ("r", 8, "jump")],
               round(6 * p), 2.0 * k, 3.0 * k, 40, base="jump", air=True, box=(8, -44, 28, 26)),
        fair=M([("s", 4, "jkick_prep"), ("a", 8, "jump_kick"), ("r", 10, "jump")],
               round(8 * p), 2.4 * k, 4.4 * k, 40, base="jump", air=True, box=(6, -36, 32, 24)),
        grab=M([("s", 4, "grab"), ("a", 4, "grab"), ("r", 18, "grab_miss")], grab=True, ground=True,
               box=(8, -54, 22, 34),
               throw=dict(phases=[("r", 26, "toss")], release=14, dmg=round(9 * p), kb=3.0, kg=4.6, ang=42)),
    )


def _hado(speed, dmg, kb, kg, x=30, y=-38, life=100, prep=4, **proj):
    return M([("s", prep, "hado_prep"), ("s", 6, "hado_fire"), ("r", 18, "hado_fire")],
             ev={prep: dict(sound="hadouken"),
                 prep + 5: dict(proj=dict(speed=speed, dmg=dmg, kb=kb, kg=kg, ang=proj.pop("ang", 30),
                                          x=x, y=y, life=life, **proj))})


def _sho(dmg, kb, kg, vy, vx=1.2, ang=80, rise=8, **kw):
    return M([("s", 3, "sho_crouch"), ("a", rise, "sho_rise"), ("a", 4, "sho_top"), ("r", 6, "sho_fall")],
             dmg, kb, kg, ang, upb=True, zone="all", invuln=(0, 6), box=(0, -84, 26, 70),
             ev={3: dict(vy=vy, vxf=vx, sound="shoryu")}, **kw)


def _tatsu(dmg=4, hits=3, rehit=8, vx=1.9):
    return M([("s", 5, "tatsu_start"), ("a", 30, "tatsu"), ("r", 8, "tatsu_end")],
             dmg, 2.0, 2.4, 45, zone="all", rehit=rehit, hits=hits, nograv=(9, 35), recover=True,
             box=(-34, -48, 68, 20),
             ev={4: dict(vy=-2.6, vxf=vx, sound="sweep"), 9: dict(vy=0.0),
                 15: dict(sound="whiff"), 23: dict(sound="whiff"), 31: dict(sound="whiff")})


def _akuma():
    m = normals()
    m.update(
        neutral=_hado(3.2, 7, 1.8, 2.6),
        airneutral=M([("s", 6, "air_hado_prep"), ("s", 6, "air_hado"), ("r", 10, "fall")],
                     air=True, nograv=(0, 14),
                     ev={0: dict(vy=-0.8), 5: dict(sound="hadouken"),
                         6: dict(proj=dict(speed=2.6, vy=1.6, air=True, dmg=7, kb=1.8, kg=2.6, ang=30,
                                           x=24, y=-34, life=90))}),
        up=_sho(12, 3.0, 5.6, -7.2),
        down=_tatsu(),
        dair=M([("a", 40, "dive")], 7, 2.0, 3.4, -65, air=True, hold=True, land_lag=10, nograv=(0, 999),
               base="jump", box=(8, -24, 28, 24), ev={0: dict(vy=4.6, vxf=2.8, sound="dive")}),
    )
    return m


def _ryu():
    m = normals()
    m.update(neutral=_hado(2.8, 8, 2.0, 2.8), up=_sho(12, 3.0, 5.6, -7.2), down=_tatsu())
    return m


def _ken():
    m = normals()
    m.update(neutral=_hado(3.4, 6, 1.6, 2.4), up=_sho(14, 3.2, 6.0, -7.6, ang=76, fire=True),
             down=_tatsu(dmg=3, hits=4, rehit=6, vx=2.3))
    return m


def _chunli():
    m = normals(p=0.9, k=0.95)
    m.update(
        neutral=_hado(2.4, 6, 1.6, 2.4, x=30, y=-36, life=80, ang=35),
        up=M([("s", 4, "lariat_a"), ("a", 30, "lariat_b"), ("r", 6, "fall")], 3, 2.0, 2.6, 65,
             upb=True, zone="all", rehit=7, hits=4, box=(-26, -60, 52, 32),
             ev={3: dict(vy=-5.6, vxf=1.4, sound="sweep")}),
        down=M([("s", 4, "kick_prep"), ("a", 24, "kick"), ("r", 10, "kick_rec")], 2, 1.4, 1.3, 35,
               ground=True, cycle=3, rehit=4, hits=6, box=(12, -50, 30, 26),
               ev={4: dict(sound="whiff"), 12: dict(sound="whiff"), 20: dict(sound="whiff")}),
    )
    return m


def _zangief():
    m = normals(p=1.25, k=1.1)
    m.update(
        neutral=M([("s", 5, "grab"), ("a", 5, "grab"), ("r", 24, "grab_miss")], grab=True, ground=True,
                  box=(8, -60, 24, 44),
                  throw=dict(phases=[("r", 44, "toss")], release=36, dmg=16, kb=3.4, kg=6.2, ang=70)),
        up=M([("s", 3, "lariat_a"), ("a", 30, "lariat_b"), ("r", 8, "lariat_a")], 4, 2.2, 3.0, 55,
             upb=True, zone="all", rehit=8, hits=4, nograv=(12, 33), box=(-40, -62, 80, 22),
             ev={3: dict(vy=-4.6, sound="sweep"), 12: dict(vy=-0.5), 20: dict(sound="whiff")}),
        down=M([("s", 8, "hammer_up"), ("a", 6, "hammer_down"), ("r", 16, "hammer_down")], 13, 3.0, 5.2, 35,
               ground=True, box=(10, -56, 32, 44)),
    )
    return m


def _sakura():
    m = normals(p=0.9, k=0.95)
    m.update(
        neutral=_hado(2.8, 8, 2.2, 3.2, x=26, y=-36, life=26, ang=35),
        up=M([("s", 3, "sho_crouch"), ("a", 10, "sho_rise"), ("a", 4, "sho_top"), ("r", 6, "sho_fall")],
             4, 2.4, 3.6, 75, upb=True, zone="all", rehit=5, hits=3, invuln=(0, 4), box=(0, -76, 26, 60),
             ev={3: dict(vy=-6.8, vxf=1.6, sound="shoryu")}),
        down=M([("s", 3, "prejump"), ("a", 24, "lariat_a"), ("r", 8, "land")], 4, 2.0, 2.8, 40,
               rehit=7, hits=3, nograv=(6, 27), box=(8, -50, 30, 30),
               ev={2: dict(vy=-2.0, vxf=2.0, sound="sweep"), 6: dict(vy=0.0)}),
    )
    return m


def _morrigan():
    m = normals(p=0.95)
    m.update(
        neutral=_hado(3.0, 7, 1.8, 2.6, x=32, y=-40),
        up=M([("s", 3, "sho_crouch"), ("a", 10, "sho_rise"), ("a", 8, "sho_top"), ("r", 4, "sho_fall")],
             4, 2.6, 4.0, 80, upb=True, zone="all", rehit=5, hits=3, box=(0, -84, 28, 70),
             ev={3: dict(vy=-7.0, vxf=1.3, sound="shoryu")}),
        down=M([("s", 4, "lariat_a"), ("a", 22, "lariat_b"), ("r", 8, "idle")], 4, 2.2, 3.6, 40,
               zone="all", rehit=6, hits=3, nograv=(4, 26), box=(-44, -36, 88, 16),
               ev={3: dict(vy=0.0, sound="sweep")}),
    )
    return m


def _felicia():
    m = normals(p=0.9)
    m.update(
        neutral=M([("s", 4, "lariat_a"), ("a", 26, "lariat_b"), ("r", 10, "land")], 4, 2.0, 3.0, 40,
                  zone="body", rehit=7, hits=3, box=(-20, -40, 44, 40),
                  ev={3: dict(vxf=3.0, sound="sweep"), 30: dict(vxf=0.0)}),
        up=M([("s", 3, "sho_crouch"), ("a", 10, "sho_rise"), ("a", 6, "sho_top"), ("r", 4, "fall")],
             9, 2.8, 5.0, 75, upb=True, zone="all", box=(0, -80, 26, 64),
             ev={3: dict(vy=-7.0, vxf=1.8, sound="shoryu")}),
        down=M([("s", 5, "hammer_up"), ("a", 5, "hammer_down"), ("r", 14, "hammer_down")], 9, 2.6, 4.6, 55,
               ground=True, box=(8, -46, 30, 40)),
    )
    return m


def _hsienko():
    m = normals()
    m.update(
        neutral=M([("s", 5, "hado_prep"), ("s", 5, "hado_fire"), ("r", 18, "hado_fire")],
                  ev={5: dict(sound="fireball"),
                      9: dict(proj=dict(speed=2.4, vy=-2.6, grav=0.13, dmg=8, kb=2.0, kg=3.0, ang=45,
                                        x=20, y=-50, life=120))}),
        up=M([("s", 3, "sho_crouch"), ("a", 9, "sho_rise"), ("a", 5, "sho_top"), ("r", 5, "sho_fall")],
             10, 2.8, 5.4, 78, upb=True, zone="all", box=(0, -84, 30, 70),
             ev={3: dict(vy=-6.8, vxf=1.0, sound="shoryu")}),
        down=M([("s", 6, "hammer_up"), ("a", 6, "hammer_down"), ("r", 14, "hammer_down")], 10, 2.8, 5.2, 32,
               ground=True, box=(10, -50, 40, 30)),
    )
    return m


# name, weight, walk, air speed, jump, double jump, gravity k, moves, AI personality
CHARS = {
    "akuma": dict(weight=1.0, walk=1.8, air=1.9, jump=-5.6, djump=-5.2, grav=1.0, moves=_akuma(),
                  ai=dict(aggr=0.7, block=0.4, react=10)),
    "ryu": dict(weight=1.0, walk=1.7, air=1.8, jump=-5.6, djump=-5.2, grav=1.0, moves=_ryu(),
                ai=dict(aggr=0.55, block=0.4, react=12)),
    "ken": dict(weight=1.0, walk=1.8, air=1.9, jump=-5.6, djump=-5.2, grav=1.0, moves=_ken(),
                ai=dict(aggr=0.7, block=0.3, react=12)),
    "chunli": dict(weight=0.88, walk=2.0, air=2.0, jump=-5.8, djump=-5.4, grav=0.95, moves=_chunli(),
                   ai=dict(aggr=0.6, block=0.4, react=11)),
    "zangief": dict(weight=1.3, walk=1.3, air=1.5, jump=-5.0, djump=-4.6, grav=1.05, moves=_zangief(),
                    ai=dict(aggr=0.65, block=0.25, react=15)),
    "sakura": dict(weight=0.86, walk=1.9, air=1.9, jump=-5.8, djump=-5.4, grav=1.0, moves=_sakura(),
                   ai=dict(aggr=0.65, block=0.3, react=12)),
    "morrigan": dict(weight=0.95, walk=1.8, air=2.0, jump=-5.8, djump=-5.8, grav=0.9, moves=_morrigan(),
                     ai=dict(aggr=0.55, block=0.4, react=12)),
    "felicia": dict(weight=0.9, walk=2.1, air=2.0, jump=-5.9, djump=-5.4, grav=1.0, moves=_felicia(),
                    ai=dict(aggr=0.75, block=0.25, react=13)),
    "hsienko": dict(weight=1.0, walk=1.6, air=1.8, jump=-5.6, djump=-5.2, grav=1.0, moves=_hsienko(),
                    ai=dict(aggr=0.55, block=0.35, react=13)),
}


# --------------------------------------------------------------------------
# scaled sprites, masks and strike areas (all cached)
# --------------------------------------------------------------------------
_SPR = {}
_FLASH = {}
_STRIKE = {}
_SHOTS = {}
_CIRCLES = {}
_PORTRAITS = {}


def _snap(img, k):
    """Smooth-scale, then snap alpha to on/off so edges stay crisp pixels."""
    w, h = img.get_size()
    out = pygame.transform.smoothscale(img, (max(1, round(w * k)), max(1, round(h * k))))
    m = pygame.mask.from_surface(out, 127)
    out.blit(m.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)), (0, 0),
             special_flags=pygame.BLEND_RGBA_MULT)
    out.blit(m.to_surface(setcolor=(0, 0, 0, 255), unsetcolor=(0, 0, 0, 0)), (0, 0),
             special_flags=pygame.BLEND_RGBA_MAX)
    return out, m


def sprite(art, key, flip, k):
    """(image, feet anchor, mask) of one sheet drawing at scale k."""
    ck = (art.cid, key, flip, k)
    e = _SPR.get(ck)
    if e is None:
        if flip:
            img, (ax, ay), _ = sprite(art, key, False, k)
            img = pygame.transform.flip(img, True, False)
            e = (img, (img.get_width() - ax, ay), pygame.mask.from_surface(img, 127))
        else:
            base, (bx, by) = art.base[key]
            img, m = _snap(base, k)
            e = (img, (round(bx * k), round(by * k)), m)
        _SPR[ck] = e
    return e


def flash_of(art, key, flip, k):
    ck = (art.cid, key, flip, k)
    s = _FLASH.get(ck)
    if s is None:
        s = _FLASH[ck] = sprite(art, key, flip, k)[2].to_surface(setcolor=(255, 255, 255, 255),
                                                                unsetcolor=(0, 0, 0, 0))
    return s


def strike_mask(art, key, flip, k, base, zone, box):
    """The part of a frame that is the attack: the frame's pixels minus the
    fighter's resting body (dilated 2px, lined up at the feet), keeping only
    real chunks (and, for 'front' moves, only what is in front of the feet).
    Falls back to the move's box if nothing sticks out.
    Returns (mask, ox, oy): offset from the frame's top-left."""
    ck = (art.cid, key, flip, k, base, zone, box)
    e = _STRIKE.get(ck)
    if e is not None:
        return e
    img, (ax, ay), m = sprite(art, key, flip, k)
    if zone == "body":                       # rolling attacks: the whole ball hits
        e = _STRIKE[ck] = (m, 0, 0)
        return e
    bkey = art.resolve(base, 0, 0)
    _, (bx, by), bm = sprite(art, bkey, flip, k)
    bw, bh = bm.get_size()
    dil = pygame.Mask((bw + 4, bh + 4))
    for dx in range(5):
        for dy in range(5):
            if (dx - 2) ** 2 + (dy - 2) ** 2 <= 5:
                dil.draw(bm, (dx, dy))
    out = m.copy()
    out.erase(dil, (ax - bx - 2, ay - by - 2))
    w, h = out.get_size()
    if zone == "front":
        if not flip and ax - 2 > 0:
            out.erase(pygame.Mask((ax - 2, h), fill=True), (0, 0))
        elif flip and ax + 2 < w:
            out.erase(pygame.Mask((w - ax - 2, h), fill=True), (ax + 2, 0))
    clean = pygame.Mask((w, h))
    for c in out.connected_components(8):
        clean.draw(c, (0, 0))
    if clean.count() >= 10:
        e = (clean, 0, 0)
    else:
        x, y, bw2, bh2 = [round(v * k) for v in box]
        rx = ax + x if not flip else ax - x - bw2
        e = (pygame.Mask((max(1, bw2), max(1, bh2)), fill=True), rx, ay + y)
    _STRIKE[ck] = e
    return e


def circle_mask(r):
    e = _CIRCLES.get(r)
    if e is None:
        s = pygame.Surface((r * 2 + 1, r * 2 + 1), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 255, 255), (r, r), r)
        e = _CIRCLES[r] = pygame.mask.from_surface(s)
    return e


def shot_frames(art, air, colors=None):
    """A character's projectile drawings, scaled, facing right and left: [(img, mask)]."""
    ck = (art.cid, air)
    e = _SHOTS.get(ck)
    if e is None:
        raw = art.projectile_frames(air)
        k = SCALE
        if not raw:
            raw = make_fireball(colors or ((255, 255, 220), (120, 200, 255), (40, 80, 220)))
            k = 0.8
        right = []
        for f in raw:
            img, m = _snap(f, k)
            right.append((img, m))
        left = []
        for img, _ in right:
            fl = pygame.transform.flip(img, True, False)
            left.append((fl, pygame.mask.from_surface(fl, 127)))
        e = _SHOTS[ck] = (right, left)
    return e


def small_portrait(cid, size=18):
    ck = (cid, size)
    e = _PORTRAITS.get(ck)
    if e is None:
        e = _PORTRAITS[ck] = pygame.transform.scale(portrait(cid), (size, size))
    return e


def sign(v):
    return (v > 0) - (v < 0)


# --------------------------------------------------------------------------
# input
# --------------------------------------------------------------------------
class Intent:
    __slots__ = ("left", "right", "up", "down", "up_p", "down_p", "left_p", "right_p",
                 "punch", "kick", "special", "shield")

    def __init__(self, **kw):
        for s in self.__slots__:
            setattr(self, s, kw.get(s, False))

    @property
    def dir(self):
        return int(bool(self.right)) - int(bool(self.left))

    def any(self):
        return any(getattr(self, s) for s in self.__slots__)

    @classmethod
    def from_input(cls, inp):
        return cls(left=inp.held("left"), right=inp.held("right"), up=inp.held("up"),
                   down=inp.held("down"), up_p=inp.pressed("up"), down_p=inp.pressed("down"),
                   left_p=inp.pressed("left"), right_p=inp.pressed("right"),
                   punch=inp.pressed("punch"), kick=inp.pressed("kick"),
                   special=inp.pressed("special"), shield=inp.held("shield"))

    def held_actions(self):
        return {a for a in ("left", "right", "up", "down", "shield") if getattr(self, a)}

    def pressed_actions(self):
        out = {a for a in ("punch", "kick", "special") if getattr(self, a)}
        for a in ("up", "down", "left", "right"):
            if getattr(self, a + "_p"):
                out.add(a)
        return out


NO_INPUT = Intent()


# --------------------------------------------------------------------------
# terrain helpers
# --------------------------------------------------------------------------
def ground_at(x, y, drop=False):
    """The floor height a fighter's feet at (x, y) stand on, or None."""
    for r in SOLIDS:
        if r.left - 3 <= x <= r.right + 3 and abs(y - r.top) < 0.5:
            return r.top
    if not drop:
        for x0, x1, yy in SOFTS:
            if x0 <= x <= x1 and abs(y - yy) < 0.5:
                return yy
    return None


def on_soft(x, y):
    return any(x0 <= x <= x1 and abs(y - yy) < 0.5 for x0, x1, yy in SOFTS)


def surface_below(x, y):
    best = None
    for r in SOLIDS:
        if r.left <= x <= r.right and r.top >= y - 0.5:
            best = r.top if best is None else min(best, r.top)
    for x0, x1, yy in SOFTS:
        if x0 <= x <= x1 and yy >= y - 0.5:
            best = yy if best is None else min(best, yy)
    return best


def _body_hits(x, y, r):
    return x + BODY_W > r.left and x - BODY_W < r.right and y > r.top and y - BODY_H < r.bottom


# --------------------------------------------------------------------------
# a fighter
# --------------------------------------------------------------------------
class Smasher:
    def __init__(self, scene, cid, slot, is_player=False):
        spec = CHARS[cid]
        self.sc = scene
        self.cid = cid
        self.name = NAMES[cid]
        self.slot = slot
        self.color = SLOT_COLORS[slot]
        self.is_player = is_player
        self.art = CharArt(cid)
        self.k = SCALE
        self.weight = spec["weight"]
        self.walk = spec["walk"]
        self.air_max = spec["air"]
        self.jump_v = spec["jump"]
        self.djump_v = spec["djump"]
        self.grav_k = spec["grav"]
        self.moves = spec["moves"]
        _, (_, _), m = sprite(self.art, self.art.resolve("idle", 0, 0), False, self.k)
        rects = m.get_bounding_rects()
        bb = rects[0].unionall(rects)
        self.hgt = bb.h
        # some sheets draw the intro at another size: use idle for those
        im = sprite(self.art, self.art.resolve("intro", 0, 0), False, self.k)[0]
        self.intro_pose = "intro" if im.get_height() <= m.get_size()[1] * 1.15 else "idle"
        self.half_w = max(6, bb.w // 3)
        self.stocks = STOCKS
        self.pct = 0.0
        self.out = False
        self.x, self.y = 0.0, float(FLOOR_Y)
        self.vx = self.vy = self.lvx = self.lvy = 0.0
        self.facing = 1
        self.airborne = False
        self.state = "intro"
        self.t = 0
        self.pose = "intro"
        self.pose_t = 0
        self.move = None
        self.move_name = None
        self.move_t = 0
        self.move_air = False
        self.move_vx = None
        self.victims = {}
        self.jumps = 1
        self.upb_used = False
        self.helpless = False
        self.fastfall = False
        self.shield = SHIELD_MAX
        self.invuln = 0
        self.hitstun = 0
        self.tumble = False
        self.hitstop = 0
        self.drop = 0
        self.roll_dir = 1
        self.buf = None            # (button, up, down, frames left)
        self.jbuf = 0
        self.grabbed = None
        self.held_by = None
        self.flash = 0
        self.dmg_shake = 0
        self.last_hit_by = None
        self.ko_count = 0
        self.crouch = False
        self.land_lag = 4
        self._whiff_t = -1
        self.draw_key = None
        self.flip = False
        self.draw_pos = (0, 0)
        self.prev_pose = None

    # ---- queries -----------------------------------------------------------
    @property
    def alive(self):
        return not self.out and self.state not in ("dead",)

    @property
    def on_field(self):
        return not self.out and self.state not in ("dead", "respawn", "intro")

    @property
    def center(self):
        return self.x, self.y - self.hgt * 0.5

    def phase_info(self):
        """(kind, pose, run_t, span) of the current move."""
        mv = self.move
        ph = mv["phases"]
        total = sum(n for _, n, _ in ph)
        t = self.move_t
        if t >= total:
            idx = len(ph) - 1
            t_in = t - (total - ph[-1][1])
        else:
            idx = 0
            t_in = t
            while t_in >= ph[idx][1]:
                t_in -= ph[idx][1]
                idx += 1
        kind, n, pose = ph[idx]
        run_t, span = t_in, n
        j = idx - 1
        while j >= 0 and ph[j][2] == pose:
            run_t += ph[j][1]
            span += ph[j][1]
            j -= 1
        j = idx + 1
        while j < len(ph) and ph[j][2] == pose:
            span += ph[j][1]
            j += 1
        return kind, pose, run_t, span

    def move_total(self):
        return sum(n for _, n, _ in self.move["phases"])

    def striking(self):
        if self.state != "move" or not self.move or self.hitstop:
            return False
        mv = self.move
        if not (mv.get("dmg") or mv.get("grab")):
            return False
        return self.phase_info()[0] == "active"

    def invulnerable(self):
        if self.invuln or self.state in ("dead", "respawn", "held", "intro") or self.out:
            return True
        if self.state == "roll" and 2 <= self.t <= 15:
            return True
        if self.state == "getup" or self.state == "ledge":
            return True
        if self.state == "move" and self.move.get("invuln"):
            a, b = self.move["invuln"]
            return a <= self.move_t <= b
        return False

    def shield_radius(self):
        full = self.hgt * 0.62
        return max(6, round(full * (0.35 + 0.65 * max(0.0, self.shield) / SHIELD_MAX)))

    def hurt(self):
        """(mask, top-left) of where this fighter can be hit, or None."""
        if self.invulnerable() or self.draw_key is None:
            return None
        if self.state == "shield":
            r = self.shield_radius()
            cx, cy = self.center
            return circle_mask(r), (round(cx) - r, round(cy) - r)
        return sprite(self.art, self.draw_key, self.flip, self.k)[2], self.draw_pos

    # ---- moves -------------------------------------------------------------
    def pick_move(self, btn, up, down):
        Mv = self.moves
        air = self.airborne
        if btn == "special":
            if up:
                name = "up"
            elif down:
                name = "down"
            else:
                name = "airneutral" if air and "airneutral" in Mv else "neutral"
        elif btn == "punch":
            name = "nair" if air else ("crjab" if down else "jab")
        elif btn == "grab":
            name = "grab"
        else:
            name = ("dair" if down and "dair" in Mv else "fair") if air else ("sweep" if down else "kick")
        mv = Mv.get(name)
        if mv is None:
            return None
        if air and mv.get("ground"):
            return None
        if name == "up" and self.upb_used:
            return None
        return name

    def start_move(self, name):
        mv = self.moves[name]
        if mv.get("upb"):
            self.upb_used = True
        self.move, self.move_name, self.move_t = mv, name, 0
        self.move_air = self.airborne
        self.move_vx = None
        self.state = "move"
        self.victims = {}
        self.buf = None
        if not self.airborne:
            self.vx *= 0.3
        self._events(0)
        if not any(e.get("sound") for e in mv["ev"].values()) and (mv.get("dmg") or mv.get("grab")):
            self._whiff_t = sum(n for kind, n, _ in mv["phases"] if kind == "startup")
        else:
            self._whiff_t = -1

    def _events(self, t):
        ev = self.move["ev"].get(t)
        if not ev:
            return
        if "vy" in ev:
            self.vy = ev["vy"]
            if self.vy < 0:
                self.airborne = True
        if "vxf" in ev:
            self.move_vx = ev["vxf"] or None
            if not ev["vxf"]:
                self.vx = 0.0
        if "sound" in ev:
            audio.play(ev["sound"], 0.8)
        if "proj" in ev:
            self.sc.spawn_shot(self, ev["proj"])
        if ev.get("release") and self.grabbed:
            self.sc.release_throw(self)

    def end_move(self):
        mv = self.move
        self.move = None
        self.move_vx = None
        if self.grabbed:
            self.sc.drop_grab(self)
        if self.airborne:
            self.state = "air"
            if mv and mv.get("upb"):
                self.helpless = True
        else:
            self.state = "stand"
        self.t = 0

    # ---- per frame ---------------------------------------------------------
    def update(self, it):
        if self.out:
            return
        if self.state == "dead":
            self.t += 1
            if self.t >= RESPAWN_WAIT:
                self.sc.respawn(self)
            return
        if self.flash:
            self.flash -= 1
        if self.dmg_shake:
            self.dmg_shake -= 1
        # remember presses so a button pushed a few frames early still comes out
        for btn in ("special", "punch", "kick"):
            if getattr(it, btn):
                self.buf = (btn, it.up, it.down, 8)
                break
        else:
            if self.buf:
                b, u, d, n = self.buf
                self.buf = (b, u, d, n - 1) if n > 1 else None
        if it.up_p:
            self.jbuf = 6
        elif self.jbuf:
            self.jbuf -= 1
        if self.hitstop:
            self.hitstop -= 1
            return
        self.t += 1
        if self.invuln:
            self.invuln -= 1
        if self.drop:
            self.drop -= 1
        if self.state != "shield" and self.shield < SHIELD_MAX:
            self.shield = min(SHIELD_MAX, self.shield + SHIELD_REGEN)
        st = self.state
        if st == "intro" or st == "win":
            return
        if st == "respawn":
            self.y = HALO_Y
            if it.any() and self.t > 10 or self.t > RESPAWN_HOLD:
                self.state, self.t = "air", 0
                self.airborne = True
                self.invuln = RESPAWN_INVULN
            return
        if st == "held":
            return
        getattr(self, "_st_" + st)(it)
        self._physics(it)

    def _consume_attack(self, it):
        if not self.buf:
            return False
        btn, up, down, _ = self.buf
        if self.helpless:
            return False
        name = self.pick_move(btn, up, down)
        if name is None:
            self.buf = None
            return False
        if it.dir:
            self.facing = it.dir
        self.start_move(name)
        return True

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
        if it.down_p and on_soft(self.x, self.y):
            self.drop = 14
            self.airborne = True
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
            self.vx *= FRICTION
            if abs(self.vx) < 0.05:
                self.vx = 0.0

    def _st_prejump(self, it):
        self.vx *= 0.9
        if self.t >= 3:
            self.vy = self.jump_v if it.up else self.jump_v * 0.74
            self.airborne = True
            self.state, self.t = "air", 0
            audio.play("jump", 0.6)

    def _st_air(self, it):
        d = it.dir
        if d:
            self.facing = d
        if not self.helpless:
            if self._consume_attack(it):
                return
            if self.jbuf and self.jumps > 0:
                self.jbuf = 0
                self.jumps -= 1
                self.vy = self.djump_v
                self.lvy = min(0.0, self.lvy) * 0.3
                self.fastfall = False
                self.t = 0
                self.prev_pose = None
                self.sc.puff(self.x, self.y)
                audio.play("jump", 0.6)
        cap = self.air_max * (0.6 if self.helpless else 1.0)
        if d:
            self.vx = max(-cap, min(cap, self.vx + AIR_ACC * d))
        else:
            self.vx *= 0.96
        if it.down_p and self.vy > -1 and not self.fastfall:
            self.fastfall = True
            self.vy = max(self.vy, FASTFALL)

    def _st_move(self, it):
        mv = self.move
        self.move_t += 1
        self._events(self.move_t)
        if self.move_t == self._whiff_t:
            audio.play("whiff", 0.6)
        if self.move_vx is not None:
            self.vx = self.move_vx * self.facing
        elif self.airborne:
            d = it.dir
            if d:
                self.vx = max(-self.air_max, min(self.air_max, self.vx + AIR_ACC * 0.5 * d))
        else:
            self.vx *= FRICTION
        if mv.get("fire") and self.phase_info()[0] == "active" and self.t % 2 == 0:
            self.sc.embers(self)
        if self.move_t >= self.move_total() and not (mv.get("hold") and self.airborne):
            self.end_move()

    def _st_land(self, it):
        self.vx *= FRICTION
        if self.t >= self.land_lag:
            self.state, self.t = "stand", 0

    def _st_shield(self, it):
        self.vx *= 0.5
        self.shield -= SHIELD_DRAIN
        if self.shield <= 0:
            self.sc.shield_break(self)
            return
        if self.buf and self.buf[0] == "punch" and "grab" in self.moves:
            self.start_move("grab")
            return
        if self.jbuf:
            self.jbuf = 0
            self.state, self.t = "prejump", 0
            return
        if it.left_p or it.right_p:
            self.roll_dir = -1 if it.left_p else 1
            self.facing = self.roll_dir
            self.state, self.t = "roll", 0
            audio.play("step")
            return
        if not it.shield:
            self.state, self.t = "stand", 0

    def _st_roll(self, it):
        self.vx = self.roll_dir * (2.6 if self.t < 14 else 0.8)
        if ground_at(self.x + self.vx * 2, self.y) is None:
            self.vx = 0.0
        if self.t >= ROLL_LEN:
            self.state, self.t = "stand", 0

    def _st_dizzy(self, it):
        self.vx *= 0.8
        if self.t >= SHIELD_BREAK:
            self.shield = SHIELD_MAX * 0.5
            self.state, self.t = ("air" if self.airborne else "stand"), 0

    def _st_hitstun(self, it):
        if not self.airborne:
            self.vx *= 0.8
        self.hitstun -= 1
        if self.hitstun <= 0:
            self.state, self.t = ("air" if self.airborne else "stand"), 0
            self.tumble = False

    def _st_down(self, it):
        self.vx *= 0.8
        if self.t >= 26 or (self.t > 8 and (it.any())):
            self.state, self.t = "getup", 0

    def _st_getup(self, it):
        if self.t >= 14:
            self.state, self.t = "stand", 0

    def _st_ledge(self, it):
        if self.t >= 10:
            self.state, self.t = "stand", 0

    # ---- physics -----------------------------------------------------------
    def _gravity_on(self):
        if self.state == "move":
            ng = self.move.get("nograv")
            if ng and ng[0] <= self.move_t < ng[1]:
                return False
        return True

    def _physics(self, it):
        if self.lvx or self.lvy:
            sp = math.hypot(self.lvx, self.lvy)
            nsp = sp - KB_DECAY
            if nsp <= 0:
                self.lvx = self.lvy = 0.0
            else:
                self.lvx *= nsp / sp
                self.lvy *= nsp / sp
        if self.airborne and self._gravity_on():
            cap = FASTFALL if self.fastfall else FALL_MAX
            if self.vy < cap:
                self.vy = min(cap, self.vy + GRAV * self.grav_k)
        dx = self.vx + self.lvx
        dy = (self.vy + self.lvy) if self.airborne else 0.0
        # horizontal, against walls
        self.x += dx
        for r in SOLIDS:
            if _body_hits(self.x, self.y, r):
                if dx > 0:
                    self.x = r.left - BODY_W
                elif dx < 0:
                    self.x = r.right + BODY_W
                else:
                    self.x = r.left - BODY_W if self.x < r.centerx else r.right + BODY_W
                self.vx = 0.0
                self.lvx *= -0.4
        # vertical
        if self.airborne:
            py = self.y
            self.y += dy
            if dy >= 0:
                land = None
                for r in SOLIDS:
                    if r.left - 3 <= self.x <= r.right + 3 and py <= r.top + 0.01 and self.y >= r.top:
                        land = r.top if land is None else min(land, r.top)
                if not self.drop:
                    for x0, x1, yy in SOFTS:
                        if x0 <= self.x <= x1 and py <= yy + 0.01 and self.y >= yy:
                            land = yy if land is None else min(land, yy)
                if land is not None:
                    self.y = land
                    self._land(dy)
            else:
                for r in SOLIDS:
                    if (self.x + BODY_W > r.left and self.x - BODY_W < r.right
                            and py - BODY_H >= r.bottom - 0.01 and self.y - BODY_H < r.bottom):
                        self.y = r.bottom + BODY_H
                        self.vy = 0.0
                        self.lvy = 0.0
            if self.airborne:
                self._ledge_snap(it)
        else:
            if ground_at(self.x, self.y, self.drop) is None:
                self.airborne = True
                if self.state in ("stand", "land", "prejump", "shield", "roll", "getup", "down", "ledge"):
                    self.state, self.t = "air", 0

    def _ledge_snap(self, it):
        """Grab a ledge you are rising or falling past, and climb up (Smash's ledge grab, simplified)."""
        if self.state not in ("air", "move") or self.vy + self.lvy < -1.5:
            return
        if self.state == "move" and not (self.move.get("upb") or self.helpless):
            return
        for lx, ly, side in LEDGES:
            inward = -side
            if not (ly - 2 <= self.y <= ly + 26):
                continue
            off = (self.x - lx) * side          # how far outside the ledge
            if -2 <= off <= 16 and (it.dir == inward or self.vx * inward > 0.2 or self.helpless):
                if self.state == "move":
                    self.move = None
                    self.move_vx = None
                self.x = lx + inward * 6
                self.y = ly
                self.vx = self.vy = self.lvx = self.lvy = 0.0
                self._landed_reset()
                self.state, self.t = "ledge", 0
                self.facing = inward
                audio.play("land", 0.6)
                return

    def _landed_reset(self):
        self.airborne = False
        self.jumps = 1
        self.upb_used = False
        self.helpless = False
        self.fastfall = False

    def _land(self, dy):
        st = self.state
        was_helpless = self.helpless
        self.vy = 0.0
        self.lvy = 0.0
        self.lvx *= 0.5
        self._landed_reset()
        if st == "move":
            mv = self.move
            if mv.get("hold") or mv.get("upb") or self.move_air:
                self.move = None
                self.move_vx = None
                if self.grabbed:
                    self.sc.drop_grab(self)
                self.state, self.t = "land", 0
                self.land_lag = mv.get("land_lag", 6)
            return
        if st == "hitstun":
            if self.tumble and self.hitstun > 4:
                self.state, self.t = "down", 0
                self.sc.puff(self.x, self.y)
                audio.play("land")
            return
        if st == "dizzy":
            return
        if st == "air":
            self.state, self.t = "land", 0
            self.land_lag = 12 if was_helpless else (4 if dy > 2 else 2)
            if dy > 2:
                audio.play("land", 0.5)

    # ---- display -----------------------------------------------------------
    def _pose(self):
        """(pose name, frames in that pose, span, cycle) for what the fighter is doing."""
        st = self.state
        if st == "move":
            kind, pose, run_t, span = self.phase_info()
            cyc = self.move.get("cycle") if kind == "active" else None
            return pose, run_t, span, cyc, True
        if st == "stand":
            if getattr(self, "crouch", False):
                p = "crouch"
            elif abs(self.vx) > 0.3:
                p = "walk"
            else:
                p = "idle"
        elif st in ("air",):
            if self.helpless:
                p = "fall"
            elif self.vy < -1.5:
                p = "jump_up"
            elif self.vy < 1.5:
                p = "jump"
            else:
                p = "fall"
        elif st == "hitstun":
            p = "launch" if self.tumble else "hurt"
        elif st == "dizzy":
            p = "hurt"
        elif st == "shield":
            p = "block"
        elif st == "roll":
            p = "dash"
        elif st in ("land", "ledge"):
            p = "land"
        elif st == "prejump":
            p = "prejump"
        elif st == "down":
            p = "down"
        elif st == "getup":
            p = "getup"
        elif st == "held":
            p = "hurt"
        elif st == "win":
            p = "victory"
        elif st == "intro":
            p = self.intro_pose
        else:
            p = "idle"
        return p, None, None, None, False

    def refresh(self):
        """Pick the drawing shown this frame (hit detection uses exactly this one)."""
        if self.out or self.state == "dead":
            self.draw_key = None
            return
        pose, run_t, span, cyc, in_move = self._pose()
        if in_move:
            pt = run_t
        else:
            if pose != self.prev_pose:
                self.pose_t = 0
            elif not self.hitstop:
                self.pose_t += 1
            pt = self.pose_t
        self.prev_pose = None if in_move else pose
        self.pose = pose
        if cyc:
            frames = self.art._anim(pose)[0]
            key = frames[(pt // cyc) % len(frames)]
        else:
            key = self.art.resolve(pose, pt, pt, span)
        self.draw_key = key
        self.flip = self.facing < 0
        _, (ax, ay), _ = sprite(self.art, key, self.flip, self.k)
        jit = 0
        if self.hitstop and self.state in ("hitstun", "shield"):
            jit = (1, -1)[self.hitstop % 2]
        self.draw_pos = (round(self.x) - ax + jit, round(self.y) - ay)


# --------------------------------------------------------------------------
# projectiles
# --------------------------------------------------------------------------
class Shot:
    def __init__(self, owner, spec):
        k = owner.k
        self.owner = owner
        self.dir = owner.facing
        self.x = owner.x + spec.get("x", 30) * k * self.dir
        self.y = owner.y + spec.get("y", -38) * k
        self.vx = spec["speed"] * self.dir
        self.vy = spec.get("vy", 0.0)
        self.grav = spec.get("grav", 0.0)
        self.life = spec.get("life", 100)
        self.spec = spec
        right, left = shot_frames(owner.art, spec.get("air", False))
        self.frames = right if self.dir > 0 else left
        self.t = 0
        self.alive = True

    def update(self):
        self.t += 1
        self.x += self.vx
        self.y += self.vy
        self.vy += self.grav
        if self.t >= self.life or not (-40 < self.x < W + 40) or self.y > H + 20:
            self.alive = False
        for r in SOLIDS:
            if r.collidepoint(self.x, self.y):
                self.alive = False

    def frame(self):
        img, m = self.frames[(self.t // 3) % len(self.frames)]
        return img, m, (round(self.x - img.get_width() / 2), round(self.y - img.get_height() / 2))


# --------------------------------------------------------------------------
# CPU brain (also drives Akuma in the tests' bot)
# --------------------------------------------------------------------------
class Brain:
    def __init__(self, scene, me, rng, focus=CPU_FOCUS):
        self.sc, self.me, self.rng = scene, me, rng
        p = CHARS[me.cid]["ai"]
        self.aggr, self.block, self.react = p["aggr"], p["block"], p["react"]
        self.focus = focus
        self.target = None
        self.retarget = 0
        self.cool = 40
        self.shield_t = 0
        self.threat_t = 0
        self.wait = 0
        self.leave_t = rng.randint(30, 70)

    def think(self):
        me, rng = self.me, self.rng
        it = Intent()
        if me.out or me.state in ("dead", "intro", "win"):
            return it
        if me.state == "respawn":
            if me.t > self.leave_t:
                it.down_p = True
                self.leave_t = rng.randint(30, 70)
            return it
        if self.cool:
            self.cool -= 1
        if me.airborne and (me.x < STAGE_L + 2 or me.x > STAGE_R - 2 or me.y > FLOOR_Y + 2):
            return self._recover(it)
        if self._shielding(it):
            return it
        t = self._pick_target()
        if t is None:
            d = sign(160 - me.x) if abs(160 - me.x) > 20 else 0
            it.left, it.right = d < 0, d > 0
            return it
        if self.wait:
            self.wait -= 1
            return it
        if me.state not in ("stand", "air"):
            return it
        dx = t.x - me.x
        dy = t.y - me.y
        adx = abs(dx)
        d = sign(dx) or me.facing
        tx = max(STAGE_L + 10, min(STAGE_R - 10, t.x))
        want = 0
        if abs(tx - me.x) > 14:
            want = sign(tx - me.x)
        if not me.airborne:
            if self.cool == 0 and not t.invulnerable() and abs(dy) < 22 and self._ground_attack(it, t, adx, d):
                return it
            if self.cool == 0 and t.state == "shield" and adx < 26 and "grab" in me.moves:
                it.shield = True
                it.punch = True
                self.cool = rng.randint(20, 40)
                return it
            if (self.cool < 10 and "proj" in str(me.moves["neutral"]["ev"]) and 60 < adx < 170
                    and abs(dy) < 14 and rng.random() < 0.04):
                it.left, it.right = d < 0, d > 0
                it.special = True
                self.cool = rng.randint(30, 60)
                return it
            if dy < -22 and adx < 60 and rng.random() < 0.12:
                it.up_p = it.up = True
            elif dy > 22 and on_soft(me.x, me.y) and adx < 80 and rng.random() < 0.2:
                it.down_p = it.down = True
                return it
            if want:
                ahead = me.x + want * 8
                if (ahead < STAGE_L + 4 or ahead > STAGE_R - 4) and ground_at(me.x, me.y) == FLOOR_Y:
                    want = 0
                for r in SOLIDS[1:]:
                    if _body_hits(me.x + want * 6, me.y, r):
                        it.up_p = it.up = True
            if want == 0 and adx > 4 and rng.random() < 0.3:
                it.left, it.right = d < 0, d > 0     # face the target
            else:
                it.left, it.right = want < 0, want > 0
            if rng.random() < 0.006 * (1.2 - self.aggr):
                self.wait = rng.randint(8, 30)
        else:
            if me.x < STAGE_L + 14 and want <= 0:
                want = 1
            elif me.x > STAGE_R - 14 and want >= 0:
                want = -1
            it.left, it.right = want < 0, want > 0
            if (self.cool == 0 and not t.invulnerable() and adx < 34 and abs(dy + 8) < 26
                    and not me.helpless):
                it.left, it.right = d < 0, d > 0
                if dy > 14 and "dair" in me.moves and rng.random() < 0.4:
                    it.down = True
                    it.kick = True
                else:
                    setattr(it, rng.choice(("punch", "kick")), True)
                self.cool = rng.randint(14, 34)
            elif dy < -12 and me.jumps and me.vy > -0.5 and adx < 50:
                it.up_p = it.up = True
        return it

    def _ground_attack(self, it, t, adx, d):
        me, rng = self.me, self.rng
        sc = self.sc
        reach_pad = t.half_w + 2
        opts = []
        for name, wgt in (("jab", 3), ("kick", 2), ("sweep", 2), ("down", 1), ("crjab", 1)):
            if name in me.moves and not me.moves[name].get("grab"):
                if adx <= sc.reach(me, name) + reach_pad:
                    if name == "kick" and t.pct > 80:
                        wgt = 6
                    opts.append((name, wgt))
        if t.y < me.y - 20 and adx < 30 and "up" in me.moves and not me.moves["up"].get("grab"):
            opts.append(("up", 2))
        if "neutral" in me.moves and me.moves["neutral"].get("grab") and adx < sc.reach(me, "neutral") + reach_pad:
            opts.append(("neutral", 2))
        if not opts or rng.random() > 0.25 + 0.6 * self.aggr:
            return False
        tot = sum(w for _, w in opts)
        r = rng.random() * tot
        for name, wgt in opts:
            r -= wgt
            if r <= 0:
                break
        it.left, it.right = d < 0, d > 0
        if name == "jab":
            it.punch = True
        elif name == "crjab":
            it.down, it.punch = True, True
        elif name == "kick":
            it.kick = True
        elif name == "sweep":
            it.down, it.kick = True, True
        elif name == "down":
            it.down, it.special = True, True
        elif name == "up":
            it.up, it.special = True, True
        else:
            it.special = True
        self.cool = int(rng.randint(18, 50) * (1.4 - self.aggr))
        return True

    def _recover(self, it):
        me = self.me
        side = -1 if me.x < 160 else 1
        ledge_x = STAGE_L if side < 0 else STAGE_R
        toward = -side
        it.left, it.right = toward < 0, toward > 0
        if me.state != "air" or me.helpless:
            return it
        dx = abs(me.x - ledge_x)
        dy = me.y - FLOOR_Y
        if me.jumps > 0 and me.vy >= -0.5 and (dy > -24 or dx > 40):
            it.up_p = it.up = True
        elif not me.upb_used and me.vy >= -0.5 and dy > -8 and dx < 90:
            it.up = True
            it.special = True
        elif (me.jumps == 0 and me.upb_used is False and dx > 60 and dy < -10
              and me.moves.get("down", {}).get("recover")):
            it.down = True
            it.special = True
        return it

    def _threat(self):
        me = self.me
        for o in self.sc.fighters:
            if o is me or not o.on_field or o.state != "move":
                continue
            mv = o.move
            if not (mv.get("dmg")) or abs(o.x - me.x) > 52 or abs(o.y - me.y) > 36:
                continue
            kind = o.phase_info()[0]
            if kind in ("startup", "active") and (mv.get("zone") in ("all", "body") or (me.x - o.x) * o.facing > -6):
                return True
        for s in self.sc.shots:
            if s.owner is not me and abs(s.y - (me.y - me.hgt / 2)) < 24 and 0 < (me.x - s.x) * sign(s.vx) < 64:
                return True
        return False

    def _shielding(self, it):
        me = self.me
        if self.shield_t > 0:
            self.shield_t -= 1
            if me.shield > 12 and me.state in ("stand", "shield"):
                it.shield = True
                return True
            self.shield_t = 0
        if me.airborne or me.state not in ("stand",):
            self.threat_t = 0
            return False
        if self._threat():
            self.threat_t += 1
            if self.threat_t == self.react and self.rng.random() < self.block:
                self.shield_t = self.rng.randint(12, 26)
                it.shield = True
                return True
        else:
            self.threat_t = 0
        return False

    def _pick_target(self):
        me, sc = self.me, self.sc

        def ok(f):
            return f is not me and f.on_field

        self.retarget -= 1
        if self.target is None or not ok(self.target) or self.retarget <= 0:
            cands = [f for f in sc.fighters if ok(f)]
            if not cands:
                self.target = None
                return None
            ak = sc.akuma
            if me is not ak and ok(ak) and self.rng.random() < self.focus:
                self.target = ak
            else:
                self.target = min(cands, key=lambda f: abs(f.x - me.x) + abs(f.y - me.y))
            self.retarget = self.rng.randint(90, 200)
        return self.target


# --------------------------------------------------------------------------
# stage art
# --------------------------------------------------------------------------
SKY_TOP, SKY_BOT = (78, 136, 222), (186, 220, 248)
STONE = (176, 168, 156)
STONE_LT = (214, 206, 192)
STONE_DK = (118, 110, 104)
MORTAR = (140, 132, 124)
ROOF = (58, 146, 118)
ROOF_DK = (34, 98, 82)
WINDOW = (36, 30, 50)


def _bricks(s, rect, base, light, dark, mortar, row=6, brick=12, seed=0):
    x0, y0, w, h = rect
    s.fill(base, rect)
    rng = random.Random(seed)
    for yy in range(y0, y0 + h, row):
        off = (brick // 2) if ((yy - y0) // row) % 2 else 0
        s.fill(mortar, (x0, yy, w, 1))
        for xx in range(x0 - off, x0 + w, brick):
            if x0 <= xx < x0 + w:
                s.fill(mortar, (xx, yy, 1, row))
            if rng.random() < 0.25:
                bx = max(x0, xx + 1)
                bw = min(x0 + w, xx + brick) - bx
                if bw > 0:
                    s.fill(light if rng.random() < 0.5 else dark, (bx, yy + 1, bw, 1))


def _arch_window(s, x, y, w, h, col=WINDOW, rim=STONE_LT):
    pygame.draw.rect(s, rim, (x - 1, y + w // 2 - 1, w + 2, h - w // 2 + 1))
    pygame.draw.circle(s, rim, (x + w // 2, y + w // 2), w // 2 + 1)
    pygame.draw.rect(s, col, (x, y + w // 2, w, h - w // 2))
    pygame.draw.circle(s, col, (x + w // 2, y + w // 2), w // 2)


def _cloud(w, h, seed):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    rng = random.Random(seed)
    for _ in range(7):
        r = rng.randint(h // 4, h // 2)
        cx = rng.randint(r, w - r)
        pygame.draw.circle(s, (206, 222, 244), (cx, h - r), r)
    for _ in range(6):
        r = rng.randint(h // 5, h // 2 - 1)
        cx = rng.randint(r, w - r)
        pygame.draw.circle(s, (250, 250, 255), (cx, h - r - 2), r)
    s.fill((0, 0, 0, 0), (0, h - 2, w, 2))
    return s


def _soft_platform(s, x0, x1, y, top=STONE_LT, body=STONE, dark=STONE_DK):
    s.fill(OUTLINE, (x0 - 1, y - 1, x1 - x0 + 2, 6))
    s.fill(top, (x0, y, x1 - x0, 2))
    s.fill(body, (x0, y + 2, x1 - x0, 2))
    for xx in range(x0 + 3, x1 - 2, 8):
        s.fill(dark, (xx, y + 2, 1, 2))
    for bx in (x0 + 2, x1 - 7):          # corbels
        pygame.draw.polygon(s, dark, [(bx, y + 4), (bx + 5, y + 4), (bx + 3, y + 9)])


_STAGE = None


def stage_art():
    global _STAGE
    if _STAGE is not None:
        return _STAGE
    bg = pygame.Surface((W, H))
    for y in range(H):
        bg.fill(mix(SKY_TOP, SKY_BOT, y / H), (0, y, W, 1))
    rng = random.Random(64)
    # far mountains
    pts = [(0, H)]
    x = 0
    while x <= W:
        pts.append((x, 104 + rng.randint(-14, 8)))
        x += rng.randint(14, 30)
    pts += [(W, H)]
    pygame.draw.polygon(bg, (132, 162, 196), pts)
    # distant castle silhouette (left) and hills
    sil = (112, 136, 174)
    for tx, tw, th in ((14, 10, 54), (28, 22, 34), (52, 8, 46), (266, 10, 50), (280, 24, 30), (306, 8, 42)):
        bg.fill(sil, (tx, 122 - th, tw, th + 20))
        pygame.draw.polygon(bg, (98, 122, 162), [(tx - 2, 122 - th), (tx + tw // 2, 122 - th - 12),
                                                 (tx + tw + 1, 122 - th)])
    pts = [(0, H)]
    x = 0
    while x <= W:
        pts.append((x, 124 + int(6 * math.sin(x / 23.0)) + rng.randint(-2, 2)))
        x += 8
    pts += [(W, H)]
    pygame.draw.polygon(bg, (82, 150, 104), pts)
    for x in range(0, W, 5):               # tree line
        hgt = rng.randint(3, 7)
        pygame.draw.circle(bg, (56, 120, 82), (x, 128 - hgt // 2 + int(6 * math.sin(x / 23.0))), hgt // 2 + 2)
    bg.fill((60, 126, 86), (0, 132, W, H - 132))

    st = pygame.Surface((W, H), pygame.SRCALPHA)
    # background keeps behind the soft ledges (scenery, not solid)
    for (x0, x1, y), shadek in zip(SOFTS[:2], (0.82, 0.74)):
        rect = (x0 + 4, y + 4, x1 - x0 - 8, FLOOR_Y - y - 4)
        _bricks(st, rect, shade(STONE, shadek), shade(STONE_LT, shadek), shade(STONE_DK, shadek),
                shade(MORTAR, shadek), seed=x0)
        cx = (x0 + x1) // 2
        _arch_window(st, cx - 4, y + 10, 8, 13, rim=shade(STONE_LT, shadek))
    # tower roof pillars
    for px in (TOWER.left + 3, TOWER.right - 6):
        _bricks(st, (px, SOFTS[2][2] + 4, 3, TOWER.top - SOFTS[2][2] - 4), shade(STONE, 0.8),
                STONE, STONE_DK, MORTAR, row=4, brick=3, seed=px)
    # main castle block
    body = pygame.Rect(STAGE_L, FLOOR_Y, STAGE_R - STAGE_L, H - FLOOR_Y)
    _bricks(st, body, STONE, STONE_LT, STONE_DK, MORTAR, seed=3)
    for bx in (STAGE_L, STAGE_R - 8):       # corner buttresses
        st.fill(STONE_DK, (bx, FLOOR_Y + 3, 8, H))
        st.fill(shade(STONE_DK, 1.15), (bx + 1, FLOOR_Y + 3, 2, H))
    gx = (STAGE_L + STAGE_R) // 2 - 14     # the gate
    _arch_window(st, gx, FLOOR_Y + 12, 28, 40)
    for xx in range(gx + 3, gx + 28, 5):
        st.fill((70, 64, 76), (xx, FLOOR_Y + 22, 1, 40))
    for wx in (STAGE_L + 22, STAGE_L + 50, STAGE_R - 58, STAGE_R - 30):
        _arch_window(st, wx, FLOOR_Y + 12, 8, 14)
    # vines
    for vx in (STAGE_L + 14, STAGE_R - 40, gx + 34):
        for k in range(rng.randint(10, 22)):
            st.fill((52, 128, 72) if k % 3 else (84, 164, 92), (vx + int(2 * math.sin(k / 2.0)), FLOOR_Y + 3 + k, 2, 1))
    # floor surface
    st.fill(OUTLINE, (STAGE_L - 1, FLOOR_Y - 1, STAGE_R - STAGE_L + 2, 1))
    st.fill(STONE_LT, (STAGE_L, FLOOR_Y, STAGE_R - STAGE_L, 3))
    st.fill((236, 230, 218), (STAGE_L, FLOOR_Y, STAGE_R - STAGE_L, 1))
    st.fill(OUTLINE, (STAGE_L - 1, FLOOR_Y, 1, H))
    st.fill(OUTLINE, (STAGE_R, FLOOR_Y, 1, H))
    # tower
    _bricks(st, TOWER, STONE, STONE_LT, STONE_DK, MORTAR, seed=9)
    for k in range(4):                     # crenellations behind the walkway
        st.fill(shade(STONE, 0.78), (TOWER.left + 2 + k * 11, TOWER.top - 5, 6, 5))
    st.fill(STONE_LT, (TOWER.left, TOWER.top, TOWER.w, 3))
    st.fill((236, 230, 218), (TOWER.left, TOWER.top, TOWER.w, 1))
    pygame.draw.rect(st, OUTLINE, TOWER.inflate(2, 2), 1)
    _arch_window(st, TOWER.centerx - 4, TOWER.top + 8, 8, 14)
    st.fill((176, 30, 40), (TOWER.left + 6, TOWER.top + 5, 6, 16))          # banners
    st.fill((176, 30, 40), (TOWER.right - 12, TOWER.top + 5, 6, 16))
    for bx in (TOWER.left + 6, TOWER.right - 12):
        pygame.draw.polygon(st, (176, 30, 40), [(bx, TOWER.top + 21), (bx + 6, TOWER.top + 21),
                                                (bx + 3, TOWER.top + 24)])
        st.fill((240, 200, 60), (bx + 2, TOWER.top + 10, 2, 2))
    # soft ledges: two stone balconies and the tower's green roof
    for x0, x1, y in SOFTS[:2]:
        _soft_platform(st, x0, x1, y)
    x0, x1, y = SOFTS[2]
    st.fill(OUTLINE, (x0 - 1, y - 1, x1 - x0 + 2, 8))
    st.fill(ROOF, (x0, y, x1 - x0, 6))
    for xx in range(x0, x1, 4):
        st.fill(ROOF_DK, (xx, y + 2, 1, 4))
    st.fill(shade(ROOF, 1.35), (x0, y, x1 - x0, 1))
    pygame.draw.polygon(st, ROOF_DK, [(x0 + 18, y), (x0 + (x1 - x0) // 2, y - 10), (x1 - 18, y)])
    pygame.draw.line(st, OUTLINE, (x0 + 17, y - 1), (x0 + (x1 - x0) // 2, y - 11))
    pygame.draw.line(st, OUTLINE, (x0 + (x1 - x0) // 2, y - 11), (x1 - 17, y - 1))
    st.fill((240, 200, 60), (x0 + (x1 - x0) // 2 - 1, y - 15, 2, 4))
    clouds = [_cloud(56, 18, 1), _cloud(40, 14, 2), _cloud(70, 22, 3)]
    _STAGE = dict(bg=bg, stage=st, clouds=clouds,
                  spark=F.SPARK_HIT, spark_small=[pygame.transform.scale_by(f, 0.6) for f in F.SPARK_HIT],
                  block=F.SPARK_BLOCK, smash=make_spark((255, 90, 40)))
    return _STAGE


def pct_color(p):
    stops = ((0, (255, 255, 255)), (60, (255, 236, 110)), (120, (255, 136, 40)), (200, (200, 20, 24)))
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if p <= b:
            return mix(ca, cb, max(0.0, (p - a) / (b - a)))
    return stops[-1][1]


# --------------------------------------------------------------------------
# the level
# --------------------------------------------------------------------------
class SmashScene:
    def __init__(self, game, seed=None, level=6, hp=None):
        F.init_shared()
        self.game = game
        self.level = level
        self.rng = random.Random(seed)
        self.max_hp = getattr(game, "akuma_max", AKUMA_MAX_HP)
        self.hp = self.max_hp if hp is None else hp
        self.menu = PauseMenu(game, CONTROLS)
        self.art = stage_art()
        roster = self.rng.sample(CPU_POOL, 3)
        self.fighters = [Smasher(self, "akuma", 0, True)] + [Smasher(self, c, i + 1)
                                                             for i, c in enumerate(roster)]
        self.akuma = self.fighters[0]
        for f, (x, y) in zip(self.fighters, SPAWNS):
            f.x, f.y = float(x), float(y)
            f.facing = 1 if x < 160 else -1
        self.brains = {f: Brain(self, f, random.Random(self.rng.random())) for f in self.fighters[1:]}
        self.cpu_enabled = True
        self.shots = []
        self.effects = []
        self.parts = []          # [x, y, vx, vy, life, color]
        self.blasts = []         # [x, y, angle, color, t]
        self.popups = []
        self._reach = {}
        self.phase = "intro"
        self.t = 0
        self.end_t = 0
        self.shake = 0
        self.flash = 0
        self.result = None
        self.won = None
        self.cloud_x = [20.0, 150.0, 250.0]
        for f in self.fighters:
            f.refresh()

    @property
    def paused(self):
        return self.menu.open

    @property
    def cpus(self):
        return self.fighters[1:]

    # ---- helpers used by fighters -----------------------------------------
    def reach(self, f, name):
        """How far forward of the feet a move's strike pixels reach (AI spacing)."""
        ck = (f.cid, name)
        r = self._reach.get(ck)
        if r is None:
            mv = f.moves[name]
            r = 0
            base = mv.get("base", "jump" if mv.get("air") else "idle")
            for kind, n, pose in mv["phases"]:
                if kind != "active" and not mv.get("grab"):
                    continue
                for key in f.art._anim(pose)[0]:
                    m, ox, oy = strike_mask(f.art, key, False, f.k, base, mv.get("zone", "front"),
                                            mv.get("box", (10, -40, 20, 14)))
                    _, (ax, _), _ = sprite(f.art, key, False, f.k)
                    for rc in m.get_bounding_rects():
                        r = max(r, ox + rc.right - ax)
            r += abs(mv.get("ev", {}).get(4, {}).get("vxf", 0)) * 8
            self._reach[ck] = r
        return r

    def spawn_shot(self, f, spec):
        self.shots.append(Shot(f, spec))

    def puff(self, x, y):
        self.effects.append(F.Effect(F.DUST, x, y - 3, 3))

    def embers(self, f):
        cx, cy = f.center
        for _ in range(2):
            self.parts.append([f.x + f.facing * self.rng.uniform(4, 14), cy - self.rng.uniform(0, 20),
                               self.rng.uniform(-0.5, 0.5), self.rng.uniform(-1.4, -0.4),
                               self.rng.randint(8, 16), self.rng.choice(((255, 220, 80), (255, 120, 30),
                                                                         (240, 60, 20)))])

    def shield_break(self, f):
        f.shield = 0
        f.state, f.t = "dizzy", 0
        f.vy = -3.0
        f.airborne = True
        audio.play("heavy")
        self.popups.append(["SHIELD BREAK!", f.x, f.y - f.hgt - 6, 60, f.color])

    def respawn(self, f):
        f.state, f.t = "respawn", 0
        f.x = 115.0 + f.slot * 30
        f.y = float(HALO_Y)
        f.vx = f.vy = f.lvx = f.lvy = 0.0
        f.pct = 0.0
        f.airborne = False
        f.jumps = 1
        f.upb_used = f.helpless = f.fastfall = False
        f.shield = SHIELD_MAX
        f.facing = 1 if f.x < 160 else -1
        f.move = None
        f.grabbed = f.held_by = None

    def drop_grab(self, att):
        v = att.grabbed
        att.grabbed = None
        if v is not None and v.state == "held":
            v.held_by = None
            v.state, v.t = ("air" if v.airborne else "stand"), 0

    def release_throw(self, att):
        v = att.grabbed
        att.grabbed = None
        if v is None or v.state != "held":
            return
        v.held_by = None
        v.state = "stand"
        th = att.move
        self._apply_hit(att, v, th, att.facing, (v.x, v.y - v.hgt / 2), grab_ok=True)

    # ---- hits ----------------------------------------------------------------
    def _apply_hit(self, att, vic, spec, dirx, point, grab_ok=False):
        """Returns 'hit', 'block' or None."""
        dmg = spec.get("dmg", 0)
        if vic.is_player and att is not None and not att.is_player:
            dmg = dmg * CPU_ON_AKUMA
        if vic.state == "shield" and not spec.get("grab"):
            vic.shield -= dmg * SHIELD_DMG_K + 1
            vic.lvx = dirx * min(3.0, 0.6 + dmg * 0.12)
            vic.hitstop = att.hitstop = 4 if att else 0
            self.effects.append(F.Effect(self.art["block"], point[0], point[1], 2))
            audio.play("block")
            if vic.shield <= 0:
                self.shield_break(vic)
            return "block"
        if spec.get("grab") and not grab_ok:
            # caught: the attacker goes into its throw
            att.grabbed = vic
            vic.held_by = att
            vic.state, vic.t = "held", 0
            vic.move = None
            vic.vx = vic.vy = vic.lvx = vic.lvy = 0.0
            if vic.grabbed:
                self.drop_grab(vic)
            th = spec["throw"]
            att.move = th
            att.move_t = 0
            att.move_vx = None
            th["ev"] = {th["release"]: dict(release=True, sound="heavy")}
            audio.play("hit")
            return "hit"
        vic.pct = min(MAX_PCT, vic.pct + dmg)
        kb = (spec["kb"] + spec["kg"] * vic.pct / 100.0) / vic.weight * self.rng.uniform(0.92, 1.08)
        crit = self.rng.random() < CRIT * (vic.pct / MAX_PCT) ** 2
        if crit:
            kb *= CRIT_K
        ang = spec["ang"]
        if not vic.airborne and ang < 0:
            ang = -ang * 0.4
        a = math.radians(ang)
        vic.lvx = math.cos(a) * kb * dirx
        vic.lvy = -math.sin(a) * kb
        vic.vx = 0.0
        if vic.lvy < -0.3 or vic.airborne:
            vic.airborne = True
            vic.vy = 0.0
        if vic.grabbed:
            self.drop_grab(vic)
        if vic.state == "move" and vic.move is not None:
            vic.move = None
            vic.move_vx = None
        vic.state, vic.t = "hitstun", 0
        vic.hitstun = int(kb * HITSTUN_K) + 4
        vic.tumble = kb > TUMBLE_KB
        vic.jumps = 1
        vic.upb_used = vic.helpless = vic.fastfall = False
        vic.flash = 8
        vic.dmg_shake = 16
        vic.last_hit_by = att
        vic.hit_t = self.t
        stop = min(16, 3 + int(dmg) // 2 + (5 if kb > 7 else 0))
        vic.hitstop = stop
        if att is not None:
            att.hitstop = stop
        if kb > 7 or crit:
            self.shake = max(self.shake, 8 if not crit else 14)
            audio.play("heavy")
        else:
            audio.play("hit")
        fx = self.art["smash"] if crit else (self.art["spark"] if dmg >= 7 else self.art["spark_small"])
        self.effects.append(F.Effect(fx, point[0], point[1], 3))
        if crit:
            self.popups.append(["SMASH!", vic.x, vic.y - vic.hgt - 8, 40, (255, 120, 40)])
        return "hit"

    def _hits(self):
        fs = [f for f in self.fighters if f.draw_key is not None]
        hurts = {f: f.hurt() for f in fs}
        for att in fs:
            if not att.striking():
                continue
            mv = att.move
            m, ox, oy = strike_mask(att.art, att.draw_key, att.flip, att.k,
                                    mv.get("base", "jump" if mv.get("air") else "idle"),
                                    mv.get("zone", "front"), mv.get("box", (10, -40, 20, 14)))
            sx, sy = att.draw_pos[0] + ox, att.draw_pos[1] + oy
            for vic in fs:
                if vic is att or hurts.get(vic) is None or att.state != "move":
                    continue
                last = att.victims.get(vic)
                if last is not None:
                    lt, n = last
                    if not mv.get("rehit") or att.move_t - lt < mv["rehit"] or n >= mv.get("hits", 1):
                        continue
                hm, (hx, hy) = hurts[vic]
                pt = hm.overlap(m, (sx - hx, sy - hy))
                if pt is None:
                    continue
                n = (last[1] + 1) if last else 1
                att.victims[vic] = (att.move_t, n)
                if mv.get("zone") in ("all", "body"):
                    dirx = sign(vic.x - att.x) or att.facing
                else:
                    dirx = att.facing
                res = self._apply_hit(att, vic, mv, dirx, (hx + pt[0], hy + pt[1]))
                hurts[vic] = vic.hurt()
                if res and mv.get("grab"):
                    break
        # projectiles
        for s in self.shots:
            if not s.alive:
                continue
            img, m, (px, py) = s.frame()
            for vic in fs:
                if vic is s.owner or hurts.get(vic) is None:
                    continue
                hm, (hx, hy) = hurts[vic]
                pt = hm.overlap(m, (px - hx, py - hy))
                if pt is not None:
                    s.alive = False
                    self._apply_hit(s.owner, vic, s.spec, s.dir, (hx + pt[0], hy + pt[1]))
                    s.owner.hitstop = 0
                    hurts[vic] = vic.hurt()
                    break
        live = [s for s in self.shots if s.alive]
        for i, a in enumerate(live):
            for b in live[i + 1:]:
                if a.owner is b.owner or not (a.alive and b.alive):
                    continue
                ia, ma, pa = a.frame()
                ib, mb, pb = b.frame()
                if ma.overlap(mb, (pb[0] - pa[0], pb[1] - pa[1])):
                    a.alive = b.alive = False
                    self.effects.append(F.Effect(self.art["block"], (a.x + b.x) / 2, (a.y + b.y) / 2, 3))
                    audio.play("block")

    def _holds(self):
        for f in self.fighters:
            v = f.grabbed
            if v is not None and v.state == "held":
                v.x = f.x + f.facing * f.hgt * 0.3
                v.y = f.y
                v.facing = -f.facing
                v.airborne = f.airborne

    def _separate(self):
        """Grounded fighters standing inside each other drift apart (no hard walls)."""
        fs = [f for f in self.fighters if f.on_field and not f.airborne
              and f.state not in ("held", "move", "hitstun")]
        for i, a in enumerate(fs):
            for b in fs[i + 1:]:
                dx = b.x - a.x
                if abs(dx) < 10 and abs(a.y - b.y) < 1:
                    push = 0.5 * (sign(dx) or (1 if a.slot < b.slot else -1))
                    for f, d in ((a, -push), (b, push)):
                        nx = f.x + d
                        if ground_at(nx, f.y) is not None and not any(_body_hits(nx, f.y, r) for r in SOLIDS):
                            f.x = nx

    def _blast_zones(self):
        for f in self.fighters:
            if f.out or f.state in ("dead", "respawn", "intro"):
                continue
            if f.x < BLAST_L or f.x > BLAST_R or f.y > BLAST_B or f.y < BLAST_T:
                self.ko(f)

    def ko(self, f):
        bx = max(0, min(W, f.x))
        by = max(0, min(H, f.y - f.hgt / 2))
        ang = math.atan2(H / 2 - by, W / 2 - bx)
        self.blasts.append([bx, by, ang, f.color, 0])
        for _ in range(26):
            a = ang + self.rng.uniform(-0.7, 0.7)
            sp = self.rng.uniform(1.5, 5)
            self.parts.append([bx, by, math.cos(a) * sp, math.sin(a) * sp, self.rng.randint(14, 30),
                               self.rng.choice((f.color, (255, 255, 255), (255, 230, 120)))])
        self.shake = 14
        self.flash = 4
        audio.play("boom")
        audio.play("ko", 0.7)
        if f.grabbed:
            self.drop_grab(f)
        if f.held_by is not None:
            f.held_by.grabbed = None
            f.held_by = None
        f.stocks -= 1
        if f.last_hit_by is not None and self.t - getattr(f, "hit_t", -9999) > 600:
            f.last_hit_by = None                 # a fall long after the last hit is a self-destruct
        if f.last_hit_by is not None:
            f.last_hit_by.ko_count += 1
        f.state, f.t = "dead", 0
        f.move = None
        f.draw_key = None
        f.last_hit_by = None
        if f.stocks <= 0:
            f.out = True

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
        for i in range(len(self.cloud_x)):
            self.cloud_x[i] = (self.cloud_x[i] + 0.06 * (i + 1)) % (W + 80)
        if self.phase == "intro":
            self.end_t += 1
            if self.end_t in (INTRO - 90, INTRO - 60, INTRO - 30):
                audio.play("beep")
            for f in self.fighters:
                f.refresh()
            if self.end_t >= INTRO:
                self.phase, self.end_t = "play", 0
                audio.play("fight")
                for f in self.fighters:
                    f.state, f.t = "stand", 0
            self._fx()
            return
        intents = {}
        if self.phase == "play":
            intents[self.akuma] = Intent.from_input(inp)
            if self.cpu_enabled:
                for f, b in self.brains.items():
                    intents[f] = b.think()
        for f in self.fighters:
            f.update(intents.get(f, NO_INPUT))
        self._holds()
        self._separate()
        for s in self.shots:
            s.update()
        for f in self.fighters:
            f.refresh()
        self._hits()
        self.shots = [s for s in self.shots if s.alive]
        self._blast_zones()
        self._fx()
        if self.phase == "play":
            if self.akuma.out:
                self.phase, self.end_t, self.won = "game", 0, False
                audio.play("ko")
            elif all(c.out for c in self.cpus):
                self.phase, self.end_t, self.won = "game", 0, True
                audio.play("encounter")
        elif self.phase == "game":
            self.end_t += 1
            ak = self.akuma
            if self.won and ak.state == "stand" and not ak.airborne and self.end_t > 30:
                ak.state, ak.t = "win", 0
                ak.vx = 0.0
            skip = self.end_t > 70 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= GAME_LEN or skip:
                if self.won:
                    self.result = "win"
                    hp = max(1, round(self.hp * (0.5 + 0.5 * ak.stocks / STOCKS)))
                    self.game.level_done(self, hp)
                else:
                    self.result = "lose"
                    self.game.level_failed(self)

    def _fx(self):
        for fx in self.effects:
            fx.update()
        self.effects = [fx for fx in self.effects if fx.alive]
        for p in self.parts:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.05
            p[4] -= 1
        self.parts = [p for p in self.parts if p[4] > 0]
        for b in self.blasts:
            b[4] += 1
        self.blasts = [b for b in self.blasts if b[4] < 40]
        for pu in self.popups:
            pu[3] -= 1
        self.popups = [pu for pu in self.popups if pu[3] > 0]

    # ---- draw ----------------------------------------------------------------
    def draw(self, surf):
        sh = (0, 0)
        if self.shake:
            m = 1 + self.shake // 5
            sh = (self.rng.randint(-m, m), self.rng.randint(-m, m))
        a = self.art
        surf.blit(a["bg"], (0, 0))
        for i, c in enumerate(a["clouds"]):
            surf.blit(c, (round(self.cloud_x[i]) - 70, 14 + i * 17))
        surf.blit(a["stage"], sh)
        for f in self.fighters:
            if f.state == "respawn":
                hx, hy = round(f.x) + sh[0], HALO_Y + sh[1]
                pygame.draw.ellipse(surf, OUTLINE, (hx - 15, hy - 2, 30, 7))
                pygame.draw.ellipse(surf, shade(f.color, 1.3), (hx - 14, hy - 1, 28, 5))
                pygame.draw.ellipse(surf, (255, 255, 255), (hx - 9, hy, 18, 2))
        order = sorted(self.fighters, key=lambda f: (f.is_player, f.state == "held"))
        for f in order:
            self._draw_fighter(surf, f, sh)
        for s in self.shots:
            img, _, (px, py) = s.frame()
            surf.blit(img, (px + sh[0], py + sh[1]))
        for fx in self.effects:
            fx.draw(surf, sh)
        for p in self.parts:
            surf.fill(p[5], (round(p[0]) + sh[0], round(p[1]) + sh[1], 2, 2))
        self._draw_blasts(surf)
        for f in self.fighters:
            self._tag(surf, f, sh)
        for text, x, y, n, col in self.popups:
            draw_text(surf, text, round(x), round(y) - (60 - n) // 5, col, align="center")
        if self.flash:
            fl = pygame.Surface((W, H), pygame.SRCALPHA)
            fl.fill((255, 255, 255, 90))
            surf.blit(fl, (0, 0))
        self._hud(surf)
        self._overlays(surf)
        if self.menu.open:
            self.menu.draw(surf)

    def _draw_fighter(self, surf, f, sh):
        if f.draw_key is None:
            return
        if f.state != "respawn":
            gy = surface_below(f.x, f.y)
            if gy is not None and gy - f.y < 60:
                w = max(8, round(f.half_w * 2.4 * (1 - (gy - f.y) / 90)))
                pygame.draw.ellipse(surf, (30, 26, 40), (round(f.x) - w // 2 + sh[0], gy - 2 + sh[1], w, 4))
        img, _, _ = sprite(f.art, f.draw_key, f.flip, f.k)
        x, y = f.draw_pos[0] + sh[0], f.draw_pos[1] + sh[1]
        if f.state == "roll" and f.t % 4 < 2:
            ghost = img.copy()
            ghost.set_alpha(130)
            surf.blit(ghost, (x, y))
        elif f.flash and f.flash % 4 >= 2:
            surf.blit(flash_of(f.art, f.draw_key, f.flip, f.k), (x, y))
        else:
            surf.blit(img, (x, y))
            if f.helpless:
                dk = img.copy()
                dk.fill((150, 150, 170, 255), special_flags=pygame.BLEND_RGBA_MULT)
                surf.blit(dk, (x, y))
            if (f.invuln or f.state == "respawn") and (self.t // 3) % 2:
                wh = flash_of(f.art, f.draw_key, f.flip, f.k).copy()
                wh.set_alpha(110)
                surf.blit(wh, (x, y))
        if f.state == "shield":
            r = f.shield_radius()
            cx, cy = f.center
            bub = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            hp = max(0.0, f.shield) / SHIELD_MAX
            col = mix((255, 60, 40), f.color, hp) if hp < 0.5 else f.color
            pygame.draw.circle(bub, col + (95,), (r + 1, r + 1), r)
            pygame.draw.circle(bub, shade(col, 1.5) + (200,), (r + 1, r + 1), r, 1)
            pygame.draw.circle(bub, (255, 255, 255, 150), (r + 1 - r // 3, r + 1 - r // 3), max(1, r // 5))
            surf.blit(bub, (round(cx) - r - 1 + sh[0], round(cy) - r - 1 + sh[1]))
        if f.state == "dizzy":
            for k in range(3):
                ang = self.t / 6 + k * math.tau / 3
                sx = round(f.x + math.cos(ang) * 9) + sh[0]
                sy = round(f.y - f.hgt - 4 + math.sin(ang) * 3) + sh[1]
                surf.fill((255, 230, 90), (sx - 1, sy, 3, 1))
                surf.fill((255, 230, 90), (sx, sy - 1, 1, 3))

    def _tag(self, surf, f, sh):
        if f.out or f.state == "dead" or self.phase == "intro":
            return
        label = "P1" if f.is_player else "CPU"
        top = f.y - f.hgt - 9
        x, y = f.x, top
        off = x < 0 or x > W or f.y < 0
        if off:
            cx = max(9, min(W - 9, x))
            cy = max(9, min(H - 40, f.y - f.hgt / 2))
            pygame.draw.circle(surf, OUTLINE, (round(cx), round(cy)), 8)
            pygame.draw.circle(surf, f.color, (round(cx), round(cy)), 7)
            surf.blit(small_portrait(f.cid, 10), (round(cx) - 5, round(cy) - 5))
            return
        y = max(2, y)
        draw_text(surf, label, round(x) + sh[0], round(y) + sh[1], f.color, align="center")
        tx, ty = round(x) + sh[0], round(y) + 8 + sh[1]
        pygame.draw.polygon(surf, f.color, [(tx - 2, ty), (tx + 2, ty), (tx, ty + 2)])

    def _draw_blasts(self, surf):
        if not self.blasts:
            return
        layer = pygame.Surface((W, H), pygame.SRCALPHA)
        for bx, by, ang, col, t in self.blasts:
            ln = min(190, 30 + t * 14)
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
        pw = 76
        y0 = H - 25
        for i, f in enumerate(self.fighters):
            x0 = 4 + i * 79
            panel = pygame.Surface((pw, 23), pygame.SRCALPHA)
            panel.fill((12, 10, 20, 170))
            surf.blit(panel, (x0, y0))
            pygame.draw.rect(surf, f.color if not f.out else (90, 90, 100), (x0, y0, pw, 23), 1)
            por = small_portrait(f.cid, 19)
            if f.out:
                por = por.copy()
                por.fill((90, 90, 90, 255), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(por, (x0 + 2, y0 + 2))
            draw_text(surf, f.name, x0 + 23, y0 + 2, f.color if not f.out else (120, 120, 130))
            for s in range(f.stocks):          # stock icons sit on top of the panel
                surf.blit(small_portrait(f.cid, 8), (x0 + 2 + s * 10, y0 - 10))
                pygame.draw.rect(surf, f.color, (x0 + 1 + s * 10, y0 - 11, 10, 10), 1)
            if f.out:
                draw_text(surf, "OUT", x0 + pw - 3, y0 + 12, (150, 150, 160), align="right")
                continue
            p = int(f.pct)
            jx = jy = 0
            if f.dmg_shake:
                jx = self.rng.randint(-1, 1)
                jy = self.rng.randint(-1, 1)
            text = "%d%%" % p
            draw_text(surf, text, x0 + pw - 3 + jx, y0 + 9 + jy, pct_color(p), scale=2, align="right")

    def _overlays(self, surf):
        cx = W // 2
        if self.phase == "intro":
            n = self.end_t
            if n < INTRO - 90:
                band = pygame.Surface((W, 44), pygame.SRCALPHA)
                band.fill((8, 6, 20, 180))
                surf.blit(band, (0, 30))
                draw_text(surf, "LEVEL %d" % self.level, cx, 34, (255, 220, 80), scale=2, align="center")
                draw_text(surf, LEVEL_NAME, cx, 52, (255, 255, 255), align="center")
                draw_text(surf, "3 STOCK FREE-FOR-ALL   HOLD I TO SHIELD", cx, 63, (180, 220, 255),
                          align="center")
            else:
                k = 3 - (n - (INTRO - 90)) // 30
                if k >= 1:
                    draw_text(surf, str(k), cx, 50, (255, 230, 90), scale=5, align="center")
        if self.phase == "play" and self.end_t == 0 and self.t < INTRO + 45:
            draw_text(surf, "GO!", cx, 46, (255, 70, 40), scale=5, align="center")
        if self.phase == "game":
            if self.end_t < 100:
                draw_text(surf, "GAME!", cx, 44, (255, 230, 80), scale=5, align="center")
            else:
                band = pygame.Surface((W, 30), pygame.SRCALPHA)
                band.fill((8, 6, 20, 190))
                surf.blit(band, (0, 50))
                if self.won:
                    draw_text(surf, "AKUMA WINS!", cx, 54, (255, 80, 60), scale=2, align="center")
                    draw_text(surf, "THE CHALLENGERS ARE SMASHED", cx, 70, (255, 255, 255), align="center")
                else:
                    draw_text(surf, "AKUMA FALLS...", cx, 54, (255, 255, 255), scale=2, align="center")
                    draw_text(surf, "OUT OF STOCKS", cx, 70, (255, 140, 120), align="center")
