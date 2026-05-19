"""Pre-build CONTRACT artifact per cycle.

A `contract.md` lives at `.agent/project/modules/<module-id>/cycles/<NN>/contract.md`.
It captures the agreed-upon scope, acceptance criteria, and must-not-regress
list BEFORE any code is written for the cycle. Two agents co-author it across
rounds — typically Claude (dev) writes a proposal, Codex (QA) writes a
counter, and they converge over up to `rounds_max` rounds.

dotagent owns:
- the template (Jinja2)
- schema validation (required sections by HTML-comment anchor + criteria checks)
- hash-based diff (sha256 of the contract.md body)
- convergence detection (hash unchanged across actor switch)
- the freeze gate (sets `Contract.status = frozen` + writes an immutable snapshot)

dotagent never writes prose. The agents fill in the body; this module only
renders the empty template and validates the structure.

## Future work (intentionally out of scope for this PR)

- `dotagent project contract unfreeze` — re-open a frozen contract.
- Auto-promotion of `contract → handoff` so `dotagent project handoff` reuses
  the contract body verbatim.
- Bootstrap audit (`dotagent project audit-track`, `audit-bootstrap`).
- `progress.json` materialization for dashboards.
- Anthropic-API-based criteria suggestion during `init`.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Template

from ..identity import resolve
from ..paths import Paths
from .model import Contract, ContractStatus, Cycle, Module


# ---- Constants -------------------------------------------------------------

# Section anchors (stable HTML comments) used both by the template and the
# validator. Re-ordering or renaming any of these is a breaking change for the
# contract — keep this list authoritative.
SECTION_ANCHORS = (
    "scope",
    "acceptance-criteria",
    "must-not-regress",
    "doc-surfaces",
    "out-of-scope",
    "test-plan",
    "uat-proof",
    "rollback-plan",  # added v0.4 — required for migration-bearing cycles, optional placeholder otherwise
    "negotiation-log",
)

# Tokens that may NOT appear in the acceptance-criteria section. Surfacing
# these in a contract means it isn't done.
FORBIDDEN_TOKENS = ("TODO", "FIXME", "xxx", "lorem")

# A criterion must carry at least one "verb-shape" signal — anything that
# marks it as a testable assertion rather than a vague intent. The check is a
# union of four cheap signals; matching ANY of them is sufficient. The breadth
# is deliberate — keyword-only detection trained agents to write "magic word"
# salad rather than natural prose.
VERB_KEYWORDS = (
    # outcomes
    "returns", "equals", "passes", "exits", "redirects", "matches",
    "succeeds", "fails", "errors", "throws", "completes",
    # trajectories
    "stays", "falls", "rises", "exceeds", "meets", "satisfies",
    # set membership
    "contains", "lacks", "includes", "excludes",
    # bounds + positioning
    "within", "outside", "above", "below", "before", "after",
)

# Comparison operators. Bare `=` is intentional: "name = value" is a real
# assertion. Substring-matched on the lowercased criterion text.
COMPARISON_OPERATORS = (
    "==", "!=", "<=", ">=", "≤", "≥", "<", ">", "=",
)

# Numeric threshold paired with a unit. Catches "200ms p95", "30 seconds",
# "99.9%", "10mb", "p99 latency 200ms" etc. without forcing a verb keyword.
# A negative-lookahead in place of `\b` so units that end in a non-word char
# (e.g., `%`) still anchor correctly when followed by whitespace.
_NUMERIC_THRESHOLD_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:ms|sec|secs|seconds?|min|mins|minutes?|"
    r"h|hr|hrs|hours?|kb|mb|gb|tb|%|p\d{2,3}|s)(?![a-zA-Z0-9])",
    re.IGNORECASE,
)

# Concrete test or command references. Implies the criterion can be exercised.
_TEST_COMMAND_RE = re.compile(
    r"\b(?:pytest|npm\s+test|cargo\s+test|go\s+test|make\s+test|"
    r"curl|grep|jq|exit\s+code|sha256|sha1)\b",
    re.IGNORECASE,
)


def _has_verb_shape(criterion: str) -> bool:
    """Return True iff `criterion` carries at least one of the four signals.

    Order: cheap substring checks first; regex last. Short-circuit on first match.
    """
    low = criterion.lower()
    if any(kw in low for kw in VERB_KEYWORDS):
        return True
    if any(op in criterion for op in COMPARISON_OPERATORS):  # ops are case-insensitive already
        return True
    if _NUMERIC_THRESHOLD_RE.search(criterion):
        return True
    if _TEST_COMMAND_RE.search(criterion):
        return True
    return False


# Kept for backward compatibility with anything outside this module that may
# reference the old constant; the validator no longer reads it directly.
VERB_SHAPE_TOKENS = VERB_KEYWORDS + COMPARISON_OPERATORS

MAX_CRITERION_LENGTH = 200
MIN_CRITERIA_COUNT = 3

# Known actor side names. The negotiation log records "by Claude" / "by Codex"
# verbatim regardless of the underlying dotagent identity — these are *roles*,
# not actors.
ACTOR_DEV = "claude"     # dev side; writes the proposal
ACTOR_QA = "codex"       # QA side; writes the counter
KNOWN_ACTORS = (ACTOR_DEV, ACTOR_QA)


# ---- Template --------------------------------------------------------------

# The template carries per-section discipline rules in each blockquote so the
# rubric criteria are visible inline in the file the agents are editing.
# Adding a section here without updating SECTION_ANCHORS is a bug — validate
# will accept a contract missing the new section silently.
_TEMPLATE = """\
# Contract — {{ module_id }} — cycle {{ cycle_n }}

