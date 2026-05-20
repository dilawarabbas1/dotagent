"""Traceability audit tests: OBJ → FEAT → Module → Contract."""

from __future__ import annotations

from dotagent.project.brief import Brief, Feature, Objective
from dotagent.project.model import Module, ModuleState, Project
from dotagent.project.traceability import (
    ContractRef,
    audit_brief_version_drift,
    audit_feat_to_module,
    audit_module_to_contract,
    audit_obj_to_feat,
)


def _brief_with(objectives, features) -> Brief:
    b = Brief()
    b.objectives = [Objective(id=oid, text=f"obj {oid}") for oid in objectives]
    b.features = features
    return b


def test_obj_to_feat_clean():
    brief = _brief_with(
        ["OBJ-01", "OBJ-02"],
        [Feature(id="FEAT-01", name="a", serves=["OBJ-01"]),
         Feature(id="FEAT-02", name="b", serves=["OBJ-02"])],
    )
    findings = audit_obj_to_feat(brief)
    assert findings == []


def test_obj_to_feat_flags_orphan():
    brief = _brief_with(
        ["OBJ-01", "OBJ-99"],   # OBJ-99 is orphan
        [Feature(id="FEAT-01", name="a", serves=["OBJ-01"])],
    )
    findings = audit_obj_to_feat(brief)
    assert len(findings) == 1
    assert "OBJ-99" in findings[0].message


def test_feat_to_module_clean():
    brief = _brief_with(
        ["OBJ-01"],
        [Feature(id="FEAT-01", name="auth", serves=["OBJ-01"])],
    )
    proj = Project(name="demo", brief_features_covered=["FEAT-01"])
    modules = [Module(id="M01", name="auth", implements_features=["FEAT-01"])]
    findings = audit_feat_to_module(brief, proj, modules)
    assert findings == []


def test_feat_to_module_flags_uncovered_feat():
    brief = _brief_with(
        ["OBJ-01"],
        [Feature(id="FEAT-01", name="auth", serves=["OBJ-01"]),
         Feature(id="FEAT-02", name="billing", serves=["OBJ-01"])],
    )
    proj = Project(name="demo", brief_features_covered=["FEAT-01", "FEAT-02"])
    modules = [Module(id="M01", name="auth", implements_features=["FEAT-01"])]
    findings = audit_feat_to_module(brief, proj, modules)
    assert len(findings) == 1
    assert "FEAT-02" in findings[0].message


def test_feat_to_module_skips_features_not_in_plan():
    """If plan.brief_features_covered explicitly lists FEAT-01, FEAT-02 is
    out of scope and shouldn't be flagged as uncovered."""
    brief = _brief_with(
        ["OBJ-01"],
        [Feature(id="FEAT-01", name="auth", serves=["OBJ-01"]),
         Feature(id="FEAT-02", name="billing", serves=["OBJ-01"])],
    )
    proj = Project(name="demo", brief_features_covered=["FEAT-01"])
    modules = [Module(id="M01", name="auth", implements_features=["FEAT-01"])]
    findings = audit_feat_to_module(brief, proj, modules)
    assert findings == []


def test_contract_without_feat_ref_is_fail():
    modules = [Module(id="M01", name="auth", implements_features=["FEAT-01"])]
    contracts = [ContractRef(
        module_id="M01", cycle_n=1,
        body=(
            "## Some other section\nstuff\n"
            "<!-- anchor: business-traceability -->\n"
            "(empty)\n"
            "<!-- anchor: negotiation-log -->\n"
        ),
    )]
    findings = audit_module_to_contract(modules, contracts)
    assert len(findings) == 1
    assert findings[0].severity == "fail"
    assert "no FEAT-NN" in findings[0].message


def test_contract_with_feat_ref_passes():
    modules = [Module(id="M01", name="auth", implements_features=["FEAT-01"])]
    contracts = [ContractRef(
        module_id="M01", cycle_n=1,
        body=(
            "<!-- anchor: business-traceability -->\n"
            "**Feature(s):** FEAT-01\n**Objective(s):** OBJ-01\n"
            "- behavior X\n"
            "<!-- anchor: negotiation-log -->\n"
        ),
    )]
    findings = audit_module_to_contract(modules, contracts)
    assert findings == []


def test_contract_feat_mismatch_warns():
    modules = [Module(id="M01", name="auth", implements_features=["FEAT-01", "FEAT-02"])]
    contracts = [ContractRef(
        module_id="M01", cycle_n=1,
        body=(
            "<!-- anchor: business-traceability -->\n"
            "**Feature(s):** FEAT-01\n**Objective(s):** OBJ-01\n"
            "<!-- anchor: negotiation-log -->\n"
        ),
    )]
    findings = audit_module_to_contract(modules, contracts)
    # FEAT-02 was declared by module but not cited in contract
    assert len(findings) == 1
    assert findings[0].severity == "warn"


def test_brief_version_drift_warning():
    brief = Brief(brief_version=3)
    proj = Project(name="demo", brief_version=2)
    findings = audit_brief_version_drift(brief, proj)
    assert len(findings) == 1
    assert "drift" in findings[0].code


def test_brief_version_no_drift_when_matched():
    brief = Brief(brief_version=2)
    proj = Project(name="demo", brief_version=2)
    findings = audit_brief_version_drift(brief, proj)
    assert findings == []


def test_contract_ref_extracts_feat_and_obj_from_section():
    cr = ContractRef(
        module_id="M01", cycle_n=1,
        body=(
            "## Acceptance criteria\n- a\n"
            "<!-- anchor: business-traceability -->\n"
            "**Feature(s):** FEAT-02, FEAT-03\n"
            "**Objective(s):** OBJ-01, OBJ-02\n"
            "<!-- anchor: negotiation-log -->\n"
        ),
    )
    assert set(cr.feat_refs) == {"FEAT-02", "FEAT-03"}
    assert set(cr.obj_refs) == {"OBJ-01", "OBJ-02"}


def test_contract_ref_ignores_refs_outside_section():
    """Refs in other sections (e.g. acceptance criteria) shouldn't count
    toward business-traceability — only refs inside the anchor."""
    cr = ContractRef(
        module_id="M01", cycle_n=1,
        body=(
            "## Acceptance criteria\n- mentions FEAT-99\n"
            "<!-- anchor: business-traceability -->\n"
            "(empty)\n"
            "<!-- anchor: negotiation-log -->\n"
        ),
    )
    assert cr.feat_refs == []
