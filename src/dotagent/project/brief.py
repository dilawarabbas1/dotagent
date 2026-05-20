"""project_brief.md — durable business intent for a dotagent project.

The brief is hand-written (or AI-drafted on init) and rarely changes.
It captures:

- Business objectives (OBJ-NN ids)
- Features (FEAT-NN ids, business outcomes — not implementation)
- Hard rules (RULE-NN ids with reasons)
- Glossary, tenancy posture, integrations, non-goals, constraints

Plan.yaml and contracts cite the IDs declared here. `dotagent project
brief check` audits the chain OBJ → FEAT → Module → Contract.

This module owns:

1. Dataclasses + parser (markdown with H2 anchors)
2. Stub template (the canonical structure new briefs start from)
3. `regenerate_modules_section()` — auto-generated Modules table

The brief is parsed by section heading. Cross-section integrity (e.g.,
"every FEAT cites an OBJ that exists") is enforced by `traceability.py`,
landing in PR #6.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Objective:
    id: str
    text: str

    def to_dict(self) -> dict:
        return {"id": self.id, "text": self.text}


@dataclass
class Feature:
    id: str
    name: str
    serves: list[str] = field(default_factory=list)        # OBJ-IDs
    expected_outcome: str = ""
    behaviors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "serves": list(self.serves),
            "expected_outcome": self.expected_outcome,
            "behaviors": list(self.behaviors),
        }


@dataclass
class HardRule:
    id: str
    name: str
    why: str = ""
    how: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "why": self.why, "how": self.how}


@dataclass
class Integration:
    vendor: str
    purpose: str = ""
    used_by: list[str] = field(default_factory=list)   # FEAT-IDs
    auth: str = ""
    contract_owner: str = ""

    def to_dict(self) -> dict:
        return {
            "vendor": self.vendor, "purpose": self.purpose,
            "used_by": list(self.used_by), "auth": self.auth,
            "contract_owner": self.contract_owner,
        }


@dataclass
class Brief:
    """Parsed project_brief.md content. Field-level access for traceability checks."""
    name: str = ""
    last_reviewed: str = ""        # ISO date string
    brief_version: int = 1
    owner: str = ""
    stage: str = ""

    vision: str = ""
    personas: list[str] = field(default_factory=list)
    objectives: list[Objective] = field(default_factory=list)
    features: list[Feature] = field(default_factory=list)
    value_props: list[str] = field(default_factory=list)
    success_metrics: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    hard_rules: list[HardRule] = field(default_factory=list)
    glossary: list[tuple[str, str]] = field(default_factory=list)
    tenancy_lines: list[str] = field(default_factory=list)
    integrations: list[Integration] = field(default_factory=list)

    raw_text: str = ""

    # ---- ID accessors (used by traceability checks) ----

    @property
    def objective_ids(self) -> list[str]:
        return [o.id for o in self.objectives]

    @property
    def feature_ids(self) -> list[str]:
        return [f.id for f in self.features]

    @property
    def rule_ids(self) -> list[str]:
        return [r.id for r in self.hard_rules]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "last_reviewed": self.last_reviewed,
            "brief_version": self.brief_version,
            "owner": self.owner,
            "stage": self.stage,
            "vision": self.vision,
            "personas": list(self.personas),
            "objectives": [o.to_dict() for o in self.objectives],
            "features": [f.to_dict() for f in self.features],
            "value_props": list(self.value_props),
            "success_metrics": list(self.success_metrics),
            "non_goals": list(self.non_goals),
            "constraints": list(self.constraints),
            "hard_rules": [r.to_dict() for r in self.hard_rules],
            "glossary": [{"term": t, "definition": d} for t, d in self.glossary],
            "tenancy_lines": list(self.tenancy_lines),
            "integrations": [i.to_dict() for i in self.integrations],
        }


# ---------------------------------------------------------------------------
# Stub template — what `brief init` writes
# ---------------------------------------------------------------------------

BRIEF_STUB = """<!-- HAND-WRITTEN (or AI-drafted from upload). Rarely changes.
     IDs (OBJ-*, FEAT-*, RULE-*) are referenced from plan.yaml and contracts.
     Bump `brief_version` on a real strategic update. -->

# Project brief: {name}

**Last reviewed:** {today}  ·  **Brief version:** 1  ·  **Owner:** {owner}  ·  **Stage:** seed

## Vision (one sentence)
{vision_or_placeholder}

