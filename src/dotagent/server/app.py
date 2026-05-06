"""FastAPI app: events POST/GET, SSE stream, token management, dashboard."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path
from typing import Any

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]

from . import storage
from .storage import Settings


_DASHBOARD_HTML = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>dotagent server</title>
<style>
  body { font-family: ui-monospace, Menlo, Consolas, monospace; margin: 24px; color: #1a1a1a; }
  h1 { font-size: 16px; margin-bottom: 8px; }
  .filters { margin: 12px 0; }
  .filters input { padding: 4px 8px; font-family: inherit; margin-right: 8px; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  td, th { padding: 4px 8px; border-bottom: 1px solid #eee; text-align: left; }
  th { background: #f4f4f4; }
  .actor { color: #0a4ea0; }
  .tool  { color: #7a3a96; }
  .kind  { color: #2a7a2a; font-weight: 600; }
  .files { color: #777; font-size: 12px; }
</style>
</head><body>
<h1>dotagent — live event stream</h1>
<div class="filters">
  <label>token: <input id="token" placeholder="reader/admin token"></label>
  <label>repo: <input id="repo" placeholder="(any)"></label>
  <label>actor: <input id="actor" placeholder="(any)"></label>
  <button id="connect">connect</button>
</div>
<table>
  <thead><tr><th>ts</th><th>actor</th><th>tool</th><th>kind</th><th>repo</th><th>summary</th><th>files</th></tr></thead>
  <tbody id="rows"></tbody>
</table>
<script>
let es;
document.getElementById('connect').onclick = () => {
  const token = document.getElementById('token').value;
  const repo  = document.getElementById('repo').value;
  const actor = document.getElementById('actor').value;
  const params = new URLSearchParams({ token });
  if (repo)  params.set('repo', repo);
  if (actor) params.set('actor', actor);
  if (es) es.close();
  document.getElementById('rows').innerHTML = '';
  es = new EventSource('/events/stream?' + params.toString());
  es.onmessage = (m) => {
    const e = JSON.parse(m.data);
    const tr = document.createElement('tr');
    const files = (e.files || []).slice(0, 3).join(', ');
    tr.innerHTML = `
      <td>${(e.ts || '').slice(0, 19).replace('T', ' ')}</td>
      <td class="actor">${e.actor || ''}</td>
      <td class="tool">${e.tool || ''}</td>
      <td class="kind">${e.kind || ''}</td>
      <td>${e.repo || ''}</td>
      <td>${(e.summary || '').slice(0, 90)}</td>
      <td class="files">${files}</td>`;
    document.getElementById('rows').prepend(tr);
  };
};
</script>
</body></html>
"""


def _need(role: str):
    """Auth dependency factory. Header: `Authorization: Bearer <token>` or `?token=`."""

    async def dep(request: Request, authorization: str | None = Header(None)) -> dict:
        token = ""
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
        if not token:
            token = request.query_params.get("token", "")
        settings: Settings = request.app.state.settings
        info = storage.lookup_token(settings, token) if token else None
        if not info:
            raise HTTPException(status_code=401, detail="invalid token")
        if role == "admin" and info["role"] != "admin":
            raise HTTPException(status_code=403, detail="admin required")
        if role == "writer" and info["role"] not in ("admin", "writer"):
            raise HTTPException(status_code=403, detail="writer required")
        # reader is the loosest — admin/writer/reader all OK
        return info

    return dep


def build_app(*, db_path: str | os.PathLike, bootstrap_admin_token: str | None = None) -> "FastAPI":
    if FastAPI is None:
        raise RuntimeError("fastapi not installed — run `pip install dotagent[server]`.")
    settings = Settings(db_path=Path(db_path), bootstrap_admin_token=bootstrap_admin_token)
    storage.init_db(settings)

    app = FastAPI(title="dotagent server", version="0.1.0")
    app.state.settings = settings

    @app.get("/", response_class=HTMLResponse)
    async def root() -> str:
        return _DASHBOARD_HTML

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    @app.post("/events", dependencies=[Depends(_need("writer"))])
    async def post_event(request: Request) -> dict:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "event must be an object")
        event_id = storage.insert_event(settings, body)
        await storage.fan_out(settings, body)
        return {"id": event_id, "ok": True}

    @app.get("/events", dependencies=[Depends(_need("reader"))])
    async def list_events(
        since_id: int = 0,
        limit: int = 100,
        actor: str | None = None,
        repo: str | None = None,
        tool: str | None = None,
    ) -> JSONResponse:
        rows = storage.list_events(settings, since_id=since_id, limit=limit,
                                   actor=actor, repo=repo, tool=tool)
        return JSONResponse(rows)

    @app.get("/events/stream", dependencies=[Depends(_need("reader"))])
    async def stream(request: Request) -> StreamingResponse:
        q: asyncio.Queue = asyncio.Queue(maxsize=settings.history_limit)
        settings.subscribers.add(q)

        async def gen():
            try:
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=15.0)
                        yield f"data: {json.dumps(ev)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
            finally:
                settings.subscribers.discard(q)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/tokens", dependencies=[Depends(_need("admin"))])
    async def create_token(request: Request) -> dict:
        body = await request.json()
        role = body.get("role", "reader")
        if role not in ("admin", "writer", "reader"):
            raise HTTPException(400, "role must be admin|writer|reader")
        token = body.get("token") or secrets.token_urlsafe(24)
        storage.add_token(settings, token, role, body.get("label", ""))
        return {"token": token, "role": role}

    @app.delete("/tokens/{token}", dependencies=[Depends(_need("admin"))])
    async def delete_token(token: str) -> dict:
        ok = storage.revoke_token(settings, token)
        return {"revoked": ok}

    return app
