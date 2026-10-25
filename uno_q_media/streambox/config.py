"""Settings. Override with environment variables."""
import os, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOVIES_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "MOVIES_DIR", Path.home() / "Downloads" / "Movies")).expanduser()
DATA = ROOT / "data"
CACHE, HLS, EXPORTS, POSTERS = DATA / "thumbs", DATA / "hls", DATA / "exports", DATA / "posters"
for d in (DATA, CACHE, HLS, EXPORTS, POSTERS, DATA / "state"):
    d.mkdir(parents=True, exist_ok=True)

EXTS = {".mp4", ".m4v", ".webm", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".ts"}
NATIVE = {".mp4", ".m4v", ".webm", ".mov"}          # containers browsers can play directly
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")

HOST = os.environ.get("HOST", "0.0.0.0")            # 127.0.0.1 = this computer only
PORT = int(os.environ.get("PORT", 5000))
THREADS = int(os.environ.get("THREADS", 64))
MAX_TRANSCODES = int(os.environ.get("MAX_TRANSCODES", 2))   # parallel ffmpeg jobs (HLS segments + downloads)
ALLOW_SIGNUP = os.environ.get("ALLOW_SIGNUP", "1") != "0"
TMDB_KEY = os.environ.get("TMDB_KEY", "").strip()   # free key from themoviedb.org -> posters, summaries, cast
SEG = 6                                             # HLS segment length (seconds)
