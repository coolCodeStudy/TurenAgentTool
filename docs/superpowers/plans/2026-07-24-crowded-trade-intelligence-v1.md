# Crowded Trade Intelligence V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a read-only end-of-day portfolio and single-symbol crowded-trade investigation that separates long crowding, short crowding/squeeze pressure, and speculative attention while refusing to score insufficient evidence.

**Architecture:** Extend the existing provider-neutral source contracts with explicit crowding capabilities, then add one entitlement-aware Futu evidence adapter behind `DataSourcePool`. A focused domain module converts bars and normalized positioning records into immutable evidence, applies deterministic family and coverage gates, and renders evidence-first reports. The command router and Command Workbench expose portfolio and single-symbol read-only entry points without adding a service or database schema.

**Tech Stack:** Python 3.11, dataclasses, enum, existing Futu OpenAPI transport, existing `DataSourcePool`, unittest/pytest, existing command router and Command Workbench.

## Global Constraints

- V1 is private, internal, single-user, read-only, and end-of-day.
- V1 supports portfolio holdings plus an explicit single-symbol investigation.
- US/HK may show a likelihood band only when at least three independent current families include price/volume and one direct positioning family.
- KR/CN remain evidence-only and must not show an aggregate likelihood band.
- Long crowding, short crowding/squeeze pressure, and speculative attention remain separate.
- Missing evidence is unknown, never zero; insufficient coverage returns `insufficient_evidence`.
- Valuation is context only and never changes a crowding score.
- Futu is optional and entitlement-gated by successful provider responses; failures degrade safely.
- No Yahoo expansion, scraping, premium data, social/community data, new network service, new database table, trade action, alert, or formal-memory write.
- Provider errors, credentials, local paths, and internal URLs never reach the public result.
- Every evidence point carries semantic metric, direction, source, observation time, fetch time, freshness, cohort, and use tier.

---

### Task 1: Explicit Source Capabilities And Approval Metadata

**Files:**
- Modify: `investment_knowledge_mcp/data_sources/contracts.py`
- Create: `investment_knowledge_mcp/data_sources/crowding.py`
- Modify: `investment_knowledge_mcp/data_sources/__init__.py`
- Modify: `tests/test_data_source_contracts.py`
- Create: `tests/test_data_source_crowding.py`

**Interfaces:**
- Produces: `SourceCapability.OWNERSHIP_CONCENTRATION`, `SHORT_INTEREST`, `OPTIONS_POSITIONING`, and `EVENT_CALENDAR`.
- Produces: immutable `SourceApproval`, `FUTU_CROWDING_APPROVAL`, and `source_is_approved(source_id, use_case)`.
- Consumers: Futu adapter and the crowding orchestrator.

- [x] **Step 1: Write failing capability and approval tests**

```python
def test_crowding_capabilities_are_explicit(self) -> None:
    self.assertEqual(SourceCapability.OWNERSHIP_CONCENTRATION.value, "ownership_concentration")
    self.assertEqual(SourceCapability.SHORT_INTEREST.value, "short_interest")
    self.assertEqual(SourceCapability.OPTIONS_POSITIONING.value, "options_positioning")
    self.assertEqual(SourceCapability.EVENT_CALENDAR.value, "event_calendar")

def test_futu_approval_is_private_internal_and_non_redistributable(self) -> None:
    self.assertTrue(source_is_approved("futu_crowding", "private_internal_research"))
    self.assertFalse(source_is_approved("futu_crowding", "public_redistribution"))
    self.assertEqual(FUTU_CROWDING_APPROVAL.access_tier, "account_entitled")
```

- [x] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_data_source_contracts.py tests/test_data_source_crowding.py -q
```

Expected: FAIL because the capabilities and crowding source module do not exist.

- [x] **Step 3: Add the minimal immutable approval contract**

```python
class SourceCapability(str, Enum):
    # existing values remain unchanged
    OWNERSHIP_CONCENTRATION = "ownership_concentration"
    SHORT_INTEREST = "short_interest"
    OPTIONS_POSITIONING = "options_positioning"
    EVENT_CALENDAR = "event_calendar"

