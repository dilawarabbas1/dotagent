"""Archive eligibility triggers.

`scan(repo)` walks every supported source and returns a flat list of
ArchiveCandidate objects — entries that meet the archive criteria for
their source kind. Pure read-only.

Sources supported:

- `bug-registry`   — H2 entries with `status: fixed` AND
                      `fix-frozen: <ISO date>` at least `bug_min_age_days`
                      ago (default 30, override via config).
- `anti-patterns`  — H2 entries with `rescinded: true` (immediate eligibility).
- `modules`        — module dirs whose `module.yaml` has `state: shipped`
                      AND last cycle frozen at least 90 days ago.

Each source is a small function returning candidates. Adding a new source
is one function + one entry in `_SOURCE_HANDLERS`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml


# Defaults — overridable via `.agent/config.yaml::archive.<key>`.
DEFAULT_BUG_MIN_AGE_DAYS = 30
DEFAULT_MODULE_MIN_AGE_DAYS = 90


# Source-kind constants.
KIND_BUG_REGISTRY = "bug-registry"
KIND_ANTI_PATTERNS = "anti-patterns"
KIND_MODULES = "modules"


@dataclass
class ArchiveCandidate:
    """One entry eligible for archival."""
    source_kind: str
    entry_id: str               # e.g. "BUG-007" or "M01"
    source_path: str            # repo-relative path to source file or dir
    title: str = ""
    reason: str = ""            # human-readable explanation of eligibility
    eligible_since: str = ""    # ISO date when the entry became eligible

    def to_dict(self) -> dict:
        return {
            "source_kind": self.source_kind,
            "entry_id": self.entry_id,
            "source_path": self.source_path,
            "title": self.title,
            "reason": self.reason,
            "eligible_since": self.eligible_since,
        }


@dataclass
class ScanReport:
    """Result of `scan()` — all eligibility findings + per-source counts."""
    candidates: list[ArchiveCandidate] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "counts": dict(self.counts),
            "total": len(self.candidates),
        }


def scan(repo: Path, *, now: datetime | None = None) -> ScanReport:
    """Walk every supported source. Return all archive candidates."""
    now = now or datetime.now(timezone.utc)
    report = ScanReport()
    config = _load_archive_config(repo)

    for kind, handler in _SOURCE_HANDLERS:
        found = handler(repo, now=now, config=config)
        report.candidates.extend(found)
        report.counts[kind] = len(found)
    return report


# ---------------------------------------------------------------------------
# Source: bug-registry
# ---------------------------------------------------------------------------

def _scan_bug_registry(
    repo: Path, *, now: datetime, config: dict
) -> list[ArchiveCandidate]:
    bug_file = repo / "docs" / "bug-registry.md"
    if not bug_file.exists():
        return []
    text = bug_file.read_text()
    min_age = config.get("bug_min_age_days", DEFAULT_BUG_MIN_AGE_DAYS)

    candidates: list[ArchiveCandidate] = []
    for h2, body in _split_h2_sections(text):
        entry_id, title = _split_id_title(h2)
        if not entry_id:
            continue
        meta = _parse_inline_metadata(body)
        status = (meta.get("status") or "").lower()
        if status != "fixed":
            continue
        fix_date_str = meta.get("fix-frozen") or meta.get("fixed-at") or meta.get("fixed")
        fix_date = _parse_date(fix_date_str)
        if fix_date is None:
            continue
        age_days = (now - fix_date).days
        if age_days < min_age:
            continue
        candidates.append(ArchiveCandidate(
            source_kind=KIND_BUG_REGISTRY,
            entry_id=entry_id,
            source_path="docs/bug-registry.md",
            title=title,
            reason=f"status=fixed; fix-frozen {age_days}d ago (threshold {min_age}d)",
            eligible_since=fix_date.date().isoformat(),
        ))
    return candidates


# ---------------------------------------------------------------------------
# Source: anti-patterns
# ---------------------------------------------------------------------------

def _scan_anti_patterns(
    repo: Path, *, now: datetime, config: dict
) -> list[ArchiveCandidate]:
    ap_file = repo / "docs" / "anti-patterns.md"
    if not ap_file.exists():
        return []
    text = ap_file.read_text()

    candidates: list[ArchiveCandidate] = []
    for h2, body in _split_h2_sections(text):
        entry_id, title = _split_id_title(h2)
        if not entry_id:
            continue
        meta = _parse_inline_metadata(body)
        rescinded = (meta.get("rescinded") or "").lower()
        if rescinded not in ("true", "yes"):
            continue
        rescinded_at = _parse_date(meta.get("rescinded-at") or meta.get("rescinded-on"))
        candidates.append(ArchiveCandidate(
            source_kind=KIND_ANTI_PATTERNS,
            entry_id=entry_id,
            source_path="docs/anti-patterns.md",
            title=title,
            reason="rescinded:true",
            eligible_since=(rescinded_at.date().isoformat() if rescinded_at else ""),
        ))
    return candidates


# ---------------------------------------------------------------------------
# Source: modules
# ---------------------------------------------------------------------------

def _scan_modules(
    repo: Path, *, now: datetime, config: dict
) -> list[ArchiveCandidate]:
    modules_dir = repo / ".agent" / "project" / "modules"
    if not modules_dir.is_dir():
        return []
    min_age = config.get("module_min_age_days", DEFAULT_MODULE_MIN_AGE_DAYS)

    candidates: list[ArchiveCandidate] = []
    for module_dir in sorted(modules_dir.iterdir()):
        if not module_dir.is_dir():
            continue
        yaml_file = module_dir / "module.yaml"
        if not yaml_file.exists():
            continue
        try:
            data = yaml.safe_load(yaml_file.read_text()) or {}
        except (OSError, yaml.YAMLError):
            continue
        state = str(data.get("state") or "").lower()
        if state != "shipped":
            continue
        # Find the last cycle's frozen_at (try multiple shapes)
        last_frozen = _find_last_frozen_at(data)
        if last_frozen is None:
            continue
        age_days = (now - last_frozen).days
        if age_days < min_age:
            continue
        candidates.append(ArchiveCandidate(
            source_kind=KIND_MODULES,
            entry_id=module_dir.name,
            source_path=f".agent/project/modules/{module_dir.name}",
            title=str(data.get("name") or module_dir.name),
            reason=f"state=shipped; last cycle frozen {age_days}d ago (threshold {min_age}d)",
            eligible_since=last_frozen.date().isoformat(),
        ))
    return candidates


def _find_last_frozen_at(module_data: dict) -> datetime | None:
    """Best-effort: find the most recent cycle's frozen_at timestamp."""
    cycles = module_data.get("cycles") or []
    if not isinstance(cycles, list):
        return None
    latest: datetime | None = None
    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue
        # Look for contract.frozen_at first, then cycle's own frozen_at
        contract = cycle.get("contract") or {}
        frozen_at = None
        if isinstance(contract, dict):
            frozen_at = contract.get("frozen_at")
        if not frozen_at:
            frozen_at = cycle.get("frozen_at") or cycle.get("ended_at")
        dt = _parse_date(frozen_at)
        if dt is None:
            continue
        if latest is None or dt > latest:
            latest = dt
    return latest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _split_h2_sections(text: str) -> list[tuple[str, str]]:
    """Split a markdown doc into (h2-heading, body-text) sections."""
    out: list[tuple[str, str]] = []
    matches = list(_H2_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1).strip(), text[start:end]))
    return out


