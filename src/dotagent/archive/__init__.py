"""Document lifecycle / archive policy.

Active content lives in `docs/*.md`. As entries become historical (fixed
bugs, rescinded anti-patterns, shipped-and-stable modules), they move to
`docs/archive/YYYY/*.md` so the active surface stays small.

This package provides:

- `scan(repo)`           — read-only audit; returns ArchiveCandidate list
- `run(repo, ...)`       — apply: move eligible entries, write log
- `restore(repo, id)`    — un-archive a single entry by id
- `list_archived(repo)`  — read the archive log

Sources handled in v1: bug-registry (entries with status=fixed). The
framework is extensible: anti-patterns and modules slot into the same
ArchiveCandidate shape via additional triggers.
"""

from __future__ import annotations

from .mover import ArchiveLog, ArchiveResult, run, restore, list_archived
from .triggers import ArchiveCandidate, scan


__all__ = (
    "ArchiveCandidate",
    "ArchiveLog",
    "ArchiveResult",
    "scan",
    "run",
    "restore",
    "list_archived",
)
