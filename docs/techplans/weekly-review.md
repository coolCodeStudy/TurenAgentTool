# Task Plan: 本周复盘生成器

> Status note (2026-07-26): The user-facing `炸裂时刻`/all-negative-Top-3 rule is superseded by [`2026-07-26-weekly-material-drag-design.md`](../superpowers/specs/2026-07-26-weekly-material-drag-design.md). Current production language is `显著拖累`: a row requires both a material USD-equivalent loss and, when opening market value exists, a material relative weekly impact. The historical wording below remains for traceability only.

## 背景

`docs/product/PRD-每周复盘.md` 定义了本周复盘产品：用户输入“本周复盘”，系统自动生成一份可直接阅读的周复盘 Markdown。

当前实现已经接入了富途历史成交和实时持仓查询，也已有 `trade_records`、`account_snapshots`、知识库、用户心得、港股 IPO、组合分析和命令路由能力。缺口不是重新接富途，而是把这些已接入数据沉淀成稳定的复盘数据资产，并基于每日快照生成周度归因。

## 产品口径

当前周复盘以每日持仓 snapshot 差分和区间交易记录共同估算单票区间盈亏：

```text
snapshot_pl_delta = 期末持仓 pl_val - 期初持仓 pl_val
realized_pl_estimate = 基于 trade_records 卖出成交和移动平均成本估算的已实现盈亏
period_pl = snapshot_pl_delta + realized_pl_estimate
```

交易记录作为解释账本，用来说明：

- 为什么 `qty` 变化。
- 为什么 `cost_price` 变化。
- 本周是否发生加仓、减仓、新开仓、清仓。
- 区间卖出/清仓对 realized P/L 的影响。

因此当前口径是：

```text
performance 主账本：account_snapshots + trade_records
快照账本：未实现盈亏变化
交易账本：卖出实现盈亏估算、仓位变化解释
富途实时接口：用于补漏和当天即时刷新，不作为唯一历史来源
```

## 现状判断

已有能力：

- `get_futu_trade_history(start, end)` 已接入。
- `get_futu_positions()` 已接入。
- `trade_records` 表和 `repository.upsert_trade_records()` 已存在。
- `account_snapshots` 表和每日 `account-snapshot-scheduler` 已存在。
- `portfolio_analysis.py` 已能做持仓归一化、币种分组、盈亏排序和知识库匹配。
- `command_router.py` 已有交易复盘、收益估算、持仓分析、IPO 等入口。

当前缺口：

- 每日账户快照任务虽然调用 `get_futu_trade_history(today, today)`，但没有把当天 `deals` 写入 `trade_records`。
- 当前数据库未必已有历史 `account_snapshots` 和 `trade_records`，需要回补或从上线后开始积累。
- `review_reports` 当前偏每日摘要，周复盘结构化字段不足。
- 指数行情 API 和外部事件源暂缓，不作为 P1 阻塞项。

## P1 数据采集闭环

修改 `investment_knowledge_mcp/account_snapshots.py` 的 `run_account_snapshot_once()`：

```text
每日账户快照任务
  -> get_futu_trade_history(today, today)
  -> upsert_trade_records(trade_snapshot.deals)
  -> get_futu_positions()
  -> upsert_account_snapshot(account_info, positions, fx_rates)
```

metadata 记录本次交易同步结果：

```python
metadata={
    "task": "daily_account_snapshot",
    "account_error": trade_snapshot.account_error,
    "position_count": len(position_snapshot.positions),
    "trade_count": len(trade_snapshot.deals),
    "trade_synced_count": trade_result["synced_count"],
}
```

这一步必须进入 P1。周复盘可以主要依赖快照，但没有每日交易入库，就无法解释仓位变化，也无法支持后续交易执行复盘。

## 新增模块

新增：

```text
investment_knowledge_mcp/weekly_review.py
```

核心函数：

```python
build_weekly_review_context(start: date, end: date) -> dict
render_weekly_review_markdown(context: dict) -> str
```

后续再接模型：

```python
generate_weekly_review_with_openai(context: dict) -> str | None
```

设计原则：

- `weekly_review.py` 做应用服务层聚合，不把逻辑继续塞进 `command_router.py`。
- 所有计算先产出结构化 context，再渲染 Markdown。
- 模型只能基于结构化 context 总结，不直接编造行情、新闻或交易结论。

## 周复盘生成流程

