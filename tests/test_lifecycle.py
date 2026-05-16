"""Module 2 — Rule Lifecycle + Expiration.

Graduated rules carry expiration dates. Stale rules surface for review.
Un-rationaled stale rules move to `.agent/dream/expired/` after the grace
period (never deleted).

Built in response to Faisal Feroz's LinkedIn feedback: "I would push you to
also think about expiration and review cycles for those entries because team
knowledge decays as the codebase evolves."
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dotagent.adapters.render import render_body
from dotagent.config import Config, merge_defaults
from dotagent.context import build as build_context
from dotagent.dream.lifecycle import (
    expire_stale,
    rerationale,
    review_stale,
)
from dotagent.memory.semantic import SemanticEntry, SemanticMemory
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.util import dump_yaml


def _setup(tmp_path: Path) -> Paths:
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "demo"}}))
    return paths


def _write_rule(
    paths: Paths,
    title: str,
    *,
    graduated_at: str | None = None,
    review_after: str | None = None,
    body: str = "rule body",
    category: str = "auto-dream",
) -> Path:
    """Helper that bypasses SemanticMemory.write to write a rule with controlled timestamps."""
    mem = SemanticMemory(paths)
    entry = SemanticEntry(
        kind="rules",
        category=category,
        title=title,
        body=body,
        rationale="test rationale",
        graduated_at=graduated_at or "",
        review_after=review_after or "",
    )
    return mem.write(entry)


# ---- write() defaults ------------------------------------------------------


def test_write_sets_graduated_at_and_review_after_by_default(tmp_path: Path):
    paths = _setup(tmp_path)
    mem = SemanticMemory(paths)
    entry = SemanticEntry(
        kind="rules", category="auto-dream",
        title="Default lifetime test", body="body",
        rationale="test",
    )
    path = mem.write(entry)
    text = path.read_text()
    assert entry.graduated_at  # was filled in
    assert entry.review_after  # was filled in
    # Default lifetime is 180 days
    grad = datetime.fromisoformat(entry.graduated_at.replace("Z", "+00:00"))
    rev = datetime.fromisoformat(entry.review_after + "T00:00:00+00:00")
    delta = (rev.date() - grad.date()).days
    assert 179 <= delta <= 181  # default lifetime is 180; allow ±1 for date math edge cases


def test_write_respects_custom_lifetime(tmp_path: Path):
    paths = _setup(tmp_path)
    mem = SemanticMemory(paths)
    entry = SemanticEntry(
        kind="rules", category="auto-dream", title="Short lifetime",
        body="body", rationale="t",
    )
    mem.write(entry, lifetime_days=30)
    grad = datetime.fromisoformat(entry.graduated_at.replace("Z", "+00:00"))
    rev = datetime.fromisoformat(entry.review_after + "T00:00:00+00:00")
    assert 29 <= (rev.date() - grad.date()).days <= 31


def test_write_preserves_caller_supplied_lifecycle_dates(tmp_path: Path):
    """If a caller (or a re-rationale) supplies dates, write() must not overwrite them."""
    paths = _setup(tmp_path)
    mem = SemanticMemory(paths)
    entry = SemanticEntry(
        kind="rules", category="auto-dream", title="Pinned dates",
        body="body", rationale="t",
        graduated_at="2025-01-01T00:00:00Z",
        review_after="2025-07-01",
    )
    mem.write(entry)
    assert entry.graduated_at == "2025-01-01T00:00:00Z"
    assert entry.review_after == "2025-07-01"


# ---- read() round-trips lifecycle metadata ---------------------------------


def test_read_round_trips_lifecycle_metadata(tmp_path: Path):
    paths = _setup(tmp_path)
    mem = SemanticMemory(paths)
    path = _write_rule(
        paths, "RT test",
        graduated_at="2025-06-01T00:00:00Z",
        review_after="2025-12-01",
    )
    loaded = mem.read(path)
    assert loaded is not None
    assert loaded.title == "RT test"
    assert loaded.graduated_at == "2025-06-01T00:00:00Z"
    assert loaded.review_after == "2025-12-01"


def test_read_handles_legacy_rule_without_metadata(tmp_path: Path):
    """Pre-Module-2 rules have no dotagent-meta comment. Read should fall back to file mtime."""
    paths = _setup(tmp_path)
    (paths.semantic / "rules" / "auto-dream").mkdir(parents=True, exist_ok=True)
    legacy = paths.semantic / "rules" / "auto-dream" / "legacy-rule.md"
    legacy.write_text("# Legacy Rule\n\nNo metadata footer.\n")
    mem = SemanticMemory(paths)
    loaded = mem.read(legacy)
    assert loaded is not None
    assert loaded.title == "Legacy Rule"
    # graduated_at falls back to mtime
    assert loaded.graduated_at  # populated from file mtime
    # review_after may be empty — that's OK, lifecycle.review_stale handles legacy bucket


# ---- review_stale() --------------------------------------------------------


def test_review_stale_is_empty_when_no_rules(tmp_path: Path):
    paths = _setup(tmp_path)
    assert review_stale(paths) == []


def test_review_stale_skips_fresh_rules(tmp_path: Path):
    paths = _setup(tmp_path)
    future = (datetime.now(timezone.utc) + timedelta(days=100)).date().isoformat()
    _write_rule(paths, "Fresh rule", review_after=future)
    assert review_stale(paths) == []


def test_review_stale_surfaces_overdue_rules(tmp_path: Path):
    paths = _setup(tmp_path)
    past = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    _write_rule(paths, "Overdue rule", review_after=past)
    stale = review_stale(paths)
    assert len(stale) == 1
    assert stale[0].entry.title == "Overdue rule"
    assert stale[0].reason == "review_after_passed"
    assert stale[0].days_overdue >= 29


def test_review_stale_finds_legacy_rules_past_default_lifetime(tmp_path: Path):
    """Rules with no metadata and mtime older than 180d are treated as stale."""
    paths = _setup(tmp_path)
    (paths.semantic / "rules" / "auto-dream").mkdir(parents=True, exist_ok=True)
    legacy = paths.semantic / "rules" / "auto-dream" / "legacy-old.md"
    legacy.write_text("# Legacy Old\n\nNo metadata footer.\n")
    # backdate the file mtime by 200 days
    old_ts = time.time() - (200 * 86400)
    os.utime(legacy, (old_ts, old_ts))
    stale = review_stale(paths)
    assert any(s.reason == "legacy_no_metadata" for s in stale)


def test_review_stale_due_soon_window_includes_upcoming(tmp_path: Path):
    paths = _setup(tmp_path)
    soon = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
    _write_rule(paths, "Due soon", review_after=soon)
    assert review_stale(paths, include_due_soon_days=0) == []
    stale = review_stale(paths, include_due_soon_days=14)
    assert len(stale) == 1
    assert stale[0].reason == "due_soon"


def test_review_stale_orders_most_overdue_first(tmp_path: Path):
    paths = _setup(tmp_path)
    today = datetime.now(timezone.utc)
    _write_rule(paths, "Mildly stale",
                review_after=(today - timedelta(days=10)).date().isoformat())
    _write_rule(paths, "Severely stale",
                review_after=(today - timedelta(days=100)).date().isoformat())
    stale = review_stale(paths)
    assert stale[0].entry.title == "Severely stale"
    assert stale[1].entry.title == "Mildly stale"


def test_review_stale_detects_churned_cited_files(tmp_path: Path):
    """If a rule's body cites `path/x.py` and that file's mtime > graduated_at + 7d, surface it."""
    paths = _setup(tmp_path)
    # Create the cited file BEFORE the rule, then bump its mtime AFTER the rule
    target = paths.repo / "services" / "auth.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# auth\n")
    rule_path = _write_rule(
        paths, "JWT rule",
        graduated_at=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
        review_after=(datetime.now(timezone.utc) + timedelta(days=100)).date().isoformat(),  # future
        body="Don't bypass `services/auth.py`.",
    )
    # bump the file mtime to "now" (long after graduated_at + 7-day buffer)
    now_ts = time.time()
    os.utime(target, (now_ts, now_ts))
    stale = review_stale(paths)
    assert any(s.reason == "cited_files_churned" for s in stale)


# ---- rerationale() ---------------------------------------------------------


def test_rerationale_requires_non_empty_rationale(tmp_path: Path):
    paths = _setup(tmp_path)
    p = _write_rule(paths, "Some rule",
                    review_after=(datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat())
    with pytest.raises(ValueError):
        rerationale(paths, p.stem, rationale="")
    with pytest.raises(ValueError):
        rerationale(paths, p.stem, rationale="   ")


def test_rerationale_extends_review_after_and_appends_note(tmp_path: Path):
    paths = _setup(tmp_path)
    past = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
    p = _write_rule(paths, "Stale rule", review_after=past)
    rerationale(paths, p.stem, rationale="Still relevant: same auth flow, same risks")
    mem = SemanticMemory(paths)
    reloaded = mem.read(p)
    # review_after pushed into the future
    rev = datetime.fromisoformat(reloaded.review_after + "T00:00:00+00:00")
    assert rev.date() > datetime.now(timezone.utc).date()
    # last_reviewed_at populated
    assert reloaded.last_reviewed_at
    # body contains the re-rationale note
    assert "Re-rationale" in p.read_text()
    assert "Still relevant" in p.read_text()


def test_rerationale_finds_rule_by_sha_prefix_or_stem(tmp_path: Path):
    paths = _setup(tmp_path)
    past = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
    p = _write_rule(paths, "Findable rule", review_after=past)
    # by stem
    rerationale(paths, p.stem, rationale="x")
    # by sha prefix
    sha_prefix = p.stem.split("-")[0]
    rerationale(paths, sha_prefix, rationale="y")


def test_rerationale_custom_extend_days(tmp_path: Path):
    paths = _setup(tmp_path)
    past = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
    p = _write_rule(paths, "Custom extend", review_after=past)
    rerationale(paths, p.stem, rationale="x", extend_days=14)
    mem = SemanticMemory(paths)
    reloaded = mem.read(p)
    rev = datetime.fromisoformat(reloaded.review_after + "T00:00:00+00:00").date()
    today = datetime.now(timezone.utc).date()
    assert (rev - today).days in (13, 14, 15)  # ±1 for date-math drift


# ---- expire_stale() --------------------------------------------------------


def test_expire_stale_moves_overdue_past_grace_to_expired(tmp_path: Path):
    paths = _setup(tmp_path)
    very_old = (datetime.now(timezone.utc) - timedelta(days=200)).date().isoformat()
    p = _write_rule(paths, "Ancient rule", review_after=very_old)
    moved = expire_stale(paths, grace_period_days=30)
    assert len(moved) == 1
    assert moved[0].parent == paths.dream / "expired"
    assert not p.exists()  # source rule removed
    assert moved[0].exists()  # but expired copy is preserved


def test_expire_stale_preserves_audit_via_expired_at_stamp(tmp_path: Path):
    paths = _setup(tmp_path)
    very_old = (datetime.now(timezone.utc) - timedelta(days=200)).date().isoformat()
    _write_rule(paths, "Audit me", review_after=very_old)
    moved = expire_stale(paths, grace_period_days=30)
    text = moved[0].read_text()
    assert "Expired" in text
    assert "Auto-expired" in text


def test_expire_stale_respects_grace_period(tmp_path: Path):
    paths = _setup(tmp_path)
    # 20 days overdue with 30-day grace → should NOT expire
    recent = (datetime.now(timezone.utc) - timedelta(days=20)).date().isoformat()
    _write_rule(paths, "Within grace", review_after=recent)
    moved = expire_stale(paths, grace_period_days=30)
    assert moved == []


def test_expire_stale_dry_run_does_not_move_files(tmp_path: Path):
    paths = _setup(tmp_path)
    very_old = (datetime.now(timezone.utc) - timedelta(days=200)).date().isoformat()
    p = _write_rule(paths, "Dry-run target", review_after=very_old)
    would_move = expire_stale(paths, grace_period_days=30, dry_run=True)
    assert len(would_move) == 1
    assert p.exists()  # source NOT removed
    assert not (paths.dream / "expired" / f"{p.stem}.md").exists()


def test_expire_stale_skips_due_soon(tmp_path: Path):
    paths = _setup(tmp_path)
    soon = (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat()
    _write_rule(paths, "Due soon", review_after=soon)
    moved = expire_stale(paths, grace_period_days=0)
    assert moved == []


# ---- rendered CLAUDE.md surfaces stale-rule warning ------------------------


def test_render_body_omits_lifecycle_warning_when_no_stale_rules(tmp_path: Path):
    paths = _setup(tmp_path)
    future = (datetime.now(timezone.utc) + timedelta(days=100)).date().isoformat()
    _write_rule(paths, "Fresh", review_after=future)
    cfg = Config.load(paths)
    ctx = build_context(paths, actor="alice", config=cfg)
    body = render_body(ctx, tool_label="Claude Code")
    assert "Rule lifecycle" not in body


def test_render_body_warns_when_stale_rules_exist(tmp_path: Path):
    paths = _setup(tmp_path)
    past = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    _write_rule(paths, "Old rule 1", review_after=past)
    _write_rule(paths, "Old rule 2", review_after=past)
    cfg = Config.load(paths)
    ctx = build_context(paths, actor="alice", config=cfg)
    body = render_body(ctx, tool_label="Claude Code")
    assert "Rule lifecycle" in body
    assert "overdue for review" in body
    assert "dotagent dream review-stale" in body


# ---- backward compat -------------------------------------------------------


def test_existing_semantic_tests_still_pass_with_new_fields(tmp_path: Path):
    """The pre-Module-2 test_semantic_uses_content_hash_slug pattern still works."""
    paths = _setup(tmp_path)
    mem = SemanticMemory(paths)
    e = SemanticEntry(
        kind="rules", category="bugs",
        title="Don't bypass BaseAgent.execute()",
        body="Always go through BaseAgent.execute()",
        rationale="audit rows lost",
        provenance="git log",
        evidence=["abc123", "def456"],
        graduated_by="alice",
    )
    path = mem.write(e)
    text = path.read_text()
    assert path.exists()
    assert "## Rationale" in text
    assert "## Evidence" in text
    assert "abc123" in text
    # plus new lifecycle section
    assert "## Lifecycle" in text
    assert "Graduated at" in text
