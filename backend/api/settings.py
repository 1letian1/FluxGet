"""REST endpoints for persisted application settings."""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from backend.persistence.settings import AppSettings, SettingsService


router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_dir: str = Field(min_length=1, max_length=32767)
    subdir: str = Field(max_length=32767)
    concurrency: StrictInt = Field(ge=1, le=32)
    max_retries: StrictInt = Field(ge=0)
    conflict_policy: Literal["overwrite", "rename", "skip", "ask"]
    current_mode: Literal["direct", "rule"]

    @field_validator("output_dir", "subdir")
    @classmethod
    def reject_null_bytes(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Paths cannot contain null bytes")
        return value.strip() if value else value

    @field_validator("output_dir")
    @classmethod
    def require_output_dir(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("output_dir must not be empty")
        value = value.strip()
        if not os.path.isabs(value):
            raise ValueError("output_dir must be an absolute path")
        return value


class SettingsResponse(SettingsUpdate):
    updated_at: str


def _service(request: Request) -> SettingsService:
    service = getattr(request.app.state, "settings_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Settings service is unavailable")
    return service


@router.get("", response_model=SettingsResponse)
async def get_settings(request: Request) -> SettingsResponse:
    settings = await _service(request).get()
    return SettingsResponse(**settings.__dict__)


@router.put("", response_model=SettingsResponse)
async def update_settings(payload: SettingsUpdate, request: Request) -> SettingsResponse:
    settings = AppSettings(**payload.model_dump())
    saved = await _service(request).update(settings)
    manager = getattr(request.app.state, "download_manager", None)
    if manager is not None:
        await manager.configure(
            concurrency=saved.concurrency,
            max_retries=saved.max_retries,
            conflict_policy=saved.conflict_policy,
        )
    return SettingsResponse(**saved.__dict__)
