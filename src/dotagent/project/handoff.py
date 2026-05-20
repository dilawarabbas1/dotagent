"""Generate the documents that wire dev ↔ QA:

- `cycles/<N>/dev-handoff.md` — what dev did + acceptance criteria + how-to-test
- `cycles/<N>/qa-findings.md` — what QA found (pass / fail with issues)
- `completion.md` — the audit when the module ships

Also exposes the "how to test" auto-detection that scans the repo for known
test runners and avoids Docker references entirely (per project rules).
"""

from __future__ import annotations

from pathlib import Path

from ..paths import Paths
from ..util import run
from .model import Cycle, Module, Project, QAResult


# ---- test-runner auto-detection (no docker) --------------------------------

def detect_test_commands(repo: Path) -> list[str]:
    """Return one-line test commands sniffed from the repo. Excludes anything mentioning docker."""
    cmds: list[str] = []
    if (repo / "pyproject.toml").exists() or (repo / "pytest.ini").exists() or (repo / "tests").is_dir():
        cmds.append("pytest -q")
    if (repo / "package.json").exists():
        try:
            import json
            pkg = json.loads((repo / "package.json").read_text())
            scripts = (pkg.get("scripts") or {})
            if "test" in scripts:
                cmds.append("npm test")
            if "test:unit" in scripts:
                cmds.append("npm run test:unit")
        except Exception:
            cmds.append("npm test")
    if (repo / "go.mod").exists():
        cmds.append("go test ./...")
    if (repo / "Cargo.toml").exists():
        cmds.append("cargo test")
    if (repo / "Makefile").exists():
        cmds.append("make test")
    # never include docker
    return [c for c in cmds if "docker" not in c.lower()]


# Paths under these prefixes (or matching these names) are dotagent's own
# state or generated adapter outputs — side-effects of dotagent commands,
# not user-authored code changes. Filter them so the QA tool sees only
# what the dev actually wrote.
_INTERNAL_PREFIXES = (".agent/", ".git/")
_GENERATED_FILES = {
    "CLAUDE.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
    "AGENTS.md",
}


def _is_internal(path: str) -> bool:
    if any(path.startswith(p) for p in _INTERNAL_PREFIXES):
        return True
    return path in _GENERATED_FILES


def files_changed_since(repo: Path, since_sha: str, *, include_internal: bool = False) -> list[str]:
    """Files changed in git since `since_sha`. Filters dotagent/git internals by default."""
    if not since_sha:
        return []
    res = run(["git", "diff", "--name-only", since_sha], cwd=repo)
    if not res.ok:
        return []
    files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    if include_internal:
        return files
    return [f for f in files if not _is_internal(f)]


def current_sha(repo: Path) -> str:
    res = run(["git", "rev-parse", "HEAD"], cwd=repo)
    return res.stdout.strip() if res.ok else ""


# ---- dev-handoff.md ---------------------------------------------------------

