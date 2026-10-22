"""Headless test of level 8 (the frozen compound, a sneaking level).

Checks the soldiers' sight (light vs shadow), the cardboard box, the
ALERT -> EVASION -> CAUTION -> normal countdown, that a soldier catching Akuma
starts a fight against rifles, and a bot walks to the elevator.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/stealth_test.py
"""

import math
import os
import sys
from collections import deque

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from akuma import stealth as S  # noqa: E402
from akuma.stealth import StealthScene, T  # noqa: E402

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


def _scene(game, seed=8):
    sc = StealthScene(game, seed, level=8)
    sc.stage = "play"
    game.overworld = sc
    game.scene = sc
    return sc


def _center(c):
    return (c[0] + 0.5) * T, (c[1] + 0.5) * T


def _aim(g, x, y):
    g.angle = g.look_base = math.atan2(y - 4 - (g.y - 4), x - g.x)
    g.look_t = 0


def _only(sc, g):
    for o in sc.guards:
        o.alive = o is g
    for c in sc.cameras:
        c["sweep"], c["base"] = 0, -math.pi / 2       # look at the wall
    g.route = [(g.x, g.y, 10 ** 9)]
    g.ri, g.wait, g.state = 0, 10 ** 9, "patrol"


def test_light_shadow(game):
    """Same distance, same cone: seen in the light, not in a shadow."""
    sc = _scene(game)
    g = sc.guards[0]
    light = [c for c in sc.passable if sc.tile(*c) in ".,"]
    shade = [c for c in sc.passable if sc.tile(*c) in ":;"]
    for gc in light:
        gx, gy = _center(gc)

        def ok(c):
            x, y = _center(c)
            d = math.hypot(x - gx, y - gy + 4)
            return 50 <= d <= 64 and sc.line_of_sight(gx, gy - 4, x, y - 4)
        s = next((c for c in shade if ok(c)), None)
        lt = next((c for c in light if ok(c)), None)
        if s and lt:
            break
    else:
        raise AssertionError("no spot to compare light and shadow")
    g.x, g.y = gx, gy
    for cell, want in ((lt, True), (s, False)):
        sc.px, sc.py = _center(cell)
        _aim(g, sc.px, sc.py)
        d = math.hypot(sc.px - g.x, sc.py - g.y)
        assert sc.guard_sees(g) is want, (cell, sc.tile(*cell), round(d), want)
    print("stealth: seen at %d px in light, unseen at %d px in shadow" % (
        math.hypot(_center(lt)[0] - gx, _center(lt)[1] - gy), math.hypot(_center(s)[0] - gx, _center(s)[1] - gy)))


def _open_spot(sc):
    """A guard tile in the light with a clear light row of floor to its right."""
    for c in sc.passable:
        row = [(c[0] + k, c[1]) for k in range(-1, 6)]
        if all(sc.tile(*r) == "," for r in row) and all(sc.tile(r[0], r[1] + dy) == ","
                                                         for r in row for dy in (-1, 1)):
            return c
    raise AssertionError("no open snow")


def test_box(game):
    sc = _scene(game)
    g = sc.guards[0]
    _only(sc, g)
    c = _open_spot(sc)
    g.x, g.y = _center(c)
    sc.px, sc.py = g.x + 52, g.y
    sc.has_box = sc.box_on = True
    sc.box_pickup = None
    for _ in range(90):                      # standing still in plain view
        _aim(g, sc.px, sc.py)
        _tick(game)
        assert sc.in_view(g.x, g.y - 4, g.angle, S.VIEW_HALF, S.VIEW_RANGE)
        assert g.state == "patrol" and sc.phase == "normal", (g.state, sc.phase)
    for _ in range(12):                      # shuffle a little: "?"
        _aim(g, sc.px, sc.py)
        _tick(game, ("up",))
        if g.state == "suspicious":
            break
    assert g.state == "suspicious" and g.huh, g.state
    assert sc.phase == "normal"
    d0 = math.hypot(g.x - sc.px, g.y - sc.py)
    for i in range(240):                     # stay still: he walks over to look
        _tick(game)
        if i == 70:
            shot(game, "stealth_box.png")
        if g.sub == "search":
            break
    d1 = math.hypot(g.x - sc.px, g.y - sc.py)
    assert g.sub == "search" and d1 < d0 - 20 and d1 < S.BOX_SPOT, (g.sub, d0, d1)
    assert sc.phase == "normal", sc.phase
    for _ in range(20):                      # move the box right under his nose
        _aim(g, sc.px, sc.py)
        _tick(game, ("left",))
        if sc.phase == "alert":
            break
    assert sc.phase == "alert", (sc.phase, g.state)
    print("stealth: still box unseen, moving box investigated from %d px to %d px, then found" % (d0, d1))


