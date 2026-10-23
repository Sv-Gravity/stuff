"""Level 6: a Smash Bros. style free-for-all at a little pixel Hyrule Castle.

Akuma and three challengers from Toshi's sprite pack fight on a wide castle
roof: a big main floor, a raised tower, and pass-through ledges spread out
over it. The camera pans and zooms so everyone stays in view. Hits add
damage % (0-200) instead of taking health; the higher it is, the further a
hit sends you and the likelier one strong blow launches you clean off the
stage. Fly past the blast zone (any side) and you lose a stock.

Two rounds of three stocks each. Akuma clears the level if he wins at least
one of the two rounds; losing both fails it.

Items drop onto the stage like in Smash:
  HOME-RUN BAT, BEAM SWORD: walk onto it and press PUNCH to pick it up, then
      PUNCH swings it (the bat's swing sends people flying).
  BOB-OMB: pick up with PUNCH, PUNCH throws it; it blows up on impact.
  HAMMER: pick up with PUNCH; it swings by itself for a few seconds and
      wrecks anyone it touches (no other attacks while you hold it).
  STAR (invincibility), HEART CONTAINER (-100%) and Japanese snacks from
      snacks.py (heal some damage %) are collected just by touching them.
  PUNCH+KICK together throws whatever you hold.
CPUs pick up and use items too.

Akuma's specials (game-wide scheme): SPECIAL alone = hadouken (in the air:
air fireball), SPECIAL+PUNCH = shoryuken (also his recovery), SPECIAL+KICK =
tatsumaki hurricane kick. "Together" is within 4 frames, in either order.
CPU fighters keep their own direction+special moves.

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
from .snacks import random_snack, heal_amount, snack_image

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
INTRO2 = 160            # the second round's (shorter) intro
GAME_LEN = 200          # GAME! + the round result
FINAL_LEN = 260         # the final tally
ROUNDS = 2
COMBO = 4               # frames within which two buttons count as pressed together
CPU_FOCUS = 0.6         # chance a CPU picks Akuma when it chooses a target
CPU_ON_AKUMA = 0.85     # CPU hits on Akuma do this much of their damage (3 on 1 is rough)
BODY_W, BODY_H = 6, 30  # terrain collision box (half width, height)

# --------------------------------------------------------------------------
# the stage: a world bigger than the screen; the camera pans and zooms over it
# --------------------------------------------------------------------------
WW, WH = 448, 252       # world size (same 16:9 shape as the canvas)
CAM_MIN_W = W           # never zoom in past 1:1
FLOOR_Y = 182
STAGE_L, STAGE_R = 70, 378
MID_X = (STAGE_L + STAGE_R) // 2
TOWER = pygame.Rect(292, 146, 52, 37)
SOLIDS = [pygame.Rect(STAGE_L, FLOOR_Y, STAGE_R - STAGE_L, 200), TOWER]
SOFTS = [(92, 148, 146), (178, 246, 110), (288, 348, 106)]    # x0, x1, y: drop-through
LEDGES = [(STAGE_L, FLOOR_Y, -1), (STAGE_R, FLOOR_Y, 1),
          (TOWER.left, TOWER.top, -1), (TOWER.right, TOWER.top, 1)]
SPAWNS = [(114, FLOOR_Y), (212, 110), (250, FLOOR_Y), (318, TOWER.top)]
HALO_Y = 70

BLAST_L, BLAST_R, BLAST_T, BLAST_B = -34, WW + 34, -60, WH + 40

SLOT_COLORS = [(232, 52, 44), (64, 110, 240), (240, 200, 40), (56, 190, 80)]
CPU_POOL = ["ryu", "ken", "sakura", "chunli", "zangief", "morrigan", "felicia", "hsienko", "drdoom"]
NAMES = {"akuma": "AKUMA", "ryu": "RYU", "ken": "KEN", "sakura": "SAKURA", "chunli": "CHUN-LI",
         "zangief": "ZANGIEF", "morrigan": "MORRIGAN", "felicia": "FELICIA", "hsienko": "HSIEN-KO",
         "drdoom": "DR. DOOM"}

CONTROLS = [
    "LEFT / RIGHT: MOVE   UP: JUMP (TWICE)",
    "DOWN: CROUCH / DROP THROUGH A LEDGE",
    "J: JAB   K: KICK   DOWN+K: SWEEP",
    "AIR: J / K ATTACKS, DOWN+K: DIVE KICK",
    "L: HADOUKEN   L+J: SHORYUKEN (RECOVER)",
    "L+K: HURRICANE KICK",
    "HOLD I: SHIELD  I+LEFT/RIGHT: ROLL",
    "I+J OR J+K: GRAB",
    "ITEMS: J ON ONE TO PICK UP, J TO USE",
    "J+K: THROW ITEM. FOOD/STAR: TOUCH",
    "2 ROUNDS OF 3 STOCKS: WIN ONE TO CLEAR",
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


def _drdoom():
    m = normals(p=1.1, k=1.05)
    m.update(neutral=_hado(3.0, 9, 2.0, 2.8, x=34, y=-40, prep=6),
             up=_sho(11, 3.0, 5.4, -6.8, vx=1.0),
             down=M([("s", 6, "tatsu_start"), ("a", 24, "lariat_b"), ("r", 10, "tatsu_end")], 4, 2.2, 3.0, 45,
                    zone="all", rehit=7, hits=3, box=(-36, -56, 72, 52), ev={5: dict(sound="fireball")}))
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
    "drdoom": dict(weight=1.2, walk=1.5, air=1.6, jump=-5.3, djump=-5.0, grav=1.0, moves=_drdoom(),
                   ai=dict(aggr=0.6, block=0.45, react=12)),
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
        self.item = None           # the Item held, if any
        self.star = 0              # frames of star invincibility left
        self.since = {"special": 99, "punch": 99, "kick": 99}   # frames since each press

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
        if self.invuln or self.star or self.state in ("dead", "respawn", "held", "intro") or self.out:
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
        if btn == "sho":                 # Akuma: special+punch
            name = "up"
        elif btn == "tatsu":             # Akuma: special+kick
            name = "down"
        elif btn == "pk":                # punch+kick: grab (on the ground)
            name = "nair" if air else "grab"
        elif btn == "special" and self.is_player:   # Akuma: special alone, whatever the stick says
            name = "airneutral" if air and "airneutral" in Mv else "neutral"
        elif btn == "special":
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

    def start_move(self, name, mv=None):
        mv = mv or self.moves[name]
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
        if self.star:
            self.star -= 1
        # remember presses so a button pushed a few frames early still comes out
        cmd = self._player_command(it) if self.is_player else None
        if cmd:
            self.buf = (cmd, it.up, it.down, 8)
        elif not self.is_player and (it.special or it.punch or it.kick):
            btn = "special" if it.special else ("punch" if it.punch else "kick")
            self.buf = (btn, it.up, it.down, 8)
        elif self.buf:
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

    CANCELABLE = ("neutral", "airneutral", "jab", "crjab", "kick", "sweep", "nair", "fair", "dair")

    def _player_command(self, it):
        """Akuma's buttons -> a command: special alone = hadouken, special+punch
        = shoryuken, special+kick = hurricane kick, punch+kick = grab/throw.
        Two presses within COMBO frames (either order) count as together; a
        move the first press already started is swapped for the combo."""
        sn = self.since
        for b in sn:
            sn[b] = min(99, sn[b] + 1)
        for b in ("special", "punch", "kick"):
            if getattr(it, b):
                sn[b] = 0
        if not (it.special or it.punch or it.kick):
            return None
        if sn["special"] <= COMBO:
            if sn["punch"] <= COMBO and (it.special or it.punch):
                cmd = "sho"
            elif sn["kick"] <= COMBO and (it.special or it.kick):
                cmd = "tatsu"
            else:
                cmd = "special"
        elif sn["punch"] <= COMBO and sn["kick"] <= COMBO:
            cmd = "pk"
        else:
            cmd = "punch" if it.punch else "kick"
        if cmd in ("sho", "tatsu", "pk") and self.state == "move" and self.move_t <= COMBO \
                and self.move_name in self.CANCELABLE and not self.grabbed:
            ok = (self.item is not None and cmd == "pk") or \
                self.pick_move(cmd, it.up, it.down) is not None
            if ok:                      # swap the move the first button started for the combo
                if self.move.get("upb"):
                    self.upb_used = False
                self.move = None
                self.move_vx = None
                self.state, self.t = ("air" if self.airborne else "stand"), 0
                self.sc.cancel_shots(self)
        return cmd

    def _consume_attack(self, it):
        if not self.buf:
            return False
        btn, up, down, _ = self.buf
        if self.helpless:
            return False
        if self.sc.item_action(self, btn, up, down, it):
            self.buf = None
            return True
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
            self.vx = d * self.walk * (0.8 if self.item and self.item.kind == "hammer" else 1.0)
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
            if self.jbuf and self.jumps > 0 and not (self.item and self.item.kind == "hammer"):
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
        if self.t >= self.life or not (-40 < self.x < WW + 40) or self.y > WH + 20:
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
        self.goal = None          # an item it is walking over to
        self.goal_t = 0

    def think(self):
        it = self._think()
        me = self.me
        if me.item is not None and me.item.kind == "bomb" and it.punch and not getattr(self, "_bomb_ok", False):
            it.punch, it.kick = False, True     # don't blow yourself up at point blank
        self._bomb_ok = False
        return it

    def _think(self):
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
        if self._items(it, t):
            return it
        if t is None:
            d = sign(MID_X - me.x) if abs(MID_X - me.x) > 20 else 0
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

    def _items(self, it, t):
        """Grab, eat and use items: walk over to a nearby one, pick it up with
        punch, lob a held bob-omb at someone a little way off."""
        me, rng, sc = self.me, self.rng, self.sc
        if me.state not in ("stand", "air"):
            return False
        held = me.item
        if held is not None:
            self.goal = None
            if held.kind == "bomb" and t is not None and not me.airborne and self.cool < 20:
                dx = t.x - me.x
                if 34 < abs(dx) < 150 and abs(t.y - me.y) < 40 and rng.random() < 0.12:
                    it.left, it.right = dx < 0, dx > 0
                    it.punch = True
                    if t.y < me.y - 20:
                        it.up = True
                    self._bomb_ok = True
                    self.cool = rng.randint(20, 40)
                    return True
            return False
        if me.airborne:
            return False
        if self.goal is not None and (self.goal not in sc.items or self.goal.state not in ("ground", "fall")
                                      or self.goal_t <= 0):
            self.goal = None
        if self.goal is None:
            best, bd = None, 9999
            for item in sc.items:
                if item.state != "ground" and item.kind != "star":
                    continue
                k = item.kind
                if k == "food" and me.pct < 15 or k == "heart" and me.pct < 40:
                    continue
                d = abs(item.x - me.x) + 2 * abs(item.y - me.y)
                rng_ok = 200 if k in ("star", "heart", "hammer") else 130
                if d < rng_ok and d < bd:
                    best, bd = item, d
            if best is None or (t is not None and abs(t.x - me.x) < 30 and rng.random() < 0.7):
                return False
            self.goal, self.goal_t = best, 240
        self.goal_t -= 1
        g = self.goal
        dx = g.x - me.x
        dy = g.y - me.y
        if abs(dx) <= 9 and abs(dy) < 3:
            if g.pickable:
                it.punch = True
                self.goal = None
            return True
        if dy < -10 and abs(dx) < 50 and rng.random() < 0.15:
            it.up_p = it.up = True
        elif dy > 10 and on_soft(me.x, me.y) and abs(dx) < 60 and rng.random() < 0.2:
            it.down_p = it.down = True
            return True
        it.left, it.right = dx < 0, dx > 0
        for r in SOLIDS[1:]:
            if _body_hits(me.x + sign(dx) * 6, me.y, r):
                it.up_p = it.up = True
        return True

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
        elif name in ("down", "up"):
            self._special(it, name)
        else:
            it.special = True
        self.cool = int(rng.randint(18, 50) * (1.4 - self.aggr))
        return True

    def _recover(self, it):
        me = self.me
        side = -1 if me.x < MID_X else 1
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
            self._special(it, "up")
        elif (me.jumps == 0 and me.upb_used is False and dx > 60 and dy < -10
              and me.moves.get("down", {}).get("recover")):
            self._special(it, "down")
        return it

    def _special(self, it, which):
        """Up/down special: CPUs use direction+special; Akuma (when the bot
        drives him) uses his own special+punch / special+kick buttons."""
        it.special = True
        if self.me.is_player:
            if which == "up":
                it.punch = True
            else:
                it.kick = True
        elif which == "up":
            it.up = True
        else:
            it.down = True

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
    DY = FLOOR_Y - 130                      # the scenery was laid out for a floor at y=130
    bg = pygame.Surface((WW, WH))
    for y in range(WH):
        bg.fill(mix(SKY_TOP, SKY_BOT, y / WH), (0, y, WW, 1))
    rng = random.Random(64)
    # far mountains
    pts = [(0, WH)]
    x = 0
    while x <= WW:
        pts.append((x, 104 + DY + rng.randint(-18, 8)))
        x += rng.randint(14, 30)
    pts += [(WW, WH)]
    pygame.draw.polygon(bg, (132, 162, 196), pts)
    # distant castle silhouettes and hills
    sil = (112, 136, 174)
    for tx, tw, th in ((10, 10, 54), (24, 22, 34), (48, 8, 46), (392, 10, 50), (406, 24, 30), (432, 8, 42)):
        bg.fill(sil, (tx, 122 + DY - th, tw, th + 20))
        pygame.draw.polygon(bg, (98, 122, 162), [(tx - 2, 122 + DY - th), (tx + tw // 2, 122 + DY - th - 12),
                                                 (tx + tw + 1, 122 + DY - th)])
    pts = [(0, WH)]
    x = 0
    while x <= WW:
        pts.append((x, 124 + DY + int(6 * math.sin(x / 23.0)) + rng.randint(-2, 2)))
        x += 8
    pts += [(WW, WH)]
    pygame.draw.polygon(bg, (82, 150, 104), pts)
    for x in range(0, WW, 5):               # tree line
        hgt = rng.randint(3, 7)
        pygame.draw.circle(bg, (56, 120, 82), (x, 128 + DY - hgt // 2 + int(6 * math.sin(x / 23.0))), hgt // 2 + 2)
    bg.fill((60, 126, 86), (0, 132 + DY, WW, WH - 132 - DY))

    st = pygame.Surface((WW, WH), pygame.SRCALPHA)
    # background keeps behind the two stone balconies (scenery, not solid)
    for (x0, x1, y), shadek in zip(SOFTS[:2], (0.82, 0.74)):
        rect = (x0 + 4, y + 4, x1 - x0 - 8, FLOOR_Y - y - 4)
        _bricks(st, rect, shade(STONE, shadek), shade(STONE_LT, shadek), shade(STONE_DK, shadek),
                shade(MORTAR, shadek), seed=x0)
        cx = (x0 + x1) // 2
        _arch_window(st, cx - 4, y + 10, 8, 13, rim=shade(STONE_LT, shadek))
        if FLOOR_Y - y > 50:
            _arch_window(st, cx - 4, y + 36, 8, 13, rim=shade(STONE_LT, shadek))
    # tower roof pillars
    for px in (TOWER.left + 3, TOWER.right - 6):
        _bricks(st, (px, SOFTS[2][2] + 4, 3, TOWER.top - SOFTS[2][2] - 4), shade(STONE, 0.8),
                STONE, STONE_DK, MORTAR, row=4, brick=3, seed=px)
    # main castle block
    body = pygame.Rect(STAGE_L, FLOOR_Y, STAGE_R - STAGE_L, WH - FLOOR_Y)
    _bricks(st, body, STONE, STONE_LT, STONE_DK, MORTAR, seed=3)
    for bx in (STAGE_L, STAGE_R - 8):       # corner buttresses
        st.fill(STONE_DK, (bx, FLOOR_Y + 3, 8, WH))
        st.fill(shade(STONE_DK, 1.15), (bx + 1, FLOOR_Y + 3, 2, WH))
    gx = MID_X - 14                          # the gate
    _arch_window(st, gx, FLOOR_Y + 12, 28, 40)
    for xx in range(gx + 3, gx + 28, 5):
        st.fill((70, 64, 76), (xx, FLOOR_Y + 22, 1, 40))
    for wx in (STAGE_L + 22, STAGE_L + 50, STAGE_L + 78, STAGE_R - 86, STAGE_R - 58, STAGE_R - 30):
        _arch_window(st, wx, FLOOR_Y + 12, 8, 14)
    # vines
    for vx in (STAGE_L + 14, STAGE_R - 40, gx + 34, STAGE_L + 66):
        for k in range(rng.randint(10, 26)):
            st.fill((52, 128, 72) if k % 3 else (84, 164, 92), (vx + int(2 * math.sin(k / 2.0)), FLOOR_Y + 3 + k, 2, 1))
    # floor surface
    st.fill(OUTLINE, (STAGE_L - 1, FLOOR_Y - 1, STAGE_R - STAGE_L + 2, 1))
    st.fill(STONE_LT, (STAGE_L, FLOOR_Y, STAGE_R - STAGE_L, 3))
    st.fill((236, 230, 218), (STAGE_L, FLOOR_Y, STAGE_R - STAGE_L, 1))
    st.fill(OUTLINE, (STAGE_L - 1, FLOOR_Y, 1, WH))
    st.fill(OUTLINE, (STAGE_R, FLOOR_Y, 1, WH))
    # tower
    _bricks(st, TOWER, STONE, STONE_LT, STONE_DK, MORTAR, seed=9)
    for k in range(5):                     # crenellations behind the walkway
        st.fill(shade(STONE, 0.78), (TOWER.left + 2 + k * 11, TOWER.top - 5, 6, 5))
    st.fill(STONE_LT, (TOWER.left, TOWER.top, TOWER.w, 3))
    st.fill((236, 230, 218), (TOWER.left, TOWER.top, TOWER.w, 1))
    pygame.draw.rect(st, OUTLINE, TOWER.inflate(2, 2), 1)
    _arch_window(st, TOWER.centerx - 4, TOWER.top + 8, 8, 14)
    for bx in (TOWER.left + 6, TOWER.right - 12):                          # banners
        st.fill((176, 30, 40), (bx, TOWER.top + 5, 6, 16))
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
    clouds = [_cloud(56, 18, 1), _cloud(40, 14, 2), _cloud(70, 22, 3), _cloud(48, 16, 4)]
    _STAGE = dict(bg=bg, stage=st, clouds=clouds,
                  spark=F.SPARK_HIT, spark_small=[pygame.transform.scale_by(f, 0.6) for f in F.SPARK_HIT],
                  block=F.SPARK_BLOCK, smash=make_spark((255, 90, 40)),
                  boom=[pygame.transform.scale_by(f, 1.6) for f in make_spark((255, 200, 60))])
    return _STAGE


# --------------------------------------------------------------------------
# items: they drop onto the stage every few seconds, Smash style
# --------------------------------------------------------------------------
ITEM_EVERY = (300, 520)     # frames between drops
ITEM_MAX = 3                # at most this many lying around
ITEM_LIFE = 15 * 60         # a dropped item fades after this long
HAMMER_TIME = 8 * 60
STAR_TIME = 8 * 60
# kind: (display name, drop weight, picked up with punch?)
ITEM_KINDS = {
    "bat": ("HOME-RUN BAT", 2, True),
    "sword": ("BEAM SWORD", 2, True),
    "bomb": ("BOB-OMB", 3, True),
    "hammer": ("HAMMER", 1, True),
    "star": ("STAR", 1, False),
    "heart": ("HEART CONTAINER", 1, False),
    "food": ("FOOD", 5, False),
}
# swings of the held melee items (hit with a box in front, `reach` px long)
SWINGS = {
    "bat": M([("s", 12, "kick_prep"), ("a", 5, "punch"), ("r", 16, "punch_rec")], 18, 6.0, 9.0, 40,
             item="bat", reach=32),
    "sword": M([("s", 4, "punch_prep"), ("a", 6, "punch"), ("r", 10, "punch_rec")], 11, 2.6, 5.4, 40,
               item="sword", reach=38),
}
TOSS = M([("s", 3, "punch_prep"), ("r", 12, "punch_rec")])
PICKUP = M([("r", 8, "crouch")])
HAMMER_HIT = dict(dmg=16, kb=4.4, kg=7.2, ang=55, item="hammer")
BOMB_HIT = dict(dmg=20, kb=4.8, kg=7.6, ang=58)
BOMB_R = 26
THROWN_HIT = dict(dmg=9, kb=2.6, kg=4.2, ang=40)
STAR_COLORS = [(255, 80, 80), (255, 200, 60), (120, 240, 90), (80, 200, 255), (200, 120, 255)]

_ITEM_IMG = {}
_ITEM_ROT = {}
_RECTS = {}


def _outline(img):
    m = pygame.mask.from_surface(img, 1)
    w, h = img.get_size()
    edge = []
    for y in range(h):
        for x in range(w):
            if m.get_at((x, y)):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and m.get_at((nx, ny)):
                    edge.append((x, y))
                    break
    for p in edge:
        img.set_at(p, OUTLINE)
    return img


def _draw_bat():
    s = pygame.Surface((21, 7), pygame.SRCALPHA)
    s.fill((96, 58, 30), (1, 2, 3, 3))            # knob
    s.fill((132, 80, 40), (3, 3, 8, 2))           # grip
    s.fill((168, 108, 56), (3, 3, 8, 1))
    s.fill((222, 184, 118), (10, 2, 9, 4))        # barrel
    s.fill((246, 222, 170), (11, 2, 7, 1))
    s.fill((178, 136, 80), (10, 5, 9, 1))
    s.fill((222, 184, 118), (19, 3, 1, 2))        # rounded tip
    s.fill((210, 40, 40), (15, 2, 1, 4))          # red stripe
    return _outline(s)


def _draw_sword():
    s = pygame.Surface((24, 7), pygame.SRCALPHA)
    s.fill((150, 150, 172), (1, 2, 6, 3))         # hilt
    s.fill((200, 200, 220), (1, 2, 6, 1))
    s.fill((84, 84, 104), (7, 1, 2, 5))           # guard
    s.fill((110, 230, 255), (9, 1, 13, 5))        # beam glow
    s.fill((240, 252, 255), (9, 2, 13, 3))        # beam core
    s.fill((110, 230, 255), (22, 2, 1, 3))
    return _outline(s)


def _draw_hammer():
    s = pygame.Surface((22, 13), pygame.SRCALPHA)
    s.fill((150, 96, 48), (1, 5, 12, 3))          # handle
    s.fill((190, 130, 70), (1, 5, 12, 1))
    s.fill((176, 112, 56), (12, 1, 8, 11))        # head
    s.fill((214, 160, 96), (12, 1, 8, 2))
    s.fill((214, 160, 96), (12, 1, 2, 11))
    s.fill((128, 78, 36), (12, 10, 8, 2))
    s.fill((96, 58, 30), (15, 1, 1, 11))          # bands
    s.fill((96, 58, 30), (18, 1, 1, 11))
    return _outline(s)


def _draw_bomb():
    s = pygame.Surface((13, 15), pygame.SRCALPHA)
    pygame.draw.circle(s, (34, 34, 46), (6, 8), 5)
    s.fill((96, 96, 128), (3, 5, 2, 2))           # shine
    s.fill((250, 250, 250), (6, 6, 1, 3))         # eyes
    s.fill((250, 250, 250), (8, 6, 1, 3))
    s.fill((200, 190, 160), (6, 1, 1, 2))         # fuse
    s.fill((240, 190, 60), (3, 13, 3, 1))         # feet
    s.fill((240, 190, 60), (7, 13, 3, 1))
    s.fill((180, 180, 196), (0, 7, 1, 3))         # wind-up key
    return _outline(s)


def _draw_star():
    s = pygame.Surface((15, 15), pygame.SRCALPHA)
    pts = []
    for k in range(10):
        r = 6.6 if k % 2 == 0 else 2.9
        a = -math.pi / 2 + k * math.pi / 5
        pts.append((7 + math.cos(a) * r, 7.5 + math.sin(a) * r))
    pygame.draw.polygon(s, (255, 214, 40), pts)
    s.fill((255, 246, 170), (6, 4, 2, 2))
    s.fill((60, 40, 20), (6, 7, 1, 2))            # eyes
    s.fill((60, 40, 20), (8, 7, 1, 2))
    return _outline(s)


def _draw_heart():
    s = pygame.Surface((13, 12), pygame.SRCALPHA)
    gold, red = (240, 200, 60), (226, 36, 56)
    for col, r, inset in ((gold, 3, 0), (red, 2, 1)):
        pygame.draw.circle(s, col, (4, 4), r)
        pygame.draw.circle(s, col, (8, 4), r)
        pygame.draw.polygon(s, col, [(1 + inset, 5), (11 - inset, 5), (6, 10 - inset)])
    s.fill((255, 150, 160), (3, 3, 1, 1))
    return _outline(s)


_DRAWERS = {"bat": _draw_bat, "sword": _draw_sword, "hammer": _draw_hammer, "bomb": _draw_bomb,
            "star": _draw_star, "heart": _draw_heart}


def item_image(kind, snack=None):
    if kind == "food":
        return snack_image(snack or "ONIGIRI")
    img = _ITEM_IMG.get(kind)
    if img is None:
        img = _ITEM_IMG[kind] = _DRAWERS[kind]()
    return img


def item_rotated(kind, flip, ang):
    """A held weapon drawn horizontally (handle on the left) turned to `ang` degrees."""
    ang = int(round(ang / 10.0)) * 10
    ck = (kind, flip, ang)
    img = _ITEM_ROT.get(ck)
    if img is None:
        img = item_image(kind)
        if flip:
            img = pygame.transform.flip(img, True, False)
        img = _ITEM_ROT[ck] = pygame.transform.rotate(img, -ang if flip else ang)
    return img


def rect_mask(w, h):
    ck = (w, h)
    m = _RECTS.get(ck)
    if m is None:
        m = _RECTS[ck] = pygame.Mask((max(1, w), max(1, h)), fill=True)
    return m


class Item:
    """An item on the stage: falling, lying on the ground, held or thrown.
    (x, y) is the bottom centre, like a fighter's feet."""

    def __init__(self, kind, x, y, snack=None):
        self.kind = kind
        self.snack = snack
        self.name = snack if kind == "food" else ITEM_KINDS[kind][0]
        self.pickable = ITEM_KINDS[kind][2]
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = 0.0, 0.0
        self.state = "fall"        # fall | ground | held | thrown | gone
        self.holder = None
        self.owner = None          # who threw it
        self.life = ITEM_LIFE
        self.timer = HAMMER_TIME if kind == "hammer" else 0
        self.victims = {}
        self.t = 0
        if kind == "star":
            self.vx = 1.1

    @property
    def gone(self):
        return self.state == "gone"

    def image(self):
        return item_image(self.kind, self.snack)

    def center(self):
        return self.x, self.y - self.image().get_height() / 2

    def land_y(self, py):
        """The surface the item fell onto this frame, if any."""
        land = None
        for r in SOLIDS:
            if r.left <= self.x <= r.right and py <= r.top + 0.01 and self.y >= r.top:
                land = r.top if land is None else min(land, r.top)
        for x0, x1, yy in SOFTS:
            if x0 <= self.x <= x1 and py <= yy + 0.01 and self.y >= yy:
                land = yy if land is None else min(land, yy)
        return land

    def in_wall(self):
        cx, cy = self.center()
        return any(r.collidepoint(cx, cy) for r in SOLIDS)


