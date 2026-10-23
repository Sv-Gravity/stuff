"""Slice art_source/akuma_hands_doom.png (first-person Akuma hands, red ki
aura, black background) into akuma/assets/doom_hands/.

Rows of the sheet (all drawn as the RIGHT hand / both hands, arm coming up
from the bottom edge of the screen):
  idle_a   7  single right claw, idle loop
  idle_b   7  the other claw idle loop
  charge   7  both hands, a red ki ball grows between them
  swipe    6  claw slash (4) + return (2)
  release  8  both hands push the ki ball out
  idle_c   7  idle
Output: <row>_<i>.png, downscaled by SCALE (ROW_SCALE per row) (area filter on premultiplied
alpha, so the aura stays soft with no dark fringe), plus anchors.json:
{name: [[ax, ay], ...]} = the centre of the arm's base (bottom edge).

    python3 tools/make_doom_hands.py
"""
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "art_source", "akuma_hands_doom.png")
OUT = os.path.join(ROOT, "akuma", "assets", "doom_hands")
SCALE = 0.45
# the two-hand rows are drawn smaller on the sheet than the single-claw close
# ups; scale them up so a hand is about the same size on screen in every row
ROW_SCALE = {"charge": 0.68, "release": 0.68}

ROWS = [("idle_a", 30, 196, 7), ("idle_b", 200, 374, 7), ("charge", 374, 560, 7),
        ("swipe", 560, 730, 6), ("release", 730, 900, 8), ("idle_c", 900, 1086, 7)]


def best_cuts(prof, n, wmin):
    """n-1 cuts through the emptiest columns, each frame >= wmin wide (DP)."""
    L = len(prof)
    INF = float("inf")
    cost = np.full((n, L), INF)
    back = np.zeros((n, L), dtype=int)
    cost[0][0] = 0.0
    for k in range(1, n):
        prev = cost[k - 1]
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


def clean(rgba):
    """Black background -> transparent. The sheet has alpha already; drop the
    near-black low-alpha remnants and fade the dim outer aura by brightness
    so no dark fringe survives."""
    out = rgba.astype(np.float32)
    a = out[..., 3]
    mx = out[..., :3].max(axis=2)
    # dim pixels that are only partly opaque are aura edge: alpha from brightness
    edge = a < 250
    a = np.where(edge, np.minimum(a, np.clip((mx - 18.0) * 3.0, 0, 255)), a)
    a[a < 12] = 0
    out[..., 3] = a
    return out.astype(np.uint8)


def main():
    rgba = clean(np.array(Image.open(SRC).convert("RGBA")))
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".png"):
            os.remove(os.path.join(OUT, f))
    anchors = {}
    for name, y0, y1, n in ROWS:
        scale = ROW_SCALE.get(name, SCALE)
        band = rgba[y0:y1]
        a = band[..., 3]
        cols = (a > 40).sum(axis=0)
        xs = np.where(cols >= 2)[0]
        bx0 = xs[0]
        band = band[:, xs[0]:xs[-1] + 1]
        prof = band[..., 3].astype(np.float32).sum(axis=0)
        prof = np.convolve(prof, np.ones(5) / 5, mode="same")
        L = band.shape[1]
        edges = [0] + best_cuts(prof, n, int(0.62 * L / n)) + [L]
        anchors[name] = []
        sizes = []
        for i, (sx, ex) in enumerate(zip(edges, edges[1:])):
            piece = band[:, sx:ex]
            al = piece[..., 3]
            ys = np.where((al > 20).sum(axis=1) >= 2)[0]
            xs = np.where((al > 20).sum(axis=0) >= 1)[0]
            piece = piece[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1]
            # anchor: centre of the opaque run along the bottom edge (the arm's base)
            bot = np.where(piece[-3:, :, 3].max(axis=0) > 200)[0]
            ax = (bot[0] + bot[-1]) / 2.0 if len(bot) else piece.shape[1] / 2.0
            im = Image.fromarray(piece, "RGBA").convert("RGBa")
            w = max(1, int(round(piece.shape[1] * scale)))
            h = max(1, int(round(piece.shape[0] * scale)))
            im = im.resize((w, h), Image.BOX).convert("RGBA")
            arr = np.array(im)
            arr[..., 3][arr[..., 3] < 10] = 0
            Image.fromarray(arr, "RGBA").save(os.path.join(OUT, "%s_%d.png" % (name, i)))
            anchors[name].append([round(ax * scale, 1), h])
            sizes.append("%dx%d" % (w, h))
        print("%-8s %d frames  %s" % (name, n, " ".join(sizes)))
    with open(os.path.join(OUT, "anchors.json"), "w") as f:
        json.dump(anchors, f, indent=1)


if __name__ == "__main__":
    sys.exit(main())
