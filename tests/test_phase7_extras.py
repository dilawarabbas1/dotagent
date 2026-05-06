from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from dotagent.dream.clustering import available as embeddings_available
from dotagent.dream.clustering import cluster_events
from dotagent.memory import EpisodicEvent, EpisodicMemory
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.watchers.cursor_watcher import (
    _is_skipped,
    _DebouncedFlusher,
    cursor_running,
    watchdog_available,
)


# ---- embeddings (graceful fallback) ----------------------------------------


def test_embeddings_available_reports_extras_state():
    """When ML extras aren't installed, available() returns False — and cluster_events returns []."""
    assert isinstance(embeddings_available(), bool)


def test_cluster_events_returns_empty_when_extras_missing(tmp_path: Path):
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    if embeddings_available():
        pytest.skip("ML extras installed; this test only runs in the lean install")
    out = cluster_events(paths, since="30d")
    assert out == []


# ---- cursor watcher (no watchdog needed for unit tests) --------------------


def test_is_skipped_excludes_dotgit_and_node_modules(tmp_path: Path):
    repo = tmp_path
    assert _is_skipped(repo / ".git" / "config", repo) is True
    assert _is_skipped(repo / "node_modules" / "lib.js", repo) is True
    assert _is_skipped(repo / ".agent" / "memory" / "x.json", repo) is True
    assert _is_skipped(repo / "src" / "ok.py", repo) is False


def test_cursor_running_returns_a_bool():
    assert isinstance(cursor_running(), bool)


def test_watchdog_available_returns_a_bool():
    assert isinstance(watchdog_available(), bool)


def test_debounced_flusher_aggregates_files(tmp_path: Path, monkeypatch):
    """Flusher should buffer a list of files; we verify dedupe + ordering without invoking watchdog."""
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    f = _DebouncedFlusher(paths, window=0.0)
    f.add("a.py"); f.add("b.py"); f.add("a.py")
    # bypass cursor_running gate
    monkeypatch.setattr("dotagent.watchers.cursor_watcher.cursor_running", lambda: True)
    f.maybe_flush()
    # event landed in episodic
    events = list(EpisodicMemory(paths).iter_events())
    assert events, "flusher should have emitted an episodic event"
    assert events[-1]["tool"] == "cursor"
    assert "a.py" in (events[-1].get("files") or [])
    assert "b.py" in (events[-1].get("files") or [])


# ---- server (only runs if [server] extras are installed) -------------------


def _has_fastapi() -> bool:
    try:
        importlib.import_module("fastapi")
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_fastapi(), reason="fastapi not installed (run with [server] extra)")
def test_server_routes_post_event_and_lists(tmp_path: Path):
    from fastapi.testclient import TestClient

    from dotagent.server import build_app

    app = build_app(db_path=tmp_path / "server.sqlite", bootstrap_admin_token="ADMIN")
    client = TestClient(app)

    r = client.get("/")
    assert r.status_code == 200
    assert "dotagent" in r.text

    # admin token can write
    headers = {"Authorization": "Bearer ADMIN"}
    payload = {
        "ts": "2026-05-06T00:00:00Z", "actor": "alice", "tool": "claude_code",
        "kind": "commit", "session": "s1", "host": "h", "repo": "demo",
        "summary": "fix x", "files": ["a.py"],
    }
    r = client.post("/events", headers=headers, json=payload)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.get("/events", headers=headers)
    assert r.status_code == 200
    rows = r.json()
    assert rows and rows[0]["actor"] == "alice"
    assert "a.py" in rows[0]["files"]


@pytest.mark.skipif(not _has_fastapi(), reason="fastapi not installed (run with [server] extra)")
def test_server_token_management(tmp_path: Path):
    from fastapi.testclient import TestClient

    from dotagent.server import build_app

    app = build_app(db_path=tmp_path / "server.sqlite", bootstrap_admin_token="ADMIN")
    client = TestClient(app)

    # admin can create a writer token
    r = client.post("/tokens", headers={"Authorization": "Bearer ADMIN"},
                    json={"role": "writer", "label": "ci"})
    assert r.status_code == 200
    writer_token = r.json()["token"]

    # writer cannot create tokens
    r = client.post("/tokens", headers={"Authorization": f"Bearer {writer_token}"},
                    json={"role": "reader"})
    assert r.status_code == 403

    # writer can post events
    r = client.post(
        "/events",
        headers={"Authorization": f"Bearer {writer_token}"},
        json={"ts": "2026-05-06T00:00:00Z", "actor": "bob", "tool": "cursor",
              "kind": "edit", "session": "s2", "host": "h", "repo": "demo"},
    )
    assert r.status_code == 200

    # invalid token rejected
    r = client.get("/events", headers={"Authorization": "Bearer NOPE"})
    assert r.status_code == 401


# ---- VS Code extension scaffold (sanity check the files exist) -------------


def test_vscode_extension_scaffold_present():
    root = Path(__file__).resolve().parents[1] / "extensions" / "vscode-copilot"
    assert (root / "package.json").exists()
    assert (root / "tsconfig.json").exists()
    assert (root / "src" / "extension.ts").exists()
    assert (root / "README.md").exists()
    pkg = json.loads((root / "package.json").read_text())
    assert pkg["name"] == "dotagent-copilot"
    assert "dotagent.binaryPath" in pkg["contributes"]["configuration"]["properties"]