> Pre-build contract. Co-authored by Claude (dev) and Codex (QA) before any
> code is written for this cycle. Converges when both sides leave it
> unchanged for one round. Frozen contracts are immutable. `dotagent project
> contract score <module>` grades the body against a 10-signal rubric
> (max 30); convergence is typically refused below 27.

- **Module:** `{{ module_id }}` — {{ module_name }}
- **Cycle:** {{ cycle_n }}
- **Status:** {{ status }}
- **Round:** {{ round }} / {{ rounds_max }}

<!-- anchor: scope -->
## Scope

> Scope = product intent only. 3-5 bullets. NO file paths, table names,
> constants, or regex patterns here — those go in 'Surfaces touched'.
> (Scored as S1 + S2: max 6 points.)

{{ purpose }}

{% for line in in_scope %}- {{ line }}
{% endfor %}

<!-- anchor: acceptance-criteria -->
## Acceptance criteria

> 8-15 numbered criteria. One assertion per line — no 'X and Y and Z'.
> Each must carry a verb (`returns`, `passes`, `exits`) AND a threshold
> (numeric+unit OR `exit code 0` OR a named test file). Cover every noun
> from Scope. No `TODO` / `FIXME` / `xxx` / `lorem`; ≤200 chars each.
> (Scored as S3 + S4 + S5 + S6: max 12 points.)

{% for c in acceptance_criteria %}{{ loop.index }}. {{ c }}
{% endfor %}

<!-- anchor: must-not-regress -->
## Must not regress

> Each entry: a `DA-BUG-####` / `AP-###` / `F###` id PLUS a guard test filename
> (for example `auth_rotation.test.py`). No prose-only invariants. Greenfield
> modules write `(none — greenfield)` as the single entry.
> (Scored as S7: max 3 points.)

- _(no entries yet — agents to populate)_

<!-- anchor: doc-surfaces -->
## Doc surfaces to update

> Every file, every migration (resolved number — no `NNN` placeholders),
> every test path, every doc surface BY SECTION (`CLAUDE.md §Architecture`,
> not just `CLAUDE.md`). (Scored as S8: max 3 points.)

- _(no entries yet — agents to populate)_

<!-- anchor: out-of-scope -->
## Out of scope

> Numbered list. Each item phase-tagged: `[Phase N]`, `[mNN]`, `[never]`,
> or `[owner-decision]`. Untagged items don't count.
> (Scored as S9: max 3 points.)

