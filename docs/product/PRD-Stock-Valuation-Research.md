# PRD: Stock Valuation Research

Status: ready for technical planning. P0, P0.1, and P0.2 are accepted; P0.3 product addendum is ready for technical planning.

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

- Build a user-confirmed valuation method library.
- For one stock at a time, identify the 1-3 most relevant valuation frames.
- Explain the assumptions that support each frame.
- Show what current market price may imply.
- Identify rerating triggers and valuation failure conditions.
- Save a valuation research artifact that can later feed stock decision cards, research jobs, and weekly reviews.

P0 is intentionally a single-stock valuation research workflow. Portfolio-level or batch valuation is deferred until the single-stock packet, calculation, citation, and degraded-state behavior is reliable.

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

#### P0 Provider And Source Policy

P0 should use the narrowest provider set that can produce traceable valuation packets:

- Official filings and financial statements are the preferred source for financial facts. Use SEC EDGAR for US listed companies when available, HKEXnews or official company reports for HK listed companies when available, and company investor-relations reports for other markets when no structured regulator source exists.
- Market data can use the cheapest available repo-consistent provider path, but every price, market-cap, enterprise-value, FX, peer-multiple, commodity, or rate field must carry a provider name, source ID or artifact path, timestamp, currency, and stale-status label.
- Analyst estimates are optional in P0. Include them only when a source is available with a timestamp and label them as estimates, not facts. If no analyst-estimate provider exists, omit the field and show a data gap instead.
- User knowledge, prior research, portfolio context, and candidate insights may influence frame selection, but they must be labeled separately from official facts and market data.
- Unofficial or wrapper sources can be used for low-cost market snapshots and exploration, but they must not silently overwrite official financial facts.
- When a provider is unavailable, rate-limited, stale, or missing a metric, the output should degrade to a lower-confidence frame explanation, list the missing data, and avoid target-price precision.

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
- LLM-discovered claims can propose leads, but they are not accepted as valuation facts until tied to a source ID or saved artifact.

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

P0.1 user-acceptance correction:

- User acceptance on 2026-07-04 showed that a valuation card that only reports missing local facts is not sufficient for real review, even if the degraded behavior is technically correct.
- For US stocks, the command flow should attempt a provider-backed valuation packet before returning the final card: SEC EDGAR company facts for official financial metrics, plus a low-cost Yahoo quote snapshot for current price, market cap, shares outstanding, currency, and timestamp.
- Provider facts must be labeled by source and timestamp, merged into deterministic calculations, and preserved in the saved artifact.
- If SEC or Yahoo data is unavailable, the output should remain safe and degraded, but it must name the provider gap instead of implying that no better data source exists.
- Cloud-IP acceptance must be rerun after this correction before asking for final user acceptance.

## P0.2 Addendum: Market-Implied Bridge And Readable Output

Status: ready for technical planning.

P0.1 user acceptance remains accepted. P0.2 is a product-quality refinement for the same command-surface valuation card and saved artifact. It should make the valuation output easier to read, make provider-gap copy stable, and answer the user's deeper valuation question: which frame can plausibly bridge current market cap or enterprise value to the assumptions the market appears to be trading?

### P0.2 User Journey

The user runs an existing valuation command such as `valuation US.INTC`, `value US.INTC`, or `估值 US.INTC`.

The output should first show a compact, readable valuation snapshot:

```text
Market cap: $601.1B
Enterprise value: $595.0B
Revenue: $52.6B
FCF margin: -9.4%
P/S: 11.4x
EV/FCF: not meaningful (negative FCF)
Data status: official financials available; market snapshot partial provider gap
```

Then the output should show a market-implied bridge:

- What the current market cap or EV implies using available data.
- Which valuation frame best fits the current market value.
- Which frames do not fit without aggressive or unavailable assumptions.
- What must become true for the best-fitting frame to remain plausible.

