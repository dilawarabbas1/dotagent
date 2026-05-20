"""Regression tests for the 4 bugs introduced by #32 (0.4.5 regenerate).

Each test pins one user-reported failure mode from the audit follow-up
so they don't recur on future regenerate runs.
"""

from __future__ import annotations

from pathlib import Path

from dotagent.config import merge_defaults
from dotagent.paths import Paths
from dotagent.project.brief import (
    regenerate_brief_modules,
    render_modules_table,
    replace_modules_section,
    write_stub,
)
from dotagent.project.handoff import render_scope
from dotagent.project.brief import parse as parse_brief, Brief, Feature, Objective
from dotagent.project.model import Module, Project, save_project
from dotagent.scaffold import scaffold_agent_dir
from dotagent.util import dump_yaml


# ---------------------------------------------------------------------------
# Bug 1: duplicate "Modules & delivery status" section
# ---------------------------------------------------------------------------

def test_replace_modules_replaces_hand_written_section_without_anchors():
    """A hand-written `## Modules & delivery status` block (no anchors)
    must be REPLACED, not appended below with a fresh anchored block."""
    src = (
        "# Project brief: demo\n\n"
        "## Vision\n"
        "do the thing\n\n"
        "## Modules & delivery status\n\n"
        "Hand-written note: intentionally not duplicated in this brief.\n\n"
        "## Glossary\n"
        "- **term** — def\n"
    )
    new = "## Modules & delivery status\n\nNew generated content.\n"
    out = replace_modules_section(src, new)
    # The hand-written line must be gone
    assert "intentionally not duplicated" not in out
    # The new generated content is present
    assert "New generated content" in out
    # Only ONE Modules & delivery status heading remains
    assert out.count("## Modules & delivery status") == 1
    # Anchors were added wrapping the new section
    assert out.count("<!-- anchor: modules-table-begin -->") == 1
    assert out.count("<!-- anchor: modules-table-end -->") == 1
    # Content after the section is preserved
    assert "## Glossary" in out
    assert "**term** — def" in out


def test_replace_modules_replaces_between_anchors_when_present():
    """When anchors are already there, the in-between content is replaced."""
    src = (
        "before\n"
        "<!-- anchor: modules-table-begin -->\n"
        "OLD content\n"
        "<!-- anchor: modules-table-end -->\n"
        "after\n"
    )
    out = replace_modules_section(src, "## Modules & delivery status\n\nNEW content\n")
    assert "OLD content" not in out
    assert "NEW content" in out
    assert "before" in out
    assert "after" in out


def test_replace_modules_no_prior_section_appends_at_end():
    """Backward compat: no anchors AND no heading → append."""
    src = "# brief\n\n## Vision\nx\n"
    out = replace_modules_section(src, "## Modules & delivery status\n\nNEW\n")
    assert "<!-- anchor: modules-table-begin -->" in out
    assert "NEW" in out


def test_regenerate_idempotent_on_repeated_calls(tmp_path: Path):
    """Running regenerate_brief_modules() twice doesn't duplicate."""
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "demo"}}))
    write_stub(paths.project_brief, name="demo")
    # Inject a hand-written modules section to simulate the user's
    # actual state
    brief_text = paths.project_brief.read_text()
    paths.project_brief.write_text(
        brief_text.replace(
            "## Hard rules",
            "## Modules & delivery status\n\nhand-written note\n\n## Hard rules",
            1,
        )
    )
    # Now set up a project with one module
    project = Project(name="demo")
    project.modules["M01"] = Module(id="M01", name="auth", state="planned")
    project.module_ids = ["M01"]
    save_project(paths, project)

    # First regen
    regenerate_brief_modules(paths)
    body_first = paths.project_brief.read_text()
    # Second regen
    regenerate_brief_modules(paths)
    body_second = paths.project_brief.read_text()

    # Only ONE modules section heading regardless of how many regens
    assert body_first.count("## Modules & delivery status") == 1
    assert body_second.count("## Modules & delivery status") == 1
    assert "hand-written note" not in body_second
    assert "M01" in body_second


# ---------------------------------------------------------------------------
# Bug 2: Implements column empty when mapping in plan.yaml only
# ---------------------------------------------------------------------------

def test_render_modules_table_reads_features_to_modules():
    """When module.implements_features is empty but
    plan.yaml::features_to_modules has the mapping, the table populates
    the Implements column from the latter."""
    project = Project(name="demo")
    project.features_to_modules = {
        "FEAT-01": ["M01"],
        "FEAT-02": ["M01", "M02"],
    }
    project.modules["M01"] = Module(id="M01", name="auth", state="planned")
    project.modules["M02"] = Module(id="M02", name="billing", state="in_progress")
    project.module_ids = ["M01", "M02"]

    table = render_modules_table(project)
    # M01 implements FEAT-01 AND FEAT-02 (from features_to_modules)
    assert "FEAT-01" in table
    assert "FEAT-02" in table
    # Neither implements column reads "—" for both
    for line in table.splitlines():
        if line.startswith("| **M01**"):
            assert "—" not in line.split("|")[2], f"M01 row: {line}"


