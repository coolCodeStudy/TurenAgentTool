from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.db import run_schema


def main() -> None:
    run_schema()
    print("Database schema initialized.")


if __name__ == "__main__":
    main()
