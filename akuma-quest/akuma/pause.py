"""The pause menu shared by the map and every fight: resume, a controls page,
and a way back to the main menu."""

import pygame

from . import audio
from .config import W, H
from .font import draw_text
from .inputs import PAD_LEGEND

MAP_LINE = "MAP: ARROWS / WASD, TOUCH ENEMIES TO FIGHT"


class PauseMenu:
    ITEMS = ["RESUME", "CONTROLS", "BACK TO MAIN MENU"]

    def __init__(self, game, controls, extra_items=(), confirm_quit=True):
        self.game = game
        self.confirm_quit = confirm_quit
        self.controls = controls          # lines for the controls page
        self.items = list(extra_items) + self.ITEMS
        self.open = False
        self.i = 0
        self.page = None                  # None | "controls" | "confirm"

    def toggle(self, inp):
        """Call every frame; returns True while the game should stay frozen."""
        if not self.open:
            if inp.pressed("start") or inp.pressed("back"):
                self.open, self.i, self.page = True, 0, None
                audio.play("select")
            elif inp.pressed("controls"):
                self.open, self.i, self.page = True, 0, "controls"
                audio.play("select")
            return self.open
        return True

    def update(self, inp):
        """Returns the chosen item (or None) and handles the sub pages itself."""
        confirm = inp.any_pressed("start", "punch", "kick", "special")
        if self.page == "controls":
            if confirm or inp.pressed("back") or inp.pressed("controls"):
                self.page = None
                audio.play("select")
            return None
        if self.page == "confirm":
            if inp.pressed("left") or inp.pressed("right") or inp.pressed("up") or inp.pressed("down"):
                self.yes = not self.yes
                audio.play("select")
            if inp.pressed("back"):
                self.page = None
            elif confirm:
                audio.play("select")
                if self.yes:
                    self.open = False
                    self.game.to_title()
                    return "title"
                self.page = None
            return None
        if inp.pressed("up"):
            self.i = (self.i - 1) % len(self.items)
            audio.play("select")
        if inp.pressed("down"):
            self.i = (self.i + 1) % len(self.items)
            audio.play("select")
        if inp.pressed("back"):
            self.open = False
            audio.play("select")
            return "RESUME"
        if inp.pressed("controls"):
            self.page = "controls"
            return None
        if confirm:
            item = self.items[self.i]
            audio.play("select")
            if item == "RESUME":
                self.open = False
            elif item == "CONTROLS":
                self.page = "controls"
            elif item == "BACK TO MAIN MENU":
                if not self.confirm_quit:
                    self.open = False
                    self.game.to_title()
                    return "title"
                self.page = "confirm"
                self.yes = False
            return item
        return None

    def draw(self, surf, title="PAUSED", labels=None):
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        s.fill((0, 0, 0, 170))
        surf.blit(s, (0, 0))
        if self.page == "controls":
            draw_text(surf, "CONTROLS", W // 2, 10, (255, 255, 255), scale=2, align="center")
            if getattr(getattr(self.game, "input", None), "pad_connected", False):
                draw_text(surf, PAD_LEGEND, W // 2, 25, (140, 220, 255), align="center")
            for k, line in enumerate(self.controls):
                draw_text(surf, line, W // 2, 34 + k * 11, (210, 210, 230), align="center")
            draw_text(surf, "ANY BUTTON: BACK", W // 2, H - 12, (255, 230, 150), align="center")
            return
        if self.page == "confirm":
            draw_text(surf, "QUIT TO THE MAIN MENU?", W // 2, 60, (255, 255, 255), scale=1, align="center")
            draw_text(surf, "THIS RUN WILL BE LOST", W // 2, 74, (255, 120, 100), align="center")
            for k, opt in enumerate(("NO", "YES")):
                sel = (k == 1) == self.yes
                draw_text(surf, ("> %s <" if sel else "%s") % opt, W // 2 - 30 + k * 60, 96,
                          (255, 230, 90) if sel else (190, 180, 200), align="center")
            return
        draw_text(surf, title, W // 2, 40, (255, 255, 255), scale=3, align="center")
        for k, item in enumerate(self.items):
            label = (labels or {}).get(item, item)
            sel = k == self.i
            draw_text(surf, ("> %s <" if sel else "%s") % label, W // 2, 76 + k * 13,
                      (255, 230, 90) if sel else (190, 180, 200), align="center")
        hint = "VIEW: RESUME" if getattr(getattr(self.game, "input", None), "pad_connected", False) else "F1 / TAB: CONTROLS"
        draw_text(surf, hint, W // 2, 82 + len(self.items) * 13, (150, 150, 170),
                  align="center")