```text
用户输入：本周复盘

1. 解析日期范围，默认本周一到今天。
2. 读取 account_snapshots 中的周初快照和期末/最新快照。
3. 读取 trade_records 中本周交易。
4. 如果 trade_records 缺失，则调用已接入的 get_futu_trade_history(start, end) 补库。
5. 如果当天 snapshot 缺失，则调用已接入的 get_futu_positions() 生成即时参考。
6. 计算每只股票的 pl_val_delta、realized_pl_estimate、period_pl、qty_delta、cost_price_delta、market_val_delta。
7. 生成高光时刻、炸裂时刻、当前持仓分析表。
8. 合并知识库、板块、用户心得和候选心得。
9. 指数和外部事件先标记为“数据源未接入”。
10. 渲染 Markdown。
11. 保存 review_reports 或 artifact。
```

## Context 结构

建议内部结构：

```python
{
    "period": {
        "start": "2026-06-08",
        "end": "2026-06-14",
        "label": "2026-06-08 至 2026-06-14",
    },
    "source_status": {
        "account_snapshots": {"status": "ok|partial|missing", "count": 0},
        "trades": {"status": "ok|backfilled|missing", "count": 0},
        "positions": {"status": "ok|fallback|missing", "fetched_at": None},
        "indexes": {"status": "missing", "reason": "index provider not configured"},
        "events": {"status": "missing", "reason": "external event provider not implemented"},
        "ipo": {"status": "ok|missing", "count": 0},
    },
    "position_changes": [],
    "highlights": [],
    "blowups": [],
    "holdings_table": [],
    "trades": {
        "records": [],
        "by_symbol": [],
    },
    "next_week": [],
    "story": {},
    "candidate_insights": [],
}
```

## 单只股票计算口径

对同一 `code` 比较期初和期末：

```text
pl_val_delta = end.pl_val - start.pl_val
realized_pl_estimate = 按期初 cost_price 和区间买卖成交估算卖出实现盈亏
period_pl = pl_val_delta + realized_pl_estimate
qty_delta = end.qty - start.qty
cost_price_delta = end.cost_price - start.cost_price
market_val_delta = end.market_val - start.market_val
```

仓位变化标签：

```text
qty 不变：持仓未变
qty 增加：加仓
qty 减少：减仓
期初无、期末有：新开仓
期初有、期末无：清仓
```

置信度：

```text
高：qty 基本不变，pl_val_delta 可以较好代表本周持仓表现。
中：qty 有变化，但仍有期初/期末持仓，可判断本周盈亏方向。
低：新开仓或清仓，需要结合 trade_records 的 realized_pl_estimate 判断，不能只看快照差分。
```

注意：如果中间发生加仓/减仓，`pl_val_delta` 只代表未实现盈亏变化；排名和故事应优先使用 `period_pl`。

## 高光时刻

按 `period_pl` 降序取 Top 3。

输出字段：

```text
标的 | 类型 | 本周盈亏变化 | 仓位变化 | 置信度 | 复盘问题
```

类型示例：

```text
持仓浮盈改善
亏损收窄
新开仓当前盈利
加仓后贡献
```

## 炸裂时刻

按 `period_pl` 升序取 Top 3。

输出字段：

```text
标的 | 类型 | 本周盈亏变化 | 仓位变化 | 置信度 | 下周处理
```

类型示例：

```text
浮亏扩大
盈利回撤
新开仓当前亏损
加仓后拖累
历史拖累延续
```

## 当前持仓分析

输出表：

```text
市场 | 标的 | 主题 | 市值 | 当前盈亏 | 本周盈亏变化 | 仓位变化 | 状态 | 下周节奏
```

状态规则：

- `核心持仓`：市值靠前，且知识库有明确主线。
- `强势贡献`：本周 `pl_val_delta` 靠前。
- `历史拖累`：当前 `pl_val` 明显为负。
- `本周拖累`：本周 `pl_val_delta` 明显为负。
- `高波动`：杠杆、量子、太空、加密、新股等。
- `补研究`：持仓较大但知识库缺失。
- `待处理`：用户心得或历史复盘里出现低效、想清理等信号。

## 交易记录使用方式

交易记录 P1 不作为 performance 主账本，但需要用于解释 `position_changes`：

- 本周买入：解释 `qty` 增加或新开仓。
- 本周卖出：解释 `qty` 减少或清仓。
- 多笔交易：展示方向和成交金额汇总，不强算 realized P/L。
- 交易记录缺失：明确标记“交易解释缺失”，但不阻塞 snapshot 差分复盘。

