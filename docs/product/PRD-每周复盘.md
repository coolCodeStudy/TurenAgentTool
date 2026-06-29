# PRD：本周复盘生成器

## 一句话定位

基于富途交易记录、账户/持仓快照、市场指数、新股日历、知识库和外部信息源，自动生成一份可直接阅读的周复盘 Markdown。

这个产品不是先让用户写复盘，再让模型润色；而是系统先把本周真实发生的事情算出来，用户只需要补充主观判断。

## 目标输出

用户输入：

```text
本周复盘
```

系统输出：

```text
# 本周复盘 YYYY-MM-DD ~ YYYY-MM-DD

## 1. 高光时刻
## 2. 炸裂时刻
## 3. 指数
## 4. 整体故事
## 5. 下周展望
## 6. 当前持仓分析
```

第一版重点是把这 6 个模块做实，不追求复杂页面。

## 数据源

### 已有数据源

- `trade_records`：富途历史成交，来自 `get_futu_trade_history` / `补全交易记录`。
- `account_snapshots`：账户信息、持仓快照、汇率快照。
- 实时持仓：`get_futu_positions` / MCP `get_realtime_portfolio_positions`。
- 知识库：个股画像、板块归属、知识项、用户心得、候选心得。
- 港股新股：`get_hk_ipo_list`，可用于下周展望。

### 需要新增或增强的数据源

- 指数行情：美股、A股、港股核心指数的本周涨跌幅和关键日波动。
- 外部事件：雪球、Twitter/X、财报日历、公告、新闻、研报摘要。
- 新股日历：港股已接入，后续补 A 股、美股 IPO / SPAC / 新股首日。
- 主题热度：从持仓股票、交易股票、用户关注股票出发，聚合 AI、内存、光通信、创新药、机器人、加密金融等主题。

## 模块设计

### 1. 高光时刻

定义：本周赚钱最多、执行最好的交易或持仓变化。

第一版计算口径：

- 优先使用 `trade_records` 中本周卖出交易的已实现收益。
- 如果没有完整成本口径，则使用成交后的当前持仓 `realized_pl` / `pl_val` 辅助判断。
- 只展示 Top 3，避免噪音。

输出字段：

| 字段 | 说明 |
| --- | --- |
| 标的 | 股票代码和名称 |
| 类型 | 已实现盈利 / 浮盈扩大 / 买入后上涨 |
| 金额 | 原币种收益或浮盈变化 |
| 触发原因 | 来自交易记录、快照变化或模型总结 |
| 复盘问题 | 为什么赚钱，是否可复制 |

示例：

| 标的 | 类型 | 金额 | 复盘问题 |
| --- | --- | ---: | --- |
| HK.02476 胜宏科技 | 当前持仓浮盈 | +6680 HKD | 是产业趋势判断正确，还是短期情绪给了溢价 |
| HK.07709 南方两倍做多海力士 | 当前持仓浮盈 | +2800 HKD | 杠杆产品是否有清晰止盈计划 |
| US.RKLB Rocket Lab | 当前持仓累计盈亏 | +1001 USD | 继续拿住的条件是什么 |

### 2. 炸裂时刻

定义：本周亏钱最多、执行最差、最需要复盘的交易或持仓变化。

第一版计算口径：

- 优先使用本周已实现亏损交易。
- 其次使用账户快照比较周初/周末持仓浮亏变化。
- 如果快照不足，则使用当前持仓 `pl_val` 和 `pl_ratio` 标记历史拖累，但必须说明不是本周新增亏损。

输出字段：

| 字段 | 说明 |
| --- | --- |
| 标的 | 股票代码和名称 |
| 类型 | 已实现亏损 / 浮亏扩大 / 历史拖累 |
| 金额 | 原币种亏损或浮亏变化 |
| 原因候选 | 买点、仓位、主题失效、事件冲击、流动性 |
| 下周处理 | 继续观察、减仓候选、等待反弹、需要补研究 |

示例：

