from __future__ import annotations

import json
import sys

import click

from ..paths import Paths, find_repo_root
from ..tools import (
    build_checklist,
    extract_python_patterns,
    investigate_stack,
    search_all,
)
from ..tools.memory_manager import summarize as memory_summarize
from ..tools.pattern_extractor import extract_js_patterns, write_patterns


def _paths() -> Paths:
    repo = find_repo_root()
    paths = Paths(repo=repo)
    if not paths.agent.exists():
        raise click.ClickException("No .agent/ in this repo. Run `dotagent init` first.")
    return paths


@click.group(name="tool", help="Built-in tools: pattern-extractor, memory, debug, checklist.")
def tool_group() -> None:
    pass


@tool_group.command(name="list", help="List available tools.")
def tool_list() -> None:
    rows = [
        ("pattern-extractor", "Static analysis → semantic patterns"),
        ("memory",            "Search across all four memory stores"),
        ("debug",             "Investigate a stack trace against past failures"),
        ("checklist",         "Synthesize a pre-deploy gate"),
    ]
    for name, desc in rows:
        click.echo(f"  · {name:22s} {desc}")


@tool_group.command(name="pattern-extractor", help="Run static analysis + write semantic patterns.")
@click.option("--write", is_flag=True, help="Write SemanticEntry records to .agent/memory/semantic/.")
def cmd_pattern_extractor(write: bool) -> None:
    paths = _paths()
    py = extract_python_patterns(paths.repo)
    js = extract_js_patterns(paths.repo)
    click.echo(f"python: {len(py['modules'])} modules, top imports: "
               + ", ".join(f"{n}({c})" for n, c in py["imports"].most_common(5)))
    click.echo(f"js/ts:  {len(js['modules'])} modules, top imports: "
               + ", ".join(f"{n}({c})" for n, c in js["imports"].most_common(5)))
    if write:
        written = write_patterns(paths)
        click.echo(f"wrote {len(written)} semantic pattern files")


@tool_group.command(name="memory", help="Search + summarize the four memory stores.")
@click.argument("query", required=False, default="")
@click.option("--summary", is_flag=True, help="Print store-level counts.")
def cmd_memory(query: str, summary: bool) -> None:
    paths = _paths()
    if summary or not query:
        s = memory_summarize(paths)
        for k, v in s.items():
            click.echo(f"  {k:24s} {v}")
        return
    results = search_all(paths, query)
    for store, hits in results.items():
        if not hits:
            continue
        click.echo(f"\n[{store}] ({len(hits)} hits)")
        for h in hits:
            click.echo(f"  · {h['path']}: {h['snippet']}")


@tool_group.command(name="debug", help="Investigate a stack trace against episodic memory + bug registry.")
@click.argument("trace_arg", required=False, default="")
@click.option("--file", "from_file", default="", help="Read trace from file (use `-` for stdin).")
def cmd_debug(trace_arg: str, from_file: str) -> None:
    paths = _paths()
    if from_file == "-":
        stack = sys.stdin.read()
    elif from_file:
        stack = open(from_file).read()
    elif trace_arg:
        stack = trace_arg
    else:
        raise click.ClickException("Provide a trace as an argument, or --file <path>, or --file - for stdin.")
    findings = investigate_stack(paths, stack)
    click.echo(f"signature: errors={findings['signature']['errors']} "
               f"files={findings['signature']['files'][:5]}")
    if findings["bug_matches"]:
        click.echo("\nbug-registry matches:")
        for b in findings["bug_matches"]:
            click.echo(f"  · {b['id']} [{b.get('severity', '?')}] — {b['title']}")
    if findings["episodic_matches"]:
        click.echo("\nepisodic matches:")
        for e in findings["episodic_matches"][:10]:
            click.echo(f"  · {e['ts'][:10]}  {e['actor']:18s} {e['tool']:12s}  "
                       f"{e.get('summary', '')[:80]}  ({e.get('match_via', '')})")
    if not findings["bug_matches"] and not findings["episodic_matches"]:
        click.echo("(no matches)")


@tool_group.command(name="checklist", help="Pre-deploy checklist from rules + risk signals.")
@click.option("--since", default="14d")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
def cmd_checklist(since: str, fmt: str) -> None:
    paths = _paths()
    cl = build_checklist(paths, since=since)
    if fmt == "json":
        click.echo(json.dumps(cl, indent=2))
        return
    click.echo(f"Pre-deploy checklist (window: {cl['window']})")
    if not cl["items"]:
        click.echo("  (empty — fill in rules.md / bug-registry.md)"); return
    for it in cl["items"]:
        click.echo(f"  [ ] {it['text']}   _({it['source']}: {it['kind']})_")
