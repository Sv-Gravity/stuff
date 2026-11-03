import { CFG } from './config.js';
import { LocalSession } from './session.js';
import { Renderer } from './render.js';
import { Keyboard } from './input.js';
import { Sfx } from './sfx.js';

const canvas = document.getElementById('game');
const menu = document.getElementById('menu');
const renderer = new Renderer(canvas);
const kb = new Keyboard();
const sfx = new Sfx();
let session = null, acc = 0, last = performance.now(), running = false;

addEventListener('resize', () => renderer.resize());
renderer.resize();

const $ = id => document.getElementById(id);
try {
  const saved = JSON.parse(localStorage.getItem('antagonist.opts') || '{}');
  if (saved.name) $('name').value = saved.name;
  if (saved.count) $('count').value = saved.count;
  if (saved.role) $('role').value = saved.role;
  if (saved.mode) $('mode').value = saved.mode;
} catch {}
const syncCount = () => { $('countLabel').textContent = $('count').value; };
$('count').addEventListener('input', syncCount); syncCount();

function start() {
  const opts = { name: $('name').value.trim().slice(0, 12) || 'You', count: +$('count').value, role: $('role').value, mode: $('mode').value };
  try { localStorage.setItem('antagonist.opts', JSON.stringify(opts)); } catch {}
  session = new LocalSession({ ...opts, seed: (Math.random() * 2 ** 32) >>> 0, sameTraitor: opts.mode === 'same' });
  menu.classList.add('hidden');
  sfx.unlock();
  running = true; acc = 0; last = performance.now();
  renderer.prev = null;
}
$('start').addEventListener('click', start);
addEventListener('keydown', e => {
  if (!running && e.key === 'Enter' && !menu.classList.contains('hidden')) start();
  if (!running) return;
  if (e.key === 'Escape') { running = false; menu.classList.remove('hidden'); }
  if (e.key === 'Enter' && session.state.phase === 'matchEnd') { session.reset((Math.random() * 2 ** 32) >>> 0); renderer.prev = null; }
});

function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.1, (now - last) / 1000); last = now;
  if (!session) return;
  if (running) {
    acc += dt;
    while (acc >= CFG.TICK) {
      acc -= CFG.TICK;
      renderer.prev = renderer.snapshot(session.view());
      const events = session.tick(kb.sample());
      const v = session.view();
      renderer.onEvents(v, events);
      sfx.onEvents(v, events);
    }
  }
  renderer.draw(session.view(), running ? acc / CFG.TICK : 1, running ? dt : 0);
}
requestAnimationFrame(frame);

// for automated testing / debugging from the console
window.__antagonist = { get session() { return session; }, start };
