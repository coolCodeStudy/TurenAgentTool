# Weekly Material Drag Design

## Status

- Date: 2026-07-26
- Feature: Frontend experience system / Weekly Review
- Owner authorization: autonomous diagnosis, implementation, deployment, and acceptance preparation.

## Problem and Evidence

The public Weekly Review labels the three most-negative weekly position changes as `炸裂时刻`, even when the selected week contains only immaterial ordinary movements. For the 2026-07-20 to 2026-07-26 review, the displayed rows included losses equivalent to only a few US dollars.

The interval P&L and USD-normalised ranking are working for those rows. The defect is semantic: `_top_blowups` accepts every negative ranking amount, so any negative number becomes an exceptional event when no larger loss is available. This is not a currency-conversion, OOM, deployment, or data-loss finding.

## Decision

1. Rename the user-facing section from `炸裂时刻` to `显著拖累`, in both the Web workbench and exported Markdown.
2. A row is eligible only when its interval loss is at least 50 USD equivalent **and**, when an opening market value exists, at least 1% of that opening position value. The ratio makes a small percentage movement in a large holding non-exceptional; the amount floor prevents tiny positions from producing a dramatic label. A fully exited or newly tracked position without an opening valuation may qualify from the 50 USD floor alone so a material realised loss is not hidden.
3. When nothing qualifies, show the explicit empty state: `本周无显著拖累。轻微波动已保留在当前持仓的本周盈亏中。`
4. Keep all ordinary positive/negative interval P&L visible in the existing current-holdings table. Do not change the source data, broker reconciliation, ranking FX table, public access boundary, or Daily/Command journeys.

## Acceptance Criteria

1. A -8.83 USD change and a -36 HKD change on a normal opening position do not appear in `blowups`/`显著拖累`.
2. A loss meeting both the USD and relative-impact gates remains ranked, cross-currency comparable, and includes the existing review question.
3. A material loss without an opening valuation remains visible when it passes the USD floor.
4. Public Web and Markdown output contain no `炸裂时刻` label and give an actionable empty-state explanation.
5. The deployed tokenless Weekly API/Web flow stays read-only; local Playwright production regression and focused Python tests pass.

## Non-Goals

- Introducing a new risk score, changing data providers, editing historic trade records, or redesigning mobile.
- Treating all negative P&L as a failure or automatically recommending a trade.
