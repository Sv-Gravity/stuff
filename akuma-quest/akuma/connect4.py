"""Level 10: Connect Four against Ryu.

Akuma stands on the left edge, Ryu on the right, a 7 x 6 board on a rooftop
between them. Akuma picks a column and throws a fire-red hadouken that arcs
over and drops into the lowest free hole, where it keeps burning as his piece.
Ryu answers with a blue one. Akuma always goes first. Four in a row wins; the
loser eats one last fireball and goes down. A full board is a draw and a new
game starts (Akuma first again).

Ryu thinks with a negamax / alpha-beta search on bitboards: transposition
table, iterative deepening inside a time budget, threat-based move ordering,
and a heuristic that counts threats by row parity (odd rows for the first
player, even rows for the second) plus centre control. It runs on a worker
thread while Ryu "thinks", so the frame never freezes.
"""

import math
import random
import threading
import time

import pygame

from . import audio
from . import fight as F
from .akuma_sprites import CharArt, portrait
from .art import mix
from .config import W, H
from .font import draw_text
from .pause import PauseMenu

CONTROLS = [
    "LEFT / RIGHT (A / D): CHOOSE A COLUMN",
    "J / K / L / SPACE: THROW THE HADOUKEN",
    "YOUR FIREBALL DROPS TO THE LOWEST FREE HOLE",
    "GET FOUR IN A ROW: ACROSS, UP OR DIAGONAL",
    "YOU ALWAYS GO FIRST. A FULL BOARD IS A DRAW",
    "AND A NEW GAME STARTS",
]

# ==========================================================================
# the engine: bitboards, 7 bits per column (6 rows + a sentinel)
# ==========================================================================
COLS_N, ROWS_N = 7, 6
H1 = ROWS_N + 1
BOTTOM = sum(1 << (c * H1) for c in range(COLS_N))
BOARD = BOTTOM * ((1 << ROWS_N) - 1)
COL_MASK = [((1 << ROWS_N) - 1) << (c * H1) for c in range(COLS_N)]
TOP = [1 << (ROWS_N - 1 + c * H1) for c in range(COLS_N)]
BOT = [1 << (c * H1) for c in range(COLS_N)]
ORDER = (3, 2, 4, 1, 5, 0, 6)
# rows counted from the bottom, 1-based: odd rows (1, 3, 5) favour the first player
ODD_ROWS = sum(1 << (c * H1 + r) for c in range(COLS_N) for r in (0, 2, 4))
EVEN_ROWS = BOARD & ~ODD_ROWS
CENTER_W = [sum(1 << (c * H1 + r) for r in range(ROWS_N)) for c in range(COLS_N)]
WIN = 10000


def popcount(x):
    return bin(x).count("1")


def winning_cells(p, mask):
    """Empty cells where stones p would make four in a row."""
    # vertical
    r = (p << 1) & (p << 2) & (p << 3)
    for s in (H1, H1 - 1, H1 + 1):          # horizontal, diag /, diag \
        t = (p << s) & (p << 2 * s)
        r |= t & (p << 3 * s)
        r |= t & (p >> s)
        t = (p >> s) & (p >> 2 * s)
        r |= t & (p << s)
        r |= t & (p >> 3 * s)
    return r & (BOARD ^ mask)


def has_four(p):
    for s in (1, H1, H1 - 1, H1 + 1):
        m = p & (p >> s)
        if m & (m >> 2 * s):
            return True
    return False


class Timeout(Exception):
    pass

CW = (0, 1, 2, 4, 2, 1, 0)
CENTER = [(CW[c], COL_MASK[c]) for c in range(COLS_N) if CW[c]]


def evaluate(cur, opp, mask, n, mywin, oppwin):
    first = n % 2 == 0            # the side to move is the one who went first
    mg, og = (ODD_ROWS, EVEN_ROWS) if first else (EVEN_ROWS, ODD_ROWS)
    # a threat right above an enemy threat is dead weight
    mywin_ok = mywin & ~(oppwin << 1)
    oppwin_ok = oppwin & ~(mywin << 1)
    s = 0
    s += 40 * popcount(mywin_ok & mg) + 18 * popcount(mywin_ok & og)
    s -= 40 * popcount(oppwin_ok & og) + 18 * popcount(oppwin_ok & mg)
    # centre control
    for w, cm in CENTER:
        s += w * (popcount(cur & cm) - popcount(opp & cm)) * 3
    return s


