# Task 3 Tech Plan: 研究数据默认展示为 Level 1 决策卡片

## 背景

当前个股研究会保存比较完整的证据层：stock profile、sources、sectors、knowledge_items、audit report、review report 和 draft artifact。这对审计、追溯和后续刷新有价值，但默认查看时信息过长，用户容易被事实条目淹没，反而看不到投资判断的核心焦点。

目标不是少存，而是分层展示：存储层保留细节，默认展示层只展示决策所需的摘要。

## 目标

1. 保留完整 `sources`、`knowledge_items`、audit/review artifacts。
2. 默认 stock inspect/search 输出 Level 1 决策卡片。
3. 默认 research jobs 列表只显示状态和摘要，不吐完整 draft/audit/review。
4. 需要证据时可以显式展开。

## 非目标

1. 不删除现有 knowledge items。
2. 不降低来源审计要求。
3. 不在本任务中改变研究任务执行位置；执行位置属于 Task 2。

## Level 1 决策卡片字段

建议先不建新表，优先从现有 `stocks` 和 `knowledge_items` 生成；后续如需要再持久化。

```text
one_line_thesis
key_drivers: 1-3 条
core_risks: 1-3 条
watch_items: 1-3 条
data_freshness
source_status
audit_status
knowledge_count
source_count
```

## 展示分层

Level 1 默认展示：

```text
RKLB US
Thesis: ...
Drivers:
- ...
Risks:
- ...
Watch:
- ...
Freshness: latest 10-Q covered, stale after ...
Evidence: 3 sources, 18 facts, audit pass
```

Level 2 证据层，需要显式参数：

```text
include_sources=true
include_knowledge_items=true
include_audit=true
```

Level 3 artifact 层，需要 verbose/full：

```text
include_draft_json=true
include_audit_markdown=true
include_review_markdown=true
```

## 需要修改的入口

1. Stock query/inspect:
   - command router 的“查看/分析/inspect 股票”输出
   - 如有必要，新增 summary helper，不破坏 MCP `search_stock` 原始返回
2. Research jobs:
   - `scripts/list_research_jobs.py`
   - MCP `list_research_jobs`
   - command router 的“查看研究任务”输出

## 实现步骤

1. 阅读当前 `search_stock`、command router stock inspect 和 `list_research_jobs` 的输出路径。
2. 新增一个纯函数，将 stock profile + knowledge items 归纳成 Level 1 card。
3. 对 knowledge items 做简单分组：
   - `business` 可进入 thesis/drivers
   - `risk` 进入 core risks
   - `watch_item` 进入 watch items
   - 其他类型默认计数，不默认铺开
4. 默认 stock inspect 输出 Level 1 card 和 counts。
5. 增加 detail/verbose 参数，用于显示完整 `knowledge_items` 和 `sources`。
6. 修改 `list_research_jobs` 默认输出，只显示：
   - symbol/market
   - status
   - provider/source_policy
   - execution_location
   - audit status
   - warnings count
   - token usage
   - artifact 是否存在
   - import status
7. verbose 模式保留完整 draft/audit/review 访问能力。
8. 对 07709 HK、09995 HK、SPCX US、RKLB US 做手工快照检查。

## 验收标准

1. 默认查看某只股票时，第一屏能看到 thesis、drivers、risks、watch items。
2. 默认输出不包含 20 条以上 facts 的长列表。
3. `list_research_jobs` 默认不包含完整 `draft_json`、`audit_markdown`、`review_markdown`。
4. verbose/detail 模式仍能拿到完整证据。
5. `import_stock_research_draft` 不丢任何 sources/knowledge_items。
6. MCP API 兼容性不被破坏；如改变返回结构，需要提供新工具或新参数，而不是静默破坏老行为。

## 测试建议

1. 单元测试：Level 1 card 从 business/risk/watch_item 中抽取合理字段。
2. 单元测试：默认 job list response 不包含大字段。
3. 单元测试：verbose=true 时可返回完整字段。
4. 手工检查：
   - `07709 HK`
   - `09995 HK`
   - `SPCX US`
   - `RKLB US`

## 风险

1. 纯规则归纳可能把 thesis 写得不够好，需要后续引入人工确认或 LLM summary。
2. 如果直接改 MCP `search_stock` 返回结构，可能破坏现有调用方；优先改展示层或新增 summary endpoint。
3. 默认瘦身不能隐藏关键风险；风险字段必须始终在 Level 1 出现。
