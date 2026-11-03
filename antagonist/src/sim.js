// The authoritative game simulation. Pure data in, pure data out: no DOM, no clocks,
// no Math.random. In multiplayer the host (or a server) runs exactly this code and
// clients only send inputs and draw what viewFor() gives them.
import { CFG, NO_INPUT } from './config.js';
import { rand } from './rng.js';
import { genMap } from './world.js';

export const COLORS = ['#f4d35e', '#5ec2f4', '#f47e5e', '#9cf45e', '#d48cf4', '#f4a4c8', '#5ef4c8', '#f4f4f4', '#f49e2e', '#8c9cf4'];

/**
 * @param {{players:{id:number,name:string,isBot:boolean}[], seed:number,
 *          sameTraitor?:boolean, traitorCount?:'auto'|1|2,
 *          forceTraitor?:number|null, avoidTraitor?:number|null}} opts
 */
export function createMatch(opts) {
  const s = {
    seed: opts.seed >>> 0,
    rng: { r: opts.seed >>> 0 },
    tick: 0,
    round: 0,
    phase: 'countdown',
    phaseT: 0,
    roundT: 0,
    timeLeft: CFG.ROUND_TIME,
    score: { colony: 0, traitor: 0 },
    sameTraitor: opts.sameTraitor !== false,
    traitorCount: opts.traitorCount || 'auto',
    forceTraitor: opts.forceTraitor ?? null,
    avoidTraitor: opts.avoidTraitor ?? null,
    traitors: [],
    caught: [],
    foodFound: false,
    scents: [],
    nextScentId: 1,
    meeting: null,
    replay: [],
    result: null,
    winner: null,
    history: [],
    events: [],
    players: opts.players.map((p, i) => ({
      id: p.id, name: p.name, isBot: !!p.isBot, color: COLORS[i % COLORS.length],
      x: 0, y: 0, face: 0, walk: 0, moving: false,
      hold: null, slot: 0, push: { x: 0, y: 0 },
      stun: 0, web: 0, tripCd: 0, vote: null, voteLocked: false, points: 0,
      meetUsed: false, mvote: null, scentCd: 0, scentsLeft: 0,
      help: 0, harm: 0, ready: false,
    })),
  };
  startRound(s);
  return s;
}

export const numTraitors = s => s.traitorCount === 'auto' ? (s.players.length >= 8 ? 2 : 1) : Math.min(+s.traitorCount, s.players.length - 2);
export const isTraitor = (s, id) => s.traitors.includes(id);

function chooseTraitors(s) {
  const n = numTraitors(s);
  const out = [];
  if (s.forceTraitor != null && s.players.some(p => p.id === s.forceTraitor)) out.push(s.forceTraitor);
  const pool = s.players.map(p => p.id).filter(id => id !== s.avoidTraitor && !out.includes(id));
  while (out.length < n && pool.length) out.push(pool.splice(Math.floor(rand(s.rng) * pool.length), 1)[0]);
  return out;
}

export function startRound(s) {
  s.round++;
  Object.assign(s, genMap(s.rng));
  // Heavier food for bigger colonies so the traitor always matters.
  const n = s.players.length, nt = numTraitors(s);
  s.food.fric = Math.max(1.6, s.food.fric + (n - 6) * (n > 6 ? 0.95 : 0.75) - (nt - 1) * 1.6);
  if (!(s.sameTraitor && s.traitors.length)) s.traitors = chooseTraitors(s);
  s.phase = 'countdown';
  s.phaseT = CFG.COUNTDOWN;
  s.roundT = 0;
  s.timeLeft = CFG.ROUND_TIME;
  s.caught = [];
  s.foodFound = false;
  s.scents = [];
  s.meeting = null;
  s.meetCd = 0;
  s.replay = [];
  s.result = null;
  s.players.forEach((p, i) => {
    const a = (i / n) * Math.PI * 2;
    p.x = s.nest.x + Math.cos(a) * (s.nest.r + 14);
    p.y = s.nest.y + Math.sin(a) * (s.nest.r + 14);
    p.face = a; p.walk = 0; p.moving = false;
    p.hold = null; p.push = { x: 0, y: 0 };
    p.stun = 0; p.web = 0; p.tripCd = 3; p.vote = null; p.voteLocked = false;
    p.meetUsed = false; p.mvote = null; p.ready = false;
    p.scentCd = 6; p.scentsLeft = isTraitor(s, p.id) ? CFG.FAKE_SCENTS : 0;
    p.help = 0; p.harm = 0;
  });
}

