# Stock Valuation P0.1: Valuation Conclusion Plan

> **Execution mode:** The Feature Coordinator executes this bounded plan in the existing isolated worktree, with test-first changes and a whole-branch return gate before release.

**Linked PRD:** [`PRD-Stock-Valuation-Research.md`](../../product/PRD-Stock-Valuation-Research.md)

**Design:** [`2026-07-23-valuation-conclusion-and-sourced-range-design.md`](../specs/2026-07-23-valuation-conclusion-and-sourced-range-design.md)

**Goal:** Make every Stock Valuation card answer what the market currently prices and whether a source-validated fair-value range exists, without fabricating a target price.

## Constraints

- Preserve `stock_valuation_packet.v1` and `stock_valuation_evidence.v1` exactly; P0.1 is a rendering-only additive behavior.
- Do not add a provider, database migration, secret, paid account, service, ingress, Compose, or public-port change.
- Do not let Codex research text, social-media content, or default financial assumptions become valuation facts.
- Preserve Chinese-first output and the byte-identical canonical English original.
- Never alter the existing protected acceptance blocker or mark user acceptance accepted.

## Task 1: Product and Delivery Contract

**Files:** `docs/product/PRD-Stock-Valuation-Research.md`, `docs/techplans/stock-valuation-research.md`, `docs/project-management/Delivery-Queue.md`.

1. Record the distinction between current market valuation and a defensible fair-value range.
2. Link the design and this plan from the durable PRD/technical plan.
3. Record an active coordinator-owned Development return with the existing acceptance item and protected-fixture blocker preserved.

## Task 2: Red Tests for Honest Conclusion and Identifier Safety

**Files:** `tests/test_stock_valuation.py`.

1. Add a failing card test for market price, market capitalization, enterprise value, fair-value unavailable status, and the precise missing evidence categories.
2. Add a failing translation regression using `fact:operating_cash_flow`, `free_cash_flow`, and `market_snapshot` to prove canonical IDs do not change.
3. Run the focused test class and record the expected RED result before implementation.

## Task 3: Deterministic Presentation Implementation

**Files:** `investment_knowledge_mcp/stock_valuation.py`.

1. Build the conclusion only from the existing validated public projection.
2. Render current-market facts when available; name unavailable market inputs otherwise.
3. Render a fair-value unavailable state with exactly the forward scenario, peer/method, and valuation-assumption gaps.
4. Replace unsafe global short-word translation with structured confidence/fit translation so canonical IDs remain verbatim.
5. Keep the English renderer as the single source for the appended original.

## Task 4: Verification and Return Gate

1. Run `tests.test_stock_valuation`, then the routed Workbench/gateway regressions.
2. Run `py_compile`, `git diff --check`, feature delivery audit, and flow-health audit.
3. Classify the immutable candidate ref. If executable changes select a release, use exactly one serialized shared quick deploy; do not alter weekly-review ingress or public-port wiring.
4. Smoke the deployed `/command` surface using public/tokenless recovery only, then route the same `AT-2026-07-19-001` for independent acceptance. Preserve the protected authenticated-success fixture blocker.

## Follow-Up: P0.2 Sourced Scenario Calculator

Create a new technical plan only after P0.1 ships. It will introduce a versioned scenario-input bundle, typed provenance validation, deterministic calculations, and a cloud-worker candidate collection contract. The cloud worker may gather candidates under an official-first source policy, but no source candidate is promoted to an input without validation. This remains separate because it depends on external-source verification, not because P0.1 implementation is deferred.
