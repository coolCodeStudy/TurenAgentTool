# PRD: Stock Valuation Research

Status: ready for technical planning.

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

P0 goals:

- Provide the confirmed valuation method library.
- For one stock at a time, identify the 1-3 most relevant valuation frames.
- Explain the assumptions that support each frame.
- Show what current market price may imply.
- Identify rerating triggers and valuation failure conditions.
- Return a concise result through the authenticated Command Workbench and save a traceable valuation artifact for later retrieval.

P0 is intentionally a single-stock, artifact-backed valuation workflow. Dedicated valuation tables, portfolio or batch valuation, weekly-review integration, decision-card integration, and other delivery surfaces are follow-ups after the single-stock packet, calculation, source, and degraded-state behavior is reliable.

## Presentation Addendum: Chinese-First With Canonical English Original

The Stock Valuation Command Workbench presentation is Chinese-first for the valuation create card, latest-artifact card, and valuation method library. Each affected Markdown response appends the exact canonical English renderer output under `## English original (原文)`.

This is a presentation-only contract. The `stock_valuation_packet.v1` artifact, bounded evidence JSON, source/provenance values, artifact persistence, authenticated access boundary, and no-formal-insight-write safety contract remain unchanged. Symbols, market-qualified targets, source/provider IDs, fact IDs, numbers, dates, currencies, URLs, and formula/input references remain verbatim. Controlled labels, status/degraded/recovery copy, metric labels, method/frame names, and safety wording are translated deterministically; unknown dynamic English text remains visible with an explicit original/fallback marker. No LLM or external translation service is used.

Acceptance criteria for this addendum:

1. US, HK, and KR valuation create/latest responses begin with Chinese presentation and end with `## English original (原文)`.
2. The appended English body is byte-for-byte identical to the canonical English output for the same validated public projection.
3. Chinese output preserves all P0 semantics, values, source coverage, freshness, degraded/recovery state, assumptions, frame evidence, watch items, and safety wording.
4. The method library preserves ordering and specialist-only markers in both sections.
5. Artifact JSON and bounded evidence JSON schemas remain unchanged and contain no translated Markdown copy.
6. Existing path-safety, leakage, no-write, router, and gateway regressions remain green.

Only Stock Valuation P0 is implemented in this slice. Generic Command Workbench output, Weekly Review, Daily Market Brief, decision cards, messaging, locale preferences, auth, ingress, Compose, and public-port wiring remain out of scope.

## Non-Goals

- Do not automate trading.
- Do not present model output as a direct buy/sell recommendation.
- Do not require a full financial model in the first version.
- Do not reduce valuation to a single target price.
- Do not write system-inferred valuation opinions into formal user insights without user confirmation.
- Do not require a new paid data account for P0.

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

- The LLM may explain frames, assumptions, triggers, and failure conditions when available.
- The LLM should not be asked to browse the whole internet every time.
- If the valuation packet is incomplete, the output must state which frame is weak because of missing data.
- P0 calculations, frame scores, artifact generation, source coverage, and degraded output must not depend on an LLM or other model.

### Data Source Strategy

#### P0 Provider And Source Policy

P0 uses the narrowest repository-consistent source set that can produce traceable valuation packets without opening a new paid account:

- US official financial facts: SEC EDGAR first, with official company reports or investor-relations material as a bounded fallback.
- HK official financial facts: HKEXnews and official company annual/interim reports first.
- KR official financial facts: DART/FSS disclosures and official company investor-relations reports first.
- Manual or Codex-worker extraction is a bounded fallback when an official document is available but structured extraction is unavailable or unreliable. The extracted fact must retain the official document reference, extraction method, and confidence; manual or model extraction does not turn an unofficial claim into an official fact.
- Fresh price and market snapshot fields use the shared market-data path already available in the repository. P0 may use an available broker or free public fallback, but it must not require a new paid provider account.
- Every price, market-cap, enterprise-value, FX, peer, commodity, rate, or estimate field must carry its provider or source reference, observation time, currency where applicable, and freshness/stale label.
- A valid stock with a local cache miss must attempt the allowed provider-backed source path before returning a final degraded result. A provider failure remains a valid degraded outcome only when the attempted source family and missing category are named.
- Analyst estimates are optional. When present, they are labeled as estimates with source and timestamp; when absent, they are shown as a gap rather than inferred.
- Peer sets begin as manual or system-suggested candidates. They become user-confirmed only after explicit user confirmation and must remain labeled candidate otherwise.

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
- Model-discovered claims can propose leads, but they are not accepted as valuation facts until tied to a saved source or artifact.

