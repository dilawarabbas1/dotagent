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

    # Pre-step: refresh dotgraph's emitted docs. Best-effort, fail-soft.
    #
    # v0.5.4 — two paths:
    # 1. Workspace path (decision A, option b): when `dotgraph-workspace.yml`
    #    exists at repo root, call `dotgraph workspace index` then
    #    `dotgraph workspace emit-docs --json`. dotgraph handles the per-repo
    #    loop on its side; one subprocess call, aggregate JSON back.
    # 2. Single-repo path: emit into `docs/codegraph/` of THIS repo, then
    #    apply the suffix-split layout.
    #
    # Other v0.5.4 behaviours active on both paths:
    # - pre-seed `.gitignore` with `.dotgraph/` (idempotent)
    # - pass `--skip-empty` so empty surfaces don't produce stub docs
    # - apply suffix-split (`*.generated.md`) layout on each affected repo
    # Config knobs (`.agent/config.yaml`):
    #   dotagent.dotgraph.emit_docs.skip_empty:    bool  (default true)
    #   dotagent.dotgraph.stale_threshold_hours:   int   (default 168)
    if not skip_dotgraph:
        _run_dotgraph_emit_pre_step(paths, cfg)

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


def _run_dotgraph_emit_pre_step(paths, cfg) -> None:
    """v0.5.4 — dotgraph emit-docs pre-step with workspace + single-repo paths.

    Three sub-cases:
      A. `dotgraph-workspace.yml` present → workspace flow (multi-repo
         emit driven by `dotgraph workspace emit-docs --json`). Apply
         the suffix-split layout in each child repo.
      B. No workspace, .dotgraph/graph.db present → single-repo flow.
      C. No workspace, no db → no-op (sync proceeds as before).

    Plus: in case (B/C), when the meta repo has <20 indexable files,
    log a one-line hint suggesting the operator add a workspace.yml.
    """
    from ..dotgraph_probe import (
        CODEGRAPH_SUBDIR,
        apply_codegraph_layout as _dg_apply_layout,
        count_indexable_files as _dg_count_files,
        emit_docs as _dg_emit_docs,
        ensure_gitignored as _dg_ensure_gitignored,
        workspace_emit_docs as _dg_ws_emit,
        workspace_index as _dg_ws_index,
        workspace_present as _dg_ws_present,
    )

    repo = paths.repo
    dg_cfg = ((cfg.raw.get("dotagent") or {}).get("dotgraph") or {}).get("emit_docs") or {}
    _ = bool(dg_cfg.get("skip_empty", True))   # workspace emit-docs uses --json; skip_empty
                                                # is implicit in dotgraph 0.1.11+

    if _dg_ws_present(repo):
        # Workspace path (decision A, option b)
        gi_msg = _dg_ensure_gitignored(repo)
        if gi_msg:
            click.echo(f"· {gi_msg}")
        ok_idx, idx_msg = _dg_ws_index(repo)
        if ok_idx:
            click.echo(f"· {idx_msg}")
        else:
            click.echo(f"  ! {idx_msg} (continuing)", err=True)

        ok, msg, payload = _dg_ws_emit(repo, out_subdir=CODEGRAPH_SUBDIR)
        if not ok:
            click.echo(f"  ! {msg} (continuing)", err=True)
            return
        click.echo(f"· {msg}")

        # Apply suffix-split in each repo that successfully emitted.
        # `workspace emit-docs` returns each repo's absolute path so we
        # can locate the codegraph dir under it.
        for result in payload.get("results", []):
            if result.get("status") != "ok":
                if result.get("status") == "error" and result.get("message"):
                    click.echo(f"  ! repo '{result.get('repo','?')}': {result['message']}", err=True)
                continue
            repo_path = result.get("path")
            if not repo_path:
                continue
            from pathlib import Path as _P
            try:
                renamed, patched = _dg_apply_layout(_P(repo_path))
                if patched:
                    click.echo(
                        f"·   {result['repo']}: patched {len(patched)} hand-maintained doc(s)"
                    )
            except Exception as exc:  # noqa: BLE001
                click.echo(f"  ! layout apply in '{result.get('repo','?')}' failed: {exc}", err=True)
        return

    # No workspace.yml — single-repo path
    if not (repo / ".dotgraph" / "graph.db").exists():
        # Helpful nudge: meta-shaped projects often want a workspace.yml
        try:
            n = _dg_count_files(repo)
        except Exception:  # noqa: BLE001
            n = 0
        if 0 < n < 20:
            click.echo(
                f"  ! meta repo has only {n} indexable file(s). "
                f"Consider adding a `dotgraph-workspace.yml` if your "
                f"real code lives in sibling repos.",
                err=True,
            )
        return

    gi_msg = _dg_ensure_gitignored(repo)
    if gi_msg:
        click.echo(f"· {gi_msg}")

    skip_empty = bool(dg_cfg.get("skip_empty", True))
    out_dir = repo / CODEGRAPH_SUBDIR
    ok, msg, _payload = _dg_emit_docs(
        repo, skip_empty=skip_empty, out_dir=out_dir,
    )
    if ok:
        click.echo(f"· {msg}")
        renamed, patched = _dg_apply_layout(repo)
        if patched:
            click.echo(
                f"· patched {len(patched)} hand-maintained doc(s) with "
                f"codegraph reference: {', '.join(patched)}"
            )
        # Single-repo "<20 files" hint when nothing was actually emitted
        if not renamed and not patched:
            try:
                n = _dg_count_files(repo)
            except Exception:  # noqa: BLE001
                n = 0
            if 0 < n < 20:
                click.echo(
                    f"  ! meta repo has only {n} indexable file(s). "
                    f"Consider adding a `dotgraph-workspace.yml` if your "
                    f"real code lives in sibling repos.",
                    err=True,
                )
    else:
        click.echo(f"  ! {msg} (continuing)", err=True)
