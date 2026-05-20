"""`.agent/git.yaml` — declarative git layout for layered projects.

Defines:
- Where Project Root meta lives (dedicated repo, non-main branch)
- Each service repo: id, path, remote, default branch, role
- Branch rules: which paths are allowed/forbidden on which branches

The companion `git.md` is auto-generated from this file for human reading.

This module is the data layer. Subprocess git invocations and branch-
rule enforcement live in `commands/git_cmd.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


# Constants used by the schema and validators.
MAIN_BRANCH_POLICY_LOCKED = "locked"
MAIN_BRANCH_POLICY_OPEN = "open"

STRATEGY_DEDICATED_REPO = "dedicated_repo"
STRATEGY_RESERVED_BRANCH = "reserved_branch"
STRATEGY_SUBMODULE = "submodule"


@dataclass
class RepoEntry:
    id: str
    path: str
    remote: str = ""
    default_branch: str = "main"
    role: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "path": self.path, "remote": self.remote,
            "default_branch": self.default_branch, "role": self.role,
        }


@dataclass
class BranchRule:
    """Path rules for one branch on one remote."""
    branch: str
    allowed_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "branch": self.branch,
            "allowed_paths": list(self.allowed_paths),
            "forbidden_paths": list(self.forbidden_paths),
            "description": self.description,
        }


@dataclass
class RemoteRules:
    """All branch rules for one remote."""
    remote: str
    branches: list[BranchRule] = field(default_factory=list)


@dataclass
class MetaConfig:
    """Where Project Root meta content lives."""
    strategy: str = STRATEGY_DEDICATED_REPO
    remote: str = ""
    branch: str = "dotagent/meta"
    main_branch_policy: str = MAIN_BRANCH_POLICY_LOCKED

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy, "remote": self.remote,
            "branch": self.branch,
            "main_branch_policy": self.main_branch_policy,
        }


@dataclass
class GitLayout:
    """Parsed git.yaml."""
    meta: MetaConfig
    repos: list[RepoEntry] = field(default_factory=list)
    branch_rules: list[RemoteRules] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "GitLayout":
        return cls(meta=MetaConfig())

    def to_dict(self) -> dict:
        return {
            "meta": self.meta.to_dict(),
            "repos": [r.to_dict() for r in self.repos],
            "branch_rules": [
                {
                    "remote": rr.remote,
                    "branches": {b.branch: {
                        "allowed_paths": b.allowed_paths,
                        "forbidden_paths": b.forbidden_paths,
                        "description": b.description,
                    } for b in rr.branches},
                }
                for rr in self.branch_rules
            ],
        }

    def rules_for(self, remote: str, branch: str) -> BranchRule | None:
        for rr in self.branch_rules:
            if rr.remote != remote:
                continue
            for b in rr.branches:
                if b.branch == branch:
                    return b
        return None


# ---------------------------------------------------------------------------
# Loader + writer
# ---------------------------------------------------------------------------

def load(path: Path) -> GitLayout | None:
    """Read git.yaml. Returns None on missing file."""
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"could not parse git.yaml: {exc}") from exc
    return parse(data)


def parse(data: dict) -> GitLayout:
    meta_raw = data.get("meta") or {}
    meta = MetaConfig(
        strategy=str(meta_raw.get("strategy") or STRATEGY_DEDICATED_REPO),
        remote=str(meta_raw.get("remote") or ""),
        branch=str(meta_raw.get("branch") or "dotagent/meta"),
        main_branch_policy=str(meta_raw.get("main_branch_policy") or MAIN_BRANCH_POLICY_LOCKED),
    )
    _validate_meta(meta)

    repos = [
        RepoEntry(
            id=str(r.get("id") or ""),
            path=str(r.get("path") or ""),
            remote=str(r.get("remote") or ""),
            default_branch=str(r.get("default_branch") or "main"),
            role=str(r.get("role") or ""),
        )
        for r in (data.get("repos") or [])
        if (r.get("id") and r.get("path"))
    ]

    branch_rules: list[RemoteRules] = []
    for rr in (data.get("branch_rules") or []):
        remote = str(rr.get("remote") or "")
        if not remote:
            continue
        branches_data = rr.get("branches") or {}
        branches: list[BranchRule] = []
        for branch_name, br in branches_data.items():
            br = br or {}
            branches.append(BranchRule(
                branch=str(branch_name),
                allowed_paths=[str(p) for p in (br.get("allowed_paths") or [])],
                forbidden_paths=[str(p) for p in (br.get("forbidden_paths") or [])],
                description=str(br.get("description") or ""),
            ))
        branch_rules.append(RemoteRules(remote=remote, branches=branches))

    return GitLayout(meta=meta, repos=repos, branch_rules=branch_rules)


def _validate_meta(meta: MetaConfig) -> None:
    """Refuse known-bad configurations."""
    if meta.branch.lower() == "main" and meta.main_branch_policy == MAIN_BRANCH_POLICY_LOCKED:
        raise ValueError(
            "git.yaml::meta.branch is 'main' but main_branch_policy is 'locked' — "
            "the meta branch must be NOT-main. Pick something like 'dotagent/meta'."
        )


# ---------------------------------------------------------------------------
# Branch-rule verifier
# ---------------------------------------------------------------------------

def verify_paths_against_rule(
    paths: list[str], rule: BranchRule,
) -> tuple[bool, list[str]]:
    """Check `paths` against one BranchRule.

    Returns (ok, offenders). ok=True iff every path either matches an
    allowed pattern AND matches no forbidden pattern.

    Special case: allowed_paths == [] AND forbidden_paths contains '**/*'
    means "this branch accepts nothing" (a locked branch).
    """
    import fnmatch

    offenders: list[str] = []
    fully_locked = (rule.allowed_paths == []) and ("**/*" in rule.forbidden_paths)
    if fully_locked:
        # Everything is rejected.
        return False, list(paths)

    for p in paths:
        if any(_fnmatch_doublestar(p, pat) for pat in rule.forbidden_paths):
            offenders.append(p)
            continue
        if rule.allowed_paths:
            if not any(_fnmatch_doublestar(p, pat) for pat in rule.allowed_paths):
                offenders.append(p)
    return len(offenders) == 0, offenders


def _fnmatch_doublestar(path: str, pattern: str) -> bool:
    """fnmatch with rough `**` support: `**/*.py`, `src/**`, etc."""
    import fnmatch
    if "**" not in pattern:
        # Standard fnmatch handles `*` (any chars except /). For our checks
        # (matching whole repo-relative paths), accept fnmatch's behavior.
        if pattern.endswith("/"):
            return path.startswith(pattern)
        if fnmatch.fnmatch(path, pattern):
            return True
        # Allow a directory prefix to match any file inside it.
        if pattern.endswith("/"):
            return path.startswith(pattern)
        return False
    # Replace `**` with `*` for fnmatch — close enough for path globs.
    # `**/*.py`  → matches any `.py` anywhere
    # `src/**`   → matches anything starting with src/
    if pattern.startswith("**/"):
        suffix = pattern[3:]
        if fnmatch.fnmatch(path, suffix):
            return True
        # Also matches `dir/<suffix>` for any dir.
        parts = path.split("/")
        for i in range(len(parts)):
            tail = "/".join(parts[i:])
            if fnmatch.fnmatch(tail, suffix):
                return True
        return False
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path.startswith(prefix) or path == prefix.rstrip("/")
    # Middle `**` — fall back to splitting and matching each segment.
    head, _, tail = pattern.partition("**")
    return path.startswith(head) and (path.endswith(tail) or fnmatch.fnmatch(path, head + "*" + tail))


# ---------------------------------------------------------------------------
# Human-facing dashboard renderer (git.md)
# ---------------------------------------------------------------------------

def render_dashboard(layout: GitLayout) -> str:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lines = [
        "<!-- GENERATED by dotagent — do not edit. Run `dotagent git rebuild` to refresh. -->",
        "# Git layout",
        "",
        f"_Last generated: {now}_",
        "",
        "## Meta content (Project Root)",
        f"- **Strategy:** {layout.meta.strategy}",
        f"- **Remote:** `{layout.meta.remote or '(unset)'}`",
        f"- **Active branch:** `{layout.meta.branch}`",
        f"- **Main branch policy:** `{layout.meta.main_branch_policy}`",
    ]
    if layout.meta.main_branch_policy == MAIN_BRANCH_POLICY_LOCKED:
        lines.append("  _Meta repo's main is reserved; never push code or content to it._")

    lines.append("")
    if layout.repos:
        lines.append("## Service repos")
        lines.append("")
        lines.append("| Folder | Repo | Active branch | Role |")
        lines.append("|---|---|---|---|")
        for r in layout.repos:
            lines.append(
                f"| `{r.path}` | `{r.remote or r.id}` | {r.default_branch} | {r.role or '—'} |"
            )

    if layout.branch_rules:
        lines.append("")
        lines.append("## Branch reservations")
        lines.append("")
        for rr in layout.branch_rules:
            lines.append(f"### `{rr.remote}`")
            for b in rr.branches:
                desc = f" — {b.description}" if b.description else ""
                lines.append(f"- **`{b.branch}`**{desc}")
                if b.allowed_paths:
                    lines.append(f"  - allowed: {', '.join(f'`{p}`' for p in b.allowed_paths)}")
                if b.forbidden_paths:
                    lines.append(f"  - forbidden: {', '.join(f'`{p}`' for p in b.forbidden_paths)}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = (
    "MAIN_BRANCH_POLICY_LOCKED", "MAIN_BRANCH_POLICY_OPEN",
    "STRATEGY_DEDICATED_REPO", "STRATEGY_RESERVED_BRANCH", "STRATEGY_SUBMODULE",
    "RepoEntry", "BranchRule", "RemoteRules", "MetaConfig", "GitLayout",
    "load", "parse", "verify_paths_against_rule", "render_dashboard",
)
