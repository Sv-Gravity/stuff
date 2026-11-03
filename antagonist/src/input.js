// Keyboard -> the same input object bots produce. Button presses are latched
// until the next sim tick consumes them, so a quick tap is never lost.
export class Keyboard {
  constructor() {
    this.down = new Set();
    this.latched = { grab: false, act: false, vote: false };
    addEventListener('keydown', e => {
      if (e.repeat) return;
      const k = e.key.toLowerCase();
      this.down.add(k);
      if (k === ' ' || k === 'e') this.latched.grab = true;
      if (k === 'q' || k === 'f') this.latched.act = true;
      if (k === 'v' || k === 'r') this.latched.vote = true;
      if ([' ', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k)) e.preventDefault();
    });
    addEventListener('keyup', e => this.down.delete(e.key.toLowerCase()));
    addEventListener('blur', () => this.down.clear());
  }
  sample() {
    const d = this.down;
    const mx = (d.has('d') || d.has('arrowright') ? 1 : 0) - (d.has('a') || d.has('arrowleft') ? 1 : 0);
    const my = (d.has('s') || d.has('arrowdown') ? 1 : 0) - (d.has('w') || d.has('arrowup') ? 1 : 0);
    const out = { mx, my, ...this.latched };
    this.latched = { grab: false, act: false, vote: false };
    return out;
  }
}
