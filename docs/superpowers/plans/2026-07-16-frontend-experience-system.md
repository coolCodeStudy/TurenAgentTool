# Frontend Experience System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one Python-rendered product shell and one safe browser access model for protected user-facing operations while keeping Daily Market Brief fully tokenless.

**Architecture:** Add a dependency-light `web_experience.py` kernel that owns primary navigation, shared tokens/shell CSS, and browser access-session primitives. Existing renderers keep page-specific content and behavior. Integrate the accepted Weekly Review public-read fix before overlapping changes, then adopt the kernel in Command Workbench, Weekly Review, and Daily Market Brief with explicit authorization and regression contracts.

**Tech Stack:** Python 3.11, `http.server`, inline HTML/CSS/JavaScript renderers, `unittest`, existing deployment classifier and serialized Ops deployment workflow.

## Global Constraints

- Preserve `/`, `/command`, `/weekly-review`, and `/daily-market-brief` behavior and URLs.
- Use canonical browser key `investment_knowledge_access_token` only for protected user-facing requests.
- Safely migrate `command_workbench_token` and `weekly_review_web_token`; never guess when both are non-empty and differ.
- Never print, log, commit, transmit, screenshot, or persist token values or Authorization headers.
- Keep Daily Market Brief reads, current-session generation, saved dates, and public history jobs tokenless.
- Keep Ops API, deploy, database, provider, and other machine credentials separate.
- Preserve the accepted Weekly Review public-read and privileged-operation matrix.
- Use one bordered surface per content section; do not add card-within-card clutter.
- Provide visible focus, semantic landmarks, `aria-current`, progress `role="status"`, and blocking-error `role="alert"`.
- At a 390px viewport, prohibit page-level horizontal overflow; wide tables may scroll only inside labeled local containers.
- Do not add a frontend framework, template engine, package manager, or asset build pipeline.
- All new durable documents, code comments, and product copy source must be English; existing Chinese user-facing labels may remain or be normalized deliberately.

---

## File Structure

- Create `investment_knowledge_mcp/web_experience.py`: shared page identity, navigation, CSS, access-session script, and access-error payloads. It must not import repositories or domain services.
- Create `tests/test_web_experience.py`: pure renderer and access-contract tests.
- Modify `investment_knowledge_mcp/command_workbench.py`: consume the shared shell and canonical access helper.
- Modify `investment_knowledge_mcp/command_api.py`: return shared recoverable access error codes.
- Modify `investment_knowledge_mcp/weekly_review_web.py`: preserve the accepted public Weekly Review behavior, consume the shared shell, and use shared protected-access errors for protected Command endpoints.
- Modify `tests/test_weekly_review_web_auth.py`: preserve the accepted Weekly Review endpoint matrix and add shared-shell/token-absence assertions.
- Modify `tests/test_daily_market_brief.py`: assert shared navigation and the complete tokenless boundary.
- Modify `scripts/smoke_test.py`: assert shared shell markers and unchanged page routes.
- Modify `docs/project-management/Feature-Registry.md`, `Acceptance-Queue.md`, and `Delivery-Queue.md`: implementation, deployment, and acceptance traceability.

### Task 1: Reconcile the Weekly Review Authorization Baseline

**Files:**
- Integrate: `investment_knowledge_mcp/weekly_review_web.py`
- Integrate: `tests/test_weekly_review_web_auth.py`
- Integrate: `docs/techplans/weekly-review.md`
- Inspect: `docs/project-management/Delivery-Queue.md`
- Inspect: `docs/project-management/Acceptance-Queue.md`

**Interfaces:**
- Consumes: accepted Weekly Review development commit `aef9424a65b3d014ef82495361222885803bfb90` plus its coordinator's final deploy/acceptance return.
- Produces: an implementation baseline where `GET /api/weekly-review` is public, the public Weekly Review page is read-only and has no token field, and generate/refresh/save/candidate operations remain protected.

- [ ] **Step 1: Inspect the compatibility return before integration**

Run:

```bash
git show --stat --oneline aef9424a65b3d014ef82495361222885803bfb90
git show --check aef9424a65b3d014ef82495361222885803bfb90
git diff HEAD aef9424a65b3d014ef82495361222885803bfb90 -- investment_knowledge_mcp/weekly_review_web.py tests/test_weekly_review_web_auth.py docs/techplans/weekly-review.md
```

Expected: only Weekly Review public-read/read-only UI, privilege tests, and its technical-plan traceability change; no Command token-storage or Daily Market Brief auth change appears.

- [ ] **Step 2: Integrate the accepted compatibility commit**

Run:

```bash
git cherry-pick aef9424a65b3d014ef82495361222885803bfb90
```

Expected: clean cherry-pick or narrow conflicts limited to coordinator-state/docs already changed on this branch. Resolve docs by preserving newer Frontend Experience state and both feature rows.

- [ ] **Step 3: Verify the accepted matrix**

Run:

```bash
.venv/bin/python -m unittest tests.test_weekly_review_web_auth tests.test_weekly_review_holder_attribution tests.test_daily_market_brief -v
```

Expected: all tests pass; public Weekly Review read is allowed, privileged routes remain protected, holder attribution still renders, and Daily Market Brief remains public.

- [ ] **Step 4: Record the reconciliation result**

Update `DQ-2026-07-04-020` with the accepted commit and the Weekly Review coordinator's final deployed/accepted ref. Do not close the Weekly Review coordinator's own row on its behalf.

- [ ] **Step 5: Commit only if conflict resolution or state reconciliation changed files**

```bash
git add docs/project-management/Delivery-Queue.md docs/project-management/Acceptance-Queue.md docs/project-management/Feature-Registry.md investment_knowledge_mcp/weekly_review_web.py tests/test_weekly_review_web_auth.py docs/techplans/weekly-review.md
git commit -m "chore: reconcile weekly review public auth"
```

Expected: no extra commit when the cherry-pick was clean and no coordinator state required adjustment.

### Task 2: Build the Shared Experience Kernel

**Files:**
- Create: `investment_knowledge_mcp/web_experience.py`
- Create: `tests/test_web_experience.py`

**Interfaces:**
- Consumes: no domain modules.
- Produces:
  - `PageIdentity` string values: `daily_market_brief`, `weekly_review`, `command_workbench`
  - `render_experience_css() -> str`
  - `render_primary_navigation(active_page: str) -> str`
  - `render_access_session_script() -> str`
  - `access_error_payload(code: str) -> dict[str, object]`

- [ ] **Step 1: Write failing navigation and token tests**

Create `tests/test_web_experience.py` with these contracts:

```python
import unittest

from investment_knowledge_mcp.web_experience import (
    CANONICAL_ACCESS_KEY,
    access_error_payload,
    render_access_session_script,
    render_experience_css,
    render_primary_navigation,
)


class WebExperienceTests(unittest.TestCase):
    def test_primary_navigation_has_stable_order_and_active_state(self) -> None:
        html = render_primary_navigation("weekly_review")
        self.assertLess(html.index("/daily-market-brief"), html.index("/weekly-review"))
        self.assertLess(html.index("/weekly-review"), html.index("/command"))
        self.assertIn('href="/weekly-review" aria-current="page"', html)

    def test_access_script_uses_canonical_and_both_legacy_keys(self) -> None:
        script = render_access_session_script()
        self.assertEqual("investment_knowledge_access_token", CANONICAL_ACCESS_KEY)
        self.assertIn("command_workbench_token", script)
        self.assertIn("weekly_review_web_token", script)
        self.assertIn("legacy_conflict", script)
        self.assertNotIn("console.log", script)

    def test_access_errors_are_distinct_and_recoverable(self) -> None:
        required = access_error_payload("access_required")
        rejected = access_error_payload("access_rejected")
        unavailable = access_error_payload("access_not_configured")
        self.assertNotEqual(required["error"], rejected["error"])
        self.assertNotEqual(rejected["error"], unavailable["error"])
        self.assertTrue(required["recovery"]["next_action"])

    def test_css_contains_shared_focus_and_compact_contracts(self) -> None:
        css = render_experience_css()
        self.assertIn(":focus-visible", css)
        self.assertIn("@media (max-width: 760px)", css)
        self.assertIn("--experience-accent", css)
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_web_experience -v
```

