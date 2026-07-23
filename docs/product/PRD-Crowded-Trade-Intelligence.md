# PRD: Crowded Trade Intelligence

Status: discovery draft; not ready for implementation
Owner: Product Discovery Coordinator
Feature Registry row: Crowded Trade Intelligence
Linked technical feasibility note: [`../techplans/crowded-trade-intelligence-feasibility.md`](../techplans/crowded-trade-intelligence-feasibility.md)
Last updated: 2026-07-23

## 1. Decision Summary

Crowded Trade Intelligence should estimate whether a portfolio-relevant position appears crowded using several independent evidence families. It must not equate a high valuation, a rising price, high short-sale volume, or social popularity with crowding on its own.

Recommended V1:

- Scope the universe to current portfolio holdings, with an explicit single-symbol investigation path.
- Run end-of-day rather than intraday.
- Produce separate `long crowding`, `short crowding / squeeze pressure`, and `speculative attention` assessments. Do not collapse opposite positioning into one directional trade instruction.
- Use a hybrid source model:
  - reuse existing portfolio, bar, official-filing, event, provenance, fallback, and degraded-state contracts;
  - add approved official/regulatory sources;
  - use existing Futu OpenAPI and approved OpenDART access only where the deployed account or API key has the required entitlements and the intended internal use is permitted;
  - add premium securities-lending or global fund-flow data only after the Owner approves budget, credentials, and licence terms.
- Launch US and HK as the first markets eligible for a full likelihood band when sufficient evidence is present.
- Show KR and CN evidence cards in the same portfolio report, but return `insufficient evidence for a crowding likelihood` until the required official API/data rights and minimum family coverage are verified.
- Keep social/retail attention optional and non-blocking. Do not scrape Reddit, X, Xueqiu, broker communities, or search pages.
- Surface a likelihood band and evidence quality, not a trading recommendation or a falsely precise probability.

This feature is not ready for implementation. The product and data decisions in section 15 must be explicit first.

## 2. User Problem

The user already cares about portfolio concentration and crowded themes. Existing weekly review and decision-card flows can say that a theme may be crowded, but the system cannot yet show why that claim is credible.

A useful crowding assessment must answer:

1. Which kind of crowd is visible: concentrated long ownership, short positioning, leveraged/options speculation, fund inflows, or attention?
2. What evidence supports that interpretation?
3. How current and complete is the evidence?
4. What counterevidence argues against the crowding hypothesis?
5. Which conclusions are unavailable because the relevant market does not publish comparable data?
6. Is a near-term event likely to make an unwind or squeeze more fragile?

The product must help the user investigate those questions without turning noisy proxies into certainty.

## 3. Product Positioning

Crowded Trade Intelligence is:

> A read-only, provenance-first portfolio risk research aid that estimates direction-specific crowding likelihood from multiple independent signals and explains the evidence, counterevidence, freshness, and missing data.

It is not:

- a buy, sell, hold, trim, hedge, or timing recommendation;
- a valuation label;
- a social-media sentiment score;
- a claim that a crowded trade must reverse;
- a claim that high short interest is bearish;
- a claim that call open interest is bullish or dealer gamma is known;
- a cross-market ranking that treats incomparable data as equivalent;
- an automated trading or alerting system in V1.

## 4. Product Principles

### 4.1 Multi-signal or no conclusion

A likelihood band requires at least three independent signal families, including:

- price/volume/liquidity; and
- at least one direct or higher-quality positioning family, such as ownership, short interest/securities lending, options positioning, fund flows, or derivatives positioning.

Price plus valuation plus social attention does not satisfy the requirement. Missing data is never scored as zero.

### 4.2 Direction matters

The product must distinguish:

- `long crowding`: many holders or flows appear aligned on the long side;
- `short crowding / squeeze pressure`: short positions, borrow demand, or days-to-cover appear elevated;
- `speculative attention`: options, turnover, search, or social activity is unusually intense but direction is uncertain;
- `two-sided crowding`: both long and short positioning or opposing speculative signals are elevated.

