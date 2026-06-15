# PRD: Stock Valuation Research

## Background

InvestmentKnowledge already supports stock research, sector context, user insights, research jobs, portfolio analysis, and weekly review planning. The next product gap is valuation.

The user often sees a stock move sharply and only later realizes that the market may have switched valuation frames. A company may move from near-term PE to forward revenue, from ordinary DCF to sum-of-the-parts, from current cycle earnings to peak-cycle optionality, or from current cash flow to real-option probability.

The product should help answer a more useful question than "what is the target price?":

> Which valuation frame could explain this stock's current or future rerating, and what assumptions must be true?

## User Problem

- The user does not always know which valuation method the market is using for a stock.
- A stock can rerate quickly when the market starts accepting a different valuation frame.
- Existing stock research captures business facts and risks, but not enough structured valuation logic.
- Different companies need different valuation methods; one static PE, PS, or DCF lens is too blunt.
- The user wants to review missed reratings and learn which valuation method was actually driving the move.

## Goals

First-stage goals:

- Build a user-confirmed valuation method library.
- For a stock, identify the 1-3 most relevant valuation frames.
- Explain the assumptions that support each frame.
- Show what current market price may imply.
- Identify rerating triggers and valuation failure conditions.
- Feed the valuation view into stock decision cards, research jobs, and weekly reviews.

## Non-Goals

- Do not automate trading.
- Do not present model output as a direct buy/sell recommendation.
- Do not require a full financial model in the first version.
- Do not reduce valuation to a single target price.
- Do not write system-inferred valuation opinions into formal user insights without user confirmation.

## Valuation Method Library

The product should not expose a textbook-style method encyclopedia. The system can keep specialist methods internally, but the default user experience should use five core valuation frames and show only the 1-3 most relevant frames for a stock.

### Default Core Frames

#### 1. Free Cash Flow Valuation

Core question:

- How much durable free cash flow can the company generate, and how much is that cash flow worth?

Product rule:

- Treat FCF as one valuation method. Do not expose FCFF, FCFE, EV/FCF, FCF yield, or owner earnings as separate first-level product methods. Those can remain implementation details inside the FCF frame.

Best for:

- Mature companies.
- Maturing growth companies.
- Platform companies that are starting to convert growth into cash.
- Companies where buyback capacity or cash generation is becoming the core market debate.

Key inputs:

- Free cash flow level.
- Free cash flow margin.
- Free cash flow growth.
- Capital intensity.
- Maintenance versus growth capex.
- Durability of cash conversion.

Common rerating triggers:

- FCF turns positive.
- FCF margin improves.
- Capex peak passes.
- Operating cash flow quality improves.
- The market switches from EPS, revenue, or narrative valuation to cash-flow valuation.
- Buyback capacity is re-priced.

Failure conditions:

- FCF is inflated by one-time working-capital release.
- Current FCF reflects peak cycle conditions.
- Growth requires much higher reinvestment than expected.
- Cash conversion weakens.

#### 2. Comparable Multiples

Core question:

- What valuation multiple does the market assign to comparable companies, and should this company trade at a discount or premium?

Common anchors:

- PE.
- PEG.
- PB.
- PS / EV Sales.
- EV EBITDA.
- EV Gross Profit.
- EV FCF as a metric inside the comparable frame.

Best for:

- Companies with a usable peer group.
- Sectors where investors trade a shared valuation anchor.
- Stocks where rerating often comes from peer-group or multiple changes.

Common rerating triggers:

- The company is moved into a higher-quality peer group.
- The market switches from earnings multiples to revenue multiples.
- The market switches from current-year multiples to forward-year multiples.
- Sector leader multiples expand.
- The company proves it deserves a premium to its old peer set.

Failure conditions:

- Peer group is wrong.
- Multiple expansion is not supported by growth, margin, or durability.
- Sector multiple compresses.
- The company loses its premium narrative.

#### 3. SOTP / Asset Value

Core question:

- Are the company's parts, assets, or hidden holdings worth more than the consolidated market value?

