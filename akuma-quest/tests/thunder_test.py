"""Headless test of Geldra's Hideout (the Rolling Thunder style level).

Checks the street layouts for many seeds (walkways inside the street, doors on
a floor, every item door there), the two-floor movement (UP under a walkway
vaults onto it, a plain jump does not reach it, DOWN + UP drops back down,
walking off the end falls), that ducking dodges a high shot and jumping a low
one, that doors hide Akuma and hand out ki / food / rapid fire once, that
maskers step out of doors and always aim before they fire, the special moves
(hadouken costs ki, shoryuken and hurricane kick by chord), losing every life
fails the level, and then a bot walks the whole street and beats Dr. Doom with
real attacks.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/thunder_test.py
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from akuma import thunder as R  # noqa: E402
from akuma.thunder import ThunderScene, Shot, Enemy, GROUND, UPPER, HIGH, LOW, LW, ARENA_X  # noqa: E402

SHOTS = os.environ.get("SHOTS", os.path.join(ROOT, "screenshots"))
MAX_FRAMES = 60 * 300


def shot(game, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pygame.image.save(pygame.transform.scale_by(game.canvas, 3), os.path.join(SHOTS, name))


def _tick(game, held=(), press=()):
    game.input.virtual = set(held)
    game.input.virtual_pressed = set(press)
    game.tick()


def _scene(game, seed, quiet=True):
    sc = ThunderScene(game, seed=seed)
    game.scene = sc
    sc.phase = "play"
    if quiet:
        sc.spawning = False
    _tick(game)
    return sc


def _settle(game, n=20, held=()):
    for _ in range(n):
        _tick(game, held)


def _put(sc, x, y):
    p = sc.p
    p.x, p.y, p.vx, p.vy = float(x), float(y), 0.0, 0.0
    p.state, p.on_ground, p.inv = "move", True, 0
    sc._camera(snap=True)


def test_layouts():
    for seed in range(40):
        st = R.Street(seed)
        last = 0
        for x0, x1 in st.balconies:
            assert x0 > last and x1 - x0 >= 160 and x1 <= LW - 60, (seed, st.balconies)
            last = x1
        kinds = [d["kind"] for d in st.doors]
        for k, n in (("ki", 3), ("food", 3), ("rapid", 2), ("arena", 4)):
            assert kinds.count(k) == n, (seed, k, kinds.count(k))
        assert sum(d["stock"] for d in st.doors if d["kind"] == "spawn") >= 18, seed
        for d in st.doors:
            assert d["y"] in (GROUND, UPPER)
            assert d["x"] > 250, "a door right at the start"
            if d["y"] == UPPER:
                assert st.covered(d["x"], 10), (seed, d)
    print("thunder: 40 street layouts OK")


def test_floors(game):
    sc = _scene(game, 3)
    x0, x1 = sc.st.balconies[0]
    # UP under the walkway vaults onto it
    _put(sc, (x0 + x1) / 2, GROUND)
    _tick(game, press={"up"})
    assert any(e[1] == "vault" for e in sc.events)
    for _ in range(90):
        _tick(game)
    assert sc.p.on_ground and sc.p.y == UPPER, ("vault", sc.p.y)
    # DOWN + UP drops back to the street
    _tick(game, held={"down"}, press={"up"})
    for _ in range(60):
        _tick(game)
    assert sc.p.on_ground and sc.p.y == GROUND, ("drop", sc.p.y)
    # a jump where there is no walkway stays well under it
    _put(sc, x0 - 40, GROUND)
    top = GROUND
    _tick(game, press={"up"})
    for _ in range(60):
        top = min(top, sc.p.y)
        _tick(game)
    assert sc.p.y == GROUND and GROUND - top > LOW + 14 and top > UPPER, top
    # walking off the end of the walkway falls to the street
    _put(sc, x1 - 6, UPPER)
    for _ in range(80):
        _tick(game, held={"right"})
    assert sc.p.on_ground and sc.p.y == GROUND
    print("thunder: vault / drop / jump / walk-off OK")


def _shot_at(game, sc, height, held=(), jump_at=None):
    """Fire an enemy shot at Akuma from 70 px away; True if it hit him."""
    _put(sc, 200, GROUND)
    sc.p.face = 1
    sc.shots = []
    _settle(game, 4, held)
    hp = sc.hp
    s = Shot(sc.p.x + 70, GROUND - height, -R.SHOT_V, 0, "ki", 12, False, sc.p, tint="rt_blue")
    s.x0 = s.x
    sc.shots.append(s)
    for i in range(70):
        press = {"up"} if jump_at is not None and abs(s.x - sc.p.x) < jump_at and sc.p.on_ground and i < 40 else set()
        _tick(game, held, press)
    return sc.hp < hp


def test_dodging(game):
    sc = _scene(game, 4)
    assert _shot_at(game, sc, HIGH), "a high shot missed a standing Akuma"
    sc.hp = sc.max_hp
    assert not _shot_at(game, sc, HIGH, held={"down"}), "ducking did not dodge a high shot"
    sc.hp = sc.max_hp
    assert _shot_at(game, sc, LOW), "a low shot missed a standing Akuma"
    sc.hp = sc.max_hp
    assert _shot_at(game, sc, LOW, held={"down"}), "ducking dodged a low shot"
    sc.hp = sc.max_hp
    assert not _shot_at(game, sc, LOW, jump_at=34), "jumping did not clear a low shot"
    sc.hp = sc.max_hp
    print("thunder: duck the high shots, jump the low ones OK")


def test_doors(game):
    sc = _scene(game, 5)
    by = {}
    for d in sc.st.doors:
        by.setdefault(d["kind"], d)
    d = by["ki"]
    _put(sc, d["x"], d["y"])
    sc.ki = 0
    _tick(game, press={"shield"})
    assert sc.p.state == "door" and sc.ki == R.KI_MAX
    # hidden: a shot flies straight through the doorway
    hp = sc.hp
    sc.shots.append(Shot(sc.p.x + 30, sc.p.y - HIGH, -R.SHOT_V, 0, "ki", 12, False, sc.p))
    for _ in range(R.DOOR_T + 2):
        _tick(game)
    assert sc.p.state == "move" and sc.hp == hp
    # the gift is once only
    sc.ki = 0
    _settle(game, 20)
    _tick(game, press={"shield"})
    assert sc.p.state == "door" and sc.ki < R.HADO_COST
    _settle(game, R.DOOR_T + 4)
    d = by["food"]
    _put(sc, d["x"], d["y"])
    sc.hp = 20
    _tick(game, press={"shield"})
    assert sc.hp > 20, "food door did not heal"
    _settle(game, R.DOOR_T + 4)
    d = by["rapid"]
    _put(sc, d["x"], d["y"])
    _tick(game, press={"shield"})
    _settle(game, R.DOOR_T + 4)
    assert sc.rapid > 0
    sc.ki = 0
    n = sum(1 for e in sc.events if e[1] == "hado")
    for i in range(60):
        _tick(game, press={"special"} if i % 12 == 0 else ())
    fired = sum(1 for e in sc.events if e[1] == "hado") - n
    assert fired >= 4 and sc.ki < R.HADO_COST, ("rapid fire", fired)
    print("thunder: doors hide Akuma and give ki / food / rapid fire once OK")


def test_moves(game):
    sc = _scene(game, 6)
    _put(sc, 400, GROUND)
    sc.ki = R.KI_MAX
    _tick(game, press={"special"})
    _settle(game, 30)
    assert sc.ki <= R.KI_MAX - R.HADO_COST + 2, "hadouken did not cost ki"
    sc.ki = 0
    n = len(sc.shots)
    _tick(game, press={"special"})
    _settle(game, 4)
    assert len(sc.shots) == n and sc.p.state == "move", "hadouken without ki"
    for chord, name in ((("special", "punch"), "shoryu"), (("special", "kick"), "tatsu")):
        _settle(game, 60)
        _tick(game, press=set(chord))
        assert sc.p.state == "attack" and sc.p.move == name, (chord, sc.p.move)
    # special then punch two frames later is still a shoryuken
    _settle(game, 80)
    sc.ki = R.KI_MAX
    _tick(game, press={"special"})
    _tick(game)
    _tick(game, press={"punch"})
    _settle(game, 3)
    assert sc.p.move == "shoryu", sc.p.move
    # a shoryuken drops a masker; so does a hadouken
    _settle(game, 80)
    for move in ("shoryu", "hado"):
        _put(sc, 400, GROUND)
        sc.p.face = 1
        e = Enemy(sc, 420 if move == "shoryu" else 480, GROUND, "masker")
        e.cd = 999
        sc.enemies = [e]
        sc.ki = R.KI_MAX
        _tick(game, press={"special", "punch"} if move == "shoryu" else {"special"})
        for _ in range(70):
            _tick(game)
        assert not e.alive, (move, e.hp)
    # the air hadouken goes down at 45 degrees
    _put(sc, sc.st.balconies[0][0] - 60, GROUND)
    sc.enemies = []
    _tick(game, press={"up"})
    _settle(game, 6)
    _tick(game, press={"special"})
    air = []
    for _ in range(14):
        _tick(game)
        air += [s for s in sc.shots if s.friendly and s.move == "ahado" and s not in air]
    assert air and air[0].vy > 0 and abs(air[0].vx) == air[0].vy, air
    print("thunder: hadouken costs ki, shoryuken / tatsu chords, one-shot maskers OK")


def test_enemies(game):
    sc = _scene(game, 7, quiet=False)
    seen = 0
    for i in range(60 * 40):
        sc.hp = sc.max_hp
        held = {"right"} if (i // 120) % 3 else set()
        _tick(game, held)
        seen = sum(1 for e in sc.events if e[1] == "spawn")
    assert seen >= 3, "no maskers came out of the doors"
    doors = {d["x"] for d in sc.st.doors}
    assert all(e[4] in doors for e in sc.events if e[1] == "spawn")
    # every shot was aimed first, long enough to read
    aims = {}
    for ev in sc.events:
        if ev[1] == "aim":
            aims[ev[2]] = ev[0]
        elif ev[1] == "fire" and ev[3] != "boss":
            assert ev[2] in aims and ev[0] - aims[ev[2]] >= Enemy.TELL, ev
    print("thunder: %d maskers stepped out of doors, all shots telegraphed OK" % seen)


def test_lose(game):
    sc = _scene(game, 8)
    _put(sc, 300, GROUND)
    for _ in range(R.LIVES):
        sc.p.inv = 0
        sc.hurt_player(999, sc.p)
        for _ in range(100):
            _tick(game)
    assert sc.phase == "lost"
    for _ in range(220):
        _tick(game)
    assert sc.result == "lose" and game.scene is not sc
    print("thunder: losing every life fails the level OK")


def test_boss_hops(game):
    """Doom follows Akuma between the floors and his landing sends shockwaves."""
    sc = _scene(game, 9)
    sc.god = True
    _put(sc, ARENA_X + 60, GROUND)
    for _ in range(4):
        _tick(game, held={"right"})
    assert sc.boss_on and sc.boss.state == "intro"
    for _ in range(200):
        _tick(game)
    b = sc.boss
    assert b.state != "intro"
    for floor in (GROUND, UPPER, GROUND):
        x0, x1 = sc.st.balconies[-1]
        _put(sc, (x0 + x1) / 2 if floor == UPPER else ARENA_X + 30, floor)
        for _ in range(900):
            sc.p.x = (x0 + x1) / 2 if floor == UPPER else ARENA_X + 30
            _tick(game)
            if b.on_ground and b.y == floor and b.state in ("walk", "recover"):
                break
        assert b.y == floor, ("Doom did not follow", floor, b.y, b.state)
    kinds = [e[1] for e in sc.events]
    assert "hop" in kinds and "slam" in kinds
    print("thunder: Doom hops between floors with a shockwave landing OK")


# ---------------------------------------------------------------------------
# the bot
# ---------------------------------------------------------------------------
def bot_step(sc, i):
    p = sc.p
    held, press = set(), set()
    if p.state == "dead":
        return held, press
    # dodge whatever is flying at him on his floor
    for s in sc.shots:
        if s.friendly or (s.vx > 0) != (p.x > s.x):
            continue
        dx = abs(s.x - p.x)
        if s.kind == "wave":
            low = True
        else:
            if abs((p.y - s.y) - HIGH) > 8 and abs((p.y - s.y) - LOW) > 8:
                continue
            low = p.y - s.y < 20
        if dx < (70 if s.kind == "beam" else 46):
            if low:
                if p.on_ground and dx < (34 if s.kind != "beam" else 50):
                    press.add("up")
                return held, press
            held.add("down")
            return held, press
    b = sc.boss
    if sc.boss_on and b.alive and b.state not in ("intro", "asleep"):
        target = b
    else:
        near = [e for e in sc.enemies if e.alive and e.state != "emerge" and abs(e.y - p.y) < 20
                and -40 < e.x - p.x < 170]
        target = min(near, key=lambda e: abs(e.x - p.x)) if near else None
    if target is b and abs(b.y - p.y) > 20 and b.on_ground and p.on_ground:
        if b.y < p.y:                       # Doom is up on the walkway
            x0, x1 = sc.st.balconies[-1]
            if x0 + 8 < p.x < x1 - 8:
                press.add("up")
            else:
                held.add("right" if p.x < x0 + 8 else "left")
        else:
            held.add("down")
            press.add("up")
        return held, press
    if target is None:
        held.add("right")
        if i % 9 == 0 and sc.ki > 80:
            press.add("special")
        return held, press
    dx = target.x - p.x
    face = "right" if dx > 0 else "left"
    dist = abs(dx)
    reach = 34 if target is b else 26
    if (p.face > 0) != (dx > 0) and dist > 4:
        held.add(face)
        return held, press
    if dist < reach:
        if i % 7 == 0:
            if i % 35 == 0:
                press |= {"special", "punch"}
            elif i % 21 == 0:
                press |= {"special", "kick"}
            else:
                press.add("punch" if (i // 7) % 3 else "kick")
    elif dist < 160 and (sc.ki >= R.HADO_COST or sc.rapid) and i % 6 == 0 and p.state == "move":
        press.add("special")
    else:
        held.add(face)
    return held, press


def test_run(game):
    """A bot walks the street and beats Dr. Doom with real attacks."""
    game.new_run(seed=4242, start=10)
    sc = game.scene
    assert isinstance(sc, ThunderScene)
    _settle(game, R.INTRO + 2)
    hurt = 0
    for i in range(MAX_FRAMES):
        if game.scene is not sc:
            break
        if sc.phase == "play" and sc.hp < 70:
            hurt += 1
            sc.hp = sc.max_hp         # keep the bot alive: this checks the level can be finished
        held, press = bot_step(sc, i)
        _tick(game, held, press)
        if i == 400:
            shot(game, "thunder_street.png")
        if sc.boss_on and sc.boss.state == "walk" and not getattr(sc, "_shot_boss", False):
            sc._shot_boss = True
            shot(game, "thunder_boss.png")
        if i % 1800 == 0:
            print("  frame %d: x=%d y=%d area=%d boss=%s hp=%s" % (
                i, sc.p.x, sc.p.y, sc.area, sc.boss.state, sc.boss.hp))
    assert sc.result == "win", (sc.phase, sc.p.x, sc.boss.hp, sc.boss.state)
    kinds = [e[1] for e in sc.events]
    assert sc.boss_dealt >= R.BOSS_HP
    print("thunder: bot cleared the street in %d frames, score %d, refills %d, boss events %s" % (
        i, sc.score, hurt, sorted({k for k in kinds if k in ("beam", "hop", "slam", "summon", "fire")})))


def test_thunder(game):
    test_layouts()
    test_floors(game)
    test_dodging(game)
    test_doors(game)
    test_moves(game)
    test_enemies(game)
    test_lose(game)
    test_boss_hops(game)
    game.to_title()
    test_run(game)
    from akuma.game import LevelClear
    assert isinstance(game.scene, LevelClear) and game.scene.level == 10, game.scene
    game.to_title()


if __name__ == "__main__":
    from akuma.game import Game
    g = Game()
    test_thunder(g)
    print("OK")
