"""`dotagent project contract diff` — convergence detection."""

from __future__ import annotations

from pathlib import Path

from dotagent.project.contract import (
    ACTOR_DEV,
    ACTOR_QA,
    advance_round,
    diff_contract,
    init_contract,
)

from ._helpers import make_project_with_module, setup_repo


def test_round_one_is_not_converged_reports_first_round(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)

    result = diff_contract(paths, module)

    assert result.converged is False
    assert result.reason == "first-round"
    assert result.round == 1
    assert result.hash.startswith("sha256:")


def _edit_body(path: Path, marker: str) -> None:
    """Insert content into the substantive body (above the negotiation-log anchor)
    so the content hash actually changes. Appending to EOF would land inside the
    log section and not move the content hash — that's by design."""
    body = path.read_text()
    anchor = "<!-- anchor: negotiation-log -->"
    idx = body.find(anchor)
    assert idx > 0, "expected negotiation-log anchor in contract body"
    new = body[:idx] + f"\n<!-- {marker} -->\n" + body[idx:]
    path.write_text(new)


def test_after_codex_writes_and_claude_resaves_unchanged_reports_converged(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    cp = paths.repo / module.current_cycle.contract.path

    # Codex writes a counter (modifies the substantive body).
    _edit_body(cp, "codex substantive counter")
    advance_round(paths, module, actor_side=ACTOR_QA)

    # Claude re-saves WITHOUT modifying the body → convergence.
    advance_round(paths, module, actor_side=ACTOR_DEV)

    result = diff_contract(paths, module)

    assert result.converged is True
    assert result.reason == "hashes-match"
    # init=round 1 (claude), codex switch → round 2, claude switch → round 3.
    assert result.round == 3


def test_when_hashes_differ_reports_not_converged(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    cp = paths.repo / module.current_cycle.contract.path

    _edit_body(cp, "codex first counter")
    advance_round(paths, module, actor_side=ACTOR_QA)

    # Claude makes further substantive edits — not a no-change re-save.
    _edit_body(cp, "claude refinement after codex")
    advance_round(paths, module, actor_side=ACTOR_DEV)

    result = diff_contract(paths, module)

    assert result.converged is False
    assert result.reason == "hashes-differ"


def test_diff_returns_json_serializable_payload(tmp_path: Path):
    import json

    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)

    payload = diff_contract(paths, module).to_dict()

    # Must round-trip through json.dumps without TypeError.
    blob = json.dumps(payload)
    loaded = json.loads(blob)
    assert set(loaded.keys()) == {"path", "round", "hash", "converged", "reason"}


def test_diff_on_module_without_contract_returns_no_contract(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    # never call init_contract

    result = diff_contract(paths, module)

    assert result.converged is False
    assert result.reason == "no-contract"
    assert result.hash == ""


def test_diff_when_file_missing_reports_so(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    (paths.repo / module.current_cycle.contract.path).unlink()

    result = diff_contract(paths, module)

    assert result.converged is False
    assert result.reason == "contract-file-missing"