@dataclass(frozen=True)
class SourceApproval:
    source_id: str
    access_tier: str
    permitted_uses: tuple[str, ...]
    redistribution_allowed: bool
    enabled_markets: tuple[str, ...]

FUTU_CROWDING_APPROVAL = SourceApproval(
    source_id="futu_crowding",
    access_tier="account_entitled",
    permitted_uses=("private_internal_research",),
    redistribution_allowed=False,
    enabled_markets=("US", "HK"),
)
```

`source_is_approved` must normalize the source/use strings and return `False` for unknown providers or uses.

- [x] **Step 4: Run GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_data_source_contracts.py tests/test_data_source_crowding.py -q
```

Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/data_sources tests/test_data_source_contracts.py tests/test_data_source_crowding.py
git commit -m "feat: define crowding source capabilities"
```

### Task 2: Entitlement-Aware Futu Crowding Evidence Adapter

**Files:**
- Modify: `investment_knowledge_mcp/futu_provider.py`
- Modify: `investment_knowledge_mcp/data_sources/crowding.py`
- Create: `tests/test_futu_crowding_provider.py`
- Modify: `tests/test_data_source_crowding.py`

**Interfaces:**
- Produces: `FutuCrowdingSnapshot`.
- Produces: `get_futu_crowding_snapshot(codes, start, end) -> FutuCrowdingSnapshot`.
- Produces: one multi-capability `FutuCrowdingSource` and `default_crowding_source_pool()`.
- Normalized record key: `{"symbol", "metric", "value", "unit", "direction", "observed_at", "published_at", "cohort", "metadata"}`.

- [x] **Step 1: Write failing transport-normalization tests**

Use a fake quote context whose methods return small DataFrame-compatible rows:

```python
def test_transport_normalizes_all_supported_families(self) -> None:
    context = FakeQuoteContext(
        ownership={"US.NVDA": [{"name": "Top holders", "holder_pct": 61.0, "static_date_str": "2026-06-30"}]},
        shorts={"US.NVDA": [{"shares_short": 30_000_000, "short_percent": 3.2, "days_to_cover": 1.8, "timestamp_str": "2026-07-15"}]},
        options={"US.NVDA": [{"code": "US.NVDA260731C200000", "option_type": "CALL", "volume": 1000, "option_open_interest": 5000, "option_implied_volatility": 42.0}]},
        events={"US.NVDA": [{"security": "US.NVDA", "earnings_date": "2026-07-29", "pub_type": "estimated"}]},
    )
    snapshot = fetch_with_context(context, ["US.NVDA"], "2026-07-17", "2026-07-31")
    self.assertEqual(61.0, snapshot.ownership_by_code["US.NVDA"][0]["holder_pct"])
    self.assertEqual(3.2, snapshot.short_interest_by_code["US.NVDA"][0]["short_percent"])
    self.assertEqual(5000, snapshot.options_by_code["US.NVDA"][0]["open_interest"])
    self.assertEqual("2026-07-29", snapshot.events_by_code["US.NVDA"][0]["event_date"])
```

Add failures for:

- unavailable OpenD;
- unsupported market;
- entitlement/provider error isolated to one family;
- empty family result;
- secret-bearing provider error redacted to a typed code;
- quote context always closed.

- [x] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_futu_crowding_provider.py tests/test_data_source_crowding.py -q
```

Expected: FAIL because transport and adapters are missing.

- [x] **Step 3: Implement the bounded Futu transport**

```python
@dataclass(frozen=True)
class FutuCrowdingSnapshot:
    ownership_by_code: dict[str, list[dict[str, Any]]]
    short_interest_by_code: dict[str, list[dict[str, Any]]]
    options_by_code: dict[str, list[dict[str, Any]]]
    events_by_code: dict[str, list[dict[str, Any]]]
    failures_by_code: dict[str, dict[str, str]]
    fetched_at: datetime
    source: str = "futu"
```

The transport must:

- accept only `US.` and `HK.` symbols;
- open one quote context per bundle request and close it in `finally`;
- call `get_shareholders_overview`;
- call `get_short_interest`;
- call `get_option_chain`, then `get_market_snapshot` in bounded chunks for option OI/volume/IV;
- call `get_earnings_calendar` in windows of at most seven days and filter by requested codes;
- bound option rows to the nearest expiries and cap snapshot codes;
- record family-level error codes without raw exception text.

