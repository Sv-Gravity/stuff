#!/usr/bin/env python3
"""
KUMATE - a tiny one-hit-kill fighting game for two players.

Run:    python3 kumate.py
Needs:  pygame   (sudo apt install python3-pygame   or   pip install pygame)

Player 1 (left side):   A / D move, W jump, S crouch, SPACE attack
Player 2 (right side):  LEFT / RIGHT move, UP jump, DOWN crouch, / attack

Moves (identical for both fighters):
    standing punch   attack
    crouching kick   down + attack
    jump             up
    dive kick        attack in mid-air (flies 45 degrees forward and down)

One hit wins the round. First to 3 rounds (best of 5) wins the match.
F11 fullscreen, F1 show hitboxes, ESC back / quit.
"""

import math
import random
import sys

import pygame

# --------------------------------------------------------------------------
# Tuning
# --------------------------------------------------------------------------
W, H = 960, 540
FPS = 60
GROUND = 450            # y of the floor
WALL = 50               # how close fighters can get to the screen edge

GRAVITY = 0.9
JUMP_V = -17.0
WALK = 5.0
DIVE = 11.0             # speed on each axis, so the path is exactly 45 degrees
MIN_DIVE_HEIGHT = 45    # feet must be this far off the floor to dive kick

BODY_W = 44
STAND_H = 130
CROUCH_H = 80

# (startup, active, recovery) in frames
PUNCH = (5, 4, 14)
CKICK = (7, 4, 18)
LAND_RECOVERY = 14      # frames stuck after a dive kick lands

ROUNDS_TO_WIN = 3       # best of 5

RED = (205, 45, 45)
BLUE = (45, 85, 215)
SKIN = (240, 200, 160)
SKIN_DARK = (205, 160, 125)
HAIR = (30, 24, 20)
BELT = (20, 20, 20)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GOLD = (255, 245, 110)
FLAME = (235, 70, 20)
P_TAG = ((255, 230, 80), (90, 230, 120))    # 1P / 2P cursor colours

# The two fighters. Identical in every way except the colour of the gi.
ROSTER = [
    dict(name='SVEN', color=RED, country='SWEDEN', map=(497, 100),
         quote='"MY MEATBALLS HIT HARDER THAN YOUR KICKS!"'),
    dict(name='LYU', color=BLUE, country='JAPAN', map=(866, 178),
         quote='"ONE HIT IS ALL I NEED. IT IS ALSO ALL I HAVE."'),
]

P1_KEYS = dict(left=pygame.K_a, right=pygame.K_d, up=pygame.K_w,
               down=pygame.K_s)
P2_KEYS = dict(left=pygame.K_LEFT, right=pygame.K_RIGHT, up=pygame.K_UP,
               down=pygame.K_DOWN)
P1_ATTACK = (pygame.K_SPACE,)
P2_ATTACK = (pygame.K_SLASH, pygame.K_KP_DIVIDE)
SWAP_KEYS = (pygame.K_a, pygame.K_d, pygame.K_LEFT, pygame.K_RIGHT)
KEY_HELP = ('WASD + SPACE', 'ARROWS + /')

NO_INPUT = dict(move=0, up=False, down=False, attack=False)

# --------------------------------------------------------------------------
# Poses. Each joint is (forward, up) measured from the point between the feet.
# "f_" = limb nearer the camera, "b_" = limb behind the body.
# --------------------------------------------------------------------------
STAND_P = dict(head=(4, 121), sh=(0, 106), hip=(0, 60),
               f_elbow=(14, 84), f_hand=(28, 98),
               b_elbow=(4, 80), b_hand=(18, 92),
               f_knee=(14, 32), f_foot=(16, 6),
               b_knee=(-8, 30), b_foot=(-16, 6))
PUNCH_P = dict(head=(10, 119), sh=(8, 104), hip=(2, 58),
               f_elbow=(44, 103), f_hand=(80, 102),
               b_elbow=(-10, 86), b_hand=(4, 80),
               f_knee=(24, 30), f_foot=(28, 6),
               b_knee=(-12, 30), b_foot=(-22, 6))
CROUCH_P = dict(head=(8, 68), sh=(2, 56), hip=(-6, 26),
                f_elbow=(16, 40), f_hand=(28, 54),
                b_elbow=(6, 36), b_hand=(18, 48),
                f_knee=(18, 30), f_foot=(14, 6),
                b_knee=(-24, 22), b_foot=(-18, 6))
CKICK_P = dict(head=(-8, 66), sh=(-10, 54), hip=(-6, 24),
               f_elbow=(4, 40), f_hand=(16, 52),
               b_elbow=(-26, 36), b_hand=(-34, 14),
               f_knee=(40, 18), f_foot=(90, 12),
               b_knee=(-22, 22), b_foot=(-16, 6))
JUMP_P = dict(head=(4, 123), sh=(0, 108), hip=(0, 64),
              f_elbow=(14, 88), f_hand=(26, 102),
              b_elbow=(2, 84), b_hand=(16, 96),
              f_knee=(18, 46), f_foot=(10, 22),
              b_knee=(-4, 40), b_foot=(-16, 24))
