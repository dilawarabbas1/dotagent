"""Source indexer.

Reads `docs/*.md` files configured under `.agent/config.yaml` `sources:` and parses
them into structured entries the Context resolver and adapters can consume.

Design notes:
- `docs/` is the single source of truth. Never copied; only indexed.
- Parsers are tolerant: they extract H2/H3 sections + bulleted metadata, falling
  back to raw section bodies when the format isn't recognized.
- Output goes to `.agent/.cache/sources.json` (gitignored) for fast adapter render
  and to `.agent/memory/semantic/sources/<id>.md` (committed) as pointer cards.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .paths import Paths
from .util import slugify, write_text

KIND_BUG_REGISTRY = "bug_registry"
KIND_ANTI_PATTERNS = "anti_patterns"
KIND_REDIS_KEYS = "redis_keys"
KIND_DB_IMPACT_MAP = "db_impact_map"
KIND_DEPENDENCY_MAP = "dependency_map"
KIND_ARCHITECTURE = "architecture"
KIND_GENERIC = "generic"

SUPPORTED_KINDS = {
    KIND_BUG_REGISTRY,
    KIND_ANTI_PATTERNS,
    KIND_REDIS_KEYS,
    KIND_DB_IMPACT_MAP,
    KIND_DEPENDENCY_MAP,
    KIND_ARCHITECTURE,
    KIND_GENERIC,
}


@dataclass
class SourceEntry:
    """One parsed item from a source doc (e.g. a single bug, a single anti-pattern)."""

    id: str
    title: str
    body: str
    severity: str = ""
    files: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    raw_metadata: dict = field(default_factory=dict)
    # IDs from OTHER repos this entry references (e.g. backend bug body
    # mentions "AGT-0042" — the project-root bug it's the local slice of).
    # Populated by extract_cross_references() during indexing.
    cross_references: list[str] = field(default_factory=list)


@dataclass
class IndexedSource:
    """The full structured index of one source file."""

    kind: str
    name: str  # logical name from config (e.g. "bug_registry")
    path: str  # repo-relative
    exists: bool
    indexed_at: str
    summary: str = ""
    entries: list[SourceEntry] = field(default_factory=list)
    full_text: str = ""  # only populated when context.embed_full_docs

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# -- markdown helpers --------------------------------------------------------

_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
_META_LINE = re.compile(r"^[-*]\s+\*\*(?P<key>[^*]+?)\*\*\s*[:：]\s*(?P<val>.+?)\s*$")
_BULLET = re.compile(r"^[-*]\s+(.+?)\s*$")
_ID_PREFIX = re.compile(r"^([A-Z]{2,8}-\d{1,5})[:：\s]")
_TABLE_REF = re.compile(r"\b([a-z][a-z0-9_]{2,30})\.([a-z][a-z0-9_]{0,40})\b")
_REDIS_KEY = re.compile(r"`([a-zA-Z0-9_:-]{2,80}\{?[a-zA-Z0-9_:.\-]*\}?[a-zA-Z0-9_:-]*)`")


def _split_h2(text: str) -> list[tuple[str, str]]:
    """Split markdown by H2. Returns [(heading, body)]. Body excludes the heading."""
    parts: list[tuple[str, str]] = []
    matches = list(_H2_RE.finditer(text))
    if not matches:
        return parts
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts.append((title, text[start:end].strip()))
    return parts


def _split_h3(text: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    matches = list(_H3_RE.finditer(text))
    if not matches:
        return parts
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts.append((title, text[start:end].strip()))
    return parts


def _parse_metadata(body: str) -> dict[str, str]:
    """Pull `- **Key**: value` lines from the top of a section body."""
    meta: dict[str, str] = {}
    for line in body.splitlines():
        if not line.strip():
            continue
        m = _META_LINE.match(line.strip())
        if m:
            meta[m.group("key").strip().lower().replace(" ", "_")] = m.group("val").strip()
        elif not line.lstrip().startswith(("-", "*")):
            break
    return meta


def _split_id_title(heading: str) -> tuple[str, str]:
    m = _ID_PREFIX.match(heading.strip())
    if m:
        bug_id = m.group(1)
        title = heading[m.end():].strip(": ").strip()
        return bug_id, title or bug_id
    return slugify(heading)[:32] or "entry", heading


def _extract_files_from_body(body: str) -> list[str]:
    files: set[str] = set()
    for m in re.finditer(r"`([\w./\-_]+\.(?:py|js|ts|tsx|jsx|go|rs|rb|java|sql|sh|cjs|mjs|md|yaml|yml|toml|json))`", body):
        files.add(m.group(1))
    return sorted(files)


def _extract_tables_from_body(body: str) -> list[str]:
    out: set[str] = set()
    for m in _TABLE_REF.finditer(body):
        out.add(f"{m.group(1)}.{m.group(2)}")
    # also bare "table: foo_bar" or column style "tables: foo, bar"
    for line in body.splitlines():
        s = line.strip().lower()
        if s.startswith(("- **table", "- **tables", "table:", "tables:")):
            for tok in re.findall(r"[a-z][a-z0-9_]{2,40}", line.split(":", 1)[-1]):
                out.add(tok)
    return sorted(out)


def _extract_redis_keys(body: str) -> list[str]:
    return sorted({m.group(1) for m in _REDIS_KEY.finditer(body)})


# -- per-kind parsers --------------------------------------------------------


def _parse_bug_registry(text: str) -> list[SourceEntry]:
    out: list[SourceEntry] = []
    for heading, body in _split_h2(text):
        bug_id, title = _split_id_title(heading)
        meta = _parse_metadata(body)
        files = _split_csv(meta.get("file") or meta.get("files")) or _extract_files_from_body(body)
        components = _split_csv(meta.get("component") or meta.get("components"))
        tags = _split_csv(meta.get("tags"))
        out.append(SourceEntry(
            id=bug_id,
            title=title,
            body=body,
            severity=(meta.get("severity") or meta.get("priority") or "").lower(),
            files=files,
            components=components,
            tags=tags,
            raw_metadata=meta,
            cross_references=extract_cross_references(body, self_prefix=_prefix_of(bug_id)),
        ))
    return out


# Cross-references like "BE-0123", "AGT-0042", "PORTAL-0089".
# The prefix is 2+ uppercase letters/digits/underscores; the number is 1+ digits.
_CROSS_REF_RE = re.compile(r"\b([A-Z][A-Z0-9_]*)-(\d{1,6})\b")


def extract_cross_references(body: str, *, self_prefix: str = "") -> list[str]:
    """Find references to OTHER repos' bug IDs in this entry's body.

    Returns a stable, deduplicated list. References to `self_prefix-NNN`
    are filtered out (they're not cross-references — they're self-references).
    Order is first-seen.
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    for m in _CROSS_REF_RE.finditer(body or ""):
        prefix = m.group(1)
        if self_prefix and prefix == self_prefix:
            continue
        full = f"{prefix}-{m.group(2)}"
        if full not in seen_set:
            seen_set.add(full)
            seen.append(full)
    return seen


