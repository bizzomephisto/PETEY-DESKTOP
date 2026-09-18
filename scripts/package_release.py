#!/usr/bin/env python3
"""Build a reviewed PETEY source ZIP from Git's non-ignored file set."""

from __future__ import annotations

import hashlib
import stat
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FORBIDDEN_ROOTS = {"blender_mcp", "examples", "peteyai", "peteyvenv"}
RELEASE_TIMESTAMP = (2026, 9, 18, 0, 0, 0)


def release_files() -> list[Path]:
    """Return the tracked and non-ignored files eligible for the release."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = [Path(raw.decode("utf-8")) for raw in result.stdout.split(b"\0") if raw]
    files: list[Path] = []
    for relative in sorted(paths, key=lambda path: path.as_posix()):
        if relative.parts[0] in FORBIDDEN_ROOTS:
            raise RuntimeError(f"forbidden release path: {relative}")
        if relative.name == "petey-addon.json":
            raise RuntimeError(f"external add-on manifest in release: {relative}")
        if relative.name == ".env":
            raise RuntimeError("private .env file in release")

        source = ROOT / relative
        if source.is_symlink():
            raise RuntimeError(f"release symlinks are not allowed: {relative}")
        if source.is_file():
            files.append(relative)
    return files


def build_release(destination: Path | None = None) -> tuple[Path, int, str]:
    from petey.version import __version__

    files = release_files()
    destination = destination or ROOT / "dist" / f"PETEY-v{__version__}-source.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"PETEY-v{__version__}"

    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in files:
            source = ROOT / relative
            info = ZipInfo(f"{prefix}/{relative.as_posix()}", RELEASE_TIMESTAMP)
            mode = source.stat().st_mode
            permissions = 0o755 if mode & stat.S_IXUSR else 0o644
            info.external_attr = (stat.S_IFREG | permissions) << 16
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, source.read_bytes(), compresslevel=9)

    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return destination, len(files), digest


def main() -> None:
    destination, count, digest = build_release()
    print(f"Created {destination}")
    print(f"Files: {count}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
