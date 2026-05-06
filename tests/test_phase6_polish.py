from __future__ import annotations

from pathlib import Path

from dotagent.adapters import REGISTRY
from dotagent.config import Config, merge_defaults
from dotagent.context import build as build_context
from dotagent.diff import diff_rendered, format_diff
from dotagent.migrate import migrate
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.util import dump_yaml


def _setup(tmp_path: Path) -> Paths:
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "demo"}}))
    return paths


def test_diff_rendered_reports_changes(tmp_path: Path):
    paths = _setup(tmp_path)
    cfg = Config.load(paths)
    ctx = build_context(paths, actor="alice", config=cfg)
    adapter = REGISTRY["claude"](paths)
    files = adapter.render(ctx)
    diffs_first = diff_rendered(files)
    # First render: nothing on disk → all files show as new
    assert diffs_first
    adapter.write(files)
    diffs_second = diff_rendered(files)
    # Second render with same content → no diff
    assert diffs_second == []
    text = format_diff(diffs_first)
    assert "CLAUDE.md" in text


def test_custom_adapter_renders_jinja_template(tmp_path: Path):
    paths = _setup(tmp_path)
    tmpl_dir = paths.adapters / "custom" / "templates"
    tmpl_dir.mkdir(parents=True)
    (tmpl_dir / "ai_context.md.j2").write_text(
        "{# output: docs/AI_CONTEXT.md #}\n"
        "# {{ ctx.project_name }} — AI context\n\n"
        "Active actor: {{ ctx.actor }}\n"
    )
    cfg = Config.load(paths)
    ctx = build_context(paths, actor="alice", config=cfg)
    adapter = REGISTRY["custom"](paths)
    files = adapter.render(ctx)
    assert files
    adapter.write(files)
    target = tmp_path / "docs" / "AI_CONTEXT.md"
    assert target.exists()
    out = target.read_text()
    assert "demo — AI context" in out
    assert "alice" in out


def test_cco_migrator_references_docs_and_imports_prompts(tmp_path: Path):
    paths = _setup(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bug-registry.md").write_text("# Bug Registry\n\n## BUG-001: x\n\nbody.\n")
    (tmp_path / "docs" / "anti-patterns.md").write_text("# Anti\n\n## ANTI-001: x\n\nbody.\n")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "deep-debug.md").write_text("# Deep debug\n\nDo deep debugging.\n")

    report = migrate(paths)

    assert "docs/bug-registry.md" in report.referenced_sources
    assert "docs/anti-patterns.md" in report.referenced_sources
    assert any("imported-deep-debug" in s for s in report.imported_skills)
    # docs untouched
    assert (tmp_path / "docs" / "bug-registry.md").read_text().startswith("# Bug Registry")
    # prompt copied as a skill with frontmatter
    skill = paths.skills / "imported-deep-debug.md"
    assert skill.exists()
    assert skill.read_text().startswith("---")
    # config now references docs/
    cfg = Config.load(paths)
    assert cfg.raw["sources"]["bug_registry"] == "docs/bug-registry.md"