class Brain:
    def __init__(self, budget=0.5, max_depth=42):
        self.budget = budget
        self.max_depth = max_depth
        self.tt = {}
        self.nodes = 0
        self.depth = 0
        self.last_time = 0.0

    def best_move(self, cur, mask):
        """cur: stones of the side to move. Returns a column."""
        t0 = time.perf_counter()
        self.deadline = t0 + self.budget
        self.nodes = 0
        n = popcount(mask)
        possible = (mask + BOTTOM) & BOARD
        legal = [c for c in ORDER if possible & COL_MASK[c]]
        # immediate win, then forced block
        mywin = winning_cells(cur, mask) & possible
        for c in legal:
            if mywin & COL_MASK[c]:
                self.depth, self.last_time = 1, time.perf_counter() - t0
                return c
        oppwin = winning_cells(cur ^ mask, mask) & possible
        for c in legal:
            if oppwin & COL_MASK[c]:
                self.depth, self.last_time = 1, time.perf_counter() - t0
                return c
        if len(self.tt) > 600000:
            self.tt.clear()
        best = legal[0]
        # safe default: a move that doesn't hand the opponent a win right above
        oppw_all = winning_cells(cur ^ mask, mask)
        for c in legal:
            if not ((possible & COL_MASK[c]) << 1) & oppw_all:
                best = c
                break
        self.depth = 0
        for depth in range(1, min(self.max_depth, 42 - n) + 1):
            try:
                score, mv = self._root(cur, mask, n, depth)
            except Timeout:
                break
            if mv is not None:
                best = mv
            self.depth = depth
            self.score = score
            if abs(score) > WIN - 100:
                break
            if time.perf_counter() > t0 + self.budget * 0.55:
                break               # the next depth wouldn't finish in time
        self.last_time = time.perf_counter() - t0
        return best

    def _root(self, cur, mask, n, depth):
        alpha, beta = -WIN * 2, WIN * 2
        possible = (mask + BOTTOM) & BOARD
        entry = self.tt.get(cur + mask)
        hint = entry[3] if entry else None
        cols = [c for c in ORDER if possible & COL_MASK[c]]
        if hint in cols:
            cols.remove(hint)
            cols.insert(0, hint)
        best, best_c = -WIN * 3, None
        opp = cur ^ mask
        for c in cols:
            mv = possible & COL_MASK[c]
            v = -self._nega(opp, mask | mv, n + 1, depth - 1, -beta, -alpha, 1)
            if v > best:
                best, best_c = v, c
            if v > alpha:
                alpha = v
        self.tt[cur + mask] = (depth, 0, best, best_c)
        return best, best_c

    def _nega(self, cur, mask, n, depth, alpha, beta, ply):
        self.nodes += 1
        if not self.nodes & 1023 and time.perf_counter() > self.deadline:
            raise Timeout
        if n >= 42:
            return 0
        possible = (mask + BOTTOM) & BOARD
        mywin = winning_cells(cur, mask)
        if possible & mywin:
            return WIN - ply
        opp = cur ^ mask
        oppwin = winning_cells(opp, mask)
        forced = possible & oppwin
        if forced:
            if forced & (forced - 1):
                return -(WIN - ply - 1)
            possible = forced
        possible &= ~(oppwin >> 1)
        if not possible:
            return -(WIN - ply - 1)
        if n >= 41:
            return 0
        if depth <= 0:
            return evaluate(cur, opp, mask, n, mywin, oppwin)
        key = cur + mask
        e = self.tt.get(key)
        hint = None
        a0 = alpha
        if e is not None:
            d, flag, v, hint = e
            if d >= depth:
                if v > WIN - 100:
                    v -= ply
                elif v < -(WIN - 100):
                    v += ply
                if flag == 0:
                    return v
                if flag == 1 and v >= beta:
                    return v
                if flag == -1 and v <= alpha:
                    return v
        # order: transposition hint, then by threats made, centre first on ties
        moves = []
        for i, c in enumerate(ORDER):
            mv = possible & COL_MASK[c]
            if mv:
                k = 1000 if c == hint else popcount(winning_cells(cur | mv, mask) & ~mask) * 10 - i
                moves.append((k, c, mv))
        moves.sort(reverse=True)
        best, best_c = -WIN * 3, None
        nm = mask
        for _, c, mv in moves:
            v = -self._nega(opp, nm | mv, n + 1, depth - 1, -beta, -alpha, ply + 1)
            if v > best:
                best, best_c = v, c
                if v > alpha:
                    alpha = v
                    if alpha >= beta:
                        break
        flag = 0 if a0 < best < beta else (1 if best >= beta else -1)
        sv = best
        if sv > WIN - 100:
            sv += ply
        elif sv < -(WIN - 100):
            sv -= ply
        self.tt[key] = (depth, flag, sv, best_c)
        return best


