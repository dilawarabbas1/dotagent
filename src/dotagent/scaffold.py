from __future__ import annotations

from pathlib import Path

from .paths import Paths
from .util import write_text

SOURCE_FILES = [
    "style.md",
    "rules.md",
    "architecture.md",
    "patterns.md",
    "preferences.md",
]

SKILL_FILES = [
    "skills/observer.md",
    "skills/research.md",
    "skills/plan.md",
    "skills/code.md",
    "skills/review.md",
]

TOOL_FILES = [
    "tools/git-proxy.md",
    "tools/pattern-extractor.md",
    "tools/memory-manager.md",
    "tools/debug-investigator.md",
    "tools/deploy-checklist.md",
]


def _scaffold_root() -> Path:
    return Path(__file__).parent / "scaffolds" / "agent"


def _read(name: str) -> str:
    return (_scaffold_root() / name).read_text()


def scaffold_agent_dir(paths: Paths, *, overwrite: bool = False) -> list[Path]:
    """Materialize the canonical .agent/ tree. Idempotent (skips existing files unless overwrite)."""
    written: list[Path] = []
    for rel in SOURCE_FILES + SKILL_FILES + TOOL_FILES:
        target = paths.agent / rel
        if target.exists() and not overwrite:
            continue
        write_text(target, _read(rel))
        written.append(target)
    for d in (
        paths.memory, paths.working, paths.episodic, paths.semantic, paths.personal,
        paths.dream, paths.dream / "candidates", paths.dream / "graduated", paths.dream / "rejected",
        paths.adapters, paths.identity_dir, paths.cache,
    ):
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not keep.exists():
            keep.touch()
    return written
