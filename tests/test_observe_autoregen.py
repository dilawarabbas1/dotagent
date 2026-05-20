"""Tests for the auto-regen-adapters-on-docs-change hook behavior.

When `dotagent observe` is called with `--files` that includes a
docs/*.md file, the existing pipeline reindexes the source. As of
v0.4.9, it also re-renders every enabled adapter so CLAUDE.md +
sister files stay in sync with the docs.

Disabled via `hooks.auto_regen_on_docs: false` in `.agent/config.yaml`.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from dotagent.commands.observe_cmd import observe
from dotagent.config import merge_defaults
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.util import dump_yaml


def _init_repo(tmp_path: Path) -> Path:
    """Minimal scaffolded dotagent project with a populated config.yaml
    so `adapters_enabled` returns the default set."""
    repo = tmp_path / "repo"
    repo.mkdir()
    paths = Paths(repo=repo)
    scaffold_agent_dir(paths)
    cfg_data = merge_defaults({"project": {"name": "demo"}})
    dump_yaml(paths.config, cfg_data)
    # Initialize a docs/ folder with a bug-registry.md the user could edit
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs" / "bug-registry.md").write_text(
        "# Bug registry\n\n## BUG-001\n- status: open\n"
    )
    return repo


def _run_observe(repo: Path, files: str) -> object:
    runner = CliRunner()
    # observe runs find_repo_root via cwd context — use isolated_filesystem
    # is overkill; we monkeypatch cwd via runner.
    import os
    cwd = os.getcwd()
    os.chdir(repo)
    try:
        return runner.invoke(
            observe,
            ["pre-commit", "--files", files, "--tool", "claude_code"],
            catch_exceptions=False,
        )
    finally:
        os.chdir(cwd)


def test_observe_regenerates_claude_md_when_docs_touched(tmp_path: Path):
    repo = _init_repo(tmp_path)
    claude_md = repo / "CLAUDE.md"
    # Ensure CLAUDE.md doesn't exist yet
    assert not claude_md.exists()

    result = _run_observe(repo, "docs/bug-registry.md")
    assert result.exit_code == 0, result.output

    # After observe-pre-commit on a docs/ change, CLAUDE.md should exist
    assert claude_md.exists(), (
        "auto-regen should have created CLAUDE.md after docs/ touch"
    )


def test_observe_does_not_regenerate_when_non_docs_touched(tmp_path: Path):
    repo = _init_repo(tmp_path)
    claude_md = repo / "CLAUDE.md"
    result = _run_observe(repo, "src/main.py")
    assert result.exit_code == 0
    # Non-docs change → no regen → no CLAUDE.md created
    assert not claude_md.exists()


def test_observe_respects_auto_regen_disabled(tmp_path: Path):
    repo = _init_repo(tmp_path)
    # Disable via config
    config_path = repo / ".agent" / "config.yaml"
    existing = config_path.read_text() if config_path.exists() else ""
    config_path.write_text(existing + "\nhooks:\n  auto_regen_on_docs: false\n")

    claude_md = repo / "CLAUDE.md"
    result = _run_observe(repo, "docs/bug-registry.md")
    assert result.exit_code == 0
    # Auto-regen disabled → no CLAUDE.md created even though docs changed
    assert not claude_md.exists(), (
        "auto_regen_on_docs: false should suppress adapter regeneration"
    )


def test_observe_regenerates_all_enabled_adapters(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _run_observe(repo, "docs/bug-registry.md")
    # Default-enabled adapters: claude, cursor, copilot (opencode is opt-in)
    assert (repo / "CLAUDE.md").exists()
    assert (repo / ".cursorrules").exists()
    assert (repo / ".github" / "copilot-instructions.md").exists()
