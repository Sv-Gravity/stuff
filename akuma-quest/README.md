# Akuma Quest

A roguelike where every encounter turns into a Street Fighter–style duel, and every level after the first few turns into a different game. You play Akuma. There are twelve levels:

1. **The Caves of Gokuentou**: explore an overhead dungeon; touching an enemy (or being touched) switches to a side-view 1-on-1 fight. Boss: **Zangief**.
2. **The Burning Temple**: the same, but every grunt brings a partner: **2-on-1** fights. Boss (alone): **Morrigan**.
3. **The Wrecking Yard**: cars drive around instead of enemies; touching one starts an SF2-style car-smashing bonus round. Boss: **The Tetris Master**, who plays Tetris on a giant well; break his blocks before he scores a TETRIS.
4. **The Car Park**: Bomberman. Plant hadouken bombs; one blast wrecks a car.
5. **Hyrule Castle**: Smash Bros 64. Akuma vs three CPUs, damage %, bubble shield, 3 stocks.
6. **The Frozen Compound**: Metal Gear Solid. Sneak past guards and cameras; get spotted and their rifles nearly one-shot you. There's a cardboard box.
7. **Skate or Die**: 720° skateboarding. 100 trick points in a minute or the ghost comes.
8. **Connect Four**: against Ryu, with fireballs for pieces.
9. **The Prisoners' Quarters**: a Dead Cells style side-scrolling metroidvania with a boss, the Warden.
10. **Geldra's Hideout**: Rolling Thunder (NES). Two floors, maskers coming out of doors, and hadoukens instead of a gun. Boss: **Dr. Doom**.
11. **The Climb**: Fall Guys. Race four Street Fighters up a giant obstacle tower to the crown, with Smash damage % and knockback; get knocked off and you start again from the bottom. Win it and round 2 is a side-scrolling race ahead of a wall of spikes.
12. **Knee-Deep in the Demon**: Doom, shooting hadoukens. Boss: **Cyber-Gief**.

The main menu has **Start Game**, **Practice** (Akuma vs a sparring Ryu), **Level** (a debug shortcut: press left/right to pick a level and start there) and **Quit**.

All the fighters use Toshi's sprite pack (`art_source/sprites/`): Akuma, and as enemies Ryu, Ken, Sakura, Felicia, Hsien-Ko, Zangief, Morrigan, Chun-Li and Dr. Doom (cut from Toshi's own Dr. Doom sheet by `tools/make_drdoom.py`). Each character's sheet is cut into frames in `akuma/assets/chars/<name>/`, with every engine pose mapped to a full animation (Akuma alone has about 200 drawings). Attack animations are stretched to fit each move's exact frame data, so every in-between drawing shows without changing the timing. The HUD shows both fighters' portraits. On the map everyone walks with their own walk cycle at half size, timed to the distance walked so feet never slide. Cars, Doom's first-person hands and the red fireballs and explosions come from Toshi's sheets too (`tools/make_cars.py`, `tools/make_doom_hands.py`, `tools/make_fx.py`). Tiles, stages and sound are drawn or synthesized by code.

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
| Shield / block (Smash), roll (level 9), duck into a door (level 10), strafe (level 11) | I | LT / RT (or left stick click) |
| Pause menu (resume, controls, back to main menu) | Enter or Esc | Start (View closes it) |
| Back / skip (closes menus, skips codec calls) | Esc | View |
| Controls page | F1 or Tab | Pause menu, CONTROLS |
| Fullscreen | F11 | |
| FPS counter | F3 | |

An Xbox controller (or any pad SDL knows: PlayStation, Switch Pro, 8BitDo...) is used automatically as soon as it's plugged in, before or during play, and the keyboard keeps working alongside it. The title screen says CONTROLLER READY when one is detected. On the title screen View only moves the cursor to QUIT, so a stray press can't close the game.

### Fight mode

