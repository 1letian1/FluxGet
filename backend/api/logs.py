"""Authenticated endpoints for recent application logs and export."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from backend.observability import LogService


router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


class LogExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: StrictInt = Field(default=5000, ge=1, le=5000)


def _service(request: Request) -> LogService:
    service = getattr(request.app.state, "log_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Log service is unavailable")
    return service


@router.get("")
async def recent_logs(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    service = _service(request)
    return await asyncio.to_thread(service.recent, limit=limit, offset=offset)


@router.post("/export")
async def export_logs(payload: LogExportRequest, request: Request) -> dict[str, object]:
    service = _service(request)
    return await asyncio.to_thread(service.export, limit=payload.limit)
