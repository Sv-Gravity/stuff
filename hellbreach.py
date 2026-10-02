#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HELLBREACH
==========
A turn-based ASCII roguelike shooter in the style of DoomRL, written for
Raspberry Pi OS (it runs anywhere Python 3 and pygame do).

    sudo apt install python3-pygame      (already on the full Pi OS image)
    python3 hellbreach.py

Options:
    --res 480p|720p|900p|1080p|1440p     pick a resolution
    --fullscreen / --windowed            force a display mode
    --nosound                            start without audio

Settings, your saved game and death reports live in ~/.hellbreach/
Press ? in the game for the full list of keys.
"""

import sys
import os
import math
import random
import pickle
import json
import time
import array
import argparse
import textwrap
from collections import deque

try:
    import pygame
except ImportError:
    print("HELLBREACH needs pygame.  Install it with:\n"
          "    sudo apt install python3-pygame")
    sys.exit(1)

VERSION = "1.0"
SAVE_VERSION = 1

# --------------------------------------------------------------------------
# Layout: a fixed 106 x 30 character grid.  Each cell is twice as tall as it
# is wide, so the grid is 16:9 and scales cleanly to 480p / 720p / 1080p.
# --------------------------------------------------------------------------
GRID_W, GRID_H = 106, 30
MAP_W, MAP_H = 80, 26
MAP_OX, MAP_OY = 0, 1
PANEL_X = 81
PANEL_W = GRID_W - PANEL_X
MAX_DEPTH = 10
INV_MAX = 16
FOV_RADIUS = 10

DATA_DIR = os.path.join(os.path.expanduser("~"), ".hellbreach")
SAVE_PATH = os.path.join(DATA_DIR, "save.dat")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
MORTEM_PATH = os.path.join(DATA_DIR, "mortem.txt")

RESOLUTIONS = [
    ("480p", 854, 480),
    ("720p", 1280, 720),
    ("900p", 1600, 900),
    ("1080p", 1920, 1080),
    ("1440p", 2560, 1440),
]

PAL = {
    'black': (0, 0, 0), 'dgrey': (74, 74, 84), 'grey': (160, 160, 168),
    'white': (240, 240, 240),
    'red': (225, 50, 45), 'dred': (125, 28, 28), 'lred': (255, 115, 100),
    'green': (70, 190, 75), 'dgreen': (35, 105, 45), 'lgreen': (150, 255, 140),
    'blue': (70, 105, 230), 'lblue': (125, 170, 255),
    'cyan': (60, 205, 215), 'lcyan': (165, 245, 255),
    'yellow': (245, 225, 80), 'gold': (255, 196, 50), 'orange': (255, 145, 40),
    'brown': (165, 115, 65), 'dbrown': (100, 72, 46),
    'magenta': (215, 85, 215), 'pink': (255, 150, 190),
}

# (name, tint for monochrome themes or None, background colour)
UI_THEMES = [
    ("Classic", None, (8, 8, 12)),
    ("Amber", (255, 176, 0), (14, 8, 0)),
    ("Green", (70, 255, 120), (0, 10, 3)),
]

DEFAULT_SETTINGS = dict(res=1, fullscreen=False, theme=0, volume=7,
                        effects=True, name="Marine", diff=1)

# --------------------------------------------------------------------------
# World data
# --------------------------------------------------------------------------
T_WALL, T_FLOOR, T_DOOR, T_ODOOR, T_STAIRS, T_ACID, T_LAVA = range(7)
TILE_NAME = ['a wall', 'floor', 'a closed door', 'an open door',
             'stairs leading down', 'acid', 'lava']
DIRS8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

# wall colour, floor colour per level style
STYLES = {
    'base': ('grey', 'dgrey'),
    'depths': ('brown', 'dbrown'),
    'cave': ('dgreen', 'dgrey'),
    'pit': ('red', 'dbrown'),
}

LEVEL_NAMES = ["", "Landing Bay", "Storage Depot", "Reactor Annex",
               "Waste Tunnels", "The Twin Gate", "Sunken Halls",
               "Bone Galleries", "Ember Caverns", "The Maw",
               "The Warden's Pit"]

DIFFS = [
    dict(name="Recruit", mons=0.7, dmg=0.7, score=0.5),
    dict(name="Marine", mons=1.0, dmg=1.0, score=1.0),
    dict(name="Veteran", mons=1.3, dmg=1.25, score=1.5),
    dict(name="Nightmare", mons=1.7, dmg=1.5, score=2.5),
]

AMMO_CAP = {'bullet': 150, 'shell': 50, 'rocket': 15, 'cell': 120}
AMMO_NAME = {'bullet': 'Bullets', 'shell': 'Shells', 'rocket': 'Rockets',
             'cell': 'Cells'}
AMMO_ORDER = ['bullet', 'shell', 'rocket', 'cell']

FISTS = dict(name='fists', melee=True, dmg=(1, 3, 0), fire=100, snd='melee')

ITEMS = {
    # --- melee weapons
    'knife': dict(type='weapon', name='combat knife', ch='\\', col='white',
                  melee=True, dmg=(2, 5, 0), fire=90, slot=1, snd='melee'),
    'chainsaw': dict(type='weapon', name='chainsaw', ch='\\', col='lred',
                     melee=True, dmg=(4, 6, 0), fire=100, slot=1, snd='saw'),
    # --- guns
    'pistol': dict(type='weapon', name='pistol', ch='}', col='grey',
                   ammo='bullet', mag=6, per=1, dmg=(2, 4, 0), shots=1,
                   acc=10, fire=100, reload=120, kind='bullet', slot=2,
                   snd='pistol'),
    'shotgun': dict(type='weapon', name='shotgun', ch='}', col='brown',
                    ammo='shell', mag=1, per=1, dmg=(8, 3, 0), shots=1,
                    acc=0, fire=100, reload=100, kind='shot', spread=0.24,
                    range=10, slot=3, snd='shotgun'),
    'cshotgun': dict(type='weapon', name='combat shotgun', ch='}',
                     col='lblue', ammo='shell', mag=5, per=1, dmg=(7, 3, 0),
                     shots=1, acc=0, fire=100, reload=160, kind='shot',
                     spread=0.22, range=10, slot=3, snd='shotgun'),
    'dshotgun': dict(type='weapon', name='double shotgun', ch='}',
                     col='orange', ammo='shell', mag=2, per=2,
                     dmg=(15, 3, 0), shots=1, acc=0, fire=100, reload=180,
                     kind='shot', spread=0.42, range=8, slot=3,
                     snd='shotgun'),
    'chaingun': dict(type='weapon', name='chaingun', ch='}', col='yellow',
                     ammo='bullet', mag=40, per=1, dmg=(1, 6, 0), shots=4,
                     acc=0, fire=100, reload=200, kind='bullet', slot=4,
                     snd='chaingun'),
    'rocket': dict(type='weapon', name='rocket launcher', ch='}', col='lred',
                   ammo='rocket', mag=1, per=1, dmg=(6, 6, 0), shots=1,
                   acc=10, fire=100, reload=140, kind='rocket', radius=2,
                   slot=5, snd='rocket'),
    'plasma': dict(type='weapon', name='plasma rifle', ch='}', col='cyan',
                   ammo='cell', mag=40, per=1, dmg=(1, 7, 0), shots=5,
                   acc=5, fire=100, reload=200, kind='plasma', slot=6,
                   snd='plasma'),
    'bfg': dict(type='weapon', name='annihilator', ch='}', col='lgreen',
                ammo='cell', mag=100, per=40, dmg=(10, 6, 0), shots=1,
                acc=20, fire=150, reload=220, kind='bfg', radius=5, slot=7,
                snd='bfg'),
    # --- ammunition (picked up automatically)
    'bullets': dict(type='ammo', name='bullets', ch='|', col='yellow',
                    ammo='bullet', amount=24),
    'shells': dict(type='ammo', name='shotgun shells', ch='|', col='orange',
                   ammo='shell', amount=8),
    'rockets': dict(type='ammo', name='rockets', ch='|', col='lred',
                    ammo='rocket', amount=3),
    'cells': dict(type='ammo', name='power cells', ch='|', col='cyan',
                  ammo='cell', amount=20),
    # --- carried consumables
    'smed': dict(type='use', name='small medkit', ch='!', col='lred',
                 desc='Restores 25 health.'),
    'lmed': dict(type='use', name='large medkit', ch='!', col='pink',
                 desc='Restores full health and cures tiredness.'),
    'phase': dict(type='use', name='phase unit', ch='?', col='lblue',
                  desc='Teleports you somewhere else on the floor.'),
    'scan': dict(type='use', name='tactical scanner', ch='?', col='lgreen',
                 desc='Maps the whole floor.'),
    # --- orbs: used the moment you step on them
    'vital': dict(type='orb', name='vital orb', ch='^', col='lblue'),
    'surge': dict(type='orb', name='surge orb', ch='^', col='cyan'),
    'rage': dict(type='orb', name='rage orb', ch='^', col='red'),
    'aegis': dict(type='orb', name='aegis orb', ch='^', col='white'),
    'shard': dict(type='orb', name='armor shard', ch='^', col='green'),
    'pack': dict(type='orb', name='backpack', ch='^', col='brown'),
    # --- armor
    'armor1': dict(type='armor', name='flak vest', ch='[', col='green',
                   prot=1),
    'armor2': dict(type='armor', name='combat armor', ch='[', col='lblue',
                   prot=2),
    'armor3': dict(type='armor', name='assault armor', ch='[', col='lred',
                   prot=4),
    # --- weapon mods
    'modP': dict(type='mod', name='power mod', ch='"', col='lred', mod='P',
                 desc='Fit to your weapon: more damage.'),
    'modA': dict(type='mod', name='agility mod', ch='"', col='cyan', mod='A',
                 desc='Fit to your weapon: +15% accuracy.'),
    'modB': dict(type='mod', name='bulk mod', ch='"', col='lblue', mod='B',
                 desc='Fit to your weapon: bigger magazine.'),
    'modT': dict(type='mod', name='tech mod', ch='"', col='yellow', mod='T',
                 desc='Fit to your weapon: faster fire and reload.'),
}

# kind, first floor, last floor, weight
WEAPON_TABLE = [
    ('shotgun', 1, 5, 10), ('knife', 1, 4, 4), ('cshotgun', 3, 9, 4),
    ('chaingun', 3, 8, 7), ('dshotgun', 4, 10, 5), ('chainsaw', 3, 10, 3),
    ('rocket', 4, 10, 5), ('plasma', 6, 10, 5), ('bfg', 8, 10, 2),
]

MONS = {
    'husk': dict(name='husk trooper', ch='h', col='grey', hp=10, speed=100,
                 cost=1.0, xp=8, depth=(1, 6), w=10, group=(1, 3),
                 ranged=dict(kind='bullet', dmg=(2, 4, 0), acc=55, range=9,
                             chance=0.55, snd='pistol'),
                 drop=[('bullets', 0.5), ('pistol', 0.08)]),
    'sarge': dict(name='husk sergeant', ch='s', col='lred', hp=14, speed=100,
                  cost=1.5, xp=14, depth=(2, 7), w=7,
                  ranged=dict(kind='shot', dmg=(6, 3, 0), range=7,
                              spread=0.24, chance=0.5, snd='shotgun'),
                  drop=[('shells', 0.55), ('shotgun', 0.25)]),
    'gunner': dict(name='husk gunner', ch='g', col='lblue', hp=20, speed=100,
                   cost=2.5, xp=26, depth=(4, 10), w=6,
                   ranged=dict(kind='bullet', dmg=(1, 5, 0), shots=3, acc=56,
                               range=9, chance=0.6, snd='chaingun'),
                   drop=[('bullets', 0.7), ('chaingun', 0.2)]),
    'fiend': dict(name='cinder fiend', ch='i', col='orange', hp=14,
                  speed=100, cost=1.5, xp=14, depth=(1, 8), w=10,
                  group=(1, 2), melee=(2, 3, 0),
                  ranged=dict(kind='fire', dmg=(2, 5, 0), acc=66, range=8,
                              chance=0.5, snd='fire')),
    'hound': dict(name='gorehound', ch='d', col='pink', hp=28, speed=125,
                  cost=2.0, xp=22, depth=(2, 9), w=8, melee=(3, 4, 0)),
    'ember': dict(name='ember skull', ch='e', col='yellow', hp=8, speed=150,
                  cost=1.2, xp=12, depth=(3, 10), w=6, group=(2, 4),
                  fly=True, melee=(1, 6, 1)),
    'bloat': dict(name='bloat', ch='O', col='red', hp=40, speed=90, cost=4.0,
                  xp=45, depth=(4, 10), w=6, fly=True, melee=(2, 6, 0),
                  ranged=dict(kind='plasma', dmg=(3, 5, 0), acc=70, range=9,
                              chance=0.55, snd='fire')),
    'archer': dict(name='bone archer', ch='r', col='white', hp=30, speed=115,
                   cost=4.5, xp=60, depth=(6, 10), w=4, melee=(2, 5, 0),
                   ranged=dict(kind='rocket', dmg=(3, 5, 0), radius=1,
                               acc=66, range=9, chance=0.45, snd='rocket'),
                   drop=[('rockets', 0.3)]),
    'brute': dict(name='horned brute', ch='b', col='brown', hp=50, speed=100,
                  cost=5.0, xp=65, depth=(5, 10), w=5, armor=1,
                  melee=(3, 6, 0),
                  ranged=dict(kind='acid', dmg=(3, 6, 0), acc=70, range=8,
                              chance=0.5, snd='fire')),
    'scuttler': dict(name='scuttler', ch='A', col='gold', hp=45, speed=110,
                     cost=5.0, xp=70, depth=(6, 10), w=4, armor=1,
                     ranged=dict(kind='plasma', dmg=(1, 6, 0), shots=3,
                                 acc=60, range=9, chance=0.6, snd='plasma'),
                     drop=[('cells', 0.6)]),
    'lord': dict(name='pit lord', ch='L', col='lred', hp=85, speed=100,
                 cost=8.0, xp=120, depth=(7, 10), w=3, armor=2,
                 melee=(4, 6, 0),
                 ranged=dict(kind='acid', dmg=(4, 6, 0), radius=1, acc=74,
                             range=9, chance=0.55, snd='fire')),
    'warden': dict(name='the Warden', ch='W', col='magenta', hp=320,
                   speed=110, cost=99, xp=600, depth=(99, 99), w=0, armor=2,
                   boss=True, melee=(5, 6, 0),
                   ranged=dict(kind='rocket', dmg=(5, 6, 0), radius=2,
                               acc=76, range=14, chance=0.6, snd='rocket')),
}

# projectile kind -> (glyph, colour, milliseconds per cell)
PROJ = {
    'bullet': ('-', 'yellow', 9),
    'fire': ('*', 'orange', 16),
    'plasma': ('*', 'lcyan', 13),
    'acid': ('*', 'lgreen', 16),
    'rocket': ('*', 'lred', 15),
    'bfg': ('O', 'lgreen', 18),
}
BOOM_COL = {'rocket': 'orange', 'acid': 'lgreen', 'bfg': 'lgreen',
            'barrel': 'orange'}

BARRELS = {
    'fuel': ('fuel barrel', 'orange'),
    'acid': ('acid barrel', 'green'),
    'napalm': ('napalm barrel', 'red'),
}

# key, name, max rank, description, requirements
TRAITS = [
    ('iron', 'Iron Hide', 5, '+10 maximum health', {}),
    ('quick', 'Quick Hands', 3, 'Firing takes 15% less time', {}),
    ('sprint', 'Sprinter', 3, 'Moving takes 15% less time, +5% dodge', {}),
    ('thick', 'Thick Skin', 3, 'Every hit you take does 1 less damage', {}),
    ('sling', 'Gunslinger', 3, 'Pistols: +2 damage and fire 20% faster', {}),
    ('loader', 'Speed Loader', 3, 'Reloading takes 25% less time', {}),
    ('eye', 'Dead Eye', 3, '+10% accuracy with every gun', {}),
    ('brute', 'Bruiser', 3, '+3 melee damage, +5% melee accuracy', {}),
    ('sense', 'Sixth Sense', 2, '1: sense items and stairs  2: monsters', {}),
    ('juggle', 'Juggler', 1, 'Swapping weapons takes no time', {}),
    ('medic', 'Field Medic', 1, 'Medkits heal 50% more', {}),
    ('evade', 'Evasion', 2, '+15% chance to dodge projectiles',
     {'sprint': 2}),
    ('rage', 'Blood Rage', 1, 'Melee kills can send you berserk',
     {'brute': 2}),
    ('shell', 'Shell Shock', 1, 'Shotguns reload themselves as you move',
     {'loader': 2}),
    ('burst', 'Trigger Discipline', 2, '+1 shot in every burst',
     {'quick': 2}),
    ('tinker', 'Tinkerer', 2, '+1 mod slot on every weapon', {'eye': 1}),
]
TRAIT_BY_KEY = {t[0]: t for t in TRAITS}


def xp_need(level):
    """Total experience needed to reach `level`."""
    return (level - 1) * (20 * level + 10)


def roll(rng, dice):
    n, sides, bonus = dice
    return sum(rng.randint(1, sides) for _ in range(n)) + bonus


def dice_str(dice, shots=1):
    n, sides, bonus = dice
    s = "%dd%d" % (n, sides)
    if bonus:
        s += "+%d" % bonus
    if shots > 1:
        s += "x%d" % shots
    return s


def sign(v):
    return (v > 0) - (v < 0)


def cheb(x0, y0, x1, y1):
    return max(abs(x1 - x0), abs(y1 - y0))


def line(x0, y0, x1, y1):
    """Bresenham line from (x0,y0) to (x1,y1), excluding the start."""
    pts = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x1 > x0 else -1
    sy = 1 if y1 > y0 else -1
    err = dx - dy
    x, y = x0, y0
    while (x, y) != (x1, y1):
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
        pts.append((x, y))
    return pts


def ray(x0, y0, x1, y1, length):
    """A line through (x1,y1) that keeps going for roughly `length` cells."""
    dx, dy = x1 - x0, y1 - y0
    m = max(abs(dx), abs(dy))
    if m == 0:
        return []
    k = max(1, -(-length // m))
    return line(x0, y0, x0 + dx * k, y0 + dy * k)[:max(length, m)]


def a_an(name):
    if name.startswith('the '):
        return name
    return ('an ' if name[0] in 'aeiou' else 'a ') + name


# --------------------------------------------------------------------------
# Sound: every effect is synthesized at start-up, so there are no asset files
# --------------------------------------------------------------------------
class Sfx:
    def __init__(self, enabled=True):
        self.ok = False
        self.volume = 0.7
        self.sounds = {}
        if not enabled:
            return
        try:
            try:
                pygame.mixer.init(22050, -16, 1, 512, allowedchanges=0)
            except TypeError:
                pygame.mixer.init(22050, -16, 1, 512)
            freq, fmt, chans = pygame.mixer.get_init()
            if fmt != -16:
                raise RuntimeError("unsupported audio format")
            self.rate, self.chans = freq, chans
            pygame.mixer.set_num_channels(12)
            self.build()
            self.ok = True
        except Exception:
            self.ok = False

    def make(self, dur, fn, vol=1.0):
        n = int(self.rate * dur)
        buf = array.array('h')
        chans = self.chans
        rate = float(self.rate)
        for i in range(n):
            v = fn(i / rate, i / float(n)) * vol
            v = -1.0 if v < -1.0 else (1.0 if v > 1.0 else v)
            s = int(v * 30000)
            for _ in range(chans):
                buf.append(s)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def build(self):
        rate = float(self.rate)
        rnd = random.Random(7)

        def noise(lp, decay, thump=0.0, thump_hz=90.0):
            st = [0.0]

            def f(t, u):
                st[0] += lp * (rnd.uniform(-1, 1) - st[0])
                v = st[0] * (1.6 / (lp ** 0.5)) * math.exp(-decay * t)
                if thump:
                    v += thump * math.sin(2 * math.pi * thump_hz * t) \
                        * math.exp(-decay * 0.8 * t)
                return v * (1.0 - u) ** 0.5
            return f

        def sweep(f0, f1, shape='sine', decay=0.0, vib=0.0, vib_hz=0.0):
            ph = [0.0]

            def f(t, u):
                hz = f0 + (f1 - f0) * u
                if vib:
                    hz += vib * math.sin(2 * math.pi * vib_hz * t)
                ph[0] += 2 * math.pi * hz / rate
                if shape == 'sine':
                    v = math.sin(ph[0])
                elif shape == 'square':
                    v = 0.6 if math.sin(ph[0]) > 0 else -0.6
                else:
                    v = ((ph[0] / (2 * math.pi)) % 1.0) * 1.4 - 0.7
                return v * math.exp(-decay * t) * min(1.0, (1.0 - u) * 6)
            return f

        def notes(seq, step, shape='sine'):
            ph = [0.0]

            def f(t, u):
                i = min(len(seq) - 1, int(t / step))
                ph[0] += 2 * math.pi * seq[i] / rate
                v = math.sin(ph[0]) if shape == 'sine' else \
                    (0.5 if math.sin(ph[0]) > 0 else -0.5)
                local = (t - i * step) / step
                return v * (1.0 - 0.6 * local) * min(1.0, (1.0 - u) * 8)
            return f

        def clicks(times, lp=0.6):
            n = noise(lp, 0.0)

            def f(t, u):
                for c in times:
                    if c <= t < c + 0.02:
                        return n(0.0, 0.0) * (1.0 - (t - c) / 0.02)
                return 0.0
            return f

        def mix(a, b, wa=0.6, wb=0.6):
            return lambda t, u: a(t, u) * wa + b(t, u) * wb

        mk, s = self.make, self.sounds
        s['pistol'] = mk(0.18, noise(0.55, 28, 0.5, 170), 0.8)
        s['shotgun'] = mk(0.40, noise(0.30, 11, 0.7, 85), 0.95)
        s['chaingun'] = mk(0.09, noise(0.65, 40, 0.3, 200), 0.7)
        s['plasma'] = mk(0.14, sweep(1500, 320, 'sine', 6), 0.5)
        s['rocket'] = mk(0.35, mix(noise(0.18, 3), sweep(120, 420, 'saw')),
                         0.6)
        s['fire'] = mk(0.25, mix(noise(0.22, 8), sweep(420, 140, 'sine', 4)),
                       0.6)
        s['boom'] = mk(0.80, noise(0.10, 5, 0.9, 52), 1.0)
        s['bfg'] = mk(0.70, mix(sweep(90, 950, 'saw'), noise(0.3, 2)), 0.6)
        s['hit'] = mk(0.06, noise(0.45, 40), 0.5)
        s['hurt'] = mk(0.22, sweep(170, 85, 'square', 5), 0.6)
        s['die'] = mk(0.35, mix(sweep(300, 55, 'saw', 3), noise(0.2, 9)),
                      0.6)
        s['melee'] = mk(0.10, noise(0.14, 22, 0.6, 110), 0.8)
        s['saw'] = mk(0.25, mix(sweep(95, 80, 'saw'), noise(0.5, 4)), 0.6)
        s['pickup'] = mk(0.12, notes([660, 880], 0.06), 0.4)
        s['ammo'] = mk(0.08, notes([520, 620], 0.04, 'square'), 0.3)
        s['power'] = mk(0.36, notes([440, 554, 659, 880], 0.09), 0.45)
        s['door'] = mk(0.20, noise(0.07, 9, 0.3, 105), 0.8)
        s['reload'] = mk(0.20, clicks([0.0, 0.13]), 0.5)
        s['empty'] = mk(0.04, clicks([0.0], 0.9), 0.4)
        s['levelup'] = mk(0.45, notes([523, 659, 784, 1047, 1319], 0.09),
                          0.5)
        s['stairs'] = mk(0.50, sweep(520, 110, 'sine', 2), 0.45)
        s['lever'] = mk(0.22, mix(clicks([0.0]), sweep(300, 300, 'square',
                                                       9)), 0.5)
        s['tele'] = mk(0.40, sweep(500, 900, 'sine', 2, 260, 34), 0.45)
        s['alert'] = mk(0.30, sweep(130, 95, 'saw', 2, 14, 22), 0.5)
        s['blip'] = mk(0.04, sweep(880, 880, 'square'), 0.2)
        s['win'] = mk(0.90, notes([523, 523, 659, 784, 659, 784, 1047, 1047,
                                   1047], 0.10), 0.5)

    def play(self, name, vol=1.0):
        if not self.ok or self.volume <= 0:
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        try:
            snd.set_volume(max(0.0, min(1.0, vol * self.volume)))
            snd.play()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------
class Item:
    def __init__(self, kind, amount=None):
        self.kind = kind
        d = ITEMS[kind]
        self.amount = amount if amount is not None else d.get('amount', 1)
        self.loaded = d.get('mag', 0)
        self.mods = []
        self.dur = 100

    @property
    def d(self):
        return ITEMS[self.kind]


class Mon:
    def __init__(self, kind, x, y, hpmul=1.0):
        self.kind = kind
        self.x, self.y = x, y
        self.maxhp = max(1, int(MONS[kind]['hp'] * hpmul))
        self.hp = self.maxhp
        self.energy = 0
        self.awake = False

    @property
    def d(self):
        return MONS[self.kind]

    @property
    def name(self):
        return MONS[self.kind]['name']

    def the(self, cap=False):
        n = self.name
        if not n.startswith('the '):
            n = 'the ' + n
        return n[0].upper() + n[1:] if cap else n

    def state(self):
        r = self.hp / float(self.maxhp)
        if r >= 1.0:
            return 'unhurt'
        if r > 0.6:
            return 'scratched'
        if r > 0.3:
            return 'wounded'
        return 'dying'


class Player:
    def __init__(self, name):
        self.name = name
        self.x = self.y = 0
        self.hp = self.maxhp = 50
        self.level = 1
        self.xp = 0
        self.inv = []
        self.weapon = None
        self.armor = None
        self.prev_kind = None
        self.ammo = {'bullet': 0, 'shell': 0, 'rocket': 0, 'cell': 0}
        self.traits = {}
        self.berserk = 0
        self.invuln = 0
        self.running = 0
        self.tired = False
        self.backpack = False
        self.kills = {}

    def tr(self, key):
        return self.traits.get(key, 0)


class Level:
    def __init__(self, depth):
        self.depth = depth
        self.t = [[T_WALL] * MAP_W for _ in range(MAP_H)]
        self.seen = [[False] * MAP_W for _ in range(MAP_H)]
        self.items = {}
        self.mons = []
        self.barrels = {}
        self.levers = {}
        self.decor = {}
        self.blood = set()
        self.visible = set()
        self.name = LEVEL_NAMES[depth] if depth < len(LEVEL_NAMES) else '?'
        self.style = 'base'
        self.start = (1, 1)
        self.stairs = None
        self.vault = None

    def inb(self, x, y):
        return 0 <= x < MAP_W and 0 <= y < MAP_H

    def solid(self, x, y):
        t = self.t[y][x]
        return t == T_WALL or t == T_DOOR

    def mon_at(self, x, y):
        for m in self.mons:
            if m.x == x and m.y == y:
                return m
        return None

    def add_item(self, x, y, it):
        self.items.setdefault((x, y), []).append(it)


# --------------------------------------------------------------------------
# Level generation.  Every floor is built from "<seed>:<depth>", so the same
# seed always gives the same dungeon.
# --------------------------------------------------------------------------
def flood(lv, start, hazard_ok=True):
    """Breadth-first distances from start over walkable tiles."""
    dist = {start: 0}
    q = deque([start])
    t = lv.t
    while q:
        x, y = q.popleft()
        d = dist[(x, y)] + 1
        for dx, dy in DIRS8:
            nx, ny = x + dx, y + dy
            if (nx, ny) in dist:
                continue
            tt = t[ny][nx]
            if tt == T_WALL:
                continue
            if not hazard_ok and (tt == T_ACID or tt == T_LAVA):
                continue
            dist[(nx, ny)] = d
            q.append((nx, ny))
    return dist


def open_around(lv, x, y):
    return lv.t[y][x] == T_FLOOR and all(
        lv.t[y + dy][x + dx] == T_FLOOR for dx, dy in DIRS8)


def barrel_kind(rng, depth):
    r = rng.random()
    if r < 0.6:
        return 'fuel'
    if r < 0.85 or depth < 4:
        return 'acid'
    return 'napalm'


def build_base(lv, rng):
    """DoomRL-style floor plan: one big hall cut into rooms by walls."""
    W, H = MAP_W, MAP_H
    t = lv.t
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            t[y][x] = T_FLOOR
    rooms, doors, doorset = [], [], set()

    def add_door(x, y):
        doorset.add((x, y))
        doors.append((x, y))
        t[y][x] = T_DOOR if rng.random() < 0.8 else T_FLOOR

    def split(x1, y1, x2, y2, depth):
        w, h = x2 - x1 + 1, y2 - y1 + 1
        can_v, can_h = w >= 11, h >= 7
        if not (can_v or can_h) or (depth >= 3 and rng.random() < 0.3):
            rooms.append((x1, y1, x2, y2))
            return
        if can_v and can_h:
            vert = rng.random() < (0.75 if w > h * 2 else 0.3)
        else:
            vert = can_v
        for _ in range(10):
            if vert:
                wx = rng.randint(x1 + 5, x2 - 5)
                if (wx, y1 - 1) in doorset or (wx, y2 + 1) in doorset:
                    continue
                for y in range(y1, y2 + 1):
                    t[y][wx] = T_WALL
                dy = rng.randint(y1, y2)
                add_door(wx, dy)
                if h >= 8 and rng.random() < 0.4:
                    dy2 = rng.randint(y1, y2)
                    if abs(dy2 - dy) >= 3:
                        add_door(wx, dy2)
                split(x1, y1, wx - 1, y2, depth + 1)
                split(wx + 1, y1, x2, y2, depth + 1)
                return
            else:
                wy = rng.randint(y1 + 3, y2 - 3)
                if (x1 - 1, wy) in doorset or (x2 + 1, wy) in doorset:
                    continue
                for x in range(x1, x2 + 1):
                    t[wy][x] = T_WALL
                dx = rng.randint(x1, x2)
                add_door(dx, wy)
                if w >= 14 and rng.random() < 0.4:
                    dx2 = rng.randint(x1, x2)
                    if abs(dx2 - dx) >= 4:
                        add_door(dx2, wy)
                split(x1, y1, x2, wy - 1, depth + 1)
                split(x1, wy + 1, x2, y2, depth + 1)
                return
        rooms.append((x1, y1, x2, y2))

    split(1, 1, W - 2, H - 2, 0)
    if len(rooms) < 4:
        return None

    start_room = rooms[rng.randrange(len(rooms))]
    sx = rng.randint(start_room[0], start_room[2])
    sy = rng.randint(start_room[1], start_room[3])

    for r in rooms:
        if r is start_room:
            continue
        x1, y1, x2, y2 = r
        w, h = x2 - x1 + 1, y2 - y1 + 1
        k = rng.random()
        if k < 0.16 and w >= 7 and h >= 5:
            fluid = T_LAVA if (lv.depth >= 6 and rng.random() < 0.6) \
                else T_ACID
            for y in range(y1 + 1, y2):
                for x in range(x1 + 2, x2 - 1):
                    t[y][x] = fluid
        elif k < 0.32 and w >= 7 and h >= 5:
            for y in range(y1 + 1, y2, 2):
                for x in range(x1 + 2, x2 - 1, 3):
                    t[y][x] = T_WALL
        elif k < 0.62:
            for _ in range(rng.randint(1, 4)):
                bx, by = rng.randint(x1, x2), rng.randint(y1, y2)
                if open_around(lv, bx, by) and (bx, by) not in lv.barrels:
                    lv.barrels[(bx, by)] = barrel_kind(rng, lv.depth)

    # a sealed vault that only a lever can open
    if rng.random() < 0.45:
        cands = [r for r in rooms if r is not start_room and
                 (r[2] - r[0] + 1) * (r[3] - r[1] + 1) <= 70]
        rng.shuffle(cands)
        for r in cands[:4]:
            x1, y1, x2, y2 = r
            rd = [(x, y) for (x, y) in doors
                  if x1 - 1 <= x <= x2 + 1 and y1 - 1 <= y <= y2 + 1]
            if not rd:
                continue
            saved = [(x, y, t[y][x]) for x, y in rd]
            for x, y in rd:
                t[y][x] = T_WALL
            need = 0
            for y in range(1, H - 1):
                for x in range(1, W - 1):
                    if t[y][x] != T_WALL and not (x1 <= x <= x2 and
                                                  y1 <= y <= y2):
                        need += 1
            if len(flood(lv, (sx, sy))) == need:
                lv.vault = dict(rect=r, door=rd[0])
                break
            for x, y, old in saved:
                t[y][x] = old
    return (sx, sy)


def build_cave(lv, rng):
    """Cellular-automaton cavern with pools of acid or lava."""
    W, H = MAP_W, MAP_H
    g = [[True] * W for _ in range(H)]
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            g[y][x] = rng.random() < 0.43
    for _ in range(4):
        ng = [[True] * W for _ in range(H)]
        for y in range(1, H - 1):
            for x in range(1, W - 1):
                n = 0
                for dy in (-1, 0, 1):
                    row = g[y + dy]
                    n += row[x - 1] + row[x] + row[x + 1]
                ng[y][x] = n >= 5
        g = ng
    best, seen = [], set()
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            if g[y][x] or (x, y) in seen:
                continue
            region, q = [], deque([(x, y)])
            seen.add((x, y))
            while q:
                cx, cy = q.popleft()
                region.append((cx, cy))
                for dx, dy in DIRS8:
                    nx, ny = cx + dx, cy + dy
                    if not g[ny][nx] and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        q.append((nx, ny))
            if len(region) > len(best):
                best = region
    if len(best) < 650:
        return None
    best.sort()
    for x, y in best:
        lv.t[y][x] = T_FLOOR
    start = best[rng.randrange(len(best))]
    fluid = T_LAVA if (lv.depth >= 8 or rng.random() < 0.5) else T_ACID
    for _ in range(rng.randint(3, 7)):
        x, y = best[rng.randrange(len(best))]
        pool = set()
        for _ in range(rng.randint(8, 30)):
            if lv.t[y][x] == T_FLOOR and (x, y) != start:
                pool.add((x, y))
            dx, dy = DIRS8[rng.randrange(8)]
            if lv.t[y + dy][x + dx] != T_WALL:
                x, y = x + dx, y + dy
        for px, py in pool:
            lv.t[py][px] = fluid
        safe = sum(1 for c in best if lv.t[c[1]][c[0]] == T_FLOOR)
        if len(flood(lv, start, hazard_ok=False)) != safe:
            for px, py in pool:
                lv.t[py][px] = T_FLOOR
    for _ in range(rng.randint(2, 7)):
        bx, by = best[rng.randrange(len(best))]
        if open_around(lv, bx, by) and (bx, by) != start:
            lv.barrels[(bx, by)] = barrel_kind(rng, lv.depth)
    return start


def build_arena(lv, rng, final):
    """A wide oval arena for the two boss floors."""
    W, H = MAP_W, MAP_H
    t = lv.t
    cx, cy = W // 2, H // 2
    for y in range(2, H - 2):
        for x in range(4, W - 4):
            if ((x - cx) / (W / 2.0 - 4)) ** 2 + \
                    ((y - cy) / (H / 2.0 - 2)) ** 2 <= 1.0:
                t[y][x] = T_FLOOR
    for x in range(16, W - 15, 12):
        for y in (cy - 5, cy + 5):
            if t[y][x] == T_FLOOR and t[y][x + 1] == T_FLOOR:
                t[y][x] = t[y][x + 1] = T_WALL
    if final:
        for px, py in ((cx - 14, cy - 2), (cx - 14, cy + 2), (cx + 4, cy - 8),
                       (cx + 4, cy + 8), (cx + 22, cy - 3), (cx + 22, cy + 3)):
            for dy in (0, 1):
                for dx in (0, 1, 2):
                    if t[py + dy][px + dx] == T_FLOOR:
                        t[py + dy][px + dx] = T_LAVA
    for bx, by in ((cx - 6, cy - 7), (cx - 6, cy + 7), (cx + 14, cy - 6),
                   (cx + 14, cy + 6)):
        if open_around(lv, bx, by):
            lv.barrels[(bx, by)] = 'fuel'
    return (8, cy)


def pick_weapon(rng, depth):
    pool = [(k, w) for k, lo, hi, w in WEAPON_TABLE if lo <= depth <= hi]
    if not pool:
        return 'shotgun'
    total = sum(w for _, w in pool)
    r = rng.random() * total
    for k, w in pool:
        r -= w
        if r <= 0:
            return k
    return pool[-1][0]


def pick_armor(rng, depth):
    r = rng.random()
    if depth <= 3:
        return 'armor1' if r < 0.8 else 'armor2'
    if depth <= 6:
        return 'armor1' if r < 0.35 else ('armor2' if r < 0.85 else 'armor3')
    return 'armor2' if r < 0.55 else 'armor3'


def pick_ammo(rng, depth):
    pool = [('bullets', 10), ('shells', 8)]
    if depth >= 4:
        pool.append(('rockets', 4))
    if depth >= 5:
        pool.append(('cells', 4 if depth < 7 else 7))
    total = sum(w for _, w in pool)
    r = rng.random() * total
    for k, w in pool:
        r -= w
        if r <= 0:
            return k
    return 'bullets'


def populate(lv, rng, diff):
    depth = lv.depth
    dist = flood(lv, lv.start, hazard_ok=False)
    cells = sorted(c for c in dist
                   if lv.t[c[1]][c[0]] == T_FLOOR and c not in lv.barrels
                   and c != lv.start and c != lv.stairs)
    rng.shuffle(cells)
    used = set()

    def spot(far=0):
        for i, c in enumerate(cells):
            if c not in used and dist[c] >= far:
                used.add(c)
                del cells[i]
                return c
        return None

    def put(kind, far=0, amount=None):
        c = spot(far)
        if c:
            lv.add_item(c[0], c[1], Item(kind, amount))

    # --- monsters
    budget = (4.0 + depth * 3.0) * DIFFS[diff]['mons']
    pool = [(k, d) for k, d in sorted(MONS.items())
            if d['w'] > 0 and d['depth'][0] <= depth <= d['depth'][1]]
    total = float(sum(d['w'] for _, d in pool))
    tries = 0
    while budget > 0.5 and tries < 300:
        tries += 1
        r = rng.random() * total
        kind = pool[-1][0]
        for k, d in pool:
            r -= d['w']
            if r <= 0:
                kind = k
                break
        d = MONS[kind]
        if d['cost'] > budget + 1.0:
            continue
        c = spot(13)
        if not c:
            break
        group = [c]
        lo, hi = d.get('group', (1, 1))
        want = rng.randint(lo, hi)
        if want > 1:
            near = [(c[0] + dx, c[1] + dy) for dx, dy in DIRS8]
            rng.shuffle(near)
            for n in near:
                if len(group) >= want:
                    break
                if n in dist and lv.t[n[1]][n[0]] == T_FLOOR and \
                        n not in used and n not in lv.barrels and \
                        n != lv.stairs:
                    used.add(n)
                    group.append(n)
        for gx, gy in group:
            m = Mon(kind, gx, gy)
            m.energy = rng.randrange(100)
            lv.mons.append(m)
            budget -= d['cost']

    # --- items
    for _ in range(4 + rng.randint(0, 2)):
        put(pick_ammo(rng, depth))
    for _ in range(rng.randint(1, 2)):
        put('smed')
    if rng.random() < 0.35:
        put('lmed')
    for _ in range(rng.randint(2, 4)):
        put('vital')
    for _ in range(rng.randint(0, 2)):
        put('shard')
    if depth == 2:
        put('shotgun')
    elif rng.random() < 0.75:
        put(pick_weapon(rng, depth))
    if rng.random() < 0.45:
        put(pick_armor(rng, depth))
    if rng.random() < 0.12:
        put('rage', 10)
    if depth >= 3 and rng.random() < 0.10:
        put('surge', 15)
    if depth >= 4 and rng.random() < 0.06:
        put('aegis', 15)
    if depth >= 2 and rng.random() < 0.15:
        put('pack', 10)
    if rng.random() < 0.25:
        put('phase')
    if rng.random() < 0.20:
        put('scan')
    if rng.random() < 0.40:
        put(rng.choice(['modP', 'modA', 'modB', 'modT']))
    if depth >= 6 and rng.random() < 0.25:
        put(rng.choice(['modP', 'modA', 'modB', 'modT']))

    # --- levers and the vault's loot
    if lv.vault:
        x1, y1, x2, y2 = lv.vault['rect']
        inside = [(x, y) for y in range(y1, y2 + 1) for x in range(x1, x2 + 1)
                  if lv.t[y][x] == T_FLOOR and (x, y) not in lv.barrels]
        rng.shuffle(inside)
        loot = [rng.choice(['modP', 'modA', 'modB', 'modT']), 'lmed',
                pick_weapon(rng, min(MAX_DEPTH, depth + 2)),
                pick_armor(rng, min(MAX_DEPTH, depth + 3)),
                pick_ammo(rng, depth + 2), 'surge']
        for kind in loot[:rng.randint(3, 5)]:
            if inside:
                x, y = inside.pop()
                lv.add_item(x, y, Item(kind))
        c = spot(8)
        if c:
            lv.levers[c] = 'vault'
    if rng.random() < 0.30:
        c = spot(8)
        if c:
            lv.levers[c] = rng.choice(['map', 'boom', 'summon', 'mend'])


def populate_arena(lv, rng, diff, final):
    cx, cy = MAP_W // 2, MAP_H // 2
    mul = [0.8, 1.0, 1.15, 1.3][diff]

    def mon(kind, x, y, hpmul=1.0):
        if lv.t[y][x] == T_FLOOR and not lv.mon_at(x, y) and \
                (x, y) not in lv.barrels:
            lv.mons.append(Mon(kind, x, y, hpmul))

    def item(kind, x, y):
        if lv.t[y][x] == T_FLOOR:
            lv.add_item(x, y, Item(kind))

    if final:
        mon('warden', cx + 16, cy, mul)
        if diff >= 1:
            mon('ember', cx + 10, cy - 4)
            mon('ember', cx + 10, cy + 4)
        if diff >= 2:
            mon('brute', cx + 6, cy - 3)
            mon('brute', cx + 6, cy + 3)
        for i, kind in enumerate(['lmed', 'cells', 'rockets', 'cells',
                                  'bullets', 'shells', 'lmed', 'rockets',
                                  'cells', 'armor3']):
            item(kind, 10 + (i % 5) * 2, cy - 2 + (i // 5) * 4)
    else:
        mon('brute', cx + 8, cy - 3, mul)
        mon('brute', cx + 8, cy + 3, mul)
        for i in range(2 + diff):
            mon('fiend', cx - 2 + i * 2, cy - 6 + (i % 2) * 12)
        mon('hound', cx + 2, cy)
        for i, kind in enumerate(['smed', 'shells', 'bullets', 'smed',
                                  'shells', 'armor2']):
            item(kind, 10 + (i % 3) * 2, cy - 2 + (i // 3) * 4)
        item('rocket', MAP_W - 12, cy - 1)
        item('rockets', MAP_W - 12, cy + 1)
        item('rockets', MAP_W - 13, cy + 1)
        item('lmed', MAP_W - 13, cy - 1)


def gen_level(seed, depth, diff):
    for attempt in range(60):
        rng = random.Random("%s:%d:%d" % (seed, depth, attempt))
        lv = Level(depth)
        final = depth >= MAX_DEPTH
        arena = final or depth == 5
        if arena:
            lv.style = 'pit' if final else 'depths'
            start = build_arena(lv, rng, final)
        elif depth <= 4:
            lv.style = 'base'
            start = build_base(lv, rng)
        elif depth <= 7:
            if rng.random() < 0.5:
                lv.style = 'depths'
                start = build_base(lv, rng)
            else:
                lv.style = 'cave'
                start = build_cave(lv, rng)
        else:
            lv.style = 'pit'
            start = build_cave(lv, rng)
        if start is None:
            continue
        lv.start = start
        dist = flood(lv, start, hazard_ok=False)
        if arena:
            if not final:
                lv.stairs = (MAP_W - 9, MAP_H // 2)
        else:
            cands = sorted((d, c) for c, d in dist.items()
                           if lv.t[c[1]][c[0]] == T_FLOOR
                           and c not in lv.barrels)
            if len(cands) < 200:
                continue
            far = cands[int(len(cands) * 0.88):]
            lv.stairs = far[rng.randrange(len(far))][1]
        if lv.stairs:
            lv.t[lv.stairs[1]][lv.stairs[0]] = T_STAIRS
        if arena:
            populate_arena(lv, rng, diff, final)
        else:
            populate(lv, rng, diff)
        return lv
    raise RuntimeError("level generation failed")


# --------------------------------------------------------------------------
# Field of view (recursive shadowcasting)
# --------------------------------------------------------------------------
_OCT = [[1, 0, 0, -1, -1, 0, 0, 1],
        [0, 1, -1, 0, 0, -1, 1, 0],
        [0, 1, 1, 0, 0, -1, -1, 0],
        [1, 0, 0, 1, -1, 0, 0, -1]]


def fov(lv, px, py, radius):
    vis = {(px, py)}
    t = lv.t
    r2 = radius * radius

    def cast(row, start, end, xx, xy, yx, yy):
        if start < end:
            return
        new_start = start
        for j in range(row, radius + 1):
            dx, dy = -j - 1, -j
            blocked = False
            while dx <= 0:
                dx += 1
                X = px + dx * xx + dy * xy
                Y = py + dx * yx + dy * yy
                l_slope = (dx - 0.5) / (dy + 0.5)
                r_slope = (dx + 0.5) / (dy - 0.5)
                if start < r_slope:
                    continue
                if end > l_slope:
                    break
                if not (0 <= X < MAP_W and 0 <= Y < MAP_H):
                    continue
                if dx * dx + dy * dy <= r2:
                    vis.add((X, Y))
                tt = t[Y][X]
                opaque = tt == T_WALL or tt == T_DOOR
                if blocked:
                    if opaque:
                        new_start = r_slope
                        continue
                    blocked = False
                    start = new_start
                elif opaque and j < radius:
                    blocked = True
                    cast(j + 1, start, l_slope, xx, xy, yx, yy)
                    new_start = r_slope
            if blocked:
                break

    for o in range(8):
        cast(1, 1.0, 0.0, _OCT[0][o], _OCT[1][o], _OCT[2][o], _OCT[3][o])
    return vis


# --------------------------------------------------------------------------
# The game itself.  Nothing in here touches pygame, so the whole object can
# be pickled for save games.  Visual and sound effects are queued in self.fx
# and played back by the front end.
# --------------------------------------------------------------------------
class Game:
    def __init__(self, name, seed, diff):
        self.seed = str(seed)
        self.diff = diff
        self.rng = random.Random("%s/combat" % seed)
        self.p = Player(name)
        self.depth = 0
        self.ticks = 0
        self.seq = 0
        self.log = []
        self.fx = []
        self.over = False
        self.won = False
        self.cause = ''
        self.levelups = 0
        self.last_target = None
        self._dm = {}
        p = self.p
        p.weapon = Item('pistol')
        p.ammo['bullet'] = 40
        p.inv = [Item('smed'), Item('smed')]
        self.lv = None
        self.enter_level(1)

    # ---------------------------------------------------------- utilities
    def msg(self, text, col='grey'):
        self.log.append((self.seq, text, col))
        if len(self.log) > 400:
            del self.log[:150]

    def sfx(self, name, x=None, y=None):
        vol = 1.0
        if x is not None:
            vol = max(0.15, 1.0 - cheb(x, y, self.p.x, self.p.y) / 26.0)
        self.fx.append(('snd', name, vol))

    def turn(self):
        return self.ticks // 100

    def ammo_cap(self, kind):
        return AMMO_CAP[kind] * (2 if self.p.backpack else 1)

    def score(self):
        s = self.p.xp + self.depth * 100 + (2000 if self.won else 0)
        return int(s * DIFFS[self.diff]['score'])

    def enter_level(self, depth):
        p = self.p
        self.depth = depth
        self.lv = gen_level(self.seed, depth, self.diff)
        p.x, p.y = self.lv.start
        p.running = 0
        p.tired = False
        self.last_target = None
        self._dm = {}
        self.msg("You enter %s (floor %d)." % (self.lv.name, depth), 'white')
        if depth == MAX_DEPTH:
            self.msg("Something enormous stirs across the pit...", 'lred')
        if p.tr('sense') >= 1:
            self.msg("You sense the lay of this place.", 'lcyan')
        self.update_fov()

    def update_fov(self):
        lv, p = self.lv, self.p
        lv.visible = fov(lv, p.x, p.y, FOV_RADIUS)
        seen = lv.seen
        for x, y in lv.visible:
            seen[y][x] = True

    def reveal_map(self):
        lv = self.lv
        for y in range(MAP_H):
            for x in range(MAP_W):
                if lv.t[y][x] != T_WALL:
                    lv.seen[y][x] = True
                    for dx, dy in DIRS8:
                        if lv.inb(x + dx, y + dy):
                            lv.seen[y + dy][x + dx] = True

    def visible_mons(self):
        p, lv = self.p, self.lv
        ms = [m for m in lv.mons if (m.x, m.y) in lv.visible]
        ms.sort(key=lambda m: (cheb(p.x, p.y, m.x, m.y), m.x, m.y))
        return ms

    def clear(self, x0, y0, x1, y1):
        """True if nothing solid lies strictly between the two cells."""
        lv = self.lv
        for x, y in line(x0, y0, x1, y1)[:-1]:
            if lv.solid(x, y):
                return False
        return True

    def noise(self, x, y, radius):
        for m in self.lv.mons:
            if not m.awake and math.hypot(m.x - x, m.y - y) <= radius:
                m.awake = True

    # ------------------------------------------------------ weapon numbers
    def wstats(self, it):
        """Effective stats of a weapon after mods and traits."""
        p = self.p
        d = dict(it.d) if it else dict(FISTS)
        n, sides, bonus = d['dmg']
        for m in (it.mods if it else []):
            if m == 'P':
                sides += 1
            elif m == 'A':
                d['acc'] = d.get('acc', 0) + 15
            elif m == 'B' and 'mag' in d:
                d['mag'] = max(d['mag'] + d.get('per', 1),
                               int(d['mag'] * 1.5))
            elif m == 'T':
                d['fire'] = int(d['fire'] * 0.8)
                if 'reload' in d:
                    d['reload'] = int(d['reload'] * 0.8)
        if d.get('melee'):
            bonus += 3 * p.tr('brute')
        if it and it.kind == 'pistol':
            bonus += 2 * p.tr('sling')
            d['fire'] = int(d['fire'] * (1 - 0.2 * p.tr('sling')))
        if d.get('shots', 1) > 1:
            d['shots'] += p.tr('burst')
        d['dmg'] = (n, sides, bonus)
        d['fire'] = max(20, int(d['fire'] * (1 - 0.15 * p.tr('quick'))))
        if 'reload' in d:
            d['reload'] = max(20, int(d['reload'] *
                                      (1 - 0.25 * p.tr('loader'))))
        return d

    def mod_slots(self):
        return 2 + self.p.tr('tinker')

    def item_label(self, it):
        d = it.d
        ty = d['type']
        if ty == 'weapon':
            ws = self.wstats(it)
            s = "%s (%s)" % (d['name'], dice_str(ws['dmg'],
                                                 ws.get('shots', 1)))
            if not d.get('melee'):
                s += " [%d/%d]" % (it.loaded, ws['mag'])
            if it.mods:
                s += " +" + "".join(it.mods)
            return s
        if ty == 'armor':
            return "%s [%d] %d%%" % (d['name'], d['prot'], it.dur)
        if ty == 'ammo':
            return "%s (x%d)" % (d['name'], it.amount)
        return d['name']

    def hit_chance(self, ws, dist):
        p = self.p
        c = 78 + ws.get('acc', 0) + 10 * p.tr('eye') - 3 * max(0, dist - 5)
        if p.running > 0:
            c -= 12
        return max(15, min(97, c))

    def dodge(self):
        p = self.p
        return (25 if p.running > 0 else 0) + 15 * p.tr('evade') + \
            5 * p.tr('sprint')

    # ------------------------------------------------------------- damage
    def gain_xp(self, n):
        p = self.p
        p.xp += n
        while p.level < 25 and p.xp >= xp_need(p.level + 1):
            p.level += 1
            self.levelups += 1
            self.msg("You advance to level %d!" % p.level, 'gold')
            self.sfx('levelup')

    def available_traits(self):
        p = self.p
        out = []
        for key, name, mx, desc, req in TRAITS:
            if p.tr(key) < mx and all(p.tr(k) >= v for k, v in req.items()):
                out.append(key)
        return out

    def take_trait(self, key):
        p = self.p
        p.traits[key] = p.tr(key) + 1
        if key == 'iron':
            p.maxhp += 10
            p.hp += 10
        self.levelups = max(0, self.levelups - 1)
        self.msg("You learn %s (rank %d)." % (TRAIT_BY_KEY[key][1],
                                              p.traits[key]), 'gold')

    def hurt_mon(self, m, dmg):
        """Damage a monster.  Returns True if it died."""
        if m.hp <= 0:
            return True
        dmg = max(1, dmg - m.d.get('armor', 0))
        m.hp -= dmg
        m.awake = True
        if (m.x, m.y) in self.lv.visible:
            self.fx.append(('hit', (m.x, m.y), 'lred'))
        if m.hp <= 0:
            self.kill(m)
            return True
        return False

    def kill(self, m):
        lv, p = self.lv, self.p
        if m in lv.mons:
            lv.mons.remove(m)
        p.kills[m.kind] = p.kills.get(m.kind, 0) + 1
        pos = (m.x, m.y)
        if pos in lv.visible:
            self.msg("%s dies." % m.the(True), 'lred')
        self.sfx('die', m.x, m.y)
        tt = lv.t[m.y][m.x]
        if tt == T_FLOOR:
            if pos not in lv.levers:
                lv.decor[pos] = ('%', m.d['col'])
            lv.blood.add(pos)
            dx, dy = DIRS8[self.rng.randrange(8)]
            if lv.t[m.y + dy][m.x + dx] == T_FLOOR:
                lv.blood.add((m.x + dx, m.y + dy))
        if tt not in (T_ACID, T_LAVA):
            for kind, chance in m.d.get('drop', []):
                if self.rng.random() < chance:
                    lv.add_item(m.x, m.y, Item(kind))
        if self.last_target is m:
            self.last_target = None
        self.gain_xp(m.d['xp'])
        if m.d.get('boss'):
            self.won = True
            self.over = True
            self.cause = 'destroyed the Warden and sealed the breach'
            self.msg("The Warden collapses. The breach is sealed. You win!",
                     'gold')
            self.sfx('win')

    def hurt_player(self, dmg, cause, armor=True):
        p = self.p
        if self.over or p.invuln > 0:
            return 0
        dmg = int(dmg * DIFFS[self.diff]['dmg'] + 0.5)
        if p.berserk > 0:
            dmg = (dmg + 1) // 2
        dmg -= p.tr('thick')
        if armor and p.armor and dmg > 1:
            red = min(p.armor.d['prot'], dmg - 1)
            dmg -= red
            p.armor.dur -= red
            if p.armor.dur <= 0:
                self.msg("Your %s is destroyed!" % p.armor.d['name'],
                         'orange')
                p.armor = None
        dmg = max(1, dmg)
        p.hp -= dmg
        self.fx.append(('flash', 'red', min(0.5, 0.15 + dmg / 60.0)))
        self.fx.append(('shake', min(10, 2 + dmg // 3)))
        self.sfx('hurt')
        if p.hp <= 0:
            p.hp = 0
            self.over = True
            self.cause = cause
            self.msg("You die...", 'red')
        return dmg

    def knock(self, m, fx_, fy_):
        lv, p = self.lv, self.p
        nx, ny = m.x + sign(m.x - fx_), m.y + sign(m.y - fy_)
        if (nx, ny) == (m.x, m.y) or lv.solid(nx, ny):
            return
        if lv.mon_at(nx, ny) or (nx, ny) in lv.barrels or \
                (nx, ny) == (p.x, p.y):
            return
        m.x, m.y = nx, ny

    def explode(self, cx, cy, radius, dice, cause, col='orange', immune=None):
        lv, p = self.lv, self.p
        cells = []
        for y in range(max(1, cy - radius), min(MAP_H - 1, cy + radius + 1)):
            for x in range(max(1, cx - radius),
                           min(MAP_W - 1, cx + radius + 1)):
                d = math.hypot(x - cx, y - cy)
                if d > radius + 0.5 or lv.solid(x, y):
                    continue
                if (x, y) != (cx, cy) and not self.clear(cx, cy, x, y):
                    continue
                cells.append((x, y, d))
        self.sfx('boom', cx, cy)
        near = cheb(cx, cy, p.x, p.y)
        self.fx.append(('shake', max(2, 9 - near // 2)))
        self.fx.append(('boom', cells, col))
        self.noise(cx, cy, 16)
        chain = []
        for x, y, d in cells:
            fall = max(0.25, 1.0 - d / (radius + 1.0))
            if (x, y) == (p.x, p.y):
                self.msg("You are caught in the blast!", 'orange')
                self.hurt_player(int(roll(self.rng, dice) * fall), cause)
            m = lv.mon_at(x, y)
            if m and m is not immune:
                if not self.hurt_mon(m, int(roll(self.rng, dice) * fall)) \
                        and d > 0:
                    self.knock(m, cx, cy)
            if (x, y) in lv.barrels:
                chain.append((x, y))
        for b in chain:
            if b in lv.barrels:
                self.explode_barrel(b)

    def explode_barrel(self, pos):
        lv = self.lv
        kind = lv.barrels.pop(pos, None)
        if kind is None:
            return
        if pos in lv.visible:
            self.msg("The %s explodes!" % BARRELS[kind][0], 'orange')
        self.explode(pos[0], pos[1], 2, (5, 5, 0),
                     'was blown up by an exploding barrel', BARRELS[kind][1])
        fluid = {'acid': T_ACID, 'napalm': T_LAVA}.get(kind)
        if fluid:
            for dx, dy in DIRS8 + [(0, 0)]:
                x, y = pos[0] + dx, pos[1] + dy
                if lv.t[y][x] == T_FLOOR and (x, y) not in lv.barrels \
                        and (x, y) not in lv.levers:
                    lv.t[y][x] = fluid
                    lv.decor.pop((x, y), None)

    # ---------------------------------------------------------- shooting
    def shot(self, who, tgt, spec):
        """Fire one projectile.  Returns what it hit: None, 'p', a Mon,
        'barrel' or 'boom'."""
        lv, p = self.lv, self.p
        byp = who is p
        sx, sy = who.x, who.y
        kind = spec['kind']
        path = ray(sx, sy, tgt[0], tgt[1], 40 if byp else
                   spec.get('range', 10) + 8)
        flown, hit, end = [], None, (sx, sy)
        for x, y in path:
            if not lv.inb(x, y) or lv.solid(x, y):
                break
            flown.append((x, y))
            end = (x, y)
            if (x, y) == (p.x, p.y):
                if byp:
                    continue
                d = cheb(sx, sy, x, y)
                c = spec.get('acc', 65) - 2 * d - self.dodge()
                if self.rng.random() * 100 < max(10, min(95, c)):
                    hit = 'p'
                    break
                continue
            m = lv.mon_at(x, y)
            if m and m is not who:
                if byp:
                    c = self.hit_chance(spec, cheb(sx, sy, x, y))
                    if (x, y) != tuple(tgt):
                        c *= 0.5
                else:
                    c = 35
                if self.rng.random() * 100 < c:
                    hit = m
                    break
                continue
            if (x, y) in lv.barrels and ((x, y) == tuple(tgt) or
                                         self.rng.random() < 0.3):
                hit = 'barrel'
                break
        if flown:
            self.fx.append(('proj', flown, kind, (sx, sy)))
        radius = spec.get('radius', 0)
        who_name = 'your own blast' if byp else a_an(who.name)
        if radius:
            if kind == 'bfg':
                self.fx.append(('flash', 'lgreen', 0.5))
            cause = 'was killed by %s' % who_name
            self.explode(end[0], end[1], radius, spec['dmg'], cause,
                         BOOM_COL.get(kind, 'orange'),
                         immune=None if byp else who)
            return 'boom'
        dmg = roll(self.rng, spec['dmg'])
        if hit == 'p':
            self.hurt_player(dmg, 'was killed by %s' % who_name)
        elif hit == 'barrel':
            self.explode_barrel(end)
        elif hit is not None:
            self.hurt_mon(hit, dmg)
        return hit

    def blast(self, who, tgt, spec):
        """Shotgun cone.  Never misses, but weakens with distance."""
        lv, p = self.lv, self.p
        byp = who is p
        sx, sy = who.x, who.y
        ang = math.atan2(tgt[1] - sy, tgt[0] - sx)
        spread = spec.get('spread', 0.24)
        R = spec.get('range', 9)
        cells = []
        for y in range(max(0, sy - R), min(MAP_H, sy + R + 1)):
            for x in range(max(0, sx - R), min(MAP_W, sx + R + 1)):
                dx, dy = x - sx, y - sy
                d = math.hypot(dx, dy)
                if d == 0 or d > R + 0.5 or lv.solid(x, y):
                    continue
                a = abs((math.atan2(dy, dx) - ang + math.pi) %
                        (2 * math.pi) - math.pi)
                if a > spread + 0.35 / d:
                    continue
                if not self.clear(sx, sy, x, y):
                    continue
                cells.append((x, y, d))
        if cells:
            self.fx.append(('cone', cells, (sx, sy)))
        total = roll(self.rng, spec['dmg'])
        hits, hit_player, chain = [], False, []
        for x, y, d in cells:
            dmg = max(1, int(total * max(0.2, 1.0 - 0.085 * max(0, d - 1))))
            if (x, y) == (p.x, p.y):
                if not byp:
                    hit_player = True
                    self.hurt_player(dmg, 'was killed by %s' % a_an(who.name))
                continue
            m = lv.mon_at(x, y)
            if m and m is not who and (byp or self.rng.random() < 0.5):
                hits.append(m.name)
                if not self.hurt_mon(m, dmg) and dmg >= 8:
                    self.knock(m, sx, sy)
            if (x, y) in lv.barrels and dmg >= 4:
                chain.append((x, y))
        for b in chain:
            if b in lv.barrels:
                self.explode_barrel(b)
        return hits, hit_player

    # ----------------------------------------------------- player actions
    # Each returns the time the action took in ticks (100 = one turn), or
    # 0 if nothing happened.
    def wait(self):
        return 100

    def can_walk(self, x, y, safe=True):
        lv = self.lv
        if not lv.inb(x, y):
            return False
        t = lv.t[y][x]
        if t == T_WALL or (x, y) in lv.barrels or lv.mon_at(x, y):
            return False
        if safe and t in (T_ACID, T_LAVA):
            return False
        return True

    def move_cost(self):
        p = self.p
        c = 100 * (1 - 0.15 * p.tr('sprint'))
        if p.running > 0:
            c *= 0.7
        return max(20, int(c))

    def move(self, dx, dy):
        lv, p = self.lv, self.p
        nx, ny = p.x + dx, p.y + dy
        if not lv.inb(nx, ny):
            return 0
        m = lv.mon_at(nx, ny)
        if m:
            return self.melee(m)
        t = lv.t[ny][nx]
        if t == T_WALL:
            return 0
        if t == T_DOOR:
            lv.t[ny][nx] = T_ODOOR
            self.msg("You open the door.")
            self.sfx('door')
            return 50
        if (nx, ny) in lv.barrels:
            bx, by = nx + dx, ny + dy
            if lv.t[by][bx] == T_FLOOR and not lv.mon_at(bx, by) and \
                    (bx, by) not in lv.barrels and (bx, by) not in lv.levers:
                lv.barrels[(bx, by)] = lv.barrels.pop((nx, ny))
                self.msg("You push the barrel.")
            else:
                self.msg("The barrel won't budge.")
                return 0
        p.x, p.y = nx, ny
        self.step_on()
        if p.tr('shell') and p.weapon and p.weapon.d.get('kind') == 'shot':
            self.load_weapon(p.weapon)
        return self.move_cost()

    def step_on(self):
        lv, p = self.lv, self.p
        pos = (p.x, p.y)
        items = lv.items.get(pos)
        if items:
            for it in list(items):
                if it.d['type'] in ('ammo', 'orb') and self.take(it):
                    items.remove(it)
            if not items:
                del lv.items[pos]
            else:
                names = [self.item_label(i) for i in items]
                self.msg("You see here: %s." % ", ".join(names))
        if pos in lv.levers:
            self.msg("There is a lever here (g to pull it).", 'gold')
        t = lv.t[p.y][p.x]
        if t == T_STAIRS:
            self.msg("Stairs lead down from here (> to descend).", 'white')

    def melee(self, m):
        p = self.p
        w = p.weapon if (p.weapon and p.weapon.d.get('melee')) else None
        ws = self.wstats(w)
        self.sfx(ws.get('snd', 'melee'))
        self.noise(p.x, p.y, 5)
        chance = 85 + 5 * p.tr('brute')
        if self.rng.random() * 100 >= chance:
            self.msg("You miss %s." % m.the())
            return ws['fire']
        dmg = roll(self.rng, ws['dmg'])
        if p.berserk > 0:
            dmg *= 2
        self.msg("You hit %s." % m.the())
        if self.hurt_mon(m, dmg) and p.tr('rage') and \
                self.rng.random() < 0.35:
            p.berserk = max(p.berserk, 1200)
            self.msg("Blood rage takes you!", 'red')
        return ws['fire']

    def load_weapon(self, w):
        p = self.p
        ws = self.wstats(w)
        n = min(ws['mag'] - w.loaded, p.ammo[ws['ammo']])
        if n > 0:
            w.loaded += n
            p.ammo[ws['ammo']] -= n
        return n

    def reload(self):
        p = self.p
        w = p.weapon
        if not w or w.d.get('melee'):
            self.msg("You have nothing to reload.")
            return 0
        ws = self.wstats(w)
        if w.loaded >= ws['mag']:
            self.msg("Your %s is already loaded." % ws['name'])
            return 0
        if self.load_weapon(w) <= 0:
            self.msg("You have no %s left!" %
                     AMMO_NAME[ws['ammo']].lower(), 'orange')
            return 0
        self.msg("You reload the %s." % ws['name'])
        self.sfx('reload')
        return ws['reload']

    def fire(self, tx, ty):
        p, lv = self.p, self.lv
        w = p.weapon
        if not w or w.d.get('melee'):
            self.msg("You have no gun in your hands.")
            return 0
        if (tx, ty) == (p.x, p.y) or not lv.inb(tx, ty):
            return 0
        ws = self.wstats(w)
        per = ws.get('per', 1)
        if w.loaded < per:
            self.sfx('empty')
            if p.ammo[ws['ammo']] > 0 and w.loaded + p.ammo[ws['ammo']] >= per:
                self.msg("Click - empty!", 'orange')
                return self.reload()
            self.msg("Click - your %s is empty and you have no %s!" %
                     (ws['name'], AMMO_NAME[ws['ammo']].lower()), 'orange')
            return 0
        target = lv.mon_at(tx, ty)
        self.noise(p.x, p.y, 14)
        self.sfx(ws.get('snd', 'pistol'))
        if ws['kind'] == 'shot':
            w.loaded -= per
            hits, _ = self.blast(p, (tx, ty), ws)
            if hits:
                self.msg("Your blast tears into %s." %
                         ", ".join("the " + h if not h.startswith('the ')
                                   else h for h in sorted(set(hits))))
            else:
                self.msg("You fire the %s." % ws['name'])
        else:
            shots = min(ws.get('shots', 1), w.loaded // per)
            hits, boom = {}, False
            for i in range(shots):
                w.loaded -= per
                if i and i % 2 == 0:
                    self.sfx(ws.get('snd', 'pistol'))
                h = self.shot(p, (tx, ty), ws)
                if h == 'boom':
                    boom = True
                elif isinstance(h, Mon):
                    hits[h.name] = hits.get(h.name, 0) + 1
                if self.over:
                    break
            for name, n in sorted(hits.items()):
                nm = name if name.startswith('the ') else 'the ' + name
                self.msg("You hit %s%s." % (nm, " x%d" % n if n > 1 else ""))
            if not hits and not boom:
                self.msg("You miss." if target else
                         "You fire the %s." % ws['name'])
        return ws['fire']

    def take(self, it):
        """Try to pick an item up.  Returns True if it left the floor."""
        p = self.p
        d = it.d
        ty = d['type']
        if ty == 'ammo':
            kind = d['ammo']
            room = self.ammo_cap(kind) - p.ammo[kind]
            n = min(room, it.amount)
            if n <= 0:
                return False
            p.ammo[kind] += n
            it.amount -= n
            self.msg("You pick up %d %s." % (n, AMMO_NAME[kind].lower()))
            self.sfx('ammo')
            return it.amount <= 0
        if ty == 'orb':
            return self.use_orb(it)
        if ty == 'weapon' and not it.mods:
            mine = [p.weapon] + p.inv if p.weapon else p.inv
            if any(o.kind == it.kind for o in mine):
                if d.get('melee'):
                    self.msg("You already carry a %s." % d['name'])
                    return False
                kind = d['ammo']
                n = min(it.loaded, self.ammo_cap(kind) - p.ammo[kind])
                if n <= 0:
                    self.msg("You already carry a %s." % d['name'])
                    return False
                p.ammo[kind] += n
                it.loaded -= n
                self.msg("You strip %d %s from the spare %s." %
                         (n, AMMO_NAME[kind].lower(), d['name']))
                self.sfx('ammo')
                return False
        if len(p.inv) >= INV_MAX:
            self.msg("Your pack is full.", 'orange')
            return False
        p.inv.append(it)
        self.msg("You pick up the %s." % d['name'])
        self.sfx('pickup')
        return True

    def use_orb(self, it):
        p = self.p
        k = it.kind
        if k == 'vital':
            if p.hp >= p.maxhp * 2:
                return False
            p.hp = min(p.maxhp * 2, p.hp + 10)
            self.msg("A vital orb: you feel better.", 'lblue')
        elif k == 'surge':
            p.hp = min(p.maxhp * 2, p.hp + p.maxhp)
            self.msg("A surge orb! Power floods through you.", 'cyan')
        elif k == 'rage':
            p.berserk = max(p.berserk, 0) + 3000
            p.hp = max(p.hp, min(p.maxhp, p.hp + 15))
            self.msg("A rage orb! You feel like a killing machine!", 'red')
        elif k == 'aegis':
            p.invuln = max(p.invuln, 0) + 2500
            self.msg("An aegis orb! Nothing can hurt you.", 'white')
        elif k == 'shard':
            if not p.armor or p.armor.dur >= 150:
                return False
            p.armor.dur = min(150, p.armor.dur + 25)
            self.msg("An armor shard patches your armor.", 'green')
        elif k == 'pack':
            if p.backpack:
                p.ammo['bullet'] = min(self.ammo_cap('bullet'),
                                       p.ammo['bullet'] + 24)
                p.ammo['shell'] = min(self.ammo_cap('shell'),
                                      p.ammo['shell'] + 8)
                self.msg("Another backpack, stuffed with ammo.", 'brown')
            else:
                p.backpack = True
                self.msg("A backpack! You can carry twice the ammo.",
                         'gold')
        self.sfx('power' if k in ('surge', 'rage', 'aegis', 'pack')
                 else 'pickup')
        return True

    def pickup(self):
        lv, p = self.lv, self.p
        pos = (p.x, p.y)
        items = lv.items.get(pos)
        if not items:
            if pos in lv.levers:
                return self.pull_lever()
            if lv.t[p.y][p.x] == T_STAIRS:
                return self.descend()
            self.msg("There is nothing here to pick up.")
            return 0
        got = False
        for it in list(items):
            if self.take(it):
                items.remove(it)
                got = True
        if not items:
            del lv.items[pos]
        return 80 if got else 0

    def interact(self):
        lv, p = self.lv, self.p
        pos = (p.x, p.y)
        if lv.t[p.y][p.x] == T_STAIRS:
            return self.descend()
        if pos in lv.levers:
            return self.pull_lever()
        if pos in lv.items:
            return self.pickup()
        self.msg("There is nothing to use here.")
        return 0

    def descend(self):
        lv, p = self.lv, self.p
        if lv.t[p.y][p.x] != T_STAIRS:
            self.msg("There are no stairs here.")
            return 0
        self.sfx('stairs')
        self.enter_level(self.depth + 1)
        return 0

    def pull_lever(self):
        lv, p = self.lv, self.p
        pos = (p.x, p.y)
        eff = lv.levers.pop(pos, None)
        if eff is None:
            return 0
        lv.decor[pos] = ('&', 'dgrey')
        self.sfx('lever')
        if eff == 'vault' and lv.vault:
            x, y = lv.vault['door']
            lv.t[y][x] = T_ODOOR
            lv.seen[y][x] = True
            self.msg("You pull the lever. Somewhere a sealed door grinds "
                     "open.", 'gold')
        elif eff == 'map':
            self.reveal_map()
            self.msg("You pull the lever. A map of the floor flickers into "
                     "view.", 'lgreen')
        elif eff == 'boom' and lv.barrels:
            self.msg("You pull the lever. Explosions rock the floor!",
                     'orange')
            for b in sorted(lv.barrels):
                if b in lv.barrels:
                    self.explode_barrel(b)
        elif eff == 'summon':
            self.msg("You pull the lever. It's a trap!", 'lred')
            self.summon(self.rng.randint(2, 3))
        elif eff == 'mend':
            p.hp = max(p.hp, p.maxhp)
            if p.armor:
                p.armor.dur = max(p.armor.dur, 100)
            self.msg("You pull the lever. A soothing light washes over "
                     "you.", 'lblue')
        else:
            self.msg("You pull the lever. Nothing seems to happen.")
        return 100

    def summon(self, n):
        lv, p = self.lv, self.p
        pool = [k for k, d in sorted(MONS.items()) if d['w'] > 0 and
                d['depth'][0] <= self.depth <= d['depth'][1] and
                d['cost'] <= 2.5]
        spots = [(x, y) for (x, y) in sorted(lv.visible)
                 if 2 <= cheb(x, y, p.x, p.y) <= 6 and
                 self.can_walk(x, y)]
        self.rng.shuffle(spots)
        for x, y in spots[:n]:
            m = Mon(self.rng.choice(pool or ['fiend']), x, y)
            m.awake = True
            lv.mons.append(m)
        self.sfx('tele')

    def close_door(self, dx, dy):
        lv, p = self.lv, self.p
        x, y = p.x + dx, p.y + dy
        if not lv.inb(x, y) or lv.t[y][x] != T_ODOOR:
            self.msg("There is no open door there.")
            return 0
        if lv.mon_at(x, y) or (x, y) in lv.items or (x, y) in lv.barrels:
            self.msg("Something is in the way.")
            return 0
        lv.t[y][x] = T_DOOR
        self.msg("You close the door.")
        self.sfx('door')
        return 50

    def open_doors_near(self):
        lv, p = self.lv, self.p
        return [(dx, dy) for dx, dy in DIRS8
                if lv.inb(p.x + dx, p.y + dy) and
                lv.t[p.y + dy][p.x + dx] == T_ODOOR]

    def toggle_run(self):
        p = self.p
        if p.running > 0:
            p.running = 0
            p.tired = True
            self.msg("You stop running and catch your breath.")
        elif p.tired:
            self.msg("You are too tired to run until the next floor.")
        else:
            p.running = 3000
            self.msg("You start running!", 'yellow')
        return 0

    def equip(self, i):
        p = self.p
        it = p.inv.pop(i)
        old = p.weapon
        p.weapon = it
        if old:
            p.inv.insert(i, old)
            p.prev_kind = old.kind
        self.msg("You ready the %s." % it.d['name'])
        self.sfx('reload')
        return 0 if p.tr('juggle') else 80

    def weapon_indexes(self):
        p = self.p
        idx = [i for i, it in enumerate(p.inv) if it.d['type'] == 'weapon']
        idx.sort(key=lambda i: (p.inv[i].d['slot'], p.inv[i].kind))
        return idx

    def quick(self, slot):
        p = self.p
        idx = [i for i in self.weapon_indexes()
               if p.inv[i].d['slot'] == slot]
        if not idx:
            if p.weapon and p.weapon.d['slot'] == slot:
                self.msg("You already hold your %s." % p.weapon.d['name'])
            else:
                self.msg("You have no weapon for slot %d." % slot)
            return 0
        return self.equip(idx[0])

    def cycle_weapon(self, step):
        p = self.p
        idx = self.weapon_indexes()
        if not idx:
            self.msg("You have no other weapon.")
            return 0
        cur = (p.weapon.d['slot'], p.weapon.kind) if p.weapon else (0, '')
        keys = [(p.inv[i].d['slot'], p.inv[i].kind) for i in idx]
        if step > 0:
            later = [i for i, k in zip(idx, keys) if k > cur]
            return self.equip(later[0] if later else idx[0])
        earlier = [i for i, k in zip(idx, keys) if k < cur]
        return self.equip(earlier[-1] if earlier else idx[-1])

    def swap_prev(self):
        p = self.p
        for i, it in enumerate(p.inv):
            if it.d['type'] == 'weapon' and it.kind == p.prev_kind:
                return self.equip(i)
        idx = self.weapon_indexes()
        if idx:
            return self.equip(idx[0])
        self.msg("You have no other weapon.")
        return 0

    def use(self, i):
        p, lv = self.p, self.lv
        if not (0 <= i < len(p.inv)):
            return 0
        it = p.inv[i]
        d = it.d
        ty = d['type']
        if ty == 'weapon':
            return self.equip(i)
        if ty == 'armor':
            old = p.armor
            p.armor = p.inv.pop(i)
            if old:
                p.inv.insert(i, old)
            self.msg("You put on the %s." % d['name'])
            return 150
        if ty == 'mod':
            w = p.weapon
            if not w:
                self.msg("Ready a weapon first.")
                return 0
            if len(w.mods) >= self.mod_slots():
                self.msg("Your %s has no free mod slots." % w.d['name'])
                return 0
            if d['mod'] == 'B' and w.d.get('melee'):
                self.msg("A bulk mod does nothing for a melee weapon.")
                return 0
            w.mods.append(d['mod'])
            p.inv.pop(i)
            self.msg("You fit the %s to your %s." % (d['name'],
                                                     w.d['name']), 'gold')
            self.sfx('reload')
            return 100
        if it.kind == 'smed':
            if p.hp >= p.maxhp:
                self.msg("You don't need a medkit right now.")
                return 0
            heal = int(25 * (1.5 if p.tr('medic') else 1))
            p.hp = min(p.maxhp, p.hp + heal)
            self.msg("You use a small medkit. You feel better.", 'lgreen')
        elif it.kind == 'lmed':
            if p.hp >= p.maxhp and not p.tired:
                self.msg("You don't need a medkit right now.")
                return 0
            top = int(p.maxhp * (1.5 if p.tr('medic') else 1))
            p.hp = max(p.hp, top)
            p.tired = False
            self.msg("You use a large medkit. You feel great!", 'lgreen')
        elif it.kind == 'phase':
            dist = flood(lv, (p.x, p.y), hazard_ok=False)
            spots = sorted(c for c, dd in dist.items() if dd >= 12 and
                           self.can_walk(c[0], c[1]))
            if not spots:
                spots = sorted(c for c in dist if self.can_walk(c[0], c[1]))
            if not spots:
                self.msg("The phase unit sputters and does nothing.")
                return 0
            p.x, p.y = spots[self.rng.randrange(len(spots))]
            self.msg("The world lurches. You are somewhere else.", 'lblue')
            self.fx.append(('flash', 'lblue', 0.4))
            self.sfx('tele')
            self.step_on()
        elif it.kind == 'scan':
            self.reveal_map()
            self.msg("The scanner maps the floor.", 'lgreen')
        else:
            return 0
        self.sfx('pickup')
        p.inv.pop(i)
        return 100

    def drop(self, i):
        p, lv = self.p, self.lv
        if not (0 <= i < len(p.inv)):
            return 0
        if lv.t[p.y][p.x] in (T_ACID, T_LAVA):
            self.msg("You can't drop things here.")
            return 0
        it = p.inv.pop(i)
        lv.add_item(p.x, p.y, it)
        self.msg("You drop the %s." % it.d['name'])
        return 50

    def path_to(self, tx, ty):
        """Shortest path over explored, safe ground (for mouse travel)."""
        lv, p = self.lv, self.p
        if not lv.inb(tx, ty) or not lv.seen[ty][tx]:
            return None
        start = (p.x, p.y)
        prev = {start: None}
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur == (tx, ty):
                break
            for dx, dy in DIRS8:
                n = (cur[0] + dx, cur[1] + dy)
                if n in prev or not lv.inb(n[0], n[1]):
                    continue
                t = lv.t[n[1]][n[0]]
                if not lv.seen[n[1]][n[0]] or t in (T_WALL, T_ACID, T_LAVA) \
                        or n in lv.barrels:
                    continue
                prev[n] = cur
                q.append(n)
        if (tx, ty) not in prev:
            return None
        path, cur = [], (tx, ty)
        while cur != start:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path

    def describe(self, x, y):
        lv, p = self.lv, self.p
        if not lv.inb(x, y):
            return ""
        pos = (x, y)
        vis = pos in lv.visible
        if not vis and not lv.seen[y][x]:
            return "Unexplored."
        parts = []
        if pos == (p.x, p.y):
            parts.append("you")
        if vis:
            m = lv.mon_at(x, y)
            if m:
                parts.append("%s (%s)" % (a_an(m.name), m.state()))
        if pos in lv.barrels:
            parts.append(a_an(BARRELS[lv.barrels[pos]][0]))
        for it in lv.items.get(pos, []):
            parts.append(self.item_label(it))
        if pos in lv.levers:
            parts.append("a lever")
        elif pos in lv.decor:
            parts.append("a used lever" if lv.decor[pos][0] == '&'
                         else "a corpse")
        parts.append(TILE_NAME[lv.t[y][x]])
        s = ", ".join(parts)
        s = s[0].upper() + s[1:] + "."
        return s if vis else "(remembered) " + s

    # ------------------------------------------------------------ monsters
    def dmap(self, fly):
        """Distance-to-player map that hunting monsters walk down."""
        dm = self._dm.get(fly)
        if dm is not None:
            return dm
        lv, p = self.lv, self.p
        t = lv.t
        dm = [[-1] * MAP_W for _ in range(MAP_H)]
        dm[p.y][p.x] = 0
        q = deque([(p.x, p.y)])
        while q:
            x, y = q.popleft()
            v = dm[y][x] + 1
            if v > 45:
                continue
            for dx, dy in DIRS8:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
                    continue
                if dm[ny][nx] != -1:
                    continue
                tt = t[ny][nx]
                if tt == T_WALL:
                    continue
                if not fly and (tt == T_ACID or tt == T_LAVA):
                    continue
                dm[ny][nx] = v
                q.append((nx, ny))
        self._dm[fly] = dm
        return dm

    def mon_act(self, m):
        lv, p = self.lv, self.p
        d = m.d
        dist = cheb(m.x, m.y, p.x, p.y)
        sees = (m.x, m.y) in lv.visible
        if not m.awake:
            if sees and self.rng.random() < 0.8:
                m.awake = True
                if self.rng.random() < 0.3:
                    self.sfx('alert', m.x, m.y)
            return
        if dist <= 1 and d.get('melee'):
            self.sfx('melee', m.x, m.y)
            if self.rng.random() * 100 < 82 - self.dodge() / 3.0:
                self.msg("%s hits you!" % m.the(True), 'lred')
                self.hurt_player(roll(self.rng, d['melee']),
                                 'was killed by %s' % a_an(m.name))
            else:
                self.msg("%s misses you." % m.the(True))
            return
        r = d.get('ranged')
        if r and sees and dist <= r['range']:
            chance = 1.0 if (dist <= 1 or not d.get('melee') and dist <= 2) \
                else r['chance']
            if self.rng.random() < chance and \
                    self.clear(m.x, m.y, p.x, p.y):
                self.mon_fire(m, r)
                return
            if dist <= 1:
                return
        self.mon_step(m)

    def mon_fire(self, m, r):
        p = self.p
        self.sfx(r.get('snd', 'fire'), m.x, m.y)
        self.noise(m.x, m.y, 6)
        hp0 = p.hp
        if r['kind'] == 'shot':
            _, hit = self.blast(m, (p.x, p.y), r)
        else:
            hit = False
            for _ in range(r.get('shots', 1)):
                h = self.shot(m, (p.x, p.y), r)
                hit = hit or h == 'p' or (h == 'boom' and p.hp < hp0)
                if self.over:
                    break
        if hit or p.hp < hp0:
            self.msg("%s hits you!" % m.the(True), 'lred')
        elif p.invuln <= 0:
            self.msg("%s fires and misses." % m.the(True))

    def mon_step(self, m):
        lv, p = self.lv, self.p
        fly = bool(m.d.get('fly'))
        dm = self.dmap(fly)
        here = dm[m.y][m.x]
        if here < 0 and not fly:
            # knocked into acid or lava: wade out by the shortest way
            dm = self.dmap(True)
            here = dm[m.y][m.x]
        if here <= 0:
            return
        opts = []
        for dx, dy in DIRS8:
            nx, ny = m.x + dx, m.y + dy
            if not lv.inb(nx, ny):
                continue
            v = dm[ny][nx]
            if 0 < v <= here:
                opts.append((v, self.rng.random(), nx, ny))
        opts.sort()
        for v, _, nx, ny in opts:
            if v == here and self.rng.random() < 0.5:
                continue
            if lv.mon_at(nx, ny) or (nx, ny) in lv.barrels:
                continue
            if lv.t[ny][nx] == T_DOOR:
                lv.t[ny][nx] = T_ODOOR
                self.sfx('door', nx, ny)
                if (nx, ny) in lv.visible:
                    self.msg("A door swings open.")
                return
            m.x, m.y = nx, ny
            return

    def advance(self, cost):
        """The player spent `cost` ticks; let the rest of the world act."""
        lv, p = self.lv, self.p
        self.ticks += cost
        if p.berserk > 0:
            p.berserk = max(0, p.berserk - cost)
            if p.berserk == 0:
                self.msg("Your rage fades.")
        if p.invuln > 0:
            p.invuln = max(0, p.invuln - cost)
            if p.invuln == 0:
                self.msg("You feel vulnerable again.", 'orange')
        if p.running > 0:
            p.running = max(0, p.running - cost)
            if p.running == 0:
                p.tired = True
                self.msg("You are too tired to keep running.")
        t = lv.t[p.y][p.x]
        if t in (T_ACID, T_LAVA):
            dice = (1, 4, 1) if t == T_ACID else (2, 5, 2)
            dmg = max(1, int(roll(self.rng, dice) * cost / 100.0))
            self.msg("The %s burns you!" % ('acid' if t == T_ACID
                                            else 'lava'), 'orange')
            self.hurt_player(dmg, 'was dissolved in acid' if t == T_ACID
                             else 'was burned to ash in lava', armor=False)
        self._dm = {}
        for m in list(lv.mons):
            if self.over:
                break
            if m.hp <= 0:
                continue
            m.energy += cost * m.d['speed'] / 100.0
            n = 0
            while m.energy >= 100 and m.hp > 0 and not self.over and n < 4:
                m.energy -= 100
                n += 1
                self.mon_act(m)
                if m.hp > 0 and not m.d.get('fly'):
                    mt = lv.t[m.y][m.x]
                    if mt in (T_ACID, T_LAVA):
                        self.hurt_mon(m, 4 if mt == T_ACID else 9)
        self.update_fov()

    # -------------------------------------------------------------- report
    def mortem_lines(self):
        p = self.p
        lines = []
        lines.append("HELLBREACH %s - final report" % VERSION)
        lines.append("")
        lines.append("%s, level %d marine," % (p.name, p.level))
        lines.append("%s" % (self.cause or 'vanished'))
        lines.append("on floor %d (%s)." % (self.depth, self.lv.name))
        lines.append("")
        lines.append("Difficulty: %-10s Seed: %s" % (DIFFS[self.diff]['name'],
                                                     self.seed))
        lines.append("Turns: %-15d Score: %d" % (self.turn(), self.score()))
        lines.append("Health: %d/%d   Experience: %d" % (p.hp, p.maxhp,
                                                         p.xp))
        lines.append("")
        total = sum(p.kills.values())
        lines.append("Kills: %d" % total)
        ks = sorted(p.kills.items(), key=lambda kv: -kv[1])
        row = []
        for kind, n in ks:
            row.append("%d %s" % (n, MONS[kind]['name']))
            if len(row) == 3:
                lines.append("  " + ", ".join(row))
                row = []
        if row:
            lines.append("  " + ", ".join(row))
        lines.append("")
        if p.traits:
            tr = ["%s %d" % (TRAIT_BY_KEY[k][1], v)
                  for k, v in sorted(p.traits.items())]
            lines.append("Traits:")
            for i in range(0, len(tr), 3):
                lines.append("  " + ", ".join(tr[i:i + 3]))
        else:
            lines.append("Traits: none")
        lines.append("")
        lines.append("Weapon: %s" % (self.item_label(p.weapon) if p.weapon
                                     else "fists"))
        lines.append("Armor:  %s" % (self.item_label(p.armor) if p.armor
                                     else "none"))
        return lines


# --------------------------------------------------------------------------
# Front end
# --------------------------------------------------------------------------
VIKEYS = {'h': (-1, 0), 'j': (0, 1), 'k': (0, -1), 'l': (1, 0),
          'y': (-1, -1), 'u': (1, -1), 'b': (-1, 1), 'n': (1, 1)}
DIRKEYS = {
    pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1),
    pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0),
    pygame.K_KP8: (0, -1), pygame.K_KP2: (0, 1),
    pygame.K_KP4: (-1, 0), pygame.K_KP6: (1, 0),
    pygame.K_KP7: (-1, -1), pygame.K_KP9: (1, -1),
    pygame.K_KP1: (-1, 1), pygame.K_KP3: (1, 1),
    pygame.K_HOME: (-1, -1), pygame.K_PAGEUP: (1, -1),
    pygame.K_END: (-1, 1), pygame.K_PAGEDOWN: (1, 1),
}
KEYNAMES = {
    pygame.K_RETURN: 'enter', pygame.K_KP_ENTER: 'enter',
    pygame.K_ESCAPE: 'esc', pygame.K_TAB: 'tab',
    pygame.K_BACKSPACE: 'backspace', pygame.K_SPACE: 'space',
    pygame.K_F1: 'f1', pygame.K_KP5: 'wait',
}
# Xbox-style layout as pygame 2 reports it
PADKEYS = {0: 'pad_a', 1: 'pad_b', 2: 'pad_x', 3: 'pad_y', 4: 'pad_lb',
           5: 'pad_rb', 6: 'pad_back', 7: 'pad_start', 8: 'pad_ls'}
PAD_DPAD = {11: (0, -1), 12: (0, 1), 13: (-1, 0), 14: (1, 0)}

LOGO_FONT = {
    'H': ["#   #", "#   #", "#####", "#   #", "#   #"],
    'E': ["#####", "#    ", "#### ", "#    ", "#####"],
    'L': ["#    ", "#    ", "#    ", "#    ", "#####"],
    'B': ["#### ", "#   #", "#### ", "#   #", "#### "],
    'R': ["#### ", "#   #", "#### ", "#  # ", "#   #"],
    'A': [" ### ", "#   #", "#####", "#   #", "#   #"],
    'C': [" ####", "#    ", "#    ", "#    ", " ####"],
}
LOGO = [" ".join(LOGO_FONT[c][r] for c in "HELLBREACH") for r in range(5)]

HELP_LEFT = [
    ("MOVING", None),
    ("Arrows / numpad", "move, attack by walking"),
    ("y u b n", "diagonal moves"),
    ("Home PgUp End PgDn", "diagonal moves too"),
    ("h j k l", "vi-style movement"),
    ("Shift + direction", "run until something happens"),
    (". or Space", "wait one turn"),
    ("Tab", "sprint: faster, harder to hit"),
    ("", None),
    ("FIGHTING", None),
    ("f", "aim, then f or Enter to fire"),
    ("Tab (while aiming)", "next target"),
    ("r", "reload"),
    ("1-7", "ready a weapon by type"),
    ("[ ]  /  z", "cycle / previous weapon"),
    ("", None),
    ("THE WORLD", None),
    ("g or ,", "pick up, pull a lever"),
    ("> or Enter", "take stairs, pull a lever"),
    ("i", "inventory (Enter use, d drop)"),
    ("c  /  x", "close a door / look around"),
    ("@  m  S", "character / messages / save"),
    ("Esc  /  F11", "menu / fullscreen"),
]
HELP_RIGHT = [
    ("MOUSE", None),
    ("Left-click floor", "walk there"),
    ("Left-click enemy", "shoot it"),
    ("Left-click yourself", "use what you stand on"),
    ("Right-click", "describe"),
    ("", None),
    ("GAMEPAD (Xbox layout)", None),
    ("D-pad / stick", "move"),
    ("A  /  B", "aim+fire / wait, cancel"),
    ("X  /  Y", "reload / pick up, stairs"),
    ("LB RB", "cycle weapons or targets"),
    ("Back / Start", "inventory / menu"),
    ("Left stick click", "sprint"),
    ("", None),
    ("ON THE MAP", None),
    ("@ you   # wall", ". floor   > stairs"),
    ("+ door  / open door", "& lever   0 barrel"),
    ("~ acid  = lava", "both burn"),
    ("} gun   \\ blade", "| ammo   [ armor"),
    ("! medkit   ^ orb", "? gadget   \" weapon mod"),
    ("a-z A-Z", "things that want you dead"),
]


class App:
    def __init__(self, args):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
        except OSError:
            pass
        self.settings = dict(DEFAULT_SETTINGS)
        first_run = True
        try:
            with open(SETTINGS_PATH) as f:
                data = json.load(f)
            for k, v in DEFAULT_SETTINGS.items():
                if k in data and type(data[k]) == type(v):
                    self.settings[k] = data[k]
            first_run = False
        except Exception:
            pass
        s = self.settings
        pygame.display.init()
        pygame.font.init()
        try:
            pygame.joystick.init()
        except Exception:
            pass
        try:
            info = pygame.display.Info()
            self.desktop = (info.current_w, info.current_h)
        except Exception:
            self.desktop = (0, 0)
        if first_run and self.desktop[0] > 0:
            s['res'] = 0
            for i, (_, w, h) in enumerate(RESOLUTIONS):
                if w <= self.desktop[0] and h <= self.desktop[1] - 70:
                    s['res'] = i
        if args.res:
            for i, r in enumerate(RESOLUTIONS):
                if r[0] == args.res.lower():
                    s['res'] = i
        if args.fullscreen:
            s['fullscreen'] = True
        if args.windowed:
            s['fullscreen'] = False
        s['res'] = max(0, min(len(RESOLUTIONS) - 1, s['res']))
        s['theme'] = max(0, min(len(UI_THEMES) - 1, s['theme']))
        s['volume'] = max(0, min(10, s['volume']))
        s['diff'] = max(0, min(len(DIFFS) - 1, s['diff']))

        self.glyphs = {}
        self.rgbcache = {}
        self.bgcol = UI_THEMES[s['theme']][2]
        self.apply_display()
        pygame.display.set_caption("HELLBREACH")
        try:
            pygame.key.set_repeat(280, 70)
        except Exception:
            pass
        self.sfx = Sfx(not args.nosound)
        self.sfx.volume = s['volume'] / 10.0
        self.pads = []
        self.scan_pads()
        self.axes = {}
        self.stick = (0, 0)
        self.hat = (0, 0)
        self.pad_dir = None
        self.pad_timer = 0
        self.clock = pygame.time.Clock()
        self.queue = deque()
        self.cur = None
        self.flash = None
        self.shake = 0.0
        self.dirty = True
        self.running = True
        self.hover = None
        self.game = None
        self.notice = ''
        self.screens = [TitleScreen(self)]

    # ------------------------------------------------------------ display
    def apply_display(self):
        s = self.settings
        _, rw, rh = RESOLUTIONS[s['res']]
        try:
            if s['fullscreen']:
                self.screen = pygame.display.set_mode((0, 0),
                                                      pygame.FULLSCREEN)
            else:
                self.screen = pygame.display.set_mode((rw, rh))
        except pygame.error:
            s['fullscreen'] = False
            self.screen = pygame.display.set_mode((rw, rh))
        self.rw, self.rh = rw, rh
        self.canvas = pygame.Surface((rw, rh))
        self.cw = max(4, rw // GRID_W)
        self.ch = max(8, rh // GRID_H)
        self.ox = (rw - self.cw * GRID_W) // 2
        self.oy = (rh - self.ch * GRID_H) // 2
        self.font = self.find_font()
        self.glyphs.clear()
        sw, sh = self.screen.get_size()
        if (sw, sh) == (rw, rh):
            self.scaled = False
            self.dst = (0, 0, rw, rh)
        else:
            k = min(sw / float(rw), sh / float(rh))
            dw, dh = max(1, int(rw * k)), max(1, int(rh * k))
            self.scaled = True
            self.dst = ((sw - dw) // 2, (sh - dh) // 2, dw, dh)
        self.dirty = True

    def find_font(self):
        path = None
        for name in ('dejavusansmono', 'liberationmono', 'notosansmono',
                     'notomono', 'freemono', 'ubuntumono', 'couriernew',
                     'consolas', 'menlo', 'monospace'):
            try:
                path = pygame.font.match_font(name, bold=True) or \
                    pygame.font.match_font(name)
            except Exception:
                path = None
            if path:
                break
        size = int(self.ch * 1.2)
        font = None
        while size >= 6:
            try:
                font = pygame.font.Font(path, size)
            except Exception:
                path = None
                font = pygame.font.Font(None, size)
            w, h = font.size('M')
            if w <= self.cw and h <= self.ch:
                break
            size -= 1
        return font

    def set_theme(self):
        self.bgcol = UI_THEMES[self.settings['theme']][2]
        self.rgbcache.clear()
        self.glyphs.clear()
        self.dirty = True

    def save_settings(self):
        try:
            with open(SETTINGS_PATH, 'w') as f:
                json.dump(self.settings, f, indent=1)
        except Exception:
            pass

    def rgb(self, key, f=1.0):
        k = (key, f)
        c = self.rgbcache.get(k)
        if c is None:
            if key == 'bg':
                c = self.bgcol
            else:
                base = PAL[key] if isinstance(key, str) else key
                r, g, b = base[0] * f, base[1] * f, base[2] * f
                tint = UI_THEMES[self.settings['theme']][1]
                if tint:
                    lum = (0.30 * r + 0.59 * g + 0.11 * b) / 255.0
                    lum = min(1.0, (lum ** 0.8) * 1.1) if lum > 0 else 0.0
                    c = (int(tint[0] * lum), int(tint[1] * lum),
                         int(tint[2] * lum))
                else:
                    c = (int(r), int(g), int(b))
            self.rgbcache[k] = c
        return c

    def glyph(self, ch, rgb):
        k = (ch, rgb)
        g = self.glyphs.get(k)
        if g is None:
            try:
                surf = self.font.render(ch, True, rgb)
            except Exception:
                surf = self.font.render('?', True, rgb)
            g = (surf, (self.cw - surf.get_width()) // 2,
                 (self.ch - surf.get_height()) // 2)
            self.glyphs[k] = g
        return g

    def cell(self, x, y, ch, fg, bg=None, f=1.0):
        if x < 0 or y < 0 or x >= GRID_W or y >= GRID_H:
            return
        px = self.ox + x * self.cw
        py = self.oy + y * self.ch
        if bg is not None:
            self.canvas.fill(self.rgb(bg), (px, py, self.cw, self.ch))
        if ch != ' ':
            surf, gx, gy = self.glyph(ch, self.rgb(fg, f))
            self.canvas.blit(surf, (px + gx, py + gy))

    def put(self, x, y, text, fg='grey', bg=None, f=1.0):
        for i, ch in enumerate(text):
            self.cell(x + i, y, ch, fg, bg, f)

    def box(self, x, y, w, h, title=None):
        self.canvas.fill(self.rgb('bg'),
                         (self.ox + x * self.cw, self.oy + y * self.ch,
                          w * self.cw, h * self.ch))
        for i in range(w):
            self.cell(x + i, y, '-', 'dgrey')
            self.cell(x + i, y + h - 1, '-', 'dgrey')
        for j in range(h):
            self.cell(x, y + j, '|', 'dgrey')
            self.cell(x + w - 1, y + j, '|', 'dgrey')
        for cx, cy in ((x, y), (x + w - 1, y), (x, y + h - 1),
                       (x + w - 1, y + h - 1)):
            self.cell(cx, cy, '+', 'dgrey', 'bg')
        if title:
            t = " %s " % title
            self.put(x + (w - len(t)) // 2, y, t, 'gold', 'bg')

    def cell_at(self, pos):
        x, y = pos
        dx, dy, dw, dh = self.dst
        if self.scaled:
            x = (x - dx) * self.rw / float(dw)
            y = (y - dy) * self.rh / float(dh)
        cx = int((x - self.ox) // self.cw)
        cy = int((y - self.oy) // self.ch)
        if 0 <= cx < GRID_W and 0 <= cy < GRID_H:
            return (cx, cy)
        return None

    # ---------------------------------------------------------- game flow
    def busy(self):
        return self.cur is not None or bool(self.queue)

    def new_game(self, name, seed, diff):
        self.game = Game(name, seed, diff)
        self.queue.clear()
        self.cur = None
        self.screens = [PlayScreen(self)]
        self.save_game()
        self.dirty = True

    def has_save(self):
        return os.path.exists(SAVE_PATH)

    def save_game(self):
        g = self.game
        if not g or g.over:
            return False
        try:
            fx, g.fx = g.fx, []
            dm, g._dm = g._dm, {}
            tmp = SAVE_PATH + ".tmp"
            with open(tmp, 'wb') as f:
                pickle.dump({'v': SAVE_VERSION, 'game': g}, f, protocol=2)
            os.replace(tmp, SAVE_PATH)
            g.fx, g._dm = fx, dm
            return True
        except Exception:
            return False

    def load_game(self):
        try:
            with open(SAVE_PATH, 'rb') as f:
                data = pickle.load(f)
            if data.get('v') != SAVE_VERSION:
                raise ValueError("old save")
            self.game = data['game']
            self.game.fx = []
            self.game._dm = {}
            self.queue.clear()
            self.cur = None
            self.screens = [PlayScreen(self)]
            self.game.seq += 1
            self.game.msg("Welcome back, %s." % self.game.p.name, 'white')
            self.dirty = True
            return True
        except Exception:
            self.notice = "That save could not be loaded."
            return False

    def end_run(self):
        g = self.game
        try:
            os.remove(SAVE_PATH)
        except OSError:
            pass
        lines = g.mortem_lines()
        try:
            with open(MORTEM_PATH, 'a') as f:
                f.write(time.strftime("%Y-%m-%d %H:%M") + "\n")
                f.write("\n".join(lines) + "\n" + "-" * 60 + "\n")
        except Exception:
            pass
        self.screens.append(MortemScreen(self, lines))
        self.dirty = True

    def to_title(self):
        self.game = None
        self.queue.clear()
        self.cur = None
        self.flash = None
        self.shake = 0.0
        self.screens = [TitleScreen(self)]
        self.dirty = True

    def quit(self):
        self.save_game()
        self.running = False

    # -------------------------------------------------------------- input
    def scan_pads(self):
        self.pads = []
        try:
            for i in range(pygame.joystick.get_count()):
                j = pygame.joystick.Joystick(i)
                j.init()
                self.pads.append(j)
        except Exception:
            pass

    def toggle_fullscreen(self):
        self.settings['fullscreen'] = not self.settings['fullscreen']
        self.apply_display()
        self.save_settings()

    def skip_fx(self):
        """A key press cuts the current animations short."""
        if self.busy():
            for fx in self.queue:
                if fx[0] == 'snd' and fx[1] in ('levelup', 'win', 'stairs'):
                    self.sfx.play(fx[1], fx[2])
            self.queue.clear()
            self.cur = None

    def event(self, ev):
        top = self.screens[-1]
        t = ev.type
        if t == pygame.QUIT:
            self.quit()
        elif t == pygame.KEYDOWN:
            self.dirty = True
            if ev.key == pygame.K_F11:
                self.toggle_fullscreen()
                return
            self.skip_fx()
            shift = bool(ev.mod & pygame.KMOD_SHIFT)
            if ev.key in DIRKEYS:
                dx, dy = DIRKEYS[ev.key]
                top.on_dir(dx, dy, shift)
                return
            name = KEYNAMES.get(ev.key)
            if name is None:
                u = getattr(ev, 'unicode', '')
                if u and len(u) == 1 and u.isprintable():
                    name = u
            if name:
                top.on_key(name)
        elif t == pygame.MOUSEBUTTONDOWN:
            self.dirty = True
            c = self.cell_at(ev.pos)
            if c and ev.button in (1, 3):
                self.skip_fx()
                top.on_click(c[0], c[1], ev.button)
        elif t == pygame.MOUSEMOTION:
            c = self.cell_at(ev.pos)
            if c != self.hover:
                self.hover = c
                if c:
                    top.on_hover(c[0], c[1])
        elif t == pygame.JOYBUTTONDOWN:
            self.dirty = True
            self.skip_fx()
            if ev.button in PAD_DPAD:
                dx, dy = PAD_DPAD[ev.button]
                top.on_dir(dx, dy, False)
            elif ev.button in PADKEYS:
                top.on_key(PADKEYS[ev.button])
        elif t == pygame.JOYHATMOTION:
            x, y = ev.value
            self.hat = (x, -y)
            if self.hat != (0, 0):
                self.dirty = True
                self.skip_fx()
                top.on_dir(x, -y, False)
                self.pad_dir = self.hat
                self.pad_timer = 320
            else:
                self.pad_dir = None
        elif t == pygame.JOYAXISMOTION:
            if ev.axis in (0, 1):
                self.axes[ev.axis] = ev.value
                ax, ay = self.axes.get(0, 0.0), self.axes.get(1, 0.0)
                d = ((ax > 0.55) - (ax < -0.55), (ay > 0.55) - (ay < -0.55))
                if d != self.stick:
                    self.stick = d
                    if d != (0, 0):
                        # short delay so diagonals register cleanly
                        self.pad_dir = d
                        self.pad_timer = 90
                    elif self.hat == (0, 0):
                        self.pad_dir = None
        elif t in (getattr(pygame, 'JOYDEVICEADDED', -1),
                   getattr(pygame, 'JOYDEVICEREMOVED', -1)):
            self.scan_pads()

    # ------------------------------------------------------------- update
    def fx_duration(self, fx):
        k = fx[0]
        if k == 'proj':
            return len(fx[1]) * PROJ.get(fx[2], PROJ['bullet'])[2] + 25
        if k == 'cone':
            return 150
        if k == 'boom':
            return 260
        if k == 'hit':
            return 70
        return 0

    def update(self, dt):
        effects = self.settings['effects']
        if self.flash:
            self.flash[1] -= dt / 240.0
            if self.flash[1] <= 0:
                self.flash = None
            self.dirty = True
        if self.shake > 0:
            self.shake *= 0.85 ** (dt / 16.0)
            if self.shake < 0.6:
                self.shake = 0.0
            self.dirty = True
        budget = dt * (1.0 + len(self.queue) / 5.0)
        while True:
            if self.cur is None:
                if not self.queue:
                    break
                fx = self.queue.popleft()
                k = fx[0]
                if k == 'snd':
                    self.sfx.play(fx[1], fx[2])
                    continue
                if not effects:
                    continue
                if k == 'flash':
                    self.flash = [PAL[fx[1]], fx[2]]
                    continue
                if k == 'shake':
                    self.shake = max(self.shake, float(fx[1]))
                    continue
                dur = self.fx_duration(fx)
                if dur <= 0:
                    continue
                self.cur = [fx, 0.0, float(dur)]
            self.cur[1] += budget
            budget = 0
            self.dirty = True
            if self.cur[1] >= self.cur[2]:
                self.cur = None
                continue
            break
        if self.pad_dir:
            self.pad_timer -= dt
            if self.pad_timer <= 0:
                self.pad_timer = 150
                self.dirty = True
                self.skip_fx()
                self.screens[-1].on_dir(self.pad_dir[0], self.pad_dir[1],
                                        False)
        self.screens[-1].update(dt)

    def draw(self):
        self.canvas.fill(self.bgcol)
        start = 0
        for i, s in enumerate(self.screens):
            if s.opaque:
                start = i
        for s in self.screens[start:]:
            s.draw()
        if self.flash:
            c, a = self.flash
            a = max(0.0, min(1.0, a))
            self.canvas.fill((int(c[0] * a), int(c[1] * a), int(c[2] * a)),
                             special_flags=pygame.BLEND_RGB_ADD)
        ox = oy = 0
        if self.shake > 0:
            k = self.shake * self.ch / 16.0
            ox = int(random.uniform(-k, k))
            oy = int(random.uniform(-k, k) * 0.6)
        if self.scaled:
            dx, dy, dw, dh = self.dst
            try:
                surf = pygame.transform.smoothscale(self.canvas, (dw, dh))
            except Exception:
                surf = pygame.transform.scale(self.canvas, (dw, dh))
            self.screen.fill((0, 0, 0))
            self.screen.blit(surf, (dx + ox, dy + oy))
        else:
            if ox or oy:
                self.screen.fill((0, 0, 0))
            self.screen.blit(self.canvas, (ox, oy))
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = min(100, self.clock.tick(60))
            for ev in pygame.event.get():
                self.event(ev)
                if not self.running:
                    break
            if not self.running:
                break
            self.update(dt)
            if self.dirty:
                self.dirty = False
                self.draw()


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------
class Screen:
    opaque = False

    def __init__(self, app):
        self.app = app

    def on_key(self, k):
        pass

    def on_dir(self, dx, dy, shift):
        pass

    def on_click(self, x, y, button):
        pass

    def on_hover(self, x, y):
        pass

    def update(self, dt):
        pass

    def draw(self):
        pass

    def close(self):
        if self in self.app.screens:
            self.app.screens.remove(self)
        self.app.dirty = True


class MenuScreen(Screen):
    title = None
    width = 40
    top = None

    def __init__(self, app):
        Screen.__init__(self, app)
        self.sel = 0

    def items(self):
        return []

    def layout(self):
        its = self.items()
        h = len(its) + 4
        x = (GRID_W - self.width) // 2
        y = self.top if self.top is not None else (GRID_H - h) // 2
        return its, x, y, self.width, h

    def activate(self, delta):
        its = self.items()
        if its:
            self.sel %= len(its)
            its[self.sel][1](delta)
            self.app.sfx.play('blip')
            self.app.dirty = True

    def back(self):
        self.close()

    def on_dir(self, dx, dy, shift):
        n = len(self.items())
        if dy and n:
            self.sel = (self.sel + dy) % n
            self.app.sfx.play('blip', 0.6)
        elif dx:
            self.activate(dx)

    def on_key(self, k):
        if k in ('enter', 'space', 'pad_a'):
            self.activate(0)
        elif k in ('esc', 'pad_b'):
            self.back()

    def row_at(self, cx, cy):
        its, x, y, w, h = self.layout()
        row = cy - (y + 2)
        if x < cx < x + w - 1 and 0 <= row < len(its):
            return row
        return None

    def on_hover(self, cx, cy):
        row = self.row_at(cx, cy)
        if row is not None and row != self.sel:
            self.sel = row
            self.app.dirty = True

    def on_click(self, cx, cy, button):
        if button == 3:
            self.back()
            return
        row = self.row_at(cx, cy)
        if row is not None:
            self.sel = row
            self.activate(0)

    def draw(self):
        app = self.app
        its, x, y, w, h = self.layout()
        if its:
            self.sel %= len(its)
        app.box(x, y, w, h, self.title)
        for i, (label, _) in enumerate(its):
            if i == self.sel:
                app.put(x + 2, y + 2 + i, ">", 'gold')
                app.put(x + 4, y + 2 + i, label[:w - 6], 'white')
            else:
                app.put(x + 4, y + 2 + i, label[:w - 6], 'grey')


class TitleScreen(MenuScreen):
    opaque = True
    width = 30
    top = 15

    def items(self):
        app = self.app
        its = []
        if app.has_save():
            its.append(("Continue", lambda d: app.load_game()))
        its.append(("New game", lambda d: app.screens.append(
            NewGameScreen(app))))
        its.append(("Settings", lambda d: app.screens.append(
            SettingsScreen(app))))
        its.append(("How to play", lambda d: app.screens.append(
            HelpScreen(app))))
        its.append(("Quit", lambda d: app.quit()))
        return its

    def back(self):
        pass

    def draw(self):
        app = self.app
        x = (GRID_W - len(LOGO[0])) // 2
        cols = ['yellow', 'orange', 'orange', 'red', 'dred']
        for r, row in enumerate(LOGO):
            app.put(x, 4 + r, row, cols[r])
        tag = "a turn-based ASCII shooter. ten floors down. no way back."
        app.put((GRID_W - len(tag)) // 2, 11, tag, 'grey')
        MenuScreen.draw(self)
        if app.notice:
            app.put((GRID_W - len(app.notice)) // 2, 25, app.notice, 'lred')
        foot = "v%s   arrows + Enter, mouse or gamepad   F11 fullscreen" \
            % VERSION
        app.put((GRID_W - len(foot)) // 2, GRID_H - 2, foot, 'dgrey')


class NewGameScreen(Screen):
    def __init__(self, app):
        Screen.__init__(self, app)
        self.sel = 3
        self.name = app.settings.get('name', 'Marine')
        self.diff = app.settings.get('diff', 1)
        self.seed = ''

    def start(self):
        app = self.app
        name = self.name.strip() or 'Marine'
        seed = self.seed.strip() or str(random.randrange(10 ** 8))
        app.settings['name'] = name
        app.settings['diff'] = self.diff
        app.save_settings()
        app.notice = ''
        app.new_game(name, seed, self.diff)

    def on_dir(self, dx, dy, shift):
        if dy:
            self.sel = (self.sel + dy) % 4
        elif dx and self.sel == 1:
            self.diff = (self.diff + dx) % len(DIFFS)
        self.app.dirty = True

    def on_key(self, k):
        if k in ('esc', 'pad_b'):
            self.close()
        elif k == 'pad_a':
            self.start()
        elif k == 'enter':
            if self.sel == 3:
                self.start()
            else:
                self.sel += 1
        elif k == 'tab':
            self.sel = (self.sel + 1) % 4
        elif self.sel in (0, 2):
            attr = 'name' if self.sel == 0 else 'seed'
            cur = getattr(self, attr)
            if k == 'backspace':
                cur = cur[:-1]
            elif k == 'space' and self.sel == 0:
                cur += ' '
            elif len(k) == 1 and len(cur) < 16 and \
                    (k.isalnum() or k in "-_'."):
                cur += k
            setattr(self, attr, cur)
        elif k == 'space' and self.sel == 1:
            self.diff = (self.diff + 1) % len(DIFFS)
        elif k == 'space' and self.sel == 3:
            self.start()
        self.app.dirty = True

    def geom(self):
        w, h = 52, 13
        return (GRID_W - w) // 2, 12, w, h

    def on_click(self, cx, cy, button):
        x, y, w, h = self.geom()
        if button == 3:
            self.close()
            return
        row = (cy - (y + 2)) // 2
        if x < cx < x + w - 1 and 0 <= row < 4 and (cy - (y + 2)) % 2 == 0:
            if row == self.sel and row == 1:
                self.diff = (self.diff + 1) % len(DIFFS)
            elif row == 3:
                self.start()
                return
            self.sel = row
            self.app.dirty = True

    def draw(self):
        app = self.app
        x, y, w, h = self.geom()
        app.box(x, y, w, h, "New game")
        d = DIFFS[self.diff]
        rows = [
            ("Name", self.name + ("_" if self.sel == 0 else "")),
            ("Difficulty", "< %s >" % d['name']),
            ("Seed", (self.seed or ("" if self.sel == 2 else "(random)")) +
             ("_" if self.sel == 2 else "")),
            ("Start", ""),
        ]
        for i, (label, val) in enumerate(rows):
            yy = y + 2 + i * 2
            on = i == self.sel
            if on:
                app.put(x + 2, yy, ">", 'gold')
            app.put(x + 4, yy, label, 'white' if on else 'grey')
            app.put(x + 18, yy, val, 'yellow' if on else 'grey')
        hint = ["Type a name.", "Left/right to change. Monsters x%.1f, "
                "damage x%.2f." % (d['mons'], d['dmg']),
                "The same seed always builds the same floors.",
                "Enter to begin."][self.sel]
        app.put(x + 4, y + h - 3, hint[:w - 6], 'dgrey')


class SettingsScreen(MenuScreen):
    title = "Settings"
    width = 46

    def layout(self):
        its = self.items()
        return its, (GRID_W - self.width) // 2, 9, self.width, 16

    def draw(self):
        MenuScreen.draw(self)
        its, x, y, w, h = self.layout()
        self.app.put(x + 4, y + h - 3, "Left/right or Enter to change",
                     'dgrey')

    def items(self):
        app = self.app
        s = app.settings
        name, rw, rh = RESOLUTIONS[s['res']]
        return [
            ("Resolution     < %s  %dx%d >" % (name, rw, rh), self.f_res),
            ("Fullscreen     < %s >" % ("on" if s['fullscreen'] else "off"),
             self.f_full),
            ("Colour theme   < %s >" % UI_THEMES[s['theme']][0],
             self.f_theme),
            ("Sound volume   < %d >" % s['volume'], self.f_vol),
            ("Effects        < %s >" % ("on" if s['effects'] else "off"),
             self.f_fx),
            ("Back", lambda d: self.back()),
        ]

    def f_res(self, d):
        s = self.app.settings
        s['res'] = (s['res'] + (d or 1)) % len(RESOLUTIONS)
        self.app.apply_display()
        self.app.save_settings()

    def f_full(self, d):
        self.app.toggle_fullscreen()

    def f_theme(self, d):
        s = self.app.settings
        s['theme'] = (s['theme'] + (d or 1)) % len(UI_THEMES)
        self.app.set_theme()
        self.app.save_settings()

    def f_vol(self, d):
        s = self.app.settings
        if d == 0:
            s['volume'] = (s['volume'] + 1) % 11
        else:
            s['volume'] = max(0, min(10, s['volume'] + d))
        self.app.sfx.volume = s['volume'] / 10.0
        self.app.sfx.play('pistol')
        self.app.save_settings()

    def f_fx(self, d):
        s = self.app.settings
        s['effects'] = not s['effects']
        self.app.save_settings()


class HelpScreen(Screen):
    opaque = True

    def on_key(self, k):
        self.close()

    def on_click(self, x, y, button):
        self.close()

    def draw(self):
        app = self.app
        app.put(2, 1, "HELLBREACH - how to play", 'gold')
        app.put(2, 2, "Fight down ten floors and destroy the Warden. "
                "Guns need ammo and reloading; death is permanent.", 'grey')
        for col, block in ((2, HELP_LEFT), (56, HELP_RIGHT)):
            y = 4
            for key, text in block:
                if text is None:
                    app.put(col, y, key, 'orange')
                else:
                    app.put(col + 1, y, key, 'white')
                    app.put(col + 22, y, text, 'grey')
                y += 1
        app.put(2, GRID_H - 2, "Press any key to go back.", 'dgrey')


class PauseMenu(MenuScreen):
    title = "Paused"
    width = 36

    def __init__(self, app):
        MenuScreen.__init__(self, app)
        self.confirm = False

    def items(self):
        app = self.app
        return [
            ("Resume", lambda d: self.close()),
            ("Save game", self.f_save),
            ("Settings", lambda d: app.screens.append(SettingsScreen(app))),
            ("How to play", lambda d: app.screens.append(HelpScreen(app))),
            ("Save and quit to title", self.f_quit),
            ("Really abandon? Press again" if self.confirm
             else "Abandon this run", self.f_abandon),
        ]

    def f_save(self, d):
        g = self.app.game
        g.seq += 1
        g.msg("Game saved." if self.app.save_game() else
              "The game could not be saved!", 'white')
        self.close()

    def f_quit(self, d):
        self.app.save_game()
        self.app.to_title()

    def f_abandon(self, d):
        if not self.confirm:
            self.confirm = True
            return
        g = self.app.game
        g.over = True
        g.cause = 'gave up the fight'
        self.close()


class InventoryScreen(Screen):
    def __init__(self, app, play):
        Screen.__init__(self, app)
        self.play = play
        self.sel = 0

    def geom(self):
        w, h = 62, INV_MAX + 9
        return (MAP_W - w) // 2, 2, w, h

    def clamp(self):
        n = len(self.app.game.p.inv)
        self.sel = max(0, min(n - 1, self.sel)) if n else 0

    def on_dir(self, dx, dy, shift):
        n = len(self.app.game.p.inv)
        if dy and n:
            self.sel = (self.sel + dy) % n
            self.app.dirty = True

    def act(self, drop):
        g = self.app.game
        if not g.p.inv:
            return
        self.clamp()
        g.seq += 1
        cost = g.drop(self.sel) if drop else g.use(self.sel)
        if cost > 0:
            self.close()
            self.play.do(cost)
        else:
            self.play.after()
        self.clamp()

    def on_key(self, k):
        if k in ('esc', 'i', 'pad_b', 'pad_back'):
            self.close()
        elif k in ('enter', 'space', 'pad_a', 'e', 'u'):
            self.act(False)
        elif k in ('d', 'pad_x'):
            self.act(True)
        elif k in ('j', 'k'):
            self.on_dir(0, 1 if k == 'j' else -1, False)

    def on_click(self, cx, cy, button):
        x, y, w, h = self.geom()
        if button == 3 or not (x <= cx < x + w and y <= cy < y + h):
            self.close()
            return
        row = cy - (y + 5)
        if 0 <= row < len(self.app.game.p.inv):
            if row == self.sel:
                self.act(False)
            else:
                self.sel = row
                self.app.dirty = True

    def draw(self):
        app = self.app
        g = app.game
        p = g.p
        self.clamp()
        x, y, w, h = self.geom()
        app.box(x, y, w, h, "Inventory %d/%d" % (len(p.inv), INV_MAX))
        app.put(x + 2, y + 2, "In hand: ", 'grey')
        app.put(x + 11, y + 2, g.item_label(p.weapon) if p.weapon
                else "fists (1d3)", 'yellow')
        app.put(x + 2, y + 3, "Wearing: ", 'grey')
        app.put(x + 11, y + 3, g.item_label(p.armor) if p.armor else "none",
                'lblue' if p.armor else 'dgrey')
        if not p.inv:
            app.put(x + 4, y + 5, "(your pack is empty)", 'dgrey')
        for i, it in enumerate(p.inv):
            yy = y + 5 + i
            on = i == self.sel
            if on:
                app.put(x + 2, yy, ">", 'gold')
            app.cell(x + 4, yy, it.d['ch'], it.d['col'])
            app.put(x + 6, yy, g.item_label(it)[:w - 9],
                    'white' if on else 'grey')
        yy = y + h - 4
        if p.inv:
            it = p.inv[self.sel]
            ty = it.d['type']
            desc = it.d.get('desc')
            if ty == 'weapon':
                desc = "Slot %d. Mods fitted: %d of %d." % (
                    it.d['slot'], len(it.mods), g.mod_slots())
            elif ty == 'armor':
                desc = "Takes %d off every hit until it wears out." % \
                    it.d['prot']
            app.put(x + 2, yy, (desc or "")[:w - 4], 'lcyan')
        last = [t for s, t, c in g.log[-3:] if s == g.seq]
        if last:
            app.put(x + 2, yy + 1, last[-1][:w - 4], 'orange')
        app.put(x + 2, y + h - 2,
                "Enter use / ready     d drop     Esc close", 'dgrey')


class LevelUpScreen(MenuScreen):
    title = "Level up! Choose a trait"
    width = 78

    def items(self):
        g = self.app.game
        p = g.p
        its = []
        for key in g.available_traits():
            _, name, mx, desc, req = TRAIT_BY_KEY[key]
            label = "%-19s %d/%d  %s" % (name, p.tr(key), mx, desc)
            its.append((label, lambda d, key=key: self.pick(key)))
        if not its:
            its.append(("Tougher still: +5 maximum health",
                        lambda d: self.pick(None)))
        return its

    def layout(self):
        its = self.items()
        h = len(its) + 4
        return its, (MAP_W - self.width) // 2 + 1, max(1, (GRID_H - h) // 2), \
            self.width, h

    def pick(self, key):
        g = self.app.game
        if key is None:
            g.p.maxhp += 5
            g.p.hp += 5
            g.levelups = max(0, g.levelups - 1)
        else:
            g.take_trait(key)
        self.sel = 0
        if g.levelups <= 0:
            self.close()

    def back(self):
        pass

    def on_dir(self, dx, dy, shift):
        if dy:
            MenuScreen.on_dir(self, 0, dy, shift)

    def on_click(self, cx, cy, button):
        if button == 1:
            MenuScreen.on_click(self, cx, cy, button)


class TextScreen(Screen):
    """A box of read-only lines; any key closes it."""
    title = ""

    def lines(self):
        return []

    def on_key(self, k):
        self.close()

    def on_click(self, x, y, button):
        self.close()

    def draw(self):
        app = self.app
        lines = self.lines()
        w = min(GRID_W - 4, max([len(self.title) + 6] +
                                [len(t) + 4 for t, c in lines]))
        h = min(GRID_H - 2, len(lines) + 4)
        x, y = (MAP_W - w) // 2 + 1, (GRID_H - h) // 2
        x = max(1, x)
        app.box(x, y, w, h, self.title)
        for i, (t, c) in enumerate(lines[:h - 4]):
            app.put(x + 2, y + 2 + i, t[:w - 4], c)


class CharScreen(TextScreen):
    title = "Character"

    def lines(self):
        g = self.app.game
        p = g.p
        out = [
            ("%s, level %d marine" % (p.name, p.level), 'white'),
            ("Health %d/%d    Experience %d (next level at %d)" %
             (p.hp, p.maxhp, p.xp, xp_need(p.level + 1)), 'grey'),
            ("Floor %d of %d    Turn %d    Score %d" %
             (g.depth, MAX_DEPTH, g.turn(), g.score()), 'grey'),
            ("Difficulty %s    Seed %s" % (DIFFS[g.diff]['name'], g.seed),
             'grey'),
            ("", 'grey'),
            ("Traits", 'orange'),
        ]
        if not p.traits:
            out.append(("  none yet - gain a level to pick one", 'dgrey'))
        for key, name, mx, desc, req in TRAITS:
            if p.tr(key):
                out.append(("  %-19s %d/%d  %s" % (name, p.tr(key), mx,
                                                   desc), 'grey'))
        out.append(("", 'grey'))
        out.append(("Kills: %d" % sum(p.kills.values()), 'orange'))
        ks = sorted(p.kills.items(), key=lambda kv: -kv[1])
        for i in range(0, len(ks), 3):
            out.append(("  " + ", ".join("%d %s" % (n, MONS[k]['name'])
                                         for k, n in ks[i:i + 3]), 'grey'))
        return out


class LogScreen(TextScreen):
    title = "Messages"

    def lines(self):
        g = self.app.game
        out = []
        for s, t, c in g.log[-(GRID_H - 6):]:
            out.append((t, c))
        return out or [("Nothing has happened yet.", 'dgrey')]


class MortemScreen(Screen):
    opaque = True

    def __init__(self, app, lines):
        Screen.__init__(self, app)
        self.text = lines
        self.wait = 500

    def update(self, dt):
        if self.wait > 0:
            self.wait -= dt

    def done(self):
        if self.wait <= 0:
            self.app.to_title()

    def on_key(self, k):
        if k in ('enter', 'space', 'esc', 'pad_a', 'pad_b', 'pad_start'):
            self.done()

    def on_click(self, x, y, button):
        self.done()

    def draw(self):
        app = self.app
        g = app.game
        won = bool(g and g.won)
        head = "V I C T O R Y" if won else "Y O U   D I E D"
        app.put((GRID_W - len(head)) // 2, 2, head,
                'gold' if won else 'red')
        x = 24
        for i, t in enumerate(self.text[:GRID_H - 8]):
            app.put(x, 5 + i, t[:GRID_W - x - 2],
                    'white' if i == 2 else 'grey')
        foot = "This report was added to ~/.hellbreach/mortem.txt   " \
               "Press Enter."
        app.put((GRID_W - len(foot)) // 2, GRID_H - 2, foot, 'dgrey')


class PlayScreen(Screen):
    opaque = True

    def __init__(self, app):
        Screen.__init__(self, app)
        self.mode = None
        self.cursor = (0, 0)
        self.targets = []
        self.auto = None
        self.auto_t = 0
        self.phase = 0
        self.phase_t = 0
        self.done = False
        self.hover = None
        self.last_depth = app.game.depth

    @property
    def g(self):
        return self.app.game

    # ------------------------------------------------------------- actions
    def do(self, cost):
        g = self.g
        if cost and cost > 0 and not g.over:
            g.advance(int(cost))
        self.after()

    def after(self):
        app, g = self.app, self.g
        if g.fx:
            app.queue.extend(g.fx)
            del g.fx[:]
        if g.depth != self.last_depth:
            self.last_depth = g.depth
            self.auto = None
            app.save_game()
        self.hover = None
        app.dirty = True
        if g.levelups > 0 and not g.over and not any(
                isinstance(s, LevelUpScreen) for s in app.screens):
            app.screens.append(LevelUpScreen(app))

    def danger(self):
        lv = self.g.lv
        vis = lv.visible
        for m in lv.mons:
            if (m.x, m.y) in vis:
                return True
        return False

    def auto_step(self):
        g = self.g
        p, lv = g.p, g.lv
        a = self.auto
        if self.danger():
            self.auto = None
            return
        if a[0] == 'run':
            dx, dy = a[1], a[2]
            nx, ny = p.x + dx, p.y + dy
            if not g.can_walk(nx, ny):
                self.auto = None
                return
        else:
            path = a[1]
            if not path:
                self.auto = None
                return
            nx, ny = path[0]
            dx, dy = nx - p.x, ny - p.y
            if max(abs(dx), abs(dy)) != 1 or not g.can_walk(nx, ny):
                self.auto = None
                return
        hp0 = p.hp
        depth0 = g.depth
        g.seq += 1
        cost = g.move(dx, dy)
        self.do(cost)
        if cost <= 0 or p.hp < hp0 or g.over or g.depth != depth0:
            self.auto = None
            return
        pos = (p.x, p.y)
        if a[0] == 'path':
            if pos == (nx, ny):
                a[1].pop(0)
            if not a[1]:
                self.auto = None
        elif pos in lv.items or pos in lv.levers or \
                lv.t[p.y][p.x] in (T_STAIRS, T_ODOOR):
            self.auto = None
        if self.danger():
            self.auto = None

    def start_target(self):
        g = self.g
        p = g.p
        g.seq += 1
        if not p.weapon or p.weapon.d.get('melee'):
            g.msg("You have no gun in your hands.")
            self.after()
            return
        self.targets = g.visible_mons()
        cur = None
        if g.last_target is not None and g.last_target in self.targets:
            cur = g.last_target
        elif self.targets:
            cur = self.targets[0]
        self.cursor = (cur.x, cur.y) if cur else (p.x, p.y)
        self.mode = 'target'
        self.app.dirty = True

    def cycle_target(self, step):
        if not self.targets:
            return
        idx = -1
        for i, m in enumerate(self.targets):
            if (m.x, m.y) == self.cursor:
                idx = i
        m = self.targets[(idx + step) % len(self.targets)]
        self.cursor = (m.x, m.y)
        self.app.dirty = True

    def confirm_target(self):
        g = self.g
        if self.mode != 'target':
            self.mode = None
            return
        self.mode = None
        cx, cy = self.cursor
        g.seq += 1
        if (cx, cy) == (g.p.x, g.p.y):
            g.msg("Pick a target first: move the cursor, then fire.")
            self.after()
            return
        m = g.lv.mon_at(cx, cy)
        if m is not None and (cx, cy) in g.lv.visible:
            g.last_target = m
        self.do(g.fire(cx, cy))

    def key_target(self, k):
        if k in ('esc', 'pad_b'):
            self.mode = None
        elif k in VIKEYS:
            self.on_dir(VIKEYS[k][0], VIKEYS[k][1], False)
        elif k in ('tab', ']', 'pad_rb', '+', '='):
            self.cycle_target(1)
        elif k in ('[', 'pad_lb', '-'):
            self.cycle_target(-1)
        elif k in ('f', 'enter', 'space', 'pad_a', 'x'):
            self.confirm_target()
        self.app.dirty = True

    def close_door(self):
        g = self.g
        opts = g.open_doors_near()
        if len(opts) == 1:
            self.do(g.close_door(opts[0][0], opts[0][1]))
        elif not opts:
            g.msg("There is no open door next to you.")
            self.after()
        else:
            self.mode = 'close'
            self.app.dirty = True

    # --------------------------------------------------------------- input
    def on_key(self, k):
        app, g = self.app, self.g
        if g.over:
            return
        self.auto = None
        if self.mode in ('target', 'look'):
            self.key_target(k)
            return
        if self.mode == 'close':
            self.mode = None
            if k in VIKEYS:
                self.on_dir(VIKEYS[k][0], VIKEYS[k][1], False)
                return
            app.dirty = True
            return
        if k in VIKEYS:
            self.on_dir(VIKEYS[k][0], VIKEYS[k][1], False)
            return
        if len(k) == 1 and k.lower() in VIKEYS and k.isupper():
            dx, dy = VIKEYS[k.lower()]
            self.on_dir(dx, dy, True)
            return
        if k in ('f', 'pad_a'):
            self.start_target()
            return
        g.seq += 1
        if k in ('r', 'pad_x'):
            self.do(g.reload())
        elif k in ('g', ',', 'pad_y'):
            self.do(g.pickup())
        elif k in ('>', 'enter'):
            self.do(g.interact())
        elif k in ('.', 'space', 'wait', 's', 'pad_b'):
            self.do(g.wait())
        elif k in ('i', 'pad_back'):
            app.screens.append(InventoryScreen(app, self))
        elif k in ('tab', 'pad_ls'):
            self.do(g.toggle_run())
        elif k == 'c':
            self.close_door()
        elif k == 'x':
            self.cursor = (g.p.x, g.p.y)
            self.mode = 'look'
        elif k == 'z':
            self.do(g.swap_prev())
        elif k in ('[', 'pad_lb'):
            self.do(g.cycle_weapon(-1))
        elif k in (']', 'pad_rb'):
            self.do(g.cycle_weapon(1))
        elif len(k) == 1 and k in '1234567':
            self.do(g.quick(int(k)))
        elif k in ('@', 'C'):
            app.screens.append(CharScreen(app))
        elif k in ('m', 'M', 'P'):
            app.screens.append(LogScreen(app))
        elif k in ('?', 'f1'):
            app.screens.append(HelpScreen(app))
        elif k == 'S':
            g.msg("Game saved." if app.save_game() else
                  "The game could not be saved!", 'white')
        elif k in ('esc', 'pad_start'):
            app.screens.append(PauseMenu(app))
        app.dirty = True

    def on_dir(self, dx, dy, shift):
        g = self.g
        if g.over:
            return
        if self.mode in ('target', 'look'):
            cx = max(0, min(MAP_W - 1, self.cursor[0] + dx))
            cy = max(0, min(MAP_H - 1, self.cursor[1] + dy))
            self.cursor = (cx, cy)
            self.app.dirty = True
            return
        g.seq += 1
        if self.mode == 'close':
            self.mode = None
            self.do(g.close_door(dx, dy))
            return
        self.auto = None
        if shift:
            self.auto = ['run', dx, dy]
            self.auto_t = 0
            return
        self.do(g.move(dx, dy))

    def on_hover(self, cx, cy):
        mx, my = cx - MAP_OX, cy - MAP_OY
        if 0 <= mx < MAP_W and 0 <= my < MAP_H:
            self.hover = (mx, my)
        else:
            self.hover = None
        self.app.dirty = True

    def on_click(self, cx, cy, button):
        g = self.g
        if g.over:
            return
        mx, my = cx - MAP_OX, cy - MAP_OY
        if not (0 <= mx < MAP_W and 0 <= my < MAP_H):
            return
        if self.mode in ('target', 'look'):
            if button == 3:
                self.mode = None
            elif self.mode == 'target':
                self.cursor = (mx, my)
                self.confirm_target()
            else:
                self.cursor = (mx, my)
            self.app.dirty = True
            return
        self.mode = None
        self.auto = None
        g.seq += 1
        p, lv = g.p, g.lv
        if button == 3:
            g.msg(g.describe(mx, my), 'lcyan')
            self.after()
            return
        if (mx, my) == (p.x, p.y):
            self.do(g.interact())
            return
        vis = (mx, my) in lv.visible
        m = lv.mon_at(mx, my) if vis else None
        gun = p.weapon and not p.weapon.d.get('melee')
        adjacent = cheb(mx, my, p.x, p.y) == 1
        if m:
            if adjacent and not gun:
                self.do(g.move(mx - p.x, my - p.y))
            elif gun:
                g.last_target = m
                self.do(g.fire(mx, my))
            else:
                g.msg("You need a gun to hit that from here.")
                self.after()
            return
        if vis and (mx, my) in lv.barrels and gun and not adjacent:
            self.do(g.fire(mx, my))
            return
        if adjacent:
            self.do(g.move(mx - p.x, my - p.y))
            return
        path = g.path_to(mx, my)
        if path:
            self.auto = ['path', path]
            self.auto_t = 0
        else:
            g.msg("You can't see a safe way there.")
            self.after()

    def update(self, dt):
        app, g = self.app, self.g
        top = app.screens[-1] is self
        self.phase_t += dt
        if self.phase_t >= 350:
            self.phase_t = 0
            self.phase += 1
            if top and app.settings['effects']:
                app.dirty = True
        if g.over:
            self.auto = None
            if not self.done and not app.busy():
                self.done = True
                self.after()
                app.end_run()
            return
        if self.auto and top:
            self.auto_t -= dt
            if self.auto_t <= 0:
                self.auto_t = 35
                self.auto_step()

    # ------------------------------------------------------------- drawing
    def glyph_at(self, x, y, monpos):
        """(char, colour, brightness) for a map cell, None if unknown."""
        lv = self.g.lv
        pos = (x, y)
        vis = pos in lv.visible
        if not vis and not lv.seen[y][x]:
            return None
        if vis:
            m = monpos.get(pos)
            if m is not None:
                return m.d['ch'], m.d['col'], 1.0
        f = 1.0 if vis else 0.42
        if pos in lv.barrels:
            return '0', BARRELS[lv.barrels[pos]][1], f
        its = lv.items.get(pos)
        if its:
            d = its[-1].d
            return d['ch'], d['col'], f
        if pos in lv.levers:
            return '&', 'gold', f
        dec = lv.decor.get(pos)
        if dec:
            return dec[0], dec[1], f * 0.7
        tt = lv.t[y][x]
        style = STYLES[lv.style]
        if tt == T_WALL:
            return '#', style[0], f
        if tt == T_FLOOR:
            return '.', ('dred' if pos in lv.blood else style[1]), f
        if tt == T_DOOR:
            return '+', 'orange', f
        if tt == T_ODOOR:
            return '/', 'orange', f
        if tt == T_STAIRS:
            return '>', 'white', f
        shimmer = self.shimmer and (x * 7 + y * 13 + self.phase) % 5 == 0
        if tt == T_ACID:
            return '~', ('lgreen' if shimmer else 'green'), f
        return '=', ('yellow' if shimmer else 'orange'), f

    def draw_map(self, monpos):
        app, g = self.app, self.g
        lv, p = g.lv, g.p
        cell = app.cell
        sense = p.tr('sense')
        self.shimmer = app.settings['effects']
        glyph_at = self.glyph_at
        for y in range(MAP_H):
            sy = MAP_OY + y
            for x in range(MAP_W):
                r = glyph_at(x, y, monpos)
                if r is not None:
                    cell(MAP_OX + x, sy, r[0], r[1], None, r[2])
                elif sense:
                    pos = (x, y)
                    if pos in lv.items:
                        d = lv.items[pos][-1].d
                        cell(MAP_OX + x, sy, d['ch'], d['col'], None, 0.5)
                    elif lv.t[y][x] == T_STAIRS:
                        cell(MAP_OX + x, sy, '>', 'white', None, 0.6)
                    elif pos in lv.levers:
                        cell(MAP_OX + x, sy, '&', 'gold', None, 0.5)
        if sense >= 2:
            for m in lv.mons:
                if (m.x, m.y) not in lv.visible and \
                        cheb(m.x, m.y, p.x, p.y) <= 14:
                    cell(MAP_OX + m.x, MAP_OY + m.y, m.d['ch'], m.d['col'],
                         'bg', 0.5)
        pc = 'gold' if p.invuln > 0 else ('lred' if p.berserk > 0
                                         else 'white')
        cell(MAP_OX + p.x, MAP_OY + p.y, '@', pc, 'bg')

    def draw_cursor(self, monpos):
        app, g = self.app, self.g
        lv, p = g.lv, g.p
        cx, cy = self.cursor
        if self.mode == 'target':
            for x, y in line(p.x, p.y, cx, cy)[:-1]:
                if lv.solid(x, y):
                    app.cell(MAP_OX + x, MAP_OY + y, 'x', 'lred', 'bg')
                    break
                if (x, y) not in monpos:
                    app.cell(MAP_OX + x, MAP_OY + y, '*', 'yellow', 'bg',
                             0.55)
        r = self.glyph_at(cx, cy, monpos)
        if (cx, cy) == (p.x, p.y):
            r = ('@', 'white', 1.0)
        app.cell(MAP_OX + cx, MAP_OY + cy, r[0] if r else ' ', 'black',
                 'yellow' if self.mode == 'target' else 'lcyan')

    def draw_fx(self):
        app = self.app
        if not app.cur:
            return
        fx, t, dur = app.cur
        vis = self.g.lv.visible
        k = fx[0]
        u = t / dur
        if k == 'proj':
            path, kind, src = fx[1], fx[2], fx[3]
            ch, col, _ = PROJ.get(kind, PROJ['bullet'])
            if kind == 'bullet':
                dx, dy = path[-1][0] - src[0], path[-1][1] - src[1]
                if abs(dx) > 2 * abs(dy):
                    ch = '-'
                elif abs(dy) > 2 * abs(dx):
                    ch = '|'
                else:
                    ch = '\\' if dx * dy > 0 else '/'
            i = min(len(path) - 1, int(u * len(path)))
            for j, f in ((i - 2, 0.3), (i - 1, 0.55), (i, 1.0)):
                if j >= 0 and path[j] in vis:
                    app.cell(MAP_OX + path[j][0], MAP_OY + path[j][1], ch,
                             col, 'bg', f)
        elif k == 'cone':
            cells = fx[1]
            far = max(c[2] for c in cells)
            front = u * (far + 2.5)
            for x, y, d in cells:
                if front - 2.5 < d <= front and (x, y) in vis:
                    app.cell(MAP_OX + x, MAP_OY + y,
                             '*' if (x + y) % 2 else ':', 'yellow', 'bg',
                             max(0.35, 1.0 - d / (far + 4.0)))
        elif k == 'boom':
            cells, col = fx[1], fx[2]
            far = max(c[2] for c in cells) if cells else 0
            front = u * (far + 2.0)
            for x, y, d in cells:
                if d > front or (x, y) not in vis:
                    continue
                age = front - d
                if u > 0.75 and d < far - 1.5:
                    continue
                c = 'white' if age < 0.7 else ('yellow' if age < 1.4
                                               else col)
                app.cell(MAP_OX + x, MAP_OY + y, '*', c, 'bg',
                         1.0 if u < 0.7 else 0.6)
        elif k == 'hit':
            x, y = fx[1]
            if (x, y) in vis:
                app.cell(MAP_OX + x, MAP_OY + y, '*', fx[2], 'bg')

    def draw_top(self):
        app, g = self.app, self.g
        lv, p = g.lv, g.p
        lim = MAP_W - 2
        if self.mode == 'target':
            cx, cy = self.cursor
            m = lv.mon_at(cx, cy) if (cx, cy) in lv.visible else None
            if m:
                ws = g.wstats(p.weapon)
                s = "Aim: %s (%s)" % (m.name, m.state())
                if ws.get('kind') != 'shot' and not ws.get('radius'):
                    s += " %d%% to hit" % g.hit_chance(
                        ws, cheb(p.x, p.y, cx, cy))
            else:
                s = "Aim: " + g.describe(cx, cy)
            s = s[:lim - 38] + "   [f/Enter fire  Tab next  Esc cancel]"
            app.put(1, 0, s[:lim], 'yellow')
            return
        if self.mode == 'look':
            s = "Look: " + g.describe(self.cursor[0], self.cursor[1])
            app.put(1, 0, (s[:lim - 12] + "  [Esc done]")[:lim], 'lcyan')
            return
        if self.mode == 'close':
            app.put(1, 0, "Close the door in which direction?", 'yellow')
            return
        msgs = []
        for entry in reversed(g.log):
            if entry[0] != g.seq:
                break
            msgs.append(entry)
        msgs.reverse()
        if msgs:
            x = 1
            for _, text, col in msgs:
                room = lim - x
                if room <= 3:
                    break
                if len(text) > room:
                    text = text[:room - 3] + "..."
                app.put(x, 0, text, col)
                x += len(text) + 1
        elif self.hover:
            app.put(1, 0, g.describe(self.hover[0], self.hover[1])[:lim],
                    'lcyan', None, 0.8)

    def hp_colour(self):
        p = self.g.p
        if p.hp > p.maxhp:
            return 'lgreen'
        r = p.hp / float(p.maxhp)
        return 'white' if r > 0.5 else ('yellow' if r > 0.25 else 'lred')

    def draw_status(self):
        app, g = self.app, self.g
        lv, p = g.lv, g.p
        y = MAP_OY + MAP_H
        app.put(1, y, p.name[:17], 'white')
        app.put(19, y, "Lv %d" % p.level, 'grey')
        app.put(28, y, "Armor :", 'grey')
        app.put(36, y, g.item_label(p.armor) if p.armor else "none",
                'lblue' if p.armor else 'dgrey')
        app.put(1, y + 1, "Health:", 'grey')
        app.put(9, y + 1, "%d/%d" % (p.hp, p.maxhp), self.hp_colour())
        lo, hi = xp_need(p.level), xp_need(p.level + 1)
        app.put(19, y + 1, "Exp %d%%" % (100 * (p.xp - lo) // (hi - lo)),
                'grey')
        app.put(28, y + 1, "Weapon:", 'grey')
        app.put(36, y + 1, (g.item_label(p.weapon) if p.weapon
                            else "fists (1d3)")[:42], 'yellow')
        if p.running > 0:
            app.put(1, y + 2, "running (%d)" % (p.running // 100 + 1),
                    'yellow')
        elif p.tired:
            app.put(1, y + 2, "tired", 'orange')
        else:
            app.put(1, y + 2, "cautious", 'grey')
        x = 19
        if p.berserk > 0:
            s = "BERSERK %d" % (p.berserk // 100 + 1)
            app.put(x, y + 2, s, 'lred')
            x += len(s) + 2
        if p.invuln > 0:
            s = "INVULNERABLE %d" % (p.invuln // 100 + 1)
            app.put(x, y + 2, s, 'white')
            x += len(s) + 2
        if lv.t[p.y][p.x] in (T_ACID, T_LAVA):
            app.put(x, y + 2, "BURNING", 'orange')
        s = "? help   %s  floor %d" % (lv.name, g.depth)
        app.put(MAP_W - 1 - len(s), y + 2, s, 'dgrey')

    def bar(self, x, y, label, val, mx, col):
        app = self.app
        n = 14
        fill = 0 if mx <= 0 else max(0, min(n, int(round(n * val /
                                                         float(mx)))))
        if val > 0 and fill == 0:
            fill = 1
        app.put(x, y, label, 'grey')
        app.cell(x + 3, y, '[', 'dgrey')
        app.put(x + 4, y, '#' * fill, col)
        app.put(x + 4 + fill, y, '-' * (n - fill), 'dgrey')
        app.cell(x + 4 + n, y, ']', 'dgrey')

    def draw_panel(self):
        app, g = self.app, self.g
        lv, p = g.lv, g.p
        X = PANEL_X
        W = PANEL_W - 1
        for y in range(GRID_H):
            app.cell(PANEL_X - 1, y, '|', 'dgrey', None, 0.7)
        app.put(X, 0, "HELLBREACH", 'red')
        app.put(X + 11, 0, DIFFS[g.diff]['name'][:W - 11], 'dgrey')
        app.put(X, 1, lv.name[:W], 'white')
        app.put(X, 2, ("Floor %d/%d  Turn %d" % (g.depth, MAX_DEPTH,
                                                 g.turn()))[:W], 'grey')
        self.bar(X, 4, "HP", p.hp, p.maxhp, self.hp_colour())
        app.put(X + 20, 4, "%d" % p.hp, self.hp_colour())
        lo, hi = xp_need(p.level), xp_need(p.level + 1)
        self.bar(X, 5, "XP", p.xp - lo, hi - lo, 'gold')
        app.put(X + 20, 5, "L%d" % p.level, 'gold')
        cur = p.weapon.d.get('ammo') if p.weapon else None
        for i, k in enumerate(AMMO_ORDER):
            col = 'white' if k == cur else ('grey' if p.ammo[k] else 'dgrey')
            app.put(X, 7 + i, "%-8s %3d/%d" % (AMMO_NAME[k], p.ammo[k],
                                               g.ammo_cap(k)), col)
            if k == cur:
                app.put(X + 18, 7 + i, "<", 'yellow')
        small = sum(1 for it in p.inv if it.kind == 'smed')
        large = sum(1 for it in p.inv if it.kind == 'lmed')
        app.put(X, 12, ("Medkits %d small %d large" % (small, large))[:W],
                'lred' if small + large else 'dgrey')
        app.put(X, 14, "In sight", 'orange')
        ms = g.visible_mons()
        if not ms:
            app.put(X, 15, "nothing hostile", 'dgrey')
        for i, m in enumerate(ms[:5]):
            if i == 4 and len(ms) > 5:
                app.put(X, 15 + i, "...and %d more" % (len(ms) - 4), 'grey')
                break
            app.cell(X, 15 + i, m.d['ch'], m.d['col'])
            app.put(X + 2, 15 + i, m.name[:13], 'grey')
            st = m.state()
            app.put(X + 16, 15 + i, st[:W - 16],
                    {'unhurt': 'dgrey', 'scratched': 'grey',
                     'wounded': 'yellow', 'dying': 'lred'}[st])
        app.put(X, 21, "Messages", 'orange')
        rows = []
        for seq, text, col in g.log[-12:]:
            for ln in textwrap.wrap(text, W) or ['']:
                rows.append((ln, col, seq == g.seq))
        rows = rows[-(GRID_H - 22):]
        for i, (ln, col, new) in enumerate(rows):
            app.put(X, 22 + i, ln, col, None, 1.0 if new else 0.5)

    def draw(self):
        g = self.g
        monpos = {(m.x, m.y): m for m in g.lv.mons}
        self.draw_map(monpos)
        if self.mode in ('target', 'look'):
            self.draw_cursor(monpos)
        self.draw_fx()
        self.draw_top()
        self.draw_status()
        self.draw_panel()


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="HELLBREACH - an ASCII "
                                 "roguelike shooter")
    ap.add_argument('--res', help="480p, 720p, 900p, 1080p or 1440p")
    ap.add_argument('--fullscreen', action='store_true')
    ap.add_argument('--windowed', action='store_true')
    ap.add_argument('--nosound', action='store_true')
    args = ap.parse_args()
    app = App(args)
    try:
        app.run()
    finally:
        app.save_settings()
        pygame.quit()


if __name__ == '__main__':
    main()
