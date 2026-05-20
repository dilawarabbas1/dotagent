"""Signal implementations for the contract scoring rubric (S1..S10).

Each `sN_*` function takes the contract body (everything before the
negotiation-log anchor) and returns a `SignalScore`. All scoring is
deterministic — no LLM calls in v1. Where an LLM fallback would clearly
help (e.g., S6 noun extraction, S10 trigger detection), the function
carries a TODO comment marking the upgrade point.

The functions share a small set of section/criteria parsers at the bottom
of this file. Those mirror — and intentionally duplicate, to avoid a
circular import — the parsers in `contract.py`.
"""

from __future__ import annotations

import re

from .contract_rubric import SignalScore


# ---- shared parsers (duplicated from contract.py to avoid circular import) ----

_ANCHOR_RE = re.compile(r"<!--\s*anchor:\s*([\w-]+)\s*-->")
_CRITERION_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")


def _sections(body: str) -> dict[str, str]:
    """{anchor_name: section body up to next anchor or EOF}."""
    out: dict[str, str] = {}
    matches = list(_ANCHOR_RE.finditer(body))
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out[name] = body[start:end]
    return out


def _bullets(section: str) -> list[str]:
    """Top-level bullet items from a section, ignoring blockquote instructions."""
    out: list[str] = []
    for line in section.splitlines():
        if line.lstrip().startswith(">"):
            continue
        m = _BULLET_RE.match(line)
        if m:
            out.append(m.group(1).strip())
    return out


def _numbered(section: str) -> list[str]:
    """Numbered items from a section, ignoring blockquote instructions."""
    out: list[str] = []
    for line in section.splitlines():
        if line.lstrip().startswith(">"):
            continue
        m = _CRITERION_RE.match(line)
        if m:
            out.append(m.group(2).strip())
    return out


def _authored(section: str) -> str:
    """Section body with blockquote instruction lines stripped."""
    return "\n".join(
        line for line in section.splitlines() if not line.lstrip().startswith(">")
    )


# ---- S1: Scope is intent only ---------------------------------------------

# Implementation tokens that should NOT appear in the Scope section. Their
# presence means the agent leaked implementation detail into product intent.
_IMPL_TOKEN_PATTERNS = (
    re.compile(r"[A-Za-z_]+\.(?:js|mjs|ts|tsx|jsx|cjs|py|sql|sh|go|rs|java|rb)\b"),  # file paths
    re.compile(r"\bmaster\.\w+\b"),                # master table refs
    re.compile(r"\btenant_\d*\.\w+\b"),             # tenant table refs
    re.compile(r"\b[A-Z_]{4,}=\w+\b"),               # env-var assignments
    re.compile(r"t:\{[a-z_]+\}:\w*"),                # redis key patterns
    re.compile(r"\b(?:redis-cli|psql|curl|kubectl|docker|grep|jq|sed|awk)\b"),  # commands
)


def s1_scope_intent_only(body: str) -> SignalScore:
    section = _sections(body).get("scope", "")
    text = _authored(section)
    tokens: list[str] = []
    for pat in _IMPL_TOKEN_PATTERNS:
        tokens.extend(pat.findall(text))
    n = len(tokens)
    if n == 0:
        score, fix = 3, ""
    elif n <= 2:
        score, fix = 2, f"Move {n} implementation token(s) to 'Surfaces touched': {tokens[:2]!r}"
    elif n <= 5:
        score, fix = 1, f"Move {n} implementation tokens to 'Surfaces touched'; scope is product intent only"
    else:
        score, fix = 0, "Scope has too many implementation details; rewrite as product intent (no file paths, table names, commands)"
    return SignalScore(
        id="S1",
        name="Scope is intent only",
        score=score,
        evidence=f"{n} implementation token(s) detected in Scope section",
        fix=fix,
    )


# ---- S2: Scope is bounded -------------------------------------------------