def test_render_modules_table_unions_both_sources():
    """A module with implements_features in module.yaml + extra FEAT
    declared in plan.yaml gets both."""
    project = Project(name="demo")
    project.features_to_modules = {"FEAT-B": ["M01"]}
    project.modules["M01"] = Module(
        id="M01", name="auth", state="planned",
        implements_features=["FEAT-A"],
    )
    project.module_ids = ["M01"]

    table = render_modules_table(project)
    assert "FEAT-A" in table
    assert "FEAT-B" in table


def test_render_modules_table_owner_from_inline():
    """Owner is pulled from module.tools['_inline'] (PR #29's preservation
    stash) when present."""
    project = Project(name="demo")
    project.modules["M01"] = Module(
        id="M01", name="auth", state="planned",
        tools={"_inline": {"owner": "alice"}},
    )
    project.module_ids = ["M01"]

    table = render_modules_table(project)
    assert "alice" in table


# ---------------------------------------------------------------------------
# Bug 3: SCOPE.md Goal == Description (both vision)
# ---------------------------------------------------------------------------

def test_render_scope_distinguishes_goal_from_description():
    """Goal falls back to brief.vision; Description falls back to OBJ list
    (or features), NOT the same vision text."""
    project = Project(name="")
    brief = Brief(
        name="Aigent",
        vision="Build the workspace solo founders actually use.",
        objectives=[
            Objective(id="OBJ-01", text="100 paying customers in 90 days"),
            Objective(id="OBJ-02", text="<5min activation"),
        ],
    )
    scope = render_scope(project, brief=brief)

    # Goal == vision
    assert "Build the workspace solo founders actually use." in scope

    # Description does NOT equal goal — it's the OBJ list instead
    # Find the Description section
    desc_start = scope.find("## Description")
    next_section = scope.find("## ", desc_start + 1)
    description_body = scope[desc_start:next_section]

    assert "OBJ-01: 100 paying customers" in description_body
    # And specifically NOT the vision sentence duplicated
    vision_count = description_body.count("Build the workspace")
    assert vision_count == 0, (
        f"Description should not duplicate vision; found {vision_count} occurrence(s)"
    )


def test_render_scope_uses_features_when_no_objectives():
    """If brief has no OBJs but does have features, description falls
    back to feature list."""
    project = Project(name="")
    brief = Brief(
        name="x",
        vision="vision",
        features=[
            Feature(id="FEAT-01", name="auth", expected_outcome="users log in"),
        ],
    )
    scope = render_scope(project, brief=brief)
    desc_start = scope.find("## Description")
    next_section = scope.find("## ", desc_start + 1)
    description_body = scope[desc_start:next_section]
    assert "FEAT-01" in description_body
    assert "users log in" in description_body


def test_render_scope_uses_placeholder_when_brief_has_nothing():
    """Empty project + empty brief → explicit unset marker, not crash."""
    project = Project(name="")
    brief = Brief(name="", vision="", objectives=[], features=[])
    scope = render_scope(project, brief=brief)
    assert "(unset" in scope


def test_render_scope_explicit_description_wins():
    """If plan.yaml has an explicit description, it wins over fallback."""
    project = Project(name="x", description="explicit description")
    brief = Brief(
        name="x", vision="v",
        objectives=[Objective(id="OBJ-01", text="o")],
    )
    scope = render_scope(project, brief=brief)
    assert "explicit description" in scope
    desc_start = scope.find("## Description")
    next_section = scope.find("## ", desc_start + 1)
    description_body = scope[desc_start:next_section]
    assert "OBJ-01" not in description_body  # didn't fall back


# ---------------------------------------------------------------------------
# Bug 4: project status name still empty
# ---------------------------------------------------------------------------

def test_project_status_falls_back_to_brief_name(tmp_path: Path):
    """`dotagent project status` should pull brief.name when plan.yaml's
    name is empty."""
    import os
    from click.testing import CliRunner
    from dotagent.cli import main

    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "Aigent"}}))
    (tmp_path / ".agent" / ".version").write_text("0.4.0\n")
    # plan.yaml WITHOUT name
    dump_yaml(paths.project_plan, {
        "modules": {"M01": {"state": "planned"}},
    })
    # brief WITH name
    (tmp_path / ".agent" / "project_brief.md").write_text(
        "# Project brief: Aigent\n\n"
        "**Brief version:** 1\n\n"
        "## Vision (one sentence)\nx\n"
    )

    runner = CliRunner()
    orig = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(main, ["project", "status"], catch_exceptions=False)
    finally:
        os.chdir(orig)

    assert result.exit_code == 0, result.output
    assert "project:  Aigent" in result.output
