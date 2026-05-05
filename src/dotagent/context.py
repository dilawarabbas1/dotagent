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
    )
