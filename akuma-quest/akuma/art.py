"""Procedural 8-bit art: enemy fighters, overworld sprites, tiles, effects, stages.

Akuma himself comes from Toshi's sprite sheet (akuma_sprites.py); everything
else is drawn from code once and cached, so a frame of gameplay is only blits.
"""

import math
import random

import pygame

from .config import TILE, W, H, GROUND_Y

OUTLINE = (14, 10, 20)


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3])


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# --------------------------------------------------------------------------
# Fighter skeleton poses (facing right). Origin = feet on ground, -y is up.
# hip, neck, head, front knee/foot, back knee/foot, front elbow/hand,
# back elbow/hand.
# --------------------------------------------------------------------------
_BASE = dict(hip=(0, -22), neck=(2, -36), head=(3, -41),
             fk=(7, -11), ff=(9, 0), bk=(-6, -11), bf=(-9, 0),
             fe=(8, -29), fh=(13, -33), be=(4, -27), bh=(9, -30))


def _p(**kw):
    p = dict(_BASE)
    p.update(kw)
    return p


_CROUCH = _p(hip=(0, -12), neck=(4, -25), head=(5, -30),
             fk=(10, -11), ff=(9, 0), bk=(-3, -4), bf=(-10, 0),
             fe=(9, -20), fh=(13, -24), be=(6, -18), bh=(10, -21))