def _prefix_of(entry_id: str) -> str:
    """Extract the alpha prefix from an ID like 'BE-0042' → 'BE'."""
    if not entry_id or "-" not in entry_id:
        return ""
    head = entry_id.rsplit("-", 1)[0]
    return head if re.fullmatch(r"[A-Z][A-Z0-9_]*", head) else ""


def _parse_anti_patterns(text: str) -> list[SourceEntry]:
    out: list[SourceEntry] = []
    for heading, body in _split_h2(text):
        pid, title = _split_id_title(heading)
        meta = _parse_metadata(body)
        out.append(SourceEntry(
            id=pid,
            title=title,
            body=body,
            severity=(meta.get("severity") or "").lower(),
            files=_split_csv(meta.get("files")) or _extract_files_from_body(body),
            components=_split_csv(meta.get("component") or meta.get("components")),
            tags=_split_csv(meta.get("tags")),
            raw_metadata=meta,
        ))
    return out


def _parse_redis_keys(text: str) -> list[SourceEntry]:
    out: list[SourceEntry] = []
    for heading, body in _split_h2(text):
        rid, title = _split_id_title(heading)
        meta = _parse_metadata(body)
        keys = _split_csv(meta.get("key") or meta.get("keys")) or _extract_redis_keys(body)
        out.append(SourceEntry(
            id=rid,
            title=title,
            body=body,
            keys=keys,
            components=_split_csv(meta.get("component") or meta.get("service") or meta.get("services")),
            tags=_split_csv(meta.get("tags")),
            raw_metadata=meta,
        ))
    return out


