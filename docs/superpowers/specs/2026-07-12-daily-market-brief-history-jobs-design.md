# Daily Market Brief Historical Jobs Design

Status: approved
Owner: Daily Market Brief Feature Coordinator
Source PRD: `docs/product/PRD-Daily-Market-Brief.md`
Supersedes: `docs/superpowers/specs/2026-07-12-daily-market-brief-history-design.md`

## Decision

Historical reconstruction remains part of Daily Market Brief, but it runs as a
persistent background job rather than inside a long public HTTP request. This
keeps Web latency bounded, isolates provider work from the daily close
scheduler, supports restart-safe progress, and makes batch backfill natural.

The already implemented market-currency formatting, Chinese A-share index
names, saved-date listing, exact-date historical provider, and provider safety
tests remain valid and are reused by the worker.

## User Flows

### Single Missing Date

1. The user selects a market and an unsaved date on `/daily-market-brief`.
2. The page offers `生成历史简报` and creates one tokenless single-date job.
3. The API returns `202 Accepted` with a job ID immediately.
4. The page polls job status and shows queued/running/progress/partial/failed
   states without keeping the original request open.
5. When the worker saves the report, the page reads it through the existing
   report API and refreshes saved dates.

### Controlled Batch Backfill

The user or Coordinator can create a batch through the authenticated Command
Workbench or controlled Agent path:

```text
补齐每日市场简报 CN 2026-07-01 到 2026-07-10
补齐每日市场简报 CN,HK,US 最近20个交易日
```

The Daily Market Brief page displays batch progress and results but does not
expose tokenless batch creation. This prevents a public caller from scheduling
unbounded provider work while keeping ordinary reading and one-date recovery
easy for the user.

## Persistence

Use two dedicated tables rather than overloading research or coding jobs.

### `daily_market_brief_jobs`

- `id`
- `request_type`: `single` or `batch`
- `source`: `web`, `command`, `scheduler_recovery`, or `agent`
- `status`: `queued`, `running`, `completed`, `partial`, `failed`, or
  `cancelled`
- `force_refresh`
- aggregate total/completed/succeeded/skipped/failed counts
- current market/date
- sanitized summary and timestamps
- cancellation request and worker heartbeat

### `daily_market_brief_job_items`

- job ID, market, and market date
- item status: `queued`, `running`, `completed`, `skipped`, `failed`, or
  `cancelled`
- attempt count, saved report ID, sanitized error, timestamps
- unique market/date within a job

Job creation deduplicates an already active market/date item. Existing saved
reports are skipped unless a controlled caller explicitly requests refresh.

## Worker

Add a dedicated `daily-market-brief-history-worker` Compose service. It claims
one item at a time with `FOR UPDATE SKIP LOCKED`, updates heartbeat/progress,
calls the tested exact-date historical reconstruction, and commits each report
independently. The normal `daily-market-brief-scheduler` remains separate and
therefore cannot be delayed by a long backfill.

Worker constraints:

- one active market/date item globally;
- up to four fixed daemon workers inside the historical provider;
- at most two concurrent Eastmoney requests process-wide;
- up to ten minutes per market/date reconstruction;
- two bounded provider attempts per request category;
- cooperative cancellation between symbols and between items;
- stale `running` items are safely requeued after heartbeat expiry;
- a worker restart resumes queued/failed-retryable work and never creates a
  duplicate report because report persistence remains market/date idempotent.

There is no total wall-clock limit for a batch. A controlled batch may take
hours, but every item checkpoints progress and has its own bounded execution.

## Queue Limits

- Tokenless Web creation accepts exactly one market/date.
- A Web request cannot request force refresh.
- At most three Web-sourced jobs may be queued or running.
- A controlled batch may contain at most 120 market/date items; larger ranges
  must be split into multiple jobs.
- One active item means batch and single-date jobs cannot multiply provider
  concurrency.

## API And Page

Add:

- `POST /api/daily-market-brief/history-jobs` for one tokenless market/date;
- `GET /api/daily-market-brief/history-jobs?id=<id>` for sanitized job detail;
- `GET /api/daily-market-brief/history-jobs?limit=10` for recent progress;
- controlled command creation for batch ranges;
- controlled cancellation for queued/running jobs.

The page shows saved dates, missing dates, recent jobs, progress counts, current
market/date, completion state, and retryable failed dates. It never renders raw
provider exceptions, SQL, stack traces, or local paths.

## Reconstruction Semantics

- Every retained index and ranking row must match the requested market date.
- Current spot metadata may select the disclosed liquid top-200 candidate
  universe; spot change/turnover values never become historical values.
- Useful exact-date partial results may be saved with visible partial status.
- Empty provider timeout/failure does not save a misleading report.
- Historical weekday holidays and weekends produce explicit no-session state.
- HK/US historical sector and capital-flow gaps remain explicit.
- Amounts use readable CNY/HKD/USD units and CN index names remain Chinese.

## Deployment And Acceptance

The new table schema and worker service are runtime/config changes but do not
change image dependencies. The deploy classifier should choose a quick/config
restart path, include `weekly-review-web`, `daily-market-brief-scheduler`, and
`daily-market-brief-history-worker`, and never recreate PostgreSQL.

Cloud acceptance must enqueue CN `2026-07-09`, observe asynchronous progress,
read the saved report, confirm repeat reads and reruns preserve report identity,
and run a controlled multi-market batch. It must also verify job recovery,
queue limits, safe failure copy, current daily scheduler health, and that the
existing `2026-07-10` reports remain intact. User acceptance remains pending
until the user reviews the deployed page.