#### Candidate Free Or Low-Cost Sources

These sources define the allowed low-cost source envelope. The technical plan should reuse the shared provider path and add only the official-source adapters needed for the P0 acceptance boundary.

| Source | Best Use | Trust | Cost | Notes |
| --- | --- | --- | --- | --- |
| SEC EDGAR APIs | US filings, submissions, XBRL company facts | Very high | Free | Best default source for US listed-company financial facts. |
| Company investor relations pages | Annual reports, presentations, earnings releases | Very high | Free | Requires crawler/extractor; source quality is high but formats vary. |
| HKEXnews | HK announcements, annual/interim reports | Very high | Free | Best default source for HK official filings and reports. |
| DART / FSS | KR disclosures, filings, and financial reports | Very high | Free public access | Best default source family for KR listed-company official facts, with company IR as an official fallback. |
| Futu OpenAPI | Holdings, user account data, possibly quotes | High for user account data | Existing integration | Good for portfolio context; quote/data licensing should be respected. |
| Alpha Vantage | Prices, fundamentals, cash flow, earnings, commodities, macro | Medium | Free tier + paid tiers | Useful fallback API; needs rate-limit handling and source audit. |
| FRED | Rates, macro, inflation, GDP, economic indicators | High | Free API key | Useful for discount-rate and macro context, not company financials. |
| Yahoo Finance / yfinance | Prices, summary data, quick peer checks | Medium-low | Free unofficial access | Useful for exploration and cheap snapshots; not an official production-grade financial source. |
| Stooq | Historical prices and index data | Medium | Free | Useful low-cost historical market data fallback. |
| Nasdaq public pages | US market calendar, earnings/IPO references | Medium | Free web access | Useful for event calendar context; scraping stability must be monitored. |

Implementation guidance:

- Start with SEC EDGAR for US financial facts.
- Start with HKEXnews and official company reports for HK financial facts.
- Start with DART/FSS and official company IR reports for KR financial facts.
- Reuse the repository's shared market-data provider path; use a configured broker source or a free public fallback only with explicit provider and freshness labels.
- Do not make P0 conditional on buying or configuring a new paid market-data account.
- Use FRED for interest-rate and macro inputs when valuation frames need discount-rate context.
- Cache every fetched payload or normalized source fact that affects valuation output.

#### Reuse Existing Stored Data First

Reuse existing database records and saved artifacts for:

- Reusable financial statements.
- Historical valuation cases.
- User-confirmed valuation views.
- Candidate peer sets and peer sets explicitly confirmed by the user.
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
- Frame scoring or selection required to produce the P0 result.
- Repeated extraction of the same financial tables.
- Silent source invention.
- Uncached peer set discovery on every query.

### Valuation Pipeline

P0 output surface:

- Primary surface: the authenticated Command Workbench using its existing preview-and-execute command path for one stock at a time.
- Command result: a concise valuation card with the selected frames, assumptions, deterministic calculations, source coverage, degraded-state explanation, and watch items.
- Artifact storage: save the packet inputs, facts, source references, calculations, all internal frame scores, the 1-3 selected frames, interpretations, freshness, and safety state under the existing research/artifact pattern before adding dedicated tables.
- Retrieval: the user can retrieve bounded evidence from the latest saved artifact for the same stock through the Command Workbench; P0 does not expose arbitrary filesystem access.
- Follow-up surfaces: weekly review, decision cards, portfolio/batch valuation, and other report or messaging integrations do not block P0 acceptance.

Interactive command:

```text
valuation SYMBOL MARKET
  -> load stock profile
  -> load cached valuation packet
  -> check stale status
  -> attempt allowed official-fact and shared market-data sources when required
  -> compute deterministic metrics
  -> score valuation frames deterministically
  -> optionally request model narrative when available
  -> return valuation card
  -> save the valuation artifact
  -> optionally create a candidate valuation case or insight for later confirmation
```

Async refresh:

```text
refresh valuation SYMBOL MARKET
  -> create valuation research job
  -> discover official sources
  -> extract financial facts
  -> compute derived metrics
  -> refresh a candidate peer set without confirming it
  -> generate valuation packet
  -> audit source coverage
  -> save artifact
```

Async refresh is a follow-up optimization unless the current-main technical plan needs it to satisfy the bounded official-source attempt. It is not a separate P0 user journey.

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

Frame scores and the selected 1-3 frames come from deterministic rules and available facts. A model may explain the result or label an alternative as inference, but it must not replace the stored score, silently change the selected frames, or be required for a usable P0 result.

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

### Evidence, Citation, And Calculation Standard

Every P0 valuation card and saved artifact must separate five layers:

- Facts: financial statement facts, market snapshots, peer rows, and relevant user-confirmed context.
- Assumptions: scenario inputs, cycle-normalization choices, peer-premium/discount reasoning, and market-implied variables.
- Calculations: deterministic metrics and reverse-implied values.
- Interpretation: rule-based or optional model explanation of why a frame may matter.
- Watch items: rerating triggers, failure conditions, and next validation steps.

Evidence rules:

- Every displayed fact carries a source ID, artifact reference, or provider reference plus timestamp when applicable.
- Every deterministic calculation links to its input fact IDs or packet fields and retains inspectable raw values even when the card uses compact formatting.
- Every stale, missing, unofficial, estimated, fallback, manually extracted, Codex-extracted, or user-provided input is labeled in source coverage.
- Any model inference is labeled as inference and cites the packet fields it used.
- Model inference, analyst estimates, user hypotheses, and candidate peer sets are not presented as confirmed facts.
- Target-price-like ranges, if present, are secondary to assumptions and show the inputs that drive the range.

Safety wording:

- Outputs are research aids, not investment advice.
- Do not use direct buy/sell/hold instructions.
- Prefer language such as "the frame may imply", "the assumption to validate is", "the data gap is", and "the watch item is".
- If evidence is too thin, say which frame cannot be supported rather than filling the gap with narrative.

### Post-P0 Optional Tables

P0 is artifact-backed and does not require a database migration. After the workflow proves useful, the product may move toward explicit storage:

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

P0 should support:

- Cached valuation packet artifact.
- Deterministic calculation of basic metrics.
- Manual or official-source financial facts.
- Frame scoring from available data.
- Useful rule-based output with optional model explanation from a compact packet.
- Clear data-gap disclosure.
- Command Workbench execution and bounded latest-artifact retrieval for one stock.

P0 should not require:

- Full automated global financial-data coverage.
- Perfect peer multiples.
- Intraday market data.
- Full Excel-style valuation model generation.
- Universal ticker/provider coverage; acceptance proves at least one supported representative stock in each P0 market (US, HK, and KR) and labels unsupported or failed source paths explicitly.
- Dedicated valuation database tables.
- Weekly-review or decision-card integration.
- Portfolio or batch valuation.
- A new paid provider account.

### Recommended Implementation Sequence

The technical implementation should be staged to avoid high token cost and unreliable output.

#### Step 1: Valuation Data Foundation

- Define a versioned valuation artifact under the repository's existing output/artifact pattern; do not gate P0 on dedicated tables.
- Implement deterministic calculations for FCF, margins, growth, EV, basic multiples, and TTM metrics.
- Build and save the compact valuation packet before any optional model interpretation.

#### Step 2: Official Financial Fact Ingestion

- US stocks: ingest SEC EDGAR companyfacts and submissions first.
- HK stocks: ingest HKEXnews annual/interim reports and official company reports first.
- KR stocks: ingest DART/FSS disclosures and official company IR reports first.
- If structured official extraction is unavailable, use bounded manual or Codex-worker extraction against the identified official document and retain extraction provenance.
- Store extracted facts with source IDs and confidence.

#### Step 3: Shared Market Snapshot Provider

- Reuse the repository's available market-data provider path and configured/free fallbacks; do not add a paid-account dependency for P0.
- The technical plan chooses the exact current-main provider order based on availability, licensing, and verified failure behavior without changing the Product contract.
- Every market snapshot must store source, timestamp, currency, and stale status.

#### Step 4: Frame Scoring Without LLM

- Implement rule-based frame scoring from stored facts and derived metrics.
- Return selected frames and data gaps even without LLM.
- This makes the valuation feature usable when model calls are disabled or expensive.

#### Step 5: LLM Explanation From Compact Packet

- Keep this optional: the deterministic P0 card and artifact must remain usable when no model is configured.
- When a model is used, send only compact valuation packets.
- Require the model to cite packet fields, data gaps, and source status.
- Forbid claims not traceable to packet data unless clearly labeled as inference.

#### Step 6: Follow-Up Async Refresh Jobs

- Add valuation refresh jobs for missing or stale packets.
- Use Codex workers for source discovery, table extraction, and audit.
- Interactive `value SYMBOL MARKET` should stay fast and avoid full web discovery.

## User Flows

### Single-Stock Valuation Research

This is the complete P0 user journey. It runs through the authenticated Command Workbench and does not depend on portfolio or batch context.

