# PRD: AI Industry Panorama

Status: discovery proposal; bounded V1 recommended, not yet approved for implementation

Research snapshot: 2026-07-23

Linked technical feasibility note: [`../techplans/ai-industry-panorama-feasibility.md`](../techplans/ai-industry-panorama-feasibility.md)

## 1. Product Summary

AI Industry Panorama is an explorable, evidence-backed map of the AI industry.
It starts with the actors creating demand and committing capital, then lets the
Owner trace how that demand reaches data centers, compute systems, accelerators,
networking and optical interconnect, memory, foundry and advanced packaging,
semiconductor equipment, and power and cooling infrastructure.

The product is not a static industry report and not an automatic stock picker.
Its durable value is a versioned industry graph in which every material node and
relationship can be inspected, dated, sourced, and distinguished as disclosed
fact, company guidance, management claim, or inference.

The recommended V1 answers:

> Who is committing AI infrastructure demand, which first-order companies and
> capabilities are connected to that demand by primary evidence, where and when
> does the relationship apply, and what remains uncertain?

## 2. Owner Problem

The Owner wants to learn the AI business system and discover investable
relationships. Today that requires reconstructing a changing supply chain from
filings, earnings calls, company announcements, technical materials, and market
narratives. The work is difficult because:

- A single capital-expenditure number often mixes AI infrastructure, ordinary
  cloud capacity, offices, logistics, or other assets.
- A supplier may disclose a customer category while withholding the customer
  name; a buyer may name a supplier without disclosing commercial magnitude.
- A partnership announcement can establish intent but not prove revenue,
  shipment, production qualification, or an operating asset.
- The chain is not a simple tree. One entity can be a buyer, designer,
  supplier, competitor, and investor at the same time.
- Geography changes the meaning of an edge because manufacturing, packaging,
  deployment, regulation, and power availability occur in different places.
- Technical standards and product generations change which capabilities are
  relevant.
- Market commentary routinely turns plausible exposure into unsupported fact.
- A one-off report ages quickly and does not show what changed.

## 3. Product Positioning

AI Industry Panorama should be:

- A learning surface for traversing the AI value chain from demand to physical
  bottlenecks.
- A versioned evidence graph, not a free-form narrative.
- Official-first, with source, period, geography, and uncertainty visible.
- Useful for forming research questions and finding public companies that merit
  deeper stock research or valuation work.
- Explicit about the difference between an economic relationship and an
  investable conclusion.

It should not be:

- A static PDF or a manually redrawn slide.
- A screen that ranks "AI beneficiaries" without showing evidence.
- A portfolio exposure or position-sizing tool in V1.
- A revenue-attribution engine when companies do not disclose attribution.
- A generic news feed.
- An autonomous crawler that publishes model-extracted relationships without
  review.
- A replacement for the existing stock research, valuation, Kline, decision
  card, or weekly review flows.

## 4. Discovery Evidence

Primary sources show why the product needs typed, time-aware relationships
rather than a timeless supply-chain diagram.

### 4.1 Demand And Capital Formation