- [x] **Step 4: Implement capability-specific adapters over one shared bundle loader**

```python
class FutuCrowdingSource:
    def __init__(self, loader: Callable[..., FutuCrowdingSnapshot]) -> None:
        self.descriptor = ProviderDescriptor(
            "futu_crowding",
            (
                SourceCapability.OWNERSHIP_CONCENTRATION,
                SourceCapability.SHORT_INTEREST,
                SourceCapability.OPTIONS_POSITIONING,
                SourceCapability.EVENT_CALENDAR,
            ),
            ("US", "HK"),
            8.0,
            0,
            "crowding",
            3600,
        )
        self._loader = loader

    def fetch(self, request: DataRequest) -> DataResult:
        # Validate approval, capability, market, one symbol, and dates.
        # Normalize only the requested semantic family.
        # Return typed unavailable/partial results with redacted failures.
```

The default pool registers this provider once. Its shared memoized bundle loader switches normalization by `request.capability`, so the four capability requests reuse one symbol/date bundle without violating `DataSourcePool`'s unique `source_id` rule.

- [x] **Step 5: Run GREEN and existing Futu-adjacent tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_futu_crowding_provider.py tests/test_data_source_crowding.py tests/test_data_source_market_bars.py -q
```

Expected: all tests pass; no local OpenD is started or contacted by tests.

- [x] **Step 6: Commit**

```bash
git add investment_knowledge_mcp/futu_provider.py investment_knowledge_mcp/data_sources/crowding.py tests/test_futu_crowding_provider.py tests/test_data_source_crowding.py
git commit -m "feat: add Futu crowding evidence adapter"
```

### Task 3: Deterministic Evidence, Coverage, And Scoring Engine

**Files:**
- Create: `investment_knowledge_mcp/crowding_intelligence.py`
- Create: `tests/test_crowding_intelligence.py`

**Interfaces:**
- Produces: `EvidenceDirection`, `EvidenceQuality`, `CrowdingBand`, `CrowdingEvidence`, `FamilyAssessment`, `CrowdingAssessment`.
- Produces: `build_crowding_assessment(symbol, market, bars_result, family_results, as_of)`.
- Produces: `render_crowding_assessment(assessment) -> str`.

- [x] **Step 1: Write failing invariants and adversarial fixtures**

```python
def test_missing_family_is_unknown_and_suppresses_band(self) -> None:
    result = build_fixture_assessment(families=("price_volume", "options"))
    self.assertEqual("insufficient_evidence", result.long_crowding.band.value)
    self.assertNotIn(0.0, [item.normalized_value for item in result.missing_evidence])

def test_high_valuation_never_changes_crowding(self) -> None:
    baseline = build_fixture_assessment(valuation=None)
    expensive = build_fixture_assessment(valuation={"pe": 1000})
    self.assertEqual(baseline.long_crowding, expensive.long_crowding)

def test_short_sale_activity_cannot_masquerade_as_short_interest(self) -> None:
    with self.assertRaises(ValueError):
        evidence(metric="short_sale_volume", family="short_interest")

def test_long_short_and_attention_are_separate(self) -> None:
    result = build_full_us_fixture()
    self.assertNotEqual(result.long_crowding.band, result.short_squeeze.band)
    self.assertEqual("insufficient_evidence", result.speculative_attention.band.value)
```

Also cover stale ownership, opposing evidence, own-history cohorts, KR/CN evidence-only, future-date rejection, identity mismatch, family caps, and no-advice rendering.

- [x] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_crowding_intelligence.py -q
```

Expected: FAIL because the domain module is missing.

- [x] **Step 3: Implement immutable evidence and assessment types**

```python
class CrowdingBand(str, Enum):
    INSUFFICIENT = "insufficient_evidence"
    LOW = "low"
    WATCH = "watch"
    ELEVATED = "elevated"
    HIGH = "high"

@dataclass(frozen=True)
class CrowdingEvidence:
    symbol: str
    market: str
    family: str
    metric: str
    direction: EvidenceDirection
    value: float | str
    unit: str
    normalized_value: float | None
    cohort: str
    observed_at: datetime
    fetched_at: datetime
    source_id: str
    access_tier: str
    freshness: str
    quality_flags: tuple[str, ...] = ()
```

