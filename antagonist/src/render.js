// Canvas renderer. Draws only from a view (viewFor), never from the raw state.
import { CFG } from './config.js';
import { numTraitors } from './sim.js';

let groundPattern = null;
function makeGround() {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d');
  g.fillStyle = '#6b4f33'; g.fillRect(0, 0, 256, 256);
  let seed = 7;
  const r = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < 900; i++) {
    const v = r();
    g.fillStyle = v < 0.33 ? 'rgba(40,28,16,0.35)' : v < 0.66 ? 'rgba(140,110,75,0.30)' : 'rgba(90,70,45,0.5)';
    const s = 1 + r() * 3;
    g.fillRect(r() * 256, r() * 256, s, s);
  }
  for (let i = 0; i < 40; i++) {
    g.fillStyle = 'rgba(170,150,120,0.5)';
    g.beginPath(); g.arc(r() * 256, r() * 256, 1 + r() * 2.5, 0, 7); g.fill();
  }
  return c;
}

const ANT_DRAW = 1.9; // stickmen are drawn bigger than their hitbox so you can read them
const lerp = (a, b, t) => a + (b - a) * t;

export class Renderer {
  constructor(canvas) {
    this.c = canvas; this.g = canvas.getContext('2d', { alpha: false, desynchronized: true });
    this.sprites = new Map(); this.spriteZ = 0;
    this.fog = document.createElement('canvas');
    this.particles = []; this.floaters = [];
    this.cam = { x: 0, y: 0, z: 2 };
    this.prev = null;
    this.flash = null;
  }

