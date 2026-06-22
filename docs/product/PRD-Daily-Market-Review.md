# PRD: Daily Market Review

## 1. Background

InvestmentKnowledge already has portfolio, stock research, decision-card, and weekly-review workflows. The missing daily layer is a concise market map that answers:

> What is today's market focus across A-shares, U.S. stocks, and Hong Kong stocks, and where is active capital concentrating?

The user does not want a generic market news digest. They want a daily review that combines sentiment, volume expectations, hot stocks, hot industries, and a cross-market narrative into a decision-support artifact.

## 2. User Problem

The user currently has to inspect multiple markets separately:

- A-shares have local themes, turnover behavior, limit-up/limit-down breadth, and sector rotation.
- U.S. stocks drive global risk appetite, AI/semiconductor sentiment, liquidity, and overnight signals.
- Hong Kong stocks often transmit China growth, internet, biotech, high-dividend, and southbound-flow signals.

Without a structured daily review, it is hard to know:

- Whether the market is risk-on, risk-off, or purely structural.
- Whether today's volume supports the market move or is only a low-liquidity rebound.
- Which stocks and industries are actually attracting attention.
- Whether the portfolio's main themes are aligned with or fighting the market center of gravity.

## 3. Product Positioning

Daily Market Review should be:

> A cross-market daily radar that summarizes A-share, U.S., and Hong Kong sentiment, projected or realized turnover, top hot stocks, top hot industries, and the market's center of gravity with traceable data.

It should not be:

- A trading signal engine.
- A full research report for every hot stock.
- A raw news feed.
- A charting terminal.
- A model-generated market essay without data provenance.

## 4. Goals

### V1 Goals

- Generate one daily Markdown review for A-shares, U.S. stocks, and Hong Kong stocks.
- For each market, show market sentiment and volume expectation or realized volume context.
- For each market, rank the top 5 hot stocks with short explanations.
- For each market, rank the top 5 hot industries or themes with short explanations.
- Produce a cross-market "center of gravity" section that explains the dominant market focus.
- Make data freshness, source coverage, missing data, and confidence visible.
- Avoid fabricating market facts when data is unavailable.

### Later Goals

- Add a web workbench for browsing historical daily reviews.
- Add scheduled generation after each market close and before the next trading day.
- Add portfolio-aware alerts when the user's holdings overlap with hot stocks or industries.
- Add multi-day theme persistence and fading analysis.
- Feed durable observations into candidate insights for user confirmation.

## 5. Non-Goals

- Do not place trades or prepare trade orders.
- Do not output direct buy, sell, hold, stop-loss, or target-price instructions.
- Do not create a high-frequency intraday monitor in V1.
- Do not require every hot stock to have full fundamental research.
- Do not treat social-media heat as verified fact.
- Do not write inferred market observations into formal user insights without confirmation.
- Do not hide missing provider coverage behind confident language.

## 6. Target Users

Primary user:

- The investment system owner who wants a daily cross-market read before deciding what to research, watch, or risk-control.

Secondary users:

- Future portfolio and decision-card agents that need market-context evidence.
- Operators who need to verify whether daily review data sources are healthy.

## 7. Core User Stories

1. As a user, I can ask for today's market review and receive a concise three-market summary.
2. As a user, I can see whether A-shares, U.S. stocks, and Hong Kong stocks are risk-on, risk-off, mixed, or narrow/structural.
3. As a user, I can see whether each market's volume is expected to expand, contract, or stay normal versus recent history.
4. As a user, I can see the top 5 hot stocks in each market and why they are hot.
5. As a user, I can see the top 5 hot industries or themes in each market and why capital is focusing there.
6. As a user, I can understand the market center of gravity without reading a long market essay.
7. As a user, I can see when the report is using complete, partial, stale, or missing data.

## 8. Core Flow

```text
User request or scheduler
  -> resolve review date and market sessions
  -> fetch market index, breadth, turnover, stock ranking, sector ranking, and news/theme data
  -> normalize data across A-share, U.S., and Hong Kong markets
  -> compute sentiment, volume expectation, hot stock ranking, and industry ranking
  -> generate structured daily review with source diagnostics
  -> save report artifact
  -> optionally propose candidate insights for user confirmation
```

