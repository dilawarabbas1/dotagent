"""dotagent CLAUDE.md v3 — navigation manifest rendering.

The v3 design treats CLAUDE.md as a NAVIGATION INDEX, not a content
compendium. Pointer-only sections drive the AI to read specific source
files as needed.

Public entry point: `render_manifest(paths, tier=None)` → markdown text.

Design ref: docs/CLAUDE_MD_DESIGN.md.
"""

from __future__ import annotations

from .manifest import render_manifest


__all__ = ("render_manifest",)
