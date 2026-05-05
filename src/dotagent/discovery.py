from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .util import run


@dataclass
class Discovery:
    repo: Path
    languages: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    test_runners: list[str] = field(default_factory=list)
    linters: list[str] = field(default_factory=list)
    formatters: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    has_ci: bool = False
    has_docker: bool = False
    is_monorepo: bool = False
    existing_ai_configs: list[str] = field(default_factory=list)
    has_claude_code_optimization: bool = False
    git_log_summary: dict = field(default_factory=dict)
    readme_excerpt: str = ""


_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".cache", ".next", ".turbo"}
_EXT = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go",
    ".rs": "Rust", ".rb": "Ruby", ".java": "Java", ".kt": "Kotlin",
    ".swift": "Swift", ".php": "PHP", ".cs": "C#", ".c": "C",
    ".cpp": "C++", ".h": "C/C++", ".sh": "Shell",
}


def _detect_languages(repo: Path) -> list[str]:
    counts: dict[str, int] = {}
    for path in repo.rglob("*"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        lang = _EXT.get(path.suffix)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return [lang for lang, _ in sorted(counts.items(), key=lambda x: -x[1])][:5]


def _read_package_json(repo: Path) -> dict:
    p = repo / "package.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _detect_node(pkg: dict) -> tuple[list[str], list[str], list[str], list[str]]:
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    runners = [n for n in ("vitest", "jest", "mocha", "ava", "playwright") if n in deps]
    linters = [n for n in ("eslint", "biome", "tslint") if n in deps]
    formatters = [n for n in ("prettier", "biome") if n in deps]
    fw_map = {
        "next": "Next.js", "react": "React", "vue": "Vue", "svelte": "Svelte",
        "@angular/core": "Angular", "fastify": "Fastify", "express": "Express",
        "@nestjs/core": "NestJS", "vite": "Vite",
    }
    frameworks = [v for k, v in fw_map.items() if k in deps]
    return runners, linters, formatters, frameworks


def _detect_python(repo: Path) -> tuple[list[str], list[str], list[str], list[str]]:
    text = ""
    for n in ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "setup.cfg"):
        p = repo / n
        if p.exists():
            text += p.read_text(errors="ignore")
    text = text.lower()
    runners = [n for n in ("pytest", "unittest") if n in text]
    linters = [n for n in ("ruff", "flake8", "pylint", "mypy") if n in text]
    formatters = [n for n in ("black", "isort") if n in text]
    if "ruff" in text and "ruff" not in formatters:
        formatters.append("ruff")
    fw_map = {"fastapi": "FastAPI", "django": "Django", "flask": "Flask", "starlette": "Starlette", "tornado": "Tornado"}
    frameworks = [v for k, v in fw_map.items() if k in text]
    return runners, linters, formatters, frameworks


def _git_log_summary(repo: Path, n: int = 500) -> dict:
    if not (repo / ".git").exists():
        return {}
    log = run(["git", "log", f"-{n}", "--pretty=%H%x09%ae%x09%s"], cwd=repo)
    if not log.ok:
        return {}
    commits = []
    authors: dict[str, int] = {}
    revert_ct = 0
    fix_ct = 0
    for line in log.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        sha, email, subject = parts
        commits.append({"sha": sha, "email": email, "subject": subject})
        authors[email] = authors.get(email, 0) + 1
        s = subject.lower()
        if s.startswith("revert") or "revert " in s:
            revert_ct += 1
        if re.match(r"^(fix|bug|hotfix)[:!(]", s):
            fix_ct += 1
    return {
        "total": len(commits),
        "authors": authors,
        "revert_count": revert_ct,
        "fix_count": fix_ct,
        "recent": commits[:25],
    }


def _readme_excerpt(repo: Path, max_chars: int = 4000) -> str:
    for name in ("README.md", "README.rst", "README", "readme.md"):
        p = repo / name
        if p.exists():
            return p.read_text(errors="replace")[:max_chars]
    return ""


def _existing_ai_configs(repo: Path) -> list[str]:
    found: list[str] = []
    candidates = [
        ("claude", "CLAUDE.md"), ("claude", ".claude"),
        ("cursor", ".cursorrules"), ("cursor", ".cursor"),
        ("copilot", ".github/copilot-instructions.md"),
        ("opencode", "AGENTS.md"),
    ]
    for tool, rel in candidates:
        if (repo / rel).exists() and tool not in found:
            found.append(tool)
    return found


def _has_cco(repo: Path) -> bool:
    return any(
        (repo / p).exists()
        for p in (
            "docs/bug-registry.md", "docs/anti-patterns.md",
            ".claude/hooks/memory-guard.sh", ".claude/hooks/session-start.sh",
        )
    )


def discover(repo: Path) -> Discovery:
    d = Discovery(repo=repo)
    d.languages = _detect_languages(repo)

    if (repo / "package.json").exists():
        d.package_managers.append("npm")
        if (repo / "yarn.lock").exists():
            d.package_managers.append("yarn")
        if (repo / "pnpm-lock.yaml").exists():
            d.package_managers.append("pnpm")
        rs, ls, fmts, fws = _detect_node(_read_package_json(repo))
        d.test_runners.extend(rs); d.linters.extend(ls); d.formatters.extend(fmts); d.frameworks.extend(fws)

    if (repo / "pyproject.toml").exists() or (repo / "requirements.txt").exists():
        d.package_managers.append("pip")
        rs, ls, fmts, fws = _detect_python(repo)
        d.test_runners.extend(rs); d.linters.extend(ls); d.formatters.extend(fmts); d.frameworks.extend(fws)

    if (repo / "go.mod").exists():
        d.package_managers.append("go")
    if (repo / "Cargo.toml").exists():
        d.package_managers.append("cargo")

    d.has_ci = (repo / ".github" / "workflows").exists() or (repo / ".gitlab-ci.yml").exists() or (repo / "circle.yml").exists()
    d.has_docker = (repo / "Dockerfile").exists() or (repo / "docker-compose.yml").exists()
    d.is_monorepo = any((repo / x).exists() for x in ("packages", "apps", "services"))
    d.existing_ai_configs = _existing_ai_configs(repo)
    d.has_claude_code_optimization = _has_cco(repo)
    d.git_log_summary = _git_log_summary(repo)
    d.readme_excerpt = _readme_excerpt(repo)
    return d