def s2_scope_bounded(body: str) -> SignalScore:
    n = len(_bullets(_sections(body).get("scope", "")))
    if 3 <= n <= 4:
        score, fix = 3, ""
    elif n == 5:
        score, fix = 2, "Scope has 5 bullets; consider trimming to 3-4 for sharper focus"
    elif 6 <= n <= 10:
        score, fix = 1, f"Scope has {n} bullets; trim to 3-4 of the truly essential intents"
    else:
        score, fix = 0, ("Scope has 0 bullets — write 3-4 product intents" if n == 0
                        else f"Scope has {n} bullets — too many to be bounded; pick 3-4 essentials")
    return SignalScore(
        id="S2",
        name="Scope is bounded",
        score=score,
        evidence=f"{n} scope bullet(s)",
        fix=fix,
    )


# ---- S3: Criteria count is adequate ---------------------------------------

def s3_criteria_count_adequate(body: str) -> SignalScore:
    n = len(_numbered(_sections(body).get("acceptance-criteria", "")))
    if 8 <= n <= 15:
        score, fix = 3, ""
    elif 6 <= n <= 7 or n >= 16:
        score, fix = 2, ("Tighten by splitting compound criteria into atomic ones (target 8-15)"
                        if n >= 16 else "Add criteria covering remaining scope nouns (target 8-15)")
    elif 3 <= n <= 5:
        score, fix = 1, f"{n} criteria is the floor; aim for 8-15 for full coverage"
    else:
        score, fix = 0, f"{n} criteria is below the minimum; write at least 3 atomic, testable assertions"
    return SignalScore(
        id="S3",
        name="Criteria count is adequate",
        score=score,
        evidence=f"{n} numbered criterion/criteria",
        fix=fix,
    )


# ---- S4: Criteria are atomic ----------------------------------------------

# Separator patterns that indicate a criterion is fused from multiple assertions.
# Parenthetical asides are excluded by stripping them before counting.
_PAREN_RE = re.compile(r"\([^)]*\)")
_SEPARATOR_RE = re.compile(r"(?:;|\s+and\s+|,\s+and\s+)", re.IGNORECASE)


def _separator_count(criterion: str) -> int:
    stripped = _PAREN_RE.sub("", criterion)
    return len(_SEPARATOR_RE.findall(stripped))


def s4_criteria_atomic(body: str) -> SignalScore:
    crits = _numbered(_sections(body).get("acceptance-criteria", ""))
    if not crits:
        return SignalScore(
            id="S4", name="Criteria are atomic", score=0,
            evidence="0 criteria to evaluate",
            fix="Write criteria first (see S3), then keep one assertion per line",
        )
    avg = sum(_separator_count(c) for c in crits) / len(crits)
    if avg < 0.5:
        score, fix = 3, ""
    elif avg < 1.0:
        score, fix = 2, f"avg {avg:.2f} separators/criterion; split items joined with ' and ' or ';'"
    elif avg <= 1.5:
        score, fix = 1, f"avg {avg:.2f} separators/criterion; most criteria are fused — split into atomic lines"
    else:
        score, fix = 0, f"avg {avg:.2f} separators/criterion; nearly every criterion is multi-assertion. Rewrite one-per-line."
    return SignalScore(
        id="S4",
        name="Criteria are atomic",
        score=score,
        evidence=f"avg {avg:.2f} separator(s) per criterion across {len(crits)} criterion/criteria",
        fix=fix,
    )


# ---- S5: Criteria are executable ------------------------------------------
#
# Reuses the same 4-signal heuristic from the validator: a criterion is
# "executable" if it carries a verb keyword, a comparison operator, a
# numeric threshold with unit, or a concrete test/command reference.

