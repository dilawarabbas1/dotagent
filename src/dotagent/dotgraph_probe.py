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
# v0.5.4 — Workspace (multi-repo) support (issue #3)
# ---------------------------------------------------------------------------
#
# Decision A: auto-pivot when `dotgraph-workspace.yml` exists at the repo
# root. dotgraph 0.1.11 ships `dotgraph workspace emit-docs --json` that
# does the per-repo loop on its side — one subprocess call, aggregate
# JSON back. dotagent doesn't parse the workspace YAML at all.

WORKSPACE_FILE = "dotgraph-workspace.yml"


def workspace_present(repo_root: Path) -> bool:
    """True iff `dotgraph-workspace.yml` exists at `repo_root`."""
    return (Path(repo_root) / WORKSPACE_FILE).exists()


def workspace_status(repo_root: Path) -> dict:
    """Read-only workspace summary for `dotagent doctor`.

    Parses `dotgraph-workspace.yml` (stdlib `yaml.safe_load`) to enumerate
    declared child repos, then checks each repo's `.dotgraph/graph.db`
    for presence. Does NOT shell to dotgraph — keeps `doctor` truly
    read-only and fast.

    Returns:
        {"yml_present": bool,
         "repos": [{"name": str, "indexed": bool, "path": str}, ...]}

    `indexed` is True iff `<repo>/.dotgraph/graph.db` exists on disk.
    Returns `{"yml_present": False, "repos": []}` when the yml is
    missing OR malformed. Never raises.
    """
    repo = Path(repo_root)
    yml = repo / WORKSPACE_FILE
    if not yml.exists():
        return {"yml_present": False, "repos": []}

    try:
        import yaml
        data = yaml.safe_load(yml.read_text()) or {}
    except Exception:  # noqa: BLE001 — yaml errors, encoding, etc.
        return {"yml_present": True, "repos": []}

    repos_out: list[dict] = []
    repos_raw = data.get("repos") if isinstance(data, dict) else None
    if not isinstance(repos_raw, list):
        return {"yml_present": True, "repos": []}

    for entry in repos_raw:
        # Tolerant: entries can be plain strings (paths) OR dicts.
        if isinstance(entry, str):
            path_str = entry
            name = Path(path_str).name or path_str
        elif isinstance(entry, dict):
            path_str = entry.get("path") or entry.get("dir") or ""
            name = entry.get("name") or (Path(path_str).name if path_str else "")
            if not name:
                continue
        else:
            continue
        if not path_str:
            continue
        # Resolve relative to repo root
        child = (repo / path_str).resolve() if not Path(path_str).is_absolute() \
                else Path(path_str)
        db = child / ".dotgraph" / "graph.db"
        repos_out.append({
            "name":    str(name),
            "path":    str(child),
            "indexed": db.exists(),
        })
    return {"yml_present": True, "repos": repos_out}


