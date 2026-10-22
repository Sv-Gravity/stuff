"""Level 9: the skate park, 720 Degrees style. No side-view fights here.

Akuma starts on foot and has to find the skateboard lying in the lot.
Stepping on it: "SKATE OR DIEEEE!" and the one-minute clock starts. On the
board he always rolls forward the way he faces: left / right turn him, up
ollies, kick pushes for speed, down brakes. Kickers launch him into the air.

In the air left / right spin him; landing counts the spin in 180 degree steps
(180, 360, 540, 720...). Special in the air kickflips the board. Every trick
landed clean is worth 25 points (a 360 kickflip is two tricks, 50). Landing
crooked, mid-flip or on top of something is a bail: no points. Reach 100
points to clear the course. When the clock runs out a ghost comes for Akuma,
faster and faster; if it touches him he dies (he can still win by reaching
100 points while it chases him).
"""

import math
import random

import pygame

from . import audio
from . import fight as F
from .akuma_sprites import MapArt, CharArt
from .art import shade, _outlined, OUTLINE
from .config import W, H, FPS
from .font import draw_text
from .pause import PauseMenu

LEVEL_NAME = "SKATE OR DIE"
HUD_H = 20
VH = H - HUD_H                   # view height under the HUD
WW, WH = 720, 460                # the park, px

GOAL = 100
TRICK_PTS = 25
TIME_LIMIT = 60 * FPS
INTRO = 110

WALK = 1.1                       # on foot, px / frame
TURN = 4.5                       # ground turning, degrees / frame
SPIN = 14.0                      # air spinning, degrees / frame
G = 0.17                         # gravity, px / frame^2
OLLIE_VZ = 2.7                   # ollie: ~32 frames of air, about a 360
RAMP_POP = 0.12                  # launch vz per px of kicker height ...
RAMP_SPEED = 0.55                # ... plus per px/frame of speed
CRUISE = 1.3                     # Akuma pushes himself up to this
MAX_SPEED = 2.8
PUSH = 0.55                      # one kick push
PUSH_CD = 16
BRAKE = 0.06
FRICTION = 0.004                 # above cruise speed
BAIL_SPEED = 1.0                 # hitting something faster than this = bail
TOL = 45                         # landing: degrees off a multiple of 180 that still counts
FLIP_FRAMES = 16
BAIL_FRAMES = 70
R = 3                            # skater footprint radius
GHOST_SPEED0, GHOST_ACC, GHOST_MAX = 0.8, 0.005, 3.1
SKY = 40                         # px of night sky the camera may show above the north wall
SK = 0.42                        # Akuma sprite scale

CONTROLS = [
    "FIND THE SKATEBOARD AND STEP ON IT",
    "LEFT / RIGHT: TURN   (IN THE AIR: SPIN)",
    "UP: OLLIE   DOWN: BRAKE   K / X: PUSH",
    "L / SPACE IN THE AIR: KICKFLIP",
    "SPIN 180 360 540 720... AND LAND STRAIGHT",
    "EVERY CLEAN TRICK: +25   KICKERS GO HIGHER",
    "CROOKED OR MID-FLIP LANDING = BAIL",
    "100 POINTS CLEARS THE COURSE",
    "1:00 ON THE CLOCK... THEN THE GHOST COMES",
]

DIRV = {"e": (1, 0), "w": (-1, 0), "s": (0, 1), "n": (0, -1)}

# the park: outer walls, a warehouse block in the middle, a loop of lanes
WALLS = [(0, 0, WW, 24), (0, WH - 16, WW, 16), (0, 0, 16, WH), (WW - 16, 0, 16, WH),
         (150, 130, 420, 200)]
ROUTE = [(83, 77), (637, 77), (637, 387), (83, 387)]   # clockwise lane centres
START = (48, 64)
BOARD = (150, 77)
# kickers: x, y, w, h, launch direction, height
RAMPS = [(250, 62, 40, 30, "e", 10), (400, 60, 46, 34, "e", 16),
         (622, 170, 30, 40, "s", 10),
         (430, 370, 46, 34, "w", 16), (240, 372, 40, 30, "w", 10),
         (68, 270, 30, 40, "n", 10)]
PUDDLES = [(180, 88, 34, 14), (600, 280, 30, 16), (330, 392, 40, 14), (40, 330, 28, 14)]
# obstacles: kind, x, y (footprint top-left)
OBSTACLES = [
    ("cone", 340, 34), ("cone", 352, 116), ("cone", 520, 36), ("bench", 470, 116),
    ("hydrant", 30, 116), ("trash", 680, 34), ("planter", 590, 120), ("cone", 676, 250),
    ("trash", 590, 230), ("hydrant", 684, 400), ("bench", 520, 336), ("cone", 360, 430),
    ("planter", 160, 422), ("bench", 300, 336), ("trash", 26, 420), ("cone", 128, 300),
    ("barrier", 20, 220), ("hydrant", 130, 140), ("cone", 30, 30), ("planter", 680, 140),
    ("post", 18, 172), ("post", 142, 172),
]
SIZES = {   # footprint w, d and height
    "cone": (6, 4, 8), "hydrant": (6, 4, 10), "bench": (26, 6, 7), "trash": (10, 6, 12),
    "planter": (22, 10, 9), "barrier": (24, 5, 9), "post": (6, 6, 30),
}
GATE_Y = 176                      # start / finish line across the left lane


def _wrap(a):
    return (a + 180) % 360 - 180


