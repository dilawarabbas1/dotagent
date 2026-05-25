"""dotgraph integration probe — read-only checks for the doctor + sync.

dotagent calls dotgraph (a separate tool) in two places:
- `dotagent doctor` reports dotgraph health alongside its own checks.
- `dotagent sync` invokes `dotgraph emit-docs --target all` as a pre-step.

This module owns the IPC: subprocess calls, version parsing, status JSON
shape coercion, freshness heuristics. All functions are best-effort —
dotgraph missing or broken NEVER raises out of here. Failures land as
structured fields the caller can branch on.

Why a separate module: the doctor and sync command both need this, and
keeping it isolated makes it trivially mock-able in tests via PATH
shimming.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# dotgraph emits its version via `dotgraph --version`. Click's default format
# is "<prog>, version <ver>". We strip the prefix so consumers see just X.Y.Z.
_VERSION_PREFIX_RE = re.compile(r"^dotgraph,\s+version\s+", re.IGNORECASE)

# How long since `last_indexed` is "fresh enough" before we consider the graph
# stale, when status doesn't expose dirty_files. Used only as a fallback —
# the primary staleness signal is `dirty_files > 0`.
_STALE_AFTER = timedelta(hours=24)

# Maximum stderr tail we report on `status` failures; long stack traces just
# noise up the JSON.
_STDERR_MAX_CHARS = 240


@dataclass
class DotgraphInfo:
    """Read-only snapshot of dotgraph's state in a repo.

    Fields mirror the spec's expected `doctor --format json :: .dotgraph` shape.
    """
    installed: bool
    version: str | None = None
    db_present: bool = False
    db_path: str | None = None
    dirty_files: int | None = None
    last_indexed: str | None = None
    stale: bool = False
    error: str | None = None
    # Bonus fields (not in the spec, but harmless and useful for the text
    # render). Set when status JSON returns them.
    files: int | None = None
    nodes: int | None = None
    edges: int | None = None
    unresolved: int | None = None

    def to_dict(self) -> dict:
        return {
            "installed":    self.installed,
            "version":      self.version,
            "db_present":   self.db_present,
            "db_path":      self.db_path,
            "dirty_files":  self.dirty_files,
            "last_indexed": self.last_indexed,
            "stale":        self.stale,
            "error":        self.error,
            "files":        self.files,
            "nodes":        self.nodes,
            "edges":        self.edges,
            "unresolved":   self.unresolved,
        }


def probe(repo_root: Path) -> DotgraphInfo:
    """Return a DotgraphInfo for the project at `repo_root`.

    Never raises. Every failure mode lands as a typed field on the returned
    struct:

    - dotgraph not on PATH        → installed=False, all other fields null
    - dotgraph crash on `status`  → installed=True, db_present=True,
                                    error=<stderr tail>, stale=True
                                    (treat unparseable as stale by default)

    Staleness heuristic:
    - `dirty_files > 0`                                   → stale
    - `last_indexed` older than 24h AND a source file is newer → stale
    - `last_indexed` not available from `status` JSON     → stale only if
                                                            `dirty_files > 0`
    - everything else                                     → fresh
    """
    info = DotgraphInfo(installed=False)
    if shutil.which("dotgraph") is None:
        return info
    info.installed = True
    info.version = _read_version()

    db = Path(repo_root) / ".dotgraph" / "graph.db"
    info.db_present = db.exists()
    if info.db_present:
        info.db_path = str(db.relative_to(repo_root)) if db.is_absolute() else str(db)

    # Status is meaningful only when the db exists; otherwise dotgraph itself
    # would raise. Don't even attempt — saves a subprocess on cold projects.
    if not info.db_present:
        return info

    status_json = _run_status_json(repo_root)
    if status_json is None:
        # status subprocess crashed; treat as stale by default
        info.stale = True
        return info
    if isinstance(status_json, dict) and "error" in status_json:
        info.error = status_json["error"]
        info.stale = True
        return info

    # Map known fields. Unknown fields silently ignored — dotgraph may add more.
    info.files       = _as_int(status_json.get("files"))
    info.dirty_files = _as_int(status_json.get("dirty_files"))
    info.nodes       = _as_int(status_json.get("nodes"))
    info.edges       = _as_int(status_json.get("edges"))
    info.unresolved  = _as_int(status_json.get("unresolved"))
    info.last_indexed = status_json.get("last_indexed")  # may be absent — that's OK
    info.stale       = _compute_stale(repo_root, info)
    return info


def emit_docs(repo_root: Path) -> tuple[bool, str]:
    """Run `dotgraph emit-docs --target all` in `repo_root`.

    Returns `(ok, message)`. Best-effort: never raises. `ok=False` covers:
    - dotgraph not on PATH
    - non-zero exit
    - timeout (>120s)
    - any OSError / subprocess error

    `message` is short — single line. Suitable for the sync logger's
    `· dotgraph emit-docs ...` line.
    """
    if shutil.which("dotgraph") is None:
        return False, "dotgraph not on PATH; skipping emit-docs"
    try:
        result = subprocess.run(
            ["dotgraph", "emit-docs", "--target", "all"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"dotgraph emit-docs failed: {exc}"
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
        snippet = tail[0][:_STDERR_MAX_CHARS] if tail else "non-zero exit"
        return False, f"dotgraph emit-docs exit={result.returncode}: {snippet}"
    # Success — extract a short summary from the last stdout line if useful.
    lines = (result.stdout or "").strip().splitlines()
    if lines:
        # Common emit-docs output is "wrote path/to/doc.md" per target.
        return True, f"dotgraph emit-docs ok ({len(lines)} target(s) written)"
    return True, "dotgraph emit-docs ok"


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _read_version() -> str | None:
    try:
        result = subprocess.run(
            ["dotgraph", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    raw = (result.stdout or result.stderr or "").strip()
    # "dotgraph, version 0.1.8" → "0.1.8"
    stripped = _VERSION_PREFIX_RE.sub("", raw).strip()
    return stripped or None


def _run_status_json(repo_root: Path) -> dict | None:
    try:
        result = subprocess.run(
            ["dotgraph", "status", "--json"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"error": f"status subprocess error: {exc}"[:_STDERR_MAX_CHARS]}
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-_STDERR_MAX_CHARS:]
        return {"error": f"status exit={result.returncode}: {tail}"}
    try:
        parsed = json.loads(result.stdout or "{}")
        if isinstance(parsed, dict):
            return parsed
        return {"error": "status JSON was not a dict"}
    except json.JSONDecodeError as exc:
        return {"error": f"status JSON parse error: {exc}"[:_STDERR_MAX_CHARS]}


def _as_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _compute_stale(repo_root: Path, info: DotgraphInfo) -> bool:
    """Decide whether the graph is stale.

    Heuristic (documented in the module docstring):
    1. `dirty_files > 0`                       → stale
    2. `last_indexed` older than 24h AND some
       source file mtime > last_indexed        → stale
    3. otherwise                               → fresh

    Source-file mtime check walks the repo (excluding `.git`, `.dotgraph`,
    `node_modules`, `__pycache__`, `.venv`, `.agent/.cache`) but bounds the
    scan: returns True on the first newer file found. Empirically this is
    <50ms on a 10k-file repo.
    """
    if info.dirty_files is not None and info.dirty_files > 0:
        return True
    if not info.last_indexed:
        # No timestamp from status — we can't compute mtime-vs-indexed.
        # Conservative: not stale (we have no evidence either way).
        return False
    try:
        last = _parse_iso(info.last_indexed)
    except ValueError:
        return True   # malformed timestamp from dotgraph → flag stale
    if datetime.now(timezone.utc) - last < _STALE_AFTER:
        return False
    # Older than 24h — check whether any source file is newer.
    return _any_source_newer_than(repo_root, last)


_SKIP_DIRS = {
    ".git", ".dotgraph", "node_modules", "__pycache__",
    ".venv", "venv", ".agent",
}


def _any_source_newer_than(repo_root: Path, threshold: datetime) -> bool:
    """Walk repo for any non-skip file with mtime > threshold."""
    threshold_ts = threshold.timestamp()
    try:
        for dirpath, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                full = Path(dirpath) / fn
                try:
                    if full.stat().st_mtime > threshold_ts:
                        return True
                except OSError:
                    continue
    except OSError:
        pass
    return False


def _parse_iso(ts: str) -> datetime:
    """Parse ISO-8601 with trailing Z tolerated."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


__all__ = ("DotgraphInfo", "probe", "emit_docs")
