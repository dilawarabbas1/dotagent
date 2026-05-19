"""Contract scoring rubric (Phase 9).

Grades a `contract.md` against a 10-signal rubric (0-3 each, 30 total). Used
by both Claude (dev) and Codex (QA) after each negotiate round to refuse
convergence below a threshold (typically 27/30).

The score is a **stateless** computation over the contract body. dotagent
does not persist it — Coda's orchestrator owns score persistence and the
"refuse convergence below 27" enforcement. This module just answers the
question "what's this contract's grade right now?"

## Signal map (S1..S10)

  S1  Scope is intent only           (max 3)
  S2  Scope is bounded                (max 3)
  S3  Criteria count is adequate      (max 3)
  S4  Criteria are atomic             (max 3)
  S5  Criteria are executable         (max 3)
  S6  Criteria cover scope nouns      (max 3)
  S7  Must-not-regress has IDs+tests  (max 3)
  S8  Surfaces touched is concrete    (max 3)
  S9  Out of scope is phase-tagged    (max 3)
  S10 Rollback / perf / observability (max 3)

  Total: 30. Bands: 27-30 ready, 22-26 polish, 16-21 rework, ≤15 not_ready.

The actual signal implementations live in `_signals.py` adjacent to this file;
this module is the public dataclass + entry-point surface.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


# ---- Bands ----------------------------------------------------------------

BAND_READY = "ready"        # 27-30
BAND_POLISH = "polish"      # 22-26
BAND_REWORK = "rework"      # 16-21
BAND_NOT_READY = "not_ready"  # 0-15

SIGNAL_MAX = 3
TOTAL_MAX = 30


def band_for(total: int) -> str:
    """Map a 0-30 total to a band name."""
    if total >= 27:
        return BAND_READY
    if total >= 22:
        return BAND_POLISH
    if total >= 16:
        return BAND_REWORK
    return BAND_NOT_READY


# ---- Dataclasses ----------------------------------------------------------

@dataclass
class SignalScore:
    """Score for one of the 10 rubric signals.

    `evidence` is a one-line factual description of what the rubric saw
    (e.g., "found 4 implementation tokens in Scope: services/auth.py,
    master.users, ..."). `fix` is a one-line "what good looks like" hint
    when the score is below max — empty string when score == max.
    """

    id: str
    name: str
    score: int
    max: int = SIGNAL_MAX
    evidence: str = ""
    fix: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ContractScore:
    """Aggregate score for one contract.md.

    Stateless: this is a pure function of the contract body at evaluation
    time. dotagent does not persist it. Callers (typically Coda) own any
    history.
    """

    total: int
    max: int = TOTAL_MAX
    band: str = BAND_NOT_READY
    signals: list[SignalScore] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "max": self.max,
            "band": self.band,
            "signals": [s.to_dict() for s in self.signals],
        }

    def lowest(self, n: int = 2) -> list[SignalScore]:
        """Return the `n` signals with the largest (max - score) gap, ties broken by signal id."""
        return sorted(self.signals, key=lambda s: (s.score - s.max, s.id))[:n]


# ---- Public entry point ---------------------------------------------------

def score_contract(body: str) -> ContractScore:
    """Score the contract body against all 10 signals.

    `body` should be the substantive contract — the negotiation log section
    is irrelevant to the score and should be stripped by the caller. The
    same content-hash boundary used by `contract.py` (everything before
    `<!-- anchor: negotiation-log -->`) is the right input here.
    """
    # Import here to avoid a circular at module-load time — contract_rubric is
    # imported by the CLI which is also reachable from contract.py.
    from ._signals import (
        s1_scope_intent_only,
        s2_scope_bounded,
        s3_criteria_count_adequate,
        s4_criteria_atomic,
        s5_criteria_executable,
        s6_criteria_cover_scope_nouns,
        s7_must_not_regress_disciplined,
        s8_surfaces_concrete,
        s9_out_of_scope_phase_tagged,
        s10_rollback_perf_observability,
    )

    signals = [
        s1_scope_intent_only(body),
        s2_scope_bounded(body),
        s3_criteria_count_adequate(body),
        s4_criteria_atomic(body),
        s5_criteria_executable(body),
        s6_criteria_cover_scope_nouns(body),
        s7_must_not_regress_disciplined(body),
        s8_surfaces_concrete(body),
        s9_out_of_scope_phase_tagged(body),
        s10_rollback_perf_observability(body),
    ]
    total = sum(s.score for s in signals)
    return ContractScore(
        total=total,
        band=band_for(total),
        signals=signals,
    )
