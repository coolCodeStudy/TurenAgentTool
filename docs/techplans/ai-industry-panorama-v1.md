# AI Industry Panorama V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a public, read-only AI industry panorama whose versioned graph, table, filters, and evidence drawers let the Owner trace six demand anchors through first-order AI infrastructure relationships without presenting inference as fact.

**Architecture:** Store V1 as an immutable reviewed JSON release inside a dedicated `investment_knowledge_mcp.ai_industry_panorama` package. A strict loader validates the release and produces one allow-listed public projection; a dedicated controller and browser renderer expose that projection through the existing `weekly-review-web` aggregate gateway. Plain JavaScript renders an accessible layered SVG and equivalent relationship table without a new frontend or database dependency.

**Tech Stack:** Python 3.11 standard library, existing `http.server` gateway, immutable JSON, HTML/CSS/plain JavaScript/SVG, `unittest`, Node-based browser-script harnesses, Playwright, existing targeted-quick deploy workflow.

## Global Constraints

- Implement only the approved bounded V1: six demand anchors, 25-35 entities/projects, and 45-70 reviewed relationships.
- Use a committed immutable release artifact; do not add a database migration, graph database, runtime crawler, scheduled ingestion, or mutable browser authoring.
- Keep `disclosed_fact`, `company_guidance`, `management_claim`, `inferred_exposure`, and `user_hypothesis` distinct in storage and display.
- Every published relationship must have stable identity, time, geography, lifecycle, confidence inputs, and at least one reviewed evidence reference.
- A relationship labeled as inference must show its derivation and must never be promoted to disclosed fact by display copy.
- The browser projection is an allow list. It must exclude raw source bodies, secrets, local paths, internal errors, credentials, and unbounded excerpts.
- Reuse the existing public-read gateway and shared browser shell; do not couple the panorama to portfolio, stock-sector, valuation, Kline, weekly-review, or command domain logic.
- Add no paid source, credential, new external service, or frontend dependency.
- The product surface is public and read-only. V1 admits only three `GET` routes and no panorama mutation route.
- Select quality route `L3`: focused developer checks, one serialized deploy, and independent versioned cloud browser acceptance.
- New and agent-authored code, comments, tests, data metadata, and durable documents use English.

## Locked V1 Surface And Ownership

### Runtime files

- Create `investment_knowledge_mcp/ai_industry_panorama/__init__.py`: stable public imports only.
- Create `investment_knowledge_mcp/ai_industry_panorama/release.py`: typed immutable records, validation, release loading, confidence projection, and bounded public projection.
- Create `investment_knowledge_mcp/ai_industry_panorama/web.py`: page HTML and JavaScript renderers.
- Create `investment_knowledge_mcp/ai_industry_panorama/controller.py`: public `GET` dispatch.
- Create `investment_knowledge_mcp/ai_industry_panorama/releases/2026-07-24.v1.json`: canonical reviewed V1 release.
- Modify `investment_knowledge_mcp/app_gateway.py`: admit and dispatch the three public routes.
- Modify `investment_knowledge_mcp/web_experience.py`: add the panorama to the stable primary navigation.
- Modify `scripts/deploy_contract.py`: classify the dedicated package as targeted-quick for `weekly-review-web`.
- Modify `scripts/deploy_release.py`: include `/ai-industry-panorama` and `/api/ai-industry-panorama` in feature-route verification.

### Verification files

- Create `tests/test_ai_industry_panorama_release.py`: schema, invariants, counts, fact/inference boundaries, and public projection.
- Create `tests/test_ai_industry_panorama_web.py`: HTML/script semantics and browser behavior harness.
- Modify `tests/test_app_gateway.py`: route ownership, public access, and dispatch.
- Modify `tests/test_web_experience.py`: navigation order and active state.
- Modify `tests/test_deploy_change_classifier.py`: exact target/mode classification.
- Modify `tests/test_deploy_release.py`: feature-route smoke contract.
- Modify `e2e/cloud-pages.spec.ts`: desktop and mobile panorama journey.
- Modify `e2e/public-api-contracts.spec.ts`: public page, asset, and API GET contracts.