DIVE_P = dict(head=(-28, 108), sh=(-22, 94), hip=(-4, 54),
              f_elbow=(-6, 78), f_hand=(8, 90),
              b_elbow=(-38, 80), b_hand=(-50, 90),
              f_knee=(18, 32), f_foot=(40, 10),
              b_knee=(14, 66), b_foot=(-6, 50))
LAND_P = dict(head=(10, 98), sh=(6, 84), hip=(0, 44),
              f_elbow=(18, 62), f_hand=(30, 74),
              b_elbow=(8, 58), b_hand=(20, 68),
              f_knee=(20, 30), f_foot=(18, 6),
              b_knee=(-16, 26), b_foot=(-18, 6))
KO_AIR_P = dict(head=(-26, 110), sh=(-16, 98), hip=(0, 60),
                f_elbow=(6, 104), f_hand=(26, 114),
                b_elbow=(0, 110), b_hand=(18, 126),
                f_knee=(20, 44), f_foot=(36, 24),
                b_knee=(14, 36), b_foot=(26, 12))
KO_DOWN_P = dict(head=(-72, 12), sh=(-56, 12), hip=(-10, 12),
                 f_elbow=(-44, 26), f_hand=(-28, 14),
                 b_elbow=(-40, 10), b_hand=(-22, 8),
                 f_knee=(18, 26), f_foot=(40, 8),
                 b_knee=(16, 10), b_foot=(44, 8))
WIN_P = dict(head=(2, 123), sh=(0, 108), hip=(0, 62),
             f_elbow=(14, 128), f_hand=(10, 152),
             b_elbow=(-12, 88), b_hand=(-4, 70),
             f_knee=(8, 32), f_foot=(12, 6),
             b_knee=(-8, 32), b_foot=(-12, 6))

# A very rough world map for the fighter select screen.
LAND = [
    [(60, 125), (150, 95), (250, 105), (300, 145), (260, 185), (230, 225),
     (200, 265), (170, 255), (150, 215), (100, 185), (70, 155)],      # N America
    [(205, 268), (262, 274), (296, 296), (214, 296)],                 # S America
    [(300, 70), (352, 62), (372, 88), (342, 112), (310, 102)],        # Greenland
    [(430, 125), (470, 112), (520, 115), (540, 145), (500, 165),
     (470, 185), (440, 175), (425, 150)],                             # Europe
    [(478, 78), (500, 62), (512, 96), (498, 118), (482, 108)],        # Scandinavia
    [(440, 205), (500, 195), (540, 225), (550, 275), (520, 296),
     (470, 296), (450, 285), (430, 245)],                             # Africa
    [(540, 115), (620, 85), (720, 85), (820, 105), (850, 145),
     (830, 185), (780, 205), (760, 245), (720, 265), (690, 235),
     (650, 245), (610, 215), (570, 185), (545, 155)],                 # Asia
    [(864, 150), (878, 160), (874, 188), (860, 198), (856, 176)],     # Japan
    [(775, 262), (835, 252), (872, 276), (860, 296), (790, 296)],     # Australia
]


def mix(a, b, t):
    """Blend two poses: t=0 gives a, t=1 gives b."""
    return {k: (a[k][0] + (b[k][0] - a[k][0]) * t,
                a[k][1] + (b[k][1] - a[k][1]) * t) for k in a}


def extension(t, frames):
    """How far a strike is extended (0..1) on frame t of the move."""
    startup, active, recovery = frames
    if t < startup:
        return t / startup
    if t < startup + active:
        return 1.0
    return max(0.0, 1.0 - (t - startup - active) / recovery)


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shade(color, amount):
    return tuple(int(c * amount) for c in color)


