// Canvas renderer. Draws only from a view (viewFor), never from the raw state.
import { CFG } from './config.js';

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
    this.c = canvas; this.g = canvas.getContext('2d');
    this.fog = document.createElement('canvas');
    this.particles = []; this.floaters = [];
    this.cam = { x: 0, y: 0, z: 2 };
    this.prev = null;
    this.flash = null;
  }

  resize() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    this.dpr = dpr;
    this.c.width = innerWidth * dpr; this.c.height = innerHeight * dpr;
    this.fog.width = this.c.width; this.fog.height = this.c.height;
  }

  // Interpolation between the last two sim ticks so movement stays smooth at any fps.
  snapshot(view) {
    const m = {};
    for (const p of view.players) m['p' + p.id] = [p.x, p.y];
    m.food = [view.food.x, view.food.y];
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
      if (e.t === 'caught' && p) { this.burst(p.x, p.y, '#ffffff', 30); this.flash = { text: `${p.name} WAS THE TRAITOR! Webbed!`, t: 3, col: '#9cff8a' }; }
      if (e.t === 'wrong' && p) { this.burst(p.x, p.y, '#ffffff', 20); this.flash = { text: `${p.name} was innocent... accusers lose their vote`, t: 3, col: '#ff8a8a' }; }
      if (e.t === 'found') this.flash = { text: `${p ? p.name : 'Someone'} found ${view.food.label}! Follow the arrow`, t: 3, col: '#ffe08a' };
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
    const sx = x => (x - mx) * z + W / 2, sy = y => (y - my) * z + H / 2;

    g.setTransform(1, 0, 0, 1, 0, 0);
    g.fillStyle = '#1b130c'; g.fillRect(0, 0, W, H);
    g.setTransform(z, 0, 0, z, W / 2 - mx * z, H / 2 - my * z);
    // ground
    g.fillStyle = groundPattern; g.fillRect(0, 0, CFG.WORLD_W, CFG.WORLD_H);
    g.strokeStyle = '#2a1d10'; g.lineWidth = 6; g.strokeRect(0, 0, CFG.WORLD_W, CFG.WORLD_H);

    const vis = (x, y, pad = 0) => Math.abs(x - mx) < W / z / 2 + pad && Math.abs(y - my) < H / z / 2 + pad;

    for (const q of view.puddles) if (vis(q.x, q.y, q.r)) this.puddle(q);
    this.nest(view.nest);
    for (const d of view.decor) if (vis(d.x, d.y, 40) && d.t !== 'grass') this.decor(d);

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
    for (const k of view.rocks) if (vis(k.x, k.y, k.r)) items.push({ y: k.y + k.r * 0.4, f: () => this.rock(k) });
    for (const d of view.decor) if (d.t === 'grass' && vis(d.x, d.y, 40)) items.push({ y: d.y, f: () => this.grass(d) });
    const [fx, fy] = this.pos('food', view.food.x, view.food.y, alpha);
    const foodVisible = view.foodKnown || Math.hypot(fx - mx, fy - my) < CFG.VISION + 40;
    if (foodVisible) items.push({ y: fy, f: () => this.food(view.food, fx, fy) });
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

    // fog of vision
    g.setTransform(1, 0, 0, 1, 0, 0);
    const fg = this.fog.getContext('2d');
    fg.globalCompositeOperation = 'source-over';
    fg.clearRect(0, 0, W, H);
    fg.fillStyle = 'rgba(12,8,4,0.86)'; fg.fillRect(0, 0, W, H);
    fg.globalCompositeOperation = 'destination-out';
    const R = CFG.VISION * z;
    const grd = fg.createRadialGradient(W / 2, H / 2, R * 0.55, W / 2, H / 2, R);
    grd.addColorStop(0, 'rgba(0,0,0,1)'); grd.addColorStop(1, 'rgba(0,0,0,0)');
    fg.fillStyle = grd; fg.beginPath(); fg.arc(W / 2, H / 2, R, 0, 7); fg.fill();
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
    g.fillStyle = 'rgba(0,0,0,0.3)'; g.beginPath(); g.ellipse(x + 4, y + r * 0.5, r * 1.05, r * 0.5, 0, 0, 7); g.fill();
    g.save(); g.translate(x, y - r * 0.15);
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
    const isT = view.traitorId === p.id;
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
    g.fillText(text, x - Math.cos(a) * 22 * dpr, y - Math.sin(a) * 22 * dpr + 4 * dpr);
  }

  hud(view, me, ui, dt, sx, sy, fx, fy) {
    const g = this.g, W = this.c.width, H = this.c.height, d = this.dpr;
    g.setTransform(1, 0, 0, 1, 0, 0);
    // edge arrows
    this.arrowTo(W, H, sx(view.nest.x), sy(view.nest.y), '#ffe9b0', 'nest ' + Math.round(Math.hypot(view.nest.x - me.x, view.nest.y - me.y) / 10) + 'cm');
    if (view.foodKnown) this.arrowTo(W, H, sx(fx), sy(fy), view.amTraitor && !view.foodFound ? '#ff8a8a' : '#ff6b8a', (view.amTraitor && !view.foodFound ? 'food (only you know)' : 'food'));

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
    g.textAlign = 'left'; g.fillStyle = '#ff7a7a'; g.fillText('TRAITOR', W / 2 + 80 * d, 30 * d);
    pips(view.score.traitor, '#ff7a7a', W / 2 + 92 * d, 1);

    // role + status panel
    g.textAlign = 'left';
    g.font = `bold ${14 * d}px system-ui`;
    g.fillStyle = view.amTraitor ? '#ff6b6b' : '#9cf4a0';
    g.fillText(view.amTraitor ? 'YOU ARE THE TRAITOR' : 'YOU ARE A WORKER', 16 * d, 28 * d);
    g.font = `${12 * d}px system-ui`; g.fillStyle = '#e8dcc8';
    const lines = [];
    const f = view.food;
    if (me.hold === 'food') {
      const spd = Math.hypot(f.vx, f.vy);
      lines.push(`Carrying with ${f.carriers} ant${f.carriers === 1 ? '' : 's'} · ${spd < 2 ? 'not moving' : Math.round(spd / 10 * 10) / 10 + ' cm/s'}`);
    } else if (typeof me.hold === 'number') lines.push(view.amTraitor ? 'Holding a crumb · Q to eat it (risky!)' : 'Holding a crumb · bring it home for +' + CFG.CRUMB_TIME + 's');
    if (me.stun > 0) lines.push('You tripped!');
    if (me.web > 0) lines.push(me.web > 1000 ? 'Caught and webbed for the rest of the round' : `Webbed! ${Math.ceil(me.web)}s`);
    if (view.amTraitor) lines.push(me.tripCd > 0 ? `Trip ready in ${Math.ceil(me.tripCd)}s` : 'Trip ready (Q near an ant)');
    lines.push(me.voteLocked ? 'You lost your accusation this round' : me.vote !== null ? `Accusing ${view.players.find(p => p.id === me.vote)?.name}` : 'V next to an ant to accuse');
    lines.forEach((l, i) => g.fillText(l, 16 * d, (48 + i * 17) * d));

    // controls
    g.font = `${11 * d}px system-ui`; g.fillStyle = 'rgba(255,255,255,0.55)';
    g.fillText(view.amTraitor
      ? 'WASD/Arrows move · Space grab/let go · Q trip ant / eat crumb · V accuse · Esc menu'
      : 'WASD/Arrows move · Space grab/let go · V accuse (majority webs them) · Esc menu', 16 * d, H - 16 * d);

    // flash messages
    if (this.flash) {
      this.flash.t -= dt;
      g.globalAlpha = Math.min(1, this.flash.t);
      g.textAlign = 'center'; g.font = `bold ${18 * d}px system-ui`;
      g.fillStyle = '#000'; g.fillText(this.flash.text, W / 2 + 2, H * 0.22 + 2);
      g.fillStyle = this.flash.col; g.fillText(this.flash.text, W / 2, H * 0.22);
      g.globalAlpha = 1;
      if (this.flash.t <= 0) this.flash = null;
    }

    // big center banners
    const banner = (title, sub, col, sub2) => {
      g.fillStyle = 'rgba(0,0,0,0.55)'; g.fillRect(0, H * 0.36, W, H * 0.28);
      g.textAlign = 'center'; g.fillStyle = col; g.font = `bold ${38 * d}px system-ui`;
      g.fillText(title, W / 2, H * 0.36 + 60 * d);
      g.fillStyle = '#f0e6d2'; g.font = `${16 * d}px system-ui`;
      g.fillText(sub, W / 2, H * 0.36 + 92 * d);
      if (sub2) { g.fillStyle = 'rgba(255,255,255,0.6)'; g.font = `${13 * d}px system-ui`; g.fillText(sub2, W / 2, H * 0.36 + 116 * d); }
    };
    if (view.phase === 'countdown') {
      banner(view.amTraitor ? 'YOU ARE THE TRAITOR' : 'YOU ARE A WORKER',
        view.amTraitor ? `Stop them hauling ${view.food.label} home. Pretend to help. Don't get caught.` : `Find ${view.food.label} and haul it to the nest. One of you is lying.`,
        view.amTraitor ? '#ff6b6b' : '#9cf4a0', `Starting in ${Math.ceil(view.phaseT)}...`);
    } else if (view.phase === 'roundEnd' || view.phase === 'matchEnd') {
      const r = view.result, tn = view.players.find(p => p.id === r.traitorId)?.name;
      const title = view.phase === 'matchEnd'
        ? (view.winner === 'colony' ? 'THE COLONY WINS THE MATCH' : 'THE TRAITOR WINS THE MATCH')
        : (r.winner === 'colony' ? 'FOOD DELIVERED!' : "TIME'S UP!");
      const sub = r.winner === 'colony'
        ? (r.reason === 'caught' ? `Colony scores. ${tn} was caught and webbed.` : `Colony scores. The traitor was ${tn}.`)
        : `The traitor (${tn}) scores.`;
      banner(title, sub, (view.phase === 'matchEnd' ? view.winner : r.winner) === 'colony' ? '#9cf4a0' : '#ff6b6b',
        view.phase === 'matchEnd' ? 'Enter: rematch · Esc: menu' : `Next round in ${Math.ceil(view.phaseT)}...`);
    }
  }
}
