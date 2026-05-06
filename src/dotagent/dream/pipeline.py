"""Auto-Dream candidate writer + graduate/reject gate (mandatory rationale)."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..identity import resolve
from ..memory import SemanticEntry, SemanticMemory
from ..paths import Paths
from .signals import Signal


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _candidate_id(sig: Signal) -> str:
    return hashlib.sha1(sig.id.encode()).hexdigest()[:10]


def generate_candidates(paths: Paths, signals: list[Signal]) -> list[Path]:
    """Materialize each signal as a candidate file. Idempotent (overwrites stale)."""
    cdir = paths.dream / "candidates"
    cdir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for sig in signals:
        cid = _candidate_id(sig)
        target = cdir / f"{cid}.md"
        body = (
            f"# Candidate `{cid}` — {sig.title}\n\n"
            f"- **kind**: `{sig.kind}`\n"
            f"- **weight**: {sig.weight}\n"
            f"- **actors**: {', '.join(sig.actors) or '(none)'}\n"
            f"- **files**: {', '.join(sig.files) or '(none)'}\n"
            f"- **generated_at**: {_now()}\n\n"
            f"## Evidence\n\n"
            + "\n".join(f"- {e}" for e in sig.evidence) + "\n\n"
            "## Status\n\nawaiting review (`dotagent dream graduate <id> --rationale ...`)\n"
        )
        target.write_text(body)
        written.append(target)
    return written


def list_candidates(paths: Paths) -> list[Path]:
    cdir = paths.dream / "candidates"
    return sorted(cdir.glob("*.md")) if cdir.exists() else []


def _move(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / src.name
    target.write_text(src.read_text())
    src.unlink()
    return target


def graduate(paths: Paths, candidate_id: str, rationale: str, *, evidence_extras: list[str] | None = None) -> Path:
    """Move candidate to dream/graduated/ AND write a SemanticEntry rule. Rationale is mandatory."""
    if not rationale or not rationale.strip():
        raise ValueError("rationale is required for graduation — non-negotiable")
    src = _find_candidate(paths, candidate_id)

    actor = resolve(paths.repo).id
    body = src.read_text()
    body += (
        f"\n\n## Rationale\n\n{rationale}\n\n"
        f"## Graduated by\n\n- {actor} on {_now()}\n"
    )
    src.write_text(body)
    target = _move(src, paths.dream / "graduated")

    title = _extract_title(body) or f"Graduated rule {candidate_id}"
    sem = SemanticMemory(paths)
    entry = SemanticEntry(
        kind="rules",
        category="auto-dream",
        title=title,
        body=body,
        rationale=rationale,
        provenance=f"auto-dream graduation from candidate {candidate_id}",
        evidence=evidence_extras or [],
        graduated_by=actor,
    )
    sem.write(entry)
    return target


def reject(paths: Paths, candidate_id: str, rationale: str) -> Path:
    if not rationale or not rationale.strip():
        raise ValueError("rationale is required for rejection — non-negotiable")
    src = _find_candidate(paths, candidate_id)
    actor = resolve(paths.repo).id
    body = src.read_text() + (
        f"\n\n## Rejection rationale\n\n{rationale}\n\n"
        f"## Rejected by\n\n- {actor} on {_now()}\n"
    )
    src.write_text(body)
    return _move(src, paths.dream / "rejected")


def _find_candidate(paths: Paths, candidate_id: str) -> Path:
    cdir = paths.dream / "candidates"
    target = cdir / f"{candidate_id}.md"
    if target.exists():
        return target
    matches = list(cdir.glob(f"{candidate_id}*.md")) if cdir.exists() else []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"ambiguous candidate id `{candidate_id}` — {[m.name for m in matches]}")
    raise FileNotFoundError(f"no candidate `{candidate_id}` found")


def _extract_title(body: str) -> str:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return ""
