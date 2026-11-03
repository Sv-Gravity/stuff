// Bot brains. A bot only ever sees viewFor(state, itsId) – the same thing a remote
// human would see – and returns the same input shape a keyboard produces.
import { CFG } from './config.js';
import { rand, range } from './rng.js';

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const norm = (x, y) => { const l = Math.hypot(x, y) || 1; return { x: x / l, y: y / l }; };
const rot = (v, a) => ({ x: v.x * Math.cos(a) - v.y * Math.sin(a), y: v.x * Math.sin(a) + v.y * Math.cos(a) });

// Steering from `from` (radius r) toward `to`, sliding around rocks.
export function steer(view, from, r, to) {
  let d = norm(to.x - from.x, to.y - from.y);
  let ax = d.x, ay = d.y;
  for (const k of view.rocks) {
    const ox = k.x - from.x, oy = k.y - from.y;
    const dd = Math.hypot(ox, oy), clear = dd - k.r - r;
    if (clear > 80 || (ox * d.x + oy * d.y) < 0) continue;
    // which side to go round: the side the goal is on
    const cross = d.x * oy - d.y * ox;
    const side = cross > 0 ? -1 : 1;
    const w = Math.max(0, 1 - clear / 80) * 1.8;
    ax += -oy / dd * side * w; ay += ox / dd * side * w;
    if (clear < 6) { ax -= ox / dd * 0.8; ay -= oy / dd * 0.8; }
  }
  return norm(ax, ay);
}

export class Bot {
  constructor(id, seed) {
    this.id = id;
    this.rng = { r: (seed * 2654435761 + id * 97) >>> 0 };
    this.wp = null; this.wpT = 0;
    this.susp = {};
    this.jitter = 0; this.jitterT = 0;
    this.mode = 'help'; this.modeT = 0;
    this.lastRound = -1;
    this.stuckT = 0; this.escapeT = 0;
    this.eatT = 0;
    this.gatherer = rand(this.rng) < 0.35;
    this.wantGrabT = 0;
  }

  resetRound(view) {
    this.lastRound = view.round;
    this.wp = null; this.susp = {}; this.mode = 'help'; this.modeT = 0; this.stuckT = 0; this.escapeT = 0;
    this.reaction = range(this.rng, 0.2, 1.2);
  }

