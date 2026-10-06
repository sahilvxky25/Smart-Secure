"""Start the server:  python run.py"""
import os

import uvicorn

from app.config import HOST, PORT

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", host=HOST, port=PORT, workers=1,  # single process: presence & rate limits live in memory
        proxy_headers=True, forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        log_level=os.getenv("LOG_LEVEL", "info"),
    )
