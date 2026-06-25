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
| AT-2026-06-25-001 | Weekly review web | `http://47.84.190.191:8010/weekly-review` | failed | blocker | Retested by Acceptance Testing Agent on 2026-06-25 20:20-20:24 SGT. `GET /weekly-review` returned 200. Browser screenshots: `/tmp/weekly-review-desktop-initial.png`, `/tmp/weekly-review-desktop-generated.png`, `/tmp/weekly-review-desktop-save.png`, `/tmp/weekly-review-desktop-holdings.png`, `/tmp/weekly-review-mobile-generated.png`. Browser evidence JSON: `/tmp/weekly-review-acceptance-browser.json`. | Main UI and all six core sections render after Generate, but the data-source status cards expose raw internal strings `index provider not configured` and `external event provider not implemented`. Save report returns HTTP 500 and displays a raw database constraint error, including `null value in column "report_key"`, `review_reports`, failing row details, and JSON-like internals. The UI still uses arbitrary start/end date inputs and the Generate button calls `GET /api/weekly-review?...` instead of the natural-week generate contract in the current tech plan. Auth/token behavior is not understandable: the page shows only an unlabeled token placeholder, and saving without a token fails as a database error rather than a clear auth or save-state message. Desktop and mobile layouts are broadly usable, with no document-level horizontal overflow on a 390px viewport. | Do not ask for user acceptance. Fix save persistence or present a clear user-facing save failure, replace provider/internal exception strings with product-language degraded states, align the web flow with the natural-week read/generate/refresh/save contract, and then move this item to `needs_retest`. |
| AT-2026-06-25-002 | Command Workbench | `http://47.84.190.191:8010/command` | pending | major | Feature registry says deployed and user acceptance is pending. | Independent user-facing acceptance has not been run in this queue. | Run black-box acceptance against the cloud URL with representative commands, preview/execute flows, unsupported actions, auth behavior, and screenshot evidence. |
| AT-2026-06-25-003 | Research display Level 1 decision card | Default stock analysis display | pending | major | Feature registry says deployed, deploy verified, and user acceptance pending. | Independent user-facing acceptance has not been run in this queue. | Identify the user surface and run acceptance against the Level 1 default display, verbose/detail paths, source evidence visibility, and empty/missing data behavior. |

## Retest Rules

- When a failed item is fixed, change status to `needs_retest` before retesting.
- When retest passes, change status to `passed` and record evidence.
- When retest still fails, keep `failed` and append the new evidence.
- Do not delete failed rows after a fix; preserve history and add a new row only when the feature surface or acceptance scope materially changes.
