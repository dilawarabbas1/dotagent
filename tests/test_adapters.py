from __future__ import annotations

from pathlib import Path

from dotagent.adapters import REGISTRY, read_source
from dotagent.config import Config, merge_defaults
from dotagent.context import build as build_context
from dotagent.memory import EpisodicEvent, EpisodicMemory, SemanticEntry, SemanticMemory
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.sources import reindex_all
from dotagent.util import dump_yaml


def test_each_adapter_renders(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    src = read_source(paths)
    assert src["style"], "scaffold should populate style.md"
    for name, cls in REGISTRY.items():
        adapter = cls(paths)
        files = adapter.render(src)
        if name == "custom":
            # custom adapter renders nothing unless templates are present
            continue
        assert files, f"adapter {name} returned no files"
        for rf in files:
            assert rf.content
        adapter.write(files)
        for rf in files:
            assert rf.path.exists()


def test_claude_adapter_writes_claude_md(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    src = read_source(paths)
    adapter = REGISTRY["claude"](paths)
    adapter.write(adapter.render(src))
    target = tmp_path / "CLAUDE.md"
    assert target.exists()
    assert "Project context for Claude Code" in target.read_text()


def test_cursor_adapter_writes_cursorrules(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    src = read_source(paths)
    adapter = REGISTRY["cursor"](paths)
    adapter.write(adapter.render(src))
    assert (tmp_path / ".cursorrules").exists()


def test_copilot_adapter_writes_under_dot_github(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    src = read_source(paths)
    adapter = REGISTRY["copilot"](paths)
    adapter.write(adapter.render(src))
    assert (tmp_path / ".github" / "copilot-instructions.md").exists()


def test_opencode_adapter_writes_agents_md(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    src = read_source(paths)
    adapter = REGISTRY["opencode"](paths)
    adapter.write(adapter.render(src))
    assert (tmp_path / "AGENTS.md").exists()


def test_episodic_jsonl_uses_actor_session_filename(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    mem = EpisodicMemory(paths)
    ev = EpisodicEvent(
        ts=EpisodicMemory.now(),
        actor="alice",
        tool="claude_code",
        host="laptop",
        session="abc123",
        kind="commit",
    )
    p = mem.append(ev)
    assert p.name == "alice__abc123.jsonl"
    assert "episodic" in str(p)


def test_episodic_append_is_safe_concurrently_per_actor(tmp_path: Path):
    """Two actors writing on the same day produce non-conflicting filenames."""
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    mem = EpisodicMemory(paths)
    a = mem.append(EpisodicEvent(ts=EpisodicMemory.now(), actor="alice", tool="claude_code", host="a", session="s1", kind="commit"))
    b = mem.append(EpisodicEvent(ts=EpisodicMemory.now(), actor="bob",   tool="cursor",      host="b", session="s2", kind="commit"))
    assert a != b
    events = list(mem.iter_events())
    actors = {e["actor"] for e in events}
    assert actors == {"alice", "bob"}


def test_claude_adapter_renders_full_context_with_bug_registry(tmp_path: Path):
    """The richer adapter render must surface bug registry, anti-patterns, and source pointers."""
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    cfg_data = merge_defaults({"project": {"name": "demo"}})
    dump_yaml(paths.config, cfg_data)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bug-registry.md").write_text(
        "# Bug Registry\n\n"
        "## BUG-007: Auth bypass\n"
        "- **Severity**: critical\n"
        "- **File**: services/auth/jwt.py\n\nStale tokens accepted.\n"
    )
    (tmp_path / "docs" / "anti-patterns.md").write_text(
        "# Anti-Patterns\n\n## ANTI-007: Direct DB writes\n- **Severity**: high\n\nBypasses repo layer.\n"
    )
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw["sources"])
    ctx = build_context(paths, actor="alice", config=cfg)

    adapter = REGISTRY["claude"](paths)
    adapter.write(adapter.render(ctx))
    body = (tmp_path / "CLAUDE.md").read_text()
    assert "BUG-007" in body
    assert "Auth bypass" in body
    assert "ANTI-007" in body
    assert "docs/bug-registry.md" in body
    assert "docs/anti-patterns.md" in body
    assert "Source pointers" in body


def test_semantic_uses_content_hash_slug(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    mem = SemanticMemory(paths)
    e = SemanticEntry(
        kind="rules",
        category="bugs",
        title="Don't bypass BaseAgent.execute()",
        body="Always go through BaseAgent.execute() so retries/timeouts/audit fire.",
        rationale="Bypassing it lost audit rows in 4 incidents.",
        provenance="git log",
        evidence=["abc123", "def456"],
        graduated_by="alice",
    )
    path = mem.write(e)
    assert path.exists()
    text = path.read_text()
    assert "## Rationale" in text
    assert "abc123" in text
