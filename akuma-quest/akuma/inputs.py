"""Keyboard + gamepad input mapped to a few arcade actions.

The game uses four directions, three attack buttons (punch, kick, special)
and start/back.
Held state is polled once per frame so movement responds on the very next
frame; presses are latched from events so a tap is never missed.
"""

import pygame

KEYMAP = {
    "up": (pygame.K_UP, pygame.K_w),
    "down": (pygame.K_DOWN, pygame.K_s),
    "left": (pygame.K_LEFT, pygame.K_a),
    "right": (pygame.K_RIGHT, pygame.K_d),
    "punch": (pygame.K_j, pygame.K_z),
    "kick": (pygame.K_k, pygame.K_x),
    "special": (pygame.K_l, pygame.K_c, pygame.K_SPACE),
    "shield": (pygame.K_i,),
    "start": (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_p),
    "back": (pygame.K_ESCAPE,),
    "controls": (pygame.K_F1, pygame.K_TAB),
}
KEY_TO_ACTION = {k: a for a, ks in KEYMAP.items() for k in ks}

# Xbox / XInput layout: X punch, A kick, B or Y special, LB punch, RB kick.
JOY_BUTTONS = {2: "punch", 0: "kick", 1: "special", 3: "special", 4: "punch", 5: "kick",
               6: "back", 7: "start", 10: "shield", 8: "back", 9: "start"}
ATTACKS = ("punch", "kick", "special")
DIRECTIONS = ("up", "down", "left", "right")
DEADZONE = 0.45


class Input:
    def __init__(self):
        self._pressed = set()
        self._held = set()
        self.virtual = set()          # held actions injected by tests / bots
        self.virtual_pressed = set()
        self.joysticks = {}
        try:
            for i in range(pygame.joystick.get_count()):
                self._add_joy(i)
        except pygame.error:
            pass

    def _add_joy(self, index):
        try:
            j = pygame.joystick.Joystick(index)
            j.init()
            self.joysticks[j.get_instance_id()] = j
        except (pygame.error, AttributeError):
            pass

    def new_frame(self):
        self._pressed = set(self.virtual_pressed)
        self.virtual_pressed = set()

    def handle(self, ev):
        if ev.type == pygame.KEYDOWN:
            a = KEY_TO_ACTION.get(ev.key)
            if a:
                self._pressed.add(a)
        elif ev.type == pygame.JOYBUTTONDOWN:
            a = JOY_BUTTONS.get(ev.button)
            if a:
                self._pressed.add(a)
        elif ev.type == pygame.JOYHATMOTION:
            x, y = ev.value
            for a, on in (("left", x < 0), ("right", x > 0), ("up", y > 0), ("down", y < 0)):
                if on:
                    self._pressed.add(a)
        elif ev.type == getattr(pygame, "JOYDEVICEADDED", -1):
            self._add_joy(ev.device_index)
        elif ev.type == getattr(pygame, "JOYDEVICEREMOVED", -1):
            self.joysticks.pop(ev.instance_id, None)

    def poll(self):
        keys = pygame.key.get_pressed()
        held = set(self.virtual)
        for a, ks in KEYMAP.items():
            if any(keys[k] for k in ks):
                held.add(a)
        for j in self.joysticks.values():
            try:
                if j.get_numhats():
                    x, y = j.get_hat(0)
                    if x < 0: held.add("left")
                    if x > 0: held.add("right")
                    if y > 0: held.add("up")
                    if y < 0: held.add("down")
                if j.get_numaxes() >= 2:
                    ax, ay = j.get_axis(0), j.get_axis(1)
                    if ax < -DEADZONE: held.add("left")
                    if ax > DEADZONE: held.add("right")
                    if ay < -DEADZONE: held.add("up")
                    if ay > DEADZONE: held.add("down")
                for b, a in JOY_BUTTONS.items():
                    if b < j.get_numbuttons() and j.get_button(b):
                        held.add(a)
            except pygame.error:
                pass
        # a direction that became held this frame counts as pressed
        for a in DIRECTIONS:
            if a in held and a not in self._held:
                self._pressed.add(a)
        self._held = held

    def held(self, a):
        return a in self._held

    def pressed(self, a):
        return a in self._pressed

    def any_pressed(self, *acts):
        return any(a in self._pressed for a in acts)
