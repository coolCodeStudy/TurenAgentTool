from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillCheck:
    exit_code: int
    message: str


def check_skill(source: Path, destination: Path) -> SkillCheck:
    if not destination.is_file():
        return SkillCheck(1, "local skill is missing")
    if source.read_bytes() != destination.read_bytes():
        return SkillCheck(1, "local skill is stale")
    return SkillCheck(0, "local skill matches tracked source")


def install_skill(source: Path, destination: Path) -> SkillCheck:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    return SkillCheck(0, "local skill installed from tracked source")


def default_destination() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return codex_home / "skills" / "architecture-code-health" / "SKILL.md"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether the local Architecture & Code Health skill matches Git.")
    parser.add_argument("--source", type=Path, default=Path("skills/architecture-code-health/SKILL.md"))
    parser.add_argument("--destination", type=Path, default=default_destination())
    parser.add_argument("--install", action="store_true", help="Copy the tracked skill to the local Codex skill directory.")
    args = parser.parse_args()
    result = install_skill(args.source, args.destination) if args.install else check_skill(args.source, args.destination)
    print(result.message)
    raise SystemExit(result.exit_code)


if __name__ == "__main__":
    main()
