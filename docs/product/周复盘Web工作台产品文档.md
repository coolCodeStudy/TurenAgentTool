# Weekly Review Web Workbench Product Document

## 1. Background

DingTalk is useful for notifications, lightweight commands, and asynchronous reminders, but it is not the right surface for a full investment review.

Weekly review is not a single command. The user needs to inspect tables, data gaps, historical views, and candidate insights. A chat stream is linear and easy to collapse, truncate, or lose. Once trade records, holding snapshots, indexes, sentiment, IPOs, and the knowledge base are involved, the user needs a persistent workbench that can be read, edited, and confirmed.

DingTalk should remain a reminder and lightweight query entrypoint, but the first real product surface should move to Web.

## 2. Product Positioning

Working product name: InvestmentKnowledge Web Workbench.

One-sentence positioning:

> An investment review workbench built around real trades, real holdings, and personal investment memory.

First product: Weekly Review.

Later products should grow naturally from weekly review: holdings workbench, trade review, research queue, insight confirmation, historical validation, and investment calendar.

## 3. Product Principles

### 3.1 Facts Before Interpretation

The page shows real trades, real holdings, and real snapshots before model synthesis.

Highlights, blowups, and current holding analysis must come from data. The model must not fabricate them.

### 3.2 Data Gaps Must Be Visible

If indexes, Xueqiu, Twitter/X, announcements, earnings, or other external data sources are not connected, the page must show the gap.

The report must not invent market stories to look complete.

### 3.3 Review Is Not A News Feed

The product should not become an infinite news feed or daily information firehose.

Weekly review answers:

- What happened this week?
- Where did I make or lose money?
- Where is the portfolio currently risky?
- What should I watch next week?
- Which insights are worth preserving?

### 3.4 User Confirmation Creates Memory

The model may generate candidate insights, but cannot write formal user insights directly.

The web page must provide explicit confirm, reject, and later actions.

### 3.5 Weekly Review Is The Main Entry

Do not scatter the first phase across too many products.

Other modules may appear as navigation entries, but the main experience must be completing one high-quality weekly review.

## 4. Information Architecture

Suggested top-level products:

| Product | Role | Phase-One Status |
| --- | --- | --- |
| Weekly Review | Generate formal weekly review reports | P0 core |
| Holdings Workbench | Current holdings, theme exposure, risk, action queue | P1 |
| Trade Review | Period trades, profitable/loss-making trades, execution issues | P1 |
| Research Queue | Stock research jobs and audit status | P2 |
| Insight Confirmation | Confirm/reject candidate insights and maintain memory | P1 |
| Historical Review | Revisit whether past judgments were validated or falsified | P2 |

First-version left navigation:

```text
InvestmentKnowledge

- Weekly Review
- Current Holdings
- Trade Review
- Insight Confirmation
- Research Queue
- Historical Reviews
- Data Source Status
```

The first version should go deep on Weekly Review.

## 5. Weekly Review Product Goals

### 5.1 User Goals

Within ten minutes each week, the user should be able to:

- Understand this week's profit and loss sources.
- See the portfolio risks that most need handling.
- See IPOs, events, earnings, and holding actions to watch next week.
- Confirm a small number of insights worth preserving.
- Generate a review report that can be revisited later.

### 5.2 Product Goals

The weekly review page should automatically generate 80% of the content from data. The user contributes the final 20% of subjective judgment.

The system is responsible for:

- Reading trade records.
- Reading account and holding snapshots.
- Reading current holdings.
- Reading the IPO calendar.
- Reading the knowledge base and insights.
- Marking data gaps.
- Generating a structured review draft.

The user is responsible for:

- Judging whether the story is valid.
- Editing next-week outlook.
- Confirming candidate insights.
- Deciding whether to save the formal report.

## 6. Page Structure

### 6.1 Header

The top area shows:

| Element | Meaning |
| --- | --- |
| Date range | Defaults to Monday through today; editable |
| Generation status | Not generated, generating, generated, incomplete data |
| Data freshness | Trade records, holdings, account snapshots, IPOs, indexes, external events |
| Primary actions | Generate review, refresh data, save report |

Example status line:

```text
Trade records: 93 records loaded
Holding snapshots: 30 holdings loaded
Account snapshots: today loaded, beginning-of-week snapshot missing
Hong Kong IPOs: 5 loaded
Indexes: not connected
External events: not connected
```

This status line is critical because it prevents the user from over-trusting incomplete reports.

### 6.2 Review Table Of Contents

The weekly review has six fixed modules:

```text
1. Highlights
2. Blowups
3. Indexes
4. Overall Story
5. Next Week Outlook
6. Current Holdings Analysis
```

