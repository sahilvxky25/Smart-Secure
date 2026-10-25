/* Shared helpers + global state (classic scripts share these across files) */
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api = async (u, m = 'GET', b) => {
  const r = await fetch(u, {method: m, headers: {'Content-Type': 'application/json'}, body: b ? JSON.stringify(b) : undefined, keepalive: m != 'GET'});
  if (r.status == 401 && !u.startsWith('/api/auth')) { location.reload(); return {}; }
  return r.json();
};

let lib = [], T = [], me, st, cur, curK, filt = 'all', feat = [], fi = 0, pick = [], sv, upT, lastSave = 0, hb, sleepT;

const hue = s => Math.abs([...s].reduce((a, c) => a * 31 + c.charCodeAt(0) | 0, 0)) % 360;
const bg = e => `url(/api/thumb/${e.id}),linear-gradient(135deg,hsl(${hue(e.id)} 45% 28%),hsl(${(hue(e.id) + 60) % 360} 50% 14%))`;
const dur = s => s ? (s >= 3600 ? Math.floor(s / 3600) + 'h ' : '') + Math.round(s % 3600 / 60) + 'm' : '';
const fsz = s => s > 1e9 ? (s / 1e9).toFixed(1) + ' GB' : Math.round(s / 1e6) + ' MB';
const mmss = t => Math.floor(t / 60) + ':' + String(Math.floor(t % 60)).padStart(2, '0');
const seen = id => st.watched.includes(id);
const pr = e => { const p = st.prog[e.id]; return !!(p && p.d && p.t > 5 && !seen(e.id)); };
const K = k => T.find(t => t.key == k);
const epl = e => `S${e.season}:E${e.ep}`;
const save = now => { clearTimeout(sv); sv = setTimeout(() => api('/api/state', 'PUT', st), now ? 0 : 800); };
const toast = m => { const t = $('#toast'); t.textContent = m; t.hidden = false; clearTimeout(t._t); t._t = setTimeout(() => t.hidden = true, 2200); };
const S = {
  az: (a, b) => a.title.localeCompare(b.title), new: (a, b) => b.added - a.added, old: (a, b) => a.added - b.added,
  long: (a, b) => b.rep.dur - a.rep.dur, year: (a, b) => b.year - a.year
};

/* v3 additions */
let META = {}, queue = [], dls = {};
const bgT = t => `url(${t.art || '/api/thumb/' + t.rep.id}),` + bg(t.rep);   // TMDB backdrop -> video thumbnail -> gradient
