# Frontend Experience System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first shared frontend experience slice by applying a server-rendered app shell, primary navigation, and design-token contract to `/weekly-review`, `/`, and `/command` while preserving current page behavior.

**Architecture:** Keep the active web pages Python-rendered and add one small shared shell helper under `investment_knowledge_mcp/`. Weekly Review and Command Workbench continue to own their page-specific content and JavaScript behavior; the helper owns global shell HTML, navigation metadata, common design tokens, shared focus/landmark conventions, and shared utility classes.

**Tech Stack:** Python stdlib HTTP handlers, inline server-rendered HTML/CSS/JavaScript, `scripts/smoke_test.py`, optional focused renderer tests if the implementation adds a test module, and browser screenshots for desktop/mobile evidence.

---

Status: ready for Frontend Experience Reviewer.
Linked PRD: `docs/product/PRD-Frontend-Experience-System.md`
Change package: `docs/changes/frontend-experience-system/`
Delivery Queue: `DQ-2026-07-05-003`

## Product Contract

The first implementation pass is a two-surface shell release. It changes the shared visual/navigation structure of `/weekly-review`, `/`, and `/command`, but it must not change command execution, weekly-review generation, auth, token storage, APIs, deployment behavior, or user acceptance state.

The implementation is intentionally narrow enough for one Development pass:

- Add shared shell/tokens/navigation helper.
- Apply the shell to Weekly Review and Command Workbench renderers.
- Add renderer/smoke tests for shared shell and regression strings.
- Capture local desktop/mobile evidence for `/weekly-review` and `/command`.
- Return to the Feature Coordinator for Release Reviewer and deploy decision.

Daily Market Brief and Candidate Insights are not new primary navigation surfaces in this slice. Candidate Insights remains embedded inside Weekly Review, and Daily Market Brief remains omitted until it has a Product package or PRD and a real route.

## Current Implementation

Current render and route ownership:

- `investment_knowledge_mcp/weekly_review_web.py`
  - Owns `GET /` and `GET /weekly-review`.
  - Owns Weekly Review APIs: `/api/weekly-review`, `/api/weekly-review/generate`, `/api/weekly-review/refresh`, `/api/weekly-review/save`.
  - Owns Candidate Insights APIs: `/api/candidate-insights` and `/api/candidate-insights/{id}/{confirm,reject}`.
  - Mirrors public Command Workbench routes: `GET /command`, `/api/command-workbench/actions`, `/api/command-workbench/parse`, and `/api/command-workbench/execute`.
- `investment_knowledge_mcp/command_workbench.py`
  - Owns `render_command_workbench_html()`, action catalog rendering, token localStorage key `command_workbench_token`, recent key `command_workbench_recent`, pinned key `command_workbench_pinned`, preview/run behavior, confirmation guards, and result-card semantics.
- `investment_knowledge_mcp/command_api.py`
  - Owns internal `command-api` `GET /command`, workbench APIs, and legacy `POST /command`.
- `investment_knowledge_mcp/weekly_review_web.py::render_weekly_review_workbench_html()`
  - Owns Weekly Review inline page rendering, token localStorage key `weekly_review_web_token`, report controls, status/source cards, report Markdown textarea, and candidate-insight controls.

The current HTML strings define separate `:root` tokens, `.shell`, button styles, card styles, breakpoints, focus behavior, and navigation. The new helper should unify the shared contract without migrating to templates or a frontend build pipeline.

## File Boundaries

Create:

- `investment_knowledge_mcp/frontend_shell.py`
  - Owns `NavItem`, `ShellPage`, `render_app_shell(...)`, `shared_design_tokens_css()`, `shared_base_css()`, `shared_nav_items()`, and `active_nav_key` handling.
  - Contains no API logic, no command parsing, no database access, and no token/auth behavior.

Modify:

- `investment_knowledge_mcp/weekly_review_web.py`
  - Keep route handlers and API handlers unchanged.
  - Refactor only `render_weekly_review_workbench_html()` so it passes page-specific HTML/CSS/JS into `render_app_shell(...)`.
  - Replace page-local primary navigation with shared app navigation.
  - Keep Weekly Review section table-of-contents anchors as page-local secondary navigation, not primary app navigation.
- `investment_knowledge_mcp/command_workbench.py`
  - Keep action registry, parser, preview, execution guard, result-card parsing/rendering JavaScript, and localStorage keys unchanged.
  - Refactor only `render_command_workbench_html()` so it passes page-specific HTML/CSS/JS into `render_app_shell(...)`.
  - Keep the Action Catalog as page-local supporting content.
- `scripts/smoke_test.py`
  - Add narrow renderer assertions for shell/nav/tokens/regression strings alongside the existing Weekly Review and Command Workbench smoke coverage.

Do not modify unless a failing test proves it is necessary:

- `investment_knowledge_mcp/command_api.py`
  - It should continue importing and serving `render_command_workbench_html()`; no route or auth changes are expected.
- `investment_knowledge_mcp/weekly_review.py`
  - Weekly Review data generation and report structures are out of scope.
- `investment_knowledge_mcp/command_router.py`
  - Command parsing/execution semantics are out of scope.
- `db/schema.sql`
  - No schema change is needed.

If implementation discovers that auth headers, token storage keys, private route behavior, secret handling, or token/error exposure must change, stop and return a blocker. Do not expand this plan into Security/Access work.

## Shared Shell Design

`frontend_shell.py` should expose a small server-rendered contract:

```python
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Literal


NavKey = Literal["weekly-review", "command"]


@dataclass(frozen=True)
class NavItem:
    key: NavKey
    label: str
    href: str


@dataclass(frozen=True)
class ShellPage:
    title: str
    lang: str
    active_nav: NavKey
    page_class: str
    heading: str
    subtitle: str
    main_html: str
    aside_html: str = ""
    page_css: str = ""
    page_js: str = ""
```

Expected helper responsibilities:

- `shared_nav_items()` returns exactly Weekly Review and Command Workbench:

```python
[
    NavItem(key="weekly-review", label="Weekly Review", href="/weekly-review"),
    NavItem(key="command", label="Command Workbench", href="/command"),
]
```

- `render_app_shell(page: ShellPage) -> str` returns a complete `<!doctype html>` document with:
  - `<html lang="...">`
  - `<meta name="viewport" content="width=device-width, initial-scale=1">`
  - Shared `<style>` block before page CSS.
  - Skip link pointing at `#main-content`.
  - Header/brand region.
  - Shared primary nav with `aria-label="Primary"` and `aria-current="page"` on the active page.
  - `<main id="main-content" class="app-main ...">`.
  - Optional page aside in a shell-supported area when supplied.
  - Page JavaScript appended after shell/page markup.

The helper should escape shell-owned string inputs such as title, heading, subtitle, labels, and hrefs. Page-specific HTML snippets remain renderer-owned because they already contain intentional inputs, IDs, and JavaScript templates.

## Design Token Contract

Use neutral, quiet product colors that work for both pages and avoid a one-note palette:

```css
:root {
  color-scheme: light;
  --app-bg: #f6f7f9;
  --app-surface: #ffffff;
  --app-surface-muted: #f0f3f6;
  --app-ink: #20242a;
  --app-muted: #627083;
  --app-line: #d8e0e8;
  --app-accent: #176b6f;
  --app-accent-strong: #145f63;
  --app-accent-soft: #e5f2f1;
  --app-good: #176b43;
  --app-bad: #a33b35;
  --app-warn: #8a5a00;
  --app-warn-bg: #fff7df;
  --app-focus: #254edb;
  --app-radius: 6px;
  --app-space-1: 4px;
  --app-space-2: 8px;
  --app-space-3: 12px;
  --app-space-4: 16px;
  --app-space-5: 24px;
}
```

Implementation may preserve existing page-local class names temporarily, but the shared shell must define these reusable classes:

- `.skip-link`
- `.app-shell`
- `.app-header`
- `.app-brand`
- `.app-primary-nav`
- `.app-nav-link`
- `.app-nav-link[aria-current="page"]`
- `.app-layout`
- `.app-main`
- `.app-side`
- `.app-panel`
- `.app-notice`
- `.app-button`
- `.app-button.primary`
- `.app-status-region`
- `.app-table-scroll`

Page-specific CSS should map existing colors to shared variables instead of keeping separate `--bg`, `--panel`, `--ink`, `--muted`, and `--accent` definitions.

## Route Ownership

Routes must stay exactly where they are:

- `/` and `/weekly-review` continue to call `render_weekly_review_workbench_html()` from `WeeklyReviewWebHandler`.
- Public `/command` on `weekly-review-web` continues to call `render_command_workbench_html()`.
- Internal `/command` on `command-api` continues to call the same `render_command_workbench_html()`.
- Weekly Review APIs and Candidate Insights APIs remain in `weekly_review_web.py`.
- Command Workbench APIs remain available in both `weekly_review_web.py` and `command_api.py`.

No route redirects are required. `/` may render Weekly Review with the shared nav active state set to `weekly-review`; it does not need to change URL.

## Regression Contract

Preserve these exact behavior strings or identifiers:

- Weekly Review route/API strings:
  - `/api/weekly-review`
  - `/api/weekly-review/generate`
  - `/api/weekly-review/refresh`
  - `/api/weekly-review/save`
  - `/api/candidate-insights?status=pending`
  - `/api/candidate-insights/${id}/${action}` in the JavaScript template
- Command Workbench route/API strings:
  - `/api/command-workbench/actions`
  - `/api/command-workbench/parse`
  - `/api/command-workbench/execute`
- Token/localStorage keys:
  - `weekly_review_web_token`
  - `command_workbench_token`
  - `command_workbench_recent`
  - `command_workbench_pinned`
- Important element IDs:
  - Weekly Review: `api-token`, `prev-week`, `this-week`, `week-date`, `generate`, `refresh`, `save`, `message`, `source-status`, `markdown-text`, `market-filter`, `status-filter`.
  - Command Workbench: `smart-input`, `api-token`, `parse`, `preview-section`, `preview`, `form-section`, `form-title`, `form`, `result`, `catalog`, `pinned`, `recent`.
- Command result-card parser section labels:
  - `Thesis:`
  - `Drivers:`
  - `Risks:`
  - `Watch:`
  - `Freshness:`
  - `Evidence:`
- Existing confirmation guard and execute behavior:
  - Browser calls parse before execute.
  - Server recomputes preview during execute.
  - Confirmation is required for write-like actions.

Do not convert inline JavaScript behavior to a shared script in this slice unless the exact behavior is preserved and tests still cover the route/API/key strings above.

## Accessibility And Responsive Rules

Shared shell requirements:

- Add a visible-on-focus skip link to `#main-content`.
- Use one primary navigation landmark: `<nav class="app-primary-nav" aria-label="Primary">`.
- Add `aria-current="page"` on the active primary nav link.
- Provide a shared `:focus-visible` style for links, buttons, inputs, selects, textareas, and summary controls.
- Keep `main` meaningful and unique per page.
- Use mobile breakpoints that keep app nav, token fields, action buttons, status messages, and generated content readable at 390px width.

Page-specific requirements:

- Weekly Review keeps `#message` and `#source-status` as status regions. `#source-status` already has `aria-live="polite"`; implementation should also make the primary message area a deliberate status region, for example `role="status" aria-live="polite"`.
- Command Workbench should make `#preview` and `#result` deliberate update regions, for example `aria-live="polite"` on the preview/result containers or a documented focus move after preview/run. Prefer live regions because they are the smallest behavior change.
- Tables should live inside intentional horizontal scroll containers on mobile. Do not introduce page-level horizontal scrolling.

## Implementation Tasks

### Task 1: Add Renderer Contract Tests

