"""CLAUDE.md v3 — navigation-manifest renderer.

Walks the canonical schema for the project's tier, groups entries by
category, and emits a structured markdown file with:

  1. Header
  2. How-to-read protocol
  3. Workflow contract (with placeholders for meta_branch + bug_prefix)
  4. Hard policy
  5. MUST READ section
  6. Quick reference (pulled from brief if available)
  7. Where-to-find-what (one section per non-hidden category)
  8. The document chain diagram
  9. Sister AI tools (Cursor, Copilot, AGENTS.md)

Every schema entry that isn't `CAT_HIDDEN` MUST appear in the output —
enforced by `test_manifest_coverage.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..canonical_structure import (
    CAT_ANTI_PATTERNS,
    CAT_ARCHITECTURE,
    CAT_BUGS,
    CAT_BUSINESS_INTENT,
    CAT_CONFIG,
    CAT_CONTRACTS,
    CAT_DATA_LAYER,
    CAT_DREAM,
    CAT_FEATURE_DOCS,
    CAT_GENERATED_ADAPTERS,
    CAT_HIDDEN,
    CAT_MEMORY_EPISODIC,
    CAT_MEMORY_PERSONAL,
    CAT_MEMORY_SEMANTIC,
    CAT_MEMORY_WORKING,
    CAT_MUST_READ,
    CAT_OPS,
    CAT_PLAN_NEGOTIATION,
    CAT_PRIORITIES,
    CAT_PROJECT_PLAN,
    CAT_SERVICE_REPO_LINK,
    CAT_SKILLS,
    CAT_STYLE,
    CAT_TOOLS_DEFS,
    CAT_UNCATEGORIZED,
    CURRENT_SCHEMA_VERSION,
    SchemaEntry,
    TIER_PROJECT_ROOT,
    TIER_SERVICE_REPO,
    TIER_SINGLE_REPO,
    detect_tier,
    schema_for,
)
from ..paths import Paths
from .workflow import (
    HARD_POLICY,
    HOW_TO_READ_PROTOCOL,
    WORKFLOW_CONTRACT_TEMPLATE,
    code_graph_awareness_block,
)


# Section headers + render order. Categories not listed here are silently
# dropped (matches CAT_HIDDEN behavior).
_CATEGORY_RENDER_ORDER: tuple[tuple[str, str], ...] = (
    # (category, section header line)
    (CAT_BUSINESS_INTENT,    "## 🎯 Business intent"),
    (CAT_FEATURE_DOCS,       "## 📑 Feature documentation (hand-maintained)"),
    (CAT_PROJECT_PLAN,       "## 📋 What's planned"),
    (CAT_PRIORITIES,         "## ⏰ What's active right now"),
    (CAT_CONTRACTS,          "## 📜 Active contracts + cycles"),
    (CAT_PLAN_NEGOTIATION,   "## ✏️ Plan drafting (negotiation history)"),
    (CAT_SERVICE_REPO_LINK,  "## 🎯 Per-service navigation"),
    (CAT_ARCHITECTURE,       "## 🏗️ Technical architecture"),
    (CAT_DATA_LAYER,         "## 🗄️ Data layer (DB + Redis)"),
    (CAT_BUGS,               "## 🐛 Bug-fix lookups"),
    (CAT_ANTI_PATTERNS,      "## 🚫 Anti-patterns to avoid"),
    (CAT_STYLE,              "## 🎨 Style + conventions"),
    (CAT_MEMORY_WORKING,     "## 🧠 Working memory (now)"),
    (CAT_MEMORY_EPISODIC,    "## 🧠 Episodic memory (event log)"),
    (CAT_MEMORY_SEMANTIC,    "## 🧠 Semantic memory (graduated truth)"),
    (CAT_MEMORY_PERSONAL,    "## 🧠 Personal memory (per-actor)"),
    (CAT_DREAM,              "## 💭 Auto-Dream pipeline"),
    (CAT_SKILLS,             "## 🧰 Skills"),
    (CAT_TOOLS_DEFS,         "## 🧰 Tools"),
    (CAT_OPS,                "## 🔧 Operations (hand-maintained — processes, deps, tuning)"),
    (CAT_CONFIG,             "## ⚙️ Configuration"),
    (CAT_GENERATED_ADAPTERS, "## 🔗 Sister AI tools (same body, different filename)"),
)


# Optional prefix paragraph rendered BETWEEN the section header and the
# bullet list for specific categories. Use when the category itself needs
# a "how to navigate" callout, not just a flat list of file pointers.
_CATEGORY_PREFACE: dict[str, str] = {
    CAT_FEATURE_DOCS: (
        "**Entry point for any feature work:** read `docs/feature_master.md` "
        "first (the FM-### index), then open the matching "
        "`docs/feature_master/FM-###-<slug>.md` for that feature's contract, "
        "design rationale, invariants, and files (host · route · db→ · redis→ · "
        "external). From there, follow file-path references into the deep "
        "registries below."
    ),
    CAT_OPS: (
        "**Hand-maintained operational reference.** dotagent never generates or "
        "overwrites these. Read for deploy / on-call / incident-response context."
    ),
}


_CHAIN_DIAGRAM = """\
## 🔗 How the documents relate