Validation rejects naive/ future timestamps, unsupported semantic-family combinations, values outside normalized `[0, 1]`, and identity mismatch.

- [x] **Step 4: Implement deterministic family features**

Price/volume uses at least 120 daily bars and calculates:

- 20-session return percentile against the symbol's rolling 20-session history;
- 20-session realized-volatility percentile;
- latest 20-session average volume versus prior 60-session average.

Ownership uses reported top-holder or institutional percentage, its observation date, and change where available.

Short interest uses outstanding short percentage or aggregated-short ratio plus days-to-cover when available. Short-sale turnover is never admitted as short interest.

Options uses call/put volume and OI, total OI relative to average underlying volume, expiry concentration, and IV. Aggregate OI never becomes signed dealer gamma.

Events produce context and freshness only; they do not add score points.

- [x] **Step 5: Implement coverage and direction-specific bands**

```python
def _eligible(families: tuple[FamilyAssessment, ...], market: str) -> bool:
    names = {family.name for family in families if family.current}
    direct = {"ownership", "short_interest", "options"}
    return (
        market in {"US", "HK"}
        and "price_volume" in names
        and len(names) >= 3
        and bool(names & direct)
    )
```

Use family-capped deterministic thresholds:

- `< 0.35`: `low`
- `< 0.55`: `watch`
- `< 0.75`: `elevated`
- otherwise: `high`

If the gate fails, omit the numeric score and return `insufficient_evidence`. Record contributors, counterevidence, missing families, oldest evidence date, and evidence quality.

- [x] **Step 6: Implement Chinese-first evidence rendering**

The output must include:

- symbol/market and `as_of`;
- three separate assessments;
- evidence quality and family coverage;
- contributors and counterevidence;
- source, metric meaning, observation/fetch date, cohort, and freshness;
- missing/blocked families;
- next known event;
- the exact no-investment-advice boundary from the PRD.

- [x] **Step 7: Run GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_crowding_intelligence.py -q
```

Expected: all invariants and rendering tests pass.

- [x] **Step 8: Commit**

```bash
git add investment_knowledge_mcp/crowding_intelligence.py tests/test_crowding_intelligence.py
git commit -m "feat: add explainable crowding assessment engine"
```

### Task 4: Single-Symbol And Portfolio Orchestration

**Files:**
- Create: `investment_knowledge_mcp/crowding_service.py`
- Create: `tests/test_crowding_service.py`

**Interfaces:**
- Produces: `investigate_symbol_crowding(symbol, market, *, as_of=None, bars_pool=None, evidence_pool=None)`.
- Produces: `investigate_portfolio_crowding(positions, *, as_of=None, max_positions=8, analyzer=None)`.
- Consumes: existing market-bar pool, new crowding pool, and assessment engine.

- [x] **Step 1: Write failing orchestration tests**

```python
def test_single_symbol_requests_each_semantic_capability(self) -> None:
    result = investigate_symbol_crowding("NVDA", "US", as_of=date(2026, 7, 24), bars_pool=bars, evidence_pool=evidence)
    self.assertEqual(
        requested_capabilities,
        [
            SourceCapability.MARKET_BARS,
            SourceCapability.OWNERSHIP_CONCENTRATION,
            SourceCapability.SHORT_INTEREST,
            SourceCapability.OPTIONS_POSITIONING,
            SourceCapability.EVENT_CALENDAR,
        ],
    )
    self.assertEqual("US.NVDA", result.canonical)

def test_portfolio_is_bounded_and_grouped_by_market(self) -> None:
    report = investigate_portfolio_crowding(make_positions(12), max_positions=8, analyzer=fake_analyzer)
    self.assertEqual(8, len(report.assessments))
    self.assertEqual(4, report.omitted_count)
    self.assertEqual(("HK", "US"), tuple(report.by_market))
```

Add tests for malformed positions, duplicate symbols, unsupported markets, partial provider results, deterministic ordering, per-symbol failure isolation, and no false global ranking.

- [x] **Step 2: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_crowding_service.py -q
```

Expected: FAIL because the service module is missing.

- [x] **Step 3: Implement explicit source plans**

