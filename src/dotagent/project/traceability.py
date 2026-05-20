"""Traceability audit: OBJ → FEAT → Module → Contract.

Pure functions over already-loaded data (Brief, Project, Modules).
No filesystem access here; callers wire the loaders.

Used by `dotagent project brief check` (PR #6) and the new `dotagent
project traceability` command. Independent of any LLM or orchestrator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .brief import Brief
from .model import Module, Project


# Findings are layered by severity matching the doctor convention.
SEV_FAIL = "fail"
SEV_WARN = "warn"
SEV_INFO = "info"


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    fix: str = ""

    def to_dict(self) -> dict:
        return {"severity": self.severity, "code": self.code,
                "message": self.message, "fix": self.fix}


@dataclass
class TraceabilityReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == SEV_FAIL for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "findings": [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# Public entry point — full chain audit
# ---------------------------------------------------------------------------

def audit(
    brief: Brief,
    project: Project | None,
    modules: list[Module],
    contracts: list[ContractRef] | None = None,
) -> TraceabilityReport:
    """Audit the full chain: Brief → Plan → Modules → Contracts.

    Each step adds findings. Returns a TraceabilityReport with all of them.
    The caller decides whether to surface them all or just fails.
    """
    report = TraceabilityReport()
    report.findings.extend(audit_obj_to_feat(brief))
    report.findings.extend(audit_feat_to_module(brief, project, modules))
    report.findings.extend(audit_module_to_contract(modules, contracts or []))
    if project is not None:
        report.findings.extend(audit_brief_version_drift(brief, project))
    return report


# ---------------------------------------------------------------------------
# Layer 1: every OBJ has at least one FEAT serving it
# ---------------------------------------------------------------------------

def audit_obj_to_feat(brief: Brief) -> list[Finding]:
    """Every OBJ-NN should be served by at least one FEAT."""
    findings: list[Finding] = []
    served: set[str] = set()
    for feat in brief.features:
        served.update(feat.serves)

    for obj in brief.objectives:
        if obj.id not in served:
            findings.append(Finding(
                severity=SEV_WARN, code="obj-no-feat",
                message=f"{obj.id} is not served by any FEAT",
                fix=f"add a feature with `**Serves:** {obj.id}` or remove {obj.id}",
            ))
    return findings


# ---------------------------------------------------------------------------
# Layer 2: every FEAT has at least one module implementing it
# ---------------------------------------------------------------------------

def audit_feat_to_module(
    brief: Brief, project: Project | None, modules: list[Module],
) -> list[Finding]:
    """Every FEAT-NN that the plan covers must have at least one module
    declaring `implements_features: [FEAT-NN]`."""
    findings: list[Finding] = []
    if project is None:
        return findings

    declared_features = set(project.brief_features_covered)
    implementations: dict[str, list[str]] = {}
    for mod in modules:
        for feat_id in mod.implements_features:
            implementations.setdefault(feat_id, []).append(mod.id)

    for feat in brief.features:
        if declared_features and feat.id not in declared_features:
            # Plan didn't claim this feature; not a finding (yet)
            continue
        if feat.id not in implementations:
            findings.append(Finding(
                severity=SEV_WARN, code="feat-no-module",
                message=f"{feat.id} has no module declaring implements_features",
                fix=f"add a module with implements_features: [{feat.id}]",
            ))
    return findings


# ---------------------------------------------------------------------------
# Layer 3: every active module's contract cites the right FEAT(s)
# ---------------------------------------------------------------------------

@dataclass
class ContractRef:
    """Reference to one cycle's contract for traceability checks."""
    module_id: str
    cycle_n: int
    body: str

    @property
    def feat_refs(self) -> list[str]:
        return _FEAT_REF_RE.findall(_business_section(self.body) or "")

    @property
    def obj_refs(self) -> list[str]:
        return _OBJ_REF_RE.findall(_business_section(self.body) or "")


def audit_module_to_contract(
    modules: list[Module], contracts: list[ContractRef],
) -> list[Finding]:
    """For every contract: cite at least one FEAT that the module implements.

    Modules with no contract yet are not flagged here — that's a separate
    "not started" concern.
    """
    findings: list[Finding] = []
    by_module = {c.module_id: c for c in contracts}
    for mod in modules:
        contract = by_module.get(mod.id)
        if contract is None:
            continue
        if not contract.feat_refs:
            findings.append(Finding(
                severity=SEV_FAIL, code="contract-no-feat",
                message=(
                    f"module {mod.id} / cycle {contract.cycle_n}: contract "
                    f"has no FEAT-NN in business-traceability section"
                ),
                fix="add `**Feature(s):** FEAT-NN` under the business-traceability anchor",
            ))
            continue
        if mod.implements_features:
            missing = [f for f in mod.implements_features if f not in contract.feat_refs]
            if missing:
                findings.append(Finding(
                    severity=SEV_WARN, code="contract-feat-mismatch",
                    message=(
                        f"module {mod.id} / cycle {contract.cycle_n}: contract "
                        f"cites {contract.feat_refs} but module declares {mod.implements_features}"
                    ),
                    fix="reconcile contract citations and module.implements_features",
                ))
    return findings


# ---------------------------------------------------------------------------
# Layer 4: brief version drift
# ---------------------------------------------------------------------------

def audit_brief_version_drift(brief: Brief, project: Project) -> list[Finding]:
    """Warn when plan was last aligned with an older brief version."""
    findings: list[Finding] = []
    if project.brief_version and brief.brief_version > project.brief_version:
        findings.append(Finding(
            severity=SEV_WARN, code="brief-version-drift",
            message=(
                f"plan aligned with brief version {project.brief_version}; "
                f"current brief is version {brief.brief_version}"
            ),
            fix="re-validate plan against the current brief; bump brief_version in plan.yaml",
        ))
    return findings


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

_FEAT_REF_RE = re.compile(r"\bFEAT-\d+\b")
_OBJ_REF_RE = re.compile(r"\bOBJ-\d+\b")

_BUSINESS_BEGIN = "<!-- anchor: business-traceability -->"
_NEGOTIATION_BEGIN = "<!-- anchor: negotiation-log -->"


def _business_section(body: str) -> str:
    """Extract content of the business-traceability section from a contract."""
    start = body.find(_BUSINESS_BEGIN)
    if start < 0:
        return ""
    after = body[start + len(_BUSINESS_BEGIN):]
    end = after.find(_NEGOTIATION_BEGIN)
    if end < 0:
        return after
    return after[:end]


# ---------------------------------------------------------------------------
# Loader helpers (filesystem-aware, used by the CLI)
# ---------------------------------------------------------------------------

def load_active_contracts(repo: Path, modules: list[Module]) -> list[ContractRef]:
    """Build ContractRef list from every module's current cycle contract."""
    out: list[ContractRef] = []
    for mod in modules:
        if not mod.cycles:
            continue
        cycle = mod.cycles[-1]
        if not cycle.contract:
            continue
        contract_path = repo / cycle.contract.path
        if not contract_path.exists():
            continue
        out.append(ContractRef(
            module_id=mod.id, cycle_n=cycle.n,
            body=contract_path.read_text(),
        ))
    return out


__all__ = (
    "SEV_FAIL", "SEV_WARN", "SEV_INFO",
    "Finding", "TraceabilityReport", "ContractRef",
    "audit", "audit_obj_to_feat", "audit_feat_to_module",
    "audit_module_to_contract", "audit_brief_version_drift",
    "load_active_contracts",
)