| 标的 | 类型 | 金额 | 下周处理 |
| --- | --- | ---: | --- |
| HK.09988 阿里巴巴-W | 当前持仓历史拖累 | -9700 HKD | 判断是否仍有配置理由 |
| US.SY 新氧 | 当前持仓历史拖累 | -810 USD | 如果长期逻辑缺失，应进入减仓候选 |
| HK.01810 小米集团-W | 当前持仓历史拖累 | -5900 HKD | 区分基本面判断和沉没成本 |

### 3. 指数

目标：用少量指数解释本周市场环境，不写泛泛市场评论。

第一版指数篮子：

| 市场 | 指数 |
| --- | --- |
| 美股 | Nasdaq 100、S&P 500、SOX 半导体指数、Russell 2000 |
| 港股 | 恒生指数、恒生科技、国企指数 |
| A股 | 沪深300、创业板指、科创50、半导体/通信相关指数 |

输出字段：

| 字段 | 说明 |
| --- | --- |
| 指数 | 指数名称 |
| 本周涨跌 | 周一开盘或上周收盘到本周收盘 |
| 最大单日波动 | 标记大阴线/大阳线 |
| 对组合影响 | AI、半导体、港股成长、A股题材等 |

第一版可以先接行情 API；如果没有行情 API，则模型只允许输出“指数数据缺失”，不能凭印象编。

### 4. 整体故事

这是产品里最需要设计的一块，不能简单让模型自由发挥。

整体故事分三层生成：

#### 4.1 客观市场层

输入：

- 指数本周涨跌。
- 持仓和交易标的的本周涨跌。
- 成交最活跃标的。
- 本周贡献/拖累最大的股票。

输出：

- 本周主线是风险偏好上升、风险偏好下降，还是结构性行情。
- 哪些市场强，哪些市场弱。
- 用户组合和指数表现是否一致。

#### 4.2 事件和舆情层

输入优先级：

1. 持仓公司公告、财报、业绩预告。
2. 雪球热帖和关注股票讨论。
3. Twitter/X 上相关 ticker、主题关键词和关键人物。
4. 财经新闻和宏观数据。
5. 用户本周记录的日志、心得、候选心得。

第一版可以先做“持仓/关注 ticker 事件摘要”，不要做全市场爬虫。

建议关键词：

- AI 基础设施：NVDA、AVGO、MRVL、MU、DRAM、SK hynix、HBM、光通信、CPO、MLCC、玻璃基板。
- 港股成长：阿里、小米、美团、创新药、半导体。
- 高波动主题：Circle、量子、太空、加密金融。

#### 4.3 模型叙事层

模型只做归纳，不直接给交易指令。

输出固定格式：

```text
本周故事：
- 主线：
- 加速因素：
- 负向信号：
- 和我组合的关系：
- 下周验证点：
```

判断规则：

- 至少引用 2 类输入：指数/个股表现/事件/交易记录/用户心得。
- 没有数据就写“本周缺少外部事件数据”，不能脑补。
- 对拥挤交易、主题过热、杠杆产品必须提示风险。

### 5. 下周展望

目标：不是预测市场，而是列出下周需要处理的少数事项。

输入：

- 港股新股列表和申购状态。
- 下周财报、业绩、宏观日历。
- 当前持仓中亏损较大、盈利较大、仓位较大的标的。
- 本周交易后的资金余量和购买力。
- 候选心得和用户历史偏好。

输出字段：

| 字段 | 说明 |
| --- | --- |
| 类型 | 新股 / 财报 / 持仓处理 / 主题观察 / 风险控制 |
| 事项 | 具体股票、事件或动作候选 |
| 为什么重要 | 和组合或历史判断的关系 |
| 需要用户决定 | 是 / 否 |

示例：

| 类型 | 事项 | 为什么重要 | 需要用户决定 |
| --- | --- | --- | --- |
| 新股 | 下周港股新股申购列表 | 判断是否有值得打新的标的 | 是 |
| 财报 | SK hynix / AI memory 相关事件 | 影响海力士两倍、DRAM、MU 主线 | 是 |
| 风险控制 | AI 基础设施仓位集中度 | 当前组合已经明显偏 AI memory/光通信 | 是 |
| 持仓处理 | 历史低效仓位清单 | 为主线仓位腾挪资金，但要避免情绪化割肉 | 是 |

