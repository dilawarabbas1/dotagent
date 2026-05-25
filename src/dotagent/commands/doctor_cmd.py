from __future__ import annotations

import json
import sys

import click

from ..doctor import run_checks
from ..dotgraph_probe import probe as _dotgraph_probe
from ..paths import find_repo_root


_GLYPH = {"ok": "✓", "warn": "!", "fail": "✗", "info": "i"}


@click.command(help="Self-check for common misconfigurations.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def doctor(fmt: str) -> None:
    diagnoses = run_checks()
    dg_info = _safe_dotgraph_probe()

    if fmt == "json":
        payload = {
            "diagnoses": [
                {"name": d.name, "status": d.status, "message": d.message, "fix": d.fix}
                for d in diagnoses
            ],
            "dotgraph": dg_info.to_dict() if dg_info else None,
        }
        click.echo(json.dumps(payload, indent=2))
    else:
        for d in diagnoses:
            glyph = _GLYPH.get(d.status, "?")
            click.echo(f"  [{glyph}] {d.name:22s} {d.message}")
            if d.fix:
                click.echo(f"        fix: {d.fix}")
        if dg_info is not None:
            click.echo(f"  [{_dg_glyph(dg_info)}] {'dotgraph':22s} {_dg_text_line(dg_info)}")
    if any(d.status == "fail" for d in diagnoses):
        sys.exit(1)


def _safe_dotgraph_probe():
    """Best-effort probe. Returns None when there's no repo to probe."""
    try:
        repo = find_repo_root()
    except Exception:  # noqa: BLE001 — find_repo_root raises ClickException
        return None
    try:
        return _dotgraph_probe(repo)
    except Exception:  # noqa: BLE001 — defense in depth; probe should never raise
        return None


def _dg_glyph(info) -> str:
    if not info.installed:
        return _GLYPH["info"]
    if info.error or info.stale:
        return _GLYPH["warn"]
    return _GLYPH["ok"]


def _dg_text_line(info) -> str:
    """Single-line text-mode summary for `dotagent doctor` (no --format json)."""
    if not info.installed:
        return "not installed"
    bits = [info.version or "(unknown version)"]
    if not info.db_present:
        bits.append("no graph at .dotgraph/graph.db (run: dotgraph index .)")
        return " · ".join(bits)
    if info.nodes is not None:
        bits.append(f"{info.nodes} nodes")
    if info.dirty_files is not None and info.dirty_files > 0:
        bits.append(f"{info.dirty_files} dirty file(s)")
    elif info.stale:
        bits.append("stale (re-run `dotgraph index .`)")
    else:
        bits.append("clean")
    if info.error:
        bits.append(f"error: {info.error}")
    return " · ".join(bits)