def thick(surf, color, a, b, w):
    """A line with real thickness and rounded ends."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length * w / 2, dx / length * w / 2
    pygame.draw.polygon(surf, color, [(a[0] + nx, a[1] + ny),
                                      (b[0] + nx, b[1] + ny),
                                      (b[0] - nx, b[1] - ny),
                                      (a[0] - nx, a[1] - ny)])
    pygame.draw.circle(surf, color, (int(a[0]), int(a[1])), w // 2)
    pygame.draw.circle(surf, color, (int(b[0]), int(b[1])), w // 2)


def vertical_gradient(size, stops):
    """A surface filled top-to-bottom through a list of colours."""
    w, h = size
    surf = pygame.Surface(size)
    n = len(stops) - 1
    for y in range(h):
        t = y / max(1, h - 1) * n
        i = min(int(t), n - 1)
        pygame.draw.line(surf, lerp_color(stops[i], stops[i + 1], t - i),
                         (0, y), (w, y))
    return surf


def fancy_text(font, string, top, bottom, outline):
    """Arcade lettering: vertical gradient, fat black outline, drop shadow."""
    face = font.render(string, True, WHITE).convert_alpha()
    w, h = face.get_size()
    grad = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        pygame.draw.line(grad, lerp_color(top, bottom, y / max(1, h - 1)),
                         (0, y), (w, y))
    face.blit(grad, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    edge = font.render(string, True, BLACK)
    out = pygame.Surface((w + outline * 3, h + outline * 3), pygame.SRCALPHA)
    for dx in (0, outline, outline * 2):
        for dy in (0, outline, outline * 2):
            out.blit(edge, (dx, dy))
    out.blit(edge, (outline * 3, outline * 3))        # drop shadow
    out.blit(face, (outline, outline))
    return out


def make_portrait(color):
    """Head-and-shoulders mugshot, 200x200, looking to the right."""
    dark = shade(color, 0.6)
    s = vertical_gradient((200, 200), [(60, 60, 75), (170, 170, 185)])
    d = pygame.draw
    d.polygon(s, color, [(0, 200), (22, 152), (72, 128), (128, 128),
                         (178, 152), (200, 200)])
    d.polygon(s, SKIN, [(80, 128), (120, 128), (100, 178)])
    thick(s, dark, (78, 127), (102, 190), 10)
    thick(s, dark, (122, 127), (98, 190), 10)
    d.rect(s, SKIN_DARK, (84, 104, 32, 30))
    d.circle(s, SKIN, (57, 86), 10)
    d.circle(s, SKIN, (143, 86), 10)
    d.ellipse(s, SKIN, (56, 28, 88, 104))
    d.polygon(s, HAIR, [(54, 76), (54, 42), (70, 22), (92, 12), (116, 10),
                        (136, 20), (148, 40), (148, 76), (140, 54),
                        (126, 44), (112, 54), (98, 42), (84, 54), (70, 44),
                        (60, 58)])
    thick(s, HAIR, (68, 72), (92, 80), 7)             # angry eyebrows
    thick(s, HAIR, (110, 80), (134, 72), 7)
    d.ellipse(s, WHITE, (70, 82, 22, 11))
    d.ellipse(s, WHITE, (110, 82, 22, 11))
    d.circle(s, BLACK, (85, 88), 4)
    d.circle(s, BLACK, (125, 88), 4)
    thick(s, SKIN_DARK, (102, 92), (106, 106), 4)     # nose
    thick(s, SKIN_DARK, (106, 106), (98, 108), 4)
    thick(s, (120, 60, 50), (88, 119), (114, 117), 4)  # stern mouth
    return s


def draw_flag(surf, country, rect):
    x, y, w, h = rect
    if country == 'SWEDEN':
        pygame.draw.rect(surf, (0, 106, 167), rect)
        pygame.draw.rect(surf, (254, 204, 0), (x + w * 5 // 16, y, w // 6, h))
        pygame.draw.rect(surf, (254, 204, 0), (x, y + h * 2 // 5, w, h // 5))
    else:
        pygame.draw.rect(surf, WHITE, rect)
        pygame.draw.circle(surf, (188, 0, 45), (x + w // 2, y + h // 2),
                           h * 3 // 10)
    pygame.draw.rect(surf, BLACK, rect, 2)


def make_title_bg():
    """Sunset, a big cheesy sun and a city skyline to fight in front of."""
    s = vertical_gradient((W, H), [(25, 10, 70), (150, 40, 110),
                                   (250, 150, 60)])
    pygame.draw.circle(s, (255, 225, 120), (W // 2, GROUND - 40), 150)
    rng = random.Random(7)
    x = -10
    while x < W:
        w = rng.randint(45, 95)
        h = rng.randint(50, 190)
        if 300 < x + w and x < 660:       # keep the middle low: fighters go here
            h = rng.randint(25, 55)
        pygame.draw.rect(s, (28, 16, 48), (x, GROUND - h, w, h))
        for wy in range(GROUND - h + 10, GROUND - 14, 18):
            for wx in range(x + 8, x + w - 10, 14):
                if rng.random() < 0.35:
                    pygame.draw.rect(s, (255, 220, 110), (wx, wy, 6, 9))
        x += w + rng.randint(0, 8)
    pygame.draw.rect(s, (14, 8, 26), (0, GROUND, W, H - GROUND))
    pygame.draw.line(s, (120, 80, 150), (0, GROUND), (W, GROUND), 3)
    return s


def make_map_bg():
    s = pygame.Surface((W, H))
    s.fill((22, 44, 130))
    for x in range(0, W, 48):
        pygame.draw.line(s, (40, 70, 165), (x, 0), (x, H))
    for y in range(0, H, 48):
        pygame.draw.line(s, (40, 70, 165), (0, y), (W, y))
    for poly in LAND:
        pygame.draw.polygon(s, (40, 135, 80), poly)
        pygame.draw.polygon(s, (18, 80, 50), poly, 3)
    return s


# --------------------------------------------------------------------------
# Fighter
# --------------------------------------------------------------------------
class Fighter:
    def __init__(self, keys):
        self.keys = keys
        self.set_character(ROSTER[0])
        self.reset(W // 2, 1)

    def set_character(self, info):
        self.name = info['name']
        self.color = info['color']
        self.dark = shade(self.color, 0.7)
        self.light = lerp_color(self.color, WHITE, 0.6)

    def reset(self, x, facing):
        self.x, self.y = float(x), float(GROUND)
        self.vx = self.vy = 0.0
        self.facing = facing
        self.state = 'idle'   # idle crouch jump punch ckick dive land ko win
        self.timer = 0
        self.walk = 0.0
        self.dive_queued = False

    # ---- input ----------------------------------------------------------
    def read(self, pressed, attack):
        k = self.keys
        return dict(move=int(pressed[k['right']]) - int(pressed[k['left']]),
                    up=pressed[k['up']], down=pressed[k['down']],
                    attack=attack)

    # ---- logic ----------------------------------------------------------
    def face(self, other):
        if other.x != self.x:
            self.facing = 1 if other.x > self.x else -1

    def update(self, inp, other):
        s = self.state
        if s == 'win':
            return

        if s == 'ko':
            if self.y < GROUND or self.vy < 0:
                self.vy += GRAVITY
                self.x += self.vx
                self.y += self.vy
                if self.y >= GROUND:
                    self.y, self.vx, self.vy = float(GROUND), 0.0, 0.0
            self.clamp()
            return

        if s in ('idle', 'crouch'):
            self.face(other)
            if inp['attack']:
                self.state = 'ckick' if inp['down'] else 'punch'
                self.timer = 0
                self.vx = 0.0
            elif inp['up']:
                self.state = 'jump'
                self.vy = JUMP_V
                self.vx = WALK * inp['move']
                self.dive_queued = False
            elif inp['down']:
                self.state = 'crouch'
                self.vx = 0.0
            else:
                self.state = 'idle'
                self.vx = WALK * inp['move']
                if self.vx:
                    self.walk += 0.25

        elif s == 'jump':
            if inp['attack']:
                self.dive_queued = True
            if self.dive_queued and GROUND - self.y >= MIN_DIVE_HEIGHT:
                self.face(other)
                self.state = 'dive'
                self.vx = DIVE * self.facing
                self.vy = DIVE

        elif s in ('punch', 'ckick', 'land'):
            self.timer += 1
            total = {'punch': sum(PUNCH), 'ckick': sum(CKICK),
                     'land': LAND_RECOVERY}[s]
            if self.timer >= total:
                self.state = 'idle'

        # physics
        self.x += self.vx
        if self.state == 'jump':
            self.vy += GRAVITY
            self.y += self.vy
            if self.y >= GROUND:
                self.y, self.vx, self.vy = float(GROUND), 0.0, 0.0
                self.state = 'idle'
        elif self.state == 'dive':
            self.y += self.vy
            if self.y >= GROUND:
                self.y, self.vx, self.vy = float(GROUND), 0.0, 0.0
                self.state = 'land'
                self.timer = 0
        self.clamp()

    def clamp(self):
        self.x = max(WALL, min(W - WALL, self.x))

    def knock_out(self, attacker):
        self.facing = 1 if attacker.x >= self.x else -1
        self.state = 'ko'
        self.vx = -self.facing * 5.0
        self.vy = -8.0

    # ---- boxes ----------------------------------------------------------
    def box(self, f0, f1, u0, u1):
        """Rect from forward f0..f1 and height u0..u1, relative to the feet."""
        xa = self.x + self.facing * f0
        xb = self.x + self.facing * f1
        return pygame.Rect(int(min(xa, xb)), int(self.y - u1),
                           int(abs(xb - xa)), int(u1 - u0))

    def hurtbox(self):
        h = CROUCH_H if self.state in ('crouch', 'ckick') else STAND_H
        return pygame.Rect(int(self.x - BODY_W / 2), int(self.y - h),
                           BODY_W, h)

    def hitbox(self):
        s, t = self.state, self.timer
        if s == 'punch' and PUNCH[0] <= t < PUNCH[0] + PUNCH[1]:
            return self.box(20, 84, 92, 112)      # chest height: whiffs over a croucher
        if s == 'ckick' and CKICK[0] <= t < CKICK[0] + CKICK[1]:
            return self.box(20, 96, 0, 26)        # ankle height: jump over it
        if s == 'dive':
            return self.box(18, 60, -8, 32)       # the leading foot
        return None

    # ---- drawing --------------------------------------------------------
    def pose(self):
        s = self.state
        if s == 'crouch':
            return CROUCH_P
        if s == 'punch':
            return mix(STAND_P, PUNCH_P, extension(self.timer, PUNCH))
        if s == 'ckick':
            return mix(CROUCH_P, CKICK_P, extension(self.timer, CKICK))
        if s == 'jump':
            return JUMP_P
        if s == 'dive':
            return DIVE_P
        if s == 'land':
            return LAND_P
        if s == 'ko':
            return KO_AIR_P if self.y < GROUND else KO_DOWN_P
        if s == 'win':
            return WIN_P
        if self.vx:                                # walking: shuffle the feet
            sway = math.sin(self.walk) * 8
            p = dict(STAND_P)
            p['f_foot'] = (STAND_P['f_foot'][0] + sway, 6)
            p['b_foot'] = (STAND_P['b_foot'][0] - sway, 6)
            p['f_knee'] = (STAND_P['f_knee'][0] + sway / 2, 32)
            p['b_knee'] = (STAND_P['b_knee'][0] - sway / 2, 30)
            return p
        return STAND_P

    def draw(self, surf, shadow=(110, 76, 44)):
        pose = self.pose()

        def at(name):
            fx, up = pose[name]
            return (self.x + self.facing * fx, self.y - up)

        def dot(name, color, r):
            p = at(name)
            pygame.draw.circle(surf, color, (int(p[0]), int(p[1])), r)

        pygame.draw.ellipse(surf, shadow,
                            (int(self.x) - 34, GROUND - 5, 68, 12))

        # back leg and arm
        thick(surf, self.dark, at('hip'), at('b_knee'), 14)
        thick(surf, self.dark, at('b_knee'), at('b_foot'), 14)
        dot('b_foot', SKIN, 7)
        thick(surf, self.dark, at('sh'), at('b_elbow'), 11)
        thick(surf, self.dark, at('b_elbow'), at('b_hand'), 11)
        dot('b_hand', SKIN, 6)

        # torso and belt
        sh, hip = at('sh'), at('hip')
        thick(surf, self.color, sh, hip, 30)
        dx, dy = sh[0] - hip[0], sh[1] - hip[1]
        length = math.hypot(dx, dy) or 1.0
        dx, dy = dx / length, dy / length
        cx, cy = hip[0] + dx * 6, hip[1] + dy * 6
        thick(surf, BELT, (cx - dy * 14, cy + dx * 14),
              (cx + dy * 14, cy - dx * 14), 7)

        # front leg
        thick(surf, self.color, hip, at('f_knee'), 14)
        thick(surf, self.color, at('f_knee'), at('f_foot'), 14)
        dot('f_foot', SKIN, 7)

        # head (hair behind, face in front, one eye so you can see facing)
        hx, hy = at('head')
        pygame.draw.circle(surf, HAIR,
                           (int(hx - self.facing * 3), int(hy - 3)), 13)
        pygame.draw.circle(surf, SKIN, (int(hx), int(hy)), 12)
        if self.state != 'ko':
            pygame.draw.circle(surf, BLACK,
                               (int(hx + self.facing * 6), int(hy - 2)), 2)

        # front arm
        thick(surf, self.color, sh, at('f_elbow'), 11)
        thick(surf, self.color, at('f_elbow'), at('f_hand'), 11)
        dot('f_hand', SKIN, 6)


# --------------------------------------------------------------------------
# Game
# --------------------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption('KUMATE')
        flags = getattr(pygame, 'SCALED', 0) | pygame.RESIZABLE
        try:
            self.screen = pygame.display.set_mode((W, H), flags)
        except pygame.error:
            self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()

        self.logo = pygame.font.Font(None, 210)
        self.big = pygame.font.Font(None, 110)
        self.head = pygame.font.Font(None, 68)
        self.mid = pygame.font.Font(None, 48)
        self.tag = pygame.font.Font(None, 36)
        self.small = pygame.font.Font(None, 28)
        for font in (self.logo, self.big, self.head):
            font.set_italic(True)

        self.title_bg = make_title_bg()
        self.map_bg = make_map_bg()
        self.faces = [make_portrait(info['color']) for info in ROSTER]
        self.veil = pygame.Surface((W, H))      # for flashes and dimming
        self.cache = {}                         # pre-rendered fancy text etc.

        self.f1 = Fighter(P1_KEYS)
        self.f2 = Fighter(P2_KEYS)
        self.pick = [0, 1]      # which ROSTER entry player 1 / player 2 has
        self.debug = False
        self.phase = 'title'    # title select vs intro fight ko gameover
        self.timer = 0
        self.hitstop = 0
        self.sparks = []
        self.score = [0, 0]
        self.round = 1
        self.round_decided = True
        self.banner = ''
        self.banner_winner = None
        self.apply_picks()
        self.place_fighters()

    # ---- flow -----------------------------------------------------------
    def goto(self, phase):
        self.phase = phase
        self.timer = 0

    def place_fighters(self):
        self.f1.reset(W // 2 - 180, 1)
        self.f2.reset(W // 2 + 180, -1)

    def apply_picks(self):
        self.f1.set_character(ROSTER[self.pick[0]])
        self.f2.set_character(ROSTER[self.pick[1]])

    def start_match(self):
        self.score = [0, 0]
        self.round = 1
        self.start_round()

    def start_round(self):
        self.place_fighters()
        self.sparks = []
        self.goto('intro')

    def title_demo(self):
        """The two fighters take turns punching over each other's head."""
        a, b = self.f1, self.f2
        a.reset(W // 2 - 55, 1)
        b.reset(W // 2 + 55, -1)
        t = self.timer % 240
        if 70 <= t < 70 + sum(PUNCH):
            a.state, a.timer, b.state = 'punch', t - 70, 'crouch'
        elif 190 <= t < 190 + sum(PUNCH):
            b.state, b.timer, a.state = 'punch', t - 190, 'crouch'

    def update(self, attacks):
        pressed = pygame.key.get_pressed()

        if self.phase == 'title':
            self.timer += 1
            self.title_demo()
            if self.timer > 30 and any(attacks):
                self.goto('select')

        elif self.phase == 'select':
            self.timer += 1
            self.apply_picks()
            if self.timer > 10 and any(attacks):
                self.goto('vs')

        elif self.phase == 'vs':
            self.timer += 1
            if self.timer >= 240 or (self.timer > 30 and any(attacks)):
                self.start_match()

        elif self.phase == 'intro':
            self.timer += 1
            if self.timer >= 70:
                self.goto('fight')

        elif self.phase == 'fight':
            self.timer += 1
            in1 = self.f1.read(pressed, attacks[0])
            in2 = self.f2.read(pressed, attacks[1])
            self.f1.update(in1, self.f2)
            self.f2.update(in2, self.f1)
            self.separate()
            self.check_hits()

        elif self.phase == 'ko':
            if self.hitstop > 0:            # freeze on the moment of impact
                self.hitstop -= 1
                return
            self.timer += 1
            self.f1.update(NO_INPUT, self.f2)
            self.f2.update(NO_INPUT, self.f1)
            if self.timer > 30:
                for f in (self.f1, self.f2):
                    if f.state == 'idle':
                        f.state = 'win'
            if self.timer >= 150:
                if max(self.score) >= ROUNDS_TO_WIN:
                    self.goto('gameover')
                else:
                    if self.round_decided:   # a double K.O. replays the round
                        self.round += 1
                    self.start_round()

        elif self.phase == 'gameover':
            self.timer += 1
            if self.timer > 40 and any(attacks):
                self.goto('select')

    def separate(self):
        """Stop two grounded fighters from walking through each other."""
        a, b = self.f1, self.f2
        if a.y < GROUND or b.y < GROUND:
            return
        for _ in range(2):
            dx = b.x - a.x
            overlap = BODY_W - abs(dx)
            if overlap <= 0:
                return
            sign = 1 if dx > 0 or (dx == 0 and a.facing > 0) else -1
            a.x -= sign * overlap / 2
            b.x += sign * overlap / 2
            a.clamp()
            b.clamp()

    def check_hits(self):
        a, b = self.f1, self.f2
        ha, hb = a.hitbox(), b.hitbox()
        hurt_a, hurt_b = a.hurtbox(), b.hurtbox()
        a_hit = bool(ha and ha.colliderect(hurt_b))
        b_hit = bool(hb and hb.colliderect(hurt_a))
        if not (a_hit or b_hit):
            return

        self.sparks = []
        if a_hit:
            self.sparks.append(ha.clip(hurt_b).center)
        if b_hit:
            self.sparks.append(hb.clip(hurt_a).center)
        if a_hit:
            b.knock_out(a)
        if b_hit:
            a.knock_out(b)

        if a_hit and b_hit:
            self.banner, self.banner_winner = 'DOUBLE K.O.', None
        else:
            winner = 0 if a_hit else 1
            self.score[winner] += 1
            self.banner, self.banner_winner = 'K.O.', (a, b)[winner]
        self.round_decided = not (a_hit and b_hit)
        self.goto('ko')
        self.hitstop = 12

    # ---- drawing helpers ------------------------------------------------
    def text(self, font, string, color, center, shadow=True):
        if shadow:
            img = font.render(string, True, BLACK)
            self.screen.blit(img, img.get_rect(center=(center[0] + 2,
                                                       center[1] + 2)))
        img = font.render(string, True, color)
        self.screen.blit(img, img.get_rect(center=center))

    def fancy(self, font, string, top, bottom, center, outline=3):
        key = (id(font), string, top, bottom, outline)
        if key not in self.cache:
            self.cache[key] = fancy_text(font, string, top, bottom, outline)
        img = self.cache[key]
        self.screen.blit(img, img.get_rect(center=center))

    def name_plate(self, fighter, font, center, outline=3):
        self.fancy(font, fighter.name, fighter.light, fighter.color, center,
                   outline)

    def portrait(self, index, size, flip):
        key = ('face', index, size, flip)
        if key not in self.cache:
            img = pygame.transform.scale(self.faces[index], (size, size))
            if flip:
                img = pygame.transform.flip(img, True, False)
            self.cache[key] = img
        return self.cache[key]

    def flash(self, alpha, color=WHITE):
        if alpha > 0:
            self.veil.fill(color)
            self.veil.set_alpha(min(255, int(alpha)))
            self.screen.blit(self.veil, (0, 0))

    # ---- screens --------------------------------------------------------
    def draw_title(self):
        s, cx, t = self.screen, W // 2, self.timer
        s.blit(self.title_bg, (0, 0))
        for fighter in (self.f1, self.f2):
            fighter.draw(s, shadow=(8, 4, 16))

        # the logo slams down from above, then everything else appears
        logo_y = 125 if t >= 30 else -130 + 255 * t // 30
        self.fancy(self.logo, 'KUMATE', GOLD, FLAME, (cx, logo_y), 6)
        if t < 30:
            return
        ribbon = [(205, 222), (755, 222), (777, 243), (755, 264), (205, 264),
                  (183, 243)]
        pygame.draw.polygon(s, (190, 20, 30), ribbon)
        pygame.draw.polygon(s, BLACK, ribbon, 3)
        self.text(self.tag, "THE WORLD'S OKAYEST WARRIORS", WHITE, (cx, 244))
        if (t // 28) % 2 == 0:
            self.fancy(self.mid, 'PRESS SPACE OR / TO START', WHITE,
                       (255, 210, 90), (cx, 486), 2)
        self.text(self.small, '(C) 2026 TOTALLY ORIGINAL GAMES CO.', WHITE,
                  (210, 522))
        self.text(self.small, 'CREDITS 99', WHITE, (W - 90, 522))
        self.flash(255 - (t - 30) * 20)

    def draw_select(self):
        s, cx = self.screen, W // 2
        blink = (self.timer // 8) % 2 == 0
        s.blit(self.map_bg, (0, 0))
        self.fancy(self.head, 'PLAYER SELECT', GOLD, FLAME, (cx, 36), 3)

        # where in the world they come from
        for info in ROSTER:
            mx, my = info['map']
            draw_flag(s, info['country'], (mx + 12, my - 30, 36, 24))
            pygame.draw.circle(s, GOLD if blink else FLAME, (mx, my), 7)
            pygame.draw.circle(s, BLACK, (mx, my), 7, 2)

        # dim the bottom of the map and put the roster on it
        self.veil.fill(BLACK)
        self.veil.set_alpha(170)
        s.blit(self.veil, (0, 296), (0, 0, W, H - 296))
        pygame.draw.line(s, GOLD, (0, 296), (W, 296), 3)

        tiles = [pygame.Rect(cx - 104 + i * 108, 336, 100, 100)
                 for i in range(len(ROSTER))]
        for i, rect in enumerate(tiles):
            s.blit(self.portrait(i, 100, False), rect.topleft)

        for player in (0, 1):
            index = self.pick[player]
            info = ROSTER[index]
            fighter = (self.f1, self.f2)[player]
            col = P_TAG[player]
            label = '%dP' % (player + 1)

            # cursor on the roster
            rect = tiles[index]
            pygame.draw.rect(s, col if blink else WHITE, rect.inflate(8, 8), 5)
            self.text(self.small, label, col, (rect.centerx, rect.top - 20))

            # big portrait in the corner, looking in toward the middle
            big = pygame.Rect(36 if player == 0 else W - 216, 312, 180, 180)
            s.blit(self.portrait(index, 180, player == 1), big.topleft)
            pygame.draw.rect(s, col, big, 4)
            self.name_plate(fighter, self.mid, (big.centerx, 517), 2)

            # player tag, flag, home country and keys beside the portrait
            ix = 292 if player == 0 else W - 292
            self.fancy(self.head, label, WHITE, col, (ix, 340), 3)
            draw_flag(s, info['country'], (ix - 24, 376, 48, 32))
            self.text(self.small, info['country'], WHITE, (ix, 426))
            self.text(self.small, KEY_HELP[player], col, (ix, 456))

        self.text(self.small, 'LEFT / RIGHT : SWAP', WHITE, (cx, 470))
        self.text(self.small, 'ATTACK : FIGHT!', WHITE, (cx, 498))

    def draw_vs(self):
        s, cx, t = self.screen, W // 2, self.timer
        a, b = self.f1, self.f2
        s.fill(shade(a.color, 0.45))
        pygame.draw.polygon(s, shade(b.color, 0.45),
                            [(540, 0), (W, 0), (W, H), (420, H)])
        pygame.draw.line(s, WHITE, (540, 0), (420, H), 6)

        # portraits slide in from the sides
        slide = max(0, 20 - t) * 30
        left = pygame.Rect(80 - slide, 70, 250, 250)
        right = pygame.Rect(W - 330 + slide, 70, 250, 250)
        s.blit(self.portrait(self.pick[0], 250, False), left.topleft)
        s.blit(self.portrait(self.pick[1], 250, True), right.topleft)
        pygame.draw.rect(s, WHITE, left, 5)
        pygame.draw.rect(s, WHITE, right, 5)
        self.name_plate(a, self.big, (left.centerx, 372), 4)
        self.name_plate(b, self.big, (right.centerx, 372), 4)
        self.text(self.small, '1P   ' + KEY_HELP[0], P_TAG[0],
                  (left.centerx, 428))
        self.text(self.small, '2P   ' + KEY_HELP[1], P_TAG[1],
                  (right.centerx, 428))
        if t >= 20:
            self.fancy(self.logo, 'VS', GOLD, FLAME, (cx, 200), 6)

        self.text(self.small, 'PUNCH: ATTACK        LOW KICK: DOWN + ATTACK',
                  WHITE, (cx, 480))
        self.text(self.small, 'JUMP: UP        DIVE KICK: ATTACK IN MID-AIR',
                  WHITE, (cx, 508))
        self.flash(255 - (t - 20) * 25 if t >= 20 else 0)

    def draw_stage(self):
        s = self.screen
        s.fill((226, 208, 170))
        for x in range(0, W + 1, 120):
            pygame.draw.line(s, (196, 172, 128), (x, 60), (x, GROUND), 3)
        pygame.draw.line(s, (196, 172, 128), (0, 250), (W, 250), 3)
        pygame.draw.rect(s, (60, 42, 30), (0, 0, W, 44))
        pygame.draw.rect(s, (120, 82, 50), (0, 44, W, 16))
        pygame.draw.rect(s, (150, 105, 62), (0, GROUND, W, H - GROUND))
        pygame.draw.line(s, (95, 62, 36), (0, GROUND), (W, GROUND), 4)
        for i in range(1, 4):
            y = GROUND + i * 24
            pygame.draw.line(s, (128, 88, 52), (0, y), (W, y), 2)

    def draw_hud(self):
        for index, fighter in enumerate((self.f1, self.f2)):
            side = 1 if index == 0 else -1
            edge = 0 if index == 0 else W
            self.text(self.tag, fighter.name, fighter.light,
                      (edge + side * 52, 23))
            for i in range(ROUNDS_TO_WIN):
                pos = (edge + side * (120 + i * 28), 22)
                if i < self.score[index]:
                    pygame.draw.circle(self.screen, fighter.color, pos, 10)
                pygame.draw.circle(self.screen, WHITE, pos, 10, 2)
        self.text(self.small, 'ROUND %d' % self.round, WHITE, (W // 2, 22),
                  shadow=False)

    def draw_spark(self, pos):
        points = []
        for i in range(16):
            r = 30 if i % 2 == 0 else 12
            ang = i * math.pi / 8
            points.append((pos[0] + math.cos(ang) * r,
                           pos[1] + math.sin(ang) * r))
        pygame.draw.polygon(self.screen, (255, 230, 80), points)
        pygame.draw.circle(self.screen, WHITE, pos, 9)

    def draw_match(self):
        cx = W // 2
        self.draw_stage()
        # draw the loser first so the winner is never hidden behind them
        for fighter in sorted((self.f1, self.f2),
                              key=lambda f: f.state != 'ko'):
            fighter.draw(self.screen)

        if self.debug:
            for f in (self.f1, self.f2):
                pygame.draw.rect(self.screen, (0, 200, 0), f.hurtbox(), 2)
                if f.hitbox():
                    pygame.draw.rect(self.screen, (255, 0, 0), f.hitbox(), 2)

        self.draw_hud()
        if self.phase == 'intro':
            self.fancy(self.big, 'ROUND %d' % self.round, GOLD, FLAME,
                       (cx, 180), 4)
        elif self.phase == 'fight' and self.timer < 40:
            self.fancy(self.big, 'FIGHT!', GOLD, FLAME, (cx, 180), 4)
        elif self.phase == 'ko':
            if self.hitstop > 0:
                for pos in self.sparks:
                    self.draw_spark(pos)
            if self.banner_winner:
                self.fancy(self.big, self.banner, self.banner_winner.light,
                           self.banner_winner.color, (cx, 180), 4)
            else:
                self.fancy(self.big, self.banner, WHITE, (150, 150, 150),
                           (cx, 180), 4)
        elif self.phase == 'gameover':
            index = 0 if self.score[0] > self.score[1] else 1
            winner = (self.f1, self.f2)[index]
            self.fancy(self.big, winner.name + ' WINS!', winner.light,
                       winner.color, (cx, 165), 4)
            self.text(self.mid, '%d - %d' % tuple(self.score), WHITE,
                      (cx, 240))
            self.text(self.tag, ROSTER[self.pick[index]]['quote'], WHITE,
                      (cx, 476))
            self.text(self.small, 'ATTACK : REMATCH        ESC : TITLE',
                      WHITE, (cx, 508))

    def draw(self):
        if self.phase == 'title':
            self.draw_title()
        elif self.phase == 'select':
            self.draw_select()
        elif self.phase == 'vs':
            self.draw_vs()
        else:
            self.draw_match()

    # ---- main loop ------------------------------------------------------
    def run(self):
        while True:
            attacks = [False, False]
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                if e.type != pygame.KEYDOWN:
                    continue
                if e.key == pygame.K_ESCAPE:
                    if self.phase == 'title':
                        return
                    self.goto('title' if self.phase in ('select', 'gameover')
                              else 'select')
                elif e.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                elif e.key == pygame.K_F1:
                    self.debug = not self.debug
                elif e.key in P1_ATTACK:
                    attacks[0] = True
                elif e.key in P2_ATTACK:
                    attacks[1] = True
                elif self.phase == 'select' and e.key in SWAP_KEYS:
                    self.pick.reverse()

            self.update(attacks)
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)


if __name__ == '__main__':
    Game().run()
    pygame.quit()
    sys.exit()