POSES = {
    "idle0": _p(),
    "idle1": _p(hip=(0, -21), neck=(2, -35), head=(3, -40),
                fe=(8, -28), fh=(13, -32), be=(4, -26), bh=(9, -29)),
    "walk0": _p(fk=(8, -11), ff=(12, 0), bk=(-5, -11), bf=(-10, 0)),
    "walk1": _p(hip=(0, -23), neck=(2, -37), head=(3, -42),
                fk=(4, -12), ff=(3, -1), bk=(-1, -12), bf=(-2, 0)),
    "walk2": _p(fk=(1, -11), ff=(-6, 0), bk=(3, -11), bf=(10, 0)),
    "walk3": _p(hip=(0, -23), neck=(2, -37), head=(3, -42),
                fk=(1, -12), ff=(0, 0), bk=(1, -12), bf=(3, -2)),
    "crouch": dict(_CROUCH),
    "jump": _p(hip=(0, -26), neck=(2, -40), head=(3, -45),
               fk=(9, -30), ff=(5, -19), bk=(-3, -29), bf=(-8, -19),
               fe=(9, -37), fh=(13, -40), be=(4, -34), bh=(8, -37)),
    "jump_up": _p(hip=(0, -24), neck=(2, -38), head=(3, -43),
                  fk=(5, -12), ff=(4, -1), bk=(-3, -12), bf=(-5, -2),
                  fe=(8, -42), fh=(10, -49), be=(2, -32), bh=(5, -36)),
    "block": _p(neck=(-1, -36), head=(-1, -41), hip=(-1, -22),
                fe=(7, -31), fh=(6, -39), be=(5, -28), bh=(8, -35),
                fk=(6, -11), ff=(8, 0), bk=(-7, -10), bf=(-11, 0)),
    "crouch_block": dict(_CROUCH, neck=(1, -25), head=(1, -30),
                         fe=(8, -21), fh=(7, -29), be=(6, -18), bh=(9, -25)),
    "hado_prep": _p(hip=(0, -20), neck=(-2, -34), head=(-3, -39),
                    ff=(13, 0), fk=(9, -11), bf=(-12, 0), bk=(-7, -10),
                    fe=(-1, -24), fh=(-6, -24), be=(-3, -23), bh=(-8, -22)),
    "hado_fire": _p(hip=(1, -20), neck=(5, -34), head=(6, -39),
                    ff=(13, 0), fk=(9, -11), bf=(-12, 0), bk=(-7, -10),
                    fe=(11, -30), fh=(19, -29), be=(10, -28), bh=(18, -27)),
    "sho_crouch": dict(_CROUCH, fe=(6, -14), fh=(10, -9)),
    "sho_rise": _p(hip=(0, -24), neck=(3, -38), head=(4, -43),
                   fe=(8, -46), fh=(9, -55), be=(-2, -32), bh=(-5, -27),
                   fk=(8, -19), ff=(4, -10), bk=(-2, -11), bf=(-3, 0)),
    "sho_top": _p(hip=(0, -24), neck=(1, -38), head=(1, -43),
                  fe=(4, -47), fh=(3, -56), be=(-4, -32), bh=(-7, -28),
                  fk=(6, -15), ff=(5, -4), bk=(-3, -11), bf=(-4, 0)),
    "fall": _p(hip=(0, -24), neck=(1, -38), head=(1, -43),
               fe=(9, -38), fh=(13, -44), be=(-5, -34), bh=(-10, -38),
               fk=(5, -12), ff=(6, -2), bk=(-4, -12), bf=(-7, -3)),
    "dive": _p(hip=(0, -24), neck=(-6, -36), head=(-8, -40),
               fk=(9, -14), ff=(16, -5), bk=(-2, -20), bf=(-1, -12),
               fe=(-3, -31), fh=(-8, -27), be=(-2, -33), bh=(-7, -38)),
    "sweep_prep": dict(_CROUCH, fk=(9, -8), ff=(15, -2), fe=(1, -14), fh=(-2, -4)),
    "sweep": dict(hip=(-2, -10), neck=(-5, -23), head=(-5, -28),
                  fk=(10, -6), ff=(26, -2), bk=(-6, -6), bf=(-10, 0),
                  fe=(-4, -14), fh=(-6, -2), be=(2, -16), bh=(4, -4)),
    "hurt": _p(hip=(-1, -22), neck=(-6, -35), head=(-8, -39),
               fe=(-1, -36), fh=(3, -41), be=(-9, -32), bh=(-13, -35),
               fk=(5, -11), ff=(8, 0), bk=(-7, -10), bf=(-11, 0)),
    "hurt_low": dict(_CROUCH, neck=(-2, -24), head=(-4, -28),
                     fe=(2, -26), fh=(5, -30), be=(-6, -22), bh=(-10, -25)),
    "launch": dict(hip=(0, -20), neck=(-11, -28), head=(-15, -30),
                   fk=(7, -26), ff=(14, -30), bk=(5, -22), bf=(13, -24),
                   fe=(-6, -34), fh=(-4, -40), be=(-12, -24), bh=(-16, -20)),
    "down": dict(hip=(2, -4), neck=(-12, -5), head=(-17, -5),
                 fk=(10, -6), ff=(18, -2), bk=(9, -3), bf=(18, -1),
                 fe=(-7, -3), fh=(-11, -1), be=(-8, -7), bh=(-4, -9)),
    "getup": dict(_CROUCH, neck=(2, -24), head=(2, -29)),
    "victory": _p(fe=(7, -43), fh=(8, -52), be=(-2, -27), bh=(2, -23),
                  neck=(1, -37), head=(2, -42)),
    "intro": _p(fe=(7, -30), fh=(-1, -29), be=(4, -28), bh=(-3, -31)),
    "punch_prep": _p(fe=(3, -29), fh=(5, -33), neck=(1, -36)),
    "punch": _p(neck=(5, -36), head=(6, -41), hip=(1, -22),
                fe=(12, -34), fh=(21, -34), be=(2, -28), bh=(5, -31),
                ff=(11, 0), fk=(9, -11)),
    "kick_prep": _p(fk=(10, -22), ff=(6, -13), bk=(-3, -11), bf=(-5, 0),
                    neck=(0, -36), head=(1, -41)),
    "kick": _p(fk=(10, -25), ff=(23, -29), bk=(-2, -11), bf=(-3, 0),
               neck=(-5, -35), head=(-7, -39), fe=(2, -30), fh=(6, -33),
               be=(-7, -31), bh=(-11, -28)),
    "dash": _p(hip=(2, -20), neck=(10, -32), head=(13, -36),
               fe=(16, -30), fh=(25, -30), be=(5, -26), bh=(0, -23),
               ff=(14, 0), fk=(10, -10), bf=(-12, 0), bk=(-6, -9)),
    "leap_kick": _p(hip=(0, -24), neck=(-4, -37), head=(-6, -41),
                    fk=(11, -22), ff=(22, -18), bk=(-2, -27), bf=(-7, -17),
                    fe=(2, -34), fh=(7, -37), be=(-7, -32), bh=(-12, -29)),
    "hammer_up": _p(fe=(3, -46), fh=(4, -54), be=(1, -46), bh=(3, -54),
                    neck=(0, -36), head=(1, -41)),
    "hammer_down": _p(hip=(1, -21), neck=(7, -33), head=(9, -37),
                      fe=(13, -30), fh=(19, -17), be=(12, -30), bh=(18, -18),
                      ff=(12, 0), fk=(9, -11)),
    "lariat_a": _p(fe=(12, -33), fh=(22, -33), be=(-9, -33), bh=(-19, -33)),
    "lariat_b": _p(fe=(-9, -33), fh=(-19, -33), be=(12, -33), bh=(22, -33),
                   fk=(-5, -11), ff=(-8, 0), bk=(6, -11), bf=(9, 0)),
    "crouch_jab": dict(_CROUCH, neck=(6, -25), head=(7, -30),
                       fe=(13, -21), fh=(22, -21), be=(5, -18), bh=(8, -21)),
    "front_kick_prep": _p(fk=(9, -18), ff=(7, -9), bk=(-4, -11), bf=(-6, 0)),
    "front_kick": _p(fk=(11, -17), ff=(23, -18), bk=(-4, -11), bf=(-6, 0),
                     neck=(-1, -36), head=(-2, -41), fe=(6, -31), fh=(10, -34),
                     be=(-4, -30), bh=(-7, -27)),
    "jump_jab": _p(hip=(0, -26), neck=(3, -40), head=(4, -45),
                   fk=(9, -30), ff=(5, -19), bk=(-3, -29), bf=(-8, -19),
                   fe=(10, -32), fh=(18, -24), be=(-1, -36), bh=(-4, -40)),
    "tatsu_a": _p(hip=(0, -24), neck=(1, -38), head=(1, -43),
                  fk=(11, -24), ff=(24, -24), bk=(-3, -15), bf=(0, -8),
                  fe=(5, -31), fh=(8, -35), be=(-4, -31), bh=(-1, -35)),
    "tatsu_b": _p(hip=(0, -24), neck=(-1, -38), head=(-1, -43),
                  bk=(-11, -24), bf=(-24, -24), fk=(3, -15), ff=(0, -8),
                  fe=(4, -31), fh=(1, -35), be=(-5, -31), bh=(-8, -35)),
}
POSE_NAMES = list(POSES)

