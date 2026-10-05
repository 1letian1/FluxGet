"""Check the expected Windows release layout and write SHA-256 checksums."""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zipfile
from pathlib import Path


def is_windows_pe(path: Path) -> bool:
    with path.open("rb") as file:
        if file.read(2) != b"MZ":
            return False
        file.seek(0x3C)
        offset_data = file.read(4)
        if len(offset_data) != 4:
            return False
        offset = struct.unpack("<I", offset_data)[0]
        file.seek(offset)
        return file.read(4) == b"PE\0\0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(release_root: Path) -> list[Path]:
    onefile = release_root / "onefile" / "URLDownloader.exe"
    portable = release_root / "URLDownloader-portable"
    portable_exe = portable / "URLDownloader.exe"
    portable_readme = portable / "README.txt"
    portable_zip = release_root / "URLDownloader-portable.zip"

    required = [onefile, portable_exe, portable_readme, portable_zip]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise ValueError("Missing release artifact(s): " + ", ".join(str(path) for path in missing))
    for executable in (onefile, portable_exe):
        if not is_windows_pe(executable):
            raise ValueError(f"Not a Windows PE executable: {executable}")
    if not any(portable.rglob("python*.dll")):
        raise ValueError("Portable directory does not contain the bundled Python runtime")
    if not (portable / "_internal" / "frontend" / "dist" / "index.html").is_file():
        raise ValueError("Portable directory does not contain the production frontend")

    with zipfile.ZipFile(portable_zip) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise ValueError(f"Portable ZIP has a corrupt member: {bad_member}")
        members = set(archive.namelist())
        if not any(name.endswith("/URLDownloader.exe") for name in members):
            raise ValueError("Portable ZIP does not contain URLDownloader.exe")
        if not any(Path(name).name.lower().startswith("python") and name.lower().endswith(".dll") for name in members):
            raise ValueError("Portable ZIP does not contain the bundled Python runtime")
        if not any(name.endswith("/_internal/frontend/dist/index.html") for name in members):
            raise ValueError("Portable ZIP does not contain the production frontend")
        if not any(name.endswith("/README.txt") for name in members):
            raise ValueError("Portable ZIP does not contain its README")

    checksum_files = [onefile, portable_zip]
    checksum_path = release_root / "SHA256SUMS.txt"
    lines = [f"{sha256(path)}  {path.relative_to(release_root).as_posix()}" for path in checksum_files]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [*checksum_files, checksum_path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        artifacts = verify(args.release_root.resolve())
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Release verification failed: {exc}", file=sys.stderr)
        return 1
    for artifact in artifacts:
        print(f"OK {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