def render_dev_handoff(
    project: Project,
    module: Module,
    cycle: Cycle,
    *,
    repo: Path,
    dev_notes: str = "",
) -> str:
    qa_tool = (project.tools.get("qa") or {}).get("tool") or "claude_code"
    qa_model = (project.tools.get("qa") or {}).get("model") or "(default)"
    dev_tool = (project.tools.get("development") or {}).get("tool") or "claude_code"
    test_cmds = detect_test_commands(repo)
    files = cycle.files_changed or []

    acc = "\n".join(f"- [ ] {c}" for c in module.plan.acceptance_criteria) or "_(none specified)_"
    files_block = "\n".join(f"- `{f}`" for f in files[:80]) or "_(no file changes detected)_"
    if len(files) > 80:
        files_block += f"\n- _(...and {len(files) - 80} more)_"

    test_block = "\n".join(f"```\n{c}\n```" for c in test_cmds) if test_cmds \
        else "_(no test runner auto-detected — describe how to test in dev notes below)_"

    deps = ", ".join(module.plan.dependencies) or "_(none)_"

    return (
f"""# QA Handoff — {module.id}

> dev-complete; awaiting QA review (cycle {cycle.n})

**Module:** {module.id} — {module.name}
**Project:** {project.name}
**Dev tool (configured):** `{dev_tool}`
**QA tool (configured):** `{qa_tool}` (model: `{qa_model}`)
**Cycle:** {cycle.n}  ·  **Handoff at:** {cycle.handoff_at}
**Diff range:** `{cycle.start_sha[:12] or 'n/a'}..{cycle.handoff_sha[:12] or 'HEAD'}`
**Depends on:** {deps}

## Module purpose

{module.plan.purpose or '_(see PLAN.md)_'}

## Acceptance criteria

{acc}

## In scope (recap)

{chr(10).join(f'- {x}' for x in module.plan.in_scope) or '_(see PLAN.md)_'}

## Out of scope (recap)

{chr(10).join(f'- {x}' for x in module.plan.out_of_scope) or '_(none specified)_'}

## Technical approach

{module.plan.technical_approach or '_(see PLAN.md)_'}

## Files changed in this cycle ({len(files)})

{files_block}

## How to test

{test_block}

## Known limitations / dev notes

{dev_notes.strip() or '_(none)_'}

---

## QA prompt — copy this into your QA tool

You are the QA agent for the `{module.id}` module of project `{project.name}`.
Read this entire handoff. Then:

1. **Verify each acceptance criterion** against the code changes listed under
   "Files changed in this cycle". Reference specific lines where possible.
2. **Reproduce the steps under "How to test"**. Report exit codes and any failures.
3. **Check for regressions** outside the listed files (search for callers of changed APIs).
4. **Pay attention to the dev notes** — known limitations may be acceptable or may need
   fixing this cycle. State your position explicitly.

When you're done, **write your findings to**:
    `.agent/project/modules/{module.id}/cycles/{cycle.n:02d}/qa-findings.md`

Structure your findings document with this skeleton:

```markdown
# QA Findings — {module.id} — cycle {cycle.n}

## Verdict
pass | fail

## Acceptance criteria results
- [x] criterion 1 — ✓ verified (file:line evidence)
- [ ] criterion 2 — ✗ failing because ...

## Issues found (if fail)
1. **Title** — what's wrong, where, suggested fix
2. ...

## Notes / suggestions
- ...
```

Then **the human** runs:

```
dotagent project qa-record {module.id} --result pass --rationale "<one-line summary>"
# or:
dotagent project qa-record {module.id} --result fail --rationale "<one-line summary>"
```

If `fail`, the dev tool will pick up `qa-findings.md` automatically on its next
session (it's surfaced in CLAUDE.md). Iterate, then call
`dotagent project handoff {module.id}` again to open cycle {cycle.n + 1}.
"""
    )


# ---- qa-findings template (used when no QA tool — interactive recording) ---

def qa_findings_template(module: Module, cycle: Cycle) -> str:
    acc = "\n".join(f"- [ ] {c}" for c in module.plan.acceptance_criteria) or "_(none specified)_"
    return (
f"""# QA Findings — {module.id} — cycle {cycle.n}

## Verdict
fail

## Acceptance criteria results
{acc}

## Issues found
1.

## Notes / suggestions
-
"""
    )


# ---- completion.md ----------------------------------------------------------

def render_completion(project: Project, module: Module) -> str:
    cycles_summary: list[str] = []
    for c in module.cycles:
        if c.qa_result:
            verdict = "✓ pass" if c.qa_result.passed else "✗ fail"
            cycles_summary.append(
                f"- **Cycle {c.n}** — {verdict} — by `{c.qa_result.recorded_by or '?'}` "
                f"on {c.qa_result.recorded_at[:10] or '?'} — _{c.qa_result.rationale}_"
            )
        else:
            cycles_summary.append(f"- **Cycle {c.n}** — _(no QA result recorded)_")

    deps = ", ".join(module.plan.dependencies) or "_(none)_"
    files_all = sorted({f for c in module.cycles for f in c.files_changed})
    files_block = "\n".join(f"- `{f}`" for f in files_all[:100]) or "_(no file changes recorded)_"
    if len(files_all) > 100:
        files_block += f"\n- _(...and {len(files_all) - 100} more)_"

    return (
f"""# Completion — {module.id}

**Module:** {module.id} — {module.name}
**Project:** {project.name}
**Cycles to ship:** {module.cycle_count}
**Depends on:** {deps}

## What was built

{module.plan.purpose}

## Acceptance criteria met

{chr(10).join(f'- [x] {c}' for c in module.plan.acceptance_criteria) or '_(none specified)_'}

## Cycle history

{chr(10).join(cycles_summary) or '_(no cycles recorded)_'}

## Total files touched ({len(files_all)})

{files_block}

---

_Marked shipped via `dotagent project resolve {module.id}`._
"""
    )


