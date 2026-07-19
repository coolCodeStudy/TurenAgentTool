# Frontend Experience E2E Reliability Design

## Status

- Date: 2026-07-19
- Feature: Frontend experience system
- Owner authorization: The Owner reopened this feature and directed the Coordinator to close the loop for page display, non-responsive controls, and all existing page journeys. Desktop is the only required viewport in this delivery.
- Decision: Playwright Test is the acceptance gate; Playwright MCP and Chrome inspection are diagnostic tools only.

## Problem

The cloud routes and direct APIs can return successful responses while the rendered page remains in a loading state. The Daily Market Brief currently demonstrates this mismatch: a direct read of the saved CN brief returns a complete response, while the Chrome page can remain at `正在读取每日市场简报。`. Earlier browser checks also exposed incomplete Command interaction evidence. API smoke alone therefore cannot establish user-visible correctness.

The three rendered pages also retain duplicated page chrome: a product-level rail plus an inner page sidebar. On desktop this wastes workspace and makes the operating product look like several unrelated tools.

## Goals

1. Make every desktop primary user journey on `/daily-market-brief`, `/weekly-review`, and `/command` executable and visibly complete in a real browser.
2. Treat a failed, hung, or unrendered browser action as a product failure even when its HTTP API returns `200`.
3. Replace duplicate navigation chrome with one shared desktop rail, one page header, and page-local navigation only where it adds non-duplicative value.
4. Establish a repeatable cloud Playwright Test suite as the required Acceptance Testing Agent browser workflow.
5. Preserve existing routes and access boundaries: Daily reads remain tokenless, Weekly is public-read/protected-write, and Command stays protected for protected operations.

## Non-Goals

- Mobile or 390px testing in this delivery.
- Replacing the Python-rendered pages with a SPA or a frontend build system.
- Creating production data, executing write-like commands, or storing any browser credential in tests, screenshots, traces, repository files, or logs.
- Using a browser automation tool to bypass Codex URL policy. The standard runner is an independently configured Playwright environment.

## Approaches Considered

### A. API smoke only

Fast but insufficient: it has already passed while the user page remained unusable. Rejected.

### B. Playwright MCP only

Useful for an agent to inspect an intermittent failure, but it is a conversational debugging interface rather than a versioned, CI-quality test gate. Rejected as the sole standard.

### C. Hybrid: Playwright Test gate with MCP/Chrome diagnostics — selected

Add a small Node Playwright Test project dedicated to cloud acceptance. It runs deterministic desktop journeys and emits screenshots, traces, and console evidence on failure. A separate Playwright MCP or user Chrome session may investigate a failing run, but cannot replace the test result.

## Desktop Information Architecture

- The shared rail owns the product brand and the three destinations in operating order: Daily Market Brief, Weekly Review, Command Workbench.
- Each page owns a single semantic `main`, one `h1`, a compact page header, and its own controls.
- Daily Market Brief removes its duplicate inner sidebar. Its former anchor links become an unobtrusive inline contents row only when report content is present.
- Weekly Review retains page-local report anchors but does not render a second product-navigation rail. Its optional right-hand context is retained only when it contains user-relevant report navigation.
- Command Workbench keeps its action catalog as a contextual desktop column, not a second global navigation surface.
- All pages use the shared spacing, typography, status, table, focus, and error rules from the existing Frontend Experience design.

## Browser Behaviour Contract

### Daily Market Brief

For a known saved public brief, selecting its date and pressing `读取` must replace the loading status with a visible brief summary and core index content. Saved-date lookup and history-job list must also settle. A request timeout or non-JSON response must replace loading with a visible retryable error; it must never leave an indefinite progress message.

### Weekly Review

Public read and visible report sections must settle without a credential. Protected mutations must show a recoverable access response without exposing credentials. A public read cannot be blocked by a protected-state migration.

### Command Workbench

The public action catalog and parser UI must settle after page load. A protected request without access must show the existing `access_required` recovery panel. A protected success fixture/session may test a read-only system-status path; write-like commands may only be tested through their confirmation guard and must not execute.

## Playwright Acceptance Standard

`@playwright/test` is the primary standard. The suite runs against `E2E_BASE_URL`, uses Chromium desktop at 1440x1000, one worker, no persisted browser storage, and trace/screenshot/video artifacts retained on failure. It has separate public and protected projects; protected tests are skipped with an explicit report reason when a CI-only secret is not present.

Every Acceptance Testing Agent must:

1. Run the cloud Playwright suite for affected routes after deployment.
2. Attach the HTML report and failed trace/screenshot paths to the acceptance record.
3. Treat a test timeout, perpetual loading state, console error, missing primary content, or page-level horizontal overflow as failed or blocked—not passed from API evidence.
4. Use Playwright MCP or Chrome only to diagnose the failing assertion, then rerun the versioned test.

## Acceptance Criteria

- Desktop Playwright suites cover navigation, first visible content, primary read/parse action, relevant unauthorized recovery, and no-page-overflow contracts for all three surfaces.
- Daily's known saved public report visibly renders after `读取`; its browser test would fail on the current indefinite-loading symptom.
- No primary action may remain in a loading state after its bounded client timeout.
- Command, Weekly, and Daily retain their declared access classes and never expose a credential in artifacts.
- The desktop pages no longer show duplicate global-navigation rails.
- The Acceptance Testing Agent protocol specifies this workflow, evidence, and status rule.

## Deployment And Watch Contract

- Deploy decision during implementation: `self_deploy` only after all local renderer and Playwright fixture tests pass, the reviewed change is integrated to authoritative `main`, and a fresh Deploy Intent names the affected service.
- Cloud retest owner: this Feature Coordinator, using an independent Playwright runner against the deployed URL.
- Watch path: the versioned cloud suite result and GitHub Actions deploy event. A failed suite returns to this Coordinator for root-cause diagnosis; no automatic acceptance pass is inferred from API smoke.
