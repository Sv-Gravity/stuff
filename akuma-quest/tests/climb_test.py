"""Headless test of The Climb (the Fall Guys style climbing race).

Checks that every platform of the tower can be jumped to from the one before
it (a jump the racers' own planner finds, timing the moving ones), that
moving platforms carry whoever stands on them, bounce pads launch, crumble
tiles fall and come back, ghost blocks blink, ledges catch a fall, that the
obstacles (sweeper, hammer, glove, fruit) add damage % and knock harder at
high %, that a fighter knocked off the side respawns on the floor at 0%,
that the first to touch the FINISH wins (a rival winning costs a try; three
lost tries fail the level), and then a bot (the rivals' own brain driving
Akuma) races four CPUs to the crown and clears the level.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/climb_test.py
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from akuma import climb as C  # noqa: E402
from akuma.climb import ClimbScene  # noqa: E402

SHOTS = os.environ.get("SHOTS", os.path.join(ROOT, "screenshots"))
MAX_FRAMES = 60 * 60 * 15


def shot(game, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOTS, name))


def _tick(game, held=(), press=()):
    game.input.virtual = set(held)
    game.input.virtual_pressed = set(press)
    game.tick()


def _start(game, seed=1, cpu=False):
    sc = ClimbScene(game, seed=seed)
    game.scene = sc
    sc.cpu_enabled = cpu
    while sc.phase == "intro":
        _tick(game)
    return sc


def _park_cpus(sc):
    """Rivals out of the way: standing still at the far end of the floor."""
    for k, f in enumerate(sc.cpus):
        _put(f, sc.plats[0], C.CW - 20.0 - k * 4)


def _put(f, p, x=None):
    f.x = p.cx if x is None else float(x)
    f.y = p.y
    f.on = p
    f.vx = f.vy = f.lvx = f.lvy = 0.0
    f.airborne = False
    f.state, f.t, f.invuln, f.hitstun = "stand", 0, 0, 0
    f.move = None


def _find(sc, kind, **kw):
    for p in sc.plats:
        if p.kind == kind and all(getattr(p, k) == v for k, v in kw.items()):
            return p
    raise AssertionError("no %s platform" % kind)


def test_course(game):
    """From every platform, some takeoff spot and moment reaches the next one."""
    sc = _start(game)
    ak = sc.akuma
    brain = C.ClimbBrain(sc, ak, C.random.Random(0), skill=1.0)
    brain.aim = 0.0
    plats = sc.plats
    for a, b in zip(plats, plats[1:]):
        ok = False
        cands = [p for p in plats if p.y > b.y - 40 and p.y < a.y + 200]
        for dt in range(0, 400, 10):            # wait for moving / blinking ones
            t = sc.course_t + dt
            ax0, _ = a.pos(t)
            if not a.lit(t):
                continue
            lo, hi = (8, C.CW - 8) if a.kind == "floor" else (ax0 + 4, ax0 + a.w - 4)
            for k in range(9):
                x = lo + (hi - lo) * k / 8
                for dj in C.DJ_OPTIONS:
                    saved = sc.course_t
                    sc.course_t = t
                    if a.kind == "bounce":      # you don't jump off a bounce pad, it throws you
                        hit = brain.simulate(x, a.pos(t)[1], 0.0, C.BOUNCE_V, 1, True, b, dj, cands)
                    else:
                        hit = brain.simulate(x, a.pos(t)[1], 0.0, 0.0, 1, False, b, dj, cands)
                    sc.course_t = saved
                    if hit is not None and hit.idx >= b.idx:
                        ok = True
                        break
                if ok:
                    break
            if ok:
                break
        assert ok, ("can't get from platform %d (%s, rise %d) to %d (%s, rise %d)"
                    % (a.idx, a.kind, C.FLOOR - a.by, b.idx, b.kind, C.FLOOR - b.by))
    hard = [n for _, _, n in C.HARD]
    kinds = {p.kind for p in plats}
    assert {"move", "belt", "bounce", "crumble", "blink", "finish"} <= kinds, kinds
    assert {h.kind for h in sc.hazards} == {"sweep", "pend", "piston", "cannon"}
    assert plats[-1] is sc.finish and C.FLOOR - sc.finish.y == C.FINISH_RISE
    print("climb course: %d platforms, %d obstacles, every hop makes it; hard spots: %s"
          % (len(plats), len(sc.hazards), ", ".join(hard)))


def test_platforms(game):
    sc = _start(game, seed=2)
    _park_cpus(sc)
    ak = sc.akuma
    # a side-to-side platform carries Akuma along
    mv = _find(sc, "move", ay=0)
    _put(ak, mv)
    off = ak.x - mv.x0
    xs = []
    for _ in range(60):
        _tick(game)
        xs.append(ak.x)
    assert ak.on is mv and not ak.airborne, (ak.state, ak.on and ak.on.idx)
    assert abs((ak.x - mv.x0) - off) < 1.0, ("slid off the mover", off, ak.x - mv.x0)
    assert max(xs) - min(xs) > 8, "the mover never moved"
    # an up-and-down one too
    lift = _find(sc, "move", ax=0)
    _put(ak, lift)
    ys = []
    for _ in range(80):
        _tick(game)
        ys.append(ak.y)
    assert ak.on is lift and abs(ak.y - lift.y) < 0.01 and max(ys) - min(ys) > 8, (ak.y, lift.y)
    # a belt drags you
    belt = _find(sc, "belt")
    _put(ak, belt)
    x0 = ak.x
    for _ in range(30):
        _tick(game)
    assert (ak.x - x0) * belt.belt > 10, ("belt", x0, ak.x)
    # a bounce pad launches you way up
    pad = _find(sc, "bounce")
    _put(ak, pad)
    ak.y -= 30
    ak.airborne, ak.on, ak.state = True, None, "air"
    top = ak.y
    for _ in range(50):
        _tick(game)
        top = min(top, ak.y)
    assert pad.y - top > 100, ("bounce", pad.y - top)
    # a crumble tile drops you a moment after you land, then comes back
    tile = _find(sc, "crumble")
    _put(ak, tile)
    ak.y -= 10
    ak.airborne, ak.on, ak.state = True, None, "air"
    for _ in range(12):
        _tick(game)
    assert ak.on is tile and tile.crumble > 0, ("didn't land on the crumble tile", ak.on and ak.on.idx)
    for _ in range(40):
        _tick(game)
    assert tile.gone > 0 and ak.on is not tile, "the tile held"
    for _ in range(210):
        _tick(game)
    assert tile.gone == 0 and tile.active(sc.course_t), "the tile never came back"
    # ghost blocks blink: there and not there
    g = _find(sc, "blink")
    seen = {g.lit(sc.course_t + k) for k in range(g.on_t + g.off_t)}
    assert seen == {True, False}
    # a ledge catches you when you hold toward it
    p = sc.plats[1]
    ak.x, ak.y = p.x0 - 8, p.y - 6
    ak.vx, ak.vy, ak.airborne, ak.on, ak.state = 0.0, 1.0, True, None, "air"
    for _ in range(20):
        _tick(game, ("right",))
        if ak.state == "ledge":
            break
    assert ak.state == "ledge" and ak.on is p, ak.state
    print("climb platforms: movers carry, belt drags, bounce pad launches %d px, crumble tile falls and "
          "returns, ghost blocks blink, ledge grab" % (pad.y - top))


def _hazard_hit(game, sc, kind, pct):
    """Akuma standing where an obstacle of this kind is about to hit; returns (damage, flight)."""
    ak = sc.akuma
    for h in sc.hazards:
        if h.kind != kind:
            continue
        for p in sc.plats:
            if abs(p.y - h.y) > 70:
                continue
            for dt in range(0, 300, 3):
                t = sc.course_t + dt
                for k in range(11):
                    x = p.pos(t)[0] + p.w * k / 10
                    box = (x - ak.half_w, p.y - ak.hgt, x + ak.half_w, p.y)
                    if h.hit(box, t) is None or not p.lit(t):
                        continue
                    # stand there just before it comes (static platforms only, so it stays put)
                    if p.kind not in ("static", "floor"):
                        continue
                    for _ in range(max(0, dt - 4)):
                        _tick(game)
                    _put(ak, p, x)
                    ak.pct = float(pct)
                    sx = ak.x
                    for _ in range(30):
                        _tick(game)
                        if ak.pct > pct:
                            break
                    hit = ak.pct - pct
                    for _ in range(40):
                        _tick(game)
                    return hit, abs(ak.x - sx)
    raise AssertionError("no spot for %s" % kind)


def test_obstacles(game):
    out = []
    for kind in ("sweep", "pend", "piston", "cannon"):
        sc = _start(game, seed=3)
        _park_cpus(sc)
        dmg, low = _hazard_hit(game, sc, kind, 0)
        assert dmg > 0, (kind, "never hit")
        sc = _start(game, seed=3)
        _park_cpus(sc)
        dmg2, high = _hazard_hit(game, sc, kind, 120)
        assert dmg2 > 0, (kind, "never hit at 120%")
        assert high > low, (kind, "flew no further at 120%", low, high)
        out.append("%s +%d%% (%d px at 0%%, %d px at 120%%)" % (kind, dmg, low, high))
    print("climb obstacles: " + ", ".join(out))


def test_knockoff(game):
    """Launched off the side high up: back on the floor at 0%."""
    sc = _start(game, seed=4)
    _park_cpus(sc)
    ak, cpu = sc.akuma, sc.cpus[0]
    p = sc.plats[12]
    _put(ak, p, p.x1 - 6)
    _put(cpu, p, p.x1 - 6 - sc.reach(cpu, "kick") + 2)
    cpu.facing, ak.facing = 1, -1
    ak.pct = 180.0
    cpu.start_move("kick")
    died = False
    for _ in range(200):
        _tick(game)
        died = died or ak.state == "dead"
        if died and ak.state != "dead":
            break
    assert died, ("not knocked off", round(ak.x), round(ak.y), ak.pct)
    assert ak.falls == 1 and ak.pct == 0 and ak.invuln > 0, (ak.falls, ak.pct)
    for _ in range(40):
        _tick(game)
    assert ak.on is sc.plats[0] and not ak.airborne, ("didn't land on the floor", ak.state)
    print("climb knock-off: kicked off the tower at 180%%, back on the floor at 0%% (rise %d)" % ak.rise)


def test_finish(game):
    """First to the crown wins; a rival winning uses up a try."""
    done, failed = [], []
    old = game.level_done, game.level_failed
    game.level_done = lambda scene, hp: done.append(hp)
    game.level_failed = lambda scene: failed.append(1)
    try:
        sc = _start(game, seed=5)
        _park_cpus(sc)
        for k in range(C.TRIES):
            cpu = sc.cpus[k]
            _put(cpu, sc.finish)
            cpu.y -= 20
            cpu.airborne, cpu.on, cpu.state = True, None, "air"
            for _ in range(30):
                _tick(game)
            assert sc.winner is cpu and sc.phase == "game" and not sc.won, (sc.phase, sc.winner)
            if k == 0:
                shot(game, "climb_lose.png")
            while sc.phase == "game":
                _tick(game)
            if k < C.TRIES - 1:
                assert sc.round == k + 2, sc.round
                while sc.phase == "intro":
                    _tick(game)
                sc.cpu_enabled = False
                _park_cpus(sc)
        assert sc.phase == "final" and sc.tries == [c.name for c in sc.cpus[:C.TRIES]], (sc.phase, sc.tries)
        for _ in range(C.FINAL_LEN + 5):
            _tick(game)
        assert failed and not done, "three lost tries did not fail the level"
        # and Akuma getting there first clears it
        sc = _start(game, seed=6)
        _park_cpus(sc)
        ak = sc.akuma
        _put(ak, sc.finish)
        ak.y -= 20
        ak.airborne, ak.on, ak.state = True, None, "air"
        for _ in range(30):
            _tick(game)
        assert sc.winner is ak and sc.won, sc.winner
        while sc.phase != "final":
            _tick(game)
        for _ in range(C.FINAL_LEN + 5):
            _tick(game)
        assert done and sc.result == "win", (done, sc.result)
    finally:
        game.level_done, game.level_failed = old
    print("climb finish: first to the crown wins, %d lost tries fail the level" % C.TRIES)


def bot_climb(game, label="climb.png"):
    """Akuma driven by the rivals' brain (at its sharpest) until he takes the crown."""
    sc = game.scene
    assert isinstance(sc, ClimbScene)
    brain = C.ClimbBrain(sc, sc.akuma, C.random.Random(1), skill=1.0)
    frames = 0
    tries = 0
    shot_at = None
    while game.scene is sc and sc.result is None and frames < MAX_FRAMES:
        frames += 1
        if brain.sc is not sc or brain.me is not sc.akuma:     # a new try: new fighters
            brain = C.ClimbBrain(sc, sc.akuma, C.random.Random(frames), skill=1.0)
        if sc.phase == "play":
            it = brain.think()
            _tick(game, it.held_actions(), it.pressed_actions())
            near = any(f.on_field and abs(f.y - sc.akuma.y) < 70 for f in sc.cpus)
            if label and shot_at is None and (sc.akuma.rise > 400 and near or sc.akuma.rise > 1300):
                shot_at = frames
                shot(game, label)
        else:
            if sc.phase == "game" and sc.end_t == 1:
                tries += 1
            _tick(game)
    assert sc.result == "win", (sc.result, frames, sc.tries,
                                [(f.name, int(f.best), f.falls, int(f.pct)) for f in sc.fighters])
    return frames, sc.tries


def test_run(game):
    game.new_run(seed=77, start=11)
    sc = game.scene
    assert isinstance(sc, ClimbScene), sc
    names = [f.name for f in sc.cpus]
    for _ in range(100):
        game.tick()
    shot(game, "climb_intro.png")
    frames, tries = bot_climb(game)
    print("climb: bot beat %s to the crown in %.1f s (tries: %s)" % (", ".join(names), frames / 60, tries))


def test_climb(game):
    test_course(game)
    test_platforms(game)
    test_obstacles(game)
    test_knockoff(game)
    test_finish(game)
    game.to_title()
    test_run(game)
    from akuma.game import LevelClear
    assert isinstance(game.scene, LevelClear) and game.scene.level == 11, game.scene
    game.to_title()


if __name__ == "__main__":
    from akuma.game import Game
    g = Game()
    test_climb(g)
    print("OK")