后续 P2 可以在完整历史交易、资金流水、费用、分红、拆合股和换汇口径稳定后，再做严格 realized P/L。

## review_reports 存储

P1 可以先兼容旧表：

```text
summary：完整 Markdown
portfolio_snapshot：完整 weekly_review_context
risks：炸裂时刻
opportunities：高光时刻 + 下周事项
new_knowledge_candidates：候选心得
```

建议增强字段：

```sql
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS period_start DATE;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS period_end DATE;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS report_type TEXT NOT NULL DEFAULT 'daily';
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS source_status JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS highlights JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS blowups JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS holdings_table JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS next_week JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS story JSONB NOT NULL DEFAULT '{}'::jsonb;
```

唯一性建议从 `report_date UNIQUE` 迁移为：

```text
UNIQUE (report_type, period_start, period_end)
```

如果短期不改约束，则周复盘先只写 artifact，或把 `report_date` 设为 `period_end` 并接受每日/周度不能同日共存的限制。

## 命令接入

在 `investment_knowledge_mcp/command_router.py` 新增：

```text
本周复盘
周复盘
复盘 2026-06-08 2026-06-14
查看下周节奏
```

`is_query_command()` 也需要加入周复盘命令，保证钉钉入口可以直接查询。

## 输出结构

```text
# 本周复盘 YYYY-MM-DD ~ YYYY-MM-DD

## 1. 高光时刻
## 2. 炸裂时刻
## 3. 指数
## 4. 整体故事
## 5. 下周展望
## 6. 当前持仓分析
```

指数和外部事件 P1 固定输出数据缺口：

```text
指数数据源未接入，本周不做指数归因。
外部事件源未接入，本周不做新闻/社媒/公告归因。
```

## P1 验收标准

1. `本周复盘` 可以输出 6 个固定模块。
2. 每日账户快照任务会自动把当天交易写入 `trade_records`。
3. 高光/炸裂主要来自 snapshot 差分，不依赖完整交易成本。
4. 仓位变化能结合交易记录解释。
5. 没有交易记录时仍可生成 snapshot 差分复盘，并明确数据缺口。
6. 没有指数行情时明确写“指数数据源未接入”。
7. 没有外部事件时明确写“外部事件源未接入”。
8. 当前持仓分析必须是表格。
9. 多币种不强行合计。
10. 不输出买卖指令。
11. 新观点只进入候选心得，不自动写正式记忆。

## 实施步骤

1. 修改 `run_account_snapshot_once()`，每日自动入库 `trade_records`。
2. 新增 `repository.list_trade_records(start, end)`。
3. 新增 `weekly_review.py`，实现 snapshot 差分和 Markdown fallback。
4. 在 `command_router.py` 接入周复盘命令。
5. 增强或兼容 `review_reports` 存储。
6. 增加 smoke test：交易缺失、快照缺失、多币种、qty 变化、指数/事件缺失。
7. 手工运行 `本周复盘` 检查钉钉阅读效果。

## P2 增强

- 接入指数行情 provider。
- 接入持仓相关公告、财报日历和外部事件摘要。
- 基于完整历史交易和资金流水做 realized P/L。
- 自动比较上周“下周展望”和本周结果。
- 支持候选心得一键确认/拒绝。
- 做 Web 页面，但 Markdown 仍保留为主输出。

## 2026-06-28 Source Completeness Update

This section supersedes the older P1/P2 split for `AT-2026-06-28-001`. Index context, external company/event evidence, theme context, and local user-knowledge evidence are now part of the acceptance scope for Weekly Review content quality.

## 2026-06-30 Holder-Level Attribution Update

This section implements the P1 follow-up tracked by `AT-2026-06-30-001`. Weekly Review V1 was accepted by the user on 2026-06-29, but the contributor/laggard rows are still too shallow when a large holding moves. The next implementation pass adds a structured `holder_attribution[]` field that explains top holding moves with source-aware cause candidates instead of generic P/L copy.

### Scope

P1 holder-level attribution covers:

- Top 3 positive contributors from `highlights[]`.
- Top 3 negative contributors from `blowups[]`.
- Any additional material current holding marked as core, high volatility, or needs research by the holdings table when it is not already covered.

The context remains provider-fed. P1 does not add live Xueqiu, Twitter/X, forum, or login-gated social scraping. Rumor, market-essay, and cost-driver material may enter only when supplied by an approved provider, cached artifact, fixture, manual source input, or existing structured `event_summary[]` / `knowledge_evidence[]` rows.

