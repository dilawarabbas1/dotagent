"""Interactive scope-building Q&A.

Two flows:
- `build_project()` — project-level (run once at `dotagent project init`)
- `build_module(name)` — per-module deep dive (run every `dotagent project add-module`)

Vague-answer detection runs after each question:
- Heuristic (always on): hedging words, single-word answers to open questions,
  missing units after numbers.
- LLM probe (when ANTHROPIC_API_KEY is set): asks the model to classify
  clear/vague/inconsistent and suggest a follow-up.

The Q&A is editor-friendly: long answers can be `<EDITOR>` to open $EDITOR.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable

from ..llm import LLM
from .model import ModulePlan, Project


KNOWN_TOOLS = ["claude_code", "codex", "cursor", "copilot", "opencode", "custom"]


# ---- Vague-answer detection ------------------------------------------------

_HEDGE = re.compile(r"\b(maybe|probably|kind of|sort of|i think|likely|might|perhaps|some|various|several)\b", re.IGNORECASE)
_NUMBER_NO_UNIT = re.compile(r"(?<![A-Za-z\.])\d{1,5}(?:\.\d+)?(?![A-Za-z%/])")
_VAGUE_QUANTIFIERS = re.compile(r"\b(fast|slow|scalable|robust|reliable|simple|complex|good|bad|nice|clean)\b", re.IGNORECASE)


def heuristic_vagueness(question: str, answer: str) -> str | None:
    """Return a follow-up prompt string if the answer looks vague, else None."""
    a = (answer or "").strip()
    if not a:
        return None  # caller already handled empty
    if len(a.split()) < 3 and question.endswith("?") and "name" not in question.lower() and "id" not in question.lower():
        return "That's quite short — can you expand with at least one concrete detail?"
    if _HEDGE.search(a):
        return f"You used hedging language ('{_HEDGE.search(a).group(0)}'). Can you commit to a specific value or remove the hedge?"
    if _VAGUE_QUANTIFIERS.search(a) and not _NUMBER_NO_UNIT.search(a):
        word = _VAGUE_QUANTIFIERS.search(a).group(0)
        return f"You said '{word}' — can you give a measurable target? (e.g., 'p95 < 200ms', '10k req/s')"
    return None


def llm_vagueness(llm: LLM, question: str, answer: str) -> str | None:
    if not llm.available:
        return None
    sys = (
        "You're helping build a project scope document. Given a question and the user's answer, "
        "classify the answer as 'clear' or 'vague'. Output STRICT JSON: "
        '{"clear": bool, "followup": "...one short follow-up question if vague, else empty..."}.'
    )
    user = f"Question: {question}\nAnswer: {answer}\n"
    try:
        raw = llm.complete(sys, user, max_tokens=200)
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        if not data.get("clear", True):
            f = (data.get("followup") or "").strip()
            return f or "That answer is a bit ambiguous — can you be more specific?"
    except Exception:
        return None
    return None


# ---- Prompt helpers --------------------------------------------------------

@dataclass
class AskOptions:
    multiline: bool = False
    list_: bool = False
    default: str = ""
    choices: list[str] | None = None
    required: bool = True
    vagueness_probes: bool = True


def _edit_in_editor(initial: str = "") -> str:
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"
    with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f:
        f.write(initial)
        f.flush()
        path = f.name
    try:
        subprocess.call([editor, path])
        with open(path, "r") as f:
            return f.read().strip()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def ask(
    prompt: str,
    *,
    opts: AskOptions | None = None,
    asker: Callable[[str], str] | None = None,
    llm: LLM | None = None,
) -> str | list[str]:
    """Ask one question. `asker` is a function `(prompt) -> raw input string` so we can mock in tests."""
    opts = opts or AskOptions()
    asker = asker or _default_asker

    while True:
        if opts.choices:
            shown = f"{prompt} ({' / '.join(opts.choices)})"
            if opts.default:
                shown += f" [{opts.default}]"
        else:
            shown = prompt
            if opts.default:
                shown += f" [{opts.default}]"
        raw = asker(shown + "\n> ").strip()

        if raw.upper() == "<EDITOR>":
            raw = _edit_in_editor()

        if not raw and opts.default:
            raw = opts.default

        if opts.list_:
            items = [line.strip(" -•\t") for line in re.split(r"[\n;]", raw) if line.strip(" -•\t")]
            if opts.required and not items:
                asker("(at least one item is required — try again)\n")
                continue
            return items

        if opts.choices:
            if raw.lower() not in [c.lower() for c in opts.choices]:
                asker(f"(must be one of: {', '.join(opts.choices)})\n")
                continue
            return raw.lower()

        if opts.required and not raw:
            asker("(this field is required — try again)\n")
            continue

        # vagueness check
        if opts.vagueness_probes and raw:
            heuristic = heuristic_vagueness(prompt, raw)
            llm_probe = llm_vagueness(llm, prompt, raw) if llm else None
            followup = llm_probe or heuristic
            if followup:
                asker(f"→ {followup} (press Enter to accept your answer, or type a refinement)\n")
                refined = asker("> ").strip()
                if refined:
                    raw = refined
        return raw


def _default_asker(prompt: str) -> str:
    """Default to stdin/stdout; click is available too but stdin is simpler in tests."""
    import sys
    sys.stdout.write(prompt)
    sys.stdout.flush()
    return sys.stdin.readline().rstrip("\n")


# ---- The flows -------------------------------------------------------------

def build_project(
    *,
    asker: Callable[[str], str] | None = None,
    llm: LLM | None = None,
) -> Project:
    """Run the project-level Q&A. Returns a populated Project (modules empty)."""
    if llm is None:
        llm = LLM()

    name = ask("Project name (one short phrase)?", opts=AskOptions(vagueness_probes=False), asker=asker, llm=llm)
    goal = ask("What is the goal of this project, in one sentence? What does success look like?",
               asker=asker, llm=llm)
    desc = ask("Describe the project in 2–4 sentences. What does it do, who is it for, why now?",
               opts=AskOptions(multiline=True), asker=asker, llm=llm)
    oos = ask("What is OUT of scope? (semicolon- or newline-separated; <EDITOR> opens $EDITOR)",
              opts=AskOptions(list_=True, required=False, vagueness_probes=False),
              asker=asker, llm=llm)
    sc = ask("What does 'done' look like? Numbered or bulleted list of success criteria.",
             opts=AskOptions(list_=True), asker=asker, llm=llm)
    stakeholders = ask("Who are the users / stakeholders? (semicolon-separated)",
                       opts=AskOptions(list_=True, required=False, vagueness_probes=False),
                       asker=asker, llm=llm)
    constraints = ask("Hard constraints? (timeline, budget, performance, security; semicolon-separated)",
                      opts=AskOptions(list_=True, required=False), asker=asker, llm=llm)

    dev_tool = ask("Which tool/agent runs DEVELOPMENT?",
                   opts=AskOptions(choices=KNOWN_TOOLS, default="claude_code", vagueness_probes=False),
                   asker=asker, llm=llm)
    dev_model = ask("Which MODEL for development (blank = tool default)?",
                    opts=AskOptions(required=False, vagueness_probes=False), asker=asker, llm=llm)
    qa_tool = ask("Which tool/agent runs QA?",
                  opts=AskOptions(choices=KNOWN_TOOLS, default="claude_code", vagueness_probes=False),
                  asker=asker, llm=llm)
    qa_model = ask("Which MODEL for QA (blank = tool default)?",
                   opts=AskOptions(required=False, vagueness_probes=False), asker=asker, llm=llm)

    from .model import now
    project = Project(
        name=name if isinstance(name, str) else name[0],
        goal=goal if isinstance(goal, str) else " ".join(goal),
        description=desc if isinstance(desc, str) else " ".join(desc),
        out_of_scope=oos if isinstance(oos, list) else [oos] if oos else [],
        success_criteria=sc if isinstance(sc, list) else [sc],
        stakeholders=stakeholders if isinstance(stakeholders, list) else [],
        constraints=constraints if isinstance(constraints, list) else [],
        created_at=now(),
        tools={
            "development": {"tool": dev_tool, "model": dev_model or ""},
            "qa":          {"tool": qa_tool,  "model": qa_model  or ""},
            "review":      {"tool": dev_tool, "model": dev_model or ""},
            "planning":    {"tool": dev_tool, "model": dev_model or ""},
        },
    )
    return project


def build_module(
    name: str,
    project: Project,
    *,
    asker: Callable[[str], str] | None = None,
    llm: LLM | None = None,
) -> ModulePlan:
    """Run the module-level Q&A. Returns a populated ModulePlan."""
    if llm is None:
        llm = LLM()

    purpose = ask(
        f"Module '{name}' — what does this module DO? One sentence.",
        asker=asker, llm=llm,
    )
    in_scope = ask(
        "What's IN scope for this module? (bulleted list; functional units)",
        opts=AskOptions(list_=True), asker=asker, llm=llm,
    )
    out_of_scope = ask(
        "What's explicitly OUT of scope for this module (to avoid creep)?",
        opts=AskOptions(list_=True, required=False), asker=asker, llm=llm,
    )
    acceptance = ask(
        "Acceptance criteria — concrete, testable, numbered (one per line):",
        opts=AskOptions(list_=True), asker=asker, llm=llm,
    )
    existing_ids = ", ".join(project.module_ids) or "(none yet)"
    deps_raw = ask(
        f"Does this module depend on other completed modules? (ids: {existing_ids}; semicolon-separated; blank = none)",
        opts=AskOptions(list_=True, required=False, vagueness_probes=False),
        asker=asker, llm=llm,
    )
    approach = ask(
        "Technical approach — what is the plan? (free text; <EDITOR> for multi-line)",
        opts=AskOptions(multiline=True), asker=asker, llm=llm,
    )
    risks = ask(
        "Known risks / unknowns / open questions (semicolon-separated; blank = none)",
        opts=AskOptions(list_=True, required=False), asker=asker, llm=llm,
    )
    effort = ask(
        "Estimated effort (e.g., '2 days', '1 week') — blank for unknown",
        opts=AskOptions(required=False, vagueness_probes=False), asker=asker, llm=llm,
    )

    return ModulePlan(
        purpose=purpose if isinstance(purpose, str) else " ".join(purpose),
        in_scope=in_scope if isinstance(in_scope, list) else [in_scope],
        out_of_scope=out_of_scope if isinstance(out_of_scope, list) else [],
        acceptance_criteria=acceptance if isinstance(acceptance, list) else [acceptance],
        dependencies=deps_raw if isinstance(deps_raw, list) else [],
        technical_approach=approach if isinstance(approach, str) else " ".join(approach),
        risks=risks if isinstance(risks, list) else [],
        estimated_effort=effort if isinstance(effort, str) else "",
    )