def _has_verb_shape_local(criterion: str) -> bool:
    """Inline copy of the verb-shape detector to avoid importing from contract.py
    (which would create a circular import via the model). Same shape as the
    validator's _has_verb_shape but with a slightly broader keyword set —
    things like 'records' / 'logs' / 'writes' are testable assertions too.
    """
    low = criterion.lower()
    verbs = (
        "returns", "equals", "passes", "exits", "redirects", "matches",
        "succeeds", "fails", "errors", "throws", "completes",
        "stays", "falls", "rises", "exceeds", "meets", "satisfies",
        "contains", "lacks", "includes", "excludes",
        "within", "outside", "above", "below", "before", "after",
        # additional outcome verbs common in service-level assertions
        "logs", "records", "writes", "emits", "fires", "raises",
        "produces", "consumes", "rejects", "accepts", "asserts",
    )
    if any(v in low for v in verbs):
        return True
    if any(op in criterion for op in ("==", "!=", "<=", ">=", "≤", "≥", "<", ">", "=")):
        return True
    threshold = re.compile(
        r"\d+(?:\.\d+)?\s*(?:ms|sec|secs|seconds?|min|mins|minutes?|"
        r"h|hr|hrs|hours?|kb|mb|gb|tb|%|p\d{2,3}|s)(?![a-zA-Z0-9])",
        re.IGNORECASE,
    )
    if threshold.search(criterion):
        return True
    command = re.compile(
        r"\b(?:pytest|npm\s+test|cargo\s+test|go\s+test|make\s+test|"
        r"curl|grep|jq|exit\s+code|sha256|sha1)\b",
        re.IGNORECASE,
    )
    if command.search(criterion):
        return True
    return False


def s5_criteria_executable(body: str) -> SignalScore:
    crits = _numbered(_sections(body).get("acceptance-criteria", ""))
    if not crits:
        return SignalScore(
            id="S5", name="Criteria are executable", score=0,
            evidence="0 criteria to evaluate",
            fix="Write criteria with at least one of: a verb, an operator, a numeric+unit threshold, or a test/command reference",
        )
    matched = sum(1 for c in crits if _has_verb_shape_local(c))
    pct = matched / len(crits)
    if pct == 1.0:
        score, fix = 3, ""
    elif pct >= 0.75:
        score, fix = 2, f"{len(crits)-matched}/{len(crits)} criteria lack a verb-shape signal; tighten them"
    elif pct >= 0.50:
        score, fix = 1, f"only {matched}/{len(crits)} criteria are executable; rewrite the rest as testable assertions"
    else:
        score, fix = 0, f"only {matched}/{len(crits)} criteria are executable; most are vague intent rather than testable"
    return SignalScore(
        id="S5",
        name="Criteria are executable",
        score=score,
        evidence=f"{matched}/{len(crits)} criteria carry a verb-shape signal ({pct*100:.0f}%)",
        fix=fix,
    )


# ---- S6: Criteria cover scope nouns ---------------------------------------
#
# TODO(llm-fallback): when ANTHROPIC_API_KEY is set, replace the heuristic
# stop-list with an LLM call that extracts domain nouns more accurately.
# Today's heuristic over-counts (every non-stopword token) which makes the
# coverage % conservative — fine as a floor.

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "to", "of", "in", "on",
    "at", "for", "with", "by", "from", "as", "is", "are", "was", "were",
    "be", "been", "being", "do", "does", "did", "have", "has", "had",
    "this", "that", "these", "those", "it", "its", "their", "our",
    "we", "you", "us", "they", "them", "i", "me", "my", "your",
    "scope", "out", "module", "purpose", "should", "must",
    "will", "would", "can", "could", "may", "might",
    # connectives and generic adjectives that don't carry domain meaning
    "without", "across", "every", "into", "onto", "through",
    "some", "many", "much", "more", "less", "less", "very",
    "just", "only", "also", "such", "than", "then", "when",
    "where", "while", "which", "whom", "what", "into",
}

_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_-]{2,}\b")


def _scope_nouns(scope_section: str) -> set[str]:
    """Heuristic 'domain noun' set from the Scope bullets."""
    out: set[str] = set()
    for bullet in _bullets(scope_section):
        for w in _WORD_RE.findall(bullet):
            wl = w.lower()
            if wl in _STOPWORDS:
                continue
            if len(wl) < 4:
                continue
            out.add(wl)
    return out