### Context Contract

`build_weekly_review_context()` now returns:

```python
{
    "holder_attribution": [
        {
            "code": "HK.02476",
            "name": "胜宏科技",
            "currency": "HKD",
            "weekly_pl": -6920.0,
            "movement": "持仓未变",
            "position_confidence": "高",
            "attribution_verdict": "mixed / single_stock_event_watch + fundamentals_cost_watch",
            "dominant_lens": "mixed",
            "confidence": "rumor_watch|low|medium|high",
            "thesis_impact": "needs_research|challenges_thesis|supports_thesis|neutral_noise",
            "cause_candidates": [
                {
                    "lens": "single_stock_event",
                    "title": "Q2 performance miss rumor or market essay discussion",
                    "claim": "Unverified market discussion may be one thing traders are watching.",
                    "source_type": "social_rumor",
                    "source_name": "manual_fixture_or_provider_source",
                    "source_date": "2026-06-30",
                    "url": "https://...",
                    "confidence": "rumor_watch",
                    "thesis_impact": "needs_research",
                    "evidence": "...",
                    "next_validation": "Check company announcement, earnings guidance, and dated reputable follow-up.",
                }
            ],
            "evidence": [],
            "source_gaps": [],
            "next_validation": [],
            "links": {
                "highlight": None,
                "blowup": "HK.02476",
                "holding": "HK.02476",
                "events": ["..."],
                "knowledge": ["..."],
                "trades": "HK.02476",
            },
        }
    ]
}
```

The builder links attribution cards to existing `highlights[]`, `blowups[]`, `holdings_table[]`, `event_summary[]`, `index_summary[]`, `knowledge_evidence[]`, and trade summaries by `code` / linked ticker / theme where available.

### Source Classification And Confidence

Attribution source classification is explicit:

| Input source | Normalized type | Confidence ceiling | Handling |
| --- | --- | --- | --- |
| Official announcement, filing, earnings call, audited report | `official` | `high` | Can support a high-confidence cause when dated and ticker-linked. |
| Reputable financial news, market data news, dated industry publication | `news_or_industry` | `medium` | Can support medium confidence, or high only when corroborated by official evidence in a later pass. |
| Dated market essay or analyst-style public article | `market_essay` | `medium` when evidence-based, otherwise `low` | Render as a candidate and separate facts from opinion where supplied. |
| Xueqiu, Twitter/X, forums, reposted screenshots, unsourced rumor | `social_rumor` | `rumor_watch` | Must be labeled unverified and must not be rewritten as fact. |
| Local confirmed/candidate user insight or stock/sector knowledge | `user_knowledge` | stored-status dependent, implemented as `medium` for confirmed/local knowledge and `low` for candidate knowledge | Used to explain thesis relationship, not to prove an external cause. |

Rumor/social rules are enforced in code:

- `social_rumor` always maps to `confidence=rumor_watch`.
- Rumor-only cards use `thesis_impact=needs_research`.
- Rumor claims are rendered as "market may be watching" / "unverified" candidates, never as confirmed causes.
- Rumor candidates are not written to formal user insights.

### Attribution Lenses

Cause candidates use these lenses:

- `market_benchmark`: broad index move for the holding market.
- `theme_sector`: detected theme / sector evidence from local knowledge or theme news.
- `single_stock_event`: dated ticker-linked event, announcement, news, essay, or rumor.
- `fundamentals_cost_drivers`: revenue/order/margin/upstream cost evidence such as copper, laminate, fiberglass, PCB supply-chain cost pressure, utilization, pricing, FX, or rates.
- `position_trade_behavior`: unchanged/increased/reduced/new/closed position and trade summary facts.
- `user_thesis_knowledge`: stored stock/sector/user knowledge and whether the week challenges or supports it.

If no usable external cause evidence exists, the card still renders with observed position/trade facts plus a transparent `source_gaps[]` state and concrete validation steps.

### Rendering

Markdown renders a `## 7. 持仓归因卡` section after the holdings table. Each card includes weekly impact, position confidence, attribution verdict, cause candidates, evidence/source/date, confidence, thesis impact, and next validation.

The Web surface renders the same `holder_attribution[]` as compact expandable cards after the holdings table. Cards expose confidence badges, source labels, evidence links/source ids, thesis impact, next validation, and source gaps. Web copy must not expose raw provider exceptions, table names, stack traces, or prompts.

### Traceability Matrix

