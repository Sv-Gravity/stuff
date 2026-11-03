// The antennae-meeting screen (DOM, so it's easy to tap and type on).
import { CFG } from './config.js';

export class MeetingUI {
  constructor(root, ctrl) {
    this.root = root; this.ctrl = ctrl; this.sig = '';
    this.list = root.querySelector('#mList'); this.chat = root.querySelector('#mChat');
    this.info = root.querySelector('#mInfo'); this.title = root.querySelector('#mTitle');
    root.querySelector('#mSkip').addEventListener('click', () => { this.ctrl.extra.mvote = 'skip'; });
    root.querySelector('#mForm').addEventListener('submit', e => {
      e.preventDefault();
      const inp = root.querySelector('#mSay');
      if (inp.value.trim()) this.ctrl.extra.say = inp.value.trim();
      inp.value = '';
    });
    this.list.addEventListener('click', e => {
      const b = e.target.closest('[data-id]');
      if (b && !b.disabled) this.ctrl.extra.mvote = +b.dataset.id;
    });
    addEventListener('keydown', e => {
      if (this.root.classList.contains('hidden') || e.target.tagName === 'INPUT') return;
      if (e.key === '0') this.ctrl.extra.mvote = 'skip';
      const n = +e.key;
      if (n >= 1 && n <= 9 && this.order && this.order[n - 1] !== undefined) this.ctrl.extra.mvote = this.order[n - 1];
    });
  }
  hide() { this.root.classList.add('hidden'); }
  update(view, running) {
    const m = view.meeting;
    if (!running || view.phase !== 'meeting' || !m) { if (!this.root.classList.contains('hidden')) { this.hide(); this.sig = ''; } return; }
    this.root.classList.remove('hidden');
    const me = view.players.find(p => p.id === view.me);
    const caller = view.players.find(p => p.id === m.caller);
    this.title.textContent = `${caller?.name || '?'} tapped antennae: MEETING`;
    this.info.textContent = `${Math.ceil(m.t)}s to vote · the round clock is still running (${Math.ceil(view.timeLeft)}s left) · majority needed`;
    const sig = JSON.stringify([view.players.map(p => [p.mvote !== null, p.web > 0]), me.mvote, m.chat.length, view.traitors]);
    if (sig === this.sig) return;
    this.sig = sig;
    const others = view.players.filter(p => p.id !== view.me);
    this.order = others.map(p => p.id);
    this.list.innerHTML = '';
    others.forEach((p, i) => {
      const b = document.createElement('button');
      b.dataset.id = p.id;
      b.disabled = p.web > 0 || me.web > 0;
      b.className = 'mrow' + (me.mvote === p.id ? ' picked' : '');
      const tag = view.traitors.includes(p.id) ? ' <em>traitor</em>' : '';
      b.innerHTML = `<span class="dot" style="background:${p.color}"></span><span class="nm">${i + 1}. ${esc(p.name)}${tag}</span><span class="st">${p.web > 0 ? 'webbed' : p.mvote !== null ? '✔ voted' : ''}</span>`;
      this.list.appendChild(b);
    });
    const meRow = document.createElement('div');
    meRow.className = 'mme';
    meRow.textContent = me.web > 0 ? "You're webbed: you can't vote." : me.mvote === 'skip' ? 'You voted to skip.' : me.mvote !== null ? 'Vote cast. You can still change it.' : 'Pick who to web, or skip (0).';
    this.list.appendChild(meRow);
    this.chat.innerHTML = m.chat.map(c => {
      const p = view.players.find(q => q.id === c.id);
      return `<div><b style="color:${p?.color}">${esc(p?.name || '?')}:</b> ${esc(c.text)}</div>`;
    }).join('') || '<div class="hint">Nobody has said anything yet.</div>';
    this.chat.scrollTop = this.chat.scrollHeight;
  }
}
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
