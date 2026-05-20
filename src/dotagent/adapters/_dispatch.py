"""Adapter render dispatch — picks v1 compendium vs v3 manifest.

All adapters (Claude, Cursor, Copilot, OpenCode) call `resolve_body()`
instead of `render_body()` directly. This function reads
`render.use_manifest` from `.agent/config.yaml` and dispatches to the
right renderer.

- `true` (default at v0.5.0+):     manifest `render_manifest()` — pointers
- `false` (opt-out):                legacy `render_body()` — embedded content

Tool label is preserved for the v1 path (changes the header). The v3
manifest is tool-agnostic (same body regardless of which AI reads it)
so `tool_label` is ignored there.
"""

from __future__ import annotations

from ..config import Config
from ..context import Context
from ..paths import Paths
from .render import render_body as _render_body_v1


def resolve_body(ctx: Context, paths: Paths, *, tool_label: str) -> str:
    """Return the adapter body, choosing renderer per config.

    Best-effort: if the config can't be read or the manifest renderer
    errors, falls back to the v1 compendium so users never get an
    empty file.
    """
    try:
        cfg = Config.load(paths)
        use_manifest = bool(
            ((cfg.raw.get("render") or {}).get("use_manifest"))
        )
    except Exception:  # noqa: BLE001
        use_manifest = False

    if use_manifest:
        try:
            from ..render.manifest import render_manifest
            return render_manifest(paths)
        except Exception as exc:  # noqa: BLE001
            from ..logging import log_exception
            log_exception("manifest render failed; falling back to v1", exc)

    return _render_body_v1(ctx, tool_label=tool_label)


__all__ = ("resolve_body",)
