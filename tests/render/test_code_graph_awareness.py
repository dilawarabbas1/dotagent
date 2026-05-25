"""Tests for the Code-graph awareness block (v0.5.3 — dotgraph integration).

The block must appear in the rendered adapter body iff `.dotgraph/graph.db`
exists at the project root. Filesystem check only — no shell to dotgraph.

Coverage:
- v3 manifest renderer (default in v0.5.0+): present iff db exists.
- v1 compendium renderer: present iff db exists.
- Sister adapters (.cursorrules, copilot, AGENTS) carry the same body
  modulo timestamp — they all inherit the block.
- The block contains the documented MCP tool names: search, context_pack,
  impact, reconcile, find_refs.
- The block contains pointers to the static doc snapshots dotgraph
  emit-docs produces.
- The block is NOT injected when only `.dotgraph/` exists without
  `graph.db` (filesystem check is on the db file).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dotagent.adapters.render import render_body
from dotagent.context import AgentSources, Context
from dotagent.memory import CurrentState
from dotagent.paths import Paths
from dotagent.render.manifest import render_manifest
from dotagent.render.workflow import (
    CODE_GRAPH_AWARENESS_BLOCK,
    code_graph_awareness_block,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paths(tmp_path: Path) -> Paths:
    (tmp_path / ".agent").mkdir()
    return Paths(repo=tmp_path)


def _add_graph_db(repo: Path) -> Path:
    (repo / ".dotgraph").mkdir(parents=True, exist_ok=True)
    db = repo / ".dotgraph" / "graph.db"
    db.write_bytes(b"")  # empty is fine — we only check existence
    return db


def _ctx_for(paths: Paths) -> Context:
    return Context(
        project_name="TestProj",
        actor="alice",
        repo_path=str(paths.repo),
        agent=AgentSources(rules="- always use python 3.11"),
        sources={},
        semantic_pointer_cards=[],
        personal={},
        current=CurrentState(actor="alice"),
        recent_episodic=[],
        config_top_n={},
    )


_BLOCK_HEADER = "🕸  CODE-GRAPH AWARENESS  (dotgraph)"
_MCP_TOOLS = ("context_pack", "impact", "reconcile", "find_refs", "search")
_STATIC_DOCS = (
    "docs/dependency-map.md",
    "docs/db-impact-map.md",
    "docs/redis-key-registry.md",
    "docs/kafka-topics.md",
    "docs/endpoints.md",
)


# ---------------------------------------------------------------------------
# code_graph_awareness_block (helper directly)
# ---------------------------------------------------------------------------

def test_helper_returns_empty_when_db_absent(tmp_path: Path):
    assert code_graph_awareness_block(tmp_path) == ""


def test_helper_returns_block_when_db_present(tmp_path: Path):
    _add_graph_db(tmp_path)
    block = code_graph_awareness_block(tmp_path)
    assert block, "expected non-empty block when .dotgraph/graph.db exists"
    assert _BLOCK_HEADER in block


def test_helper_returns_empty_when_dir_exists_but_db_missing(tmp_path: Path):
    """Filesystem check is on the db FILE, not the directory."""
    (tmp_path / ".dotgraph").mkdir()
    # No graph.db inside
    assert code_graph_awareness_block(tmp_path) == ""


# ---------------------------------------------------------------------------
# v3 manifest renderer
# ---------------------------------------------------------------------------

def test_manifest_includes_block_when_db_present(tmp_path: Path):
    paths = _make_paths(tmp_path)
    _add_graph_db(tmp_path)
    rendered = render_manifest(paths, tier="single-repo")
    assert _BLOCK_HEADER in rendered
    for tool in _MCP_TOOLS:
        assert tool in rendered, f"manifest missing MCP tool '{tool}'"
    for doc in _STATIC_DOCS:
        assert doc in rendered, f"manifest missing static doc reference '{doc}'"


def test_manifest_omits_block_when_db_absent(tmp_path: Path):
    paths = _make_paths(tmp_path)
    rendered = render_manifest(paths, tier="single-repo")
    assert _BLOCK_HEADER not in rendered


def test_manifest_block_appears_in_rules_segment(tmp_path: Path):
    """Block sits in the rules-of-engagement segment — after the HARD POLICY
    header (which is itself well past the workflow contract that mentions
    'MUST READ' as a process step) and BEFORE the 'Where to find what'
    navigation section."""
    paths = _make_paths(tmp_path)
    _add_graph_db(tmp_path)
    rendered = render_manifest(paths, tier="single-repo")
    pos_hard = rendered.find("HARD POLICY")
    pos_block = rendered.find(_BLOCK_HEADER)
    pos_navigation = rendered.find("# Where to find what")
    assert pos_hard >= 0 and pos_block >= 0 and pos_navigation >= 0, (
        "all three markers must be present"
    )
    assert pos_hard < pos_block < pos_navigation, (
        f"expected ordering Hard Policy → Code-graph block → Navigation; "
        f"got hard={pos_hard} block={pos_block} navigation={pos_navigation}"
    )


def test_manifest_byte_diff_only_block(tmp_path: Path):
    """Toggling the db must produce a deterministic diff: the block is the
    only difference (plus the rendered-at timestamp)."""
    import re
    paths = _make_paths(tmp_path)
    without = render_manifest(paths, tier="single-repo")
    _add_graph_db(tmp_path)
    with_db = render_manifest(paths, tier="single-repo")
    # Strip timestamps for diff comparison
    ts_re = re.compile(r"rendered-at: [^\s]+")
    norm_without = ts_re.sub("rendered-at: <ts>", without)
    norm_with = ts_re.sub("rendered-at: <ts>", with_db)
    diff_lines_with = set(norm_with.splitlines()) - set(norm_without.splitlines())
    # Diff lines should all be inside the awareness block
    assert any(_BLOCK_HEADER in line for line in diff_lines_with), (
        "expected the diff to contain the block header"
    )
    # And the lines unique to `without` should be empty (nothing was removed)
    diff_lines_without = set(norm_without.splitlines()) - set(norm_with.splitlines())
    assert diff_lines_without == set(), (
        f"unexpected lines removed when db was added: {diff_lines_without}"
    )


# ---------------------------------------------------------------------------
# v1 compendium renderer
# ---------------------------------------------------------------------------

def test_v1_includes_block_when_db_present(tmp_path: Path):
    paths = _make_paths(tmp_path)
    _add_graph_db(tmp_path)
    body = render_body(_ctx_for(paths), tool_label="test")
    assert _BLOCK_HEADER in body


def test_v1_omits_block_when_db_absent(tmp_path: Path):
    paths = _make_paths(tmp_path)
    body = render_body(_ctx_for(paths), tool_label="test")
    assert _BLOCK_HEADER not in body


# ---------------------------------------------------------------------------
# Sister-adapter parity
# ---------------------------------------------------------------------------

def test_all_adapters_carry_block_when_db_present(tmp_path: Path):
    """All four adapter bodies (CLAUDE.md, .cursorrules, copilot, AGENTS)
    inherit from the same renderer. If the block is in CLAUDE.md, it's in
    all of them."""
    from dotagent.adapters.claude import ClaudeAdapter
    from dotagent.adapters.copilot import CopilotAdapter
    from dotagent.adapters.cursor import CursorAdapter
    from dotagent.adapters.opencode import OpenCodeAdapter
    from dotagent.config import merge_defaults
    from dotagent.scaffold import scaffold_agent_dir
    from dotagent.util import dump_yaml

    paths = _make_paths(tmp_path)
    scaffold_agent_dir(paths)
    dump_yaml(paths.config, merge_defaults({"project": {"name": "X"}}))
    _add_graph_db(tmp_path)

    ctx = _ctx_for(paths)
    for cls in (ClaudeAdapter, CursorAdapter, CopilotAdapter, OpenCodeAdapter):
        adapter = cls(paths)
        body = adapter.render(ctx)[0].content
        assert _BLOCK_HEADER in body, (
            f"{cls.__name__} body missing the dotgraph awareness block"
        )


# ---------------------------------------------------------------------------
# Block content invariants
# ---------------------------------------------------------------------------

def test_block_does_not_embed_mcp_config_snippet():
    """Spec: do NOT include the MCP server config snippet itself.
    That's the consumer's job."""
    block = CODE_GRAPH_AWARENESS_BLOCK
    # No json-shaped or yaml-shaped server config
    assert '"command": "dotgraph"' not in block
    assert '"command":"dotgraph"' not in block
    assert "args:" not in block.replace(" args:", "")  # naive guard


def test_block_references_all_5_mcp_tools():
    for tool in _MCP_TOOLS:
        assert tool in CODE_GRAPH_AWARENESS_BLOCK, f"missing tool '{tool}'"


def test_block_does_not_claim_a_sixth_mcp_tool():
    r"""v0.5.4 regression — `dotgraph serve` exposes exactly 5 MCP tools.
    Adding a sixth (or removing one) without bumping the locked surface
    contract would silently mis-advertise dotgraph's capabilities. Lock
    the count.

    Matches a top-level bullet line of the form `  · \`<name>(...)\` —`.
    Tolerant to formatting tweaks; strict on count.
    """
    import re
    pattern = re.compile(r"^\s*·\s+`([a-z_]+)\(", re.MULTILINE)
    found = pattern.findall(CODE_GRAPH_AWARENESS_BLOCK)
    assert set(found) == set(_MCP_TOOLS), (
        f"awareness block must list exactly the 5 locked MCP tools "
        f"{sorted(_MCP_TOOLS)}; found {sorted(found)}"
    )
    assert len(found) == 5, (
        f"awareness block lists {len(found)} tools; locked surface is 5"
    )


def test_block_references_all_5_static_docs():
    for doc in _STATIC_DOCS:
        assert doc in CODE_GRAPH_AWARENESS_BLOCK, f"missing doc '{doc}'"