An instrument may be crowded on both sides. The product must preserve that ambiguity.

### 4.3 Explanation before score

Every displayed likelihood must show:

- the strongest supporting evidence;
- material counterevidence;
- the observation and publication dates;
- source and metric semantics;
- market-relative comparison group;
- coverage and freshness;
- why the conclusion is a likelihood rather than a fact.

### 4.4 No false comparability

FINRA short interest, HK SFC reportable short positions, KRX net short positions, and mainland margin/securities-lending balances are not identical metrics. They may inform the same family but must retain market-specific semantics.

Daily short-sale turnover or volume is not a substitute for open short interest. Options open interest is not signed investor direction. ETF trading turnover is not fund flow.

### 4.5 Safe degradation is a product result

When coverage is weak, the correct result is:

> Insufficient evidence for a crowding likelihood. Two signal families are current, while ownership and direct positioning data are unavailable or stale. The observations below are useful context but do not establish that this trade is crowded.

The product should still show available evidence and the exact gap. It must not silently renormalize a thin dataset into a high-confidence score.

## 5. Goals

### 5.1 V1 goals

- Assess current portfolio holdings once per requested report using the latest completed market sessions.
- Support explicit single-symbol investigation.
- Use deterministic signal calculations and source-admission rules.
- Produce direction-specific likelihood bands only when coverage gates pass.
- Explain evidence, counterevidence, provenance, freshness, legal-use class, and missing categories.
- Keep market comparisons inside valid market, sector/industry, and liquidity cohorts.
- Reuse the repository's provider-neutral data-source contracts and official-source patterns.
- Degrade safely when a provider, entitlement, licence, symbol, or metric is unavailable.
- Preserve the no-investment-advice and no-formal-user-insight-write boundaries.

### 5.2 Later goals

- Calibrate likelihood bands against defined crowding/unwind outcomes.
- Add theme- and sector-level overlap analysis.
- Add licensed global securities-lending and fund-flow feeds.
- Add recurring weekly-review integration after single-report quality is accepted.
- Add low-noise change detection and alerts only after false-positive rates are measured.

## 6. Non-Goals

- Intraday alerts or high-frequency surveillance.
- Trade execution, order preparation, or portfolio rebalancing.
- A global "most crowded stocks" screener.
- A numeric target price or expected return.
- Predicting when a crowded trade will unwind.
- Dealer gamma exposure claims without a licensed, directionally classified dataset and documented methodology.
- Scraping websites or communities that do not provide approved programmatic access.
- Treating aggregate fund flows as security-level ownership without a traceable allocation method.
- ETF look-through overlap when holdings rights and effective dates are unavailable.
- A universal cross-market score before comparable data and calibration exist.

## 7. Approaches Considered

### 7.1 Public-only, broad-market score

Use public exchange pages, filings, free price data, and attention proxies across all four markets.

Advantages:

- low direct data spend;
- visually broad coverage.

Problems:

- strong differences in publication lag and metric meaning;
- automated access or redistribution may not be permitted;
- weak securities-lending and fund-flow evidence;
- high risk of substituting activity proxies for positions;
- likely to produce a polished but unreliable cross-market ranking.

Decision: rejected as the product default.

### 7.2 Hybrid official plus existing entitled sources

Use current portfolio and bar contracts, official filings/regulatory datasets, and Futu interfaces where the deployment has lawful entitlements. Return market-specific degraded states where direct positioning is missing.

Advantages:

- reuses current architecture;
- delivers credible US/HK evidence without immediately requiring an institutional data contract;
- keeps source and market semantics visible;
- supports a clean premium-data upgrade path.

Problems:

- asymmetric market coverage;
- credentials and legal-use confirmation still required;
- true borrow cost/utilization and global fund flows remain incomplete.

Decision: recommended V1.

