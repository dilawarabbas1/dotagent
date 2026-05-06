"""Cursor < 0.40 file-watcher fallback.

Cursor 0.40+ supports proper hooks. For older versions, we run a foreground
daemon that:
1. Watches the repo (excluding .git, node_modules, .venv, etc.).
2. When a file is modified AND a Cursor process is currently running,
   tags the change as `tool=cursor` and forwards it to dotagent observe.
3. Debounces bursts (2-second window) so a single Cursor edit becomes one event.

Requires `pip install dotagent[watch]` (adds `watchdog`). Without it, the command
prints an actionable error instead of silently skipping.
"""

from __future__ import annotations

import importlib
import subprocess
import time
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Any

from ..identity import host, new_session_id, resolve
from ..memory import EpisodicEvent, EpisodicMemory, WorkingMemory
from ..paths import Paths

_DEBOUNCE_SECONDS = 2.0
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cache", "dist", "build", ".next", ".agent"}


def watchdog_available() -> bool:
    try:
        importlib.import_module("watchdog.events")
        importlib.import_module("watchdog.observers")
        return True
    except ImportError:
        return False


def cursor_running() -> bool:
    """True if any process named cursor is currently running."""
    try:
        res = subprocess.run(
            ["pgrep", "-f", "(?i)cursor"], capture_output=True, text=True, timeout=2
        )
        return res.returncode == 0 and bool(res.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _is_skipped(path: Path, repo: Path) -> bool:
    try:
        rel = path.resolve().relative_to(repo.resolve())
    except ValueError:
        return True
    return any(part in _SKIP_DIRS for part in rel.parts)


class _DebouncedFlusher:
    """Aggregate file changes within a window, then emit one event."""

    def __init__(self, paths: Paths, *, window: float = _DEBOUNCE_SECONDS) -> None:
        self.paths = paths
        self.window = window
        self.buffer: deque[str] = deque()
        self.last_change: float = 0.0
        self.lock = Lock()

    def add(self, file: str) -> None:
        with self.lock:
            if file not in self.buffer:
                self.buffer.append(file)
            self.last_change = time.time()

    def maybe_flush(self) -> None:
        with self.lock:
            if not self.buffer or (time.time() - self.last_change) < self.window:
                return
            files = list(self.buffer)
            self.buffer.clear()
        if not cursor_running():
            return
        self._emit(files)

    def _emit(self, files: list[str]) -> None:
        repo = self.paths.repo
        identity = resolve(repo)
        session = new_session_id()
        event = EpisodicEvent(
            ts=EpisodicMemory.now(),
            actor=identity.id,
            tool="cursor",
            host=host(),
            session=session,
            kind="edit",
            repo=repo.name,
            files=files,
            summary=f"cursor watcher: {len(files)} file(s)",
        )
        EpisodicMemory(self.paths).append(event)
        WorkingMemory(self.paths, identity.id).record_event(
            kind="edit", tool="cursor", summary=event.summary,
            files=files, session=session,
        )


def run_cursor_watch(paths: Paths, *, on_event: Any = None) -> None:
    """Foreground watcher loop. Ctrl-C to stop."""
    if not watchdog_available():
        raise RuntimeError("watchdog not installed — run `pip install dotagent[watch]`.")
    events_mod = importlib.import_module("watchdog.events")
    observers_mod = importlib.import_module("watchdog.observers")

    flusher = _DebouncedFlusher(paths)

    class Handler(events_mod.FileSystemEventHandler):  # type: ignore[misc, name-defined]
        def on_modified(self, event):  # type: ignore[no-untyped-def]
            if event.is_directory:
                return
            p = Path(event.src_path)
            if _is_skipped(p, paths.repo):
                return
            try:
                rel = str(p.resolve().relative_to(paths.repo.resolve()))
            except ValueError:
                return
            flusher.add(rel)
            if on_event:
                on_event(rel)

    observer = observers_mod.Observer()
    observer.schedule(Handler(), str(paths.repo), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(0.5)
            flusher.maybe_flush()
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
