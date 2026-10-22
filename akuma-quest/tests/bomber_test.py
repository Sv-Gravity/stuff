"""Headless test of level 4 (the car park): a bot plants hadouken bombs next to
the cars, hides from its own blasts, and wrecks every car. Also checks that a
headlight beam and Akuma's own blast hurt him.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/bomber_test.py
"""

import os
import sys
from collections import deque

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from akuma import bomber as B  # noqa: E402
from akuma.bomber import BomberScene  # noqa: E402

SHOTS = os.environ.get("SHOTS")
MAX_FRAMES = 60 * 300


def shot(game, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOTS, name))


def _tick(game, held=(), press=()):
    game.input.virtual = set(held)
    game.input.virtual_pressed = set(press)
    game.tick()


def _bfs(sc, start, goal_fn, avoid=()):
    q = deque([start])
    prev = {start: None}
    while q:
        c = q.popleft()
        if goal_fn(c):
            path = []
            while c != start:
                path.append(c)
                c = prev[c]
            return path[::-1]
        for dx, dy in B.DIRS.values():
            n = (c[0] + dx, c[1] + dy)
            if n not in prev and sc._free_for_akuma(*n) and n not in avoid:
                prev[n] = c
                q.append(n)
    return None


def _toward(sc, cell):
    """Arrow to hold to walk to the centre of a neighbouring cell."""
    tx, ty = B.center(cell[0]), B.center(cell[1])
    dx, dy = tx - sc.px, ty - sc.py
    if abs(dx) > abs(dy):
        return "right" if dx > 0 else "left"
    if abs(dy) > 0.5:
        return "down" if dy > 0 else "up"
    return None


def _reaches(sc, bomb_cell, fire, target):
    if bomb_cell == target:
        return True
    for dx, dy in B.DIRS.values():
        for k in range(1, fire + 1):
            c = (bomb_cell[0] + dx * k, bomb_cell[1] + dy * k)
            if sc._cell(*c) != B.EMPTY:
                break
            if c == target:
                return True
    return False


def bot_bomber(game, label=""):
    sc = game.scene
    assert isinstance(sc, BomberScene)
    frames = 0
    while sc.phase == "intro":
        _tick(game)
        frames += 1
    mode, plan = "hunt", []
    while game.scene is sc and sc.result is None and frames < MAX_FRAMES:
        frames += 1
        if frames % 30 == 0:
            sc.hp = max(sc.hp, sc.max_hp // 2)
        if sc.phase != "play":
            _tick(game)
            continue
        here = sc.akuma_cell
        danger = sc._danger()
        cars = [c for c in sc.cars if c.alive]
        press = ()
        if here in danger or mode == "hide":
            # get to the nearest cell no blast can reach, then wait there
            path = _bfs(sc, here, lambda c: c not in danger)
            mode = "hide" if (path or here in danger) else "hunt"
            if here not in danger and not sc.bombs and not sc.blasts:
                mode = "hunt"
            step = path[0] if path else here
        else:
            car_cells = {(c.target or (c.cx, c.cy)) for c in cars} | {(c.cx, c.cy) for c in cars}

            def good(cell):
                if cell in danger:
                    return False
                if not any(_reaches(sc, cell, sc.fire, cc) for cc in car_cells):
                    return False
                # only bomb from a spot with somewhere safe to run to
                fake = set(danger) | {cell}
                for dx, dy in B.DIRS.values():
                    for k in range(1, sc.fire + 1):
                        c2 = (cell[0] + dx * k, cell[1] + dy * k)
                        if sc._cell(*c2) != B.EMPTY:
                            break
                        fake.add(c2)
                return _bfs(sc, cell, lambda c: c not in fake) is not None
            if good(here) and not sc._bomb_at(*here):
                press = ("punch",)
                mode = "hide"
                step = here
            else:
                path = _bfs(sc, here, good, avoid=danger)
                if path is None:
                    # nothing reachable: blast a crate to open the lot up
                    path = _bfs(sc, here, lambda c: any(sc._cell(c[0] + dx, c[1] + dy) == B.CRATE
                                                        for dx, dy in B.DIRS.values()), avoid=danger)
                    if path == []:
                        press = ("punch",)
                        mode = "hide"
                step = path[0] if path else here
        d = _toward(sc, step)
        _tick(game, (d,) if d else (), press)
        if frames == 600 and label:
            shot(game, label)
    assert sc.result == "win", (sc.result, [c.hp for c in sc.cars], frames)
    return frames


def test_hazards(game):
    sc = BomberScene(game, seed=11)
    game.scene = sc
    while sc.phase != "play":
        _tick(game)
    # headlights straight down Akuma's lane
    car, beam = None, []
    for c in sc.cars:
        for d in B.DIRS:
            c.dir, c.target = d, None
            if not beam and sc._beam(c):
                car, beam = c, sc._beam(c)
                break
    assert beam, "no car has a lane to light"
    car.state, car.t = "lights", 0
    sc.px, sc.py = float(B.center(beam[0][0])), float(B.center(beam[0][1]))
    for c in sc.cars:
        if c is not car:
            c.state, c.cool = "wreck", 999
    hp = sc.hp
    for _ in range(B.LIGHTS_WARN + 4):
        sc.px, sc.py = float(B.center(beam[0][0])), float(B.center(beam[0][1]))
        _tick(game)
    assert sc.hp == hp - B.DMG_BEAM, ("beam", hp, sc.hp)
    # own blast
    sc.invuln = 0
    car.state, car.cool = "drive", 999
    hp = sc.hp
    _tick(game, press=("punch",))
    for _ in range(B.FUSE + 2):
        _tick(game)
    assert sc.hp < hp, "own blast did no damage"
    print("bomber hazards: beam %d, own blast ok" % B.DMG_BEAM)


def test_one_hit(game):
    """One blast on a car's cell wrecks it outright."""
    sc = BomberScene(game, seed=3)
    game.scene = sc
    while sc.phase != "play":
        _tick(game)
    assert B.CAR_HP == 1, B.CAR_HP
    car = sc.cars[0]
    kills = game.kills
    cell = (round((car.x - B.T / 2) / B.T), round((car.y - B.T / 2) / B.T))
    sc.invuln = 999
    sc.blasts[cell] = [B.BLAST_LIFE, "c", 4242]
    sc._blasts()
    assert not car.alive, ("car survived one blast", car.hp, car.state)
    assert game.kills == kills + 1
    assert all(c.alive for c in sc.cars[1:]), "other cars hit"
    print("bomber: one blast wrecks a car")


def test_bomber(game):
    test_one_hit(game)
    test_hazards(game)
    game.scene = BomberScene(game, seed=5)
    f = bot_bomber(game, "bomber.png")
    print("bomber: every car wrecked in %.1f s" % (f / 60))


if __name__ == "__main__":
    from akuma.game import Game
    g = Game()
    g.level_done = lambda scene, hp: None
    g.level_failed = lambda scene: None
    test_bomber(g)
    print("bomber test passed")
