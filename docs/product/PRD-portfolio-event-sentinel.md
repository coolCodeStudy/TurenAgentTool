# PRD: Portfolio Event Sentinel

## 1. Background

InvestmentKnowledge already stores portfolio positions, stock research, sector links, decision cards, candidate insights, weekly reviews, and DingTalk reminders. It can explain a stock from durable knowledge, but it does not yet monitor external events against the user's live portfolio exposures.

The user raised an example: a U.S. portfolio contains LITE and AXTI, and a weekend China export-control headline may have affected both stocks because of indium phosphide or China operating exposure. The example is intentionally uncertain. The product must not accept the user's explanation as fact. It must treat user input as a hypothesis, independently verify the event, map the event to portfolio exposures, compare market behavior, and then decide whether the user should be notified.

This PRD defines a read-only event sentinel that turns external news and user-supplied clues into traceable portfolio risk hypotheses.

## 2. Industry And Source Research Summary

### 2.1 Global News Discovery

GDELT DOC 2.0 provides a global full-text news search API with JSON output, article-list modes, longitudinal timelines, and cross-language machine translation across monitored coverage. It is suitable for broad discovery and theme heat, but it should not be treated as authoritative evidence by itself.

Source: [GDELT DOC 2.0 API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)

Product implication:

- Use GDELT-style global search for discovery, theme heat, and source candidate lists.
- Store only title, publisher, date, URL, short extracted fact, language/region, and query metadata.
- Require official or high-trust corroboration before issuing high-severity alerts.

### 2.2 Official Company Evidence

The SEC EDGAR APIs expose company submission history and extracted XBRL data through JSON endpoints without authentication, with filing history and financial-statement APIs updated as filings are disseminated. This is a strong source for U.S. company filings, 8-Ks, 10-Qs, 10-Ks, risk factors, ticker metadata, and official event evidence.