For example, if current earnings and FCF are negative or weak but market cap is high, the product should not normalize raw negative multiples as if they were ordinary valuation ratios. It should explain whether the current value is better understood through revenue multiple, margin recovery, cycle-normalized earnings, future FCF margin, or a growth/scenario frame. If the required bridge cannot be computed because key inputs are missing, the output should name the missing input and keep the bridge qualitative.

### Readable Number Formatting

P0.2 output should format numbers for investment readability:

- Currency and large absolute values: `$601.1B`, `$52.6B`, `$1.2M`, with currency shown when known.
- Percentages: `-9.4%`, `18.2%`.
- Multiples and ratios: `11.4x`, `0.8x`.
- Per-share values, if shown: `$12.34/share`.
- Raw full-precision floats should not appear in the user-facing card.
- Saved artifacts may preserve raw numeric values, but they should also include display values or enough metadata for deterministic formatting.

Formatting should not create false precision. Use one decimal place for large headline values and percentages by default; use two decimals only when the unit or magnitude requires it. If currency, unit, or scale is unknown, label the value as unknown rather than guessing.

### Provider-Gap Taxonomy

P0.2 should use a stable provider-gap taxonomy so partial data does not read like total failure.

Use these labels:

- `complete_missing`: no usable data was available for that provider category.
- `partial_provider_gap`: some provider fields were usable, but another provider call, endpoint, or field failed.
- `fallback_used`: a lower-priority provider or cached/snapshot value was used because the preferred path was unavailable.
- `stale_or_unknown_freshness`: data exists, but timestamp or freshness is stale or unknown.

Product copy rules:

- Do not say "market data missing" when price, market cap, or shares are present but a quote-detail call failed.
- Do not hide a provider error if it affects confidence or available fields.
- Do not show raw HTTP/provider errors as the main user-facing message. Translate them into the taxonomy and keep raw details in artifact diagnostics.
- Each provider category should have one status and a short explanation, for example: `Market snapshot: partial provider gap. Yahoo market-cap and price fields are available, but Yahoo quote detail returned unauthorized, so quote freshness is lower confidence.`
- Provider status should distinguish official financial facts from low-cost market snapshots and from model interpretation.

### Negative Or Meaningless Ratio Handling

P0.2 should avoid presenting negative valuation multiples as normal ratios.

Rules:

- If earnings are negative, show PE as `not meaningful (negative earnings)`.
- If free cash flow is negative, show EV/FCF and FCF yield as `not meaningful (negative FCF)`, while still showing FCF amount and FCF margin as operating facts.
- If EBITDA is negative, show EV/EBITDA as `not meaningful (negative EBITDA)`.
- If denominator data is missing or zero, show `not available` with the missing input.
- Negative margins are meaningful operating metrics and may be shown as percentages. Negative valuation multiples are not meaningful as ordinary valuation ratios.
- Artifacts may preserve raw calculated values for audit, but the user-facing card should use the meaningfulness label.

### Current Market Cap / EV Bridge

P0.2 should add a deterministic or semi-deterministic bridge from current market value to implied assumptions when the required inputs exist.

The bridge should prefer the simplest useful implication for the available data:

- Revenue available and market cap/EV available: show implied price-to-sales or EV-to-sales, and the revenue scale or multiple required for the current value to make sense.
- FCF available and market cap/EV available: show FCF yield when FCF is positive; when FCF is negative, show the FCF margin or future FCF level required for a selected yield assumption only if the assumption is explicitly labeled.
- Revenue plus negative FCF available: show required future FCF margin for illustrative yields such as 3%, 5%, and 7%, clearly labeled as bridge math, not a target price.
- Net income negative or depressed: do not show PE as meaningful; consider cycle-normalized earnings or margin recovery only when there is a current-cycle, sector, or profile signal.
- Cyclical stocks: if current earnings look depressed or peak-like, explain whether the current value requires mid-cycle earnings recovery, upcycle duration, or cycle-normalized margins.
- Growth/scenario stocks: if current profit cannot support the market value, explain the revenue growth, TAM penetration, margin maturity, or milestone probability needed for the scenario frame.
- SOTP/asset-heavy stocks: if segment or asset data is missing, mark the SOTP bridge as unsupported instead of inventing segment values.

