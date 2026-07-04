# Stock Valuation Provider Packet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a P0.1 provider-backed valuation packet so cloud Stock valuation outputs have real market and financial facts for US stocks such as `US.INTC` instead of only degraded scaffolding.

**Architecture:** Keep the existing artifact-backed valuation flow. Add a small provider module that fetches SEC EDGAR company facts for US financial metrics and Yahoo quote summary for low-cost market snapshot fields, then merge those facts into the existing valuation packet before deterministic calculations run.

**Tech Stack:** Python standard library, `requests`, existing `investment_knowledge_mcp.stock_valuation`, existing Command Workbench command path, `unittest`.

---

### Task 1: Provider Snapshot Module

**Files:**
- Create: `investment_knowledge_mcp/valuation_data_provider.py`
- Modify: `tests/test_stock_valuation.py`

- [x] **Step 1: Write failing tests**

Add tests that monkeypatch provider HTTP responses and assert US provider facts include SEC-backed revenue/net income/cash-flow fields and Yahoo-backed market fields, and that provider failures return explicit errors without raising.

- [x] **Step 2: Verify tests fail**

Run: `python3 -m unittest tests.test_stock_valuation`
Expected: FAIL because `investment_knowledge_mcp.valuation_data_provider` does not exist.

- [x] **Step 3: Implement provider module**

Implement `fetch_provider_snapshot(symbol, market, timeout=8)` with:
- US-only SEC EDGAR CIK lookup plus companyfacts fetch.
- Recent annual/quarterly metric extraction for revenue, net income, operating cash flow, capex, cash, debt, shares outstanding where present.
- Yahoo quote summary/chart fallback for price, market cap, shares outstanding, currency, timestamp.
- Structured return: `facts`, `sources`, `errors`, `market_snapshot_status`, `financial_fact_status`.

- [x] **Step 4: Verify tests pass**

Run: `python3 -m unittest tests.test_stock_valuation`
Expected: PASS.

### Task 2: Valuation Packet Integration

**Files:**
- Modify: `investment_knowledge_mcp/stock_valuation.py`
- Modify: `investment_knowledge_mcp/command_router.py`
- Modify: `tests/test_stock_valuation.py`

- [x] **Step 1: Write failing tests**

Add tests showing `build_valuation_artifact(..., provider_snapshot=...)` merges provider facts into calculations and source coverage, while preserving degraded errors if provider data is partial.

- [x] **Step 2: Verify tests fail**

Run: `python3 -m unittest tests.test_stock_valuation`
Expected: FAIL because `provider_snapshot` is not accepted or merged.

- [x] **Step 3: Implement integration**

Update `build_valuation_artifact` to accept optional `provider_snapshot`; add provider facts to `_extract_facts`, provider sources to `_source_coverage`, provider errors to degraded reasons, and update assumptions to say P0.1 can use provider snapshots when available. Update `_handle_stock_valuation` to fetch the provider snapshot before building the artifact.

- [x] **Step 4: Verify tests pass**

Run: `python3 -m unittest tests.test_stock_valuation`
Expected: PASS.

### Task 3: Docs, Delivery State, And Verification

**Files:**
- Modify: `docs/product/PRD-Stock-Valuation-Research.md`
- Modify: `docs/techplans/stock-valuation-research.md`
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`

- [x] **Step 1: Update product/technical docs**

Record P0.1 provider-backed US valuation packet behavior, SEC/Yahoo source policy, degraded behavior, and cloud-IP retest requirement.

- [x] **Step 2: Update delivery state**

Mark Stock valuation user acceptance as `needs_reacceptance` or pending with a precise next action for provider-backed retest, and move `AT-2026-07-01-001` to `needs_retest` once implementation is ready for cloud retest.

- [x] **Step 3: Run verification**

Run:
- `python3 -m unittest tests.test_stock_valuation`
- `python3 -m py_compile investment_knowledge_mcp/stock_valuation.py investment_knowledge_mcp/command_router.py investment_knowledge_mcp/valuation_data_provider.py`
- `python3 scripts/audit_delivery_state.py --feature "Stock valuation research"`
- `git diff --check`

- [ ] **Step 4: Commit and push**

Commit all implementation, docs, and delivery-state updates, then push the coordinator branch.
