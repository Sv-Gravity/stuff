// Bot brains. A bot only ever sees viewFor(state, itsId) – the same thing a remote
// human would see – and returns the same input shape a keyboard produces.
import { CFG } from './config.js';
import { rand, range, pick } from './rng.js';

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const norm = (x, y) => { const l = Math.hypot(x, y) || 1; return { x: x / l, y: y / l }; };
const rot = (v, a) => ({ x: v.x * Math.cos(a) - v.y * Math.sin(a), y: v.x * Math.sin(a) + v.y * Math.cos(a) });

// Steering from `from` (radius r) toward `to`, sliding around rocks.
export function steer(view, from, r, to) {
  const d = norm(to.x - from.x, to.y - from.y);
  let ax = d.x, ay = d.y;
  for (const k of view.rocks) {
    const ox = k.x - from.x, oy = k.y - from.y;
    if (ox > 250 || ox < -250 || oy > 250 || oy < -250) continue;
    const dd = Math.hypot(ox, oy), clear = dd - k.r - r;
    if (clear > 80 || (ox * d.x + oy * d.y) < 0) continue;
    const cross = d.x * oy - d.y * ox;
    const side = cross > 0 ? -1 : 1;
    const w = Math.max(0, 1 - clear / 80) * 1.8;
    ax += -oy / dd * side * w; ay += ox / dd * side * w;
    if (clear < 6) { ax -= ox / dd * 0.8; ay -= oy / dd * 0.8; }
  }
  return norm(ax, ay);
}

const LINES = {
  pull: ['{X} was pulling the food the wrong way!', 'Watch {X}. They keep dragging it backwards.', '{X} is pushing sideways the whole time.'],
  trip: ['{X} was right next to me when I tripped.', 'Somebody tripped me and {X} was the only one close.'],
  eat: ['I saw {X} munch a crumb. Who does that?', '{X} ATE a crumb. Clock time, gone.'],
  slack: ['{X} holds on but never pushes.'],
  none: ["I don't know yet. Watch who leans the wrong way.", 'I was out foraging, I saw nothing.', 'Skip? I have no proof on anyone.'],
  defend: ["It's not me, I was pushing toward the nest!", 'Me?? I carried that thing half the way!'],
};

export class Bot {
  constructor(id, seed) {
    this.id = id;
    this.rng = { r: (seed * 2654435761 + id * 97) >>> 0 };
    this.wp = null; this.wpT = 0;
    this.susp = {}; this.why = {};
    this.jitter = 0; this.jitterT = 0;
    this.mode = 'help'; this.modeT = 0;
    this.lastRound = -1;
    this.stuckT = 0; this.escapeT = 0;
    this.eatT = 0;
    this.gatherer = rand(this.rng) < 0.35;
  }

  resetRound(view) {
    this.lastRound = view.round;
    this.wp = null; this.susp = {}; this.why = {}; this.mode = 'help'; this.modeT = 0; this.stuckT = 0; this.escapeT = 0;
    this.reaction = range(this.rng, 0.2, 1.2);
    this.meetingKey = null;
  }

  addSusp(id, v, why) {
    this.susp[id] = (this.susp[id] || 0) + v;
    if (why && v > 0) { const w = this.why[id] || (this.why[id] = {}); w[why] = (w[why] || 0) + v; }
  }
  topWhy(id) {
    const w = this.why[id]; if (!w) return 'none';
    return Object.entries(w).sort((a, b) => b[1] - a[1])[0][0];
  }
  isFellow(view, id) { return view.amTraitor && view.traitors.includes(id); }

