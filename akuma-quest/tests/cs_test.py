"""Headless test of level 12 (DUST II, the Counter-Strike round): every site
can be reached from T spawn, planting needs a site and a still Akuma, a CT
defuses a bomb it reaches and a hit stops it, the clock running out loses,
the bomb going off wins, and a bot plays a whole round for real (walks to B,
fights the CTs with hadoukens and kicks, plants, holds the site).

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/cs_test.py
"""

import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from akuma import cs as C  # noqa: E402
from akuma import doom as D  # noqa: E402
from akuma.cs import CsScene  # noqa: E402
from tests.doom_test import _angdiff, _path, _quiet, _tick, shot  # noqa: E402

MAX_FRAMES = 60 * 180


def _fresh(game, **kw):
    sc = CsScene(game, seed=kw.pop("seed", 7), **kw)
    game.scene = sc
    while sc.phase == "intro":
        _tick(game)
    return sc


def _cell_in(sc, area):
    x0, y0, x1, y1 = sc.map.areas[area]
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if sc.map.grid[y, x] == 0 and sc.map.area_of(x, y) == area:
                return x, y
    raise AssertionError(area)


# ---- checks --------------------------------------------------------------
def test_layout(game):
    sc = _fresh(game)
    here = (int(sc.px), int(sc.py))
    assert sc.map.area_of(*here) == "start"
    for area in ("asite", "bsite", "ctspawn", "mid", "longa", "catwalk", "tunnels", "lowertuns"):
        p = _path(sc, here, _cell_in(sc, area))
        assert p, "no way from T spawn to %s" % area
    assert len(sc.enemies) == 3 and {e.kind for e in sc.enemies} == {"ryu", "ken", "chunli"}
    assert sc.boss is None
    shot(game, "cs.png")


def _plant_at(game, sc, area, cell=None):
    x, y = cell or _cell_in(sc, area)
    sc.px, sc.py = x + 0.5, y + 0.5
    _tick(game)
    for _ in range(C.PLANT_T + 2):
        _tick(game, held={"shield"})
        if sc.bomb:
            break


