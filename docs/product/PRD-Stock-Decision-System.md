# PRD: Stock Decision System V1

## Background

InvestmentKnowledge already has stock profiles, sector trees, knowledge items, user insights, candidate insights, research drafts, valuation research planning, Futu portfolio access, and weekly review workflows.

The current "Level 1 decision card" compresses stock evidence into a first-screen summary:

- One-line thesis.
- Key drivers.
- Core risks.
- Watch items.
- Data freshness.
- Source and audit status.

That name is confusing because the card does not truly make a decision. It should be treated as a stock evidence summary card:

> A compact summary of what the knowledge graph currently knows about the stock.

The evidence card is useful, but it is not yet a full decision system. It explains what the system knows; it does not yet decide how that knowledge should interact with the user's portfolio constraints, available attention, market regime, industry strength, valuation frame, technical setup, chip structure, event risk, and personal risk preferences.

Stock Decision System V1 turns the existing knowledge graph and research pipeline into a personal decision-support layer:

> Given one stock, the user's current portfolio state, the user's constraints, the stock evidence, the sector context, and the market context, produce a traceable composite score, recommendation, position-size range, entry conditions, add/reduce conditions, veto conditions, confidence level, and next review trigger.

This is a decision-support system, not an automated trading system.

## User Problem

The user does not only need to know whether a stock is "good." The user needs to know whether it is good enough to own now, in this portfolio, with this amount of attention, under this market and sector regime, at this valuation and technical position.

Current pain points:

- Model-generated stock research can sound plausible but may overrepresent the model's own judgment.
- Fundamental data, valuation interpretation, technical setup, chip/event structure, and sector context are not yet balanced in one decision output.
- Portfolio constraints are not explicit enough: cash ratio, current exposure, position count, category concentration, attention budget, volatility tolerance, and single-name maximum position should change the recommendation.
- Industry and market context are often decisive, especially when a market has globally dominant sectors or when an industry's pricing power is concentrated in a specific listing market.
- Data freshness is uneven. Prices and technical data can stale in minutes or hours; filings can stay useful for quarters; inferred theses must remain reviewable and should not be stored as facts.
- The system must evolve with the user's recurring new ideas without letting unconfirmed model inference overwrite confirmed user preferences.

## Product Judgment

V1 should be a full product scope, not a prototype. The system should be designed around traceability, data freshness, and user-specific constraints from the beginning.

The most important product distinction:

- Stock Evidence Card, formerly Level 1 decision card: "What do we know about this stock?"
- Stock Decision System V1: "Given what we know and given the user's actual constraints, what should the user do or not do?"

The recommendation must include action boundaries, not just a score. A high score without position sizing, veto conditions, and review triggers is dangerous and incomplete.

## Terminology Decision

The product should stop using "Level 1 decision card" as the user-facing name.

Recommended terminology:

| Old term | New term | Why |
| --- | --- | --- |
| Level 1 decision card | Stock Evidence Card | It summarizes stock evidence but does not issue a portfolio-aware recommendation. |
| Level 2 evidence layer | Evidence Detail | It expands sources, facts, audit status, and graph objects. |
| Stock Decision System | Decision Ticket / Decision Engine | It produces the actual score, recommendation, position boundary, gates, and review triggers. |

Internal code can continue using existing helper names until implementation work renames them safely. Product docs and user-facing commands should prefer the new terms.

## Coexistence Plan

The Stock Decision System is not a simple replacement for the evidence card. It is a higher-level decision layer that uses the evidence card as one input.

### Product Layer

| Product object | User question | Output | User-facing entrypoint |
| --- | --- | --- | --- |
| Stock Evidence Card | What does the system know about this stock? | Thesis, drivers, risks, watch items, freshness, evidence count. | `分析 SYMBOL MARKET`, stock page summary. |
| Evidence Detail | What evidence supports this summary? | Sources, knowledge items, candidate insights, audit report, research draft. | `分析详情 SYMBOL MARKET`, expanded evidence view. |
| Decision Ticket | What should I do with this stock given my portfolio and constraints? | Score, recommendation, position range, gates, entry/add/reduce conditions, review trigger. | `决策 SYMBOL MARKET`, decision workbench. |

