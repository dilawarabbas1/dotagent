from __future__ import annotations

import click

from ..identity import host, new_session_id, resolve
from ..memory import EpisodicEvent, EpisodicMemory
from ..paths import Paths, find_repo_root
from ..util import run


@click.command(help="Append an event to episodic memory. Used by hooks.")
@click.argument("kind")
@click.option("--tool", default="cli", help="AI tool driving the event.")
@click.option("--summary", default="", help="One-line description.")
@click.option("--files", default="", help="Newline-separated file list.")
@click.option("--sha", default="", help="Commit SHA, if applicable.")
def observe(kind, tool, summary, files, sha) -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        return  # no-op if dotagent isn't initialized in this repo
    identity = resolve(repo)
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout
    file_list = [f for f in (files or "").split("\n") if f.strip()]
    event = EpisodicEvent(
        ts=EpisodicMemory.now(),
        actor=identity.id,
        tool=tool,
        host=host(),
        session=new_session_id(),
        kind=kind,
        repo=repo.name,
        branch=branch,
        files=file_list,
        diff_sha=sha,
        summary=summary,
    )
    EpisodicMemory(paths).append(event)
