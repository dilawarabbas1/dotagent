"""`dotagent project contract score` — per-signal rubric tests.

Each test builds a minimal contract-body fixture engineered to exercise one
signal at a specific score. Plus one perfect-30 fixture, one 22, one 14.

Body fixtures are constructed by hand (not via init_contract) so each test
isolates a single signal — the surrounding sections are at neutral / max
scores so the only varying axis is the signal under test.
"""

from __future__ import annotations

from dotagent.project.contract_rubric import (
    BAND_NOT_READY,
    BAND_POLISH,
    BAND_READY,
    BAND_REWORK,
    band_for,
    score_contract,
)


# ---- helpers --------------------------------------------------------------

# A baseline body that scores at-or-near max on every signal except the one
# the caller overrides. Helpers below build per-signal variants by replacing
# one section.
_BASELINE_SECTIONS = {
    "scope": (
        "Issue and verify JWTs for the customer portal so requests prove identity.\n"
        "- Sign tokens at login for valid credentials\n"
        "- Verify tokens against the documented public key\n"
        "- Rotation of signing keys across live sessions\n"
    ),
    "acceptance-criteria": "\n".join(
        f"{i}. {line}" for i, line in enumerate([
            "POST /auth/login returns 200 and a signed JWT token for valid credentials",
            "POST /auth/login returns 401 when credentials are invalid",
            "GET /auth/verify returns 200 for an unexpired token",
            "GET /auth/verify returns 401 for an expired token within 100ms",
            "Token rotation completes under 200ms p95 across live sessions",
            "Signing key fingerprint matches the documented public key",
            "Audit log contains a redacted token id for every verify call",
            "Auth p95 latency stays below 200ms under signing key rotation",
            "The rotation worker exits 0 on a clean restart cycle",
        ], start=1)
    ),
    "must-not-regress": (
        "- DA-BUG-007 — stale JWT cache: guard test `auth_rotation.test.py`\n"
        "- DA-BUG-012 — TTL inheritance: guard test `auth_ttl.test.py`\n"
        "- AP-001 — direct DB writes from controllers: guard test `controllers_layered.test.py`\n"
    ),
    "doc-surfaces": (
        "- `services/auth/jwt.py`, `services/auth/rotation.py`\n"
        "- `tests/auth/test_jwt.py`, `tests/auth/test_rotation.py`\n"
        "- `migrations/2026_05_jwt_keys.sql`\n"
        "- CLAUDE.md §Architecture, CLAUDE.md §Project rules\n"
        "- docs/bug-registry.md §Auth\n"
    ),
    "out-of-scope": (
        "- Mobile SSO integration [Phase 2]\n"
        "- Hardware-key support [m07]\n"
        "- Anonymous read paths [never]\n"
        "- Custom signing algorithms [owner-decision]\n"
    ),
    "test-plan": (
        "- unit: auth/test_jwt.py, auth/test_rotation.py\n"
        "- integration: tests/e2e/auth_flow.py\n"
        "- smoke: scripts/smoke_auth.sh\n"
        "- load: k6/auth_p95_under_200ms.js\n"
    ),
    "uat-proof": (
        "- `curl -i -X POST http://localhost:8080/auth/login -d ...`\n"
        "- `redis-cli get session:meta:test-user`\n"
        "- `psql -c 'SELECT count(*) FROM audit_log WHERE kind=auth_verify'`\n"
    ),
    "rollback-plan": (
        "- `alembic downgrade -1` reverts the 2026_05_jwt_keys migration\n"
        "  followed by `pytest tests/auth/test_rotation.py::test_smoke_post_revert`\n"
    ),
    "business-traceability": (
        "**Feature(s):** FEAT-01\n"
        "**Objective(s):** OBJ-01, OBJ-02\n"
        "- recovery via email completes within 5 minutes\n"
        "- prior sessions invalidated on password change\n"
    ),
}


