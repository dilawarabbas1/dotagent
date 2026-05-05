from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..paths import Paths


@dataclass
class EpisodicEvent:
    ts: str
    actor: str
    tool: str
    host: str
    session: str
    kind: str
    repo: str = ""
    branch: str = ""
    files: list[str] = field(default_factory=list)
    diff_sha: str = ""
    summary: str = ""
    tags: list[str] = field(default_factory=list)


class EpisodicMemory:
    """Append-only JSONL log under .agent/memory/episodic/YYYY/MM/DD/<actor>__<session>.jsonl.

    Filenames are partitioned by date and namespaced by actor+session so concurrent writes
    from teammates never produce git merge conflicts.
    """

    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    def append(self, event: EpisodicEvent) -> Path:
        ts = datetime.fromisoformat(event.ts.replace("Z", "+00:00"))
        sub = self.paths.episodic / f"{ts.year:04d}" / f"{ts.month:02d}" / f"{ts.day:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        path = sub / f"{event.actor}__{event.session}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(event), separators=(",", ":")) + "\n")
        return path

    def iter_events(self):
        if not self.paths.episodic.exists():
            return
        for jsonl in sorted(self.paths.episodic.rglob("*.jsonl")):
            for line in jsonl.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
