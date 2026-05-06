"""Auto-Dream signal extraction.

Heuristic signals (no embeddings yet — Phase 5 walking skeleton):
- revert_cluster:        2+ revert events within window
- repeat_fix:            same file appears in 3+ fix-prefixed commits
- cross_actor_anti:      multiple actors hit the same bug-registry entry
- frequent_failure:      same error name surfaces in 3+ episodic events
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .. import episodic_index
from ..paths import Paths
from ..sources import load_cache


@dataclass
class Signal:
    id: str
    kind: str
    title: str
    weight: int = 1
    actors: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


_REVERT = re.compile(r"\brevert\b", re.IGNORECASE)
_FIX = re.compile(r"^(fix|hotfix|bug)[: (\!]", re.IGNORECASE)
_ERROR = re.compile(r"\b([A-Z][A-Za-z0-9_]+(?:Error|Exception))\b")


def extract_signals(paths: Paths, *, since: str = "30d", min_cluster_size: int = 3) -> list[Signal]:
    episodic_index.ensure_indexed(paths)
    since_iso = episodic_index.parse_since(since)
    events = episodic_index.activity(paths, since_iso=since_iso, limit=5000)
    out: list[Signal] = []

    # revert_cluster
    reverts = [e for e in events if _REVERT.search(e.get("summary", "") or "") or e.get("kind") == "revert"]
    if len(reverts) >= 2:
        out.append(Signal(
            id="revert_cluster",
            kind="revert_cluster",
            title=f"{len(reverts)} reverts in last {since}",
            weight=len(reverts),
            actors=sorted({e.get("actor", "") for e in reverts}),
            tools=sorted({e.get("tool", "") for e in reverts}),
            files=sorted({f for e in reverts for f in (e.get("files") or [])}),
            evidence=[f"{e['ts'][:10]} {e.get('actor', '')}: {e.get('summary', '')[:80]}" for e in reverts[:10]],
        ))

    # repeat_fix per file
    fix_files: Counter[str] = Counter()
    fix_actors: dict[str, set[str]] = defaultdict(set)
    fix_evidence: dict[str, list[str]] = defaultdict(list)
    for e in events:
        if _FIX.match(e.get("summary", "") or ""):
            for f in e.get("files") or []:
                fix_files[f] += 1
                fix_actors[f].add(e.get("actor", ""))
                fix_evidence[f].append(f"{e['ts'][:10]} {e.get('actor', '')}: {e.get('summary', '')[:80]}")
    for f, n in fix_files.items():
        if n >= min_cluster_size:
            out.append(Signal(
                id=f"repeat_fix:{f}",
                kind="repeat_fix",
                title=f"`{f}` was fix-touched {n} times in last {since}",
                weight=n,
                actors=sorted(fix_actors[f]),
                files=[f],
                evidence=fix_evidence[f][:8],
            ))

    # frequent_failure: errors mentioned in summaries
    err_count: Counter[str] = Counter()
    err_evidence: dict[str, list[str]] = defaultdict(list)
    for e in events:
        s = e.get("summary", "") or ""
        for m in _ERROR.finditer(s):
            err_count[m.group(1)] += 1
            err_evidence[m.group(1)].append(f"{e['ts'][:10]} {e.get('actor', '')}: {s[:80]}")
    for err, n in err_count.items():
        if n >= min_cluster_size:
            out.append(Signal(
                id=f"frequent_failure:{err}",
                kind="frequent_failure",
                title=f"`{err}` appeared {n} times in last {since}",
                weight=n,
                evidence=err_evidence[err][:8],
            ))

    # cross_actor_anti: bug-registry entries with multiple touching actors recently
    sources = load_cache(paths)
    bug_src = sources.get("bug_registry")
    if bug_src and bug_src.exists:
        for entry in bug_src.entries:
            actors_seen: set[str] = set()
            ev_evidence: list[str] = []
            for e in events:
                if any(f in (e.get("files") or []) for f in entry.files):
                    actors_seen.add(e.get("actor", ""))
                    ev_evidence.append(f"{e['ts'][:10]} {e.get('actor', '')}: {e.get('summary', '')[:80]}")
            if len(actors_seen) >= 2:
                out.append(Signal(
                    id=f"cross_actor_anti:{entry.id}",
                    kind="cross_actor_anti",
                    title=f"bug `{entry.id}` ({entry.title}) hit by {len(actors_seen)} actors",
                    weight=len(actors_seen),
                    actors=sorted(actors_seen),
                    files=entry.files,
                    evidence=ev_evidence[:8],
                ))
    return out
