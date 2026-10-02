/* Main application: auth, routing, list + conversation views, labels, settings, live updates. */

const App = {
  user: null, config: null, labels: [], counts: { inbox: 0, drafts: 0, spam: 0, labels: {} },
  route: null, list: null, thread: null, selected: new Set(), expanded: new Set(), showImg: new Set(), seq: 0,
  refresh: async () => {},
};

const FOLDERS = [
  { id: 'inbox', name: 'Inbox', icon: 'inbox', empty: 'Your inbox is clear.' },
  { id: 'starred', name: 'Starred', icon: 'star', empty: 'Star a conversation to find it here quickly.' },
  { id: 'sent', name: 'Sent', icon: 'send', empty: 'Messages you send show up here.' },
  { id: 'drafts', name: 'Drafts', icon: 'drafts', empty: 'No drafts. Anything you start writing is saved automatically.' },
  { id: 'all', name: 'All Mail', icon: 'all', empty: 'No mail yet.' },
  { id: 'spam', name: 'Spam', icon: 'spam', empty: 'No spam. Nice.' },
  { id: 'trash', name: 'Trash', icon: 'trash', empty: 'Trash is empty.' },
];
const REAL_FOLDERS = ['inbox', 'sent', 'drafts', 'spam', 'trash'];
const main = $('#main');

// ======================================================= auth

let authMode = 'login';
function showAuth() {
  closeEvents();
  App.user = null;
  $('#app').hidden = true;
  $('#auth').hidden = false;
  composeWins.forEach((c) => removeComposeWindow(c));
  setAuthMode('login');
  $('#authForm [name=username]').focus();
}

function setAuthMode(mode) {
  authMode = mode;
  const reg = mode === 'register';
  $$('.reg-only').forEach((el) => (el.hidden = !reg));
  $('#authTitle').textContent = reg ? 'Create your account' : 'Sign in';
  $('#authIdLabel').textContent = reg ? 'Choose an address' : 'Email';
  $('#authSubmit').textContent = reg ? 'Create account' : 'Sign in';
  $('#authSwitchText').textContent = reg ? 'Already have an account?' : 'New here?';
  $('#authSwitch').textContent = reg ? 'Sign in' : 'Create an account';
  $('#authSwitch').parentElement.hidden = !reg && !(App.config && App.config.allowSignup);
  $('#authForm [name=password]').autocomplete = reg ? 'new-password' : 'current-password';
  $('#authForm [name=name]').required = reg;
  $('#authError').textContent = '';
}

$('#authSwitch').addEventListener('click', () => setAuthMode(authMode === 'login' ? 'register' : 'login'));
$('#authForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  const btn = $('#authSubmit');
  btn.disabled = true;
  $('#authError').textContent = '';
  try {
    const body = authMode === 'login' ? { email: f.username, password: f.password } : { username: f.username, name: f.name, password: f.password };
    App.user = await api(`/api/auth/${authMode === 'login' ? 'login' : 'register'}`, { method: 'POST', body });
    e.target.reset();
    startApp();
  } catch (err) {
    $('#authError').textContent = err.message;
  } finally {
    btn.disabled = false;
  }
});

window.addEventListener('signed-out', () => { if (App.user) showAuth(); });

async function signOut() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
  closeDialog();
  showAuth();
}

// ======================================================= boot

async function boot() {
  paintIcons();
  try { App.config = await api('/api/config'); } catch { App.config = { appName: 'Mail', domain: 'localhost', allowSignup: true }; }
  $$('.app-name').forEach((el) => (el.textContent = App.config.appName));
  $('.domain-suffix').textContent = '@' + App.config.domain;
  try {
    App.user = await api('/api/me');
    startApp();
  } catch {
    showAuth();
  }
}

async function startApp() {
  $('#auth').hidden = true;
  $('#app').hidden = false;
  $('#avatarBtn').textContent = initial(App.user);
  $('#avatarBtn').title = App.user.email;
  App.route = null; App.list = null; App.thread = null; App.selected.clear();
  await Promise.all([loadLabels(), loadCounts()]);
  connectEvents();
  if (!location.hash) location.hash = '#/inbox';
  onRoute();
}

// ======================================================= live updates

let events = null;
function connectEvents() {
  closeEvents();
  events = new EventSource('/api/events');
  events.onmessage = () => queueRefresh();
}
function closeEvents() { if (events) { events.close(); events = null; } }
const queueRefresh = debounce(() => App.refresh(), 300);

App.refresh = async () => {
  if (!App.user) return;
  await Promise.all([loadCounts(), App.route && (App.route.thread ? loadThread({ quiet: true }) : loadList())]);
};
document.addEventListener('visibilitychange', () => { if (!document.hidden) App.refresh(); });

// ======================================================= data loading