def _parse_db_impact_map(text: str) -> list[SourceEntry]:
    out: list[SourceEntry] = []
    for heading, body in _split_h2(text):
        eid, title = _split_id_title(heading)
        meta = _parse_metadata(body)
        tables = _split_csv(meta.get("table") or meta.get("tables")) or _extract_tables_from_body(body)
        out.append(SourceEntry(
            id=eid,
            title=title,
            body=body,
            tables=tables,
            files=_split_csv(meta.get("files")) or _extract_files_from_body(body),
            components=_split_csv(meta.get("component") or meta.get("service") or meta.get("services")),
            tags=_split_csv(meta.get("tags")),
            raw_metadata=meta,
        ))
    return out


def _parse_dependency_map(text: str) -> list[SourceEntry]:
    out: list[SourceEntry] = []
    sections = _split_h2(text)
    if not sections:
        sections = [("Dependencies", text)]
    for heading, body in sections:
        eid, title = _split_id_title(heading)
        meta = _parse_metadata(body)
        components = _split_csv(meta.get("component") or meta.get("service") or meta.get("services"))
        if not components:
            for line in body.splitlines():
                bm = _BULLET.match(line.strip())
                if bm and "→" in bm.group(1):
                    components.extend(s.strip() for s in re.split(r"→|->", bm.group(1)))
        out.append(SourceEntry(
            id=eid,
            title=title,
            body=body,
            components=sorted(set(c for c in components if c)),
            tags=_split_csv(meta.get("tags")),
            raw_metadata=meta,
        ))
    return out


def _parse_architecture(text: str) -> list[SourceEntry]:
    """Architecture docs are read as section summaries — each H2 is one entry."""
    out: list[SourceEntry] = []
    sections = _split_h2(text)
    if not sections:
        out.append(SourceEntry(id="architecture", title="Architecture", body=text.strip()))
        return out
    for heading, body in sections:
        eid, title = _split_id_title(heading)
        meta = _parse_metadata(body)
        out.append(SourceEntry(
            id=eid,
            title=title,
            body=body,
            files=_extract_files_from_body(body),
            tables=_extract_tables_from_body(body),
            components=_split_csv(meta.get("component") or meta.get("service") or meta.get("services")),
            raw_metadata=meta,
        ))
    return out


def _parse_generic(text: str) -> list[SourceEntry]:
    out: list[SourceEntry] = []
    for heading, body in _split_h2(text) or [("Document", text)]:
        eid, title = _split_id_title(heading)
        out.append(SourceEntry(id=eid, title=title, body=body))
    return out


_PARSERS = {
    KIND_BUG_REGISTRY: _parse_bug_registry,
    KIND_ANTI_PATTERNS: _parse_anti_patterns,
    KIND_REDIS_KEYS: _parse_redis_keys,
    KIND_DB_IMPACT_MAP: _parse_db_impact_map,
    KIND_DEPENDENCY_MAP: _parse_dependency_map,
    KIND_ARCHITECTURE: _parse_architecture,
    KIND_GENERIC: _parse_generic,
}


def _split_csv(s: str | None) -> list[str]:
    if not s:
        return []
    return [p.strip() for p in re.split(r"[,;]", s) if p.strip()]


# -- public API --------------------------------------------------------------


def index_one(repo: Path, kind: str, name: str, rel_path: str) -> IndexedSource:
    """Parse a single configured source. Missing files yield an empty IndexedSource."""
    if kind not in SUPPORTED_KINDS:
        kind = KIND_GENERIC
    abs_path = (repo / rel_path).resolve()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not abs_path.exists() or not abs_path.is_file():
        return IndexedSource(kind=kind, name=name, path=rel_path, exists=False, indexed_at=now)
    try:
        text = abs_path.read_text(errors="replace")
    except OSError:
        return IndexedSource(kind=kind, name=name, path=rel_path, exists=False, indexed_at=now)
    parser = _PARSERS.get(kind, _parse_generic)
    entries = parser(text)
    summary = _summarize(kind, entries)
    return IndexedSource(
        kind=kind, name=name, path=rel_path, exists=True,
        indexed_at=now, summary=summary, entries=entries,
    )


