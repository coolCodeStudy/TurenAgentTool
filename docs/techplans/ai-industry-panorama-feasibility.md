# AI Industry Panorama Technical Feasibility Note

Status: discovery feasibility; architecture recommendation only, not an implementation plan

Research snapshot: 2026-07-23

Linked PRD: [`../product/PRD-AI-Industry-Panorama.md`](../product/PRD-AI-Industry-Panorama.md)

## 1. Feasibility Conclusion

The bounded V1 in the linked PRD is technically feasible in one later
implementation pass, but it should not be implemented on the repository's
existing portfolio sector graph.

Recommended architecture:

> Create a dedicated, immutable, versioned panorama domain; reuse the
> repository's provider-result, official-source, artifact-safety, stock-identity,
> browser-access, and evidence-projection patterns only through narrow adapters.

The technically risky part is not graph rendering. It is preserving source,
assertion, time, geography, lifecycle, and fact-versus-inference semantics while
keeping published releases reproducible.

No production runtime code, schema, service, or deployment is changed by this
feasibility note.

## 2. Alternatives Considered

### 2.1 Static Report Or Hand-Built Diagram

Advantages:

- Lowest implementation effort.
- Easy to author an initial narrative.

Disadvantages:

- No stable entity or relationship identity.
- No filterable time, geography, lifecycle, or evidence model.
- Difficult to show diffs and corrections.
- Quickly becomes stale.
- Encourages unsupported lines between logos.

Decision: reject. It does not satisfy the Owner's requirement for an explorable,
durable learning product.

### 2.2 Reuse `sectors` And `stock_sector_relations`

Advantages:

- Existing tables, repository helpers, confidence, and source IDs.
- Existing stock context and portfolio graph code can read the relations.

Disadvantages:

- Only stocks can be related to sectors; V1 also needs private labs, standards,
  projects/sites, capabilities, products, and geographies.
- The taxonomy is a parent-child sector tree, while panorama entities need
  multiple simultaneous capabilities.
- Each stock-sector relation points to at most one source.
- There is no graph release, evidence cutoff, assertion kind, source locator,
  valid time, lifecycle, geography role, contradiction, or inference derivation.
- Reuse would couple industry learning to portfolio coverage and durable stock
  knowledge.

Decision: reject. Extending these tables until they fit would create a broad,
hard-to-reason-about schema that weakens existing portfolio contracts.

### 2.3 Dedicated Versioned Panorama Domain

Advantages:

- Models the required entity and evidence types directly.
- Preserves published history.
- Supports graph and table views from one public projection.
- Reuses existing source transports without inheriting portfolio behavior.
- Creates a stable future boundary for automated candidate ingestion.

Disadvantages:

- Requires a focused schema and validation layer.
- Manual V1 data needs a curator fixture/import path.
- A release validator and diff contract are mandatory before browser work.

Decision: recommend. The extra domain boundary is justified by the product's
trust requirements and prevents accidental portfolio coupling.

## 3. Relevant Repository Patterns

### 3.1 Provider-Neutral Source Outcomes

`investment_knowledge_mcp/data_sources/contracts.py` and
`investment_knowledge_mcp/data_sources/pool.py` already define:

- Typed source capabilities.
- Preferred, allowed, and fallback source plans.
- `ok`, `partial`, and `unavailable` outcomes.
- Attempted and selected sources.
- Coverage, freshness timestamps, cache state, and sanitized failures.

Reuse recommendation:

- Preserve these result semantics for future panorama source acquisition.
- Add a panorama-specific capability only when automated acquisition is in
  scope; V1 manual curation does not need to expand the shared enum.
- Keep transport success separate from assertion validity. A successful HTTP
  fetch does not validate a relationship.

### 3.2 Official Research Sources

`investment_knowledge_mcp/research/official_sources.py` and
`investment_knowledge_mcp/research/models.py` already provide:

- SEC, HKEX, issuer-IR, and official-page source discovery.
- `SourceDocument` metadata including source type, title, URL, publisher,
  publication time, notes, and bounded excerpt.
- Bounded fetching and source deduplication.

Reuse recommendation:

