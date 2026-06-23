# PRD: Kline Agent

## 1. Background

InvestmentKnowledge is becoming a personal investment research, review, and memory operating system. It already has stock research, user insights, decision cards, portfolio snapshots, Futu position/trade access, valuation research, and weekly review workflows.

The missing market-behavior layer is structured Kline analysis. The user often wants to understand whether a stock's recent price behavior has historical patterns across daily, weekly, and monthly charts:

> When this stock enters a similar Kline state, what has usually happened next, and how strong is the evidence?

The Kline Agent should not become a trading oracle. Its product value is to turn chart observations into traceable, statistically grounded market-behavior evidence that can support stock research, decision cards, and weekly reviews.

## 2. User Problem

The user can manually inspect charts, but manual chart reading has several problems:

- It is easy to overfit a visual pattern after seeing the latest move.
- It is hard to remember how a stock historically behaved after similar daily, weekly, or monthly structures.
- It is hard to compare daily noise with weekly and monthly trend context.
- It is hard to know whether the current move is stock-specific, sector-wide, or market-driven.
- Existing research and valuation flows capture business facts and assumptions, but not enough structured price-behavior evidence.
- Existing weekly review planning already identifies market behavior as important, but historical Kline analysis is not yet implemented as a reusable product module.

## 3. Product Positioning

The Kline Agent should be:

> A read-only market-behavior evidence agent that investigates daily, weekly, and monthly Kline patterns for a stock, reports historical samples and failure conditions, and feeds traceable observations into the investment workflow.

It should not be:

- An automated trading system.
- A short-term prediction bot.
- A generic technical-indicator dashboard.
- A model that invents chart patterns without deterministic evidence.
- A replacement for fundamental research, valuation, or portfolio risk review.

## 4. Goals

### 4.1 V1 Goals

V1 should prove that the system can produce trustworthy single-stock Kline investigation reports.

Goals:

- Analyze one stock at a time across daily, weekly, and monthly timeframes.
- Fetch and normalize historical OHLCV data from a primary source and optional fallback source.
- Make data source, adjustment type, timezone, currency, and freshness visible.
- Apply a fixed deterministic pattern library instead of allowing the LLM to invent patterns.
- For every pattern observation, show sample count, forward return distribution, worst case, drawdown, and failure condition.
- Separate facts, statistics, and interpretation in the report.
- Return "insufficient evidence" when sample size or data quality is weak.

### 4.2 V2 Goals

V2 should connect trusted Kline evidence to the user's normal investment workflow.

Goals:

- Scan portfolio positions and watchlist stocks automatically.
- Detect material market-behavior changes with low noise.
- Feed market-behavior evidence into decision cards.
- Add relevant Kline observations to weekly reviews.
- Compare a stock's behavior with indexes, sectors, and theme baskets.
- Propose candidate observations for user confirmation when an observation may become durable investment memory.

## 5. Why Split V1 And V2

The split is a trust ladder, not a way to defer ordinary implementation work.

V1 is needed because Kline analysis has a high hallucination and overfitting risk. Before the system can safely scan holdings or influence recurring review workflows, it must prove three foundations:

- Data reliability: adjustment types, missing trading days, source freshness, and timeframe aggregation must be validated.
- Statistical usefulness: pattern observations must have enough sample support and must not be visual storytelling.
- Communication quality: the report must clearly separate fact, statistics, interpretation, and non-advice watch items.

V2 automation should begin only after V1 report quality is trusted. Portfolio scanning and notifications can quickly become noisy if the rule library, data quality checks, or output tone are not stable.

## 6. Non-Goals

- Do not place trades or prepare trade orders.
- Do not output direct buy, sell, or hold instructions.
- Do not optimize intraday or high-frequency strategies.
- Do not expose a large indicator menu as the primary experience.
- Do not let LLM-generated patterns become facts.
- Do not write inferred observations into formal user insights without confirmation.
- Do not require chart rendering in V1, although chart rendering can be added later.

## 7. Target Users

Primary user:

- The investment system owner who wants to understand market behavior for held stocks, watchlist stocks, or stocks under research.

Secondary users:

- Future agents that need market-behavior evidence for decision cards, weekly reviews, or research drafts.
- Operators who need to verify historical price evidence for a stock.

## 8. Core User Stories

### V1 User Stories

1. As a user, I can ask for a Kline investigation of one stock and receive a concise daily, weekly, and monthly report.
2. As a user, I can see which data source and adjustment type were used.
3. As a user, I can see whether a pattern is statistically supported or evidence is insufficient.
4. As a user, I can see historical examples similar to the current state, including average forward return, worst outcome, and drawdown.
5. As a user, I can understand watch points without receiving a direct trading recommendation.

### V2 User Stories

