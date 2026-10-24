"""Fighter sprites, cut from Toshi's sprite pack (art_source/sprites/).

tools/extract_pocket.py cuts each character's sheet into assets/chars/<id>/:
one image per drawing, its feet point, and which drawings play for every
engine pose. CharArt loads one character; MapArt is the same walk and idle
at map size.
"""

import os
import sys

import pygame


def asset_dir():
    base = getattr(sys, "_MEIPASS", None)   # PyInstaller one-file bundle
    if base:
        return os.path.join(base, "akuma", "assets")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _load(path):
    return pygame.image.load(os.path.join(asset_dir(), path)).convert_alpha()


# a pose a character's sheet has no drawing for borrows a close one
FALLBACK = {
    "walk_back": "walk", "dash": "walk", "prejump": "crouch", "land": "crouch",
    "jump_up": "jump", "fall": "jump", "getup": "crouch", "crouch_block": "block",
    "block": "hurt", "hurt_low": "hurt", "bounce": "launch", "down": "launch",
    "intro": "idle", "victory": "idle", "taunt": "victory",
    "punch_rec": "punch_prep", "cr_punch_rec": "cr_punch_prep", "kick_rec": "kick_prep",
    "front_kick_rec": "front_kick_prep", "crkick_rec": "crkick_prep", "sweep_rec": "sweep_prep",
    "sho_fall": "fall", "tatsu_end": "fall", "air_hado_prep": "jpunch_prep", "air_hado": "jump_jab",
    "hado_prep": "punch_prep", "hado_fire": "punch", "grab": "punch", "grab_miss": "punch_prep",
    "toss": "hado_fire", "tomoe_pull": "grab", "tomoe_roll": "down", "tomoe_getup": "getup", "leap_kick": "jump_kick", "hammer_up": "punch_prep",
    "hammer_down": "punch", "lariat_a": "punch", "lariat_b": "punch",
    "jpunch_prep": "jump", "jump_jab": "punch", "jkick_prep": "jump", "jump_kick": "kick",
    "front_kick_prep": "kick_prep", "front_kick": "kick", "crkick_prep": "crouch",
    "crkick": "kick", "cr_punch_prep": "crouch", "crouch_jab": "punch",
    "sweep_prep": "crkick_prep", "sweep": "crkick", "sho_crouch": "crouch",
    "sho_rise": "punch", "sho_top": "sho_rise", "tatsu_start": "kick_prep", "tatsu": "kick",
    "dive": "jump_kick",
}
STRIKE_GROW = 3       # px of the standing body an attack must reach past to count as the hitting part
STRIKE_MIN_PART = 24  # px; smaller loose bits of that are hair or toes, not a fist
ALIASES = {"idle0": "idle", "idle1": "idle", "walk0": "walk", "walk1": "walk", "walk2": "walk",
           "walk3": "walk"}


