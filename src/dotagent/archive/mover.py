"""Atomic archive moves + reversible log.

Moves are coarse but predictable:

- `bug-registry` / `anti-patterns` — H2 entries:
  Slice the section out of the source `.md` and append it to
  `docs/archive/<YYYY>/<filename>`. Atomic per-file: write to a temp,
  then rename source + archive on success.

- `modules` — entire dir:
  Move the directory from `.agent/project/modules/<id>` to
  `.agent/project/archive/<YYYY>/<id>`. The whole tree (cycles, contracts,
  handoffs, completion record) travels together.

Every move is logged in `.agent/archive-log.md`. `restore()` reads the log
and reverses one entry by id.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .triggers import (
    KIND_ANTI_PATTERNS,
    KIND_BUG_REGISTRY,
    KIND_MODULES,
    ArchiveCandidate,
    ScanReport,
    _H2_RE,
    _ID_TITLE_RE,
    scan,
)


@dataclass
class ArchiveLog:
    """One entry in the archive log (or rollback target)."""
    timestamp: str
    source_kind: str
    entry_id: str
    source_path: str            # original repo-relative path of source
    archive_path: str           # destination repo-relative path
    restored_at: str = ""       # set when this entry is restored

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "source_kind": self.source_kind,
            "entry_id": self.entry_id,
            "source_path": self.source_path,
            "archive_path": self.archive_path,
            "restored_at": self.restored_at,
        }


@dataclass
class ArchiveResult:
    """Outcome of one `run()` call."""
    moved: list[ArchiveLog] = field(default_factory=list)
    skipped: list[ArchiveCandidate] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (entry_id, reason)

    def to_dict(self) -> dict:
        return {
            "moved": [m.to_dict() for m in self.moved],
            "skipped": [c.to_dict() for c in self.skipped],
            "errors": [{"entry_id": e[0], "reason": e[1]} for e in self.errors],
        }


# ---------------------------------------------------------------------------
# Public: run, restore, list
# ---------------------------------------------------------------------------

def run(
    repo: Path,
    *,
    dry_run: bool = False,
    candidates: list[ArchiveCandidate] | None = None,
) -> ArchiveResult:
    """Execute archival for every eligible candidate.

    If `candidates` is None, scans the repo. Pass an explicit list to
    archive a curated subset. `dry_run=True` returns the result without
    touching the filesystem.
    """
    if candidates is None:
        candidates = scan(repo).candidates

    result = ArchiveResult()
    now_iso = _utc_now_iso()

    for cand in candidates:
        try:
            if dry_run:
                # Simulate by constructing the archive path the same way
                # the real path resolver would.
                arch_path = _archive_path_for(repo, cand, now_iso)
                result.moved.append(ArchiveLog(
                    timestamp=now_iso,
                    source_kind=cand.source_kind,
                    entry_id=cand.entry_id,
                    source_path=cand.source_path,
                    archive_path=str(arch_path.relative_to(repo)),
                ))
                continue
            arch_log = _move_one(repo, cand, now_iso)
            result.moved.append(arch_log)
        except Exception as exc:  # noqa: BLE001
            result.errors.append((cand.entry_id, str(exc)))

    if not dry_run and result.moved:
        _append_log(repo, result.moved)

    return result


def restore(repo: Path, entry_id: str) -> ArchiveLog | None:
    """Un-archive one entry. Returns the log entry, or None if not found.

    Raises FileNotFoundError if the archive log itself is missing.
    Raises ValueError if the entry exists but has already been restored.
    """
    log = _read_log(repo)
    if not log:
        raise FileNotFoundError("archive log is missing or empty")

    target: ArchiveLog | None = None
    for entry in reversed(log):  # most-recent match wins
        if entry.entry_id != entry_id:
            continue
        if entry.restored_at:
            continue
        target = entry
        break

    if target is None:
        return None

    _reverse_move(repo, target)
    target.restored_at = _utc_now_iso()
    _rewrite_log(repo, log)
    return target


def list_archived(repo: Path) -> list[ArchiveLog]:
    """Return every entry in the archive log, in insertion order."""
    return _read_log(repo)


# ---------------------------------------------------------------------------
# Move implementations
# ---------------------------------------------------------------------------

def _move_one(repo: Path, cand: ArchiveCandidate, now_iso: str) -> ArchiveLog:
    """Dispatch on source kind. Returns the log entry."""
    if cand.source_kind in (KIND_BUG_REGISTRY, KIND_ANTI_PATTERNS):
        return _move_markdown_section(repo, cand, now_iso)
    if cand.source_kind == KIND_MODULES:
        return _move_module_dir(repo, cand, now_iso)
    raise ValueError(f"unsupported source_kind: {cand.source_kind!r}")


def _move_markdown_section(
    repo: Path, cand: ArchiveCandidate, now_iso: str
) -> ArchiveLog:
    """Slice an H2 section out of source .md; append to archive year-file."""
    source = repo / cand.source_path
    if not source.exists():
        raise FileNotFoundError(f"source missing: {cand.source_path}")

    text = source.read_text()
    section_text, remainder = _extract_h2_section(text, cand.entry_id)
    if section_text is None:
        raise ValueError(
            f"entry {cand.entry_id!r} not found in {cand.source_path}"
        )

    archive_path = _archive_path_for(repo, cand, now_iso)
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    # Append (preserving any existing archived content)
    archive_header = (
        "" if archive_path.exists() else
        "<!-- Archived entries. Auto-appended by `dotagent archive run`. "
        "Each H2 is one historical entry. -->\n"
        f"# {_archive_doc_title(cand.source_kind)} — archive\n\n"
    )
    archive_marker = (
        f"\n<!-- archived: {now_iso} · from {cand.source_path} -->\n"
        f"## {cand.entry_id}"
        + (f" · {cand.title}" if cand.title else "")
        + "\n"
        + section_text.rstrip()
        + "\n"
    )
    if archive_path.exists():
        archive_path.write_text(archive_path.read_text().rstrip() + "\n\n" + archive_marker.lstrip("\n"))
    else:
        archive_path.write_text(archive_header + archive_marker.lstrip("\n"))

    # Rewrite source with the section removed
    _atomic_write(source, remainder.rstrip() + ("\n" if remainder else ""))

    return ArchiveLog(
        timestamp=now_iso,
        source_kind=cand.source_kind,
        entry_id=cand.entry_id,
        source_path=cand.source_path,
        archive_path=str(archive_path.relative_to(repo)),
    )


def _move_module_dir(
    repo: Path, cand: ArchiveCandidate, now_iso: str
) -> ArchiveLog:
    """Move an entire module directory under .agent/project/archive/YYYY/."""
    source = repo / cand.source_path
    if not source.is_dir():
        raise FileNotFoundError(f"module dir missing: {cand.source_path}")

    archive_dir = _archive_path_for(repo, cand, now_iso)
    archive_dir.parent.mkdir(parents=True, exist_ok=True)
    if archive_dir.exists():
        raise FileExistsError(
            f"archive destination already exists: {archive_dir}; "
            f"resolve manually and retry"
        )

    shutil.move(str(source), str(archive_dir))

    return ArchiveLog(
        timestamp=now_iso,
        source_kind=cand.source_kind,
        entry_id=cand.entry_id,
        source_path=cand.source_path,
        archive_path=str(archive_dir.relative_to(repo)),
    )


def _reverse_move(repo: Path, log_entry: ArchiveLog) -> None:
    """Un-do one archived move based on its log entry."""
    archive = repo / log_entry.archive_path
    source = repo / log_entry.source_path

    if log_entry.source_kind == KIND_MODULES:
        if not archive.is_dir():
            raise FileNotFoundError(
                f"archived dir not found: {log_entry.archive_path}"
            )
        if source.exists():
            raise FileExistsError(
                f"source already exists at {log_entry.source_path}; "
                f"resolve manually"
            )
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(archive), str(source))
        return

    # Markdown section sources
    if not archive.exists():
        raise FileNotFoundError(
            f"archive file not found: {log_entry.archive_path}"
        )
    arch_text = archive.read_text()
    section_text, remainder = _extract_h2_section(arch_text, log_entry.entry_id)
    if section_text is None:
        raise ValueError(
            f"archived entry {log_entry.entry_id!r} not found in "
            f"{log_entry.archive_path}"
        )

    # Append back to source (or create source if it's gone)
    section_for_source = (
        f"\n## {log_entry.entry_id}\n"
        + section_text.rstrip()
        + "\n"
    )
    if source.exists():
        source.write_text(source.read_text().rstrip() + "\n" + section_for_source)
    else:
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(section_for_source.lstrip("\n"))

    # Remove the section from the archive file
    _atomic_write(archive, remainder.rstrip() + ("\n" if remainder else ""))


# ---------------------------------------------------------------------------
# H2 section extraction (used by markdown sources + restore)
# ---------------------------------------------------------------------------

def _extract_h2_section(text: str, entry_id: str) -> tuple[str | None, str]:
    """Return (section_body, remainder_without_section).

    section_body excludes the H2 heading itself but includes the body.
    remainder is the original text with that section removed.
    `section_body` is None if no matching H2 was found.
    """
    matches = list(_H2_RE.finditer(text))
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        cand_id, _title = _split_id_title_for_match(heading)
        if cand_id != entry_id:
            continue
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_body = text[body_start:body_end]
        # Build remainder: everything before this match + everything after the section
        section_start = m.start()
        remainder = text[:section_start].rstrip("\n") + "\n" + text[body_end:].lstrip("\n")
        if not text[:section_start].strip():
            remainder = text[body_end:].lstrip("\n")
        return section_body, remainder
    return None, text


def _split_id_title_for_match(heading: str) -> tuple[str, str]:
    """ID matcher used for archive moves; tolerates surrounding markdown."""
    m = _ID_TITLE_RE.match(heading.strip())
    if not m:
        return ("", heading.strip())
    return (m.group(1), (m.group(2) or "").strip())


# ---------------------------------------------------------------------------
# Archive path resolver
# ---------------------------------------------------------------------------

def _archive_path_for(
    repo: Path, cand: ArchiveCandidate, now_iso: str
) -> Path:
    """Compute the destination archive path for a candidate."""
    year = now_iso[:4]
    if cand.source_kind in (KIND_BUG_REGISTRY, KIND_ANTI_PATTERNS):
        source_name = Path(cand.source_path).name  # e.g. bug-registry.md
        return repo / "docs" / "archive" / year / source_name
    if cand.source_kind == KIND_MODULES:
        return repo / ".agent" / "project" / "archive" / year / cand.entry_id
    raise ValueError(f"unsupported source_kind: {cand.source_kind!r}")


def _archive_doc_title(source_kind: str) -> str:
    if source_kind == KIND_BUG_REGISTRY:
        return "Bug registry"
    if source_kind == KIND_ANTI_PATTERNS:
        return "Anti-patterns"
    return source_kind


# ---------------------------------------------------------------------------
# Log persistence
# ---------------------------------------------------------------------------

def _log_path(repo: Path) -> Path:
    return repo / ".agent" / "archive-log.md"


_LOG_HEADER = (
    "<!-- Archive log — machine-readable. Each `- ARCHIVED` / `- RESTORED` "
    "line is one filesystem move. -->\n"
    "# Archive log\n\n"
)


def _append_log(repo: Path, entries: list[ArchiveLog]) -> None:
    """Append a batch of archive moves to the log file."""
    log_file = _log_path(repo)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if not log_file.exists():
        log_file.write_text(_LOG_HEADER)
    body = log_file.read_text().rstrip() + "\n"
    for e in entries:
        body += _format_log_line(e) + "\n"
    log_file.write_text(body)


def _rewrite_log(repo: Path, entries: list[ArchiveLog]) -> None:
    """Rewrite the entire log (used after restore())."""
    log_file = _log_path(repo)
    body = _LOG_HEADER
    for e in entries:
        body += _format_log_line(e) + "\n"
    log_file.write_text(body)


def _format_log_line(e: ArchiveLog) -> str:
    """One canonical log line, machine-parseable."""
    suffix = f" · restored: {e.restored_at}" if e.restored_at else ""
    return (
        f"- ARCHIVED: {e.entry_id} ({e.source_kind}) "
        f"{e.source_path} → {e.archive_path} · at: {e.timestamp}{suffix}"
    )


def _read_log(repo: Path) -> list[ArchiveLog]:
    """Parse the archive log into a list of entries (in original order)."""
    log_file = _log_path(repo)
    if not log_file.exists():
        return []
    out: list[ArchiveLog] = []
    for line in log_file.read_text().splitlines():
        entry = _parse_log_line(line)
        if entry:
            out.append(entry)
    return out


def _parse_log_line(line: str) -> ArchiveLog | None:
    """Parse one `- ARCHIVED: ...` log line. Tolerant to whitespace."""
    s = line.strip()
    if not s.startswith("- ARCHIVED:"):
        return None
    s = s[len("- ARCHIVED:"):].strip()
    # ID (kind) source → archive · at: ts [· restored: ts]
    # Cheap split — the format is controlled by us.
    import re as _re
    m = _re.match(
        r"^(?P<id>\S+)\s+\((?P<kind>[\w-]+)\)\s+"
        r"(?P<src>\S+)\s+→\s+(?P<dst>\S+)\s+·\s+at:\s*(?P<ts>\S+)"
        r"(?:\s+·\s+restored:\s*(?P<restored>\S+))?\s*$",
        s,
    )
    if not m:
        return None
    return ArchiveLog(
        timestamp=m.group("ts"),
        source_kind=m.group("kind"),
        entry_id=m.group("id"),
        source_path=m.group("src"),
        archive_path=m.group("dst"),
        restored_at=(m.group("restored") or ""),
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _atomic_write(target: Path, content: str) -> None:
    """Write `content` to `target` atomically via a temp file in same dir."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=str(target.parent), prefix=f".{target.name}.",
        suffix=".tmp", delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(target)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = (
    "ArchiveLog",
    "ArchiveResult",
    "run",
    "restore",
    "list_archived",
)
