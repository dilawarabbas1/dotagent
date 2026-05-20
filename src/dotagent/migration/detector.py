"""Detect which install mode a repo is in.

Pure read-only. Looks at filesystem signals; does not parse or validate.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from ..canonical_structure import CURRENT_SCHEMA_VERSION


class Mode(str, Enum):
    """Install-mode classification.

    Three install scenarios (FRESH / MID_PROJECT / PRE_V0_4) plus two
    computed states (CURRENT, UPGRADE) that distinguish a clean install
    from one that needs a schema bump.
    """
    FRESH = "fresh"                # no .git, no .agent → user should `dotagent init`
    MID_PROJECT = "mid-project"    # .git exists, no .agent → user should `dotagent init`
    PRE_V0_4 = "pre-v0.4"          # .agent exists, no .version stamp
    UPGRADE = "upgrade"            # .version exists but is older than current
    CURRENT = "current"            # .version matches CURRENT_SCHEMA_VERSION


def detect_mode(repo: Path) -> Mode:
    """Return the Mode for `repo`. No filesystem changes."""
    has_git = (repo / ".git").exists()
    agent_dir = repo / ".agent"
    has_agent = agent_dir.is_dir()
    version_file = agent_dir / ".version"

    if not has_agent and not has_git:
        return Mode.FRESH
    if not has_agent and has_git:
        return Mode.MID_PROJECT
    if not version_file.exists():
        return Mode.PRE_V0_4

    try:
        actual = version_file.read_text().strip()
    except OSError:
        actual = ""

    if not actual:
        return Mode.PRE_V0_4
    if actual == CURRENT_SCHEMA_VERSION:
        return Mode.CURRENT
    if actual < CURRENT_SCHEMA_VERSION:
        return Mode.UPGRADE
    # actual > CURRENT_SCHEMA_VERSION means the install was written by a
    # newer dotagent than this one. We surface it as CURRENT (don't try to
    # "downgrade"); doctor will warn separately.
    return Mode.CURRENT


__all__ = ("Mode", "detect_mode")
