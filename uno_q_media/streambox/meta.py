"""Optional TMDB lookup (set TMDB_KEY). Runs in the background; results and images are cached on disk,
so after the first run everything works offline."""
import hashlib, json, threading, time, urllib.parse, urllib.request
from . import config as C

FILE = C.DATA / "meta.json"
API, IMG = "https://api.themoviedb.org/3", "https://image.tmdb.org/t/p/"


class Meta:
    def __init__(self):
        try:
            self.d = json.loads(FILE.read_text())
        except Exception:
            self.d = {}
        self.busy = False

    def _get(self, path, **q):
        q["api_key"] = C.TMDB_KEY
        with urllib.request.urlopen(f"{API}{path}?{urllib.parse.urlencode(q)}", timeout=15) as r:
            return json.load(r)

    def _img(self, path, size, name):
        f = C.POSTERS / name
        if not f.exists() and path:
            try:
                with urllib.request.urlopen(f"{IMG}{size}{path}", timeout=20) as r:
                    f.write_bytes(r.read())
            except Exception:
                return ""
        return name if f.exists() else ""

    def lookup(self, key, title, year, tv):
        kind = "tv" if tv else "movie"
        q = dict(query=title)
        if year:
            q["first_air_date_year" if tv else "year"] = year
        res = self._get(f"/search/{kind}", **q).get("results") or (self._get(f"/search/{kind}", query=title).get("results") if year else [])
        if not res:
            return {}
        det = self._get(f"/{kind}/{res[0]['id']}", append_to_response="credits")
        h = hashlib.md5(key.encode()).hexdigest()[:12]
        return dict(tmdb=res[0]["id"], overview=det.get("overview", ""), tagline=det.get("tagline", ""),
                    rating=round(det.get("vote_average") or 0, 1),
                    year=int((det.get("release_date") or det.get("first_air_date") or "0")[:4] or 0),
                    genres=[g["name"] for g in det.get("genres", [])],
                    cast=[c["name"] for c in det.get("credits", {}).get("cast", [])[:6]],
                    poster=self._img(det.get("poster_path"), "w342", h + "_p.jpg"),
                    backdrop=self._img(det.get("backdrop_path"), "w780", h + "_b.jpg"))

    def fetch_missing(self, lib):
        if not C.TMDB_KEY or self.busy:
            return

        def job():
            self.busy = True
            try:
                done = set()
                for m in list(lib.items):
                    k = m["key"]
                    if k in done or k in self.d:
                        continue
                    done.add(k)
                    try:
                        self.d[k] = self.lookup(k, m.get("series") or m["title"], m["year"], "series" in m)
                    except Exception:
                        continue          # network hiccup: retried on next start
                    FILE.write_text(json.dumps(self.d))
                    time.sleep(0.3)       # be polite to the API
            finally:
                self.busy = False
        threading.Thread(target=job, daemon=True).start()