### 6. 当前持仓分析

目标：做一张能直接行动前复盘的表，不写长篇。

数据来源：

- 实时持仓。
- 个股知识库和板块归属。
- 用户已确认心得。
- 候选心得。
- 当前盈亏、仓位、市值、币种。

输出字段：

| 字段 | 说明 |
| --- | --- |
| 市场 | US / HK / CN |
| 标的 | 代码 + 名称 |
| 主题 | 来自知识库或规则映射 |
| 市值 | 原币种 |
| 盈亏 | `pl_val` 和 `pl_ratio` |
| 状态 | 核心持仓 / 观察 / 拖累 / 高波动 / 待处理 |
| 知识库观点 | 已确认知识或心得的一句话 |
| 下周节奏 | 拿住、观察、补研究、减仓候选、等待事件 |

示例：

| 市场 | 标的 | 主题 | 市值 | 盈亏 | 状态 | 下周节奏 |
| --- | --- | --- | ---: | ---: | --- | --- |
| HK | 02476 胜宏科技 | AI PCB/服务器供应链 | 37880 HKD | +6680 / +21.41% | 强势贡献 | 观察是否过热，保留止盈条件 |
| HK | 07709 南方两倍做多海力士 | HBM/AI memory | 10655 HKD | +2800 / +35.65% | 杠杆高波动 | 必须跟踪海力士和 memory 主线 |
| US | DRAM Roundhill Memory ETF | Memory ETF | 2730 USD | +671 / +32.56% | 主线贡献 | 跟踪 memory 是否拥挤 |
| US | SY 新氧 | 非主线/低效仓位 | 722 USD | -810 / -52.88% | 历史拖累 | 进入处理清单 |

## 命令设计

### 生成复盘

```text
本周复盘
周复盘
复盘 2026-06-08 2026-06-14
```

流程：

1. 解析日期范围，默认本周一到今天。
2. 查询/回补本周交易记录。
3. 读取区间账户快照和当前持仓。
4. 计算高光、炸裂、持仓表。
5. 拉取指数和新股日历。
6. 拉取外部事件摘要；如果未接入，明确标记缺失。
7. 调用模型生成“整体故事”和“下周展望”。
8. 保存 `review_reports` 或 Markdown artifact。
9. 生成候选心得，但不写入正式心得。

### 查看下周节奏

```text
查看下周节奏
```

只输出第 5、6 部分，适合工作日快速查看。

### 回补数据

```text
补全交易记录 本周
保存账户快照
```

用于复盘前保证数据完整。

## 计算逻辑

### 高光/炸裂排序

优先级：

1. 本周已实现收益/亏损。
2. 本周浮盈/浮亏变化：需要周初和周末持仓快照。
3. 当前累计盈亏：只能作为背景，不标记为本周事件。

排序：

- 高光：收益金额降序，其次收益率降序。
- 炸裂：亏损金额升序，其次亏损率升序。
- 同一标的多笔交易合并展示。

### 持仓状态标签

规则：

- `核心持仓`：知识库中有明确主线，且仓位/市值靠前。
- `强势贡献`：`pl_val > 0` 且 `pl_ratio` 位于前 20%。
- `历史拖累`：`pl_val < 0` 且亏损金额靠前。
- `高波动`：量子、加密、太空、杠杆 ETF、IPO 新股等。
- `待处理`：用户历史复盘中出现“等机会卖出、清掉、感觉不大、垃圾”等表达。
- `补研究`：持仓较大但知识库缺失。

### 整体故事生成约束

- 模型必须拿结构化 facts 作为输入，不直接查一堆网页后自由发挥。
- 每条故事要能追溯到：指数、个股表现、交易记录、事件源、用户心得之一。
- 事实和推断分开展示。
- 推断只能进入 `candidate_insights`，不能进入正式 `user_insights`。

