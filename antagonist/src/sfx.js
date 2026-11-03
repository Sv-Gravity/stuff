// Tiny synthesized sound effects (no audio files needed).
export class Sfx {
  unlock() {
    if (!this.ctx) { try { this.ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch { this.ctx = null; } }
    this.ctx?.resume?.();
  }
  beep(freq, dur = 0.08, type = 'square', vol = 0.05, slide = 0) {
    const c = this.ctx; if (!c) return;
    const o = c.createOscillator(), g = c.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, c.currentTime);
    if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(40, freq + slide), c.currentTime + dur);
    g.gain.setValueAtTime(vol, c.currentTime); g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + dur);
    o.connect(g); g.connect(c.destination); o.start(); o.stop(c.currentTime + dur);
  }
  onEvents(view, events) {
    const me = view.me;
    for (const e of events) {
      const mine = e.id === me;
      if (e.t === 'grab' && mine) this.beep(520, 0.05);
      if (e.t === 'drop' && mine) this.beep(300, 0.05);
      if (e.t === 'trip') this.beep(mine ? 160 : 240, 0.18, 'sawtooth', 0.04, -100);
      if (e.t === 'crumb') this.beep(880, 0.12, 'triangle', 0.06, 400);
      if (e.t === 'eat' && Math.hypot(e.x - view.players[me].x, e.y - view.players[me].y) < 300) this.beep(120, 0.15, 'square', 0.04, -40);
      if (e.t === 'vote') this.beep(mine ? 700 : 600, 0.06, 'triangle', 0.04);
      if (e.t === 'caught') { this.beep(660, 0.15, 'triangle', 0.07); setTimeout(() => this.beep(990, 0.25, 'triangle', 0.07), 140); }
      if (e.t === 'wrong') this.beep(200, 0.35, 'sawtooth', 0.05, -120);
      if (e.t === 'found') this.beep(740, 0.2, 'triangle', 0.06, 300);
      if (e.t === 'go') this.beep(880, 0.2, 'square', 0.05);
      if (e.t === 'roundEnd') this.beep(e.winner === 'colony' ? 520 : 180, 0.5, 'triangle', 0.07, e.winner === 'colony' ? 520 : -80);
    }
  }
}