The evidence card remains useful because not every stock lookup should spend tokens, refresh data, or produce a recommendation. The decision ticket is used when the user is making or reviewing an action.

### Data Storage Layer

The evidence card should usually be derived, not stored as a primary object:

- Derived from `stocks`, `knowledge_items`, `sources`, sector relations, and latest research job status.
- Can be cached later for speed, but the durable source of truth remains the graph.
- Can be embedded into a decision snapshot as `stock_card_json` so historical decisions remain reproducible.

The decision system needs durable storage because it represents a point-in-time judgment:

- `stock_decisions` stores the decision ticket and score components.
- `stock_observations` stores time-sensitive market, technical, valuation, and event snapshots.
- `inference_items` stores model-inferred theses separately from facts.
- `user_constraint_profiles` stores structured decision constraints.
- `sector_regime_snapshots` and `market_regime_snapshots` store time-sensitive context.

### Workflow Layer

Default stock analysis workflow:

```text
分析 SYMBOL MARKET
  -> load graph context
  -> build Stock Evidence Card
  -> show compact evidence summary
```

Detailed evidence workflow:

```text
分析详情 SYMBOL MARKET
  -> load graph context
  -> show evidence detail, sources, facts, audit status, candidate insights
```

Decision workflow:

```text
决策 SYMBOL MARKET
  -> build Stock Evidence Card
  -> load user constraint profile
  -> load current portfolio exposure
  -> load / refresh technical, valuation, chip-event, sector, and market packs
  -> run deterministic gates and pre-scores
  -> run model synthesis on compact context pack
  -> save Decision Ticket snapshot
  -> propose candidate insights if new user-style rules are inferred
```

Weekly review workflow:

```text
复盘
  -> read trades, holdings, P/L, user thoughts, and saved Decision Tickets
  -> compare decisions against outcomes
  -> propose lessons and candidate insights
```

### Upgrade Relationship

From the user's perspective, the decision system is an upgrade from "stock summary" to "portfolio-aware action support."

Architecturally, it is not a replacement. The relationship is:

```text
Knowledge Graph
  -> Stock Evidence Card
  -> Decision Ticket
  -> Weekly Review / Historical Validation
```

The evidence card is the compact evidence input. The decision ticket is the portfolio-aware output.

## Goals

- Produce a composite stock decision score with sub-scores.
- Produce a recommendation category: avoid, watch, wait, starter, normal position, high-conviction candidate, trim/reduce, or review existing holding.
- Produce a suggested initial position range and maximum position cap based on user constraints and current portfolio exposure.
- Separate facts, model inference, user-confirmed insights, and candidate insights.
- Attach freshness and evidence metadata to every decision component.
- Use the existing knowledge graph as the main context layer.
- Support fresh data acquisition when existing graph data is stale or incomplete.
- Control token cost by using layered context packs and deterministic pre-scoring before model synthesis.
- Make the output auditable enough for future weekly reviews and historical validation.

## Non-Goals

- Do not place trades.
- Do not present the output as personalized financial advice or guaranteed return prediction.
- Do not reduce the decision to one target price.
- Do not store model-inferred user preferences as confirmed user insights.
- Do not require a perfect full financial model before producing a useful decision.
- Do not depend on one data vendor for all markets and all data types.
- Do not turn every decision request into a broad web search if the graph already contains fresh audited context.

## User Stories