The bridge should not require peer-set sourcing, analyst estimates, or a full normalized multi-year financial table in P0.2. If those would materially improve the answer, list them as follow-up validation inputs.

### Frame Fit Ranking

P0.2 should rank frames by fit to current market value, not only by generic relevance.

Each selected frame should include:

```text
frame
fit_to_current_market_value: fits / partial_fit / does_not_fit / insufficient_data
why_it_fits_or_not
implied_assumptions
assumptions_that_must_become_true
main_data_gaps
confidence
```

Product interpretation rules:

- "Best fit" means the frame most plausibly explains the current market cap or EV with available evidence, not the frame that is most attractive.
- A frame may be relevant to the business but fail to bridge current market value.
- If all frames are weak, say so and identify the least-bad explanatory frame.
- For stocks like INTC where one visible method may dominate current calculations but the market may be trading expectations, the card should explicitly say which expectation-based bridge is needed, such as margin recovery, foundry/AI optionality, cycle-normalized earnings, or revenue multiple support.

### Safety And Memory Boundaries

P0.2 remains a research-aid feature:

- Do not provide direct buy, sell, hold, or position-sizing advice.
- Do not present precise target prices unless they are sourced, confirmed, and secondary to assumptions.
- Do not write formal user insights, valuation cases, or memory records without explicit user confirmation.
- Candidate valuation interpretation may be saved in the valuation artifact, but it must remain candidate research until confirmed.

### P0.2 Acceptance Criteria

1. User-facing valuation output uses readable number formatting for currency, percentages, multiples, and per-share values; raw long floats do not appear in the command card.
2. Negative earnings, negative FCF, and negative EBITDA do not produce ordinary negative PE, EV/FCF, FCF-yield, or EV/EBITDA ratios; the card shows `not meaningful` with the reason.
3. Provider status uses the P0.2 taxonomy and distinguishes complete missing data from partial provider gaps, fallback data, and stale or unknown freshness.
4. A partial provider gap does not contradict available data. If market cap or price is present while a quote-detail call fails, the card says market snapshot is partially available and names the failed part.
5. The saved artifact preserves provider diagnostics, raw numeric inputs, display-ready values or formatting metadata, calculation meaningfulness, and frame-fit bridge fields.
6. When market cap or EV and at least one operating anchor are available, the output includes a market-implied bridge such as current sales multiple, required FCF margin, implied FCF yield, required margin recovery, cycle-normalized earnings need, or scenario-growth assumption.
7. When bridge inputs are missing, the output names the missing inputs and avoids target-price precision.
8. Selected frames include a fit ranking against current market value: best fit, partial fit, does not fit, or insufficient data.
9. The output explains which assumptions must become true for the best-fitting frame to support the current market value.
10. The output identifies relevant frames that do not fit current market value and explains why without dismissive or advisory language.
11. The feature continues to show source coverage, stale fields, confidence, no-advice wording, and no formal user-insight-write behavior.
12. Peer set sourcing, analyst estimates, normalized multi-year financial tables, async refresh, and user-confirmed valuation-case workflow are not required for P0.2 acceptance unless Engineering finds one is strictly necessary to satisfy the market-implied bridge.

## P0.3 Addendum: Non-US Valuation Provider Coverage

Status: ready for technical planning.

P0, P0.1, and P0.2 remain accepted and must not be reopened. P0.3 is a new provider-coverage addendum for non-US listed stocks where the accepted US-only provider path is not enough. The first implementation scope is conservative: support Korea and Hong Kong well enough for useful single-stock valuation reports, with `KR.000660` / SK hynix and `HK.01888` / 建滔積層板控股有限公司 / Kingboard Laminates Holdings Limited as the first acceptance fixtures.

Product mapping notes:

- SK hynix maps to internal target `KR.000660`; the first Yahoo/yfinance-style market snapshot candidate is `000660.KS`; reporting currency should be `KRW`.
- 建滔積層板 / Kingboard Laminates maps to HKEX stock code `1888`, displayed internally as `HK.01888` when the command parser normalizes Hong Kong codes to five digits; the first Yahoo/yfinance-style market snapshot candidate is `1888.HK`; reporting currency should be `HKD`.
- Engineering must preserve both the user-entered target and the resolved provider ticker in the output, for example `Input: 建滔积层板 HK -> resolved: HK.01888 Kingboard Laminates Holdings Limited -> market snapshot ticker: 1888.HK`.
- If Engineering discovers that a provider requires a different exchange suffix, code format, or entity mapping, the card and artifact must show the attempted mapping and the selected mapping instead of silently substituting another stock.

### P0.3 Minimum Useful Report

A P0.3 non-US valuation card must not stop at "unknown currency" or a generic provider gap. The minimum useful report for a supported KR or HK stock is:

- Resolved ticker and entity mapping: input text, normalized internal symbol/market, company name, provider market ticker, exchange/market, and mapping confidence or mapping source.
- Currency-labeled market snapshot when available: latest price, market cap, shares outstanding when available, currency, provider, snapshot timestamp or stale/unknown freshness label, and any FX note if later frames compare across currencies.
- Official or company financial source coverage: whether official financial facts were available, partially available, or missing, with source family and attempted provider/source named.
- Valuation snapshot: revenue, net income, operating cash flow, capex/free cash flow, cash, debt/net debt, shares, and enterprise value only where inputs exist; every value must carry `HKD`, `KRW`, or an explicit source currency.
- Deterministic ratios where inputs exist: P/S, PE, FCF margin, FCF yield, EV/sales, EV/FCF, net debt, and other P0/P0.2 ratios, with `not meaningful` labels for negative earnings, negative FCF, negative EBITDA, zero denominators, or missing denominators.
- Market-implied scenario or bridge: explain whether current market cap or EV is being bridged by sales multiple, normalized earnings, FCF recovery, cyclical duration, HBM/cycle expectations, segment/asset value, or another selected P0 frame. The bridge may be partially qualitative only when the missing inputs are named.
- Source coverage and degraded-state section: show official financials, market snapshot, provider mapping, peer/estimate availability, and user-confirmed valuation-case status as separate categories.
- Safety line: research aid only, no direct buy/sell/hold recommendation, no formal user insight written without confirmation.

### P0.3 Source Policy

Market snapshot:

- Use Yahoo/yfinance-style exchange ticker mapping where available for low-cost market snapshots, starting with `000660.KS` for SK hynix and `1888.HK` for Kingboard Laminates if provider verification succeeds.
- Market snapshot facts are vendor-labeled market data. They may support price, market cap, shares outstanding, quote currency, quote timestamp, and stale status.
- If the snapshot provider returns partial data, use P0.2 taxonomy such as `partial_provider_gap` and name the missing category without raw HTTP/provider diagnostics.

Official or company financials:

- HK listed companies: prefer HKEXnews filings, annual/interim reports, and official company investor-relations reports. HKEXnews or official company reports are the authoritative source for financial-statement facts.
- KR listed companies: prefer DART/FSS filings, company investor-relations reports, or explicitly sourced company reports. Company IR and regulator filings are authoritative for financial-statement facts.
- Yahoo/yfinance fundamentals may be used only as vendor-labeled fallback facts, not as official/regulator facts. The output must not describe yfinance fundamentals as audited, official, HKEX, DART, FSS, or company-reported unless the underlying source is separately verified.
- User knowledge and existing research may influence frame selection, but it must be labeled separately from official financial facts and market data.

Missing data labeling:

- Missing data must be labeled by category: `provider_mapping`, `market_snapshot`, `official_financials`, `cash_flow_statement`, `balance_sheet`, `shares_outstanding`, `enterprise_value_inputs`, `peer_multiples`, `analyst_estimates`, `valuation_case`, or `freshness`.
- User-facing output must not show raw provider errors, exception classes, endpoint URLs, auth/header text, local paths, or stack traces. Raw diagnostics may remain only in protected artifact internals when needed for debugging.

### P0.3 Degraded Behavior

P0.3 should allow transparent partial reports, but only when enough data remains to help the user think about valuation.

