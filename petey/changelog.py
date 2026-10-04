"""Read the bundled changelog into safe, structured release notes."""

from __future__ import annotations

import re
from pathlib import Path


RELEASE_HEADING = re.compile(r"^## (v\d+\.\d+\.\d+(?:-[\w.]+)?)(?:\s+—\s+(.+))?$")


def _plain(text: str) -> str:
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    return text.replace("**", "").replace("`", "").strip()


def load_changelog(path: str | Path) -> list[dict]:
    """Parse headings, paragraphs and bullets without rendering Markdown as HTML."""
    releases: list[dict] = []
    current: dict | None = None
    block: dict | None = None

    def flush() -> None:
        nonlocal block
        if current is not None and block is not None:
            block["text"] = _plain(block["text"])
            current["blocks"].append(block)
        block = None

    for line in Path(path).read_text(encoding="utf-8").splitlines():
        heading = RELEASE_HEADING.match(line)
        if heading:
            flush()
            current = {"version": heading.group(1), "date": heading.group(2) or "", "blocks": []}
            releases.append(current)
            continue
        if current is None:
            continue
        if not line.strip():
            flush()
        elif line.startswith("### "):
            flush()
            current["blocks"].append({"type": "heading", "text": _plain(line[4:])})
        elif line.startswith("- "):
            flush()
            block = {"type": "bullet", "text": line[2:].strip()}
        elif block is None:
            block = {"type": "paragraph", "text": line.strip()}
        else:
            block["text"] += " " + line.strip()
    flush()
    return releases
