"""Dev tool: the Doom level's Street Fighter III look.

Toshi picked Third Strike sprites for the possessed fighters in level 10 and
Mech Zangief (Marvel vs. Capcom) for Cyber-Gief. The animated gifs come from
fightersgeneration.com and live in art_source/fightersgeneration/. This cuts
them into the same frame folders the Pocket Fighter characters use
(akuma/assets/chars/<cid>/: f<pose>_<i>.png, anchors.txt, poses.txt and
projectile_<i>.png), so CharArt loads them like any other character.

Each gif frame is cropped to its drawing; its anchor is the feet. Poses whose
gif keeps the fighter in place share one anchor column (taken from the gif's
first frame) so the animation doesn't wobble; poses where the fighter travels
across the gif (Chun-Li's dash, Gief's charge) follow the body instead.
Moves the site has no gif for (Chun-Li getting hit and falling) are made by
tilting her stance.

    python tools/make_doom_fighters.py
"""

import os

import numpy as np
from PIL import Image, ImageSequence

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "art_source", "fightersgeneration")
OUT = os.path.join(ROOT, "akuma", "assets", "chars")

R = lambda a, b: list(range(a, b + 1))     # noqa: E731

# pose: (gif, frames, frames-per-drawing, loop, anchor, columns kept)
#   anchor "fixed": the gif's first-frame body column; "body": each frame's own
#   loop as poses.txt: 1 = loops, 0 = plays once
CHARS = {
    "ryu3s": dict(
        poses={
            "idle": ("ryu-ts-stance", R(0, 9), 6, 1, "fixed", None),
            "walk": ("ryu-walkf", R(0, 10), 4, 1, "fixed", None),
            "punch_prep": ("ryu-mp", R(0, 1), 3, 0, "fixed", None),
            "punch": ("ryu-mp", R(2, 4), 3, 0, "fixed", None),
            "punch_rec": ("ryu-mp", R(5, 7), 3, 0, "fixed", None),
            "kick_prep": ("ryu-hk", R(0, 5), 2, 0, "fixed", None),
            "kick": ("ryu-hk", R(6, 9), 3, 0, "fixed", None),
            "kick_rec": ("ryu-hk", R(10, 14), 3, 0, "fixed", None),
            "hado_prep": ("ryu-fireballs", R(0, 4), 3, 0, "fixed", None),
            "hado_fire": ("ryu-fireballs", R(5, 11), 3, 0, "fixed", None),
            "hurt": ("ryu-stand-hit", [1, 2, 3, 4, 5], 3, 0, "fixed", None),
            "launch": ("ryu-twist", R(0, 14), 3, 0, "fixed", None),
            "down": ("ryu-twist", R(15, 26), 4, 0, "fixed", None),
        },
        # the blue ball of his Shinku Hadouken gif
        projectile=("ryu-blackhadou", R(8, 16), (110, None), "blue"),
    ),
    "chunli3s": dict(
        poses={
            "idle": ("chunny-ts-stance", R(0, 9), 8, 1, "fixed", None),
            "walk": ("chunny-ts-dashforward", R(1, 8), 3, 1, "body", None),
            "punch_prep": ("chun-ts-a1", [0], 3, 0, "fixed", None),
            "punch": ("chun-ts-a1", R(1, 3), 3, 0, "fixed", None),
            "punch_rec": ("chun-ts-a1", [4], 3, 0, "fixed", None),
            "kick_prep": ("chuny-ts-kickz", R(0, 2), 2, 0, "fixed", None),
            "kick": ("chuny-ts-kickz", R(3, 12), 2, 0, "fixed", None),
            "kick_rec": ("chuny-ts-kickz", R(13, 15), 2, 0, "fixed", None),
            "hado_prep": ("chun-ts-hadouken", R(0, 5), 3, 0, "fixed", None),
            "hado_fire": ("chun-ts-hadouken", R(6, 9), 3, 0, "fixed", (0, 142)),
        },
        tilt={"hurt": [8, 14], "launch": [25, 45, 65], "down": [90]},
        projectile=("chun-ts-hadouken", R(20, 25), (158, None), None),
    ),
    "mechgief": dict(
        poses={
            "idle": ("zangief-mechstand", R(0, 9), 6, 1, "fixed", None),
            "walk": ("zangief-mech-walk", R(0, 9), 6, 1, "fixed", None),
            "hammer_up": ("mz-headbutt", R(0, 4), 3, 0, "fixed", None),
            "hammer_down": ("mz-headbutt", R(5, 13), 3, 0, "fixed", None),
            "hado_prep": ("zangief-mechstand", [0, 1], 4, 0, "fixed", None),
            "hado_fire": ("zangief-flame", R(0, 3), 4, 0, "fixed", (0, 122)),
            "dash": ("mz-dash", R(3, 21), 3, 1, "body", None),
            "launch": ("mz-throw", R(8, 12), 4, 0, "fixed", None),
            "down": ("mz-throw", R(13, 20), 4, 0, "fixed", None),
        },
        # his ice breath, cut off the flame gif
        projectile=("zangief-flame", R(0, 3), (128, None), None),
    ),
}


