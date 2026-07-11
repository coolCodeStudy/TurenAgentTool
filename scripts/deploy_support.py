from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
        """Run a command and return its captured result."""


class SubprocessRunner:
    def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