def _body(**overrides: str) -> str:
    """Render a fixture body with optional per-section overrides."""
    sections = dict(_BASELINE_SECTIONS)
    sections.update(overrides)
    parts: list[str] = ["# Contract — 01-auth — cycle 1\n"]
    order = [
        "scope", "acceptance-criteria", "must-not-regress", "doc-surfaces",
        "out-of-scope", "test-plan", "uat-proof", "rollback-plan",
        "business-traceability",
    ]
    for anchor in order:
        parts.append(f"\n<!-- anchor: {anchor} -->\n## {anchor.replace('-', ' ').title()}\n\n")
        parts.append(sections[anchor])
    return "".join(parts)


def _signal(result, sid: str):
    return next(s for s in result.signals if s.id == sid)


# ---- band thresholds ------------------------------------------------------

def test_band_for_thresholds():
    # Updated for v0.5: rubric max is now 33 (S11 added). Bands shifted up.
    assert band_for(33) == BAND_READY
    assert band_for(30) == BAND_READY
    assert band_for(29) == BAND_POLISH
    assert band_for(24) == BAND_POLISH
    assert band_for(23) == BAND_REWORK
    assert band_for(18) == BAND_REWORK
    assert band_for(17) == BAND_NOT_READY
    assert band_for(0) == BAND_NOT_READY


# ---- S1: Scope is intent only ---------------------------------------------

def test_s1_full_score_on_pure_intent_scope():
    body = _body()
    s = _signal(score_contract(body), "S1")
    assert s.score == 3


def test_s1_zero_when_scope_drowns_in_implementation_tokens():
    leaky_scope = (
        "Wire `services/auth/jwt.py` to `master.users` and `tenant_42.sessions`.\n"
        "- Set `JWT_ROTATION_KEY=secret-blob`\n"
        "- Read `t:{tid}:user` keys via redis-cli\n"
        "- Call `psql -c` against the audit schema\n"
    )
    s = _signal(score_contract(_body(scope=leaky_scope)), "S1")
    assert s.score == 0


def test_s1_mid_score_when_one_token_leaks():
    one_token_scope = (
        "Issue and verify JWTs for the portal.\n"
        "- Issue tokens on login\n"
        "- Verify tokens against the documented public key\n"
        "- Rotate keys via `services/auth/rotation.py` worker\n"
    )
    s = _signal(score_contract(_body(scope=one_token_scope)), "S1")
    assert s.score == 2


# ---- S2: Scope is bounded -------------------------------------------------

def test_s2_3_4_bullets_scores_max():
    s = _signal(score_contract(_body()), "S2")
    assert s.score == 3


def test_s2_too_many_bullets_scores_low():
    big_scope = "Verbiage\n" + "\n".join(f"- bullet {i}" for i in range(11))
    s = _signal(score_contract(_body(scope=big_scope)), "S2")
    assert s.score == 0


def test_s2_5_bullets_scores_2():
    five_scope = "Lead\n" + "\n".join(f"- bullet {i}" for i in range(5))
    s = _signal(score_contract(_body(scope=five_scope)), "S2")
    assert s.score == 2


# ---- S3: Criteria count ---------------------------------------------------

def test_s3_full_score_at_8_to_15_criteria():
    s = _signal(score_contract(_body()), "S3")
    assert s.score == 3


def test_s3_low_score_at_2_criteria():
    short_crits = "1. POST /auth/login returns 200\n2. GET /auth/verify returns 401"
    s = _signal(score_contract(_body(**{"acceptance-criteria": short_crits})), "S3")
    assert s.score == 0


def test_s3_mid_score_at_3_criteria():
    three = "\n".join([
        "1. POST /auth/login returns 200 for valid creds",
        "2. POST /auth/login returns 401 for invalid creds",
        "3. JWT verify matches public key fingerprint",
    ])
    s = _signal(score_contract(_body(**{"acceptance-criteria": three})), "S3")
    assert s.score == 1


# ---- S4: Criteria are atomic ----------------------------------------------

def test_s4_atomic_criteria_score_max():
    s = _signal(score_contract(_body()), "S4")
    assert s.score == 3


