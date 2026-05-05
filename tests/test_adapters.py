from __future__ import annotations

from pathlib import Path

from dotagent.adapters import REGISTRY, read_source
from dotagent.memory import EpisodicEvent, EpisodicMemory, SemanticEntry, SemanticMemory
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir


def test_each_adapter_renders(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    src = read_source(paths)
    assert src["style"], "scaffold should populate style.md"
    for name, cls in REGISTRY.items():
        adapter = cls(paths)
        files = adapter.render(src)
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
