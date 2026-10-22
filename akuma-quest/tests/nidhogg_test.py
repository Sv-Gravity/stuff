"""Headless test of level 11's Nidhogg sabre duels: parries, lunge range,
disarms, thrown sabres, dive kick + neck snap, Akuma's hearts, and a bot that
wins a duel against the CPU.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/nidhogg_test.py
"""

import os
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from akuma import nidhogg as N  # noqa: E402
from akuma.nidhogg import NidhoggScene, Ctrl  # noqa: E402

SHOTS = os.environ.get("SHOTS", os.path.join(ROOT, "screenshots"))
NONE = Ctrl()


def shot(game, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOTS, name))


def make_enemy(boss=False, cid="ken"):
    return SimpleNamespace(name="THE SWORD SAINT RYU" if boss else "MAD KEN", cid="ryu" if boss else cid,
                           boss=boss, level=5 if boss else 2, hp=14, walk=1.4, moves=[],
                           ai=dict(aggression=0.9, block=0.6, jumpiness=0.3, reaction=2) if boss else
                           dict(aggression=0.5, block=0.3, jumpiness=0.2, reaction=6))


def duel(game, boss=False, hp=None, seed=7, cid="ken"):
    """A scene already past EN GARDE, for driving one frame at a time."""
    sc = NidhoggScene(game, make_enemy(boss, cid), game.akuma_max if hp is None else hp, game.akuma_max, seed=seed)
    game.scene = sc
    sc.phase = "duel"
    for f in (sc.p, sc.e):
        f.set_state("stand")
    return sc


def place(sc, px, ex, ph=1, eh=1):
    sc.p.x, sc.e.x = float(px), float(ex)
    sc.p.height, sc.e.height = ph, eh
    sc.p.facing, sc.e.facing = (1, -1) if px < ex else (-1, 1)


def run(sc, n, pc=NONE, ec=NONE, first_pc=None, first_ec=None):
    for i in range(n):
        sc._step(first_pc if (i == 0 and first_pc) else pc, first_ec if (i == 0 and first_ec) else ec)
        if sc.p.dead or sc.e.dead:
            return


def names(sc):
    return [e for _, e in sc.events]


J = Ctrl(pressed=("punch",))
K = Ctrl(pressed=("kick",))


def test_parry(game):
    sc = duel(game)
    # same height, blades just crossing: a lunge is parried, nobody dies
    place(sc, 100, 100 + 2 * (N.HAND + N.BLADE), 1, 1)
    run(sc, 20, first_pc=J)
    assert "parry" in names(sc), names(sc)
    assert not sc.p.dead and not sc.e.dead
    assert sc.e.armed and sc.p.armed
    # clinch: walking blade-to-blade at the same height just pushes
    sc = duel(game)
    place(sc, 100, 190, 2, 2)
    e0 = sc.e.x
    run(sc, 40, pc=Ctrl(held=("right",)))
    assert not sc.p.dead and not sc.e.dead, names(sc)
    assert sc.e.x > e0, "clinch did not push"
    assert abs(sc.e.x - sc.p.x) >= 2 * (N.HAND + N.BLADE) - 1
    print("nidhogg: parry at matching height, same-height blades push")


def test_lunge_range(game):
    sc = duel(game)
    place(sc, 100, 166, 1, 2)         # in range, heights differ
    run(sc, 20, first_pc=J)
    assert sc.e.dead and not sc.p.dead, (names(sc), sc.e.x - sc.p.x)
    assert sc.phase == "kill"
    sc = duel(game)
    place(sc, 100, 188, 1, 2)         # out of range
    run(sc, 20, first_pc=J)
    assert not sc.e.dead and not sc.p.dead, names(sc)
    # tapping lunge repeatedly inches forward
    x0 = sc.p.x
    for _ in range(4):
        run(sc, N.LUNGE_RELUNGE, first_pc=J)
    assert sc.p.x > x0 + 4, (x0, sc.p.x)
    print("nidhogg: lunge in range kills, out of range misses, repeat lunges inch forward")


