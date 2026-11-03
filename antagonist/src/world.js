// Procedural backyard: nest, boulders (pebbles to us), puddles, crumbs, decor, and the prize.
import { CFG } from './config.js';
import { rand, range, pick } from './rng.js';

export const FOODS = [
  { kind: 'strawberry', r: 30, fric: 2.7, label: 'a giant strawberry' },
  { kind: 'cookie', r: 34, fric: 3.0, label: 'a whole cookie' },
  { kind: 'cheeseball', r: 26, fric: 2.4, label: 'a cheese puff' },
  { kind: 'gummy', r: 28, fric: 2.6, label: 'a gummy bear' },
  { kind: 'donut', r: 36, fric: 3.2, label: 'a mini donut' },
];

const d2 = (a, b) => (a.x - b.x) ** 2 + (a.y - b.y) ** 2;

export function genMap(rng) {
  const W = CFG.WORLD_W, H = CFG.WORLD_H;
  // Nest near one edge, food far away.
  const side = Math.floor(rand(rng) * 4);
  const nest = { r: 46 };
  if (side === 0) { nest.x = range(rng, 220, 420); nest.y = range(rng, 300, H - 300); }
  else if (side === 1) { nest.x = range(rng, W - 420, W - 220); nest.y = range(rng, 300, H - 300); }
  else if (side === 2) { nest.x = range(rng, 400, W - 400); nest.y = range(rng, 220, 380); }
  else { nest.x = range(rng, 400, W - 400); nest.y = range(rng, H - 380, H - 220); }

  const rocks = [];
  for (let tries = 0; rocks.length < 30 && tries < 2000; tries++) {
    const r = { x: range(rng, 60, W - 60), y: range(rng, 60, H - 60), r: range(rng, 16, 85) };
    if (d2(r, nest) < (nest.r + r.r + 140) ** 2) continue;
    if (rocks.some(o => d2(o, r) < (o.r + r.r + 70) ** 2)) continue;
    rocks.push(r);
  }

  const puddles = [];
  for (let tries = 0; puddles.length < 5 && tries < 500; tries++) {
    const p = { x: range(rng, 150, W - 150), y: range(rng, 150, H - 150), r: range(rng, 55, 120) };
    if (d2(p, nest) < (nest.r + p.r + 120) ** 2) continue;
    if (rocks.some(o => d2(o, p) < (o.r + p.r + 10) ** 2)) continue;
    if (puddles.some(o => d2(o, p) < (o.r + p.r + 40) ** 2)) continue;
    puddles.push(p);
  }

  const def = pick(rng, FOODS);
  let food = null;
  for (let tries = 0; !food && tries < 3000; tries++) {
    const ang = rand(rng) * Math.PI * 2, dist = range(rng, 1250, 1700);
    const f = { x: nest.x + Math.cos(ang) * dist, y: nest.y + Math.sin(ang) * dist };
    if (f.x < 120 || f.y < 120 || f.x > W - 120 || f.y > H - 120) continue;
    if (rocks.some(o => d2(o, f) < (o.r + def.r + 40) ** 2)) continue;
    if (puddles.some(o => d2(o, f) < (o.r + def.r) ** 2)) continue;
    food = f;
  }
  if (!food) food = { x: W - nest.x, y: H - nest.y };
  Object.assign(food, { kind: def.kind, label: def.label, r: def.r, fric: def.fric, vx: 0, vy: 0, carriers: 0, rot: 0 });

  const clear = (p, pad) => !rocks.some(o => d2(o, p) < (o.r + pad) ** 2) && !puddles.some(o => d2(o, p) < (o.r + pad) ** 2);
  const crumbs = [];
  for (let tries = 0; crumbs.length < CFG.CRUMBS && tries < 2000; tries++) {
    const c = { x: range(rng, 80, W - 80), y: range(rng, 80, H - 80) };
    if (!clear(c, 12) || d2(c, nest) < 250 ** 2) continue;
    crumbs.push({ id: crumbs.length, x: c.x, y: c.y, alive: true, carrier: null, kind: Math.floor(rand(rng) * 3) });
  }

  // Purely visual, but generated from the seed so every client sees the same yard.
  const decor = [];
  for (let i = 0; i < 260; i++) {
    const d = { x: range(rng, 0, W), y: range(rng, 0, H), t: pick(rng, ['grass', 'grass', 'grass', 'leaf', 'twig', 'clover']), a: rand(rng) * Math.PI * 2, s: range(rng, 0.7, 1.5) };
    if (!clear(d, 8) || d2(d, nest) < 90 ** 2) continue;
    decor.push(d);
  }

  return { nest, rocks, puddles, food, crumbs, decor };
}
