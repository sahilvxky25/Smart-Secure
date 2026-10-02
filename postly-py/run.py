"""Start Postly:  python run.py"""
import uvicorn

from app.config import config

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        log_level="info",
        proxy_headers=config.trust_proxy,
        forwarded_allow_ips="*" if config.trust_proxy else None,
        timeout_graceful_shutdown=3,  # open live-update streams shouldn't hold up Ctrl+C
    )
