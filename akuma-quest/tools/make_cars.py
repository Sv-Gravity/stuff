"""Dev tool: the level 3/4 cars from Toshi's damage sheet.

art_source/akuma_car_damage_sheet.png is a 7 x 5 grid: one column per model
(each on its own coloured gradient panel under a header label), one row per
damage stage (pristine, light, medium, heavy, destroyed). The sheet carries an
alpha matte, but it is soft and also covers the smoke plumes over the wrecked
cars and the stage labels in the first column. This cuts every car out, drops
the smoke, labels and specks, keeps the debris lying around the destroyed cars,
flips them to face right (the game's cars drive right) and shrinks them to the
game's car size:

    akuma/assets/cars/<model>_<stage>.png      e.g. ae86_0.png ... cougar_4.png

All five stages of a model share one canvas size and line up (the rear bumper
and the tyres stay put), so the car does not jump around as it is smashed; the
game takes its anchor and roof line from the pristine stage's pixels.

    python tools/make_cars.py              write the PNGs
    python tools/make_cars.py preview      also write a preview sheet to OUT_PREVIEW
"""

import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "art_source", "akuma_car_damage_sheet.png")
OUT = os.path.join(ROOT, "akuma", "assets", "cars")

MODELS = ["ae86", "mr2", "miata", "s2000", "gti", "rx7", "cougar"]
COLS = [0, 210, 432, 648, 862, 1070, 1305, 1536]      # panel edges on the sheet
ROWS = [50, 133, 218, 302, 394, 490]                   # stage bands (below the header)
LABEL_W = 88          # the first column's stage labels sit left of this, above the car
GAME_W = 100          # the pristine car's body width in game pixels (the old drawn cars: ~100)
ALPHA = 200           # matte cut-off for "solid"
MIN_DEBRIS = 30       # sheet-px area: smaller loose bits are specks
PAD = 2               # transparent margin round every canvas


def _components(mask):
    """4-connected labelling with a small union-find (numpy only)."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    parent = [0]

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for y in range(h):
        row = mask[y]
        for x in range(w):
            if not row[x]:
                continue
            up = lab[y - 1, x] if y else 0
            left = lab[y, x - 1] if x else 0
            if up and left:
                a, b = find(up), find(left)
                lab[y, x] = min(a, b)
                if a != b:
                    parent[max(a, b)] = min(a, b)
            elif up or left:
                lab[y, x] = up or left
            else:
                parent.append(len(parent))
                lab[y, x] = len(parent) - 1
    roots = np.array([find(i) for i in range(len(parent))], np.int32)
    return roots[lab]


def cut_cell(rgba, col, row):
    """One car (facing left, as on the sheet): (rgba crop, bbox of the main body, debris)."""
    x0, x1 = COLS[col] + 2, COLS[col + 1] - 2
    y0, y1 = ROWS[row], ROWS[row + 1]
    c = rgba[y0:y1, x0:x1].astype(int)
    al = c[..., 3]
    rgb = c[..., :3]
    solid = al >= ALPHA
    # smoke: soft-matted, grey and mid-dark; the car's own greys are fully opaque
    sat = rgb.max(-1) - rgb.min(-1)
    val = rgb.max(-1)
    smoke = (al < 250) & (sat < 34) & (val > 34) & (val < 150)
    # ...and only over the car: the tyres below its waist are grey and soft-edged too
    ys = np.nonzero(solid.any(1))[0]
    smoke[int(ys.min() + (ys.max() - ys.min()) * 0.45):] = False
    m = solid & ~smoke
    lab = _components(m)
    ids, counts = np.unique(lab[lab > 0], return_counts=True)
    main = ids[np.argmax(counts)]
    body = lab == main
    ys, xs = np.nonzero(body)
    bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
    keep = body.copy()
    mid = (by0 + by1) / 2
    for i, n in zip(ids, counts):
        if i == main or n < MIN_DEBRIS or row < 4:      # only the wreck has debris
            continue
        cy, cx = np.nonzero(lab == i)
        # loose parts lying on the ground around the car are debris; anything
        # floating above the car's waist (labels, smoke puffs) is not
        if cy.mean() > mid and cx.min() >= bx0 - 30 and cx.max() <= bx1 + 30:
            keep |= lab == i
    if col == 0:
        keep[:, :LABEL_W] &= np.arange(c.shape[0])[:, None] > by0 + (by1 - by0) * 0.3
        keep &= body | (np.arange(c.shape[0])[:, None] > mid)
    # the tyre line: the lowest row still about as wide as two tyres
    rc = body.sum(1)
    by1 = np.nonzero(rc >= rc.max() * 0.25)[0].max()
    if row < 4:
        keep[by1 + 2:] = False      # bits of the ground shadow hanging under the tyres
    # holes closed in by the car (a tyre or window the cut-offs nibbled) go back in
    holes = _components(~keep)
    edge = set(np.unique(np.concatenate([holes[0], holes[-1], holes[:, 0], holes[:, -1]])))
    for i in np.unique(holes[holes > 0]):
        if i not in edge:
            keep |= (holes == i) & (al >= 60)
    out = np.zeros(c.shape, np.uint8)
    out[..., :3] = rgb
    out[..., 3] = np.where(keep, 255, 0)
    return out, (bx0, by0, bx1, by1)


def _shrink(img, k):
    """Area-average the colours (over the kept pixels only), then a hard alpha."""
    h, w = img.shape[:2]
    nw, nh = max(1, round(w * k)), max(1, round(h * k))
    a = img[..., 3:4].astype(np.float32) / 255
    pre = img[..., :3].astype(np.float32) * a
    pim = Image.fromarray(np.concatenate([pre, a * 255], -1).clip(0, 255).astype(np.uint8), "RGBA")
    small = np.array(pim.resize((nw, nh), Image.BOX)).astype(np.float32)
    al = small[..., 3]
    rgb = np.where(al[..., None] > 0, small[..., :3] * 255 / np.maximum(al[..., None], 1), 0)
    out = np.zeros((nh, nw, 4), np.uint8)
    out[..., :3] = rgb.clip(0, 255).astype(np.uint8)
    out[..., 3] = np.where(al >= 120, 255, 0)
    return out


def _outline(img):
    """A 1 px dark outline around the silhouette, like the game's other sprites."""
    a = img[..., 3] > 0
    grow = a.copy()
    grow[1:] |= a[:-1]
    grow[:-1] |= a[1:]
    grow[:, 1:] |= a[:, :-1]
    grow[:, :-1] |= a[:, 1:]
    edge = grow & ~a
    out = img.copy()
    out[edge] = (14, 10, 20, 255)
    return out


