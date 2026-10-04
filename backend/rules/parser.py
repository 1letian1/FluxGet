"""Line-oriented rule input parser.

The accepted current format is two to four whitespace-separated fields:
name, version, optional filename, optional extension. This is deterministic
and matches the examples currently used in the frontend. Legacy HPI behavior
is still pending its original sample input.
"""

from __future__ import annotations

import re

from backend.rules.models import ParsedInput


_EXTENSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")


class RuleParser:
    def parse(self, text: str, default_ext: str = "") -> list[ParsedInput]:
        results: list[ParsedInput] = []
        for line_number, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            fields = raw.split()
            if len(fields) < 2 or len(fields) > 4:
                results.append(ParsedInput(
                    line_number=line_number,
                    raw=raw,
                    error="Expected name and version, with optional filename and extension",
                ))
                continue

            name, version = fields[:2]
            filename = fields[2] if len(fields) >= 3 else name
            ext = fields[3] if len(fields) == 4 else default_ext
            if not self._valid_field(name) or not self._valid_field(version):
                results.append(ParsedInput(line_number, raw, error="Name and version must be valid single-line values"))
                continue
            if not self._valid_field(filename):
                results.append(ParsedInput(line_number, raw, error="Filename must be a valid single-line value"))
                continue
            ext = ext.removeprefix(".")
            if ext and not _EXTENSION.fullmatch(ext):
                results.append(ParsedInput(line_number, raw, error="Extension may contain only letters, digits, '_' or '-'"))
                continue
            results.append(ParsedInput(line_number, raw, name, version, filename, ext))
        return results

    @staticmethod
    def _valid_field(value: str) -> bool:
        return bool(value.strip()) and not any(ord(char) < 32 for char in value) and "\x00" not in value
