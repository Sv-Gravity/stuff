"""Level 7, Hu Lao Gate: Dynasty Warriors style. Every fight is Akuma against a
whole squad of one- or two-hit soldiers who pour in from both sides, a KO
counter, a Musou gauge, and Lu Bu waiting at the end."""

import random

import pygame

from . import audio
from .config import W, H, GROUND_Y, STAGE_LEFT, STAGE_RIGHT
from .fight import FightScene, Effect, CONTROLS
from . import fight as F
from .fighters import HIT
from .font import draw_text
from .pause import PauseMenu

ON_STAGE = 5            # soldiers fighting at once; the rest wait to charge in
ATTACKERS = 3           # of those, how many press the attack together
GONE_AFTER = 50         # frames a beaten soldier lies there before vanishing
MUSOU_MAX = 100
MUSOU_GAIN_HIT = 9      # gauge per hit landed
MUSOU_GAIN_HURT = 0.5   # gauge per point of damage taken
MUSOU_DMG = 3 * HIT     # what the Musou attack does to every soldier on screen
MUSOU_LEN = 70
LUBU_SCALE = 1.3

MUSOU_CONTROLS = CONTROLS + ["I (GAUGE FULL) = MUSOU ATTACK: SHUN GOKU SATSU"]

_STAGE = {}