def test_alert_cycle(game):
    sc = _scene(game)
    for g in sc.guards:
        g.alive = False
    sc.has_box = sc.box_on = True         # hidden somewhere quiet
    sc.spotted()
    assert sc.phase == "alert" and sc.timer == S.ALERT_T
    for _ in range(S.FREEZE + 30):
        _tick(game)
    assert sc.phase == "alert" and sc.timer < S.ALERT_T - 20, sc.timer
    shot(game, "stealth_alert.png")
    seq = []
    for want in ("evasion", "caution", "normal"):
        sc.timer = 3
        for _ in range(5):
            _tick(game)
        assert sc.phase == want, (sc.phase, want)
        seq.append(want)
    # seen again during caution goes straight back to ALERT
    sc.phase, sc.timer = "caution", 500
    sc.spotted()
    assert sc.phase == "alert" and sc.timer == S.ALERT_T
    print("stealth: alert -> %s" % " -> ".join(seq))


def test_fight(game):
    from akuma.fight import FightScene
    sc = _scene(game)
    a, b = sc.guards[0], sc.guards[1]
    for g in sc.guards[2:]:
        g.alive = False
    c = _open_spot(sc)
    sc.px, sc.py = _center(c)
    a.x, a.y = sc.px + 30, sc.py
    b.x, b.y = sc.px - 40, sc.py
    sc.spotted(a)
    for _ in range(120):
        _tick(game)
        if game.scene is not sc:
            break
    fs = game.scene
    assert isinstance(fs, FightScene), type(fs)
    e = fs.enemy_ref
    assert e in (a, b) and e.name == "GENOME SOLDIER"
    guns = [ev["proj"] for m in e.moves for ev in m.get("events", {}).values() if "proj" in ev]
    assert guns and all(p["speed"] >= 6 and p["dmg"] >= 20 for p in guns), guns
    assert max(p["dmg"] for p in guns) >= 30
    assert len(e.allies) == 1, e.allies
    n_allies = len(e.allies)
    hp = 99
    game.end_fight(fs, "win", hp)
    assert game.scene is sc and sc.hp == hp
    assert not a.alive and not b.alive
    print("stealth: caught -> FightScene vs %s + %d ally, %d gun shots (max %d dmg); win removes both" % (
        e.name, n_allies, len(guns), max(p["dmg"] for p in guns)))


def bot_stealth(game, label="stealth.png"):
    """Walk to the elevator. Cheats: the soldiers ignore Akuma."""
    sc = game.scene
    assert isinstance(sc, StealthScene)
    frames = 0
    codec_shot = False
    while sc.stage != "play" and frames < 3000:
        _tick(game, press=("punch",) if frames % 40 == 39 else ())
        frames += 1
        if sc.stage == "codec" and sc.line == 2 and sc.chars >= 40 and label and not codec_shot:
            codec_shot = True
            shot(game, "stealth_codec.png")
    shot_done = not label
    sc.ignore_player = True
    goal = sc.exit_tiles
    while game.scene is sc and sc.result is None and frames < MAX_FRAMES:
        frames += 1
        if sc.stage != "play":
            _tick(game)
            continue
        here = (int(sc.px // T), int(sc.py // T))
        q, prev = deque([here]), {here: None}
        end = None
        while q:
            cur = q.popleft()
            if cur in goal:
                end = cur
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (cur[0] + dx, cur[1] + dy)
                if n not in prev and not sc.solid(*n):
                    prev[n] = cur
                    q.append(n)
        assert end, "no path to the elevator"
        step = end
        while prev[step] not in (here, None):
            step = prev[step]
        tx, ty = _center(step)
        held = []
        if abs(tx - sc.px) > 1:
            held.append("right" if tx > sc.px else "left")
        if abs(ty - sc.py) > 1:
            held.append("down" if ty > sc.py else "up")
        _tick(game, held)
        if not shot_done and any(g.alive and abs(g.x - sc.px) < 110 and abs(g.y - sc.py) < 60
                                 for g in sc.guards):
            shot_done = True
            shot(game, label)
    assert sc.result == "win", (sc.result, sc.stage, frames)
    return frames


def test_stealth(game):
    test_light_shadow(game)
    test_box(game)
    test_alert_cycle(game)
    test_fight(game)
    game.overworld = game.scene = StealthScene(game, 8, level=8)
    f = bot_stealth(game)
    print("stealth: bot reached the elevator in %.1f s" % (f / 60))


if __name__ == "__main__":
    from akuma.game import Game
    g = Game()
    g.level = 8
    g.level_done = lambda scene, hp: None
    g.level_failed = lambda scene: None
    test_stealth(g)
    print("stealth test passed")
