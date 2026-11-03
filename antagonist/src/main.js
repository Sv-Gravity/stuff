import { CFG } from './config.js';
import { LocalSession } from './session.js';
import { Renderer } from './render.js';
import { Controls, isTouch, setupTouch } from './input.js';
import { MeetingUI } from './meeting-ui.js';
import { Sfx } from './sfx.js';

const $ = id => document.getElementById(id);
const canvas = $('game'), menu = $('menu');
const renderer = new Renderer(canvas);
const ctrl = new Controls();
const sfx = new Sfx();
const touch = isTouch();
const meetingUI = new MeetingUI($('meeting'), ctrl);
let session = null, acc = 0, last = performance.now(), running = false;
const ui = { touch, fps: 0, showFps: true };

addEventListener('resize', () => renderer.resize());
renderer.resize();
if (touch) {
  setupTouch(ctrl, $('touch'));
  document.body.classList.add('touch');
}

try {
  const saved = JSON.parse(localStorage.getItem('antagonist.opts') || '{}');
  for (const k of ['name', 'count', 'role', 'mode', 'traitors']) if (saved[k] != null && $(k)) $(k).value = saved[k];
} catch {}
const syncCount = () => { $('countLabel').textContent = $('count').value; };
$('count').addEventListener('input', syncCount); syncCount();

const newSeed = () => (Math.random() * 2 ** 32) >>> 0;
function start() {
  const opts = { name: $('name').value.trim().slice(0, 12) || 'Scout', count: +$('count').value, role: $('role').value, mode: $('mode').value, traitors: $('traitors').value };
  try { localStorage.setItem('antagonist.opts', JSON.stringify(opts)); } catch {}
  session = new LocalSession({ ...opts, seed: newSeed(), sameTraitor: opts.mode === 'same', traitorCount: opts.traitors === 'auto' ? 'auto' : +opts.traitors });
  menu.classList.add('hidden');
  sfx.unlock();
  running = true; acc = 0; last = performance.now();
  renderer.prev = null;
  if (touch) document.documentElement.requestFullscreen?.().catch(() => {});
}
function openMenu() { running = false; menu.classList.remove('hidden'); meetingUI.hide(); }
$('start').addEventListener('click', start);
$('pauseBtn').addEventListener('click', openMenu);
addEventListener('keydown', e => {
  if (e.target && e.target.id === 'mSay') return;
  if (!running && e.key === 'Enter' && !menu.classList.contains('hidden')) { start(); return; }
  if (e.key === 'F3') { ui.showFps = !ui.showFps; e.preventDefault(); }
  if (!running) return;
  if (e.key === 'Escape') openMenu();
  if (e.key === 'Enter' && session.state.phase === 'matchEnd') { session.reset(newSeed()); renderer.prev = null; }
});
canvas.addEventListener('pointerdown', () => {
  if (!running || !session) return;
  const ph = session.state.phase;
  if (ph === 'roundEnd') ctrl.press('ready');
  if (ph === 'matchEnd') { session.reset(newSeed()); renderer.prev = null; }
});

// FPS: smoothed over the last ~half second
let fpsFrames = 0, fpsT = 0;
function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.1, (now - last) / 1000); last = now;
  fpsFrames++; fpsT += dt;
  if (fpsT >= 0.5) { ui.fps = Math.round(fpsFrames / fpsT); fpsFrames = 0; fpsT = 0; }
  if (!session) return;
  if (running) {
    acc += dt;
    // Input is sampled right before each tick, so a key press affects the very next 16 ms step.
    let steps = 0;
    while (acc >= CFG.TICK && steps++ < 8) {
      acc -= CFG.TICK;
      renderer.prev = renderer.snapshot(session.state);
      const events = session.tick(ctrl.sample());
      const v = session.view();
      renderer.onEvents(v, events);
      sfx.onEvents(v, events);
    }
    if (acc > CFG.TICK) acc = 0; // tab was asleep: don't spiral
  }
  const view = session.view();
  if (touch) document.body.classList.toggle('traitor', view.amTraitor);
  meetingUI.update(view, running);
  renderer.draw(view, running ? acc / CFG.TICK : 1, running ? dt : 0, { touch, fps: ui.showFps ? ui.fps : 0 });
}
requestAnimationFrame(frame);

// for automated testing / debugging from the console
window.__antagonist = { get session() { return session; }, start, ctrl };
