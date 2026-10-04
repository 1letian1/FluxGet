"""FastAPI application factory and local-instance authentication."""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.api.settings import router as settings_router
from backend.api.tasks import events_router, router as tasks_router
from backend.download.manager import DownloadManager
from backend.download.repository import TaskRepository
from backend.persistence.database import Database
from backend.persistence.settings import SettingsRepository, SettingsService


class LocalInstanceAuth:
    """Require the current desktop instance token for local API/WS traffic."""

    def __init__(self, app: ASGIApp, token: str | None) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.token is None or scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        protected = (
            scope["type"] == "http" and path.startswith("/api/v1/") and path != "/api/v1/health"
        ) or (scope["type"] == "websocket" and path == "/ws/events")
        if not protected:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"x-session-token", b"").decode("utf-8", "ignore")
        if scope["type"] == "websocket" and not supplied:
            query = scope.get("query_string", b"").decode("ascii", "ignore")
            supplied = next(
                (part.partition("=")[2] for part in query.split("&") if part.partition("=")[0] == "session_token"),
                "",
            )

        if not secrets.compare_digest(supplied, self.token):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4401})
            else:
                body = b'{"error":{"code":"unauthorized","message":"Invalid session token","details":{}}}'
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)


def create_app(
    session_token: str | None = None,
    database_path: str | Path | None = None,
) -> ASGIApp:
    """Create an API app; desktop instances pass a fresh token and persistent DB path."""
    database = Database(database_path)

    @asynccontextmanager
    async def lifespan(api: FastAPI):
        await database.initialize()
        repository = SettingsRepository(database)
        await repository.ensure_defaults()
        settings = await repository.get()
        download_manager = DownloadManager(
            TaskRepository(database), concurrency=settings.concurrency,
            max_retries=settings.max_retries, conflict_policy=settings.conflict_policy,
        )
        await download_manager.start()
        api.state.database = database
        api.state.settings_service = SettingsService(repository)
        api.state.download_manager = download_manager
        try:
            yield
        finally:
            await download_manager.close()
            api.state.download_manager = None
            api.state.settings_service = None
            api.state.database = None

    api = FastAPI(title="Universal Downloader API", version="0.1.0", lifespan=lifespan)
    api.include_router(settings_router)
    api.include_router(tasks_router)
    api.include_router(events_router)

    @api.get("/api/v1/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Report that the local API is running."""
        return {"status": "ok"}

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if (frontend_dist / "index.html").is_file():
        api.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return LocalInstanceAuth(api, session_token)


app: Any = create_app()
