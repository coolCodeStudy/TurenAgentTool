# PRD: Daily Market Brief

Status: draft  
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

## Proposed P0 Scope

P0 should define and implement one daily close report per market/date:

| Market | Proposed close timezone | Proposed core indexes |
|---|---|---|
| CN A-shares | Asia/Shanghai | Shanghai Composite, Shenzhen Component, CSI 300, ChiNext, STAR 50 |
| HK | Asia/Hong_Kong | Hang Seng Index, Hang Seng TECH Index, Hang Seng China Enterprises Index |
| US | America/New_York | S&P 500, Nasdaq Composite or Nasdaq 100, Dow Jones Industrial Average, Russell 2000 |

Each market brief should include:

1. Market date, generation timestamp, source labels, and source-status summary.
2. Core index changes for the latest completed session, including percentage change and turnover or volume change when available.
3. Top 5 gaining sectors or industries using a provider-specific taxonomy that is named in the output.
4. Top 5 gaining individual stocks using a Product-approved universe and liquidity filter.
5. Top 5 capital inflow names or segments when provider-supported; otherwise a visible "not available from configured provider" degraded state.
6. Volume or turnover change versus previous trading day and a recent average baseline, with Product choosing the final average window.
7. A short narrative summary that names market breadth, leadership, liquidity/turnover, and data gaps.

## Output Surface

Product decision required.

Recommended P0 default if the user does not choose otherwise:

- Persist the brief as a structured `review_reports` entry with a new report type such as `daily_market_brief`.
- Add a command query to retrieve the latest or specified market/date brief.
- Add DingTalk push only after Product confirms the channel, timing, and message length expectations.

Other possible surfaces:

- DingTalk push after each market close.
- Weekly Review Web extension.
- Standalone market brief Web page.
- Saved Markdown artifact only.
- Combined command retrieval plus push notification.

## Data And Provider Requirements

Provider choice is a Product decision because coverage differs by market and metric.

P0 provider behavior must be explicit:

- Core indexes: use the most reliable configured source per market; fall back only when the fallback can supply the same metric semantics.
- Sectors or industries: label the taxonomy and provider; do not compare incompatible taxonomies across markets without saying so.
- Individual stock gainers: define whether the universe is all listed shares, index constituents, actively traded names, or large/liquid names.
- Capital inflow: define per market. CN may support northbound or main-fund style data depending on provider; HK may support southbound or market/stock money-flow data depending on provider; US stock-level money-flow may be unavailable without a paid provider.
- Volume or turnover baseline: Product should choose previous trading day only, 5-day average, 20-day average, or all three.

## Idempotency And Scheduling

- CN, HK, and US should be scheduled independently after each market's normal close plus a configurable delay.
- Each run should be idempotent by market/date/provider version; reruns should update the same generated report or create a clear refreshed version according to the technical plan.
- If the market was closed for a holiday, the scheduler should record a skipped or no-session state instead of creating a misleading empty report.
- Manual rerun should be available for a specific market/date.

## Acceptance Criteria

- A generated CN brief includes the approved CN indexes, top sectors, top stocks, volume/turnover baseline, source labels, market date, and timestamp.
- A generated HK brief includes the approved HK indexes, top sectors or industries when supported, top stocks, flow/degraded-flow state, volume/turnover baseline, source labels, market date, and timestamp.
- A generated US brief includes the approved US indexes, top sectors or industries when supported, top stocks, flow/degraded-flow state, volume baseline, source labels, market date, and timestamp.
- Each market can run after its own close and can be rerun for the same market/date without duplicate confusing reports.
- Missing provider coverage is visible in user language and does not block the rest of the brief when partial data exists.
- The brief is retrievable from the chosen user surface and is understandable without reading raw provider fields.
- Independent acceptance testing verifies the real chosen surface before asking the user for acceptance.

## Open Product Decisions

1. Preferred output surface for P0: DingTalk push, command query, weekly-review Web extension, standalone Web page, saved Markdown/report, or a combination.
2. Final core index list for each market, especially Nasdaq Composite versus Nasdaq 100 for US and whether STAR 50 is required for CN.
3. Provider and taxonomy for sector/industry rankings per market.
4. Definition of "capital inflow" per market and acceptable degraded behavior when unavailable.
5. Individual-stock universe and liquidity filter for top gainers.
6. Volume/turnover baseline: previous trading day, 5-day average, 20-day average, or all three.
7. Brief language, timezone display, and exact delivery timing after each close.

## Recommended Next Owner

Product Agent should refine this draft into a ready PRD by resolving or explicitly defaulting the open Product decisions. Engineering should not start a full technical plan until those decisions are recorded.
