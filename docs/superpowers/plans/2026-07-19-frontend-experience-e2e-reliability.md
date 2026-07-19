# Frontend Experience E2E Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the three desktop product pages visibly complete their primary actions and establish Playwright Test as the cloud acceptance gate.

**Architecture:** Keep Python renderers and APIs. Add a small versioned Playwright Test harness that targets the deployed cloud service with public and protected projects. First reproduce the browser/UI mismatch, then add bounded client recovery and simplify duplicated page chrome. Update the acceptance protocol so automated browser evidence is required after affected cloud deployments.

**Tech Stack:** Python 3.11 inline renderers, vanilla browser JavaScript, Node LTS, `@playwright/test`, GitHub Actions, existing unittest suite.

## Global Constraints

- Desktop Chromium only at 1440x1000; no mobile scope.
- Preserve `/command`, `/weekly-review`, `/daily-market-brief`, and `/` routes and their declared access classes.
- Do not generate cloud reports or execute write-like commands in E2E.
- Keep Daily Market Brief tokenless; do not store or report browser credential values.
- Run one Playwright worker in CI and retain trace, screenshot, video, and HTML report only on failure.
- A direct API `200` cannot pass a page journey whose visible UI remains loading or blank.

---

### Task 1: Establish the Cloud Playwright Harness and Red Daily Regression

**Files:**
- Create: `package.json`
- Create: `playwright.config.ts`
- Create: `e2e/cloud-pages.spec.ts`
- Create: `.github/workflows/cloud-e2e.yml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `E2E_BASE_URL`, defaulting only in local developer execution to `http://127.0.0.1:8010`; CI supplies the deployed cloud URL.
- Produces: `npm run test:e2e:cloud` and a Playwright HTML report under `playwright-report/`.

- [x] **Step 1: Write the failing Daily rendered-content E2E test**

```ts
test('Daily saved brief renders after Read', async ({ page }) => {
  await page.goto('/daily-market-brief');
  await page.getByLabel('市场日期').fill('2026-07-17');
  await page.getByRole('button', { name: '读取' }).click();
  await expect(page.getByRole('heading', { name: '核心指数' })).toBeVisible();
  await expect(page.locator('#summary')).not.toBeEmpty();
  await expect(page.getByRole('status')).not.toContainText('正在读取');
});
```

- [x] **Step 2: Run the test against the cloud URL and record RED evidence**

Run: `E2E_BASE_URL=http://47.84.190.191:8010 npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public`

Expected: fail if the browser-visible Daily page remains in its loading state despite the saved report API response.

- [x] **Step 3: Add public page smoke contracts**

```ts
for (const journey of [
  ['/daily-market-brief', '每日市场简报'],
  ['/weekly-review', '每周复盘'],
  ['/command', 'Command Workbench'],
] as const) {
  test(`${journey[0]} has one desktop main journey`, async ({ page }) => {
    await page.goto(journey[0]);
    await expect(page.getByRole('main')).toBeVisible();
    await expect(page.getByRole('heading', { name: journey[1] })).toBeVisible();
    await expect(page.locator('body')).toEvaluate((body) =>
      body.scrollWidth <= document.documentElement.clientWidth
    );
  });
}
```

- [x] **Step 4: Configure failure artifacts and a manually dispatched GitHub workflow**

Configure Chromium desktop, `workers: 1`, `trace: 'retain-on-failure'`, `screenshot: 'only-on-failure'`, `video: 'retain-on-failure'`, and upload the Playwright report after test completion. The workflow must run only through `workflow_dispatch` until it is stable; it receives `base_url` as an input and must not deploy.

- [x] **Step 5: Run local static checks and commit**

Run: `npm ci && npx playwright install --with-deps && npx playwright test --list`

Expected: test discovery succeeds without contacting cloud services.

Commit: `git add package.json package-lock.json playwright.config.ts e2e .github/workflows/cloud-e2e.yml .gitignore && git commit -m "test: add cloud browser acceptance harness"`

### Task 2: Diagnose and Fix Settling Behaviour Before Visual Changes

**Files:**
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Modify: `tests/test_daily_market_brief.py`
- Modify: `tests/test_weekly_review_web_auth.py`
- Modify: `e2e/cloud-pages.spec.ts`

**Interfaces:**
- Consumes: Daily read/date/history responses and the shared browser `fetch` helper contract.
- Produces: every initial and user-triggered browser request settles into success, visible retryable error, or visible access recovery within a bounded timeout.

- [x] **Step 1: Write failing renderer and browser-script tests**

Add tests that execute the rendered Daily JavaScript with a pending `fetch` promise and assert it replaces `正在读取每日市场简报。` with a visible retry action after the bounded timeout. Add a parallel Command parser test asserting its fetch settles to the existing recovery UI.

- [x] **Step 2: Run the focused tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_daily_market_brief tests.test_web_experience tests.test_command_workbench -v`

Expected: the new pending-request assertions fail because Daily has no bounded visible recovery contract.

- [x] **Step 3: Implement the shared request-settling contract**

Add a dependency-free inline helper used by Daily, Weekly, and Command page scripts. It must use `AbortController`, a finite timeout, response JSON validation, and a caller-supplied success handler. It must render a product-language retry state for abort/network/invalid-response failures, preserve public Daily requests without Authorization, and keep existing distinct access payload handling.

- [x] **Step 4: Run GREEN and rerun the Daily cloud E2E regression**

Run: `.venv/bin/python -m unittest tests.test_daily_market_brief tests.test_weekly_review_web_auth tests.test_web_experience tests.test_command_workbench -v`

Then run: `E2E_BASE_URL=http://47.84.190.191:8010 npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public`

