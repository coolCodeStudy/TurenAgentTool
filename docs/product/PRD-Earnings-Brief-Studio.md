# PRD: Earnings Brief Studio

**Status:** Ready for implementation
**Owner:** Product Owner
**Feature Coordinator:** Earnings Brief Studio coordinator
**Quality route:** L3
**Last updated:** 2026-07-24

## 1. Product Definition

Earnings Brief Studio is a browser workspace for selecting a company and reporting period, opening an evidence-backed quarterly earnings brief, inspecting the provenance of every material claim, and exporting a polished long-form PNG.

The first screen is the working studio. It is not a marketing page. V1 ships one reviewed, fixture-backed US example and an architecture that admits additional issuers without changing the public contract.

The product is analytical research software. It must not present personalized buy, sell, or position-sizing advice.

## 2. User Problem

Quarterly filings, earnings releases, presentations, and calls contain different pieces of the same story. A user must currently reconcile them manually, verify figures, identify management signals, separate market attention from structural evidence, and rebuild the result for sharing.

The Studio condenses that work while keeping evidence visible. Visual polish must never hide missing, conflicting, stale, or secondary evidence.

## 3. Approved V1 Scope

V1 includes:

- one fixture-backed US issuer and reporting period: Apple Inc. (`US.AAPL`), fiscal 2025 first quarter ended 2024-12-28;
- a company/period selector whose catalog exposes only supported releases;
- a generated-at timestamp and an evidence as-of timestamp with distinct meanings;
- a one-line core judgment;
- headline KPI cards;
- earnings-call or management-signal cards;
- revenue and profit-flow visualization;
- quarterly revenue and gross-margin trend charts;
- revenue-mix visualization;
- market-focus and structural-signal sections;
- bull, base, and bear scenarios with explicit validation conditions;
- a source drawer with stable source identity, family, tier, date, locator, URL, and evidence status;
- per-field provenance and typed missing/conflict states;
- deterministic, client-side long PNG export of the visible brief;
- responsive desktop and mobile browser layouts;
- public, read-only access through the existing browser gateway and navigation shell.

V1 does not include:

- live crawling, autonomous publication, or background generation;
- paid providers, new credentials, or a second access-token mechanism;
- editable narratives or user-authored scenario persistence;
- portfolio, valuation, Weekly Review, Daily Market Brief, Panorama, or Trading Agent state writes;
- personalized recommendations;
- PDF export;
- CN, HK, or KR issuer catalogs.

CN/HK/KR are bounded follow-up scope. Their regulatory document formats, issuer archive stability, transcript availability, and redistribution rules need a separate provider-feasibility review. They do not block the US vertical slice.

## 4. Workflow

1. The user opens `/earnings-brief-studio`.
2. The Studio loads the public release catalog.
3. The user selects an admitted company and reporting period.
4. The Studio retrieves the immutable reviewed brief for that exact key.
5. The user scans the judgment and KPI layer, then the signals, flows, trends, structure, and scenarios.
6. Selecting a provenance marker or source count opens the source drawer and highlights the supporting source records.
7. Missing or conflicting evidence remains visible in place and in the source drawer.
8. The user selects `Export PNG`; the browser renders the same ordered brief into a long image and downloads it.

Retrieval is idempotent. Reopening the same release key returns the same release ID and evidence snapshot. `generated_at` may describe the immutable publication event; it must not be rewritten on each read.

## 5. Evidence Hierarchy

Evidence tiers are:

1. `regulatory_filing`: SEC or other regulator-hosted filing.
2. `issuer_ir`: issuer earnings release, presentation, prepared remarks, or issuer-hosted call material.
3. `exchange_filing`: official exchange disclosure.
4. `official_transcript`: issuer-hosted or filing-attached call transcript.
5. `consensus_secondary`: clearly labeled reputable consensus or secondary research.

V1 material claims use tiers 1-2. Secondary evidence cannot independently support a disclosed figure or management claim.

Every source record contains:

- `source_id`;
- `family`;
- `tier`;
- `publisher`;
- `document_title`;
- `url`;
- `publication_date`;
- `retrieved_at`;
- `as_of`;
- `locator`;
- `content_hash`;
- `review_state`.

Every numeric field and management claim references one or more `source_id` values and carries its own `as_of`.

## 6. Evidence State And Conflict Rules

The exact evidence states are:

- `available`: one or more admitted sources support the value or claim;
- `missing`: the expected field is unavailable;
- `not_disclosed`: the issuer explicitly does not disclose the field;
- `not_applicable`: the field does not apply;
- `conflict`: admitted sources disagree beyond formatting or rounding tolerance;
- `secondary_only`: only labeled secondary evidence is available;
- `stale`: the evidence predates the selected reporting period or required as-of boundary.

