"""Task creation and control endpoints backed by DownloadManager."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from backend.download.manager import DownloadManager
from backend.download.path_service import PathService, UnsafePath
from backend.download.state_machine import InvalidTaskTransition
from backend.rules.engine import RuleEngine
from backend.rules.models import RuleDefinition


router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
events_router = APIRouter(tags=["events"])


class DirectTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urls: str = Field(min_length=1, max_length=1_000_000)
    output_dir: str | None = Field(default=None, max_length=32767)
    subdir: str | None = Field(default=None, max_length=32767)


class RuleTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str = Field(min_length=1, max_length=128)
    inputs: str = Field(min_length=1, max_length=1_000_000)
    base_url: str | None = Field(default=None, max_length=2048)
    output_dir: str | None = Field(default=None, max_length=32767)
    subdir: str | None = Field(default=None, max_length=32767)


class ConflictResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution: Literal["overwrite", "rename", "skip"]


def _manager(request: Request) -> DownloadManager:
    manager = getattr(request.app.state, "download_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Download service is unavailable")
    return manager


def _settings(request: Request):
    service = getattr(request.app.state, "settings_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Settings service is unavailable")
    return service


@router.get("")
async def list_tasks(request: Request, limit: int = 500, offset: int = 0) -> dict[str, object]:
    if not 1 <= limit <= 1000 or offset < 0:
        raise HTTPException(status_code=422, detail="limit must be 1-1000 and offset must be non-negative")
    tasks = await _manager(request).list_tasks(active_only=True, limit=limit, offset=offset)
    return {"items": [task.to_dict() for task in tasks], "limit": limit, "offset": offset}


@router.get("/history")
async def list_history(request: Request, limit: int = 100, offset: int = 0) -> dict[str, object]:
    if not 1 <= limit <= 1000 or offset < 0:
        raise HTTPException(status_code=422, detail="limit must be 1-1000 and offset must be non-negative")
    tasks = await _manager(request).repository.history(limit=limit, offset=offset)
    return {"items": [task.to_dict() for task in tasks], "limit": limit, "offset": offset}


@router.post("/clear-completed")
async def clear_completed(request: Request) -> dict[str, int]:
    cleared = await _manager(request).repository.clear_completed_queue()
    return {"cleared": cleared}


@router.post("/direct", status_code=201)
async def create_direct_tasks(payload: DirectTaskRequest, request: Request) -> dict[str, object]:
    settings = await _settings(request).get()
    root = payload.output_dir or settings.output_dir
    subdir = settings.subdir if payload.subdir is None else payload.subdir
    created: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    for line_number, raw in enumerate(payload.urls.splitlines(), start=1):
        url = raw.strip()
        if not url:
            continue
        try:
            filename = PathService.filename_from_url(url)
            task = await _manager(request).create_task(url, filename, root, subdir)
            created.append(task.to_dict())
        except UnsafePath as exc:
            errors.append({"line": line_number, "input": raw, "error": str(exc)})
        except (ValueError, OSError):
            errors.append({"line": line_number, "input": raw, "error": "Invalid URL or inaccessible output location"})
    if not created and not errors:
        raise HTTPException(status_code=422, detail="At least one non-empty URL is required")
    return {"created": created, "errors": errors}


@router.post("/from-rule", status_code=201)
async def create_rule_tasks(payload: RuleTaskRequest, request: Request) -> dict[str, object]:
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(status_code=503, detail="Database is unavailable")
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT id, name, base_url, url_template, filename_template, default_ext, builtin FROM rules WHERE id = ?",
            (payload.rule_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule = RuleDefinition(**dict(row))
    if payload.base_url is not None:
        rule = replace(rule, base_url=payload.base_url.strip())
    engine = RuleEngine()
    previews = engine.preview(rule, payload.inputs)
    settings = await _settings(request).get()
    root = payload.output_dir or settings.output_dir
    subdir = settings.subdir if payload.subdir is None else payload.subdir
    created: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    for preview in previews:
        if not preview.valid:
            errors.append({"line": preview.line_number, "input": preview.raw, "error": preview.error})
            continue
        try:
            task = await _manager(request).create_task(
                preview.url, preview.filename, root, subdir,
                source_type="rule", rule_id=rule.id,
            )
            created.append(task.to_dict())
        except UnsafePath as exc:
            errors.append({"line": preview.line_number, "input": preview.raw, "error": str(exc)})
        except (ValueError, OSError):
            errors.append({"line": preview.line_number, "input": preview.raw,
                           "error": "Invalid generated URL or inaccessible output location"})
    return {"created": created, "errors": errors}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request) -> dict[str, object]:
    try:
        task = await _manager(request).cancel(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except InvalidTaskTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return task.to_dict()


@router.post("/{task_id}/retry")
async def retry_task(task_id: str, request: Request) -> dict[str, object]:
    try:
        task = await _manager(request).retry(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except InvalidTaskTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return task.to_dict()


@router.post("/retry-failed")
async def retry_failed(request: Request) -> dict[str, object]:
    manager = _manager(request)
    tasks = await manager.list_tasks(active_only=False, limit=1000)
    retried = []
    for task in tasks:
        if task.status == "failed":
            retried.append((await manager.retry(task.id)).to_dict())
    return {"retried": retried}


@router.post("/{task_id}/conflict-resolution")
async def resolve_conflict(task_id: str, payload: ConflictResolutionRequest, request: Request) -> dict[str, object]:
    try:
        task = await _manager(request).resolve_conflict(task_id, payload.resolution)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except InvalidTaskTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return task.to_dict()


@events_router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    manager = getattr(websocket.app.state, "download_manager", None)
    if manager is None:
        await websocket.close(code=1013)
        return
    queue = manager.events.subscribe()
    await websocket.accept()
    incoming = asyncio.create_task(websocket.receive_text())
    outgoing = asyncio.create_task(queue.get())
    try:
        while True:
            done, _ = await asyncio.wait({incoming, outgoing}, return_when=asyncio.FIRST_COMPLETED)
            if incoming in done:
                try:
                    message = incoming.result()
                except WebSocketDisconnect:
                    break
                if message == "ping":
                    await websocket.send_json({"type": "connection.pong", "data": {}, "occurred_at": None})
                incoming = asyncio.create_task(websocket.receive_text())
            if outgoing in done:
                event = outgoing.result()
                await websocket.send_json(event.to_dict())
                outgoing = asyncio.create_task(queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        incoming.cancel()
        outgoing.cancel()
        await asyncio.gather(incoming, outgoing, return_exceptions=True)
        manager.events.unsubscribe(queue)