### 7.3 Licensed institutional data stack

Contract a global securities-finance feed, fund-flow feed, and granular options-flow product.

Advantages:

- best direct positioning coverage and cross-market consistency;
- enables borrow-cost, utilization, supply concentration, flow, and participant-type evidence;
- better foundation for later calibration.

Problems:

- spend, procurement, data storage, derived-data, display, redistribution, and user-count terms;
- integration and entitlement operations;
- vendor coverage still needs instrument-level validation for CN/KR/HK.

Decision: preferred upgrade path, not a default V1 dependency.

## 8. V1 User Experience

### 8.1 Portfolio report

The user requests a crowding review for the current portfolio. The report:

1. resolves current holdings from the existing position/snapshot path;
2. groups holdings by market;
3. assesses each holding against market-valid evidence;
4. shows full likelihood bands only when coverage gates pass;
5. shows evidence-only degraded cards for other holdings;
6. sorts within each market by evidence strength and portfolio relevance;
7. does not compare a US full-coverage score directly with a CN price-only result.

Default report sections:

- Coverage summary by market.
- Holdings requiring attention because evidence changed materially.
- Per-holding direction-specific crowding card.
- Missing sources and entitlement status.
- Method and no-advice boundary.

### 8.2 Single-symbol report

The user can request one explicit market-qualified symbol. The result uses the same evidence and scoring contract as the portfolio report and adds a deeper source timeline.

### 8.3 Example card

```text
US.NVDA — Long-crowding likelihood: Elevated
Evidence quality: Medium (4 of 7 eligible families; latest market close 2026-07-22)

Why it may be crowded
- Price/volume: 20-day turnover and realized volatility are in the 93rd and 88th
  percentiles versus U.S. large-cap semiconductors.
- Ownership: the latest available institutional filing set shows high holder overlap,
  but the quarter-end snapshot is 43 days old.
- Options: call and put open interest are concentrated near two expiries; open
  interest alone does not identify who is long or short.

Counterevidence
- Published short interest and days-to-cover are not elevated versus the stock's
  own two-year history.

Fragility context
- Earnings are 6 calendar days away. Event proximity can amplify an unwind or
  squeeze but does not predict its direction.

What this does not mean
- This is a research aid, not a recommendation to reduce, add, hedge, or trade.
```

## 9. Signal Families

| Family | Useful evidence | What it can support | What it cannot establish alone |
|---|---|---|---|
| Price, volume, volatility, and liquidity | returns, gaps, turnover, realized volatility, correlation, drawdown, bid/ask or liquidity metrics | extension, participation, co-movement, unwind fragility | who owns the position or whether flows are long/short |
| Ownership and concentration | top holders, institutional filings, holder overlap, free float, insider changes | concentrated holders, passive/index overlap, ownership change | current positions between filing dates |
| Short interest and securities lending | open short positions, days-to-cover, lendable supply, utilization, borrow fee, recalls | short crowding, squeeze pressure, borrow stress | bearish conviction for every short position |
| Options positioning | volume, open interest, IV/HV, skew, expiry/strike concentration, participant/open-close data when licensed | speculative intensity, event pricing, concentration | signed dealer gamma or investor direction from aggregate OI alone |
| ETF and fund flows | creations/redemptions, estimated net flows, AUM/shares changes, fund allocation overlap | common funding source, passive-flow pressure, crowded theme ownership | security-level demand when allocation and effective date are unknown |
| Futures and derivatives positioning | open-interest change, basis, roll, trader-category positions | market/theme leverage and hedge demand | single-stock positioning unless the contract directly maps to the instrument |
| Retail and public attention | search interest, approved social volume, broker/customer order classifications | attention burst and speculative participation | verified positions, intent, or investment quality |
| Insider and institutional filings | Forms 3/4/5, 13D/G, 13F, HK Part XV, DART, exchange reports | ownership changes and concentration | a complete real-time ownership map |
| Earnings and event proximity | scheduled earnings, filings, lockups, index changes, corporate actions | fragility or catalyst proximity | crowding without positioning evidence |
| Portfolio relevance | position weight, theme concentration, recent trade activity | user impact and prioritization | market crowding |

