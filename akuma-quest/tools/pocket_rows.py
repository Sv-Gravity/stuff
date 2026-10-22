"""Dev tool: rows r0..r1 of a sheet as labelled strips, bigger than the contact sheet.

    python tools/pocket_rows.py Ryu.png 10 20 out.png [scale]
"""
import os, sys, pickle
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw
import pygame
pygame.init()
import pocket_sheets as ps
name, r0, r1, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
k = float(sys.argv[5]) if len(sys.argv) > 5 else 1.5
cache = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pocket_cache_%s.pkl" % name)
if os.path.exists(cache):
    rgb, fr = pickle.load(open(cache, "rb"))
else:
    rgb, fr = ps.frames(name)
    pickle.dump((rgb, fr), open(cache, "wb"))
rows = {}
for ri, i, box, keep in fr:
    if r0 <= ri <= r1:
        rows.setdefault(ri, []).append((i, box, keep))
strips = []
for ri in sorted(rows):
    imgs = []
    for i, (x0, y0, x1, y1), keep in rows[ri]:
        a = np.dstack([rgb[y0:y1, x0:x1].astype(np.uint8), np.where(keep, 255, 0).astype(np.uint8)])
        im = Image.fromarray(a, "RGBA")
        im = im.resize((round(im.width * k), round(im.height * k)), Image.NEAREST)
        imgs.append((i, im))
    h = max(im.height for _, im in imgs) + 14
    w = sum(im.width + 6 for _, im in imgs) + 40
    s = Image.new("RGB", (w, h), (40, 40, 60))
    d = ImageDraw.Draw(s)
    d.text((2, 2), "R%d" % ri, fill=(255, 255, 0))
    x = 40
    for i, im in imgs:
        s.paste(im, (x, h - 14 - im.height), im)
        d.text((x, h - 12), "%d.%d" % (ri, i), fill=(255, 255, 255))
        x += im.width + 6
    strips.append(s)
W = max(s.width for s in strips)
H = sum(s.height for s in strips)
o = Image.new("RGB", (W, H), (20, 20, 30))
y = 0
for s in strips:
    o.paste(s, (0, y)); y += s.height
o.save(out)
print(W, H)
