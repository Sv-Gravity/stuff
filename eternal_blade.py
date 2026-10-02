#!/usr/bin/env python3
"""
ETERNAL BLADE - a first-person sword duelling game in the spirit of the old
swipe-to-slash mobile classics. One file, no assets, runs on a Raspberry Pi 5.

Run:    python3 eternal_blade.py
Needs:  pygame   (sudo apt install python3-pygame   or   pip install pygame)

How a duel works
    The foe winds up, then swings. Survive the swing, then cut them down
    while they are off balance.
    DODGE   A / D (or tap the corner buttons). Easy, opens the foe briefly.
    BLOCK   hold S or SPACE (or hold the shield button). Safe, but your
            shield only takes a few hits per fight.
    PARRY   swipe TOWARD the incoming blade just before it lands
            (arrow keys, or drag the mouse / touchscreen). Hard, but it
            staggers the foe for a long time.
    SLASH   swipe in any direction while the foe is open. Change direction
            with every cut to build a combo.
    SUPER   Q when the left meter is full: stuns the foe.
    HEAL    E when the right meter is full.

The long game
    Fight up the castle to the Deathless King. He will probably kill you.
    Your descendant then starts again with all your levels, gold and gear.
    Progress is saved to ~/.eternal_blade_save.json.

ENTER confirm, ESC back, F11 fullscreen.
"""

import json
import math
import os
import random
import sys

import pygame

# --------------------------------------------------------------------------
# Tuning (all times are in frames at 60 fps)
# --------------------------------------------------------------------------
W, H = 960, 540
FPS = 60
FLOOR_Y = 486

STRIKE_T = 10           # how long the enemy's swing animation lasts
PARRY_WINDOW = 13       # swipe within this many frames of impact to parry
DODGE_T = 26            # length of a dodge
DODGE_ACTIVE = 19       # ...of which this many frames actually evade
DODGE_CD = 34
SWING_CD = 13           # time between your own slashes
OPEN_DODGE = 85         # how long the foe stays open after each defence
OPEN_BLOCK = 45
OPEN_PARRY = 150
OPEN_SUPER = 190
CHIP = 0.15             # damage fraction when slashing a foe who is on guard

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GOLD = (255, 225, 110)
EMBER = (235, 90, 30)
GREY = (150, 150, 160)
GOOD = (110, 230, 130)
BAD = (240, 70, 60)
PANEL = (22, 22, 30)
EDGE = (90, 90, 112)

# name, bonus, price, colour
WEAPONS = [('Rusted Blade', 0, 0, (150, 140, 130)),
           ("Soldier's Sword", 8, 150, (190, 195, 205)),
           ("Knight's Edge", 18, 450, (215, 225, 240)),
           ('Dragon Fang', 32, 1100, (240, 200, 120)),
           ('Sunsteel', 50, 2400, (255, 235, 150)),
           ('Eternal Blade', 80, 5000, (150, 230, 255))]
SHIELDS = [('Plank Shield', 0, 0, (120, 85, 50)),
           ('Buckler', 1, 120, (150, 150, 160)),
           ('Kite Shield', 2, 400, (60, 90, 170)),
           ('Tower Shield', 4, 1000, (170, 60, 50)),
           ('Aegis', 6, 2200, (230, 200, 100))]
ARMORS = [('Rags', 0, 0, GREY),
          ('Leather', 30, 140, GREY),
          ('Chainmail', 70, 420, GREY),
          ('Plate', 130, 1050, GREY),
          ('Dragonscale', 220, 2300, GREY)]
GEAR = [('weapon', WEAPONS, 'SWORD', 'ATTACK'),
        ('shield_item', SHIELDS, 'SHIELD', 'BLOCKS'),
        ('armor', ARMORS, 'ARMOUR', 'HEALTH')]
STATS = [('health', 'HEALTH'), ('attack', 'ATTACK'), ('shield', 'SHIELD'),
         ('magic', 'MAGIC')]

# hp / dmg / slow are multipliers; heavy = shield points one block costs
FOES = [
    dict(name='HOLLOW GUARD', body=(112, 118, 130), trim=(150, 45, 45),
         eye=(255, 220, 120), size=1.0, bulk=1.0, helm='flat',
         weapon='sword', hp=1.0, dmg=1.0, slow=1.0, combo=2, heavy=1,
         moves=('left', 'right', 'up')),
    dict(name='MARSH BRUTE', body=(74, 108, 72), trim=(96, 74, 44),
         eye=(255, 90, 60), size=1.1, bulk=1.3, helm='hood',
         weapon='club', hp=1.4, dmg=1.3, slow=1.25, combo=1, heavy=2,
         moves=('left', 'right', 'up', 'up')),
    dict(name='ASH KNIGHT', body=(126, 54, 48), trim=(44, 44, 50),
         eye=(255, 170, 60), size=1.0, bulk=1.0, helm='horn',
         weapon='sword', hp=0.9, dmg=1.0, slow=0.82, combo=3, heavy=1,
         moves=('left', 'right', 'up', 'left', 'right', 'bash')),
    dict(name='BONE WARDEN', body=(202, 196, 176), trim=(96, 64, 116),
         eye=(140, 255, 170), size=1.07, bulk=1.15, helm='horn',
         weapon='axe', hp=1.2, dmg=1.2, slow=1.0, combo=2, heavy=2,
         moves=('left', 'right', 'up', 'bash')),
    dict(name='NIGHT CHAMPION', body=(58, 54, 100), trim=(176, 154, 64),
         eye=(120, 200, 255), size=1.1, bulk=1.1, helm='horn',
         weapon='sword', hp=1.2, dmg=1.1, slow=0.86, combo=4, heavy=1,
         moves=('left', 'right', 'up', 'left', 'right', 'bash')),
    dict(name='THE DEATHLESS KING', body=(40, 36, 46), trim=(216, 176, 70),
         eye=(255, 60, 60), size=1.2, bulk=1.2, helm='crown',
         weapon='sword', hp=1.3, dmg=1.0, slow=0.92, combo=4, heavy=2,
         moves=('left', 'right', 'up', 'left', 'right', 'bash')),
]
KING = len(FOES) - 1
# (foe, base level, backdrop)
STAGES = [(0, 1, 0), (1, 2, 0), (2, 3, 1), (3, 5, 1), (4, 7, 2), (KING, 20, 2)]

PALETTES = [
    dict(sky=[(60, 40, 90), (230, 140, 90)], wall=(96, 88, 100),
         pillar=(122, 112, 122), dark=(52, 40, 66), floor=(74, 66, 70),
         line=(52, 46, 52), glow=(255, 190, 90)),          # courtyard at dusk
    dict(sky=[(18, 20, 34), (40, 44, 70)], wall=(66, 70, 88),
         pillar=(88, 92, 112), dark=(24, 26, 40), floor=(52, 54, 68),
         line=(36, 38, 50), glow=(255, 170, 70)),          # great hall
    dict(sky=[(30, 8, 14), (90, 24, 30)], wall=(62, 46, 54),
         pillar=(84, 62, 70), dark=(22, 12, 18), floor=(46, 32, 38),
         line=(28, 18, 24), glow=(255, 90, 50)),           # throne room
]