def _summarize(kind: str, entries: list[SourceEntry]) -> str:
    if not entries:
        return "(no entries parsed)"
    if kind == KIND_BUG_REGISTRY:
        sev = {}
        for e in entries:
            sev[e.severity or "unknown"] = sev.get(e.severity or "unknown", 0) + 1
        breakdown = ", ".join(f"{n} {k}" for k, n in sorted(sev.items()))
        return f"{len(entries)} bugs ({breakdown})"
    if kind == KIND_ANTI_PATTERNS:
        return f"{len(entries)} anti-patterns"
    if kind == KIND_REDIS_KEYS:
        all_keys = sum(len(e.keys) for e in entries)
        return f"{len(entries)} entries, {all_keys} keys"
    if kind == KIND_DB_IMPACT_MAP:
        all_tables = sum(len(e.tables) for e in entries)
        return f"{len(entries)} entries, {all_tables} table refs"
    if kind == KIND_DEPENDENCY_MAP:
        return f"{len(entries)} dependency entries"
    if kind == KIND_ARCHITECTURE:
        return f"{len(entries)} sections"
    return f"{len(entries)} entries"


def reindex_all(paths: Paths, sources_cfg: dict, *, embed_full_docs: bool = False) -> dict[str, IndexedSource]:
    """Index every configured source. Writes cache + pointer cards. Returns name->IndexedSource."""
    out: dict[str, IndexedSource] = {}
    repo = paths.repo
    for name, value in (sources_cfg or {}).items():
        if name == "extra":
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        kind = name if name in SUPPORTED_KINDS else KIND_GENERIC
        idx = index_one(repo, kind, name, value)
        if embed_full_docs and idx.exists:
            try:
                idx.full_text = (repo / idx.path).read_text(errors="replace")
            except OSError:
                pass
        out[name] = idx
    for extra in (sources_cfg or {}).get("extra") or []:
        if not isinstance(extra, dict):
            continue
        ename = extra.get("name") or ""
        epath = extra.get("path") or ""
        ekind = extra.get("kind") or KIND_GENERIC
        if not ename or not epath:
            continue
        idx = index_one(repo, ekind, ename, epath)
        if embed_full_docs and idx.exists:
            try:
                idx.full_text = (repo / idx.path).read_text(errors="replace")
            except OSError:
                pass
        out[ename] = idx
    _write_cache(paths, out)
    _write_pointer_cards(paths, out)
    return out


def load_cache(paths: Paths) -> dict[str, IndexedSource]:
    """Read the cache file. Returns empty dict if missing."""
    if not paths.sources_cache.exists():
        return {}
    try:
        raw = json.loads(paths.sources_cache.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, IndexedSource] = {}
    for name, d in raw.items():
        entries = [SourceEntry(**e) for e in d.get("entries") or []]
        out[name] = IndexedSource(
            kind=d.get("kind", KIND_GENERIC),
            name=d.get("name", name),
            path=d.get("path", ""),
            exists=bool(d.get("exists")),
            indexed_at=d.get("indexed_at", ""),
            summary=d.get("summary", ""),
            entries=entries,
            full_text=d.get("full_text", ""),
        )
    return out


def _write_cache(paths: Paths, idx: dict[str, IndexedSource]) -> None:
    paths.cache.mkdir(parents=True, exist_ok=True)
    if not paths.cache_gitignore.exists():
        paths.cache_gitignore.write_text("# dotagent cache — regenerated, do not commit\n*\n!.gitignore\n")
    payload = {name: src.to_dict() for name, src in idx.items()}
    paths.sources_cache.write_text(json.dumps(payload, indent=2))


def _write_pointer_cards(paths: Paths, idx: dict[str, IndexedSource]) -> None:
    paths.semantic_sources.mkdir(parents=True, exist_ok=True)
    for name, src in idx.items():
        target = paths.semantic_sources / f"{slugify(name)}.md"
        body = (
            f"# {name}\n\n"
            f"- **Source path**: `{src.path}`\n"
            f"- **Kind**: `{src.kind}`\n"
            f"- **Exists**: {src.exists}\n"
            f"- **Last indexed**: {src.indexed_at}\n"
            f"- **Summary**: {src.summary or '(none)'}\n\n"
            f"_Pointer card. Source of truth lives at `{src.path}`. dotagent indexes it on every "
            f"`reindex` / `sync` run; structured entries cached at `.agent/.cache/sources.json`._\n"
        )
        write_text(target, body)
