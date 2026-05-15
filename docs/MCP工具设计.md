# InvestmentKnowledge MCP 工具设计

## 设计目标

MCP Server 是大模型和本地知识库之间的边界。大模型负责研究、总结、推理和提问；MCP Server 负责可靠地查询、写入、更新和校验数据。

重要原则：

1. 大模型产出的事实默认进入待确认状态。
2. 用户明确确认后再更新核心画像字段。
3. 所有重要结论要带来源。
4. 用户心得可以直接保存，但需要保留原文。

## 第一版工具

### search_stock

查询股票画像。

输入：

```json
{
  "symbol": "00700",
  "market": "HK"
}
```

输出：

```json
{
  "stock": {},
  "sectors": [],
  "knowledge_items": [],
  "user_insights": []
}
```

### upsert_stock_profile

创建或更新股票画像。

输入：

```json
{
  "symbol": "00700",
  "market": "HK",
  "name": "腾讯控股",
  "core_business": "...",
  "equity_structure": "...",
  "stock_character": "...",
  "notable_history": "...",
  "confirmed_by_user": false,
  "sources": []
}
```

行为：

- 如果股票不存在，则创建。
- 如果股票已存在，则更新非空字段。
- 大模型生成内容默认不覆盖用户确认内容，除非用户明确允许。

### upsert_sector_tree

创建或更新板块树。

输入：

```json
{
  "path": ["AI", "算力", "光模块"],
  "description": "...",
  "recent_status": "..."
}
```

行为：

- 按路径逐级创建 sectors。
- 已存在则复用。
- 返回最后一级 sector_id。

### link_stock_to_sector

建立股票和板块关系。

输入：

```json
{
  "stock_id": 1,
  "sector_id": 10,
  "relation_type": "main",
  "confidence": 0.85,
  "source_id": 3,
  "confirmed_by_user": false
}
```

### add_knowledge_item

写入事实知识。

输入：

```json
{
  "target_type": "stock",
  "target_id": 1,
  "knowledge_type": "business",
  "content": "...",
  "source_id": 3,
  "confidence": 0.8,
  "confirmed_by_user": false,
  "stale_after": "2026-08-15T00:00:00+08:00"
}
```

### add_user_insight

写入用户心得。

输入：

```json
{
  "target_type": "stock",
  "target_id": 1,
  "insight": "我觉得这个票股性很妖，适合短线不适合长拿。",
  "normalized_summary": "用户认为该股波动和情绪属性较强，更适合短线交易。",
  "tags": ["股性", "短线", "高波动"]
}
```

### get_portfolio_summary

查询当前持仓。

输出：

```json
{
  "positions": [],
  "sector_exposure": [],
  "top_risks": []
}
```

### record_trade_event

记录操作事件。

输入：

```json
{
  "stock_id": 1,
  "action_type": "buy",
  "price": 300.5,
  "quantity": 100,
  "reason": "回调到支撑位，试仓。",
  "source": "manual",
  "happened_at": "2026-05-15T10:30:00+08:00"
}
```

### create_review_report

保存每日复盘。

输入：

```json
{
  "report_date": "2026-05-15",
  "portfolio_snapshot": {},
  "summary": "...",
  "risks": [],
  "opportunities": [],
  "new_knowledge_candidates": []
}
```

## 推荐调用流程

### 个股录入

```text
search_stock
  -> 外部搜索/公告/财报工具
  -> upsert_stock_profile
  -> upsert_sector_tree
  -> link_stock_to_sector
  -> add_knowledge_item
```

### 用户心得

```text
search_stock 或搜索板块
  -> add_user_insight
  -> 后续分析时语义检索 user_insights
```

### 每日复盘

```text
Futu MCP 获取持仓
  -> 更新 positions
  -> get_portfolio_summary
  -> 同花顺 MCP 获取公告和板块近况
  -> add_knowledge_item 写入待确认知识
  -> create_review_report
```