Valuation is context, not a crowding signal family. It may explain why a trade is debated, but it must never independently increase the crowding likelihood.

## 10. Scoring And Explanation Contract

### 10.1 Evidence normalization

Each eligible metric is normalized within a valid peer group:

- same market;
- comparable instrument type;
- sector or industry when available;
- liquidity/market-cap bucket;
- the instrument's own history for time-series extremes.

The report must name the cohort. A percentile without a cohort is invalid.

### 10.2 Direction-specific family scores

Each evidence point declares its allowed contribution:

- `long_crowding`;
- `short_crowding`;
- `speculative_attention`;
- `fragility_only`;
- `counterevidence`;
- `non_directional`.

Provider labels such as "capital flow" are not accepted until their calculation semantics are documented.

### 10.3 Likelihood bands

V1 may display:

- `insufficient_evidence`;
- `low`;
- `watch`;
- `elevated`;
- `high`.

The internal deterministic score may use a 0-100 scale, but the user surface shows a band and uncertainty. It must say `heuristic likelihood; not a calibrated probability` until a documented historical calibration and validation set exists.

### 10.4 Minimum coverage

A displayed band requires:

- at least three independent families;
- price/volume/liquidity;
- at least one direct/higher-quality positioning family;
- no required family beyond its permitted staleness;
- no unresolved identity mismatch;
- no source-licence or entitlement violation;
- a coverage value and family list in the output.

If the gate fails, the result is `insufficient_evidence`, even if available proxies are extreme.

### 10.5 Explanation

Every band must include:

- top two to four contributors;
- at least one counterevidence item when available;
- missing families;
- oldest material source date;
- next known event;
- a plain-language uncertainty statement.

Model-generated narrative may summarize validated evidence, but it must not create metrics, change deterministic scores, infer missing positions, or convert a source label into a stronger claim.

## 11. Data Source Tiers

### Tier A — existing repository and public official data

- portfolio positions, snapshots, and trades;
- existing market bars and validated market snapshots;
- SEC EDGAR, FINRA, OCC, CFTC;
- SFC reportable short positions and HKEX public statistical files;
- DART/OpenDART and KRX official products after access terms are satisfied;
- SSE/SZSE/CNInfo official publications after access terms are satisfied;
- issuer IR and official exchange announcements.

Tier A does not mean "free to scrape." Each adapter needs an approved programmatic access and storage/display contract.

### Tier B — existing account-entitled data

- Futu OpenAPI interfaces for entitled price, option, short-interest, earnings-calendar, and related fields.

Tier B requires:

- the required account/quote entitlement;
- deployment credentials;
- rate/quota handling;
- confirmation that the intended internal storage and display are permitted.

### Tier C — licensed premium data

Candidate categories:

- global securities finance from S&P Global Market Intelligence or an equivalent provider;
- global fund flows from EPFR, LSEG Lipper, or an equivalent provider;
- granular options participant/open-close data from Cboe DataShop or an equivalent provider;
- licensed exchange files where public pages do not permit automated collection or redistribution.

Tier C must be evaluated by semantics, market/instrument coverage, lag, history, derived-data rights, display rights, storage rights, and cost. Brand name alone is not sufficient.

## 12. Recommended V1 Market Coverage

