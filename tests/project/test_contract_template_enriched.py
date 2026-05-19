"""The contract template carries per-section discipline blockquotes + the
new Rollback plan anchored section."""

from __future__ import annotations

from pathlib import Path

from dotagent.project.contract import SECTION_ANCHORS, init_contract

from ._helpers import make_project_with_module, setup_repo


def test_rollback_plan_anchor_present_in_required_set():
    """Module 4 of this PR: Rollback plan is now a required schema anchor."""
    assert "rollback-plan" in SECTION_ANCHORS


def test_rendered_contract_carries_rollback_anchor_and_section_heading(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    contract = init_contract(paths, module)
    body = (paths.repo / contract.path).read_text()
    assert "<!-- anchor: rollback-plan -->" in body
    assert "## Rollback plan" in body


def test_rendered_contract_carries_enriched_blockquotes(tmp_path: Path):
    """Each section's discipline rules are visible in the file the agents edit."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    contract = init_contract(paths, module)
    body = (paths.repo / contract.path).read_text()

    # Scope mentions S1 + S2 score map and forbids implementation tokens.
    assert "Scored as S1 + S2" in body
    assert "NO file paths" in body

    # Acceptance criteria mentions S3+S4+S5+S6.
    assert "S3 + S4 + S5 + S6" in body
    assert "One assertion per line" in body

    # Must-not-regress requires IDs + guard test names.
    assert "DA-BUG-####" in body
    assert "AP-###" in body
    assert "guard test filename" in body

    # Doc surfaces forbids NNN placeholders, requires §Section.
    assert "§Section" in body or "§Architecture" in body
    assert "no `NNN`" in body or "no NNN" in body

    # Out of scope wants phase tags.
    assert "[Phase N]" in body
    assert "phase-tagged" in body

    # Rollback plan section's discipline.
    assert "additive change only" in body

    # Negotiation log forbids manual edits below the anchor.
    assert "Maintained by dotagent" in body or "must not edit" in body


def test_rendered_contract_references_score_command_at_the_top(tmp_path: Path):
    """The header blockquote tells agents how to grade themselves."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    contract = init_contract(paths, module)
    body = (paths.repo / contract.path).read_text()
    assert "dotagent project\n> contract score" in body or "contract score" in body
    assert "27" in body  # the suggested threshold