## 9. Review Timing Model

The product must handle timezone and session differences explicitly. The default user timezone is Asia/Singapore unless configured otherwise.

| Run Time | A-Share Section | Hong Kong Section | U.S. Section |
| --- | --- | --- | --- |
| Asia morning before A/HK open | Previous trading day plus today's pre-open setup if available | Previous trading day plus today's pre-open setup if available | Latest completed U.S. session |
| During A/HK session | Intraday state and full-day volume projection | Intraday state and full-day volume projection | Latest completed U.S. session |
| After A/HK close before U.S. close | Completed A/HK day | Completed Hong Kong day | U.S. pre-market or previous session, clearly labeled |
| After U.S. close | Latest completed trading day for all available markets | Latest completed trading day for all available markets | Latest completed U.S. session |

Each section must label the session date it represents. The report title should avoid implying that all markets are from the same calendar day when sessions differ.

## 10. Functional Scope

### 10.1 Inputs

Required:

- Review date or natural language date, defaulting to the latest market session available.
- Market set, defaulting to `CN`, `US`, and `HK`.

Optional:

- Run mode: `post_close`, `intraday`, or `pre_open`. If omitted, infer from market session time and data availability.
- Watchlist or portfolio-aware mode.
- Force refresh flag.
- Output format: Markdown by default; JSON for API integration.

### 10.2 Output Sections

Default report structure:

```text
# Daily Market Review: <session label>

## 1. Executive Snapshot
## 2. Cross-Market Center Of Gravity
## 3. A-Share Market
## 4. U.S. Market
## 5. Hong Kong Market
## 6. Theme Persistence And Rotation
## 7. Portfolio/Watchlist Relevance
## 8. Data Coverage And Caveats
```

### 10.3 Executive Snapshot

The first screen should answer:

- Which market is strongest today?
- Which market has the weakest sentiment?
- Is volume expanding or contracting?
- What is the dominant cross-market theme?
- Are hot stocks concentrated in one theme or spread across multiple themes?
- What should the user verify next?

Recommended format:

| Field | Requirement |
| --- | --- |
| Market mood | One of `risk_on`, `risk_off`, `mixed`, `narrow_theme`, `liquidity_pullback`, or `data_insufficient`. |
| Volume state | One of `expanding`, `normal`, `contracting`, `projected_high`, `projected_low`, or `data_insufficient`. |
| Dominant focus | One sentence naming the main market focus, such as AI infrastructure, China internet rebound, high-dividend defense, biotech policy, or small-cap speculation. |
| Confidence | High, medium, or low, based on data freshness and source coverage. |
| User relevance | Whether the focus overlaps with holdings, watchlist, or confirmed user insights. |

### 10.4 Per-Market Sentiment

Each market should have a sentiment score and a human-readable label.

Recommended inputs:

| Signal | A-Shares | U.S. Stocks | Hong Kong Stocks |
| --- | --- | --- | --- |
| Index performance | CSI 300, STAR 50, ChiNext, major sector indexes | S&P 500, Nasdaq 100, Russell 2000, SOX | Hang Seng, Hang Seng Tech, HSCEI |
| Breadth | Advancers/decliners, limit-up/limit-down, above moving averages | Advancers/decliners, new highs/lows, equal-weight indexes | Advancers/decliners, Hang Seng Tech breadth |
| Volume/turnover | Market turnover and sector turnover | Dollar volume and ETF volume | Market turnover and southbound flow if available |
| Volatility/risk | Large drawdowns, limit-down clusters | VIX, bond yield moves, mega-cap concentration | HSI volatility, China ADR spillover |
| Theme concentration | Limit-up boards and sector heat | Mega-cap/AI/semiconductor concentration | Internet, biotech, dividend, southbound concentration |

Sentiment labels:

- `strong_risk_on`: Broad gains, expanding turnover, supportive breadth.
- `risk_on_but_narrow`: Index gains led by a small number of stocks or industries.
- `mixed_rotation`: Indexes mixed, capital rotating between themes.
- `risk_off`: Broad weakness, defensive leadership, weak breadth.
- `liquidity_weak`: Direction not terrible, but volume and participation are poor.
- `data_insufficient`: Required data is missing or stale.

### 10.5 Volume Expectation

The product should prefer turnover amount over share volume because turnover is more comparable across markets and industries.

Volume expectation means different things by run mode:

| Run Mode | Meaning |
| --- | --- |
| Pre-open | Expected turnover range for the coming session based on rolling history, overnight catalysts, futures/pre-market data where available, and previous-session setup. |
| Intraday | Projected full-day turnover based on current turnover, elapsed trading time, and historical intraday volume curves for the same market. |
| Post-close | Actual turnover versus rolling averages, plus next-session volume setup when enough signals exist. |

Required fields:

| Field | Description |
| --- | --- |
| Actual or projected turnover | Market-level turnover amount in local currency or USD equivalent where available. |
| Relative level | Versus 5-day, 20-day, and 60-day average turnover. |
| Direction | Expanding, normal, contracting, or unavailable. |
| Projection confidence | High, medium, low, or unavailable. |
| Explanation | Why the volume state matters for today's move. |

Guardrails:

- Intraday volume projection must use market-specific trading-session calendars and lunch breaks.
- If the provider only has share volume but not turnover, label the metric clearly.
- If there is no reliable intraday curve, show actual current turnover and mark full-day projection unavailable.
- Do not present pre-open volume expectation as certainty.

### 10.6 Hot Stock Top 5

Each market should list the top 5 hot stocks.

Hot stock ranking should combine:

- Price move relative to market and sector.
- Turnover or dollar-volume abnormality.
- News/event catalyst count and quality.
- Social/news discussion heat when available.
- Sector/theme relevance.
- Whether the stock is in the user's portfolio, watchlist, or knowledge base.

Output fields:

| Field | Description |
| --- | --- |
| Rank | 1 to 5. |
| Stock | Symbol and company name. |
| Market | CN, US, or HK. |
| Move | Latest session return and relative strength. |
| Volume heat | Turnover versus recent average. |
| Catalyst | Earnings, policy, product, macro, sector event, rumor, or unknown. |
| Theme | Mapped industry or theme. |
| Why hot | One concise explanation grounded in data. |
| User relevance | Portfolio/watchlist/knowledge overlap, if any. |
| Confidence | High, medium, low, or data_insufficient. |

Hot stock explanations must avoid unsupported causal certainty. Use language such as "appears linked to" or "market discussion centered on" when catalyst evidence is incomplete.

### 10.7 Hot Industry Top 5

Each market should list the top 5 hot industries or themes.

Industry ranking should combine:

- Sector/index return.
- Sector turnover share and turnover abnormality.
- Breadth within the sector.
- Number and strength of hot stocks inside the sector.
- News and policy catalysts.
- Cross-market echo, such as U.S. semiconductor strength influencing A-share or Hong Kong technology stocks.

Output fields:

| Field | Description |
| --- | --- |
| Rank | 1 to 5. |
| Industry/theme | Standard industry name plus local theme label when useful. |
| Market | CN, US, or HK. |
| Performance | Latest session return or relative strength. |
| Volume heat | Turnover share and abnormality. |
| Representative stocks | Up to 3 names from the ranked hot stocks or sector leaders. |
| Catalyst | Policy, earnings, macro, product cycle, commodity, liquidity, or unknown. |
| Why it matters | One sentence linking the industry to the market's center of gravity. |
| Confidence | High, medium, low, or data_insufficient. |

### 10.8 Cross-Market Center Of Gravity

This is the most important narrative section. It should synthesize, not repeat.

Required questions:

- Is the main market focus global, regional, or local?
- Is it driven by fundamentals, liquidity, policy, earnings, macro, or speculation?
- Are A-shares, U.S. stocks, and Hong Kong stocks confirming each other or diverging?
- Is the theme broadening or becoming crowded/narrow?
- Does the theme overlap with the user's portfolio, watchlist, or durable insights?

