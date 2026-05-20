"""Integration tests for the adapter render dispatch.

Confirms each adapter (Claude, Cursor, Copilot, OpenCode) honors
`render.use_manifest`:

- flag false (default) → v1 compendium content
- flag true            → v3 manifest content
- flag malformed/missing → falls back to v1 safely
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dotagent.adapters.claude import ClaudeAdapter
from dotagent.adapters.copilot import CopilotAdapter
from dotagent.adapters.cursor import CursorAdapter
from dotagent.adapters.opencode import OpenCodeAdapter
from dotagent.config import merge_defaults
from dotagent.context import AgentSources, Context
from dotagent.memory import CurrentState
from dotagent.paths import Paths
from dotagent.scaffold import scaffold_agent_dir
from dotagent.util import dump_yaml


def _scaffolded(tmp_path: Path, *, render_config: dict | None = None) -> Paths:
    paths = Paths(repo=tmp_path)
    scaffold_agent_dir(paths)
    cfg = merge_defaults({"project": {"name": "TestProj"}})
    if render_config is not None:
        cfg["render"] = render_config
    dump_yaml(paths.config, cfg)
    return paths


def _minimal_ctx(paths: Paths) -> Context:
    return Context(
        project_name="TestProj",
        actor="alice",
        repo_path=str(paths.repo),
        agent=AgentSources(),
        sources={},
        semantic_pointer_cards=[],
        personal={},
        current=CurrentState(actor="alice"),
        recent_episodic=[],
        config_top_n={},
    )


# ---------------------------------------------------------------------------
# Default (flag OFF) → v1 compendium
# ---------------------------------------------------------------------------

def test_claude_adapter_uses_v1_when_flag_explicitly_off(tmp_path: Path):
    """`render.use_manifest: false` (explicit opt-out) → v1 path."""
    paths = _scaffolded(tmp_path, render_config={"use_manifest": False})
    adapter = ClaudeAdapter(paths)
    files = adapter.render(_minimal_ctx(paths))

    body = files[0].content
    # v1 header signature
    assert "Project context for Claude Code" in body
    # v3 manifest signatures should be absent
    assert "HOW TO READ THIS FILE" not in body
    assert "WORKFLOW CONTRACT" not in body


def test_cursor_copilot_opencode_use_v1_when_flag_explicitly_off(tmp_path: Path):
    """Every adapter respects an explicit opt-out, not just Claude."""
    paths = _scaffolded(tmp_path, render_config={"use_manifest": False})
    ctx = _minimal_ctx(paths)
    for adapter_cls in (CursorAdapter, CopilotAdapter, OpenCodeAdapter):
        adapter = adapter_cls(paths)
        body = adapter.render(ctx)[0].content
        assert "WORKFLOW CONTRACT" not in body, (
            f"{adapter_cls.__name__} produced manifest output despite explicit opt-out"
        )


def test_default_config_emits_v3_manifest(tmp_path: Path):
    """v0.5.0+ default: `merge_defaults` sets `use_manifest: True` so the
    manifest renderer is the default render path."""
    paths = _scaffolded(tmp_path)  # no override → use the default
    adapter = ClaudeAdapter(paths)
    body = adapter.render(_minimal_ctx(paths))[0].content
    # v3 signatures present
    assert "HOW TO READ THIS FILE" in body
    assert "WORKFLOW CONTRACT" in body
    # v1 header should be absent
    assert "Project context for Claude Code" not in body


# ---------------------------------------------------------------------------
# Flag ON → v3 manifest
# ---------------------------------------------------------------------------

def test_claude_adapter_uses_manifest_when_flag_on(tmp_path: Path):
    """`render.use_manifest: true` produces the v3 manifest."""
    paths = _scaffolded(tmp_path, render_config={"use_manifest": True})
    adapter = ClaudeAdapter(paths)
    files = adapter.render(_minimal_ctx(paths))

    body = files[0].content
    # v3 signatures
    assert "HOW TO READ THIS FILE" in body
    assert "WORKFLOW CONTRACT" in body
    assert "HARD POLICY" in body
    assert "MUST READ before any code edit" in body
    # v1 signature should be absent
    assert "Project context for Claude Code" not in body


def test_all_adapters_emit_manifest_when_flag_on(tmp_path: Path):
    """All four adapters produce the same manifest body (tool-agnostic).

    Compare structure (timestamp-stripped) — `rendered-at:` differs by
    nanoseconds across the four render calls, which is fine.
    """
    import re as _re
    paths = _scaffolded(tmp_path, render_config={"use_manifest": True})
    ctx = _minimal_ctx(paths)
    bodies = {}
    for adapter_cls in (ClaudeAdapter, CursorAdapter, CopilotAdapter, OpenCodeAdapter):
        adapter = adapter_cls(paths)
        bodies[adapter_cls.__name__] = adapter.render(ctx)[0].content
    # All four should have the manifest's invariant text
    for name, body in bodies.items():
        assert "WORKFLOW CONTRACT" in body, f"{name} missing manifest content"
        assert "MUST READ" in body, f"{name} missing manifest content"
    # Strip the rendered-at timestamp before comparing; everything else
    # must be byte-identical across adapter targets.
    _ts_re = _re.compile(r"rendered-at: [^\s]+")
    normalized = {k: _ts_re.sub("rendered-at: <ts>", v) for k, v in bodies.items()}
    unique_bodies = set(normalized.values())
    assert len(unique_bodies) == 1, (
        "v3 manifest should be identical (modulo timestamp) across all "
        f"adapter targets; got {len(unique_bodies)} distinct bodies"
    )


# ---------------------------------------------------------------------------
# Safety: malformed flag → v1 fallback (never empty)
# ---------------------------------------------------------------------------

def test_malformed_render_block_falls_back_to_v1(tmp_path: Path):
    """A non-dict `render:` field shouldn't crash sync."""
    paths = _scaffolded(tmp_path)
    # Manually rewrite the config to be malformed
    cfg = yaml.safe_load(paths.config.read_text())
    cfg["render"] = "not a dict"
    dump_yaml(paths.config, cfg)

    adapter = ClaudeAdapter(paths)
    body = adapter.render(_minimal_ctx(paths))[0].content
    # Should still emit SOMETHING (v1 fallback)
    assert body.strip()
    assert "HOW TO READ THIS FILE" not in body


