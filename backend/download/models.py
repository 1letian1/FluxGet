"""Persistent download task model and API serialization."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

TaskStatus = Literal["pending", "downloading", "waiting_user", "completed", "failed", "cancelled", "skipped"]
SourceType = Literal["direct", "rule"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class DownloadTask:
    id: str
    url: str
    filename: str
    output_dir: str
    temp_path: str
    source_type: SourceType = "direct"
    rule_id: str | None = None
    status: TaskStatus = "pending"
    bytes_total: int | None = None
    bytes_downloaded: int = 0
    retry_count: int = 0
    max_retries: int = 3
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = ""
    updated_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    conflict_policy: str = "ask"
    output_root: str = ""
    subdir: str = ""

    @classmethod
    def create(cls, url: str, filename: str, output_dir: str, *, source_type: SourceType = "direct",
               rule_id: str | None = None, max_retries: int = 3, conflict_policy: str = "ask",
               output_root: str = "", subdir: str = "") -> "DownloadTask":
        now = utc_now()
        target = Path(output_dir)
        return cls(str(uuid4()), url, filename, str(target), str(target / f"{filename}.part"),
                   source_type, rule_id, max_retries=max_retries, created_at=now, updated_at=now,
                   conflict_policy=conflict_policy, output_root=output_root or str(target), subdir=subdir)

    def changed(self, **changes: object) -> "DownloadTask":
        return replace(self, updated_at=utc_now(), **changes)

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["progress"] = (min(100.0, self.bytes_downloaded * 100 / self.bytes_total)
                               if self.bytes_total else None)
        return result
