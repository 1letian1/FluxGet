"""SQLite persistence for download tasks."""

from __future__ import annotations

from dataclasses import fields
import logging
import os
from pathlib import Path

from backend.download.models import DownloadTask
from backend.download.models import utc_now
from backend.download.path_service import PathService, UnsafePath
from backend.persistence.database import Database

logger = logging.getLogger(__name__)


class TaskRepository:
    _COLUMNS = tuple(field.name for field in fields(DownloadTask))

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _from_row(row: object) -> DownloadTask:
        values = dict(row)
        return DownloadTask(**{key: values[key] for key in TaskRepository._COLUMNS if key in values})

    async def create(self, task: DownloadTask) -> None:
        columns = ", ".join(self._COLUMNS)
        placeholders = ", ".join("?" for _ in self._COLUMNS)
        async with await self.database.connect() as connection:
            await connection.execute(
                f"INSERT INTO download_tasks ({columns}) VALUES ({placeholders})",
                tuple(getattr(task, key) for key in self._COLUMNS),
            )
            await connection.commit()

    async def save(self, task: DownloadTask, *, expected_status: str | None = None) -> bool:
        columns = ", ".join(f"{key} = ?" for key in self._COLUMNS if key != "id")
        values = tuple(getattr(task, key) for key in self._COLUMNS if key != "id")
        async with await self.database.connect() as connection:
            where = "id = ?" if expected_status is None else "id = ? AND status = ?"
            params = (*values, task.id) if expected_status is None else (*values, task.id, expected_status)
            cursor = await connection.execute(f"UPDATE download_tasks SET {columns} WHERE {where}", params)
            await connection.commit()
            return cursor.rowcount == 1

    async def get(self, task_id: str) -> DownloadTask | None:
        async with await self.database.connect() as connection:
            cursor = await connection.execute("SELECT * FROM download_tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
        return self._from_row(row) if row else None

    async def list(self, *, active_only: bool = False, limit: int = 500, offset: int = 0) -> list[DownloadTask]:
        where = "WHERE status IN ('pending', 'downloading', 'waiting_user') OR (status = 'completed' AND queue_cleared = 0)" if active_only else ""
        async with await self.database.connect() as connection:
            cursor = await connection.execute(
                f"SELECT * FROM download_tasks {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def history(self, *, limit: int = 100, offset: int = 0) -> list[DownloadTask]:
        async with await self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM download_tasks WHERE status IN ('completed', 'failed', 'cancelled', 'skipped') ORDER BY finished_at DESC, created_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def clear_completed_queue(self) -> int:
        async with await self.database.connect() as connection:
            cursor = await connection.execute(
                "UPDATE download_tasks SET queue_cleared = 1 WHERE status = 'completed' AND queue_cleared = 0"
            )
            await connection.commit()
            return cursor.rowcount

    async def recover_interrupted(self) -> list[DownloadTask]:
        async with await self.database.connect() as connection:
            cursor = await connection.execute("SELECT * FROM download_tasks WHERE status = 'downloading'")
            rows = await cursor.fetchall()
            for row in rows:
                task = self._from_row(row)
                try:
                    root = task.output_root or task.output_dir
                    target, safe_name = PathService.resolve_output_path(root, task.subdir, task.filename)
                    expected_part = str(target) + ".part"
                    if safe_name != task.filename or self._normalized_path(task.temp_path) != self._normalized_path(expected_part):
                        raise UnsafePath("Recovered task paths do not match the validated destination")
                    part_path = Path(expected_part)
                    if part_path.is_symlink() or (part_path.exists() and not part_path.is_file()):
                        raise UnsafePath("Recovered partial file is not a regular application file")
                    try:
                        actual = os.path.getsize(expected_part)
                    except FileNotFoundError:
                        actual = 0
                    await connection.execute(
                        "UPDATE download_tasks SET status='pending', output_dir=?, temp_path=?, bytes_downloaded=?, updated_at=?, error_code=NULL, error_message=NULL, finished_at=NULL WHERE id=?",
                        (str(target.parent), expected_part, actual, utc_now(), task.id),
                    )
                    logger.info("Interrupted task restored for resume", extra={"event": "task.recovered",
                                "task_id": task.id, "download_filename": task.filename, "status": "pending"})
                except (UnsafePath, OSError, RuntimeError, ValueError):
                    logger.warning("Interrupted task could not be safely resumed",
                                   extra={"event": "task.recovery_failed", "task_id": task.id,
                                          "download_filename": task.filename, "status": "failed",
                                          "error_code": "recovery_failed"})
                    await connection.execute(
                        "UPDATE download_tasks SET status='failed', bytes_downloaded=0, updated_at=?, finished_at=?, error_code='recovery_failed', error_message='The interrupted task could not be safely resumed' WHERE id=?",
                        (utc_now(), utc_now(), task.id),
                    )
            await connection.commit()
        return await self.list(active_only=True, limit=10000)

    @staticmethod
    def _normalized_path(value: str) -> str:
        return os.path.normcase(os.path.abspath(Path(value).expanduser()))
