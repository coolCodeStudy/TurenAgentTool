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
| AT-2026-06-25-001 | Weekly review web | `http://47.84.190.191:8010/weekly-review` | passed | note | Original failed retest by Acceptance Testing Agent on 2026-06-25 20:20-20:24 SGT. Original browser screenshots: `/tmp/weekly-review-desktop-initial.png`, `/tmp/weekly-review-desktop-generated.png`, `/tmp/weekly-review-desktop-save.png`, `/tmp/weekly-review-desktop-holdings.png`, `/tmp/weekly-review-mobile-generated.png`; original evidence JSON: `/tmp/weekly-review-acceptance-browser.json`. Development fix was merged to `main` and deployed by GitHub Actions run `28295470409`; follow-up copy hotfix was deployed by run `28295682296` at commit `2b376b7`. Retest evidence: `/tmp/weekly-review-acceptance-retest-20260628-v2.json` and `/tmp/weekly-review-acceptance-generate-20260628.json`. Browser screenshot capture was limited by in-app browser timeout, so final evidence used cloud HTML/API checks. Side effects: created or updated test-week reports for `1999-01-04` and `1999-01-11`. | Passed 2026-06-28 SGT for Web flow, natural-week behavior, persistence, and safe degraded copy only. Cloud HTML exposes natural-week controls and read/generate/force-refresh/save endpoints. Read, generate-missing-week, force-refresh confirmation failure, empty-save validation, save persistence, and read-back all returned expected product behavior. Responses no longer expose `index provider not configured`, `external event provider not implemented`, `review_reports`, raw DB constraint text, or tracebacks; degraded source states display product-language messages. | User acceptance remains pending for this Web-flow scope; source completeness and story quality are tracked by failed item `AT-2026-06-28-001`. |
| AT-2026-06-28-001 | Weekly review content quality and source completeness | `http://47.84.190.191:8010/weekly-review` | failed | major | User acceptance feedback on 2026-06-28 SGT after reviewing the deployed Weekly Review page. Product acceptance criteria added to `docs/product/PRD-每周复盘.md` on 2026-06-28. | The page still shows missing index and external-event sources, and the overall story is too thin because it is mainly derived from holding snapshot changes. The generated story explicitly says external events are not connected and that index/external-event context is unavailable, so the review is not yet product-acceptable even though the Web flow, persistence, and safe error handling passed in `AT-2026-06-25-001`. | Engineering must update `docs/techplans/weekly-review.md` for source providers, fallback/source-status semantics, story inputs, verification, and acceptance criteria before implementation; after deploy, run a focused acceptance retest for source completeness and story quality. |
| AT-2026-06-25-002 | Command Workbench | `http://47.84.190.191:8010/command` | pending | major | Feature registry says deployed and user acceptance is pending. | Independent user-facing acceptance has not been run in this queue. | Run black-box acceptance against the cloud URL with representative commands, preview/execute flows, unsupported actions, auth behavior, and screenshot evidence. |
| AT-2026-06-25-003 | Research display Level 1 decision card | Default stock analysis display | pending | major | Feature registry says deployed, deploy verified, and user acceptance pending. | Independent user-facing acceptance has not been run in this queue. | Identify the user surface and run acceptance against the Level 1 default display, verbose/detail paths, source evidence visibility, and empty/missing data behavior. |

## Retest Rules

- When a failed item is fixed, change status to `needs_retest` before retesting.
- When retest passes, change status to `passed` and record evidence.
- When retest still fails, keep `failed` and append the new evidence.
- Do not delete failed rows after a fix; preserve history and add a new row only when the feature surface or acceptance scope materially changes.
