/* Main app: accounts, library, rendering, info modal, settings, events */

/* ---------- accounts ---------- */
let signupOK = true;
async function boot() {
  const r = await api('/api/auth/me'); signupOK = r.signup;
  r.user ? start(r.user) : showLogin();
}
function showLogin() { $('#login').hidden = false; $('#suBtn').hidden = !signupOK; $('#ln').focus(); }
async function authReq(kind) {
  const r = await fetch('/api/auth/' + kind, {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: $('#ln').value, pw: $('#lp').value})});
  const j = await r.json();
  if (!r.ok) { $('#lerr').textContent = j.error || 'Something went wrong'; return; }
  start(j.user);
}
async function start(u) {
  me = u; $('#login').hidden = true; $('#lerr').textContent = '';
  const s = await api('/api/state');
  st = {prog: {}, list: [], watched: [], hist: [], rate: {}, pl: [], ...s,
    set: {auto: true, subs: false, acc: '#7c5cff', rate: 1, vol: 1, q: 'orig', ...s.set}};
  document.documentElement.style.setProperty('--acc', st.set.acc);
  const av = $('#av'); av.textContent = u.name[0].toUpperCase(); av.style.background = `hsl(${hue(u.name)} 60% 42%)`;
  await loadLib(true);
}

/* ---------- library (fetched on page load; the server scans only at startup) ---------- */
async function loadLib(first) {
  [lib, META] = await Promise.all([api('/api/library'), api('/api/meta')]);
  build();
  if (first) {
    pick = T.filter(t => !t.done).sort(() => Math.random() - .5).slice(0, 12).map(t => t.key);
    const rc = recommend(5); feat = (rc.length ? rc.map(t => t.key) : pick).slice(0, 5);
  }
  hero(); render();
}
function build() {
  const m = new Map();
  lib.filter(i => !i.dup_of).forEach(i => { (m.get(i.key) || m.set(i.key, []).get(i.key)).push(i); });   // duplicates are hidden
  T = [...m].map(([key, eps]) => {
    eps.sort((a, b) => (a.season || 0) - (b.season || 0) || (a.ep || 0) - (b.ep || 0) || a.title.localeCompare(b.title));
    const ip = eps.filter(pr).sort((a, b) => st.prog[b.id].ts - st.prog[a.id].ts)[0], s = !!eps[0].series, mt = META[key] || {};
    return {key, eps, s, meta: mt, genres: mt.genres || [], art: mt.backdrop ? '/api/img/' + mt.backdrop : '',
      rep: ip || eps.find(e => !seen(e.id)) || eps[0], title: s ? eps[0].series : eps[0].title, cat: eps[0].category,
      added: Math.max(...eps.map(e => e.added)), year: mt.year || eps[0].year, done: eps.every(e => seen(e.id)), ts: ip ? st.prog[ip.id].ts : 0};
  });
  indexTitles();
}

