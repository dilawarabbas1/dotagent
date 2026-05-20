"""Parser tests for project/brief.py."""

from __future__ import annotations

from dotagent.project.brief import (
    Feature,
    HardRule,
    Objective,
    parse,
    render_stub,
)


_SAMPLE = """# Project brief: demo

**Last reviewed:** 2026-05-01  ·  **Brief version:** 3  ·  **Owner:** alice@x.com  ·  **Stage:** beta

## Vision (one sentence)
Become the default workspace for solo founders.

## Target users
- **Persona 1 — Sara**: ships at night
- **Persona 2 — Mike**: bills clients monthly

## Business objectives
- **OBJ-01**: 100 paying customers in 90 days
- **OBJ-02**: <5min activation
- **OBJ-03**: zero security incidents

## Features

### FEAT-01 · Authentication
**Serves:** OBJ-02, OBJ-03
**Expected outcome:** users can create accounts and log in
**What it must do:**
- sign up with email + password
- log in returning user

### FEAT-02 · Password recovery
**Serves:** OBJ-01, OBJ-02
**Expected outcome:** lost-password users recover access via email
**What it must do:**
- reset via email
- no enumeration oracle

## Value propositions
- one-line auth integration
- non-technical admin UI

## Business success metrics
- MRR — target $50k — source Stripe

## Non-goals (business)
- Mobile native apps
- Federated SSO

## Constraints
- Bootstrapped budget
- EU data residency from day one

## Hard rules
- **RULE-01 · Tenant isolation** — _why: BUG-014 leak in 2025-09; how: every multi-tenant query filters by tenant_id_
- **RULE-02 · No PII to LLMs** — _why: SOC2 + GDPR; how: redactor runs on every prompt_

## Glossary
- **tenant** — a billing account; one tenant has many users
- **workspace** — a tenant's sandboxed data scope

## Tenancy & security posture
- **Tenancy:** row-level
- **User auth:** JWT
- **Service-to-service auth:** HMAC

## External integrations
- **Stripe** — purpose: billing — used by: FEAT-03 — auth: api key — contract owner: alice
- **SendGrid** — purpose: transactional email — used by: FEAT-02 — auth: api key — contract owner: bob
"""


def test_parse_header_metadata():
    b = parse(_SAMPLE)
    assert b.name == "demo"
    assert b.brief_version == 3
    assert b.last_reviewed == "2026-05-01"
    assert b.owner == "alice@x.com"
    assert b.stage == "beta"


def test_parse_vision_first_line():
    b = parse(_SAMPLE)
    assert "default workspace for solo founders" in b.vision


def test_parse_personas_bullets():
    b = parse(_SAMPLE)
    assert len(b.personas) == 2


def test_parse_objectives_with_ids():
    b = parse(_SAMPLE)
    assert len(b.objectives) == 3
    assert b.objectives[0] == Objective(id="OBJ-01", text="100 paying customers in 90 days")
    assert b.objective_ids == ["OBJ-01", "OBJ-02", "OBJ-03"]


def test_parse_features_with_serves_and_behaviors():
    b = parse(_SAMPLE)
    assert len(b.features) == 2

    feat1 = b.features[0]
    assert feat1.id == "FEAT-01"
    assert feat1.name == "Authentication"
    assert feat1.serves == ["OBJ-02", "OBJ-03"]
    assert "users can create accounts" in feat1.expected_outcome
    assert len(feat1.behaviors) == 2

    feat2 = b.features[1]
    assert feat2.id == "FEAT-02"
    assert feat2.serves == ["OBJ-01", "OBJ-02"]


def test_parse_hard_rules():
    b = parse(_SAMPLE)
    assert len(b.hard_rules) == 2
    rule1 = b.hard_rules[0]
    assert rule1.id == "RULE-01"
    assert rule1.name == "Tenant isolation"
    assert "BUG-014" in rule1.why
    assert "tenant_id" in rule1.how


def test_parse_glossary_terms():
    b = parse(_SAMPLE)
    assert len(b.glossary) == 2
    term, defn = b.glossary[0]
    assert term == "tenant"
    assert "billing account" in defn


def test_parse_integrations_with_used_by():
    b = parse(_SAMPLE)
    assert len(b.integrations) == 2
    stripe = b.integrations[0]
    assert stripe.vendor == "Stripe"
    assert stripe.purpose == "billing"
    assert stripe.used_by == ["FEAT-03"]
    assert stripe.auth == "api key"
    assert stripe.contract_owner == "alice"


def test_to_dict_roundtrip_stable():
    b = parse(_SAMPLE)
    payload = b.to_dict()
    assert payload["name"] == "demo"
    assert payload["brief_version"] == 3
    assert len(payload["objectives"]) == 3
    assert len(payload["features"]) == 2


def test_render_stub_produces_parseable_output():
    text = render_stub(name="aigent", owner="me@x.com", vision="ship the thing")
    b = parse(text)
    assert b.name == "aigent"
    assert b.owner == "me@x.com"
    # Vision line in stub starts with the value we passed.
    assert "ship the thing" in b.vision


def test_render_stub_includes_modules_anchors():
    text = render_stub(name="demo")
    assert "<!-- anchor: modules-table-begin -->" in text
    assert "<!-- anchor: modules-table-end -->" in text


def test_parse_tolerates_missing_sections():
    text = "# Project brief: minimal\n\n**Last reviewed:** 2026-01-01\n"
    b = parse(text)
    assert b.name == "minimal"
    assert b.objectives == []
    assert b.features == []
    assert b.hard_rules == []
