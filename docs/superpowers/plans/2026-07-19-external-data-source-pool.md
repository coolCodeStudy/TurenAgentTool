# External Data Source Pool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Weekly Review and Daily Market Brief one capability-based provider, fallback, failure, cache, and provenance contract, beginning with market bars and market activity.

**Architecture:** Add a focused `data_sources` package containing immutable contracts and an in-process pool. Existing Futu, Yahoo, AKShare, and public HTTP functions remain transport implementations behind adapters; features inject a `SourcePlan` and consume normalized `DataResult` values.

**Tech Stack:** Python 3.11, dataclasses, enum, unittest, existing provider functions.

**Implementation status (2026-07-19):** Implemented, independently reviewed, and deployed on authoritative `main@86652e4` by full deploy run `29660355957`. Weekly Review and Daily Market Brief market bars use the shared contracts/pool, and Daily live/historical market activity uses the same result/failure/provenance boundary while preserving provider transports, timeout/cancellation semantics, and feature-layer evidence admission. The final focused market-activity suite passed 122 tests. The production release passed its 60-second stable window, and the architecture harness reports P0 0/P1 7; its remaining signals are report-only module-size findings, not admission for broad refactors. Delivery evidence is closed in `DQ-2026-07-19-001`.

## Global Constraints

- Do not add a network service, Redis, credential, or cloud dependency.
- Do not change provider credentials or log request secrets.
- Migrate one capability at a time and delete its feature-local fallback only after characterization tests pass.
- `partial` and `unavailable` must remain distinguishable from `ok`.
- Provider attempts and selected source must be present in every result.

---

### Task 1: Data Source Contracts

**Files:**
- Create: `investment_knowledge_mcp/data_sources/__init__.py`
- Create: `investment_knowledge_mcp/data_sources/contracts.py`
- Test: `tests/test_data_source_contracts.py`

**Interfaces:**
- Produces: `SourceCapability`, `DataStatus`, `ProviderFailure`, `DataRequest`, `SourcePlan`, `ProviderDescriptor`, and `DataResult`.
- Consumers: pool and feature adapters in later tasks.

- [ ] **Step 1: Write failing contract validation tests**

```python
def test_data_result_requires_selected_source_for_success():
    with self.assertRaises(ValueError):
        DataResult(status=DataStatus.OK, records=({},), selected_source=None)

def test_source_plan_rejects_fallback_outside_allowed_sources():
    with self.assertRaises(ValueError):
        SourcePlan(
            capability=SourceCapability.MARKET_BARS,
            preferred_sources=("futu",),
            allowed_sources=("futu",),
            fallback_sources=("yahoo",),
        )
```

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest tests.test_data_source_contracts -v`

Expected: FAIL because `investment_knowledge_mcp.data_sources.contracts` does not exist.

- [ ] **Step 3: Implement immutable contract types**

```python
class SourceCapability(str, Enum):
    MARKET_BARS = "market_bars"
    MARKET_ACTIVITY = "market_activity"
    OFFICIAL_EVENTS = "official_events"
    NEWS_EVENTS = "news_events"

class DataStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"

@dataclass(frozen=True)
class DataRequest:
    capability: SourceCapability
    market: str
    symbols: tuple[str, ...] = ()
    start: date | None = None
    end: date | None = None
    freshness: str = "default"

@dataclass(frozen=True)
class SourcePlan:
    capability: SourceCapability
    preferred_sources: tuple[str, ...]
    allowed_sources: tuple[str, ...]
    fallback_sources: tuple[str, ...] = ()
    allow_partial: bool = True
```

Implement validation plus `ProviderFailure`, `ProviderDescriptor`, and
`DataResult` fields from the approved design.

- [ ] **Step 4: Verify GREEN**

Run: `python3 -m unittest tests.test_data_source_contracts -v`

Expected: all contract tests pass.

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/data_sources tests/test_data_source_contracts.py
git commit -m "feat: define external data source contracts"
```

### Task 2: Deterministic Pool Execution