```python
def futu_only_plan(capability: SourceCapability) -> SourcePlan:
    return SourcePlan(
        capability,
        preferred_sources=("futu_crowding",),
        allowed_sources=("futu_crowding",),
        fallback_sources=(),
        required=False,
        partial_allowed=True,
    )
```

Market bars use the existing Futu adapter only for this feature. Do not add Yahoo as a crowding fallback.

- [x] **Step 4: Implement bounded orchestration**

The single-symbol path:

- normalizes `SH`/`SZ` to product market `CN` while preserving provider code;
- requests approximately 400 calendar days of bars;
- requests each evidence capability separately through the pool;
- retains all attempted/selected source and failure metadata;
- builds an assessment even when every provider is unavailable.

The portfolio path:

- accepts normalized position dictionaries from current Futu positions;
- deduplicates canonical symbols;
- orders by market value within currency/market-safe groups;
- analyzes at most eight holdings in one request;
- isolates per-symbol failures;
- groups results by market and coverage mode;
- never emits one cross-market leaderboard.

- [x] **Step 5: Implement portfolio rendering**

Render a compact summary per holding with:

- canonical symbol/name;
- market coverage mode;
- long/short/attention bands;
- evidence quality;
- top contributor;
- missing families.

Append omitted-count and no-advice language.

- [x] **Step 6: Run GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_crowding_service.py tests/test_crowding_intelligence.py -q
```

Expected: all tests pass.

- [x] **Step 7: Commit**

```bash
git add investment_knowledge_mcp/crowding_service.py tests/test_crowding_service.py
git commit -m "feat: orchestrate symbol and portfolio crowding reports"
```

### Task 5: Command Router And Workbench Delivery

**Files:**
- Modify: `investment_knowledge_mcp/command_router.py`
- Modify: `investment_knowledge_mcp/command_workbench.py`
- Modify: `tests/test_command_router.py`
- Modify: `tests/test_command_workbench.py`

**Interfaces:**
- Single symbol: `拥挤度 US.NVDA`, `拥挤交易 US.NVDA`, `crowding US.NVDA`.
- Portfolio: `持仓拥挤度`, `拥挤交易`, `portfolio crowding`.
- Workbench actions: `crowding_symbol`, `crowding_portfolio`.

- [x] **Step 1: Write failing router tests**

```python
def test_single_symbol_crowding_is_read_only_query(self) -> None:
    with mock.patch.object(command_router, "investigate_symbol_crowding", return_value=fake_assessment()):
        result = command_router.handle_command("拥挤度 US.NVDA")
    self.assertTrue(result.ok)
    self.assertIn("US.NVDA", result.message)
    self.assertTrue(command_router.is_query_command("拥挤度 US.NVDA"))

def test_portfolio_crowding_reads_positions_and_isolates_provider_failure(self) -> None:
    with (
        mock.patch.object(command_router, "get_futu_positions", return_value=fake_positions()),
        mock.patch.object(command_router, "investigate_portfolio_crowding", return_value=fake_portfolio_report()),
    ):
        result = command_router.handle_command("持仓拥挤度")
    self.assertTrue(result.ok)
    self.assertIn("不构成投资建议", result.message)
```

Also test invalid/unqualified symbols, unsupported market evidence-only behavior, redacted provider failures, and help text.

- [x] **Step 2: Write failing Workbench tests**

```python
def test_crowding_actions_are_registered_read_only(self) -> None:
    actions = {item["id"]: item for item in list_workbench_actions()}
    self.assertEqual("read_only", actions["crowding_symbol"]["safety_level"])
    self.assertEqual("read_only", actions["crowding_portfolio"]["safety_level"])
    self.assertFalse(actions["crowding_symbol"]["confirmation_required"])

def test_exact_crowding_symbol_does_not_require_stock_profile_bootstrap(self) -> None:
    preview = parse_workbench_command("拥挤度 US.NVDA", allow_llm=False)
    self.assertEqual("crowding_symbol", preview["action_id"])
    self.assertEqual("拥挤度 US.NVDA", preview["exact_command"])
```

- [x] **Step 3: Run RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_command_router.py tests/test_command_workbench.py -q
```

Expected: new tests fail because routes and actions are absent.

