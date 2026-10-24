"""Main loop and the screens around a run (title menu, level clear, game over)."""

import random
import sys

import pygame

from . import audio
from .akuma_sprites import AkumaArt
from .art import make_stage
from .config import W, H, FPS, TITLE, AKUMA_MAX_HP
from .dungeon import Overworld, LEVELS
from .fight import FightScene, CONTROLS
from .pause import PauseMenu, MAP_LINE
from .cars import CarScene
from .font import draw_text
from .inputs import Input
from .practice import PracticeScene

LAST_LEVEL = max(LEVELS)


class Title:
    # LEVEL SELECT is a debug shortcut (Toshi asked for it while testing; easy to drop later)
    ITEMS = ["START GAME", "PRACTICE", "LEVEL SELECT", "QUIT"]

    def __init__(self, game):
        self.game = game
        self.t = 0
        self.i = 0
        self.pick = 1
        self.controls = PauseMenu(game, [MAP_LINE] + CONTROLS)
        self.bg = make_stage(0)
        img = AkumaArt().frame("idle0")
        self.akuma = pygame.transform.scale(img, (img.get_width() * 2, img.get_height() * 2))

    def update(self, inp):
        self.t += 1
        if self.controls.page == "controls":
            self.controls.update(inp)
            return
        if inp.pressed("controls"):
            self.controls.page = "controls"
            return
        if inp.pressed("up"):
            self.i = (self.i - 1) % len(self.ITEMS)
            audio.play("select")
        if inp.pressed("down"):
            self.i = (self.i + 1) % len(self.ITEMS)
            audio.play("select")
        if self.ITEMS[self.i] == "LEVEL SELECT" and (inp.pressed("left") or inp.pressed("right")):
            self.pick = (self.pick - 1 + (1 if inp.pressed("right") else -1)) % LAST_LEVEL + 1
            audio.play("select")
        if self.t > 15 and inp.any_pressed("start", "punch", "kick", "special"):
            audio.play("select")
            choice = self.ITEMS[self.i]
            if choice == "START GAME":
                self.game.new_run()
            elif choice == "LEVEL SELECT":
                self.game.new_run(start=self.pick)
            elif choice == "PRACTICE":
                self.game.scene = PracticeScene(self.game)
            else:
                self.game.running = False
        elif inp.pressed("back"):
            # a pad's View button only jumps to QUIT, so one stray press can't close the game
            if "back" in inp.pad_pressed and self.ITEMS[self.i] != "QUIT":
                self.i = self.ITEMS.index("QUIT")
                audio.play("select")
            else:
                self.game.running = False

    def draw(self, surf):
        surf.blit(self.bg, (0, 0))
        bob = (self.t // 30) % 2
        surf.blit(self.akuma, (250 - self.akuma.get_width() // 2, 160 - self.akuma.get_height() + bob))
        cx = 92
        draw_text(surf, "AKUMA", cx, 26, (255, 50, 40), scale=4, align="center")
        draw_text(surf, "QUEST", cx, 56, (255, 220, 160), scale=2, align="center")
        for k, item in enumerate(self.ITEMS):
            sel = k == self.i
            col = (255, 230, 90) if sel else (200, 190, 210)
            if item == "LEVEL SELECT":
                item = "LEVEL < %d >" % self.pick
                col = (140, 220, 255) if sel else (130, 150, 170)
            draw_text(surf, ("> %s <" if sel else "%s") % item, cx, 80 + k * 13, col, align="center")
        # the picked level's name, so you know what you're starting
        sel = self.ITEMS[self.i] == "LEVEL SELECT"
        draw_text(surf, LEVELS[self.pick]["name"], cx, 131, (255, 200, 120) if sel else (120, 120, 140),
                  align="center")
        if self.game.input.pad_connected:
            draw_text(surf, "CONTROLLER READY", cx, 143, (140, 220, 255), align="center")
            draw_text(surf, "X PUNCH  A KICK  B SPECIAL", cx, 154, (170, 160, 185), align="center")
            draw_text(surf, "START: PAUSE   RT: SHIELD", cx, 165, (170, 160, 185), align="center")
        else:
            draw_text(surf, "MOVE: ARROWS / WASD", cx, 143, (170, 160, 185), align="center")
            draw_text(surf, "J PUNCH  K KICK  L SPECIAL", cx, 154, (170, 160, 185), align="center")
            draw_text(surf, "ESC: PAUSE   F1: CONTROLS", cx, 165, (170, 160, 185), align="center")
        if self.controls.page == "controls":
            self.controls.draw(surf)


class LevelClear:
    def __init__(self, game, level):
        self.game = game
        self.level = level
        self.t = 0

    def update(self, inp):
        self.t += 1
        if self.t > 45 and inp.any_pressed("start", "punch", "kick", "special"):
            audio.play("select")
            self.game.start_level(self.level + 1)

    def draw(self, surf):
        surf.fill((20, 10, 30))
        draw_text(surf, "LEVEL %d CLEAR!" % self.level, W // 2, 34, (255, 220, 60), scale=3, align="center")
        draw_text(surf, "%s HAS FALLEN" % LEVELS[self.level]["boss_name"], W // 2, 70, (255, 255, 255),
                  align="center")
        nxt = LEVELS[self.level + 1]
        draw_text(surf, "NEXT: LEVEL %d" % (self.level + 1), W // 2, 100, (200, 190, 210), align="center")
        draw_text(surf, nxt["name"], W // 2, 112, (255, 160, 120), align="center")
        draw_text(surf, "AKUMA'S HEALTH IS RESTORED", W // 2, 130, (140, 230, 140), align="center")
        if self.t > 45 and (self.t // 30) % 2 == 0:
            draw_text(surf, "PRESS ENTER", W // 2, 158, (255, 230, 150), align="center")


class EndScreen:
    def __init__(self, game, won, stats):
        self.game = game
        self.won = won
        self.stats = stats
        self.t = 0

    def update(self, inp):
        self.t += 1
        if self.t > 60 and inp.any_pressed("start", "punch", "kick", "special"):
            audio.play("select")
            self.game.new_run()
        elif self.t > 30 and inp.pressed("back"):
            self.game.to_title()

    def draw(self, surf):
        surf.fill((14, 6, 12) if not self.won else (20, 10, 30))
        if self.won:
            draw_text(surf, "QUEST COMPLETE!", W // 2, 30, (255, 220, 60), scale=2, align="center")
            draw_text(surf, "EVERY DEMON HAS FALLEN TO AKUMA", W // 2, 64, (255, 255, 255), align="center")
        else:
            draw_text(surf, "GAME OVER", W // 2, 30, (255, 50, 40), scale=3, align="center")
            draw_text(surf, "AKUMA HAS FALLEN", W // 2, 64, (255, 255, 255), align="center")
        y = 86
        for k, v in self.stats:
            draw_text(surf, k, W // 2 - 70, y, (180, 170, 200))
            draw_text(surf, str(v), W // 2 + 70, y, (255, 255, 255), align="right")
            y += 11
        if self.t > 60 and (self.t // 30) % 2 == 0:
            draw_text(surf, "ENTER: NEW RUN   ESC: TITLE", W // 2, 160, (255, 230, 150), align="center")


class Game:
    def __init__(self, fullscreen=False, headless=False):
        audio.init()
        pygame.init()
        pygame.display.set_caption(TITLE)
        flags = pygame.SCALED
        if fullscreen:
            flags |= pygame.FULLSCREEN
        try:
            self.screen = pygame.display.set_mode((W, H), flags, vsync=1)
        except pygame.error:
            self.screen = pygame.display.set_mode((W, H), flags)
        self.canvas = self.screen
        self.clock = pygame.time.Clock()
        self.input = Input()
        self.running = True
        self.overworld = None
        self.akuma_max = AKUMA_MAX_HP
        self.power = 1.0
        self.kills = 0
        self.fights = 0
        self.frames = 0
        self.show_fps = False
        self.level = 1
        self.seed = 0
        self.scene = Title(self)

    # ---- flow --------------------------------------------------------
    def to_title(self):
        self.overworld = None
        self.scene = Title(self)

    def new_run(self, seed=None, start=1):
        self.akuma_max = AKUMA_MAX_HP
        self.power = 1.0
        self.kills = 0
        self.fights = 0
        self.run_frames = 0
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.start_level(start)

    # whole-level scenes (no overworld): mode -> (module, class)
    SCENES = {"bomber": ("bomber", "BomberScene"),
              "smash": ("smash", "SmashScene"), "stealth": ("stealth", "StealthScene"),
              "skate": ("skate", "SkateScene"), "connect4": ("connect4", "Connect4Scene"),
              "metroid": ("metroid", "MetroidScene"), "thunder": ("thunder", "ThunderScene"),
              "climb": ("climb", "ClimbScene"), "doom": ("doom", "DoomScene")}

    def start_level(self, level):
        self.level = level
        mode = LEVELS[level].get("mode")
        if mode:
            import importlib
            mod, cls = self.SCENES[mode]
            scene = getattr(importlib.import_module("akuma." + mod), cls)(self, self.seed + level * 1000, level)
            # the stealth base is a map you return to after its gunfights
            self.overworld = scene if mode == "stealth" else None
            self.scene = scene
            return
        self.overworld = Overworld(self, self.seed + level * 1000, level)
        self.scene = self.overworld

    def level_done(self, scene, hp):
        """A whole-level scene (bomber, smash, ...) was cleared."""
        if self.level < LAST_LEVEL:
            self.scene = LevelClear(self, self.level)
        else:
            self.scene = EndScreen(self, True, self._stats())

    def level_failed(self, scene):
        self.scene = EndScreen(self, False, self._stats())

    def start_fight(self, enemy, hp, ambush):
        self.fights += 1
        if getattr(enemy, "car", False):
            self.scene = CarScene(self, enemy, hp, self.akuma_max, self.power, seed=self.seed + self.fights)
            return
        cfg = LEVELS[self.level]
        seed = self.seed + self.fights
        self.scene = FightScene(self, enemy, hp, self.akuma_max, self.power, ambush, seed=seed)

    def end_fight(self, fight, result, hp):
        enemy = fight.enemy_ref
        if result == "escape":
            self.overworld.after_fight(result, hp, enemy)
            self.scene = self.overworld
            return
        if result == "win":
            self.kills += 1
            if enemy.boss:
                if self.level < LAST_LEVEL:
                    self.scene = LevelClear(self, self.level)
                else:
                    self.scene = EndScreen(self, True, self._stats())
                return
            self.overworld.after_fight(result, hp, enemy)
            self.scene = self.overworld
        else:
            self.scene = EndScreen(self, False, self._stats())

    def _stats(self):
        secs = getattr(self, "run_frames", 0) // FPS
        return [("LEVEL REACHED", self.level), ("FOES DEFEATED", self.kills), ("FIGHTS", self.fights),
                ("TIME", "%d:%02d" % (secs // 60, secs % 60)), ("SEED", self.seed)]

    # ---- loop --------------------------------------------------------
    def tick(self):
        inp = self.input
        inp.new_frame()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_F11:
                pygame.display.toggle_fullscreen()
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_F3:
                self.show_fps = not self.show_fps
            inp.handle(ev)
        inp.poll()
        self.scene.update(inp)
        if self.scene is self.overworld or getattr(self.scene, "paused", None) is False:
            self.run_frames = getattr(self, "run_frames", 0) + 1
        self.scene.draw(self.canvas)
        if self.show_fps:
            draw_text(self.canvas, "%d FPS" % round(self.clock.get_fps()), W - 4, H - 10,
                      (120, 255, 120), align="right")
        pygame.display.flip()
        self.frames += 1

    def run(self):
        while self.running:
            self.tick()
            self.clock.tick_busy_loop(FPS)
        pygame.quit()


def main():
    fullscreen = "--fullscreen" in sys.argv
    Game(fullscreen=fullscreen).run()
