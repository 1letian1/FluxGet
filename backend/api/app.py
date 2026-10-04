"""FastAPI application skeleton."""

from fastapi import FastAPI

app = FastAPI(
    title="Universal Downloader API",
    version="0.1.0",
)


@app.get("/api/v1/health", tags=["health"])
async def health() -> dict[str, str]:
    """Report that the local development API is running."""
    return {"status": "ok"}
