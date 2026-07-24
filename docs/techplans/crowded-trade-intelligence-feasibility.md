# Technical Feasibility Note: Crowded Trade Intelligence

Status: bounded V1 implemented and locally verified; live entitlement and cloud acceptance pending
Linked PRD: [`../product/PRD-Crowded-Trade-Intelligence.md`](../product/PRD-Crowded-Trade-Intelligence.md)
Linked implementation plan: [`../superpowers/plans/2026-07-24-crowded-trade-intelligence-v1.md`](../superpowers/plans/2026-07-24-crowded-trade-intelligence-v1.md)
Last updated: 2026-07-24

## 1. Feasibility Conclusion

An explainable crowded-trade capability is technically feasible, but a credible four-market score is not feasible from the repository's current sources alone.

The bounded V1 should:

- assess current holdings and an explicitly requested symbol at end of day;
- model `long crowding`, `short crowding / squeeze pressure`, and `speculative attention` separately;
- reuse the existing source-planning, fallback, provenance, partial-result, portfolio, bar, filing, and event contracts;
- add narrowly defined capabilities and approved official or entitled adapters instead of scraping websites;
- make US and HK eligible for likelihood bands after entitlement and semantic checks;
- keep KR and CN in evidence-only mode until programmatic access and use rights pass the same gate;
- treat premium securities-finance and fund-flow data as upgrades, not hidden V1 dependencies.

This is a heuristic evidence product, not a calibrated probability model. Without labelled historical outcomes, the system may report a likelihood band supported by transparent rules; it must not describe the numeric score as the probability that a trade will reverse.

## 2. Existing Repository Fit

### 2.1 Reusable contracts

The repository already has the right control-plane shape:

| Existing component | Current role | Reuse for this feature |
|---|---|---|
| `data_sources/contracts.py` | `DataRequest`, `SourcePlan`, `ProviderDescriptor`, `DataResult`, typed status and provider failure | Extend capability vocabulary and preserve selected/attempted source, freshness, coverage, partial/unavailable states, and redaction |
| `data_sources/pool.py` | Deterministic provider selection, fallback, cache compatibility | Resolve one approved plan per evidence request; do not make the scoring layer call vendors directly |
| `data_sources/market_bars.py` | Normalized Futu/Yahoo bars for US/HK/CN/multi-market use | Supply price, volume, realized volatility, range, and turnover-derived features where fields are actually present |
| `data_sources/market_activity.py` | Section-level market activity with source status and partial results | Reuse its section-level degradation pattern for family-level evidence |
| `data_sources/valuation.py` and `valuation_data_provider.py` | Official-first market plans and snapshot fallback | Reuse planning conventions; valuation remains context only |
| `research/official_sources.py` | SEC, HKEX, and issuer-IR routing | Extend through normal provider interfaces for filings and events |
| portfolio/position providers | Holdings and trade records, including Futu-backed paths | Define the bounded portfolio universe and user exposure; never infer market crowding from the user's own position |
| K-line and weekly-review flows | Evidence cards, insufficient-evidence language, concentration concerns | Reuse presentation patterns after independent acceptance, not in the first implementation slice |

Current capability vocabulary covers market bars, market activity, financial facts, snapshots, official/news events, positions, and trades. It does not yet represent ownership, short interest, lending, options positioning, fund flows, derivatives positioning, or attention. Those concepts should become explicit source capabilities rather than being smuggled into `MARKET_ACTIVITY`.

### 2.2 Current-source limitations

