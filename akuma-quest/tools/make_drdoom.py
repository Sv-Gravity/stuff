"""Dev tool: Dr. Doom from Toshi's "Doom Pocket Fighter" sheet.

That sheet (art_source/drdoom_sheet.png) is one big painted page: a light grey
paper background, drop shadows, text labels, a portrait and a face box. This
cuts every drawing off the paper at game scale and lays them out on a flat
background as art_source/sprites/DrDoom.png, one strip per animation, so the
normal pipeline (tools/extract_pocket.py with tools/specs/drdoom.py) can pick
frames from it like any other Pocket Fighter sheet. Also writes his HUD
portrait (from the face box).

    python tools/make_drdoom.py            clean sheet + portrait + extract
"""

import os
import sys

import numpy as np
import pygame
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "art_source", "drdoom_sheet.png")
CLEAN = os.path.join(ROOT, "art_source", "sprites", "DrDoom.png")
OUT = os.path.join(ROOT, "akuma", "assets", "chars", "drdoom")

PAPER = np.array([219, 215, 211])   # the sheet's background grey
INK = 28            # a pixel this far (per channel) from the paper is drawing
K = 0.62            # sheet px -> game px (idle ~68 px tall, a little over Ryu's 66)
FB_K = 0.65         # the fireball, further shrunk to Ryu's fireball size
HOLE = 60           # paper-coloured holes smaller than this (sheet px) are highlights, not gaps
BG = (255, 0, 255)  # the clean sheet's flat background
GAP, PITCH = 14, 110

# every drawing: its rough box on the painted sheet (x0, y0, x1, y1); one strip each
STRIPS = [
    ("idle", [(17, 386, 108, 499), (111, 386, 202, 499), (213, 387, 309, 499), (322, 388, 422, 499)]),
    ("walk", [(469, 392, 580, 499), (587, 388, 678, 499), (687, 387, 780, 499), (787, 390, 881, 499)]),
    ("crouch", [(937, 411, 1032, 502), (1039, 416, 1133, 502), (1138, 414, 1229, 501)]),
    ("jump", [(21, 565, 108, 685), (120, 530, 219, 648), (231, 554, 335, 669), (328, 602, 416, 696)]),
    ("air_jump", [(452, 575, 556, 681), (566, 543, 680, 664), (688, 588, 794, 696)]),
    ("dash", [(841, 590, 960, 681), (986, 590, 1105, 682), (1122, 588, 1236, 683)]),
    ("light_punch", [(20, 769, 100, 867), (119, 767, 213, 866), (215, 766, 316, 866)]),
    ("light_kick", [(359, 768, 450, 867), (479, 763, 579, 867)]),
    ("strong_punch", [(657, 766, 752, 867), (763, 764, 886, 867)]),
    ("strong_kick", [(950, 764, 1063, 867), (1089, 762, 1212, 867)]),
    ("fireball", [(24, 943, 122, 1043), (133, 950, 224, 1043), (237, 963, 328, 1044)]),
    ("teleport", [(455, 951, 555, 1048), (575, 925, 680, 1050), (693, 948, 776, 1048)]),
    ("hellfire", [(835, 925, 989, 1060), (989, 925, 1222, 1060)]),
    ("hit", [(21, 1109, 113, 1216), (129, 1121, 223, 1215), (232, 1090, 310, 1207), (310, 1158, 425, 1217)]),
    ("win", [(510, 1086, 642, 1220)]),
    ("lose", [(718, 1133, 828, 1219)]),
]
# the text labels that reach into a drawing's box
LABELS = [(472, 1072, 584, 1094)]
FIREBALL = (328, 955, 420, 1040)    # the green ball, cut off the fireball pose
FACE_BOX = (743, 113, 866, 238)     # inside the face box's frame
PORTRAIT_SIZE = 30


def _mask(b):
    s = pygame.Surface(b.shape[::-1], pygame.SRCALPHA)
    a = pygame.surfarray.pixels_alpha(s)
    a[:] = (b.T * 255).astype(np.uint8)
    del a
    return pygame.mask.from_surface(s)


