from __future__ import annotations

import subprocess
from unittest.mock import patch

from click.testing import CliRunner

from dotagent.commands import update_cmd
from dotagent.commands.update_cmd import update


def test_check_prints_versions_without_running_install():
    runner = CliRunner()
    with patch.object(update_cmd, "_latest_main_sha", return_value="abc1234"), \
         patch.object(update_cmd, "_detect_install_method", return_value="pipx"), \
         patch.object(update_cmd, "_installed_version", return_value="0.3.0"), \
         patch("subprocess.run") as run:
        result = runner.invoke(update, ["--check"])
    assert result.exit_code == 0
    assert "dotagent 0.3.0" in result.output
    assert "abc1234" in result.output
    assert "pipx" in result.output
    run.assert_not_called()


def test_check_handles_unreachable_github():
    runner = CliRunner()
    with patch.object(update_cmd, "_latest_main_sha", return_value=None), \
         patch.object(update_cmd, "_detect_install_method", return_value="pipx"), \
         patch.object(update_cmd, "_installed_version", return_value="0.3.0"):
        result = runner.invoke(update, ["--check"])
    assert result.exit_code == 0
    assert "could not reach github" in result.output


def test_dry_run_pipx_prints_install_command_only():
    runner = CliRunner()
    with patch.object(update_cmd, "_latest_main_sha", return_value="abc1234"), \
         patch.object(update_cmd, "_detect_install_method", return_value="pipx"), \
         patch.object(update_cmd, "_installed_version", return_value="0.3.0"), \
         patch("shutil.which", return_value="/usr/bin/pipx"), \
         patch("subprocess.run") as run:
        result = runner.invoke(update, ["--dry-run"])
    assert result.exit_code == 0
    assert "pipx install --force git+https://github.com/dilawarabbas1/dotagent" in result.output
    run.assert_not_called()


def test_dry_run_pip_uses_pip_install_upgrade():
    runner = CliRunner()
    with patch.object(update_cmd, "_latest_main_sha", return_value="abc1234"), \
         patch.object(update_cmd, "_detect_install_method", return_value="pip"), \
         patch.object(update_cmd, "_installed_version", return_value="0.3.0"), \
         patch("subprocess.run") as run:
        result = runner.invoke(update, ["--dry-run"])
    assert result.exit_code == 0
    assert "pip install --upgrade git+https://github.com/dilawarabbas1/dotagent" in result.output
    run.assert_not_called()


def test_editable_install_refuses_and_exits_nonzero():
    runner = CliRunner()
    with patch.object(update_cmd, "_latest_main_sha", return_value="abc1234"), \
         patch.object(update_cmd, "_detect_install_method", return_value="editable"), \
         patch.object(update_cmd, "_installed_version", return_value="0.3.0"), \
         patch("subprocess.run") as run:
        result = runner.invoke(update, [])
    assert result.exit_code == 1
    assert "editable install detected" in result.output
    run.assert_not_called()


def test_ref_appends_at_branch_to_git_url():
    runner = CliRunner()
    with patch.object(update_cmd, "_latest_main_sha", return_value=None), \
         patch.object(update_cmd, "_detect_install_method", return_value="pip"), \
         patch.object(update_cmd, "_installed_version", return_value="0.3.0"), \
         patch("subprocess.run") as run:
        result = runner.invoke(update, ["--ref", "v0.3.0", "--dry-run"])
    assert result.exit_code == 0
    assert "git+https://github.com/dilawarabbas1/dotagent@v0.3.0" in result.output
    run.assert_not_called()


def test_pipx_install_runs_when_not_dry_run():
    runner = CliRunner()
    completed = subprocess.CompletedProcess(args=[], returncode=0)
    with patch.object(update_cmd, "_latest_main_sha", return_value="abc1234"), \
         patch.object(update_cmd, "_detect_install_method", return_value="pipx"), \
         patch.object(update_cmd, "_installed_version", side_effect=["0.3.0", "0.4.0"]), \
         patch("shutil.which", return_value="/usr/bin/pipx"), \
         patch("subprocess.run", return_value=completed) as run:
        result = runner.invoke(update, [])
    assert result.exit_code == 0
    run.assert_called_once()
    assert "0.3.0 → 0.4.0" in result.output


def test_pipx_missing_on_path_errors_out():
    runner = CliRunner()
    with patch.object(update_cmd, "_latest_main_sha", return_value=None), \
         patch.object(update_cmd, "_detect_install_method", return_value="pipx"), \
         patch.object(update_cmd, "_installed_version", return_value="0.3.0"), \
         patch("shutil.which", return_value=None), \
         patch("subprocess.run") as run:
        result = runner.invoke(update, [])
    assert result.exit_code == 1
    assert "pipx not on PATH" in result.output
    run.assert_not_called()
