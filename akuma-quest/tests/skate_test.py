"""Headless test of level 9 (the skate park, 720 Degrees style): picking up the
board, a 360, a kickflip, a crooked landing, the ghost after the clock runs out,
and a bot that rolls the course and lands tricks off the kickers until 100 points.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/skate_test.py
"""

import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from akuma import skate as S  # noqa: E402
from akuma.skate import SkateScene  # noqa: E402

SHOTS = os.environ.get("SHOTS", os.path.join(ROOT, "screenshots"))
MAX_FRAMES = 60 * 120


def shot(game, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOTS, name))


def _tick(game, held=(), press=()):
    game.input.virtual = set(held)
    game.input.virtual_pressed = set(press)
    game.tick()


def _new(game, seed=1):
    sc = SkateScene(game, seed=seed)
    game.scene = sc
    while sc.phase == "intro":
        _tick(game)
    return sc


def _walk_to_board(game, sc):
    n = 0
    while sc.mode == "foot" and n < 600:
        held = []
        dx, dy = sc.board[0] - sc.px, sc.board[1] - sc.py
        if abs(dx) > 1:
            held.append("right" if dx > 0 else "left")
        if abs(dy) > 1:
            held.append("down" if dy > 0 else "up")
        _tick(game, held)
        n += 1
    assert sc.mode == "skate", "never reached the board"
    return n


def _place(sc, x, y, heading, speed=S.CRUISE):
    sc.px, sc.py, sc.z = float(x), float(y), 0.0
    sc.heading, sc.speed = float(heading), speed
    sc.air, sc.bail_t, sc.board_fly = False, 0, None


def _until_landed(game, sc, held_fn=lambda sc: (), limit=200):
    n = 0
    while (sc.air or n == 0) and n < limit:
        _tick(game, held_fn(sc))
        n += 1
    assert not sc.air, "never landed"


# --------------------------------------------------------------------------
def test_pickup(game):
    sc = _new(game)
    assert sc.mode == "foot" and not sc.timer_on
    _walk_to_board(game, sc)
    assert sc.banner and "SKATE OR DIE" in sc.banner[0], sc.banner
    assert sc.timer_on and sc.timer == S.TIME_LIMIT, sc.timer
    for _ in range(10):
        _tick(game)
    assert sc.timer == S.TIME_LIMIT - 10, sc.timer
    shot(game, "skate.png")
    print("skate: board picked up -> %r, clock running" % sc.banner[0])
    return sc


def test_tricks(game, sc):
    # a 360 on flat ground in the right-hand lane
    _place(sc, 637, 230, 90)
    score = sc.score
    _tick(game, press=("up",))
    assert sc.air
    _until_landed(game, sc, lambda sc: ("right",) if abs(sc.spin) < 360 - S.SPIN / 2 else ())
    assert sc.bail_t == 0, sc.bail_why
    assert sc.score == score + 25, (score, sc.score)
    assert sc.last_trick["spin"] == 360 and sc.last_trick["flips"] == 0, sc.last_trick
    print("skate: 360 landed -> %s" % sc.last_trick["name"])
    # a kickflip
    _place(sc, 637, 230, 90)
    score = sc.score
    _tick(game, press=("up",))
    _tick(game, press=("special",))
    assert sc.flip_t
    _until_landed(game, sc)
    assert sc.bail_t == 0, sc.bail_why
    assert sc.score == score + 25 and sc.last_trick["flips"] == 1 and sc.last_trick["spin"] == 0, sc.last_trick
    print("skate: kickflip landed -> %s" % sc.last_trick["name"])
    # a crooked landing: a quarter turn
    _place(sc, 637, 230, 90)
    score, bails = sc.score, sc.bails
    _tick(game, press=("up",))
    _until_landed(game, sc, lambda sc: ("right",) if abs(sc.spin) < 90 else ())
    assert sc.bails == bails + 1 and sc.bail_t > 0, (sc.bails, sc.bail_t)
    assert sc.score == score, (score, sc.score)
    print("skate: crooked landing -> bail (%s), no points" % sc.bail_why)
    # a kickflip still turning when the wheels come down
    while sc.bail_t:
        _tick(game)
    _place(sc, 637, 230, 90)
    score = sc.score
    _tick(game, press=("up",))
    for _ in range(25):
        _tick(game)
    _tick(game, press=("special",))
    _until_landed(game, sc)
    assert sc.bail_t > 0 and sc.score == score, ("mid-flip landing", sc.bail_why)
    print("skate: mid-flip landing -> bail (%s)" % sc.bail_why)


