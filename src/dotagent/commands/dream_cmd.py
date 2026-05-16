from __future__ import annotations

import click

from ..dream import generate_candidates, graduate, reject
from ..dream.clustering import available as embeddings_available
from ..dream.clustering import cluster_events
from ..dream.cron import install as cron_install
from ..dream.cron import uninstall as cron_uninstall
from ..dream.cron import write_github_action
from ..dream.lifecycle import expire_stale, rerationale, review_stale
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
@click.option("--no-embeddings", is_flag=True, help="Disable embedding-based clustering even if installed.")
@click.option("--quiet", is_flag=True)
@click.option("--commit-candidates", is_flag=True, help="Reserved: stage candidate files for commit.")
def cmd_run(since: str, min_cluster_size: int, no_embeddings: bool, quiet: bool, commit_candidates: bool) -> None:
    paths = _paths()
    sigs = extract_signals(paths, since=since, min_cluster_size=min_cluster_size)
    if not no_embeddings and embeddings_available():
        sigs.extend(cluster_events(paths, since=since, min_cluster_size=min_cluster_size))
    written = generate_candidates(paths, sigs)
    if not quiet:
        embed_state = "on" if (not no_embeddings and embeddings_available()) else "off (heuristic only)"
        click.echo(f"embeddings: {embed_state}")
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


# ---- Module 2: lifecycle ---------------------------------------------------


@dream_group.command(name="review-stale", help="List graduated rules due for review (or whose cited files churned).")
@click.option("--due-soon-days", default=14, type=int,
              help="Also include rules whose review_after falls within the next N days.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def cmd_review_stale(due_soon_days: int, fmt: str) -> None:
    paths = _paths()
    stale = review_stale(paths, include_due_soon_days=due_soon_days)
    if fmt == "json":
        import json
        click.echo(json.dumps([s.to_dict() for s in stale], indent=2))
        return
    if not stale:
        click.echo("(no rules are due for review)")
        return
    click.echo(f"{len(stale)} rule(s) due for review:")
    for s in stale:
        flag = {
            "review_after_passed":  f"⏰ {s.days_overdue}d overdue",
            "due_soon":             f"⏳ due in {-s.days_overdue}d",
            "cited_files_churned":  "📁 cited files changed",
            "legacy_no_metadata":   f"🕰  legacy ({s.days_overdue}d past default lifetime)",
        }.get(s.reason, s.reason)
        click.echo(f"  · {s.path.stem:50s} {flag:30s} {s.entry.title[:60]}")
    click.echo("\n→ to re-rationale: `dotagent dream rerationale <rule-id> --rationale \"...\"`")
    click.echo("→ to retire stale:  `dotagent dream expire-stale`")


@dream_group.command(name="rerationale", help="Mark a stale rule as reviewed. Rationale REQUIRED.")
@click.argument("rule_id")
@click.option("--rationale", required=True, help="Why this rule is still valid. Mandatory.")
@click.option("--extend-days", default=None, type=int, help="Extend review_after by N days (default: full lifetime).")
def cmd_rerationale(rule_id: str, rationale: str, extend_days: int | None) -> None:
    paths = _paths()
    try:
        target = rerationale(paths, rule_id, rationale=rationale, extend_days=extend_days)
    except (FileNotFoundError, ValueError) as e:
        raise click.ClickException(str(e))
    click.echo(f"✓ re-rationaled → {target.relative_to(paths.repo)}")


@dream_group.command(name="expire-stale", help="Move past-grace stale rules to dream/expired/ (never deletes).")
@click.option("--grace-period-days", default=30, type=int)
@click.option("--dry-run", is_flag=True)
def cmd_expire_stale(grace_period_days: int, dry_run: bool) -> None:
    paths = _paths()
    moved = expire_stale(paths, grace_period_days=grace_period_days, dry_run=dry_run)
    if not moved:
        click.echo("(no rules past grace period)")
        return
    verb = "would move" if dry_run else "moved"
    click.echo(f"{verb} {len(moved)} rule(s) to {paths.dream / 'expired'}:")
    for p in moved:
        click.echo(f"  · {p.name}")
