"""Dev tool: every pose of a character as an anchored strip, for checking the
frame picks and that the feet stay put.  python tools/preview_chars.py akuma"""

import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def preview(cid, out=None, k=2):
    d = os.path.join(ROOT, "akuma", "assets", "chars", cid)
    anchors = {}
    for line in open(os.path.join(d, "anchors.txt")):
        n, x, y = line.split()
        anchors[n] = (int(x), int(y))
    poses = [line.split() for line in open(os.path.join(d, "poses.txt")) if not line.startswith("#")]
    cw, ch = 130, 110
    cols = max(len(p) - 3 for p in poses)
    img = Image.new("RGB", (90 + cols * cw, len(poses) * ch), (44, 44, 60))
    dr = ImageDraw.Draw(img)
    for r, p in enumerate(poses):
        dr.text((4, r * ch + 4), p[0], fill=(255, 255, 0))
        for c, n in enumerate(p[3:]):
            fr = Image.open(os.path.join(d, n + ".png"))
            ax, ay = anchors[n]
            ox, oy = 90 + c * cw + cw // 2, r * ch + ch - 8
            img.paste(fr, (ox - ax, oy - ay), fr)
            dr.line((ox - 3, oy, ox + 3, oy), fill=(0, 255, 0))
            dr.line((ox, oy - 3, ox, oy + 3), fill=(0, 255, 0))
            dr.text((90 + c * cw + 2, r * ch + 2), n[1:], fill=(150, 150, 170))
    img = img.resize((img.width * k // 2, img.height * k // 2))
    img.save(out or os.path.join(ROOT, "art_source", "contact", "poses_%s.png" % cid))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.endswith(".png")]
    outs = [a for a in sys.argv[1:] if a.endswith(".png")]
    for cid in args:
        preview(cid, *outs[:1])
