# PRD: Daily Market Brief

Status: ready
Owner: Product Agent
Feature Registry row: Daily market brief
Last updated: 2026-06-30

## Background

The user wants a useful daily investment brief after each market close for A-shares, Hong Kong stocks, and U.S. stocks. The brief should summarize what happened in each market using core index moves, leading sectors or industries, leading stocks, capital-flow signals when available, and trading volume or turnover changes against a useful baseline.

This should not be a raw provider dump. It should be a concise market-close narrative that helps the user understand market breadth, leadership, liquidity, and notable activity before the next investment review.

## Repo Context

Current implementation patterns that should shape the product and technical plan:

- `investment_knowledge_mcp/account_snapshots.py` and `investment_knowledge_mcp/ipo_reminders.py` use simple standalone scheduler loops with idempotency guards or sent-event records.
- `investment_knowledge_mcp/weekly_review.py` builds structured report context, renders Markdown, records source status, and persists generated reports through `review_reports`.
- `investment_knowledge_mcp/weekly_review_web.py` exposes a report read/generate/refresh/save Web/API pattern on the public weekly-review surface.
- `investment_knowledge_mcp/command_router.py` exposes generated reports through reusable command surfaces.
- `investment_knowledge_mcp/market_data_provider.py` and `investment_knowledge_mcp/futu_provider.py` already provide market-data and Futu integration patterns, including explicit provider errors and fallback source labels.
- `db/schema.sql` already allows multiple `review_reports.report_type` values with structured context and source-status metadata, but it may need stronger uniqueness for market/date idempotency if multiple daily market briefs share one date.

## Goals

- Generate a daily close brief independently for CN, HK, and US markets after each market closes.
- Include core index moves, top gaining sectors or industries, top gaining individual stocks, capital inflow names or segments when provider-supported, and volume or turnover change versus baseline.
- Make missing or partial data explicit with source, timestamp, market date, and degraded-state language.
- Store each generated brief so it can be retrieved later and safely rerun for the same market/date.
- Keep the output investment-useful: short interpretation first, provider tables second.

## Non-Goals

- Do not place trades, make recommendations, or automatically alter portfolio state.
- Do not invent capital-flow data when a provider cannot support it.
- Do not merge all markets into one global scheduled job; each market needs its own close-time run and rerun semantics.
- Do not require paid data providers for P0 unless Product explicitly approves that dependency.
- Do not mark the feature accepted until independent acceptance testing passes and the user explicitly accepts it.

## P0 Scope And Product Defaults

P0 implements one daily close report per market/date. The report is generated independently for CN A-shares, HK, and US after each market's regular close. P0 is ready for one Engineering planning pass with the defaults below; unresolved enhancements are P1, not blockers.

| Market | Close timezone | P0 core indexes |
|---|---|---|
| CN A-shares | Asia/Shanghai | Shanghai Composite, Shenzhen Component, CSI 300, ChiNext Index, STAR 50 |
| HK | Asia/Hong_Kong | Hang Seng Index, Hang Seng TECH Index, Hang Seng China Enterprises Index |
| US | America/New_York | S&P 500, Nasdaq Composite, Dow Jones Industrial Average, Russell 2000 |

Each market brief should include:

1. Market date, generation timestamp, source labels, and source-status summary.
2. Core index changes for the latest completed regular session, including percentage change and turnover or volume change when available.
3. Top 5 gaining sectors or industries using the configured provider's native taxonomy, with the taxonomy and provider named in the output.
4. Top 5 gaining individual stocks from the P0 liquid common-stock universe.
5. Top 5 capital inflow names or segments only when the configured provider supports an explicit flow metric for that market; otherwise show a visible degraded state.
6. Volume or turnover change versus the previous trading day, 5-trading-day average, and 20-trading-day average when enough history is available.
7. A short narrative summary that names market breadth, leadership, liquidity/turnover, and data gaps.

## Output Surface

P0 output surface:

- Persist each brief as a structured `review_reports` entry with report type `daily_market_brief`.
- Add command retrieval for latest and specific market/date briefs. The exact command parser wording is an Engineering detail, but the user-facing intent must support "show latest daily market brief for CN/HK/US" and "show daily market brief for market/date".
- Provide a Web review page so the user can inspect and accept the feature without running CLI commands. The page may extend the existing Weekly Review Web service as long as it has a direct `/daily-market-brief` route and read/generate controls for CN/HK/US.
- Store structured context, source status, generated Markdown, market, market date, provider labels, and generation timestamp so the brief can be regenerated, inspected, and rendered consistently.

P0 does not include DingTalk push or a separate standalone Web app. Those remain P1 because they require channel, layout, and notification-timing decisions. Engineering should keep the storage/API shape compatible with future push surfaces.

## User Flow

1. Scheduler runs after the regular close delay for one market.
2. The generator identifies the latest completed trading session for that market.
3. The generator collects index, sector/industry, stock-gainer, flow, and volume/turnover data from configured providers.
4. Missing provider coverage is recorded in source status and shown in product-language copy inside the brief.
5. The generator persists or refreshes the market/date brief idempotently.
6. The user retrieves the latest or a market/date-specific brief through the command surface.

## Data, Provider, And Metric Semantics

P0 must use configured providers already available to the project or a no-paid-dependency provider that Engineering explicitly documents in the technical plan. Futu is the preferred configured provider for CN/HK coverage when available. The existing market data provider or Yahoo-style chart source is acceptable for US indexes/equities when it supplies the required semantics. P0 must not introduce a paid data dependency.

