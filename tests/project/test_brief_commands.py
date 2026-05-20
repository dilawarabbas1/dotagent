"""End-to-end CLI tests for dotagent project brief."""

from __future__ import annotations

import json
import os
from pathlib import Path

from click.testing import CliRunner

from dotagent.cli import main


def _invoke(runner: CliRunner, args: list[str], cwd: Path):
    """Helper: run `dotagent <args>` with cwd set."""
    orig = os.getcwd()
    os.chdir(cwd)
    try:
        return runner.invoke(main, args, catch_exceptions=False)
    finally:
        os.chdir(orig)


def _scaffold_repo(tmp_path: Path) -> Path:
    """Minimal v0.4 layout: .agent/ with .version + memory dirs."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".agent").mkdir()
    (tmp_path / ".agent" / ".version").write_text("0.4.0\n")
    (tmp_path / ".agent" / "config.yaml").write_text("name: demo\n")
    (tmp_path / ".agent" / "architecture.md").write_text("# arch\n")
    (tmp_path / ".agent" / "rules.md").write_text("# rules\n")
    for sub in ("working", "episodic", "semantic", "personal"):
        (tmp_path / ".agent" / "memory" / sub).mkdir(parents=True)
    return tmp_path


def test_brief_init_writes_stub(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo(tmp_path)

    result = _invoke(
        runner,
        ["project", "brief", "init", "--non-interactive",
         "--name", "aigent", "--owner", "me@x.com", "--vision", "test"],
        repo,
    )
    assert result.exit_code == 0, result.output

    brief = repo / ".agent" / "project_brief.md"
    assert brief.exists()
    body = brief.read_text()
    assert "Project brief: aigent" in body
    assert "me@x.com" in body
    assert "test" in body


def test_brief_init_refuses_overwrite_without_force(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo(tmp_path)
    (repo / ".agent" / "project_brief.md").write_text("existing\n")

    result = _invoke(runner, ["project", "brief", "init", "--non-interactive"], repo)
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_brief_show_json(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo(tmp_path)
    (repo / ".agent" / "project_brief.md").write_text(
        "# Project brief: demo\n"
        "**Last reviewed:** 2026-01-01  ·  **Brief version:** 2  ·  **Owner:** x  ·  **Stage:** beta\n\n"
        "## Vision (one sentence)\nThe vision.\n\n"
        "## Business objectives\n- **OBJ-01**: foo\n\n"
        "## Features\n### FEAT-01 · Auth\n**Serves:** OBJ-01\n"
        "**Expected outcome:** y\n**What it must do:**\n- do x\n"
    )

    result = _invoke(runner, ["project", "brief", "show", "--format", "json"], repo)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["name"] == "demo"
    assert payload["brief_version"] == 2
    assert len(payload["objectives"]) == 1
    assert len(payload["features"]) == 1


def test_brief_show_when_missing(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo(tmp_path)

    result = _invoke(runner, ["project", "brief", "show"], repo)
    assert result.exit_code == 1


def test_brief_check_reports_missing_brief(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo(tmp_path)

    result = _invoke(runner, ["project", "brief", "check"], repo)
    assert result.exit_code == 1
    assert "no brief" in result.output


def test_brief_check_clean_after_init(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo(tmp_path)
    (repo / ".agent" / "project_brief.md").write_text(
        "# Project brief: demo\n"
        "**Last reviewed:** 2026-05-01  ·  **Brief version:** 1  ·  **Owner:** x  ·  **Stage:** beta\n\n"
        "## Vision (one sentence)\nThe vision.\n\n"
        "## Business objectives\n- **OBJ-01**: foo\n\n"
        "## Features\n### FEAT-01 · Auth\n**Serves:** OBJ-01\n"
        "**Expected outcome:** y\n**What it must do:**\n- do x\n\n"
        "## Hard rules\n- **RULE-01 · Iso** — _why: BUG-1; how: filter_\n"
    )

    result = _invoke(runner, ["project", "brief", "check"], repo)
    assert result.exit_code == 0, result.output
    assert "clean" in result.output


def test_brief_check_detects_dangling_obj_reference(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo(tmp_path)
    (repo / ".agent" / "project_brief.md").write_text(
        "# Project brief: demo\n"
        "**Last reviewed:** 2026-01-01  ·  **Brief version:** 1  ·  **Owner:** x  ·  **Stage:** beta\n\n"
        "## Vision (one sentence)\nv\n\n"
        "## Business objectives\n- **OBJ-01**: foo\n\n"
        "## Features\n### FEAT-01 · Auth\n**Serves:** OBJ-99\n"
        "**Expected outcome:** y\n**What it must do:**\n- do x\n\n"
        "## Hard rules\n- **RULE-01 · X** — _why: y; how: z_\n"
    )

    result = _invoke(runner, ["project", "brief", "check"], repo)
    assert result.exit_code == 1
    assert "OBJ-99" in result.output
    assert "FEAT-01" in result.output


def test_brief_check_detects_duplicate_id(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo(tmp_path)
    (repo / ".agent" / "project_brief.md").write_text(
        "# Project brief: demo\n"
        "**Last reviewed:** 2026-01-01  ·  **Brief version:** 1  ·  **Owner:** x  ·  **Stage:** beta\n\n"
        "## Vision (one sentence)\nv\n\n"
        "## Business objectives\n- **OBJ-01**: foo\n- **OBJ-01**: dup\n\n"
        "## Features\n### FEAT-01 · Auth\n**Serves:** OBJ-01\n"
        "**Expected outcome:** y\n**What it must do:**\n- do x\n\n"
        "## Hard rules\n- **RULE-01 · X** — _why: y; how: z_\n"
    )

    result = _invoke(runner, ["project", "brief", "check"], repo)
    assert result.exit_code == 1
    assert "duplicate id" in result.output
    assert "OBJ-01" in result.output


def test_brief_check_json_shape(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo(tmp_path)
    (repo / ".agent" / "project_brief.md").write_text(
        "# Project brief: demo\n"
        "**Last reviewed:** 2026-05-01  ·  **Brief version:** 1  ·  **Owner:** x  ·  **Stage:** beta\n\n"
        "## Vision (one sentence)\nv\n\n"
        "## Business objectives\n- **OBJ-01**: foo\n\n"
        "## Features\n### FEAT-01 · Auth\n**Serves:** OBJ-01\n"
        "**Expected outcome:** y\n**What it must do:**\n- do x\n\n"
        "## Hard rules\n- **RULE-01 · X** — _why: y; how: z_\n"
    )

    result = _invoke(runner, ["project", "brief", "check", "--format", "json"], repo)
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["findings"] == []


def test_brief_upload_replaces_file(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo(tmp_path)
    upload_src = tmp_path / "external_brief.md"
    upload_src.write_text(
        "# Project brief: uploaded\n"
        "**Last reviewed:** 2026-01-01  ·  **Brief version:** 5  ·  **Owner:** x  ·  **Stage:** beta\n\n"
        "## Business objectives\n- **OBJ-07**: seven\n"
    )

    result = _invoke(
        runner, ["project", "brief", "upload", str(upload_src), "--force"], repo,
    )
    assert result.exit_code == 0, result.output

    body = (repo / ".agent" / "project_brief.md").read_text()
    assert "uploaded" in body
    assert "OBJ-07" in body


def test_brief_upload_rejects_pdf(tmp_path: Path):
    runner = CliRunner()
    repo = _scaffold_repo(tmp_path)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    result = _invoke(runner, ["project", "brief", "upload", str(pdf), "--force"], repo)
    assert result.exit_code == 1
    assert "PDF" in result.output or "deferred" in result.output
