"""Tests for `dotagent doc-coverage` — the read-only doc checklist CLI.

Coverage:
1. parse_fm_index — extracts file→FM-### mapping from feature_master/*.md
2. doc_coverage   — applies HARD/SUGGESTED/CHECK severities correctly
3. CLI            — json/text/markdown formats, --severity filter, errors
4. Boundary       — the command NEVER writes to disk
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from click.testing import CliRunner

from dotagent.commands.doc_coverage_cmd import doc_coverage_cmd
from dotagent.coverage import (
    SEVERITY_CHECK,
    SEVERITY_HARD,
    SEVERITY_SUGGESTED,
    doc_coverage,
    parse_fm_index,
    parse_fm_index_multi,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".agent").mkdir(parents=True)
    (repo / "docs" / "feature_master").mkdir(parents=True)
    return repo


def _write_fm(repo: Path, fm_id: str, slug: str, files: list[str]) -> Path:
    bullet_lines = "\n".join(f"- `{p}`" for p in files)
    body = (
        f"# {fm_id} — {slug}\n\n"
        f"## contract\nWhat it does.\n\n"
        f"## design\nWhy.\n\n"
        f"## files\n{bullet_lines}\n\n"
        f"## invariants\n- AP-001: must X\n"
    )
    target = repo / "docs" / "feature_master" / f"{fm_id}-{slug}.md"
    target.write_text(body)
    return target


# ---------------------------------------------------------------------------
# parse_fm_index — single FM
# ---------------------------------------------------------------------------

def test_parse_fm_index_extracts_files_section(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-014", "auth", [
        "src/auth.py", "src/db/users.py", "src/api/auth.ts",
    ])
    fm_map = parse_fm_index(repo)
    assert fm_map["src/auth.py"] == "FM-014"
    assert fm_map["src/db/users.py"] == "FM-014"
    assert fm_map["src/api/auth.ts"] == "FM-014"


def test_parse_fm_index_no_dir_returns_empty(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert parse_fm_index(repo) == {}


def test_parse_fm_index_skips_tokens_without_path_shape(tmp_path: Path):
    """Backtick tokens that don't look like paths (e.g. table names) skip."""
    repo = _init_repo(tmp_path)
    body = (
        "# FM-001 — billing\n\n"
        "## files\n"
        "- `src/billing.py`\n"
        "- table: `users` (not a file path)\n"
        "- env: `DB_URL` (not a file path)\n"
    )
    (repo / "docs" / "feature_master" / "FM-001-billing.md").write_text(body)
    fm_map = parse_fm_index(repo)
    assert "src/billing.py" in fm_map
    assert "users" not in fm_map
    assert "DB_URL" not in fm_map


def test_parse_fm_index_stops_at_next_heading(tmp_path: Path):
    """Backtick paths under later headings are NOT mapped to this FM."""
    repo = _init_repo(tmp_path)
    body = (
        "# FM-007\n\n"
        "## files\n"
        "- `src/should_match.py`\n\n"
        "## invariants\n"
        "- `src/should_not_match.py` is read-only\n"
    )
    (repo / "docs" / "feature_master" / "FM-007-foo.md").write_text(body)
    fm_map = parse_fm_index(repo)
    assert "src/should_match.py" in fm_map
    assert "src/should_not_match.py" not in fm_map


def test_parse_fm_index_tolerates_case_variants(tmp_path: Path):
    """`## Files`, `## files:`, `### files` all parse."""
    repo = _init_repo(tmp_path)
    for fm_id, heading in (
        ("FM-100", "## Files"),
        ("FM-101", "## files:"),
        ("FM-102", "### files"),
    ):
        body = f"# {fm_id}\n\n{heading}\n- `src/{fm_id}.py`\n"
        (repo / "docs" / "feature_master" / f"{fm_id}-x.md").write_text(body)
    fm_map = parse_fm_index(repo)
    assert "src/FM-100.py" in fm_map
    assert "src/FM-101.py" in fm_map
    assert "src/FM-102.py" in fm_map


# ---------------------------------------------------------------------------
# parse_fm_index_multi — multiple FMs claiming the same file
# ---------------------------------------------------------------------------

