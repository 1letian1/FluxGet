"""Rotating application logs and safe log export helpers."""

from __future__ import annotations

import json
import logging
import logging.handlers
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonLineFormatter(logging.Formatter):
    _EXTRA_FIELDS = ("event", "task_id", "download_filename", "url", "status", "error_code")

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in self._EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                entry["filename" if key == "download_filename" else key] = value
        return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))


class LogService:
    MAX_READ_LINES = 5000

    def __init__(self, log_dir: str | Path) -> None:
        self.log_dir = Path(log_dir)
        self.path = self.log_dir / "app.jsonl"
        self._handler: logging.Handler | None = None

    def configure(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        app_logger = logging.getLogger("backend")
        if app_logger.level == logging.NOTSET:
            app_logger.setLevel(logging.INFO)
        resolved = self.path.resolve()
        if any(getattr(handler, "baseFilename", None) == str(resolved) for handler in app_logger.handlers):
            return
        handler = logging.handlers.RotatingFileHandler(
            self.path, maxBytes=5 * 1024 * 1024, backupCount=4, encoding="utf-8",
        )
        handler.setFormatter(JsonLineFormatter())
        app_logger.addHandler(handler)
        self._handler = handler

    def close(self) -> None:
        if self._handler is None:
            return
        app_logger = logging.getLogger("backend")
        app_logger.removeHandler(self._handler)
        self._handler.close()
        self._handler = None

    def recent(self, *, limit: int = 200, offset: int = 0) -> dict[str, object]:
        entries: deque[dict[str, Any]] = deque(maxlen=self.MAX_READ_LINES)
        for path in (self.path.with_name(f"{self.path.name}.{index}") for index in range(4, 0, -1)):
            self._append_file(path, entries)
        self._append_file(self.path, entries)
        ordered = list(reversed(entries))
        return {"items": ordered[offset:offset + limit], "limit": limit, "offset": offset,
                "total": len(ordered)}

    def export(self, *, limit: int = 5000) -> dict[str, object]:
        items = self.recent(limit=limit)["items"]
        assert isinstance(items, list)
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        content = "\n".join(json.dumps(item, ensure_ascii=False) for item in items)
        if content:
            content += "\n"
        return {"filename": f"universal-downloader-logs-{day}.jsonl", "content": content,
                "count": len(items)}

    @staticmethod
    def _append_file(path: Path, entries: deque[dict[str, Any]]) -> None:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        entries.append(value)
        except OSError:
            return
