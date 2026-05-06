"""Embedding-based clustering for Auto-Dream.

Optional. Requires `pip install dotagent[ml]` for `numpy` + `scikit-learn` +
`sentence-transformers`. If those aren't present, callers fall back to the
heuristic clustering in `dream.signals`.

Pipeline:
1. Pull recent episodic events.
2. Build a text representation per event (kind + summary + files).
3. Embed via sentence-transformers (default: all-MiniLM-L6-v2, 22MB, runs on CPU).
4. Cluster via DBSCAN (proxy for HDBSCAN — stdlib-friendly via sklearn).
5. Emit one Signal per non-noise cluster, weighted by size.
"""

from __future__ import annotations

import importlib
from dataclasses import asdict
from typing import Any

from .. import episodic_index
from ..paths import Paths
from .signals import Signal


def _try_import(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def available() -> bool:
    return all(_try_import(m) is not None for m in ("numpy", "sklearn", "sentence_transformers"))


def _event_text(ev: dict) -> str:
    parts = [ev.get("kind", ""), ev.get("summary", "")]
    files = ev.get("files") or []
    if files:
        parts.append("files:" + " ".join(files))
    return " | ".join(p for p in parts if p)


def cluster_events(
    paths: Paths,
    *,
    since: str = "30d",
    min_cluster_size: int = 3,
    eps: float = 0.45,
    model_name: str = "all-MiniLM-L6-v2",
) -> list[Signal]:
    """Embed + cluster recent episodic events. Returns a Signal per cluster.

    Returns an empty list if the ML extras aren't installed.
    """
    if not available():
        return []

    np = importlib.import_module("numpy")
    sklearn_cluster = importlib.import_module("sklearn.cluster")
    st = importlib.import_module("sentence_transformers")

    episodic_index.ensure_indexed(paths)
    events = episodic_index.activity(paths, since_iso=episodic_index.parse_since(since), limit=2000)
    texts = [_event_text(e) for e in events]
    if len(texts) < min_cluster_size:
        return []

    model = st.SentenceTransformer(model_name)
    embeds = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)

    clusterer = sklearn_cluster.DBSCAN(
        eps=eps, min_samples=min_cluster_size, metric="cosine",
    )
    labels = clusterer.fit_predict(np.asarray(embeds))

    by_cluster: dict[int, list[int]] = {}
    for i, lbl in enumerate(labels):
        if lbl == -1:
            continue
        by_cluster.setdefault(int(lbl), []).append(i)

    out: list[Signal] = []
    for cid, idxs in by_cluster.items():
        members = [events[i] for i in idxs]
        actors = sorted({e.get("actor", "") for e in members if e.get("actor")})
        tools = sorted({e.get("tool", "") for e in members if e.get("tool")})
        files = sorted({f for e in members for f in (e.get("files") or [])})
        title = _label_cluster(members)
        evidence = [
            f"{e['ts'][:10]} {e.get('actor', '')} via {e.get('tool', '')}: {e.get('summary', '')[:80]}"
            for e in members[:8]
        ]
        out.append(Signal(
            id=f"semantic_cluster:{cid}",
            kind="semantic_cluster",
            title=title,
            weight=len(members),
            actors=actors,
            tools=tools,
            files=files,
            evidence=evidence,
        ))
    return out


def _label_cluster(members: list[dict]) -> str:
    """Pick a representative title for the cluster (most common kind + 1st summary)."""
    kinds: dict[str, int] = {}
    for e in members:
        k = e.get("kind") or "event"
        kinds[k] = kinds.get(k, 0) + 1
    top_kind = max(kinds.items(), key=lambda kv: kv[1])[0]
    summary = next((e.get("summary") for e in members if e.get("summary")), "")
    if summary:
        return f"{top_kind} cluster: {summary[:80]} ({len(members)} events)"
    return f"{top_kind} cluster — {len(members)} events"
