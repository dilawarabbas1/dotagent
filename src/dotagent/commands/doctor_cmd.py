from __future__ import annotations

import sys

import click

from ..doctor import run_checks


_GLYPH = {"ok": "✓", "warn": "!", "fail": "✗", "info": "i"}


@click.command(help="Self-check for common misconfigurations.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def doctor(fmt: str) -> None:
    diagnoses = run_checks()
    if fmt == "json":
        import json
        payload = [
            {"name": d.name, "status": d.status, "message": d.message, "fix": d.fix}
            for d in diagnoses
        ]
        click.echo(json.dumps(payload, indent=2))
    else:
        for d in diagnoses:
            glyph = _GLYPH.get(d.status, "?")
            click.echo(f"  [{glyph}] {d.name:22s} {d.message}")
            if d.fix:
                click.echo(f"        fix: {d.fix}")
    if any(d.status == "fail" for d in diagnoses):
        sys.exit(1)
