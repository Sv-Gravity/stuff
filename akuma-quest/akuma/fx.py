"""Akuma's fireball / impact / explosion effect frames.

Cut by tools/make_fx.py from art_source/akuma_fireballs_explosions_sheet.png
into assets/fx/<row>_<i>.png. Rows:
  start, charge, release, fly, fly_alt, hit_small, hit_large, hit_wall, fade,
  var_regular, var_large, var_dark, explode_small, explode_medium,
  explode_large
Projectile rows face RIGHT; use flipped() / fx_frames(..., flip=True) for left.

    from akuma import fx
    frames = fx.fx_frames("explode_medium", scale_height=40)
    surf = fx.frame_at("fly", t, fps=14, scale_height=16)
"""

import os

import pygame

from akuma.akuma_sprites import asset_dir

ROWS = ("start", "charge", "release", "fly", "fly_alt", "hit_small",
        "hit_large", "hit_wall", "fade", "var_regular", "var_large",
        "var_dark", "explode_small", "explode_medium", "explode_large")

_raw = {}
_cache = {}


def _convert(s):
    try:
        return s.convert_alpha()
    except pygame.error:          # no display mode set yet
        return s


def _raw_frames(name):
    if name not in _raw:
        d = os.path.join(asset_dir(), "fx")
        out, i = [], 0
        while True:
            p = os.path.join(d, "%s_%d.png" % (name, i))
            if not os.path.exists(p):
                break
            out.append(_convert(pygame.image.load(p)))
            i += 1
        if not out:
            raise KeyError("no fx frames for %r" % name)
        _raw[name] = out
    return _raw[name]


def row_height(name):
    """Tallest native frame of a row (frames keep their relative sizes)."""
    return max(s.get_height() for s in _raw_frames(name))


def fx_frames(name, scale_height=None, flip=False):
    """List of surfaces for a row, cached. scale_height scales the whole row
    so its tallest frame is that many pixels (relative sizes kept)."""
    key = (name, scale_height, flip)
    got = _cache.get(key)
    if got is None:
        raw = _raw_frames(name)
        if scale_height:
            k = float(scale_height) / row_height(name)
            got = [scale(s, k) for s in raw]
        else:
            got = list(raw)
        if flip:
            got = [flipped(s) for s in got]
        _cache[key] = got
    return got


def scale(surf, k):
    w = max(1, int(round(surf.get_width() * k)))
    h = max(1, int(round(surf.get_height() * k)))
    if (w, h) == surf.get_size():
        return surf
    if k < 1.0:
        return pygame.transform.smoothscale(surf, (w, h))
    return pygame.transform.scale(surf, (w, h))


def flipped(surf):
    return pygame.transform.flip(surf, True, False)


def frame_at(name, t, fps=12.0, scale_height=None, flip=False, loop=True):
    """The frame at time t seconds (loops, or holds the last frame)."""
    frames = fx_frames(name, scale_height, flip)
    i = int(t * fps)
    i = i % len(frames) if loop else min(i, len(frames) - 1)
    return frames[i]


def count(name):
    return len(_raw_frames(name))
