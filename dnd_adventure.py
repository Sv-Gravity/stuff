#!/usr/bin/env python3
"""
THE BARROW OF GALLOWS HILL
A small, text-only solo adventure using simplified D&D 5th Edition rules
(the 2024 revision of the rulebooks).

Run it with:   python3 dnd_adventure.py

Needs only Python 3 (no extra packages), so it runs as-is on Raspberry Pi OS.

What is kept from the real rules
  - Six ability scores rolled with 4d6, drop the lowest die
  - Ability modifiers, +2 proficiency bonus, skill checks against a DC
  - Armor Class, attack rolls, natural 20 critical hits, natural 1 misses
  - Backgrounds raise ability scores (+2 / +1), as in the 2024 rules
  - Drinking a healing potion is a bonus action (2024 rules)

What is simplified to keep the game small
  - Four classes, four species, four backgrounds, nine skills
  - One attack and one special ability per class, no feats, no equipment shop
  - Monsters are weaker than the book versions because you adventure alone
  - No death saving throws: at 0 hit points you fall, and may retry the fight
"""

import copy
import random
import shutil
import textwrap

WIDTH = max(40, min(shutil.get_terminal_size((80, 24)).columns, 80))
PROF = 2            # proficiency bonus at levels 1-4
POTION_PRICE = 25

# ----------------------------------------------------------------------------
# Rules data
# ----------------------------------------------------------------------------

ABILITIES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]

ABILITY_INFO = {
    "STR": "Strength - muscle. Swinging heavy weapons, forcing doors.",
    "DEX": "Dexterity - agility. Dodging blows, sneaking, quick blades.",
    "CON": "Constitution - toughness. Gives you more hit points.",
    "INT": "Intelligence - learning. Wizard magic, lore, searching.",
    "WIS": "Wisdom - awareness. Cleric magic, noticing things, reading people.",
    "CHA": "Charisma - force of personality. Persuading and intimidating.",
}

SKILLS = {
    "Athletics": "STR",
    "Stealth": "DEX",
    "Sleight of Hand": "DEX",
    "Arcana": "INT",
    "Investigation": "INT",
    "Insight": "WIS",
    "Perception": "WIS",
    "Intimidation": "CHA",
    "Persuasion": "CHA",
}

CLASSES = {
    "Fighter": {
        "blurb": "Heavily armored warrior. Tough and simple - great for a first game.",
        "hit_die": 10,
        "primary": "STR",
        "order": ["STR", "CON", "DEX", "WIS", "CHA", "INT"],
        "skills": ["Athletics", "Perception"],
        "power": 2,
        "power_name": "Second Wind",
    },
    "Rogue": {
        "blurb": "Quick and cunning. Hits hard with Sneak Attack, good at skills.",
        "hit_die": 8,
        "primary": "DEX",
        "order": ["DEX", "CON", "CHA", "INT", "WIS", "STR"],
        "skills": ["Stealth", "Sleight of Hand", "Investigation", "Persuasion"],
        "power": 0,
        "power_name": "",
    },
    "Wizard": {
        "blurb": "Fragile spellcaster. Fire Bolt at will, Magic Missile never misses.",
        "hit_die": 6,
        "primary": "INT",
        "order": ["INT", "CON", "DEX", "WIS", "CHA", "STR"],
        "skills": ["Arcana", "Investigation"],
        "power": 2,
        "power_name": "Spell slots",
    },
    "Cleric": {
        "blurb": "Armored holy caster. Can heal wounds or blast foes with light.",
        "hit_die": 8,
        "primary": "WIS",
        "order": ["WIS", "CON", "STR", "DEX", "CHA", "INT"],
        "skills": ["Insight", "Persuasion"],
        "power": 2,
        "power_name": "Spell slots",
    },
}

ATTACKS = {
    "Fighter": {"name": "Longsword", "verb": "swing your longsword", "n": 1, "sides": 8, "add_mod": True},
    "Rogue": {"name": "Shortsword", "verb": "lunge with your shortsword", "n": 1, "sides": 6, "add_mod": True},
    "Wizard": {"name": "Fire Bolt", "verb": "hurl a Fire Bolt", "n": 1, "sides": 10, "add_mod": False},
    "Cleric": {"name": "Sacred Flame", "verb": "call down Sacred Flame", "n": 1, "sides": 8, "add_mod": False},
}

SPECIES = {
    "Human": "Skillful - you pick one extra skill to be proficient in.",
    "Elf": "Keen Senses - proficient in Perception. Darkvision - you see in the dark.",
    "Dwarf": "Dwarven Toughness - 1 extra hit point per level. Darkvision.",
    "Halfling": "Luck - whenever you roll a 1 on a d20, you get to reroll it.",
}

BACKGROUNDS = {
    "Soldier": {"plus2": "STR", "plus1": "CON", "skills": ["Athletics", "Intimidation"]},
    "Criminal": {"plus2": "DEX", "plus1": "CON", "skills": ["Sleight of Hand", "Stealth"]},
    "Sage": {"plus2": "INT", "plus1": "CON", "skills": ["Arcana", "Investigation"]},
    "Acolyte": {"plus2": "WIS", "plus1": "CHA", "skills": ["Insight", "Persuasion"]},
}


class GameOver(Exception):
    """Raised to end the current adventure early."""


# ----------------------------------------------------------------------------
# Text helpers
# ----------------------------------------------------------------------------

def say(text=""):
    """Print story text, word-wrapped, one blank line after each paragraph."""
    text = textwrap.dedent(text).strip("\n")
    if not text.strip():
        print()
        return
    for para in text.split("\n\n"):
        print(textwrap.fill(" ".join(para.split()), WIDTH, break_on_hyphens=False))
        print()


