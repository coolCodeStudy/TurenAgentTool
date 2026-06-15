#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.db import run_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Record InvestmentKnowledge deployment events.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--source", default="local_codex")
    start.add_argument("--deploy-mode", default="quick")
    start.add_argument("--commit-sha")
    start.add_argument("--branch-name")
    start.add_argument("--summary")
    start.add_argument("--metadata-json")

    finish = subparsers.add_parser("finish")
    finish.add_argument("--id", type=int, required=True)
    finish.add_argument("--status", choices=["succeeded", "failed"], required=True)
    finish.add_argument("--summary")
    finish.add_argument("--logs-tail")
    finish.add_argument("--metadata-json")

    args = parser.parse_args()
    run_schema()

    if args.command == "start":
        row = repository.start_deploy_event(
            source=args.source,
            deploy_mode=args.deploy_mode,
            commit_sha=args.commit_sha,
            branch_name=args.branch_name,
            summary=args.summary,
            metadata=_metadata(args.metadata_json),
        )
    else:
        row = repository.finish_deploy_event(
            deploy_event_id=args.id,
            status=args.status,
            summary=args.summary,
            logs_tail=args.logs_tail,
            metadata=_metadata(args.metadata_json),
        )
    print(row["id"])


def _metadata(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("metadata JSON must be an object")
    return value


if __name__ == "__main__":
    main()
