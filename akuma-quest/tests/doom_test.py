"""Headless test of level 13 (the Doom-style hell fortress): times the
raycaster, checks walls hide sprites (z-buffer), a hadouken hurts what it
hits, a locked door needs its key, the exit portal ends the level, and a bot
clears the whole level for real (keys, doors, hadoukens, CYBER-GIEF, portal).

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/doom_test.py
"""

import math
import os
import statistics
import sys
import time
from collections import deque

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from akuma import doom as D  # noqa: E402
from akuma.doom import DoomScene  # noqa: E402

SHOTS = os.environ.get("SHOTS", os.path.join(ROOT, "screenshots"))
MAX_FRAMES = 60 * 600


def shot(game, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOTS, name))


def _tick(game, held=(), press=()):
    game.input.virtual = set(held)
    game.input.virtual_pressed = set(press)
    game.tick()


def _fresh(game, **kw):
    sc = DoomScene(game, seed=kw.pop("seed", 7), **kw)
    game.scene = sc
    while sc.phase == "intro":
        _tick(game)
    return sc


def _angdiff(a, b):
    return (a - b + math.pi) % (2 * math.pi) - math.pi


def _quiet(sc, keep=()):
    """Remove every enemy except keep (tests want one thing at a time)."""
    for e in sc.enemies:
        if e not in keep:
            e.state = "dead"
            e.x, e.y = 0.5, 0.5


# ---- checks --------------------------------------------------------------
def test_frame_time(game):
    sc = _fresh(game)
    views = {"start room": (6.5, 28.3, -math.pi / 2), "demon hall": (10.0, 14.5, -2.6),
             "arena (sky)": (34.5, 24.5, -math.pi / 2)}
    lights = [(34.5, 22.0 - k * 3, 0.7, (0.5, 0.7, 1.5)) for k in range(3)]
    worst = 0
    for name, (x, y, a) in views.items():
        sc.px, sc.py, sc.ang = x, y, a
        for li in ([], lights):
            ts = []
            for _ in range(60):
                t = time.perf_counter()
                sc.r.render(x, y, a, 0.5, sc.light_now, li, 0.5 if li else 0)
                ts.append(time.perf_counter() - t)
            med = statistics.median(ts) * 1000
            worst = max(worst, med)
            print("doom raycaster, %-12s %s: %.2f ms" % (name, "+3 lights" if li else "        ", med))
    # a whole frame: world, sprites, hands, status bar
    sc.px, sc.py, sc.ang = 10.0, 14.5, -2.6
    ts = []
    for _ in range(60):
        t = time.perf_counter()
        sc.draw(game.canvas)
        ts.append(time.perf_counter() - t)
    full = statistics.median(ts) * 1000
    print("doom full frame draw (hall, enemies in view): %.2f ms" % full)
    assert worst < 30 and full < 35, (worst, full)
    return full


def test_zbuffer(game):
    """An enemy behind a closed door is hidden; open the door and he shows."""
    sc = _fresh(game)
    e = next(e for e in sc.enemies if e.kind == "zombie")
    _quiet(sc, (e,))
    sc.px, sc.py, sc.ang = 6.5, 26.5, -math.pi / 2
    e.x, e.y, e.state, e.alert = 6.5, 20.5, "idle", False
    door = sc.map.doors[(6, 24)]
    view = pygame.Rect(0, 0, D.W, D.VIEW_H - 40)

    def grab():
        sc.draw(game.canvas)
        return pygame.image.tobytes(game.canvas.subsurface(view), "RGB")

    with_enemy = grab()
    drawn = [k for k in sc.drawn if k[0] and k[0][0] == "zombie"]
    e.x = 0.5
    without = grab()
    assert with_enemy == without, "enemy drawn through a closed door"
    assert not drawn, drawn
    assert min(sc.r.zbuf[150:170]) < 3.0, "the door is not in the z-buffer"
    door.open, door.opening = 1.0, True
    sc.map.door_open[24, 6] = 1.0
    e.x = 6.5
    opened = grab()
    e.x = 0.5
    empty = grab()
    assert opened != empty, "enemy not drawn with the door open"
    print("doom z-buffer: walls hide sprites, open doorway shows them")


