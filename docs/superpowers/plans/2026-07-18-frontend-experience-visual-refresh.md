# Frontend Experience Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the three Python-rendered surfaces into one professional, responsive operational workspace without changing routes, business behavior, or public/private boundaries.

**Architecture:** Extend the dependency-free `web_experience.py` kernel so it owns the single product rail, workspace tokens, header, status, metric, and responsive rules. Command, Weekly Review, and Daily Market Brief retain their page JavaScript and API behavior but consume this shared visual contract and remove redundant page rails.

**Tech Stack:** Python 3.11, inline HTML/CSS/JavaScript, `unittest`, Node.js behavior harnesses, serialized production deployment workflow.

## Global Constraints

- Start the execution worktree from `origin/main`; preserve the visual spec and this plan by cherry-picking their commits before edits.
- Preserve `/`, `/command`, `/weekly-review`, and `/daily-market-brief` URLs and route/API semantics.
- Keep unified browser access behavior unchanged and never expose token values.
- Keep Daily Market Brief HTML and browser request flow completely tokenless.
- Do not add a frontend framework, external font, icon library, package manager, static-asset build process, or new public URL.
- Use one shared product navigation rail; never render a duplicate `.sidebar` beside it on Weekly or Daily.
- At 390px, prohibit page-level horizontal overflow; allow it only inside labelled `.table-scroll` regions.
- Preserve skip links, landmarks, active navigation, visible focus, `role="status"`, and `role="alert"`.

---

### Task 1: Establish the shared professional workspace contract

**Files:**

- Modify: `investment_knowledge_mcp/web_experience.py`
- Modify: `tests/test_web_experience.py`

**Interfaces:**

- Consumes: `render_primary_navigation(active_page: PageIdentity) -> str`
- Produces: `render_workspace_header(title: str, subtitle: str, controls_html: str = "") -> str`, shared workspace CSS, and compatible primary navigation.

- [ ] **Step 1: Write failing renderer-contract tests**

Add these methods to `WebExperienceTests`:

```python
def test_shared_workspace_css_has_single_rail_and_compact_rules(self) -> None:
    css = render_experience_css()
    self.assertIn(".experience-brand", css)
    self.assertIn(".experience-context", css)
    self.assertIn(".experience-metric-grid", css)
    self.assertIn(".experience-status--error", css)
    self.assertIn("@media (max-width: 760px)", css)
    self.assertIn("overflow-x: auto", css)
    self.assertIn("prefers-reduced-motion", css)

def test_primary_navigation_includes_product_wordmark(self) -> None:
    html = render_primary_navigation("daily_market_brief")
    self.assertIn('class="experience-brand"', html)
    self.assertEqual(1, html.count('aria-label="主导航"'))
    self.assertIn('href="/daily-market-brief" aria-current="page"', html)

def test_workspace_header_escapes_text_and_keeps_controls_adjacent(self) -> None:
    from investment_knowledge_mcp.web_experience import render_workspace_header
    html = render_workspace_header("A < B", "Desk & report", '<button id="read">Read</button>')
    self.assertIn("A &lt; B", html)
    self.assertIn("Desk &amp; report", html)
    self.assertIn('class="experience-page-controls"', html)
    self.assertIn('id="read"', html)
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_web_experience.WebExperienceTests.test_shared_workspace_css_has_single_rail_and_compact_rules tests.test_web_experience.WebExperienceTests.test_primary_navigation_includes_product_wordmark tests.test_web_experience.WebExperienceTests.test_workspace_header_escapes_text_and_keeps_controls_adjacent -v
```

Expected: FAIL because the new workspace selectors and header renderer do not exist.

- [ ] **Step 3: Implement the minimal shared primitives**

Add this exact helper:

```python
def render_workspace_header(title: str, subtitle: str, controls_html: str = "") -> str:
    controls = f'<div class="experience-page-controls">{controls_html}</div>' if controls_html else ""
    return (
        '<header class="experience-page-header">'
        f'<div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>{controls}'
        '</header>'
    )
```

Update `render_primary_navigation()` to emit one `<aside class="experience-rail">`, one `experience-brand` link, and the existing three destination links inside the labelled nav. Preserve order and `aria-current`.

Replace the existing CSS with tokens `--experience-canvas`, `--experience-surface`, `--experience-ink`, `--experience-muted`, `--experience-accent`, `--experience-positive`, `--experience-negative`, and `--experience-warning`. Define `.experience-shell`, `.experience-rail`, `.experience-context`, `.experience-page-header`, `.experience-page-controls`, `.experience-metric-grid`, `.experience-status`, `.experience-status--error`, and `.table-scroll`. At 760px, make the rail a sticky horizontal destination bar, stack controls, and retain 44px controls. Add a reduced-motion rule with transition duration `0.01ms`.

