"""Harbor: a small Google Drive-style file storage app (Flask + SQLite).

Importing this package has no side effects (config, data dir and database are only
touched once `create_app()` or a submodule is imported), so tests can set DATA_DIR first.
"""


def create_app():
    from .app import create_app as _create_app
    return _create_app()


def start_background_jobs(*args, **kwargs):
    from .app import start_background_jobs as _start
    return _start(*args, **kwargs)