```text
User: valuation RKLB US
System:
  1. Read stock context.
  2. Load cached facts and attempt the bounded official-fact and shared market-data paths where needed.
  3. Compute reproducible metrics and deterministically rank all five core frames.
  4. Return a concise card with the 1-3 most relevant frames, assumptions, market-implied bridge when supported, triggers, failure conditions, source/freshness coverage, confidence, and degraded-state details.
  5. Save the complete valuation artifact and expose bounded latest-artifact retrieval.
  6. Keep any valuation case, peer set, or insight as a candidate until the user explicitly confirms it.
```

### Follow-Up Research Job Integration

```text
research_job
  -> official sources
  -> business facts
  -> valuation frame candidates
  -> valuation review artifact
  -> decision card
```

### Follow-Up Weekly Review Integration

Weekly review should add:

- Which holdings may have rerated this week.
- Which moves came from earnings changes versus multiple expansion.
- Which valuation assumptions were supported or challenged.
- Whether the user missed a valuation-frame switch.

This follow-up is not a P0 acceptance blocker.

## System Integration

### Data Model

P0 uses a versioned saved artifact before valuation-specific tables. The artifact must be durable enough for latest-result retrieval and future integrations, while any later schema work remains a technical follow-up.

Possible post-P0 tables include:

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

The current-main technical plan must choose the exact existing artifact root and schema version. It may not make P0 depend on adding these tables or write a valuation conclusion into `knowledge_items` as a formal user insight without explicit confirmation.

### Command Workbench Entry Points

P0 commands run through the existing Command Workbench preview-and-execute route and the shared command router. Supported intent should include:

- `valuation 000660 KR`
- `value 000660 KR`
- `how is SK Hynix valued`
- `valuation methods`
- `latest valuation 000660 KR`
- a bounded latest-artifact evidence command for acceptance and audit, scoped to the parsed stock target rather than an arbitrary path.

P0 Command Workbench behavior:

- Preview identifies the valuation action, normalized single-stock target, safety classification, and whether execution will save an artifact.
- Execute returns the concise valuation card and a saved-artifact reference without exposing local paths, raw provider errors, credentials, headers, or arbitrary file contents.
- If no cached packet exists, execution attempts the bounded provider/source path before returning a named degraded result.
- If financial facts exist but market data is missing, show supported frame logic and financial calculations while suppressing unsupported price/multiple conclusions.
- If market data exists but official financial facts are missing, show a clearly labeled low-confidence market snapshot and name the official source gap.
- If peer data is missing or stale, comparable-multiple confidence falls and no candidate peer set is treated as user-confirmed.
- If no model is available, calculations, frame scores, selected frames, source coverage, artifact saving, and degraded behavior still work.

### Follow-Up Stock Decision Card Integration

Level 1 stock decision cards should add:

```text
valuation_frame: most important current valuation frame
valuation_rerating_trigger: variable most likely to drive rerating
valuation_risk: condition that could break valuation
valuation_status: no_data / candidate / user_confirmed / stale
```

Decision-card consumption is not required for P0 acceptance.

### Follow-Up Research Draft Protocol Integration

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
2. Deliver single-stock valuation in the authenticated Command Workbench with saved and boundedly retrievable artifacts.
3. Prove official-fact attempts, shared market-data fallback, deterministic calculations and frame scores, source traceability, and useful degraded behavior for the bounded P0 markets.
4. Add decision-card, weekly-review, portfolio/batch, and dedicated-table integrations only after P0 proves useful.

The follow-up integrations may consume P0 artifact fields, but they do not block P0 acceptance.

## Acceptance Criteria

P0 acceptance criteria:

