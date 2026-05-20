"""`dotagent archive` — document lifecycle commands.

- `scan`    — list every archive-eligible entry (read-only)
- `run`     — execute archival; logs every move
- `restore` — un-archive one entry by id
- `list`    — show what's been archived
"""

from __future__ import annotations

import json
import sys

import click

from ..archive import (
    ArchiveCandidate,
    list_archived,
    restore,
    run,
    scan,
)
from ..paths import find_repo_root


@click.group(help="Move historical entries (fixed bugs, rescinded patterns, shipped modules) to docs/archive/.")
def archive() -> None:
    pass


@archive.command(name="scan", help="Report archive-eligible entries (read-only).")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def scan_cmd(fmt: str) -> None:
    repo = find_repo_root()
    report = scan(repo)

    if fmt == "json":
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    if not report.candidates:
        click.echo("no archive-eligible entries.")
        return

    click.echo(f"found {len(report.candidates)} archive-eligible entr"
               f"{'y' if len(report.candidates) == 1 else 'ies'}:\n")
    for c in report.candidates:
        click.echo(f"  [{c.source_kind:<14}] {c.entry_id}")
        if c.title:
            click.echo(f"                   title:    {c.title}")
        click.echo(f"                   source:   {c.source_path}")
        click.echo(f"                   reason:   {c.reason}")
        if c.eligible_since:
            click.echo(f"                   since:    {c.eligible_since}")
        click.echo("")
    click.echo("run `dotagent archive run` to apply.")


@archive.command(name="run", help="Move every eligible entry to its archive location.")
@click.option("--dry-run", is_flag=True, help="Show what would move; touch nothing.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def run_cmd(dry_run: bool, yes: bool, fmt: str) -> None:
    repo = find_repo_root()
    report = scan(repo)

    if not report.candidates:
        if fmt == "json":
            click.echo(json.dumps({"moved": [], "skipped": [], "errors": []}, indent=2))
        else:
            click.echo("no archive-eligible entries.")
        return

    if not dry_run and not yes and fmt == "text":
        click.echo(f"would archive {len(report.candidates)} entr"
                   f"{'y' if len(report.candidates) == 1 else 'ies'}.")
        click.confirm("proceed?", abort=True)

    result = run(repo, dry_run=dry_run, candidates=report.candidates)

    if fmt == "json":
        click.echo(json.dumps(result.to_dict(), indent=2))
        sys.exit(1 if result.errors else 0)

    if dry_run:
        click.echo(f"[--dry-run] would move {len(result.moved)} entr"
                   f"{'y' if len(result.moved) == 1 else 'ies'}:")
    else:
        click.echo(f"moved {len(result.moved)} entr"
                   f"{'y' if len(result.moved) == 1 else 'ies'}:")
    for m in result.moved:
        click.echo(f"  {m.entry_id} ({m.source_kind}): {m.source_path} → {m.archive_path}")
    if result.errors:
        click.echo(f"\n✗ {len(result.errors)} error(s):")
        for entry_id, reason in result.errors:
            click.echo(f"  {entry_id}: {reason}")
        sys.exit(1)


@archive.command(name="restore", help="Un-archive one entry by ID.")
@click.argument("entry_id")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def restore_cmd(entry_id: str, fmt: str) -> None:
    repo = find_repo_root()
    try:
        entry = restore(repo, entry_id)
    except FileNotFoundError as exc:
        msg = str(exc)
        if fmt == "json":
            click.echo(json.dumps({"error": msg}, indent=2))
        else:
            click.echo(f"error: {msg}", err=True)
        sys.exit(1)

    if entry is None:
        msg = f"entry {entry_id!r} not found in archive (or already restored)"
        if fmt == "json":
            click.echo(json.dumps({"error": msg}, indent=2))
        else:
            click.echo(msg, err=True)
        sys.exit(1)

    if fmt == "json":
        click.echo(json.dumps(entry.to_dict(), indent=2))
        return
    click.echo(
        f"restored {entry.entry_id} ({entry.source_kind}): "
        f"{entry.archive_path} → {entry.source_path}"
    )


@archive.command(name="list", help="Show every archived entry.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--source", type=str, default=None, help="Filter by source kind (e.g. bug-registry).")
@click.option("--show-restored", is_flag=True, help="Include restored entries (default: hidden).")
def list_cmd(fmt: str, source: str | None, show_restored: bool) -> None:
    repo = find_repo_root()
    entries = list_archived(repo)
    if source:
        entries = [e for e in entries if e.source_kind == source]
    if not show_restored:
        entries = [e for e in entries if not e.restored_at]

    if fmt == "json":
        click.echo(json.dumps([e.to_dict() for e in entries], indent=2))
        return

    if not entries:
        click.echo("archive is empty.")
        return

    click.echo(f"{len(entries)} archived entr"
               f"{'y' if len(entries) == 1 else 'ies'}:")
    for e in entries:
        mark = " [restored]" if e.restored_at else ""
        click.echo(f"  {e.entry_id} ({e.source_kind}){mark}")
        click.echo(f"    archived: {e.timestamp}")
        click.echo(f"    path:     {e.archive_path}")
