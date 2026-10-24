"""Gamepad input test with a fake Xbox pad (no hardware needed).

    python tests/pad_test.py
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from akuma import inputs  # noqa: E402
from akuma.game import Game, Title  # noqa: E402


class FakeJoy:
    def __init__(self, iid):
        self.iid = iid

    def get_instance_id(self):
        return self.iid


class FakePad:
    """Stands in for pygame._sdl2.controller.Controller."""

    def __init__(self, iid):
        self.iid, self.buttons, self.axes, self.plugged = iid, set(), {}, True

    def as_joystick(self):
        return FakeJoy(self.iid)

    def attached(self):
        return self.plugged

    def get_button(self, b):
        return b in self.buttons

    def get_axis(self, a):
        return self.axes.get(a, 0)


class FakeCtrlModule:
    def __init__(self):
        self.devices = []            # device index -> FakePad

    def is_controller(self, i):
        return True

    def Controller(self, i):
        return self.devices[i]


def frame(game, events=()):
    inp = game.input
    inp.new_frame()
    for ev in events:
        inp.handle(ev)
    inp.poll()
    game.scene.update(inp)
    game.scene.draw(game.canvas)


def tap(game, pad, button):
    pad.buttons.add(button)
    frame(game, [pygame.event.Event(pygame.CONTROLLERBUTTONDOWN, instance_id=pad.iid, button=button)])
    pad.buttons.discard(button)
    frame(game)


def test_pad():
    game = Game(headless=True)
    inp = game.input
    assert not inp.pad_connected
    frame(game)

    # hot-plug: a pad shows up mid-session
    fake = FakeCtrlModule()
    real, inputs._ctrl = inputs._ctrl, fake
    try:
        pad = FakePad(7)
        fake.devices.append(pad)
        frame(game, [pygame.event.Event(pygame.JOYDEVICEADDED, device_index=0)])
        assert inp.pad_connected and 7 in inp.pads
        # the same pad announced twice (startup scan + event) is still one pad
        inp.handle(pygame.event.Event(pygame.JOYDEVICEADDED, device_index=0))
        assert len(inp.pads) == 1
    finally:
        inputs._ctrl = real

    # title menu: d-pad down moves the cursor, View jumps to QUIT instead of quitting
    assert isinstance(game.scene, Title)
    for _ in range(20):
        frame(game)
    tap(game, pad, pygame.CONTROLLER_BUTTON_DPAD_DOWN)
    assert game.scene.i == 1, game.scene.i
    tap(game, pad, pygame.CONTROLLER_BUTTON_DPAD_UP)
    assert game.scene.i == 0
    tap(game, pad, pygame.CONTROLLER_BUTTON_BACK)
    assert game.running and game.scene.ITEMS[game.scene.i] == "QUIT"
    tap(game, pad, pygame.CONTROLLER_BUTTON_DPAD_DOWN)     # wraps back to START GAME

    # stick: a push past the deadzone is held and counts as a press on the first frame
    pad.axes[pygame.CONTROLLER_AXIS_LEFTX] = 30000
    frame(game)
    assert inp.held("right") and inp.pressed("right")
    frame(game)
    assert inp.held("right") and not inp.pressed("right")
    pad.axes[pygame.CONTROLLER_AXIS_LEFTX] = 9000          # inside the deadzone
    frame(game)
    assert not inp.held("right")
    pad.axes.clear()

    # A starts the game
    assert game.scene.ITEMS[game.scene.i] == "START GAME"
    tap(game, pad, pygame.CONTROLLER_BUTTON_A)
    assert not isinstance(game.scene, Title), game.scene

    # buttons map to the arcade actions; held state comes from polling
    for b, act in ((pygame.CONTROLLER_BUTTON_X, "punch"), (pygame.CONTROLLER_BUTTON_A, "kick"),
                   (pygame.CONTROLLER_BUTTON_B, "special"), (pygame.CONTROLLER_BUTTON_Y, "special"),
                   (pygame.CONTROLLER_BUTTON_LEFTSHOULDER, "punch"),
                   (pygame.CONTROLLER_BUTTON_RIGHTSHOULDER, "kick")):
        pad.buttons.add(b)
        inp.new_frame()
        inp.handle(pygame.event.Event(pygame.CONTROLLERBUTTONDOWN, instance_id=7, button=b))
        inp.poll()
        assert inp.pressed(act) and inp.held(act), act
        pad.buttons.clear()
        inp.new_frame()
        inp.poll()
        assert not inp.held(act)

    # triggers = shield
    pad.axes[pygame.CONTROLLER_AXIS_TRIGGERRIGHT] = 32000
    inp.new_frame(); inp.poll()
    assert inp.pressed("shield") and inp.held("shield")
    pad.axes.clear()
    inp.new_frame(); inp.poll()
    assert not inp.held("shield")

    # Start opens the pause menu in a level, View resumes
    tap(game, pad, pygame.CONTROLLER_BUTTON_START)
    menu = getattr(game.scene, "menu", None)
    assert menu is not None and menu.open, "start should pause"
    tap(game, pad, pygame.CONTROLLER_BUTTON_BACK)
    assert not menu.open, "view should resume"

    # raw joystick events from a game controller are ignored (no double presses)
    inp.new_frame()
    inp.handle(pygame.event.Event(pygame.JOYBUTTONDOWN, instance_id=7, button=10))
    inp.poll()
    assert not inp._pressed

    # unplugging: removed on the event, and the keyboard still works
    inp.handle(pygame.event.Event(pygame.CONTROLLERDEVICEREMOVED, instance_id=7))
    assert not inp.pad_connected
    inp.new_frame()
    inp.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j, mod=0, unicode="j", scancode=0))
    inp.poll()
    assert inp.pressed("punch")

    # a pad that drops out without an event is noticed on the next poll
    pad.plugged = False
    inp.pads[7] = pad
    inp.new_frame(); inp.poll()
    assert not inp.pad_connected
    pygame.quit()
    print("pad test OK")


if __name__ == "__main__":
    test_pad()
