"""Idempotent regenerator for project-tier derived files.

Bundles the three v0.4.10 generators:

  - `docs/service-registry.md`  (from `.agent/git.yaml`)
  - `.agent/project/modules/<id>/HISTORY.md`  (from each module's cycles)
  - `.agent/dashboard.md`  (project health snapshot)

Safe to call repeatedly. Each generator is wrapped in try/except so a
single failure doesn't prevent the others from writing. Returns the
list of paths that were successfully written.

Called from:
  - `dotagent sync` (every adapter regen)
  - `dotagent project regenerate` (explicit)
  - `dotagent observe pre-commit` (when docs/*.md changes)
"""

from __future__ import annotations

from pathlib import Path

from ..logging import log_exception
from ..paths import Paths
from ..util import write_text


def regenerate_derived_files(paths: Paths) -> list[Path]:
    """Re-render every project-tier derived file we know how to produce.

    Skipped silently when the inputs aren't present (e.g. service-registry
    needs `.agent/git.yaml`, HISTORY/dashboard need a loadable project).
    """
    written: list[Path] = []
    if not paths.agent.exists():
        return written

    written.extend(_regen_service_registry(paths))
    project = _safe_load_project(paths)
    if project is not None:
        written.extend(_regen_module_history(paths, project))
        written.extend(_regen_dashboard(paths, project))
    return written


def _regen_service_registry(paths: Paths) -> list[Path]:
    try:
        from ..git_layout import load as _load_git
        from .service_registry import render_service_registry
        git_yaml = paths.agent / "git.yaml"
        if not git_yaml.exists():
            return []
        layout = _load_git(git_yaml)
        target = paths.repo / "docs" / "service-registry.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        write_text(target, render_service_registry(layout))
        return [target]
    except Exception as exc:  # noqa: BLE001
        log_exception("service-registry regen", exc)
        return []


def _regen_module_history(paths: Paths, project) -> list[Path]:
    out: list[Path] = []
    try:
        from .module_history import render_module_history
    except Exception as exc:  # noqa: BLE001
        log_exception("module_history import", exc)
        return out

    for module in project.modules.values():
        try:
            module_dir = paths.agent / "project" / "modules" / module.id
            module_dir.mkdir(parents=True, exist_ok=True)
            target = module_dir / "HISTORY.md"
            write_text(target, render_module_history(module))
            out.append(target)
        except Exception as exc:  # noqa: BLE001
            log_exception(f"module HISTORY regen ({module.id})", exc)
    return out


def _regen_dashboard(paths: Paths, project) -> list[Path]:
    try:
        from .dashboard import render_dashboard
        target = paths.agent / "dashboard.md"
        write_text(target, render_dashboard(project, paths))
        return [target]
    except Exception as exc:  # noqa: BLE001
        log_exception("dashboard regen", exc)
        return []


def _safe_load_project(paths: Paths):
    """Load Project if a plan.yaml exists. None on any failure."""
    plan = paths.agent / "project" / "plan.yaml"
    if not plan.exists():
        return None
    try:
        from ..project.model import load_project
        return load_project(paths)
    except Exception as exc:  # noqa: BLE001
        log_exception("project load (for derived regen)", exc)
        return None


__all__ = ("regenerate_derived_files",)
