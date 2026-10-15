"""Local and production entry point (one worker, no reload)."""

import os
import ipaddress
import logging
import uvicorn
from app.server import create_app
from app.config import LOG_LEVEL

app = create_app()

if __name__ == "__main__":
    trusted = os.getenv("TRUSTED_PROXY_IPS", "").strip()
    for network in filter(None, trusted.split(",")):
        if ipaddress.ip_network(network.strip(), strict=False).prefixlen == 0:
            raise ValueError("TRUSTED_PROXY_IPS must not trust all addresses")
    logging.basicConfig(level=LOG_LEVEL.upper(), format="%(levelname)s: %(message)s")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=False,
        workers=1,
        log_level=LOG_LEVEL,
        proxy_headers=bool(trusted),
        forwarded_allow_ips=trusted,
        limit_concurrency=32,
        timeout_keep_alive=5,
    )