Source: [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

Product implication:

- Use official filings and issuer IR pages to validate company-specific exposure.
- Use filing risk factors and business descriptions to build the durable exposure graph.
- Never infer a company's supply-chain exposure from a news headline alone.

### 2.3 Notification Quality

Notification research highlights alert fatigue: too many low-value notifications desensitize users and can cause important alerts to be missed. A notification system should issue, suppress, or aggregate notifications based on severity, user preferences, and timing.

Source: [A Snooze-less User-Aware Notification System for Proactive Conversational Agents](https://arxiv.org/abs/2003.02097)

Product implication:

- The sentinel should optimize for high-signal awareness, not maximum alert count.
- Low-confidence or low-severity events should be batched into weekly review or an inbox.
- Push notifications require severity, portfolio relevance, and source confidence thresholds.

## 3. User Problem

The user wants to notice external events that matter to current holdings before the weekly review, without becoming trapped in a noisy news feed.

Current gaps:

- The system can analyze holdings but explicitly does not include real-time news or announcements.
- Weekly review product docs already describe event and theme-news evidence, but the implementation still lacks external event attribution.
- Stock decision cards contain static risks, but static risk text does not wake up when a matching event occurs.
- User observations are valuable clues, but they may be wrong or overfit to price action.
- A falling stock can be misattributed to a headline without checking alternative explanations.

## 4. Product Positioning

Portfolio Event Sentinel should be:

> A read-only hypothesis-verification and notification agent that monitors external events against the user's portfolio exposure graph, explains why an event may matter, and routes only high-signal items to the user.

It should not be:

- A generic breaking-news feed.
- A trading recommendation engine.
- A system that treats user speculation as fact.
- A scraper that stores full copyrighted articles.
- A replacement for company research, valuation, decision cards, Kline analysis, or weekly review.

## 5. Goals

1. Detect external events that may materially affect current holdings, watchlist names, or known portfolio themes.
2. Treat every user-supplied explanation as a hypothesis until verified.
3. Build and use a portfolio exposure graph connecting stocks to products, materials, geography, supply chain, customers, regulation, macro factors, and themes.
4. Grade event relevance using source confidence, exposure strength, market behavior, portfolio weight, and alternative explanations.
5. Notify the user only when an event clears a relevance and severity threshold.
6. Preserve every alert as traceable evidence for decision cards and weekly reviews.
7. Keep the product read-only: no trades, no direct buy/sell instructions, no automatic user-insight promotion.

## 6. Non-Goals

- Do not create a full real-time news terminal.
- Do not monitor every market headline equally.
- Do not send push alerts for weak single-source rumors.
- Do not automatically write inferred hypotheses into `user_insights`.
- Do not copy full article content into the database or prompts.
- Do not require paid news-provider credentials for the first usable version.
- Do not make the LLM the only relevance judge; deterministic source, exposure, and threshold rules must exist.

## 7. Scope Split Rationale

This feature should be delivered in a trust-building sequence because it has three concrete risks:

- External data uncertainty: provider availability, article duplication, language coverage, official-source structure, and rate limits vary by source.
- Alert-fatigue risk: a noisy first version would train the user to ignore the system.
- Attribution risk: the system can easily over-explain price moves if it does not separate event facts, exposure facts, market behavior, and interpretation.

The first implementation should still be a complete usable slice: portfolio exposure mapping, event discovery, hypothesis cards, confidence grading, and one notification route. Later versions can expand provider coverage and automation frequency after the user accepts the signal quality.

## 8. Target Users

Primary user:

- The investment system owner who holds a multi-market portfolio and wants early awareness of portfolio-relevant external events.

Secondary users:

- Weekly review generator, which needs event evidence for the story and next-week watch items.
- Decision-card workflow, which needs fresh risk/catalyst evidence.
- Research agent, which can use recurring event misses to update stock or sector knowledge.

## 9. Core User Stories

1. As a user, when a relevant external event happens, I want to know which holdings may be affected and why.
2. As a user, when I give the system a possible explanation, I want it to verify the explanation rather than agree with me.
3. As a user, I want to see the evidence chain: source event, portfolio exposure, market behavior, alternative explanations, confidence, and recommended review action.
4. As a user, I want only important events pushed to DingTalk; weaker signals should wait for the weekly review or an inbox.
5. As a user, I want the event to update the decision card or weekly review as evidence, not as a trading instruction.
6. As a user, I want to confirm or reject recurring hypotheses before they become durable memory.

## 10. Product Principles

### 10.1 Hypothesis, Not Fact

User statements and model classifications are hypotheses until verified by source evidence.

Required wording:

```text
Hypothesis: China export-control news may affect AXTI and LITE.
Verified event: ...
Exposure evidence: ...
Market confirmation: ...
Alternative explanations: ...
Conclusion: supported / partially supported / not supported / unresolved.
```

### 10.2 Evidence Before Alert

An alert must show at least:

- What happened.
- Which holdings are affected.
- Why the event maps to those holdings.
- How confident the system is.
- What remains unverified.
- What the user can review next.

### 10.3 Suppress The Merely Interesting

Not every relevant article deserves a notification. If relevance is weak, confidence is low, or portfolio exposure is small, the event should be stored for review but not pushed.

### 10.4 Preserve Uncertainty

The product must clearly distinguish:

- Confirmed event facts.
- Confirmed company exposure facts.
- Inferred relevance.
- Market behavior evidence.
- User hypothesis.
- Model interpretation.

### 10.5 Read-Only And Non-Advisory

The sentinel may recommend review actions such as "refresh decision card" or "add to weekly review validation." It must not recommend trades.

## 11. Core Flow

### 11.1 Scheduled Monitoring Flow

```text
Portfolio snapshot
  -> resolve current holdings and watchlist
  -> load exposure graph
  -> generate source queries
  -> fetch event candidates
  -> dedupe and classify events
  -> verify source confidence
  -> map event to holdings
  -> compare market behavior
  -> check alternative explanations
  -> score severity and notification eligibility
  -> create hypothesis cards
  -> push, inbox, or weekly-review route
```

### 11.2 User-Supplied Hypothesis Flow

```text
User says "maybe X caused Y"
  -> parse event hypothesis
  -> parse affected holdings
  -> verify whether X happened
  -> verify whether holdings have X exposure
  -> test Y against peer/index behavior
  -> identify alternative explanations
  -> return a hypothesis-verification card
  -> optionally store as candidate insight or event hypothesis
```

### 11.3 Review Integration Flow

```text
Weekly review generation
  -> load event hypotheses during the week
  -> include high/medium relevance events in story evidence
  -> include unresolved high-impact events as next-week validation items
  -> include rejected/low-confidence events only in diagnostics
```

## 12. Functional Scope

### 12.1 Exposure Graph

The system must maintain structured exposure edges from stocks and sectors to event-sensitive concepts.

Exposure types:

| Type | Examples |
| --- | --- |
| Product | InP substrate, optical module, HBM, GLP-1, solar inverter |
| Material | indium, gallium, germanium, rare earths, copper, lithium |
| Geography | China operations, U.S. revenue, Japan customer sales |
| Regulation | export control, sanctions, tariffs, FDA approval, reimbursement |
| Customer | hyperscaler capex, Apple, Nvidia supply chain, telecom OEMs |
| Supplier | single-source supplier, foundry, substrate provider |
| Theme | AI optical communications, AI memory, Hong Kong growth |
| Macro | rates, USD, oil, shipping, credit spreads |

Each exposure edge must include:

- `target_type`: stock, sector, portfolio, strategy.
- `target_id`.
- `exposure_type`.
- `exposure_key`.
- `description`.
- `direction`: positive, negative, mixed, unknown.
- `strength`: high, medium, low.
- `source_id`.
- `confidence`.
- `stale_after`.
- `confirmed_by_user`.

Existing `knowledge_items`, `stock_sector_relations`, and candidate insights can seed this graph, but the technical design should add a structured event-exposure layer rather than relying only on free-text search.

### 12.2 Event Discovery

Supported event categories for the first usable version:

| Category | Examples | Preferred sources |
| --- | --- | --- |
| Official company event | 8-K, earnings release, guidance, production update | SEC EDGAR, issuer IR |
| Government/regulatory event | export controls, sanctions, tariffs, approvals | official government sites, high-trust wires |
| Theme news | AI optical components, HBM, GLP-1, rare earths | GDELT, Google/Yahoo Finance fallback |
| Macro calendar | FOMC, CPI, payrolls, PCE | official calendars already identified in weekly-review PRD |
| Market behavior | stock/sector/index relative moves | Futu market data or existing Kline Agent provider |

The first version should use a small controlled provider set. It should not launch a broad crawler.

### 12.3 Event Candidate Normalization

Every event candidate should normalize to:

```json
{
  "event_key": "provider-stable-key-or-url-hash",
  "event_type": "government_regulation",
  "headline": "China announces export-control action...",
  "publisher": "Ministry of Commerce / Reuters / SEC",
  "source_url": "https://...",
  "published_at": "2026-06-22T00:00:00Z",
  "region": "CN",
  "language": "zh",
  "source_confidence": "official|high|medium|low",
  "extracted_fact": "Short factual summary, not a full article",
  "raw_query": "China export control indium phosphide",
  "fetched_at": "2026-06-24T00:00:00Z"
}
```

### 12.4 Relevance Mapping

The mapping engine should score every event-to-holding link.

Inputs:

- Event category and source confidence.
- Exposure edge strength.
- Portfolio weight and current position status.
- Stock knowledge freshness.
- Whether the event directly names the company, product, material, customer, or region.
- Whether market behavior confirms a stock-specific or theme-specific move.
- Alternative explanation checks.

Output:

```json
{
  "event_id": 123,
  "target": "US.AXTI",
  "relevance": "high",
  "impact_direction": "negative",
  "confidence": "medium",
  "mapping_path": [
    "event: China export-control action",
    "exposure: InP/GaAs substrate and China operations",
    "holding: US.AXTI"
  ],
  "evidence": ["source_id:456", "knowledge_item:437"],
  "unverified_points": ["whether the exact controlled item includes indium phosphide"],
  "alternative_explanations": ["sector selloff", "company financing", "earnings/guidance"]
}
```

### 12.5 Market Behavior Check

The sentinel should not infer causality from a headline alone.

For each mapped holding, compare:

- Same-day and 5-day move.
- Relative move versus relevant index or sector ETF.
- Peer basket move.
- Whether the event time precedes the move, when timestamps are available.
- Whether other company-specific events occurred in the same window.

Market behavior statuses:

- `confirms`: affected holding moved materially worse or better than benchmark/peers.
- `mixed`: holding moved with the broader group.
- `contradicts`: market behavior does not support the hypothesized event impact.
- `unavailable`: market data missing.

### 12.6 Alternative Explanation Check

Before a medium or high alert, the system must search for obvious alternative explanations:

- Earnings or guidance.
- Offering, dilution, buyback, debt, liquidity event.
- Analyst rating or price-target move.
- Customer/order news.
- Sector-wide selloff or rally.
- Macro event.
- Existing high-volatility or crowded-trade risk.

The alert can still be sent when alternatives exist, but it must label the conclusion as mixed or unresolved.

### 12.7 Notification Routing

Routes:

| Route | When used | User experience |
| --- | --- | --- |
| DingTalk push | High relevance, medium/high confidence, material portfolio exposure, or direct company official event | Short alert with confidence and review action |
| Event inbox | Medium relevance or unresolved hypothesis | Appears in command/web surface for triage |
| Weekly review | Low urgency, theme heat, weak confidence, or multiple related small events | Aggregated into story/next-week validation |
| Decision card evidence | Stock-specific event with durable relevance | Added as fresh evidence or watch item |
| Candidate insight | User or model proposes a durable lesson | Requires explicit confirmation |

Push notification must be throttled:

- No duplicate push for the same event-target pair.
- Aggregate related events within a configurable quiet window.
- Default maximum: three portfolio event pushes per trading day unless a direct official company event occurs.
- Never push low-confidence rumor-only items.

### 12.8 Alert Message Shape

Example alert:

```text
Portfolio event hypothesis

Event: China export-control action reported on 2026-06-22.
Affected holdings: US.AXTI high relevance, US.LITE medium relevance.
Why it maps: AXTI has InP/GaAs substrate and China operating exposure; LITE has optical/InP photonics supply-chain exposure.
Confidence: medium. Official/source event exists; exact controlled material mapping still needs verification.
Market check: AXTI/LITE underperformed optical/semiconductor peers over the last 5 trading days.
Alternative explanations: sector weakness and company-specific news still need checking.
Suggested review: refresh AXTI and LITE decision cards; add to weekly review validation.

No trade action was taken or recommended.
```

### 12.9 User Feedback Loop

The user must be able to mark an event hypothesis as:

- Useful.
- Too noisy.
- Wrong mapping.
- Already known.
- Needs research.
- Promote as candidate insight.
- Mute this event key, exposure key, or source.

Feedback should update future scoring but must not rewrite historical evidence.

## 13. Entrypoints

### 13.1 Commands

Candidate command names:

```text
持仓事件
组合事件
事件哨兵
验证假设 <free text>
检查持仓新闻
```

English aliases:

```text
portfolio events
event sentinel
verify hypothesis <free text>
```

### 13.2 Weekly Review

Add an `External Events And Hypotheses` section to the weekly review story inputs:

- Confirmed high-relevance events.
- Unresolved high-impact hypotheses.
- Suppressed low-confidence items count.
- Data source status.

### 13.3 Decision Cards

Decision cards should eventually include:

- Fresh event evidence.
- Event-driven watch items.
- Active unresolved hypotheses.
- Muted or rejected hypothesis notes, when relevant for future context.

### 13.4 Web Surface

The Web workbench should eventually include an event inbox:

- Filter by holding, theme, severity, status, source, and date.
- Show event cards with evidence chain and confidence.
- Allow feedback actions without editing raw evidence.

## 14. Data Model Impact

The technical plan should evaluate adding these tables or equivalent structures:

### 14.1 `portfolio_exposures`

Stores durable exposure edges.

Key fields:

- `id`
- `target_type`
- `target_id`
- `exposure_type`
- `exposure_key`
- `description`
- `direction`
- `strength`
- `confidence`
- `source_id`
- `confirmed_by_user`
- `stale_after`
- `created_at`
- `updated_at`

### 14.2 `event_sources`

Stores normalized external event candidates without full copyrighted article bodies.

Key fields:

- `id`
- `event_key`
- `event_type`
- `headline`
- `publisher`
- `source_url`
- `published_at`
- `region`
- `language`
- `source_confidence`
- `extracted_fact`
- `raw_query`
- `fetched_at`
- `metadata`

### 14.3 `event_hypotheses`

Stores event-to-target relevance judgments.

Key fields:

- `id`
- `event_source_id`
- `target_type`
- `target_id`
- `relevance`
- `impact_direction`
- `confidence`
- `mapping_path`
- `evidence_refs`
- `market_behavior_status`
- `alternative_explanations`
- `unverified_points`
- `status`: pending, confirmed, rejected, muted, archived
- `created_at`
- `updated_at`

### 14.4 `event_notifications`

Stores routing and dedupe state.

Key fields:

- `id`
- `event_hypothesis_id`
- `route`
- `sent_at`
- `message`
- `dedupe_key`
- `user_feedback`

## 15. Source Trust Model

Source confidence levels:

| Level | Definition | Examples |
| --- | --- | --- |
| official | Primary issuer/regulator/exchange/government source | SEC, HKEXnews, company IR, ministry announcement |
| high | Reliable professional news source or data provider | Reuters, AP, Bloomberg, WSJ, FT |
| medium | Aggregator or broad search source with clear URL attribution | GDELT article list, Yahoo Finance, Google News |
| low | Social, forums, reposted summaries, unsourced commentary | X/Twitter, forum posts, unattributed blogs |

Alert rules:

- Official direct company events can trigger high-severity alerts without another news source.
- Government/regulatory events affecting multiple holdings should prefer official or high-trust corroboration.
- Medium sources can create inbox items and weekly-review candidates.
- Low sources cannot push alerts unless corroborated by higher-trust sources or direct company/market evidence.

## 16. Permissions And Safety

- Read-only feature: no orders, no portfolio mutation, no automatic trade recommendations.
- External fetches must be explicit providers with rate limits and source attribution.
- Do not store full article bodies by default.
- Do not put full copyrighted articles into LLM prompts.
- User hypotheses remain hypotheses unless confirmed by evidence.
- Candidate insights require explicit user confirmation before becoming formal user memory.
- Notification webhook configuration must reuse existing secure DingTalk configuration; no temporary tokens in docs, logs, or commits.
- If cloud scheduling is used, deployment must follow the existing Ops API/service-boundary rules.

## 17. Functional Requirements

### 17.1 Must Have

1. Build portfolio exposure candidates from current holdings, stock knowledge, sector links, and confirmed user insights.
2. Allow manual or scheduled event scan against a controlled source/provider list.
3. Normalize event candidates into source records with URL, publisher, date, and short extracted fact.
4. Map event candidates to holdings through explicit exposure paths.
5. Produce hypothesis cards with relevance, confidence, unverified points, and alternative explanations.
6. Route high-signal events to one notification channel and all other items to inbox/weekly-review storage.
7. Store dedupe state so one event-target pair is not repeatedly pushed.
8. Expose source diagnostics when event data is missing or provider fetch fails.
9. Integrate at least one event summary path into weekly review or decision-card evidence.
10. Keep all outputs read-only and non-advisory.

### 17.2 Should Have

1. Market behavior comparison against sector/index/peer basket.
2. User feedback actions for useful/noisy/wrong/mute/needs research.
3. Command entrypoint for `verify hypothesis <free text>`.
4. Event inbox in web workbench.
5. Configurable quiet hours and maximum daily push count.
6. Per-exposure mute and priority overrides.

### 17.3 Could Have

1. Additional paid news providers if credentials are available.
2. Xueqiu/WeChat/manual-import sources with explicit user approval.
3. LLM-assisted event clustering across languages.
4. Automatic research-job creation for high-impact unresolved hypotheses.
5. Cross-portfolio pattern learning after enough feedback.

## 18. Prioritization

P0 should be one complete useful path:

1. Exposure graph seed from existing knowledge and a small manual/curated exposure schema.
2. Controlled event scan using SEC/issuer official sources plus one broad news discovery source.
3. Event-to-holding hypothesis cards.
4. DingTalk push for high-confidence/high-relevance events.
5. Weekly review inclusion for non-pushed items.
6. Dedupe, diagnostics, and no-advice guardrails.

P1 can expand:

- Web event inbox.
- Market behavior comparison.
- User feedback loop.
- More source providers.

P2 can add:

- Automatic exposure refresh from new filings.
- Provider-specific source health dashboards.
- Cross-language clustering and richer event taxonomy.

The split is based on provider uncertainty and alert-quality validation, not on deferring normal implementation work.

## 19. Metrics

North-star metric:

- Percentage of portfolio-relevant material events that the user notices through the system before or during weekly review, without reporting alert fatigue.

Quality metrics:

- Alert usefulness rate: useful alerts / total pushed alerts.
- False-positive rate: alerts marked wrong or noisy / total pushed alerts.
- Missed-event rate: user later identifies a relevant event not captured by the sentinel.
- Average evidence completeness: event source + exposure path + market check + alternatives present.
- Time from event publication to hypothesis card.
- Percentage of alerts with source diagnostics and confidence label.
- Weekly-review event coverage: material event hypotheses included in review.

Guardrail metrics:

- Daily push count.
- Duplicate push count.
- Low-confidence push count.
- Number of outputs containing direct trading advice; must be zero.
- Number of candidate insights auto-promoted without confirmation; must be zero.

## 20. Acceptance Criteria

### 20.1 PRD-Level Acceptance

1. The feature treats user explanations as hypotheses, not facts.
2. The product can describe how it gets relevant news without becoming a generic news feed.
3. The product can describe how it decides whether an event matters to a holding.
4. The product can describe how it avoids alert fatigue.
5. The product defines storage impact, notification routes, safety boundaries, metrics, and source trust levels.
6. The product defines how events flow into weekly review and decision cards.

### 20.2 First Implementation Acceptance

1. Given a current holding with a known exposure, and a matching official or high-trust event, the system creates a hypothesis card with event fact, exposure path, confidence, and source URL.
2. Given a user hypothesis, the system verifies event existence and exposure mapping before producing a conclusion.
3. Given a weak single-source rumor, the system stores it as inbox/weekly-review evidence and does not push a DingTalk alert.
4. Given the same event-target pair twice, the system deduplicates notifications.
5. Given missing source data or failed provider fetch, the user sees a diagnostic instead of a fabricated event summary.
6. Given a high-relevance event, the user receives a concise notification with no trade instruction.
7. Given weekly review generation, relevant event hypotheses can appear as story evidence or next-week validation items.
8. Given a candidate durable lesson, it remains pending until the user confirms it.

## 21. Risks

| Risk | Mitigation |
| --- | --- |
| Alert fatigue | Severity thresholds, daily caps, aggregation, feedback loop, quiet hours |
| False attribution | Separate event facts, exposure facts, market behavior, and alternatives |
| Source unreliability | Source trust model and official/high-trust corroboration rules |
| Copyright risk | Store short facts, metadata, and URLs; no full articles in prompts |
| Overfitting user hypotheses | User statements remain hypothesis inputs, not facts |
| Provider fragility | Controlled provider list, diagnostics, fallback routing |
| Privacy/security | Reuse existing webhook config; do not expose portfolio externally beyond provider queries |
| Product overreach | Read-only, non-advisory copy and no trading actions |

## 22. Open Questions For Technical Design

1. Should portfolio exposure edges be a new table, or should they first be derived from `knowledge_items` plus a structured JSON field?
2. Which broad news provider should be the first production provider: GDELT, Yahoo Finance/Google News fallback, or a user-approved paid source?
3. What is the minimum market data provider for relative behavior checks before Kline Agent is implemented?
4. Should DingTalk alerts be enabled immediately in P0, or should P0 run in dry-run inbox mode until signal quality is accepted?
5. How should watchlist stocks be represented if they are not current Futu positions?
6. What default daily notification cap is acceptable to the user?

## 23. Product Decision

This PRD is ready for technical planning.

The accepted product direction is:

- Build a portfolio event sentinel, not a generic news feed.
- Treat user statements as hypotheses requiring verification.
- Use a portfolio exposure graph to map events to holdings.
- Preserve uncertainty and source attribution in every output.
- Push only high-signal items; route weaker items to inbox or weekly review.
- Keep the feature read-only and non-advisory.
