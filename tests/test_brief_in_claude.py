"""CLAUDE.md renders brief excerpt when project_brief.md exists."""

from __future__ import annotations

from pathlib import Path

from dotagent.adapters.render import _render_brief_excerpt
from dotagent.context import Context, AgentSources
from dotagent.memory import CurrentState
from dotagent.project.brief import (
    Brief,
    Feature,
    HardRule,
    Integration,
    Objective,
)


def _make_ctx(brief: Brief | None = None) -> Context:
    return Context(
        project_name="demo",
        actor="alice",
        repo_path="/tmp/x",
        agent=AgentSources(),
        sources={},
        semantic_pointer_cards=[],
        personal={},
        current=CurrentState(actor="alice"),
        recent_episodic=[],
        config_top_n={},
        brief=brief,
    )


def test_no_brief_renders_empty_string():
    ctx = _make_ctx(brief=None)
    assert _render_brief_excerpt(ctx) == ""


def test_brief_with_objectives_appears_in_excerpt():
    brief = Brief(
        name="demo", brief_version=2, last_reviewed="2026-05-01",
        objectives=[
            Objective(id="OBJ-01", text="100 paying customers"),
            Objective(id="OBJ-02", text="<5min activation"),
        ],
    )
    excerpt = _render_brief_excerpt(_make_ctx(brief=brief))
    assert "## Project context" in excerpt
    assert "OBJ-01" in excerpt
    assert "OBJ-02" in excerpt
    assert "100 paying customers" in excerpt
    assert "brief version 2" in excerpt


def test_brief_with_features_shows_serves():
    brief = Brief(
        name="demo",
        features=[
            Feature(id="FEAT-01", name="Auth", serves=["OBJ-01"],
                    expected_outcome="users can log in"),
        ],
    )
    excerpt = _render_brief_excerpt(_make_ctx(brief=brief))
    assert "FEAT-01" in excerpt
    assert "Auth" in excerpt
    assert "OBJ-01" in excerpt
    assert "users can log in" in excerpt


def test_hard_rules_appear():
    brief = Brief(
        name="demo",
        hard_rules=[
            HardRule(id="RULE-01", name="Tenant isolation", why="BUG-014 leak"),
        ],
    )
    excerpt = _render_brief_excerpt(_make_ctx(brief=brief))
    assert "RULE-01" in excerpt
    assert "Tenant isolation" in excerpt
    assert "BUG-014" in excerpt


def test_glossary_terms_appear():
    brief = Brief(
        name="demo",
        glossary=[("tenant", "a billing account"), ("workspace", "data scope")],
    )
    excerpt = _render_brief_excerpt(_make_ctx(brief=brief))
    assert "Glossary" in excerpt
    assert "tenant" in excerpt
    assert "billing account" in excerpt


def test_non_goals_appear():
    brief = Brief(
        name="demo",
        non_goals=["Mobile native apps", "Federated SSO"],
    )
    excerpt = _render_brief_excerpt(_make_ctx(brief=brief))
    assert "Non-goals" in excerpt
    assert "Mobile native apps" in excerpt


def test_integrations_appear():
    brief = Brief(
        name="demo",
        integrations=[
            Integration(vendor="Stripe", purpose="billing",
                        used_by=["FEAT-03"], auth="api key"),
        ],
    )
    excerpt = _render_brief_excerpt(_make_ctx(brief=brief))
    assert "Stripe" in excerpt
    assert "billing" in excerpt
    assert "FEAT-03" in excerpt


def test_excerpt_includes_pointer_to_full_brief():
    brief = Brief(name="demo", vision="ship the thing")
    excerpt = _render_brief_excerpt(_make_ctx(brief=brief))
    assert "project_brief.md" in excerpt


def test_render_body_includes_brief_excerpt_when_present():
    """Full pipeline: render_body() includes the brief section."""
    from dotagent.adapters.render import render_body
    brief = Brief(
        name="demo", brief_version=1,
        objectives=[Objective(id="OBJ-01", text="ship")],
        features=[Feature(id="FEAT-01", name="auth", serves=["OBJ-01"])],
    )
    body = render_body(_make_ctx(brief=brief))
    assert "## Project context (from `.agent/project_brief.md`)" in body
    assert "FEAT-01" in body
    assert "OBJ-01" in body


def test_render_body_omits_brief_section_when_absent():
    """Backward compat: repos without a brief render unchanged."""
    from dotagent.adapters.render import render_body
    body = render_body(_make_ctx(brief=None))
    assert "## Project context (from `.agent/project_brief.md`)" not in body


def test_brief_metadata_line_includes_stage_and_review_date():
    brief = Brief(
        name="demo",
        brief_version=3,
        last_reviewed="2026-04-15",
        stage="beta",
    )
    excerpt = _render_brief_excerpt(_make_ctx(brief=brief))
    assert "brief version 3" in excerpt
    assert "last reviewed 2026-04-15" in excerpt
    assert "stage: beta" in excerpt
