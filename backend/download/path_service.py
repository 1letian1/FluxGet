"""Cross-platform validation and containment for download paths."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.IGNORECASE)


class UnsafePath(ValueError):
    pass


class PathService:
    @staticmethod
    def safe_filename(value: str) -> str:
        name = unquote(str(value)).strip().rstrip(" .")
        if not name or name in {".", ".."} or _INVALID.search(name) or _RESERVED.match(name):
            raise UnsafePath("Filename contains unsupported characters or a reserved name")
        if len(name) > 240:
            raise UnsafePath("Filename is too long")
        return name

    @staticmethod
    def safe_subdir(value: str) -> tuple[str, ...]:
        if "\x00" in value:
            raise UnsafePath("Output subdirectory contains a null byte")
        normalized = value.replace("\\", "/").strip()
        if not normalized:
            return ()
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
            raise UnsafePath("Output subdirectory must be relative")
        segments = tuple(segment for segment in normalized.split("/") if segment)
        if any(segment in {".", ".."} or _INVALID.search(segment) or _RESERVED.match(segment) for segment in segments):
            raise UnsafePath("Output subdirectory contains an unsafe path segment")
        return segments

    @classmethod
    def resolve_output_path(cls, root: str, subdir: str, filename: str) -> tuple[Path, str]:
        root_candidate = Path(root).expanduser()
        if not root_candidate.is_absolute():
            raise UnsafePath("Download directory must be an absolute path")
        root_path = root_candidate.resolve()
        safe_name = cls.safe_filename(filename)
        target_dir = root_path.joinpath(*cls.safe_subdir(subdir)).resolve()
        try:
            target_dir.relative_to(root_path)
        except ValueError as exc:
            raise UnsafePath("Output path must remain inside the selected download directory") from exc
        return target_dir / safe_name, safe_name

    @staticmethod
    def filename_from_url(url: str) -> str:
        name = Path(unquote(urlsplit(url).path)).name
        return name or "download"