| Button | Standing | Forward | Back | Down | In the air |
|---|---|---|---|---|---|
| **Special** | Gou Hadouken (fireball) | Gou Hadouken | Gou Hadouken | Gou Hadouken | Zanku Hadouken (air fireball, angled down) |
| **Punch** | Jab | Jab | Jab | Crouching jab | Jumping punch |
| **Kick** | Front kick (medium reach) | Front kick | Roundhouse (long reach, slower windup) | Sweep (low, knocks down) | Jumping kick, or dive kick with down held |

**Special + Punch** together is the **Goshoryuken** (dragon punch). **Special + Kick** together is the **Tatsumaki** (hurricane kick). "Together" means within 4 frames of each other, in either order, so a fireball that has only just started turns into the dragon punch or hurricane kick. Directions no longer change specials.

**Punch + Kick together** up close is a **throw**, Akuma's Third Strike tomoe nage: he grabs them, drops onto his back, plants a foot in their gut and flips them over his head so they land behind him, then rolls back up. It does double damage and can't be blocked.

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
- Beating a level restores Akuma's health and opens the next one. Clear the last level to win the run.

### Hitboxes

Hits are pixel-exact. A fighter can be hit anywhere its current drawing has pixels, and an attack hits with the part of its drawing that sticks out of the standing body (the fist, the foot, the flame), so if it looks like it connected, it did. Fireballs hit with their drawn shape too, and so do hits on the cars.

### Level 3: The Wrecking Yard

A small parking garage with only **5 cars** driving around it instead of enemies. Touch a car to start a **bonus round** like Street Fighter II's car stage:

- The car never fights back. Beat it up before the **30-second** timer runs out.
- Five cars a run come from seven models drawn on Toshi's car sheet: **Toyota AE86**, **Toyota MR2 SW20**, **Mazda Miata NA**, **Honda S2000**, **VW GTI Mk2**, **Mazda RX-7 FC** and a **'65 Mercury Cougar**. Each has five damage stages, from pristine to a smoking wreck in a pile of debris, and blows up when it's finished. Each side of the car has its own gauge (L and R under its health bar) and takes about **5 kicks** to wreck. Once one side is scrap, hits there do nothing, so **jump over the car** and wreck the other side. Windows shatter, bumpers fall off, doors get torn away and it starts smoking as each side takes damage.
- Cars are solid: you can't walk through one, but you can **jump on top and stand on the roof** (and attack from up there), then walk off either end. A **hurricane kick spins right through the car**, hitting it about ten times on the way.
- If the timer runs out, the car drives off and Akuma loses 20 HP.
- The boss is **The Tetris Master**, a guy in a backwards cap at an arcade cabinet on the left of the stage. His Tetris well (10 wide, 9 tall) fills the right half, and his screen mirrors it. He plays like a real player: each piece slides, turns and soft-drops into the spot his AI likes best (it looks at the NEXT piece too), stacking flat rows and keeping the right-hand column open for the long I piece. Rows that are one I piece away from clearing glow in that column, a warning flashes once three are lined up, and with rows lined up he has a knack for getting the I piece.
- If he clears **4 lines at once (TETRIS!)** the screen flashes, a shockwave goes out and Akuma takes **40 HP** and is knocked down. A triple costs Akuma 10 HP; singles and doubles do nothing. He starts mid-game with two rows already lined up.
- Break his blocks to wreck his lines: a punch (or each spin of a hurricane kick) cracks a block, a kick breaks one, a hadouken breaks the first two it hits, and a shoryuken breaks up to three. A hole in a row means that row can never clear. His health bar is **40 blocks**; empty it to win (a falling piece smashed in mid-air counts for 2).
- Falling pieces hurt: one that reaches Akuma breaks on him for **12 HP** and knocks him down. A faint outline shows where each piece will land. Punch, kick or hadouken a piece to smash it before it lands.
- The stack is solid: Akuma can't walk through it, but he can **jump on top and stand on it** to reach the high blocks. Blocks hanging over a gap can be walked under.
- There's a **60-second** timer. If it runs out Akuma loses 30 HP and the clock restarts. If the Master ever tops out, his board is wiped and he loses 6.
- Lose a fight and the run is over.

### Level 4: The Car Park

A Bomberman level in a parking garage with concrete pillars, crates, oil drums and traffic cones. Five of the seven cars from level 3 cruise the lanes; each one you wreck explodes and shows up on the tally at the end.