Required format:

```text
Center of gravity:
- Main focus:
- Confirming evidence:
- Diverging evidence:
- Volume confirmation:
- Portfolio relevance:
- Next verification:
```

Generation rules:

- Cite at least two evidence types, such as index performance, breadth, turnover, sector rankings, hot stocks, news catalysts, portfolio overlap, or user insights.
- If only one market has reliable data, mark the cross-market view as low confidence.
- If hot stocks are concentrated in one theme with weak breadth, explicitly call out concentration risk.
- If the market move is volume-light, avoid describing it as strong confirmation.

### 10.9 Theme Persistence And Rotation

V1 should include a lightweight section comparing today with recent days when historical daily reviews exist.

Fields:

- Persistent themes: themes in the top 5 for at least 2 of the last 3 sessions.
- New themes: themes newly entering top rankings.
- Fading themes: themes dropping out or losing volume support.
- Crowding signal: hot stocks concentrated in a theme with rapidly expanding turnover and narrow breadth.

If historical reports do not exist yet, show "not enough history" instead of inventing a trend.

### 10.10 Portfolio And Watchlist Relevance

If portfolio or watchlist data is available, the report should show:

- Holdings that overlap with today's hot stocks.
- Holdings that belong to today's top industries.
- Holdings moving against their industry or market.
- Watchlist names that are becoming market focus.
- Existing confirmed user insights that match today's theme.

The section should not suggest trades. It should frame what deserves research or risk review.

## 11. Data Source Strategy

### 11.0 Product Principle

Daily Market Review is only useful if the user can trust the source layer.

For this feature, data source quality is a product requirement, not an implementation detail. The report's credibility comes from:

```text
source coverage + session freshness + turnover data + ranking method + traceability
```

It does not come from a model sounding fluent. If market data is missing, stale, delayed, or only suitable for prototyping, the report must say so directly.

### 11.1 Required Data Domains

V1 needs provider coverage for:

- Market calendars and session metadata.
- Index quotes and returns.
- Market turnover or volume.
- Breadth, where available.
- Stock rankings by return, turnover, and abnormal activity.
- Sector or industry rankings.
- News/event snippets or theme labels.
- Existing InvestmentKnowledge portfolio, watchlist, stock profiles, sectors, and user insights.

### 11.2 Source Hierarchy

V1 should reuse the provider ladder already established in the Kline Agent PRD, but adapt it for daily-market use cases. Kline data alone is not enough; daily review additionally needs market screening, plate/sector ranking, hot-stock ranking, intraday turnover, and sentiment or market-temperature signals.

Recommended V1 hierarchy:

1. Futu OpenD as the primary integrated quote source when coverage and quote permissions are available.
2. LongPort as a strong broker-style backup for HK/US/CN quote, intraday, historical candlestick, trading-session, trading-day, capital-flow, and market-temperature data.
3. AkShare as prototype, fallback, and cross-check source, especially for A-share industry/concept boards, Eastmoney/THS hot rankings, fund flow, and Hong Kong hot-rank style data.
4. Polygon/Massive as a U.S. full-market backup for daily summaries and snapshots if U.S. all-market screening through broker APIs is insufficient and paid access is approved.
5. Alpha Vantage or EODHD only as lower-priority global/index fallback when the higher-priority sources cannot cover a required symbol or market.

### 11.3 Provider Capability Map

