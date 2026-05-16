from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.research.validation import validate_research_draft


def default_output_path(draft_path: Path) -> Path:
    return draft_path.with_suffix(".review.md")


def build_review_markdown(draft: dict[str, Any], draft_path: Path) -> str:
    stock = draft.get("stock", {})
    lines: list[str] = []
    title = f"{stock.get('name') or stock.get('symbol', 'Unknown')} 研究草稿审阅"
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 确认状态")
    lines.append("")
    lines.append("- [ ] 我已确认股票画像可以入库")
    lines.append("- [ ] 我已确认板块归属可以入库")
    lines.append("- [ ] 我已确认事实知识和来源匹配")
    lines.append("- [ ] 我已确认用户心得代表我的观点")
    lines.append("")
    lines.append("## 股票画像")
    lines.append("")
    lines.append(f"- 代码：{stock.get('symbol', '')}")
    lines.append(f"- 市场：{stock.get('market', '')}")
    lines.append(f"- 名称：{stock.get('name', '')}")
    lines.append(f"- 核心业务：{stock.get('core_business', '')}")
    lines.append(f"- 股权结构：{stock.get('equity_structure', '')}")
    lines.append(f"- 股性：{stock.get('stock_character', '')}")
    lines.append(f"- 突出历史：{stock.get('notable_history', '')}")
    lines.append("")

    lines.append("## 板块归属")
    lines.append("")
    sectors = draft.get("sectors", [])
    if sectors:
        for item in sectors:
            path = " > ".join(item.get("path", []))
            lines.append(
                f"- `{item.get('relation_type', 'related')}` {path} "
                f"(confidence={item.get('confidence', 0.5)}, source={item.get('source_key', '')})"
            )
            if item.get("description"):
                lines.append(f"  - 描述：{item['description']}")
            if item.get("recent_status"):
                lines.append(f"  - 近况：{item['recent_status']}")
    else:
        lines.append("- 暂无")
    lines.append("")

    lines.append("## 事实知识")
    lines.append("")
    knowledge_items = draft.get("knowledge_items", [])
    if knowledge_items:
        for item in knowledge_items:
            lines.append(
                f"- `{item.get('knowledge_type', '')}` "
                f"(confidence={item.get('confidence', 0.5)}, source={item.get('source_key', '')})"
            )
            lines.append(f"  - {item.get('content', '')}")
            if item.get("stale_after"):
                lines.append(f"  - 复核时间：{item['stale_after']}")
    else:
        lines.append("- 暂无")
    lines.append("")

    lines.append("## 用户心得")
    lines.append("")
    insights = draft.get("user_insights", [])
    if insights:
        for item in insights:
            tags = ", ".join(item.get("tags", []))
            lines.append(f"- {item.get('insight', '')}")
            if item.get("normalized_summary"):
                lines.append(f"  - 摘要：{item['normalized_summary']}")
            if tags:
                lines.append(f"  - 标签：{tags}")
    else:
        lines.append("- 暂无")
    lines.append("")

    lines.append("## 来源")
    lines.append("")
    for source in draft.get("sources", []):
        title = source.get("title", "")
        key = source.get("key", "")
        url = source.get("url")
        publisher = source.get("publisher", "")
        if url:
            lines.append(f"- `{key}` [{title}]({url}) - {publisher}")
        else:
            lines.append(f"- `{key}` {title} - {publisher}")
    lines.append("")

    lines.append("## 确认后导入")
    lines.append("")
    lines.append("确认无误后运行：")
    lines.append("")
    lines.append("```bash")
    lines.append(f"python scripts/import_research_draft.py {draft_path} --confirmed")
    lines.append("```")
    lines.append("")
    lines.append("如果不确认，请直接修改原 JSON，再重新运行：")
    lines.append("")
    lines.append("```bash")
    lines.append(f"python scripts/validate_research_draft.py {draft_path}")
    lines.append(f"python scripts/review_research_draft.py {draft_path}")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a human-readable review file for a research draft.")
    parser.add_argument("draft_path", type=Path, help="Path to enriched research draft JSON.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output review markdown path. Defaults to replacing .json with .review.md.",
    )
    args = parser.parse_args()

    draft = json.loads(args.draft_path.read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        print("Draft must be a JSON object.", file=sys.stderr)
        raise SystemExit(1)

    result = validate_research_draft(draft)
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    for warning in result.warnings:
        print(f"WARNING: {warning}")

    output_path = args.output or default_output_path(args.draft_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_review_markdown(draft, args.draft_path), encoding="utf-8")
    print(f"Research draft review written to {output_path}")


if __name__ == "__main__":
    main()
