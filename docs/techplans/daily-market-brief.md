# Daily Market Brief Technical Plan

Status: deployed_pending_user_acceptance
Owner: Daily Market Brief Feature Coordinator
Source PRD: `docs/product/PRD-Daily-Market-Brief.md`
Feature Registry row: `Daily market brief`
Acceptance Queue rows: `AT-2026-06-30-002`, `AT-2026-07-01-002`, `AT-2026-07-10-001`
Last updated: 2026-07-11

## Scope

Implement P0 as a Web-reviewable, command-retrievable, scheduler-ready daily close report for CN, HK, and US markets. The report persists as `review_reports.report_type = daily_market_brief`, is idempotent by market and market date, renders Simplified Chinese Markdown, and records source/degraded states for unavailable provider coverage.

Out of scope for this pass: DingTalk push, paid data providers, cross-market sector taxonomy normalization, and user acceptance.

## Production Verification

- Integrated release: `main` commit `254e38ff430c8bc75ef176d8119fe3fc4ebc83c7`; full-image deploy run `29148635683` succeeded.
- HK/US bounded Sina gainer fallback: `main` commit `027b9228a2658fb3aebc78afcc9a72f4d6db1764`; quick deploy run `29149263462` succeeded after the Ops API source-refresh fix in `main` commit `ff750055a3c214230162116dde39c07925f6e559`.
- Cloud page: `http://47.84.190.191:8010/daily-market-brief` returned the tokenless CN/HK/US review surface. Browser verification found CN with 5 indexes, 5 sectors, and 5 gainers; HK with 3 indexes and 5 gainers; US with 4 indexes and 5 gainers. Unsupported HK/US sectors and unsupported capital-flow coverage are shown as product-language degraded states.
- Persisted 2026-07-10 reports coexist as CN `#19`, HK `#20`, and US `#21`. A fresh US rerun updated report `#21`, confirming same-market/date idempotency.
- At the 2026-07-10 acceptance point, older and future public generation requests were rejected with HTTP 400. The later Historical Jobs section supersedes the older-date behavior: older dates now enqueue durable single-date history jobs and future dates remain rejected. Cloud system status showed `daily-market-brief-scheduler` running alongside healthy Web, database, and control-plane services.
- `AT-2026-07-10-001` passed independent cloud acceptance on 2026-07-11. User acceptance remains pending.

## Touched Modules

- `investment_knowledge_mcp/daily_market_brief.py`: generation, rendering, persistence wrapper, scheduler-ready loop, fixture provider for deterministic verification.
- `investment_knowledge_mcp/command_router.py`: command retrieval and manual generation/rerun entrypoints.
- `investment_knowledge_mcp/weekly_review_web.py`: `/daily-market-brief` user-facing page plus read/generate APIs on the existing Web service.
- `investment_knowledge_mcp/repository.py`: daily-brief-specific upsert and lookup helpers over `review_reports`.
- `investment_knowledge_mcp/market_data_provider.py`: Yahoo symbol coverage for P0 index lists where supported.
- `tests/test_daily_market_brief.py`: focused unit tests for generation, idempotency, degraded states, command retrieval, and scheduler date behavior.

## Storage And Idempotency

P0 reuses `review_reports` without a migration. Rows use:

- `report_type`: `daily_market_brief`
- `report_date`, `period_start`, `period_end`: market date
- `portfolio_snapshot`: structured context including `market.code`, indexes, sectors, gainers, flow, volume baselines, source status, and generated timestamps
- `summary`: rendered Markdown
- `source_status`: structured provider/degraded status
- `story`: narrative and scheduler metadata

Repository helpers find existing rows by `report_type = daily_market_brief`, `report_date`, and `portfolio_snapshot->'market'->>'code'`. Reruns update the existing market/date row instead of creating another confusing report.

Acceptance-fix update: databases that still have the legacy `review_reports.report_key` column or `idx_review_reports_report_key` unique index are handled safely. `db/schema.sql` rewrites existing daily-market-brief keys to `daily_market_brief:<market>:<start>:<end>`, gives duplicate legacy rows a non-conflicting suffix, drops the stale unique index, and adds a non-unique market/date lookup index. `repository.upsert_daily_market_brief_report` also writes the market-aware `report_key` when that legacy column exists, so CN/HK/US same-date briefs can coexist and same-market reruns remain idempotent.

## Provider Strategy

P0 does not add a paid provider dependency.

- Core indexes: use existing Yahoo chart fallback through `market_data_provider.get_yahoo_market_bars` for supported P0 index symbols.
- Sectors/industries and top gainers: live generation uses AKShare/Eastmoney where coverage is reliable enough for a daily brief. CN uses AKShare industry-board rankings and liquidity-filtered A-share gainers, with direct Eastmoney and Sina fallbacks. HK and US first use the corresponding AKShare/Eastmoney spot rankings; when those endpoints are unavailable, bounded Sina gainers queries provide the fallback without scanning the full market. The same turnover thresholds remain in force, and US warrant/right-like rows remain filtered out. HK/US sector rankings remain explicit degraded states until an equally reliable provider is added.
- Capital flow: CN uses AKShare/Eastmoney industry fund-flow ranking (`stock_sector_fund_flow_rank`) for top inflow segments. HK/US remain explicit degraded states because AKShare does not provide comparable no-paid, same-semantics flow coverage for those markets in this implementation.
- Verification fixtures: deterministic in-process fixture data can be injected by tests and by the scheduler/generator code path when explicitly requested. Fixture output is labeled `fixture` and is not presented as real market data.

