"""`dotagent project contract score --json` — output schema validates."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from dotagent.commands.contract_cmd import contract_group
from dotagent.project.contract import init_contract
from dotagent.project.model import save_module

from ._helpers import make_project_with_module, setup_repo


def test_json_output_round_trips_and_has_expected_keys(tmp_path: Path, monkeypatch):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    save_module(paths, module)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(contract_group, ["score", module.id, "--json"])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    assert set(payload.keys()) == {"total", "max", "band", "signals"}
    assert isinstance(payload["total"], int)
    assert payload["max"] == 33
    assert payload["band"] in {"ready", "polish", "rework", "not_ready"}
    assert isinstance(payload["signals"], list)
    assert len(payload["signals"]) == 11
    for s in payload["signals"]:
        assert set(s.keys()) == {"id", "name", "score", "max", "evidence", "fix"}
        assert s["id"].startswith("S")
        assert 0 <= s["score"] <= s["max"]
        assert s["max"] == 3


def test_default_output_is_human_summary_not_json(tmp_path: Path, monkeypatch):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    save_module(paths, module)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(contract_group, ["score", module.id])
    assert result.exit_code == 0, result.output
    # not JSON
    assert not result.output.lstrip().startswith("{")
    assert "Contract:" in result.output
    assert "/33" in result.output


def test_report_output_is_markdown_table(tmp_path: Path, monkeypatch):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    save_module(paths, module)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(contract_group, ["score", module.id, "--report", "--no-color"])
    assert result.exit_code == 0, result.output
    assert "# Contract score" in result.output
    assert "| Signal | Score | Evidence | Fix |" in result.output
    for sid in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11"):
        assert sid in result.output
