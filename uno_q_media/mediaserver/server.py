"""Server bootstrap."""
import os
import shutil
import socket
from http.server import ThreadingHTTPServer

from .config import parse_args
from .handler import Handler
from .library import Library


def local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def run(cfg):
    if not os.path.isdir(cfg.root):
        os.makedirs(cfg.root, exist_ok=True)
        print("Created media folder:", cfg.root)

    Handler.library = Library(cfg.root, ttl=cfg.rescan)
    Handler.token = cfg.token
    Handler.ffmpeg = shutil.which("ffmpeg")

    count = len(Handler.library.items(force=True))
    srv = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    srv.daemon_threads = True

    suffix = "/?token=%s" % cfg.token if cfg.token else "/"
    print("UNO Q Media Server")
    print("  root   :", Handler.library.root, "(%d files)" % count)
    print("  ffmpeg :", Handler.ffmpeg or "not found (MKV/AVI remux disabled)")
    print("  open   : http://%s:%d%s" % (local_ip(), cfg.port, suffix))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
    finally:
        srv.server_close()


def main(argv=None):
    run(parse_args(argv))
