"""Rule lifecycle — Module 2.

Graduated rules carry expiration dates. Stale rules surface for review. Rules
not re-rationaled within the grace period are moved to `.agent/dream/expired/`
(never deleted — audit is sacred).

Built in response to Faisal Feroz's LinkedIn feedback: "I would push you to
also think about expiration and review cycles for those entries because team
knowledge decays as the codebase evolves."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..memory.semantic import SemanticEntry, SemanticMemory, _now_iso, _parse_iso
from ..paths import Paths
from ..util import write_text


def _today() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Normalize a parsed datetime to UTC-aware so arithmetic with `_today()` works.

    `datetime.fromisoformat("2025-12-01")` returns a tz-naive value; we treat naked
    dates as UTC midnight to keep things deterministic.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class StaleRule:
    path: Path
    entry: SemanticEntry
    reason: str          # "review_after_passed" | "cited_files_churned" | "legacy_no_metadata"
    days_overdue: int    # negative means "due soon", positive means past

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "title": self.entry.title,
            "category": self.entry.category,
            "reason": self.reason,
            "days_overdue": self.days_overdue,
            "graduated_at": self.entry.graduated_at,
            "review_after": self.entry.review_after,
            "last_reviewed_at": self.entry.last_reviewed_at,
        }


def _cited_files_churned(entry: SemanticEntry, paths: Paths) -> bool:
    """Best-effort: do any files mentioned in the rule body have an mtime later
    than the rule's `graduated_at`?

    This is a cheap proxy for "the code drifted under the rule." Not perfect —
    a file can be modified without violating the rule — but combined with
    `review_after`, it surfaces rules that genuinely need a second look.
    """
    graduated = _aware(_parse_iso(entry.graduated_at))
    if not graduated:
        return False
    import re
    file_paths: set[str] = set()
    # backtick-wrapped paths in the body, e.g. `services/auth/jwt.py`
    for m in re.finditer(r"`([\w./\-_]+\.(?:py|js|ts|tsx|jsx|go|rs|rb|java|sql|sh|md|yaml|yml|toml))`", entry.body):
        file_paths.add(m.group(1))
    for rel in file_paths:
        f = paths.repo / rel
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime > graduated + timedelta(days=7):  # 7-day buffer to avoid same-day noise
            return True
    return False


def review_stale(paths: Paths, *, include_due_soon_days: int = 0) -> list[StaleRule]:
    """Return every rule that is past review or whose cited files have drifted.

    `include_due_soon_days`: if > 0, also include rules whose `review_after`
    falls within the next N days (so teams can preview upcoming reviews).
    """
    out: list[StaleRule] = []
    mem = SemanticMemory(paths)
    today = _today()
    for path in mem.list():
        if "expired" in path.parts:
            continue
        entry = mem.read(path)
        if not entry:
            continue
        review_dt = _aware(_parse_iso(entry.review_after) or _parse_iso(entry.review_after + "T00:00:00Z"))
        # Bucket 1: explicit review_after has passed (or is approaching)
        if review_dt:
            delta = (today - review_dt).days
            if delta >= -include_due_soon_days:
                out.append(StaleRule(
                    path=path, entry=entry,
                    reason="review_after_passed" if delta >= 0 else "due_soon",
                    days_overdue=delta,
                ))
                continue
        elif not entry.review_after:
            # Bucket 2: legacy rule with no metadata — treat as stale if file mtime > 180d
            graduated = _aware(_parse_iso(entry.graduated_at))
            if graduated and (today - graduated).days > SemanticMemory.DEFAULT_LIFETIME_DAYS:
                out.append(StaleRule(
                    path=path, entry=entry,
                    reason="legacy_no_metadata",
                    days_overdue=(today - graduated).days - SemanticMemory.DEFAULT_LIFETIME_DAYS,
                ))
                continue
        # Bucket 3: not past review by date — but cited files churned
        if _cited_files_churned(entry, paths):
            out.append(StaleRule(
                path=path, entry=entry,
                reason="cited_files_churned",
                days_overdue=0,
            ))
    out.sort(key=lambda r: -r.days_overdue)  # most overdue first
    return out


def rerationale(paths: Paths, rule_id: str, *, rationale: str,
                extend_days: int | None = None) -> Path:
    """Mark a stale rule as reviewed. Rationale is mandatory.

    `extend_days` extends `review_after` by N days (default = full lifetime).
    """
    if not rationale or not rationale.strip():
        raise ValueError("rationale is required to re-rationale a rule — non-negotiable")
    mem = SemanticMemory(paths)
    target = _find_rule_by_id_or_path(paths, rule_id, mem)
    entry = mem.read(target)
    if not entry:
        raise FileNotFoundError(f"cannot read rule at {target}")
    # update lifecycle metadata
    now = _today()
    extend = extend_days if extend_days is not None else SemanticMemory.DEFAULT_LIFETIME_DAYS
    entry.last_reviewed_at = _now_iso()
    entry.review_after = (now + timedelta(days=extend)).date().isoformat()
    # append the new rationale inline in the body (no `## ` heading — that would
    # be truncated as a section boundary on the next read)
    entry.body = entry.body.rstrip() + (
        f"\n\n_Re-rationaled {_now_iso()}: {rationale}_\n"
    )
    return mem.write(entry)


def expire_stale(paths: Paths, *, grace_period_days: int = 30, dry_run: bool = False) -> list[Path]:
    """Move rules whose review_after has been past for > grace_period_days into expired/.

    Files are MOVED (not deleted). The original `.agent/memory/semantic/...` tree
    is the canonical home; expired rules live under `.agent/dream/expired/`.
    """
    moved: list[Path] = []
    today = _today()
    expired_root = paths.dream / "expired"
    expired_root.mkdir(parents=True, exist_ok=True)
    for stale in review_stale(paths):
        if stale.reason == "due_soon":
            continue
        if stale.days_overdue < grace_period_days:
            continue
        target = expired_root / f"{stale.path.stem}.md"
        # idempotent — same name re-runs to the same target
        if dry_run:
            moved.append(target)
            continue
        # rewrite with expired_at stamp
        stale.entry.expired_at = _now_iso()
        stale.entry.body = stale.entry.body.rstrip() + (
            f"\n\n## Expired ({stale.entry.expired_at})\n\n"
            f"Auto-expired by `dotagent dream expire-stale` after the grace period "
            f"(was {stale.days_overdue} day(s) overdue at review). "
            f"To revive: edit this file and copy back to "
            f"`{stale.path.relative_to(paths.repo)}`.\n"
        )
        target.write_text(stale.entry.body)
        stale.path.unlink()
        moved.append(target)
    return moved


def _find_rule_by_id_or_path(paths: Paths, rule_id: str, mem: SemanticMemory) -> Path:
    """Allow callers to pass either the SHA prefix, the slug, the filename, or a relative path."""
    rule_id = rule_id.strip().lstrip("/")
    candidates = mem.list()
    # exact filename or stem match
    for p in candidates:
        if p.name == rule_id or p.stem == rule_id:
            return p
    # SHA prefix match (slugs are <sha8>-<slug>.md)
    for p in candidates:
        if p.stem.startswith(rule_id + "-") or p.stem == rule_id:
            return p
    # path match
    abs_p = (paths.repo / rule_id).resolve() if "/" in rule_id else None
    for p in candidates:
        if abs_p and p.resolve() == abs_p:
            return p
    raise FileNotFoundError(f"no rule matching '{rule_id}' under {paths.semantic}")
