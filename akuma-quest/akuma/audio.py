"""Synthesised chiptune sound effects (no audio files, no numpy).

If no audio device exists every call is a silent no-op.
"""

import math
import random
from array import array

import pygame

RATE = 22050
_ok = False
_sfx = {}


def init():
    global _ok
    try:
        pygame.mixer.pre_init(RATE, -16, 1, 256)
        pygame.mixer.init(RATE, -16, 1, 256)
        pygame.mixer.set_num_channels(16)
        _ok = True
    except pygame.error:
        _ok = False
        return
    _build_sfx()


def _sound(samples):
    a = array("h", (max(-32767, min(32767, int(v))) for v in samples))
    return pygame.mixer.Sound(buffer=a.tobytes())


def _tone(f0, f1, dur, vol=0.4, wave="square", noise=0.0, duty=0.5):
    n = int(RATE * dur)
    out = []
    ph = 0.0
    rnd = random.Random(int(f0 * 7 + dur * 1000))
    for i in range(n):
        t = i / n
        f = f0 + (f1 - f0) * t
        ph += f / RATE
        p = ph % 1.0
        if wave == "square":
            v = 1.0 if p < duty else -1.0
        elif wave == "tri":
            v = 4 * abs(p - 0.5) - 1
        else:
            v = math.sin(p * math.tau)
        if noise:
            v = v * (1 - noise) + (rnd.random() * 2 - 1) * noise
        env = (1 - t) ** 1.5
        out.append(v * env * vol * 32767)
    return out


def _noise(dur, vol=0.4, decay=2.0, lp=0.5):
    n = int(RATE * dur)
    rnd = random.Random(int(dur * 9999))
    out, prev = [], 0.0
    for i in range(n):
        t = i / n
        prev = prev + (rnd.random() * 2 - 1 - prev) * lp
        out.append(prev * (1 - t) ** decay * vol * 32767)
    return out


def _add(a, b):
    if len(a) < len(b):
        a, b = b, a
    out = list(a)
    for i, v in enumerate(b):
        out[i] += v
    return out


def _build_sfx():
    S = _sfx
    S["hit"] = _sound(_add(_noise(0.12, 0.6, 2.5, 0.6), _tone(180, 60, 0.1, 0.4)))
    S["heavy"] = _sound(_add(_noise(0.22, 0.7, 2.0, 0.4), _tone(140, 40, 0.2, 0.5)))
    S["block"] = _sound(_add(_noise(0.06, 0.4, 3.0, 0.9), _tone(900, 700, 0.05, 0.2)))
    S["whiff"] = _sound(_noise(0.08, 0.25, 1.5, 0.2))
    S["hadouken"] = _sound(_add(_tone(220, 520, 0.18, 0.3, "square", 0.3),
                                _noise(0.25, 0.25, 1.0, 0.15)))
    S["fireball"] = _sound(_tone(300, 500, 0.16, 0.25, "square", 0.4, 0.25))
    S["shoryu"] = _sound(_add(_tone(200, 900, 0.25, 0.3, "square", 0.2), _noise(0.2, 0.2, 1, 0.3)))
    S["dive"] = _sound(_tone(800, 200, 0.12, 0.25, "square", 0.1, 0.25))
    S["sweep"] = _sound(_noise(0.14, 0.35, 1.2, 0.25))
    S["jump"] = _sound(_tone(300, 600, 0.06, 0.15, "square", 0, 0.25))
    S["land"] = _sound(_noise(0.05, 0.25, 3, 0.3))
    S["ko"] = _sound(_add(_tone(400, 50, 0.8, 0.4, "square", 0.2), _noise(0.8, 0.4, 1.2, 0.2)))
    S["select"] = _sound(_tone(660, 990, 0.08, 0.2, "square", 0, 0.25))
    S["encounter"] = _sound(_add(_tone(200, 1200, 0.35, 0.25, "square", 0, 0.5),
                                 _tone(1200, 200, 0.35, 0.15, "tri")))
    S["pickup"] = _sound(_tone(880, 1760, 0.15, 0.25, "square", 0, 0.25))
    S["fight"] = _sound(_tone(440, 880, 0.3, 0.3, "square", 0, 0.5))
    S["step"] = _sound(_noise(0.025, 0.08, 3, 0.2))
    # level 4: bombs and angry cars
    S["boom"] = _sound(_add(_noise(0.5, 0.7, 1.6, 0.25), _tone(110, 30, 0.45, 0.45, "square", 0.3)))
    S["plant"] = _sound(_tone(500, 260, 0.08, 0.2, "square", 0.1, 0.25))
    S["beep"] = _sound(_tone(740, 740, 0.06, 0.12, "square", 0, 0.5))
    S["honk"] = _sound(_add(_tone(330, 320, 0.4, 0.22, "square", 0.05, 0.5),
                            _tone(415, 405, 0.4, 0.18, "square", 0.05, 0.5)))
    S["lights"] = _sound(_tone(1200, 1600, 0.1, 0.15, "tri"))
    _build_mgs(S)       # level 8 (stealth.py): sound-alikes, appended below