1. The authenticated Command Workbench can preview and execute a valuation command for exactly one normalized stock target and can list the valuation method library.
2. The library contains the five default core frames—FCF, Comparable Multiples, SOTP / Asset Value, Cyclical, and Growth / Scenario—and clearly marks Dividend, Residual Income / ROE-PB, and Event-Driven as specialist-only.
3. A successful execution returns a concise card with 1-3 selected core frames, not every possible frame, and saves a versioned valuation artifact for the same stock.
4. The card and artifact include key assumptions, market-implied assumptions only when supported, rerating triggers, failure conditions, confidence, source coverage, freshness/stale fields, and explicit data gaps.
5. The artifact preserves the packet inputs, displayed facts, source references, deterministic calculation inputs and results, all five internal frame scores, selected frames, interpretation provenance, watch items, degraded state, and safety state.
6. Every displayed fact has a source ID, provider reference, or artifact reference and a timestamp or reporting period when applicable; every calculated value links to inspectable input facts or packet fields.
7. US execution attempts SEC EDGAR first for official facts; HK execution attempts HKEXnews and official company reports first; KR execution attempts DART/FSS and official company IR first. A structured-source gap may use bounded manual or Codex extraction only when the official document and extraction provenance remain traceable.
8. Fresh price and market fields use the repository's available shared market-data path, require no new paid account, and show provider, timestamp, currency, and stale status. A local cache miss alone is not a final result: the allowed provider path must be attempted before degradation.
9. Calculations and frame scoring are deterministic and usable without a model. With model access unavailable, the card and artifact still contain calculations, all frame scores, selected frames, source coverage, watch items, and data gaps; optional narrative is labeled unavailable or omitted.
10. Facts, assumptions, calculations, interpretation, and watch items are visibly distinct. Model or rule inference, analyst estimates, vendor fallback fundamentals, manually extracted facts, and user hypotheses are labeled by provenance and are not presented as official confirmed facts.
11. Peer sets are candidate/manual-first. Missing or stale peer data lowers comparable-frame confidence, and no peer set or valuation case becomes user-confirmed without explicit user confirmation.
12. Missing official financial facts returns a named degraded state and does not fabricate target-price precision. Missing market data suppresses unsupported market-implied or multiple conclusions. Missing both returns a recovery-oriented card naming attempted source families and missing categories.
13. The latest saved artifact can be retrieved through a stock-scoped, bounded Command Workbench action suitable for acceptance evidence; the action cannot browse arbitrary paths or expose raw provider diagnostics, credentials, headers, stack traces, or local filesystem paths.
14. The output uses research-aid language, provides no direct buy/sell/hold instruction, and does not present optional target-price-like ranges as the center of the result.
15. No valuation inference, candidate peer set, valuation case, or candidate insight is written as a formal user insight without explicit user confirmation.
16. Weekly-review, decision-card, research-draft, portfolio/batch, dedicated-table, standalone valuation web-page, and messaging integrations are not required for P0 acceptance. The authenticated Command Workbench itself remains the required P0 surface.
17. Independent P0 surface acceptance runs from the deployed Command Workbench after current-main integration; local CLI or unit evidence alone does not satisfy the Command Workbench criteria.

## Risks

- Valuation outputs can create false precision; default to ranges and assumptions.
- One stock can be explained by multiple competing methods; show the competition.
- Without reliable financial and peer multiple data, first version should not force exact target prices.
- High-growth and real-option valuation can become narrative abuse; always show failure conditions.

## Confirmed Product Decisions

1. Use five default core frames: FCF, Comparable Multiples, SOTP / Asset Value, Cyclical, and Growth / Scenario.
2. Keep Dividend, Residual Income / ROE-PB, and Event-Driven as specialist frames that appear only when clearly triggered.
3. Put valuation explanation before target price.
4. P0 is a single-stock Command Workbench workflow with a saved valuation artifact and bounded latest-artifact retrieval.
5. P0 is artifact-backed before dedicated valuation tables.
6. Official facts use SEC EDGAR first for US, HKEXnews/company reports first for HK, and DART/FSS/company IR first for KR. Manual or Codex extraction is a bounded, provenance-preserving fallback.
7. Market snapshots reuse the repository's shared available provider path with source/freshness labeling and no new paid-account dependency.
8. Peer sets are candidate/manual-first and become user-confirmed only after explicit confirmation.
9. Calculations and frame scoring have no model dependency; optional model narrative operates only on the compact packet and stays labeled as interpretation.
10. Missing local data triggers bounded provider attempts before deterministic degradation. Missing or stale categories are named, not silently filled.
11. Weekly-review, decision-card, research-draft, portfolio/batch, dedicated-table, standalone valuation web-page, and messaging integrations are follow-ups, not P0 acceptance blockers; the Command Workbench remains P0.
12. The product never writes valuation inference into formal user insights without confirmation and never presents its output as investment advice.

## Non-Blocking Technical-Plan Decisions

The current-main technical plan may choose the exact artifact filename/schema, shared-provider order, synchronous versus asynchronous refresh boundary, and extraction implementation. Those choices must satisfy the confirmed Product decisions and acceptance criteria above; none requires another Product or Owner decision.

## Research Sources

- CFA-style equity valuation frameworks: income, market, and asset approaches.
- Aswath Damodaran valuation framing: intrinsic value, relative value, and real options.
- Standard DCF literature: explicit forecast period plus terminal value.
- Relative valuation and multiples frameworks: peer group, standardized multiples, and comparability.
- Residual income valuation: book value plus present value of future residual income.
- Sum-of-the-parts valuation: segment-level valuation for conglomerates and holding companies.
- Real options valuation: value of managerial flexibility under uncertainty.