def _array(m, w, h):
    s = m.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
    return pygame.surfarray.array_alpha(s).T[:h, :w] > 0


def _parts(b):
    """[(count, rect, bool array)] of a mask's connected parts, biggest first."""
    h, w = b.shape
    out = []
    for c in _mask(b).connected_components(1):
        rs = c.get_bounding_rects()
        out.append((c.count(), rs[0].unionall(rs), _array(c, w, h)))
    out.sort(key=lambda p: -p[0])
    return out


def cut_out(rgb, box):
    """The drawing in box as RGBA at sheet size: paper, labels and shadow removed."""
    x0, y0, x1, y1 = box
    p = 6
    sub = rgb[y0 - p:y1 + p, x0 - p:x1 + p].astype(np.int32)
    h, w = sub.shape[:2]
    ink = np.abs(sub - PAPER).max(-1) > INK
    # the blue-grey drop shadow under the feet
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    shadow = (b - np.maximum(r, g) > 18) & (b < 215)
    rows = np.arange(h)[:, None]
    ink &= ~(shadow & (rows >= y1 - y0 + p - 14))
    # only what lies in the box (the next drawing's edge, labels and the fireball stay out)
    inside = np.zeros_like(ink)
    inside[p:p + y1 - y0, p:p + x1 - x0] = True
    ink &= inside
    for lx0, ly0, lx1, ly1 in LABELS:
        ink[max(0, ly0 - y0 + p):max(0, ly1 - y0 + p), max(0, lx0 - x0 + p):max(0, lx1 - x0 + p)] = False
    # paper-coloured holes too small to be a gap between limbs are highlights
    for n, rect, part in _parts(~ink):
        if n < HOLE and rect.x > 0 and rect.y > 0 and rect.right < w and rect.bottom < h:
            ink |= part
    # keep the body and whatever sits on or right next to it (sparks, the halo)
    parts = _parts(ink)
    body = parts[0][2].copy()
    br = parts[0][1]
    for n, rect, part in parts[1:]:
        if n < 6:
            continue
        cx, cy = rect.centerx, rect.centery
        if rect.x <= p or rect.y <= p or rect.right >= w - p or rect.bottom >= h - p:
            continue    # cut off by the box: a neighbouring drawing's edge
        if br.x - 10 <= cx <= br.right + 10 and br.y - 14 <= cy <= br.bottom + 4:
            body |= part
    # a 1px rim of pale paper blend on the outside edge is the anti-aliasing halo
    for _ in range(2):
        edge = body & ~_erode(body)
        lum = sub.mean(-1)
        sat = sub.max(-1) - sub.min(-1)
        body &= ~(edge & (lum > 150) & (sat < 40))
    rgba = np.dstack([sub.astype(np.uint8), np.where(body, 255, 0).astype(np.uint8)])
    ys, xs = np.where(body)
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _erode(b):
    e = b.copy()
    e[1:] &= b[:-1]
    e[:-1] &= b[1:]
    e[:, 1:] &= b[:, :-1]
    e[:, :-1] &= b[:, 1:]
    return e


def shrink(rgba, k):
    """Area-average down to game scale, then hard alpha (no soft edge, no paper halo)."""
    a = rgba[..., 3:].astype(np.float32) / 255
    pre = np.dstack([rgba[..., :3] * a, a * 255]).astype(np.float32)
    w, h = max(1, round(rgba.shape[1] * k)), max(1, round(rgba.shape[0] * k))
    ch = [np.array(Image.fromarray(pre[..., i]).resize((w, h), Image.BOX)) for i in range(4)]
    al = ch[3] / 255
    rgb = np.dstack([c / np.maximum(al, 1e-3) for c in ch[:3]])
    keep = al > 0.5
    out = np.dstack([np.clip(rgb, 0, 255), np.where(keep, 255, 0)]).astype(np.uint8)
    # outermost pixels that came out pale (blended from paper) get the outline colour
    edge = keep & ~_erode(keep)
    pale = out[..., :3].astype(int).mean(-1) > 165
    out[edge & pale, :3] = (24, 30, 26)
    return out