## Target users
- **Persona 1 — TBD**: TBD

## Business objectives
- **OBJ-01**: TBD (measurable outcome with a number and a deadline)

## Features

### FEAT-01 · TBD
**Serves:** OBJ-01
**Expected outcome:** TBD
**What it must do:**
- TBD

## Value propositions
- TBD

## Business success metrics
- TBD

## Non-goals (business)
- TBD

## Constraints
- TBD

## Risks
- **R1 · TBD** — _mitigation: TBD, owner: TBD_

## Open questions
- TBD — _decided by: TBD, revisit: TBD_

## Glossary
- **TBD** — TBD

## Tenancy & security posture
- **Tenancy:** TBD
- **User auth:** TBD
- **Service-to-service auth:** TBD
- **PII handling:** TBD

## Hard rules
- **RULE-01 · TBD** — _why: TBD; how: TBD_

## External integrations
- **TBD** — purpose: TBD — used by: FEAT-01 — auth: TBD — contract owner: TBD

## Definition of Done
- Acceptance criteria pass (tested, not claimed)
- CI green
- Docs updated in same PR

## Workflow
- **Branching:** trunk + short-lived feature branches; never commit directly to main
- **PR policy:** 1 reviewer min, all CI checks pass, squash-merge
- **Release cadence:** TBD
- **Bug IDs:** `<PREFIX>-####` in `docs/bug-registry.md`

<!-- anchor: modules-table-begin -->
## Modules & delivery status