  think(view) {
    const dt = CFG.TICK;
    const inp = { mx: 0, my: 0, grab: false, act: false, vote: false, meet: false, scent: false };
    if (view.round !== this.lastRound) this.resetRound(view);
    if (view.phase === 'meeting') return this.meeting(view, inp);
    this.meetingKey = null;
    if (view.phase === 'roundEnd') { inp.ready = true; return inp; }
    if (view.phase !== 'play') return inp;
    const me = view.players.find(p => p.id === this.id);
    if (!me || me.stun > 0 || me.web > 0) return inp;
    if (this.reaction > 0) { this.reaction -= dt; return inp; }

    const f = view.food;
    const traitor = view.amTraitor;
    this.observe(view, me, dt);

    // ---- call an antennae meeting ----
    if (!me.meetUsed && view.roundT > CFG.MEETING_MIN_ROUND_T && !(view.meetCd > 0)) {
      if (!traitor) {
        const top = this.topSuspect(view, me);
        if (top && this.susp[top.id] > 7 && rand(this.rng) < 0.3 * dt) { inp.meet = true; return inp; }
      } else if (view.foodFound && dist(f, view.nest) < 450 && view.timeLeft < 30 && rand(this.rng) < 0.3 * dt) {
        inp.meet = true; return inp; // waste their time
      }
    }

    // ---- accusations ----
    if (!me.voteLocked) {
      let target = null;
      if (traitor) {
        const onMe = view.players.filter(p => p.vote === me.id).length;
        if (onMe > 0 && me.vote === null) {
          const n = this.nearestOther(view, me, CFG.VOTE_RANGE - 5);
          if (n && !this.isFellow(view, n.id)) target = n;
        }
      } else {
        const best = this.topSuspect(view, me);
        if (best && this.susp[best.id] > 3.4 && best.id !== me.vote && dist(best, me) < CFG.VOTE_RANGE - 5) {
          const near = this.nearestOther(view, me, CFG.VOTE_RANGE);
          if (near && near.id === best.id) target = best;
        }
      }
      if (target && target.id !== me.vote) inp.vote = true;
    }

    // ---- carrying the big food ----
    if (me.hold === 'food' && !f.hidden) {
      let goal = this.foodGoal(view, f);
      if (traitor) goal = this.sabotage(view, me, goal, dt, inp);
      this.jitterT -= dt;
      if (this.jitterT <= 0) { this.jitterT = range(this.rng, 0.6, 1.6); this.jitter = range(this.rng, -0.3, 0.3); }
      const g = rot(goal, this.jitter);
      inp.mx = g.x; inp.my = g.y;
      return inp;
    }

    // ---- carrying a crumb ----
    if (typeof me.hold === 'number') {
      if (traitor) {
        this.eatT -= dt;
        const watchers = view.players.filter(p => p.id !== me.id && dist(p, me) < 160).length;
        if (this.eatT <= 0 && watchers === 0) { inp.act = true; return inp; }
      }
      const s = steer(view, me, CFG.ANT_R, view.nest);
      inp.mx = s.x; inp.my = s.y;
      return inp;
    }

    if (traitor) {
      // trip people walking near the food
      if (me.tripCd <= 0 && rand(this.rng) < 0.6 * dt) {
        const near = this.nearestOther(view, me, CFG.TRIP_RANGE - 4);
        if (near && near.hold === 'food' && !this.isFellow(view, near.id)) inp.act = true;
      }
      // plant a fake scent far from the food, ideally before the real one is found
      if (me.scentsLeft > 0 && me.scentCd <= 0 && dist(me, f) > 600 && dist(me, view.nest) > 300 &&
          rand(this.rng) < (view.foodFound ? 0.08 : 0.3) * dt) inp.scent = true;
    }

    // ---- head for the food (if seen) or the nearest scent ----
    let goal = null;
    if (traitor) { if (view.foodFound) goal = f; }
    else if (!f.hidden) goal = f;
    else if (view.scents.length) {
      let bd = 1e9;
      for (const sc of view.scents) { const d = dist(sc, me); if (d < bd) { bd = d; goal = sc; } }
    }
    if (goal) {
      if (!f.hidden && dist(me, f) < f.r + CFG.ANT_R + CFG.GRAB_RANGE - 3) { inp.grab = true; return inp; }
      let tgt = goal;
      if (!f.hidden && dist(me, f) < f.r + 40) {
        const a = (this.id * 2.39996) % (Math.PI * 2);
        tgt = { x: f.x + Math.cos(a) * (f.r + 6), y: f.y + Math.sin(a) * (f.r + 6) };
      }
      const s = steer(view, me, CFG.ANT_R, tgt);
      inp.mx = s.x; inp.my = s.y;
      return inp;
    }

    // ---- foraging: crumbs and wandering ----
    if (this.gatherer || traitor) {
      let best = null, bd = traitor ? 90 : 120;
      for (const c of view.crumbs) {
        if (!c.alive || c.carrier !== null) continue;
        const d = dist(c, me);
        if (d < bd) { bd = d; best = c; }
      }
      if (best && (!traitor || rand(this.rng) < 0.5)) {
        if (bd < 12) { inp.grab = true; this.eatT = range(this.rng, 1, 3); return inp; }
        const s = steer(view, me, CFG.ANT_R, best); inp.mx = s.x; inp.my = s.y; return inp;
      }
    }
    this.wpT -= dt;
    if (!this.wp || this.wpT <= 0 || dist(me, this.wp) < 40) {
      for (let i = 0; i < 8; i++) {
        this.wp = { x: range(this.rng, 100, CFG.WORLD_W - 100), y: range(this.rng, 100, CFG.WORLD_H - 100) };
        if (!traitor || dist(this.wp, f) > 700) break; // the traitor quietly searches elsewhere
      }
      this.wpT = range(this.rng, 5, 10);
    }
    const s = steer(view, me, CFG.ANT_R, this.wp);
    inp.mx = s.x; inp.my = s.y;
    return inp;
  }

