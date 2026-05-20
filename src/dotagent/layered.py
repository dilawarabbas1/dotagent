"""Layered context resolution — `parent:` field in `.agent/config.yaml`.

A service repo's `.agent/config.yaml` can declare:

    parent: ../..

This points dotagent at a sibling project-root layer that contributes
cross-cutting content (brief, hard rules, glossary, tenancy posture,
shared architecture). At sync time, parent content is merged BEFORE
local content; local fields override on conflict.

Memory layers (working / episodic / semantic / personal) are NEVER
inherited — they remain service-local.

Cycle detection (depth-3 cap + visited-set) prevents A → B → A loops
from blowing up.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .paths import Paths


MAX_PARENT_DEPTH = 3


@dataclass
class ParentChain:
    """Resolved chain of ancestor `.agent/` directories.

    [closest_parent, ..., root]. Empty when the current repo has no
    `parent:` declared or resolution failed (e.g., cycle, missing path).
    """
    repos: list[Path]


def resolve_parent_chain(paths: Paths) -> ParentChain:
    """Walk `parent:` declarations up to MAX_PARENT_DEPTH.

    Returns an empty chain when:
    - current config has no `parent:` field
    - resolved parent path doesn't contain `.agent/`
    - a cycle is detected
    - depth cap is exceeded (treated as a misconfiguration; logs nothing
      here, doctor surfaces it elsewhere)
    """
    chain: list[Path] = []
    visited: set[Path] = {paths.repo.resolve()}
    current = paths.repo

    for _ in range(MAX_PARENT_DEPTH):
        next_repo = _parent_repo(current)
        if next_repo is None:
            break
        resolved = next_repo.resolve()
        if resolved in visited:
            # cycle detected; stop
            break
        if not (resolved / ".agent").is_dir():
            break
        chain.append(resolved)
        visited.add(resolved)
        current = resolved

    return ParentChain(repos=chain)


def _parent_repo(repo: Path) -> Path | None:
    """Read `parent:` from `<repo>/.agent/config.yaml`, return resolved repo dir.

    Returns None if no parent declared or the file is missing/unreadable.
    """
    cfg = repo / ".agent" / "config.yaml"
    if not cfg.exists():
        return None
    try:
        data = yaml.safe_load(cfg.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return None
    raw_parent = data.get("parent")
    if not raw_parent or not isinstance(raw_parent, str):
        return None
    parent_path = raw_parent.strip()
    if not parent_path:
        return None
    # Relative paths resolve against the repo containing the config.
    candidate = (repo / parent_path).resolve() if not Path(parent_path).is_absolute() \
        else Path(parent_path).resolve()
    if not candidate.exists() or not candidate.is_dir():
        return None
    return candidate


def merge_agent_sources(local, parent_chain: ParentChain, paths: Paths):
    """Overlay parent agent-source content on top of the local layer.

    Strategy: parent goes first (so the user sees project-wide context),
    local goes second and gets a clear divider. Empty fields use parent
    text; non-empty local fields concatenate after parent with a separator.
    """
    if not parent_chain.repos:
        return local

    from .context import AgentSources
    # Build the "parent merged" string from the chain (root first, working down)
    parent_chain_iter = list(reversed(parent_chain.repos))  # root → closest
    parent_style: list[str] = []
    parent_rules: list[str] = []
    parent_architecture: list[str] = []
    parent_patterns: list[str] = []
    parent_preferences: list[str] = []

    for parent_repo in parent_chain_iter:
        parent_paths = Paths(repo=parent_repo)
        if parent_paths.style.exists():
            parent_style.append(parent_paths.style.read_text())
        if parent_paths.rules.exists():
            parent_rules.append(parent_paths.rules.read_text())
        if parent_paths.architecture.exists():
            parent_architecture.append(parent_paths.architecture.read_text())
        if parent_paths.patterns.exists():
            parent_patterns.append(parent_paths.patterns.read_text())
        if parent_paths.preferences.exists():
            parent_preferences.append(parent_paths.preferences.read_text())

    def _stitch(parent_parts: list[str], local_text: str, label: str) -> str:
        if not parent_parts:
            return local_text
        parent_joined = "\n\n".join(p.strip() for p in parent_parts if p.strip())
        if not local_text.strip():
            return f"<!-- inherited from parent ({label}) -->\n\n{parent_joined}\n"
        return (
            f"<!-- inherited from parent ({label}) -->\n\n"
            + parent_joined
            + f"\n\n<!-- service-local ({label}) -->\n\n"
            + local_text
        )

    return AgentSources(
        style=_stitch(parent_style, local.style, "style.md"),
        rules=_stitch(parent_rules, local.rules, "rules.md"),
        architecture=_stitch(parent_architecture, local.architecture, "architecture.md"),
        patterns=_stitch(parent_patterns, local.patterns, "patterns.md"),
        preferences=_stitch(parent_preferences, local.preferences, "preferences.md"),
    )


def load_parent_brief(parent_chain: ParentChain):
    """Return the closest parent's project_brief.md (Brief) if present, else None."""
    if not parent_chain.repos:
        return None
    from .project.brief import load
    for parent_repo in parent_chain.repos:
        brief_path = parent_repo / ".agent" / "project_brief.md"
        if brief_path.exists():
            return load(brief_path)
    return None


__all__ = (
    "MAX_PARENT_DEPTH",
    "ParentChain",
    "resolve_parent_chain",
    "merge_agent_sources",
    "load_parent_brief",
)
