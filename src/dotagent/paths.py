from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

AGENT_DIR_NAME = ".agent"


@dataclass(frozen=True)
class Paths:
    """Canonical paths inside a project's .agent/ folder."""

    repo: Path

    @property
    def agent(self) -> Path:
        return self.repo / AGENT_DIR_NAME

    @property
    def config(self) -> Path:
        return self.agent / "config.yaml"

    @property
    def identity_dir(self) -> Path:
        return self.agent / "identity"

    @property
    def developers(self) -> Path:
        return self.identity_dir / "developers.yaml"

    @property
    def tools(self) -> Path:
        return self.identity_dir / "tools.yaml"

    @property
    def memory(self) -> Path:
        return self.agent / "memory"

    @property
    def working(self) -> Path:
        return self.memory / "working"

    @property
    def episodic(self) -> Path:
        return self.memory / "episodic"

    @property
    def semantic(self) -> Path:
        return self.memory / "semantic"

    @property
    def personal(self) -> Path:
        return self.memory / "personal"

    @property
    def dream(self) -> Path:
        return self.agent / "dream"

    @property
    def cache(self) -> Path:
        return self.agent / ".cache"

    @property
    def adapters(self) -> Path:
        return self.agent / "adapters"

    @property
    def skills(self) -> Path:
        return self.agent / "skills"

    @property
    def tools_dir(self) -> Path:
        return self.agent / "tools"

    @property
    def style(self) -> Path:
        return self.agent / "style.md"

    @property
    def rules(self) -> Path:
        return self.agent / "rules.md"

    @property
    def architecture(self) -> Path:
        return self.agent / "architecture.md"

    @property
    def patterns(self) -> Path:
        return self.agent / "patterns.md"

    @property
    def preferences(self) -> Path:
        return self.agent / "preferences.md"

    @property
    def sources_cache(self) -> Path:
        return self.cache / "sources.json"

    @property
    def semantic_sources(self) -> Path:
        return self.semantic / "sources"

    @property
    def working_current(self) -> Path:
        return self.working / "current"

    @property
    def cache_gitignore(self) -> Path:
        return self.cache / ".gitignore"

    @property
    def imported(self) -> Path:
        """Directory where pre-existing AI-tool configs are backed up before overwrite."""
        return self.agent / ".imported"


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up until we hit a git repo or an existing .agent/. Default cwd."""
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".git").exists() or (parent / AGENT_DIR_NAME).is_dir():
            return parent
    return cur


def user_config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "dotagent"


def user_identity_path() -> Path:
    return user_config_dir() / "identity.yaml"
