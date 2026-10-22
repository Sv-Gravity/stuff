"""Headless test of level 5 (the fighter maze): the random chaser roster,
getting caught, KOing a frightened chaser (who tags out for a bench fighter),
losing, and a bot that eats every pellet.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/pacman_test.py
"""

import os
import sys
from collections import deque

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from akuma import pacman as P  # noqa: E402
from akuma.pacman import PacmanScene  # noqa: E402

SHOTS = os.environ.get("SHOTS")
MAX_FRAMES = 60 * 360


def shot(game, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOTS, name))


def _hook(game):
    """Record level_done / level_failed calls (and still run Game's own, if it has them)."""
    calls = []
    for name in ("level_done", "level_failed"):
        orig = getattr(type(game), name, None)

        def rec(scene, *args, _n=name, _o=orig):
            calls.append((_n, scene) + args)
            if _o is not None:
                _o(game, scene, *args)
        setattr(game, name, rec)
    return calls


def _idle(game, frames=1):
    game.input.virtual = set()
    for _ in range(frames):
        game.tick()


def _to_play(game, sc, cap=400):
    n = 0
    while sc.phase != "play" and n < cap:
        _idle(game)
        n += 1
    assert sc.phase == "play", sc.phase


def _danger(sc):
    """Tiles near a chaser that can still catch Akuma."""
    bad = set()
    for c in sc.chuns:
        if c.state != "out" or c.scared:
            continue
        for t in (c.tile, c.ahead()):
            bad.add(t)
            for _, n in P.neighbors(t):
                bad.add(n)
    return bad


def _plan(sc, start, avoid):
    """First step of the shortest path from start to the nearest pellet."""
    prev = {start: None}
    q = deque([start])
    while q:
        t = q.popleft()
        if t in sc.pellets and t != start:
            while prev[t][0] != start:
                t = prev[t][0]
            return prev[t][1]
        for d, n in P.neighbors(t):
            if n not in prev and n not in avoid:
                prev[n] = (t, d)
                q.append(n)
    return None


def bot_dir(sc):
    a = sc.akuma
    here = a.ahead()
    avoid = _danger(sc) - {here, a.tile}
    d = _plan(sc, here, avoid) or _plan(sc, here, set())
    if d is None and a.d:
        d = a.d
    # running straight into a chaser: turn round
    if a.d and a.p > 0 and here in _danger(sc) and a.tile not in _danger(sc):
        d = P.REVERSE[a.d]
    return d


def check_caught(game):
    game.scene = sc = PacmanScene(game, seed=5, level=5)
    _to_play(game, sc)
    game.input.virtual = {"left"}
    for _ in range(40):
        game.tick()
    eaten = sc.total - len(sc.pellets)
    assert eaten >= 3, eaten
    hp = sc.hp
    c = sc.chuns[0]
    c.tile, c.p, c.d, c.scared = sc.akuma.tile, 0.0, "right", False
    _idle(game)
    assert sc.phase == "caught", sc.phase
    assert sc.hp == hp - sc.dmg and sc.dmg == round(game.akuma_max / 4), (hp, sc.hp)
    _idle(game, P.CATCH_FREEZE + 2)
    assert sc.phase == "ready", sc.phase
    assert sc.akuma.tile == P.START and sc.akuma.p == 0
    assert sc.chuns[0].tile == P.EXIT and all(k.state == "pen" for k in sc.chuns[1:])
    assert sc.total - len(sc.pellets) == eaten, "pellets came back"
    _to_play(game, sc)
    print("caught: hp %d -> %d, positions reset, %d pellets stay eaten" % (hp, sc.hp, eaten))


def check_ko(game):
    game.scene = sc = PacmanScene(game, seed=5, level=5)
    _to_play(game, sc)
    sc.power_up()
    assert sc.fright == P.FRIGHT and all(c.scared for c in sc.chuns)
    c = sc.chuns[0]
    ko_cid = c.cid
    c.tile, c.p, c.d = sc.akuma.tile, 0.0, "left"
    score = sc.score
    _idle(game)
    assert c.state == "eyes" and not c.scared, c.state
    assert sc.score == score + P.KO_PTS[0], sc.score
    assert sc.hp == game.akuma_max and sc.phase == "play"
    assert sc.freeze == P.KO_FREEZE
    _idle(game, P.KO_FREEZE)
    shot(game, "pacman_ko.png")
    c2 = sc.chuns[1]
    c2.state, c2.tile, c2.p, c2.d = "out", sc.akuma.tile, 0.0, "left"
    score = sc.score
    _idle(game)
    assert c2.state == "eyes" and sc.score == score + P.KO_PTS[1], sc.score
    n = 0
    while c.state != "out" and n < 60 * 20:
        sc.hp = sc.max_hp
        _idle(game)
        n += 1
    assert c.state == "out", "KO'd chaser never came back out of the pen"
    assert sc.tagged >= 1 and c.cid != ko_cid, ("KO'd chaser didn't tag out", ko_cid, c.cid)
    assert len(set(k.cid for k in sc.chuns)) == 4, [k.cid for k in sc.chuns]
    print("ko: two KOs for %d + %d, back out of the pen after %d frames" % (P.KO_PTS[0], P.KO_PTS[1], n))


