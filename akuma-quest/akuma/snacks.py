"""Japanese snacks: the health pickups found all over the game (Toshi likes
Japanese snacks). Each is pixel art drawn in code at 12x12, plus how much it
heals as a fraction of Akuma's max health.

    from .snacks import SNACKS, snack_image, random_snack
    name = random_snack(rng)            # e.g. "RAMEN"
    img = snack_image(name)             # 12x12 surface, cached
    heal = SNACKS[name]                 # fraction of max HP
"""

import pygame

# name: fraction of max HP it heals. Bigger meals heal more.
SNACKS = {
    "RAMEN": 0.35,
    "ONIGIRI": 0.20,
    "MOCHI": 0.15,
    "DANGO": 0.15,
    "TAIYAKI": 0.20,
    "TAKOYAKI": 0.25,
    "POCKY": 0.10,
    "MELON PAN": 0.20,
    "DORAYAKI": 0.20,
    "BENTO": 0.40,
}
# how often each turns up (big meals are rarer)
WEIGHTS = {"RAMEN": 2, "ONIGIRI": 4, "MOCHI": 4, "DANGO": 4, "TAIYAKI": 3, "TAKOYAKI": 3,
           "POCKY": 5, "MELON PAN": 3, "DORAYAKI": 3, "BENTO": 1}

OUTLINE = (24, 16, 20)
SIZE = 12
_cache = {}


def random_snack(rng):
    names = list(WEIGHTS)
    return rng.choices(names, weights=[WEIGHTS[n] for n in names])[0]


def heal_amount(name, max_hp):
    return max(1, round(SNACKS.get(name, 0.2) * max_hp))


def snack_image(name, scale=1):
    key = (name, scale)
    img = _cache.get(key)
    if img is None:
        img = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
        _DRAW.get(name, _onigiri)(img)
        _outline(img)
        if scale != 1:
            img = pygame.transform.scale(img, (SIZE * scale, SIZE * scale))
        _cache[key] = img
    return img


def _outline(img):
    """A dark 1px outline around the drawing so it reads on any floor."""
    m = pygame.mask.from_surface(img, 1)
    w, h = img.get_size()
    edge = []
    for y in range(h):
        for x in range(w):
            if m.get_at((x, y)):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and m.get_at((nx, ny)):
                    edge.append((x, y))
                    break
    for p in edge:
        img.set_at(p, OUTLINE)


def _px(img, rows, colors):
    """Draw from a little character map: one char per pixel, '.' is empty."""
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c != ".":
                img.set_at((x, y), colors[c])


def _ramen(img):
    _px(img, [
        "..y.y.......",
        ".y.y........",
        "..y.y.......",
        "............",
        "wwwwwwwwwwww",
        "wbbnnnnpbbgw",
        "wbnnenngnnbw",
        ".rrrrrrrrrr.",
        ".rwrrrrrwrr.",
        "..rrrrrrrr..",
        "...rrrrrr...",
        "....dddd....",
    ], dict(y=(240, 240, 240), w=(250, 246, 236), b=(206, 140, 70), n=(250, 222, 130),
            e=(250, 200, 60), p=(240, 150, 170), g=(90, 170, 80), r=(200, 40, 40), d=(140, 24, 24)))


def _onigiri(img):
    _px(img, [
        ".....ww.....",
        "....wwww....",
        "...wwwwww...",
        "...wwwwww...",
        "..wwwwwwww..",
        "..wwwwwwww..",
        ".wwwwwwwwww.",
        ".wwwnnnnwww.",
        "wwwnnnnnnwww",
        "wwwnnnnnnwww",
        "wwwnnnnnnwww",
        ".wwnnnnnnww.",
    ], dict(w=(248, 248, 244), n=(30, 60, 40)))


def _mochi(img):
    _px(img, [
        "............",
        "............",
        "...pppppp...",
        "..pppPPppp..",
        ".ppPPPPpppp.",
        ".pppppppppp.",
        ".pppppppppp.",
        ".gggggggggg.",
        "..ggGGGGgg..",
        "..ggggggggg.",
        "....LLLL....",
        "............",
    ], dict(p=(250, 200, 214), P=(255, 236, 242), g=(250, 250, 246), G=(255, 255, 255),
            L=(120, 170, 90)))


