/* Typo-tolerant search: "avengrs", "intersteller", "spider man" vs "Spiderman" all still match. */
const norm = s => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim();

// Damerau-Levenshtein distance (counts a swapped pair like "teh"->"the" as 1 typo)
function dl(a, b) {
  const m = a.length, n = b.length;
  if (!m) return n; if (!n) return m;
  const d = Array.from({length: m + 1}, (_, i) => { const r = new Array(n + 1).fill(0); r[0] = i; return r; });
  for (let j = 1; j <= n; j++) d[0][j] = j;
  for (let i = 1; i <= m; i++) for (let j = 1; j <= n; j++) {
    const c = a[i - 1] == b[j - 1] ? 0 : 1;
    d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c);
    if (i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
  }
  return d[m][n];
}

// How well does one typed word match one title word? (0 = no match, 1 = exact)
function tokScore(q, w) {
  if (q == w) return 1;
  if (w.startsWith(q)) return .9;
  if (q.length > 2 && w.includes(q)) return .7;
  const max = q.length <= 3 ? 0 : q.length <= 4 ? 1 : q.length <= 7 ? 2 : 3;   // typos allowed grow with word length
  const x = dl(q, w);
  if (x <= max) return .8 - x * .1;
  if (q.length > 3) { const p = dl(q, w.slice(0, q.length)); if (p <= max) return .6 - p * .1; }   // typo in a half-typed word
  if (q.length > 3 && w.length > q.length && q[0] == w[0]) {      // abbreviation: "avng" -> "avengers"
    let i = 0; for (const ch of w) if (ch == q[i]) i++;
    if (i == q.length) return .5;
  }
  return 0;
}

function score(q, t) {
  const qs = q.split(' '); let tot = 0;
  for (const x of qs) {
    let b = 0;
    for (const w of t.w) { b = Math.max(b, tokScore(x, w)); if (b == 1) break; }
    if (!b) { tot = -1; break; }
    tot += b;
  }
  if (tot > 0) return tot / qs.length;
  const a = q.replace(/ /g, ''), s = t.nm.replace(/ /g, '');     // spacing typos: "spider man" vs "spiderman"
  if (a.length > 3 && s.includes(a)) return .65;
  const mx = a.length > 6 ? 2 : 1;
  return a.length > 3 && dl(a, s.slice(0, a.length)) <= mx ? .5 : 0;
}

function indexTitles() { T.forEach(t => { t.nm = norm(t.title + ' ' + (t.year || '')); t.w = t.nm.split(' '); }); }

function searchT(raw) {
  const q = norm(raw);
  if (!q) return [];
  return T.map(t => ({t, s: score(q, t)})).filter(x => x.s >= .45)
    .sort((a, b) => b.s - a.s || a.t.title.localeCompare(b.t.title));
}

function suggest() {
  const q = $('#q').value, el = $('#sg'), r = q.trim() ? searchT(q).slice(0, 6) : [];
  el.hidden = !r.length;
  el.innerHTML = r.map(({t}) => `<a data-k="${esc(t.key)}" data-sg="1"><i style="background-image:${bg(t.rep)}"></i>${esc(t.title)}<small>${t.s ? 'Show' : t.year || ''}</small></a>`).join('');
}
