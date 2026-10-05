"""Isolated FastAPI instance used by browser tests."""

import tempfile
from pathlib import Path

import uvicorn
from fastapi.responses import Response

from backend.api.app import create_app


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="fluxget-e2e-") as directory:
        wrapped = create_app(database_path=Path(directory) / "e2e.sqlite3")
        api = wrapped.app
        server = uvicorn.Server(uvicorn.Config(wrapped, host="127.0.0.1", port=8766, log_level="warning"))

        @api.middleware("http")
        async def serve_test_download(request, call_next):
            if request.url.path == "/test-download":
                return Response(b"browser-test-download", media_type="application/octet-stream")
            if request.url.path == "/test-shutdown":
                server.should_exit = True
                return Response(status_code=204)
            return await call_next(request)

        server.run()


if __name__ == "__main__":
    main()
