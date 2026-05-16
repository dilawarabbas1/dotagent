from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dotagent.config import Config, merge_defaults
from dotagent.context import build as build_context
from dotagent.paths import Paths
from dotagent.project import Module, ModuleState, Project, load_project, save_project
from dotagent.project.handoff import (
    detect_test_commands,
    qa_findings_template,
    render_completion,
    render_dev_handoff,
    render_module_plan,
    render_scope,
)
from dotagent.project.model import Cycle, ModulePlan, can_transition, next_module_id, now
from dotagent.project.operations import (
    ProjectError,
    add_module,
    block_module,
    handoff_to_qa,
    init_project,
    next_recommended_module,
    project_status,
    record_qa,
    resolve_module,
    start_module,
    unblock_module,
)
from dotagent.scaffold import scaffold_agent_dir
from dotagent.util import dump_yaml


def _setup(tmp_path: Path) -> Paths:
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "demo"}}))
    return paths


def _init_git(repo: Path) -> None:
    # No commit — `current_sha()` tolerates empty HEAD; `files_changed_since("")` returns [].
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)


def _make_project(name: str = "AI Portal") -> Project:
    return Project(
        name=name,
        goal="Ship the new portal",
        description="Customer-facing portal v2",
        success_criteria=["users can log in", "MFA works"],
        created_at=now(),
        module_ids=[],
        tools={
            "development": {"tool": "claude_code", "model": "claude-opus-4-7"},
            "qa":          {"tool": "claude_code", "model": "claude-sonnet-4-6"},
            "review":      {"tool": "claude_code", "model": ""},
            "planning":    {"tool": "claude_code", "model": ""},
        },
    )


def _make_module(project: Project, name: str, plan: ModulePlan | None = None) -> Module:
    plan = plan or ModulePlan(
        purpose=f"Build {name}",
        in_scope=["thing one", "thing two"],
        acceptance_criteria=["does X", "verifies Y"],
        technical_approach="straightforward",
    )
    return Module(id=next_module_id(project, name), name=name, plan=plan, created_at=now())


# ---- model + persistence ----------------------------------------------------

def test_save_and_load_project_round_trip(tmp_path: Path):
    paths = _setup(tmp_path)
    project = _make_project()
    init_project(paths, project)
    mod = _make_module(project, "Auth Service")
    add_module(paths, project, mod)

    reloaded = load_project(paths)
    assert reloaded is not None
    assert reloaded.name == "AI Portal"
    assert mod.id in reloaded.module_ids
    assert reloaded.modules[mod.id].plan.acceptance_criteria == ["does X", "verifies Y"]
    assert reloaded.modules[mod.id].state == ModuleState.PLANNED


def test_next_module_id_uses_index_prefix(tmp_path: Path):
    paths = _setup(tmp_path)
    project = _make_project()
    init_project(paths, project)
    mid1 = next_module_id(project, "Auth Service")
    assert mid1.startswith("01-")
    add_module(paths, project, _make_module(project, "Auth Service"))
    mid2 = next_module_id(project, "Rate Limiter")
    assert mid2.startswith("02-")


def test_state_transitions_allowed_and_forbidden():
    assert can_transition(ModuleState.PLANNED, ModuleState.IN_PROGRESS)
    assert can_transition(ModuleState.DEV_COMPLETE, ModuleState.QA_PASSED)
    assert can_transition(ModuleState.DEV_COMPLETE, ModuleState.IN_PROGRESS)  # qa-fail loops back
    assert can_transition(ModuleState.QA_PASSED, ModuleState.SHIPPED)
    assert not can_transition(ModuleState.PLANNED, ModuleState.SHIPPED)
    assert not can_transition(ModuleState.SHIPPED, ModuleState.IN_PROGRESS)


# ---- end-to-end cycle: start → handoff → qa-fail → start → handoff → qa-pass → resolve

