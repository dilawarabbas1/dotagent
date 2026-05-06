"""Skills runtime — load, list, and run the markdown skills under .agent/skills/.

A skill is a markdown file with optional YAML frontmatter:

    ---
    name: observer
    description: Observe the repo state before acting.
    inputs: [task]
    ---
    # Observer
    Body that becomes the system prompt when the skill is run via LLM.

`dotagent skill list/show` work without an API key. `dotagent skill run` calls
the LLM (anthropic). When no API key is set, run prints a dry-run plan with
the resolved prompt instead of failing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .context import Context
from .llm import LLM
from .paths import Paths


_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Skill:
    name: str
    path: Path
    description: str = ""
    inputs: list[str] = field(default_factory=list)
    frontmatter: dict = field(default_factory=dict)
    body: str = ""


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER.match(text)
    if not m:
        return {}, text
    import yaml
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, text[m.end():]


def load_skill(path: Path) -> Skill:
    text = path.read_text(errors="replace")
    meta, body = _parse_frontmatter(text)
    name = (meta.get("name") if isinstance(meta, dict) else None) or path.stem
    return Skill(
        name=name,
        path=path,
        description=(meta.get("description") if isinstance(meta, dict) else "") or "",
        inputs=list((meta.get("inputs") if isinstance(meta, dict) else []) or []),
        frontmatter=meta if isinstance(meta, dict) else {},
        body=body.strip(),
    )


def list_skills(paths: Paths) -> list[Skill]:
    out: list[Skill] = []
    if not paths.skills.exists():
        return out
    for p in sorted(paths.skills.glob("*.md")):
        try:
            out.append(load_skill(p))
        except Exception:
            continue
    return out


def get_skill(paths: Paths, name: str) -> Skill:
    for s in list_skills(paths):
        if s.name == name or s.path.stem == name:
            return s
    raise KeyError(f"unknown skill: {name}")


def _system_prompt(skill: Skill, ctx: Context) -> str:
    return (
        f"You are running the `{skill.name}` skill on the `{ctx.project_name}` project.\n"
        f"Skill description: {skill.description}\n\n"
        f"Skill instructions:\n{skill.body}\n"
    )


def _user_prompt(ctx: Context, task: str = "", extra_inputs: dict | None = None) -> str:
    parts: list[str] = []
    parts.append(f"Active actor: {ctx.actor}")
    if ctx.current.branch:
        parts.append(f"Branch: {ctx.current.branch}")
    if task:
        parts.append(f"Task: {task}")
    if extra_inputs:
        for k, v in extra_inputs.items():
            parts.append(f"{k}: {v}")
    if ctx.current.recent_files:
        parts.append("Recent files: " + ", ".join(ctx.current.recent_files[:10]))
    if ctx.top_bugs():
        parts.append("Top bugs to be mindful of:")
        for b in ctx.top_bugs(5):
            parts.append(f"  - {b.id} [{b.severity}] {b.title}")
    if ctx.recent_episodic:
        parts.append("Recent episodic events:")
        for e in ctx.recent_episodic[:5]:
            parts.append(f"  - {e['ts'][:10]} {e.get('actor')} via {e.get('tool')}: {e.get('summary', '')[:80]}")
    return "\n".join(parts)


def run_skill(
    paths: Paths,
    ctx: Context,
    name: str,
    *,
    task: str = "",
    extra_inputs: dict | None = None,
    dry_run: bool = False,
) -> dict:
    skill = get_skill(paths, name)
    sys_p = _system_prompt(skill, ctx)
    usr_p = _user_prompt(ctx, task=task, extra_inputs=extra_inputs)
    if dry_run:
        return {"skill": skill.name, "system": sys_p, "user": usr_p, "output": None}
    llm = LLM()
    if not llm.available:
        return {"skill": skill.name, "system": sys_p, "user": usr_p, "output": None,
                "note": "ANTHROPIC_API_KEY not set; printing prompt instead of running."}
    try:
        out = llm.complete(sys_p, usr_p, max_tokens=2000)
    except Exception as e:
        return {"skill": skill.name, "system": sys_p, "user": usr_p, "output": None, "error": str(e)}
    return {"skill": skill.name, "system": sys_p, "user": usr_p, "output": out}


def run_pipeline(paths: Paths, ctx: Context, names: list[str], *, task: str = "", dry_run: bool = False) -> list[dict]:
    """Chain skills, feeding each output as `prior_output` to the next."""
    results: list[dict] = []
    prior = ""
    for n in names:
        extras = {"prior_output": prior} if prior else None
        r = run_skill(paths, ctx, n, task=task, extra_inputs=extras, dry_run=dry_run)
        results.append(r)
        prior = r.get("output") or ""
    return results