- As the user, I can ask for a decision on one stock and receive a score, recommendation, position range, and reasoned boundaries.
- As the user, I can see why a stock is high quality but still not suitable for my current portfolio.
- As the user, I can distinguish a buyable stock from a watch-only stock.
- As the user, I can see which part of the score is weak: fundamentals, valuation, technical setup, chip/event structure, sector regime, market fit, or portfolio fit.
- As the user, I can ask what data is stale and what must be refreshed before trusting the decision.
- As the user, I can confirm, reject, or revise inferred strategy lessons after a decision or weekly review.
- As the user, I can later review whether a decision was validated, invalidated, or simply not followed.

## Core Flow

```text
User asks: decide SYMBOL MARKET
  -> resolve stock and current holding
  -> load user constraint profile
  -> load current portfolio snapshot and exposure map
  -> load stock context from knowledge graph
  -> load sector context and ancestor sectors
  -> load market context
  -> run data freshness planner
  -> refresh only required missing or stale sources
  -> build structured evidence pack
  -> run deterministic pre-scoring
  -> run model synthesis on compact evidence pack
  -> produce decision ticket
  -> save decision snapshot
  -> propose candidate insights if new user-style rules are inferred
```

## Output: Decision Ticket

Default decision output:

```text
SYMBOL MARKET (Name)
Recommendation: starter / wait / watch / avoid / increase / trim / review
Composite score: 0-100
Confidence: low / medium / high

Suggested position:
- Initial range: x%-y%
- Max cap: z%
- Position class: starter / normal / high-conviction candidate

Sub-scores:
- Portfolio fit
- Fundamental quality
- Valuation setup
- Technical setup
- Chip and event structure
- Sector regime
- Market regime and market-sector leadership fit
- Evidence quality and freshness

Why:
- 3-5 key reasons

Veto conditions:
- Conditions that should block buying or adding

Entry conditions:
- Conditions under which buying becomes acceptable

Add conditions:
- Conditions under which adding becomes acceptable

Reduce/exit review conditions:
- Conditions that should trigger review or reduction

Next review:
- date or event trigger

Evidence:
- sources count
- stale components
- inferred components
- unresolved questions
```

## Scoring Model

V1 should use deterministic score components plus model synthesis. The deterministic layer prevents the model from turning persuasive prose into unsupported scores.

### Composite Score

Recommended initial weights:

| Component | Weight | Purpose |
| --- | ---: | --- |
| Portfolio fit | 20 | Whether the stock fits current cash, concentration, market, sector, and attention constraints. |
| Fundamental quality | 18 | Business quality, growth, profitability, balance sheet, execution quality. |
| Valuation setup | 16 | Whether current price is supported by reasonable valuation frames and rerating assumptions. |
| Sector regime | 14 | Whether the industry has real incremental demand, pricing power, and strong supply-demand structure. |
| Market regime and leadership fit | 10 | Whether the listing market currently rewards this sector and whether the sector is a local/global leadership area. |
| Technical setup | 9 | Trend, price location, volatility, support/resistance, momentum. |
| Chip and event structure | 8 | Unlocks, index inclusion, connect inclusion, shareholder structure, IPO lock-up, privatization expectation, catalysts. |
| Evidence quality and freshness | 5 | Whether the decision is based on current, traceable, and audited evidence. |

Weights should be configurable through a user-confirmed strategy profile later. V1 can start with these defaults and expose the reason for each score.

### Score Gating

Some conditions should cap the recommendation even if the composite score is high:

- Missing or stale critical data caps confidence.
- Existing theme concentration caps position size.
- Upcoming major unlock or binary event caps recommendation to watch/starter unless explicitly accepted.
- Valuation frame unsupported by evidence caps valuation score.
- Technical breakdown caps immediate buy recommendation.
- User attention shortage caps the number of high-volatility or event-heavy holdings.
- User-confirmed risk rules override model enthusiasm.

## User Constraint Profile

The system needs a structured profile before issuing strong recommendations.

### Required Fields

