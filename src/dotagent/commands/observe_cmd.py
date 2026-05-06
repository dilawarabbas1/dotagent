from __future__ import annotations

import click

from ..identity import host, new_session_id, resolve
from ..memory import EpisodicEvent, EpisodicMemory, WorkingMemory
from ..paths import Paths, find_repo_root
from ..util import run


@click.command(help="Append an event to episodic memory + update working memory. Used by hooks.")
@click.argument("kind")
@click.option("--tool", default="cli", help="AI tool driving the event.")
@click.option("--summary", default="", help="One-line description.")
@click.option("--files", default="", help="Newline- or comma-separated file list.")
@click.option("--sha", default="", help="Commit SHA, if applicable.")
@click.option("--session", default="", help="Session id (auto-generated if blank).")
def observe(kind, tool, summary, files, sha, session) -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        return  # no-op if dotagent isn't initialized in this repo

    identity = resolve(repo)
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout
    file_list = _parse_files(files)
    session_id = session or new_session_id()

    event = EpisodicEvent(
        ts=EpisodicMemory.now(),
        actor=identity.id,
        tool=tool,
        host=host(),
        session=session_id,
        kind=kind,
        repo=repo.name,
        branch=branch,
        files=file_list,
        diff_sha=sha,
        summary=summary,
    )
    EpisodicMemory(paths).append(event)

    WorkingMemory(paths, identity.id).record_event(
        kind=kind, tool=tool, summary=summary,
        files=file_list, branch=branch, session=session_id,
    )

    if _touches_docs(file_list):
        try:
            from ..config import Config
            from ..sources import reindex_all
            cfg = Config.load(paths)
            reindex_all(
                paths,
                cfg.raw.get("sources") or {},
                embed_full_docs=bool((cfg.raw.get("context") or {}).get("embed_full_docs")),
            )
        except Exception:
            pass

    try:
        from dataclasses import asdict as _asdict

        from ..config import Config
        cfg = Config.load(paths)
        server_cfg = cfg.raw.get("server") or {}
        if server_cfg.get("forward_events") and server_cfg.get("url"):
            _forward_to_server(server_cfg, _asdict(event))
    except Exception:
        pass


def _forward_to_server(server_cfg: dict, payload: dict) -> None:
    import json as _json
    import urllib.request

    url = server_cfg["url"].rstrip("/") + "/events"
    req = urllib.request.Request(
        url,
        data=_json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {server_cfg.get('token', '')}",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=2.0).read()


def _parse_files(s: str) -> list[str]:
    if not s:
        return []
    parts: list[str] = []
    for chunk in s.replace(",", "\n").split("\n"):
        c = chunk.strip()
        if c:
            parts.append(c)
    return parts


def _touches_docs(files: list[str]) -> bool:
    return any(f.startswith("docs/") and f.endswith(".md") for f in files)
