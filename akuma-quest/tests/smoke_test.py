"""Headless smoke test: a bot plays a whole run (every enemy + the boss).

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/smoke_test.py
"""

import os
import random
import sys
import time
from collections import deque

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from akuma.config import TILE, MAP_W, MAP_H  # noqa: E402
from akuma.dungeon import FLOOR, Overworld  # noqa: E402
from akuma.fight import FightScene  # noqa: E402
from akuma.dungeon import LEVELS  # noqa: E402
from akuma.fighters import AKUMA_MOVES, HIT, PUNCH_DMG, KICK_DMG, SPECIAL_DMG  # noqa: E402
from akuma.game import Game, EndScreen, LevelClear, Title  # noqa: E402
from akuma.practice import PracticeScene  # noqa: E402
from akuma.cars import CarScene  # noqa: E402
from akuma.bomber import BomberScene  # noqa: E402
from akuma.pacman import PacmanScene  # noqa: E402
from tests.bomber_test import bot_bomber, test_bomber  # noqa: E402
from tests.pacman_test import bot_dir as pacman_bot, test_pacman  # noqa: E402

SHOTS = os.environ.get("SHOTS")


def shot(game, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOTS, name))


def check_connected(ow):
    g = ow.dg.grid
    sx, sy = int(ow.px // TILE), int(ow.py // TILE)
    seen = {(sx, sy)}
    q = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and g[ny][nx] == FLOOR and (nx, ny) not in seen:
                seen.add((nx, ny))
                q.append((nx, ny))
    for e in ow.enemies:
        assert (int(e.x // TILE), int(e.y // TILE)) in seen, "enemy unreachable"
    for r in ow.dg.rooms:
        assert r.center in seen, "room unreachable"


def bot_fight(game, rng, max_frames=60 * 120, label=""):
    fs = game.scene
    assert isinstance(fs, FightScene)
    inp = game.input
    frames = 0
    used = set()
    while game.scene is fs and frames < max_frames:
        p, e = fs.p, fs.p.opponent or fs.e   # gangs: the foe Akuma is squared up to
        fwd = "right" if e.x > p.x else "left"
        back = "left" if fwd == "right" else "right"
        dist = abs(e.x - p.x)
        inp.virtual = set()
        r = rng.random()
        if frames % 6 == 0:
            if dist > 90:
                choice = rng.choice(["hado", "walk", "walk", "jumpkick", "jumppunch", "airhado"])
            elif dist > 45:
                choice = rng.choice(["hado", "jumpkick", "jumppunch", "dive", "walk", "sweep", "round",
                                     "tatsu", "ckick"])
            else:
                choice = rng.choice(["sho", "sweep", "block", "jab", "cjab", "front", "round", "tatsu"])
            bot_fight.choice = choice
        choice = getattr(bot_fight, "choice", "walk")
        press = r < 0.2
        if choice == "walk":
            inp.virtual = {fwd}
        elif choice == "block":
            inp.virtual = {back, "down"} if r < 0.5 else {back}
        elif choice in ("jumpkick", "jumppunch", "dive", "airhado"):
            inp.virtual = {"up", fwd}
            if not p.on_ground and p.vy > -2 and r < 0.4:
                inp.virtual_pressed = {{"jumpkick": "kick", "jumppunch": "punch", "dive": "kick",
                                        "airhado": "special"}[choice]}
                if choice == "dive":
                    inp.virtual = {"down", fwd}
        elif press:
            held, btn = {"hado": (set(), "special"), "sho": ({"down", rng.choice([fwd, back])}, "special"),
                         "ckick": ({"down", fwd}, "kick"),
                         "tatsu": ({"down"}, "special"), "jab": (set(), "punch"),
                         "cjab": ({"down"}, "punch"), "front": ({fwd}, "kick"),
                         "round": ({back}, "kick"), "sweep": ({"down"}, "kick")}[choice]
            inp.virtual = held
            inp.virtual_pressed = {btn}
        if p.state == "move" and p.move:
            used.add(p.move["name"])
        if fs.phase == "fight" and frames % 7 == 0:
            p.hp = max(p.hp, 100)  # keep the bot alive so the whole run is exercised
        game.tick()
        frames += 1
        if frames == 70 and label:
            shot(game, label)
    assert game.scene is not fs, "fight did not finish in %d frames" % max_frames
    return frames, used


def bot_car(game, label=""):
    """Smash a car: attack the near side, jump over once it is wrecked."""
    cs = game.scene
    assert isinstance(cs, CarScene)
    inp = game.input
    frames = 0
    while game.scene is cs and frames < 60 * 90:
        p, car = cs.p, cs.car
        inp.virtual = set()
        side = 0 if p.x < car.x else 1
        if car.side_hp[side] <= 0:
            inp.virtual = {"up", "right" if side == 0 else "left"}
        elif frames % 8 == 0:
            inp.virtual_pressed = {["punch", "kick", "special"][(frames // 8) % 3]}
        if cs.phase == "fight" and frames % 7 == 0:
            p.hp = max(p.hp, 100)
        game.tick()
        frames += 1
        if frames == 300 and label:
            shot(game, label)
    assert game.scene is not cs, "car fight did not finish"
    assert cs.result == "win", cs.result
    return frames


def test_car_escape(game, ow):
    """Running out the clock on a car: it drives off and Akuma loses some health."""
    car = next(e for e in ow.enemies if e.alive and not e.boss)
    ow.invuln = 0
    ow.px, ow.py = car.x, car.y
    while not isinstance(game.scene, CarScene):
        game.tick()
    cs = game.scene
    hp = cs.p.hp
    while cs.phase == "intro":
        game.tick()
    cs.timer = 3
    n = 0
    while game.scene is cs and n < 400:
        game.input.virtual = set()
        game.tick()
        n += 1
    assert cs.result == "escape" and game.scene is ow and not car.alive, cs.result
    assert ow.hp < hp, (ow.hp, hp)


def _akuma():
    from akuma.art import AKUMA_LOOK
    from akuma.fighters import Fighter
    p = Fighter("A", AKUMA_LOOK, {}, 100, is_player=True)
    e = Fighter("E", AKUMA_LOOK, [], 100)
    p.x, e.x = 100.0, 300.0
    p.opponent, e.opponent = e, p
    p.projectiles = []
    return p


def test_move_mapping():
    """Every button + direction combo comes out as the requested move."""
    D, F, B = {"down": True}, {"right": True}, {"left": True}
    cases = [({}, "special", "Gou Hadouken"), (F, "special", "Gou Hadouken"),
             (B, "special", "Gou Hadouken"), (D, "special", "Tatsumaki"),
             (dict(D, **F), "special", "Goshoryuken"), (dict(D, **B), "special", "Goshoryuken"),
             ({}, "punch", "Jab"), (F, "punch", "Jab"), (B, "punch", "Jab"),
             (D, "punch", "Crouching Jab"), (D, "kick", "Sweep"), (dict(D, **B), "kick", "Sweep"),
             (dict(D, **F), "kick", "Crouching Kick"), ({}, "kick", "Front Kick"),
             (F, "kick", "Front Kick"), (B, "kick", "Roundhouse")]
    for held, btn, want in cases:
        p = _akuma()
        p.update(dict(held, **{btn: True}))
        assert p.move and p.move["name"] == want, (held, btn, p.move and p.move["name"], want)
    for held, btn, want in (({}, "punch", "Jumping Jab"), ({}, "kick", "Jumping Kick"),
                            ({"down": True}, "kick", "Dive Kick"),
                            ({}, "special", "Zanku Hadouken")):
        p = _akuma()
        p.update({"up": True})
        for _ in range(8):
            p.update({})
        p.update(dict(held, **{btn: True}))
        assert p.move and p.move["name"] == want, (btn, want)


def test_air_moves_never_slide():
    """Regression: a dive kick landing used to slide along the floor forever."""
    for jdir in (None, "right", "left"):
        for btn in ("kick", "punch", "dive", "special"):
            for at in range(0, 45):
                p = _akuma()
                for f in range(150):
                    it = {"up": True} if f < 3 else {}
                    if jdir and f < 3:
                        it[jdir] = True
                    if f == at:
                        it["kick" if btn == "dive" else btn] = True
                        if btn == "dive":
                            it["down"] = True
                    p.update(it)
                    p.projectiles.clear()
                assert p.state == "stand" and p.vx == 0 and p.on_ground, (jdir, btn, at, p.state, p.vx)


def test_damage_tiers():
    for m in AKUMA_MOVES.values():
        if m["cat"] == "throw":
            assert m.get("dmg", HIT * 2) == HIT * 2, m["name"]
            continue
        dmg = m.get("dmg") or [ev["proj"]["dmg"] for ev in m["events"].values() if "proj" in ev][0]
        total = dmg * m.get("max_hits", 1)
        want = {"punch": PUNCH_DMG, "kick": KICK_DMG, "special": SPECIAL_DMG}[m["cat"]]
        assert total == want, (m["name"], total, want)
    assert PUNCH_DMG * 2 == KICK_DMG and SPECIAL_DMG * 2 == KICK_DMG * 3


def test_practice_and_combos(game):
    """Menu -> practice; a punch/kick/special string combos and caps at 5 hits."""
    game.input.virtual_pressed = {"down"}
    game.tick()
    game.input.virtual_pressed = {"start"}
    game.tick()
    ps = game.scene
    assert isinstance(ps, PracticeScene)
    inp = game.input
    while ps.phase != "fight":
        game.tick()
    ps.e.x = ps.p.x + 34
    string = [(set(), "punch"), (set(), "punch"), (set(), "kick"), ({"left"}, "kick"),
              (set(), "special")]
    best = 0
    k = 0
    pressed_for = None
    for f in range(400):
        inp.virtual = set()
        p = ps.p
        if k < len(string) and (k == 0 and f == 2 or (p.cancel > 0 and pressed_for != (p.move_t, p.chain) and p.cancel == 12)):
            held, btn = string[k]
            inp.virtual = set(held)
            inp.virtual_pressed = {btn}
            pressed_for = (p.move_t, p.chain)
            k += 1
        game.tick()
        best = max(best, ps.combo if ps.combo_owner is ps.p else 0)
        if f == 40:
            shot(game, "practice.png")
    print("practice combo: %d hits, string used %d moves" % (best, k))
    assert best >= 5, "combo string did not chain"
    assert ps.e.state in ("down", "getup", "stand", "launched"), ps.e.state
    # menu -> exit to title
    inp.virtual_pressed = {"start"}
    game.tick()
    assert ps.paused
    for _ in range(4):
        inp.virtual_pressed = {"down"}
        game.tick()
    inp.virtual_pressed = {"start"}
    game.tick()
    assert isinstance(game.scene, Title), "practice menu did not exit"


def test_pause_menu(game):
    """Esc opens a small menu: controls on their own page, and back to the title."""
    game.new_run(seed=3)
    ow = game.overworld
    inp = game.input
    inp.virtual_pressed = {"back"}
    game.tick()
    assert ow.menu.open and ow.menu.page is None
    inp.virtual_pressed = {"controls"}
    game.tick()
    assert ow.menu.page == "controls"
    shot(game, "pause_controls.png")
    inp.virtual_pressed = {"punch"}
    game.tick()
    assert ow.menu.page is None
    shot(game, "pause.png")
    for _ in range(2):
        inp.virtual_pressed = {"down"}
        game.tick()
    inp.virtual_pressed = {"start"}
    game.tick()
    assert ow.menu.page == "confirm"
    inp.virtual_pressed = {"right"}
    game.tick()
    inp.virtual_pressed = {"start"}
    game.tick()
    assert isinstance(game.scene, Title), "back to main menu failed"
    for _ in range(20):
        game.tick()


def test_jump_ins_open_combos(game):
    """Jumping punch, jumping kick and dive kick hit a standing enemy without
    knocking it down, and Akuma can land and keep the combo going."""
    for held, btn in (((), "punch"), ((), "kick"), (("down",), "kick")):
        game.scene = PracticeScene(game)
        ps = game.scene
        inp = game.input
        while ps.phase != "fight":
            game.tick()
        ps.e.x = ps.p.x + 80
        best = 0
        knocked = False
        stage = 0
        for f in range(160):
            p, e = ps.p, ps.e
            inp.virtual = set()
            if f < 3:
                inp.virtual = {"up", "right"}
            elif stage == 0 and p.airborne and p.vy > 0.5 and abs(e.x - p.x) < 48:
                inp.virtual = set(held)
                inp.virtual_pressed = {btn}
                stage = 1
            elif stage == 1 and ps.combo >= 1 and p.on_ground:
                inp.virtual_pressed = {"punch"}
                stage = 2
            game.tick()
            if ps.combo_owner is ps.p:
                best = max(best, ps.combo)
            if ps.combo == 1 and e.state in ("launched", "down"):
                knocked = True
        print("jump-in %s%s: %d hits" % ("down+" if held else "", btn, best))
        assert stage == 2 and not knocked and best >= 2, (held, btn, stage, knocked, best)
    game.to_title()


def test_level_select(game):
    """Debug shortcut on the title: pick a level and start straight there."""
    t = Title(game)
    game.scene = t
    inp = game.input
    for _ in range(20):
        game.tick()
    for _ in range(2):
        inp.virtual_pressed = {"down"}
        game.tick()
    for _ in range(2):
        inp.virtual_pressed = {"right"}
        game.tick()
    assert t.pick == 3, t.pick
    inp.virtual_pressed = {"start"}
    game.tick()
    assert isinstance(game.scene, Overworld) and game.scene.level == 3
    game.to_title()


def test_throws(game):
    """Punch + kick up close grabs and tosses the way you hold, for 2x damage."""
    from akuma.fighters import KICK_DMG
    for held, gap, side in (((), 0, 1), (("left",), 0, -1), (("right",), 1, 1), (("left",), 2, -1)):
        game.scene = PracticeScene(game)
        ps = game.scene
        inp = game.input
        while ps.phase != "fight":
            game.tick()
        ps.e.x = ps.p.x + 26
        hp = ps.e.hp
        inp.virtual = set(held)
        inp.virtual_pressed = {"punch"} if gap else {"punch", "kick"}
        game.tick()
        for _ in range(gap - 1):
            inp.virtual = set(held)
            game.tick()
        if gap:
            inp.virtual = set(held)
            inp.virtual_pressed = {"kick"}
            game.tick()
        lost = 0
        for f in range(70):
            inp.virtual = set()
            game.tick()
            lost = max(lost, hp - ps.e.hp)
            if f == 6 and side < 0:
                shot(game, "throw.png")
        where = 1 if ps.e.x > ps.p.x else -1
        print("throw held=%s gap=%d: %d dmg, tossed %s" % (held, gap, lost, "right" if where > 0 else "left"))
        assert lost == 2 * KICK_DMG, lost
        assert where == side, (held, where)
    game.to_title()


def test_car_platform(game):
    """Cars are solid: Akuma can't walk through, can stand on the roof, and a
    hurricane kick spins right through hitting it many times."""
    game.new_run(seed=3, start=3)
    e = next(e for e in game.scene.enemies if not e.boss)
    cs = CarScene(game, e, 200, 200, seed=1)
    game.scene = cs
    inp = game.input

    def run(n, held=(), press=()):
        for i in range(n):
            inp.virtual = set(held)
            inp.virtual_pressed = set(press) if i == 0 else set()
            game.tick()
    while cs.phase == "intro":
        run(1)
    p, car = cs.p, cs.car
    from akuma.config import GROUND_Y
    run(80, {"right"})
    assert p.x < car.x - car.half and p.y == GROUND_Y, ("walked into the car", p.x)
    run(1, {"up", "right"})
    run(40, {"right"})
    run(20)
    assert p.y < GROUND_Y - 20 and not p.airborne and abs(p.x - car.x) < car.half, \
        ("did not land on the car", p.x, p.y)
    shot(game, "car_roof.png")
    hp = car.hp
    run(1, press={"kick"})
    run(30)
    assert car.hp < hp, "kick from the roof missed"
    run(80, {"right"})
    assert p.y == GROUND_Y and p.x > car.x + car.half, ("did not walk off the roof", p.x, p.y)
    run(30)
    p.x, p.facing = car.x + car.half + 14, -1
    run(5)
    hp = car.hp
    run(1, {"down"}, press={"special"})
    run(150)
    hits = (hp - car.hp) / 4
    assert p.x < car.x - car.half and hits >= 8, ("tatsu through the car", p.x, hits)
    print("car platform: stood on the roof, tatsu through = %d hits" % hits)
    game.to_title()


def test_tetris_repair(game):
    """Car boss: a puzzle piece that lands on the car locks in and repairs it."""
    from akuma.cars import FallingPiece, CELL, REPAIR_FRAC
    game.new_run(seed=3, start=3)
    boss = next(e for e in game.scene.enemies if e.boss)
    cs = CarScene(game, boss, 200, 200, seed=1)
    game.scene = cs
    inp = game.input
    inp.virtual, inp.virtual_pressed = set(), set()
    while cs.phase == "intro":
        game.tick()
    car = cs.car
    car.side_hp[0] = car.side_max // 3
    car.boss_shed()
    hp, gone = car.hp, len(car.gone)
    cs.drop_t = 10 ** 6
    d = FallingPiece("O", cs.rng)
    d.col = d.goal = round((car.x - 30) / CELL)
    cs.drops = [d]
    for _ in range(400):
        inp.virtual, inp.virtual_pressed = set(), set()
        game.tick()
        if not cs.drops:
            break
    assert car.hp == hp + round(car.max_hp * REPAIR_FRAC), ("piece did not repair the car", hp, car.hp)
    assert len(car.gone) < gone, "repair did not put blocks back"
    print("tetris repair: boss %d -> %d HP, %d blocks restored" % (hp, car.hp, gone - len(car.gone)))
    game.to_title()


def main():
    rng = random.Random(7)
    game = Game()
    test_move_mapping()
    test_air_moves_never_slide()
    test_damage_tiers()
    for _ in range(30):
        game.tick()
    shot(game, "title.png")
    test_practice_and_combos(game)
    test_jump_ins_open_combos(game)
    test_throws(game)
    test_pause_menu(game)
    test_level_select(game)
    test_car_platform(game)
    test_tetris_repair(game)
    for _ in range(20):
        game.tick()
    game.input.virtual_pressed = {"start"}
    game.tick()
    assert isinstance(game.scene, Overworld)
    # check several seeds generate valid maps
    for seed in range(20):
        check_connected(Overworld(game, seed))
    game.new_run(seed=1234)
    all_moves = set()
    fights = 0
    t0 = time.perf_counter()
    total_frames = 0
    for level in (1, 2, 3):   # 4 and 5 are whole-level scenes, below
        ow = game.overworld
        assert ow.level == level
        check_connected(ow)
        cars = LEVELS[level].get("cars")
        if not cars:
            assert ow.boss.hp == HIT * LEVELS[level]["boss_hits"]
            hits = [e.hp / HIT for e in ow.enemies if not e.boss]
            avg = sum(hits) / len(hits)
            print("level %d grunts: %.1f hits on average" % (level, avg))
            assert 6.0 <= avg <= 8.0, avg
            # level 2: every grunt fight is two on one
            assert all(len(e.allies) == level - 1 for e in ow.enemies if not e.boss)
        for i in range(240):
            game.input.virtual = {["right", "down", "left", "up"][(i // 60) % 4]}
            game.tick()
        shot(game, "overworld%s.png" % ("" if level == 1 else level))
        if cars:
            test_car_escape(game, ow)
        order = [e for e in ow.enemies if not e.boss and e.alive] + [ow.boss]
        for e in order:
            ow.invuln = 0
            ow.px, ow.py = e.x, e.y
            game.input.virtual = set()
            n = 0
            while game.scene is ow and n < 60:
                game.tick()
                n += 1
            label = ""
            if e.boss:
                label = "fight_boss%s.png" % ("" if level == 1 else level)
            elif fights == 2:
                label = "fight.png"
            elif cars:
                label = "car_fight.png"
            if cars:
                assert isinstance(game.scene, CarScene), "no car fight started"
                f = bot_car(game, label)
            else:
                assert isinstance(game.scene, FightScene), "no encounter started"
                assert len(game.scene.foes) == (1 if e.boss else level), "level %d squad size" % level
                f, used = bot_fight(game, rng, label=label)
                all_moves |= used
            total_frames += f
            fights += 1
            if e.boss:
                break
            assert game.scene is ow
            assert not e.alive
        assert isinstance(game.scene, LevelClear), "level %d boss did not lead on" % level
        for _ in range(50):
            game.tick()
        shot(game, "level_clear%s.png" % ("" if level == 1 else level))
        game.input.virtual_pressed = {"start"}
        game.tick()
    # level 4: the car park (bomberman), level 5: the Chun-Li maze (pac-man)
    assert isinstance(game.scene, BomberScene), game.scene
    total_frames += bot_bomber(game)
    assert isinstance(game.scene, LevelClear), "level 4 did not lead on"
    for _ in range(50):
        game.tick()
    game.input.virtual_pressed = {"start"}
    game.tick()
    sc = game.scene
    assert isinstance(sc, PacmanScene), sc
    n = 0
    while game.scene is sc and n < 60 * 400:
        if n % 60 == 0:
            sc.hp = sc.max_hp
        d = pacman_bot(sc) if sc.phase == "play" else None
        game.input.virtual = {d} if d else set()
        game.tick()
        n += 1
    total_frames += n
    assert isinstance(game.scene, LevelClear), "level 5 did not lead on"
    game.input.virtual_pressed = {"start"}
    for _ in range(3):
        game.tick()
    dt = time.perf_counter() - t0
    print("fights: %d, frames: %d, avg %.2f ms/frame (headless incl. draw)" % (fights, total_frames, dt * 1000 / total_frames))
    print("akuma moves used:", sorted(all_moves))
    for need in ("Gou Hadouken", "Goshoryuken", "Tatsumaki", "Jumping Jab",
                 "Front Kick", "Roundhouse", "Sweep", "Dive Kick"):
        assert need in all_moves, need
    # a losing fight goes to game over
    game.new_run(seed=99)
    ow = game.overworld
    e = ow.enemies[0]
    ow.invuln = 0
    ow.px, ow.py = e.x, e.y
    while not isinstance(game.scene, FightScene):
        game.tick()
    game.scene.p.hp = 1
    for _ in range(60 * 60):
        if isinstance(game.scene, EndScreen):
            break
        game.input.virtual = set()
        game.tick()
    assert isinstance(game.scene, EndScreen) and not game.scene.won, "losing did not end the run"
    test_bomber(game)
    test_pacman(game)
    test_level_starts(game)
    # every later level's own test: rules plus a bot that clears it
    from tests.smash_test import test_smash
    from tests.musou_test import test_musou
    from tests.stealth_test import test_stealth
    from tests.skate_test import test_skate
    from tests.connect4_test import test_connect4
    from tests.nidhogg_test import test_nidhogg
    from tests.metroid_test import test_metroid
    from tests.doom_test import test_doom
    for t in (test_smash, test_musou, test_stealth, test_skate, test_connect4, test_nidhogg,
              test_metroid, test_doom):
        game.to_title()
        t(game)
    print("OK")


def test_level_starts(game):
    """Each of levels 6-13 starts as its own kind of scene and survives a few frames;
    the last one's clear is the ending."""
    import importlib
    for level in range(6, max(LEVELS) + 1):
        game.new_run(seed=50 + level, start=level)
        cfg = LEVELS[level]
        if cfg.get("mode"):
            mod, cls = Game.SCENES[cfg["mode"]]
            want = getattr(importlib.import_module("akuma." + mod), cls)
            assert isinstance(game.scene, want), (level, game.scene)
        else:
            ow = game.overworld
            assert isinstance(game.scene, Overworld)
            e = next(e for e in ow.enemies if not e.boss)
            game.start_fight(e, ow.hp, False)
            kind = "MusouScene" if cfg.get("musou") else "NidhoggScene"
            assert type(game.scene).__name__ == kind, (level, game.scene)
        for _ in range(30):
            game.tick()
        print("level %d (%s) starts: %s" % (level, cfg["name"], type(game.scene).__name__))
    game.level_done(game.scene, 100)
    assert isinstance(game.scene, EndScreen) and game.scene.won, "level 13 is not the last"
    game.to_title()


if __name__ == "__main__":
    main()
