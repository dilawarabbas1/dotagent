"""Memory Manager — search + summarize across all four memory stores."""

from __future__ import annotations

from pathlib import Path

from ..paths import Paths
from ..sources import load_cache


def search_all(paths: Paths, query: str, *, limit_per_store: int = 10) -> dict:
    """Substring search across episodic, semantic, sources, personal. Cheap.

    Returns dict keyed by store name. Each value is a list of {path, snippet} dicts.
    """
    q = query.lower().strip()
    out: dict[str, list] = {"episodic": [], "semantic": [], "sources": [], "personal": []}
    if not q:
        return out

    # episodic: search via SQLite if available, fall back to JSONL scan
    try:
        from .. import episodic_index
        episodic_index.ensure_indexed(paths)
        rows = episodic_index.search_summary(paths, query, limit=limit_per_store)
        out["episodic"] = [
            {"path": r.get("ts", ""), "snippet": f"{r['actor']} via {r['tool']}: {r.get('summary', '')}"}
            for r in rows
        ]
    except Exception:
        pass

    # semantic markdown
    if paths.semantic.exists():
        for p in paths.semantic.rglob("*.md"):
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            if q in text.lower():
                out["semantic"].append({"path": str(p.relative_to(paths.repo)), "snippet": _snippet(text, q)})
                if len(out["semantic"]) >= limit_per_store:
                    break

    # indexed sources (cache)
    sources = load_cache(paths)
    for src in sources.values():
        for e in src.entries:
            blob = (e.title + "\n" + e.body).lower()
            if q in blob:
                out["sources"].append({
                    "path": f"{src.path}#{e.id}",
                    "snippet": f"{e.id} — {e.title}",
                })
                if len(out["sources"]) >= limit_per_store:
                    break
        if len(out["sources"]) >= limit_per_store:
            break

    # personal — only the active actor's profile is searchable; teammates' profiles never leak
    if paths.personal.exists():
        for p in paths.personal.rglob("profile.yaml"):
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            if q in text.lower():
                out["personal"].append({"path": str(p.relative_to(paths.repo)), "snippet": _snippet(text, q)})

    return out


def summarize(paths: Paths) -> dict:
    """Return high-level counts across every store."""
    counts = {
        "episodic_files": _count(paths.episodic, "*.jsonl"),
        "semantic_files": _count(paths.semantic, "*.md"),
        "personal_files": _count(paths.personal, "*"),
        "working_files": _count(paths.working, "*.json"),
        "dream_candidates": _count(paths.dream / "candidates", "*.md"),
        "dream_graduated": _count(paths.dream / "graduated", "*.md"),
        "dream_rejected": _count(paths.dream / "rejected", "*.md"),
        "indexed_sources": len(load_cache(paths)),
    }
    return counts


def _count(path: Path, pattern: str) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.rglob(pattern))


def _snippet(text: str, q: str, ctx: int = 80) -> str:
    lower = text.lower()
    i = lower.find(q)
    if i < 0:
        return text[: ctx * 2].replace("\n", " ")
    start = max(0, i - ctx)
    end = min(len(text), i + len(q) + ctx)
    return ("…" if start > 0 else "") + text[start:end].replace("\n", " ") + ("…" if end < len(text) else "")
