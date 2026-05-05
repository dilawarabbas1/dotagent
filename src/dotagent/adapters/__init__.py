from .base import Adapter, RenderedFile, read_source
from .claude import ClaudeAdapter
from .copilot import CopilotAdapter
from .cursor import CursorAdapter
from .opencode import OpenCodeAdapter

REGISTRY: dict[str, type[Adapter]] = {
    "claude": ClaudeAdapter,
    "cursor": CursorAdapter,
    "copilot": CopilotAdapter,
    "opencode": OpenCodeAdapter,
}


def get(name: str) -> type[Adapter]:
    if name not in REGISTRY:
        raise KeyError(f"Unknown adapter: {name}")
    return REGISTRY[name]


__all__ = [
    "Adapter",
    "ClaudeAdapter",
    "CopilotAdapter",
    "CursorAdapter",
    "OpenCodeAdapter",
    "REGISTRY",
    "RenderedFile",
    "get",
    "read_source",
]