async function loadLabels() {
  try { App.labels = await api('/api/labels'); } catch { /* keep old */ }
  renderSidebar();
}
async function loadCounts() {
  try { App.counts = await api('/api/counts'); } catch { return; }
  renderSidebar();
}

// ======================================================= routing

function parseRoute() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter((x) => x !== '').map(decodeURIComponent);
  let view = parts.shift() || 'inbox';
  if (!FOLDERS.some((f) => f.id === view) && view !== 'search' && view !== 'label') view = 'inbox';
  const r = { view, arg: null, page: 1, thread: null };
  if (view === 'search' || view === 'label') r.arg = parts.shift() ?? '';
  while (parts.length) {
    const p = parts.shift();
    if (p === 't') r.thread = parts.shift() || null;
    else if (/^p\d+$/.test(p)) r.page = Number(p.slice(1));
  }
  return r;
}

function hashFor(r) {
  let h = '#/' + r.view;
  if (r.view === 'search' || r.view === 'label') h += '/' + encodeURIComponent(r.arg ?? '');
  if (r.page > 1) h += '/p' + r.page;
  if (r.thread) h += '/t/' + encodeURIComponent(r.thread);
  return h;
}

function navigate(patch) { location.hash = hashFor({ ...App.route, ...patch }); }

async function onRoute() {
  if (!App.user) return;
  const prev = App.route;
  App.route = parseRoute();
  const r = App.route;
  closeMenu(); closeNav();
  if (!prev || prev.view !== r.view || prev.arg !== r.arg || prev.page !== r.page) App.selected.clear();
  if (!prev || prev.thread !== r.thread) { App.thread = null; App.expanded = new Set(); }
  $('#searchInput').value = r.view === 'search' ? r.arg : '';
  renderSidebar();
  if (!prev || prev.view !== r.view || prev.arg !== r.arg || prev.thread !== r.thread) main.innerHTML = '<div class="empty">Loading…</div>';
  if (r.thread) await loadThread(); else await loadList();
}
window.addEventListener('hashchange', onRoute);

$('#searchForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const q = $('#searchInput').value.trim();
  location.hash = q ? `#/search/${encodeURIComponent(q)}` : '#/inbox';
  $('#searchInput').blur();
});

// ======================================================= sidebar

const closeNav = () => $('#app').classList.remove('nav-open');

function viewLabel() {
  const r = App.route;
  if (!r) return 'Mail';
  if (r.view === 'search') return 'Search';
  if (r.view === 'label') return (App.labels.find((l) => String(l.id) === r.arg) || {}).name || 'Label';
  return FOLDERS.find((f) => f.id === r.view).name;
}

function renderSidebar() {
  const r = App.route || {};
  const c = App.counts;
  $('#folderList').innerHTML = FOLDERS.map((f) => {
    const n = f.id === 'inbox' ? c.inbox : f.id === 'drafts' ? c.drafts : f.id === 'spam' ? c.spam : 0;
    return `<li><a class="nav-item${r.view === f.id ? ' active' : ''}" href="#/${f.id}"${r.view === f.id ? ' aria-current="page"' : ''}>${icon(f.icon)}<span class="nm">${f.name}</span>${n ? `<span class="count">${n}</span>` : ''}</a></li>`;
  }).join('');
  $('#labelList').innerHTML =
    App.labels.map((l) => {
      const n = c.labels && c.labels[l.id];
      const active = r.view === 'label' && r.arg === String(l.id);
      return `<li><a class="nav-item${active ? ' active' : ''}" href="#/label/${l.id}"><span class="dot" style="background:${esc(l.color)}"></span><span class="nm">${esc(l.name)}</span>${n ? `<span class="count">${n}</span>` : ''}</a></li>`;
    }).join('') || '<li class="hint" style="padding:6px 16px">No labels yet</li>';
  document.title = `${c.inbox ? `(${c.inbox}) ` : ''}${viewLabel()} – ${(App.config && App.config.appName) || 'Mail'}`;
}

// ======================================================= list view

const scopeFor = () => (App.route && REAL_FOLDERS.includes(App.route.view) ? App.route.view : 'all');

async function loadList() {
  const r = App.route;
  const seq = ++App.seq;
  const qs = new URLSearchParams({ view: r.view === 'label' ? 'label:' + r.arg : r.view, page: r.page });
  if (r.view === 'search') qs.set('q', r.arg);
  let data;
  try { data = await api('/api/threads?' + qs); } catch (e) {
    if (seq === App.seq) main.innerHTML = `<div class="empty"><h3>Couldn’t load mail</h3><p>${esc(e.message)}</p><button class="btn" data-act="refresh">Try again</button></div>`;
    return;
  }
  if (seq !== App.seq) return;
  if (data.total && !data.threads.length && r.page > 1) return navigate({ page: 1 });
  App.list = data;
  renderList();
}

