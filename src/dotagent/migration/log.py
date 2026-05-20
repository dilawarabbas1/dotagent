"""Migration log: append-only record of every migrate step, for rollback.

The log is markdown for human readability, with machine-parseable lines.
Format:

    ## 2026-05-21T10:00:00Z · v0.3 → v0.4.0

    - CREATED: .agent/.version (`0.4.0`)
    - CREATED: .agent/project_brief.md (stub)
    - MOVED:   .agent/old/path → .agent/new/path

`read_log()` parses the most recent run so `--rollback` can reverse it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# Step kinds. Each maps to a reversible filesystem operation.
KIND_CREATED = "CREATED"  # rollback: delete the path
KIND_DELETED = "DELETED"  # rollback: restore from backup at .imported/
KIND_MOVED = "MOVED"      # rollback: move back
KIND_MODIFIED = "MODIFIED"  # rollback: restore from backup at .imported/
KIND_INFERRED = "INFERRED"  # informational, not reversible


@dataclass
class MigrationStep:
    """One reversible change made (or to be made) during migration."""
    kind: str
    path: str
    detail: str = ""          # human note (e.g., "(stub)")
    original_path: str = ""   # for MOVED steps

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "path": self.path,
            "detail": self.detail,
            "original_path": self.original_path,
        }

    def to_log_line(self) -> str:
        if self.kind == KIND_MOVED and self.original_path:
            line = f"- {self.kind}:   {self.original_path} → {self.path}"
        else:
            line = f"- {self.kind}: {self.path}"
        if self.detail:
            line += f" {self.detail}"
        return line


@dataclass
class MigrationLog:
    """One migration session — header + steps."""
    timestamp: str
    from_version: str | None
    to_version: str
    steps: list[MigrationStep] = field(default_factory=list)


def _log_path(repo: Path) -> Path:
    return repo / ".agent" / ".migration-log.md"


def write_log(
    repo: Path,
    from_version: str | None,
    to_version: str,
    steps: list[MigrationStep],
) -> Path:
    """Append a new section to the migration log. Returns the log path."""
    log_file = _log_path(repo)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    header = f"## {ts} · v{from_version or 'pre-0.4'} → v{to_version}"
    body = "\n".join(s.to_log_line() for s in steps)

    if log_file.exists():
        existing = log_file.read_text()
        new = existing.rstrip() + "\n\n" + header + "\n\n" + body + "\n"
    else:
        new = (
            "<!-- Migration log — machine-readable. Each `##` section "
            "is one `dotagent migrate` run. -->\n"
            "# Migration log\n\n"
            + header + "\n\n" + body + "\n"
        )
    log_file.write_text(new)
    return log_file


_SECTION_HEADER_RE = re.compile(
    r"^## (?P<ts>\S+) · v(?P<from>\S+) → v(?P<to>\S+)\s*$"
)
_STEP_LINE_RE = re.compile(
    r"^- (?P<kind>[A-Z]+): +(?P<rest>.+?)(?:\s+\((?P<detail>[^)]+)\))?\s*$"
)


def read_last_log(repo: Path) -> MigrationLog | None:
    """Parse the most recent migration section.

    Returns None if no log exists or the file is malformed beyond use.
    """
    log_file = _log_path(repo)
    if not log_file.exists():
        return None
    try:
        text = log_file.read_text()
    except OSError:
        return None

    sections = _split_sections(text)
    if not sections:
        return None
    header_line, body = sections[-1]
    m = _SECTION_HEADER_RE.match(header_line)
    if not m:
        return None

    from_v = m.group("from")
    if from_v == "pre-0.4":
        from_v = None

    log = MigrationLog(
        timestamp=m.group("ts"),
        from_version=from_v,
        to_version=m.group("to"),
    )
    for line in body.splitlines():
        if not line.startswith("- "):
            continue
        step = _parse_step_line(line)
        if step is not None:
            log.steps.append(step)
    return log


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Return [(header_line, body), ...] for every `## ...` section."""
    sections: list[tuple[str, str]] = []
    current_header: str | None = None
    current_body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_header is not None:
                sections.append((current_header, "\n".join(current_body)))
            current_header = line
            current_body = []
        elif current_header is not None:
            current_body.append(line)
    if current_header is not None:
        sections.append((current_header, "\n".join(current_body)))
    return sections


def _parse_step_line(line: str) -> MigrationStep | None:
    """Parse one `- KIND: ...` log line into a MigrationStep.

    Tolerant of MOVED lines (`- MOVED: a → b`) and detail suffixes.
    """
    # Try MOVED form first
    m_moved = re.match(
        r"^- (?P<kind>MOVED): +(?P<src>\S+) +→ +(?P<dst>\S+)(?:\s+(?P<detail>.+))?\s*$",
        line,
    )
    if m_moved:
        return MigrationStep(
            kind=m_moved.group("kind"),
            path=m_moved.group("dst"),
            original_path=m_moved.group("src"),
            detail=(m_moved.group("detail") or "").strip(),
        )
    m = re.match(r"^- (?P<kind>[A-Z]+): +(?P<path>\S+)(?:\s+(?P<detail>.+))?\s*$", line)
    if m:
        return MigrationStep(
            kind=m.group("kind"),
            path=m.group("path"),
            detail=(m.group("detail") or "").strip(),
        )
    return None


__all__ = (
    "KIND_CREATED",
    "KIND_DELETED",
    "KIND_MOVED",
    "KIND_MODIFIED",
    "KIND_INFERRED",
    "MigrationStep",
    "MigrationLog",
    "write_log",
    "read_last_log",
)
