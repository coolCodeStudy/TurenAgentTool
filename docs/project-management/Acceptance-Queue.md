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
| AT-2026-06-25-001 | Weekly review web | `http://47.84.190.191:8010/weekly-review` | failed | blocker | User screenshot plus live `GET /weekly-review` on 2026-06-25; `HEAD /weekly-review` returned 501. | Page is reachable, but the main report exposes internal/developer data-source states such as `index provider not configured` and `external event provider not implemented`. The page can say a draft/report was generated while key review sources are missing or not user-readable. | Do not ask for user acceptance yet. Decide whether index/external events are required for acceptance; either implement providers or replace internal states with a clear degraded-state UX and tracked product gap. Add an automated web acceptance check for this route. |
| AT-2026-06-25-002 | Command Workbench | `http://47.84.190.191:8010/command` | pending | major | Feature registry says deployed and user acceptance is pending. | Independent user-facing acceptance has not been run in this queue. | Run black-box acceptance against the cloud URL with representative commands, preview/execute flows, unsupported actions, auth behavior, and screenshot evidence. |
| AT-2026-06-25-003 | Research display Level 1 decision card | Default stock analysis display | pending | major | Feature registry says deployed, deploy verified, and user acceptance pending. | Independent user-facing acceptance has not been run in this queue. | Identify the user surface and run acceptance against the Level 1 default display, verbose/detail paths, source evidence visibility, and empty/missing data behavior. |

## Retest Rules

- When a failed item is fixed, change status to `needs_retest` before retesting.
- When retest passes, change status to `passed` and record evidence.
- When retest still fails, keep `failed` and append the new evidence.
- Do not delete failed rows after a fix; preserve history and add a new row only when the feature surface or acceptance scope materially changes.