# ---- PLAN.md (human-readable per-module plan generated from Q&A) -----------

def render_module_plan(module: Module) -> str:
    p = module.plan
    return (
f"""# Plan — {module.id} — {module.name}

> Built via `dotagent project add-module` interactive Q&A.

## Purpose

{p.purpose}

## In scope

{chr(10).join(f'- {x}' for x in p.in_scope) or '_(none)_'}

## Out of scope

{chr(10).join(f'- {x}' for x in p.out_of_scope) or '_(none)_'}

## Acceptance criteria

{chr(10).join(f'{i+1}. {c}' for i, c in enumerate(p.acceptance_criteria)) or '_(none)_'}

## Dependencies on other modules

{chr(10).join(f'- `{d}`' for d in p.dependencies) or '_(none)_'}

## Technical approach

{p.technical_approach}

## Known risks / open questions

{chr(10).join(f'- {r}' for r in p.risks) or '_(none)_'}

## Estimated effort

{p.estimated_effort or '_(unestimated)_'}

---

_Edit this file freely; dotagent re-reads it on `dotagent project show`. The
machine-readable copy lives in `module.yaml` — keep them in sync if you edit
this by hand._
"""
    )


# ---- SCOPE.md (project-level human-readable scope) -------------------------

def render_scope(project: Project, *, brief=None) -> str:
    """Render `.agent/project/SCOPE.md`.

    Defensive: if `project` is missing top-level fields (name, goal,
    description, out_of_scope, success_criteria) — common in the
    layered-tier plan.yaml shape — fall back to the brief where possible
    so a regenerate doesn't hollow out the file.
    """
    # Project field fallbacks
    name = (project.name
            or (getattr(brief, "name", "") if brief else "")
            or "(unset — add `name:` to plan.yaml or the brief)")
    goal = (project.goal
            or (getattr(brief, "vision", "") if brief else "")
            or "_(unset — add `goal:` to plan.yaml)_")
    description = (project.description
                   or (getattr(brief, "vision", "") if brief else "")
                   or "_(unset — add `description:` to plan.yaml)_")
    out_of_scope = (project.out_of_scope
                    or (getattr(brief, "non_goals", []) if brief else []))
    success_criteria = (project.success_criteria
                        or (getattr(brief, "success_metrics", []) if brief else []))

    modules_md = ""
    for mid in project.module_ids:
        mod = project.modules.get(mid)
        if mod:
            modules_md += f"- **{mid}** — {mod.name} _({mod.state})_\n"
        else:
            modules_md += f"- **{mid}** _(not loaded)_\n"
    return (
f"""<!-- generated by dotagent — do not edit. Re-render with `dotagent project regenerate` or any project state change. -->
# Project Scope — {name}

## Goal

{goal}

## Description

{description}

## Out of scope

{chr(10).join(f'- {x}' for x in out_of_scope) or '_(none)_'}

## Success criteria

{chr(10).join(f'- {x}' for x in success_criteria) or '_(none)_'}

## Stakeholders

{chr(10).join(f'- {x}' for x in project.stakeholders) or '_(none)_'}

## Constraints

{chr(10).join(f'- {x}' for x in project.constraints) or '_(none)_'}

## Tool routing (defaults)

| Role | Tool | Model |
| --- | --- | --- |
{chr(10).join(f"| {role} | `{(project.tools.get(role) or {}).get('tool','-')}` | `{(project.tools.get(role) or {}).get('model','-')}` |" for role in ("development", "qa", "review", "planning"))}

## Modules

{modules_md or '_(no modules yet — `dotagent project add-module <name>` to add)_'}

---

_Generated by dotagent. Edit `plan.yaml` for the source of truth; this file
regenerates on changes._
"""
    )
