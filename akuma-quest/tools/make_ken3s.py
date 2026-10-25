"""Dev tool: Third Strike Ken for the Dust II level (cs.py), made from Ryu.

There is no Ken gif in art_source/, so this repaints the ryu3s frames
(tools/make_doom_fighters.py): the white gi turns Ken red (shading kept) and
the black hair blond. The headband stays; everything else (poses, anchors,
the blue hadouken) is Ryu's.

    python tools/make_ken3s.py
"""

import os
import shutil

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CHARS = os.path.join(os.path.dirname(HERE), "akuma", "assets", "chars")
SRC, DST = os.path.join(CHARS, "ryu3s"), os.path.join(CHARS, "ken3s")


def repaint(path, out):
    im = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
    rgb, a = im[..., :3], im[..., 3]
    mx, mn = rgb.max(-1), rgb.min(-1)
    lum = rgb.mean(-1)
    solid = a > 0
    # the gi: light, nearly grey (Ryu's whites lean a little blue or yellow)
    gi = solid & (mx - mn < 44) & (lum > 120)
    t = (lum - 120) / 135
    red = np.stack([150 + 100 * t, 18 + 40 * t, 14 + 30 * t], -1)
    rgb[gi] = red[gi]
    # the hair: near-black or dark blue pixels in the top fifth of the body
    ys = np.nonzero(solid.any(1))[0]
    if len(ys):
        top = ys[0] + (ys[-1] - ys[0]) * 0.2
        rows = np.arange(rgb.shape[0])[:, None] <= top
        hair = solid & rows & (lum < 70) & ~((rgb[..., 0] > 120) & (rgb[..., 1] < 60))
        k = np.clip(rgb[..., 2] / 110, 0, 1)           # Ryu's blue highlights become the light strands
        gold = np.stack([196 + 56 * k, 140 + 86 * k, 30 + 60 * k], -1)
        clear = ~solid
        near = np.zeros_like(clear)                    # keep the hair's outer outline dark
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            near |= np.roll(np.roll(clear, dy, 0), dx, 1)
        edge = hair & near
        rgb[hair & ~edge] = gold[hair & ~edge]
    im[..., :3] = rgb
    Image.fromarray(np.clip(im, 0, 255).astype(np.uint8), "RGBA").save(out)


def main():
    os.makedirs(DST, exist_ok=True)
    for name in sorted(os.listdir(SRC)):
        src, dst = os.path.join(SRC, name), os.path.join(DST, name)
        if name.startswith("f") and name.endswith(".png"):
            repaint(src, dst)
        else:
            shutil.copy(src, dst)          # anchors, poses, the hadouken
    print("wrote", DST)


if __name__ == "__main__":
    main()
