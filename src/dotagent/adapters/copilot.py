from __future__ import annotations

from .base import Adapter, RenderedFile
from .render import coerce_to_context, render_body


class CopilotAdapter(Adapter):
    name = "copilot"

    def render(self, source) -> list[RenderedFile]:
        ctx = coerce_to_context(source, self.paths)
        body = render_body(ctx, tool_label="GitHub Copilot")
        return [
            RenderedFile(self.paths.repo / ".github" / "copilot-instructions.md", body),
            RenderedFile(self.paths.adapters / "copilot" / "copilot-instructions.md", body),
        ]
