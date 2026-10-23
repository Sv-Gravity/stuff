# Akuma Quest

A roguelike where every encounter turns into a Street Fighter–style duel, and every level after the first few turns into a different game. You play Akuma. There are eleven levels:

1. **The Caves of Gokuentou**: explore an overhead dungeon; touching an enemy (or being touched) switches to a side-view 1-on-1 fight. Boss: **Zangief**.
2. **The Burning Temple**: the same, but every grunt brings a partner: **2-on-1** fights. Boss (alone): **Morrigan**.
3. **The Wrecking Yard**: cars drive around instead of enemies; touching one starts an SF2-style car-smashing bonus round. Boss: **The Block Cruiser**, which Tetris pieces keep repairing.
4. **The Car Park**: Bomberman. Plant hadouken bombs; one blast wrecks a car.
5. **The Fighter Maze**: Pac-Man, chased by four of the cast (it changes every run).
6. **Hyrule Castle**: Smash Bros 64. Akuma vs three CPUs, damage %, bubble shield, 3 stocks.
7. **The Frozen Compound**: Metal Gear Solid. Sneak past guards and cameras; get spotted and their rifles nearly one-shot you. There's a cardboard box.
8. **Skate or Die**: 720° skateboarding. 100 trick points in a minute or the ghost comes.
9. **Connect Four**: against Ryu, with fireballs for pieces.
10. **The Prisoners' Quarters**: a Dead Cells style side-scrolling metroidvania with a boss, the Warden.
11. **Knee-Deep in the Demon**: Doom, shooting hadoukens. Boss: **Cyber-Gief**.

The main menu has **Start Game**, **Practice** (Akuma vs a sparring Ryu), **Level** (a debug shortcut: press left/right to pick a level and start there) and **Quit**.

All the fighters use Toshi's sprite pack (`art_source/sprites/`): Akuma, and as enemies Ryu, Ken, Sakura, Felicia, Hsien-Ko, Zangief, Morrigan, Chun-Li and Dr. Doom (cut from Toshi's own Dr. Doom sheet by `tools/make_drdoom.py`). Each character's sheet is cut into frames in `akuma/assets/chars/<name>/`, with every engine pose mapped to a full animation (Akuma alone has about 200 drawings). Attack animations are stretched to fit each move's exact frame data, so every in-between drawing shows without changing the timing. The HUD shows both fighters' portraits. On the map everyone walks with their own walk cycle at half size, timed to the distance walked so feet never slide. Tiles, stages, cars, effects and sound are drawn or synthesized by code.

## Run it on Windows

1. Install Python 3.10 or newer from https://www.python.org/downloads/ and tick **"Add python.exe to PATH"** during setup.
2. Unzip this folder anywhere.
3. Double-click **`run.bat`**. The first time, it installs pygame for you.

Or, from a terminal in this folder:

```
pip install pygame
python main.py
```

Add `--fullscreen` to start in full screen, or press **F11** in game.

### Make a standalone .exe (optional)

Double-click **`build_exe.bat`**. It installs PyInstaller and produces `dist\AkumaQuest.exe`, which you can copy to any Windows PC and run without Python.

## Controls

| | Keyboard | Gamepad (Xbox layout) |
|---|---|---|
| Move | Arrow keys or WASD | D-pad / left stick |
| Punch | J or Z | X (or LB) |
| Kick | K or X | A (or RB) |
| Special | L, C or Space | B or Y |
| Shield / block (Smash), roll (level 10), strafe (level 11) | I | left stick click |
| Pause menu (resume, controls, back to main menu) | Enter or Esc | Start |
| Controls page | F1 or Tab | |
| Fullscreen | F11 | |
| FPS counter | F3 | |

### Fight mode

| Button | Standing | Forward | Back | Down | In the air |
|---|---|---|---|---|---|
| **Special** | Gou Hadouken (fireball) | Gou Hadouken | Gou Hadouken | Gou Hadouken | Zanku Hadouken (air fireball, angled down) |
| **Punch** | Jab | Jab | Jab | Crouching jab | Jumping punch |
| **Kick** | Front kick (medium reach) | Front kick | Roundhouse (long reach, slower windup) | Sweep (low, knocks down) | Jumping kick, or dive kick with down held |

