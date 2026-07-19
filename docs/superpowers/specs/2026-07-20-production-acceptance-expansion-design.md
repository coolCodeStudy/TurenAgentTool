# Production Acceptance Expansion Design

## Intent

The owner authorized a production-focused closure pass for the Frontend experience system. The system must test every public browser/API contract and every safe authorization boundary without creating reports, saving portfolio content, executing commands, or exposing credentials.

## Options Considered

1. Browser smoke only: fast but cannot prove API contracts, authorization boundaries, or asset delivery.
2. **Layered read-only acceptance (selected):** run local contract tests, deployed public API contracts, browser journeys, and protected rejection checks; use a dedicated fixture only for protected success. This is repeatable and does not mutate production data.
3. Run all real actions on production: provides weak additional evidence while creating reports, history jobs, saved data, or possible operational commands. Rejected.

## Acceptance Model

The production matrix has four layers.

| Layer | Coverage | Allowed production effects |
|---|---|---|
| Static/contract | Route ownership, access classes, invalid request validation, renderer tests | None |
| Public HTTP | Every public route in `app_gateway.route_contracts()` plus HTML/JavaScript assets | Read-only GETs and deliberately invalid POST payloads that fail before dispatch |
| Browser | Daily, Weekly, and Command visible journeys, navigation, loading settlement, recovery panels, overflow, accessibility primitives | Read-only controls and no-token recovery only |
| Protected fixture | Read-only successful Command preview and visible confirmation guard | Dedicated approved test credential only; no execute/save/generate action |

## Contract Matrix

- Public pages/assets: `/`, `/weekly-review`, `/assets/weekly-review.js`, `/daily-market-brief`, `/assets/daily-market-brief.js`, `/command`, and `/health` must be reachable and content-complete.
- Public APIs: action catalog, Weekly read, Daily read, saved dates, and public-page history jobs must return documented JSON and never require a browser token.
- Protected APIs: candidate insights, Command parse/execute, Weekly generate/refresh/save, and candidate decision endpoints must return a recoverable `401` without a credential before any mutation.
- Public write endpoints: Daily generate and history-job creation receive deliberately invalid payloads only, proving validation rejects before a job/report can be created.
- Successful protected preview and confirmation guard require `E2E_PROTECTED_ACCESS_TOKEN`, supplied through an approved repository secret. GitHub PAT and `COMMAND_API_TOKEN` are not substitutes.

## Standardization

Playwright Test remains the browser gate. A separate public API contract spec uses its isolated request context against the deployed base URL. Both suites run with fresh browser state, retain failure artifacts, and are safe to run after any cloud deployment. The GitHub `cloud-e2e.yml` workflow is validation-only and must never deploy application code.

## Non-goals

- Do not perform valid generation, refresh, save, execute, confirm, reject, webhook, or data-import operations against production.
- Do not read, print, commit, or transmit credential values outside the approved CI secret injection mechanism.
- Do not claim protected-success coverage when the dedicated fixture is absent.
