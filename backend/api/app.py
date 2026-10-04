"""FastAPI application factory and local-instance authentication."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send


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


def create_app(session_token: str | None = None) -> ASGIApp:
    """Create an API app; desktop instances pass a fresh per-process token."""
    api = FastAPI(title="Universal Downloader API", version="0.1.0")

    @api.get("/api/v1/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Report that the local API is running."""
        return {"status": "ok"}

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if (frontend_dist / "index.html").is_file():
        api.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return LocalInstanceAuth(api, session_token)


app: Any = create_app()
