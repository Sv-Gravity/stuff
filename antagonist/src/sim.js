// The authoritative game simulation. Pure data in, pure data out: no DOM, no clocks,
// no Math.random. In multiplayer the host (or a server) runs exactly this code and
// clients only send inputs and draw what viewFor() gives them.
import { CFG, NO_INPUT } from './config.js';
import { rand } from './rng.js';
import { genMap } from './world.js';

export const COLORS = ['#f4d35e', '#5ec2f4', '#f47e5e', '#9cf45e', '#d48cf4', '#f4a4c8', '#5ef4c8', '#f4f4f4', '#f49e2e', '#8c9cf4'];

/**
 * @param {{players:{id:number,name:string,isBot:boolean}[], seed:number,
 *          sameTraitor?:boolean, forceTraitor?:number|null, avoidTraitor?:number|null}} opts
 */
export function createMatch(opts) {
  const s = {
    seed: opts.seed >>> 0,
    rng: { r: opts.seed >>> 0 },
    tick: 0,
    round: 0,
    phase: 'countdown',
    phaseT: 0,
    timeLeft: CFG.ROUND_TIME,
    score: { colony: 0, traitor: 0 },
    sameTraitor: opts.sameTraitor !== false,
    forceTraitor: opts.forceTraitor ?? null,
    avoidTraitor: opts.avoidTraitor ?? null,
    traitorId: -1,
    caught: false,
    foodFound: false,
    result: null,
    winner: null,
    history: [],
    events: [],
    players: opts.players.map((p, i) => ({
      id: p.id, name: p.name, isBot: !!p.isBot, color: COLORS[i % COLORS.length],
      x: 0, y: 0, face: 0, walk: 0, moving: false,
      hold: null, slot: 0, push: { x: 0, y: 0 },
      stun: 0, web: 0, tripCd: 0, vote: null, voteLocked: false, points: 0,
    })),
  };
  startRound(s);
  return s;
}

function chooseTraitor(s) {
  if (s.forceTraitor != null && s.players.some(p => p.id === s.forceTraitor)) return s.forceTraitor;
  const pool = s.players.filter(p => p.id !== s.avoidTraitor);
  return pool[Math.floor(rand(s.rng) * pool.length)].id;
}

export function startRound(s) {
  s.round++;
  Object.assign(s, genMap(s.rng));
  // Heavier food for bigger colonies so the traitor always matters.
  s.food.fric = Math.max(1.6, s.food.fric + (s.players.length - 6) * (s.players.length > 6 ? 0.95 : 0.45));
  if (!(s.sameTraitor && s.traitorId >= 0)) s.traitorId = chooseTraitor(s);
  s.phase = 'countdown';
  s.phaseT = CFG.COUNTDOWN;
  s.timeLeft = CFG.ROUND_TIME;
  s.caught = false;
  s.foodFound = false;
  s.result = null;
  const n = s.players.length;
  s.players.forEach((p, i) => {
    const a = (i / n) * Math.PI * 2;
    p.x = s.nest.x + Math.cos(a) * (s.nest.r + 14);
    p.y = s.nest.y + Math.sin(a) * (s.nest.r + 14);
    p.face = a; p.walk = 0; p.moving = false;
    p.hold = null; p.push = { x: 0, y: 0 };
    p.stun = 0; p.web = 0; p.tripCd = 3; p.vote = null; p.voteLocked = false;
  });
}

const len = (x, y) => Math.hypot(x, y);
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const inPuddle = (s, p) => s.puddles.some(q => dist(q, p) < q.r);
const disabled = p => p.stun > 0 || p.web > 0;

function release(s, p) {
  if (typeof p.hold === 'number') {
    const c = s.crumbs[p.hold];
    if (c) c.carrier = null;
  }
  p.hold = null;
  p.push = { x: 0, y: 0 };
}

function collideCircle(s, o, r) {
  for (const k of s.rocks) {
    const dx = o.x - k.x, dy = o.y - k.y, d = Math.hypot(dx, dy), m = k.r + r;
    if (d < m && d > 0.0001) {
      const nx = dx / d, ny = dy / d;
      o.x = k.x + nx * m; o.y = k.y + ny * m;
      if (o.vx !== undefined) {
        const vn = o.vx * nx + o.vy * ny;
        if (vn < 0) { o.vx -= vn * nx; o.vy -= vn * ny; }
      }
    }
  }
  o.x = Math.max(r, Math.min(CFG.WORLD_W - r, o.x));
  o.y = Math.max(r, Math.min(CFG.WORLD_H - r, o.y));
}

