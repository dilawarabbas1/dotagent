"""Schema-version migration for dotagent projects.

Three install modes detected by `detector.detect_mode()`:

- `FRESH`        — no .git, no .agent (user should run `dotagent init`)
- `MID_PROJECT`  — .git exists, no .agent (user should run `dotagent init`)
- `PRE_V0_4`     — .agent exists but no .version stamp (legacy)
- `UPGRADE`      — .version stamp present but < current schema version
- `CURRENT`      — .version matches current schema version (no-op)

The `migrate()` entry point routes by mode. Every change is recorded in
`.agent/.migration-log.md` so `migrate --rollback` can reverse it.

Per-version migrators live in their own module (`v0_3_to_v0_4.py`).
Adding a new version pair = adding one module + registering it in
`_MIGRATORS` below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .detector import Mode, detect_mode
from .log import MigrationLog, MigrationStep, write_log
from .v0_3_to_v0_4 import migrate_v0_3_to_v0_4


@dataclass
class MigrationPlan:
    """What `migrate()` will do, in order. Used by `--plan` preview."""
    mode: Mode
    from_version: str | None
    to_version: str
    steps: list[MigrationStep] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "steps": [s.to_dict() for s in self.steps],
            "notes": self.notes,
        }


# Ordered chain of per-version-pair migrators.
# Each entry: (from_version_prefix, to_version, migrator_callable).
# The migrator returns the list of MigrationStep it WOULD execute (plan mode)
# or DID execute (write mode); it never raises for missing-input cases — the
# detector has already filtered those.
_MIGRATORS = (
    (None,   "0.4.0", migrate_v0_3_to_v0_4),  # None = no version stamp = pre-v0.4
    ("0.3",  "0.4.0", migrate_v0_3_to_v0_4),
)


def build_plan(repo: Path) -> MigrationPlan:
    """Compute the migration plan WITHOUT making any changes."""
    mode = detect_mode(repo)
    from_version = _read_version(repo)

    plan = MigrationPlan(
        mode=mode,
        from_version=from_version,
        to_version=_target_version(from_version),
    )

    if mode in (Mode.FRESH, Mode.MID_PROJECT):
        plan.notes.append(
            "no .agent/ directory found — run `dotagent init` to initialize this repo."
        )
        return plan
    if mode is Mode.CURRENT:
        plan.notes.append(
            f"already on schema version {from_version}; nothing to do."
        )
        return plan

    # Pre-v0.4 or upgrade: run each applicable migrator in plan mode.
    for from_prefix, to_version, migrator in _MIGRATORS:
        if _migrator_applies(from_version, from_prefix, to_version):
            plan.steps.extend(migrator(repo, write=False))
    return plan


def apply_plan(repo: Path, plan: MigrationPlan, *, log: bool = True) -> list[MigrationStep]:
    """Execute the plan. Returns the list of steps actually performed.

    If `log=True`, appends to `.agent/.migration-log.md`.
    """
    if plan.mode in (Mode.FRESH, Mode.MID_PROJECT, Mode.CURRENT):
        return []

    executed: list[MigrationStep] = []
    for from_prefix, to_version, migrator in _MIGRATORS:
        if _migrator_applies(plan.from_version, from_prefix, to_version):
            executed.extend(migrator(repo, write=True))

    if log and executed:
        write_log(repo, plan.from_version, plan.to_version, executed)

    return executed


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _read_version(repo: Path) -> str | None:
    """Read `.agent/.version`. None if absent."""
    f = repo / ".agent" / ".version"
    if not f.exists():
        return None
    try:
        return f.read_text().strip() or None
    except OSError:
        return None


def _target_version(from_version: str | None) -> str:
    """The version this migrate run will produce."""
    # For now, the only chain is to 0.4.0. As new migrators land, this picks
    # the highest applicable target.
    return "0.4.0"


def _migrator_applies(
    from_version: str | None, from_prefix: str | None, to_version: str
) -> bool:
    """True iff a migrator with `from_prefix → to_version` applies right now.

    Special case: `from_prefix is None` matches a missing version stamp.
    Otherwise, matches if the actual from_version starts with the prefix
    and the current install is older than `to_version`.
    """
    if from_prefix is None:
        return from_version is None
    if from_version is None:
        return False
    if not from_version.startswith(from_prefix + "."):
        return False
    # Cheap version comparison: only upgrades, never downgrades.
    return from_version < to_version


__all__ = (
    "Mode",
    "MigrationPlan",
    "MigrationStep",
    "MigrationLog",
    "build_plan",
    "apply_plan",
    "detect_mode",
)
