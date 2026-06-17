# Weekly Review Week Scope And Force Refresh Tech Plan

## Goal

Make the weekly review workbench a simple natural-week workflow:

1. Read the selected week first.
2. If a report exists and the request is not force refresh, return it.
3. If no report exists, Generate creates and saves the weekly report.
4. Force refresh reruns the pipeline, overwrites the same weekly report, and returns it.
5. Save finalized report writes the currently edited content back to the same weekly report.

There is no weekly report status machine. No `draft`, `finalized`, or `refresh_draft` rows are created for the same week.

## Product Contract

Use one natural week as the review unit:

```text
Monday through Sunday
```

The browser may submit `YYYY-Www`, `week_start`, or a generic date. The backend normalizes it to:

```text
week_start = Monday
week_end = week_start + 6 days
```

Default behavior:

| Scenario | Behavior |
| --- | --- |
| Open current week | Query `review_reports`; return the existing report or `missing`. |
| Open historical week | Query only; do not regenerate. |
| Generate missing week | Run the weekly review pipeline and save one weekly report row. |
| Generate existing week | Return the existing report with `already_exists=true`; do not rerun. |
| Force refresh any week | Require `force=true`, rerun the pipeline, overwrite the same weekly report row, and return it. |
| Save finalized report | Save submitted Markdown/context to the same weekly report row; do not refetch or regenerate. |

## Data Model

The implementation keeps the existing `review_reports` table as the single weekly report row and adds report metadata that is useful without changing product behavior:

```text
generated_at
refreshed_at
token_usage
budget_warnings
```

The migration must not delete existing weekly reports. A page read calls schema setup, so destructive cleanup in schema would erase product data during normal use.

```text
No DELETE FROM review_reports in schema migration.
```

Application code queries the selected week first:

```text
report_type = 'weekly'
period_start = selected Monday
period_end = selected Sunday
```

If a row exists, update it. Otherwise insert one row. If duplicates somehow exist from earlier test data, the implementation picks the latest `id` and updates that row.

P1 adds operational records without changing the one-report-row product contract:

```text
weekly_review_runs
weekly_review_sources
```

`weekly_review_runs` records generation and force-refresh attempts, their result status, token usage, source summary, and budget-warning metadata.

`weekly_review_sources` caches provider payloads by week, source type, and source key. Force refresh bypasses the cache and overwrites provider records for the selected week.

## API

`GET /api/weekly-review?week=2026-W25`

Read-only. It must not call data providers or LLMs.

`POST /api/weekly-review/generate`

Runs generation only when no report exists for the week. Existing content is returned with `already_exists=true`.

`POST /api/weekly-review/refresh`

Requires `force=true`. Reruns the pipeline and overwrites the same weekly report row. It does not create a separate refresh draft and there is no compare view.

`POST /api/weekly-review/save`

Saves submitted Markdown using the submitted context or the existing report context. It must not call `build_weekly_review(...)`.

## Token And Cost Policy

The workbench records token usage but does not enforce a hard budget.

- Opening an existing week: `0` tokens.
- Viewing a historical week: `0` tokens.
- Saving the current report: `0` tokens.
- First generation or force refresh: may use tokens if story generation is enabled.
- When tokens are used, save provider/model/token/cost metadata into `review_reports.token_usage` and `weekly_review_runs.token_usage`.
- Optional warning thresholds can add metadata to `budget_warnings`; they do not block generation.

If exact price calculation is unavailable, store token counts and leave cost blank. Do not invent costs.

## Scope

Implemented together:

1. Week selector UI instead of arbitrary start/end date inputs.
2. Read-only page load.
3. Generate missing report.
4. Generate existing report returns existing content without rerun.
5. Force refresh overwrites the same weekly report row.
6. Save without hidden regeneration.
7. Token usage persistence without budget enforcement.
8. Default index provider through Futu OpenD `request_history_kline`, using the accepted first basket: Nasdaq 100, S&P 500, Dow Jones, Hang Seng Index, Hang Seng Tech, CSI 300, ChiNext Index, and STAR 50.
9. JSON file, environment JSON, or configured JSON URL overrides for external sources, used for tests, manual imports, or fallback data only; users should not need to configure these for default index data.
10. Provider cache records in `weekly_review_sources`.
11. Generation and force-refresh run records in `weekly_review_runs`.
12. Token spend summary returned by the workbench API.
13. Budget warning metadata stored on reports and runs when configured thresholds are exceeded.

## Main Concerns

- Snapshot gaps can make weekly attribution approximate; the UI must keep source status visible.
- Realtime holdings are current state, not historical evidence.
- News, macro, and theme sources are high-noise and stay out of read-only page load; they are fetched only during generation or force refresh.
- Save must never regenerate context; otherwise the cost-control promise is broken even if the UI looks correct.
