// Keyboard + touch -> the same input object bots produce. Button presses are
// latched until the next sim tick consumes them, so a quick tap is never lost.
const KEYMAP = { ' ': 'grab', e: 'grab', q: 'act', f: 'act', v: 'vote', r: 'vote', m: 'meet', t: 'scent' };

export class Controls {
  constructor() {
    this.down = new Set();
    this.latched = {};
    this.stick = { x: 0, y: 0 };
    this.extra = {};         // mvote / say from the meeting screen
    this.enabled = true;
    addEventListener('keydown', e => {
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
      const k = e.key.toLowerCase();
      if ([' ', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k)) e.preventDefault();
      if (e.repeat) return;
      this.down.add(k);
      if (KEYMAP[k]) this.latched[KEYMAP[k]] = true;
    });
    addEventListener('keyup', e => this.down.delete(e.key.toLowerCase()));
    addEventListener('blur', () => { this.down.clear(); this.stick = { x: 0, y: 0 }; });
  }
  press(name) { this.latched[name] = true; }
  sample() {
    const d = this.down;
    let mx = (d.has('d') || d.has('arrowright') ? 1 : 0) - (d.has('a') || d.has('arrowleft') ? 1 : 0);
    let my = (d.has('s') || d.has('arrowdown') ? 1 : 0) - (d.has('w') || d.has('arrowup') ? 1 : 0);
    if (!mx && !my) { mx = this.stick.x; my = this.stick.y; }
    const out = { mx, my, grab: !!this.latched.grab, act: !!this.latched.act, vote: !!this.latched.vote, meet: !!this.latched.meet, scent: !!this.latched.scent, ready: !!this.latched.ready, ...this.extra };
    this.latched = {}; this.extra = {};
    return out;
  }
}

export const isTouch = () => matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;

// Virtual joystick (left thumb, anywhere on the left half) + action buttons (right thumb).
export function setupTouch(ctrl, root) {
  root.classList.add('on');
  const base = root.querySelector('.stick'), knob = root.querySelector('.knob');
  let id = null, cx = 0, cy = 0;
  const R = 55;
  const zone = root.querySelector('.stickzone');
  zone.addEventListener('pointerdown', e => {
    id = e.pointerId; cx = e.clientX; cy = e.clientY;
    base.style.left = cx + 'px'; base.style.top = cy + 'px'; base.classList.add('active');
    knob.style.transform = 'translate(-50%,-50%)';
    zone.setPointerCapture(id); e.preventDefault();
  });
  zone.addEventListener('pointermove', e => {
    if (e.pointerId !== id) return;
    let dx = e.clientX - cx, dy = e.clientY - cy;
    const l = Math.hypot(dx, dy);
    if (l > R) { dx *= R / l; dy *= R / l; }
    knob.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
    const m = Math.hypot(dx, dy) / R;
    ctrl.stick = m < 0.2 ? { x: 0, y: 0 } : { x: dx / R, y: dy / R };
  });
  const end = e => { if (e.pointerId !== id) return; id = null; ctrl.stick = { x: 0, y: 0 }; base.classList.remove('active'); };
  zone.addEventListener('pointerup', end); zone.addEventListener('pointercancel', end);
  root.querySelectorAll('[data-act]').forEach(b => b.addEventListener('pointerdown', e => {
    e.preventDefault(); e.stopPropagation(); ctrl.press(b.dataset.act);
    b.classList.add('hit'); setTimeout(() => b.classList.remove('hit'), 120);
  }));
}
