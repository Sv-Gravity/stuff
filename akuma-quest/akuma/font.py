"""A hand-made 5x7 bitmap font so text looks properly 8-bit (no TTF needed)."""

import pygame

_FONT_DATA = """
A .###. #...# #...# ##### #...# #...# #...#
B ####. #...# #...# ####. #...# #...# ####.
C .###. #...# #.... #.... #.... #...# .###.
D ####. #...# #...# #...# #...# #...# ####.
E ##### #.... #.... ####. #.... #.... #####
F ##### #.... #.... ####. #.... #.... #....
G .###. #...# #.... #.### #...# #...# .####
H #...# #...# #...# ##### #...# #...# #...#
I .###. ..#.. ..#.. ..#.. ..#.. ..#.. .###.
J ..### ...#. ...#. ...#. ...#. #..#. .##..
K #...# #..#. #.#.. ##... #.#.. #..#. #...#
L #.... #.... #.... #.... #.... #.... #####
M #...# ##.## #.#.# #.#.# #...# #...# #...#
N #...# #...# ##..# #.#.# #..## #...# #...#
O .###. #...# #...# #...# #...# #...# .###.
P ####. #...# #...# ####. #.... #.... #....
Q .###. #...# #...# #...# #.#.# #..#. .##.#
R ####. #...# #...# ####. #.#.. #..#. #...#
S .#### #.... #.... .###. ....# ....# ####.
T ##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..
U #...# #...# #...# #...# #...# #...# .###.
V #...# #...# #...# #...# #...# .#.#. ..#..
W #...# #...# #...# #.#.# #.#.# #.#.# .#.#.
X #...# #...# .#.#. ..#.. .#.#. #...# #...#
Y #...# #...# .#.#. ..#.. ..#.. ..#.. ..#..
Z ##### ....# ...#. ..#.. .#... #.... #####
0 .###. #...# #..## #.#.# ##..# #...# .###.
1 ..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.
2 .###. #...# ....# ...#. ..#.. .#... #####
3 ####. ....# ....# .###. ....# ....# ####.
4 ...#. ..##. .#.#. #..#. ##### ...#. ...#.
5 ##### #.... ####. ....# ....# #...# .###.
6 .###. #.... #.... ####. #...# #...# .###.
7 ##### ....# ...#. ..#.. .#... .#... .#...
8 .###. #...# #...# .###. #...# #...# .###.
9 .###. #...# #...# .#### ....# ....# .###.
. ..... ..... ..... ..... ..... ..... ..#..
, ..... ..... ..... ..... ..... ..#.. .#...
! ..#.. ..#.. ..#.. ..#.. ..#.. ..... ..#..
? .###. #...# ....# ...#. ..#.. ..... ..#..
: ..... ..#.. ..... ..... ..... ..#.. .....
- ..... ..... ..... .###. ..... ..... .....
+ ..... ..#.. ..#.. ##### ..#.. ..#.. .....
/ ....# ....# ...#. ..#.. .#... #.... #....
' ..#.. ..#.. ..... ..... ..... ..... .....
% ##..# ##..# ...#. ..#.. .#... #..## #..##
( ...#. ..#.. .#... .#... .#... ..#.. ...#.
) .#... ..#.. ...#. ...#. ...#. ..#.. .#...
> .#... ..#.. ...#. ....# ...#. ..#.. .#...
< ...#. ..#.. .#... #.... .#... ..#.. ...#.
= ..... ..... ##### ..... ##### ..... .....
* ..... #.#.# .###. ##### .###. #.#.# .....
& .##.. #..#. #.#.. .#... #.#.# #..#. .##.#
"""

GLYPHS = {" ": ["....."] * 7}
for _line in _FONT_DATA.strip().splitlines():
    _parts = _line.split()
    GLYPHS[_parts[0]] = _parts[1:]

CHAR_W = 6   # 5 pixels + 1 spacing
CHAR_H = 7

_cache = {}


def text_surface(text, color, scale=1):
    key = (text, color, scale)
    surf = _cache.get(key)
    if surf is not None:
        return surf
    if len(_cache) > 800:
        _cache.clear()
    up = text.upper()
    w = max(1, len(up) * CHAR_W - 1)
    surf = pygame.Surface((w, CHAR_H), pygame.SRCALPHA)
    for i, ch in enumerate(up):
        rows = GLYPHS.get(ch, GLYPHS["?"])
        ox = i * CHAR_W
        for ry, row in enumerate(rows):
            for rx, c in enumerate(row):
                if c == "#":
                    surf.fill(color, (ox + rx, ry, 1, 1))
    if scale > 1:
        surf = pygame.transform.scale(surf, (w * scale, CHAR_H * scale))
    _cache[key] = surf
    return surf


def text_width(text, scale=1):
    return (len(text) * CHAR_W - 1) * scale


def draw_text(dst, text, x, y, color=(255, 255, 255), scale=1,
              shadow=(0, 0, 0), align="left"):
    surf = text_surface(text, color, scale)
    x = int(x)
    if align == "center":
        x -= surf.get_width() // 2
    elif align == "right":
        x -= surf.get_width()
    if shadow is not None:
        dst.blit(text_surface(text, shadow, scale), (x + scale, int(y) + scale))
    dst.blit(surf, (x, int(y)))
    return surf.get_width()


def wrap(text, max_chars):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w) if cur else w
    if cur:
        lines.append(cur)
    return lines
