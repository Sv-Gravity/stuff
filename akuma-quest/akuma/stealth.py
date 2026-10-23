"""The frozen compound, a top-down sneaking level.

Akuma infiltrates a snowy yard and a hangar on a chain of missions:
  1) raid the barracks (a red beret guards it) for the keycard and the C4,
  2) plant the C4 on the three generators: the blast cuts the power, so the
     cameras and the laser fence die, the hangar goes dark and the magnetic
     lock on the prisoner's cell drops,
  3) free the prisoner, who tells him where the commander is,
  4) the commander, REVOLVER KEN, rides the elevator up with two soldiers:
     beat them (a normal boss fight) and the level is clear.
The current objective is on the HUD and every step is a codec call.

Genome soldiers mostly stand on post staring one way (glancing left and right
now and then); a few walk short beats with long pauses. Smokers have a short,
narrow cone. Red berets guard the rooms with power-ups, see further and are
tougher in a fight. Soldiers chat in speech bubbles.

Seeing: vision cones (much shorter when Akuma is in a shadow). A soldier who
half sees him goes "?" and walks over to look; seen properly: "!", ALERT ->
EVASION -> CAUTION -> normal. Caught: a side-view fight against rifles
(game.start_fight). Hidden: still in the cardboard box, or inside a bush
(only a soldier bumping into him finds him). Behind an unaware soldier, punch
snaps his neck: no fight, but a body left in view puts the base on CAUTION.
Health pickups are random Japanese snacks (akuma/snacks.py).
"""

import math
import random
from collections import deque
from types import SimpleNamespace

import pygame

from . import audio
from . import fight as F
from .akuma_sprites import MapArt, MAP_SCALE, portrait
from .art import random_look, shade
from .config import W, H
from .fighters import HIT, boss_moveset, scale_damage
from .font import draw_text, wrap
from .pause import PauseMenu
from .snacks import heal_amount, random_snack, snack_image

T = 16
# ---------------------------------------------------------------------------
# the map: # wall  . floor  : floor in shadow  , snow  ; snow in shadow
#          C crate  T truck  E elevator  B cardboard box  P start  b bush
#          G generator  D cell door (magnetic lock)  K keycard door
# ---------------------------------------------------------------------------
MAP = """
########################################################
#::::::::######::::...........G..............#....EEE..#
#::::::::#::::#::::..........................#.........#
#:::B::::#::::D::::..CC...........CC...................#
#::::::::#::::#::::..CC...........CC...................#
#::::::::######::::.::::.........::::........###########
#::::::::######::::.::::.........::::..................#
#####::########::::....................................#
#:::::::::::::#::::........CC.................##########
#:::::::::::::#::::........CC..........CC.....#......CC#
#G:::::::::::::::::.......::::.........CC.....K........#
#::::::::::::::::::.......::::........::::....#........#
#:::::::::::::#::::...................::::....#:::...CC#
######::######################..########################
#;;;;;;;;;;;;;;;;;;;;;;;G;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;#
#,,,,,,,C,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,C,,,,,,,,,bb,,,#
#,,,,,,,;,,,,,,,,,,,,,,,,,bb,,,,,,,,,,,,;,,,CC,,,,,,,,,#
#,,bb,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,CC,,,,,,,,,#
#,,b,,,,,,,,TTTT,,,,,,,,,,,,,,,,,,,,,,,,,,,,;;,,,,,,,,,#
#,,,,,,,,,,,TTTT,,,,,,,,,,,,,bb,,,,,,,,,,,,,,,,,,,,,,,,#
#,,,,,,,,,,;;;;;;,,,,,,,,,,,,,,,,,,,TTTT,,,,,,,,,,,CC,,#
#,,,,,,,,,,;;;;;;,,C,,,,,,,,,,,,,,,,TTTT,,,,,,,,,,,;;,,#
#,,,,,,C,,,,,,,,,,,C,,,,,,,,,,,,,,,;;;;;;,,,,,,,,,,,,,,#
#,,,,,,;,,,,,,,,,,,,,,,,,,,,,,,,,,,;;;;;;,,,,,,,,,,,,,,#
#,,,,,,,,,,,,,bb,,,,,,,,,,,,,,,,,,,b,,,,,,,,,,,,,,,,,,,#
#,,,,,,,,,,,,,b,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,##########
#,,,,,,,,,,,,,,,,,,,,,,,TTTT,,,,,,,,,,,,,,,,,,#.....:::#
#,,,,,,,bb,,,,,,,,,,,,,,TTTT,,,,,,,,,,,,,,,,,,#.....:::#
#,,,,,,,,,,,,,,,,,,,,,,;;;;;;,,,,,,,,,,,,b,,,,#........#
#,,,,,,,,,,,,,,,,,,,,,,;;;;;;,,,C,,,,,,,,bb,,,.........#
#,,,,,P,,,,,,,,,,,,,bb,,,,,,,,,,;,,,,,,,,,,,,,#........#
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#.......C#
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,#.......C#
########################################################
"""
SOLID = set("#CTGDK")
SHADOW = set(":;B")
SNOW = set(",;Pb")
INDOOR = set(".:BE")
HELIPAD = (7, 28)            # tile the painted H sits on

# the soldiers: kind, and a beat of stops (tx, ty, frames to stand there, facing in
# degrees, 0 = right, 90 = down; None keeps the way he walked in). One stop = a post.
GUARDS = [
    dict(kind="guard", route=[(4, 22, 450, None), (13, 22, 450, None)]),       # yard, west beat
    dict(kind="guard", route=[(43, 20, 420, None), (51, 23, 420, None)]),      # yard, east beat
    dict(kind="smoker", route=[(17, 18, 0, 0)]),                               # smoking by the truck
    dict(kind="guard", route=[(29, 15, 0, 90)]),                               # main door
    dict(kind="smoker", route=[(32, 15, 0, 180)]),                             # ...and his smoking buddy
    dict(kind="guard", route=[(21, 15, 0, 0)]),                                # watches generator 3
    dict(kind="elite", route=[(44, 29, 0, 180)]),                              # barracks door
    dict(kind="guard", route=[(38, 26, 480, 0), (38, 31, 480, 0)]),            # by the barracks
    dict(kind="smoker", route=[(17, 9, 0, 90)]),                               # dark corridor
    dict(kind="guard", route=[(26, 7, 480, None), (37, 7, 480, None)]),        # hangar hall beat
    dict(kind="guard", route=[(33, 2, 0, 180)]),                               # watches generator 1
    dict(kind="elite", route=[(44, 10, 0, 180)]),                              # armory door
    dict(kind="guard", route=[(48, 2, 0, 180)]),                               # elevator room
    dict(kind="guard", route=[(4, 11, 450, None), (12, 11, 450, None)]),       # west corridor, generator 2
]
# security cameras: wall tile, direction looked at (degrees, 90 = down), sweep +-, period
CAMERAS = [((36, 13), 90, 50, 400), ((25, 0), 90, 55, 460), ((17, 13), 90, 45, 360)]
# laser fence across the elevator room door: tile column, rows, frames on, frames off
LASERS = [((45, 3), (45, 4), 150, 80)]
# the rooms the red berets guard
KEYCARD_AT = (50, 29)
PICKUPS = [("lifeup", (53, 30)), ("snack", (48, 32)), ("powup", (51, 10)), ("bento", (48, 11))]
PRISONER_AT = (11, 3)
BOSS_FROM, BOSS_POST = (51, 1), (49, 3)
N_SNACKS = 7                 # extra snacks lying around the base

# ---- tuning ----------------------------------------------------------------
WALK, SNEAK, BOX_SPEED = 1.35, 0.6, 0.8        # Akuma, px / frame
VIEW_RANGE, VIEW_HALF = 84, math.radians(32)    # a soldier's cone
SMOKE_RANGE, SMOKE_HALF = 52, math.radians(22)  # a smoker's (busy with his cigarette)
ELITE_RANGE, ELITE_HALF = 96, math.radians(38)  # a red beret's
CAM_RANGE, CAM_HALF = 82, math.radians(20)
SHADOW_K = 0.33              # cone reach on a target standing in a shadow
CAUTION_K = 1.15             # longer looks while on CAUTION
NEAR_K = 0.55                # seen inside this part of the cone: "!" at once
NOTICE_T = 40                # frames kept in a far view before "?" becomes "!"
BOX_SPOT = 26                # a moving box this close to a soldier is found out
HEAR = 44                    # px a normal step is heard over (sneaking is silent)
KNOCK_HEAR = 120
G_WALK, G_CAUTION, G_RUN, G_SEARCH = 0.5, 0.7, 1.25, 0.85
ALERT_T, EVASION_T, CAUTION_T = 60 * 15, 60 * 20, 60 * 25
FREEZE = 26                  # the world stops for the "!" sting
INVULN = 120                 # after a fight, before another can start
SNAP_RANGE = 20              # px: close enough to grab
SNAP_BEHIND = math.radians(100)   # this far off where he looks counts as behind him
SNAP_T, SNAP_KILL = 34, 20   # grab length, frame of the crack
DETONATE_T = 100             # frames from the last charge to the blast
HUD_RADAR = pygame.Rect(W - 72, 0, 72, 68)   # screen areas speech bubbles keep out of
HUD_LIFE = pygame.Rect(0, 0, 156, 40)
CHAT_GAP = 150               # frames between two soldiers' idle chatter

# ---- the soldiers in a fight -------------------------------------------------
GUARD_HITS = 5               # normal hits a soldier takes
ELITE_HITS = 9
BOSS_HITS = 16
SHOT_DMG, BURST_DMG, LOW_DMG, BUTT_DMG = 34, 20, 28, 22
BULLET_SPEED = 7.5
GUARD_AI = dict(aggression=0.85, block=0.3, jumpiness=0.1, reaction=4)
ELITE_AI = dict(aggression=0.9, block=0.45, jumpiness=0.15, reaction=3)
BOSS_AI = dict(aggression=0.85, block=0.45, jumpiness=0.25, reaction=2, boss=True)

CONTROLS = [
    "ARROWS / WASD: MOVE",
    "HOLD K: SNEAK (SLOW AND SILENT)",
    "J BEHIND A GUARD: SNAP HIS NECK",
    "J BY A WALL: KNOCK TO LURE A GUARD",
    "J BY A GENERATOR: PLANT C4",
    "L / SPACE: CARDBOARD BOX ON / OFF",
    "STILL IN THE BOX, OR IN A BUSH: UNSEEN",
    "CAUGHT: FIGHT RIFLES. JUMP OR BLOCK THE SHOTS",
    "FOLLOW THE OBJECTIVE (TOP LEFT, RADAR)",
]

# codec calls: who talks; the right-hand portrait is the last non-Akuma speaker
CODEC = {
    "intro": [
        ("CHUN-LI", "AKUMA, DO YOU READ ME? YOU'RE INSIDE THE FROZEN COMPOUND."),
        ("AKUMA", "..."),
        ("CHUN-LI", "THE COMMANDER, REVOLVER KEN, HIDES BELOW. WE HAVE TO DRAW HIM OUT."),
        ("CHUN-LI", "FIRST RAID THE BARRACKS IN THE SOUTH-EAST. A RED BERET GUARDS THE DOOR."),
        ("CHUN-LI", "GET BEHIND A GUARD AND PRESS PUNCH. QUIETLY. BUSHES AND SHADOWS HIDE YOU."),
        ("AKUMA", "A DEMON DOES NOT HIDE."),
        ("CHUN-LI", "THIS ONE DOES. OH, AND SOMEONE LEFT A CARDBOARD BOX IN STORAGE. DON'T ASK."),
    ],
    "keycard": [
        ("CHUN-LI", "THE KEYCARD AND THREE C4 CHARGES. GOOD WORK."),
        ("CHUN-LI", "PLANT THE C4 ON THE THREE GENERATORS. CHECK YOUR RADAR."),
        ("CHUN-LI", "NO POWER, NO CAMERAS, NO LASERS. AND THE KEYCARD OPENS THE ARMORY."),
    ],
    "power": [
        ("CHUN-LI", "THE POWER'S OUT! THE CAMERAS AND THE LASER FENCE ARE DEAD."),
        ("CHUN-LI", "THE PRISON CELL IN THE WEST WING HAD A MAGNETIC LOCK. IT JUST DROPPED."),
        ("AKUMA", "A PRISONER?"),
        ("CHUN-LI", "SHE KNOWS WHERE KEN IS. GET HER OUT."),
    ],
    "rescue": [
        ("SAKURA", "AKUMA-SAN?! I CAME HERE LOOKING FOR RYU AND THEY LOCKED ME UP!"),
        ("AKUMA", "..."),
        ("SAKURA", "THEIR COMMANDER IS COMING UP THE ELEVATOR. HE SPINS HIS GUN A LOT. IT'S WEIRD."),
        ("REVOLVER KEN", "YOU'RE PRETTY GOOD... FOR A DEMON. I'LL BE WAITING AT THE ELEVATOR."),
    ],
}
PORTRAITS = {"CHUN-LI": "chunli", "SAKURA": "sakura", "REVOLVER KEN": "ken", "AKUMA": "akuma"}
FREQ = "140.85"

