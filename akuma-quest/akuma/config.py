"""Global constants."""

TITLE = "Akuma Quest"
W, H = 320, 180          # internal canvas; scaled up crisply to the window
FPS = 60
TILE = 16

# Overworld
MAP_W, MAP_H = 64, 48    # in tiles
PLAYER_SPEED = 1.5       # px / frame on the map
ENEMY_COUNT = 12

# Fight
GROUND_Y = 158
STAGE_LEFT, STAGE_RIGHT = 14, W - 14
GRAVITY = 0.42
HITSTOP = 7

AKUMA_MAX_HP = 160
WIN_HEAL = 0.18          # fraction of max hp restored after each won fight
