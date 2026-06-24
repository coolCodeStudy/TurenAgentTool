# Product Strategy and Roadmap

## Product Positioning

InvestmentKnowledge is not a generic investment notebook and it is not an automated trading system. Its long-term position is:

> A personal investment research, review, and memory operating system.

The system helps the user compound experience in the market over many years by connecting real holdings, investment journals, stock research, user insights, review reports, valuation frames, and later validation into a traceable and evolving personal investment knowledge base.

## Product Philosophy

The user's core philosophy:

> Investing is a long practice and a long accumulation process. The user wants to stay in the market for a long time, keep reviewing decisions, accumulate experience, and improve judgment over time.

The product should therefore optimize for long-term judgment quality, not daily information volume.

## North Star Metric

First-stage north star metric:

> Complete one high-quality, traceable, insight-generating weekly investment review each week.

Input metrics:

- Number of account snapshots saved per week.
- Number of raw user thoughts captured per week.
- Number of candidate insights generated per week.
- Number of candidate insights confirmed or rejected per week.
- Number of historical views referenced per week.

Quality metrics:

- Whether the weekly review explains the main sources of gains and losses.
- Whether the review identifies portfolio risk and attention cost.
- Whether the review references historical views.
- Whether the review generates useful candidate insights.
- Whether the user wants to continue using it the following week.

## User Journey

### Daily Capture

The user can capture:

- An investment thought.
- A market observation.
- An emotional reaction.
- A trade rationale.
- A historical journal entry.
- A stock, sector, or valuation question.

The system preserves the raw text. System-inferred opinions go into candidate insights first and do not become formal user insights without confirmation.

### Lightweight Daily Automation

The system runs lightweight daily tasks:

- Save account snapshots.
- Save holdings snapshots.
- Mark large gain/loss changes.
- Collect candidate weekly-review events.
- Avoid long daily reports by default.

The daily layer is low-noise and record-oriented.

### Formal Weekly Review

The system generates a weekly review:

- Weekly return overview.
- Main contributors and detractors.
- Holdings, currency, market, and theme exposure.
- Concentration and crowded-trade risk.
- What went right, what went wrong, what was missed, and where emotion interfered.
- Historical view validation or invalidation.
- New candidate insights.
- The 3-5 most important items to watch next week.

Weekly review is the core first-stage product ritual.

### Long-Term Recall

The user can return to any historical point and see:

- Holdings at that time.
- Raw journal entries at that time.
- Market views at that time.
- Whether later facts validated or challenged those views.
- Whether today's analysis conflicts with older preferences.

## Product Modules

### 1. Investment Journal Library

Goal: preserve the user's long-term logs and raw thoughts.

Key capabilities:

- Import Markdown, txt, chat logs, and document exports.
- Split by date, source, and topic.
- Preserve raw text without replacing it with summaries.
- Extract stock, sector, portfolio, strategy, and valuation targets.
- Generate candidate insights.

### 2. Weekly Review

Goal: create a stable investment-review ritual.

Key capabilities:

- Read account and holdings snapshots.
- Calculate gains, losses, contributors, detractors, and exposure.
- Reference new journal entries and insights from the week.
- Reference historical views.
- Generate candidate insights and next-week watch items.

### 3. Decision Cards

Goal: turn dense evidence into first-screen decision information.

Default fields:

- One-line thesis.
- Key drivers.
- Core risks.
- Watch items.
- Data freshness.
- Source and audit status.

Full sources, knowledge items, audit reports, and research drafts remain in the evidence layer and can be expanded when needed.

### 4. Stock Valuation Research

Goal: explain which valuation frames the market may be using for a stock and which assumptions could trigger rerating.

Key capabilities:

- Maintain a valuation method library.
- Output a stock-specific valuation method matrix.
- Reverse-engineer current market-implied assumptions.
- Identify rerating triggers and valuation failure conditions.
- Feed valuation frames into decision cards and weekly reviews.

### 5. Historical View Validation

Goal: help the user observe how judgment evolves.

Key capabilities:

- Record when a view was formed and what the market environment looked like.
- Detect whether later facts supported or challenged that view.
- Detect conflicts between current analysis and historical preferences.
- Build a long-term user investment style profile.

### 6. Research Task Pipeline

Goal: continuously fill the holdings graph and stock research base.

Key capabilities:

- Create research tasks for holdings.
- Show task status, failure reasons, and audit status.
- Keep default task display concise.
- Route confirmation needs into a clear confirmation queue.

### 7. Position Discipline Layer

Goal: help the user remember why each meaningful holding exists and whether current behavior still follows the original discipline.

Key capabilities:

- Preserve raw buying rationale separately from AI summaries.
- Maintain user-confirmed position discipline cards for material holdings.
- Track review dates, invalidation conditions, risk limits, add rules, reduce rules, and attention cost.
- Generate a small discipline review queue for missing contracts, stale theses, rule breaches, high-attention positions, and theme crowding.
- Feed discipline outcomes into portfolio analysis, weekly review, and candidate insights.

## Roadmap

### P0: Product Foundation

- Maintain product documentation under `docs/product/`.
- Define the north star metric and product principles.
- Maintain the Product Agent working protocol.
- Separate product roadmap from technical implementation plans.

### P1: Weekly Review MVP

- Save account snapshots daily.
- Generate weekly review Markdown.
- Support the `weekly review` command.
- Save review reports as artifacts or database records.
- Generate candidate insights from weekly reviews.

### P2: Investment Journal Import

- Import historical journal files.
- Preserve raw text.
- Split by date.
- Generate candidate insights.
- Support confirmation, rejection, and merge workflows.

### P3: Decision Cards and Valuation Frames

- Show Level 1 decision cards by default for stocks.
- Keep research task lists concise by default.
- Support explicit evidence expansion.
- Add valuation frame, rerating trigger, and valuation risk fields.

### P3.5: Position Discipline Layer

- Add position discipline cards for material holdings.
- Add a concise discipline queue.
- Add discipline state to portfolio analysis.
- Add discipline checks to weekly review.
- Keep AI-generated discipline drafts pending until user confirmation.

### P4: Long-Term Memory and Validation

- Retrieve historical views.
- Detect conflicts.
- Mark views as validated or challenged.
- Build a user investment style profile.

## Product Principles

- Always preserve raw text.
- Separate facts, user opinions, and model inference.
- Only user-confirmed opinions become formal user insights.
- Default display should support decision-making, not maximize information volume.
- Evidence must remain traceable.
- Weekly review comes before long daily reports.
- Valuation explanation comes before target price.
- The product should be able to run for ten years, not just answer one question.