1. As a user, I can scan my portfolio and watchlist for important Kline state changes.
2. As a user, I can see market-behavior evidence inside a stock decision card.
3. As a user, I can see whether a stock's move is stronger or weaker than its index, sector, or theme basket.
4. As a user, I can confirm or reject a recurring Kline observation as part of my long-term investment memory.
5. As a user, I can review weekly market-behavior changes without receiving noisy daily chart commentary.

## 9. Core Flow

### 9.1 V1 Single-Stock Investigation Flow

```text
User request
  -> resolve stock entity
  -> select provider and adjustment type
  -> fetch daily OHLCV data
  -> validate data quality
  -> derive weekly and monthly bars
  -> run deterministic pattern library
  -> compute historical sample statistics
  -> generate structured report
  -> optionally attach observation to a decision card as evidence
```

### 9.2 V2 Monitoring Flow

```text
Portfolio/watchlist scan
  -> fetch or reuse cached Kline data
  -> detect material rule triggers
  -> rank observations by evidence and user relevance
  -> suppress noisy or low-sample observations
  -> surface important changes in decision cards and weekly review
  -> propose candidate insights only when durable memory may be useful
```

## 10. Functional Scope

### 10.1 V1 Functional Scope

#### Inputs

Required:

- Stock symbol and market.

Optional:

- Date range, defaulting to a meaningful multi-year window when available.
- Adjustment type: raw, forward-adjusted, backward-adjusted, or provider-equivalent terms.
- Timeframes: daily, weekly, monthly. Default: all three.
- Specific user question, such as "what usually happens after a new high?" or "what happened historically after breaking the 20-week moving average?"

#### Output Sections

Default report sections:

- Metadata: symbol, market, provider, provider symbol, adjustment type, timezone, currency, date range, fetched time.
- Data quality: missing dates, source warnings, sample size, fallback usage, cross-source differences if checked.
- Monthly structure: long-cycle trend state and major drawdown/recovery context.
- Weekly structure: intermediate trend, support/resistance proxy levels, moving-average state, and current structure.
- Daily structure: recent volatility, volume behavior, gaps, short-term extension, and current trigger state.
- Historical pattern observations: deterministic rule outputs with sample statistics.
- Current watch items: price/volume/structure items to monitor, without direct trading instructions.
- Evidence limits: what cannot be concluded from the data.

#### Fixed V1 Pattern Library

V1 should start with a small rule library:

- New high behavior: 52-week high, all-time high, and failed breakout.
- Moving-average state: break, reclaim, and distance from 20-day, 60-day, 20-week, and 40-week averages.
- Volume-price behavior: high-volume up day, high-volume down day, volume breakout, volume stalling.
- Gap behavior: gap up, gap down, gap fill, unfilled gap persistence.
- Consecutive moves: consecutive up days/weeks, consecutive down days/weeks, and reversal after streaks.
- Drawdown/recovery: pullback from recent high, reclaim after drawdown, and recovery time.

Each rule must define:

- Trigger condition.
- Minimum lookback.
- Minimum sample threshold.
- Forward windows to evaluate, such as 5, 20, and 60 trading days for daily rules.
- Metrics to compute.
- Conditions under which the rule should not be shown.

#### Required Statistics

Each observation should include:

- Sample count.
- Mean and median forward return.
- Win rate.
- Best and worst sample.
- Maximum adverse excursion or drawdown.
- Recovery time where relevant.
- Current trigger status.
- Confidence level derived from data quality and sample count, not from model tone.

### 10.2 V2 Functional Scope

V2 should add:

- Portfolio and watchlist scanning.
- Alert ranking and suppression.
- Decision-card integration through a `Market Behavior Evidence` section.
- Weekly review integration for material changes.
- Relative strength against indexes, sectors, and theme baskets.
- Candidate observation confirmation.
- Saved Kline analysis history so later reviews can validate whether observations were useful.

## 11. Data Source Strategy

### 11.1 Product Principle

The Kline Agent's credibility comes from:

```text
data source + adjustment type + deterministic rules + sample statistics + traceability
```

It does not come from a model sounding confident.

### 11.2 Recommended Source Hierarchy

Primary source:

- Futu OpenD should be the default source because the repository already depends on `futu-api`, existing provider code already reads Futu positions/trades/IPO data, and the weekly review PRD already identifies Futu market behavior APIs as preferred sources.

Fallback and validation sources:

- AkShare: useful for local prototyping, A-share/HK/US fallback, and cross-checking. It should not be the only trusted production source because its own documentation limits use to research, warns about data risk, and notes some interfaces may be removed.
- LongPort: a strong broker-style alternative to Futu for HK/US/A-share historical candlesticks, with explicit history ranges and rate limits.
- EODHD or Alpha Vantage: useful as global market fallback when Futu does not cover a market well, such as some international stocks.
- Polygon/Massive or Alpaca: useful for deeper US equity bar data and future US-specific backtesting, if paid access is approved.

