"""Headless test of level 7 (Hu Lao Gate): squads of 5-10 one- or two-hit
soldiers, reinforcements charging in, the KO counter, the Musou attack and
Lu Bu with his bodyguards.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/musou_test.py
"""

import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from akuma import musou as M  # noqa: E402
from akuma.fighters import HIT  # noqa: E402


def _fight(game, enemy):
    ow = game.overworld
    game.start_fight(enemy, ow.hp, False)
    fs = game.scene
    assert isinstance(fs, M.MusouScene), type(fs)
    while fs.phase != "fight":
        game.tick()
    return fs


def test_musou(game):
    from smoke_test import bot_fight, shot
    game.new_run(seed=3, start=7)
    ow = game.overworld
    grunts = [e for e in ow.enemies if not e.boss]
    sizes = [1 + len(e.allies) for e in grunts]
    assert all(5 <= n <= 10 for n in sizes), sizes
    assert all(g.hp in (HIT, 2 * HIT) for e in grunts for g in [e] + e.allies), "soldiers take 1-2 hits"
    # a squad: only ON_STAGE at once, the rest charge in
    fs = _fight(game, grunts[0])
    assert len(fs.foes) <= M.ON_STAGE and fs.total == sizes[0]
    # Musou: a full gauge and I wipes everyone on screen
    fs.gauge = M.MUSOU_MAX
    on = [f for f in fs.foes if not f.ko]
    game.input.virtual_pressed = {"shield"}
    game.tick()
    for _ in range(M.MUSOU_LEN + 5):
        game.tick()
    assert all(f.ko for f in on), [f.hp for f in on]
    print("musou: Shun Goku Satsu floored %d soldiers, gauge %d" % (len(on), fs.gauge))
    frames, _ = bot_fight(game, random.Random(1))
    assert fs.result == "win" and fs.kos >= sizes[0], (fs.result, fs.kos)
    print("musou: squad of %d beaten, %d KO" % (sizes[0], fs.kos))
    # Lu Bu and four bodyguards
    fs = _fight(game, ow.boss)
    assert fs.e.name == "LU BU" and fs.e.art.cid == "lubu" and fs.total == 5
    for _ in range(40):
        game.tick()
    shot(game, "musou_lubu.png")
    frames, _ = bot_fight(game, random.Random(2), max_frames=60 * 300)
    assert fs.result == "win", fs.result
    print("musou: Lu Bu defeated in %.1f s" % (frames / 60))


if __name__ == "__main__":
    from akuma.game import Game
    test_musou(Game())
    print("musou test passed")
