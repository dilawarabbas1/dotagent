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


# ---------------------------------------------------------------------------
# Categories drive CLAUDE.md navigation manifest rendering.
# Every schema entry MUST declare one (test coverage gate enforces this).
# ---------------------------------------------------------------------------

CAT_MUST_READ = "must-read"                # 🔴 read first, every session
CAT_BUSINESS_INTENT = "business-intent"    # 🎯 OBJ / FEAT / vision
CAT_PROJECT_PLAN = "project-plan"          # 📋 plan.yaml + SCOPE
CAT_PRIORITIES = "priorities"              # ⏰ NOW.md + active state
CAT_CONTRACTS = "contracts"                # 📜 module + cycle files
CAT_PLAN_NEGOTIATION = "plan-negotiation"  # ✏️ plan drafting history
CAT_ARCHITECTURE = "architecture"          # 🏗️ tech architecture docs
CAT_DATA_LAYER = "data-layer"              # 🗄️ db + redis
CAT_BUGS = "bugs"                          # 🐛 bug registry
CAT_ANTI_PATTERNS = "anti-patterns"        # 🚫 anti-patterns
CAT_STYLE = "style"                        # 🎨 style + patterns + prefs
CAT_MEMORY_WORKING = "memory-working"      # 🧠 working memory
CAT_MEMORY_EPISODIC = "memory-episodic"    # 🧠 episodic memory
CAT_MEMORY_SEMANTIC = "memory-semantic"    # 🧠 semantic memory
CAT_MEMORY_PERSONAL = "memory-personal"    # 🧠 personal (sidecar pointer)
CAT_DREAM = "dream"                        # 💭 auto-dream pipeline
CAT_SKILLS = "skills"                      # 🧰 skills
CAT_TOOLS_DEFS = "tools-defs"              # 🧰 tool definitions
CAT_CONFIG = "config"                      # ⚙️ config + git topology
CAT_GENERATED_ADAPTERS = "generated-adapters"  # 🔗 sister AI files
CAT_SERVICE_REPO_LINK = "service-repo-link"    # 🎯 per-service navigation
CAT_HIDDEN = "hidden"                      # don't surface in CLAUDE.md
CAT_UNCATEGORIZED = "uncategorized"        # default — fails coverage test

ALL_CATEGORIES = (
    CAT_MUST_READ, CAT_BUSINESS_INTENT, CAT_PROJECT_PLAN, CAT_PRIORITIES,
    CAT_CONTRACTS, CAT_PLAN_NEGOTIATION, CAT_ARCHITECTURE, CAT_DATA_LAYER,
    CAT_BUGS, CAT_ANTI_PATTERNS, CAT_STYLE,
    CAT_MEMORY_WORKING, CAT_MEMORY_EPISODIC, CAT_MEMORY_SEMANTIC,
    CAT_MEMORY_PERSONAL,
    CAT_DREAM, CAT_SKILLS, CAT_TOOLS_DEFS, CAT_CONFIG,
    CAT_GENERATED_ADAPTERS, CAT_SERVICE_REPO_LINK,
    CAT_HIDDEN, CAT_UNCATEGORIZED,
)


@dataclass(frozen=True)
class SchemaEntry:
    """One row in the canonical structure schema.

    `path` is relative to the repo root. `kind` decides whether absence
    is a fail / warn / info. `since` tracks the dotagent version that
    introduced the entry, so migrations know what to add.

    `category` controls where the entry appears in the generated
    CLAUDE.md navigation manifest. Must be one of the `CAT_*` constants.
    A coverage test fails CI if any entry remains `CAT_UNCATEGORIZED`.

    `when_to_read` is the one-line instruction the AI sees next to the
    pointer in CLAUDE.md (e.g. "Read first for business intent"). Defaults
    to `description` when empty.
    """
    path: str
    required: bool
    kind: str
    since: str = "0.4.0"
    description: str = ""
    category: str = CAT_UNCATEGORIZED
    when_to_read: str = ""

    def __post_init__(self) -> None:
        if self.kind not in (KIND_FILE, KIND_DIR, KIND_GENERATED, KIND_OPTIONAL):
            raise ValueError(f"unknown kind: {self.kind!r}")
        if self.category not in ALL_CATEGORIES:
            raise ValueError(
                f"unknown category: {self.category!r} for {self.path!r}. "
                f"Pick from canonical_structure.ALL_CATEGORIES or mark CAT_HIDDEN."
            )