def test_ghost(game):
    sc = _new(game, seed=2)
    _walk_to_board(game, sc)
    failed = []
    old = game.level_failed
    game.level_failed = lambda scene: failed.append(scene)
    try:
        sc.timer = 2
        _tick(game)
        assert sc.ghost is None
        _tick(game)
        assert sc.ghost is not None, "no ghost at 0:00"
        for _ in range(40):
            _tick(game, ("down",))
        shot(game, "skate_ghost.png")
        assert sc.phase == "play"
        sc.ghost[0], sc.ghost[1] = sc.px + 4, sc.py
        _tick(game)
        assert sc.phase == "lost", sc.phase
        n = 0
        while sc.result is None and n < 300:
            _tick(game)
            n += 1
        assert sc.result == "lose" and failed == [sc], (sc.result, failed)
    finally:
        game.level_failed = old
    print("skate: clock ran out -> ghost, touch -> level_failed")


# --------------------------------------------------------------------------
def _runway_clear(sc, length):
    a = math.radians(sc.heading)
    for d in range(4, int(length), 4):
        x, y = sc.px + math.cos(a) * d, sc.py + math.sin(a) * d
        if sc.hits(x, y, 0) or sc.ground_at(x, y) > 0:
            return False
    return True


def bot_skate(game, label=True):
    """Walks to the board, then follows the painted route; spins and kickflips
    whenever it is in the air (off the kickers, or an ollie on a clear run)."""
    sc = game.scene
    assert isinstance(sc, SkateScene)
    frames = 0
    while sc.phase == "intro":
        _tick(game)
        frames += 1
    frames += _walk_to_board(game, sc)
    wp = 1
    trick_shot = False
    while game.scene is sc and sc.result is None and frames < MAX_FRAMES:
        frames += 1
        held, press = [], []
        if sc.phase != "play" or sc.bail_t:
            _tick(game)
            continue
        tx, ty = S.ROUTE[wp]
        if math.hypot(tx - sc.px, ty - sc.py) < 40:
            wp = (wp + 1) % len(S.ROUTE)
            tx, ty = S.ROUTE[wp]
        if sc.air:
            if sc.air_t <= 1 and not sc.flips and sc.air_frames_left() > S.FLIP_FRAMES + 3:
                press.append("special")
            left = sc.air_frames_left()
            best = abs(sc.spin) + left * S.SPIN
            target = int((best - 4) // 180) * 180
            if target - abs(sc.spin) >= S.SPIN / 2:
                held.append("right")
            if sc.score > 0 and abs(sc.spin) > 300 and not trick_shot and label:
                trick_shot = True
                _tick(game, held, press)
                shot(game, "skate_trick.png")
                continue
        else:
            want = math.degrees(math.atan2(ty - sc.py, tx - sc.px))
            diff = S._wrap(want - sc.heading)
            if diff > S.TURN / 2:
                held.append("right")
            elif diff < -S.TURN / 2:
                held.append("left")
            if sc.speed < 2.2 and not sc.push_cd:
                press.append("kick")
            run = sc.speed * 36 + 24
            r = sc.ramp_at(sc.px, sc.py)
            if r and sc.z > r["h"] - 2.5:
                press.append("up")              # pop off the lip for extra air
            # kickers first; flat-ground ollies only once half the clock is gone
            if (sc.timer < S.TIME_LIMIT // 2 and abs(diff) < 8 and sc.z == 0 and sc.speed > 1.0 and _runway_clear(sc, run)
                    and math.hypot(tx - sc.px, ty - sc.py) > run + 20):
                press.append("up")
        _tick(game, held, press)
    assert sc.result == "win", (sc.result, sc.score, sc.bails, frames)
    return frames, sc


def test_skate(game):
    sc = test_pickup(game)
    test_tricks(game, sc)
    test_ghost(game)
    done = []
    old = game.level_done
    game.level_done = lambda scene, hp: done.append((scene, hp))
    try:
        game.scene = SkateScene(game, seed=5)
        f, sc = bot_skate(game)
    finally:
        game.level_done = old
    assert done and done[0][0] is sc
    assert sc.score >= S.GOAL and sc.timer > 0
    print("skate: bot cleared the course with %d points in %.1f s (%d bails, %.0f s left): %s"
          % (sc.score, f / 60, sc.bails, sc.timer / 60, ", ".join(t["name"] for t in sc.tricks)))


if __name__ == "__main__":
    from akuma.game import Game
    g = Game()
    g.level_done = lambda scene, hp: None
    g.level_failed = lambda scene: None
    test_skate(g)
    print("skate test passed")
