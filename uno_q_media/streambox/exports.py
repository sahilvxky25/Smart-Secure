"""Downloads for offline viewing. Original file, or a smaller MP4 made on demand
(handy for phones). Converted files are cached, so the next person gets them instantly."""
import subprocess, threading
from flask import Blueprint, abort, current_app as app, jsonify, request, send_file
from . import config as C
from .hls import SLOTS

bp = Blueprint("exports", __name__)
JOBS = {}                     # (video id, height) -> {state, pct}
HEIGHTS = (1080, 720, 480, 360)


def _file(i, q):
    return C.EXPORTS / f"{i}_{q}.mp4"


def _run(m, q, job):
    out = _file(m["id"], q)
    tmp = out.with_name(out.stem + ".part.mp4")
    with SLOTS:
        job["state"] = "running"
        p = subprocess.Popen([C.FFMPEG, "-v", "error", "-y", "-i", m["path"], "-map", "0:v:0", "-map", "0:a:0?",
                              "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-vf", f"scale=-2:{q}",
                              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-movflags", "+faststart",
                              "-progress", "pipe:1", "-nostats", str(tmp)],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for line in p.stdout:
            if line.startswith("out_time_ms=") and m["dur"]:
                try:
                    job["pct"] = min(99, int(int(line.split("=")[1]) / 1e6 / m["dur"] * 100))
                except ValueError:
                    pass
        p.wait()
    if p.returncode == 0 and tmp.exists():
        tmp.replace(out)
        job.update(state="done", pct=100)
    else:
        job["state"] = "error"


def _status(i, q):
    if _file(i, q).exists():
        return dict(state="done", pct=100)
    return JOBS.get((i, q)) or dict(state="none", pct=0)


@bp.post("/api/export/<i>/<int:q>")
def start(i, q):
    m = app.lib.index.get(i) or abort(404)
    if not C.FFMPEG or q not in HEIGHTS:
        abort(400)
    if _status(i, q)["state"] in ("none", "error"):
        job = JOBS[(i, q)] = dict(state="queued", pct=0)
        threading.Thread(target=_run, args=(m, q, job), daemon=True).start()
    return jsonify(_status(i, q))


@bp.get("/api/export/<i>/<int:q>")
def status(i, q):
    return jsonify(_status(i, q))


@bp.get("/download/<i>")
def download(i):
    m, q = app.lib.index.get(i) or abort(404), request.args.get("q", "orig")
    if q == "orig":
        return send_file(m["path"], as_attachment=True)
    if not q.isdigit() or not _file(i, int(q)).exists():
        abort(404)
    return send_file(_file(i, int(q)), as_attachment=True, download_name=f"{m['title']} {q}p.mp4")
