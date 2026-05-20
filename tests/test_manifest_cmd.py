"""Tests for `dotagent manifest` — the explicit generator entrypoint
for the CLAUDE.md navigation manifest renderer.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from dotagent.commands.manifest_cmd import manifest


def _make_repo(tmp_path: Path, parent: str | None = None) -> Path:
    repo = tmp_path / "repo"
    (repo / ".agent").mkdir(parents=True)
    if parent is not None:
        (repo / ".agent" / "config.yaml").write_text(f"parent: {parent}\n")
    return repo


def test_manifest_renders_to_stdout(tmp_path: Path):
    repo = _make_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(manifest, ["--repo", str(repo)])
    assert result.exit_code == 0, result.output
    assert "Project context" in result.output
    assert "WORKFLOW CONTRACT" in result.output


def test_manifest_force_tier_single_repo(tmp_path: Path):
    repo = _make_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        manifest, ["--repo", str(repo), "--tier", "single-repo"]
    )
    assert result.exit_code == 0
    assert "single-repo (standalone)" in result.output


def test_manifest_force_tier_service_repo_has_inherited(tmp_path: Path):
    repo = _make_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        manifest, ["--repo", str(repo), "--tier", "service-repo"]
    )
    assert result.exit_code == 0
    assert "INHERITED" in result.output
    assert "../.agent/project_brief.md" in result.output


def test_manifest_force_tier_project_root_no_parent_refs(tmp_path: Path):
    repo = _make_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        manifest, ["--repo", str(repo), "--tier", "project-root"]
    )
    assert result.exit_code == 0
    # project-root has no parent — should NOT render ../-prefixed entries
    assert "../.agent/project_brief.md" not in result.output


def test_manifest_write_to_file(tmp_path: Path):
    repo = _make_repo(tmp_path)
    out = tmp_path / "preview" / "CLAUDE.preview.md"
    runner = CliRunner()
    result = runner.invoke(
        manifest, ["--repo", str(repo), "--write", str(out), "--tier", "single-repo"]
    )
    assert result.exit_code == 0
    assert out.exists()
    assert "Project context" in out.read_text()
    # Path was created including parent dirs
    assert out.parent.is_dir()


def test_manifest_diff_against_missing_file_shows_full_diff(tmp_path: Path):
    repo = _make_repo(tmp_path)
    # The flag is exists=True, so we need an actual file. Use an empty one.
    target = tmp_path / "existing.md"
    target.write_text("")
    runner = CliRunner()
    result = runner.invoke(
        manifest,
        ["--repo", str(repo), "--diff", str(target), "--tier", "single-repo"],
    )
    assert result.exit_code == 0
    # Diff output shows additions (the entire rendered manifest is new)
    assert "+# Project context" in result.output


def test_manifest_diff_identical_content(tmp_path: Path):
    repo = _make_repo(tmp_path)
    runner = CliRunner()
    # First render the manifest to a file
    out = tmp_path / "current.md"
    result_write = runner.invoke(
        manifest, ["--repo", str(repo), "--write", str(out), "--tier", "single-repo"]
    )
    assert result_write.exit_code == 0
    # Then diff that file against the same tier — should report no diff
    result_diff = runner.invoke(
        manifest,
        ["--repo", str(repo), "--diff", str(out), "--tier", "single-repo"],
    )
    assert result_diff.exit_code == 0
    # The "no diff" message goes to stderr in click; CliRunner mixes them
    assert "No diff" in result_diff.output


def test_manifest_errors_without_dot_agent(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    runner = CliRunner()
    result = runner.invoke(manifest, ["--repo", str(bare)])
    assert result.exit_code != 0
    assert "No .agent" in result.output


def test_manifest_auto_detects_service_repo_tier(tmp_path: Path):
    """When --tier is not passed and config has `parent:`, detect service-repo."""
    repo = _make_repo(tmp_path, parent="../meta")
    runner = CliRunner()
    result = runner.invoke(manifest, ["--repo", str(repo)])
    assert result.exit_code == 0
    # Auto-detected as service-repo, so should have INHERITED markers
    assert "INHERITED" in result.output
