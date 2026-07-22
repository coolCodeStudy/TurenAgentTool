# Weekly source details — Task 1 report

## Status

Completed the test-only RED phase. No production renderer code was edited and no real report was generated.

## Commit

`438e51fe386952919509e2515b2eaccac300a8aa` — `test: lock Weekly source detail contracts`

## Changed files in the commit

- `tests/test_weekly_review_web_auth.py`
  - Adds the renderer contract for the dialog shell, interactive source-card attributes, weekly P&L field/label, and the public/tokenless no-extra-endpoint boundary.
- `e2e/cloud-pages.spec.ts`
  - Adds the public `GET /api/weekly-review` fixture journey with positive, negative, and legacy holdings; source-detail data; no-second-read assertion; and Escape/close focus restoration checks.

## RED evidence

### Renderer contract

Command:

```bash
.venv/bin/python -m unittest tests.test_weekly_review_web_auth.WeeklyReviewWebAuthorizationTests.test_weekly_source_cards_have_safe_detail_dialog_contract -v
```

Result: **FAIL** as intended. The assertion for `id="source-detail-dialog"` failed because the current Weekly HTML has no dialog shell.

Note: the first sandboxed attempt could not bind the test's loopback HTTP server (`PermissionError: [Errno 1] Operation not permitted`); the same command was rerun with approved loopback access and produced the intended assertion failure above.

### Browser journey

Command:

```bash
npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public --grep "Weekly source detail drawer"
```

Result: **FAIL** as intended. The fixture-backed journey failed at the first contract assertion: the current holdings table text was `市场 标的 主题 市值 盈亏 状态 知识库观点 下周节奏`, which lacks `本周盈亏` and the weekly P&L values.

The browser run used only a local `127.0.0.1:8010` Weekly renderer for the page shell. The test routed its one public Weekly GET response, so no real Weekly report was read or generated. The renderer was stopped immediately after the run.

## Concerns and implementation handoff

- The browser fixture deliberately includes `provider_errors: ["raw-provider-diagnostic-marker"]`; the future drawer implementation must allowlist source-status fields so that marker never appears.
- The legacy holding lacks `weekly_pl_delta`; implementation must render `—`, not a false zero.
- The dialog must restore focus for both Escape and its close button without issuing another Weekly-read request.
- This report was written after the test-only commit as requested and is intentionally not part of that commit.

## Coverage review follow-up

The Task 1 browser fixture was strengthened without changing production renderer code.

- The raw provider diagnostic marker is now asserted absent from the complete page body, in addition to the source-detail dialog.
- The routed public Weekly request records the `Authorization` header and asserts it is absent.
- The source-status card now requires `role="button"`, `tabindex="0"`, and `aria-haspopup="dialog"`; the journey opens it with Enter, closes it with Escape, reopens it with Space, then closes it with the dialog close button.
- The test asserts that the public Weekly GET count remains exactly one after each close lifecycle, covering both Escape and the close button.

### Follow-up RED evidence

Renderer command:

```bash
.venv/bin/python -m unittest tests.test_weekly_review_web_auth.WeeklyReviewWebAuthorizationTests.test_weekly_source_cards_have_safe_detail_dialog_contract -v
```

Result: **FAIL** as intended at `id="source-detail-dialog"`; the current rendered HTML has no dialog shell. The first sandboxed execution could not bind the loopback test server, so the same local-only command was rerun with loopback permission.

Browser command:

```bash
npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public --grep "Weekly source detail drawer"
```

Result: **FAIL** as intended at the existing missing `本周盈亏` assertion. The current holdings text contains only `市场 标的 主题 市值 盈亏 状态 知识库观点 下周节奏`; therefore the new semantic, activation, public-header, whole-page diagnostic, and post-close request-count assertions remain RED behind the primary missing feature contract.

The browser test used only a local `weekly-review-web` page shell on `127.0.0.1:8010`, connected to the preflight local database target (`localhost:55432`). Its sole `/api/weekly-review` response was fulfilled by Playwright, so no real Weekly report was read or generated. The local shell was stopped after verification.

## P1 coverage completion

The same public fixture journey now also exercises the remaining populated and blocked source states without changing production renderer code.

- It opens the `trades` card, asserts the user-visible `3` record count and the defined contribution copy (`Supports realised interval P&L and position-change context.`), then closes through the visible control and verifies focus returns to the `trades` card.
- It opens the `events` card with Space, asserts the user-visible blocked reason `External events are unavailable`, then closes with Escape and verifies focus returns to the `events` card.
- Both additional lifecycle checks retain the tokenless public GET assertion, exactly one Weekly-read request, and whole-page raw-diagnostic absence established above.

### P1 focused RED evidence

Command:

```bash
npx playwright test e2e/cloud-pages.spec.ts --project=desktop-public --grep "Weekly source detail drawer"
```

Result: **FAIL** as intended at the pre-existing `本周盈亏` assertion. The rendered holdings text remains `市场标的主题市值盈亏状态知识库观点下周节奏`, so the task stays RED for the missing production feature before any dialog assertions run. The local `weekly-review-web` shell was started only on `127.0.0.1:8010`; Playwright fulfilled the one `/api/weekly-review` fixture response, and the shell was stopped immediately afterwards. No real Weekly report was read or generated.
