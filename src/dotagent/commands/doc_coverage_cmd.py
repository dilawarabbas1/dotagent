"""`dotagent doc-coverage` — required-doc checklist for a changed-file set.

Reads the hand-maintained `docs/feature_master.md` + `docs/feature_master/`
mapping (no writes — that's authored by humans + Claude) and the
join-key heuristics from docs/HAND_MAINTAINED_DOCS_CONVENTION.md, then
returns the docs the caller should consider updating.

Typical caller: the Coda orchestrator's doc-maintenance gate (Prompt 2
field #4). Also useful standalone for `dotagent doc-coverage --files
$(git diff --cached --name-only)` on the command line.

This command NEVER writes to any file. Read-only by design.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ..coverage import (
    SEVERITY_CHECK,
    SEVERITY_HARD,
    SEVERITY_SUGGESTED,
    doc_coverage,
)
from ..paths import Paths, find_repo_root


_SEVERITY_GLYPH = {
    SEVERITY_HARD: "🔴 HARD",
    SEVERITY_SUGGESTED: "🟡 SUGGESTED",
    SEVERITY_CHECK: "🟢 CHECK",
}


@click.command(
    "doc-coverage",
    help=(
        "Return the required-doc checklist for a changed-file set. Reads the "
        "hand-maintained FM-### structure; writes nothing."
    ),
)
@click.option(
    "--files", "files_arg", required=True,
    help=(
        "Repo-relative paths, comma- or newline-separated. "
        "Example: `--files src/auth.py,src/db/users.py` or "
        "`--files \"$(git diff --cached --name-only)\"`."
    ),
)
@click.option(
    "--format", "fmt",
    type=click.Choice(["json", "text", "markdown"]),
    default="json",
    help="Output format. Default: json (for orchestrator consumption).",
)
@click.option(
    "--commit-msg", default="",
    help=(
        "Optional commit message. Used to detect bug-fix intent (DA-BUG-* "
        "tokens) and add the matching bug-registry shard to the checklist."
    ),
)
@click.option(
    "--repo",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Repo root. Default: auto-discover via .agent/.",
)
@click.option(
    "--severity",
    type=click.Choice(["all", "hard", "suggested+", "hard+suggested"]),
    default="all",
    help=(
        "Filter docs by severity. `hard` = only explicit FM-### `files:` "
        "matches. `suggested+` = HARD + SUGGESTED (skip CHECK noise). "
        "`hard+suggested` = same as `suggested+`."
    ),
)
def doc_coverage_cmd(
    files_arg: str,
    fmt: str,
    commit_msg: str,
    repo: Path | None,
    severity: str,
) -> None:
    repo_root = repo if repo is not None else _safe_find_repo_root()
    paths = Paths(repo=repo_root)
    if not paths.agent.exists():
        raise click.ClickException(
            f"No .agent/ at {repo_root}. Run `dotagent init` or pass --repo."
        )

    files = _parse_files(files_arg)
    if not files:
        raise click.ClickException(
            "No files supplied. Pass repo-relative paths via --files."
        )

    report = doc_coverage(repo_root, files, commit_msg=commit_msg)

    if severity != "all":
        report = _filter_by_severity(report, severity)

    if fmt == "json":
        click.echo(json.dumps(report.to_dict(), indent=2))
    elif fmt == "markdown":
        click.echo(_render_markdown(report))
    else:
        click.echo(_render_text(report))


def _safe_find_repo_root() -> Path:
    try:
        return find_repo_root()
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(
            f"Could not auto-discover repo root: {exc}. Pass --repo explicitly."
        )


def _parse_files(arg: str) -> list[str]:
    """Split a comma- or newline-separated --files value, skip empties."""
    out: list[str] = []
    for chunk in arg.replace(",", "\n").splitlines():
        c = chunk.strip()
        if c and c not in out:
            out.append(c)
    return out


def _filter_by_severity(report, severity: str):
    """Apply a severity filter in-place. Removes docs (not files)."""
    keep_check = severity == "all"
    keep_suggested = severity in ("all", "suggested+", "hard+suggested")
    keep_hard = True  # HARD always kept
    for f in report.files:
        f.required_docs = [
            d for d in f.required_docs
            if (d.severity == SEVERITY_HARD and keep_hard)
            or (d.severity == SEVERITY_SUGGESTED and keep_suggested)
            or (d.severity == SEVERITY_CHECK and keep_check)
        ]
    return report


def _render_text(report) -> str:
    """Plain-text checklist — for ad-hoc CLI use."""
    lines: list[str] = []
    if report.warnings:
        lines.append("⚠  Warnings:")
        for w in report.warnings:
            lines.append(f"   · {w}")
        lines.append("")
    for f in report.files:
        lines.append(f"=== {f.path}")
        if f.fm_ids:
            lines.append(f"    FM-### : {', '.join(f.fm_ids)}")
        else:
            lines.append("    FM-### : (unmapped — no FM-### claims this file)")
        if not f.required_docs:
            lines.append("    no required docs (filter excluded everything)")
        for d in f.required_docs:
            label = _SEVERITY_GLYPH.get(d.severity, d.severity)
            lines.append(f"    {label}  {d.path}")
            lines.append(f"        → {d.reason}")
        lines.append("")
    if report.unmapped_files:
        lines.append(
            f"⚠  {len(report.unmapped_files)} unmapped file(s) "
            f"(no FM-### claims them): {', '.join(report.unmapped_files)}"
        )
        lines.append(
            "   Either add them to an existing `FM-###-<slug>.md` `files:` "
            "section, or declare a new FM-### for the feature they belong to."
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_markdown(report) -> str:
    """Markdown — pasteable into Prompt 2 field #4 or a PR comment."""
    lines: list[str] = ["# Doc-coverage checklist", ""]
    if report.warnings:
        lines.append("> **Warnings**")
        for w in report.warnings:
            lines.append(f"> - {w}")
        lines.append("")
    for f in report.files:
        lines.append(f"## `{f.path}`")
        if f.fm_ids:
            lines.append(f"**FM-###:** {', '.join(f'`{i}`' for i in f.fm_ids)}")
        else:
            lines.append("**FM-###:** _(unmapped — no FM-### claims this file)_")
        lines.append("")
        if not f.required_docs:
            lines.append("_no required docs (filter excluded everything)_")
            lines.append("")
            continue
        for d in f.required_docs:
            label = _SEVERITY_GLYPH.get(d.severity, d.severity)
            lines.append(f"- {label} — `{d.path}`")
            lines.append(f"  - {d.reason}")
        lines.append("")
    if report.unmapped_files:
        lines.append("## Unmapped files")
        lines.append("")
        lines.append(
            "These changed files are not claimed by any `FM-###-<slug>.md` "
            "`files:` section. Either add them to an existing feature, or "
            "declare a new FM-###."
        )
        lines.append("")
        for u in report.unmapped_files:
            lines.append(f"- `{u}`")
    return "\n".join(lines).rstrip() + "\n"