**Files:**
- Create: `investment_knowledge_mcp/data_sources/pool.py`
- Test: `tests/test_data_source_pool.py`

**Interfaces:**
- Consumes: contracts from Task 1.
- Produces: `ExternalDataSource.fetch(request) -> DataResult`, `DataSourcePool.register(provider)`, and `DataSourcePool.fetch(request, plan)`.

- [ ] **Step 1: Write failing selection and fallback tests**

```python
def test_pool_uses_preferred_provider_without_fallback():
    result = pool_with(ok_provider("futu"), ok_provider("yahoo")).fetch(request, plan)
    self.assertEqual("futu", result.selected_source)
    self.assertEqual(("futu",), result.attempted_sources)

def test_pool_falls_back_only_for_admitted_transient_failure():
    result = pool_with(timeout_provider("futu"), ok_provider("yahoo")).fetch(request, plan)
    self.assertEqual("yahoo", result.selected_source)
    self.assertEqual(("futu", "yahoo"), result.attempted_sources)

def test_pool_does_not_fallback_for_invalid_request():
    with self.assertRaises(DataSourceRequestError):
        pool_with(invalid_request_provider("futu"), ok_provider("yahoo")).fetch(request, plan)
```

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest tests.test_data_source_pool -v`

Expected: FAIL because the pool is missing.

- [ ] **Step 3: Implement minimal registry, execution, and cache interfaces**

```python
class ExternalDataSource(Protocol):
    descriptor: ProviderDescriptor
    def fetch(self, request: DataRequest) -> DataResult: ...

class DataSourcePool:
    def register(self, provider: ExternalDataSource) -> None: ...
    def fetch(self, request: DataRequest, plan: SourcePlan) -> DataResult: ...
```

Use an injected `ResultCache` protocol with a default bounded in-memory
implementation. Do not add cross-process state.

- [ ] **Step 4: Verify GREEN**

Run: `python3 -m unittest tests.test_data_source_pool -v`

Expected: selection, admitted fallback, no-fallback, partial, and cache tests pass.

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/data_sources/pool.py tests/test_data_source_pool.py
git commit -m "feat: add deterministic data source pool"
```

### Task 3: Market Bar Adapters

**Files:**
- Create: `investment_knowledge_mcp/data_sources/market_bars.py`
- Modify: `investment_knowledge_mcp/market_data_provider.py`
- Test: `tests/test_market_data_provider.py`
- Test: `tests/test_data_source_market_bars.py`

**Interfaces:**
- Consumes: `get_futu_market_bars`, `get_yahoo_market_bars`, and existing `MarketBarSnapshot`.
- Produces: `FutuMarketBarsSource`, `YahooMarketBarsSource`, and `default_market_bar_pool()`.

- [ ] **Step 1: Add failing adapter normalization tests**

Assert that both providers return the same normalized record keys and map
timeouts, unavailable providers, and incomplete symbol coverage to the same
failure/status vocabulary.

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest tests.test_data_source_market_bars -v`

Expected: FAIL because adapters are missing.

- [ ] **Step 3: Implement adapters without changing transports**

```python
class YahooMarketBarsSource:
    descriptor = ProviderDescriptor(
        source_id="yahoo_chart",
        capabilities=frozenset({SourceCapability.MARKET_BARS}),
        markets=frozenset({"CN", "HK", "US"}),
    )

    def fetch(self, request: DataRequest) -> DataResult:
        snapshot = get_yahoo_market_bars(list(request.symbols), request.start.isoformat(), request.end.isoformat())
        return market_bar_snapshot_result(snapshot, request)
```

Implement the Futu adapter with the same mapper. Preserve old provider
functions for compatibility until Tasks 4 and 5 pass.

- [ ] **Step 4: Verify GREEN and existing provider behavior**

Run: `python3 -m unittest tests.test_market_data_provider tests.test_data_source_market_bars -v`

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/data_sources/market_bars.py investment_knowledge_mcp/market_data_provider.py tests
git commit -m "feat: adapt market bar providers to shared pool"
```

### Task 4: Weekly Review Market Bar Migration

