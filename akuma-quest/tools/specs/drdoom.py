"""Dr. Doom, from Toshi's "Doom Pocket Fighter" sheet (art_source/drdoom_sheet.png).

That sheet is painted on paper with labels, so tools/make_drdoom.py first cuts
it into art_source/sprites/DrDoom.png, one strip per animation:
 0 idle(4)  1 walk(4)  2 crouch(3)  3 jump(4)  4 air jump(3)  5 dash(3)
 6 light punch(3)  7 light kick(2)  8 strong punch(2)  9 strong kick(2)
10 fireball pose(3)  11 teleport(3, 1 = green ghost)  12 hellfire(2)
13 hit/stun(4: 2 = halo, 3 = knocked down)  14 win  15 lose  16 fireball(4)
Poses the sheet has no drawing for borrow the nearest one: teleport is his
intro, hellfire his spinning special (tatsu / lariat), the win pose's raised
fist his rising uppercut. Re-run: python tools/make_drdoom.py
"""
from specs import R, F

SPEC = dict(
    sheet="DrDoom.png",
    projectile=R(16, 0, 3), projectile_scale=1.0,
    poses={
        "idle": (R(0, 0, 3) + F("0.2", "0.1"), 7, True),
        "walk": (R(1, 0, 3), 7, True),
        "walk_back": (R(1, 3, 0), 7, True),
        "dash": (R(5, 0, 2), 4, True),
        "crouch": (R(2, 0, 2) + F("2.1"), 7, "loop1"),
        "block": (F("13.0"), 3, False),
        "crouch_block": (F("2.2"), 3, False),
        "getup": (F("15.0", "2.0", "2.1"), 6, False),
        "prejump": (F("2.0"), 1, False),
        "jump_up": (R(3, 0, 1), 5, False),
        "jump": (R(3, 1, 2), 6, False),
        "fall": (F("3.2", "4.2"), 6, False),
        "land": (F("3.3", "2.0"), 4, False),
        "punch_prep": (R(6, 0, 1), 2, False),
        "punch": (F("6.2"), 3, False),
        "punch_rec": (F("6.1", "6.0"), 3, False),
        "cr_punch_prep": (F("2.1"), 2, False),
        "crouch_jab": (F("6.2"), 3, False),
        "cr_punch_rec": (F("2.1"), 3, False),
        "front_kick_prep": (F("7.0"), 2, False),
        "front_kick": (F("7.1"), 3, False),
        "front_kick_rec": (F("7.0"), 3, False),
        "kick_prep": (F("9.0"), 2, False),
        "kick": (F("9.1"), 3, False),
        "kick_rec": (F("9.0", "0.0"), 3, False),
        "crkick_prep": (F("2.1"), 2, False),
        "crkick": (F("7.1"), 3, False),
        "crkick_rec": (F("2.1"), 3, False),
        "sweep_prep": (F("2.0", "9.0"), 2, False),
        "sweep": (F("9.1"), 3, False),
        "sweep_rec": (F("9.0", "2.0"), 3, False),
        "hado_prep": (R(10, 0, 1), 3, False),
        "hado_fire": (F("10.2"), 3, False),
        "air_hado_prep": (F("4.1"), 3, False),
        "air_hado": (F("4.0"), 3, False),
        "sho_crouch": (F("2.0"), 2, False),
        "sho_rise": (F("14.0"), 3, False),
        "sho_top": (F("14.0"), 3, False),
        "sho_fall": (F("4.2"), 4, False),
        "tatsu_start": (F("11.0", "11.1"), 2, False),
        "tatsu": (F("12.0"), 3, True),
        "tatsu_end": (F("11.2"), 3, False),
        "hammer_up": (F("8.0"), 3, False),
        "hammer_down": (F("8.1"), 3, False),
        "leap_kick": (F("4.0"), 3, False),
        "lariat_a": (F("12.0"), 2, True),
        "lariat_b": (F("12.1", "12.0"), 2, True),
        "jpunch_prep": (F("3.1"), 1, False),
        "jump_jab": (F("4.0"), 3, False),
        "jkick_prep": (F("4.1"), 2, False),
        "jump_kick": (F("3.2"), 3, False),
        "dive": (R(5, 1, 2), 4, True),
        "hurt": (R(13, 0, 1), 3, False),
        "hurt_low": (F("13.1"), 3, False),
        "launch": (R(13, 1, 2), 4, False),
        "bounce": (F("13.3"), 4, False),
        "down": (F("13.3"), 5, False),
        "intro": (F("11.1", "11.2") + R(0, 0, 3), 6, "loop2"),
        "victory": (F("0.0", "14.0"), 8, False),
        "taunt": (F("14.0"), 6, False),
        "grab": (F("8.0"), 2, False),
        "grab_miss": (F("8.0", "0.0"), 3, False),
        "toss": (F("8.0", "8.1", "6.2"), 3, False),
    },
)