| Field | Type | Why it matters |
| --- | --- | --- |
| max_single_stock_position_pct | number | Caps position sizing. |
| preferred_starter_position_pct | number | Determines trial position size. |
| cash_reserve_min_pct | number | Prevents over-deployment. |
| max_positions_target | number | Controls attention complexity. |
| max_positions_hard_cap | number | Blocks over-fragmentation. |
| daily_monitoring_minutes | number | Controls tolerance for fast-moving/event-heavy stocks. |
| weekly_research_hours | number | Controls how many complex theses can be held. |
| max_theme_exposure_pct | number | Controls crowded theme risk. |
| max_market_exposure_pct | object | Controls market concentration. |
| volatility_tolerance | enum | Low/medium/high. |
| drawdown_tolerance | enum | Low/medium/high. |
| missed_opportunity_vs_drawdown_bias | enum | Whether the user fears missing upside or drawdown more. |
| event_stock_allowed | boolean | Whether IPO, lock-up, privatization, or binary-catalyst stocks are allowed. |

### First-Run Questions

The product should ask only the minimum needed questions and infer the rest from portfolio data:

- What is the maximum single-stock position you are comfortable with?
- What is your normal starter position?
- How many stocks can you realistically follow?
- How much time can you spend monitoring markets daily and researching weekly?
- Which is worse for you now: missing a good opportunity or suffering a large drawdown?
- Which themes or markets already feel crowded in your portfolio?

The answers should become candidate or confirmed strategy/profile data depending on whether the user explicitly states them as preferences.

## Data Source Strategy

V1 should use a source ladder rather than one data provider.

### Source Ladder

| Layer | Source class | Examples | Use |
| --- | --- | --- | --- |
| L0 Internal | Knowledge graph, user insights, portfolio snapshots, weekly reviews, research drafts | Existing PostgreSQL graph and Futu snapshots | First context layer and personalization. |
| L1 Official | Company filings, exchange announcements, issuer pages, regulator APIs | SEC EDGAR, HKEXnews, SSE/SZSE disclosures, ETF issuer pages, company IR | Authoritative fundamentals, announcements, share structure, risk factors. |
| L2 Market Data | Broker/API quotes, candles, holdings, account data | Futu OpenD, exchange data, licensed providers | Price, technical setup, portfolio state, position exposure. |
| L3 Industry Data | Industry associations, market research firms, official statistics | SIA/WSTS, IDC, Counterpoint, CAICT, Gartner if licensed | Sector demand, shipment, pricing, capacity, cycle data. |
| L4 Index/Flow/Event | Index providers, connect lists, lock-up calendars, corporate action sources | HKEX/Stock Connect, CSI, MSCI/FTSE/S&P notices where licensed, exchange filings | Chip and event structure. |
| L5 News/Research | Reliable media, broker research, curated search | Only when official or structured sources are insufficient | Timely color, but lower default authority. |
| L6 Model Inference | Model synthesis from evidence | Labeled inference only | Thesis, scenario, uncertainty, missing questions. |

### Source Selection Rules

- Use internal graph first if data is fresh and audited.
- Use official filings and announcements before news.
- Use Futu for portfolio state, holdings, quotes, candles, and multi-market access where available.
- Use industry sources for sector regime only when source publisher, date, and metric definition are stored.
- Use search only as a freshness or gap-filling step, not as the default for every request.
- Record every source with publisher, URL, published_at, fetched_at, source_type, target, and license/access notes if relevant.

### External Source Notes

- SEC EDGAR offers company submissions and XBRL APIs, with JSON company submissions and company facts available without API keys. It also publishes real-time/near-real-time filing and XBRL updates and bulk nightly archives.
- SEC fair-access rules require efficient scripting, a declared user agent, and a request rate currently limited to 10 requests per second.
- HKEXnews, SSE, and SZSE provide official listed-company announcement pages.
- Futu OpenD provides a local/cloud gateway plus SDK model for quotation and trading interfaces, including snapshots and historical candlesticks for supported markets subject to authority.

## Data Storage Strategy

The core storage principle:

> Store observations, derived metrics, model inferences, and user preferences as different objects with different freshness rules.

### Data Classes