| Product requirement | Implementation target | Verification |
| --- | --- | --- |
| Structured `holder_attribution[]` linked to existing Weekly Review context | `investment_knowledge_mcp/weekly_review.py` builder after source evidence is loaded | Fixture assertions for links and coverage |
| Cause candidates with verdict, evidence/source/date, confidence, thesis impact, next validation | Attribution candidate builder and Markdown/Web renderers | `HK.02476` fixture and Markdown/Web rendering assertions |
| Lenses for market, theme, single-stock, fundamentals/cost, position/trade, user thesis | Candidate builder helper functions | Cross-lens fixture plus source-missing fallback |
| Source classification for official/news/essay/rumor/user knowledge | Source normalization helpers | Source-label safety fixture |
| Rumor capped at `rumor_watch` and not laundered as fact | Source confidence ceiling and copy helpers | Rumor fixture checks |
| No live Xueqiu scraping in P1 | No new scraping provider added | Code review and fixture-only tests |

### Verification Plan

- `python3 -m py_compile investment_knowledge_mcp/weekly_review.py investment_knowledge_mcp/weekly_review_web.py`
- `python3 -m unittest tests.test_weekly_review_holder_attribution`
- Fixture checks for `HK.02476` / Shenghong Technology with unchanged position, negative weekly attribution, supplied Q2 miss rumor/market-essay source, and supplied upstream cost-inflation source.
- Provider-missing fallback check: same holding without usable events renders source gaps and next validation without invented causes.
- Source-label safety check: `social_rumor` remains `rumor_watch`; `news_or_industry` cost-driver evidence remains separate and higher confidence than rumor.
- `git diff --check`
- `python3 scripts/audit_delivery_state.py --feature "Weekly review generator"`

### Provider Set And Schemas

The first implementation pass uses a bounded provider set:

| Source family | Provider | Context field | Required fields |
| --- | --- | --- | --- |
| Market indexes | Futu OpenD daily K-line via `get_futu_market_bars()`, falling back to no-key Yahoo chart daily bars when OpenD is unavailable in cloud Web containers | `index_summary[]` | `code`, `name`, `market`, `weekly_change_pct`, `largest_daily_move`, `environment_label`, `portfolio_relevance`, `source.provider`, `source.metric`, `source.start_date`, `source.end_date` |
| Company announcements / filings | `OfficialResearchProvider` for supported US/HK holdings and contributors/detractors | `event_summary[]` | `category`, `code`, `name`, `source_name`, `source_type`, `published_at` or `checked_at`, `title`, `url`, `freshness`, `summary`, `citation` |
| Dated company/theme news | No-key Yahoo Finance RSS via `event_data_provider.get_yahoo_finance_news_events()` for top holdings and bounded theme proxy symbols, used before disclosure-reference fallback | `event_summary[]` | `category`, `code`, `name`, `linked_ticker`, `linked_theme`, `source_name`, `source_type`, `source_id`, `published_at`, `checked_at`, `title`, `url`, `freshness`, `summary`, `citation` |
| Disclosure references | Official company disclosure/reference URLs for top holdings when live dated company/theme event collection returns no usable events | `event_summary[]` | `category`, `code`, `name`, `source_name`, `source_type`, `checked_at`, `title`, `url`, `freshness=reference_source`, `summary`, `citation` |
| Theme context | Existing sector mappings and sector knowledge from `repository.get_stock_context()` | `knowledge_evidence[]` | `source_type`, `id`, `code`, `name`, `summary`, `citation`, optional linked `source` metadata |
| User knowledge | Existing `user_insights`, `candidate_insights`, stock/sector/global memory from `repository.get_stock_context()` | `knowledge_evidence[]` | same evidence fields as theme context |

The required index basket is:

- US: S&P 500 (`US.SPX`), Nasdaq 100 (`US.NDX`), SOX Semiconductor Index (`US.SOX`)
- Hong Kong: Hang Seng Index (`HK.HSI`), Hang Seng Tech Index (`HK.HSTECH`), Hang Seng China Enterprises Index (`HK.HSCEI`)
- Mainland China: CSI 300 (`SH.000300`), ChiNext Index (`SZ.399006`), STAR 50 (`SH.000688`)

Index weekly change uses a named close-to-close convention over the available bars inside the review week. Largest daily move uses the largest absolute close-to-close daily change inside the same bar set.

### `source_status` Semantics

Weekly Review source families use these statuses:

| Status | Meaning | Product behavior |
| --- | --- | --- |
| `ok` | Required source family is available for the required coverage. | Story may make claims from this source family with citations. |
| `partial` | Some useful evidence is available, but at least one required item/category is missing. | Story may use available evidence and must name the missing coverage. |
| `checked_empty` | Provider ran and returned no relevant material events or knowledge. | Story may say the category was checked empty; this is different from an unavailable provider. |
| `missing` | No source data was loaded and no provider check succeeded. | Story must avoid claims depending on this family. |
| `provider_unavailable` | Provider exists but is unreachable, not installed, or failed in this environment. | Report is a transparent degraded draft. |
| `source_blocked` | Required acceptance coverage cannot be met, such as an active market without a representative index or no usable event evidence. | Report may render safely, but the source gap remains an acceptance blocker. |

Safe degraded copy must continue to hide internal provider names, table names, stack traces, and raw database errors from normal user copy.

### Story Input Contract

`story` is generated from structured context only:

- Portfolio/trade facts: `highlights`, `blowups`, `position_changes`, `holdings_table`, and trade summaries.
- Index facts: `index_summary` rows with close-to-close metrics and largest daily move.
- Event/theme facts: `event_summary` rows from official/company sources, dated company/theme news, and disclosure-reference fallback rows, plus `knowledge_evidence` rows from local stock/sector/user memory.
- Source facts: `source_status` entries, including missing and blocked categories.

Story output must include:

```text
mainline
market_environment
portfolio_attribution
event_evidence
negative_signals
portfolio_relation
next_validation
claims[] with type, text, citations[]
```

Every generated claim must cite one or more structured inputs such as `index:<code>`, `holding:<code>`, an official-source citation, or a local-memory citation like `stock_insight:<id>`.

### Acceptance Criteria For `AT-2026-06-28-001`

- The Weekly Review page no longer shows the old fixed “index/external event source not connected” content when generated context contains source-status and evidence fields.
- Each active portfolio market has at least one available broad index, or the report is clearly marked `source_blocked`.
- Material AI/semiconductor/growth exposure gets a relevant proxy index when available, or the missing proxy is visible in `source_status.indexes`.
- At least one dated external company, theme/news, or macro event category is included in the story evidence chain with `published_at` or event date, title/description, URL or stable source id, linked ticker/theme when applicable, and source-to-claim citations. Reference/search URLs alone do not satisfy this criterion.
- The story uses the required seven-part structure and includes source-to-claim citations.
- Missing macro calendar coverage remains visible as a partial/source-blocked category until a later provider fills it or Product removes it from scope.

### Verification Plan

- Fixture/local smoke: run the weekly review smoke path and assert the new story fields, source-status vocabulary, and absence of old internal/provider-not-configured copy.
- Provider-missing check: run in an environment without Futu/OpenD and confirm the report degrades to `provider_unavailable` or `source_blocked` without throwing or exposing internals.
- Cloud fallback check: run with Futu/OpenD unavailable and mocked Yahoo chart bars; verify `source_status.indexes.status=partial`, `index_summary[]` contains index rows, `source.provider=yahoo_chart`, and `event_summary[]` contains either dated Yahoo Finance RSS company/theme evidence or, only when dated collection is empty, official disclosure/reference evidence.
- Dated event check: fixture and live-provider smoke must prove at least one `event_summary[]` row can carry `published_at`, `source_id` or URL, linked ticker/theme metadata, and a cited story claim.
- Provider-available check: on cloud or an approved Futu/OpenD environment, generate the current natural week and verify index rows, event/knowledge evidence, and story citations in both Markdown and Web JSON.
- Acceptance retest: after deployment, route `AT-2026-06-28-001` back to Acceptance Testing for a focused source-completeness and story-quality retest.

### Coordinator Return Gate Status

2026-06-28: Development returned `origin/codex/weekly-review-source-completeness` at `ce36764`. The Delivery Coordinator accepted the branch for integration and cherry-picked it locally as `80da965` on `codex/weekly-review-source-completeness-integration`; coordinator state is recorded on the same local branch.

Local coordinator verification passed:

- `python3 -m py_compile investment_knowledge_mcp/futu_provider.py investment_knowledge_mcp/weekly_review.py investment_knowledge_mcp/weekly_review_web.py scripts/smoke_test.py`
- `git diff --check origin/main..HEAD`
- `python3 scripts/audit_delivery_state.py --feature "Weekly review generator"`
- Web HTML render assertions for the new index slot and absence of old provider-not-configured copy
- Mocked weekly-review fixture assertions for index summary, source status, story fields, claims, and Markdown copy

