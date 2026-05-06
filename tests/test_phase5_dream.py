from __future__ import annotations

from pathlib import Path

import pytest

from dotagent.dream import generate_candidates, graduate, reject
from dotagent.dream.signals import extract_signals
from dotagent.memory import EpisodicEvent, EpisodicMemory
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir


def _ev(**kw) -> EpisodicEvent:
    base = dict(ts=EpisodicMemory.now(), actor="alice", tool="claude_code", host="h",
                session="s1", kind="commit", repo="demo", branch="main", files=[], summary="")
    base.update(kw)
    return EpisodicEvent(**base)


def test_signals_finds_revert_cluster(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    mem = EpisodicMemory(paths)
    mem.append(_ev(summary="Revert: fix"))
    mem.append(_ev(actor="bob", session="s2", summary="Revert thing"))
    sigs = extract_signals(paths, since="30d", min_cluster_size=2)
    kinds = {s.kind for s in sigs}
    assert "revert_cluster" in kinds


def test_signals_finds_repeat_fix(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    mem = EpisodicMemory(paths)
    for i in range(3):
        mem.append(_ev(session=f"s{i}", summary=f"fix: bug {i}", files=["repeat.py"]))
    sigs = extract_signals(paths, since="30d", min_cluster_size=3)
    fix_sigs = [s for s in sigs if s.kind == "repeat_fix"]
    assert fix_sigs
    assert "repeat.py" in fix_sigs[0].files


def test_graduate_requires_rationale(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    mem = EpisodicMemory(paths)
    for i in range(3):
        mem.append(_ev(session=f"s{i}", summary=f"fix: bug {i}", files=["repeat.py"]))
    sigs = extract_signals(paths, since="30d", min_cluster_size=3)
    written = generate_candidates(paths, sigs)
    assert written
    cid = written[0].stem
    with pytest.raises(ValueError):
        graduate(paths, cid, rationale="")
    target = graduate(paths, cid, rationale="Recurring fix indicates a missing test gate")
    assert target.exists()
    text = target.read_text()
    assert "Rationale" in text
    # source candidate file is moved out of candidates/
    assert not (paths.dream / "candidates" / f"{cid}.md").exists()
    # graduated entry also written into semantic memory
    sem_files = list(paths.semantic.rglob("*.md"))
    assert any("auto-dream" in str(p) for p in sem_files)


def test_reject_requires_rationale_and_moves_file(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    mem = EpisodicMemory(paths)
    for i in range(3):
        mem.append(_ev(session=f"s{i}", summary=f"fix: bug {i}", files=["x.py"]))
    sigs = extract_signals(paths, since="30d", min_cluster_size=3)
    written = generate_candidates(paths, sigs)
    cid = written[0].stem
    with pytest.raises(ValueError):
        reject(paths, cid, rationale="")
    target = reject(paths, cid, rationale="Coincidental — three independent bugs, not a pattern")
    assert target.exists()
    assert "Rejection rationale" in target.read_text()
