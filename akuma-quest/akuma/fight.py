"""Street-fighter style one-round battle against a map enemy and any allies it
brought along (level 2 fights are two on one)."""

import random

import pygame

from . import audio
from .akuma_sprites import AkumaArt, CharArt, portrait
from .art import AKUMA_LOOK, make_spark, make_dust, make_stage
from .config import W, H, HITSTOP, STAGE_LEFT, STAGE_RIGHT
from .fighters import Fighter, AI, overlap, contact, CANCEL_WINDOW, MAX_COMBO, AKUMA_MOVES, THROW_RANGE
from .font import draw_text
from .pause import PauseMenu

SPARK_HIT = None
SPARK_BLOCK = None
DUST = None
_STAGES = {}
_AKUMA_ART = None
_PORTRAIT = None
BAR_W = 110
BOSS_SCALE = 1.15


CONTROLS = ["J PUNCH  K KICK  L SPECIAL",
            "SPECIAL: HADOUKEN  DOWN = HURRICANE KICK",
            "  DOWN-FWD / DOWN-BACK = SHORYUKEN",
            "PUNCH: JAB / DOWN = CROUCH JAB",
            "KICK: FRONT / BACK ROUNDHOUSE / DOWN SWEEP",
            "  DOWN-FWD = LOW KICK",
            "AIR: PUNCH, KICK, DOWN+KICK = DIVE KICK",
            "  SPECIAL = AIR FIREBALL",
            "PUNCH + KICK UP CLOSE = THROW (HOLD A DIRECTION)",
            "HOLD BACK TO BLOCK, DOWN-BACK FOR LOWS"]