def test_plant_rules(game):
    sc = _fresh(game)
    _quiet(sc)
    # holding shield off-site does nothing
    for _ in range(C.PLANT_T + 10):
        _tick(game, held={"shield"})
    assert sc.bomb is None and sc.plant == 0
    # on site, moving resets the plant
    sc.px, sc.py, sc.ang = 6.5, 7.5, -math.pi / 2
    for _ in range(C.PLANT_T // 2):
        _tick(game, held={"shield"})
    assert sc.plant > 0
    shot(game, "cs_planting.png")
    _tick(game, held={"shield", "left"})
    assert sc.plant == 0 and sc.bomb is None
    _plant_at(game, sc, "bsite")
    assert sc.bomb is not None and sc.bomb.site == "B", "the bomb was not planted"
    # A works too
    sc = _fresh(game)
    _quiet(sc)
    _plant_at(game, sc, "asite")
    assert sc.bomb is not None and sc.bomb.site == "A"


def test_defuse(game):
    sc = _fresh(game)
    ken = next(e for e in sc.enemies if e.kind == "ken")
    _quiet(sc, keep=(ken,))
    _plant_at(game, sc, "bsite")
    b = sc.bomb
    # Akuma walks off; Ken is put near the bomb and has to find it on his own
    sc.px, sc.py = 19.5, 28.5
    ken.x, ken.y = 6.5, 14.5
    for _ in range(60 * 20):
        _tick(game)
        if sc.defuser:
            break
    assert sc.defuser is ken, "ken never reached the bomb (%.1f, %.1f)" % (ken.x, ken.y)
    for _ in range(60):
        _tick(game)
    assert sc.defuse > 30
    shot(game, "cs_defusing_far.png")
    # a hit stops the defuse and resets it
    sc._damage(ken, 1)
    assert sc.defuser is None and sc.defuse == 0
    # left alone he finishes it: the CTs win
    lost = []
    old = game.level_failed
    game.level_failed = lambda scene: lost.append(1)
    for _ in range(C.DEFUSE_T + 60 * 8):
        _tick(game)
        if sc.phase == "ctwin":
            break
    assert sc.phase == "ctwin" and "DEFUSED" in sc.why, (sc.phase, sc.defuse)
    shot(game, "cs_defused.png")
    for _ in range(220):
        _tick(game)
    game.level_failed = old
    assert lost and sc.result == "lose"
    assert b.x


def test_timeout(game):
    sc = _fresh(game)
    _quiet(sc)
    sc.round_t = 3
    for _ in range(5):
        _tick(game)
    assert sc.phase == "ctwin" and "TIME" in sc.why


def test_explosion(game):
    sc = _fresh(game)
    _quiet(sc)
    _plant_at(game, sc, "asite", (34, 8))
    sc.px, sc.py, sc.ang = 35.5, 15.5, -math.pi / 2       # back down long A to watch
    _tick(game)
    assert sc.bomb_t <= 150, "with every CT dead the bomb should not keep Akuma waiting"
    done = []
    old = game.level_done
    game.level_done = lambda scene, hp: done.append(hp)
    for _ in range(400):
        _tick(game)
        if sc.phase == "won" and sc.end_t == 12:
            shot(game, "cs_boom.png")
        if done:
            break
    game.level_done = old
    assert done and sc.result == "win"


# ---- the bot -----------------------------------------------------------------
def _target(sc):
    best = None
    for e in sc.enemies:
        if not e.alive:
            continue
        d = math.hypot(e.x - sc.px, e.y - sc.py)
        if d > 12 or not sc.map.los(sc.px, sc.py, e.x, e.y):
            continue
        k = d - (20 if e is sc.defuser else 0)
        if best is None or k < best[0]:
            best = (k, d, e)
    return best and best[1:]


def bot_cs(game, goal_area="bsite"):
    """Plays the round: walks to a site by BFS, turns onto any CT it can see
    and throws real hadoukens (auto-aim, and it keeps its health and ki
    topped up), plants, then holds the site, the defuser first."""
    sc = game.scene
    assert isinstance(sc, CsScene)
    frames = 0
    while sc.phase == "intro":
        _tick(game)
        frames += 1
    goal = (6, 6) if goal_area == "bsite" else (33, 6)
    fight_shot = plant_shot = False
    kick_cool = 0
    last_pos, stuck = (sc.px, sc.py), 0
    while game.scene is sc and sc.result is None and frames < MAX_FRAMES:
        frames += 1
        if frames % 30 == 0:
            sc.hp = max(sc.hp, sc.max_hp * 0.6)
            sc.ki = max(sc.ki, 25)
        if sc.phase != "play":
            _tick(game)
            continue
        held, press = set(), set()
        kick_cool -= 1
        tgt = _target(sc)
        on_site = sc.map.area_of(int(sc.px), int(sc.py)) == goal_area
        if tgt and not (sc.plant and sc.plant > C.PLANT_T * 0.7):
            d, e = tgt
            want = math.atan2(e.y - sc.py, e.x - sc.px)
            diff = _angdiff(want, sc.ang)
            tol = max(0.03, math.atan2(e.radius * 0.6, d))
            if abs(diff) > tol:
                held.add("right" if diff > 0 else "left")
                if abs(diff) < D.TURN_SPEED:
                    sc.ang = want
            else:
                held.add("special")
                if d > 5 and sc.bomb is None:
                    held.add("up")
            if d < 1.2 and kick_cool <= 0:
                press.add("kick")
                kick_cool = 25
            flying = [s for s in sc.shots if s.owner == "akuma" and s.t >= 8]
            if not fight_shot and 2.5 < d < 7 and flying and e.flash == 0:
                fight_shot = True
                _tick(game, held, press)
                shot(game, "cs_fight.png")
                continue
        elif sc.bomb is None and on_site and sc.weapon is None:
            held.add("shield")
            if not plant_shot and sc.plant > C.PLANT_T // 2:
                plant_shot = True
                _tick(game, held)
                shot(game, "cs_planting.png")
                continue
        elif sc.bomb is None:
            here = (int(sc.px), int(sc.py))
            path = _path(sc, here, goal) or [goal]
            nxt = path[0]
            g = sc.map.grid[nxt[1], nxt[0]]
            closed = g == D.DOOR and sc.map.doors[nxt].open < 0.95
            want = math.atan2(nxt[1] + 0.5 - sc.py, nxt[0] + 0.5 - sc.px)
            diff = _angdiff(want, sc.ang)
            if abs(diff) > 0.06:
                held.add("right" if diff > 0 else "left")
            if closed:
                if abs(diff) < 0.2 and kick_cool <= 0:
                    press.add("kick")
                    kick_cool = 30
            elif abs(diff) < 0.35:
                held.add("up")
        else:
            # hold the site: look at the bomb's side of the map, turning slowly
            held.add("left" if (frames // 90) % 2 else "right")
        _tick(game, held, press)
        moved = math.hypot(sc.px - last_pos[0], sc.py - last_pos[1])
        if "up" in held and moved < 0.002:
            stuck += 1
            if stuck > 40:
                for _ in range(12):
                    _tick(game, {"shield", "left" if (frames // 200) % 2 else "right"})
                stuck = 0
        else:
            stuck = 0
        last_pos = (sc.px, sc.py)
    assert sc.result == "win", (sc.result, sc.phase, sc.why, frames, (sc.px, sc.py), sc.bomb is not None,
                                [(e.kind, e.state, round(e.hp)) for e in sc.enemies])
    return frames


def test_cs(game):
    test_layout(game)
    test_plant_rules(game)
    test_defuse(game)
    test_timeout(game)
    test_explosion(game)
    done = []
    old = game.level_done
    game.level_done = lambda scene, hp: done.append(hp)
    for site, seed in (("bsite", 5), ("asite", 9)):
        game.scene = CsScene(game, seed=seed)
        sc = game.scene
        f = bot_cs(game, site)
        print("cs: bot won the round at %s in %.1f s (%d kills)" % (site[0].upper(), f / 60, sc.kills))
    game.level_done = old
    assert len(done) == 2


if __name__ == "__main__":
    from akuma.game import Game
    g = Game()
    g.level_done = lambda scene, hp: None
    g.level_failed = lambda scene: None
    test_cs(g)
    print("cs test passed")
