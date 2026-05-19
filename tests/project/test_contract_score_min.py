"""`dotagent project contract score --min N` — exits 2 below threshold, 0 at/above."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from dotagent.commands.contract_cmd import contract_group
from dotagent.project.contract import init_contract
from dotagent.project.model import save_module

from ._helpers import make_project_with_module, setup_repo


def test_min_high_threshold_exits_2_on_freshly_inited_contract(tmp_path: Path, monkeypatch):
    """A freshly-inited contract scores well below 27 (it's mostly placeholders).
    --min 27 should exit 2."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    save_module(paths, module)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(contract_group, ["score", module.id, "--min", "27"])
    assert result.exit_code == 2, f"expected 2, got {result.exit_code}: {result.output}"


def test_min_zero_always_exits_0(tmp_path: Path, monkeypatch):
    """Default --min 0 means the command informational-only; exit 0 regardless."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    save_module(paths, module)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(contract_group, ["score", module.id])
    assert result.exit_code == 0
    result_explicit = runner.invoke(contract_group, ["score", module.id, "--min", "0"])
    assert result_explicit.exit_code == 0


def test_min_low_threshold_exits_0_on_freshly_inited_contract(tmp_path: Path, monkeypatch):
    """A fresh contract scores ~9-10 (mostly empty); --min 5 should still pass."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    save_module(paths, module)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(contract_group, ["score", module.id, "--min", "5"])
    assert result.exit_code == 0
