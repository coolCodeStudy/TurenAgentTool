# Weekly Review Source Details Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Weekly Review holdings show server-established weekly P&L, make every source-status card open an accessible, safe explanation drawer, and let the Trades drawer show the individual records already returned for the selected review week.

**Architecture:** Keep the change in the existing Python HTML renderer and its inline browser script. The drawer reads only `state.context.source_status` returned by the public Weekly-read API; no backend field, endpoint, access contract, or data mutation changes.

**Tech Stack:** Python 3 renderer tests, vanilla browser JavaScript/native `dialog`, Playwright Test.

## Global Constraints

- Use existing `weekly_pl_delta`; do not recompute P&L in JavaScript.
- Preserve `public_read_protected_write`, Daily tokenlessness, and all public URLs.
- Allowlist drawer fields; never render raw provider diagnostics, raw provider payloads, snapshots, or unknown source-status fields. The Trades drawer may render only the safe, already-public transaction fields defined in the design spec.
- Quality route is L3: focused checks, one serialized quick deployment, and local Playwright against the public URL.

---

### Task 1: Lock the renderer contracts with failing tests

**Files:**
- Modify: `tests/test_weekly_review_web_auth.py`
- Modify: `e2e/cloud-pages.spec.ts`

**Interfaces:**
- Consumes: `render_weekly_review_workbench_html()` and public `GET /api/weekly-review` fixture responses.
- Produces: regression coverage for weekly-P&L rendering and source detail dialog lifecycle.

- [ ] **Step 1: Add a failing renderer contract**

Add assertions that the rendered Weekly HTML contains `id="source-detail-dialog"`, `data-source-key`, `aria-haspopup="dialog"`, `本周盈亏`, `weekly_pl_delta`, and does not contain an authorization header in `renderStatus` or an extra source-detail endpoint.

- [ ] **Step 2: Run the focused renderer test and verify RED**

Run: `.venv/bin/python -m unittest tests.test_weekly_review_web_auth.WeeklyReviewWebAuthorizationTests.test_weekly_source_cards_have_safe_detail_dialog_contract -v`

Expected: fail because the current cards are non-interactive divs and no dialog exists.

- [ ] **Step 3: Add a failing browser journey**

Add a routed public Weekly fixture with a positive row, a negative row, and a legacy row lacking `weekly_pl_delta`; source status includes populated trades, partial indexes with coverage, and blocked events with a reason. Assert `本周盈亏`, signed formatted values, `—`, dialog contents, no second request, Escape/close focus restoration, and no raw provider diagnostic marker.

- [ ] **Step 4: Run the browser journey and verify RED**

Run: `npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public --grep "Weekly source detail drawer"`

Expected: fail because no source card opens a dialog and the holdings table has no weekly P&L column.

### Task 2: Implement the bounded weekly drawer and column

**Files:**
- Modify: `investment_knowledge_mcp/weekly_review_web.py`

**Interfaces:**
- Consumes: `state.context.source_status` and `state.holdings[*].weekly_pl_delta`.
- Produces: `renderSourceDetail`, `openSourceDetail`, and safe dialog lifecycle; existing `renderHoldings` gains the interval P&L column.

- [ ] **Step 1: Add the dialog shell and drawer styles**

Render one `dialog#source-detail-dialog` after the status grid with `aria-labelledby="source-detail-title"`, a close button, and `#source-detail-body`. Add desktop side-drawer CSS with visible focus, scrollable body, and no nested-card styling.

- [ ] **Step 2: Convert source cards to buttons**

In `renderStatus`, render `<button type="button" class="status" data-source-key="trades" aria-haspopup="dialog">` for each fixed source key. Preserve concise existing status text and use a fixed key-to-label map rather than dynamic object keys.

- [ ] **Step 3: Add allowlisted dialog rendering and lifecycle**

Implement a fixed `sourceDetailDefinition(key, item)` map with contribution copy and selected fields only: `status`, `count`, `providers`/`provider`/`sources`, `fetched_at`, cache indicators, `coverage`, `missing`, market/category gaps, and a sanitised user-facing reason. For `trades` only, render `state.context.trades.records` as an escaped fixed-column table of date, side, symbol/name, quantity, price, and amount. Ignore `provider_errors`, `failures`, unknown fields, arbitrary nested values, and raw transaction payload fields. On click or keyboard activation, set the title/body with escaped text, `showModal()`, and remember the invoking button. Close restores focus to that button.

- [ ] **Step 4: Render weekly P&L without false zeroes**

Extend the table header after `盈亏` with `本周盈亏`. Use a helper that treats only finite numeric `weekly_pl_delta` as a displayable monetary value; otherwise output `—`. Apply `moneyClass` only to displayable values.

- [ ] **Step 5: Run the focused Python and browser checks and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_weekly_review_web_auth tests.test_weekly_review_holder_attribution -q
npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public --grep "Weekly source detail drawer"
```

Expected: both commands pass; the browser fixture records exactly one Weekly-read request.

- [ ] **Step 6: Commit implementation and tests**

```bash
git add investment_knowledge_mcp/weekly_review_web.py tests/test_weekly_review_web_auth.py e2e/cloud-pages.spec.ts
git commit -m "feat: add Weekly source detail drawer"
```

### Task 3: Verify, deploy, and accept

**Files:**
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`

**Interfaces:**
- Consumes: immutable commit, GitHub serialized workflow, deployed public Weekly page.
- Produces: one L3 release-verification manifest and `ready_for_user_acceptance` only after cloud evidence passes.

- [ ] **Step 1: Run complete local regression and static checks**

Run:

```bash
git diff --check
.venv/bin/python -m unittest tests.test_weekly_review_web_auth tests.test_weekly_review_holder_attribution tests.test_web_experience -q
npm run test:e2e:cloud -- --project=desktop-public
```

Expected: no diff errors, all Python tests pass, and all desktop-public tests pass.

- [ ] **Step 2: Integrate the verified ref and record Deploy Intent**

Fast-forward the verified branch into authoritative `main`; record `targeted_quick`, service `weekly-review-web`, the public verification URL, and the coordinator watch path in Delivery Queue before waiting for the single automatic `deploy.yml` run.

- [ ] **Step 3: Verify the deployed public surface**

Run:

```bash
E2E_BASE_URL=http://47.84.190.191:8010 npm run test:e2e:cloud -- --project=desktop-public
```

Expected: all desktop-public tests pass against the public deployment, including the new drawer journey. Confirm the serialized workflow only recreates `weekly-review-web` and remains healthy for 30 seconds.

- [ ] **Step 4: Update durable state and commit it**

Record the exact deployed SHA, run/event, L3 evidence, and user-acceptance next step in the Registry, Acceptance Queue, and Delivery Queue. Run `python3 scripts/audit_delivery_state.py --feature "Frontend experience system"`, then commit and push the docs-only state update.