def test_full_dev_qa_loop_to_ship(tmp_path: Path):
    paths = _setup(tmp_path)
    _init_git(paths.repo)
    project = _make_project()
    init_project(paths, project)
    mod = _make_module(project, "JWT Auth")
    add_module(paths, project, mod)

    # 1. start cycle 1
    start_module(paths, project, mod.id)
    assert project.modules[mod.id].state == ModuleState.IN_PROGRESS
    assert project.modules[mod.id].cycle_count == 1

    # 2. dev hands off
    handoff_to_qa(paths, project, mod.id, dev_notes="some notes")
    assert project.modules[mod.id].state == ModuleState.DEV_COMPLETE
    doc = paths.module_cycle_dir(mod.id, 1) / "dev-handoff.md"
    assert doc.exists()
    body = doc.read_text()
    assert "QA Handoff" in body
    assert "claude_code" in body  # configured QA tool name
    assert "docker" not in body.lower()  # never include docker

    # 3. QA fails — back to in_progress, cycle 1's qa_result.passed = False, findings template stub written
    record_qa(paths, project, mod.id, passed=False, rationale="missing test for rotation case")
    assert project.modules[mod.id].state == ModuleState.IN_PROGRESS
    last_qa = project.modules[mod.id].last_qa_result
    assert last_qa is not None and not last_qa.passed
    assert (paths.module_cycle_dir(mod.id, 1) / "qa-findings.md").exists()

    # 4. start (cycle 2) — should open new cycle
    start_module(paths, project, mod.id)
    assert project.modules[mod.id].cycle_count == 2

    # 5. handoff cycle 2
    handoff_to_qa(paths, project, mod.id, dev_notes="addressed the rotation case")
    doc2 = paths.module_cycle_dir(mod.id, 2) / "dev-handoff.md"
    assert doc2.exists()

    # 6. QA passes
    record_qa(paths, project, mod.id, passed=True, rationale="all criteria met")
    assert project.modules[mod.id].state == ModuleState.QA_PASSED

    # 7. resolve → shipped + completion doc
    resolve_module(paths, project, mod.id, rationale="v0.1 release")
    assert project.modules[mod.id].state == ModuleState.SHIPPED
    completion = paths.module_completion(mod.id)
    assert completion.exists()
    assert "Completion" in completion.read_text()
    assert "Cycles to ship:** 2" in completion.read_text()


def test_qa_record_rationale_required(tmp_path: Path):
    paths = _setup(tmp_path)
    _init_git(paths.repo)
    project = _make_project()
    init_project(paths, project)
    mod = _make_module(project, "M1")
    add_module(paths, project, mod)
    start_module(paths, project, mod.id)
    handoff_to_qa(paths, project, mod.id)
    with pytest.raises(ProjectError):
        record_qa(paths, project, mod.id, passed=True, rationale="")
    with pytest.raises(ProjectError):
        record_qa(paths, project, mod.id, passed=False, rationale="   ")


def test_resolve_requires_qa_pass(tmp_path: Path):
    paths = _setup(tmp_path)
    _init_git(paths.repo)
    project = _make_project()
    init_project(paths, project)
    mod = _make_module(project, "M1")
    add_module(paths, project, mod)
    start_module(paths, project, mod.id)
    handoff_to_qa(paths, project, mod.id)
    record_qa(paths, project, mod.id, passed=False, rationale="not yet")
    with pytest.raises(ProjectError):
        # state is now in_progress; can't go to shipped
        resolve_module(paths, project, mod.id)


def test_block_and_unblock_restores_previous_state(tmp_path: Path):
    paths = _setup(tmp_path)
    _init_git(paths.repo)
    project = _make_project()
    init_project(paths, project)
    mod = _make_module(project, "M1")
    add_module(paths, project, mod)
    start_module(paths, project, mod.id)
    assert project.modules[mod.id].state == ModuleState.IN_PROGRESS
    block_module(paths, project, mod.id, "waiting on third-party API")
    assert project.modules[mod.id].state == ModuleState.BLOCKED
    assert "third-party" in project.modules[mod.id].blocked_reason
    unblock_module(paths, project, mod.id)
    assert project.modules[mod.id].state == ModuleState.IN_PROGRESS


