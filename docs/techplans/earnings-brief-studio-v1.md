# Earnings Brief Studio V1 Technical Plan

**Status:** Locally implemented and verified; deployment and independent L3 acceptance pending
**PRD:** [`PRD-Earnings-Brief-Studio.md`](../product/PRD-Earnings-Brief-Studio.md)
**Quality route:** L3
**Deployment class:** Targeted quick deploy of `weekly-review-web`

## 1. Architecture

V1 is a dedicated, read-only package at `investment_knowledge_mcp/earnings_brief_studio`. It owns an immutable reviewed JSON release, strict validation, a bounded public projection, browser rendering, and export code. The aggregate gateway owns route admission and delegates to the package.

The feature reuses:

- `app_gateway.py` for explicit route ownership and access class;
- `weekly_review_web.py` as the aggregate HTTP handler;
- `web_experience.py` for primary navigation and visual tokens;
- provider-neutral provenance concepts from research packages, without importing their mutable job or persistence state;
- existing Playwright and deploy-classification infrastructure.

The feature does not read or write Weekly Review, Daily Market Brief, valuation, Panorama, portfolio, command, or trading state.

## 2. Files And Responsibilities

- `investment_knowledge_mcp/earnings_brief_studio/release.py`: frozen records, exact-key validation, calculation validation, fixture loading, public projection.
- `investment_knowledge_mcp/earnings_brief_studio/web.py`: page HTML, CSS, browser rendering, source drawer, canvas PNG export.
- `investment_knowledge_mcp/earnings_brief_studio/controller.py`: catalog and selected-release GET handling.
- `investment_knowledge_mcp/earnings_brief_studio/releases/2026-07-24.apple-fy2025-q1.v1.json`: immutable reviewed fixture.
- `investment_knowledge_mcp/app_gateway.py`: admit page, asset, catalog, and brief routes as public read.
- `investment_knowledge_mcp/weekly_review_web.py`: narrow delegating render/write helpers only.
- `investment_knowledge_mcp/web_experience.py`: add stable navigation item.
- `scripts/deploy_contract.py`: map package and route changes to `weekly-review-web` targeted quick.
- `tests/test_earnings_brief_release.py`: schema, evidence, derived calculation, conflict/missing, and projection tests.
- `tests/test_earnings_brief_web.py`: semantic HTML and Node browser-script tests, including nonblank canvas export.
- existing gateway, experience, deploy-classifier, and Playwright suites: regression and cloud journeys.

## 3. Storage And Idempotency

The canonical V1 release is a committed immutable JSON file. There is no database migration.

`load_release(company_id, fiscal_period_id)` resolves only the catalog's exact tuple. Repeated reads return the same object content, `release_id`, `generated_at`, and `evidence_as_of`. Unknown selectors return a sanitized 404 payload with the admitted catalog.

A later mutable generator must store immutable source snapshots and publish a new release ID. It must never overwrite an existing published release.

## 4. Validation

The loader rejects:

- unknown top-level or nested keys;
- duplicate or malformed stable IDs;
- unsupported currencies, units, states, claim kinds, scenario kinds, or source tiers;
- non-HTTPS source URLs;
- fields without source IDs or as-of values;
- management claims without admitted sources;
- non-available fields that carry canonical values;
- available fields without canonical values;
- derived fields whose declared result does not match formula inputs within tolerance;
- unresolved source, input-field, or supporting-claim references;
- a published release with any source or evidence record not reviewed;
- unbounded display strings or serialized public projections over 1 MiB;
- credential-looking keys, local paths, internal URLs, or raw document bodies.

The public projection is an exact allow list and never serializes internal validation details.

## 5. Source Snapshot And Provenance

V1 records official Apple investor-relations and SEC filing URLs with publication/retrieval dates, stable locators, and hashes of the bounded fixture evidence representation. It does not archive or redistribute full source documents.

Every public metric or claim carries:

- stable field or claim ID;
- evidence state;
- `as_of`;
- `source_ids`;
- optional formula and input IDs;
- optional candidate values for `conflict`.

The UI joins these IDs only after release validation.

## 6. Charts And Long-Image Rendering

The browser uses plain JavaScript and Canvas 2D; no frontend dependency is added.

Page charts:

- financial flow: proportional labeled nodes and connectors with a text table;
- trends: bars for quarterly revenue and a line/labels for gross margin;
- mix: stacked bars plus exact labeled legend.

The export renderer receives the already-validated public brief. It draws an editorial composition on a 1440-pixel-wide canvas, wraps text deterministically, measures section height before painting, uses semantic colors plus labels, appends sources, and downloads `canvas.toDataURL("image/png")`.

Export content parity tests assert the release ID, source count, KPI labels/values, scenario labels, and evidence cutoff are passed to the renderer. Browser acceptance verifies actual PNG dimensions and a nontransparent pixel sample.

## 7. Generation Lifecycle

V1 has no background generation lifecycle. The selector retrieves a published fixture.

Future lifecycle, if approved:

`missing -> collecting -> review_required -> published | failed`

Publication must remain a distinct reviewed action. Runtime collection failures must not change the last published release.

## 8. Access Contract

All V1 routes are public read:

- `GET /earnings-brief-studio`
- `GET /assets/earnings-brief-studio.js`
- `GET /api/earnings-briefs`
- `GET /api/earnings-brief?company_id=US.AAPL&period_id=FY2025-Q1`

There is no POST route. Existing canonical access-token handling remains untouched.

## 9. Verification

Developer verification:

- release/schema/calculation unit tests;
- missing/conflict mutation tests;
- browser-script tests in Node;
- gateway, navigation, and deploy-classification regressions;
- `git diff --check`;
- existing focused public gateway suites.

Visual verification:

- local page screenshots at 1440x1000 and 390x844;
- full-page screenshot inspection;
- chart SVG/canvas bounding boxes and nonblank pixels;
- source drawer interaction and source link href checks;
- exported PNG dimensions, file size, text/readability inspection, and content parity.

Independent L3 acceptance runs on the deployed cloud URL and records one Acceptance Queue item.

## 10. Deployment And Rollback

The change requires no image-layer, dependency, Compose, database, credential, or ingress modification. It uses targeted quick deploy for `weekly-review-web`.

Before deploy, reconcile the feature branch with latest `origin/main`, rerun focused tests, and check the shared production deployment channel. Deploy only a pushed commit through the serialized standard workflow.

Rollback is release-level rollback to the prior healthy application ref. Because the feature is additive and read-only, rollback removes the routes and navigation item without data restoration.

## 11. Implementation Traceability

| PRD criterion | Implementation area | Verification | State |
|---|---|---|---|
| Working selector and fixture | controller, release catalog, web | release/web/Playwright tests | local_verified |
| Typed evidence and provenance | release validator and fixture | mutation and projection tests | local_verified |
| Judgment, KPI, signal, flow, trends, mix, structure, scenarios | page renderer | semantic and visual tests | local_verified |
| PNG export | browser canvas renderer | real Chromium PNG signature, 1440px width, long height, and file-size test | local_verified |
| Shared shell and isolated state | gateway and web experience | gateway/navigation regressions | local_verified |
| Cloud acceptance | serialized deploy and L3 test | Acceptance Queue evidence | pending_deploy |

## 12. Plan Review

The bounded plan can be completed in one implementation pass. It introduces no external credential, provider, migration, or product decision. CN/HK/KR and live generation are separated because source/licensing feasibility and review workflow are genuine dependencies, not routine implementation work.