| Class | Examples | Storage | Freshness |
| --- | --- | --- | --- |
| Raw source | Filing, announcement, report, API response excerpt | `sources`, future `source_artifacts` | Immutable except fetch metadata. |
| Fact | Revenue, margin, lock-up date, shareholder, risk disclosure | `knowledge_items` or structured metric tables | Source-dependent. |
| Time-series metric | Price, volume, market cap, PE, moving average, RSI | Future `market_observations` / `stock_metrics` | Minutes to daily. |
| Derived metric | Sector exposure, concentration, score component, relative strength | Future `derived_observations` | Recomputed when inputs change. |
| Model inference | Thesis, scenario, valuation frame guess, sector interpretation | Future `inference_items` or decision snapshot component | Must be labeled inference, expires quickly unless confirmed. |
| User preference | Position limits, strategy rule, bias, accepted risk | `user_insights` / future `user_constraint_profile` | Durable until revised. |
| Candidate user preference | Inferred user lesson from conversation or decision | `candidate_insights` | Pending until confirmed/rejected. |
| Decision output | Score, recommendation, position range, reasons, gates | Future `stock_decisions` | Snapshot, immutable for audit. |

### Proposed Tables

#### user_constraint_profiles

Stores the user's decision constraints as structured values.

Key fields:

- id
- profile_name
- max_single_stock_position_pct
- preferred_starter_position_pct
- cash_reserve_min_pct
- max_positions_target
- max_positions_hard_cap
- daily_monitoring_minutes
- weekly_research_hours
- max_theme_exposure_pct
- max_market_exposure_json
- volatility_tolerance
- drawdown_tolerance
- missed_opportunity_vs_drawdown_bias
- event_stock_allowed
- source_insight_ids_json
- confirmed_by_user
- created_at
- updated_at

#### stock_decisions

Stores each decision as an auditable snapshot.

Key fields:

- id
- stock_id
- requested_at
- decision_type
- recommendation
- composite_score
- confidence
- suggested_initial_position_min_pct
- suggested_initial_position_max_pct
- suggested_max_position_pct
- score_components_json
- gates_json
- reasons_json
- entry_conditions_json
- add_conditions_json
- reduce_conditions_json
- veto_conditions_json
- next_review_trigger_json
- evidence_summary_json
- stale_components_json
- unresolved_questions_json
- input_context_hash
- model_name
- created_at

#### stock_observations

Stores factual and time-sensitive observations that are not durable business knowledge.

Key fields:

- id
- stock_id
- observation_type
- observed_at
- period_start
- period_end
- value_json
- source_id
- confidence
- stale_after
- created_at

Examples:

- `technical_snapshot`
- `valuation_snapshot`
- `chip_event_snapshot`
- `market_relative_strength`
- `sector_relative_strength`

#### inference_items

Stores model-inferred claims separately from facts and user insights.

Key fields:

- id
- target_type
- target_id
- inference_type
- content
- supporting_source_ids_json
- supporting_knowledge_item_ids_json
- confidence
- stale_after
- status
- promoted_to_knowledge_item_id
- created_at
- updated_at

Status values:

- candidate
- active
- superseded
- rejected
- promoted

#### sector_regime_snapshots

Stores time-sensitive sector conditions.

Key fields:

- id
- sector_id
- observed_at
- demand_trend
- supply_trend
- pricing_power
- inventory_cycle
- capacity_cycle
- order_visibility
- crowding_level
- leadership_markets_json
- key_metrics_json
- source_ids_json
- confidence
- stale_after

#### market_regime_snapshots

Stores market-level context.

Key fields:

- id
- market_code
- observed_at
- risk_appetite
- liquidity_condition
- dominant_sectors_json
- leadership_fit_json
- valuation_regime_json
- flows_json
- source_ids_json
- confidence
- stale_after

## Freshness Policy

Default freshness targets:

| Data | Freshness target |
| --- | --- |
| Live/near-live price snapshot | Intraday to 1 day. |
| Technical indicators | 1 trading day. |
| Portfolio holdings and cash | Intraday to 1 day. |
| Market/sector relative strength | 1-3 trading days. |
| Unlocks, index inclusion, corporate actions | Refresh before decision and after announcements. |
| Earnings estimates or valuation multiples | 1-7 days depending on source. |
| Company filings | Until next filing or major announcement. |
| Industry monthly shipment/sales data | Until next release. |
| Sector thesis inference | 7-30 days depending on volatility. |
| User confirmed constraint profile | Durable until changed. |
| Model-generated decision | Snapshot only; never treated as current after stale_after. |

The decision engine must show stale components explicitly and lower confidence when critical components are stale.

## Knowledge Graph Integration

The stock decision system should not create a parallel research memory. It should read and enrich the existing graph.

### Existing Context Inputs

Use `get_stock_context(symbol, market)` as the default graph context pack:

- stock profile
- stock-sector relations
- stock knowledge
- stock user insights
- stock candidate insights
- sector knowledge
- sector user insights
- sector candidate insights
- global user insights
- global candidate insights
- sources

Add portfolio and market packs:

- current positions
- account cash and market value
- theme exposure
- sector exposure
- market exposure
- historical weekly review findings
- unresolved candidate insights

### Graph Rules

- Facts go into `knowledge_items`.
- User preferences go into `user_insights`.
- Inferred user preferences go into `candidate_insights`.
- Time-sensitive metrics should go into observation tables, not durable knowledge.
- Model synthesis should go into inference or decision snapshots, not facts.
- Every decision should cite the graph objects it used, so weekly review can later compare decisions against outcomes.

### Graph Enrichment

After a decision, the system may propose:

- candidate stock insight
- candidate sector insight
- candidate portfolio/strategy insight
- missing data task
- research refresh task
- next review event

It must not automatically confirm those insights.

## Token, Quality, and Speed Balance

The system should use a tiered context budget.

### Tier 0: Deterministic Local Path

Use for quick checks or repeated decisions when graph data is fresh.

- No broad web search.
- No long filings in prompt.
- Load compact graph facts and latest observations.
- Compute scores with deterministic rules.
- Model sees only top evidence snippets and score reasons.

Target:

- Low cost.
- Fast response.
- Good for watchlist refresh and holdings review.

### Tier 1: Focused Refresh Path

Use when one or two critical components are stale.

- Refresh only stale modules, such as technical snapshot or latest announcements.
- Reuse existing graph context.
- Model receives compact refreshed summaries.

Target:

- Balanced speed and quality.
- Default for normal `decide SYMBOL MARKET`.

### Tier 2: Deep Decision Path

Use when stock is new, high-stakes, high position impact, or evidence is weak.

- Official source discovery.
- Filing/announcement extraction.
- Industry source refresh.
- Valuation frame refresh.
- Sector and market leadership fit assessment.
- Audit and source coverage report.

Target:

- Higher token and latency budget.
- Required before high-conviction recommendations.

### Context Pack Design

The model should receive structured packs, not raw database dumps:

```json
{
  "user_constraints": {},
  "portfolio_exposure": {},
  "stock_card": {},
  "valuation_pack": {},
  "technical_pack": {},
  "chip_event_pack": {},
  "sector_pack": {},
  "market_pack": {},
  "freshness_report": {},
  "score_precalc": {},
  "open_questions": []
}
```

### Token Controls

- Keep raw filings out of the final synthesis prompt.
- Extract source facts before model synthesis.
- Rank evidence by decision relevance.
- Limit each pack to the top 5-10 facts unless deep mode is requested.
- Use hashes to detect unchanged context and reuse cached summaries.
- Store decision snapshots to avoid re-answering the same context from scratch.
- Use smaller/faster models for extraction and deterministic validation where appropriate.
- Use the strongest model only for final synthesis, conflict resolution, and ambiguous judgments.

### Quality Controls