- [x] **Step 4: Add read-only router handlers**

```python
symbol_match = re.fullmatch(r"(?:拥挤度|拥挤交易|crowding)\s+(.+)", cleaned, re.IGNORECASE)
if symbol_match:
    target = _parse_stock_target(symbol_match.group(1))
    if target is None:
        return CommandResult(False, "拥挤度调查需要市场限定的股票标的，例如：拥挤度 US.NVDA")
    symbol, market = target
    assessment = investigate_symbol_crowding(symbol, market)
    return CommandResult(True, render_crowding_assessment(assessment))
```

Portfolio handler reads current positions and returns safe bounded recovery if Futu positions are unavailable.

- [x] **Step 5: Register Workbench actions and parser rules**

`crowding_symbol` accepts exact market-qualified symbols without requiring a stock profile. Named aliases may still resolve through existing profiles/holdings. `crowding_portfolio` has no fields and is pinned. Both are read-only and require no confirmation.

- [x] **Step 6: Run GREEN and HTTP boundary regression**

Run:

```bash
.venv/bin/python -m pytest tests/test_command_router.py tests/test_command_workbench.py tests/test_command_http.py -q
```

Expected: all tests pass.

- [x] **Step 7: Commit**

```bash
git add investment_knowledge_mcp/command_router.py investment_knowledge_mcp/command_workbench.py tests/test_command_router.py tests/test_command_workbench.py
git commit -m "feat: expose crowded trade intelligence commands"
```

### Task 6: Product Traceability And Acceptance Queue

**Files:**
- Modify: `docs/product/PRD-Crowded-Trade-Intelligence.md`
- Modify: `docs/techplans/crowded-trade-intelligence-feasibility.md`
- Modify: `docs/superpowers/plans/2026-07-24-crowded-trade-intelligence-v1.md`
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`

**Interfaces:**
- Produces: one traceability matrix and one independent acceptance item.

- [x] **Step 1: Add implementation traceability**

Record each PRD acceptance criterion as:

- implemented and test reference;
- intentionally degraded;
- deferred by approved V1 scope;
- blocked on live entitlement/deployment.

Do not claim KR/CN full scoring, social attention, premium sources, or calibration.

- [x] **Step 2: Update delivery state**

Set:

- PRD `ready`;
- technical plan `implemented` only after all implementation tasks pass;
- implementation `local_verified`;
- evidence `test_passed`;
- user acceptance `pending`.

Create an Acceptance Queue row covering:

- US fixture with full evidence;
- HK fixture with full evidence;
- KR/CN evidence-only;
- entitlement failure;
- high-price/no-positioning insufficient evidence;
- real cloud Workbench preview/execution after deployment.

- [x] **Step 3: Run documentation audits**

Run:

```bash
python3 scripts/audit_delivery_state.py --feature "Crowded Trade Intelligence"
python3 scripts/audit_prd_status.py
git diff --check
```

Expected: no missing delivery link; acceptance remains pending until independent cloud testing.

- [x] **Step 4: Commit**

```bash
git add docs/product/PRD-Crowded-Trade-Intelligence.md docs/techplans/crowded-trade-intelligence-feasibility.md docs/superpowers/plans/2026-07-24-crowded-trade-intelligence-v1.md docs/project-management/Feature-Registry.md docs/project-management/Acceptance-Queue.md
git commit -m "docs: record crowded trade V1 implementation evidence"
```

### Task 7: Verification, Review, Push, Deploy, And Acceptance Routing

**Files:**
- Modify only if a verified durable lesson exists: `docs/agent-lessons.md`
- Modify after deployment/acceptance state changes: `docs/project-management/Feature-Registry.md`
- Modify after deployment/acceptance state changes: `docs/project-management/Acceptance-Queue.md`
- Modify after milestones: `docs/project-history.md`

**Interfaces:**
- Produces: immutable branch commit, deployment decision, cloud verification evidence, and independent acceptance routing.

- [x] **Step 1: Run focused verification**

```bash
.venv/bin/python -m pytest \
  tests/test_data_source_contracts.py \
  tests/test_data_source_pool.py \
  tests/test_data_source_market_bars.py \
  tests/test_data_source_crowding.py \
  tests/test_futu_crowding_provider.py \
  tests/test_crowding_intelligence.py \
  tests/test_crowding_service.py \
  tests/test_command_router.py \
  tests/test_command_workbench.py \
  tests/test_command_http.py -q
