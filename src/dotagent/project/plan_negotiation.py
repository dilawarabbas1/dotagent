"""Plan negotiation primitives — pure data-layer.

Mirrors the contract negotiation pattern. dotagent stores drafts, advances
rounds, computes convergence via content hash, and freezes; it does NOT
invoke any LLM. An orchestrator (Coda, a script, a human) drives the loop:

  1. Read brief + current draft + repos manifest.
  2. Generate a new draft (any way — LLM, hand, scripted).
  3. Call `dotagent project plan write-draft --actor <name> --from-stdin`
     OR `dotagent project plan write-review --actor <name> --from-stdin --rationale "..."`
  4. Check `dotagent project plan converged`.
  5. Loop until converged, then `dotagent project plan freeze`.

`--actor` is opaque to dotagent. Any two distinct strings advance rounds;
two consecutive writes by the same actor refine the same round.

File layout:

  .agent/project/
  ├── plan.yaml                            ← in-effect (after freeze)
  ├── plan.frozen.yaml                     ← snapshot from last freeze
  └── plan-negotiations/
      └── 01/                              ← current session
          ├── plan.draft.yaml              ← live working doc
          ├── negotiation-log.md           ← append-only history
          └── rounds/
              ├── 01-<actor>.yaml          ← immutable per-round snapshot
              └── 02-<actor>.yaml
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..paths import Paths


@dataclass
class Round:
    """One round in the negotiation log."""
    n: int
    actor: str
    written_at: str
    content_hash: str
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "n": self.n, "actor": self.actor,
            "written_at": self.written_at,
            "content_hash": self.content_hash,
            "rationale": self.rationale,
        }


@dataclass
class NegotiationState:
    """Snapshot of the current session's state."""
    session_n: int
    current_round: int
    last_actor: str
    last_hash: str
    converged: bool
    converged_reason: str = ""
    rounds: list[Round] = None

    def __post_init__(self):
        if self.rounds is None:
            self.rounds = []

    def to_dict(self) -> dict:
        return {
            "session_n": self.session_n,
            "current_round": self.current_round,
            "last_actor": self.last_actor,
            "last_hash": self.last_hash,
            "converged": self.converged,
            "converged_reason": self.converged_reason,
            "rounds": [r.to_dict() for r in self.rounds],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def current_session_n(paths: Paths) -> int:
    """Highest existing session number, or 1 if none."""
    base = paths.plan_negotiations_dir
    if not base.exists():
        return 1
    nums: list[int] = []
    for child in base.iterdir():
        if child.is_dir() and child.name.isdigit():
            nums.append(int(child.name))
    return max(nums) if nums else 1


def write_draft(
    paths: Paths,
    actor: str,
    content: str,
    *,
    rationale: str = "",
    is_review: bool = False,
) -> NegotiationState:
    """Write a new draft from `actor`. Returns the post-write state.

    Rules:
    - If `actor` differs from the previous round's actor, increments the
      round counter; same actor = round-refinement (counter unchanged).
    - If `is_review` is True, `rationale` is required (mirrors contract
      `qa-record` discipline).
    - Validates the YAML parses before writing.
    """
    actor = (actor or "").strip()
    if not actor:
        raise ValueError("actor is required (any non-empty string)")
    if is_review and not (rationale or "").strip():
        raise ValueError("review requires a non-empty --rationale")

    _validate_yaml(content)

    n = current_session_n(paths)
    session_dir = paths.plan_negotiation_session_dir(n)
    session_dir.mkdir(parents=True, exist_ok=True)

    log_path = paths.plan_negotiation_log(n)
    state = _read_state(paths, n)

    if state.last_actor and state.last_actor == actor:
        new_round = state.current_round
    else:
        new_round = state.current_round + 1 if state.rounds else 1

    written_at = _utc_now_iso()
    content_hash = _content_hash(content)

    # Write the live draft
    paths.plan_draft_path(n).write_text(content)

    # Write the immutable per-round snapshot
    rounds_dir = paths.plan_round_dir(n)
    rounds_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = rounds_dir / f"{new_round:02d}-{actor}.yaml"
    snapshot_path.write_text(content)

    # Append to negotiation log
    _append_log(log_path, Round(
        n=new_round, actor=actor, written_at=written_at,
        content_hash=content_hash, rationale=rationale,
    ), is_review=is_review)

    return _read_state(paths, n)


def diff(paths: Paths, n: int | None = None) -> dict:
    """Return a structural diff between the last two rounds (different actors)."""
    n = n or current_session_n(paths)
    state = _read_state(paths, n)
    if len(state.rounds) < 2:
        return {"status": "no-prior-round", "rounds": len(state.rounds)}
    # Find the last two distinct actors
    last = state.rounds[-1]
    prev = next((r for r in reversed(state.rounds[:-1]) if r.actor != last.actor), None)
    if prev is None:
        return {"status": "no-prior-counter", "rounds": len(state.rounds)}
    return {
        "status": "ok",
        "from": prev.to_dict(),
        "to": last.to_dict(),
        "hash_match": prev.content_hash == last.content_hash,
    }


def is_converged(paths: Paths, n: int | None = None) -> bool:
    """True iff the two most-recent rounds from different actors hash-match."""
    n = n or current_session_n(paths)
    state = _read_state(paths, n)
    return state.converged


def read_state(paths: Paths, n: int | None = None) -> NegotiationState:
    """Public access to the parsed negotiation state."""
    n = n or current_session_n(paths)
    return _read_state(paths, n)


def freeze(
    paths: Paths,
    *,
    force: bool = False,
    rationale: str = "",
) -> Path:
    """Promote the converged draft to plan.yaml. Returns the frozen-snapshot path.

    Without `--force`, refuses if not converged. With `--force`, records
    `rationale` in the log.
    """
    n = current_session_n(paths)
    state = _read_state(paths, n)

    if not state.converged:
        if not force:
            raise PermissionError(
                f"plan negotiation has not converged (reason: "
                f"{state.converged_reason!r}); pass --force to override"
            )
        if not (rationale or "").strip():
            raise ValueError("--force freeze requires --rationale")

    draft = paths.plan_draft_path(n)
    if not draft.exists():
        raise FileNotFoundError(f"no plan draft at {draft}")
    body = draft.read_text()

    paths.project_dir.mkdir(parents=True, exist_ok=True)
    paths.project_plan.write_text(body)

    frozen_at = _utc_now_iso()
    forced_note = f" (forced: {rationale.strip()})" if force else ""
    snapshot_body = (
        f"# frozen at {frozen_at}{forced_note}\n"
        + body.rstrip()
        + "\n"
    )
    paths.plan_frozen.write_text(snapshot_body)
    try:
        paths.plan_frozen.chmod(0o444)
    except OSError:
        pass

    # Append a freeze marker to the negotiation log
    log_path = paths.plan_negotiation_log(n)
    if log_path.exists():
        with log_path.open("a") as fh:
            fh.write(
                f"\n## Frozen at {frozen_at}"
                + (f" (forced: {rationale.strip()})" if force else "")
                + "\n"
            )

    return paths.plan_frozen


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _validate_yaml(content: str) -> None:
    """Refuse non-YAML content. Doesn't enforce a schema — just parseability."""
    try:
        yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f"draft is not valid YAML: {exc}") from exc


