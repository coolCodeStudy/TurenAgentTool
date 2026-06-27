# Acceptance Queue

This queue tracks independent acceptance testing before user acceptance.

Use `docs/product/Acceptance-Testing-Agent-Protocol.md` for role boundaries, status definitions, and evidence requirements.

Acceptance testing does not mark user acceptance. Only the user can move `User Acceptance` to `accepted`.

## Status Values

- `pending`
- `passed`
- `failed`
- `blocked`
- `needs_retest`
- `not_required`

## Queue

| ID | Feature | Surface | Status | Severity | Evidence | Findings | Next Action |
|---|---|---|---|---|---|---|---|
| AT-2026-06-25-001 | Weekly review web | `http://47.84.190.191:8010/weekly-review` | needs_retest | major | Original failed retest by Acceptance Testing Agent on 2026-06-25 20:20-20:24 SGT. `GET /weekly-review` returned 200. Browser screenshots: `/tmp/weekly-review-desktop-initial.png`, `/tmp/weekly-review-desktop-generated.png`, `/tmp/weekly-review-desktop-save.png`, `/tmp/weekly-review-desktop-holdings.png`, `/tmp/weekly-review-mobile-generated.png`. Browser evidence JSON: `/tmp/weekly-review-acceptance-browser.json`. Development fix prepared on 2026-06-28: syntax checks passed; no-database weekly Web contract checks passed; full smoke was blocked because local PostgreSQL `localhost:55432` refused connections. | Original findings: Main UI and all six core sections rendered after Generate, but data-source status cards exposed raw internal strings; Save report returned HTTP 500 and displayed a raw `report_key` database constraint error; UI used arbitrary start/end date inputs and Generate called the old range GET path; token behavior was unclear. Development fix now uses natural-week read/generate/refresh/save endpoints, product-language source statuses, labeled token input, safe save errors, and legacy `report_key` schema hardening. | Deploy the pushed fix to `weekly-review-web`, then run independent acceptance retest against the cloud URL. Do not ask for user acceptance until retest passes. |
| AT-2026-06-25-002 | Command Workbench | `http://47.84.190.191:8010/command` | pending | major | Feature registry says deployed and user acceptance is pending. | Independent user-facing acceptance has not been run in this queue. | Run black-box acceptance against the cloud URL with representative commands, preview/execute flows, unsupported actions, auth behavior, and screenshot evidence. |
| AT-2026-06-25-003 | Research display Level 1 decision card | Default stock analysis display | pending | major | Feature registry says deployed, deploy verified, and user acceptance pending. | Independent user-facing acceptance has not been run in this queue. | Identify the user surface and run acceptance against the Level 1 default display, verbose/detail paths, source evidence visibility, and empty/missing data behavior. |

## Retest Rules

- When a failed item is fixed, change status to `needs_retest` before retesting.
- When retest passes, change status to `passed` and record evidence.
- When retest still fails, keep `failed` and append the new evidence.
- Do not delete failed rows after a fix; preserve history and add a new row only when the feature surface or acceptance scope materially changes.