```
project_brief.md  ──►  plan.yaml  ──►  NOW.md  ──►  modules/<id>/  ──►  cycles/<NN>/contract.md
   business why        technical what    priorities     module slice           dev↔QA agreement
                                                                                      │
                                                                                      ▼
                                                                            contract.frozen.md
                                                                            dev-handoff.md
                                                                            qa-findings.md
                                                                            completion.md
```

Every contract cites a FEAT-NN and OBJ-NN from the brief. Every module
implements one or more FEAT-NN. Every plan tracks which OBJ-NN it covers.
Audit the chain end-to-end with `dotagent project brief check`.
"""


_TROUBLESHOOTING = """\
## 🛠️ When you're confused, run

```bash
dotagent doctor                          # is the project healthy?
dotagent project brief check             # OBJ→FEAT→Module→Contract chain intact?
dotagent project next                    # what should I work on next?
dotagent context                         # show me the current merged context
dotagent who --file <path>               # who last touched this file?
dotagent activity --since 7d             # what's happened recently?
```
"""


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def render_manifest(paths: Paths, tier: str | None = None) -> str:
    """Render CLAUDE.md as a navigation manifest for the given tier.

    If `tier` is None, infers it from filesystem signals (project-root if
    git.yaml present; service-repo if config has `parent:`; else single-repo).
    """
    if tier is None:
        tier = detect_tier(paths.repo)
    schema = schema_for(tier)

    project_name = _resolve_project_name(paths)
    git_layout = _load_git_yaml_safely(paths)
    bug_prefix = _resolve_bug_prefix(paths)
    brief_summary = _quick_reference_from_brief(paths)

    by_category = _group_entries_by_category(schema)

    sections: list[str] = []

    # 1. Banner + header
    sections.append(_render_banner_header(project_name, tier))

    # 2. How to read this file
    sections.append(HOW_TO_READ_PROTOCOL.rstrip())

    # 3. Workflow contract (templated)
    sections.append(
        WORKFLOW_CONTRACT_TEMPLATE
        .replace("{meta_branch}", _meta_branch_or_default(git_layout))
        .replace("{bug_prefix}", bug_prefix)
        .rstrip()
    )

    # 4. Hard policy
    sections.append(HARD_POLICY.rstrip())

    # 4a. Code-graph awareness (only when `.dotgraph/graph.db` is present).
    # Lives in the rules-of-engagement segment so the agent reads the
    # MCP-tool guidance before it consults the navigation manifest below.
    cg_block = code_graph_awareness_block(paths.repo)
    if cg_block:
        sections.append(cg_block.rstrip())

    # 5. MUST READ
    sections.append(_render_must_read(by_category.get(CAT_MUST_READ, [])))

    # 6. Quick reference (best-effort from brief)
    if brief_summary:
        sections.append(brief_summary)

    # 7. Where-to-find-what — one section per category
    sections.append("---")
    sections.append("# Where to find what")
    sections.append("")
    for category, header in _CATEGORY_RENDER_ORDER:
        entries = by_category.get(category, [])
        if not entries:
            continue
        sections.append(_render_category_section(header, entries, category))

    # 7a. Dynamic docs/ listing — any .md files in docs/ that aren't
    # already covered by canonical schema entries.
    other_docs_section = _render_other_docs(paths, schema)
    if other_docs_section:
        sections.append(other_docs_section)

    # 8. How everything connects
    sections.append(_CHAIN_DIAGRAM.rstrip())

    # 9. Troubleshooting CLI shortcuts
    sections.append(_TROUBLESHOOTING.rstrip())

    return "\n\n".join(s for s in sections if s).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_banner_header(project_name: str, tier: str) -> str:
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    tier_label = {
        TIER_PROJECT_ROOT: "project-root (the meta layer)",
        TIER_SERVICE_REPO: "service-repo (inherits from a parent project-root)",
        TIER_SINGLE_REPO: "single-repo (standalone)",
    }.get(tier, tier)
    return (
        f"<!-- generated by dotagent · navigation manifest for `{project_name}` -->\n"
        f"<!-- schema-version: {CURRENT_SCHEMA_VERSION} · tier: {tier} · rendered-at: {now_iso} -->\n"
        f"\n"
        f"# Project context — {project_name}\n"
        f"\n"
        f"You are working on **{project_name}** (tier: {tier_label}).\n"
        f"This file is a NAVIGATION MANIFEST — it points you at the right files; "
        f"it does not contain content inline."
    )


def _render_must_read(entries: list[SchemaEntry]) -> str:
    if not entries:
        return (
            "═══════════════════════════════════════════════════════════════════════════\n"
            "  🔴  MUST READ before any code edit\n"
            "═══════════════════════════════════════════════════════════════════════════\n"
            "\n"
            "_(no required files declared for this tier — check schema)_"
        )
    lines = [
        "═══════════════════════════════════════════════════════════════════════════",
        "  🔴  MUST READ before any code edit",
        "═══════════════════════════════════════════════════════════════════════════",
        "",
    ]
    for i, entry in enumerate(entries, 1):
        when = entry.when_to_read or entry.description or "(no description)"
        lines.append(f"  {i}. `{entry.path}` — {when}")
    lines.append("")
    lines.append(
        "Also read `CLAUDE.local.md` if it exists (your per-session sidecar; "
        "gitignored; holds working state + personal preferences + recent activity)."
    )
    return "\n".join(lines)


def _render_category_section(
    header: str, entries: list[SchemaEntry], category: str = "",
) -> str:
    """Render one navigation section: header + (optional preface) + bullet list."""
    lines = [header, ""]
    preface = _CATEGORY_PREFACE.get(category) if category else None
    if preface:
        lines.append(preface)
        lines.append("")
    for entry in entries:
        when = entry.when_to_read or entry.description or "(no description)"
        lines.append(f"- `{entry.path}` — {when}")
    return "\n".join(lines)


def _render_other_docs(paths: Paths, schema: tuple[SchemaEntry, ...]) -> str:
    """List any `docs/*.md` files in the repo that aren't already covered by
    canonical schema entries.

    Rationale: canonical filenames (bug-registry.md, anti-patterns.md, ...)
    get rich `when_to_read` text from the schema. Anything else the user
    has in `docs/` should still be discoverable by the AI — we list it
    here with the file's first H1 (or first non-empty line) as the
    description.

    Suppressed when there are no non-canonical docs.
    """
    docs_dir = paths.repo / "docs"
    if not docs_dir.is_dir():
        return ""

    # Paths the schema already covers — skip these in the dynamic listing.
    canonical_paths = {
        e.path for e in schema
        if e.path.startswith("docs/") and e.path.endswith(".md")
    }

    extras: list[tuple[str, str]] = []  # (relative_path, description)
    for md_file in sorted(docs_dir.rglob("*.md")):
        rel = md_file.relative_to(paths.repo).as_posix()
        # Skip archived docs (auto-generated by `dotagent archive`)
        if "/archive/" in rel:
            continue
        # Skip the canonical ones already in the schema
        if rel in canonical_paths:
            continue
        description = _first_h1_or_line(md_file)
        extras.append((rel, description))

    if not extras:
        return ""

    lines = [
        "## 🗂️ Other docs in this repo",
        "",
        "_Auto-listed from `docs/` — files not in the canonical set."
        " Read these for domain-specific context. YOU update them when"
        " their subject changes._",
        "",
    ]
    for rel, desc in extras:
        lines.append(f"- `{rel}` — {desc or '(no description)'}")
    return "\n".join(lines)


def _first_h1_or_line(md_path: "Path") -> str:
    """Extract the first H1 heading from a markdown file, or first non-empty
    non-comment line as fallback. Returns "" if nothing usable found.
    """
    try:
        text = md_path.read_text(errors="replace")
    except OSError:
        return ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("<!--"):  # skip HTML/banner comments
            continue
        if line.startswith("# "):
            # H1 → strip leading "# " and any trailing punctuation
            return line[2:].strip().rstrip(":")
        if line.startswith("#"):  # other heading levels — keep walking
            continue
        # Plain text — use as description, truncated
        return _truncate(line, 100)
    return ""


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _group_entries_by_category(
    schema: tuple[SchemaEntry, ...],
) -> dict[str, list[SchemaEntry]]:
    """Bucket schema entries by their `category`. Hidden entries are dropped.

    Uncategorized entries (default) are KEPT but bucketed under their own
    category so the coverage test can flag them.
    """
    out: dict[str, list[SchemaEntry]] = {}
    for entry in schema:
        if entry.category == CAT_HIDDEN:
            continue
        out.setdefault(entry.category, []).append(entry)
    return out


def _resolve_project_name(paths: Paths) -> str:
    """Best-effort: read project name from brief, then plan, then config.

    Falls back to the repo directory name.
    """
    # Brief
    brief_path = paths.repo / ".agent" / "project_brief.md"
    if brief_path.exists():
        try:
            text = brief_path.read_text()
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("# Project brief:"):
                    return line.split(":", 1)[1].strip() or paths.repo.name
        except OSError:
            pass

    # plan.yaml
    plan_path = paths.repo / ".agent" / "project" / "plan.yaml"
    if plan_path.exists():
        try:
            data = yaml.safe_load(plan_path.read_text()) or {}
            name = data.get("name")
            if name:
                return str(name)
        except (OSError, yaml.YAMLError):
            pass

    # config.yaml::project.name
    config_path = paths.repo / ".agent" / "config.yaml"
    if config_path.exists():
        try:
            data = yaml.safe_load(config_path.read_text()) or {}
            name = (data.get("project") or {}).get("name")
            if name:
                return str(name)
        except (OSError, yaml.YAMLError):
            pass

    return paths.repo.name


def _resolve_bug_prefix(paths: Paths) -> str:
    """Read `bugs.id_prefix` from config.yaml, default to placeholder."""
    config_path = paths.repo / ".agent" / "config.yaml"
    if not config_path.exists():
        return "<PREFIX>"
    try:
        data = yaml.safe_load(config_path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return "<PREFIX>"
    prefix = (data.get("bugs") or {}).get("id_prefix") or ""
    return str(prefix) or "<PREFIX>"


def _load_git_yaml_safely(paths: Paths):
    """Load `.agent/git.yaml` if present; None on any failure."""
    git_yaml = paths.repo / ".agent" / "git.yaml"
    if not git_yaml.exists():
        return None
    try:
        from ..git_layout import load as _load_git
        return _load_git(git_yaml)
    except Exception:  # noqa: BLE001
        return None


def _meta_branch_or_default(git_layout) -> str:
    if git_layout is None:
        return "main"
    branch = (git_layout.meta.branch or "").strip()
    return branch or "dotagent/meta"


def _quick_reference_from_brief(paths: Paths) -> str:
    """Render a brief Quick reference block. Empty if brief is missing or
    doesn't have the relevant sections."""
    try:
        from ..project.brief import load as load_brief
        brief = load_brief(paths.project_brief)
    except Exception:  # noqa: BLE001
        return ""
    if brief is None:
        return ""

    bits: list[str] = []
    if brief.vision:
        bits.append(f"- **Vision:** {brief.vision}")
    if brief.tenancy_lines:
        bits.append(f"- **Tenancy / security posture:** {' · '.join(brief.tenancy_lines[:3])}")
    rules = brief.hard_rules[:5]
    if rules:
        rule_summaries = [f"{r.id} ({r.name})" for r in rules]
        bits.append(f"- **Hard rules (top {len(rules)}):** " + " · ".join(rule_summaries))
    if brief.non_goals:
        bits.append(f"- **Non-goals:** " + " · ".join(brief.non_goals[:5]))
    if not bits:
        return ""
    return "## 📌 Quick reference (one-liners; full detail in source)\n\n" + "\n".join(bits)


__all__ = ("render_manifest",)