def find_four(grid):
    """grid[col][row] (row 0 = bottom), 0 empty / 1 / 2. Returns the four
    winning (col, row) cells, or None."""
    for c in range(COLS_N):
        for r in range(ROWS_N):
            who = grid[c][r]
            if not who:
                continue
            for dc, dr in ((1, 0), (0, 1), (1, 1), (1, -1)):
                cells = [(c + dc * k, r + dr * k) for k in range(4)]
                if all(0 <= x < COLS_N and 0 <= y < ROWS_N and grid[x][y] == who for x, y in cells):
                    return cells
    return None


# ==========================================================================
# the scene
# ==========================================================================
AKUMA, RYU = 1, 2
CELL = 17
BX = W // 2 - COLS_N * CELL // 2        # board holes, top-left
BY = 46
FEET = 166
AKUMA_X, RYU_X = 38, W - 38
SCALE = 0.66
PIECE = 15
PREP, FIRE = 12, 26                     # hadouken pose frames
FLY = 38                                # frames for the arc to the column top
THINK_MIN = 40
RYU_BUDGET = 0.55                       # seconds of search per move

FIRE_RAMP = [(90, 6, 0), (200, 30, 8), (250, 90, 20), (255, 160, 40), (255, 225, 110), (255, 250, 220)]
BLUE_RAMP = [(8, 16, 90), (24, 70, 210), (60, 140, 250), (120, 200, 255), (190, 235, 255), (245, 252, 255)]


def _ramp(ramp, t):
    t = max(0.0, min(1.0, t)) * (len(ramp) - 1)
    i = min(len(ramp) - 2, int(t))
    return mix(ramp[i], ramp[i + 1], t - i)


def recolor(img, ramp):
    """Map a fireball's brightness onto a colour ramp (keeps its shading)."""
    img = img.copy()
    w, h = img.get_size()
    lum = []
    for x in range(w):
        for y in range(h):
            c = img.get_at((x, y))
            if c.a:
                lum.append((x, y, c.a, 0.3 * c.r + 0.59 * c.g + 0.11 * c.b))
    if not lum:
        return img
    lo = min(v[3] for v in lum)
    hi = max(v[3] for v in lum)
    span = max(1.0, hi - lo)
    for x, y, a, l in lum:
        r, g, b = _ramp(ramp, 0.15 + 0.85 * (l - lo) / span)
        img.set_at((x, y), (int(r), int(g), int(b), a))
    return img


def _snap(img):
    """Hard pixel edges after smoothscale: alpha > 127 -> opaque, else gone."""
    out = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    m = pygame.mask.from_surface(img, 127)
    for x in range(img.get_width()):
        for y in range(img.get_height()):
            if m.get_at((x, y)):
                c = img.get_at((x, y))
                out.set_at((x, y), (c.r, c.g, c.b, 255))
    return out


def _piece_frames(frames):
    """The fireball turned head-down (flame licking upwards), cropped to its
    round head and fitted to a hole."""
    out = []
    for f in frames:
        f = pygame.transform.rotate(f, -90)          # right-facing -> head at the bottom
        w, h = f.get_size()
        side = min(w, h)
        head = f.subsurface((0, h - side - min(6, h - side), w, side + min(6, h - side))).copy()
        k = PIECE / max(head.get_size())
        img = pygame.transform.smoothscale(head, (max(1, round(head.get_width() * k)),
                                                  max(1, round(head.get_height() * k))))
        out.append(_snap(img))
    return out


class Fighter:
    def __init__(self, cid, x, flip):
        self.cid = cid
        self.art = CharArt(cid)
        self.x = float(x)
        self.home = x
        self.y = 0.0                    # height above the floor (knockdown arc)
        self.vx = self.vy = 0.0
        self.flip = flip
        self.pose, self.pose_t, self.span = "idle", 0, None
        self._cache = {}

    def set(self, pose, span=None):
        self.pose, self.pose_t, self.span = pose, 0, span

    def image(self, clock):
        key = self.art.resolve(self.pose, self.pose_t, clock, self.span)
        e = self._cache.get(key)
        if e is None:
            img, (ax, ay) = self.art.entry(key, self.flip)
            sw, sh = max(1, round(img.get_width() * SCALE)), max(1, round(img.get_height() * SCALE))
            e = self._cache[key] = (_snap(pygame.transform.smoothscale(img, (sw, sh))),
                                    (round(ax * SCALE), round(ay * SCALE)))
        return e

    def hands(self):
        """Where the fireball leaves from: the front-most point of the hadouken pose."""
        key = self.art.resolve("hado_fire", 999, 0, FIRE)
        img, (ax, ay) = self.art.entry(key, self.flip)
        m = pygame.mask.from_surface(img, 127)
        rects = m.get_bounding_rects()
        r = rects[0].unionall(rects) if rects else pygame.Rect(0, 0, 1, 1)
        col = r.left if self.flip else r.right - 1
        ys = [y for y in range(img.get_height()) if m.get_at((col, y))] or [ay - 30]
        hx = (col - ax) * SCALE
        hy = (sum(ys) / len(ys) - ay) * SCALE
        return hx, hy