### Durable delivery files

- Modify `docs/techplans/ai-industry-panorama-v1.md`: implementation traceability and evidence after each accepted task.
- Modify `docs/project-management/Feature-Registry.md`: implementation, evidence, deploy, and next-action state.
- Modify `docs/project-management/Acceptance-Queue.md`: keep one active L3 release-candidate row.
- Modify `docs/project-management/Delivery-Queue.md`: compact accepted Development, deploy, and Acceptance returns.
- Modify `docs/changes/ai-industry-panorama/context-packet.md`: exact ref, route, deploy event, acceptance evidence, and watch state.

## Exact Release Contract

`load_release()` returns a frozen `PanoramaRelease`:

```python
@dataclass(frozen=True)
class PanoramaRelease:
    schema_version: str
    release_id: str
    taxonomy_version: str
    published_at: str
    evidence_cutoff: str
    change_summary: tuple[str, ...]
    curator: str
    reviewer: str
    entities: tuple[PanoramaEntity, ...]
    sources: tuple[PanoramaSource, ...]
    evidence: tuple[PanoramaEvidence, ...]
    relationships: tuple[PanoramaRelationship, ...]
```

The only accepted `schema_version` is `ai_industry_panorama_release.v1`. Stable IDs use the prefixes `entity:`, `source:`, `evidence:`, and `relationship:`. The loader accepts an optional `Path` only for tests; production uses `Path(__file__).parent / "releases" / "2026-07-24.v1.json"`.

`validate_release(payload)` returns the frozen release or raises `PanoramaReleaseError` with a sanitized deterministic message. It validates:

- exact top-level and record keys;
- ISO-8601 dates/timestamps and `effective_from <= effective_to`;
- unique stable IDs and valid foreign keys;
- exactly six demand-anchor IDs;
- 25-35 entities and 45-70 relationships;
- a traversable path of at least two supported hops from every demand anchor;
- nonempty English labels and bounded summaries/excerpts;
- admitted taxonomy layers, entity kinds, relationship types, assertion kinds, lifecycle states, geography roles, source tiers, and review states;
- at least one evidence item per relationship;
- source locator, publication date, retrieval date, and publisher on every evidence path;
- inference derivation references only existing disclosed/guidance/claim relationships;
- confidence labels derived from evidence attributes rather than accepted from prose;
- admitted optional research/valuation links with a canonical stock ID, safe internal path, and non-executing command hint;
- no credential-looking fields, local filesystem paths, raw source documents, or unsupported keys.

`build_public_projection(release)` returns:

```python
{
    "ok": True,
    "schema_version": "ai_industry_panorama_public.v1",
    "release": {...},
    "taxonomy": [...],
    "entities": [...],
    "relationships": [...],
    "evidence": [...],
    "sources": [...],
    "facets": {...},
}
```

No other release object is serialized by the gateway.

## Curated Release And Update Contract

- Product owns taxonomy meaning, V1 scope, non-goals, user journeys, and acceptance criteria.
- A Research curator adds or changes entities, relationships, evidence locators, and bounded excerpts in a new release file.
- A second reviewer confirms source identity, assertion kind, lifecycle, time, geography, and inference derivation before publication.
- Development owns the schema validator, public projection, browser behavior, and deployment mechanics; it does not decide that a market narrative is factual.
- Every update creates a new immutable release ID and file. Never edit the contents of a deployed release file under the same ID.
- Publication requires validator success, deterministic JSON order, a nonempty change summary, distinct curator/reviewer names, link checks, developer tests, and review approval.
- Official issuer, regulator, filing, standards-body, grid/operator, and consortium sources are Tier 1. Named technical or partner announcements are Tier 2. Secondary context is Tier 3 and cannot independently support `disclosed_fact`.
- V1 contains no automatic fetch. A later acquisition adapter may create review-required candidates but may not publish relationships.

## Task 1: Release Domain, Validator, And Reviewed V1 Artifact

**Files:**