- [ ] **Step 4: Run shared-kernel tests to verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_web_experience -v
```

Expected: all shared access and workspace contracts pass.

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/web_experience.py tests/test_web_experience.py
git commit -m "feat: add professional workspace primitives"
```

### Task 2: Remove duplicate Weekly and Daily chrome

**Files:**

- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Modify: `tests/test_weekly_review_web_auth.py`
- Modify: `tests/test_daily_market_brief.py`

**Interfaces:**

- Consumes: `render_experience_css`, `render_primary_navigation`, and `render_workspace_header`.
- Produces: one persistent product rail per page, main-flow contextual navigation, shared headers and metric grids, unchanged APIs.

- [ ] **Step 1: Write failing structural/boundary tests**

Add to `tests/test_weekly_review_web_auth.py`:

```python
def test_public_weekly_page_uses_one_product_rail_and_shared_workspace_header(self) -> None:
    html = web.render_weekly_review_workbench_html()
    self.assertEqual(1, html.count('class="experience-rail"'))
    self.assertNotIn('class="sidebar"', html)
    self.assertIn('class="experience-page-header"', html)
    self.assertIn('class="experience-metric-grid"', html)
    self.assertNotIn('id="access-token"', html)
```

Add to `tests/test_daily_market_brief.py`:

```python
def test_daily_page_uses_one_product_rail_and_remains_tokenless_after_visual_refresh(self) -> None:
    html = render_daily_market_brief_html()
    self.assertEqual(1, html.count('class="experience-rail"'))
    self.assertNotIn('class="sidebar"', html)
    self.assertIn('class="experience-page-header"', html)
    self.assertIn('class="experience-metric-grid"', html)
    self.assertNotIn("access-token", html)
    self.assertNotIn("Authorization", html)
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_weekly_review_web_auth.WeeklyReviewWebAuthorizationTests.test_public_weekly_page_uses_one_product_rail_and_shared_workspace_header tests.test_daily_market_brief.DailyMarketBriefTests.test_daily_page_uses_one_product_rail_and_remains_tokenless_after_visual_refresh -v
```

Expected: FAIL due to legacy `.sidebar`, `.topbar`, and page-specific metric markup.

- [ ] **Step 3: Implement Weekly and Daily migration**

Import `render_workspace_header` in `weekly_review_web.py`.

For Weekly, replace the inner `.sidebar` and `.topbar` markup with:

```python
render_workspace_header(
    "本周复盘",
    "只读查看基于交易记录、账户快照、当前持仓、IPO 和知识库生成的周复盘。",
    weekly_controls_html,
)
```

Keep IDs `prev-week`, `this-week`, `week-date`, and the `公开只读` marker unchanged. Move existing local anchors into `<nav class="experience-context" aria-label="On this page">` inside `main`; rename `status-grid` to `experience-metric-grid`; remove page-local sidebar, brand, nav, topbar, and duplicate control CSS.

For Daily, use:

```python
render_workspace_header(
    "每日市场简报",
    "按市场查看收盘后的核心指数、领涨方向、个股、资金流和数据缺口。",
    daily_controls_html,
)
```

Keep IDs `market-date`, `saved-date`, `read`, `generate`, and all `data-market` values unchanged. Move existing local anchors into `experience-context`, rename `summary-grid` to `experience-metric-grid`, and remove duplicated page chrome. Do not alter any `fetch()` URL, method, body, or Authorization behavior.

- [ ] **Step 4: Run Weekly/Daily regression suites**

Run:

```bash
.venv/bin/python -m unittest tests.test_weekly_review_web_auth tests.test_weekly_review_holder_attribution tests.test_daily_market_brief -v
```

Expected: Weekly public reads remain tokenless, protected operations retain their matrix, and Daily remains tokenless.

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/weekly_review_web.py tests/test_weekly_review_web_auth.py tests/test_daily_market_brief.py
git commit -m "feat: unify weekly and daily workspace display"
```

### Task 3: Recompose Command Workbench

**Files:**

- Modify: `investment_knowledge_mcp/command_workbench.py`
- Modify: `tests/test_web_experience.py`

**Interfaces:**

- Consumes: the shared workspace CSS and navigation.
- Produces: a desktop contextual Action Catalog, compact inline catalog, and distinct preview/execution work areas without changing protected request behavior.

- [ ] **Step 1: Write failing Command layout tests**

Add to `WebExperienceTests`:

```python
def test_command_uses_contextual_catalog_without_nested_shell_chrome(self) -> None:
    from investment_knowledge_mcp.command_workbench import render_command_workbench_html
    html = render_command_workbench_html()
    self.assertIn('class="command-workspace"', html)
    self.assertIn('class="command-catalog"', html)
    self.assertIn('class="command-workareas"', html)
    self.assertNotIn('<div class="shell">', html)
    self.assertIn('@media (max-width: 900px)', html)