Expected: local tests pass; cloud run remains an explicit pre-deploy baseline or fails with captured evidence until the release is deployed.

- [x] **Step 5: Commit the focused behaviour change**

Commit: `git add investment_knowledge_mcp/weekly_review_web.py investment_knowledge_mcp/command_workbench.py tests/test_daily_market_brief.py tests/test_weekly_review_web_auth.py tests/test_web_experience.py tests/test_command_workbench.py e2e/cloud-pages.spec.ts && git commit -m "fix: settle browser requests with visible recovery"`

### Task 3: Consolidate Desktop Navigation and Page Displays

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
- Consumes: `render_primary_navigation(active_page)` and existing page-local anchor/candidate content.
- Produces: exactly one product-level navigation rail on desktop and one page header/main hierarchy on every page.

- [x] **Step 1: Add renderer contracts**

Assert every renderer emits exactly one `nav[aria-label="主导航"]`, one `main`, and one `h1`; Daily emits no duplicate `.sidebar`; Weekly emits local anchors without a duplicate global rail; Command action catalog remains visible in a contextual column.

- [x] **Step 2: Record the pre-change browser evidence**

Run: `.venv/bin/python -m unittest tests.test_web_experience tests.test_daily_market_brief tests.test_weekly_review_web_auth tests.test_command_workbench -v`

Expected: current Daily and Weekly renderer contracts fail because duplicate desktop chrome remains.

- [x] **Step 3: Implement the minimal shared shell and page-local layout changes**

Keep the shared rail at 216px, use a fluid `minmax(0, 1fr)` main column, remove Daily's `.sidebar`, turn Weekly's former product links into a local contents list, and make Command's action catalog a contextual `aside`. Keep system typography, clear dividers, labelled table scrolling, visible focus, and status/error roles.

- [x] **Step 4: Run GREEN, then desktop visual contracts**

Run: `.venv/bin/python -m unittest tests.test_web_experience tests.test_daily_market_brief tests.test_weekly_review_web_auth tests.test_command_workbench -v`

Then run: `E2E_BASE_URL=http://47.84.190.191:8010 npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public`

Expected: renderer tests pass; cloud evidence remains recorded separately until deployment.

- [x] **Step 5: Commit the display slice**

Commit: `git add investment_knowledge_mcp/web_experience.py investment_knowledge_mcp/weekly_review_web.py investment_knowledge_mcp/command_workbench.py tests e2e/cloud-pages.spec.ts && git commit -m "feat: unify desktop product workspace"`

### Task 4: Add Protected and Primary-Action Browser Coverage

**Files:**
- Modify: `e2e/cloud-pages.spec.ts`
- Modify: `playwright.config.ts`
- Modify: `docs/product/Acceptance-Testing-Agent-Protocol.md`

**Interfaces:**
- Consumes: CI-only `E2E_PROTECTED_ACCESS_TOKEN` when provided.
- Produces: public browser coverage, explicit protected-skip evidence, and protected read-only/confirmation-guard coverage without data mutation.

- [x] **Step 1: Write E2E assertions for every primary action**

Cover Daily `读取` and saved-date selection; Weekly public `读取`; Command action catalog load and `系统状态` parse; unauthenticated Command recovery; protected read-only system-status success only when the CI secret exists; and a write-like Command preview that stops at visible confirmation.

- [x] **Step 2: Run test discovery and a no-secret public run**

Run: `npx playwright test --project=desktop-public --list`

Run: `E2E_BASE_URL=http://47.84.190.191:8010 npx playwright test --project=desktop-public`

Expected: public tests run; protected tests are not silently passed and report skipped because the secret is absent.

- [x] **Step 3: Document the acceptance-agent mandatory workflow**

Add the cloud Playwright command, desktop-only scope, failure-artifact requirements, secrets rule, no-write rule, and status mapping to `Acceptance-Testing-Agent-Protocol.md`.

- [x] **Step 4: Commit the acceptance standard**

Commit: `git add e2e/cloud-pages.spec.ts playwright.config.ts docs/product/Acceptance-Testing-Agent-Protocol.md && git commit -m "docs: standardize cloud browser acceptance"`

### Task 5: Integrate, Deploy, and Close the Acceptance Loop

**Files:**
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`

- [ ] **Step 1: Run complete local verification**

Run: `.venv/bin/python -m unittest tests.test_web_experience tests.test_daily_market_brief tests.test_weekly_review_web_auth tests.test_command_workbench -v`

Run: `npm run test:e2e:cloud -- --list`

Run: `git diff --check`

- [ ] **Step 2: Review changed routes and classify deployment**

Run: `python3 scripts/classify_deploy_change.py origin/main HEAD`

Expected: application renderer changes select `targeted_quick` with `weekly-review-web` and `command-api` when Command changes; documentation and E2E workflow files do not independently cause an application deploy.

- [ ] **Step 3: Record Deploy Intent and integrate only reviewed commits**

Record feature, authoritative main commit, classified mode, affected services, cloud URL, watch owner, and Playwright retest command in Delivery Queue. Merge only onto current authoritative `main`; do not deploy a feature branch.

- [ ] **Step 4: Use the one serialized deployment path and wait for stable health**

Do not start a second deployment channel. Verify route health plus a 30-second stability window before browser acceptance.

- [ ] **Step 5: Run independent cloud Playwright acceptance and update durable state**

Run: `E2E_BASE_URL=http://47.84.190.191:8010 npx playwright test --project=desktop-public`

Run the protected project only when the CI secret/session is available. Attach artifacts, update `AT-2026-07-16-002`, apply the Coordinator Return Gate, and keep user acceptance pending until the user explicitly accepts.