{% if out_of_scope %}{% for line in out_of_scope %}- {{ line }}
{% endfor %}{% else %}- _(none specified)_
{% endif %}

<!-- anchor: test-plan -->
## Test plan

> Group by tier: unit / integration / smoke / load (load only if on a
> hot path).

- _(no entries yet — agents to populate)_

<!-- anchor: uat-proof -->
## UAT proof plan

> Each line is a paste-ready command — `curl -i`, `psql -c`, `redis-cli` —
> no prose summaries.

- _(no entries yet — agents to populate)_

<!-- anchor: rollback-plan -->
## Rollback plan

> Required when this cycle includes a migration, schema change, or feature
> flag. Each rollback: the revert command + a smoke test name asserting
> post-revert health. Greenfield / additive-only cycles write
> `(none — additive change only)`. (Part of S10.)

- _(no entries yet — agents to populate)_

<!-- anchor: negotiation-log -->
## Negotiation log

> Append-only audit trail. Each row is one round's write — never edited.
> Maintained by dotagent — agents must not edit lines below this anchor.

- Round 1 proposal by Claude · {{ proposal_hash }} · {{ now }}
"""


# ---- Helpers ---------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z").rsplit(".", 1)[0] + "Z"


def hash_file(path: Path) -> str:
    """Return `sha256:<hex>` of the entire file. Empty string if the file is missing.

    Public utility; what `diff_contract` reports as `hash` in its JSON output —
    the actual on-disk file hash a human can `sha256sum` and verify.
    """
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


_NEGOTIATION_LOG_ANCHOR = "<!-- anchor: negotiation-log -->"


def _content_hash_text(text: str) -> str:
    """sha256:<hex> of the substantive body — everything BEFORE the negotiation log anchor.

    The negotiation log section grows on every `round` call as dotagent appends
    an audit-trail line. If `proposal_hash` / `counter_hash` recorded the full
    file hash, no "re-save unchanged" could ever look unchanged (the log line
    itself is a difference). Hashing only the substantive content makes the
    convergence semantic robust: `proposal_hash == counter_hash` iff both
    actors saw and accepted the same body.
    """
    idx = text.find(_NEGOTIATION_LOG_ANCHOR)
    body = text if idx < 0 else text[:idx]
    h = hashlib.sha256(body.encode("utf-8"))
    return f"sha256:{h.hexdigest()}"


def _content_hash_file(path: Path) -> str:
    if not path.exists():
        return ""
    return _content_hash_text(path.read_text())


def contract_path(paths: Paths, module_id: str, cycle_n: int) -> Path:
    """Canonical path to the contract markdown for a given cycle."""
    return paths.module_cycle_dir(module_id, cycle_n) / "contract.md"


def frozen_snapshot_path(paths: Paths, module_id: str, cycle_n: int) -> Path:
    """Canonical path to the immutable frozen snapshot."""
    return paths.module_cycle_dir(module_id, cycle_n) / "contract.frozen.md"


def resolve_actor_id(paths: Paths) -> str:
    """Best-effort actor identifier for the `frozen_by` field.

    Uses `dotagent identity` if configured; else `$USER`; else `unknown`.
    """
    try:
        ident = resolve(paths.repo)
        if ident and ident.id:
            return ident.id
    except Exception:  # noqa: BLE001 — identity helpers are best-effort here
        pass
    return os.environ.get("USER") or "unknown"


# ---- init ------------------------------------------------------------------

def init_contract(paths: Paths, module: Module) -> Contract:
    """Render `contract.md` for the module's current cycle from its `ModulePlan`.

    Raises if there is no active cycle, if a contract already exists, or if
    the cycle is already frozen.
    """
    if not module.current_cycle:
        raise ValueError(
            f"module {module.id!r} has no active cycle — run `dotagent project start` first"
        )
    cycle: Cycle = module.current_cycle
    target = contract_path(paths, module.id, cycle.n)
    if target.exists():
        raise FileExistsError(
            f"contract already exists at {target} — edit it or "
            f"call `dotagent project contract round` after an agent writes"
        )
    if cycle.contract and cycle.contract.status == ContractStatus.FROZEN:
        raise PermissionError(
            f"cycle {cycle.n} of {module.id} is frozen — `unfreeze` is not yet implemented"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    template = Template(_TEMPLATE)
    body = template.render(
        module_id=module.id,
        module_name=module.name,
        cycle_n=cycle.n,
        status=ContractStatus.PROPOSED,
        round=1,
        rounds_max=3,
        purpose=module.plan.purpose or "_(see PLAN.md)_",
        in_scope=module.plan.in_scope or [],
        out_of_scope=module.plan.out_of_scope or [],
        acceptance_criteria=module.plan.acceptance_criteria or [],
        proposal_hash="sha256:<computed on write>",
        now=_now_iso(),
    )
    target.write_text(body)

    # Record the content hash (substantive body, log section excluded) as
    # `proposal_hash`. The placeholder string in the rendered log line above is
    # irrelevant past this point — the convergence check compares content
    # hashes, not the literal string in the log.
    contract = Contract(
        path=str(target.relative_to(paths.repo)),
        status=ContractStatus.PROPOSED,
        round=1,
        rounds_max=3,
        proposal_hash=_content_hash_file(target),
        last_actor=ACTOR_DEV,
    )
    cycle.contract = contract
    return contract


# ---- validate --------------------------------------------------------------

@dataclass
class ValidationResult:
    ok: bool
    violations: list[str]


_ANCHOR_RE = re.compile(r"<!--\s*anchor:\s*([\w-]+)\s*-->")
# numbered criteria look like "1. xxx" or "12. xxx". Tolerant of leading whitespace.
_CRITERION_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$")


def _split_sections_by_anchor(text: str) -> dict[str, str]:
    """Return {anchor_name: body_after_anchor_until_next_anchor_or_eof}."""
    out: dict[str, str] = {}
    matches = list(_ANCHOR_RE.finditer(text))
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[name] = text[start:end]
    return out


def _parse_criteria(criteria_section: str) -> list[str]:
    """Extract numbered criteria from the acceptance-criteria section body.

    Tolerates the `> blockquote` instruction lines and blank lines between
    items. A criterion is any line matching `^\\s*\\d+\\.\\s+(.+)$`.
    """
    out: list[str] = []
    for line in criteria_section.splitlines():
        if line.lstrip().startswith(">"):
            continue  # skip blockquote instructions
        m = _CRITERION_RE.match(line)
        if m:
            out.append(m.group(2).strip())
    return out


def validate_contract(path: Path) -> ValidationResult:
    """Validate `contract.md` against the schema. Returns a `ValidationResult`."""
    violations: list[str] = []
    if not path.exists():
        return ValidationResult(False, [f"contract file does not exist: {path}"])

    text = path.read_text()

    # 1. all required section anchors present
    sections = _split_sections_by_anchor(text)
    for anchor in SECTION_ANCHORS:
        if anchor not in sections:
            violations.append(f"missing required section anchor: '{anchor}'")

    # 2-4. acceptance-criteria checks
    crit_section = sections.get("acceptance-criteria", "")
    criteria = _parse_criteria(crit_section)
    if len(criteria) < MIN_CRITERIA_COUNT:
        violations.append(
            f"need at least {MIN_CRITERIA_COUNT} numbered acceptance criteria; found {len(criteria)}"
        )
    # Only scan author-written content for forbidden tokens — not the instruction
    # blockquote that may legitimately *name* the forbidden tokens.
    crit_authored = "\n".join(
        line for line in crit_section.splitlines() if not line.lstrip().startswith(">")
    )
    for token in FORBIDDEN_TOKENS:
        if token.lower() in crit_authored.lower():
            violations.append(
                f"acceptance-criteria contains forbidden token {token!r}; "
                f"replace it with the concrete criterion"
            )
    for i, c in enumerate(criteria, 1):
        if len(c) > MAX_CRITERION_LENGTH:
            violations.append(
                f"criterion {i} is {len(c)} chars; max is {MAX_CRITERION_LENGTH}"
            )
        if not _has_verb_shape(c):
            violations.append(
                f"criterion {i} lacks a verb-shape signal — none of: "
                f"a testable verb (e.g., returns / passes / exceeds / stays), "
                f"a comparison operator (==, !=, <=, >=), "
                f"a numeric threshold with unit (e.g., 200ms, p95, 30 seconds), "
                f"or a concrete test/command (pytest, npm test, curl, exit code). "
                f"Rewrite the criterion as a testable assertion."
            )

    return ValidationResult(not violations, violations)


# ---- round ----------------------------------------------------------------

def advance_round(
    paths: Paths,
    module: Module,
    *,
    actor_side: str,
) -> Contract:
    """Record an agent's write to `contract.md`.

    `actor_side` is `"claude"` (dev) or `"codex"` (QA). The round counter
    advances by 1 ONLY if `actor_side` differs from the previous write's
    actor — a same-actor re-save is a refinement of the same round, not a
    new one. The relevant hash field is refreshed either way.
    """
    if actor_side not in KNOWN_ACTORS:
        raise ValueError(
            f"actor_side must be one of {KNOWN_ACTORS}; got {actor_side!r}"
        )
    if not module.current_cycle:
        raise ValueError(f"module {module.id!r} has no active cycle")
    cycle: Cycle = module.current_cycle
    if not cycle.contract:
        raise ValueError(
            f"no contract on cycle {cycle.n} of {module.id} — "
            f"run `dotagent project contract init` first"
        )
    if cycle.contract.status == ContractStatus.FROZEN:
        raise PermissionError(
            f"contract on cycle {cycle.n} of {module.id} is frozen"
        )

    path = paths.repo / cycle.contract.path
    if not path.exists():
        raise FileNotFoundError(f"contract.md missing at {path}")
    new_hash = _content_hash_file(path)

    previous_actor = cycle.contract.last_actor
    if previous_actor and previous_actor != actor_side:
        cycle.contract.round += 1
        cycle.contract.status = ContractStatus.COUNTER

    if actor_side == ACTOR_DEV:
        cycle.contract.proposal_hash = new_hash
    else:
        cycle.contract.counter_hash = new_hash
    cycle.contract.last_actor = actor_side

    # Append-only negotiation log entry. The log line contains the FULL file
    # hash so a human reading the log can `sha256sum contract.md` and find a
    # match against a specific row — but the convergence check up above uses
    # the content hash, which excludes the log section.
    label = "proposal" if actor_side == ACTOR_DEV else "counter"
    name = "Claude" if actor_side == ACTOR_DEV else "Codex"
    file_hash_for_log = hash_file(path)
    log_line = f"- Round {cycle.contract.round} {label} by {name} · {file_hash_for_log} · {_now_iso()}\n"
    body = path.read_text()
    if _NEGOTIATION_LOG_ANCHOR in body:
        body = body.rstrip() + "\n" + log_line
        path.write_text(body)

    return cycle.contract


# ---- diff ------------------------------------------------------------------

@dataclass
class DiffResult:
    path: str
    round: int
    hash: str
    converged: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "round": self.round,
            "hash": self.hash,
            "converged": self.converged,
            "reason": self.reason,
        }


def diff_contract(paths: Paths, module: Module) -> DiffResult:
    """Decide whether the contract has converged across actors.

    Returns a `DiffResult` whose JSON shape is the contract Coda integrates
    against.

    **Hash asymmetry — important for integrators.** The returned `hash` field
    is the full-file sha256 of `contract.md` (a stable identifier for the
    file's current on-disk state). The `converged` field is computed from
    *content* hashes — the file body excluding the auto-appended Negotiation
    log section. Callers should trust `converged` to detect "did the actor
    actually change anything"; they should NOT recompute convergence by
    comparing `hash` values across rounds. The `hash` will always drift
    between rounds because `advance_round` appends a log line on every call;
    that is by design, not a bug.

    Converged means: the substantive body (everything before
    `<!-- anchor: negotiation-log -->`) is byte-identical between what the
    proposing actor most recently wrote and what the countering actor most
    recently wrote — i.e., one side has read and accepted the other side's
    version without modification.
    """
    if not module.current_cycle or not module.current_cycle.contract:
        return DiffResult(path="", round=0, hash="", converged=False, reason="no-contract")
    contract = module.current_cycle.contract
    path = paths.repo / contract.path
    if not path.exists():
        return DiffResult(
            path=contract.path, round=contract.round, hash="",
            converged=False, reason="contract-file-missing",
        )
    # The JSON `hash` field reports the full file hash so the caller (coda)
    # can correlate with a literal `sha256sum contract.md`. Convergence is
    # computed from the content hashes (log-section stripped) so a no-change
    # round survives dotagent's own log append.
    file_hash = hash_file(path)

    if contract.round == 1 and not contract.counter_hash:
        return DiffResult(
            path=contract.path, round=contract.round, hash=file_hash,
            converged=False, reason="first-round",
        )

    both_recorded = bool(contract.proposal_hash and contract.counter_hash)
    if both_recorded and contract.proposal_hash == contract.counter_hash:
        return DiffResult(
            path=contract.path, round=contract.round, hash=file_hash,
            converged=True, reason="hashes-match",
        )

    return DiffResult(
        path=contract.path, round=contract.round, hash=file_hash,
        converged=False, reason="hashes-differ",
    )


# ---- freeze ----------------------------------------------------------------

def freeze_contract(
    paths: Paths,
    module: Module,
    *,
    force: bool = False,
) -> Path:
    """Freeze the contract and write an immutable snapshot.

    Without `--force`, the contract must report `converged=True` from
    `diff_contract`. With `--force`, the freeze proceeds and the snapshot
    records `forced=True`.

    Idempotent: re-freezing an already-frozen contract is a no-op that
    returns the existing snapshot path.
    """
    if not module.current_cycle or not module.current_cycle.contract:
        raise ValueError(f"module {module.id!r} has no contract on its current cycle")
    contract = module.current_cycle.contract
    snapshot = frozen_snapshot_path(paths, module.id, module.current_cycle.n)

    if contract.status == ContractStatus.FROZEN:
        return snapshot  # idempotent

    src = paths.repo / contract.path
    if not src.exists():
        raise FileNotFoundError(f"contract.md missing at {src}")

    if not force:
        validation = validate_contract(src)
        if not validation.ok:
            raise PermissionError(
                "validate refused: " + "; ".join(validation.violations)
                + " — fix the contract or pass --force to override"
            )

    if not force:
        diff = diff_contract(paths, module)
        if not diff.converged:
            raise PermissionError(
                f"contract has not converged (reason={diff.reason!r}); "
                f"pass --force to override"
            )

    # Rollback gate: if the contract triggers the migration signal (S10) AND
    # the rollback plan is empty, refuse to freeze. This catches "we're shipping
    # a schema change with no documented rollback path" — historically a
    # post-incident regret. `--force` overrides.
    if not force:
        from ._signals import has_migration_trigger, s10_rollback_perf_observability
        body_for_score = src.read_text()
        anchor = "<!-- anchor: negotiation-log -->"
        idx = body_for_score.find(anchor)
        substantive = body_for_score if idx < 0 else body_for_score[:idx]
        if has_migration_trigger(substantive):
            s10 = s10_rollback_perf_observability(substantive)
            if s10.score == 0:
                raise PermissionError(
                    "contract has a migration trigger but S10 (rollback / perf / "
                    "observability) scores 0 — populate the rollback plan, or pass "
                    "--force to override"
                )

    body = src.read_text()
    actor = resolve_actor_id(paths)
    contract.status = ContractStatus.FROZEN
    contract.frozen_at = _now_iso()
    contract.frozen_by = actor

    forced_note = "  (forced)" if force else ""
    snapshot_body = (
        f"<!-- frozen at {contract.frozen_at} by {actor}{forced_note} -->\n\n"
        + body.rstrip()
        + "\n"
    )
    snapshot.write_text(snapshot_body)
    try:
        snapshot.chmod(0o444)  # read-only for everyone
    except OSError:
        pass  # best-effort; permission may be denied on some filesystems
    return snapshot
