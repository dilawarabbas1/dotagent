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
        "extra": [],
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
