"""Headless test of level 10 (Connect Four against Ryu): the engine blocks and
takes immediate wins, finds fours in every direction and stays inside its time
budget; fireballs land in the lowest free hole in the right colours; and a bot
playing Akuma wins a game through the real input and throw animation.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python tests/connect4_test.py
"""

import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from akuma import connect4 as C  # noqa: E402
from akuma.connect4 import Connect4Scene, AKUMA, RYU  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def _bits(cells):
    b = 0
    for c, r in cells:
        b |= 1 << (c * C.H1 + r)
    return b


def _position(akuma, ryu):
    """(stones of the side to move = Ryu, mask)"""
    a, r = _bits(akuma), _bits(ryu)
    return r, a | r


# --------------------------------------------------------------------------
def test_engine():
    brain = C.Brain(0.5)
    # Akuma threatens bottom row 1-2-3: Ryu must block at 0 or 4 (both open -> any block)
    cur, mask = _position([(2, 0), (3, 0), (4, 0)], [(2, 1), (3, 1)])
    mv = brain.best_move(cur, mask)
    assert mv in (1, 5), ("did not block", mv)
    # vertical threat in column 6
    cur, mask = _position([(6, 0), (6, 1), (6, 2), (0, 0)], [(3, 0), (3, 1), (2, 0)])
    assert brain.best_move(cur, mask) == 6, "did not block the column"
    # Ryu has three up column 5 and Akuma threatens too: winning beats blocking
    cur, mask = _position([(0, 0), (1, 0), (2, 0), (6, 0)], [(5, 0), (5, 1), (5, 2)])
    assert brain.best_move(cur, mask) == 5, "missed its own win"
    # time budget and depth over a played-out game
    worst, depths = 0.0, []
    cur, mask = 0, 0
    for c in (3, 3, 2, 4, 4, 2, 5):            # some opening moves, then the brain plays both sides
        cur, mask = cur ^ mask, mask | (((mask + C.BOTTOM) & C.BOARD) & C.COL_MASK[c])
    for _ in range(12):
        t0 = time.perf_counter()
        c = brain.best_move(cur, mask)
        dt = time.perf_counter() - t0
        worst = max(worst, dt)
        depths.append(brain.depth)
        mv = ((mask + C.BOTTOM) & C.BOARD) & C.COL_MASK[c]
        cur, mask = cur ^ mask, mask | mv
        if C.has_four(cur ^ mask) or C.popcount(mask) == 42:
            break
    first = C.Brain(0.5)
    first.best_move(0, _bits([(3, 0)]))    # Ryu's very first reply
    assert worst < 0.8, ("search too slow", worst)
    assert first.depth >= 8, ("too shallow on the first reply", first.depth)
    print("connect4 engine: blocks, wins, first reply depth %d in %.2f s, worst move %.2f s, depths %s"
          % (first.depth, first.last_time, worst, depths))
    return first.depth


def test_find_four():
    def grid(cells):
        g = [[0] * 6 for _ in range(7)]
        for c, r in cells:
            g[c][r] = AKUMA
        return g
    lines = {"horizontal": [(1, 2), (2, 2), (3, 2), (4, 2)],
             "vertical": [(5, 1), (5, 2), (5, 3), (5, 4)],
             "diagonal /": [(0, 0), (1, 1), (2, 2), (3, 3)],
             "diagonal \\": [(3, 5), (4, 4), (5, 3), (6, 2)]}
    for name, cells in lines.items():
        assert sorted(C.find_four(grid(cells))) == sorted(cells), name
        assert C.has_four(_bits(cells)), name
        assert C.find_four(grid(cells[:3])) is None, name
        assert not C.has_four(_bits(cells[:3])), name
    # no wrap-around between columns
    assert not C.has_four(_bits([(0, 5), (1, 0), (1, 1), (1, 2)]))
    print("connect4: four in a row found across, up and both diagonals")


def _color(img):
    r = g = b = n = 0
    for x in range(img.get_width()):
        for y in range(img.get_height()):
            c = img.get_at((x, y))
            if c.a > 127:
                r, g, b, n = r + c.r, g + c.g, b + c.b, n + 1
    return r / n, g / n, b / n


def _wait_pick(game, sc, limit=60 * 20):
    for _ in range(limit):
        if sc.phase in ("pick", "won", "lost") or game.scene is not sc:
            return
        _tick(game)
    raise AssertionError("never got back to Akuma's turn: %s" % sc.phase)