- Adapt `SourceDocument` into a panorama source candidate.
- Do not treat `SourceDocument` as a complete evidence snapshot. The panorama
  also needs retrieval time, content hash or immutable filing accession,
  source locator, access/license class, extraction method, review state, and
  supersession metadata.
- Keep market-specific official-source discovery independent from panorama
  persistence.

### 3.3 Research Validation And Fact Extraction

The research pipeline validates source keys and citations, extracts a bounded
set of financial/risk/guidance snippets, audits official versus secondary
publishers, and writes source-fact artifacts.

Reuse recommendation:

- Reuse source-key integrity, validation style, and official-publisher checks.
- Do not reuse the current fact extractor as the panorama relationship
  extractor. Its patterns are intentionally stock-research and valuation
  oriented and cannot safely identify arbitrary supplier, customer, project,
  lifecycle, geography, or technical-standard assertions.
- Future extraction should produce review-required assertion candidates, never
  published edges.

### 3.4 Stock Valuation Artifact And Evidence Projection

`stock_valuation_packet.v1` demonstrates:

- An explicit schema version.
- Stable opaque fact and source IDs.
- Source references on facts and input references on calculations.
- Immutable timestamped artifacts plus a latest pointer.
- An allow-listed bounded public evidence projection.
- Separation of facts, assumptions, calculations, interpretation, and watch
  items.

Reuse recommendation:

- Apply the same ideas to `ai_industry_panorama_release.v1`.
- Generate graph and table views only from a validated bounded public
  projection.
- Do not embed raw source documents, credentials, diagnostics, local paths, or
  unbounded excerpts in browser responses.

### 3.5 Kline And Market-Data Contracts

The Kline product demonstrates:

- Provider and adjustment metadata.
- Explicit data-quality warnings.
- Deterministic rules.
- Confidence driven by data quality and sample support.
- Useful insufficient-evidence output.

Reuse recommendation:

- Treat panorama relationship confidence as a deterministic projection of
  evidence attributes, not model tone.
- Preserve an explicit insufficient-evidence or unsupported-edge state.
- Kline bars and Kline analysis are otherwise outside this domain.

### 3.6 Browser Workbench Patterns

The Command Workbench and weekly-review browser surfaces demonstrate:

- Self-contained HTML served by an existing Python web surface.
- Small JSON APIs.
- Gateway/access-token boundaries.
- Structured metadata around results.
- Browser-local state that excludes tokens.
- Cloud acceptance through the existing public web service.

Reuse recommendation:

- Add a dedicated route in the existing user-facing web service rather than a
  new service for V1.
- Keep the panorama page read-only.
- Use a dedicated panorama module and API rather than adding graph logic to
  `command_workbench.py` or `weekly_review_web.py`.
- The later implementation plan should assess whether the current
  self-contained HTML approach remains maintainable for the chosen graph
  renderer; no frontend library decision is made in discovery.

### 3.7 Existing Portfolio Graph

`investment_knowledge_mcp/portfolio_graph.py` is a read-only coverage queue
driven by current positions and stock/sector/knowledge coverage. It is not a
general graph engine.

Reuse recommendation:

- Reuse no domain logic.
- Preserve its safety principle that a read-only view does not automatically
  create stock, sector, knowledge, or insight records.

## 4. Proposed Domain Boundary

The later implementation should own focused modules conceptually equivalent to:

- Panorama schema and validation.
- Panorama release builder and diff.
- Panorama repository or artifact store.
- Panorama public projection.
- Panorama read API and browser renderer.
- Panorama curated seed/import tool.

The exact file paths belong in the later implementation plan. Discovery should
not lock them before the Feature Coordinator approves the V1 and a Development
Agent reviews the current main branch.

The panorama domain may depend on:

- Generic database transaction utilities.
- Generic source-result and failure contracts.
- Official-source candidate adapters.
- Canonical stock symbol normalization for optional organization identifiers.
- Existing web access policy and response helpers.

Portfolio, weekly review, valuation, Kline, decision-card, research-job, and
user-insight modules must not depend on the panorama domain in V1.

## 5. Proposed Data Contract

### 5.1 Release

