# Antagonist

An original social-deduction foraging game. You are a stickman the size of an ant.
Your colony has to find a giant piece of food somewhere in the backyard and haul it
back to the nest before the timer runs out. One of you is a traitor.

**Play:** https://sv-gravity.github.io/stuff/antagonist/

## Rules

- Everyone starts at the nest. The big food (strawberry, cookie, cheese puff, gummy bear
  or donut) is hidden 12–17 m away. Once an honest ant spots it, everyone gets an arrow.
- Grab the food (Space) and push with your movement keys. **The food moves with the
  vector sum of every carrier's push**, minus friction. Nobody can lift it alone; one
  ant pulling the wrong way slows everyone down.
- Crumbs are lying around. Bring one home for +4 s on the clock.
- **Traitor:** always knows where the food is. Grab on and drag it the wrong way, steer it
  into rocks, trip an ant off it (Q, 9 s cooldown), or eat crumbs (Q while holding one;
  people nearby will see the munch).
- **Accusations:** stand next to an ant and press V. Votes are public (red dots). If a
  majority votes for the same ant, that ant is webbed. The traitor is webbed for the rest
  of the round; an innocent for 12 s, and their accusers lose their vote that round.
  The traitor can vote too, so watch for framing.
- **Scents:** when an honest ant spots the food, a scent arrow points everyone to it.
  Traitors can plant up to 2 fake scents a round (T) that look identical until an honest ant
  walks within sniffing range and exposes the fake.
- **Antennae meeting (M):** each ant can call one per round. Everyone freezes, chats and
  votes (majority webs the target, skip is allowed). The round clock keeps running, so a
  traitor can call one just to burn time. Bots talk in meetings, accuse, defend themselves,
  and the traitor bot frames people.
- **Two traitors** automatically at 8+ ants (or pick 1 or 2 in the menu). Traitors know each other.
- **Round-end replay:** the haul is replayed on a map with every carrier's push arrow (red
  = pulling away from the nest) and a "who pulled their weight" chart. Press Space to skip.
- Food home in time: the colony scores. Time runs out: the traitor scores. First to 3.
- Menu options: colony size 4–10, play as random / worker / traitor, and whether the
  traitor stays the same all match (as pitched) or is reshuffled each round.

## Controls

| Key | Action |
| --- | --- |
| WASD / arrows | move / push |
| Space or E | grab / let go of food or a crumb |
| Q or F | traitor: trip nearest ant, or eat held crumb |
| V or R | accuse the nearest ant (press again to withdraw) |
| M | call an antennae meeting (1–9 / 0 to vote, type to chat) |
| T | traitor: plant a fake scent where you stand |
| F3 | toggle FPS counter |

On phones and tablets there's a virtual joystick (left thumb, anywhere on the left half)
and big action buttons on the right.

## Performance

The sim runs at a fixed 60 Hz and reads input right before every step, and rendering
interpolates between steps. Static art (rocks, grass, leaves, food, nest) is pre-rendered
once per zoom level, the vision fog is cached, and the canvas resolution is capped so
retina and 4K screens don't tank the frame rate.
| Esc | menu |

## Code layout (built for multiplayer later)

Plain ES modules, no build step. Serve the repo root with any static server, e.g.
`python3 -m http.server` and open `/antagonist/`.

| File | Role |
| --- | --- |
| `src/sim.js` | Authoritative simulation. Pure data, fixed 30 Hz tick, seeded RNG, no DOM. `createMatch`, `step(state, inputs)`, `viewFor(state, playerId)` |
| `src/world.js` | Procedural yard generation from the seed |
| `src/bots.js` | Bot brains. They read only `viewFor(...)` and return the same input object a keyboard does |
| `src/session.js` | `LocalSession`: runs sim + bots in the browser tab |
| `src/render.js` | Canvas renderer; draws from a view, never the raw state |
| `src/input.js`, `src/sfx.js`, `src/main.js` | keyboard, synthesized sounds, loop and menu |
| `src/config.js` | all tuning numbers |

Multiplayer plan: a `NetSession` with the same `tick/view` interface. The host (or a small
Node/WebSocket server running `sim.js` unchanged) collects `{mx,my,grab,act,vote}` from each
player, steps the sim, and sends each client `viewFor(state, theirId)`. `viewFor` already
strips the traitor's identity and cooldown, so clients can't cheat by reading the network.
Bots fill empty seats on the host.

Balancing: `node` can run bot-only matches headlessly against `sim.js` + `bots.js`; with 6
ants the colony wins about 60–65% of rounds against a bot traitor.
