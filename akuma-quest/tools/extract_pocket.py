"""Dev tool: cut every character's animations out of Toshi's sprite sheets.

Frame numbers are "row.index" as tools/pocket_sheets.py prints them on its
contact sheets. Each character lists, for every engine pose, the frames to
play, the frames each image shows (used when the pose is not timed by a move
phase) and whether it loops. Output per character, in akuma/assets/chars/<id>/:
one PNG per sheet frame, anchors.txt (feet point) and poses.txt.

    python tools/extract_pocket.py            (needs pillow + numpy + pygame)
    python tools/extract_pocket.py akuma ryu  just those
"""

import os
import sys

import numpy as np
import pygame
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pocket_sheets as ps  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "akuma", "assets", "chars")


from specs import R, F  # noqa: E402

# pose: (frames, ticks per image, loop). Move poses are stretched to fill their
# move phase, so their tick count only matters outside moves.
AKUMA = dict(
    sheet="Akuma.png",
    projectile=R(56, 0, 7), air_projectile=R(60, 0, 6), projectile_scale=0.75,
    poses={
        "idle": (R(0, 0, 9), 6, True),
        "walk": (R(1, 0, 7), 5, True),
        "walk_back": (R(2, 0, 7), 5, True),
        "dash": (R(3, 0, 6), 3, True),
        "crouch": (R(9, 0, 1) + R(10, 0, 3), 6, "loop2"),
        "crouch_block": (R(5, 10, 11), 3, False),
        "block": (R(5, 7, 9), 3, False),
        "getup": (R(85, 0, 1) + R(12, 0, 1), 6, False),
        "prejump": (F("6.0"), 1, False),
        "jump_up": (R(6, 1, 3), 5, False),
        "jump": (R(6, 3, 6), 6, False),
        "fall": (R(6, 5, 6), 6, False),
        "land": (F("6.7", "6.0"), 4, False),
        "hado_prep": (R(53, 0, 3), 3, False),
        "hado_fire": (R(53, 4, 10), 3, False),
        "air_hado_prep": (R(16, 0, 1), 3, False),
        "air_hado": (R(53, 5, 7), 3, False),
        "punch_prep": (R(14, 0, 1), 2, False),
        "punch": (R(14, 2, 3), 3, False),
        "punch_rec": (R(14, 3, 3) + F("14.1", "14.0"), 3, False),
        "cr_punch_prep": (R(17, 0, 1), 2, False),
        "crouch_jab": (R(17, 2, 3), 3, False),
        "cr_punch_rec": (F("17.1", "17.0"), 3, False),
        "jpunch_prep": (F("16.0"), 1, False),
        "jump_jab": (R(16, 1, 2), 3, False),
        "jkick_prep": (R(23, 1, 2), 2, False),
        "jump_kick": (R(23, 3, 4), 3, False),
        "front_kick_prep": (R(19, 0, 2), 2, False),
        "front_kick": (R(19, 3, 4), 3, False),
        "front_kick_rec": (R(19, 5, 6), 3, False),
        "kick_prep": (R(20, 0, 5), 2, False),
        "kick": (R(20, 6, 7), 3, False),
        "kick_rec": (F("20.8", "19.6"), 3, False),
        "crkick_prep": (R(21, 0, 1), 2, False),
        "crkick": (R(21, 2, 3), 3, False),
        "crkick_rec": (F("21.4"), 3, False),
        "sweep_prep": (R(22, 0, 2), 2, False),
        "sweep": (R(22, 3, 5), 3, False),
        "sweep_rec": (R(22, 6, 9), 3, False),
        "sho_crouch": (R(65, 0, 2), 2, False),
        "sho_rise": (R(65, 3, 4), 3, False),
        "sho_top": (R(65, 5, 6), 3, False),
        "sho_fall": (R(65, 7, 8), 4, False),
        "tatsu_start": (R(61, 0, 2), 2, False),
        "tatsu": (R(61, 3, 10), 3, True),
        "tatsu_end": (F("61.11", "62.0", "62.1"), 3, False),
        "dive": (R(13, 2, 3), 4, True),
        "hurt": (R(82, 0, 3), 3, False),
        "hurt_low": (R(87, 1, 2), 3, False),
        "launch": (R(83, 1, 3), 4, False),
        "bounce": (R(83, 4, 5), 4, False),
        "down": (F("83.6") + R(84, 0, 2), 5, False),
        "victory": (R(89, 0, 12), 6, False),
        "intro": (R(86, 0, 7), 6, True),
        "taunt": (R(73, 2, 8), 6, False),
        "grab": (R(24, 0, 2), 2, False),
        "grab_miss": (R(24, 2, 0), 3, False),
        "toss": (R(24, 3, 7), 3, False),
        # poses only enemies use
        "leap_kick": (R(23, 3, 4), 3, False),
        "hammer_up": (R(15, 0, 3), 3, False),
        "hammer_down": (R(15, 4, 6), 3, False),
        "lariat_a": (R(61, 3, 6), 2, True),
        "lariat_b": (R(61, 7, 10), 2, True),
    },
)

CHARS = {"akuma": AKUMA}

