from __future__ import annotations

from .base import Adapter, RenderedFile
from .render import coerce_to_context, render_body


class CursorAdapter(Adapter):
    name = "cursor"

    def render(self, source) -> list[RenderedFile]:
        ctx = coerce_to_context(source, self.paths)
        body = render_body(ctx, tool_label="Cursor")
        return [
            RenderedFile(self.paths.repo / ".cursorrules", body),
            RenderedFile(self.paths.adapters / "cursor" / ".cursorrules", body),
        ]