This frame combines:

- Sum-of-the-parts valuation.
- NAV or asset-value valuation.
- Holding-company discount analysis.
- Breakup or monetization value.

Best for:

- Conglomerates.
- Holding platforms.
- Real estate, resource, shipping, and other asset-heavy companies.
- Companies with both mature cash-flow segments and high-growth segments.
- Companies with credible spin-off, disposal, restructuring, or asset-monetization potential.

Key inputs:

- Segment revenue, profit, cash flow, or asset value.
- Segment-specific multiples.
- NAV or revalued assets.
- Net debt.
- Holding-company discount.
- Asset monetization path.

Common rerating triggers:

- Spin-off or separate listing.
- Asset sale.
- Better segment disclosure.
- Hidden asset becomes visible.
- NAV discount narrows.
- Buyback, dividend, or privatization unlocks value.

Failure conditions:

- Assets cannot be monetized.
- Segment disclosure stays poor.
- Holding-company discount remains justified.
- Net debt or minority interests consume the apparent upside.

#### 4. Cyclical Valuation

Core question:

- Are current earnings near a cycle top or bottom, and should the market value current earnings, mid-cycle earnings, or an upcycle/downcycle transition?

Best for:

- Semiconductors.
- Memory.
- Shipping.
- Energy.
- Materials.
- Industrial cyclicals.

Key inputs:

- Mid-cycle earnings.
- Supply-demand gap.
- Capacity cycle.
- Unit economics.
- Inventory cycle.
- Price and utilization trends.

Common rerating triggers:

- Cycle inflection is confirmed.
- Pricing rises or stops falling.
- Supply discipline improves.
- Inventory clears.
- The market switches from trough PB to upcycle EPS.

Failure conditions:

- Peak earnings are mistaken for durable earnings.
- Supply response arrives faster than expected.
- Inventory cycle reverses.
- Demand was pulled forward.

#### 5. Growth / Scenario Valuation

Core question:

- If the company captures a large opportunity or reaches a critical milestone, what could the future business be worth?

This frame combines:

- High-growth / TAM valuation.
- Real-options valuation.
- Milestone or probability-weighted scenario valuation.

Best for:

- AI, space, quantum, nuclear, energy transition, deep technology.
- SaaS and internet platforms with large TAM.
- Biotech or early commercialization companies.
- Companies where current profit does not represent long-term potential.

Key inputs:

- TAM / SAM / SOM.
- Penetration rate.
- Forward revenue.
- Gross margin.
- Operating leverage.
- Probability of success.
- Milestones and time window.

Common rerating triggers:

- TAM is revised higher.
- Penetration speed exceeds expectations.
- Unit economics improve.
- Key technical or regulatory milestone is achieved.
- Major customer order validates the scenario.
- The market assigns higher probability to the success case.

Failure conditions:

- TAM narrative is exaggerated.
- Unit economics do not improve.
- Milestone is delayed or fails.
- Capital needs dilute upside.
- The market shifts back from scenario valuation to cash-flow valuation.

### Specialist Frames

Specialist frames should not be shown by default. They should appear only when the stock type or event clearly calls for them.

#### 6. Dividend Valuation

Use only for stable payout companies such as utilities, REITs, banks, and mature dividend stocks.

Core question:

- How much cash can the company sustainably distribute to shareholders?

#### 7. Residual Income / ROE-PB Valuation

Use mainly for financial companies where book value and ROE are central.

Core question:

- Can the company earn sustainable ROE above its cost of equity, and does current PB reflect that excess return?

#### 8. Event-Driven Valuation

Use only when a specific corporate action is central.

Core question:

- Does M&A, privatization, buyback, restructuring, asset injection, or activist pressure change per-share value?

## Product Concepts

### Valuation Method Matrix

Each stock can have multiple valuation frames. The default output should show only the 1-3 most relevant frames from the five default core frames, with specialist frames added only when clearly triggered.

```text
method
applicability
key_assumptions
implied_value_range
current_market_implied_assumptions
rerating_triggers
failure_conditions
confidence
source_status
user_confirmed
```

