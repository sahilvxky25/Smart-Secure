/* Player: direct play or adaptive HLS (quality + audio track switching), resume, queue, shortcuts */
const v = $('#v');
const seek = d => v.currentTime = Math.max(0, v.currentTime + d);
const fs = () => document.fullscreenElement ? document.exitFullscreen() : $('#player').requestFullscreen?.();
const sib = (e, d) => { const t = T.find(t => t.eps.includes(e)); return t && t.s ? t.eps[t.eps.indexOf(e) + d] : null; };
const canHls = () => !!(window.Hls && Hls.isSupported()) || !!v.canPlayType('application/vnd.apple.mpegurl');
let startAt = null, hls = null, aIdx = 0, forceH = false, mode = 'direct';

/* (Re)load the video, keeping position t. Direct file when possible, HLS when the browser can't play the
   file, when a lower quality is chosen, or when a non-default audio track is selected. */
function load(e, t) {
  startAt = t; if (hls) { hls.destroy(); hls = null; }
  const q = st.set.q, H = window.Hls && Hls.isSupported(), canH = e.hls && canHls();
  mode = canH && (forceH || !e.native || q != 'orig' || aIdx > 0) ? 'hls' : 'direct';
  if (mode == 'hls') {
    const url = `/hls/${e.id}/master.m3u8?a=${aIdx}&q=${q != 'orig' ? q : e.native ? 'best' : 'auto'}`;
    if (H) {
      hls = new Hls({maxBufferLength: 30}); hls.loadSource(url); hls.attachMedia(v);
      hls.on(Hls.Events.ERROR, (_, d) => { if (d.fatal) $('#err').textContent = 'Stream error: ' + d.details; });
    } else v.src = url;
  } else v.src = '/stream/' + e.id;
  v.play().catch(() => {});
}

function play(id) {
  const e = lib.find(x => x.id == id); if (!e) return;
  cur = e; aIdx = 0; forceH = false; clearInterval(upT); $('#up').hidden = true; $('#err').textContent = '';
  ['modal', 'settings', 'page'].forEach(i => $('#' + i).hidden = true);
  v.innerHTML = e.subs.map((s, i) => `<track kind="subtitles" src="/api/subs/${e.id}/${i}" label="${esc(s)}" srclang="en" ${st.set.subs && !i ? 'default' : ''}>`).join('');
  v.defaultPlaybackRate = st.set.rate; v.volume = st.set.vol; $('#rate').value = st.set.rate; $('#qual').value = st.set.q;
  const au = $('#aud'); au.hidden = e.audio.length < 2;
  au.innerHTML = e.audio.map(a => `<option value="${a.i}">${esc(a.lang || 'Track ' + (a.i + 1))}${a.name ? ' · ' + esc(a.name) : ''} (${a.ch}ch)</option>`).join('');
  $('#pt').textContent = e.series ? `${e.series} · ${epl(e)}` : e.title;
  $('#player').hidden = false; logHist(id); load(e, null);
  clearInterval(hb); const beat = () => api('/api/heartbeat', 'POST', {id: e.id}); beat();
  hb = setInterval(() => cur && !v.paused && beat(), 15000);       // lets the admin see who is watching
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({title: e.title, artwork: [{src: '/api/thumb/' + e.id}]});
    navigator.mediaSession.setActionHandler('nexttrack', () => $('#nx').click());
    navigator.mediaSession.setActionHandler('previoustrack', () => $('#pv').click());
  }
}

v.onloadedmetadata = () => {
  const p = st.prog[cur.id];
  const t = startAt != null ? startAt : (p && pr(cur) && p.t < v.duration - 30 ? p.t : 0);
  startAt = null;
  if (t > 1 && isFinite(v.duration)) { v.currentTime = t; if (!$('#qual')._sw) toast('Resumed at ' + mmss(t)); }
};
v.ontimeupdate = () => {
  if (!cur || v.currentTime < 1) return;
  const d = cur.dur || v.duration;
  if (d && v.currentTime > d * .95) { if (!seen(cur.id)) { st.watched.push(cur.id); delete st.prog[cur.id]; save(); } return; }
  if (Date.now() - lastSave > 5000) { lastSave = Date.now(); st.prog[cur.id] = {t: v.currentTime, d, ts: Date.now()}; save(); }
};
v.onended = () => {
  if (!cur) return;
  if (!seen(cur.id)) { st.watched.push(cur.id); delete st.prog[cur.id]; }
  save(true);
  const n = sib(cur, 1) || (queue.length && lib.find(x => x.id == queue.shift()));    // next episode, else next in queue
  n && st.set.auto ? upnext(n) : closeP();
};
v.onerror = () => {
  if (mode == 'direct' && cur && cur.hls && !forceH && (window.Hls || v.canPlayType('application/vnd.apple.mpegurl'))) {
    forceH = true; toast('Converting for this device…'); return load(cur, v.currentTime || null);   // auto-fallback
  }
  $('#err').textContent = "Can't play this video on this device.";
};
v.onvolumechange = () => { st.set.vol = v.volume; };
v.ondblclick = e => {
  if (e.offsetY > v.clientHeight - 70) return; e.preventDefault();
  const x = e.offsetX / v.clientWidth; x < .33 ? seek(-10) : x > .67 ? seek(10) : fs();
};

