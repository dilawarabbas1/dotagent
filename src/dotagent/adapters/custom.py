"""Custom Jinja-based adapter.

Reads templates from `.agent/adapters/custom/templates/*.j2` and writes outputs
to user-specified paths declared in each template's frontmatter:

    {# output: docs/AI_CONTEXT.md #}
    # {{ ctx.project_name }} — AI context
    ...
"""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .base import Adapter, RenderedFile
from .render import coerce_to_context, render_body


_OUTPUT_DIRECTIVE = re.compile(r"\{#\s*output:\s*([^\s#]+)\s*#\}")


class CustomAdapter(Adapter):
    name = "custom"

    def render(self, source) -> list[RenderedFile]:
        ctx = coerce_to_context(source, self.paths)
        tdir = self.paths.adapters / "custom" / "templates"
        if not tdir.exists():
            return []
        env = Environment(
            loader=FileSystemLoader(str(tdir)),
            autoescape=select_autoescape(disabled_extensions=("j2", "md", "txt")),
            keep_trailing_newline=True,
        )
        env.globals["render_body"] = lambda label="AI agent": render_body(ctx, tool_label=label)
        out: list[RenderedFile] = []
        for tmpl_path in sorted(tdir.glob("*.j2")):
            text = tmpl_path.read_text()
            m = _OUTPUT_DIRECTIVE.search(text)
            if not m:
                continue
            target_rel = m.group(1)
            template = env.get_template(tmpl_path.name)
            rendered = template.render(ctx=ctx, project=ctx.project_name, actor=ctx.actor)
            out.append(RenderedFile(self.paths.repo / target_rel, rendered))
        return out
