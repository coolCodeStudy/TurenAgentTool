# Daily Market Brief Historical Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace synchronous public historical reconstruction with a persistent single-item worker queue that supports tokenless one-date jobs, controlled batch backfill, progress display, cancellation, and restart-safe persistence.

**Architecture:** Dedicated job/item tables provide durable queue state and `FOR UPDATE SKIP LOCKED` claims. A separate Compose worker invokes the already tested exact-date reconstruction domain with a ten-minute item budget; the Web page only enqueues and polls, while authenticated command routing creates bounded batches.

**Tech Stack:** Python 3.11, PostgreSQL/psycopg, standard-library HTTP server, Docker Compose, existing command router, AKShare historical provider, `unittest`.

## Global Constraints

- The public Web endpoint creates exactly one market/date job and returns immediately.
- Tokenless callers cannot create batch jobs or force refresh.
- Controlled batches contain at most 120 market/date items.
- One worker processes one item globally; provider internals retain four daemon workers and two Eastmoney calls.
- Each item has a ten-minute deadline; a batch has no total wall-clock limit.
- Every successful item checkpoints a report and job progress independently.
- Existing reports are skipped unless a controlled caller requests refresh.
- Exact-date, partial-data, no-session, currency, Chinese-name, idempotency, and safe-error semantics from the approved design remain binding.
- The normal close scheduler must not process historical job items.
- User acceptance remains pending until deployed user review.

---

### Task 1: Persistent Job And Item Repository

**Files:**
- Modify: `db/schema.sql`
- Create: `investment_knowledge_mcp/daily_market_jobs.py`
- Test: `tests/test_daily_market_jobs.py`

**Interfaces:**
- `create_history_job(markets: list[str], dates: list[date], *, request_type: str, source: str, force_refresh: bool = False, max_items: int = 120) -> dict[str, Any]`
- `get_history_job(job_id: int) -> dict[str, Any] | None`
- `list_history_jobs(limit: int = 10) -> list[dict[str, Any]]`
- `claim_next_history_item(worker_name: str) -> dict[str, Any] | None`
- `finish_history_item(item_id: int, *, status: str, report_id: int | None = None, error_summary: str | None = None) -> dict[str, Any]`
- `request_history_job_cancel(job_id: int) -> dict[str, Any] | None`
- `requeue_stale_history_items(stale_before: datetime) -> int`

- [ ] **Step 1: Write failing repository tests**

Test schema text and fake transactional behavior for: normalized markets; one item per market/date; 120-item rejection; active market/date deduplication; newest-first listing; one claimed item; `SKIP LOCKED`; aggregate progress; cancellation; stale-running recovery; sanitized errors; and existing-report skip metadata.

```python
def test_batch_rejects_more_than_120_market_dates(self) -> None:
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(41)]
    with self.assertRaisesRegex(ValueError, "最多 120"):
        jobs.create_history_job(["CN", "HK", "US"], dates, request_type="batch", source="command")
```

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m unittest tests.test_daily_market_jobs`

Expected: import failure for the missing module/table contract.

- [ ] **Step 3: Add schema and repository implementation**

Create `daily_market_brief_jobs` and `daily_market_brief_job_items` with explicit status checks, foreign key cascade, unique `(job_id, market, market_date)`, active-item indexes, heartbeat/cancel fields, counts, sanitized summary, and timestamps. Claims must use one transaction and `FOR UPDATE SKIP LOCKED`.

- [ ] **Step 4: Run GREEN and commit**

```bash
.venv/bin/python -m unittest tests.test_daily_market_jobs
git diff --check
git add db/schema.sql investment_knowledge_mcp/daily_market_jobs.py tests/test_daily_market_jobs.py
git commit -m "feat: persist daily brief history jobs"
```

### Task 2: Dedicated Historical Worker

**Files:**
- Create: `scripts/daily_market_brief_history_worker.py`
- Modify: `investment_knowledge_mcp/daily_market_jobs.py`
- Test: `tests/test_daily_market_history_worker.py`

**Interfaces:**
- `run_worker_once(*, worker_name: str, item_timeout_seconds: float = 600.0, now: datetime | None = None) -> dict[str, Any] | None`
- `run_worker_forever(*, poll_seconds: float = 5.0, stop_event: Event | None = None) -> None`

- [ ] **Step 1: Write failing worker tests**

Cover: claim one item; skip existing report without force; exact historical build and report ID; no-session completion; partial completion; safe failure; heartbeat; cancellation before build; cancellation between items; stale recovery; ten-minute timeout passed to provider; and job aggregate terminal status.

```python
def test_worker_saves_one_claimed_item_and_checkpoints(self) -> None:
    outcome = worker.run_worker_once(worker_name="fixture-worker", item_timeout_seconds=600)
    self.assertEqual("completed", outcome["status"])
    self.assertEqual(19, outcome["report_id"])
    self.assertEqual(1, fake_jobs.completed_count)
