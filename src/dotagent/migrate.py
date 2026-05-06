"""Lossless migrator from Claude-Code-Optimization layout to dotagent.

Reads:
- docs/bug-registry.md, docs/anti-patterns.md, docs/redis-key-registry.md,
  docs/db-impact-map.md, docs/dependency-map.md  → registered as `sources` in
  config.yaml (NOT copied; references only).
- prompts/*.md  → copied into .agent/skills/ (renamed to slugs).
- .claude/hooks/*.sh  → bridged via dotagent observe (no copy).
- existing CLAUDE.md  → ingested into .agent/*.md buckets.

Returns a report describing what was wired vs. left untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, merge_defaults
from .ingest import ingest_existing
from .paths import Paths
from .util import dump_yaml, slugify


@dataclass
class MigrationReport:
    referenced_sources: list[str] = field(default_factory=list)
    imported_skills: list[str] = field(default_factory=list)
    ingested_buckets: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


_CCO_SOURCES = {
    "bug_registry": "docs/bug-registry.md",
    "anti_patterns": "docs/anti-patterns.md",
    "redis_keys": "docs/redis-key-registry.md",
    "db_impact_map": "docs/db-impact-map.md",
    "dependency_map": "docs/dependency-map.md",
    "architecture": "docs/architecture.md",
}


def migrate(paths: Paths, *, write: bool = True) -> MigrationReport:
    repo = paths.repo
    report = MigrationReport()

    # 1. Wire docs/ → sources in config.yaml
    cfg_data = Config.load(paths).raw or merge_defaults({"project": {"name": repo.name}})
    cfg_data.setdefault("sources", {})
    for name, rel in _CCO_SOURCES.items():
        if (repo / rel).exists():
            cfg_data["sources"][name] = rel
            report.referenced_sources.append(rel)
    if write:
        dump_yaml(paths.config, cfg_data)

    # 2. Import prompts/*.md into .agent/skills/
    prompts_dir = repo / "prompts"
    if prompts_dir.exists():
        paths.skills.mkdir(parents=True, exist_ok=True)
        for p in sorted(prompts_dir.glob("*.md")):
            slug = slugify(p.stem)
            target = paths.skills / f"imported-{slug}.md"
            if write and not target.exists():
                imported = (
                    f"---\nname: imported-{slug}\n"
                    f"description: Imported from {p.relative_to(repo)} via Claude-Code-Optimization migrator.\n"
                    f"---\n\n" + p.read_text(errors="replace")
                )
                target.write_text(imported)
            report.imported_skills.append(target.name)

    # 3. Ingest existing CLAUDE.md / .cursorrules / etc. into .agent/*.md buckets
    ingested = ingest_existing(repo)
    for key, body in ingested.items():
        if write:
            getattr(paths, key).write_text(body)
        report.ingested_buckets.append(key)

    # 4. Notes for things we deliberately don't copy
    if (repo / ".claude" / "hooks").exists():
        report.notes.append(
            ".claude/hooks/* preserved as-is. dotagent observe is wired into Claude Code post-tool "
            "via .claude/hooks/post-tool.sh on init/sync; existing CCO hooks continue to run."
        )
    if (repo / "docs").exists():
        report.notes.append(
            "docs/ kept as the single source of truth. dotagent indexes via config.yaml `sources:`; "
            "no files are duplicated."
        )

    return report