def test_disarm(game):
    sc = duel(game)
    place(sc, 100, 152, 0, 1)         # blades overlap well past half-way
    run(sc, 1, first_pc=Ctrl(pressed=("up",)))
    assert "disarm" in names(sc), names(sc)
    assert not sc.e.armed and sc.p.armed and sc.p.height == 1
    run(sc, 60)
    assert any(sb.rest for sb in sc.sabres), "the lost sabre never landed"
    # a light touch (less than half-way) only clinks
    sc = duel(game)
    place(sc, 100, 162, 0, 1)
    run(sc, 1, first_pc=Ctrl(pressed=("up",)))
    assert sc.e.armed and "disarm" not in names(sc)
    # disarmed fighter picks the sabre up with down
    sc = duel(game)
    place(sc, 100, 152, 0, 1)
    run(sc, 1, first_pc=Ctrl(pressed=("up",)))
    run(sc, 60)
    sab = [sb for sb in sc.sabres if sb.rest][0]
    sc.e.x = sab.x + 3
    sc.e.set_state("stand")
    run(sc, 2, first_ec=Ctrl(held=("down",), pressed=("down",)))
    assert sc.e.armed, "no pick up"
    print("nidhogg: crossing past half-way disarms, the sabre lands and can be picked up")


def test_thrown(game):
    # low guard: killed, Akuma loses a heart
    sc = duel(game)
    place(sc, 80, 220, 0, 1)
    run(sc, 80, first_ec=K)
    assert sc.p.dead and "kill_akuma_thrown" in names(sc), names(sc)
    assert sc.hearts == N.HEARTS - 1
    # mid guard parries it
    sc = duel(game)
    place(sc, 80, 220, 1, 1)
    run(sc, 80, first_ec=K)
    assert not sc.p.dead and "throw_parried" in names(sc), names(sc)
    run(sc, 60)
    assert any(sb.rest for sb in sc.sabres)
    # ducking dodges it; it flies on to the wall
    sc = duel(game)
    place(sc, 80, 220, 0, 1)
    sc.p.set_state("duck")
    run(sc, 80, pc=Ctrl(held=("down",)), first_ec=K)
    assert not sc.p.dead, names(sc)
    print("nidhogg: thrown sabre kills a low guard, mid parries, ducking dodges")


def test_dive_and_snap(game):
    sc = duel(game)
    place(sc, 100, 160, 1, 1)
    sc.p.set_state("air")
    sc.p.y = N.FLOOR_Y - 34
    sc.p.x = sc.e.x - 30
    sc.p.vx = sc.p.vy = 0.0
    run(sc, 30, first_pc=J)
    assert "divekick" in names(sc), names(sc)
    assert sc.e.state == "down" and not sc.e.armed and not sc.p.dead
    run(sc, 16)
    sc.p.x = sc.e.x - 12
    sc.p.set_state("stand")
    run(sc, 20, first_pc=J)
    assert sc.e.dead and "kill_enemy_snap" in names(sc), names(sc)
    # a high sabre skewers the dive kick
    sc = duel(game)
    place(sc, 100, 160, 1, 2)
    sc.p.set_state("air")
    sc.p.y = N.FLOOR_Y - 34
    sc.p.x = sc.e.x - 34
    sc.p.vx = sc.p.vy = 0.0
    run(sc, 30, first_pc=J)
    assert sc.p.dead and "kill_akuma_skewered" in names(sc), names(sc)
    print("nidhogg: dive kick knocks down and disarms, neck snap kills, high sabre skewers dives")


