"""CRON installer + GitHub Action template."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..paths import Paths


_CRON_TAG = "# dotagent-dream"


def _crontab_lines() -> list[str]:
    res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if res.returncode != 0:
        return []
    return res.stdout.splitlines()


def _write_crontab(lines: list[str]) -> None:
    res = subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"crontab write failed: {res.stderr.strip()}")


def install(paths: Paths, *, schedule: str = "0 2 * * *") -> str:
    """Install/refresh the dream cron entry. Returns the line that was written."""
    repo_path = str(paths.repo.resolve())
    line = (
        f"{schedule} cd {repo_path} && "
        f"command -v dotagent >/dev/null 2>&1 && dotagent dream run --quiet "
        f"{_CRON_TAG} {repo_path}"
    )
    existing = [ln for ln in _crontab_lines() if not (_CRON_TAG in ln and repo_path in ln)]
    existing.append(line)
    _write_crontab(existing)
    return line


def uninstall(paths: Paths) -> int:
    repo_path = str(paths.repo.resolve())
    existing = _crontab_lines()
    kept = [ln for ln in existing if not (_CRON_TAG in ln and repo_path in ln)]
    if len(kept) == len(existing):
        return 0
    _write_crontab(kept)
    return len(existing) - len(kept)


GITHUB_ACTION_TEMPLATE = """\
name: dotagent-auto-dream

on:
  schedule:
    - cron: '0 2 * * *'   # daily at 02:00 UTC
  workflow_dispatch: {}

permissions:
  contents: write
  pull-requests: write

jobs:
  dream:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dotagent
        run: pip install dotagent
      - name: Run dream
        run: |
          dotagent reindex-events
          dotagent dream run --commit-candidates
      - name: Open PR with candidates
        uses: peter-evans/create-pull-request@v6
        with:
          branch: dotagent/dream-${{ github.run_id }}
          title: 'dotagent: auto-dream candidates for review'
          body: |
            Auto-Dream produced new candidates. Review each, then graduate
            with `dotagent dream graduate <id> --rationale "..."` or
            reject with `dotagent dream reject <id> --rationale "..."`.
          commit-message: 'chore(dotagent): auto-dream candidates'
"""


def write_github_action(paths: Paths) -> Path:
    target = paths.repo / ".github" / "workflows" / "dotagent-dream.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(GITHUB_ACTION_TEMPLATE)
    return target