# --------------------------------------------------------------------------
# sounds (built on first use, into the shared audio table)
# --------------------------------------------------------------------------
def _ensure_sfx():
    if not audio._ok or "sk_ollie" in audio._sfx:
        return
    from .audio import _sound, _tone, _noise, _add, RATE
    S = audio._sfx

    def wave(dur, f, vol, vib=0.0, vib_hz=6, kind="square", noise=0.0, sustain=False, seed=1):
        n = int(RATE * dur)
        rnd = random.Random(seed)
        out, ph = [], 0.0
        for i in range(n):
            t = i / n
            fr = f(t) * (1 + vib * math.sin(i / RATE * vib_hz * math.tau))
            ph += fr / RATE
            p = ph % 1.0
            v = (1.0 if p < 0.5 else -1.0) if kind == "square" else (
                4 * abs(p - 0.5) - 1 if kind == "tri" else math.sin(p * math.tau))
            if noise:
                v = v * (1 - noise) + (rnd.random() * 2 - 1) * noise
            env = min(1, t * 20) * ((1 - t) ** 0.5 if sustain else (1 - t) ** 1.5)
            out.append(v * env * vol * 32767)
        return out

    S["sk_ollie"] = _sound(_add(_noise(0.05, 0.55, 3, 0.8), _tone(240, 110, 0.07, 0.3, "square", 0.2)))
    S["sk_land"] = _sound(_add(_noise(0.1, 0.5, 2.5, 0.35), _tone(130, 60, 0.09, 0.35)))
    S["sk_roll"] = _sound(_noise(0.14, 0.12, 0.6, 0.07))
    S["sk_push"] = _sound(_noise(0.05, 0.18, 3, 0.25))
    S["sk_flip"] = _sound(_add(_noise(0.1, 0.2, 1, 0.2), _tone(900, 1500, 0.1, 0.15, "tri")))
    S["sk_bail"] = _sound(_add(_noise(0.4, 0.7, 1.5, 0.3), _tone(320, 60, 0.35, 0.35, "square", 0.3)))
    S["sk_trick"] = _sound(_tone(660, 660, 0.06, 0.22, "square", 0, 0.25)
                           + _tone(880, 880, 0.06, 0.22, "square", 0, 0.25)
                           + _tone(1320, 1320, 0.14, 0.22, "square", 0, 0.25))
    S["sk_wail"] = _sound(_add(wave(1.0, lambda t: 300 + 260 * math.sin(t * math.pi) - 120 * t, 0.25,
                                    vib=0.06, vib_hz=7, kind="sine", sustain=True),
                               wave(1.0, lambda t: 451 + 300 * math.sin(t * math.pi), 0.1,
                                    vib=0.08, vib_hz=5, kind="tri", sustain=True)))
    # "SKATE OR DIEEEE!": a hiss, three shouted square-wave syllables and a long rising wail
    gap = [0.0] * int(RATE * 0.03)
    s = _noise(0.07, 0.3, 0.8, 0.95)
    kate = _add(_noise(0.02, 0.4, 3, 0.9), wave(0.17, lambda t: 260 - 40 * t, 0.32, noise=0.25, seed=2))
    orr = wave(0.15, lambda t: 200 - 20 * t, 0.3, noise=0.15, seed=3)
    die = _add(wave(0.75, lambda t: 230 + 260 * t, 0.32, vib=0.05, vib_hz=8, noise=0.12, sustain=True, seed=4),
               wave(0.75, lambda t: 345 + 390 * t, 0.12, vib=0.05, vib_hz=8, kind="tri", sustain=True))
    S["sk_sting"] = _sound(s + kate + gap + orr + gap + die)


def _play(name, vol=1.0):
    audio.play(name, vol)


# --------------------------------------------------------------------------
# art
# --------------------------------------------------------------------------
def _board_base(bottom):
    s = pygame.Surface((16, 7), pygame.SRCALPHA)
    wheel = (236, 232, 210)
    for x in (2, 12):
        s.fill(wheel, (x, 0, 2, 1))
        s.fill(wheel, (x, 6, 2, 1))
    if bottom:
        pygame.draw.rect(s, (250, 200, 50), (0, 1, 16, 5), border_radius=2)
        s.fill((220, 40, 40), (4, 2, 8, 3))
        s.fill((40, 40, 50), (3, 3, 1, 1))
        s.fill((40, 40, 50), (12, 3, 1, 1))
    else:
        pygame.draw.rect(s, (200, 40, 36), (0, 1, 16, 5), border_radius=2)
        s.fill((44, 42, 50), (2, 2, 12, 3))
        s.fill((80, 76, 90), (5, 3, 6, 1))
    return s


class BoardArt:
    """The board from above, rotated to 16 headings and squashed through a kickflip."""

    def __init__(self):
        self.top, self.bottom = _board_base(False), _board_base(True)
        self.cache = {}

    def get(self, heading, flip_step=0):
        a = round(heading / 22.5) % 16
        key = (a, flip_step)
        img = self.cache.get(key)
        if img is None:
            c = math.cos(flip_step * math.pi / 4)
            base = self.top if c >= 0 else self.bottom
            hgt = max(1, round(7 * max(0.25, abs(c))))
            b = pygame.transform.scale(base, (16, hgt))
            r = pygame.transform.rotate(b, -a * 22.5)
            r = pygame.transform.scale(r, (r.get_width(), max(1, round(r.get_height() * 0.75))))
            img = self.cache[key] = _outlined(r)
        return img