class Shot:
    """A hadouken in flight: an arc to (ex, ey), then (optionally) a drop to drop_y."""

    def __init__(self, who, sx, sy, ex, ey, drop_y=None, high=50, fly=FLY):
        self.who = who
        self.sx, self.sy, self.ex, self.ey = sx, sy, ex, ey
        self.mx, self.my = (sx + ex) / 2, min(sy, ey) - high
        self.drop_y = drop_y
        self.t = 0
        self.fly = fly
        self.x, self.y = sx, sy
        self.angle = 0.0
        self.vy = 0.0
        self.dropping = False
        self.done = False

    def update(self):
        self.t += 1
        if not self.dropping:
            u = min(1.0, self.t / self.fly)
            a, b = (1 - u) ** 2, 2 * u * (1 - u)
            self.x = a * self.sx + b * self.mx + u * u * self.ex
            self.y = a * self.sy + b * self.my + u * u * self.ey
            dx = 2 * (1 - u) * (self.mx - self.sx) + 2 * u * (self.ex - self.mx)
            dy = 2 * (1 - u) * (self.my - self.sy) + 2 * u * (self.ey - self.my)
            self.angle = math.degrees(math.atan2(-dy, dx))
            if u >= 1:
                if self.drop_y is None:
                    self.done = True
                else:
                    self.dropping, self.vy = True, 1.5
        else:
            self.angle = -90
            self.vy = min(7.0, self.vy + 0.45)
            self.y += self.vy
            if self.y >= self.drop_y:
                self.y = self.drop_y
                self.done = True