class Effect:
    def __init__(self, frames, x, y, rate=3, flip=False):
        self.frames, self.x, self.y, self.rate, self.t = frames, x, y, rate, 0
        self.flip = flip

    @property
    def alive(self):
        return self.t < len(self.frames) * self.rate

    def update(self):
        self.t += 1

    def draw(self, surf, shake):
        img = self.frames[min(len(self.frames) - 1, self.t // self.rate)]
        if self.flip:
            img = pygame.transform.flip(img, True, False)
        surf.blit(img, (round(self.x - img.get_width() / 2) + shake[0],
                        round(self.y - img.get_height() / 2) + shake[1]))


_MINI = {}


def _mini(img, h=14):
    m = _MINI.get(id(img))
    if m is None or m[0] is not img:
        m = _MINI[id(img)] = (img, pygame.transform.smoothscale(img, (h, h)))
    return m[1]


def init_shared():
    """Effects and Akuma's sprites, built once and shared by every fight."""
    global SPARK_HIT, SPARK_BLOCK, DUST, _AKUMA_ART, _PORTRAIT
    if SPARK_HIT is None:
        SPARK_HIT = make_spark((255, 200, 60))
        SPARK_BLOCK = make_spark((120, 180, 255))
        DUST = make_dust()
        _AKUMA_ART = AkumaArt()
        _PORTRAIT = portrait()


class FightScene:
    def __init__(self, game, enemy, akuma_hp, akuma_max, power=1.0, ambush=False, seed=None):
        init_shared()
        self.game = game
        self.enemy_ref = enemy
        self.rng = random.Random(seed)
        self.boss = enemy.boss
        lvl = getattr(game, "level", 1)
        variant = self.rng.choice((0, 1)) if lvl == 1 else 2
        key = (variant, self.boss, lvl)
        if key not in _STAGES:
            _STAGES[key] = make_stage(*key)
        self.stage = _STAGES[key]
        p = Fighter("AKUMA", AKUMA_LOOK, {}, akuma_max, walk=1.75, back_walk=1.35,
                    is_player=True, art=_AKUMA_ART)
        p.hp = akuma_hp
        self.p = p
        # every enemy is a character from Toshi's sprite pack; bosses a bit bigger
        squad = [enemy] + list(getattr(enemy, "allies", ()))
        self.foes = [self._make_foe(en, ambush) for en in squad]
        self.e = e = self.foes[0]
        self.e_portrait = self.portraits[e]
        self.fighters = [p] + self.foes
        self._place()
        p.opponent = e
        self.projectiles = []
        self.effects = []
        for f in self.fighters:
            f.projectiles = self.projectiles
            f.effects = self._spawn_effect
            f.state = "intro"
        self.ais = {}
        for f, en in zip(self.foes, squad):
            f.opponent = p
            self.ais[f] = AI(self.rng, **en.ai)
            self.ais[f].setup(f)
        self.ai = self.ais[e]
        self.attackers = 2      # foes allowed to press the attack at once; the rest circle
        self.power = power
        self.ambush = ambush
        # grunt fights start and end fast so a dungeon full of them never drags
        self.intro_len = 60 if self.boss else 26
        self.outro_len = 150 if self.boss else 64
        self.level = getattr(enemy, "level", 0)
        self.phase = "intro"
        self.t = 0
        self.hitstop = 0
        self.shake = 0
        self.combo = 0
        self.combo_show = 0
        self.combo_owner = None
        self.lag = {f: f.hp for f in self.fighters}
        self.embers = []
        self.result = None
        self.enraged = False
        self.menu = PauseMenu(game, CONTROLS)

    def _make_foe(self, en, ambush, k=None):
        k = k or (BOSS_SCALE if self.boss else 1.0)
        f = Fighter(en.name, en.look, en.moves, en.hp, walk=en.walk, back_walk=en.walk * 0.8,
                    art=CharArt(en.cid, k))
        f.sx = f.sy = k
        f.level = getattr(en, "level", 0)
        if ambush:
            f.hp = int(f.hp * 0.8)
        if not hasattr(self, "portraits"):
            self.portraits = {}
        self.portraits[f] = pygame.transform.flip(portrait(f.art.cid), True, False)
        return f

    def _place(self):
        """Akuma left of a lone foe; against a gang he starts in the middle."""
        p = self.p
        if len(self.foes) == 1:
            p.x, self.foes[0].x = 115.0, 205.0
        else:
            p.x = W / 2
            for i, f in enumerate(self.foes):
                side = 1 if i % 2 == 0 else -1
                f.x = W / 2 + side * (75 + 45 * (i // 2))
        for f in self.foes:
            f.x = max(STAGE_LEFT + 10, min(STAGE_RIGHT - 10, f.x))
            f.facing = 1 if p.x > f.x else -1
        p.facing = 1 if self.foes[0].x > p.x else -1

    def live_foes(self):
        return [f for f in self.foes if not f.ko]

    def _retarget(self):
        """Akuma squares up to the closest foe still standing."""
        live = self.live_foes()
        if live:
            self.p.opponent = min(live, key=lambda f: (f.state in ("down", "getup"), abs(f.x - self.p.x)))

    def _foe_intents(self):
        """The nearest few foes fight; the others hang back until a slot opens."""
        live = sorted(self.live_foes(), key=lambda f: abs(f.x - self.p.x))
        out = {}
        for i, f in enumerate(live):
            it = self.ais[f].think(f)
            if i >= self.attackers:
                it.pop("move", None)
                d = f.x - self.p.x
                if abs(d) < 70:
                    it = {"left" if d < 0 else "right": True} if f.state == "stand" else {}
            out[f] = it
        return out

    # --------------------------------------------------------------------
    def _spawn_effect(self, kind, x, y):
        if kind == "dust":
            self.effects.append(Effect(DUST, x, y - 4, 4))

    def _intent(self, inp):
        return dict(left=inp.held("left"), right=inp.held("right"), up=inp.held("up"),
                    down=inp.held("down"), punch=inp.pressed("punch"), kick=inp.pressed("kick"),
                    special=inp.pressed("special"))

    @property
    def paused(self):
        return self.menu.open

    def update(self, inp):
        if self.menu.open:
            self.menu.update(inp)
            return
        if self.phase == "fight" and self.menu.toggle(inp):
            return
        self.t += 1
        for f in self.fighters:
            if self.lag[f] > f.hp:
                self.lag[f] = max(f.hp, self.lag[f] - 0.6)
            else:
                self.lag[f] = f.hp
        if self.shake:
            self.shake -= 1
        for f in self.fighters:
            if f.flash:
                f.flash -= 1
        if self.combo_show:
            self.combo_show -= 1
        for fx in self.effects:
            fx.update()
        self.effects = [fx for fx in self.effects if fx.alive]
        self._embers()

        if self.phase == "intro":
            for f in self.fighters:
                f.update({})
            if self.t == self.intro_len - 18:
                audio.play("fight")
            if self.t >= self.intro_len:
                self.phase = "fight"
                for f in self.fighters:
                    f._to_stand()
            return

        if self.hitstop > 0:
            self.hitstop -= 1
            if self.phase == "fight":
                self.p.feed_buffer(self._intent(inp))
            return

        if self.phase == "ko":
            self.ko_t += 1
            slow = self.ko_t < 30 and self.ko_t % 2 != 0
            if not slow:
                self._step({}, foe_intents={})
            won = not self.p.ko
            if self.ko_t == self.outro_len // 2:
                for winner in [self.p] if won else self.live_foes():
                    if winner.on_ground and winner.state in ("stand", "land", "move"):
                        winner._to_stand()
                    winner.state = "win"
            if self.ko_t >= self.outro_len or (self.ko_t > 24 and inp.any_pressed("punch", "kick", "special", "start")):
                self.result = "win" if won else "lose"
                self.game.end_fight(self, self.result, self.p.hp)
            return

        self._retarget()
        self._step(self._intent(inp), foe_intents=self._foe_intents())

        if self.boss and not self.enraged and self.e.hp <= self.e.max_hp // 2:
            self.enraged = True
            self.e.tint = (255, 40, 40)
            self.e.speed_mul = 1.25
            self.ai.aggr = min(1.0, self.ai.aggr * 1.35)
            self.ai.block = min(0.9, self.ai.block + 0.15)

        if self.p.ko or not self.live_foes():
            self.phase = "ko"
            self.ko_t = 0
            self.hitstop = 12
            self.shake = 14
            audio.play("ko")

    def _step(self, pi, ei=None, foe_intents=None):
        """One frame of the fight. ei is the first foe's intent (practice
        drives its dummy that way); foe_intents gives every foe its own."""
        p = self.p
        intents = foe_intents if foe_intents is not None else {self.e: ei or {}}
        p.update(pi)
        for f in self.foes:
            f.update(intents.get(f, {}))
        self._push_apart()
        for pr in self.projectiles:
            pr.update()
        # projectile clashes
        for a in self.projectiles:
            for b in self.projectiles:
                if a is not b and (a.owner is p) != (b.owner is p) and a.alive and b.alive and overlap(a.rect(), b.rect()):
                    a.alive = b.alive = False
                    self.effects.append(Effect(SPARK_BLOCK, (a.x + b.x) / 2, a.y, 2))
                    audio.play("block")
        for pr in self.projectiles:
            if not pr.alive:
                continue
            for tgt in (self.foes if pr.owner is p else [p]):
                at = contact(pr.area(), tgt.hurt_area())
                if at is None:
                    continue
                pr.alive = False
                dmg = pr.dmg * (self.power if pr.owner is p else 1)
                self._resolve(pr.owner, tgt, dict(dmg=round(dmg), hitstun=pr.hitstun,
                                                   blockstun=pr.blockstun, height="mid",
                                                   push=2.6, chip=pr.chip),
                              pr.x - pr.dir * 10, at, projectile=True)
                break
        self.projectiles[:] = [pr for pr in self.projectiles if pr.alive]
        self._throws()
        # melee: an attack lands where its drawn fist or foot touches the target's drawing
        hits = []
        for att, dfn in self._pairs():
            at = contact(att.strike_area(), dfn.hurt_area())
            if at is not None:
                hits.append((att, dfn, at, att.move))
        landed = set()
        for att, dfn, at, m in hits:
            if att not in landed:
                att.hits_done += 1
                att.last_hit_t = att.move_t
                landed.add(att)
            dmg = m["dmg"] * (self.power if att is p else 1)
            if att.is_player and m.get("cat") in ("punch", "kick"):
                att.cancel = CANCEL_WINDOW   # hit or block, the next press can cancel
            self._resolve(att, dfn, dict(dmg=round(dmg), hitstun=m["hitstun"],
                                         blockstun=m["blockstun"], height=m.get("height", "mid"),
                                         knockdown=m.get("knockdown", False),
                                         launch=m.get("launch", -4.5), push=m.get("push", 2.5),
                                         chip=1 if m["dmg"] >= 14 else 0,
                                         opener=m.get("opener", False)),
                          att.x, at)
            if m.get("bounce") and att.vy >= -2.2:
                # a small hop off the target, landing right in front of it to keep comboing
                att.vy = -2.2
                att.vx = -0.4 * att.facing
                att.bounced = True

    def _pairs(self):
        """(attacker, defender) pairs: Akuma against each foe; foes never hit each other."""
        live = self.live_foes()
        return [(self.p, f) for f in live] + [(f, self.p) for f in live]

    def _throws(self):
        """A grab that is close enough to a grounded opponent becomes a throw:
        unblockable, 2x damage, tossed the way the thrower chose."""
        for att, dfn in [(self.p, self.p.opponent)] + [(f, self.p) for f in self.live_foes()]:
            if dfn is None:
                continue
            m = att.move
            if att.state != "move" or not m or not m.get("grab") or att.phase()[0] != "active":
                continue
            if not (dfn.on_ground and dfn.state in ("stand", "land", "move", "prejump", "intro")):
                continue
            if dfn.hurtbox() is None or abs(dfn.x - att.x) > THROW_RANGE:
                continue
            d = att.throw_dir
            att.start_move(AKUMA_MOVES["toss"], chained=True)
            att.facing = d
            dfn.x = max(STAGE_LEFT, min(STAGE_RIGHT, att.x + d * 16))
            dmg = m["dmg"] * (self.power if att is self.p else 1)
            self._resolve(att, dfn, dict(dmg=round(dmg), hitstun=30, blockstun=0, height="mid",
                                         knockdown=True, launch=-5.0, push=0, throw=True),
                          dfn.x - d * 4, (dfn.x, dfn.y - 30))
            if not dfn.ko:
                dfn.vx = 3.2 * d
            dfn.facing = -d

    def _resolve(self, att, dfn, info, from_x, at, projectile=False):
        if not info.get("throw") and dfn.can_block(info["height"]):
            dfn.take_block(info["blockstun"], info["push"], from_x, info.get("chip", 0))
            self.effects.append(Effect(SPARK_BLOCK, at[0], at[1], 2))
            audio.play("block")
            self.hitstop = max(self.hitstop, 5)
            if not projectile and att.on_ground:
                self._wall_push(att, dfn, info["push"])
            return
        if dfn.state in ("hitstun", "launched") and self.combo_owner is att:
            self.combo += 1
        else:
            self.combo = 1
            self.combo_owner = att
        dmg = info["dmg"]
        knockdown = info.get("knockdown", False)
        if att.is_player and self.combo >= MAX_COMBO:
            knockdown = True           # combo cap: the last hit always sends them flying
        heavy = dmg >= 14 or knockdown or info.get("throw")
        dfn.take_hit(dmg, info["hitstun"], from_x, knockdown, info.get("launch", -4.5), info["push"],
                     opener=info.get("opener", False))
        self.on_damage(att, dmg)
        if self.combo >= 2:
            self.combo_show = 70
        self.effects.append(Effect(SPARK_HIT, at[0], at[1], 2))
        audio.play("heavy" if heavy else "hit")
        self.hitstop = max(self.hitstop, HITSTOP + (4 if heavy else 0))
        self.shake = max(self.shake, 8 if heavy else 4)
        if not projectile and att.on_ground:
            self._wall_push(att, dfn, info["push"])

    def on_damage(self, att, dmg):
        pass

    def _wall_push(self, att, dfn, push):
        if dfn.x <= STAGE_LEFT + 1 or dfn.x >= STAGE_RIGHT - 1:
            att.vx = -att.facing * push

    def _push_apart(self):
        fs = [f for f in self.fighters if f.state not in ("down", "ko") and not f.ko]
        for i, a in enumerate(fs):
            for b in fs[i + 1:]:
                self._separate(a, b)

    def _separate(self, p, e):
        """Bodies don't overlap; if one is pinned against a wall the other takes the push."""
        wa = p.hurt_w * 0.75
        wb = e.hurt_w * 0.75
        if abs(p.y - e.y) > 36:
            return
        dx = e.x - p.x
        min_d = wa + wb
        if abs(dx) < min_d:
            over = min_d - abs(dx)
            s = 1 if dx > 0 else -1
            if dx == 0:
                s = -p.facing
            p.x -= s * over / 2
            e.x += s * over / 2
            for f in (p, e):
                f.x = max(STAGE_LEFT, min(STAGE_RIGHT, f.x))
            if abs(e.x - p.x) < min_d - 0.5:
                if p.x <= STAGE_LEFT or p.x >= STAGE_RIGHT:
                    e.x = p.x + s * min_d
                else:
                    p.x = e.x - s * min_d

    def _embers(self):
        if self.boss or self.enraged:
            if self.rng.random() < 0.4:
                self.embers.append([self.rng.uniform(0, W), H, self.rng.uniform(-0.3, 0.3),
                                    self.rng.uniform(-1.2, -0.4), self.rng.randint(60, 160)])
        for em in self.embers:
            em[0] += em[2]
            em[1] += em[3]
            em[4] -= 1
        self.embers = [em for em in self.embers if em[4] > 0]

    # --------------------------------------------------------------------
    def draw(self, surf):
        sh = (0, 0)
        if self.shake:
            sh = (self.rng.choice((-2, -1, 1, 2)), self.rng.choice((-1, 0, 1)))
        surf.blit(self.stage, sh)
        for em in self.embers:
            surf.set_at((int(em[0]), int(em[1])), (255, 140 + (em[4] % 3) * 40, 40))
        # whoever is attacking draws on top
        order = sorted(self.fighters, key=lambda f: (not f.ko, f.state == "move", f is self.p))
        for f in order:
            f.draw(surf, sh)
        for pr in self.projectiles:
            pr.draw(surf, sh)
        for fx in self.effects:
            fx.draw(surf, sh)
        self._hud(surf)
        if self.menu.open:
            self._draw_menu(surf)

    def _bar(self, surf, f, x, right, y=10, bh=8, bw=BAR_W):
        pygame.draw.rect(surf, (10, 6, 14), (x - 1, y - 1, bw + 2, bh + 2))
        pygame.draw.rect(surf, (90, 16, 20), (x, y, bw, bh))
        lag_w = int(bw * self.lag[f] / f.max_hp)
        cur_w = int(bw * f.hp / f.max_hp)
        col = (250, 210, 40) if f.hp > f.max_hp * 0.25 else (255, 120, 40)
        if right:
            pygame.draw.rect(surf, (230, 60, 40), (x + bw - lag_w, y, lag_w, bh))
            pygame.draw.rect(surf, col, (x + bw - cur_w, y, cur_w, bh))
            pygame.draw.rect(surf, (255, 255, 200), (x + bw - cur_w, y, cur_w, 2))
        else:
            pygame.draw.rect(surf, (230, 60, 40), (x, y, lag_w, bh))
            pygame.draw.rect(surf, col, (x, y, cur_w, bh))
            pygame.draw.rect(surf, (255, 255, 200), (x, y, cur_w, 2))

    def _hud(self, surf):
        surf.blit(_PORTRAIT, (4, 4))
        pygame.draw.rect(surf, (10, 6, 14), (3, 3, _PORTRAIT.get_width() + 2, _PORTRAIT.get_height() + 2), 1)
        self._bar(surf, self.p, 40, False)
        draw_text(surf, "AKUMA", 40, 21, (255, 90, 90))
        if len(self.foes) == 1:
            ep = self.e_portrait
            surf.blit(ep, (W - 4 - ep.get_width(), 4))
            pygame.draw.rect(surf, (10, 6, 14), (W - 5 - ep.get_width(), 3, ep.get_width() + 2, ep.get_height() + 2), 1)
            self._bar(surf, self.e, W - 38 - BAR_W, True)
            name = self.e.name if self.boss or not self.level else "LV%d %s" % (self.level, self.e.name)
            draw_text(surf, name, W - 38, 21, (255, 230, 120) if self.boss else (220, 220, 255),
                      align="right")
            moves = " / ".join(m["name"] for m in self.e.moves)
            if not self.boss:
                draw_text(surf, moves, W - 38, 30, (150, 150, 170), align="right")
        else:
            self._gang_hud(surf)
        draw_text(surf, "KO", W // 2, 9, (255, 60, 60), scale=1, align="center")
        if self.phase == "intro":
            if self.t < self.intro_len - 18:
                n = len(self.foes)
                txt = "SNEAK ATTACK!" if self.ambush else ("BOSS!" if self.boss else "VS" if n == 1 else "%d ON 1!" % n)
                draw_text(surf, txt, W // 2, 70, (255, 220, 80), scale=2, align="center")
                names = self.e.name if n == 1 else " & ".join(f.name for f in self.foes[:3])
                draw_text(surf, names, W // 2, 90, (255, 255, 255), align="center")
            else:
                draw_text(surf, "FIGHT!", W // 2, 70, (255, 60, 40), scale=3, align="center")
        if self.combo_show and self.combo >= 2:
            x = 6 if self.combo_owner is self.p else W - 6
            draw_text(surf, "%d HIT COMBO" % self.combo, x, 46, (255, 200, 40), scale=2,
                      align="left" if self.combo_owner is self.p else "right")
        if self.phase == "ko":
            if (self.ko_t // 6) % 2 == 0 or self.ko_t > 30:
                draw_text(surf, "K.O.", W // 2, 64, (255, 50, 40), scale=4, align="center")
            if self.ko_t > self.outro_len // 2:
                msg = "AKUMA FALLS..." if self.p.ko else "AKUMA WINS"
                draw_text(surf, msg, W // 2, 100, (255, 255, 255), scale=2, align="center")
        if self.enraged and self.phase == "fight" and self.t % 60 < 30:
            draw_text(surf, "ENRAGED!", W - 8, 30, (255, 80, 60), align="right")

    def _gang_hud(self, surf):
        """Two or three foes: a small portrait, bar and name each, stacked on the right."""
        for i, f in enumerate(self.foes[:3]):
            y = 5 + i * 17
            small = _mini(self.portraits[f])
            surf.blit(small, (W - 4 - small.get_width(), y))
            if f.ko:
                pygame.draw.line(surf, (255, 60, 40), (W - 4 - small.get_width(), y),
                                 (W - 5, y + small.get_height() - 1), 2)
            self._bar(surf, f, W - 8 - small.get_width() - BAR_W, True, y=y + 1, bh=5)
            name = f.name if not f.level else "LV%d %s" % (f.level, f.name)
            draw_text(surf, name, W - 8 - small.get_width(), y + 8, (150, 150, 170) if f.ko else (220, 220, 255),
                      align="right")

    def _draw_menu(self, surf):
        self.menu.draw(surf)