| Requirement | Preferred Source | Backup / Cross-Check | Notes |
| --- | --- | --- | --- |
| Market calendars and session state | Futu `request_trading_days`, `get_market_state`, `get_global_state`; LongPort market trading days and trading-session APIs | Exchange calendars or AkShare if needed | Session labels must distinguish A/HK/U.S. trading days. |
| Index quotes and daily returns | Futu market snapshot, real-time quote, historical candlesticks | LongPort candlesticks; Polygon/Massive or Alpha Vantage for U.S. indexes | Store provider symbol and adjustment/session metadata. |
| Intraday turnover and volume projection | Futu `get_rt_data` / real-time candlestick where available | LongPort intraday lines and candlesticks | Use market-specific intraday curves; mark unavailable if only EOD data exists. |
| Hot stocks top 5 | Futu stock filter sorted by change, turnover, volume, amplitude, and turnover rate; Futu market snapshots for candidate details | AkShare A/HK hot-rank endpoints; Polygon/Massive U.S. snapshot/daily summary | Hot-stock score should blend price move, turnover abnormality, catalyst, and user relevance. |
| Hot industry/theme top 5 | Futu plate list, plate constituents, owner plate, and plate-stock sorting | AkShare industry/concept board APIs and THS/Eastmoney fund-flow/board data | Futu provides structure; AkShare may provide richer A-share board heat in prototype mode. |
| Market sentiment | Deterministic score from index, breadth, turnover, hot-stock concentration, and sector breadth | LongPort current/historical market temperature where available | Do not outsource final sentiment entirely to a provider label. |
| Breadth | Derived from market/plate constituents and snapshots | AkShare board constituent data; Polygon/Massive U.S. all-market daily summary | Breadth should degrade gracefully when full-constituent coverage is unavailable. |
| News/catalyst context | Existing official/company/news research providers where available | AkShare hot-rank metadata, provider snippets, manual source import | News is explanation evidence, not the ranking source of truth. |
| Portfolio/watchlist relevance | Existing InvestmentKnowledge portfolio, stock profiles, sectors, user insights | Futu/LongPort watchlist APIs if later approved | User memory and portfolio relevance are first-party product data. |

### 11.4 Provider-Specific Product Notes

#### Futu OpenD

Futu should be the default source because the repository already depends on `futu-api` and has Futu OpenD deployment/service work. For Daily Market Review, the relevant API families are:

- Market snapshot and real-time quote for current prices, changes, volume, and turnover.
- Real-time time frame / real-time candlestick data for intraday turnover projection.
- Historical candlesticks for rolling turnover baselines and index/stock return history.
- Stock filter for market-wide screening by change, turnover, volume, amplitude, and turnover rate.
- Plate list and plate stock for sector/theme membership and constituent screening.
- Owner plate for mapping hot stocks back to sectors/themes.
- Market state, global state, and trading calendar for session-aware report timing.

Known constraint:

- Quote permissions, market coverage, stock-filter behavior, and plate coverage must be verified in the technical plan with live or approved cloud-side checks.

#### LongPort

LongPort should be treated as a serious backup and enrichment source rather than a distant fallback. It is especially relevant because its quote docs expose:

- Historical candlesticks with turnover and documented HK/U.S./A-share history ranges.
- Intraday lines with price, volume, turnover, and average price.
- Trading-session and market-trading-day APIs.
- Security capital-flow data.
- Current and historical market-temperature APIs for US, HK, SG, and CN.

Known constraint:

- Quote authority and API credentials are required. It should not become mandatory for V1 if Futu can satisfy the report, but it is a strong candidate for sentiment and volume validation.

#### AkShare

AkShare is valuable for fast product proof and A-share/HK market color, especially:

- A-share concept and industry board rankings.
- THS/Eastmoney industry summaries with price-change percentage, total turnover, net inflow, breadth, and leading stock fields.
- Industry fund-flow rankings.
- Eastmoney A-share hot-rank and Hong Kong hot-rank endpoints.
- AH comparison and northbound/southbound style flow datasets where useful.

Known constraint:

- AkShare should be labeled as prototype/fallback/cross-check unless the technical plan explicitly approves a production usage pattern. Its upstream pages can change, and its data should not be the only basis for a high-confidence production report.

#### Polygon/Massive

Polygon/Massive is a useful U.S. backup when the product needs broad U.S. market screening:

- Daily market summary can return OHLC, volume, VWAP, and transaction-count-style fields for all U.S. stocks on a date.
- Full market snapshot can return current full-market ticker data, including day/minute/previous-day fields and today's percentage change where plan access allows.

Known constraint:

- Plan access and recency differ by subscription level. Use it only after access/cost is approved.

### 11.5 Minimum V1 Provider Decision

