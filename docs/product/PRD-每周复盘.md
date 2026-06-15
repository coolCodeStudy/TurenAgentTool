# PRD: Weekly Review Generator

## One-Sentence Positioning

Generate a readable weekly review Markdown report from Futu trade records, account/holding snapshots, market indexes, IPO calendar, the knowledge base, and external information sources.

This product should not ask the user to write a review first and then polish it. The system should calculate what really happened during the week, while the user adds final subjective judgment.

## Target Output

User input:

```text
本周复盘
```

System output:

```text
# Weekly Review YYYY-MM-DD ~ YYYY-MM-DD

## 1. Highlights
## 2. Blowups
## 3. Indexes
## 4. Overall Story
## 5. Next Week Outlook
## 6. Current Holdings Analysis
```

The first version should make these six modules solid. It does not need a complex page.

## Data Sources

Existing sources:

- `trade_records`: historical Futu trades from `get_futu_trade_history` or trade-record backfill.
- `account_snapshots`: account, position, and FX snapshots.
- Realtime positions: `get_futu_positions` or MCP `get_realtime_portfolio_positions`.
- Knowledge base: stock profiles, sector links, knowledge items, user insights, candidate insights.
- Hong Kong IPO list: `get_hk_ipo_list`, useful for next-week outlook.

Sources to add or improve:

- Market indexes: weekly performance and key daily moves for US, A-share, and Hong Kong indexes.
- External events: Xueqiu, Twitter/X, earnings calendar, announcements, news, and research summaries.
- IPO calendar: Hong Kong is connected; later add A-share, US IPO, SPAC, and first-day data.
- Theme heat: aggregate themes such as AI, memory, optical communications, innovative drugs, robotics, and crypto finance from holdings, traded names, and watchlist names.

## Module Design

### 1. Highlights

Definition: the trades or holdings that made the most money or showed the best execution quality this week.

First-version methodology:

- Prefer realized gains from this week's sell trades in `trade_records`.
- If cost basis is incomplete, use current holding `realized_pl` or `pl_val` as supporting evidence.
- Show only the top three to avoid noise.

Output fields:

| Field | Meaning |
| --- | --- |
| Security | Symbol and name |
| Type | Realized gain, unrealized gain expansion, or post-buy rise |
| Amount | Original-currency gain or unrealized gain change |
| Trigger | Trade record, snapshot change, or model summary |
| Review question | Why did it work, and is it repeatable? |

### 2. Blowups

Definition: the trades or holdings that lost the most money or most deserve review this week.

First-version methodology:

- Prefer realized losses from this week's trades.
- Then compare beginning/end weekly snapshots for unrealized-loss expansion.
- If snapshots are insufficient, use current `pl_val` and `pl_ratio` to mark historical detractors, and explicitly state that they are not necessarily new weekly losses.

Output fields:

| Field | Meaning |
| --- | --- |
| Security | Symbol and name |
| Type | Realized loss, unrealized loss expansion, or historical drag |
| Amount | Original-currency loss or unrealized-loss change |
| Reason candidates | Entry timing, position size, theme failure, event shock, liquidity |
| Next-week handling | Observe, reduce candidate, wait for rebound, needs more research |

### 3. Indexes

Goal: use a small index basket to explain the week's market environment without generic market commentary.

First index basket:

| Market | Indexes |
| --- | --- |
| US | Nasdaq 100, S&P 500, SOX Semiconductor Index, Russell 2000 |
| Hong Kong | Hang Seng Index, Hang Seng Tech, HSCEI |
| A-share | CSI 300, ChiNext, STAR 50, semiconductor/communications indexes |

If index data is missing, the model must output that index data is missing. It must not invent data from memory.

### 4. Overall Story

This is the most valuable and riskiest module. It must not let the model free-write a story.

Generate the story in three layers:

1. Objective market layer: index moves, security moves, active trades, largest contributors and detractors.
2. Event and sentiment layer: announcements, earnings, Xueqiu/Twitter/X discussion, news, macro data, and this week's user notes.
3. Model narrative layer: synthesis only, never direct trading instructions.

Fixed output format:

```text
Weekly story:
- Main line:
- Accelerating factors:
- Negative signals:
- Relationship to my portfolio:
- Next-week validation points:
```

Rules:

- Cite at least two input categories, such as index, stock performance, events, trade records, or user insights.
- If data is missing, write that the week lacks external-event data.
- Always warn about crowded trades, overheated themes, and leveraged products when relevant.

### 5. Next Week Outlook

Goal: list a small number of items to handle next week, not predict the market.

Inputs:

- Hong Kong IPO list and subscription status.
- Earnings, corporate-event, and macro calendar.
- Current holdings with large losses, large profits, or large position sizes.
- Available cash and buying power after this week's trades.
- Candidate insights and historical user preferences.

Output fields:

| Field | Meaning |
| --- | --- |
| Type | IPO, earnings, holding action, theme watch, risk control |
| Item | Specific security, event, or action candidate |
| Why it matters | Relationship to portfolio or historical judgment |
| User decision needed | Yes or no |

### 6. Current Holdings Analysis

Goal: show the current portfolio state after the week.

Must include:

- Position list by market and currency.
- Profit/loss contribution in original currency.
- Theme and sector grouping.
- Concentration and liquidity risks.
- Positions that need next-week handling.
- Knowledge-base coverage and missing stock profiles.

## Saving And Knowledge Retention

When the review is saved:

- Store the final Markdown report.
- Store structured `portfolio_snapshot`, `source_status`, highlights, blowups, holdings table, story, and next-week items when available.
- Generate candidate insights only; do not promote them to formal user insights without confirmation.
- Preserve the user's edited Markdown as the formal review text.

## Non-Goals

- Do not build a full market-news product.
- Do not auto-generate trading orders.
- Do not infer external events when data is missing.
- Do not replace user judgment with model judgment.

## Acceptance Criteria

- The command can produce the six-module Markdown report for a selected week.
- Missing data is visible and not hidden.
- Highlights and blowups are traceable to trades, snapshots, or current holdings.
- The story cites available input categories and admits missing external data.
- The report can generate candidate insights without writing formal insights automatically.
- The output can be saved for later review.