Expected: FAIL with `ModuleNotFoundError: investment_knowledge_mcp.web_experience`.

- [ ] **Step 3: Implement the minimal module**

Implement constants and helpers using escaped static metadata:

```python
from __future__ import annotations

from html import escape
from typing import Final, Literal

CANONICAL_ACCESS_KEY: Final = "investment_knowledge_access_token"
LEGACY_ACCESS_KEYS: Final = ("command_workbench_token", "weekly_review_web_token")
PageIdentity = Literal["daily_market_brief", "weekly_review", "command_workbench"]

PRIMARY_DESTINATIONS: Final = (
    ("daily_market_brief", "/daily-market-brief", "每日简报"),
    ("weekly_review", "/weekly-review", "每周复盘"),
    ("command_workbench", "/command", "命令工作台"),
)


def render_primary_navigation(active_page: PageIdentity) -> str:
    links = []
    for page, href, label in PRIMARY_DESTINATIONS:
        current = ' aria-current="page"' if page == active_page else ""
        links.append(f'<a href="{escape(href)}"{current}>{escape(label)}</a>')
    return '<nav class="experience-nav" aria-label="主导航">' + "".join(links) + "</nav>"
```

`render_access_session_script()` must create `window.InvestmentKnowledgeAccess` with these exact methods:

```javascript
resolve()
getToken()
remember(value)
forget()
authorizationHeaders()
classifyResponse(status, payload)
```

`resolve()` must return only `{status: "ready"}`, `{status: "missing"}`, or `{status: "legacy_conflict"}`—never the token value. Internal closures may use the value to build the Authorization header.

- [ ] **Step 4: Run the kernel tests to verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_web_experience -v
```

Expected: all four tests pass.

- [ ] **Step 5: Commit the kernel**

```bash
git add investment_knowledge_mcp/web_experience.py tests/test_web_experience.py
git commit -m "feat: add shared web experience kernel"
```

### Task 3: Adopt the Shared Shell and Access Model in Command Workbench

**Files:**
- Modify: `investment_knowledge_mcp/command_workbench.py`
- Modify: `investment_knowledge_mcp/command_api.py`
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Modify: `tests/test_web_experience.py`
- Modify: `scripts/smoke_test.py`

**Interfaces:**
- Consumes: `render_experience_css`, `render_primary_navigation`, `render_access_session_script`, and `access_error_payload` from Task 2.
- Produces: Command HTML with shared navigation/shell, canonical access migration, and distinct recoverable access errors in both HTTP serving paths.

- [ ] **Step 1: Write failing Command renderer and error tests**

Add this method to `WebExperienceTests` in `tests/test_web_experience.py`:

```python
    def test_command_uses_shared_shell_and_canonical_access(self) -> None:
        from investment_knowledge_mcp.command_workbench import render_command_workbench_html

        html = render_command_workbench_html()
        self.assertIn('href="/command" aria-current="page"', html)
        self.assertIn("investment_knowledge_access_token", html)
        self.assertNotIn('id="api-token"', html)
        self.assertIn('id="access-panel"', html)
        self.assertIn('role="alert"', html)
```

Add unit coverage that invokes the authorization helpers with no header, an invalid synthetic header, and no configured server token. Assert `access_required`, `access_rejected`, and `access_not_configured` respectively. Do not assert or print the synthetic value.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_web_experience -v
```

Expected: FAIL because Command still renders `api-token` and old shell markup.

- [ ] **Step 3: Update Command rendering and access recovery**

In `command_workbench.py`:

- Inject shared CSS and primary navigation with active page `command_workbench`.
- Replace the always-visible token input with a hidden-by-default access panel containing a labeled password input, `Continue`, and `Forget access` actions.
- Resolve/migrate browser state at startup.
- Use `authorizationHeaders()` for parse/execute only.
- On `access_required`, `access_rejected`, or `access_not_configured`, show product copy in the access panel and retain the attempted command.
- Do not store token values in recent/pinned history.

In both `command_api.py` and `weekly_review_web.py`, produce shared access payloads:

```python
if not configured_token:
    self._write_json(HTTPStatus.SERVICE_UNAVAILABLE, access_error_payload("access_not_configured"))
elif not supplied_token:
    self._write_json(HTTPStatus.UNAUTHORIZED, access_error_payload("access_required"))
elif not hmac.compare_digest(supplied_token, configured_token):
    self._write_json(HTTPStatus.UNAUTHORIZED, access_error_payload("access_rejected"))
```

- [ ] **Step 4: Run Command and smoke tests to verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_web_experience -v
.venv/bin/python scripts/smoke_test.py
```

Expected: shared-shell/access tests pass; smoke still validates action catalog, preview, confirmation, and result rendering.

- [ ] **Step 5: Scan for token leakage regressions**

Run:

```bash
rg -n "console\.log|location\.(href|search)|URLSearchParams.*token|command_workbench_token|weekly_review_web_token" investment_knowledge_mcp/command_workbench.py investment_knowledge_mcp/web_experience.py
```

Expected: legacy key names appear only inside the migration helper; no token value is sent to logging or URLs.

- [ ] **Step 6: Commit Command adoption**

```bash
git add investment_knowledge_mcp/command_workbench.py investment_knowledge_mcp/command_api.py investment_knowledge_mcp/weekly_review_web.py investment_knowledge_mcp/web_experience.py tests/test_web_experience.py scripts/smoke_test.py
git commit -m "feat: unify command workbench access"
```

### Task 4: Adopt the Shared Shell in Weekly Review Without Reintroducing Token Friction

**Files:**
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Modify: `tests/test_weekly_review_web_auth.py`
- Modify: `tests/test_weekly_review_holder_attribution.py`

**Interfaces:**
- Consumes: accepted Task 1 public-read baseline and Task 2 shell helpers.
- Produces: shared Weekly Review navigation/tokens and preserved public read-only behavior with no user-managed token field.

- [ ] **Step 1: Add failing shell and authorization assertions**

Add this method to `WeeklyReviewWebAuthTests` in `tests/test_weekly_review_web_auth.py`:

```python
    def test_public_weekly_page_uses_shared_shell_without_token_control(self) -> None:
        html = render_weekly_review_workbench_html()
        self.assertIn('href="/weekly-review" aria-current="page"', html)
        self.assertIn('href="/daily-market-brief"', html)
        self.assertIn('href="/command"', html)
        self.assertNotIn('id="api-token"', html)
        self.assertNotIn("investment_knowledge_access_token", html)
        self.assertIn("公开只读", html)
```

Retain tests proving public GET read, protected generate/refresh/save/candidates, and public Daily Market Brief behavior.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_weekly_review_web_auth tests.test_weekly_review_holder_attribution -v
```

Expected: shell navigation assertion fails; existing authorization and attribution tests pass.

- [ ] **Step 3: Apply only shared shell/navigation primitives**

Inject `render_experience_css()` and `render_primary_navigation("weekly_review")`. Keep the page read-only UI from Task 1. Do not embed `render_access_session_script()` because the public page makes no protected request.

Preserve these route decisions exactly:

```text
GET /api/weekly-review                     public
POST /api/weekly-review/generate           protected
POST /api/weekly-review/refresh            protected
POST /api/weekly-review/save               protected
GET/POST /api/candidate-insights...        protected
```