def check_lose(game, calls):
    game.scene = sc = PacmanScene(game, seed=5, level=5)
    _to_play(game, sc)
    sc.hp = 1
    c = sc.chuns[0]
    c.tile, c.p, c.d = sc.akuma.tile, 0.0, "left"
    _idle(game)
    n = 0
    while sc.result is None and n < 600:
        _idle(game)
        n += 1
    assert sc.result == "lose" and calls[-1][:2] == ("level_failed", sc), calls[-1:]
    print("lose: level_failed after %d frames" % n)


def check_clear(game, calls):
    game.scene = sc = PacmanScene(game, seed=5, level=5)
    inp = game.input
    frames = 0
    shot_at = 60 * 25
    kos = 0
    while sc.result is None and frames < MAX_FRAMES:
        if frames % 60 == 0:
            sc.hp = sc.max_hp                         # the bot can't lose
        d = bot_dir(sc) if sc.phase == "play" else None
        inp.virtual = {d} if d else set()
        before = sum(c.state == "eyes" for c in sc.chuns)
        game.tick()
        kos += sum(c.state == "eyes" for c in sc.chuns) > before
        frames += 1
        if frames == shot_at:
            shot(game, "pacman.png")
        if sc.phase == "won" and sc.end_t == 20:
            shot(game, "pacman_won.png")
    assert sc.result == "win", "bot didn't clear the maze: %d pellets left after %d frames" % (
        len(sc.pellets), frames)
    assert calls[-1][:2] == ("level_done", sc) and calls[-1][2] >= 1, calls[-1:]
    print("clear: %d pellets in %.1f s (%d frames), caught %d times, %d KOs, score %d" % (
        sc.total, frames / 60, frames, sc.catches, kos, sc.score))


def check_roster(game):
    rosters = set()
    for seed in range(12):
        sc = PacmanScene(game, seed=seed, level=5)
        cids = [c.cid for c in sc.chuns]
        assert len(set(cids)) == 4 and all(c in P.ROSTER for c in cids), cids
        assert [c.i for c in sc.chuns] == [0, 1, 2, 3]
        assert set(sc.bench) == set(P.ROSTER) - set(cids)
        rosters.add(tuple(cids))
    assert len(rosters) >= 6, rosters
    for cid in P.ROSTER:
        art = P.chaser_art(cid)
        w, h = art.size
        assert h <= P.CHASER_H + 1 and w <= P.CHASER_W + 1 and h >= 18, (cid, art.size)
    print("roster: %d different line-ups over 12 runs, %d fighters all fit the maze"
          % (len(rosters), len(P.ROSTER)))


def check_pause(game):
    game.scene = sc = PacmanScene(game, seed=5, level=5)
    _to_play(game, sc)
    game.input.virtual_pressed = {"start"}
    game.tick()
    assert sc.paused
    t = sc.t
    _idle(game, 10)
    assert sc.t == t
    game.input.virtual_pressed = {"controls"}
    game.tick()
    shot(game, "pacman_controls.png")
    game.input.virtual_pressed = {"back"}
    game.tick()
    game.input.virtual_pressed = {"back"}
    game.tick()
    assert not sc.paused
    print("pause: freezes the maze, controls page ok")


def test_pacman(game):
    calls = _hook(game)
    game.input.virtual = set()
    game.scene = sc = PacmanScene(game, seed=5, level=5)
    assert sc.hp == game.akuma_max
    assert len(sc.power) == 4 and sc.total == len(sc.pellets)
    _idle(game, 30)
    shot(game, "pacman_intro.png")
    check_roster(game)
    check_pause(game)
    check_caught(game)
    check_ko(game)
    check_lose(game, calls)
    check_clear(game, calls)
    print("pacman test passed")


if __name__ == "__main__":
    from akuma.game import Game
    test_pacman(Game())
