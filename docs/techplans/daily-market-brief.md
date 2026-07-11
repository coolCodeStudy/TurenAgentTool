# Daily Market Brief Technical Plan

Status: partially_implemented
Owner: Development Agent
Source PRD: `docs/product/PRD-Daily-Market-Brief.md`
Feature Registry row: `Daily market brief`
Acceptance Queue rows: `AT-2026-06-30-002`, `AT-2026-07-01-001`
Last updated: 2026-06-30

## Scope

Implement P0 as a Web-reviewable, command-retrievable, scheduler-ready daily close report for CN, HK, and US markets. The report persists as `review_reports.report_type = daily_market_brief`, is idempotent by market and market date, renders Simplified Chinese Markdown, and records source/degraded states for unavailable provider coverage.

Out of scope for this pass: DingTalk push, paid data providers, cross-market sector taxonomy normalization, cloud deployment, and user acceptance.

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
- Sectors/industries and top gainers: live generation now uses AKShare/Eastmoney where coverage is reliable enough for a daily brief. CN uses AKShare industry-board rankings and liquidity-filtered A-share gainers; HK uses AKShare Hong Kong main-board gainers; US uses AKShare US stock gainers with warrant/right-like rows filtered out. HK/US sector rankings remain explicit degraded states until an equally reliable provider is added.
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

The page exposes CN/HK/US tabs, market-date selection, read/generate actions, summary cards, narrative, core-index table, sector/gainer/flow tables, source-status table, and Markdown original. Daily Market Brief read and live-generation APIs are public so the user does not need to create or enter a token. The public generation endpoint accepts only the selected market's latest completed session, rejects fixture mode and older/future dates, and applies a per-market/date single-flight gate with a 60-second cooldown. Schema initialization stays in service startup, not the public request path. Other Weekly Review Web write surfaces remain token-protected. The command surface remains the underlying product path for scheduler, operational reruns, fixture verification, retrieval, and regression verification; the Web page is the user acceptance surface.

Live operational reruns are also limited to the latest completed session. Historical live generation may be rendered without saving to explain provider limitations, but it cannot overwrite a stored historical brief with empty spot-ranking sections. Historical replacement requires a provider that supplies genuine historical sector, gainer, and flow rankings.

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
| HK brief includes required P0 indexes, sectors/industries when supported, gainers, flow/degraded state, turnover baselines | verified | `tests.test_daily_market_brief`; fake-AKShare unit coverage; `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 HK 2026-06-30 fixture` | HK command fixture renders all three P0 indexes. Live mode now attempts AKShare Hong Kong main-board gainers; HK sector and fund-flow rows remain explicit degraded states. |
| US brief includes required P0 indexes, sectors/industries when supported, common-stock gainers, explicit flow degraded state, volume baselines | verified | `tests.test_daily_market_brief`; fake-AKShare unit coverage; `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 US 2026-06-30 fixture` | US command fixture renders all four P0 indexes. Live mode now attempts AKShare US gainers after filtering warrant/right-like rows; US sector and fund-flow rows remain explicit degraded states. |
| Independent market scheduler and rerun semantics | local_verified | `run_daily_market_brief_scheduler_forever`, `run_daily_market_brief_once`; scheduler timezone unit test; `daily-market-brief-scheduler` Compose service and deploy target | Production wiring now starts one scheduler process that tracks CN/HK/US independently and is covered by deploy process health checks. Cloud runtime verification remains required. |
| Idempotent storage by report type, market, market date | verified | `repository.upsert_daily_market_brief_report`; `db/schema.sql`; DB smoke on `POSTGRES_PORT=55433` | Market-aware `report_key` values are protected by a unique partial index and transaction-scoped advisory lock, preventing concurrent public/scheduler inserts for the same market/date. |
| Missing provider coverage visible in user language | verified | Renderer and degraded-state unit test; forced command-router provider failure | Source status is explicit for sectors/gainers/flow; raw provider/SSL/internal exception text is not rendered in user-facing Markdown. |
| Command surface retrieves latest and specified market/date | verified | `command_router.py`; command retrieval unit test | HTTP command API is not required for local verification. |
| Web surface lets the user review latest/specified market/date briefs | local_verified | `weekly_review_web.py`; `tests.test_daily_market_brief` Web render/response, latest-session, single-flight, holiday/incomplete-session, and historical-spot-safety tests; `AT-2026-07-01-001` | The public page has CN/HK/US read/generate controls without a token or fixture control. Public generation is limited to the market's latest completed session; historical reads remain available without mixing current spot rankings into past dates. Cloud deployment and black-box retest remain required before asking for final user acceptance. |
| Stored report includes structured context and source status | verified | `repository.upsert_daily_market_brief_report`; DB smoke on `POSTGRES_PORT=55433` | Context is stored in `portfolio_snapshot`; status in `source_status`; saved rows were retrieved through the command surface. |
| Narrative is understandable and has no buy/sell recommendations | verified | Markdown assertions in `tests/test_daily_market_brief.py` | Renderer describes market breadth/leadership/liquidity/data gaps only. |
| Holiday/no-session runs produce explicit skipped/no-session state | verified | Weekend no-session unit test; `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 CN 2026-06-27 fixture` | Weekend command saved `review_reports #133` with explicit no-session copy. Full holiday calendars remain a future provider enhancement. |
| Independent acceptance testing before user acceptance | verified | `AT-2026-06-30-002` passed for command surface; `AT-2026-07-01-001` passed for the Web surface | User acceptance remains pending and must happen through the Web page, not CLI commands. |

## Risks And Blockers

- AKShare/Eastmoney data can be source-limited or temporarily unavailable. Live generation must degrade in product language and keep indexes/other available sections rather than exposing raw provider exceptions.
- Full exchange holiday detection is unavailable locally. Weekend no-session is implemented; exchange-holiday calendars are a future provider/data-source task.
- Cloud deployment is coordinator-owned. Because `requirements.txt` adds AKShare, the initial integrated release requires the classified full-image path; subsequent code-only changes should use the normal quick path.
- The scheduler is also included in the independent Ops API service catalog, recent-error collection, and deploy health. Because `scripts/ecs_ops_api.py` and `scripts/deploy_contract.py` changed, `/opt/investment-ops` must be bootstrapped before the first business full-image deployment so the server-side classifier recognizes the new target.
