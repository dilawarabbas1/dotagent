from __future__ import annotations

import click

from ..dream import generate_candidates, graduate, reject
from ..dream.cron import install as cron_install
from ..dream.cron import uninstall as cron_uninstall
from ..dream.cron import write_github_action
from ..dream.pipeline import list_candidates
from ..dream.signals import extract_signals
from ..paths import Paths, find_repo_root


def _paths() -> Paths:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init` first.")
    return paths


@click.group(name="dream", help="Auto-Dream: cluster experience → candidates → graduate with rationale.")
def dream_group() -> None:
    pass


@dream_group.command(name="run", help="Extract signals + write candidate files.")
@click.option("--since", default="30d")
@click.option("--min-cluster-size", type=int, default=3)
@click.option("--quiet", is_flag=True)
@click.option("--commit-candidates", is_flag=True, help="Reserved: stage candidate files for commit.")
def cmd_run(since: str, min_cluster_size: int, quiet: bool, commit_candidates: bool) -> None:
    paths = _paths()
    sigs = extract_signals(paths, since=since, min_cluster_size=min_cluster_size)
    written = generate_candidates(paths, sigs)
    if not quiet:
        click.echo(f"signals: {len(sigs)}; candidates written: {len(written)}")
        for s in sigs:
            click.echo(f"  · [{s.kind}] {s.title}")


@dream_group.command(name="list", help="List pending candidates.")
def cmd_list() -> None:
    paths = _paths()
    cands = list_candidates(paths)
    if not cands:
        click.echo("(no candidates — run `dotagent dream run`)")
        return
    for c in cands:
        head = ""
        for line in c.read_text().splitlines():
            if line.startswith("# "):
                head = line[2:].strip()
                break
        click.echo(f"  · {c.stem:12s}  {head}")


@dream_group.command(name="graduate", help="Promote a candidate to a graduated rule. Rationale REQUIRED.")
@click.argument("candidate_id")
@click.option("--rationale", required=True, help="Why this rule should govern the codebase. Mandatory.")
def cmd_graduate(candidate_id: str, rationale: str) -> None:
    paths = _paths()
    target = graduate(paths, candidate_id, rationale)
    click.echo(f"graduated → {target}")


@dream_group.command(name="reject", help="Reject a candidate. Rationale REQUIRED.")
@click.argument("candidate_id")
@click.option("--rationale", required=True, help="Why this candidate is wrong. Mandatory.")
def cmd_reject(candidate_id: str, rationale: str) -> None:
    paths = _paths()
    target = reject(paths, candidate_id, rationale)
    click.echo(f"rejected → {target}")


@dream_group.command(name="cron-install", help="Install a daily cron entry that runs auto-dream.")
@click.option("--schedule", default="0 2 * * *", help="Cron schedule (default: 02:00 daily).")
def cmd_cron_install(schedule: str) -> None:
    paths = _paths()
    line = cron_install(paths, schedule=schedule)
    click.echo(f"installed: {line}")


@dream_group.command(name="cron-uninstall", help="Remove the dotagent dream cron entry for this repo.")
def cmd_cron_uninstall() -> None:
    paths = _paths()
    n = cron_uninstall(paths)
    click.echo(f"removed {n} entries")


@dream_group.command(name="github-action", help="Write the dotagent dream GitHub Action template.")
def cmd_github_action() -> None:
    paths = _paths()
    target = write_github_action(paths)
    click.echo(f"wrote {target}")
