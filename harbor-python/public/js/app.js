/* Harbor — front end. Plain JavaScript, no build step. */
(function () {
  'use strict';

  // ====================================================================
  // Helpers
  // ====================================================================
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ic = (name, cls = '') => `<svg class="ic ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const coarse = matchMedia('(pointer: coarse)').matches;

  const LOGO = '<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="var(--accent)"/><path d="M6 14c3-3 6-3 10 0s7 3 10 0M6 21c3-3 6-3 10 0s7 3 10 0" fill="none" stroke="var(--accent-ink)" stroke-width="2.4" stroke-linecap="round"/></svg>';

  function fmtSize(n) {
    if (n < 1024) return `${n} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let i = -1;
    do { n /= 1024; i++; } while (n >= 1024 && i < units.length - 1);
    return `${n < 10 ? n.toFixed(1) : Math.round(n)} ${units[i]}`;
  }
  function fmtDate(ts) {
    const d = new Date(ts);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    const sameYear = d.getFullYear() === now.getFullYear();
    return d.toLocaleDateString([], sameYear ? { month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' });
  }

  const ext = (name) => (name.includes('.') ? name.split('.').pop().toLowerCase() : '');
  const CODE_EXT = new Set(['js', 'mjs', 'ts', 'tsx', 'jsx', 'py', 'rb', 'go', 'rs', 'java', 'c', 'h', 'cpp', 'cs', 'php', 'sh', 'sql', 'swift', 'kt', 'html', 'css', 'json', 'xml', 'yml', 'yaml', 'toml']);
  const TEXT_EXT = new Set(['txt', 'md', 'log', 'csv', 'ini', 'env']);

  /** Visual category — picks the icon and colour. */
  function category(it) {
    if (it.kind === 'folder') return 'folder';
    const m = it.mime || '';
    const e = ext(it.name);
    if (m.startsWith('image/')) return 'image';
    if (m.startsWith('video/')) return 'video';
    if (m.startsWith('audio/')) return 'audio';
    if (m === 'application/pdf' || e === 'pdf') return 'pdf';
    if (['doc', 'docx', 'odt', 'rtf', 'pages'].includes(e)) return 'doc';
    if (['xls', 'xlsx', 'ods', 'numbers'].includes(e) || e === 'csv') return 'sheet';
    if (['ppt', 'pptx', 'odp', 'key'].includes(e)) return 'slide';
    if (['zip', 'rar', '7z', 'tar', 'gz', 'tgz', 'bz2'].includes(e)) return 'archive';
    if (CODE_EXT.has(e)) return 'code';
    if (TEXT_EXT.has(e) || m.startsWith('text/')) return 'text';
    return 'file';
  }
  const ICON_FOR = { folder: 'folder', image: 'image', video: 'video', audio: 'audio', pdf: 'text', doc: 'text', sheet: 'sheet', slide: 'slide', archive: 'archive', code: 'code', text: 'text', file: 'file' };

  /** What the browser can show inline. Mirrors the server's allow-list. */
  function previewKind(it) {
    if (it.kind !== 'file') return null;
    const m = it.mime || '';
    if (m.startsWith('image/')) return 'image';
    if (m.startsWith('video/')) return 'video';
    if (m.startsWith('audio/')) return 'audio';
    if (m === 'application/pdf') return 'pdf';
    if (m.startsWith('text/') || m === 'application/json' || m === 'application/xml' || CODE_EXT.has(ext(it.name)) || TEXT_EXT.has(ext(it.name))) return 'text';
    return null;
  }

  // ====================================================================
  // API
  // ====================================================================
  class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }

  async function api(method, url, body, { quiet = false } = {}) {
    const init = { method, credentials: 'same-origin', headers: {} };
    if (body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
    let res;
    try { res = await fetch(url, init); } catch { throw new ApiError('Can\'t reach the server. Check your connection.', 0); }
    let data = null;
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) {
      if (res.status === 401 && !quiet && state.user) sessionExpired();
      throw new ApiError((data && data.error) || `Request failed (${res.status}).`, res.status);
    }
    return data;
  }

  // ====================================================================
  // State
  // ====================================================================
  const stored = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
  const state = {
    user: null,
    route: { view: 'drive', id: null, q: '' },
    items: [], folder: null, path: [], access: 'owner', error: null,
    selected: new Set(), lastClicked: null,
    layout: stored('harbor.layout', 'grid'),
    sort: stored('harbor.sort', { by: 'name', dir: 'asc' }),
    storage: { used: 0, quota: 0 },
  };
  const byId = (id) => state.items.find((i) => i.id === id);
  const selectedItems = () => state.items.filter((i) => state.selected.has(i.id));

  // ====================================================================
  // Toasts
  // ====================================================================
  function toast(message, { error = false, action = null } = {}) {
    const el = document.createElement('div');
    el.className = `toast${error ? ' error' : ''}`;
    el.setAttribute('role', error ? 'alert' : 'status');
    el.innerHTML = `<span>${esc(message)}</span>`;
    if (action) {
      const b = document.createElement('button');
      b.textContent = action.label;
      b.onclick = () => { el.remove(); action.onClick(); };
      el.append(b);
    }
    $('#toasts').append(el);
    setTimeout(() => el.remove(), action ? 9000 : 5000);
  }

  // ====================================================================
  // Modals
  // ====================================================================
  function openModal({ title, body, actions = [], wide = false, onClose }) {
    const back = document.createElement('div');
    back.className = 'modal-back';
    back.innerHTML = `
      <div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true">
        <div class="modal-head"><h2></h2><button class="icon-btn" data-x aria-label="Close">${ic('close')}</button></div>
        <div class="modal-body"></div>
        <div class="modal-foot"></div>
      </div>`;
    $('h2', back).textContent = title;
    const bodyEl = $('.modal-body', back);
    if (typeof body === 'string') bodyEl.innerHTML = body; else if (body) bodyEl.append(body);
    const foot = $('.modal-foot', back);
    if (!actions.length) foot.remove();
    const previousFocus = document.activeElement;

    const modal = {
      el: back, body: bodyEl, buttons: {},
      close(result = null) {
        back.remove();
        document.removeEventListener('keydown', onKey, true);
        if (previousFocus && previousFocus.focus) previousFocus.focus();
        if (onClose) onClose(result);
      },
    };
    actions.forEach((a) => {
      const b = document.createElement('button');
      b.className = `btn ${a.kind || ''}`;
      b.textContent = a.label;
      b.onclick = () => a.onClick(modal, b);
      foot.append(b);
      modal.buttons[a.label] = b;
    });
    function onKey(e) { if (e.key === 'Escape') { e.stopPropagation(); modal.close(null); } }
    document.addEventListener('keydown', onKey, true);
    back.addEventListener('mousedown', (e) => { if (e.target === back) modal.close(null); });
    $('[data-x]', back).onclick = () => modal.close(null);
    $('#modals').append(back);
    const first = bodyEl.querySelector('input, select') || $('.btn.primary', foot);
    if (first) first.focus();
    return modal;
  }

  function promptName({ title, value = '', confirm = 'Save', placeholder = '' }) {
    return new Promise((resolve) => {
      const submit = (m) => {
        const input = $('input', m.body);
        const v = input.value.trim();
        if (!v) { $('.form-error', m.body).textContent = 'Enter a name.'; input.focus(); return; }
        if (/[\/\\]/.test(v)) { $('.form-error', m.body).textContent = 'Names can\'t contain / or \\.'; input.focus(); return; }
        m.close(v);
      };
      const m = openModal({
        title,
        body: `<input class="input" maxlength="255" autocomplete="off" value="${esc(value)}" placeholder="${esc(placeholder)}" aria-label="Name"><p class="form-error" style="margin:8px 0 0"></p>`,
        actions: [{ label: 'Cancel', onClick: (mm) => mm.close(null) }, { label: confirm, kind: 'primary', onClick: submit }],
        onClose: resolve,
      });
      const input = $('input', m.body);
      const dot = value.lastIndexOf('.');
      input.setSelectionRange(0, dot > 0 ? dot : value.length);
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(m); });
    });
  }

  function confirmDialog({ title, message, confirm = 'Confirm', danger = false }) {
    return new Promise((resolve) => {
      openModal({
        title, body: `<p>${esc(message)}</p>`,
        actions: [
          { label: 'Cancel', onClick: (m) => m.close(false) },
          { label: confirm, kind: danger ? 'danger' : 'primary', onClick: (m) => m.close(true) },
        ],
        onClose: (r) => resolve(!!r),
      });
    });
  }

  // ====================================================================
  // Popup menu
  // ====================================================================
  const ctx = $('#ctx');
  function hideMenu() { ctx.hidden = true; ctx.innerHTML = ''; ctx._entries = null; }
  function showMenu(x, y, entries) {
    ctx.innerHTML = entries.map((e, i) => {
      if (e.sep) return '<hr>';
      if (e.heading) return `<div class="ctx-title">${esc(e.heading)}</div>`;
      return `<button role="menuitem" data-i="${i}" class="${e.danger ? 'danger' : ''}">${e.icon ? ic(e.icon) : ''}<span>${esc(e.label)}</span>${e.check ? ic('check', 'check') : ''}</button>`;
    }).join('');
    ctx._entries = entries;
    ctx.hidden = false;
    const r = ctx.getBoundingClientRect();
    ctx.style.left = `${Math.max(8, Math.min(x, innerWidth - r.width - 8))}px`;
    ctx.style.top = `${Math.max(8, Math.min(y, innerHeight - r.height - 8))}px`;
    const first = $('button', ctx);
    if (first) first.focus({ preventScroll: true });
  }
  function menuBelow(button, entries) {
    const r = button.getBoundingClientRect();
    showMenu(r.left, r.bottom + 4, entries);
  }
  ctx.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-i]');
    if (!b) return;
    const entry = ctx._entries[Number(b.dataset.i)];
    hideMenu();
    if (entry.onClick) entry.onClick();
  });
  document.addEventListener('mousedown', (e) => { if (!ctx.hidden && !ctx.contains(e.target)) hideMenu(); }, true);
  document.addEventListener('keydown', (e) => {
    if (ctx.hidden) return;
    if (e.key === 'Escape') { hideMenu(); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const buttons = $$('button', ctx);
      let i = buttons.indexOf(document.activeElement);
      i = e.key === 'ArrowDown' ? (i + 1) % buttons.length : (i - 1 + buttons.length) % buttons.length;
      buttons[i].focus();
    }
  });
  addEventListener('resize', hideMenu);
  document.addEventListener('scroll', hideMenu, true);

  // ====================================================================
  // Auth screen
  // ====================================================================
  function renderAuth(mode = 'login') {
    const login = mode === 'login';
    $('#root').innerHTML = `
      <div class="auth">
        <form class="auth-card" id="authForm" novalidate>
          <div class="brand">${LOGO}<span>Harbor</span></div>
          <h1>${login ? 'Sign in' : 'Create your account'}</h1>
          <p class="sub">${login ? 'Pick up where you left off.' : 'Store, organize and share your files.'}</p>
          ${login ? '' : '<div class="field"><label for="a-name">Name</label><input class="input" id="a-name" autocomplete="name" required></div>'}
          <div class="field"><label for="a-email">Email</label><input class="input" id="a-email" type="email" autocomplete="email" required></div>
          <div class="field"><label for="a-pass">Password</label><input class="input" id="a-pass" type="password" autocomplete="${login ? 'current-password' : 'new-password'}" ${login ? '' : 'minlength="8"'} required>${login ? '' : '<span style="color:var(--ink-3);font-size:12px">At least 8 characters.</span>'}</div>
          <p class="form-error" id="authErr" role="alert"></p>
          <button class="btn primary" type="submit">${login ? 'Sign in' : 'Create account'}</button>
          <p class="auth-switch">${login ? 'New to Harbor?' : 'Already have an account?'} <button type="button" class="link-btn" id="switchMode">${login ? 'Create an account' : 'Sign in'}</button></p>
        </form>
      </div>`;
    $('#switchMode').onclick = () => renderAuth(login ? 'register' : 'login');
    $(login ? '#a-email' : '#a-name').focus();
    $('#authForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const err = $('#authErr');
      const btn = $('button[type="submit"]', e.target);
      err.textContent = '';
      btn.disabled = true;
      try {
        const payload = { email: $('#a-email').value, password: $('#a-pass').value };
        if (!login) payload.name = $('#a-name').value;
        const res = await api('POST', `/api/auth/${login ? 'login' : 'register'}`, payload, { quiet: true });
        state.user = res.user;
        location.hash = '#/drive';
        await startApp();
      } catch (ex) {
        err.textContent = ex.message;
        btn.disabled = false;
      }
    });
  }

  function sessionExpired() {
    state.user = null;
    renderAuth('login');
    toast('Your session expired. Sign in again.', { error: true });
  }

  // ====================================================================
  // App shell
  // ====================================================================
  const NAV = [
    ['drive', 'My Drive', 'drive'], ['shared', 'Shared with me', 'users'], ['recent', 'Recent', 'clock'],
    ['starred', 'Starred', 'star'], ['trash', 'Trash', 'trash'],
  ];

  function renderShell() {
    document.body.classList.remove('nav-open');
    $('#root').innerHTML = `
      <div class="app">
        <header class="topbar">
          <button class="icon-btn menu-btn" id="menuBtn" aria-label="Open menu">${ic('menu')}</button>
          <a class="brand" href="#/drive">${LOGO}<span>Harbor</span></a>
          <form class="search" id="searchForm" role="search">
            ${ic('search')}
            <input id="searchInput" type="text" placeholder="Search in Harbor" aria-label="Search files and folders" autocomplete="off" spellcheck="false">
            <button type="button" class="icon-btn clear" id="searchClear" aria-label="Clear search" hidden>${ic('close')}</button>
          </form>
          <div class="topbar-actions">
            <button class="icon-btn" id="themeBtn"></button>
            <button class="avatar" id="userBtn" aria-label="Account" aria-haspopup="menu">${esc((state.user.name || '?').trim().charAt(0))}</button>
          </div>
        </header>
        <aside class="sidebar" id="sidebar">
          <button class="new-btn" id="newBtn" aria-haspopup="menu">${ic('plus')}New</button>
          <nav class="nav" aria-label="Main">
            ${NAV.map(([v, label, icon]) => `<a href="#/${v}" data-nav="${v}">${ic(icon)}<span>${label}</span></a>`).join('')}
          </nav>
          <div class="storage" id="storage"></div>
        </aside>
        <main class="main" id="main">
          <div class="pathbar" id="pathbar"></div>
          <div class="toolbar" id="toolbar"></div>
          <div class="content" id="content" tabindex="-1"></div>
        </main>
      </div>
      <div class="scrim" id="scrim"></div>
      <input type="file" id="fileInput" multiple hidden>
      <input type="file" id="dirInput" webkitdirectory hidden>
      <div class="uploads" id="uploads" hidden></div>`;
    bindShell();
    renderTheme();
    renderStorage();
  }

  function renderTheme() {
    const dark = document.documentElement.dataset.theme === 'dark';
    const btn = $('#themeBtn');
    if (!btn) return;
    btn.innerHTML = ic(dark ? 'sun' : 'moon');
    btn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
  }

  function renderStorage() {
    const el = $('#storage');
    if (!el) return;
    const { used, quota } = state.storage;
    const pct = quota ? Math.min(100, (used / quota) * 100) : 0;
    el.innerHTML = `
      <div class="meter ${pct >= 95 ? 'full' : ''}" role="progressbar" aria-label="Storage used" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(pct)}"><span style="width:${pct}%"></span></div>
      <div>${fmtSize(used)} of ${fmtSize(quota)} used</div>`;
  }
  async function refreshStorage() {
    try { state.storage = await api('GET', '/api/storage'); renderStorage(); } catch { /* not critical */ }
  }

  function bindShell() {
    $('#menuBtn').onclick = () => document.body.classList.toggle('nav-open');
    $('#scrim').onclick = () => document.body.classList.remove('nav-open');
    $('#sidebar').addEventListener('click', (e) => { if (e.target.closest('a')) document.body.classList.remove('nav-open'); });

    $('#themeBtn').onclick = () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      localStorage.setItem('harbor.theme', next);
      renderTheme();
    };
    $('#userBtn').onclick = (e) => menuBelow(e.currentTarget, [
      { heading: `${state.user.name} (${state.user.email})` },
      { label: 'Sign out', icon: 'logout', onClick: signOut },
    ]);

    // Search
    const input = $('#searchInput');
    let timer;
    const runSearch = () => {
      const q = input.value.trim();
      $('#searchClear').hidden = !q;
      if (q) navigate(`#/search/${encodeURIComponent(q)}`, { replace: state.route.view === 'search' });
      else if (state.route.view === 'search') navigate('#/drive');
    };
    input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(runSearch, 280); $('#searchClear').hidden = !input.value; });
    $('#searchForm').addEventListener('submit', (e) => { e.preventDefault(); clearTimeout(timer); runSearch(); });
    $('#searchClear').onclick = () => { input.value = ''; runSearch(); input.focus(); };

    // New menu
    $('#newBtn').onclick = (e) => {
      if (!createTarget()) return;
      menuBelow(e.currentTarget, [
        { label: 'New folder', icon: 'folder-plus', onClick: newFolder },
        { sep: true },
        { label: 'File upload', icon: 'upload', onClick: () => $('#fileInput').click() },
        { label: 'Folder upload', icon: 'folder', onClick: () => $('#dirInput').click() },
      ]);
    };
    $('#fileInput').onchange = (e) => {
      enqueueUploads([...e.target.files].map((file) => ({ file, dirs: [] })));
      e.target.value = '';
    };
    $('#dirInput').onchange = (e) => {
      enqueueUploads([...e.target.files].map((file) => ({ file, dirs: file.webkitRelativePath.split('/').slice(0, -1) })));
      e.target.value = '';
    };

    bindContent();
  }

  async function signOut() {
    try { await api('POST', '/api/auth/logout', {}, { quiet: true }); } catch { /* ignore */ }
    state.user = null;
    state.items = [];
    location.hash = '';
    renderAuth('login');
  }

  // ====================================================================
  // Routing & loading
  // ====================================================================
  function parseRoute() {
    const [view = 'drive', ...rest] = location.hash.replace(/^#\/?/, '').split('/');
    const arg = rest.join('/');
    if (view === 'search') { let q = ''; try { q = decodeURIComponent(arg); } catch { q = arg; } return { view, q, id: null }; }
    if (view === 'drive' || view === 'shared') return { view, id: /^\d+$/.test(arg) ? Number(arg) : null };
    if (['recent', 'starred', 'trash'].includes(view)) return { view, id: null };
    return { view: 'drive', id: null };
  }
  function navigate(hash, { replace = false } = {}) {
    if (replace) { history.replaceState(null, '', hash); handleRoute(); } else if (location.hash === hash) handleRoute(); else location.hash = hash;
  }
  function handleRoute() {
    if (!state.user || !$('#content')) return;
    state.route = parseRoute();
    const input = $('#searchInput');
    if (state.route.view === 'search') { if (document.activeElement !== input) input.value = state.route.q; } else input.value = '';
    $('#searchClear').hidden = !input.value;
    load();
  }

  let loadSeq = 0;
  async function load({ keepSelection = false } = {}) {
    const seq = ++loadSeq;
    const r = state.route;
    const params = new URLSearchParams({ view: r.view, sort: state.sort.by, dir: state.sort.dir });
    if (r.id) params.set('parent', r.id);
    if (r.q) params.set('q', r.q);
    try {
      const data = await api('GET', `/api/items?${params}`);
      if (seq !== loadSeq) return;
      Object.assign(state, { items: data.items, folder: data.folder, path: data.path || [], access: data.access, error: null });
    } catch (e) {
      if (seq !== loadSeq) return;
      if (e.status === 401) return;
      if (e.status === 404 && r.id) { toast(e.message, { error: true }); navigate(`#/${r.view}`); return; }
      Object.assign(state, { items: [], folder: null, path: [], error: e.message });
    }
    state.selected = keepSelection ? new Set([...state.selected].filter((id) => byId(id))) : new Set();
    renderAll();
  }
  function renderAll() {
    renderNav();
    renderPath();
    renderToolbar();
    renderContent();
  }

  /** Where "New" and dropped files go, or null when the current view can't accept them. */
  function createTarget() {
    const { view } = state.route;
    if (view === 'drive') return { parentId: state.folder ? state.folder.id : null, label: state.folder ? state.folder.name : 'My Drive' };
    if (view === 'shared') {
      if (state.folder && (state.access === 'editor' || state.access === 'owner')) return { parentId: state.folder.id, label: state.folder.name };
      return null;
    }
    if (view === 'trash') return null;
    return { parentId: null, label: 'My Drive' };
  }

  function renderNav() {
    $$('.nav a').forEach((a) => {
      if (a.dataset.nav === state.route.view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    const nb = $('#newBtn');
    const ok = !!createTarget();
    nb.disabled = !ok;
    nb.title = ok ? '' : 'You can\'t add items here';
  }

  const VIEW_TITLE = { shared: 'Shared with me', recent: 'Recent', starred: 'Starred', trash: 'Trash' };
  function renderPath() {
    const r = state.route;
    const crumbs = [];
    if (r.view === 'drive' || r.view === 'shared') {
      const rootLabel = r.view === 'drive' ? 'My Drive' : 'Shared with me';
      crumbs.push({ label: rootLabel, href: `#/${r.view}`, drop: r.view === 'drive' ? 'root' : null });
      state.path.forEach((p, i) => crumbs.push({ label: p.name, href: `#/${r.view}/${p.id}`, drop: r.view === 'drive' ? p.id : null, current: i === state.path.length - 1 }));
      if (!state.path.length) crumbs[0].current = true;
    } else if (r.view === 'search') {
      crumbs.push({ label: r.q ? `Results for “${r.q}”` : 'Search', current: true });
    } else {
      crumbs.push({ label: VIEW_TITLE[r.view], current: true });
    }
    $('#pathbar').innerHTML = `<nav class="crumbs" aria-label="Location">${crumbs.map((c, i) => {
      const sep = i ? ic('chevron-right') : '';
      if (c.current) return `${sep}<span class="cur" aria-current="location">${esc(c.label)}</span>`;
      return `${sep}<a href="${c.href}" ${c.drop != null ? `data-drop-id="${c.drop}"` : ''}>${esc(c.label)}</a>`;
    }).join('')}</nav>`;
    document.title = `${crumbs[crumbs.length - 1].label} – Harbor`;
  }

  function sortLabel() { return { name: 'Name', modified: 'Last modified', size: 'Size' }[state.sort.by]; }
  function setSort(by) {
    if (state.sort.by === by) state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc';
    else state.sort = { by, dir: by === 'modified' ? 'desc' : 'asc' };
    localStorage.setItem('harbor.sort', JSON.stringify(state.sort));
    load({ keepSelection: true });
  }

  function renderToolbar() {
    const tb = $('#toolbar');
    if (state.selected.size) {
      const acts = availableActions(selectedItems()).filter((a) => a.bar);
      tb.innerHTML = `<div class="selbar" role="toolbar" aria-label="Actions for selected items">
        <button class="icon-btn" data-act="clear-sel" aria-label="Clear selection">${ic('close')}</button>
        <span class="count">${state.selected.size} selected</span>
        ${acts.map((a) => `<button class="icon-btn" data-act="${a.id}" title="${esc(a.label)}" aria-label="${esc(a.label)}">${ic(a.icon)}</button>`).join('')}
      </div>`;
      return;
    }
    const v = state.route.view;
    let left = '';
    if (v === 'trash') {
      left = '<span class="hint">Items in the trash are deleted forever after 30 days.</span>';
      if (state.items.length) left += `<button class="btn small" data-act="empty-trash">${ic('trash')}Empty trash</button>`;
    }
    const sortable = ['drive', 'shared', 'starred', 'search'].includes(v);
    tb.innerHTML = `${left}<div class="spacer"></div>
      ${sortable ? `<button class="btn small" data-act="sort" aria-haspopup="menu">${sortLabel()} ${ic('arrow-up', state.sort.dir === 'desc' ? 'flip' : '')}</button>` : ''}
      <div class="seg" role="group" aria-label="Layout">
        <button data-layout="grid" aria-pressed="${state.layout === 'grid'}" aria-label="Grid layout" title="Grid layout">${ic('grid')}</button>
        <button data-layout="list" aria-pressed="${state.layout === 'list'}" aria-label="List layout" title="List layout">${ic('list')}</button>
      </div>`;
  }

  // ---------------------------------------------------------------- items

  function subline(it) {
    const v = state.route.view;
    if (v === 'trash') return `Deleted ${fmtDate(it.trashedAt)}`;
    if (!it.owner.me) return `Shared by ${it.owner.name}`;
    if (v === 'recent') return `Opened ${fmtDate(it.openedAt || it.updatedAt)}`;
    return it.kind === 'folder' ? fmtDate(it.updatedAt) : `${fmtSize(it.size)}, ${fmtDate(it.updatedAt)}`;
  }
  function badges(it) {
    return (it.starred ? ic('star', 'fill star') : '') + (it.shared && it.owner.me ? `<span title="Shared">${ic('users', 'shared-ic')}</span>` : '');
  }
  function canDrag(it) { return it.owner.me && state.route.view !== 'trash'; }

  function itemHTML(it) {
    const cat = category(it);
    const sel = state.selected.has(it.id);
    const cls = state.layout === 'list' ? 'row item' : `item ${it.kind}`;
    const attrs = `class="${cls} cat-${cat}${sel ? ' selected' : ''}" data-id="${it.id}" data-kind="${it.kind}" tabindex="0" role="option" aria-selected="${sel}" ${canDrag(it) ? 'draggable="true"' : ''}`;
    const more = `<button class="icon-btn item-more" aria-label="More actions for ${esc(it.name)}" aria-haspopup="menu">${ic('more')}</button>`;
    if (state.layout === 'list') {
      const dateCol = state.route.view === 'trash' ? it.trashedAt : state.route.view === 'recent' ? (it.openedAt || it.updatedAt) : it.updatedAt;
      return `<div ${attrs}>
        <div class="cell-name"><span class="kind-ic">${ic(ICON_FOR[cat], it.kind === 'folder' ? 'fill' : '')}</span><span class="item-name" title="${esc(it.name)}">${esc(it.name)}</span>${badges(it)}</div>
        <div class="cell-muted cell-owner">${it.owner.me ? 'me' : esc(it.owner.name)}</div>
        <div class="cell-muted cell-date">${fmtDate(dateCol)}</div>
        <div class="cell-muted cell-size">${it.kind === 'folder' ? '–' : fmtSize(it.size)}</div>
        ${more}</div>`;
    }
    if (it.kind === 'folder') {
      return `<div ${attrs}><span class="kind-ic">${ic('folder', 'fill')}</span><span class="item-name" title="${esc(it.name)}">${esc(it.name)}</span>${badges(it)}${more}</div>`;
    }
    const thumb = cat === 'image' ? `<img loading="lazy" alt="" src="/api/items/${it.id}/download?inline=1">` : '';
    const e = ext(it.name);
    return `<div ${attrs}>
      <div class="thumb">${ic(ICON_FOR[cat])}${thumb}${e && e.length <= 5 ? `<span class="ext">${esc(e)}</span>` : ''}</div>
      <div class="item-meta"><span class="item-name" title="${esc(it.name)}">${esc(it.name)}</span>${badges(it)}${more}</div>
      <div class="sub">${esc(subline(it))}</div></div>`;
  }

  function emptyState() {
    const v = state.route.view;
    if (state.error) return { icon: 'close', title: 'Couldn\'t load your files', text: state.error, actions: '<button class="btn" data-act="reload">Try again</button>' };
    const can = createTarget();
    const add = can ? `<div style="display:flex;gap:8px"><button class="btn primary" data-act="upload-files">${ic('upload')}Upload files</button><button class="btn" data-act="new-folder">${ic('folder-plus')}New folder</button></div>` : '';
    const map = {
      drive: state.folder
        ? { icon: 'folder', title: 'This folder is empty', text: can ? 'Drag files here or use New to add some.' : 'Nothing has been added yet.', actions: add }
        : { icon: 'drive', title: 'Your drive is empty', text: 'Upload files or drag them anywhere on this page. They\'ll be stored here.', actions: add },
      shared: state.folder
        ? { icon: 'folder', title: 'This folder is empty', text: 'Nothing has been added yet.', actions: add }
        : { icon: 'users', title: 'Nothing has been shared with you', text: 'Files and folders that other people share with you will appear here.' },
      recent: { icon: 'clock', title: 'No recent files', text: 'Files you upload or open will show up here.' },
      starred: { icon: 'star', title: 'No starred items', text: 'Star important files and folders to find them quickly.' },
      trash: { icon: 'trash', title: 'Trash is empty', text: 'Items you delete stay here for 30 days before they\'re removed for good.' },
      search: { icon: 'search', title: state.route.q ? `No results for “${state.route.q}”` : 'Search your files', text: state.route.q ? 'Check the spelling or try a shorter word.' : 'Type a name in the search box above.' },
    };
    return map[v];
  }

  function renderContent() {
    const box = $('#content');
    if (!state.items.length) {
      const e = emptyState();
      box.innerHTML = `<div class="empty"><div class="art">${ic(e.icon)}</div><h2>${esc(e.title)}</h2><p>${esc(e.text)}</p>${e.actions || ''}</div>`;
      return;
    }
    const folders = state.items.filter((i) => i.kind === 'folder');
    const files = state.items.filter((i) => i.kind === 'file');
    if (state.layout === 'list') {
      const arrow = (key) => (state.sort.by === key ? ic('arrow-up', state.sort.dir === 'desc' ? 'flip' : '') : '');
      const sortable = ['drive', 'shared', 'starred', 'search'].includes(state.route.view);
      const head = (key, label) => (sortable ? `<button data-sort="${key}">${label}${arrow(key)}</button>` : label);
      const dateLabel = state.route.view === 'trash' ? 'Deleted' : state.route.view === 'recent' ? 'Last opened' : 'Last modified';
      box.innerHTML = `<div class="list" role="listbox" aria-multiselectable="true" aria-label="Files">
        <div class="list-head"><div>${head('name', 'Name')}</div><div class="col-owner">Owner</div><div class="col-date">${sortable ? head('modified', dateLabel) : dateLabel}</div><div>${head('size', 'Size')}</div><div></div></div>
        ${state.items.map(itemHTML).join('')}</div>`;
      return;
    }
    box.innerHTML = `<div role="listbox" aria-multiselectable="true" aria-label="Files and folders">
      ${folders.length ? `<div class="section-title">Folders</div><div class="folders">${folders.map(itemHTML).join('')}</div>` : ''}
      ${files.length ? `<div class="section-title">Files</div><div class="files">${files.map(itemHTML).join('')}</div>` : ''}</div>`;
  }

  // ====================================================================
  // Actions available for a selection
  // ====================================================================
  function canRename(it) { return it.owner.me || state.access === 'editor'; }
  const atShareRoot = () => state.route.view === 'shared' && !state.route.id;

  function availableActions(sel) {
    const v = state.route.view;
    const out = [];
    if (!sel.length) return out;
    if (v === 'trash') {
      out.push({ id: 'restore', label: 'Restore', icon: 'restore', bar: true });
      out.push({ id: 'purge', label: 'Delete forever', icon: 'trash', bar: true, danger: true });
      return out;
    }
    const one = sel.length === 1 ? sel[0] : null;
    const mine = sel.every((i) => i.owner.me);
    if (one && one.kind === 'folder') out.push({ id: 'open', label: 'Open', icon: 'folder' });
    if (one && previewKind(one)) out.push({ id: 'preview', label: 'Preview', icon: 'eye' });
    if (one && ['recent', 'starred', 'search'].includes(v)) out.push({ id: 'locate', label: 'Show in folder', icon: 'folder' });
    out.push({ id: 'download', label: 'Download', icon: 'download', bar: true });
    if (one && canRename(one)) out.push({ id: 'rename', label: 'Rename', icon: 'rename' });
    if (one && one.owner.me) out.push({ id: 'share', label: 'Share', icon: 'share', bar: true });
    if (mine) {
      out.push({ id: 'move', label: 'Move to…', icon: 'move', bar: true });
      const allStarred = sel.every((i) => i.starred);
      out.push({ id: allStarred ? 'unstar' : 'star', label: allStarred ? 'Remove star' : 'Add star', icon: 'star', bar: true });
      out.push({ sep: true });
      out.push({ id: 'trash', label: 'Move to trash', icon: 'trash', bar: true, danger: true });
    } else if (atShareRoot()) {
      out.push({ sep: true });
      out.push({ id: 'leave', label: 'Remove from Shared with me', icon: 'close', bar: true });
    }
    return out;
  }

  function menuFor(sel) {
    return availableActions(sel).map((a) => (a.sep ? a : { label: a.label, icon: a.icon, danger: a.danger, onClick: () => runAction(a.id, sel) }));
  }

  async function runAction(id, sel = selectedItems()) {
    try {
      switch (id) {
        case 'clear-sel': clearSelection(); break;
        case 'open': openItem(sel[0]); break;
        case 'preview': openItem(sel[0]); break;
        case 'locate': navigate(sel[0].parentId ? `#/drive/${sel[0].parentId}` : '#/drive'); break;
        case 'download': downloadItems(sel); break;
        case 'rename': await renameItem(sel[0]); break;
        case 'share': openShare(sel[0]); break;
        case 'move': await moveDialog(sel); break;
        case 'star': case 'unstar': await setStar(sel, id === 'star'); break;
        case 'trash': await trashItems(sel); break;
        case 'restore': await restoreItems(sel); break;
        case 'purge': await purgeItems(sel); break;
        case 'leave': await leaveShare(sel); break;
        case 'empty-trash': await emptyTrash(); break;
        case 'new-folder': await newFolder(); break;
        case 'upload-files': $('#fileInput').click(); break;
        case 'reload': load(); break;
        default: break;
      }
    } catch (e) {
      if (e.status !== 401) toast(e.message, { error: true });
    }
  }

  function openItem(it) {
    if (!it) return;
    if (state.route.view === 'trash') { toast('Restore this item to open it.'); return; }
    if (it.kind === 'folder') { navigate(`#/${state.route.view === 'shared' ? 'shared' : 'drive'}/${it.id}`); return; }
    if (previewKind(it)) {
      const list = state.items.filter((i) => previewKind(i));
      openPreview(list, list.findIndex((i) => i.id === it.id), (x, inline) => `/api/items/${x.id}/download${inline ? '?inline=1' : ''}`);
    } else downloadItems([it]);
  }

  function downloadItems(list) {
    list.forEach((it, i) => setTimeout(() => {
      const a = document.createElement('a');
      a.href = `/api/items/${it.id}/download`;
      a.download = '';
      document.body.append(a);
      a.click();
      a.remove();
    }, i * 350));
  }

  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

  async function renameItem(it) {
    const name = await promptName({ title: 'Rename', value: it.name });
    if (!name || name === it.name) return;
    await api('PATCH', `/api/items/${it.id}`, { name });
    await load({ keepSelection: true });
  }

  async function newFolder() {
    const target = createTarget();
    if (!target) return;
    const name = await promptName({ title: 'New folder', value: 'Untitled folder', confirm: 'Create' });
    if (!name) return;
    try {
      const res = await api('POST', '/api/items/folder', { name, parentId: target.parentId });
      if (['drive', 'shared'].includes(state.route.view)) {
        await load();
        state.selected = new Set([res.item.id]);
        updateSelectionUI();
      } else toast(`Created “${name}” in My Drive.`);
    } catch (e) { toast(e.message, { error: true }); }
  }

  async function setStar(list, on) {
    await Promise.all(list.map((it) => api('PATCH', `/api/items/${it.id}`, { starred: on })));
    await load({ keepSelection: true });
  }

  async function trashItems(list) {
    await Promise.all(list.map((it) => api('DELETE', `/api/items/${it.id}`)));
    await load();
    toast(`Moved ${plural(list.length, 'item')} to trash`, { action: { label: 'Undo', onClick: () => restoreItems(list, true) } });
  }
  async function restoreItems(list, quiet = false) {
    await Promise.all(list.map((it) => api('POST', `/api/items/${it.id}/restore`, {})));
    await load();
    if (!quiet) toast(`Restored ${plural(list.length, 'item')}`); else toast('Restored');
  }
  async function purgeItems(list) {
    const ok = await confirmDialog({
      title: 'Delete forever?',
      message: list.length === 1 ? `“${list[0].name}” will be permanently deleted. This can't be undone.` : `${plural(list.length, 'item')} will be permanently deleted. This can't be undone.`,
      confirm: 'Delete forever', danger: true,
    });
    if (!ok) return;
    await Promise.all(list.map((it) => api('DELETE', `/api/items/${it.id}?permanent=1`)));
    await load();
    refreshStorage();
    toast(`Deleted ${plural(list.length, 'item')} forever`);
  }
  async function emptyTrash() {
    const ok = await confirmDialog({ title: 'Empty trash?', message: 'Everything in the trash will be permanently deleted. This can\'t be undone.', confirm: 'Empty trash', danger: true });
    if (!ok) return;
    await api('POST', '/api/items/empty-trash', {});
    await load();
    refreshStorage();
    toast('Trash emptied');
  }
  async function leaveShare(list) {
    await Promise.all(list.map((it) => api('DELETE', `/api/items/${it.id}/shares/${state.user.id}`)));
    await load();
    toast(`Removed ${plural(list.length, 'item')} from Shared with me`);
  }

  // ---------------------------------------------------------------- moving

  async function moveItems(list, parentId) {
    const movable = list.filter((it) => it.owner.me && it.id !== parentId && (it.parentId ?? null) !== parentId);
    if (!movable.length) return;
    const previous = movable.map((it) => [it.id, it.parentId ?? null]);
    await Promise.all(movable.map((it) => api('PATCH', `/api/items/${it.id}`, { parentId })));
    await load();
    toast(`Moved ${plural(movable.length, 'item')}`, {
      action: {
        label: 'Undo',
        onClick: async () => {
          try {
            await Promise.all(previous.map(([id, pid]) => api('PATCH', `/api/items/${id}`, { parentId: pid })));
            await load();
          } catch (e) { toast(e.message, { error: true }); }
        },
      },
    });
  }

  function moveDialog(list) {
    return new Promise((resolve) => {
      const exclude = new Set(list.filter((i) => i.kind === 'folder').map((i) => i.id));
      let current = null;
      const m = openModal({
        title: list.length === 1 ? `Move “${list[0].name}”` : `Move ${plural(list.length, 'item')}`,
        body: '<div class="picker-path"></div><div class="picker-list" role="listbox" aria-label="Folders"></div>',
        actions: [
          { label: 'Cancel', onClick: (mm) => mm.close(null) },
          { label: 'Move here', kind: 'primary', onClick: (mm) => mm.close({ id: current }) },
        ],
        onClose: async (choice) => {
          resolve();
          if (choice) { try { await moveItems(list, choice.id); } catch (e) { toast(e.message, { error: true }); } }
        },
      });
      const pathEl = $('.picker-path', m.body);
      const listEl = $('.picker-list', m.body);
      async function show(parentId) {
        current = parentId;
        const data = await api('GET', `/api/items?view=drive&kind=folder${parentId ? `&parent=${parentId}` : ''}`);
        const crumbs = [{ id: null, name: 'My Drive' }, ...data.path];
        pathEl.innerHTML = crumbs.map((c, i) => `${i ? ic('chevron-right') : ''}<button data-go="${c.id ?? ''}">${esc(c.name)}</button>`).join('');
        listEl.innerHTML = data.items.length
          ? data.items.map((f) => `<button data-open="${f.id}" ${exclude.has(f.id) ? 'disabled' : ''}>${ic('folder', 'fill')}<span>${esc(f.name)}</span></button>`).join('')
          : '<div class="picker-empty">No folders here</div>';
        m.buttons['Move here'].disabled = list.every((it) => (it.parentId ?? null) === parentId);
      }
      m.body.addEventListener('click', (e) => {
        const go = e.target.closest('[data-go]');
        const open = e.target.closest('[data-open]');
        if (go) show(go.dataset.go ? Number(go.dataset.go) : null).catch((x) => toast(x.message, { error: true }));
        if (open) show(Number(open.dataset.open)).catch((x) => toast(x.message, { error: true }));
      });
      show(null).catch((x) => toast(x.message, { error: true }));
    });
  }

  // ---------------------------------------------------------------- sharing

  async function openShare(item) {
    let s;
    const m = openModal({
      title: `Share “${item.name}”`, wide: true, body: '<p>Loading…</p>',
      actions: [{ label: 'Done', kind: 'primary', onClick: (mm) => mm.close() }],
      onClose: () => load({ keepSelection: true }),
    });
    try { s = await api('GET', `/api/items/${item.id}/sharing`); } catch (e) { m.close(); toast(e.message, { error: true }); return; }
    const linkUrl = () => `${location.origin}/s/${s.link.token}`;
    const initial = (n) => esc((n || '?').trim().charAt(0));

    function render(errorText = '', keepEmail = '') {
      m.body.innerHTML = `
        <div class="share-add">
          <input class="input" id="shEmail" type="email" placeholder="Add people by email" aria-label="Email address" autocomplete="off" value="${esc(keepEmail)}">
          <select class="select" id="shRole" aria-label="Permission"><option value="viewer">Viewer</option><option value="editor">Editor</option></select>
          <button class="btn primary" id="shAdd">Share</button>
        </div>
        <p class="form-error" id="shErr" style="margin:6px 0 0">${esc(errorText)}</p>
        <div class="people">
          <div class="person"><span class="avatar">${initial(s.owner.name)}</span><div class="who"><b>${esc(s.owner.name)} (you)</b><span>${esc(s.owner.email)}</span></div><span class="role-static">Owner</span></div>
          ${s.people.map((p) => `<div class="person"><span class="avatar">${initial(p.name)}</span>
            <div class="who"><b>${esc(p.name)}</b><span>${esc(p.email)}</span></div>
            <select class="select small" data-role="${p.userId}" data-email="${esc(p.email)}" aria-label="Permission for ${esc(p.name)}"><option value="viewer" ${p.role === 'viewer' ? 'selected' : ''}>Viewer</option><option value="editor" ${p.role === 'editor' ? 'selected' : ''}>Editor</option></select>
            <button class="icon-btn" data-remove="${p.userId}" aria-label="Remove ${esc(p.name)}">${ic('close')}</button></div>`).join('')}
        </div>
        <div class="general">
          <span class="globe">${ic('globe')}</span>
          <div class="txt"><b>Anyone with the link</b><span>${s.link.enabled ? 'Anyone who has the link can view.' : 'Turned off. Only the people above can open this.'}</span></div>
          <button class="switch" id="shLink" role="switch" aria-checked="${s.link.enabled}" aria-label="Anyone with the link can view"></button>
        </div>
        ${s.link.enabled ? `<div class="link-row"><input class="input" id="shUrl" readonly value="${esc(linkUrl())}" aria-label="Share link"><button class="btn" id="shCopy">${ic('link')}Copy link</button></div>` : ''}`;
    }
    render();

    const call = async (fn) => { try { s = await fn(); render(); } catch (e) { render(e.message, $('#shEmail', m.body)?.value || ''); } };
    m.body.addEventListener('click', async (e) => {
      if (e.target.closest('#shAdd')) {
        const email = $('#shEmail', m.body).value.trim();
        if (!email) { $('#shErr', m.body).textContent = 'Enter an email address.'; return; }
        const role = $('#shRole', m.body).value;
        await call(() => api('POST', `/api/items/${item.id}/shares`, { email, role }));
      } else if (e.target.closest('[data-remove]')) {
        await call(() => api('DELETE', `/api/items/${item.id}/shares/${e.target.closest('[data-remove]').dataset.remove}`));
      } else if (e.target.closest('#shLink')) {
        await call(() => api('POST', `/api/items/${item.id}/link`, { enabled: !s.link.enabled }));
      } else if (e.target.closest('#shCopy')) {
        const input = $('#shUrl', m.body);
        try { await navigator.clipboard.writeText(input.value); } catch { input.select(); document.execCommand('copy'); }
        toast('Link copied');
      }
    });
    m.body.addEventListener('change', async (e) => {
      const sel = e.target.closest('[data-role]');
      if (sel) await call(() => api('POST', `/api/items/${item.id}/shares`, { email: sel.dataset.email, role: sel.value }));
    });
    m.body.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.id === 'shEmail') { e.preventDefault(); $('#shAdd', m.body).click(); } });
  }

  // ====================================================================
  // Selection, clicks, keyboard
  // ====================================================================
  function clearSelection() { state.selected.clear(); updateSelectionUI(); }
  function selectOnly(id) { state.selected = new Set([id]); }
  function updateSelectionUI() {
    $$('#content .item').forEach((el) => {
      const on = state.selected.has(Number(el.dataset.id));
      el.classList.toggle('selected', on);
      el.setAttribute('aria-selected', on);
    });
    renderToolbar();
  }

  function bindContent() {
    const content = $('#content');
    const main = $('#main');

    content.addEventListener('error', (e) => { if (e.target.tagName === 'IMG') e.target.remove(); }, true);

    content.addEventListener('click', (e) => {
      const act = e.target.closest('[data-act]');
      if (act) { runAction(act.dataset.act, []); return; }
      const sortBtn = e.target.closest('[data-sort]');
      if (sortBtn) { setSort(sortBtn.dataset.sort); return; }
      const el = e.target.closest('.item');
      if (!el) { if (state.selected.size) clearSelection(); return; }
      const id = Number(el.dataset.id);
      const it = byId(id);
      if (e.target.closest('.item-more')) {
        if (!state.selected.has(id)) { selectOnly(id); updateSelectionUI(); }
        menuBelow(e.target.closest('.item-more'), menuFor(selectedItems()));
        return;
      }
      if (coarse) { openItem(it); return; }
      if (e.metaKey || e.ctrlKey) {
        if (state.selected.has(id)) state.selected.delete(id); else state.selected.add(id);
      } else if (e.shiftKey && state.lastClicked != null) {
        const ids = state.items.map((i) => i.id);
        const [a, b] = [ids.indexOf(state.lastClicked), ids.indexOf(id)].sort((x, y) => x - y);
        state.selected = new Set(ids.slice(a, b + 1));
      } else selectOnly(id);
      state.lastClicked = id;
      updateSelectionUI();
    });

    content.addEventListener('dblclick', (e) => {
      const el = e.target.closest('.item');
      if (el && !e.target.closest('.item-more')) openItem(byId(Number(el.dataset.id)));
    });

    content.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      const el = e.target.closest('.item');
      if (el) {
        const id = Number(el.dataset.id);
        if (!state.selected.has(id)) { selectOnly(id); updateSelectionUI(); }
        showMenu(e.clientX, e.clientY, menuFor(selectedItems()));
      } else {
        clearSelection();
        const target = createTarget();
        if (target) {
          showMenu(e.clientX, e.clientY, [
            { label: 'New folder', icon: 'folder-plus', onClick: newFolder },
            { label: 'File upload', icon: 'upload', onClick: () => $('#fileInput').click() },
            { label: 'Folder upload', icon: 'folder', onClick: () => $('#dirInput').click() },
          ]);
        }
      }
    });

    content.addEventListener('keydown', (e) => {
      const el = e.target.closest('.item');
      if (!el || e.target !== el) return;
      const id = Number(el.dataset.id);
      if (e.key === 'Enter') { e.preventDefault(); openItem(byId(id)); }
      if (e.key === ' ') { e.preventDefault(); if (state.selected.has(id)) state.selected.delete(id); else state.selected.add(id); updateSelectionUI(); }
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft' || e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        const all = $$('#content .item');
        const i = all.indexOf(el);
        const next = all[i + (e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : -1)];
        if (next) { e.preventDefault(); next.focus(); }
      }
    });

    // Toolbar (selection bar, sort, layout)
    $('#toolbar').addEventListener('click', (e) => {
      const layout = e.target.closest('[data-layout]');
      if (layout) {
        state.layout = layout.dataset.layout;
        localStorage.setItem('harbor.layout', JSON.stringify(state.layout));
        renderToolbar();
        renderContent();
        return;
      }
      const act = e.target.closest('[data-act]');
      if (!act) return;
      if (act.dataset.act === 'sort') {
        menuBelow(act, [
          { heading: 'Sort by' },
          ...['name', 'modified', 'size'].map((k) => ({
            label: { name: 'Name', modified: 'Last modified', size: 'Size' }[k],
            check: state.sort.by === k, onClick: () => setSort(k),
          })),
          { sep: true },
          { label: state.sort.dir === 'asc' ? 'Ascending' : 'Descending', icon: 'arrow-up', onClick: () => { state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc'; localStorage.setItem('harbor.sort', JSON.stringify(state.sort)); load({ keepSelection: true }); } },
        ]);
        return;
      }
      runAction(act.dataset.act);
    });

    // Drag & drop: moving items into folders, and dropping files from the desktop
    let dragIds = [];
    content.addEventListener('dragstart', (e) => {
      const el = e.target.closest('.item');
      if (!el) return;
      const id = Number(el.dataset.id);
      if (!state.selected.has(id)) { selectOnly(id); updateSelectionUI(); }
      dragIds = [...state.selected];
      e.dataTransfer.setData('application/x-harbor-items', JSON.stringify(dragIds));
      e.dataTransfer.effectAllowed = 'move';
      requestAnimationFrame(() => dragIds.forEach((i) => $(`#content .item[data-id="${i}"]`)?.classList.add('dragging')));
    });
    content.addEventListener('dragend', () => { dragIds = []; $$('.dragging, .drop-target').forEach((el) => el.classList.remove('dragging', 'drop-target')); });

    const internal = (e) => e.dataTransfer && [...e.dataTransfer.types].includes('application/x-harbor-items');
    const dropTarget = (e) => e.target.closest('#content .item[data-kind="folder"], #pathbar [data-drop-id]');
    const targetId = (el) => (el.dataset.dropId !== undefined ? (el.dataset.dropId === 'root' ? null : Number(el.dataset.dropId)) : Number(el.dataset.id));
    const over = (e) => {
      if (!internal(e)) return;
      const t = dropTarget(e);
      $$('.drop-target').forEach((el) => { if (el !== t) el.classList.remove('drop-target'); });
      if (t && !dragIds.includes(targetId(t))) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; t.classList.add('drop-target'); }
    };
    const drop = async (e) => {
      if (!internal(e)) return;
      const t = dropTarget(e);
      if (!t) return;
      e.preventDefault();
      t.classList.remove('drop-target');
      const ids = dragIds.slice();
      dragIds = [];
      try { await moveItems(state.items.filter((i) => ids.includes(i.id)), targetId(t)); } catch (x) { toast(x.message, { error: true }); }
    };
    [content, $('#pathbar')].forEach((z) => { z.addEventListener('dragover', over); z.addEventListener('drop', drop); z.addEventListener('dragleave', (e) => { const t = dropTarget(e); if (t && !t.contains(e.relatedTarget)) t.classList.remove('drop-target'); }); });

    // Files dragged in from the desktop
    let depth = 0;
    const hasFiles = (e) => e.dataTransfer && [...e.dataTransfer.types].includes('Files');
    const overlay = () => $('.drop-overlay', main);
    const hideOverlay = () => { depth = 0; const o = overlay(); if (o) o.remove(); };
    main.addEventListener('dragenter', (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth++;
      const target = createTarget();
      if (target && !overlay()) {
        const o = document.createElement('div');
        o.className = 'drop-overlay';
        o.innerHTML = `<div>${ic('upload')}Drop to upload to ${esc(target.label)}</div>`;
        main.append(o);
      }
    });
    main.addEventListener('dragover', (e) => { if (hasFiles(e)) { e.preventDefault(); e.dataTransfer.dropEffect = createTarget() ? 'copy' : 'none'; } });
    main.addEventListener('dragleave', (e) => { if (!hasFiles(e)) return; depth--; if (depth <= 0) hideOverlay(); });
    main.addEventListener('drop', async (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      hideOverlay();
      // A folder card under the pointer becomes the destination.
      const folderEl = e.target.closest('.item[data-kind="folder"]');
      const parentId = folderEl && state.route.view === 'drive' ? Number(folderEl.dataset.id) : undefined;
      const entries = await entriesFromDataTransfer(e.dataTransfer);
      enqueueUploads(entries, parentId);
    });
  }

  // Global shortcuts
  document.addEventListener('keydown', (e) => {
    if (!state.user || !$('#content')) return;
    if ($('#modals').children.length || $('.preview') || !ctx.hidden) return;
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    const sel = selectedItems();
    if (e.key === 'Escape' && sel.length) { clearSelection(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') { e.preventDefault(); state.selected = new Set(state.items.map((i) => i.id)); updateSelectionUI(); return; }
    if (!sel.length) return;
    const allowed = availableActions(sel).map((a) => a.id);
    if ((e.key === 'Delete' || e.key === 'Backspace') && (allowed.includes('trash') || allowed.includes('purge'))) { e.preventDefault(); runAction(allowed.includes('purge') ? 'purge' : 'trash', sel); }
    if (e.key === 'F2' && allowed.includes('rename')) { e.preventDefault(); runAction('rename', sel); }
  });

  // ====================================================================
  // Uploads
  // ====================================================================
  const uploads = { jobs: [], running: 0, seq: 0, collapsed: false, folderCache: new Map(), refreshTimer: null };
  const MAX_PARALLEL = 3;

  /** Turns dropped files and folders into a flat list of { file, dirs }. */
  async function entriesFromDataTransfer(dt) {
    const roots = [...dt.items].map((i) => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null)).filter(Boolean);
    if (!roots.length) return [...dt.files].map((file) => ({ file, dirs: [] }));
    const out = [];
    const readAll = (reader) => new Promise((resolve, reject) => {
      const all = [];
      (function next() {
        reader.readEntries((batch) => { if (!batch.length) resolve(all); else { all.push(...batch); next(); } }, reject);
      })();
    });
    async function walk(entry, dirs) {
      if (entry.isFile) {
        const file = await new Promise((res, rej) => entry.file(res, rej));
        out.push({ file, dirs });
      } else if (entry.isDirectory) {
        const here = [...dirs, entry.name];
        const children = await readAll(entry.createReader());
        if (!children.length) out.push({ file: null, dirs: here }); // keep empty folders
        for (const c of children) await walk(c, here);
      }
    }
    for (const r of roots) await walk(r, []);
    return out;
  }

  function enqueueUploads(entries, parentOverride) {
    if (!entries.length) return;
    const target = parentOverride !== undefined ? { parentId: parentOverride } : createTarget();
    if (!target) { toast('You can\'t upload here. Open a folder you can edit first.', { error: true }); return; }
    if (['recent', 'starred', 'search'].includes(state.route.view)) toast('Uploading to My Drive');
    for (const en of entries) {
      uploads.jobs.push({ id: ++uploads.seq, file: en.file, name: en.file ? en.file.name : en.dirs[en.dirs.length - 1], dirs: en.dirs, target: target.parentId, status: 'queued', loaded: 0, total: en.file ? en.file.size : 0, xhr: null, error: '' });
    }
    renderUploads();
    pump();
  }

  function pump() {
    while (uploads.running < MAX_PARALLEL) {
      const job = uploads.jobs.find((j) => j.status === 'queued');
      if (!job) return;
      runJob(job);
    }
  }

  async function runJob(job) {
    job.status = 'uploading';
    uploads.running++;
    renderUploads();
    try {
      const parentId = await ensurePath(job.target, job.dirs);
      if (job.status === 'canceled') throw new Error('Canceled');
      if (job.file) await sendFile(job, parentId);
      job.status = 'done';
    } catch (e) {
      if (job.status !== 'canceled') { job.status = 'error'; job.error = e.message; }
    }
    uploads.running--;
    renderUploads();
    scheduleRefresh();
    pump();
    if (!uploads.running && !uploads.jobs.some((j) => j.status === 'queued')) uploads.folderCache.clear();
  }

  /** Creates any missing folders for a dropped directory tree, once per path. */
  async function ensurePath(target, dirs) {
    let parent = target;
    let key = String(target ?? 'root');
    for (const name of dirs) {
      key += `/${name}`;
      const k = key;
      const pid = parent;
      if (!uploads.folderCache.has(k)) {
        uploads.folderCache.set(k, api('POST', '/api/items/folder', { name, parentId: pid }).then((r) => r.item.id).catch((e) => { uploads.folderCache.delete(k); throw e; }));
      }
      parent = await uploads.folderCache.get(k);
    }
    return parent;
  }

  function sendFile(job, parentId) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      job.xhr = xhr;
      xhr.open('POST', `/api/items/upload?parentId=${parentId ?? 'root'}`);
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) { job.loaded = e.loaded; job.total = e.total; updateUploadRow(job); } };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) { job.loaded = job.total; resolve(); return; }
        let msg = 'Upload failed.';
        try { msg = JSON.parse(xhr.responseText).error || msg; } catch { /* keep default */ }
        if (xhr.status === 401) sessionExpired();
        reject(new Error(msg));
      };
      xhr.onerror = () => reject(new Error('Network error. Check your connection.'));
      xhr.onabort = () => reject(new Error('Canceled'));
      const fd = new FormData();
      fd.append('files', job.file, job.file.name);
      xhr.send(fd);
    });
  }

  function cancelJob(id) {
    const job = uploads.jobs.find((j) => j.id === id);
    if (!job || !['queued', 'uploading'].includes(job.status)) return;
    job.status = 'canceled';
    if (job.xhr) job.xhr.abort();
    renderUploads();
  }

  function scheduleRefresh() {
    clearTimeout(uploads.refreshTimer);
    uploads.refreshTimer = setTimeout(() => {
      refreshStorage();
      if (state.user && ['drive', 'shared', 'recent'].includes(state.route.view)) load({ keepSelection: true });
    }, 400);
  }

  function updateUploadRow(job) {
    const row = $(`.upload-row[data-job="${job.id}"] .progress span`);
    if (row) row.style.width = `${job.total ? Math.min(100, (job.loaded / job.total) * 100) : 0}%`;
  }

  function renderUploads() {
    const panel = $('#uploads');
    if (!panel) return;
    if (!uploads.jobs.length) { panel.hidden = true; return; }
    panel.hidden = false;
    panel.classList.toggle('collapsed', uploads.collapsed);
    const active = uploads.jobs.filter((j) => ['queued', 'uploading'].includes(j.status)).length;
    const failed = uploads.jobs.filter((j) => j.status === 'error').length;
    const done = uploads.jobs.filter((j) => j.status === 'done').length;
    const title = active ? `Uploading ${plural(active, 'item')}` : failed ? `${plural(failed, 'upload')} failed` : `${plural(done, 'upload')} complete`;
    const stateText = { queued: 'Waiting', uploading: 'Uploading', done: 'Done', error: '', canceled: 'Canceled' };
    panel.innerHTML = `
      <div class="uploads-head"><b>${esc(title)}</b>
        <button class="icon-btn" data-up="toggle" aria-label="${uploads.collapsed ? 'Expand' : 'Collapse'} uploads">${ic('chevron-down', uploads.collapsed ? 'flip' : '')}</button>
        ${active ? '' : `<button class="icon-btn" data-up="close" aria-label="Close uploads">${ic('close')}</button>`}
      </div>
      <div class="uploads-list">${uploads.jobs.map((j) => `
        <div class="upload-row" data-job="${j.id}">
          <span class="cat-${j.file ? category({ kind: 'file', name: j.name, mime: j.file.type }) : 'folder'}" style="color:var(--cat)">${ic(j.file ? ICON_FOR[category({ kind: 'file', name: j.name, mime: j.file.type })] : 'folder')}</span>
          <span class="name" title="${esc(j.name)}">${esc(j.name)}</span>
          ${j.status === 'done' ? `<span class="done">${ic('check')}</span>`
            : ['queued', 'uploading'].includes(j.status) ? `<button class="icon-btn" data-cancel="${j.id}" aria-label="Cancel upload of ${esc(j.name)}">${ic('close')}</button>`
            : `<span class="state ${j.status === 'error' ? 'err' : ''}">${esc(j.status === 'error' ? j.error : stateText[j.status])}</span>`}
          ${j.status === 'uploading' || j.status === 'queued' ? `<div class="progress"><span style="width:${j.total ? Math.min(100, (j.loaded / j.total) * 100) : 0}%"></span></div>` : ''}
        </div>`).join('')}</div>`;
  }

  document.addEventListener('click', (e) => {
    const up = e.target.closest('[data-up]');
    if (up) {
      if (up.dataset.up === 'toggle') { uploads.collapsed = !uploads.collapsed; renderUploads(); }
      if (up.dataset.up === 'close') { uploads.jobs = []; renderUploads(); }
    }
    const c = e.target.closest('[data-cancel]');
    if (c) cancelJob(Number(c.dataset.cancel));
  });

  addEventListener('beforeunload', (e) => {
    if (uploads.jobs.some((j) => ['queued', 'uploading'].includes(j.status))) { e.preventDefault(); e.returnValue = ''; }
  });

  // ====================================================================
  // Preview
  // ====================================================================
  const TEXT_PREVIEW_BYTES = 256 * 1024;

  /** Builds the element that shows one file. `urlFor(item, inline)` decides where bytes come from. */
  async function buildPreview(it, urlFor) {
    const kind = previewKind(it);
    const src = urlFor(it, true);
    let el;
    if (kind === 'image') { el = document.createElement('img'); el.alt = it.name; el.src = src; }
    else if (kind === 'video') { el = document.createElement('video'); el.controls = true; el.autoplay = true; el.playsInline = true; el.src = src; }
    else if (kind === 'audio') {
      el = document.createElement('div');
      el.className = 'audio-card';
      el.innerHTML = `${ic('audio')}<b>${esc(it.name)}</b>`;
      const a = document.createElement('audio');
      a.controls = true; a.autoplay = true; a.src = src;
      el.append(a);
    } else if (kind === 'pdf') { el = document.createElement('iframe'); el.title = it.name; el.src = src; }
    else if (kind === 'text') {
      el = document.createElement('pre');
      try {
        const res = await fetch(src, { headers: { Range: `bytes=0-${TEXT_PREVIEW_BYTES - 1}` }, credentials: 'same-origin' });
        if (!res.ok && res.status !== 206) throw new Error();
        let text = await res.text();
        if (it.size > TEXT_PREVIEW_BYTES) text += '\n\n… Preview shows the first 256 KB. Download the file to see everything.';
        el.textContent = text || '(This file is empty.)';
      } catch { el.textContent = 'Couldn\'t load a preview of this file.'; }
    } else {
      el = document.createElement('div');
      el.className = `nopreview cat-${category(it)}`;
      el.innerHTML = `${ic(ICON_FOR[category(it)])}<b>${esc(it.name)}</b><span>No preview for this type of file.</span>
        <a class="btn primary" href="${urlFor(it, false)}" download>${ic('download')}Download</a>`;
    }
    return el;
  }

  function openPreview(list, startIndex, urlFor) {
    let index = Math.max(0, startIndex);
    let token = 0;
    const previousFocus = document.activeElement;
    const overlay = document.createElement('div');
    overlay.className = 'preview';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.innerHTML = `
      <div class="preview-bar">
        <div class="title"></div>
        <a class="icon-btn" data-dl aria-label="Download" title="Download" download>${ic('download')}</a>
        <button class="icon-btn" data-close aria-label="Close preview" title="Close">${ic('close')}</button>
      </div>
      <div class="preview-stage">
        <button class="icon-btn nav-btn prev" aria-label="Previous file">${ic('chevron-left')}</button>
        <button class="icon-btn nav-btn next" aria-label="Next file">${ic('chevron-right')}</button>
      </div>`;
    const stage = $('.preview-stage', overlay);

    async function show() {
      const it = list[index];
      const mine = ++token;
      $('.title', overlay).innerHTML = `<span class="cat-${category(it)}" style="color:var(--cat);display:flex">${ic(ICON_FOR[category(it)])}</span><span>${esc(it.name)}</span>`;
      $('[data-dl]', overlay).href = urlFor(it, false);
      $('.prev', overlay).hidden = $('.next', overlay).hidden = list.length < 2;
      $$(':scope > :not(.nav-btn)', stage).forEach((n) => n.remove());
      const el = await buildPreview(it, urlFor);
      if (mine !== token) return;
      stage.append(el);
    }
    const step = (d) => { index = (index + d + list.length) % list.length; show(); };
    function close() {
      document.removeEventListener('keydown', onKey, true);
      overlay.remove();
      if (previousFocus && previousFocus.focus) previousFocus.focus();
    }
    function onKey(e) {
      if (e.key === 'Escape') { e.stopPropagation(); close(); }
      else if (e.key === 'ArrowRight' && list.length > 1) step(1);
      else if (e.key === 'ArrowLeft' && list.length > 1) step(-1);
    }
    $('[data-close]', overlay).onclick = close;
    $('.prev', overlay).onclick = () => step(-1);
    $('.next', overlay).onclick = () => step(1);
    document.addEventListener('keydown', onKey, true);
    document.body.append(overlay);
    $('[data-close]', overlay).focus();
    show();
  }

  // ====================================================================
  // Public share page (/s/<token>)
  // ====================================================================
  async function bootPublic(token) {
    const urlFor = (it, inline) => `/api/public/${token}/download/${it.id}${inline ? '?inline=1' : ''}`;
    const root = $('#root');
    const shell = (inner) => {
      root.innerHTML = `<div class="pub">
        <div class="pub-top"><a class="brand" href="/">${LOGO}<span>Harbor</span></a><a class="btn" href="/">Sign in</a></div>
        <main class="pub-main">${inner}</main></div>`;
    };

    async function show() {
      const folderId = (location.hash.match(/^#\/(\d+)/) || [])[1];
      let data;
      try {
        data = await api('GET', `/api/public/${token}${folderId ? `?folder=${folderId}` : ''}`, undefined, { quiet: true });
      } catch (e) {
        shell(`<div class="empty"><div class="art">${ic('link')}</div><h2>This link doesn't work</h2><p>${esc(e.message)}</p><a class="btn primary" href="/">Go to Harbor</a></div>`);
        document.title = 'Link unavailable – Harbor';
        return;
      }
      const { root: top } = data;
      const here = data.path.length ? data.path[data.path.length - 1] : top;
      document.title = `${here.name} – Harbor`;

      if (top.kind === 'file') {
        shell(`<div class="pub-head"><div class="grow"><h1>${esc(top.name)}</h1><div class="by">Shared by ${esc(data.sharedBy)}, ${fmtSize(top.size)}</div></div>
          <a class="btn primary" href="${urlFor(top, false)}" download>${ic('download')}Download</a></div><div class="pub-preview" id="pubPreview"></div>`);
        $('#pubPreview').append(await buildPreview(top, urlFor));
        return;
      }

      const files = data.items.filter((i) => i.kind === 'file' && previewKind(i));
      shell(`<div class="pub-head"><div class="grow"><h1>${esc(here.name)}</h1><div class="by">Shared by ${esc(data.sharedBy)}</div></div>
          <a class="btn primary" href="${urlFor(here, false)}" download>${ic('download')}Download all</a></div>
        ${data.path.length > 1 ? `<nav class="crumbs" style="margin-bottom:8px" aria-label="Location">${data.path.map((p, i) => `${i ? ic('chevron-right') : ''}${i === data.path.length - 1 ? `<span class="cur">${esc(p.name)}</span>` : `<a href="#/${i === 0 ? '' : p.id}">${esc(p.name)}</a>`}`).join('')}</nav>` : ''}
        ${data.items.length ? `<div class="list" role="list">
          <div class="list-head"><div>Name</div><div>Last modified</div><div>Size</div></div>
          ${data.items.map((i) => {
            const cat = category(i);
            return `<div class="row cat-${cat}" role="listitem" tabindex="0" data-id="${i.id}"><div class="cell-name"><span class="kind-ic" style="color:var(--cat)">${ic(ICON_FOR[cat], i.kind === 'folder' ? 'fill' : '')}</span><span class="item-name">${esc(i.name)}</span></div><div class="cell-muted">${fmtDate(i.updatedAt)}</div><div class="cell-muted">${i.kind === 'folder' ? '–' : fmtSize(i.size)}</div></div>`;
          }).join('')}</div>` : '<div class="empty"><div class="art">' + ic('folder') + '</div><h2>This folder is empty</h2></div>'}`);
      const open = (row) => {
        const i = data.items.find((x) => x.id === Number(row.dataset.id));
        if (i.kind === 'folder') location.hash = `#/${i.id}`;
        else if (previewKind(i)) openPreview(files, files.findIndex((f) => f.id === i.id), urlFor);
        else location.href = urlFor(i, false);
      };
      $$('.row', root).forEach((row) => {
        row.addEventListener('click', () => open(row));
        row.addEventListener('keydown', (e) => { if (e.key === 'Enter') open(row); });
      });
    }
    addEventListener('hashchange', show);
    show();
  }

  // ====================================================================
  // Start
  // ====================================================================
  async function startApp() {
    renderShell();
    state.route = parseRoute();
    if (!location.hash) history.replaceState(null, '', '#/drive');
    handleRoute();
    refreshStorage();
  }

  addEventListener('hashchange', handleRoute);

  (async function boot() {
    const pub = location.pathname.match(/^\/s\/([\w-]+)/);
    if (pub) { bootPublic(pub[1]); return; }
    try {
      const me = await api('GET', '/api/auth/me', undefined, { quiet: true });
      state.user = me.user;
      state.storage = me.storage;
      await startApp();
    } catch {
      renderAuth('login');
    }
  })();
})();