- [ ] **Step 4: Run Weekly Review tests to verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_weekly_review_web_auth tests.test_weekly_review_holder_attribution -v
```

Expected: all tests pass and no token control is rendered.

- [ ] **Step 5: Commit Weekly Review adoption**

```bash
git add investment_knowledge_mcp/weekly_review_web.py tests/test_weekly_review_web_auth.py tests/test_weekly_review_holder_attribution.py
git commit -m "feat: align weekly review experience shell"
```

### Task 5: Adopt the Shared Shell in Daily Market Brief and Lock the Tokenless Boundary

**Files:**
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Modify: `tests/test_daily_market_brief.py`

**Interfaces:**
- Consumes: Task 2 shell/navigation primitives only.
- Produces: Daily Market Brief shared navigation/tokens with no browser access helper or protected request header.

- [ ] **Step 1: Add failing shell and tokenless assertions**

Add this method to `DailyMarketBriefTests` in `tests/test_daily_market_brief.py`:

```python
    def test_daily_brief_uses_shared_shell_and_remains_tokenless(self) -> None:
        html = render_daily_market_brief_html()
        self.assertIn('href="/daily-market-brief" aria-current="page"', html)
        self.assertIn('href="/weekly-review"', html)
        self.assertIn('href="/command"', html)
        self.assertNotIn("investment_knowledge_access_token", html)
        self.assertNotIn("Authorization", html)
        self.assertNotIn('id="api-token"', html)
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_daily_market_brief.DailyMarketBriefTests.test_daily_brief_uses_shared_shell_and_remains_tokenless -v
```

Expected: FAIL on the shared-shell active-state assertion.

- [ ] **Step 3: Inject shared shell primitives without access JavaScript**

Use `render_experience_css()` and `render_primary_navigation("daily_market_brief")`. Do not render or import the access-session script into the Daily Market Brief page. Keep all existing fetch calls header-free except `Content-Type` on JSON POST.

- [ ] **Step 4: Run Daily Market Brief regression tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_daily_market_brief tests.test_daily_market_history tests.test_daily_market_jobs -v
```

Expected: all tests pass, including public read/generate/history behavior and provider-safe error copy.

- [ ] **Step 5: Commit Daily Market Brief adoption**

```bash
git add investment_knowledge_mcp/weekly_review_web.py tests/test_daily_market_brief.py
git commit -m "feat: align daily brief experience shell"
```

### Task 6: Verify the Complete Slice and Update Delivery Traceability

**Files:**
- Modify: `scripts/smoke_test.py`
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`
- Modify: `docs/superpowers/plans/2026-07-16-frontend-experience-system.md`

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: one reviewed implementation ref, complete verification evidence, deploy classification, and acceptance-ready queue state.

- [ ] **Step 1: Add cross-page smoke assertions**

In `scripts/smoke_test.py`, render all pages and assert:

```python
for path in ("/daily-market-brief", "/weekly-review", "/command"):
    assert path in command_html
    assert path in weekly_html
    assert path in daily_html