## Command Surface

Supported P0 command intents:

- Show latest: `每日市场简报 CN`, `最新每日市场简报 HK`, `daily market brief US`
- Show specific date: `每日市场简报 CN 2026-06-30`
- Manual generate/rerun: `生成每日市场简报 CN 2026-06-30`, `重跑每日市场简报 US 2026-06-30`
- Fixture generation for local verification only: append `fixture` or `测试夹具` to a generation command.

The command path returns saved Markdown and does not start HTTP services.

## Web Surface

The existing weekly-review Web service also serves Daily Market Brief:

- Page: `/daily-market-brief`
- Read API: `GET /api/daily-market-brief?market=CN&date=2026-06-30`
- Generate API: `POST /api/daily-market-brief/generate`

The page exposes CN/HK/US tabs, market-date selection, read/generate actions, summary cards, narrative, core-index table, sector/gainer/flow tables, source-status table, and Markdown original. Daily Market Brief read and current-session live-generation APIs are public so the user does not need to create or enter a token. The public generation endpoint accepts the selected market's latest completed session, rejects fixture mode and future dates, and applies a per-market/date single-flight gate with a 60-second cooldown. When the selected date is older than the latest completed session, the Web endpoint enqueues a durable single-date history job and returns HTTP 202 immediately. Schema initialization stays in service startup, not the public request path. Other Weekly Review Web write surfaces remain token-protected. The command surface remains the underlying product path for scheduler, operational reruns, fixture verification, retrieval, and regression verification; the Web page is the user acceptance surface.

Live operational reruns are also limited to the latest completed session. Historical reconstruction jobs may save partial historical reports when the provider can supply real historical index bars but not exact historical sector, gainer, or flow rankings; missing sections are labeled as unavailable rather than filled from current spot rankings.

## Historical Jobs

Status: implemented_pending_deploy
Last updated: 2026-07-12

- Public Web historical generation accepts exactly one `market` and one `date`, rejects future dates and workload-control fields, and enqueues through `daily_market_brief_jobs` / `daily_market_brief_job_items`.
- Public job status APIs expose only `source = web` and `request_type = single` jobs. If a tokenless Web request collides with an authenticated batch item for the same market/date, it returns a capacity response instead of leaking the authenticated parent batch.
- Authenticated Command Workbench and the trusted MCP command path support batch backfill, status, and cancellation commands. Workbench write actions require confirmation; the public page has no batch or cancel control.
- `scripts/daily_market_brief_history_worker.py` processes at most one item globally through PostgreSQL advisory locking and item leases. Provider work runs synchronously inside the claimed item lifecycle; the worker-level deadline covers the whole item and no provider thread is allowed to continue after the item returns.
- Cancellation, lease checks, report upsert, terminalization, and parent-job recompute are serialized in transactions. A canceled item cannot save a report after cancellation wins the lease check.
- Recent-trading-day batch expansion stops before each market's latest completed session, leaving that date for the realtime close generator.
- MCP is still a trusted internal/control-plane surface. The production Compose default binds the MCP host port to `127.0.0.1` via `MCP_BIND_HOST`, so the unauthenticated MCP transport is not publicly exposed by default.
- Workbench and MCP command failures use sanitized public messages when failed `CommandResult` values contain connection strings, SQL, tracebacks, filesystem paths, SSL/provider internals, tokens, or credentials.

## Scheduler-Ready Entry Points

`investment_knowledge_mcp.daily_market_brief` exposes:

- `run_daily_market_brief_once(market, market_date=None, save=True, use_fixture=False)`
- `run_daily_market_brief_scheduler_forever(markets=None, interval_seconds=300)`
- CLI module entrypoint: `python -m investment_knowledge_mcp.daily_market_brief --once --market CN --date 2026-06-30`

The scheduler loop tracks CN/HK/US independently, only runs after each market's local close time, and records no-session states for weekends. A full exchange holiday calendar remains a P1/provider enhancement.

## Verification Plan

- `git diff --check`
- `python3 scripts/audit_delivery_state.py --feature "Daily market brief"`
- `.venv/bin/python -m unittest tests.test_daily_market_brief`
- `.venv/bin/python -m py_compile investment_knowledge_mcp/daily_market_brief.py investment_knowledge_mcp/command_router.py investment_knowledge_mcp/repository.py investment_knowledge_mcp/market_data_provider.py`
- Local command smoke with `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py ...` covering CN/HK/US fixture generation, specific/latest retrieval, same-market rerun idempotency, cross-market same-date coexistence, weekend/no-session behavior, and forced degraded product-language output.
- Web surface checks for `render_daily_market_brief_html`, `/daily-market-brief`, `/api/daily-market-brief`, and `/api/daily-market-brief/generate`.

