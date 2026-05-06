from __future__ import annotations

import os
from pathlib import Path

from .paths import Paths

_PRE_COMMIT = """#!/usr/bin/env bash
# dotagent pre-commit hook (auto-installed)
if command -v dotagent >/dev/null 2>&1; then
  dotagent observe pre-commit --files "$(git diff --cached --name-only)" || true
fi
"""

_POST_COMMIT = """#!/usr/bin/env bash
# dotagent post-commit hook (auto-installed)
if command -v dotagent >/dev/null 2>&1; then
  dotagent observe post-commit --sha "$(git rev-parse HEAD)" || true
fi
"""

_PREPARE_COMMIT_MSG = """#!/usr/bin/env bash
# dotagent prepare-commit-msg: append actor + AI tool trailer so attribution
# survives in `git log` even on machines without dotagent installed.
MSG_FILE="$1"
SOURCE="$2"
if [ "$SOURCE" = "merge" ] || [ "$SOURCE" = "squash" ]; then exit 0; fi
if command -v dotagent >/dev/null 2>&1; then
  TRAILER="$(dotagent trailer 2>/dev/null)"
  if [ -n "$TRAILER" ] && ! grep -qF "$TRAILER" "$MSG_FILE" 2>/dev/null; then
    printf "\\n%s\\n" "$TRAILER" >> "$MSG_FILE"
  fi
fi
"""

_CLAUDE_POST_TOOL = """#!/usr/bin/env bash
# dotagent: forward Claude Code post-tool events into episodic memory
if command -v dotagent >/dev/null 2>&1; then
  dotagent observe post-tool --tool claude_code "$@" || true
fi
"""


def install_git_hooks(paths: Paths) -> list[Path]:
    hooks_dir = paths.repo / ".git" / "hooks"
    if not hooks_dir.is_dir():
        return []
    written: list[Path] = []
    for name, body in (
        ("pre-commit", _PRE_COMMIT),
        ("post-commit", _POST_COMMIT),
        ("prepare-commit-msg", _PREPARE_COMMIT_MSG),
    ):
        target = hooks_dir / name
        if target.exists():
            existing = target.read_text()
            if "dotagent" in existing:
                continue
            target.write_text(existing.rstrip() + "\n\n" + body)
        else:
            target.write_text(body)
        try:
            os.chmod(target, 0o755)
        except Exception:
            pass
        written.append(target)
    return written


def install_claude_hooks(paths: Paths) -> list[Path]:
    hd = paths.repo / ".claude" / "hooks"
    hd.mkdir(parents=True, exist_ok=True)
    target = hd / "post-tool.sh"
    target.write_text(_CLAUDE_POST_TOOL)
    try:
        os.chmod(target, 0o755)
    except Exception:
        pass
    return [target]
