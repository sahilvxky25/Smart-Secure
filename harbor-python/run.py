"""Start Harbor:  python run.py   (add --debug for the auto-reloading dev server)."""
import logging
import sys

from harbor import config, create_app, start_background_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()


def main():
    url = f"http://{'localhost' if config.HOST in ('127.0.0.1', '0.0.0.0') else config.HOST}:{config.PORT}"
    if "--debug" in sys.argv:
        app.run(host=config.HOST, port=config.PORT, debug=True)
        return
    from waitress import serve
    start_background_jobs()
    print(f"Harbor is running at {url}", flush=True)
    serve(app, host=config.HOST, port=config.PORT, threads=16,
          max_request_body_size=max(config.QUOTA_BYTES, config.MAX_FILE_BYTES) + 64 * 1024 * 1024,
          channel_timeout=600, ident="harbor")


if __name__ == "__main__":
    main()
