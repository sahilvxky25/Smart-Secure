"""Start StreamBox:   python run.py [videos_folder]"""
import socket
from streambox import config as C, create_app

app = create_app()


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "localhost"


if __name__ == "__main__":
    print(f"\n  Library  : {C.MOVIES_DIR}  ({len(app.lib.items)} videos, scanned at startup)")
    print(f"  ffmpeg   : {'found' if C.FFMPEG else 'NOT found (no thumbnails / mkv support)'}")
    print(f"  Users    : {len(app.store.users)} account(s)   Sign-ups: {'on' if C.ALLOW_SIGNUP else 'off'}")
    print(f"  Open     : http://localhost:{C.PORT}   |   same Wi-Fi: http://{lan_ip()}:{C.PORT}\n")
    try:
        from waitress import serve
    except ImportError:
        print("  (waitress not installed - using Flask's built-in server; run: pip install waitress)\n")
        app.run(host=C.HOST, port=C.PORT, threaded=True)
    else:
        serve(app, host=C.HOST, port=C.PORT, threads=C.THREADS)