P0 provider behavior must be explicit:

- Core indexes: use the most reliable configured source per market; fall back only when the fallback can supply the same metric semantics.
- Sectors or industries: use each market provider's native sector or industry taxonomy. Label the taxonomy and provider in the brief. Do not normalize CN, HK, and US sectors into one cross-market taxonomy in P0.
- Individual stock gainers: use common equities or ADR/common-share equivalents only. Exclude ETFs, funds, warrants, rights, preferred shares, structured products, suspended names, and symbols with no latest regular-session price when the provider exposes enough metadata to do so. Apply the P0 liquidity filter before ranking: choose the top 1,000 common equities by latest regular-session turnover per market, or the full available common-equity universe when fewer than 1,000 names are available. If provider metadata cannot reliably identify exclusions, label the limitation in source status.
- Capital inflow: show only named provider flow metrics. CN may use northbound flow, main-fund flow, or stock/sector money-flow metrics when the configured provider supports them. HK may use southbound flow or stock/sector money-flow metrics when supported. US defaults to `not_available` in P0 unless the configured no-paid-dependency provider supplies explicit stock or sector flow data. Price action, volume spikes, or turnover are not acceptable substitutes for a capital-flow metric.
- Capital-flow degraded copy: when unsupported, show "capital-flow data is not available from the configured provider for this market/session; the rest of the brief was generated from available market data" in the report language, plus provider/source status metadata.
- Volume or turnover baseline: include previous trading day, 5-trading-day average, and 20-trading-day average where history exists. If fewer than 5 or 20 prior sessions are available, show a partial-history state instead of suppressing the whole brief.
- Market breadth: P0 may use provider-supported advance/decline counts when available. If unavailable, the narrative should describe leadership using sectors, gainers, and liquidity without inventing breadth statistics.

## Language, Timezones, And Delivery Timing

- Brief language: Simplified Chinese for narrative and user-facing labels. Provider names, ticker symbols, and official index names may remain in English where that is the market convention.
- Timestamp display: show market date in the market's local timezone and generation timestamp in both market-local timezone and Asia/Singapore.
- CN schedule: run after the normal A-share close at 15:30 Asia/Shanghai.
- HK schedule: run after the normal HK close at 16:30 Asia/Hong_Kong.
- US schedule: run after the normal US close at 16:30 America/New_York.
- Holiday or no-session behavior: record a skipped/no-session state with market/date/source status and do not create a misleading empty market-move narrative.
- Manual rerun: support explicit market/date rerun for operational recovery and acceptance testing.

## Idempotency And Scheduling

- CN, HK, and US should be scheduled independently after each market's normal close plus a configurable delay.
- Each run should be idempotent by report type, market, market date, and provider version or source signature. Reruns should refresh the same market/date report or create a clearly linked refreshed version; Engineering should choose the storage strategy in the technical plan and make duplicate prevention explicit.
- If the market was closed for a holiday, the scheduler should record a skipped or no-session state instead of creating a misleading empty report.
- Manual rerun should be available for a specific market/date.

## Acceptance Criteria

- A generated CN brief includes Shanghai Composite, Shenzhen Component, CSI 300, ChiNext Index, STAR 50, top 5 provider-taxonomy sectors/industries, top 5 liquid common-stock gainers, CN flow or degraded-flow state, previous-day/5-day/20-day volume or turnover baselines, source labels, market date, and timestamp.
- A generated HK brief includes Hang Seng Index, Hang Seng TECH Index, Hang Seng China Enterprises Index, top sectors or industries when supported, top 5 liquid common-stock gainers, HK flow or degraded-flow state, previous-day/5-day/20-day turnover baselines, source labels, market date, and timestamp.
- A generated US brief includes S&P 500, Nasdaq Composite, Dow Jones Industrial Average, Russell 2000, top sectors or industries when supported, top 5 liquid common-stock or ADR/common-share gainers, explicit US flow degraded state unless a real configured flow metric exists, previous-day/5-day/20-day volume baselines, source labels, market date, and timestamp.
- Each market can run after its own configured close delay and can be rerun for the same market/date without duplicate confusing reports.
- Missing provider coverage is visible in user language and does not block the rest of the brief when partial data exists.
- The command surface retrieves the latest generated brief per market and a specified market/date brief.
- The stored report includes structured context and source status sufficient for later Web/push rendering without reparsing Markdown.
- The narrative is understandable without reading raw provider fields and does not make buy/sell recommendations.
- Holiday/no-session runs produce an explicit skipped/no-session state rather than a market-move report.
- Independent acceptance testing verifies the real chosen surface before asking the user for acceptance.

## Open P1 Decisions

These are intentionally out of P0 and should not block technical planning:

1. DingTalk push channel, message length, and retry/escalation behavior.
2. Standalone Web page or Weekly Review Web integration.
3. Cross-market sector taxonomy normalization.
4. Paid provider adoption for deeper capital-flow coverage.
5. More advanced breadth, factor, or macro attribution.
6. User-customizable delivery timing or market selection.

## Recommended Next Owner

Engineering should create `docs/techplans/daily-market-brief.md`, covering provider selection, storage uniqueness/idempotency, scheduler integration, command retrieval, source-status shape, verification fixtures, and deployment impact. Acceptance testing is required after an implemented user-facing command surface exists; no acceptance queue row is needed before implementation because there is nothing user-facing to test yet.