def make_gate_stage(boss=False):
    """Hu Lao Gate at dusk: the fortress wall, its great gate, faction banners."""
    rng = random.Random(7 + boss)
    s = pygame.Surface((W, H))
    top, bot = ((40, 10, 14), (200, 80, 40)) if boss else ((60, 40, 70), (230, 150, 80))
    for y in range(GROUND_Y):
        t = round(y / GROUND_Y * 10) / 10
        s.fill([int(a + (b - a) * t) for a, b in zip(top, bot)], (0, y, W, 1))
    # setting sun and smoke
    pygame.draw.circle(s, (255, 210, 120), (250, 70), 16)
    for _ in range(6):
        x = rng.randrange(W)
        for k in range(8):
            pygame.draw.circle(s, (90, 70, 80), (x + k * 2, 90 - k * 9), 5 + k)
    # distant hills
    pts = [(0, 120)] + [(x, 104 + rng.randint(-8, 8)) for x in range(0, W + 20, 20)] + [(W, 120)]
    pygame.draw.polygon(s, (90, 60, 60), pts + [(W, 130), (0, 130)])
    # the wall
    wall, dark, lite = (120, 86, 56), (74, 50, 32), (150, 112, 74)
    pygame.draw.rect(s, wall, (0, 60, W, 98))
    for y in range(64, 156, 8):
        off = 0 if (y // 8) % 2 else 10
        pygame.draw.line(s, dark, (0, y), (W, y))
        for x in range(off, W, 20):
            pygame.draw.line(s, dark, (x, y), (x, y + 8))
    for x in range(0, W, 16):      # battlements
        pygame.draw.rect(s, wall, (x, 50, 10, 10))
        pygame.draw.rect(s, lite, (x, 50, 10, 2))
    pygame.draw.rect(s, lite, (0, 60, W, 2))
    # gate tower and the great gate
    gx = W // 2 - 40
    pygame.draw.rect(s, (60, 22, 18), (gx - 6, 22, 92, 30))
    pygame.draw.polygon(s, (30, 20, 24), [(gx - 16, 24), (W // 2, 6), (gx + 96, 24)])
    for x in range(gx, gx + 80, 12):
        pygame.draw.rect(s, (230, 180, 70), (x + 4, 30, 4, 14))
    pygame.draw.rect(s, (60, 34, 20), (gx, 84, 80, 74))
    pygame.draw.rect(s, (40, 22, 14), (gx, 84, 80, 74), 2)
    pygame.draw.line(s, (40, 22, 14), (W // 2, 84), (W // 2, 158), 2)
    for y in range(94, 156, 12):
        for x in range(gx + 6, gx + 80, 12):
            pygame.draw.circle(s, (200, 160, 70), (x, y), 2)
    # faction banners on poles: Wei blue, Shu green, Wu red, Yellow Turbans, Lu Bu's black and red
    colours = [(40, 70, 170), (40, 140, 60), (190, 40, 40), (220, 190, 40), (30, 20, 30)]
    for i, x in enumerate((14, 52, 92, 230, 268, 306)):
        c = colours[i % len(colours)]
        pygame.draw.line(s, (50, 30, 20), (x, 30), (x, 158), 2)
        pygame.draw.polygon(s, c, [(x + 1, 32), (x + 16, 34), (x + 14, 60), (x + 1, 58)])
        pygame.draw.rect(s, (240, 230, 200), (x + 5, 40, 6, 10))   # the family name panel
        pygame.draw.line(s, (20, 10, 10), (x + 6, 43), (x + 10, 43))
        pygame.draw.line(s, (20, 10, 10), (x + 8, 41), (x + 8, 48))
    # braziers
    for x in (36, 284):
        pygame.draw.rect(s, (40, 30, 30), (x - 6, 140, 12, 18))
        pygame.draw.polygon(s, (255, 150, 40), [(x - 6, 140), (x, 126), (x + 6, 140)])
        pygame.draw.polygon(s, (255, 230, 120), [(x - 3, 140), (x, 132), (x + 3, 140)])
    # trampled ground
    pygame.draw.rect(s, (110, 84, 56), (0, GROUND_Y, W, H - GROUND_Y))
    pygame.draw.line(s, (150, 118, 80), (0, GROUND_Y), (W, GROUND_Y))
    for _ in range(80):
        s.set_at((rng.randrange(W), rng.randrange(GROUND_Y + 2, H)), (84, 62, 40))
    return s


class MusouScene(FightScene):
    def __init__(self, game, enemy, akuma_hp, akuma_max, power=1.0, ambush=False, seed=None):
        super().__init__(game, enemy, akuma_hp, akuma_max, power, ambush, seed)
        if self.boss and self.e.art.cid == "lubu":
            self._grow(self.e, LUBU_SCALE)
        if self.boss not in _STAGE:
            _STAGE[self.boss] = make_gate_stage(self.boss)
        self.stage = _STAGE[self.boss]
        self.attackers = ATTACKERS
        # only a handful fight at once; the rest charge in as soldiers fall
        self.reserve = self.foes[ON_STAGE:]
        del self.foes[ON_STAGE:]
        self.fighters = [self.p] + self.foes
        self._place()
        self.total = len(self.foes) + len(self.reserve)
        self.down_t = {}
        self.kos = getattr(game, "musou_kos", 0)
        self.fight_kos = 0
        self.gauge = getattr(game, "musou_gauge", 0.0)
        self.musou_t = 0
        self.banner = None          # (text, frames left)
        self.intro_len = 60 if self.boss else 34
        self.menu = PauseMenu(game, MUSOU_CONTROLS)

    @staticmethod
    def _grow(f, k):
        from .akuma_sprites import CharArt
        f.art = CharArt(f.art.cid, k)
        f.sx = f.sy = k
        f._measure_hurtbox()

    # ---- the squad ----------------------------------------------------
    def _reinforce(self):
        on = [f for f in self.foes if not f.ko]
        while self.reserve and len(on) < ON_STAGE:
            f = self.reserve.pop(0)
            side = self.rng.choice((-1, 1)) if self.p.x > 90 and self.p.x < W - 90 else \
                (1 if self.p.x < W / 2 else -1)
            f.x = STAGE_LEFT + 4 if side < 0 else STAGE_RIGHT - 4
            f.y = float(GROUND_Y)
            f.facing = -side
            f.state = "stand"
            f._to_stand()
            self.foes.append(f)
            self.fighters.append(f)
            on.append(f)

    def _clear_fallen(self):
        for f in list(self.foes):
            if not f.ko or f is self.e and self.boss:
                continue
            if f not in self.down_t:
                self.down_t[f] = 0
                self.kos += 1
                self.fight_kos += 1
                self.gauge = min(MUSOU_MAX, self.gauge + 4)
                if self.kos % 50 == 0:
                    self.banner = ("%d KO!" % self.kos, 90)
                    audio.play("fight")
            self.down_t[f] += 1
            if self.down_t[f] > GONE_AFTER and f is not self.e:
                self.foes.remove(f)
                self.fighters.remove(f)

    def live_foes(self):
        return [f for f in self.foes if not f.ko] + ([self.reserve[0]] if self.reserve and
                                                      not any(not f.ko for f in self.foes) else [])

    def on_damage(self, att, dmg):
        if att is self.p:
            self.gauge = min(MUSOU_MAX, self.gauge + MUSOU_GAIN_HIT)
        else:
            self.gauge = min(MUSOU_MAX, self.gauge + dmg * MUSOU_GAIN_HURT)

    # ---- musou attack -------------------------------------------------
    def _musou(self):
        """Akuma's Shun Goku Satsu on every soldier on screen."""
        self.musou_t += 1
        t = self.musou_t
        targets = [f for f in self.foes if not f.ko and abs(f.x - self.p.x) < W]
        if t % 6 == 0 and targets:
            f = self.rng.choice(targets)
            self.effects.append(Effect(F.SPARK_HIT, f.x + self.rng.randint(-10, 10),
                                       f.y - self.rng.randint(20, 60), 2))
            audio.play("hit")
        if t == MUSOU_LEN:
            audio.play("ko")
            self.shake = 20
            for f in targets:
                f.take_hit(MUSOU_DMG, 30, self.p.x, knockdown=True, launch=-6.0)
                self.lag[f] = self.lag.get(f, f.hp)
            self.p._to_stand()
            self.musou_t = 0
            self.banner = ("SHUN GOKU SATSU", 70)

    # ---- frame --------------------------------------------------------
    def update(self, inp):
        if self.banner:
            self.banner = (self.banner[0], self.banner[1] - 1) if self.banner[1] > 1 else None
        if self.musou_t and not self.menu.open:
            self.t += 1
            for fx in self.effects:
                fx.update()
            self.effects = [fx for fx in self.effects if fx.alive]
            if self.shake:
                self.shake -= 1
            self._musou()
            return
        if (self.phase == "fight" and not self.menu.open and self.gauge >= MUSOU_MAX
                and inp.pressed("shield") and self.p.state in ("stand", "move", "land")):
            self.gauge = 0
            self.musou_t = 1
            self.p.move = None
            self.p.state = "stand"
            self.p.pose = "taunt"
            self.p.pose_t = 0
            audio.play("encounter")
            self.banner = ("MUSOU!", 60)
            return
        if self.phase == "fight":
            self._reinforce()
        if self.phase in ("fight", "ko"):
            self._clear_fallen()
        for f in self.fighters:
            self.lag.setdefault(f, f.hp)
        super().update(inp)
        self.game.musou_kos = self.kos
        self.game.musou_gauge = self.gauge

    def _step(self, pi, ei=None, foe_intents=None):
        super()._step(pi, ei, foe_intents)
        # crowds don't stack up on one spot behind Akuma
        for f in self.foes:
            f.x = max(STAGE_LEFT, min(STAGE_RIGHT, f.x))

    # ---- drawing ------------------------------------------------------
    def draw(self, surf):
        super().draw(surf)
        if self.musou_t:
            # the screen goes dark and red while the demon works
            dark = pygame.Surface((W, H), pygame.SRCALPHA)
            a = min(200, self.musou_t * 8)
            dark.fill((0, 0, 0, a) if self.musou_t % 12 < 9 else (120, 0, 0, a))
            surf.blit(dark, (0, 0))
            draw_text(surf, "SHUN GOKU SATSU", W // 2, 70, (255, 60, 40), scale=2, align="center")
            if self.musou_t > MUSOU_LEN - 20:
                draw_text(surf, "TEN", W // 2, 96, (255, 255, 255), scale=3, align="center")

    def _hud(self, surf):
        surf.blit(F._PORTRAIT, (4, 4))
        pygame.draw.rect(surf, (10, 6, 14), (3, 3, F._PORTRAIT.get_width() + 2, F._PORTRAIT.get_height() + 2), 1)
        self._bar(surf, self.p, 40, False)
        draw_text(surf, "AKUMA", 40, 21, (255, 90, 90))
        # Musou gauge under the life bar
        full = self.gauge >= MUSOU_MAX
        pygame.draw.rect(surf, (10, 6, 14), (39, 28, 82, 6))
        col = (255, 220, 60) if not full or self.t % 10 < 5 else (255, 255, 220)
        pygame.draw.rect(surf, col, (40, 29, int(80 * self.gauge / MUSOU_MAX), 4))
        draw_text(surf, "MUSOU" + (" READY: PRESS I" if full else ""), 40, 36, (255, 220, 60))
        # the KO counter
        draw_text(surf, "%d" % self.kos, W - 30, 6, (255, 255, 255), scale=2, align="right")
        draw_text(surf, "KO", W - 8, 12, (255, 200, 60), align="right")
        left = len([f for f in self.foes if not f.ko]) + len(self.reserve)
        draw_text(surf, "ENEMIES %d" % left, W - 8, 24, (220, 220, 255), align="right")
        if self.boss:
            self._bar(surf, self.e, W - 8 - BAR_W_BOSS, True, y=36, bh=6, bw=BAR_W_BOSS)
            draw_text(surf, self.e.name, W - 8, 45, (255, 80, 60), align="right")
        # a sliver of health over every soldier, like the real thing
        for f in self.foes:
            if f.ko or f is self.e and self.boss:
                continue
            head = f.y - f.hurt_h - 6
            w = 14
            pygame.draw.rect(surf, (20, 10, 10), (f.x - w // 2 - 1, head - 1, w + 2, 4))
            pygame.draw.rect(surf, (230, 60, 40), (f.x - w // 2, head, round(w * f.hp / f.max_hp), 2))
        if self.phase == "intro":
            if self.t < self.intro_len - 18:
                if self.boss:
                    draw_text(surf, "LU BU HAS ENTERED THE BATTLE!", W // 2, 64, (255, 80, 60),
                              align="center", scale=1)
                    draw_text(surf, "DON'T PURSUE LU BU!", W // 2, 80, (255, 220, 80), scale=2,
                              align="center")
                else:
                    draw_text(surf, "%d SOLDIERS ATTACK!" % self.total, W // 2, 70, (255, 220, 80),
                              scale=2, align="center")
            else:
                draw_text(surf, "FIGHT!", W // 2, 70, (255, 60, 40), scale=3, align="center")
        if self.phase == "ko":
            if (self.ko_t // 6) % 2 == 0 or self.ko_t > 30:
                msg = "AKUMA FALLS..." if self.p.ko else ("LU BU DEFEATED!" if self.boss else "VICTORY!")
                draw_text(surf, msg, W // 2, 64, (255, 50, 40), scale=2, align="center")
            if not self.p.ko and self.ko_t > self.outro_len // 2:
                draw_text(surf, "%d KO THIS BATTLE" % self.fight_kos, W // 2, 96, (255, 255, 255),
                          align="center")
        if self.combo_show and self.combo >= 2 and self.combo_owner is self.p:
            draw_text(surf, "%d HITS" % self.combo, 6, 46, (255, 200, 40), scale=2)
        if self.banner:
            draw_text(surf, self.banner[0], W // 2, 50, (255, 230, 80), scale=2, align="center")


BAR_W_BOSS = 120