/* ---------- rendering ---------- */
function card(t) {
  const p = st.prog[t.rep.id], pc = p && p.d && pr(t.rep) ? Math.min(100, p.t / p.d * 100) : 0, r = st.rate[t.key];
  return `<div class="card" data-k="${esc(t.key)}" style="background-image:${bgT(t)}"><b class="add">${st.list.includes(t.key) ? '✓' : '+'}</b>${t.done ? '<u>✓ Watched</u>' : t.s ? `<u>${t.eps.length} eps</u>` : r ? `<u>★ ${r}</u>` : ''}<span>${esc(t.title)}</span>${pc ? `<i style="width:${pc}%"></i>` : ''}</div>`;
}
function render() {
  const q = $('#q').value.trim(), cats = [...new Set(T.map(t => t.cat))].sort(), so = $('#sort').value;
  $('#chips').innerHTML = [['all', 'All'], ['movies', 'Movies'], ['shows', 'TV Shows'], ['list', 'My List'], ['unwatched', 'Unwatched'],
    ...st.pl.map(p => ['p:' + p.id, '▤ ' + p.name]), ...cats.map(c => ['c:' + c, c])]
    .map(([k, l]) => `<a data-f="${esc(k)}" class="${k == filt ? 'on' : ''}">${esc(l)}</a>`).join('');
  const F = {all: () => 1, movies: t => !t.s, shows: t => t.s, list: t => st.list.includes(t.key), unwatched: t => !t.done};
  const f = filt.startsWith('c:') ? t => t.cat == filt.slice(2) : filt.startsWith('p:') ? t => { const p = curPl(); return p && p.items.includes(t.key); } : F[filt];
  const grid = q || filt != 'all' || so != 'rows';
  $('#hero').style.display = grid ? 'none' : ''; let h = '';
  if (grid) {
    let L, note = '';
    if (q) {
      const r = searchT(q).filter(x => f(x.t)); L = r.map(x => x.t);
      if (so != 'rows') L.sort(S[so]);
      if (r.length && r[0].s < .85) note = `<p class="note">No exact match for “${esc(q)}”. Showing the closest titles.</p>`;
      if (!r.length) note = `<p class="note">No results for “${esc(q)}”. Check the spelling or try fewer words.</p>`;
    } else L = T.filter(f).sort(S[so] || S.new);
    h = note + plBar() + (L.length ? `<div class="grid">${L.map(card).join('')}</div>` : q ? '' : '<p class="empty">Nothing here.</p>');
  } else {
    const rec = recommend(), bec = because();
    const rows = [['Continue Watching', T.filter(t => t.ts).sort((a, b) => b.ts - a.ts)], ['My List', T.filter(t => st.list.includes(t.key))],
      ['Recommended For You', rec], bec && ['Because you watched ' + bec[0], bec[1]], ['Recently Added', [...T].sort(S.new).slice(0, 15)],
      ...(rec.length ? [] : [['Picked For You', pick.map(K).filter(Boolean)]]),
      ...st.pl.map(p => ['▤ ' + p.name, T.filter(t => p.items.includes(t.key))]), ...cats.map(c => [c, T.filter(t => t.cat == c).sort(S.az)])].filter(Boolean);
    h = rows.filter(r => r[1].length).map(([n, a]) => `<h2>${esc(n)}</h2><div class="row">${a.map(card).join('')}</div>`).join('')
      || '<p class="empty">No videos found. Put files in your Movies folder and restart the server.</p>';
  }
  $('#rows').innerHTML = h;
}
function hero() {
  const t = feat.length && K(feat[fi % feat.length]), h = $('#hero');
  if (!t) { h.style.height = '80px'; h.innerHTML = ''; return; }
  const r = t.rep; h.style.height = '';
  h.style.backgroundImage = `linear-gradient(to top,#0b0b10,transparent 65%),linear-gradient(90deg,#000b,transparent 70%),${bgT(t)}`;
  h.innerHTML = `<div><h1>${esc(t.title)}</h1><p class="meta">${[t.year || '', t.meta.rating ? '★ ' + t.meta.rating : '', t.s ? t.eps.length + ' episodes' : r.quality, dur(r.dur), t.genres.slice(0, 3).join(', ') || t.cat].filter(Boolean).join(' · ')}</p>
  <button class="btn p" data-a="play" data-id="${r.id}">▶ ${pr(r) ? 'Resume' : 'Play'}</button><button class="btn s" data-a="info" data-k="${esc(t.key)}">ⓘ More info</button></div>`;
}
setInterval(() => { if ($('#player').hidden && $('#modal').hidden) { fi++; hero(); } }, 9000);