- If market snapshot exists but official financials are missing, show the currency-labeled market snapshot, explain that deterministic operating ratios are blocked by missing official/company financial facts, and offer a refresh/source-discovery path. Do not present this as a full valuation report.
- If official/company financials exist but market snapshot is missing, show sourced financial facts and frame relevance, but mark market-implied bridge, market cap, EV, and market multiples as unavailable because the market snapshot provider failed or is missing.
- If both official/company financials and market snapshot are missing, return a recovery card that lists attempted source families and missing categories; it is not a usable valuation report and must not show `unknown currency` as if it were a valid report.
- If provider mapping is ambiguous or unverified, return candidates or a mapping-confirmation card rather than running valuation against the wrong entity.
- If only vendor-labeled fallback fundamentals are available, the card may compute provisional ratios, but must label them as vendor fallback, lower confidence, and not official/regulator facts.
- If current data supports only one narrow bridge, show that bridge and explicitly list follow-up inputs needed for stronger frames, such as official cash flow, net debt, segment revenue, HBM/cycle evidence, or peer multiples.

### P0.3 Acceptance Criteria

1. `valuation KR.000660` and `valuation 000660 KR` resolve to SK hynix, display the normalized target `KR.000660`, the provider market ticker attempted or used, and `KRW` currency labels for market and financial facts when available.
2. `valuation 建滔积层板 HK`, `valuation HK.01888`, and `valuation 1888 HK` resolve or ask for confirmation as Kingboard Laminates Holdings Limited / 建滔積層板控股有限公司, display normalized target `HK.01888`, provider market ticker attempted or used, and `HKD` currency labels when available.
3. The prior SK hynix output fails P0.3 if it only reports a US-only provider gap, unknown currency, no provider ticker mapping, or no category-level source coverage.
4. The prior HK missing output fails P0.3 if it cannot map 建滔積層板/Kingboard Laminates to HK code `1888`/`HK.01888`, or if it stops at generic missing provider text without attempted HK market snapshot and official-source categories.
5. For supported KR/HK fixtures, the card distinguishes market snapshot provider data from official/company financial facts and from vendor-labeled fallback fundamentals.
6. HK official financial source attempts are labeled as HKEXnews and/or official company reports; KR official financial source attempts are labeled as DART/FSS, company IR, or explicitly sourced company reports.
7. Yahoo/yfinance fundamentals, if used, are labeled as vendor fallback and never presented as official/regulator facts.
8. Currency formatting uses `HKD` and `KRW` prefixes or labels consistently; no user-facing valuation report may treat `unknown currency` as usable for market cap, revenue, FCF, net debt, or ratios.
9. Deterministic ratios are computed only when their inputs exist and share a compatible currency basis; negative or missing denominator behavior follows P0.2 meaningfulness rules.
10. When market cap/EV and at least one operating anchor exist, the output includes a market-implied bridge. For SK hynix, the bridge should be able to discuss sales multiple, cycle-normalized earnings, FCF recovery, and HBM/memory-cycle expectations when relevant inputs or sourced context exist. For Kingboard Laminates, the bridge should be able to discuss sales/earnings/cash-flow support and cyclical laminate/PCB-material expectations when relevant inputs exist.
11. When bridge inputs are missing, the output names the missing categories and attempted providers/sources, and avoids target-price precision.
12. Source coverage is visible in the card and artifact: provider mapping, market snapshot, official/company financials, deterministic calculations, fallback fundamentals, peer/estimate availability, and stale/unknown freshness.
13. User-facing degraded copy contains no raw HTTP/provider diagnostics, endpoint URLs, exception fragments, auth/header text, local paths, stack traces, or arbitrary file-read content.
14. Bounded artifact evidence, if available for P0.3, preserves mapping, source coverage, raw numeric facts, display values, calculation meaningfulness, market-implied bridge, and degraded categories without exposing unsafe diagnostics.
15. P0.3 does not require broad global market coverage, peer-set sourcing, analyst estimates, async refresh, or user-confirmed valuation-case workflow beyond the KR/HK fixture scope unless Engineering finds one of those is strictly necessary to produce the minimum useful report.

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