const len = (x, y) => Math.hypot(x, y);
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const inPuddle = (s, p) => s.puddles.some(q => dist(q, p) < q.r);
const disabled = p => p.stun > 0 || p.web > 0;
const byId = (s, id) => s.players.find(p => p.id === id);

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
    const dx = o.x - k.x, dy = o.y - k.y, m = k.r + r;
    if (dx > m || dx < -m || dy > m || dy < -m) continue;
    const d = Math.hypot(dx, dy);
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
    if (q === p || disabled(q) || isTraitor(s, q.id)) continue;
    const d = dist(p, q);
    if (d < bd) { bd = d; best = q; }
  }
  if (!best) return;
  release(s, best);
  best.stun = CFG.TRIP_STUN;
  p.tripCd = CFG.TRIP_COOLDOWN;
  // `by` is stripped by viewFor for everyone but the traitors.
  s.events.push({ t: 'trip', id: best.id, x: best.x, y: best.y, by: p.id });
}

function tryFakeScent(s, p) {
  if (p.scentCd > 0 || p.scentsLeft <= 0) return;
  if (dist(p, s.food) < 400 || dist(p, s.nest) < 250) { s.events.push({ t: 'noscent', id: p.id }); return; }
  p.scentsLeft--; p.scentCd = CFG.FAKE_SCENT_COOLDOWN;
  s.scents.push({ id: s.nextScentId++, x: p.x, y: p.y, fake: true, by: p.id, debunked: false });
  s.events.push({ t: 'scent', x: p.x, y: p.y });
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

const activePlayers = s => s.players.filter(p => p.web <= 0);
const majority = s => Math.max(2, Math.ceil(activePlayers(s).length / 2));

function verdict(s, tid, voters, src = 'field') {
  const t = byId(s, tid);
  if (isTraitor(s, tid)) {
    t.web = 9999; release(s, t);
    s.caught.push(tid);
    s.players.forEach(p => { if (p.vote === tid) p.vote = null; });
    s.events.push({ t: 'caught', id: tid, src });
  } else {
    t.web = CFG.WRONG_WEB_TIME; release(s, t);
    voters.forEach(v => { v.vote = null; v.voteLocked = true; });
    s.players.forEach(p => { if (p.vote === tid) p.vote = null; });
    s.events.push({ t: 'wrong', id: tid, voters: voters.map(v => v.id), src });
  }
}

function resolveVotes(s) {
  const active = activePlayers(s), need = majority(s);
  const counts = new Map();
  for (const p of active) if (p.vote !== null) counts.set(p.vote, (counts.get(p.vote) || 0) + 1);
  for (const [tid, c] of counts) {
    if (c >= need) { verdict(s, tid, active.filter(p => p.vote === tid)); return; }
  }
}

function startMeeting(s, p) {
  if (p.meetUsed || s.meeting || s.roundT < CFG.MEETING_MIN_ROUND_T || s.meetCd > 0) { s.events.push({ t: 'nomeet', id: p.id }); return; }
  p.meetUsed = true;
  s.phase = 'meeting';
  s.meeting = { caller: p.id, t: CFG.MEETING_TIME, chat: [] };
  s.players.forEach(q => { q.mvote = null; q.moving = false; });
  s.food.vx = s.food.vy = 0;
  s.events.push({ t: 'meeting', id: p.id });
}

function endMeeting(s) {
  const active = activePlayers(s), need = majority(s);
  const counts = new Map();
  for (const p of active) if (p.mvote !== null && p.mvote !== 'skip') counts.set(p.mvote, (counts.get(p.mvote) || 0) + 1);
  let top = null, tc = 0, tie = false;
  for (const [id, c] of counts) { if (c > tc) { top = id; tc = c; tie = false; } else if (c === tc) tie = true; }
  const outcome = { votes: Object.fromEntries(s.players.map(p => [p.id, p.mvote])) };
  const voters = active.filter(p => p.mvote === top);
  s.phase = 'play';
  s.meeting = null;
  s.players.forEach(p => { p.mvote = null; });
  s.lastMeeting = outcome;
  s.meetCd = 15;
  if (top !== null && !tie && tc >= need) verdict(s, top, voters, 'meeting');
  else s.events.push({ t: 'meetingEnd', result: 'none' });
}

function endRound(s, winner, reason) {
  s.score[winner]++;
  s.players.forEach(p => {
    if ((winner === 'traitor') === isTraitor(s, p.id)) p.points++;
    release(s, p);
    p.ready = false;
  });
  s.result = { winner, reason, traitors: [...s.traitors], food: s.food.label };
  s.history.push(s.result);
  s.phase = 'roundEnd';
  s.phaseT = CFG.INTERMISSION;
  s.meeting = null;
  s.events.push({ t: 'roundEnd', winner, reason });
}

function recordReplay(s) {
  const f = s.food;
  const c = [];
  for (const p of s.players) if (p.hold === 'food') c.push([p.id, Math.round(p.push.x * 100) / 100, Math.round(p.push.y * 100) / 100, Math.round(p.slot * 100) / 100]);
  s.replay.push([Math.round(f.x), Math.round(f.y), c]);
}

/** Advance one fixed tick. inputs: {[playerId]: input}; grab/act/vote/meet/scent are "pressed this tick". */
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
    for (const p of s.players) { const i = inputs[p.id]; if (i && (i.ready || i.grab)) p.ready = true; }
    const humans = s.players.filter(p => !p.isBot);
    const allReady = humans.length > 0 && humans.every(p => p.ready) && s.phaseT < CFG.INTERMISSION - 2;
    if (s.phaseT <= 0 || allReady) {
      if (s.score.colony >= CFG.WIN_POINTS || s.score.traitor >= CFG.WIN_POINTS) {
        s.phase = 'matchEnd';
        s.winner = s.score.colony >= CFG.WIN_POINTS ? 'colony' : 'traitor';
        s.events.push({ t: 'matchEnd', winner: s.winner });
      } else startRound(s);
    }
    return s;
  }
  if (s.phase === 'meeting') {
    s.timeLeft -= dt;
    s.meeting.t -= dt;
    for (const p of s.players) {
      const inp = inputs[p.id]; if (!inp || p.web > 0) continue;
      if (inp.mvote !== undefined && inp.mvote !== null && (inp.mvote === 'skip' || (byId(s, inp.mvote) && inp.mvote !== p.id))) {
        if (p.mvote !== inp.mvote) { p.mvote = inp.mvote; s.events.push({ t: 'mvote', id: p.id }); }
      }
      if (typeof inp.say === 'string' && inp.say.trim()) {
        s.meeting.chat.push({ id: p.id, text: inp.say.trim().slice(0, 90) });
        if (s.meeting.chat.length > 40) s.meeting.chat.shift();
        s.events.push({ t: 'say', id: p.id });
      }
    }
    const allVoted = activePlayers(s).every(p => p.mvote !== null);
    if (s.meeting.t <= 0 || allVoted) endMeeting(s);
    if (s.timeLeft <= 0) endRound(s, 'traitor', 'timeout');
    return s;
  }
  if (s.phase !== 'play') return s;

  s.timeLeft -= dt;
  s.roundT += dt;
  s.meetCd = Math.max(0, (s.meetCd || 0) - dt);

  const f = s.food;
  const ideal = (() => { const dx = s.nest.x - f.x, dy = s.nest.y - f.y, l = len(dx, dy) || 1; return { x: dx / l, y: dy / l }; })();

  for (const p of s.players) {
    p.stun = Math.max(0, p.stun - dt);
    p.web = Math.max(0, p.web - dt);
    p.tripCd = Math.max(0, p.tripCd - dt);
    p.scentCd = Math.max(0, p.scentCd - dt);
    const inp = inputs[p.id] || NO_INPUT;
    let mx = +inp.mx || 0, my = +inp.my || 0;
    const ml = len(mx, my);
    if (ml > 1) { mx /= ml; my /= ml; }

    if (disabled(p)) { if (p.hold !== null) release(s, p); p.moving = false; continue; }

    if (inp.meet) { startMeeting(s, p); if (s.phase === 'meeting') return s; }
    if (inp.grab) tryGrab(s, p);
    if (inp.act && isTraitor(s, p.id)) {
      if (typeof p.hold === 'number') {
        const c = s.crumbs[p.hold];
        c.alive = false; c.carrier = null; p.hold = null;
        s.events.push({ t: 'eat', id: p.id, x: p.x, y: p.y });
      } else tryTrip(s, p);
    }
    if (inp.scent && isTraitor(s, p.id)) tryFakeScent(s, p);
    if (inp.vote) tryVote(s, p);

    if (p.hold === 'food') {
      p.push = { x: mx, y: my };
      p.moving = ml > 0.1;
      if (p.moving) p.walk += dt * 6;
      const a = mx * ideal.x + my * ideal.y;
      if (a > 0) p.help += a * dt; else p.harm -= a * dt;
    } else {
      let sp = CFG.ANT_SPEED;
      if (inPuddle(s, p)) sp *= CFG.PUDDLE_SLOW;
      if (typeof p.hold === 'number') sp *= CFG.CRUMB_CARRY_SLOW;
      p.x += mx * sp * dt; p.y += my * sp * dt;
      collideCircle(s, p, CFG.ANT_R);
      const d = dist(p, f), m = f.r + CFG.ANT_R;
      if (d < m && d > 0.001) { p.x = f.x + (p.x - f.x) / d * m; p.y = f.y + (p.y - f.y) / d * m; }
      p.moving = ml > 0.1;
      if (p.moving) { p.face = Math.atan2(my, mx); p.walk += dt * sp * 0.12; }
    }
  }

  // Crumbs follow their carrier; delivering one buys the colony time.
  for (const c of s.crumbs) {
    if (!c.alive || c.carrier === null) continue;
    const p = byId(s, c.carrier);
    c.x = p.x + Math.cos(p.face) * 7; c.y = p.y + Math.sin(p.face) * 7;
    if (dist(c, s.nest) < s.nest.r) {
      c.alive = false; p.hold = null; c.carrier = null;
      s.timeLeft += CFG.CRUMB_TIME;
      s.events.push({ t: 'crumb', id: p.id, x: s.nest.x, y: s.nest.y });
    }
  }

  // The big food moves with the vector sum of everyone's push.
  let fx = 0, fy = 0, n = 0;
  for (const p of s.players) if (p.hold === 'food') { fx += p.push.x; fy += p.push.y; n++; }
  f.carriers = n;
  const mag = len(fx, fy);
  let spd = mag > f.fric ? Math.min(CFG.FOOD_MAX_SPEED, (mag - f.fric) * CFG.FOOD_K) : 0;
  if (inPuddle(s, f)) spd *= 0.6;
  const tvx = mag > 0 ? fx / mag * spd : 0, tvy = mag > 0 ? fy / mag * spd : 0;
  const k = 1 - Math.exp(-6 * dt);
  f.vx += (tvx - f.vx) * k; f.vy += (tvy - f.vy) * k;
  f.x += f.vx * dt; f.y += f.vy * dt;
  collideCircle(s, f, f.r);
  f.rot += f.vx * 0.06 * dt;
  for (const p of s.players) {
    if (p.hold !== 'food') continue;
    p.x = f.x + Math.cos(p.slot) * (f.r + CFG.ANT_R - 1);
    p.y = f.y + Math.sin(p.slot) * (f.r + CFG.ANT_R - 1);
    p.face = len(p.push.x, p.push.y) > 0.1 ? Math.atan2(p.push.y, p.push.x) : p.slot + Math.PI;
  }

  // Scents: only honest eyes find the food; honest ants also expose fake scents.
  for (const p of s.players) {
    if (isTraitor(s, p.id) || disabled(p)) continue;
    if (!s.foodFound && dist(p, f) < CFG.VISION * 0.75) {
      s.foodFound = true;
      s.scents.push({ id: s.nextScentId++, x: f.x, y: f.y, fake: false, real: true, debunked: false });
      s.events.push({ t: 'found', id: p.id });
    }
    for (const sc of s.scents) {
      if (sc.fake && !sc.debunked && dist(p, sc) < CFG.DEBUNK_RANGE) {
        sc.debunked = true;
        s.events.push({ t: 'debunk', id: p.id, x: sc.x, y: sc.y });
      }
    }
  }
  for (const sc of s.scents) if (sc.real) { sc.x = f.x; sc.y = f.y; }
  s.scents = s.scents.filter(sc => !sc.debunked);

  if (s.tick % CFG.REPLAY_EVERY === 0) recordReplay(s);

  resolveVotes(s);

  if (dist(f, s.nest) < s.nest.r + 4) endRound(s, 'colony', s.caught.length ? 'caught' : 'delivered');
  else if (s.timeLeft <= 0) endRound(s, 'traitor', 'timeout');
  return s;
}

