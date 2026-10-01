#!/usr/bin/env python3
"""
CRAWL  --  a Dungeon Crawler Carl-flavored ASCII roguelike (fan-made homage)

Run:   python3 dcc_crawl.py     (needs a terminal of at least 80x24)
Needs: Python 3 with the standard 'curses' module (default on Linux).

You are Carl: no pants, one cat, one very bad day.
Three floors. Each floor is a fresh dungeon with a collapse timer,
a boss, loot boxes, achievements and a very rude System AI.
"""
import curses
import os
import random
import textwrap
from collections import deque

MAP_W, MAP_H = 60, 19
SIDE_X = 62
DIRS8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

WEAPONS = [("Bare Fists", 4), ("Rusty Spoon", 5), ("Sharpened Shiv", 6),
           ("Nail Bat", 8), ("Goblin Cleaver", 10), ("Crowbar of Regret", 12)]
ARMORS = [("Boxers (only)", 0), ("Pants", 1), ("Cargo Pants", 2),
          ("Motorcycle Jacket", 3), ("Riot Vest", 4), ("Skullplate", 5)]

# col: 1 red 2 green 3 yellow 4 blue 5 magenta 6 cyan 7 white
MON = {
    'roach':  dict(name="Giant Cockroach", ch='r', hp=6, atk=3, df=0, xp=5, col=3, fast=True),
    'goblin': dict(name="Goblin", ch='g', hp=9, atk=4, df=0, xp=9, col=2),
    'thug':   dict(name="Skull Empire Thug", ch='S', hp=18, atk=6, df=1, xp=16, col=1),
    'gunner': dict(name="Skull Empire Gunner", ch='k', hp=11, atk=5, df=0, xp=14, col=5, ranged=True),
    'raptor': dict(name="Velociraptor", ch='R', hp=22, atk=8, df=1, xp=26, col=6, fast=True),
    'goblin_boss': dict(name="Gurgle, Goblin Warlord", ch='G', hp=55, atk=7, df=1, xp=70, col=2, boss=True),
    'skull_boss':  dict(name="Skullface Sal", ch='K', hp=85, atk=9, df=2, xp=120, col=1, boss=True),
    'final_boss':  dict(name="Gristlegut, Floor Warden", ch='W', hp=130, atk=12, df=3, xp=250, col=5, boss=True),
}

FLOORS = [
    dict(name="FLOOR 1: THE BASEMENT OF BAD IDEAS", wall=4, floorc=7, timer=450, rooms=8, mobs=9,
         pool=['roach', 'roach', 'goblin', 'goblin', 'goblin'], boss='goblin_boss', minion='goblin',
         boxes=['Silver', 'Bronze', 'Bronze'], potions=2, bombs=2,
         intro="Welcome to Floor 1, Crawler. Dress code: boxers. Dress code is not negotiable."),
    dict(name="FLOOR 2: THE SKULL EMPIRE QUARRY", wall=3, floorc=3, timer=500, rooms=9, mobs=12,
         pool=['goblin', 'thug', 'thug', 'gunner', 'roach'], boss='skull_boss', minion='thug',
         boxes=['Silver', 'Bronze', 'Gold'], potions=2, bombs=2,
         intro="Floor 2. The audience has noticed you. Please try not to die boringly."),
    dict(name="FLOOR 3: THE WARDEN'S OUTSKIRTS", wall=1, floorc=5, timer=550, rooms=10, mobs=14,
         pool=['thug', 'gunner', 'raptor', 'raptor', 'gunner'], boss='final_boss', minion='raptor',
         boxes=['Gold', 'Silver', 'Bronze'], potions=3, bombs=3,
         intro="Floor 3. The Warden is waiting. The viewers have placed bets. Against you."),
]

AI_KILL = [
    "Kill logged. The audience is mildly awake.",
    "Another one down. Your hair looks terrible, by the way.",
    "Excellent. Please try to enjoy it less.",
    "Viewership ticks up. Your self-respect ticks down.",
    "Noted. Someone out there is making a clip of that.",
]
AI_LOW = [
    "Your health is low. Viewership is up 400%. Coincidence? No.",
    "Bleeding stylishly, I see. The fans are placing bets.",
]
TIPS = [
    "Bombs hurt. Don't stand next to your own explosion, kid.",
    "Donut's Torch has a cooldown. Let her cook.",
    "The floor WILL collapse. Watch that timer, Crawler.",
    "Loot boxes are lies wrapped in cardboard. Open them anyway.",
    "Skip the boss and you skip the loot. Your call.",
    "Bronze, Silver, Gold, Platinum. In order of 'worth it'.",
    "Pants. Get some pants. Silver boxes are your friend.",
]