def _dango(img):
    _px(img, [
        "..........s.",
        ".........pp.",
        "........pppp",
        "........pppp",
        "......wwpp..",
        ".....wwww...",
        ".....wwww...",
        "...ggww.....",
        "..gggg......",
        "..gggg......",
        ".s.gg.......",
        "s...........",
    ], dict(s=(170, 120, 70), p=(246, 160, 180), w=(250, 248, 240), g=(130, 190, 100)))


def _taiyaki(img):
    _px(img, [
        "............",
        "...ttttt....",
        "..tTTtttt.t.",
        ".tTettttttt.",
        "tttttttttttt",
        "ttTtTtTttttt",
        "tttttttttt.t",
        ".tttttttt...",
        "..ttttt.....",
        "............",
        "............",
        "............",
    ], dict(t=(214, 140, 60), T=(240, 186, 100), e=(60, 30, 20)))


def _takoyaki(img):
    _px(img, [
        "............",
        "..b..b...b..",
        ".bbb.bbb.bbb",
        ".bsb.bgb.bsb",
        ".bbb.bbb.bbb",
        "..b..b...b..",
        "............",
        "kkkkkkkkkkkk",
        "kKKKKKKKKKKk",
        ".kkkkkkkkkk.",
        "............",
        "............",
    ], dict(b=(190, 120, 50), s=(110, 50, 30), g=(90, 160, 70), k=(130, 90, 50), K=(170, 120, 70)))


def _pocky(img):
    _px(img, [
        "........c...",
        ".......cc.c.",
        "......cc.cc.",
        ".....cc.cc..",
        "....cc.cc...",
        "...cc.cc....",
        "..bb.cc.....",
        ".bb.bb......",
        "bb.bb.......",
        "rrrrr.......",
        "rRRrr.......",
        "rrrrr.......",
    ], dict(c=(90, 40, 30), b=(230, 190, 120), r=(210, 30, 40), R=(250, 240, 240)))


def _melon_pan(img):
    _px(img, [
        "............",
        "...mmmmmm...",
        "..mMmMmMmm..",
        ".mmMmMmMmmm.",
        ".mMmMmMmMmm.",
        ".mmMmMmMmmm.",
        ".mMmMmMmMmm.",
        "..mmmmmmmm..",
        "..bbbbbbbb..",
        "............",
        "............",
        "............",
    ], dict(m=(236, 214, 120), M=(250, 236, 170), b=(200, 150, 70)))


def _dorayaki(img):
    _px(img, [
        "............",
        "............",
        "..cccccccc..",
        ".cCCCCcccccc",
        ".cccccccccc.",
        ".aaaaaaaaaa.",
        ".AaAaaAaaAa.",
        ".cccccccccc.",
        ".cccccccccc.",
        "..cccccccc..",
        "............",
        "............",
    ], dict(c=(170, 100, 40), C=(210, 150, 80), a=(110, 40, 50), A=(150, 70, 80)))


def _bento(img):
    _px(img, [
        "............",
        "kkkkkkkkkkkk",
        "kwwwwwKoooKk",
        "kwwrwwKoyoKk",
        "kwwwwwKoooKk",
        "kwwwwwKKKKKk",
        "kwwwwwKgggKk",
        "kwwwwwKgpgKk",
        "kkkkkkkkkkkk",
        "kRRRRRRRRRRk",
        "kkkkkkkkkkkk",
        "............",
    ], dict(k=(40, 26, 24), K=(60, 40, 34), w=(248, 248, 244), r=(220, 40, 50),
            o=(240, 160, 60), y=(250, 220, 90), g=(110, 180, 80), p=(240, 150, 170), R=(180, 30, 40)))


_DRAW = {"RAMEN": _ramen, "ONIGIRI": _onigiri, "MOCHI": _mochi, "DANGO": _dango,
         "TAIYAKI": _taiyaki, "TAKOYAKI": _takoyaki, "POCKY": _pocky, "MELON PAN": _melon_pan,
         "DORAYAKI": _dorayaki, "BENTO": _bento}
