from __future__ import annotations

from pathlib import Path

from dotagent.config import merge_defaults
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.sources import (
    KIND_ANTI_PATTERNS,
    KIND_BUG_REGISTRY,
    KIND_DB_IMPACT_MAP,
    KIND_DEPENDENCY_MAP,
    KIND_REDIS_KEYS,
    index_one,
    load_cache,
    reindex_all,
)


def _write_docs(repo: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


BUG_REGISTRY = """# Bug Registry

## BUG-001: Auth bypass on stale JWT
- **File**: services/auth/jwt.py
- **Severity**: critical
- **Component**: auth-service

Stale JWTs were accepted because the cache TTL exceeded the rotation window.

## BUG-002: Redis pipeline hangs under load
- **Files**: services/cache/pipeline.js, services/cache/redis.js
- **Severity**: high
- **Component**: cache-service

Connections leaked when the pipeline was abandoned mid-flush.

## BUG-003: Migration order mismatch
- **Severity**: medium
- **Tables**: users, audit_log
"""


def test_bug_registry_parses_entries(tmp_path: Path):
    _write_docs(tmp_path, {"docs/bug-registry.md": BUG_REGISTRY})
    src = index_one(tmp_path, KIND_BUG_REGISTRY, "bug_registry", "docs/bug-registry.md")
    assert src.exists is True
    assert len(src.entries) == 3
    ids = [e.id for e in src.entries]
    assert ids == ["BUG-001", "BUG-002", "BUG-003"]
    crit = src.entries[0]
    assert crit.severity == "critical"
    assert "services/auth/jwt.py" in crit.files
    assert crit.components == ["auth-service"]
    assert "stale jwts" in crit.body.lower()


def test_anti_patterns_parses_entries(tmp_path: Path):
    body = """# Anti-Patterns

## ANTI-001: Bypassing BaseAgent.execute()
- **Severity**: high
- **Files**: services/agents/runner.py

Audit rows are lost when callers skip the wrapper.
"""
    _write_docs(tmp_path, {"docs/anti-patterns.md": body})
    src = index_one(tmp_path, KIND_ANTI_PATTERNS, "anti_patterns", "docs/anti-patterns.md")
    assert src.exists
    assert len(src.entries) == 1
    e = src.entries[0]
    assert e.id == "ANTI-001"
    assert e.severity == "high"
    assert "services/agents/runner.py" in e.files


def test_redis_keys_extracts_keys_from_body(tmp_path: Path):
    body = """# Redis Key Registry

## RED-001: Session cache keys
- **Component**: auth-service

We use `session:{user_id}` and `session:meta:{user_id}` for active sessions.
"""
    _write_docs(tmp_path, {"docs/redis-key-registry.md": body})
    src = index_one(tmp_path, KIND_REDIS_KEYS, "redis_keys", "docs/redis-key-registry.md")
    assert src.exists
    assert len(src.entries) == 1
    keys = src.entries[0].keys
    assert any(k.startswith("session:") for k in keys)


def test_db_impact_extracts_tables(tmp_path: Path):
    body = """# DB Impact Map

## DB-001: Users + audit_log writes
- **Tables**: users, audit_log
- **Files**: services/users/repo.py

Writes to `users.email` are mirrored into `audit_log.actor_email`.
"""
    _write_docs(tmp_path, {"docs/db-impact-map.md": body})
    src = index_one(tmp_path, KIND_DB_IMPACT_MAP, "db_impact_map", "docs/db-impact-map.md")
    assert src.exists
    e = src.entries[0]
    assert "users" in e.tables
    assert "audit_log" in e.tables


def test_dependency_map_parses_components(tmp_path: Path):
    body = """# Dependency Map

## DEP-001: auth → users → audit
- **Services**: auth-service, users-service, audit-service

The auth-service depends on users-service and audit-service.
"""
    _write_docs(tmp_path, {"docs/dependency-map.md": body})
    src = index_one(tmp_path, KIND_DEPENDENCY_MAP, "dependency_map", "docs/dependency-map.md")
    assert src.exists
    e = src.entries[0]
    assert "auth-service" in e.components
    assert "audit-service" in e.components


def test_missing_source_yields_exists_false(tmp_path: Path):
    src = index_one(tmp_path, KIND_BUG_REGISTRY, "bug_registry", "docs/does-not-exist.md")
    assert src.exists is False
    assert src.entries == []
    assert src.summary == ""


def test_reindex_all_writes_cache_and_pointer_cards(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    _write_docs(tmp_path, {"docs/bug-registry.md": BUG_REGISTRY})
    cfg = merge_defaults({})
    idx = reindex_all(paths, cfg["sources"])
    assert "bug_registry" in idx
    assert idx["bug_registry"].exists
    # cache present + gitignored
    assert paths.sources_cache.exists()
    assert paths.cache_gitignore.exists()
    # pointer card committed under semantic memory
    pointer = paths.semantic_sources / "bug-registry.md"
    assert pointer.exists()
    assert "Source path" in pointer.read_text()
    # cache reload round-trips entries
    reloaded = load_cache(paths)
    assert reloaded["bug_registry"].entries[0].id == "BUG-001"