def test_s4_compound_criteria_score_zero():
    fused = "\n".join([
        "1. POST /auth/login returns 200 and sets a cookie and writes to audit_log; logs the event",
        "2. GET /auth/verify returns 401 and clears the cache and notifies metrics; emits a counter",
        "3. Rotation worker exits 0 and updates redis and writes a marker; logs success",
        "4. Refresh returns 200 and writes a new token and audits; updates last_seen",
        "5. Logout returns 204 and clears redis and invalidates the JWT; writes audit",
        "6. Health returns 200 and reports queue depth and writes metrics; logs uptime",
        "7. Audit query returns 200 and filters by user and redacts pii; logs the access",
        "8. Token validate returns 200 and verifies signature and checks exp; emits metrics",
    ])
    s = _signal(score_contract(_body(**{"acceptance-criteria": fused})), "S4")
    assert s.score == 0


# ---- S5: Criteria are executable ------------------------------------------

def test_s5_all_executable_scores_max():
    s = _signal(score_contract(_body()), "S5")
    assert s.score == 3


def test_s5_vague_criteria_score_zero():
    vague = "\n".join([
        "1. The auth flow should be solid",
        "2. Tokens are nice and tidy",
        "3. Performance is acceptable",
    ])
    s = _signal(score_contract(_body(**{"acceptance-criteria": vague})), "S5")
    assert s.score == 0


# ---- S6: Criteria cover scope nouns ---------------------------------------

def test_s6_high_score_when_criteria_reference_scope_nouns():
    s = _signal(score_contract(_body()), "S6")
    assert s.score >= 2  # the baseline covers most nouns


def test_s6_zero_when_criteria_dont_reference_scope_at_all():
    # Scope is about JWT auth; criteria are about something else.
    irrelevant = "\n".join([
        f"{i}. Random unrelated assertion exits 0"
        for i in range(1, 9)
    ])
    s = _signal(score_contract(_body(**{"acceptance-criteria": irrelevant})), "S6")
    assert s.score == 0


# ---- S7: Must-not-regress has IDs + tests ---------------------------------

def test_s7_full_score_with_id_and_test_each_entry():
    s = _signal(score_contract(_body()), "S7")
    assert s.score == 3


def test_s7_zero_when_entries_are_prose_only():
    prose_only = "\n".join([
        "- Don't break the auth flow",
        "- Don't regress rate limiting",
        "- Don't leak tokens to logs",
    ])
    s = _signal(score_contract(_body(**{"must-not-regress": prose_only})), "S7")
    assert s.score == 0


def test_s7_greenfield_marker_scores_max():
    greenfield = "- (none — greenfield)\n"
    s = _signal(score_contract(_body(**{"must-not-regress": greenfield})), "S7")
    assert s.score == 3


# ---- S8: Surfaces touched is concrete -------------------------------------

def test_s8_full_score_when_no_placeholders_and_sections_named():
    s = _signal(score_contract(_body()), "S8")
    assert s.score == 3


def test_s8_zero_when_placeholders_dominate():
    sloppy = (
        "- DA-BUG-NNNN — TBD bug reference\n"
        "- migration NNN — schema change\n"
        "- CLAUDE.md\n"   # no §Section
        "- AGENTS.md\n"
        "- README.md\n"
    )
    s = _signal(score_contract(_body(**{"doc-surfaces": sloppy})), "S8")
    assert s.score <= 1


# ---- S9: Out of scope is phase-tagged -------------------------------------

def test_s9_full_score_when_every_entry_phase_tagged():
    s = _signal(score_contract(_body()), "S9")
    assert s.score == 3


def test_s9_zero_when_no_entries_tagged():
    untagged = (
        "- Mobile SSO\n"
        "- Hardware keys\n"
        "- Custom signing\n"
    )
    s = _signal(score_contract(_body(**{"out-of-scope": untagged})), "S9")
    assert s.score == 0


# ---- S10: Rollback / perf / observability ---------------------------------

def test_s10_full_score_when_triggers_have_corresponding_content():
    # baseline mentions migration (in doc-surfaces) AND has a rollback plan
    # AND mentions auth/latency (perf trigger) with p95/ms in criteria
    # AND mentions audit/redact in criteria.
    s = _signal(score_contract(_body()), "S10")
    assert s.score == 3


