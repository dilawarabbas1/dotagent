from __future__ import annotations

from pathlib import Path

from dotagent.config import Config, merge_defaults
from dotagent.context import build as build_context
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.skills import get_skill, list_skills, run_pipeline, run_skill
from dotagent.util import dump_yaml


def _setup(tmp_path: Path) -> Paths:
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "demo"}}))
    return paths


def test_list_skills_finds_scaffolded_skills(tmp_path: Path):
    paths = _setup(tmp_path)
    skills = list_skills(paths)
    names = {s.name for s in skills}
    assert {"observer", "research", "plan", "code", "review"} <= names


def test_skill_loader_parses_frontmatter(tmp_path: Path):
    paths = _setup(tmp_path)
    custom = paths.skills / "custom-skill.md"
    custom.write_text(
        "---\n"
        "name: custom-skill\n"
        "description: Test skill\n"
        "inputs: [task, context]\n"
        "---\n\n"
        "# Custom Skill\n\nDo the thing.\n"
    )
    s = get_skill(paths, "custom-skill")
    assert s.description == "Test skill"
    assert s.inputs == ["task", "context"]
    assert "Do the thing" in s.body


def test_run_skill_dry_run_returns_resolved_prompts(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    ctx = build_context(paths, actor="alice", config=cfg)
    res = run_skill(paths, ctx, "observer", task="ship X", dry_run=True)
    assert res["skill"] == "observer"
    assert "observer" in res["system"].lower()
    assert "ship X" in res["user"]
    assert res["output"] is None


def test_pipeline_runs_skills_in_order(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    ctx = build_context(paths, actor="alice", config=cfg)
    out = run_pipeline(paths, ctx, ["observer", "plan"], task="ship X", dry_run=True)
    assert [r["skill"] for r in out] == ["observer", "plan"]