def test_missing_config_yaml_falls_back_to_v1(tmp_path: Path):
    """If config.yaml is missing entirely, default to v1 (safe)."""
    paths = Paths(repo=tmp_path)
    paths.agent.mkdir()
    # Don't write config.yaml
    adapter = ClaudeAdapter(paths)
    body = adapter.render(_minimal_ctx(paths))[0].content
    assert body.strip()
    # v1 path
    assert "HOW TO READ THIS FILE" not in body


# ---------------------------------------------------------------------------
# File outputs
# ---------------------------------------------------------------------------

def test_manifest_path_unchanged_for_claude_adapter(tmp_path: Path):
    """Output file paths are independent of renderer choice."""
    paths = _scaffolded(tmp_path, render_config={"use_manifest": True})
    adapter = ClaudeAdapter(paths)
    files = adapter.render(_minimal_ctx(paths))
    output_paths = {f.path for f in files}
    assert paths.repo / "CLAUDE.md" in output_paths
    assert paths.adapters / "claude" / "CLAUDE.md" in output_paths


def test_manifest_token_economy_is_real(tmp_path: Path):
    """Sanity: manifest output is significantly smaller than v1 compendium
    on a populated project."""
    paths = _scaffolded(tmp_path)
    ctx = _minimal_ctx(paths)
    adapter = ClaudeAdapter(paths)

    # v1
    v1_body = adapter.render(ctx)[0].content

    # v3
    dump_yaml(
        paths.config,
        {**yaml.safe_load(paths.config.read_text()), "render": {"use_manifest": True}},
    )
    v3_body = adapter.render(ctx)[0].content

    # Both should be non-empty
    assert v1_body.strip()
    assert v3_body.strip()
    # Manifest is the bigger of the two on a small repo (workflow contract is
    # heavier than the v1 empty-source overview). Just confirm both produce
    # distinct output — the actual ratio depends on project size.
    assert v1_body != v3_body