P0 output surface:

- Primary surface: command retrieval through the existing command/MCP style, returning a concise valuation card and saving a valuation artifact.
- Artifact storage: save the packet, deterministic calculations, selected frames, source coverage, and narrative output under the repository's existing research/artifact pattern before adding dedicated tables.
- Retrieval: users should be able to rerun or inspect the latest saved valuation artifact for a stock.
- Later surfaces: decision-card, weekly-review, web, and DingTalk integrations are follow-up surfaces after P0 valuation packets are reliable.
- No P0 cloud/web acceptance surface is required unless Engineering explicitly adds one.

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

### Evidence, Citation, And Calculation Standard

Every P0 valuation output must separate five layers:

- Facts: financial statement facts, market snapshots, peer rows, user portfolio context, and user knowledge items.
- Assumptions: scenario inputs, cycle-normalization choices, peer-premium/discount reasoning, and market-implied variables.
- Calculations: deterministic metrics and reverse-implied values.
- Interpretation: model or rule-based explanation of why a frame may matter.
- Watch items: triggers, failure conditions, and next validation steps.

Evidence rules:

- Every fact shown in the user-facing output must carry a source ID, artifact path, or provider reference plus timestamp when applicable.
- Every deterministic calculation must link to its input fact IDs or packet fields.
- Every stale, missing, unofficial, or user-provided input must be labeled in the source coverage section.
- Any model inference must be labeled as inference and must cite the packet fields it used.
- The product must not present model inference, analyst estimates, or user hypotheses as confirmed facts.
- Target-price-like ranges, if present, must be secondary to assumptions and must show the inputs that drive the range.

Safety wording:

- Outputs are research aids, not investment advice.
- Do not use direct buy/sell/hold instructions.
- Prefer language such as "the frame may imply", "the assumption to validate is", "the data gap is", and "the watch item is".
- If evidence is too thin, say which frame cannot be supported rather than filling the gap with narrative.

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

P0 should not try to solve everything. It should support:

- Cached valuation packet artifact.
- Deterministic calculation of basic metrics.
- Manual or official-source financial facts.
- Frame scoring from available data.
- LLM explanation from compact packet.
- Clear data-gap disclosure.

P0 should not require:

- Full automated global financial-data coverage.
- Perfect peer multiples.
- Intraday market data.
- Full Excel-style valuation model generation.
- Portfolio-level or batch valuation.
- Web or DingTalk delivery.

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

This is the P0 user journey and should be implemented before portfolio or batch valuation.

