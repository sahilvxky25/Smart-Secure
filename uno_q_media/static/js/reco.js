/* Recommendations: learns from what you watched, rated, and listed (genres from TMDB, folders, years, title words) */
function seenT(t) { return t.eps.some(e => seen(e.id) || pr(e)); }
const tags = t => [...(t.genres || []), 'c:' + t.cat];

function taste() {                                   // weight per genre/folder
  const w = {};
  T.forEach(t => {
    let x = seenT(t) ? 1 : 0;
    const r = st.rate[t.key]; if (r) x += (r - 3) * 1.5;           // 5★ = +3, 1★ = -3
    if (st.list.includes(t.key)) x += .5;
    if (x) tags(t).forEach(g => w[g] = (w[g] || 0) + x);
  });
  return w;
}
function sim(a, b) {                                 // how alike are two titles?
  let s = 0; const g = new Set(a.genres || []), bg_ = b.genres || [];
  if (g.size && bg_.length) s += bg_.filter(x => g.has(x)).length / Math.sqrt(g.size * bg_.length) * 2;
  if (a.cat == b.cat) s += .4;
  if (a.year && b.year && Math.abs(a.year - b.year) <= 8) s += .2;
  const aw = new Set(a.w); s += b.w.filter(x => x.length > 3 && aw.has(x)).length * .3;
  return s;
}
function recommend(n = 12) {
  const w = taste(); if (!Object.keys(w).length) return [];
  return T.filter(t => !t.done && !seenT(t)).map(t => ({t, s: tags(t).reduce((a, g) => a + (w[g] || 0), 0) / Math.sqrt(tags(t).length) + (t.meta.rating || 0) * .05}))
    .filter(x => x.s > 0).sort((a, b) => b.s - a.s).slice(0, n).map(x => x.t);
}
function because() {                                 // "Because you watched X"
  for (const h of st.hist) {
    const e = lib.find(x => x.id == h.id), base = e && T.find(t => t.eps.some(x => x.id == e.id));
    if (!base || (st.rate[base.key] && st.rate[base.key] <= 2)) continue;
    const r = T.filter(t => t !== base && !t.done).map(t => ({t, s: sim(base, t)})).filter(x => x.s > .5)
      .sort((a, b) => b.s - a.s).slice(0, 12).map(x => x.t);
    if (r.length) return [base.title, r];
  }
  return null;
}