A right-side anchor navigation may help users jump between modules.

## 7. Module Design

### 7.1 Highlights

User-language definition: trades that made meaningful money this week.

Product definition: the largest positive contributors or highest-quality execution cases during the week.

Data priority:

1. Realized gains from this week's trades.
2. Weekly unrealized gain changes from snapshots.
3. Current cumulative unrealized gains.

If only current cumulative profit/loss is available, the page must label it as cumulative and not necessarily a weekly gain.

User actions:

- Mark as worth reviewing.
- Write a personal explanation.
- Generate a candidate insight.

### 7.2 Blowups

User-language definition: trades that lost meaningful money this week.

Product definition: the largest negative contributors or cases that most deserve reflection.

Data priority:

1. Realized losses from this week's trades.
2. Weekly unrealized-loss expansion from snapshots.
3. Current cumulative unrealized losses.

If only current cumulative loss is available, the page must label it as historical drag and not necessarily a weekly loss.

User actions:

- Mark as needs action.
- Add a handling note.
- Create a candidate insight or next-week action item.

### 7.3 Indexes

Goal: explain the market backdrop with a compact index basket.

The module should show:

- Weekly move.
- Largest daily move.
- Relationship to portfolio themes.
- Missing-data status when no index provider is connected.

No index data means the page must say "not connected" or "missing"; it must not let the model invent market moves.

### 7.4 Overall Story

Goal: summarize the week using facts first and model synthesis second.

Required inputs:

- Index movements if available.
- Security/holding movements.
- Trade records.
- Largest contributors and detractors.
- External events if available.
- User notes, insights, and candidate insights.

Output structure:

```text
Weekly story
- Main line:
- Supporting facts:
- Negative signals:
- Relationship to my portfolio:
- Next-week validation points:
```

Rules:

- Cite the available input categories.
- Admit missing external events.
- Warn about theme crowding and leveraged products when relevant.
- Do not produce direct trading instructions.

### 7.5 Next Week Outlook

Goal: list the few items the user should handle next week.

Inputs:

- Hong Kong IPO list.
- Earnings and macro calendar when connected.
- Large winners, losers, and concentrated positions.
- Cash and buying power.
- Candidate insights and historical preferences.

Output fields:

| Field | Meaning |
| --- | --- |
| Type | IPO, earnings, holding action, theme watch, risk control |
| Item | Specific security, event, or candidate action |
| Why it matters | Relationship to portfolio or historical judgment |
| User decision needed | Yes or no |

### 7.6 Current Holdings Analysis

Goal: show what the portfolio looks like after this week.

Must show:

- Current holdings by market and currency.
- Profit/loss in original currency.
- Theme grouping.
- Concentration and leverage risk.
- Positions needing attention.
- Knowledge coverage and missing profiles.

## 8. Candidate Insight Confirmation

The page should make candidate insights visible and actionable.

Required actions:

- Confirm.
- Reject.
- Keep for later.
- Edit user wording before confirming when supported.

Confirmed insights become formal user memory. Rejected insights should remain rejected and not keep returning.

## 9. Save Behavior

Saving a weekly review should:

- Store the final Markdown after user edits.
- Store structured context where available.
- Preserve source status and data gaps.
- Keep candidate insights separate from formal insights unless confirmed.
- Make the saved report retrievable by period.

## 10. P0 Scope

P0 must include:

- Local web page for weekly review.
- Date range selection.
- Generate draft.
- Data-source status display.
- Six fixed review modules.
- Markdown draft editor.
- Save formal report.
- Candidate insight list with confirm/reject actions if available.

P0 does not include:

- Full login system.
- Complex charts.
- Full external-event crawler.
- Index provider if not already available.
- Mobile-optimized editing.
- Automatic trading or order generation.

## 11. Acceptance Criteria

- Opening the Web workbench shows Weekly Review as the first screen, not a marketing landing page.
- The user can select a date range and generate a draft.
- The page shows data source status and missing data.
- The six modules are present and populated from available data.
- The Markdown draft is editable and can be saved.
- Candidate insights can be reviewed without becoming formal insights automatically.
- Missing index or external event data is explicitly shown.

## 12. Product Direction

Recommended current direction:

1. Do not make DingTalk the main product interface.
2. Use Web as the primary weekly review workbench.
3. Keep DingTalk for reminders and lightweight queries.
4. Make weekly review the first deep product.
5. Keep other products as navigation and roadmap items until the weekly review loop is strong.

Open product questions:

- Should candidate insight confirmation live inside weekly review or become a separate page first?
- Should saved reports be Markdown-first, structured-data-first, or both?
- How much manual editing should be supported before the first production deployment?