def test_hadouken_hits(game):
    sc = _fresh(game)
    e = next(e for e in sc.enemies if e.kind == "pinky")
    _quiet(sc, (e,))
    sc.px, sc.py, sc.ang = 9.5, 13.5, math.pi
    e.x, e.y = 6.0, 13.5
    e.alert, e.state, e.cool = True, "chase", 999
    e.spec = dict(e.spec, pain=0.0, melee=0)
    e.speed = 0
    hp0, ki0 = e.hp, sc.ki
    _tick(game, press=("special",))
    for _ in range(40):
        _tick(game)
        if e.hp < hp0:
            break
    assert sc.ki == ki0 - D.HADO_COST, (sc.ki, ki0)
    assert e.hp == hp0 - D.HADO_DMG * sc.power, ("hadouken did not hit", hp0, e.hp)
    assert not [s for s in sc.shots if s.owner == "akuma"], "hadouken flew through"
    # a hadouken at a wall hits nothing and bursts
    sc.ang = 0.0
    _tick(game, press=("special",))
    for _ in range(60):
        _tick(game)
    assert e.hp == hp0 - D.HADO_DMG * sc.power
    # the shinku pierces and hits hard
    sc.ang = math.pi
    sc.ki = 20
    _tick(game, held=("shield",), press=("special",))
    for _ in range(60):
        _tick(game)
    assert e.hp <= hp0 - (D.HADO_DMG + D.SHINKU_DMG) * sc.power + 1e-6 or not e.alive, e.hp
    print("doom: hadouken hits for %d, shinku for %d" % (D.HADO_DMG, D.SHINKU_DMG))


def test_locked_door(game):
    sc = _fresh(game)
    _quiet(sc)
    door = sc.map.doors[(9, 7)]
    assert door.key == "blue"
    sc.px, sc.py, sc.ang = 9.5, 8.5, -math.pi / 2
    _tick(game, press=("kick",))
    for _ in range(40):
        _tick(game, held=("up",))
    assert door.open == 0 and sc.py > 8.0, ("blue door opened without the key", door.open, sc.py)
    assert "BLUE" in sc.msg, sc.msg
    sc.keys.add("blue")
    sc.px, sc.py, sc.ang = 9.5, 8.5, -math.pi / 2
    _tick(game, press=("kick",))
    for _ in range(30):
        _tick(game)
    assert door.open == 1.0, door.open
    for _ in range(60):
        _tick(game, held=("up",))
    assert sc.py < 6.5, ("could not walk through the open door", sc.py)
    print("doom: the blue door needs the blue key")


def test_exit(game):
    sc = _fresh(game)
    _quiet(sc, (sc.boss,))
    sc.px, sc.py, sc.ang = 34.5, 29.5, 0.0
    sc.boss.x, sc.boss.y = 34.5, 5.0
    for _ in range(10):
        _tick(game)
    assert sc.phase == "play", "portal works while CYBER-GIEF lives"
    sc.px, sc.py, sc.ang = 34.5, 25.5, math.pi / 2
    sc._damage(sc.boss, 99999)
    assert not sc.boss.alive
    done = []
    game.level_done = lambda scene, hp: done.append(hp)
    for _ in range(400):
        _tick(game, held=("up",))
        if done:
            break
    assert sc.result == "win" and done, (sc.result, sc.phase, sc.px, sc.py)
    print("doom: killing CYBER-GIEF opens the seal; the portal ends the level")


def test_combos(game):
    """special + punch = shoryuken, special + kick = tatsumaki (within the
    window, either order); the tatsumaki spins the view a full turn."""
    sc = _fresh(game)
    _quiet(sc)
    sc.px, sc.py, sc.ang = 10.0, 12.0, 0.0
    ki0 = sc.ki
    _tick(game, press=("special",))
    _tick(game)
    _tick(game, press=("punch",))
    assert sc.weapon == "shoryu" and sc.ki == ki0, (sc.weapon, sc.ki, ki0)
    for _ in range(40):
        _tick(game)
    _tick(game, press=("kick",))
    _tick(game, press=("special",))
    assert sc.weapon == "tatsu", sc.weapon
    a0, seen = sc.ang, set()
    for _ in range(45):
        _tick(game)
        seen.add(int(((sc.ang - a0) % (2 * math.pi)) / (math.pi / 2)))
    assert seen == {0, 1, 2, 3} and abs(_angdiff(sc.ang, a0)) < 1e-6, (seen, sc.ang, a0)
    _tick(game, press=("punch",))
    assert sc.weapon == "punch"
    print("doom: shoryuken / tatsumaki combos and the plain punch work")


