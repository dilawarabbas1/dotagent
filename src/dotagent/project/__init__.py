"""dotagent project — project management capabilities.

Track a multi-module project end-to-end. Each module has its own extensive plan
(built via interactive Q&A), runs through a dev → QA cycle (potentially many
rounds), and is only marked `shipped` when QA passes and you explicitly resolve.

Documents wire the dev ↔ QA loop:
- cycles/<N>/dev-handoff.md    — dev says "done" — QA tool reads this
- cycles/<N>/qa-findings.md    — QA writes findings — dev tool reads this if next round
- completion.md                — written on resolve; full cycle audit

Source of truth for project completion lives in `.agent/project/plan.yaml`.
"""

from .model import (
    Cycle,
    Module,
    ModuleState,
    Project,
    QAResult,
    load_project,
    save_project,
)

__all__ = [
    "Cycle",
    "Module",
    "ModuleState",
    "Project",
    "QAResult",
    "load_project",
    "save_project",
]