## 2026-06-28 Product Acceptance Addendum: Source Completeness And Story Quality

This addendum resolves failed user acceptance item `AT-2026-06-28-001`. The prior Web-flow acceptance result only proves that the page can read, generate, refresh, save, and degrade safely. It does not make Weekly Review product-complete. A generated report is product-acceptable only when it explains why the week happened using source-backed market, event, theme, portfolio, and user-knowledge inputs.

### Minimum Index Context

Required acceptance basket:

| Market | Required indexes |
| --- | --- |
| US | S&P 500, Nasdaq 100, SOX Semiconductor Index |
| Hong Kong | Hang Seng Index, Hang Seng Tech Index, Hang Seng China Enterprises Index |
| Mainland China | CSI 300, ChiNext Index, STAR 50 |

Required weekly metrics for each available required index:

- Weekly change over the review week, using a consistent close-to-close or prior-close-to-week-close convention that is named in `source_status`.
- Largest daily move during the review week, including date, direction, and percent move when available.
- A market-environment label such as broad risk-on, broad risk-off, growth-led, semiconductor-led, Hong Kong growth-led, A-share theme-led, or mixed/rotation.
- Portfolio/theme relevance, explicitly mapping the index move to the user's holdings, trades, and dominant themes such as AI infrastructure, HBM/memory, optical communication, Hong Kong growth, innovative drugs, crypto finance, robotics, or other detected themes.

Degraded behavior:

- If one required index is unavailable but the provider returns other indexes for the same market, the report may still generate as `partial` and must name the missing index, show the remaining evidence, and avoid claims that depend on the missing index.
- For product acceptance, each active portfolio market in the review week must have at least one representative broad index available, and AI/semiconductor or growth exposure must have at least one relevant proxy available when those themes are material to holdings or trades.
- If an entire active market's index coverage is unavailable, or if the report cannot provide any relevant proxy for a material portfolio theme, the report may be shown as a transparent source-blocked draft but must not be considered product-acceptable.

### Minimum External Event, News, And Theme Context

Required event categories for acceptance:

| Category | Minimum bar |
| --- | --- |
| Holding company announcements and earnings | For top holdings, largest contributors, largest detractors, new positions, and closed positions, check company announcements, earnings, guidance, filings, or exchange notices during the review week. |
| Macro and market calendar | Check major central-bank, rates, inflation, jobs, liquidity, and market-calendar items that plausibly explain broad index movement during the week. |
| Sector and theme news | Check material theme-level news for the user's active themes, especially AI infrastructure, memory/HBM, semiconductors, optical communication/CPO, Hong Kong growth, innovative drugs, crypto finance, robotics, and other themes detected from holdings/trades. |
| User knowledge and insights | Include relevant `user_insights`, `candidate_insights`, `knowledge_items`, sector mappings, and prior review context already stored in the local knowledge base. |

Source freshness and evidence expectations:

- External company, macro, and theme sources should be from the review week, or from the nearest prior dated event that was clearly still being priced during the review week.
- Next-week outlook items may include dated calendar events within the next 14 calendar days.
- Every external event used in the story must carry at least source name, publication or event date, title/description, URL or stable source identifier, and the linked ticker/theme when applicable.
- Internal knowledge sources must carry the source type and local identifier or summary so a reviewer can trace the statement back to knowledge, insight, candidate insight, or sector mapping data.
- If a required provider returns no relevant events, the report should say the category was checked and no material event was found. If the provider is unavailable or not implemented, that is a source gap, not a passing empty result.

Acceptable first implementation pass:

- A bounded provider set is acceptable: one reliable market-index provider, one company-announcement or earnings/calendar source, one general news/theme source, and the existing local knowledge-base sources.
- The first pass may prioritize holdings, trades, top contributors/detractors, and detected portfolio themes instead of crawling the entire market.
- Raw social-media firehose ingestion, sentiment scoring, full research-report summarization, paid data-only sources, and one-click promotion of generated ideas into formal user insights remain out of scope unless a later product decision adds them.
- Social or community summaries may be included only when source freshness and citation metadata meet the evidence bar above; otherwise they should be omitted rather than paraphrased from memory.

