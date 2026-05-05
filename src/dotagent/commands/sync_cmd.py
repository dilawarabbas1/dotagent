from __future__ import annotations

import click

from ..adapters import REGISTRY as ADAPTER_REGISTRY
from ..adapters import get as get_adapter
from ..adapters import read_source
from ..config import Config
from ..hooks import install_claude_hooks, install_git_hooks
from ..identity import resolve, upsert_developer
from ..paths import Paths, find_repo_root


@click.command(help="Regenerate every adapter file from .agent/ source. Idempotent.")
@click.option("--no-hooks", is_flag=True, help="Skip hook (re)install.")
def sync(no_hooks: bool) -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.config.exists():
        raise click.ClickException("No .agent/config.yaml found. Run `dotagent init` first.")
    cfg = Config.load(paths)
    source = read_source(paths)

    identity = resolve(repo)
    upsert_developer(paths, identity)

    rendered = 0
    for name in cfg.adapters_enabled:
        if name not in ADAPTER_REGISTRY:
            continue
        adapter = get_adapter(name)(paths)
        adapter.write(adapter.render(source))
        rendered += 1
    click.echo(f"✓ rendered {rendered} adapters")

    if not no_hooks:
        install_git_hooks(paths)
        if cfg.get("adapters", "claude"):
            install_claude_hooks(paths)