# ---- handoff doc content ----------------------------------------------------

def test_dev_handoff_doc_includes_acceptance_and_qa_prompt(tmp_path: Path):
    paths = _setup(tmp_path)
    _init_git(paths.repo)
    project = _make_project()
    init_project(paths, project)
    mod = _make_module(project, "M1", plan=ModulePlan(
        purpose="do the thing",
        acceptance_criteria=["A1", "A2", "A3"],
        technical_approach="x",
    ))
    add_module(paths, project, mod)
    start_module(paths, project, mod.id)
    handoff_to_qa(paths, project, mod.id, dev_notes="watch out for race condition")
    body = (paths.module_cycle_dir(mod.id, 1) / "dev-handoff.md").read_text()
    assert "- [ ] A1" in body
    assert "- [ ] A2" in body
    assert "race condition" in body
    assert "QA prompt" in body
    assert "dotagent project qa-record" in body


def test_detect_test_commands_excludes_docker(tmp_path: Path):
    # python project
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    cmds = detect_test_commands(tmp_path)
    assert any("pytest" in c for c in cmds)
    assert not any("docker" in c.lower() for c in cmds)


def test_render_scope_lists_modules(tmp_path: Path):
    paths = _setup(tmp_path)
    project = _make_project()
    init_project(paths, project)
    add_module(paths, project, _make_module(project, "M1"))
    add_module(paths, project, _make_module(project, "M2"))
    body = render_scope(project)
    assert "AI Portal" in body
    assert "M1" in body
    assert "M2" in body


# ---- project_status + recommended next -------------------------------------

def test_project_status_aggregates_and_recommends(tmp_path: Path):
    paths = _setup(tmp_path)
    _init_git(paths.repo)
    project = _make_project()
    init_project(paths, project)
    m1 = _make_module(project, "M1")
    m2 = _make_module(project, "M2", plan=ModulePlan(
        purpose="depends on m1",
        acceptance_criteria=["X"],
        dependencies=[],  # will set below
    ))
    add_module(paths, project, m1)
    add_module(paths, project, m2)
    # add dependency m2 -> m1
    project.modules[m2.id].plan.dependencies = [m1.id]
    save_project(paths, project)

    # m2 cannot be next until m1 ships
    rec = next_recommended_module(project)
    assert rec == m1.id

    # ship m1 fully
    start_module(paths, project, m1.id)
    handoff_to_qa(paths, project, m1.id)
    record_qa(paths, project, m1.id, passed=True, rationale="done")
    resolve_module(paths, project, m1.id)
    assert next_recommended_module(project) == m2.id

    s = project_status(project)
    assert s["shipped"] == 1
    assert s["percent_complete"] == pytest.approx(50.0)


# ---- Context integration ---------------------------------------------------

def test_context_loads_project_and_surfaces_active_module(tmp_path: Path):
    paths = _setup(tmp_path)
    _init_git(paths.repo)
    project = _make_project()
    init_project(paths, project)
    mod = _make_module(project, "Auth")
    add_module(paths, project, mod)
    start_module(paths, project, mod.id)

    cfg = Config.load(paths)
    ctx = build_context(paths, actor="alice", config=cfg)
    assert ctx.project_plan is not None
    assert ctx.project_active_module_id == mod.id


def test_render_body_includes_project_section_and_active_doc_pointer(tmp_path: Path):
    from dotagent.adapters.render import render_body
    paths = _setup(tmp_path)
    _init_git(paths.repo)
    project = _make_project()
    init_project(paths, project)
    mod = _make_module(project, "Auth")
    add_module(paths, project, mod)
    start_module(paths, project, mod.id)

    cfg = Config.load(paths)
    ctx = build_context(paths, actor="alice", config=cfg)
    body = render_body(ctx, tool_label="Claude Code")
    assert "Project: `AI Portal`" in body
    assert "Active module" in body
    assert mod.id in body
    assert "PLAN.md" in body  # active doc pointer when in_progress + no failed cycle yet


