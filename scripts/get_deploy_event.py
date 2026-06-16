#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp import repository


def main() -> None:
    parser = argparse.ArgumentParser(description="Read an InvestmentKnowledge deployment event.")
    parser.add_argument("id", type=int)
    args = parser.parse_args()

    row = repository.get_deploy_event(args.id)
    print(json.dumps(row, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