- Create: `investment_knowledge_mcp/ai_industry_panorama/__init__.py`
- Create: `investment_knowledge_mcp/ai_industry_panorama/release.py`
- Create: `investment_knowledge_mcp/ai_industry_panorama/releases/2026-07-24.v1.json`
- Create: `tests/test_ai_industry_panorama_release.py`

**Interfaces:**

- Produces: `PanoramaReleaseError`, `load_release(path: Path | None = None) -> PanoramaRelease`, `validate_release(payload: Mapping[str, object]) -> PanoramaRelease`, `diff_releases(previous: PanoramaRelease, current: PanoramaRelease) -> dict[str, object]`, and `build_public_projection(release: PanoramaRelease) -> dict[str, object]`.
- Consumes: Python standard library only.

- [ ] **Step 1: Write failing validator and public-projection tests**

```python
def test_canonical_release_has_bounded_counts_and_six_demand_anchors() -> None:
    release = load_release()
    assert 25 <= len(release.entities) <= 35
    assert 45 <= len(release.relationships) <= 70
    assert sum(entity.is_demand_anchor for entity in release.entities) == 6

def test_inference_requires_visible_derivation() -> None:
    payload = canonical_payload()
    inferred = next(item for item in payload["relationships"] if item["assertion_kind"] == "inferred_exposure")
    inferred["derivation_relationship_ids"] = []
    with self.assertRaisesRegex(PanoramaReleaseError, "inference derivation"):
        validate_release(payload)

def test_second_fixture_produces_diff_without_mutating_history() -> None:
    previous = load_release()
    current = validate_release(next_release_payload(previous))
    change = diff_releases(previous, current)
    self.assertEqual(previous.release_id, "ai-panorama:2026-07-24:v1")
    self.assertEqual(change["from_release_id"], previous.release_id)
    self.assertEqual(change["to_release_id"], current.release_id)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_ai_industry_panorama_release -v`

Expected: import failure because `investment_knowledge_mcp.ai_industry_panorama.release` does not exist.

- [ ] **Step 3: Implement the frozen records, validator, loader, and projection**

Keep validation functions small and deterministic. Parse JSON with UTF-8, reject duplicate keys through `object_pairs_hook`, and never return the raw mapping after validation.

- [ ] **Step 4: Curate the canonical release**

Use only reviewed primary-source relationships from the PRD discovery set and directly linked official materials. Include the six anchors and enough first-order entities/projects to satisfy the locked counts and two-hop traversal invariant. Include explicit examples of announced versus operating, sampling versus mass production, and guidance versus observed fact. An unnamed customer remains an unnamed entity/category; do not infer a named customer. Technical compatibility is not a purchase contract. Add optional research/valuation links only for listed organizations with canonical stock IDs; unlisted labs, projects, standards, and capabilities carry no stock record.

- [ ] **Step 5: Run release tests and verify GREEN**

Run: `.venv/bin/python -m unittest tests.test_ai_industry_panorama_release -v`

Expected: all release, mutation, count, source, inference, confidence, and public-allowlist tests pass.

- [ ] **Step 6: Commit**

```bash
git add investment_knowledge_mcp/ai_industry_panorama tests/test_ai_industry_panorama_release.py
git commit -m "feat: add validated AI panorama release"
```

## Task 2: Public Page, Script, Filters, And Evidence Drawers

**Files:**

- Create: `investment_knowledge_mcp/ai_industry_panorama/web.py`
- Create: `tests/test_ai_industry_panorama_web.py`

**Interfaces:**

- Consumes: `build_public_projection(load_release())`.
- Produces: `render_panorama_html() -> str` and `render_panorama_script() -> str`.

- [ ] **Step 1: Write failing semantic and browser-script tests**

```python
def test_page_exposes_equivalent_graph_and_table_regions() -> None:
    html = render_panorama_html()
    assert 'id="panorama-graph"' in html
    assert 'id="relationship-table"' in html
    assert 'aria-label="Relationship evidence"' in html
    assert 'data-experience-ready="true"' in html
```

