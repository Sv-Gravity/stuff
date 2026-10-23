"""Headless test of the frozen compound (a sneaking level).

Checks the soldiers' sight (light vs shadow), the cardboard box, bushes, the
ALERT -> EVASION -> CAUTION -> normal countdown, neck snaps (and a body being
found), soldiers on post staying put, smokers' short cones, snacks, that a
soldier catching Akuma starts a fight against rifles, and a bot that runs the
mission chain (keycard, C4, prisoner) and beats the boss.

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
MAX_FRAMES = 60 * 240


def shot(game, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOTS, name))


def _tick(game, held=(), press=()):
    game.input.virtual = set(held)
    game.input.virtual_pressed = set(press)
    game.tick()


def _scene(game, seed=8):
    sc = StealthScene(game, seed, level=getattr(game, "level", 8))
    sc.stage = "play"
    game.overworld = sc
    game.scene = sc
    return sc


def _center(c):
    return (c[0] + 0.5) * T, (c[1] + 0.5) * T


def _aim(g, x, y):
    g.angle = g.look_base = math.atan2(y - 4 - (g.y - 4), x - g.x)
    g.look_t = 0


def _plain(sc, k=0):
    return [g for g in sc.guards if g.kind == "guard"][k]


def _only(sc, g):
    for o in sc.guards:
        o.alive = o is g
    for c in sc.cameras:
        c["sweep"], c["base"] = 0, -math.pi / 2       # look at the wall
    g.route = [(g.x, g.y, 10 ** 9, None)]
    g.post = True
    g.ri, g.wait, g.state = 0, 10 ** 9, "patrol"
    g.cycle = 10 ** 9                                 # no glancing away
    g.chat_cd = 10 ** 9


def test_light_shadow(game):
    """Same distance, same cone: seen in the light, not in a shadow."""
    sc = _scene(game)
    g = _plain(sc)
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
    g = _plain(sc)
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
    assert g.say and "BOX" in g.say[0], g.say
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


def test_bush(game):
    """In a bush nobody sees him, even creeping about; a soldier bumping in finds him."""
    sc = _scene(game)
    bush = next((x, y) for x, y in sc.passable if sc.tile(x, y) == "b" and sc.tile(x + 1, y) == "b")
    g = _plain(sc)
    _only(sc, g)
    sc.px, sc.py = _center(bush)
    g.x, g.y = sc.px - 40, sc.py
    _aim(g, sc.px, sc.py)
    assert sc.visibility() == "hidden"
    for k in range(120):
        _aim(g, sc.px, sc.py)
        _tick(game, ("right", "kick") if (k // 30) % 2 == 0 else ("left", "kick"))   # sneaking: no footsteps
        sc.px = max(_center(bush)[0] - 4, min(_center(bush)[0] + T + 4, sc.px))
        assert sc.phase == "normal" and g.state == "patrol", (sc.phase, g.state)
    shot(game, "stealth_bush.png")
    g.x = sc.px - 2                           # he walks right into the bush
    g.angle = 0
    for _ in range(3):
        _tick(game)
    assert sc.phase == "alert", sc.phase
    print("stealth: unseen in a bush at 40 px (moving), found when bumped into")


def test_snap(game):
    """From behind: punch snaps an unaware soldier's neck, no fight; his body,
    left in view, puts the base on CAUTION when another soldier sees it."""
    sc = _scene(game)
    g, w = _plain(sc, 0), _plain(sc, 1)
    _only(sc, g)
    w.alive = True
    c = _open_spot(sc)
    g.x, g.y = _center(c)
    g.angle = g.look_base = 0.0                # looking right
    sc.px, sc.py = g.x - 40, g.y               # behind him
    w.x, w.y = g.x + 200, g.y + 300            # somewhere else for now
    w.route = [(w.x, w.y, 10 ** 9, math.pi)]
    w.post, w.wait, w.ri, w.cycle, w.chat_cd = True, 10 ** 9, 0, 10 ** 9, 10 ** 9
    for _ in range(80):
        if sc.snap_target() is g:
            break
        _tick(game, ("right", "kick"))         # sneak up
    assert sc.snap_target() is g, math.hypot(g.x - sc.px, g.y - sc.py)
    assert sc.phase == "normal" and g.state == "patrol"
    _tick(game, press=("punch",))
    assert sc.snap and sc.snap["g"] is g
    for i in range(S.SNAP_T + 4):
        _tick(game)
        if i == S.SNAP_KILL - 2:
            shot(game, "stealth_snap.png")
    assert not g.alive and len(sc.bodies) == 1 and sc.snap is None
    assert game.scene is sc and sc.phase == "normal"
    # front-on there is no snap
    sc.bodies.clear()
    w.x, w.y = sc.px + 14, sc.py
    w.angle = math.pi                           # looking at Akuma
    assert sc.snap_target() is None
    # the other one walks up and sees the body
    b = dict(x=g.x, y=g.y, img=pygame.Surface((4, 4)), found=False)
    sc.bodies.append(b)
    sc.px, sc.py = g.x - 300, g.y               # out of the way
    w.x, w.y = g.x + 50, g.y
    w.angle = w.look_base = math.pi
    w.route = [(w.x, w.y, 10 ** 9, math.pi)]
    sc.ignore_player = True
    for _ in range(5):
        _tick(game)
    sc.ignore_player = False
    assert b["found"] and sc.phase == "caution" and w.state == "suspicious", (b["found"], sc.phase, w.state)
    print("stealth: neck snapped from behind in %d frames, body found -> CAUTION" % S.SNAP_T)


def test_posts(game):
    """Soldiers on post stay put (only glancing about); smokers' cones are short."""
    sc = _scene(game)
    sc.ignore_player = True
    posts = [g for g in sc.guards if g.post]
    beats = [g for g in sc.guards if not g.post]
    assert len(posts) >= len(sc.guards) // 2, (len(posts), len(sc.guards))
    start = {g: (g.x, g.y) for g in posts}
    turned = {g: 0.0 for g in posts}
    still = {g: 0 for g in beats}
    for _ in range(900):
        a0 = {g: g.angle for g in posts}
        _tick(game)
        for g in posts:
            turned[g] += abs(g.angle - a0[g])
        for g in beats:
            still[g] += not g.moving
    for g in posts:
        assert (g.x, g.y) == start[g], g.kind
    assert sum(1 for g in posts if turned[g] > 0.5) >= 2, "nobody looks around"
    assert all(still[g] > 300 for g in beats), [still[g] for g in beats]
    smoker = next(g for g in sc.guards if g.kind == "smoker")
    elite = next(g for g in sc.guards if g.kind == "elite")
    assert smoker.range < S.VIEW_RANGE and smoker.half < S.VIEW_HALF
    assert elite.range > S.VIEW_RANGE and elite.hp > _plain(sc).hp and elite.name != _plain(sc).name
    assert any(g.puffs for g in sc.guards if g.kind == "smoker")
    print("stealth: %d posts held still for 15 s, beats paused %d%% of the time" % (
        len(posts), 100 * min(still.values()) // 900))


def test_snack(game):
    sc = _scene(game)
    sc.ignore_player = True
    it = next(i for i in sc.items if i["kind"] == "snack")
    sc.hp = 10
    sc.px, sc.py = it["x"], it["y"]
    _tick(game)
    assert it not in sc.items and sc.hp > 10
    assert sc.messages and it["name"] in sc.messages[0][0] and "+" in sc.messages[0][0], sc.messages
    print("stealth: picked up %s" % sc.messages[0][0])


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
    a, b = _plain(sc, 0), _plain(sc, 1)
    for g in sc.guards:
        if g not in (a, b):
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


# ---------------------------------------------------------------------------
def _walk(game, sc, goal, frames, label=None, near=None):
    """BFS-walk Akuma toward a set of goal tiles (or until near(sc) is true)."""
    shot_done = not label
    while game.scene is sc and frames[0] < MAX_FRAMES:
        if sc.stage != "play":
            return
        here = (int(sc.px // T), int(sc.py // T))
        if here in goal or (near and near(sc)):
            return
        frames[0] += 1
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
        assert end, ("no path", here, goal)
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


def _codecs(game, sc, frames, name=None):
    """Click through codec calls until back in play."""
    shot_done = name is None
    while sc.stage != "play" and frames[0] < MAX_FRAMES and game.scene is sc:
        frames[0] += 1
        _tick(game, press=("punch",) if frames[0] % 40 == 39 else ())
        if not shot_done and sc.stage == "codec" and sc.chars >= 40:
            shot_done = True
            shot(game, name)


def _adjacent(sc, tile):
    tx, ty = tile
    return {(tx + dx, ty + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)) if not sc.solid(tx + dx, ty + dy)}


def bot_stealth(game, label="stealth.png"):
    """Run the missions and beat the boss. Cheats: the soldiers ignore Akuma
    (he still walks everywhere), and the boss fight is won for him."""
    from akuma.fight import FightScene
    sc = game.scene
    assert isinstance(sc, StealthScene)
    frames = [0]
    _codecs(game, sc, frames, "stealth_codec.png" if label else None)
    sc.ignore_player = True
    # 1) the keycard in the barracks
    key = next(i for i in sc.items if i["kind"] == "keycard")
    _walk(game, sc, {(int(key["x"] // T), int(key["y"] // T))}, frames, label)
    assert sc.mission == 1 and sc.keycard and sc.c4 == 3, (sc.mission, sc.keycard)
    _codecs(game, sc, frames)
    # 2) C4 on every generator
    for gen in list(sc.gens):
        _walk(game, sc, _adjacent(sc, gen), frames)
        for _ in range(40):                       # step into the middle of the tile, face it
            cx, cy = _center((int(sc.px // T), int(sc.py // T)))
            held = [k for k, v in (("right", cx - sc.px > 1), ("left", sc.px - cx > 1),
                                   ("down", cy - sc.py > 1), ("up", sc.py - cy > 1)) if v]
            _tick(game, held)
        _tick(game, press=("punch",))
        assert sc.gens[gen], gen
    while sc.mission == 1 and frames[0] < MAX_FRAMES:
        frames[0] += 1
        _tick(game)
    assert sc.mission == 2 and not sc.power, (sc.mission, sc.power)
    _codecs(game, sc, frames)
    if label:
        _tick(game)
        shot(game, "stealth_blackout.png")
    # 3) the prisoner
    p = sc.prisoner
    _walk(game, sc, {(int(p.x // T), int(p.y // T))}, frames,
          near=lambda s: s.prisoner.free or s.stage != "play")
    assert p.free and sc.mission == 3
    _codecs(game, sc, frames, "stealth_codec2.png" if label else None)
    assert sc.boss_g is not None and sc.boss_g.boss
    # 4) the boss at the elevator
    for _ in range(150):
        _tick(game)
    b = sc.boss_g
    if label:
        ox, oy = sc.px, sc.py
        sc.px, sc.py = b.x - 60, b.y + 30
        _tick(game)
        shot(game, "stealth_boss.png")
        sc.px, sc.py = ox, oy
    while game.scene is sc and frames[0] < MAX_FRAMES:
        _walk(game, sc, {(int(b.x // T), int(b.y // T))}, frames, near=lambda s: s.encounter is not None)
        frames[0] += 1
        _tick(game)
    fs = game.scene
    assert isinstance(fs, FightScene) and fs.enemy_ref is b, type(fs)
    assert fs.boss and len(fs.foes) == 3, len(fs.foes)
    game.end_fight(fs, "win", sc.hp)
    assert type(game.scene).__name__ in ("LevelClear", "EndScreen"), type(game.scene)
    sc.result = "win"
    return frames[0]


def test_stealth(game):
    from akuma.dungeon import LEVELS
    game.level = next((k for k, v in LEVELS.items() if v.get("mode") == "stealth"), 8)
    test_light_shadow(game)
    test_box(game)
    test_bush(game)
    test_snap(game)
    test_posts(game)
    test_snack(game)
    test_alert_cycle(game)
    test_fight(game)
    game.overworld = game.scene = StealthScene(game, 8, level=getattr(game, "level", 8))
    f = bot_stealth(game)
    print("stealth: bot ran the missions and reached the boss fight in %.1f s" % (f / 60))


if __name__ == "__main__":
    from akuma.game import Game
    from akuma.dungeon import LEVELS
    g = Game()
    g.level = next((k for k, v in LEVELS.items() if v.get("mode") == "stealth"), 8)
    g.level_done = lambda scene, hp: None
    g.level_failed = lambda scene: None
    test_stealth(g)
    print("stealth test passed")
