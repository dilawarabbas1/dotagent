from __future__ import annotations

import click

from ..config import Config
from ..paths import Paths, find_repo_root
from ..sources import reindex_all


@click.command(help="Re-parse every configured source under `docs/`. Updates cache + pointer cards.")
@click.option("--embed-full-docs", is_flag=True, help="Cache full doc text in addition to entries.")
def reindex(embed_full_docs: bool) -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init` first.")
    cfg = Config.load(paths)
    sources_cfg = cfg.raw.get("sources") or {}
    embed = embed_full_docs or bool((cfg.raw.get("context") or {}).get("embed_full_docs"))
    idx = reindex_all(paths, sources_cfg, embed_full_docs=embed)
    click.echo(f"reindexed {len(idx)} sources:")
    for name, src in sorted(idx.items()):
        flag = "ok" if src.exists else "missing"
        click.echo(f"  · {name:20s} {flag:8s}  {src.path}  ({src.summary})")