### 11.3 Provider Selection Rules

V1 default:

1. Use Futu when available for the requested market and symbol.
2. Use AkShare only as explicit fallback, prototype mode, or cross-check source.
3. If Futu and AkShare cannot provide the requested symbol, return a clear provider limitation instead of fabricating an answer.

Future provider routing:

| Market / Use Case | Preferred Provider | Fallback |
| --- | --- | --- |
| Existing portfolio stocks covered by Futu | Futu OpenD | AkShare or LongPort |
| A-share research prototype | Futu OpenD | AkShare |
| HK / US research prototype | Futu OpenD | LongPort or AkShare |
| US deep historical bars | Polygon/Massive or Alpaca | Alpha Vantage |
| Global stocks not covered by Futu | EODHD or Alpha Vantage | Manual source import |

### 11.4 Source References

- Futu historical candlesticks: <https://openapi.futunn.com/futu-api-doc/en/quote/request-history-kline.html>
- Futu quote definitions: <https://openapi.futunn.com/futu-api-doc/en/quote/quote.html>
- LongPort history candlesticks: <https://open.longportapp.com/docs/quote/pull/history-candlestick>
- Polygon/Massive custom bars: <https://polygon.io/docs/stocks/get_v2_aggs_ticker__stocksticker__range__multiplier___timespan___from___to>
- Alpaca historical bars: <https://docs.alpaca.markets/reference/stockbars>
- Alpha Vantage documentation: <https://www.alphavantage.co/documentation/>
- EODHD historical data: <https://eodhd.com/financial-apis/api-for-historical-data-and-volumes/>
- AkShare stock data: <https://akshare.akfamily.xyz/data/stock/stock.html>
- AkShare special notice: <https://akshare.akfamily.xyz/special.html>
- AkShare data tips: <https://akshare.akfamily.xyz/data_tips.html>

## 12. Data Quality Requirements

Every Kline result must preserve:

- Provider name.
- Provider symbol.
- Market.
- Currency.
- Timezone.
- Period.
- Adjustment type.
- Date range.
- Fetch timestamp.
- Raw bar count.
- Missing-data warnings.
- Corporate-action or adjustment warnings when available.

Validation requirements:

- Reject or warn on duplicated dates.
- Reject or warn when OHLC values are impossible, such as high below low.
- Warn when adjusted prices are zero or negative unless the provider explicitly documents the condition and the rule can still be computed safely.
- Warn when daily-to-weekly/monthly aggregation does not match provider weekly/monthly data beyond a tolerance, if a cross-check is available.
- Warn when the latest bar may be incomplete.

## 13. Data Model Impact

The exact schema should be finalized in the technical plan, but the product needs durable traceability for three entities:

### 13.1 Kline Bars

Purpose:

- Cache normalized OHLCV bars so repeated analysis is reproducible and provider quotas are controlled.

Suggested fields:

- `market`
- `symbol`
- `provider`
- `provider_symbol`
- `period`
- `adjust_type`
- `bar_time`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `turnover`
- `currency`
- `timezone`
- `fetched_at`
- `source_hash`

### 13.2 Kline Analysis Runs

Purpose:

- Preserve each report's inputs, data version, rule version, and generated output.

Suggested fields:

- `stock_id`
- `requested_symbol`
- `market`
- `provider`
- `date_range`
- `adjust_type`
- `rule_version`
- `data_quality_summary`
- `report_summary`
- `created_at`

### 13.3 Pattern Observations

Purpose:

- Store rule outputs that may later appear in decision cards, weekly reviews, or candidate insights.

Suggested fields:

- `analysis_run_id`
- `rule_id`
- `timeframe`
- `trigger_date`
- `sample_count`
- `forward_window`
- `mean_return`
- `median_return`
- `win_rate`
- `max_drawdown`
- `worst_sample`
- `confidence`
- `observation_text`
- `needs_user_confirmation`

## 14. Command And Entrypoint Impact

V1 should expose at least one controlled command or MCP entrypoint.

Possible command examples:

```text
K线 US.NVDA
K线 HK.00700
K线 000660 KR
K线调查 US.NVDA 5年 前复权
```

Possible MCP-style tool:

```text
inspect_kline_behavior(symbol, market, range, adjust_type, timeframes)
```

The command router should:

- Resolve stock entities using existing stock profiles when possible.
- Refuse ambiguous names and show candidate symbols.
- Require explicit market when a symbol is ambiguous across markets.
- Return a read-only report only.

