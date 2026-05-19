"""`dotagent project contract validate` — schema check on contract.md.

Confirms:
- Well-formed fixture passes (returns empty violations).
- Missing required anchor fails.
- Fewer than 3 numbered criteria fails.
- FORBIDDEN tokens in the criteria section fail.
- Criterion without a verb-shape signal fails.
"""

from __future__ import annotations

from pathlib import Path

from dotagent.project.contract import (
    MAX_CRITERION_LENGTH,
    init_contract,
    validate_contract,
)

from ._helpers import make_project_with_module, setup_repo


def _initialized(tmp_path: Path) -> Path:
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    contract = init_contract(paths, module)
    return paths.repo / contract.path


# ---- happy path ------------------------------------------------------------


def test_well_formed_contract_validates(tmp_path: Path):
    path = _initialized(tmp_path)
    result = validate_contract(path)
    assert result.ok, f"expected pass; got violations={result.violations}"
    assert result.violations == []


# ---- missing anchor --------------------------------------------------------


def test_missing_anchor_fails(tmp_path: Path):
    path = _initialized(tmp_path)
    body = path.read_text()
    body = body.replace("<!-- anchor: acceptance-criteria -->", "")
    path.write_text(body)

    result = validate_contract(path)

    assert not result.ok
    assert any("acceptance-criteria" in v for v in result.violations)


# ---- not enough criteria ---------------------------------------------------


def test_fewer_than_three_criteria_fails(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(
        paths,
        criteria=["only one passes == true"],
    )
    contract = init_contract(paths, module)
    path = paths.repo / contract.path

    result = validate_contract(path)

    assert not result.ok
    assert any("at least 3" in v for v in result.violations)


# ---- forbidden tokens ------------------------------------------------------


def test_forbidden_token_in_criteria_fails(tmp_path: Path):
    path = _initialized(tmp_path)
    body = path.read_text()
    body = body.replace(
        "JWT verify matches the issuer's public key fingerprint",
        "TODO: figure out JWT verify against the public key",
    )
    path.write_text(body)

    result = validate_contract(path)

    assert not result.ok
    assert any("TODO" in v for v in result.violations)


def test_lorem_token_in_criteria_fails(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(
        paths,
        criteria=[
            "returns 200 on success",
            "passes audit when key rotated",
            "lorem ipsum dolor sit amet",
        ],
    )
    contract = init_contract(paths, module)
    path = paths.repo / contract.path

    result = validate_contract(path)

    assert not result.ok
    assert any("lorem" in v.lower() for v in result.violations)


# ---- verb-shape signals (four-signal union) --------------------------------


def test_criterion_without_any_signal_fails(tmp_path: Path):
    """No verb keyword, no comparison op, no numeric threshold, no test ref → fail."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(
        paths,
        criteria=[
            "Returns 200 on success",                # passes (verb keyword)
            "Auth flow described in design doc",     # ← no signal whatsoever
            "Equals the documented behavior",        # passes (verb keyword)
        ],
    )
    contract = init_contract(paths, module)
    path = paths.repo / contract.path

    result = validate_contract(path)

    assert not result.ok
    assert any("verb-shape" in v for v in result.violations)


def test_vague_phrasing_still_fails(tmp_path: Path):
    """'looks good' / 'should be fine' / 'is acceptable' carry zero signal."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(
        paths,
        criteria=[
            "looks good",
            "should be fine",
            "is acceptable",
        ],
    )
    contract = init_contract(paths, module)
    path = paths.repo / contract.path

    result = validate_contract(path)

    assert not result.ok
    # all three should be flagged
    verb_violations = [v for v in result.violations if "verb-shape" in v]
    assert len(verb_violations) == 3


def test_natural_phrasing_with_threshold_unit_passes(tmp_path: Path):
    """The whole reason we replaced keyword-only detection: prose that's clearly
    testable should pass without forcing magic-word salad."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(
        paths,
        criteria=[
            "latency stays below 200ms p95",                  # verb + op-like word + threshold
            "request count exceeds threshold of 100",         # verb + numeric (no unit)
            "pytest -q exits 0 within 30 seconds",            # verb + test ref + threshold
        ],
    )
    contract = init_contract(paths, module)
    path = paths.repo / contract.path

    result = validate_contract(path)

    assert result.ok, f"expected pass; got violations={result.violations}"


def test_comparison_operator_alone_qualifies(tmp_path: Path):
    """A criterion whose only signal is a comparison operator should pass."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(
        paths,
        criteria=[
            "response.status == 200",                          # bare `==`
            "result.user_id != null",                          # bare `!=`
            "memory.usage <= 512mb",                           # `<=` AND numeric threshold
        ],
    )
    contract = init_contract(paths, module)
    path = paths.repo / contract.path

    result = validate_contract(path)

    assert result.ok, f"expected pass; got violations={result.violations}"


def test_test_command_reference_alone_qualifies(tmp_path: Path):
    """`curl`, `pytest`, etc. mark a criterion as exercisable without a verb keyword."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(
        paths,
        criteria=[
            "curl /health for tenant scoping verification",    # curl
            "npm test for the auth module green run",          # npm test
            "the exit code of the bootstrap script is zero",   # exit code (also verb 'is' — but verb 'is' not in our list; exit-code rescue)
        ],
    )
    contract = init_contract(paths, module)
    path = paths.repo / contract.path

    result = validate_contract(path)

    assert result.ok, f"expected pass; got violations={result.violations}"


def test_numeric_threshold_with_unit_alone_qualifies(tmp_path: Path):
    """A naked '200ms' threshold (paired with a unit) marks a measurable target."""
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(
        paths,
        criteria=[
            "p95 200ms tenant routing budget",                 # threshold (via `200ms`)
            "uptime maintains 99.9% on the SLA dashboard",     # threshold (via `99.9%`) + 'maintains' (not in list)
            "30 seconds soft deadline on bootstrap warm-up",   # threshold (via `30 seconds`)
        ],
    )
    contract = init_contract(paths, module)
    path = paths.repo / contract.path

    result = validate_contract(path)

    assert result.ok, f"expected pass; got violations={result.violations}"


# ---- criterion too long ----------------------------------------------------


def test_criterion_over_max_length_fails(tmp_path: Path):
    long_crit = "POST /auth/login returns " + ("x" * (MAX_CRITERION_LENGTH + 1))
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(
        paths,
        criteria=[
            long_crit,
            "passes audit",
            "equals the documented behavior",
        ],
    )
    contract = init_contract(paths, module)
    path = paths.repo / contract.path

    result = validate_contract(path)

    assert not result.ok
    assert any("chars" in v or "200" in v for v in result.violations)


# ---- nonexistent file ------------------------------------------------------


def test_missing_file_fails(tmp_path: Path):
    result = validate_contract(tmp_path / "no-such-contract.md")
    assert not result.ok
    assert any("does not exist" in v for v in result.violations)
