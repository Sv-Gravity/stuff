// A "session" owns the authoritative state and decides where inputs come from.
// LocalSession runs everything in this tab (you + bots). A future NetSession
// would expose the same three methods: the host runs step() and broadcasts
// viewFor(state, id) to each client; clients just send their input.
import { createMatch, step, viewFor } from './sim.js';
import { Bot } from './bots.js';

export class LocalSession {
  constructor({ name, count, seed, sameTraitor, role, traitorCount }) {
    const players = [{ id: 0, name: name || 'You', isBot: false }];
    const botNames = ['Pip', 'Crumb', 'Dot', 'Twig', 'Mote', 'Speck', 'Nib', 'Grub', 'Fleck', 'Seed', 'Bean'];
    for (let i = 1; i < count; i++) players.push({ id: i, name: botNames[(i - 1) % botNames.length], isBot: true });
    this.opts = { players, seed, sameTraitor, traitorCount, forceTraitor: role === 'traitor' ? 0 : null, avoidTraitor: role === 'worker' ? 0 : null };
    this.localId = 0;
    this.reset(seed);
  }
  reset(seed) {
    this.state = createMatch({ ...this.opts, seed });
    this.bots = this.opts.players.filter(p => p.isBot).map(p => new Bot(p.id, seed));
  }
  /** Advance one tick with the local player's input. */
  tick(localInput) {
    const inputs = { [this.localId]: localInput };
    for (const b of this.bots) inputs[b.id] = b.think(viewFor(this.state, b.id));
    step(this.state, inputs);
    return this.state.events;
  }
  view() { return viewFor(this.state, this.localId); }
}
