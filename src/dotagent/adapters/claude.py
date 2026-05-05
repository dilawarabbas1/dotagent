from __future__ import annotations

from .base import Adapter, RenderedFile
from .render import coerce_to_context, render_body


class ClaudeAdapter(Adapter):
    name = "claude"

    def render(self, source) -> list[RenderedFile]:
        ctx = coerce_to_context(source, self.paths)
        body = render_body(ctx, tool_label="Claude Code")
        return [
            RenderedFile(self.paths.repo / "CLAUDE.md", body),
            RenderedFile(self.paths.adapters / "claude" / "CLAUDE.md", body),
        ]