  topSuspect(view, me) {
    let best = null, bs = 0;
    for (const p of view.players) {
      if (p.id === me.id || p.web > 0) continue;
      const sc = this.susp[p.id] || 0;
      if (sc > bs) { bs = sc; best = p; }
    }
    return best;
  }

  // ---- antennae meeting: say something, then vote ----
  meeting(view, inp) {
    const m = view.meeting, me = view.players.find(p => p.id === this.id);
    if (!m || !me || me.web > 0) return inp;
    if (this.meetingKey !== m.caller + ':' + view.round + ':' + Math.round(view.timeLeft - m.t)) {
      this.meetingKey = m.caller + ':' + view.round + ':' + Math.round(view.timeLeft - m.t);
      this.sayAt = range(this.rng, 0.8, 5); this.voteAt = range(this.rng, 6, 13); this.said = false; this.chatSeen = 0;
    }
    const elapsed = CFG.MEETING_TIME - m.t;
    const name = id => view.players.find(p => p.id === id)?.name;
    // read chat: names mentioned become more (or less) suspicious
    for (; this.chatSeen < m.chat.length; this.chatSeen++) {
      const c = m.chat[this.chatSeen];
      if (c.id === me.id) continue;
      for (const p of view.players) {
        if (p.id === c.id || !c.text.includes(p.name)) continue;
        if (p.id === me.id) this.addSusp(c.id, 1.5, 'none');      // they accused me, and I know I'm honest
        else if (!view.amTraitor) this.addSusp(p.id, 1.2 + (c.id === view.me ? 0 : 0), null);
      }
    }
    if (!this.said && elapsed > this.sayAt) {
      this.said = true;
      let line;
      const onMe = m.chat.some(c => c.id !== me.id && c.text.includes(me.name));
      if (view.amTraitor) {
        // frame the honest ant others already suspect, or anyone near the food
        const honest = view.players.filter(p => !view.traitors.includes(p.id) && p.web <= 0);
        const victim = honest.sort((a, b) => view.players.filter(q => q.vote === b.id).length - view.players.filter(q => q.vote === a.id).length)[0];
        this.frame = victim?.id;
        line = onMe ? pick(this.rng, LINES.defend) : pick(this.rng, rand(this.rng) < 0.6 ? LINES.pull : LINES.trip).replace('{X}', victim?.name || '???');
      } else {
        const top = this.topSuspect(view, me);
        if (onMe && (!top || this.susp[top.id] < 2)) line = pick(this.rng, LINES.defend);
        else if (top && this.susp[top.id] > 1.6) line = pick(this.rng, LINES[this.topWhy(top.id)] || LINES.pull).replace('{X}', top.name);
        else line = pick(this.rng, LINES.none);
      }
      inp.say = line;
      return inp;
    }
    if (me.mvote === null && elapsed > this.voteAt) {
      if (view.amTraitor) {
        const counts = {};
        for (const p of view.players) if (p.mvote !== null && p.mvote !== 'skip') counts[p.mvote] = (counts[p.mvote] || 0) + 1;
        const band = Object.entries(counts).sort((a, b) => b[1] - a[1]).find(([id]) => !view.traitors.includes(+id));
        inp.mvote = band ? +band[0] : (this.frame !== undefined && rand(this.rng) < 0.5 ? this.frame : 'skip');
      } else {
        const top = this.topSuspect(view, me);
        const conviction = top ? Math.min(0.8, Math.max(0, (this.susp[top.id] - 3) / 7)) : 0;
        inp.mvote = top && rand(this.rng) < conviction ? top.id : 'skip';
      }
    }
    return inp;
  }

  nearestOther(view, me, maxD) {
    let best = null, bd = maxD;
    for (const p of view.players) {
      if (p.id === me.id || p.web > 0) continue;
      const d = dist(p, me);
      if (d < bd) { bd = d; best = p; }
    }
    return best;
  }