# key: (name, text, reward box tier or None)
ACH = {
    'blood': ("First Blood", "You killed something. The fans say: 'eh, okay.'", None),
    'box':   ("Box Opener", "You opened your first loot box. It was a little sad.", None),
    'pants': ("Pants!", "You are now wearing pants. Society welcomes you back.", 'Bronze'),
    'boom':  ("Compensated Anarchist", "Two or more enemies, one explosion. Beautiful.", 'Bronze'),
    'donut': ("Good Girl", "Donut got a kill. She will never let you forget it.", 'Bronze'),
    'lvl5':  ("Level 5 Crawler", "You are marginally less doomed than before.", 'Silver'),
    'skip':  ("Coward's Shortcut", "You skipped a boss. The audience boos. Delicious.", None),
    'boss0': ("Warlord Down", "You killed Gurgle. The goblins are filing a complaint.", 'Silver'),
    'boss1': ("Skullface Sal-vaged", "Sal is dead. The Skull Empire sends its regrets.", 'Silver'),
    'boss2': ("Warden Defenestrated", "Gristlegut is dead. Somebody get the mop.", 'Gold'),
    'ouch':  ("Cutting It Close", "You survived at 3 HP or less. Ratings spike.", None),
}


def cheb(x1, y1, x2, y2):
    return max(abs(x1 - x2), abs(y1 - y2))


