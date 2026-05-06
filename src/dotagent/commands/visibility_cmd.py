"""Phase 2 visibility commands: who, activity, timeline, feed, leaderboard, search."""

from __future__ import annotations

import json

import click

from .. import episodic_index as idx
from ..paths import Paths, find_repo_root


def _paths() -> Paths:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init` first.")
    idx.ensure_indexed(paths)
    return paths


@click.command(name="who", help="Who touched a file or rule, with which AI tool.")
@click.option("--file", "file_", default="", help="Show every actor that touched this file.")
@click.option("--rule", default="", help="Show actors involved with this semantic rule slug.")
def who(file_: str, rule: str) -> None:
    if not file_ and not rule:
        raise click.ClickException("Pass --file <path> or --rule <slug>.")
    paths = _paths()
    if file_:
        rows = idx.who_touched_file(paths, file_)
        if not rows:
            click.echo(f"no events touch `{file_}`"); return
        click.echo(f"actors who touched {file_}:")
        for r in rows:
            click.echo(f"  · {r['actor']:20s} via {r['tool']:14s} {r['n']:>4d} events  last={r['last_seen'][:10]}")
        return
    rows = idx.search_summary(paths, rule)
    if not rows:
        click.echo(f"no events mention `{rule}`"); return
    click.echo(f"events mentioning rule `{rule}`:")
    for r in rows[:25]:
        click.echo(f"  · {r['ts'][:10]}  {r['actor']:18s} {r['tool']:12s}  {r['summary'][:80]}")


@click.command(name="activity", help="Filtered event feed.")
@click.option("--since", default="7d", help="Lookback window: 7d / 24h / 30m / ISO datetime.")
@click.option("--by", default="", help="Filter by actor id.")
@click.option("--tool", default="", help="Filter by AI tool.")
@click.option("--kind", default="", help="Filter by event kind.")
@click.option("--limit", default=50, type=int)
def activity(since: str, by: str, tool: str, kind: str, limit: int) -> None:
    paths = _paths()
    rows = idx.activity(paths, since_iso=idx.parse_since(since), actor=by or None,
                        tool=tool or None, kind=kind or None, limit=limit)
    _print_events(rows)


@click.command(name="timeline", help="Per-file edit timeline (latest first).")
@click.argument("file_")
@click.option("--limit", default=50, type=int)
def timeline(file_: str, limit: int) -> None:
    paths = _paths()
    rows = idx.timeline(paths, file_, limit=limit)
    if not rows:
        click.echo(f"no events touch `{file_}`"); return
    for r in rows:
        sha = (r.get("diff_sha") or "")[:7]
        click.echo(f"  {r['ts'][:19].replace('T', ' ')}  {r['actor']:18s} {r['tool']:12s}  "
                   f"{r['kind']:14s} {sha:7s}  {r.get('summary', '')[:80]}")


@click.command(name="feed", help="Chronological team-wide event stream.")
@click.option("--limit", default=50, type=int)
def feed(limit: int) -> None:
    paths = _paths()
    _print_events(idx.feed(paths, limit=limit))


@click.command(name="leaderboard", help="Per-actor activity counts.")
@click.option("--since", default="30d", help="Lookback window.")
def leaderboard(since: str) -> None:
    paths = _paths()
    rows = idx.leaderboard(paths, since_iso=idx.parse_since(since))
    if not rows:
        click.echo("no events in window"); return
    click.echo(f"{'actor':22s} {'tool':14s} {'events':>7s} {'commits':>8s} {'graduations':>12s}")
    for r in rows:
        click.echo(f"{r['actor']:22s} {r['tool']:14s} {r['events']:>7d} {r['commits']:>8d} {r['graduations']:>12d}")


@click.command(name="reindex-events", help="Rebuild the SQLite event index from JSONL.")
def reindex_events() -> None:
    paths = _paths()
    n = idx.rebuild(paths)
    click.echo(f"indexed {n} events")


def _print_events(rows: list[dict]) -> None:
    if not rows:
        click.echo("(no events)"); return
    for r in rows:
        files = r.get("files") or []
        head = f"  {r['ts'][:19].replace('T', ' ')}  {r['actor']:18s} {r['tool']:12s} {r['kind']:14s}"
        if r.get("summary"):
            head += f"  {r['summary'][:90]}"
        click.echo(head)
        if files:
            click.echo("    files: " + ", ".join(files[:5]))
