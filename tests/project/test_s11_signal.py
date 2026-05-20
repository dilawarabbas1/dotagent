"""Tests for S11 rubric signal — business-traceability."""

from __future__ import annotations

from dotagent.project._signals import s11_business_traceability


def _wrap(business_section: str) -> str:
    return (
        "## Some scope\n- a\n"
        f"<!-- anchor: business-traceability -->\n{business_section}\n"
        "<!-- anchor: negotiation-log -->\n"
    )


def test_s11_zero_when_no_feat_cited():
    body = _wrap("(empty)\n")
    s = s11_business_traceability(body)
    assert s.score == 0
    assert "no FEAT-NN" in s.evidence


def test_s11_zero_when_section_missing():
    s = s11_business_traceability("## Other\n- a\n")
    assert s.score == 0


def test_s11_one_when_feat_but_no_obj():
    body = _wrap("**Feature(s):** FEAT-01\n")
    s = s11_business_traceability(body)
    assert s.score == 1


def test_s11_two_when_feat_and_obj_no_bullets():
    body = _wrap("**Feature(s):** FEAT-01\n**Objective(s):** OBJ-01\n")
    s = s11_business_traceability(body)
    assert s.score == 2


def test_s11_three_when_full():
    body = _wrap(
        "**Feature(s):** FEAT-01\n"
        "**Objective(s):** OBJ-01, OBJ-02\n"
        "Behavior bullets:\n"
        "- recovery via email completes within 5min\n"
        "- old sessions are invalidated on password change\n"
    )
    s = s11_business_traceability(body)
    assert s.score == 3
    assert "1 FEAT" in s.evidence or "FEAT" in s.evidence


def test_s11_ignores_template_placeholder():
    body = _wrap(
        "**Feature(s):** _(populate with FEAT-NN ids from project_brief.md)_\n"
    )
    s = s11_business_traceability(body)
    # Placeholder text shouldn't count as a real FEAT citation
    assert s.score == 0


def test_score_contract_now_returns_eleven_signals():
    """Sanity check that score_contract() includes S11 in its signal list."""
    from dotagent.project.contract_rubric import score_contract
    result = score_contract("## scope\n- a\n")
    assert len(result.signals) == 11
    assert any(s.id == "S11" for s in result.signals)
    assert result.max == 33


def test_band_thresholds_updated():
    """New band cutoffs: 30/24/18 over /33."""
    from dotagent.project.contract_rubric import band_for, BAND_READY, BAND_POLISH, BAND_REWORK, BAND_NOT_READY
    assert band_for(33) == BAND_READY
    assert band_for(30) == BAND_READY
    assert band_for(29) == BAND_POLISH
    assert band_for(24) == BAND_POLISH
    assert band_for(23) == BAND_REWORK
    assert band_for(18) == BAND_REWORK
    assert band_for(17) == BAND_NOT_READY
    assert band_for(0) == BAND_NOT_READY