### Overall Story Acceptance Bar

The overall story must be useful enough to explain why the week happened, not only list what changed in the holdings snapshot.

Minimum input diversity for product acceptance:

- Portfolio/trade facts: highlights, blowups, position changes, and current holdings table.
- Index facts: required broad and theme-relevant index context for active markets.
- Event/theme facts: at least one checked external company, macro, or sector/theme event category relevant to the week's portfolio movement.
- User knowledge facts: relevant stored knowledge, insights, candidate insights, or sector mappings when available.

Required story structure:

```text
本周故事：
- 主线：
- 市场环境：
- 组合归因：
- 事件/主题证据：
- 负向信号：
- 和我组合的关系：
- 下周验证点：
```

Each story claim must separate observed facts from interpretation and cite one or more structured inputs: index, holding/transaction, external event, user knowledge, or source-status fact. The model may summarize and connect evidence, but it must not invent market causes, company events, or social sentiment.

Missing-source handling:

- Missing required sources should produce a clearly labeled source-blocked or partial draft, with the missing categories and next engineering/data action visible.
- The product must not pass acceptance merely because it says data is missing. If missing sources prevent the story from explaining the market and portfolio drivers, the acceptance result remains failed or blocked until sources are implemented or an explicit product decision removes that source from scope.
- The page should still preserve safe degraded behavior: no raw provider names, table names, stack traces, or internal implementation messages as normal user copy.

### Engineering Handoff Requirement

Before implementation resumes, Engineering must update `docs/techplans/weekly-review.md` to cover:

- Source providers and schemas for required indexes, company/earnings/calendar events, macro/calendar items, sector/theme news, and local knowledge inputs.
- `source_status` semantics for `ok`, `partial`, `checked_empty`, `missing`, `provider_unavailable`, and `source_blocked`.
- Story-generation input contract, citation/evidence fields, and source-to-claim traceability.
- Fallback and degraded behavior that distinguishes product-acceptable partial data from source-blocked drafts.
- Verification plan, including fixture-level checks, provider-missing checks, cloud Weekly Review checks, and a focused acceptance retest for `AT-2026-06-28-001`.

Implementation should not proceed from the old P1/P2 split that treated index and external-event sources as non-blocking future enhancements. That split is superseded for the source-completeness and story-quality acceptance scope.

## 2026-06-30 P1 Product Addendum: Holder-Level Attribution

This addendum defines the next P1 follow-up after Weekly Review V1 user acceptance. The user accepted the V1 report as useful, but a top holding row such as `胜宏科技 HK.02476 | 盈利回撤 | -6,920.00 HKD | 持仓未变 / 高 | 拖累来自持仓表现，需要确认逻辑是否变化` is still too blind for investment use. A contributor or drag row must explain why the move may have happened, how well the explanation is supported, whether the user's thesis changed, and what should be validated next.

### Product Scope

P1 holder-level attribution applies to the largest contributors and laggards in the Weekly Review, not to every holding. The first pass should cover:

- Top 3 positive contributors and top 3 negative contributors by weekly holding attribution, using the existing ranking logic.
- Any additional holding that is both a material position and marked `core`, `high_volatility`, or `needs_research` when it is not already in the top contributor/laggard set.
- Both Markdown and Web surfaces, with the same underlying structured attribution data.

For each covered holding, the report must say more than price and P/L:

| Field | Required product meaning |
| --- | --- |
| Attribution verdict | Whether the move is likely market/benchmark-driven, theme/sector-driven, single-stock-event-driven, fundamental/cost-driver-driven, position/trade-behavior-driven, thesis/knowledge-driven, mixed, or unexplained. |
| Cause candidates | 1-4 possible explanations, each with evidence, source type, date, and confidence. |
| Evidence trace | Source name, source type, date, URL or stable local identifier, and the claim it supports. |
| Confidence | `high`, `medium`, `low`, or `rumor_watch`, based on source quality and corroboration. |
| Thesis impact | `supports_thesis`, `challenges_thesis`, `neutral_noise`, `needs_research`, or `invalidates_unless_confirmed`. |
| Next validation | The next concrete check: announcement, earnings/guidance, margin/cost trend, upstream input price, sector index, peer move, user thesis note, or trade/risk review. |