def workspace_index(repo_root: Path) -> tuple[bool, str]:
    """Run `dotgraph workspace index --root <repo>`. Best-effort.

    Returns `(ok, message)`. dotgraph indexes every child repo declared
    in the workspace yml. Used before `workspace_emit_docs` so all child
    repos have a fresh graph.

    Failure modes: missing binary, non-zero exit, timeout. All
    captured; nothing raises.
    """
    if shutil.which("dotgraph") is None:
        return False, "dotgraph not on PATH; skipping workspace index"
    try:
        result = subprocess.run(
            ["dotgraph", "workspace", "index", "--root", str(repo_root)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=600,    # workspace index can be slow on multi-repo
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"dotgraph workspace index failed: {exc}"
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
        snippet = tail[0][:_STDERR_MAX_CHARS] if tail else "non-zero exit"
        return False, f"dotgraph workspace index exit={result.returncode}: {snippet}"
    return True, "dotgraph workspace index ok"


def workspace_emit_docs(
    repo_root: Path,
    *,
    out_subdir: str = "docs/codegraph",
) -> tuple[bool, str, dict]:
    """Run `dotgraph workspace emit-docs --json` and parse the aggregate.

    Returns `(ok, message, payload)`. `payload` shape (dotgraph 0.1.11+):

        {
          "workspace": "redscope",
          "results": [
            {"repo": "backend", "path": "...", "status": "ok",
             "written": [{"target", "path", "bytes"}, ...],
             "skipped": ["kafka-topics", "redis-key-registry"]},
            {"repo": "portal", "path": "...", "status": "ok", ...},
            {"repo": "admin",  "path": "...", "status": "ok", ...}
          ],
          "rendered_at": "..."
        }

    Per-repo `status` may be:
      · "ok"           — emit succeeded; `written` + `skipped` populated
      · "not_indexed"  — repo exists but wasn't indexed (skip silently)
      · "error"        — repo-specific failure; `message` populated

    Best-effort. Never raises.
    """
    if shutil.which("dotgraph") is None:
        return False, "dotgraph not on PATH; skipping workspace emit-docs", {}
    cmd = [
        "dotgraph", "workspace", "emit-docs",
        "--root", str(repo_root),
        "--out-subdir", out_subdir,
        "--json",
    ]
    try:
        result = subprocess.run(
            cmd, cwd=str(repo_root),
            capture_output=True, text=True, timeout=300,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"dotgraph workspace emit-docs failed: {exc}", {}
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
        snippet = tail[0][:_STDERR_MAX_CHARS] if tail else "non-zero exit"
        return False, f"dotgraph workspace emit-docs exit={result.returncode}: {snippet}", {}
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        return False, f"dotgraph workspace emit-docs JSON parse error: {exc}", {}
    if not isinstance(payload, dict):
        return False, "dotgraph workspace emit-docs returned non-dict JSON", {}
    results = payload.get("results") or []
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    err_count = sum(1 for r in results if r.get("status") == "error")
    if err_count:
        msg = f"dotgraph workspace emit-docs partial: {ok_count} ok, {err_count} error"
    else:
        msg = f"dotgraph workspace emit-docs ok ({ok_count} repo(s))"
    return True, msg, payload


def workspace_summary_for_doctor(payload: dict) -> list[dict]:
    """Transform `workspace_emit_docs` payload into the per-repo summary
    rows the doctor block expects:

        [{"name": str, "indexed": bool, "last_indexed": str | None,
          "written": int, "skipped": list[str], "status": str,
          "error": str | None}, ...]

    Empty list when payload is malformed or missing `results`.
    """
    out: list[dict] = []
    for r in (payload or {}).get("results") or []:
        if not isinstance(r, dict):
            continue
        status = r.get("status", "unknown")
        written = r.get("written") or []
        skipped = r.get("skipped") or []
        out.append({
            "name":         r.get("repo") or "",
            "indexed":      status == "ok",
            "status":       status,
            "last_indexed": r.get("last_indexed"),
            "written":      len(written) if isinstance(written, list) else 0,
            "skipped":      list(skipped) if isinstance(skipped, list) else [],
            "error":        r.get("message") or r.get("error"),
        })
    return out


def count_indexable_files(repo_root: Path) -> int:
    """v0.5.4 heuristic — rough count of files dotgraph would index.

    Used when no `dotgraph-workspace.yml` is present to detect "meta repo
    masquerading as code repo." When the count is below the threshold
    (default 20), sync emits a warning suggesting the operator add a
    workspace yml if real code lives in sibling repos.

    Walks the same skip-dirs as `_any_source_newer_than`. Bounded;
    returns the count immediately past the threshold so we don't waste
    time on huge trees. Conservative — extensions matched are the
    common ones dotgraph supports.
    """
    extensions = {
        ".py", ".pyx", ".ts", ".tsx", ".js", ".jsx", ".mjs",
        ".go", ".rs", ".java", ".kt", ".scala", ".swift",
        ".cs", ".rb", ".php", ".vue", ".svelte",
        ".cpp", ".cc", ".c", ".h", ".hpp",
    }
    threshold_cutoff = 50   # stop walking past this; we only care about <20
    n = 0
    try:
        for dirpath, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                if Path(fn).suffix.lower() in extensions:
                    n += 1
                    if n >= threshold_cutoff:
                        return n
    except OSError:
        pass
    return n


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


# ---------------------------------------------------------------------------
# v0.5.4 — Suffix-split layout (issue #4)
# ---------------------------------------------------------------------------
#
# Locked Decision B: dotgraph emits `*.generated.md` filenames under
# `docs/codegraph/`. Hand-maintained `docs/*.md` keeps narrative/intent and
# links to the generated counterpart. Two files per topic; no content loss;
# one extra hop for readers.

CODEGRAPH_SUBDIR = "docs/codegraph"

# Five canonical targets dotgraph emit-docs produces (these are the file
# stems WITHOUT the `.generated` suffix — that's added during rename).
_CODEGRAPH_TARGETS = (
    "dependency-map",
    "db-impact-map",
    "redis-key-registry",
    "kafka-topics",
    "endpoints",
)

# Marker used to identify a doc that has already been patched with a
# reference link to its generated counterpart. Lets us detect "already
# patched" without diff-parsing the file.
_REFERENCE_MARKER = "<!-- dotagent: links to docs/codegraph/ -->"

# Title-cased target names for the reference section header.
_TARGET_TITLES = {
    "dependency-map":     "Dependency map",
    "db-impact-map":      "DB impact map",
    "redis-key-registry": "Redis key registry",
    "kafka-topics":       "Kafka topics",
    "endpoints":          "Endpoints",
}


def apply_codegraph_layout(repo_root: Path) -> tuple[list[str], list[str]]:
    """Rename freshly-emitted `docs/codegraph/<target>.md` files to
    `<target>.generated.md` and patch hand-maintained counterparts.

    Returns `(renamed, patched)` — two lists of relative paths that
    were touched. Both are best-effort; missing files are skipped.

    Behaviour per target (e.g. `dependency-map`):
      1. If `docs/codegraph/dependency-map.md` exists (freshly emitted),
         rename it to `docs/codegraph/dependency-map.generated.md`.
         The `.generated.md` suffix is the contract — humans see at a
         glance "this file is auto-written; edits will be wiped."
      2. If a hand-maintained `docs/dependency-map.md` exists AND
         doesn't already carry the reference marker, prepend a
         one-time reference section pointing readers at the generated
         file. The existing content is preserved verbatim BELOW the
         injected header.
      3. If neither side exists, do nothing for that target.

    Idempotent: re-running after the first patch is a no-op (marker
    check + rename target already exists).
    """
    repo = Path(repo_root)
    codegraph_dir = repo / CODEGRAPH_SUBDIR

    renamed: list[str] = []
    patched: list[str] = []

    if not codegraph_dir.is_dir():
        return renamed, patched

    for target in _CODEGRAPH_TARGETS:
        # Step 1: rename emitted file
        raw = codegraph_dir / f"{target}.md"
        generated = codegraph_dir / f"{target}.generated.md"
        if raw.exists():
            try:
                # If the generated path already exists (re-run), overwrite
                # it with the latest content rather than holding both.
                if generated.exists():
                    generated.unlink()
                raw.rename(generated)
                renamed.append(str(generated.relative_to(repo)))
            except OSError:
                pass

        # Step 2: patch hand-maintained counterpart (one-time)
        hand = repo / "docs" / f"{target}.md"
        if hand.exists() and generated.exists():
            try:
                body = hand.read_text(errors="replace")
                if _REFERENCE_MARKER in body:
                    continue   # already patched
                title = _TARGET_TITLES.get(target, target.replace("-", " ").title())
                header = (
                    f"{_REFERENCE_MARKER}\n"
                    f"## {title}\n\n"
                    f"> Auto-generated section is in "
                    f"[`{target}.generated.md`](./codegraph/{target}.generated.md). "
                    f"Update narrative / intent below.\n\n"
                    f"---\n\n"
                )
                hand.write_text(header + body)
                patched.append(str(hand.relative_to(repo)))
            except OSError:
                pass

    return renamed, patched


__all__ = (
    "DotgraphInfo", "probe", "emit_docs", "ensure_gitignored",
    "apply_codegraph_layout", "CODEGRAPH_SUBDIR",
    "workspace_present", "workspace_status", "workspace_index",
    "workspace_emit_docs", "workspace_summary_for_doctor",
    "count_indexable_files",
    "WORKSPACE_FILE",
    "STALE_REASON_DIRTY", "STALE_REASON_OLD", "STALE_REASON_INDEX_FILE_OLDER",
    "STALE_REASON_ERROR", "STALE_REASON_NO_DB",
)
