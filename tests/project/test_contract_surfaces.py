"""Tests for the contract `## Surfaces` section (v0.5.3 — dotgraph integration).

Three guarantees:

1. The scaffold emits the Surfaces block (template + parser agree).
2. `parse_surfaces` round-trips real values without dropping them; missing
   top-level keys parse as empty arrays.
3. The score JSON gains `surfaces_enumerated` + `surfaces_present` fields;
   placeholders count as zero.
4. The Surfaces YAML survives `contract round` (it's BEFORE the
   negotiation-log anchor, so it's part of the content hash).
5. Old contracts without a Surfaces section continue to validate and score.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from dotagent.commands.contract_cmd import contract_group
from dotagent.project.contract import (
    SURFACES_SCHEMA,
    count_surfaces,
    extract_surfaces_block,
    init_contract,
    parse_surfaces,
    validate_contract,
)
from dotagent.project.model import save_module

from ._helpers import make_project_with_module, setup_repo


# ---------------------------------------------------------------------------
# 1. Scaffold emits the Surfaces section
# ---------------------------------------------------------------------------

def test_scaffold_includes_surfaces_anchor_and_fenced_yaml(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    body = (paths.repo / module.current_cycle.contract.path).read_text()

    assert "<!-- anchor: surfaces -->" in body
    assert "## Surfaces" in body
    raw_yaml = extract_surfaces_block(body)
    assert raw_yaml.strip(), "fenced YAML block must be present in the scaffold"
    # The YAML body should have the canonical top-level keys.
    for key in ("surfaces:", "code:", "data:", "tables:", "redis_keys:",
                "kafka_topics:", "collections:",
                "callers_to_update:", "tests_to_update:"):
        assert key in raw_yaml, f"scaffold yaml missing '{key}'"


# ---------------------------------------------------------------------------
# 2. parse_surfaces — round-trip and tolerance
# ---------------------------------------------------------------------------

_FULL_YAML = """\
surfaces:
  code:
    - id: function:src/auth.py:42:login
      why: change return shape
    - id: class:src/auth.py:80:AuthService
      why: add tenant claim
  data:
    tables:
      - users
      - sessions
    columns:
      - users.tenant_id
    redis_keys:
      - "session:*"
    kafka_topics:
      - auth.login.v1
    collections: []
  callers_to_update:
    - id: function:src/api/handlers.py:21:handleLogin
      reason: signature change
  tests_to_update:
    - tests/test_auth.py
    - test:tests/test_auth.py:42:test_login_returns_token