def s6_criteria_cover_scope_nouns(body: str) -> SignalScore:
    sections = _sections(body)
    nouns = _scope_nouns(sections.get("scope", ""))
    crits = _numbered(sections.get("acceptance-criteria", ""))
    if not nouns:
        return SignalScore(
            id="S6", name="Criteria cover scope nouns", score=0,
            evidence="0 scope nouns to evaluate",
            fix="Write scope bullets with concrete domain nouns first (see S1, S2)",
        )
    if not crits:
        return SignalScore(
            id="S6", name="Criteria cover scope nouns", score=0,
            evidence=f"{len(nouns)} scope noun(s), 0 criteria",
            fix="Write criteria that name every scope noun (see S3)",
        )
    crit_blob = " \n ".join(crits).lower()

    def _covered(noun: str) -> bool:
        # Substring match, with a tiny stem so plurals / present-tense forms count:
        # "tokens" / "token" and "rotating" / "rotate" both register as coverage.
        if noun in crit_blob:
            return True
        if noun.endswith("s") and len(noun) > 3 and noun[:-1] in crit_blob:
            return True
        if noun.endswith("ing") and len(noun) > 5 and noun[:-3] in crit_blob:
            return True
        return False

    covered = sum(1 for n in nouns if _covered(n))
    pct = covered / len(nouns)
    if pct >= 0.90:
        score, fix = 3, ""
    elif pct >= 0.70:
        score, fix = 2, f"covered {covered}/{len(nouns)} scope nouns; add criteria for the missing ones"
    elif pct >= 0.40:
        score, fix = 1, f"covered {covered}/{len(nouns)} scope nouns; most are unverified by acceptance criteria"
    else:
        score, fix = 0, f"covered {covered}/{len(nouns)} scope nouns; criteria don't reference what scope promises"
    return SignalScore(
        id="S6",
        name="Criteria cover scope nouns",
        score=score,
        evidence=f"{covered}/{len(nouns)} scope nouns referenced in criteria ({pct*100:.0f}%)",
        fix=fix,
    )


# ---- S7: Must-not-regress has IDs + guard tests ---------------------------

_BUG_ID_RE = re.compile(r"\b(?:DA-BUG-\d+|AP-\d+|F\d{3,})\b")
_TEST_FILE_RE = re.compile(r"\b\w+\.test\.\w+\b")
_GREENFIELD_MARKER_RE = re.compile(
    r"\(none[^)]*greenfield[^)]*\)|\(greenfield[^)]*\)",
    re.IGNORECASE,
)


def s7_must_not_regress_disciplined(body: str) -> SignalScore:
    section = _sections(body).get("must-not-regress", "")
    items = _bullets(section)
    if not items:
        return SignalScore(
            id="S7", name="Must-not-regress is disciplined", score=0,
            evidence="0 must-not-regress entries (and no greenfield marker)",
            fix="Add must-not-regress entries with IDs (DA-BUG-####, AP-###, F###) and guard test names, or mark '(none — greenfield)'",
        )
    # Single-entry greenfield marker → 3
    if len(items) == 1 and _GREENFIELD_MARKER_RE.search(items[0]):
        return SignalScore(
            id="S7", name="Must-not-regress is disciplined", score=3,
            evidence="single 'none — greenfield' marker; no regressions possible", fix="",
        )
    per_item: list[int] = []
    for item in items:
        if _GREENFIELD_MARKER_RE.search(item):
            continue  # ignore greenfield markers mixed with real entries
        partial = 0
        if _BUG_ID_RE.search(item):
            partial += 1
        if _TEST_FILE_RE.search(item):
            partial += 1
        per_item.append(partial)
    if not per_item:
        # all items were greenfield markers but not exactly one
        return SignalScore(
            id="S7", name="Must-not-regress is disciplined", score=0,
            evidence=f"{len(items)} greenfield markers mixed with no real entries",
            fix="Use exactly one entry: '(none — greenfield)' OR replace with real ID + test entries",
        )
    avg = sum(per_item) / len(per_item)  # 0..2
    # Normalize 0-2 → 0-3 with round-down for fair grading
    if avg >= 1.9:
        score, fix = 3, ""
    elif avg >= 1.4:
        score, fix = 2, "Most entries have both ID and test; add the missing IDs/test names to the rest"
    elif avg >= 0.7:
        score, fix = 1, "Entries name either an ID or a test but rarely both; add the other half"
    else:
        score, fix = 0, "Must-not-regress entries are prose-only; add an ID (DA-BUG-####/AP-###/F###) AND a guard test filename per entry"
    return SignalScore(
        id="S7",
        name="Must-not-regress is disciplined",
        score=score,
        evidence=f"{len(per_item)} entries; avg {avg:.2f} of (ID, test) markers per entry",
        fix=fix,
    )


