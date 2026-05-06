"""SQLite-backed storage + an asyncio fan-out queue for SSE subscribers.

Storage is local to the server (configurable path). Multi-tenant scoping is
done by repo+actor — the dashboard filters on those. RBAC is the token map
(token → role). Roles: `writer` (POST events), `reader` (GET stream/list),
`admin` (manage tokens).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_ts INTEGER NOT NULL,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    tool TEXT NOT NULL,
    host TEXT,
    session TEXT,
    kind TEXT NOT NULL,
    repo TEXT,
    branch TEXT,
    files_json TEXT,
    diff_sha TEXT,
    summary TEXT,
    tags_json TEXT,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_server_ts ON events(server_ts);
CREATE INDEX IF NOT EXISTS idx_events_repo ON events(repo);
CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor);

CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    label TEXT,
    created_at INTEGER NOT NULL
);
"""


@dataclass
class Settings:
    db_path: Path
    bootstrap_admin_token: str | None = None
    history_limit: int = 500
    subscribers: set[asyncio.Queue] = field(default_factory=set)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def init_db(settings: Settings) -> None:
    conn = _connect(settings.db_path)
    try:
        with conn:
            if settings.bootstrap_admin_token:
                conn.execute(
                    "INSERT OR IGNORE INTO tokens(token, role, label, created_at) VALUES(?, 'admin', 'bootstrap', ?)",
                    (settings.bootstrap_admin_token, int(time.time())),
                )
    finally:
        conn.close()


def insert_event(settings: Settings, event: dict) -> int:
    conn = _connect(settings.db_path)
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO events "
                "(server_ts, ts, actor, tool, host, session, kind, repo, branch, files_json, "
                " diff_sha, summary, tags_json, raw_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    int(time.time()),
                    event.get("ts", ""),
                    event.get("actor", ""),
                    event.get("tool", ""),
                    event.get("host", ""),
                    event.get("session", ""),
                    event.get("kind", ""),
                    event.get("repo", ""),
                    event.get("branch", ""),
                    json.dumps(event.get("files") or []),
                    event.get("diff_sha", ""),
                    event.get("summary", ""),
                    json.dumps(event.get("tags") or []),
                    json.dumps(event),
                ),
            )
            return cur.lastrowid or 0
    finally:
        conn.close()


def list_events(settings: Settings, *, since_id: int = 0, limit: int = 100,
                actor: str | None = None, repo: str | None = None,
                tool: str | None = None) -> list[dict]:
    where = ["id > ?"]; params: list[Any] = [since_id]
    if actor: where.append("actor = ?"); params.append(actor)
    if repo:  where.append("repo = ?");  params.append(repo)
    if tool:  where.append("tool = ?");  params.append(tool)
    sql = (f"SELECT id, server_ts, ts, actor, tool, kind, repo, branch, summary, files_json "
           f"FROM events WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?")
    params.append(limit)
    conn = _connect(settings.db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["files"] = json.loads(d.pop("files_json") or "[]")
        out.append(d)
    return out


def lookup_token(settings: Settings, token: str) -> dict | None:
    if not token:
        return None
    conn = _connect(settings.db_path)
    try:
        row = conn.execute("SELECT token, role, label FROM tokens WHERE token = ?", (token,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def add_token(settings: Settings, token: str, role: str, label: str = "") -> None:
    conn = _connect(settings.db_path)
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO tokens(token, role, label, created_at) VALUES(?, ?, ?, ?)",
                (token, role, label, int(time.time())),
            )
    finally:
        conn.close()


def revoke_token(settings: Settings, token: str) -> bool:
    conn = _connect(settings.db_path)
    try:
        with conn:
            cur = conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
            return cur.rowcount > 0
    finally:
        conn.close()


async def fan_out(settings: Settings, event: dict) -> None:
    dead: list[asyncio.Queue] = []
    for q in list(settings.subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        settings.subscribers.discard(q)