def play(name, vol=1.0):
    if not _ok:
        return
    s = _sfx.get(name)
    if s:
        s.set_volume(vol)
        s.play()


# --------------------------------------------------------------------------
# Level 8 (stealth.py): synthesised sound-alikes of the sneaking-game cues
# --------------------------------------------------------------------------
def _seq(*parts):
    out = []
    for p in parts:
        out.extend(p)
    return out


def _rest(dur):
    return [0.0] * int(RATE * dur)


def _build_mgs(S):
    # "!": a bright dissonant stab over a noise crack, gone in a third of a second
    stab = _add(_add(_tone(1175, 1150, 0.34, 0.2, "square", 0, 0.5), _tone(1661, 1630, 0.34, 0.16)),
                _add(_tone(587, 560, 0.34, 0.2, "square", 0, 0.3), _noise(0.12, 0.45, 2.5, 0.8)))
    S["mgs_alert"] = _sound(stab)
    # "?": two soft rising notes
    S["mgs_huh"] = _sound(_seq(_tone(520, 540, 0.09, 0.22, "tri"), _tone(780, 830, 0.16, 0.22, "tri")))
    # codec call: a trilling double ring, twice
    ring = _seq(*[_tone(1320 if i % 2 else 990, 1320 if i % 2 else 990, 0.035, 0.16, "square", 0, 0.5)
                  for i in range(6)])
    S["codec"] = _sound(_seq(ring, _rest(0.08), ring))
    S["codec_beep"] = _sound(_tone(1600, 1600, 0.02, 0.06, "square", 0, 0.5))
    # alert siren: a two-tone wee-oo
    S["alarm"] = _sound(_seq(_tone(960, 960, 0.16, 0.14, "square", 0, 0.5), _tone(720, 720, 0.16, 0.14, "square", 0, 0.5)))
    S["mgs_item"] = _sound(_seq(_tone(660, 660, 0.06, 0.2, "tri"), _tone(880, 880, 0.06, 0.2, "tri"),
                                _tone(1320, 1320, 0.18, 0.22, "tri")))
    S["box_on"] = _sound(_add(_noise(0.1, 0.35, 2.0, 0.15), _tone(160, 90, 0.1, 0.25, "tri")))
    S["box_off"] = _sound(_add(_noise(0.08, 0.3, 2.0, 0.25), _tone(220, 300, 0.08, 0.2, "tri")))
    # evasion / caution phase cue: three falling notes
    S["mgs_evasion"] = _sound(_seq(_tone(880, 880, 0.1, 0.16), _tone(740, 740, 0.1, 0.16),
                                   _tone(587, 560, 0.26, 0.16)))
    S["mgs_clear"] = _sound(_seq(_tone(587, 587, 0.08, 0.14, "tri"), _tone(880, 880, 0.2, 0.14, "tri")))
    S["gunshot"] = _sound(_add(_noise(0.16, 0.7, 3.0, 0.9), _tone(220, 60, 0.08, 0.35, "square", 0.4)))
    S["knock"] = _sound(_seq(_noise(0.03, 0.4, 3, 0.3), _rest(0.07), _noise(0.03, 0.4, 3, 0.3)))


