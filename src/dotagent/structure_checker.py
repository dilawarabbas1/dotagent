"""Check a repo's filesystem against the canonical structure schema.

Pure read-only audit. Returns a list of `Deviation` objects; never modifies
anything on disk. The checker is the engine behind `dotagent doctor`'s
structure check and `dotagent structure check`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .canonical_structure import (
    CURRENT_SCHEMA_VERSION,
    KIND_DIR,
    KIND_FILE,
    KIND_GENERATED,
    KIND_OPTIONAL,
    SchemaEntry,
    detect_tier,
    schema_for,
)


# Deviation severities. Map cleanly to doctor's existing fail/warn/info levels.
SEVERITY_FAIL = "fail"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"


@dataclass
class Deviation:
    """One thing the filesystem disagrees with the schema about."""
    path: str
    severity: str  # fail | warn | info
    reason: str
    fix: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "severity": self.severity,
            "reason": self.reason,
            "fix": self.fix,
        }


@dataclass
class CheckResult:
    """Outcome of one `check()` run."""
    tier: str
    schema_version: str
    actual_version: str | None
    deviations: list[Deviation]

    @property
    def ok(self) -> bool:
        return not any(d.severity == SEVERITY_FAIL for d in self.deviations)

    @property
    def needs_migration(self) -> bool:
        return self.actual_version != self.schema_version

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "schema_version": self.schema_version,
            "actual_version": self.actual_version,
            "ok": self.ok,
            "needs_migration": self.needs_migration,
            "deviations": [d.to_dict() for d in self.deviations],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check(repo: Path, tier: str | None = None) -> CheckResult:
    """Audit `repo` against the canonical schema.

    If `tier` is None, infers it from filesystem signals via `detect_tier`.
    Returns a CheckResult with every deviation, sorted: fails first, then
    warns, then info.
    """
    if tier is None:
        tier = detect_tier(repo)

    schema = schema_for(tier)
    actual_version = _read_version(repo)
    deviations: list[Deviation] = []

    for entry in schema:
        deviations.extend(_check_entry(repo, entry))

    if actual_version is not None and actual_version != CURRENT_SCHEMA_VERSION:
        deviations.append(Deviation(
            path=".agent/.version",
            severity=SEVERITY_WARN,
            reason=(
                f"schema version is {actual_version!r}; "
                f"current dotagent expects {CURRENT_SCHEMA_VERSION!r}"
            ),
            fix="run `dotagent migrate` to upgrade",
        ))

    # Stable sort: fail > warn > info, then alphabetic by path.
    _sev_order = {SEVERITY_FAIL: 0, SEVERITY_WARN: 1, SEVERITY_INFO: 2}
    deviations.sort(key=lambda d: (_sev_order.get(d.severity, 99), d.path))

    return CheckResult(
        tier=tier,
        schema_version=CURRENT_SCHEMA_VERSION,
        actual_version=actual_version,
        deviations=deviations,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _read_version(repo: Path) -> str | None:
    """Read `.agent/.version`. None if absent or unreadable."""
    version_file = repo / ".agent" / ".version"
    if not version_file.exists():
        return None
    try:
        text = version_file.read_text().strip()
    except OSError:
        return None
    return text or None


def _check_entry(repo: Path, entry: SchemaEntry) -> list[Deviation]:
    """Validate one schema entry. Returns 0..1 deviations."""
    target = repo / entry.path
    exists = target.exists()

    # Kind-specific expectations.
    if entry.kind == KIND_DIR:
        return _check_dir(target, entry, exists)
    if entry.kind == KIND_FILE:
        return _check_file(target, entry, exists)
    if entry.kind == KIND_GENERATED:
        return _check_generated(target, entry, exists)
    if entry.kind == KIND_OPTIONAL:
        return []  # optional entries are never flagged
    return []


def _check_dir(target: Path, entry: SchemaEntry, exists: bool) -> list[Deviation]:
    if not exists:
        if entry.required:
            return [Deviation(
                path=entry.path,
                severity=SEVERITY_FAIL,
                reason=f"required directory missing ({entry.description or 'no description'})",
                fix=f"create the directory: mkdir -p {entry.path}",
            )]
        return []
    if not target.is_dir():
        return [Deviation(
            path=entry.path,
            severity=SEVERITY_FAIL,
            reason="expected a directory, found a file",
            fix=f"remove the file at {entry.path} and create a directory",
        )]
    return []


def _check_file(target: Path, entry: SchemaEntry, exists: bool) -> list[Deviation]:
    if not exists:
        if entry.required:
            return [Deviation(
                path=entry.path,
                severity=SEVERITY_FAIL,
                reason=f"required file missing ({entry.description or 'no description'})",
                fix=f"create {entry.path} or run `dotagent migrate`",
            )]
        return []
    if not target.is_file():
        return [Deviation(
            path=entry.path,
            severity=SEVERITY_FAIL,
            reason="expected a file, found a directory",
            fix=f"remove the directory at {entry.path} and create a file",
        )]
    return []


def _check_generated(target: Path, entry: SchemaEntry, exists: bool) -> list[Deviation]:
    if not exists:
        # Generated files are always optional on disk — they materialize on
        # the first `dotagent sync` after content is present.
        return []
    if not target.is_file():
        return [Deviation(
            path=entry.path,
            severity=SEVERITY_FAIL,
            reason="expected a generated file, found a directory",
            fix=f"remove the directory at {entry.path}",
        )]
    # Generated files SHOULD carry the banner; absence is a warning, not
    # a fail (hand-written content at a generated-file path indicates the
    # user lost the banner via direct edit).
    if not _has_generated_banner(target):
        return [Deviation(
            path=entry.path,
            severity=SEVERITY_WARN,
            reason="generated file is missing the dotagent banner; may have been hand-edited",
            fix=f"re-run the relevant sync/regenerate command to restore",
        )]
    return []


# Lowercase forms; the comparison is case-insensitive so both
# "GENERATED by dotagent" (preferred) and "generated by dotagent"
# (existing renderer) are accepted.
_GENERATED_BANNER_MARKERS = (
    "generated by dotagent",
)


def _has_generated_banner(file: Path) -> bool:
    """Cheap check for the auto-generated banner in the first few lines."""
    try:
        with file.open("r", encoding="utf-8", errors="replace") as fh:
            head = "".join(fh.readline() for _ in range(5))
    except OSError:
        return False
    head_lower = head.lower()
    return any(marker in head_lower for marker in _GENERATED_BANNER_MARKERS)


__all__ = (
    "SEVERITY_FAIL",
    "SEVERITY_WARN",
    "SEVERITY_INFO",
    "Deviation",
    "CheckResult",
    "check",
)