# ---- S8: Surfaces touched is concrete --------------------------------------

_NNN_PLACEHOLDER_RE = re.compile(r"\bNNN+\b|####+")
_SECTION_REF_RE = re.compile(r"§[A-Za-z]")  # e.g., "CLAUDE.md §Architecture"
_DOC_FILE_RE = re.compile(r"\b(?:CLAUDE|AGENTS|README|CHANGELOG|CONTRIBUTING|[A-Z_-]+)\.md\b")


def s8_surfaces_concrete(body: str) -> SignalScore:
    section = _sections(body).get("doc-surfaces", "")
    text = _authored(section)
    placeholders = _NNN_PLACEHOLDER_RE.findall(text)
    doc_refs = _DOC_FILE_RE.findall(text)
    sectioned = len(_SECTION_REF_RE.findall(text))
    n_docs = len(doc_refs)

    # Score components: (a) placeholders absent, (b) doc surfaces have sections
    a_clean = len(placeholders) == 0
    a_some = len(placeholders) <= 1

    if n_docs == 0:
        # No doc surfaces named at all — could be intentional (code-only change)
        # or a gap. Score by placeholder cleanliness only.
        if a_clean:
            return SignalScore(
                id="S8", name="Surfaces touched is concrete", score=3,
                evidence="no doc surfaces named, no placeholders",
                fix="",
            )
        return SignalScore(
            id="S8", name="Surfaces touched is concrete", score=1,
            evidence=f"{len(placeholders)} placeholder token(s); no doc surfaces named",
            fix="Resolve NNN placeholders and name affected docs with §Section refs",
        )

    sectioned_ratio = sectioned / n_docs if n_docs else 0.0
    if a_clean and sectioned_ratio >= 0.99:
        score, fix = 3, ""
    elif a_clean and sectioned_ratio >= 0.5:
        score, fix = 2, f"{n_docs - sectioned}/{n_docs} doc surfaces lack a §Section ref"
    elif a_some:
        score, fix = 1, "Some placeholders remain and most doc surfaces lack §Section refs"
    else:
        score, fix = 0, f"{len(placeholders)} NNN placeholders + many unsectioned doc surfaces; resolve all"
    return SignalScore(
        id="S8",
        name="Surfaces touched is concrete",
        score=score,
        evidence=f"{len(placeholders)} placeholder(s); {sectioned}/{n_docs} doc surfaces have §Section",
        fix=fix,
    )


# ---- S9: Out of scope is phase-tagged --------------------------------------

_PHASE_TAG_RE = re.compile(
    r"\[(?:phase\s*\d+|m\d+|never|owner[a-z\-]*)\]",
    re.IGNORECASE,
)


def s9_out_of_scope_phase_tagged(body: str) -> SignalScore:
    section = _sections(body).get("out-of-scope", "")
    items = _bullets(section)
    if not items:
        return SignalScore(
            id="S9", name="Out of scope is phase-tagged", score=0,
            evidence="0 out-of-scope entries",
            fix="List items explicitly out of this cycle, each phase-tagged: [Phase 2], [m07], [never], [owner-decision]",
        )
    tagged = sum(1 for it in items if _PHASE_TAG_RE.search(it))
    pct = tagged / len(items)
    if pct >= 0.99:
        score, fix = 3, ""
    elif pct >= 0.66:
        score, fix = 2, f"{len(items) - tagged}/{len(items)} entries lack a phase tag — add [Phase N], [mNN], [never], or [owner-decision]"
    elif pct >= 0.33:
        score, fix = 1, f"only {tagged}/{len(items)} entries are phase-tagged; untagged items don't count"
    else:
        score, fix = 0, "out-of-scope entries are untagged; without a phase tag they read as forgotten work not deliberate exclusion"
    return SignalScore(
        id="S9",
        name="Out of scope is phase-tagged",
        score=score,
        evidence=f"{tagged}/{len(items)} entries phase-tagged ({pct*100:.0f}%)",
        fix=fix,
    )