Verification limits:

- Full `scripts/smoke_test.py` could not run in the coordinator environment because PostgreSQL on `localhost:55432` was not reachable.
- Futu/OpenD provider-available verification still requires the cloud or another approved provider environment.
- The branch was later pushed to `main` at `8147cb8`, automatic quick deploy run `28326148823` succeeded, and manual full deploy run `28326192300` succeeded. Cloud HTML verification passed for the new index slot and absence of old provider-not-connected copy. Cloud force-refresh for week `2026-06-22` produced the new story structure, but provider-available verification did not pass: indexes returned `provider_unavailable`, events returned `source_blocked`, and cloud output had no `index_summary` or `event_summary` rows. `AT-2026-06-28-001` must remain `failed` until cloud source/provider evidence is available or Product changes the acceptance bar.

Follow-up cloud-source fix on `codex/weekly-review-cloud-sources`:

- Added `investment_knowledge_mcp/market_data_provider.py` with a no-key Yahoo chart fallback for the required index basket.
- Updated `weekly_review.py` so Futu index failure falls through to Yahoo chart before marking indexes unavailable.
- Added official disclosure/reference fallback evidence for top US/HK/CN holdings and known ETF/product pages, so `event_summary[]` can carry traceable company evidence when live official-source scraping returns no dated documents.
- Reference-only evidence remains partial and keeps `dated_company_events`, `macro_calendar`, and `general_news_theme_feed` visible as blocked categories. This should unblock Coordinator cloud verification of non-empty index/event evidence, but Acceptance Testing must still judge whether the evidence quality satisfies `AT-2026-06-28-001`.

Coordinator verification of the follow-up cloud-source fix:

- Integrated returned commit `31aa130` as main commit `9381a1a`.
- Local checks passed: `py_compile` for changed modules, `git diff --check`, feature delivery audit, and mocked fallback fixture with Futu unavailable, Yahoo index rows present, official-source collection empty, and reference event evidence populated.
- Automatic quick deploy run `28326901616` succeeded; manual full deploy run `28326950490` succeeded.
- Cloud force-refresh for week `2026-06-22` succeeded and saved `/private/tmp/weekly-review-cloud-refresh-20260622.json`.
- Cloud output met the coordinator retest gate: `source_status.indexes.status=partial`, `source_status.indexes.provider=yahoo_chart`, `index_summary` count `7`, `source_status.events.status=partial`, `event_summary` count `6`, `knowledge_evidence` count `16`, and story claims present.
- Remaining quality risks for Acceptance Testing: Futu remains unavailable, Yahoo fallback missed `ChiNext Index` and `STAR 50`, event evidence is reference/partial rather than dated company events, and macro calendar/general news firehose remain blocked.

Acceptance retest return and dated-event fix:

- Acceptance retest branch `origin/codex/weekly-review-acceptance-retest-20260628` at `c32ba3f` was accepted as a valid failed retest. The page/API, Yahoo index fallback, story fields, and old missing-source copy passed, but `event_summary[]` was still only disclosure reference/search URLs with no dated `published_at` event evidence.
- Development branch `codex/weekly-review-dated-events` adds `investment_knowledge_mcp/event_data_provider.py` with a no-key Yahoo Finance RSS provider and wires it into `weekly_review.py` before the disclosure-reference fallback. It queries top portfolio holdings plus bounded theme proxy symbols, filters to dated/relevant company or theme news inside the review week, and emits `published_at`, `source_id`, URL, linked ticker/theme metadata, freshness, summary, and citation fields.
- `source_status.events` now reports provider `yahoo_finance_rss` and checked category `dated_company_or_theme_news` when dated RSS evidence is present. In that case the remaining blocked category is `macro_calendar`; if dated collection is empty, the report still falls back to disclosure/reference URLs and keeps `dated_company_events`, `macro_calendar`, and `general_news_theme_feed` visible as blocked.
- Local verification passed for syntax, a mocked dated-event fixture, and a live Yahoo Finance RSS provider smoke returning dated 2026-06-28 items. Full `scripts/smoke_test.py` remains blocked in this worktree because PostgreSQL on `localhost:55432` is not running.
- Coordinator integrated the dated-event fix as main commit `4fd1008`, automatic deploy run `28328143409` and manual full deploy run `28328183696` both succeeded, and cloud force-refresh for week `2026-06-22` saved `/private/tmp/weekly-review-cloud-dated-events-20260622.json`. Cloud output had `event_summary[]` count `10`, dated `published_at` count `10`, providers including `yahoo_finance_rss`, `source_blocked_categories=["macro_calendar"]`, and a dated external-event story claim with citation. `AT-2026-06-28-001` was moved back to `needs_retest` for independent Acceptance Testing.
- 2026-06-29 user correction: after later main pushes, the live report for week `2026-06-22` again showed old missing-source output (`indexes.status=missing`, `events.status=missing`) until Coordinator ran a manual full deploy of latest `main` commit `37c1060` via GitHub Actions run `28383104668` and force-refreshed the week. Post-correction evidence `/private/tmp/weekly-review-20260622-after-full-deploy-refresh.json` restored the expected source-backed output: `index_summary[]` count `7`, `event_summary[]` count `10`, dated `published_at` count `10`, `source_blocked_categories=["macro_calendar"]`, and a dated external-event story claim. Future acceptance requests must verify the latest deployed main ref, not only an earlier full-deployed SHA.

