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
- Sectors/industries and top gainers: no reliable full-market common-equity universe exists in the current repo. Default live generation records these as `provider_unavailable` degraded states instead of inventing rankings.
- Capital flow: no configured no-paid provider currently exposes explicit market/stock/sector flow metrics for all three markets. Default live generation records explicit degraded states; fixtures may provide CN/HK flow-like rows only for deterministic tests.
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

The page exposes CN/HK/US tabs, market-date selection, read/generate/fixture-generate actions, summary cards, narrative, core-index table, sector/gainer/flow tables, source-status table, and Markdown original. It reuses the weekly-review Web token authorization path and renders missing/degraded states in product language. The command surface remains the underlying product path for scheduler, retrieval, and regression verification; the Web page is the user acceptance surface.

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
| CN brief includes required P0 indexes, sectors/industries, gainers, flow/degraded state, volume baselines, source labels, date, timestamp | verified | `tests.test_daily_market_brief`; `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 CN 2026-06-30 fixture` | CN command fixture now uses deterministic index bars and renders all five P0 indexes; same-market rerun reused `review_reports #130`. Live sectors/gainers/flow degrade until a configured full-market provider exists. |
| HK brief includes required P0 indexes, sectors/industries when supported, gainers, flow/degraded state, turnover baselines | verified | `tests.test_daily_market_brief`; `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 HK 2026-06-30 fixture` | HK command fixture renders all three P0 indexes and saved beside CN as `review_reports #131`. Same provider limitation as CN for live sectors/gainers. |
| US brief includes required P0 indexes, sectors/industries when supported, common-stock gainers, explicit flow degraded state, volume baselines | verified | `tests.test_daily_market_brief`; `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 US 2026-06-30 fixture` | US command fixture renders all four P0 indexes and saved beside CN/HK as `review_reports #132`; US flow remains explicit degraded state per PRD. |
| Independent market scheduler and rerun semantics | verified | `run_daily_market_brief_scheduler_forever`, `run_daily_market_brief_once`; scheduler timezone unit test | Scheduler is ready as a module entrypoint; cloud service wiring is out of P0. |
| Idempotent storage by report type, market, market date | verified | `repository.upsert_daily_market_brief_report`; `db/schema.sql`; DB smoke on `POSTGRES_PORT=55433` | Existing rows show market-aware keys: CN `#130`, HK `#131`, and US `#132` for `2026-06-30`; weekend CN `#133` also saved. |
| Missing provider coverage visible in user language | verified | Renderer and degraded-state unit test; forced command-router provider failure | Source status is explicit for sectors/gainers/flow; raw provider/SSL/internal exception text is not rendered in user-facing Markdown. |
| Command surface retrieves latest and specified market/date | verified | `command_router.py`; command retrieval unit test | HTTP command API is not required for local verification. |
| Web surface lets the user review latest/specified market/date briefs | verified | `weekly_review_web.py`; `tests.test_daily_market_brief` Web render/response tests; `AT-2026-07-01-001` | Independent local Web acceptance passed for `/daily-market-brief`, API read/generate, CN/HK/US tabs, fixture rendering, missing states, idempotency, and desktop/mobile usability. Cloud deployment still needs Coordinator/Ops handling before asking for final user acceptance on the deployed page. |
| Stored report includes structured context and source status | verified | `repository.upsert_daily_market_brief_report`; DB smoke on `POSTGRES_PORT=55433` | Context is stored in `portfolio_snapshot`; status in `source_status`; saved rows were retrieved through the command surface. |
| Narrative is understandable and has no buy/sell recommendations | verified | Markdown assertions in `tests/test_daily_market_brief.py` | Renderer describes market breadth/leadership/liquidity/data gaps only. |
| Holiday/no-session runs produce explicit skipped/no-session state | verified | Weekend no-session unit test; `POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 CN 2026-06-27 fixture` | Weekend command saved `review_reports #133` with explicit no-session copy. Full holiday calendars remain a future provider enhancement. |
| Independent acceptance testing before user acceptance | verified | `AT-2026-06-30-002` passed for command surface; `AT-2026-07-01-001` passed for the Web surface | User acceptance remains pending and must happen through the Web page, not CLI commands. |

## Risks And Blockers

- Current repo has no full-market sector/industry and common-equity ranking provider. P0 will not invent this data in live mode; it records degraded state and uses fixtures for deterministic verification.
- Full exchange holiday detection is unavailable locally. Weekend no-session is implemented; exchange-holiday calendars are a future provider/data-source task.
- Cloud deployment is out of this handoff unless the coordinator explicitly approves it.