def single(rgba):
    """Keep what tools/pocket_sheets.py will read as one frame: the biggest part
    plus small bits next to it, so the clean sheet extracts exactly as drawn."""
    on = rgba[..., 3] > 0
    parts = _parts(on)
    keep = parts[0][2].copy()
    br = parts[0][1]
    for n, rect, part in parts[1:]:
        small = n < 300 or rect.h < 16
        cx, cy = rect.centerx, rect.centery
        near = max(br.x - cx, 0, cx - br.right) <= 4 and max(br.y - cy, 0, cy - br.bottom) <= 4
        if small and near:
            keep |= part
    out = rgba.copy()
    out[..., 3] = np.where(keep, 255, 0)
    ys, xs = np.where(keep)
    return out[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def fireball_frames(rgb):
    """The green ball (facing right) and three flickers of it."""
    ball = shrink(cut_out(rgb, FIREBALL), K * FB_K)
    frames = [ball]
    h, w = ball.shape[:2]
    stretched = np.array(Image.fromarray(ball, "RGBA").resize((w + 3, h), Image.NEAREST))
    frames.append(stretched)
    hot = ball.copy()
    m = hot[..., 3] > 0
    hot[m, :3] = np.clip(hot[m, :3].astype(int) * [1.0, 1.15, 1.0] + [40, 30, 40], 0, 255).astype(np.uint8)
    frames.append(hot)
    squat = np.array(Image.fromarray(ball, "RGBA").resize((w + 1, max(16, h - 1)), Image.NEAREST))
    frames.append(squat)
    return [single(f) for f in frames]


def make_portrait(rgb):
    x0, y0, x1, y1 = FACE_BOX
    face = Image.fromarray(rgb[y0:y1, x0:x1].astype(np.uint8)).resize(
        (PORTRAIT_SIZE, PORTRAIT_SIZE), Image.LANCZOS)
    a = np.array(face.convert("RGBA"))
    # the box's black backdrop becomes the HUD's plum like everyone else's
    dark = a[..., :3].astype(int).max(-1) < 22
    a[dark, :3] = (40, 24, 52)
    os.makedirs(OUT, exist_ok=True)
    Image.fromarray(a, "RGBA").save(os.path.join(OUT, "portrait.png"))


def build(src=SRC):
    rgb = np.array(Image.open(src).convert("RGB"))
    strips = []
    for name, boxes in STRIPS:
        strips.append([single(shrink(cut_out(rgb, b), K)) for b in boxes])
    strips.append(fireball_frames(rgb))
    W = max(sum(f.shape[1] + GAP for f in s) for s in strips) + GAP
    H = PITCH * len(strips)
    sheet = np.zeros((H, W, 3), np.uint8)
    sheet[:] = BG
    for r, frames in enumerate(strips):
        x = GAP
        mid = r * PITCH + PITCH // 2
        for f in frames:
            h, w = f.shape[:2]
            y = mid - h // 2
            on = f[..., 3] > 0
            region = sheet[y:y + h, x:x + w]
            region[on] = f[on][:, :3]
            x += w + GAP
    # the backdrop colour must stay unique to the backdrop
    on_bg = (sheet == BG).all(-1)
    assert on_bg.sum() > sheet.shape[0] * sheet.shape[1] // 2
    os.makedirs(os.path.dirname(CLEAN), exist_ok=True)
    Image.fromarray(sheet).save(CLEAN)
    make_portrait(rgb)
    print("DrDoom.png: %d strips -> %s" % (len(strips), CLEAN))


if __name__ == "__main__":
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    build(sys.argv[1] if len(sys.argv) > 1 else SRC)
    import extract_pocket
    from specs.drdoom import SPEC
    extract_pocket.extract("drdoom", SPEC)
