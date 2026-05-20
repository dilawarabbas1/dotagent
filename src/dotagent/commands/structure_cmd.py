"""`dotagent structure` — inspect the canonical structure of a project.

Three subcommands:

- `structure show`   — print the canonical schema for a tier (read-only)
- `structure check`  — audit the current repo against the schema
- `structure version` — print the schema version this dotagent expects
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ..canonical_structure import (
    CURRENT_SCHEMA_VERSION,
    KIND_DIR,
    KIND_FILE,
    KIND_GENERATED,
    KIND_OPTIONAL,
    TIER_PROJECT_ROOT,
    TIER_SERVICE_REPO,
    TIER_SINGLE_REPO,
    detect_tier,
    schema_for,
)
from ..structure_checker import (
    SEVERITY_FAIL,
    SEVERITY_INFO,
    SEVERITY_WARN,
    check,
)


_TIER_CHOICES = (TIER_PROJECT_ROOT, TIER_SERVICE_REPO, TIER_SINGLE_REPO)


@click.group(help="Inspect a dotagent project's canonical structure.")
def structure() -> None:
    pass


@structure.command(name="show", help="Print the canonical schema for a tier.")
@click.option(
    "--tier", type=click.Choice(_TIER_CHOICES), default=None,
    help="Which tier to show. If omitted, infers from the current repo.",
)
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
def show(tier: str | None, fmt: str) -> None:
    repo = Path.cwd()
    if tier is None:
        tier = detect_tier(repo)
    entries = schema_for(tier)

    if fmt == "json":
        payload = {
            "tier": tier,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "entries": [
                {
                    "path": e.path,
                    "required": e.required,
                    "kind": e.kind,
                    "since": e.since,
                    "description": e.description,
                }
                for e in entries
            ],
        }
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(f"tier:           {tier}")
    click.echo(f"schema version: {CURRENT_SCHEMA_VERSION}")
    click.echo(f"entries:        {len(entries)}")
    click.echo("")
    click.echo(f"{'PATH':<48} {'REQ':<5} {'KIND':<10} {'SINCE':<7} DESCRIPTION")
    click.echo("-" * 100)
    for e in entries:
        req = "yes" if e.required else "-"
        click.echo(f"{e.path:<48} {req:<5} {e.kind:<10} {e.since:<7} {e.description}")


@structure.command(name="check", help="Audit the current repo against the canonical schema.")
@click.option(
    "--tier", type=click.Choice(_TIER_CHOICES), default=None,
    help="Override the detected tier.",
)
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def check_cmd(tier: str | None, fmt: str) -> None:
    repo = Path.cwd()
    result = check(repo, tier=tier)

    if fmt == "json":
        click.echo(json.dumps(result.to_dict(), indent=2))
        sys.exit(0 if result.ok else 1)

    glyph = {SEVERITY_FAIL: "✗", SEVERITY_WARN: "!", SEVERITY_INFO: "i"}
    click.echo(f"tier:           {result.tier}")
    click.echo(f"schema version: {result.schema_version}")
    click.echo(f"actual version: {result.actual_version or '(none)'}")
    if result.needs_migration:
        click.echo(
            "version drift detected — run `dotagent migrate` to upgrade."
        )
    click.echo("")
    if not result.deviations:
        click.echo("no deviations. structure is clean.")
        return

    for d in result.deviations:
        g = glyph.get(d.severity, "?")
        click.echo(f"  [{g}] {d.path}")
        click.echo(f"        {d.reason}")
        if d.fix:
            click.echo(f"        fix: {d.fix}")
    sys.exit(0 if result.ok else 1)


@structure.command(name="version", help="Print the schema version this dotagent expects.")
def version_cmd() -> None:
    click.echo(CURRENT_SCHEMA_VERSION)