"""


def test_parse_full_yaml_returns_canonical_shape():
    fenced = f"<!-- anchor: surfaces -->\n## Surfaces\n```yaml\n{_FULL_YAML}```\n"
    s = parse_surfaces(fenced)
    assert len(s["code"]) == 2
    assert s["code"][0]["id"] == "function:src/auth.py:42:login"
    assert s["data"]["tables"] == ["users", "sessions"]
    assert s["data"]["columns"] == ["users.tenant_id"]
    assert s["data"]["redis_keys"] == ["session:*"]
    assert s["data"]["kafka_topics"] == ["auth.login.v1"]
    assert s["data"]["collections"] == []
    assert len(s["callers_to_update"]) == 1
    assert s["tests_to_update"] == [
        "tests/test_auth.py",
        "test:tests/test_auth.py:42:test_login_returns_token",
    ]


def test_parse_returns_empty_schema_when_section_absent():
    s = parse_surfaces("# A contract\n\nNo surfaces here.")
    assert s == {
        "code": [],
        "data": {k: [] for k in SURFACES_SCHEMA["data"]},
        "callers_to_update": [],
        "tests_to_update": [],
    }


def test_parse_tolerates_missing_top_level_keys():
    # Only `code` declared; everything else defaults to empty.
    yaml_str = "surfaces:\n  code:\n    - id: function:foo:1:bar\n      why: x\n"
    fenced = f"<!-- anchor: surfaces -->\n## Surfaces\n```yaml\n{yaml_str}```\n"
    s = parse_surfaces(fenced)
    assert len(s["code"]) == 1
    assert s["data"] == {k: [] for k in SURFACES_SCHEMA["data"]}
    assert s["callers_to_update"] == []
    assert s["tests_to_update"] == []


def test_parse_tolerates_malformed_yaml():
    fenced = "<!-- anchor: surfaces -->\n## Surfaces\n```yaml\n: not [yaml at all\n```\n"
    s = parse_surfaces(fenced)
    # No exception, empty schema returned.
    assert s["code"] == []
    assert s["data"]["tables"] == []


def test_parse_tolerates_missing_surfaces_root_key():
    # Has a fenced yaml block but no `surfaces:` root — must not crash.
    fenced = "<!-- anchor: surfaces -->\n## Surfaces\n```yaml\nrandom: value\n```\n"
    s = parse_surfaces(fenced)
    assert s["code"] == []


# ---------------------------------------------------------------------------
# 3. count_surfaces — placeholders excluded
# ---------------------------------------------------------------------------

def test_count_excludes_placeholder_entries(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    body = (paths.repo / module.current_cycle.contract.path).read_text()
    # Fresh scaffold uses `<dotgraph_node_id>` etc. → count is 0.
    assert count_surfaces(body) == 0


def test_count_real_entries(tmp_path: Path):
    fenced = f"<!-- anchor: surfaces -->\n## Surfaces\n```yaml\n{_FULL_YAML}```\n"
    # 2 code + 2 tables + 1 column + 1 redis + 1 kafka + 0 collections
    # + 1 caller + 2 tests = 10
    assert count_surfaces(fenced) == 10


def test_count_mixed_placeholder_and_real():
    yaml_str = (
        "surfaces:\n"
        "  code:\n"
        "    - id: <dotgraph_node_id>\n"
        "      why: <short reason>\n"
        "    - id: function:src/real.py:1:real\n"
        "      why: actual change\n"
        "  data:\n"
        "    tables: [orders, payments]\n"
        "    redis_keys: []\n"
        "    kafka_topics: []\n"
        "    collections: []\n"
        "    columns: []\n"
    )
    fenced = f"<!-- anchor: surfaces -->\n## Surfaces\n```yaml\n{yaml_str}```\n"
    # 1 real code (placeholder dropped) + 2 tables = 3
    assert count_surfaces(fenced) == 3


# ---------------------------------------------------------------------------
# 4. score --json emits surfaces fields
# ---------------------------------------------------------------------------

def test_score_json_includes_surfaces_fields_zero_when_placeholder(
    tmp_path: Path, monkeypatch
):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    save_module(paths, module)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(contract_group, ["score", module.id, "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "surfaces_enumerated" in payload
    assert "surfaces_present" in payload
    assert payload["surfaces_enumerated"] == 0
    assert payload["surfaces_present"] is False


def test_score_json_reflects_real_surfaces_when_populated(
    tmp_path: Path, monkeypatch
):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    save_module(paths, module)

    # Replace the placeholder Surfaces block with real entries.
    contract_path = paths.repo / module.current_cycle.contract.path
    original = contract_path.read_text()
    fenced_real = (
        "```yaml\n"
        "surfaces:\n"
        "  code:\n"
        "    - id: function:src/auth.py:42:login\n"
        "      why: tenant claim\n"
        "  data:\n"
        "    tables: [users]\n"
        "    columns: []\n"
        "    redis_keys: []\n"
        "    kafka_topics: []\n"
        "    collections: []\n"
        "  callers_to_update: []\n"
        "  tests_to_update: [tests/test_auth.py]\n"
        "```"
    )
    # Replace the scaffolded fenced block with the populated one.
    import re
    new = re.sub(
        r"```yaml\s*\n.*?\n```",
        fenced_real,
        original,
        count=1,
        flags=re.DOTALL,
    )
    contract_path.write_text(new)

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(contract_group, ["score", module.id, "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    # 1 code + 1 table + 1 test = 3
    assert payload["surfaces_enumerated"] == 3
    assert payload["surfaces_present"] is True


# ---------------------------------------------------------------------------
# 5. Backward compatibility — old contracts without Surfaces still validate
# ---------------------------------------------------------------------------

def test_old_contract_without_surfaces_still_validates(tmp_path: Path):
    paths = setup_repo(tmp_path)
    _, module = make_project_with_module(paths)
    init_contract(paths, module)
    contract_path = paths.repo / module.current_cycle.contract.path
    original = contract_path.read_text()

    # Strip the entire Surfaces section to simulate a pre-v0.5.3 contract.
    import re
    stripped = re.sub(
        r"<!-- anchor: surfaces -->.*?(?=<!-- anchor: negotiation-log -->)",
        "",
        original,
        flags=re.DOTALL,
    )
    assert "<!-- anchor: surfaces -->" not in stripped
    contract_path.write_text(stripped)

    # Validator must still report OK — Surfaces is OPTIONAL, not in SECTION_ANCHORS.
    result = validate_contract(contract_path)
    assert result.ok, f"old contract should still validate: {result.violations}"
    # And count_surfaces returns 0 without crashing.
    assert count_surfaces(stripped) == 0


# ---------------------------------------------------------------------------
# 6. Diff preservation — Surfaces is before negotiation-log
# ---------------------------------------------------------------------------

def test_surfaces_block_is_part_of_content_hash(tmp_path: Path):
    """Surfaces is BEFORE `<!-- anchor: negotiation-log -->`, so changes to it
    affect the content hash. Convergence works correctly: same Surfaces =
    same hash; different Surfaces = different hash."""
    from dotagent.project.contract import _content_hash_text

    fenced_a = (
        "```yaml\n"
        "surfaces:\n"
        "  code:\n"
        "    - id: function:src/foo.py:1:foo\n"
        "      why: A\n"
        "```"
    )
    fenced_b = (
        "```yaml\n"
        "surfaces:\n"
        "  code:\n"
        "    - id: function:src/foo.py:1:foo\n"
        "      why: B (different)\n"
        "```"
    )
    body_a = (
        f"<!-- anchor: surfaces -->\n## Surfaces\n{fenced_a}\n"
        "<!-- anchor: negotiation-log -->\n## Negotiation log\n- Round 1\n"
    )
    body_b = (
        f"<!-- anchor: surfaces -->\n## Surfaces\n{fenced_b}\n"
        "<!-- anchor: negotiation-log -->\n## Negotiation log\n- Round 1\n"
    )
    assert _content_hash_text(body_a) != _content_hash_text(body_b)

    # And same body with a different negotiation log = SAME hash.
    body_a2 = (
        f"<!-- anchor: surfaces -->\n## Surfaces\n{fenced_a}\n"
        "<!-- anchor: negotiation-log -->\n## Negotiation log\n- Different log line\n"
    )
    assert _content_hash_text(body_a) == _content_hash_text(body_a2)