## Implementation Traceability

### 2026-06-28 development update

Implemented or preserved:

- Six-section weekly Markdown generation remains implemented in `investment_knowledge_mcp/weekly_review.py`.
- Weekly report persistence now updates the latest row for `(report_type, period_start, period_end)` instead of depending on a unique `ON CONFLICT` path, matching the current one-row-per-natural-week contract.
- `db/schema.sql` now handles a legacy `review_reports.report_key` column by backfilling missing keys and dropping the legacy `NOT NULL` requirement so weekly saves do not fail with raw database constraint errors.
- The Web API now separates read, generate, force-refresh, and save:
  - `GET /api/weekly-review?week_start=YYYY-MM-DD` reads only.
  - `POST /api/weekly-review/generate` generates only when missing.
  - `POST /api/weekly-review/refresh` requires `force=true` and overwrites the same weekly row.
  - `POST /api/weekly-review/save` saves submitted Markdown/context without hidden regeneration.
- The Web UI now uses a natural-week selector and product-language source status strings for missing index and external-event sources.

Still follow-up product/tech work:

- External index, macro, news/theme, and opportunity-list providers remain out of scope for this fix and should stay visible as source gaps.
- Full local smoke verification requires PostgreSQL on `localhost:55432`; in this task that database was unavailable, so only syntax and no-database weekly Web contract checks ran locally.

### 2026-07-16 public Web authorization regression fix

The public Weekly Review surface now follows an explicit public-read / privileged-write contract:

| Endpoint or surface | Access contract | Public page exposure |
| --- | --- | --- |
| `GET /weekly-review` | Public | Read-only week navigation, rendered report sections, holder-attribution cards, and report Markdown |
| `GET /api/weekly-review?week_start=YYYY-MM-DD` | Public | Used by the public page to read an existing report or a safe missing-report state |
| `POST /api/weekly-review/generate` | Authenticated | Not exposed |
| `POST /api/weekly-review/refresh` | Authenticated | Not exposed |
| `POST /api/weekly-review/save` | Authenticated | Not exposed |
| Candidate-insight reads and confirm/reject decisions | Authenticated | Not exposed |
| Command Workbench parse/execute | Authenticated | Remains on its controlled surface |

Security reasoning: Weekly Review acceptance is a public read journey, so the browser must not ask users to discover, enter, or persist a service secret. Generation, force refresh, arbitrary save, and candidate decisions can mutate durable data or trigger provider work; they remain authenticated APIs for controlled internal flows. The public page is therefore intentionally read-only and displays a clear missing-report state instead of offering controls that would predictably fail with `401`.

Implementation and verification evidence:

- Removed the read authorization guard from `GET /api/weekly-review` while preserving the existing guards on all privileged endpoints.
- Candidate-insight reads now fail closed when no write token is configured, matching the existing fail-closed mutation behavior.
- Removed the Weekly Review token input, browser `localStorage` token persistence, generate/refresh/save controls, and candidate-decision controls from the public page.
- Added `tests/test_weekly_review_web_auth.py` using `ThreadingHTTPServer` to verify the contract at the HTTP boundary with configured service tokens.
- TDD RED: the new suite initially observed `401` for tokenless Weekly read and found the token/write UX in the public HTML.
- TDD GREEN: the suite verifies tokenless Weekly read `200`, privileged operations `401`, read-only holder-attribution HTML without secret UX, and tokenless Daily Market Brief read `200`.
- A cloud deploy and independent acceptance retest remain required before this regression is ready for user acceptance.
