"""Context resolver — merges everything an AI agent needs to never lose context.

Pulls together:
- The five `.agent/*.md` source files (style, rules, architecture, patterns, preferences)
- Indexed `docs/*.md` sources (bug registry, anti-patterns, redis keys, db impact map,
  dependency map, architecture docs)
- Semantic memory (graduated patterns/rules + source pointer cards)
- Personal memory (per-actor profile)
- Working memory (current session: branch, recent files, last events)
- Episodic memory (recent activity, optionally filtered to currently-touched files)

Exposes a single `Context` dataclass that adapters render into CLAUDE.md / .cursorrules /
.github/copilot-instructions.md / AGENTS.md / etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .memory import CurrentState, EpisodicMemory, PersonalMemory, WorkingMemory
from .paths import Paths
from .sources import IndexedSource, SourceEntry, load_cache


@dataclass
class AgentSources:
    style: str = ""
    rules: str = ""
    architecture: str = ""
    patterns: str = ""
    preferences: str = ""


@dataclass
class Context:
    project_name: str
    actor: str
    repo_path: str
    agent: AgentSources
    sources: dict[str, IndexedSource]
    semantic_pointer_cards: list[str]
    personal: dict
    current: CurrentState
    recent_episodic: list[dict]
    config_top_n: dict[str, int]
    # Phase 8: project management
    project_plan: object | None = None       # dotagent.project.Project | None
    project_active_module_id: str = ""

    # ---- helpers for adapters ---------------------------------------------

    def top_bugs(self, n: int | None = None) -> list[SourceEntry]:
        n = n if n is not None else self.config_top_n.get("bug_registry_top_n", 15)
        src = self.sources.get("bug_registry")
        if not src or not src.exists:
            return []
        return _rank_by_severity(src.entries)[:n]

    def top_anti_patterns(self, n: int | None = None) -> list[SourceEntry]:
        n = n if n is not None else self.config_top_n.get("anti_patterns_top_n", 10)
        src = self.sources.get("anti_patterns")
        if not src or not src.exists:
            return []
        return _rank_by_severity(src.entries)[:n]

    def redis_keys(self) -> list[SourceEntry]:
        src = self.sources.get("redis_keys")
        return list(src.entries) if src and src.exists else []

    def db_impact(self) -> list[SourceEntry]:
        src = self.sources.get("db_impact_map")
        return list(src.entries) if src and src.exists else []

    def dependency_map(self) -> list[SourceEntry]:
        src = self.sources.get("dependency_map")
        return list(src.entries) if src and src.exists else []

    def architecture_sections(self) -> list[SourceEntry]:
        src = self.sources.get("architecture")
        return list(src.entries) if src and src.exists else []

    def hotspots_for_files(self, files: list[str]) -> dict[str, list[SourceEntry]]:
        """For a list of files, return matching entries from bug-registry / anti-patterns / db / redis."""
        out: dict[str, list[SourceEntry]] = {"bugs": [], "anti_patterns": [], "tables": [], "keys": []}
        files_lower = {f.lower() for f in files if f}
        for kind, key in (("bug_registry", "bugs"), ("anti_patterns", "anti_patterns")):
            src = self.sources.get(kind)
            if not src or not src.exists:
                continue
            for e in src.entries:
                if any(f.lower() in files_lower or any(part in files_lower for part in [f.lower()])
                       for f in e.files):
                    out[key].append(e)
        return out

    # ---- Conflict detection (Module 1) ------------------------------------
    #
    # When the active developer's recent files (working memory) overlap with
    # files cited by semantic rules / bug-registry entries / anti-patterns,
    # surface that overlap as a `Conflict` so the rendered CLAUDE.md can warn
    # the AI agent before the conflicting change lands.

    def detect_conflicts(self, *, top_n: int | None = None) -> list[dict]:
        """Return active-file ↔ rule conflicts, ranked by severity.

        Each returned dict has keys: file, kind, id, title, severity, source_path,
        what_to_do. Empty list if working memory has no files yet OR no rules
        cite those files.
        """
        files = list(self.current.recent_files or [])
        if not files:
            return []
        n = top_n if top_n is not None else self.config_top_n.get("conflicts_top_n", 8)

        rows: list[dict] = []
        for kind_id, kind_label, source_kind in (
            ("bugs",          "bug-registry", "bug_registry"),
            ("anti_patterns", "anti-pattern", "anti_patterns"),
        ):
            src = self.sources.get(source_kind)
            if not src or not src.exists:
                continue
            files_set = {f.lower() for f in files}
            for e in src.entries:
                touched = [f for f in (e.files or []) if f.lower() in files_set]
                if not touched:
                    continue
                rows.append({
                    "file": touched[0],
                    "all_touched_files": touched,
                    "kind": kind_label,
                    "id": e.id,
                    "title": e.title,
                    "severity": e.severity or "unknown",
                    "source_path": src.path,
                    "what_to_do": _conflict_remedy(kind_label, e),
                })

        # Graduated semantic rules can also cite files via their body. Scan
        # `.agent/memory/semantic/rules/` and `.agent/memory/semantic/patterns/`
        # for file references (backtick-wrapped paths) overlapping with the
        # active recent_files.
        from pathlib import Path
        from .paths import Paths
        try:
            paths = Paths(repo=Path(self.repo_path))
            files_set = {f.lower() for f in files}
            for rule_path in self._iter_semantic_rule_files(paths):
                rule_text = ""
                try:
                    rule_text = rule_path.read_text(errors="replace")
                except OSError:
                    continue
                touched = _cited_files_in(rule_text, files_set)
                if not touched:
                    continue
                title = _first_h1(rule_text) or rule_path.stem
                severity = _infer_severity_from_path_or_text(rule_path, rule_text)
                rows.append({
                    "file": touched[0],
                    "all_touched_files": touched,
                    "kind": "semantic-rule",
                    "id": rule_path.stem,
                    "title": title,
                    "severity": severity,
                    "source_path": str(rule_path.relative_to(paths.repo)),
                    "what_to_do": (
                        f"This graduated rule cites a file you're editing — "
                        f"open `{rule_path.relative_to(paths.repo)}` and confirm the "
                        f"change is still consistent with the rule's rationale."
                    ),
                })
        except Exception as e:
            from .logging import log_exception
            log_exception("semantic-rule conflict scan failed", e)

        rows.sort(key=lambda r: (_SEVERITY_ORDER.get(r["severity"], 5), r["id"]))
        return rows[:n]

    def _iter_semantic_rule_files(self, paths):
        """Yield .md files under semantic/rules and semantic/patterns. Skip pointer cards + expired."""
        for sub in ("rules", "patterns"):
            root = paths.semantic / sub
            if not root.exists():
                continue
            for p in root.rglob("*.md"):
                if "expired" in p.parts or "sources" in p.parts:
                    continue
                yield p


_CITED_FILE_RE = __import__("re").compile(
    r"`([\w./\-_]+\.(?:py|js|ts|tsx|jsx|go|rs|rb|java|sql|sh|cjs|mjs|md|yaml|yml|toml|json))`"
)


def _cited_files_in(text: str, files_set: set[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _CITED_FILE_RE.finditer(text):
        f = m.group(1)
        if f.lower() in files_set and f not in seen:
            out.append(f)
            seen.add(f)
    return out


def _first_h1(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _infer_severity_from_path_or_text(path, text: str) -> str:
    """Best-effort: look for a 'severity' field in the rule body; else use the
    rule's category as a coarse signal. `bugs` and `auto-dream` graduations
    default to high so they don't get drowned by medium-severity sources."""
    import re
    m = re.search(r"\*\*Severity\*\*\s*[:：]\s*(\w+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip().lower()
    cat = next((p for p in path.parts if p in ("bugs", "anti-patterns", "auto-dream", "patterns")), "")
    if cat == "bugs":
        return "high"
    if cat == "auto-dream":
        return "high"
    return "medium"


def _conflict_remedy(kind: str, entry: SourceEntry) -> str:
    """One-line 'what to do' hint for a conflict row."""
    if kind == "bug-registry":
        return f"Verify the change does not regress {entry.id} (see body of the entry)."
    if kind == "anti-pattern":
        return f"Review {entry.id} before merging — your change touches files this pattern forbids."
    return f"Review {entry.id} for relevance."



_SEVERITY_ORDER = {"critical": 0, "high": 1, "p0": 0, "p1": 1, "p2": 2, "medium": 2, "low": 3, "p3": 3, "": 4, "unknown": 4}


def _rank_by_severity(entries: list[SourceEntry]) -> list[SourceEntry]:
    return sorted(entries, key=lambda e: (_SEVERITY_ORDER.get(e.severity, 5), e.id))


def _read_agent_sources(paths: Paths) -> AgentSources:
    def _read(p: Path) -> str:
        return p.read_text() if p.exists() else ""
    return AgentSources(
        style=_read(paths.style),
        rules=_read(paths.rules),
        architecture=_read(paths.architecture),
        patterns=_read(paths.patterns),
        preferences=_read(paths.preferences),
    )


def _list_pointer_cards(paths: Paths) -> list[str]:
    if not paths.semantic_sources.exists():
        return []
    return sorted(p.name for p in paths.semantic_sources.glob("*.md"))


def _read_personal(paths: Paths, actor: str) -> dict:
    if not actor:
        return {}
    return PersonalMemory(paths, actor).load()


def _recent_episodic(paths: Paths, actor: str, limit: int, file_filter: list[str] | None = None) -> list[dict]:
    """Return the latest `limit` episodic events. Filtered to files when provided."""
    mem = EpisodicMemory(paths)
    events = list(mem.iter_events())
    events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    if file_filter:
        ff_lower = {f.lower() for f in file_filter}
        filtered = [e for e in events if any(f.lower() in ff_lower for f in e.get("files") or [])]
        events = filtered or events
    return events[:limit]


def build(paths: Paths, *, actor: str = "", config: Config | None = None) -> Context:
    """Build the merged Context. Cheap: reads cache + small files only."""
    if config is None:
        config = Config.load(paths)
    project_name = (config.get("project", "name") or paths.repo.name) if config else paths.repo.name
    sources = load_cache(paths)
    agent_sources = _read_agent_sources(paths)
    pointer_cards = _list_pointer_cards(paths)
    personal = _read_personal(paths, actor) if actor else {}
    current = WorkingMemory(paths, actor).load_current() if actor else CurrentState(actor="")
    n = (config.raw.get("context") or {}).get("recent_activity_top_n", 8) if config else 8
    recent = _recent_episodic(paths, actor, n, current.recent_files or None)
    top_n = dict((config.raw.get("context") or {})) if config else {}

    # Phase 8: load project state if initialized
    project_plan = None
    active_mid = ""
    try:
        from .project import load_project
        from .project.operations import next_recommended_module
        project_plan = load_project(paths)
        if project_plan:
            # active = first in_progress/dev_complete/qa_passed, else recommended next
            from .project.model import ModuleState
            for mid in project_plan.module_ids:
                m = project_plan.modules.get(mid)
                if m and m.state in (
                    ModuleState.IN_PROGRESS,
                    ModuleState.DEV_COMPLETE,
                    ModuleState.QA_PASSED,
                ):
                    active_mid = mid
                    break
            if not active_mid:
                active_mid = next_recommended_module(project_plan) or ""
    except Exception as e:
        from .logging import log_exception
        log_exception("project context load failed", e)

    return Context(
        project_name=project_name,
        actor=actor,
        repo_path=str(paths.repo),
        agent=agent_sources,
        sources=sources,
        semantic_pointer_cards=pointer_cards,
        personal=personal,
        current=current,
        recent_episodic=recent,
        config_top_n=top_n,
        project_plan=project_plan,
        project_active_module_id=active_mid,
    )
