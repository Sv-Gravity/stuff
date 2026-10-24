"""Keyboard + gamepad input mapped to a few arcade actions.

The game uses four directions, three attack buttons (punch, kick, special)
and start/back.
Held state is polled once per frame so movement responds on the very next
frame; presses are latched from events so a tap is never missed.

Gamepads: an Xbox (or any SDL "game controller") pad is opened through SDL's
GameController API, so the buttons are the same on every OS and driver.
Pads are picked up whenever they are plugged in, before or during play, and
the keyboard keeps working alongside them. Anything SDL doesn't know as a
game controller falls back to a plain joystick with a best-guess layout.
"""

import pygame

try:
    from pygame._sdl2 import controller as _ctrl
except ImportError:                    # very old pygame / builds without it
    _ctrl = None

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

# Xbox layout: X punch, A kick, B special, Y special, LB punch, RB kick,
# LT / RT / left stick click shield, Start pause, View (back) = Esc, d-pad / left stick move.
PAD_BUTTONS = {}
if _ctrl is not None:
    PAD_BUTTONS = {
        pygame.CONTROLLER_BUTTON_X: "punch", pygame.CONTROLLER_BUTTON_A: "kick",
        pygame.CONTROLLER_BUTTON_B: "special", pygame.CONTROLLER_BUTTON_Y: "special",
        pygame.CONTROLLER_BUTTON_LEFTSHOULDER: "punch",
        pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: "kick",
        pygame.CONTROLLER_BUTTON_LEFTSTICK: "shield",
        pygame.CONTROLLER_BUTTON_START: "start", pygame.CONTROLLER_BUTTON_BACK: "back",
        pygame.CONTROLLER_BUTTON_DPAD_UP: "up", pygame.CONTROLLER_BUTTON_DPAD_DOWN: "down",
        pygame.CONTROLLER_BUTTON_DPAD_LEFT: "left", pygame.CONTROLLER_BUTTON_DPAD_RIGHT: "right",
    }
# raw joystick fallback, numbered like XInput on Windows: A0 B1 X2 Y3 LB4 RB5 View6 Start7
JOY_BUTTONS = {2: "punch", 0: "kick", 1: "special", 3: "special", 4: "punch", 5: "kick",
               6: "back", 7: "start", 8: "shield"}
PAD_LEGEND = "PAD  X:PUNCH  A:KICK  B:SPECIAL  RT:SHIELD (I)"
ATTACKS = ("punch", "kick", "special")
DIRECTIONS = ("up", "down", "left", "right")
DEADZONE = 0.45
TRIGGER = 0.5


def _stick(held, x, y):
    if x < -DEADZONE: held.add("left")
    if x > DEADZONE: held.add("right")
    if y < -DEADZONE: held.add("up")
    if y > DEADZONE: held.add("down")


class Input:
    def __init__(self):
        self._pressed = set()
        self._held = set()
        self._pad_held = set()
        self.virtual = set()          # held actions injected by tests / bots
        self.virtual_pressed = set()
        self.pad_pressed = set()      # this frame's presses that came from a pad
        self.pads = {}                # instance id -> Controller
        self.joysticks = {}           # instance id -> Joystick (non game-controller devices)
        if _ctrl is not None:
            try:
                _ctrl.init()
            except pygame.error:
                pass
        self.scan()

    # ---- devices -----------------------------------------------------
    @property
    def pad_connected(self):
        return bool(self.pads or self.joysticks)

    def scan(self):
        """Open every attached pad we don't have yet (startup and hot-plug)."""
        try:
            n = pygame.joystick.get_count()
        except pygame.error:
            return
        for i in range(n):
            self._add(i)

    def _add(self, index):
        try:
            if _ctrl is not None and _ctrl.is_controller(index):
                c = _ctrl.Controller(index)
                iid = c.as_joystick().get_instance_id()
                if iid not in self.pads:
                    self.pads[iid] = c
                self.joysticks.pop(iid, None)
                return
            j = pygame.joystick.Joystick(index)
            j.init()
            iid = j.get_instance_id()
            if iid not in self.pads:
                self.joysticks[iid] = j
        except (pygame.error, AttributeError, IndexError):
            pass

    def _remove(self, iid):
        self.pads.pop(iid, None)
        self.joysticks.pop(iid, None)

    # ---- per frame ---------------------------------------------------
    def new_frame(self):
        self._pressed = set(self.virtual_pressed)
        self.virtual_pressed = set()
        self.pad_pressed = set()

    def _pad_press(self, a):
        if a:
            self._pressed.add(a)
            self.pad_pressed.add(a)

    def handle(self, ev):
        t = ev.type
        if t == pygame.KEYDOWN:
            a = KEY_TO_ACTION.get(ev.key)
            if a:
                self._pressed.add(a)
        elif t == getattr(pygame, "CONTROLLERBUTTONDOWN", -1):
            if getattr(ev, "instance_id", None) in self.pads:
                self._pad_press(PAD_BUTTONS.get(ev.button))
        elif t == pygame.JOYBUTTONDOWN:
            # a game controller also sends raw joystick events; only use those for other pads
            if getattr(ev, "instance_id", None) in self.joysticks:
                self._pad_press(JOY_BUTTONS.get(ev.button))
        elif t == pygame.JOYHATMOTION:
            if getattr(ev, "instance_id", None) in self.joysticks:
                x, y = ev.value
                for a, on in (("left", x < 0), ("right", x > 0), ("up", y > 0), ("down", y < 0)):
                    if on:
                        self._pad_press(a)
        elif t == getattr(pygame, "JOYDEVICEADDED", -1):
            self._add(ev.device_index)
        elif t in (getattr(pygame, "JOYDEVICEREMOVED", -1), getattr(pygame, "CONTROLLERDEVICEREMOVED", -1)):
            self._remove(getattr(ev, "instance_id", None))

    def _poll_pads(self):
        held = set()
        for iid, c in list(self.pads.items()):
            try:
                if not c.attached():
                    self._remove(iid)
                    continue
                for b, a in PAD_BUTTONS.items():
                    if c.get_button(b):
                        held.add(a)
                _stick(held, c.get_axis(pygame.CONTROLLER_AXIS_LEFTX) / 32767,
                       c.get_axis(pygame.CONTROLLER_AXIS_LEFTY) / 32767)
                if max(c.get_axis(pygame.CONTROLLER_AXIS_TRIGGERLEFT),
                       c.get_axis(pygame.CONTROLLER_AXIS_TRIGGERRIGHT)) > TRIGGER * 32767:
                    held.add("shield")
            except pygame.error:
                self._remove(iid)
        for iid, j in list(self.joysticks.items()):
            try:
                if j.get_numhats():
                    x, y = j.get_hat(0)
                    _stick(held, x, -y)
                if j.get_numaxes() >= 2:
                    _stick(held, j.get_axis(0), j.get_axis(1))
                if j.get_numaxes() >= 6:      # XInput triggers rest at -1
                    if max(j.get_axis(4), j.get_axis(5)) > 0:
                        held.add("shield")
                for b, a in JOY_BUTTONS.items():
                    if b < j.get_numbuttons() and j.get_button(b):
                        held.add(a)
            except pygame.error:
                self._remove(iid)
        return held

    def poll(self):
        keys = pygame.key.get_pressed()
        held = set(self.virtual)
        for a, ks in KEYMAP.items():
            if any(keys[k] for k in ks):
                held.add(a)
        pad = self._poll_pads()
        # stick pushes and trigger pulls have no button event: count the edge as a press
        for a in pad - self._pad_held:
            self._pad_press(a)
        self._pad_held = pad
        held |= pad
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
