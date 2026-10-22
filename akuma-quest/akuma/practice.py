"""Practice mode: Akuma vs a training dummy that never dies."""

import random
from types import SimpleNamespace

from . import audio
from .art import random_look
from .config import W, H, GROUND_Y
from .fight import FightScene, CONTROLS
from .pause import PauseMenu
from .fighters import m_jab, m_kick, m_sweep, m_fireball
from .font import draw_text

MODES = ["STAND", "CROUCH", "BLOCK", "JUMP", "FIGHT BACK"]


def _dummy():
    rng = random.Random(4)
    look = random_look(rng, build="normal")
    look.update(top=(200, 170, 110), pants=(200, 170, 110), hair_style="bald",
                skin=(210, 180, 130), belt=(120, 80, 40), extras=set())
    return SimpleNamespace(name="SPARRING RYU", cid="ryu", look=look, boss=False, level=0, hp=100,
                           walk=1.3, moves=[m_jab(rng), m_kick(rng), m_sweep(rng), m_fireball(rng)],
                           ai=dict(aggression=0.5, block=0.3, jumpiness=0.2, reaction=6))


class PracticeScene(FightScene):
    def __init__(self, game):
        super().__init__(game, _dummy(), 160, 160, seed=1)
        self.intro_len = 20
        self.mode = 0
        self.idle_t = 0
        self.combo_dmg = 0
        self.last = None        # (hits, damage) of the last finished combo
        self.jump_t = 0
        self.menu = PauseMenu(game, CONTROLS, extra_items=("DUMMY", "RESET POSITIONS"),
                              confirm_quit=False)

    def on_damage(self, att, dmg):
        if att is not self.p:
            return
        if self.combo == 1:
            self.combo_dmg = 0
        self.combo_dmg += dmg
        self.last = (self.combo, self.combo_dmg)

    def _dummy_intent(self):
        mode = MODES[self.mode]
        e, p = self.e, self.p
        away = "left" if p.x > e.x else "right"
        if mode == "CROUCH":
            return {"down": True}
        if mode == "BLOCK":
            low = p.move is not None and p.move.get("height") == "low"
            return {away: True, "down": low}
        if mode == "JUMP":
            self.jump_t += 1
            return {"up": self.jump_t % 70 < 3}
        if mode == "FIGHT BACK":
            return self.ai.think(e)
        return {}

    def update(self, inp):
        if self.menu.open:
            self._menu(inp)
            return
        if self.phase == "fight" and self.menu.toggle(inp):
            return
        if self.phase != "fight":
            super().update(inp)
            return
        self.t += 1
        for f in (self.p, self.e):
            self.lag[f] = max(f.hp, self.lag[f] - 0.6) if self.lag[f] > f.hp else f.hp
            if f.flash:
                f.flash -= 1
        if self.shake:
            self.shake -= 1
        if self.combo_show:
            self.combo_show -= 1
        for fx in self.effects:
            fx.update()
        self.effects = [fx for fx in self.effects if fx.alive]
        if self.hitstop > 0:
            self.hitstop -= 1
            self.p.feed_buffer(self._intent(inp))
            return
        self._step(self._intent(inp), self._dummy_intent())
        # nobody dies in practice
        e, p = self.e, self.p
        if e.ko:
            e.ko = False
            e.hp = 1
        p.ko = False
        p.hp = p.max_hp
        if e.state in ("stand", "air", "land"):
            self.idle_t += 1
            if self.idle_t > 50:
                e.hp = e.max_hp
        else:
            self.idle_t = 0

    def _menu(self, inp):
        m = self.menu
        if not m.page and m.items[m.i] == "DUMMY" and (inp.pressed("left") or inp.pressed("right")):
            self.mode = (self.mode + (1 if inp.pressed("right") else -1)) % len(MODES)
            audio.play("select")
        item = m.update(inp)
        if item == "DUMMY":
            self.mode = (self.mode + 1) % len(MODES)
        elif item == "RESET POSITIONS":
            self._reset()
            m.open = False

    def _reset(self):
        self.projectiles.clear()
        for f, x, face in ((self.p, 115.0, 1), (self.e, 205.0, -1)):
            f.x, f.y, f.vx, f.vy, f.facing = x, float(GROUND_Y), 0.0, 0.0, face
            f.airborne = False
            f.ko = False
            f._to_stand()
            f.hp = f.max_hp

    def _hud(self, surf):
        super()._hud(surf)
        draw_text(surf, "PRACTICE  DUMMY: %s   ENTER: MENU" % MODES[self.mode], W // 2, H - 10,
                  (140, 230, 140), align="center")
        if self.last:
            draw_text(surf, "LAST COMBO: %d HITS  %d DMG" % self.last, W // 2, H - 20,
                      (255, 230, 150), align="center")

    def _draw_menu(self, surf):
        self.menu.draw(surf, "PRACTICE", {"DUMMY": "DUMMY: < %s >" % MODES[self.mode]})
