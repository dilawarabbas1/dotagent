"""dotagent doctor — diagnose common misconfigurations.

Each check returns a `Diagnosis` with status: `ok` / `warn` / `fail` / `info`.
The CLI prints them grouped, then exits with code 1 if any `fail` was reported.

Designed to be the first thing a user (or Claude Code) runs when something
seems wrong.
"""

from __future__ import annotations

import importlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Config
from .paths import Paths
from .sources import load_cache
from .structure_checker import (
    SEVERITY_FAIL as _STRUCT_FAIL,
    SEVERITY_WARN as _STRUCT_WARN,
    check as _structure_check,
)


@dataclass
class Diagnosis:
    name: str
    status: str  # ok | warn | fail | info
    message: str
    fix: str = ""


_OK = "ok"
_WARN = "warn"
_FAIL = "fail"
_INFO = "info"


def _check_python_version() -> Diagnosis:
    import sys
    v = sys.version_info
    if v < (3, 11):
        return Diagnosis("python", _FAIL, f"Python {v.major}.{v.minor} is too old.",
                         "Install Python 3.11+ (dotagent requires it).")
    return Diagnosis("python", _OK, f"Python {v.major}.{v.minor}.{v.micro}.")


def _check_git_present() -> Diagnosis:
    if shutil.which("git"):
        return Diagnosis("git", _OK, "git is on PATH.")
    return Diagnosis("git", _WARN, "git is not on PATH.",
                     "Install git. Most features still work, but hooks won't fire.")


def _check_anthropic_key() -> Diagnosis:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return Diagnosis("anthropic_key", _OK, "ANTHROPIC_API_KEY is set.")
    return Diagnosis("anthropic_key", _INFO,
                     "ANTHROPIC_API_KEY is not set.",
                     "Optional. Set it for LLM-backed drafting and `dotagent skill run`.")


def _check_agent_dir(paths: Paths) -> Diagnosis:
    if not paths.agent.exists():
        return Diagnosis("agent_dir", _FAIL, f"No .agent/ at {paths.agent}.",
                         "Run `dotagent init` in this repo.")
    if not paths.config.exists():
        return Diagnosis("agent_dir", _FAIL, f".agent/ exists but config.yaml is missing.",
                         "Run `dotagent init` again.")
    return Diagnosis("agent_dir", _OK, f".agent/ initialized at {paths.agent}.")


def _check_sources(paths: Paths, cfg: Config) -> Diagnosis:
    sources_cfg = cfg.raw.get("sources") or {}
    if not sources_cfg or all(not v for v in sources_cfg.values() if isinstance(v, str)):
        return Diagnosis("sources", _WARN,
                         "No sources configured under .agent/config.yaml `sources:`.",
                         "Point at your docs/*.md files (bug-registry, anti-patterns, etc.).")
    cached = load_cache(paths)
    present = sum(1 for s in cached.values() if s.exists)
    total = len(cached)
    if total == 0:
        return Diagnosis("sources", _WARN, "Source cache is empty.",
                         "Run `dotagent reindex`.")
    if present == 0:
        return Diagnosis("sources", _WARN,
                         f"0/{total} configured sources exist on disk.",
                         "Create at least one of the configured docs/*.md files.")
    return Diagnosis("sources", _OK,
                     f"{present}/{total} sources indexed and present on disk.")


def _check_hooks(paths: Paths) -> Diagnosis:
    git_hooks = paths.repo / ".git" / "hooks"
    if not git_hooks.is_dir():
        return Diagnosis("hooks", _WARN,
                         "Not a git repo — no git hooks installed.",
                         "Run `git init` then `dotagent sync`.")
    missing: list[str] = []
    for name in ("pre-commit", "post-commit", "prepare-commit-msg"):
        target = git_hooks / name
        if not target.exists():
            missing.append(name); continue
        try:
            text = target.read_text()
        except OSError:
            missing.append(name); continue
        if "dotagent" not in text:
            missing.append(name)
    if missing:
        return Diagnosis("hooks", _WARN,
                         f"git hooks missing dotagent wiring: {', '.join(missing)}",
                         "Run `dotagent sync` to (re)install hooks.")
    claude_hook = paths.repo / ".claude" / "hooks" / "post-tool.sh"
    if not claude_hook.exists():
        return Diagnosis("hooks", _WARN,
                         "Claude Code post-tool hook is missing.",
                         "Run `dotagent sync`.")
    return Diagnosis("hooks", _OK, "All git + Claude Code hooks installed.")


