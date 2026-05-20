"""`dotagent git` — git layout management for layered projects.

Subcommands:

- `status`          — show drift between local and meta remote (best-effort)
- `push`            — commit + push meta-only content to the meta branch
- `pull`            — fetch + fast-forward
- `rebuild`         — regenerate `.agent/git.md` from `.agent/git.yaml`
- `init`            — wizard scaffolds `.agent/git.yaml`
- `clone-services` — clone every entry in repos[] as a sibling directory
- `verify`          — check pending changes against branch rules (PR #14)

Subprocess git invocations happen here. Pure data lives in `git_layout.py`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import click
import yaml

from ..git_layout import (
    GitLayout,
    MAIN_BRANCH_POLICY_LOCKED,
    STRATEGY_DEDICATED_REPO,
    load as load_layout,
    render_dashboard,
    verify_paths_against_rule,
)
from ..paths import Paths, find_repo_root


def _layout_or_die() -> tuple[GitLayout, Paths, Path]:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    layout = load_layout(paths.git_yaml)
    if layout is None:
        click.echo(
            f"no git.yaml at {paths.git_yaml.relative_to(repo)}. "
            "Run `dotagent git init` to scaffold one.",
            err=True,
        )
        sys.exit(1)
    return layout, paths, repo


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args, cwd=str(cwd) if cwd else None,
        check=False, capture_output=True, text=True,
    )


@click.group(name="git", help="Manage layered-project git layout (git.yaml).")
def git_group() -> None:
    pass


@git_group.command(name="rebuild", help="Regenerate .agent/git.md from .agent/git.yaml.")
def rebuild_cmd() -> None:
    layout, paths, repo = _layout_or_die()
    paths.git_md.write_text(render_dashboard(layout))
    click.echo(f"✓ wrote {paths.git_md.relative_to(repo)}")


@git_group.command(name="init", help="Scaffold a default git.yaml.")
@click.option("--remote", required=True, help="git remote URL for the meta repo.")
@click.option("--meta-branch", default="dotagent/meta", show_default=True,
              help="Active branch in the meta repo (must NOT be 'main').")
@click.option("--force", is_flag=True, help="Overwrite existing git.yaml.")
def init_cmd(remote: str, meta_branch: str, force: bool) -> None:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if paths.git_yaml.exists() and not force:
        click.echo(f"git.yaml already exists at {paths.git_yaml.relative_to(repo)}; use --force.", err=True)
        sys.exit(1)
    if meta_branch.lower() == "main":
        click.echo("meta-branch cannot be 'main'. Pick something like 'dotagent/meta'.", err=True)
        sys.exit(1)

    body = {
        "meta": {
            "strategy": STRATEGY_DEDICATED_REPO,
            "remote": remote,
            "branch": meta_branch,
            "main_branch_policy": MAIN_BRANCH_POLICY_LOCKED,
        },
        "repos": [
            {"id": "TBD", "path": "./TBD", "remote": "git@github.com:...",
             "default_branch": "main", "role": "TBD"},
        ],
        "branch_rules": [
            {
                "remote": remote,
                "branches": {
                    "main": {
                        "allowed_paths": [],
                        "forbidden_paths": ["**/*"],
                        "description": "Reserved. Never push to main.",
                    },
                    meta_branch: {
                        "allowed_paths": [".agent/", "docs/", "*.md"],
                        "forbidden_paths": [
                            "**/*.py", "**/*.ts", "**/*.tsx",
                            "**/Dockerfile", "**/*.sql",
                        ],
                        "description": "Meta content only — never code.",
                    },
                },
            },
        ],
    }
    paths.agent.mkdir(parents=True, exist_ok=True)
    paths.git_yaml.write_text(yaml.safe_dump(body, sort_keys=False))
    click.echo(f"✓ wrote {paths.git_yaml.relative_to(repo)}")
    click.echo("→ edit repos[] entries, then `dotagent git rebuild` to refresh git.md.")


@git_group.command(name="status", help="Show drift between local meta tree and the meta remote.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def status_cmd(fmt: str) -> None:
    layout, paths, repo = _layout_or_die()
    out: dict = {
        "meta_remote": layout.meta.remote,
        "meta_branch": layout.meta.branch,
        "dirty_files": [],
        "unpushed_commits": 0,
        "behind_remote": 0,
    }
    # local dirtiness
    result = _git(["status", "--porcelain"], cwd=repo)
    if result.returncode == 0:
        out["dirty_files"] = [
            line[3:] for line in result.stdout.splitlines() if line.strip()
        ]
    # commits ahead/behind
    rev = _git(
        ["rev-list", "--left-right", "--count", f"{layout.meta.branch}@{{u}}...HEAD"],
        cwd=repo,
    )
    if rev.returncode == 0 and rev.stdout.strip():
        try:
            behind, ahead = (int(x) for x in rev.stdout.split())
            out["behind_remote"] = behind
            out["unpushed_commits"] = ahead
        except ValueError:
            pass

    if fmt == "json":
        click.echo(json.dumps(out, indent=2))
        return
    click.echo(f"meta remote:     {out['meta_remote'] or '(unset)'}")
    click.echo(f"meta branch:     {out['meta_branch']}")
    click.echo(f"dirty files:     {len(out['dirty_files'])}")
    click.echo(f"unpushed local:  {out['unpushed_commits']}")
    click.echo(f"behind remote:   {out['behind_remote']}")
    if out["dirty_files"]:
        click.echo("\nuncommitted:")
        for f in out["dirty_files"]:
            click.echo(f"  {f}")


@git_group.command(name="push", help="git push the meta branch (current HEAD must match meta.branch).")
def push_cmd() -> None:
    layout, paths, repo = _layout_or_die()
    # Verify current branch matches meta.branch
    head = _git(["symbolic-ref", "--short", "HEAD"], cwd=repo)
    if head.returncode != 0 or head.stdout.strip() != layout.meta.branch:
        click.echo(
            f"current HEAD is {head.stdout.strip() or 'unknown'!r}; "
            f"checkout {layout.meta.branch!r} before pushing meta.",
            err=True,
        )
        sys.exit(1)
    result = _git(["push", "-u", "origin", layout.meta.branch], cwd=repo)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    sys.exit(result.returncode)


@git_group.command(name="pull", help="Fast-forward the meta branch from remote.")
def pull_cmd() -> None:
    layout, paths, repo = _layout_or_die()
    result = _git(["pull", "--ff-only", "origin", layout.meta.branch], cwd=repo)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    sys.exit(result.returncode)


@git_group.command(name="clone-services", help="Clone every repos[] entry as a sibling directory.")
@click.option("--dry-run", is_flag=True, help="Print git clone commands; don't run.")
def clone_services_cmd(dry_run: bool) -> None:
    layout, paths, repo = _layout_or_die()
    if not layout.repos:
        click.echo("no repos[] declared in git.yaml.", err=True)
        sys.exit(1)
    failures = 0
    for r in layout.repos:
        if r.id == "TBD" or not r.remote:
            click.echo(f"skipping placeholder entry {r.id!r}")
            continue
        target = (repo / r.path).resolve()
        cmd = ["git", "clone", r.remote, str(target)]
        if target.exists():
            click.echo(f"skip {r.id}: {target} already exists")
            continue
        if dry_run:
            click.echo("would run: " + " ".join(cmd))
            continue
        click.echo("→ " + " ".join(cmd))
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            failures += 1
            click.echo(f"  FAILED: {result.stderr.strip()}")
        else:
            click.echo(f"  cloned to {target}")
    sys.exit(0 if failures == 0 else 1)


@git_group.command(
    name="init-hooks",
    help="Install the local pre-push hook in this meta-repo clone.",
)
@click.option("--force", is_flag=True, help="Overwrite an existing hook.")
def init_hooks_cmd(force: bool) -> None:
    layout, paths, repo = _layout_or_die()
    if layout.meta.strategy != STRATEGY_DEDICATED_REPO:
        click.echo(
            f"init-hooks only supported for strategy=dedicated_repo "
            f"(current: {layout.meta.strategy}). Service repos do NOT need it.",
            err=True,
        )
        sys.exit(1)
    hook_target = repo / ".git" / "hooks" / "pre-push"
    if not hook_target.parent.exists():
        click.echo(f"not a git repository: no {hook_target.parent}", err=True)
        sys.exit(1)
    if hook_target.exists() and not force:
        click.echo(f"hook already exists at {hook_target}; use --force.", err=True)
        sys.exit(1)
    import importlib.resources as ir
    template_text = ir.files("dotagent.scaffolds.branch_protection").joinpath("pre-push.sh").read_text()
    hook_target.write_text(template_text)
    hook_target.chmod(0o755)
    click.echo(f"✓ installed {hook_target}")


@git_group.command(
    name="scaffold-protection",
    help="Write a GitHub Actions workflow that enforces branch rules server-side.",
)
@click.option("--force", is_flag=True, help="Overwrite an existing workflow.")
def scaffold_protection_cmd(force: bool) -> None:
    layout, paths, repo = _layout_or_die()
    workflow_dir = repo / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    target = workflow_dir / "branch-rules.yml"
    if target.exists() and not force:
        click.echo(f"workflow already exists at {target.relative_to(repo)}; use --force.", err=True)
        sys.exit(1)
    import importlib.resources as ir
    template_text = ir.files("dotagent.scaffolds.branch_protection").joinpath("branch-rules.yml").read_text()
    target.write_text(template_text)
    click.echo(f"✓ wrote {target.relative_to(repo)}")
    click.echo("→ enable branch protection in GitHub UI: require status check 'branch-rules' to pass.")


@git_group.command(name="verify", help="Check pending changes against branch rules.")
@click.option("--remote", default=None, help="Remote to look up rules for. Defaults to origin URL.")
@click.option("--branch", default=None,
              help="Branch to verify against. Defaults to current HEAD.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--paths", "extra_paths", multiple=True,
              help="Override: file paths to verify (instead of git diff).")
def verify_cmd(remote: str | None, branch: str | None, fmt: str,
               extra_paths: tuple[str, ...]) -> None:
    layout, paths_obj, repo = _layout_or_die()

    if remote is None:
        # Best-effort: use origin URL
        out = _git(["remote", "get-url", "origin"], cwd=repo)
        if out.returncode == 0:
            remote = out.stdout.strip()
    if branch is None:
        head = _git(["symbolic-ref", "--short", "HEAD"], cwd=repo)
        if head.returncode == 0:
            branch = head.stdout.strip()

    rule = layout.rules_for(remote or "", branch or "")
    if rule is None:
        result = {"status": "no-rule", "remote": remote, "branch": branch}
        if fmt == "json":
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"no branch rule for {remote}::{branch}")
        sys.exit(0)

    if extra_paths:
        files = list(extra_paths)
    else:
        # Verify staged + unstaged changes
        result = _git(["diff", "--name-only", "HEAD"], cwd=repo)
        files = [line for line in (result.stdout or "").splitlines() if line.strip()]

    ok, offenders = verify_paths_against_rule(files, rule)
    payload = {
        "status": "ok" if ok else "violation",
        "remote": remote, "branch": branch,
        "files_checked": files,
        "offenders": offenders,
        "rule": rule.to_dict(),
    }
    if fmt == "json":
        click.echo(json.dumps(payload, indent=2))
    else:
        if ok:
            click.echo(f"✓ {len(files)} file(s) match branch rules for {branch}.")
        else:
            click.echo(f"✗ {len(offenders)} file(s) violate rules for {branch}:")
            for f in offenders:
                click.echo(f"  - {f}")
            if rule.description:
                click.echo(f"  rule: {rule.description}")
    sys.exit(0 if ok else 1)