class Game:
    def __init__(self):
        self.floor = 0
        self.level = 1
        self.xp = 0
        self.maxhp = 30
        self.hp = 30
        self.wi = 0
        self.ar = 0
        self.potions = 1
        self.bombs = 2
        self.viewers = 1337
        self.fans = 0
        self.kills = 0
        self.boxes = 0
        self.turn = 0
        self.donut_kills = 0
        self.ach = set()
        self.pending = []
        self.log = []
        self.ai = ""
        self.state = 'play'
        self.cause = ''
        self.donut = dict(x=0, y=0, hp=25, maxhp=25, down=0, cd=0)
        self.monsters = []
        self.items = {}
        self.vis = set()
        self.boss_dead = False
        self.mord_used = False
        self.low_warned = False

    # ------------------------------------------------------------ messages
    def msg(self, t):
        self.log.append(t)
        self.log = self.log[-60:]

    def say(self, t):
        self.ai = t
        self.msg("SYSTEM: " + t)

    # ------------------------------------------------------------ stats
    def atk(self):
        return WEAPONS[self.wi][1] + (self.level - 1) // 2

    def defense(self):
        return ARMORS[self.ar][1] + (self.level - 1) // 3

    def gain_xp(self, n):
        self.xp += n
        while self.xp >= self.level * 20:
            self.xp -= self.level * 20
            self.level += 1
            self.maxhp += 6
            self.hp = min(self.maxhp, self.hp + 12)
            d = self.donut
            d['maxhp'] += 3
            d['hp'] = min(d['maxhp'], d['hp'] + 6)
            self.say("LEVEL UP! You are level %d. The System congratulates you, grudgingly." % self.level)
            if self.level >= 5:
                self.achieve('lvl5')

    def achieve(self, k):
        if k in self.ach:
            return
        self.ach.add(k)
        name, txt, reward = ACH[k]
        self.say("NEW ACHIEVEMENT: %s! %s" % (name, txt))
        self.fans += random.randint(5, 40)
        self.viewers += random.randint(500, 5000)
        if reward:
            self.pending.append(reward)

    # ------------------------------------------------------------ map
    def gen_map(self, nrooms):
        g = [['#'] * MAP_W for _ in range(MAP_H)]
        rooms = []
        for _ in range(300):
            if len(rooms) >= nrooms:
                break
            w, h = random.randint(5, 11), random.randint(3, 6)
            x = random.randint(1, MAP_W - w - 1)
            y = random.randint(1, MAP_H - h - 1)
            if any(x <= rx + rw + 1 and rx <= x + w + 1 and y <= ry + rh + 1 and ry <= y + h + 1
                   for rx, ry, rw, rh in rooms):
                continue
            rooms.append((x, y, w, h))
        rooms.sort()
        for x, y, w, h in rooms:
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    g[yy][xx] = '.'

        def ctr(r):
            return r[0] + r[2] // 2, r[1] + r[3] // 2

        for a, b in zip(rooms, rooms[1:]):
            ax, ay = ctr(a)
            bx, by = ctr(b)
            if random.random() < 0.5:
                for x in range(min(ax, bx), max(ax, bx) + 1):
                    g[ay][x] = '.'
                for y in range(min(ay, by), max(ay, by) + 1):
                    g[y][bx] = '.'
            else:
                for y in range(min(ay, by), max(ay, by) + 1):
                    g[y][ax] = '.'
                for x in range(min(ax, bx), max(ax, bx) + 1):
                    g[by][x] = '.'
        self.grid = g
        self.rooms = rooms
        self.ctr = ctr

    def new_floor(self, n):
        self.floor = n
        cfg = FLOORS[n]
        while True:
            self.gen_map(cfg['rooms'])
            if len(self.rooms) >= 5:
                break
        self.seen = [[False] * MAP_W for _ in range(MAP_H)]
        self.monsters = []
        self.items = {}
        self.boss_dead = False
        self.mord_used = False
        self.low_warned = False
        self.timer = cfg['timer']
        sx, sy = self.ctr(self.rooms[0])
        self.px, self.py = sx, sy
        self.donut['x'], self.donut['y'] = sx + 1, sy
        self.mord = (sx + 2, sy)
        lx, ly = self.ctr(self.rooms[-1])
        self.stairs = (lx, ly)
        # boss
        self.monsters.append(self.make_mon(cfg['boss'], lx + 1, ly))
        # regular monsters
        mid = self.rooms[1:-1]
        for _ in range(cfg['mobs']):
            spot = self.rand_tile(random.choice(mid))
            if spot:
                self.monsters.append(self.make_mon(random.choice(cfg['pool']), *spot))
        # items
        for tier in cfg['boxes']:
            self.place_item(('box', tier))
        for _ in range(cfg['potions']):
            self.place_item(('potion',))
        for _ in range(cfg['bombs']):
            self.place_item(('bomb',))
        if self.donut['down'] > 0:
            self.donut['down'] = 0
            self.donut['hp'] = self.donut['maxhp'] // 2
        self.compute_fov()
        self.say(cfg['intro'])
        self.msg("You entered " + cfg['name'] + ".")

    def make_mon(self, key, x, y):
        t = MON[key]
        m = dict(t)
        m.update(x=x, y=y, maxhp=t['hp'], awake=False, key=key)
        return m

    def mon_at(self, x, y):
        for m in self.monsters:
            if m['x'] == x and m['y'] == y:
                return m
        return None

    def free(self, x, y):
        if not (0 <= x < MAP_W and 0 <= y < MAP_H) or self.grid[y][x] == '#':
            return False
        if (x, y) == (self.px, self.py) or (x, y) == (self.donut['x'], self.donut['y']):
            return False
        if (x, y) == self.mord or self.mon_at(x, y):
            return False
        return True

    def rand_tile(self, room):
        x, y, w, h = room
        for _ in range(40):
            px, py = random.randint(x, x + w - 1), random.randint(y, y + h - 1)
            if self.free(px, py) and (px, py) not in self.items and (px, py) != self.stairs:
                return px, py
        return None

    def place_item(self, item):
        for _ in range(20):
            spot = self.rand_tile(random.choice(self.rooms[1:]))
            if spot:
                self.items[spot] = item
                return

    # ------------------------------------------------------------ vision
    def los(self, x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = x0, y0
        while (x, y) != (x1, y1):
            if (x, y) != (x0, y0) and self.grid[y][x] == '#':
                return False
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
        return True

    def compute_fov(self):
        vis = {(self.px, self.py)}
        for y in range(max(0, self.py - 7), min(MAP_H, self.py + 8)):
            for x in range(max(0, self.px - 14), min(MAP_W, self.px + 15)):
                if (x - self.px) ** 2 + 4 * (y - self.py) ** 2 <= 196 and \
                        self.los(self.px, self.py, x, y):
                    vis.add((x, y))
        self.vis = vis
        for x, y in vis:
            self.seen[y][x] = True

    def dmap(self, sx, sy):
        d = {(sx, sy): 0}
        q = deque([(sx, sy)])
        while q:
            x, y = q.popleft()
            v = d[(x, y)]
            if v >= 45:
                continue
            for dx, dy in DIRS8:
                nx, ny = x + dx, y + dy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and self.grid[ny][nx] != '#' \
                        and (nx, ny) not in d:
                    d[(nx, ny)] = v + 1
                    q.append((nx, ny))
        return d

    def step_toward(self, e, dm):
        best, bd = None, dm.get((e['x'], e['y']), 999)
        for dx, dy in DIRS8:
            nx, ny = e['x'] + dx, e['y'] + dy
            v = dm.get((nx, ny))
            if v is not None and v < bd and self.free(nx, ny):
                best, bd = (nx, ny), v
        if best:
            e['x'], e['y'] = best

    # ------------------------------------------------------------ loot
    def roll_tier(self):
        r = random.random()
        t = [(0.7, 0.95), (0.45, 0.85), (0.25, 0.7)][self.floor]
        return 'Bronze' if r < t[0] else ('Silver' if r < t[1] else 'Gold')

    def open_box(self, tier):
        self.boxes += 1
        self.say("You open a %s LOOT BOX!" % tier.upper())
        if self.boxes == 1:
            self.achieve('box')
        gifts = []
        if tier == 'Bronze':
            r = random.random()
            if r < 0.45:
                n = random.randint(1, 2)
                self.potions += n
                gifts.append("%d Healing Potion%s" % (n, "s" if n > 1 else ""))
            elif r < 0.9:
                n = random.randint(1, 2)
                self.bombs += n
                gifts.append("%d Homemade Bomb%s" % (n, "s" if n > 1 else ""))
            else:
                self.hp = min(self.maxhp, self.hp + 10)
                gifts.append("a suspiciously old donut (+10 HP)")
        else:
            if self.ar == 0:
                self.ar = 1
                gifts.append("A PAIR OF PANTS")
                self.potions += 1
                gifts.append("a Healing Potion")
                self.achieve('pants')
            else:
                cap = 3 if tier == 'Silver' else 5
                opts = ['p', 'b']
                if self.wi < cap:
                    opts.append('w')
                if self.ar < cap:
                    opts.append('a')
                pick = random.choice(opts + (['w', 'a'] if tier != 'Silver' else []))
                if pick == 'w' and self.wi < cap:
                    self.wi = min(cap, self.wi + (2 if tier != 'Silver' and random.random() < .4 else 1))
                    gifts.append("weapon: " + WEAPONS[self.wi][0])
                elif pick == 'a' and self.ar < cap:
                    self.ar = min(cap, self.ar + 1)
                    gifts.append("armor: " + ARMORS[self.ar][0])
                elif pick == 'b':
                    self.bombs += 2
                    gifts.append("2 Homemade Bombs")
                else:
                    self.potions += 2
                    gifts.append("2 Healing Potions")
            if tier in ('Gold', 'Platinum'):
                self.potions += 1
                self.bombs += 1
                gifts.append("a potion and a bomb")
            if tier == 'Platinum':
                self.hp = self.maxhp
                self.donut['hp'] = self.donut['maxhp']
                gifts.append("FULL HEAL")
        self.msg("Inside: " + ", ".join(gifts) + ".")

    def process_pending(self):
        while self.pending:
            self.open_box(self.pending.pop(0))

    # ------------------------------------------------------------ combat
    def kill_mon(self, m, by='you'):
        if m not in self.monsters:
            return
        self.monsters.remove(m)
        self.kills += 1
        self.gain_xp(m['xp'])
        self.viewers += random.randint(100, 900)
        self.msg("%s dies." % m['name'])
        if self.kills == 1:
            self.achieve('blood')
        if by == 'donut':
            self.donut_kills += 1
            self.msg("Donut: 'Mine! That one was MINE!'")
            self.achieve('donut')
        pos = (m['x'], m['y'])
        if m.get('boss'):
            self.boss_dead = True
            self.items[pos] = ('box', 'Platinum' if self.floor == 2 else 'Gold')
            self.say("%s is dead! A shiny loot box clatters to the floor." % m['name'])
            self.achieve('boss%d' % self.floor)
        else:
            r = random.random()
            if pos not in self.items and pos != self.stairs:
                if r < 0.18:
                    self.items[pos] = ('box', self.roll_tier())
                elif r < 0.30:
                    self.items[pos] = ('potion',)
            if random.random() < 0.2:
                self.say(random.choice(AI_KILL))

    def attack(self, m):
        dmg = max(1, self.atk() - m['df'] + random.randint(-1, 1))
        crit = random.random() < 0.1
        if crit:
            dmg *= 2
        m['hp'] -= dmg
        m['awake'] = True
        self.msg("You %s the %s for %d.%s" % ("pummel" if crit else "hit", m['name'], dmg,
                                               " CRIT!" if crit else ""))
        if m['hp'] <= 0:
            self.kill_mon(m, 'you')

    def hurt_player(self, dmg, src):
        self.hp -= dmg
        if 0 < self.hp <= 3:
            self.achieve('ouch')
        if self.hp <= 0:
            self.state = 'dead'
            self.cause = src
        elif self.hp <= 8 and not self.low_warned:
            self.low_warned = True
            self.say(random.choice(AI_LOW))

    def hurt_donut(self, dmg, src):
        d = self.donut
        d['hp'] -= dmg
        if d['hp'] <= 0:
            d['hp'] = 0
            d['down'] = 20
            self.say("Princess Donut is DOWN! She says it is SO unfair.")

    def throw_bomb(self):
        if self.bombs <= 0:
            self.msg("You have no bombs. Sad Carl.")
            return False
        targets = [m for m in self.monsters if (m['x'], m['y']) in self.vis
                   and cheb(self.px, self.py, m['x'], m['y']) <= 8]
        if not targets:
            self.msg("Nothing in sight to blow up.")
            return False
        t = min(targets, key=lambda m: cheb(self.px, self.py, m['x'], m['y']))
        if cheb(self.px, self.py, t['x'], t['y']) < 3:
            self.msg("Too close! You would blow yourself up.")
            return False
        self.bombs -= 1
        self.msg("You hurl a homemade bomb at the %s. KABOOM!" % t['name'])
        killed = 0
        for m in list(self.monsters):
            if cheb(m['x'], m['y'], t['x'], t['y']) <= 1:
                m['hp'] -= max(1, 15 - m['df'])
                m['awake'] = True
                if m['hp'] <= 0:
                    killed += 1
                    self.kill_mon(m, 'bomb')
        d = self.donut
        if d['down'] == 0 and cheb(d['x'], d['y'], t['x'], t['y']) <= 1:
            self.msg("Donut gets singed. She will remember this.")
            self.hurt_donut(8, 'bomb')
        if killed >= 2:
            self.achieve('boom')
        return True

    def drink(self):
        if self.potions <= 0:
            self.msg("No potions left.")
            return False
        if self.hp >= self.maxhp:
            self.msg("You are already at full health.")
            return False
        self.potions -= 1
        self.hp = min(self.maxhp, self.hp + 18)
        self.msg("You drink a potion. Tastes like regret and cherry. +18 HP")
        return True

    # ------------------------------------------------------------ actions
    def try_move(self, dx, dy):
        nx, ny = self.px + dx, self.py + dy
        if not (0 <= nx < MAP_W and 0 <= ny < MAP_H) or self.grid[ny][nx] == '#':
            return False
        m = self.mon_at(nx, ny)
        if m:
            self.attack(m)
            return True
        if (nx, ny) == self.mord:
            self.talk()
            return True
        d = self.donut
        if (nx, ny) == (d['x'], d['y']):
            d['x'], d['y'] = self.px, self.py
        self.px, self.py = nx, ny
        item = self.items.pop((nx, ny), None)
        if item:
            if item[0] == 'box':
                self.open_box(item[1])
            elif item[0] == 'potion':
                self.potions += 1
                self.msg("You pick up a Healing Potion.")
            else:
                self.bombs += 1
                self.msg("You pick up a Homemade Bomb. Boom.")
        if (nx, ny) == self.stairs:
            extra = "" if self.boss_dead else " (The boss still lives. Skipping it means no loot.)"
            self.msg("The stairwell! Press > to descend." + extra)
        self.compute_fov()
        return True

    def talk(self):
        d = self.donut
        if not self.mord_used:
            self.mord_used = True
            self.hp = self.maxhp
            d['hp'] = d['maxhp']
            d['down'] = 0
            self.say("Mordecai patches you and Donut up. Free, this once per floor.")
        else:
            self.msg("Mordecai: '%s'" % random.choice(TIPS))

    def descend(self):
        if (self.px, self.py) != self.stairs:
            self.msg("There are no stairs here.")
            return False
        if not self.boss_dead:
            self.achieve('skip')
        if self.floor >= 2:
            self.state = 'won'
            return False
        self.say("Descending. Donut leaps into your arms, outraged about the draft.")
        self.new_floor(self.floor + 1)
        return False

    # ------------------------------------------------------------ turn
    def end_turn(self):
        self.turn += 1
        self.timer -= 1
        self.viewers = max(0, self.viewers + random.randint(-40, 160))
        if self.timer in (150, 75, 30, 10):
            self.say("FLOOR COLLAPSE IN %d TURNS. Please panic responsibly." % self.timer)
        if self.timer <= 0:
            self.state = 'dead'
            self.cause = "the collapsing floor"
            return
        if self.turn % 8 == 0 and self.hp < self.maxhp:
            self.hp += 1
        d = self.donut
        if self.turn % 12 == 0 and d['hp'] < d['maxhp'] and d['down'] == 0:
            d['hp'] += 1
        self.donut_turn()
        self.monsters_turn()
        self.process_pending()
        self.compute_fov()

    def donut_turn(self):
        d = self.donut
        if d['down'] > 0:
            d['down'] -= 1
            if d['down'] == 0:
                d['hp'] = max(1, d['maxhp'] // 2)
                self.msg("Princess Donut is back on her paws, and furious.")
            return
        if d['cd'] > 0:
            d['cd'] -= 1
        best, bd = None, 99
        for m in self.monsters:
            dist = cheb(d['x'], d['y'], m['x'], m['y'])
            if dist <= 6 and dist < bd and self.los(d['x'], d['y'], m['x'], m['y']):
                best, bd = m, dist
        if best:
            if d['cd'] == 0:
                dmg = 5 + self.level
                best['hp'] -= dmg
                best['awake'] = True
                d['cd'] = 3
                self.msg("Donut hurls a sparkly Torch at the %s for %d!" % (best['name'], dmg))
                if best['hp'] <= 0:
                    self.kill_mon(best, 'donut')
                return
            if bd == 1:
                dmg = 2 + self.level // 2
                best['hp'] -= dmg
                best['awake'] = True
                self.msg("Donut claws the %s for %d." % (best['name'], dmg))
                if best['hp'] <= 0:
                    self.kill_mon(best, 'donut')
                return
        if cheb(d['x'], d['y'], self.px, self.py) > 3:
            self.step_toward(d, self.dmap(self.px, self.py))

    def monsters_turn(self):
        d = self.donut
        dm_p = self.dmap(self.px, self.py)
        dm_d = self.dmap(d['x'], d['y']) if d['down'] == 0 else None
        for m in list(self.monsters):
            if m not in self.monsters or self.state != 'play':
                continue
            if m.get('boss') and not m.get('rage') and m['hp'] <= m['maxhp'] // 2:
                m['rage'] = True
                m['atk'] += 1
                self.say("%s roars and calls for backup!" % m['name'])
                n = 0
                for dx, dy in DIRS8:
                    x, y = m['x'] + dx, m['y'] + dy
                    if n < 2 and self.free(x, y):
                        mn = self.make_mon(FLOORS[self.floor]['minion'], x, y)
                        mn['awake'] = True
                        self.monsters.append(mn)
                        n += 1
            for step in range(2 if m.get('fast') else 1):
                if not m['awake']:
                    near = cheb(m['x'], m['y'], self.px, self.py)
                    if near <= (10 if m.get('boss') else 8) and \
                            self.los(m['x'], m['y'], self.px, self.py):
                        m['awake'] = True
                    else:
                        break
                tp = cheb(m['x'], m['y'], self.px, self.py)
                td = cheb(m['x'], m['y'], d['x'], d['y']) if dm_d is not None and d['down'] == 0 else 999
                at_donut = td < tp
                dist = td if at_donut else tp
                tx, ty = (d['x'], d['y']) if at_donut else (self.px, self.py)
                if m.get('ranged') and 2 <= dist <= 6 and self.los(m['x'], m['y'], tx, ty) \
                        and random.random() < 0.7:
                    dmg_base = m['atk']
                    if at_donut:
                        self.msg("The %s shoots at Donut!" % m['name'])
                        self.hurt_donut(max(1, dmg_base - 1 + random.randint(-1, 1)), m['name'])
                    else:
                        dmg = max(1, dmg_base - self.defense() + random.randint(-1, 1))
                        self.msg("The %s shoots you for %d." % (m['name'], dmg))
                        self.hurt_player(dmg, m['name'])
                    break
                if dist <= 1:
                    if step == 1:
                        break
                    if at_donut:
                        dmg = max(1, m['atk'] - 1 + random.randint(-1, 1))
                        self.msg("The %s bites Donut for %d!" % (m['name'], dmg))
                        self.hurt_donut(dmg, m['name'])
                    else:
                        dmg = max(1, m['atk'] - self.defense() + random.randint(-1, 1))
                        self.msg("The %s hits you for %d." % (m['name'], dmg))
                        self.hurt_player(dmg, m['name'])
                    break
                self.step_toward(m, dm_d if at_donut else dm_p)

    # ------------------------------------------------------------ input
    def handle(self, k):
        if k in KEYMAP:
            return self.try_move(*KEYMAP[k])
        if k in (ord('.'), ord(' '), ord('5')):
            return True
        if k == ord('p'):
            return self.drink()
        if k == ord('b'):
            return self.throw_bomb()
        if k in (ord('>'), 10, 13, curses.KEY_ENTER):
            return self.descend()
        return False


KEYMAP = {}
for _keys, _d in [((curses.KEY_UP, ord('w'), ord('k'), ord('8')), (0, -1)),
                  ((curses.KEY_DOWN, ord('s'), ord('j'), ord('2')), (0, 1)),
                  ((curses.KEY_LEFT, ord('a'), ord('h'), ord('4')), (-1, 0)),
                  ((curses.KEY_RIGHT, ord('d'), ord('l'), ord('6')), (1, 0)),
                  ((ord('q'), ord('7')), (-1, -1)), ((ord('e'), ord('9')), (1, -1)),
                  ((ord('z'), ord('1')), (-1, 1)), ((ord('c'), ord('3')), (1, 1))]:
    for _k in _keys:
        KEYMAP[_k] = _d


# ====================================================================== UI
def put(scr, y, x, s, attr=0):
    try:
        scr.addstr(y, x, s, attr)
    except curses.error:
        pass


def cp(n):
    return curses.color_pair(n)


def bar(cur, mx, width=12):
    filled = 0 if mx <= 0 else max(0, min(width, int(round(width * cur / mx))))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def draw(scr, g):
    scr.erase()
    put(scr, 0, 0, g.ai[:79], cp(6) | curses.A_BOLD)
    cfg = FLOORS[g.floor]
    wallc, floorc = cp(cfg['wall']), cp(cfg['floorc'])
    for y in range(MAP_H):
        for x in range(MAP_W):
            if not g.seen[y][x]:
                continue
            v = (x, y) in g.vis
            if g.grid[y][x] == '#':
                ch, at = '#', wallc | (curses.A_BOLD if v else curses.A_DIM)
            else:
                ch, at = '.', floorc | (0 if v else curses.A_DIM)
            put(scr, 1 + y, x, ch, at)
    sx, sy = g.stairs
    if g.seen[sy][sx]:
        put(scr, 1 + sy, sx, '>', cp(3) | curses.A_BOLD)
    for (x, y), it in g.items.items():
        if g.seen[y][x]:
            if it[0] == 'box':
                col = {'Bronze': 3, 'Silver': 7, 'Gold': 3, 'Platinum': 6}[it[1]]
                put(scr, 1 + y, x, '&', cp(col) | curses.A_BOLD)
            elif it[0] == 'potion':
                put(scr, 1 + y, x, '!', cp(5) | curses.A_BOLD)
            else:
                put(scr, 1 + y, x, 'o', cp(1) | curses.A_BOLD)
    for m in g.monsters:
        if (m['x'], m['y']) in g.vis:
            put(scr, 1 + m['y'], m['x'], m['ch'], cp(m['col']) | curses.A_BOLD)
    if g.mord in g.vis:
        put(scr, 1 + g.mord[1], g.mord[0], 'M', cp(5) | curses.A_BOLD)
    d = g.donut
    if (d['x'], d['y']) in g.vis:
        put(scr, 1 + d['y'], d['x'], 'f', (cp(5) if d['down'] == 0 else cp(7) | curses.A_DIM) | curses.A_BOLD)
    put(scr, 1 + g.py, g.px, '@', cp(7) | curses.A_BOLD)

    side = [
        ("CRAWLER CARL", cp(3) | curses.A_BOLD),
        ("Comp. Anarchist", 0),
        ("Lv %d XP %d/%d" % (g.level, g.xp, g.level * 20), 0),
        ("HP %d/%d" % (max(0, g.hp), g.maxhp), cp(1 if g.hp <= 8 else 2)),
        (bar(g.hp, g.maxhp), cp(1 if g.hp <= 8 else 2)),
        ("ATK %d  DEF %d" % (g.atk(), g.defense()), 0),
        (WEAPONS[g.wi][0], 0),
        (ARMORS[g.ar][0], 0),
        ("Potions %d  (p)" % g.potions, cp(5)),
        ("Bombs   %d  (b)" % g.bombs, cp(1)),
        ("", 0),
        ("PRINCESS DONUT", cp(5) | curses.A_BOLD),
        ("DOWN (%d)" % d['down'] if d['down'] else "HP %d/%d" % (d['hp'], d['maxhp']), 0),
        (bar(d['hp'], d['maxhp']), cp(5)),
        ("", 0),
        ("FLOOR %d/3" % (g.floor + 1), cp(6) | curses.A_BOLD),
        ("Collapse: %d" % g.timer, cp(1) | curses.A_BOLD if g.timer < 80 else 0),
        ("Viewers %s" % format(g.viewers, ","), 0),
        ("Fans %d Kills %d" % (g.fans, g.kills), 0),
    ]
    for i, (t, a) in enumerate(side):
        put(scr, 1 + i, SIDE_X, t[:17], a)

    lines = []
    for m in g.log[-12:]:
        lines += textwrap.wrap(m, 78) or [""]
    for i, t in enumerate(lines[-4:]):
        put(scr, 20 + i, 0, t[:79])
    scr.refresh()


def screen(scr, lines, attr=0):
    scr.erase()
    h, w = scr.getmaxyx()
    top = max(0, (h - len(lines)) // 2)
    for i, t in enumerate(lines):
        put(scr, top + i, max(0, (w - len(t)) // 2), t, attr)
    scr.refresh()
    while True:
        k = scr.getch()
        if k != curses.KEY_RESIZE:
            return k


INTRO = [
    "===========================================",
    "    D U N G E O N   C R A W L E R   C A R L",
    "          ~ an ASCII fan homage ~",
    "===========================================",
    "",
    "   /\\_/\\",
    "  ( o.o )   <- Princess Donut (very important)",
    "   > ^ <",
    "",
    "The world ended. The dungeon began.",
    "You are Carl. You are wearing boxers. That is all.",
    "A rude AI is narrating your doom for a live audience.",
    "Descend three floors before each one collapses.",
    "Kill the boss for loot, or skip it and be mocked.",
    "",
    "Move: arrows / wasd / hjkl   Diagonals: q e z c",
    "Attack: walk into enemies    Wait: space",
    "p drink potion   b throw bomb   > descend   Q quit",
    "",
    "Legend: @ you  f Donut  M Mordecai  & loot box  ! potion",
    "        o bomb  > stairs  letters = things that want you dead",
    "",
    "[ press any key ]",
]


def end_screen(scr, g, won):
    score = g.kills * 25 + g.level * 100 + (g.floor + 1) * 200 + len(g.ach) * 50 + g.fans + (1000 if won else 0)
    if won:
        art = [
            "  FLOOR 3 CLEARED!  ",
            "",
            "  The stairwell to Floor 4 grinds open.",
            "  The System is... almost impressed.",
            "  Donut demands a victory snack.",
            "",
            "          TO BE CONTINUED",
        ]
        attr = cp(3) | curses.A_BOLD
    else:
        art = [
            "        _______",
            "       /       \\",
            "      /  R.I.P  \\",
            "     |   CARL    |",
            "     |           |",
            "     |  Floor %d  |" % (g.floor + 1),
            "    ^^^^^^^^^^^^^^^^^",
            "",
            "Killed by: %s" % g.cause,
            "The audience boos. Then buys merch.",
        ]
        attr = cp(1) | curses.A_BOLD
    art += ["",
            "Level %d | Kills %d | Achievements %d/%d" % (g.level, g.kills, len(g.ach), len(ACH)),
            "Viewers %s | Fans %d" % (format(g.viewers, ","), g.fans),
            "FINAL SCORE: %d" % score,
            "",
            "[ press any key ]"]
    screen(scr, art, attr)


def game_loop(scr):
    curses.curs_set(0)
    scr.keypad(True)
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        cols = [curses.COLOR_RED, curses.COLOR_GREEN, curses.COLOR_YELLOW, curses.COLOR_BLUE,
                curses.COLOR_MAGENTA, curses.COLOR_CYAN, curses.COLOR_WHITE]
        for i, c in enumerate(cols, 1):
            curses.init_pair(i, c, bg)
    h, w = scr.getmaxyx()
    if h < 24 or w < 80:
        raise SystemExit("Terminal too small: need at least 80x24 (have %dx%d)." % (w, h))
    screen(scr, INTRO, cp(6))
    g = Game()
    g.new_floor(0)
    while g.state == 'play':
        draw(scr, g)
        k = scr.getch()
        if k == curses.KEY_RESIZE:
            continue
        if k == ord('Q'):
            g.msg("Really quit? Press Q again. The audience is begging you not to.")
            draw(scr, g)
            if scr.getch() == ord('Q'):
                return
            continue
        if k == ord('?'):
            screen(scr, INTRO, cp(6))
            continue
        if g.handle(k) and g.state == 'play':
            g.end_turn()
    end_screen(scr, g, g.state == 'won')


def main():
    os.environ.setdefault('ESCDELAY', '25')
    try:
        curses.wrapper(game_loop)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
