"""Headless test of the Smash Bros. level: the shield blocks, a strong hit at
150% launches a fighter past the blast zone but not at 0%, Akuma's special
buttons (special / special+punch / special+kick / punch+kick), items (pick up,
swing, throw, bob-omb, hammer, star, snacks), the two rounds of three stocks
(win one to clear), a round with Dr. Doom in the cast, and a bot (the CPU
brain driving Akuma, with his damage kept low) that clears the level.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python3 tests/smash_test.py
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from akuma import smash as S  # noqa: E402
from akuma.smash import SmashScene  # noqa: E402

SHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")
MAX_FRAMES = 60 * 60 * 12


def shot(game, name):
    os.makedirs(SHOT_DIR, exist_ok=True)
    pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOT_DIR, name))


def _tick(game, held=(), press=()):
    game.input.virtual = set(held)
    game.input.virtual_pressed = set(press)
    game.tick()


def _start(game, seed, cpu=True, items=False):
    sc = SmashScene(game, seed=seed)
    game.scene = sc
    sc.cpu_enabled = cpu
    sc.items_enabled = items
    while sc.phase == "intro":
        _tick(game)
    return sc


def _duel(sc, ax=150.0, gap=None, facing=-1):
    """Akuma and one CPU face to face on the main floor; the other two parked on the tower."""
    a, c = sc.akuma, sc.cpus[0]
    for k, f in enumerate(sc.cpus[1:]):
        f.x, f.y = S.TOWER.left + 12.0 + k * 26, float(S.TOWER.top)
    a.x, a.y = ax, float(S.FLOOR_Y)
    a.facing = facing
    gap = gap if gap is not None else sc.reach(a, "kick") - 2
    c.x, c.y = ax + facing * gap, float(S.FLOOR_Y)
    c.facing = -facing
    for f in sc.fighters:
        f.vx = f.vy = f.lvx = f.lvy = 0.0
        f.state, f.t, f.airborne, f.invuln = "stand", 0, False, 0
    return a, c


def test_shield(game):
    sc = _start(game, seed=2, cpu=False)
    a, c = _duel(sc, ax=150.0, gap=sc.reach(sc.cpus[0], "kick") - 2, facing=1)
    for _ in range(4):
        _tick(game, ("shield",))
    assert a.state == "shield", a.state
    shield = a.shield
    c.start_move("kick")
    blocked = False
    for _ in range(40):
        _tick(game, ("shield",))
        blocked = blocked or a.shield < shield - 5
    assert a.pct == 0, ("shield let damage through", a.pct)
    assert blocked, ("the kick never reached the shield", shield, a.shield)
    # and without the shield the same kick lands
    for _ in range(20):
        _tick(game)
    a, c = _duel(sc, ax=150.0, gap=sc.reach(sc.cpus[0], "kick") - 2, facing=1)
    c.start_move("kick")
    for _ in range(40):
        _tick(game)
    assert a.pct > 0, "unshielded kick missed"
    print("smash shield: blocked a %s kick (shield %.0f -> %.0f), unshielded it does %d%%"
          % (c.name, shield, a.shield if a.shield < shield else shield, a.pct))


def _launch(game, pct, seed=4):
    sc = _start(game, seed=seed, cpu=False)
    a, c = _duel(sc, ax=140.0, facing=-1)
    c.pct = float(pct)
    stocks = c.stocks
    _tick(game, ("left",), ("kick",))
    hit = False
    for _ in range(360):
        _tick(game)
        hit = hit or c.pct > pct
        if c.stocks < stocks:
            break
    assert hit, "the kick missed"
    return sc, c, c.stocks < stocks


def test_knockback(game):
    sc, c, ko = _launch(game, 150)
    assert ko, ("150%% kick did not KO %s" % c.name, round(c.x), round(c.y), c.state)
    sc, c, ko = _launch(game, 0)
    assert not ko, "0% kick KO'd"
    assert S.STAGE_L <= c.x <= S.STAGE_R and c.y <= S.FLOOR_Y, (c.x, c.y)
    print("smash knockback: 150%% kick KOs %s, 0%% kick leaves %s on stage at %d%%"
          % (c.name, c.name, c.pct))


def test_hit_shot(game):
    """A mid-air kick connecting, for the screenshot."""
    sc = _start(game, seed=7, cpu=False)
    for _ in range(50):             # let the GO! banner clear
        _tick(game)
    a, c = _duel(sc, ax=150.0, facing=1)
    c.pct = 120.0
    _tick(game, ("right",), ("kick",))
    for _ in range(40):
        _tick(game)
        if c.state == "hitstun" and c.hitstop and c.hitstop < 8:
            shot(game, "smash_hit.png")
            break
    else:
        raise AssertionError("no hit to screenshot")


def _end_round(game, sc, win):
    """Knock out the losing side, then let GAME! and the round result play out."""
    rnd = sc.round
    if win:
        for c in sc.cpus:
            c.stocks = 1
            c.state, c.invuln = "air", 0
            c.x = S.BLAST_R + 5.0
    else:
        sc.akuma.stocks = 1
        sc.akuma.state, sc.akuma.invuln = "air", 0
        sc.akuma.x = S.BLAST_L - 5.0
    _tick(game)
    assert sc.phase == "game" and sc.won == win, (sc.phase, sc.won)
    for _ in range(S.GAME_LEN + 2):
        _tick(game)
        if sc.round != rnd or sc.phase == "final":
            break


def test_stocks(game):
    done = []
    old_done, old_failed = game.level_done, game.level_failed
    game.level_done = lambda scene, hp: done.append(("win", hp))
    game.level_failed = lambda scene: done.append(("lose", None))
    try:
        sc = _start(game, seed=9, cpu=False)
        c = sc.cpus[0]
        c.y = S.BLAST_B + 5.0
        _tick(game)
        assert c.stocks == 2 and c.state == "dead", (c.stocks, c.state)
        for _ in range(S.RESPAWN_WAIT + 2):
            _tick(game)
        assert c.state == "respawn" and c.pct == 0, c.state
        # win round 1, lose round 2: still a clear
        _end_round(game, sc, True)
        assert sc.round == 2 and sc.phase == "intro" and sc.round_wins == [True], (sc.round, sc.phase)
        assert all(f.stocks == S.STOCKS and not f.out for f in sc.fighters)
        shot(game, "smash_round2.png")
        while sc.phase == "intro":
            _tick(game)
        _end_round(game, sc, False)
        assert sc.phase == "final" and sc.round_wins == [True, False], (sc.phase, sc.round_wins)
        for _ in range(60):
            _tick(game)
        shot(game, "smash_final.png")
        for _ in range(S.FINAL_LEN + 2):
            _tick(game)
        assert done and done[-1][0] == "win", done
        # lose both: fail
        sc = _start(game, seed=10, cpu=False)
        _end_round(game, sc, False)
        while sc.phase == "intro":
            _tick(game)
        _end_round(game, sc, False)
        assert sc.phase == "final" and not sc.rounds_won
        for _ in range(S.FINAL_LEN + 2):
            _tick(game)
        assert done[-1][0] == "lose", done
        # lose round 1, win round 2: clear
        n = len(done)
        sc = _start(game, seed=11, cpu=False)
        _end_round(game, sc, False)
        while sc.phase == "intro":
            _tick(game)
        _end_round(game, sc, True)
        for _ in range(S.FINAL_LEN + 2):
            _tick(game)
        assert len(done) == n + 1 and done[-1][0] == "win", done
    finally:
        game.level_done, game.level_failed = old_done, old_failed
    print("smash rounds: KO -> respawn; 2 rounds of 3 stocks; W-L and L-W clear, L-L fails")


def _still(sc):
    a = sc.akuma
    for f in sc.fighters:
        f.vx = f.vy = f.lvx = f.lvy = 0.0
    a.x, a.y, a.state, a.t, a.airborne, a.move = 150.0, float(S.FLOOR_Y), "stand", 0, False, None
    a.upb_used = False
    a.buf = None
    for k in a.since:
        a.since[k] = 99


def test_controls(game):
    """special = hadouken, special+punch = shoryuken, special+kick = tatsu,
    within 4 frames in either order; punch+kick = grab."""
    sc = _start(game, seed=3, cpu=False)
    for f in sc.cpus:
        f.x, f.y = S.TOWER.left + 20.0, float(S.TOWER.top)
    a = sc.akuma
    seen = {}
    cases = [("fireball", [("special",)], "neutral"),
             ("sho together", [("special", "punch")], "up"),
             ("tatsu together", [("special", "kick")], "down"),
             ("special then punch", [("special",), (), (), ("punch",)], "up"),
             ("kick then special", [("kick",), (), ("special",)], "down"),
             ("special, punch too late", [("special",)] + [()] * 6 + [("punch",)], "neutral"),
             ("punch+kick grab", [("punch",), ("kick",)], "grab"),
             ("up+special is no longer sho", [("up", "special")], "neutral")]
    for label, seq, want in cases:
        _still(sc)
        sc.shots = []
        names = []
        for press in seq:
            _tick(game, ("up",) if "up" in press else (), tuple(p for p in press if p != "up"))
            names.append(a.move_name if a.state == "move" else None)
        got = names[-1]
        assert got == want, (label, names, want)
        for _ in range(12):
            _tick(game)
        if want == "neutral":
            assert sc.shots, (label, "no fireball")
        if want == "up":
            assert not sc.shots, (label, "fireball not taken back")
        seen[label] = got
        for _ in range(80):
            _tick(game)
    print("smash controls: " + ", ".join("%s -> %s" % kv for kv in seen.items()))


def test_items(game):
    sc = _start(game, seed=6, cpu=False)
    a, c = _duel(sc, ax=150.0, gap=26, facing=-1)
    # pick up a bat with punch, swing it at someone at 60%: home run
    bat = sc.spawn_item("bat", x=a.x + 3, y=a.y - 1)
    for _ in range(4):
        _tick(game)
    assert bat.state == "ground", bat.state
    _tick(game, (), ("punch",))
    assert a.item is bat and bat.state == "held", (a.item, bat.state)
    for _ in range(12):
        _tick(game)
    a, c = _duel(sc, ax=150.0, gap=24, facing=-1)
    c.pct = 60.0
    stocks = c.stocks
    _tick(game, (), ("punch",))
    assert a.move_name == "item", a.move_name
    for _ in range(300):
        _tick(game)
        if c.stocks < stocks:
            break
    assert c.stocks < stocks, ("bat at 60% did not KO", c.pct, c.x, c.y)
    # punch+kick throws it
    for _ in range(80):
        _tick(game)
    a, c = _duel(sc, ax=150.0, gap=60, facing=-1)
    for _ in range(30):
        _tick(game)
    _tick(game, (), ("punch", "kick"))
    assert a.item is None and bat.state == "thrown", bat.state
    for _ in range(80):
        _tick(game)
    # snack heals damage %
    a.pct = 60.0
    food = sc.spawn_item("food", x=a.x, y=a.y - 20, snack="RAMEN")
    for _ in range(30):
        _tick(game)
    assert food.gone and a.pct < 60, (food.state, a.pct)
    healed = 60 - a.pct
    # heart container
    a.pct = 150.0
    sc.spawn_item("heart", x=a.x, y=a.y - 20)
    for _ in range(30):
        _tick(game)
    assert a.pct == 50.0, a.pct
    # star: hits do nothing
    sc.spawn_item("star", x=a.x, y=a.y - 20)
    for _ in range(30):
        _tick(game)
    assert a.star > 0
    a, c = _duel(sc, ax=150.0, facing=-1)
    a.star = 200
    pct = a.pct
    c.start_move("kick")
    for _ in range(30):
        _tick(game)
    assert a.pct == pct, "star didn't protect"
    a.star = 0
    # bob-omb: pick up, throw, boom
    for _ in range(60):
        _tick(game)
    a, c = _duel(sc, ax=150.0, gap=70, facing=-1)
    c.pct = 0.0
    bomb = sc.spawn_item("bomb", x=a.x + 2, y=a.y - 1)
    for _ in range(4):
        _tick(game)
    _tick(game, (), ("punch",))
    assert a.item is bomb
    for _ in range(14):
        _tick(game)
    a.facing = -1
    _tick(game, ("left",), ("punch",))
    assert bomb.state == "thrown"
    for _ in range(60):
        _tick(game)
        if bomb.gone:
            break
    assert bomb.gone and c.pct >= 15, ("bob-omb", bomb.state, c.pct, c.x, bomb.x, bomb.y)
    shot(game, "smash_bomb.png") if sc.booms else None
    bomb_pct = c.pct
    # hammer: swings by itself
    for _ in range(80):
        _tick(game)
    a, c = _duel(sc, ax=150.0, gap=60, facing=-1)
    c.pct = 0.0
    ham = sc.spawn_item("hammer", x=a.x - 2, y=a.y - 1)
    for _ in range(4):
        _tick(game)
    _tick(game, (), ("punch",))
    assert a.item is ham
    for _ in range(10):
        _tick(game)
    c.x = a.x - 16
    c.state, c.vx = "stand", 0.0
    for _ in range(20):
        _tick(game)
    assert c.pct >= 15, ("hammer missed", c.pct)
    _tick(game, (), ("special",))
    assert not sc.shots, "special came out while holding the hammer"
    print("smash items: bat KO at 60%%, throw, RAMEN -%d%%, heart, star, bob-omb %d%%, hammer %d%%"
          % (healed, bomb_pct, c.pct))


def test_doom_round(game):
    """A full CPU round with Dr. Doom in the cast (Akuma played by the bot)."""
    sc = SmashScene(game, seed=21)
    sc.roster = ["drdoom", "ryu", "ken"]
    sc._start_round()
    game.scene = sc
    assert sc.cpus[0].name == "DR. DOOM"
    brain = S.Brain(sc, sc.akuma, S.random.Random(2), focus=0.0)
    used = set()
    frames = 0
    while sc.round == 1 and frames < 60 * 60 * 4:
        frames += 1
        if frames % 20 == 0:
            sc.akuma.pct = min(sc.akuma.pct, 30.0)
        d = sc.cpus[0]
        if d.state == "move":
            used.add(d.move_name)
        if sc.phase == "play":
            it = brain.think()
            _tick(game, it.held_actions(), it.pressed_actions())
        else:
            _tick(game)
        if frames == 700:
            shot(game, "smash_doom.png")
    assert sc.round == 2 or sc.phase == "final", (sc.round, sc.phase)
    print("smash doom: round with DR. DOOM done in %.1f s, he used %s" % (frames / 60, sorted(used)))


def bot_smash(game, label="smash.png"):
    """Akuma played by the CPU brain (focused on whoever is closest), his damage
    kept low as a small cheat, until every challenger is out of stocks."""
    sc = game.scene
    assert isinstance(sc, SmashScene)
    brain = S.Brain(sc, sc.akuma, S.random.Random(1), focus=0.0)
    brain.aggr, brain.block, brain.react = 0.95, 0.5, 8
    frames = 0
    items = set()
    while game.scene is sc and sc.result is None and frames < MAX_FRAMES:
        frames += 1
        if frames % 20 == 0:
            sc.akuma.pct = min(sc.akuma.pct, 30.0)
        if sc.phase == "play":
            it = brain.think()
            _tick(game, it.held_actions(), it.pressed_actions())
        else:
            _tick(game)
        for f in sc.fighters:
            if f.item is not None:
                items.add((f.name, f.item.kind))
        if frames == 900 and label:
            shot(game, label)
    assert sc.result == "win", (sc.result, frames, [(f.name, f.stocks, int(f.pct)) for f in sc.fighters])
    print("smash bot: rounds %s, items held: %s" % (sc.round_wins, sorted(items)))
    return frames


def test_smash(game):
    test_shield(game)
    test_knockback(game)
    test_hit_shot(game)
    test_stocks(game)
    test_controls(game)
    test_items(game)
    test_doom_round(game)
    old_done = game.level_done
    won = []
    game.level_done = lambda scene, hp: won.append(hp)
    try:
        game.scene = SmashScene(game, seed=5)
        names = [f.name for f in game.scene.cpus]
        f = bot_smash(game)
    finally:
        game.level_done = old_done
    assert won, "level_done not called"
    print("smash: bot beat %s in %.1f s (hp handed on: %d)" % (", ".join(names), f / 60, won[0]))


if __name__ == "__main__":
    from akuma.game import Game
    g = Game()
    g.level_done = lambda scene, hp: None
    g.level_failed = lambda scene: None
    test_smash(g)
    print("smash test passed")