### Valuation Explanation Before Target Price

The first version should explain:

- Which valuation frame the market may be using.
- Why that frame could justify a stock move.
- Which assumptions matter most.
- Which evidence supports or challenges those assumptions.
- What would break the valuation frame.

Target price can exist as an optional field, but it should not be the default center of the product.

### Market-Implied Assumptions

The system should try to reverse-engineer what the current price implies:

- Implied revenue growth.
- Implied margin.
- Implied PE / PS / EV EBITDA.
- Implied TAM penetration.
- Implied probability of success.
- Implied duration of cycle strength.

This is more useful than simply saying "cheap" or "expensive".

## Data And Cost Architecture

This feature is difficult because valuation is not mainly an LLM problem. It is a data, calculation, source-quality, and token-cost problem. The product must explicitly separate persistent facts, derived calculations, fresh market data, and model interpretation.

### Data Layers

#### 1. Persistent Financial Facts

These should be stored in the database because they are reused across many valuation runs:

- Quarterly, half-year, and annual revenue.
- Gross profit, operating income, net income.
- Operating cash flow.
- Capital expenditure.
- Free cash flow.
- Cash, debt, net debt.
- Shares outstanding and diluted shares.
- Segment revenue and segment profit when available.
- Management guidance.
- Key operating metrics, such as subscribers, units shipped, bookings, backlog, wafer capacity, or same-store sales.

These facts should keep:

```text
stock_id
period_type        -- quarter / half_year / annual / trailing_twelve_month
period_end_date
metric_code
metric_value
currency
unit
source_id
confidence
extracted_by       -- script / crawler / codex_worker / manual / api
confirmed_by_user
created_at
updated_at
```

Product rule:

- Do not ask the model to rediscover historical financial numbers every time.
- Store the numbers once, audit them, and reuse them.
- If a number is missing, say it is missing instead of inventing it.

#### 2. Fresh Market Data

These can change daily or intraday and should usually be fetched or snapshotted:

- Latest price.
- Market cap.
- Enterprise value.
- FX rate.
- Index and sector movement.
- Peer multiples.
- Commodity prices for cyclical stocks.
- Interest rates when relevant.

Product rule:

- Use snapshots for review and backtesting.
- Use fresh fetch for current valuation only when the provider is available.
- Every valuation output must show data timestamp and stale status.

#### 3. Derived Metrics

These should be calculated by deterministic code, not by the model:

- FCF = operating cash flow - capital expenditure.
- FCF margin.
- Revenue growth.
- Gross margin.
- Operating margin.
- Net margin.
- Net debt.
- EV.
- PE, PB, PS, EV/Sales, EV/EBITDA, EV/FCF.
- FCF yield.
- Segment contribution.
- TTM metrics.
- Period-over-period growth.
- Cycle peak/trough comparisons.

Product rule:

- LLMs may explain derived metrics, but should not be the primary calculator.
- Calculations should be reproducible and inspectable.
- Each derived metric should point back to input facts.

#### 4. Semi-Structured Research Data

These are useful but require extraction:

- Annual reports.
- Interim reports.
- 10-K, 10-Q, 20-F, 6-K, 8-K.
- Investor presentations.
- Earnings call transcripts.
- Company press releases.
- Exchange announcements.
- ETF issuer pages.
- Segment disclosures.

Extraction can be done by:

- Official-source provider.
- Lightweight crawler.
- Codex worker.
- Manual source upload.
- Future API connectors.

Product rule:

- Prefer official sources before web summaries.
- Store excerpts and source facts so future valuation runs do not reread long documents.
- Use Codex workers for hard extraction and source discovery, not for every interactive valuation query.

#### 5. Model Interpretation Layer

The model should receive a compact valuation packet, not raw long documents:

```text
stock profile
latest market snapshot
financial fact summary
derived metric summary
peer summary
relevant source excerpts
user insights
candidate valuation frames
data gaps
```

Product rule:

- The LLM explains frames, assumptions, triggers, and failure conditions.
- The LLM should not be asked to browse the whole internet every time.
- If the valuation packet is incomplete, the output must state which frame is weak because of missing data.

### Data Source Strategy

#### Source Trust Tiers

Valuation should use a trust-tier model. The system should prefer high-trust data even if it is slower, and use low-cost market data only with clear labeling.

```text
Tier 1: Official company and exchange sources
Tier 2: Regulator structured data
Tier 3: Broker / market data APIs already available to the user
Tier 4: Free public market data APIs
Tier 5: Unofficial scraped or wrapper sources
Tier 6: LLM-discovered claims, which must be treated as unverified until sourced
```

Product rule:

- Financial statement facts should come from Tier 1 or Tier 2 whenever possible.
- Market prices and peer multiples can use lower-cost sources, but must carry source and timestamp.
- Unofficial sources can help exploration, but should not silently overwrite official facts.

#### Candidate Free Or Low-Cost Sources

These sources are candidates for implementation and should be validated before coding.

| Source | Best Use | Trust | Cost | Notes |
| --- | --- | --- | --- | --- |
| SEC EDGAR APIs | US filings, submissions, XBRL company facts | Very high | Free | Best default source for US listed-company financial facts. |
| Company investor relations pages | Annual reports, presentations, earnings releases | Very high | Free | Requires crawler/extractor; source quality is high but formats vary. |
| HKEXnews | HK announcements, annual/interim reports | Very high | Free | Best default source for HK official filings and reports. |
| Futu OpenAPI | Holdings, user account data, possibly quotes | High for user account data | Existing integration | Good for portfolio context; quote/data licensing should be respected. |
| Alpha Vantage | Prices, fundamentals, cash flow, earnings, commodities, macro | Medium | Free tier + paid tiers | Useful fallback API; needs rate-limit handling and source audit. |
| FRED | Rates, macro, inflation, GDP, economic indicators | High | Free API key | Useful for discount-rate and macro context, not company financials. |
| Yahoo Finance / yfinance | Prices, summary data, quick peer checks | Medium-low | Free unofficial access | Useful for exploration and cheap snapshots; not an official production-grade financial source. |
| Stooq | Historical prices and index data | Medium | Free | Useful low-cost historical market data fallback. |
| Nasdaq public pages | US market calendar, earnings/IPO references | Medium | Free web access | Useful for event calendar context; scraping stability must be monitored. |

Implementation guidance:

- Start with SEC EDGAR for US financial facts.
- Start with HKEXnews for HK financial reports and announcements.
- Use Alpha Vantage or Yahoo/yfinance only for low-cost market snapshots and fallback fundamentals, with clear source labels.
- Use FRED for interest-rate and macro inputs when valuation frames need discount-rate context.
- Cache every fetched payload or normalized source fact that affects valuation output.

#### Use Database First

Use the database for:

- Reusable financial statements.
- Historical valuation cases.
- User-confirmed valuation views.
- Peer sets confirmed by the user or system.
- Previous valuation artifacts.
- Weekly review snapshots.

#### Use Deterministic Calculation Second

Use code to compute:

- Ratios.
- Margins.
- Growth rates.
- FCF.
- Multiples.
- TTM values.
- Implied assumptions where possible.

#### Use Crawlers To Reduce Cost

Use crawlers for:

- Official report discovery.
- Investor relations page checks.
- Exchange filing pages.
- Peer multiple pages when the source is stable and allowed.
- Earnings date or event calendars.

Crawler outputs should become structured source facts, not raw prompt stuffing.

#### Use Codex CLI / Workers For Hard Tasks

Use Codex workers for:

- Discovering missing official sources.
- Extracting tables from filings.
- Building a first valuation packet for a stock with no prior data.
- Auditing whether reported numbers can be traced to sources.
- Refreshing stale valuation packets asynchronously.

Do not use Codex worker for every user query if the valuation packet already exists.

#### Use LLM Only At The End

Use the LLM for:

- Frame selection explanation.
- Market-implied assumption interpretation.
- Rerating trigger synthesis.
- Failure-condition synthesis.
- User-facing narrative.

Do not use the LLM for:

- Primary arithmetic.
- Repeated extraction of the same financial tables.
- Silent source invention.
- Uncached peer set discovery on every query.

### Valuation Pipeline

Interactive command:

```text
value SYMBOL MARKET
  -> load stock profile
  -> load cached valuation packet
  -> check stale status
  -> fetch latest market snapshot if cheap
  -> compute deterministic metrics
  -> score valuation frames
  -> send compact packet to model
  -> return valuation card
  -> optionally create candidate valuation case
```

Async refresh:

```text
refresh valuation SYMBOL MARKET
  -> create valuation research job
  -> discover official sources
  -> extract financial facts
  -> compute derived metrics
  -> refresh peer set
  -> generate valuation packet
  -> audit source coverage
  -> save artifact
```

### Frame Scoring Inputs

Each frame should be selected by rules and evidence before the model explains it.

```text
FCF:
  + stable or improving FCF
  + positive FCF margin
  + buyback relevance
  - FCF driven by one-time working capital

Comparable Multiples:
  + usable peer group
  + market trades sector by multiples
  + recent peer multiple expansion
  - peer group is weak or business model is unique

SOTP / Asset Value:
  + multiple segments
  + hidden holdings or assets
  + NAV discount
  + possible spin-off or monetization

Cyclical:
  + commodity / memory / shipping / industrial cycle exposure
  + strong price, inventory, capacity, or utilization signals
  - current earnings likely peak and not durable

Growth / Scenario:
  + large TAM
  + milestone-driven value
  + current profit does not reflect future opportunity
  + nonlinear upside
  - scenario lacks observable milestones
```

The model can challenge the score, but the first pass should come from deterministic rules and available facts.

### Token Budget Rules

Default interactive valuation should fit in a compact packet:

```text
target: under 2,000-4,000 tokens of input context
hard cap: no raw filings unless explicitly requested
```

Use these controls:

- Include only the latest 8-12 key financial facts.
- Include only top 3 peer multiple rows.
- Include only source excerpts tied to the chosen frames.
- Include only user insights related to valuation, sector, or the stock.
- Exclude full research drafts by default.
- Link to artifacts instead of embedding them.

### Data Freshness Rules

Each valuation output should show:

```text
financials_as_of
market_data_as_of
peer_data_as_of
source_coverage
stale_fields
confidence
```

Example:

```text
Financials: FY2025 annual report and 2026 Q1 results covered.
Market data: price snapshot from 2026-06-16.
Peer multiples: stale, last refreshed 2026-05-30.
Confidence: medium because peer set is stale.
```

### Suggested Additional Tables

The first implementation can use artifacts, but the product should move toward explicit storage:

```text
financial_facts
id
stock_id
period_type
period_end_date
metric_code
metric_value
currency
unit
source_id
confidence
extracted_by
confirmed_by_user
created_at
updated_at
```

```text
market_snapshots
id
stock_id
snapshot_at
price
market_cap
enterprise_value
currency
fx_rates
source
created_at
```

```text
peer_sets
id
stock_id
name
peers
reason
confirmed_by_user
created_at
updated_at
```

```text
valuation_packets
id
stock_id
packet_date
financials_as_of
market_data_as_of
peer_data_as_of
data
source_status
created_by
created_at
```

```text
valuation_runs
id
stock_id
packet_id
run_type
selected_frames
output_summary
artifact_path
confidence
created_at
```

### First Version Data Boundary

P1 should not try to solve everything. It should support:

- Cached valuation packet artifact.
- Deterministic calculation of basic metrics.
- Manual or official-source financial facts.
- Frame scoring from available data.
- LLM explanation from compact packet.
- Clear data-gap disclosure.

P1 should not require:

- Full automated global financial-data coverage.
- Perfect peer multiples.
- Intraday market data.
- Full Excel-style valuation model generation.

### Recommended Implementation Sequence

The technical implementation should be staged to avoid high token cost and unreliable output.

