from __future__ import annotations

import json

import click

from ..adapters import REGISTRY as ADAPTER_REGISTRY
from ..adapters import get as get_adapter
from ..adapters import read_source
from ..config import Config, merge_defaults
from ..discovery import discover
from ..hooks import install_claude_hooks, install_git_hooks
from ..identity import resolve, save_user_identity, upsert_developer
from ..llm import LLM
from ..paths import Paths, find_repo_root
from ..scaffold import scaffold_agent_dir
from ..util import dump_yaml


def _draft_with_llm(llm: LLM, disco) -> dict:
    """Use the LLM to draft initial style/rules/architecture/patterns/preferences."""
    if not llm.available:
        return {}
    sys = (
        "You are drafting a fresh `.agent/*.md` set for a software project. "
        "Output STRICT JSON with keys: style, rules, architecture, patterns, preferences. "
        "Each value is markdown. No prose outside the JSON."
    )
    facts = {
        "languages": disco.languages,
        "frameworks": disco.frameworks,
        "test_runners": disco.test_runners,
        "linters": disco.linters,
        "package_managers": disco.package_managers,
        "is_monorepo": disco.is_monorepo,
        "has_ci": disco.has_ci,
        "has_docker": disco.has_docker,
        "git_authors": list((disco.git_log_summary or {}).get("authors", {}).keys())[:5],
        "git_total_commits": (disco.git_log_summary or {}).get("total"),
        "readme_excerpt": (disco.readme_excerpt or "")[:1500],
    }
    user = (
        "Project facts:\n```json\n"
        + json.dumps(facts, indent=2)
        + "\n```\n\nDraft the five files. Be concrete. If you don't know, say `_(unknown — please fill in)_`."
    )
    try:
        raw = llm.complete(sys, user, max_tokens=4000)
        return json.loads(raw)
    except Exception as e:  # pragma: no cover
        click.echo(f"  [llm] draft failed ({e}); using scaffold defaults", err=True)
        return {}


@click.command(help="One-shot setup. Scaffold .agent/, draft memory, generate adapters.")
@click.option("--interactive", is_flag=True, help="Run the question-driven flow.")
@click.option("--no-llm", is_flag=True, help="Skip LLM drafting; use scaffold defaults.")
@click.option("--no-hooks", is_flag=True, help="Skip installing git hooks.")
@click.option("--dry-run", is_flag=True, help="Run all phases but write nothing.")
def init(interactive: bool, no_llm: bool, no_hooks: bool, dry_run: bool) -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    click.echo(f"dotagent init → {repo}")

    click.echo("· phase 1: discovery")
    disco = discover(repo)
    click.echo(f"  languages: {', '.join(disco.languages) or '(none)'}")
    click.echo(f"  frameworks: {', '.join(disco.frameworks) or '(none)'}")
    click.echo(f"  detected ai-tool configs: {', '.join(disco.existing_ai_configs) or '(none)'}")
    if disco.has_claude_code_optimization:
        click.echo("  · detected Claude-Code-Optimization assets — will import them in a later phase")

    click.echo("· phase 2: drafting .agent/*.md")
    drafts: dict = {}
    if not no_llm:
        llm = LLM()
        if not llm.available:
            click.echo("  [llm] ANTHROPIC_API_KEY not set; using scaffold defaults")
        else:
            drafts = _draft_with_llm(llm, disco)

    click.echo("· phase 3: identity")
    identity = resolve(repo)
    click.echo(f"  actor: {identity.id} <{', '.join(identity.emails) or 'no email'}>")

    if dry_run:
        click.echo("· dry-run: would scaffold .agent/, write adapters, install hooks. Stopping.")
        return

    click.echo("· phase 4: scaffolding .agent/")
    written = scaffold_agent_dir(paths, overwrite=False)
    click.echo(f"  scaffolded {len(written)} files")

    for key in ("style", "rules", "architecture", "patterns", "preferences"):
        if drafts.get(key):
            target = getattr(paths, key)
            target.write_text(drafts[key].rstrip() + "\n")

    save_user_identity(identity)
    upsert_developer(paths, identity)

    cfg_data = merge_defaults({"project": {"name": repo.name}})
    if disco.existing_ai_configs:
        for k in cfg_data["adapters"]:
            cfg_data["adapters"][k] = k in disco.existing_ai_configs
        for k in ("claude", "cursor", "copilot"):
            cfg_data["adapters"][k] = True
    dump_yaml(paths.config, cfg_data)

    click.echo("· phase 5: rendering adapters")
    cfg = Config(raw=cfg_data, path=paths.config)
    source = read_source(paths)
    rendered_count = 0
    for name in cfg.adapters_enabled:
        if name not in ADAPTER_REGISTRY:
            continue
        adapter = get_adapter(name)(paths)
        files = adapter.render(source)
        adapter.write(files)
        rendered_count += len(files)
    click.echo(f"  wrote {rendered_count} adapter files")

    if not no_hooks:
        click.echo("· phase 6: installing hooks")
        ghs = install_git_hooks(paths)
        chs = install_claude_hooks(paths) if cfg.get("adapters", "claude") else []
        click.echo(f"  installed {len(ghs)} git + {len(chs)} claude hooks")

    click.echo("\n✓ dotagent ready. Edit .agent/*.md, then run `dotagent sync`.")