**Files:**
- Modify: `scripts/smoke_test.py`

- [ ] **Step 1: Add failing assertions for shared shell and nav**

Add assertions near the existing `render_command_workbench_html()` and `render_weekly_review_workbench_html()` smoke checks:

```python
workbench_html = render_command_workbench_html()
assert "Command Workbench" in workbench_html
assert "/api/command-workbench/actions" in workbench_html
assert "/api/command-workbench/parse" in workbench_html
assert "/api/command-workbench/execute" in workbench_html
assert "command_workbench_token" in workbench_html
assert "command_workbench_recent" in workbench_html
assert "command_workbench_pinned" in workbench_html
assert "id=\"main-content\"" in workbench_html
assert "class=\"skip-link\"" in workbench_html
assert "aria-label=\"Primary\"" in workbench_html
assert "href=\"/weekly-review\"" in workbench_html
assert "href=\"/command\"" in workbench_html
assert "aria-current=\"page\"" in workbench_html
assert "Daily Market Brief" not in workbench_html
assert "Thesis:" in workbench_html
assert "Drivers:" in workbench_html
assert "Risks:" in workbench_html
assert "Watch:" in workbench_html
assert "Freshness:" in workbench_html
assert "Evidence:" in workbench_html

weekly_web_html = render_weekly_review_workbench_html()
assert "InvestmentKnowledge" in weekly_web_html
assert "本周复盘" in weekly_web_html
assert "/api/weekly-review/save" in weekly_web_html
assert "/api/weekly-review/generate" in weekly_web_html
assert "/api/weekly-review/refresh" in weekly_web_html
assert "/api/candidate-insights?status=pending" in weekly_web_html
assert "weekly_review_web_token" in weekly_web_html
assert "id=\"main-content\"" in weekly_web_html
assert "class=\"skip-link\"" in weekly_web_html
assert "aria-label=\"Primary\"" in weekly_web_html
assert "href=\"/weekly-review\"" in weekly_web_html
assert "href=\"/command\"" in weekly_web_html
assert "aria-current=\"page\"" in weekly_web_html
assert "Daily Market Brief" not in weekly_web_html
```

- [ ] **Step 2: Run the focused smoke test and confirm failure**

Run:

```bash
python3 scripts/smoke_test.py
```

Expected before implementation: fails on the new shared shell assertions.

### Task 2: Add Shared Shell Helper

**Files:**
- Create: `investment_knowledge_mcp/frontend_shell.py`

- [ ] **Step 1: Implement `frontend_shell.py`**

Create the helper with dataclasses, shared nav metadata, token CSS, base CSS, nav renderer, and complete document renderer. Use shell-owned escaping for labels and metadata. The helper should not import page modules or repository code.

- [ ] **Step 2: Add a minimal direct check**

Run:

```bash
python3 -m py_compile investment_knowledge_mcp/frontend_shell.py
```

Expected: no output and exit code 0.

### Task 3: Apply Shell To Command Workbench

**Files:**
- Modify: `investment_knowledge_mcp/command_workbench.py`

- [ ] **Step 1: Import the shared helper**

Use:

```python
from investment_knowledge_mcp.frontend_shell import ShellPage, render_app_shell
```

- [ ] **Step 2: Refactor only `render_command_workbench_html()`**

Keep all current element IDs, API paths, storage keys, result-card parsing functions, and action catalog logic. Move Command Workbench page CSS into a page CSS string that uses shared variables, and pass body markup into `ShellPage(active_nav="command", ...)`.

- [ ] **Step 3: Preserve result-card semantics**

Verify that `parseDecisionCard(message)`, `renderDecisionResult(card, rawMessage)`, `translateEvidence(value)`, and raw-output fallback logic are unchanged except for class names that do not affect parsing or display semantics.

### Task 4: Apply Shell To Weekly Review

**Files:**
- Modify: `investment_knowledge_mcp/weekly_review_web.py`

- [ ] **Step 1: Import the shared helper**

Use:

```python
from investment_knowledge_mcp.frontend_shell import ShellPage, render_app_shell
```

- [ ] **Step 2: Refactor only `render_weekly_review_workbench_html()`**

Keep all current element IDs, API paths, token key, report controls, candidate-insight handlers, and generated-report rendering logic. Remove the old app-primary sidebar links from primary navigation and keep Weekly Review internal anchors as secondary page navigation.

- [ ] **Step 3: Add deliberate status region semantics**

Make the primary message element a status region without changing its ID:

```html
<div id="message" class="app-notice notice" role="status" aria-live="polite">正在读取本周复盘状态。</div>
```

### Task 5: Verify Routes And Rendering

**Files:**
- Modify: `scripts/smoke_test.py` if needed after implementation.

- [ ] **Step 1: Run Python syntax checks**

Run:

```bash
python3 -m py_compile investment_knowledge_mcp/frontend_shell.py investment_knowledge_mcp/command_workbench.py investment_knowledge_mcp/weekly_review_web.py investment_knowledge_mcp/command_api.py
```

Expected: no output and exit code 0.

- [ ] **Step 2: Run smoke verification**

Run:

```bash
python3 scripts/smoke_test.py
```

Expected: all smoke assertions pass, including shell/nav/regression strings.

- [ ] **Step 3: Verify `command-api` still uses the same renderer**

Do not change `command_api.py` unless required. The passing smoke and import checks should prove that `command_api.py` can still import `render_command_workbench_html()`.

### Task 6: Capture Local Browser Evidence

**Files:**
- Evidence artifacts should be written under `/private/tmp` or `/tmp`, not committed.

- [ ] **Step 1: Start only the local surface needed for browser verification**

Use `weekly-review-web` for `/weekly-review`, `/`, and the public `/command` mirror. State the database target before starting it. Do not start `command-api` unless the implementation specifically needs internal route-owner browser verification; if started, use a strong local token and do not record it in docs.

- [ ] **Step 2: Capture desktop and mobile screenshots**

Capture:

- `/weekly-review` desktop, around 1440x1000.
- `/weekly-review` mobile, around 390x844.
- `/command` desktop, around 1440x1000.
- `/command` mobile, around 390x844.

Screenshots should prove:

- Shared header and primary nav exist on both pages.
- Active nav state is correct.
- No Daily Market Brief nav affordance exists.
- Token fields and primary actions are visible.
- No overlapping primary controls or horizontal page scroll appears at mobile width.

- [ ] **Step 3: Keyboard and live-region spot check**

Record concise evidence in the implementation return:

- Tab reaches skip link, primary nav, token field, primary actions, and page-specific controls.
- Active nav link exposes current state.
- Weekly Review message/source status and Command Workbench preview/result updates use the documented live-region/focus pattern.

## Test Strategy

Minimum local tests for implementation handoff:

```bash
python3 -m py_compile investment_knowledge_mcp/frontend_shell.py investment_knowledge_mcp/command_workbench.py investment_knowledge_mcp/weekly_review_web.py investment_knowledge_mcp/command_api.py
python3 scripts/smoke_test.py
git diff --check
```

If `.venv/bin/python` exists in the implementation worktree, prefer it for repo checks. If it is absent, use `python3` and report that the ignored per-worktree virtualenv was unavailable.

Smoke coverage must include:

- `/` and `/weekly-review` still render Weekly Review.
- `/command` still renders through both route owners by keeping `command_api.py` and `weekly_review_web.py` imports/routes unchanged.
- Required API route strings are still present.
- Token storage keys are unchanged.
- Command Workbench result-card parser strings are unchanged.
- Daily Market Brief is absent from nav.
- Shared skip link, primary nav, active state, and main landmark are present.

Browser evidence must include desktop/mobile screenshots for `/weekly-review` and `/command`. Local browser evidence is sufficient for implementation handoff; deployed cloud evidence is required after release.

## Deploy Strategy

Development implementation must not deploy by itself unless explicitly assigned a deploy role later.

