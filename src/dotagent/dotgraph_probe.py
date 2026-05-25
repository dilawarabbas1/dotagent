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

# v0.5.4 — default staleness threshold. Operator-overridable via
# `dotagent.dotgraph.stale_threshold_hours` in `.agent/config.yaml`.
# 168h = 7 days is conservative enough for weekly review cycles without
# being noisy on active projects.
_STALE_AFTER_HOURS_DEFAULT = 168

# Staleness reason codes — surfaced in DotgraphInfo.stale_reasons so the
# orchestrator can branch on the cause.
STALE_REASON_DIRTY = "dirty_files"
STALE_REASON_OLD = "last_indexed_too_old"
STALE_REASON_NO_DB = "db_missing"
STALE_REASON_ERROR = "probe_error"
STALE_REASON_INDEX_FILE_OLDER = "index_file_older_than_sources"  # legacy mtime check

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
    # v0.5.4 — staleness diagnostic surface. `stale_reasons` is an ordered
    # list of reason codes (see STALE_REASON_*); `stale_threshold_hours`
    # is the threshold actually applied. Both additive.
    stale_reasons: list[str] | None = None
    stale_threshold_hours: int | None = None

    def to_dict(self) -> dict:
        return {
            "installed":    self.installed,
            "version":      self.version,
            "db_present":   self.db_present,
            "db_path":      self.db_path,
            "dirty_files":  self.dirty_files,
            "last_indexed": self.last_indexed,
            "stale":        self.stale,
            "stale_reasons":         list(self.stale_reasons) if self.stale_reasons else [],
            "stale_threshold_hours": self.stale_threshold_hours,
            "error":        self.error,
            "files":        self.files,
            "nodes":        self.nodes,
            "edges":        self.edges,
            "unresolved":   self.unresolved,
        }


def probe(
    repo_root: Path,
    *,
    stale_threshold_hours: int | None = None,
) -> DotgraphInfo:
    """Return a DotgraphInfo for the project at `repo_root`.

    Never raises. Every failure mode lands as a typed field on the returned
    struct:

    - dotgraph not on PATH        → installed=False, all other fields null
    - dotgraph crash on `status`  → installed=True, db_present=True,
                                    error=<stderr tail>, stale=True
                                    (treat unparseable as stale by default)

    Staleness (v0.5.4):
    - `dirty_files > 0`                            → STALE_REASON_DIRTY
    - `last_indexed` ≥ `stale_threshold_hours` old → STALE_REASON_OLD
                                                     (default 168h = 7d)
    - source file newer than `last_indexed`        → STALE_REASON_INDEX_FILE_OLDER
    - probe error                                  → STALE_REASON_ERROR
    - missing db                                   → STALE_REASON_NO_DB

    Reasons are surfaced in `info.stale_reasons` (list[str]). Threshold
    in `info.stale_threshold_hours`. `info.stale` is True iff any reason
    fires.

    `stale_threshold_hours` can be overridden by the caller (typically
    from `.agent/config.yaml`'s `dotagent.dotgraph.stale_threshold_hours`).
    """
    threshold = stale_threshold_hours if stale_threshold_hours is not None \
        else _STALE_AFTER_HOURS_DEFAULT

    info = DotgraphInfo(installed=False, stale_threshold_hours=threshold)
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
    # `db_present=False` is NOT stale — it's an unindexed project. Operator
    # action is "run dotgraph index ." not "refresh stale index."
    if not info.db_present:
        info.stale_reasons = []
        return info

    status_json = _run_status_json(repo_root)
    if status_json is None:
        info.stale_reasons = [STALE_REASON_ERROR]
        info.stale = True
        return info
    if isinstance(status_json, dict) and "error" in status_json:
        info.error = status_json["error"]
        info.stale_reasons = [STALE_REASON_ERROR]
        info.stale = True
        return info

    # Map known fields. Unknown fields silently ignored — dotgraph may add more.
    info.files       = _as_int(status_json.get("files"))
    info.dirty_files = _as_int(status_json.get("dirty_files"))
    info.nodes       = _as_int(status_json.get("nodes"))
    info.edges       = _as_int(status_json.get("edges"))
    info.unresolved  = _as_int(status_json.get("unresolved"))
    info.last_indexed = status_json.get("last_indexed")  # may be absent — that's OK

    info.stale, info.stale_reasons = _compute_stale(
        repo_root, info, threshold_hours=threshold,
    )
    return info


