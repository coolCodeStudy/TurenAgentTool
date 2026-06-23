# InvestmentKnowledge MCP 工具设计

> Status note: This is the foundational MCP tool design reference. The authoritative tool surface is the current MCP/server code and the current engineering state in `docs/当前工程状态.md`.

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

### get_stock_context

构建个股分析上下文。它比 `search_stock` 更适合给大模型分析使用，会同时返回：

- 个股画像。
- 个股所属板块路径。
- 个股事实知识和来源。
- 个股用户心得。
- 相关板块知识和板块心得。
- `portfolio` / `strategy` 级用户偏好。

输入：

```json
{
  "symbol": "000660",
  "market": "KR"
}
```

### get_sector_context

构建板块分析上下文，可按板块路径或 `sector_id` 查询。

输入：

```json
{
  "path": ["科技", "半导体", "存储芯片", "DRAM/HBM"]
}
```

输出包含当前板块及子板块、相关股票、板块知识、板块心得和组合/策略级用户偏好。

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

### add_source

写入资料来源。

输入：

```json
{
  "source_type": "web",
  "title": "公司公告",
  "url": "https://example.com",
  "publisher": "交易所",
  "published_at": "2026-05-16T00:00:00+08:00"
}
```

### add_user_insight

写入用户心得。

心得可以指向不同对象：`stock` 表示个股，`sector` 表示板块，`portfolio` 表示整体组合或仓位管理，`strategy` 表示长期交易纪律。`portfolio` 和 `strategy` 这类全局心得可以暂时使用 `target_id: null`。

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

仓位管理心得示例：

```json
{
  "target_type": "portfolio",
  "target_id": null,
  "insight": "AI 主线涨幅很大时，我不希望单一主题仓位超过组合的一半。",
  "normalized_summary": "用户希望控制单一高拥挤主题的组合占比，避免主题风险过度集中。",
  "tags": ["仓位管理", "主题拥挤", "风险控制"]
}
```

### record_user_insight

按自然对象写入用户明确确认过的心得。它是 `add_user_insight` 的便利层，会先把股票代码或板块路径解析成内部 `target_id`，再写入 `user_insights`。

个股心得示例：

```json
{
  "target_type": "stock",
  "symbol": "000660",
  "market": "KR",
  "insight": "海力士要优先按 AI 内存/HBM 主线理解。",
  "normalized_summary": "用户认为 SK 海力士的核心观察框架是 AI 内存和 HBM，而非单纯传统存储周期。",
  "tags": ["AI内存", "HBM", "个股框架"]
}
```

板块心得示例：

```json
{
  "target_type": "sector",
  "sector_path": ["AI基础设施", "AI服务器供应链", "高带宽内存"],
  "insight": "HBM 很强，但太拥挤时不要追太满。",
  "normalized_summary": "用户认可 HBM 主线强度，但希望避免在拥挤阶段追高过度。",
  "tags": ["HBM", "拥挤度", "仓位管理"]
}
```

### propose_candidate_insight

提出待确认候选心得。适用于系统根据分析、复盘或对话推断出来，但用户还没有明确确认的观点。候选心得不会作为正式用户偏好参与分析，只会出现在待确认区。

输入：

```json
{
  "target_type": "sector",
  "sector_path": ["AI基础设施", "AI服务器供应链", "高带宽内存"],
  "insight": "HBM 很强，但拥挤时不要无脑追高。",
  "normalized_summary": "系统推断用户可能希望在 HBM 拥挤交易阶段控制追高风险。",
  "tags": ["HBM", "拥挤度", "候选"],
  "reason": "来自一次海力士分析后的系统提炼，需要用户确认。"
}
```

### list_candidate_insights

查看候选心得。

输入：

```json
{
  "status": "pending",
  "target_type": null
}
```

### confirm_candidate_insight

确认候选心得。确认后会创建或复用一条正式 `user_insights`，并把候选状态标记为 `confirmed`。

输入：

```json
{
  "candidate_id": 1
}
```

### reject_candidate_insight

拒绝候选心得。拒绝后候选状态标记为 `rejected`，不会进入正式用户记忆。

输入：

```json
{
  "candidate_id": 1
}
```

### import_stock_research_draft

把用户确认后的个股研究草稿一次性入库。

输入：

```json
{
  "draft": {
    "stock": {
      "symbol": "00700",
      "market": "HK",
      "name": "腾讯控股"
    },
    "sources": [],
    "sectors": [],
    "knowledge_items": [],
    "user_insights": []
  },
  "confirmed_by_user": true
}
```

行为：

- 创建或更新股票画像。
- 创建或复用多级板块树。
- 建立股票和板块关系。
- 写入来源和事实知识。
- 写入用户心得。
- 返回导入结果和 `search_stock` 查询结果。

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
