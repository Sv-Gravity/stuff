"""Headless test of level 6 (the Smash Bros. stage): the shield blocks, a strong
hit at 150% launches a fighter past the blast zone but not at 0%, stocks run
out and end the game both ways, and a bot (the CPU brain driving Akuma, with
his damage kept low) wins the whole free-for-all.

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
MAX_FRAMES = 60 * 60 * 6


def shot(game, name):
    os.makedirs(SHOT_DIR, exist_ok=True)
    pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOT_DIR, name))


def _tick(game, held=(), press=()):
    game.input.virtual = set(held)
    game.input.virtual_pressed = set(press)
    game.tick()


def _start(game, seed, cpu=True):
    sc = SmashScene(game, seed=seed)
    game.scene = sc
    sc.cpu_enabled = cpu
    while sc.phase == "intro":
        _tick(game)
    return sc


def _duel(sc, ax=150.0, gap=None, facing=-1):
    """Akuma and one CPU face to face on the main floor; the other two parked on the tower."""
    a, c = sc.akuma, sc.cpus[0]
    for k, f in enumerate(sc.cpus[1:]):
        f.x, f.y = 206.0 + k * 28, float(S.TOWER.top)
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
        for c in sc.cpus:
            c.stocks = 1
            c.state, c.invuln = "air", 0
            c.x = S.BLAST_R + 5.0
        _tick(game)
        assert all(c.out for c in sc.cpus)
        assert sc.phase == "game" and sc.won
        for _ in range(S.GAME_LEN + 2):
            _tick(game)
        assert done and done[-1][0] == "win", done
        sc = _start(game, seed=10, cpu=False)
        sc.akuma.stocks = 1
        sc.akuma.x = S.BLAST_L - 5.0
        _tick(game)
        assert sc.akuma.out and sc.phase == "game" and not sc.won
        for _ in range(S.GAME_LEN + 2):
            _tick(game)
        assert done[-1][0] == "lose", done
    finally:
        game.level_done, game.level_failed = old_done, old_failed
    print("smash stocks: KO -> respawn, last stocks end the game (win and lose)")


def bot_smash(game, label="smash.png"):
    """Akuma played by the CPU brain (focused on whoever is closest), his damage
    kept low as a small cheat, until every challenger is out of stocks."""
    sc = game.scene
    assert isinstance(sc, SmashScene)
    brain = S.Brain(sc, sc.akuma, S.random.Random(1), focus=0.0)
    brain.aggr, brain.block, brain.react = 0.95, 0.5, 8
    frames = 0
    while game.scene is sc and sc.result is None and frames < MAX_FRAMES:
        frames += 1
        if frames % 20 == 0:
            sc.akuma.pct = min(sc.akuma.pct, 30.0)
        if sc.phase == "play":
            it = brain.think()
            _tick(game, it.held_actions(), it.pressed_actions())
        else:
            _tick(game)
        if frames == 900 and label:
            shot(game, label)
    assert sc.result == "win", (sc.result, frames, [(f.name, f.stocks, int(f.pct)) for f in sc.fighters])
    return frames


def test_smash(game):
    test_shield(game)
    test_knockback(game)
    test_hit_shot(game)
    test_stocks(game)
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