OBJECTIVES = ["RAID THE BARRACKS (SE)", "PLANT C4: GENERATORS %d/3", "FREE THE PRISONER (W)",
              "BEAT REVOLVER KEN (NE)"]

# ---- what the soldiers say ---------------------------------------------------
CHATTER = {
    "guard": [
        "I REALLY NEED TO PEE.",
        "WHEN I GET OFF SHIFT I'M GETTING RAMEN.",
        "WHO KEEPS LEAVING CARDBOARD BOXES AROUND?",
        "MY FEET ARE FROZEN TO THE FLOOR.",
        "I JOINED FOR THE DENTAL PLAN.",
        "*YAWN*... WHAT TIME IS IT?",
        "SNOW AGAIN. GREAT.",
        "THEY SAY A DEMON IS LOOSE. HA. DEMONS.",
        "I HEARD THE COMMANDER SLEEPS IN A BOX.",
        "ONE DAY I'LL GET A RED BERET.",
        "THESE GOGGLES ARE JUST FOR SHOW.",
        "STARE AT THE WALL, THEY SAID. IT'LL BE FUN.",
        "LA LA LA... GUARDING... LA LA...",
    ],
    "smoker": [
        "JUST ONE MORE. THEN I QUIT.",
        "DON'T TELL THE SERGEANT.",
        "SMOKING IS BAD FOR YOU. SO IS THIS JOB.",
        "AH... THAT HITS THE SPOT.",
        "IS IT SMOKE OR IS IT MY BREATH? BOTH?",
    ],
    "elite": [
        "NOBODY GETS PAST ME.",
        "I DID 500 PUSH-UPS TODAY.",
        "THIS BERET IS NOT A FASHION STATEMENT.",
        "I CAN SMELL FEAR. AND RAMEN.",
    ],
}
HUH = {"noise": "WHAT WAS THAT NOISE?", "box": "IS THAT BOX... MOVING?",
       "seen": "HUH? WHO'S THERE?", "body": "HEY! WAKE UP! ...OH NO."}
GIVE_UP = {"noise": ["MUST'VE BEEN THE WIND... IT'S ALWAYS THE WIND.", "HUH. I NEED MORE SLEEP."],
           "box": ["JUST A BOX. NICE BOX, THOUGH.", "BOXES DON'T MOVE. RIGHT?"],
           "seen": ["I'M SEEING THINGS AGAIN.", "MUST'VE BEEN A RABBIT."],
           "body": ["SOMEONE CALL A MEDIC... LATER."]}
CAUTION_OVER = ["I GUESS IT WAS NOTHING.", "BACK TO STARING AT WALLS."]
BOSS_LINES = ["SIX BULLETS. MORE THAN ENOUGH.", "COME ON, DEMON!", "YOU'RE PRETTY GOOD.",
              "*SPINS REVOLVER*"]
PRISONER_LINES = ["HELLO? ANYONE?", "I JUST WANTED TO FIND RYU...", "THIS CELL SMELLS LIKE SOCKS."]

DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def _rows():
    return [r for r in MAP.strip("\n").split("\n")]


def _angdiff(a, b):
    return abs((a - b + math.pi) % math.tau - math.pi)


def _sounds():
    """This level's own little sounds, built once into audio's table."""
    if not getattr(audio, "_ok", False) or "neck_snap" in audio._sfx:
        return
    S = audio._sfx
    S["neck_snap"] = audio._sound(audio._add(audio._noise(0.06, 0.7, 4.0, 0.95),
                                             audio._tone(320, 70, 0.07, 0.35, "square", 0.5)))
    S["grab"] = audio._sound(audio._add(audio._noise(0.1, 0.35, 2.0, 0.2), audio._tone(180, 120, 0.08, 0.2, "tri")))
    S["rustle"] = audio._sound(audio._noise(0.14, 0.12, 1.4, 0.7))
    S["c4_beep"] = audio._sound(audio._tone(1400, 1400, 0.05, 0.1, "square", 0, 0.5))
    S["door_open"] = audio._sound(audio._seq(audio._tone(600, 900, 0.06, 0.15, "tri"),
                                             audio._noise(0.25, 0.25, 1.0, 0.1)))


# ---------------------------------------------------------------------------
# guns: the soldiers' fight moves (akuma/fighters.py enemy move format)
# ---------------------------------------------------------------------------
_TRACER = None


