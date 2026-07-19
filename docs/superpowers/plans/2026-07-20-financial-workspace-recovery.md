# Financial Workspace Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a recoverable Weekly Review flow, make Daily history tasks genuinely interactive, and apply one coherent financial desktop workspace visual system across Daily, Weekly, and Command.

**Architecture:** Keep the declared Python route owners and vanilla rendered JavaScript. Extend the existing `web_experience` access-session contract to Weekly's protected recovery action while retaining public GET reads. Centralize visual tokens in `web_experience`, then let each renderer consume the same rail, command-bar, status, table, and task-row contracts.

**Tech Stack:** Python 3.11 rendered HTML/JavaScript, unittest, Playwright Test, existing app gateway and access-session contract.

## Global Constraints

- Desktop only; preserve `/command`, `/weekly-review`, and `/daily-market-brief` URLs.
- Daily reads and page-created history task inspection remain tokenless; command/agent batch tasks remain private.
- Weekly GET reads remain public. Generate/Refresh sends the existing access-session Authorization header and never renders or logs a credential.
- Command protected behaviour, confirmation guard, and stored-access migration remain unchanged.
- Public E2E never creates reports; a protected CI test may use only `E2E_PROTECTED_ACCESS_TOKEN`.

---

### Task 1: Add Weekly Empty-State Recovery Without Changing Public Reads

**Files:**
- Modify: `investment_knowledge_mcp/web_experience.py`
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Modify: `tests/test_web_experience.py`
- Modify: `tests/test_weekly_review_web_auth.py`
- Modify: `e2e/cloud-pages.spec.ts`

**Interfaces:**
- Consumes: `window.InvestmentKnowledgeAccess.authorizationHeaders()` and `POST /api/weekly-review/generate`.
- Produces: `#weekly-recovery`, `#weekly-generate`, and `#weekly-access-panel`; default page read remains public `GET` only.

- [ ] **Step 1: Write the failing renderer tests**

```python
def test_weekly_missing_state_has_protected_recovery_not_blank_sections(self) -> None:
    html = render_weekly_review_workbench_html()
    self.assertIn('id="weekly-recovery"', html)
    self.assertIn('id="weekly-generate"', html)
    self.assertIn('id="weekly-access-panel"', html)
    self.assertIn('InvestmentKnowledgeAccess.authorizationHeaders()', html)

def test_weekly_public_read_contract_stays_tokenless(self) -> None:
    script = render_weekly_review_script()
    public_read = script.split('function loadReview', 1)[1].split('function generateReview', 1)[0]
    self.assertNotIn('Authorization', public_read)
```

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m unittest tests.test_web_experience tests.test_weekly_review_web_auth -v`

Expected: the recovery elements and `generateReview` boundary are absent.

- [ ] **Step 3: Implement the smallest shared recovery panel and Weekly flow**

Add `render_access_recovery_panel(...)` to `web_experience.py`; it emits a hidden labelled panel with password input, Continue, and Forget access controls. Include `render_access_session_script()` in Weekly. In `loadReview`, missing data reveals `#weekly-recovery` with non-error copy. `generateReview` makes exactly this protected request:

```javascript
const response = await fetch("/api/weekly-review/generate", {
  method: "POST",
  headers: { "Content-Type": "application/json", ...access.authorizationHeaders() },
  body: JSON.stringify({ week_start: state.weekStart }),
});
const payload = await response.json();
const recovery = access.classifyResponse(response.status, payload).status;
if (["access_required", "access_rejected", "access_not_configured"].includes(recovery)) {
  showWeeklyRecovery(recovery, payload.message || "Private access is required for generation.");
  return;
}
if (!response.ok || !payload.ok) throw new Error(payload.error || "Unable to generate the review.");
await loadReview();
```

- [ ] **Step 4: Verify GREEN and public recovery E2E**

Run: `.venv/bin/python -m unittest tests.test_web_experience tests.test_weekly_review_web_auth -v`

Add a public E2E missing-week test: click Generate/Refresh without a token and assert the visible recovery panel. Run: `E2E_BASE_URL=http://47.84.190.191:8010 npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public --grep "Weekly missing"`.

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/web_experience.py investment_knowledge_mcp/weekly_review_web.py tests/test_web_experience.py tests/test_weekly_review_web_auth.py e2e/cloud-pages.spec.ts
git commit -m "fix: recover empty weekly review"
```

### Task 2: Make Daily Page-Created History Tasks Selectable

**Files:**
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Modify: `tests/test_daily_market_brief.py`
- Modify: `e2e/cloud-pages.spec.ts`

**Interfaces:**
- Consumes: public `GET /api/daily-market-brief/history-jobs?id=<id>` and existing Daily read endpoint.
- Produces: buttons with `data-history-job-id`, selected detail, polling for active jobs, and no mutation on selection.

- [ ] **Step 1: Write the failing DOM/script tests**

```python
def test_recent_history_jobs_are_selectable_public_web_jobs(self) -> None:
    html = render_daily_market_brief_html()
    self.assertIn('data-history-job-id', html)
    self.assertIn('selectHistoryJob(jobId)', html)
    self.assertIn('历史生成队列（本页面任务）', html)

def test_completed_history_task_selection_reads_existing_brief(self) -> None:
    script = render_daily_market_brief_script()
    self.assertIn('async function selectHistoryJob(jobId)', script)
    self.assertIn('await loadBrief("read")', script)
    self.assertNotIn('fetch("/api/daily-market-brief/history-jobs", { method: "POST"', script)
```

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m unittest tests.test_daily_market_brief -v`

Expected: current recent rows are inert text without a selection function.

- [ ] **Step 3: Implement select-only task handling**