def ensure_gitignored(repo_root: Path) -> str:
    """v0.5.4 — pre-seed `.gitignore` with `.dotgraph/` if missing.

    Called once on the emit pre-step so a brand-new dotgraph install
    doesn't commit the .dotgraph/ directory by accident. Idempotent.

    Returns one of:
      - "" — nothing to do (entry already present)
      - "added .dotgraph/ to .gitignore" — appended to existing .gitignore
      - "created .gitignore with .dotgraph/" — wrote a fresh file

    Never raises. Errors (e.g. read-only fs) are returned as empty string.
    """
    gi = Path(repo_root) / ".gitignore"
    entry = ".dotgraph/"
    try:
        if gi.exists():
            text = gi.read_text(errors="replace")
            # Tolerant match — accept `.dotgraph`, `.dotgraph/`, `/.dotgraph/`,
            # with or without a trailing comment. Skip if any variant present.
            for line in text.splitlines():
                stripped = line.strip()
                if stripped in {".dotgraph", ".dotgraph/", "/.dotgraph", "/.dotgraph/"}:
                    return ""
                if stripped.startswith(".dotgraph") or stripped.startswith("/.dotgraph"):
                    return ""
            sep = "" if text.endswith("\n") or text == "" else "\n"
            gi.write_text(text + sep + entry + "\n")
            return "added .dotgraph/ to .gitignore"
        gi.write_text(entry + "\n")
        return "created .gitignore with .dotgraph/"
    except OSError:
        return ""


def emit_docs(
    repo_root: Path,
    *,
    skip_empty: bool = True,
    out_dir: Path | None = None,
    extra_args: list[str] | None = None,
) -> tuple[bool, str, dict]:
    """Run `dotgraph emit-docs --target all` in `repo_root`.

    Returns `(ok, message, payload)`. Best-effort: never raises.
    `ok=False` covers: dotgraph not on PATH, non-zero exit, timeout,
    OSError, JSON parse failure.

    `payload` is the parsed `--json` response from dotgraph when
    available. Shape (dotgraph 0.1.10+):

        {"written": [{"target": str, "path": str, "bytes": int}, ...],
         "skipped": [str, ...],
         "rendered_at": "<ISO>"}

    On older dotgraph that doesn't support `--json`, `payload` is `{}`
    and `message` falls back to a stdout-line summary.

    `skip_empty` defaults to True (v0.5.4 — issue #2). Set False to
    force all 5 docs to be emitted even if a target has no data. The
    runtime config knob `dotagent.dotgraph.emit_docs.skip_empty` (in
    `.agent/config.yaml`) overrides this default per-project.

    `out_dir` overrides dotgraph's default output directory (`<root>/docs/`).
    Pass `<root>/docs/codegraph` to land under the suffix-split layout
    (v0.5.4 — issue #4).

    `extra_args` is appended verbatim to the subprocess command — escape
    hatch for workspace flags that may exist in newer dotgraph builds.
    """
    if shutil.which("dotgraph") is None:
        return False, "dotgraph not on PATH; skipping emit-docs", {}

    cmd = ["dotgraph", "emit-docs", "--target", "all"]
    if skip_empty:
        cmd.append("--skip-empty")
    if out_dir is not None:
        cmd.extend(["--out-dir", str(out_dir)])
    if extra_args:
        cmd.extend(extra_args)
    cmd.append("--json")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"dotgraph emit-docs failed: {exc}", {}

    if result.returncode != 0:
        # Compat fallback: older dotgraph rejects --json and/or --skip-empty.
        # Retry without them so v0.5.4 works against 0.1.8 too.
        stderr_lower = (result.stderr or "").lower()
        unknown_flag = any(
            flag in stderr_lower
            for flag in ("--skip-empty", "--json", "no such option")
        )
        if unknown_flag:
            return _emit_docs_legacy(repo_root, out_dir=out_dir, extra_args=extra_args)
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
        snippet = tail[0][:_STDERR_MAX_CHARS] if tail else "non-zero exit"
        return False, f"dotgraph emit-docs exit={result.returncode}: {snippet}", {}

    # Try JSON first. If stdout doesn't parse (older dotgraph that ignores
    # --json silently), fall back to the line-count summary.
    raw = (result.stdout or "").strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}

    if isinstance(payload, dict) and "written" in payload:
        written = payload.get("written") or []
        skipped = payload.get("skipped") or []
        msg = f"dotgraph emit-docs ok ({len(written)} written"
        if skipped:
            msg += f", {len(skipped)} skipped: {', '.join(skipped)}"
        msg += ")"
        return True, msg, payload

    # Legacy success path — count "wrote ..." lines.
    lines = raw.splitlines()
    if lines:
        return True, f"dotgraph emit-docs ok ({len(lines)} target(s) written)", {}
    return True, "dotgraph emit-docs ok", {}


