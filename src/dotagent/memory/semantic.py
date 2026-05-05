from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import Paths
from ..util import slugify


@dataclass
class SemanticEntry:
    kind: str  # patterns | rules
    category: str  # dependencies | redis-keys | bugs | anti-patterns | ...
    title: str
    body: str
    rationale: str = ""
    provenance: str = ""
    evidence: list[str] = field(default_factory=list)
    graduated_by: str = ""

    @property
    def slug(self) -> str:
        digest = hashlib.sha1((self.kind + self.category + self.title).encode()).hexdigest()[:8]
        return f"{digest}-{slugify(self.title)}"


class SemanticMemory:
    """Graduated patterns + rules. Files use content-hashed slugs so cross-team writes never collide."""

    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    def write(self, entry: SemanticEntry) -> Path:
        target = self.paths.semantic / entry.kind / entry.category / f"{entry.slug}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        rationale = entry.rationale or "_(rationale required — fill in or graduate via Auto-Dream)_"
        provenance = entry.provenance or "_(unknown)_"
        evidence = "\n".join(f"- {e}" for e in entry.evidence) or "_(none)_"
        graduated_by = entry.graduated_by or "_(none)_"
        body = (
            f"# {entry.title}\n\n{entry.body}\n\n"
            f"## Rationale\n\n{rationale}\n\n"
            f"## Evidence\n\n{evidence}\n\n"
            f"## Provenance\n\n{provenance}\n\n"
            f"## Graduated by\n\n{graduated_by}\n"
        )
        target.write_text(body)
        return target

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
