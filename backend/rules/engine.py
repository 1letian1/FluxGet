"""RuleEngine orchestration without persistence or download scheduling."""

from __future__ import annotations

from backend.rules.models import RuleDefinition, RulePreview, TaskSpec
from backend.rules.parser import RuleParser
from backend.rules.renderer import RuleRenderer


class RuleEngine:
    def __init__(self, parser: RuleParser | None = None, renderer: RuleRenderer | None = None) -> None:
        self.parser = parser or RuleParser()
        self.renderer = renderer or RuleRenderer()

    def preview(self, rule: RuleDefinition, text: str) -> list[RulePreview]:
        parsed_rows = self.parser.parse(text, rule.default_ext)
        return [self.renderer.render(rule, row) for row in parsed_rows]

    def create_task_specs(self, rule: RuleDefinition, preview: list[RulePreview]) -> list[TaskSpec]:
        """Build task inputs from the same preview DTO that the UI displays."""
        return [
            TaskSpec(url=row.url, filename=row.filename, rule_id=rule.id)
            for row in preview
            if row.valid
        ]
