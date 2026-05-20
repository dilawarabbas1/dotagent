from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .paths import Paths
from .util import dump_yaml, load_yaml

DEFAULT_CONFIG: dict = {
    "project": {"name": "", "description": ""},
    "adapters": {
        "claude": True,
        "cursor": True,
        "copilot": True,
        "opencode": False,
        "custom": False,
    },
    "sources": {
        "bug_registry": "docs/bug-registry.md",
        "anti_patterns": "docs/anti-patterns.md",
        "redis_keys": "docs/redis-key-registry.md",
        "db_impact_map": "docs/db-impact-map.md",
        "dependency_map": "docs/dependency-map.md",
        "architecture": "docs/architecture.md",
        # Hand-maintained feature documentation system. Indexed if files
        # exist; silently skipped if they don't (so single-repo projects
        # without this convention aren't affected). dotagent NEVER
        # generates these — see docs/HAND_MAINTAINED_DOCS_CONVENTION.md.
        "extra": [
            {"name": "feature_master", "path": "docs/feature_master.md", "kind": "generic"},
            {"name": "db_impact_master", "path": "docs/db-impact-map-master.md", "kind": "db_impact_map"},
            {"name": "db_impact_tenant", "path": "docs/db-impact-map-tenant.md", "kind": "db_impact_map"},
            {"name": "db_impact_vector", "path": "docs/db-impact-map-vector.md", "kind": "db_impact_map"},
            {"name": "redis_tenant", "path": "docs/redis-key-registry-tenant.md", "kind": "redis_keys"},
            {"name": "redis_global", "path": "docs/redis-key-registry-global.md", "kind": "redis_keys"},
            {"name": "redis_events", "path": "docs/redis-key-registry-events.md", "kind": "redis_keys"},
            {"name": "bug_registry_infrastructure", "path": "docs/bug-registry-infrastructure.md", "kind": "bug_registry"},
            {"name": "bug_registry_agents", "path": "docs/bug-registry-agents.md", "kind": "bug_registry"},
            {"name": "bug_registry_orchestrator", "path": "docs/bug-registry-orchestrator.md", "kind": "bug_registry"},
            {"name": "architecture_narrative", "path": "docs/ARCHITECTURE.md", "kind": "architecture"},
            {"name": "ops_service_registry", "path": "docs/ops/service-registry.md", "kind": "generic"},
            {"name": "ops_server_dependencies", "path": "docs/ops/server-dependencies.md", "kind": "generic"},
            {"name": "ops_tuning", "path": "docs/ops/tuning.md", "kind": "generic"},
            {"name": "ops_tls_and_env", "path": "docs/ops/tls-and-env.md", "kind": "generic"},
        ],
    },
    "context": {
        "bug_registry_top_n": 15,
        "anti_patterns_top_n": 10,
        "recent_activity_top_n": 8,
        "conflicts_top_n": 8,
        "embed_full_docs": False,
    },
    "project": {
        "enabled": True,
        "tools": {
            "development": {"tool": "claude_code", "model": ""},
            "qa":          {"tool": "claude_code", "model": ""},
            "review":      {"tool": "claude_code", "model": ""},
            "planning":    {"tool": "claude_code", "model": ""},
        },
        "max_cycles_warning": 5,
    },
    "server": {
        "url": "",
        "token": "",
        "forward_events": False,
    },
    "dream": {
        "enabled": True,
        "cron": {
            "daily": "0 2 * * *",
            "weekly": "0 9 * * 1",
            "monthly": "0 9 1 * *",
        },
        "min_cluster_size": 3,
        "window_days": 14,
    },
    "share": {
        "episodic": "full",
        "semantic": "full",
        "personal": "never",
    },
    "pii": {
        "redact_secrets": True,
        "redact_paths": ["**/.env*", "**/secrets/**"],
    },
    "hooks": {
        "git_pre_commit": True,
        "git_post_commit": True,
        "block_on_rule_violation": False,
    },
    # Tiered bug registry conventions. id_prefix is this repo's bug ID prefix
    # (e.g. "BE" for backend, "PORTAL" for the customer portal). Empty means
    # "no prefix declared" — the parser falls back to whatever prefix the
    # entries happen to use, with a doctor warning to set it explicitly.
    # cross_reference_prefixes is the list of OTHER repos' prefixes that this
    # repo expects to see references to (e.g. project-root's "AGT").
    "bugs": {
        "id_prefix": "",
        "cross_reference_prefixes": [],
    },
    # Render strategy for adapter files (CLAUDE.md, .cursorrules, etc.).
    # When `use_manifest: true`, dotagent emits the v0.5.0+ navigation manifest
    # (schema-driven, ~3K tokens, pointer-based). When `false` (default during
    # v0.4.x), emits the legacy compendium (~50-100K tokens, content embedded).
    # Flip to true to opt into the new design; default becomes true at v0.5.0.
    "render": {
        "use_manifest": False,
    },
}


@dataclass
class Config:
    raw: dict = field(default_factory=dict)
    path: Path | None = None

    @classmethod
    def load(cls, paths: Paths) -> "Config":
        return cls(raw=load_yaml(paths.config), path=paths.config)

    def save(self) -> None:
        if self.path is None:
            raise ValueError("Config has no path")
        dump_yaml(self.path, self.raw)

    def get(self, *keys, default=None):
        cur = self.raw
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    @property
    def adapters_enabled(self) -> list[str]:
        return [name for name, enabled in (self.raw.get("adapters") or {}).items() if enabled]


def merge_defaults(user: dict) -> dict:
    """Shallow-merge top-level defaults; preserve user keys that override."""
    out: dict = {}
    for k, v in DEFAULT_CONFIG.items():
        if isinstance(v, dict) and isinstance(user.get(k), dict):
            merged = dict(v)
            merged.update(user[k])
            out[k] = merged
        elif k in user:
            out[k] = user[k]
        else:
            out[k] = v
    for k, v in user.items():
        if k not in out:
            out[k] = v
    return out
