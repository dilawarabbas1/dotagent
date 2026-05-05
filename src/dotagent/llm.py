from __future__ import annotations

import os
from typing import Any

try:
    from anthropic import Anthropic  # type: ignore
except ImportError:  # pragma: no cover
    Anthropic = None  # type: ignore

DEFAULT_MODEL = "claude-sonnet-4-6"


class LLM:
    """Thin wrapper around the Anthropic SDK. Gracefully unavailable if the SDK or key is missing."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("DOTAGENT_MODEL", DEFAULT_MODEL)
        self._client: Any = None
        if Anthropic is not None and os.environ.get("ANTHROPIC_API_KEY"):
            self._client = Anthropic()

    @property
    def available(self) -> bool:
        return self._client is not None

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        if not self.available:
            raise RuntimeError(
                "LLM not configured. Install `anthropic` and set ANTHROPIC_API_KEY, "
                "or run with --no-llm."
            )
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in msg.content if hasattr(block, "text")).strip()
