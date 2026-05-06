"""Pattern Extractor — static analysis emits semantic patterns.

Phase 4 walking-skeleton: Python AST + JS/TS regex import scanning. Emits
SemanticEntry records (kind=patterns, category=imports/structure) into
.agent/memory/semantic/. Lossless — entries describe observed structure;
graduation to "rules" still requires human review (Auto-Dream pipeline).
"""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from pathlib import Path

from ..memory import SemanticEntry, SemanticMemory
from ..paths import Paths


_SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".cache", ".next"}


def _walk(repo: Path, exts: tuple[str, ...]):
    for p in repo.rglob("*"):
        if any(part in _SKIP for part in p.parts):
            continue
        if p.is_file() and p.suffix in exts:
            yield p


def extract_python_patterns(repo: Path) -> dict:
    """Return {imports: Counter, fan_in: dict, modules: list}.

    Cheap heuristic: counts top-level imports + per-module dependencies.
    """
    imports: Counter[str] = Counter()
    deps: dict[str, set[str]] = defaultdict(set)
    modules: list[str] = []
    for p in _walk(repo, (".py",)):
        rel = str(p.relative_to(repo))
        modules.append(rel)
        try:
            tree = ast.parse(p.read_text(errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports[n.name.split(".")[0]] += 1
                    deps[rel].add(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                imports[root] += 1
                deps[rel].add(root)
    return {"imports": imports, "deps": deps, "modules": modules}


_JS_IMPORT = re.compile(r"""(?:^|\s)(?:import|require)\s*\(?["']([^"']+)["']\)?""")


def extract_js_patterns(repo: Path) -> dict:
    imports: Counter[str] = Counter()
    deps: dict[str, set[str]] = defaultdict(set)
    modules: list[str] = []
    for p in _walk(repo, (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
        rel = str(p.relative_to(repo))
        modules.append(rel)
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        for m in _JS_IMPORT.finditer(text):
            target = m.group(1)
            root = target.split("/")[0]
            if root.startswith("."):
                continue
            imports[root] += 1
            deps[rel].add(root)
    return {"imports": imports, "deps": deps, "modules": modules}


def write_patterns(paths: Paths) -> list[Path]:
    """Run extractors + write SemanticEntry files. Returns list of written paths."""
    repo = paths.repo
    written: list[Path] = []
    py = extract_python_patterns(repo)
    js = extract_js_patterns(repo)
    mem = SemanticMemory(paths)

    for label, result in (("python", py), ("js-ts", js)):
        top = result["imports"].most_common(20)
        if not top:
            continue
        body_lines = [f"Top imports across {len(result['modules'])} {label} modules:"]
        for name, n in top:
            body_lines.append(f"- `{name}` — used by {n} reference(s)")
        entry = SemanticEntry(
            kind="patterns",
            category="imports",
            title=f"{label} import landscape",
            body="\n".join(body_lines),
            rationale="Emitted by Pattern Extractor (static analysis). Use as input to "
                      "Auto-Dream graduation, not as a rule on its own.",
            provenance="static analysis",
            evidence=[f"{n}× {name}" for name, n in top[:10]],
        )
        written.append(mem.write(entry))
    return written