function senderText(t) {
  if (t.folder === 'drafts') return '<span class="draft-tag">Draft</span>';
  if (App.route.view === 'sent') return 'To: ' + esc(t.to.map(displayName).join(', ') || '(no recipients)');
  const names = t.senders.map((s) => (s.address === App.user.email ? 'me' : displayName(s))).filter(Boolean);
  const uniq = [...new Set(names)];
  const shown = uniq.length > 3 ? [uniq[0], '…', ...uniq.slice(-2)] : uniq;
  return esc(shown.join(', ')) + (t.count > 1 ? `<span class="n">${t.count}</span>` : '');
}

const chipsFor = (ids) => ids.map((id) => App.labels.find((l) => l.id === id)).filter(Boolean).map((l) => `<span class="chip" style="background:${esc(l.color)}">${esc(l.name)}</span>`).join('');

function rowHtml(t) {
  const sel = App.selected.has(t.key);
  return `<li class="row${t.unread ? ' unread' : ''}${sel ? ' selected' : ''}" data-act="open" data-key="${esc(t.key)}" data-id="${t.id}" data-thread="${esc(t.threadId)}" data-folder="${t.folder}">
    <input type="checkbox" class="chk" data-act="sel" aria-label="Select conversation"${sel ? ' checked' : ''}>
    <button class="star-btn${t.starred ? ' on' : ''}" data-act="star" aria-label="${t.starred ? 'Unstar' : 'Star'}">${icon('star')}</button>
    <div class="from">${senderText(t)}</div>
    <div class="mid">${chipsFor(t.labelIds)}<span class="subject">${esc(t.subject || '(no subject)')}</span><span class="snip">${esc(t.snippet)}</span></div>
    <div class="meta">${t.hasAttachments ? icon('clip') : ''}<span class="date">${fmtListDate(t.date)}</span></div>
  </li>`;
}

function toolbarButtons() {
  const v = App.route.view;
  const b = (act, ic, label) => `<button class="icon-btn" data-act="${act}" aria-label="${label}" title="${label}">${icon(ic)}</button>`;
  if (App.selected.size === 0) return '';
  if (v === 'trash') return b('restore', 'restore', 'Restore') + b('delete', 'trash', 'Delete forever');
  if (v === 'spam') return b('notspam', 'inbox', 'Not spam') + b('delete', 'trash', 'Delete forever');
  if (v === 'drafts') return b('delete', 'trash', 'Discard drafts');
  return (v === 'sent' ? '' : b('archive', 'archive', 'Archive')) + b('spam', 'spam', 'Report spam') + b('trash', 'trash', 'Move to Trash') +
    b('read', 'mailopen', 'Mark as read') + b('unread', 'mail', 'Mark as unread') + `<button class="icon-btn" data-act="label" aria-label="Labels" title="Labels">${icon('tag')}</button>`;
}

function toolbarHtml() {
  const { threads, total, page, pageSize } = App.list;
  const sel = App.selected.size;
  const from = total ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(page * pageSize, total);
  return `<input type="checkbox" class="chk" data-act="select-all" aria-label="Select all"${sel && sel === threads.length ? ' checked' : ''}>
    <button class="icon-btn" data-act="refresh" aria-label="Refresh" title="Refresh">${icon('refresh')}</button>
    ${toolbarButtons()}
    <span class="spacer"></span>
    ${total ? `<span class="pager">${from}–${to} of ${total}</span>` : ''}
    <button class="icon-btn" data-act="page-prev" aria-label="Newer"${page <= 1 ? ' disabled' : ''}>${icon('left')}</button>
    <button class="icon-btn" data-act="page-next" aria-label="Older"${to >= total ? ' disabled' : ''}>${icon('right')}</button>`;
}

function updateToolbar() {
  const tb = $('.toolbar', main);
  if (!tb || !App.list) return;
  tb.innerHTML = toolbarHtml();
  const cb = $('[data-act=select-all]', tb);
  cb.indeterminate = App.selected.size > 0 && App.selected.size < App.list.threads.length;
}

