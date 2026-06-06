from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.research.audit import audit_research_draft, build_audit_markdown
from investment_knowledge_mcp.research.source_facts import extract_source_facts


def default_output_path(draft_path: Path) -> Path:
    return draft_path.with_name(draft_path.stem.replace("_research_draft", "") + "_audit_report.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a research draft against source excerpts.")
    parser.add_argument("draft_path", type=Path)
    parser.add_argument("--source-facts", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-review", action="store_true")
    args = parser.parse_args()

    draft = json.loads(args.draft_path.read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        raise SystemExit("Draft must be a JSON object.")

    if args.source_facts:
        source_facts = json.loads(args.source_facts.read_text(encoding="utf-8"))
    else:
        source_facts = extract_source_facts(draft)

    audit = audit_research_draft(draft, source_facts=source_facts)
    output = args.output or default_output_path(args.draft_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_audit_markdown(draft, source_facts, audit), encoding="utf-8")
    print(f"Audit report written to {output}")
    print(f"audit_status={audit.status}")

    if audit.status == "fail" or (args.fail_on_review and audit.status == "needs_review"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