class Connect4Scene:
    def __init__(self, game, seed=None, level=10, hp=None):
        F.init_shared()
        self.game = game
        self.level = level
        self.rng = random.Random(seed)
        self.max_hp = game.akuma_max
        self.hp = self.max_hp if hp is None else hp
        self.menu = PauseMenu(game, CONTROLS)
        self.akuma = Fighter("akuma", AKUMA_X, False)
        self.ryu = Fighter("ryu", RYU_X, True)
        self.fly_img = {}
        self.piece_img = {}
        for who, cid, ramp in ((AKUMA, "akuma", FIRE_RAMP), (RYU, "ryu", BLUE_RAMP)):
            src = [recolor(f, ramp) for f in CharArt(cid).projectile_frames()]
            small = []
            for f in src:
                k = 0.55
                small.append(_snap(pygame.transform.smoothscale(
                    f, (max(1, round(f.get_width() * k)), max(1, round(f.get_height() * k))))))
            self.fly_img[who] = small
            self.piece_img[who] = _piece_frames(src)
        self.portraits = {}
        for cid in ("akuma", "ryu"):
            p = portrait(cid)
            k = 16 / p.get_height()
            self.portraits[cid] = pygame.transform.smoothscale(
                p, (max(1, round(p.get_width() * k)), 16))
        self.bg = self._background()
        self.board_img = self._board()
        self.brain = Brain(RYU_BUDGET)
        self.games = 1
        self.phase = "intro"
        self.t = 0
        self.phase_t = 0
        self.end_t = 0
        self.shake = 0
        self.sparks = []
        self.result = None
        self.winner = None
        self.four = None
        self.finisher = None
        self.banner = None
        self._new_board()

    # ---- board state -----------------------------------------------------
    def _new_board(self):
        self.grid = [[0] * ROWS_N for _ in range(COLS_N)]
        self.bits = {AKUMA: 0, RYU: 0}
        self.mask = 0
        self.pieces = []                 # [col, row, who, birth frame]
        self.cursor = 3
        self.shot = None
        self.thrower = None
        self.col = None
        self.ai = None
        self.falling = []                # pieces dropping out after a draw

    def drop_row(self, col):
        """The lowest empty row of a column, or None when it is full."""
        for r in range(ROWS_N):
            if not self.grid[col][r]:
                return r
        return None

    def legal(self, col):
        return 0 <= col < COLS_N and self.drop_row(col) is not None

    def place(self, col, who):
        """Put a piece straight in (no animation). Returns its row."""
        r = self.drop_row(col)
        self.grid[col][r] = who
        bit = 1 << (col * H1 + r)
        self.bits[who] |= bit
        self.mask |= bit
        self.pieces.append([col, r, who, self.t])
        return r

    def full(self):
        return all(self.grid[c][ROWS_N - 1] for c in range(COLS_N))

    @staticmethod
    def cell_center(col, row):
        return BX + col * CELL + CELL // 2, BY + (ROWS_N - 1 - row) * CELL + CELL // 2

    @property
    def paused(self):
        return self.menu.open

    # ---- Ryu's brain (worker thread) ---------------------------------------
    def _start_think(self):
        box = {"move": None}
        cur, mask = self.bits[RYU], self.mask

        def run():
            box["move"] = self.brain.best_move(cur, mask)
        th = threading.Thread(target=run, daemon=True)
        box["thread"] = th
        self.ai = box
        th.start()

    # ---- update ----------------------------------------------------------
    def update(self, inp):
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.phase not in ("intro", "won", "lost") and self.menu.toggle(inp):
            return
        self.t += 1
        self.phase_t += 1
        if self.shake:
            self.shake -= 1
        for f in (self.akuma, self.ryu):
            f.pose_t += 1
        self._sparks()
        if self.banner:
            self.banner[1] -= 1
            if self.banner[1] <= 0:
                self.banner = None
        getattr(self, "_u_" + self.phase)(inp)

    def _go(self, phase):
        self.phase, self.phase_t = phase, 0

    def _u_intro(self, inp):
        if self.phase_t == 70:
            audio.play("fight")
        if self.phase_t >= 95:
            self._go("pick")

    def _u_pick(self, inp):
        if not self.legal(self.cursor):
            self._step_cursor(1) or self._step_cursor(-1)
        for d, key in ((-1, "left"), (1, "right")):
            if inp.pressed(key) and self._step_cursor(d):
                audio.play("select", 0.6)
        if inp.any_pressed("punch", "kick", "special") and self.legal(self.cursor):
            self._throw(AKUMA, self.cursor)

    def _step_cursor(self, d):
        c = self.cursor + d
        while 0 <= c < COLS_N:
            if self.legal(c):
                self.cursor = c
                return True
            c += d
        return False

    def _throw(self, who, col):
        self.thrower, self.col = who, col
        f = self.akuma if who == AKUMA else self.ryu
        f.set("hado_prep", PREP)
        self._go("throw")

    def _u_throw(self, inp):
        f = self.akuma if self.thrower == AKUMA else self.ryu
        if self.phase_t == PREP:
            f.set("hado_fire", FIRE)
            audio.play("hadouken" if self.thrower == AKUMA else "fireball")
            hx, hy = f.hands()
            r = self.drop_row(self.col)
            cx, cy = self.cell_center(self.col, r)
            self.shot = Shot(self.thrower, f.x + hx, FEET + hy, cx, BY - 12, drop_y=cy, high=58)
        if self.phase_t == PREP + FIRE:
            f.set("idle")
        if self.shot:
            self.shot.update()
            if self.shot.done:
                self.shot = None
                self._land()

    def _land(self):
        who, col = self.thrower, self.col
        r = self.place(col, who)
        x, y = self.cell_center(col, r)
        audio.play("hit", 0.7)
        self.shake = 4
        self._burst(x, y, who, 10)
        self.four = find_four(self.grid)
        if self.four:
            self.winner = who
            audio.play("ko")
            self._go("four")
        elif self.full():
            self._go("draw")
            self.banner = ["DRAW! AGAIN", 130]
        elif who == AKUMA:
            self._start_think()
            self._go("think")
        else:
            self._go("pick")

    def _u_think(self, inp):
        if self.phase_t >= THINK_MIN and self.ai and self.ai["move"] is not None:
            col = self.ai["move"]
            self.ai = None
            if not self.legal(col):          # can't happen, but never stall
                col = next(c for c in ORDER if self.legal(c))
            self._throw(RYU, col)

    def _u_draw(self, inp):
        if self.phase_t == 70:
            # the fireballs fall out of the bottom of the board
            for p in self.pieces:
                x, y = self.cell_center(p[0], p[1])
                self.falling.append([x, y, self.rng.uniform(-0.6, 0.6), self.rng.uniform(-1.5, 0), p[2]])
            self.pieces = []
            audio.play("whiff")
        for f in self.falling:
            f[0] += f[2]
            f[3] += 0.3
            f[1] += f[3]
        if self.phase_t >= 130:
            self.games += 1
            self._new_board()
            self._go("pick")

    def _u_four(self, inp):
        """The four pulse, then the winner throws one more at the loser."""
        if self.phase_t == 60:
            win = self.akuma if self.winner == AKUMA else self.ryu
            win.set("hado_prep", PREP)
        if self.phase_t == 60 + PREP:
            win = self.akuma if self.winner == AKUMA else self.ryu
            lose = self.ryu if self.winner == AKUMA else self.akuma
            win.set("hado_fire", FIRE)
            audio.play("hadouken")
            hx, hy = win.hands()
            self.finisher = Shot(self.winner, win.x + hx, FEET + hy, lose.x, FEET - 28, high=70, fly=46)
        if self.phase_t == 60 + PREP + FIRE:
            (self.akuma if self.winner == AKUMA else self.ryu).set("idle")
        if self.finisher:
            self.finisher.update()
            if self.finisher.done:
                lose = self.ryu if self.winner == AKUMA else self.akuma
                self._burst(self.finisher.x, self.finisher.y, self.winner, 18)
                self.finisher = None
                audio.play("heavy")
                self.shake = 10
                lose.set("launch")
                lose.vx = 1.6 if lose is self.ryu else -1.6
                lose.vy = 3.4
                self._go("won" if self.winner == AKUMA else "lost")
                self.end_t = 0

    def _knock(self):
        lose = self.ryu if self.winner == AKUMA else self.akuma
        win = self.akuma if self.winner == AKUMA else self.ryu
        if lose.pose == "launch":
            lose.x += lose.vx
            lose.y += lose.vy
            lose.vy -= 0.3
            lose.x = max(28, min(W - 28, lose.x))
            if lose.y <= 0:
                lose.y = 0
                lose.set("down")
                audio.play("land")
                self.shake = 4
        if self.end_t == 50:
            win.set("victory")

    def _u_won(self, inp):
        self._end(inp)

    def _u_lost(self, inp):
        self._end(inp)

    def _end(self, inp):
        self.end_t += 1
        self._knock()
        skip = self.end_t > 60 and inp.any_pressed("punch", "kick", "special", "start")
        if self.end_t >= 200 or skip:
            if self.phase == "won":
                self.result = "win"
                self.game.level_done(self, max(1, self.hp))
            else:
                self.result = "lose"
                self.game.level_failed(self)

    # ---- effects ---------------------------------------------------------
    def _burst(self, x, y, who, n):
        ramp = FIRE_RAMP if who == AKUMA else BLUE_RAMP
        for _ in range(n):
            a = self.rng.uniform(0, math.tau)
            s = self.rng.uniform(0.6, 2.4)
            self.sparks.append([x, y, math.cos(a) * s, math.sin(a) * s - 0.8, self.rng.randint(12, 24),
                                ramp[self.rng.randint(2, 5)]])

    def _sparks(self):
        for s in self.sparks:
            s[0] += s[2]
            s[1] += s[3]
            s[3] += 0.12
            s[4] -= 1
        self.sparks = [s for s in self.sparks if s[4] > 0]

    # ---- art -------------------------------------------------------------
    def _background(self):
        rng = random.Random(10)
        s = pygame.Surface((W, H))
        top, bot = (24, 12, 40), (226, 108, 52)
        for y in range(FEET):
            t = round(y / 150 * 12) / 12
            pygame.draw.line(s, mix(top, bot, min(1, t)), (0, y), (W, y))
        for _ in range(26):
            s.set_at((rng.randrange(W), rng.randrange(60)), (230, 220, 240))
        pygame.draw.circle(s, (255, 200, 120), (W // 2, 128), 46)        # setting sun behind the board
        pygame.draw.circle(s, (255, 230, 170), (W // 2, 128), 38)
        for i in range(3):
            pygame.draw.line(s, mix((255, 200, 120), bot, 0.5), (W // 2 - 60, 100 + i * 9), (W // 2 + 60, 100 + i * 9))
        # far rooftops of the city
        far = (64, 26, 44)
        x = -10
        while x < W:
            w = rng.randint(24, 46)
            h = rng.randint(118, 140)
            pygame.draw.rect(s, far, (x, h, w, FEET - h))
            pygame.draw.polygon(s, far, [(x - 5, h), (x + w + 5, h), (x + w - 4, h - 7), (x + 4, h - 7)])
            x += w + rng.randint(2, 10)
        # a pagoda on each side, behind the fighters
        dark = (40, 14, 28)
        for px in (18, W - 18):
            for i in range(4):
                w = 40 - i * 8
                y = 128 - i * 14
                pygame.draw.polygon(s, dark, [(px - w // 2 - 5, y), (px + w // 2 + 5, y),
                                              (px + w // 2 - 2, y - 6), (px - w // 2 + 2, y - 6)])
                pygame.draw.rect(s, dark, (px - w // 2 + 4, y, w - 8, 14))
            pygame.draw.line(s, dark, (px, 70), (px, 86))
        # lanterns on a string
        pygame.draw.line(s, (30, 10, 20), (0, 28), (W, 34))
        for lx in range(20, W, 46):
            ly = 28 + lx * 6 // W + 2
            pygame.draw.line(s, (30, 10, 20), (lx, ly - 2), (lx, ly + 1))
            pygame.draw.ellipse(s, (200, 40, 30), (lx - 4, ly + 1, 8, 9))
            pygame.draw.ellipse(s, (255, 150, 80), (lx - 2, ly + 3, 4, 5))
        # the rooftop the fight is on: tiles
        pygame.draw.rect(s, (52, 30, 36), (0, FEET - 4, W, H - FEET + 4))
        pygame.draw.line(s, (120, 70, 60), (0, FEET - 4), (W, FEET - 4))
        pygame.draw.line(s, (86, 50, 50), (0, FEET - 3), (W, FEET - 3))
        for x in range(0, W, 8):
            pygame.draw.line(s, (36, 20, 26), (x, FEET - 2), (x + (x - W // 2) // 10, H))
        for y in (FEET + 4, FEET + 10):
            pygame.draw.line(s, (40, 22, 28), (0, y), (W, y))
        return s

    def _board(self):
        bw, bh = COLS_N * CELL, ROWS_N * CELL
        pad = 5
        s = pygame.Surface((bw + pad * 2, H), pygame.SRCALPHA)
        # legs down to the roof
        for lx in (2, bw + pad * 2 - 8):
            s.fill((60, 34, 20), (lx, BY + bh, 6, FEET - BY - bh))
            s.fill((96, 58, 32), (lx + 1, BY + bh, 2, FEET - BY - bh))
        frame = pygame.Rect(0, BY - pad, bw + pad * 2, bh + pad * 2)
        s.fill((30, 16, 10), frame)
        s.fill((128, 78, 40), frame.inflate(-2, -2))
        rng = random.Random(4)
        for _ in range(40):                       # wood grain
            y = rng.randrange(frame.top + 2, frame.bottom - 2)
            x = rng.randrange(2, frame.width - 12)
            pygame.draw.line(s, (108, 64, 32), (x, y), (x + rng.randint(5, 18), y))
        s.fill((160, 104, 56), (1, frame.top + 1, frame.width - 2, 1))
        s.fill((84, 48, 24), (1, frame.bottom - 2, frame.width - 2, 1))
        for cx in (3, frame.width - 4):           # iron bolts
            for cy in (frame.top + 3, frame.bottom - 4):
                s.fill((40, 40, 46), (cx - 1, cy - 1, 2, 2))
        for c in range(COLS_N):
            for r in range(ROWS_N):
                x, y = pad + c * CELL + CELL // 2, BY + r * CELL + CELL // 2
                pygame.draw.circle(s, (70, 40, 20), (x, y), 8)
                pygame.draw.circle(s, (22, 12, 14), (x, y), 7)
                pygame.draw.circle(s, (34, 20, 22), (x + 1, y + 1), 5)
        return s, BX - pad

    # ---- draw ------------------------------------------------------------
    def draw(self, surf):
        ox, oy = 0, 0
        if self.shake:
            ox, oy = self.rng.choice((-2, -1, 1, 2)), self.rng.choice((-1, 0, 1))
        surf.blit(self.bg, (ox, oy))
        img, bx = self.board_img
        surf.blit(img, (bx + ox, oy))
        self._draw_pieces(surf, ox, oy)
        for f in self.falling:
            fr = self.piece_img[f[4]][(self.t // 5) % len(self.piece_img[f[4]])]
            surf.blit(fr, (round(f[0] - fr.get_width() / 2) + ox, round(f[1] - fr.get_height() / 2) + oy))
        for fighter in (self.akuma, self.ryu):
            self._draw_fighter(surf, fighter, ox, oy)
        if self.phase == "pick":
            self._draw_cursor(surf)
        for shot in (self.shot, self.finisher):
            if shot:
                self._draw_shot(surf, shot, ox, oy)
        for s in self.sparks:
            surf.fill(s[5], (round(s[0]) + ox, round(s[1]) + oy, 2 if s[4] > 8 else 1, 2 if s[4] > 8 else 1))
        if self.phase == "think":
            dots = "." * (1 + (self.phase_t // 12) % 3)
            draw_text(surf, dots, round(self.ryu.x) - 4, FEET - 54, (255, 255, 255))
        self._hud(surf)

    def _draw_pieces(self, surf, ox, oy):
        win = set(self.four or ())
        for col, row, who, born in self.pieces:
            frames = self.piece_img[who]
            fr = frames[(self.t // 5 + col * 3 + row) % len(frames)]
            x, y = self.cell_center(col, row)
            if (col, row) in win:
                k = 1.0 + 0.18 * math.sin(self.t * 0.25)
                fr = pygame.transform.scale_by(fr, k)
                ring = (255, 255, 255) if (self.t // 6) % 2 else (255, 230, 90)
                pygame.draw.circle(surf, ring, (x + ox, y + oy), 9, 1)
            surf.blit(fr, (round(x - fr.get_width() / 2) + ox, round(y - fr.get_height() / 2) + oy))

    def _draw_fighter(self, surf, f, ox, oy):
        img, (ax, ay) = f.image(self.t)
        x = round(f.x) - ax + ox
        y = FEET - round(f.y) - ay + oy
        pygame.draw.ellipse(surf, (24, 12, 18), (round(f.x) - 12 + ox, FEET - 2 + oy, 24, 5))
        surf.blit(img, (x, y))

    def _draw_cursor(self, surf):
        x, _ = self.cell_center(self.cursor, 0)
        bob = round(math.sin(self.t * 0.15) * 2)
        frames = self.piece_img[AKUMA]
        fr = frames[(self.t // 5) % len(frames)].copy()
        fr.set_alpha(170)
        surf.blit(fr, (x - fr.get_width() // 2, BY - 22 + bob))
        pygame.draw.polygon(surf, (255, 230, 90), [(x - 3, BY - 6 + bob), (x + 3, BY - 6 + bob), (x, BY - 3 + bob)])

    def _draw_shot(self, surf, shot, ox, oy):
        frames = self.fly_img[shot.who]
        fr = frames[(shot.t // 3) % len(frames)]
        fr = pygame.transform.rotate(fr, shot.angle)
        surf.blit(fr, (round(shot.x - fr.get_width() / 2) + ox, round(shot.y - fr.get_height() / 2) + oy))

    def _hud(self, surf):
        surf.fill((10, 6, 14), (0, 0, W, 20))
        pa, pr = self.portraits["akuma"], self.portraits["ryu"]
        surf.blit(pa, (2, 2))
        surf.blit(pr, (W - 2 - pr.get_width(), 2))
        draw_text(surf, "AKUMA", 6 + pa.get_width(), 3, (255, 90, 80))
        draw_text(surf, "RYU", W - 6 - pr.get_width(), 3, (110, 170, 255), align="right")
        ia = self.piece_img[AKUMA][(self.t // 5) % 8]
        ir = self.piece_img[RYU][(self.t // 5) % 8]
        surf.blit(pygame.transform.scale_by(ia, 0.6), (6 + pa.get_width(), 11))
        surf.blit(pygame.transform.scale_by(ir, 0.6), (W - 15 - pr.get_width(), 11))
        draw_text(surf, "CONNECT 4", W // 2, 3, (255, 220, 160), align="center")
        msg, col = "", (255, 255, 255)
        if self.phase == "pick":
            msg, col = "YOUR MOVE", (255, 200, 120)
        elif self.phase == "think":
            msg, col = "RYU IS THINKING", (150, 200, 255)
        elif self.phase == "throw":
            msg = "HADOUKEN!"
            col = (255, 140, 80) if self.thrower == AKUMA else (120, 180, 255)
        if self.games > 1 and self.phase != "intro":
            msg = (msg + "  " if msg else "") + "GAME %d" % self.games
        if msg:
            draw_text(surf, msg, W // 2, 12, col, align="center")
        if self.phase in ("pick", "think", "throw"):
            draw_text(surf, "LEFT/RIGHT: AIM   J/K/L: THROW", W // 2, H - 9, (220, 200, 210), align="center")
        if self.phase == "intro":
            draw_text(surf, "LEVEL %d" % self.level, W // 2, 50, (255, 220, 80), scale=2, align="center")
            draw_text(surf, "CONNECT FOUR VS RYU", W // 2, 70, (255, 255, 255), align="center")
            draw_text(surf, "DROP 4 HADOUKENS IN A ROW TO WIN", W // 2, 82, (230, 210, 240), align="center")
            draw_text(surf, "YOU GO FIRST", W // 2, 94, (230, 210, 240), align="center")
            if self.phase_t > 70:
                draw_text(surf, "GO!", W // 2, 108, (255, 60, 40), scale=3, align="center")
        if self.banner:
            draw_text(surf, self.banner[0], W // 2, 76, (255, 240, 200), scale=2, align="center")
        if self.phase in ("four", "won", "lost") and (self.phase != "four" or self.phase_t > 10):
            if self.winner == AKUMA:
                draw_text(surf, "AKUMA WINS", W // 2, 24, (255, 90, 60), scale=2, align="center")
            else:
                draw_text(surf, "RYU WINS", W // 2, 24, (110, 170, 255), scale=2, align="center")
        if self.menu.open:
            self.menu.draw(surf)