def test_punch_trip(game):
    sc = duel(game)
    place(sc, 100, 120, 1, 1)
    sc.p.armed = sc.e.armed = False
    run(sc, 14, first_pc=J)
    assert sc.e.state == "hurt", (sc.e.state, names(sc))
    sc.p.x = sc.e.x - 20
    run(sc, 14, first_pc=J)
    assert sc.e.state == "down", (sc.e.state, names(sc))
    # trip from a duck
    sc = duel(game)
    place(sc, 100, 118, 1, 1)
    sc.p.armed = sc.e.armed = False
    sc.p.set_state("duck")
    run(sc, 12, pc=Ctrl(held=("down",)), first_pc=Ctrl(held=("down",), pressed=("kick",)))
    assert sc.e.state == "down", (sc.e.state, names(sc))
    # rolling under a mid sabre, low sabre kills a roller
    sc = duel(game)
    place(sc, 60, 200, 1, 0)
    sc.p.armed = False
    run(sc, 60, pc=Ctrl(held=("right",)), first_pc=Ctrl(held=("right",), pressed=("down",)))
    assert sc.p.dead and "kill_akuma_stab" in names(sc), names(sc)
    sc = duel(game)
    place(sc, 110, 200, 1, 1)
    sc.p.armed = False
    run(sc, N.ROLL_T, pc=Ctrl(held=("right",)), first_pc=Ctrl(held=("right",), pressed=("down",)))
    assert not sc.p.dead, names(sc)
    print("nidhogg: two punches knock down, trips knock down, rolls pass under mid, low kills rollers")


def test_hearts(game):
    results = []
    game.end_fight = lambda f, r, hp: results.append((r, hp))
    sc = duel(game)
    seg = game.akuma_max / N.HEARTS
    assert sc.hearts == 5
    for k in range(5):
        assert sc.phase == "duel", (k, sc.phase)
        sc.kill(sc.p, sc.e, "test")
        assert sc.hearts == 4 - k, (k, sc.hearts, sc.hp)
        assert abs(sc.hp - (4 - k) * seg) < 1
        for _ in range(400):
            sc.update(game.input)
            if sc.phase in ("duel",) or results:
                break
        if k < 4:
            assert sc.phase == "duel" and not sc.p.dead and sc.p.x == N.P_START and sc.e.x == N.E_START, sc.phase
            assert sc.p.armed and sc.e.armed
    assert results == [("lose", 0)], results
    # a partly spent hp bar rounds up to hearts
    sc = duel(game, hp=game.akuma_max * 0.5)
    assert sc.hearts == 3
    print("nidhogg: each death costs a heart and resets en garde, 5 deaths lose")


def bot_nidhogg(game, boss=False, seed=3, max_frames=60 * 120, label=None):
    """Plays Akuma: reads the CPU's real sabre height (cheating past any
    reaction delay), holds a different one, steps into lunge range and thrusts;
    matches a lunge's height to parry; picks up a lost sabre."""
    sc = NidhoggScene(game, make_enemy(boss), game.akuma_max, game.akuma_max, seed=seed)
    game.scene = sc
    results = []
    game.end_fight = lambda f, r, hp: results.append((r, hp))
    frames = 0
    cd = 0
    shot_done = False
    while not results and frames < max_frames:
        frames += 1
        held, pressed = set(), set()
        p, e = sc.p, sc.e
        if sc.phase == "duel" and not p.dead:
            d = abs(e.x - p.x)
            toward = "right" if e.x > p.x else "left"
            cd = max(0, cd - 1)
            if p.state == "down":
                pressed.add("up")
            elif not p.armed:
                sab = sc.nearest_floor_sabre(p)
                if sab is not None and sab.rest:
                    if abs(sab.x - p.x) < 8:
                        held.add("down")
                        pressed.add("down")
                    else:
                        held.add("right" if sab.x > p.x else "left")
                elif p.state == "duck":
                    pressed.add("up")
            elif p.state == "duck":
                pressed.add("up")
            elif e.state == "down" and d < N.SNAP_RANGE - 4:
                pressed.add("punch")
            elif p.state == "stand":
                reach = N.HAND + N.LUNGE_EXT + N.BLADE + 8
                if e.state == "lunge" and e.armed and e.guard != p.height and cd == 0:
                    want = e.guard
                elif not e.armed or e.state == "down":
                    want = 0 if e.state in ("down", "roll", "duck") else 1
                else:
                    want = (e.guard + 1) % 3
                if want != p.height and cd == 0:
                    pressed.add("up" if want > p.height else "down")
                    cd = 2
                elif want == p.height and (not e.armed or e.guard != p.height):
                    if d <= reach:
                        pressed.add("punch")
                    else:
                        held.add(toward)
                elif d > N.HAND + N.BLADE + 30:
                    held.add(toward)
            if not shot_done and label and d < 84:
                shot(game, label)
                shot_done = True
        game.input.virtual = held
        game.input.virtual_pressed = pressed
        game.tick()
        if sc.phase == "kill" and sc.phase_t == 12:
            shot(game, "nidhogg_kill.png")
    game.input.virtual = set()
    assert results and results[0][0] == "win", (results, sc.hearts, names(sc)[-20:])
    return frames, sc


