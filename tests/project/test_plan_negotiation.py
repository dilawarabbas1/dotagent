"""Plan negotiation primitive tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dotagent.paths import Paths
from dotagent.project.plan_negotiation import (
    current_session_n,
    diff,
    freeze,
    is_converged,
    read_state,
    write_draft,
)


def _setup(tmp_path: Path) -> Paths:
    paths = Paths(repo=tmp_path)
    paths.project_dir.mkdir(parents=True)
    return paths


_YAML_A = "name: demo\nmodules:\n  - id: M01\n    state: planned\n"
_YAML_B = "name: demo\nmodules:\n  - id: M01\n    state: planned\n  - id: M02\n    state: planned\n"


def test_write_draft_creates_first_round(tmp_path: Path):
    paths = _setup(tmp_path)
    state = write_draft(paths, actor="planner", content=_YAML_A)
    assert state.current_round == 1
    assert state.last_actor == "planner"
    assert paths.plan_draft_path(1).exists()
    assert paths.plan_round_dir(1).joinpath("01-planner.yaml").exists()


def test_two_actors_advance_round(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    state = write_draft(paths, actor="qa", content=_YAML_B,
                        rationale="add M02", is_review=True)
    assert state.current_round == 2
    assert state.last_actor == "qa"


def test_same_actor_refines_same_round(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    state = write_draft(paths, actor="planner",
                        content=_YAML_A + "# typo fixed\n")
    assert state.current_round == 1
    assert state.last_actor == "planner"


def test_convergence_when_hashes_match(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    write_draft(paths, actor="qa", content=_YAML_B,
                rationale="r", is_review=True)
    write_draft(paths, actor="planner", content=_YAML_B)
    assert is_converged(paths)


def test_no_convergence_when_hashes_differ(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    write_draft(paths, actor="qa", content=_YAML_B,
                rationale="r", is_review=True)
    assert not is_converged(paths)


def test_review_requires_rationale(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    with pytest.raises(ValueError, match="rationale"):
        write_draft(paths, actor="qa", content=_YAML_B, is_review=True)


def test_invalid_yaml_rejected(tmp_path: Path):
    paths = _setup(tmp_path)
    with pytest.raises(ValueError, match="YAML"):
        write_draft(paths, actor="planner",
                    content="not: valid: yaml: at:: all")


def test_diff_reports_no_prior_round(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    result = diff(paths)
    assert result["status"] == "no-prior-round"


def test_diff_reports_change_between_rounds(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    write_draft(paths, actor="qa", content=_YAML_B,
                rationale="r", is_review=True)
    result = diff(paths)
    assert result["status"] == "ok"
    assert result["hash_match"] is False
    assert result["from"]["actor"] == "planner"
    assert result["to"]["actor"] == "qa"


def test_freeze_refuses_when_not_converged(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    with pytest.raises(PermissionError, match="converged"):
        freeze(paths)


def test_freeze_writes_plan_yaml_and_snapshot(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    write_draft(paths, actor="qa", content=_YAML_B,
                rationale="r", is_review=True)
    write_draft(paths, actor="planner", content=_YAML_B)
    snapshot = freeze(paths)
    assert snapshot.exists()
    assert snapshot == paths.plan_frozen
    assert paths.project_plan.exists()
    assert paths.project_plan.read_text() == _YAML_B


def test_freeze_force_requires_rationale(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    with pytest.raises(ValueError, match="rationale"):
        freeze(paths, force=True)


def test_freeze_force_succeeds_with_rationale(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    snapshot = freeze(paths, force=True, rationale="executive override")
    assert snapshot.exists()
    assert "forced: executive override" in snapshot.read_text()


def test_read_state_returns_round_history(tmp_path: Path):
    paths = _setup(tmp_path)
    write_draft(paths, actor="planner", content=_YAML_A)
    write_draft(paths, actor="qa", content=_YAML_B,
                rationale="add M02", is_review=True)
    state = read_state(paths)
    assert len(state.rounds) == 2
    assert state.rounds[0].actor == "planner"
    assert state.rounds[1].actor == "qa"
    assert state.rounds[1].rationale == "add M02"


def test_empty_session_returns_zero_round_state(tmp_path: Path):
    paths = _setup(tmp_path)
    state = read_state(paths)
    assert state.current_round == 0
    assert state.last_actor == ""
    assert state.converged is False
