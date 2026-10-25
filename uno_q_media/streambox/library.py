"""Finds videos, parses names, probes streams, detects duplicates, makes thumbnails."""
import hashlib, json, re, subprocess, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import config as C

SE = re.compile(r"[Ss](\d{1,2})[ ._-]*[Ee](\d{1,3})")
YEAR = re.compile(r"\b(19[2-9]\d|20[0-4]\d)\b")
QUAL = re.compile(r"(2160p|4k|1080p|720p|480p)", re.I)
BAD_V = {"hevc", "h265", "mpeg4", "vc1", "wmv3", "mpeg2video"}     # browsers often can't play these directly
BAD_A = {"ac3", "eac3", "dts", "truehd", "mp2"}


def clean(s):
    s = re.sub(r"[\[\(].*?[\]\)]", " ", s)
    s = re.sub(r"[._]+", " ", s)
    s = re.sub(r"\b(2160p|1080p|720p|480p|4k|bluray|brrip|webrip|web-dl|hdrip|dvdrip|x264|x265|hevc|h264|aac|yify)\b.*", "", s, flags=re.I)
    t = YEAR.sub("", s)
    return re.sub(r"\s+", " ", t if t.strip() else s).strip(" -").title()


def probe(path):
    out = dict(dur=0, h=0, w=0, vc="", audio=[])
    if not C.FFPROBE:
        return out
    try:
        r = subprocess.run([C.FFPROBE, "-v", "error", "-show_entries",
                            "format=duration:stream=codec_type,codec_name,height,width,channels:stream_tags=language,title",
                            "-of", "json", path], capture_output=True, text=True, timeout=30)
        j = json.loads(r.stdout)
        out["dur"] = int(float(j.get("format", {}).get("duration") or 0))
        for s in j.get("streams", []):
            if s.get("codec_type") == "video" and not out["h"]:
                out.update(h=s.get("height") or 0, w=s.get("width") or 0, vc=s.get("codec_name", ""))
            elif s.get("codec_type") == "audio":
                t = s.get("tags", {})
                out["audio"].append(dict(i=len(out["audio"]), lang=t.get("language", ""), name=t.get("title", ""),
                                         ch=s.get("channels") or 2, codec=s.get("codec_name", "")))
    except Exception:
        pass
    return out


def _nk(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


class Library:
    def __init__(self):
        self.items, self.index, self.public_json, self.dups = [], {}, b"[]", []
        self._tl = {}

    def scan(self):
        """Runs once at startup (and when an admin presses Rescan)."""
        files = []
        if C.MOVIES_DIR.is_dir():
            files = [p for p in sorted(C.MOVIES_DIR.rglob("*"))
                     if p.is_file() and p.suffix.lower() in C.EXTS and not p.name.startswith(".")]
        with ThreadPoolExecutor(4) as ex:
            probes = list(ex.map(lambda p: probe(str(p)), files))
        items = [self._item(p, pr) for p, pr in zip(files, probes)]
        self.dups = self._dups(items)
        self.index, self.items = {m["id"]: m for m in items}, items
        self.public_json = json.dumps([{k: v for k, v in m.items() if k not in ("path", "_subs")}
                                       for m in items]).encode()
        return len(items)

    def _item(self, p, pr):
        rel, st = p.relative_to(C.MOVIES_DIR), p.stat()
        se, y, q = SE.search(p.stem), YEAR.search(p.stem), QUAL.search(p.stem)
        ext, cat, iid = p.suffix.lower(), (rel.parts[0] if len(rel.parts) > 1 else "Movies"), hashlib.md5(str(rel).encode()).hexdigest()[:12]
        subs = sorted(f for f in p.parent.iterdir() if f.suffix.lower() in (".srt", ".vtt") and f.name.startswith(p.stem))
        ok = ext in C.NATIVE
        if C.FFPROBE and pr["h"]:
            ok = ok and pr["vc"] not in BAD_V and not (pr["audio"] and pr["audio"][0]["codec"] in BAD_A)
        it = dict(id=iid, key=iid, title=clean(p.stem), category=cat, added=int(st.st_mtime), size=st.st_size, ext=ext,
                  native=ok or not C.FFMPEG, hls=bool(C.FFMPEG and pr["dur"] and pr["h"]),
                  dur=pr["dur"], height=pr["h"], width=pr["w"], audio=pr["audio"],
                  year=int(y.group()) if y else 0, quality=q.group().upper() if q else "",
                  subs=[f.stem[len(p.stem):].strip(". _-") or "Subtitles" for f in subs],
                  path=str(p), _subs=[str(f) for f in subs])
        if se:
            it.update(series=clean(p.stem[:se.start()]) or clean(p.parent.name), season=int(se[1]), ep=int(se[2]))
            it["key"] = f"s:{cat}|{it['series']}"
        return it

    def _dups(self, items):
        """Same movie (title+year) or same episode in several files -> the best copy wins."""
        g = {}
        for m in items:
            k = (_nk(m["series"]), m["season"], m["ep"]) if "series" in m else (_nk(m["title"]), m["year"])
            if k[0]:
                g.setdefault(k, []).append(m)
        out = []
        for v in g.values():
            if len(v) > 1:
                v.sort(key=lambda m: (m["height"], m["size"]), reverse=True)
                for m in v[1:]:
                    m["dup_of"] = v[0]["id"]
                out.append(v)
        return out

    def thumb(self, i):
        m = self.index.get(i)
        if not m:
            return None
        p = Path(m["path"])
        for ext in (".jpg", ".png"):                 # custom poster beside the video
            if p.with_suffix(ext).exists():
                return p.with_suffix(ext)
        out = C.CACHE / f"{i}.jpg"
        if out.exists() or not C.FFMPEG:
            return out if out.exists() else None
        with self._tl.setdefault(i, threading.Lock()):
            if not out.exists():
                tmp = C.CACHE / f"{i}.tmp.jpg"
                subprocess.run([C.FFMPEG, "-y", "-ss", str((m["dur"] or 60) * 0.1), "-i", m["path"], "-frames:v", "1",
                                "-vf", "scale=640:-2", "-q:v", "4", str(tmp)], capture_output=True)
                if tmp.exists():
                    tmp.replace(out)
        return out if out.exists() else None

    def warm(self):
        def job():
            with ThreadPoolExecutor(2) as ex:
                list(ex.map(self.thumb, [m["id"] for m in self.items]))
        threading.Thread(target=job, daemon=True).start()
