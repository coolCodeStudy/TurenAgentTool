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
| AT-2026-06-25-001 | Weekly review web | `http://47.84.190.191:8010/weekly-review` | failed | blocker | Retest by Acceptance Testing Agent on 2026-06-28 SGT against deployed commit `b3a228da2e120125a5f676b034f8e0b53711f226`. Health returned 200/`{"ok": true}`. `GET /weekly-review` returned 200 and HTML evidence is `/tmp/weekly-review-page.html`. API evidence: `/tmp/weekly-review-read.json`, `/tmp/weekly-review-generate.json`, `/tmp/weekly-review-refresh-no-force.json`, `/tmp/weekly-review-save-no-token.json`, `/tmp/weekly-review-refresh-force.json`, `/tmp/weekly-review-read-after-refresh.json`. Compact evidence summary: `/tmp/weekly-review-acceptance-retest-2026-06-28.json`. Browser screenshot tooling limit: initial in-app browser navigation timed out at the tool layer, so this retest used cloud HTML/API evidence. | Natural-week read/generate/refresh behavior passed: the page has week controls, previous/current week controls, token field, and separate Generate/Force refresh/Save actions; read normalized `2026-06-22` to `2026-W26` (`2026-06-22` through `2026-06-28`); generate existing returned `already_exists=true`; refresh without `force=true` returned HTTP 409 with product-language copy; force refresh returned `status=refreshed` and product-language source statuses (`指数数据源未接入`, `外部事件源未接入`) without the previous raw provider strings or raw database errors. Blockers: no `WEEKLY_REVIEW_WEB_TOKEN` or `COMMAND_API_TOKEN` was available in the acceptance environment, but unauthenticated `POST /api/weekly-review/save` returned `ok=true`, `status=saved`, and wrote `review_reports` id 14; the deployed save success copy still uses the internal table name format `已保存报告：review_reports #...`. Public unauthenticated writes and internal table-name user copy are not safe for user acceptance. | Development Agent should remove internal table-name copy from save success messaging; Development/Ops must also require or configure weekly-review write authentication on the public cloud surface, or explicitly split read-only public access from authenticated generate/refresh/save writes. After fixes are deployed, move this row back to `needs_retest` and rerun the same cloud acceptance journey. Do not ask for user acceptance while this row is `failed`. |
| AT-2026-06-25-002 | Command Workbench | `http://47.84.190.191:8010/command` | pending | major | Feature registry says deployed and user acceptance is pending. | Independent user-facing acceptance has not been run in this queue. | Run black-box acceptance against the cloud URL with representative commands, preview/execute flows, unsupported actions, auth behavior, and screenshot evidence. |
| AT-2026-06-25-003 | Research display Level 1 decision card | Default stock analysis display | pending | major | Feature registry says deployed, deploy verified, and user acceptance pending. | Independent user-facing acceptance has not been run in this queue. | Identify the user surface and run acceptance against the Level 1 default display, verbose/detail paths, source evidence visibility, and empty/missing data behavior. |

## Retest Rules

- When a failed item is fixed, change status to `needs_retest` before retesting.
- When retest passes, change status to `passed` and record evidence.
- When retest still fails, keep `failed` and append the new evidence.
- Do not delete failed rows after a fix; preserve history and add a new row only when the feature surface or acceptance scope materially changes.