class CharArt:
    """One character's fight animations (assets/chars/<cid>/, cut by
    tools/extract_pocket.py). Same interface the fight code always used:
    resolve() picks the image for a pose, frame()/anchor() draw it."""

    _shared = {}
    _proj = {}

    def __init__(self, cid="akuma", scale=1.0):
        if not os.path.exists(os.path.join(asset_dir(), "chars", cid, "poses.txt")):
            cid = "akuma"
        self.cid = cid
        self.scale = scale
        if cid not in CharArt._shared:
            CharArt._shared[cid] = self._read(cid)
        self.base, self.poses, self.extra = CharArt._shared[cid]
        self._cache = {}

    @staticmethod
    def _read(cid):
        d = os.path.join(asset_dir(), "chars", cid)
        base = {}
        with open(os.path.join(d, "anchors.txt")) as f:
            for line in f:
                n, x, y = line.split()
                base[n] = (pygame.image.load(os.path.join(d, n + ".png")).convert_alpha(), (int(x), int(y)))
        poses, extra = {}, {}
        with open(os.path.join(d, "poses.txt")) as f:
            for line in f:
                bits = line.split()
                if bits[0].startswith("#"):
                    extra[bits[0][1:]] = int(bits[1])
                    continue
                loop = bits[2]
                intro = int(loop[4:]) if loop.startswith("loop") else (0 if loop == "1" else None)
                poses[bits[0]] = (bits[3:], int(bits[1]), intro)
        return base, poses, extra

    def _anim(self, pose):
        pose = ALIASES.get(pose, pose)
        seen = 0
        while pose not in self.poses and seen < 8:
            pose = FALLBACK.get(pose, "idle")
            seen += 1
        return self.poses.get(pose) or self.poses["idle"]

    def has(self, pose):
        return ALIASES.get(pose, pose) in self.poses

    def resolve(self, pose, pose_t=0, clock=0, span=None):
        """The image to show for a pose that has run pose_t frames.

        span: frames the pose lasts (a move phase): one-shot animations are
        then spread evenly over it, so every attack plays all of its drawings."""
        if pose in self.base:
            return pose
        frames, dur, intro = self._anim(pose)
        n = len(frames)
        if intro is None:
            if span:
                i = min(n - 1, pose_t * n // max(1, span))
            else:
                i = min(n - 1, pose_t // dur)
        elif pose_t < intro * dur:
            i = pose_t // dur
        else:
            i = intro + ((pose_t - intro * dur) // dur) % (n - intro) if intro else (clock // dur) % n
        return frames[i]

    def entry(self, key, flip=False, flash=False):
        ck = (key, flip, flash)
        e = self._cache.get(ck)
        if e is None:
            if key not in self.base:
                key = self.resolve(key)
            if flash:
                img, anc = self.entry(key, flip)
                img = pygame.mask.from_surface(img).to_surface(
                    setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
                e = (img, anc)
            elif flip:
                img, anc = self.entry(key)
                e = (pygame.transform.flip(img, True, False), (img.get_width() - anc[0], anc[1]))
            else:
                e = _scaled(*self.base[key], self.scale)
            self._cache[ck] = e
        return e

    def frame(self, key, flip=False, flash=False):
        return self.entry(key, flip, flash)[0]

    def anchor(self, key, flip=False):
        return self.entry(key, flip)[1]

    # ---- hit detection: the drawn pixels themselves ------------------------
    def mask(self, key, flip=False):
        """Pixel mask of a drawing: where this character can be hit."""
        ck = ("mask", key, flip)
        m = self._cache.get(ck)
        if m is None:
            m = self._cache[ck] = pygame.mask.from_surface(self.frame(key, flip), 127)
        return m

    def strike_mask(self, key, flip=False, both_sides=False):
        """The part of an attack drawing that does the hitting: the pixels that
        stick out of the character's standing body (fist, foot, flame), found by
        removing the idle drawing, grown by STRIKE_GROW px, lined up at the feet.
        Only the side the attack faces counts unless both_sides (spins)."""
        ck = ("strike", key, flip, both_sides)
        m = self._cache.get(ck)
        if m is None:
            m = self.mask(key, flip).copy()
            idle = self.resolve("idle")
            ax, ay = self.anchor(key, flip)
            bx, by = self.anchor(idle, flip)
            m.erase(self._body_mask(idle, flip), (ax - bx, ay - by))
            if not both_sides:
                # only what is level with or ahead of the chest
                w, h = m.get_size()
                front = pygame.Mask((w, h))
                if flip:
                    front.draw(pygame.Mask((min(w, ax + 3), h), fill=True), (0, 0))
                else:
                    front.draw(pygame.Mask((max(1, w - ax + 3), h), fill=True), (max(0, ax - 3), 0))
                m = m.overlap_mask(front, (0, 0))
            # stray specks (a hair tip, a shifted toe) don't hit anything
            solid = pygame.Mask(m.get_size())
            for part in m.connected_components(STRIKE_MIN_PART):
                r = part.get_bounding_rects()[0].unionall(part.get_bounding_rects())
                if r.bottom >= ay - 2 and r.w < 14 and r.h < 12:
                    continue    # a foot shuffling on the floor
                solid.draw(part, (0, 0))
            m = solid
            self._cache[ck] = m
        return m

    def _body_mask(self, idle, flip):
        ck = ("body", flip)
        m = self._cache.get(ck)
        if m is None:
            src = self.mask(idle, flip)
            m = pygame.Mask(src.get_size())
            for dx in range(-STRIKE_GROW, STRIKE_GROW + 1):
                for dy in range(-STRIKE_GROW, STRIKE_GROW + 1):
                    if dx * dx + dy * dy <= STRIKE_GROW * STRIKE_GROW:
                        m.draw(src, (dx, dy))
            self._cache[ck] = m
        return m

    def projectile_frames(self, air=False):
        key = "air_projectile" if air and self.extra.get("air_projectile") else "projectile"
        frames = CharArt._proj.get((self.cid, key))
        if frames is None:
            frames = [_load("chars/%s/%s_%d.png" % (self.cid, key, i)) for i in range(self.extra.get(key, 0))]
            CharArt._proj[(self.cid, key)] = frames
        return frames


class AkumaArt(CharArt):
    def __init__(self, scale=1.0):
        super().__init__("akuma", scale)


def _scaled(img, anchor, k):
    if k == 1:
        return img, anchor
    out = pygame.transform.scale(img, (round(img.get_width() * k), round(img.get_height() * k)))
    return out, (round(anchor[0] * k), round(anchor[1] * k))


def hado_frames(cid="akuma", air=False):
    """A character's fireball, facing right."""
    return CharArt(cid).projectile_frames(air)


# --------------------------------------------------------------------------
# Map sprites: the sheet's idle and walk cycles at half size, so walking on
# the map uses the same hand-drawn stride as the fights.
# --------------------------------------------------------------------------
MAP_SCALE = 0.5
MAP_STRIDE = 6.0         # map pixels walked per walk-cycle image (no foot sliding)


def _half(img, anchor, k):
    w, h = img.get_size()
    out = pygame.transform.smoothscale(img, (max(1, round(w * k)), max(1, round(h * k))))
    # snap alpha back to on/off so the small sprite keeps hard pixel edges
    m = pygame.mask.from_surface(out, 110)
    clean = pygame.Surface(out.get_size(), pygame.SRCALPHA)
    for x in range(out.get_width()):
        for y in range(out.get_height()):
            if m.get_at((x, y)):
                c = out.get_at((x, y))
                clean.set_at((x, y), (c.r, c.g, c.b, 255))
    return clean, (round(anchor[0] * k), round(anchor[1] * k))


class MapArt:
    """Walk/idle cycle for the map, facing right or left."""

    def __init__(self, cid="akuma", scale=MAP_SCALE):
        art = CharArt(cid)
        walk, _, _ = art._anim("walk")
        idle, _, _ = art._anim("idle")
        self.walk = [self._both(art, n, scale) for n in walk]
        self.idle = [self._both(art, n, scale) for n in idle]
        self.size = self.idle[0][0][0].get_size()

    @staticmethod
    def _both(art, key, k):
        img, anc = _half(*art.entry(key), k)
        flip = pygame.transform.flip(img, True, False)
        return (img, anc), (flip, (img.get_width() - anc[0], anc[1]))

    def frame(self, facing, moving, walked, clock):
        """facing: 1 right / -1 left; walked: map pixels covered (drives the stride)."""
        side = 0 if facing > 0 else 1
        if moving:
            return self.walk[int(walked / MAP_STRIDE) % len(self.walk)][side]
        return self.idle[(clock // 8) % len(self.idle)][side]


PORTRAIT_H = 30


def portrait(cid="akuma"):
    return _load("chars/%s/portrait.png" % cid)