# --------------------------------------------------------------------------
# a few sounds of our own (built lazily from audio's synth helpers)
# --------------------------------------------------------------------------
_MYSFX = {}


def sfx(name, vol=1.0):
    if not getattr(audio, "_ok", False):
        audio.play({"bat": "heavy", "star": "pickup", "eat": "pickup", "drop": "beep"}.get(name, name), vol)
        return
    s = _MYSFX.get(name)
    if s is None:
        try:
            if name == "bat":            # the home-run "ping"
                smp = audio._add(audio._tone(1900, 1500, 0.35, 0.3, "tri"), audio._noise(0.12, 0.5, 2.0, 0.6))
            elif name == "star":
                smp = []
                for f in (523, 659, 784, 1047, 784, 1047):
                    smp += audio._tone(f, f, 0.07, 0.22, "square", 0, 0.25)
            elif name == "eat":
                smp = audio._tone(500, 900, 0.07, 0.25, "square", 0, 0.5) + audio._tone(700, 1300, 0.09, 0.25,
                                                                                         "square", 0, 0.5)
            elif name == "drop":
                smp = audio._tone(1200, 1500, 0.05, 0.12, "tri") + audio._tone(1500, 1800, 0.05, 0.12, "tri")
            else:
                return audio.play(name, vol)
            s = _MYSFX[name] = audio._sound(smp)
        except Exception:
            _MYSFX[name] = s = False
    if s:
        s.set_volume(vol)
        s.play()


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
        self.roster = self.rng.sample(CPU_POOL, 3)
        self.cpu_enabled = True
        self.items_enabled = True
        self.round = 1
        self.round_wins = []         # True/False per finished round (Akuma's view)
        self.round_stocks = []       # Akuma's stocks left at the end of each round
        self._reach = {}
        self.t = 0
        self.result = None
        self.cloud_x = [20.0, 150.0, 250.0, 380.0]
        self.world = pygame.Surface((WW, WH))
        self.cam = [MID_X, (FLOOR_Y - 40.0), float(WW)]      # centre x, centre y, width
        self.fighters = []
        self._start_round()
        self.cam = self._cam_target()

    def _start_round(self):
        """Fresh fighters (same roster) on their spawn spots, stage cleared."""
        cast = ["akuma"] + list(self.roster)
        if [f.cid for f in self.fighters] == cast:
            for f in self.fighters:              # reset in place: the same objects stay in play
                f.__init__(self, f.cid, f.slot, f.is_player)
        else:
            self.fighters = [Smasher(self, c, i, i == 0) for i, c in enumerate(cast)]
        self.akuma = self.fighters[0]
        for f, (x, y) in zip(self.fighters, SPAWNS):
            f.x, f.y = float(x), float(y)
            f.facing = 1 if x < MID_X else -1
        self.brains = {f: Brain(self, f, random.Random(self.rng.random())) for f in self.fighters[1:]}
        self.shots = []
        self.items = []
        self.effects = []
        self.parts = []          # [x, y, vx, vy, life, color]
        self.blasts = []         # [x, y, angle, color, t]
        self.booms = []          # [x, y, r, t]
        self.popups = []         # [text, x, y, frames, color] in world coords
        self.phase = "intro"
        self.end_t = 0
        self.shake = 0
        self.flash = 0
        self.won = None
        self.item_t = self.rng.randint(*ITEM_EVERY) // 2
        for f in self.fighters:
            f.refresh()

    @property
    def intro_len(self):
        return INTRO if self.round == 1 else INTRO2

    @property
    def paused(self):
        return self.menu.open

    @property
    def cpus(self):
        return self.fighters[1:]

    @property
    def rounds_won(self):
        return sum(1 for w in self.round_wins if w)

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

    def cancel_shots(self, f):
        """A fireball started on the frame before a combo press is taken back."""
        self.shots = [s for s in self.shots if not (s.owner is f and s.t <= COMBO)]

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
        f.x = MID_X - 60.0 + f.slot * 40
        f.y = float(HALO_Y)
        f.vx = f.vy = f.lvx = f.lvy = 0.0
        f.pct = 0.0
        f.airborne = False
        f.jumps = 1
        f.upb_used = f.helpless = f.fastfall = False
        f.shield = SHIELD_MAX
        f.facing = 1 if f.x < MID_X else -1
        f.move = None
        f.grabbed = f.held_by = None
        f.star = 0

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

    # ---- items -------------------------------------------------------------
    def spawn_item(self, kind=None, x=None, y=-12.0, snack=None):
        if kind is None:
            kinds = list(ITEM_KINDS)
            kind = self.rng.choices(kinds, weights=[ITEM_KINDS[k][1] for k in kinds])[0]
        if kind == "food" and snack is None:
            snack = random_snack(self.rng)
        if x is None:
            spots = [(STAGE_L + 14, STAGE_R - 14, 3)] + [(x0 + 6, x1 - 6, 1) for x0, x1, _ in SOFTS] + \
                    [(TOWER.left + 6, TOWER.right - 6, 1)]
            x0, x1, _ = self.rng.choices(spots, weights=[w for _, _, w in spots])[0]
            x = self.rng.uniform(x0, x1)
        item = Item(kind, x, y, snack)
        if kind == "star":
            item.vx = self.rng.choice((-1.1, 1.1))
        self.items.append(item)
        return item

    def item_at(self, f):
        best = None
        for item in self.items:
            if item.state == "ground" and item.pickable and abs(item.x - f.x) <= 14 and abs(item.y - f.y) < 4:
                if best is None or abs(item.x - f.x) < abs(best.x - f.x):
                    best = item
        return best

    def pickup(self, f, item):
        item.state, item.holder, item.owner = "held", f, None
        item.vx = item.vy = 0.0
        f.item = item
        sfx("pickup", 0.6)
        if item.kind == "hammer":
            item.timer = HAMMER_TIME
            self.popups.append(["HAMMER!", f.x, f.y - f.hgt - 6, 50, (255, 200, 90)])

    def drop_item(self, f, gone=False):
        item = f.item
        f.item = None
        if item is None:
            return
        item.holder = None
        if gone or item.kind == "hammer":
            item.state = "gone"
        else:
            item.state = "fall"
            item.vx, item.vy = 0.0, -1.0

    def throw_item(self, f, up, down):
        item = f.item
        f.item = None
        item.holder = None
        item.owner = f
        item.victims = {}
        hx, hy = self._hand(f)
        item.x, item.y = hx, hy + 4
        if up:
            item.vx, item.vy = f.facing * 1.2, -6.4
        elif down and f.airborne:
            item.vx, item.vy = 0.0, 5.0
        else:
            item.vx, item.vy = f.facing * 4.4 + f.vx * 0.4, -1.8
        item.state = "thrown"
        item.t = 0
        f.start_move("toss", TOSS)
        audio.play("whiff", 0.7)

    def item_action(self, f, btn, up, down, it):
        """Items take over the punch button: pick up, swing, throw. True if used."""
        held = f.item
        if held is not None:
            if held.kind == "hammer":
                return btn in ("punch", "kick", "special", "pk", "sho", "tatsu")
            if btn == "pk" or (btn == "punch" and held.kind == "bomb"):
                if it.dir:
                    f.facing = it.dir
                self.throw_item(f, up, down)
                return True
            if btn == "punch" and held.kind in SWINGS:
                if it.dir:
                    f.facing = it.dir
                f.start_move("item", SWINGS[held.kind])
                return True
            return False
        if btn == "punch" and not f.airborne:
            item = self.item_at(f)
            if item is not None:
                self.pickup(f, item)
                f.start_move("pickup", PICKUP)
                return True
        return False

    def collect(self, f, item):
        item.state = "gone"
        k = item.kind
        if k == "star":
            f.star = STAR_TIME
            sfx("star", 0.7)
            self.popups.append(["STAR!", f.x, f.y - f.hgt - 6, 60, (255, 230, 80)])
        elif k == "heart":
            got = min(100, int(f.pct))
            f.pct = max(0.0, f.pct - 100)
            sfx("eat", 0.7)
            self.popups.append(["HEART -%d%%" % got, f.x, f.y - f.hgt - 6, 70, (255, 110, 130)])
        else:
            heal = heal_amount(item.snack, 100)
            f.pct = max(0.0, f.pct - heal)
            sfx("eat", 0.7)
            self.popups.append(["%s -%d%%" % (item.snack, heal), f.x, f.y - f.hgt - 6, 70, (140, 255, 140)])
        for _ in range(8):
            self.parts.append([item.x, item.y - 5, self.rng.uniform(-1.2, 1.2), self.rng.uniform(-2, -0.5),
                               self.rng.randint(10, 20), self.rng.choice(((255, 255, 255), (255, 230, 120)))])

    def explode(self, item):
        item.state = "gone"
        if item.holder is not None:
            item.holder.item = None
            item.holder = None
        cx, cy = item.center()
        self.booms.append([cx, cy, BOMB_R, 0])
        for _ in range(24):
            a = self.rng.uniform(0, math.tau)
            sp = self.rng.uniform(1.0, 4.0)
            self.parts.append([cx, cy, math.cos(a) * sp, math.sin(a) * sp, self.rng.randint(12, 26),
                               self.rng.choice(((255, 240, 160), (255, 160, 40), (240, 70, 30), (70, 60, 60)))])
        self.shake = max(self.shake, 12)
        audio.play("boom")
        owner = item.owner
        cm = circle_mask(BOMB_R)
        for vic in self.fighters:
            h = vic.hurt() if vic.draw_key is not None else None
            if h is None:
                continue
            hm, (hx, hy) = h
            pt = hm.overlap(cm, (round(cx) - BOMB_R - hx, round(cy) - BOMB_R - hy))
            if pt is None:
                continue
            att = owner if owner is not vic else None
            self._apply_hit(att, vic, BOMB_HIT, sign(vic.x - cx) or 1, (hx + pt[0], hy + pt[1]))
            if att is not None:
                att.hitstop = 0

    def _hand(self, f):
        return f.x + f.facing * f.half_w * 0.9, f.y - f.hgt * 0.55

    def _items_update(self):
        if self.phase == "play" and self.items_enabled:
            self.item_t -= 1
            if self.item_t <= 0:
                self.item_t = self.rng.randint(*ITEM_EVERY)
                if sum(1 for i in self.items if i.state in ("fall", "ground")) < ITEM_MAX:
                    self.spawn_item()
                    sfx("drop", 0.5)
        fs = [f for f in self.fighters if f.on_field and f.state != "held"]
        for item in self.items:
            item.t += 1
            st = item.state
            if st == "held":
                f = item.holder
                if f is None or not f.on_field:
                    item.state = "gone"
                    continue
                item.x, item.y = self._hand(f)
                if item.kind == "hammer":
                    item.timer -= 1
                    if item.timer <= 0:
                        self.drop_item(f, gone=True)
                        self.puff(f.x, f.y - f.hgt)
                continue
            if st in ("fall", "ground"):
                item.life -= 1
                if item.life <= 0:
                    if item.kind == "bomb":
                        self.explode(item)
                    else:
                        item.state = "gone"
                        self.puff(item.x, item.y)
                    continue
                if not item.pickable:            # touch to collect
                    for f in fs:
                        if (abs(f.x - item.x) < f.half_w + 6 and f.y - f.hgt - 4 < item.y - 4 < f.y + 6):
                            self.collect(f, item)
                            break
                    if item.gone:
                        continue
            if st == "ground":
                if item.kind == "star" or ground_at(item.x, item.y) is None:
                    item.state = "fall"
                continue
            # falling or flying
            py = item.y
            item.vy = min(4.0, item.vy + (0.18 if st == "thrown" else 0.22))
            item.x += item.vx
            item.y += item.vy
            if item.x < BLAST_L or item.x > BLAST_R or item.y > BLAST_B:
                item.state = "gone"
                continue
            if st == "thrown":
                if self._thrown_hits(item, fs):
                    continue
                if item.in_wall():
                    if item.kind == "bomb":
                        self.explode(item)
                        continue
                    item.vx *= -0.3
                    item.x += item.vx * 3
                    item.state = "fall"
            if item.vy >= 0:
                land = item.land_y(py)
                if land is not None:
                    item.y = land
                    if item.kind == "bomb" and item.state == "thrown":
                        self.explode(item)
                    elif item.kind == "star":
                        item.vy = -4.4
                    else:
                        item.vx = item.vy = 0.0
                        item.state = "ground"
                        item.owner = None
        self.items = [i for i in self.items if not i.gone]

    def _thrown_hits(self, item, fs):
        img = item.image()
        cx, cy = item.center()
        r = max(4, img.get_width() // 3)
        cm = circle_mask(r)
        for vic in fs:
            if vic is item.owner and item.t < 30:
                continue
            h = vic.hurt()
            if h is None:
                continue
            hm, (hx, hy) = h
            pt = hm.overlap(cm, (round(cx) - r - hx, round(cy) - r - hy))
            if pt is None:
                continue
            if item.kind == "bomb":
                self.explode(item)
                return True
            att = item.owner if item.owner is not vic else None
            self._apply_hit(att, vic, THROWN_HIT, sign(item.vx) or 1, (hx + pt[0], hy + pt[1]))
            if att is not None:
                att.hitstop = 0
            item.vx *= -0.3
            item.vy = -2.2
            item.state = "fall"
            item.owner = None
            return True
        return False

    def _hammer_hits(self, hurts):
        for f in self.fighters:
            item = f.item
            if item is None or item.kind != "hammer" or not f.on_field or f.state == "held":
                continue
            w, h = 32, round(f.hgt) + 6
            left = round(f.x) - 6 if f.facing > 0 else round(f.x) + 6 - w
            top = round(f.y - f.hgt) - 12
            m = rect_mask(w, h)
            for vic in self.fighters:
                if vic is f or hurts.get(vic) is None:
                    continue
                if self.t - item.victims.get(vic, -999) < 24:
                    continue
                hm, (hx, hy) = hurts[vic]
                pt = hm.overlap(m, (left - hx, top - hy))
                if pt is None:
                    continue
                item.victims[vic] = self.t
                self._apply_hit(f, vic, HAMMER_HIT, f.facing, (hx + pt[0], hy + pt[1]))
                f.hitstop = min(f.hitstop, 4)
                hurts[vic] = vic.hurt()

    # ---- hits ----------------------------------------------------------------
    def _apply_hit(self, att, vic, spec, dirx, point, grab_ok=False):
        """Returns 'hit', 'block' or None."""
        dmg = spec.get("dmg", 0)
        if vic.is_player and att is not None and not att.is_player:
            dmg = dmg * CPU_ON_AKUMA
        if vic.state == "shield" and not spec.get("grab"):
            vic.shield -= dmg * SHIELD_DMG_K + 1
            vic.lvx = dirx * min(3.0, 0.6 + dmg * 0.12)
            vic.hitstop = 4
            if att:
                att.hitstop = 4
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
        if spec.get("item") == "bat":
            sfx("bat", 0.8)
            if kb > 9:
                self.popups.append(["HOME RUN!", vic.x, vic.y - vic.hgt - 8, 50, (255, 240, 120)])
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

    def _item_strike(self, att):
        """(mask, x, y) of a held weapon's swing: a box in front, `reach` long."""
        mv = att.move
        w, h = mv["reach"], round(att.hgt * 0.9) + 6
        left = round(att.x) - 2 if att.facing > 0 else round(att.x) + 2 - w
        return rect_mask(w, h), left, round(att.y - att.hgt) - 6

    def _hits(self):
        fs = [f for f in self.fighters if f.draw_key is not None]
        hurts = {f: f.hurt() for f in fs}
        for att in fs:
            if not att.striking():
                continue
            mv = att.move
            if mv.get("item"):
                m, sx, sy = self._item_strike(att)
            else:
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
        self._hammer_hits(hurts)
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
        cx, cy, cw = self.cam
        ch = cw * H / W
        bx = max(cx - cw / 2, min(cx + cw / 2, f.x))
        by = max(cy - ch / 2, min(cy + ch / 2, f.y - f.hgt / 2))
        ang = math.atan2(cy - by, cx - bx)
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
        if f.item is not None:
            self.drop_item(f, gone=True)
        f.star = 0
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
            self.cloud_x[i] = (self.cloud_x[i] + 0.06 * (i % 3 + 1)) % (WW + 80)
        if self.phase == "final":
            self.end_t += 1
            for f in self.fighters:
                f.refresh()
            self._fx()
            skip = self.end_t > 80 and inp.any_pressed("punch", "kick", "special", "start")
            if (self.end_t >= FINAL_LEN or skip) and self.result is None:
                self._finish()
            return
        if self.phase == "intro":
            self.end_t += 1
            n = self.intro_len
            if self.end_t in (n - 90, n - 60, n - 30):
                audio.play("beep")
            for f in self.fighters:
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
        self._items_update()
        self._blast_zones()
        self._fx()
        self._camera()
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
            skip = self.end_t > 110 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= GAME_LEN or skip:
                self.round_wins.append(bool(self.won))
                self.round_stocks.append(ak.stocks if self.won else 0)
                if self.round < ROUNDS:
                    self.round += 1
                    self._start_round()
                else:
                    self.phase, self.end_t = "final", 0
                    audio.play("encounter" if self.rounds_won else "ko", 0.7)

    def _finish(self):
        if self.rounds_won >= 1:
            self.result = "win"
            best = max(self.round_stocks)
            hp = max(1, round(self.hp * (0.5 + 0.5 * best / STOCKS)))
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
        for b in self.booms:
            b[3] += 1
        self.booms = [b for b in self.booms if b[3] < 20]
        for pu in self.popups:
            pu[3] -= 1
        self.popups = [pu for pu in self.popups if pu[3] > 0]

    # ---- camera ----------------------------------------------------------------
    def _cam_target(self):
        """(centre x, centre y, width) framing every fighter in play, 16:9, inside the world."""
        pts = []
        for f in self.fighters:
            if f.out or f.state == "dead":
                continue
            if f.state == "respawn":
                pts.append((f.x, HALO_Y - 30))
                continue
            x = max(BLAST_L + 20, min(BLAST_R - 20, f.x))
            y = max(-10, min(WH, f.y))
            pts += [(x - 34, y - f.hgt - 22), (x + 34, y + 14)]
        if not pts:
            return [MID_X, WH / 2, float(WW)]
        x0 = min(p[0] for p in pts)
        x1 = max(p[0] for p in pts)
        y0 = min(p[1] for p in pts)
        y1 = max(p[1] for p in pts)
        w = max(CAM_MIN_W, x1 - x0, (y1 - y0 + 26) * W / H)    # room for the HUD at the bottom
        w = min(float(WW), w)
        h = w * H / W
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2 + 12
        cx = max(w / 2, min(WW - w / 2, cx))
        cy = max(h / 2, min(WH - h / 2, cy))
        return [cx, cy, w]

    def _camera(self):
        tx, ty, tw = self._cam_target()
        cx, cy, cw = self.cam
        k = 0.06
        cw += (tw - cw) * k
        cw = max(float(CAM_MIN_W), min(float(WW), cw))
        h = cw * H / W
        cx += (tx - cx) * k
        cy += (ty - cy) * k
        cx = max(cw / 2, min(WW - cw / 2, cx))
        cy = max(h / 2, min(WH - h / 2, cy))
        self.cam = [cx, cy, cw]

    def cam_rect(self):
        cx, cy, cw = self.cam
        w = int(round(cw))
        h = int(round(w * H / W))
        x = int(round(cx - w / 2))
        y = int(round(cy - h / 2))
        x = max(0, min(WW - w, x))
        y = max(0, min(WH - h, y))
        return pygame.Rect(x, y, w, h)

    def to_screen(self, x, y, rect=None):
        r = rect or self.cam_rect()
        k = W / r.w
        return (x - r.x) * k, (y - r.y) * k

    # ---- draw ----------------------------------------------------------------
    def draw(self, surf):
        sh = (0, 0)
        if self.shake:
            m = 1 + self.shake // 5
            sh = (self.rng.randint(-m, m), self.rng.randint(-m, m))
        a = self.art
        ws = self.world
        ws.blit(a["bg"], (0, 0))
        for i, c in enumerate(a["clouds"]):
            ws.blit(c, (round(self.cloud_x[i]) - 70, 20 + (i % 3) * 22))
        ws.blit(a["stage"], sh)
        for f in self.fighters:
            if f.state == "respawn":
                hx, hy = round(f.x) + sh[0], HALO_Y + sh[1]
                pygame.draw.ellipse(ws, OUTLINE, (hx - 15, hy - 2, 30, 7))
                pygame.draw.ellipse(ws, shade(f.color, 1.3), (hx - 14, hy - 1, 28, 5))
                pygame.draw.ellipse(ws, (255, 255, 255), (hx - 9, hy, 18, 2))
        for item in self.items:
            if item.state != "held":
                self._draw_item(ws, item, sh)
        order = sorted(self.fighters, key=lambda f: (f.is_player, f.state == "held"))
        for f in order:
            self._draw_fighter(ws, f, sh)
            if f.item is not None and f.draw_key is not None:
                self._draw_held(ws, f, sh)
        for s in self.shots:
            img, _, (px, py) = s.frame()
            ws.blit(img, (px + sh[0], py + sh[1]))
        for fx in self.effects:
            fx.draw(ws, sh)
        self._draw_booms(ws, sh)
        for p in self.parts:
            ws.fill(p[5], (round(p[0]) + sh[0], round(p[1]) + sh[1], 2, 2))
        self._draw_blasts(ws)
        # the camera: the part of the world in view, scaled to the canvas
        r = self.cam_rect()
        view = ws.subsurface(r)
        if r.w == W:
            surf.blit(view, (0, 0))
        else:
            pygame.transform.scale(view, (W, H), surf)
        for f in self.fighters:
            self._tag(surf, f, sh, r)
        for text, x, y, n, col in self.popups:
            sx, sy = self.to_screen(x, y, r)
            sx = max(text_width(text) // 2 + 2, min(W - text_width(text) // 2 - 2, sx))
            draw_text(surf, text, round(sx), max(2, round(sy) - (60 - n) // 5), col, align="center")
        if self.flash:
            fl = pygame.Surface((W, H), pygame.SRCALPHA)
            fl.fill((255, 255, 255, 90))
            surf.blit(fl, (0, 0))
        self._hud(surf)
        self._overlays(surf)
        if self.menu.open:
            self.menu.draw(surf)

    def _draw_item(self, surf, item, sh):
        if item.state in ("fall", "ground") and item.life < 120 and (item.life // 4) % 2:
            return                                   # blinking: about to vanish
        img = item.image()
        x = round(item.x - img.get_width() / 2) + sh[0]
        y = round(item.y - img.get_height()) + sh[1]
        if item.kind == "star":
            y += round(math.sin(item.t / 5) * 1)
        if item.state == "thrown" and item.kind in ("bat", "sword", "hammer"):
            img = item_rotated(item.kind, item.vx < 0, (item.t * 30) % 360)
            x = round(item.x - img.get_width() / 2) + sh[0]
            y = round(item.y - 5 - img.get_height() / 2) + sh[1]
        if item.state == "ground":
            pygame.draw.ellipse(surf, (30, 26, 40), (round(item.x) - 5 + sh[0], round(item.y) - 1 + sh[1], 10, 3))
        surf.blit(img, (x, y))
        if item.kind == "bomb" and (item.state == "thrown" or item.life < 240):
            col = (255, 240, 120) if (item.t // 3) % 2 else (255, 120, 40)
            surf.fill(col, (x + 6, y - 1, 2, 2))
        elif item.kind == "star":
            col = STAR_COLORS[(item.t // 4) % len(STAR_COLORS)]
            surf.fill(col, (x + (item.t // 2) % 14, y + 13, 1, 1))

    def _draw_held(self, surf, f, sh):
        item = f.item
        hx, hy = self._hand(f)
        hx += sh[0]
        hy += sh[1]
        k = item.kind
        flip = f.facing < 0
        if k == "bomb":
            img = item.image()
            surf.blit(img, (round(hx - img.get_width() / 2), round(hy - img.get_height() + 3)))
            return
        if k == "hammer":
            up = (self.t // 12) % 2 == 0
            ang = 100 if up else 0
            if up:
                hx, hy = f.x + sh[0] + f.facing * 2, f.y - f.hgt * 0.8 + sh[1]
        elif f.state == "move" and f.move and f.move.get("item"):
            kind, _, run_t, span = f.phase_info()
            if kind == "startup":
                ang = 120
            elif kind == "active":
                ang = 80 - 110 * min(1.0, run_t / max(1, span - 1))
            else:
                ang = -30
        else:
            ang = 60
        img = item_rotated(k, flip, ang)
        ln = item_image(k).get_width() / 2 - 3
        dx = math.cos(math.radians(ang)) * ln * f.facing
        dy = -math.sin(math.radians(ang)) * ln
        surf.blit(img, (round(hx + dx - img.get_width() / 2), round(hy + dy - img.get_height() / 2)))

    def _draw_booms(self, surf, sh):
        for x, y, r, t in self.booms:
            k = min(1.0, t / 6)
            rr = max(2, round(r * (0.4 + 0.6 * k)))
            cx, cy = round(x) + sh[0], round(y) + sh[1]
            if t < 14:
                pygame.draw.circle(surf, (240, 70, 30), (cx, cy), rr)
                pygame.draw.circle(surf, (255, 170, 50), (cx, cy), max(1, rr - 4))
                pygame.draw.circle(surf, (255, 246, 200), (cx, cy), max(1, rr - 10 - t))
            else:
                pygame.draw.circle(surf, (90, 80, 84), (cx, cy - (t - 14)), max(1, rr - (t - 14) * 3), 2)

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
            if f.star:
                tint = flash_of(f.art, f.draw_key, f.flip, f.k).copy()
                tint.fill(STAR_COLORS[(self.t // 3) % len(STAR_COLORS)] + (255,),
                          special_flags=pygame.BLEND_RGBA_MULT)
                tint.set_alpha(120 if f.star > 90 or (f.star // 4) % 2 else 40)
                surf.blit(tint, (x, y))
                if self.t % 3 == 0:
                    self.parts.append([f.x + self.rng.uniform(-8, 8), f.y - self.rng.uniform(0, f.hgt), 0, -0.4,
                                       10, STAR_COLORS[self.rng.randrange(len(STAR_COLORS))]])
            elif (f.invuln or f.state == "respawn") and (self.t // 3) % 2:
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

    def _tag(self, surf, f, sh, rect):
        if f.out or f.state == "dead" or self.phase == "intro":
            return
        label = "P1" if f.is_player else "CPU"
        x, top = self.to_screen(f.x, f.y - f.hgt, rect)
        _, feet = self.to_screen(f.x, f.y, rect)
        _, mid = self.to_screen(f.x, f.y - f.hgt / 2, rect)
        if x < 0 or x > W or feet < 0 or top > H:
            cx = max(9, min(W - 9, x))
            cy = max(9, min(H - 40, mid))
            pygame.draw.circle(surf, OUTLINE, (round(cx), round(cy)), 8)
            pygame.draw.circle(surf, f.color, (round(cx), round(cy)), 7)
            surf.blit(small_portrait(f.cid, 10), (round(cx) - 5, round(cy) - 5))
            return
        y = max(2, top - 9)
        draw_text(surf, label, round(x) + sh[0], round(y) + sh[1], f.color, align="center")
        tx, ty = round(x) + sh[0], round(y) + 8 + sh[1]
        pygame.draw.polygon(surf, f.color, [(tx - 2, ty), (tx + 2, ty), (tx, ty + 2)])

    def _draw_blasts(self, surf):
        if not self.blasts:
            return
        layer = pygame.Surface((WW, WH), pygame.SRCALPHA)
        for bx, by, ang, col, t in self.blasts:
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
            if f.item is not None:             # what they're holding, next to the stocks
                ic = f.item.image()
                surf.blit(ic, (x0 + pw - ic.get_width() - 1, y0 - ic.get_height() - 1))
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
        # round counter, top centre
        if self.phase in ("play", "game"):
            draw_text(surf, "ROUND %d/%d" % (self.round, ROUNDS), W // 2, 3, (255, 255, 255), align="center")
            self._tally_pips(surf, W // 2, 12)

    def _tally_pips(self, surf, cx, y):
        for k in range(ROUNDS):
            x = cx - (ROUNDS - 1) * 6 + k * 12
            if k < len(self.round_wins):
                col = (255, 80, 60) if self.round_wins[k] else (110, 110, 130)
            else:
                col = (40, 36, 54)
            pygame.draw.circle(surf, OUTLINE, (x, y + 3), 4)
            pygame.draw.circle(surf, col, (x, y + 3), 3)

    def _band(self, surf, y, h, alpha=185):
        band = pygame.Surface((W, h), pygame.SRCALPHA)
        band.fill((8, 6, 20, alpha))
        surf.blit(band, (0, y))

    def _overlays(self, surf):
        cx = W // 2
        if self.phase == "intro":
            n = self.end_t
            L = self.intro_len
            if n < L - 90:
                if self.round == 1:
                    self._band(surf, 26, 54)
                    draw_text(surf, "LEVEL %d" % self.level, cx, 30, (255, 220, 80), scale=2, align="center")
                    draw_text(surf, LEVEL_NAME, cx, 48, (255, 255, 255), align="center")
                    draw_text(surf, "ROUND 1 OF %d - 3 STOCKS - ITEMS ON" % ROUNDS, cx, 59, (180, 220, 255),
                              align="center")
                    draw_text(surf, "WIN A ROUND TO CLEAR THE LEVEL", cx, 69, (255, 190, 150), align="center")
                else:
                    self._band(surf, 30, 46)
                    draw_text(surf, "ROUND %d" % self.round, cx, 34, (255, 220, 80), scale=3, align="center")
                    w = self.rounds_won
                    draw_text(surf, "AKUMA %d - %d CHALLENGERS" % (w, len(self.round_wins) - w), cx, 62,
                              (255, 255, 255), align="center")
            else:
                k = 3 - (n - (L - 90)) // 30
                if k >= 1:
                    draw_text(surf, str(k), cx, 50, (255, 230, 90), scale=5, align="center")
        if self.phase == "play" and self.t - getattr(self, "play_t", -999) < 45:
            draw_text(surf, "GO!", cx, 46, (255, 70, 40), scale=5, align="center")
        if self.phase == "game":
            if self.end_t < 100:
                draw_text(surf, "GAME!", cx, 44, (255, 230, 80), scale=5, align="center")
            else:
                self._band(surf, 50, 30)
                if self.won:
                    draw_text(surf, "AKUMA WINS ROUND %d!" % self.round, cx, 54, (255, 80, 60), scale=2,
                              align="center")
                    draw_text(surf, "THE CHALLENGERS ARE SMASHED", cx, 70, (255, 255, 255), align="center")
                else:
                    draw_text(surf, "AKUMA LOSES ROUND %d" % self.round, cx, 54, (255, 255, 255), scale=2,
                              align="center")
                    nxt = "ROUND 2 IS NEXT" if self.round < ROUNDS else "OUT OF STOCKS"
                    draw_text(surf, nxt, cx, 70, (255, 140, 120), align="center")
        if self.phase == "final":
            self._band(surf, 22, 78, 205)
            w = self.rounds_won
            draw_text(surf, "FINAL TALLY", cx, 26, (255, 220, 80), scale=2, align="center")
            for k, won in enumerate(self.round_wins):
                txt = "ROUND %d:  %s" % (k + 1, "AKUMA WINS" if won else "CHALLENGERS WIN")
                draw_text(surf, txt, cx, 45 + k * 10, (255, 120, 90) if won else (170, 170, 190), align="center")
            draw_text(surf, "AKUMA %d - %d CHALLENGERS" % (w, len(self.round_wins) - w), cx, 67,
                      (255, 255, 255), align="center")
            if w:
                draw_text(surf, "LEVEL CLEAR!", cx, 80, (255, 80, 60), scale=2, align="center")
            else:
                draw_text(surf, "AKUMA IS DEFEATED", cx, 80, (200, 200, 220), scale=2, align="center")