def header(title):
    print()
    print("=" * WIDTH)
    print(title.center(WIDTH))
    print("=" * WIDTH)
    print()


def pause(prompt="[Press Enter to continue]"):
    input(prompt + " ")
    print()


def ask(prompt):
    while True:
        raw = input(prompt + " ").strip()
        if raw:
            print()
            return raw


def choose(prompt, options):
    """Show a numbered menu and return the index of the option picked."""
    if prompt:
        print(textwrap.fill(prompt, WIDTH))
    for i, opt in enumerate(options, 1):
        print(textwrap.fill(opt, WIDTH, initial_indent="  %d) " % i, subsequent_indent="     "))
    while True:
        raw = input("> ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            print()
            return int(raw) - 1
        print("  Type a number from 1 to %d and press Enter." % len(options))


def roll(n, sides):
    return sum(random.randint(1, sides) for _ in range(n))


def fmt(n):
    return "+%d" % n if n >= 0 else str(n)


# ----------------------------------------------------------------------------
# The hero
# ----------------------------------------------------------------------------

class Hero:
    def __init__(self):
        self.name = "Hero"
        self.species = ""
        self.cls = ""
        self.background = ""
        self.scores = {a: 10 for a in ABILITIES}
        self.skills = set()
        self.level = 1
        self.max_hp = 1
        self.hp = 1
        self.max_power = 0      # spell slots or Second Wind uses
        self.power = 0
        self.gold = 50
        self.potions = 0
        self.flags = set()

    def mod(self, ability):
        return (self.scores[ability] - 10) // 2

    @property
    def ac(self):
        dex = self.mod("DEX")
        if self.cls == "Fighter":
            return 18                       # chain mail + shield
        if self.cls == "Cleric":
            return 15 + min(dex, 2)         # chain shirt + shield
        if self.cls == "Rogue":
            return 11 + dex                 # leather armor
        return 13 + dex                     # wizard's Mage Armor

    @property
    def attack_bonus(self):
        return PROF + self.mod(CLASSES[self.cls]["primary"])

    @property
    def darkvision(self):
        return self.species in ("Elf", "Dwarf")

    def skill_bonus(self, skill):
        return self.mod(SKILLS[skill]) + (PROF if skill in self.skills else 0)

    def d20(self, advantage=False):
        def one():
            r = random.randint(1, 20)
            if r == 1 and self.species == "Halfling":
                print("  (Halfling Luck! You rolled a 1 and reroll it.)")
                r = random.randint(1, 20)
            return r
        r = one()
        if advantage:
            r = max(r, one())
        return r

    def check(self, skill, dc, advantage=False):
        """Roll a skill check, print the maths, return True on success."""
        bonus = self.skill_bonus(skill)
        r = self.d20(advantage)
        total = r + bonus
        ok = total >= dc
        adv = " with advantage" if advantage else ""
        print("  [%s check%s: d20 roll %d %s = %d vs DC %d -> %s]"
              % (skill, adv, r, fmt(bonus), total, dc, "SUCCESS" if ok else "FAILURE"))
        print()
        return ok

    def heal(self, amount):
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - before

    def hurt(self, amount, floor=0):
        self.hp = max(floor, self.hp - amount)

    def long_rest(self):
        self.hp = self.max_hp
        self.power = self.max_power


def skill_label(hero, skill):
    return "%s %s" % (skill, fmt(hero.skill_bonus(skill)))


def show_sheet(hero):
    cls = CLASSES[hero.cls]
    atk = ATTACKS[hero.cls]
    line = "-" * WIDTH
    print(line)
    print("  %s - Level %d %s %s (%s)" % (hero.name, hero.level, hero.species, hero.cls, hero.background))
    print(line)
    print("  Hit Points: %d/%d    Armor Class: %d    Proficiency: +%d"
          % (hero.hp, hero.max_hp, hero.ac, PROF))
    print()
    for a in ABILITIES:
        print("    %s %2d (%s)" % (a, hero.scores[a], fmt(hero.mod(a))))
    print()
    skills = ", ".join(skill_label(hero, s) for s in SKILLS if s in hero.skills)
    print(textwrap.fill("Skills: " + skills, WIDTH, initial_indent="  ", subsequent_indent="    "))

    dmg_mod = fmt(hero.mod(cls["primary"])) if atk["add_mod"] else ""
    if hero.cls == "Cleric":
        attack = "Sacred Flame: foe must roll %d+ on a Dexterity save or take 1d8" % (8 + PROF + hero.mod("WIS"))
    else:
        attack = "%s: %s to hit, %dd%d%s damage" % (atk["name"], fmt(hero.attack_bonus), atk["n"], atk["sides"], dmg_mod)
        if hero.cls == "Rogue":
            attack += ", +1d6 Sneak Attack"
    print("  Attack: " + attack)

    special = {
        "Fighter": "Second Wind (%d uses): heal 1d10 + your level" % hero.max_power,
        "Rogue": "Sneak Attack: +1d6 damage whenever you hit",
        "Wizard": "Magic Missile (%d spell slots): 3d4+3 damage, never misses" % hero.max_power,
        "Cleric": "%d spell slots: Cure Wounds (heal 2d8%s) or Guiding Bolt (4d6 damage)"
                  % (hero.max_power, fmt(hero.mod("WIS"))),
    }[hero.cls]
    print(textwrap.fill("Special: " + special, WIDTH, initial_indent="  ", subsequent_indent="    "))
    print(textwrap.fill("Trait: " + SPECIES[hero.species], WIDTH, initial_indent="  ", subsequent_indent="    "))
    print("  Carrying: %d healing potion(s), %d gold" % (hero.potions, hero.gold))
    print(line)
    print()


# ----------------------------------------------------------------------------
# Character creation
# ----------------------------------------------------------------------------

def roll_scores():
    scores = []
    for i in range(1, 7):
        dice = sorted((random.randint(1, 6) for _ in range(4)), reverse=True)
        total = sum(dice[:3])
        print("  Roll %d:  %s   drop the %d  ->  %2d"
              % (i, "  ".join(str(d) for d in dice), dice[3], total))
        scores.append(total)
    print()
    return sorted(scores, reverse=True)


def assign_scores(hero, scores):
    """Let the player place each rolled score. Returns a dict of ability -> score."""
    while True:
        pool = list(scores)
        result = {}
        primary = CLASSES[hero.cls]["primary"]
        for a in ABILITIES:
            note = "  <- most important for a %s" % hero.cls if a == primary else ""
            print(ABILITY_INFO[a] + note)
            if len(pool) == 1:
                print("  Only %d is left, so it goes here." % pool[0])
                print()
                result[a] = pool.pop()
            else:
                i = choose("Which score goes in %s?" % a, [str(s) for s in pool])
                result[a] = pool.pop(i)
        print("  " + "   ".join("%s %d" % (a, result[a]) for a in ABILITIES))
        print()
        if choose("Happy with that?", ["Yes, keep it", "No, let me place them again"]) == 0:
            return result


def create_character():
    hero = Hero()
    header("CREATE YOUR CHARACTER")
    say("""
        Every adventure starts with a hero. We'll build yours in five quick
        steps: name, class, species, background, and ability scores.
    """)

    # 1. Name
    print("STEP 1 of 5 - NAME")
    hero.name = ask("What is your character called?")[:24]

    # 2. Class
    print("STEP 2 of 5 - CLASS")
    say("Your class is what you do: how you fight and what you're good at.")
    names = list(CLASSES)
    hero.cls = names[choose("Choose a class:", ["%s - %s" % (n, CLASSES[n]["blurb"]) for n in names])]
    hero.skills.update(CLASSES[hero.cls]["skills"])

    # 3. Species
    print("STEP 3 of 5 - SPECIES")
    say("Your species gives you one special trait.")
    names = list(SPECIES)
    hero.species = names[choose("Choose a species:", ["%s - %s" % (n, SPECIES[n]) for n in names])]
    if hero.species == "Elf":
        hero.skills.add("Perception")

    # 4. Background
    print("STEP 4 of 5 - BACKGROUND")
    say("""
        Your background is what you did before adventuring. It raises two
        ability scores and teaches you two skills.
    """)
    names = list(BACKGROUNDS)
    labels = []
    for n in names:
        b = BACKGROUNDS[n]
        labels.append("%s - +2 %s, +1 %s; skills: %s" % (n, b["plus2"], b["plus1"], " and ".join(b["skills"])))
    hero.background = names[choose("Choose a background:", labels)]
    hero.skills.update(BACKGROUNDS[hero.background]["skills"])

    if hero.species == "Human":
        spare = [s for s in SKILLS if s not in hero.skills]
        pick = choose("As a Human you learn one extra skill. Which one?",
                      ["%s (uses %s)" % (s, SKILLS[s]) for s in spare])
        hero.skills.add(spare[pick])

    # 5. Ability scores
    print("STEP 5 of 5 - ABILITY SCORES")
    say("""
        Six numbers describe your hero's body and mind. For each one you roll
        four six-sided dice and add up the best three. Around 10 is average,
        15 or more is excellent.
    """)
    while True:
        pause("[Press Enter to roll the dice]")
        scores = roll_scores()
        print("  Your six scores: " + ", ".join(str(s) for s in scores))
        print()
        pick = choose("What now?", [
            "Place the scores myself",
            "Place them for me (best fit for a %s)" % hero.cls,
            "Reroll all six",
        ])
        if pick == 0:
            hero.scores = assign_scores(hero, scores)
            break
        if pick == 1:
            hero.scores = dict(zip(CLASSES[hero.cls]["order"], scores))
            break

    bg = BACKGROUNDS[hero.background]
    hero.scores[bg["plus2"]] = min(20, hero.scores[bg["plus2"]] + 2)
    hero.scores[bg["plus1"]] = min(20, hero.scores[bg["plus1"]] + 1)
    print("  Your %s background adds +2 %s and +1 %s." % (hero.background, bg["plus2"], bg["plus1"]))
    print()

    # Derived numbers
    cls = CLASSES[hero.cls]
    hero.max_hp = max(1, cls["hit_die"] + hero.mod("CON")) + (1 if hero.species == "Dwarf" else 0)
    hero.max_power = cls["power"]
    hero.long_rest()

    say("Your hero is ready. Here is your character sheet:")
    show_sheet(hero)
    pause()
    return hero


def level_up(hero):
    cls = CLASSES[hero.cls]
    gain = max(1, cls["hit_die"] // 2 + 1 + hero.mod("CON")) + (1 if hero.species == "Dwarf" else 0)
    hero.level = 2
    hero.max_hp += gain
    print("  *** LEVEL UP! %s is now level 2. ***" % hero.name)
    print("  Maximum hit points +%d (now %d)." % (gain, hero.max_hp))
    if hero.cls in ("Wizard", "Cleric"):
        hero.max_power = 3
        print("  You now have 3 spell slots.")
    if hero.cls == "Fighter":
        print("  Second Wind now heals a little more.")
    print()


# ----------------------------------------------------------------------------
# Combat
# ----------------------------------------------------------------------------

class Monster:
    def __init__(self, name, hp, ac, to_hit, dice, bonus, attack, dex_save=0,
                 leader=False, on_bloodied=None):
        self.name = name
        self.hp = self.max_hp = hp
        self.ac = ac
        self.to_hit = to_hit
        self.dice = dice            # (number, sides)
        self.bonus = bonus
        self.attack = attack        # e.g. "slashes at you"
        self.dex_save = dex_save
        self.leader = leader        # if the leader dies, the fight is over
        self.on_bloodied = on_bloodied
        self.bloodied_done = False


def damage_monster(target, dmg):
    target.hp = max(0, target.hp - dmg)
    if target.hp == 0:
        print("  %s is defeated!" % target.name)


def pick_target(monsters):
    alive = [m for m in monsters if m.hp > 0]
    if len(alive) == 1:
        return alive[0]
    return alive[choose("Which foe?", ["%s (%d HP)" % (m.name, m.hp) for m in alive])]


def hero_attack(hero, target):
    atk = ATTACKS[hero.cls]

    if hero.cls == "Cleric":        # Sacred Flame: the target rolls to dodge
        dc = 8 + PROF + hero.mod("WIS")
        total = random.randint(1, 20) + target.dex_save
        if total >= dc:
            print("  You %s, but %s twists away (its save: %d vs DC %d)."
                  % (atk["verb"], target.name, total, dc))
        else:
            dmg = roll(1, 8)
            print("  You %s. %s fails to dodge (its save: %d vs DC %d) -> %d damage!"
                  % (atk["verb"], target.name, total, dc, dmg))
            damage_monster(target, dmg)
        return

    r = hero.d20()
    total = r + hero.attack_bonus
    maths = "d20 roll %d %s = %d vs AC %d" % (r, fmt(hero.attack_bonus), total, target.ac)
    if r == 1 or (r != 20 and total < target.ac):
        print("  You %s: %s -> miss." % (atk["verb"], maths))
        return
    crit = r == 20
    mult = 2 if crit else 1
    dmg = roll(atk["n"] * mult, atk["sides"])
    if atk["add_mod"]:
        dmg += hero.mod(CLASSES[hero.cls]["primary"])
    extra = ""
    if hero.cls == "Rogue":
        dmg += roll(mult, 6)
        extra = " (with Sneak Attack)"
    dmg = max(1, dmg)
    print("  You %s: %s -> %s %d damage%s."
          % (atk["verb"], maths, "CRITICAL HIT!" if crit else "HIT!", dmg, extra))
    damage_monster(target, dmg)


def hero_turn(hero, monsters):
    bonus_used = False
    while True:
        cls = CLASSES[hero.cls]
        status = "  %s: %d/%d HP, AC %d, potions %d" % (hero.name, hero.hp, hero.max_hp, hero.ac, hero.potions)
        if hero.max_power:
            status += ", %s %d/%d" % (cls["power_name"].lower(), hero.power, hero.max_power)
        print(status)
        print("  Foes: " + ", ".join("%s (%d HP)" % (m.name, m.hp) for m in monsters if m.hp > 0))
        print()

        options = ["Attack - " + ATTACKS[hero.cls]["name"]]
        actions = ["attack"]
        if hero.cls == "Wizard" and hero.power > 0:
            options.append("Cast Magic Missile - 3d4+3 damage, never misses (uses a spell slot)")
            actions.append("missile")
        if hero.cls == "Cleric" and hero.power > 0:
            options.append("Cast Guiding Bolt - 4d6 damage if it hits (uses a spell slot)")
            actions.append("bolt")
            if hero.hp < hero.max_hp:
                options.append("Cast Cure Wounds - heal 2d8%s (uses a spell slot)" % fmt(hero.mod("WIS")))
                actions.append("cure")
        if hero.cls == "Fighter" and hero.power > 0 and not bonus_used and hero.hp < hero.max_hp:
            options.append("Second Wind - heal 1d10+%d, then keep acting (bonus action)" % hero.level)
            actions.append("wind")
        if hero.potions > 0 and not bonus_used and hero.hp < hero.max_hp:
            options.append("Drink a healing potion - heal 2d4+2, then keep acting (bonus action)")
            actions.append("potion")

        act = actions[choose("Your turn. What do you do?", options)]

        if act == "attack":
            hero_attack(hero, pick_target(monsters))
            return
        if act == "missile":
            target = pick_target(monsters)
            hero.power -= 1
            dmg = roll(3, 4) + 3
            print("  Three glowing darts streak into %s -> %d damage." % (target.name, dmg))
            damage_monster(target, dmg)
            return
        if act == "bolt":
            target = pick_target(monsters)
            hero.power -= 1
            r = hero.d20()
            total = r + hero.attack_bonus
            maths = "d20 roll %d %s = %d vs AC %d" % (r, fmt(hero.attack_bonus), total, target.ac)
            if r == 1 or (r != 20 and total < target.ac):
                print("  Your Guiding Bolt flashes past %s: %s -> miss." % (target.name, maths))
            else:
                dmg = roll(8 if r == 20 else 4, 6)
                print("  Your Guiding Bolt strikes %s: %s -> %s %d damage."
                      % (target.name, maths, "CRITICAL HIT!" if r == 20 else "HIT!", dmg))
                damage_monster(target, dmg)
            return
        if act == "cure":
            hero.power -= 1
            got = hero.heal(max(1, roll(2, 8) + hero.mod("WIS")))
            print("  Warm light knits your wounds. You heal %d (now %d/%d HP)." % (got, hero.hp, hero.max_hp))
            return
        if act == "wind":
            hero.power -= 1
            bonus_used = True
            got = hero.heal(roll(1, 10) + hero.level)
            print("  You grit your teeth and find your Second Wind. You heal %d (now %d/%d HP)."
                  % (got, hero.hp, hero.max_hp))
            print()
        if act == "potion":
            hero.potions -= 1
            bonus_used = True
            got = hero.heal(roll(2, 4) + 2)
            print("  You gulp down the potion. You heal %d (now %d/%d HP)." % (got, hero.hp, hero.max_hp))
            print()


def monsters_turn(hero, monsters):
    for m in monsters:
        if m.hp <= 0 or hero.hp <= 0:
            continue
        r = random.randint(1, 20)
        total = r + m.to_hit
        if r == 1 or (r != 20 and total < hero.ac):
            print("  %s %s: %d vs your AC %d -> miss." % (m.name, m.attack, total, hero.ac))
        else:
            crit = r == 20
            dmg = max(1, roll(m.dice[0] * (2 if crit else 1), m.dice[1]) + m.bonus)
            hero.hurt(dmg)
            print("  %s %s: %d vs your AC %d -> %s You take %d damage (%d/%d HP)."
                  % (m.name, m.attack, total, hero.ac, "CRITICAL HIT!" if crit else "hit!",
                     dmg, hero.hp, hero.max_hp))


def battle(hero, monsters, hero_first=None):
    """Run one fight. Returns True if the hero wins, False if the hero falls."""
    if hero_first is None:
        mine = hero.d20() + hero.mod("DEX")
        theirs = random.randint(1, 20) + max(m.dex_save for m in monsters)
        hero_first = mine >= theirs
        print("  Initiative: you %d, them %d -> %s."
              % (mine, theirs, "you act first" if hero_first else "they act first"))
    rnd = 1
    while True:
        print()
        print("--- Round %d ---" % rnd)
        for side in (("hero", "foes") if hero_first else ("foes", "hero")):
            if side == "hero":
                hero_turn(hero, monsters)
                for m in list(monsters):
                    if m.hp > 0 and m.on_bloodied and not m.bloodied_done and m.hp <= m.max_hp // 2:
                        m.bloodied_done = True
                        m.on_bloodied(hero, monsters)
                if any(m.leader and m.hp <= 0 for m in monsters) or not any(m.hp > 0 for m in monsters):
                    print()
                    return True
            else:
                monsters_turn(hero, monsters)
                if hero.hp <= 0:
                    print()
                    return False
            print()
        rnd += 1


def fight(hero, make_monsters, hero_first=None):
    """Run a battle, offering a retry if the hero falls."""
    saved = copy.deepcopy(hero.__dict__)
    while True:
        if battle(hero, make_monsters(), hero_first):
            return
        say("%s crumples to the ground. The world goes dark..." % hero.name)
        if choose("Fate offers you one more chance.",
                  ["Try this fight again", "Accept your fate (end the game)"]) == 1:
            raise GameOver("death")
        hero.__dict__.update(copy.deepcopy(saved))
        say("Time rewinds. You steady yourself and face the fight again.")


# ----------------------------------------------------------------------------
# The adventure
# ----------------------------------------------------------------------------

def scene_tavern(hero):
    header("CHAPTER 1 - THE TIPSY GRIFFIN")
    say("""
        Rain drums on the thatch of the Tipsy Griffin, the only tavern in the
        village of Oakhollow. You have been on the road for three days, and the
        fire, the stew and the cheap ale feel like a royal welcome.

        The common room is quiet tonight. Marta the barkeep polishes the same
        mug over and over. A grey-bearded old soldier stares into his cup by
        the hearth. In the corner, a grinning halfling rattles a pair of dice
        at anyone who glances his way.
    """)
    todo = ["marta", "garrick", "pip"]
    labels = {
        "marta": "Chat with Marta the barkeep",
        "garrick": "Sit down beside the old soldier",
        "pip": "Try your luck with the halfling's dice",
    }
    while True:
        options = [labels[t] for t in todo] + ["Finish your drink"]
        pick = choose("What do you do?", options)
        if pick == len(todo):
            break
        who = todo.pop(pick)

        if who == "marta":
            say("""
                "You picked a poor week to visit, traveler," Marta says, lowering
                her voice. "Three nights running there've been green lights up on
                Gallows Hill, where the old barrow is. Sheep gone missing. And
                yesterday the gravedigger found two graves in the churchyard dug
                open. From the inside, he swears."

                She slides a bowl of stew across the bar. "On the house. You look
                like you can handle yourself, and we may have need of that."
            """)

        elif who == "garrick":
            say("""
                The old soldier doesn't look up as you sit. His hand, you notice,
                is trembling on the cup. Whatever is on his mind, he isn't
                sharing it freely.
            """)
            pick = choose("How do you approach him?", [
                "Buy him a drink and ask about his soldiering days (%s)" % skill_label(hero, "Persuasion"),
                "Watch him a while, then say what you think is troubling him (%s)" % skill_label(hero, "Insight"),
                "Leave him to his thoughts",
            ])
            if pick == 2:
                say("You nod to him and return to your own table.")
            elif hero.check("Persuasion" if pick == 0 else "Insight", 12):
                hero.flags.add("staff_hint")
                say("""
                    His eyes sharpen. "Garrick's the name. I went into that barrow
                    once, thirty years gone, when a pale wizard called Vexmoor
                    first tried his tricks up there. We drove him out."

                    He leans close. "Listen well. His power isn't in him, it's in
                    that staff of bone he carries. When he's hurt, he leans on it
                    to call up the dead. Break the staff and he's just a
                    frightened old man."
                """)
                print("  (You will remember Garrick's advice.)")
                print()
            else:
                say("""
                    "Leave an old man to his drink," he mutters, and turns his
                    shoulder to you. You get nothing more out of him.
                """)

        elif who == "pip":
            say("""
                "Pip Thistlewick, at your service!" The halfling sweeps the dice
                into a cup. "High roll takes the pot. Five gold a throw, friend."
            """)
            if hero.gold < 5:
                say("You turn out your empty pockets. Pip sighs and waves you off.")
                continue
            pick = choose("You have %d gold." % hero.gold, [
                "Play fair and trust your luck",
                "Swap in a loaded die when he blinks (%s)" % skill_label(hero, "Sleight of Hand"),
                "Keep your gold",
            ])
            if pick == 0:
                while True:
                    mine, his = random.randint(1, 20), random.randint(1, 20)
                    print("  You roll %d. Pip rolls %d." % (mine, his))
                    if mine != his:
                        break
                    print("  A tie! You both roll again.")
                print()
                if mine > his:
                    hero.gold += 5
                    say('"Beginner\'s luck," Pip grumbles, pushing 5 gold across the table.')
                else:
                    hero.gold -= 5
                    say('"Better luck next time!" Pip scoops up your 5 gold with a wink.')
            elif pick == 1:
                if hero.check("Sleight of Hand", 13):
                    hero.gold += 10
                    say("""
                        Your die lands on its best face, twice. Pip pays out 10 gold,
                        squinting at you with the first stirrings of suspicion.
                    """)
                else:
                    hero.gold -= 5
                    say("""
                        Pip's small hand clamps onto your wrist. "Nice try," he says
                        cheerfully. "That'll be five gold for the lesson." You pay up.
                    """)
            else:
                say('"Suit yourself," says Pip, already looking for another mark.')

    say("""
        You drain the last of your ale. You have barely set the mug down when
        the tavern door crashes open.

        A young farmhand staggers in out of the rain, his sleeve torn and
        bloody. "The dead!" he gasps. "The dead are walking on Gallows Hill! I
        saw them come out of the barrow, and they... they looked at me!"
    """)
    pause()


def scene_quest(hero):
    say("""
        The room goes silent. Then an elderly woman rises from a table by the
        window, leaning on a cane. Marta whispers, "Elder Rowena."

        "So it is true," the elder says. "Vexmoor the Pale has come back."
        She turns to the room. "Thirty years ago we drove a necromancer out of
        the old barrow. Now he has returned, and he is raising the dead from
        our own churchyard. When the moon is full tomorrow night, he will have
        enough of them to march on Oakhollow."

        Her gaze settles on you, the only armed stranger in the room.
        "%s, is it? We are farmers, not fighters. Go to the barrow on Gallows
        Hill and stop Vexmoor before tomorrow's moonrise. The village will pay
        you 100 gold pieces. It is everything we have."
    """ % hero.name)
    if choose("Do you accept the quest?", ["Yes. I'll stop him.", "No. This isn't my fight."]) == 1:
        say('"Then we are lost," Rowena says quietly. Every face in the room is turned toward you.')
        if choose("", ["Change your mind and accept", "Leave Oakhollow tonight"]) == 1:
            say("""
                You shoulder your pack and slip out into the rain. Nobody tries to
                stop you.

                Weeks later, in a city far to the south, you overhear a merchant
                say that Oakhollow is only a name on old maps now.

                Not every tale is a heroic one.
            """)
            raise GameOver("coward")
        say('You let out a long breath. "All right. I\'ll do it."')
    say("""
        "Bless you." The elder presses a small red vial into your hand. "A
        healing potion. It is the only one I have."
    """)
    hero.potions += 1
    print("  (You gain 1 healing potion. Each one heals 2d4+2 hit points.)")
    print()

    say('Marta waves you over to the bar. "I keep a few of those myself. %d gold apiece."' % POTION_PRICE)
    while True:
        can_buy = hero.gold >= POTION_PRICE
        options = ["Buy a healing potion (%d gold)" % POTION_PRICE] if can_buy else []
        options.append("Get some sleep and set out at dawn")
        pick = choose("You have %d gold and %d potion(s)." % (hero.gold, hero.potions), options)
        if not can_buy or pick == 1:
            break
        hero.gold -= POTION_PRICE
        hero.potions += 1
        print("  You buy a potion.")
        print()


def make_goblins():
    return [
        Monster("Skinny Goblin", 7, 12, 3, (1, 6), 0, "jabs with a rusty knife", dex_save=2),
        Monster("Fat Goblin", 7, 12, 3, (1, 6), 0, "swings a club", dex_save=2),
    ]


def scene_road(hero):
    header("CHAPTER 2 - THE ROAD TO GALLOWS HILL")
    say("""
        You leave at first light. By afternoon the road climbs through bare,
        wind-bent trees. Rounding a bend, you spot an overturned cart, and two
        goblins squabbling over the turnips spilled from it.

        They haven't noticed you yet.
    """)
    pick = choose("What do you do?", [
        "Draw your weapon and attack",
        "Creep past through the trees (%s)" % skill_label(hero, "Stealth"),
        "Step out and scare them off (%s)" % skill_label(hero, "Intimidation"),
    ])
    fought = True
    if pick == 0:
        say("You charge. The goblins shriek and snatch up their weapons.")
        fight(hero, make_goblins)
    elif pick == 1:
        if hero.check("Stealth", 12):
            fought = False
            say("""
                You slip from trunk to trunk, silent as a shadow. The goblins
                never look up from their turnips. Soon they are far behind you.
            """)
        else:
            say("A dry branch snaps under your boot. Two ugly heads whip around. They rush you!")
            fight(hero, make_goblins, hero_first=False)
    else:
        if hero.check("Intimidation", 13):
            fought = False
            hero.gold += 8
            say("""
                You stride out and roar a challenge. The goblins take one look at
                you, drop everything and bolt into the woods. One of them leaves
                behind a greasy pouch holding 8 gold.
            """)
        else:
            say("""
                The goblins look at you, then at each other, and burst into
                cackling laughter. Then they come at you.
            """)
            fight(hero, make_goblins)
    if fought:
        hero.gold += 8
        say("The goblins lie still. In the cart you find a pouch holding 8 gold.")
    pause()

    say("""
        At dusk you reach Gallows Hill. Halfway up its bald slope, a doorway of
        stacked stones opens into the earth: the barrow. A faint green glow
        flickers somewhere far inside.

        You are tired, and nothing good will come of going in exhausted. You
        make a cold camp among the rocks and rest for a few hours, thinking
        over the road behind you. You are tougher and wiser than the traveler
        who walked into the Tipsy Griffin.
    """)
    level_up(hero)
    hero.long_rest()
    print("  (After a rest, your hit points and abilities are fully restored.)")
    print()
    pause()


def make_skeletons():
    return [
        Monster("Rusty Skeleton", 9, 12, 3, (1, 6), 1, "hacks with a notched sword", dex_save=1),
        Monster("Tall Skeleton", 9, 12, 3, (1, 6), 1, "thrusts a spear", dex_save=1),
    ]


def scene_barrow(hero):
    header("CHAPTER 3 - THE BARROW")
    if hero.darkvision:
        say("""
            You duck through the doorway. The dark is no trouble to your %s
            eyes; the passage ahead shows clearly in shades of grey.
        """ % ("elven" if hero.species == "Elf" else "dwarven"))
    else:
        say("""
            You light a torch and duck through the doorway. The flame gutters
            in the stale air, and the shadows crowd close around you.
        """)
    say("The passage slopes down, its walls lined with niches full of old bones.")
    if hero.check("Perception", 13, advantage=hero.darkvision):
        say("""
            You stop mid-step. One flagstone sits a finger's width higher than
            the rest, and there are small holes in the wall beside it. You
            step carefully over the pressure plate and move on.
        """)
    else:
        dmg = roll(1, 6)
        hero.hurt(dmg, floor=1)
        say("""
            A flagstone sinks under your foot with a click. Darts hiss out of
            the wall!
        """)
        print("  You take %d damage (%d/%d HP)." % (dmg, hero.hp, hero.max_hp))
        print()

    say("""
        The passage opens into a low chamber. Two heaps of bones against the
        far wall rattle, shift, and stand up. Green light burns in their eye
        sockets as they raise their weapons.
    """)
    fight(hero, make_skeletons)
    say("The skeletons collapse into ordinary bones. The chamber is still.")

    if choose("Before moving on:", ["Search the chamber (%s)" % skill_label(hero, "Investigation"),
                                    "Press on"]) == 0:
        if hero.check("Investigation", 12):
            hero.potions += 1
            say("""
                Behind a loose stone you find a rotted satchel, left by some
                earlier visitor who never came back. Inside, wrapped in cloth,
                is an unbroken healing potion.
            """)
        else:
            say("You find dust, bones and more dust. Nothing of use.")

    # The riddle door
    say("""
        Beyond the chamber, the way is blocked by a slab of black stone carved
        with a grinning skull. As you approach, its jaw grinds open and a voice
        like gravel fills the passage:

        "Feed me and I grow. Give me drink and I die. I have no lungs, yet I
        must have air. Name me, and pass."
    """)
    wrong = 0
    studied = False
    while True:
        options = ["Speak an answer"]
        actions = ["answer"]
        if not studied:
            options.append("Study the runes around the skull for a clue (%s)" % skill_label(hero, "Arcana"))
            actions.append("study")
        options.append("Put your shoulder to the door (%s)" % skill_label(hero, "Athletics"))
        actions.append("force")
        act = actions[choose("What do you do?", options)]

        if act == "answer":
            guess = ask("Your answer:").lower()
            if any(word in guess for word in ("fire", "flame", "blaze")):
                say('"Fire," the skull agrees, almost sadly. The slab rumbles aside.')
                break
            wrong += 1
            if wrong >= 3:
                say("""
                    "Wrong. The answer was fire." The skull sighs like a tired
                    schoolmaster. "Thirty years I have waited to ask that. Go on,
                    then." The slab rumbles aside.
                """)
                break
            dmg = roll(1, 4)
            hero.hurt(dmg, floor=1)
            say('"Wrong." A jolt of cold leaps from the stone into your chest.')
            print("  You take %d damage (%d/%d HP)." % (dmg, hero.hp, hero.max_hp))
            print()
        elif act == "study":
            studied = True
            if hero.check("Arcana", 12):
                say("""
                    The runes are an old warding script. One sign repeats all
                    around the skull: the mark for "hearth", the thing that
                    warms a home.
                """)
            else:
                say("The runes swim before your eyes. They mean nothing to you.")
        else:
            if hero.check("Athletics", 14):
                say("""
                    You heave. Stone shrieks against stone, and the slab scrapes
                    aside far enough to squeeze through. "Rude," mutters the skull.
                """)
                break
            dmg = roll(1, 4)
            hero.hurt(dmg, floor=1)
            say("The slab doesn't budge, and the ward on it bites back.")
            print("  You take %d damage (%d/%d HP)." % (dmg, hero.hp, hero.max_hp))
            print()

    say("""
        Past the door is a small, bare antechamber. Green light leaks under
        one last door ahead, and a low chanting comes from behind it. Nothing
        stirs here, so you sit against the wall, bind your wounds and gather
        your strength for what comes next.
    """)
    hero.long_rest()
    print("  (You rest. Your hit points and abilities are fully restored.)")
    print()
    pause()


def scene_boss(hero):
    header("CHAPTER 4 - VEXMOOR THE PALE")
    say("""
        You ease the last door open on a round burial chamber lit by sickly
        green candles.
        Bodies lie on stone slabs, stitched with glowing thread. Among them
        stands a gaunt man in tattered robes, chalk-pale, gripping a staff of
        knotted bones.

        Vexmoor the Pale has his back to you. He is chanting over the nearest
        corpse, and has not heard you enter.
    """)
    pick = choose("How do you begin?", [
        "Step forward and challenge him",
        "Creep up behind him and strike first (%s)" % skill_label(hero, "Stealth"),
        "Scuff out part of his chalk ritual circle (%s)" % skill_label(hero, "Arcana"),
    ])
    hero_first = None
    pre_damage = 0
    if pick == 0:
        say("""
            "Vexmoor!" Your voice rings off the stone. He turns slowly, and
            smiles with too many teeth.

            "Oakhollow sent a %s? How quaint. You will make a fine sergeant
            for my army."
        """ % hero.cls.lower())
    elif pick == 1:
        if hero.check("Stealth", 13):
            hero_first = True
            say("You cross the chamber without a sound. He never sees you coming.")
        else:
            hero_first = False
            say("""
                Your foot nudges a candle. Vexmoor spins around, staff already
                raised. "A rat in my hall!"
            """)
    else:
        if hero.check("Arcana", 13):
            pre_damage = roll(2, 6)
            say("""
                You drag your heel through the chalk at exactly the right point.
                The circle's stored power bursts loose and slams into its maker.
                Vexmoor screams.
            """)
            print("  (Vexmoor takes %d damage before the fight begins.)" % pre_damage)
            print()
        else:
            dmg = roll(1, 6)
            hero.hurt(dmg, floor=1)
            say("""
                You smudge the wrong line. Green fire lashes up your leg, and
                Vexmoor whirls around. "Clumsy fool!"
            """)
            print("  You take %d damage (%d/%d HP)." % (dmg, hero.hp, hero.max_hp))
            print()

    def raise_dead(hero, monsters):
        print()
        if "staff_hint" in hero.flags:
            say("""
                Vexmoor staggers and raises his bone staff to call up the dead.
                But you remember Garrick's words. You strike the staff with all
                your strength, and it shatters like dry kindling.

                "No!" The bodies on the slabs lie still.
            """)
            hero.flags.add("staff_broken")
        else:
            say("""
                Vexmoor staggers and slams his bone staff against the floor.
                "Rise!" A corpse lurches off the nearest slab and shambles
                toward you.
            """)
            monsters.append(Monster("Risen Corpse", 8, 10, 3, (1, 6), 0, "claws at you", dex_save=-1))

    def make_boss():
        boss = Monster("Vexmoor", 30, 12, 4, (1, 8), 1, "flings a bolt of grave-cold", dex_save=1,
                       leader=True, on_bloodied=raise_dead)
        boss.hp -= pre_damage
        return [boss]

    hero.flags.discard("staff_broken")
    fight(hero, make_boss, hero_first)

    say("""
        Vexmoor crumples to the floor. The green candles gutter out all
        together, and across the chamber the glowing threads go dark. Whatever
        he had bound here is at rest again.
    """)
    if "staff_broken" not in hero.flags:
        say("You snap the bone staff over your knee, just to be sure.")
    pause()


def scene_ending(hero):
    header("EPILOGUE - OAKHOLLOW")
    say("""
        You walk back down Gallows Hill under a clean dawn. By the time you
        reach Oakhollow the whole village is waiting outside the Tipsy
        Griffin, and the cheer that goes up rattles the shutters.

        Elder Rowena counts 100 gold pieces into your hands. Marta announces
        that you will never pay for a drink in Oakhollow again.
    """)
    hero.gold += 100
    if "staff_hint" in hero.flags:
        say('Old Garrick lifts his cup to you from beside the hearth. "Told you. The staff."')
    say("""
        And Pip Thistlewick, eyeing your heavy purse, rattles his dice
        hopefully.

        The churchyard is quiet. The road is open. And somewhere beyond the
        hills, no doubt, another adventure is waiting for %s.
    """ % hero.name)
    show_sheet(hero)
    print("THE END".center(WIDTH))
    print()


def play():
    header("THE BARROW OF GALLOWS HILL")
    say("""
        A short solo adventure using simplified Dungeons & Dragons 5th Edition
        rules. Everything is text: read the story, then type the number of
        your choice and press Enter. The dice are rolled for you, and you'll
        see every roll.
    """)
    pause()
    hero = create_character()
    try:
        scene_tavern(hero)
        scene_quest(hero)
        scene_road(hero)
        scene_barrow(hero)
        scene_boss(hero)
        scene_ending(hero)
    except GameOver as over:
        if str(over) == "death":
            say("""
                Here ends the tale of %s. With no one left to stand against
                Vexmoor, the dead march on Oakhollow at moonrise.
            """ % hero.name)
        print("THE END".center(WIDTH))
        print()


def main():
    try:
        while True:
            play()
            if choose("Play again with a new character?", ["Yes", "No"]) == 1:
                break
        print("Thanks for playing. Farewell, adventurer!")
    except (KeyboardInterrupt, EOFError):
        print()
        print("Farewell, adventurer!")


if __name__ == "__main__":
    main()