```

- [ ] **Step 2: Run RED, implement, run GREEN**

The worker calls `build_daily_market_brief(... historical_activity_provider=lambda market, day: load_historical_market_activity(market, day, timeout_seconds=600))`. It never handles current close scheduling. It catches raw exceptions, stores only `_public_history_job_error(...)`, and completes/cancels one item before claiming another.

- [ ] **Step 3: Commit**

```bash
.venv/bin/python -m unittest tests.test_daily_market_history_worker tests.test_daily_market_history tests.test_daily_market_brief
git add scripts/daily_market_brief_history_worker.py investment_knowledge_mcp/daily_market_jobs.py tests/test_daily_market_history_worker.py
git commit -m "feat: process historical daily brief jobs"
```

### Task 3: Tokenless Single-Date Queue And Progress Page

**Files:**
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Test: `tests/test_daily_market_brief.py`

**Interfaces:**
- `POST /api/daily-market-brief/history-jobs` body `{"market":"CN","date":"2026-07-09"}` returns HTTP 202 and job summary.
- `GET /api/daily-market-brief/history-jobs?id=123` returns sanitized detail and items.
- `GET /api/daily-market-brief/history-jobs?limit=10` returns recent jobs.

- [ ] **Step 1: Write failing API and page tests**

Cover: one-date only; future rejection; no force/batch fields; maximum three active Web jobs; active date dedup returns existing job; immediate 202 without calling historical build; job polling; saved report reload; failure copy; cancellation absent from tokenless controls; selected date preserved; progress counts and current item visible.

- [ ] **Step 2: Run RED and replace synchronous history execution**

Current-session generation remains synchronous. When the selected date is historical, the handler creates a job and returns 202; it must not acquire the old long-running historical lease or call `build_daily_market_brief` in the request thread. Remove superseded synchronous historical Web code and tests.

- [ ] **Step 3: Run GREEN and commit**

```bash
.venv/bin/python -m unittest tests.test_daily_market_brief tests.test_daily_market_jobs
git add investment_knowledge_mcp/weekly_review_web.py tests/test_daily_market_brief.py
git commit -m "feat: enqueue historical briefs from web"
```

### Task 4: Controlled Batch Commands And Cancellation

**Files:**
- Modify: `investment_knowledge_mcp/command_router.py`
- Test: `tests/test_daily_market_brief.py`
- Test: `tests/test_command_router.py`

**Interfaces:**
- `补齐每日市场简报 CN 2026-07-01 到 2026-07-10`
- `补齐每日市场简报 CN,HK,US 最近20个交易日`
- `取消每日市场简报任务 123`
- `每日市场简报任务 123`

- [ ] **Step 1: Write failing parser/command tests**

Assert normalized markets, inclusive date expansion, weekday filtering, recent-N expansion per market, 120-item cap, authenticated command-only routing, skip-existing default, explicit force only in controlled command, status rendering, sanitized failures, and cancellation.

- [ ] **Step 2: Run RED, implement handlers, run GREEN**

Use the job repository API rather than invoking historical providers. Render job ID, item count, skipped existing count, and page URL. Do not expose SQL/provider exceptions.

- [ ] **Step 3: Commit**

```bash
.venv/bin/python -m unittest tests.test_command_router tests.test_daily_market_brief tests.test_daily_market_jobs
git add investment_knowledge_mcp/command_router.py tests/test_command_router.py tests/test_daily_market_brief.py
git commit -m "feat: manage daily brief backfill jobs"
```

### Task 5: Service Wiring, Delivery State, Deploy, And Acceptance

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `scripts/deploy_contract.py`
- Modify: `scripts/deploy_release.py`
- Modify: `scripts/ecs_ops_api.py`
- Modify: `tests/test_deploy_change_classifier.py`
- Modify: `tests/test_deploy_release.py`
- Modify: `tests/test_ecs_ops_api.py`
- Modify: `docs/product/PRD-Daily-Market-Brief.md`
- Modify: `docs/techplans/daily-market-brief.md`
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`

- [ ] **Step 1: Add failing service/deploy tests**

Assert `daily-market-brief-history-worker` uses the application image, container PostgreSQL target, restart policy, health/running checks, deploy target mapping, and never recreates PostgreSQL.

- [ ] **Step 2: Wire service and update durable docs**

Update PRD/tech plan traceability with asynchronous single/batch behavior and provider limits. Mark acceptance `needs_retest`; user acceptance remains pending.

- [ ] **Step 3: Run full verification and review**

```bash
.venv/bin/python -m unittest tests.test_daily_market_jobs tests.test_daily_market_history_worker tests.test_daily_market_history tests.test_daily_market_brief tests.test_command_router
.venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/audit_delivery_state.py --feature "Daily market brief"
.venv/bin/python -m py_compile investment_knowledge_mcp/daily_market_jobs.py scripts/daily_market_brief_history_worker.py
git diff --check
```

- [ ] **Step 4: Merge and deploy through the classified shared path**

Deploy Intent: Daily Market Brief historical jobs; affected application targets `weekly-review-web`, `daily-market-brief-scheduler`, and `daily-market-brief-history-worker`; PostgreSQL schema initializes through the existing startup path but PostgreSQL is not recreated. Watch the deploy through stable health.

- [ ] **Step 5: Cloud acceptance**

1. Enqueue public CN `2026-07-09`; verify immediate 202 and page progress.
2. Wait for completion; verify saved report, Chinese indexes, CNY units, and exact-date provenance.
3. Re-enqueue the same date; verify dedup/same report identity.
4. Create a controlled CN/HK/US batch; verify item counts, progress, skip-existing, partial failures, and cancellation.
5. Restart/recover a worker item and verify checkpoint-safe resumption.
6. Verify current close scheduler and existing `2026-07-10` reports remain intact.
7. Run browser desktop/mobile checks and raw-error/advice scans.

- [ ] **Step 6: Close at ready for user acceptance**

Record independent acceptance evidence, push state-only `no_deploy` closure, and ask the user to review the production page without marking their acceptance automatically.
