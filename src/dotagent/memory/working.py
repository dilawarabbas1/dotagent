from __future__ import annotations

import json
from pathlib import Path

from ..paths import Paths


class WorkingMemory:
    """Per-actor, per-session live state. Local only."""

    def __init__(self, paths: Paths, actor: str) -> None:
        self.dir = paths.working / actor
        self.dir.mkdir(parents=True, exist_ok=True)

    def write(self, session: str, payload: dict) -> Path:
        p = self.dir / f"session-{session}.json"
        p.write_text(json.dumps(payload, indent=2))
        return p

    def read(self, session: str) -> dict:
        p = self.dir / f"session-{session}.json"
        if not p.exists():
            return {}
        return json.loads(p.read_text())

    def clear(self, session: str) -> None:
        p = self.dir / f"session-{session}.json"
        if p.exists():
            p.unlink()