/* ---------- info modal ---------- */
function info(k) {
  const t = K(k); if (!t) return; curK = k;
  const r = t.rep, m = t.meta, inl = st.list.includes(k), cont = t.eps.some(pr), my = st.rate[k] || 0, vers = lib.filter(e => e.dup_of == r.id);
  const eps = t.s ? t.eps.map((e, i) => {
    const p = st.prog[e.id], pc = pr(e) && p.d ? p.t / p.d * 100 : 0;
    return (i && t.eps[i - 1].season == e.season ? '' : `<h3>Season ${e.season}</h3>`) +
      `<div class="ep" data-a="play" data-id="${e.id}"><b>${e.ep}</b><div>${esc(e.title)}<small>${dur(e.dur)} ${e.quality} ${e.subs.length ? '· CC' : ''}</small>${pc ? `<i style="width:${pc}%"></i>` : ''}</div><button data-a="dl" data-id="${e.id}" title="Download">⬇</button><button data-a="watch" data-id="${e.id}" title="Toggle watched">${seen(e.id) ? '✓' : '○'}</button></div>`;
  }).join('') : '';
  $('#mc').innerHTML = `<div class="mh" style="background-image:linear-gradient(to top,#181820,transparent),${bgT(t)}"><button data-a="closem">✕</button><h1>${esc(t.title)}</h1></div>
  <div class="mb"><p class="meta">${[t.year || '', m.rating ? '★ ' + m.rating + ' TMDB' : '', t.s ? t.eps.length + ' episodes' : r.quality || (r.height ? r.height + 'p' : ''), dur(r.dur), fsz(t.eps.reduce((a, e) => a + e.size, 0)), t.cat, r.subs.length ? 'CC' : '', r.audio.length > 1 ? r.audio.length + ' audio' : ''].filter(Boolean).join(' · ')}</p>
  ${m.tagline ? `<p class="meta"><i>${esc(m.tagline)}</i></p>` : ''}${m.overview ? `<p style="margin-bottom:10px">${esc(m.overview)}</p>` : ''}
  ${t.genres.length ? `<p class="meta">${esc(t.genres.join(' · '))}</p>` : ''}${m.cast && m.cast.length ? `<p class="meta">Cast: ${esc(m.cast.join(', '))}</p>` : ''}
  <button class="btn p" data-a="play" data-id="${r.id}">▶ ${pr(r) ? 'Resume' : 'Play'}${t.s ? ' ' + epl(r) : ''}</button>
  <button class="btn s" data-a="list" data-k="${esc(k)}">${inl ? '✓ In My List' : '+ My List'}</button><button class="btn s" data-a="plpick" data-k="${esc(k)}">▤ Playlist</button>
  ${cont ? `<button class="btn s" data-a="unresume" data-k="${esc(k)}">Remove from Continue Watching</button>` : ''}
  ${t.s ? '' : `<button class="btn s" data-a="watch" data-id="${r.id}">${seen(r.id) ? 'Mark unwatched' : 'Mark watched'}</button>`}
  <div class="stars">Your rating: ${[1, 2, 3, 4, 5].map(n => `<span data-a="rate" data-k="${esc(k)}" data-n="${n}" class="${n <= my ? 'on' : ''}">★</span>`).join('')}</div>
  <p class="meta" style="margin:10px 0">Download for offline: <select id="dlq"><option value="orig">Original</option><option value="720">720p</option><option value="480">480p</option><option value="360">360p</option></select>
  ${t.s ? '(tap ⬇ on an episode)' : `<button class="btn s" data-a="dl" data-id="${r.id}">⬇ Download</button>`}</p>
  ${vers.length ? `<h3>Other versions</h3>` + vers.map(e => `<div class="ep" data-a="play" data-id="${e.id}"><b>▶</b><div>${e.height ? e.height + 'p' : '?'} · ${e.ext.slice(1).toUpperCase()}<small>${fsz(e.size)}</small></div></div>`).join('') : ''}${eps}</div>`;
  $('#modal').hidden = false;
}
function toggle(k) { const i = st.list.indexOf(k); i < 0 ? st.list.push(k) : st.list.splice(i, 1); save(); render(); }
function mark(id) { const i = st.watched.indexOf(id); i < 0 ? st.watched.push(id) : st.watched.splice(i, 1); delete st.prog[id]; save(); build(); render(); }

