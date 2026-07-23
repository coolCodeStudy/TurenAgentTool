# Weekly Review Source Details Design

## Status

- Date: 2026-07-22
- Feature: Frontend experience system
- Owner authorization: autonomous delivery through implementation, deployment, and local-first acceptance.
- Scope: desktop `/weekly-review` only.

## Problem

The current-holdings table omits the already-computed weekly interval P&L, even though the generated report includes it. The seven source-status cards communicate availability but cannot explain what each source contributes, its coverage, or its limitations.

## Decisions

1. Add a `本周盈亏` column after `盈亏`, displaying the existing `weekly_pl_delta` value from each holdings row. It remains an interval estimate produced server-side from the established snapshot/trade logic; the browser does not recompute it.
2. A missing or non-numeric legacy weekly P&L displays `—`, never `0`.
3. Convert every source-status card into a keyboard-operable button that opens one reusable right-side native dialog drawer.
4. The drawer is populated only from the already-public `source_status` object. It shows an allowlisted set of source name, review period, status, count, selected provider/source, retrieved time, cache/coverage fields, source contribution, and plain-language limitations.
5. The Trades drawer renders individual selected-week trade records from a dedicated safe public view. Its fixed table shows only transaction date, buy/sell side, symbol/name, quantity, execution price, and execution amount. The public response and drawer exclude raw provider payloads, account snapshots, internal identifiers, internal provider errors, exception strings, configuration details, write actions, and new network requests.
6. The drawer closes through the visible close control, Escape, or modal backdrop behavior, and returns focus to its invoking source card.
7. Global highlights and blowups rank interval P&L in USD equivalent, never by mixed raw currency amounts. Each row retains its native-currency amount and shows the USD equivalent used for comparison. USD and HKD use the existing 1 USD = 7.80 HKD fallback when a historical snapshot rate is unavailable; unsupported currencies are not mixed into the global ranking.
8. The Trades card and drawer explicitly say `本复盘周` so their count is understood as the selected review period, not account-history total.

## Source Contribution Copy

| Source | Contribution shown in drawer |
| --- | --- |
| Trades | Supports realised interval P&L and position-change context. |
| Account snapshots | Compares start and end snapshots for interval P&L. |
| Current holdings | Supplies current market value and current P&L. |
| HK IPO | Supplies next-week subscription context. |
| Indexes | Supplies market-environment comparison. |
| External events | Supplies dated company/theme evidence. |
| Local knowledge | Supplies thesis, theme, and validation context. |

## Accessibility And Interaction

- Each card has an explicit accessible name ending in `查看数据详情` and `aria-haspopup="dialog"`.
- Opening moves focus into the dialog; closing restores focus to the source card.
- Only one dialog can be open and opening it does not read, generate, save, or alter the selected week.
- All user-visible values are escaped and unknown fields are ignored.

## Non-Goals

- Arbitrary historical broker-record export, raw provider payloads, source configuration, editable data, new endpoints, token or access-model changes, Daily/Command changes, and a mobile redesign. This slice visualizes only the selected week's already-public transaction records.
- Exact broker-statement reconciliation. The column retains the existing interval-estimate semantics.

## Acceptance Criteria

1. Populated holding rows show both current P&L and correctly signed, currency-formatted weekly P&L; missing legacy values show `—`.
2. Every source card opens the matching dialog via pointer or keyboard, with no additional API request.
3. The drawer renders complete, partial, missing, realtime, and cached/backfilled states in user language without exposing raw diagnostics.
4. Close button, Escape, and backdrop restore the source-card focus.
5. Existing public Weekly reads and protected generation recovery retain their access boundary; no token value is read, stored, or emitted.
6. Local Python regression tests and local Playwright against the deployed URL pass after one serialized `weekly-review-web` quick deployment.
7. Opening the Trades source drawer shows each available transaction in the selected review week in a readable, escaped table; an empty selected week says that there are no transaction records.
8. A USD gain of 500 ranks above a HKD gain of 1,800; the user sees both native values and their USD-comparison values.
