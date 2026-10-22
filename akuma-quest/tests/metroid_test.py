"""Headless test of level 12 (the Prisoners' Quarters, a side-scrolling souls-like).

Checks that layouts are completable for many seeds (a walk/jump/climb search
from the start reaches every shrine, altar, reward and the Warden), that the
jump really clears what the search assumes, that a dodge roll's i-frames avoid
damage, that drinking flasks heals and a shrine refills them, that dying
respawns at the last shrine and costs a life (and running out of lives fails
the level), and that enemies telegraph before they hit. Then a bot runs the
level (following the search's path, warping only when stuck), and kills the
Warden with real punches and kicks.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/metroid_test.py
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from akuma import metroid as M  # noqa: E402
from akuma.metroid import MetroidScene, T  # noqa: E402

SHOTS = os.environ.get("SHOTS", os.path.join(ROOT, "screenshots"))
MAX_FRAMES = 60 * 360


def shot(game, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOTS, name))


def _tick(game, held=(), press=()):
    game.input.virtual = set(held)
    game.input.virtual_pressed = set(press)
    game.tick()


def _scene(game, seed, quiet=True):
    sc = MetroidScene(game, seed=seed)
    game.scene = sc
    sc.phase = "play"
    if quiet:
        sc.enemies = []
        sc.lv.trigger_x = 10 ** 9      # the arena floor is a quiet test stage: keep the Warden asleep
    _tick(game)
    return sc


def _settle(game, n=20):
    for _ in range(n):
        _tick(game)


def _put(sc, x, y):
    p = sc.p
    p.x, p.y, p.vx, p.vy = float(x), float(y), 0.0, 0.0
    p.state, p.t = "move", 0


# ---------------------------------------------------------------------------
def test_generation(game):
    lens = []
    for seed in range(30):
        lv = M.Level(seed)
        assert M.LW > 3 * 320 and M.LH > 2 * 180
        path = lv.path_to(lv.start_cell, lv.boss_tile)
        assert path, "seed %d: no way to the Warden" % seed
        reach = lv.reachable(lv.start_cell)
        for s in lv.shrines:
            assert s["tile"] in reach, ("shrine", seed)
        for a in lv.altars:
            assert a["tile"] in reach, ("altar", seed)
        assert len(lv.rewards) >= 2 and all(w["tile"] in reach for w in lv.rewards), ("rewards", seed)
        assert {w["kind"] for w in lv.rewards} >= {"str", "vit"}, seed
        assert len(lv.shrines) == 3 and len(lv.altars) == 2
        assert lv.exit_tile not in reach, "exit reachable before the Warden falls"
        lv.gate_out = False
        assert lv.exit_tile in lv.reachable(lv.start_cell), seed
        lens.append(len(path))
    layouts = {tuple(M.Level(s).path) for s in range(30)}
    assert len(layouts) > 10, "layouts barely vary"
    print("metroid: 30 seeds completable, %d distinct main paths, path %d-%d steps"
          % (len(layouts), min(lens), max(lens)))


def _flat(sc, c0, r_floor, width=14):
    """Carve a test strip into the level: air above a floor row."""
    g = sc.lv.grid
    for c in range(c0, c0 + width):
        for r in range(r_floor - 6, r_floor):
            g[r][c] = "."
        g[r_floor][c] = "#"
    return g


def test_jump_physics(game):
    """The search assumes a 3-tile rise and a 4-tile gap: check them for real."""
    sc = _scene(game, 1)
    c0, rf = 2 * M.RW + 2, 1 * M.RH + 9
    g = _flat(sc, c0, rf)
    for r in range(rf - 3, rf):           # a 3-tile wall to climb onto
        for c in range(c0 + 6, c0 + 14):
            g[r][c] = "#"
    _put(sc, (c0 + 4) * T + 8, rf * T)
    _settle(game, 5)
    for i in range(60):
        _tick(game, ("right", "up"), ("up",) if i == 0 else ())
    assert sc.p.on_ground and abs(sc.p.y - (rf - 3) * T) < 0.5, ("3-tile rise failed", sc.p.y, (rf - 3) * T)
    # gap of 3 tiles (stand cell to stand cell 4 apart), jumping from the edge cell centre
    g = _flat(sc, c0, rf)
    for c in range(c0 + 5, c0 + 8):
        g[rf][c] = "."
        g[rf + 1][c] = "^"
    _put(sc, (c0 + 4) * T + 8, rf * T)
    _settle(game, 5)
    hp = sc.hp
    for i in range(50):
        _tick(game, ("right", "up"), ("up",) if i == 0 else ())
    assert sc.hp == hp and sc.p.x > (c0 + 8) * T, ("gap jump failed", sc.p.x)
    # variable height: a tap is much lower than a held jump
    _put(sc, (c0 + 2) * T + 8, rf * T)
    g = _flat(sc, c0, rf)
    _settle(game, 5)
    top = sc.p.y
    _tick(game, ("up",), ("up",))
    for _ in range(40):
        _tick(game)
        top = min(top, sc.p.y)
    tap = rf * T - top
    top = sc.p.y
    _tick(game, ("up",), ("up",))
    for _ in range(40):
        _tick(game, ("up",))
        top = min(top, sc.p.y)
    full = rf * T - top
    assert full > 48 and tap < full * 0.6, (tap, full)
    print("metroid: 3-tile rise, 3-tile gap ok; jump height tap %d px / held %d px" % (tap, full))


def _grunt_vs(sc, game, dx=18):
    p = sc.p
    e = M.Grunt(sc, p.x + dx, p.y, "ryu")
    e.face = -1 if dx > 0 else 1
    e.state = "chase"
    e.cd = 0
    sc.enemies = [e]
    return e


def _arena_floor(sc):
    lv = sc.lv
    return lv.arena_x0 + 14 * T, lv.arena_floor


def test_roll_iframes(game):
    sc = _scene(game, 2)
    x, y = _arena_floor(sc)
    _put(sc, x, y)
    _settle(game, 5)
    # control: standing still, the grunt's swing lands
    e = _grunt_vs(sc, game)
    hp = sc.hp
    for _ in range(120):
        _tick(game)
        if sc.hp < hp:
            break
    assert sc.hp == hp - M.DMG["grunt"], ("swing did not land", hp, sc.hp)
    # roll through the same swing: no damage
    sc.p.inv = 0
    _put(sc, x, y)
    sc.hp = hp = sc.max_hp
    e = _grunt_vs(sc, game)
    rolled = False
    dodges = len([ev for ev in sc.events if ev[1] == "dodge"])
    for _ in range(140):
        if e.state == "windup" and e.t == e.wind_t - 2 and not rolled:
            _tick(game, ("right",), ("shield",))
            rolled = True
            continue
        _tick(game)
        if rolled and e.state == "recover":
            break
    assert rolled and sc.hp == hp, ("rolled into a swing and got hurt", sc.hp)
    assert len([ev for ev in sc.events if ev[1] == "dodge"]) > dodges, "the swing never overlapped the roll"
    # a fireball through a roll
    sc.enemies = []
    _put(sc, x, y)
    _settle(game, 12)
    _tick(game, (), ("shield",))
    assert sc.p.state == "roll"
    _tick(game)
    sc.spawn_proj(sc.p.x, sc.p.y - 10, 0.2, 0, "bolt", M.DMG["bolt"], False, None)
    _settle(game, 3)
    assert sc.hp == hp, "fireball hit through the roll's i-frames"
    _settle(game, 40)
    sc.spawn_proj(sc.p.x, sc.p.y - 10, 0.2, 0, "bolt", M.DMG["bolt"], False, None)
    _settle(game, 3)
    assert sc.hp == hp - M.DMG["bolt"], "fireball did not hit a standing Akuma"
    print("metroid: roll i-frames dodge a swing and a fireball; standing still costs %d / %d"
          % (M.DMG["grunt"], M.DMG["bolt"]))


def test_flasks_and_shrine(game):
    sc = _scene(game, 4)
    x, y = _arena_floor(sc)
    _put(sc, x, y)
    _settle(game, 5)
    assert sc.flasks == M.FLASKS
    sc.hp = 20
    _tick(game, ("down",), ("special",))
    assert sc.p.state == "drink" and sc.flasks == M.FLASKS - 1
    _settle(game, M.DRINK_T + 2)
    heal = round(sc.max_hp * M.FLASK_HEAL)
    assert sc.hp == 20 + heal, (sc.hp, heal)
    for _ in range(M.FLASKS):
        sc.hp = 10
        _tick(game, ("down",), ("special",))
        _settle(game, M.DRINK_T + 2)
    assert sc.flasks == 0
    hp = sc.hp = 30
    _tick(game, ("down",), ("special",))
    _settle(game, M.DRINK_T)
    assert sc.hp == hp and sc.p.state != "drink", "drank from an empty flask"
    # the shop's shrine refills them and becomes the respawn point
    s = sc.shrines[1]
    _put(sc, *s["pos"])
    _settle(game, 3)
    assert sc.flasks == M.FLASKS and sc.respawn == 1 and s["lit"], (sc.flasks, sc.respawn)
    print("metroid: flask heals %d, empty flask does nothing, shrine refills %d flasks" % (heal, M.FLASKS))


def test_death_and_lives(game, failed):
    sc = _scene(game, 5)
    s = sc.shrines[1]
    _put(sc, *s["pos"])
    _settle(game, 3)
    assert sc.respawn == 1
    x, y = _arena_floor(sc)
    _put(sc, x, y)
    sc.hp = 5
    sc.flasks = 0
    _settle(game, 5)
    _grunt_vs(sc, game)
    for _ in range(300):
        _tick(game)
        if sc.p.state == "dead":
            break
    assert sc.p.state == "dead" and sc.lives == M.LIVES
    for _ in range(200):
        _tick(game)
        if sc.p.state != "dead":
            break
    assert sc.lives == M.LIVES - 1, sc.lives
    assert (sc.p.x, sc.p.y) == tuple(map(float, s["pos"])), ((sc.p.x, sc.p.y), s["pos"])
    assert sc.hp == sc.max_hp and sc.flasks == M.FLASKS and sc.phase == "play"
    assert sc.game.scene is sc
    # the last life
    sc.lives = 1
    sc.enemies = []
    sc.p.inv = 0
    sc.spawn_proj(sc.p.x, sc.p.y - 10, 0, 0, "bolt", 9999, False, None)
    for _ in range(600):
        _tick(game)
        if sc.result:
            break
    assert sc.result == "lose" and failed and failed[-1] is sc, (sc.result, sc.phase)
    print("metroid: death respawns at shrine %d for a life; out of lives -> level_failed" % 1)


def test_telegraph(game):
    """Each enemy type flashes for its whole wind-up before it can hurt Akuma."""
    sc = _scene(game, 6)
    x, y = _arena_floor(sc)
    out = []
    for kind in ("grunt", "shield", "caster", "bat"):
        _put(sc, x, y)
        sc.p.inv = 0
        sc.hp = sc.max_hp
        _settle(game, 3)
        if kind == "bat":
            e = sc.make_enemy("bat", x + 40, y - 50)
        elif kind == "caster":
            e = sc.make_enemy("caster", x + 90, y)
        else:
            e = sc.make_enemy(kind, x + (24 if kind == "shield" else 18), y)
        e.face = -1
        e.aggro = True
        e.cd = 0
        if kind != "bat":
            e.state = "chase"
        sc.enemies = [e]
        mark = len(sc.events)
        flashed = 0
        for _ in range(400):
            _tick(game)
            if e.state == "windup" and e.tell_flash():
                flashed += 1
            if any(ev[1] == "hurt" for ev in sc.events[mark:]):
                break
        evs = sc.events[mark:]
        hurt = [ev for ev in evs if ev[1] == "hurt"]
        assert hurt, "%s never hit" % kind
        wind = [ev for ev in evs if ev[1] == "windup" and ev[2] == e.uid and ev[0] <= hurt[0][0]]
        assert wind, "%s hit without a wind-up" % kind
        gap = hurt[0][0] - wind[-1][0]
        assert gap >= M.TELEGRAPH[kind], (kind, gap)
        assert flashed >= 4, (kind, flashed)
        out.append("%s %d" % (kind, gap))
    print("metroid: telegraph frames before the first hit: " + ", ".join(out))


def test_shop(game):
    sc = _scene(game, 7)
    a = next(a for a in sc.altars if a["kind"] == "str")
    _put(sc, *a["pos"])
    _settle(game, 3)
    _tick(game, ("down",), ("down",))
    assert sc.dmg_mult == 1.0, "bought with no cells"
    sc.cells = 100
    _settle(game, 3)
    _tick(game, ("down",), ("down",))
    assert sc.dmg_mult > 1.0 and sc.cells == 100 - M.SHOP_COST[0]
    v = next(a for a in sc.altars if a["kind"] == "vit")
    _put(sc, *v["pos"])
    _settle(game, 3)
    mh = sc.max_hp
    _tick(game, ("down",), ("down",))
    assert sc.max_hp == mh + M.VIT_UP
    print("metroid: altars sell strength (x%.1f) and vitality (+%d)" % (sc.dmg_mult, M.VIT_UP))


# ---------------------------------------------------------------------------
# the bot
# ---------------------------------------------------------------------------
def _cell_of(sc):
    p = sc.p
    if p.state == "ladder":
        return int(p.x // T), int((p.y - 1) // T)
    return int(p.x // T), int(round(p.y) // T) - 1


def _walk_to(game, sc, goal, budget, log, shots):
    """Follow the walk/jump/climb search's path to a stand cell. Warps to the
    next step if stuck there for 2 seconds."""
    lv = sc.lv
    path = lv.path_to(_cell_of(sc), goal)
    if path is None:
        p = sc.p
        p.x, p.y = goal[0] * T + T / 2, (goal[1] + 1) * T
        log["warps"] += 1
        return 0
    i = 1
    frames = 0
    stuck = 0
    jumping = 0
    while i < len(path) and frames < budget and sc.result is None:
        frames += 1
        p = sc.p
        if frames % 20 == 0:
            sc.hp = max(sc.hp, sc.max_hp * 0.6)
        if p.state == "dead" or sc.phase != "play":
            _tick(game)
            continue
        cur = _cell_of(sc)
        nxt = path[i]
        prv = path[i - 1]
        tx = nxt[0] * T + T / 2
        held, press = set(), set()
        # fight whatever stands in the way
        foe = None
        for e in sc.enemies:
            if e.alive and abs(e.x - p.x) < 34 and abs(e.y - p.y) < 30 and e.kind != "bat":
                foe = e
        if foe and p.state in ("move", "attack") and p.on_ground:
            p.face = 1 if foe.x > p.x else -1
            press.add("kick" if foe.kind == "shield" else "punch")
            if foe.kind == "shield" and (p.x - foe.x) * foe.face > 0:
                held.add("right" if foe.x > p.x else "left")
            _tick(game, held, press)
            log["fights"] += 1
            if shots and not log.get("fight_shot") and any(e.state in ("windup", "attack") for e in sc.enemies
                                                         if abs(e.x - p.x) < 120):
                shot(game, "metroid_fight.png")
                log["fight_shot"] = True
            continue
        if cur == nxt or (abs(p.x - tx) < 4 and cur[1] == nxt[1] and (p.on_ground or p.state == "ladder")):
            i += 1
            stuck = 0
            continue
        stuck += 1
        if stuck % 45 == 0 and p.on_ground and p.state == "move" and lv.stand(*cur):
            again = lv.path_to(cur, goal)         # landed somewhere else: plan again from here
            if again:
                path, i = again, 1
                jumping = 0
                continue
        if stuck > 150:
            if os.environ.get("MV_DEBUG"):
                print("warp", prv, "->", nxt, "at", cur, p.state, round(p.x), round(p.y),
                      [sc.lv.tile(nxt[0], r) for r in range(nxt[1] - 1, nxt[1] + 2)])
            p.x, p.y, p.vx, p.vy = tx, (nxt[1] + 1) * T, 0.0, 0.0
            p.state = "move"
            log["warps"] += 1
            i += 1
            stuck = 0
            _tick(game)
            continue
        dc, dr = nxt[0] - prv[0], nxt[1] - prv[1]
        ladder = dc == 0 and (lv.ladder(prv[0], prv[1]) or lv.ladder(prv[0], prv[1] + 1) or lv.ladder(*nxt))
        if ladder:
            px = prv[0] * T + T / 2
            if p.state != "ladder" and abs(p.x - px) > 5:
                held.add("right" if px > p.x else "left")
            else:
                held.add("up" if dr < 0 else "down")
        elif dr < 0 or (dr == 0 and abs(dc) > 1 and not all(
                lv.stand(c, prv[1]) for c in range(min(prv[0], nxt[0]), max(prv[0], nxt[0]) + 1))):  # a jump
            sx = prv[0] * T + T / 2
            if p.on_ground and not jumping:
                if abs(p.x - sx) > 3 and cur != nxt:
                    held.add("right" if sx > p.x else "left")
                else:
                    held.update(("up",))
                    press.add("up")
                    jumping = 40
            if jumping:
                jumping -= 1
                held.add("up")
                if abs(p.x - tx) > 2:
                    held.add("right" if tx > p.x else "left")
                if p.on_ground and jumping < 36:
                    jumping = 0
        elif dr > 0 and dc == 0:                              # drop through a plank
            held.add("down")
            if p.on_ground:
                press.add("up")
                held.add("up")
        else:
            if abs(p.x - tx) > 1:
                held.add("right" if tx > p.x else "left")
        _tick(game, held, press)
        if shots and frames > 150 and not log.get("explore_shot") and not sc.popups and p.on_ground and \
                not any(abs(e.x - p.x) < 140 and abs(e.y - p.y) < 90 for e in sc.enemies):
            shot(game, "metroid.png")
            log["explore_shot"] = True
    log["frames"] += frames
    return frames


def _fight_boss(game, sc, log, shots):
    b = sc.boss
    frames = 0
    dealt0 = sc.boss_dealt
    while b.alive and frames < 60 * 240:
        frames += 1
        p = sc.p
        if frames % 15 == 0:
            sc.hp = max(sc.hp, sc.max_hp * 0.6)
        held, press = set(), set()
        if p.state != "dead" and b.state not in ("intro", "sleep"):
            dx = b.x - p.x
            toward = "right" if dx > 0 else "left"
            if b.state == "windup" and b.t == b.wind_t - 3 and b.act in ("charge", "swing"):
                held.add(toward)
                press.add("shield")              # roll through it
            elif abs(dx) > 30:
                held.add(toward)
            else:
                if p.face != (1 if dx > 0 else -1) and p.state == "move":
                    held.add(toward)
                press.add("kick" if (frames // 40) % 3 == 2 else "punch")
        _tick(game, held, press)
        if shots and not log.get("boss_shot") and b.hp < b.max_hp * 0.75 and b.state in ("windup", "leap", "charge"):
            shot(game, "metroid_boss.png")
            log["boss_shot"] = True
    log["frames"] += frames
    dealt = sc.boss_dealt - dealt0
    return frames, dealt


def bot_metroid(game, shots=True):
    sc = game.scene
    assert isinstance(sc, MetroidScene)
    while sc.phase == "intro":
        _tick(game, (), ("punch",) if sc.end_t > 45 else ())
    log = dict(warps=0, frames=0, fights=0)
    lv = sc.lv
    # through the level: every shrine, the altar room, the side rooms, then the Warden
    goals = [s["tile"] for s in lv.shrines[1:2]]
    goals += [w["tile"] for w in lv.rewards[:1]]
    goals += [lv.shrines[2]["tile"], lv.boss_tile]
    for goal in goals:
        _walk_to(game, sc, goal, 60 * 60, log, shots)
        if goal == lv.shrines[1]["tile"]:
            sc.cells += 60                      # a little cheat: buy both upgrades
            for a in sc.altars:
                _walk_to(game, sc, a["tile"], 60 * 10, log, False)
                _settle(game, 4)
                _tick(game, ("down",), ("down",))
    assert sc.boss_on or sc.boss.state != "sleep" or sc.p.x > lv.trigger_x, "never reached the arena"
    while not sc.boss_on:
        _tick(game, ("right",))
        log["frames"] += 1
    frames, dealt = _fight_boss(game, sc, log, shots)
    assert not sc.boss.alive, ("Warden survived", sc.boss.hp)
    assert dealt >= M.BOSS_HP, (dealt, M.BOSS_HP)
    # every hit Akuma took came after a wind-up from that foe
    _check_telegraphs(sc)
    # out through the exit
    lv.gate_out = False
    _settle(game, 60)
    _walk_to(game, sc, lv.exit_tile, 60 * 30, log, False)
    for _ in range(400):
        if sc.result:
            break
        _tick(game, ("right",), ("punch",) if sc.phase == "won" and sc.end_t > 60 else ())
    assert sc.result == "win", (sc.result, sc.phase, sc.p.x, lv.exit_pos)
    return log, frames, dealt


def _check_telegraphs(sc):
    last = {}
    for ev in sc.events:
        if ev[1] == "windup":
            last[ev[2]] = ev[0]
        elif ev[1] == "hurt" and ev[2] in last:
            assert ev[0] - last[ev[2]] >= 16, ("hit without warning", ev)


def test_metroid(game):
    test_generation(game)
    test_jump_physics(game)
    test_roll_iframes(game)
    test_flasks_and_shrine(game)
    failed = []
    old = game.level_failed
    game.level_failed = lambda scene: failed.append(scene)
    try:
        test_death_and_lives(game, failed)
    finally:
        game.level_failed = old
    test_telegraph(game)
    test_shop(game)
    game.scene = MetroidScene(game, seed=12)
    log, f, dealt = bot_metroid(game)
    print("metroid: bot cleared the level in %.1f s (boss %.1f s, %d damage dealt to the Warden), %d warps"
          % (log["frames"] / 60, f / 60, dealt, log["warps"]))


if __name__ == "__main__":
    from akuma.game import Game
    g = Game()
    g.level_done = lambda scene, hp: None
    g.level_failed = lambda scene: None
    test_metroid(g)
    print("metroid test passed")