def test_views(game):
    """A hadouken flying away is drawn from behind; one coming at you from the front."""
    sc = _fresh(game)
    _quiet(sc)
    sc.px, sc.py, sc.ang = 10.0, 12.0, 0.0
    _tick(game, press=("special",))
    for _ in range(14):
        _tick(game)
    s = [s for s in sc.shots if s.owner == "akuma"][0]
    sc.draw(game.canvas)
    assert s.view == "back", s.view
    shot(game, "doom_hado_back.png")
    s.vx, s.vy = -s.vx, -s.vy
    sc.draw(game.canvas)
    assert s.view == "front", s.view
    print("doom: fireballs show their back flying away, their front coming at you")


def test_snacks(game):
    sc = _fresh(game)
    snacks = [t for t in sc.things if t.kind == "snack"]
    assert len(snacks) >= D.EXTRA_SNACKS, len(snacks)
    t = snacks[0]
    sc.hp = 10
    sc.px, sc.py = t.x, t.y
    _tick(game)
    assert t.taken and sc.hp > 10 and t.snack in sc.msg, (t.taken, sc.hp, sc.msg)
    print("doom: %d snacks, %s" % (len(snacks), sc.msg))


def test_poses(game):
    """Screenshots of every first-person pose."""
    sc = _fresh(game)
    _quiet(sc)
    sc.px, sc.py, sc.ang = 10.0, 14.0, -math.pi / 2
    sc.draw(game.canvas)
    shot(game, "doom_pose_idle.png")
    for name, press, at in (("hado", ("special",), (4, 9)), ("punch", ("punch",), (5,)),
                            ("kick", ("kick",), (8,)), ("shoryu", ("special", "punch"), (3, 10)),
                            ("tatsu", ("special", "kick"), (16,))):
        _tick(game, press=press)
        for k in range(max(at) + 1):
            if k in at:
                shot(game, "doom_pose_%s_%d.png" % (name, k))
            _tick(game)
        while sc.weapon:
            _tick(game)


# ---- the bot -----------------------------------------------------------------
def _passable(sc, c):
    m = sc.map
    if not (0 <= c[0] < D.MAP_W and 0 <= c[1] < D.MAP_H):
        return False
    g = m.grid[c[1], c[0]]
    if g == 0:
        return True
    if g != D.DOOR:
        return False
    d = m.doors[c]
    if d.key is None or d.open >= 1 or d.key in sc.keys:
        return True
    return d.key == "boss" and not sc.boss.alive


def _path(sc, start, goal):
    q = deque([start])
    prev = {start: None}
    while q:
        c = q.popleft()
        if c == goal:
            out = []
            while c != start:
                out.append(c)
                c = prev[c]
            return out[::-1]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + dx, c[1] + dy)
            if n not in prev and _passable(sc, n):
                prev[n] = c
                q.append(n)
    return None


def _goal(sc):
    th = {t.kind: t for t in sc.things}
    if "blue" not in sc.keys:
        t = th["bluekey"]
    elif "red" not in sc.keys:
        t = th["redkey"]
    elif sc.boss.alive:
        b = sc.boss
        return (int(b.x), int(b.y)) if sc.boss_awake else (31, 12)
    else:
        t = th["portal"]
    return int(t.x), int(t.y)


def _target(sc):
    best = None
    for e in sc.enemies:
        if not e.alive:
            continue
        d = math.hypot(e.x - sc.px, e.y - sc.py)
        if d > 11 or not sc.map.los(sc.px, sc.py, e.x, e.y):
            continue
        if e.boss and not sc.boss_awake:
            continue
        if best is None or d < best[0]:
            best = (d, e)
    return best


