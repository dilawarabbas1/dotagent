from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from importlib.metadata import PackageNotFoundError, version

import click

_REPO = "dilawarabbas1/dotagent"
_GIT_URL = f"git+https://github.com/{_REPO}"


def _installed_version() -> str:
    try:
        return version("dotagent")
    except PackageNotFoundError:
        return "unknown"


def _detect_install_method() -> str:
    """Return 'pipx', 'pip', or 'editable'."""
    exe = sys.executable
    if "/pipx/venvs/dotagent/" in exe or "\\pipx\\venvs\\dotagent\\" in exe:
        return "pipx"
    try:
        dist_info = subprocess.run(
            [sys.executable, "-m", "pip", "show", "dotagent"],
            capture_output=True, text=True, check=False,
        )
        if "Editable project location" in dist_info.stdout:
            return "editable"
    except FileNotFoundError:
        pass
    return "pip"


def _latest_main_sha() -> str | None:
    url = f"https://api.github.com/repos/{_REPO}/commits/main"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
        return data.get("sha", "")[:7] or None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


@click.command(help="Upgrade dotagent itself to the latest version from GitHub.")
@click.option("--check", is_flag=True, help="Print installed + latest commit; no upgrade.")
@click.option("--ref", default="main", show_default=True, help="Branch, tag, or SHA to install.")
@click.option("--dry-run", is_flag=True, help="Print the command without running it.")
def update(check: bool, ref: str, dry_run: bool) -> None:
    method = _detect_install_method()
    current = _installed_version()
    click.echo(f"installed:  dotagent {current}  ({method})")

    latest = _latest_main_sha()
    if latest:
        click.echo(f"latest:     {_REPO}@{ref} (HEAD {latest})")
    else:
        click.echo(f"latest:     {_REPO}@{ref} (could not reach github)")

    if check:
        return

    if method == "editable":
        click.echo("editable install detected — run `git pull` in the source tree instead.")
        sys.exit(1)

    target = f"{_GIT_URL}@{ref}" if ref != "main" else _GIT_URL
    if method == "pipx":
        if not shutil.which("pipx"):
            click.echo("pipx not on PATH; install pipx or use pip.", err=True)
            sys.exit(1)
        cmd = ["pipx", "install", "--force", target]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", target]

    click.echo(f"running:    {' '.join(cmd)}")
    if dry_run:
        return

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        sys.exit(result.returncode)

    new = _installed_version()
    click.echo(f"upgraded:   dotagent {current} → {new}")
