'use strict';
/* =====================================================================
   Chatly web client - vanilla JS, no build step, no third-party code.
   All dynamic text is inserted with textContent (never innerHTML) -> XSS safe.
   ===================================================================== */

/* ---------- tiny DOM helper ---------- */
function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style') Object.assign(el.style, v);
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k in el) el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const $ = (s, r = document) => r.querySelector(s);

const ICONS = {
  search: 'M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  send: 'M2.01 21 23 12 2.01 3 2 10l15 2-15 2z',
  back: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  emoji: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm3.5-10c.83 0 1.5-.67 1.5-1.5S16.33 7 15.5 7 14 7.67 14 8.5s.67 1.5 1.5 1.5zm-7 0C9.33 10 10 9.33 10 8.5S9.33 7 8.5 7 7 7.67 7 8.5 7.67 10 8.5 10zm3.5 7.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z',
  chat: 'M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z',
  group: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5s-3 1.34-3 3 1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
  lock: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM9 8V6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9z',
  reply: 'M10 9V5l-7 7 7 7v-4.1c5 0 8.5 1.6 11 5.1-1-5-4-10-11-11z',
  trash: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  copy: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  down: 'M16.59 8.59 12 13.17 7.41 8.59 6 10l6 6 6-6z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.48.48 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  addperson: 'M15 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm-9-2V7H4v3H1v2h3v3h2v-3h3v-2H6zm9 4c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  info: 'M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z',
};
function icon(name, size = 24) {
  const s = h('span', { class: 'ico' });
  s.innerHTML = `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="currentColor" aria-hidden="true"><path d="${ICONS[name]}"/></svg>`;
  return s;
}
function tickIcon(status) {
  const t = h('span', { class: 'tick' + (status === 'read' ? ' read' : '') });
  t.innerHTML = status === 'sent'
    ? '<svg viewBox="0 0 17 12" width="16" height="12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6.5l3.5 3.5 7-8"/></svg>'
    : '<svg viewBox="0 0 17 12" width="17" height="12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M1 6.5L4.5 10 10.5 2.5"/><path d="M6.5 8.5l1.5 1.5 7-8"/></svg>';
  return t;
}

/* ---------- state ---------- */
const S = {
  me: null, chats: new Map(), msgs: new Map(), more: new Map(), loadingOlder: false,
  active: null, ws: null, wsTries: 0, typing: new Map(), replyTo: null, filter: '',
  everConnected: false, offline: false,
};
const root = $('#root');
const isTouch = matchMedia('(pointer:coarse)').matches;