function renderList() {
  const { threads, total } = App.list;
  const r = App.route;
  const keys = threads.map((t) => t.key);
  App.selected = new Set([...App.selected].filter((k) => keys.includes(k)));
  const prevScroll = $('.list', main) ? $('.scroll', main).scrollTop : 0; // only keep scroll when refreshing the same list
  closeMenu();

  let banner = '';
  if ((r.view === 'trash' || r.view === 'spam') && total) banner = `<div class="banner">${r.view === 'trash' ? 'Trash' : 'Spam'} is kept until you delete it. <button class="link" data-act="empty-folder">Empty ${r.view} now</button></div>`;
  if (r.view === 'search') banner = `<div class="banner">${total} result${total === 1 ? '' : 's'} for <b>${esc(r.arg)}</b></div>`;

  let body;
  if (!threads.length) {
    const f = FOLDERS.find((x) => x.id === r.view);
    body = `<div class="empty">${icon(r.view === 'search' ? 'search' : (f ? f.icon : 'tag'))}<h3>${r.view === 'search' ? 'No results' : r.view === 'label' ? 'Nothing with this label' : 'Nothing here'}</h3><p>${r.view === 'search' ? 'Try fewer words, or filters like from:name or has:attachment.' : r.view === 'label' ? 'Apply this label to conversations from the tag button.' : esc(f.empty)}</p></div>`;
  } else body = `<ul class="list">${threads.map(rowHtml).join('')}</ul>`;

  main.innerHTML = `<div class="toolbar"></div>${banner}<div class="scroll">${body}</div>`;
  updateToolbar();
  $('.scroll', main).scrollTop = prevScroll;
}

// ======================================================= actions on conversations

function plural(n) { return n === 1 ? 'Conversation' : `${n} conversations`; }

const UNDO = {
  trash: { action: 'restore', scope: 'trash', msg: (n) => `${plural(n)} moved to Trash` },
  archive: { action: 'inbox', scope: 'archive', msg: (n) => `${plural(n)} archived` },
  spam: { action: 'notspam', scope: 'spam', msg: (n) => `${plural(n)} reported as spam` },
};
const SIMPLE_MSG = {
  restore: (n) => `${plural(n)} restored`, notspam: (n) => `${plural(n)} moved to Inbox`, delete: (n) => `${plural(n)} deleted forever`,
  read: () => 'Marked as read', unread: () => 'Marked as unread', label: () => 'Label applied', unlabel: () => 'Label removed',
};

async function doBatch(action, keys, { labelId, scope, silent = false, leaveThread = false } = {}) {
  if (!keys.length) return;
  try {
    await api('/api/threads/batch', { method: 'POST', body: { action, threads: keys, scope: scope || scopeFor(), labelId } });
  } catch (e) {
    return toast(e.message, { error: true });
  }
  App.selected.clear();
  if (!silent) {
    const u = UNDO[action];
    if (u) toast(u.msg(keys.length), { action: 'Undo', onAction: () => doBatch(u.action, keys, { scope: u.scope, silent: true }), ms: 7000 });
    else if (SIMPLE_MSG[action]) toast(SIMPLE_MSG[action](keys.length));
  }
  if (leaveThread && App.route.thread) navigate({ thread: null });
  else App.refresh();
}

function openLabelMenu(anchor, infos, keys) {
  if (!App.labels.length) { openLabelsDialog(); return; }
  const items = App.labels.map((l) => {
    const all = infos.length > 0 && infos.every((t) => t.labelIds.includes(l.id));
    return { label: l.name, dot: l.color, checkable: true, on: all, onClick: () => doBatch(all ? 'unlabel' : 'label', keys, { labelId: l.id }) };
  });
  items.push('hr', { label: 'Manage labels…', onClick: openLabelsDialog });
  showMenu(anchor, items);
}

function selectedInfos() { return App.list.threads.filter((t) => App.selected.has(t.key)); }

main.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el) return;
  const act = el.dataset.act;
  const row = el.closest('.row');
  const keys = [...App.selected];

  switch (act) {
    case 'sel': {
      const key = row.dataset.key;
      if (el.checked) App.selected.add(key); else App.selected.delete(key);
      row.classList.toggle('selected', el.checked);
      updateToolbar();
      return;
    }
    case 'select-all': {
      if (el.checked) App.list.threads.forEach((t) => App.selected.add(t.key)); else App.selected.clear();
      $$('.row', main).forEach((r) => { const on = App.selected.has(r.dataset.key); r.classList.toggle('selected', on); $('.chk', r).checked = on; });
      updateToolbar();
      return;
    }
    case 'open':
      if (row.dataset.folder === 'drafts') editDraft(Number(row.dataset.id));
      else navigate({ thread: row.dataset.thread });
      return;
    case 'star': {
      e.stopPropagation();
      const t = App.list.threads.find((x) => x.key === row.dataset.key);
      const on = !t.starred;
      t.starred = on;
      el.classList.toggle('on', on);
      doBatch(on ? 'star' : 'unstar', [row.dataset.key], { silent: true });
      return;
    }
    case 'refresh': App.refresh(); return;
    case 'page-prev': navigate({ page: App.route.page - 1 }); return;
    case 'page-next': navigate({ page: App.route.page + 1 }); return;
    case 'archive': case 'spam': case 'trash': case 'restore': case 'notspam': case 'delete': case 'read': case 'unread':
      if (act === 'delete' && !confirm(`Delete ${keys.length === 1 ? 'this conversation' : keys.length + ' conversations'} forever? This can’t be undone.`)) return;
      doBatch(act, keys);
      return;
    case 'label': openLabelMenu(el, selectedInfos(), keys); return;
    case 'empty-folder':
      if (confirm(`Delete everything in ${App.route.view} forever?`)) {
        api(`/api/folders/${App.route.view}/empty`, { method: 'POST' }).then(() => { toast('Emptied'); App.refresh(); }, (err) => toast(err.message, { error: true }));
      }
      return;
    default: threadAct(act, el, e);
  }
});