function upnext(n) {
  let c = 6; $('#upt').textContent = n.series ? `${epl(n)} ${n.title}` : n.title; $('#upc').textContent = c; $('#up').hidden = false;
  upT = setInterval(() => { $('#upc').textContent = --c; if (c <= 0) { clearInterval(upT); play(n.id); } }, 1000);
  $('#upn').onclick = () => { clearInterval(upT); play(n.id); };
}
$('#upx').onclick = () => { clearInterval(upT); $('#up').hidden = true; queue = []; };

function closeP() {
  clearInterval(upT); clearInterval(hb); clearTimeout(sleepT); $('#sleep').value = 0; queue = []; save(true);
  if (hls) { hls.destroy(); hls = null; }
  v.pause(); v.removeAttribute('src'); v.load(); document.fullscreenElement && document.exitFullscreen();
  $('#player').hidden = true; $('#up').hidden = true; cur = null; build(); render(); hero();
}
function cc() {
  const tr = [...v.textTracks]; if (!tr.length) return toast('No subtitles found (put a .srt next to the video)');
  const i = tr.findIndex(t => t.mode == 'showing'); tr.forEach(t => t.mode = 'disabled');
  if (i + 1 < tr.length) { tr[i + 1].mode = 'showing'; toast('Subtitles: ' + tr[i + 1].label); } else toast('Subtitles off');
}

$('#x').onclick = closeP; $('#b10').onclick = () => seek(-10); $('#f10').onclick = () => seek(10); $('#skip').onclick = () => seek(85); $('#ccb').onclick = cc;
$('#nx').onclick = () => { const n = sib(cur, 1); n ? play(n.id) : toast('No next episode'); };
$('#pv').onclick = () => { const n = sib(cur, -1); n ? play(n.id) : toast('No previous episode'); };
$('#pip').onclick = () => document.pictureInPictureElement ? document.exitPictureInPicture() : v.requestPictureInPicture?.()?.catch(() => toast('PiP unavailable'));
$('#rate').onchange = e => { v.playbackRate = v.defaultPlaybackRate = st.set.rate = +e.target.value; save(); };
$('#qual').onchange = e => {                       // quality: Original / Auto / 1080 / 720 / 480 / 360
  st.set.q = e.target.value; save();
  if (!cur) return;
  if (st.set.q != 'orig' && !(cur.hls && canHls())) return toast('Quality switching needs ffmpeg on the server and HLS support (internet for hls.js once)');
  toast('Quality: ' + e.target.selectedOptions[0].text); load(cur, v.currentTime);
};
$('#aud').onchange = e => {                        // audio track (re-streams via HLS, keeps position)
  aIdx = +e.target.value;
  if (!(cur.hls && canHls())) return toast('Audio switching needs ffmpeg on the server and HLS support');
  toast('Audio: ' + e.target.selectedOptions[0].text); load(cur, v.currentTime);
};
$('#sleep').onchange = e => {
  clearTimeout(sleepT); const m = +e.target.value;
  if (m) { sleepT = setTimeout(() => { v.pause(); toast('Sleep timer: paused'); }, m * 60000); toast('Pausing in ' + m + ' min'); }
};

addEventListener('keydown', e => {
  if ($('#player').hidden || e.target.matches('input,select')) return;
  const k = e.key, n = () => e.preventDefault();
  if (k == ' ' || k == 'k') { n(); v.paused ? v.play() : v.pause(); }
  else if (k == 'ArrowRight') { n(); seek(5); } else if (k == 'ArrowLeft') { n(); seek(-5); }
  else if (k == 'l') seek(10); else if (k == 'j') seek(-10);
  else if (k == 'ArrowUp') { n(); v.volume = Math.min(1, v.volume + .1); } else if (k == 'ArrowDown') { n(); v.volume = Math.max(0, v.volume - .1); }
  else if (k == 'm') v.muted = !v.muted; else if (k == 'f') fs(); else if (k == 'c') cc();
  else if (k == 'n' || k == 'N') $('#nx').click(); else if (k == 'p') $('#pv').click();
  else if (k == '>' || k == '<') {
    const r = [.5, .75, 1, 1.25, 1.5, 2], i = Math.max(0, Math.min(5, r.indexOf(st.set.rate) + (k == '>' ? 1 : -1)));
    $('#rate').value = r[i]; $('#rate').onchange({target: $('#rate')}); toast(r[i] + 'x');
  }
  else if (/^\d$/.test(k)) v.currentTime = v.duration * k / 10;
  else if (k == 'Escape' && !document.fullscreenElement) closeP();
});