- Require source-linked evidence for facts.
- Show confidence separately from score.
- Show freshness separately from confidence.
- Mark model inference as inference.
- Use rule-based gates for portfolio concentration, stale data, major events, and user-confirmed risk limits.
- Keep an audit trail from final recommendation back to sources and graph items.

## Functional Scope

### Commands

Add:

```text
决策 SYMBOL MARKET
决策详情 SYMBOL MARKET
刷新决策数据 SYMBOL MARKET
设置决策偏好
查看决策偏好
查看决策历史 SYMBOL MARKET
```

English aliases:

```text
decide SYMBOL MARKET
decision-detail SYMBOL MARKET
refresh-decision-data SYMBOL MARKET
set-decision-profile
show-decision-profile
decision-history SYMBOL MARKET
```

### Default Command Behavior

`决策 SYMBOL MARKET`:

- Uses Tier 1 focused refresh if needed.
- Returns the decision ticket.
- Saves a decision snapshot.
- Proposes candidate insights when appropriate.

`决策详情 SYMBOL MARKET`:

- Includes score component evidence.
- Shows source links, graph item ids, stale data, inferred items, and unresolved questions.

`刷新决策数据 SYMBOL MARKET`:

- Refreshes data packs without forcing a recommendation.

### UI / Workbench Surface

The future web surface should mirror the weekly review workbench style:

- Top decision ticket.
- Score component table.
- Portfolio fit panel.
- Evidence freshness panel.
- Source trace panel.
- Candidate insights panel.
- Decision history panel.

## V1 Engineering Handoff

This PRD is ready for engineering planning, but implementation should still be delivered in explicit build slices because the feature touches database schema, command routing, graph context, portfolio state, market data freshness, model prompting, and future weekly-review validation. The split is for dependency control and verification safety, not because the product scope is a throwaway prototype.

### Non-Negotiable V1 Contract

V1 is only acceptable if it can produce a saved Decision Ticket that includes:

- Composite score and component scores.
- Recommendation category.
- Confidence and freshness status.
- Suggested initial position range and max position cap.
- Reasons, veto conditions, entry conditions, add conditions, and review triggers.
- Evidence summary linked back to graph objects or source records.
- Clear labels for facts, observations, inferences, and user-confirmed preferences.

If any of those are missing, the feature is still incomplete.

### Build Order

Recommended engineering order:

1. Add storage for `user_constraint_profiles`, `stock_decisions`, `stock_observations`, and `inference_items`.
2. Build a `decision_context_pack` function that combines `get_stock_context`, portfolio exposure, user constraints, and freshness metadata.
3. Implement deterministic pre-scoring and gates before any model synthesis.
4. Add `决策 SYMBOL MARKET` and `决策详情 SYMBOL MARKET` command paths.
5. Save decision snapshots and expose decision history.
6. Add focused refresh hooks for technical, valuation, chip/event, sector, and market packs.
7. Connect decisions to weekly review and candidate insight generation.

### Default Product Decisions For Engineering

Use these defaults unless the user later confirms different preferences:

- User-facing recommendation language should use decision-support categories such as watch, wait, starter, normal position, high-conviction candidate, review, trim, and reduce. Avoid strong imperative "buy now" language.
- If the user constraint profile is missing, the system may produce analysis and a provisional recommendation, but it must cap confidence and ask for the missing constraints before suggesting a large position.
- High-conviction recommendations require deep mode or fresh enough evidence across portfolio, valuation, sector, market, technical, and event packs.
- Theme exposure should use both sector-tree paths and explicit theme tags. If they conflict, show the conflict instead of hiding it.
- First implementation should prioritize existing graph data, Futu portfolio/quote access, and official source records already supported by the research pipeline. Additional paid or fragile industry providers should be adapter-based.

### First Acceptance Scenario

The first end-to-end scenario should use an existing or recently researched holding with graph context, sector links, and user insights. A good candidate is `000660 KR` because it already connects to AI infrastructure, HBM, memory-cycle risk, and user-confirmed caution around crowded trades.

