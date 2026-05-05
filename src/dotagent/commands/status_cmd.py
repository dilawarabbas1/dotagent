from __future__ import annotations

import click

from ..config import Config
from ..identity import resolve
from ..paths import Paths, find_repo_root
from ..sources import load_cache


@click.command(help="Summary: identity, adapters, memory + indexed sources.")
def status() -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init`.")
    cfg = Config.load(paths)
    identity = resolve(repo)
    click.echo(f"repo:     {repo}")
    click.echo(f"actor:    {identity.id} <{', '.join(identity.emails) or 'no email'}>")
    click.echo(f"adapters: {', '.join(cfg.adapters_enabled) or '(none)'}")

    sources = load_cache(paths)
    if sources:
        present = sum(1 for s in sources.values() if s.exists)
        click.echo(f"sources:  {present}/{len(sources)} present (run `dotagent reindex` to refresh)")
        for name, s in sorted(sources.items()):
            flag = "ok" if s.exists else "missing"
            click.echo(f"  · {name:20s} {flag:8s}  {s.path}  ({s.summary})")
    else:
        click.echo("sources:  (none indexed — run `dotagent reindex`)")

    epi_count = sum(1 for _ in paths.episodic.rglob("*.jsonl")) if paths.episodic.exists() else 0
    sem_count = sum(1 for _ in paths.semantic.rglob("*.md")) if paths.semantic.exists() else 0
    dream_g = sum(1 for _ in (paths.dream / "graduated").glob("*.md")) if (paths.dream / "graduated").exists() else 0
    dream_c = sum(1 for _ in (paths.dream / "candidates").glob("*.md")) if (paths.dream / "candidates").exists() else 0
    click.echo(f"episodic: {epi_count} session files")
    click.echo(f"semantic: {sem_count} graduated entries")
    click.echo(f"dream:    {dream_c} candidates / {dream_g} graduated")

    working_current = paths.working
    if working_current.exists():
        currents = list(working_current.glob("*/current.json"))
        if currents:
            click.echo(f"working:  {len(currents)} active session(s)")