#### Step 1: Valuation Data Foundation

- Add or simulate `financial_facts`, `market_snapshots`, `peer_sets`, `valuation_packets`, and `valuation_runs`.
- Implement deterministic calculations for FCF, margins, growth, EV, basic multiples, and TTM metrics.
- Build a compact valuation packet artifact before using LLM interpretation.

#### Step 2: Official Financial Fact Ingestion

- US stocks: ingest SEC EDGAR companyfacts and submissions first.
- HK stocks: ingest HKEXnews annual/interim reports and announcements first.
- Non-US/non-HK stocks: fall back to company IR pages and manual/Codex worker extraction.
- Store extracted facts with source IDs and confidence.

#### Step 3: Cheap Market Snapshot Provider

- Add one low-cost price/market snapshot provider.
- Candidate order: existing Futu quote path if licensing/availability is acceptable, Alpha Vantage free tier, Yahoo/yfinance fallback, Stooq fallback for historical prices.
- Every market snapshot must store source, timestamp, currency, and stale status.

#### Step 4: Frame Scoring Without LLM

- Implement rule-based frame scoring from stored facts and derived metrics.
- Return selected frames and data gaps even without LLM.
- This makes the valuation feature usable when model calls are disabled or expensive.

#### Step 5: LLM Explanation From Compact Packet

- Send only compact valuation packets to the model.
- Require the model to cite packet fields, data gaps, and source status.
- Forbid claims not traceable to packet data unless clearly labeled as inference.

#### Step 6: Async Refresh Jobs

- Add valuation refresh jobs for missing or stale packets.
- Use Codex workers for source discovery, table extraction, and audit.
- Interactive `value SYMBOL MARKET` should stay fast and avoid full web discovery.

## User Flows

### Single-Stock Valuation Research

```text
User: value RKLB US
System:
  1. Read stock context.
  2. Read knowledge items, sources, research drafts, and portfolio status.
  3. Identify candidate valuation frames.
  4. Output a concise valuation-frame matrix.
  5. Explain the most likely rerating path.
  6. Generate candidate valuation insights for user confirmation.
```

### Research Job Integration

```text
research_job
  -> official sources
  -> business facts
  -> valuation frame candidates
  -> valuation review artifact
  -> decision card
```

### Weekly Review Integration

Weekly review should add:

- Which holdings may have rerated this week.
- Which moves came from earnings changes versus multiple expansion.
- Which valuation assumptions were supported or challenged.
- Whether the user missed a valuation-frame switch.

## System Integration

### Data Model

Recommendation: add valuation-specific tables instead of forcing valuation into generic knowledge items.

```text
valuation_methods
id
code
name
category
description
applicable_stock_types
key_inputs
common_triggers
limitations
created_at
updated_at
```

```text
stock_valuation_cases
id
stock_id
method_code
valuation_date
applicability
key_assumptions
implied_value_low
implied_value_base
implied_value_high
currency
market_price
market_implied_assumptions
rerating_triggers
failure_conditions
confidence
source_status
confirmed_by_user
created_at
updated_at
```

```text
valuation_sources
id
valuation_case_id
source_id
relation_type
created_at
```

If the first version should avoid schema changes, save valuation artifacts under `drafts/valuation/` and write a short summary into `knowledge_items`. In the medium term, use dedicated tables.

### MCP / Command Entry Points

New MCP tools:

- `list_valuation_methods`
- `inspect_stock_valuation`
- `create_stock_valuation_case`
- `confirm_stock_valuation_case`
- `reject_stock_valuation_case`

New commands:

- `value 000660 KR`
- `valuation 000660 KR`
- `how is SK Hynix valued`
- `valuation methods`
- `confirm valuation case 12`
- `show valuation case 000660 KR`

### Stock Decision Card Integration

Level 1 stock decision cards should add:

```text
valuation_frame: most important current valuation frame
valuation_rerating_trigger: variable most likely to drive rerating
valuation_risk: condition that could break valuation
valuation_status: no_data / candidate / user_confirmed / stale
```