def _read_state(paths: Paths, n: int) -> NegotiationState:
    """Reconstruct state from the per-round snapshots + log."""
    log_path = paths.plan_negotiation_log(n)
    rounds: list[Round] = []
    if log_path.exists():
        rounds = _parse_log(log_path.read_text())

    if not rounds:
        return NegotiationState(
            session_n=n, current_round=0,
            last_actor="", last_hash="",
            converged=False, converged_reason="no rounds yet",
        )

    last = rounds[-1]
    prev = next((r for r in reversed(rounds[:-1]) if r.actor != last.actor), None)
    if prev is None:
        return NegotiationState(
            session_n=n, current_round=last.n,
            last_actor=last.actor, last_hash=last.content_hash,
            converged=False, converged_reason="first-round",
            rounds=rounds,
        )
    if prev.content_hash == last.content_hash:
        return NegotiationState(
            session_n=n, current_round=last.n,
            last_actor=last.actor, last_hash=last.content_hash,
            converged=True, converged_reason="hashes-match",
            rounds=rounds,
        )
    return NegotiationState(
        session_n=n, current_round=last.n,
        last_actor=last.actor, last_hash=last.content_hash,
        converged=False, converged_reason="hashes-differ",
        rounds=rounds,
    )


# Negotiation-log format (one round per markdown bullet):
#
#   ## Negotiation log
#
#   - Round 1 (proposal by planner) · sha256:abcd1234 · 2026-05-20T10:00:00Z
#   - Round 2 (review by qa) · sha256:beef5678 · 2026-05-20T10:05:00Z · rationale: ...
#

def _append_log(log_path: Path, round_obj: Round, *, is_review: bool) -> None:
    """Append one round line to the log. Creates the file if missing."""
    role = "review" if is_review else "proposal"
    line = (
        f"- Round {round_obj.n} ({role} by {round_obj.actor}) · "
        f"{round_obj.content_hash} · {round_obj.written_at}"
    )
    if round_obj.rationale:
        line += f" · rationale: {round_obj.rationale}"
    line += "\n"
    if log_path.exists():
        body = log_path.read_text()
        if not body.endswith("\n"):
            body += "\n"
        body += line
    else:
        body = (
            "<!-- Plan negotiation log. Append-only. -->\n"
            "## Negotiation log\n\n"
            + line
        )
    log_path.write_text(body)


_LOG_LINE_RE = __import__("re").compile(
    r"^- Round (?P<n>\d+) \((?P<role>proposal|review) by (?P<actor>[^)]+)\) · "
    r"(?P<hash>\S+) · (?P<ts>\S+)(?: · rationale: (?P<rationale>.+))?\s*$"
)


def _parse_log(text: str) -> list[Round]:
    rounds: list[Round] = []
    for line in text.splitlines():
        m = _LOG_LINE_RE.match(line.strip())
        if not m:
            continue
        rounds.append(Round(
            n=int(m.group("n")),
            actor=m.group("actor"),
            written_at=m.group("ts"),
            content_hash=m.group("hash"),
            rationale=(m.group("rationale") or "").strip(),
        ))
    return rounds


__all__ = (
    "Round", "NegotiationState",
    "current_session_n",
    "write_draft", "diff", "is_converged", "read_state", "freeze",
)
