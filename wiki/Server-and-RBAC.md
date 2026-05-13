# Server and RBAC

Optional centralized event server for teams. Forwards every `dotagent observe`
event to a central place; provides an SSE live stream + small dashboard so
you can watch the whole team's coding activity across every repo in real
time.

You don't need it. Multi-developer + multi-AI-tool attribution works
perfectly with just the per-repo episodic JSONL files committed to git.
The server is an opt-in convenience for teams that want a real-time view.

## Install + run

```bash
pip install 'dotagent[server]'         # adds fastapi + uvicorn

dotagent serve --host 0.0.0.0 --port 9700
# [bootstrap] admin token: kvB9rL0eQjV...
# dotagent server → http://0.0.0.0:9700  db=~/.local/share/dotagent/server.sqlite
```

Save the printed admin token — you'll use it to mint scoped tokens for
your team.

Behind a reverse proxy (recommended): bind `--host 127.0.0.1`, terminate
TLS in nginx/Caddy, forward to `127.0.0.1:9700`.

## RBAC

Three roles:

| Role | Can do |
|------|--------|
| `admin` | everything; mint and revoke tokens |
| `writer` | POST events; cannot read history or stream |
| `reader` | GET events / SSE stream / dashboard; cannot post |

The bootstrap token is `admin`. Use it to mint scoped tokens.

```bash
# mint a writer token for CI / each teammate's machine
curl -X POST https://dotagent.internal:9700/tokens \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"role":"writer","label":"alice@laptop"}'
# {"token":"...","role":"writer"}

# mint a reader token for a dashboard user
curl -X POST https://dotagent.internal:9700/tokens \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -d '{"role":"reader","label":"team-lead"}'

# revoke
curl -X DELETE https://dotagent.internal:9700/tokens/$TOKEN \
     -H "Authorization: Bearer $ADMIN_TOKEN"
```

## Client config

In each repo's `.agent/config.yaml`:

```yaml
server:
  url: https://dotagent.internal:9700
  token: <writer-token-for-this-actor>
  forward_events: true
```

`dotagent observe` will now POST every event to the server in addition to
writing to local JSONL + SQLite. Failures forward silently (set
`DOTAGENT_DEBUG=1` to surface them).

## API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | none | HTML dashboard |
| `GET` | `/health` | none | `{"ok": true}` |
| `POST` | `/events` | writer | Insert an event |
| `GET` | `/events` | reader | List events; query: `?since_id=N&actor=...&repo=...&tool=...&limit=N` |
| `GET` | `/events/stream` | reader | Server-Sent Events live stream; query: `?token=...&repo=...&actor=...` |
| `POST` | `/tokens` | admin | Mint a token; body: `{"role":"...","label":"..."}` |
| `DELETE` | `/tokens/{token}` | admin | Revoke |

Auth is `Authorization: Bearer <token>` header OR `?token=<>` query param
(useful for SSE which can't set headers from browsers).

## The dashboard

Open `https://dotagent.internal:9700/` in a browser, paste a reader token,
optionally filter by repo / actor, click connect. SSE streams every new
event as it arrives.

```
ts                actor   tool          kind     repo            summary             files
2026-05-06 12:34  alice   claude_code   commit   aigent-portal   fix bug-007         src/auth.py
2026-05-06 12:30  bob     cursor        edit     aigent-backend  refactor handler    src/api.py
```

## Storage

SQLite, default at `~/.local/share/dotagent/server.sqlite`. Override with
`--db <path>`. Schema is in `src/dotagent/server/storage.py`.

Back up with a regular SQLite dump; you can also rebuild from the per-repo
JSONL files in everyone's git history (the server is a cache of those).

## Production checklist

- [ ] TLS termination in front of the server (nginx / Caddy / Cloudflare).
- [ ] Bind `--host 127.0.0.1` and forward through the proxy; don't expose 9700 directly.
- [ ] Rate-limit in the proxy (we don't enforce it in-app).
- [ ] Rotate admin tokens periodically; mint scoped writer tokens per
      teammate so revocation is per-person.
- [ ] Back up the SQLite file (cron `cp -p server.sqlite server.sqlite.bak`).
- [ ] Set `DOTAGENT_DEBUG=1` on the server host for richer logging.

## What's NOT in the server (deliberately)

- No multi-tenant orgs (one-team-per-instance).
- No OIDC / SSO. Use token-based auth + your proxy's auth layer for SSO.
- No retention policies. The DB grows forever; vacuum/prune yourself if needed.
- No write-side validation beyond `event must be an object`. Trust the writer token.

If you need any of those, fork it — the server is ~150 lines.

## Next

- **[[Multi-Project and Multi-Developer]]** — pointing many repos at one server
- **[[Commands Reference]]** — full `dotagent serve` options
