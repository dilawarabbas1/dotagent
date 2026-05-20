"""Doc-coverage mapper.

Given a set of changed file paths, return the checklist of hand-maintained
docs that should be updated, based on:

  1. The feature_master.md / feature_master/FM-###-<slug>.md mapping
     (parsed from disk; tolerant to format variation).
  2. Join-key heuristics from docs/HAND_MAINTAINED_DOCS_CONVENTION.md:
       - db-touching path  → db-impact-map-{master,tenant,vector}.md
       - redis-touching    → redis-key-registry-{tenant,global,events}.md
       - host/route/port   → ops/service-registry.md
       - any code change   → anti-patterns.md (invariant check)
       - bug-fix commit    → bug-registry-{infra,agents,orchestrator}.md
       - always            → matching feature_master/FM-###-<slug>.md files:

Output is a structured report consumable as JSON (for Coda's Prompt 2
field #4) or as a human-readable checklist for debugging.

dotagent NEVER writes to any of these files — this module only READS the
hand-maintained structure to build a recommendation list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Public data shapes
# ---------------------------------------------------------------------------

# Required-doc severity:
#   HARD       — file is explicitly listed in an FM's files: section.
#   SUGGESTED  — heuristic match (file path looks DB-ish, Redis-ish, etc.).
#   CHECK      — always applies (anti-patterns invariant scan).
SEVERITY_HARD = "hard"
SEVERITY_SUGGESTED = "suggested"
SEVERITY_CHECK = "check"


@dataclass
class RequiredDoc:
    """One row of 'update this doc' guidance."""
    path: str                       # the doc to update (relative to repo)
    severity: str                   # SEVERITY_HARD / SUGGESTED / CHECK
    reason: str                     # one-line "because this file …"


@dataclass
class FileCoverage:
    """Coverage report for one changed file."""
    path: str
    fm_ids: list[str] = field(default_factory=list)
    required_docs: list[RequiredDoc] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "fm_ids": list(self.fm_ids),
            "required_docs": [
                {"path": d.path, "severity": d.severity, "reason": d.reason}
                for d in self.required_docs
            ],
        }


@dataclass
class CoverageReport:
    files: list[FileCoverage] = field(default_factory=list)
    unmapped_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "files": [f.to_dict() for f in self.files],
            "unmapped_files": list(self.unmapped_files),
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# FM-### parser
# ---------------------------------------------------------------------------

_FM_ID_RE = re.compile(r"FM-(\d{2,4})")
# Matches a file path inside backticks. Permissive — file paths can contain
# letters, digits, /, _, ., -, *, and we tolerate quoting nuances.
_BACKTICK_PATH_RE = re.compile(r"`([^`\s][^`]*?)`")
# Section header recognising "## files", "## Files", "## Files:", etc.
_FILES_HEADING_RE = re.compile(r"^#{1,6}\s+files?\s*:?\s*$", re.IGNORECASE)
# Next H2/H3 heading after the files section (we stop parsing here).
_ANY_HEADING_RE = re.compile(r"^#{1,6}\s+\S")


def parse_fm_index(repo: Path) -> dict[str, str]:
    """Parse docs/feature_master/*.md and return path -> FM-### map.

    Strategy: for every `FM-NNN-*.md` file under `docs/feature_master/`,
    extract its FM-### id from the filename, then walk the file looking
    for a `## files` (or similar) heading, then collect backtick-quoted
    paths that follow until the next heading or EOF.

    Returns a dict mapping each declared file path to the FM-### that
    claims it. If multiple FMs claim the same file, both are kept (the
    map becomes path -> last-wins). For full multi-mapping use
    `parse_fm_index_multi`.
    """
    return {p: ids[0] for p, ids in parse_fm_index_multi(repo).items()}


def parse_fm_index_multi(repo: Path) -> dict[str, list[str]]:
    """Same as `parse_fm_index` but a file may map to multiple FM-###s."""
    out: dict[str, list[str]] = {}
    fm_dir = repo / "docs" / "feature_master"
    if not fm_dir.is_dir():
        return out
    for md in sorted(fm_dir.glob("FM-*.md")):
        fm_id = _extract_fm_id_from_filename(md.name)
        if not fm_id:
            continue
        for path in _extract_files_section(md):
            out.setdefault(path, []).append(fm_id)
    return out


def _extract_fm_id_from_filename(name: str) -> str:
    """Pull the FM-### id from a filename like `FM-014-auth.md`."""
    m = _FM_ID_RE.search(name)
    return f"FM-{m.group(1)}" if m else ""


def _extract_files_section(md_path: Path) -> list[str]:
    """Read an FM-### markdown file and return the list of declared
    file paths (backtick-quoted) under its `## files` heading.

    Defensive: tolerates missing heading, mixed casing, alternate
    section names, and free-text annotations after each path.
    """
    try:
        text = md_path.read_text(errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    in_files = False
    paths: list[str] = []
    for line in lines:
        if not in_files:
            if _FILES_HEADING_RE.match(line):
                in_files = True
            continue
        # In the files section. Stop at the next heading.
        if _ANY_HEADING_RE.match(line):
            break
        # Collect every backtick-quoted token that looks like a path.
        for token in _BACKTICK_PATH_RE.findall(line):
            if _looks_like_path(token):
                paths.append(token)
    return paths


def _looks_like_path(s: str) -> bool:
    """Heuristic: backtick-quoted tokens we treat as paths.

    Filters out things like `users` (table name, no slash/dot/star), but
    keeps `src/auth.py`, `routes/*.ts`, `db/users.sql`, etc.
    """
    s = s.strip()
    if not s:
        return False
    return ("/" in s) or ("." in s) or ("*" in s)


# ---------------------------------------------------------------------------
# Join-key heuristics
# ---------------------------------------------------------------------------

# Each rule: (name, predicate, [(doc_path, severity, reason_template)]).
# Predicate is a function `path -> bool`. Reason template gets the path
# interpolated with `{path}` if it includes the placeholder.

_DB_RE = re.compile(
    r"(?:^|/)(?:db|database|models?|migrations?|repos?|schema|sql|orm)(?:/|$|\.)",
    re.IGNORECASE,
)
_REDIS_RE = re.compile(r"(?:^|/)(?:redis|cache)(?:/|$|\.)|redis_client|redis\.", re.IGNORECASE)
_ROUTE_RE = re.compile(
    r"(?:^|/)(?:routes?|controllers?|api|handlers?|endpoints?)(?:/|$|\.)",
    re.IGNORECASE,
)
_HOST_RE = re.compile(
    r"(?:^|/)(?:pm2|ecosystem|docker|deploy|nginx)(?:[/.]|\.config|$)|"
    r"(?:^|/)(?:server|worker|daemon|consumer|producer)\.(?:py|ts|js|mjs)$",
    re.IGNORECASE,
)


def _touches_db(path: str) -> bool:
    return bool(_DB_RE.search(path))


def _touches_redis(path: str) -> bool:
    return bool(_REDIS_RE.search(path))


def _touches_route(path: str) -> bool:
    return bool(_ROUTE_RE.search(path))


def _touches_host(path: str) -> bool:
    return bool(_HOST_RE.search(path))


def _heuristic_docs_for(path: str) -> list[RequiredDoc]:
    """Apply every heuristic rule to one path; collect matching docs."""
    docs: list[RequiredDoc] = []
    if _touches_db(path):
        for shard in ("master", "tenant", "vector"):
            docs.append(RequiredDoc(
                path=f"docs/db-impact-map-{shard}.md",
                severity=SEVERITY_SUGGESTED,
                reason=f"`{path}` looks DB-related — update the relevant shard's file→table map.",
            ))
    if _touches_redis(path):
        for scope in ("tenant", "global", "events"):
            docs.append(RequiredDoc(
                path=f"docs/redis-key-registry-{scope}.md",
                severity=SEVERITY_SUGGESTED,
                reason=f"`{path}` looks Redis-related — update the relevant scope's key map.",
            ))
    if _touches_host(path):
        docs.append(RequiredDoc(
            path="docs/ops/service-registry.md",
            severity=SEVERITY_SUGGESTED,
            reason=f"`{path}` looks like a host/process file — verify pm2 mode · port · restart entry.",
        ))
    if _touches_route(path):
        docs.append(RequiredDoc(
            path="docs/feature_master/FM-###-<slug>.md",
            severity=SEVERITY_SUGGESTED,
            reason=(
                f"`{path}` looks like a route/controller — confirm the matching feature's "
                "`files:` section includes it (and its route is documented)."
            ),
        ))
    return docs


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

# Commit-message patterns that imply a bug-fix → bug-registry update.
_BUG_PREFIX_RE = re.compile(
    r"(?:DA-BUG|BUG)-(INFRA|AGT|ORCH|INFRASTRUCTURE|AGENTS|ORCHESTRATOR)-(\d+)",
    re.IGNORECASE,
)
_BUG_LAYER_TO_FILE = {
    "INFRA": "docs/bug-registry-infrastructure.md",
    "INFRASTRUCTURE": "docs/bug-registry-infrastructure.md",
    "AGT": "docs/bug-registry-agents.md",
    "AGENTS": "docs/bug-registry-agents.md",
    "ORCH": "docs/bug-registry-orchestrator.md",
    "ORCHESTRATOR": "docs/bug-registry-orchestrator.md",
}


def doc_coverage(
    repo: Path,
    changed_files: list[str],
    *,
    commit_msg: str = "",
) -> CoverageReport:
    """Build a CoverageReport for the given changed-file set.

    `repo` is the repository root; `changed_files` are repo-relative
    paths; `commit_msg` is optional and used only to detect bug-fix
    intent (DA-BUG-LAYER-NNN tokens).
    """
    report = CoverageReport()
    fm_map = parse_fm_index_multi(repo)
    if not fm_map and not (repo / "docs" / "feature_master.md").exists():
        report.warnings.append(
            "No docs/feature_master.md or docs/feature_master/ found — "
            "FM-### mapping is empty; only heuristic suggestions returned."
        )

    bug_targets = _bug_registry_targets_from_commit(commit_msg)

    for changed in changed_files:
        cov = FileCoverage(path=changed)
        # HARD mapping from FM-###-<slug>.md files: section
        fm_ids = _match_fm(changed, fm_map)
        cov.fm_ids = fm_ids
        for fm_id in fm_ids:
            cov.required_docs.append(RequiredDoc(
                path=_fm_doc_path(repo, fm_id) or
                     f"docs/feature_master/{fm_id}-<slug>.md",
                severity=SEVERITY_HARD,
                reason=(
                    f"`{changed}` is declared in {fm_id}'s `files:` section — "
                    "update that feature's record if behaviour, route, "
                    "deps, or invariants changed."
                ),
            ))
        # SUGGESTED heuristic matches
        cov.required_docs.extend(_heuristic_docs_for(changed))
        # CHECK (always) — anti-patterns invariant scan
        cov.required_docs.append(RequiredDoc(
            path="docs/anti-patterns.md",
            severity=SEVERITY_CHECK,
            reason=(
                "Always: review whether this change introduces or fixes an "
                "anti-pattern. Add an AP-### entry if so."
            ),
        ))
        # CHECK — bug-fix commits
        for layer_doc in bug_targets:
            cov.required_docs.append(RequiredDoc(
                path=layer_doc,
                severity=SEVERITY_CHECK,
                reason=(
                    "Commit message cites a bug id — mark `status: fixed`, "
                    "add `fix-frozen: <date>` + `fix-sha: <sha>`, and link "
                    "any guard test."
                ),
            ))

        # Deduplicate while preserving order
        cov.required_docs = _dedupe_docs(cov.required_docs)

        if not cov.fm_ids:
            report.unmapped_files.append(changed)
        report.files.append(cov)

    return report


def _match_fm(changed: str, fm_map: dict[str, list[str]]) -> list[str]:
    """Find FM-### ids that claim `changed`. Supports glob entries
    (e.g. an FM record listing `src/api/auth/*.ts`).
    """
    if not fm_map:
        return []
    matched: list[str] = []
    for declared, ids in fm_map.items():
        if _path_matches(changed, declared):
            for fm_id in ids:
                if fm_id not in matched:
                    matched.append(fm_id)
    return matched


def _path_matches(changed: str, declared: str) -> bool:
    """`changed` is concrete; `declared` may be exact or a glob."""
    if changed == declared:
        return True
    # Glob handling — convert simple `*` and `**` to regex.
    if "*" in declared:
        pattern = re.escape(declared).replace(r"\*\*", r".*").replace(r"\*", r"[^/]*")
        return bool(re.fullmatch(pattern, changed))
    return False


def _fm_doc_path(repo: Path, fm_id: str) -> str:
    """Find the actual filename for an FM-### in docs/feature_master/.
    Returns the repo-relative path, or empty string if not found.
    """
    fm_dir = repo / "docs" / "feature_master"
    if not fm_dir.is_dir():
        return ""
    for md in fm_dir.glob(f"{fm_id}-*.md"):
        return md.relative_to(repo).as_posix()
    return ""


def _bug_registry_targets_from_commit(commit_msg: str) -> list[str]:
    """Extract bug-registry shard paths implied by commit-message bug ids."""
    if not commit_msg:
        return []
    out: list[str] = []
    for m in _BUG_PREFIX_RE.finditer(commit_msg):
        layer = m.group(1).upper()
        target = _BUG_LAYER_TO_FILE.get(layer)
        if target and target not in out:
            out.append(target)
    return out


def _dedupe_docs(docs: list[RequiredDoc]) -> list[RequiredDoc]:
    """Keep first occurrence of each (path, severity) pair."""
    seen: set[tuple[str, str]] = set()
    out: list[RequiredDoc] = []
    for d in docs:
        key = (d.path, d.severity)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


__all__ = (
    "CoverageReport",
    "FileCoverage",
    "RequiredDoc",
    "SEVERITY_CHECK",
    "SEVERITY_HARD",
    "SEVERITY_SUGGESTED",
    "doc_coverage",
    "parse_fm_index",
    "parse_fm_index_multi",
)