  foodGoal(view, f) {
    const dt = CFG.TICK;
    const sp = Math.hypot(f.vx, f.vy);
    if (f.carriers >= 3 && sp < 6) this.stuckT += dt; else this.stuckT = Math.max(0, this.stuckT - dt);
    if (this.stuckT > 1.5) { this.escapeT = 1.6; this.stuckT = 0; }
    let g = steer(view, f, f.r, view.nest);
    if (this.escapeT > 0) {
      this.escapeT -= dt;
      let nr = null, nd = 1e9;
      for (const k of view.rocks) { const d = dist(k, f) - k.r; if (d < nd) { nd = d; nr = k; } }
      if (nr && nd < 30) {
        const away = norm(f.x - nr.x, f.y - nr.y);
        const home = norm(view.nest.x - f.x, view.nest.y - f.y);
        const t1 = { x: -away.y, y: away.x }, t2 = { x: away.y, y: -away.x };
        const t = (t1.x * home.x + t1.y * home.y) > (t2.x * home.x + t2.y * home.y) ? t1 : t2;
        g = norm(away.x * 0.6 + t.x, away.y * 0.6 + t.y);
      }
    }
    return g;
  }

  sabotage(view, me, goal, dt, inp) {
    const onMe = view.players.filter(p => p.vote === me.id).length;
    this.modeT -= dt;
    if (onMe > 0 && this.mode !== 'help') { this.mode = 'help'; this.modeT = range(this.rng, 5, 8); }
    if (this.modeT <= 0) {
      const r = rand(this.rng);
      this.mode = r < 0.4 ? 'help' : r < 0.75 ? 'drag' : 'veer';
      this.modeT = range(this.rng, 2.5, 6);
      this.veerSide = rand(this.rng) < 0.5 ? 1 : -1;
      this.dragAng = range(this.rng, -1.0, 1.0);
    }
    if (me.tripCd <= 0 && rand(this.rng) < 0.35 * dt) {
      const near = this.nearestOther(view, me, CFG.TRIP_RANGE - 3);
      if (near && near.hold === 'food' && !this.isFellow(view, near.id)) inp.act = true;
    }
    if (this.mode === 'drag') return rot(goal, Math.PI + this.dragAng);
    if (this.mode === 'veer') return rot(goal, this.veerSide * 1.9);
    return goal;
  }

  // Honest bots watch how others behave and grow suspicious.
  observe(view, me, dt) {
    const f = view.food;
    const ideal = f.hidden ? null : norm(view.nest.x - f.x, view.nest.y - f.y);
    for (const p of view.players) {
      if (p.id === me.id || dist(p, me) > CFG.VISION) continue;
      if (p.hold === 'food' && ideal) {
        const pl = Math.hypot(p.push.x, p.push.y);
        // in a pile of ants it's hard to tell who's doing what: sometimes blame the wrong one
        if (pl > 0.2 && rand(this.rng) < 0.4) {
          const pile = view.players.filter(q => q.hold === 'food' && q.id !== me.id);
          const a = (p.push.x * ideal.x + p.push.y * ideal.y) / pl;
          if (a < 0.2 && pile.length) this.addSusp(pick(this.rng, pile).id, 0.6 * dt, 'pull');
          continue;
        }
        if (pl < 0.2) this.addSusp(p.id, 0.15 * dt, 'slack');
        else {
          const a = (p.push.x * ideal.x + p.push.y * ideal.y) / pl;
          if (a < -0.3) this.addSusp(p.id, 0.7 * dt, 'pull'); else if (a < 0.2) this.addSusp(p.id, 0.2 * dt, 'pull'); else this.addSusp(p.id, -0.25 * dt);
        }
      } else this.addSusp(p.id, -0.05 * dt);
      const votes = view.players.filter(q => q.vote === p.id && q.id !== me.id).length;
      if (votes) this.addSusp(p.id, votes * 0.25 * dt, null);
      if (this.susp[p.id] < 0) this.susp[p.id] = 0;
    }
    for (const e of view.events) {
      if (e.t === 'trip' && dist(e, me) < CFG.VISION && e.id !== me.id) {
        for (const p of view.players) if (p.id !== e.id && p.id !== me.id && dist(p, e) < CFG.TRIP_RANGE + 8) this.addSusp(p.id, 1.8, 'trip');
      }
      if (e.t === 'trip' && e.id === me.id) {
        for (const p of view.players) if (p.id !== me.id && dist(p, e) < CFG.TRIP_RANGE + 4) this.addSusp(p.id, 2.5, 'trip');
      }
      if (e.t === 'eat' && dist(e, me) < CFG.VISION) this.addSusp(e.id, 6, 'eat');
      if (e.t === 'wrong') { for (const v of e.voters) this.addSusp(v, 1, null); this.susp[e.id] = 0; }
    }
  }
}