def _ghost_frames():
    frames = []
    for f in range(4):
        s = pygame.Surface((24, 30), pygame.SRCALPHA)
        body = (232, 232, 255, 215)
        pygame.draw.circle(s, body, (12, 13), 10)
        s.fill(body, (2, 13, 20, 10))
        for x in range(2, 22):
            y = 23 + round(2 * math.sin(x * 0.9 + f * math.pi / 2))
            s.fill(body, (x, 22, 1, max(1, y - 22)))
        s.fill((210, 200, 250, 215), (16, 8, 4, 12))          # shading
        # Hsien-Ko touches: a little Qing hat and a talisman on the forehead
        s.fill((70, 40, 110, 255), (5, 2, 14, 4))
        s.fill((100, 60, 150, 255), (7, 0, 10, 3))
        s.fill((230, 60, 60, 255), (11, 0, 2, 1))
        s.fill((250, 230, 120, 255), (10, 6, 4, 9))
        for y in (7, 9, 11, 13):
            s.fill((210, 40, 40, 255), (11 + (y // 2) % 2, y, 2, 1))
        for ex in (6, 15):                                   # hollow eyes
            s.fill((20, 10, 40, 255), (ex, 10, 3, 4))
            s.fill((140, 220, 255, 255), (ex + 1, 11, 1, 1))
        pygame.draw.ellipse(s, (20, 10, 40, 255), (10, 16, 4, 5))   # wailing mouth
        out = pygame.Surface((26, 32), pygame.SRCALPHA)
        m = pygame.mask.from_surface(s, 60).to_surface(setcolor=(60, 30, 90, 200), unsetcolor=(0, 0, 0, 0))
        for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
            out.blit(m, (dx, dy))
        out.blit(s, (1, 1))
        frames.append(out)
    return frames


def _obstacle_img(kind, rng):
    w, d, h = SIZES[kind]
    s = pygame.Surface((w + 2, d + h + 2), pygame.SRCALPHA)
    if kind == "cone":
        pygame.draw.polygon(s, (245, 110, 30), [(1, h + d), (w + 1, h + d), (w // 2 + 1, 1)])
        s.fill((245, 245, 245), (2, h // 2 + 1, w - 2, 2))
        s.fill((60, 56, 60), (0, h + d - 1, w + 2, 2))
    elif kind == "hydrant":
        s.fill((200, 30, 30), (1, 3, w, h + d - 3))
        s.fill((240, 70, 60), (2, 3, 2, h + d - 4))
        s.fill((170, 20, 26), (0, 6, w + 2, 2))
        pygame.draw.ellipse(s, (230, 60, 50), (1, 0, w, 5))
    elif kind == "bench":
        s.fill((150, 100, 50), (1, 1, w, d))                 # seat
        for y in range(2, d, 2):
            s.fill((180, 128, 70), (1, y, w, 1))
        s.fill((110, 70, 36), (1, d + 1, w, 2))
        for x in (2, w - 3):
            s.fill((70, 70, 80), (x, d + 1, 2, h))
    elif kind == "trash":
        s.fill((50, 120, 70), (1, 1, w, d))
        s.fill((36, 90, 52), (1, d + 1, w, h))
        for x in range(3, w, 3):
            s.fill((28, 70, 40), (x, d + 2, 1, h - 2))
        s.fill((70, 150, 90), (1, 1, w, 2))
    elif kind == "planter":
        s.fill((150, 146, 140), (1, 1 + 4, w, d))
        s.fill((118, 114, 110), (1, d + 5, w, h - 4))
        for _ in range(26):
            x, y = rng.randrange(2, w), rng.randrange(0, d + 2)
            pygame.draw.circle(s, rng.choice(((50, 130, 60), (70, 160, 70), (40, 100, 50))), (x, y), 2)
    elif kind == "barrier":
        s.fill((230, 230, 230), (1, 1, w, d))
        s.fill((210, 210, 210), (1, d + 1, w, h))
        for x in range(-6, w, 6):
            pygame.draw.polygon(s, (220, 40, 40), [(x + 1, d + h), (x + 4, d + h), (x + 8, d + 1), (x + 5, d + 1)])
    elif kind == "post":
        s.fill((60, 60, 70), (1, 1, w, d + h))
        s.fill((230, 230, 230), (2, 1, 2, d + h))
        for y in range(4, d + h, 8):
            s.fill((220, 40, 40), (1, y, w, 3))
    return _outlined(s)


def _flag_img(col):
    s = pygame.Surface((12, 22), pygame.SRCALPHA)
    s.fill((200, 200, 200), (1, 0, 1, 22))
    pygame.draw.polygon(s, col, [(2, 1), (11, 4), (2, 8)])
    return _outlined(s)


def _ramp_draw(surf, rx, ry, rw, rh, d, hgt):
    """A kicker drawn in the 3/4 view: points at height z show at y - z."""
    top_lo, top_hi = (96, 104, 120), (176, 186, 204)
    side = (60, 64, 78)
    if d in ("e", "w"):
        lo_x, hi_x = (rx, rx + rw) if d == "e" else (rx + rw, rx)
        steps = rw
        for i in range(steps):
            k = i / steps
            x = lo_x + (hi_x - lo_x) * k
            z = hgt * k
            col = tuple(round(a + (b - a) * k) for a, b in zip(top_lo, top_hi))
            surf.fill(col, (round(min(x, x + (1 if d == "e" else -1))), round(ry - z), 1, rh))
            surf.fill(side, (round(x), round(ry + rh - z), 1, round(z) + 1))   # side face
        surf.fill((220, 220, 230), (round(hi_x) - (1 if d == "e" else 0), round(ry - hgt), 1, rh))   # coping
    else:
        lo_y, hi_y = (ry, ry + rh) if d == "s" else (ry + rh, ry)
        n = rh
        rows = []
        for i in range(n + 1):
            k = i / n
            y = lo_y + (hi_y - lo_y) * k
            rows.append((y - hgt * k, k))
        rows.sort()
        for yy, k in rows:
            col = tuple(round(a + (b - a) * k) for a, b in zip(top_lo, top_hi))
            surf.fill(col, (rx, round(yy), rw, 2))
        if d == "s":
            surf.fill(side, (rx, ry + rh - hgt, rw, hgt))                     # the drop face
            surf.fill((220, 220, 230), (rx, ry + rh - hgt - 1, rw, 1))
        else:
            surf.fill((220, 220, 230), (rx, ry - hgt, rw, 1))


def _arrow(surf, x, y, ang, col):
    a = math.radians(ang)
    fx, fy = math.cos(a), math.sin(a)
    px, py = -fy, fx
    pts = [(x + fx * 8, y + fy * 8), (x - fx * 2 + px * 7, y - fy * 2 + py * 7),
           (x - fx * 2 + px * 3, y - fy * 2 + py * 3), (x - fx * 8 + px * 3, y - fy * 8 + py * 3),
           (x - fx * 8 - px * 3, y - fy * 8 - py * 3), (x - fx * 2 - px * 3, y - fy * 2 - py * 3),
           (x - fx * 2 - px * 7, y - fy * 2 - py * 7)]
    pygame.draw.polygon(surf, col, [(round(a_), round(b_)) for a_, b_ in pts])


def _sky(rng):
    s = pygame.Surface((W, SKY))
    for y in range(SKY):
        s.fill(tuple(round(a + (b - a) * y / SKY) for a, b in zip((14, 10, 34), (60, 36, 70))), (0, y, W, 1))
    for _ in range(40):
        s.set_at((rng.randrange(W), rng.randrange(SKY - 12)), (230, 230, 255))
    x = 0
    while x < W:                                            # city rooftops behind the wall
        w, h = rng.randrange(18, 44), rng.randrange(8, 24)
        s.fill((26, 22, 40), (x, SKY - h, w, h))
        for wy in range(SKY - h + 3, SKY - 2, 5):
            for wx in range(x + 3, x + w - 3, 6):
                if rng.random() < 0.3:
                    s.fill((250, 210, 110), (wx, wy, 2, 2))
        x += w + rng.randrange(0, 6)
    return s


def _world(rng):
    s = pygame.Surface((WW, WH))
    s.fill((70, 70, 80))
    for _ in range(5200):
        x, y = rng.randrange(WW), rng.randrange(WH)
        s.set_at((x, y), shade((70, 70, 80), rng.choice((0.82, 0.9, 1.1, 1.18))))
    for _ in range(18):                                    # cracks
        x, y = rng.randrange(WW), rng.randrange(WH)
        pts = [(x, y)]
        for _ in range(4):
            x += rng.randint(-6, 6)
            y += rng.randint(-6, 6)
            pts.append((x, y))
        pygame.draw.lines(s, (52, 52, 60), False, pts)
    # painted route: dashed lane line plus arrows
    for i, a in enumerate(ROUTE):
        b = ROUTE[(i + 1) % len(ROUTE)]
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        dist = math.hypot(b[0] - a[0], b[1] - a[1])
        for k in range(30, int(dist) - 20, 70):
            t = k / dist
            _arrow(s, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, ang, (210, 200, 110))
    # puddles
    for x, y, w, h in PUDDLES:
        pygame.draw.ellipse(s, (40, 60, 100), (x, y, w, h))
        pygame.draw.ellipse(s, (70, 100, 150), (x + 2, y + 2, w - 4, h - 4))
        s.fill((150, 180, 230), (x + w // 3, y + 3, w // 4, 1))
    # start / finish line: a checker strip across the left lane
    for x in range(16, 150, 4):
        for r in range(2):
            col = (240, 240, 240) if (x // 4 + r) % 2 else (24, 24, 30)
            s.fill(col, (x, GATE_Y - 2 + r * 2, 4, 2))
    for r in RAMPS:
        _ramp_draw(s, *r)
    # outer walls: brick, the north one shows its face
    brick, mortar = (128, 62, 52), (88, 44, 40)
    for (x, y, w, h) in WALLS[:4]:
        s.fill(mortar, (x, y, w, h))
        for yy in range(y, y + h, 4):
            off = 0 if (yy // 4) % 2 else 4
            for xx in range(x - off, x + w, 8):
                s.fill(brick, (max(x, xx), yy, min(7, x + w - max(x, xx)), 3))
    s.fill((168, 168, 176), (0, 0, WW, 4))
    # the warehouse: roof seen from above, south face below it
    bx, by, bw, bh = WALLS[4]
    face = 26
    s.fill((96, 96, 110), (bx, by, bw, bh - face))
    for x in range(bx, bx + bw, 12):
        s.fill((84, 84, 98), (x, by, 1, bh - face))
    s.fill((130, 130, 146), (bx, by, bw, 3))
    for (vx, vy) in ((bx + 60, by + 40), (bx + 210, by + 90), (bx + 330, by + 50)):   # roof vents
        s.fill((150, 150, 160), (vx, vy, 18, 12))
        s.fill((60, 60, 70), (vx + 2, vy + 3, 14, 6))
    fy = by + bh - face
    s.fill((150, 90, 70), (bx, fy, bw, face))
    for yy in range(fy, fy + face, 4):
        off = 0 if (yy // 4) % 2 else 4
        for xx in range(bx - off, bx + bw, 8):
            s.fill((170, 104, 80), (max(bx, xx), yy, min(7, bx + bw - max(bx, xx)), 3))
    for wx in range(bx + 20, bx + bw - 20, 60):
        s.fill((30, 30, 44), (wx, fy + 6, 18, 10))
        s.fill((90, 120, 170), (wx + 1, fy + 7, 7, 4))
    pygame.draw.rect(s, OUTLINE, (bx, by, bw, bh), 1)
    # SKATE OR DIE graffiti on the roof edge, AKUMA SK8 sign
    draw_text(s, "SKATE OR DIE", bx + bw // 2, by + bh - face - 34, (255, 80, 200), scale=3, align="center")
    draw_text(s, "AKUMA SK8 PARK", bx + bw // 2, by + 18, (255, 220, 120), scale=2, align="center")
    return s


# --------------------------------------------------------------------------
# the level
# --------------------------------------------------------------------------
class SkateScene:
    def __init__(self, game, seed=None, level=9, hp=None):
        F.init_shared()
        _ensure_sfx()
        self.game = game
        self.level = level
        self.rng = random.Random(seed)
        self.max_hp = game.akuma_max
        self.hp = self.max_hp if hp is None else hp
        self.menu = PauseMenu(game, CONTROLS)
        self.world = _world(random.Random(7))
        self.sky = _sky(random.Random(8))
        self.board_art = BoardArt()
        self.ghost_img = _ghost_frames()
        self.flags = [_flag_img(c) for c in ((255, 60, 40), (60, 200, 255), (255, 220, 60))]
        orng = random.Random(3)
        self.obstacles = []
        for kind, x, y in OBSTACLES:
            w, d, h = SIZES[kind]
            self.obstacles.append(dict(kind=kind, rect=pygame.Rect(x, y, w, d), h=h,
                                       img=_obstacle_img(kind, orng)))
        for r in WALLS:
            self.obstacles.append(dict(kind="wall", rect=pygame.Rect(r), h=999, img=None))
        self.ramps = [dict(rect=pygame.Rect(x, y, w, h), dir=d, h=hh) for x, y, w, h, d, hh in RAMPS]
        self.puddles = [pygame.Rect(p) for p in PUDDLES]
        self.foot = MapArt("akuma", SK)
        art = CharArt("akuma")
        both = MapArt._both
        self.poses = {
            "stand": [both(art, n, SK) for n in art._anim("idle")[0]],
            "crouch": both(art, "f9_1", SK),
            "air": both(art, "f6_4", SK),
            "air_up": both(art, "f6_3", SK),
            "fall": both(art, "f83_6", SK),
            "down": both(art, "f84_2", SK),
        }
        # Akuma
        self.mode = "foot"
        self.px, self.py = float(START[0]), float(START[1])
        self.z, self.vz = 0.0, 0.0
        self.heading = 0.0
        self.speed = 0.0
        self.air = False
        self.vx = self.vy = 0.0
        self.spin = 0.0
        self.flip_t = 0
        self.flips = 0
        self.air_t = 0
        self.bail_t = 0
        self.bail_why = ""
        self.bails = 0
        self.push_cd = 0
        self.push_t = 0
        self.side = 1
        self.walked = 0.0
        self.moving = False
        self.board = list(BOARD)           # where the board lies before pickup
        self.board_fly = None              # [x, y, z, vx, vy, vz, rot] while bailing
        self.score = 0
        self.tricks = []                   # every landed trick: dict(spin, flips, pts, name)
        self.last_trick = None
        self.timer = TIME_LIMIT
        self.timer_on = False
        self.ghost = None                  # [x, y, speed, t]
        self.popups = []                   # [text, x, y, frames, color]
        self.parts = []                    # [x, y, vx, vy, life, color]
        self.banner = None                 # [text, frames, color]
        self.phase = "intro"
        self.t = 0
        self.end_t = 0
        self.shake = 0
        self.result = None
        self.laps = 0

    @property
    def paused(self):
        return self.menu.open

    # ---- world queries -----------------------------------------------------
    def ramp_at(self, x, y):
        for r in self.ramps:
            if r["rect"].collidepoint(x, y):
                return r
        return None

    def ground_at(self, x, y):
        g = 0.0
        for r in self.ramps:
            rc = r["rect"]
            if not rc.collidepoint(x, y):
                continue
            d = r["dir"]
            if d == "e":
                p = (x - rc.x) / rc.w
            elif d == "w":
                p = (rc.right - x) / rc.w
            elif d == "s":
                p = (y - rc.y) / rc.h
            else:
                p = (rc.bottom - y) / rc.h
            g = max(g, r["h"] * max(0.0, min(1.0, p)))
        return g

    def hits(self, x, y, z):
        """The obstacle (or wall) a skater at x, y, height z would run into."""
        for o in self.obstacles:
            if o["h"] > z + 0.5 and o["rect"].inflate(2 * R, 2 * R).collidepoint(x, y):
                return o
        return None

    def _blocked_ground(self, x, y, z):
        return self.hits(x, y, z) is not None or self.ground_at(x, y) - z > 3

    def in_puddle(self, x, y):
        for p in self.puddles:
            if p.collidepoint(x, y):
                # an ellipse, not its box
                nx = (x - p.centerx) / (p.w / 2)
                ny = (y - p.centery) / (p.h / 2)
                if nx * nx + ny * ny <= 1:
                    return True
        return False

    # ---- update ------------------------------------------------------------
    def update(self, inp):
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.phase == "play" and self.menu.toggle(inp):
            return
        self.t += 1
        if self.shake:
            self.shake -= 1
        if self.banner:
            self.banner[1] -= 1
            if self.banner[1] <= 0:
                self.banner = None
        self._fx()
        if self.phase == "intro":
            if self.t == INTRO - 25:
                _play("fight")
            if self.t >= INTRO:
                self.phase = "play"
            return
        if self.phase in ("won", "lost"):
            self.end_t += 1
            if self.phase == "lost" and self.ghost:
                self.ghost[3] += 1
            if self.board_fly:
                self._board_fly()
            skip = self.end_t > 40 and inp.any_pressed("punch", "kick", "special", "start")
            if self.end_t >= 150 or skip:
                if self.phase == "won":
                    self.result = "win"
                    self.game.level_done(self, max(1, self.hp))
                else:
                    self.result = "lose"
                    self.game.level_failed(self)
            return
        if self.mode == "foot":
            self._walk(inp)
        else:
            self._skate(inp)
            self._clock()
            self._ghost()

    def _fx(self):
        for p in self.parts:
            p[0] += p[2]
            p[1] += p[3]
            p[4] -= 1
        self.parts = [p for p in self.parts if p[4] > 0]
        for p in self.popups:
            p[3] -= 1
        self.popups = [p for p in self.popups if p[3] > 0]

    def _popup(self, text, color=(255, 240, 120), frames=70):
        self.popups.append([text, self.px, self.py - self.z - 34, frames, color])

    # ---- on foot -----------------------------------------------------------
    def _walk(self, inp):
        dx = (1 if inp.held("right") else 0) - (1 if inp.held("left") else 0)
        dy = (1 if inp.held("down") else 0) - (1 if inp.held("up") else 0)
        k = WALK * (0.7071 if dx and dy else 1)
        ox, oy = self.px, self.py
        if dx and not self.hits(self.px + dx * k, self.py, 0):
            self.px += dx * k
        if dy and not self.hits(self.px, self.py + dy * k, 0):
            self.py += dy * k
        if dx:
            self.side = dx
        self.z = self.ground_at(self.px, self.py)
        moved = math.hypot(self.px - ox, self.py - oy)
        self.walked += moved
        self.moving = moved > 0.2
        if self.moving and int(self.walked / 12) != int((self.walked - moved) / 12):
            _play("step", 0.5)
        if math.hypot(self.px - self.board[0], self.py - self.board[1]) < 9:
            self._pickup()

    def _pickup(self):
        self.mode = "skate"
        self.px, self.py = float(self.board[0]), float(self.board[1])
        self.heading = 0.0 if self.side > 0 else 180.0
        self.speed = 0.6
        self.timer = TIME_LIMIT
        self.timer_on = True
        self.banner = ["SKATE OR DIEEEE!", 130, (255, 80, 60)]
        self.shake = 10
        _play("sk_sting")
        for _ in range(16):
            a = self.rng.uniform(0, math.tau)
            self.parts.append([self.px, self.py - 8, math.cos(a) * 1.5, math.sin(a) * 1.5 - 0.5, 30,
                               self.rng.choice(((255, 230, 90), (255, 120, 60), (255, 255, 255)))])

    # ---- on the board --------------------------------------------------------
    def _skate(self, inp):
        if self.push_t:
            self.push_t -= 1
        if self.push_cd:
            self.push_cd -= 1
        if self.bail_t:
            self.bail_t -= 1
            if self.board_fly:
                self._board_fly()
            if not self.bail_t:
                self.board_fly = None
                self.speed = 0.0
            return
        turn = (1 if inp.held("right") else 0) - (1 if inp.held("left") else 0)
        if not self.air:
            self.heading = (self.heading + turn * TURN) % 360
            if turn:
                self.side = self._side_for(self.heading)
            if inp.pressed("kick") or (inp.held("kick") and not self.push_cd):
                if not self.push_cd:
                    self.speed = min(MAX_SPEED, self.speed + PUSH)
                    self.push_cd, self.push_t = PUSH_CD, 12
                    _play("sk_push", 0.6)
            if inp.held("down"):
                self.speed = max(0.0, self.speed - BRAKE)
            elif self.speed < CRUISE:
                self.speed = min(CRUISE, self.speed + 0.03)
            elif self.speed > CRUISE:
                self.speed = max(CRUISE, self.speed - FRICTION)
            if self.in_puddle(self.px, self.py):
                self.speed *= 0.985
                if self.speed > 0.6 and self.t % 4 == 0:
                    self.parts.append([self.px, self.py, self.rng.uniform(-0.8, 0.8), -1.0, 14,
                                       (150, 190, 240)])
            if self.speed > 0.4 and self.t % 9 == 0:
                _play("sk_roll", min(1.0, 0.25 + self.speed * 0.2))
            if inp.pressed("up"):
                self.ollie()
            else:
                self._roll()
        else:
            if turn:
                self.heading = (self.heading + turn * SPIN) % 360
                self.spin += turn * SPIN
            if inp.pressed("special") and not self.flip_t:
                self.flip_t = FLIP_FRAMES
                self.flips += 1
                _play("sk_flip")
            elif self.flip_t:
                self.flip_t -= 1
            self._fly()

    @staticmethod
    def _side_for(heading, keep=1):
        c = math.cos(math.radians(heading))
        if c > 0.2:
            return 1
        if c < -0.2:
            return -1
        return keep

    def _roll(self):
        a = math.radians(self.heading)
        dx, dy = math.cos(a) * self.speed, math.sin(a) * self.speed
        nx, ny = self.px + dx, self.py + dy
        if self._blocked_ground(nx, ny, self.z):
            self._bump(dx, dy)
            return
        g = self.ground_at(nx, ny)
        if g < self.z - 1.5:
            # rolled off the top of a kicker: launch
            r = self.ramp_at(self.px, self.py)
            vz = 0.0
            if r:
                vx, vy = DIRV[r["dir"]]
                along = (vx * dx + vy * dy) / max(0.01, self.speed)
                vz = max(0.0, along) * (r["h"] * RAMP_POP + self.speed * RAMP_SPEED)
            self.px, self.py = nx, ny
            self._take_off(vz)
            return
        self.px, self.py, self.z = nx, ny, g

    def _bump(self, dx, dy):
        if self.speed > BAIL_SPEED:
            self.bail("WIPEOUT!")
            return
        bx = self._blocked_ground(self.px + dx, self.py, self.z)
        by = self._blocked_ground(self.px, self.py + dy, self.z)
        if bx:
            dx = -dx
        if by:
            dy = -dy
        if not bx and not by:
            dx, dy = -dx, -dy
        self.heading = math.degrees(math.atan2(dy, dx)) % 360
        self.side = self._side_for(self.heading, self.side)
        self.speed *= 0.5
        _play("land", 0.6)

    def ollie(self):
        """Up on the ground: pop into the air (a kicker under the wheels adds to it)."""
        if self.air or self.bail_t or self.mode != "skate":
            return
        vz = OLLIE_VZ
        r = self.ramp_at(self.px, self.py)
        if r and self.z > 0:
            vx, vy = DIRV[r["dir"]]
            a = math.radians(self.heading)
            along = vx * math.cos(a) + vy * math.sin(a)
            vz += max(0.0, along) * self.speed * 0.7 * (self.z / r["h"])
        _play("sk_ollie")
        self._take_off(vz)

    def _take_off(self, vz):
        a = math.radians(self.heading)
        self.air = True
        self.vz = vz
        self.vx, self.vy = math.cos(a) * self.speed, math.sin(a) * self.speed
        self.spin = 0.0
        self.flips = 0
        self.flip_t = 0
        self.air_t = 0
        self.travel = self.heading

    def air_frames_left(self):
        """Frames until touchdown on flat ground if nothing changes (bots use this)."""
        z, vz, n = self.z, self.vz, 0
        while n < 400:
            vz -= G
            z += vz
            n += 1
            if z <= self.ground_at(self.px + self.vx * n, self.py + self.vy * n):
                return n
        return n

    def _fly(self):
        self.air_t += 1
        nx, ny = self.px + self.vx, self.py + self.vy
        self.vz -= G
        nz = self.z + self.vz
        hit = self.hits(nx, ny, nz)
        if hit:
            self.bail("LANDED ON A %s!" % hit["kind"].upper() if hit["kind"] != "wall" and nz > 0
                      else "SLAMMED THE WALL!")
            return
        self.px, self.py, self.z = nx, ny, nz
        g = self.ground_at(nx, ny)
        if self.z <= g:
            self.z = g
            self.land()

    def land(self):
        self.air = False
        self.vz = 0.0
        net = self.spin
        n = int(round(abs(net) / 180))
        off = abs(abs(net) - n * 180)
        if self.flip_t:
            self.bail("MID-FLIP!")
            return
        if off > TOL:
            self.bail("CROOKED LANDING!")
            return
        # clean: Akuma straightens out and rides on the way he was flying
        self.heading = math.degrees(math.atan2(self.vy, self.vx)) % 360 if (self.vx or self.vy) else \
            round(self.heading / 180) * 180 % 360
        self.side = self._side_for(self.heading, self.side)
        self.speed = min(MAX_SPEED, math.hypot(self.vx, self.vy) * 0.95)
        names, pts = [], 0
        if n >= 1:
            deg = n * 180
            names.append("%d%s" % (deg, "!!" if deg == 720 else "!!!" if deg > 720 else ""))
            pts += TRICK_PTS
        if self.flips:
            names.append(("DOUBLE " if self.flips == 2 else "TRIPLE " if self.flips >= 3 else "") + "KICKFLIP")
            pts += TRICK_PTS * self.flips
        for _ in range(6):
            self.parts.append([self.px, self.py, self.rng.uniform(-1, 1), self.rng.uniform(-0.6, 0), 12,
                               (160, 150, 140)])
        if not pts:
            _play("sk_land", 0.8)
            return
        name = " ".join(names)
        if not name.endswith("!"):
            name += "!"
        self.score += pts
        self.last_trick = dict(spin=n * 180, flips=self.flips, pts=pts, name=name)
        self.tricks.append(self.last_trick)
        _play("sk_land", 0.6)
        _play("sk_trick")
        self._popup("%s +%d" % (name, pts), (120, 255, 140) if n < 4 else (255, 120, 255))
        if self.score >= GOAL:
            self.phase, self.end_t = "won", 0
            self.banner = None
            _play("encounter")

    def bail(self, why="BAIL!"):
        self.bails += 1
        self.bail_why = why
        self.bail_t = BAIL_FRAMES
        a = math.radians(self.heading)
        sp = max(self.speed, math.hypot(self.vx, self.vy) if self.air else 0)
        self.board_fly = [self.px, self.py, max(self.z, 2.0), math.cos(a) * sp * 0.8,
                          math.sin(a) * sp * 0.8, 2.4, 0.0]
        self.air = False
        self.vz = 0.0
        self.z = self.ground_at(self.px, self.py)
        self.speed = 0.0
        self.spin = 0.0
        self.flips = 0
        self.flip_t = 0
        self.vx = self.vy = 0.0
        self.shake = 8
        _play("sk_bail")
        self._popup("BAIL! " + why if why != "BAIL!" else "BAIL!", (255, 90, 70), 80)
        for _ in range(10):
            self.parts.append([self.px, self.py - 6, self.rng.uniform(-1.5, 1.5), self.rng.uniform(-2, 0), 20,
                               self.rng.choice(((255, 230, 120), (255, 255, 255), (160, 150, 140)))])

    def _board_fly(self):
        b = self.board_fly
        nx, ny = b[0] + b[3], b[1] + b[4]
        if not self.hits(nx, ny, b[2]):
            b[0], b[1] = nx, ny
        else:
            b[3], b[4] = -b[3] * 0.4, -b[4] * 0.4
        b[5] -= G
        b[2] += b[5]
        if b[2] <= 0:
            b[2] = 0
            b[5] = -b[5] * 0.4 if abs(b[5]) > 0.6 else 0
            b[3] *= 0.85
            b[4] *= 0.85
        b[6] += 25 * math.hypot(b[3], b[4])

    # ---- the clock and the ghost --------------------------------------------
    def _clock(self):
        if not self.timer_on or self.timer <= 0:
            return
        self.timer -= 1
        if self.timer in (10 * FPS, 5 * FPS, 4 * FPS, 3 * FPS, 2 * FPS, FPS):
            _play("beep")
        if self.timer <= 0:
            self._spawn_ghost()

    def _spawn_ghost(self):
        a = math.radians(self.heading + 180)
        gx = min(WW - 10, max(10, self.px + math.cos(a) * 170))
        gy = min(WH - 10, max(10, self.py + math.sin(a) * 170))
        self.ghost = [gx, gy, GHOST_SPEED0, 0]
        self.banner = ["TIME'S UP! SKATE OR DIE!", 150, (200, 160, 255)]
        self.shake = 12
        _play("sk_wail")

    def _ghost(self):
        g = self.ghost
        if not g:
            return
        g[3] += 1
        g[2] = min(GHOST_MAX, g[2] + GHOST_ACC)
        dx, dy = self.px - g[0], self.py - g[1]
        d = math.hypot(dx, dy)
        if d > 0.01:
            g[0] += dx / d * min(d, g[2])
            g[1] += dy / d * min(d, g[2])
        if g[3] % 150 == 0:
            _play("sk_wail", 0.6)
        if math.hypot(self.px - g[0], self.py - g[1]) < 10:
            self.caught()

    def caught(self):
        self.phase, self.end_t = "lost", 0
        self.air = False
        self.z = self.ground_at(self.px, self.py)
        self.bail_t = 0
        self.shake = 14
        _play("sk_wail")
        _play("ko")

    # ---- drawing -------------------------------------------------------------
    def camera(self):
        cx = min(max(0, self.px - W / 2), WW - W)
        cy = min(max(-SKY, self.py - self.z * 0.6 - VH / 2 - 8), WH - VH)
        return round(cx), round(cy)

    def draw(self, surf):
        sh = (0, 0)
        if self.shake:
            sh = (self.rng.choice((-2, -1, 1, 2)), self.rng.choice((-1, 0, 1)))
        cx, cy = self.camera()
        ox, oy = -cx + sh[0], HUD_H - cy + sh[1]
        surf.fill((16, 14, 22))
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, HUD_H, W, VH))
        if oy > HUD_H:
            surf.blit(self.sky, (0, oy - SKY))
        surf.blit(self.world, (ox, oy))
        # puddle glints
        for p in self.puddles:
            if (self.t // 20 + p.x) % 3 == 0:
                surf.fill((220, 235, 255), (ox + p.x + p.w // 2 + (self.t // 7) % 5, oy + p.y + p.h // 2, 2, 1))
        # course flags at the corners
        for i, (fx, fy) in enumerate(((30, 40), (690, 40), (690, 430), (30, 430))):
            surf.blit(self.flags[i % 3], (ox + fx - 2, oy + fy - 22 + (1 if (self.t // 20 + i) % 2 else 0)))
        # start / finish banner over the gate
        things = []
        for o in self.obstacles:
            if o["img"] is not None:
                things.append((o["rect"].bottom, 0, "ob", o))
        things.append((self.py + 0.5, 1, "akuma", None))
        things.sort(key=lambda t: (t[0], t[1]))
        for _, _, kind, o in things:
            if kind == "ob":
                img = o["img"]
                rc = o["rect"]
                surf.blit(img, (ox + rc.x - 1, oy + rc.bottom - img.get_height() + 1))
            else:
                self._draw_akuma(surf, ox, oy)
        self._draw_gate(surf, ox, oy)
        if self.ghost:
            g = self.ghost
            img = self.ghost_img[(g[3] // 6) % 4]
            bob = round(3 * math.sin(g[3] * 0.1))
            pygame.draw.ellipse(surf, (20, 14, 30), (round(ox + g[0]) - 7, round(oy + g[1]) - 1, 14, 4))
            surf.blit(img, (round(ox + g[0]) - img.get_width() // 2, round(oy + g[1]) - 34 + bob))
        for p in self.parts:
            surf.fill(p[5], (round(ox + p[0]), round(oy + p[1]), 2, 2))
        for text, x, y, f, col in self.popups:
            draw_text(surf, text, round(ox + x), round(oy + y - (80 - f) // 4), col, align="center")
        surf.set_clip(clip)
        self._hud(surf)

    def _draw_gate(self, surf, ox, oy):
        x0, x1 = ox + 21, ox + 145
        y = oy + GATE_Y - 34
        surf.fill((24, 24, 30), (x0, y - 1, x1 - x0, 11))
        surf.fill((220, 40, 40), (x0, y, x1 - x0, 9))
        draw_text(surf, "START / FINISH", (x0 + x1) // 2, y + 1, (255, 255, 255), align="center")

    def _draw_akuma(self, surf, ox, oy):
        x, y = ox + self.px, oy + self.py
        if self.mode == "foot":
            # the board waiting on the ground, with a bouncing marker
            bx, by = ox + self.board[0], oy + self.board[1]
            img = self.board_art.get(0)
            surf.blit(img, (round(bx) - img.get_width() // 2, round(by) - img.get_height() // 2))
            if self.phase == "play" and (self.t // 15) % 2 == 0:
                draw_text(surf, "!", round(bx), round(by) - 18 - (self.t // 8) % 3, (255, 230, 80), align="center")
            fimg, (ax, ay) = self.foot.frame(self.side, self.moving, self.walked, self.t)
            pygame.draw.ellipse(surf, (20, 18, 26), (round(x) - 6, round(y - self.z) - 2, 12, 4))
            surf.blit(fimg, (round(x) - ax, round(y - self.z) - ay + 1))
            return
        g = self.ground_at(self.px, self.py)
        hgt = max(0.0, self.z - g)
        sw = max(6, 12 - int(hgt / 4))
        pygame.draw.ellipse(surf, (20, 18, 26), (round(x) - sw // 2, round(y - g) - 2, sw, 4))
        fy = y - self.z
        side = 0 if self.side > 0 else 1
        if self.air:
            self.side = self._side_for(self.heading, self.side)
            side = 0 if self.side > 0 else 1
        if self.bail_t or self.phase == "lost":
            if self.board_fly:
                b = self.board_fly
                step = int(b[6] / 45) % 8
                img = self.board_art.get(b[6] * 0.3, step)
                pygame.draw.ellipse(surf, (20, 18, 26), (round(ox + b[0]) - 5, round(oy + b[1]) - 2, 10, 4))
                surf.blit(img, (round(ox + b[0]) - img.get_width() // 2,
                                round(oy + b[1] - b[2]) - img.get_height() // 2))
            left = self.bail_t
            pose = "fall" if (BAIL_FRAMES - left) < 12 and self.phase != "lost" else "down"
            img, (ax, ay) = self.poses[pose][side]
            if self.phase == "lost" and (self.end_t // 4) % 2:
                img = pygame.mask.from_surface(img).to_surface(setcolor=(200, 190, 255, 255),
                                                               unsetcolor=(0, 0, 0, 0))
            surf.blit(img, (round(x) - ax, round(fy) - ay + 2))
            return
        step = 0
        if self.flip_t:
            step = int((FLIP_FRAMES - self.flip_t) / FLIP_FRAMES * 8) % 8
        bimg = self.board_art.get(self.heading, step)
        lift = 3 if self.flip_t else 0                         # the board pops up a little while flipping
        surf.blit(bimg, (round(x) - bimg.get_width() // 2, round(fy) - bimg.get_height() // 2 - lift))
        if self.air:
            pose = self.poses["air_up" if self.vz > 0.8 else "air"]
        elif self.push_t:
            pose = self.poses["crouch"]
        else:
            pose = self.poses["stand"][(self.t // 6) % len(self.poses["stand"])]
        img, (ax, ay) = pose[side]
        surf.blit(img, (round(x) - ax, round(fy) - ay - 1 - lift))
        if self.air and abs(self.spin) >= 30:
            n = int(round(abs(self.spin) / 180))
            ok = abs(abs(self.spin) - n * 180) <= TOL
            draw_text(surf, "%d" % int(abs(self.spin)), round(x), round(fy) - 42,
                      (140, 255, 150) if ok else (255, 120, 100), align="center")

    def _hud(self, surf):
        surf.fill((10, 8, 16), (0, 0, W, HUD_H - 1))
        surf.fill((60, 40, 80), (0, HUD_H - 1, W, 1))
        # score toward the goal
        draw_text(surf, "SCORE %d / %d" % (self.score, GOAL), 4, 2, (255, 230, 120))
        bw = 84
        surf.fill((40, 30, 50), (4, 11, bw + 2, 5))
        surf.fill((120, 255, 140) if self.score >= GOAL else (255, 200, 60),
                  (5, 12, round(bw * min(1, self.score / GOAL)), 3))
        # clock
        if self.ghost:
            col = (200, 160, 255) if (self.t // 10) % 2 else (255, 255, 255)
            draw_text(surf, "SKATE OR DIE!", W // 2, 2, col, align="center")
            draw_text(surf, "0:00", W // 2, 11, (255, 60, 60), align="center")
        else:
            secs = (self.timer + FPS - 1) // FPS
            col = (255, 255, 255)
            if not self.timer_on:
                col = (150, 150, 170)
            elif secs <= 10 and (self.t // 10) % 2:
                col = (255, 60, 60)
            draw_text(surf, "TIME", W // 2, 2, (180, 170, 200), align="center")
            draw_text(surf, "%d:%02d" % (secs // 60, secs % 60), W // 2, 11, col, align="center")
        draw_text(surf, LEVEL_NAME, W - 4, 2, (255, 160, 120), align="right")
        if self.mode == "skate":
            draw_text(surf, "SPEED", W - 64, 11, (150, 150, 170), align="right")
            sp = self.speed if not self.air else math.hypot(self.vx, self.vy)
            surf.fill((40, 30, 50), (W - 60, 12, 56, 5))
            surf.fill((90, 200, 255), (W - 59, 13, round(54 * min(1, sp / MAX_SPEED)), 3))
        else:
            draw_text(surf, "FIND THE BOARD", W - 4, 11, (150, 220, 255), align="right")
        if self.phase == "intro":
            band = pygame.Surface((W, 56), pygame.SRCALPHA)
            band.fill((6, 4, 12, 200))
            surf.blit(band, (0, 54))
            draw_text(surf, "LEVEL %d" % self.level, W // 2, 58, (255, 220, 80), scale=2, align="center")
            draw_text(surf, "THE SKATE PARK", W // 2, 76, (255, 255, 255), align="center")
            draw_text(surf, "FIND THE BOARD. LAND TRICKS. 100 POINTS!", W // 2, 88, (200, 200, 230),
                      align="center")
            if self.t > INTRO - 25:
                draw_text(surf, "GO!", W // 2, 116, (255, 60, 40), scale=3, align="center")
        if self.banner and self.phase == "play":
            text, f, col = self.banner
            if f > 0 and (f > 30 or (f // 4) % 2):
                scale = 2 if len(text) <= 18 else 1
                band = pygame.Surface((W, 14 * scale + 6), pygame.SRCALPHA)
                band.fill((6, 4, 12, 170))
                surf.blit(band, (0, H - 14 * scale - 12))
                wob = round(math.sin(self.t * 0.5) * 2) if f > 90 else 0
                draw_text(surf, text, W // 2 + wob, H - 14 * scale - 8, col, scale=scale, align="center")
        if self.phase == "won" and self.end_t > 10:
            band = pygame.Surface((W, 44), pygame.SRCALPHA)
            band.fill((6, 4, 12, 200))
            surf.blit(band, (0, 62))
            draw_text(surf, "COURSE CLEAR!", W // 2, 66, (255, 220, 60), scale=3, align="center")
            draw_text(surf, "%d POINTS  %d TRICKS" % (self.score, len(self.tricks)), W // 2, 92,
                      (255, 255, 255), align="center")
        if self.phase == "lost" and self.end_t > 10:
            band = pygame.Surface((W, 40), pygame.SRCALPHA)
            band.fill((6, 4, 12, 200))
            surf.blit(band, (0, 66))
            draw_text(surf, "THE GHOST GOT YOU", W // 2, 70, (210, 180, 255), scale=2, align="center")
            draw_text(surf, "AKUMA FALLS...", W // 2, 92, (255, 255, 255), align="center")
        if self.menu.open:
            self.menu.draw(surf)
