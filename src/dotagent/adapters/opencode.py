from __future__ import annotations

from .base import Adapter, RenderedFile
from .render import coerce_to_context, render_body


class OpenCodeAdapter(Adapter):
    name = "opencode"

    def render(self, source) -> list[RenderedFile]:
        ctx = coerce_to_context(source, self.paths)
        body = render_body(ctx, tool_label="OpenCode / agentic CLI")
        return [
            RenderedFile(self.paths.repo / "AGENTS.md", body),
            RenderedFile(self.paths.adapters / "opencode" / "AGENTS.md", body),
        ]