  think(view) {
    const dt = CFG.TICK;
    const inp = { mx: 0, my: 0, grab: false, act: false, vote: false };
    if (view.round !== this.lastRound) this.resetRound(view);
    if (view.phase !== 'play') return inp;
    const me = view.players.find(p => p.id === this.id);
    if (!me || me.stun > 0 || me.web > 0) return inp;
    if (this.reaction > 0) { this.reaction -= dt; return inp; }

    const f = view.food;
    const traitor = view.amTraitor;
    this.observe(view, me, dt);

    // ---- accusations ----
    if (!me.voteLocked) {
      let target = null;
      if (traitor) {
        // frame someone if people are onto me
        const onMe = view.players.filter(p => p.vote === me.id).length;
        if (onMe > 0 && me.vote === null) target = this.nearestOther(view, me, CFG.VOTE_RANGE - 5);
      } else {
        let best = null, bs = 3.4;
        for (const p of view.players) {
          if (p.id === me.id || p.web > 0) continue;
          const sc = this.susp[p.id] || 0;
          if (sc > bs) { bs = sc; best = p; }
        }
        if (best && best.id !== me.vote) {
          if (dist(best, me) < CFG.VOTE_RANGE - 5) {
            const near = this.nearestOther(view, me, CFG.VOTE_RANGE);
            if (near && near.id === best.id) target = best;
          }
        }
      }
      if (target && target.id !== me.vote) inp.vote = true;
    }

    // ---- carrying the big food ----
    if (me.hold === 'food') {
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

    // ---- traitor trips people walking near it ----
    if (traitor && me.tripCd <= 0 && rand(this.rng) < 0.6 * dt) {
      const near = this.nearestOther(view, me, CFG.TRIP_RANGE - 4);
      if (near && near.hold === 'food') inp.act = true;
    }

    // ---- go to the food once we know where it is ----
    const knows = view.foodFound || dist(me, f) < CFG.VISION * 0.7 || (traitor && view.foodFound);
    if (knows) {
      if (dist(me, f) < f.r + CFG.ANT_R + CFG.GRAB_RANGE - 3) { inp.grab = true; return inp; }
      // spread around the food rather than all queueing on one side
      const a = (this.id * 2.39996) % (Math.PI * 2);
      const tgt = { x: f.x + Math.cos(a) * (f.r + 6), y: f.y + Math.sin(a) * (f.r + 6) };
      const s = steer(view, me, CFG.ANT_R, dist(me, f) < f.r + 40 ? tgt : f);
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
      // the traitor knows where the food is and quietly searches elsewhere
      for (let i = 0; i < 8; i++) {
        this.wp = { x: range(this.rng, 100, CFG.WORLD_W - 100), y: range(this.rng, 100, CFG.WORLD_H - 100) };
        if (!traitor || dist(this.wp, f) > 700) break;
      }
      this.wpT = range(this.rng, 5, 10);
    }
    const s = steer(view, me, CFG.ANT_R, this.wp);
    inp.mx = s.x; inp.my = s.y;
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
        // slide along the rock, on the side that faces home
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
      this.mode = r < 0.3 ? 'help' : r < 0.8 ? 'drag' : 'veer';
      this.modeT = range(this.rng, 2.5, 6);
      this.veerSide = rand(this.rng) < 0.5 ? 1 : -1;
      this.dragAng = range(this.rng, -0.6, 0.6);
    }
    if (me.tripCd <= 0 && rand(this.rng) < 0.35 * dt) {
      const near = this.nearestOther(view, me, CFG.TRIP_RANGE - 3);
      if (near && near.hold === 'food') inp.act = true;
    }
    if (this.mode === 'drag') return rot(goal, Math.PI + this.dragAng);
    if (this.mode === 'veer') return rot(goal, this.veerSide * 1.9);
    return goal;
  }

  // Honest bots watch how others behave and grow suspicious.
  observe(view, me, dt) {
    const f = view.food;
    const ideal = norm(view.nest.x - f.x, view.nest.y - f.y);
    for (const p of view.players) {
      if (p.id === me.id) continue;
      if (dist(p, me) > CFG.VISION) continue;
      let s = this.susp[p.id] || 0;
      if (p.hold === 'food') {
        const pl = Math.hypot(p.push.x, p.push.y);
        if (pl < 0.2) s += 0.15 * dt;
        else {
          const a = (p.push.x * ideal.x + p.push.y * ideal.y) / pl;
          if (a < -0.3) s += 1.1 * dt; else if (a < 0.2) s += 0.3 * dt; else s -= 0.25 * dt;
        }
      } else s -= 0.05 * dt;
      // trust others' accusations a little
      if (p.id !== me.id) {
        const votes = view.players.filter(q => q.vote === p.id && q.id !== me.id).length;
        s += votes * 0.25 * dt;
      }
      this.susp[p.id] = Math.max(0, s);
    }
    for (const e of view.events) {
      if (e.t === 'trip' && dist(e, me) < CFG.VISION && e.id !== me.id) {
        for (const p of view.players) if (p.id !== e.id && p.id !== me.id && dist(p, e) < CFG.TRIP_RANGE + 8) this.susp[p.id] = (this.susp[p.id] || 0) + 1.8;
      }
      if (e.t === 'trip' && e.id === me.id) {
        // I got tripped: whoever was right next to me is very suspicious
        for (const p of view.players) if (p.id !== me.id && dist(p, e) < CFG.TRIP_RANGE + 4) this.susp[p.id] = (this.susp[p.id] || 0) + 2.5;
      }
      if (e.t === 'eat' && dist(e, me) < CFG.VISION) this.susp[e.id] = (this.susp[e.id] || 0) + 6;
      if (e.t === 'wrong') for (const v of e.voters) this.susp[v] = (this.susp[v] || 0) + 1;
      if (e.t === 'wrong') this.susp[e.id] = 0;
    }
  }
}
