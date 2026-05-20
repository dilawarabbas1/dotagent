"""`dotagent project brief` — manage the project_brief.md file.

Subcommands:

- `init`   — interactive Q&A produces a populated stub
- `upload` — parse an existing markdown brief into the canonical location
- `show`   — print parsed brief as text or JSON
- `edit`   — open in $EDITOR
- `check`  — audit brief health (sections, IDs, last-reviewed age)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from ..paths import Paths, find_repo_root
from ..project.brief import (
    BRIEF_STUB,
    load,
    parse,
    render_stub,
    write_stub,
)


@click.group(name="brief", help="Manage project_brief.md (business intent).")
def brief_group() -> None:
    pass


def _brief_path(repo: Path) -> Path:
    return repo / ".agent" / "project_brief.md"


@brief_group.command(name="init", help="Create project_brief.md from interactive Q&A (or stub).")
@click.option("--name", default="", help="Project name.")
@click.option("--owner", default="", help="Owner email/name.")
@click.option("--vision", default="", help="One-sentence vision.")
@click.option("--non-interactive", is_flag=True, help="Skip prompts; write stub with placeholders.")
@click.option("--force", is_flag=True, help="Overwrite an existing brief.")
def init_cmd(name: str, owner: str, vision: str, non_interactive: bool, force: bool) -> None:
    repo = find_repo_root()
    target = _brief_path(repo)

    if target.exists() and not force:
        click.echo(f"brief already exists at {target.relative_to(repo)}; use --force to overwrite", err=True)
        sys.exit(1)

    if not non_interactive:
        if not name:
            name = click.prompt("project name", default="<your project name>")
        if not owner:
            owner = click.prompt("owner (email/handle)", default="<name@domain>")
        if not vision:
            vision = click.prompt(
                "vision (one sentence)",
                default="<What this product becomes if it wins.>",
                show_default=False,
            )

    if target.exists() and force:
        target.unlink()
    write_stub(target, name=name, owner=owner, vision=vision)
    click.echo(f"✓ wrote {target.relative_to(repo)}")
    click.echo("edit the file and run `dotagent project brief check` to audit.")


@brief_group.command(name="upload", help="Replace project_brief.md with content from PATH.")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--force", is_flag=True, help="Overwrite without prompting.")
def upload_cmd(path: Path, force: bool) -> None:
    repo = find_repo_root()
    target = _brief_path(repo)

    if path.suffix.lower() not in (".md", ".markdown", ".txt"):
        click.echo("v1 supports .md / .txt only; PDF/DOCX import deferred.", err=True)
        sys.exit(1)

    if target.exists() and not force:
        click.confirm(f"overwrite {target.relative_to(repo)}?", abort=True)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(path.read_text())
    click.echo(f"✓ wrote {target.relative_to(repo)} from {path}")

    # Parse and report what was found
    b = parse(target.read_text())
    click.echo(f"  parsed: {len(b.objectives)} OBJ · {len(b.features)} FEAT · "
               f"{len(b.hard_rules)} RULE · {len(b.integrations)} integration(s)")


@brief_group.command(name="show", help="Print the brief.")
@click.option("--format", "fmt", type=click.Choice(["text", "json", "raw"]), default="text")
def show_cmd(fmt: str) -> None:
    repo = find_repo_root()
    target = _brief_path(repo)
    if not target.exists():
        click.echo(f"no brief at {target.relative_to(repo)}. Run `dotagent project brief init`.", err=True)
        sys.exit(1)

    if fmt == "raw":
        click.echo(target.read_text())
        return

    b = load(target)
    if b is None:
        click.echo("could not parse brief.", err=True)
        sys.exit(1)

    if fmt == "json":
        click.echo(json.dumps(b.to_dict(), indent=2))
        return

    click.echo(f"project:        {b.name or '(unset)'}")
    click.echo(f"brief version:  {b.brief_version}")
    click.echo(f"last reviewed:  {b.last_reviewed or '(unset)'}")
    click.echo(f"owner:          {b.owner or '(unset)'}")
    click.echo(f"stage:          {b.stage or '(unset)'}")
    click.echo("")
    click.echo(f"vision:         {b.vision or '(unset)'}")
    click.echo("")
    click.echo(f"objectives ({len(b.objectives)}):")
    for o in b.objectives:
        click.echo(f"  · {o.id}: {o.text}")
    click.echo(f"\nfeatures ({len(b.features)}):")
    for f in b.features:
        serves = ", ".join(f.serves) if f.serves else "(none)"
        click.echo(f"  · {f.id} ({f.name}) → serves {serves}")
        if f.expected_outcome:
            click.echo(f"      outcome: {f.expected_outcome}")
    click.echo(f"\nhard rules ({len(b.hard_rules)}):")
    for r in b.hard_rules:
        click.echo(f"  · {r.id}: {r.name}")
    click.echo(f"\nglossary ({len(b.glossary)} terms)")
    click.echo(f"integrations ({len(b.integrations)})")


@brief_group.command(name="edit", help="Open project_brief.md in $EDITOR.")
def edit_cmd() -> None:
    repo = find_repo_root()
    target = _brief_path(repo)
    if not target.exists():
        click.echo(f"no brief at {target.relative_to(repo)}. Run `dotagent project brief init`.", err=True)
        sys.exit(1)

    editor = os.environ.get("EDITOR") or shutil.which("vi") or shutil.which("nano")
    if not editor:
        click.echo("set $EDITOR (e.g., vim, nano).", err=True)
        sys.exit(1)
    subprocess.call([editor, str(target)])


@brief_group.command(name="check", help="Audit brief health.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--max-age-days", type=int, default=180,
              help="Warn if last-reviewed is older than this. Default: 180.")
def check_cmd(fmt: str, max_age_days: int) -> None:
    repo = find_repo_root()
    target = _brief_path(repo)
    findings: list[dict] = []

    if not target.exists():
        finding = {"severity": "fail", "code": "brief-missing",
                   "message": f"no brief at {target.relative_to(repo)}",
                   "fix": "run `dotagent project brief init`"}
        if fmt == "json":
            click.echo(json.dumps({"findings": [finding], "ok": False}, indent=2))
        else:
            click.echo(f"  [✗] {finding['message']}")
            click.echo(f"        fix: {finding['fix']}")
        sys.exit(1)

    text = target.read_text()
    b = parse(text)

    # Required H2 anchors check (minimal — full structural audit is PR #6)
    required_sections = (
        "Vision (one sentence)",
        "Business objectives",
        "Features",
        "Hard rules",
    )
    for section in required_sections:
        if f"## {section}" not in text:
            findings.append({
                "severity": "fail",
                "code": "missing-section",
                "message": f"required H2 section absent: '{section}'",
                "fix": f"add a '## {section}' section",
            })

    # IDs sanity
    if not b.objectives:
        findings.append({
            "severity": "warn", "code": "no-objectives",
            "message": "no OBJ-NN ids parsed",
            "fix": "add at least one **OBJ-NN**: ... bullet under Business objectives",
        })
    if not b.features:
        findings.append({
            "severity": "warn", "code": "no-features",
            "message": "no FEAT-NN ids parsed",
            "fix": "add at least one ### FEAT-NN heading under Features",
        })

    # Duplicate IDs
    for label, ids in (("OBJ", b.objective_ids), ("FEAT", b.feature_ids), ("RULE", b.rule_ids)):
        seen: set[str] = set()
        for i in ids:
            if i in seen:
                findings.append({
                    "severity": "fail", "code": "duplicate-id",
                    "message": f"duplicate id {i!r}",
                    "fix": "rename to a unique id",
                })
            seen.add(i)

    # FEAT must serve at least one OBJ
    for f in b.features:
        if not f.serves:
            findings.append({
                "severity": "warn", "code": "feat-no-serves",
                "message": f"{f.id} has no Serves: declaration",
                "fix": f"add `**Serves:** OBJ-NN` under {f.id}",
            })
        for obj_id in f.serves:
            if obj_id not in b.objective_ids:
                findings.append({
                    "severity": "fail", "code": "dangling-obj-ref",
                    "message": f"{f.id} serves {obj_id} but that OBJ is not defined",
                    "fix": f"either add {obj_id} to Business objectives or remove the reference",
                })

    # Brief staleness
    if b.last_reviewed:
        try:
            reviewed = datetime.fromisoformat(b.last_reviewed)
            if reviewed.tzinfo is None:
                reviewed = reviewed.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - reviewed
            if age > timedelta(days=max_age_days):
                findings.append({
                    "severity": "warn", "code": "brief-stale",
                    "message": f"last reviewed {age.days} days ago (threshold {max_age_days})",
                    "fix": "review the brief and update **Last reviewed** + **Brief version**",
                })
        except ValueError:
            findings.append({
                "severity": "warn", "code": "bad-date",
                "message": f"could not parse Last reviewed: {b.last_reviewed!r}",
                "fix": "use ISO 8601 date (YYYY-MM-DD)",
            })

    ok = not any(f["severity"] == "fail" for f in findings)
    if fmt == "json":
        click.echo(json.dumps({"findings": findings, "ok": ok}, indent=2))
        sys.exit(0 if ok else 1)

    if not findings:
        click.echo("✓ brief is clean.")
        return

    glyph = {"fail": "✗", "warn": "!", "info": "i"}
    for f in findings:
        click.echo(f"  [{glyph.get(f['severity'], '?')}] {f['message']}")
        if f.get("fix"):
            click.echo(f"        fix: {f['fix']}")
    sys.exit(0 if ok else 1)
