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
| AT-2026-06-28-001 | Weekly review content quality and source completeness | `http://47.84.190.191:8010/weekly-review` | failed | major | User acceptance feedback on 2026-06-28 SGT after reviewing the deployed Weekly Review page. Product acceptance criteria added to `docs/product/PRD-每周复盘.md` on 2026-06-28. Development branch `origin/codex/weekly-review-source-completeness` at `ce36764` was integrated into `main` through `8147cb8`; follow-up cloud-source branch `origin/codex/weekly-review-cloud-sources` at `31aa130` was integrated through `9381a1a`; automatic quick deploy run `28326901616` and manual full deploy run `28326950490` both succeeded. Coordinator cloud force-refresh for week `2026-06-22` succeeded and saved evidence at `/private/tmp/weekly-review-cloud-refresh-20260622.json`. Acceptance retest branch `origin/codex/weekly-review-acceptance-retest-20260628` at `c32ba3f` returned failed/major on 2026-06-28 23:38 SGT with evidence at `/private/tmp/weekly-review-acceptance-retest-20260628.json`, raw API JSON at `/private/tmp/weekly-review-acceptance-read-20260628.json`, cloud HTML at `/private/tmp/weekly-review-acceptance-page-20260628.html`, and headers at `/private/tmp/weekly-review-acceptance-api-headers-20260628.txt` plus `/private/tmp/weekly-review-acceptance-headers-20260628.txt`. Development branch `codex/weekly-review-dated-events` adds a Yahoo Finance RSS dated company/theme news provider and passed local fixture plus live-provider smoke, but cloud deploy/force-refresh evidence is not yet recorded. | Retest failed for product story quality/source completeness. Passing checks: cloud page and API returned `200 OK`; week `2026-06-22` read as an existing report; old fixed missing-source/internal copy was absent; `source_status.indexes.status=partial` with Yahoo chart fallback, 7 index rows, no uncovered active markets, and visible missing `ChiNext Index`/`STAR 50`; story included `mainline`, `market_environment`, `portfolio_attribution`, `event_evidence`, `negative_signals`, `portfolio_relation`, `next_validation`, and 5 cited claims. Blocking gap before the dated-event fix: `event_summary[]` was populated by company disclosure reference/search URLs with no dated `published_at` company events, while `dated_company_events`, `macro_calendar`, and `general_news_theme_feed` remained blocked. | Keep this row `failed` until Coordinator/Ops integrates and deploys `codex/weekly-review-dated-events`, force-refreshes week `2026-06-22`, and confirms cloud `event_summary[]` contains at least one dated company/theme/macro event with `published_at` or event date, title/description, URL or source id, linked ticker/theme, and story claim citation. Then move to `needs_retest`; do not ask for user acceptance while this row is failed unless the known gap is explicitly accepted out of scope by the user. |
| AT-2026-06-25-002 | Command Workbench | `http://47.84.190.191:8010/command` | pending | major | Feature registry says deployed and user acceptance is pending. | Independent user-facing acceptance has not been run in this queue. | Run black-box acceptance against the cloud URL with representative commands, preview/execute flows, unsupported actions, auth behavior, and screenshot evidence. |
| AT-2026-06-25-003 | Research display Level 1 decision card | Default stock analysis display | pending | major | Feature registry says deployed, deploy verified, and user acceptance pending. | Independent user-facing acceptance has not been run in this queue. | Identify the user surface and run acceptance against the Level 1 default display, verbose/detail paths, source evidence visibility, and empty/missing data behavior. |

## Retest Rules

- When a failed item is fixed, change status to `needs_retest` before retesting.
- When retest passes, change status to `passed` and record evidence.
- When retest still fails, keep `failed` and append the new evidence.
- Do not delete failed rows after a fix; preserve history and add a new row only when the feature surface or acceptance scope materially changes.