The output may say "no supported cause found" when source coverage is insufficient. That is preferable to a confident but unsupported explanation.

### Attribution Pattern

Each holder-level attribution card should decompose the move across these lenses:

| Lens | Examples of evidence | Product behavior |
| --- | --- | --- |
| Market / benchmark | Active-market broad index, risk-on/risk-off label, exchange-wide selloff or rally. | Use when the holding moved with the market; do not overfit stock-specific explanations. |
| Theme / sector | Semiconductor, AI infrastructure, PCB, HBM/memory, optical communication, Hong Kong growth, innovative drugs, crypto finance, robotics, or other mapped themes. | Explain whether the holding followed or diverged from the theme basket. |
| Single-stock event | Company announcement, earnings, guidance, customer/order news, regulatory notice, major media item, dated market essay. | Prefer official/company or reputable dated sources; cite date and source. |
| Fundamentals / cost drivers | Revenue/order expectation, gross margin, upstream material prices, copper/fiberglass/laminate/PCB supply-chain cost pressure, utilization, pricing power, FX, rates. | Treat as a driver candidate unless confirmed by company data or multiple reliable sources. |
| Position / trade behavior | Added, reduced, unchanged, new, closed, leverage/ETF exposure, realized/unrealized split. | Explain whether the user's own position behavior amplified or reduced the weekly impact. |
| User thesis / knowledge | Confirmed insights, candidate insights, stock/sector knowledge, prior review thesis, watch conditions. | Explicitly state whether the week's evidence supports or challenges the user's stored thesis. |

The report should distinguish:

- `Observed`: price/P&L, index/theme moves, position/trade changes, dated source facts.
- `Inferred`: likely relationship between evidence and holding performance.
- `Unverified`: rumor, social discussion, single unconfirmed essay, or a plausible cost-driver narrative without direct confirmation.

### Rumor, Social, And Market-Essay Evidence

Social evidence such as Xueqiu posts, Twitter/X posts, forum discussion, market essays, broker chat summaries, and reposted rumors may be used only as labeled cause candidates. The system must not launder these into facts.

Allowed P1 source handling:

| Source type | Allowed label | Confidence ceiling | Requirements |
| --- | --- | --- | --- |
| Official company announcement, exchange filing, earnings call, audited report | `official` | `high` | Date, title, URL or filing id, linked ticker. |
| Reputable financial news, market data provider news, dated industry publication | `news_or_industry` | `medium` unless corroborated | Date, title, URL/source id, linked ticker/theme. |
| Dated market essay or analyst-style public article | `market_essay` | `medium` when evidence-based; otherwise `low` | Date, author/source when available, URL/source id, separated facts vs opinion. |
| Xueqiu, Twitter/X, forums, reposted screenshots, unsourced rumor | `social_rumor` | `rumor_watch` | Date, platform/source, URL/source id when available, exact claim summary, and clear "unverified" label. |
| Local user insight or candidate insight | `user_knowledge` | follows its stored status | Local identifier or summary and whether it is confirmed or candidate. |

Rumor/social rules:

- A rumor may explain "what the market may be trading" but not "what is true."
- Rumor/social evidence cannot be the only basis for `high` or `medium` confidence.
- If a rumor is paired with price action but no corroborating official/news/fundamental source, the card should use `rumor_watch` and `thesis_impact=needs_research`.
- If later official evidence confirms or refutes the rumor, the official evidence should supersede the rumor while keeping traceability to the prior watch item when useful.
- The system should not scrape or bypass login-gated social feeds in P1 unless a compliant provider or user-supplied source artifact is available.

Non-goals for this P1:

- No live Xueqiu scraping requirement.
- No full social-media firehose, sentiment score, or popularity ranking.
- No automatic trading instruction or stop-loss/take-profit command.
- No promotion of rumor-derived claims into formal user insights without explicit user confirmation.
- No claim that an attribution cause is definitive unless evidence actually supports that standard.

### Output Shape

Markdown should add a holder-level attribution subsection under highlights/blowups or immediately after the current holdings table:

```text
### 持仓归因卡：HK.02476 胜宏科技

- 本周影响：盈利回撤 -6,920.00 HKD；持仓未变；归因置信度：position high / cause low-to-rumor_watch
- 归因判断：mixed / single-stock-event-watch + cost-driver-watch
- 可能原因：
  1. Q2 performance miss rumor or market essay discussion
     - Evidence: social_rumor or market_essay, source/date/link if available
     - Confidence: rumor_watch or low
     - Thesis impact: needs_research
  2. Upstream material/cost inflation pressure for PCB supply chain
     - Evidence: industry/news/cost-driver source/date/link when available
     - Confidence: low or medium depending on corroboration
     - Thesis impact: challenges_thesis if margin pressure is relevant to the stored thesis
- 和我的逻辑关系：If the thesis is AI PCB demand growth, the next check is whether cost pressure only compresses short-term margin or also weakens order/growth assumptions.
- 下周验证点：check company announcement/earnings guidance, gross-margin commentary, upstream copper/laminate/cost trend, peer PCB movement, and whether user thesis notes mention margin tolerance.
```

Web should expose the same content as a compact expandable attribution card for each covered holding:

| Web element | Required behavior |
| --- | --- |
| Attribution badge | Shows dominant attribution lens and confidence, such as `Theme + Rumor Watch` or `Market-driven / Medium`. |
| Cause candidate list | Shows candidate title, confidence label, source type, source/date, and one-line evidence. |
| Evidence links | Link or stable source id is visible when available; local knowledge ids may be rendered as traceable labels. |
| Thesis impact | Uses product-language labels; does not issue trade instructions. |
| Next validation | Shows the next concrete check as an action-oriented research item. |
| Source gap state | If no usable evidence exists, the card says which source category is missing and what provider/user input would unblock it. |

The Web card must not show raw stack traces, provider exceptions, database table names, or internal prompts.

### Acceptance Criteria

P1 holder-level attribution is acceptable when:

1. A generated Weekly Review includes structured attribution cards for the top contributors and laggards defined in scope.
2. Each card includes attribution verdict, cause candidates or a transparent "no supported cause found" state, evidence/source/date, confidence label, thesis impact, and next validation.
3. Cause candidates cover the practical lenses of market/benchmark, theme/sector, single-stock event, fundamentals/cost drivers, position/trade behavior, and user thesis/knowledge when relevant evidence exists.
4. Rumor/social evidence is labeled as `social_rumor` or equivalent user-facing copy, capped at `rumor_watch`, and never rewritten as confirmed fact.
5. The system can represent a Xueqiu-style or market-essay claim when supplied by a compliant provider, cached artifact, manual source input, or other approved source path; live Xueqiu scraping is not required for P1 acceptance.
6. A Shenghong Technology (`HK.02476` / `胜宏科技`) style laggard card can show both "Q2 miss rumor/market essay" and "upstream cost inflation pressure" as separate cause candidates when those sources are present, with different confidence and thesis-impact labels.
7. If those Shenghong sources are not present, the card still remains actionable by showing missing source categories and next validation steps instead of a generic "holding performance drag" sentence.
8. Markdown and Web output are consistent in content, source traceability, confidence labels, and source-gap behavior.
9. New attribution inferences remain candidate-level and do not automatically write formal user insights.

Acceptance-test focus:

- Fixture test with `HK.02476` as a top laggard, unchanged position, negative weekly attribution, one supplied Xueqiu-style rumor/essay source about possible Q2 miss, and one supplied industry/cost source about upstream cost inflation. Expected: two separate candidates, rumor labeled `rumor_watch`, cost-driver labeled according to source quality, thesis impact `needs_research` or `challenges_thesis`, and concrete next validation.
- Fixture/provider-missing test with the same holding but no social/news/cost sources. Expected: no invented cause; visible source gap and next validation.
- Cross-lens test where a holding moved with its benchmark/theme. Expected: market/theme attribution is allowed and the system does not force a single-stock story.
- Web rendering test for compact/expanded attribution cards, evidence labels, and absence of raw internals.
- Markdown rendering test for readable attribution cards with traceable evidence and confidence labels.

### Recommended Development Handoff Scope

Development should update `docs/techplans/weekly-review.md` before implementation, then implement the holder-level attribution context and renderers. Recommended technical scope:

- Add a structured `holder_attribution[]` context field keyed by ticker/name and linked to `highlights`, `blowups`, `holdings_table`, `event_summary`, `index_summary`, `knowledge_evidence`, and trade/position-change facts.
- Add source classification and confidence rules for `official`, `news_or_industry`, `market_essay`, `social_rumor`, and `user_knowledge`.
- Add cause-candidate generation that decomposes market/theme/single-stock/fundamental-cost/position/user-thesis lenses without claiming certainty.
- Add Markdown and Web rendering for attribution cards.
- Add fixtures for the Shenghong `HK.02476` acceptance scenario, provider-missing fallback, and source-label safety.
- Keep live Xueqiu scraping out of scope unless Product and Engineering approve a compliant provider path.

## 数据模型影响

第一版复用现有表：

- `trade_records`
- `account_snapshots`
- `review_reports`
- `user_insights`
- `candidate_insights`
- `knowledge_items`
- `command_events`

建议增强 `review_reports`：

```text
report_date
period_start
period_end
source_status      -- trade/snapshot/index/ipo/story 数据完整度
portfolio_snapshot
highlights         -- 高光时刻 JSON
blowups            -- 炸裂时刻 JSON
index_summary      -- 指数 JSON
story              -- 整体故事 JSON/Text
next_week          -- 下周展望 JSON
holdings_table     -- 当前持仓分析 JSON
candidate_insights -- 本次提炼的候选心得
summary
created_at
```

如果暂时不改表，可以先把完整 Markdown 存 `summary`，其余结构存在 `portfolio_snapshot` / `risks` / `opportunities`。

## P1 验收标准

- `本周复盘` 可以直接使用交易记录和持仓快照生成报告。
- 报告必须包含高光、炸裂、指数、整体故事、下周展望、当前持仓分析 6 个部分。
- 高光/炸裂至少基于交易记录或持仓快照，不能纯模型编写。
- 当前持仓分析必须是 table，并结合知识库输出主题、状态和下周节奏。
- 指数数据缺失时要显式说明缺失，不能臆测。
- 整体故事必须标记输入来源和数据缺口。
- 新产生的观点只能进入候选心得。
- 所有命令不允许交易、不调用解锁。
- The 2026-06-28 source-completeness addendum supersedes the older degraded-source acceptance bar for `AT-2026-06-28-001`: missing index and external-event providers can be safely displayed, but they are no longer sufficient for product acceptance when they prevent a source-backed weekly story.

## P2 增强

- 接入雪球/Twitter/X 的持仓相关事件抓取；minimum external event coverage is now required by the 2026-06-28 addendum, while broad social firehose ingestion remains P2.
- 接入财报日历和宏观日历；minimum calendar/event coverage is now required by the 2026-06-28 addendum before source-completeness acceptance can pass.
- 自动比较本周复盘和上周“下周展望”，判断哪些被验证、证伪或遗漏。
- 支持用户对每个候选心得一键确认/拒绝。
- 支持 Web 页面，但第一版仍以 Markdown 为主。

## 产品原则

- 先算真实交易和快照，再让模型总结。
- 复盘只服务决策质量，不堆信息。
- 对用户亏损和错误执行要直接指出，但不输出买卖指令。
- 外部故事必须可追溯，不允许模型凭空讲市场。
- 长期看，产品价值来自“每周生成 -> 下周验证 -> 心得沉淀”的闭环。