def _aim_and_throw(game, sc, col):
    while sc.cursor != col:
        _tick(game, press=("right",) if col > sc.cursor else ("left",))
        _tick(game)
    _tick(game, press=("punch",))
    assert sc.phase == "throw", sc.phase


def test_landing(game):
    sc = Connect4Scene(game, seed=1)
    game.scene = sc
    _wait_pick(game, sc)
    sc.place(2, RYU)
    sc.place(2, AKUMA)
    _aim_and_throw(game, sc, 2)
    saw_flight = False
    while sc.phase == "throw":
        saw_flight |= sc.shot is not None
        _tick(game)
    assert saw_flight, "no fireball flew"
    assert sc.grid[2][2] == AKUMA and sc.grid[2][3] == 0, [sc.grid[2]]
    assert sc.pieces[-1][:3] == [2, 2, AKUMA]
    _wait_pick(game, sc)
    ryu = [p for p in sc.pieces if p[2] == RYU]
    assert len(ryu) == 2, "Ryu did not answer"
    col = ryu[-1][0]
    assert sc.grid[col][ryu[-1][1]] == RYU and (ryu[-1][1] == 0 or sc.grid[col][ryu[-1][1] - 1])
    ra, _, ba = _color(sc.piece_img[AKUMA][0])
    rr, _, br = _color(sc.piece_img[RYU][0])
    assert ra > ba + 60, ("Akuma's fireball isn't red", ra, ba)
    assert br > rr + 60, ("Ryu's fireball isn't blue", rr, br)
    print("connect4: fireball lands in the lowest free hole; Akuma red (%d,%d) Ryu blue (%d,%d)"
          % (ra, ba, rr, br))


def test_draw(game):
    sc = Connect4Scene(game, seed=2)
    game.scene = sc
    _wait_pick(game, sc)
    # a full board with no four, bar the last hole (column 6 top)
    pattern = ["AARRAAR", "RRAARRA", "AARRAAR", "RRAARRA", "AARRAAR", "RRAARR."]
    for r, row in enumerate(pattern):
        for c, ch in enumerate(row):
            if ch != ".":
                sc.place(c, AKUMA if ch == "A" else RYU)
    assert C.find_four(sc.grid) is None
    _aim_and_throw(game, sc, 6)
    for _ in range(300):
        if sc.phase == "draw":
            break
        _tick(game)
    assert sc.phase == "draw", sc.phase
    _wait_pick(game, sc)
    assert sc.games == 2 and not sc.pieces and sc.mask == 0
    print("connect4: full board -> DRAW! AGAIN, new game, Akuma first")


def bot_connect4(game, label="connect4_win.png"):
    """Akuma bot. It cheats a little: the board starts with two red fireballs
    on the bottom row (Ryu's two on top of them) so Akuma has a winning attack,
    and the bot searches longer than Ryu. Every move it makes still goes through
    the cursor, the throw and the fireball landing."""
    sc = game.scene
    assert isinstance(sc, Connect4Scene)
    frames = 0
    _wait_pick(game, sc)
    for c, who in ((2, AKUMA), (2, RYU), (3, AKUMA), (3, RYU)):
        sc.place(c, who)
    brain = C.Brain(1.5)
    turns = 0
    while game.scene is sc and sc.result is None and frames < MAX_FRAMES:
        if sc.phase == "pick":
            col = brain.best_move(sc.bits[AKUMA], sc.mask)
            _aim_and_throw(game, sc, col)
            turns += 1
            if turns == 2 and label:
                for _ in range(PRE_SHOT):
                    _tick(game)
                shot(game, "connect4.png")
        _tick(game)
        frames += 1
        if sc.phase == "won" and sc.end_t == 70 and label:
            shot(game, label)
    assert sc.result == "win", (sc.result, sc.phase, sc.grid)
    return frames


PRE_SHOT = 24


def test_connect4(game):
    test_find_four()
    depth = test_engine()
    test_landing(game)
    test_draw(game)
    game.scene = Connect4Scene(game, seed=10)
    f = bot_connect4(game)
    print("connect4: Akuma beats Ryu in %.1f s" % (f / 60))
    return depth


if __name__ == "__main__":
    from akuma.game import Game
    g = Game()
    g.level_done = lambda scene, hp: None
    g.level_failed = lambda scene: None
    test_connect4(g)
    print("connect4 test passed")