/**
 * What one player is allowed to know. Hidden info (who the traitors are, their
 * cooldowns, which scents are fake, the replay until the round ends) is stripped
 * so a network client could never cheat by reading it.
 */
export function viewFor(s, pid) {
  const amTraitor = isTraitor(s, pid);
  const over = s.phase === 'roundEnd' || s.phase === 'matchEnd';
  const known = over || amTraitor ? s.traitors : s.caught;
  const me = byId(s, pid);
  const seesFood = amTraitor || over || !me || dist(me, s.food) < CFG.VISION + 60;
  const hideP = p => (p.id === pid || over || amTraitor) ? p : { ...p, tripCd: 0, scentCd: 0, scentsLeft: 0, help: 0, harm: 0 };
  return {
    ...s,
    rng: undefined,
    me: pid,
    traitors: known,
    amTraitor,
    foodKnown: s.foodFound || amTraitor,
    // Out of sight, the food's position is withheld: otherwise you could tell the real scent from a fake.
    food: seesFood ? s.food : { ...s.food, x: null, y: null, vx: 0, vy: 0, hidden: true },
    scents: s.scents.map(sc => amTraitor ? sc : { id: sc.id, x: sc.x, y: sc.y }),
    replay: over ? s.replay : [],
    events: amTraitor || over ? s.events : s.events.map(e => e.by !== undefined ? { ...e, by: undefined } : e),
    players: s.players.map(hideP),
  };
}