// ======================================================= conversation view

async function loadThread({ quiet = false } = {}) {
  const r = App.route;
  const seq = ++App.seq;
  let data;
  try {
    data = await api(`/api/threads/${encodeURIComponent(r.thread)}${r.view === 'trash' || r.view === 'spam' ? '?view=' + r.view : ''}`);
  } catch (e) {
    if (seq !== App.seq) return;
    if (quiet) return navigate({ thread: null });
    main.innerHTML = `<div class="toolbar"><button class="icon-btn" data-act="back" aria-label="Back">${icon('left')}</button></div><div class="empty">${icon('mail')}<h3>Conversation not found</h3><p>It may have been moved or deleted.</p></div>`;
    return;
  }
  if (seq !== App.seq) return;
  const sig = data.messages.map((m) => `${m.id}:${m.starred}:${m.folder}`).join(',') + '|' + data.labelIds.join(',') + '|' + data.subject;
  if (quiet && App.thread && App.thread.sig === sig) return;
  data.sig = sig;
  const firstLoad = !App.thread;
  // Expand the newest message and anything unread; keep what the person already opened
  data.messages.forEach((m, i) => { if (m.folder !== 'drafts' && (m.unread || i === data.messages.length - 1) && (firstLoad || m.unread)) App.expanded.add(m.id); });
  App.thread = data;
  renderThread();
}

const threadScope = () => scopeFor();
const threadInfo = () => [{ labelIds: App.thread.labelIds }];

function recipientsSummary(m) {
  const all = [...m.to, ...m.cc];
  if (!all.length) return 'no recipients';
  const names = all.map((p) => (p.address === App.user.email ? 'me' : displayName(p)));
  return 'to ' + names.slice(0, 3).join(', ') + (names.length > 3 ? ` +${names.length - 3}` : '');
}

/** Remote images can track readers, so they stay hidden until the person asks. */
function blockRemote(html) {
  const doc = new DOMParser().parseFromString(html, 'text/html'); // inert: nothing loads or runs
  let n = 0;
  doc.querySelectorAll('img[src]').forEach((img) => {
    if (/^https?:/i.test(img.getAttribute('src'))) { img.removeAttribute('src'); n++; }
  });
  doc.querySelectorAll('[style]').forEach((el) => {
    const s = el.getAttribute('style');
    if (/url\(/i.test(s)) { el.setAttribute('style', s.replace(/url\([^)]*\)/gi, 'none')); n++; }
  });
  return { html: doc.body.innerHTML, blocked: n };
}

function emailDoc(html) {
  return `<!doctype html><html><head><meta charset="utf-8"><base target="_blank"><style>
html,body{margin:0;padding:0}
body{padding:14px 16px;font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#1c2524;overflow-wrap:anywhere}
img{max-width:100%;height:auto}table{max-width:100%}pre{white-space:pre-wrap}a{color:#0f766e}
blockquote{margin:8px 0 8px 2px;padding-left:12px;border-left:3px solid #cfd9d7;color:#55625f}
</style></head><body>${html}</body></html>`;
}

function fitFrame(f) {
  const d = f.contentDocument;
  if (!d || !d.documentElement) return;
  const fit = () => { f.style.height = d.documentElement.scrollHeight + 'px'; };
  fit();
  d.querySelectorAll('img').forEach((img) => img.addEventListener('load', fit, { once: true }));
}
window.addEventListener('resize', debounce(() => $$('.msg-body iframe').forEach(fitFrame), 150));

