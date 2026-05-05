from __future__ import annotations

from pathlib import Path

from ..paths import Paths
from ..util import dump_yaml, load_yaml


class PersonalMemory:
    """Per-actor profile. Never merged across actors; never sent into other devs' adapter outputs."""

    def __init__(self, paths: Paths, actor: str) -> None:
        self.dir = paths.personal / actor
        self.profile = self.dir / "profile.yaml"

    def load(self) -> dict:
        return load_yaml(self.profile)

    def save(self, data: dict) -> None:
        dump_yaml(self.profile, data)

    def update(self, **kwargs) -> dict:
        data = self.load()
        data.update(kwargs)
        self.save(data)
        return data
