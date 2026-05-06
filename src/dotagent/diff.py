"""Unified-diff helper for --dry-run."""

from __future__ import annotations

import difflib
from pathlib import Path

from .adapters.base import RenderedFile


def diff_rendered(files: list[RenderedFile]) -> list[tuple[Path, str]]:
    """Return [(path, diff_text)] for each rendered file vs its on-disk version."""
    out: list[tuple[Path, str]] = []
    for f in files:
        old = f.path.read_text(errors="replace") if f.path.exists() else ""
        new = f.content
        if old == new:
            continue
        diff = "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{f.path.name}",
                tofile=f"b/{f.path.name}",
                n=3,
            )
        )
        out.append((f.path, diff))
    return out


def format_diff(diffs: list[tuple[Path, str]]) -> str:
    if not diffs:
        return "(no changes)"
    parts: list[str] = []
    for path, text in diffs:
        parts.append(f"--- {path} ---\n{text}")
    return "\n".join(parts)
