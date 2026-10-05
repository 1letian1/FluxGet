"""SQLite database lifecycle, schema initialization, and migration support."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite


SCHEMA_VERSION = 4


def default_data_dir() -> Path:
    """Return the per-user application data directory for this platform."""
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "UniversalDownloader"
        return Path.home() / "AppData" / "Local" / "UniversalDownloader"

    root = os.environ.get("XDG_DATA_HOME")
    base = Path(root) if root else Path.home() / ".local" / "share"
    return base / "UniversalDownloader"


def default_download_dir() -> str:
    """Return the conventional per-user Downloads directory."""
    if os.name == "nt":
        profile = os.environ.get("USERPROFILE")
        home = Path(profile) if profile else Path.home()
        return str(home / "Downloads")
    return str(Path.home() / "Downloads")


class Database:
    """Own the on-disk SQLite database and apply schema migrations."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_data_dir() / "downloader.db"

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        """Open a connection and apply per-connection safety settings."""
        async with aiosqlite.connect(self.path, timeout=5) as connection:
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("PRAGMA busy_timeout = 5000")
            yield connection

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data_dir = self.path.parent
        (data_dir / "logs").mkdir(exist_ok=True)
        (data_dir / "cache").mkdir(exist_ok=True)

        async with self.connect() as connection:
            cursor = await connection.execute("PRAGMA user_version")
            row = await cursor.fetchone()
            version = int(row[0]) if row else 0
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {version} is newer than supported version {SCHEMA_VERSION}"
                )
            if version < 1:
                await self._migrate_to_v1(connection)
                version = 1
            if version < 2:
                await self._migrate_to_v2(connection)
                version = 2
            if version < 3:
                await self._migrate_to_v3(connection)
                version = 3
            if version < 4:
                await self._migrate_to_v4(connection)
                version = 4
            await connection.execute(f"PRAGMA user_version = {version}")
            await connection.commit()

    @staticmethod
    async def _migrate_to_v1(connection: aiosqlite.Connection) -> None:
        await connection.executescript(
            """
            CREATE TABLE settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                output_dir TEXT NOT NULL,
                subdir TEXT NOT NULL DEFAULT '',
                concurrency INTEGER NOT NULL DEFAULT 4 CHECK (concurrency BETWEEN 1 AND 32),
                max_retries INTEGER NOT NULL DEFAULT 3 CHECK (max_retries >= 0),
                conflict_policy TEXT NOT NULL DEFAULT 'ask'
                    CHECK (conflict_policy IN ('overwrite', 'rename', 'skip', 'ask')),
                current_mode TEXT NOT NULL DEFAULT 'direct'
                    CHECK (current_mode IN ('direct', 'rule')),
                updated_at TEXT NOT NULL
            );

            CREATE TABLE rules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                base_url TEXT NOT NULL,
                url_template TEXT NOT NULL,
                filename_template TEXT NOT NULL,
                default_ext TEXT NOT NULL DEFAULT '',
                builtin INTEGER NOT NULL DEFAULT 0 CHECK (builtin IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE download_tasks (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                filename TEXT NOT NULL,
                output_dir TEXT NOT NULL,
                temp_path TEXT NOT NULL,
                source_type TEXT NOT NULL CHECK (source_type IN ('direct', 'rule')),
                rule_id TEXT REFERENCES rules(id) ON DELETE SET NULL,
                status TEXT NOT NULL CHECK (status IN (
                    'pending', 'downloading', 'waiting_user', 'completed',
                    'failed', 'cancelled', 'skipped'
                )),
                bytes_total INTEGER CHECK (bytes_total IS NULL OR bytes_total >= 0),
                bytes_downloaded INTEGER NOT NULL DEFAULT 0 CHECK (bytes_downloaded >= 0),
                retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
                max_retries INTEGER NOT NULL CHECK (max_retries >= 0),
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );
            CREATE INDEX idx_download_tasks_status_created
                ON download_tasks(status, created_at);
            CREATE INDEX idx_download_tasks_created
                ON download_tasks(created_at);

            CREATE VIEW download_history AS
            SELECT id, url, filename, output_dir, source_type, status,
                   bytes_downloaded, bytes_total, retry_count, error_code,
                   error_message, created_at, finished_at
            FROM download_tasks
            WHERE status IN ('completed', 'failed', 'cancelled', 'skipped');
            """
        )

    @staticmethod
    async def _migrate_to_v2(connection: aiosqlite.Connection) -> None:
        await connection.execute(
            """ALTER TABLE download_tasks ADD COLUMN conflict_policy TEXT NOT NULL DEFAULT 'ask'
               CHECK (conflict_policy IN ('overwrite', 'rename', 'skip', 'ask'))"""
        )

    @staticmethod
    async def _migrate_to_v3(connection: aiosqlite.Connection) -> None:
        await connection.execute("ALTER TABLE download_tasks ADD COLUMN output_root TEXT NOT NULL DEFAULT ''")
        await connection.execute("ALTER TABLE download_tasks ADD COLUMN subdir TEXT NOT NULL DEFAULT ''")
        await connection.execute("UPDATE download_tasks SET output_root = output_dir WHERE output_root = ''")

    @staticmethod
    async def _migrate_to_v4(connection: aiosqlite.Connection) -> None:
        await connection.execute(
            "ALTER TABLE download_tasks ADD COLUMN queue_cleared INTEGER NOT NULL DEFAULT 0 CHECK (queue_cleared IN (0, 1))"
        )
