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


# ---- no verb-shape signal --------------------------------------------------


def test_criterion_without_verb_shape_fails(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(
        paths,
        criteria=[
            "Returns 200 on success",
            "Auth flow described in design doc",   # ← no verb-shape token
            "Equals the documented behavior",
        ],
    )
    contract = init_contract(paths, module)
    path = paths.repo / contract.path

    result = validate_contract(path)

    assert not result.ok
    assert any("verb-shape" in v for v in result.violations)


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
