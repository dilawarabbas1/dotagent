from __future__ import annotations

from pathlib import Path

from dotagent.adapters.render import render_body
from dotagent.config import Config, merge_defaults
from dotagent.context import build
from dotagent.memory import EpisodicEvent, EpisodicMemory, PersonalMemory, WorkingMemory
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.sources import reindex_all
from dotagent.util import dump_yaml


BUG_REGISTRY = """# Bug Registry

## BUG-101: Critical token leak
- **Severity**: critical
- **Files**: services/auth/jwt.py

Tokens leaked because the redact filter was inverted.

## BUG-102: Slow pagination
- **Severity**: low
- **Files**: services/api/list.py
"""

ANTI = """# Anti-Patterns

## ANTI-001: Direct DB writes from controllers
- **Severity**: high
- **Files**: services/api/controllers.py

Bypasses the repository layer.
"""


def _setup_repo(tmp_path: Path) -> Paths:
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    cfg_data = merge_defaults({"project": {"name": "demo"}})
    dump_yaml(paths.config, cfg_data)
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "bug-registry.md").write_text(BUG_REGISTRY)
    (tmp_path / "docs" / "anti-patterns.md").write_text(ANTI)
    return paths


def test_context_merges_sources_personal_working_episodic(tmp_path: Path):
    paths = _setup_repo(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])

    PersonalMemory(paths, "alice").save({"editor": "vim", "favorite_lang": "python"})
    WorkingMemory(paths, "alice").record_event(
        kind="edit", tool="claude_code", summary="touched jwt", files=["services/auth/jwt.py"], branch="main",
    )
    EpisodicMemory(paths).append(EpisodicEvent(
        ts=EpisodicMemory.now(), actor="alice", tool="claude_code", host="laptop",
        session="s1", kind="commit", summary="fix jwt", files=["services/auth/jwt.py"],
    ))

    ctx = build(paths, actor="alice", config=cfg)
    assert ctx.actor == "alice"
    assert ctx.project_name == "demo"
    assert "bug_registry" in ctx.sources
    assert "anti_patterns" in ctx.sources
    assert ctx.sources["bug_registry"].exists
    assert ctx.personal["editor"] == "vim"
    assert "services/auth/jwt.py" in ctx.current.recent_files
    assert ctx.recent_episodic
    bugs = ctx.top_bugs()
    assert bugs and bugs[0].id == "BUG-101"  # critical first


def test_render_body_includes_all_sections(tmp_path: Path):
    paths = _setup_repo(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    PersonalMemory(paths, "alice").save({"editor": "vim"})
    WorkingMemory(paths, "alice").record_event(
        kind="edit", tool="claude_code", summary="x", files=["services/auth/jwt.py"], branch="main",
    )
    ctx = build(paths, actor="alice", config=cfg)
    body = render_body(ctx, tool_label="Claude Code")

    # Source-of-truth pointers
    assert "docs/bug-registry.md" in body
    assert "docs/anti-patterns.md" in body
    # Critical bug surfaced
    assert "BUG-101" in body
    assert "Critical token leak" in body
    # Anti-pattern surfaced
    assert "ANTI-001" in body
    # Working memory surfaced
    assert "services/auth/jwt.py" in body
    # Personal memory surfaced
    assert "vim" in body
    # Source pointers footer
    assert "Source pointers" in body


def test_top_bugs_orders_by_severity(tmp_path: Path):
    paths = _setup_repo(tmp_path)
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    ctx = build(paths, actor="alice", config=cfg)
    bugs = ctx.top_bugs()
    assert bugs[0].severity == "critical"
    assert bugs[-1].severity == "low"


# Sharded-docs aggregation: a kind backed by a thin canonical index PLUS
# per-domain shards (registered under sources.extra with the same kind)
# must surface entries from EVERY shard, not just the canonical file.
# Regression for the composr case: backend/docs/bug-registry-*.md held
# thousands of lines of real entries that never reached the agent context
# because top_bugs() read only sources["bug_registry"] (an index stub).
SHARD_AGENTS = """# Bug Registry — agents shard

## AGT-9001: Agent prompt cache poisoning
- **Severity**: high
- **Files**: services/agent-runner/prompt.py

Stale cache served a poisoned prompt across tenants.
"""

SHARD_INFRA = """# Bug Registry — infra shard

## INF-7001: Redis connection storm on boot
- **Severity**: medium
- **Files**: services/boot/redis_init.py

All workers opened clients simultaneously and tripped maxclients.
"""


def test_kind_aggregates_across_extra_shards(tmp_path: Path):
    paths = _setup_repo(tmp_path)
    # Canonical bug-registry (index stub with one entry) already written by
    # _setup_repo. Add two backend shards + register them as same-kind extras.
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "bug-registry-agents.md").write_text(SHARD_AGENTS)
    (tmp_path / "docs" / "bug-registry-infra.md").write_text(SHARD_INFRA)
    cfg = Config.load(paths)
    cfg.raw["sources"]["extra"] = [
        {"name": "bug_registry_agents", "path": "docs/bug-registry-agents.md", "kind": "bug_registry"},
        {"name": "bug_registry_infra", "path": "docs/bug-registry-infra.md", "kind": "bug_registry"},
    ]
    reindex_all(paths, cfg.raw["sources"])
    ctx = build(paths, actor="alice", config=cfg)
    ids = {b.id for b in ctx.top_bugs()}
    # Canonical entries AND both shards' entries are all surfaced.
    assert "BUG-101" in ids, f"canonical entry missing: {ids}"
    assert "AGT-9001" in ids, f"agents-shard entry missing: {ids}"
    assert "INF-7001" in ids, f"infra-shard entry missing: {ids}"