def test_parse_fm_index_multi_collects_all_claimants(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-014", "auth", ["src/shared.py"])
    _write_fm(repo, "FM-027", "tenancy", ["src/shared.py"])
    fm_map = parse_fm_index_multi(repo)
    assert set(fm_map["src/shared.py"]) == {"FM-014", "FM-027"}


# ---------------------------------------------------------------------------
# doc_coverage — HARD severity (FM-### claimed)
# ---------------------------------------------------------------------------

def test_doc_coverage_hard_match_when_file_in_fm(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-014", "auth", ["src/auth.py"])
    report = doc_coverage(repo, ["src/auth.py"])
    cov = report.files[0]
    assert cov.fm_ids == ["FM-014"]
    hards = [d for d in cov.required_docs if d.severity == SEVERITY_HARD]
    assert hards, "must have HARD entry pointing at the FM-### record"
    assert any("FM-014" in d.path for d in hards)


def test_doc_coverage_unmapped_when_no_fm_claims_file(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-014", "auth", ["src/auth.py"])
    report = doc_coverage(repo, ["src/unrelated.py"])
    assert "src/unrelated.py" in report.unmapped_files
    cov = report.files[0]
    assert cov.fm_ids == []
    # No HARD entries — only heuristics + CHECK
    assert not any(d.severity == SEVERITY_HARD for d in cov.required_docs)


# ---------------------------------------------------------------------------
# doc_coverage — SUGGESTED severity (heuristics)
# ---------------------------------------------------------------------------

def test_heuristic_db_path_suggests_all_three_shards(tmp_path: Path):
    repo = _init_repo(tmp_path)
    report = doc_coverage(repo, ["src/db/users.py"])
    suggested = [d.path for d in report.files[0].required_docs
                 if d.severity == SEVERITY_SUGGESTED]
    for shard in ("master", "tenant", "vector"):
        assert f"docs/db-impact-map-{shard}.md" in suggested


def test_heuristic_redis_path_suggests_all_three_scopes(tmp_path: Path):
    repo = _init_repo(tmp_path)
    report = doc_coverage(repo, ["src/redis/keys.py"])
    suggested = [d.path for d in report.files[0].required_docs
                 if d.severity == SEVERITY_SUGGESTED]
    for scope in ("tenant", "global", "events"):
        assert f"docs/redis-key-registry-{scope}.md" in suggested


def test_heuristic_route_path_suggests_fm_files_section(tmp_path: Path):
    repo = _init_repo(tmp_path)
    report = doc_coverage(repo, ["src/api/auth.ts"])
    suggested = [d for d in report.files[0].required_docs
                 if d.severity == SEVERITY_SUGGESTED]
    assert any("FM-###-<slug>.md" in d.path for d in suggested)


def test_heuristic_host_file_suggests_ops_service_registry(tmp_path: Path):
    repo = _init_repo(tmp_path)
    report = doc_coverage(repo, ["ecosystem.config.js"])
    suggested = [d.path for d in report.files[0].required_docs
                 if d.severity == SEVERITY_SUGGESTED]
    assert "docs/ops/service-registry.md" in suggested


# ---------------------------------------------------------------------------
# doc_coverage — CHECK severity (always-applicable)
# ---------------------------------------------------------------------------

def test_check_anti_patterns_always_present(tmp_path: Path):
    repo = _init_repo(tmp_path)
    report = doc_coverage(repo, ["any/file.py"])
    paths = [d.path for d in report.files[0].required_docs
             if d.severity == SEVERITY_CHECK]
    assert "docs/anti-patterns.md" in paths


def test_bug_commit_msg_adds_matching_bug_registry(tmp_path: Path):
    repo = _init_repo(tmp_path)
    report = doc_coverage(
        repo, ["src/foo.py"], commit_msg="fix(DA-BUG-INFRA-042): refresh token"
    )
    paths = [d.path for d in report.files[0].required_docs
             if d.severity == SEVERITY_CHECK]
    assert "docs/bug-registry-infrastructure.md" in paths


def test_bug_commit_msg_with_agt_layer(tmp_path: Path):
    repo = _init_repo(tmp_path)
    report = doc_coverage(
        repo, ["src/foo.py"], commit_msg="DA-BUG-AGT-007"
    )
    paths = [d.path for d in report.files[0].required_docs
             if d.severity == SEVERITY_CHECK]
    assert "docs/bug-registry-agents.md" in paths


def test_non_bug_commit_does_not_add_bug_registry(tmp_path: Path):
    repo = _init_repo(tmp_path)
    report = doc_coverage(
        repo, ["src/foo.py"], commit_msg="feat: add caching"
    )
    paths = [d.path for d in report.files[0].required_docs]
    assert not any("bug-registry" in p for p in paths)


# ---------------------------------------------------------------------------
# Warnings + dedup
# ---------------------------------------------------------------------------

def test_warning_when_no_feature_master_present(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".agent").mkdir(parents=True)
    report = doc_coverage(repo, ["src/foo.py"])
    assert any("feature_master" in w for w in report.warnings)


def test_dedup_removes_duplicate_doc_paths(tmp_path: Path):
    """Two heuristics matching the same file shouldn't add the same doc twice."""
    repo = _init_repo(tmp_path)
    report = doc_coverage(repo, ["src/db/redis/users.py"])
    # This path matches both DB and Redis heuristics. Check no duplicates.
    paths_seen = [(d.path, d.severity) for d in report.files[0].required_docs]
    assert len(paths_seen) == len(set(paths_seen)), (
        f"duplicate entries in required_docs: {paths_seen}"
    )


# ---------------------------------------------------------------------------
# Glob support in files: section
# ---------------------------------------------------------------------------

def test_glob_in_fm_files_section_matches_concrete_path(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-300", "api", ["src/api/auth/*.ts"])
    report = doc_coverage(repo, ["src/api/auth/login.ts"])
    assert report.files[0].fm_ids == ["FM-300"]


def test_double_star_glob_matches_nested(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-301", "deep", ["src/deep/**.ts"])
    report = doc_coverage(repo, ["src/deep/nested/file.ts"])
    assert report.files[0].fm_ids == ["FM-301"]


# ---------------------------------------------------------------------------
# CLI — formats + flags
# ---------------------------------------------------------------------------

def _invoke(repo: Path, *args) -> object:
    cwd = os.getcwd()
    os.chdir(repo)
    try:
        return CliRunner().invoke(doc_coverage_cmd, list(args), catch_exceptions=False)
    finally:
        os.chdir(cwd)


def test_cli_json_format(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-001", "x", ["src/x.py"])
    result = _invoke(repo, "--files", "src/x.py", "--format", "json")
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["files"][0]["fm_ids"] == ["FM-001"]


def test_cli_text_format(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-001", "x", ["src/x.py"])
    result = _invoke(repo, "--files", "src/x.py", "--format", "text")
    assert result.exit_code == 0
    assert "src/x.py" in result.output
    assert "FM-001" in result.output


def test_cli_markdown_format(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-001", "x", ["src/x.py"])
    result = _invoke(repo, "--files", "src/x.py", "--format", "markdown")
    assert result.exit_code == 0
    assert "# Doc-coverage checklist" in result.output
    assert "`src/x.py`" in result.output


def test_cli_severity_filter_hard_excludes_check(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-001", "x", ["src/x.py"])
    result = _invoke(
        repo, "--files", "src/x.py", "--format", "json", "--severity", "hard",
    )
    payload = json.loads(result.output)
    severities = {d["severity"] for d in payload["files"][0]["required_docs"]}
    assert severities == {SEVERITY_HARD}, (
        f"severity=hard should keep only HARD, got {severities}"
    )


def test_cli_severity_filter_suggested_plus_hard(tmp_path: Path):
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-001", "x", ["src/db/x.py"])
    result = _invoke(
        repo, "--files", "src/db/x.py", "--format", "json",
        "--severity", "suggested+",
    )
    payload = json.loads(result.output)
    severities = {d["severity"] for d in payload["files"][0]["required_docs"]}
    assert SEVERITY_CHECK not in severities
    assert SEVERITY_HARD in severities or SEVERITY_SUGGESTED in severities


def test_cli_comma_and_newline_separated_files(tmp_path: Path):
    repo = _init_repo(tmp_path)
    result = _invoke(
        repo, "--files", "a.py,b.py\nc.py", "--format", "json",
    )
    payload = json.loads(result.output)
    paths = {f["path"] for f in payload["files"]}
    assert paths == {"a.py", "b.py", "c.py"}


def test_cli_errors_without_agent_dir(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    result = CliRunner().invoke(
        doc_coverage_cmd,
        ["--files", "a.py", "--repo", str(bare)],
    )
    assert result.exit_code != 0
    assert "No .agent" in result.output


def test_cli_errors_on_empty_files(tmp_path: Path):
    repo = _init_repo(tmp_path)
    result = _invoke(repo, "--files", "  ")
    assert result.exit_code != 0
    assert "No files supplied" in result.output


# ---------------------------------------------------------------------------
# Hard boundary — never writes
# ---------------------------------------------------------------------------

def test_doc_coverage_never_writes_anything(tmp_path: Path):
    """The CLI is read-only. Snapshot the FS before and after; assert
    nothing changed."""
    repo = _init_repo(tmp_path)
    _write_fm(repo, "FM-014", "auth", ["src/auth.py"])
    # Snapshot file mtimes + contents
    snapshot: dict[Path, tuple[float, str]] = {}
    for p in repo.rglob("*"):
        if p.is_file():
            snapshot[p] = (p.stat().st_mtime, p.read_text())

    _invoke(repo, "--files", "src/auth.py,docs/feature_master/FM-014-auth.md",
            "--format", "json", "--commit-msg", "DA-BUG-INFRA-001")

    for p, (mtime, content) in snapshot.items():
        assert p.exists(), f"doc-coverage deleted {p}"
        assert p.read_text() == content, f"doc-coverage modified {p} content"
        assert p.stat().st_mtime == mtime, f"doc-coverage touched {p} mtime"

    # And no new files appeared.
    after = {p for p in repo.rglob("*") if p.is_file()}
    assert after == set(snapshot.keys()), (
        f"doc-coverage created new file(s): {after - set(snapshot.keys())}"
    )
