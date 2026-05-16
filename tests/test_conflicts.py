"""Module 1 — Conflict Detection.

When working-memory recent files overlap with semantic rules / bug-registry
entries / anti-patterns citing those files, the Context resolver surfaces the
overlap as a `Conflict` row and the renderer adds a ⚠ section to CLAUDE.md.

Built in response to Faisal Feroz's LinkedIn feedback: "how do you handle
conflicts when working memory contradicts what semantic memory says is the
team standard."
"""

from __future__ import annotations

from pathlib import Path

from dotagent.adapters.render import render_body
from dotagent.config import Config, merge_defaults
from dotagent.context import build as build_context
from dotagent.memory import WorkingMemory
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.sources import reindex_all
from dotagent.util import dump_yaml


BUG_REGISTRY = """# Bug Registry

## BUG-100: Auth bypass via stale JWT
- **Severity**: critical
- **Files**: services/auth/jwt.py, services/cache/redis.js

The cache TTL exceeded the rotation window.
"""

ANTI_PATTERNS = """# Anti-patterns

## ANTI-100: Direct DB writes from controllers
- **Severity**: high
- **Files**: services/api/controllers.py

Controllers must call repositories.

## ANTI-101: Unbounded retry loops
- **Severity**: medium
- **Files**: services/notifier/slack.py
"""


def _setup(tmp_path: Path) -> Paths:
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "demo"}}))
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "bug-registry.md").write_text(BUG_REGISTRY)
    (tmp_path / "docs" / "anti-patterns.md").write_text(ANTI_PATTERNS)
    return paths


def _seed_working_memory(paths: Paths, actor: str, files: list[str]) -> None:
    wm = WorkingMemory(paths, actor)
    for f in files:
        wm.record_event(kind="edit", tool="claude_code", files=[f], summary="test")


# ---- detect_conflicts() ----------------------------------------------------

def test_no_conflicts_when_working_memory_empty(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    ctx = build_context(paths, actor="alice", config=cfg)
    assert ctx.detect_conflicts() == []


def test_no_conflicts_when_files_dont_match_rules(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    _seed_working_memory(paths, "alice", ["services/billing/invoice.py", "tests/test_invoice.py"])
    ctx = build_context(paths, actor="alice", config=cfg)
    assert ctx.detect_conflicts() == []


def test_conflict_surfaced_when_file_matches_bug_registry(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    _seed_working_memory(paths, "alice", ["services/auth/jwt.py"])
    ctx = build_context(paths, actor="alice", config=cfg)
    rows = ctx.detect_conflicts()
    assert len(rows) == 1
    assert rows[0]["id"] == "BUG-100"
    assert rows[0]["kind"] == "bug-registry"
    assert rows[0]["severity"] == "critical"
    assert "services/auth/jwt.py" in rows[0]["all_touched_files"]


def test_conflict_surfaced_when_file_matches_anti_pattern(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    _seed_working_memory(paths, "alice", ["services/api/controllers.py"])
    ctx = build_context(paths, actor="alice", config=cfg)
    rows = ctx.detect_conflicts()
    assert len(rows) == 1
    assert rows[0]["id"] == "ANTI-100"
    assert rows[0]["kind"] == "anti-pattern"
    assert rows[0]["severity"] == "high"


def test_conflicts_ordered_by_severity_critical_first(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    _seed_working_memory(paths, "alice", [
        "services/notifier/slack.py",    # ANTI-101 medium
        "services/auth/jwt.py",          # BUG-100 critical
        "services/api/controllers.py",   # ANTI-100 high
    ])
    ctx = build_context(paths, actor="alice", config=cfg)
    rows = ctx.detect_conflicts()
    assert [r["severity"] for r in rows] == ["critical", "high", "medium"]


def test_conflict_top_n_respected(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    _seed_working_memory(paths, "alice", [
        "services/auth/jwt.py", "services/api/controllers.py",
        "services/notifier/slack.py",
    ])
    ctx = build_context(paths, actor="alice", config=cfg)
    assert len(ctx.detect_conflicts(top_n=2)) == 2


def test_conflict_remedy_includes_action_hint(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    _seed_working_memory(paths, "alice", ["services/auth/jwt.py"])
    ctx = build_context(paths, actor="alice", config=cfg)
    row = ctx.detect_conflicts()[0]
    assert "regress" in row["what_to_do"].lower() or "review" in row["what_to_do"].lower()


# ---- rendered CLAUDE.md ----------------------------------------------------

def test_render_body_omits_conflict_section_when_no_conflicts(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    ctx = build_context(paths, actor="alice", config=cfg)
    body = render_body(ctx, tool_label="Claude Code")
    assert "Rule conflicts in active edits" not in body


def test_render_body_surfaces_conflicts_section(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    _seed_working_memory(paths, "alice", [
        "services/auth/jwt.py",          # BUG-100 critical
        "services/api/controllers.py",   # ANTI-100 high
    ])
    ctx = build_context(paths, actor="alice", config=cfg)
    body = render_body(ctx, tool_label="Claude Code")
    assert "Rule conflicts in active edits" in body
    assert "BUG-100" in body
    assert "ANTI-100" in body
    # source-of-truth path appears
    assert "docs/bug-registry.md" in body or "bug-registry.md" in body
    # severity markers visible
    assert "CRITICAL" in body
    # ordered: critical first
    assert body.index("BUG-100") < body.index("ANTI-100")


def test_conflicts_section_appears_before_rules_section(tmp_path: Path):
    """Conflicts are more time-sensitive than general rules — prominence matters."""
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    _seed_working_memory(paths, "alice", ["services/auth/jwt.py"])
    ctx = build_context(paths, actor="alice", config=cfg)
    body = render_body(ctx, tool_label="Claude Code")
    assert body.index("Rule conflicts") < body.index("Project rules")


def test_legacy_dict_context_does_not_break_renderer(tmp_path: Path):
    """The legacy dict source signature must keep working (no detect_conflicts call)."""
    from dotagent.adapters.render import coerce_to_context
    legacy_dict = {
        "style": "s", "rules": "r", "architecture": "a",
        "patterns": "p", "preferences": "x",
    }
    ctx = coerce_to_context(legacy_dict, Paths(repo=tmp_path))
    body = render_body(ctx, tool_label="Claude Code")
    assert "Rule conflicts in active edits" not in body  # no working memory in legacy dict path