**Special + Punch** together is the **Goshoryuken** (dragon punch). **Special + Kick** together is the **Tatsumaki** (hurricane kick). "Together" means within 4 frames of each other, in either order, so a fireball that has only just started turns into the dragon punch or hurricane kick. Directions no longer change specials.

**Punch + Kick together** up close is a **throw**, Third Strike style: Akuma grabs the enemy, lifts them up over his head and flings them the way you are holding (left or right; neutral throws forward, back swings them over his head to the other side). They spin through the air and slam into the floor. It does double damage and can't be blocked.

**Down-forward + Kick** is a small, fast crouching kick that hits low and combos. **Down-back + Kick** is the sweep.

Moving works like Street Fighter. Forward walks, back walks away or **blocks** when an attack or fireball is coming, down crouches (down-back blocks low), and up jumps (hold forward or back to jump that way). Overheads (dive kicks, jump-ins, hammer fists) must be blocked standing; sweeps must be blocked crouching. Button presses are buffered for a few frames, so an early press still comes out. Only one fireball (ground or air) can be on screen at a time. The dragon punch is invincible on startup.

### Damage

| Button | Damage | Speed |
|---|---|---|
| Punch | 0.5 hit | Fastest (2-frame startup) |
| Kick | 1 hit | Normal (5 frames; roundhouse 9) |
| Special | 1.5 hits | Hurricane kick spreads it over 3 hits |
| Throw | 2 hits | Unblockable, needs to be up close |

### Combos

Combos work like Street Fighter cancels. When a punch or kick connects (hit or block), you have a short window to press the next button, and it interrupts the first move's recovery:

- **Punches** cancel into another punch, a kick or a special.
- **Kicks** cancel into a different kick or a special.
- **Specials** end the string.

A string is at most 5 moves, and the 5th hit of any combo always knocks the enemy down, so nothing is infinite. Jump-ins are combo openers: a jumping punch, jumping kick or dive kick that hits never knocks the enemy down. It leaves them reeling long enough for you to land and keep going, for example **dive kick, jab, jab, kick, special**. Presses made during the hit freeze are remembered, including the direction you were holding.

A good starter: **jab, jab, kick, back+kick, special** (5 hits, ends with a hadouken).

### Practice mode

Practice puts Akuma against a sparring Ryu that never dies. Its health refills when you stop hitting it, and the screen shows the hits and damage of your last combo. Press Enter for the practice menu, where you can set Ryu to **Stand**, **Crouch**, **Block** (blocks everything correctly), **Jump** or **Fight back**, reset positions, or go back to the main menu.

## How a run works

- The dungeon is randomly generated each run (the seed is shown on the end screen).
- **12 grunts** roam level 1 (Ryu, Ken, Sakura and Felicia) and **10** pairs roam level 2 (Hsien-Ko joins them). Each one gets a random speed, personality (aggression, blocking, jumping) and **1 or 2 attacks** from this pool: Jab, Roundhouse, Fireball, Rising Upper, Rush Punch, Leap Kick, Low Sweep, Hammer Fist, each played with that character's own animation. Their moves are listed under their health bar.
- Grunts usually take about **7 hits** to beat. On level 2 they come in twos: one on each side of Akuma, two health bars on the right, and he turns to face whichever is closer. Only the boss fights alone. Every grunt also has a **level from 1 to 4**, shown above its head on the map; higher levels take a little more and hit harder.
- Enemies notice you (a red **!**) and give chase. If you touch one before it notices you, you get a **Sneak Attack** and it starts the fight with 20% less health.
- Fights start and end quickly: a short flash, a quick "FIGHT!", and straight back to the map after the K.O. (press any attack button to skip it).
- Akuma's health carries over between fights. You heal 25% after each win, **Japanese snacks** are scattered all over the map (ramen, mochi, onigiri, dango, taiyaki, takoyaki, Pocky, melon pan, dorayaki and the rare bento; bigger meals heal more), and **Satsui orbs** raise max HP and damage.
- Each level's **boss** waits on a throne in the biggest room. **Zangief** (level 1) takes **15 hits** and hits three times as hard as a grunt. He has 7 attacks, including a big energy push, a rush punch and a multi-hit Double Lariat. **Morrigan** (level 2) takes 18 hits, is faster and more aggressive, adds a leap kick, and hits even harder. Both get **enraged** at half health.
- Beating a level restores Akuma's health and opens the next one. Clear level 11 to win the run.

