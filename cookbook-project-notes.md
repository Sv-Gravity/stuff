# Fire in the Hole: A Cookbook — project notes

Toshi's CS2 utility notebook. One self-contained HTML file (`cookbook.html`) with lineups ("recipes"), settings ("The Pantry"), and per-map "Ingredients".

## Files
- `cookbook.html` — the whole book. Everything is embedded (images as WebP, no outside links needed).
- `autoexec.cfg`, `prac.cfg` — the configs shown in The Pantry.

## Style rules
- Very concise. No fluff descriptions. Toshi prunes, so keep it lean.
- No text baked into pictures, and captions don't repeat the step text.
- Dark theme matching the app (bg #12151a, panels #1b2028, lines #2f3947, text #e6eaf0, muted #8c98a9, orange accent #f5a524).
- Be precise with aim wording: name the exact feature the crosshair sits on (e.g. "left window of the chimney", not "left edge of the chimney"). Check the close-up before writing it.
- Never write "zoom" in captions. The close-up caption just says where the crosshair goes.
- No redundant names: if the section already says "B Site", the lineup is "Pillar", not "B Pillar".
- Write as a top-level pro coach who has played since 1.6: short, practical usage notes.

## Adding a lineup from a csnades.gg link
1. Read the page for side, technique (left/right/both click, jump), movement (stationary/run/walk/crouch) and the video URL (assets.csnades.gg/nades/<slug>/hq.webm). assets.csnades.gg is allowed in Toshi's settings.
2. Pull frames from the video. Four pictures, in this order:
   - **Stand here** — a wide shot with the exact spot circled in orange on the floor. If the video's stand frame is too close up, use a wider frame from earlier and circle the spot.
   - **Aim here** — the crosshair settled on the lineup.
   - **Close-up** — crop around the crosshair, captioned "Crosshair on <exact feature>".
   - **Result** — where it lands or pops, captioned just "Bon appétit" (shown in script). Skip fully white flashed frames.
   Trim the CSNADES.gg watermark off the top of each picture.
3. Entry fields: side, type (Smoke/Flash/Molotov/HE/Wall Spam), sections for both where it's thrown from and where it lands, and action icons set explicitly (jump, crouch, run, walk, left click, right click, both).
4. Steps: stand, aim, throw. No picture pointers like "(first picture)": the captions already say it.
5. When Toshi sends a batch, show previews first and only add to the file after he approves.

## YouTube lineups
No downloading YouTube videos. Toshi sends screenshots (stand, aim, pop) or his own recording instead, and they're processed the same way.

## Layout
- Front page: "FIRE IN THE HOLE / A COOKBOOK", line-art bowl with the HE, smoke, flash and plump banana, unlit molotov standing behind the bowl. The Pantry card, then the map list.
- Map pages: an icon bar at the top for jumping between maps (current map in orange). Ingredients sits at the end of the bar with a jar icon. No Pantry link on map pages.
- Ingredients page order: Callouts, Odds (round win split), Timings (earliest times only, as clock times), Default CT setup.
- Strats get a blue "Strat" pill and can be split into stages, each with its own steps and pictures. Players are lettered (A + B, X + Y + Z), never numbered.

## Still to do
- Banana rush flash from the YouTube video (needs Toshi's screenshots).
- Default CT setups for maps other than Inferno.
- Windows 11 section (Toshi will expand it first).
