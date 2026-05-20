"""`dotagent project` command group."""

from __future__ import annotations

from pathlib import Path

import click

from ..llm import LLM
from ..paths import Paths, find_repo_root
from ..project.handoff import render_module_plan, render_scope
from ..project.model import (
    Module,
    ModuleState,
    next_module_id,
    now,
    save_module,
    save_project,
)
from ..project.operations import (
    ProjectError,
    add_module as op_add_module,
    block_module,
    handoff_to_qa,
    init_project,
    next_recommended_module,
    project_status,
    record_qa,
    require_project,
    resolve_module,
    start_module,
    unblock_module,
)
from ..project.scope_builder import KNOWN_TOOLS, build_module, build_project
from ..util import write_text


def _paths() -> Paths:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init` first.")
    return paths


@click.group(name="project", help="Project management: scope, modules, dev↔QA cycle, completion tracking.")
def project_group() -> None:
    pass


# ---- init ------------------------------------------------------------------

@project_group.command(name="init", help="Interactive Q&A to build the project-level scope.")
@click.option("--no-llm", is_flag=True, help="Skip LLM-assisted vagueness probing.")
def cmd_init(no_llm: bool) -> None:
    paths = _paths()
    if paths.project_plan.exists():
        click.echo(f"Project already initialized at {paths.project_plan}. Edit by hand or remove to start over.")
        raise SystemExit(0)
    click.echo("dotagent project init — building project scope. Type <EDITOR> in any answer to open $EDITOR.\n")
    llm = LLM() if not no_llm else None
    project = build_project(llm=llm)
    init_project(paths, project)
    click.echo(f"\n✓ project '{project.name}' initialized")
    click.echo(f"  · plan: {paths.project_plan.relative_to(paths.repo)}")
    click.echo(f"  · scope: {paths.project_scope_md.relative_to(paths.repo)}")
    click.echo(f"\n→ next: `dotagent project add-module <name>` for each functional unit you'll build.")


# ---- add-module ------------------------------------------------------------

@project_group.command(name="add-module", help="Interactive Q&A to plan a new module.")
@click.argument("name")
@click.option("--no-llm", is_flag=True)
def cmd_add_module(name: str, no_llm: bool) -> None:
    paths = _paths()
    project = require_project(paths)
    mid = next_module_id(project, name)
    click.echo(f"adding module {mid} ({name})\n")
    llm = LLM() if not no_llm else None
    plan = build_module(name, project, llm=llm)
    mod = Module(id=mid, name=name, plan=plan, created_at=now())
    op_add_module(paths, project, mod)
    click.echo(f"\n✓ {mid} planned. {len(plan.acceptance_criteria)} acceptance criteria.")
    click.echo(f"  · plan: {paths.module_plan_md(mid).relative_to(paths.repo)}")
    click.echo(f"\n→ when ready: `dotagent project start {mid}`")


# ---- list / status / show --------------------------------------------------

@project_group.command(name="list", help="List all modules with their state.")
def cmd_list() -> None:
    paths = _paths()
    project = require_project(paths)
    if not project.module_ids:
        click.echo("(no modules — `dotagent project add-module <name>`)")
        return
    glyph = {
        ModuleState.DEFINED: "·", ModuleState.PLANNED: "○",
        ModuleState.IN_PROGRESS: "▶", ModuleState.DEV_COMPLETE: "▸",
        ModuleState.QA_PASSED: "✓", ModuleState.SHIPPED: "★",
        ModuleState.BLOCKED: "⊘",
    }
    for mid in project.module_ids:
        mod = project.modules.get(mid)
        if not mod:
            continue
        g = glyph.get(mod.state, "?")
        cycles = f"c{mod.cycle_count}" if mod.cycle_count else "—"
        click.echo(f"  {g}  {mid:30s}  {mod.state:14s}  {cycles:>4s}  {mod.name}")


@project_group.command(name="status", help="Source-of-truth project completion summary.")
def cmd_status() -> None:
    paths = _paths()
    project = require_project(paths)
    s = project_status(project)
    click.echo(f"project:  {s['name']}")
    click.echo(f"modules:  {s['shipped']}/{s['modules_total']} shipped"
               f"  ({s['percent_complete']:.0f}% complete)")
    if s["blocked"]:
        click.echo(f"blocked:  {s['blocked']}")
    for state in (
        ModuleState.IN_PROGRESS, ModuleState.DEV_COMPLETE, ModuleState.QA_PASSED,
        ModuleState.PLANNED, ModuleState.DEFINED, ModuleState.BLOCKED, ModuleState.SHIPPED,
    ):
        items = s["by_state"].get(state) or []
        if items:
            click.echo(f"  {state}: {', '.join(items)}")
    nxt = next_recommended_module(project)
    if nxt:
        click.echo(f"\nnext recommended: {nxt}")


@project_group.command(name="show", help="Full detail on one module: plan, cycles, QA history.")
@click.argument("module_id")
def cmd_show(module_id: str) -> None:
    paths = _paths()
    project = require_project(paths)
    if module_id not in project.modules:
        raise click.ClickException(f"unknown module '{module_id}'")
    mod = project.modules[module_id]
    click.echo(f"\n=== {mod.id} — {mod.name} ===")
    click.echo(f"state:   {mod.state}")
    click.echo(f"cycles:  {mod.cycle_count}")
    if mod.state == ModuleState.BLOCKED:
        click.echo(f"blocked: {mod.blocked_reason}")
    click.echo(f"\npurpose: {mod.plan.purpose}")
    if mod.plan.dependencies:
        click.echo(f"deps:    {', '.join(mod.plan.dependencies)}")
    click.echo("\nacceptance criteria:")
    for c in mod.plan.acceptance_criteria:
        click.echo(f"  - {c}")
    if mod.cycles:
        click.echo("\ncycles:")
        for c in mod.cycles:
            verdict = "—"
            if c.qa_result:
                verdict = ("✓ pass" if c.qa_result.passed else "✗ fail") + f" ({c.qa_result.rationale[:60]})"
            click.echo(f"  cycle {c.n}  start={c.started_at[:10] or '-'}  "
                       f"handoff={c.handoff_at[:10] or '-'}  files={len(c.files_changed)}  qa={verdict}")
    click.echo(f"\nfiles: {paths.module_dir(mod.id).relative_to(paths.repo)}/")


# ---- start / handoff / qa-record / resolve ---------------------------------

@project_group.command(name="start", help="Start (or resume) work on a module.")
@click.argument("module_id")
def cmd_start(module_id: str) -> None:
    paths = _paths()
    project = require_project(paths)
    try:
        mod = start_module(paths, project, module_id)
    except ProjectError as e:
        raise click.ClickException(str(e))
    click.echo(f"▶ {mod.id} → in_progress (cycle {mod.current_cycle.n})")
    click.echo(f"  working-memory task set: '{mod.id}: {mod.name}'")
    click.echo(f"  read your plan: {paths.module_plan_md(mod.id).relative_to(paths.repo)}")


@project_group.command(name="handoff", help="Dev says 'done': write the dev-handoff doc for QA.")
@click.argument("module_id")
@click.option("--notes", default="", help="Free-text dev notes appended to the handoff (limitations, gotchas).")
@click.option("--notes-file", default="", help="Read dev notes from a file (markdown).")
def cmd_handoff(module_id: str, notes: str, notes_file: str) -> None:
    paths = _paths()
    project = require_project(paths)
    if notes_file:
        notes = Path(notes_file).read_text()
    try:
        mod = handoff_to_qa(paths, project, module_id, dev_notes=notes)
    except ProjectError as e:
        raise click.ClickException(str(e))
    cycle = mod.current_cycle
    doc = paths.module_cycle_dir(mod.id, cycle.n) / "dev-handoff.md"
    click.echo(f"▸ {mod.id} → dev_complete (cycle {cycle.n}) — {len(cycle.files_changed)} files in this cycle")
    click.echo(f"  handoff doc: {doc.relative_to(paths.repo)}")
    click.echo(f"\n→ tell your QA tool: 'Read {doc.relative_to(paths.repo)} and follow the QA prompt at the bottom.'")


@project_group.command(name="qa-prompt", help="Print the QA prompt for the current cycle (copy into QA tool).")
@click.argument("module_id")
def cmd_qa_prompt(module_id: str) -> None:
    paths = _paths()
    project = require_project(paths)
    if module_id not in project.modules:
        raise click.ClickException(f"unknown module '{module_id}'")
    mod = project.modules[module_id]
    if not mod.current_cycle or not mod.current_cycle.handoff_at:
        raise click.ClickException(f"no dev-handoff yet — run `dotagent project handoff {module_id}` first")
    doc = paths.module_cycle_dir(mod.id, mod.current_cycle.n) / "dev-handoff.md"
    if not doc.exists():
        raise click.ClickException(f"handoff file missing: {doc}")
    click.echo(doc.read_text())


@project_group.command(name="qa-record", help="Record QA result. Rationale required (pass or fail).")
@click.argument("module_id")
@click.option("--result", type=click.Choice(["pass", "fail"]), required=True)
@click.option("--rationale", required=True, help="One-line summary. Mandatory.")
@click.option("--findings-file", default="", help="Optional path to the QA findings markdown.")
def cmd_qa_record(module_id: str, result: str, rationale: str, findings_file: str) -> None:
    paths = _paths()
    project = require_project(paths)
    try:
        mod = record_qa(paths, project, module_id,
                        passed=(result == "pass"), rationale=rationale,
                        findings_path=findings_file)
    except ProjectError as e:
        raise click.ClickException(str(e))
    if result == "pass":
        click.echo(f"✓ {mod.id} → qa_passed (cycle {mod.current_cycle.n})")
        click.echo(f"  → ship it: `dotagent project resolve {mod.id}`")
    else:
        cdir = paths.module_cycle_dir(mod.id, mod.current_cycle.n)
        click.echo(f"✗ {mod.id} → in_progress (cycle {mod.current_cycle.n} failed); next cycle on `start`/`handoff`")
        click.echo(f"  findings: {(cdir / 'qa-findings.md').relative_to(paths.repo)}")
        click.echo(f"  → dev tool will surface these findings on next session.")


@project_group.command(name="resolve", help="Mark module shipped (only after qa_passed). Writes completion.md.")
@click.argument("module_id")
@click.option("--rationale", default="", help="Optional resolve note (e.g., release tag).")
def cmd_resolve(module_id: str, rationale: str) -> None:
    paths = _paths()
    project = require_project(paths)
    try:
        mod = resolve_module(paths, project, module_id, rationale=rationale)
    except ProjectError as e:
        raise click.ClickException(str(e))
    click.echo(f"★ {mod.id} SHIPPED after {mod.cycle_count} cycle(s)")
    click.echo(f"  completion: {paths.module_completion(mod.id).relative_to(paths.repo)}")


@project_group.command(name="block", help="Mark a module blocked.")
@click.argument("module_id")
@click.option("--reason", required=True)
def cmd_block(module_id: str, reason: str) -> None:
    paths = _paths()
    project = require_project(paths)
    try:
        mod = block_module(paths, project, module_id, reason)
    except ProjectError as e:
        raise click.ClickException(str(e))
    click.echo(f"⊘ {mod.id} blocked (was {mod.pre_block_state}): {reason}")


@project_group.command(name="unblock", help="Unblock a module (restores previous state).")
@click.argument("module_id")
def cmd_unblock(module_id: str) -> None:
    paths = _paths()
    project = require_project(paths)
    try:
        mod = unblock_module(paths, project, module_id)
    except ProjectError as e:
        raise click.ClickException(str(e))
    click.echo(f"{mod.id} → {mod.state}")


@project_group.command(name="next", help="Recommend the next module to work on (resolves dependencies).")
def cmd_next() -> None:
    paths = _paths()
    project = require_project(paths)
    nxt = next_recommended_module(project)
    if not nxt:
        click.echo("(no unblocked unshipped modules — `dotagent project add-module` or `unblock` something)")
        return
    mod = project.modules[nxt]
    click.echo(f"→ {mod.id} ({mod.state}) — {mod.name}")
    if mod.state == ModuleState.PLANNED:
        click.echo(f"  run: `dotagent project start {mod.id}`")
    elif mod.state == ModuleState.IN_PROGRESS:
        click.echo(f"  continue dev. when done: `dotagent project handoff {mod.id}`")
    elif mod.state == ModuleState.DEV_COMPLETE:
        click.echo(f"  awaiting QA — `dotagent project qa-prompt {mod.id}`")
    elif mod.state == ModuleState.QA_PASSED:
        click.echo(f"  ship: `dotagent project resolve {mod.id}`")


# ---- Pre-build contract subgroup -------------------------------------------
# Registers `dotagent project contract ...` lazily at import time so the
# subgroup lives alongside the existing project verbs without touching cli.py.
from .contract_cmd import contract_group as _contract_group  # noqa: E402
from .brief_cmd import brief_group as _brief_group  # noqa: E402
from .contracts_index_cmd import contracts_group as _contracts_group  # noqa: E402
from .plan_cmd import plan_group as _plan_group  # noqa: E402
project_group.add_command(_contract_group)
project_group.add_command(_brief_group)
project_group.add_command(_contracts_group)
project_group.add_command(_plan_group)
