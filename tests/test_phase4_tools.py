from __future__ import annotations

from pathlib import Path

from dotagent.config import merge_defaults
from dotagent.memory import EpisodicEvent, EpisodicMemory
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.sources import reindex_all
from dotagent.tools.debug_investigator import investigate_stack
from dotagent.tools.deploy_checklist import build_checklist
from dotagent.tools.memory_manager import search_all, summarize
from dotagent.tools.pattern_extractor import extract_python_patterns, write_patterns
from dotagent.util import dump_yaml


def test_pattern_extractor_finds_python_imports(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("import os\nimport json\nfrom collections import Counter\n")
    (tmp_path / "src" / "b.py").write_text("import os\nimport sys\n")
    res = extract_python_patterns(tmp_path)
    assert res["imports"]["os"] == 2
    assert res["imports"]["json"] == 1
    assert "collections" in res["imports"]


def test_pattern_extractor_writes_semantic_entries(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("import os\nimport json\n")
    written = write_patterns(paths)
    assert written
    body = written[0].read_text()
    assert "import landscape" in body.lower()
    assert "Rationale" in body


def test_memory_manager_search_finds_episodic_events(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    EpisodicMemory(paths).append(EpisodicEvent(
        ts=EpisodicMemory.now(), actor="alice", tool="claude_code", host="h",
        session="s1", kind="commit", summary="fix BUG-001 token leak",
    ))
    res = search_all(paths, "BUG-001")
    assert res["episodic"]
    assert "BUG-001" in res["episodic"][0]["snippet"]


def test_memory_summarize_returns_counts(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    s = summarize(paths)
    assert s["episodic_files"] == 0
    assert s["dream_candidates"] == 0


def test_debug_investigator_matches_files_and_bugs(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    cfg = merge_defaults({"project": {"name": "demo"}})
    dump_yaml(paths.config, cfg)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bug-registry.md").write_text(
        "# Bugs\n\n## BUG-001: JWT failure\n- **Files**: services/auth/jwt.py\n\nStale tokens.\n"
    )
    reindex_all(paths, cfg["sources"])
    EpisodicMemory(paths).append(EpisodicEvent(
        ts=EpisodicMemory.now(), actor="alice", tool="claude_code", host="h",
        session="s1", kind="commit", summary="touched jwt", files=["services/auth/jwt.py"],
    ))
    stack = (
        'Traceback (most recent call last):\n'
        '  File "services/auth/jwt.py", line 42, in verify\n'
        '    raise TokenError("stale")\n'
        'TokenError: stale\n'
    )
    findings = investigate_stack(paths, stack)
    assert findings["signature"]["files"] == ["services/auth/jwt.py"]
    assert "TokenError" in findings["signature"]["errors"]
    assert findings["bug_matches"]
    assert findings["bug_matches"][0]["id"] == "BUG-001"
    assert findings["episodic_matches"]


def test_deploy_checklist_pulls_from_rules_and_bugs(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    cfg = merge_defaults({})
    dump_yaml(paths.config, cfg)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bug-registry.md").write_text(
        "# Bugs\n\n## BUG-002: Auth\n- **Severity**: critical\n- **Files**: a.py\n\nbad.\n"
    )
    reindex_all(paths, cfg["sources"])
    cl = build_checklist(paths, since="14d")
    assert cl["window"] == "14d"
    texts = [it["text"] for it in cl["items"]]
    assert any("BUG-002" in t for t in texts)
    assert any(it["source"] == "rules.md" for it in cl["items"])  # scaffold rules.md has bullets