Render every public web job as `<button class="history-task" type="button" data-history-job-id="…">`. Attach one delegated listener to `#history-jobs`. The selection function must make only the existing detail GET; it polls queued/running jobs and, for completed/partial jobs, assigns the returned item market/date before reading the saved brief:

```javascript
async function selectHistoryJob(jobId) {
  const data = await fetchJson(`/api/daily-market-brief/history-jobs?id=${encodeURIComponent(jobId)}`);
  const job = data.job;
  renderHistoryJob(job);
  const item = (job.items || [])[0];
  if (["queued", "running"].includes(job.status)) return startHistoryJobPolling(job.id, item?.market_date || "");
  if (["completed", "partial"].includes(job.status) && item?.market && item?.market_date) {
    state.market = item.market;
    $("#market-date").value = item.market_date;
    await loadBrief("read");
  }
}
```

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/python -m unittest tests.test_daily_market_brief -v`

Add a safe browser/fixture test proving a task click uses detail/read requests only. Run: `npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public --grep "history task"`.

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/weekly_review_web.py tests/test_daily_market_brief.py e2e/cloud-pages.spec.ts
git commit -m "fix: make daily history tasks selectable"
```

### Task 3: Apply the Financial Research Workspace Visual System

**Files:**
- Modify: `investment_knowledge_mcp/web_experience.py`
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Modify: `investment_knowledge_mcp/command_workbench.py`
- Modify: `tests/test_web_experience.py`
- Modify: `tests/test_daily_market_brief.py`
- Modify: `tests/test_weekly_review_web_auth.py`
- Modify: `tests/test_command_workbench.py`
- Modify: `e2e/cloud-pages.spec.ts`

**Interfaces:**
- Consumes: `render_experience_css()` and `render_primary_navigation()`.
- Produces: `workspace-command-bar`, `workspace-section`, `history-task`, `status-success`, and a single shared navigation hierarchy.

- [ ] **Step 1: Write failing shared-style tests**

```python
def test_shared_workspace_css_exposes_financial_tokens(self) -> None:
    css = render_experience_css()
    for token in ("--experience-ink", "--experience-canvas", "--experience-positive", "--experience-warning"):
        self.assertIn(token, css)
    self.assertIn("font-variant-numeric: tabular-nums", css)

def test_daily_controls_use_contextual_command_bar(self) -> None:
    html = render_daily_market_brief_html()
    self.assertIn('class="workspace-command-bar"', html)
    self.assertNotIn('<aside class="sidebar">', html)
```

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m unittest tests.test_web_experience tests.test_daily_market_brief tests.test_weekly_review_web_auth tests.test_command_workbench -v`

Expected: independent inline tokens and Daily's duplicate sidebar fail the new contracts.

- [ ] **Step 3: Implement visual tokens and layout**

Put these stable contracts in `render_experience_css()`:

```css
:root { --experience-ink:#10243a; --experience-canvas:#eef2f6; --experience-surface:#fff;
  --experience-line:#d6dee8; --experience-accent:#2369a8; --experience-positive:#177245;
  --experience-warning:#a86600; --experience-danger:#b42318; }
.workspace-command-bar { display:flex; gap:12px; align-items:end; flex-wrap:wrap; padding:16px 18px;
  border:1px solid var(--experience-line); background:var(--experience-surface); }
.workspace-section { border-top:1px solid var(--experience-line); padding:22px 0; }
.financial-number { font-variant-numeric:tabular-nums; }
.history-task { width:100%; display:grid; grid-template-columns:minmax(0,1fr) auto; text-align:left; }
```

Remove Daily's duplicate sidebar and use an inline contents row. Make Weekly local contents compact. Keep Command's action catalog as its contextual aside. Use section dividers rather than nested-card surfaces; do not change routes or access behaviour.

- [ ] **Step 4: Verify renderer and cloud visual contracts**

Run: `.venv/bin/python -m unittest tests.test_web_experience tests.test_daily_market_brief tests.test_weekly_review_web_auth tests.test_command_workbench -v`

Run: `E2E_BASE_URL=http://47.84.190.191:8010 npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public`

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/web_experience.py investment_knowledge_mcp/weekly_review_web.py investment_knowledge_mcp/command_workbench.py tests e2e/cloud-pages.spec.ts
git commit -m "feat: establish financial research workspace"
```

### Task 4: Review, Deploy, and Retest

**Files:**
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`

- [ ] **Step 1: Run complete local evidence**

Run: `.venv/bin/python -m unittest tests.test_web_experience tests.test_daily_market_brief tests.test_weekly_review_web_auth tests.test_command_workbench -v`

Run: `npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public --list`

Run: `git diff --check`

- [ ] **Step 2: Integrate only reviewed code and record one deploy intent**

Classify changed files with `python3 scripts/classify_deploy_change.py <changed-files>`. Record ref, selected mode, targets, cloud URL, Playwright retest command, and this Coordinator as watch owner in `Delivery-Queue.md`.

- [ ] **Step 3: Use one serialized deployment and independent acceptance**

After 30-second stable target health, verify public Weekly recovery, Daily task selection, all three desktop pages, and `daily-market-brief-history-worker` from the approved Ops path. Run the public cloud Playwright suite. Run the protected success only if the secret-managed credential exists. Update durable state with actual evidence; do not create a history job merely to test it.

## Self-Review

- Task 1 covers the Weekly empty/read-only recovery gap; Task 2 makes the Daily public queue useful without exposing private jobs; Task 3 supplies the financial UI system; Task 4 owns deployment and acceptance.
- The plan has no `TBD`, `TODO`, or unspecified implementation placeholder.
- Existing interfaces are preserved: task selection uses `history-jobs?id=`, and Weekly mutations use the canonical access-session header.