The Node harness must load the script with a synthetic public projection and assert that search, one-hop/two-hop focus, layer/geography/time/lifecycle/evidence/confidence filters, and disclosed-only mode update both SVG and table from one filtered relationship set.

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_ai_industry_panorama_web -v`

Expected: import failure because the renderer does not exist.

- [ ] **Step 3: Implement HTML and CSS**

Use `render_primary_navigation("ai_industry_panorama")` and `render_experience_css()`. The page must contain a heading, release metadata, change summary, search, filter controls, disclosed-only switch, hop-depth control, layered SVG region, equivalent table, entity drawer, relationship/evidence drawer, legend, loading status, and readable failure state.

- [ ] **Step 4: Implement plain JavaScript**

Fetch only `/api/ai-industry-panorama`. Render SVG nodes as keyboard-focusable buttons/groups with text labels; use deterministic layer columns and stable ordering rather than force simulation. Selecting a node focuses one or two hops. Selecting a relationship opens evidence, source, time, geography, lifecycle, assertion kind, confidence inputs, and derivation. The entity drawer renders an optional safe research/valuation link plus a non-executing command hint for listed organizations; unlisted entities render no stock placeholder. Never build HTML from unescaped source strings.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `.venv/bin/python -m unittest tests.test_ai_industry_panorama_web tests.test_web_experience -v`

Expected: all panorama browser-contract and preserved shared-shell tests pass.

- [ ] **Step 6: Commit**

```bash
git add investment_knowledge_mcp/ai_industry_panorama/web.py tests/test_ai_industry_panorama_web.py
git commit -m "feat: render AI panorama browser"
```

## Task 3: Gateway Routes And Shared Navigation

**Files:**

- Create: `investment_knowledge_mcp/ai_industry_panorama/controller.py`
- Modify: `investment_knowledge_mcp/app_gateway.py`
- Modify: `investment_knowledge_mcp/web_experience.py`
- Modify: `tests/test_app_gateway.py`
- Modify: `tests/test_web_experience.py`

**Interfaces:**

- Produces: `dispatch_panorama_get(handler: Any, parsed: ParseResult) -> bool`.
- Admits: public `GET /ai-industry-panorama`, `GET /assets/ai-industry-panorama.js`, and `GET /api/ai-industry-panorama`.

- [ ] **Step 1: Add failing route and navigation tests**

Assert exact owner `ai_industry_panorama`, `AccessClass.PUBLIC_READ`, no panorama `POST`, the page/asset/API response types, stable navigation order, and the panorama active state.

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_app_gateway tests.test_web_experience -v`

Expected: failures because the routes and `PageIdentity` are absent.

- [ ] **Step 3: Add the controller, route contracts, dispatch, and navigation**

The controller writes HTML, JavaScript, or the allow-listed projection. It catches `PanoramaReleaseError` and returns a sanitized `503` JSON degraded state for the API; the page remains loadable and renders that state. Do not add a write route or authorization token dependency.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `.venv/bin/python -m unittest tests.test_ai_industry_panorama_release tests.test_ai_industry_panorama_web tests.test_app_gateway tests.test_web_experience -v`

Expected: all targeted tests pass with existing routes unchanged.

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/ai_industry_panorama/controller.py investment_knowledge_mcp/app_gateway.py investment_knowledge_mcp/web_experience.py tests/test_app_gateway.py tests/test_web_experience.py
git commit -m "feat: expose AI panorama routes"
```

## Task 4: Deploy Classification And Release Verification

**Files:**

- Modify: `scripts/deploy_contract.py`
- Modify: `scripts/deploy_release.py`
- Modify: `tests/test_deploy_change_classifier.py`
- Modify: `tests/test_deploy_release.py`

**Interfaces:**

- Produces: targeted-quick classification with only `weekly-review-web`.
- Produces: local deploy verification for `/ai-industry-panorama` and `/api/ai-industry-panorama`.

- [ ] **Step 1: Add failing deploy-contract tests**

```python
def test_ai_panorama_package_targets_only_weekly_review_web() -> None:
    decision = classify_paths(["investment_knowledge_mcp/ai_industry_panorama/release.py"])
    assert decision.mode == DeployMode.TARGETED_QUICK
    assert decision.targets == ("weekly-review-web",)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_deploy_change_classifier tests.test_deploy_release -v`

Expected: the new package is not specifically classified and panorama routes are not verified.

- [ ] **Step 3: Add the exact package rule and feature-route smoke**

Add one prefix rule for `investment_knowledge_mcp/ai_industry_panorama/`. Do not broaden shared-service targets. Verify page status/content and API `ok`, schema version, release ID, and nonempty entities/relationships.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `.venv/bin/python -m unittest tests.test_deploy_change_classifier tests.test_deploy_release -v`

Expected: all deploy planning and preservation tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/deploy_contract.py scripts/deploy_release.py tests/test_deploy_change_classifier.py tests/test_deploy_release.py
git commit -m "ops: classify AI panorama release"
```

