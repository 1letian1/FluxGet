"""Single source of truth for task status transitions."""

from __future__ import annotations

from backend.download.models import DownloadTask, TaskStatus, utc_now

_ALLOWED: dict[str, set[str]] = {
    "pending": {"downloading", "cancelled"},
    "downloading": {"pending", "completed", "failed", "cancelled", "waiting_user"},
    "waiting_user": {"pending", "skipped", "failed"},
    "failed": {"pending"},
    "cancelled": {"pending"},
    "completed": set(),
    "skipped": set(),
}


class InvalidTaskTransition(ValueError):
    pass


class TaskStateMachine:
    @staticmethod
    def transition(task: DownloadTask, status: TaskStatus, **changes: object) -> DownloadTask:
        if status not in _ALLOWED.get(task.status, set()):
            raise InvalidTaskTransition(f"Cannot transition task from {task.status} to {status}")
        if status in {"completed", "failed", "cancelled", "skipped"}:
            changes.setdefault("finished_at", utc_now())
        elif status == "pending":
            changes.setdefault("finished_at", None)
        if status == "downloading":
            changes.setdefault("started_at", utc_now())
        return task.changed(status=status, **changes)