# --------------------------------------------------------------------------
# Level 13 (doom.py): built lazily by DoomScene on first use, so nothing above
# needs to call this.
# --------------------------------------------------------------------------
def _build_doom(S):
    S["doom_door"] = _sound(_add(_noise(0.5, 0.3, 0.6, 0.08), _tone(70, 55, 0.5, 0.25, "square", 0.3)))
    S["doom_locked"] = _sound(_seq(_tone(160, 120, 0.12, 0.3, "square", 0.2), _tone(120, 90, 0.16, 0.3, "square", 0.2)))
    S["doom_oof"] = _sound(_tone(140, 90, 0.12, 0.3, "square", 0.3))
    S["doom_ouch"] = _sound(_add(_tone(260, 150, 0.16, 0.3, "square", 0.35), _noise(0.1, 0.3, 2, 0.5)))
    S["doom_pain"] = _sound(_tone(420, 180, 0.18, 0.28, "square", 0.45, 0.3))
    S["doom_die"] = _sound(_add(_tone(380, 60, 0.6, 0.3, "square", 0.4, 0.3), _noise(0.5, 0.3, 1.5, 0.3)))
    S["doom_sight"] = _sound(_seq(_tone(200, 330, 0.12, 0.22, "square", 0.4), _tone(330, 150, 0.22, 0.22, "square", 0.4)))
    S["doom_imp"] = _sound(_add(_noise(0.3, 0.35, 1.2, 0.2), _tone(500, 250, 0.25, 0.15, "tri")))
    S["doom_boom"] = _sound(_add(_noise(0.35, 0.5, 1.8, 0.3), _tone(160, 50, 0.3, 0.3, "square", 0.3)))
    S["doom_charge"] = _sound(_tone(150, 900, 0.3, 0.25, "square", 0.25, 0.3))
    S["doom_shinku"] = _sound(_add(_tone(110, 700, 0.45, 0.3, "square", 0.3), _noise(0.5, 0.35, 0.8, 0.12)))
    S["doom_item"] = _sound(_tone(990, 1320, 0.08, 0.2, "square", 0, 0.25))
    S["doom_key"] = _sound(_seq(_tone(660, 660, 0.07, 0.2), _tone(990, 990, 0.07, 0.2), _tone(1320, 1320, 0.14, 0.2)))
    S["doom_secret"] = _sound(_seq(_tone(523, 523, 0.1, 0.2, "tri"), _tone(784, 784, 0.1, 0.2, "tri"),
                                   _tone(1047, 1047, 0.25, 0.2, "tri")))
    S["doom_roar"] = _sound(_add(_tone(90, 60, 1.0, 0.35, "square", 0.5, 0.3), _noise(1.0, 0.35, 1.0, 0.1)))
    S["doom_bossdie"] = _sound(_add(_tone(300, 30, 1.6, 0.4, "square", 0.4), _noise(1.6, 0.5, 0.9, 0.15)))
    S["doom_death"] = _sound(_seq(_tone(300, 200, 0.25, 0.3, "square", 0.3), _tone(200, 60, 0.6, 0.3, "square", 0.3)))
    S["doom_portal"] = _sound(_add(_tone(200, 1600, 0.9, 0.2, "tri"), _tone(400, 3200, 0.9, 0.08, "square", 0, 0.25)))
    S["doom_rip"] = _sound(_seq(_tone(110, 110, 0.15, 0.35, "square", 0.2), _rest(0.05),
                                _tone(110, 110, 0.15, 0.35, "square", 0.2), _tone(147, 140, 0.45, 0.35, "square", 0.2)))
