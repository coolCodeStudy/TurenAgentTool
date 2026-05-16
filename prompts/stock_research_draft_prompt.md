# 个股研究草稿补全任务

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

