"""Migrate a pre-v0.4 dotagent install to v0.4.0.

Changes applied (each one a reversible MigrationStep):

1. Write `.agent/.version` with `0.4.0`.
2. If `.agent/project_brief.md` is missing, create a minimal stub.

Future versions extend this list. Each step records enough metadata that
`migrate --rollback` can reverse it.
"""

from __future__ import annotations

from pathlib import Path

from .log import KIND_CREATED, MigrationStep


_BRIEF_STUB = """<!-- Project brief stub — hand-fill or run `dotagent project brief init`.
     IDs (OBJ-*, FEAT-*, RULE-*) are referenced from plan.yaml and contracts. -->

# Project brief: <your project name>

**Last reviewed:** <YYYY-MM-DD>  ·  **Brief version:** 1  ·  **Owner:** <name@domain>  ·  **Stage:** <idea | seed | alpha | beta | GA>

## Vision (one sentence)
<What this product becomes if it wins.>

## Target users
- **Persona 1 — <name + role>**: <pain that brings them to you>

## Business objectives
- **OBJ-01**: <measurable outcome with a number and a deadline>

## Features
### FEAT-01 · <feature name>
**Serves:** OBJ-01
**Expected outcome:** <business result>
**What it must do:**
- <user-visible behavior>

## Hard rules
- **RULE-01 · <name>** — _why: <reason>; how: <when it applies>_

## Glossary
- **<term>** — <one-line definition>

## Constraints
- <hard limit on what we can do>
"""


def migrate_v0_3_to_v0_4(repo: Path, *, write: bool) -> list[MigrationStep]:
    """Return (or apply) the list of changes for a v0.3 → v0.4 upgrade.

    `write=False` is plan mode: build the step list, touch nothing.
    `write=True` performs each step.
    """
    steps: list[MigrationStep] = []
    agent = repo / ".agent"

    # Step 1: version stamp
    version_file = agent / ".version"
    if not version_file.exists():
        step = MigrationStep(
            kind=KIND_CREATED,
            path=".agent/.version",
            detail="(0.4.0)",
        )
        steps.append(step)
        if write:
            agent.mkdir(parents=True, exist_ok=True)
            version_file.write_text("0.4.0\n")

    # Step 2: project_brief.md stub
    brief = agent / "project_brief.md"
    if not brief.exists():
        step = MigrationStep(
            kind=KIND_CREATED,
            path=".agent/project_brief.md",
            detail="(stub)",
        )
        steps.append(step)
        if write:
            agent.mkdir(parents=True, exist_ok=True)
            brief.write_text(_BRIEF_STUB)

    return steps


def rollback_step(repo: Path, step: MigrationStep) -> bool:
    """Reverse one step. Returns True on success.

    Best-effort: a missing target is treated as a success (already gone),
    not a failure.
    """
    if step.kind == KIND_CREATED:
        target = repo / step.path
        if target.exists():
            try:
                target.unlink()
            except OSError:
                return False
        return True
    # MOVED / MODIFIED / DELETED rollbacks are added when those step kinds
    # are introduced. For now (v0.3 → v0.4) we only ever CREATE.
    return False


__all__ = ("migrate_v0_3_to_v0_4", "rollback_step")