# ---- S10: Rollback / performance / observability --------------------------
#
# TODO(llm-fallback): trigger detection here is keyword-based. An LLM pass
# would catch indirect signals (e.g., a "soft-delete column" mention implies
# migration even without the word "migration"). Today's check ranges from
# conservative to overeager depending on phrasing.

_MIGRATION_TRIGGER = re.compile(r"\b(?:migration|schema\s+change|alembic|sql\s+migrate)\b", re.IGNORECASE)
_PERF_TRIGGER = re.compile(r"\b(?:/chat|ingress|hot\s*path|auth\b|p95|p99|latency)\b", re.IGNORECASE)
_OBS_TRIGGER = re.compile(r"\b(?:audit|logged|logging|redact|pii)\b", re.IGNORECASE)

_LATENCY_UNIT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*ms\b|\bp\d{2,3}\b", re.IGNORECASE)


_PLACEHOLDER_RE = re.compile(r"_\(\s*no entries yet[^)]*\)_|_\(\s*not filled in\s*\)_", re.IGNORECASE)


def _has_rollback_section(body: str) -> bool:
    """Rollback presence: the rollback-plan section has at least one non-
    placeholder bullet, OR criteria mention revert/rollback directly.

    Placeholders (`_(no entries yet — agents to populate)_`) and the
    'additive change only' opt-out do NOT count as real content.
    """
    sections = _sections(body)
    real_bullets = [
        b for b in _bullets(sections.get("rollback-plan", ""))
        if not _PLACEHOLDER_RE.search(b)
        and "additive change only" not in b.lower()
    ]
    if real_bullets:
        return True
    crits_blob = " ".join(_numbered(sections.get("acceptance-criteria", ""))).lower()
    return bool(re.search(r"\b(?:revert|rollback)\b", crits_blob))


def _has_latency_criterion(body: str) -> bool:
    for c in _numbered(_sections(body).get("acceptance-criteria", "")):
        if _LATENCY_UNIT_RE.search(c):
            return True
    return False


def _has_observability_criterion(body: str) -> bool:
    crits = _numbered(_sections(body).get("acceptance-criteria", ""))
    for c in crits:
        if re.search(r"\b(?:audit|logged|redact|pii|observ)\w*\b", c, re.IGNORECASE):
            return True
    return False


def s10_rollback_perf_observability(body: str) -> SignalScore:
    surfaces = _authored(_sections(body).get("doc-surfaces", ""))
    crits_blob = "\n".join(_numbered(_sections(body).get("acceptance-criteria", "")))
    trigger_text = f"{surfaces}\n{crits_blob}"

    triggers: list[str] = []
    met: list[str] = []

    if _MIGRATION_TRIGGER.search(trigger_text):
        triggers.append("rollback")
        if _has_rollback_section(body):
            met.append("rollback")
    if _PERF_TRIGGER.search(trigger_text):
        triggers.append("perf")
        if _has_latency_criterion(body):
            met.append("perf")
    if _OBS_TRIGGER.search(trigger_text):
        triggers.append("observability")
        if _has_observability_criterion(body):
            met.append("observability")

    if not triggers:
        return SignalScore(
            id="S10", name="Rollback / perf / observability requirements", score=3,
            evidence="no triggers detected (no migration / perf-hot-path / audit signals)",
            fix="",
        )
    pct = len(met) / len(triggers)
    if pct >= 0.99:
        score, fix = 3, ""
    elif pct >= 0.66:
        score, fix = 2, f"{len(met)}/{len(triggers)} requirements met: missing {sorted(set(triggers) - set(met))}"
    elif pct >= 0.34:
        score, fix = 1, f"{len(met)}/{len(triggers)} requirements met; most triggered requirements are unaddressed"
    else:
        score, fix = 0, f"0/{len(triggers)} triggered requirements met. Missing: {sorted(set(triggers) - set(met))}"
    return SignalScore(
        id="S10",
        name="Rollback / perf / observability requirements",
        score=score,
        evidence=f"triggers={triggers} met={met}",
        fix=fix,
    )


