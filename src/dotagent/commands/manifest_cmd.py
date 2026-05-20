"""`dotagent manifest` — render and preview the CLAUDE.md navigation manifest.

This is the explicit generator entrypoint for the v3 (post-0.5.0)
navigation-manifest renderer. It does NOT touch any on-disk adapter
files; for that, use `dotagent sync`. This command is for:

  • previewing what the manifest will look like before flipping
    `render.use_manifest: true` in `.agent/config.yaml`,
  • diffing the manifest against a fixture (e.g. for service-repo
    layered installs),
  • piping the manifest into a doc, screenshot, or PR comment.

Examples:

    dotagent manifest                          # auto-detect tier
    dotagent manifest --tier service-repo      # force a tier
    dotagent manifest --diff CLAUDE.md         # show what would change
    dotagent manifest --write CLAUDE.md.new    # write to a file
"""

from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

import click


_RENDERED_AT_RE = re.compile(r"rendered-at: [0-9T:.+\-Z]+")


def _strip_timestamp(text: str) -> str:
    """Strip the `rendered-at: ...` timestamp so diffs aren't noisy."""
    return _RENDERED_AT_RE.sub("rendered-at: <stripped>", text)

from ..canonical_structure import (
    TIER_PROJECT_ROOT,
    TIER_SERVICE_REPO,
    TIER_SINGLE_REPO,
    detect_tier,
)
from ..paths import Paths, find_repo_root
from ..render.manifest import render_manifest


_TIER_CHOICES = (TIER_PROJECT_ROOT, TIER_SERVICE_REPO, TIER_SINGLE_REPO)


@click.command(
    "manifest",
    help=(
        "Render the CLAUDE.md navigation manifest (v3 renderer). "
        "Doesn't touch on-disk adapter files — use `dotagent sync` for that."
    ),
)
@click.option(
    "--tier",
    type=click.Choice(_TIER_CHOICES),
    default=None,
    help="Force a specific tier. Default: auto-detect from filesystem signals.",
)
@click.option(
    "--diff",
    "diff_against",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Diff the rendered manifest against an existing file (e.g. CLAUDE.md).",
)
@click.option(
    "--write",
    "write_to",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the rendered manifest to a file instead of stdout.",
)
@click.option(
    "--repo",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Repo root to render for. Default: auto-discover via .agent/.",
)
def manifest(
    tier: str | None,
    diff_against: Path | None,
    write_to: Path | None,
    repo: Path | None,
) -> None:
    repo_root = repo if repo is not None else find_repo_root()
    paths = Paths(repo=repo_root)
    if not paths.agent.exists():
        raise click.ClickException(
            f"No .agent/ at {repo_root}. Run `dotagent init` first, or pass --repo."
        )

    resolved_tier = tier or detect_tier(repo_root)
    rendered = render_manifest(paths, tier=resolved_tier)

    # Diff mode — write nothing, just show what would change.
    if diff_against is not None:
        current = diff_against.read_text() if diff_against.exists() else ""
        # Strip the volatile rendered-at timestamp so diffs only show
        # semantic changes, not "the wall clock advanced 200ms".
        current_norm = _strip_timestamp(current)
        rendered_norm = _strip_timestamp(rendered)
        diff_lines = list(
            difflib.unified_diff(
                current_norm.splitlines(keepends=True),
                rendered_norm.splitlines(keepends=True),
                fromfile=str(diff_against),
                tofile=f"<rendered tier={resolved_tier}>",
                n=3,
            )
        )
        if not diff_lines:
            click.echo(
                f"# No diff — {diff_against} matches the rendered "
                f"{resolved_tier} manifest.",
                err=True,
            )
            return
        sys.stdout.writelines(diff_lines)
        return

    # Write mode — write file, log path.
    if write_to is not None:
        write_to.parent.mkdir(parents=True, exist_ok=True)
        write_to.write_text(rendered)
        click.echo(
            f"# Wrote {len(rendered)} bytes to {write_to} (tier={resolved_tier}).",
            err=True,
        )
        return

    # Default — pipe to stdout.
    click.echo(rendered, nl=False)
