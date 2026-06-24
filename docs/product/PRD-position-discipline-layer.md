# PRD: Position Discipline Layer

## 1. Background

InvestmentKnowledge is positioned as a personal investment research, review, and memory operating system. It already has several important pieces:

- Real-time Futu position reading.
- Portfolio analysis through `持仓分析` / `今天仓位怎么看`.
- Weekly review generation.
- Stock research decision cards.
- User insights and candidate insight confirmation.

The current gap is not company research volume. The user can hold many positions across markets, themes, and volatility profiles, then later forget:

- Why a position was originally bought.
- What would prove the original thesis wrong.
- What risk limit, stop-loss rule, or review discipline was intended.
- Whether adding to a losing or high-volatility position is still consistent with the original plan.
- Which positions are consuming too much attention relative to their portfolio value.

During product discovery on 2026-06-24, the live portfolio contained roughly thirty positions across U.S. and Hong Kong markets, including AI infrastructure, semiconductors, memory, optical components, space, quantum, crypto/stablecoin, biotech/medical, consumer, and leveraged exposure. This portfolio shape makes the problem concrete: the user's bottleneck is no longer only information access, but decision-memory and discipline execution.

## 2. Product Decision

This should not be a separate product.

It should be built as the **Position Discipline Layer** inside InvestmentKnowledge.

Reason:

- The problem is a direct extension of the current product promise: long-term investment memory, review, and judgment improvement.
- A separate product would split holdings, research cards, user insights, weekly reviews, and discipline records across different systems.
- The highest value comes from connecting trade rationale, current holdings, historical user views, stock research, and weekly review outcomes in one memory graph.

The user-facing module may have its own entry point, such as `纪律队列`, `持仓契约`, or `Discipline`, but it should remain part of the same product, database, command surface, and weekly review loop.

## 3. Design References

This PRD incorporates agent-design and human-in-the-loop guidance from:

- Anthropic, [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents): start with simple, composable workflows; add agentic autonomy only when it improves outcomes; make agent planning and tool interfaces transparent.
- OpenAI, [Safety best practices](https://developers.openai.com/api/docs/guides/safety-best-practices): use human oversight in high-stakes domains, show original source material for verification, and test for adversarial or off-track behavior.
- LangChain, [Memory overview](https://docs.langchain.com/oss/python/concepts/memory): distinguish semantic, episodic, and procedural memory rather than treating all memory as one mutable summary.
- LangGraph, [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts): use explicit pause-and-resume checkpoints for human approval, review, editing, and validation.

## 4. Best-Practice Design Principles

This feature should apply agent and human-in-the-loop best practices:

- Start with a predictable workflow before adding autonomous behavior. Position discipline is better modeled as a state machine and review queue than as a free-running investment agent.
- Preserve raw user text. The user's original buying rationale must remain inspectable and must not be overwritten by AI summaries.
- Separate model inference from confirmed user intent. AI may draft a contract or detect a possible breach, but confirmed discipline rules require user approval.
- Use explicit checkpoints for high-stakes actions. The system may remind, flag, summarize, or ask for confirmation; it must not automatically trade.
- Show reasons for alerts. A discipline alert must state which rule, threshold, date, or missing field caused it.
- Optimize for low-noise review. The user needs a small queue of actionable items, not another long daily report.

## 5. User Problem

The user is an active investor with a growing portfolio and a long-term goal of improving judgment through review.

The user needs help answering:

- Which positions have no remembered buying rationale?
- Which positions have a thesis that is stale, contradicted, or untested?
- Which positions have triggered a stop-loss, review, or risk threshold?
- Which positions are high attention-cost and should not be allowed to drift unmanaged?
- Which portfolio themes are becoming crowded relative to the user's own discipline?
- Which current actions would violate a previously confirmed rule?

The painful failure mode is not merely losing money. It is losing the link between the decision made in the past and the discipline needed today.

## 6. Product Goals

1. Create a traceable "contract" for each meaningful holding that records why the user owns it and what would make the user reconsider it.
2. Convert missing, stale, or breached discipline into a small review queue.
3. Integrate discipline checks into existing portfolio analysis and weekly review.
4. Preserve raw rationale, AI-generated drafts, and user-confirmed rules separately.
5. Reduce attention overload by measuring and surfacing position attention cost.
6. Support theme-level discipline for crowded or highly correlated exposures.
7. Keep the product advisory and reflective, not executional.

## 7. Non-Goals

- Do not build automated trading, automatic stop-loss execution, or broker-side order placement.
- Do not provide personalized buy/sell orders as final decisions.
- Do not treat model-generated rules as user-confirmed rules.
- Do not force every tiny position to complete a long form before it can be tracked.
- Do not create a separate standalone product, database, or app.
- Do not replace weekly review; discipline should feed the weekly ritual.
- Do not create long daily reports by default.

## 8. Target User Behavior

The desired behavior change:

- When opening or increasing a position, the user writes or confirms the reason and discipline while the decision is fresh.
- When a position drifts, loses money, becomes too large, or grows stale, the user sees a short prompt to review it.
- During weekly review, the user can quickly see which positions followed the plan and which ones need a decision.
- Over time, the user builds a record of which kinds of discipline rules were useful, ignored, or poorly specified.

## 9. Core User Flows

### 9.1 New Or Increased Position Contract

```text
Position appears or quantity increases
-> system detects missing or stale contract
-> AI drafts a discipline card from current research, holdings, and user context
-> user reviews and edits the card
-> confirmed contract becomes active
-> next review date and monitoring triggers are scheduled
```

Required user-facing questions:

1. Why do I own this?
2. What would prove me wrong?
3. What is the expected holding period?
4. What is the maximum acceptable loss or risk condition?
5. What would justify adding more?
6. What would require reducing or exiting?
7. When must I review this again?

### 9.2 Discipline Review Queue

```text
Daily or on-demand portfolio check
-> evaluate all active holdings
-> detect missing contract, stale thesis, rule breach, high attention cost, or theme crowding
-> show only the highest-priority items
-> user confirms, edits, defers, or archives each item
```

Queue item examples:

```text
POET: new position, no confirmed contract.
AXTI: recent trading activity plus large historical drawdown; thesis needs re-signing.
PLTR: current loss exceeds default review threshold and no explicit loss discipline is confirmed.
HK.07709: leveraged exposure; review cadence should be short.
AI memory theme: multiple positions point to the same infrastructure theme; concentration rule needs confirmation.
```

### 9.3 Portfolio Analysis Integration

`持仓分析` should include discipline status, not only market value and P/L.

Example output column:

```text
市场 | 标的 | 主题 | 市值 | 当前盈亏 | 状态 | 纪律状态 | 下次动作
```

Discipline status examples:

- `missing_contract`
- `draft_pending_confirmation`
- `active`
- `review_due`
- `breach_triggered`
- `theme_crowding`
- `archived`

### 9.4 Weekly Review Integration

Weekly review should include a concise "Discipline Check" section:

- New contracts created this week.
- Positions that breached confirmed rules.
- Positions that were deferred without a decision.
- Positions whose thesis was validated or challenged.
- Theme-level concentration and attention-cost changes.
- Candidate insights generated from repeated behavior patterns.

### 9.5 Theme-Level Contract

Some risk lives above single stocks. The system should support optional theme-level discipline cards for themes such as:

- AI infrastructure.
- Memory and HBM.
- Semiconductor equipment.
- Optical components.
- Space.
- Quantum.
- Crypto and stablecoin infrastructure.
- Biotech or medical technology.

Theme contract fields:

- Why the theme deserves exposure.
- Maximum desired portfolio share.
- Maximum number of high-attention positions.
- What would invalidate the theme.
- What would indicate the trade is crowded.
- Which holdings belong to the theme.

## 10. Functional Scope

### 10.1 Position Discipline Card

Each material holding can have one active discipline card.

Core fields:

| Field | Purpose |
|---|---|
| `raw_rationale` | User's original text, preserved verbatim. |
| `summary_thesis` | User-confirmed structured thesis. |
| `position_type` | Core, tactical, event-driven, watch position, speculative, hedge, ETF, leveraged. |
| `expected_holding_period` | Days, weeks, months, years, or open-ended. |
| `review_cadence_days` | Required review interval. |
| `invalidation_conditions` | Facts or events that would prove the thesis wrong. |
| `risk_limit` | Loss, drawdown, position size, exposure, or event-based limit. |
| `add_rule` | Conditions for adding. |
| `reduce_rule` | Conditions for reducing or exiting. |
| `attention_cost` | Low, medium, high, or critical. |
| `source_status` | User-entered, AI-drafted, imported from journal, inferred from previous insight. |
| `confirmation_status` | Draft, confirmed, needs review, superseded, archived. |
| `next_review_at` | Next required review date. |

### 10.2 State Model

```text
missing_contract
-> draft_pending_confirmation
-> active
-> review_due
-> breach_triggered
-> needs_resign
-> active
-> archived
```

State rules:

- New active holdings without confirmed cards are `missing_contract`.
- AI-generated cards are `draft_pending_confirmation`.
- Confirmed cards are `active`.
- Cards past `next_review_at` are `review_due`.
- Cards with triggered risk or invalidation conditions are `breach_triggered`.
- Cards whose thesis materially changes after review are `needs_resign` until confirmed.
- Closed positions move to `archived` after final review.

### 10.3 Review Queue

The review queue should rank items by severity and actionability:

1. Confirmed rule breach.
2. Missing contract on large, new, or high-attention position.
3. Leveraged or speculative position without short review cadence.
4. Large loss without explicit invalidation or stop rule.
5. Theme concentration or attention overload.
6. Stale thesis past review date.
7. Low-value cleanup suggestions.

The queue should default to a short list, ideally three to seven items.

### 10.4 Attention Cost

Attention cost should be treated as a portfolio risk dimension.

Default heuristics:

- Low: broad ETF, mature cash-generating company, stable core holding.
- Medium: cyclical, growth, or single-name technology exposure.
- High: early-stage growth, biotech, space, quantum, crypto, new IPO, high valuation, turnaround.
- Critical: leveraged product, high-volatility theme with large position, or position with repeated rule breaches.

The system should allow the user to override attention cost.

### 10.5 AI Drafting

The agent may draft discipline cards using:

- Current position data.
- Stock decision card.
- Existing user insights.
- Sector and theme context.
- Recent review reports.
- User-provided raw text.

AI-drafted content must be visibly marked as a draft until user confirmation.

### 10.6 Candidate Insights

The system may propose candidate insights when repeated behavior appears:

- User repeatedly adds to high-volatility winners without a review cadence.
- User holds large losses without invalidation conditions.
- User over-concentrates in a crowded theme.
- User keeps speculative positions too long after the expected holding period.

Candidate insights must follow the existing confirmation workflow and must not become formal user memory without confirmation.

## 11. Entrypoints

### 11.1 Commands

Suggested commands:

```text
纪律队列
持仓纪律
持仓契约
给 POET 建一个持仓契约
重签 PLTR 纪律
查看 阿里 的持仓契约
本周纪律检查
```

English aliases may be added later:

```text
discipline queue
position contract US.PLTR
review discipline HK.09988
```

### 11.2 Existing Command Integration

- `持仓分析`: add discipline state, attention cost, and next action.
- `本周复盘`: add discipline check section.
- Stock analysis / decision card: show linked active contract when available.
- Candidate insight review: include discipline-derived candidate insights.

### 11.3 Future Web UI

If a web surface is built later, the first screen should be a dense operational queue, not a marketing page:

- Review queue.
- Coverage metrics.
- Theme exposure and attention cost.
- Position contract detail.
- Confirm/edit/defer/archive actions.

## 12. Data Model Impact

The technical plan should decide exact schema, but the product needs at least:

### 12.1 `position_discipline_cards`

Stores active and historical discipline cards.

Candidate fields:

- `id`
- `market`
- `symbol`
- `position_code`
- `scope_type`: `stock`, `theme`, `portfolio`
- `scope_id`
- `raw_rationale`
- `summary_thesis`
- `position_type`
- `expected_holding_period`
- `review_cadence_days`
- `invalidation_conditions` JSON
- `risk_limit` JSON
- `add_rule` JSON
- `reduce_rule` JSON
- `attention_cost`
- `source_status`
- `confirmation_status`
- `state`
- `created_at`
- `confirmed_at`
- `superseded_at`
- `next_review_at`
- `metadata`

### 12.2 `discipline_events`

Stores lifecycle and audit events.

Candidate event types:

- `draft_created`
- `confirmed`
- `edited`
- `review_due`
- `breach_detected`
- `breach_acknowledged`
- `deferred`
- `resigned`
- `archived`
- `theme_linked`

### 12.3 `discipline_queue_items`

May be materialized or generated on demand.

Important fields:

- `severity`
- `reason_code`
- `reason_text`
- `evidence`
- `recommended_user_action`
- `status`
- `created_at`
- `resolved_at`

## 13. Safety And Permission Boundaries

This feature is high-stakes because it touches investment decisions.

Hard boundaries:

- The system must never place trades.
- The system must never auto-create a confirmed contract from AI output.
- The system must never mark a rule breach as resolved without user action.
- The system must clearly distinguish "discipline reminder" from "investment advice."
- The system must preserve the user's original rationale even if the AI summary changes.
- The system must show the reason for every alert.
- The system must allow the user to defer an item, but repeated deferrals should remain visible in weekly review.

Recommended wording:

```text
This is a discipline reminder, not an automatic trading instruction.
Please confirm whether the original thesis still stands.
```

## 14. MVP Scope

The first implementation should deliver one coherent loop:

1. Detect current holdings without active confirmed contracts.
2. Generate draft discipline cards for selected positions.
3. Let the user confirm, edit, defer, or archive a draft.
4. Show a discipline queue command.
5. Add discipline state to `持仓分析`.
6. Add a discipline check section to weekly review.
7. Support simple threshold rules: missing contract, review date expired, loss threshold, leveraged/high-attention exposure, and theme crowding.
8. Store raw rationale separately from structured summary.

The MVP should not attempt full broker trade-history reconstruction if current position snapshots and user-provided rationale are enough for a useful first loop.

## 15. Future Scope

- Auto-detect new buys and increases from trade records.
- Build a web discipline workbench.
- Link contract changes to realized P/L outcomes after position close.
- Compare declared discipline with actual behavior over time.
- Learn user's recurring behavior patterns as candidate insights.
- Add richer theme-level crowding signals from market data and news.
- Add broker notification or calendar reminders after the reminder system proves useful.

## 16. Metrics

Coverage metrics:

- Percentage of current market value covered by confirmed discipline cards.
- Percentage of high-attention holdings with confirmed cards.
- Number of missing-contract positions.
- Number of overdue reviews.

Behavior metrics:

- Number of contracts confirmed per week.
- Number of queue items resolved per week.
- Number of repeated deferrals.
- Number of rule breaches acknowledged.

Quality metrics:

- Whether weekly review references discipline outcomes.
- Whether the user edits AI drafts rather than accepting low-quality defaults.
- Whether position exits or reductions later include a final review note.
- Whether the user reports reduced forgotten-thesis anxiety.

## 17. Acceptance Criteria

The feature is product-ready for technical planning when:

1. Product scope is explicitly part of InvestmentKnowledge, not a separate product.
2. The PRD defines card fields, state model, review queue, entrypoints, safety boundaries, and MVP scope.
3. The feature registry tracks it as a ready PRD with missing technical plan.

The MVP is product-acceptable when:

1. Running `持仓纪律` or `纪律队列` shows the highest-priority missing, stale, or breached discipline items.
2. The user can create and confirm a discipline card for at least one current holding.
3. AI-drafted cards remain drafts until user confirmation.
4. Raw user rationale is preserved separately from structured summary.
5. `持仓分析` shows discipline status and next action for relevant holdings.
6. Weekly review includes a concise discipline check section.
7. No command or workflow can place trades or mark AI output as confirmed without user action.
8. Queue items show reason codes and evidence.
9. High-attention or leveraged positions can be assigned shorter review cadences.
10. Theme-level concentration can generate a review item without pretending to be a sell decision.

## 18. Risks

- Too much friction on every trade could make the user ignore the feature.
- AI-drafted discipline could become generic unless grounded in user text and stock-specific research.
- Too many alerts could recreate the daily-report overload the product is trying to avoid.
- Loss-threshold rules could be misread as mechanical sell advice.
- Theme classification may be noisy until sector links and position grouping improve.
- Without trade records, detecting increases may initially depend on snapshots and imperfect comparisons.

## 19. Open Product Decisions

These decisions should be resolved during technical planning or first implementation:

1. What default position size makes a holding "material" enough to require a contract?
2. What default loss threshold should trigger review when the user has not set a rule?
3. Should a new position always create a contract prompt, or only if size or attention cost exceeds a threshold?
4. How should the system rank a small but critical high-volatility position against a large low-attention position?
5. Should theme-level contracts be user-created first, or inferred from existing sector links?
6. What should happen when a user repeatedly defers the same breach?

## 20. Summary

The Position Discipline Layer turns InvestmentKnowledge from a system that remembers research into a system that also remembers promises.

It should help the user avoid the common failure mode of owning too many positions, forgetting the original thesis, and losing discipline around review, stop-loss, add rules, and theme concentration.

The first version should be a simple, transparent, human-confirmed workflow: contract, monitor, queue, review, and learn.
