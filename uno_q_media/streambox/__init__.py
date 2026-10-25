import secrets
from flask import Flask, g, jsonify, request, send_from_directory
from . import config as C
from .library import Library
from .meta import Meta
from .store import Store


def create_app():
    app = Flask(__name__, static_folder=str(C.ROOT / "static"), static_url_path="")
    key = C.DATA / "secret.key"
    if not key.exists():
        key.write_text(secrets.token_hex(32))
    app.config["SECRET_KEY"] = key.read_text()

    app.store = Store()
    app.lib = Library()
    app.lib.scan()          # the library is scanned ONCE here, at startup
    app.lib.warm()          # thumbnails build in the background
    app.meta = Meta()
    app.meta.fetch_missing(app.lib)   # TMDB lookup in the background (only if TMDB_KEY is set)

    from . import api, auth, exports, hls, media
    for bp in (auth.bp, api.bp, media.bp, hls.bp, exports.bp):
        app.register_blueprint(bp)

    @app.before_request
    def guard():
        auth.load_user()
        public = request.endpoint in ("static", "index", "manifest") or request.path.startswith("/api/auth/")
        if not g.user and not public:
            return jsonify(error="login required"), 401

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/manifest.json")
    def manifest():
        return jsonify(name="StreamBox", short_name="StreamBox", start_url="/", display="standalone",
                       background_color="#0b0b10", theme_color="#0b0b10")

    return app