# ---- Public helpers used by freeze gating in contract.py ------------------

def has_migration_trigger(body: str) -> bool:
    """True if a migration-trigger is detectable in author-written content.

    Public because `freeze_contract` consults it to decide whether the S10=0
    gate fires. We scan only the author-written lines of doc-surfaces and
    acceptance-criteria — blockquote instructions in the template legitimately
    contain the word "migration" and must not trip the gate.
    """
    sections = _sections(body)
    haystacks = [
        _authored(sections.get("doc-surfaces", "")),
        _authored(sections.get("acceptance-criteria", "")),
        _authored(sections.get("rollback-plan", "")),
    ]
    return any(_MIGRATION_TRIGGER.search(h) for h in haystacks)


# ---- S11: business-traceability ---------------------------------------------

_FEAT_REF_RE = re.compile(r"\bFEAT-\d+\b")
_OBJ_REF_RE = re.compile(r"\bOBJ-\d+\b")


def s11_business_traceability(body: str) -> SignalScore:
    """Every contract must cite at least one FEAT and one OBJ from
    project_brief.md. Scoring:

        0/3  no FEAT-NN cited anywhere in business-traceability section
        1/3  FEAT-NN cited but no OBJ-NN
        2/3  both FEAT-NN and OBJ-NN cited, but no behavior bullets
             (just IDs, no narrative)
        3/3  FEAT-NN + OBJ-NN + at least one populated bullet under the
             section (real traceability narrative)

    Only the author-written content of the business-traceability section
    counts. The template's `_(populate ...)_` placeholder is filtered out.
    """
    sections = _sections(body)
    section = sections.get("business-traceability", "")
    authored = _authored(section)
    placeholder_stripped = _PLACEHOLDER_RE.sub("", authored)

    feats = set(_FEAT_REF_RE.findall(placeholder_stripped))
    objs = set(_OBJ_REF_RE.findall(placeholder_stripped))

    if not feats:
        return SignalScore(
            id="S11", name="Business traceability (FEAT+OBJ)", score=0,
            evidence="no FEAT-NN cited in business-traceability section",
            fix="add `**Feature(s):** FEAT-NN` and `**Objective(s):** OBJ-NN` referencing project_brief.md",
        )
    if not objs:
        return SignalScore(
            id="S11", name="Business traceability (FEAT+OBJ)", score=1,
            evidence=f"FEAT-NN cited ({len(feats)}) but no OBJ-NN",
            fix="add `**Objective(s):** OBJ-NN` to cite the business objectives served",
        )

    # Real bullets in the authored portion (not just ID lines)
    real_bullets = [
        b for b in _bullets(section)
        if not _PLACEHOLDER_RE.search(b)
        and not re.fullmatch(r"\s*\*\*?[A-Za-z][\w ()]*\*?\*:\s*[A-Z]+-\d+(?:[,\s]+[A-Z]+-\d+)*\s*", b)
    ]
    if not real_bullets:
        return SignalScore(
            id="S11", name="Business traceability (FEAT+OBJ)", score=2,
            evidence=f"FEAT-NN and OBJ-NN cited but no behavior bullets",
            fix="add bullets describing which FEAT behaviors this slice must satisfy",
        )

    return SignalScore(
        id="S11", name="Business traceability (FEAT+OBJ)", score=3,
        evidence=f"cites {len(feats)} FEAT-NN, {len(objs)} OBJ-NN, {len(real_bullets)} bullet(s)",
    )