## Task 5: L3 Browser Journey, Traceability, And Delivery State

**Files:**

- Modify: `e2e/cloud-pages.spec.ts`
- Modify: `e2e/public-api-contracts.spec.ts`
- Modify: `docs/techplans/ai-industry-panorama-v1.md`
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`
- Modify: `docs/changes/ai-industry-panorama/context-packet.md`

**Interfaces:**

- Produces: one public, non-mutating Playwright journey and one active L3 Acceptance Queue item.
- Consumes: deployed exact ref on `http://47.84.190.191:8010/ai-industry-panorama`.

- [ ] **Step 1: Add the local Playwright journey**

The test must verify page heading/navigation/release metadata, no horizontal overflow at desktop and 390px mobile, nonblank graph and table, search for a demand anchor, one-hop and two-hop focus, disclosed-only filtering, geography/time/lifecycle filters, entity drawer, relationship evidence drawer, source link, visible inference label/derivation, keyboard focus, and zero panorama mutation requests.

- [ ] **Step 2: Run local developer verification**

Run the focused Python suite:

```bash
.venv/bin/python -m unittest tests.test_ai_industry_panorama_release tests.test_ai_industry_panorama_web tests.test_app_gateway tests.test_web_experience tests.test_deploy_change_classifier tests.test_deploy_release -v
```

Start only `weekly-review-web` in a dedicated local terminal, using the verified local database target inherited from preflight:

```bash
WEEKLY_REVIEW_WEB_HOST=127.0.0.1 WEEKLY_REVIEW_WEB_PORT=8010 .venv/bin/python -m investment_knowledge_mcp.weekly_review_web
```

Then run the non-mutating browser, smoke, and delivery checks from another terminal:

```bash
npm run test:e2e:cloud -- --project=desktop-public --grep "AI Industry Panorama"
.venv/bin/python scripts/smoke_test.py
python3 scripts/audit_delivery_state.py --feature "AI Industry Panorama"
```

Expected: all focused tests, local public browser journey, smoke checks, and delivery audit pass.

- [ ] **Step 3: Update implementation traceability and release-candidate state**

Record exact commits, test counts, selected `L3` route, planned URL, deploy mode `targeted_quick`, target `weekly-review-web`, and one Acceptance Queue row. Keep user acceptance `pending`.

- [ ] **Step 4: Commit and push the verified implementation candidate**

```bash
git add e2e docs/techplans/ai-industry-panorama-v1.md docs/project-management/Feature-Registry.md docs/project-management/Acceptance-Queue.md docs/project-management/Delivery-Queue.md docs/changes/ai-industry-panorama/context-packet.md
git commit -m "test: prepare AI panorama release acceptance"
git push origin codex/ai-industry-panorama-discovery
```

- [ ] **Step 5: Coordinator deploys through the shared serialized path**

Deploy Intent:

- Feature: AI Industry Panorama
- Ref or commit: exact pushed implementation candidate
- Deploy mode: `targeted_quick` (workflow-compatible `quick`)
- Affected services: `weekly-review-web`
- Reason: publish the new public panorama page/API/asset
- Verification URL: `http://47.84.190.191:8010/ai-industry-panorama`
- Watch owner/path: this AI Industry Panorama Feature Coordinator polling the one serialized deploy