def test_render_body_surfaces_qa_findings_after_fail(tmp_path: Path):
    from dotagent.adapters.render import render_body
    paths = _setup(tmp_path)
    _init_git(paths.repo)
    project = _make_project()
    init_project(paths, project)
    mod = _make_module(project, "Auth")
    add_module(paths, project, mod)
    start_module(paths, project, mod.id)
    handoff_to_qa(paths, project, mod.id)
    record_qa(paths, project, mod.id, passed=False, rationale="missing test")
    # now state is IN_PROGRESS again, with last_qa_result.passed == False
    cfg = Config.load(paths)
    ctx = build_context(paths, actor="alice", config=cfg)
    body = render_body(ctx, tool_label="Claude Code")
    assert "qa-findings.md" in body
    assert "previous cycle" in body.lower()


def test_render_body_surfaces_handoff_when_dev_complete(tmp_path: Path):
    from dotagent.adapters.render import render_body
    paths = _setup(tmp_path)
    _init_git(paths.repo)
    project = _make_project()
    init_project(paths, project)
    mod = _make_module(project, "Auth")
    add_module(paths, project, mod)
    start_module(paths, project, mod.id)
    handoff_to_qa(paths, project, mod.id)
    cfg = Config.load(paths)
    ctx = build_context(paths, actor="alice", config=cfg)
    body = render_body(ctx, tool_label="Claude Code")
    assert "dev-handoff.md" in body
    assert "QA tool" in body or "QA prompt" in body or "QA" in body


# ---- scope_builder (mocked input) -------------------------------------------

def test_build_project_with_mocked_asker(tmp_path: Path):
    from dotagent.project.scope_builder import build_project

    # Each subsequent ask() call pops the next answer. Provide enough for the full flow.
    answers = iter([
        "Acme Portal",                                     # name
        "Ship a new self-serve portal users can access",   # goal
        "It is a customer self-serve portal with login, settings, billing and notifications.",  # desc
        "external SSO integrations",                       # out-of-scope (list)
        "users can log in; users can edit settings",       # success criteria (list)
        "internal customers; product team",                # stakeholders
        "Q4 deadline; PII compliant",                      # constraints
        "claude_code",                                     # dev tool
        "claude-opus-4-7",                                 # dev model
        "claude_code",                                     # qa tool
        "claude-sonnet-4-6",                               # qa model
    ])

    def asker(prompt: str) -> str:
        # Suppress vague-followup prompts — they have no "> " trailing in their format.
        if "press Enter to accept" in prompt:
            return ""
        if prompt.strip() == ">":
            return ""
        try:
            return next(answers)
        except StopIteration:
            return ""

    project = build_project(asker=asker, llm=None)
    assert project.name == "Acme Portal"
    assert "self-serve" in project.goal
    assert project.tools["development"]["tool"] == "claude_code"
    assert project.tools["qa"]["model"] == "claude-sonnet-4-6"


def test_scope_builder_vagueness_detects_hedge_words():
    from dotagent.project.scope_builder import heuristic_vagueness
    fu = heuristic_vagueness("What is the goal of this project?", "maybe ship a portal")
    assert fu is not None and "hedging" in fu.lower()


def test_scope_builder_vagueness_detects_short_answers():
    from dotagent.project.scope_builder import heuristic_vagueness
    fu = heuristic_vagueness("Describe the project in 2-4 sentences?", "a portal")
    assert fu is not None


def test_scope_builder_vagueness_detects_vague_quantifiers():
    from dotagent.project.scope_builder import heuristic_vagueness
    fu = heuristic_vagueness("What is the performance target?", "make it fast")
    assert fu is not None and "measurable" in fu.lower()


def test_scope_builder_vagueness_passes_clear_answers():
    from dotagent.project.scope_builder import heuristic_vagueness
    assert heuristic_vagueness(
        "What is the performance target?",
        "API p95 latency under 200ms for all endpoints",
    ) is None
