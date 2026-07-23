# Weekly Trade Integrity Design

## Status

- Date: 2026-07-23
- Feature: Frontend experience system / Weekly Review data integrity
- Owner authorization: autonomous diagnosis, implementation, deployment, and acceptance preparation.

## Incident and Root Cause

The Weekly Review for 2026-07-13 to 2026-07-19 displayed two `US.DRAM` executions while the account history contains several completed US and HK executions on 2026-07-15 and 2026-07-16.

This is not a database deletion event. The scheduler invokes `run_account_snapshot_once` only once after its daily scheduled time. It normally succeeds near midnight, before the following trading session has produced executions, then deliberately skips all later intervals for that date. A Weekly Review builder also treats any non-empty local trade set as complete and skips broker reconciliation. A partial set can therefore become a permanently stale saved report.

The rejected 2026-07-16 deployments failed resource preflight before service activation and did not mutate the application or database. They are not the cause of the missing records.

## Decisions

1. The account snapshot scheduler will poll the current calendar date at its configured interval after the daily start time. Every poll upserts executions and the current account snapshot; it must not create duplicate trades.
2. The first successful poll of each date will reconcile a bounded trailing 14-day execution window. This repairs recent service outages, overnight timing gaps, and stale partial weeks without introducing an unbounded broker-history export.
3. A Weekly Review generation or forced refresh will reconcile the selected review range with Futu even if the database already contains rows. Public Weekly reads remain tokenless and read-only.
4. A failed reconciliation will leave previously stored records intact, report the failure through existing protected-generation recovery, and retry on the scheduler's next interval. It will never erase stored trades.
5. The release behavior changes `scheduler-host` and `weekly-review-web`. The existing deploy classifier also treats `weekly_review.py` as shared command logic, so its serialized `targeted_quick` release will recreate the established target set: `dingtalk-api`, `dingtalk-stream-bot`, `mcp`, `scheduler-host`, and `weekly-review-web`. Existing public URLs and access boundaries remain unchanged.

## Acceptance Criteria

1. A scheduler running at 00:05 and again at 12:00 calls the broker both times for the current date.
2. The first daily scheduler call reconciles the preceding 14 days; later same-day calls avoid re-reading that historical window.
3. A partial local selected-week trade set is reconciled with a broker snapshot before a regenerated Weekly Review is saved.
4. Reconciliation is idempotent and records a source status that distinguishes a broker refresh from a database-only read.
5. The production 2026-07-13 to 2026-07-19 report contains the completed 2026-07-15 and 2026-07-16 executions confirmed in the account history, including US and HK records, after the automated repair.
6. A public Weekly read remains tokenless and does not mutate broker or database state.

## Non-Goals

- Importing cancelled or rejected orders as executions.
- Arbitrary historical account exports, changing brokerage credentials, changing the Command access model, or a mobile redesign.