def gif_frames(name):
    im = Image.open(os.path.join(SRC, name + ".gif"))
    return [np.array(f.convert("RGBA")) for f in ImageSequence.Iterator(im)]


def body_x(a):
    """Alpha-weighted centre column of the lower half of a drawing (the legs:
    arms, kicks and effects don't drag it around)."""
    al = a[..., 3] > 0
    ys = np.nonzero(al.any(1))[0]
    if len(ys) == 0:
        return a.shape[1] // 2
    lo = al[(ys[0] + ys[-1]) // 2:]
    cols = lo.sum(0)
    return int(round((cols * np.arange(len(cols))).sum() / max(1, cols.sum())))


def feet_y(a):
    ys = np.nonzero((a[..., 3] > 0).any(1))[0]
    return int(ys[-1]) + 1 if len(ys) else a.shape[0]


def keep_cols(a, cols):
    if cols is None:
        return a
    a = a.copy()
    x0, x1 = cols
    a[:, :x0, 3] = 0
    if x1 is not None:
        a[:, x1:, 3] = 0
    return a


def crop(a, ax, ay):
    al = a[..., 3] > 0
    ys, xs = np.nonzero(al.any(1))[0], np.nonzero(al.any(0))[0]
    if len(ys) == 0:
        return Image.new("RGBA", (1, 1)), (0, 0)
    y0, y1, x0, x1 = ys[0], ys[-1] + 1, xs[0], xs[-1] + 1
    return Image.fromarray(a[y0:y1, x0:x1]), (ax - x0, ay - y0)


def build(cid, spec):
    d = os.path.join(OUT, cid)
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        os.remove(os.path.join(d, f))
    anchors, poses = [], []
    for row, (pose, (gif, idx, dur, loop, mode, cols)) in enumerate(spec["poses"].items()):
        frames = gif_frames(gif)
        first = keep_cols(frames[idx[0]], cols)
        fx, fy = body_x(first), feet_y(first)
        names = []
        for i, k in enumerate(idx):
            a = keep_cols(frames[k], cols)
            ax = fx if mode == "fixed" else body_x(a)
            ay = fy if mode == "fixed" else feet_y(a)
            img, anc = crop(a, ax, ay)
            n = "f%d_%d" % (row, i)
            img.save(os.path.join(d, n + ".png"))
            anchors.append("%s %d %d" % (n, anc[0], anc[1]))
            names.append(n)
        poses.append("%s %d %d %s" % (pose, dur, loop, " ".join(names)))
    if "tilt" in spec:
        # no gif for these: lean the stance back, then topple over
        base = Image.open(os.path.join(d, "f0_0.png"))
        row = len(spec["poses"])
        for pose, angles in spec["tilt"].items():
            names = []
            for i, ang in enumerate(angles):
                img = base.rotate(ang, resample=Image.BICUBIC, expand=True)
                a = np.array(img)
                ys = np.nonzero((a[..., 3] > 0).any(1))[0]
                xs = np.nonzero((a[..., 3] > 0).any(0))[0]
                img = img.crop((xs[0], ys[0], xs[-1] + 1, ys[-1] + 1))
                n = "f%d_%d" % (row, i)
                img.save(os.path.join(d, n + ".png"))
                anchors.append("%s %d %d" % (n, img.width // 2, img.height))
                names.append(n)
            poses.append("%s %d 0 %s" % (pose, 4, " ".join(names)))
            row += 1
    gif, idx, cols, colour = spec["projectile"]
    frames = gif_frames(gif)
    count = 0
    for k in idx:
        a = keep_cols(frames[k], cols)
        if colour == "blue":
            r, g, b = (a[..., c].astype(int) for c in range(3))
            blue = (b > r + 30) & (a[..., 3] > 0)
            ys, xs = np.nonzero(blue.any(1))[0], np.nonzero(blue.any(0))[0]
            inside = np.zeros_like(blue)
            inside[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1] = True
            # the ball: its blue flame plus the white-hot core inside it
            hot = (r + g + b > 600) & (b >= r - 8) & inside
            a[..., 3] = np.where(blue | hot, a[..., 3], 0)
        img, _ = crop(a, 0, 0)
        img.save(os.path.join(d, "projectile_%d.png" % count))
        count += 1
    poses.append("#projectile %d" % count)
    with open(os.path.join(d, "anchors.txt"), "w") as f:
        f.write("\n".join(anchors) + "\n")
    with open(os.path.join(d, "poses.txt"), "w") as f:
        f.write("\n".join(poses) + "\n")
    print("%s: %d drawings, %d poses, %d projectile frames" % (cid, len(anchors), len(poses) - 1, count))


if __name__ == "__main__":
    for cid, spec in CHARS.items():
        build(cid, spec)
