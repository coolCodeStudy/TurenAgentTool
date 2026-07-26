# Weekly Material Drag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent immaterial weekly losses from being presented as exceptional events while preserving material cross-currency risk signals.

**Architecture:** The Weekly domain builder owns materiality selection and continues to return the compatible `blowups` payload key. The Web and Markdown renderers only change the presentation contract to `显著拖累` and a precise no-material-drag state.

**Tech Stack:** Python 3, unittest, existing server-rendered HTML/JavaScript and local Playwright regression.

## Global Constraints

- Keep Weekly public reads tokenless and read-only; do not read, log, or expose credentials.
- Do not alter account snapshots, broker reconciliation, source data, or FX ranking rates.
- Use an absolute 50 USD-equivalent floor and a 1% opening-position impact gate when opening value is available.
- Release through the existing serialized deployment workflow; no ingress, Compose, port, or Daily/Command access changes.

### Task 1: Define material weekly-drag selection

**Files:**
- Modify: `tests/test_weekly_review_cross_currency_ranking.py`
- Modify: `investment_knowledge_mcp/weekly_review.py`

**Interfaces:**
- Produces: `_top_blowups(position_changes: list[dict[str, Any]]) -> list[dict[str, Any]]` returning only material loss rows.

- [ ] **Step 1: Write failing tests** for a small US loss and a small HK loss that must be excluded, a material cross-currency loss that remains eligible, and a qualifying loss with no opening value.
- [ ] **Step 2: Run the focused test module** and verify the old negative-only selection fails.
- [ ] **Step 3: Implement** `MIN_SIGNIFICANT_WEEKLY_DRAG_USD`, `MIN_SIGNIFICANT_WEEKLY_DRAG_RATIO`, and a narrow predicate used only by `_top_blowups`.
- [ ] **Step 4: Run the focused module** until all ranking and materiality tests pass.

### Task 2: Make the product language precise

**Files:**
- Modify: `tests/test_weekly_review_web_auth.py`
- Modify: `investment_knowledge_mcp/weekly_review.py`
- Modify: `investment_knowledge_mcp/weekly_review_web.py`

**Interfaces:**
- Consumes: an empty `context["blowups"]` from Task 1.
- Produces: `显著拖累` headings and the explicit no-material-drag copy in Markdown and Web output.

- [ ] **Step 1: Write failing renderer assertions** for the new heading and empty-state wording.
- [ ] **Step 2: Run the focused Web/Markdown assertions** and verify the old `炸裂时刻` contract fails them.
- [ ] **Step 3: Replace only presentation strings** while retaining the compatible API field name and rendered table accessibility contract.
- [ ] **Step 4: Run focused Weekly domain/Web tests** until green.

### Task 3: Release and verify the reported week

**Files:**
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`

- [ ] **Step 1: Run** focused Python tests, applicable local Playwright production tests, deploy-classification checks, and `git diff --check`.
- [ ] **Step 2: Commit, push, integrate** the exact reviewed ref into authoritative `main`, record one `targeted_quick` Deploy Intent, and watch the automatic serialized workflow.
- [ ] **Step 3: Verify** health and the tokenless 2026-07-20 public Weekly response has no immaterial rows in `blowups`; then rerun local Playwright against production.
- [ ] **Step 4: Record** state evidence and leave the feature `ready_for_user_acceptance` only after the deployed correction passes.

## Self-Review

- Spec coverage: Tasks 1 and 2 cover all five acceptance criteria; Task 3 covers deploy and production evidence.
- Placeholder scan: no deferred implementation placeholders.
- Type consistency: the existing `blowups` payload key is preserved across domain, API, and renderer layers.
