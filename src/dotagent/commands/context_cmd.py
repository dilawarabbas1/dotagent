from __future__ import annotations

import click

from ..adapters.render import render_body
from ..config import Config
from ..context import build
from ..identity import resolve
from ..paths import Paths, find_repo_root


@click.command(help="Print the merged Context the agents see. Useful for debugging.")
@click.option("--format", "fmt", type=click.Choice(["summary", "markdown", "json"]), default="summary")
def context(fmt: str) -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init` first.")
    cfg = Config.load(paths)
    identity = resolve(repo)
    ctx = build(paths, actor=identity.id, config=cfg)

    if fmt == "markdown":
        click.echo(render_body(ctx, tool_label="dotagent context"))
        return

    if fmt == "json":
        import json
        from dataclasses import asdict
        payload = {
            "project": ctx.project_name,
            "actor": ctx.actor,
            "current": ctx.current.to_dict(),
            "sources": {
                name: {"path": s.path, "exists": s.exists, "summary": s.summary, "n_entries": len(s.entries)}
                for name, s in ctx.sources.items()
            },
            "personal": ctx.personal,
            "recent_episodic": ctx.recent_episodic,
            "agent_files_present": {
                "style": bool(ctx.agent.style),
                "rules": bool(ctx.agent.rules),
                "architecture": bool(ctx.agent.architecture),
                "patterns": bool(ctx.agent.patterns),
                "preferences": bool(ctx.agent.preferences),
            },
        }
        click.echo(json.dumps(payload, indent=2))
        return

    # summary (default)
    click.echo(f"project:  {ctx.project_name}")
    click.echo(f"actor:    {ctx.actor}")
    click.echo(f"branch:   {ctx.current.branch or '(unknown)'}")
    if ctx.current.task:
        click.echo(f"task:     {ctx.current.task}")
    click.echo("sources:")
    if not ctx.sources:
        click.echo("  (none indexed — run `dotagent reindex`)")
    for name, s in sorted(ctx.sources.items()):
        flag = "ok" if s.exists else "missing"
        click.echo(f"  · {name:20s} {flag:8s}  {s.path}  ({s.summary})")
    click.echo(f"recent files:    {len(ctx.current.recent_files)}")
    click.echo(f"recent events:   {len(ctx.recent_episodic)}")
    if ctx.top_bugs():
        click.echo(f"bug registry:    top {len(ctx.top_bugs())} surfaced to adapters")
    if ctx.top_anti_patterns():
        click.echo(f"anti-patterns:   top {len(ctx.top_anti_patterns())} surfaced to adapters")