- Futu is already integrated, but current adapters do not expose all Futu OpenAPI fields relevant to crowding.
- Yahoo-backed market bars are a compatibility source. Yahoo's current terms prohibit automated data collection without prior permission, so V1 must not deepen this dependency until use rights are approved ([Yahoo Terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html?ncid=mbr_idnedulnk00000001)).
- AKShare is used for some market-activity paths. Its own project describes an academic/public-data collection library and warns about commercial risk and upstream interface changes. It is useful for research and fallback experiments, but should not be the sole production evidence source for a consequential label ([AKShare introduction](https://github.com/akfamily/akshare/blob/main/docs/introduction.md)).
- Current valuation coverage and valuation factors cannot substitute for positioning. A high multiple is not evidence that investors are positioned the same way.
- The repository has no labelled crowding-outcome dataset, source-semantic conformance suite, or calibration history.

## 3. Proposed Evidence Model

### 3.1 Evidence record

Every raw observation should normalize to an immutable evidence record with:

- `symbol`, canonical market, instrument type, and observation cohort;
- evidence family and metric semantic identifier;
- direction: `long`, `short`, `two_sided`, `attention`, or `context`;
- value, units, comparison window, percentile method, and denominator;
- observation time, provider publication time when known, fetched time, and lag;
- selected provider, attempted providers, source URL/report identifier, and licence tier;
- coverage status, quality flags, and any transformation version;
- whether redistribution is allowed, internal use only, or not yet cleared.

The metric semantic identifier is essential. Examples that must remain distinct include:

- exchange-reported short-sale turnover;
- outstanding short interest;
- securities-lending utilization;
- borrow fee;
- net reportable short position;
- option contract volume;
- option open interest;
- dealer gamma estimate;
- fund flow into a vehicle;
- underlying-company ownership concentration.

### 3.2 Result structure

One symbol result should contain:

1. source and market coverage summary;
2. family scores and direction;
3. contributors;
4. counterevidence;
5. missing or stale evidence;
6. separate likelihood bands for long crowding, short crowding/squeeze pressure, and speculative attention;
7. an evidence-quality label;
8. an explicit non-advice statement.

Missing evidence is `unknown`, never zero. A provider failure may reduce confidence or make the result unavailable; it must not mechanically make the position look less crowded.

### 3.3 Gating and scoring

Use deterministic rules before considering statistical calibration:

- Normalize only within a comparable market, instrument class, and time window.
- Require price/volume plus at least one direct positioning family.
- Require at least three independent families for a likelihood band.
- Cap a family contribution so correlated metrics cannot dominate.
- Keep ownership, short/lending, options, flows, and attention separate before aggregation.
- Record counterevidence, such as high price momentum with falling borrow cost or large fund inflows with dispersed ownership.
- Suppress the aggregate band when freshness or minimum-family gates fail.

An internal 0–100 heuristic may support deterministic ordering. The user-facing output should be `insufficient evidence`, `low`, `watch`, `elevated`, or `high`, accompanied by evidence quality. Cross-market portfolio sorting must not imply that a US full-coverage score is directly comparable with a CN evidence-only card.

## 4. Data Source Research

The following catalog distinguishes metric meaning, access tier, cadence/lag, geography, and operational or legal constraints. "Public" means available from an official public page or API; it does not automatically grant bulk collection or redistribution rights.

### 4.1 Price, volume, turnover, and volatility

| Source | Geography | Access | Cadence and lag | Useful evidence | Constraints |
|---|---|---|---|---|---|
| Existing Futu OpenAPI historical K-lines | US/HK/CN where account entitlement permits | Account-entitled; quote cards may be paid | Intraday/daily interfaces; entitlement-dependent | Returns, volume shocks, range, realized volatility, turnover where supplied | Login, quote rights, subscription/history quotas, and rate limits apply ([Futu quote authority](https://openapi.futunn.com/futu-api-doc/intro/authority.html), [historical K-line](https://openapi.futunn.com/futu-api-doc/en/quote/request-history-kline.html)) |
| Existing Yahoo compatibility path | Multi-market | Public website/interface, not an approved production licence | Typically daily/intraday, no contractual SLA | Prototype bar fallback | Current terms restrict automated collection without permission; do not expand until cleared ([Yahoo Terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html?ncid=mbr_idnedulnk00000001)) |
| KRX Data Marketplace/Open API | KR | Official; some datasets/API access require registration or purchase | Dataset-specific, generally exchange-day data | Prices, investor activity, ETF statistics, short selling, derivatives | Site terms restrict unauthorized automated collection, copying, and distribution; use Open API or purchased products ([KRX Data Marketplace](https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd?locale=en), [KRX Open API](https://openapi.krx.co.kr/contents/OPP/DATA/OPPDATA002.jsp), [site terms](https://data.krx.co.kr/contents/MDC/INFO/informationController/MDCINFO003.cmd)) |
| SSE/SZSE official products | CN | Official pages and licensed market data | Exchange-day or real-time depending product | Prices, volume, margin/lending, option fields | Programmatic access and redistribution must be confirmed per product; SZSE option rules require permission/written agreement for use, processing, or dissemination ([SZSE options rules](https://investor.szse.cn/English/rules/siteRule/P020210723557406190676.pdf)) |

Derived returns, volume z-scores, realized volatility, gap/range expansion, and turnover persistence are feasible from normalized bars. They are indirect stress/attention signals, not proof of positioning.

### 4.2 Ownership, institutional concentration, and insiders

| Source | Geography | Access | Cadence and lag | Useful evidence | Constraints |
|---|---|---|---|---|---|
| SEC Form 13F | US-listed reportable securities | Public/free through EDGAR | Quarterly; due within 45 days after quarter-end | Reported institutional concentration, manager count, ownership change | Material lag; covers qualifying managers and reportable securities, not all holders ([SEC 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f)) |
| SEC Schedules 13D/13G | US issuers | Public/free through EDGAR | Event-driven; >5% beneficial owners, with accelerated deadlines under current rules | Large-holder entry/change and concentration | Thresholded; different filer categories and deadlines must remain explicit ([SEC amendments](https://www.sec.gov/newsroom/press-releases/2023-219)) |
| SEC Forms 3/4/5 | US issuers | Public/free through EDGAR | Event-driven; most Form 4 changes are due within two business days | Insider buys/sells and ownership change | Insider activity is context, not automatically crowding |
| SEC EDGAR APIs | US | Public/free, no API key | Near filing time; SEC notes submissions often available within minutes | Machine-readable filing index/submissions and company facts | Declare user agent and stay within SEC fair-access limit of 10 requests/second ([EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [developer resources](https://www.sec.gov/about/developer-resources)) |
| HKEX/SFC Part XV disclosures | HK | Public/free search surface | Event-driven | Interests/short positions of substantial shareholders and directors; substantial shareholder threshold starts at 5% voting shares | Thresholded and filing-dependent; bulk/programmatic rights must be checked ([SFC Part XV](https://www.sfc.hk/en/Rules-and-standards/Securities-and-Futures-Ordinance-Part-XV---Disclosure-of-Interests)) |
| DART/OpenDART major holdings | KR | Official API key | Event-driven; Korea's 5% regime generally requires reports within five business days for reportable changes | Major shareholder and ownership change | API key, terms, filing semantics, and issuer mapping required ([OpenDART major holdings API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DE004&apiId=AE00040), [DART 5% reporting](https://dart.fss.or.kr/info/main.do?menu=310), [OpenDART terms](https://opendart.fss.or.kr/intro/terms.do)) |
| Issuer periodic reports / exchange filings | CN | Public official filings | Quarterly/semiannual/annual, publication lag | Total shareholder count and top shareholders | Sparse snapshots, nominee structures, and report lag limit inference; SSE describes top-ten and shareholder-count disclosure in quarterly reports ([SSE quarterly-report guidance](https://english.sse.com.cn/news/newsrelease/c/5608730.shtml)) |

Ownership concentration is a slow-moving direct-positioning family. V1 should distinguish stale-but-valid quarterly evidence from fresh event-driven large-holder evidence.

### 4.3 Short interest and securities lending

| Source | Geography | Access | Cadence and lag | Useful evidence | Constraints |
|---|---|---|---|---|---|
| FINRA short interest | US | Official/public publication and licensed files/products as applicable | Firms report twice monthly; FINRA publishes on its schedule | Outstanding short positions | Lagged and not daily. Do not substitute FINRA short-sale volume ([FINRA short interest](https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest)) |
| FINRA short-sale volume | US off-exchange | Public files | Daily/monthly publication | Trading activity involving short-sale marking | Not consolidated exchange-wide and not short interest; FINRA explicitly warns against equating the metrics ([FINRA short-sale volume](https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/monthly-short-sale-volume-files)) |
| Futu short-interest interface | US/HK | Existing account-entitled API | Provider/market dependent | US shares short, short ratio, days to cover; HK aggregated short and ratio | Confirm deployed entitlements, source lineage, field cadence, and internal-use rights ([Futu short interest](https://openapi.futunn.com/futu-api-doc/en/quote/get-short-interest.html)) |
| SFC aggregated reportable short positions | HK specified shares | Official/public CSV | Weekly; positions are thresholded and published with roughly one-week reporting/publication lag | Net reportable short-position amount and percentage | Only reportable positions above the lower of 0.02% market cap or HK$30m for specified shares; anonymized and incomplete below threshold ([SFC reporting](https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting), [aggregated files](https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting/Aggregated-reportable-short-positions-of-specified-shares)) |
| HKEX short-selling turnover | HK | Public daily page; licensed historical/data products | Daily; licensed files are published after market processing | Exchange short-selling turnover and ratio | Flow is not outstanding short interest. Historical automated use and redistribution may require a data licence ([HKEX daily page](https://www.hkex.com.hk/eng/stat/smstat/ssturnover/sstoday.htm), [historical data products](https://www.hkex.com.hk/eng/ods/historicalData.aspx)) |
| KRX short-selling datasets | KR | Official Data Marketplace/Open API or licensed product | Exchange-day, dataset-specific | Short-selling transactions, balances, net positions, large holders | Confirm API/product rights; metric thresholds and reporting rules require Korean-market semantics ([KRX Data Marketplace](https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd?locale=en), [KRX trading guide](https://global.krx.co.kr/contents/GLB/01/0109/0109000000/guide_to_trading_in_the_korean_stock_market.pdf)) |
| SSE margin and securities-lending disclosure | CN | Official exchange disclosure | Prior-day amounts disclosed before the next market open under exchange rules | Margin purchase balances and securities-lending sold/unsold quantities | Covers eligible margin/lending securities and is not equivalent to global securities-lending utilization ([SSE margin rules](https://english.sse.com.cn/start/sserules/stocks/trading/c/10647720/files/95943f34d9d74a5f87b8581d793829bc.pdf)) |
| S&P Global Securities Finance | Global | Licensed/paid | Daily and intraday products | Borrow supply/demand, balances, fees, utilization-style measures, transactions | Contract, budget, identifiers, redistribution, and derived-data rights required ([S&P Global Securities Finance](https://www.spglobal.com/market-intelligence/en/solutions/products/securities-finance)) |

Securities-finance data is the highest-value premium upgrade because borrow cost, utilization, supply, and demand directly describe short-side positioning better than short-sale volume.

### 4.4 Options positioning

| Source | Geography | Access | Cadence and lag | Useful evidence | Constraints |
|---|---|---|---|---|---|
| OCC daily open interest and volume files | US listed options | Official/public reports | Open interest reflects prior settlement; daily files | Contract/series open interest and volume | Open interest is not investor direction and cannot identify opening buy versus closing sell by itself ([OCC daily open interest](https://www.theocc.com/market-data/market-data-reports/other-market-data-info/batch-processing/daily-open-interest), [series search](https://www.theocc.com/Market-Data/Market-Data-Reports/Series-and-Trading-Data/Series-Search?symbol=GME&symbolType=Underlying), [volume query](https://www.theocc.com/market-data/market-data-reports/other-market-data-info/batch-processing/volume-query-batch-processing)) |
| Cboe Options Open-Close | US Cboe venues | Licensed/paid | Daily files | Participant type, buy/sell, open/close, contract volume | Proprietary Cboe-exchange coverage, not a full consolidated market; licence/derived display rights required ([Cboe DataShop](https://datashop.cboe.com/cboe-options-open-close-volume-summary)) |
| Futu option-chain interface | US/HK | Existing account-entitled API | OI is daily; documentation notes market-specific update timing | Open interest, volume, implied volatility, strikes and expiries | Confirm entitlement, coverage, and Greeks/IV semantics; HK single-stock option coverage is narrower than US ([Futu option chain](https://openapi.futunn.com/futu-api-doc/en/quote/get-option-chain.html)) |
| HKEX stock-option and derivatives statistics | HK | Public reports plus licensed data products | Daily/contract-level, product dependent | Volume and open interest | Public/report files and licensed products have different automation and redistribution rights ([HKEX stock-option statistics](https://www.hkex.com.hk/Products/Listed-Derivatives/Single-Stock/Stock-Options/Statistics/Data-Download-Centre?sc_lang=en), [derivatives OI](https://www.hkex.com.hk/eng/stat/dmstat/oi/oi_f.asp?sc_site=market_website)) |
| KRX derivatives products | KR | Official/possibly licensed | Daily/intraday by product | Futures/options volume and open interest | Single-name coverage and API rights must be validated |
| SSE/SZSE option products | CN | Official/licensed | Real time and daily fields by product | Volume, amount, and gross open interest | Single-stock options are not broadly comparable to US; written permission/data agreement constraints apply ([SZSE options rules](https://investor.szse.cn/English/rules/siteRule/P020210723557406190676.pdf)) |

V1 may use option activity as a speculative-attention or leverage signal. It must not claim dealer gamma, net customer direction, or squeeze probability unless the licensed fields and model assumptions actually support those constructs.

### 4.5 ETF and fund flows

| Source | Geography | Access | Cadence and lag | Useful evidence | Constraints |
|---|---|---|---|---|---|
| SEC Form N-PORT public data | US registered funds | Public/free | Current public regime is periodic and lagged; SEC's 2024 more-frequent regime has been delayed to 2027 | Fund holdings, exposures, and portfolio changes | Filing lag makes it unsuitable for real-time flows; parse regime/version explicitly ([SEC N-PORT data notes](https://www.sec.gov/files/nport_readme.pdf), [2025 compliance-date extension](https://www.sec.gov/rules-regulations/2025/04/s7-26-22)) |
| Issuer ETF shares outstanding / holdings | Market/product dependent | Often public issuer files | Daily for some products, not standardized | Estimated creations/redemptions and basket exposure | No universal schema or licence; do not create an ad hoc scraper fleet |
| KRX ETF statistics | KR | Official Data Marketplace/Open API/licensed | Exchange-day, dataset-specific | ETF prices, AUM, shares, and activity | Access/product terms must be confirmed |
| EPFR | Global | Licensed/paid | Daily, weekly, and monthly products; vendor production timing applies | Fund and ETF flows, allocations, investor segments | Contract, universe mapping, redistribution, and derived-data rights required ([EPFR](https://epfr.com/), [product overview](https://epfr.com/wp-content/uploads/2023/09/EFPR-Product-Overview.pdf)) |
| LSEG Lipper | Global | Licensed/paid | Daily/weekly/monthly estimates and reported series, product dependent | Fund flows, assets, classifications | Contract and redistribution terms required ([Lipper fund data](https://www.lseg.com/en/data-analytics/financial-data/fund-data)) |

Fund flows are conceptually valuable but difficult to attribute from a fund to a single stock without holdings weights and assumptions. V1 should use direct single-name evidence first. A premium global fund-flow source is the second recommended upgrade after securities finance.

### 4.6 Futures and derivatives positioning

| Source | Geography | Access | Cadence and lag | Useful evidence | Constraints |
|---|---|---|---|---|---|
| CFTC Commitments of Traders | US futures markets | Official/public | Weekly Friday publication for positions as of Tuesday | Trader-category positioning and concentration at futures-market level | Not a single-stock dataset; useful for index, rate, commodity, FX, or thematic context only ([CFTC COT overview](https://www.cftc.gov/MarketReports/CommitmentsofTraders/AbouttheCOTReports/index.htm)) |
| HKEX derivatives OI | HK | Public reports/licensed products | Daily | Futures/options volume, gross/net OI, and change | Map only to related index/product exposure; do not present as direct ownership of a constituent |
| KRX derivatives statistics | KR | Official/licensed | Daily/intraday by product | Index/equity derivative volume and OI | Product mapping and terms required |
| CN exchange derivatives/options | CN | Official/licensed | Product dependent | Index/ETF option OI and volume | Market/product restrictions and data permissions apply |

Derivatives context can explain theme-level leverage but should not be silently assigned to every constituent.

### 4.7 Retail and social attention

| Source | Geography | Access | Cadence and lag | Useful evidence | Constraints |
|---|---|---|---|---|---|
| Google Trends API alpha | Search regions where available | Application-only alpha; terms apply | Rolling five-year history with daily/weekly/monthly/yearly aggregation | Relative search attention by region | Data is sampled, aggregated, anonymized, and normalized; not investor positioning ([Trends API](https://developers.google.com/search/apis/trends), [data interpretation](https://developers.google.com/search/docs/monitor-debug/trends-start)) |
| Reddit Data API | Primarily global/US attention | Approval required; commercial use requires permission/contract | Endpoint/product dependent | Post/comment attention with approved access | Responsible-builder rules, rate/bulk limits, privacy, deletion, and retention obligations; no scraping fallback ([Reddit access policy](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data), [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)) |
| X API | Global attention | Paid, pay-per-use | Endpoint/tier dependent | Mention/activity trends | Budget, retention, display, and terms constraints; current API is not a free dependency ([X API pricing](https://docs.x.com/x-api/getting-started/pricing)) |
| Local broker/community platforms | HK/KR/CN | No approved repository contract | Unknown | Potential retail attention | Exclude from V1 absent an official/licensed API and legal review; no Xueqiu or forum scraping |

Attention should be optional and non-blocking. A spike can reflect news, controversy, or genuine interest; it cannot establish crowding without direct-positioning evidence.

### 4.8 Earnings and event proximity

| Source | Geography | Access | Cadence and lag | Useful evidence | Constraints |
|---|---|---|---|---|---|
| SEC/HKEX/DART/issuer IR | US/HK/KR and issuer dependent | Official/public; OpenDART key required for API | Event-driven | Filing date, earnings release, corporate actions, shareholder events | Calendar estimates and confirmed filings must remain distinct |
| Futu earnings calendar | US/HK and provider coverage | Existing account-entitled API | Provider dependent | Earnings date/proximity and related market fields | Confirm entitlement and whether dates are estimated or confirmed ([Futu earnings calendar](https://openapi.futunn.com/futu-api-doc/en/quote/get-earnings-calendar.html)) |
| Exchange calendars | Per market | Official/public or licensed | Scheduled | Trading-day normalization and known exchange events | Does not replace issuer event confirmation |

Event proximity is a context/risk amplifier. It changes how the user should interpret unstable price, volatility, borrow, and option evidence; it is not itself a crowding signal.

## 5. Recommended V1 Source Plans

### 5.1 US

Minimum eligible full-band plan:

- normalized entitled market bars;
- at least one direct family from FINRA short interest, Futu short interest, or SEC ownership;
- at least one further independent family from SEC ownership/insiders, OCC/Futu options, or approved flows;
- official event proximity;
- optional approved attention.

Use SEC EDGAR for 13F, 13D/G, and insider filings. Use FINRA short interest with explicit publication lag. Use OCC or entitled Futu options without claiming customer direction. Securities-finance data is a premium enhancement.

### 5.2 HK

Minimum eligible full-band plan:

- normalized entitled market bars;
- SFC reportable short positions and/or entitled Futu short-interest data;
- HKEX/SFC ownership disclosure or entitled holder data;
- HKEX/Futu option activity when the symbol has meaningful listed-option coverage;
- official event proximity.

Daily short-selling turnover may supplement but never replace outstanding short-position evidence.

### 5.3 KR

Evidence-only launch plan:

- existing/approved bars;
- OpenDART major-holder filings after API-key and terms validation;
- KRX short, ownership, ETF, or derivatives data only through its Open API or a purchased product.

KR becomes eligible for a likelihood band only after at least three independent families, including one direct family, are available under approved programmatic terms.

### 5.4 CN

Evidence-only launch plan:

- existing/approved bars;
- official periodic shareholder concentration from issuer/exchange filings;
- official margin/securities-lending balances where programmatic access and use rights are confirmed;
- ETF/index options only as clearly labelled context.

CN must not receive a full likelihood band from price/volume plus margin balance alone. The product should display the precise missing families.

## 6. Contract And Architecture Recommendation

### 6.1 Capability vocabulary

Add explicit capabilities in a later implementation plan:

- `OWNERSHIP_CONCENTRATION`
- `INSIDER_ACTIVITY`
- `SHORT_INTEREST`
- `SECURITIES_LENDING`
- `OPTIONS_POSITIONING`
- `FUND_FLOWS`
- `DERIVATIVES_POSITIONING`
- `ATTENTION`
- `EVENT_CALENDAR`

Provider descriptors should also carry access tier, entitlement key, permitted-use classification, metric semantics, market coverage, expected cadence, and expected publication lag.

### 6.2 Layer boundaries

```text
Portfolio universe / explicit symbol
              |
              v
Crowding evidence orchestrator
              |
              v
Capability-specific SourcePlans
              |
              v
Existing DataSourcePool + approved adapters
              |
              v
Normalized immutable evidence records
              |
              v
Family features -> coverage gate -> direction-specific bands
              |
              v
Evidence-first report with provenance and degraded states
```

The orchestrator may request evidence; it must not know vendor endpoints. Providers may normalize fields; they must not assign product bands. The scoring layer may aggregate normalized evidence; it must not silently fill missing values. The presentation layer may explain results; it must not change score semantics.

### 6.3 Caching and refresh

- Bars and daily option/short activity: refresh after the market's official processing window.
- FINRA short interest: refresh only on the publication schedule.
- SFC short positions: weekly refresh after publication.
- SEC 13F: poll by filing index and retain quarter/report dates.
- 13D/G, insider, and DART major-holder filings: event-driven polling within fair-access limits.
- Premium lending/flow sources: follow contract cadence and retention rules.

Cache keys must include provider, semantic metric, symbol/instrument identifier, market, observation date, and transformation version. Publication lag should remain visible after a cache hit.

### 6.4 Identifier mapping

Add a mapping layer rather than embedding vendor symbols in score code. It should support:

- canonical market plus local ticker;
- issuer identifiers such as CIK and DART corporation code;
- option underlying/product identifiers;
- ETF/fund identifiers and share classes;
- vendor-specific identifiers with provenance.

Ambiguous or unmapped instruments should return unavailable evidence, not guess.

### 6.5 Legal and entitlement control

Maintain a machine-readable source approval register with:

- provider/product;
- approved environments and use case;
- credentials owner;
- internal display, derived result, storage, retention, and redistribution rights;
- expiry/renewal date;
- rate and quota limits;
- legal review reference;
- enabled markets/capabilities.

An adapter must remain disabled until this record is approved. Credentials stay in the existing secret-management path and never in reports, provenance fields, fixtures, or logs. Public availability is not equivalent to permission for automated production collection.

## 7. Safe Failure Model

| Failure | Required result |
|---|---|
| One provider fails and an approved semantically equivalent provider succeeds | Return result with attempted/selected providers and fallback notice |
| Only a non-equivalent proxy exists | Show the proxy as a different metric; do not call it a fallback |
| Required direct family is absent | `insufficient evidence` |
| Source is stale but still informative | Preserve observation and publication dates; reduce quality; do not relabel as current |
| Entitlement or licence is missing | `source unavailable: entitlement/approval required`; no scraping workaround |
| Identifier mapping is ambiguous | Suppress evidence for the instrument |
| One market is closed/holiday | Use its own last valid observation and market calendar; do not align by naive calendar date |
| Score version changes | Version the transformation and prevent unexplained comparison across versions |
| Attention source fails | Continue without it and state that optional attention evidence is unavailable |
| All positioning evidence fails | Return bars/context only with no aggregate likelihood |

## 8. Validation Strategy For A Later Implementation

### 8.1 Contract tests

- provider capability and market matching;
- typed partial/unavailable failures;
- lag, freshness, source, and attempted-provider preservation;
- licence-gate disabled behavior;
- identifier ambiguity behavior;
- no secret leakage.

### 8.2 Semantic fixtures

Create dated, licence-compatible fixtures for:

- FINRA short interest versus FINRA short-sale volume;
- SFC reportable net short positions versus HKEX short-selling turnover;
- OCC open interest versus option volume;
- SEC 13F quarter/report dates versus filing dates;
- KRX short metrics;
- SSE margin versus securities-lending balances.

Tests should fail if adapters map these concepts to one generic "short ratio".

### 8.3 Scoring invariants

- missing never contributes zero;
- no aggregate band without the minimum direct family;
- family caps prevent duplicate metrics from dominating;
- stale evidence cannot improve evidence quality;
- counterevidence is preserved;
- long and short bands can coexist;
- a high valuation alone never changes the band;
- event proximity changes context, not the underlying positioning measurement.

### 8.4 Historical evaluation

Before describing the output as calibrated, build a legally retainable history and predefine outcomes such as:

- forward drawdown conditional on market;
- volatility expansion;
- borrow-fee or short-interest unwind;
- ownership or fund-flow reversal;
- option-IV normalization.

Evaluate discrimination, calibration, stability by market/regime, false positives, and value beyond price/volume baselines. Until then, user language remains "heuristic likelihood band".

### 8.5 Acceptance evidence

A later implementation should demonstrate:

- one sufficiently covered US example;
- one sufficiently covered HK example;
- one KR or CN evidence-only example with explicit missing requirements;
- one entitlement failure;
- one stale filing/short-interest case;
- one source fallback;
- one case with strong price attention but no direct-positioning evidence, which must not receive a band.

## 9. Cost And Adoption Tiers

### Tier A — repository plus official sources

Lowest direct vendor cost. Supports bars, official ownership/insider filings, regulatory short data, public option/OI reports, and events. Operational cost includes identifiers, parsing, fair-access compliance, and source-change monitoring.

### Tier B — current Futu entitlement

Best bounded V1 accelerator if the deployed account and intended use are approved. It can reduce adapter count for bars, option chains, short interest, earnings, and related holder fields, but it does not eliminate provenance or entitlement checks.

### Tier C — institutional upgrade

Recommended purchase order:

1. global securities finance;
2. global fund/ETF flows;
3. granular opening/closing options flow;
4. licensed attention data only if user adoption proves it useful.

Request quotes and sample coverage against the actual portfolio universe before contracting. Evaluate retention, derived-data display, model-input, and redistribution rights, not price alone.

## 10. Approved Defaults And Remaining Access Gates

The Owner delegated the discovery choices and approved the recommended defaults on 2026-07-24:

1. US/HK may earn full bands; KR/CN remain evidence-only.
2. Portfolio holdings and explicit single-symbol investigation are both included.
3. The user surface exposes bands and explanation, not a precise probability.
4. Refresh is end of day; the implementation plan must choose only the minimum cache needed for reproducible evidence and approved source retention.
5. The product is private, internal, and single-user; redistribution is out of scope.
6. Futu is optional and entitlement-gated. Its absence produces degraded coverage.
7. OpenDART, KRX automation, and CN automated positioning access are deferred.
8. Premium securities finance, fund flows, granular options flow, and social/community data are excluded from V1.

These defaults authorized the linked bounded implementation plan. The Futu adapter is present but remains response- and entitlement-gated: unsuccessful live calls degrade to typed unavailable evidence. Every deferred official/licensed source remains disabled until its access gate is satisfied.

## 11. Implemented V1 Architecture

The linked implementation plan has been executed locally:

| Layer | Implementation | Verification |
|---|---|---|
| Capability and approval control | Added explicit ownership, short-interest, options-positioning, and event-calendar capabilities plus an immutable Futu private-internal approval register. The register currently leaves environment, credential owner, display/derived/storage/retention rights, expiry, legal review reference, and per-capability approvals unverified; therefore `FUTU_CROWDING_PRIVATE_USE_APPROVED=approved` cannot bypass the gate and the loader returns `approval_required`. | `tests/test_data_source_contracts.py`, `tests/test_data_source_crowding.py` |
| Vendor transport | Added a bounded Futu bundle transport for US/HK holder, short-interest, option-chain/snapshot, and earnings-calendar evidence. Aggregate residual holder rows such as `Other` are excluded from named-holder concentration, and option contract OI retains the chain lot-size multiplier for underlying-equivalent normalization. Large chains are selected deterministically from nearest expiries and report measured partial coverage when truncated. One context is closed in `finally`; family failures are isolated and redacted, with entitlement failures distinguished from generic provider failure. | `tests/test_futu_crowding_provider.py` |
| Provider-neutral adapter | Registered one multi-capability `futu_crowding` provider with a memoized bundle loader and normalized semantic records. | `tests/test_data_source_crowding.py` |
| Evidence and scoring | Added immutable evidence/family/assessment types, own-history price-volume features, direction-specific family gates, stale-data exclusion, point-in-time publication checks, coverage retention, and deterministic bands. Unknown-publication evidence fetched after a historical `as_of` is excluded. Falling-price fragility is counterevidence. Aggregate option OI remains two-sided and cannot raise signed long/short scores; partial price or positioning coverage below 80% fails the current-family gate and remains visible in the explanation. | `tests/test_crowding_intelligence.py` |
| Orchestration | Added Futu-only market-bar plans, separate evidence requests, provider-bar-backed latest-completed-session resolution, per-holding session display, CN provider-code mapping, class-share identifiers, bounded portfolio analysis, per-symbol isolation, and market grouping. | `tests/test_crowding_service.py` |
| User surface | Added read-only single-symbol and portfolio commands plus Workbench actions that do not require profile bootstrap for exact symbols. | `tests/test_command_router.py`, `tests/test_command_workbench.py`, `tests/test_command_http.py` |

No service, database table, dependency, social scraper, premium vendor, credential, trade action, alert, or formal-memory write was added.

### 11.1 Deliberate V1 limits

- US/HK bands depend on current entitled Futu responses and the direction-specific three-family gate.
- Live Futu crowding calls remain disabled until the approval register records the deployed environment, credential owner, display/derived/storage/retention rights, retention policy, expiry, legal review reference, and all four bundled capabilities. V1 transport fetches those families together, so capability approval is deliberately all-or-nothing; a future per-capability transport split is required before narrower activation is safe. Runtime must also identify itself through `CROWDING_RUNTIME_ENVIRONMENT` as one of those approved environments. Only then may an operator set `FUTU_CROWDING_PRIVATE_USE_APPROVED=approved`; the flag is not a credential and cannot substitute for the register or quote entitlements.
- KR/CN remain evidence-only.
- Price/volume normalization is labelled against the instrument's own rolling history; V1 does not claim sector/liquidity peer percentiles.
- Speculative attention remains insufficient because social/retail collection is excluded.
- Bands are uncalibrated deterministic heuristics, not reversal probabilities.

### 11.2 Remaining release gates

1. Integration, serialized deployment, public/tokenless checks, approved-session class-share preview, and fail-closed single-symbol execution are complete at `main@61ee36dca794ce7996e84644e0298aecd381aace`, workflow `30060363722` attempt 2, event `1784858995286`.
2. Independent degraded-mode acceptance passed. `AT-2026-07-24-001` remains `blocked/major` for full live-source US/HK behavior.
3. The accountable data/licence operator must complete the approval register and confirm deployed quote entitlements. Only then enable the runtime gate and rerun the same acceptance item; no code redeploy is required merely for the current approval blocker.
4. Keep user acceptance pending until the Owner explicitly accepts the deployed surface.

### 11.3 Architecture audit disposition

The repository architecture audit reports `investment_knowledge_mcp.futu_provider` at 1,247 lines. This is a report-only P1 under `docs/architecture/architecture-contract.md`, not an admitted release gate. The smallest safe follow-up is to extract the independently tested crowded-trade transport and snapshot types into `futu_crowding_provider.py` while preserving adapter contracts; verification is the Futu transport/source suite plus a repeated architecture audit. That refactor is deliberately separate from this release so a late structural move does not add product risk.