/* ---------- settings ---------- */
async function settings() {
  const tot = lib.reduce((a, e) => a + e.size, 0), td = lib.reduce((a, e) => a + e.dur, 0);
  $('#sc').innerHTML = `<button id="xs" data-a="closes">✕</button><h2 style="padding:0 0 8px">Settings · ${esc(me.name)}${me.admin ? ' (admin)' : ''}</h2>
  <label><input type=checkbox id=s1 ${st.set.auto ? 'checked' : ''}> Auto-play next episode</label>
  <label><input type=checkbox id=s2 ${st.set.subs ? 'checked' : ''}> Subtitles on by default</label>
  <label>Default quality <select id=s4>${[['orig', 'Original (best, direct)'], ['auto', 'Auto (adaptive)'], ['1080', '1080p'], ['720', '720p'], ['480', '480p'], ['360', '360p']].map(([v_, l]) => `<option value="${v_}" ${st.set.q == v_ ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
  <label>Accent colour <input type=color id=s3 value="${st.set.acc}"></label>
  <p class="meta">${lib.length} files · ${T.length} titles · ${fsz(tot)} · ${Math.round(td / 3600)} h of video</p>
  <div id="adm" ${me.admin ? '' : 'hidden'}>Loading…</div>
  ${me.admin ? '<button class="btn s" data-a="rescan">↻ Rescan folder</button><button class="btn s" data-a="dups">Duplicates</button><button class="btn s" data-a="clearcache">Clear transcode cache</button>' : ''}<button class="btn s" data-a="logout">Log out</button>`;
  $('#s1').onchange = e => { st.set.auto = e.target.checked; save(); };
  $('#s2').onchange = e => { st.set.subs = e.target.checked; save(); };
  $('#s4').onchange = e => { st.set.q = e.target.value; save(); };
  $('#s3').oninput = e => { st.set.acc = e.target.value; document.documentElement.style.setProperty('--acc', st.set.acc); save(); };
  $('#settings').hidden = false;
  if (me.admin) {
    const s = await api('/api/admin/stats');
    $('#adm').innerHTML = `<b>${s.users} account(s) · ${s.watching.length} watching now</b>` + s.watching.map(w => `<br>▶ ${esc(w.user)} — ${esc(w.title)}`).join('') +
      `<br>ffmpeg: ${s.ffmpeg ? 'on (quality/audio switching available)' : '<b>off</b> — install it for quality, audio tracks and thumbnails'}` +
      `<br>Metadata: ${s.tmdb ? s.meta + ' titles from TMDB' : 'off — start the server with TMDB_KEY=… for posters, summaries and cast'}`;
  }
}

/* ---------- events ---------- */
document.addEventListener('click', async e => {
  const t = e.target, a = t.closest('[data-a]'), f = t.closest('[data-f]'), add = t.closest('.add'), c = t.closest('.card'), sg = t.closest('[data-sg]');
  if (!t.closest('#sw')) $('#sg').hidden = true;
  if (sg) { $('#sg').hidden = true; return info(sg.dataset.k); }
  if (f) { filt = f.dataset.f; return render(); }
  if (a) {
    const x = a.dataset.a, {k, id} = a.dataset;
    if (extra(x, a.dataset)) return;
    if (x == 'play') play(id); else if (x == 'info') info(k);
    else if (x == 'list') { toggle(k); info(k); }
    else if (x == 'watch') { mark(id); info(curK); }
    else if (x == 'unresume') { K(k).eps.forEach(e => delete st.prog[e.id]); save(); build(); render(); info(k); }
    else if (x == 'closem') $('#modal').hidden = true; else if (x == 'closes') $('#settings').hidden = true;
    else if (x == 'signin') authReq('login'); else if (x == 'signup') authReq('signup');
    else if (x == 'rescan') { const r = await api('/api/admin/rescan', 'POST'); await loadLib(); toast(`Rescanned: ${r.count} files`); }
    else if (x == 'logout') { await api('/api/auth/logout', 'POST'); location.reload(); }
    return;
  }
  if (add) return toggle(add.closest('.card').dataset.k);
  if (c) return info(c.dataset.k);
  if (['modal', 'settings', 'page'].includes(t.id)) t.hidden = true;
});
let qt; $('#q').oninput = () => { suggest(); clearTimeout(qt); qt = setTimeout(render, 120); };
$('#q').onkeydown = e => { if (e.key == 'Enter') { $('#sg').hidden = true; render(); } else if (e.key == 'Escape') { $('#q').value = ''; $('#sg').hidden = true; render(); } };
$('#sort').onchange = render; $('#gear').onclick = settings; $('#hbtn').onclick = histPage;
$('#lp').onkeydown = $('#ln').onkeydown = e => { if (e.key == 'Enter') authReq('login'); };
$('#sur').onclick = () => { const u = T.filter(t => !t.done); if (u.length) info(u[Math.random() * u.length | 0].key); };
addEventListener('beforeunload', () => me && st && save(true));
addEventListener('keydown', e => {
  if (!$('#player').hidden || e.target.matches('input,select')) return;
  if (e.key == '/') { e.preventDefault(); $('#q').focus(); } else if (e.key == 'Escape') { $('#modal').hidden = $('#settings').hidden = $('#page').hidden = true; }
});
boot();
