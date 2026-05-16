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
    notifier: Callable[[str], None] | None = None,
    llm: LLM | None = None,
) -> str | list[str]:
    """Ask one question.

    `asker(prompt) -> raw input` reads ONE answer from the user.
    `notifier(msg) -> None`  emits a status/help line. Crucially, the notifier
    must NOT consume input — otherwise status messages eat the next answer.
    """
    opts = opts or AskOptions()
    asker = asker or _default_asker
    notifier = notifier or _default_notifier

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
            # treat literal "none" / "(none)" / "n/a" / "-" as "no items"
            if raw.strip().lower() in ("none", "(none)", "n/a", "-"):
                if opts.required:
                    notifier("(at least one item is required — try again)")
                    continue
                return []
            items = [line.strip(" -•\t") for line in re.split(r"[\n;]", raw) if line.strip(" -•\t")]
            if opts.required and not items:
                notifier("(at least one item is required — try again)")
                continue
            return items

        if opts.choices:
            if raw.lower() not in [c.lower() for c in opts.choices]:
                notifier(f"(must be one of: {', '.join(opts.choices)})")
                continue
            return raw.lower()

        if opts.required and not raw:
            notifier("(this field is required — try again)")
            continue

        # vagueness check
        if opts.vagueness_probes and raw:
            heuristic = heuristic_vagueness(prompt, raw)
            llm_probe = llm_vagueness(llm, prompt, raw) if llm else None
            followup = llm_probe or heuristic
            if followup:
                notifier(f"→ {followup} (press Enter to accept your answer, or type a refinement)")
                refined = asker("> ").strip()
                if refined:
                    raw = refined
        return raw


def _default_notifier(msg: str) -> None:
    """Emit a status/help line to stdout. Does NOT consume input."""
    import sys
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


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
    notifier: Callable[[str], None] | None = None,
    llm: LLM | None = None,
) -> Project:
    """Run the project-level Q&A. Returns a populated Project (modules empty)."""
    if llm is None:
        llm = LLM()
    kw = {"asker": asker, "notifier": notifier, "llm": llm}

    name = ask("Project name (one short phrase)?", opts=AskOptions(vagueness_probes=False), **kw)
    goal = ask("What is the goal of this project, in one sentence? What does success look like?", **kw)
    desc = ask("Describe the project in 2–4 sentences. What does it do, who is it for, why now? "
               "(<EDITOR> for multi-line)", opts=AskOptions(multiline=True), **kw)
    oos = ask("Out of scope (semicolon-separated; 'none' for empty):",
              opts=AskOptions(list_=True, required=False, vagueness_probes=False), **kw)
    sc = ask("Success criteria (semicolon-separated, or <EDITOR> for one-per-line):",
             opts=AskOptions(list_=True), **kw)
    stakeholders = ask("Users / stakeholders (semicolon-separated; 'none' for empty):",
                       opts=AskOptions(list_=True, required=False, vagueness_probes=False), **kw)
    constraints = ask("Hard constraints (semicolon-separated; 'none' for empty):",
                      opts=AskOptions(list_=True, required=False), **kw)

    dev_tool = ask("Which tool/agent runs DEVELOPMENT?",
                   opts=AskOptions(choices=KNOWN_TOOLS, default="claude_code", vagueness_probes=False), **kw)
    dev_model = ask("Which MODEL for development (blank = tool default)?",
                    opts=AskOptions(required=False, vagueness_probes=False), **kw)
    qa_tool = ask("Which tool/agent runs QA?",
                  opts=AskOptions(choices=KNOWN_TOOLS, default="claude_code", vagueness_probes=False), **kw)
    qa_model = ask("Which MODEL for QA (blank = tool default)?",
                   opts=AskOptions(required=False, vagueness_probes=False), **kw)

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
    notifier: Callable[[str], None] | None = None,
    llm: LLM | None = None,
) -> ModulePlan:
    """Run the module-level Q&A. Returns a populated ModulePlan."""
    if llm is None:
        llm = LLM()
    kw = {"asker": asker, "notifier": notifier, "llm": llm}

    purpose = ask(f"Module '{name}' — what does this module DO? One sentence.", **kw)
    in_scope = ask("In scope (semicolon-separated; type 'none' for empty list):",
                   opts=AskOptions(list_=True), **kw)
    out_of_scope = ask("Out of scope (semicolon-separated; 'none' for empty):",
                       opts=AskOptions(list_=True, required=False), **kw)
    acceptance = ask("Acceptance criteria (semicolon-separated; or type <EDITOR> for one-per-line in $EDITOR):",
                     opts=AskOptions(list_=True), **kw)
    existing_ids = ", ".join(project.module_ids) or "(none yet)"
    deps_raw = ask(
        f"Depends on other modules? Existing ids: {existing_ids} — semicolon-separated, 'none' for empty:",
        opts=AskOptions(list_=True, required=False, vagueness_probes=False), **kw,
    )
    approach = ask("Technical approach — what is the plan? (free text; <EDITOR> for multi-line)",
                   opts=AskOptions(multiline=True), **kw)
    risks = ask("Known risks / unknowns (semicolon-separated; 'none' for empty):",
                opts=AskOptions(list_=True, required=False), **kw)
    effort = ask("Estimated effort (e.g., '2 days', '1 week') — blank for unknown:",
                 opts=AskOptions(required=False, vagueness_probes=False), **kw)

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
