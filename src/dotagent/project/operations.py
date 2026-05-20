"""High-level operations that drive the module state machine.

Every operation:
1. Validates the current state.
2. Updates the module record.
3. Writes the relevant document (handoff / findings / completion).
4. Persists.
5. Records an episodic event so visibility/auto-dream pick it up.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..identity import host, new_session_id, resolve
from ..memory import EpisodicEvent, EpisodicMemory, WorkingMemory
from ..paths import Paths
from ..util import write_text
from .handoff import (
    current_sha,
    files_changed_since,
    qa_findings_template,
    render_completion,
    render_dev_handoff,
    render_module_plan,
    render_scope,
)
from .model import (
    Cycle,
    Module,
    ModuleState,
    Project,
    QAResult,
    can_transition,
    load_project,
    next_module_id,
    now,
    save_module,
    save_project,
)


class ProjectError(Exception):
    """Raised when an operation violates the state machine or finds the project missing."""


# ---- Project init / add-module ---------------------------------------------

def init_project(paths: Paths, project: Project) -> None:
    """Persist a freshly-built project (from the scope builder)."""
    save_project(paths, project)
    write_text(paths.project_scope_md, render_scope(project))
    _record_event(paths, kind="project_init", summary=f"project '{project.name}' initialized")


def add_module(paths: Paths, project: Project, module: Module) -> None:
    """Attach a module (with its built plan) to the project. State starts as PLANNED."""
    if module.id in project.modules:
        raise ProjectError(f"module {module.id} already exists")
    module.state = ModuleState.PLANNED
    module.created_at = module.created_at or now()
    project.modules[module.id] = module
    if module.id not in project.module_ids:
        project.module_ids.append(module.id)
    save_project(paths, project)
    paths.module_dir(module.id).mkdir(parents=True, exist_ok=True)
    save_module(paths, module)
    write_text(paths.module_plan_md(module.id), render_module_plan(module))
    write_text(paths.project_scope_md, render_scope(project))
    _record_event(paths, kind="module_added",
                  summary=f"module {module.id} ({module.name}) planned")
    # Auto-regenerate downstream indexes
    try:
        from .contracts_index import regenerate as _regen_contracts
        from .brief import regenerate_brief_modules
        _regen_contracts(paths, project)
        regenerate_brief_modules(paths)
    except Exception as exc:  # noqa: BLE001
        from ..logging import log_exception
        log_exception("add_module index regen failed", exc)


# ---- State transitions ------------------------------------------------------

def start_module(paths: Paths, project: Project, module_id: str) -> Module:
    mod = _require_module(project, module_id)
    if not can_transition(mod.state, ModuleState.IN_PROGRESS):
        raise ProjectError(f"cannot start module from state '{mod.state}'")
    # if currently planned or qa-passed back-to-fix etc.
    # Open a new cycle (first cycle if none yet)
    cycle_n = mod.cycle_count + (0 if (mod.cycles and mod.current_cycle.handoff_at == "") else 1)
    if cycle_n == 0:
        cycle_n = 1
    # If we're starting fresh OR after a qa-fail, append a new cycle.
    if not mod.cycles or mod.current_cycle.handoff_at != "":
        mod.cycles.append(Cycle(n=len(mod.cycles) + 1, started_at=now(), start_sha=current_sha(paths.repo)))
    mod.state = ModuleState.IN_PROGRESS
    save_module(paths, mod)
    # set working memory task
    identity = resolve(paths.repo)
    WorkingMemory(paths, identity.id).set_task(f"{mod.id}: {mod.name}")
    _record_event(paths, kind="module_started",
                  summary=f"started cycle {mod.current_cycle.n} of {mod.id}",
                  files=[])
    return mod


def handoff_to_qa(paths: Paths, project: Project, module_id: str, *, dev_notes: str = "") -> Module:
    mod = _require_module(project, module_id)
    if not can_transition(mod.state, ModuleState.DEV_COMPLETE):
        raise ProjectError(f"cannot hand off from state '{mod.state}' — run `start` first")
    if not mod.current_cycle:
        raise ProjectError("no active cycle — run `start` first")

    cycle = mod.current_cycle
    cycle.handoff_at = now()
    cycle.handoff_sha = current_sha(paths.repo)
    cycle.files_changed = files_changed_since(paths.repo, cycle.start_sha) if cycle.start_sha else []

    paths.module_cycle_dir(mod.id, cycle.n).mkdir(parents=True, exist_ok=True)
    doc_path = paths.module_cycle_dir(mod.id, cycle.n) / "dev-handoff.md"
    write_text(doc_path, render_dev_handoff(project, mod, cycle, repo=paths.repo, dev_notes=dev_notes))
    # also stash files-changed.txt for quick inspection
    write_text(paths.module_cycle_dir(mod.id, cycle.n) / "files-changed.txt",
               "\n".join(cycle.files_changed) + ("\n" if cycle.files_changed else ""))

    mod.state = ModuleState.DEV_COMPLETE
    save_module(paths, mod)
    _record_event(paths, kind="module_handoff",
                  summary=f"{mod.id} → QA (cycle {cycle.n})",
                  files=cycle.files_changed[:50])
    return mod


def record_qa(
    paths: Paths,
    project: Project,
    module_id: str,
    *,
    passed: bool,
    rationale: str,
    findings_path: str = "",
) -> Module:
    if not rationale or not rationale.strip():
        raise ProjectError("rationale is required (pass or fail) — non-negotiable")
    mod = _require_module(project, module_id)
    target_state = ModuleState.QA_PASSED if passed else ModuleState.IN_PROGRESS
    if not can_transition(mod.state, target_state):
        raise ProjectError(f"cannot record QA from state '{mod.state}'")
    if not mod.current_cycle:
        raise ProjectError("no active cycle to record QA against")

    identity = resolve(paths.repo)
    cycle = mod.current_cycle
    cycle.qa_result = QAResult(
        cycle=cycle.n, passed=passed, rationale=rationale,
        findings_path=findings_path, recorded_at=now(), recorded_by=identity.id,
    )

    # If findings_path not provided + fail, stub a findings template the dev tool can pick up.
    if not passed:
        cdir = paths.module_cycle_dir(mod.id, cycle.n)
        cdir.mkdir(parents=True, exist_ok=True)
        target = cdir / "qa-findings.md"
        if not target.exists():
            write_text(target, qa_findings_template(mod, cycle))
        cycle.qa_result.findings_path = str(target.relative_to(paths.repo))

    mod.state = target_state
    save_module(paths, mod)
    _record_event(paths, kind=("qa_pass" if passed else "qa_fail"),
                  summary=f"{mod.id} cycle {cycle.n}: {'pass' if passed else 'fail'} — {rationale[:120]}")
    return mod


def resolve_module(paths: Paths, project: Project, module_id: str, *, rationale: str = "") -> Module:
    mod = _require_module(project, module_id)
    if not can_transition(mod.state, ModuleState.SHIPPED):
        raise ProjectError(f"cannot resolve from state '{mod.state}' — QA must pass first")
    last = mod.last_qa_result
    if not last or not last.passed:
        raise ProjectError("the latest QA result must be `pass` before resolving")
    mod.state = ModuleState.SHIPPED
    save_module(paths, mod)
    write_text(paths.module_completion(mod.id), render_completion(project, mod))
    _record_event(paths, kind="module_shipped",
                  summary=f"{mod.id} shipped after {mod.cycle_count} cycle(s){' — ' + rationale if rationale else ''}")
    return mod


def block_module(paths: Paths, project: Project, module_id: str, reason: str) -> Module:
    if not reason.strip():
        raise ProjectError("reason is required to block a module")
    mod = _require_module(project, module_id)
    if mod.state == ModuleState.SHIPPED:
        raise ProjectError("cannot block a shipped module")
    if mod.state == ModuleState.BLOCKED:
        raise ProjectError("module is already blocked")
    mod.pre_block_state = mod.state
    mod.state = ModuleState.BLOCKED
    mod.blocked_reason = reason
    save_module(paths, mod)
    _record_event(paths, kind="module_blocked", summary=f"{mod.id} blocked: {reason[:160]}")
    return mod


def unblock_module(paths: Paths, project: Project, module_id: str) -> Module:
    mod = _require_module(project, module_id)
    if mod.state != ModuleState.BLOCKED:
        raise ProjectError("module is not blocked")
    restored = mod.pre_block_state or ModuleState.PLANNED
    mod.state = restored
    mod.blocked_reason = ""
    mod.pre_block_state = ""
    save_module(paths, mod)
    _record_event(paths, kind="module_unblocked", summary=f"{mod.id} unblocked → {restored}")
    return mod


# ---- Status / queries -------------------------------------------------------

def project_status(project: Project) -> dict:
    """Aggregate status. Source of truth for project completion."""
    by_state: dict[str, list[str]] = {}
    for mid in project.module_ids:
        mod = project.modules.get(mid)
        if not mod:
            continue
        by_state.setdefault(mod.state, []).append(mid)
    total = len([m for m in project.modules.values() if m.state != ModuleState.BLOCKED])
    shipped = len([m for m in project.modules.values() if m.state == ModuleState.SHIPPED])
    pct = (shipped / total * 100) if total else 0.0
    return {
        "name": project.name,
        "modules_total": len(project.modules),
        "shipped": shipped,
        "blocked": len(by_state.get(ModuleState.BLOCKED, [])),
        "percent_complete": pct,
        "by_state": by_state,
    }


def next_recommended_module(project: Project) -> str | None:
    """Pick the next module whose dependencies are all shipped + isn't blocked."""
    shipped: set[str] = {m.id for m in project.modules.values() if m.state == ModuleState.SHIPPED}
    for mid in project.module_ids:
        mod = project.modules.get(mid)
        if not mod or mod.state in (ModuleState.SHIPPED, ModuleState.BLOCKED):
            continue
        deps_ok = all(d in shipped for d in mod.plan.dependencies)
        if deps_ok:
            return mid
    return None


def require_project(paths: Paths) -> Project:
    project = load_project(paths)
    if project is None:
        raise ProjectError(
            "No project found. Run `dotagent project init` first."
        )
    return project


# ---- internals --------------------------------------------------------------

def _require_module(project: Project, module_id: str) -> Module:
    if module_id not in project.modules:
        raise ProjectError(f"unknown module '{module_id}'. Run `dotagent project list` to see modules.")
    return project.modules[module_id]


def _record_event(paths: Paths, *, kind: str, summary: str, files: list[str] | None = None) -> None:
    """Record an episodic event so visibility + auto-dream pick it up."""
    try:
        identity = resolve(paths.repo)
        ev = EpisodicEvent(
            ts=EpisodicMemory.now(),
            actor=identity.id, tool="dotagent_project",
            host=host(), session=new_session_id(),
            kind=kind, repo=paths.repo.name, branch="",
            files=files or [], summary=summary,
        )
        EpisodicMemory(paths).append(ev)
    except Exception as e:
        from ..logging import log_exception
        log_exception(f"project event {kind!r} record failed", e)
