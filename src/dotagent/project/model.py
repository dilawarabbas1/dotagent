"""Data model for dotagent's project management layer.

Persistence:
- `.agent/project/plan.yaml`      — project-level (name, goal, modules list, tool routing)
- `.agent/project/modules/<id>/module.yaml`  — per-module state + plan structured data

Two-tier on purpose: the project file is small and rarely changes; module files
hold the per-module action history. Editing one module never touches another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..paths import Paths
from ..util import dump_yaml, load_yaml, slugify


# ---- State machine ---------------------------------------------------------

class ModuleState:
    DEFINED = "defined"             # module added but plan not yet built via Q&A
    PLANNED = "planned"             # extensive plan built; dev hasn't started
    IN_PROGRESS = "in_progress"     # dev actively working (cycle N)
    DEV_COMPLETE = "dev_complete"   # dev wrote handoff for cycle N; awaiting QA
    QA_PASSED = "qa_passed"         # latest cycle's QA result is pass; awaiting resolve
    SHIPPED = "shipped"             # explicitly resolved; module is done
    BLOCKED = "blocked"             # sideband; user must `unblock` to continue


ALL_STATES = {
    ModuleState.DEFINED, ModuleState.PLANNED, ModuleState.IN_PROGRESS,
    ModuleState.DEV_COMPLETE, ModuleState.QA_PASSED, ModuleState.SHIPPED,
    ModuleState.BLOCKED,
}


# Allowed transitions: state → set of valid next states.
# (BLOCKED is reachable from any active state and returns to where it came from.)
TRANSITIONS: dict[str, set[str]] = {
    ModuleState.DEFINED:      {ModuleState.PLANNED, ModuleState.BLOCKED},
    ModuleState.PLANNED:      {ModuleState.IN_PROGRESS, ModuleState.BLOCKED},
    # IN_PROGRESS → IN_PROGRESS is allowed: starting a new cycle after a qa-fail.
    ModuleState.IN_PROGRESS:  {ModuleState.IN_PROGRESS, ModuleState.DEV_COMPLETE, ModuleState.BLOCKED},
    # dev-complete can go to either: QA passed, or QA found issues (→ back to in-progress for next cycle)
    ModuleState.DEV_COMPLETE: {ModuleState.QA_PASSED, ModuleState.IN_PROGRESS, ModuleState.BLOCKED},
    ModuleState.QA_PASSED:    {ModuleState.SHIPPED, ModuleState.IN_PROGRESS, ModuleState.BLOCKED},
    ModuleState.SHIPPED:      set(),  # terminal (re-open by editing yaml by hand if needed)
    ModuleState.BLOCKED:      ALL_STATES - {ModuleState.SHIPPED, ModuleState.BLOCKED},
}


def can_transition(from_state: str, to_state: str) -> bool:
    return to_state in TRANSITIONS.get(from_state, set())


# ---- Per-cycle records ------------------------------------------------------

class ContractStatus:
    """Lifecycle states for the per-cycle pre-build contract artifact.

    Mirrors `ModuleState` shape (class with string constants) rather than `Enum`,
    consistent with the rest of this module.
    """

    PROPOSED = "proposed"   # initial contract.md written; round=1
    COUNTER = "counter"     # opposing actor has produced a counter-version
    FROZEN = "frozen"       # contract has converged; immutable for this cycle


CONTRACT_STATES = {
    ContractStatus.PROPOSED, ContractStatus.COUNTER, ContractStatus.FROZEN,
}


@dataclass
class Contract:
    """Pre-build contract attached to a `Cycle`.

    The markdown body lives at `path` (relative to repo root). dotagent owns
    only the schema and lifecycle metadata; the prose is authored by Claude
    (dev) and Codex (QA) across negotiation rounds.

    Convergence is detected when the file hash is unchanged between an actor's
    write and the next actor's read (see `dotagent project contract diff`).
    """

    path: str = ""                                    # repo-relative path to contract.md
    status: str = ContractStatus.PROPOSED
    round: int = 1                                    # 1-based; advances when the *other* actor writes
    rounds_max: int = 3
    proposal_hash: str = ""                           # sha256:<hex> of the most-recent Claude (dev) write
    counter_hash: str = ""                            # sha256:<hex> of the most-recent Codex (QA) write
    frozen_at: str = ""                               # ISO timestamp set on freeze()
    frozen_by: str = ""                               # actor id who froze the contract
    last_actor: str = ""                              # actor of the most recent `round` call

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "status": self.status,
            "round": self.round,
            "rounds_max": self.rounds_max,
            "proposal_hash": self.proposal_hash,
            "counter_hash": self.counter_hash,
            "frozen_at": self.frozen_at,
            "frozen_by": self.frozen_by,
            "last_actor": self.last_actor,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "Contract | None":
        if not d:
            return None
        return cls(
            path=d.get("path", ""),
            status=d.get("status", ContractStatus.PROPOSED),
            round=int(d.get("round", 1)),
            rounds_max=int(d.get("rounds_max", 3)),
            proposal_hash=d.get("proposal_hash", ""),
            counter_hash=d.get("counter_hash", ""),
            frozen_at=d.get("frozen_at", ""),
            frozen_by=d.get("frozen_by", ""),
            last_actor=d.get("last_actor", ""),
        )


@dataclass
class QAResult:
    cycle: int
    passed: bool
    rationale: str = ""
    findings_path: str = ""     # relative to repo root
    recorded_at: str = ""
    recorded_by: str = ""       # actor id

    def to_dict(self) -> dict:
        return {
            "cycle": self.cycle, "passed": self.passed,
            "rationale": self.rationale, "findings_path": self.findings_path,
            "recorded_at": self.recorded_at, "recorded_by": self.recorded_by,
        }


@dataclass
class Cycle:
    n: int                      # 1-based
    started_at: str = ""        # when dev started this cycle
    start_sha: str = ""         # git HEAD at cycle start (for diff scope)
    handoff_at: str = ""        # when dev-handoff.md was written
    handoff_sha: str = ""       # git HEAD at handoff
    files_changed: list[str] = field(default_factory=list)
    qa_result: QAResult | None = None
    contract: Contract | None = None    # pre-build artifact; populated by `contract init`

    def to_dict(self) -> dict:
        d = {
            "n": self.n,
            "started_at": self.started_at, "start_sha": self.start_sha,
            "handoff_at": self.handoff_at, "handoff_sha": self.handoff_sha,
            "files_changed": self.files_changed,
        }
        if self.qa_result:
            d["qa_result"] = self.qa_result.to_dict()
        # New in v0.4: appended at end so existing YAML round-trips stay backward-compatible.
        if self.contract:
            d["contract"] = self.contract.to_dict()
        return d


# ---- Plan structure (built by the scope-builder Q&A) -----------------------

@dataclass
class ModulePlan:
    purpose: str = ""
    in_scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)   # module ids
    technical_approach: str = ""
    risks: list[str] = field(default_factory=list)
    estimated_effort: str = ""

    def to_dict(self) -> dict:
        return {
            "purpose": self.purpose,
            "in_scope": self.in_scope, "out_of_scope": self.out_of_scope,
            "acceptance_criteria": self.acceptance_criteria,
            "dependencies": self.dependencies,
            "technical_approach": self.technical_approach,
            "risks": self.risks,
            "estimated_effort": self.estimated_effort,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "ModulePlan":
        d = d or {}
        return cls(
            purpose=d.get("purpose", ""),
            in_scope=list(d.get("in_scope") or []),
            out_of_scope=list(d.get("out_of_scope") or []),
            acceptance_criteria=list(d.get("acceptance_criteria") or []),
            dependencies=list(d.get("dependencies") or []),
            technical_approach=d.get("technical_approach", ""),
            risks=list(d.get("risks") or []),
            estimated_effort=d.get("estimated_effort", ""),
        )


# ---- Per-module record ------------------------------------------------------

@dataclass
class Module:
    id: str                          # auto-generated, e.g. "01-auth-service"
    name: str                        # human title
    state: str = ModuleState.DEFINED
    created_at: str = ""
    updated_at: str = ""
    plan: ModulePlan = field(default_factory=ModulePlan)
    cycles: list[Cycle] = field(default_factory=list)
    blocked_reason: str = ""
    pre_block_state: str = ""        # so `unblock` restores correctly
    # PR #6 — traceability fields
    implements_features: list[str] = field(default_factory=list)  # FEAT-NN ids
    cross_module: str = ""                                         # for cross-service slices
    # per-module tool overrides
    tools: dict = field(default_factory=dict)

    @property
    def current_cycle(self) -> Cycle | None:
        return self.cycles[-1] if self.cycles else None

    @property
    def cycle_count(self) -> int:
        return len(self.cycles)

    @property
    def last_qa_result(self) -> QAResult | None:
        for c in reversed(self.cycles):
            if c.qa_result is not None:
                return c.qa_result
        return None

    def acceptance_progress(self) -> tuple[int, int]:
        """Returns (met, total). For now, all unmet until shipped; future: per-criterion tracking."""
        total = len(self.plan.acceptance_criteria)
        met = total if self.state == ModuleState.SHIPPED else 0
        return met, total

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "state": self.state,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "plan": self.plan.to_dict(),
            "cycles": [c.to_dict() for c in self.cycles],
            "blocked_reason": self.blocked_reason,
            "pre_block_state": self.pre_block_state,
            "tools": self.tools,
            "implements_features": list(self.implements_features),
            "cross_module": self.cross_module,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Module":
        cycles: list[Cycle] = []
        for cd in d.get("cycles") or []:
            qa = cd.get("qa_result")
            qa_obj = QAResult(**qa) if qa else None
            cycles.append(Cycle(
                n=cd["n"],
                started_at=cd.get("started_at", ""), start_sha=cd.get("start_sha", ""),
                handoff_at=cd.get("handoff_at", ""), handoff_sha=cd.get("handoff_sha", ""),
                files_changed=list(cd.get("files_changed") or []),
                qa_result=qa_obj,
                contract=Contract.from_dict(cd.get("contract")),
            ))
        return cls(
            id=d.get("id") or "",
            name=d.get("name") or d.get("id") or "",
            state=d.get("state", ModuleState.DEFINED),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            plan=ModulePlan.from_dict(d.get("plan")),
            cycles=cycles,
            blocked_reason=d.get("blocked_reason", ""),
            pre_block_state=d.get("pre_block_state", ""),
            tools=d.get("tools") or {},
            implements_features=list(d.get("implements_features") or []),
            cross_module=d.get("cross_module", ""),
        )


# ---- Project-level record ---------------------------------------------------

@dataclass
class Project:
    name: str
    goal: str = ""
    description: str = ""
    out_of_scope: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    stakeholders: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    module_ids: list[str] = field(default_factory=list)   # ordered list (for index assignment)
    tools: dict = field(default_factory=dict)             # defaults per role

    # PR #6 — brief traceability fields
    brief: str = ""                                                # path to project_brief.md
    brief_version: int = 0
    brief_objectives_covered: list[str] = field(default_factory=list)
    brief_features_covered: list[str] = field(default_factory=list)
    features_to_modules: dict[str, list[str]] = field(default_factory=dict)
    # PR #12: cross-repo manifest. Each entry: {id, path, remote?, default_branch?, role?}
    repos: list[dict] = field(default_factory=list)

    # transient: loaded modules
    modules: dict[str, Module] = field(default_factory=dict)

    def to_dict(self) -> dict:
        # NOTE: modules are persisted separately; plan.yaml carries only the ordered id list.
        return {
            "name": self.name, "goal": self.goal,
            "description": self.description,
            "out_of_scope": self.out_of_scope,
            "success_criteria": self.success_criteria,
            "stakeholders": self.stakeholders,
            "constraints": self.constraints,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "module_ids": self.module_ids,
            "tools": self.tools,
            "brief": self.brief,
            "brief_version": self.brief_version,
            "brief_objectives_covered": list(self.brief_objectives_covered),
            "brief_features_covered": list(self.brief_features_covered),
            "features_to_modules": dict(self.features_to_modules),
            "repos": [dict(r) for r in self.repos],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        return cls(
            # Tolerate plan.yaml files without an explicit `name:` (the new
            # layered-tier shape sometimes omits it because the manifest
            # has its own per-repo names). Empty string is fine — callers
            # fall back to the directory name when rendering.
            name=d.get("name") or "",
            goal=d.get("goal", ""),
            description=d.get("description", ""),
            out_of_scope=list(d.get("out_of_scope") or []),
            success_criteria=list(d.get("success_criteria") or []),
            stakeholders=list(d.get("stakeholders") or []),
            constraints=list(d.get("constraints") or []),
            created_at=d.get("created_at", ""), updated_at=d.get("updated_at", ""),
            module_ids=list(d.get("module_ids") or []),
            tools=d.get("tools") or {},
            brief=d.get("brief", ""),
            brief_version=int(d.get("brief_version") or 0),
            brief_objectives_covered=list(d.get("brief_objectives_covered") or []),
            brief_features_covered=list(d.get("brief_features_covered") or []),
            features_to_modules=dict(d.get("features_to_modules") or {}),
            repos=[dict(r) for r in (d.get("repos") or [])],
        )


# ---- Persistence ------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_project(paths: Paths) -> Project | None:
    """Load the project plan + every module from disk. Returns None if no project initialized."""
    if not paths.project_plan.exists():
        return None
    data = load_yaml(paths.project_plan)
    project = Project.from_dict(data)
    if paths.project_modules.exists():
        for mid in project.module_ids:
            myaml = paths.module_yaml(mid)
            if myaml.exists():
                project.modules[mid] = Module.from_dict(load_yaml(myaml))
    return project


def save_project(paths: Paths, project: Project) -> None:
    """Persist project + all modules. Updates `updated_at` timestamps."""
    project.updated_at = _now()
    paths.project_dir.mkdir(parents=True, exist_ok=True)
    dump_yaml(paths.project_plan, project.to_dict())
    for mid, mod in project.modules.items():
        mod.updated_at = _now()
        paths.module_dir(mid).mkdir(parents=True, exist_ok=True)
        dump_yaml(paths.module_yaml(mid), mod.to_dict())


def save_module(paths: Paths, module: Module) -> None:
    """Persist a single module (cheaper than save_project)."""
    module.updated_at = _now()
    paths.module_dir(module.id).mkdir(parents=True, exist_ok=True)
    dump_yaml(paths.module_yaml(module.id), module.to_dict())


def next_module_id(project: Project, name: str) -> str:
    """Generate `NN-slug` where NN is the next index (zero-padded)."""
    idx = len(project.module_ids) + 1
    return f"{idx:02d}-{slugify(name)}"


def now() -> str:
    return _now()
