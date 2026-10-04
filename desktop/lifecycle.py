"""Start the local API and desktop window, then shut them down together."""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import uvicorn
import webview

from backend.api.app import create_app
from desktop.bridge import NativeBridge

logger = logging.getLogger(__name__)


class ApiServer:
    def __init__(self, port: int, token: str) -> None:
        self.port = port
        self.config = uvicorn.Config(
            create_app(token), host="127.0.0.1", port=port, log_config=None,
            access_log=False, lifespan="on", timeout_graceful_shutdown=15,
        )
        self.server = uvicorn.Server(self.config)
        self.thread = threading.Thread(target=self.server.run, name="local-api", daemon=True)
        self._stop_lock = threading.Lock()
        self._stopped = False

    def start(self, timeout: float = 15.0) -> None:
        self.thread.start()
        deadline = time.monotonic() + timeout
        health_url = f"http://127.0.0.1:{self.port}/api/v1/health"
        while time.monotonic() < deadline:
            if not self.thread.is_alive():
                raise RuntimeError("Local API server stopped before becoming ready")
            try:
                with urllib.request.urlopen(health_url, timeout=0.4) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(0.08)
        self.stop()
        raise TimeoutError("Local API server did not become ready within 15 seconds")

    def stop(self) -> None:
        with self._stop_lock:
            if self._stopped:
                return
            self.server.should_exit = True
            if self.thread.is_alive() and threading.current_thread() is not self.thread:
                self.thread.join(timeout=30)
            if self.thread.is_alive():
                logger.error("Local API did not stop cleanly; forcing server shutdown")
                self.server.force_exit = True
                self.thread.join(timeout=2)
            self._stopped = not self.thread.is_alive()
            if self._stopped:
                logger.info("Local API stopped after application cleanup")


def _reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _frontend_url(port: int) -> str:
    override = os.environ.get("UNIVERSAL_DOWNLOADER_FRONTEND_URL")
    if override:
        return override
    root = Path(__file__).resolve().parents[1]
    index = root / "frontend" / "dist" / "index.html"
    return f"http://127.0.0.1:{port}/" if index.is_file() else "http://127.0.0.1:5173"


def run_desktop() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    port = _reserve_local_port()
    token = os.urandom(32).hex()
    api = ApiServer(port, token)
    api.start()
    bridge = NativeBridge(port, token, shutdown=api.stop)
    try:
        window = webview.create_window(
            "通用下载器", _frontend_url(port), js_api=bridge, width=1440, height=940,
            min_size=(900, 640), frameless=True, easy_drag=True,
            background_color="#10131a", text_select=True,
        )
        if window is None:
            raise RuntimeError("pywebview failed to create the application window")
        bridge.bind_window(window)
        window.events.closing += api.stop
        webview.start(debug=bool(os.environ.get("UNIVERSAL_DOWNLOADER_DEBUG")))
    finally:
        api.stop()