/* ---------- API ---------- */
async function api(method, url, body) {
  let res;
  try {
    res = await fetch('/api' + url, {
      method, credentials: 'same-origin',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch { throw Object.assign(new Error('Cannot reach the server. Check your connection.'), { status: 0 }); }
  let data = null;
  try { data = await res.json(); } catch { /* empty */ }
  if (!res.ok) {
    if (res.status === 401 && S.me && !url.startsWith('/auth/')) { sessionLost(); }
    throw Object.assign(new Error((data && data.error) || 'Something went wrong.'), { status: res.status, data });
  }
  return data;
}

/* ---------- misc helpers ---------- */
const COLORS = ['#e5575a', '#d9822b', '#5a9e2f', '#1f9d8f', '#3b82c4', '#7d5bd0', '#c2519c', '#6b7a8f'];
const colorFor = (id) => COLORS[Math.abs(Number(id) || 0) % COLORS.length];
function avatar(name, id, size = 49, isGroup = false) {
  const a = h('div', { class: 'avatar', style: { '--s': size + 'px', background: colorFor(id + (isGroup ? 3 : 0)) } });
  if (isGroup) a.append(icon('group', Math.round(size * .55))); else a.append((name || '?').trim().charAt(0) || '?');
  return a;
}
const sameDay = (a, b) => new Date(a).toDateString() === new Date(b).toDateString();
const fmtTime = (t) => new Date(t).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
function dayLabel(t) {
  const d = new Date(t), now = new Date(), diff = Math.round((new Date(now.toDateString()) - new Date(d.toDateString())) / 864e5);
  if (diff === 0) return 'Today'; if (diff === 1) return 'Yesterday';
  if (diff < 7) return d.toLocaleDateString([], { weekday: 'long' });
  return d.toLocaleDateString([], { day: 'numeric', month: 'long', year: 'numeric' });
}
function listTime(t) {
  const d = new Date(t), now = new Date(), diff = Math.round((new Date(now.toDateString()) - new Date(d.toDateString())) / 864e5);
  if (diff === 0) return fmtTime(t); if (diff === 1) return 'Yesterday';
  if (diff < 7) return d.toLocaleDateString([], { weekday: 'long' });
  return d.toLocaleDateString([], { day: 'numeric', month: 'numeric', year: '2-digit' });
}
function lastSeenText(m) {
  if (m.online) return 'online';
  if (!m.lastSeen) return '';
  const d = new Date(m.lastSeen), diff = Math.round((new Date(new Date().toDateString()) - new Date(d.toDateString())) / 864e5);
  return 'last seen ' + (diff === 0 ? 'today' : diff === 1 ? 'yesterday' : d.toLocaleDateString([], { day: 'numeric', month: 'short' })) + ' at ' + fmtTime(m.lastSeen);
}
function linkify(text) {
  const out = []; const re = /(https?:\/\/[^\s<]+[^\s<.,;:!?)"'\]])/g; let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(h('a', { href: m[0], target: '_blank', rel: 'noopener noreferrer nofollow' }, m[0]));
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
function toast(msg, bad = false) {
  let box = $('.toasts'); if (!box) { box = h('div', { class: 'toasts' }); document.body.append(box); }
  const t = h('div', { class: 'toast' + (bad ? ' bad' : '') }, msg); box.append(t);
  setTimeout(() => t.remove(), bad ? 5000 : 3000);
}
async function busy(btn, fn) {
  const label = [...btn.childNodes]; btn.disabled = true; btn.replaceChildren(h('span', { class: 'spin' }));
  try { return await fn(); } finally { btn.disabled = false; btn.replaceChildren(...label); }
}
function field(label, props = {}, hint) {
  const input = props.tag === 'select' ? h('select', props) : h('input', props);
  const wrap = h('label', { class: 'field' }, h('span', {}, label), input, hint ? h('small', {}, hint) : null);
  return { wrap, input };
}
function pwField(label, props = {}, hint) {
  const input = h('input', { type: 'password', autocomplete: 'current-password', ...props });
  const toggle = h('button', { type: 'button', onClick: () => { const s = input.type === 'password'; input.type = s ? 'text' : 'password'; toggle.textContent = s ? 'Hide' : 'Show'; } }, 'Show');
  const wrap = h('label', { class: 'field' }, h('span', {}, label), h('div', { class: 'pw' }, input, toggle), hint ? h('small', {}, hint) : null);
  return { wrap, input };
}
const POPUP_CLOSERS = [];
function closePopups() { while (POPUP_CLOSERS.length) POPUP_CLOSERS.pop()(); }
function popup(anchor, items, align = 'right') {
  closePopups();
  const r = anchor.getBoundingClientRect();
  const p = h('div', { class: 'popup', role: 'menu' }, items.filter(Boolean).map((i) =>
    h('button', { class: i.danger ? 'danger' : '', onClick: () => { closePopups(); i.run(); } }, i.icon ? icon(i.icon, 20) : null, i.label)));
  document.body.append(p);
  const w = p.offsetWidth, hgt = p.offsetHeight;
  let left = align === 'right' ? r.right - w : r.left; left = Math.max(8, Math.min(left, innerWidth - w - 8));
  let top = r.bottom + 4; if (top + hgt > innerHeight - 8) top = Math.max(8, r.top - hgt - 4);
  Object.assign(p.style, { left: left + 'px', top: top + 'px' });
  const off = (e) => { if (!p.contains(e.target)) closePopups(); };
  setTimeout(() => document.addEventListener('pointerdown', off), 0);
  POPUP_CLOSERS.push(() => { p.remove(); document.removeEventListener('pointerdown', off); });
}
function openModal(title, body, { wide = false, onClose } = {}) {
  closePopups();
  const close = () => { ov.remove(); document.removeEventListener('keydown', esc); onClose && onClose(); };
  const esc = (e) => { if (e.key === 'Escape') close(); };
  const bodyEl = h('div', { class: 'modal-body' }, body);
  const ov = h('div', { class: 'overlay', onMousedown: (e) => { if (e.target === ov) close(); } },
    h('div', { class: 'modal' + (wide ? ' wide' : ''), role: 'dialog', 'aria-label': title },
      h('div', { class: 'modal-head' }, h('h3', {}, title), h('button', { class: 'iconbtn', 'aria-label': 'Close', onClick: close }, icon('close'))),
      bodyEl));
  document.addEventListener('keydown', esc); document.body.append(ov);
  return { close, bodyEl, setBody: (...n) => bodyEl.replaceChildren(...n.flat()) };
}

/* ---------- theme ---------- */
function applyTheme() {
  const pref = localStorage.getItem('theme') || 'auto';
  const dark = pref === 'dark' || (pref === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  $('meta[name=theme-color]').content = dark ? '#202c33' : '#008069';
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
applyTheme();

/* =====================================================================
   AUTH SCREENS
   ===================================================================== */
const LOGO = '<svg class="logo" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#00a884"/><path d="M32 14c-10 0-18 7.2-18 16 0 4.2 1.8 8 4.8 10.8L17 50l9.2-4.4c1.8.4 3.7.6 5.8.6 10 0 18-7.2 18-16s-8-16-18-16z" fill="#fff"/></svg>';
function authShell(...content) {
  const brand = h('div', { class: 'brand' }); brand.innerHTML = LOGO; brand.append('Chatly Web');
  root.replaceChildren(h('div', { class: 'auth' }, h('div', { class: 'auth-wrap' }, brand, h('div', { class: 'card' }, content))));
}
const errBox = () => h('div', { class: 'err', hidden: true, role: 'alert' });
function showErr(box, e) { box.textContent = e.message || String(e); box.hidden = false; }

function viewLogin(prefillEmail = '', notice = '') {
  const err = errBox();
  const email = field('Email address', { type: 'email', autocomplete: 'username', required: true, value: prefillEmail, inputMode: 'email' });
  const pw = pwField('Password', { autocomplete: 'current-password', required: true });
  const btn = h('button', { class: 'btn block', type: 'submit' }, 'Sign in');
  const form = h('form', {
    onSubmit: async (e) => {
      e.preventDefault(); err.hidden = true;
      try {
        const r = await busy(btn, () => api('POST', '/auth/login', { email: email.input.value, password: pw.input.value }));
        if (r.twoFactor) return view2fa(r.ticket);
        await enterApp(r.user);
      } catch (x) { showErr(err, x); }
    },
  }, email.wrap, pw.wrap, err, btn);
  authShell(h('h1', {}, 'Sign in'), h('p', { class: 'sub' }, 'Welcome back. Log in with your email address.'),
    notice ? h('div', { class: 'ok' }, notice) : null, form,
    h('div', { class: 'row sp', style: { marginTop: '14px' } },
      h('button', { class: 'link', onClick: () => viewForgot(email.input.value) }, 'Forgot password?'),
      h('button', { class: 'link', onClick: () => viewRegister() }, 'Create account')));
  email.input.focus();
}

function view2fa(ticket) {
  const err = errBox();
  const code = field('Verification code', { class: 'otp', inputMode: 'text', autocomplete: 'one-time-code', required: true, placeholder: '000000', maxLength: 12 });
  const btn = h('button', { class: 'btn block', type: 'submit' }, 'Verify');
  authShell(h('h1', {}, 'Two-step verification'),
    h('p', { class: 'sub' }, 'Enter the 6-digit code from your authenticator app, or one of your backup codes.'),
    h('form', {
      onSubmit: async (e) => {
        e.preventDefault(); err.hidden = true;
        try { const r = await busy(btn, () => api('POST', '/auth/login/2fa', { ticket, code: code.input.value })); await enterApp(r.user); }
        catch (x) { if (x.data && x.data.restart) return viewLogin('', ''); showErr(err, x); code.input.select(); }
      },
    }, code.wrap, err, btn),
    h('div', { class: 'foot' }, h('button', { class: 'link', onClick: () => viewLogin() }, '← Back to sign in')));
  code.input.focus();
}

function viewRegister() {
  const err = errBox();
  const name = field('Your name', { required: true, maxLength: 40, autocomplete: 'name' });
  const email = field('Email address', { type: 'email', required: true, autocomplete: 'email', inputMode: 'email' });
  const pw = pwField('Password', { autocomplete: 'new-password', required: true, minLength: 8 }, 'At least 8 characters, with a letter and a number.');
  const sel = h('select', {});
  const custom = field('Your own question', { maxLength: 120, placeholder: 'e.g. What street did you grow up on?' }); custom.wrap.hidden = true;
  const ans = field('Answer', { required: true, maxLength: 100, autocomplete: 'off' }, 'Not case-sensitive. You will need this exact answer to reset your password.');
  const selWrap = h('label', { class: 'field' }, h('span', {}, 'Security question (for password recovery)'), sel);
  api('GET', '/auth/questions').then((r) => {
    sel.replaceChildren(...r.questions.map((q) => h('option', { value: q }, q)), h('option', { value: '__custom' }, 'Write my own question…'));
  }).catch(() => {});
  sel.addEventListener('change', () => { custom.wrap.hidden = sel.value !== '__custom'; if (!custom.wrap.hidden) custom.input.focus(); });
  const btn = h('button', { class: 'btn block', type: 'submit' }, 'Create account');
  const form = h('form', {
    onSubmit: async (e) => {
      e.preventDefault(); err.hidden = true;
      try {
        const r = await busy(btn, () => api('POST', '/auth/register', {
          name: name.input.value, email: email.input.value, password: pw.input.value,
          question: sel.value === '__custom' ? custom.input.value : sel.value, answer: ans.input.value,
        }));
        await enterApp(r.user);
      } catch (x) { showErr(err, x); }
    },
  }, name.wrap, email.wrap, pw.wrap, selWrap, custom.wrap, ans.wrap, err, btn);
  authShell(h('h1', {}, 'Create your account'), h('p', { class: 'sub' }, 'Sign up with your email address. It takes a minute.'), form,
    h('div', { class: 'foot' }, 'Already have an account? ', h('button', { class: 'link', onClick: () => viewLogin() }, 'Sign in')));
  name.input.focus();
}

/* forgot password: email -> security question -> (2FA) -> new password */
function viewForgot(prefill = '') {
  const err = errBox();
  const email = field('Email address', { type: 'email', required: true, value: prefill, autocomplete: 'username', inputMode: 'email' });
  const btn = h('button', { class: 'btn block', type: 'submit' }, 'Continue');
  authShell(h('h1', {}, 'Reset your password'), h('p', { class: 'sub' }, 'Enter your email and we will ask the security question you chose at sign-up.'),
    h('form', {
      onSubmit: async (e) => {
        e.preventDefault(); err.hidden = true;
        try { const r = await busy(btn, () => api('POST', '/auth/forgot/question', { email: email.input.value })); viewForgotQuestion(email.input.value, r.question); }
        catch (x) { showErr(err, x); }
      },
    }, email.wrap, err, btn),
    h('div', { class: 'foot' }, h('button', { class: 'link', onClick: () => viewLogin(email.input.value) }, '← Back to sign in')));
  email.input.focus();
}
function viewForgotQuestion(emailVal, question) {
  const err = errBox();
  const ans = field('Your answer', { required: true, autocomplete: 'off', maxLength: 100 });
  const btn = h('button', { class: 'btn block', type: 'submit' }, 'Verify answer');
  authShell(h('h1', {}, 'Security question'), h('p', { class: 'sub' }, 'Answer the question you picked when you created your account.'),
    h('div', { class: 'q-box' }, question),
    h('form', {
      onSubmit: async (e) => {
        e.preventDefault(); err.hidden = true;
        try {
          const r = await busy(btn, () => api('POST', '/auth/forgot/verify', { email: emailVal, answer: ans.input.value }));
          if (r.needs2fa) viewForgot2fa(r.ticket); else viewForgotReset(r.resetToken);
        } catch (x) { showErr(err, x); ans.input.select(); }
      },
    }, ans.wrap, err, btn),
    h('div', { class: 'foot' }, h('button', { class: 'link', onClick: () => viewForgot(emailVal) }, '← Use a different email')));
  ans.input.focus();
}
function viewForgot2fa(ticket) {
  const err = errBox();
  const code = field('Verification code', { class: 'otp', required: true, autocomplete: 'one-time-code', placeholder: '000000', maxLength: 12 });
  const btn = h('button', { class: 'btn block', type: 'submit' }, 'Verify');
  authShell(h('h1', {}, 'One more step'), h('p', { class: 'sub' }, 'Two-step verification is on for this account. Enter your authenticator code or a backup code.'),
    h('form', {
      onSubmit: async (e) => {
        e.preventDefault(); err.hidden = true;
        try { const r = await busy(btn, () => api('POST', '/auth/forgot/2fa', { ticket, code: code.input.value })); viewForgotReset(r.resetToken); }
        catch (x) { if (x.data && x.data.restart) return viewForgot(); showErr(err, x); }
      },
    }, code.wrap, err, btn));
  code.input.focus();
}
function viewForgotReset(resetToken) {
  const err = errBox();
  const p1 = pwField('New password', { autocomplete: 'new-password', required: true, minLength: 8 }, 'At least 8 characters, with a letter and a number.');
  const p2 = pwField('Confirm new password', { autocomplete: 'new-password', required: true });
  const btn = h('button', { class: 'btn block', type: 'submit' }, 'Save new password');
  authShell(h('h1', {}, 'Choose a new password'), h('p', { class: 'sub' }, 'Answer verified. You will be signed out of all devices.'),
    h('form', {
      onSubmit: async (e) => {
        e.preventDefault(); err.hidden = true;
        if (p1.input.value !== p2.input.value) return showErr(err, new Error('The two passwords do not match.'));
        try { await busy(btn, () => api('POST', '/auth/forgot/reset', { resetToken, newPassword: p1.input.value })); viewLogin('', 'Password updated. Sign in with your new password.'); }
        catch (x) { if (x.data && x.data.restart) return viewForgot(); showErr(err, x); }
      },
    }, p1.wrap, p2.wrap, err, btn));
  p1.input.focus();
}

/* =====================================================================
   MAIN APP
   ===================================================================== */
const el = {};
S.drafts = new Map();
const isMobile = () => matchMedia('(max-width:820px)').matches;
const visible = () => document.visibilityState === 'visible';
const EMOJIS = '😀 😃 😄 😁 😆 😅 😂 🤣 🙂 😉 😊 😇 🥰 😍 🤩 😘 😋 😛 😜 🤪 🤗 🤔 🤨 😐 😑 😶 🙄 😏 😣 😥 😮 😴 😌 😎 🤓 😕 😟 🙁 😢 😭 😤 😠 😡 🥺 😳 😱 😨 😰 😓 🤯 🥳 🤝 👍 👎 👏 🙌 🙏 💪 👀 👋 ✌️ 🤞 🫶 ❤️ 🧡 💛 💚 💙 💜 🖤 💔 💯 🔥 ✨ 🎉 🎂 🎁 ☕ 🍕 🍔 🍺 🌞 🌙 ⭐ 🌈 🌸 🐶 🐱 ✅ ❌ ⚠️ 📎 📷 🚀'.split(' ');

async function enterApp(user) {
  S.me = user; S.chats.clear(); S.msgs.clear(); S.more.clear(); S.active = null; S.filter = '';
  S.everConnected = false;
  buildShell();
  connectWS();
  try { const r = await api('GET', '/chats'); r.chats.forEach((c) => S.chats.set(c.id, c)); } catch (e) { toast(e.message, true); }
  renderList();
}
function sessionLost(msg = 'Your session ended. Please sign in again.') {
  if (!S.me) return;
  S.me = null; S.active = null; closeWS(); document.title = 'Chatly';
  viewLogin('', msg);
}
async function doLogout() {
  try { await api('POST', '/auth/logout'); } catch { /* ignore */ }
  S.me = null; S.active = null; closeWS(); document.title = 'Chatly'; viewLogin();
}

function buildShell() {
  el.search = h('input', { type: 'text', placeholder: 'Search chats or people', 'aria-label': 'Search chats', autocomplete: 'off', onInput: (e) => { S.filter = e.target.value.trim().toLowerCase(); renderList(); } });
  el.list = h('div', { class: 'list' });
  el.banner = h('div', { class: 'banner', hidden: true }, 'Reconnecting…');
  el.meSlot = h('div', {});
  const menuBtn = h('button', { class: 'iconbtn', 'aria-label': 'Menu', onClick: (e) => popup(e.currentTarget, [
    { icon: 'group', label: 'New group', run: openNewGroup },
    { icon: 'settings', label: 'Settings', run: () => openSettings() },
    { icon: 'logout', label: 'Log out', run: doLogout },
  ]) }, icon('more'));
  el.side = h('aside', { class: 'side' },
    h('div', { class: 'top' }, el.meSlot,
      h('div', { class: 'actions' },
        h('button', { class: 'iconbtn', 'aria-label': 'New chat', title: 'New chat', onClick: openNewChat }, icon('chat')),
        menuBtn)),
    el.banner,
    h('div', { class: 'searchbar' }, h('div', { class: 'search' }, icon('search', 20), el.search)),
    el.list);
  el.main = h('main', { class: 'main' });
  el.app = h('div', { class: 'app' }, el.side, el.main);
  root.replaceChildren(el.app);
  renderMe(); renderWelcome();
}
function renderMe() {
  const a = avatar(S.me.name, S.me.id, 40);
  a.classList.add('me'); a.title = 'Profile & settings'; a.setAttribute('role', 'button'); a.tabIndex = 0;
  a.addEventListener('click', () => openSettings());
  el.meSlot.replaceChildren(a);
}
function renderWelcome() {
  const logo = h('div', {}); logo.innerHTML = LOGO.replace('class="logo"', 'width="90" height="90"');
  el.main.replaceChildren(h('div', { class: 'welcome' }, logo, h('h2', {}, 'Chatly Web'),
    h('p', {}, 'Send and receive messages in real time. Start a chat with anyone using their email address, or create a group.'),
    h('div', { class: 'lockline' }, icon('lock', 14), encNote())));
}
const encNote = () => 'Messages are encrypted ' + (location.protocol === 'https:' ? 'in transit (TLS) and ' : '') + 'at rest (AES-256-GCM).';

/* ---------- chat helpers ---------- */
const nameOf = (c, uid) => (c.members.find((m) => m.id === uid) || {}).name || 'Someone';
function statusOf(c, m) {
  const others = c.members.filter((x) => x.id !== S.me.id);
  if (!others.length) return 'sent';
  if (others.every((x) => x.read >= m.id)) return 'read';
  if (others.every((x) => x.delivered >= m.id)) return 'delivered';
  return 'sent';
}
function previewOf(c) {
  const l = c.last;
  if (!l) return { text: c.type === 'group' ? 'Group created' : 'No messages yet' };
  if (l.kind === 'system') return { text: l.text };
  const mine = l.senderId === S.me.id;
  if (l.deleted) return { text: '🚫 ' + (mine ? 'You deleted this message' : 'This message was deleted') };
  const who = c.type === 'group' ? (mine ? 'You: ' : nameOf(c, l.senderId) + ': ') : '';
  return { text: who + l.text.replace(/\s+/g, ' '), status: mine ? statusOf(c, l) : null };
}
const chatAvatarId = (c) => (c.type === 'dm' ? c.peerId : c.id);
const sortedChats = () => [...S.chats.values()]
  .filter((c) => !(c.type === 'dm' && !c.last && c.createdBy !== S.me.id))
  .sort((a, b) => ((b.last && b.last.createdAt) || b.createdAt) - ((a.last && a.last.createdAt) || a.createdAt));

function renderList() {
  if (!el.list) return;
  const q = S.filter;
  let chats = sortedChats();
  if (q) chats = chats.filter((c) => c.name.toLowerCase().includes(q) || c.members.some((m) => m.id !== S.me.id && m.email.toLowerCase().includes(q)));
  const nodes = chats.map((c) => {
    const p = previewOf(c);
    return h('button', { class: 'item' + (S.active === c.id ? ' active' : '') + (c.unread ? ' unread' : ''), onClick: () => openChat(c.id) },
      avatar(c.name, chatAvatarId(c), 49, c.type === 'group'),
      h('div', { class: 'body' },
        h('div', { class: 'l1' }, h('span', { class: 'name' }, c.name), c.last ? h('span', { class: 'time' }, listTime(c.last.createdAt)) : null),
        h('div', { class: 'l2' },
          h('span', { class: 'prev' }, p.status ? tickIcon(p.status) : null, h('span', { class: 't' }, p.text)),
          c.unread ? h('span', { class: 'badge' }, c.unread > 99 ? '99+' : c.unread) : null)));
  });
  if (!nodes.length) {
    nodes.push(h('div', { class: 'empty-list' }, q ? 'No chats match your search.' : h('div', {},
      h('p', {}, 'No conversations yet.'),
      h('button', { class: 'btn', onClick: openNewChat }, 'Start a chat'), ' ',
      h('button', { class: 'btn ghost', onClick: openNewGroup }, 'New group'))));
  }
  el.list.replaceChildren(...nodes);
  const total = [...S.chats.values()].reduce((n, c) => n + (c.unread || 0), 0);
  document.title = (total ? `(${total}) ` : '') + 'Chatly';
}

/* ---------- open / close chat ---------- */
async function openChat(id) {
  closePopups();
  const chat = S.chats.get(id); if (!chat) return;
  if (S.active !== id) {
    if (S.active != null && el.input) S.drafts.set(S.active, el.input.value);
    S.active = id; S.replyTo = null; buildChat();
  }
  el.app.classList.add('chat-open');
  if (isMobile() && !(history.state && history.state.chat)) history.pushState({ chat: id }, '');
  renderList();
  if (!S.msgs.has(id)) {
    try { await loadMessages(id); } catch (e) { toast(e.message, true); S.msgs.set(id, []); }
  }
  if (S.active !== id) return;
  renderMessages({ bottom: true });
  markRead();
  if (!isTouch) el.input.focus();
}
function closeChat() {
  if (S.active == null) return;
  if (el.input) S.drafts.set(S.active, el.input.value);
  S.active = null; el.app.classList.remove('chat-open'); renderList();
  setTimeout(() => { if (S.active == null) { renderWelcome(); el.input = null; } }, 260);
}
function goBack() { if (history.state && history.state.chat) history.back(); else closeChat(); }
window.addEventListener('popstate', () => { if (S.active != null && !(history.state && history.state.chat)) closeChat(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && S.active != null && !$('.overlay') && !$('.popup')) goBack(); });
document.addEventListener('visibilitychange', () => { if (visible()) markRead(); });
window.addEventListener('focus', () => markRead());

function buildChat() {
  el.head = h('div', { class: 'chat-head' });
  el.msgs = h('div', { class: 'msgs', onScroll: onMsgScroll });
  el.down = h('button', { class: 'scroll-down', hidden: true, 'aria-label': 'Scroll to latest', onClick: () => { el.msgs.scrollTo({ top: el.msgs.scrollHeight, behavior: 'smooth' }); } }, icon('down'));
  el.replySlot = h('div', {}); el.emojiSlot = h('div', {});
  el.input = h('textarea', { rows: 1, placeholder: 'Type a message', maxLength: 4000, 'aria-label': 'Message', autocomplete: 'off', onInput: onType, onKeydown: onKey });
  el.sendBtn = h('button', { class: 'send', type: 'button', 'aria-label': 'Send message', onClick: send }, icon('send'));
  el.main.replaceChildren(h('div', { class: 'chat' }, el.head, el.msgs, el.down,
    h('div', { class: 'composer-wrap' }, el.replySlot, el.emojiSlot,
      h('div', { class: 'composer' },
        h('div', { class: 'box' }, h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Emoji', onClick: toggleEmoji }, icon('emoji')), el.input),
        el.sendBtn))));
  el.input.value = S.drafts.get(S.active) || ''; autosize();
  renderHead();
}

function typersFor(chatId) {
  const c = S.chats.get(chatId); if (!c) return [];
  return c.members.filter((m) => m.id !== S.me.id && S.typing.has(chatId + ':' + m.id)).map((m) => m.name);
}
function showInfo() { const c = S.chats.get(S.active); if (c) (c.type === 'group' ? openGroupInfo(c.id) : openContactInfo(c.id)); }
function renderHead() {
  const c = S.chats.get(S.active); if (!c || !el.head) return;
  const peer = c.type === 'dm' ? c.members.find((m) => m.id !== S.me.id) : null;
  const typers = typersFor(c.id);
  let status;
  if (typers.length) status = c.type === 'dm' ? 'typing…' : typers.join(', ') + ' typing…';
  else if (c.type === 'dm') status = peer ? lastSeenText(peer) : '';
  else status = c.members.map((m) => (m.id === S.me.id ? 'You' : m.name)).join(', ');
  el.head.replaceChildren(
    h('button', { class: 'iconbtn back', 'aria-label': 'Back', onClick: goBack }, icon('back')),
    h('div', { class: 'who', onClick: showInfo }, avatar(c.name, chatAvatarId(c), 40, c.type === 'group'),
      h('div', { style: { minWidth: '0' } }, h('div', { class: 't1' }, c.name), h('div', { class: 't2' + (typers.length ? ' typing' : '') }, status))),
    h('button', { class: 'iconbtn', 'aria-label': 'Chat info', onClick: showInfo }, icon('info')));
}

/* ---------- messages ---------- */
async function loadMessages(id) {
  const r = await api('GET', `/chats/${id}/messages?limit=40`);
  S.msgs.set(id, r.messages); S.more.set(id, r.hasMore);
}
async function loadOlder() {
  const id = S.active, list = S.msgs.get(id);
  if (S.loadingOlder || !list || !list.length || !S.more.get(id)) return;
  S.loadingOlder = true;
  try {
    const r = await api('GET', `/chats/${id}/messages?limit=40&before=${list[0].id}`);
    S.msgs.set(id, [...r.messages, ...list]); S.more.set(id, r.hasMore);
    if (S.active === id) renderMessages({ keepFrom: true });
  } catch (e) { toast(e.message, true); } finally { S.loadingOlder = false; }
}
function onMsgScroll() {
  const b = el.msgs, far = b.scrollHeight - b.scrollTop - b.clientHeight > 300;
  el.down.hidden = !far;
  if (b.scrollTop < 80) loadOlder();
}
function renderMessages({ bottom = false, keepFrom = false } = {}) {
  if (!el.msgs || S.active == null) return;
  const c = S.chats.get(S.active); if (!c) return;
  const list = S.msgs.get(S.active) || [], box = el.msgs;
  const prevH = box.scrollHeight, prevTop = box.scrollTop, near = prevH - prevTop - box.clientHeight < 140;
  const frag = document.createDocumentFragment();
  if (S.more.get(S.active)) frag.append(h('div', { class: 'older' }, h('button', { class: 'btn ghost small', onClick: loadOlder }, 'Load earlier messages')));
  else frag.append(h('div', { class: 'enc-note' }, '🔒 ' + encNote()));
  let prev = null;
  for (const m of list) {
    if (!prev || !sameDay(prev.createdAt, m.createdAt)) frag.append(h('div', { class: 'day' }, h('span', {}, dayLabel(m.createdAt))));
    if (m.kind === 'system') { frag.append(h('div', { class: 'sys' }, h('span', {}, m.text))); prev = m; continue; }
    const first = !prev || prev.kind === 'system' || prev.senderId !== m.senderId || !sameDay(prev.createdAt, m.createdAt) || m.createdAt - prev.createdAt > 5 * 60e3;
    frag.append(msgNode(c, m, first)); prev = m;
  }
  box.replaceChildren(frag);
  if (bottom) box.scrollTop = box.scrollHeight;
  else if (keepFrom) box.scrollTop = box.scrollHeight - prevH + prevTop;
  else if (near) box.scrollTop = box.scrollHeight;
  else box.scrollTop = prevTop;
  onMsgScroll();
}
function msgNode(c, m, first) {
  const out = m.senderId === S.me.id;
  const bubble = h('div', { class: 'bubble' + (m.deleted ? ' deleted' : '') });
  if (!out && c.type === 'group' && first) bubble.append(h('div', { class: 'sender', style: { color: colorFor(m.senderId) } }, nameOf(c, m.senderId)));
  if (m.replyTo && !m.deleted) {
    bubble.append(h('div', { class: 'quote', onClick: () => jumpTo(m.replyTo.id) },
      h('b', {}, m.replyTo.senderId === S.me.id ? 'You' : nameOf(c, m.replyTo.senderId)),
      h('span', {}, m.replyTo.text == null ? '🚫 This message was deleted' : m.replyTo.text)));
  }
  const meta = h('span', { class: 'meta' }, fmtTime(m.createdAt), out && !m.deleted ? tickIcon(statusOf(c, m)) : null);
  bubble.append(h('div', { class: 'text' }, m.deleted ? ('🚫 ' + (out ? 'You deleted this message' : 'This message was deleted')) : linkify(m.text), meta));
  if (!m.deleted) {
    bubble.append(h('button', { class: 'menu-btn', 'aria-label': 'Message options', onClick: (e) => popup(e.currentTarget, [
      { icon: 'reply', label: 'Reply', run: () => setReply(m) },
      { icon: 'copy', label: 'Copy', run: () => navigator.clipboard && navigator.clipboard.writeText(m.text).then(() => toast('Copied')) },
      out ? { icon: 'trash', label: 'Delete for everyone', danger: true, run: () => deleteMsg(m) } : null,
    ], out ? 'right' : 'left') }, icon('down', 18)));
  }
  return h('div', { class: 'msg ' + (out ? 'out' : 'in') + (first ? ' first' : ''), id: 'm' + m.id }, bubble);
}
function jumpTo(id) {
  const n = document.getElementById('m' + id); if (!n) return toast('Original message is further up. Scroll up to load it.');
  n.scrollIntoView({ block: 'center', behavior: 'smooth' }); n.classList.remove('flash'); void n.offsetWidth; n.classList.add('flash');
}
async function deleteMsg(m) {
  if (!confirm('Delete this message for everyone?')) return;
  try { await api('DELETE', `/chats/${m.chatId}/messages/${m.id}`); } catch (e) { toast(e.message, true); }
}
function setReply(m) {
  S.replyTo = m;
  const c = S.chats.get(S.active);
  el.replySlot.replaceChildren(h('div', { class: 'replybar' },
    h('div', { class: 'quote' }, h('b', {}, m.senderId === S.me.id ? 'You' : nameOf(c, m.senderId)), h('span', {}, m.text)),
    h('button', { class: 'iconbtn', 'aria-label': 'Cancel reply', onClick: clearReply }, icon('close'))));
  el.input.focus();
}
function clearReply() { S.replyTo = null; if (el.replySlot) el.replySlot.replaceChildren(); }

/* ---------- composer ---------- */
let lastTypingSent = 0, typingTimer = null;
function autosize() { el.input.style.height = 'auto'; el.input.style.height = Math.min(el.input.scrollHeight, 120) + 'px'; }
function onType() {
  autosize();
  if (!el.input.value.trim()) return stopTyping();
  const now = Date.now();
  if (now - lastTypingSent > 2500) { lastTypingSent = now; wsSend({ t: 'typing', chatId: S.active, typing: true }); }
  clearTimeout(typingTimer); typingTimer = setTimeout(stopTyping, 3000);
}
function stopTyping() { clearTimeout(typingTimer); if (lastTypingSent) { lastTypingSent = 0; wsSend({ t: 'typing', chatId: S.active, typing: false }); } }
function onKey(e) { if (e.key === 'Enter' && !e.shiftKey && !isTouch) { e.preventDefault(); send(); } }
function toggleEmoji() {
  if (el.emojiSlot.firstChild) return closeEmoji();
  el.emojiSlot.replaceChildren(h('div', { class: 'emoji-panel' }, EMOJIS.map((em) => h('button', { type: 'button', onClick: () => {
    const i = el.input, s = i.selectionStart ?? i.value.length, e2 = i.selectionEnd ?? s;
    i.value = i.value.slice(0, s) + em + i.value.slice(e2); i.selectionStart = i.selectionEnd = s + em.length; autosize(); onType();
  } }, em))));
}
function closeEmoji() { if (el.emojiSlot) el.emojiSlot.replaceChildren(); }
async function send() {
  const text = el.input.value.trim(); if (!text || S.active == null) return;
  const id = S.active, replyTo = S.replyTo ? S.replyTo.id : null;
  el.input.value = ''; autosize(); clearReply(); stopTyping(); S.drafts.delete(id); closeEmoji();
  try {
    const r = await api('POST', `/chats/${id}/messages`, { text, replyTo });
    ingestMessage(r.message);
  } catch (e) { toast(e.message, true); if (S.active === id && !el.input.value) { el.input.value = text; autosize(); } }
  if (!isTouch && el.input) el.input.focus();
}

/* ---------- incoming data ---------- */
async function fetchChat(id) {
  try { const r = await api('GET', '/chats/' + id); S.chats.set(id, r.chat); renderList(); if (S.active === id) { renderHead(); } } catch { /* ignore */ }
}
function ingestMessage(m) {
  const c = S.chats.get(m.chatId);
  if (!c) { fetchChat(m.chatId); return; }
  const list = S.msgs.get(m.chatId);
  if (list && !list.some((x) => x.id === m.id)) list.push(m);
  const isNew = !c.last || m.id > c.last.id;
  if (isNew) c.last = m;
  const mine = m.senderId === S.me.id;
  if (isNew && m.kind === 'text' && !mine && !(S.active === c.id && visible())) c.unread = (c.unread || 0) + 1;
  if (!mine && m.senderId) { clearTimeout(S.typing.get(c.id + ':' + m.senderId)); S.typing.delete(c.id + ':' + m.senderId); }
  renderList();
  if (S.active === c.id) { renderHead(); renderMessages({ bottom: mine }); markRead(); }
}
function markRead() {
  const c = S.chats.get(S.active); if (!c || !visible()) return;
  const list = S.msgs.get(c.id) || [];
  const lastId = Math.max((c.last && c.last.id) || 0, list.length ? list[list.length - 1].id : 0);
  const me = c.members.find((m) => m.id === S.me.id);
  if (lastId && me && me.read < lastId) { wsSend({ t: 'read', chatId: c.id, upTo: lastId }); me.read = lastId; }
  if (c.unread) { c.unread = 0; renderList(); }
}
async function resync() {
  try {
    const r = await api('GET', '/chats');
    S.chats.clear(); r.chats.forEach((c) => S.chats.set(c.id, c));
    for (const id of [...S.msgs.keys()]) if (id !== S.active) S.msgs.delete(id);
    if (S.active != null) {
      if (!S.chats.has(S.active)) return closeChat();
      await loadMessages(S.active); renderHead(); renderMessages({ bottom: true }); markRead();
    }
    renderList();
  } catch { /* ignore */ }
}
function onEvent(t, d) {
  switch (t) {
    case 'ready': if (S.everConnected) resync(); S.everConnected = true; break;
    case 'message': ingestMessage(d); break;
    case 'message_deleted': {
      const c = S.chats.get(d.chatId); if (!c) break;
      const apply = (m) => { if (m && m.id === d.id) { m.deleted = true; m.text = null; } };
      apply(c.last); (S.msgs.get(d.chatId) || []).forEach((m) => { apply(m); if (m.replyTo && m.replyTo.id === d.id) m.replyTo.text = null; });
      renderList(); if (S.active === c.id) renderMessages(); break;
    }
    case 'receipt': {
      const c = S.chats.get(d.chatId); if (!c) break;
      const m = c.members.find((x) => x.id === d.userId);
      if (m) { m.delivered = Math.max(m.delivered, d.delivered); m.read = Math.max(m.read, d.read); }
      if (d.userId === S.me.id && c.last && d.read >= c.last.id) c.unread = 0;
      renderList(); if (S.active === c.id) renderMessages(); break;
    }
    case 'typing': {
      const key = d.chatId + ':' + d.userId; clearTimeout(S.typing.get(key));
      if (d.typing) S.typing.set(key, setTimeout(() => { S.typing.delete(key); if (S.active === d.chatId) renderHead(); }, 5000)); else S.typing.delete(key);
      if (S.active === d.chatId) renderHead(); break;
    }
    case 'presence':
      S.chats.forEach((c) => c.members.forEach((m) => { if (m.id === d.userId) { m.online = d.online; m.lastSeen = d.lastSeen; } }));
      renderHead(); break;
    case 'profile':
      S.chats.forEach((c) => { c.members.forEach((m) => { if (m.id === d.id) { m.name = d.name; m.about = d.about; } }); if (c.type === 'dm' && c.peerId === d.id) c.name = d.name; });
      if (d.id === S.me.id) { S.me.name = d.name; S.me.about = d.about; renderMe(); }
      renderList(); renderHead(); if (S.active != null) renderMessages(); break;
    case 'chat': {
      const wasActive = S.active === d.id; if (wasActive) d.unread = 0;
      S.chats.set(d.id, d); renderList();
      if (wasActive) { renderHead(); renderMessages(); markRead(); }
      break;
    }
    case 'chat_removed':
      S.chats.delete(d.chatId); S.msgs.delete(d.chatId);
      if (S.active === d.chatId) { closeChat(); toast('You are no longer in that chat.'); }
      renderList(); break;
  }
  if (S.infoRender && ['chat', 'profile', 'presence', 'chat_removed'].includes(t)) S.infoRender.fn();
}

/* ---------- WebSocket ---------- */
let pingTimer = null, retryTimer = null;
function connectWS() {
  if (S.ws || !S.me) return;
  const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  S.ws = ws;
  ws.onopen = () => { S.wsTries = 0; el.banner && (el.banner.hidden = true); pingTimer = setInterval(() => wsSend({ t: 'ping' }), 25000); };
  ws.onmessage = (e) => { try { const m = JSON.parse(e.data); onEvent(m.t, m.d); } catch (x) { console.error(x); } };
  ws.onclose = async () => {
    clearInterval(pingTimer); S.ws = null; if (!S.me) return;
    el.banner && (el.banner.hidden = false);
    try { await api('GET', '/me'); } catch (e) { if (e.status === 401) return; }   // 401 -> sessionLost() already ran
    if (!S.me) return;
    retryTimer = setTimeout(connectWS, Math.min(1000 * 2 ** S.wsTries++, 15000));
  };
  ws.onerror = () => ws.close();
}
function closeWS() { clearTimeout(retryTimer); clearInterval(pingTimer); const w = S.ws; S.ws = null; if (w) { w.onclose = null; w.close(); } }
function wsSend(o) { if (S.ws && S.ws.readyState === 1) S.ws.send(JSON.stringify(o)); }
window.addEventListener('online', () => { if (S.me && !S.ws) connectWS(); });

/* =====================================================================
   DIALOGS: new chat, groups, contact info
   ===================================================================== */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const muted = { color: 'var(--ink-2)' };

function openNewChat() {
  const err = errBox();
  const email = field('Their email address', { type: 'email', required: true, inputMode: 'email', autocomplete: 'off', placeholder: 'friend@example.com' });
  const btn = h('button', { class: 'btn block', type: 'submit' }, 'Start chat');
  const m = openModal('New chat', h('form', {
    onSubmit: async (e) => {
      e.preventDefault(); err.hidden = true;
      try {
        const r = await busy(btn, () => api('POST', '/chats/dm', { email: email.input.value }));
        S.chats.set(r.chat.id, r.chat); m.close(); openChat(r.chat.id);
      } catch (x) { showErr(err, x); }
    },
  }, h('p', { style: { ...muted, marginTop: 0 } }, 'Enter the email address they used to sign up for Chatly.'), email.wrap, err, btn));
  email.input.focus();
}

function openNewGroup() {
  const err = errBox();
  const name = field('Group name', { maxLength: 60, required: true, autocomplete: 'off' });
  const desc = field('Description (optional)', { maxLength: 200, autocomplete: 'off' });
  const extra = new Set(), chips = h('div', { class: 'chips' });
  const contacts = sortedChats().filter((c) => c.type === 'dm').map((c) => c.members.find((x) => x.id !== S.me.id)).filter(Boolean);
  const boxes = contacts.map((p) => ({ p, box: h('input', { type: 'checkbox' }) }));
  const pick = contacts.length ? h('div', { class: 'pick' }, boxes.map(({ p, box }) =>
    h('label', {}, box, avatar(p.name, p.id, 34), h('div', {}, h('div', {}, p.name), h('small', { style: muted }, p.email))))) : null;
  const em = h('input', { class: 'input', type: 'email', placeholder: 'Add someone by email address', autocomplete: 'off', inputMode: 'email',
    onKeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); addEmail(); } } });
  function renderChips() { chips.replaceChildren(...[...extra].map((e) => h('span', { class: 'chip' }, e, h('button', { type: 'button', 'aria-label': 'Remove', onClick: () => { extra.delete(e); renderChips(); } }, '×')))); }
  function addEmail() {
    const v = em.value.trim().toLowerCase(); if (!v) return;
    if (!EMAIL_RE.test(v)) return showErr(err, new Error('Enter a valid email address.'));
    if (v === S.me.email) return showErr(err, new Error("You're already in the group."));
    err.hidden = true; extra.add(v); em.value = ''; renderChips();
  }
  const btn = h('button', { class: 'btn block', type: 'submit' }, 'Create group');
  const m = openModal('New group', h('form', {
    onSubmit: async (e) => {
      e.preventDefault(); err.hidden = true; addEmail();
      const emails = [...boxes.filter((b) => b.box.checked).map((b) => b.p.email), ...extra];
      if (!emails.length) return showErr(err, new Error('Add at least one person to the group.'));
      try {
        const r = await busy(btn, () => api('POST', '/chats/group', { name: name.input.value, description: desc.input.value, emails }));
        S.chats.set(r.chat.id, r.chat); m.close(); openChat(r.chat.id);
        if (r.notFound && r.notFound.length) toast('No account found for: ' + r.notFound.join(', '), true);
      } catch (x) { showErr(err, x.data && x.data.notFound && x.data.notFound.length ? new Error(x.message + ' Not found: ' + x.data.notFound.join(', ')) : x); }
    },
  }, name.wrap, desc.wrap,
  h('div', { class: 'field' }, h('span', {}, 'Members')),
  pick, chips, h('div', { class: 'row', style: { marginBottom: '14px' } }, em, h('button', { class: 'btn ghost small', type: 'button', onClick: addEmail }, 'Add')),
  err, btn));
  name.input.focus();
}

function openContactInfo(chatId) {
  const c = S.chats.get(chatId); if (!c) return;
  const render = () => {
    const c2 = S.chats.get(chatId); if (!c2) return m.close();
    const p = c2.members.find((x) => x.id !== S.me.id);
    m.setBody(h('div', { class: 'center' }, h('div', { style: { display: 'flex', justifyContent: 'center', marginBottom: '12px' } }, avatar(c2.name, chatAvatarId(c2), 96)),
      h('h2', { style: { margin: '0 0 2px', fontWeight: 500 } }, c2.name),
      p ? h('div', { style: muted }, p.email) : null, p ? h('div', { style: { ...muted, marginTop: '4px' } }, lastSeenText(p)) : null,
      h('div', { class: 'section', style: { marginTop: '18px', textAlign: 'left' } }, h('h4', {}, 'About'), h('p', { style: { margin: 0 } }, p ? p.about : '')),
      h('div', { style: { ...muted, fontSize: '13px', display: 'flex', gap: '6px', justifyContent: 'center', alignItems: 'center' } }, icon('lock', 14), encNote())));
  };
  const m = openModal('Contact info', '', { onClose: () => { S.infoRender = null; } });
  S.infoRender = { id: chatId, fn: render }; render();
}

function openGroupInfo(chatId) {
  const m = openModal('Group info', '', { wide: true, onClose: () => { S.infoRender = null; } });
  const render = () => {
    const c = S.chats.get(chatId); if (!c) return m.close();
    const admin = c.myRole === 'admin', err = errBox();
    const adopt = (r) => { if (r && r.chat) { S.chats.set(r.chat.id, r.chat); renderList(); renderHead(); } };
    const nameIn = h('input', { class: 'input', value: c.name, maxLength: 60, disabled: !admin, 'aria-label': 'Group name' });
    const descIn = h('textarea', { class: 'input', rows: 2, maxLength: 200, disabled: !admin, placeholder: admin ? 'Add a group description' : 'No description', 'aria-label': 'Group description' });
    descIn.value = c.description || '';
    const saveBtn = h('button', { class: 'btn small', type: 'button', onClick: async () => {
      err.hidden = true;
      try { adopt(await busy(saveBtn, () => api('PATCH', `/chats/${c.id}`, { name: nameIn.value, description: descIn.value }))); toast('Group updated'); } catch (x) { showErr(err, x); }
    } }, 'Save');
    const addIn = h('input', { class: 'input', type: 'email', placeholder: 'Add people by email (comma separated)', autocomplete: 'off', 'aria-label': 'Add members by email' });
    const addBtn = h('button', { class: 'btn small', type: 'button', onClick: async () => {
      err.hidden = true;
      const emails = addIn.value.split(/[,\s;]+/).map((x) => x.trim()).filter(Boolean);
      if (!emails.length) return;
      try {
        const r = await busy(addBtn, () => api('POST', `/chats/${c.id}/members`, { emails })); adopt(r); addIn.value = '';
        if (r.notFound && r.notFound.length) toast('No account found for: ' + r.notFound.join(', '), true);
      } catch (x) { showErr(err, x.data && x.data.notFound && x.data.notFound.length ? new Error(x.message + ' Not found: ' + x.data.notFound.join(', ')) : x); }
    } }, 'Add');
    const rows = c.members.map((p) => {
      const you = p.id === S.me.id;
      return h('div', { class: 'member' }, avatar(p.name, p.id, 40),
        h('div', { class: 'info' }, h('b', {}, p.name + (you ? ' (You)' : '')), h('small', {}, p.email)),
        p.role === 'admin' ? h('span', { class: 'tag' }, 'Admin') : null,
        admin && !you ? h('button', { class: 'btn ghost small', type: 'button', onClick: async () => {
          try { adopt(await api('POST', `/chats/${c.id}/members/${p.id}/role`, { role: p.role === 'admin' ? 'member' : 'admin' })); } catch (x) { toast(x.message, true); }
        } }, p.role === 'admin' ? 'Dismiss admin' : 'Make admin') : null,
        admin && !you ? h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Remove ' + p.name, title: 'Remove from group', onClick: async () => {
          if (!confirm(`Remove ${p.name} from the group?`)) return;
          try { await api('DELETE', `/chats/${c.id}/members/${p.id}`); } catch (x) { toast(x.message, true); }
        } }, icon('close', 20)) : null);
    });
    m.setBody(
      h('div', { class: 'center', style: { marginBottom: '16px' } }, h('div', { style: { display: 'flex', justifyContent: 'center', marginBottom: '8px' } }, avatar(c.name, c.id, 88, true)),
        h('div', { style: muted }, `Group · ${c.members.length} member${c.members.length === 1 ? '' : 's'}`)),
      h('label', { class: 'field' }, h('span', {}, 'Name'), nameIn), h('label', { class: 'field' }, h('span', {}, 'Description'), descIn),
      admin ? h('div', { style: { marginBottom: '16px' } }, saveBtn) : null, err,
      h('div', { class: 'section' }, h('h4', {}, 'Members'), rows),
      admin ? h('div', { class: 'section' }, h('h4', {}, 'Add people'), h('p', {}, 'They must already have a Chatly account. They will not see earlier messages.'), h('div', { class: 'row' }, addIn, addBtn)) : null,
      h('button', { class: 'btn danger block', type: 'button', onClick: async () => {
        if (!confirm('Leave this group?')) return;
        try { await api('DELETE', `/chats/${c.id}/members/${S.me.id}`); m.close(); } catch (x) { toast(x.message, true); }
      } }, 'Leave group'));
  };
  S.infoRender = { id: chatId, fn: render }; render();
}

/* =====================================================================
   SETTINGS: profile, appearance, password, security question, 2FA, devices, delete
   ===================================================================== */
async function getQuestions() { if (!S.questions) S.questions = (await api('GET', '/auth/questions')).questions; return S.questions; }
function section(title, desc, ...body) { return h('div', { class: 'section' }, h('h4', {}, title), desc ? h('p', {}, desc) : null, body); }
function uaName(ua = '') {
  const b = /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
  const o = /iPhone|iPad/.test(ua) ? 'iOS' : /Android/.test(ua) ? 'Android' : /Mac OS X/.test(ua) ? 'macOS' : /Windows/.test(ua) ? 'Windows' : /Linux/.test(ua) ? 'Linux' : '';
  return b + (o ? ' on ' + o : '');
}

function openSettings() {
  const m = openModal('Settings', '', { wide: true });
  const render = () => m.setBody(profileSection(), appearanceSection(), passwordSection(), questionSection(), twoFactorSection(render), devicesSection(), dangerSection(m));
  render();
}

function profileSection() {
  const err = errBox();
  const name = field('Name', { value: S.me.name, maxLength: 40, required: true });
  const about = field('About', { value: S.me.about, maxLength: 140 });
  const btn = h('button', { class: 'btn small', type: 'submit' }, 'Save profile');
  return section('Profile', null,
    h('div', { class: 'row', style: { marginBottom: '12px' } }, avatar(S.me.name, S.me.id, 56), h('div', {}, h('b', {}, S.me.email), h('div', { style: { ...muted, fontSize: '13px' } }, 'Your sign-in email'))),
    h('form', {
      onSubmit: async (e) => {
        e.preventDefault(); err.hidden = true;
        try { const r = await busy(btn, () => api('PATCH', '/me', { name: name.input.value, about: about.input.value })); Object.assign(S.me, r.user); renderMe(); toast('Profile saved'); } catch (x) { showErr(err, x); }
      },
    }, name.wrap, about.wrap, err, btn));
}

function appearanceSection() {
  const sel = h('select', { 'aria-label': 'Theme', onChange: () => { localStorage.setItem('theme', sel.value); applyTheme(); } },
    ['auto', 'Match my device'], ['light', 'Light'], ['dark', 'Dark']);
  sel.replaceChildren(...[['auto', 'Match my device'], ['light', 'Light'], ['dark', 'Dark']].map(([v, l]) => h('option', { value: v }, l)));
  sel.value = localStorage.getItem('theme') || 'auto';
  return section('Appearance', null, h('label', { class: 'field', style: { marginBottom: 0 } }, h('span', {}, 'Theme'), sel));
}

function passwordSection() {
  const err = errBox(), ok = h('div', { class: 'ok', hidden: true });
  const cur = pwField('Current password', { autocomplete: 'current-password', required: true });
  const p1 = pwField('New password', { autocomplete: 'new-password', required: true, minLength: 8 }, 'At least 8 characters, with a letter and a number.');
  const p2 = pwField('Confirm new password', { autocomplete: 'new-password', required: true });
  const btn = h('button', { class: 'btn small', type: 'submit' }, 'Change password');
  return section('Change password', 'You will stay signed in here; other devices will be signed out.',
    h('form', {
      onSubmit: async (e) => {
        e.preventDefault(); err.hidden = true; ok.hidden = true;
        if (p1.input.value !== p2.input.value) return showErr(err, new Error('The two new passwords do not match.'));
        try {
          await busy(btn, () => api('POST', '/account/password', { current: cur.input.value, new: p1.input.value }));
          cur.input.value = p1.input.value = p2.input.value = ''; ok.textContent = 'Password changed.'; ok.hidden = false;
        } catch (x) { showErr(err, x); }
      },
    }, cur.wrap, p1.wrap, p2.wrap, err, ok, btn));
}

function questionSection() {
  const err = errBox(), ok = h('div', { class: 'ok', hidden: true });
  const pw = pwField('Current password', { required: true });
  const sel = h('select', {}), custom = field('Your own question', { maxLength: 120 }); custom.wrap.hidden = true;
  const ans = field('New answer', { required: true, maxLength: 100, autocomplete: 'off' });
  getQuestions().then((qs) => { sel.replaceChildren(...qs.map((q) => h('option', { value: q }, q)), h('option', { value: '__custom' }, 'Write my own question…')); if (qs.includes(S.me.securityQuestion)) sel.value = S.me.securityQuestion; }).catch(() => {});
  sel.addEventListener('change', () => { custom.wrap.hidden = sel.value !== '__custom'; });
  const btn = h('button', { class: 'btn small', type: 'submit' }, 'Update question');
  return section('Security question', 'Used to reset your password if you forget it.',
    h('div', { class: 'q-box' }, S.me.securityQuestion),
    h('form', {
      onSubmit: async (e) => {
        e.preventDefault(); err.hidden = true; ok.hidden = true;
        try {
          const r = await busy(btn, () => api('POST', '/account/security-question', { password: pw.input.value, question: sel.value === '__custom' ? custom.input.value : sel.value, answer: ans.input.value }));
          S.me.securityQuestion = r.user.securityQuestion; pw.input.value = ans.input.value = ''; ok.textContent = 'Security question updated.'; ok.hidden = false;
          const qb = btn.closest('.section').querySelector('.q-box'); if (qb) qb.textContent = S.me.securityQuestion;
        } catch (x) { showErr(err, x); }
      },
    }, pw.wrap, h('label', { class: 'field' }, h('span', {}, 'New question'), sel), custom.wrap, ans.wrap, err, ok, btn));
}

function twoFactorSection(rerender) {
  const box = h('div', {});
  const sec = section('Two-step verification (2FA)', 'Add a second layer of protection: a 6-digit code from an authenticator app such as Google Authenticator, Authy or 1Password.', box);
  const showOff = () => {
    const err = errBox(), btn = h('button', { class: 'btn small', type: 'button' }, 'Set up 2FA');
    btn.addEventListener('click', async () => {
      err.hidden = true;
      try { showSetup(await busy(btn, () => api('POST', '/account/2fa/setup'))); } catch (x) { showErr(err, x); }
    });
    box.replaceChildren(err, btn);
  };
  const showSetup = (s) => {
    const err = errBox();
    const code = field('Enter the 6-digit code from the app', { class: 'otp', inputMode: 'numeric', autocomplete: 'one-time-code', required: true, maxLength: 7, placeholder: '000000' });
    const btn = h('button', { class: 'btn small', type: 'submit' }, 'Turn on');
    box.replaceChildren(
      h('p', {}, '1. Scan this QR code with your authenticator app (or type the key in manually).'),
      h('img', { class: 'qr', src: s.qr, alt: 'QR code for your authenticator app' }),
      h('div', { class: 'secret' }, s.secret),
      h('p', {}, '2. Enter the code the app shows to confirm.'),
      h('form', {
        onSubmit: async (e) => {
          e.preventDefault(); err.hidden = true;
          try { const r = await busy(btn, () => api('POST', '/account/2fa/enable', { code: code.input.value })); S.me.twoFactor = true; showCodes(r.backupCodes); } catch (x) { showErr(err, x); }
        },
      }, code.wrap, err, h('div', { class: 'row' }, btn, h('button', { class: 'btn ghost small', type: 'button', onClick: showOff }, 'Cancel'))));
    code.input.focus();
  };
  const showCodes = (codes) => {
    const text = 'Chatly backup codes for ' + S.me.email + '\nEach code works once.\n\n' + codes.join('\n') + '\n';
    box.replaceChildren(h('div', { class: 'ok' }, 'Two-step verification is now ON.'),
      h('p', {}, 'Save these backup codes somewhere safe. Each one can be used once if you lose access to your authenticator app. They will not be shown again.'),
      h('div', { class: 'codes' }, codes.map((c) => h('code', {}, c))),
      h('div', { class: 'row' },
        h('button', { class: 'btn ghost small', type: 'button', onClick: () => navigator.clipboard && navigator.clipboard.writeText(text).then(() => toast('Copied')) }, 'Copy'),
        h('button', { class: 'btn ghost small', type: 'button', onClick: () => {
          const a = h('a', { href: URL.createObjectURL(new Blob([text], { type: 'text/plain' })), download: 'chatly-backup-codes.txt' }); document.body.append(a); a.click(); a.remove();
        } }, 'Download'),
        h('button', { class: 'btn small', type: 'button', onClick: rerender }, 'Done')));
  };
  const showOn = () => {
    const err = errBox(), pw = pwField('Password', { required: true }), code = field('Authenticator or backup code', { required: true, autocomplete: 'one-time-code', maxLength: 12 });
    const btn = h('button', { class: 'btn danger small', type: 'submit' }, 'Turn off 2FA');
    box.replaceChildren(h('div', { class: 'ok' }, '✓ Two-step verification is ON.'),
      h('form', {
        onSubmit: async (e) => {
          e.preventDefault(); err.hidden = true;
          try { await busy(btn, () => api('POST', '/account/2fa/disable', { password: pw.input.value, code: code.input.value })); S.me.twoFactor = false; toast('Two-step verification turned off'); showOff(); } catch (x) { showErr(err, x); }
        },
      }, pw.wrap, code.wrap, err, btn));
  };
  if (S.me.twoFactor) showOn(); else showOff();
  return sec;
}

function devicesSection() {
  const list = h('div', {}, h('small', { style: muted }, 'Loading…'));
  const btn = h('button', { class: 'btn ghost small', type: 'button', hidden: true, onClick: async () => {
    try { await api('POST', '/account/sessions/revoke-others'); toast('Signed out of other devices'); load(); } catch (x) { toast(x.message, true); }
  } }, 'Sign out all other devices');
  async function load() {
    try {
      const r = await api('GET', '/account/sessions');
      list.replaceChildren(...r.sessions.map((s) => h('div', { class: 'sess' }, h('div', {}, h('b', {}, uaName(s.userAgent)), h('small', {}, `Signed in ${new Date(s.createdAt).toLocaleString()}`)), s.current ? h('span', { class: 'tag' }, 'This device') : null)));
      btn.hidden = r.sessions.length < 2;
    } catch (x) { list.textContent = x.message; }
  }
  load();
  return section('Devices', 'Where your account is currently signed in.', list, h('div', { style: { marginTop: '10px' } }, btn));
}

function dangerSection(settingsModal) {
  return h('div', { class: 'section danger-zone' }, h('h4', {}, 'Delete account'),
    h('p', {}, 'Permanently deletes your account, your messages and your one-to-one chats. Groups you are in continue without you. This cannot be undone.'),
    h('button', { class: 'btn danger small', type: 'button', onClick: () => openDeleteAccount(settingsModal) }, 'Delete my account…'));
}
function openDeleteAccount(settingsModal) {
  const err = errBox();
  const pw = pwField('Your password', { required: true });
  const code = S.me.twoFactor ? field('Authenticator or backup code', { required: true, autocomplete: 'one-time-code', maxLength: 12 }) : null;
  const confirmIn = field('Type DELETE to confirm', { required: true, autocomplete: 'off', placeholder: 'DELETE' });
  const btn = h('button', { class: 'btn danger block', type: 'submit' }, 'Permanently delete account');
  const m = openModal('Delete account', h('form', {
    onSubmit: async (e) => {
      e.preventDefault(); err.hidden = true;
      try {
        await busy(btn, () => api('POST', '/account/delete', { password: pw.input.value, code: code ? code.input.value : '', confirm: confirmIn.input.value }));
        m.close(); settingsModal.close(); S.me = null; S.active = null; closeWS(); document.title = 'Chatly';
        viewLogin('', 'Your account has been deleted.');
      } catch (x) { showErr(err, x); }
    },
  }, h('p', { style: { marginTop: 0, color: 'var(--danger)' } }, 'This will permanently erase your account and messages. Everyone you chat with will lose the conversation.'),
  pw.wrap, code && code.wrap, confirmIn.wrap, err, btn));
  pw.input.focus();
}

/* ---------- boot ---------- */
(async function boot() {
  root.replaceChildren(h('div', { class: 'loading' }, 'Loading…'));
  try { const r = await api('GET', '/me'); await enterApp(r.user); }
  catch (e) { viewLogin(); if (e.status === 0) toast(e.message, true); }
})();
