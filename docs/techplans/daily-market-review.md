# Daily Market Review Technical Plan

## Status

Partially implemented and locally verified.

Linked PRD: [`docs/product/PRD-Daily-Market-Review.md`](../product/PRD-Daily-Market-Review.md)

This plan covers V1 as a manual command/API-capable generator with durable storage and source diagnostics. The command/report/storage/scoring path is implemented and smoke-tested with fake providers in `codex/daily-market-review`; live provider coverage still depends on approved dependencies/credentials and must be verified with `scripts/probe_daily_market_providers.py`. Scheduled generation, a dedicated web workbench, portfolio alerts, and automatic durable insight writes remain later work from the PRD.

## Product Contract

V1 must generate a saved Markdown and structured JSON daily market review for `CN`, `US`, and `HK` when data is available. Each market section must include session labeling, sentiment, volume context, top 5 hot stocks, top 5 hot industries/themes, provider coverage, and confidence. The cross-market section must synthesize the center of gravity without fabricating missing facts.

Implementation should be completed in one bounded pass after a provider coverage probe. The probe is not a separate product phase; it is the first implementation step because provider permissions determine which fields are `complete`, `partial_coverage`, or `unavailable`.

## Existing System Fit

Reuse the existing weekly-review pattern:

```text
command_router
  -> daily_market_review.build_daily_market_review(...)
  -> provider fetch + normalization
  -> deterministic scoring and context assembly
  -> render Markdown
  -> repository.upsert_review_report(...)
```

This keeps daily review behavior consistent with `investment_knowledge_mcp.weekly_review`: facts are assembled into a structured context first, Markdown rendering is deterministic, and the model layer is optional and constrained to summarization after data exists.

## Implementation Scope

In scope:

- Manual command entrypoints: `每日复盘`, `今日复盘`, `市场复盘`, `日复盘`, `复盘今天市场`, plus date/market/mode options.
- Python service functions for context build, Markdown rendering, report saving, and latest/by-date retrieval helpers.
- Provider abstraction for quote/calendar/screener/sector/news-like catalyst snippets.
- Futu OpenD as the primary provider where quote permissions are available.
- AkShare as the initial fallback/cross-check provider for CN/HK heat, sector boards, and hot-rank style datasets.
- Optional LongPort and Polygon/Massive provider interfaces behind configuration, with graceful `not_configured` diagnostics if credentials are absent.
- Database persistence for report body, structured payload, per-market snapshots, rankings, source diagnostics, and fetch metadata.
- Local smoke/unit tests using fixtures and provider fakes.

Out of scope for V1:

- Placing trades or preparing orders.
- A dedicated daily review web UI.
- Scheduled cloud generation.
- Direct buy/sell/hold/target-price instructions.
- Automatic promotion of recurring observations into confirmed user insights.
- Making LongPort or Polygon/Massive mandatory when Futu/AkShare can produce a clearly labeled partial-but-useful V1 report.

## Proposed Modules

```text
investment_knowledge_mcp/daily_market_review.py
investment_knowledge_mcp/market_data/__init__.py
investment_knowledge_mcp/market_data/models.py
investment_knowledge_mcp/market_data/providers/base.py
investment_knowledge_mcp/market_data/providers/futu_quote.py
investment_knowledge_mcp/market_data/providers/akshare_quote.py
investment_knowledge_mcp/market_data/providers/longport_quote.py
investment_knowledge_mcp/market_data/providers/polygon_quote.py
investment_knowledge_mcp/market_data/provider_probe.py
investment_knowledge_mcp/market_data/session_calendar.py
investment_knowledge_mcp/market_data/scoring.py
investment_knowledge_mcp/market_data/taxonomy.py
investment_knowledge_mcp/market_data/volume_projection.py
```

### `daily_market_review.py`

Application service layer:

```python
build_daily_market_review(
    review_date: date | None = None,
    markets: list[str] | None = None,
    mode: str | None = None,
    force_refresh: bool = False,
    save: bool = True,
) -> DailyMarketReviewResult

build_daily_market_review_context(...) -> dict[str, Any]
render_daily_market_review_markdown(context: dict[str, Any]) -> str
save_daily_market_review_report(context: dict[str, Any], markdown: str) -> dict[str, Any]
```

`build_daily_market_review_context` owns orchestration only. Provider-specific calls, scoring, taxonomy mapping, and portfolio relevance should stay in helper modules.

### Provider Interface

Create a narrow interface that supports degradation per data domain:

```python
class MarketDataProvider(Protocol):
    name: str

    def probe_capabilities(self, markets: list[str]) -> ProviderProbeResult: ...
    def get_session_state(self, market: str, review_dt: datetime) -> SessionState: ...
    def get_index_quotes(self, market: str, session: SessionState) -> FetchResult[list[IndexQuote]]: ...
    def get_market_turnover(self, market: str, session: SessionState) -> FetchResult[TurnoverSnapshot]: ...
    def get_breadth(self, market: str, session: SessionState) -> FetchResult[BreadthSnapshot]: ...
    def get_hot_stocks(self, market: str, session: SessionState, limit: int) -> FetchResult[list[HotStockCandidate]]: ...
    def get_hot_industries(self, market: str, session: SessionState, limit: int) -> FetchResult[list[HotIndustryCandidate]]: ...
    def get_catalysts(self, market: str, symbols: list[str], themes: list[str]) -> FetchResult[list[CatalystSnippet]]: ...
```

Each `FetchResult` must include:

- `status`: `ok`, `partial`, `stale`, `missing`, `failed`, or `not_configured`.
- `provider`.
- `fetched_at`.
- `source_refs`.
- `warnings`.
- `raw_sample` or `raw_metadata`, sanitized and credential-free.

### Futu Provider

Extend the existing `investment_knowledge_mcp.futu_provider` carefully or add quote-specific code in `market_data/providers/futu_quote.py` to avoid mixing trade/account operations with market review fetches.

Expected Futu calls:

- Market state, global state, and trading days for session labels.
- Snapshots and historical candlesticks for indexes, stocks, and rolling turnover baselines.
- Real-time data or intraday candlesticks for intraday turnover projection.
- Stock filter for hot-stock candidate screening by return, turnover, volume, amplitude, and turnover rate.
- Plate list, plate stocks, and owner plate for industry/theme ranking and stock-to-theme mapping.

If quote authority blocks a call, return a structured `failed` or `partial` result with the provider error summarized, not a hard crash for the whole report.

### AkShare Provider

Use AkShare as fallback/cross-check where installed and allowed:

- CN industry/concept board rankings.
- Eastmoney/THS hot rankings and fund-flow style board summaries.
- HK hot-rank style endpoints when available.

AkShare output must be marked `prototype_fallback` in source diagnostics unless later production approval changes that status.

### LongPort And Polygon/Massive Providers

Add configuration and interfaces, but keep them optional in V1:

- LongPort can enrich HK/US/CN turnover, intraday, trading sessions, and market-temperature data.
- Polygon/Massive can fill U.S. broad-market daily summaries or snapshots when broker APIs cannot screen the U.S. market well enough.

If credentials are not configured, diagnostics should say `not_configured`, and V1 should continue with available sources.

### Dependency Policy

Current committed dependencies include `futu-api` but not AkShare, LongPort, or Polygon/Massive client libraries. Non-Futu providers must use lazy imports inside provider methods, never module-level imports that can break `scripts/smoke_test.py` in a clean environment.

V1 implementation must choose one of two explicit paths for each optional provider:

- Add the provider package to `requirements.txt`, document the deploy impact, and use full deploy because image/dependency layers change.
- Keep the provider optional and return `not_configured` or `dependency_missing` diagnostics when the package or credentials are absent.

The command router, repository, scoring, and Markdown renderer must pass local tests with only the currently committed dependencies installed.

### Provider Selection Policy

Use a domain-by-domain provider ladder instead of a single all-or-nothing provider:

- Futu first for session state, snapshots, candlesticks, screeners, and plates when quote permission allows it.
- LongPort second for session, turnover, intraday, and market-temperature enrichment when configured.
- AkShare as CN/HK heat, industry/concept, and hot-rank fallback or cross-check.
- Polygon/Massive only for U.S. broad-market screening when configured and approved.

If two providers cover the same domain, keep both source diagnostics but use one canonical normalized value for scoring. Candidate hot-stock and hot-industry lists may be merged only after symbol/name normalization and duplicate handling.

## Session And Date Resolution

Default timezone: `Asia/Singapore`.

Implement `session_calendar.resolve_review_sessions(review_dt, mode, markets)` returning per-market session metadata:

```json
{
  "market": "US",
  "session_date": "2026-06-22",
  "run_mode": "post_close",
  "label": "latest completed U.S. session",
  "timezone": "America/New_York",
  "is_open": false,
  "elapsed_session_ratio": null
}
```

The title must avoid implying that CN/HK/US sessions share the same calendar date when they do not.

Intraday projection must account for lunch breaks and trading windows per market. If no reliable intraday curve exists, render current turnover only and mark full-day projection unavailable.

## Data Model

Keep `review_reports` as the report artifact table, but add structured daily-market tables because V1 needs historical ranking and theme persistence without parsing Markdown.

Important storage constraint: the current `review_reports` unique key is `(report_type, period_start, period_end)`. That is not enough for Daily Market Review because two reports can share the same represented session date range while differing by requested market set, run mode, or refresh intent. The implementation must not overload `report_type` with encoded market names. Add a stable report artifact key and move report upserts to that key before saving daily-market reports.

Schema additions:

```sql
ALTER TABLE review_reports ADD COLUMN IF NOT EXISTS report_key TEXT;

UPDATE review_reports
SET report_key = CONCAT(
  report_type,
  ':',
  COALESCE(period_start::text, report_date::text),
  ':',
  COALESCE(period_end::text, report_date::text)
)
WHERE report_key IS NULL;

DROP INDEX IF EXISTS idx_review_reports_type_period;

CREATE UNIQUE INDEX IF NOT EXISTS idx_review_reports_report_key
  ON review_reports (report_key);

ALTER TABLE review_reports ALTER COLUMN report_key SET NOT NULL;

CREATE TABLE IF NOT EXISTS market_data_fetches (
  id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  domain TEXT NOT NULL,
  session_date DATE,
  status TEXT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL,
  source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  diagnostics JSONB NOT NULL DEFAULT '{}'::jsonb,
  raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_market_reviews (
  id BIGSERIAL PRIMARY KEY,
  review_key TEXT NOT NULL UNIQUE,
  report_id BIGINT REFERENCES review_reports(id) ON DELETE SET NULL,
  requested_date DATE NOT NULL,
  session_label TEXT NOT NULL,
  markets JSONB NOT NULL DEFAULT '[]'::jsonb,
  run_mode TEXT NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL,
  source_coverage JSONB NOT NULL DEFAULT '{}'::jsonb,
  structured_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS daily_market_snapshots (
  id BIGSERIAL PRIMARY KEY,
  review_id BIGINT NOT NULL REFERENCES daily_market_reviews(id) ON DELETE CASCADE,
  market TEXT NOT NULL,
  session_date DATE NOT NULL,
  run_mode TEXT NOT NULL,
  mood TEXT NOT NULL,
  sentiment_score NUMERIC,
  volume_state TEXT NOT NULL,
  confidence TEXT NOT NULL,
  snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_status JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (review_id, market)
);

CREATE TABLE IF NOT EXISTS daily_market_hot_stocks (
  id BIGSERIAL PRIMARY KEY,
  review_id BIGINT NOT NULL REFERENCES daily_market_reviews(id) ON DELETE CASCADE,
  market TEXT NOT NULL,
  rank INTEGER NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT,
  move_pct NUMERIC,
  volume_heat NUMERIC,
  theme TEXT,
  catalyst TEXT,
  confidence TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (review_id, market, rank)
);

CREATE TABLE IF NOT EXISTS daily_market_hot_industries (
  id BIGSERIAL PRIMARY KEY,
  review_id BIGINT NOT NULL REFERENCES daily_market_reviews(id) ON DELETE CASCADE,
  market TEXT NOT NULL,
  rank INTEGER NOT NULL,
  industry_name TEXT NOT NULL,
  theme_label TEXT,
  performance_pct NUMERIC,
  volume_heat NUMERIC,
  confidence TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (review_id, market, rank)
);

CREATE INDEX IF NOT EXISTS idx_market_data_fetches_market_domain
  ON market_data_fetches (market, domain, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_daily_market_reviews_requested_date
  ON daily_market_reviews (requested_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_market_hot_stocks_symbol
  ON daily_market_hot_stocks (market, symbol);

CREATE INDEX IF NOT EXISTS idx_daily_market_hot_industries_name
  ON daily_market_hot_industries (market, industry_name);
```