```json
{
  "schema_version": "ai_industry_panorama_release.v1",
  "release_id": "aip-2026-07-23.1",
  "taxonomy_version": "ai-industry-taxonomy.v1",
  "published_at": "2026-07-23T00:00:00Z",
  "evidence_cutoff_at": "2026-07-23T00:00:00Z",
  "prior_release_id": null,
  "status": "published",
  "release_notes": [],
  "entities": [],
  "taxonomy_nodes": [],
  "relationships": [],
  "assertions": [],
  "evidence": [],
  "sources": [],
  "diff": {}
}
```

Published payloads are immutable. `draft` and `reviewed` are workflow states;
only validated `published` releases are visible on the Owner-facing page.

### 5.2 Entity

Required fields:

- Stable opaque ID.
- Entity type: organization, project/site, capability, product/generation,
  standard, or geography.
- Canonical name and aliases.
- Capability taxonomy references.
- Geography references with roles.
- Optional listed-security identifiers.
- Valid time and status.

An organization may have zero or many securities. An unlisted model lab and a
data-center project remain first-class entities.

### 5.3 Relationship

Required fields:

- Stable opaque ID.
- Canonical source and target IDs.
- Controlled relationship type.
- Assertion IDs.
- Lifecycle state.
- Valid/expected time.
- Geography references and roles.
- Confidence label and rationale.
- Limitation codes.
- Review state and reviewed time.

The relationship is a durable identity; its assertions can change across
releases. For example, an `announced` project can later gain a new `operating`
assertion without erasing the announcement.

### 5.4 Assertion

Required fields:

- Stable opaque ID.
- Relationship or entity subject.
- Plain-language text.
- Assertion kind.
- Evidence IDs or inference-premise assertion IDs.
- Observed/reporting period.
- Valid time.
- Geography.
- Extraction method.
- Review status.
- Confidence inputs and derived display label.
- Contradictions and limitations.

Inference derivations must cite premise assertion IDs, not only source URLs.
This allows the UI to show why the inference exists.

### 5.5 Evidence And Source Snapshot

Source metadata:

- Stable opaque source ID.
- Source family and tier.
- Publisher.
- Document title and type.
- Publication time.
- Canonical URL or filing accession.
- Retrieval time.
- Content hash when permitted and useful.
- Access/license class.
- Language.
- Superseded-by source ID when known.

Evidence metadata:

- Stable opaque evidence ID.
- Source ID.
- Page, section, paragraph, timestamp, XBRL concept/period, or other bounded
  locator.
- Short compliant excerpt or structured values where permitted.
- Extraction method and extractor version.
- Review state and reviewer.
- Evidence limitations.

The public projection may expose locators and short excerpts but must not
redistribute licensed documents or unbounded copyrighted text.

## 6. Persistence Options

### 6.1 Database-Native Releases

Normalized tables would support:

- Entity and alias search.
- Relationship filters.
- Source-to-assertion joins.
- Release membership and diffs.
- Later candidate review workflows.

Risks:

- More migration and repository work.
- Release immutability needs explicit constraints and tests.

### 6.2 Validated JSON Release Artifacts

Timestamped JSON releases would support:

- Fast initial authoring.
- Reproducible fixtures and diffs.
- Simple static read APIs.
- No immediate database migration.

Risks:

- Search and curator workflows become harder as graph size grows.
- Concurrency and candidate-review state need a later store.

### 6.3 Recommendation

Use a hybrid:

- Author and validate one canonical release document.
- Persist normalized release records in PostgreSQL if the later implementation
  review confirms schema work is proportionate.
- Always export the bounded canonical `ai_industry_panorama_release.v1` artifact
  for reproducibility and testing.

If schema review identifies material migration risk, V1 may start with immutable
validated artifacts and a read-only index, provided the public contract and
future normalized IDs are unchanged. This is the one technical choice the later
Development Agent should settle after measuring current migration conventions.

## 7. Confidence Derivation

Do not store only a numeric confidence. Store the inputs:

```json
{
  "source_authority": "regulator_filing",
  "explicitness": "named_relationship",
  "corroboration": "single_primary",
  "temporal_fit": "current",
  "geographic_fit": "specific",
  "extraction": "reviewed_manual",
  "contradiction_state": "none",
  "display_label": "high"
}
```

