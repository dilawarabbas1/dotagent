from __future__ import annotations

import json

import click

from ..config import Config
from ..context import build as build_context
from ..identity import resolve
from ..paths import Paths, find_repo_root
from ..skills import get_skill, list_skills, run_pipeline, run_skill


def _paths() -> tuple[Paths, Config]:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init` first.")
    return paths, Config.load(paths)


@click.group(name="skill", help="Skills runtime: observer / research / plan / code / review.")
def skill_group() -> None:
    pass


@skill_group.command(name="list", help="List available skills.")
def cmd_list() -> None:
    paths, _ = _paths()
    skills = list_skills(paths)
    if not skills:
        click.echo("(no skills found in .agent/skills/)")
        return
    for s in skills:
        click.echo(f"  · {s.name:14s} {s.description or '(no description)'}")


@skill_group.command(name="show", help="Print a skill's resolved prompts (no LLM call).")
@click.argument("name")
@click.option("--task", default="")
def cmd_show(name: str, task: str) -> None:
    paths, cfg = _paths()
    identity = resolve(paths.repo)
    ctx = build_context(paths, actor=identity.id, config=cfg)
    res = run_skill(paths, ctx, name, task=task, dry_run=True)
    click.echo("=== system ===")
    click.echo(res["system"])
    click.echo("\n=== user ===")
    click.echo(res["user"])


@skill_group.command(name="run", help="Run a skill (calls LLM if ANTHROPIC_API_KEY is set).")
@click.argument("name")
@click.option("--task", default="")
@click.option("--dry-run", is_flag=True)
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def cmd_run(name: str, task: str, dry_run: bool, fmt: str) -> None:
    paths, cfg = _paths()
    identity = resolve(paths.repo)
    ctx = build_context(paths, actor=identity.id, config=cfg)
    res = run_skill(paths, ctx, name, task=task, dry_run=dry_run)
    if fmt == "json":
        click.echo(json.dumps({k: v for k, v in res.items() if k != "system"}, indent=2))
        return
    if res.get("note"):
        click.echo(f"[dry-run] {res['note']}")
        click.echo(res["user"])
        return
    if res.get("error"):
        click.echo(f"[error] {res['error']}", err=True)
        return
    click.echo(res.get("output") or "(no output)")


@skill_group.command(name="pipeline", help="Chain skills (each output becomes the next's prior_output).")
@click.argument("names", nargs=-1, required=True)
@click.option("--task", default="")
@click.option("--dry-run", is_flag=True)
def cmd_pipeline(names: tuple[str, ...], task: str, dry_run: bool) -> None:
    paths, cfg = _paths()
    identity = resolve(paths.repo)
    ctx = build_context(paths, actor=identity.id, config=cfg)
    results = run_pipeline(paths, ctx, list(names), task=task, dry_run=dry_run)
    for r in results:
        click.echo(f"\n--- {r['skill']} ---")
        if r.get("note"):
            click.echo(f"[note] {r['note']}")
        click.echo(r.get("output") or r.get("user") or "")
