# Daily Market Brief Technical Plan

Status: partially_implemented
Owner: Development Agent
Source PRD: `docs/product/PRD-Daily-Market-Brief.md`
Feature Registry row: `Daily market brief`
Acceptance Queue row: `AT-2026-06-30-002`
Last updated: 2026-06-30

## Scope

Implement P0 as a command-retrievable, scheduler-ready daily close report for CN, HK, and US markets. The report persists as `review_reports.report_type = daily_market_brief`, is idempotent by market and market date, renders Simplified Chinese Markdown, and records source/degraded states for unavailable provider coverage.

Out of scope for this pass: DingTalk push, standalone Web page, Weekly Review Web integration, paid data providers, cross-market sector taxonomy normalization, cloud deployment, and user acceptance.

## Touched Modules

- `investment_knowledge_mcp/daily_market_brief.py`: generation, rendering, persistence wrapper, scheduler-ready loop, deterministic fixture provider for indexes/activity, and product-language degraded-state rendering.
- `investment_knowledge_mcp/command_router.py`: command retrieval and manual generation/rerun entrypoints.
- `investment_knowledge_mcp/repository.py`: daily-brief-specific upsert and lookup helpers over `review_reports`.
- `investment_knowledge_mcp/market_data_provider.py`: Yahoo symbol coverage for P0 index lists where supported.
- `tests/test_daily_market_brief.py`: focused unit tests for generation, idempotency, degraded states, command retrieval, and scheduler date behavior.

## Storage And Idempotency

P0 reuses `review_reports` and normalizes legacy `report_key` behavior in `db/schema.sql`. Rows use:

- `report_type`: `daily_market_brief`
- `report_date`, `period_start`, `period_end`: market date
- `portfolio_snapshot`: structured context including `market.code`, indexes, sectors, gainers, flow, volume baselines, source status, and generated timestamps
- `summary`: rendered Markdown
- `source_status`: structured provider/degraded status
- `story`: narrative and scheduler metadata

Repository helpers find existing rows by `report_type = daily_market_brief`, `report_date`, and `portfolio_snapshot->'market'->>'code'`. When the legacy `report_key` column exists, daily brief keys include market: `daily_market_brief:<market>:<date>:<date>`. Reruns update the existing market/date row instead of creating another confusing report, while CN/HK/US briefs for the same date can coexist.

## Provider Strategy

P0 does not add a paid provider dependency.

- Core indexes: use existing Yahoo chart fallback through `market_data_provider.get_yahoo_market_bars` for supported P0 index symbols.
- Sectors/industries and top gainers: no reliable full-market common-equity universe exists in the current repo. Default live generation records these as `provider_unavailable` degraded states instead of inventing rankings.
- Capital flow: no configured no-paid provider currently exposes explicit market/stock/sector flow metrics for all three markets. Default live generation records explicit degraded states; fixtures may provide CN/HK flow-like rows only for deterministic tests.
- Verification fixtures: deterministic in-process fixture data covers indexes, sectors/industries, gainers, and supported flow rows when explicitly requested. Fixture output is labeled `fixture` and is not presented as real market data.

## Command Surface

Supported P0 command intents:

- Show latest: `每日市场简报 CN`, `最新每日市场简报 HK`, `daily market brief US`
- Show specific date: `每日市场简报 CN 2026-06-30`
- Manual generate/rerun: `生成每日市场简报 CN 2026-06-30`, `重跑每日市场简报 US 2026-06-30`
- Fixture generation for local verification only: append `fixture` or `测试夹具` to a generation command.

The command path returns saved Markdown and does not start HTTP services.

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
- Optional local command smoke with fixture generation if a database is available.

## Implementation Traceability

| PRD scope / acceptance criterion | Status | Evidence | Notes |
|---|---|---|---|
| CN brief includes required P0 indexes, sectors/industries, gainers, flow/degraded state, volume baselines, source labels, date, timestamp | verified | `investment_knowledge_mcp/daily_market_brief.py`; `.venv/bin/python -m unittest tests.test_daily_market_brief`; `env POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 CN 2026-06-30 fixture` | CN fixture verifies full rendered shape and idempotent persistence through the real CLI path. Live sectors/gainers/flow degrade until a configured full-market provider exists. |
| HK brief includes required P0 indexes, sectors/industries when supported, gainers, flow/degraded state, turnover baselines | verified | `env POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 HK 2026-06-30 fixture`; `每日市场简报 HK 2026-06-30` | HK fixture generated all required indexes and saved alongside CN for the same date without `report_key` collision. |
| US brief includes required P0 indexes, sectors/industries when supported, common-stock gainers, explicit flow degraded state, volume baselines | verified | `tests/test_daily_market_brief.py::test_live_us_defaults_to_explicit_capital_flow_degraded_state`; `env POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py 生成每日市场简报 US 2026-06-30 fixture` | US flow defaults to unsupported per PRD with product-language copy; sectors/gainers degrade without a configured full-market provider. |
| Independent market scheduler and rerun semantics | verified | `run_daily_market_brief_scheduler_forever`, `run_daily_market_brief_once`; scheduler timezone unit test | Scheduler is ready as a module entrypoint; cloud service wiring is out of P0. |
| Idempotent storage by report type, market, market date | verified | `repository.upsert_daily_market_brief_report`; `db/schema.sql`; local DB metadata check on `POSTGRES_PORT=55433` | Daily brief `report_key` is market-aware when the legacy column exists; local rows verified as `daily_market_brief:CN/HK/US:<date>:<date>`. |
| Missing provider coverage visible in user language | verified | Renderer and degraded-state unit test; non-fixture CLI smoke for `US 2026-06-29` | Source status uses product-language labels and sanitized degraded copy; raw Yahoo fallback/SSL/provider exceptions are not rendered. |
| Command surface retrieves latest and specified market/date | verified | `command_router.py`; command retrieval unit test; `scripts/ikg.py` latest/specific checks on `POSTGRES_PORT=55433` | HTTP command API is not required for local verification. |
| Stored report includes structured context and source status | verified | `repository.upsert_daily_market_brief_report`; `env POSTGRES_PORT=55433 .venv/bin/python scripts/ikg.py ...` | Context is stored in `portfolio_snapshot`; status in `source_status`; local DB smoke passed against the existing project PostgreSQL on `localhost:55433`. |
| Narrative is understandable and has no buy/sell recommendations | verified | Markdown assertions in `tests/test_daily_market_brief.py` | Renderer describes market breadth/leadership/liquidity/data gaps only. |
| Holiday/no-session runs produce explicit skipped/no-session state | verified | Weekend no-session unit test | Full holiday calendars remain a future provider enhancement. |
| Independent acceptance testing before user acceptance | in_progress | `AT-2026-06-30-002` moved to `needs_retest` after developer verification | Acceptance Testing should rerun the command surface on this branch or after coordinator integration; user acceptance remains pending. |

## Risks And Blockers

- Current repo has no full-market sector/industry and common-equity ranking provider. P0 will not invent this data in live mode; it records degraded state and uses fixtures for deterministic verification.
- Full exchange holiday detection is unavailable locally. Weekend no-session is implemented; exchange-holiday calendars are a future provider/data-source task.
- Cloud deployment is out of this handoff unless the coordinator explicitly approves it.
