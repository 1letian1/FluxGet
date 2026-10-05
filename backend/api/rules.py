"""Rule catalog, persistence, and renderer-backed preview endpoints."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.rules.builtins import JENKINS_HPI_RULE
from backend.rules.engine import RuleEngine
from backend.rules.models import RuleDefinition

router = APIRouter(prefix="/api/v1/rules", tags=["rules"])


class RuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    base_url: str = Field(max_length=2048)
    url_template: str = Field(min_length=1, max_length=2048)
    filename_template: str = Field(min_length=1, max_length=255)
    default_ext: str = Field(default="", max_length=32)

    @field_validator("name", "url_template", "filename_template")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field must not be empty")
        return value

    @field_validator("base_url", "default_ext")
    @classmethod
    def trim_optional_values(cls, value: str) -> str:
        return value.strip()


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inputs: str = Field(min_length=1, max_length=1_000_000)
    base_url: str | None = Field(default=None, max_length=2048)


def _database(request: Request):
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(status_code=503, detail="Database is unavailable")
    return database


async def seed_builtin_rules(database) -> None:
    rule = JENKINS_HPI_RULE
    async with database.connect() as connection:
        await connection.execute(
            "INSERT OR IGNORE INTO rules (id, name, base_url, url_template, filename_template, default_ext, builtin, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (rule.id, rule.name, rule.base_url, rule.url_template, rule.filename_template, rule.default_ext),
        )
        await connection.commit()


@router.get("")
async def list_rules(request: Request) -> dict[str, list[dict[str, object]]]:
    async with _database(request).connect() as connection:
        cursor = await connection.execute(
            "SELECT id, name, base_url, url_template, filename_template, default_ext, builtin FROM rules ORDER BY builtin DESC, name COLLATE NOCASE"
        )
        rows = await cursor.fetchall()
    return {"items": [dict(row) for row in rows]}


@router.post("", status_code=201)
async def create_rule(payload: RuleInput, request: Request) -> dict[str, object]:
    database = _database(request)
    rule_id = f"custom:{uuid4()}"
    values = payload.model_dump()
    try:
        async with database.connect() as connection:
            await connection.execute(
                "INSERT INTO rules (id, name, base_url, url_template, filename_template, default_ext, builtin, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 0, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                (rule_id, values["name"].strip(), values["base_url"].strip(), values["url_template"].strip(), values["filename_template"].strip(), values["default_ext"].strip().lstrip(".")),
            )
            await connection.commit()
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="A rule with this name already exists") from exc
        raise
    return {"id": rule_id, **values, "name": values["name"].strip(), "builtin": False}


@router.put("/{rule_id}")
async def update_rule(rule_id: str, payload: RuleInput, request: Request) -> dict[str, object]:
    database = _database(request)
    values = payload.model_dump()
    try:
        async with database.connect() as connection:
            cursor = await connection.execute("SELECT builtin FROM rules WHERE id = ?", (rule_id,))
            row = await cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Rule not found")
            if row["builtin"]:
                raise HTTPException(status_code=409, detail="Built-in rules cannot be edited")
            await connection.execute(
                "UPDATE rules SET name = ?, base_url = ?, url_template = ?, filename_template = ?, default_ext = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                (values["name"].strip(), values["base_url"].strip(), values["url_template"].strip(), values["filename_template"].strip(), values["default_ext"].strip().lstrip("."), rule_id),
            )
            await connection.commit()
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="A rule with this name already exists") from exc
        raise
    return {"id": rule_id, **values, "name": values["name"].strip(), "builtin": False}


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str, request: Request) -> dict[str, bool]:
    async with _database(request).connect() as connection:
        cursor = await connection.execute("SELECT builtin FROM rules WHERE id = ?", (rule_id,))
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Rule not found")
        if row["builtin"]:
            raise HTTPException(status_code=409, detail="Built-in rules cannot be deleted")
        await connection.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        await connection.commit()
    return {"deleted": True}


@router.post("/{rule_id}/preview")
async def preview_rule(rule_id: str, payload: PreviewInput, request: Request) -> dict[str, list[dict[str, object]]]:
    async with _database(request).connect() as connection:
        cursor = await connection.execute(
            "SELECT id, name, base_url, url_template, filename_template, default_ext, builtin FROM rules WHERE id = ?",
            (rule_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule = RuleDefinition(**dict(row))
    if payload.base_url is not None:
        rule = replace(rule, base_url=payload.base_url.strip())
    previews = RuleEngine().preview(rule, payload.inputs)
    return {"items": [{**item.__dict__, "valid": item.valid} for item in previews]}
