import pytest

from backend.rules.engine import RuleEngine
from backend.rules.models import RuleDefinition
from backend.rules.parser import RuleParser
from backend.rules.renderer import RuleRenderer, RuleValidationError, URLValidator


def test_parser_skips_blank_rows_and_keeps_original_line_numbers() -> None:
    rows = RuleParser().parse("\n plugin 1.2\n\nonly-name\nplugin 2.0 file.jar zip")

    assert [row.line_number for row in rows] == [2, 4, 5]
    assert rows[0].filename == "plugin"
    assert rows[1].error
    assert rows[2].filename == "file.jar"
    assert rows[2].ext == "zip"


def test_engine_keeps_valid_rows_when_another_row_is_invalid() -> None:
    rule = RuleDefinition("test", "Test", "https://example.test/base/",
                          "{base_url}/{name}/{version}/{filename}.{ext}",
                          "{filename}.{ext}", "hpi", False)

    preview = RuleEngine().preview(rule, "good 1.0\nbad\nother 2.0 file")
    specs = RuleEngine().create_task_specs(rule, preview)

    assert [row.valid for row in preview] == [True, False, True]
    assert preview[0].url == "https://example.test/base/good/1.0/good.hpi"
    assert [(spec.url, spec.filename) for spec in specs] == [
        (preview[0].url, preview[0].filename),
        (preview[2].url, preview[2].filename),
    ]


@pytest.mark.parametrize("template", ["https://example.test/{unknown}", "https://example.test/{name"])
def test_renderer_rejects_unknown_or_malformed_template_variables(template: str) -> None:
    rule = RuleDefinition("test", "Test", "https://example.test", template,
                          "{filename}.{ext}", "zip", False)

    row = RuleEngine().preview(rule, "thing 1.0")[0]

    assert not row.valid
    assert row.error


@pytest.mark.parametrize("url", ["file:///tmp/a", "ftp://example.test/a", "https://user:pass@example.test/a", "https://example.test:99999/a"])
def test_url_validator_accepts_only_safe_absolute_http_urls(url: str) -> None:
    with pytest.raises(RuleValidationError):
        URLValidator.validate(url)


def test_renderer_rejects_windows_device_names() -> None:
    rule = RuleDefinition("test", "Test", "https://example.test", "{base_url}/{name}",
                          "{filename}.{ext}", "", False)

    preview = RuleEngine().preview(rule, "x 1 CON.txt")[0]

    assert not preview.valid
    assert "Windows cannot use" in (preview.error or "")