Rules:

- A field in any state other than `available` must not expose a canonical numeric value.
- Conflicting candidate values remain visible with separate source references.
- Rounding differences are reconciled only when the canonical base-unit values agree within the declared tolerance.
- Missing data is not converted to zero.
- Derived values list their input field IDs and formula.
- Narrative claims distinguish `disclosed_fact`, `management_claim`, and `analytical_inference`.
- An analytical inference lists supporting claim IDs and is visually labeled.
- The Twitter/X reference image is never an evidence source.

## 7. Public Output Contract

The public projection uses schema `earnings_brief_public.v1`:

```json
{
  "ok": true,
  "schema_version": "earnings_brief_public.v1",
  "release": {},
  "catalog": [],
  "brief": {
    "company": {},
    "reporting_period": {},
    "generated_at": "",
    "evidence_as_of": "",
    "judgment": {},
    "kpis": [],
    "management_signals": [],
    "financial_flow": {},
    "quarterly_trends": [],
    "revenue_mix": [],
    "market_focus": [],
    "structural_signals": [],
    "scenarios": [],
    "sources": []
  }
}
```

The release key is `<canonical_company_id>:<fiscal_period_id>:<release_id>`. The catalog key is `<canonical_company_id>:<fiscal_period_id>`.

`generated_at` is the time the reviewed immutable release was produced. `evidence_as_of` is the latest admitted evidence cutoff. Browser read time is not either value.

Amounts store decimal strings plus currency and unit. Percentages store decimal strings. The renderer formats values for display but does not parse prose to recover numbers.

## 8. Browser Experience

The visual system takes inspiration from the reference's information hierarchy and density, not its exact artwork.

Desktop uses a centered editorial canvas with:

- compact selector and export controls;
- masthead and evidence timestamp;
- dark judgment band;
- responsive KPI grid;
- signal cards;
- a flow diagram with accessible text equivalents;
- trend and mix charts with labels and non-color encodings;
- paired market-focus and structural-signal panels;
- three scenario cards;
- source appendix and source drawer.

Mobile uses a single-column reading order. Charts must remain readable without horizontal scrolling. All interactive controls have keyboard focus and descriptive labels.

Source links open the canonical HTTPS document. A visible provenance control shows the supporting source count and evidence state. No raw document body, credential, local path, internal URL, stack trace, or unbounded excerpt appears.

## 9. PNG Export Contract

`Export PNG` creates a PNG in the browser with:

- a fixed 1440-pixel logical width;
- a height derived from content with a bounded maximum;
- the same section order and displayed values as the browser brief;
- company, period, release ID, generated-at, evidence-as-of, and source appendix;
- readable text at native scale;
- no controls, focus rings, browser chrome, hidden source drawer, or access tokens;
- filename `<ticker>-<period>-earnings-brief-<release-id>.png`.

Export failure is recoverable and leaves the brief usable. V1 does not claim pixel parity between the responsive page and export; it claims content parity and a stable editorial composition.

## 10. Acceptance Criteria

1. `/earnings-brief-studio` opens the working studio and exposes the Apple FY2025 Q1 fixture.
2. The API returns only the allow-listed public schema and exact selected release.
3. Every numeric field and management claim has source IDs, as-of metadata, and an admitted evidence state.
4. Missing and conflict fixtures fail closed: they never become zero or an unsupported canonical value.
5. Derived metrics expose formula and input field IDs, and calculation tests pass independently.
6. The page visibly separates disclosed facts, management claims, and analytical inferences.
7. Source links resolve to HTTPS issuer or regulator documents and the source drawer identifies tier, family, date, locator, and review state.
8. Desktop at 1440 pixels and mobile at 390 pixels have no overlapping text, clipped controls, or unreadable charts.
9. Flow, trend, and mix charts render nonblank and include accessible text equivalents.
10. PNG export downloads a nonblank long image with the same release ID, values, scenarios, and sources as the page.
11. No personalized advice, secret, token, raw error, filesystem path, or Twitter-sourced figure appears.
12. Existing public pages, protected access behavior, route ownership, and primary navigation regressions pass.
13. The deployed cloud page and API pass independent L3 acceptance before Owner acceptance is requested.

## 11. Product Decisions And Follow-Up

- V1 uses a reviewed immutable fixture because it proves the complete truth-and-export workflow without introducing an unreliable crawler or credential boundary.
- A future generation pipeline may create `review_required` candidates but cannot publish automatically.
- PDF is deferred because it adds pagination and font-embedding concerns without improving the first user journey.
- CN/HK/KR support requires a separate feasibility record covering official source availability, transcript rights, issuer identifier mapping, and locale-specific fiscal period semantics.