## 15. Decision Card And Weekly Review Impact

### 15.1 Decision Card

Decision cards should eventually include:

```text
Market Behavior Evidence
- Trend state: strong / neutral / weakening / damaged
- Current key levels
- Active pattern observations
- Historical sample summary
- Failure conditions
- Data freshness
```

This section should remain evidence, not advice.

### 15.2 Weekly Review

Weekly review should eventually include:

- Material Kline changes for held stocks.
- Market-behavior confirmation or contradiction for key themes.
- Stocks whose weekly or monthly structures changed meaningfully.
- Candidate observations that may deserve user confirmation.

## 16. Permission And Safety Boundaries

- The Kline Agent is read-only.
- It must not call trade APIs.
- It must not generate direct buy/sell/hold instructions.
- It must show source and data-quality context for every report.
- It must mark low-sample observations as low confidence or insufficient evidence.
- It must not treat model interpretation as a stored user opinion.
- It must route durable personal investment lessons through the candidate-insight confirmation workflow.
- It must preserve user raw text when the user supplies a hypothesis or market observation.

## 17. UX Principles

- Default to concise evidence, not a textbook indicator dump.
- Show the most relevant 3-5 observations first.
- Put source metadata and warnings near the top.
- Make "insufficient evidence" feel like a useful answer, not a failure.
- Use consistent labels for facts, statistics, interpretation, and watch items.
- Avoid alert fatigue in V2 by ranking only material changes.

## 18. Acceptance Criteria

### 18.1 V1 Acceptance Criteria

V1 is acceptable when:

- A user can request a Kline investigation for one supported stock.
- The report includes daily, weekly, and monthly sections.
- The report includes provider, provider symbol, adjustment type, timezone, currency, date range, and fetch time.
- The system applies only deterministic rules from the approved rule library.
- Each shown pattern has sample count and forward-performance statistics.
- Low-sample patterns are hidden or clearly marked as insufficient evidence.
- Data quality warnings are displayed when relevant.
- The report includes watch items without direct trading instructions.
- The analysis can be reproduced from stored provider, rule version, date range, and adjustment type.

### 18.2 V2 Acceptance Criteria

V2 is acceptable when:

- The system can scan current portfolio positions or a watchlist.
- The scan ranks important observations and suppresses low-value noise.
- Decision cards can display market-behavior evidence.
- Weekly review can include material Kline changes.
- Relative strength can compare a stock against at least one index or sector proxy.
- Candidate durable observations require user confirmation before becoming formal insights.
- The user can trace each alert back to data source, rule, and sample statistics.

## 19. Metrics

V1 quality metrics:

- Percentage of reports with complete source metadata.
- Percentage of observations with sufficient sample count.
- Number of user follow-up questions required to understand a report.
- User-rated usefulness of top observations.
- Number of data-quality warnings encountered by provider and market.

V2 quality metrics:

- Weekly number of useful market-behavior observations.
- Alert dismissal rate.
- False-positive rate based on user feedback.
- Number of decision cards with market-behavior evidence.
- Number of weekly reviews referencing Kline evidence.
- Number of candidate observations confirmed or rejected by the user.

## 20. Risks

- Data-source adjustment differences may produce conflicting results.
- Futu historical Kline availability may depend on market coverage, quote permissions, or OpenD stability.
- AkShare is useful but not suitable as the only trusted production source.
- Historical pattern mining can overfit if the rule library expands too quickly.
- Too many V2 alerts could reduce trust.
- The user may confuse evidence-backed watch items with trade recommendations if language is not disciplined.
- Cross-market symbols and timezones may create subtle data bugs.

## 21. Open Questions

- Which markets should V1 officially support first: US, HK, A-share, KR, or only markets covered by current portfolio holdings?
- Should V1 cache all fetched bars immediately, or only cache reports and metadata?
- Should forward-return windows be fixed globally or configurable per market/style?
- What minimum sample threshold should be used by default?
- Should the first UI be command-only, web page, or decision-card embedded?
- Which external paid provider, if any, is worth approving for V2 global coverage?

## 22. Recommended Implementation Path

Recommended product path:

1. Build V1 around Futu OpenD as the primary provider.
2. Add AkShare as explicit prototype/fallback/cross-check mode.
3. Implement the deterministic rule library and report format before adding recurring scans.
4. Validate output quality on a small set of user-relevant stocks.
5. Add decision-card integration only after V1 report quality is trusted.
6. Add V2 portfolio/watchlist scanning after alert ranking and suppression rules are designed.

The first technical plan should cover V1 end to end in one implementation pass if Futu access is available locally or through the approved cloud read path. If provider access is unavailable, the implementation can still complete deterministic analysis against fixtures and defer live-provider verification as a concrete environment limitation.
