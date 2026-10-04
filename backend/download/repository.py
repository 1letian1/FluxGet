"""SQLite persistence for download tasks."""

from __future__ import annotations

from dataclasses import fields

from backend.download.models import DownloadTask
from backend.persistence.database import Database


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
        where = "WHERE status IN ('pending', 'downloading', 'waiting_user')" if active_only else ""
        async with await self.database.connect() as connection:
            cursor = await connection.execute(
                f"SELECT * FROM download_tasks {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def recover_interrupted(self) -> list[DownloadTask]:
        async with await self.database.connect() as connection:
            cursor = await connection.execute("SELECT * FROM download_tasks WHERE status = 'downloading'")
            rows = await cursor.fetchall()
            for row in rows:
                task = self._from_row(row)
                from dataclasses import replace
                from backend.download.models import utc_now
                actual = 0
                try:
                    import os
                    actual = os.path.getsize(task.temp_path)
                except OSError:
                    pass
                recovered = replace(task, status="pending", bytes_downloaded=actual, updated_at=utc_now(),
                                    error_code=None, error_message=None, finished_at=None)
                await connection.execute(
                    "UPDATE download_tasks SET status='pending', bytes_downloaded=?, updated_at=?, error_code=NULL, error_message=NULL, finished_at=NULL WHERE id=?",
                    (actual, recovered.updated_at, task.id),
                )
            await connection.commit()
        return await self.list(active_only=True, limit=10000)