function tryGrab(s, p) {
  if (p.hold !== null) { release(s, p); s.events.push({ t: 'drop', id: p.id }); return; }
  const f = s.food;
  if (dist(p, f) < f.r + CFG.ANT_R + CFG.GRAB_RANGE) {
    p.hold = 'food';
    p.slot = Math.atan2(p.y - f.y, p.x - f.x);
    s.events.push({ t: 'grab', id: p.id });
    return;
  }
  let best = null, bd = 16;
  for (const c of s.crumbs) {
    if (!c.alive || c.carrier !== null) continue;
    const d = dist(p, c);
    if (d < bd) { bd = d; best = c; }
  }
  if (best) { p.hold = best.id; best.carrier = p.id; s.events.push({ t: 'grab', id: p.id }); }
}

function tryTrip(s, p) {
  if (p.tripCd > 0) return;
  let best = null, bd = CFG.TRIP_RANGE;
  for (const q of s.players) {
    if (q === p || disabled(q)) continue;
    const d = dist(p, q);
    if (d < bd) { bd = d; best = q; }
  }
  if (!best) return;
  release(s, best);
  best.stun = CFG.TRIP_STUN;
  p.tripCd = CFG.TRIP_COOLDOWN;
  // Note: the event says who was tripped and where, but NOT who did it.
  s.events.push({ t: 'trip', id: best.id, x: best.x, y: best.y, by: p.id });
}

function tryVote(s, p) {
  if (p.voteLocked) { s.events.push({ t: 'novote', id: p.id }); return; }
  let best = null, bd = CFG.VOTE_RANGE;
  for (const q of s.players) {
    if (q === p || q.web > 0) continue;
    const d = dist(p, q);
    if (d < bd) { bd = d; best = q; }
  }
  if (!best) return;
  p.vote = p.vote === best.id ? null : best.id;
  s.events.push({ t: 'vote', id: p.id, target: p.vote });
}

function resolveVotes(s) {
  const active = s.players.filter(p => p.web <= 0);
  const need = Math.max(2, Math.ceil(active.length / 2));
  const counts = new Map();
  for (const p of active) if (p.vote !== null) counts.set(p.vote, (counts.get(p.vote) || 0) + 1);
  for (const [tid, c] of counts) {
    if (c < need) continue;
    const t = s.players.find(p => p.id === tid);
    const voters = active.filter(p => p.vote === tid);
    if (tid === s.traitorId) {
      t.web = 9999; release(s, t);
      s.caught = true;
      s.players.forEach(p => { p.vote = null; });
      s.events.push({ t: 'caught', id: tid });
    } else {
      t.web = CFG.WRONG_WEB_TIME; release(s, t);
      voters.forEach(v => { v.vote = null; v.voteLocked = true; });
      s.players.forEach(p => { if (p.vote === tid) p.vote = null; });
      s.events.push({ t: 'wrong', id: tid, voters: voters.map(v => v.id) });
    }
    return;
  }
}

function endRound(s, winner, reason) {
  s.score[winner]++;
  s.players.forEach(p => {
    if ((winner === 'traitor') === (p.id === s.traitorId)) p.points++;
    release(s, p);
  });
  s.result = { winner, reason, traitorId: s.traitorId, food: s.food.label };
  s.history.push(s.result);
  s.phase = 'roundEnd';
  s.phaseT = CFG.INTERMISSION;
  s.events.push({ t: 'roundEnd', winner, reason });
}