| Market | V1 product mode | Likelihood-band eligibility | Main strengths | Main limitations |
|---|---|---|---|---|
| US | full assessment when gates pass | Yes | existing bars; SEC ownership/insider filings; FINRA short interest; OCC options OI/volume; CFTC market-level positions; Futu entitled options/short/earnings | 13F lag; free short interest is twice monthly; aggregate OI is not signed; daily fund flow and borrow cost need licences |
| HK | full assessment when gates pass | Yes | existing Futu path; SFC weekly reportable shorts; HKEX daily short turnover and derivatives OI; Part XV ownership; HKEXnews | reportable-short thresholds omit smaller positions; some HKEX data/storage/display uses require a licence; fund-flow parity is weak |
| KR | evidence-only pilot | No, until official access and coverage tests pass | KRX exposes price, investor, foreign ownership, short-position, ETF, and derivatives statistics; DART has 5%/insider filings | KRX terms prohibit unauthorized automated collection; official API/product and usage rights must be contracted; fund-flow and lending depth need validation |
| CN | evidence-only pilot | No, until official access and coverage tests pass | existing CN bars/activity; exchange margin and securities-lending balances; periodic top-holder filings; ETF/index derivatives | lending balance is not comparable to global borrow data; single-stock options are limited; current AKShare path is research-oriented and based on upstream public sites; official automated rights are unresolved |

Cross-market portfolio summaries must display coverage mode beside every holding and rank only within comparable coverage groups.

## 13. Safe Degraded Behavior

The system must return a useful non-score result when:

- fewer than three independent families are current;
- only price/volume and attention are present;
- short-sale volume is present but short interest is missing;
- ownership filings are stale beyond their declared cadence;
- option OI exists but the instrument mapping or expiry history is incomplete;
- an ETF's flow is estimated without traceable shares/NAV inputs;
- a provider entitlement, credential, API key, or legal-use class is missing;
- the symbol maps to multiple instruments or share classes;
- the market is closed and the latest bar is incomplete;
- current and fallback sources disagree beyond tolerance.

Required output:

- `status=insufficient_evidence` or `status=provider_unavailable`;
- available evidence and dates;
- missing families;
- whether retry, credential, licence, or product-scope action can improve coverage;
- no numeric score;
- no raw credential, provider exception, local path, or internal endpoint.

## 14. Safety And Language

Required language:

- "Crowding likelihood" or "evidence suggests", not "this trade is definitely crowded."
- "Short crowding / squeeze pressure", not "shorts will be squeezed."
- "Options activity is concentrated", not "dealers must buy."
- "Event proximity may increase fragility", not "earnings will trigger an unwind."
- "Insufficient evidence", not "not crowded," when sources are missing.

Every report must state:

> This is a research aid based on incomplete and differently lagged market evidence. Crowded trades can continue, become more crowded, or unwind in either direction. The report is not investment advice and does not instruct the user to buy, sell, hold, trim, hedge, or trade.

The feature:

- is read-only;
- does not write formal user insights;
- may propose a candidate observation only in a later confirmed-memory workflow;
- does not expose licensed raw data beyond permitted display fields;
- does not store social usernames or user content in V1.

## 15. Decisions Required Before Implementation

### Product decisions

1. Approve the recommended asymmetric launch: US/HK can show a likelihood band; KR/CN remain evidence-only until their access gates pass.
2. Approve the V1 output as a heuristic likelihood band rather than a calibrated numeric probability.
3. Approve holdings-only plus explicit single-symbol scope; theme/sector screens and watchlists remain later.
4. Approve end-of-day refresh; intraday alerts remain later.

### Data, credentials, and spending decisions

5. Confirm whether this remains a private/internal personal research surface. This affects exchange and vendor display/redistribution terms.
6. Confirm which deployed Futu account and quote entitlements may be used for US/HK option, short-interest, and earnings data. Do not record credential values in documentation.
7. Approve obtaining an OpenDART API key and define its secret-management owner if KR remains in V1.
8. Approve a KRX official API/data-product enquiry and licence review before automated KR collection.
9. Approve an SSE/SZSE/CNInfo programmatic-access and data-use review before automated CN positioning collection.
10. Decide whether to evaluate premium data now. The recommended order is:
    1. global securities finance;
    2. global fund flow;
    3. granular options participant/open-close data.

