# Weekly Trade Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent future intraday execution loss, repair recent partial weeks, and ensure regenerated Weekly Reviews reconcile their selected trade range.

**Architecture:** `scheduler_jobs` controls poll cadence; `account_snapshots` performs bounded broker reads and idempotent upserts; `weekly_review` performs an explicit selected-range reconciliation only during protected build/refresh. Public read remains a database read.

**Tech Stack:** Python 3, unittest/mock, existing Futu provider and PostgreSQL repository.

## Global Constraints

- Never read, log, or expose broker, access-token, or account credential values.
- Store completed executions only as returned by Futu's deal-history API; do not synthesize orders.
- Preserve `public_read_protected_write` and Daily Market Brief tokenlessness.
- Release through one serialized `targeted_quick` deployment. The current classifier selects `dingtalk-api`, `dingtalk-stream-bot`, `mcp`, `scheduler-host`, and `weekly-review-web` because `weekly_review.py` is shared command logic.

### Task 1: Capture intraday executions and a bounded repair window

**Files:**
- Modify: `tests/test_scheduler_jobs.py`
- Modify: `tests/test_account_snapshots.py`
- Modify: `investment_knowledge_mcp/scheduler_jobs.py`
- Modify: `investment_knowledge_mcp/account_snapshots.py`

- [ ] Write failing tests proving a successful 00:05 snapshot does not suppress a 12:00 current-day poll, and that only the first poll uses a 14-day reconciliation start.
- [ ] Run the focused tests and verify they fail against the once-per-day callback.
- [ ] Add an explicit `trade_start` range to the snapshot operation; make the scheduler use a trailing 14-day range once per day and the current date at later intervals.
- [ ] Run the focused scheduler and account-snapshot tests until green.

### Task 2: Reconcile generated Weekly Reviews rather than trusting a non-empty cache

**Files:**
- Modify: `tests/test_weekly_review.py`
- Modify: `investment_knowledge_mcp/weekly_review.py`

- [ ] Write a failing test where one cached execution and multiple broker executions produce a complete merged trade set.
- [ ] Run the focused test and verify it fails because the current loader returns early.
- [ ] Reconcile the selected range during generation, upsert idempotently, then read the canonical stored set. Preserve cached rows with a warning if Futu is unavailable.
- [ ] Run focused Weekly Review tests until green.

### Task 3: Release and validate the corrected historical week

**Files:**
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`

- [ ] Run focused and relevant full Python regressions plus `git diff --check`.
- [ ] Commit, push, integrate the verified ref to authoritative `main`, and record a targeted quick Deploy Intent for the classifier-selected service set.
- [ ] Let the single serialized deployment complete; verify stable health, trigger or observe the bounded repair, then confirm the 2026-07-13 report has the expected completed US and HK executions.
- [ ] Run local Playwright against the deployed public URL, update durable state, and leave the feature ready for user acceptance only with evidence.