Deterministic rules:

- Inference never renders as disclosed, irrespective of display confidence.
- `high` requires reviewed primary evidence and an explicit named or directly
  observed assertion.
- Forward-looking, one-party, or category-level disclosures are capped at
  `medium`.
- Unreviewed model extraction is not publishable.
- Stale or materially contradicted evidence is `low` or superseded.
- Missing geography or commercial magnitude becomes a visible limitation; it
  does not necessarily invalidate the relationship.

## 8. Acquisition And Source Tiers

### 8.1 V1

V1 should use curated source records with no autonomous network job. Curators
may use:

- SEC EDGAR public filings and XBRL.
- HKEXnews public documents.
- Issuer annual reports, investor presentations, results releases, and
  company-posted transcripts.
- Official company partnership and project announcements.
- Government and standards-body sources.

OpenDART automation is not required for V1. Its API requires an issued 40
character authentication key and has request limits documented by FSS.
[OpenDART guide](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019002)

### 8.2 Later Automated Candidates

A future acquisition worker may:

- Schedule source discovery by entity and source family.
- Reuse `DataSourcePool` attempt/fallback semantics.
- Save immutable source snapshots and extraction metadata.
- Produce `relationship_candidate` and `assertion_candidate` records.
- Require review before inclusion in a release.

It must not:

- Publish edges from model output.
- Treat transport success as evidence validation.
- bypass source access terms, rate limits, or license restrictions.
- Hide extraction gaps behind a confident summary.

## 9. Read API And Browser Projection

The later implementation should expose a small read contract:

- Latest published release metadata.
- Bounded graph projection with filters.
- Entity detail.
- Relationship detail.
- Release diff.
- Search/alias resolution.

Required protections:

- Hard caps on nodes, edges, response bytes, nesting depth, and source excerpts.
- Allow-listed fields only.
- No credentials, auth headers, raw provider failures, stack traces, local
  paths, or unrestricted source bodies.
- Stable pagination or focus-based traversal rather than returning an
  unbounded graph.
- The table view reads the same projection as the map.

Rendering recommendation:

- Use a layered directed layout for the focused traversal.
- Do not render all graph edges by default.
- Style assertion kinds and lifecycle states independently.
- Preserve filters and focus in the URL so a view can be reopened.
- Provide keyboard navigation and an equivalent relationship table.

## 10. Versioning And Diff

Release validation must prove:

- Referential integrity.
- Controlled enum values.
- Non-inverted time ranges.
- Valid taxonomy and geography references.
- Evidence or explicit inference derivation on every material assertion.
- No unreviewed assertion in a published release.
- No inference mislabeled as disclosed.
- Source locator and retrieval metadata completeness.
- Stable IDs across unchanged records.
- Published release immutability.

Diff categories:

- Entity added, changed, merged, or retired.
- Relationship added, changed, expired, or removed.
- Assertion added, superseded, or contradicted.
- Evidence added or replaced.
- Taxonomy node added, renamed, moved, or deprecated.

Removal should include a reason such as correction, expiry, entity merge, or
relationship no longer supported.

## 11. Security, Safety, And Licensing

- V1 is read-only on the Owner-facing surface.
- Curated imports are administrative/offline implementation concerns, not
  public endpoints.
- Source access credentials, if added later, remain server-side.
- Licensed or access-restricted standards and reports are cited by metadata and
  locator; their bodies are not copied into public artifacts.
- Short excerpts must remain bounded and attributable.
- The graph makes no trade, allocation, or recommendation.
- No browse action writes portfolio, knowledge, insight, or research-job state.

## 12. Testing Feasibility

The V1 contract is testable without live source access.

Domain fixture coverage:

- Six demand anchors.
- Every entity and relationship type in V1.
- Named bilateral relationship.
- One-sided named supplier relationship.
- Category-only supplier relationship.
- Guidance and later actual.
- Announced, under-construction, operating, sampling, and mass-production
  states.