def bot_doom(game):
    """Plays the level: walks the keys/doors route by BFS, kicks doors open,
    turns to face enemies and throws real hadoukens (auto-aim: it turns
    exactly onto its target; cheats: keeps health and ki topped up)."""
    sc = game.scene
    assert isinstance(sc, DoomScene)
    frames = 0
    while sc.phase == "intro":
        _tick(game)
        frames += 1
    shot(game, "doom.png")
    fight_shot = boss_shot = False
    last_pos, stuck = (sc.px, sc.py), 0
    kick_cool = 0
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
        if tgt:
            d, e = tgt
            want = math.atan2(e.y - sc.py, e.x - sc.px)
            diff = _angdiff(want, sc.ang)
            tol = max(0.03, math.atan2(e.radius * 0.6, d))
            if abs(diff) > tol:
                held.add("right" if diff > 0 else "left")
                if abs(diff) < D.TURN_SPEED:
                    sc.ang = want          # auto-aim snaps the last sliver
            else:
                if e.boss and sc.ki >= D.SHINKU_COST and sc.weapon is None and frames % 3 == 0:
                    held.add("shield")
                    press.add("special")
                else:
                    held.add("special")
                if d > 4 and not e.boss:
                    held.add("up")
            if d < 1.2 and kick_cool <= 0:
                press.add("kick")
                kick_cool = 25
            flying = [s for s in sc.shots if s.owner == "akuma" and s.t >= 8]
            if not fight_shot and not e.boss and 2.5 < d < 7 and flying and sc.hurt < 4 and e.flash == 0:
                fight_shot = True
                _tick(game, held, press)
                shot(game, "doom_fight.png")
                continue
            if e.boss and not boss_shot and 2.5 < d < 9 and sc.boss.hp < sc.boss.max_hp * 0.8 and \
                    flying and sc.hurt < 4 and e.flash == 0:
                boss_shot = True
                _tick(game, held, press)
                shot(game, "doom_boss.png")
                continue
        else:
            here = (int(sc.px), int(sc.py))
            goal = _goal(sc)
            path = _path(sc, here, goal)
            if path == []:
                path = [goal]          # in the goal cell: walk onto the item itself
            if path:
                nxt = path[0]
                g = sc.map.grid[nxt[1], nxt[0]]
                closed = g == D.DOOR and sc.map.doors[nxt].open < 0.95
                # aim at the cell after next when the path runs straight (smoother)
                tx, ty = nxt[0] + 0.5, nxt[1] + 0.5
                want = math.atan2(ty - sc.py, tx - sc.px)
                diff = _angdiff(want, sc.ang)
                if abs(diff) > 0.06:
                    held.add("right" if diff > 0 else "left")
                if closed:
                    if abs(diff) < 0.2 and kick_cool <= 0 and not sc.map.doors[nxt].opening:
                        press.add("kick")
                        kick_cool = 30
                elif abs(diff) < 0.35:
                    held.add("up")
        _tick(game, held, press)
        moved = math.hypot(sc.px - last_pos[0], sc.py - last_pos[1])
        if "up" in held and moved < 0.002:
            stuck += 1
            if stuck > 40:
                # nudge sideways out of a corner
                for _ in range(12):
                    _tick(game, {"shield", "left" if (frames // 200) % 2 else "right"})
                stuck = 0
        else:
            stuck = 0
        last_pos = (sc.px, sc.py)
    assert sc.result == "win", (sc.result, sc.phase, frames, sc.keys, sc.boss.hp, (sc.px, sc.py))
    if not boss_shot:
        shot(game, "doom_boss.png")
    return frames


def test_doom(game):
    test_frame_time(game)
    test_zbuffer(game)
    test_hadouken_hits(game)
    test_locked_door(game)
    test_exit(game)
    test_combos(game)
    test_views(game)
    test_snacks(game)
    test_poses(game)
    done = []
    old = game.level_done
    game.level_done = lambda scene, hp: done.append(hp)
    game.scene = DoomScene(game, seed=5)
    f = bot_doom(game)
    game.level_done = old
    sc_kills = game.scene.kills if isinstance(game.scene, DoomScene) else None
    print("doom: bot cleared the level in %.1f s (%s kills), level_done called: %s" % (f / 60, sc_kills, bool(done)))


if __name__ == "__main__":
    from akuma.game import Game
    g = Game()
    g.level_done = lambda scene, hp: None
    g.level_failed = lambda scene: None
    test_doom(g)
    print("doom test passed")