The PRD should not leave provider requirements abstract, but live provider checks and the technical plan belong to the technical owner or Development Agent. Product should hand off a concrete coverage checklist:

| Market | Primary | Required before V1 can be considered usable |
| --- | --- | --- |
| A-shares | Futu OpenD, with AkShare cross-check for industry/concept heat | Index quotes, market turnover proxy, stock filter or hot-rank substitute, industry/concept top 5. |
| U.S. stocks | Futu OpenD first; LongPort or Polygon/Massive fallback if all-market screening is weak | Index quotes, top movers by return and turnover/volume, sector/theme mapping, market-temperature or deterministic sentiment. |
| Hong Kong stocks | Futu OpenD first; LongPort and AkShare hot-rank fallback | Index quotes, turnover/volume, plate/industry or theme ranking, hot-stock ranking. |

If any market cannot meet the minimum, V1 can still ship only if that market is visibly marked `partial_coverage` and the acceptance criteria are adjusted before implementation.

Product handoff boundary:

- Product owns the required data domains, quality bar, source transparency, user-facing degradation behavior, and acceptance criteria.
- Technical planning owns provider client design, credentials, quotas, schema, caching, service boundaries, and live coverage verification.
- Product should review the provider coverage result before implementation starts, especially if any market is proposed as partial coverage.

### 11.6 Source References

- Futu quote overview and market APIs: <https://openapi.futunn.com/futu-api-doc/en/quote/overview.html>
- Futu stock filter: <https://openapi.futunn.com/futu-api-doc/en/quote/get-stock-filter.html>
- Futu plate list: <https://openapi.futunn.com/futu-api-doc/en/quote/get-plate-list.html>
- Futu plate stocks: <https://openapi.futunn.com/futu-api-doc/en/quote/get-plate-stock.html>
- Futu historical candlesticks: <https://openapi.futunn.com/futu-api-doc/en/quote/request-history-kline.html>
- LongPort historical candlesticks: <https://open.longportapp.com/docs/quote/pull/history-candlestick>
- LongPort intraday data: <https://open.longportapp.com/docs/quote/pull/intraday>
- LongPort market temperature: <https://open.longportapp.com/docs/quote/pull/market_temperature>
- AkShare stock data: <https://akshare.akfamily.xyz/data/stock/stock.html>
- AkShare special notice: <https://akshare.akfamily.xyz/special.html>
- Polygon/Massive daily market summary: <https://massive.com/docs/rest/stocks/aggregates/daily-market-summary>
- Polygon/Massive full market snapshot: <https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot>

### 11.7 Missing Data Behavior

If a source is unavailable, the system must:

- Show which market or field is missing.
- Degrade the affected score or mark it unavailable.
- Avoid filling missing facts with model guesses.
- Still generate useful sections from available data when safe.

## 12. Data Model And Storage Impact

The technical plan should decide final table names and migrations, but the product expects durable storage for:

- Daily review reports.
- Per-market sentiment snapshots.
- Volume expectation snapshots.
- Hot stock ranking snapshots.
- Hot industry ranking snapshots.
- Source diagnostics and fetch metadata.
- Optional candidate insights generated from recurring market observations.

Minimum saved report metadata:

| Field | Requirement |
| --- | --- |
| Report date/session label | Must distinguish A/HK/U.S. session dates when needed. |
| Markets covered | CN, US, HK. |
| Run mode | Pre-open, intraday, post-close, or mixed. |
| Generated at | Timestamp with timezone. |
| Source coverage | Complete, partial, stale, or failed per market. |
| Report body | Markdown artifact. |
| Structured payload | JSON suitable for future web rendering. |

## 13. Entry Points

### 13.1 Command Entrypoints

Supported natural commands:

```text
每日复盘
今日复盘
市场复盘
日复盘
复盘今天市场
每日复盘 2026-06-23
每日复盘 --market CN,US,HK --mode post_close
```

The command result should return the Markdown report and save the artifact.

### 13.2 API Entrypoints

The web/API design should support:

- Generate daily market review.
- Get latest daily market review.
- Get review by date.
- Force refresh by date and market set.
- Return source diagnostics for a review.

### 13.3 Web Entrypoints

V1 does not require a new web surface, but the report should be structured so a future web page can show:

- Executive snapshot.
- Per-market panels.
- Hot stock and industry tables.
- Source diagnostics.
- Historical theme persistence.

## 14. Safety And Permissions

- This feature is read-only except for saving report artifacts and optional candidate insights.
- Candidate insights must remain pending until user confirmation.
- Reports must state data freshness and missing coverage.
- The feature must not trigger trades or order preparation.
- The feature must not store provider credentials or secrets in reports, logs, or docs.
- If cloud scheduling is added later, deployment and external API credentials require explicit setup and verification.

## 15. UX And Writing Guidelines

- Start with the answer, then evidence.
- Prefer compact tables for top stocks and industries.
- Keep each market section scannable within one screen when rendered in Markdown.
- Use direct labels such as `risk_on_but_narrow` and then explain in plain language.
- Separate facts, interpretation, and missing data.
- Use careful causality wording when catalysts are inferred rather than confirmed.
- Avoid generic commentary such as "investors should pay attention to risks" unless tied to a specific market condition.

## 16. Acceptance Criteria

### Report Generation

- Given `每日复盘`, the system generates a daily market review covering A-shares, U.S. stocks, and Hong Kong stocks when data is available.
- The report includes an executive snapshot, cross-market center of gravity, and one section per market.
- Each market section includes sentiment, volume state, hot stocks top 5, and hot industries top 5.
- Each hot stock includes symbol, name, move, volume heat, catalyst or unknown catalyst, theme, explanation, user relevance, and confidence.
- Each hot industry includes performance, volume heat, representative stocks, catalyst or unknown catalyst, explanation, and confidence.

### Data Integrity

- The report labels session dates separately when market sessions differ.
- The report labels provider name, fetch time, and coverage status.
- Missing data is explicitly marked and does not get replaced by invented content.
- Intraday volume projection uses elapsed session time and market-specific calendars; if unavailable, projection is marked unavailable.
- Post-close volume state compares actual turnover against at least one rolling average.

### Market Narrative

- The center-of-gravity section cites at least two evidence types.
- The narrative distinguishes broad risk appetite from narrow theme speculation.
- The narrative calls out volume-light moves, crowded themes, and cross-market divergence.
- Portfolio/watchlist relevance appears when matching data exists and stays omitted or marked unavailable when it does not.

### Persistence And Retrieval

- Generated reports can be saved and retrieved by date.
- Structured ranking data is available for future web rendering or historical comparisons.
- Theme persistence shows "not enough history" until enough prior reports exist.

### Safety

- The report contains no direct trade instructions.
- Candidate insights, if generated, are pending and require explicit user confirmation.
- Provider credentials and secrets never appear in report text, logs, or durable docs.

## 17. Open Decisions

These decisions should be resolved by the technical owner or Development Agent before implementation:

- Which market-data provider or provider combination passes live coverage checks for each market?
- Whether LongPort credentials/quote authority should be approved for market-temperature and turnover validation.
- Whether Polygon/Massive U.S. full-market access is worth approving if Futu/LongPort U.S. screening is insufficient.
- Whether V1 should include scheduled generation or manual command only.
- Whether U.S. pre-market and after-hours data should be part of V1 or a later enhancement.
- Which industry taxonomy should be canonical across CN, US, and HK.
- Whether source diagnostics should be stored in existing report tables or a new provider-fetch table.

None of these change the product intent. The PRD is ready for technical handoff; implementation should wait until provider coverage is checked and documented by the technical owner.

## 18. Success Metrics

- The user can understand the market's daily center of gravity in under two minutes.
- The report identifies the dominant hot stocks and industries without requiring the user to open multiple market apps.
- Missing data is visible enough that the user can trust the report's limits.
- At least 80% of generated daily reports have complete or partial-but-useful coverage for all three markets after provider setup.
- The user can point from a narrative statement back to supporting market, stock, sector, volume, or source diagnostics evidence.