# Enemy weapon poses: ((grip x, grip y), blade angle in degrees). Coordinates
# are measured from the enemy's feet, y up; 90 degrees is straight up.
REST = ((10, 150), 65)
COCK = {'left': ((-95, 250), 140), 'right': ((95, 250), 40),
        'up': ((0, 285), 90)}
FOLLOW = {'left': ((80, 110), -35), 'right': ((-80, 110), 215),
          'up': ((0, 100), -90)}
STAGGER = ((85, 95), -15)
LEAN = {'left': -22, 'right': 22, 'up': 0, 'bash': 0}
# where the enemy's swing crosses your view
SWEEP = {'left': ((40, 110), (920, 480)), 'right': ((920, 110), (40, 480)),
         'up': ((480, 30), (480, 530))}

SWIPE_KEYS = {pygame.K_LEFT: 'left', pygame.K_RIGHT: 'right',
              pygame.K_UP: 'up', pygame.K_DOWN: 'down'}
BTN_DODGE_L = ((70, H - 70), 52)
BTN_DODGE_R = ((W - 70, H - 70), 52)
BTN_BLOCK = ((W // 2, H - 58), 46)
BTN_SUPER = ((56, 60), 38)
BTN_MAGIC = ((W - 56, 60), 38)

SAVE_PATH = os.environ.get(
    'ETERNAL_BLADE_SAVE',
    os.path.join(os.path.expanduser('~'), '.eternal_blade_save.json'))
NEW_SAVE = dict(bloodline=1, level=1, xp=0, gold=0, points=0, health=0,
                attack=0, shield=0, magic=0, weapon=0, shield_item=0,
                armor=0, stage=0, kills=0, king_defeats=0)


# --------------------------------------------------------------------------
# Save game and character maths
# --------------------------------------------------------------------------
def load_save():
    sv = dict(NEW_SAVE)
    try:
        with open(SAVE_PATH) as f:
            data = json.load(f)
        for key in sv:
            if isinstance(data.get(key), int):
                sv[key] = max(0, data[key])
    except (OSError, ValueError, AttributeError):
        pass
    sv['bloodline'] = max(1, sv['bloodline'])
    sv['level'] = max(1, sv['level'])
    for key, table, _, _ in GEAR:
        sv[key] = min(sv[key], len(table) - 1)
    if sv['stage'] >= len(STAGES):      # quit on the victory screen
        sv['stage'] = 0
        sv['bloodline'] += 1
        sv['king_defeats'] += 1
    return sv


def write_save(sv):
    try:
        with open(SAVE_PATH, 'w') as f:
            json.dump(sv, f)
    except OSError:
        pass                            # no save is better than a crash


def need_xp(level):
    return 10 + 30 * level


def max_hp(sv):
    return 100 + 20 * sv['health'] + ARMORS[sv['armor']][1]


def attack_power(sv):
    return 10 + 3 * sv['attack'] + WEAPONS[sv['weapon']][1]


def shield_points(sv):
    return 3 + sv['shield'] + SHIELDS[sv['shield_item']][1]


def heal_power(sv):
    return 30 + 12 * sv['magic']


def stat_value(sv, index):
    return (max_hp, attack_power, shield_points, heal_power)[index](sv)


def foe_level(sv):
    foe, base, _ = STAGES[sv['stage']]
    if foe == KING:
        return base + 10 * sv['king_defeats']
    # foes grow with each bloodline, but never faster than you do
    return base + min(2 * (sv['bloodline'] - 1), sv['level'] - 1)


# --------------------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------------------
def ip(p):
    return (int(p[0]), int(p[1]))


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shade(color, amount):
    return tuple(min(255, int(c * amount)) for c in color)


def swipe_dir(dx, dy):
    if abs(dx) > abs(dy):
        return 'right' if dx > 0 else 'left'
    return 'down' if dy > 0 else 'up'


def thick(surf, color, a, b, w):
    """A line with real thickness and rounded ends."""
    w = max(2, int(w))
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length * w / 2, dx / length * w / 2
    pygame.draw.polygon(surf, color, [(a[0] + nx, a[1] + ny),
                                      (b[0] + nx, b[1] + ny),
                                      (b[0] - nx, b[1] - ny),
                                      (a[0] - nx, a[1] - ny)])
    pygame.draw.circle(surf, color, ip(a), w // 2)
    pygame.draw.circle(surf, color, ip(b), w // 2)


def streak(surf, color, a, b, w):
    """A slash mark: thin at the start, fat in the middle, sharp at the tip."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length * w / 2, dx / length * w / 2
    mx, my = a[0] + dx * 0.55, a[1] + dy * 0.55
    pygame.draw.polygon(surf, color, [a, (mx + nx, my + ny), b,
                                      (mx - nx, my - ny)])


def vertical_gradient(size, stops):
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
    """Lettering with a vertical gradient, black outline and drop shadow."""
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
    out.blit(edge, (outline * 3, outline * 3))
    out.blit(face, (outline, outline))
    return out


def make_backdrop(pal):
    """A castle wall with arches, pillars, torches and a flagstone floor.
    Wider than the screen so it can slide when you dodge."""
    wd, horizon = W + 300, 340
    s = vertical_gradient((wd, H), pal['sky'])
    d = pygame.draw
    d.rect(s, pal['wall'], (0, 72, wd, horizon - 72))
    for x in range(0, wd, 60):                       # battlements
        d.rect(s, pal['wall'], (x, 46, 34, 28))
    for x in range(90, wd, 210):                     # arches
        d.rect(s, pal['dark'], (x, 160, 96, horizon - 160))
        d.circle(s, pal['dark'], (x + 48, 160), 48)
    for x in range(-15, wd, 210):                    # pillars and torches
        d.rect(s, pal['pillar'], (x, 72, 54, horizon - 72))
        d.rect(s, pal['dark'], (x - 6, 72, 66, 14))
        d.rect(s, pal['dark'], (x - 6, horizon - 16, 66, 16))
        d.rect(s, pal['dark'], (x + 23, 196, 8, 40))
        d.circle(s, pal['glow'], (x + 27, 188), 15)
        d.circle(s, (255, 245, 200), (x + 27, 192), 7)
    d.rect(s, pal['floor'], (0, horizon, wd, H - horizon))
    for i in range(-14, 15):                         # flagstones
        d.line(s, pal['line'], (wd // 2 + i * 40, horizon),
               (wd // 2 + i * 190, H), 2)
    for y in (8, 24, 48, 82, 128, 186):
        d.line(s, pal['line'], (0, horizon + y), (wd, horizon + y), 2)
    d.line(s, pal['dark'], (0, horizon), (wd, horizon), 4)
    return s


def draw_foe(surf, kind, cx, fy, s, grip, ang, lean=0.0, drop=0.0,
             flash=0.0, tint=None, fade=0.0):
    """Draw an armoured enemy standing at (cx, fy), facing the player.
    grip/ang place the two-handed weapon; the arms follow it."""
    d = pygame.draw
    b = kind['bulk']
    body = kind['body']

    def col(c):
        if tint:
            c = lerp_color(c, tint[0], tint[1])
        if flash > 0:
            c = lerp_color(c, WHITE, min(1.0, flash))
        if fade > 0:
            c = lerp_color(c, (20, 16, 24), min(1.0, fade))
        return c

    def P(x, y):
        return (cx + (x + lean * y / 250.0) * s,
                fy - y * (1 - drop / 250.0) * s)

    dark, light, trim = shade(body, 0.6), lerp_color(body, WHITE, 0.3), \
        kind['trim']
    d.ellipse(surf, (18, 14, 20), (int(cx - 115 * s * b), int(fy - 14 * s),
                                   int(230 * s * b), int(32 * s)))
    for sx in (-1, 1):                               # legs
        d.polygon(surf, col(dark), [P(sx * 12 * b, 135), P(sx * 58 * b, 135),
                                    P(sx * 62 * b, 0), P(sx * 20 * b, 0)])
        d.polygon(surf, col(body), [P(sx * 22 * b, 72), P(sx * 60 * b, 72),
                                    P(sx * 68 * b, 0), P(sx * 18 * b, 0)])
    d.polygon(surf, col(trim), [P(-36 * b, 150), P(36 * b, 150),
                                P(42 * b, 62), P(0, 40), P(-42 * b, 62)])
    d.polygon(surf, col(body), [P(-80 * b, 246), P(80 * b, 246),
                                P(56 * b, 135), P(-56 * b, 135)])
    d.polygon(surf, col(light), [P(-52 * b, 238), P(52 * b, 238),
                                 P(34 * b, 162), P(-34 * b, 162)])
    d.polygon(surf, col(dark), [P(-58 * b, 150), P(58 * b, 150),
                                P(56 * b, 135), P(-56 * b, 135)])
    for sx in (-1, 1):                               # shoulder plates
        d.circle(surf, col(light), ip(P(sx * 86 * b, 240)), int(31 * b * s))
        d.circle(surf, col(dark), ip(P(sx * 86 * b, 240)), int(31 * b * s),
                 max(2, int(4 * s)))

    eye_y = 275
    if kind['helm'] == 'hood':
        d.circle(surf, col(trim), ip(P(0, 272)), int(42 * s))
        d.circle(surf, col((26, 22, 26)), ip(P(0, 266)), int(29 * s))
        eye_y = 268
    else:
        d.polygon(surf, col(shade(body, 0.8)),
                  [P(-30, 308), P(30, 308), P(36, 256), P(0, 238),
                   P(-36, 256)])
        d.polygon(surf, col((16, 14, 18)),
                  [P(-25, 283), P(25, 283), P(23, 267), P(-23, 267)])
        d.polygon(surf, col(light), [P(-4, 266), P(4, 266), P(0, 240)])
        if kind['helm'] == 'horn':
            for sx in (-1, 1):
                d.polygon(surf, col((225, 215, 190)),
                          [P(sx * 28, 302), P(sx * 38, 284), P(sx * 80, 318),
                           P(sx * 72, 354)])
        elif kind['helm'] == 'crown':
            d.polygon(surf, col(trim),
                      [P(-32, 304), P(-38, 342), P(-18, 322), P(0, 352),
                       P(18, 322), P(38, 342), P(32, 304)])
    for sx in (-1, 1):
        d.circle(surf, col(kind['eye']), ip(P(sx * 11, eye_y)),
                 max(2, int(5 * s)))

    # weapon, held in both hands
    g = P(*grip)
    a = math.radians(ang)
    ux, uy = math.cos(a), -math.sin(a)

    def Q(along, side):
        return (g[0] + (ux * along - uy * side) * s,
                g[1] + (uy * along + ux * side) * s)

    steel = col((205, 210, 222))
    wood = col((84, 60, 38))
    if kind['weapon'] == 'sword':
        thick(surf, wood, Q(-32, 0), Q(14, 0), 9 * s)
        thick(surf, col(trim), Q(16, -30), Q(16, 30), 9 * s)
        d.polygon(surf, steel, [Q(18, -11), Q(172, -8), Q(204, 0),
                                Q(172, 8), Q(18, 11)])
        d.line(surf, col(WHITE), ip(Q(24, 0)), ip(Q(192, 0)), 2)
    elif kind['weapon'] == 'axe':
        thick(surf, wood, Q(-44, 0), Q(196, 0), 10 * s)
        for side in (-1, 1):
            d.polygon(surf, steel, [Q(132, side * 5), Q(118, side * 62),
                                    Q(160, side * 78), Q(202, side * 58),
                                    Q(188, side * 5)])
    else:
        thick(surf, wood, Q(-34, 0), Q(120, 0), 12 * s)
        thick(surf, col((104, 78, 50)), Q(124, 0), Q(190, 0), 44 * s)
        for along, side in ((130, 26), (160, -28), (186, 24), (205, 0)):
            d.circle(surf, steel, ip(Q(along, side)), max(2, int(8 * s)))
    for sx in (-1, 1):                               # arms reach the grip
        sh = P(sx * 86 * b, 232)
        hand = Q(8 * sx, 0)
        el = ((sh[0] + hand[0]) / 2 + sx * 24 * s,
              (sh[1] + hand[1]) / 2 + 26 * s)
        thick(surf, col(body), sh, el, 26 * s * b)
        thick(surf, col(dark), el, hand, 22 * s * b)
        d.circle(surf, col(light), ip(hand), int(13 * s))


# --------------------------------------------------------------------------
# The two duellists
# --------------------------------------------------------------------------
class Hero:
    """Your stats for one fight (permanent progress lives in the save)."""

    def __init__(self, sv):
        self.max_hp = self.hp = max_hp(sv)
        self.atk = attack_power(sv)
        self.max_shield = self.shield = shield_points(sv)
        self.heal = heal_power(sv)
        self.magic_rate = 100.0 / 1500 * (1 + 0.1 * sv['magic'])
        self.dodge_t = self.dodge_cd = self.swing_cd = 0
        self.dodge_dir = 0
        self.block = False
        self.block_anim = 0.0
        self.super = 0.0
        self.magic = 0.0
        self.combo = 0
        self.last_dir = None
        self.hurt = self.glow = self.shake = 0

    @property
    def dodging(self):
        return self.dodge_t > DODGE_T - DODGE_ACTIVE


class Enemy:
    def __init__(self, kind, level):
        self.kind = kind
        self.level = level
        self.max_hp = self.hp = int((80 + 60 * level) * kind['hp'])
        self.damage = int((8 + 4 * level) * kind['dmg'])
        self.wind = max(30, int((56 - 1.2 * level) * kind['slow']))
        self.combo_max = min(4, kind['combo'] + level // 10)
        self.state = 'idle'   # idle windup strike open stagger stun dead
        self.timer = 80
        self.t_total = 1
        self.queue = []
        self.attack = None
        self.result = 'hit'   # how you handled the last blow
        self.dead_t = 0
        self.grip = list(REST[0])
        self.ang = float(REST[1])
        self.lean = self.drop = self.flash = 0.0
        self.zoom = 1.0
        self.clock = 0

    @property
    def vulnerable(self):
        return self.state in ('open', 'stagger', 'stun')

    def rest(self):
        self.state, self.attack = 'idle', None
        self.timer = random.randint(35, 85)

    def open_up(self, state, frames):
        self.state, self.timer, self.queue = state, frames, []

    def begin_combo(self):
        n = random.randint(1, self.combo_max)
        self.queue = [random.choice(self.kind['moves']) for _ in range(n)]
        self.next_attack(True)

    def next_attack(self, first=False):
        self.attack = self.queue.pop(0)
        self.state = 'windup'
        self.t_total = self.wind if first else max(26, int(self.wind * 0.8))
        if self.attack == 'bash':
            self.t_total = int(self.t_total * 1.2)
        self.timer = self.t_total

    def update(self):
        """Advance one frame. Returns 'impact' when a blow lands."""
        event = None
        if self.state == 'dead':
            self.dead_t += 1
        elif self.state == 'idle':
            self.timer -= 1
            if self.timer <= 0:
                self.begin_combo()
        elif self.state == 'windup':
            self.timer -= 1
            if self.timer <= 0:
                self.state, self.timer = 'strike', STRIKE_T
                event = 'impact'
        elif self.state == 'strike':
            self.timer -= 1
            if self.timer <= 0:
                if self.queue:
                    self.next_attack()
                elif self.result == 'dodge':
                    self.open_up('open', OPEN_DODGE)
                elif self.result == 'block':
                    self.open_up('open', OPEN_BLOCK)
                else:
                    self.rest()
        else:
            self.timer -= 1
            if self.timer <= 0:
                self.rest()
        self.animate()
        return event

    def animate(self):
        """Ease the body and weapon toward the pose for the current state."""
        self.clock += 1
        st, move = self.state, self.attack
        (gx, gy), ang = REST
        gy += math.sin(self.clock * 0.06) * 4
        lean, drop, zoom, rate = 0.0, 0.0, 1.0, 0.15
        if st == 'windup':
            if move == 'bash':
                drop, zoom = 20, 0.9
            else:
                (gx, gy), ang = COCK[move]
                lean = LEAN[move]
                gx += math.sin(self.clock * 1.3) * 2
        elif st == 'strike':
            rate = 0.5
            if move == 'bash':
                zoom = 1.45
            else:
                (gx, gy), ang = FOLLOW[move]
                lean, zoom = -LEAN[move], 1.12
        elif self.vulnerable:
            (gx, gy), ang = STAGGER
            lean, drop = 26 + math.sin(self.clock * 0.15) * 8, 22
        elif st == 'dead':
            (gx, gy), ang = (70, 40), -10
            lean, drop, rate = 50, 150, 0.05
        self.grip[0] += (gx - self.grip[0]) * rate
        self.grip[1] += (gy - self.grip[1]) * rate
        self.ang += (ang - self.ang) * rate
        self.lean += (lean - self.lean) * rate
        self.drop += (drop - self.drop) * rate
        self.zoom += (zoom - self.zoom) * rate
        self.flash = max(0.0, self.flash - 0.12)


class Inp:
    """Everything the player did this frame."""

    def __init__(self):
        self.swipes = []      # (direction, start point, end point)
        self.dodges = []      # -1 left, +1 right
        self.taps = []        # mouse / touch releases
        self.keys = []
        self.super = self.magic = self.confirm = self.back = False
        self.block = False


# --------------------------------------------------------------------------
# Game
# --------------------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption('Eternal Blade')
        flags = getattr(pygame, 'SCALED', 0) | pygame.RESIZABLE
        try:
            self.screen = pygame.display.set_mode((W, H), flags)
        except pygame.error:
            self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()

        self.f_logo = pygame.font.Font(None, 124)
        self.f_big = pygame.font.Font(None, 92)
        self.f_head = pygame.font.Font(None, 56)
        self.f_mid = pygame.font.Font(None, 36)
        self.f_small = pygame.font.Font(None, 26)
        self.f_logo.set_italic(True)

        self.backdrops = [make_backdrop(p) for p in PALETTES]
        self.veil = pygame.Surface((W, H))
        self.menu_bg = pygame.Surface((W, H))
        self.menu_bg.blit(self.backdrops[2], (-150, 0))
        self.veil.fill(BLACK)
        self.veil.set_alpha(150)
        self.menu_bg.blit(self.veil, (0, 0))
        self.cache = {}

        self.save = load_save()
        self.running = True
        self.phase = 'title'  # title camp intro fight victory death ending
        self.timer = 0
        self.frame = 0
        self.drag = None
        self.mouse_block = False
        self.hero = self.enemy = None
        self.bg = 0
        self.reward = (0, 0, 0)
        self.slashes, self.sparks, self.popups = [], [], []

    # ---- flow -----------------------------------------------------------
    def goto(self, phase):
        self.phase, self.timer = phase, 0

    def start_fight(self):
        foe, _, self.bg = STAGES[self.save['stage']]
        self.enemy = Enemy(FOES[foe], foe_level(self.save))
        self.hero = Hero(self.save)
        self.slashes, self.sparks, self.popups = [], [], []
        self.mouse_block = False
        self.drag = None
        self.goto('intro')

    def camp_buttons(self):
        buttons = [(pygame.Rect(262, 204 + i * 52, 44, 36), 'stat%d' % i)
                   for i in range(len(STATS))]
        buttons += [(pygame.Rect(545, 224 + i * 96, 86, 36), 'buy%d' % i)
                    for i in range(len(GEAR))]
        buttons.append((pygame.Rect(690, 432, 210, 52), 'fight'))
        return buttons

    def camp_action(self, name):
        sv = self.save
        if name == 'fight':
            self.start_fight()
            return
        index = int(name[-1])
        if name.startswith('stat') and sv['points'] > 0:
            sv[STATS[index][0]] += 1
            sv['points'] -= 1
        elif name.startswith('buy'):
            key, table = GEAR[index][0], GEAR[index][1]
            nxt = sv[key] + 1
            if nxt < len(table) and sv['gold'] >= table[nxt][2]:
                sv['gold'] -= table[nxt][2]
                sv[key] = nxt
        write_save(sv)

    def update(self, inp):
        self.frame += 1
        self.timer += 1
        getattr(self, 'update_' + self.phase)(inp)

    def update_title(self, inp):
        if inp.back:
            self.running = False
        elif pygame.K_n in inp.keys:
            self.save = dict(NEW_SAVE)
            write_save(self.save)
            self.goto('camp')
        elif self.timer > 15 and (inp.confirm or inp.taps):
            self.goto('camp')

    def update_camp(self, inp):
        if inp.back:
            self.goto('title')
            return
        keymap = {pygame.K_1: 'stat0', pygame.K_2: 'stat1',
                  pygame.K_3: 'stat2', pygame.K_4: 'stat3',
                  pygame.K_z: 'buy0', pygame.K_x: 'buy1', pygame.K_c: 'buy2'}
        actions = [keymap[k] for k in inp.keys if k in keymap]
        for pos in inp.taps:
            actions += [name for rect, name in self.camp_buttons()
                        if rect.collidepoint(pos)]
        if inp.confirm and self.timer > 10:
            actions.append('fight')
        for name in actions:
            self.camp_action(name)
            if self.phase != 'camp':
                break

    def update_intro(self, inp):
        self.enemy.animate()
        if inp.back:
            self.goto('camp')
        elif self.timer >= 110 or (self.timer > 20 and
                                   (inp.confirm or inp.taps)):
            self.goto('fight')

    def update_fight(self, inp):
        h, e = self.hero, self.enemy
        if inp.back:
            self.goto('camp')
            return
        h.dodge_t = max(0, h.dodge_t - 1)
        h.dodge_cd = max(0, h.dodge_cd - 1)
        h.swing_cd = max(0, h.swing_cd - 1)
        h.hurt = max(0, h.hurt - 1)
        h.glow = max(0, h.glow - 1)
        h.shake = max(0, h.shake - 1)
        h.magic = min(100.0, h.magic + h.magic_rate)
        alive = e.state != 'dead'

        h.block = bool(inp.block and h.shield > 0 and h.swing_cd == 0
                       and h.dodge_t == 0)
        for direction in inp.dodges:
            if h.dodge_cd == 0 and h.swing_cd == 0:
                h.dodge_t, h.dodge_cd = DODGE_T, DODGE_CD
                h.dodge_dir, h.block = direction, False
        h.block_anim += ((1.0 if h.block else 0.0) - h.block_anim) * 0.35
        for direction, a, b in inp.swipes:
            if alive and h.swing_cd == 0 and not h.block:
                self.slash(direction, a, b)
        if inp.super and h.super >= 100 and alive:
            h.super = 0.0
            e.open_up('stun', OPEN_SUPER)
            h.glow = 14
            self.popup('SUPER!', W // 2, 210, (140, 210, 255), True)
        if inp.magic and h.magic >= 100 and h.hp > 0:
            h.magic = 0.0
            h.hp = min(h.max_hp, h.hp + h.heal)
            h.glow = 24
            self.popup('+%d' % h.heal, 280, H - 70, GOOD, True)

        was_open = e.vulnerable
        if e.update() == 'impact':
            self.impact()
        if was_open and not e.vulnerable:
            h.combo, h.last_dir = 0, None
        self.update_effects()
        if self.phase == 'fight' and e.state == 'dead' and e.dead_t > 80:
            self.win()

    def slash(self, direction, a, b):
        h, e = self.hero, self.enemy
        h.swing_cd = SWING_CD
        h.dodge_t = 0                   # committing to a swing ends a dodge
        self.slashes.append([a, b, 0])
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if (e.state == 'windup' and e.attack != 'bash'
                and e.timer <= PARRY_WINDOW and direction == e.attack):
            e.open_up('stagger', OPEN_PARRY)
            e.flash = 1.0
            h.super = min(100.0, h.super + 15)
            self.popup('PARRY!', W // 2, 210, GOLD, True)
            self.burst(mid, GOLD, 18)
        elif e.vulnerable:
            h.combo = h.combo + 1 if direction != h.last_dir else 1
            h.last_dir = direction
            mult = 1 + 0.2 * min(h.combo - 1, 5)
            dmg = max(1, int(h.atk * mult * random.uniform(0.9, 1.1)))
            e.hp -= dmg
            e.flash = 1.0
            h.super = min(100.0, h.super + 5)
            self.popup(str(dmg), mid[0] + random.randint(-40, 40),
                       mid[1] - 30, WHITE)
            if h.combo >= 3:
                self.popup('COMBO x%d' % h.combo, W // 2, 150, GOLD)
            self.burst(mid, (255, 120, 90), 8)
            if e.hp <= 0:
                e.hp, e.state, e.queue = 0, 'dead', []
        else:
            e.hp = max(1, e.hp - max(1, int(h.atk * CHIP)))
            self.popup('GUARDED', mid[0], mid[1] - 30, GREY)
            self.burst(mid, WHITE, 5)

    def impact(self):
        """The enemy's blow lands: did you dodge, block, or eat it?"""
        h, e = self.hero, self.enemy
        bash = e.attack == 'bash'
        if h.dodging:
            e.result = 'dodge'
            self.popup('DODGED', W // 2, 260, GOOD)
        elif h.block and not bash:
            e.result = 'block'
            h.shield = max(0, h.shield - e.kind['heavy'])
            h.shake = 6
            self.burst((W // 2, H - 200), WHITE, 10)
            if h.shield == 0:
                self.popup('SHIELD BROKEN!', W // 2, 300, BAD, True)
            else:
                self.popup('BLOCKED', W // 2, 300, (150, 190, 255))
        else:
            e.result = 'hit'
            dmg = int(e.damage * (1.3 if bash else 1.0)
                      * random.uniform(0.9, 1.1))
            h.hp = max(0, h.hp - dmg)
            h.hurt, h.shake, h.combo = 22, 14, 0
            h.super = min(100.0, h.super + 12)
            self.popup('-%d' % dmg, 280, H - 70, BAD, True)
            if h.hp == 0:
                self.goto('death')

    def win(self):
        sv, e = self.save, self.enemy
        king = STAGES[sv['stage']][0] == KING
        xp = (25 + 15 * e.level) * (3 if king else 1)
        gold = (20 + 12 * e.level) * (5 if king else 1)
        sv['xp'] += xp
        sv['gold'] += gold
        sv['kills'] += 1
        levels = 0
        while sv['xp'] >= need_xp(sv['level']):
            sv['xp'] -= need_xp(sv['level'])
            sv['level'] += 1
            sv['points'] += 2
            levels += 1
        self.reward = (xp, gold, levels)
        sv['stage'] += 1
        write_save(sv)
        self.goto('victory')

    def update_victory(self, inp):
        self.update_effects()
        if self.timer > 30 and (inp.confirm or inp.taps):
            if self.save['stage'] >= len(STAGES):
                self.goto('ending')
            else:
                self.goto('camp')

    def update_death(self, inp):
        self.update_effects()
        if self.timer > 70 and (inp.confirm or inp.taps):
            self.save['bloodline'] += 1
            self.save['stage'] = 0
            write_save(self.save)
            self.goto('camp')

    def update_ending(self, inp):
        if self.timer > 60 and (inp.confirm or inp.taps):
            self.save['king_defeats'] += 1
            self.save['bloodline'] += 1
            self.save['stage'] = 0
            write_save(self.save)
            self.goto('camp')

    # ---- little effects -------------------------------------------------
    def popup(self, string, x, y, color, big=False):
        self.popups.append([string, x, y, color, 0, big])

    def burst(self, pos, color, count):
        for _ in range(count):
            ang = random.uniform(0, math.tau)
            speed = random.uniform(3, 10)
            self.sparks.append([pos[0], pos[1], math.cos(ang) * speed,
                                math.sin(ang) * speed - 2, 0, color])

    def update_effects(self):
        for s in self.slashes:
            s[2] += 1
        self.slashes = [s for s in self.slashes if s[2] < 10]
        for p in self.sparks:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.5
            p[4] += 1
        self.sparks = [p for p in self.sparks if p[4] < 22]
        for p in self.popups:
            p[2] -= 1.2
            p[4] += 1
        self.popups = [p for p in self.popups if p[4] < 55]

    # ---- drawing helpers ------------------------------------------------
    def text(self, font, string, color, pos, anchor='center', shadow=True):
        images = []
        for c in ((BLACK, color) if shadow else (color,)):
            key = (id(font), string, c)
            if key not in self.cache:
                if len(self.cache) > 600:
                    self.cache.clear()
                self.cache[key] = font.render(string, True, c)
            images.append(self.cache[key])
        rect = images[-1].get_rect(**{anchor: pos})
        if shadow:
            self.screen.blit(images[0], rect.move(2, 2))
        self.screen.blit(images[-1], rect)

    def fancy(self, font, string, top, bottom, center, outline=3):
        key = ('fancy', id(font), string, top, bottom, outline)
        if key not in self.cache:
            self.cache[key] = fancy_text(font, string, top, bottom, outline)
        img = self.cache[key]
        self.screen.blit(img, img.get_rect(center=center))

    def dim(self, alpha, color=BLACK):
        if alpha > 0:
            self.veil.fill(color)
            self.veil.set_alpha(min(255, int(alpha)))
            self.screen.blit(self.veil, (0, 0))

    def bar(self, rect, frac, color):
        pygame.draw.rect(self.screen, (28, 28, 36), rect)
        fill = pygame.Rect(rect.x, rect.y,
                           int(rect.w * max(0.0, min(1.0, frac))), rect.h)
        if fill.w > 0:
            pygame.draw.rect(self.screen, color, fill)
        pygame.draw.rect(self.screen, WHITE, rect, 2)

    def meter(self, button, frac, color, label):
        (cx, cy), r = button
        s = self.screen
        pygame.draw.circle(s, (24, 24, 32), (cx, cy), r)
        if frac > 0.02:
            steps = max(2, int(40 * frac))
            pts = [(cx, cy)] + [
                (cx + math.sin(i / steps * frac * math.tau) * r,
                 cy - math.cos(i / steps * frac * math.tau) * r)
                for i in range(steps + 1)]
            pygame.draw.polygon(s, color, pts)
        ready = frac >= 1.0
        ring = WHITE if ready and (self.frame // 10) % 2 == 0 else GREY
        pygame.draw.circle(s, ring, (cx, cy), r, 4)
        self.text(self.f_mid, label, WHITE if ready else GREY, (cx, cy))

    def round_button(self, button, label, lit):
        (cx, cy), r = button
        pygame.draw.circle(self.screen, (24, 24, 32), (cx, cy), r)
        pygame.draw.circle(self.screen, WHITE if lit else (80, 80, 92),
                           (cx, cy), r, 4)
        self.text(self.f_mid, label, WHITE if lit else (110, 110, 120),
                  (cx, cy))

    def panel(self, rect, title):
        pygame.draw.rect(self.screen, PANEL, rect)
        pygame.draw.rect(self.screen, EDGE, rect, 2)
        self.text(self.f_mid, title, GOLD, (rect.x + 16, rect.y + 26),
                  'midleft')

    # ---- screens --------------------------------------------------------
    def draw(self):
        if self.phase == 'title':
            self.draw_title()
        elif self.phase == 'camp':
            self.draw_camp()
        elif self.phase == 'ending':
            self.draw_ending()
        else:
            self.draw_scene()

    def draw_title(self):
        s, cx, sv = self.screen, W // 2, self.save
        s.blit(self.menu_bg, (0, 0))
        # a great sword driven point-down behind the logo
        pygame.draw.polygon(s, (120, 130, 150),
                            [(cx - 22, 120), (cx + 22, 120), (cx + 16, 430),
                             (cx, 480), (cx - 16, 430)])
        pygame.draw.polygon(s, (190, 200, 220),
                            [(cx - 5, 120), (cx + 5, 120), (cx, 470)])
        thick(s, (180, 140, 60), (cx - 80, 116), (cx + 80, 116), 16)
        thick(s, (90, 64, 40), (cx, 50), (cx, 110), 14)
        pygame.draw.circle(s, (180, 140, 60), (cx, 44), 14)
        self.fancy(self.f_logo, 'ETERNAL BLADE', (200, 240, 255),
                   (60, 110, 220), (cx, 210), 5)
        self.text(self.f_mid, 'BLOODLINE %d      LEVEL %d' %
                  (sv['bloodline'], sv['level']), GOLD, (cx, 300))
        if (self.frame // 30) % 2 == 0:
            self.text(self.f_mid, 'PRESS ENTER OR TAP TO BEGIN', WHITE,
                      (cx, 372))
        for i, line in enumerate((
                'DODGE  A / D        BLOCK  hold S        SUPER  Q        '
                'HEAL  E',
                'SLASH and PARRY  arrow keys, or swipe with mouse / touch',
                'N  start over (erases your save)        ESC  quit')):
            self.text(self.f_small, line, GREY if i == 2 else WHITE,
                      (cx, 448 + i * 28))

    def draw_camp(self):
        s, sv = self.screen, self.save
        s.blit(self.menu_bg, (0, 0))
        self.fancy(self.f_head, 'BLOODLINE %d' % sv['bloodline'], GOLD,
                   EMBER, (W // 2, 34), 3)

        # the road to the king
        for i in range(len(STAGES)):
            x = 180 + i * 120
            if i < len(STAGES) - 1:
                pygame.draw.line(s, GOOD if i < sv['stage'] else EDGE,
                                 (x, 96), (x + 120, 96), 4)
        for i, (foe, _, _) in enumerate(STAGES):
            x, r = 180 + i * 120, 18 if foe == KING else 13
            here = i == sv['stage']
            col = GOOD if i < sv['stage'] else GOLD if here else (70, 70, 84)
            if here:
                r += int(2 + math.sin(self.frame * 0.12) * 2)
            pygame.draw.circle(s, col, (x, 96), r)
            pygame.draw.circle(s, BLACK, (x, 96), r, 2)
            if foe == KING:
                pygame.draw.polygon(s, GOLD, [(x - 14, 72), (x - 16, 54),
                                              (x - 7, 64), (x, 50),
                                              (x + 7, 64), (x + 16, 54),
                                              (x + 14, 72)])

        buttons = dict((name, rect) for rect, name in self.camp_buttons())

        # warrior
        left = pygame.Rect(30, 140, 290, 360)
        self.panel(left, 'WARRIOR')
        self.text(self.f_mid, 'LV %d' % sv['level'], WHITE,
                  (left.right - 16, left.y + 26), 'midright')
        self.bar(pygame.Rect(46, 182, 258, 10),
                 sv['xp'] / need_xp(sv['level']), (120, 170, 255))
        for i, (_, label) in enumerate(STATS):
            y = 222 + i * 52
            self.text(self.f_small, label, GREY, (46, y), 'midleft')
            self.text(self.f_mid, str(stat_value(sv, i)), WHITE, (250, y),
                      'midright')
            rect = buttons['stat%d' % i]
            can = sv['points'] > 0
            pygame.draw.rect(s, (40, 110, 60) if can else (40, 40, 50), rect)
            pygame.draw.rect(s, WHITE if can else EDGE, rect, 2)
            self.text(self.f_small, '+ %d' % (i + 1),
                      WHITE if can else EDGE, rect.center)
        self.text(self.f_small, 'POINTS TO SPEND: %d' % sv['points'],
                  GOLD if sv['points'] else GREY, (46, 440), 'midleft')
        self.text(self.f_small, 'keys 1-4, or tap +', GREY, (46, 468),
                  'midleft')

        # armoury
        mid = pygame.Rect(335, 140, 310, 360)
        self.panel(mid, 'ARMOURY')
        self.text(self.f_mid, '%d gold' % sv['gold'], GOLD,
                  (mid.right - 16, mid.y + 26), 'midright')
        for i, (key, table, slot, what) in enumerate(GEAR):
            y = 196 + i * 96
            item = table[sv[key]]
            self.text(self.f_small, '%s:  %s' % (slot, item[0]), WHITE,
                      (351, y + 4), 'midleft')
            rect = buttons['buy%d' % i]
            if sv[key] + 1 < len(table):
                nxt = table[sv[key] + 1]
                can = sv['gold'] >= nxt[2]
                self.text(self.f_small, 'next: ' + nxt[0],
                          GOOD if can else GREY, (351, y + 34), 'midleft')
                self.text(self.f_small, '+%d %s' % (nxt[1] - item[1], what),
                          GOOD if can else GREY, (351, y + 58), 'midleft')
                pygame.draw.rect(s, (40, 110, 60) if can else (40, 40, 50),
                                 rect)
                pygame.draw.rect(s, WHITE if can else EDGE, rect, 2)
                self.text(self.f_small, '%s  %d' % ('ZXC'[i], nxt[2]),
                          WHITE if can else EDGE, rect.center)
            else:
                self.text(self.f_small, 'the finest there is', GOLD,
                          (351, y + 34), 'midleft')

        # next foe
        right = pygame.Rect(660, 140, 270, 360)
        self.panel(right, 'NEXT FOE')
        kind = FOES[STAGES[sv['stage']][0]]
        self.text(self.f_small, kind['name'], WHITE, (right.centerx, 194))
        self.text(self.f_small, 'LEVEL %d' % foe_level(sv), BAD,
                  (right.centerx, 218))
        draw_foe(s, kind, right.centerx, 422, 0.44 * kind['size'], REST[0],
                 REST[1])
        rect = buttons['fight']
        pygame.draw.rect(s, (150, 40, 36), rect)
        pygame.draw.rect(s, WHITE, rect, 3)
        self.text(self.f_mid, 'FIGHT  [ENTER]', WHITE, rect.center)
        self.text(self.f_small, 'ESC  title', GREY, (W // 2, 520))

    def draw_scene(self):
        """The duel itself, plus the intro / victory / death overlays."""
        s, h, e = self.screen, self.hero, self.enemy
        kind = e.kind
        view = 0.0
        if h.dodge_t:
            view = (math.sin((1 - h.dodge_t / DODGE_T) * math.pi) * 230
                    * h.dodge_dir)
        sx = random.randint(-h.shake, h.shake) if h.shake else 0
        sy = random.randint(-h.shake, h.shake) if h.shake else 0
        s.blit(self.backdrops[self.bg], (int(-150 - view * 0.5) + sx, sy))

        tint = None
        if e.state == 'windup' and e.attack == 'bash':
            tint = ((255, 40, 30), 0.4 + 0.25 * math.sin(self.frame * 0.5))
        elif e.state == 'stun':
            tint = ((120, 200, 255), 0.35)
        draw_foe(s, kind, W / 2 - view + sx, FLOOR_Y + sy,
                 kind['size'] * e.zoom, e.grip, e.ang, e.lean, e.drop,
                 e.flash, tint, e.dead_t / 70.0)

        if e.state == 'strike':                      # their swing
            k = 1 - e.timer / STRIKE_T
            if e.attack == 'bash':
                pygame.draw.circle(s, (255, 90, 70), (W // 2, 300),
                                   int(120 + k * 480), 14)
            else:
                a, b = SWEEP[e.attack]
                t = min(1.0, k * 1.7)
                tip = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                streak(s, (255, 200, 180), a, tip, 90 * (1 - k) + 12)
                streak(s, WHITE, a, tip, 40 * (1 - k) + 4)
        self.draw_telegraph()

        for a, b, t in self.slashes:                 # your cuts
            k = t / 10.0
            far = (a[0] + (b[0] - a[0]) * 1.5, a[1] + (b[1] - a[1]) * 1.5)
            streak(s, (150, 220, 255), a, far, 34 * (1 - k))
            streak(s, WHITE, a, far, 14 * (1 - k))
        for x, y, vx, vy, t, color in self.sparks:
            pygame.draw.line(s, color, (int(x), int(y)),
                             (int(x - vx * 1.5), int(y - vy * 1.5)), 3)

        self.draw_hero_gear()
        if h.hurt:
            self.dim(h.hurt * 7, (200, 0, 0))
        if h.glow:
            self.dim(h.glow * 5, (120, 255, 170))
        self.draw_hud()
        for string, x, y, color, t, big in self.popups:
            self.text(self.f_head if big else self.f_mid, string, color,
                      (int(x), int(y)))

        cx = W // 2
        if self.phase == 'intro':
            self.dim(110)
            self.fancy(self.f_big, kind['name'], WHITE, (200, 60, 50),
                       (cx, 190), 4)
            self.text(self.f_mid, 'LEVEL %d' % e.level, GOLD, (cx, 256))
            self.text(self.f_small, 'Dodge, block or parry the swing. '
                      'Then strike while the foe is open.', WHITE, (cx, 330))
            self.text(self.f_small, 'To parry, swipe toward the side the '
                      'blade comes from as the arrow turns gold.', WHITE,
                      (cx, 358))
        elif self.phase == 'victory':
            xp, gold, levels = self.reward
            self.dim(min(130, self.timer * 5))
            self.fancy(self.f_big, 'VICTORY', GOLD, EMBER, (cx, 180), 4)
            self.text(self.f_mid, '+%d XP        +%d GOLD' % (xp, gold),
                      WHITE, (cx, 260))
            if levels:
                self.text(self.f_mid, 'LEVEL UP!  +%d POINTS' % (levels * 2),
                          GOOD, (cx, 306))
            if self.timer > 30:
                self.text(self.f_small, 'ENTER or tap to continue', GREY,
                          (cx, 370))
        elif self.phase == 'death':
            self.dim(min(215, self.timer * 4), (40, 0, 0))
            self.fancy(self.f_big, 'YOU HAVE FALLEN', (255, 150, 130),
                       (150, 20, 20), (cx, 180), 4)
            if self.timer > 40:
                self.text(self.f_mid, 'Years pass. Your child takes up '
                          'the blade...', WHITE, (cx, 268))
                self.text(self.f_mid, 'BLOODLINE %d' %
                          (self.save['bloodline'] + 1), GOLD, (cx, 314))
            if self.timer > 70:
                self.text(self.f_small, 'ENTER or tap to continue', GREY,
                          (cx, 380))

    def draw_telegraph(self):
        """Arrow on the side the blow comes from; gold = parry now."""
        e, s = self.enemy, self.screen
        if e.state != 'windup' or self.phase != 'fight':
            return
        if e.attack == 'bash':
            self.fancy(self.f_big, '!', (255, 200, 190), BAD, (W // 2, 120), 4)
            self.text(self.f_small, 'DODGE!', WHITE, (W // 2, 166))
            return
        hot = e.timer <= PARRY_WINDOW
        col, z = (GOLD, 36) if hot else ((230, 60, 50), 24)
        if e.attack == 'left':
            x, y = 110, 250
            pts = [(x - z, y - z), (x + z, y), (x - z, y + z), (x - z // 2, y)]
        elif e.attack == 'right':
            x, y = W - 110, 250
            pts = [(x + z, y - z), (x - z, y), (x + z, y + z), (x + z // 2, y)]
        else:
            x, y = W // 2, 118
            pts = [(x - z, y - z), (x, y + z), (x + z, y - z), (x, y - z // 2)]
        pygame.draw.polygon(s, col, pts)
        pygame.draw.polygon(s, BLACK, pts, 3)

    def draw_hero_gear(self):
        s, h, sv = self.screen, self.hero, self.save
        bob = math.sin(self.frame * 0.05) * 6
        if h.swing_cd == 0:                          # your sword, at rest
            low = bob + 130 * h.block_anim
            blade = WEAPONS[sv['weapon']][3]
            base, tip = (W - 250, H + 50 + low), (W - 372, H - 185 + low)
            dx, dy = tip[0] - base[0], tip[1] - base[1]
            length = math.hypot(dx, dy)
            nx, ny = -dy / length, dx / length
            near = (base[0] + dx * 0.9, base[1] + dy * 0.9)
            pygame.draw.polygon(s, blade, [
                (base[0] + nx * 22, base[1] + ny * 22),
                (near[0] + nx * 13, near[1] + ny * 13), tip,
                (near[0] - nx * 13, near[1] - ny * 13),
                (base[0] - nx * 22, base[1] - ny * 22)])
            pygame.draw.line(s, WHITE, ip(base), ip(tip), 3)
            guard = (base[0] + dx * 0.14, base[1] + dy * 0.14)
            thick(s, (150, 120, 60), (guard[0] + nx * 54, guard[1] + ny * 54),
                  (guard[0] - nx * 54, guard[1] - ny * 54), 16)
        if h.block_anim > 0.03:                      # your shield, raised
            col = SHIELDS[sv['shield_item']][3]
            cx = W // 2 - 30
            top = H - 270 * h.block_anim + 60 * (1 - h.block_anim)
            pts = [(cx - 170, top), (cx + 170, top), (cx + 186, top + 150),
                   (cx, top + 360), (cx - 186, top + 150)]
            pygame.draw.polygon(s, col, pts)
            pygame.draw.polygon(s, shade(col, 0.55), pts, 12)
            pygame.draw.polygon(s, shade(col, 1.3), [
                (cx - 16, top + 6), (cx + 16, top + 6), (cx + 16, top + 330),
                (cx, top + 350), (cx - 16, top + 330)])
            pygame.draw.circle(s, shade(col, 0.55), (cx, int(top + 120)), 34)
            pygame.draw.circle(s, (220, 220, 230), (cx, int(top + 120)), 20)

    def draw_hud(self):
        s, h, e = self.screen, self.hero, self.enemy
        cx = W // 2
        self.text(self.f_small, '%s   LV %d' % (e.kind['name'], e.level),
                  WHITE, (cx, 16))
        self.bar(pygame.Rect(cx - 200, 30, 400, 16), e.hp / e.max_hp,
                 (210, 50, 45))
        if e.vulnerable and self.phase == 'fight':
            total = {'stun': OPEN_SUPER, 'stagger': OPEN_PARRY}.get(
                e.state, OPEN_DODGE)
            self.bar(pygame.Rect(cx - 120, 52, 240, 8), e.timer / total, GOLD)
            if (self.frame // 8) % 2 == 0:
                self.text(self.f_mid, 'STRIKE!', GOLD, (cx, 82))

        self.meter(BTN_SUPER, h.super / 100.0, (90, 160, 255), 'Q')
        self.meter(BTN_MAGIC, h.magic / 100.0, (90, 220, 130), 'E')
        self.round_button(BTN_DODGE_L, '< A', h.dodge_cd == 0)
        self.round_button(BTN_DODGE_R, 'D >', h.dodge_cd == 0)
        self.round_button(BTN_BLOCK, 'S', h.shield > 0)

        self.bar(pygame.Rect(150, H - 46, 250, 18), h.hp / h.max_hp,
                 (70, 200, 90))
        self.text(self.f_small, '%d / %d' % (h.hp, h.max_hp), WHITE,
                  (275, H - 37))
        self.text(self.f_small, 'SHIELD %d / %d' % (h.shield, h.max_shield),
                  (150, 190, 255) if h.shield else BAD, (W // 2 + 70, H - 37),
                  'midleft')

    def draw_ending(self):
        s, cx, sv = self.screen, W // 2, self.save
        s.fill((8, 6, 12))
        self.fancy(self.f_big, 'THE KING IS SLAIN', GOLD, EMBER, (cx, 150), 4)
        self.text(self.f_mid, 'It took %d bloodline%s and %d duels.' %
                  (sv['bloodline'], '' if sv['bloodline'] == 1 else 's',
                   sv['kills']), WHITE, (cx, 250))
        self.text(self.f_mid, '...but the Deathless always return.', GREY,
                  (cx, 300))
        self.text(self.f_small, 'He will be stronger next time. So will you.',
                  GREY, (cx, 340))
        if self.timer > 60:
            self.text(self.f_small, 'ENTER or tap to begin a new bloodline',
                      WHITE, (cx, 430))

    # ---- input and main loop --------------------------------------------
    def key_slash(self, direction):
        """Where a keyboard slash is drawn on screen."""
        j = random.randint(-40, 40)
        line = {'left': ((660, 300 + j), (300, 260 - j)),
                'right': ((300, 300 + j), (660, 260 - j)),
                'up': ((470 + j, 430), (500 - j, 150)),
                'down': ((470 + j, 150), (500 - j, 430))}[direction]
        return (direction,) + line

    def poll(self):
        inp = Inp()
        fighting = self.phase == 'fight'

        def inside(button, pos):
            (bx, by), r = button
            return math.hypot(pos[0] - bx, pos[1] - by) <= r + 8

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                inp.keys.append(k)
                if k == pygame.K_ESCAPE:
                    inp.back = True
                elif k == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    inp.confirm = True
                elif k in SWIPE_KEYS:
                    inp.swipes.append(self.key_slash(SWIPE_KEYS[k]))
                elif k == pygame.K_a:
                    inp.dodges.append(-1)
                elif k == pygame.K_d:
                    inp.dodges.append(1)
                elif k == pygame.K_q:
                    inp.super = True
                elif k == pygame.K_e:
                    inp.magic = True
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if not fighting:
                    continue
                if inside(BTN_DODGE_L, ev.pos):
                    inp.dodges.append(-1)
                elif inside(BTN_DODGE_R, ev.pos):
                    inp.dodges.append(1)
                elif inside(BTN_BLOCK, ev.pos):
                    self.mouse_block = True
                elif inside(BTN_SUPER, ev.pos):
                    inp.super = True
                elif inside(BTN_MAGIC, ev.pos):
                    inp.magic = True
                else:
                    self.drag = ev.pos
            elif ev.type == pygame.MOUSEMOTION:
                # a long enough drag is a slash; keep dragging to chain them
                if fighting and self.drag and ev.buttons[0]:
                    dx = ev.pos[0] - self.drag[0]
                    dy = ev.pos[1] - self.drag[1]
                    if math.hypot(dx, dy) >= 70:
                        inp.swipes.append((swipe_dir(dx, dy), self.drag,
                                           ev.pos))
                        self.drag = ev.pos
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                self.mouse_block = False
                self.drag = None
                if not fighting:
                    inp.taps.append(ev.pos)

        keys = pygame.key.get_pressed()
        inp.block = bool(keys[pygame.K_s] or keys[pygame.K_SPACE]
                         or self.mouse_block)
        return inp

    def run(self):
        while self.running:
            self.update(self.poll())
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)


if __name__ == '__main__':
    Game().run()
    pygame.quit()
    sys.exit()