function msgHtml(m) {
  const t = App.thread;
  const open = App.expanded.has(m.id);
  const star = `<button class="star-btn${m.starred ? ' on' : ''}" data-act="star-msg" data-mid="${m.id}" aria-label="${m.starred ? 'Unstar' : 'Star'} message">${icon('star')}</button>`;
  const avatar = `<div class="avatar-sm" aria-hidden="true">${esc(initial(m.from))}</div>`;

  if (m.folder === 'drafts') {
    return `<article class="msg is-draft" data-mid="${m.id}"><div class="msg-head">${avatar}<div class="msg-who"><div class="name"><span style="color:var(--danger)">Draft</span></div><div class="sub">${esc(recipientsSummary(m))} – ${esc(makeSnip(m.text))}</div></div><button class="btn" data-act="edit-draft" data-mid="${m.id}">Edit draft</button></div></article>`;
  }
  if (!open) {
    return `<article class="msg collapsed" data-act="expand" data-mid="${m.id}"><div class="msg-head">${avatar}<div class="msg-who"><div class="name">${esc(displayName(m.from))}${m.unread ? ' <span class="chip">New</span>' : ''}</div><div class="sub">${esc(makeSnip(m.text))}</div></div><span class="msg-date">${esc(fmtListDate(m.date))}</span></div></article>`;
  }
  const own = m.folder === 'sent';
  const prep = blockRemote(m.html);
  m._hidden = !own && !App.showImg.has(m.id) ? prep.blocked : 0;
  const details = App.showDetails && App.showDetails.has(m.id)
    ? `<div class="msg-details"><b>from:</b><span>${esc(fmtAddr(m.from))}</span><b>to:</b><span>${esc(m.to.map(fmtAddr).join(', ') || '—')}</span>${m.cc.length ? `<b>cc:</b><span>${esc(m.cc.map(fmtAddr).join(', '))}</span>` : ''}${m.bcc.length ? `<b>bcc:</b><span>${esc(m.bcc.map(fmtAddr).join(', '))}</span>` : ''}<b>date:</b><span>${esc(fmtLongDate(m.date))}</span><b>subject:</b><span>${esc(m.subject)}</span></div>` : '';
  const atts = m.attachments.length
    ? `<div class="atts">${m.attachments.map((a) => `<a class="att" href="/api/attachments/${a.id}?download=1" download>${icon('clip')}<span>${esc(a.filename)}</span><small>${fmtSize(a.size)}</small></a>`).join('')}</div>` : '';
  return `<article class="msg" data-mid="${m.id}">
    <div class="msg-head" data-act="collapse" data-mid="${m.id}">${avatar}
      <div class="msg-who"><div><span class="name">${esc(displayName(m.from))}</span><span class="addr">&lt;${esc(m.from.address)}&gt;</span></div>
        <div class="sub">${esc(recipientsSummary(m))} <button data-act="details" data-mid="${m.id}">details</button></div></div>
      <span class="msg-date">${esc(fmtLongDate(m.date))}</span>${star}
      <button class="icon-btn sm" data-act="reply" data-mid="${m.id}" aria-label="Reply" title="Reply">${icon('reply')}</button>
      <button class="icon-btn sm" data-act="msgmenu" data-mid="${m.id}" aria-label="More" title="More">${icon('more')}</button>
    </div>${details}
    ${m._hidden ? `<div class="img-bar">Images in this message are hidden to protect your privacy. <button class="link" data-act="showimg" data-mid="${m.id}">Show images</button></div>` : ''}
    <div class="msg-body" data-body="${m.id}"></div>${atts}
  </article>`;
}

const makeSnip = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 120);

function renderThread() {
  const t = App.thread;
  const prevScroll = $('.thread', main) ? $('.scroll', main).scrollTop : 0;
  closeMenu();
  const v = App.route.view;
  const b = (act, ic, label) => `<button class="icon-btn" data-act="${act}" aria-label="${label}" title="${label}">${icon(ic)}</button>`;
  let actions;
  if (v === 'trash') actions = b('t-restore', 'restore', 'Restore') + b('t-delete', 'trash', 'Delete forever');
  else if (v === 'spam') actions = b('t-notspam', 'inbox', 'Not spam') + b('t-delete', 'trash', 'Delete forever');
  else actions = (v === 'sent' ? '' : b('t-archive', 'archive', 'Archive')) + b('t-spam', 'spam', 'Report spam') + b('t-trash', 'trash', 'Move to Trash') + b('t-unread', 'mail', 'Mark as unread') + b('t-label', 'tag', 'Labels');

  const lastReal = [...t.messages].reverse().find((m) => m.folder !== 'drafts');
  main.innerHTML = `
    <div class="toolbar"><button class="icon-btn" data-act="back" aria-label="Back to list" title="Back">${icon('left')}</button>${actions}</div>
    <div class="scroll"><div class="thread">
      <div class="thread-head"><h2>${esc(t.subject)}</h2>${t.labelIds.map((id) => App.labels.find((l) => l.id === id)).filter(Boolean).map((l) => `<span class="chip" style="background:${esc(l.color)}">${esc(l.name)}<button data-act="rmlabel" data-label="${l.id}" aria-label="Remove label ${esc(l.name)}">${icon('x')}</button></span>`).join('')}</div>
      ${t.messages.map(msgHtml).join('')}
      ${lastReal ? `<div class="reply-bar"><button class="btn" data-act="reply" data-mid="${lastReal.id}">${icon('reply')} Reply</button><button class="btn" data-act="replyall" data-mid="${lastReal.id}">${icon('replyall')} Reply all</button><button class="btn" data-act="forward" data-mid="${lastReal.id}">${icon('forward')} Forward</button></div>` : ''}
    </div></div>`;

  $$('.msg-body[data-body]', main).forEach((box) => {
    const m = t.messages.find((x) => String(x.id) === box.dataset.body);
    const showAll = m.folder === 'sent' || App.showImg.has(m.id);
    const f = document.createElement('iframe');
    f.setAttribute('sandbox', 'allow-same-origin allow-popups allow-popups-to-escape-sandbox'); // no scripts, ever
    f.title = 'Message from ' + displayName(m.from);
    f.srcdoc = emailDoc(showAll ? m.html : blockRemote(m.html).html);
    f.addEventListener('load', () => fitFrame(f));
    box.append(f);
  });
  $('.scroll', main).scrollTop = prevScroll;
}