Because this slice changes both `/weekly-review` and `/command` in one release, the Feature Coordinator must run or dispatch Release Reviewer before deploy. Release Reviewer should check:

- Branch/commit to deploy is named and pushed.
- `weekly-review-web` public surface is affected.
- `command-api` internal `/command` renderer is affected through the shared renderer import.
- Smoke tests and screenshot evidence exist.
- No auth/header/token/private-route behavior changed.
- Deploy mode is selected by the coordinator or release owner, with affected service/URL and watch path recorded.
- Acceptance Testing is routed only after the relevant cloud surface is updated.

Rollback plan:

- Revert the implementation commit if shell rendering breaks either page.
- Since no schema, API, route, token, or deploy-contract changes are planned, rollback should be code-only.
- If only one page breaks during local implementation, fix in the same branch before handoff rather than splitting the slice, unless the blocker is structural and returned to the Feature Coordinator.

## Reviewer Gates

Frontend Experience Reviewer before implementation handoff:

- Confirm the plan covers PRD acceptance criteria 1 through 10.
- Confirm the shell/nav contract includes only Weekly Review and Command Workbench.
- Confirm Candidate Insights remains embedded and Daily Market Brief is omitted.
- Confirm responsive/mobile evidence requirements cover both pages.
- Confirm accessibility checks include skip link, landmarks, focus visibility, keyboard reachability, active nav state, and status/result announcements.
- Confirm non-goals and regression strings protect APIs, auth headers, token keys, result-card semantics, and Weekly Review data behavior.

Release Reviewer before deploy:

- Required because one release changes both `/weekly-review` and `/command`.
- Confirm the pushed ref, deploy path, affected services, verification URL, and watch owner/path.
- Confirm local tests and screenshot evidence passed.
- Confirm Security/Access Reviewer is not needed because no auth/token/private-route behavior changed. If any such behavior changed, block release until Security/Access review occurs.

Acceptance Reviewer after deployment:

- Test deployed `/weekly-review`, `/`, and `/command` from the real cloud/user-facing URL.
- Verify shared shell/nav/tokens on the deployed pages.
- Verify Weekly Review read/generate/refresh/save and candidate-insight controls are not regressed, using safe scoped actions and existing acceptance rules.
- Verify Command Workbench token entry, parse/preview, execute, confirmation guards, local history, action catalog, and result cards are not regressed.
- Capture desktop/mobile evidence and update the acceptance state without marking user acceptance accepted.

Security/Access Reviewer:

- Not required for this planned shell-only slice.
- Becomes required only if implementation changes auth headers, token storage, private route behavior, secret handling, or token/error exposure.
- If such a change appears necessary, stop and return a blocker instead of expanding scope.

## Rollout Plan

1. Development Agent implements this plan on a task branch.
2. Development Agent runs local syntax/smoke/diff checks and captures desktop/mobile local evidence.
3. Development Agent returns branch, commit, evidence, and remaining gaps to Feature Coordinator.
4. Feature Coordinator applies Return Gate and dispatches Frontend Experience Reviewer if not already done.
5. After Frontend Experience Reviewer passes, Feature Coordinator routes implementation/release preparation.
6. Release Reviewer checks the two-surface release before deploy.
7. Named release/deploy owner deploys the pushed ref through the shared deploy path and records Deploy Intent.
8. Acceptance Reviewer tests the deployed user-facing surface.
9. Feature Coordinator asks the Owner for user acceptance only after deployed acceptance passes.

## Non-Goals

- No frontend framework, bundler, SPA router, or template migration.
- No Daily Market Brief route, nav link, disabled fake link, or implementation.
- No Candidate Insights standalone page or nav item.
- No Weekly Review API/data/model/generation changes.
- No Command Workbench parser, confirmation, execution, action registry, local history, or result-card semantic changes.
- No auth header, token storage key, private route, or secret handling changes.
- No schema migration.
- No cloud deploy by Development during implementation unless later explicitly assigned.
- No user acceptance marking.
