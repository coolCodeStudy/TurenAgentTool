from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

PROMPT_TEMPLATE_PATH = PROJECT_ROOT / "prompts" / "stock_research_draft_prompt.md"

DEFAULT_PROMPT_TEMPLATE = """# 个股研究草稿补全任务

你是投资知识图谱系统的研究员。请根据下面的草稿骨架和资料来源，补全一个可入库的 `research_draft.json`。

## 目标

把候选资料整理成结构化研究草稿，供用户确认后写入知识库。

## 严格规则

1. 只输出一个 JSON 对象，不要输出 Markdown、解释文字或代码块。
2. 保留输入中的 `stock.symbol`、`stock.market` 和 `sources`。
3. 每条事实型 `knowledge_items` 必须引用 `source_key`。
4. 不确定的内容不要硬填；可以降低 `confidence`，或写入 `watch_item`。
5. 不要把推测写成事实。
6. `user_insights` 只能写用户明确表达过的观点；如果没有用户观点，保持空数组。
7. `sectors` 要使用多级路径，股票可归属多个板块。
8. 所有输出字段必须符合草稿协议。

## 建议字段

`stock`:

- `symbol`
- `market`
- `name`
- `core_business`
- `equity_structure`
- `stock_character`
- `notable_history`

`knowledge_items.knowledge_type` 可使用：

- `business`
- `equity_structure`
- `history`
- `risk`
- `watch_item`
- `sector_logic`
- `announcement`

`sectors.relation_type` 可使用：

- `main`
- `theme`
- `related`

## 草稿骨架

{{DRAFT_JSON}}

## 资料来源

{{SOURCES_JSON}}

## 输出要求

输出完整 JSON，形状如下：

```json
{
  "stock": {},
  "sources": [],
  "sectors": [],
  "knowledge_items": [],
  "user_insights": []
}
```
"""


def default_output_path(draft_path: Path) -> Path:
    return draft_path.with_suffix(".prompt.md")


def pretty_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def load_prompt_template(path: Path = PROMPT_TEMPLATE_PATH) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return DEFAULT_PROMPT_TEMPLATE


def build_prompt(draft: dict, template: str) -> str:
    sources = draft.get("sources", [])
    return (
        template.replace("{{DRAFT_JSON}}", pretty_json(draft))
        .replace("{{SOURCES_JSON}}", pretty_json(sources))
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a model prompt from a research draft skeleton.")
    parser.add_argument("draft_path", type=Path, help="Path to draft skeleton JSON.")
    parser.add_argument(
        "--template",
        type=Path,
        default=PROMPT_TEMPLATE_PATH,
        help="Prompt template path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output prompt path. Defaults to replacing .json with .prompt.md.",
    )
    args = parser.parse_args()

    draft = json.loads(args.draft_path.read_text(encoding="utf-8"))
    template = load_prompt_template(args.template)
    prompt = build_prompt(draft=draft, template=template)

    output_path = args.output or default_output_path(args.draft_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt, encoding="utf-8")
    print(f"Research prompt written to {output_path}")


if __name__ == "__main__":
    main()
