"""Adaptive streaming (HLS). Playlists are generated from the video's length; each 6-second
segment is transcoded the first time somebody asks for it, then cached for everyone.
Seeking works instantly, and any audio track / quality can be chosen."""
import math, subprocess, threading
from flask import Blueprint, Response, abort, current_app as app, request, send_file
from . import config as C

bp = Blueprint("hls", __name__, url_prefix="/hls")
SLOTS = threading.BoundedSemaphore(C.MAX_TRANSCODES)      # shared with downloads: caps CPU use
LOCKS = {}
LADDER = [(1080, 5_000_000), (720, 2_800_000), (480, 1_400_000), (360, 800_000)]


def _m(i):
    m = app.lib.index.get(i)
    return m if m and m["hls"] else abort(404)


def levels(m):
    return [h for h, _ in LADDER if h <= m["height"] + 8] or [m["height"]]


def _audio(m):
    a = request.args.get("a", 0, type=int)
    return a if 0 <= a < max(1, len(m["audio"])) else 0


@bp.get("/<i>/master.m3u8")
def master(i):
    m, a, q = _m(i), _audio(_m(i)), request.args.get("q", "auto")
    ls = levels(m)
    if q == "best":
        ls = ls[:1]
    elif q.isdigit():
        ls = [min(ls, key=lambda h: abs(h - int(q)))]
    out = ["#EXTM3U"]
    for h in ls:
        w = int(m["width"] * h / m["height"]) // 2 * 2
        out += [f"#EXT-X-STREAM-INF:BANDWIDTH={dict(LADDER).get(h, 2_000_000)},RESOLUTION={w}x{h}", f"{h}/index.m3u8?a={a}"]
    return Response("\n".join(out) + "\n", mimetype="application/vnd.apple.mpegurl")


@bp.get("/<i>/<int:h>/index.m3u8")
def variant(i, h):
    m, a = _m(i), _audio(_m(i))
    if h not in levels(m):
        abort(404)
    out = ["#EXTM3U", "#EXT-X-VERSION:3", f"#EXT-X-TARGETDURATION:{C.SEG}", "#EXT-X-MEDIA-SEQUENCE:0", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for k in range(math.ceil(m["dur"] / C.SEG)):
        out += [f"#EXTINF:{min(C.SEG, m['dur'] - k * C.SEG):.3f},", f"{k}.ts?a={a}"]
    out.append("#EXT-X-ENDLIST")
    return Response("\n".join(out) + "\n", mimetype="application/vnd.apple.mpegurl")


def _make(m, h, a, k, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp, s = out.with_suffix(".tmp"), k * C.SEG
    subprocess.run([C.FFMPEG, "-v", "error", "-y", "-ss", str(s), "-i", m["path"], "-t", str(min(C.SEG, m["dur"] - s)),
                    "-map", "0:v:0", "-map", f"0:a:{a}?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-vf", f"scale=-2:{h}", "-pix_fmt", "yuv420p", "-g", "48", "-sc_threshold", "0",
                    "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-output_ts_offset", str(s), "-f", "mpegts", str(tmp)],
                   capture_output=True, timeout=300)
    if tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(out)


@bp.get("/<i>/<int:h>/<int:k>.ts")
def segment(i, h, k):
    m, a = _m(i), _audio(_m(i))
    if h not in levels(m) or k * C.SEG >= m["dur"]:
        abort(404)
    out = C.HLS / m["id"] / f"{h}_{a}" / f"{k}.ts"
    if not out.exists():
        with LOCKS.setdefault((i, h, a, k), threading.Lock()):     # many viewers -> one ffmpeg run
            if not out.exists():
                with SLOTS:
                    if not out.exists():
                        _make(m, h, a, k, out)
        LOCKS.pop((i, h, a, k), None)
    if not out.exists():
        abort(500)
    return send_file(out, mimetype="video/mp2t", max_age=3600)