Also persist the Markdown in `review_reports`:

```text
report_key = daily_market:<requested_date>:<sorted_markets>:<run_mode>
report_type = daily_market
period_start = minimum represented session date
period_end = maximum represented session date
summary = rendered Markdown
source_status = source coverage and provider diagnostics
highlights = executive snapshot items
story = center-of-gravity and theme persistence payload
portfolio_snapshot = portfolio/watchlist relevance payload
```

Repository work:

- Extend `upsert_review_report(...)` with an optional `report_key` argument and update the SQL to use `ON CONFLICT (report_key)`.
- Preserve existing call sites by deriving a default key from `report_type`, `period_start`, `period_end`, and `report_date` when the caller does not pass one.
- Save `daily_market_reviews.review_key` equal to `review_reports.report_key` so structured rows and Markdown artifacts have one stable identity.
- Normalize the market set in the key by sorting and uppercasing, for example `CN,HK,US`, so caller ordering does not create duplicate reports.
- Verify weekly review still overwrites the same natural-week report after this migration.

## Context Shape

The internal context should be JSON-serializable:

```python
{
    "request": {
        "requested_date": "2026-06-23",
        "markets": ["CN", "US", "HK"],
        "mode": "mixed",
        "timezone": "Asia/Singapore",
        "force_refresh": False,
    },
    "sessions": {},
    "executive_snapshot": {},
    "center_of_gravity": {},
    "markets": {
        "CN": {
            "session": {},
            "sentiment": {},
            "volume": {},
            "hot_stocks": [],
            "hot_industries": [],
            "coverage": {},
            "warnings": [],
        }
    },
    "theme_persistence": {},
    "portfolio_relevance": {},
    "source_diagnostics": {},
    "warnings": [],
}
```

## Markdown And JSON Render Contract

The renderer must emit the PRD's default section order:

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

Each hot-stock row must include rank, symbol/name, market, move, volume heat, catalyst or `unknown`, theme, grounded "why hot" text, user relevance, and confidence.

Each hot-industry row must include rank, industry/theme, market, performance, volume heat, representative stocks, catalyst or `unknown`, why it matters, and confidence.

The command path should default to Markdown. `--format json` should return the same structured payload used for storage, with Markdown included under a `markdown` field for callers that need both.

## Scoring Rules

Use deterministic scoring first. A model may later summarize, but it must not decide facts.

Sentiment inputs:

- Index returns and relative index leadership.
- Breadth, when available.
- Turnover versus 5-day, 20-day, and 60-day baselines.
- Concentration of top stocks and industries.
- Volatility/risk proxy where available.

Suggested sentiment score:

```text
score = index_component + breadth_component + volume_component + risk_component + theme_component
```

Map score and coverage to labels:

- `strong_risk_on`
- `risk_on_but_narrow`
- `mixed_rotation`
- `risk_off`
- `liquidity_weak`
- `data_insufficient`

Hot stock score:

```text
0.35 * relative_move
+ 0.25 * turnover_abnormality
+ 0.15 * catalyst_quality
+ 0.15 * theme_relevance
+ 0.10 * user_relevance
```

Hot industry score:

```text
0.30 * sector_return
+ 0.25 * sector_turnover_heat
+ 0.20 * sector_breadth
+ 0.15 * hot_stock_density
+ 0.10 * cross_market_echo_or_catalyst
```

If a component is unavailable, rescale only over available components and lower confidence. Do not silently assign neutral values to missing facts.

## Portfolio And Watchlist Relevance

Reuse first-party data:

- `get_realtime_portfolio_positions`/Futu positions where explicitly invoked through existing provider code.
- Existing stock profiles, sector relations, knowledge items, candidate insights, and confirmed user insights.
- Future watchlist table/API only when it exists.

Relevance output should say `portfolio_overlap`, `theme_overlap`, `watchlist_overlap`, `knowledge_overlap`, or `unavailable`. It must frame next research/risk-review questions, not trade instructions.

## Command Router Changes

Add daily-market commands without disturbing weekly review matching:

```text
DAILY_MARKET_REVIEW_COMMANDS = {
    "每日复盘",
    "今日复盘",
    "市场复盘",
    "日复盘",
    "复盘今天市场",
    "daily market review",
}
```

Parsing rules:

- Date: parse explicit `YYYY-MM-DD`; otherwise latest available sessions.
- Markets: parse `--market CN,US,HK`, default all three.
- Mode: parse `--mode pre_open|intraday|post_close`; otherwise infer.
- Force refresh: parse `--force-refresh`.
- Format: parse `--format markdown|json`, default `markdown`.

Return the Markdown report and append a saved report footer when `save=True`.

`is_query_command` should treat daily market review commands as read-mostly query commands. Saving the report artifact is allowed by the PRD and mirrors weekly review behavior.

## API And Retrieval Helpers

V1 does not need a new HTTP server, but the service should expose functions that command-api or a future web route can call:

```python
get_latest_daily_market_review(markets: list[str] | None = None) -> dict[str, Any] | None
get_daily_market_review_by_date(review_date: date, markets: list[str] | None = None) -> dict[str, Any] | None
list_daily_market_reviews(limit: int = 20) -> list[dict[str, Any]]
```

Repository helpers should read from `daily_market_reviews` and join to `review_reports` for Markdown.

## Source Diagnostics

Every rendered report must include a coverage table:

```text
Market | Provider | Domain | Status | Fetched At | Notes
```

Coverage status per market:

- `complete`: required domains available and fresh.
- `partial_coverage`: at least one required domain missing but the report remains useful.
- `stale`: data is older than the represented session or provider freshness limit.
- `failed`: the market section cannot be produced beyond diagnostics.
- `not_configured`: provider credentials or dependency are absent.

Report confidence is capped by source coverage:

- Any market with only one reliable domain cannot exceed `low`.
- Cross-market center of gravity cannot exceed `low` if fewer than two markets have useful coverage.
- A hot-stock or hot-industry row cannot exceed `medium` when catalyst evidence is missing.

## Provider Coverage Probe

Add a non-writing probe command/script before enabling production use:

```text
.venv/bin/python scripts/probe_daily_market_providers.py --markets CN,US,HK
```

The probe should:

- Check configured provider dependencies and credentials without printing secrets.
- Fetch one session-state sample per market.
- Fetch one index quote sample per market.
- Fetch one turnover or volume sample per market.
- Fetch stock screener or hot-rank candidates per market.
- Fetch sector/industry candidates per market.
- Print a domain coverage matrix and write a sanitized JSON artifact under `artifacts/provider-probes/`.

This script is the concrete answer to the PRD's open provider decisions. Implementation can proceed with partial coverage only if the generated diagnostics make the limitation explicit.

## Verification Plan

Local deterministic tests:

- Session resolver handles Asia morning, A/HK intraday, A/HK post-close before U.S. close, and after U.S. close.
- Intraday elapsed-session ratio handles CN/HK lunch breaks.
- Scoring maps fixture data to expected sentiment labels and confidence caps.
- Hot stock and hot industry ranking order is stable from fixtures.
- Missing provider domains lower confidence and render missing-data diagnostics.
- Markdown contains all required PRD sections and no direct trade instructions.
- Repository upsert/retrieval is idempotent by review key.
- Command router recognizes daily review commands and does not collide with weekly review commands.

Recommended command:

```bash
.venv/bin/python scripts/smoke_test.py
```

Add narrow tests to the smoke suite with fake providers so normal local verification does not require live Futu, LongPort, Polygon, or AkShare network access.

Live/provider checks:

- Run `scripts/probe_daily_market_providers.py` only when provider access is explicitly approved or already available in the environment.
- If cloud-side provider permissions differ from local, verify through the approved cloud read path before deploying a cloud-served scheduler or web surface.

## Rollout And Deployment

Manual command-only V1 is a normal application release. It changes database schema and command-router behavior but does not require starting `command-api`, `dingtalk-api`, schedulers, or Docker Compose for local verification.

Deployment notes:

- If only Python/schema code changes, use the normal pull-based quick deploy after commit/push approval.
- If dependency additions are required for AkShare, LongPort, or Polygon clients, use full deploy because `requirements.txt` or image layers change.
- Do not enable scheduled generation in V1. A future scheduler requires explicit service startup/deployment review and provider credential verification.

## Risks And Mitigations

Provider coverage uncertainty:

- Mitigation: provider probe first, source diagnostics in every report, optional providers behind configuration.

Data freshness and session mismatch:

- Mitigation: per-market session labels, provider fetched-at timestamps, confidence caps.

Ranking overfits one provider's hot list:

- Mitigation: score from normalized candidates and label provider-specific fallback data as such.

Industry taxonomy conflicts across CN/US/HK:

- Mitigation: keep local provider taxonomy in V1, add canonical theme labels in `taxonomy.py`, and preserve provider names in payload.

Markdown becomes fluent but unsupported:

- Mitigation: deterministic rendering from structured context; model summarization remains optional and evidence-bound.

Database churn:

- Mitigation: idempotent review keys, separate structured tables for rankings, and sanitized raw metadata only.

## Implementation Checklist

- [ ] Add schema tables and repository helpers for daily market reviews, snapshots, rankings, and provider fetches.
- [ ] Add provider models, fake provider fixtures, and `FetchResult` diagnostics.
- [ ] Implement session/date resolution for CN, HK, and US.
- [ ] Implement Futu quote provider coverage needed for session, index, turnover, screeners, and plates.
- [ ] Implement AkShare fallback provider where dependency is available.
- [ ] Add optional LongPort and Polygon/Massive provider stubs/configuration with `not_configured` diagnostics.
- [ ] Add provider probe script and sanitized artifact output.
- [ ] Implement deterministic scoring, confidence caps, and taxonomy mapping.
- [ ] Build daily review context and Markdown renderer.
- [ ] Persist report body and structured payload idempotently.
- [ ] Wire command router commands and query-command classification.
- [ ] Add smoke/unit tests with fake providers.
- [ ] Run local smoke verification.
- [ ] Review PRD acceptance criteria against implementation before release.

## Open Technical Decisions

- Which Futu quote APIs are available under the deployed account's permissions for each market.
- Whether AkShare should be added as a committed dependency or treated as optional import-only fallback.
- Whether LongPort credentials are approved for V1 enrichment.
- Whether Polygon/Massive U.S. all-market access is approved if Futu/LongPort U.S. screeners are insufficient.
- Whether `daily_market_reviews.review_key` should include requested market set ordering or a normalized sorted market list.
- Whether later web rendering should read directly from structured daily tables or from `review_reports.story` plus ranking tables.

These do not block the technical plan from being ready; they are addressed by the provider probe and implementation checklist before V1 is called usable.