```text
User: value RKLB US
System:
  1. Read stock context.
  2. Read knowledge items, sources, research drafts, and portfolio status.
  3. Identify candidate valuation frames.
  4. Output a concise valuation-frame matrix.
  5. Explain the most likely rerating path.
  6. Save a valuation artifact with source coverage, calculation inputs, selected frames, assumptions, interpretation, and watch items.
  7. Generate candidate valuation insights for user confirmation.
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
- `show valuation artifact 000660 KR`
- `confirm valuation case 12`
- `show valuation case 000660 KR`

P0 command behavior:

- If no valuation packet exists, return a clear missing-packet response and offer to create or refresh valuation research.
- If financial facts exist but market data is missing, show frame selection and financial-derived metrics while marking market-implied assumptions as unavailable.
- If market data exists but official financial facts are missing, show a low-confidence market snapshot and create a refresh path for official facts.
- If the LLM/model is unavailable, return deterministic frame scores, source coverage, calculations, and data gaps without narrative interpretation.

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

P0 acceptance criteria:

1. The system can list the valuation method library with five default core frames and specialist frames clearly marked as specialist-only.
2. For a single stock, the system can produce a valuation research artifact and concise command output with the 1-3 most relevant frames, not all possible frames.
3. The output includes key assumptions, market-implied assumptions when data allows, rerating triggers, failure conditions, source coverage, stale fields, and confidence.
4. The output clearly separates facts, assumptions, deterministic calculations, model/rule interpretation, and watch items.
5. Every displayed fact has a source ID, provider reference, or artifact path plus timestamp when applicable.
6. Every deterministic metric links to its input facts or packet fields.
7. Missing financial facts produce an explicit degraded state and do not block the feature from returning available frame logic.
8. Missing market data suppresses market-implied assumptions and price/multiple conclusions, while still showing financial-fact-based frames where possible.
9. Stale or unavailable peer data is labeled and lowers confidence; the output must not silently use stale peer multiples as current data.
10. If the LLM/model is unavailable, the command still returns deterministic frame scores, calculations, source coverage, and data gaps, and labels narrative interpretation as unavailable.
11. If no user-confirmed valuation case exists, the output is labeled as a candidate valuation view and is not treated as confirmed user knowledge.
12. The system does not write valuation inference into formal user insights without user confirmation.
13. The output uses research-aid language and does not present direct investment advice.
14. Weekly review and decision-card integration are not required for P0 acceptance, but the artifact should expose fields that later integrations can consume.
15. Portfolio or batch valuation is not required for P0 acceptance.

## Risks

- Valuation outputs can create false precision; default to ranges and assumptions.
- One stock can be explained by multiple competing methods; show the competition.
- Without reliable financial and peer multiple data, first version should not force exact target prices.
- High-growth and real-option valuation can become narrative abuse; always show failure conditions.

## Confirmed Product Decisions

1. Use five default core frames: FCF, Comparable Multiples, SOTP / Asset Value, Cyclical, and Growth / Scenario.
2. Keep Dividend, Residual Income / ROE-PB, and Event-Driven as specialist frames that appear only when clearly triggered.
3. Put valuation explanation before target price.
4. P0 is single-stock valuation research before portfolio or batch valuation.
5. P0 primary surface is command retrieval plus saved valuation artifact/report storage.
6. Web, DingTalk, weekly-review, and decision-card integrations are later surfaces after P0 packet quality is proven.
7. Build the feature as a valuation packet system, not an LLM-first valuation chat.
8. P0 may start with artifact-backed valuation packets before dedicated valuation tables, as long as artifacts preserve source IDs, timestamps, input fields, deterministic calculations, and selected frames.
9. Official financial facts should use SEC EDGAR for US stocks first, HKEXnews or official company reports for HK stocks first, and company investor-relations reports or user/manual extraction for other markets.
10. The first market snapshot provider should be the repo-consistent low-cost path Engineering can verify fastest; Futu can be used if licensing/availability is acceptable, otherwise Alpha Vantage, Yahoo/yfinance, or Stooq may be used with clear unofficial/stale labeling.
11. HKEX annual/interim extraction can start with Codex-worker or manual artifact extraction when scripting the full report parser would delay P0.
12. Peer sets should start as system-suggested candidate peer sets and become user-confirmed only after explicit user confirmation.
13. Analyst estimates are optional for P0 and must be labeled as estimates when present.
14. P0 must have deterministic degraded behavior when financial facts, market data, peer data, model access, or user-confirmed cases are missing.

## Non-Blocking Follow-Ups For Technical Design

- Decide the exact file path and schema for P0 valuation artifacts.
- Decide whether the first implementation adds dedicated valuation tables immediately or keeps them as a follow-up migration after artifact-backed P0 is validated.
- Choose the first market snapshot provider based on available repo credentials, licensing, rate limits, and implementation cost.
- Decide which recurring source refreshes should run synchronously in commands versus asynchronously in research jobs.

## Research Sources

- CFA-style equity valuation frameworks: income, market, and asset approaches.
- Aswath Damodaran valuation framing: intrinsic value, relative value, and real options.
- Standard DCF literature: explicit forecast period plus terminal value.
- Relative valuation and multiples frameworks: peer group, standardized multiples, and comparability.
- Residual income valuation: book value plus present value of future residual income.
- Sum-of-the-parts valuation: segment-level valuation for conglomerates and holding companies.
- Real options valuation: value of managerial flexibility under uncertainty.
