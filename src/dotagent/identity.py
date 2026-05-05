from __future__ import annotations

import getpass
import socket
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .paths import Paths, user_identity_path
from .util import dump_yaml, load_yaml, run, slugify


@dataclass
class Identity:
    id: str
    name: str
    emails: list[str] = field(default_factory=list)
    github: str | None = None
    gitlab: str | None = None
    default_tool: str = "claude_code"
    role: str = "contributor"

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "name": self.name,
            "emails": self.emails,
            "default_tool": self.default_tool,
            "role": self.role,
        }
        if self.github:
            d["github"] = self.github
        if self.gitlab:
            d["gitlab"] = self.gitlab
        return d


def detect_from_git(repo: Path) -> Identity | None:
    email = run(["git", "config", "user.email"], cwd=repo).stdout
    name = run(["git", "config", "user.name"], cwd=repo).stdout
    if not email and not name:
        return None
    name = name or (email.split("@", 1)[0] if email else "")
    base_id = slugify(email.split("@", 1)[0]) if email else slugify(name)
    return Identity(
        id=base_id or "anonymous",
        name=name or "Anonymous",
        emails=[email] if email else [],
    )


def load_user_identity() -> Identity | None:
    data = load_yaml(user_identity_path())
    if not data:
        return None
    return Identity(
        id=data["id"],
        name=data.get("name", data["id"]),
        emails=data.get("emails", []),
        github=data.get("github"),
        gitlab=data.get("gitlab"),
        default_tool=data.get("default_tool", "claude_code"),
        role=data.get("role", "contributor"),
    )


def save_user_identity(identity: Identity) -> None:
    dump_yaml(user_identity_path(), identity.to_dict())


def resolve(repo: Path) -> Identity:
    """User-level identity wins; fall back to git-detected; last resort: hostname/user."""
    user = load_user_identity()
    if user:
        return user
    detected = detect_from_git(repo)
    if detected:
        return detected
    return Identity(
        id=slugify(getpass.getuser()) or "anonymous",
        name=getpass.getuser() or "Anonymous",
        emails=[],
    )


def host() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def upsert_developer(paths: Paths, identity: Identity) -> None:
    """Add/update the developer entry in .agent/identity/developers.yaml."""
    devs = load_yaml(paths.developers) or {"developers": []}
    roster = devs.setdefault("developers", [])
    for dev in roster:
        if dev.get("id") == identity.id:
            existing = set(dev.get("emails") or [])
            for e in identity.emails:
                if e not in existing:
                    dev.setdefault("emails", []).append(e)
            dev["name"] = dev.get("name") or identity.name
            break
    else:
        roster.append(identity.to_dict())
    dump_yaml(paths.developers, devs)