function threadAct(act, el, e) {
  const t = App.thread;
  const mid = el.dataset.mid && Number(el.dataset.mid);
  const msg = mid && t && t.messages.find((m) => m.id === mid);
  const keys = t ? [t.threadId] : [];

  switch (act) {
    case 'back': navigate({ thread: null }); break;
    case 'expand': App.expanded.add(mid); renderThread(); break;
    case 'collapse':
      if (e.target.closest('button, a')) return;
      if (t.messages.length > 1) { App.expanded.delete(mid); renderThread(); }
      break;
    case 'details':
      (App.showDetails ||= new Set());
      if (App.showDetails.has(mid)) App.showDetails.delete(mid); else App.showDetails.add(mid);
      renderThread();
      break;
    case 'showimg': App.showImg.add(mid); renderThread(); break;
    case 'reply': startReply(msg, t); break;
    case 'replyall': startReply(msg, t, true); break;
    case 'forward': startForward(msg, t); break;
    case 'edit-draft': editDraft(mid); break;
    case 'msgmenu':
      showMenu(el, [
        { label: 'Reply', icon: 'reply', onClick: () => startReply(msg, t) },
        { label: 'Reply all', icon: 'replyall', onClick: () => startReply(msg, t, true) },
        { label: 'Forward', icon: 'forward', onClick: () => startForward(msg, t) },
      ]);
      break;
    case 'star-msg': {
      e.stopPropagation();
      const on = !msg.starred;
      msg.starred = on;
      el.classList.toggle('on', on);
      api('/api/threads/batch', { method: 'POST', body: { action: on ? 'star' : 'unstar', threads: [t.threadId], scope: 'all' } }).then(() => App.refresh(), (err) => toast(err.message, { error: true }));
      break;
    }
    case 'rmlabel': doBatch('unlabel', keys, { labelId: Number(el.dataset.label), scope: 'all' }).then(() => loadThread()); break;
    case 't-archive': doBatch('archive', keys, { leaveThread: true }); break;
    case 't-spam': doBatch('spam', keys, { leaveThread: true }); break;
    case 't-trash': doBatch('trash', keys, { leaveThread: true }); break;
    case 't-restore': doBatch('restore', keys, { leaveThread: true }); break;
    case 't-notspam': doBatch('notspam', keys, { leaveThread: true }); break;
    case 't-delete':
      if (confirm('Delete this conversation forever? This can’t be undone.')) doBatch('delete', keys, { leaveThread: true });
      break;
    case 't-unread': doBatch('unread', keys, { leaveThread: true, silent: true }).then(() => toast('Marked as unread')); break;
    case 't-label': openLabelMenu(el, threadInfo(), keys); break;
  }
}

// ======================================================= labels dialog

function openLabelsDialog() {
  closeMenu();
  const draw = () => openDialog(`
    <h3>Labels</h3>
    <p class="hint">Use labels to organise conversations. A conversation can have several.</p>
    <div id="lblRows" style="display:grid;gap:8px">
      ${App.labels.map((l) => `<div class="lbl-row" data-id="${l.id}"><input type="color" value="${esc(l.color)}" aria-label="Colour for ${esc(l.name)}"><input type="text" value="${esc(l.name)}" maxlength="40" aria-label="Label name"><button class="icon-btn" data-del aria-label="Delete label ${esc(l.name)}">${icon('trash')}</button></div>`).join('')}
    </div>
    <form class="lbl-row" id="lblNew"><input type="color" value="#0f766e" aria-label="Colour"><input type="text" placeholder="New label name" maxlength="40" required aria-label="New label name"><button class="btn primary" type="submit">Add</button></form>
    <p class="error" id="lblErr"></p>
    <div class="dlg-foot"><button class="btn" data-close>Done</button></div>`,
  (d) => {
    $('[data-close]', d).onclick = closeDialog;
    const fail = (e) => { $('#lblErr', d).textContent = e.message; };
    $('#lblNew', d).onsubmit = async (e) => {
      e.preventDefault();
      const [color, name] = $$('input', e.target);
      try { await api('/api/labels', { method: 'POST', body: { name: name.value, color: color.value } }); await loadLabels(); draw(); } catch (err) { fail(err); }
    };
    $$('.lbl-row[data-id]', d).forEach((row) => {
      const id = row.dataset.id;
      const [color, name] = $$('input', row);
      const save = async () => { try { await api('/api/labels/' + id, { method: 'PUT', body: { name: name.value, color: color.value } }); await loadLabels(); App.refresh(); } catch (err) { fail(err); } };
      color.onchange = save;
      name.onchange = save;
      $('[data-del]', row).onclick = async () => {
        if (!confirm(`Delete the label “${name.value}”? Conversations keep their messages.`)) return;
        try { await api('/api/labels/' + id, { method: 'DELETE' }); await loadLabels(); App.refresh(); draw(); } catch (err) { fail(err); }
      };
    });
  });
  draw();
}