```

- [x] **Step 2: Run project-level smoke and architecture checks**

```bash
.venv/bin/python scripts/smoke_test.py
.venv/bin/python scripts/audit_architecture_health.py --repo . --format markdown
python3 scripts/audit_delivery_state.py --feature "Crowded Trade Intelligence"
git diff --check
```

- [x] **Step 3: Perform independent code review**

Use `superpowers:requesting-code-review`. Resolve every critical/major finding and rerun affected tests.

- [x] **Step 4: Review the plan for misses**

Compare every task and PRD acceptance criterion with the final diff. Complete straightforward misses immediately and record only genuine entitlement, deployment, or accepted-scope gaps.

- [x] **Step 5: Close role learning**

Check Product, Engineering, Testing, and Coordinator learning against `docs/lesson-capture-protocol.md`. Record only durable cross-task lessons; otherwise report `Role learning: none` with the reason.

- [x] **Step 6: Push the verified branch**

```bash
git push origin codex/crowded-trade-intelligence-discovery
```

- [x] **Step 7: Make the deploy decision**

Classify the exact changed paths. If deployment is required, record Deploy Intent:

- feature: Crowded Trade Intelligence V1;
- exact pushed ref;
- mode: `quick` unless image/dependency/compose files changed;
- affected service: `weekly-review-web`/command surface;
- verification URL: cloud `/command`;
- watch owner: this Feature Coordinator.

Use only the shared deployment path. Do not start local services or ad hoc SSH.

- [x] **Step 8: Verify cloud and route independent acceptance**

Verify:

- `/command` loads;
- catalog exposes both crowding actions;
- a single-symbol preview is read-only and exact;
- execution either returns full evidence when cloud Futu entitlement supports it or an explicit entitlement/insufficient-evidence result;
- portfolio execution is bounded and grouped by market;
- no provider exception, token, path, advice, or false cross-market ranking leaks.

Then update the acceptance row and route the same feature to independent acceptance. The coordinator closure state is `ready_for_user_acceptance` only after independent acceptance passes; otherwise continue through `reject_and_return` or `blocked_with_owner` with an exact owner and condition.

#### Local verification evidence

- Focused suite: `147 passed, 77 subtests passed`.
- Frontend renderer smoke: passed (`weekly=36046`, `command=19355`, `daily=11359` rendered characters).
- Full `scripts/smoke_test.py`: reached the database setup and stopped because the isolated worktree has no permitted PostgreSQL listener at `localhost:55432`; no service was started because this task did not authorize local service startup.
- Delivery audit: only independent acceptance remains.
- PRD audit: no unregistered or not-started PRD.
- Architecture audit: P0 `0`; the Futu provider size is a report-only P1 with a separately recorded extraction slice.
- `git diff --check`: passed.
- Independent re-review: no remaining Critical, Important, or Minor findings.
- Integration: PR `#37`, authoritative `main@61ee36dca794ce7996e84644e0298aecd381aace`.
- Deployment: workflow `30060363722` attempt 2, event `1784858995286`, `targeted_quick`, all five targets healthy for a 30-second stable window, no rollback.
- Coordinator cloud evidence: `/health`, `/command`, both crowding catalog actions, tokenless structured access recovery, exact `US.BRK.B` preview, fail-closed single-symbol execution event `#537`, and read-only portfolio preview passed without advice, secret, raw exception, path, internal URL, or false crowding claim.
- Independent acceptance: degraded mode passed; overall `blocked/major` because live US/HK source cases require an approved source register and deployed entitlements. No redeploy is required for that external blocker.
- Plan review closed the point-in-time publication, signed-option, partial-price/option coverage, provider-session provenance, portfolio coverage display, class-share identity, and approval-register gaps.
- Lessons recorded in `docs/techplans/crowded-trade-intelligence-feasibility.md`: bundled vendor collection requires all bundled capabilities to be approved; unknown publication time cannot support later-fetched historical replay; aggregate option OI remains non-directional; provider bars are the safe session provenance.