### Hitboxes

Hits are pixel-exact. A fighter can be hit anywhere its current drawing has pixels, and an attack hits with the part of its drawing that sticks out of the standing body (the fist, the foot, the flame), so if it looks like it connected, it did. Fireballs hit with their drawn shape too, and so do hits on the cars.

### Level 3: The Wrecking Yard

A small parking garage with only **5 cars** driving around it instead of enemies. Touch a car to start a **bonus round** like Street Fighter II's car stage:

- The car never fights back. Beat it up before the **30-second** timer runs out.
- The five cars are a **Toyota AE86**, a first-gen **Toyota MR2**, a **'99 Mustang GT**, an **Eagle Talon TSi** and a **'65 Cougar XLR**. Each side of the car has its own gauge (L and R under its health bar) and takes about **5 kicks** to wreck. Once one side is scrap, hits there do nothing, so **jump over the car** and wreck the other side. Windows shatter, bumpers fall off, doors get torn away and it starts smoking as each side takes damage.
- Cars are solid: you can't walk through one, but you can **jump on top and stand on the roof** (and attack from up there), then walk off either end. A **hurricane kick spins right through the car**, hitting it about ten times on the way.
- If the timer runs out, the car drives off and Akuma loses 20 HP.
- The boss, **The Block Cruiser**, is a car built from falling-block puzzle pieces. Blocks fly off whichever side you hit, about 9 kicks per side, with a 45-second timer. If its timer runs out Akuma loses 30 HP and the clock restarts.
- Meanwhile Tetris is being played in the sky: a random tetromino falls every few seconds, stepping down and turning like someone is steering it. One that **lands on the car repairs it** (about 4% of its health, and the lost blocks come back); one that lands on Akuma hurts. Punch, kick or hadouken a piece to smash it before it lands.
- Lose a fight and the run is over.

### Level 4: The Car Park

A Bomberman level in a parking garage with concrete pillars, crates, oil drums and traffic cones. The five cars from level 3 cruise the lanes.