// ======================================================= settings

function openSettings() {
  openDialog(`
    <h3>Settings</h3>
    <p class="hint">Signed in as <b>${esc(App.user.email)}</b></p>
    <label class="field">Display name<input id="setName" value="${esc(App.user.name)}" maxlength="80"></label>
    <label class="field">Signature<textarea id="setSig" maxlength="2000" placeholder="Added to new messages and replies">${esc(App.user.signature)}</textarea></label>
    <details><summary>Change password</summary>
      <div style="display:grid;gap:10px;margin-top:10px">
        <label class="field">Current password<input id="setCur" type="password" autocomplete="current-password"></label>
        <label class="field">New password (8+ characters)<input id="setNew" type="password" autocomplete="new-password" minlength="8"></label>
      </div></details>
    <p class="hint">Shortcuts: <b>c</b> compose · <b>/</b> search · <b>e</b> archive · <b>#</b> trash · <b>r</b> reply · <b>g</b> then <b>i</b> inbox · <b>Ctrl/⌘+Enter</b> send</p>
    <p class="error" id="setErr"></p>
    <div class="dlg-foot"><button class="btn" id="setOut">${icon('logout')} Sign out</button><span style="flex:1"></span><button class="btn" data-close>Cancel</button><button class="btn primary" id="setSave">Save</button></div>`,
  (d) => {
    $('[data-close]', d).onclick = closeDialog;
    $('#setOut', d).onclick = signOut;
    $('#setSave', d).onclick = async () => {
      const body = { name: $('#setName', d).value, signature: $('#setSig', d).value };
      if ($('#setNew', d).value) { body.newPassword = $('#setNew', d).value; body.currentPassword = $('#setCur', d).value; }
      try {
        App.user = await api('/api/me', { method: 'PUT', body });
        $('#avatarBtn').textContent = initial(App.user);
        closeDialog();
        toast('Settings saved');
      } catch (err) { $('#setErr', d).textContent = err.message; }
    };
  });
}

// ======================================================= global clicks & keyboard

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  switch (el.dataset.action) {
    case 'compose': closeNav(); openCompose(); break;
    case 'toggle-nav': $('#app').classList.toggle('nav-open'); break;
    case 'close-nav': closeNav(); break;
    case 'open-settings': openSettings(); break;
    case 'manage-labels': openLabelsDialog(); break;
  }
});

let gPending = false;
document.addEventListener('keydown', (e) => {
  if (!App.user || e.ctrlKey || e.metaKey || e.altKey) return;
  const tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable || $('#dialog').open) {
    if (e.key === 'Escape' && e.target.id === 'searchInput') e.target.blur();
    return;
  }
  const r = App.route;
  if (gPending) {
    gPending = false;
    const dest = { i: 'inbox', s: 'starred', t: 'sent', d: 'drafts', a: 'all' }[e.key];
    if (dest) location.hash = '#/' + dest;
    return;
  }
  const inThread = r && r.thread && App.thread;
  const last = inThread && [...App.thread.messages].reverse().find((m) => m.folder !== 'drafts');
  switch (e.key) {
    case 'c': e.preventDefault(); openCompose(); break;
    case '/': e.preventDefault(); $('#searchInput').focus(); break;
    case 'g': gPending = true; setTimeout(() => (gPending = false), 1000); break;
    case 'u': case 'Escape': if (inThread) navigate({ thread: null }); break;
    case 'r': if (last) { e.preventDefault(); startReply(last, App.thread); } break;
    case 'a': if (last) { e.preventDefault(); startReply(last, App.thread, true); } break;
    case 'f': if (last) { e.preventDefault(); startForward(last, App.thread); } break;
    case 'e': if (inThread) doBatch('archive', [App.thread.threadId], { leaveThread: true }); else if (App.selected.size && r.view !== 'sent') doBatch('archive', [...App.selected]); break;
    case '#': case 'Delete': if (inThread) doBatch('trash', [App.thread.threadId], { leaveThread: true }); else if (App.selected.size) doBatch('trash', [...App.selected]); break;
  }
});

boot();
