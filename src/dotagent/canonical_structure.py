"""Canonical structure schema for a dotagent project.

Defines, in data, what a v0.4+ dotagent project SHOULD look like at each
tier (project-root vs service-repo). Every later module that asks "where
does this file go?" reads from here so we never re-litigate the layout.

Three things live here:

1. `SchemaEntry` dataclass — a single declarative row in the schema
2. `TIER_PROJECT_ROOT` / `TIER_SERVICE_REPO` — the two layout schemas
3. `CURRENT_SCHEMA_VERSION` — the version stamp written to .agent/.version

The schema is INTENTIONALLY data-driven (a list of entries, not code).
Adding a new file = adding one row + a test. Renaming or moving anything
in this file is a breaking schema change and bumps `CURRENT_SCHEMA_VERSION`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# Stamp written to `.agent/.version` after a successful migrate or fresh init.
# Bump this when the schema changes shape. dotagent doctor + migrate read it.
CURRENT_SCHEMA_VERSION = "0.4.0"


# Tier names. Used by doctor and migrate to pick the right schema.
TIER_PROJECT_ROOT = "project-root"
TIER_SERVICE_REPO = "service-repo"
TIER_SINGLE_REPO = "single-repo"  # legacy/today's behavior — no parent, no manifest


# Entry kinds. Influences how the checker treats deviations.
KIND_FILE = "file"            # hand-written content; missing if required = fail
KIND_DIR = "dir"              # a directory; missing if required = fail
KIND_GENERATED = "generated"  # dotagent owns it; banner expected; missing OK on fresh install
KIND_OPTIONAL = "optional"    # may be absent; not flagged


@dataclass(frozen=True)
class SchemaEntry:
    """One row in the canonical structure schema.

    `path` is relative to the repo root. `kind` decides whether absence
    is a fail / warn / info. `since` tracks the dotagent version that
    introduced the entry, so migrations know what to add.
    """
    path: str
    required: bool
    kind: str
    since: str = "0.4.0"
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in (KIND_FILE, KIND_DIR, KIND_GENERATED, KIND_OPTIONAL):
            raise ValueError(f"unknown kind: {self.kind!r}")


# ---------------------------------------------------------------------------
# TIER: project-root  (the meta layer at the top of a layered project)
# ---------------------------------------------------------------------------

_PROJECT_ROOT_ENTRIES: tuple[SchemaEntry, ...] = (
    # Version stamp — written by init/migrate; read by doctor.
    SchemaEntry(".agent/.version", required=True, kind=KIND_FILE,
                description="Schema version of this .agent/ tree."),

    # Core config + identity
    SchemaEntry(".agent/config.yaml", required=True, kind=KIND_FILE,
                description="Project-wide dotagent config."),

    # Hand-written cross-cutting context
    SchemaEntry(".agent/architecture.md", required=True, kind=KIND_FILE,
                description="Whole-project technical architecture."),
    SchemaEntry(".agent/rules.md", required=True, kind=KIND_FILE,
                description="Rules every service inherits."),
    SchemaEntry(".agent/style.md", required=False, kind=KIND_FILE,
                description="Shared style baseline."),
    SchemaEntry(".agent/patterns.md", required=False, kind=KIND_FILE,
                description="Shared patterns."),
    SchemaEntry(".agent/preferences.md", required=False, kind=KIND_FILE,
                description="Shared preferences."),

    # Project brief — durable business intent
    SchemaEntry(".agent/project_brief.md", required=True, kind=KIND_FILE,
                description="Business objectives, features, hard rules. Hand-written.",
                since="0.4.0"),

    # Git layout config (optional until layered structure is used)
    SchemaEntry(".agent/git.yaml", required=False, kind=KIND_FILE,
                description="Defines meta repo + service repos + branch rules.",
                since="0.7.0"),
    SchemaEntry(".agent/git.md", required=False, kind=KIND_GENERATED,
                description="Human dashboard for git.yaml.",
                since="0.7.0"),

    # Memory layers
    SchemaEntry(".agent/memory", required=True, kind=KIND_DIR,
                description="Working / episodic / semantic / personal memory."),
    SchemaEntry(".agent/memory/working", required=True, kind=KIND_DIR),
    SchemaEntry(".agent/memory/episodic", required=True, kind=KIND_DIR),
    SchemaEntry(".agent/memory/semantic", required=True, kind=KIND_DIR),
    SchemaEntry(".agent/memory/personal", required=True, kind=KIND_DIR),

    # Project management layer
    SchemaEntry(".agent/project", required=False, kind=KIND_DIR,
                description="Project management state (plan, modules, cycles)."),
    SchemaEntry(".agent/project/plan.yaml", required=False, kind=KIND_FILE,
                description="Project mission, repo manifest, FEAT→Module map."),
    SchemaEntry(".agent/project/SCOPE.md", required=False, kind=KIND_GENERATED,
                description="Human-readable plan summary."),
    SchemaEntry(".agent/project/CONTRACTS.md", required=False, kind=KIND_GENERATED,
                description="Per-repo contracts dashboard.",
                since="0.5.0"),
    SchemaEntry(".agent/project/modules", required=False, kind=KIND_DIR,
                description="Cross-service modules at this tier."),

    # Source docs
    SchemaEntry("docs", required=False, kind=KIND_DIR,
                description="Cross-cutting source-of-truth docs."),

    # Generated adapters + dashboards at repo root
    SchemaEntry("CLAUDE.md", required=False, kind=KIND_GENERATED,
                description="What Claude Code reads."),
    SchemaEntry(".cursorrules", required=False, kind=KIND_GENERATED),
    SchemaEntry(".github/copilot-instructions.md", required=False, kind=KIND_GENERATED),
    SchemaEntry("contracts.md", required=False, kind=KIND_GENERATED,
                description="Cross-repo contracts rollup (Tier 1).",
                since="0.6.0"),
)


# ---------------------------------------------------------------------------
# TIER: service-repo  (a service that inherits from a parent project-root)
# ---------------------------------------------------------------------------

_SERVICE_REPO_ENTRIES: tuple[SchemaEntry, ...] = (
    SchemaEntry(".agent/.version", required=True, kind=KIND_FILE),
    SchemaEntry(".agent/config.yaml", required=True, kind=KIND_FILE,
                description="Service config with `parent:` field pointing to project root."),
    SchemaEntry(".agent/architecture.md", required=True, kind=KIND_FILE,
                description="Service-only architecture."),
    SchemaEntry(".agent/rules.md", required=True, kind=KIND_FILE,
                description="Service-only rules."),
    SchemaEntry(".agent/style.md", required=False, kind=KIND_FILE),
    SchemaEntry(".agent/patterns.md", required=False, kind=KIND_FILE),
    SchemaEntry(".agent/preferences.md", required=False, kind=KIND_FILE),

    SchemaEntry(".agent/memory", required=True, kind=KIND_DIR),
    SchemaEntry(".agent/memory/working", required=True, kind=KIND_DIR),
    SchemaEntry(".agent/memory/episodic", required=True, kind=KIND_DIR),
    SchemaEntry(".agent/memory/semantic", required=True, kind=KIND_DIR),
    SchemaEntry(".agent/memory/personal", required=True, kind=KIND_DIR),

    SchemaEntry(".agent/project", required=False, kind=KIND_DIR),
    SchemaEntry(".agent/project/plan.yaml", required=False, kind=KIND_FILE,
                description="Service-local plan slice."),
    SchemaEntry(".agent/project/CONTRACTS.md", required=False, kind=KIND_GENERATED,
                since="0.5.0"),

    SchemaEntry("docs", required=False, kind=KIND_DIR,
                description="Service-owned source docs."),

    SchemaEntry("CLAUDE.md", required=False, kind=KIND_GENERATED),
    SchemaEntry(".cursorrules", required=False, kind=KIND_GENERATED),
    SchemaEntry(".github/copilot-instructions.md", required=False, kind=KIND_GENERATED),
)


# ---------------------------------------------------------------------------
# TIER: single-repo  (today's default — no layering, no parent)
# Backward compatibility: a v0.3 install upgraded to v0.4 starts here unless
# the user explicitly opts into the project-root tier.
# ---------------------------------------------------------------------------

_SINGLE_REPO_ENTRIES: tuple[SchemaEntry, ...] = (
    SchemaEntry(".agent/.version", required=True, kind=KIND_FILE),
    SchemaEntry(".agent/config.yaml", required=True, kind=KIND_FILE),
    SchemaEntry(".agent/architecture.md", required=True, kind=KIND_FILE),
    SchemaEntry(".agent/rules.md", required=True, kind=KIND_FILE),
    SchemaEntry(".agent/style.md", required=False, kind=KIND_FILE),
    SchemaEntry(".agent/patterns.md", required=False, kind=KIND_FILE),
    SchemaEntry(".agent/preferences.md", required=False, kind=KIND_FILE),

    SchemaEntry(".agent/memory", required=True, kind=KIND_DIR),
    SchemaEntry(".agent/memory/working", required=True, kind=KIND_DIR),
    SchemaEntry(".agent/memory/episodic", required=True, kind=KIND_DIR),
    SchemaEntry(".agent/memory/semantic", required=True, kind=KIND_DIR),
    SchemaEntry(".agent/memory/personal", required=True, kind=KIND_DIR),

    SchemaEntry(".agent/project", required=False, kind=KIND_DIR),
    SchemaEntry(".agent/project/plan.yaml", required=False, kind=KIND_FILE),
    SchemaEntry(".agent/project/CONTRACTS.md", required=False, kind=KIND_GENERATED,
                since="0.5.0"),

    SchemaEntry("docs", required=False, kind=KIND_DIR),

    SchemaEntry("CLAUDE.md", required=False, kind=KIND_GENERATED),
    SchemaEntry(".cursorrules", required=False, kind=KIND_GENERATED),
    SchemaEntry(".github/copilot-instructions.md", required=False, kind=KIND_GENERATED),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def schema_for(tier: str) -> tuple[SchemaEntry, ...]:
    """Return the canonical schema for the given tier.

    Raises ValueError if the tier is unknown.
    """
    if tier == TIER_PROJECT_ROOT:
        return _PROJECT_ROOT_ENTRIES
    if tier == TIER_SERVICE_REPO:
        return _SERVICE_REPO_ENTRIES
    if tier == TIER_SINGLE_REPO:
        return _SINGLE_REPO_ENTRIES
    raise ValueError(
        f"unknown tier: {tier!r}. Expected one of: "
        f"{TIER_PROJECT_ROOT}, {TIER_SERVICE_REPO}, {TIER_SINGLE_REPO}"
    )


def all_tiers() -> tuple[str, ...]:
    """List every tier name in declaration order."""
    return (TIER_PROJECT_ROOT, TIER_SERVICE_REPO, TIER_SINGLE_REPO)


def detect_tier(repo: Path) -> str:
    """Infer the tier from filesystem signals.

    Signals (highest to lowest priority):
    - `.agent/git.yaml` present → project-root
    - `.agent/config.yaml` declares `parent:` → service-repo
    - else → single-repo

    This is the default heuristic. Callers can override with an explicit
    --tier flag when the signal is ambiguous.
    """
    if (repo / ".agent" / "git.yaml").exists():
        return TIER_PROJECT_ROOT

    config = repo / ".agent" / "config.yaml"
    if config.exists():
        try:
            text = config.read_text()
        except OSError:
            text = ""
        # Cheap detection — a proper YAML parse happens elsewhere if needed.
        for line in text.splitlines():
            stripped = line.split("#", 1)[0].strip()
            if stripped.startswith("parent:") and stripped != "parent:":
                return TIER_SERVICE_REPO

    return TIER_SINGLE_REPO


__all__ = (
    "CURRENT_SCHEMA_VERSION",
    "TIER_PROJECT_ROOT",
    "TIER_SERVICE_REPO",
    "TIER_SINGLE_REPO",
    "KIND_FILE",
    "KIND_DIR",
    "KIND_GENERATED",
    "KIND_OPTIONAL",
    "SchemaEntry",
    "schema_for",
    "all_tiers",
    "detect_tier",
)