## Implementation Traceability

| PRD scope / acceptance criterion | Status | Evidence | Notes |
|---|---|---|---|
| CN brief includes required P0 indexes, sectors/industries, gainers, flow/degraded state, volume baselines, source labels, date, timestamp | verified | `tests.test_daily_market_brief`; fake-AKShare unit coverage; `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 CN 2026-06-30 fixture` | CN command fixture still uses deterministic index bars. Live mode now attempts AKShare/Eastmoney industry-board rankings, liquidity-filtered A-share gainers, and industry fund-flow ranking before degrading. |
| HK brief includes required P0 indexes, sectors/industries when supported, gainers, flow/degraded state, turnover baselines | verified | `tests.test_daily_market_brief`; fake-AKShare and direct HTTP fallback coverage; live HK fallback probe; `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 HK 2026-06-30 fixture` | HK command fixture renders all three P0 indexes. Live mode attempts AKShare Hong Kong main-board gainers, then bounded direct Eastmoney/Sina rankings; HK sector and fund-flow rows remain explicit degraded states. |
| US brief includes required P0 indexes, sectors/industries when supported, common-stock gainers, explicit flow degraded state, volume baselines | verified | `tests.test_daily_market_brief`; fake-AKShare and direct HTTP fallback coverage; live US fallback probe; `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 US 2026-06-30 fixture` | US command fixture renders all four P0 indexes. Live mode attempts AKShare US gainers, then bounded direct Eastmoney/Sina rankings after turnover and warrant/right-like filtering; US sector and fund-flow rows remain explicit degraded states. |
| Independent market scheduler and rerun semantics | deploy_verified | `run_daily_market_brief_scheduler_forever`, `run_daily_market_brief_once`; scheduler timezone unit test; cloud system status on 2026-07-11 | Production runs one `daily-market-brief-scheduler` process that tracks CN/HK/US independently; controlled cloud status reported it running with healthy dependencies. |
| Idempotent storage by report type, market, market date | verified | `repository.upsert_daily_market_brief_report`; `db/schema.sql`; DB smoke on `POSTGRES_PORT=55433` | Market-aware `report_key` values are protected by a unique partial index and transaction-scoped advisory lock, preventing concurrent public/scheduler inserts for the same market/date. |
| Missing provider coverage visible in user language | verified | Renderer and degraded-state unit test; forced command-router provider failure | Source status is explicit for sectors/gainers/flow; raw provider/SSL/internal exception text is not rendered in user-facing Markdown. |
| Command surface retrieves latest and specified market/date | verified | `command_router.py`; command retrieval unit test | HTTP command API is not required for local verification. |
| Web surface lets the user review latest/specified market/date briefs | deploy_verified | `weekly_review_web.py`; `tests.test_daily_market_brief`; `AT-2026-07-01-002`; `AT-2026-07-10-001`; cloud browser/API verification on 2026-07-11 | The deployed public page has CN/HK/US read/generate controls without token or fixture controls. Latest-session generation, historical reads, date bounds, useful rankings, and safe degraded states passed black-box cloud verification. |
| Stored report includes structured context and source status | verified | `repository.upsert_daily_market_brief_report`; DB smoke on `POSTGRES_PORT=55433` | Context is stored in `portfolio_snapshot`; status in `source_status`; saved rows were retrieved through the command surface. |
| Narrative is understandable and has no buy/sell recommendations | verified | Markdown assertions in `tests/test_daily_market_brief.py` | Renderer describes market breadth/leadership/liquidity/data gaps only. |
| Holiday/no-session runs produce explicit skipped/no-session state | verified | Weekend no-session unit test; `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 CN 2026-06-27 fixture` | Weekend command saved `review_reports #133` with explicit no-session copy. Full holiday calendars remain a future provider enhancement. |
| Independent acceptance testing before user acceptance | verified | `AT-2026-06-30-002`, `AT-2026-07-01-002`, and `AT-2026-07-10-001` passed | User acceptance remains pending and must happen through the deployed Web page, not CLI commands. |

## Risks And Blockers

- AKShare/Eastmoney data can be source-limited or temporarily unavailable. Live generation must degrade in product language and keep indexes/other available sections rather than exposing raw provider exceptions.
- Full exchange holiday detection is unavailable locally. Weekend no-session is implemented; exchange-holiday calendars are a future provider/data-source task.
- The initial AKShare dependency release required and completed a full-image deployment. Subsequent code-only releases should use the normal quick path unless the deploy classifier requires a rebuild.
- The scheduler is included in the independent Ops API service catalog, recent-error collection, and deploy health. The control plane was bootstrapped before the final quick deployment, and source resolution now fetches `origin/main` before reachability validation.
