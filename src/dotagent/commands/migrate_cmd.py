from __future__ import annotations

import click

from ..migrate import migrate
from ..paths import Paths, find_repo_root
from ..sources import reindex_all
from ..config import Config


@click.command(help="Migrate a Claude-Code-Optimization repo into dotagent layout (lossless).")
@click.option("--dry-run", is_flag=True, help="Report what would change; write nothing.")
def migrate_cco(dry_run: bool) -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init` first.")
    report = migrate(paths, write=not dry_run)
    click.echo(f"referenced sources ({len(report.referenced_sources)}):")
    for s in report.referenced_sources:
        click.echo(f"  · {s}")
    click.echo(f"\nimported skills ({len(report.imported_skills)}):")
    for s in report.imported_skills:
        click.echo(f"  · {s}")
    click.echo(f"\ningested buckets ({len(report.ingested_buckets)}): "
               + (", ".join(report.ingested_buckets) or "(none)"))
    for n in report.notes:
        click.echo(f"\nnote: {n}")
    if dry_run:
        click.echo("\n[dry-run] nothing was written.")
        return
    cfg = Config.load(paths)
    reindex_all(paths, cfg.raw.get("sources") or {})
    click.echo("\n→ run `dotagent sync` to render adapters with the migrated context.")