- Press **Punch, Kick or Special** to plant a **hadouken bomb**. It pulses, flashes faster and faster, then bursts in a **cross** that stops at pillars and blows up the first crate it reaches. Bombs set each other off.
- Crates sometimes drop orbs: **B** lets you plant one more bomb at a time, **F** makes the blasts longer.
- Cars fight back two ways. **Headlights**: a car stops, its headlights blink, then they switch on in a beam down the whole lane (-24 HP if you're in it). **Horn**: a car beeps and flashes, then honks, a small round blast around it (-20 HP). Getting run over hurts a little, and so does your own blast (-32 HP).
- **One blast** wrecks a car. Wreck all five to clear the level.

### Level 5: Hyrule Castle

Smash Bros 64 on a pixel Hyrule Castle: a wide main floor, the tower, and pass-through ledges spread out across a bigger stage; the camera pans and zooms to keep everyone in view. Akuma vs three random CPUs, each with their own moveset (Ryu's shoryuken, Chun-Li's spinning bird kick, Zangief's piledriver and lariat, Hsien-Ko's thrown axes, Dr. Doom's green fireball and hellfire, and so on).

- **Left/right** move and face that way. **Up** jumps, up again double-jumps. **Down** drops through ledges.
- **J** jab / air attack, **K** kick (down+K sweep, air down+K dive kick), **L** hadouken, **L+J** shoryuken (also your recovery), **L+K** hurricane kick.
- **Hold I** for the bubble shield. It shrinks as it takes hits and breaks if you hold it too long (you're dizzy). I+left/right rolls, J+K grabs.
- **Items** drop from the sky: Home-Run Bat, Beam Sword, Bob-omb, Hammer, Star, Heart Container and Japanese snacks. Stand on one and press **J** to pick it up, **J** to use it, **J+K** to throw it. Touching a star, heart or snack uses it at once. The CPUs go for items too.
- Damage goes from **0% to 200%**. The higher it is, the further hits send you. **Two rounds of 3 stock**; win at least one round to clear the level.

### Level 6: The Frozen Compound

Metal Gear Solid. A snowy base full of guards, most of them standing on post staring one way (and glancing around now and then); a few walk short routes. Three of them are smoking, and everyone has something to say ("I REALLY NEED TO PEE.", "MUST'VE BEEN THE WIND... IT'S ALWAYS THE WIND.").

- Guards see in a cone (drawn on the floor) and hear running nearby. **Shadows** shrink how far they see you; smokers barely notice anything. Hold **K** to sneak silently; **J** against a wall knocks to lure a guard.
- Sneak up behind an unaware guard and press **J** to **snap his neck**. A body left out in view puts the base on caution.
- Hide in the **bushes** (you're invisible unless a guard walks into you) or the **cardboard box** hidden in a storage room.
- Two rooms are guarded by tougher **red berets**: the barracks (keycard, C4, a max-life boost) and the armory (damage up).
- **Missions** (shown top-left and on the radar, with a codec call for each): get the keycard and C4, blow the three generators (the power dies, cameras and lasers go dark), free the prisoner, then **Revolver Ken** comes up the elevator. Beat him to clear the level.
- If a guard catches you, it's a side-view fight against soldiers with **rifles** that kill in a few shots. Japanese snacks heal. The sounds are sound-alikes made in code (the game can't ship Konami's audio).

### Level 7: Skate or Die

720° on a skateboard in a big open park. Find the board ("SKATE OR DIEEEE!") and the one-minute clock starts.

- **J** ollies, **K** pushes, **L** kickflips (in the air, or straight off the ground), **left/right** turn (and spin in the air), **down** brakes.
- Each clean trick is **25 points**: spins in 180s (180, 360, 540, 720!!) and kickflips. Land crooked or mid-flip and you bail.
- **Grind** by ollieing onto a rail, or onto the edge of a grind box, bench, planter or barrier, while heading along it: sparks fly and longer grinds score more (the long rail is worth about 34). Press J or L to pop off early.
- Ollie clean over a fire hydrant for a **HYDRANT HOP** (+15); cones and trash cans are worth +10.
- Reach **100 points** to clear it. If the clock runs out a **ghost** chases you; if it touches you, you die.

### Level 8: Connect Four

Akuma and Ryu stand on either side of a Connect Four board. Pick a column with left/right and press an attack: Akuma throws a **red** hadouken that drops into the column and stays there as his piece; Ryu answers in **blue**. You always go first. Ryu searches 10 to 20 moves ahead and is hard to beat. A draw replays; Ryu winning ends the run.

### Level 9: The Prisoners' Quarters

A Dead Cells style side-scroller: a castle prison laid out differently every run, with shrines, altars, hidden scrolls of power and the **Warden** at the end.

- **Up** jumps (hold for higher), **J** a three-hit string, **K** a heavy kick that breaks shields (down+K sweep, air down+K stomp), **L** hadouken (uses ki; in the air it shoots 45° down), **L+J** shoryuken, **L+K** hurricane kick, **down+L** drinks a flask, **I** dodge-rolls through attacks.
- Japanese snacks lie around the castle and drop from chests.
- Enemies flash before they swing and hit hard. Grunts, shield bearers, witches and bats.
- 3 flasks, refilled at shrines. Dying costs one of 3 lives and sends you back to the last shrine. Spend cells at the altars for damage or health.

### Level 10: Geldra's Hideout

Rolling Thunder on the NES, with Akuma instead of Albatross. A long street front with two floors, the street and a balcony walkway above it, in two areas (a brick warehouse district, then the steel Geldra base). Hooded Geldra maskers (the sprite-pack fighters, tinted by rank) step out of the doors on both floors.

- No gun: the **hadouken is the gun** and **ki is the ammo** (4 shots when full, slow to refill). **Shoryuken** (special + punch, invincible on the way up) and **hurricane kick** (special + kick) are the close-range answer, plus the usual punch string, kick, low punch / sweep, jump attacks, dive kick and the 45° air hadouken (good for shooting down onto the street from the walkway). A hadouken also eats the maskers' small ki shots.
- **UP** jumps; under a walkway it is a **vault**, a flip up onto the walkway. **DOWN + UP** on the walkway drops back down. **DOWN** ducks.
- **Standing shooters fire high: duck. Crouching shooters fire low: jump.** Every masker flashes and shows a "!" before it fires.
- Ranks: blue maskers shoot, red ones rush in and punch, green ones leap between the floors and jump-kick, purple ones (area 2) fire three-shot bursts.
- **I** in front of a door ducks Akuma inside: hidden, nothing can hit him. Doors marked **KI** refill ki, **FOOD** heals with a Japanese snack, **RAPID** gives 12 seconds of free rapid-fire hadoukens. Each gives its item once.
- 3 lives; dying puts Akuma back on his feet where he fell with a full bar.
- **Dr. Doom**, master of Geldra, waits in the locked courtyard at the end: volleys of ki shots (watch his stance: crouched = low, standing = high), a charged beam, a punch up close, he flies to whichever floor you are on and his landing sends shockwaves along the floor (jump them), and he calls maskers out of the courtyard doors as his health drops. Faster below half health.

### Level 11: The Climb

Fall Guys meets Smash. A giant candy-coloured obstacle tower, ten screens tall, and Akuma races four random Street Fighter rivals from the floor to the **crown** on top: whoever touches the FINISH first wins. The camera flies down the whole tower before the countdown so you can see what is coming.

- Mostly medium climbing: steps, moving platforms (side to side and up and down), conveyor belts, bounce pads, swinging hammers, sweeper bars, boxing-glove pistons that punch out of the walls, and cannons firing big fruit across the tower.
- Hard spots on the way, called out when you reach them and marked red on the tower bar at the right: the **Crumble Bridge** (tiles that fall a moment after you land, under a spinning bar), the **Pillars** (a double sweeper, then thin pillars between pistons), the **Ghost Blocks** (platforms that blink on and off in turn while fruit flies through), and **the Summit** at the end (a lift, crumbling steps, a glove, fruit and a double sweeper spinning round the crown).
- Everyone fights with their Smash moveset (same controls as level 5, no items) and has a **damage %**: hits and obstacles raise it, and the higher it is the further everything knocks you. Knock rivals off the tower to send them back to the bottom.
- Get knocked off the side yourself and you **respawn on the floor at 0%** and have to catch up. Holding toward a ledge as you fall past grabs it.
- The rivals plan their jumps (and time the moving platforms and obstacles), sometimes hesitate, and brawl with whoever is next to them. **3 tries**: win the tower race to go on to round 2.

**Round 2: The Spike Run.** The same rivals, now on a long left-to-right course with a huge wall of spikes grinding along behind you, speeding up slowly. The course has three floors that braid together:

- **Splits**: a fast high road of short hops under a windmill, a middle road with a wall to vault and a hammer swinging over the gap, and a slow low road with a backward conveyor, spikes, a pit and a crusher slamming down from above.
- **Crossings**: an X of stairs where the top road steps down and the bottom road climbs up, so everyone meets in the middle, with a fruit cannon firing along the floor.
- **Arenas**: the roads squeeze onto one big platform with spikes below and a windmill above. Brawl here and knock rivals back into the wall.
- **? boxes**: jump into them for a snack (-35%) or a star (a few seconds where nothing can hit you, though the spike wall still can).
- Touch the spike wall and you are out of that try. Fall off the bottom and you drop back in just ahead of the wall at 0%. Reach the gate at the end first to win. **3 tries**: win one to clear the level.

### Level 12: Knee-Deep in the Demon

Doom with hadoukens. A hell fortress in first person under a blood-red sky: green-grey stone, keycards, doors, a secret wall, imps, pinkies, cacodemons, lost souls and zombiemen, possessed street fighters drawn with Third Strike sprites (**Ryu** throws hadoukens, **Chun-Li** dashes in with lightning legs and the odd kikoken), and **Cyber-Gief**, Mech Zangief from Marvel vs. Capcom, guarding the exit portal. Gief breathes ice in a three-way spread, headbutts you up close, and barrels in with a **shoulder charge**: sidestep it or shoryuken over him. Akuma's own clawed hands (prayer beads, red ki) and bare foot fill the bottom of the screen, above a Doom-style status bar.

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
  cars.py          level 3: car bonus rounds, the seven car models, the block-car boss
  fx.py            loads the fireball and explosion frames
  bomber.py        level 4: the Bomberman car park
  smash.py         level 5: Smash Bros on Hyrule Castle
  stealth.py       level 6: the Metal Gear base
  skate.py         level 7: the 720 skate park
  connect4.py      level 8: Connect Four and Ryu's search
  metroid.py       level 9: the Dead Cells style castle
  thunder.py       level 10: the Rolling Thunder street
  climb.py         level 11: the Fall Guys climbing race
  spikerun.py      level 11, round 2: the scrolling spike-wall run
  doom.py          level 12: the raycaster
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
tools/make_lubu.py           the Warden (level 9 boss): Ryu recoloured with armour and plumes
tools/make_drdoom.py         Dr. Doom: cuts Toshi's Dr. Doom sheet into frames
tools/make_doom_fighters.py  Doom level fighters: cuts the fightersgeneration.com gifs (art_source/fightersgeneration/) into ryu3s, chunli3s, mechgief
art_source/retired/          the earlier Akuma sheets' cut sprites and their tools (no longer used)
                             (the tools need pillow + numpy; not needed to play)
tests/smoke_test.py         headless tests: move mapping, damage tiers, a 5-hit combo, jump-in
                            combos, throws, practice menu, car roofs, Tetris repairs, bots that
                            play levels 1-4, every later level starting, and each level's test below
tests/<level>_test.py       bomber, smash, stealth, skate, connect4, metroid, thunder, climb, doom: each level's rules plus a bot that clears it
tests/pad_test.py           Xbox controller input with a fake pad: hot-plug, buttons, stick, triggers, menus
```

Run the test with `python tests/smoke_test.py`. It needs no window and no sound. The game needs pygame and numpy (`run.bat` installs both).