Do not start another deploy channel if `production-deploy` is active.

- [ ] **Step 6: Dispatch independent L3 acceptance**

Run the cloud suite against the deployed exact ref:

```bash
E2E_BASE_URL=http://47.84.190.191:8010 npm run test:e2e:cloud -- --project=desktop-public --grep "AI Industry Panorama"
```

The Quality & Acceptance Lead captures desktop/mobile screenshots, API response, safety scan, exact ref/deploy event, and usefulness findings. Failure routes back to Development and the same Acceptance Queue item becomes `needs_retest`; pass routes to the Coordinator Return Gate and then `waiting_for_user_acceptance`.

## PRD Acceptance Traceability

| # | PRD acceptance criterion | Implementation | Verification |
|---|---|---|---|
| 1 | Start from each of six anchors and traverse two supported hops | Anchor flags plus validator reachability check and hop-focus UI | Six-anchor reachability unit test and Playwright focus journey |
| 2 | 25-35 reviewed entities/projects and 45-70 reviewed relationships across six groups | Canonical release count and taxonomy invariants | Validator count/taxonomy tests |
| 3 | Every material relationship carries direction, type, assertion, kind, lifecycle, time, geography, confidence, limits, and evidence/derivation | Strict relationship/evidence records | Missing-field, dangling, time, evidence, and projection tests |
| 4 | Disclosed-only mode and visible guidance/claim/inference distinctions | Assertion-kind facets, labels, and legend | Node harness and Playwright filter checks |
| 5 | Layer, geography, time, lifecycle, and confidence filters preserve focus | One shared plain-JS filtered/focused state | Browser harness and cloud journey |
| 6 | Drawers expose publisher, title, publication date, locator, retrieval date, and limitations | Entity and relationship/evidence drawers | Projection schema, semantic HTML, and Playwright checks |
| 7 | Equivalent table exposes the same relationships and filters | SVG and table consume the same filtered relationship IDs | Browser unit and Playwright equality assertions |
| 8 | Lifecycle distinctions cover announced/operating, sampling/mass production, and guidance/observed fact | Reviewed canonical examples and visible badges | Canonical-release and drawer tests |
| 9 | Graph/taxonomy versions, cutoff, machine-readable diff, and immutable prior history | `PanoramaRelease` metadata and `diff_releases` | Second programmatic fixture-release diff/immutability test |
| 10 | Invalid, source-less, dangling, time-inverted, or inference-mislabeled fixtures fail | Deterministic validator | Mutation test matrix |
| 11 | No portfolio reads or writes to knowledge, insights, orders, or jobs | Dedicated package and GET-only routes | Import-boundary, route, and zero-mutation Playwright tests |
| 12 | Listed organizations can link to existing research/valuation; unlisted entities need no stock | Optional allow-listed research links and command hints | Projection/UI tests for listed and unlisted entities |

## Release-Verification Manifest Template

- Candidate ref:
- Quality route: `L3`
- Deployed service: `weekly-review-web`
- Deploy mode/event:
- Public page: `http://47.84.190.191:8010/ai-industry-panorama`
- Public API: `http://47.84.190.191:8010/api/ai-industry-panorama`
- Release ID and evidence cutoff:
- Focused developer verification:
- Cloud Playwright evidence:
- Independent tester and date:
- Safety scan:
- Unresolved exceptions:
- User acceptance: `pending`

## Plan Self-Review

- Spec coverage: all approved V1 requirements and all 12 proposed acceptance criteria map to a task and verification.
- Scope: one implementation pass; no deferred P0/P1 split is needed because V1 is bounded, read-only, dependency-free, and uses one existing service.
- Type consistency: loader, projection, renderer, controller, gateway, deploy, and test interfaces use the same release and route names.
- Placeholder scan: the release-verification manifest intentionally contains empty evidence fields that must be replaced with real release evidence before handoff; no implementation step uses placeholder language or unspecified error handling.
- Product-code gate: implementation begins only after the Feature Coordinator accepts this plan and marks the technical-plan state `ready`.
