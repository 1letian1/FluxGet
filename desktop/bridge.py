"""Restricted native capabilities exposed to the Vue application."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class NativeBridge:
    def __init__(self, api_port: int, session_token: str) -> None:
        self.api_port = api_port
        self.session_token = session_token
        self.window: Any | None = None
        self._maximized = False

    def bind_window(self, window: Any) -> None:
        self.window = window

    def get_runtime_config(self) -> dict[str, Any]:
        return {"apiBaseUrl": f"http://127.0.0.1:{self.api_port}", "sessionToken": self.session_token}

    def choose_folder(self, initial_dir: str = "") -> str | None:
        if self.window is None:
            return None
        import webview

        paths = self.window.create_file_dialog(webview.FOLDER_DIALOG, directory=initial_dir)
        return str(Path(paths[0])) if paths else None

    def open_folder(self, path: str) -> bool:
        candidate = Path(path).expanduser().resolve()
        if not candidate.is_dir():
            return False
        if os.name == "nt":
            os.startfile(str(candidate))  # type: ignore[attr-defined]
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(candidate)], close_fds=True)
        return True

    def minimize(self) -> None:
        if self.window is not None:
            self.window.minimize()

    def toggle_maximize(self) -> None:
        if self.window is None:
            return
        if self._maximized:
            self.window.restore()
        else:
            self.window.maximize()
        self._maximized = not self._maximized

    def close_window(self) -> None:
        if self.window is not None:
            self.window.destroy()
