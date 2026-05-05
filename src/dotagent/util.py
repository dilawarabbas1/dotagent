from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class CmdResult:
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def run(cmd: list[str], cwd: Path | None = None, check: bool = False) -> CmdResult:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    res = CmdResult(proc.returncode, proc.stdout.strip(), proc.stderr.strip())
    if check and not res.ok:
        raise RuntimeError(f"{cmd!r} failed: {res.stderr or res.stdout}")
    return res


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


def load_yaml(p: Path) -> dict:
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text()) or {}


def dump_yaml(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


def write_text(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def slugify(s: str) -> str:
    out: list[str] = []
    prev_dash = False
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")