_(generated; do not edit between the anchors. dotagent rewrites this section on every project event.)_
<!-- anchor: modules-table-end -->
"""


def render_stub(*, name: str = "<your project name>", owner: str = "<name@domain>",
                vision: str = "") -> str:
    """Render a starter brief with sensible placeholders."""
    today = datetime.now(timezone.utc).date().isoformat()
    return BRIEF_STUB.format(
        name=name or "<your project name>",
        owner=owner or "<name@domain>",
        today=today,
        vision_or_placeholder=(vision or "<What this product becomes if it wins.>"),
    )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_H1_RE = re.compile(r"^#\s+Project brief:\s*(.+?)\s*$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)

_META_LINE_RE = re.compile(
    # `**Key:**` (colon inside the bold markers) value (up to · or newline)
    r"\*\*([A-Za-z][\w \-]*?):\*\*\s*(.+?)(?=\s+·|\s*$)",
    re.MULTILINE,
)
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
_ID_TITLE_RE = re.compile(r"^([A-Z][A-Z0-9_]*-\d+)(?:\s*[·:\-—]\s*(.+))?$")
_RULE_LINE_RE = re.compile(
    r"^\s*[-*]\s+\*\*(?P<id>RULE-\d+)\s*[·:\-—]?\s*(?P<name>[^*]+?)\*\*\s*[—-]\s*(?P<rest>.+)$"
)


def parse(text: str) -> Brief:
    """Parse a brief markdown file into a Brief dataclass.

    Tolerant of missing sections; absent fields stay empty/zero. Used by
    traceability audits (PR #6) which then enforce inter-section integrity.
    """
    brief = Brief(raw_text=text)

    # Project name from H1
    h1 = _H1_RE.search(text)
    if h1:
        brief.name = h1.group(1).strip()

    # Metadata line(s) right after H1
    meta_block = _slice_after_h1(text)
    for m in _META_LINE_RE.finditer(meta_block):
        key = m.group(1).strip().lower()
        val = m.group(2).strip()
        if key == "last reviewed":
            brief.last_reviewed = val
        elif key == "brief version":
            try:
                brief.brief_version = int(val)
            except ValueError:
                pass
        elif key == "owner":
            brief.owner = val
        elif key == "stage":
            brief.stage = val

    sections = _split_h2(text)

    if "Vision (one sentence)" in sections:
        body = sections["Vision (one sentence)"].strip()
        # First non-empty line wins
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("<!--"):
                brief.vision = line
                break

    if "Target users" in sections:
        brief.personas = _bullets(sections["Target users"])

    if "Business objectives" in sections:
        brief.objectives = _parse_objectives(sections["Business objectives"])

    if "Features" in sections:
        brief.features = _parse_features(sections["Features"])

    if "Value propositions" in sections:
        brief.value_props = _bullets(sections["Value propositions"])

    if "Business success metrics" in sections:
        brief.success_metrics = _bullets(sections["Business success metrics"])

    if "Non-goals (business)" in sections:
        brief.non_goals = _bullets(sections["Non-goals (business)"])

    if "Constraints" in sections:
        brief.constraints = _bullets(sections["Constraints"])

    if "Hard rules" in sections:
        brief.hard_rules = _parse_hard_rules(sections["Hard rules"])

    if "Glossary" in sections:
        brief.glossary = _parse_glossary(sections["Glossary"])

    if "Tenancy & security posture" in sections:
        brief.tenancy_lines = _bullets(sections["Tenancy & security posture"])

    if "External integrations" in sections:
        brief.integrations = _parse_integrations(sections["External integrations"])

    return brief


def _slice_after_h1(text: str) -> str:
    """Return the slice between H1 and the first H2."""
    h1 = _H1_RE.search(text)
    if not h1:
        return ""
    start = h1.end()
    h2 = _H2_RE.search(text, pos=start)
    end = h2.start() if h2 else len(text)
    return text[start:end]


def _split_h2(text: str) -> dict[str, str]:
    """Return {heading: body} for every H2 section."""
    out: dict[str, str] = {}
    matches = list(_H2_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[m.group(1).strip()] = text[start:end]
    return out


def _bullets(body: str) -> list[str]:
    """Extract bullet lines, skipping TBD/empty."""
    out: list[str] = []
    for line in body.splitlines():
        m = _BULLET_RE.match(line)
        if not m:
            continue
        v = m.group(1).strip()
        if not v or v.lower() == "tbd":
            continue
        out.append(v)
    return out


def _parse_objectives(body: str) -> list[Objective]:
    out: list[Objective] = []
    for line in body.splitlines():
        m = _BULLET_RE.match(line)
        if not m:
            continue
        content = m.group(1).strip()
        # **OBJ-NN**: description
        id_match = re.match(
            r"\*\*(OBJ-\d+)\*\*\s*:?\s*(.+)$", content
        )
        if id_match:
            out.append(Objective(id=id_match.group(1), text=id_match.group(2).strip()))
    return out


def _parse_features(body: str) -> list[Feature]:
    """Features are H3 subsections inside the H2 'Features' section."""
    out: list[Feature] = []
    # Re-scan body for H3 boundaries within Features
    matches = list(_H3_RE.finditer(body))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        head = m.group(1).strip()
        feat_id, feat_name = _split_feature_heading(head)
        if not feat_id:
            continue
        section = body[start:end]
        feat = Feature(id=feat_id, name=feat_name)

        for line in section.splitlines():
            stripped = line.strip()
            # **Serves:** OBJ-01, OBJ-02
            m_serves = re.match(r"^\*\*Serves:\*\*\s*(.+)$", stripped)
            if m_serves:
                feat.serves = [
                    s.strip() for s in re.split(r"[,;]", m_serves.group(1))
                    if s.strip() and re.match(r"^OBJ-\d+$", s.strip())
                ]
                continue
            m_outcome = re.match(r"^\*\*Expected outcome:\*\*\s*(.+)$", stripped)
            if m_outcome:
                feat.expected_outcome = m_outcome.group(1).strip()
                continue
            # bullet under "What it must do"
            m_b = _BULLET_RE.match(line)
            if m_b:
                v = m_b.group(1).strip()
                if v and v.lower() != "tbd":
                    feat.behaviors.append(v)

        out.append(feat)
    return out


def _split_feature_heading(heading: str) -> tuple[str, str]:
    """'FEAT-01 · Authentication' → ('FEAT-01', 'Authentication')."""
    m = re.match(r"^(FEAT-\d+)\s*[·:\-—]?\s*(.+)$", heading.strip())
    if not m:
        return ("", heading.strip())
    return (m.group(1), m.group(2).strip())


def _parse_hard_rules(body: str) -> list[HardRule]:
    """Each rule is a bullet: `**RULE-NN · Name** — _why: ...; how: ..._`."""
    out: list[HardRule] = []
    for line in body.splitlines():
        m = _RULE_LINE_RE.match(line)
        if not m:
            continue
        rule_id = m.group("id")
        name = m.group("name").strip()
        if name.lower() == "tbd":
            continue
        rest = m.group("rest")
        # Strip leading/trailing _italics_
        rest = rest.strip().strip("_")
        why = ""
        how = ""
        # why: <text>; how: <text>
        m_why = re.search(r"why:\s*(.+?)(?:;\s*how:|$)", rest, re.IGNORECASE)
        m_how = re.search(r"how:\s*(.+)$", rest, re.IGNORECASE)
        if m_why:
            why = m_why.group(1).strip().rstrip(";").strip()
        if m_how:
            how = m_how.group(1).strip().rstrip("_").strip()
        out.append(HardRule(id=rule_id, name=name, why=why, how=how))
    return out


def _parse_glossary(body: str) -> list[tuple[str, str]]:
    """Glossary bullets: `**term** — definition`."""
    out: list[tuple[str, str]] = []
    for line in body.splitlines():
        m = _BULLET_RE.match(line)
        if not m:
            continue
        content = m.group(1).strip()
        m_kv = re.match(r"^\*\*([^*]+?)\*\*\s*[—-]\s*(.+)$", content)
        if not m_kv:
            continue
        term = m_kv.group(1).strip()
        defn = m_kv.group(2).strip()
        if not term or term.lower() == "tbd":
            continue
        out.append((term, defn))
    return out


def _parse_integrations(body: str) -> list[Integration]:
    """Integration bullets: `**vendor** — purpose: X — used by: FEAT-01 — auth: Y — contract owner: Z`."""
    out: list[Integration] = []
    for line in body.splitlines():
        m = _BULLET_RE.match(line)
        if not m:
            continue
        content = m.group(1).strip()
        m_vendor = re.match(r"^\*\*([^*]+?)\*\*\s*(?:—|-)\s*(.*)$", content)
        if not m_vendor:
            continue
        vendor = m_vendor.group(1).strip()
        if vendor.lower() == "tbd":
            continue
        rest = m_vendor.group(2)
        integ = Integration(vendor=vendor)
        for chunk in re.split(r"\s+—\s+|\s+-\s+", rest):
            kv = re.match(r"^(purpose|used by|auth|contract owner):\s*(.+)$", chunk, re.IGNORECASE)
            if not kv:
                continue
            key = kv.group(1).lower()
            val = kv.group(2).strip()
            if key == "purpose":
                integ.purpose = val
            elif key == "used by":
                integ.used_by = [
                    s.strip() for s in re.split(r"[,;]", val)
                    if s.strip() and re.match(r"^FEAT-\d+$", s.strip())
                ]
            elif key == "auth":
                integ.auth = val
            elif key == "contract owner":
                integ.contract_owner = val
        out.append(integ)
    return out


# ---------------------------------------------------------------------------
# Loading + saving
# ---------------------------------------------------------------------------

def load(brief_path: Path) -> Brief | None:
    """Read + parse the brief at `brief_path`. None if file missing."""
    if not brief_path.exists():
        return None
    return parse(brief_path.read_text())


def write_stub(brief_path: Path, *, name: str = "", owner: str = "",
               vision: str = "") -> None:
    """Write a fresh brief stub to `brief_path`. Refuses to overwrite."""
    if brief_path.exists():
        raise FileExistsError(f"brief already exists at {brief_path}")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(render_stub(name=name, owner=owner, vision=vision))


# ---------------------------------------------------------------------------
# Auto-generated Modules table (PR #5 stubs; PR #10 implements regeneration)
# ---------------------------------------------------------------------------

_MODULES_BEGIN = "<!-- anchor: modules-table-begin -->"
_MODULES_END = "<!-- anchor: modules-table-end -->"


def replace_modules_section(text: str, new_section_body: str) -> str:
    """Replace content between the modules anchors. Preserves anchors.

    Hand-written content outside the anchors is untouched.
    """
    begin_idx = text.find(_MODULES_BEGIN)
    end_idx = text.find(_MODULES_END)
    if begin_idx < 0 or end_idx < 0 or end_idx < begin_idx:
        # Anchors missing — append the anchored block at the end.
        return (
            text.rstrip()
            + "\n\n" + _MODULES_BEGIN + "\n" + new_section_body.rstrip()
            + "\n" + _MODULES_END + "\n"
        )
    before = text[:begin_idx + len(_MODULES_BEGIN)]
    after = text[end_idx:]
    return before + "\n" + new_section_body.rstrip() + "\n" + after


__all__ = (
    "Brief", "Objective", "Feature", "HardRule", "Integration",
    "BRIEF_STUB",
    "render_stub", "parse", "load", "write_stub",
    "replace_modules_section",
)
