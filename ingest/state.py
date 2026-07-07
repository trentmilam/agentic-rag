"""Content-hash watermark so a repeat ingest only re-embeds files that actually changed.

Keyed by each file's path relative to ``data/`` (posix-separated, so the watermark is
stable across Windows/Linux) mapped to a sha256 of its raw bytes.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def changed_files(all_files_with_hashes: dict[str, str], old_state: dict[str, str]) -> list[Path]:
    """Files that are new or whose hash differs from the last recorded run."""
    return [
        Path(rel) for rel, chash in all_files_with_hashes.items()
        if old_state.get(rel) != chash
    ]
