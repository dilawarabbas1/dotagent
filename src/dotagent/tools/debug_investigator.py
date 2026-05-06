"""Debug Investigator — given a stack trace, walk episodic memory for similar past failures."""

from __future__ import annotations

import re
from collections import Counter

from .. import episodic_index
from ..paths import Paths
from ..sources import load_cache


_FILE_REF = re.compile(r"""(?:File\s+"|in\s+|at\s+|\s)([\w./\-_]+\.(?:py|js|ts|tsx|jsx|go|rs|rb|java)):?(\d+)?""")
_ERROR_NAME = re.compile(r"\b([A-Z][A-Za-z0-9_]+(?:Error|Exception|Warning))\b")
_FN_NAME = re.compile(r"\b([a-z_][a-zA-Z0-9_]{2,40})\(", re.MULTILINE)


def _signature(stack: str) -> dict:
    files = sorted({m.group(1) for m in _FILE_REF.finditer(stack)})
    errors = sorted({m.group(1) for m in _ERROR_NAME.finditer(stack)})
    fns = [m.group(1) for m in _FN_NAME.finditer(stack)]
    return {"files": files, "errors": errors, "fn_freq": Counter(fns)}


def investigate_stack(paths: Paths, stack: str, *, limit: int = 10) -> dict:
    """Match a stack trace against episodic memory + bug registry. Returns findings."""
    sig = _signature(stack)
    findings: dict = {"signature": sig, "episodic_matches": [], "bug_matches": []}

    episodic_index.ensure_indexed(paths)

    # episodic matches: events touching any signature file, or summary mentioning an error name
    seen_ids: set[int] = set()
    for f in sig["files"]:
        for r in episodic_index.timeline(paths, f, limit=limit):
            key = (r["ts"], r.get("actor", ""), r.get("kind", ""))
            if key in seen_ids:
                continue
            seen_ids.add(key)
            findings["episodic_matches"].append({**r, "match_via": f"file:{f}"})
    for err in sig["errors"]:
        for r in episodic_index.search_summary(paths, err, limit=limit):
            key = (r["ts"], r.get("actor", ""), r.get("kind", ""))
            if key in seen_ids:
                continue
            seen_ids.add(key)
            findings["episodic_matches"].append({**r, "match_via": f"error:{err}"})

    # bug registry matches: bugs whose files overlap signature files
    sources = load_cache(paths)
    bug_src = sources.get("bug_registry")
    if bug_src and bug_src.exists:
        for e in bug_src.entries:
            ev_files = {f.lower() for f in e.files}
            if any(f.lower() in ev_files for f in sig["files"]):
                findings["bug_matches"].append({
                    "id": e.id, "title": e.title, "severity": e.severity,
                    "files": e.files, "snippet": (e.body or "")[:200],
                })

    findings["episodic_matches"] = findings["episodic_matches"][:limit]
    findings["bug_matches"] = findings["bug_matches"][:limit]
    return findings
