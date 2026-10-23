"""Slice art_source/akuma_fireballs_explosions_sheet.png into akuma/assets/fx/.

The sheet is RGBA (real alpha). Each labelled row is cut into frames by
splitting the row band on empty columns. Output: akuma/assets/fx/<row>_<i>.png
(native sheet resolution, tight bbox; akuma/fx.py scales at load time).

    python3 tools/make_fx.py
Needs PIL + numpy (tool only; the game loads the PNGs with pygame).
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "art_source", "akuma_fireballs_explosions_sheet.png")
OUT = os.path.join(ROOT, "akuma", "assets", "fx")

LX = (138, 895)    # left panel, right of the row labels
RX = (1004, 1512)   # right panel, right of the row labels
# name: (x range, y0, y1, frame count)
ROWS = {
    "start": (LX, 36, 76, 7),
    "charge": (LX, 76, 133, 8),
    "release": (LX, 133, 180, 3),
    "fly": (LX, 180, 234, 9),
    "fly_alt": (LX, 234, 285, 10),
    "hit_small": (LX, 285, 338, 8),
    "hit_large": (LX, 338, 409, 9),
    "hit_wall": (LX, 409, 470, 8),
    "fade": ((160, 895), 470, 520, 12),
    "var_regular": (RX, 40, 102, 8),
    "var_large": (RX, 102, 178, 7),
    "var_dark": (RX, 178, 245, 7),
    "explode_small": (RX, 288, 352, 7),
    "explode_medium": (RX, 352, 427, 6),
    "explode_large": (RX, 427, 515, 5),
}
ALPHA_T = 24       # alpha counted as "ink" for column splitting


def best_cuts(prof, n, wmin):
    """n-1 cut columns minimising the summed ink under them (DP), with every
    frame at least wmin wide.  The glows of neighbouring frames touch, so
    plain gap-splitting is unreliable; the frame count per row is known."""
    L = len(prof)
    INF = float("inf")
    # cost[k][x]: best cost with k cuts, the last one at x
    cost = np.full((n, L), INF)
    back = np.zeros((n, L), dtype=int)
    cost[0][0] = 0.0
    for k in range(1, n):
        prev = cost[k - 1]
        # running argmin of prev over [0, x - wmin]
        best, bi = INF, 0
        for x in range(L):
            j = x - wmin
            if j >= 0 and prev[j] < best:
                best, bi = prev[j], j
            if best < INF:
                cost[k][x] = best + prof[x]
                back[k][x] = bi
    last = cost[n - 1].copy()
    last[L - wmin + 1:] = INF
    x = int(np.argmin(last))
    cuts = []
    for k in range(n - 1, 0, -1):
        cuts.append(x)
        x = back[k][x]
    return sorted(cuts)


def cut_row(rgba, name, xr, y0, y1, n):
    band = rgba[y0:y1, xr[0]:xr[1]].copy()
    raw = band[..., 3].copy()
    a = raw.astype(np.float32)
    if name == "hit_wall":
        # the wall-splat rows carry a dark speckled square; fade the dark
        # parts so only the lit splat + debris stays on top of game walls
        lum = band[..., :3].max(axis=2).astype(np.float32)
        a *= np.clip((lum - 25.0) / 70.0, 0.0, 1.0)
    # the sheet's background haze sits at alpha ~1-30: ramp it out
    a = np.clip((a - 28.0) * (255.0 / 227.0), 0, 255)
    band[..., 3] = a.astype(np.uint8)
    ink = (raw > ALPHA_T).sum(axis=0)
    xs = np.where(ink >= 2)[0]
    band = band[:, xs[0]:xs[-1] + 1]
    prof = raw[:, xs[0]:xs[-1] + 1].astype(np.float32).sum(axis=0)
    prof = np.convolve(prof, np.ones(3) / 3, mode="same")
    L = band.shape[1]
    edges = [0] + best_cuts(prof, n, max(8, int(0.62 * L / n))) + [L]
    frames = []
    for sx, ex in zip(edges, edges[1:]):
        piece = band[:, sx:ex]
        ys = np.where((piece[..., 3] > ALPHA_T).any(axis=1))[0]
        xs = np.where((piece[..., 3] > 0).any(axis=0))[0]
        if len(ys) == 0:
            continue
        piece = piece[max(0, ys[0] - 1):ys[-1] + 2, xs[0]:xs[-1] + 1]
        frames.append(piece)
    return frames


def main():
    rgba = np.array(Image.open(SRC).convert("RGBA"))
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".png"):
            os.remove(os.path.join(OUT, f))
    for name, (xr, y0, y1, n) in ROWS.items():
        frames = cut_row(rgba, name, xr, y0, y1, n)
        for i, fr in enumerate(frames):
            Image.fromarray(fr, "RGBA").save(os.path.join(OUT, "%s_%d.png" % (name, i)))
        print("%-15s %2d frames  %s" % (name, len(frames),
                                        " ".join("%dx%d" % (f.shape[1], f.shape[0]) for f in frames)))


if __name__ == "__main__":
    sys.exit(main())