def _emit_docs_legacy(
    repo_root: Path,
    *,
    out_dir: Path | None = None,
    extra_args: list[str] | None = None,
) -> tuple[bool, str, dict]:
    """Pre-0.1.10 fallback: run emit-docs without --skip-empty / --json."""
    cmd = ["dotgraph", "emit-docs", "--target", "all"]
    if out_dir is not None:
        cmd.extend(["--out-dir", str(out_dir)])
    if extra_args:
        cmd.extend(extra_args)
    try:
        result = subprocess.run(
            cmd, cwd=str(repo_root), capture_output=True, text=True, timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"dotgraph emit-docs failed: {exc}", {}
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
        snippet = tail[0][:_STDERR_MAX_CHARS] if tail else "non-zero exit"
        return False, f"dotgraph emit-docs exit={result.returncode}: {snippet}", {}
    lines = (result.stdout or "").strip().splitlines()
    if lines:
        return True, f"dotgraph emit-docs ok ({len(lines)} target(s) written, legacy mode)", {}
    return True, "dotgraph emit-docs ok", {}


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


def _compute_stale(
    repo_root: Path,
    info: DotgraphInfo,
    *,
    threshold_hours: int = _STALE_AFTER_HOURS_DEFAULT,
) -> tuple[bool, list[str]]:
    """Decide whether the graph is stale, returning reason codes.

    Returns `(is_stale, reasons)` where `reasons` is an ordered list of
    STALE_REASON_* codes explaining WHY. `is_stale` is True iff any
    reason fires.

    Heuristic (v0.5.4):
    1. `dirty_files > 0`                              → STALE_REASON_DIRTY
    2. `last_indexed` older than `threshold_hours`    → STALE_REASON_OLD
       (additionally, if some source file is newer than last_indexed,
        also adds STALE_REASON_INDEX_FILE_OLDER as a sub-signal)
    3. otherwise                                      → fresh, reasons=[]

    The reason list lets `dotagent doctor` (and downstream gates like
    Coda's pre-cycle check) branch on the cause:
      - dirty_files > 0       → tell operator "N files modified since index"
      - too_old AND src_newer → tell operator "index is stale AND drifting"
      - too_old alone         → tell operator "index hasn't been refreshed in N days"

    Source-file mtime walk excludes `.git`, `.dotgraph`, `node_modules`,
    `__pycache__`, `.venv`, `.agent`. Bounded — returns on first match.
    """
    reasons: list[str] = []

    if info.dirty_files is not None and info.dirty_files > 0:
        reasons.append(STALE_REASON_DIRTY)

    if info.last_indexed:
        try:
            last = _parse_iso(info.last_indexed)
            age = datetime.now(timezone.utc) - last
            if age >= timedelta(hours=threshold_hours):
                reasons.append(STALE_REASON_OLD)
                # Optional sub-signal: at least one source file is newer.
                if _any_source_newer_than(repo_root, last):
                    reasons.append(STALE_REASON_INDEX_FILE_OLDER)
        except ValueError:
            # Malformed timestamp from dotgraph → flag stale-with-old reason
            reasons.append(STALE_REASON_OLD)

    return (len(reasons) > 0, reasons)


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


__all__ = ("DotgraphInfo", "probe", "emit_docs", "ensure_gitignored")