# Chibi ("super-deformed") look: the pose skeletons above are squashed into a
# short, stocky body and topped with a huge head.
CHX, CHY = 1.0, 0.95

# sx, sy, limb width, shoulder w, hip w, head radius
BUILDS = {
    "normal": (1.0, 1.0, 7, 16, 13, 12),
    "slim": (0.95, 1.0, 6, 13, 11, 12),
    "big": (1.15, 1.08, 8, 19, 15, 13),
    "huge": (1.3, 1.2, 9, 22, 18, 14),
    "small": (0.9, 0.88, 6, 13, 11, 11),
}

CANVAS_W, CANVAS_H = 112, 100
ANCHOR_X, ANCHOR_Y = 56, 94


def _line(s, c, a, b, w):
    a = (round(a[0]), round(a[1]))
    b = (round(b[0]), round(b[1]))
    pygame.draw.line(s, c, a, b, w)
    r = max(1, w // 2)
    pygame.draw.circle(s, c, a, r)
    pygame.draw.circle(s, c, b, r)


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _outlined(layer):
    m = pygame.mask.from_surface(layer)
    sil = m.to_surface(setcolor=OUTLINE + (255,), unsetcolor=(0, 0, 0, 0))
    out = pygame.Surface(layer.get_size(), pygame.SRCALPHA)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        out.blit(sil, (dx, dy))
    out.blit(layer, (0, 0))
    return out


def _arc_pt(hx, hy, deg, r):
    a = math.radians(deg)
    return (round(hx + math.cos(a) * r), round(hy - math.sin(a) * r))


def _draw_head(s, look, c, hr):
    """Big chibi head facing right (+x), with anime eyes."""
    hx, hy = round(c[0]), round(c[1])
    skin, hair, style = look["skin"], look["hair"], look["hair_style"]
    if style == "afro":
        pygame.draw.circle(s, hair, (hx - 2, hy - 2), hr + 4)
    if style == "long":
        _line(s, hair, (hx - hr + 2, hy - 2), (hx - hr - 1, hy + hr + 4), 7)
    if style == "hood":
        pygame.draw.circle(s, look["top"], (hx, hy), hr + 1)
        pygame.draw.ellipse(s, skin, (hx - 1, hy - 4, hr + 1, 9))
    else:
        pygame.draw.circle(s, skin, (hx, hy), hr)
        if style not in ("bald",):
            pygame.draw.circle(s, hair, (hx, hy), hr + 1, draw_top_left=True,
                               draw_top_right=True, draw_bottom_left=True)
            pygame.draw.ellipse(s, skin, (hx - 2, hy - 3, hr + 2, hr + 2))
            for i in range(3):
                x0 = hx - 2 + i * 4
                pygame.draw.polygon(s, hair, [(x0, hy - 4), (x0 + 4, hy - 4), (x0 + 1, hy)])
    if style == "spiky":
        for a in (72, 100, 128, 156, 184, 210):
            b0 = _arc_pt(hx, hy, a - 16, hr - 2)
            b1 = _arc_pt(hx, hy, a + 16, hr - 2)
            tip = _arc_pt(hx, hy, a + 14, hr + 7 + (a % 3))
            pygame.draw.polygon(s, hair, [b0, tip, b1])
        pygame.draw.polygon(s, shade(hair, 1.35), [_arc_pt(hx, hy, 90, hr - 2),
                                                  _arc_pt(hx, hy, 104, hr + 6),
                                                  _arc_pt(hx, hy, 112, hr - 2)])
    elif style == "mohawk":
        for a in (60, 90, 120, 150):
            pygame.draw.polygon(s, hair, [_arc_pt(hx, hy, a - 10, hr - 1), _arc_pt(hx, hy, a + 6, hr + 5),
                                          _arc_pt(hx, hy, a + 10, hr - 1)])
    elif style == "topknot":
        pygame.draw.circle(s, hair, _arc_pt(hx, hy, 115, hr + 2), 4)
    elif style == "headband":
        band = look.get("band", (200, 30, 30))
        half = int(math.sqrt(max(0, hr * hr - 16)))
        _line(s, band, (hx - half, hy - 5), (hx + half, hy - 5), 3)
        _line(s, band, (hx - hr, hy - 4), (hx - hr - 7, hy - 1), 2)
        _line(s, band, (hx - hr, hy - 3), (hx - hr - 5, hy + 3), 2)
    if "beard" in look["extras"]:
        pygame.draw.polygon(s, hair, [(hx + 1, hy + 5), (hx + hr, hy + 3),
                                      (hx + hr - 2, hy + hr + 3), (hx + 2, hy + hr + 1)])
    # eyes: big front eye, narrow far eye, angry brows
    glow = look.get("glow_eye")
    white = (255, 225, 225) if glow else (250, 250, 250)
    pupil = look.get("eye", (30, 30, 50))
    ex = hx + hr - 6
    ey = hy - 2
    pygame.draw.rect(s, white, (ex, ey, 3, 5))
    pygame.draw.rect(s, pupil, (ex + 1, ey + 1, 2, 4))
    s.set_at((ex + 1, ey + 1), (255, 255, 255))
    pygame.draw.rect(s, white, (hx - 1, ey + 1, 2, 4))
    pygame.draw.rect(s, pupil, (hx, ey + 2, 1, 3))
    brow = OUTLINE if style in ("bald", "hood") else shade(hair, 0.6)
    pygame.draw.line(s, brow, (ex - 1, ey - 1), (ex + 3, ey - 3), 2)
    pygame.draw.line(s, brow, (hx - 2, ey - 2), (hx + 1, ey), 1)
    if "beard" not in look["extras"]:
        pygame.draw.line(s, (120, 40, 40), (hx + 4, hy + 5), (hx + 6, hy + 5))


def render_pose(look, pose_name):
    sx, sy, lw, sw, hw, hr = BUILDS[look["build"]]
    raw = POSES[pose_name]
    P = {k: (ANCHOR_X + v[0] * CHX * sx, ANCHOR_Y + v[1] * CHY * sy) for k, v in raw.items()}
    # chibi fists sit at chest height so they don't cover the face
    for k in ("fe", "fh", "be", "bh"):
        if P[k][1] > P["neck"][1] - 4:
            P[k] = (P[k][0], P[k][1] + 3)
    nx, ny = P["neck"]
    dx, dy = P["head"][0] - nx, P["head"][1] - ny
    d = math.hypot(dx, dy) or 1.0
    head_c = (nx + dx / d * (hr - 1), ny + dy / d * (hr - 1))
    skin = look["skin"]
    top = look["top"] or skin
    pants = look["pants"]
    sleeve = top if look.get("sleeves") else skin
    glove = look.get("glove") or skin
    shoe = look.get("shoe") or skin

    def leg(s, k, f, dark):
        k1 = 0.78 if dark else 1.0
        _line(s, shade(pants, k1), P["hip"], P[k], lw + 1)
        _line(s, shade(pants, k1), P[k], P[f], lw)
        fx, fy = P[f]
        pygame.draw.ellipse(s, shade(shoe, k1), (round(fx) - 3, round(fy) - 4, 10, 5))

    def arm(s, e, h, dark, shoulder):
        k1 = 0.78 if dark else 1.0
        _line(s, shade(sleeve, k1), shoulder, P[e], lw - 1)
        _line(s, shade(skin, k1), P[e], P[h], lw - 2)
        if "wrist" in look["extras"]:
            pygame.draw.circle(s, shade(look.get("wrist_c", (220, 220, 220)), k1),
                               (round(P[h][0]), round(P[h][1])), lw // 2 + 1)
        pygame.draw.circle(s, shade(glove, k1), (round(P[h][0]), round(P[h][1])), lw // 2 + 2)

    shoulder_f = _lerp(P["neck"], P["hip"], 0.2)
    shoulder_b = (shoulder_f[0] - 3, shoulder_f[1] + 1)

    back = pygame.Surface((CANVAS_W, CANVAS_H), pygame.SRCALPHA)
    leg(back, "bk", "bf", True)
    arm(back, "be", "bh", True, shoulder_b)

    body = pygame.Surface((CANVAS_W, CANVAS_H), pygame.SRCALPHA)
    _line(body, top, P["hip"], P["neck"], hw)
    _line(body, top, _lerp(P["hip"], P["neck"], 0.5), P["neck"], sw)
    if look["top"] and look.get("open_chest"):
        a = _lerp(P["hip"], P["neck"], 0.45)
        n = P["neck"]
        pygame.draw.polygon(body, skin, [(round(n[0] - 1), round(n[1])), (round(n[0] + 5), round(n[1])),
                                         (round(a[0] + 2), round(a[1]))])
    belt = look.get("belt")
    if belt:
        _line(body, belt, _lerp(P["hip"], P["neck"], 0.02), _lerp(P["hip"], P["neck"], 0.16), hw + 1)
        bx, by = _lerp(P["hip"], P["neck"], 0.1)
        _line(body, belt, (bx - 3, by), (bx - 6, by + 6), 2)
    if "beads" in look["extras"]:
        n = P["neck"]
        for i in range(6):
            t = i / 5
            bx = n[0] - 5 + 11 * t
            by = n[1] + 2 + math.sin(t * math.pi) * 5
            pygame.draw.circle(body, (70, 44, 30), (round(bx), round(by)), 2)
            body.set_at((round(bx), round(by) - 1), (170, 120, 80))

    head = pygame.Surface((CANVAS_W, CANVAS_H), pygame.SRCALPHA)
    _draw_head(head, look, head_c, hr)

    front = pygame.Surface((CANVAS_W, CANVAS_H), pygame.SRCALPHA)
    leg(front, "fk", "ff", False)
    arm(front, "fe", "fh", False, shoulder_f)

    out = _outlined(back)
    out.blit(_outlined(body), (0, 0))
    if P["fh"][1] < head_c[1]:      # fist raised overhead: arm in front of head
        out.blit(_outlined(head), (0, 0))
        out.blit(_outlined(front), (0, 0))
    else:
        out.blit(_outlined(front), (0, 0))
        out.blit(_outlined(head), (0, 0))
    return out


class FighterArt:
    """Lazily-rendered, cached frames for one look."""

    def __init__(self, look):
        self.look = look
        self._cache = {}

    def frame(self, pose, flip=False, flash=False):
        key = (pose, flip, flash)
        surf = self._cache.get(key)
        if surf is None:
            if flash:
                base = self.frame(pose, flip)
                surf = pygame.mask.from_surface(base).to_surface(
                    setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
            elif flip:
                surf = pygame.transform.flip(self.frame(pose), True, False)
            else:
                surf = render_pose(self.look, pose)
            self._cache[key] = surf
        return surf

    def anchor(self, pose, flip=False):
        return (CANVAS_W - ANCHOR_X if flip else ANCHOR_X), ANCHOR_Y

    def warm(self):
        for p in POSE_NAMES:
            self.frame(p, False)
            self.frame(p, True)


# --------------------------------------------------------------------------
# Looks
# --------------------------------------------------------------------------
AKUMA_LOOK = dict(skin=(176, 112, 80), hair=(196, 36, 36), hair_style="spiky",
                  top=(62, 56, 70), pants=(62, 56, 70), belt=(150, 120, 70),
                  sleeves=False, open_chest=True, build="normal",
                  extras={"beads"}, eye=(255, 40, 40), glow_eye=True)

SKINS = [(232, 182, 140), (210, 150, 110), (176, 112, 80), (130, 84, 56),
         (96, 62, 44), (240, 200, 160)]
HAIRS = [(30, 24, 20), (90, 54, 30), (220, 190, 80), (180, 60, 30),
         (200, 200, 210), (40, 40, 60), (120, 40, 140)]
CLOTH = [(40, 80, 170), (170, 40, 40), (40, 130, 70), (200, 150, 40),
         (120, 60, 160), (60, 60, 60), (200, 200, 200), (30, 140, 150),
         (150, 90, 50), (220, 100, 40), (90, 100, 40)]


def random_look(rng, build=None):
    style = rng.choice(["short", "bald", "mohawk", "long", "headband", "topknot",
                        "afro", "hood", "short"])
    top = rng.choice(CLOTH + [None, None])
    look = dict(skin=rng.choice(SKINS), hair=rng.choice(HAIRS), hair_style=style,
                top=top if style != "hood" else rng.choice(CLOTH),
                pants=rng.choice(CLOTH), belt=rng.choice([None, (30, 30, 30), (230, 230, 230),
                                                          (150, 30, 30), (200, 160, 40)]),
                sleeves=rng.random() < 0.5, open_chest=False,
                build=build or rng.choice(["normal", "slim", "big", "huge", "small", "normal"]),
                extras=set(), band=rng.choice(CLOTH))
    if rng.random() < 0.3:
        look["extras"].add("beard")
    if rng.random() < 0.3:
        look["extras"].add("wrist")
        look["wrist_c"] = rng.choice(CLOTH)
    if rng.random() < 0.3:
        look["glove"] = rng.choice(CLOTH)
    if rng.random() < 0.5:
        look["shoe"] = rng.choice([(40, 30, 30), (200, 200, 200), (120, 70, 40)])
    if look["top"] is None:
        look["sleeves"] = False
    return look


BOSS_LOOK = dict(skin=(120, 150, 170), hair=(110, 50, 130), hair_style="topknot",
                 top=(110, 20, 30), pants=(40, 20, 30), belt=(220, 180, 50),
                 sleeves=False, open_chest=True, build="huge",
                 extras={"beard", "wrist"}, wrist_c=(220, 180, 50),
                 glove=(70, 70, 80), shoe=(50, 40, 40),
                 eye=(255, 220, 60), glow_eye=True)


BOSS2_LOOK = dict(skin=(200, 70, 60), hair=(245, 245, 235), hair_style="mohawk",
                  top=(30, 30, 40), pants=(60, 50, 90), belt=(230, 200, 60),
                  sleeves=False, open_chest=True, build="huge",
                  extras={"beads", "wrist"}, wrist_c=(230, 200, 60),
                  glove=(40, 40, 50), shoe=(40, 30, 30),
                  eye=(120, 255, 120), glow_eye=True)


# --------------------------------------------------------------------------
# Overworld (top-down) chibi sprites, 16x20
# --------------------------------------------------------------------------
OW_W, OW_H = 16, 20


def _ow_frame(look, direction, step):
    """16x20 chibi map sprite: big head, tiny body."""
    s = pygame.Surface((OW_W, OW_H), pygame.SRCALPHA)
    skin, hair = look["skin"], look["hair"]
    top = look["top"] or skin
    pants = look["pants"]
    style = look["hair_style"]
    shoe = look.get("shoe") or skin
    bob = 1 if step else 0
    # legs + feet
    if direction in ("down", "up"):
        l1, l2 = (15, 16) if step else (16, 16)
        pygame.draw.rect(s, pants, (5, l1, 2, 3))
        pygame.draw.rect(s, pants, (9, l2 - (1 if step else 0) + 1, 2, 2))
        pygame.draw.rect(s, shoe, (4, 18 - (1 if step else 0), 4, 2))
        pygame.draw.rect(s, shoe, (8, 18, 4, 2))
    else:
        f = 1 if direction == "right" else -1
        a = 2 if step else 0
        pygame.draw.rect(s, shade(pants, 0.8), (7 - a * f // 2, 15, 2, 3))
        pygame.draw.rect(s, pants, (7 + a * f // 2, 15, 2, 3))
        pygame.draw.rect(s, shade(shoe, 0.8), (6 - a * f // 2 + (1 if f > 0 else -1), 18, 4, 2))
        pygame.draw.rect(s, shoe, (6 + a * f // 2 + (1 if f > 0 else -1), 18, 4, 2))
    # body
    by = 10 - bob
    pygame.draw.rect(s, top, (4, by, 8, 6))
    if look.get("belt"):
        pygame.draw.rect(s, look["belt"], (4, by + 4, 8, 1))
    arm_c = top if look.get("sleeves") else skin
    if direction in ("down", "up"):
        pygame.draw.rect(s, arm_c, (2, by + 1 + (1 if step else 0), 2, 3))
        pygame.draw.rect(s, arm_c, (12, by + 1 + (0 if step else 1), 2, 3))
        pygame.draw.rect(s, skin, (2, by + 4 + (1 if step else 0), 2, 1))
        pygame.draw.rect(s, skin, (12, by + 4 + (0 if step else 1), 2, 1))
    else:
        pygame.draw.rect(s, arm_c, (7 + (1 if step else -1), by + 1, 3, 3))
        pygame.draw.rect(s, skin, (7 + (1 if step else -1), by + 4, 3, 1))
    if look.get("open_chest") and direction == "down":
        pygame.draw.rect(s, skin, (7, by, 2, 2))
    # big head
    hy = 0 - bob
    hc = top if style == "hood" else skin
    pygame.draw.ellipse(s, hc, (2, hy, 12, 11))
    if style == "afro":
        pygame.draw.ellipse(s, hair, (1, hy - 2, 14, 8))
    elif style not in ("bald", "hood"):
        if direction == "up":
            pygame.draw.ellipse(s, hair, (2, hy, 12, 10))
        else:
            pygame.draw.ellipse(s, hair, (2, hy, 12, 6))
            if direction == "right":
                pygame.draw.rect(s, hair, (2, hy + 2, 4, 6))
            elif direction == "left":
                pygame.draw.rect(s, hair, (10, hy + 2, 4, 6))
    if style == "spiky":
        for x in (2, 5, 8, 11):
            pygame.draw.polygon(s, hair, [(x, hy + 2), (x + 1, hy - 3), (x + 3, hy + 2)])
    elif style == "mohawk":
        pygame.draw.rect(s, hair, (7, hy - 2, 2, 4))
    elif style == "topknot":
        pygame.draw.circle(s, hair, (8, hy), 2)
    elif style == "headband":
        pygame.draw.rect(s, look.get("band", (200, 30, 30)), (2, hy + 4, 12, 1))
    elif style == "long" and direction != "down":
        pygame.draw.rect(s, hair, (3 if direction != "left" else 9, hy + 5, 4, 6))
    eye = look.get("eye", (20, 20, 30))
    if style == "hood" and direction != "up":
        pygame.draw.rect(s, skin, (4 if direction == "down" else (7 if direction == "right" else 3), hy + 5, 9 if direction == "down" else 6, 3))
    if direction == "down":
        for ex in (5, 9):
            pygame.draw.rect(s, (250, 250, 250), (ex, hy + 5, 2, 3))
            pygame.draw.rect(s, eye, (ex + (1 if ex == 5 else 0), hy + 6, 1, 2))
    elif direction in ("right", "left"):
        ex = 10 if direction == "right" else 4
        pygame.draw.rect(s, (250, 250, 250), (ex, hy + 5, 2, 3))
        pygame.draw.rect(s, eye, (ex + (1 if direction == "right" else 0), hy + 6, 1, 2))
    if "beard" in look["extras"] and direction != "up":
        pygame.draw.rect(s, hair, (5 if direction == "down" else (8 if direction == "right" else 3), hy + 9, 6 if direction == "down" else 5, 2))
    return _outlined(s)


class OverworldArt:
    def __init__(self, look):
        self.frames = {(d, st): _ow_frame(look, d, st)
                       for d in ("down", "up", "left", "right") for st in (0, 1)}

    def frame(self, direction, step):
        return self.frames[(direction, step)]


# --------------------------------------------------------------------------
# Tiles
# --------------------------------------------------------------------------
# floor, wall top, brick, mortar for each dungeon level
TILESETS = {
    1: ((66, 58, 72), (30, 24, 38), (92, 62, 58), (44, 30, 34)),
    2: ((104, 84, 66), (34, 12, 10), (150, 52, 34), (60, 20, 16)),
    3: ((56, 56, 64), (30, 30, 38), (96, 96, 104), (70, 70, 78)),   # retiled in cars.car_tiles
}


def make_tiles(seed=1, level=1):
    rng = random.Random(seed)
    FLOOR_C, WALL_TOP_C, brick, mortar = TILESETS[level]
    t = {}
    floors = []
    for v in range(4):
        s = pygame.Surface((TILE, TILE))
        s.fill(FLOOR_C)
        g = shade(FLOOR_C, 0.72)
        off = 8 if v % 2 else 0
        pygame.draw.line(s, g, (0, 7), (15, 7))
        pygame.draw.line(s, g, (0, 15), (15, 15))
        pygame.draw.line(s, g, (off + 3, 0), (off + 3, 7))
        pygame.draw.line(s, g, ((off + 11) % 16, 8), ((off + 11) % 16, 15))
        for _ in range(6):
            s.set_at((rng.randrange(16), rng.randrange(16)), shade(FLOOR_C, rng.choice([0.85, 1.15])))
        if v == 3:
            pygame.draw.lines(s, g, False, [(4, 2), (6, 5), (5, 9), (8, 12)])
        pygame.draw.line(s, shade(FLOOR_C, 1.12), (0, 0), (15, 0))
        floors.append(s)
    t["floor"] = floors
    top = pygame.Surface((TILE, TILE))
    top.fill(WALL_TOP_C)
    for _ in range(5):
        top.set_at((rng.randrange(16), rng.randrange(16)), shade(WALL_TOP_C, 1.3))
    t["wall_top"] = top
    face = pygame.Surface((TILE, TILE))
    face.fill(mortar)
    for row in range(4):
        y = row * 4
        offs = 0 if row % 2 == 0 else 4
        for bx in range(-8, 16, 8):
            r = pygame.Rect(bx + offs, y, 7, 3)
            c = shade(brick, rng.choice([0.85, 1.0, 1.1]))
            face.fill(c, r.clip(face.get_rect()))
    pygame.draw.line(face, shade(brick, 1.3), (0, 0), (15, 0))
    t["wall_face"] = face
    shadow = pygame.Surface((TILE, 4), pygame.SRCALPHA)
    shadow.fill((0, 0, 0, 90))
    t["shadow"] = shadow
    # torch flames (3 frames)
    flames = []
    for i in range(3):
        f = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.rect(f, (60, 40, 30), (7, 8, 2, 6))
        pygame.draw.rect(f, (110, 80, 50), (6, 7, 4, 2))
        h = (5, 6, 4)[i]
        pygame.draw.ellipse(f, (240, 120, 30), (5, 7 - h, 6, h + 1))
        pygame.draw.ellipse(f, (255, 230, 120), (6 + (i % 2), 8 - h + 2, 3, h - 1))
        flames.append(f)
    t["torch"] = flames
    # decorations
    bones = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    pygame.draw.line(bones, (200, 196, 180), (3, 11), (10, 8), 2)
    pygame.draw.circle(bones, (210, 206, 190), (11, 11), 3)
    bones.set_at((10, 11), (30, 30, 30))
    bones.set_at((12, 11), (30, 30, 30))
    t["bones"] = bones
    rubble = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    for x, y, r in ((4, 10, 3), (9, 12, 2), (11, 8, 2)):
        pygame.draw.circle(rubble, (90, 82, 96), (x, y), r)
        pygame.draw.circle(rubble, (120, 110, 126), (x - 1, y - 1), max(1, r - 2))
    t["rubble"] = rubble
    lantern = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    pygame.draw.rect(lantern, (70, 70, 80), (4, 3, 8, 12))
    pygame.draw.rect(lantern, (90, 90, 100), (3, 2, 10, 2))
    pygame.draw.rect(lantern, (255, 200, 90), (6, 6, 4, 4))
    pygame.draw.rect(lantern, (90, 90, 100), (5, 14, 6, 2))
    t["lantern"] = lantern
    # pickups
    oni = pygame.Surface((12, 12), pygame.SRCALPHA)
    pygame.draw.polygon(oni, (245, 245, 240), [(6, 1), (11, 10), (1, 10)])
    pygame.draw.rect(oni, (20, 40, 30), (3, 7, 6, 4))
    t["onigiri"] = _outlined(oni)
    orbs = []
    for i in range(4):
        o = pygame.Surface((12, 12), pygame.SRCALPHA)
        r = 4 + (1 if i in (1, 2) else 0)
        pygame.draw.circle(o, (160, 20, 40), (6, 6), r)
        pygame.draw.circle(o, (255, 90, 110), (5, 5), r - 2)
        pygame.draw.circle(o, (255, 220, 220), (4, 4), 1)
        orbs.append(o)
    t["orb"] = orbs
    # boss gate/throne marker
    throne = pygame.Surface((TILE * 2, TILE * 2), pygame.SRCALPHA)
    pygame.draw.rect(throne, (80, 20, 30), (4, 2, 24, 26))
    pygame.draw.rect(throne, (200, 160, 40), (4, 2, 24, 26), 2)
    pygame.draw.rect(throne, (120, 30, 40), (8, 12, 16, 16))
    t["throne"] = throne
    return t


# --------------------------------------------------------------------------
# Effects
# --------------------------------------------------------------------------
def make_fireball(colors, big=False):
    core, mid, outer = colors
    frames = []
    for i in range(4):
        w, h = (30, 22) if big else (24, 16)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = w - 9 if not big else w - 11, h // 2
        r = (6 if not big else 8) + (i % 2)
        for k in range(4):   # tail
            tx = cx - 5 - k * 4 - (i % 2) * 2
            tr = max(1, r - 2 - k)
            pygame.draw.circle(s, outer, (tx, cy + ((k + i) % 3) - 1), tr)
        pygame.draw.circle(s, outer, (cx, cy), r + 1)
        pygame.draw.circle(s, mid, (cx, cy), r - 1)
        pygame.draw.circle(s, core, (cx + 1, cy), max(1, r - 3))
        frames.append(s)
    return frames


def make_spark(color):
    frames = []
    for i in range(5):
        s = pygame.Surface((32, 32), pygame.SRCALPHA)
        r = 4 + i * 3
        n = 8
        for k in range(n):
            a = k / n * math.tau + i * 0.2
            r0 = r * 0.4
            p0 = (16 + math.cos(a) * r0, 16 + math.sin(a) * r0)
            p1 = (16 + math.cos(a) * r, 16 + math.sin(a) * r)
            pygame.draw.line(s, color if k % 2 else (255, 255, 255), p0, p1, 2 if i < 3 else 1)
        if i < 2:
            pygame.draw.circle(s, (255, 255, 255), (16, 16), 6 - i * 2)
        frames.append(s)
    return frames


def make_dust():
    frames = []
    for i in range(4):
        s = pygame.Surface((16, 10), pygame.SRCALPHA)
        a = 200 - i * 45
        pygame.draw.circle(s, (200, 190, 170, a), (5, 6), 3 + i // 2)
        pygame.draw.circle(s, (200, 190, 170, a), (10, 6), 2 + i // 2)
        frames.append(s)
    return frames


# --------------------------------------------------------------------------
# Fight stages
# --------------------------------------------------------------------------
STAGE_PALETTES = [
    # sky top, sky bottom, mountains, ground, ground line
    ((24, 10, 40), (140, 40, 60), (40, 20, 50), (70, 56, 60), (50, 40, 46)),
    ((10, 16, 40), (60, 70, 120), (24, 30, 56), (64, 66, 72), (44, 46, 54)),
    ((30, 20, 10), (170, 90, 40), (60, 36, 26), (86, 66, 50), (60, 44, 34)),
]


def make_stage(variant, boss=False, level=1):
    rng = random.Random(variant * 31 + (99 if boss else 0) + level * 7)
    s = pygame.Surface((W, H))
    if level == 6:      # the frozen compound: night snow
        top, bot, mtn, gnd, gl = (10, 16, 34), (90, 110, 150), (50, 60, 84), (190, 200, 216), (140, 150, 170)
    elif boss and level == 2:
        top, bot, mtn, gnd, gl = (8, 4, 20), (90, 30, 120), (30, 10, 40), (40, 30, 50), (24, 16, 30)
    elif boss:
        top, bot, mtn, gnd, gl = (20, 4, 6), (120, 24, 10), (36, 10, 12), (48, 30, 30), (30, 16, 18)
    else:
        top, bot, mtn, gnd, gl = STAGE_PALETTES[variant % len(STAGE_PALETTES)]
    for y in range(GROUND_Y):
        t = y / GROUND_Y
        # banded gradient for an 8-bit look
        t = round(t * 10) / 10
        pygame.draw.line(s, mix(top, bot, t), (0, y), (W, y))
    if not boss:
        pygame.draw.circle(s, (240, 230, 200), (250, 40), 16)
        pygame.draw.circle(s, mix(top, bot, 0.25), (256, 36), 13)
        for _ in range(30):
            s.set_at((rng.randrange(W), rng.randrange(80)), (220, 220, 240))
    # far mountains
    pts = [(0, GROUND_Y)]
    x = 0
    while x <= W:
        pts.append((x, rng.randint(70, 110)))
        x += rng.randint(20, 45)
    pts += [(W, GROUND_Y)]
    pygame.draw.polygon(s, mtn, pts)
    if boss:
        # stalactites and lava glow
        for _ in range(14):
            x = rng.randrange(W)
            h = rng.randint(10, 40)
            pygame.draw.polygon(s, (24, 8, 10), [(x - 6, 0), (x + 6, 0), (x, h)])
        for i in range(6):
            pygame.draw.line(s, mix((255, 120, 20), mtn, i / 6), (0, GROUND_Y - 1 - i), (W, GROUND_Y - 1 - i))
    else:
        # pagoda / torii silhouettes
        dark = shade(mtn, 0.6)
        tx = rng.choice([60, 90, 220])
        pygame.draw.rect(s, dark, (tx, 96, 4, GROUND_Y - 96))
        pygame.draw.rect(s, dark, (tx + 40, 96, 4, GROUND_Y - 96))
        pygame.draw.rect(s, dark, (tx - 8, 92, 60, 4))
        pygame.draw.rect(s, dark, (tx - 2, 102, 48, 3))
        px = (tx + 130) % 280
        for i in range(4):
            w = 40 - i * 8
            y = 130 - i * 12
            pygame.draw.polygon(s, dark, [(px - w // 2 - 4, y), (px + w // 2 + 4, y),
                                          (px + w // 2 - 2, y - 5), (px - w // 2 + 2, y - 5)])
            pygame.draw.rect(s, dark, (px - w // 2 + 4, y, w - 8, 12))
    # ground
    pygame.draw.rect(s, gnd, (0, GROUND_Y, W, H - GROUND_Y))
    for i in range(0, W + 40, 24):
        pygame.draw.line(s, gl, (i, GROUND_Y), (i - 30 + (i - W // 2) // 3, H))
    pygame.draw.line(s, gl, (0, GROUND_Y + 8), (W, GROUND_Y + 8))
    pygame.draw.line(s, shade(gnd, 1.25), (0, GROUND_Y), (W, GROUND_Y))
    if boss:
        for _ in range(8):
            x = rng.randrange(W)
            y = rng.randrange(GROUND_Y + 3, H - 2)
            pygame.draw.line(s, (255, 110, 30), (x, y), (x + rng.randint(6, 18), y + rng.randint(-2, 2)))
    return s