def test_ai_fights(game):
    """The CPU left alone against a dummy Akuma kills him, and two CPUs
    don't freeze up."""
    sc = duel(game, seed=11)
    sc.update(game.input)
    for _ in range(60 * 30):
        sc._step(NONE, sc.ai.think(sc.e, sc.p, sc))
        if sc.p.dead:
            break
    assert sc.p.dead, ("idle akuma survived the CPU", names(sc)[-10:])
    print("nidhogg: CPU kills a dummy Akuma (%s)" % names(sc)[-1])


def test_level11(game):
    """A real level 11 map enemy, through game.start_fight / end_fight."""
    from akuma.dungeon import LEVELS
    if not any(cfg.get("nidhogg") for cfg in LEVELS.values()):
        print("nidhogg: no nidhogg level wired yet, skipping the level 11 check")
        return
    lvl = [k for k, cfg in LEVELS.items() if cfg.get("nidhogg")][0]
    end = game.end_fight
    game.end_fight = type(game).end_fight.__get__(game)
    try:
        game.new_run(seed=4, start=lvl)
        ow = game.overworld
        foe = [en for en in ow.enemies if not en.boss][0]
        ow.enemies.remove(foe)   # as the map does when a fight starts
        game.start_fight(foe, ow.hp, False)
        sc = game.scene
        assert isinstance(sc, NidhoggScene), type(sc)
        assert sc.hearts == N.HEARTS
        # pause menu opens and freezes the duel
        while sc.phase != "duel":
            game.tick()
        game.input.virtual_pressed = {"start"}
        game.tick()
        assert sc.paused
        game.input.virtual_pressed = {"back"}
        game.tick()
        assert not sc.paused
        sc.kill(sc.e, sc.p, "test")
        for _ in range(400):
            game.tick()
            if game.scene is not sc:
                break
        assert game.scene is ow and sc.result == "win", (game.scene, sc.result)
        print("nidhogg: level %d map enemy duel returns to the map" % lvl)
    finally:
        game.end_fight = end


def test_nidhogg(game):
    end = game.end_fight
    try:
        test_parry(game)
        test_lunge_range(game)
        test_disarm(game)
        test_thrown(game)
        test_dive_and_snap(game)
        test_punch_trip(game)
        test_ai_fights(game)
        test_hearts(game)
        test_level11(game)
        f, sc = bot_nidhogg(game, label="nidhogg.png")
        print("nidhogg: bot beat a grunt in %.1f s with %d hearts left" % (f / 60, sc.hearts))
        f, sc = bot_nidhogg(game, boss=True, seed=5)
        print("nidhogg: bot beat the boss in %.1f s with %d hearts left" % (f / 60, sc.hearts))
    finally:
        game.end_fight = end


if __name__ == "__main__":
    from akuma.game import Game
    g = Game()
    test_nidhogg(g)
    print("nidhogg test passed")
