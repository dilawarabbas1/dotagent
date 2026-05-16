from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..paths import Paths
from ..util import slugify


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


@dataclass
class SemanticEntry:
    kind: str  # patterns | rules
    category: str  # dependencies | redis-keys | bugs | anti-patterns | auto-dream | ...
    title: str
    body: str
    rationale: str = ""
    provenance: str = ""
    evidence: list[str] = field(default_factory=list)
    graduated_by: str = ""
    # Module 2 — lifecycle metadata
    graduated_at: str = ""
    review_after: str = ""        # ISO date; default = graduated_at + lifetime_days
    last_reviewed_at: str = ""
    expired_at: str = ""          # set when moved to expired/

    @property
    def slug(self) -> str:
        digest = hashlib.sha1((self.kind + self.category + self.title).encode()).hexdigest()[:8]
        return f"{digest}-{slugify(self.title)}"


# Marker lines we embed in the rendered markdown so we can round-trip the
# lifecycle metadata without forcing every consumer to also keep a YAML sidecar.
_META_PREFIX = "<!-- dotagent-meta:"
_META_SUFFIX = "-->"
_META_RE = re.compile(r"<!--\s*dotagent-meta:\s*(.+?)\s*-->", re.DOTALL)


def _serialize_meta(entry: SemanticEntry) -> str:
    fields = {
        "graduated_at":     entry.graduated_at,
        "review_after":     entry.review_after,
        "last_reviewed_at": entry.last_reviewed_at,
        "expired_at":       entry.expired_at,
    }
    body = ";".join(f"{k}={v}" for k, v in fields.items() if v)
    return f"{_META_PREFIX} {body} {_META_SUFFIX}\n" if body else ""


def _parse_meta(text: str) -> dict:
    """Return the LAST meta comment in the file (most recent re-rationale wins)."""
    matches = list(_META_RE.finditer(text))
    if not matches:
        return {}
    out: dict[str, str] = {}
    for chunk in matches[-1].group(1).split(";"):
        chunk = chunk.strip()
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _extract_body(text: str) -> str:
    """Pull the user-authored body out of a previously-rendered rule file.

    Rendered files look like:  `# {title}\n\n{body}\n\n## Rationale\n...`
    On re-write we want to recover {body} so we don't nest the rendered
    template (and don't carry stale meta comments forward).
    """
    lines = text.splitlines()
    start = 0
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            start = i + 1
            break
    body_lines: list[str] = []
    for ln in lines[start:]:
        # body ends at the first "## " section heading (Rationale / Evidence / Lifecycle / ...)
        if ln.startswith("## "):
            break
        body_lines.append(ln)
    return "\n".join(body_lines).strip()


class SemanticMemory:
    """Graduated patterns + rules. Files use content-hashed slugs so cross-team writes never collide."""

    DEFAULT_LIFETIME_DAYS = 180

    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    def write(self, entry: SemanticEntry, *, lifetime_days: int | None = None) -> Path:
        target = self.paths.semantic / entry.kind / entry.category / f"{entry.slug}.md"
        target.parent.mkdir(parents=True, exist_ok=True)

        # Fill in lifecycle defaults if not provided
        if not entry.graduated_at:
            entry.graduated_at = _now_iso()
        if not entry.review_after:
            lt = lifetime_days if lifetime_days is not None else self.DEFAULT_LIFETIME_DAYS
            base = _parse_iso(entry.graduated_at) or datetime.now(timezone.utc)
            entry.review_after = (base + timedelta(days=lt)).date().isoformat()

        rationale = entry.rationale or "_(rationale required — fill in or graduate via Auto-Dream)_"
        provenance = entry.provenance or "_(unknown)_"
        evidence = "\n".join(f"- {e}" for e in entry.evidence) or "_(none)_"
        graduated_by = entry.graduated_by or "_(none)_"
        body = (
            f"# {entry.title}\n\n{entry.body}\n\n"
            f"## Rationale\n\n{rationale}\n\n"
            f"## Evidence\n\n{evidence}\n\n"
            f"## Provenance\n\n{provenance}\n\n"
            f"## Graduated by\n\n{graduated_by}\n\n"
            f"## Lifecycle\n\n"
            f"- **Graduated at**: {entry.graduated_at}\n"
            f"- **Review after**: {entry.review_after}\n"
            + (f"- **Last reviewed**: {entry.last_reviewed_at}\n" if entry.last_reviewed_at else "")
            + (f"- **Expired at**: {entry.expired_at}\n" if entry.expired_at else "")
            + "\n"
            + _serialize_meta(entry)
        )
        target.write_text(body)
        return target

    def read(self, path: Path) -> SemanticEntry | None:
        """Best-effort parse of a rule .md file back into a SemanticEntry.

        Returns lifecycle metadata even when the rule pre-dates Module 2
        (in which case `graduated_at` is approximated from the file mtime).
        """
        if not path.exists():
            return None
        text = path.read_text(errors="replace")
        meta = _parse_meta(text)
        # extract title from first H1
        title = ""
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        # derive kind/category from path: semantic/<kind>/<category>/<file>.md
        parts = path.relative_to(self.paths.semantic).parts if self.paths.semantic in path.parents else path.parts
        kind = parts[0] if len(parts) >= 1 else ""
        category = parts[1] if len(parts) >= 2 else ""
        # legacy fallback: file mtime as graduated_at
        graduated_at = meta.get("graduated_at") or datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")
        return SemanticEntry(
            kind=kind, category=category, title=title, body=_extract_body(text),
            graduated_at=graduated_at,
            review_after=meta.get("review_after", ""),
            last_reviewed_at=meta.get("last_reviewed_at", ""),
            expired_at=meta.get("expired_at", ""),
        )

    def list(self, kind: str | None = None, category: str | None = None) -> list[Path]:
        roots: list[Path] = (
            [self.paths.semantic / "patterns", self.paths.semantic / "rules"]
            if kind is None
            else [self.paths.semantic / kind]
        )
        out: list[Path] = []
        for root in roots:
            if not root.exists():
                continue
            for p in root.rglob("*.md"):
                if category and category not in p.parts:
                    continue
                out.append(p)
        return sorted(out)
