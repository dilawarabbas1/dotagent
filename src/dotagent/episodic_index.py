"""SQLite index over episodic JSONL — fast queries for who/activity/timeline/feed/leaderboard.

The JSONL files remain the source of truth (append-only, merge-conflict-free). The
SQLite index is a derived cache: rebuild from JSONL any time. Only stored locally,
gitignored, never shared.

Schema:
- events(id, ts, actor, tool, host, session, kind, repo, branch, files_json,
         diff_sha, summary, tags_json, jsonl_path)
- file_index(file, event_id) — flattened many-to-many for `dotagent who --file`

Indexes are created for ts, actor, tool, kind, file lookups.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .paths import Paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    jsonl_path TEXT,
    UNIQUE(ts, actor, session, kind, summary, diff_sha)
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor);
CREATE INDEX IF NOT EXISTS idx_events_tool ON events(tool);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);

CREATE TABLE IF NOT EXISTS file_index (
    file TEXT NOT NULL,
    event_id INTEGER NOT NULL,
    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_file_index_file ON file_index(file);
"""


def _connect(paths: Paths) -> sqlite3.Connection:
    db_dir = paths.episodic
    db_dir.mkdir(parents=True, exist_ok=True)
    db = db_dir / "index.sqlite"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _index_path(paths: Paths) -> Path:
    return paths.episodic / "index.sqlite"


def rebuild(paths: Paths) -> int:
    """Drop + reindex from JSONL. Returns event count."""
    db = _index_path(paths)
    if db.exists():
        db.unlink()
    conn = _connect(paths)
    n = 0
    try:
        with conn:
            for jsonl in sorted(paths.episodic.rglob("*.jsonl")):
                for line in jsonl.read_text().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    n += _insert(conn, ev, str(jsonl))
    finally:
        conn.close()
    return n


def append(paths: Paths, event: dict, jsonl_path: str = "") -> int:
    """Insert one event into the index. Idempotent on the unique key."""
    conn = _connect(paths)
    try:
        with conn:
            return _insert(conn, event, jsonl_path)
    finally:
        conn.close()


def _insert(conn: sqlite3.Connection, ev: dict, jsonl_path: str) -> int:
    files = ev.get("files") or []
    tags = ev.get("tags") or []
    cur = conn.execute(
        "INSERT OR IGNORE INTO events "
        "(ts, actor, tool, host, session, kind, repo, branch, files_json, diff_sha, summary, tags_json, jsonl_path) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ev.get("ts", ""),
            ev.get("actor", ""),
            ev.get("tool", ""),
            ev.get("host", ""),
            ev.get("session", ""),
            ev.get("kind", ""),
            ev.get("repo", ""),
            ev.get("branch", ""),
            json.dumps(files),
            ev.get("diff_sha", ""),
            ev.get("summary", ""),
            json.dumps(tags),
            jsonl_path,
        ),
    )
    if cur.rowcount == 0:
        return 0
    event_id = cur.lastrowid
    if files:
        conn.executemany(
            "INSERT INTO file_index(file, event_id) VALUES (?, ?)",
            [(f, event_id) for f in files],
        )
    return 1


# -- queries -----------------------------------------------------------------


def who_touched_file(paths: Paths, file: str) -> list[dict]:
    conn = _connect(paths)
    try:
        rows = conn.execute(
            "SELECT actor, tool, COUNT(*) AS n, MAX(ts) AS last_seen "
            "FROM file_index fi JOIN events e ON e.id = fi.event_id "
            "WHERE fi.file = ? GROUP BY actor, tool ORDER BY n DESC",
            (file,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def timeline(paths: Paths, file: str, limit: int = 50) -> list[dict]:
    conn = _connect(paths)
    try:
        rows = conn.execute(
            "SELECT e.ts, e.actor, e.tool, e.kind, e.summary, e.diff_sha "
            "FROM file_index fi JOIN events e ON e.id = fi.event_id "
            "WHERE fi.file = ? ORDER BY e.ts DESC LIMIT ?",
            (file, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def activity(
    paths: Paths,
    *,
    since_iso: str | None = None,
    actor: str | None = None,
    tool: str | None = None,
    kind: str | None = None,
    limit: int = 100,
) -> list[dict]:
    where = ["1=1"]
    params: list = []
    if since_iso:
        where.append("ts >= ?"); params.append(since_iso)
    if actor:
        where.append("actor = ?"); params.append(actor)
    if tool:
        where.append("tool = ?"); params.append(tool)
    if kind:
        where.append("kind = ?"); params.append(kind)
    sql = (
        "SELECT ts, actor, tool, kind, summary, files_json, diff_sha, branch "
        f"FROM events WHERE {' AND '.join(where)} ORDER BY ts DESC LIMIT ?"
    )
    params.append(limit)
    conn = _connect(paths)
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


def feed(paths: Paths, limit: int = 50) -> list[dict]:
    return activity(paths, limit=limit)


def leaderboard(paths: Paths, *, since_iso: str | None = None) -> list[dict]:
    where = ["1=1"]; params: list = []
    if since_iso:
        where.append("ts >= ?"); params.append(since_iso)
    sql = (
        "SELECT actor, tool, COUNT(*) AS events, "
        "       SUM(CASE WHEN kind = 'commit' THEN 1 ELSE 0 END) AS commits, "
        "       SUM(CASE WHEN kind LIKE 'graduat%' THEN 1 ELSE 0 END) AS graduations "
        f"FROM events WHERE {' AND '.join(where)} "
        "GROUP BY actor, tool ORDER BY events DESC"
    )
    conn = _connect(paths)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def search_summary(paths: Paths, query: str, limit: int = 50) -> list[dict]:
    """Substring search over summary/kind. Cheap; FTS5 can replace later."""
    like = f"%{query}%"
    conn = _connect(paths)
    try:
        rows = conn.execute(
            "SELECT ts, actor, tool, kind, summary, files_json "
            "FROM events WHERE summary LIKE ? OR kind LIKE ? "
            "ORDER BY ts DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r); d["files"] = json.loads(d.pop("files_json") or "[]")
        out.append(d)
    return out


def parse_since(since: str) -> str:
    """Parse '7d' / '24h' / '30m' / ISO datetime into ISO-8601 UTC."""
    s = since.strip()
    now = datetime.now(timezone.utc)
    if s.endswith("d") and s[:-1].isdigit():
        dt = now - timedelta(days=int(s[:-1]))
    elif s.endswith("h") and s[:-1].isdigit():
        dt = now - timedelta(hours=int(s[:-1]))
    elif s.endswith("m") and s[:-1].isdigit():
        dt = now - timedelta(minutes=int(s[:-1]))
    elif s.endswith("w") and s[:-1].isdigit():
        dt = now - timedelta(weeks=int(s[:-1]))
    else:
        # assume ISO date / datetime
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            dt = now - timedelta(days=7)
    return dt.isoformat().replace("+00:00", "Z")


def ensure_indexed(paths: Paths) -> int:
    """Rebuild only if the index is missing. Cheap no-op when present."""
    if _index_path(paths).exists():
        return 0
    return rebuild(paths)
