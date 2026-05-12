"""Tiny debug-logging helper.

dotagent runs inside git hooks and Claude Code post-tool hooks where stderr
chatter is annoying. Default is silent. Set `DOTAGENT_DEBUG=1` to surface
exceptions and trace messages on stderr.

Use like:

    from .logging import log_exception
    try:
        thing_that_might_fail()
    except Exception as e:
        log_exception("thing failed", e)
"""

from __future__ import annotations

import os
import sys
import traceback


def debug_enabled() -> bool:
    return os.environ.get("DOTAGENT_DEBUG", "").strip() not in ("", "0", "false", "False")


def log_debug(msg: str) -> None:
    if debug_enabled():
        sys.stderr.write(f"[dotagent.debug] {msg}\n")


def log_exception(msg: str, exc: BaseException) -> None:
    if debug_enabled():
        sys.stderr.write(f"[dotagent.error] {msg}: {exc.__class__.__name__}: {exc}\n")
        sys.stderr.write(traceback.format_exc())
