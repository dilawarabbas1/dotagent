from __future__ import annotations

from pathlib import Path

from dotagent import episodic_index
from dotagent.memory import EpisodicEvent, EpisodicMemory
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir


def _ev(**kw) -> EpisodicEvent:
    base = dict(ts=EpisodicMemory.now(), actor="alice", tool="claude_code", host="laptop",
                session="s1", kind="commit", repo="demo", branch="main", files=[], summary="")
    base.update(kw)
    return EpisodicEvent(**base)


def test_episodic_index_round_trips_events(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    mem = EpisodicMemory(paths)
    mem.append(_ev(actor="alice", session="s1", files=["a.py"], summary="fix a"))
    mem.append(_ev(actor="bob", tool="cursor", session="s2", files=["a.py", "b.py"], summary="refactor"))
    rows = episodic_index.activity(paths, limit=10)
    assert len(rows) == 2
    actors = {r["actor"] for r in rows}
    assert actors == {"alice", "bob"}


def test_who_touched_file_aggregates_by_actor_tool(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    mem = EpisodicMemory(paths)
    mem.append(_ev(actor="alice", session="s1", files=["x.py"]))
    mem.append(_ev(actor="alice", session="s2", files=["x.py"]))
    mem.append(_ev(actor="bob", tool="cursor", session="s3", files=["x.py"]))
    rows = episodic_index.who_touched_file(paths, "x.py")
    assert len(rows) == 2  # alice/claude_code, bob/cursor
    by_actor = {r["actor"]: r for r in rows}
    assert by_actor["alice"]["n"] == 2
    assert by_actor["bob"]["n"] == 1


def test_timeline_orders_by_recency(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    mem = EpisodicMemory(paths)
    mem.append(_ev(actor="alice", session="s1", files=["x.py"], summary="first", ts="2026-01-01T00:00:00Z"))
    mem.append(_ev(actor="bob", session="s2", files=["x.py"], summary="second", ts="2026-02-01T00:00:00Z"))
    rows = episodic_index.timeline(paths, "x.py", limit=10)
    assert rows[0]["summary"] == "second"
    assert rows[1]["summary"] == "first"


def test_leaderboard_counts_per_actor_tool(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    mem = EpisodicMemory(paths)
    mem.append(_ev(actor="alice", session="s1", kind="commit"))
    mem.append(_ev(actor="alice", session="s2", kind="commit"))
    mem.append(_ev(actor="bob", session="s3", kind="commit"))
    rows = episodic_index.leaderboard(paths)
    by_actor = {r["actor"]: r for r in rows}
    assert by_actor["alice"]["events"] == 2
    assert by_actor["bob"]["events"] == 1


def test_parse_since_handles_relative_durations():
    iso = episodic_index.parse_since("7d")
    assert iso.endswith("Z")
    assert "T" in iso