  resize() {
    // Cap the backing-store size: fill-rate is the main cost on big/retina screens.
    const maxPx = 2.4e6;
    const dpr = Math.max(0.75, Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(maxPx / (innerWidth * innerHeight))));
    this.dpr = dpr;
    this.spriteZ = 0;
    this.c.width = innerWidth * dpr; this.c.height = innerHeight * dpr;
    this.fog.width = this.c.width; this.fog.height = this.c.height;
  }

  // Pre-render a static thing once at the current zoom; afterwards it's one drawImage.
  spr(key, half, fn) {
    let c = this.sprites.get(key);
    if (!c) {
      c = document.createElement('canvas');
      const px = Math.max(2, Math.ceil(half * 2 * this.spriteZ));
      c.width = c.height = px;
      const sg = c.getContext('2d');
      sg.setTransform(this.spriteZ, 0, 0, this.spriteZ, px / 2, px / 2);
      const old = this.g; this.g = sg; fn(); this.g = old;
      this.sprites.set(key, c);
    }
    return c;
  }
  blit(key, x, y, half, fn) { this.g.drawImage(this.spr(key, half, fn), x - half, y - half, half * 2, half * 2); }

  buildFog(W, H, z) {
    const fg = this.fog.getContext('2d');
    fg.globalCompositeOperation = 'source-over';
    fg.clearRect(0, 0, W, H);
    fg.fillStyle = 'rgba(12,8,4,0.86)'; fg.fillRect(0, 0, W, H);
    fg.globalCompositeOperation = 'destination-out';
    const R = CFG.VISION * z;
    const grd = fg.createRadialGradient(W / 2, H / 2, R * 0.55, W / 2, H / 2, R);
    grd.addColorStop(0, 'rgba(0,0,0,1)'); grd.addColorStop(1, 'rgba(0,0,0,0)');
    fg.fillStyle = grd; fg.beginPath(); fg.arc(W / 2, H / 2, R, 0, 7); fg.fill();
    fg.globalCompositeOperation = 'source-over';
  }

  // Interpolation between the last two sim ticks so movement stays smooth at any fps.
  snapshot(view) {
    const m = {};
    for (const p of view.players) m['p' + p.id] = [p.x, p.y];
    if (!view.food.hidden) m.food = [view.food.x, view.food.y];
    for (const c of view.crumbs) m['c' + c.id] = [c.x, c.y];
    return { round: view.round, m };
  }
  pos(key, x, y, a) {
    const pv = this.prev && this.prev.round === this.curRound ? this.prev.m[key] : null;
    return pv ? [lerp(pv[0], x, a), lerp(pv[1], y, a)] : [x, y];
  }

  onEvents(view, events) {
    for (const e of events) {
      const p = view.players.find(q => q.id === e.id);
      if (e.t === 'trip' && p) { this.burst(e.x, e.y, '#d8c8a0', 14); this.floater(e.x, e.y - 18, 'tripped!', '#ffd27a'); }
      if (e.t === 'eat') { this.burst(e.x, e.y, '#e9c27a', 10); this.floater(e.x, e.y - 18, '*munch*', '#ff9b6b'); }
      if (e.t === 'crumb') this.floater(e.x, e.y - 30, '+' + CFG.CRUMB_TIME + 's', '#9cff8a');
      if (e.t === 'caught' && p) { this.burst(p.x, p.y, '#ffffff', 30); this.flash = { text: `${p.name} WAS A TRAITOR! Webbed for the round`, t: 3.5, col: '#9cff8a' }; }
      if (e.t === 'wrong' && p) { this.burst(p.x, p.y, '#ffffff', 20); this.flash = { text: `${p.name} was innocent... the accusers lose their vote`, t: 3.5, col: '#ff8a8a' }; }
      if (e.t === 'meetingEnd') this.flash = { text: 'Nobody was voted out', t: 2.5, col: '#e8dcc8' };
      if (e.t === 'found') this.flash = { text: 'Someone smelled food! Follow the scent arrows', t: 3, col: '#ffe08a' };
      if (e.t === 'scent' && !view.amTraitor) this.flash = { text: 'A new food scent is in the air...', t: 3, col: '#ffb0d8' };
      if (e.t === 'scent' && view.amTraitor) this.flash = { text: 'Fake scent planted', t: 2, col: '#ff9b9b' };
      if (e.t === 'debunk') { this.flash = { text: `${p ? p.name : 'Someone'} sniffed out a FAKE scent!`, t: 3, col: '#ff9b6b' }; this.burst(e.x, e.y, '#ff9bd0', 24); }
      if (e.t === 'noscent' && e.id === view.me) this.flash = { text: 'Too close to the food or nest to plant a fake', t: 2, col: '#ff9b9b' };
      if (e.t === 'nomeet' && e.id === view.me) this.flash = { text: "Can't call a meeting right now", t: 2, col: '#e8dcc8' };
    }
  }
  burst(x, y, col, n) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * 7, s = 20 + Math.random() * 60;
      this.particles.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, t: 0.6 + Math.random() * 0.4, col });
    }
  }
  floater(x, y, text, col) { this.floaters.push({ x, y, text, col, t: 1.4 }); }

  draw(view, alpha, dt, ui) {
    this.curRound = view.round;
    const g = this.g, W = this.c.width, H = this.c.height, dpr = this.dpr;
    if (!groundPattern) groundPattern = g.createPattern(makeGround(), 'repeat');
    const me = view.players.find(p => p.id === view.me);
    const [mx, my] = me ? this.pos('p' + me.id, me.x, me.y, alpha) : [view.nest.x, view.nest.y];
    const z = Math.min(W, H) / (CFG.VISION * 1.75);
    this.cam = { x: mx, y: my, z };
    if (z !== this.spriteZ) { this.sprites.clear(); this.spriteZ = z; this.buildFog(W, H, z); }
    const sx = x => (x - mx) * z + W / 2, sy = y => (y - my) * z + H / 2;

    g.setTransform(1, 0, 0, 1, 0, 0);
    g.fillStyle = '#1b130c'; g.fillRect(0, 0, W, H);
    g.setTransform(z, 0, 0, z, W / 2 - mx * z, H / 2 - my * z);
    // ground
    const hw = W / z / 2 + 2, hh = H / z / 2 + 2;
    const gx0 = Math.max(0, mx - hw), gy0 = Math.max(0, my - hh);
    g.fillStyle = groundPattern; g.fillRect(gx0, gy0, Math.min(CFG.WORLD_W, mx + hw) - gx0, Math.min(CFG.WORLD_H, my + hh) - gy0);
    g.strokeStyle = '#2a1d10'; g.lineWidth = 6; g.strokeRect(0, 0, CFG.WORLD_W, CFG.WORLD_H);

    const vis = (x, y, pad = 0) => Math.abs(x - mx) < W / z / 2 + pad && Math.abs(y - my) < H / z / 2 + pad;

    for (const q of view.puddles) if (vis(q.x, q.y, q.r)) this.puddle(q);
    const n = view.nest;
    if (vis(n.x, n.y, 80)) { this.blit('nest', n.x, n.y, n.r * 1.6 + 14, () => this.nest({ x: 0, y: 0, r: n.r })); this.nestLabel(n); }
    view.decor.forEach((d, i) => { if (d.t !== 'grass' && vis(d.x, d.y, 50)) this.blit('d' + i, d.x, d.y, 45 * d.s, () => this.decor({ ...d, x: 0, y: 0 })); });
    // scent clouds (real and fake look the same unless you planted it)
    const tnow = performance.now() / 1000;
    for (const sc of view.scents) {
      if (!vis(sc.x, sc.y, 60)) continue;
      for (let i = 0; i < 3; i++) {
        const rr = 18 + ((tnow * 14 + i * 14) % 42);
        g.strokeStyle = sc.fake ? `rgba(255,120,120,${0.5 - rr / 120})` : `rgba(255,150,210,${0.5 - rr / 120})`;
        g.lineWidth = 1.5; g.beginPath(); g.arc(sc.x, sc.y, rr, 0, 7); g.stroke();
      }
    }

    // crumbs
    for (const c of view.crumbs) {
      if (!c.alive) continue;
      const [cx, cy] = this.pos('c' + c.id, c.x, c.y, alpha);
      if (!vis(cx, cy, 10)) continue;
      g.fillStyle = ['#e7c48a', '#d9a35c', '#f2dcb0'][c.kind];
      g.strokeStyle = '#7a5a2e'; g.lineWidth = 0.6;
      g.beginPath(); g.moveTo(cx - 3.5, cy + 2); g.lineTo(cx - 1, cy - 3.5); g.lineTo(cx + 3.5, cy - 1); g.lineTo(cx + 2, cy + 3); g.closePath(); g.fill(); g.stroke();
    }

    // depth-sorted things: rocks, food, ants, grass
    const items = [];
    view.rocks.forEach((k, i) => { if (vis(k.x, k.y, k.r * 1.4)) items.push({ y: k.y + k.r * 0.4, f: () => this.blit('r' + i, k.x, k.y, k.r * 1.4, () => this.rock({ x: 0, y: 0, r: k.r })) }); });
    view.decor.forEach((d, i) => { if (d.t === 'grass' && vis(d.x, d.y, 70)) items.push({ y: d.y, f: () => this.blit('g' + i, d.x, d.y - 30 * d.s, 40 * d.s, () => this.grass({ ...d, x: 0, y: 30 * d.s })) }); });
    const [fx, fy] = view.food.hidden ? [NaN, NaN] : this.pos('food', view.food.x, view.food.y, alpha);
    if (!view.food.hidden) items.push({ y: fy, f: () => {
      const f = view.food;
      g.fillStyle = 'rgba(0,0,0,0.3)'; g.beginPath(); g.ellipse(fx + 4, fy + f.r * 0.5, f.r * 1.05, f.r * 0.5, 0, 0, 7); g.fill();
      const spin = f.kind === 'cookie' || f.kind === 'cheeseball' || f.kind === 'donut';
      const c = this.spr('food-' + f.kind, f.r * 1.3, () => this.food({ ...f, rot: 0 }, 0, 0));
      g.save(); g.translate(fx, fy - f.r * 0.15); if (spin) g.rotate(f.rot);
      g.drawImage(c, -f.r * 1.3, -f.r * 1.3, f.r * 2.6, f.r * 2.6); g.restore();
    } });
    for (const p of view.players) {
      const [px, py] = this.pos('p' + p.id, p.x, p.y, alpha);
      const far = Math.hypot(px - mx, py - my) > CFG.VISION + 20;
      if (far && p.id !== view.me) continue;
      items.push({ y: py, f: () => this.ant(view, p, px, py) });
    }
    items.sort((a, b) => a.y - b.y);
    for (const it of items) it.f();

    // particles
    for (const pt of this.particles) {
      pt.x += pt.vx * dt; pt.y += pt.vy * dt; pt.vx *= 0.92; pt.vy *= 0.92; pt.t -= dt;
      g.globalAlpha = Math.max(0, Math.min(1, pt.t * 2)); g.fillStyle = pt.col;
      g.fillRect(pt.x - 1, pt.y - 1, 2, 2);
    }
    g.globalAlpha = 1;
    this.particles = this.particles.filter(p => p.t > 0);

    // labels & votes on top
    for (const p of view.players) {
      const [px, py] = this.pos('p' + p.id, p.x, p.y, alpha);
      if (Math.hypot(px - mx, py - my) > CFG.VISION + 20) continue;
      this.label(view, p, px, py);
    }
    for (const f of this.floaters) {
      f.t -= dt; f.y -= dt * 14;
      g.globalAlpha = Math.max(0, Math.min(1, f.t));
      g.font = 'bold 8px system-ui'; g.textAlign = 'center';
      g.fillStyle = '#000'; g.fillText(f.text, f.x + 0.6, f.y + 0.6);
      g.fillStyle = f.col; g.fillText(f.text, f.x, f.y);
    }
    g.globalAlpha = 1;
    this.floaters = this.floaters.filter(f => f.t > 0);

    // fog of vision (pre-rendered; the camera always centres on you)
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.drawImage(this.fog, 0, 0);

    this.hud(view, me, ui, dt, sx, sy, fx, fy);
  }

  puddle(q) {
    const g = this.g;
    g.fillStyle = 'rgba(70,120,160,0.55)';
    g.beginPath(); g.ellipse(q.x, q.y, q.r, q.r * 0.8, 0, 0, 7); g.fill();
    g.strokeStyle = 'rgba(200,230,255,0.35)'; g.lineWidth = 1.5;
    const t = performance.now() / 1000;
    for (let i = 0; i < 2; i++) {
      const rr = ((t * 10 + i * q.r / 2) % q.r) * 0.8;
      g.beginPath(); g.ellipse(q.x, q.y, rr, rr * 0.8, 0, 0, 7); g.stroke();
    }
  }

  nest(n) {
    const g = this.g;
    g.fillStyle = '#8a6a44';
    g.beginPath(); g.ellipse(n.x, n.y, n.r * 1.5, n.r * 1.25, 0, 0, 7); g.fill();
    g.fillStyle = '#a07c50';
    g.beginPath(); g.ellipse(n.x, n.y - 3, n.r * 1.2, n.r * 0.95, 0, 0, 7); g.fill();
    const grd = g.createRadialGradient(n.x, n.y, 2, n.x, n.y, n.r * 0.8);
    grd.addColorStop(0, '#000'); grd.addColorStop(1, '#2a1a0c');
    g.fillStyle = grd; g.beginPath(); g.ellipse(n.x, n.y, n.r * 0.7, n.r * 0.55, 0, 0, 7); g.fill();
  }
  nestLabel(n) {
    const g = this.g;
    g.fillStyle = 'rgba(255,240,200,0.8)'; g.font = 'bold 9px system-ui'; g.textAlign = 'center';
    g.fillText('NEST', n.x, n.y - n.r * 1.25 - 4);
  }

  rock(k) {
    const g = this.g;
    g.fillStyle = 'rgba(0,0,0,0.3)';
    g.beginPath(); g.ellipse(k.x + k.r * 0.15, k.y + k.r * 0.25, k.r * 1.05, k.r * 0.85, 0, 0, 7); g.fill();
    const grd = g.createRadialGradient(k.x - k.r * 0.35, k.y - k.r * 0.45, k.r * 0.1, k.x, k.y, k.r * 1.1);
    grd.addColorStop(0, '#c9c3b8'); grd.addColorStop(0.6, '#8e877c'); grd.addColorStop(1, '#5a544c');
    g.fillStyle = grd; g.beginPath(); g.ellipse(k.x, k.y, k.r, k.r * 0.92, 0, 0, 7); g.fill();
    g.fillStyle = 'rgba(255,255,255,0.12)';
    g.beginPath(); g.ellipse(k.x - k.r * 0.3, k.y - k.r * 0.4, k.r * 0.3, k.r * 0.18, -0.5, 0, 7); g.fill();
  }

  grass(d) {
    const g = this.g;
    g.lineCap = 'round';
    for (let i = 0; i < 5; i++) {
      const a = -Math.PI / 2 + (i - 2) * 0.25 + Math.sin(d.a + i) * 0.1;
      const L = (28 + (i % 3) * 10) * d.s;
      const bend = Math.sin(performance.now() / 900 + d.a + i) * 3;
      g.strokeStyle = i % 2 ? '#4f8a2e' : '#3e7024'; g.lineWidth = 2.6 * d.s;
      g.beginPath(); g.moveTo(d.x + (i - 2) * 2, d.y);
      g.quadraticCurveTo(d.x + (i - 2) * 3 + Math.cos(a) * L * 0.5, d.y + Math.sin(a) * L * 0.5, d.x + Math.cos(a) * L + bend, d.y + Math.sin(a) * L);
      g.stroke();
    }
  }

  decor(d) {
    const g = this.g;
    g.save(); g.translate(d.x, d.y); g.rotate(d.a); g.scale(d.s, d.s);
    if (d.t === 'leaf') {
      g.fillStyle = '#7d6b2a'; g.beginPath(); g.ellipse(0, 0, 26, 11, 0, 0, 7); g.fill();
      g.strokeStyle = '#5a4c1c'; g.lineWidth = 1; g.beginPath(); g.moveTo(-26, 0); g.lineTo(26, 0); g.stroke();
    } else if (d.t === 'twig') {
      g.strokeStyle = '#4a3420'; g.lineWidth = 4; g.lineCap = 'round';
      g.beginPath(); g.moveTo(-40, 0); g.lineTo(40, 3); g.moveTo(10, 1); g.lineTo(24, -12); g.stroke();
    } else {
      g.fillStyle = '#3f7a2a';
      for (let i = 0; i < 3; i++) { g.beginPath(); g.ellipse(Math.cos(i * 2.1) * 8, Math.sin(i * 2.1) * 8, 9, 7, i * 2.1, 0, 7); g.fill(); }
    }
    g.restore();
  }

  food(f, x, y) {
    const g = this.g, r = f.r;
    g.save(); g.translate(x, y);
    if (f.kind === 'strawberry') {
      g.fillStyle = '#d6283a'; g.beginPath(); g.moveTo(0, r); g.bezierCurveTo(r * 1.3, r * 0.2, r * 0.9, -r, 0, -r * 0.8); g.bezierCurveTo(-r * 0.9, -r, -r * 1.3, r * 0.2, 0, r); g.fill();
      g.fillStyle = '#f5e08a';
      for (let i = 0; i < 22; i++) { const a = i * 2.4, d = (i % 5 + 1) / 6 * r * 0.75; g.fillRect(Math.cos(a) * d * 0.9 - 1, Math.sin(a) * d * 0.8 + r * 0.05 - 1, 2, 2.6); }
      g.fillStyle = '#3c9a33';
      for (let i = 0; i < 5; i++) { g.save(); g.translate(0, -r * 0.75); g.rotate(-Math.PI / 2 + (i - 2) * 0.55); g.beginPath(); g.ellipse(r * 0.25, 0, r * 0.3, r * 0.1, 0, 0, 7); g.fill(); g.restore(); }
    } else if (f.kind === 'cookie') {
      g.rotate(f.rot);
      g.fillStyle = '#c98d48'; g.beginPath(); g.arc(0, 0, r, 0, 7); g.fill();
      g.strokeStyle = '#9c6a30'; g.lineWidth = 2; g.stroke();
      g.fillStyle = '#4a2a14';
      for (let i = 0; i < 9; i++) { const a = i * 2.3, d = (i % 3 + 1) / 3.6 * r; g.beginPath(); g.ellipse(Math.cos(a) * d, Math.sin(a) * d, 4, 3, a, 0, 7); g.fill(); }
    } else if (f.kind === 'cheeseball') {
      g.rotate(f.rot);
      g.fillStyle = '#f39a1e'; g.beginPath();
      for (let i = 0; i <= 20; i++) { const a = i / 20 * Math.PI * 2, rr = r * (0.85 + 0.15 * Math.sin(i * 3.3)); g.lineTo(Math.cos(a) * rr, Math.sin(a) * rr); }
      g.fill(); g.fillStyle = '#ffc04a'; g.beginPath(); g.arc(-r * 0.3, -r * 0.3, r * 0.35, 0, 7); g.fill();
    } else if (f.kind === 'gummy') {
      g.fillStyle = 'rgba(60,200,90,0.9)';
      g.beginPath(); g.ellipse(0, r * 0.2, r * 0.7, r * 0.8, 0, 0, 7); g.fill();
      g.beginPath(); g.arc(0, -r * 0.65, r * 0.45, 0, 7); g.fill();
      g.beginPath(); g.arc(-r * 0.4, -r, r * 0.17, 0, 7); g.arc(r * 0.4, -r, r * 0.17, 0, 7); g.fill();
      g.fillStyle = 'rgba(255,255,255,0.35)'; g.beginPath(); g.ellipse(-r * 0.25, 0, r * 0.15, r * 0.35, 0.3, 0, 7); g.fill();
    } else {
      g.fillStyle = '#d9a35c'; g.beginPath(); g.arc(0, 0, r, 0, 7); g.fill();
      g.fillStyle = '#f07ab0'; g.beginPath(); g.arc(0, 0, r * 0.88, 0, 7); g.fill();
      g.fillStyle = '#6b4f33'; g.beginPath(); g.arc(0, 0, r * 0.3, 0, 7); g.fill();
      const cols = ['#fff', '#7af', '#ff7', '#7f7'];
      g.save(); g.rotate(f.rot);
      for (let i = 0; i < 16; i++) { const a = i * 2.2, d = r * (0.45 + (i % 3) * 0.13); g.fillStyle = cols[i % 4]; g.save(); g.translate(Math.cos(a) * d, Math.sin(a) * d); g.rotate(a * 3); g.fillRect(-2.5, -0.8, 5, 1.6); g.restore(); }
      g.restore();
    }
    g.restore();
  }

  ant(view, p, x, y) {
    const g = this.g;
    const webbed = p.web > 0, stunned = p.stun > 0;
    const right = Math.cos(p.face) >= 0 ? 1 : -1;
    const carrying = p.hold === 'food';
    const pushX = carrying ? p.push.x : 0, pushY = carrying ? p.push.y : 0;
    const lean = carrying ? pushX * 3 : (p.moving ? right * 1.2 : 0);
    const sw = p.moving ? Math.sin(p.walk * 2.2) : 0;
    g.save(); g.translate(x, y); g.scale(ANT_DRAW, ANT_DRAW);
    g.fillStyle = 'rgba(0,0,0,0.35)'; g.beginPath(); g.ellipse(0, 0, 4, 1.6, 0, 0, 7); g.fill();
    g.save();
    if (stunned) g.rotate(Math.sin(performance.now() / 60) * 0.3 + 1.2 * right);
    g.strokeStyle = p.color; g.fillStyle = p.color; g.lineWidth = 1.3; g.lineCap = 'round';
    const hipX = lean * 0.3, hipY = -5, nX = lean, nY = -10.5;
    g.beginPath();
    g.moveTo(hipX, hipY); g.lineTo(hipX + sw * 2.4 - pushX * 1.5, -0.2 - pushY * 0.5);
    g.moveTo(hipX, hipY); g.lineTo(hipX - sw * 2.4 - pushX * 1.5, -0.2 + pushY * 0.5);
    g.moveTo(hipX, hipY); g.lineTo(nX, nY);
    if (carrying) {
      // arms reaching to the food (toward slot center) and straining in the push direction
      const toF = { x: -Math.cos(p.slot), y: -Math.sin(p.slot) };
      g.moveTo(nX, nY + 1); g.lineTo(nX + toF.x * 4 + pushX * 2, nY - 1.5 + toF.y * 2);
      g.moveTo(nX, nY + 1); g.lineTo(nX + toF.x * 4 + pushX * 2.5, nY + 1.5 + toF.y * 2);
    } else if (typeof p.hold === 'number') {
      g.moveTo(nX, nY + 1); g.lineTo(nX + right * 2, nY - 4); g.moveTo(nX, nY + 1); g.lineTo(nX + right * 3.5, nY - 3.5);
    } else {
      g.moveTo(nX, nY + 1); g.lineTo(nX - sw * 2.5, nY + 5);
      g.moveTo(nX, nY + 1); g.lineTo(nX + sw * 2.5, nY + 5);
    }
    g.stroke();
    g.beginPath(); g.arc(nX + right * 0.3, nY - 2.2, 2.2, 0, 7); g.fill();
    g.fillStyle = '#111'; g.fillRect(nX + right * 1.1 - 0.4, nY - 2.8, 0.8, 0.8);
    // tiny antennae – we are basically ants
    g.strokeStyle = p.color; g.lineWidth = 0.5;
    g.beginPath(); g.moveTo(nX, nY - 4); g.lineTo(nX + right * 1.5, nY - 6.5); g.moveTo(nX + right * 0.8, nY - 4); g.lineTo(nX + right * 2.8, nY - 6); g.stroke();
    if (typeof p.hold === 'number') { g.fillStyle = '#e7c48a'; g.fillRect(nX + right * 2 - 2, nY - 8, 4, 3.5); }
    g.restore();
    if (webbed) {
      g.strokeStyle = 'rgba(255,255,255,0.75)'; g.lineWidth = 0.5;
      for (let i = 0; i < 6; i++) { const a = i * 1.05; g.beginPath(); g.moveTo(Math.cos(a) * 8, -6 + Math.sin(a) * 9); g.lineTo(-Math.cos(a) * 8, -6 - Math.sin(a) * 9); g.stroke(); }
      g.beginPath(); g.ellipse(0, -6, 5, 7, 0, 0, 7); g.stroke();
    }
    if (stunned) {
      const t = performance.now() / 200;
      g.fillStyle = '#ffe36b';
      for (let i = 0; i < 3; i++) { const a = t + i * 2.1; g.fillRect(Math.cos(a) * 5 - 0.7, -15 + Math.sin(a) * 1.5, 1.4, 1.4); }
    }
    if (p.id === view.me) {
      g.strokeStyle = 'rgba(255,255,255,0.7)'; g.lineWidth = 0.7;
      g.beginPath(); g.ellipse(0, 0, 6.5, 2.6, 0, 0, 7); g.stroke();
    }
    g.restore();
  }

  label(view, p, x, y) {
    const g = this.g;
    g.font = 'bold 9px system-ui'; g.textAlign = 'center';
    const isT = view.traitors.includes(p.id);
    const txt = p.name + (isT ? ' (traitor)' : '');
    g.fillStyle = 'rgba(0,0,0,0.6)'; g.fillText(txt, x + 0.5, y - 17.5 * ANT_DRAW);
    g.fillStyle = isT ? '#ff6b6b' : (p.id === view.me ? '#fff' : 'rgba(255,255,255,0.8)');
    g.fillText(txt, x, y - 18 * ANT_DRAW);
    const votes = view.players.filter(q => q.vote === p.id && q.web <= 0).length;
    if (votes > 0) {
      for (let i = 0; i < votes; i++) {
        g.fillStyle = '#ff4747'; g.beginPath(); g.arc(x - (votes - 1) * 4 + i * 8, y - 18 * ANT_DRAW - 10, 3, 0, 7); g.fill();
      }
    }
    const me = view.players.find(q => q.id === view.me);
    if (me && me.vote === p.id) {
      g.strokeStyle = '#ff4747'; g.lineWidth = 0.8; g.setLineDash([1.5, 1.5]);
      g.beginPath(); g.arc(x, y - 6 * ANT_DRAW, 10 * ANT_DRAW, 0, 7); g.stroke(); g.setLineDash([]);
    }
  }

  arrowTo(W, H, tx, ty, col, text) {
    const g = this.g, dpr = this.dpr;
    const dx = tx - W / 2, dy = ty - H / 2;
    const m = 50 * dpr, mt = 110 * dpr;
    if (tx > m && ty > mt && tx < W - m && ty < H - m) return;
    const a = Math.atan2(dy, dx);
    const k = Math.min((W / 2 - m) / Math.abs(Math.cos(a) || 1e-9), ((Math.sin(a) < 0 ? H / 2 - mt : H / 2 - m)) / Math.abs(Math.sin(a) || 1e-9));
    const x = W / 2 + Math.cos(a) * k, y = H / 2 + Math.sin(a) * k;
    g.save(); g.translate(x, y); g.rotate(a);
    g.fillStyle = col; g.beginPath(); g.moveTo(14 * dpr, 0); g.lineTo(-6 * dpr, -8 * dpr); g.lineTo(-6 * dpr, 8 * dpr); g.closePath(); g.fill();
    g.restore();
    g.font = `bold ${11 * dpr}px system-ui`; g.textAlign = 'center'; g.fillStyle = col;
    const off = 18 * dpr + Math.abs(Math.cos(a)) * g.measureText(text).width / 2;
    g.fillText(text, x - Math.cos(a) * off, y - Math.sin(a) * 22 * dpr + 4 * dpr);
  }

  hud(view, me, ui, dt, sx, sy, fx, fy) {
    const g = this.g, W = this.c.width, H = this.c.height, d = this.dpr;
    g.setTransform(1, 0, 0, 1, 0, 0);
    const playing = view.phase === 'play' || view.phase === 'countdown';
    if (playing) {
      this.arrowTo(W, H, sx(view.nest.x), sy(view.nest.y), '#ffe9b0', 'nest ' + Math.round(Math.hypot(view.nest.x - me.x, view.nest.y - me.y) / 10) + 'cm');
      if (view.amTraitor) {
        this.arrowTo(W, H, sx(view.food.x), sy(view.food.y), '#ff6b8a', view.foodFound ? 'food' : 'food (only you know)');
        for (const sc of view.scents) if (sc.fake) this.arrowTo(W, H, sx(sc.x), sy(sc.y), '#ff9b9b', 'your fake');
      } else {
        for (const sc of view.scents) this.arrowTo(W, H, sx(sc.x), sy(sc.y), '#ff9bd0', 'scent');
      }
    }

    // timer + score
    const t = Math.max(0, view.timeLeft);
    const ts = `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
    g.textAlign = 'center';
    g.font = `bold ${30 * d}px system-ui`;
    g.fillStyle = t < 15 && view.phase === 'play' ? (Math.floor(t * 2) % 2 ? '#ff5050' : '#fff') : '#fff';
    g.fillText(ts, W / 2, 40 * d);
    g.font = `${13 * d}px system-ui`; g.fillStyle = '#cdb';
    g.fillText(`Round ${view.round}`, W / 2, 58 * d);
    const pips = (n, col, x, align) => {
      for (let i = 0; i < CFG.WIN_POINTS; i++) {
        g.fillStyle = i < n ? col : 'rgba(255,255,255,0.15)';
        g.beginPath(); g.arc(x + (align * i * 16) * d, 52 * d, 6 * d, 0, 7); g.fill();
      }
    };
    g.font = `bold ${14 * d}px system-ui`;
    g.textAlign = 'right'; g.fillStyle = '#9cf4a0'; g.fillText('COLONY', W / 2 - 80 * d, 30 * d);
    pips(view.score.colony, '#9cf4a0', W / 2 - 92 * d, -1);
    g.textAlign = 'left'; g.fillStyle = '#ff7a7a'; g.fillText(numTraitors(view) > 1 ? 'TRAITORS' : 'TRAITOR', W / 2 + 80 * d, 30 * d);
    pips(view.score.traitor, '#ff7a7a', W / 2 + 92 * d, 1);

    // role + status panel
    const small = W < 700 * d;
    g.textAlign = 'left';
    g.font = `bold ${14 * d}px system-ui`;
    g.fillStyle = view.amTraitor ? '#ff6b6b' : '#9cf4a0';
    const partners = view.amTraitor ? view.traitors.filter(id => id !== view.me).map(id => view.players.find(p => p.id === id)?.name) : [];
    g.fillText(view.amTraitor ? 'YOU ARE A TRAITOR' + (partners.length ? ` (with ${partners.join(', ')})` : '') : 'YOU ARE A WORKER', 16 * d, small ? 84 * d : 28 * d);
    g.font = `${12 * d}px system-ui`; g.fillStyle = '#e8dcc8';
    const lines = [];
    const f = view.food;
    if (me.hold === 'food') {
      const spd = Math.hypot(f.vx, f.vy);
      lines.push(`Carrying with ${f.carriers} ant${f.carriers === 1 ? '' : 's'} · ${spd < 2 ? 'not moving' : (spd / 10).toFixed(1) + ' cm/s'}`);
    } else if (typeof me.hold === 'number') lines.push(view.amTraitor ? 'Holding a crumb · Q to eat it (risky!)' : 'Holding a crumb · bring it home for +' + CFG.CRUMB_TIME + 's');
    if (me.stun > 0) lines.push('You tripped!');
    if (me.web > 0) lines.push(me.web > 1000 ? 'Caught and webbed for the rest of the round' : `Webbed! ${Math.ceil(me.web)}s`);
    if (view.amTraitor) {
      lines.push(me.tripCd > 0 ? `Trip ready in ${Math.ceil(me.tripCd)}s` : 'Trip ready (Q near an ant)');
      if (me.scentsLeft > 0) lines.push(me.scentCd > 0 ? `Fake scent in ${Math.ceil(me.scentCd)}s (${me.scentsLeft} left)` : `T: plant a fake scent here (${me.scentsLeft} left)`);
    }
    lines.push(me.voteLocked ? 'You lost your accusation this round' : me.vote !== null ? `Accusing ${view.players.find(p => p.id === me.vote)?.name}` : 'V next to an ant to accuse');
    lines.push(me.meetUsed ? 'Meeting used' : 'M: call an antennae meeting (once a round)');
    if (ui?.touch) for (let i = 0; i < lines.length; i++) lines[i] = lines[i].replace('Q near an ant', 'TRIP near an ant').replace('Q to eat', 'EAT to eat').replace('T: plant', 'FAKE SCENT: plant').replace('V next to', 'ACCUSE next to').replace('M: call', 'MEET: call');
    if (!small || view.phase === 'play') lines.forEach((l, i) => g.fillText(l, 16 * d, ((small ? 102 : 48) + i * 17) * d));

    if (!ui?.touch) {
      g.font = `${11 * d}px system-ui`; g.fillStyle = 'rgba(255,255,255,0.55)';
      g.fillText(view.amTraitor
        ? 'WASD move · Space grab · Q trip / eat crumb · T fake scent · V accuse · M meeting · Esc menu'
        : 'WASD move · Space grab/let go · V accuse · M meeting · Esc menu', 16 * d, H - 16 * d);
    }
    if (ui?.fps) {
      g.textAlign = 'right'; g.font = `${11 * d}px ui-monospace, monospace`; g.fillStyle = 'rgba(255,255,255,0.6)';
      g.fillText(`${ui.fps} fps`, W - 12 * d, 72 * d);
    }

    if (this.flash) {
      this.flash.t -= dt;
      g.globalAlpha = Math.max(0, Math.min(1, this.flash.t));
      g.textAlign = 'center'; g.font = `bold ${(small ? 14 : 18) * d}px system-ui`;
      g.fillStyle = '#000'; g.fillText(this.flash.text, W / 2 + 2, H * 0.2 + 2);
      g.fillStyle = this.flash.col; g.fillText(this.flash.text, W / 2, H * 0.2);
      g.globalAlpha = 1;
      if (this.flash.t <= 0) this.flash = null;
    }

    const banner = (title, sub, col, sub2, y0 = H * 0.36, h = H * 0.28) => {
      g.fillStyle = 'rgba(0,0,0,0.6)'; g.fillRect(0, y0, W, h);
      g.textAlign = 'center'; g.fillStyle = col; g.font = `bold ${(small ? 24 : 38) * d}px system-ui`;
      g.fillText(title, W / 2, y0 + (small ? 40 : 56) * d);
      g.fillStyle = '#f0e6d2'; g.font = `${(small ? 13 : 16) * d}px system-ui`;
      g.fillText(sub, W / 2, y0 + (small ? 64 : 86) * d);
      if (sub2) { g.fillStyle = 'rgba(255,255,255,0.6)'; g.font = `${13 * d}px system-ui`; g.fillText(sub2, W / 2, y0 + (small ? 84 : 110) * d); }
    };
    if (view.phase === 'countdown') {
      banner(view.amTraitor ? 'YOU ARE A TRAITOR' : 'YOU ARE A WORKER',
        view.amTraitor ? `Stop them hauling ${view.food.label} home. Pretend to help.` : `Find ${view.food.label} and haul it to the nest. Someone is lying.`,
        view.amTraitor ? '#ff6b6b' : '#9cf4a0', `Starting in ${Math.ceil(view.phaseT)}...`);
    } else if (view.phase === 'roundEnd' || view.phase === 'matchEnd') {
      const r = view.result, tn = r.traitors.map(id => view.players.find(p => p.id === id)?.name).join(' & ');
      const many = r.traitors.length > 1;
      const title = view.phase === 'matchEnd'
        ? (view.winner === 'colony' ? 'THE COLONY WINS THE MATCH' : `THE TRAITOR${many ? 'S WIN' : ' WINS'} THE MATCH`)
        : (r.winner === 'colony' ? 'FOOD DELIVERED!' : "TIME'S UP!");
      const sub = r.winner === 'colony'
        ? (r.reason === 'caught' ? `Colony scores. ${tn} ${many ? 'were' : 'was'} the traitor${many ? 's' : ''} (caught!).` : `Colony scores. The traitor${many ? 's were' : ' was'} ${tn}.`)
        : `The traitor${many ? 's' : ''} (${tn}) score${many ? '' : 's'}.`;
      const next = view.phase === 'matchEnd' ? (ui?.touch ? 'Tap to play again' : 'Enter: rematch · Esc: menu')
        : `${ui?.touch ? 'Tap' : 'Space'} to continue${me.ready ? ' (waiting...)' : ''} · next round in ${Math.ceil(view.phaseT)}`;
      banner(title, sub, (view.phase === 'matchEnd' ? view.winner : r.winner) === 'colony' ? '#9cf4a0' : '#ff6b6b', next, H * 0.05, small ? 100 * d : 124 * d);
      this.replayPanel(view, H * 0.05 + (small ? 108 : 134) * d);
    }
  }

  // Round-end reveal: the haul replayed with everyone's push arrows, plus who really helped.
  replayPanel(view, top) {
    const g = this.g, W = this.c.width, H = this.c.height, d = this.dpr;
    const rp = view.replay;
    const small = W < 700 * d;
    const pad = 16 * d;
    const boxH = H - top - pad;
    const mapW = small ? W - pad * 2 : Math.min(W * 0.55, boxH * 1.4);
    const mapH = small ? boxH * 0.55 : boxH;
    const mx0 = small ? pad : W / 2 - (mapW + Math.min(360 * d, W * 0.35)) / 2, my0 = top;
    g.fillStyle = 'rgba(10,7,4,0.85)'; g.fillRect(mx0, my0, mapW, mapH);
    g.strokeStyle = 'rgba(255,220,160,0.25)'; g.strokeRect(mx0, my0, mapW, mapH);
    if (rp.length > 1) {
      let x0 = view.nest.x, x1 = view.nest.x, y0 = view.nest.y, y1 = view.nest.y;
      for (const [x, y] of rp) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      const m = 120; x0 -= m; y0 -= m; x1 += m; y1 += m;
      const k = Math.min(mapW / (x1 - x0), mapH / (y1 - y0));
      const ox = mx0 + (mapW - (x1 - x0) * k) / 2 - x0 * k, oy = my0 + (mapH - (y1 - y0) * k) / 2 - y0 * k;
      const X = x => ox + x * k, Y = y => oy + y * k;
      g.save(); g.beginPath(); g.rect(mx0, my0, mapW, mapH); g.clip();
      g.fillStyle = 'rgba(140,135,125,0.5)';
      for (const r of view.rocks) { g.beginPath(); g.arc(X(r.x), Y(r.y), r.r * k, 0, 7); g.fill(); }
      g.fillStyle = 'rgba(70,120,160,0.5)';
      for (const q of view.puddles) { g.beginPath(); g.arc(X(q.x), Y(q.y), q.r * k, 0, 7); g.fill(); }
      g.fillStyle = '#a07c50'; g.beginPath(); g.arc(X(view.nest.x), Y(view.nest.y), Math.max(4 * d, view.nest.r * k), 0, 7); g.fill();
      // full path faint, progress bright
      const prog = Math.min(1, Math.max(0, (CFG.INTERMISSION - view.phaseT) / (CFG.INTERMISSION * 0.8)));
      const idx = view.phase === 'matchEnd' ? rp.length - 1 : Math.floor(prog * (rp.length - 1));
      g.fillStyle = '#ffe9b0'; g.font = `bold ${10 * d}px system-ui`; g.textAlign = 'center';
      g.fillText('NEST', X(view.nest.x), Y(view.nest.y) - Math.max(4 * d, view.nest.r * k) - 4 * d);
      g.lineWidth = 3 * d; g.strokeStyle = 'rgba(255,255,255,0.25)';
      g.beginPath(); rp.forEach(([x, y], i) => i ? g.lineTo(X(x), Y(y)) : g.moveTo(X(x), Y(y))); g.stroke();
      g.strokeStyle = '#ffd27a'; g.beginPath();
      for (let i = 0; i <= idx; i++) { const [x, y] = rp[i]; i ? g.lineTo(X(x), Y(y)) : g.moveTo(X(x), Y(y)); }
      g.stroke();
      const [fx, fy, cs] = rp[idx];
      g.fillStyle = '#ff6b8a'; g.beginPath(); g.arc(X(fx), Y(fy), Math.max(5 * d, view.food.r * k), 0, 7); g.fill();
      const toNest = Math.atan2(view.nest.y - fy, view.nest.x - fx);
      for (const [id, px, py, slot] of cs) {
        const p = view.players.find(q => q.id === id); if (!p) continue;
        const ax = X(fx) + Math.cos(slot) * Math.max(8 * d, view.food.r * k), ay = Y(fy) + Math.sin(slot) * Math.max(8 * d, view.food.r * k);
        const L = 26 * d;
        const bad = (px * Math.cos(toNest) + py * Math.sin(toNest)) < 0;
        g.strokeStyle = bad ? '#ff4d4d' : p.color; g.fillStyle = g.strokeStyle; g.lineWidth = (bad ? 3 : 2) * d;
        g.beginPath(); g.moveTo(ax, ay); g.lineTo(ax + px * L, ay + py * L); g.stroke();
        g.font = `bold ${10 * d}px system-ui`; g.textAlign = 'center';
        if (Math.hypot(px, py) > 0.1) g.fillText(p.name, ax + px * (L + 8 * d), ay + py * (L + 8 * d) + 3 * d);
      }
      g.restore();
      g.font = `${11 * d}px system-ui`; g.fillStyle = 'rgba(255,255,255,0.6)'; g.textAlign = 'left';
      g.fillText('REPLAY · red arrows pulled away from the nest', mx0 + 8 * d, my0 + 16 * d);
    } else {
      g.font = `${13 * d}px system-ui`; g.fillStyle = 'rgba(255,255,255,0.6)'; g.textAlign = 'center';
      g.fillText('Nobody carried the food this round', mx0 + mapW / 2, my0 + mapH / 2);
    }

    // helpfulness bars
    const bx = small ? pad : mx0 + mapW + 16 * d, by = small ? my0 + mapH + 14 * d : my0;
    const bw = small ? W - pad * 2 : Math.min(360 * d, W * 0.35) - 16 * d;
    const ps = [...view.players].sort((a, b) => (b.help - b.harm) - (a.help - a.harm));
    const maxV = Math.max(1, ...ps.map(p => Math.max(p.help, p.harm)));
    const rowH = Math.min(26 * d, ((small ? H - by - pad : mapH) - 20 * d) / ps.length);
    g.font = `bold ${11 * d}px system-ui`; g.textAlign = 'left'; g.fillStyle = 'rgba(255,255,255,0.7)';
    g.fillText('WHO PULLED THEIR WEIGHT (seconds pushing home / away)', bx, by + 10 * d);
    ps.forEach((p, i) => {
      const y = by + 20 * d + i * rowH;
      const isT = view.result.traitors.includes(p.id);
      g.fillStyle = isT ? '#ff6b6b' : p.color; g.font = `bold ${Math.min(12 * d, rowH * 0.5)}px system-ui`; g.textAlign = 'left';
      g.fillText(p.name + (isT ? ' (T)' : '') + (p.id === view.me ? ' (you)' : ''), bx, y + rowH * 0.62);
      const cx = bx + bw * 0.5, half = bw * 0.24;
      g.fillStyle = 'rgba(255,255,255,0.08)'; g.fillRect(cx - half, y + rowH * 0.2, half * 2, rowH * 0.6);
      g.fillStyle = '#6fdc7a'; g.fillRect(cx, y + rowH * 0.2, half * p.help / maxV, rowH * 0.6);
      g.fillStyle = '#ff5a5a'; g.fillRect(cx - half * p.harm / maxV, y + rowH * 0.2, half * p.harm / maxV, rowH * 0.6);
      g.fillStyle = 'rgba(255,255,255,0.7)'; g.textAlign = 'right'; g.font = `${Math.min(11 * d, rowH * 0.45)}px system-ui`;
      g.fillText(`+${p.help.toFixed(0)} / -${p.harm.toFixed(0)}`, bx + bw, y + rowH * 0.62);
    });
  }
}