def test_s10_zero_when_migration_present_but_no_rollback_or_perf_or_obs():
    # Migration in surfaces; rollback section empty; criteria have no latency/obs
    naked_migration = (
        "1. POST /auth/login returns 200 for valid creds\n"
        "2. POST /auth/login returns 401 for invalid creds\n"
        "3. GET /auth/verify returns 200 for valid token\n"
        "4. GET /auth/verify returns 401 for expired token\n"
        "5. Rotation worker exits 0 on restart\n"
        "6. Login redirects to /home after success\n"
        "7. Logout returns 204\n"
        "8. Health endpoint returns 200\n"
    )
    body = _body(**{
        "acceptance-criteria": naked_migration,
        "rollback-plan": "- _(not filled in)_\n",
    })
    s = _signal(score_contract(body), "S10")
    assert s.score == 0


# ---- composite fixtures ---------------------------------------------------

def test_perfect_30_30_fixture_scores_30():
    """Baseline fixture is engineered to score perfect on every signal.

    Pre-v0.5 max was 30; with S11 added the new ceiling is 33.
    """
    result = score_contract(_body())
    assert result.total == 33, [f"{s.id}={s.score}" for s in result.signals]
    assert result.band == BAND_READY


def test_22_30_polish_fixture():
    """Knock 8 points off the baseline via two-section degradations."""
    body = _body(
        scope=(  # S1: -2 implementation tokens leaked  → S1=1 (loss 2)
            "Wire `services/auth/jwt.py` and `tenant_99.users` for auth.\n"
            "- Issue tokens on login\n"
            "- Verify tokens against the public key\n"
            "- Rotate keys without dropping sessions\n"
        ),
        **{"out-of-scope": (  # S9: 3 of 4 tagged → loss 1
            "- Mobile SSO [Phase 2]\n"
            "- Hardware keys [m07]\n"
            "- Custom signing [owner-decision]\n"
            "- WebAuthn\n"
        )},
        **{"must-not-regress": (  # S7: each entry has ID but no test → loss 1
            "- DA-BUG-007 — stale JWT cache\n"
            "- DA-BUG-012 — TTL inheritance\n"
            "- AP-001 — direct DB writes from controllers\n"
        )},
        **{"doc-surfaces": (  # S8: half doc-surfaces unsectioned → loss 1
            "- `services/auth/jwt.py`\n"
            "- `services/auth/rotation.py`\n"
            "- CLAUDE.md\n"
            "- AGENTS.md §Auth\n"
            "- README.md\n"
        )},
    )
    result = score_contract(body)
    assert 22 <= result.total <= 26, [f"{s.id}={s.score}" for s in result.signals]
    assert result.band == BAND_POLISH


def test_14_30_not_ready_fixture():
    """Heavily degraded across multiple signals — should land in not_ready."""
    body = _body(
        scope=(  # S1=0 S2=0
            "Wire `services/auth/jwt.py`, `master.users`, `tenant_42.sessions`.\n"
            + "\n".join(f"- bullet {i}" for i in range(12))
        ),
        **{"acceptance-criteria": (  # S3=0 (just 2) S4=0 fused S5=0 vague
            "1. The auth flow should be solid and tokens are nice\n"
            "2. Performance is acceptable and good"
        )},
        **{"must-not-regress": "- Don't break things\n- Don't leak tokens\n"},  # S7=0
        **{"out-of-scope": "- Mobile SSO\n- Hardware keys\n"},  # S9=0
    )
    result = score_contract(body)
    assert result.total <= 15, [f"{s.id}={s.score}" for s in result.signals]
    assert result.band == BAND_NOT_READY


def test_score_lowest_returns_n_signals_sorted_by_gap():
    # Many implementation tokens + many bullets in Scope → S1=0, S2=0;
    # filler bullet content also leaves S6 noun coverage at 0. The two worst
    # by (score - max) gap should both be picked.
    body = _body(
        scope=(
            "Wire `services/auth/jwt.py`, `master.users`, `tenant_42.sessions`, "
            "`redis-cli`, `psql`, `services/auth/rotation.py`, `tenant_99.users`.\n"
            + "\n".join(f"- bullet {i}" for i in range(11))
        ),
    )
    result = score_contract(body)
    top2 = result.lowest(2)
    ids = {s.id for s in top2}
    # The two worst should be drawn from {S1, S2, S6} (all score 0 in this fixture).
    assert ids.issubset({"S1", "S2", "S6"})
    # And every signal returned should be at its worst possible score.
    for s in top2:
        assert s.score == 0
