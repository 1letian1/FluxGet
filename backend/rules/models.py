"""Immutable data objects shared by the rule engine stages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    name: str
    base_url: str
    url_template: str
    filename_template: str
    default_ext: str = ""
    builtin: bool = False


@dataclass(frozen=True)
class ParsedInput:
    line_number: int
    raw: str
    name: str = ""
    version: str = ""
    filename: str = ""
    ext: str = ""
    error: str | None = None


@dataclass(frozen=True)
class RulePreview:
    line_number: int
    raw: str
    name: str = ""
    version: str = ""
    url: str = ""
    filename: str = ""
    error: str | None = None

    @property
    def valid(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class TaskSpec:
    """Validated task input; persistence and scheduling belong to later stages."""

    url: str
    filename: str
    source_type: str = "rule"
    rule_id: str = ""
