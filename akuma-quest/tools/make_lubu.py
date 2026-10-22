"""Dev tool: Lu Bu (level 7's boss) from Ryu's drawings.

The sprite pack has no Lu Bu, so this recolours Ryu's frames (white gi -> dark
armour with gold trim, red headband -> gold) and gives him the two long
pheasant tail plumes from his helmet. Output: akuma/assets/chars/lubu/.

    python tools/make_lubu.py
"""

import math
import os
import shutil

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "akuma", "assets", "chars", "ryu")
OUT = os.path.join(ROOT, "akuma", "assets", "chars", "lubu")
PAD = 34            # room above the head for the plumes
ARMOUR = np.array([70, 34, 60])      # dark plum lacquer
TRIM = np.array([235, 190, 70])      # gold
PLUME = (205, 60, 30)
PLUME_DARK = (110, 24, 16)


def recolour(a):
    rgb = a[..., :3].astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = rgb.mean(-1) / 255
    out = rgb.copy()
    gi = (g >= r) & (b >= r - 10) & (rgb.max(-1) > 100)       # Ryu's pale blue-white gi
    out[gi] = ARMOUR * (0.35 + 1.1 * lum[gi, None])
    red = (r > 125) & (g < 60)                                 # headband, gloves, belt bits
    out[red] = TRIM * (0.55 + 0.6 * lum[red, None])
    hair = (r > g * 2) & (r <= 125)                            # dark red-brown hair -> black
    out[hair] = np.array([28, 22, 30]) + 60 * lum[hair, None]
    a = a.copy()
    a[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return a


def plumes(img, ax):
    """Two long pheasant plumes rising from the helmet and arching back."""
    a = np.array(img)
    ys, xs = np.where(a[..., 3] > 0)
    # the head: the highest part near the body's middle (not a raised foot or fist)
    mid = np.abs(xs - ax) <= 12
    top = ys[mid].min() if mid.any() else ys.min()
    near = xs[mid & (ys <= top + 4)]
    hx = int(np.median(near)) if len(near) else ax
    d = ImageDraw.Draw(img)
    for k, (reach, rise) in enumerate(((26, 30), (18, 24))):
        pts = []
        for i in range(30):
            t = i / 29
            # up out of the helmet, then over and back, the tip dipping
            x = hx + 2 * k - reach * t ** 1.5
            y = top + 3 - rise * math.sin(t * math.pi * 0.85)
            pts.append((x, y))
        d.line(pts, fill=PLUME_DARK + (255,), width=4)
        d.line(pts, fill=PLUME + (255,), width=2)
        d.line(pts[:18], fill=(250, 150, 70, 255), width=1)
    return img


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    anchors = []
    for line in open(os.path.join(SRC, "anchors.txt")):
        n, x, y = line.split()
        x, y = int(x), int(y)
        im = Image.open(os.path.join(SRC, n + ".png")).convert("RGBA")
        a = recolour(np.array(im))
        big = Image.new("RGBA", (im.width + 24, im.height + PAD))
        big.paste(Image.fromarray(a, "RGBA"), (12, PAD))
        plumes(big, x + 12).save(os.path.join(OUT, n + ".png"))
        anchors.append("%s %d %d" % (n, x + 12, y + PAD))
    with open(os.path.join(OUT, "anchors.txt"), "w") as f:
        f.write("\n".join(anchors) + "\n")
    shutil.copy(os.path.join(SRC, "poses.txt"), OUT)
    for f in os.listdir(SRC):
        if f.startswith(("projectile", "air_projectile")):
            a = np.array(Image.open(os.path.join(SRC, f)).convert("RGBA"))
            rgb = a[..., :3].astype(np.float32)
            lum = rgb.mean(-1, keepdims=True) / 255
            a[..., :3] = np.clip(np.array([200, 60, 255]) * (0.3 + lum), 0, 255).astype(np.uint8)
            Image.fromarray(a, "RGBA").save(os.path.join(OUT, f))
        elif f == "portrait.png":
            a = np.array(Image.open(os.path.join(SRC, f)).convert("RGBA"))
            Image.fromarray(recolour(a), "RGBA").save(os.path.join(OUT, f))
    print("lubu: %d frames" % len(anchors))


if __name__ == "__main__":
    main()