def test_command_visual_refresh_keeps_recovery_and_preview_contracts(self) -> None:
    from investment_knowledge_mcp.command_workbench import render_command_workbench_html
    html = render_command_workbench_html()
    self.assertIn('id="access-panel"', html)
    self.assertIn('id="preview"', html)
    self.assertIn('id="result" role="status" aria-live="polite"', html)
    self.assertIn('id="parse"', html)
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_web_experience.WebExperienceTests.test_command_uses_contextual_catalog_without_nested_shell_chrome tests.test_web_experience.WebExperienceTests.test_command_visual_refresh_keeps_recovery_and_preview_contracts -v
```

Expected: first test FAILS because the legacy `.shell` and generic `aside` layout is still rendered.

- [ ] **Step 3: Implement Command composition without behavioral edits**

Replace the command page's inner `.shell`, generic `main`, and generic `aside` selectors with:

```html
<div class="command-workspace">
  <main id="main-content" class="command-main" tabindex="-1">...</main>
  <aside class="command-catalog" aria-label="Command actions">...</aside>
</div>
```

Wrap Preview, action form, and execution sections in `<div class="command-workareas">`. Preserve IDs `preview-section`, `form-section`, `preview`, `form`, `result`, `smart-input`, `parse`, all access-panel IDs, and all JavaScript selectors/endpoints. Use a desktop `minmax(0, 1fr) minmax(248px, 320px)` grid, a 900px single-column breakpoint, and a 680px one-column command form. Retain 44px compact controls and use shared accent variables instead of the legacy teal palette.

- [ ] **Step 4: Run behavioral, renderer, and syntax checks**

Run:

```bash
.venv/bin/python -m unittest tests.test_web_experience tests.test_weekly_review_web_auth tests.test_daily_market_brief -v
.venv/bin/python -m py_compile investment_knowledge_mcp/web_experience.py investment_knowledge_mcp/command_workbench.py investment_knowledge_mcp/weekly_review_web.py
```

Expected: all tests pass; the existing Node command harness confirms retry/access behavior is unchanged.

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/command_workbench.py tests/test_web_experience.py
git commit -m "feat: refine command workspace display"
```

### Task 4: Integrate, deploy, and independently retest

**Files:**

- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`

**Interfaces:**

- Consumes: the committed visual branch, focused test evidence, deploy classification, and cloud deployment event.
- Produces: one authoritative main integration, one deploy intent, cloud smoke, and an explicit acceptance result.

- [ ] **Step 1: Reconcile with main**

Run:

```bash
git fetch origin main
git merge --ff-only origin/main
git log --oneline origin/main..HEAD
git diff --check origin/main...HEAD
```

Expected: only visual spec/plan and visual-refresh commits are ahead. If fast-forward fails, stop and resolve the exact ref conflict before deployment.

- [ ] **Step 2: Verify and classify**

Run:

```bash
.venv/bin/python -m unittest tests.test_web_experience tests.test_weekly_review_web_auth tests.test_weekly_review_holder_attribution tests.test_daily_market_brief -v
.venv/bin/python scripts/smoke_test.py
python3 scripts/classify_deploy_change.py investment_knowledge_mcp/web_experience.py investment_knowledge_mcp/command_workbench.py investment_knowledge_mcp/weekly_review_web.py
git diff --check
```

Expected: all focused suites pass and the classifier chooses a product deploy mode, not `no_deploy`.

- [ ] **Step 3: Integrate and record Deploy Intent**

After the Return Gate accepts the diff, merge it into current `main`, update the three delivery-state documents with branch, main SHA, tests, target surfaces, acceptance owner, and this exact intent: feature `Frontend experience system`; ref `main@<sha>`; selected deploy mode; services `command-api` and `weekly-review-web`; URLs `/command`, `/weekly-review`, `/daily-market-brief`; watch owner `Frontend Experience Coordinator`.

- [ ] **Step 4: Use one deployment path and smoke test**

Push `main`, wait for its one serialized automatic `deploy.yml` run, and do not start a competing deploy. After stable health, run:

```bash
curl -fsS http://47.84.190.191:8010/health
curl -fsS http://47.84.190.191:8010/command
curl -fsS http://47.84.190.191:8010/weekly-review
curl -fsS http://47.84.190.191:8010/daily-market-brief
```

Expected: each returns 200. Run only an unauthenticated Command parse to confirm secret-free `access_required`; do not use credentials.

- [ ] **Step 5: Retest visual acceptance**

Use an isolated browser at exact 390px only if the production URL is allowed by browser policy. Verify shared navigation, no duplicate rails, stacked controls, no page overflow, labelled table scrolling, protected recovery, public Weekly read, and tokenless Daily requests. If policy still blocks the raw IP, record the browser-environment blocker; do not claim visual acceptance.

- [ ] **Step 6: Record durable closure**

Commit and push the queue/registry updates. Terminal status is `ready_for_user_acceptance` only after independent browser acceptance passes; otherwise record `blocked_with_owner` with exact browser-policy or product-defect evidence.