**Files:**
- Modify: `investment_knowledge_mcp/weekly_review.py`
- Test: `tests/test_weekly_review_market_context.py`

**Interfaces:**
- Consumes: `DataSourcePool.fetch`, `DataRequest`, and Weekly Review's injected provider seam.
- Produces: existing Weekly Review context with normalized provenance.

- [ ] **Step 1: Add characterization tests for Futu success, Futu timeout/Yahoo fallback, partial symbols, and both unavailable**
- [ ] **Step 2: Verify the new tests pass against old behavior, then change assertions only where the approved normalized provenance is intentionally different**
- [ ] **Step 3: Inject a market-bar `SourcePlan` and translate `DataResult` into the existing context shape**
- [ ] **Step 4: Remove the migrated local fallback loop and run tests**

Run: `python3 -m unittest tests.test_weekly_review_market_context -v`

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/weekly_review.py tests/test_weekly_review_market_context.py
git commit -m "refactor: route weekly market bars through source pool"
```

### Task 5: Daily Market Brief Market Bar Migration

**Files:**
- Modify: `investment_knowledge_mcp/daily_market_brief.py`
- Test: `tests/test_daily_market_brief.py`

**Interfaces:**
- Consumes: market-bar pool and existing `market_bar_loader` test seam.
- Produces: unchanged report context plus normalized source status.

- [ ] **Step 1: Add failing compatibility tests for index success, provider timeout, partial index coverage, and explicit-date behavior**
- [ ] **Step 2: Route live default loading through the pool while preserving injected fixtures**
- [ ] **Step 3: Map `DataResult` to the existing `source_status["indexes"]` contract**
- [ ] **Step 4: Run Daily Brief and historical worker tests**

Run: `python3 -m unittest tests.test_daily_market_brief tests.test_daily_market_history_worker -v`

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/daily_market_brief.py tests/test_daily_market_brief.py
git commit -m "refactor: route daily brief bars through source pool"
```

### Task 6: Market Activity Admission

**Files:**
- Create: `investment_knowledge_mcp/data_sources/market_activity.py`
- Modify: `investment_knowledge_mcp/daily_market_brief.py`
- Modify: `investment_knowledge_mcp/daily_market_history.py`
- Test: `tests/test_data_source_market_activity.py`
- Test: `tests/test_daily_market_brief.py`
- Test: `tests/test_daily_market_history.py`

**Interfaces:**
- Produces: one `MARKET_ACTIVITY` result containing sectors, gainers, and indices with section-level coverage.

- [ ] **Step 1: Characterize AKShare/Eastmoney/public HTTP fallback and historical deadline behavior**
- [ ] **Step 2: Add adapters that preserve provider-specific transport functions but return one result/failure vocabulary**
- [ ] **Step 3: Route live and historical activity through an injected pool without moving product evidence admission into adapters**
- [ ] **Step 4: Remove migrated `_akshare_call` fallback ownership only after parity tests pass**
- [ ] **Step 5: Run full feature verification and commit**

Run: `python3 -m unittest tests.test_data_source_market_activity tests.test_daily_market_brief tests.test_daily_market_history tests.test_daily_market_history_worker -v`

```bash
git add investment_knowledge_mcp/data_sources investment_knowledge_mcp/daily_market_brief.py investment_knowledge_mcp/daily_market_history.py tests
git commit -m "refactor: unify daily market activity sources"
```

### Task 7: Contract And Architecture Verification

**Files:**
- Modify only if admitted: `docs/architecture/architecture-contract.md`
- Modify only if deterministic: `scripts/audit_architecture_health.py`
- Test: `tests/test_architecture_health_audit.py`

- [ ] **Step 1: Run all data-source and product tests**
- [ ] **Step 2: Run `python3 scripts/audit_architecture_health.py --repo . --format markdown`**
- [ ] **Step 3: Keep direct-fallback detection report-only unless fixture pass/fail and main baseline satisfy admission**
- [ ] **Step 4: Run `git diff --check` and commit any admitted contract/harness update separately**