### Research Draft Protocol Integration

Future `research_draft.json` can add:

```json
{
  "valuation_cases": [
    {
      "method_code": "comparable_multiples",
      "applicability": "...",
      "key_assumptions": ["..."],
      "market_implied_assumptions": ["..."],
      "rerating_triggers": ["..."],
      "failure_conditions": ["..."],
      "confidence": 0.7,
      "source_keys": ["annual_report", "peer_multiple"]
    }
  ]
}
```

Do not auto-import valuation cases as confirmed conclusions. First create candidate valuation cases.

### User Memory Integration

Valuation research may propose candidate insights such as:

- "The user prefers SOTP for multi-business platform companies."
- "The user is cautious about peak-cycle PE for cyclical stocks."
- "The user wants to track valuation-frame switches, not just static cheapness."

These must go into `candidate_insights` first.

## First-Version Output Example

```text
RKLB US Valuation Research

Most likely valuation frames:
1. Growth / Scenario
2. Comparable Multiples

Market may be pricing:
- Continued commercial launch revenue growth.
- Larger TAM if Neutron succeeds.
- Higher certainty from defense and space infrastructure orders.

Most price-sensitive assumptions:
- Neutron success probability.
- Forward revenue scale.
- Gross margin and capital expenditure path.
- Revenue multiple the market is willing to assign.

Rerating triggers:
- Neutron milestone success.
- Large government or commercial contract.
- Comparable space asset multiples move higher.

Valuation failure conditions:
- Neutron delays or cost overruns.
- Launch margins fail to improve.
- Market shifts from Growth / Scenario valuation back to FCF valuation.
```

## Priority

Recommended priority:

1. Confirm the valuation method library.
2. Add `value SYMBOL MARKET` as a text/artifact output.
3. Add valuation frame fields to Level 1 decision cards.
4. Add dedicated valuation tables after the first workflow proves useful.

This should be built alongside the decision-card work, because valuation frame is part of the first-screen investment decision.

## Acceptance Criteria

- The system can list the user-confirmed valuation method library.
- For a stock, the system can output 1-3 relevant valuation frames.
- Output includes key assumptions, rerating triggers, and failure conditions.
- Output clearly separates facts, valuation assumptions, and model inference.
- The system does not write valuation inference into formal user insights without confirmation.
- Weekly review can highlight potential valuation-frame changes in current holdings.

## Risks

- Valuation outputs can create false precision; default to ranges and assumptions.
- One stock can be explained by multiple competing methods; show the competition.
- Without reliable financial and peer multiple data, first version should not force exact target prices.
- High-growth and real-option valuation can become narrative abuse; always show failure conditions.

## Confirmed Product Decisions

1. Use five default core frames: FCF, Comparable Multiples, SOTP / Asset Value, Cyclical, and Growth / Scenario.
2. Keep Dividend, Residual Income / ROE-PB, and Event-Driven as specialist frames that appear only when clearly triggered.
3. Put valuation explanation before target price.
4. Prioritize current holdings before broad market coverage.
5. Include valuation-frame changes in weekly review.
6. Build the feature as a valuation packet system, not an LLM-first valuation chat.

## Open Questions For Technical Design

- Whether P1 uses real database tables immediately or starts with artifact-backed valuation packets.
- Which low-cost market snapshot provider should be implemented first after official financial facts.
- How much of HKEX annual/interim report extraction should be scripted versus delegated to Codex workers.
- Whether peer sets should be manually confirmed first or generated automatically with later review.

## Research Sources

- CFA-style equity valuation frameworks: income, market, and asset approaches.
- Aswath Damodaran valuation framing: intrinsic value, relative value, and real options.
- Standard DCF literature: explicit forecast period plus terminal value.
- Relative valuation and multiples frameworks: peer group, standardized multiples, and comparability.
- Residual income valuation: book value plus present value of future residual income.
- Sum-of-the-parts valuation: segment-level valuation for conglomerates and holding companies.
- Real options valuation: value of managerial flexibility under uncertainty.
