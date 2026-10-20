"""Embedded FastAPI backend for zero-config hosting (e.g. Streamlit Community Cloud).

The Streamlit UI talks to the FastAPI backend over HTTP (``web/api_client.py``).
On single-process hosts there is no second service to run ``uvicorn``, so when
demo mode is active (``PAWPILOT_DEMO_MODE=1``) and no external backend URL is
configured (``PAWPILOT_API_URL`` unset), we start the API in a daemon thread on
127.0.0.1:8000. Local development with a separately launched backend is
unaffected: the env var check short-circuits before any binding happens.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ``streamlit run web/app.py`` puts the *script directory* (``web/``) at the
# front of ``sys.path``. ``web/app.py`` then shadows the repo-root ``app``
# package, so the backend's absolute imports (``app.api.main``) would resolve
# to the Streamlit script and fail with "'app' is not a package". Put the repo
# root first — before any ``app.*`` import happens — and drop a shadowed
# ``app`` module if one was already cached.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_repo_str = str(_REPO_ROOT)
if _repo_str in sys.path:
    sys.path.remove(_repo_str)
sys.path.insert(0, _repo_str)
_shadow = sys.modules.get("app")
if _shadow is not None and not hasattr(_shadow, "__path__"):
    del sys.modules["app"]

_HOST = "127.0.0.1"
_PORT = 8000

_lock = threading.Lock()
_started = False


def _port_open(timeout: float = 0.3) -> bool:
    try:
        socket.create_connection((_HOST, _PORT), timeout=timeout).close()
    except OSError:
        return False
    return True


def ensure_demo_api() -> None:
    """Start the in-process demo API if needed (idempotent, thread-safe)."""
    global _started
    if os.environ.get("PAWPILOT_DEMO_MODE", "").lower() not in {"1", "true", "yes"}:
        return
    if os.environ.get("PAWPILOT_API_URL"):
        # External backend configured — never bind locally.
        return
    if _started:
        return
    with _lock:
        if _started:
            return
        if _port_open():
            # A backend is already listening (e.g. developer's own uvicorn).
            _started = True
            return
        import uvicorn

        config = uvicorn.Config(
            "app.api.main:app",
            host=_HOST,
            port=_PORT,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        threading.Thread(target=server.run, daemon=True, name="pawpilot-demo-api").start()
        # Demo-mode lifespan ingests the bundled corpus into DuckDB on startup;
        # wait until the port accepts connections before letting the UI call it.
        for _ in range(150):  # up to ~30s
            if _port_open():
                break
            time.sleep(0.2)
        else:
            logger.warning("embedded demo API did not open port %s in time", _PORT)
        _started = True