def _check_episodic_index(paths: Paths) -> Diagnosis:
    if not paths.episodic.exists():
        return Diagnosis("episodic_index", _INFO,
                         "No episodic events recorded yet.",
                         "Normal on a fresh install.")
    db = paths.episodic / "index.sqlite"
    jsonl_count = sum(1 for _ in paths.episodic.rglob("*.jsonl"))
    if jsonl_count and not db.exists():
        return Diagnosis("episodic_index", _WARN,
                         f"{jsonl_count} JSONL files exist but no SQLite index.",
                         "Run `dotagent reindex-events`.")
    return Diagnosis("episodic_index", _OK,
                     f"{jsonl_count} JSONL files, index present.")


def _check_optional_extras() -> list[Diagnosis]:
    out: list[Diagnosis] = []
    for label, modules, extra in (
        ("embeddings", ["sentence_transformers", "sklearn", "numpy"], "ml"),
        ("server", ["fastapi", "uvicorn"], "server"),
        ("watcher", ["watchdog"], "watch"),
    ):
        missing = [m for m in modules if not _try_import(m)]
        if missing:
            out.append(Diagnosis(
                f"extras:{label}", _INFO,
                f"Optional {label} extras not installed (missing: {', '.join(missing)}).",
                f"Install with `pip install 'dotagent[{extra}]'`.",
            ))
        else:
            out.append(Diagnosis(f"extras:{label}", _OK, f"{label} extras installed."))
    return out


def _try_import(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def _check_cache_gitignored(paths: Paths) -> Diagnosis:
    if not paths.cache.exists():
        return Diagnosis("cache_gitignore", _INFO, "No .agent/.cache/ yet.")
    gi = paths.cache_gitignore
    if not gi.exists():
        return Diagnosis("cache_gitignore", _WARN,
                         ".agent/.cache/.gitignore missing — the cache may get committed.",
                         "Run `dotagent reindex` (regenerates .gitignore).")
    return Diagnosis("cache_gitignore", _OK, ".cache/ is gitignored.")


def _check_canonical_structure(paths: Paths) -> Diagnosis:
    """Audit the repo against the canonical structure schema.

    Returns a single Diagnosis summarizing the structure check. Detail is
    available via `dotagent structure check`.
    """
    result = _structure_check(paths.repo)
    fails = [d for d in result.deviations if d.severity == _STRUCT_FAIL]
    warns = [d for d in result.deviations if d.severity == _STRUCT_WARN]

    if fails:
        return Diagnosis(
            name="structure",
            status=_FAIL,
            message=(
                f"{len(fails)} structural failure(s); tier={result.tier} "
                f"({fails[0].path}: {fails[0].reason})"
            ),
            fix="run `dotagent structure check` for full report; "
                "then `dotagent migrate` if needs_migration is true",
        )
    if result.needs_migration:
        return Diagnosis(
            name="structure",
            status=_WARN,
            message=(
                f"schema version drift: have {result.actual_version or 'none'}, "
                f"expected {result.schema_version}"
            ),
            fix="run `dotagent migrate` to upgrade",
        )
    if warns:
        return Diagnosis(
            name="structure",
            status=_WARN,
            message=f"{len(warns)} structural warning(s); tier={result.tier}",
            fix="run `dotagent structure check` for full report",
        )
    return Diagnosis(
        name="structure",
        status=_OK,
        message=f"canonical structure clean (tier={result.tier})",
    )


def _check_archive_pending(paths: Paths) -> Diagnosis:
    """Report info-level count of entries eligible for archival."""
    try:
        from .archive import scan as _archive_scan
        report = _archive_scan(paths.repo)
    except Exception as exc:  # noqa: BLE001
        return Diagnosis(
            name="archive",
            status=_INFO,
            message=f"archive scan failed: {exc}",
        )
    total = len(report.candidates)
    if total == 0:
        return Diagnosis(name="archive", status=_OK, message="no archive-eligible entries")
    breakdown = ", ".join(f"{k}={v}" for k, v in report.counts.items() if v > 0)
    return Diagnosis(
        name="archive",
        status=_INFO,
        message=f"{total} entry/entries eligible for archive ({breakdown})",
        fix="run `dotagent archive scan` for detail, then `dotagent archive run`",
    )


def run_checks() -> list[Diagnosis]:
    """Run every check. Return a flat list of diagnoses."""
    from .paths import find_repo_root
    repo = find_repo_root()
    paths = Paths(repo=repo)

    out: list[Diagnosis] = []
    out.append(_check_python_version())
    out.append(_check_git_present())
    out.append(_check_anthropic_key())

    agent_check = _check_agent_dir(paths)
    out.append(agent_check)
    if agent_check.status == _FAIL:
        out.extend(_check_optional_extras())
        return out

    cfg = Config.load(paths)
    out.append(_check_canonical_structure(paths))
    out.append(_check_archive_pending(paths))
    out.append(_check_sources(paths, cfg))
    out.append(_check_hooks(paths))
    out.append(_check_episodic_index(paths))
    out.append(_check_cache_gitignored(paths))
    out.extend(_check_optional_extras())
    return out
