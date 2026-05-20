from __future__ import annotations

from ._dispatch import resolve_body
from .base import Adapter, RenderedFile
from .render import coerce_to_context


class CursorAdapter(Adapter):
    name = "cursor"

    def render(self, source) -> list[RenderedFile]:
        ctx = coerce_to_context(source, self.paths)
        body = resolve_body(ctx, self.paths, tool_label="Cursor")
        return [
            RenderedFile(self.paths.repo / ".cursorrules", body),
            RenderedFile(self.paths.adapters / "cursor" / ".cursorrules", body),
        ]
