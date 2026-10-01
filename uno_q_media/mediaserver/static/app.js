const $ = s => document.querySelector(s);
const ICON = { video: "🎬", audio: "🎵", image: "🖼️" };
const REMUX_EXT = ["mkv", "avi", "mov"];

let lib = [], kind = "all", query = "", current = null, ffmpeg = false;

const enc = p => p.split("/").map(encodeURIComponent).join("/");
const esc = s => String(s).replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtSize = b => {
  const u = ["B", "KB", "MB", "GB"]; let i = 0;
  while (b >= 1024 && i < 3) { b /= 1024; i++; }
  return b.toFixed(i ? 1 : 0) + " " + u[i];
};
const visible = () => lib.filter(i =>
  (kind === "all" || i.kind === kind) && i.path.toLowerCase().includes(query));

async function load(force) {
  const r = await fetch("/api/library" + (force ? "?rescan=1" : ""));
  if (r.status === 401) return showLogin();
  const d = await r.json();
  lib = d.items; ffmpeg = d.ffmpeg;
  render();
}

function showLogin() {
  $("#count").textContent = "";
  $("#list").innerHTML = `<li class="login"><p>This server needs an access token.</p>
    <form id="lf"><input id="tk" type="password" placeholder="Access token" autofocus>
    <button>Unlock</button></form></li>`;
  $("#lf").onsubmit = e => {
    e.preventDefault();
    location.href = "/?token=" + encodeURIComponent($("#tk").value);
  };
}

function render() {
  const v = visible();
  $("#count").textContent = v.length + " items";
  $("#list").innerHTML = v.length ? v.map(i => `
    <li data-p="${esc(i.path)}" class="${i.path === current ? "on" : ""}">
      <span class="ic">${ICON[i.kind]}</span>
      <div><b>${esc(i.name)}</b>
      <small>${esc(i.folder || "/")} · ${i.ext.toUpperCase()} · ${fmtSize(i.size)}</small></div>
    </li>`).join("") : '<li class="empty">No media found</li>';
}

function play(path) {
  const i = lib.find(x => x.path === path);
  if (!i) return;
  current = path;
  const remux = ffmpeg && REMUX_EXT.includes(i.ext);
  const src = (remux ? "/remux/" : "/media/") + enc(i.path);
  let html;
  if (i.kind === "video") {
    const track = i.sub ? `<track default kind="subtitles" src="/sub/${enc(i.sub)}">` : "";
    html = `<video id="pl" src="${src}" controls autoplay playsinline>${track}</video>`;
  } else if (i.kind === "audio") {
    html = `<audio id="pl" src="${src}" controls autoplay></audio>`;
  } else {
    html = `<img src="${src}" alt="">`;
  }
  $("#player").innerHTML = html + `<div class="t">${esc(i.name)}</div>`;
  $("#player").hidden = false;
  const el = $("#pl");
  if (el) el.onended = playNext;
  window.scrollTo({ top: 0, behavior: "smooth" });
  render();
}

function playNext() {
  const v = visible().filter(i => i.kind !== "image");
  const n = v.findIndex(i => i.path === current);
  if (n >= 0 && n < v.length - 1) play(v[n + 1].path);
}

$("#list").onclick = e => {
  const li = e.target.closest("li[data-p]");
  if (li) play(li.dataset.p);
};
$("#q").oninput = e => { query = e.target.value.toLowerCase(); render(); };
$("#chips").onclick = e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.id === "rescan") return load(true);
  kind = b.dataset.k;
  document.querySelectorAll("#chips [data-k]").forEach(x => x.classList.toggle("on", x === b));
  render();
};

load();