- Multi-geography relationship.
- Inference with premise IDs.
- Contradiction and supersession.
- Taxonomy version change.

Validator failure coverage:

- Dangling entity, taxonomy, geography, source, evidence, or premise reference.
- Material assertion without source or inference premises.
- Invalid enum.
- Time inversion.
- Inference labeled as disclosed.
- Unreviewed assertion in published release.
- Missing source locator or retrieval timestamp.
- Mutation of a published release.
- Oversized excerpt or public response.

API/browser coverage:

- Anchor focus and one-/two-hop traversal.
- Filters for layer, geography, time, lifecycle, confidence, and disclosed-only.
- Node and edge drawers.
- Equivalent table rows.
- Search and aliases.
- Release diff.
- Safe not-found and empty-filter states.
- No stock/portfolio/insight/research-job writes.
- Access policy and response leakage regression.

Independent acceptance should use the deployed Owner-facing route only after a
later implementation, review, and deploy. No deployment is required for this
discovery branch.

## 13. Performance Feasibility

The bounded V1 size is small:

- 25-35 organizations/projects.
- 45-70 relationships.
- A few hundred assertions/evidence locators at most.

This does not require a graph database. PostgreSQL or validated JSON plus an
in-memory/indexed projection is sufficient. The public API should still be
focus-based and bounded so the contract scales without later breaking clients.

A specialized graph database should be considered only after measured needs
such as deep path queries, substantially larger graphs, or concurrent curation
make PostgreSQL unsuitable.

## 14. Delivery Risks

### 14.1 Evidence Semantics Drift

Risk: UI work begins before assertion and evidence types are locked, resulting
in unlabeled edges.

Mitigation: implement and review schema, validator, fixtures, and public
projection before the graph UI.

### 14.2 Taxonomy Overreach

Risk: the first taxonomy attempts to classify every AI market and becomes
unmaintainable.

Mitigation: lock the six V1 groups and allow multi-capability tags; version all
taxonomy changes.

### 14.3 False Precision

Risk: users interpret confidence or Capex as quantified vendor revenue exposure.

Mitigation: categorical evidence labels, visible limitations, no exposure
percentages without a separate approved methodology.

### 14.4 Source Instability And Licensing

Risk: company pages move, PDFs change, or standards restrict redistribution.

Mitigation: stable filing accessions where available, retrieval metadata,
hashes when permitted, bounded excerpts, access/license class, and source-link
health checks.

### 14.5 Portfolio Coupling

Risk: graph content is filtered or ranked by holdings and starts writing
unsupported knowledge into stock records.

Mitigation: separate schema/module and explicit no-write boundary tests.

### 14.6 Frontend Maintainability

Risk: adding a sophisticated graph to a large self-contained HTML module makes
the existing web surface harder to maintain.

Mitigation: later plan must isolate panorama rendering and assets behind a
focused route/module and run frontend architecture review if the chosen library
or bundle changes the current delivery model.

## 15. Implementation Readiness Gates

Before implementation dispatch:

1. Feature Coordinator accepts the PRD's six-anchor, US-demand/global-supply V1.
2. Development Agent inspects current main and chooses database-backed versus
   artifact-first persistence while preserving the public release contract.
3. Exact module, migration, route, access, and test files are named in a
   technical implementation plan.
4. A curated V1 entity/relationship manifest and review owner are named.
5. Quality route is selected. A user-facing graph with evidence and browser
   navigation should default to independent browser acceptance.
6. Feature Registry moves from discovery `draft` to `ready` only after these
   gates.

No credentials are required for the recommended V1. Paid data, OpenDART
automation, and autonomous acquisition require separate approval only if later
added.

## 16. Recommended Next Coordinator Action

`accept_and_route` only after the Feature Coordinator reviews this discovery
package:

- If the bounded V1 is accepted, update PRD and technical status to `ready`,
  choose the quality route, generate the feature handoff packet, and dispatch a
  Development Agent to write the exact implementation plan before code changes.
- If the scope is rejected, return the package to Product with one concrete
  correction list.
- Do not dispatch implementation from a `draft` registry state.
- Deploy decision for this discovery branch: `not_required` because it changes
  documentation and delivery state only.