# ---------------------------------------------------------------------------
# TIER: project-root  (the meta layer at the top of a layered project)
# ---------------------------------------------------------------------------

_PROJECT_ROOT_ENTRIES: tuple[SchemaEntry, ...] = (
    # Version stamp — written by init/migrate; read by doctor.
    SchemaEntry(".agent/.version", required=True, kind=KIND_FILE,
                description="Schema version of this .agent/ tree.",
                category=CAT_HIDDEN),

    # Core config + identity
    SchemaEntry(".agent/config.yaml", required=True, kind=KIND_FILE,
                description="Project-wide dotagent config.",
                category=CAT_CONFIG,
                when_to_read="dotagent config: sources, adapters, hooks, bug-id prefix."),

    # Hand-written cross-cutting context
    SchemaEntry(".agent/architecture.md", required=True, kind=KIND_FILE,
                description="Whole-project technical architecture.",
                category=CAT_ARCHITECTURE,
                when_to_read="Whole-project tech architecture (concise; see docs/architecture.md for long form)."),
    SchemaEntry(".agent/rules.md", required=True, kind=KIND_FILE,
                description="Rules every service inherits.",
                category=CAT_MUST_READ,
                when_to_read="Project-wide hard rules — never violate."),
    SchemaEntry(".agent/style.md", required=False, kind=KIND_FILE,
                description="Shared style baseline.",
                category=CAT_STYLE,
                when_to_read="Project-wide code style baseline."),
    SchemaEntry(".agent/patterns.md", required=False, kind=KIND_FILE,
                description="Shared patterns.",
                category=CAT_STYLE,
                when_to_read="Approved design patterns to follow."),
    SchemaEntry(".agent/preferences.md", required=False, kind=KIND_FILE,
                description="Shared preferences.",
                category=CAT_STYLE,
                when_to_read="Team workflow preferences."),

    # Project brief — durable business intent
    SchemaEntry(".agent/project_brief.md", required=True, kind=KIND_FILE,
                description="Business objectives, features, hard rules. Hand-written.",
                category=CAT_MUST_READ,
                when_to_read="Business intent: OBJ-NN, FEAT-NN, RULE-NN, vision, non-goals."),

    # Git layout config (optional until layered structure is used)
    SchemaEntry(".agent/git.yaml", required=False, kind=KIND_FILE,
                description="Defines meta repo + service repos + branch rules.",
                category=CAT_CONFIG,
                when_to_read="Git topology: which folder maps to which repo + branch rules."),
    SchemaEntry(".agent/git.md", required=False, kind=KIND_GENERATED,
                description="Human dashboard for git.yaml.",
                category=CAT_MUST_READ,
                when_to_read="Branch policy + push rules — read before any git push."),

    # Memory layers
    SchemaEntry(".agent/memory", required=True, kind=KIND_DIR,
                description="Working / episodic / semantic / personal memory.",
                category=CAT_HIDDEN),
    SchemaEntry(".agent/memory/working", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_WORKING,
                when_to_read="Per-actor current state: branch, recent files, active task. Fed by hooks."),
    SchemaEntry(".agent/memory/episodic", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_EPISODIC,
                when_to_read="Append-only event log per actor+session. Query via `dotagent activity` / `who` / `timeline`."),
    SchemaEntry(".agent/memory/semantic", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_SEMANTIC,
                when_to_read="Graduated rules + patterns with mandatory rationale. Team-wide truth."),
    SchemaEntry(".agent/memory/personal", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_PERSONAL,
                when_to_read="Per-developer prefs. YOURS lives in CLAUDE.local.md (gitignored sidecar)."),

    # Project management layer
    SchemaEntry(".agent/project", required=False, kind=KIND_DIR,
                description="Project management state (plan, modules, cycles).",
                category=CAT_HIDDEN),
    SchemaEntry(".agent/project/plan.yaml", required=False, kind=KIND_FILE,
                description="Project mission, repo manifest, FEAT→Module map.",
                category=CAT_PROJECT_PLAN,
                when_to_read="Machine-readable plan: FEAT→Module mapping, repos manifest."),
    SchemaEntry(".agent/project/SCOPE.md", required=False, kind=KIND_GENERATED,
                description="Human-readable plan summary.",
                category=CAT_PROJECT_PLAN,
                when_to_read="Project blueprint: modules, success criteria, scope."),
    SchemaEntry(".agent/project/CONTRACTS.md", required=False, kind=KIND_GENERATED,
                description="Per-repo contracts dashboard.",
                category=CAT_PRIORITIES,
                when_to_read="Every cycle's state — open + frozen contracts in this repo."),
    SchemaEntry(".agent/project/modules", required=False, kind=KIND_DIR,
                description="Cross-service modules at this tier.",
                category=CAT_CONTRACTS,
                when_to_read="Per-module dirs: module.yaml, PLAN.md, cycles/<NN>/{contract,dev-handoff,qa-findings}.md."),

    # Source docs (cross-cutting; Claude maintains these — never dotagent)
    SchemaEntry("docs", required=False, kind=KIND_DIR,
                description="Cross-cutting source-of-truth docs.",
                category=CAT_HIDDEN),
    SchemaEntry("docs/bug-registry.md", required=False, kind=KIND_FILE,
                category=CAT_BUGS,
                when_to_read="Cross-service bugs (prefix AGT-). Read for bug-fix tasks. YOU update after fixing."),
    SchemaEntry("docs/anti-patterns.md", required=False, kind=KIND_FILE,
                category=CAT_ANTI_PATTERNS,
                when_to_read="Anti-patterns to avoid. YOU add new ones discovered during work."),
    SchemaEntry("docs/redis-keys.md", required=False, kind=KIND_FILE,
                category=CAT_DATA_LAYER,
                when_to_read="Redis namespace catalog + TTL conventions. YOU update when adding a namespace."),
    SchemaEntry("docs/db-impact-map.md", required=False, kind=KIND_FILE,
                category=CAT_DATA_LAYER,
                when_to_read="DB tables + blast-radius + migration policy. YOU update when touching tables."),
    SchemaEntry("docs/dependency-map.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="Service-to-service graph. YOU update when adding/changing cross-service calls."),
    SchemaEntry("docs/architecture.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="Long-form system architecture. YOU update when system shape changes."),
    SchemaEntry("docs/service-registry.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="Per-service description (project-root only). Mostly stable."),
    SchemaEntry("docs/shared-contracts.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="API + event schemas BETWEEN services. YOU update on cross-service contract changes."),

    # Generated adapters + dashboards at repo root
    SchemaEntry("CLAUDE.md", required=False, kind=KIND_GENERATED,
                description="What Claude Code reads.",
                category=CAT_HIDDEN),
    SchemaEntry(".cursorrules", required=False, kind=KIND_GENERATED,
                category=CAT_GENERATED_ADAPTERS,
                when_to_read="Same body as CLAUDE.md — Cursor reads this."),
    SchemaEntry(".github/copilot-instructions.md", required=False, kind=KIND_GENERATED,
                category=CAT_GENERATED_ADAPTERS,
                when_to_read="Same body as CLAUDE.md — GitHub Copilot reads this."),
    SchemaEntry("contracts.md", required=False, kind=KIND_GENERATED,
                description="Cross-repo contracts rollup (Tier 1).",
                category=CAT_PRIORITIES,
                when_to_read="Cross-repo contracts rollup at project root."),
)


# ---------------------------------------------------------------------------
# TIER: service-repo  (a service that inherits from a parent project-root)
# ---------------------------------------------------------------------------

_SERVICE_REPO_ENTRIES: tuple[SchemaEntry, ...] = (
    SchemaEntry(".agent/.version", required=True, kind=KIND_FILE,
                category=CAT_HIDDEN),
    SchemaEntry(".agent/config.yaml", required=True, kind=KIND_FILE,
                description="Service config with `parent:` field pointing to project root.",
                category=CAT_CONFIG,
                when_to_read="Service config (note `parent:` field — inherits from project root)."),
    SchemaEntry(".agent/architecture.md", required=True, kind=KIND_FILE,
                description="Service-only architecture.",
                category=CAT_ARCHITECTURE,
                when_to_read="THIS service's architecture (project-wide is at ../.agent/architecture.md)."),
    SchemaEntry(".agent/rules.md", required=True, kind=KIND_FILE,
                description="Service-only rules.",
                category=CAT_MUST_READ,
                when_to_read="Service-specific hard rules (project-wide rules at ../.agent/rules.md also apply)."),
    SchemaEntry(".agent/style.md", required=False, kind=KIND_FILE,
                category=CAT_STYLE,
                when_to_read="Service-specific code style."),
    SchemaEntry(".agent/patterns.md", required=False, kind=KIND_FILE,
                category=CAT_STYLE,
                when_to_read="Service-specific patterns."),
    SchemaEntry(".agent/preferences.md", required=False, kind=KIND_FILE,
                category=CAT_STYLE,
                when_to_read="Service-specific team preferences."),

    SchemaEntry(".agent/memory", required=True, kind=KIND_DIR,
                category=CAT_HIDDEN),
    SchemaEntry(".agent/memory/working", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_WORKING,
                when_to_read="Per-actor current state in THIS service."),
    SchemaEntry(".agent/memory/episodic", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_EPISODIC,
                when_to_read="Service-local event log. Query via `dotagent activity`."),
    SchemaEntry(".agent/memory/semantic", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_SEMANTIC,
                when_to_read="Service-graduated rules + patterns."),
    SchemaEntry(".agent/memory/personal", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_PERSONAL,
                when_to_read="Per-developer prefs. YOURS lives in CLAUDE.local.md (gitignored)."),

    SchemaEntry(".agent/project", required=False, kind=KIND_DIR,
                category=CAT_HIDDEN),
    SchemaEntry(".agent/project/plan.yaml", required=False, kind=KIND_FILE,
                description="Service-local plan slice.",
                category=CAT_PROJECT_PLAN,
                when_to_read="This service's plan slice — module_ids + cross_module refs."),
    SchemaEntry(".agent/project/CONTRACTS.md", required=False, kind=KIND_GENERATED,
                since="0.4.0",
                category=CAT_PRIORITIES,
                when_to_read="Open + frozen contracts dashboard for THIS service."),

    # Modules + cycle artifacts (the contract layer for this service)
    SchemaEntry(".agent/project/modules", required=False, kind=KIND_DIR,
                category=CAT_CONTRACTS,
                when_to_read=(
                    "Per-module directories. Each module: module.yaml + PLAN.md + cycles/. "
                    "If `module.yaml` declares `cross_module: <project-root-module>`, this "
                    "is a SLICE of a cross-service module — coordinate via the parent's "
                    "cycle contract."
                )),
    SchemaEntry(".agent/project/modules/<id>/module.yaml", required=False, kind=KIND_FILE,
                category=CAT_CONTRACTS,
                when_to_read="Module state, implements_features, cross_module reference, cycles[]."),
    SchemaEntry(".agent/project/modules/<id>/PLAN.md", required=False, kind=KIND_GENERATED,
                category=CAT_CONTRACTS,
                when_to_read="Human-readable module plan (generated from module.yaml)."),
    SchemaEntry(".agent/project/modules/<id>/cycles/<NN>/contract.md", required=False, kind=KIND_FILE,
                category=CAT_CONTRACTS,
                when_to_read="LIVE contract under dev↔QA negotiation. Cite FEAT-NN + OBJ-NN in business-traceability."),
    SchemaEntry(".agent/project/modules/<id>/cycles/<NN>/contract.frozen.md", required=False, kind=KIND_GENERATED,
                category=CAT_CONTRACTS,
                when_to_read="IMMUTABLE post-freeze snapshot. Never edit. The agreement you implement against."),
    SchemaEntry(".agent/project/modules/<id>/cycles/<NN>/dev-handoff.md", required=False, kind=KIND_FILE,
                category=CAT_CONTRACTS,
                when_to_read="Dev says 'done' — written via `dotagent project handoff`. QA reads this next."),
    SchemaEntry(".agent/project/modules/<id>/cycles/<NN>/qa-findings.md", required=False, kind=KIND_FILE,
                category=CAT_CONTRACTS,
                when_to_read="QA pass/fail with MANDATORY rationale — written via `dotagent project qa-record`."),
    SchemaEntry(".agent/project/modules/<id>/completion.md", required=False, kind=KIND_FILE,
                category=CAT_CONTRACTS,
                when_to_read="Post-ship summary (added after `dotagent project resolve`)."),

    SchemaEntry("docs", required=False, kind=KIND_DIR,
                description="Service-owned source docs.",
                category=CAT_HIDDEN),
    SchemaEntry("docs/bug-registry.md", required=False, kind=KIND_FILE,
                category=CAT_BUGS,
                when_to_read="Service-local bugs (prefix per `bugs.id_prefix`). YOU update after fixing."),
    SchemaEntry("docs/anti-patterns.md", required=False, kind=KIND_FILE,
                category=CAT_ANTI_PATTERNS,
                when_to_read="Service-local anti-patterns. YOU add new ones discovered."),
    SchemaEntry("docs/redis-keys.md", required=False, kind=KIND_FILE,
                category=CAT_DATA_LAYER,
                when_to_read="Service-local Redis namespaces. YOU update when adding."),
    SchemaEntry("docs/db-impact-map.md", required=False, kind=KIND_FILE,
                category=CAT_DATA_LAYER,
                when_to_read="Tables this service owns. YOU update on schema changes."),
    SchemaEntry("docs/dependency-map.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="Intra-service module graph. YOU update on dep changes."),
    SchemaEntry("docs/architecture.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="Service architecture (long form). YOU update on system changes."),

    SchemaEntry("CLAUDE.md", required=False, kind=KIND_GENERATED,
                category=CAT_HIDDEN),
    SchemaEntry(".cursorrules", required=False, kind=KIND_GENERATED,
                category=CAT_GENERATED_ADAPTERS,
                when_to_read="Same body as CLAUDE.md — Cursor reads this."),
    SchemaEntry(".github/copilot-instructions.md", required=False, kind=KIND_GENERATED,
                category=CAT_GENERATED_ADAPTERS,
                when_to_read="Same body as CLAUDE.md — GitHub Copilot reads this."),

    # ─── INHERITED FROM PROJECT ROOT ─────────────────────────────────────
    # This service is a CHILD of the layered project root (typically `..`).
    # These pointers reference the parent layer; they hold cross-cutting
    # context that applies to every service in the project.
    SchemaEntry("../.agent/project_brief.md", required=False, kind=KIND_FILE,
                category=CAT_MUST_READ,
                when_to_read="INHERITED · business intent (OBJ/FEAT/RULE) for the WHOLE project."),
    SchemaEntry("../.agent/rules.md", required=False, kind=KIND_FILE,
                category=CAT_MUST_READ,
                when_to_read="INHERITED · project-wide hard rules. Your service rules ADD; never override these."),
    SchemaEntry("../.agent/git.md", required=False, kind=KIND_GENERATED,
                category=CAT_MUST_READ,
                when_to_read="INHERITED · branch policy + push rules for the meta repo. Read before any push."),
    SchemaEntry("../.agent/architecture.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="INHERITED · whole-project technical architecture (concise)."),
    SchemaEntry("../.agent/style.md", required=False, kind=KIND_FILE,
                category=CAT_STYLE,
                when_to_read="INHERITED · project-wide style baseline. Your service style overrides where it disagrees."),
    SchemaEntry("../.agent/patterns.md", required=False, kind=KIND_FILE,
                category=CAT_STYLE,
                when_to_read="INHERITED · project-wide patterns."),
    SchemaEntry("../.agent/git.yaml", required=False, kind=KIND_FILE,
                category=CAT_CONFIG,
                when_to_read="INHERITED · git topology + branch rules (source of truth for git.md)."),
    SchemaEntry("../.agent/project/plan.yaml", required=False, kind=KIND_FILE,
                category=CAT_PROJECT_PLAN,
                when_to_read="INHERITED · PROJECT-WIDE plan: features_to_modules, repos manifest, FEAT-OBJ links."),
    SchemaEntry("../.agent/project/SCOPE.md", required=False, kind=KIND_GENERATED,
                category=CAT_PROJECT_PLAN,
                when_to_read="INHERITED · human-readable project blueprint."),
    SchemaEntry("../.agent/project/CONTRACTS.md", required=False, kind=KIND_GENERATED,
                category=CAT_PRIORITIES,
                when_to_read="INHERITED · project-root tier contracts dashboard (cross-service modules)."),
    SchemaEntry("../contracts.md", required=False, kind=KIND_GENERATED,
                category=CAT_PRIORITIES,
                when_to_read="INHERITED · Tier-1 cross-repo contracts rollup. See all services' state at a glance."),
    SchemaEntry("../.agent/project/modules", required=False, kind=KIND_DIR,
                category=CAT_CONTRACTS,
                when_to_read=(
                    "INHERITED · CROSS-SERVICE modules at the project-root tier. "
                    "If your service has a slice (module.yaml has `cross_module: ...`), "
                    "the parent's cycle contract is the authoritative agreement."
                )),
    SchemaEntry("../docs/service-registry.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="INHERITED · what each service in this project does. Start here when navigating to a sibling."),
    SchemaEntry("../docs/shared-contracts.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="INHERITED · API/event schemas BETWEEN services. Update when changing cross-service contracts."),
    SchemaEntry("../docs/dependency-map.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="INHERITED · CROSS-SERVICE dependency graph."),
    SchemaEntry("../docs/architecture.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="INHERITED · whole-project architecture (long form)."),
    SchemaEntry("../docs/bug-registry.md", required=False, kind=KIND_FILE,
                category=CAT_BUGS,
                when_to_read="INHERITED · cross-service bugs (AGT-####). Your BE-#### bugs may cross-ref these."),
    SchemaEntry("../docs/anti-patterns.md", required=False, kind=KIND_FILE,
                category=CAT_ANTI_PATTERNS,
                when_to_read="INHERITED · project-wide anti-patterns."),
)


# ---------------------------------------------------------------------------
# TIER: single-repo  (today's default — no layering, no parent)
# Backward compatibility: a v0.3 install upgraded to v0.4 starts here unless
# the user explicitly opts into the project-root tier.
# ---------------------------------------------------------------------------

_SINGLE_REPO_ENTRIES: tuple[SchemaEntry, ...] = (
    SchemaEntry(".agent/.version", required=True, kind=KIND_FILE,
                category=CAT_HIDDEN),
    SchemaEntry(".agent/config.yaml", required=True, kind=KIND_FILE,
                category=CAT_CONFIG,
                when_to_read="dotagent config: sources, adapters, hooks, bug-id prefix."),
    SchemaEntry(".agent/architecture.md", required=True, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="Technical architecture for THIS project."),
    SchemaEntry(".agent/rules.md", required=True, kind=KIND_FILE,
                category=CAT_MUST_READ,
                when_to_read="Hard rules — never violate."),
    # Brief is OPTIONAL in single-repo tier but if present should be
    # MUST_READ. SchemaEntry's category controls categorization regardless
    # of whether the file exists on disk.
    SchemaEntry(".agent/project_brief.md", required=False, kind=KIND_FILE,
                category=CAT_MUST_READ,
                when_to_read="Business intent: OBJ-NN, FEAT-NN, RULE-NN, vision, non-goals (if present)."),
    SchemaEntry(".agent/style.md", required=False, kind=KIND_FILE,
                category=CAT_STYLE,
                when_to_read="Code style baseline."),
    SchemaEntry(".agent/patterns.md", required=False, kind=KIND_FILE,
                category=CAT_STYLE,
                when_to_read="Approved patterns."),
    SchemaEntry(".agent/preferences.md", required=False, kind=KIND_FILE,
                category=CAT_STYLE,
                when_to_read="Workflow preferences."),

    SchemaEntry(".agent/memory", required=True, kind=KIND_DIR,
                category=CAT_HIDDEN),
    SchemaEntry(".agent/memory/working", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_WORKING,
                when_to_read="Per-actor current state. Fed by hooks."),
    SchemaEntry(".agent/memory/episodic", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_EPISODIC,
                when_to_read="Event log per actor+session. Query via `dotagent activity`."),
    SchemaEntry(".agent/memory/semantic", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_SEMANTIC,
                when_to_read="Graduated rules + patterns with rationale."),
    SchemaEntry(".agent/memory/personal", required=True, kind=KIND_DIR,
                category=CAT_MEMORY_PERSONAL,
                when_to_read="Per-developer prefs. YOURS in CLAUDE.local.md (gitignored)."),

    SchemaEntry(".agent/project", required=False, kind=KIND_DIR,
                category=CAT_HIDDEN),
    SchemaEntry(".agent/project/plan.yaml", required=False, kind=KIND_FILE,
                category=CAT_PROJECT_PLAN,
                when_to_read="Project plan: modules, FEAT→Module map."),
    SchemaEntry(".agent/project/CONTRACTS.md", required=False, kind=KIND_GENERATED,
                since="0.4.0",
                category=CAT_PRIORITIES,
                when_to_read="Open + frozen contracts dashboard."),

    SchemaEntry("docs", required=False, kind=KIND_DIR,
                category=CAT_HIDDEN),
    SchemaEntry("docs/bug-registry.md", required=False, kind=KIND_FILE,
                category=CAT_BUGS,
                when_to_read="Bug registry. YOU update after fixing a bug."),
    SchemaEntry("docs/anti-patterns.md", required=False, kind=KIND_FILE,
                category=CAT_ANTI_PATTERNS,
                when_to_read="Anti-patterns to avoid. YOU add new ones discovered."),
    SchemaEntry("docs/redis-keys.md", required=False, kind=KIND_FILE,
                category=CAT_DATA_LAYER,
                when_to_read="Redis namespace catalog. YOU update when adding a namespace."),
    SchemaEntry("docs/db-impact-map.md", required=False, kind=KIND_FILE,
                category=CAT_DATA_LAYER,
                when_to_read="DB tables + blast-radius. YOU update when touching tables."),
    SchemaEntry("docs/dependency-map.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="Service/module graph. YOU update on dep changes."),
    SchemaEntry("docs/architecture.md", required=False, kind=KIND_FILE,
                category=CAT_ARCHITECTURE,
                when_to_read="Long-form architecture. YOU update on system changes."),

    SchemaEntry("CLAUDE.md", required=False, kind=KIND_GENERATED,
                category=CAT_HIDDEN),
    SchemaEntry(".cursorrules", required=False, kind=KIND_GENERATED,
                category=CAT_GENERATED_ADAPTERS,
                when_to_read="Same body as CLAUDE.md — Cursor reads this."),
    SchemaEntry(".github/copilot-instructions.md", required=False, kind=KIND_GENERATED,
                category=CAT_GENERATED_ADAPTERS,
                when_to_read="Same body as CLAUDE.md — GitHub Copilot reads this."),
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
