"""Dev tool: find every sprite frame on Toshi's Pocket Fighter style sheets.

The sheets (art_source/sprites/) are ripped strips of frames on one flat
background colour, with no labels. This finds each frame (connected blobs,
grown a couple of pixels so a loose hair tuft or a spark stays with its body),
groups them into rows, and numbers them "row.index" top to bottom, left to
right. The frame lists in tools/extract_pocket.py refer to those numbers.

    python tools/pocket_sheets.py Akuma.png      writes a labelled contact sheet
                                                 to art_source/contact/ for picking frames
"""

import os
import sys

import numpy as np
import pygame
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "art_source", "sprites")
CONTACT = os.path.join(ROOT, "art_source", "contact")
BODY_PIXELS = 300   # a blob this big is a frame of its own; smaller ones are loose bits
JOIN = 4            # px a loose bit may sit from its frame
MAX_H = 140         # taller blobs are the big portrait art
ROW_TOL = 22        # px between frame middles on one strip


def load(name):
    rgb = np.array(Image.open(os.path.join(SRC, name)).convert("RGB")).astype(np.int16)  # name may be absolute
    c = rgb.astype(np.int32)
    packed = (c[..., 0] << 16) | (c[..., 1] << 8) | c[..., 2]
    bg = np.bincount(packed.ravel()).argmax()
    fg = packed != bg
    return rgb, fg


def _comp_mask(c, r):
    sub = pygame.Mask(r.size)
    sub.draw(c, (-r.x, -r.y))
    return pygame.surfarray.array_alpha(sub.to_surface(setcolor=(255, 255, 255, 255),
                                                       unsetcolor=(0, 0, 0, 0))).T > 0


def frames(name, max_h=MAX_H):
    """[(row, idx, (x0, y0, x1, y1), keep)] where keep is the frame's own pixel mask."""
    rgb, fg = load(name)
    h, w = fg.shape
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    alpha = pygame.surfarray.pixels_alpha(surf)
    alpha[:] = (fg.T * 255).astype(np.uint8)
    del alpha
    mask = pygame.mask.from_surface(surf)
    bodies, bits = [], []
    for c in mask.connected_components(4):
        r = c.get_bounding_rects()[0].unionall(c.get_bounding_rects())
        if c.count() >= BODY_PIXELS and r.h >= 16:
            bodies.append([r.x, r.y, r.right, r.bottom, _comp_mask(c, r)])
        else:
            bits.append((r, c))
    # loose bits (a hair tuft, a spark, a fist) join the body they touch or sit next to
    for r, c in bits:
        cx, cy = r.centerx, r.centery
        best, bd = None, JOIN + 1
        for b in bodies:
            dx = max(b[0] - cx, 0, cx - b[2])
            dy = max(b[1] - cy, 0, cy - b[3])
            d = max(dx, dy)
            if d < bd:
                best, bd = b, d
        if best is None:
            continue
        x0, y0 = min(best[0], r.x), min(best[1], r.y)
        x1, y1 = max(best[2], r.right), max(best[3], r.bottom)
        keep = np.zeros((y1 - y0, x1 - x0), bool)
        keep[best[1] - y0:best[3] - y0, best[0] - x0:best[2] - x0] |= best[4]
        keep[r.y - y0:r.bottom - y0, r.x - x0:r.right - x0] |= _comp_mask(c, r)
        best[:] = [x0, y0, x1, y1, keep]
    # rows: frames on one strip have about the same vertical middle
    bodies = [b for b in bodies if b[3] - b[1] <= max_h]
    bodies.sort(key=lambda b: (b[1] + b[3]) / 2)
    rows = []
    for b in bodies:
        mid = (b[1] + b[3]) / 2
        if rows and abs(mid - rows[-1][0]) <= ROW_TOL:
            rows[-1][1].append(b)
        else:
            rows.append([mid, [b]])
    out = []
    for ri, (_, row) in enumerate(rows):
        row.sort(key=lambda b: b[0])
        for i, (x0, y0, x1, y1, keep) in enumerate(row):
            out.append((ri, i, (x0, y0, x1, y1), keep))
    return rgb, out


def contact(name):
    rgb, fr = frames(name)
    img = Image.fromarray(rgb.astype(np.uint8))
    d = ImageDraw.Draw(img)
    for ri, i, (x0, y0, x1, y1), _ in fr:
        d.rectangle((x0 - 1, y0 - 1, x1, y1), outline=(255, 255, 0))
        d.text((x0 + 1, y1 + 1), "%d.%d" % (ri, i), fill=(255, 255, 255), stroke_width=1,
               stroke_fill=(0, 0, 0))
    os.makedirs(CONTACT, exist_ok=True)
    out = os.path.join(CONTACT, os.path.splitext(name)[0] + ".png")
    img.save(out)
    print("%s: %d frames in %d rows -> %s" % (name, len(fr), fr[-1][0] + 1 if fr else 0, out))


if __name__ == "__main__":
    pygame.init()
    for n in sys.argv[1:] or sorted(os.listdir(SRC)):
        contact(n)