# head-and-shoulders HUD portraits from the character select art (a 4 x 3 grid)
PORTRAITS = os.path.join(ROOT, "art_source", "portraits.png")
PORTRAIT_CELL = {"akuma": (0, 0), "ryu": (1, 0), "ken": (2, 0), "chunli": (0, 1), "sakura": (1, 1),
                 "morrigan": (2, 1), "hsienko": (3, 1), "felicia": (0, 2), "zangief": (2, 2)}
PORTRAIT_SIZE = 30
try:
    from pocket_specs import ENEMIES   # the other characters, kept in their own file
    CHARS.update(ENEMIES)
except ImportError:
    pass


def anchor(rgba):
    """Feet point: x at the middle of head and chest (steady while limbs swing), y = feet."""
    a = rgba[..., 3] > 0
    ys, xs = np.where(a)
    top, bottom = ys.min(), ys.max() + 1
    h = bottom - top
    band = (ys >= top + h * 0.12) & (ys <= top + h * 0.55)
    ax = int(round(np.median(xs[band])))
    return ax, bottom


def cut(rgb, box, keep, flip=False):
    x0, y0, x1, y1 = box
    a = np.where(keep, 255, 0).astype(np.uint8)
    rgba = np.dstack([rgb[y0:y1, x0:x1].astype(np.uint8), a])
    # a sheet drawn facing left (spec flip=True) is mirrored to face right
    return rgba[:, ::-1].copy() if flip else rgba


def scale(rgba, k):
    if k == 1:
        return rgba
    im = Image.fromarray(rgba, "RGBA")
    w, h = max(1, round(im.width * k)), max(1, round(im.height * k))
    return np.array(im.resize((w, h), Image.NEAREST))


_portrait_blobs = None


def portrait(cid, out):
    global _portrait_blobs
    if _portrait_blobs is None:
        _portrait_blobs = ps.frames(PORTRAITS, max_h=9999)
    rgb, blobs = _portrait_blobs
    h, w = rgb.shape[:2]
    cx, cy = PORTRAIT_CELL[cid]
    best = None
    for _, _, (x0, y0, x1, y1), keep in blobs:
        mx, my = (x0 + x1) / 2 * 4 / w, (y0 + y1) / 2 * 3 / (h - 100)
        if int(mx) == cx and int(my) == cy and (best is None or keep.sum() > best[1].sum()):
            best = ((x0, y0, x1, y1), keep)
    rgba = cut(rgb, *best)
    # the face: the top part of the art, as a square
    side = min(rgba.shape[1], int(rgba.shape[0] * 0.62))
    ys, xs = np.where(rgba[: side, :, 3] > 0)
    mid = int(np.median(xs))
    x0 = max(0, min(rgba.shape[1] - side, mid - side // 2))
    face = Image.fromarray(rgba[:side, x0:x0 + side], "RGBA").resize((PORTRAIT_SIZE, PORTRAIT_SIZE), Image.LANCZOS)
    a = np.array(face)
    a[..., 3] = np.where(a[..., 3] > 110, 255, 0)
    bg = np.zeros_like(a)
    bg[..., :3] = (40, 24, 52)
    bg[..., 3] = 255
    m = a[..., 3:] > 0
    Image.fromarray(np.where(m, a, bg).astype(np.uint8), "RGBA").save(os.path.join(out, "portrait.png"))


def extract(cid, spec):
    rgb, frames = ps.frames(spec["sheet"])
    byref = {"%d.%d" % (r, i): (box, keep) for r, i, box, keep in frames}
    out = os.path.join(OUT, cid)
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.endswith((".png", ".txt")) and f != "portrait.png":
            os.remove(os.path.join(out, f))
    k = spec.get("scale", 1.0)
    used = {}
    lines = []
    for pose, (refs, dur, loop) in spec["poses"].items():
        names = []
        for ref in refs:
            if ref not in byref:
                raise SystemExit("%s: %s frame %s is not on the sheet" % (cid, pose, ref))
            name = "f" + ref.replace(".", "_")
            if name not in used:
                used[name] = scale(cut(rgb, *byref[ref], flip=spec.get("flip", False)), k)
            names.append(name)
        lines.append("%s %d %s %s" % (pose, dur, loop if isinstance(loop, str) else int(loop), " ".join(names)))
    anchors = []
    for name, rgba in used.items():
        Image.fromarray(rgba, "RGBA").save(os.path.join(out, name + ".png"))
        anchors.append("%s %d %d" % ((name,) + anchor(rgba)))
    for key in ("projectile", "air_projectile"):
        refs = spec.get(key)
        if not refs:
            continue
        pk = spec.get("projectile_scale", 1.0) * k
        for i, ref in enumerate(refs):
            im = scale(cut(rgb, *byref[ref], flip=spec.get("flip", False)), pk)
            Image.fromarray(im, "RGBA").save(os.path.join(out, "%s_%d.png" % (key, i)))
        lines.append("#%s %d" % (key, len(refs)))
    if cid in PORTRAIT_CELL:
        portrait(cid, out)
    with open(os.path.join(out, "poses.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(out, "anchors.txt"), "w") as f:
        f.write("\n".join(anchors) + "\n")
    print("%s: %d poses, %d images" % (cid, len(spec["poses"]), len(used)))


if __name__ == "__main__":
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    for cid in sys.argv[1:] or CHARS:
        extract(cid, CHARS[cid])
