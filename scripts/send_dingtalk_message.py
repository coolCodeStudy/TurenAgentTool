from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.command_router import handle_command
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.dingtalk_sender import send_text_message


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a text message to a DingTalk custom robot.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message", help="Message text to send.")
    group.add_argument("--command", help="InvestmentKnowledge command to run and send.")
    args = parser.parse_args()

    if args.command:
        run_schema()
        result = handle_command(
            args.command,
            output_dir=PROJECT_ROOT / "drafts",
            include_artifact_path=False,
        )
        content = result.message
        if not result.ok:
            raise SystemExit(content)
    else:
        content = args.message

    response = send_text_message(content)
    print(f"DingTalk message sent: {response}")


if __name__ == "__main__":
    main()
