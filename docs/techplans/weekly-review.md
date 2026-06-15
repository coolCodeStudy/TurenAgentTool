# Task Plan: Weekly Review Generator

## Background

`docs/product/PRD-每周复盘.md` defines the weekly review product: when the user requests a weekly review, the system generates readable weekly review Markdown.

The system already has Futu historical trades and realtime positions, plus `trade_records`, `account_snapshots`, the knowledge base, user insights, Hong Kong IPO data, portfolio analysis, and command routing. The gap is not reconnecting Futu. The gap is turning these connected data sources into stable review data assets and using daily snapshots for weekly attribution.

## Product Methodology

P1 does not aim for a strict complete realized-P/L ledger. The first weekly review uses daily holding snapshot deltas as the main ledger:

```text
weekly stock performance = ending holding pl_val - beginning holding pl_val
```

Trade records are the explanatory ledger:

- Why `qty` changed.
- Why `cost_price` changed.
- Whether the week included add, trim, open, or close actions.
- Future foundation for execution review and realized P/L.

P1 methodology:

```text
Main performance ledger: account_snapshots
Trade explanation ledger: trade_records
Futu realtime API: used for gaps and same-day freshness, not as the only historical source
```

## Current State

Existing capabilities:

- `get_futu_trade_history(start, end)`.
- `get_futu_positions()`.
- `trade_records` table and `repository.upsert_trade_records()`.
- `account_snapshots` table and daily `account-snapshot-scheduler`.
- `portfolio_analysis.py` for holding normalization, currency grouping, P/L sorting, and knowledge-base matching.
- `command_router.py` entrypoints for trade review, return estimate, holdings analysis, IPO, and related commands.

Current gaps:

- Daily account snapshot calls `get_futu_trade_history(today, today)` but does not persist `deals` into `trade_records`.
- The current database may lack historical `account_snapshots` and `trade_records`; it may need backfill or gradual accumulation.
- `review_reports` is still closer to daily summary and lacks structured weekly-review fields.
- Index API and external event sources are deferred and should not block P1.

## P1 Data Collection Loop

Modify `investment_knowledge_mcp/account_snapshots.py` `run_account_snapshot_once()`:

```text
daily account snapshot task
  -> get_futu_trade_history(today, today)
  -> upsert_trade_records(trade_snapshot.deals)
  -> get_futu_positions()
  -> upsert_account_snapshot(account_info, positions, fx_rates)
```

Record trade sync result in metadata:

```python
metadata={
    "task": "daily_account_snapshot",
    "account_error": trade_snapshot.account_error,
    "position_count": len(position_snapshot.positions),
    "trade_count": len(trade_snapshot.deals),
    "trade_synced_count": trade_result["synced_count"],
}
```

This is required for P1. Weekly review can mainly depend on snapshots, but without daily trades in the database it cannot explain position changes or support later trade-execution review.

## New Module

Add:

```text
investment_knowledge_mcp/weekly_review.py
```

Core functions:

```python
build_weekly_review_context(start: date, end: date) -> dict
render_weekly_review_markdown(context: dict) -> str
```

Later optional model layer:

```python
generate_weekly_review_with_openai(context: dict) -> str | None
```

Design principles:

- `weekly_review.py` is an application-service aggregation layer. Do not keep adding logic to `command_router.py`.
- All calculation first produces structured context, then renders Markdown.
- The model can summarize from structured context only. It must not invent market data, news, or trade conclusions.

## Weekly Review Flow

```text
User input: 本周复盘

1. Parse date range, defaulting to Monday through today.
2. Read beginning and ending/latest snapshots from account_snapshots.
3. Read this week's trades from trade_records.
4. If trade_records are missing, use get_futu_trade_history(start, end) to backfill.
5. If today's snapshot is missing and end date includes today, fetch realtime positions as reference.
6. Calculate each stock's pl_val_delta, qty_delta, cost_price_delta, and market_val_delta.
7. Generate highlights, blowups, and current holdings analysis table.
8. Merge knowledge base, sectors, user insights, and candidate insights.
9. Mark indexes and external events as not connected.
10. Render Markdown.
11. Save `review_reports` or an artifact.
```

## Context Structure

Suggested internal structure:

```python
{
    "period": {
        "start": "2026-06-08",
        "end": "2026-06-14",
        "label": "2026-06-08 to 2026-06-14",
    },
    "source_status": {
        "account_snapshots": {"status": "ok|partial|missing", "count": 0},
        "trades": {"status": "ok|backfilled|missing", "count": 0},
        "positions": {"status": "ok|fallback|missing", "fetched_at": None},
        "indexes": {"status": "missing", "reason": "index provider not configured"},
        "events": {"status": "missing", "reason": "external event provider not implemented"},
        "ipo": {"status": "ok|missing", "count": 0},
    },
    "position_changes": [],
    "highlights": [],
    "blowups": [],
    "holdings_table": [],
    "trades": {
        "records": [],
        "by_symbol": [],
    },
    "next_week": [],
    "story": {},
    "candidate_insights": [],
}
```

## Per-Stock Methodology

Compare beginning and ending rows for the same `code`:

```text
pl_val_delta = end.pl_val - start.pl_val
qty_delta = end.qty - start.qty
cost_price_delta = end.cost_price - start.cost_price
market_val_delta = end.market_val - start.market_val
```

Position-change labels:

```text
qty unchanged: unchanged holding
qty increased: added
qty decreased: trimmed
missing at start, present at end: opened
present at start, missing at end: closed
```

Confidence:

- High: quantity is basically unchanged, so `pl_val_delta` can represent weekly holding performance reasonably well.
- Medium: quantity changed, but beginning and ending holdings exist, so direction is still useful.
- Low: opened or closed; describe position change and current/ending result, not pure price contribution.

If adds or trims happened during the week, `pl_val_delta` includes position-adjustment effects and must not be described as pure price contribution.

## Highlights And Blowups

Highlights: sort by `pl_val_delta` descending and take top three.

Fields:

```text
security | type | weekly P/L change | position change | confidence | review question
```

Blowups: sort by `pl_val_delta` ascending and take top three.

Fields:

```text
security | type | weekly P/L change | position change | confidence | next-week handling
```

## Persistence

Save weekly reports to `review_reports` with:

- `report_type = weekly`
- `period_start`
- `period_end`
- `summary`
- `portfolio_snapshot`
- `source_status`
- `highlights`
- `blowups`
- `holdings_table`
- `next_week`
- `story`

## Acceptance Criteria

- `本周复盘` generates a six-section Markdown report.
- Daily account snapshot persists same-day trade records.
- The report uses snapshot deltas as the main ledger and trades as explanation.
- Missing index and external-event data is explicitly shown.
- The report can be saved.
- No formal user insights are created without confirmation.