_ID_TITLE_RE = re.compile(r"^([A-Z][A-Z0-9_-]*-\d+)(?:\s*[·:\-—]\s*(.+))?$")


def _split_id_title(heading: str) -> tuple[str, str]:
    """Parse 'BUG-007 · Title' or 'BUG-007: Title' → ('BUG-007', 'Title')."""
    m = _ID_TITLE_RE.match(heading.strip())
    if not m:
        return ("", heading.strip())
    return (m.group(1), (m.group(2) or "").strip())


_META_LINE_RE = re.compile(r"^\s*[-*]?\s*\*?\*?([A-Za-z][\w-]*)\*?\*?\s*:\s*(.+?)\s*$")


def _parse_inline_metadata(body: str) -> dict[str, str]:
    """Parse simple `key: value` lines (bulleted or plain) at start of body."""
    out: dict[str, str] = {}
    for line in body.splitlines():
        if not line.strip():
            continue
        m = _META_LINE_RE.match(line)
        if not m:
            # First non-metadata line ends the metadata block
            if out:
                break
            continue
        out[m.group(1).lower()] = m.group(2).strip()
    return out


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
)


def _parse_date(value) -> datetime | None:
    """Best-effort ISO date / datetime parser. Returns UTC datetime.

    Accepts strings (ISO 8601 forms) and datetime objects (YAML may
    already have parsed an ISO timestamp). None for anything else.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    # Special-case "Z" suffix
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    # ISO 8601 catch-all
    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _load_archive_config(repo: Path) -> dict:
    """Read `.agent/config.yaml::archive` section, or return defaults."""
    config_file = repo / ".agent" / "config.yaml"
    if not config_file.exists():
        return {}
    try:
        data = yaml.safe_load(config_file.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}
    archive = data.get("archive")
    if not isinstance(archive, dict):
        return {}
    return archive


# Order matters for stable output.
_SOURCE_HANDLERS = (
    (KIND_BUG_REGISTRY, _scan_bug_registry),
    (KIND_ANTI_PATTERNS, _scan_anti_patterns),
    (KIND_MODULES, _scan_modules),
)


__all__ = (
    "DEFAULT_BUG_MIN_AGE_DAYS",
    "DEFAULT_MODULE_MIN_AGE_DAYS",
    "KIND_BUG_REGISTRY",
    "KIND_ANTI_PATTERNS",
    "KIND_MODULES",
    "ArchiveCandidate",
    "ScanReport",
    "scan",
)