assert "investment_knowledge_access_token" in command_html
assert "investment_knowledge_access_token" not in weekly_html
assert "investment_knowledge_access_token" not in daily_html
```

- [ ] **Step 2: Run the full narrow verification suite**

Run:

```bash
.venv/bin/python -m unittest tests.test_web_experience tests.test_weekly_review_web_auth tests.test_weekly_review_holder_attribution tests.test_daily_market_brief tests.test_daily_market_history tests.test_daily_market_jobs -v
.venv/bin/python scripts/smoke_test.py
.venv/bin/python -m py_compile investment_knowledge_mcp/web_experience.py investment_knowledge_mcp/command_workbench.py investment_knowledge_mcp/command_api.py investment_knowledge_mcp/weekly_review_web.py
git diff --check
```

Expected: zero failures and zero syntax/diff errors.

- [ ] **Step 3: Run deployment and delivery audits**

Run:

```bash
.venv/bin/python scripts/classify_deploy_change.py --repo . --base-sha origin/main --target-sha HEAD --format json
.venv/bin/python scripts/audit_delivery_state.py --feature "Frontend experience system"
```

Expected: deploy classifier names every affected service; delivery audit reports only the expected pending deploy/acceptance gap.

- [ ] **Step 4: Update traceability**

Set the registry technical plan to this plan, technical status `implemented`, implementation `local_verified`, evidence `test_passed`, and next action to coordinator integration/deploy. Move `AT-2026-07-16-002` to `needs_retest` only after the implementation ref is deployed. Update `DQ-2026-07-04-020` with the returned branch/commit and exact verification.

- [ ] **Step 5: Commit the verified implementation state**

```bash
git add scripts/smoke_test.py docs/project-management/Feature-Registry.md docs/project-management/Acceptance-Queue.md docs/project-management/Delivery-Queue.md docs/superpowers/plans/2026-07-16-frontend-experience-system.md
git commit -m "docs: record frontend experience verification"
```

### Task 7: Serialized Deploy, Cloud Smoke, and Independent Acceptance

**Files:**
- Modify after evidence: `docs/project-management/Feature-Registry.md`
- Modify after evidence: `docs/project-management/Acceptance-Queue.md`
- Modify after evidence: `docs/project-management/Delivery-Queue.md`

**Interfaces:**
- Consumes: pushed verified implementation ref and deploy-classifier targets from Task 6.
- Produces: stable cloud deployment, independent acceptance result, and `ready_for_user_acceptance` or a precise returned blocker.

- [ ] **Step 1: Push the reviewed implementation ref**

Use the repository's isolated first-line PAT flow. Confirm local HEAD equals the upstream branch SHA after push. Never print the PAT or credential-store contents.

- [ ] **Step 2: Record complete Deploy Intent**

Record in `DQ-2026-07-04-020`:

```text
Feature: Frontend experience system
Ref or commit: the exact output of `git rev-parse HEAD` from Step 1
Deploy mode: the exact `mode` value from Task 6's classifier JSON
Affected services: the complete `targets` list from Task 6's classifier JSON
Reason: shared renderer/access implementation
Verification URLs: /command, /weekly-review, /daily-market-brief
Watch owner/path: Frontend Experience Feature Coordinator in this task
```

- [ ] **Step 3: Use one shared serialized deploy path**

Before triggering, check whether an automatic production deploy is already running for the same ref. Trigger either the existing automatic path or the approved Ops API path, not both. Poll until completion and a stable health window; do not infer success from immediate container startup.

- [ ] **Step 4: Run coordinator cloud smoke**

Verify without exposing secrets:

```text
GET /command -> 200 shared shell
Command parse without access -> recoverable access_required, not bare unauthorized
GET /weekly-review -> 200 shared shell
GET /api/weekly-review?week_start=2026-06-22 -> 200 and holder attribution present
Privileged Weekly endpoints without access -> protected with recoverable error
GET /daily-market-brief -> 200 shared shell
Daily read/generate/dates/history -> tokenless contract preserved
No response artifact contains token values, Authorization headers, stack traces, or raw credential configuration
```

- [ ] **Step 5: Move acceptance to retest and dispatch an independent tester**

Update `AT-2026-07-16-002` to `needs_retest`, add a Delivery Queue row for the Acceptance Testing Agent, and include the exact deployed SHA/event, URLs, access matrix, 390px/desktop checks, migration cases, token-leak scans, and Daily Market Brief regression guard.

- [ ] **Step 6: Apply the Acceptance Return Gate**

Inspect the tester's branch/result/evidence. If major findings exist, mark the item failed and dispatch Development with exact reproduction. If passed, update the row to `passed`, reconcile state against authoritative `main`, and set the feature next action to Owner acceptance.

- [ ] **Step 7: Record terminal coordinator state**

When independent cloud acceptance passes:

```text
Closure: ready_for_user_acceptance
Deploy decision: self_deploy completed
User acceptance: pending
Watch path: closed for internal work; reopen on Owner acceptance feedback
```

Run:

```bash
.venv/bin/python scripts/audit_delivery_state.py --feature "Frontend experience system"
git diff --check
```

Expected: no hidden implementation, deploy, or independent-acceptance gap; only explicit Owner acceptance remains pending.
