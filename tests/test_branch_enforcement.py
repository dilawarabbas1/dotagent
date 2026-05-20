"""Tests for branch reservation enforcement (init-hooks + scaffold)."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from click.testing import CliRunner

from dotagent.cli import main


def _invoke(runner: CliRunner, args: list[str], cwd: Path):
    orig = os.getcwd()
    os.chdir(cwd)
    try:
        return runner.invoke(main, args, catch_exceptions=False)
    finally:
        os.chdir(orig)


def _scaffold_repo_with_git_yaml(tmp_path: Path, strategy: str = "dedicated_repo") -> Path:
    """A repo with .git/, .agent/, and a valid git.yaml."""
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / "git.yaml").write_text(yaml.safe_dump({
        "meta": {
            "strategy": strategy,
            "remote": "git@github.com:org/meta.git",
            "branch": "dotagent/meta",
            "main_branch_policy": "locked",
        },
        "repos": [
            {"id": "backend", "path": "./backend", "remote": "git@github.com:org/backend.git",
             "default_branch": "main", "role": "api"},
        ],
        "branch_rules": [
            {
                "remote": "git@github.com:org/meta.git",
                "branches": {
                    "main": {"allowed_paths": [], "forbidden_paths": ["**/*"]},
                    "dotagent/meta": {
                        "allowed_paths": [".agent/", "docs/", "*.md"],
                        "forbidden_paths": ["**/*.py"],
                    },
                },
            },
        ],
    }))
    return tmp_path


def test_init_hooks_writes_pre_push_executable(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo_with_git_yaml(tmp_path)
    result = _invoke(runner, ["git", "init-hooks"], repo)
    assert result.exit_code == 0, result.output
    hook = repo / ".git" / "hooks" / "pre-push"
    assert hook.exists()
    assert "dotagent git verify" in hook.read_text()
    # Executable bit set
    assert hook.stat().st_mode & 0o111 != 0


def test_init_hooks_refuses_to_overwrite(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo_with_git_yaml(tmp_path)
    hook = repo / ".git" / "hooks" / "pre-push"
    hook.write_text("# existing\n")
    result = _invoke(runner, ["git", "init-hooks"], repo)
    assert result.exit_code == 1
    assert "exists" in result.output


def test_init_hooks_force_overwrites(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo_with_git_yaml(tmp_path)
    hook = repo / ".git" / "hooks" / "pre-push"
    hook.write_text("# stale content\n")
    result = _invoke(runner, ["git", "init-hooks", "--force"], repo)
    assert result.exit_code == 0
    body = hook.read_text()
    assert "stale content" not in body
    assert "dotagent git verify" in body


def test_init_hooks_refuses_for_non_dedicated_strategy(tmp_path: Path):
    """Service repos (reserved-branch strategy) should NOT install meta hooks."""
    runner = CliRunner()
    repo = _scaffold_repo_with_git_yaml(tmp_path, strategy="reserved_branch")
    result = _invoke(runner, ["git", "init-hooks"], repo)
    assert result.exit_code == 1
    assert "dedicated_repo" in result.output


def test_scaffold_protection_writes_workflow(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo_with_git_yaml(tmp_path)
    result = _invoke(runner, ["git", "scaffold-protection"], repo)
    assert result.exit_code == 0, result.output
    workflow = repo / ".github" / "workflows" / "branch-rules.yml"
    assert workflow.exists()
    body = workflow.read_text()
    assert "dotagent git verify" in body
    assert "branch-rules" in body


def test_scaffold_protection_refuses_overwrite_without_force(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo_with_git_yaml(tmp_path)
    workflow = repo / ".github" / "workflows" / "branch-rules.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("# existing\n")
    result = _invoke(runner, ["git", "scaffold-protection"], repo)
    assert result.exit_code == 1


def test_verify_passes_on_meta_branch_with_meta_files(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo_with_git_yaml(tmp_path)
    result = _invoke(
        runner,
        [
            "git", "verify",
            "--remote", "git@github.com:org/meta.git",
            "--branch", "dotagent/meta",
            "--paths", ".agent/architecture.md",
            "--paths", "docs/bug-registry.md",
        ],
        repo,
    )
    assert result.exit_code == 0
    assert "match" in result.output


def test_verify_fails_on_python_file_in_meta_branch(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo_with_git_yaml(tmp_path)
    result = _invoke(
        runner,
        [
            "git", "verify",
            "--remote", "git@github.com:org/meta.git",
            "--branch", "dotagent/meta",
            "--paths", "backend/auth.py",
        ],
        repo,
    )
    assert result.exit_code == 1
    assert "backend/auth.py" in result.output
    assert "violate" in result.output


def test_verify_rejects_everything_on_locked_main(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo_with_git_yaml(tmp_path)
    result = _invoke(
        runner,
        [
            "git", "verify",
            "--remote", "git@github.com:org/meta.git",
            "--branch", "main",
            "--paths", "README.md",
        ],
        repo,
    )
    assert result.exit_code == 1


def test_verify_no_rule_status(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo_with_git_yaml(tmp_path)
    result = _invoke(
        runner,
        [
            "git", "verify",
            "--remote", "git@github.com:other/repo.git",
            "--branch", "main",
            "--paths", "x.txt",
            "--format", "json",
        ],
        repo,
    )
    assert result.exit_code == 0
    assert "no-rule" in result.output
