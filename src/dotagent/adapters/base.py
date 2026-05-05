from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ..paths import Paths


@dataclass
class RenderedFile:
    path: Path
    content: str


class Adapter(ABC):
    name: str = "base"

    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    @abstractmethod
    def render(self, source: dict) -> list[RenderedFile]:
        ...

    def write(self, files: list[RenderedFile]) -> list[Path]:
        written: list[Path] = []
        for f in files:
            f.path.parent.mkdir(parents=True, exist_ok=True)
            f.path.write_text(f.content)
            written.append(f.path)
        return written


def read_source(paths: Paths) -> dict:
    """Load the five source markdown files. Missing files become empty strings."""

    def _read(p: Path) -> str:
        return p.read_text() if p.exists() else ""

    return {
        "style": _read(paths.style),
        "rules": _read(paths.rules),
        "architecture": _read(paths.architecture),
        "patterns": _read(paths.patterns),
        "preferences": _read(paths.preferences),
    }
