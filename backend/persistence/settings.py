"""Settings repository and service backed by the singleton SQLite row."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from backend.persistence.database import Database, default_download_dir


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class AppSettings:
    output_dir: str
    subdir: str = ""
    concurrency: int = 4
    max_retries: int = 3
    conflict_policy: str = "ask"
    current_mode: str = "direct"
    updated_at: str = ""


class SettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def ensure_defaults(self) -> None:
        async with await self.database.connect() as connection:
            await connection.execute(
                """INSERT OR IGNORE INTO settings
                   (id, output_dir, subdir, concurrency, max_retries,
                    conflict_policy, current_mode, updated_at)
                   VALUES (1, ?, '', 4, 3, 'ask', 'direct', ?)""",
                (default_download_dir(), utc_now()),
            )
            await connection.commit()

    async def get(self) -> AppSettings:
        async with await self.database.connect() as connection:
            cursor = await connection.execute(
                """SELECT output_dir, subdir, concurrency, max_retries,
                          conflict_policy, current_mode, updated_at
                   FROM settings WHERE id = 1"""
            )
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Settings defaults have not been initialized")
        return AppSettings(**dict(row))

    async def replace(self, settings: AppSettings) -> AppSettings:
        updated_at = utc_now()
        values = asdict(settings)
        async with await self.database.connect() as connection:
            await connection.execute(
                """INSERT INTO settings
                   (id, output_dir, subdir, concurrency, max_retries,
                    conflict_policy, current_mode, updated_at)
                   VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     output_dir=excluded.output_dir,
                     subdir=excluded.subdir,
                     concurrency=excluded.concurrency,
                     max_retries=excluded.max_retries,
                     conflict_policy=excluded.conflict_policy,
                     current_mode=excluded.current_mode,
                     updated_at=excluded.updated_at""",
                (
                    values["output_dir"], values["subdir"], values["concurrency"],
                    values["max_retries"], values["conflict_policy"],
                    values["current_mode"], updated_at,
                ),
            )
            await connection.commit()
        return AppSettings(**{**values, "updated_at": updated_at})


class SettingsService:
    def __init__(self, repository: SettingsRepository) -> None:
        self.repository = repository

    async def get(self) -> AppSettings:
        return await self.repository.get()

    async def update(self, settings: AppSettings) -> AppSettings:
        return await self.repository.replace(settings)
