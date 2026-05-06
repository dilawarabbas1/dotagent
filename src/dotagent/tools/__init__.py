"""dotagent tools — concrete utilities the AI agents (and humans) call.

- pattern_extractor: static analysis → semantic patterns
- memory_manager: search + summarize across all four memory stores
- debug_investigator: given a stack trace, find similar past failures
- deploy_checklist: generate a deploy gate from rules + risk signals
- git_proxy: trailer + (future) commit attribution
"""

from .debug_investigator import investigate_stack
from .deploy_checklist import build_checklist
from .memory_manager import search_all
from .pattern_extractor import extract_python_patterns

__all__ = [
    "build_checklist",
    "extract_python_patterns",
    "investigate_stack",
    "search_all",
]