def tracer_frames():
    """A bullet: a hot white core with an orange tail, facing right."""
    global _TRACER
    if _TRACER is None:
        out = []
        for k in range(2):
            s = pygame.Surface((14, 3), pygame.SRCALPHA)
            for x in range(14):
                t = x / 13
                a = int(255 * t ** 1.4)
                col = (255, 120 + int(100 * t), 40) if x < 10 else (255, 250, 210)
                s.fill(col + (a,), (x, 1, 1, 1))
                if x >= 9 + k:
                    s.fill((255, 220, 140, a // 2), (x, 0, 1, 1))
                    s.fill((255, 220, 140, a // 2), (x, 2, 1, 1))
            out.append(s)
        _TRACER = out
    return _TRACER


def _bullet(dmg, y, chip, x=24, speed=BULLET_SPEED):
    return dict(speed=speed, dmg=dmg, hitstun=22, blockstun=12, chip=chip,
                colors=((255, 255, 230), (255, 220, 120), (230, 120, 40)),
                y=y, px=True, x=x, tracer=True, frames=tracer_frames(), size=(12, 5))


def m_rifle(rng):
    return dict(name="Rifle Shot", range=(30, 400), gun=True,
                phases=[("startup", 9 + rng.randint(0, 3), "hado_prep"), ("startup", 4, "hado_fire"),
                        ("recovery", 20, "hado_fire")],
                events={10: dict(sound="gunshot", proj=_bullet(SHOT_DMG, -44, 5))})


def m_burst(rng):
    return dict(name="Burst Fire", range=(40, 400), gun=True,
                phases=[("startup", 14, "hado_prep"), ("startup", 12, "hado_fire"),
                        ("recovery", 26, "hado_fire")],
                events={14: dict(sound="gunshot", proj=_bullet(BURST_DMG, -44, 3)),
                        19: dict(sound="gunshot", proj=_bullet(BURST_DMG, -42, 3)),
                        24: dict(sound="gunshot", proj=_bullet(BURST_DMG, -46, 3))})


def m_low_shot(rng):
    return dict(name="Kneeling Shot", range=(40, 400), gun=True, crouching=True,
                phases=[("startup", 12, "crouch"), ("startup", 4, "crouch_jab"),
                        ("recovery", 22, "crouch")],
                events={13: dict(sound="gunshot", proj=_bullet(LOW_DMG, -22, 4, x=22))})


def m_butt(rng):
    return dict(name="Rifle Butt", range=(0, 34),
                phases=[("startup", 6, "punch_prep"), ("active", 4, "punch"), ("recovery", 14, "punch_prep")],
                hitbox=(8, -38, 22, 12), dmg=BUTT_DMG, hitstun=20, blockstun=12, height="mid",
                knockdown=True, launch=-4.0, push=2.6, events={4: dict(sound="whiff")})


def guard_moveset(rng):
    return [m_rifle(rng), m_burst(rng), m_low_shot(rng), m_butt(rng)]


def m_revolver(rng):
    """Six quick shots, high and low: the commander showing off."""
    evs = {}
    for k in range(6):
        y = -44 if k % 2 == 0 else -22
        evs[10 + k * 6] = dict(sound="gunshot", proj=_bullet(18, y, 3, x=22, speed=8.5))
    return dict(name="Six Shooter", range=(40, 400), gun=True,
                phases=[("startup", 10, "hado_prep"), ("startup", 36, "hado_fire"), ("recovery", 24, "hado_prep")],
                events=evs)


def boss_moves(rng):
    return [m_revolver(rng), m_rifle(rng)] + scale_damage(boss_moveset(rng), 3.2)


_ART = {}


def _map_art(cid, k=1.0):
    key = (cid, k)
    if key not in _ART:
        _ART[key] = MapArt(cid, MAP_SCALE * k)
    return _ART[key]


class Guard:
    """A soldier on post or on a short beat, and the enemy namespace handed
    to game.start_fight."""

    def __init__(self, rng, spec, index):
        self.kind = spec.get("kind", "guard")
        self.route = [((tx + 0.5) * T, (ty + 0.5) * T, wait, None if f is None else math.radians(f))
                      for tx, ty, wait, f in spec["route"]]
        self.x, self.y = self.route[0][0], self.route[0][1]
        self.ri = 0
        self.post = len(self.route) == 1
        f0 = self.route[0][3]
        self.angle = f0 if f0 is not None else rng.uniform(0, math.tau)
        self.look_base = self.angle
        # glance left and right once a cycle; smokers less, red berets more often
        lo, hi = {"smoker": (520, 820), "elite": (220, 340)}.get(self.kind, (300, 520))
        self.cycle = rng.randint(lo, hi)
        self.look_t = rng.randrange(self.cycle)
        self.wait = 10 ** 9 if self.post else max(1, self.route[0][2] // 2)
        self.state = "patrol"        # patrol, suspicious, alert, search
        self.sub = None
        self.why = "noise"
        self.t = 0
        self.stim = None
        self.notice = 0
        self.exclaim = 0
        self.huh = 0
        self.search_to = None
        self.alive = True
        self.moving = False
        self.walked = 0.0
        self.face = 1 if math.cos(self.angle) >= 0 else -1
        self.anim = rng.randrange(60)
        self.say = None              # [text, frames left]
        self.chat_cd = rng.randint(240, 1200)
        self.puffs = []
        self.range, self.half = {"smoker": (SMOKE_RANGE, SMOKE_HALF),
                                 "elite": (ELITE_RANGE, ELITE_HALF)}.get(self.kind, (VIEW_RANGE, VIEW_HALF))
        # --- fight namespace (like dungeon.MapEnemy) ---
        self.boss = False
        self.car = False
        self.look = random_look(rng)
        self.allies = []
        if self.kind == "elite":
            self.name = "RED BERET"
            self.cid = "zangief"
            self.level = 5
            self.hp = HIT * ELITE_HITS
            self.walk = 1.35
            self.moves = scale_damage(guard_moveset(rng), 1.3)
            self.ai = dict(ELITE_AI)
            self.map_art = _map_art(self.cid, 1.12)
        else:
            self.name = "GENOME SOLDIER"
            self.cid = "ryu" if index % 2 == 0 else "ken"
            self.level = 4
            self.hp = HIT * GUARD_HITS
            self.walk = 1.5
            self.moves = guard_moveset(rng)
            self.ai = dict(GUARD_AI)
            self.map_art = _map_art(self.cid)

    def rect(self):
        return pygame.Rect(round(self.x) - 5, round(self.y) - 4, 10, 8)


def make_boss(rng):
    """REVOLVER KEN and the two soldiers he brings up the elevator."""
    b = Guard(rng, dict(kind="guard", route=[(BOSS_FROM[0], BOSS_FROM[1], 0, 90)]), 1)
    b.kind = "boss"
    b.name = "REVOLVER KEN"
    b.cid = "ken"
    b.boss = True
    b.level = 6
    b.hp = HIT * BOSS_HITS
    b.walk = 1.5
    b.moves = boss_moves(rng)
    b.ai = dict(BOSS_AI)
    b.map_art = _map_art("ken", 1.15)
    b.allies = [Guard(rng, dict(kind="guard", route=[(BOSS_FROM[0], BOSS_FROM[1], 0, 90)]), i) for i in range(2)]
    b.chat_cd = 60
    return b


# ---------------------------------------------------------------------------
# art
# ---------------------------------------------------------------------------
SNOW_C = (206, 214, 230)
METAL_C = (74, 82, 98)
WALL_TOP_C = (30, 34, 48)
PANEL_C = (92, 100, 120)


def _px(rows, colors):
    """A little sprite from a character map: one char per pixel, '.' empty."""
    s = pygame.Surface((len(rows[0]), len(rows)), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c != ".":
                s.set_at((x, y), colors[c])
    return s


def _icons():
    o = (24, 16, 20)
    return {
        "keycard": _px(["kkkkkkkkkkk",
                        "kwwwwwwwwwk",
                        "kbbbbbbbbbk",
                        "kwwwwwwyywk",
                        "kwggwwwyywk",
                        "kwwwwwwwwwk",
                        "kkkkkkkkkkk"], dict(k=o, w=(230, 236, 246), b=(40, 60, 120), y=(230, 200, 70),
                                             g=(120, 130, 150))),
        "c4": _px(["..rrr......",
                   ".r...r.....",
                   "kkkkkkkkkkk",
                   "kccccccccck",
                   "kcwwwccgcck",
                   "kccccccccck",
                   "kkkkkkkkkkk"], dict(k=o, c=(196, 186, 140), w=(240, 240, 230), g=(60, 220, 80),
                                         r=(220, 40, 40))),
        "lifeup": _px([".kk...kk..",
                       "krrk.krrk.",
                       "krwrkrrrk.",
                       "krrrrrrrk.",
                       ".krrrrrk..",
                       "..krrrk...",
                       "...krk....",
                       "....k....."], dict(k=o, r=(230, 50, 60), w=(255, 220, 220))),
        "powup": _px(["..kkkkk...",
                      ".kyyyyyk..",
                      "kyykkkyyk.",
                      "kyykyyyyk.",
                      "kyykkkyyk.",
                      "kyyyyykyk.",
                      "kyykkkyyk.",
                      ".kyyyyyk..",
                      "..kkkkk..."], dict(k=o, y=(255, 200, 40))),
    }


def _make_tiles(rng):
    t = {}
    snow = []
    for v in range(4):
        s = pygame.Surface((T, T))
        s.fill(SNOW_C)
        for _ in range(10):
            s.set_at((rng.randrange(T), rng.randrange(T)), rng.choice(((236, 242, 252), (184, 194, 214))))
        if v == 3:
            for x in range(2, 14, 3):
                s.set_at((x, 9 + (x % 2)), (176, 186, 206))
        snow.append(s)
    t["snow"] = snow
    metal = []
    for v in range(3):
        s = pygame.Surface((T, T))
        s.fill(METAL_C)
        g = shade(METAL_C, 0.8)
        for y in range(2, 16, 4):
            pygame.draw.line(s, g, (1, y), (14, y))
        pygame.draw.line(s, shade(METAL_C, 1.18), (0, 0), (15, 0))
        pygame.draw.line(s, shade(METAL_C, 0.7), (0, 15), (15, 15))
        for p in ((1, 1), (14, 1), (1, 14), (14, 14)):
            s.set_at(p, (120, 128, 146))
        if v == 2:
            pygame.draw.line(s, (60, 66, 80), (4, 6), (9, 10))
        metal.append(s)
    t["metal"] = metal
    top = pygame.Surface((T, T))
    top.fill(WALL_TOP_C)
    for _ in range(6):
        top.set_at((rng.randrange(T), rng.randrange(T)), (60, 66, 84))
    t["wall_top"] = top
    snowy = top.copy()
    for _ in range(14):
        snowy.set_at((rng.randrange(T), rng.randrange(T)), (200, 208, 226))
    t["wall_top_snow"] = snowy
    face = pygame.Surface((T, T))
    face.fill(PANEL_C)
    pygame.draw.line(face, shade(PANEL_C, 0.7), (7, 0), (7, 15))
    pygame.draw.line(face, shade(PANEL_C, 0.7), (0, 9), (15, 9))
    pygame.draw.line(face, shade(PANEL_C, 1.3), (0, 0), (15, 0))
    pygame.draw.line(face, shade(PANEL_C, 0.55), (0, 15), (15, 15))
    for p in ((2, 3), (12, 3), (2, 12), (12, 12)):
        face.set_at(p, (140, 148, 166))
    t["wall_face"] = face
    # an olive army crate seen from above, front edge showing
    crate = pygame.Surface((T, T), pygame.SRCALPHA)
    crate.fill((92, 98, 62), (0, 0, 16, 12))
    crate.fill((64, 70, 42), (0, 12, 16, 4))
    pygame.draw.rect(crate, (50, 54, 32), (0, 0, 16, 16), 1)
    pygame.draw.line(crate, (112, 120, 78), (1, 1), (14, 1))
    pygame.draw.line(crate, (70, 76, 46), (2, 2), (13, 10))
    pygame.draw.line(crate, (70, 76, 46), (13, 2), (2, 10))
    crate.fill((220, 220, 200), (6, 13, 4, 1))
    t["crate"] = crate
    t["truck"] = _truck()
    # a generator: a yellow-and-grey box with a fan grille and warning stripes
    gen = pygame.Surface((T, T), pygame.SRCALPHA)
    gen.fill((120, 124, 110), (1, 1, 14, 11))
    gen.fill((84, 88, 76), (1, 12, 14, 4))
    pygame.draw.rect(gen, (40, 42, 36), (1, 1, 14, 15), 1)
    pygame.draw.circle(gen, (50, 54, 48), (6, 6), 4)
    pygame.draw.line(gen, (150, 154, 140), (3, 6), (9, 6))
    pygame.draw.line(gen, (150, 154, 140), (6, 3), (6, 9))
    for k in range(0, 12, 4):
        gen.fill((230, 190, 40), (2 + k, 13, 2, 2))
    gen.fill((40, 220, 80), (12, 3, 2, 2))
    t["gen"] = gen
    # cell bars
    bars = pygame.Surface((T, T), pygame.SRCALPHA)
    for x in range(1, T, 4):
        bars.fill((150, 156, 170), (x, 0, 2, T))
        bars.fill((210, 216, 230), (x, 0, 1, T))
    bars.fill((90, 96, 110), (0, 7, T, 2))
    t["bars"] = bars
    # keycard door
    door = pygame.Surface((T, T))
    door.fill((70, 76, 92))
    pygame.draw.rect(door, (40, 44, 56), (0, 0, T, T), 1)
    pygame.draw.line(door, (50, 54, 66), (8, 1), (8, 14))
    door.fill((230, 190, 40), (2, 13, 12, 2))
    t["door"] = door
    t["bush"] = _bush(rng)
    return t


def _bush(rng):
    """A snowy shrub, drawn over whoever stands in it."""
    s = pygame.Surface((20, 20), pygame.SRCALPHA)
    for cx, cy, r in ((6, 10, 6), (14, 10, 6), (10, 6, 6), (10, 13, 6)):
        pygame.draw.circle(s, (28, 70, 44), (cx, cy), r)
    for cx, cy, r in ((6, 9, 4), (14, 9, 4), (10, 5, 4)):
        pygame.draw.circle(s, (46, 104, 62), (cx, cy), r)
    for _ in range(12):
        s.set_at((rng.randrange(3, 17), rng.randrange(3, 16)), (70, 136, 84))
    for x, y in ((5, 4), (9, 1), (10, 2), (14, 4), (4, 5), (15, 5), (11, 1), (8, 2)):
        s.fill((236, 242, 252), (x, y, 2, 1))
    return s


def _truck():
    s = pygame.Surface((64, 32), pygame.SRCALPHA)
    for x in (6, 16, 34, 52):
        s.fill((18, 18, 22), (x, 0, 7, 3))
        s.fill((18, 18, 22), (x, 29, 7, 3))
    s.fill((92, 100, 70), (1, 2, 46, 28))                  # canvas back
    for x in range(5, 46, 6):
        pygame.draw.line(s, (72, 80, 54), (x, 3), (x, 28))
    pygame.draw.rect(s, (52, 58, 38), (1, 2, 46, 28), 1)
    rng = random.Random(8)
    for _ in range(26):                                     # snow on the canvas
        s.fill((226, 232, 242), (rng.randrange(3, 44), rng.randrange(4, 27), 2, 1))
    s.fill((70, 78, 58), (48, 4, 15, 24))                  # cab
    pygame.draw.rect(s, (44, 50, 34), (48, 4, 15, 24), 1)
    s.fill((150, 182, 204), (58, 7, 3, 18))                # windscreen
    s.fill((210, 230, 240), (59, 8, 1, 6))
    s.fill((255, 230, 140), (62, 5, 1, 3))
    s.fill((255, 230, 140), (62, 24, 1, 3))
    return s


def _box_sprites():
    """The cardboard box Akuma wears: still, and two shuffle frames."""
    out = []
    for k in range(3):
        s = pygame.Surface((20, 18), pygame.SRCALPHA)
        y0 = 2 if k == 0 else (1 if k == 1 else 3)
        s.fill((176, 132, 78), (1, y0 + 4, 18, 11))        # front
        s.fill((198, 156, 98), (1, y0, 18, 5))              # top
        pygame.draw.line(s, (150, 110, 62), (10, y0), (10, y0 + 4))
        pygame.draw.rect(s, (110, 76, 40), (1, y0, 18, 15), 1)
        s.fill((30, 20, 14), (5, y0 + 7, 10, 2))            # the slit
        if k:
            s.set_at((8, y0 + 7), (255, 255, 255))
            s.set_at((11, y0 + 7), (255, 255, 255))
        s.fill((120, 160, 210), (13, y0 + 11, 4, 2))        # a printed label
        out.append(s)
    pick = pygame.Surface((16, 12), pygame.SRCALPHA)
    pick.fill((176, 132, 78), (1, 3, 14, 8))
    pick.fill((198, 156, 98), (1, 1, 14, 3))
    pygame.draw.rect(pick, (110, 76, 40), (1, 1, 14, 10), 1)
    out.append(pick)
    return out


def _codec_portrait(cid):
    img = pygame.transform.scale(portrait(cid), (60, 60))
    img.fill((150, 255, 170), special_flags=pygame.BLEND_RGB_MULT)
    for y in range(0, 60, 2):                                # scanlines
        img.fill((200, 210, 200), (0, y, 60, 1), special_flags=pygame.BLEND_RGB_MULT)
    return img


def _body_img(art, face):
    """A soldier lying in the snow: his idle frame turned on its side."""
    img, _ = art.frame(face, False, 0, 0)
    return pygame.transform.rotate(img, -90 if face > 0 else 90)


# ---------------------------------------------------------------------------
class StealthScene:
    def __init__(self, game, seed=None, level=8, hp=None):
        F.init_shared()
        _sounds()
        self.game = game
        self.level = level
        self.rng = random.Random(seed)
        self.grid = _rows()
        self.gw, self.gh = len(self.grid[0]), len(self.grid)
        self.mw, self.mh = self.gw * T, self.gh * T
        self.tiles = _make_tiles(random.Random(seed or 0))
        self.box_img = _box_sprites()
        self.icons = _icons()
        self.art = _map_art("akuma")
        self.menu = PauseMenu(game, CONTROLS)
        self.exit_tiles = set()
        self.gens = {}
        self.box_pickup = None
        for y, row in enumerate(self.grid):
            for x, c in enumerate(row):
                if c == "P":
                    self.px, self.py = (x + 0.5) * T, (y + 0.5) * T
                elif c == "B":
                    self.box_pickup = [(x + 0.5) * T, (y + 0.5) * T]
                elif c == "E":
                    self.exit_tiles.add((x, y))
                elif c == "G":
                    self.gens[(x, y)] = False
        self.passable = [(x, y) for y in range(self.gh) for x in range(self.gw) if not self.solid(x, y)]
        self.power = True            # the generators still run
        self._render()
        self.guards = [Guard(self.rng, spec, i) for i, spec in enumerate(GUARDS)]
        self.cameras = [dict(x=(tx + 0.5) * T, y=(ty + 1) * T - 2, base=math.radians(b), sweep=math.radians(s),
                             period=p, angle=math.radians(b), t=self.rng.randrange(p), flash=0)
                        for (tx, ty), b, s, p in CAMERAS]
        self.lasers = [dict(x=(a[0] + 0.5) * T, y0=a[1] * T, y1=(b[1] + 1) * T, on=on, off=off,
                            t=self.rng.randrange(on + off)) for a, b, on, off in LASERS]
        self.hp = game.akuma_max if hp is None else hp
        self.pface = 1
        self.pvx = self.pvy = 0.0
        self.walked = 0.0
        self.moving = False
        self.still = 99            # frames Akuma has not moved
        self.sneaking = False
        self.has_box = False
        self.box_on = False
        self.invuln = 0
        self.steps = 0
        self.footprints = deque(maxlen=120)
        self.flakes = [[self.rng.uniform(0, W), self.rng.uniform(0, H), self.rng.uniform(0.2, 0.6)]
                       for _ in range(46)]
        self.ripples = []
        self.leaves = []
        self.pops = []             # floating "+15" texts
        # alert state: normal, alert, evasion, caution
        self.phase = "normal"
        self.timer = 0
        self.lkp = (self.px, self.py)
        self.freeze = 0
        self.ignore_player = False  # tests / bots
        self.messages = []
        self.encounter = None
        self.encounter_t = 0
        self._fields = {}
        self.chat_cd = 120
        self._decks = {}
        # neck snaps and what they leave behind
        self.snap = None
        self.bodies = []
        # the missions
        self.mission = 0
        self.keycard = False
        self.c4 = 0
        self.detonate = 0
        self.shake = 0
        self.items = self._place_items(seed)
        self.prisoner = SimpleNamespace(x=(PRISONER_AT[0] + 0.5) * T, y=(PRISONER_AT[1] + 0.5) * T, free=False,
                                        say=None, chat_cd=200, face=1, art=_map_art("sakura"))
        self.boss_g = None
        # intro: codec call, then the level card
        self.stage = "ring"         # ring, codec, card, play
        self.codec_lines = CODEC["intro"]
        self.after_codec = "card"
        self.t = 0
        self.line = 0
        self.chars = 0
        self.result = None
        self.anim = 0
        self._portraits = {}

    def _place_items(self, seed):
        items = [dict(kind="keycard", x=(KEYCARD_AT[0] + 0.5) * T, y=(KEYCARD_AT[1] + 0.5) * T)]
        rng = random.Random((seed or 0) + 5)
        for kind, (tx, ty) in PICKUPS:
            it = dict(kind=kind, x=(tx + 0.5) * T, y=(ty + 0.5) * T)
            if kind in ("snack", "bento"):
                it["kind"], it["name"] = "snack", "BENTO" if kind == "bento" else random_snack(rng)
            items.append(it)
        # snacks in random corners of the open base (not in the rooms, not by the start)
        sx, sy = int(self.px // T), int(self.py // T)
        spots = [(x, y) for x, y in self.passable if self.tile(x, y) in ".:,;"
                 and not (x >= 46 and (y >= 25 or 8 <= y <= 12)) and not (9 <= x <= 14 and y <= 6)
                 and abs(x - sx) + abs(y - sy) > 8 and not (x >= 45 and y <= 4)]
        rng.shuffle(spots)
        taken = []
        for x, y in spots:
            if len(taken) >= N_SNACKS:
                break
            if all(abs(x - a) + abs(y - b) > 9 for a, b in taken):
                taken.append((x, y))
                items.append(dict(kind="snack", name=random_snack(rng), x=(x + 0.5) * T, y=(y + 0.5) * T))
        return items

    # ---- map queries ------------------------------------------------------
    def tile(self, tx, ty):
        if 0 <= tx < self.gw and 0 <= ty < self.gh:
            return self.grid[ty][tx]
        return "#"

    def solid(self, tx, ty):
        return self.tile(tx, ty) in SOLID

    def in_shadow(self, x, y):
        c = self.tile(int(x // T), int(y // T))
        return c in SHADOW or (not self.power and c in INDOOR)

    def in_bush(self, x=None, y=None):
        x = self.px if x is None else x
        y = self.py if y is None else y
        return self.tile(int(x // T), int(y // T)) == "b"

    def rect_hits(self, r):
        for ty in range(r.top // T, (r.bottom - 1) // T + 1):
            for tx in range(r.left // T, (r.right - 1) // T + 1):
                if self.solid(tx, ty):
                    return True
        return False

    def line_of_sight(self, x0, y0, x1, y1):
        d = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(d / 4))
        for i in range(1, n + 1):
            t = i / n
            if self.solid(int((x0 + (x1 - x0) * t) // T), int((y0 + (y1 - y0) * t) // T)):
                return False
        return True

    def player_rect(self):
        return pygame.Rect(round(self.px) - 5, round(self.py) - 4, 10, 8)

    def set_tile(self, tx, ty, c):
        row = self.grid[ty]
        self.grid[ty] = row[:tx] + c + row[tx + 1:]
        self._fields.clear()
        self.passable = [(x, y) for y in range(self.gh) for x in range(self.gw) if not self.solid(x, y)]
        self._render()

    @property
    def paused(self):
        return self.menu.open

    def message(self, text, frames=120):
        if not self.messages or self.messages[-1][0] != text:
            self.messages.append([text, frames])

    def speak(self, who, text, frames=None):
        who.say = [text, frames or max(120, 40 + len(text) * 4)]

    def _line(self, key, pool):
        """Next line from a shuffled deck, so nobody repeats himself soon."""
        deck = self._decks.get(key)
        if not deck:
            deck = list(pool)
            self.rng.shuffle(deck)
            self._decks[key] = deck
        return deck.pop()

    @property
    def objective(self):
        if self.mission == 1:
            return OBJECTIVES[1] % sum(self.gens.values())
        return OBJECTIVES[min(self.mission, 3)]

    # ---- art --------------------------------------------------------------
    def _render(self):
        rng = random.Random(77)
        surf = pygame.Surface((self.mw, self.mh))
        dark = pygame.Surface((self.mw, self.mh), pygame.SRCALPHA)
        night = pygame.Surface((self.mw, self.mh), pygame.SRCALPHA)   # the hangar with the power cut
        trucks = []
        self.bushes = []
        for ty in range(self.gh):
            for tx in range(self.gw):
                c = self.tile(tx, ty)
                x, y = tx * T, ty * T
                outdoor = c in SNOW
                if c == "#":
                    if not self.solid(tx, ty + 1) and ty + 1 < self.gh:
                        surf.blit(self.tiles["wall_face"], (x, y))
                    else:
                        surf.blit(self.tiles["wall_top_snow" if ty in (0, 13) or ty > 13 or tx in (0, 55)
                                             else "wall_top"], (x, y))
                    continue
                if c in "CTG":
                    outdoor = ty > 13 and not (tx >= 46 and ty >= 25)
                floor = self.tiles["snow"][rng.choice((0, 0, 1, 2, 3))] if outdoor else \
                    self.tiles["metal"][rng.choice((0, 0, 1, 2))]
                surf.blit(floor, (x, y))
                if c == "C":
                    surf.blit(self.tiles["crate"], (x, y))
                elif c == "G":
                    surf.blit(self.tiles["gen"], (x, y))
                elif c == "D":
                    surf.blit(self.tiles["bars"], (x, y))
                elif c == "K":
                    surf.blit(self.tiles["door"], (x, y))
                elif c == "b":
                    self.bushes.append((x - 2, y - 4))
                elif c == "T" and self.tile(tx - 1, ty) != "T" and self.tile(tx, ty - 1) != "T":
                    trucks.append((x, y))
                elif c == "E":
                    for k in range(0, T, 4):
                        surf.fill((220, 190, 40) if (k // 4 + tx) % 2 else (30, 30, 30), (x + k, y + 12, 4, 4))
                if c in SHADOW:
                    dark.fill((6, 10, 26, 135), (x, y, T, T))
                elif c in INDOOR or (not outdoor and c != "b"):
                    night.fill((6, 10, 26, 135), (x, y, T, T))
                if self.solid(tx, ty - 1) and not outdoor:
                    surf.fill((40, 44, 58), (x, y, T, 3))
        for x, y in trucks:
            surf.blit(self.tiles["truck"], (x, y))
        # the helipad
        hx, hy = (HELIPAD[0] + 0.5) * T, (HELIPAD[1] + 0.5) * T
        pygame.draw.circle(surf, (176, 180, 190), (hx, hy), 34, 3)
        pygame.draw.circle(surf, (226, 196, 70), (hx, hy), 30, 1)
        for dx in (-9, 9):
            surf.fill((226, 196, 70), (hx + dx - 2, hy - 12, 4, 24))
        surf.fill((226, 196, 70), (hx - 9, hy - 2, 18, 4))
        # elevator doors in the wall above the goal
        ex = min(x for x, _ in self.exit_tiles) * T
        surf.fill((120, 130, 150), (ex, 0, 3 * T, T))
        pygame.draw.line(surf, (60, 66, 80), (ex + 24, 2), (ex + 24, 15))
        pygame.draw.rect(surf, (50, 56, 70), (ex, 0, 3 * T, T), 1)
        surf.fill((80, 255, 120) if self.power else (255, 80, 60), (ex + 22, 2, 4, 2))
        self.map_surf = surf
        self.dark = dark
        self.night = night
        self.radar_map = self._render_radar()

    def _render_radar(self):
        s = pygame.Surface((self.gw * 4, self.gh * 4))
        s.fill((4, 26, 14))
        for ty in range(self.gh):
            for tx in range(self.gw):
                c = self.tile(tx, ty)
                if c in SOLID:
                    s.fill((40, 120, 66), (tx * 4, ty * 4, 4, 4))
                elif c == "b":
                    s.fill((20, 70, 36), (tx * 4, ty * 4, 4, 4))
        for tx, ty in self.exit_tiles:
            s.fill((200, 255, 200), (tx * 4, ty * 4, 4, 4))
        return s

    # ---- pathing -----------------------------------------------------------
    def _field(self, goal):
        f = self._fields.get(goal)
        if f is None:
            if len(self._fields) > 48:
                self._fields.clear()
            f = {goal: 0}
            q = deque([goal])
            while q:
                c = q.popleft()
                d = f[c] + 1
                for dx, dy in DIRS8:
                    n = (c[0] + dx, c[1] + dy)
                    if n in f or self.solid(*n):
                        continue
                    if dx and dy and (self.solid(c[0] + dx, c[1]) or self.solid(c[0], c[1] + dy)):
                        continue
                    f[n] = d
                    q.append(n)
            self._fields[goal] = f
        return f

    def _step_toward(self, g, tx, ty, speed):
        """Walk a soldier one frame along the shortest path to (tx, ty).
        Returns True once he is there."""
        d = math.hypot(tx - g.x, ty - g.y)
        if d < max(1.5, speed):
            g.x, g.y = tx, ty
            g.moving = False
            return True
        goal = (int(tx // T), int(ty // T))
        here = (int(g.x // T), int(g.y // T))
        if here == goal or (d < 20 and self.line_of_sight(g.x, g.y, tx, ty)):
            nx, ny = tx, ty
        else:
            f = self._field(goal)
            best, bd = None, f.get(here, 10 ** 6)
            for dx, dy in DIRS8:
                n = (here[0] + dx, here[1] + dy)
                v = f.get(n)
                if v is not None and v < bd:
                    if dx and dy and (self.solid(here[0] + dx, here[1]) or self.solid(here[0], here[1] + dy)):
                        continue
                    best, bd = n, v
            if best is None:
                nx, ny = tx, ty
            else:
                nx, ny = (best[0] + 0.5) * T, (best[1] + 0.5) * T
        dd = math.hypot(nx - g.x, ny - g.y) or 1
        vx, vy = (nx - g.x) / dd * speed, (ny - g.y) / dd * speed
        g.x += vx
        g.y += vy
        g.moving = True
        g.walked += speed
        if abs(vx) > 0.05:
            g.face = 1 if vx > 0 else -1
        self._turn(g, math.atan2(vy, vx), 0.15)
        return False

    @staticmethod
    def _turn(g, target, rate):
        diff = (target - g.angle + math.pi) % math.tau - math.pi
        g.angle += max(-rate, min(rate, diff))
        if abs(math.cos(g.angle)) > 0.3 and not g.moving:
            g.face = 1 if math.cos(g.angle) > 0 else -1

    # ---- seeing and hearing ------------------------------------------------
    def visibility(self):
        """What a watcher can see of Akuma: 'hidden' (still in the box, or in
        a bush), 'box' (a box shuffling along) or 'full'."""
        if self.ignore_player:
            return "hidden"
        if self.in_bush():
            return "hidden"
        if self.box_on:
            return "hidden" if self.still >= 3 else "box"
        return "full"

    def in_view(self, x, y, angle, half, reach, tx=None, ty=None):
        """Is the point (Akuma by default) inside this cone, in reach and in sight?"""
        if tx is None:
            tx, ty = self.px, self.py - 4
        d = math.hypot(tx - x, ty - y)
        if self.in_shadow(tx, ty + 4):
            reach *= SHADOW_K
        if self.phase == "caution":
            reach *= CAUTION_K
        if d > reach:
            return False
        if d > 6:
            if _angdiff(math.atan2(ty - y, tx - x), angle) > half:
                return False
        return self.line_of_sight(x, y, tx, ty)

    def guard_sees(self, g):
        return self.in_view(g.x, g.y - 4, g.angle, g.half, g.range)

    def behind(self, g, x=None, y=None):
        """Is (x, y) (Akuma) behind where this soldier is looking?"""
        x = self.px if x is None else x
        y = self.py if y is None else y
        return _angdiff(math.atan2(y - g.y, x - g.x), g.angle) > SNAP_BEHIND

    def _cone(self, x, y, angle, half, reach, cx, cy):
        pts = [(x - cx, y - cy)]
        n = 12
        for i in range(n + 1):
            a = angle - half + 2 * half * i / n
            ca, sa = math.cos(a), math.sin(a)
            r = 4
            while r < reach and not self.solid(int((x + ca * r) // T), int((y + sa * r) // T)):
                r += 4
            r = min(r, reach)
            pts.append((x + ca * r - cx, y + sa * r - cy))
        return pts

    # ---- alert phases ------------------------------------------------------
    def spotted(self, by=None):
        """Someone saw Akuma properly: ALERT (or keep it going)."""
        self.lkp = (self.px, self.py)
        if self.phase != "alert":
            audio.play("mgs_alert")
            self.phase = "alert"
            self.freeze = FREEZE
            self.message("ALERT!", 90)
            for g in self.guards:
                if g.alive:
                    g.state = "alert"
                    g.huh = 0
                    g.say = None
        if by is not None:
            if not by.exclaim:
                by.exclaim = 60
        self.timer = ALERT_T

    def _phases(self):
        if self.phase == "alert":
            if self.t % 44 == 0:
                audio.play("alarm", 0.45)
            self.timer -= 1
            if self.timer <= 0:
                self.phase = "evasion"
                self.timer = EVASION_T
                audio.play("mgs_evasion")
                self.message("EVASION", 90)
                for g in self.guards:
                    if g.alive:
                        g.state = "search"
                        g.search_to = None
        elif self.phase == "evasion":
            self.timer -= 1
            if self.timer <= 0:
                self.phase = "caution"
                self.timer = CAUTION_T
                audio.play("mgs_evasion", 0.6)
                self.message("CAUTION", 90)
                for g in self.guards:
                    if g.alive:
                        self._back_to_patrol(g)
        elif self.phase == "caution":
            self.timer -= 1
            if self.timer <= 0:
                self.phase = "normal"
                self.timer = 0
                audio.play("mgs_clear")
                self.message("ALL CLEAR", 80)
                live = [g for g in self.guards if g.alive]
                if live:
                    g = min(live, key=lambda o: math.hypot(o.x - self.px, o.y - self.py))
                    self.speak(g, self.rng.choice(CAUTION_OVER))

    def _back_to_patrol(self, g):
        g.state = "patrol"
        g.stim = None
        g.notice = 0
        # rejoin the beat at its nearest stop
        g.ri = min(range(len(g.route)), key=lambda i: math.hypot(g.route[i][0] - g.x, g.route[i][1] - g.y))
        g.wait = 0

    def _suspect(self, g, x, y, sound=True, why=None):
        if g.state not in ("patrol", "suspicious"):
            return
        if g.state != "suspicious" or g.sub == "search":
            g.sub = "look"
            g.t = 0
            if sound:
                audio.play("mgs_huh", 0.8)
            g.huh = 50
            g.why = why or ("box" if self.box_on else "noise")
            self.speak(g, HUH[g.why], 110)
        g.state = "suspicious"
        g.stim = (x, y)

    # ---- update ------------------------------------------------------------
    def update(self, inp):
        if self.encounter:
            self.encounter_t += 1
            if self.encounter_t >= 14:
                g, ambush = self.encounter
                self.encounter = None
                self.game.start_fight(g, self.hp, ambush)
            return
        if self.menu.open:
            self.menu.update(inp)
            return
        self.t += 1
        self.anim += 1
        if self.stage == "ring":
            if self.t in (1, 34):
                audio.play("codec")
            if self.t >= 60 or (self.t > 10 and inp.any_pressed("punch", "kick", "special", "start")):
                self.stage, self.t = "codec", 0
                audio.play("codec_beep")
            return
        if self.stage == "codec":
            self._codec(inp)
            return
        if self.stage == "card":
            if self.t >= 100 or (self.t > 20 and inp.any_pressed("punch", "kick", "special", "start")):
                self.stage, self.t = "play", 0
            return
        if self.menu.toggle(inp):
            return
        for m in self.messages[:1]:
            m[1] -= 1
        self.messages = [m for m in self.messages if m[1] > 0]
        self._weather()
        if self.freeze:
            self.freeze -= 1          # the world holds still for the "!" sting
            return
        if self.invuln:
            self.invuln -= 1
        if self.shake:
            self.shake -= 1
        if self.chat_cd:
            self.chat_cd -= 1
        if self.snap:
            self._snapping()
        else:
            self._move(inp)
            self._items(inp)
        if self.power:
            for c in self.cameras:
                self._camera(c)
            for lz in self.lasers:
                self._laser(lz)
        vis = self.visibility()
        for g in self.guards:
            if g.alive and not (self.snap and self.snap["g"] is g):
                self._guard(g, vis)
        self._phases()
        self._missions()
        self._touch()

    def _ring(self, key, after="play"):
        """Start a codec call (ringing first)."""
        self.codec_lines = CODEC[key]
        self.after_codec = after
        self.stage, self.t, self.line, self.chars = "ring", 0, 0, 0
        self.pvx = self.pvy = 0.0

    def _codec(self, inp):
        who, text = self.codec_lines[self.line]
        if self.chars < len(text):
            self.chars += 1 if self.t % 2 == 0 else 0
            if self.t % 6 == 0 and text[min(self.chars, len(text) - 1)] != " ":
                audio.play("codec_beep", 0.4)
        if inp.any_pressed("punch", "kick", "special", "start"):
            if self.chars < len(text):
                self.chars = len(text)
            else:
                self.line += 1
                self.chars = 0
                audio.play("codec_beep")
                if self.line >= len(self.codec_lines):
                    self._end_codec()
        if inp.pressed("back"):
            self._end_codec()

    def _end_codec(self):
        self.line = min(self.line, len(self.codec_lines) - 1)
        self.stage, self.t = self.after_codec, 0
        if self.after_codec == "card":
            audio.play("fight")
        if self.codec_lines is CODEC["rescue"] and self.boss_g is None:
            self._boss_arrives()

    def _weather(self):
        for f in self.flakes:
            f[1] += f[2]
            f[0] += math.sin((self.anim + f[1]) / 30) * 0.2
            if f[1] > H:
                f[1] = -2
                f[0] = self.rng.uniform(0, W)
        for r in self.ripples:
            r[2] += 1
        self.ripples = [r for r in self.ripples if r[2] < 30]
        for p in self.leaves:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.05
            p[4] -= 1
        self.leaves = [p for p in self.leaves if p[4] > 0]
        for p in self.pops:
            p[1] -= 0.4
            p[3] -= 1
        self.pops = [p for p in self.pops if p[3] > 0]

    def _move(self, inp):
        dx = (1 if inp.held("right") else 0) - (1 if inp.held("left") else 0)
        dy = (1 if inp.held("down") else 0) - (1 if inp.held("up") else 0)
        self.sneaking = inp.held("kick") and not self.box_on
        base = BOX_SPEED if self.box_on else SNEAK if self.sneaking else WALK
        sp = base * (0.7071 if dx and dy else 1)
        self.pvx += (dx * sp - self.pvx) * 0.3
        self.pvy += (dy * sp - self.pvy) * 0.3
        if not dx and abs(self.pvx) < 0.05:
            self.pvx = 0.0
        if not dy and abs(self.pvy) < 0.05:
            self.pvy = 0.0
        moved = 0.0
        was_bush = self.in_bush()
        if self.pvx or self.pvy:
            ox, oy = self.px, self.py
            self._slide(self.pvx, 0)
            self._slide(0, self.pvy)
            moved = math.hypot(self.px - ox, self.py - oy)
            self.walked += moved
        self.moving = moved > 0.2
        self.still = 0 if self.moving else self.still + 1
        if dx:
            self.pface = dx
        if self.in_bush() != was_bush or (self.moving and self.in_bush() and self.steps % 24 == 0):
            audio.play("rustle", 0.6)
            for _ in range(4):
                self.leaves.append([self.px + self.rng.uniform(-6, 6), self.py - self.rng.uniform(4, 12),
                                    self.rng.uniform(-0.5, 0.5), -self.rng.uniform(0.3, 0.9), 26])
        if self.moving:
            self.steps += 1
            loud = not self.sneaking and not self.box_on
            if self.steps % (18 if loud else 30) == 0:
                audio.play("step", 0.5 if loud else 0.15)
                if not self.box_on and self.tile(int(self.px // T), int(self.py // T)) in ",;P":
                    self.footprints.append([self.px + (2 if (self.steps // 18) % 2 else -2), self.py + 2, 700])
            if loud and self.steps % 10 == 0:
                self._noise(HEAR)

    def _slide(self, dx, dy):
        nx, ny = self.px + dx, self.py + dy
        r = pygame.Rect(round(nx) - 5, round(ny) - 4, 10, 8)
        if not self.rect_hits(r):
            self.px, self.py = nx, ny
            return
        for nudge in (1, -1, 2, -2, 3, -3):
            r2 = r.move(0, nudge) if dx else r.move(nudge, 0)
            if not self.rect_hits(r2):
                if dx:
                    self.py += nudge * 0.5
                else:
                    self.px += nudge * 0.5
                return

    def _noise(self, radius, x=None, y=None):
        if self.ignore_player:
            return
        x = self.px if x is None else x
        y = self.py if y is None else y
        for g in self.guards:
            if g.alive and g.state in ("patrol", "suspicious") and math.hypot(g.x - x, g.y - y) < radius:
                self._suspect(g, x, y, why="noise")

    # ---- neck snaps --------------------------------------------------------
    def snap_target(self):
        """The unaware soldier Akuma is right behind, if any."""
        if self.box_on or self.snap:
            return None
        best, bd = None, SNAP_RANGE
        for g in self.guards:
            if not g.alive or g.state == "alert":
                continue
            d = math.hypot(g.x - self.px, g.y - self.py)
            if d < bd and self.behind(g):
                best, bd = g, d
        return best

    def start_snap(self, g):
        self.snap = dict(g=g, t=0)
        self.pvx = self.pvy = 0.0
        self.moving = False
        g.moving = False
        g.say = None
        g.huh = g.exclaim = 0
        self.pface = 1 if g.x > self.px else -1
        audio.play("grab")

    def _snapping(self):
        s = self.snap
        g = s["g"]
        s["t"] += 1
        # pull in tight behind him
        bx, by = g.x - math.cos(g.angle) * 7, g.y - math.sin(g.angle) * 4
        if not self.rect_hits(pygame.Rect(round(bx) - 5, round(by) - 4, 10, 8)):
            self.px += (bx - self.px) * 0.3
            self.py += (by - self.py) * 0.3
        if s["t"] == 4:
            self.speak(g, "GURK!", 40)
        if s["t"] == SNAP_KILL:
            audio.play("neck_snap")
            self.ripples.append([g.x, g.y - 14, 10])
        if s["t"] >= SNAP_T:
            g.alive = False
            g.say = None
            self.snap = None
            self.game.kills = getattr(self.game, "kills", 0) + 1
            self.bodies.append(dict(x=g.x, y=g.y, img=_body_img(g.map_art, g.face), found=False))
            self.message("SILENT TAKEDOWN", 90)

    # ---- items and missions -----------------------------------------------
    def _items(self, inp):
        pr = self.player_rect()
        bp = self.box_pickup
        if bp and pr.colliderect(pygame.Rect(bp[0] - 7, bp[1] - 6, 14, 12)):
            self.box_pickup = None
            self.has_box = True
            self.box_on = True
            self.still = 0
            audio.play("mgs_item")
            self.message("CARDBOARD BOX: EQUIPPED", 150)
            self.message("L / SPACE: TAKE IT OFF AND ON", 120)
        for it in list(self.items):
            if pr.colliderect(pygame.Rect(it["x"] - 7, it["y"] - 7, 14, 14)):
                self.items.remove(it)
                self._pickup(it)
        if self.has_box and inp.pressed("special"):
            self.box_on = not self.box_on
            audio.play("box_on" if self.box_on else "box_off")
        # keycard doors open as he walks up with the card
        near = pr.inflate(12, 12)
        for ty in range(near.top // T, (near.bottom - 1) // T + 1):
            for tx in range(near.left // T, (near.right - 1) // T + 1):
                if self.tile(tx, ty) == "K":
                    if self.keycard:
                        self.set_tile(tx, ty, ".")
                        audio.play("door_open")
                        self.message("ACCESS GRANTED", 90)
                    else:
                        self.message("LOCKED: KEYCARD NEEDED", 60)
                elif self.tile(tx, ty) == "D":
                    self.message("MAGNETIC LOCK. CUT THE POWER.", 60)
        if inp.pressed("punch") and not self.box_on:
            g = self.snap_target()
            if g is not None:
                self.start_snap(g)
                return
            if self._plant():
                return
            r = self.player_rect().inflate(10, 10)
            if self.rect_hits(r):
                audio.play("knock")
                self.ripples.append([self.px, self.py - 6, 0])
                self._noise(KNOCK_HEAR)

    def _pickup(self, it):
        k = it["kind"]
        mx = self.game.akuma_max
        if k == "snack":
            heal = heal_amount(it["name"], mx)
            self.hp = min(mx, self.hp + heal)
            audio.play("pickup")
            self.message("%s +%d" % (it["name"], heal), 100)
            self.pops.append([it["x"], it["y"] - 12, "+%d" % heal, 50])
        elif k == "keycard":
            self.keycard = True
            self.c4 = 3
            audio.play("mgs_item")
            self.message("KEYCARD AND C4 x3", 140)
            if self.mission == 0:
                self.mission = 1
                self._ring("keycard")
        elif k == "lifeup":
            self.game.akuma_max = mx + 20
            self.hp = min(self.game.akuma_max, self.hp + 20)
            audio.play("mgs_item")
            self.message("LIFE UP! MAX LIFE +20", 140)
            self.pops.append([it["x"], it["y"] - 12, "LIFE UP", 60])
        elif k == "powup":
            self.game.power = getattr(self.game, "power", 1.0) + 0.15
            audio.play("mgs_item")
            self.message("DAMAGE UP! POWER x%.2f" % self.game.power, 140)
            self.pops.append([it["x"], it["y"] - 12, "POWER UP", 60])

    def _plant(self):
        for (tx, ty), done in self.gens.items():
            if done or not pygame.Rect(tx * T, ty * T, T, T).inflate(22, 22).collidepoint(self.px, self.py):
                continue
            if self.c4 <= 0:
                self.message("NO C4. RAID THE BARRACKS FIRST.", 100)
                return True
            self.gens[(tx, ty)] = True
            self.c4 -= 1
            audio.play("plant")
            n = sum(self.gens.values())
            self.message("C4 PLANTED (%d/3)" % n, 110)
            if n == len(self.gens):
                self.detonate = DETONATE_T
                self.message("ALL CHARGES SET... DETONATING", 120)
            return True
        return False

    def _missions(self):
        if self.detonate:
            self.detonate -= 1
            if self.detonate % 20 == 0:
                audio.play("c4_beep")
            if self.detonate == 0:
                self._blackout()
        p = self.prisoner
        if not p.free:
            if p.say:
                p.say[1] -= 1
                if p.say[1] <= 0:
                    p.say = None
            p.chat_cd -= 1
            if p.chat_cd <= 0 and math.hypot(p.x - self.px, p.y - self.py) < 120:
                p.chat_cd = 600
                self.speak(p, "AKUMA-SAN?! OVER HERE!" if not self.power else self.rng.choice(PRISONER_LINES))
            if self.mission == 2 and self.player_rect().inflate(6, 6).colliderect(
                    pygame.Rect(p.x - 6, p.y - 6, 12, 12)):
                p.free = True
                self.mission = 3
                audio.play("mgs_item")
                self.message("PRISONER FREED", 120)
                self._ring("rescue")
        b = self.boss_g
        if b is not None and b.alive:
            b.anim += 1
            if b.say:
                b.say[1] -= 1
                if b.say[1] <= 0:
                    b.say = None
            tx, ty = (BOSS_POST[0] + 0.5) * T, (BOSS_POST[1] + 0.5) * T
            if self._step_toward(b, tx, ty, G_WALK + 0.2):
                self._turn(b, math.atan2(self.py - b.y, self.px - b.x), 0.1)
                b.face = 1 if self.px > b.x else -1
            b.chat_cd -= 1
            if b.chat_cd <= 0 and math.hypot(b.x - self.px, b.y - self.py) < 160:
                b.chat_cd = 300
                self.speak(b, self._line("boss", BOSS_LINES))

    def _blackout(self):
        self.power = False
        self.shake = 40
        audio.play("boom")
        for (tx, ty), done in self.gens.items():
            self.ripples.append([(tx + 0.5) * T, (ty + 0.5) * T, 0])
        for y, row in enumerate(self.grid):
            for x, c in enumerate(row):
                if c == "D":
                    self.grid[y] = self.grid[y][:x] + "." + self.grid[y][x + 1:]
        self.set_tile(PRISONER_AT[0], PRISONER_AT[1], self.tile(*PRISONER_AT))   # re-render
        self.message("POWER CUT!", 120)
        if self.phase == "normal":
            self.phase, self.timer = "caution", CAUTION_T
        if self.mission == 1:
            self.mission = 2
            self._ring("power")

    def _boss_arrives(self):
        b = make_boss(self.rng)
        b.x, b.y = (BOSS_FROM[0] + 0.5) * T, (BOSS_FROM[1] + 0.5) * T
        self.boss_g = b
        audio.play("mgs_alert", 0.6)
        self.message("THE ELEVATOR IS COMING UP...", 150)
        self.speak(b, "YOU'RE PRETTY GOOD.", 150)

    def _camera(self, c):
        c["t"] += 1
        c["angle"] = c["base"] + math.sin(c["t"] * math.tau / c["period"]) * c["sweep"]
        if c["flash"]:
            c["flash"] -= 1
        if self.visibility() == "full" and self.in_view(c["x"], c["y"], c["angle"], CAM_HALF, CAM_RANGE):
            c["flash"] = 40
            if self.phase != "alert":
                self.message("SPOTTED BY A CAMERA", 90)
            self.spotted()

    def _laser(self, lz):
        lz["t"] = (lz["t"] + 1) % (lz["on"] + lz["off"])
        if lz["t"] < lz["on"] and not self.ignore_player:
            if self.player_rect().colliderect(pygame.Rect(lz["x"] - 1, lz["y0"], 2, lz["y1"] - lz["y0"])):
                if self.phase != "alert":
                    self.message("INFRARED SENSOR TRIPPED", 90)
                self.spotted()

    # ---- the soldiers ------------------------------------------------------
    def _guard(self, g, vis):
        g.anim += 1
        if g.exclaim:
            g.exclaim -= 1
        if g.huh:
            g.huh -= 1
        if g.say:
            g.say[1] -= 1
            if g.say[1] <= 0:
                g.say = None
        if g.kind == "smoker" and g.state == "patrol" and g.anim % 46 == 0:
            g.puffs.append([g.x + g.face * 8, g.y - 22, 0])
        for p in g.puffs:
            p[0] += 0.12 + 0.1 * math.sin(p[2] / 9)
            p[1] -= 0.28
            p[2] += 1
        g.puffs = [p for p in g.puffs if p[2] < 70]
        sees = vis != "hidden" and self.guard_sees(g)
        d = math.hypot(self.px - g.x, self.py - g.y)
        # ---- noticing ----
        if sees:
            if g.state in ("alert", "search"):
                self.spotted(g)
            elif vis == "box":
                if d < BOX_SPOT:
                    self.message("IT'S AKUMA IN A BOX!", 100)
                    self.spotted(g)
                else:
                    self._suspect(g, self.px, self.py, why="box")
            else:
                reach = g.range * (SHADOW_K if self.in_shadow(self.px, self.py) else 1)
                g.notice += (2 if d < reach * 0.8 else 1) * (0.5 if g.kind == "smoker" else 1)
                if d < reach * NEAR_K or g.notice >= NOTICE_T or self.phase in ("evasion", "caution") \
                        and g.notice > NOTICE_T // 2:
                    self.spotted(g)
                else:
                    self._suspect(g, self.px, self.py, why="seen")
        elif g.notice:
            g.notice -= 0.25 if g.state == "suspicious" else 1
            g.notice = max(0, g.notice)
        if g.state in ("patrol", "suspicious"):
            self._look_for_bodies(g)
        # ---- acting ----
        if g.state == "patrol":
            self._patrol(g)
            self._chatter(g, d)
        elif g.state == "suspicious":
            self._investigate(g)
        elif g.state == "alert":
            if sees:
                tx, ty = self.px, self.py
            else:
                tx, ty = self.lkp
            if self._step_toward(g, tx, ty, G_RUN) and not sees:
                g.state = "search"            # lost him at the last known spot: look around
                g.search_to = None
        elif g.state == "search":
            self._search(g)

    def _chatter(self, g, d):
        g.chat_cd -= 1
        if g.chat_cd > 0 or g.say or self.chat_cd or d > 170:
            return
        g.chat_cd = self.rng.randint(900, 1800)
        self.chat_cd = CHAT_GAP
        self.speak(g, self._line(g.kind, CHATTER.get(g.kind, CHATTER["guard"])))

    def _look_for_bodies(self, g):
        for b in self.bodies:
            if b["found"] or self.in_bush(b["x"], b["y"]):
                continue
            if self.in_view(g.x, g.y - 4, g.angle, g.half, g.range, b["x"], b["y"] - 4):
                b["found"] = True
                g.state = "patrol"            # fresh suspicion, aimed at the body
                self._suspect(g, b["x"], b["y"], why="body")
                if self.phase == "normal":
                    self.phase, self.timer = "caution", CAUTION_T
                    self.message("A BODY WAS FOUND. CAUTION", 120)
                return

    def _patrol(self, g):
        x, y, wait, face = g.route[g.ri]
        if g.wait > 0:
            g.wait -= 1
            g.moving = False
            g.look_t += 1
            self._glance(g)
            if g.wait == 0:
                g.ri = (g.ri + 1) % len(g.route)
            return
        speed = G_CAUTION if self.phase == "caution" else G_WALK
        if self._step_toward(g, x, y, speed):
            g.wait = 10 ** 9 if g.post else wait
            g.look_base = face if face is not None else g.angle
            g.look_t = 0

    def _glance(self, g):
        """On post: stare one way; once a cycle look left, then right, then back."""
        c, L = g.look_t % g.cycle, g.cycle
        if c < L - 150:
            tgt = g.look_base
        elif c < L - 100:
            tgt = g.look_base - 0.9
        elif c < L - 50:
            tgt = g.look_base + 0.9
        else:
            tgt = g.look_base
        self._turn(g, tgt, 0.05)

    def _investigate(self, g):
        g.t += 1
        sx, sy = g.stim
        if g.sub == "look":
            g.moving = False
            self._turn(g, math.atan2(sy - g.y, sx - g.x), 0.12)
            if g.t >= 36:
                g.sub, g.t = "go", 0
        elif g.sub == "go":
            d = math.hypot(sx - g.x, sy - g.y)
            if d < 18:
                g.sub, g.t = "search", 0
                g.moving = False
                g.look_base = math.atan2(sy - g.y, sx - g.x) if d > 1 else g.angle
            else:
                # stop beside the spot, not on it (a box gets looked at, not walked into)
                ang = math.atan2(g.y - sy, g.x - sx)
                self._step_toward(g, sx + math.cos(ang) * 16, sy + math.sin(ang) * 16, G_WALK + 0.2)
                if g.t > 60 * 12:
                    g.sub, g.t = "search", 0
        else:
            g.moving = False
            self._turn(g, g.look_base + math.sin(g.t / 26) * 1.0, 0.07)
            if g.t >= 150:
                self.speak(g, self.rng.choice(GIVE_UP.get(g.why, GIVE_UP["noise"])), 150)
                self._back_to_patrol(g)

    def _search(self, g):
        if g.search_to is None:
            lx, ly = int(self.lkp[0] // T), int(self.lkp[1] // T)
            f = self._field((lx, ly))
            near = [c for c, v in f.items() if v <= 7]
            c = self.rng.choice(near) if near else (lx, ly)
            g.search_to = ((c[0] + 0.5) * T, (c[1] + 0.5) * T)
            g.t = 0
        if g.t:
            g.t -= 1
            g.moving = False
            self._turn(g, g.look_base + math.sin(g.t / 20) * 1.2, 0.09)
            if g.t == 0:
                g.search_to = None
            return
        if self._step_toward(g, *g.search_to, G_SEARCH):
            g.t = 70
            g.look_base = g.angle

    def _touch(self):
        if self.invuln:
            return
        pr = self.player_rect()
        b = self.boss_g
        if b is not None and b.alive and pr.inflate(4, 4).colliderect(b.rect()):
            if self.phase != "alert":
                self.phase, self.timer = "alert", ALERT_T
            self.encounter = (b, False)
            self.encounter_t = 0
            audio.play("encounter")
            return
        if self.ignore_player:
            return
        for g in self.guards:
            if not g.alive or not pr.colliderect(g.rect()) or (self.snap and self.snap["g"] is g):
                continue
            aware = g.state in ("alert", "search") or self.phase in ("alert", "evasion")
            hidden = self.box_on or self.in_bush()
            if hidden and not aware:
                self.message("IT'S AKUMA IN A %s!" % ("BUSH" if self.in_bush() else "BOX"), 100)
                self.spotted(g)
                aware = True
            elif not aware and self.behind(g):
                continue                     # right behind him and he hasn't noticed: snap him
            g.allies = []
            if aware:
                if self.phase != "alert":
                    self.spotted(g)
                near = sorted((o for o in self.guards if o is not g and o.alive and o.state == "alert"),
                              key=lambda o: math.hypot(o.x - self.px, o.y - self.py))
                g.allies = [o for o in near if math.hypot(o.x - self.px, o.y - self.py) < 110][:2]
                for o in g.allies:
                    o.allies = []
            self.encounter = (g, not aware)
            self.encounter_t = 0
            audio.play("encounter")
            return

    def after_fight(self, result, hp, enemy):
        self.hp = hp
        self.invuln = INVULN
        if result == "win":
            down = [enemy] + list(getattr(enemy, "allies", []) or [])
            for g in down:
                g.alive = False
                g.allies = []
            elite = sum(1 for g in down if getattr(g, "kind", "") == "elite")
            if elite and len(down) == 1:
                self.message("RED BERET DOWN", 110)
            else:
                self.message("%d SOLDIER%s DOWN" % (len(down), "S" if len(down) > 1 else ""), 110)
            if self.phase == "alert":
                self.phase = "evasion"
                self.timer = EVASION_T
                for g in self.guards:
                    if g.alive:
                        g.state = "search"
                        g.search_to = None
        elif result == "escape":
            if self.phase == "alert":
                self.phase, self.timer = "evasion", EVASION_T

    # ---- drawing -----------------------------------------------------------
    def camera(self):
        cx = int(self.px - W / 2)
        cy = int(self.py - H / 2)
        cx, cy = max(0, min(self.mw - W, cx)), max(0, min(self.mh - H, cy))
        if self.shake:
            cx += self.rng.randint(-3, 3)
            cy += self.rng.randint(-2, 2)
        return cx, cy

    def draw(self, surf):
        if self.stage in ("ring", "codec"):
            self._draw_codec(surf)
            return
        cx, cy = self.camera()
        surf.fill((0, 0, 0))
        surf.blit(self.map_surf, (0, 0), (cx, cy, W, H))
        view = pygame.Rect(cx - 100, cy - 100, W + 200, H + 200)
        for fx, fy, life in self.footprints:
            surf.fill((150, 162, 190), (round(fx) - cx, round(fy) - cy, 2, 1))
        # generators: a blinking C4 on the planted ones
        for (tx, ty), done in self.gens.items():
            x, y = tx * T - cx, ty * T - cy
            if done and self.power:
                surf.blit(self.icons["c4"], (x + 3, y + 8))
                if (self.anim // 10) % 2:
                    surf.fill((255, 40, 40), (x + 11, y + 10, 2, 2))
            elif not self.power:
                pygame.draw.line(surf, (30, 30, 30), (x + 2, y + 2), (x + 13, y + 12), 2)
                pygame.draw.line(surf, (30, 30, 30), (x + 13, y + 3), (x + 4, y + 13), 2)
        # bodies
        for b in self.bodies:
            img = b["img"]
            surf.blit(img, (round(b["x"]) - img.get_width() // 2 - cx, round(b["y"]) - img.get_height() + 4 - cy))
        # pickups
        for it in self.items:
            x, y = round(it["x"]) - cx, round(it["y"]) - cy + round(math.sin(self.anim / 14 + it["x"]) * 1.5)
            if not (-16 < x < W + 16 and -16 < y < H + 16):
                continue
            img = snack_image(it["name"]) if it["kind"] == "snack" else self.icons[it["kind"]]
            pygame.draw.ellipse(surf, (40, 46, 70), (x - 5, round(it["y"]) - cy + 3, 10, 3))
            surf.blit(img, (x - img.get_width() // 2, y - img.get_height() // 2 - 2))
            if it["kind"] != "snack" and (self.anim // 12) % 3 == 0:
                surf.fill((255, 255, 255), (x + 4, y - 7, 1, 1))
        # vision cones on the floor
        cones = pygame.Surface((W, H), pygame.SRCALPHA)
        for g in self.guards:
            if g.alive and view.collidepoint(g.x, g.y):
                col = (255, 40, 30, 96) if g.state in ("alert",) else \
                    (255, 190, 30, 96) if g.state in ("suspicious", "search") else (40, 120, 255, 84)
                reach = g.range * (CAUTION_K if self.phase == "caution" else 1)
                pygame.draw.polygon(cones, col, self._cone(g.x, g.y - 4, g.angle, g.half, reach, cx, cy))
        if self.power:
            for c in self.cameras:
                if view.collidepoint(c["x"], c["y"]):
                    col = (255, 40, 30, 100) if c["flash"] else (255, 200, 40, 80)
                    pygame.draw.polygon(cones, col, self._cone(c["x"], c["y"], c["angle"], CAM_HALF, CAM_RANGE,
                                                               cx, cy))
        surf.blit(cones, (0, 0))
        # lasers
        for lz in self.lasers:
            if self.power and lz["t"] < lz["on"]:
                x = round(lz["x"]) - cx
                col = (255, 40, 40) if (self.anim // 2) % 3 else (255, 160, 160)
                pygame.draw.line(surf, col, (x, lz["y0"] - cy), (x, lz["y1"] - cy))
            for yy in (lz["y0"] - 3, lz["y1"]):
                surf.fill((60, 60, 70), (round(lz["x"]) - 2 - cx, yy - cy, 4, 3))
        # the box waiting in storage
        if self.box_pickup:
            bx, by = self.box_pickup
            img = self.box_img[3]
            surf.blit(img, (round(bx) - 8 - cx, round(by) - 6 - cy))
            if (self.anim // 12) % 3 == 0:
                surf.fill((255, 255, 255), (round(bx) + 5 - cx, round(by) - 7 - cy, 1, 1))
        # y-sorted actors
        actors = [(self.py, "akuma")] + [(g.y, g) for g in self.guards if g.alive and view.collidepoint(g.x, g.y)]
        if not self.prisoner.free:
            actors.append((self.prisoner.y, "prisoner"))
        if self.boss_g is not None and self.boss_g.alive:
            actors.append((self.boss_g.y, self.boss_g))
        actors.sort(key=lambda a: a[0])
        for _, g in actors:
            if g == "akuma":
                self._draw_akuma(surf, cx, cy)
            elif g == "prisoner":
                p = self.prisoner
                img, (ax, ay) = p.art.frame(p.face, False, 0, self.anim)
                surf.blit(img, (round(p.x) - ax - cx, round(p.y) - ay + 2 - cy))
            else:
                self._draw_guard(surf, g, cx, cy)
        # bushes cover whoever is in them
        for bx, by in self.bushes:
            if -24 < bx - cx < W + 4 and -24 < by - cy < H + 4:
                surf.blit(self.tiles["bush"], (bx - cx, by - cy))
        if self.in_bush() and not self.box_on:     # a pair of eyes in the leaves
            x, y = round(self.px) - cx, round(self.py) - cy - 9
            if (self.anim // 50) % 4:
                surf.fill((255, 240, 200), (x - 3 + self.pface, y, 2, 1))
                surf.fill((255, 240, 200), (x + 1 + self.pface, y, 2, 1))
        for p in self.leaves:
            surf.fill((70, 136, 84), (round(p[0]) - cx, round(p[1]) - cy, 2, 1))
        # shadows darken whoever stands in them
        surf.blit(self.dark, (0, 0), (cx, cy, W, H))
        if not self.power:
            surf.blit(self.night, (0, 0), (cx, cy, W, H))
        for c in self.cameras:
            x, y = round(c["x"]) - cx, round(c["y"]) - cy
            if -10 < x < W + 10 and -10 < y < H + 10:
                pygame.draw.rect(surf, (40, 40, 48), (x - 4, y - 4, 8, 6))
                pygame.draw.line(surf, (80, 80, 92), (x, y), (x + round(math.cos(c["angle"]) * 6),
                                                              y + round(math.sin(c["angle"]) * 6)), 3)
                on = self.power and (c["flash"] or (self.anim // 20) % 2)
                surf.fill((255, 40, 40) if on else (60, 20, 20), (x - 1, y - 3, 2, 2))
        # smoke, then marks and speech over heads (drawn above the shadow so they always read)
        for g in self.guards:
            for px, py, a in g.puffs:
                r = 2 + a // 20
                c = max(110, 200 - a)
                pygame.draw.circle(surf, (c, c, c + 8), (round(px) - cx, round(py) - cy), r)
        for g in self.guards:
            if not g.alive:
                continue
            x, y = round(g.x) - cx, round(g.y) - 36 - cy
            mark = True
            if g.exclaim:
                k = 3 if g.exclaim > 50 else 2
                draw_text(surf, "!", x, y - 6 * (k - 2), (255, 50, 30), scale=k, shadow=(255, 255, 255), align="center")
            elif g.huh:
                draw_text(surf, "?", x, y, (255, 230, 70), scale=2, align="center")
            elif g.state == "suspicious" and g.sub == "search" and (self.anim // 20) % 2:
                draw_text(surf, "...", x, y + 6, (230, 230, 240), align="center")
            else:
                mark = False
            if g.say and -60 < x < W + 60 and -20 < y < H + 60:
                self._bubble(surf, x, y - (10 if mark else -2), g.say[0])
        tgt = self.snap_target() if self.stage == "play" and not self.ignore_player else None
        if tgt is not None and (self.anim // 8) % 3:
            draw_text(surf, "J: SNAP", round(tgt.x) - cx, round(tgt.y) - 46 - cy, (255, 255, 255),
                      shadow=(160, 20, 20), align="center")
        for who in (self.prisoner, self.boss_g):
            if who is not None and getattr(who, "say", None) and not getattr(who, "free", False):
                self._bubble(surf, round(who.x) - cx, round(who.y) - 34 - cy, who.say[0])
        for x, y, t in self.ripples:
            pygame.draw.circle(surf, (230, 240, 255), (round(x) - cx, round(y) - cy), 6 + t * 2, 1)
        for x, y, text, life in self.pops:
            draw_text(surf, text, round(x) - cx, round(y) - cy, (140, 255, 160), align="center")
        # snow over the yard
        for fx, fy, sp in self.flakes:
            if (fy + cy) // T >= 13:
                surf.fill((240, 246, 255), (round(fx), round(fy), 1 if sp < 0.4 else 2, 1))
        self._hud(surf)
        if self.freeze:
            self._freeze_fx(surf)
        if self.stage == "card":
            self._card(surf)
        if self.menu.open:
            self.menu.draw(surf)
        if self.encounter:
            self._encounter_fx(surf)

    def _draw_guard(self, surf, g, cx, cy):
        snapping = self.snap and self.snap["g"] is g
        img, (ax, ay) = g.map_art.frame(g.face, g.moving, g.walked, g.anim if not snapping else 0)
        jx = 0
        if snapping:
            jx = (self.snap["t"] // 2) % 3 - 1 if self.snap["t"] < SNAP_KILL else 0
            if self.snap["t"] >= SNAP_KILL:     # going limp
                img = pygame.transform.rotate(img, -g.face * min(60, (self.snap["t"] - SNAP_KILL) * 5))
        x, y = round(g.x) - cx + jx, round(g.y) - cy
        pygame.draw.ellipse(surf, (40, 46, 70), (x - 7, y - 1, 14, 4))
        top = y - ay + 2
        surf.blit(img, (x - ax, top))
        if g.kind == "elite":                     # the red beret
            hx = x + g.face * 1
            pygame.draw.ellipse(surf, (200, 30, 40), (hx - 5, top - 1, 10, 4))
            surf.fill((140, 10, 20), (hx - 5, top + 2, 10, 1))
            surf.fill((255, 220, 60), (hx + g.face * 2, top, 1, 1))
        if g.kind == "smoker" and g.state == "patrol" and not snapping:
            mx, my = x + g.face * 4, top + 11
            surf.fill((40, 30, 30), (min(mx, mx + g.face * 4) - 1, my - 1, 6, 3))
            surf.fill((250, 250, 250), (min(mx, mx + g.face * 3), my, 4, 1))
            surf.fill((255, 120, 40) if (g.anim // 6) % 3 else (255, 230, 120), (mx + g.face * 4, my, 1, 1))
        if g.kind == "boss":                      # a cowboy hat, and a revolver spun round a finger
            hx = x + g.face
            surf.fill((120, 76, 36), (hx - 8, top + 2, 16, 2))
            surf.fill((150, 98, 48), (hx - 4, top - 2, 8, 4))
            surf.fill((60, 36, 20), (hx - 4, top + 1, 8, 1))
            a = self.anim / 4
            rx, ry = x + g.face * 6, top + 14
            pygame.draw.line(surf, (60, 60, 70), (rx, ry), (rx + round(math.cos(a) * 5), ry + round(math.sin(a) * 3)), 2)
        else:
            # gun barrel pointing where he looks
            hx, hy = x, y - 12
            pygame.draw.line(surf, (30, 30, 34), (hx, hy), (hx + round(math.cos(g.angle) * 8),
                                                           hy + round(math.sin(g.angle) * 8)), 2)

    def _bubble(self, surf, x, y, text):
        """A comic speech bubble whose tail points down at (x, y)."""
        lines = wrap(text, 22)
        w = max(len(s) for s in lines) * 6 + 5
        h = len(lines) * 9 + 3
        bx = max(2, min(W - w - 2, x - w // 2))
        by = max(2, y - h - 3)
        # keep clear of the radar (top right) and the life bar / objective (top left)
        for cand in (bx, HUD_RADAR.left - w - 2, HUD_LIFE.right + 2):
            r = pygame.Rect(cand, by, w, h + 4)
            if cand >= 2 and cand + w <= W - 2 and not r.collidelist([HUD_RADAR, HUD_LIFE]) + 1:
                bx = cand
                break
        else:                                        # nowhere beside them: hang it under his feet
            by = max(y + 50, HUD_RADAR.bottom + 4)
            tx = max(bx + 4, min(bx + w - 5, x))
            pygame.draw.rect(surf, (248, 248, 240), (bx, by, w, h))
            pygame.draw.polygon(surf, (248, 248, 240), [(tx - 3, by), (tx + 2, by), (tx, by - 4)])
            pygame.draw.rect(surf, (30, 30, 46), (bx, by, w, h), 1)
            pygame.draw.line(surf, (30, 30, 46), (tx - 3, by - 1), (tx, by - 4))
            pygame.draw.line(surf, (30, 30, 46), (tx + 2, by - 1), (tx, by - 4))
            for i, s in enumerate(lines):
                draw_text(surf, s, bx + 3, by + 2 + i * 9, (30, 30, 46), shadow=None)
            return
        tx = max(bx + 4, min(bx + w - 5, x))
        pygame.draw.rect(surf, (248, 248, 240), (bx, by, w, h))
        pygame.draw.polygon(surf, (248, 248, 240), [(tx - 3, by + h - 1), (tx + 2, by + h - 1), (tx, by + h + 3)])
        pygame.draw.rect(surf, (30, 30, 46), (bx, by, w, h), 1)
        pygame.draw.line(surf, (30, 30, 46), (tx - 3, by + h), (tx, by + h + 3))
        pygame.draw.line(surf, (30, 30, 46), (tx + 2, by + h), (tx, by + h + 3))
        for i, s in enumerate(lines):
            draw_text(surf, s, bx + 3, by + 2 + i * 9, (30, 30, 46), shadow=None)

    def _draw_akuma(self, surf, cx, cy):
        if self.invuln and (self.invuln // 4) % 2:
            return
        x, y = round(self.px) - cx, round(self.py) - cy
        if self.box_on:
            k = 0 if not self.moving else 1 + int(self.walked / 4) % 2
            img = self.box_img[k]
            pygame.draw.ellipse(surf, (40, 46, 70), (x - 9, y - 1, 18, 5))
            surf.blit(img, (x - 10, y - 15))
            return
        img, (ax, ay) = self.art.frame(self.pface, self.moving, self.walked, self.anim)
        pygame.draw.ellipse(surf, (40, 46, 70), (x - 7, y - 1, 14, 4))
        surf.blit(img, (x - ax, y - ay + 2))

    def _freeze_fx(self, surf):
        t = FREEZE - self.freeze
        if t < 3:
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            s.fill((255, 255, 255, 120))
            surf.blit(s, (0, 0))
        for k in range(10):
            a = k * math.tau / 10 + t * 0.02
            r0, r1 = 150 - t * 2, 190
            pygame.draw.line(surf, (255, 80, 60), (W // 2 + math.cos(a) * r0, H // 2 + math.sin(a) * r0),
                             (W // 2 + math.cos(a) * r1, H // 2 + math.sin(a) * r1), 2)

    def _hud(self, surf):
        # LIFE
        mx = self.game.akuma_max
        draw_text(surf, "LIFE", 6, 4, (200, 230, 255))
        pygame.draw.rect(surf, (10, 14, 24), (5, 12, 84, 7))
        pygame.draw.rect(surf, (40, 50, 60), (6, 13, 82, 5))
        frac = max(0, min(1, self.hp / mx))
        col = (100, 220, 140) if frac > 0.3 else (255, 90, 60)
        pygame.draw.rect(surf, col, (6, 13, int(82 * frac), 5))
        pygame.draw.rect(surf, (230, 255, 230), (6, 13, int(82 * frac), 1))
        # the objective
        if self.stage == "play":
            draw_text(surf, self.objective, 6, 22, (255, 220, 120))
            if self.detonate:
                draw_text(surf, "DETONATION %d" % (self.detonate // 30 + 1), 6, 31, (255, 90, 60))
            elif self.in_bush() and not self.ignore_player:
                draw_text(surf, "IN A BUSH", 6, 31, (120, 220, 140))
            elif self.sneaking:
                draw_text(surf, "SNEAKING", 6, 31, (160, 190, 230))
        self._radar(surf)
        # item box
        bx, by = W - 38, H - 30
        pygame.draw.rect(surf, (10, 14, 24), (bx, by, 34, 26))
        pygame.draw.rect(surf, (120, 140, 170), (bx, by, 34, 26), 1)
        if self.has_box:
            surf.blit(self.box_img[3], (bx + 9, by + 3))
            col = (255, 230, 120) if self.box_on and (self.anim // 20) % 2 else (200, 210, 230)
            draw_text(surf, "BOX", bx + 17, by + 17, col, align="center")
        else:
            draw_text(surf, "NO", bx + 17, by + 6, (90, 100, 120), align="center")
            draw_text(surf, "ITEM", bx + 17, by + 15, (90, 100, 120), align="center")
        # keycard and C4 beside it
        x = bx - 4
        if self.c4:
            x -= 24
            surf.blit(self.icons["c4"], (x, by + 4))
            draw_text(surf, "x%d" % self.c4, x + 12, by + 16, (230, 230, 210), align="center")
        if self.keycard:
            x -= 15
            surf.blit(self.icons["keycard"], (x, by + 5))
        if self.messages:
            draw_text(surf, self.messages[0][0], W // 2, H - 12, (255, 240, 200), align="center")

    def _targets(self):
        """Where the radar points for the current objective."""
        if self.mission == 0:
            return [(it["x"], it["y"]) for it in self.items if it["kind"] == "keycard"]
        if self.mission == 1:
            return [((tx + 0.5) * T, (ty + 0.5) * T) for (tx, ty), d in self.gens.items() if not d]
        if self.mission == 2:
            return [(self.prisoner.x, self.prisoner.y)]
        if self.boss_g is not None:
            return [(self.boss_g.x, self.boss_g.y)]
        return []

    def _radar(self, surf):
        rw, rh = 64, 44
        ox, oy = W - rw - 4, 4
        pygame.draw.rect(surf, (6, 10, 8), (ox - 1, oy - 1, rw + 2, rh + 2))
        jammed = self.phase in ("alert", "evasion")
        box = pygame.Rect(ox, oy, rw, rh)
        if jammed:
            surf.fill((10, 30, 16), box)
            for _ in range(140):
                surf.fill(self.rng.choice(((40, 120, 66), (120, 200, 140), (6, 20, 10))),
                          (ox + self.rng.randrange(rw), oy + self.rng.randrange(rh), 2, 1))
            draw_text(surf, "JAMMING", ox + rw // 2, oy + rh // 2 - 3, (180, 255, 190), align="center")
        else:
            sx = round(self.px / 4) - rw // 2
            sy = round(self.py / 4) - rh // 2
            surf.blit(self.radar_map, (ox, oy), (sx, sy, rw, rh))
            clip = surf.get_clip()
            surf.set_clip(box)
            for g in self.guards:
                if not g.alive:
                    continue
                gx, gy = ox + g.x / 4 - sx, oy + g.y / 4 - sy
                r = g.range / 4
                pts = [(gx, gy), (gx + math.cos(g.angle - g.half) * r, gy + math.sin(g.angle - g.half) * r),
                       (gx + math.cos(g.angle + g.half) * r, gy + math.sin(g.angle + g.half) * r)]
                pygame.draw.polygon(surf, (60, 150, 90) if g.state == "patrol" else (170, 160, 60), pts, 1)
                surf.fill((255, 60, 60), (round(gx) - 1, round(gy) - 1, 3, 3))
            if self.power:
                for c in self.cameras:
                    surf.fill((255, 230, 90), (round(ox + c["x"] / 4 - sx) - 1, round(oy + c["y"] / 4 - sy) - 1, 2, 2))
            if (self.anim // 10) % 3:
                surf.fill((255, 255, 255), (ox + rw // 2 - 1, oy + rh // 2 - 1, 3, 3))
            surf.set_clip(clip)
            # objective markers, pinned to the radar's edge when off it
            if (self.anim // 12) % 2:
                for tx, ty in self._targets():
                    mx = max(ox + 1, min(ox + rw - 3, round(ox + tx / 4 - sx) - 1))
                    my = max(oy + 1, min(oy + rh - 3, round(oy + ty / 4 - sy) - 1))
                    surf.fill((255, 220, 60), (mx, my, 3, 3))
        pygame.draw.rect(surf, (120, 200, 140), (ox - 1, oy - 1, rw + 2, rh + 2), 1)
        # phase + countdown under the radar
        if self.phase != "normal":
            col = {"alert": (255, 60, 40), "evasion": (255, 200, 60), "caution": (255, 160, 60)}[self.phase]
            secs = self.timer / 60
            draw_text(surf, self.phase.upper(), ox + rw // 2, oy + rh + 4, col, align="center")
            draw_text(surf, "%05.2f" % min(99.99, secs), ox + rw // 2, oy + rh + 13, col, scale=1, align="center")
            if self.phase == "alert":
                pygame.draw.rect(surf, col, (ox - 1, oy - 1, rw + 2, rh + 2), 1)

    def _card(self, surf):
        s = pygame.Surface((W, 56), pygame.SRCALPHA)
        s.fill((0, 0, 0, 180))
        surf.blit(s, (0, 52))
        draw_text(surf, "LEVEL %d" % self.level, W // 2, 58, (255, 220, 80), scale=2, align="center")
        draw_text(surf, "THE FROZEN COMPOUND", W // 2, 78, (230, 240, 255), align="center")
        draw_text(surf, "COMPLETE THE MISSIONS. DRAW OUT THE COMMANDER.", W // 2, 92, (180, 200, 230),
                  align="center")

    def _portrait(self, who):
        cid = PORTRAITS.get(who, "chunli")
        if cid not in self._portraits:
            self._portraits[cid] = _codec_portrait(cid)
        return self._portraits[cid]

    def _draw_codec(self, surf):
        surf.fill((4, 12, 8))
        for y in range(0, H, 3):
            surf.fill((8, 20, 12), (0, y, W, 1))
        if self.stage == "ring":
            if (self.t // 8) % 2 == 0:
                draw_text(surf, "CALL", W // 2, 60, (150, 255, 170), scale=3, align="center")
            draw_text(surf, "PUSH ANY BUTTON", W // 2, 96, (90, 180, 110), align="center")
            draw_text(surf, FREQ, W // 2, 110, (150, 255, 170), scale=2, align="center")
            return
        lines = self.codec_lines
        who, text = lines[min(self.line, len(lines) - 1)]
        caller = next((w for w, _ in reversed(lines[:self.line + 1]) if w != "AKUMA"),
                      next((w for w, _ in lines if w != "AKUMA"), "CHUN-LI"))
        lx, rx, py = 30, W - 90, 20
        for img, x, talking in ((self._portrait("AKUMA"), lx, who == "AKUMA"),
                                (self._portrait(caller), rx, who != "AKUMA")):
            surf.blit(img, (x, py))
            if not talking:
                dim = pygame.Surface((60, 60), pygame.SRCALPHA)
                dim.fill((0, 0, 0, 110))
                surf.blit(dim, (x, py))
            pygame.draw.rect(surf, (120, 220, 140), (x - 2, py - 2, 64, 64), 1)
        draw_text(surf, "AKUMA", lx + 30, py + 66, (150, 255, 170), align="center")
        draw_text(surf, caller, rx + 30, py + 66, (150, 255, 170), align="center")
        # frequency readout and signal bars
        draw_text(surf, "PTT", W // 2, py + 2, (90, 180, 110), align="center")
        draw_text(surf, FREQ, W // 2, py + 14, (150, 255, 170), scale=2, align="center")
        for k in range(8):
            h = 3 + k * 2
            on = k < 3 + (self.anim // 4 + k) % 6 if who != "AKUMA" else k < 2
            surf.fill((120, 240, 150) if on else (20, 50, 30), (W // 2 - 24 + k * 6, py + 50 - h, 4, h))
        pygame.draw.rect(surf, (60, 140, 80), (8, 112, W - 16, 62), 1)
        shown = text[:self.chars]
        draw_text(surf, who + ":", 14, 117, (255, 255, 255))
        for i, line in enumerate(wrap(shown, 48)):
            draw_text(surf, line, 14, 129 + i * 10, (190, 255, 200))
        if self.chars >= len(text) and (self.anim // 20) % 2:
            draw_text(surf, ">", W - 18, 162, (150, 255, 170))

    def _encounter_fx(self, surf):
        t = self.encounter_t
        if t < 4 and t % 2 == 0:
            surf.fill((255, 255, 255))
            return
        n = 12
        bh = H // n + 1
        prog = max(0, (t - 3) / 10)
        for i in range(n):
            w = int(W * min(1, prog * 1.6 - (i % 3) * 0.15))
            if w > 0:
                pygame.draw.rect(surf, (6, 10, 20), (W - w if i % 2 else 0, i * bh, w, bh))