The scenario should demonstrate:

- Evidence card is generated from graph context.
- Decision context adds portfolio and user constraints.
- Sector and market packs are present or explicitly marked stale/missing.
- Composite score is produced with gates.
- Decision snapshot is saved.
- Follow-up candidate insights are proposed only when appropriate.

## Safety Boundaries

- The system is for decision support and personal research, not automated trading.
- Trading APIs must remain read-only unless a separate explicit trading product is designed and approved.
- Recommendations must include uncertainty, veto conditions, and review triggers.
- If critical data is stale or missing, the recommendation must degrade to watch/wait or require refresh.
- The system must not fabricate price, filings, announcements, or industry data.
- User-confirmed constraints override model judgment.

## Metrics

Usage metrics:

- Decision requests per week.
- Percent of current holdings with fresh decision snapshots.
- Percent of high-value watchlist names with decision snapshots.
- Percent of decisions with complete source coverage.

Quality metrics:

- Percent of decisions with explicit portfolio fit reasoning.
- Percent of decisions with stale components disclosed.
- Percent of decisions that produce useful candidate insights.
- Percent of decisions referenced in weekly review.
- User acceptance rate of candidate strategy insights.

Outcome learning metrics:

- Number of decisions later validated, invalidated, or revised.
- Number of veto conditions that later occurred.
- Number of missed opportunities explained by prior watch/wait decisions.
- Number of losses where the system had identified the risk in advance.

## Acceptance Criteria

- A user can run `决策 SYMBOL MARKET` and receive a decision ticket with composite score, recommendation, confidence, position range, reasons, veto conditions, review triggers, and evidence summary.
- The decision uses existing graph context from stock, sector, global insights, candidate insights, and sources.
- The decision includes portfolio fit and respects max position, current exposure, theme concentration, market exposure, and attention constraints when available.
- Facts, observations, inferences, user preferences, and decision snapshots are stored separately.
- Stale or missing critical data is visible in the output and lowers confidence or gates the recommendation.
- A detailed view can trace each score component to sources or graph objects.
- Candidate user insights generated by a decision stay pending until user confirmation.
- The system can run in quick/focused/deep paths with explicit token and latency tradeoffs.
- The feature does not start trading, command-api, schedulers, or broad compose services for normal local validation.

## Risks

- Data source licensing may restrict automated storage or redistribution of some provider data.
- Technical/chip/event data can become stale quickly and create false confidence.
- Model synthesis may overweight narrative unless deterministic scoring and gates are enforced.
- The user may interpret a high score as a command to buy unless the system clearly shows position limits and veto conditions.
- Too many inputs can make the system slow and expensive unless context packs and caching are implemented early.
- Market regime and industry data are harder to normalize across US, HK, A-share, Korea, and other markets.

## Open Product Questions

- Should the user allow strong buy-style recommendations, or should the language stay within decision-support categories such as starter/watch/wait?
- What is the user's confirmed maximum single-stock position and starter position?
- What is the user's practical maximum number of active holdings?
- How should the system classify themes for exposure control: by sector tree, custom theme tags, or both?
- Which data providers are acceptable for non-official industry data?
- Should high-conviction recommendations require deep mode by default?

These questions should not block engineering planning because the default product decisions above provide conservative starting behavior. They should be revisited after the first real decision tickets are reviewed by the user.

## References

- SEC EDGAR Application Programming Interfaces: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC Accessing EDGAR Data and fair access guidance: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- HKEXnews listed-company announcements: https://www.hkexnews.hk/index.htm
- Shanghai Stock Exchange listed-company announcements: https://www.sse.com.cn/disclosure/listedinfo/announcement/
- Shenzhen Stock Exchange listed-company announcements: https://www.szse.cn/disclosure/listed/notice/index.html
- Futu OpenD API documentation: https://openapi.futunn.com/futu-api-doc/en/