No Engineering implementation plan should be marked ready until decisions 1-6 are explicit. Market adapters requiring credentials or spend cannot enter implementation until their corresponding decision is explicit.

## 16. Proposed Acceptance Criteria

### Product and semantics

1. No result uses valuation alone, price alone, social attention alone, or short-sale volume alone to label a trade crowded.
2. Long crowding, short crowding/squeeze pressure, speculative attention, and fragility are visibly distinct.
3. Missing data produces `insufficient evidence`, not a low crowding score.
4. Every likelihood band names at least three current independent families, including one direct/higher-quality positioning family.
5. Every evidence point shows source, metric meaning, observation date, publication/fetch date, market, and freshness.
6. The user can see supporting evidence, counterevidence, missing families, and event proximity.
7. US, HK, KR, and CN results never imply that non-equivalent short, ownership, options, or flow metrics are directly comparable.

### Data and provenance

8. Providers run through the shared source contract with explicit preferred, allowed, and fallback sources.
9. Fallback occurs only between equivalent metric semantics.
10. Source failures are typed, redacted, and visible in product language.
11. Entitlement- or licence-blocked data is not fetched, cached, displayed, or silently replaced.
12. Source records retain observation time separately from fetch time.
13. A source conflict or identity mismatch prevents the likelihood band.

### Scoring and quality

14. Deterministic fixtures demonstrate that missing families do not lower or raise the score.
15. Peer percentiles name and validate market, instrument, sector/industry, and liquidity cohorts.
16. A historical replay test prevents future data, later filings, or revised values from leaking into past assessments.
17. The surface labels the V1 output `heuristic likelihood; not a calibrated probability`.
18. A fixed set of adversarial fixtures covers high valuation, meme attention, high daily short volume, high options OI, stale 13F data, and opposing long/short evidence.

### User surface and safety

19. A portfolio report groups by market and coverage mode rather than publishing a false global leaderboard.
20. A single-symbol investigation uses the same evidence contract as the portfolio report.
21. Reports contain no buy/sell/hold/trim/hedge instruction.
22. No social username/content, secret, raw provider exception, internal URL, or local path appears in the user surface.
23. Independent acceptance testing verifies at least:
    - one US full-evidence example;
    - one HK full-evidence example;
    - one KR evidence-only example;
    - one CN evidence-only example;
    - one deliberate insufficient-evidence case.

## 17. Adoption Path

### Gate 0 — product and data decisions

Close section 15 and record licence/access owners. No runtime code starts before this gate.

### Gate 1 — contract and evidence slice

Extend the shared provider-neutral contracts with crowding-specific capabilities and normalized evidence. Build deterministic fixtures and evidence-only rendering before live providers.

### Gate 2 — US/HK live source slice

Add official/regulatory adapters and approved Futu-entitled adapters. Verify metric semantics and degraded behavior.

### Gate 3 — portfolio report

Reuse current position resolution to run bounded per-holding assessments. Keep ranking within market and coverage mode.

### Gate 4 — KR/CN access validation

Add only official, licensed, or expressly approved programmatic adapters. Evidence-only mode remains valid if access does not meet the product gate.

### Gate 5 — premium upgrade

Evaluate securities finance first, then fund flows, then granular options flow. Recalibrate only when history and rights support reproducible backtests.

### Gate 6 — recurring workflow integration

After independent acceptance, consider weekly-review and decision-card integration. Notifications and formal memory remain separate product decisions.

## 18. Discovery Conclusion

The capability is credible if it is built as an explainable, direction-specific evidence system with strict source semantics and honest coverage gates. It is not credible as a universal public-data score across US/HK/KR/CN.

The recommended hybrid V1 can produce useful US/HK assessments and honest KR/CN evidence gaps while preserving a clear path to institutional-grade lending and fund-flow data. The most important product promise is not that every holding receives a score; it is that the system refuses to manufacture one when the evidence does not support it.
