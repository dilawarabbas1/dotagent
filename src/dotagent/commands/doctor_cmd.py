from __future__ import annotations

import json
import sys

import click

from ..doctor import run_checks
from ..dotgraph_probe import (
    STALE_REASON_DIRTY,
    STALE_REASON_OLD,
    probe as _dotgraph_probe,
)
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
            hint = _dg_hint(dg_info)
            if hint:
                click.echo(f"        hint: {hint}")
    if any(d.status == "fail" for d in diagnoses):
        sys.exit(1)


def _safe_dotgraph_probe():
    """Best-effort probe. Returns None when there's no repo to probe.

    Honours `dotagent.dotgraph.stale_threshold_hours` from .agent/config.yaml
    when present; otherwise the probe's built-in default applies.
    """
    try:
        repo = find_repo_root()
    except Exception:  # noqa: BLE001 — find_repo_root raises ClickException
        return None

    threshold = _stale_threshold_from_config(repo)

    try:
        return _dotgraph_probe(repo, stale_threshold_hours=threshold)
    except Exception:  # noqa: BLE001 — defense in depth; probe should never raise
        return None


def _stale_threshold_from_config(repo) -> int | None:
    """Read `dotagent.dotgraph.stale_threshold_hours` from .agent/config.yaml.
    Returns None to let the probe apply its default."""
    try:
        from ..config import Config
        from ..paths import Paths
        paths = Paths(repo=repo)
        if not paths.config.exists():
            return None
        cfg = Config.load(paths)
        val = (((cfg.raw.get("dotagent") or {})
                .get("dotgraph") or {})
                .get("stale_threshold_hours"))
        return int(val) if val is not None else None
    except Exception:  # noqa: BLE001
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


def _dg_hint(info) -> str:
    """v0.5.4 — actionable one-liner when stale. Returns "" otherwise."""
    if not info.installed or not info.stale or not info.stale_reasons:
        return ""

    parts = []
    if STALE_REASON_DIRTY in info.stale_reasons:
        n = info.dirty_files or 0
        parts.append(f"{n} dirty file{'s' if n != 1 else ''}")
    if STALE_REASON_OLD in info.stale_reasons and info.last_indexed:
        parts.append(f"last indexed {_humanize_age(info.last_indexed)} ago")

    detail = " / ".join(parts) if parts else ""
    body = f"run `dotgraph index .`"
    if detail:
        body += f" ({detail})"
    return body


def _humanize_age(iso_ts: str) -> str:
    """'2026-05-21T14:32:01Z' → '4d', '3h', '12m', etc."""
    from datetime import datetime, timezone
    try:
        ts = iso_ts[:-1] + "+00:00" if iso_ts.endswith("Z") else iso_ts
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return iso_ts
    seconds = (datetime.now(timezone.utc) - dt).total_seconds()
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"
