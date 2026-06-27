from __future__ import annotations

import os
from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_STATUS_LINES = 40


def main() -> None:
    print("# Agent Preflight")
    print()
    _print_git_status()
    _print_database_target()
    _print_daily_log_policy()
    _print_file_excerpt("AGENTS.md", max_lines=80)
    _print_file_excerpt("docs/agent-lessons.md", max_lines=120)


def _print_git_status() -> None:
    print("## Git Status")
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        print(f"- unable to run git status: {exc}")
        print()
        return

    output = result.stdout.strip()
    if output:
        lines = output.splitlines()
        for line in lines[:MAX_STATUS_LINES]:
            print(f"- {line}")
        if len(lines) > MAX_STATUS_LINES:
            print(f"- ... {len(lines) - MAX_STATUS_LINES} more entries not shown ...")
        print(f"- total changed/untracked entries: {len(lines)}")
    else:
        print("- clean")
    print()


def _print_database_target() -> None:
    host = os.environ.get("POSTGRES_HOST") or "localhost"
    port = os.environ.get("POSTGRES_PORT") or "55432"
    database = os.environ.get("POSTGRES_DB") or "investment_kg"
    print("## Database Target")
    print(f"- POSTGRES_HOST={host}")
    print(f"- POSTGRES_PORT={port}")
    print(f"- POSTGRES_DB={database}")
    print("- Verify this target before running services or write commands.")
    print()


def _print_daily_log_policy() -> None:
    daily_log_dir = PROJECT_ROOT / "docs/每日工作记录"
    print("## Daily Log Policy")
    if not daily_log_dir.exists():
        print("- routine daily-log directory not present")
        print()
        return

    files = sorted(path for path in daily_log_dir.rglob("*") if path.is_file())
    if not files:
        print("- routine daily-log directory exists but contains no files")
        print()
        return

    print("- routine daily-log files are present and should not be kept by default")
    for path in files[:5]:
        print(f"- {path.relative_to(PROJECT_ROOT)}")
    if len(files) > 5:
        print(f"- ... {len(files) - 5} more entries not shown ...")
    print("- move durable content to durable docs or remove files you created")
    print()


def _print_file_excerpt(relative_path: str, *, max_lines: int) -> None:
    path = PROJECT_ROOT / relative_path
    title = relative_path
    print(f"## {title}")
    if not path.exists():
        print("- missing")
        print()
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines[:max_lines]:
        print(line)
    if len(lines) > max_lines:
        print(f"... truncated after {max_lines} lines ...")
    print()


if __name__ == "__main__":
    main()
