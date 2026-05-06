"""Deploy Checklist — synthesize a pre-deploy gate from rules + recent risk signals."""

from __future__ import annotations

from .. import episodic_index
from ..paths import Paths
from ..sources import load_cache


def build_checklist(paths: Paths, *, since: str = "14d") -> dict:
    """Return checklist items derived from rules.md, bug registry, and recent reverts/fixes."""
    items: list[dict] = []

    rules_md = paths.rules.read_text(errors="replace") if paths.rules.exists() else ""
    for line in rules_md.splitlines():
        s = line.strip()
        if s.startswith("- ") and len(s) > 4:
            items.append({"source": "rules.md", "kind": "rule", "text": s[2:]})

    sources = load_cache(paths)
    bug_src = sources.get("bug_registry")
    if bug_src and bug_src.exists:
        for e in bug_src.entries:
            if e.severity in ("critical", "high", "p0", "p1"):
                files = ", ".join(e.files[:3])
                txt = f"Verify {e.id} ({e.title}) is not regressed"
                if files:
                    txt += f" — touches {files}"
                items.append({"source": "bug-registry", "kind": "regression-check", "text": txt})

    try:
        episodic_index.ensure_indexed(paths)
        since_iso = episodic_index.parse_since(since)
        recent = episodic_index.activity(paths, since_iso=since_iso, limit=200)
    except Exception:
        recent = []

    reverts = [e for e in recent if "revert" in (e.get("summary") or "").lower() or e.get("kind") == "revert"]
    fixes = [e for e in recent if (e.get("kind", "") in ("fix", "hotfix") or
                                    (e.get("summary", "").lower().startswith(("fix", "hotfix"))))]
    if reverts:
        items.append({
            "source": "episodic", "kind": "risk-signal",
            "text": f"{len(reverts)} reverts in last {since} — confirm rollback plan + dashboards",
        })
    if len(fixes) >= 5:
        items.append({
            "source": "episodic", "kind": "risk-signal",
            "text": f"{len(fixes)} fix-commits in last {since} — request a heightened-attention review",
        })

    anti_src = sources.get("anti_patterns")
    if anti_src and anti_src.exists:
        items.append({
            "source": "anti-patterns", "kind": "review-prompt",
            "text": f"Spot-check the diff against `{anti_src.path}` ({len(anti_src.entries)} entries)",
        })

    return {"window": since, "items": items}
