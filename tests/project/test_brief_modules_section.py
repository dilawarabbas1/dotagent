"""Tests for the auto-generated Modules table in project_brief.md."""

from __future__ import annotations

from pathlib import Path

from dotagent.paths import Paths
from dotagent.project.brief import (
    regenerate_brief_modules,
    render_modules_table,
    replace_modules_section,
    render_stub,
    write_stub,
)
from dotagent.project.contract import init_contract

from ._helpers import make_project_with_module, setup_repo


def test_render_table_empty_modules():
    class FakeProject:
        modules = {}
        name = "demo"
    text = render_modules_table(FakeProject())
    assert "## Modules & delivery status" in text
    assert "No modules" in text


def test_replace_modules_section_preserves_anchors():
    src = (
        "# brief\n"
        "<!-- anchor: modules-table-begin -->\n"
        "old content\n"
        "<!-- anchor: modules-table-end -->\n"
        "trailing\n"
    )
    out = replace_modules_section(src, "## New table\n\n| a | b |\n")
    assert "<!-- anchor: modules-table-begin -->" in out
    assert "<!-- anchor: modules-table-end -->" in out
    assert "old content" not in out
    assert "## New table" in out
    assert "trailing" in out


def test_replace_modules_section_appends_when_no_anchors():
    src = "# brief without anchors\n"
    out = replace_modules_section(src, "## modules\nstuff\n")
    assert "<!-- anchor: modules-table-begin -->" in out
    assert "<!-- anchor: modules-table-end -->" in out
    assert "## modules" in out


def test_regenerate_no_brief_returns_false(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    paths.agent.mkdir()
    assert regenerate_brief_modules(paths) is False


def test_regenerate_updates_modules_table_in_brief(tmp_path: Path):
    paths = setup_repo(tmp_path)
    project, module = make_project_with_module(paths)
    # Write a stub brief at the expected path
    write_stub(paths.project_brief, name="demo", owner="me", vision="ship")
    assert paths.project_brief.exists()

    assert regenerate_brief_modules(paths) is True

    body = paths.project_brief.read_text()
    assert module.id in body
    assert "## Modules & delivery status" in body


def test_regenerate_called_on_init_contract(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    write_stub(paths.project_brief, name="demo", owner="me", vision="ship")
    # Stub initial text doesn't yet contain a real modules row
    body_before = paths.project_brief.read_text()
    assert module.id not in body_before

    init_contract(paths, module)

    body_after = paths.project_brief.read_text()
    assert module.id in body_after


def test_hand_written_content_outside_anchors_preserved(tmp_path: Path):
    paths = setup_repo(tmp_path)
    project, module = make_project_with_module(paths)

    # Inject a brief that has unique hand-written content above + below the anchors
    paths.project_brief.parent.mkdir(parents=True, exist_ok=True)
    paths.project_brief.write_text(
        "# Project brief: demo\n"
        "## Hand-written above\nPRESERVE-ME-ABOVE\n\n"
        "<!-- anchor: modules-table-begin -->\n"
        "(generated content)\n"
        "<!-- anchor: modules-table-end -->\n"
        "\n## Hand-written below\nPRESERVE-ME-BELOW\n"
    )

    regenerate_brief_modules(paths)
    body = paths.project_brief.read_text()
    assert "PRESERVE-ME-ABOVE" in body
    assert "PRESERVE-ME-BELOW" in body
    assert module.id in body
