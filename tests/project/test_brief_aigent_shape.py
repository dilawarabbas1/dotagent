"""Regression tests for the brief parser, post-Aigent feedback.

User reported (0.4.3): a brief that writes `**OBJ-01 · Universal AI chat
layer**: <description>` and `### FEAT-01 · Multi-LLM…` parsed zero IDs
because the parser required the bold span to contain ONLY the ID.

These tests pin the relaxed parser so the regression doesn't recur.
"""

from __future__ import annotations

from dotagent.project.brief import parse


def test_obj_with_title_inside_bold_parses():
    """`**OBJ-01 · Universal AI chat layer**: description` — the format
    the user actually wrote — must parse the ID + retain the title."""
    text = (
        "# Project brief: Aigent\n\n"
        "## Business objectives\n"
        "- **OBJ-01 · Universal AI chat layer**: 100 paying customers in 90 days\n"
        "- **OBJ-02 · Cross-tenant isolation**: zero security incidents\n"
    )
    brief = parse(text)
    assert len(brief.objectives) == 2
    assert brief.objectives[0].id == "OBJ-01"
    assert brief.objectives[1].id == "OBJ-02"
    # Title from the bold span is preserved in the text
    assert "Universal AI chat layer" in brief.objectives[0].text
    assert "100 paying customers" in brief.objectives[0].text


def test_obj_plain_format_still_works():
    """Backward compat: the old shape `**OBJ-01**: description`."""
    text = (
        "# Project brief: demo\n\n"
        "## Business objectives\n"
        "- **OBJ-01**: 100 paying customers\n"
    )
    brief = parse(text)
    assert len(brief.objectives) == 1
    assert brief.objectives[0].id == "OBJ-01"
    assert brief.objectives[0].text == "100 paying customers"


def test_obj_no_colon_after_bold():
    """`**OBJ-01 · Title**` (title only, no description)."""
    text = (
        "# Project brief: demo\n\n"
        "## Business objectives\n"
        "- **OBJ-01 · Just a title**\n"
    )
    brief = parse(text)
    assert len(brief.objectives) == 1
    assert brief.objectives[0].id == "OBJ-01"
    assert "Just a title" in brief.objectives[0].text


def test_features_section_named_capabilities():
    """A brief with `## Capabilities` instead of `## Features` still parses."""
    text = (
        "# Project brief: demo\n\n"
        "## Capabilities\n\n"
        "### FEAT-01 · Authentication\n"
        "**Serves:** OBJ-01\n"
        "**Expected outcome:** users can log in\n"
    )
    brief = parse(text)
    assert len(brief.features) == 1
    assert brief.features[0].id == "FEAT-01"
    assert brief.features[0].serves == ["OBJ-01"]


def test_section_match_is_case_insensitive():
    """`## business objectives` (lowercase) still matches."""
    text = (
        "# Project brief: demo\n\n"
        "## business objectives\n"
        "- **OBJ-01**: foo\n"
    )
    brief = parse(text)
    assert len(brief.objectives) == 1


def test_section_match_tolerates_parenthetical_suffix():
    """`## Features (capabilities)` matches the `Features` lookup."""
    text = (
        "# Project brief: demo\n\n"
        "## Features (capabilities)\n\n"
        "### FEAT-99 · Some feature\n"
        "**Serves:** OBJ-99\n"
    )
    brief = parse(text)
    assert len(brief.features) == 1
    assert brief.features[0].id == "FEAT-99"


def test_objectives_section_named_objectives():
    """`## Objectives` (short form) also works."""
    text = (
        "# Project brief: demo\n\n"
        "## Objectives\n"
        "- **OBJ-05**: short-form heading\n"
    )
    brief = parse(text)
    assert len(brief.objectives) == 1
    assert brief.objectives[0].id == "OBJ-05"


def test_personas_via_alternative_heading():
    """`## Personas` (synonym for `## Target users`) works."""
    text = (
        "# Project brief: demo\n\n"
        "## Personas\n"
        "- **Sara**: solo founder shipping at night\n"
    )
    brief = parse(text)
    assert len(brief.personas) == 1


def test_users_full_aigent_shape_parses():
    """End-to-end: a brief that mirrors the user's reported Aigent format
    (titles inside bold for OBJ; FEAT with H3 + Title)."""
    text = (
        "# Project brief: Aigent\n\n"
        "**Brief version:** 1\n\n"
        "## Vision\n"
        "Build the workspace solo founders actually use.\n\n"
        "## Business objectives\n"
        "- **OBJ-01 · Universal AI chat layer**: 100 paying customers in 90 days\n"
        "- **OBJ-02 · Multi-tenant isolation**: zero incidents year one\n\n"
        "## Capabilities\n\n"
        "### FEAT-01 · Multi-LLM routing\n"
        "**Serves:** OBJ-01\n"
        "**Expected outcome:** users can switch LLMs without losing context\n"
        "**What it must do:**\n"
        "- route to provider based on cost + latency\n\n"
        "### FEAT-02 · Tenant boundary enforcement\n"
        "**Serves:** OBJ-02\n"
        "**Expected outcome:** zero cross-tenant data exposure\n"
    )
    brief = parse(text)
    assert brief.name == "Aigent"
    assert len(brief.objectives) == 2
    assert brief.objective_ids == ["OBJ-01", "OBJ-02"]
    assert len(brief.features) == 2
    assert brief.feature_ids == ["FEAT-01", "FEAT-02"]
    assert brief.features[0].serves == ["OBJ-01"]
    assert brief.features[1].serves == ["OBJ-02"]