/** Advance one fixed tick. inputs: {[playerId]: {mx,my,grab,act,vote}} (grab/act/vote are "pressed this tick"). */
export function step(s, inputs) {
  const dt = CFG.TICK;
  s.tick++;
  s.events = [];

  if (s.phase === 'countdown') {
    s.phaseT -= dt;
    if (s.phaseT <= 0) { s.phase = 'play'; s.events.push({ t: 'go' }); }
    return s;
  }
  if (s.phase === 'roundEnd') {
    s.phaseT -= dt;
    if (s.phaseT <= 0) {
      if (s.score.colony >= CFG.WIN_POINTS || s.score.traitor >= CFG.WIN_POINTS) {
        s.phase = 'matchEnd';
        s.winner = s.score.colony >= CFG.WIN_POINTS ? 'colony' : 'traitor';
        s.events.push({ t: 'matchEnd', winner: s.winner });
      } else startRound(s);
    }
    return s;
  }
  if (s.phase !== 'play') return s;

  s.timeLeft -= dt;

  for (const p of s.players) {
    p.stun = Math.max(0, p.stun - dt);
    p.web = Math.max(0, p.web - dt);
    p.tripCd = Math.max(0, p.tripCd - dt);
    const inp = inputs[p.id] || NO_INPUT;
    let mx = +inp.mx || 0, my = +inp.my || 0;
    const ml = len(mx, my);
    if (ml > 1) { mx /= ml; my /= ml; }

    if (disabled(p)) { if (p.hold !== null) release(s, p); p.moving = false; continue; }

    if (inp.grab) tryGrab(s, p);
    if (inp.act && p.id === s.traitorId) {
      if (typeof p.hold === 'number') {
        const c = s.crumbs[p.hold];
        c.alive = false; c.carrier = null; p.hold = null;
        s.events.push({ t: 'eat', id: p.id, x: p.x, y: p.y });
      } else tryTrip(s, p);
    }
    if (inp.vote) tryVote(s, p);

    if (p.hold === 'food') {
      p.push = { x: mx, y: my };
      p.moving = ml > 0.1;
      if (p.moving) p.walk += dt * 6;
    } else {
      let sp = CFG.ANT_SPEED;
      if (inPuddle(s, p)) sp *= CFG.PUDDLE_SLOW;
      if (typeof p.hold === 'number') sp *= CFG.CRUMB_CARRY_SLOW;
      p.x += mx * sp * dt; p.y += my * sp * dt;
      collideCircle(s, p, CFG.ANT_R);
      // ants can't walk through the food either
      const f = s.food, d = dist(p, f), m = f.r + CFG.ANT_R;
      if (d < m && d > 0.001) { p.x = f.x + (p.x - f.x) / d * m; p.y = f.y + (p.y - f.y) / d * m; }
      p.moving = ml > 0.1;
      if (p.moving) { p.face = Math.atan2(my, mx); p.walk += dt * sp * 0.12; }
    }
  }

  // Crumbs follow their carrier; delivering one buys the colony time.
  for (const c of s.crumbs) {
    if (!c.alive || c.carrier === null) continue;
    const p = s.players.find(q => q.id === c.carrier);
    c.x = p.x + Math.cos(p.face) * 7; c.y = p.y + Math.sin(p.face) * 7;
    if (dist(c, s.nest) < s.nest.r) {
      c.alive = false; p.hold = null; c.carrier = null;
      s.timeLeft += CFG.CRUMB_TIME;
      s.events.push({ t: 'crumb', id: p.id, x: s.nest.x, y: s.nest.y });
    }
  }

  // The big food: it moves with the vector sum of everyone's push.
  const f = s.food;
  let fx = 0, fy = 0, n = 0;
  for (const p of s.players) if (p.hold === 'food') { fx += p.push.x; fy += p.push.y; n++; }
  f.carriers = n;
  const mag = len(fx, fy);
  let spd = mag > f.fric ? Math.min(CFG.FOOD_MAX_SPEED, (mag - f.fric) * CFG.FOOD_K) : 0;
  if (inPuddle(s, f)) spd *= 0.6;
  const tvx = mag > 0 ? fx / mag * spd : 0, tvy = mag > 0 ? fy / mag * spd : 0;
  f.vx += (tvx - f.vx) * 0.18; f.vy += (tvy - f.vy) * 0.18;
  f.x += f.vx * dt; f.y += f.vy * dt;
  collideCircle(s, f, f.r);
  f.rot += (f.vx * 0.002);
  for (const p of s.players) {
    if (p.hold !== 'food') continue;
    p.x = f.x + Math.cos(p.slot) * (f.r + CFG.ANT_R - 1);
    p.y = f.y + Math.sin(p.slot) * (f.r + CFG.ANT_R - 1);
    p.face = len(p.push.x, p.push.y) > 0.1 ? Math.atan2(p.push.y, p.push.x) : p.slot + Math.PI;
  }

  // Only honest eyes reveal the food to the whole colony (the traitor already knows).
  if (!s.foodFound) {
    for (const p of s.players) {
      if (p.id !== s.traitorId && !disabled(p) && dist(p, f) < CFG.VISION * 0.75) {
        s.foodFound = true; s.events.push({ t: 'found', id: p.id }); break;
      }
    }
  }

  resolveVotes(s);

  if (dist(f, s.nest) < s.nest.r + 4) endRound(s, 'colony', s.caught ? 'caught' : 'delivered');
  else if (s.timeLeft <= 0) endRound(s, 'traitor', 'timeout');
  return s;
}

/**
 * What one player is allowed to know. Hidden info (who the traitor is, their
 * cooldown) is stripped so a network client could never cheat by reading it.
 */
export function viewFor(s, pid) {
  const reveal = pid === s.traitorId || s.phase === 'roundEnd' || s.phase === 'matchEnd' || s.caught;
  return {
    ...s,
    rng: undefined,
    me: pid,
    traitorId: reveal ? s.traitorId : -1,
    amTraitor: pid === s.traitorId,
    foodKnown: s.foodFound || pid === s.traitorId,
    players: s.players.map(p => (p.id === pid || reveal) ? p : { ...p, tripCd: 0 }),
  };
}
