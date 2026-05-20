from __future__ import annotations

import click

from ..identity import host, new_session_id, resolve
from ..logging import log_exception
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
            # Auto-regenerate adapter files (CLAUDE.md, .cursorrules,
            # copilot-instructions.md, AGENTS.md) so the AI-facing
            # navigation manifest stays in sync with docs/.
            # Skipped if `auto_regen` is explicitly disabled in config.
            auto_regen = (cfg.raw.get("hooks") or {}).get("auto_regen_on_docs", True)
            if auto_regen:
                _regen_adapters(paths, cfg, identity.id)
        except Exception as e:
            log_exception("docs reindex on observe failed", e)

    try:
        from dataclasses import asdict as _asdict

        from ..config import Config
        cfg = Config.load(paths)
        server_cfg = cfg.raw.get("server") or {}
        if server_cfg.get("forward_events") and server_cfg.get("url"):
            _forward_to_server(server_cfg, _asdict(event))
    except Exception as e:
        log_exception("server forward on observe failed", e)


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


def _regen_adapters(paths: Paths, cfg, actor_id: str) -> None:
    """Re-render every enabled adapter (CLAUDE.md, .cursorrules,
    copilot-instructions.md, AGENTS.md) so the navigation manifest
    reflects the latest docs/ state. Called from the pre-commit hook
    when docs/*.md files are staged.

    Failures are logged, not raised — the commit must still succeed.
    """
    from ..adapters import REGISTRY as ADAPTER_REGISTRY
    from ..adapters import get as get_adapter
    from ..context import build as build_context
    from ..render.derived import regenerate_derived_files

    ctx = build_context(paths, actor=actor_id, config=cfg)
    for name in cfg.adapters_enabled:
        if name not in ADAPTER_REGISTRY:
            continue
        adapter = get_adapter(name)(paths)
        try:
            adapter.write(adapter.render(ctx))
        except OSError as e:
            log_exception(f"adapter regen write failed: {name}", e)
    # Refresh derived files too (service-registry, HISTORY.md, dashboard)
    # so they stay in sync with the docs/* the user just edited.
    try:
        regenerate_derived_files(paths)
    except Exception as e:  # noqa: BLE001
        log_exception("derived-files regen on observe failed", e)
