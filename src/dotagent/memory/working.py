"""Working memory — what's happening *now*.

Two surfaces:
- `WorkingMemory.write/read/clear(session)` — per-session JSON snapshots (legacy API).
- `CurrentState` — a per-actor "current" pointer (`.agent/memory/working/<actor>/current.json`)
  describing the live session: branch, recent files, last-N event summaries. Updated
  by `dotagent observe` so any AI tool can read it and pick up context instantly.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..paths import Paths


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class WorkingEvent:
    ts: str
    kind: str
    tool: str
    summary: str = ""
    files: list[str] = field(default_factory=list)


@dataclass
class CurrentState:
    actor: str
    session: str = ""
    tool: str = ""
    branch: str = ""
    started_at: str = ""
    updated_at: str = ""
    recent_files: list[str] = field(default_factory=list)
    recent_events: list[WorkingEvent] = field(default_factory=list)
    task: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["recent_events"] = [asdict(e) for e in self.recent_events]
        return d


class WorkingMemory:
    """Per-actor, per-session live state. Local only."""

    MAX_RECENT_FILES = 30
    MAX_RECENT_EVENTS = 25

    def __init__(self, paths: Paths, actor: str) -> None:
        self.paths = paths
        self.actor = actor
        self.dir = paths.working / actor
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---- legacy session API (kept for backwards compatibility) ------------

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

    # ---- current-state API (new) ------------------------------------------

    @property
    def current_path(self) -> Path:
        return self.dir / "current.json"

    def load_current(self) -> CurrentState:
        if not self.current_path.exists():
            return CurrentState(actor=self.actor, started_at=_now(), updated_at=_now())
        try:
            data = json.loads(self.current_path.read_text())
        except (OSError, json.JSONDecodeError):
            return CurrentState(actor=self.actor, started_at=_now(), updated_at=_now())
        events = [WorkingEvent(**e) for e in data.get("recent_events") or []]
        return CurrentState(
            actor=data.get("actor", self.actor),
            session=data.get("session", ""),
            tool=data.get("tool", ""),
            branch=data.get("branch", ""),
            started_at=data.get("started_at", _now()),
            updated_at=data.get("updated_at", _now()),
            recent_files=list(data.get("recent_files") or []),
            recent_events=events,
            task=data.get("task", ""),
        )

    def save_current(self, state: CurrentState) -> Path:
        self.current_path.write_text(json.dumps(state.to_dict(), indent=2))
        return self.current_path

    def record_event(
        self,
        *,
        kind: str,
        tool: str,
        summary: str = "",
        files: list[str] | None = None,
        branch: str = "",
        session: str = "",
    ) -> CurrentState:
        state = self.load_current()
        if session:
            state.session = session
        if tool:
            state.tool = tool
        if branch:
            state.branch = branch
        state.updated_at = _now()

        files = files or []
        if files:
            seen: deque[str] = deque(maxlen=self.MAX_RECENT_FILES)
            for f in (files + state.recent_files):
                if f and f not in seen:
                    seen.append(f)
            state.recent_files = list(seen)

        ev = WorkingEvent(ts=_now(), kind=kind, tool=tool, summary=summary, files=files)
        state.recent_events.insert(0, ev)
        state.recent_events = state.recent_events[: self.MAX_RECENT_EVENTS]
        self.save_current(state)
        return state

    def set_task(self, task: str) -> CurrentState:
        state = self.load_current()
        state.task = task
        state.updated_at = _now()
        self.save_current(state)
        return state
