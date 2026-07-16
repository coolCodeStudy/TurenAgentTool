# Daily Market Brief Cross-Market Gainer Eligibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict CN, HK, and US top-gainer lists to liquid ordinary shares above market-specific minimum market capitalizations without imposing a percentage-gain cap.

**Architecture:** Keep the existing provider and report pipeline, but normalize market capitalization at provider boundaries and enforce one shared eligibility rule before ranking. Apply the same helper to the current spot universe used by historical reconstruction, then expose the threshold in stored rows, metric labels, and source status.

**Tech Stack:** Python 3, unittest, AKShare/Eastmoney/Sina provider adapters, PostgreSQL-backed report persistence.

## Global Constraints

- CN minimum market cap: CNY 3,500,000,000.
- HK minimum market cap: HKD 4,000,000,000.
- US minimum market cap: USD 500,000,000.
- Keep existing CN/HK/US turnover thresholds.
- Do not cap or clamp percentage gains.
- Missing or malformed market cap makes a row ineligible.
- Historical price change and turnover remain exact-date values; historical candidate market cap comes from the current spot snapshot and must be labeled as such.

---

### Task 1: Live Provider Eligibility

**Files:**
- Modify: `tests/test_daily_market_brief.py`
- Modify: `investment_knowledge_mcp/daily_market_brief.py`

**Interfaces:**
- Consumes: provider rows accepted by `_akshare_stock_gainers(frame, market, min_turnover)`.
- Produces: `MARKET_CAP_THRESHOLDS`, `_eligible_common_equity(...)`, and gainer rows containing `market_cap`.

- [ ] Add failing tests with above-threshold ordinary shares, below-threshold shares, missing-market-cap shares, ETF/leveraged products, and an above-100% qualifying ordinary share for CN/HK/US.
- [ ] Run `.venv/bin/python -m unittest tests.test_daily_market_brief.DailyMarketBriefTests.test_akshare_gainers_require_common_equity_and_market_cap tests.test_daily_market_brief.DailyMarketBriefTests.test_direct_eastmoney_hk_us_gainers_keep_liquid_common_equities tests.test_daily_market_brief.DailyMarketBriefTests.test_sina_hk_us_rows_are_normalized_and_filtered` and confirm failures are caused by absent market-cap enforcement.
- [ ] Add market-cap constants and shared security eligibility logic; keep CN `ST`/delisting behavior and reject ETF/ETN/fund/leveraged/inverse/warrant/right/unit/preferred markers conservatively.
- [ ] Read `Total Market Value`/`Market Cap` aliases, persist `market_cap`, and include both turnover and market-cap thresholds in `metric`.
- [ ] Request Eastmoney `f20` for CN/HK/US and map Sina `mktcap` where provided.
- [ ] Re-run the focused tests and confirm all pass.

### Task 2: Historical Candidate Eligibility

**Files:**
- Modify: `tests/test_daily_market_history.py`
- Modify: `investment_knowledge_mcp/daily_market_history.py`

**Interfaces:**
- Consumes: current spot-universe rows from AKShare and market-specific thresholds.
- Produces: historical candidate rows carrying `current_market_cap`, filtered by the same ordinary-share and market-cap rules.

- [ ] Add failing tests proving each market excludes missing/below-threshold market caps, rejects non-common securities, and retains a qualifying ordinary share whose exact-date gain exceeds 100%.
- [ ] Run the new historical tests and confirm they fail because `_load_universe` does not enforce market cap.
- [ ] Add market-cap thresholds and shared-equivalent historical eligibility, carry `current_market_cap` into persisted historical rows, and change `universe_basis`/message/metric to identify the generation-time market-cap filter.
- [ ] Re-run `tests.test_daily_market_history` and confirm all tests pass.

### Task 3: Documentation, State, And Verification

**Files:**
- Modify: `docs/techplans/daily-market-brief.md`
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`

**Interfaces:**
- Consumes: verified implementation and test evidence.
- Produces: auditable delivery state and deploy/retest ownership.

- [ ] Update the technical plan provider strategy and traceability with the three market-cap thresholds and current-snapshot historical limitation.
- [ ] Record the implementation/retest dispatch and acceptance item without marking user acceptance accepted.
- [ ] Run `.venv/bin/python -m unittest tests.test_daily_market_brief tests.test_daily_market_history`.
- [ ] Run `.venv/bin/python -m py_compile investment_knowledge_mcp/daily_market_brief.py investment_knowledge_mcp/daily_market_history.py`.
- [ ] Run `git diff --check` and `python3 scripts/audit_delivery_state.py --feature "Daily market brief"`.
- [ ] Commit the verified implementation and state updates, push the task branch, integrate through the approved repository flow, deploy the affected Web/scheduler/history-worker services, regenerate affected reports, and verify the public page/API.