def build():
    sheet = np.array(Image.open(SRC).convert("RGBA"))
    result = {}
    for col, name in enumerate(MODELS):
        cells = [cut_cell(sheet, col, row) for row in range(5)]
        # common anchor: the rear (right edge on the sheet) and the tyre line
        pw = cells[0][1][2] - cells[0][1][0] + 1
        k = GAME_W / pw
        imgs = []
        for img, (bx0, by0, bx1, by1) in cells:
            ys, xs = np.nonzero(img[..., 3])
            # shift so the body's rear edge sits at x = 0 and its bottom at y = 0
            imgs.append((img, xs.min() - bx1, xs.max() - bx1, ys.min() - by1, ys.max() - by1))
        left = min(i[1] for i in imgs)
        right = max(i[2] for i in imgs)
        top = min(i[3] for i in imgs)
        bottom = max(i[4] for i in imgs)
        out = []
        for img, (bx0, by0, bx1, by1) in cells:
            big = np.zeros((bottom - top + 1, right - left + 1, 4), np.uint8)
            ys, xs = np.nonzero(img[..., 3])
            big[ys - by1 - top, xs - bx1 - left] = img[ys, xs]
            small = _shrink(big[:, ::-1], k)          # face right
            can = np.zeros((small.shape[0] + 2 * PAD, small.shape[1] + 2 * PAD, 4), np.uint8)
            can[PAD:-PAD, PAD:-PAD] = small
            out.append(_outline(can))
        result[name] = dict(frames=out, body_w=round(pw * k))
    return result


def main():
    os.makedirs(OUT, exist_ok=True)
    res = build()
    for name, r in res.items():
        for st, f in enumerate(r["frames"]):
            Image.fromarray(f, "RGBA").save(os.path.join(OUT, "%s_%d.png" % (name, st)))
        print(name, r["frames"][0].shape[1], "x", r["frames"][0].shape[0], "body", r["body_w"])
    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        dst = os.environ.get("OUT_PREVIEW", os.path.join(ROOT, "cars_preview.png"))
        cw = max(f.shape[1] for r in res.values() for f in r["frames"]) + 4
        chh = max(f.shape[0] for r in res.values() for f in r["frames"]) + 4
        sheet = np.zeros((chh * 5, cw * 7, 4), np.uint8)
        sheet[..., :3] = (60, 120, 60)
        sheet[..., 3] = 255
        for c, r in enumerate(res.values()):
            for s, f in enumerate(r["frames"]):
                sub = sheet[s * chh + 2:s * chh + 2 + f.shape[0], c * cw + 2:c * cw + 2 + f.shape[1]]
                a = f[..., 3:4] > 0
                sub[..., :3] = np.where(a, f[..., :3], sub[..., :3])
        Image.fromarray(sheet).resize((sheet.shape[1] * 3, sheet.shape[0] * 3), Image.NEAREST).save(dst)
        print("preview", dst)


if __name__ == "__main__":
    main()
