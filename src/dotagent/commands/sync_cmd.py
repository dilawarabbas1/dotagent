from __future__ import annotations

import click

from ..adapters import REGISTRY as ADAPTER_REGISTRY
from ..adapters import get as get_adapter
from ..backup import backup_existing
from ..config import Config
from ..context import build as build_context
from ..diff import diff_rendered, format_diff
from ..hooks import install_claude_hooks, install_git_hooks
from ..identity import resolve, upsert_developer
from ..paths import Paths, find_repo_root
from ..sources import reindex_all


@click.command(help="Re-index docs/ sources, rebuild context, regenerate every adapter. Idempotent.")
@click.option("--no-hooks", is_flag=True, help="Skip hook (re)install.")
@click.option("--no-reindex", is_flag=True, help="Skip docs/ reindex (use cached entries).")
@click.option("--dry-run", is_flag=True, help="Show unified diff vs on-disk files; do not write.")
@click.option(
    "--skip-dotgraph", is_flag=True,
    help="Skip the `dotgraph emit-docs` pre-step. Useful for CI envs without dotgraph installed.",
)
def sync(no_hooks: bool, no_reindex: bool, dry_run: bool, skip_dotgraph: bool) -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.config.exists():
        raise click.ClickException("No .agent/config.yaml found. Run `dotagent init` first.")
    cfg = Config.load(paths)

    identity = resolve(repo)
    upsert_developer(paths, identity)

    # Pre-step: refresh dotgraph's emitted docs (dependency-map, db-impact-map,
    # redis-key-registry, kafka-topics, endpoints) so the subsequent reindex
    # reads fresh content. Best-effort: any failure is logged and ignored —
    # adapter render proceeds against whatever's on disk.
    if not skip_dotgraph and (paths.repo / ".dotgraph" / "graph.db").exists():
        from ..dotgraph_probe import emit_docs as _dg_emit_docs
        ok, msg = _dg_emit_docs(paths.repo)
        if ok:
            click.echo(f"· {msg}")
        else:
            click.echo(f"  ! {msg} (continuing)", err=True)

    if not no_reindex:
        idx = reindex_all(
            paths,
            cfg.raw.get("sources") or {},
            embed_full_docs=bool((cfg.raw.get("context") or {}).get("embed_full_docs")),
        )
        present = sum(1 for s in idx.values() if s.exists)
        click.echo(f"· reindexed {present}/{len(idx)} sources from docs/")

    ctx = build_context(paths, actor=identity.id, config=cfg)

    if not dry_run:
        backups = backup_existing(paths)
        written_backups = [b for b in backups if b.ok]
        if written_backups:
            click.echo(f"· backed up {len(written_backups)} pre-existing config(s) before overwrite:")
            for b in written_backups:
                click.echo(f"    · {b.source.relative_to(paths.repo)} → {b.backup.relative_to(paths.repo)}")
            click.echo("  (restore with `dotagent restore-original`)")

    all_files = []
    rendered = 0
    for name in cfg.adapters_enabled:
        if name not in ADAPTER_REGISTRY:
            continue
        adapter = get_adapter(name)(paths)
        files = adapter.render(ctx)
        all_files.extend(files)
        if dry_run:
            continue
        adapter.write(files)
        rendered += 1

    if dry_run:
        diffs = diff_rendered(all_files)
        click.echo(format_diff(diffs))
        click.echo(f"\n[dry-run] {len(diffs)} file(s) would change; nothing written.")
        return

    click.echo(f"✓ rendered {rendered} adapters")

    # Project-tier derived files (service-registry, per-module HISTORY,
    # dashboard). Silently no-ops when project state isn't present.
    try:
        from ..render.derived import regenerate_derived_files
        derived = regenerate_derived_files(paths)
        if derived:
            click.echo(f"✓ regenerated {len(derived)} derived file(s)")
    except Exception as exc:  # noqa: BLE001
        click.echo(f"  ! derived-files regen failed: {exc}", err=True)

    if not no_hooks:
        install_git_hooks(paths)
        if cfg.get("adapters", "claude"):
            install_claude_hooks(paths)
