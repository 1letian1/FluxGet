"""Single source of truth for URL and filename rendering and validation."""

from __future__ import annotations

import re
import string
from urllib.parse import quote, urlsplit

from backend.rules.models import ParsedInput, RuleDefinition, RulePreview


ALLOWED_VARIABLES = frozenset({"base_url", "name", "version", "filename", "ext"})
_WINDOWS_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.IGNORECASE)
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class RuleValidationError(ValueError):
    pass


class URLValidator:
    @staticmethod
    def validate(url: str) -> str:
        try:
            parts = urlsplit(url)
            # Accessing port also validates malformed/out-of-range port values.
            _ = parts.port
        except ValueError as exc:
            raise RuleValidationError("Generated URL is malformed") from exc
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise RuleValidationError("Generated URL must be an absolute HTTP or HTTPS URL")
        if parts.username is not None or parts.password is not None:
            raise RuleValidationError("Generated URL must not contain credentials")
        if any(ord(char) < 32 or char.isspace() for char in url):
            raise RuleValidationError("Generated URL must not contain whitespace or control characters")
        return url


class RuleRenderer:
    def render(self, rule: RuleDefinition, parsed: ParsedInput) -> RulePreview:
        if parsed.error:
            return RulePreview(parsed.line_number, parsed.raw, error=parsed.error)
        try:
            self._validate_template(rule.url_template, "URL")
            self._validate_template(rule.filename_template, "filename")
            values = {
                "base_url": rule.base_url.rstrip("/"),
                "name": parsed.name,
                "version": parsed.version,
                "filename": parsed.filename,
                "ext": parsed.ext or rule.default_ext.removeprefix("."),
            }
            url = self._format_url(rule.url_template, values)
            url = self._normalize_url_separators(url)
            URLValidator.validate(url)
            filename = self._format_filename(rule.filename_template, values)
            self._validate_filename(filename)
            return RulePreview(parsed.line_number, parsed.raw, parsed.name, parsed.version, url, filename)
        except RuleValidationError as exc:
            return RulePreview(parsed.line_number, parsed.raw, parsed.name, parsed.version, error=str(exc))

    @staticmethod
    def _validate_template(template: str, label: str) -> None:
        if not template.strip():
            raise RuleValidationError(f"{label} template must not be empty")
        try:
            fields = [field for _, field, _, _ in string.Formatter().parse(template) if field is not None]
        except ValueError as exc:
            raise RuleValidationError(f"{label} template has invalid brace syntax") from exc
        unknown = sorted(set(fields) - ALLOWED_VARIABLES)
        if unknown:
            raise RuleValidationError(f"{label} template contains unsupported variable: {{{unknown[0]}}}")
        if any(not field or any(char in field for char in ".[]") for field in fields):
            raise RuleValidationError(f"{label} template contains an invalid variable")

    @staticmethod
    def _format_url(template: str, values: dict[str, str]) -> str:
        # Encode user supplied path/query values while retaining URL syntax in base_url.
        formatter = string.Formatter()
        chunks: list[str] = []
        try:
            for literal, field, _, _ in formatter.parse(template):
                chunks.append(literal)
                if field is not None:
                    if field not in values:
                        raise RuleValidationError(f"URL template contains unsupported variable: {{{field}}}")
                    value = values[field]
                    chunks.append(value if field == "base_url" else quote(value, safe=""))
        except ValueError as exc:
            raise RuleValidationError("URL template has invalid brace syntax") from exc
        return "".join(chunks)

    @staticmethod
    def _format_filename(template: str, values: dict[str, str]) -> str:
        try:
            return template.format_map(values).strip()
        except (KeyError, ValueError) as exc:
            raise RuleValidationError("Filename template could not be rendered") from exc

    @staticmethod
    def _normalize_url_separators(url: str) -> str:
        # Normalize repeated slashes only in the URL path, preserving scheme and authority.
        try:
            parts = urlsplit(url)
        except ValueError as exc:
            raise RuleValidationError("Generated URL is malformed") from exc
        path = re.sub(r"/{2,}", "/", parts.path)
        return parts._replace(path=path).geturl()

    @staticmethod
    def _validate_filename(filename: str) -> None:
        if not filename or filename in {".", ".."}:
            raise RuleValidationError("Rendered filename must not be empty or a path component")
        if _INVALID_FILENAME.search(filename) or filename.endswith((".", " ")):
            raise RuleValidationError("Rendered filename contains characters Windows cannot use")
        if _WINDOWS_RESERVED.fullmatch(filename):
            raise RuleValidationError("Rendered filename is a reserved Windows device name")
        if len(filename) > 255:
            raise RuleValidationError("Rendered filename exceeds 255 characters")
