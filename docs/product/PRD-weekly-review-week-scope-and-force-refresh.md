# PRD: Weekly Review Week Scope And Force Refresh

> Status note (2026-06-18): This PRD is kept as historical product context. The accepted current behavior is simpler than several sections below: weekly review stores one report row per natural week; `Force refresh` requires explicit confirmation and then overwrites that same weekly report; there is no `refresh_draft`, compare view, or DB status machine. The current implementation contract is documented in `docs/techplans/weekly-review-week-scope-force-refresh.md`.

## 1. Background

The first version of the weekly review web workbench allows users to generate a review from arbitrary `start/end` dates. That is cheap while the product only uses trades and position snapshots, but it becomes expensive and inconsistent once the product adds indexes, macro calendars, news themes, opportunity lists, and LLM-generated story candidates.

Arbitrary ranges create three problems:

- A user can query ranges such as `6.13-6.17` and `6.13-6.20`, repeatedly triggering data fetches, news searches, and model generation.
- Arbitrary ranges break the product definition of a weekly review, making reports hard to compare across weeks.
- Users may refresh accidentally and burn token budget, external API quota, and time without realizing it.

The weekly review should therefore move from an arbitrary date-range query tool to a fixed-week workbench: generate once, read many times, and run the full pipeline only when the user explicitly requests a force refresh.

## 2. Product Goals

1. A weekly review can only be generated for a fixed week.
2. The same week is generated once by default; later visits read the existing report or draft.
3. The user can explicitly click `Force refresh` to run the full data fetch and story-generation pipeline again.
4. Force refresh must protect user-edited or finalized reports and must never silently overwrite them.
5. The page must clearly show whether the current content is missing, cached, a draft, a finalized report, or a refreshed draft.

## 3. Non-Goals

- Do not support arbitrary free-form date ranges.
- Do not turn the weekly review into a real-time news feed.
- Do not fetch news or spend LLM tokens every time the page opens.
- Do not overwrite a finalized report without explicit user confirmation.

## 4. Week Definition

Use natural weeks by default:

```text
Monday 00:00:00 through Sunday 23:59:59
```

The page and API should use `week_start` as the primary input. `week_start` must be a Monday.

Display format:

```text
2026-W25
2026-06-15 to 2026-06-21
```

If a user chooses any date from a date picker, the system normalizes that date to its natural week. The product does not preserve arbitrary `start/end` values.

## 5. User Stories

### 5.1 Open This Week's Review

As a user, when I open the page, I want to see the current natural week's review state:

- If the week has not been generated, show `Missing` and the primary button `Generate weekly review`.
- If a draft exists, show the draft and data-source status.
- If a finalized report exists, show the finalized report and make any new edits explicit.

### 5.2 View A Historical Week

As a user, when I select `2026-W24`, I want to see the existing review for that week instead of rerunning the pipeline.

### 5.3 Force Refresh

As a user, when I know source data has changed or I want to rerun macro/news/index inputs, I can click `Force refresh`.

The confirmation must say:

```text
This will refetch trades, positions, indexes, macro events, news/theme data, and opportunity lists, then regenerate the story draft.
It will not directly overwrite a finalized report.
```

### 5.4 Protect Finalized Reports

As a user, if I already finalized a report and then click `Force refresh`, the system should create a refreshed draft version so I can compare it before deciding whether to replace the finalized report.

## 6. Page Interaction

### 6.1 Top Controls

Replace `Start date / End date` with `Select week`.

Controls:

| Control | Description |
| --- | --- |
| Previous week | Switch to the previous natural week. |
| This week | Switch to the current natural week. |
| Next week | Allow viewing a future week, but do not generate trading review content by default. |
| Week selector | Accept `YYYY-Www` or any date, then normalize to Monday. |
| Generate weekly review | Show only when no report or draft exists for the week. |
| Force refresh | Show when a report or draft exists; requires confirmation. |
| Save finalized report | Save the current draft as the finalized weekly review. |

### 6.2 Status Bar

The status bar must show:

```text
Review week: 2026-W25
Report status: Missing / Draft / Finalized / Refreshed draft / Stale
Generated at: 2026-06-21 22:15
Last refreshed: 2026-06-22 08:30
Sources: Trades, positions, indexes, macro, news, opportunity lists
LLM: Not used / Story candidates generated
```

### 6.3 Force Refresh Confirmation

Dialog copy:

```text
Force refresh 2026-W25?

The system will rerun the full pipeline:
- Backfill trades and position snapshots
- Fetch index data
- Fetch macro calendar events
- Fetch news/theme heat
- Fetch opportunity lists
- Regenerate the overall story draft

If a finalized report already exists, this result will be saved as a refreshed draft and will not directly overwrite the finalized report.
```

Buttons:

```text
Cancel
Confirm force refresh
```

## 7. Backend Behavior

### 7.1 Normal Read

Request:

```text
GET /api/weekly-review?week=2026-W25
```

Flow:

1. Parse `week` into `week_start/week_end`.
2. Query `review_reports` for an existing report for that week.
3. If one exists, return it without triggering external providers or LLM generation.
4. If none exists, return `status=missing` so the frontend can show `Generate weekly review`.

### 7.2 First Generation

Request:

```text
POST /api/weekly-review/generate
{
  "week": "2026-W25"
}
```

Flow:

1. If a draft or finalized report already exists for the week, return the existing content by default.
2. If no report exists, run the full generation pipeline.
3. Save the result as `draft`.
4. Return the draft, source status, and estimated generation cost.

### 7.3 Force Refresh

Request:

```text
POST /api/weekly-review/refresh
{
  "week": "2026-W25",
  "force": true
}
```

Flow:

1. Bypass the weekly report cache.
2. Pass `refresh=true` to external sources.
3. Run the full pipeline again.
4. If no finalized report exists, overwrite or update the current automatic draft.
5. If a finalized report exists, create a `refresh_draft` and do not overwrite the finalized report.
6. Record refresh reason, refresh time, and source payload versions.

## 8. Data Model Recommendations

### 8.1 `review_reports`

Recommended fields:

```text
report_type      weekly
period_start     Monday date
period_end       Sunday date
status           draft / finalized / refresh_draft / archived
version          Version number within the same week
generated_at
refreshed_at
finalized_at
generation_mode  initial / force_refresh / manual_edit
token_usage      JSONB
source_status    JSONB
portfolio_snapshot JSONB
summary          Markdown
```

Recommended uniqueness:

```text
UNIQUE(report_type, period_start, status)
```

For a stricter model, split versions into a separate table so there can be only one finalized report per week.

### 8.2 `weekly_review_sources`

New cache table:

```text
week_start
week_end
source_type      trades / positions / indexes / macro / news / opportunities
source_key       Provider name or query key
payload          JSONB
fetched_at
expires_at
refresh_run_id
error
```

Uses:

- Avoid refetching external data when the same week is opened repeatedly.
- Create a new `refresh_run_id` during force refresh.
- Make the overall story traceable to concrete source payloads.

### 8.3 `weekly_review_runs`

Record each generation or refresh run:

```text
id
week_start
mode             initial / force_refresh
status           running / succeeded / failed
started_at
finished_at
duration_ms
token_usage
source_counts
error
```

## 9. Generation Flow

Full pipeline:

```text
1. Parse week
2. Read or backfill trades
3. Read or backfill account and position snapshots
4. Fetch index data
5. Fetch macro calendar events
6. Fetch market-theme news and theme heat
7. Fetch opportunity lists
8. Build the fact board
9. Generate overall story candidates
10. Render the Markdown draft
11. Save draft or refresh_draft
```

Opening the page normally only does:

```text
1. Parse week
2. Read existing report
3. Return
```

## 10. Cost Control

Default behavior:

| Scenario | Fetch external data | Call LLM |
| --- | --- | --- |
| Open existing weekly review | No | No |
| Generate the week for the first time | Yes | Depends on configuration |
| Save finalized report | No | No |
| Force refresh | Yes | Yes |
| View historical week | No | No |

Force refresh should record cost:

```json
{
  "input_tokens": 12000,
  "output_tokens": 1800,
  "provider": "openai",
  "model": "...",
  "source_fetch_seconds": 18,
  "llm_seconds": 24
}
```

## 11. Acceptance Criteria

1. The page no longer exposes arbitrary `start/end` date inputs.
2. When the user selects any date, the system normalizes it to the natural week.
3. Opening an already-generated weekly review does not trigger external providers.
4. The `Force refresh` button requires confirmation.
5. Force refresh reruns the full pipeline.
6. A finalized report is never silently overwritten by force refresh.
7. Every report version for a week is traceable to its source payloads and generation run.
8. The UI clearly shows report status, generated time, refreshed time, and source status.

## 12. Implementation Priority

### P0

- Change the web page from date range selection to week selection.
- Add unified backend week parsing.
- Read an existing report by default when one exists for the same week.
- Add `Force refresh` button and confirmation dialog.
- Save force-refresh output as `draft` or `refresh_draft`.

### P1

- Add `weekly_review_runs`.
- Add `weekly_review_sources`.
- Add index provider integration.
- Show cache/refresh state in source status.

### P2

- Add macro calendar provider.
- Add market theme provider.
- Add opportunity list provider.
- Show token/time cost.

### P3

- Add draft version comparison.
- Add finalized report replacement approval.
- Close the loop for accepting, rejecting, and converting story candidates into user insights.