- Press **Punch, Kick or Special** to plant a **hadouken bomb**. It pulses, flashes faster and faster, then bursts in a **cross** that stops at pillars and blows up the first crate it reaches. Bombs set each other off.
- Crates sometimes drop orbs: **B** lets you plant one more bomb at a time, **F** makes the blasts longer.
- Cars fight back two ways. **Headlights**: a car stops, its headlights blink, then they switch on in a beam down the whole lane (-24 HP if you're in it). **Horn**: a car beeps and flashes, then honks, a small round blast around it (-20 HP). Getting run over hurts a little, and so does your own blast (-32 HP).
- **One blast** wrecks a car. Wreck all five to clear the level.

### Level 5: The Fighter Maze

Pac-Man with Akuma. Four fighters picked from Chun-Li, Zangief, Morrigan, Felicia, Ryu, Ken, Sakura and Hsien-Ko chase him, each with a personality: one chases, one cuts him off ahead, one flanks, and one is shy.

- Eat every pellet to clear the level. The side tunnels wrap around.
- A **power pellet** turns them blue and makes them flee; touching one KOs it (200, 400, 800, 1600 points in a row). A KO'd fighter tags out for someone from the bench.
- Getting caught costs a quarter of Akuma's health. Health runs out and the run is over.

### Level 6: Hyrule Castle

Smash Bros 64 on a pixel Hyrule Castle: a wide main floor, the tower, and pass-through ledges spread out across a bigger stage; the camera pans and zooms to keep everyone in view. Akuma vs three random CPUs, each with their own moveset (Ryu's shoryuken, Chun-Li's spinning bird kick, Zangief's piledriver and lariat, Hsien-Ko's thrown axes, Dr. Doom's green fireball and hellfire, and so on).

- **Left/right** move and face that way. **Up** jumps, up again double-jumps. **Down** drops through ledges.
- **J** jab / air attack, **K** kick (down+K sweep, air down+K dive kick), **L** hadouken, **L+J** shoryuken (also your recovery), **L+K** hurricane kick.
- **Hold I** for the bubble shield. It shrinks as it takes hits and breaks if you hold it too long (you're dizzy). I+left/right rolls, J+K grabs.
- **Items** drop from the sky: Home-Run Bat, Beam Sword, Bob-omb, Hammer, Star, Heart Container and Japanese snacks. Stand on one and press **J** to pick it up, **J** to use it, **J+K** to throw it. Touching a star, heart or snack uses it at once. The CPUs go for items too.
- Damage goes from **0% to 200%**. The higher it is, the further hits send you. **Two rounds of 3 stock**; win at least one round to clear the level.

### Level 7: The Frozen Compound

Metal Gear Solid. A snowy base full of guards, most of them standing on post staring one way (and glancing around now and then); a few walk short routes. Three of them are smoking, and everyone has something to say ("I REALLY NEED TO PEE.", "MUST'VE BEEN THE WIND... IT'S ALWAYS THE WIND.").

- Guards see in a cone (drawn on the floor) and hear running nearby. **Shadows** shrink how far they see you; smokers barely notice anything. Hold **K** to sneak silently; **J** against a wall knocks to lure a guard.
- Sneak up behind an unaware guard and press **J** to **snap his neck**. A body left out in view puts the base on caution.
- Hide in the **bushes** (you're invisible unless a guard walks into you) or the **cardboard box** hidden in a storage room.
- Two rooms are guarded by tougher **red berets**: the barracks (keycard, C4, a max-life boost) and the armory (damage up).
- **Missions** (shown top-left and on the radar, with a codec call for each): get the keycard and C4, blow the three generators (the power dies, cameras and lasers go dark), free the prisoner, then **Revolver Ken** comes up the elevator. Beat him to clear the level.
- If a guard catches you, it's a side-view fight against soldiers with **rifles** that kill in a few shots. Japanese snacks heal. The sounds are sound-alikes made in code (the game can't ship Konami's audio).

### Level 8: Skate or Die

720° on a skateboard in a big open park. Find the board ("SKATE OR DIEEEE!") and the one-minute clock starts.

- **J** ollies, **K** pushes, **L** kickflips (in the air, or straight off the ground), **left/right** turn (and spin in the air), **down** brakes.
- Each clean trick is **25 points**: spins in 180s (180, 360, 540, 720!!) and kickflips. Land crooked or mid-flip and you bail.
- **Grind** by ollieing onto a rail, or onto the edge of a grind box, bench, planter or barrier, while heading along it: sparks fly and longer grinds score more (the long rail is worth about 34). Press J or L to pop off early.
- Ollie clean over a fire hydrant for a **HYDRANT HOP** (+15); cones and trash cans are worth +10.
- Reach **100 points** to clear it. If the clock runs out a **ghost** chases you; if it touches you, you die.

### Level 9: Connect Four

Akuma and Ryu stand on either side of a Connect Four board. Pick a column with left/right and press an attack: Akuma throws a **red** hadouken that drops into the column and stays there as his piece; Ryu answers in **blue**. You always go first. Ryu searches 10 to 20 moves ahead and is hard to beat. A draw replays; Ryu winning ends the run.

### Level 10: The Prisoners' Quarters

A Dead Cells style side-scroller: a castle prison laid out differently every run, with shrines, altars, hidden scrolls of power and the **Warden** at the end.

- **Up** jumps (hold for higher), **J** a three-hit string, **K** a heavy kick that breaks shields (down+K sweep, air down+K stomp), **L** hadouken (uses ki; in the air it shoots 45° down), **L+J** shoryuken, **L+K** hurricane kick, **down+L** drinks a flask, **I** dodge-rolls through attacks.
- Japanese snacks lie around the castle and drop from chests.
- Enemies flash before they swing and hit hard. Grunts, shield bearers, witches and bats.
- 3 flasks, refilled at shrines. Dying costs one of 3 lives and sends you back to the last shrine. Spend cells at the altars for damage or health.

### Level 11: Knee-Deep in the Demon

Doom with hadoukens. A hell fortress in first person under a blood-red sky: green-grey stone, keycards, doors, a secret wall, imps, pinkies, cacodemons, lost souls and zombiemen, and **Cyber-Gief** guarding the exit portal. Akuma's own clawed hands (prayer beads, red ki) and bare foot fill the bottom of the screen, above a Doom-style status bar.

- **Up/down** walk, **left/right** turn, **hold I** + left/right to strafe.
- **L** fires a hadouken (hold to keep firing), **L+J** shoryuken, **L+K** spinning tatsumaki, **I+L** a piercing Shinku Hadouken, **J** punches, **K** kicks and opens doors.
- Ki orbs refill ki, Japanese snacks heal. Kill Cyber-Gief and step into the portal to finish the quest.

## Smoothness

The game runs a fixed 60 fps with frame-counted logic, like an arcade fighter: no variable timestep, so every move has exact frame data. It uses hitstop and screen shake on impact, renders at 320×180 and scales up with sharp pixels, and caches every sprite up front. A frame of gameplay takes about 1 ms of CPU.

## Project layout

```
main.py            entry point
run.bat            Windows launcher (installs pygame if needed)
build_exe.bat      PyInstaller build of a standalone .exe
akuma/
  game.py          main loop, title / game-over / level-clear screens
  dungeon.py       map generation, exploration, map enemies, pickups, lighting
  fight.py         the fighting-game mode (hits, blocks, hitstop, HUD, KO)
  fighters.py      frame data for Akuma's moves, the enemy move pool, fighter physics, enemy AI
  art.py           procedural pixel art: tiles, effects, stages
  akuma_sprites.py loads each character's frames and picks the image for every pose
  practice.py      practice mode vs a sparring Ryu
  cars.py          level 3: car bonus rounds, the five car models, the block-car boss
  bomber.py        level 4: the Bomberman car park
  pacman.py        level 5: the fighter maze
  smash.py         level 6: Smash Bros on Hyrule Castle
  stealth.py       level 7: the Metal Gear base
  skate.py         level 8: the 720 skate park
  connect4.py      level 9: Connect Four and Ryu's search
  metroid.py       level 10: the Dead Cells style castle
  doom.py          level 11: the raycaster
  snacks.py        the Japanese snack health pickups (pixel art and how much each heals)
  pause.py         the pause menu and controls page
  assets/chars/    every character's frames, feet points, pose lists and HUD portrait
  audio.py         synthesized sound effects
  inputs.py        keyboard + gamepad
  font.py          5x7 bitmap font
art_source/sprites/          Toshi's sprite pack, one sheet per character
art_source/portraits.png     character art the HUD portraits are cut from
tools/pocket_sheets.py       finds every frame on a sheet and writes a numbered contact sheet
tools/pocket_rows.py         shows chosen rows of a sheet bigger, for picking frames
tools/extract_pocket.py      Akuma's frame list; cuts every character into akuma/assets/chars
tools/specs/<name>.py        the other characters' frame lists
tools/preview_chars.py       every pose of a character on one image, anchored on the feet
tools/make_lubu.py           the Warden (level 10 boss): Ryu recoloured with armour and plumes
tools/make_drdoom.py         Dr. Doom: cuts Toshi's Dr. Doom sheet into frames
art_source/retired/          the earlier Akuma sheets' cut sprites and their tools (no longer used)
                             (the tools need pillow + numpy; not needed to play)
tests/smoke_test.py         headless tests: move mapping, damage tiers, a 5-hit combo, jump-in
                            combos, throws, practice menu, car roofs, Tetris repairs, bots that
                            play levels 1-5, every later level starting, and each level's test below
tests/<level>_test.py       bomber, pacman, smash, stealth, skate, connect4, metroid, doom: each level's rules plus a bot that clears it
```

Run the test with `python tests/smoke_test.py`. It needs no window and no sound. The game needs pygame and numpy (`run.bat` installs both).
