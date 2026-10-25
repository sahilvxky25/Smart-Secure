/* Watch history, ratings, playlists, offline downloads, duplicate report */
const page = h => { $('#pgc').innerHTML = `<button id="xp" data-a="closep">✕</button><div class="pg">${h}</div>`; $('#page').hidden = false; };

/* ---- history ---- */
function logHist(id) {
  const l = st.hist[0];
  if (!(l && l.id == id && Date.now() - l.ts < 1800000)) st.hist.unshift({id, ts: Date.now()});
  st.hist = st.hist.slice(0, 500); save();
}
function histPage() {
  const days = {}, today = new Date().toDateString(), yest = new Date(Date.now() - 864e5).toDateString();
  st.hist.forEach(h => { const e = lib.find(x => x.id == h.id); if (e) { const d = new Date(h.ts); (days[d.toDateString()] = days[d.toDateString()] || []).push([e, d]); } });
  const keys = Object.keys(days);
  page(`<h2 style="padding:0 0 8px">Watch history</h2>` + (keys.length ? keys.map(k =>
    `<h3>${k == today ? 'Today' : k == yest ? 'Yesterday' : k}</h3>` + days[k].map(([e, d]) =>
      `<div class="ep" data-a="play" data-id="${e.id}"><i class="th" style="background-image:${bg(e)}"></i><div>${esc(e.series ? e.series + ' · ' + epl(e) : e.title)}<small>${d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}</small></div></div>`).join('')).join('')
    + `<button class="btn s" data-a="clearhist" style="margin-top:14px">Clear history</button>` : '<p class="meta">Nothing watched yet.</p>'));
}

/* ---- ratings ---- */
function rate(k, n) { st.rate[k] == n ? delete st.rate[k] : st.rate[k] = n; save(); build(); render(); info(k); }

/* ---- playlists ---- */
const curPl = () => st.pl.find(p => 'p:' + p.id == filt);
function plPicker(k) {
  page(`<h2 style="padding:0 0 8px">Add to playlist</h2>` + st.pl.map(p =>
    `<label><input type=checkbox data-a="pltog" data-p="${p.id}" data-k="${esc(k)}" ${p.items.includes(k) ? 'checked' : ''}> ${esc(p.name)}</label>`).join('')
    + `<button class="btn s" data-a="plnew" data-k="${esc(k)}">+ New playlist</button>`);
}
function plBar() {
  const p = curPl();
  return p ? `<div class="note"><b>▤ ${esc(p.name)}</b> · ${p.items.length} titles<br><button class="btn s" data-a="plplay">▶ Play all</button><button class="btn s" data-a="plshuf">🔀 Shuffle</button><button class="btn s" data-a="plren">Rename</button><button class="btn s" data-a="pldel">Delete</button></div>` : '';
}

/* ---- downloads (original or a smaller converted copy) ---- */
async function dlFile(id) {
  const q = ($('#dlq') || {}).value || 'orig';
  if (q == 'orig') return location.href = `/download/${id}?q=orig`;
  const key = id + q; if (dls[key]) return toast('Already preparing…'); dls[key] = 1;
  try {
    let j = await api(`/api/export/${id}/${q}`, 'POST');
    while (j.state != 'done') {
      if (j.state == 'error') throw 0;
      toast(`Preparing ${q}p… ${j.pct}%`); await new Promise(r => setTimeout(r, 2000)); j = await api(`/api/export/${id}/${q}`);
    }
    location.href = `/download/${id}?q=${q}`;
  } catch { toast('Conversion failed (is ffmpeg installed?)'); }
  delete dls[key];
}

/* ---- admin ---- */
async function dupPage() {
  const d = await api('/api/admin/duplicates');
  page(`<h2 style="padding:0 0 8px">Duplicates</h2><p class="meta">${d.groups.length} group(s) · ${fsz(d.waste)} could be freed. StreamBox never deletes files; users see only the best copy.</p>` +
    d.groups.map(g => `<h3>${esc(g[0].title)}</h3>` + g.map((f, i) => `<div class="meta" style="margin:2px 0">${i ? '✂ extra' : '✔ keep'} · ${f.h ? f.h + 'p · ' : ''}${fsz(f.size)}<br>${esc(f.path)}</div>`).join('')).join(''));
}

/* ---- click router for the actions above (returns true if handled) ---- */
function extra(x, d) {
  const {k, id, p, n} = d;
  switch (x) {
    case 'hist': histPage(); break;
    case 'clearhist': st.hist = []; save(); histPage(); break;
    case 'closep': $('#page').hidden = true; break;
    case 'rate': rate(k, +n); break;
    case 'dl': dlFile(id); break;
    case 'plpick': plPicker(k); break;
    case 'pltog': { const pl = st.pl.find(q => q.id == p), i = pl.items.indexOf(k); i < 0 ? pl.items.push(k) : pl.items.splice(i, 1); save(); render(); break; }
    case 'plnew': { const nm = (prompt('Playlist name') || '').trim().slice(0, 40); if (!nm) break; st.pl.push({id: Date.now().toString(36), name: nm, items: [k]}); save(); render(); plPicker(k); break; }
    case 'plplay': case 'plshuf': {
      const pl = curPl(); if (!pl) break;
      const ids = T.filter(t => pl.items.includes(t.key)).map(t => t.rep.id); if (!ids.length) break;
      if (x == 'plshuf') ids.sort(() => Math.random() - .5);
      queue = ids.slice(1); play(ids[0]); break;
    }
    case 'plren': { const pl = curPl(), nm = (prompt('New name', pl.name) || '').trim().slice(0, 40); if (nm) { pl.name = nm; save(); render(); } break; }
    case 'pldel': { const pl = curPl(); if (confirm('Delete this playlist?')) { st.pl = st.pl.filter(q => q != pl); filt = 'all'; save(); render(); } break; }
    case 'dups': dupPage(); break;
    case 'clearcache': api('/api/admin/clear_cache', 'POST').then(() => toast('Transcode cache cleared')); break;
    default: return false;
  }
  return true;
}