- Alphabet's 2025 Q4 earnings call states that roughly 60% of 2025 investment
  went to machines and roughly 40% to data centers and networking, with a
  similar mix expected in 2026. This supports separate `machines` and
  `long_duration_infrastructure` facts; it does not disclose vendor allocation.
  [Source](https://abc.xyz/investor/events/event-details/2026/2025-Q4-Earnings-Call-2026-Dr_C033hS6/default.aspx)
- Microsoft's FY2026 Q3 call describes a stack spanning data-center design,
  silicon, systems software, model architecture, custom processors, and
  third-party accelerators, and gives current capacity and capital-expenditure
  guidance. This supports multiple typed capabilities and time-bounded
  guidance, not one undifferentiated "AI Capex" edge.
  [Source](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q3)
- Meta's Q1 2026 release raises its 2026 capital-expenditure range and attributes
  the change to component pricing and future data-center capacity. The guidance
  is an issuer statement as of the release date, not a supplier revenue fact.
  [Source](https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-Reports-First-Quarter-2026-Results/)
- Amazon's 2025 Form 10-K says cash capital expenditure primarily reflected
  technology infrastructure, the majority supporting AWS growth, plus
  fulfillment capacity; its Q1 2026 release separately names OpenAI and
  Anthropic Trainium commitments. These are different evidence types and should
  not be collapsed into a single annual Capex number.
  [10-K](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000004/amzn-20251231.htm),
  [Q1 2026 release](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-First-Quarter-Results/default.aspx)
- OpenAI's Stargate announcements identify partners, sites, planned capacity,
  and development status. They demonstrate that `announced`, `under
  development`, and `operating` must be separate lifecycle states.
  [Five-site announcement](https://openai.com/index/five-new-stargate-sites/),
  [Oracle capacity announcement](https://openai.com/index/stargate-advances-with-partnership-with-oracle/)
- Anthropic's April 2026 announcement names Google and Broadcom and says the
  next-generation TPU capacity is expected to come online starting in 2027.
  This is a named, forward relationship with an effective window, not evidence
  of current operating capacity.
  [Source](https://www.anthropic.com/news/google-broadcom-partnership-compute)

### 4.2 Supply Chain And Technical Dependencies

- NVIDIA's fiscal 2026 Form 10-K names foundries, memory suppliers, CoWoS
  packaging, and contract manufacturers. It also explains that long lead times,
  non-cancellable commitments, data-center availability, energy, and capital
  can constrain deployments. This is strong evidence for named supply-chain
  edges, but not for each supplier's revenue share.
  [Source](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm)
- TSMC materials connect AI accelerator demand with leading-edge process and
  CoWoS capacity, while its annual report documents the underlying foundry and
  packaging capabilities. The product must distinguish a capability node from
  a customer-specific relationship.
  [2025 annual report section](https://investor.tsmc.com/static/annualReports/2025/english/pdf/2025_tsmc_ar_e_ch5.pdf)
- ASML's 2025 annual report connects AI demand with advanced Logic, DRAM, EUV,
  and packaging product investment. This supports an equipment-enables-process
  relationship, not a direct edge from every hyperscaler to ASML.
  [Source](https://www.asml.com/en/investors/annual-report/2025/financials)
- SK hynix's FY2025 release states that HBM revenue more than doubled, while its
  June 2026 HBM4E announcement says samples were shipped to unnamed major
  customers. The customer relationship must remain unnamed unless another
  primary source names it.
  [FY2025 results](https://news.skhynix.com/sk-hynix-announces-fy25-financial-results/),
  [HBM4E samples](https://news.skhynix.com/12-layer-hbm4e-sample/)
- Corning's June 2026 announcement names a multibillion-dollar Amazon agreement
  for optical fiber, cable, and connectivity. This is stronger relationship
  evidence than a generic assertion that optical suppliers benefit from data
  centers, but it still requires a contract period and geography.
  [Source](https://www.corning.com/worldwide/en/about-us/news-events/news-releases/2026/06/amazon-announces-agreement-with-corning-to-boost-us-fiber-optics-manufacturing-creating-1000-advanced-manufacturing-jobs-in-north-carolina.html)
- Schneider Electric and NVIDIA publish reference-design work for power and
  cooling of rack-scale systems. A technical compatibility or co-design edge
  should not be presented as a purchase contract unless purchase evidence also
  exists.
  [Source](https://www.se.com/ww/en/about-us/newsroom/news/press-releases/schneider-electric-teams-with-nvidia-to-develop-validated-blueprints-to-design-simulate-build-operate-and-maintain-gigawattscale-ai-factories-69b82397e7fa28870e0cd5a3/)

### 4.3 Geography, Power, And Standards

- The U.S. Energy Information Administration expects especially rapid near-term
  load growth in ERCOT and PJM and identifies data centers as a major driver.
  Geography therefore belongs on projects and relationships, not only on
  company headquarters.
  [Source](https://www.eia.gov/todayinenergy/detail.php/detail.php?id=67344)
- The Open Compute Project's Open Data Centers for AI work covers facility
  reference designs, grid solutions, cooling, telemetry, and power estimation.
  It provides a neutral capability vocabulary; it does not prove that a
  specific company has adopted every OCP design.
  [Source](https://www.opencompute.org/community/open-data-centers-for-ai)
- Ultra Ethernet Consortium specification history shows that standards are
  versioned and can be corrected after initial release. A standards edge needs
  a version and date.
  [Source](https://ultraethernet.org/specification-history/)

### 4.4 Discovery Conclusion

The evidence supports a graph whose core record is:

```text
typed assertion
  + one or more source snapshots
  + source locator
  + valid time
  + geography
  + lifecycle state
  + evidence strength
  + explicit fact/inference classification
```

A company logo connected by an unlabeled line is not sufficient.

## 5. Recommended V1

### 5.1 Scope

V1 should be a manually curated, read-only panorama with:

- Six demand anchors: Alphabet/Google, Microsoft, Meta, Amazon/AWS, OpenAI, and
  Anthropic.
- Approximately 25-35 organizations and projects in total.
- Approximately 45-70 reviewed relationships.
- A US demand and data-center buildout lens with global supply-chain geography,
  especially Taiwan, South Korea, the Netherlands, and relevant US
  manufacturing or deployment sites.
- Source coverage centered on 2024-2027 actuals, current guidance, announced
  commitments, and named projects.
- One immutable published graph release plus a visible update timestamp and
  change summary.

The first taxonomy should cover:

1. Demand and capital formation
   - Hyperscalers and cloud platforms
   - Frontier model labs
2. Data-center capacity
   - Owners/operators
   - Developers, colocation, and cloud capacity
   - Compute systems and rack integration
3. Compute and interconnect
   - GPUs and AI accelerators
   - Custom silicon and CPUs
   - Scale-up/scale-out networking
   - Optical fiber, transceivers, cables, and connectivity
4. Memory and storage
   - HBM
   - Server DRAM
   - Enterprise storage
5. Manufacturing
   - Foundry and leading-edge process
   - Advanced packaging and test
   - Lithography, deposition, etch, inspection, and related equipment
6. Physical infrastructure
   - Grid and generation access
   - Electrical distribution and backup
   - Air and liquid cooling

Entities may belong to multiple capabilities. The taxonomy is a navigational
classification, not an exclusive company classification.

### 5.2 Why This Is Narrow Enough

This slice proves the essential trust and learning loop:

```text
demand actor
  -> named or inferred relationship
  -> infrastructure capability
  -> company/project
  -> evidence and uncertainty
  -> next research question
```

It avoids four high-blast-radius expansions:

- Automated source discovery and extraction, which needs its own review and
  failure-handling contract.
- Global demand coverage, which would multiply jurisdictions and disclosure
  systems before the navigation model is proven.
- Quantified company revenue exposure, which is usually not disclosed and would
  require estimate methodology and licensing decisions.
- Portfolio, valuation, and recommendation integration, which would turn a
  learning graph into a decision product before the graph is trusted.

## 6. Core User Journeys

### 6.1 Trace Demand Downstream

1. The Owner opens the panorama and sees the six demand anchors.
2. The Owner selects Microsoft.
3. The map focuses on one- and two-hop relationships and groups them by
   capability layer.
4. Directly disclosed and inferred edges are visually distinct.
5. The Owner filters to `2026-2027`, `United States`, and `announced or under
   construction`.
6. The Owner opens an edge to read the exact relationship claim, evidence
   locator, date, confidence rationale, and limitations.

### 6.2 Learn A Capability

1. The Owner selects `Advanced packaging`.
2. The product explains the capability in plain language.
3. It shows entities, relevant standards or product generations, upstream and
   downstream dependencies, and geographic concentration.
4. The Owner can traverse from CoWoS to TSMC, HBM providers, accelerator
   designers, and demand anchors only where evidence supports the path.

### 6.3 Investigate A Company

1. The Owner searches for Corning.
2. A company drawer shows capabilities, named counterparties, relevant
   geographies, dated facts, inferred exposures, and source coverage.
3. If the company is already represented in the stock research system, the
   drawer may offer a link to existing research or valuation.
4. No panorama fact is silently written into a stock thesis, user insight, or
   portfolio record.

### 6.4 Understand What Changed

1. A later graph release is published.
2. The Owner can see added, changed, expired, and removed relationships.
3. A changed edge retains its prior version and evidence history.
4. New company guidance does not rewrite what management said in an earlier
   period.

## 7. Navigation And Interaction Contract

### 7.1 Default View

The default view is a layered chain map, not a force-directed "hairball":

- Demand anchors remain on the left.
- Capability layers progress to the right.
- Cross-layer relationships can be followed without showing the entire graph at
  once.
- The initial view shows a curated number of high-information edges; the Owner
  expands details on demand.

### 7.2 Required Controls

- Search entities, capabilities, projects, and aliases.
- Focus on an entity and choose one-hop or two-hop traversal.
- Filter by capability layer, geography, valid period, lifecycle state,
  evidence type, and confidence.
- Toggle `Disclosed only` versus `Include inference`.
- Reset to the complete V1 panorama.
- Switch to an accessible table/list representation with the same filters.

### 7.3 Node Drawer

Every organization or project drawer shows:

- Canonical name, aliases, entity type, listing identifiers when applicable,
  and headquarters or site geography.
- Plain-language role and capability tags.
- Direct disclosed relationships.
- Inferred exposures in a separate section.
- Relevant dated facts and guidance.
- Latest evidence date, coverage gaps, and staleness state.
- Optional links to existing stock research and valuation; no embedded portfolio
  state in V1.

### 7.4 Relationship Drawer

Every edge drawer shows:

- Direction and relationship type.
- A plain-language assertion.
- `assertion_kind`: `disclosed_fact`, `company_guidance`,
  `management_claim`, `inferred_exposure`, or `user_hypothesis`.
- Lifecycle state such as `announced`, `committed`, `qualification`,
  `sampling`, `mass_production`, `shipping`, `under_construction`,
  `operating`, `expired`, or `unknown`.
- Valid-from, valid-to or expected start, observed-at, and last-reviewed dates.
- Geography and whether it represents headquarters, manufacturing, packaging,
  deployment, or end demand.
- Confidence label and a short rationale.
- One or more source citations with publisher, document, publication date,
  source locator, and retrieval date.
- Limitations such as `commercial magnitude undisclosed`, `customer unnamed`,
  `forward-looking`, or `one-party disclosure`.

## 8. Fact, Guidance, Claim, And Inference

The product must not compress evidence into a single "true/false" flag.

### 8.1 Assertion Kinds

| Kind | Meaning | Example |
|---|---|---|
| `disclosed_fact` | A dated filing or primary source reports an observed event or state | NVIDIA names TSMC among its foundries |
| `company_guidance` | Management states an expectation about a future period | 2026 capital-expenditure range |
| `management_claim` | A company makes a technical or market claim that is not an audited financial fact | Product efficiency or capacity claim |
| `inferred_exposure` | The system connects supported premises but lacks a direct disclosure of the final edge | ASML may benefit from leading-edge capacity needed for an unnamed accelerator program |
| `user_hypothesis` | The Owner records a question or thesis for investigation | Power bottlenecks may shift value toward on-site generation |

### 8.2 Promotion Rules

- A model extraction is never itself a source.
- A bilateral announcement can support a named partnership but not undisclosed
  economics.
- A supplier-category disclosure cannot be promoted to a named customer edge.
- An inferred exposure remains inference even if confidence is medium.
- A secondary source can identify a candidate relationship for review but cannot
  establish a high-confidence edge by itself.
- User hypotheses never become disclosed facts without new evidence.

## 9. Confidence And Uncertainty

V1 uses transparent categorical confidence rather than a pseudo-precise score.

Each assertion records:

- Source authority.
- Relationship explicitness.
- Corroboration count and whether sources are independent.
- Extraction method and review status.
- Temporal fit.
- Geographic fit.
- Known contradictions or limitations.

Display labels:

- `high`: explicit named relationship or observed fact in a strong primary
  source, with no material contradiction.
- `medium`: primary evidence exists but is one-sided, category-level,
  forward-looking, or missing commercial magnitude.
- `low`: partial, stale, weakly matched, or materially ambiguous evidence.
- `inference`: a separately styled conclusion derived from cited premises; it
  is not displayed as a disclosed relationship regardless of analytical
  confidence.

Confidence is evaluated per assertion. It is not a permanent company score.

## 10. Time And Geography

### 10.1 Time

Every material assertion must have:

- `published_at`
- `observed_at` or reporting period
- `valid_from`
- `valid_to` or `expected_start` when known
- `reviewed_at`
- `freshness_state`: `current`, `review_due`, `stale`, or `superseded`

Default review policies:

- Quarterly Capex or capacity guidance: review at the next earnings release or
  after 120 days, whichever comes first.
- Announced projects: review every 90 days until operating, cancelled, or
  superseded.
- Named manufacturing relationships in annual filings: review at the next
  annual filing or a contradictory material announcement.
- Product sampling and qualification: review every 90 days until production
  status is known.
- Standards: current until a new version or correction is published.

### 10.2 Geography

Geography is attached to the relevant claim, project, or operation and uses a
controlled hierarchy:

```text
global -> country -> region/state -> metro/site
```

The product distinguishes:

- Company headquarters.
- Demand or deployment geography.
- Data-center site.
- Wafer fabrication.
- Packaging and test.
- Equipment or component manufacturing.
- Grid or utility region.

Unknown geography remains `unknown`; headquarters must not be used as a proxy
for manufacturing or deployment.

## 11. Versioned Taxonomy And Graph

### 11.1 Release Contract

Published graph releases are immutable and include:

- Graph release ID and semantic schema version.
- Taxonomy version.
- Published time and evidence cutoff time.
- Entity, relationship, assertion, and source-snapshot IDs.
- Release notes and a machine-readable diff from the prior release.
- Review owner and review state.

Corrections create a new release. They do not rewrite the prior release.

### 11.2 Identity

- Organizations, projects/sites, capabilities, standards, products/product
  generations, and geographies have distinct entity types.
- Listed securities are identifiers on an organization, not the organization
  identity itself.
- Aliases are versioned and market-qualified where needed.
- Mergers, renames, and joint ventures preserve lineage rather than reusing an
  ambiguous name.

### 11.3 Relationship Types

V1 should use a small controlled set:

- `buys_from`
- `supplies`
- `manufactures_for`
- `packages_or_tests_for`
- `develops_or_operates`
- `leases_or_provides_capacity_to`
- `invests_in`
- `partners_with`
- `co_designs`
- `adopts_or_supports_standard`
- `enables_capability`
- `competes_with`
- `depends_on`
- `inferred_exposure_to`

Inverse labels may be rendered in the UI, but one canonical direction is stored.

## 12. Source Strategy And Cost

| Tier | Sources | V1 role | Access/cost |
|---|---|---|---|
| 1 | Regulator filings and structured disclosure: SEC EDGAR, HKEXnews, DART/FSS | Highest-authority company facts and filed supplier/manufacturing disclosures | SEC and HKEX public access; OpenDART requires an issued API key for automation |
| 2 | Issuer investor relations, company-posted earnings transcripts, official bilateral announcements, annual reports | Capex guidance, named partnerships, project and product lifecycle | Generally public web access; archive source snapshot and terms metadata |
| 3 | Government and standards bodies: EIA, FERC, IEA, OCP, UEC, CXL, JEDEC, ASHRAE | Geography, grid context, capability and standards vocabulary | Many public documents; some standards have license or download restrictions, so store metadata/locators rather than redistributing restricted content |
| 4 | Licensed transcript, fundamentals, supply-chain, or market-data vendors | Optional scale and corroboration after V1 | Paid and credentialed; requires Owner approval before purchase or integration |
| 5 | Reputable journalism and industry research | Candidate discovery and contradiction search | Public or licensed; cannot alone establish a high-confidence edge |
| 6 | System inference and user hypotheses | Explicitly labeled analytical layer | No external data cost; never presented as source evidence |

The SEC provides free public filing and XBRL APIs subject to fair-access rules,
including a published rate limit of no more than ten requests per second and an
identifying user agent.
[SEC public data APIs](https://data.sec.gov/),
[fair-access limit](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits)

Recommended V1 cost: no paid source subscription. Manual curation should use
public Tier 1-3 sources. OpenDART automation and licensed transcript/supply-chain
data are later choices, not V1 blockers.

## 13. Update Workflow

V1 uses a review-first workflow:

```text
source candidate
  -> archived source snapshot and metadata
  -> bounded assertion extraction
  -> human/agent review against the source locator
  -> entity and relationship resolution
  -> confidence and limitation assignment
  -> draft release validation
  -> release diff review
  -> immutable publish
```

Update triggers:

- Monthly panorama review.
- Quarterly earnings and annual filings for demand anchors and major suppliers.
- Material partnership, capacity, product qualification, production, project,
  cancellation, or standards announcements.
- A contradiction or stale relationship found during stock research.

The release validator must reject:

- An edge without an assertion.
- A material assertion without a source or an explicit inference record.
- A source without publisher, title, publication date when available, URL or
  stable locator, and retrieval timestamp.
- An inferred edge styled as disclosed.
- Invalid entity IDs, relationship directions, taxonomy nodes, time ranges, or
  geography references.
- A published release that mutates a prior release ID.

## 14. Relationship To Existing Investment Flows

V1 may reuse:

- Canonical market-qualified stock identifiers.
- Official-source discovery and source metadata patterns.
- Provider-neutral source attempt, partial, unavailable, freshness, and
  sanitized-failure contracts.
- Versioned artifact and bounded evidence-projection patterns.
- Existing browser access and self-contained workbench delivery patterns.

V1 must not:

- Reuse `sectors` as the industry taxonomy.
- Store panorama relationships in `stock_sector_relations`.
- Read positions to rank or hide graph content.
- Write panorama assertions into `knowledge_items`, `candidate_insights`, or
  `user_insights`.
- Trigger valuation, Kline, decision-card, weekly-review, or research jobs
  merely by browsing the graph.
- Treat a listed security as the only entity type.

Stock research and valuation remain downstream destinations the Owner may open
deliberately. The panorama is an independent learning and relationship domain.

## 15. Metrics

V1 success is usefulness and trust, not graph size.

Product metrics:

- Percentage of sessions that start at a demand anchor and open at least one
  downstream relationship.
- Median number of evidence drawers opened per focused traversal.
- Use of geography, time, and `Disclosed only` filters.
- Number of follow-on stock research or valuation opens.
- Repeat visits after a graph release.

Quality metrics:

- 100% of published material relationships have a typed assertion and evidence,
  or are explicitly marked inference.
- 100% of source-backed assertions have a source locator and retrieval date.
- Zero inferred edges rendered as disclosed.
- Zero broken source-to-assertion references in a published release.
- Stale relationship count and median review age.
- Correction count by release and reason.

## 16. Proposed V1 Acceptance Criteria

1. The Owner can start from each of the six demand anchors and traverse at least
   two supported hops into the infrastructure chain.
2. The published V1 contains approximately 25-35 reviewed organizations/projects
   and 45-70 reviewed relationships across all six taxonomy groups.
3. Every material relationship has a direction, type, plain-language assertion,
   assertion kind, lifecycle state, valid time, geography or explicit unknown,
   confidence rationale, limitations, and at least one source or explicit
   inference derivation.
4. The Owner can toggle `Disclosed only` and visibly distinguish guidance,
   management claims, and inference.
5. The Owner can filter by layer, geography, time, lifecycle state, and
   confidence without losing the focused entity.
6. Node and relationship drawers expose source publisher, document title,
   publication date, source locator, retrieval date, and evidence limitations.
7. A table/list view exposes the same relationships and filters without
   requiring graph interaction.
8. At least one example demonstrates each important lifecycle distinction:
   announced versus operating, sampling versus mass production, and guidance
   versus observed fact.
9. The release records graph and taxonomy versions, an evidence cutoff, and a
   machine-readable diff contract; a second fixture release proves that prior
   published history remains immutable.
10. Invalid, source-less, dangling, time-inverted, or inference-mislabeled
    release fixtures fail validation.
11. The panorama does not read portfolio positions and browsing does not write
    stock knowledge, candidate insights, user insights, orders, or research
    jobs.
12. A listed organization can link explicitly to existing research or valuation
    when available, while an unlisted lab, project, standard, or capability can
    exist without a stock record.

## 17. Non-Goals And Later Candidates

Not in V1:

- Automated crawling, autonomous publication, or unrestricted model extraction.
- A complete global AI market map.
- Revenue, gross-profit, order, or market-share estimates where not disclosed.
- Company scoring, beneficiary ranking, recommendations, or price targets.
- Portfolio exposure, scenario P/L, or position sizing.
- Real-time news.
- Editable graph authoring in the Owner-facing browser.
- Paid supply-chain datasets.
- Regulations, export controls, subsidies, and tariffs as a fully modeled
  policy graph. They may appear only as sourced limitations on relevant V1
  relationships.

Strong later candidates, after V1 trust is demonstrated:

- Curator workbench and source-candidate queue.
- Automated filing and issuer-IR change detection with review-required drafts.
- Additional demand regions and sovereign AI projects.
- Product-generation and bill-of-material dependency views.
- Quantified exposure methodology with estimate provenance.
- Opt-in portfolio overlay.
- Historical scenario playback and graph-diff alerts.

## 18. Product Decisions And Readiness

Recommended decisions:

- Use a dedicated versioned panorama domain.
- Adopt a US demand/global supply-chain V1.
- Use manual official-first curation and no paid data.
- Keep facts and inference as separate first-class layers.
- Use a layered map plus equivalent table view.
- Keep portfolio, valuation synthesis, and autonomous ingestion out of V1.

No credential, paid-data, or infrastructure approval is needed to approve this
product scope.

The feature is not implementation-ready until the Owner or Feature Coordinator
accepts the bounded V1 scope and the Development Agent converts the linked
feasibility note into an implementation plan with exact schema, routes, tests,
and release ownership. Discovery does not authorize product-code changes or
deployment.
