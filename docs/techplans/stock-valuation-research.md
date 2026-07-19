# Stock Valuation Research P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task by task, with a task-scoped review after each task and a whole-branch review before release.

**Status:** ready

**Linked PRD:** [`PRD-Stock-Valuation-Research.md`](../product/PRD-Stock-Valuation-Research.md)

**Goal:** Deliver traceable, deterministic, single-stock valuation research through the authenticated Command Workbench for representative US, HK, and KR stocks, with saved versioned artifacts and bounded evidence read-back.

**Architecture:** Recover the proven valuation domain logic from historical ref `origin/codex/release-kline-stock-valuation-p03@acd9856` as evidence, but port it onto current `origin/main@957220a` through new focused modules and narrow registrations. `stock_valuation.py` owns pure packet construction, calculations, scoring, rendering, and artifact safety. `valuation_data_provider.py` owns stock normalization plus official-source and shared-market-data acquisition; it must use current source contracts and existing official-research/source transports rather than restore an old application stack.

**Tech Stack:** Python 3.11, `unittest`, current `investment_knowledge_mcp.data_sources` contracts/pool, existing research official-source provider, shared command router, authenticated Command Workbench/app gateway, JSON artifacts.

## Global Constraints

- Implement the complete bounded P0 in one pass; do not split normal P0 work into later phases.
- P0 is single-stock Command Workbench plus saved/boundedly retrievable artifact only.
- Do not add a database migration, new paid account, new service, standalone valuation page, model dependency, or formal user-insight write.
- Preserve current gateway/access behavior, shared provider policy, frontend shell, scheduler topology, command-api retirement, and deploy-control-plane version gate.
- Never merge the historical release branch wholesale; port only valuation-specific behavior and tests.
- Calculations and frame ranking are deterministic. Optional model interpretation is out of scope for implementation.
- Official-source precedence is SEC EDGAR for US, HKEXnews/company reports for HK, and DART/FSS/company IR for KR. Any fallback retains source family, extraction method, confidence, timestamp/period, currency, and freshness.
- Market snapshots use the current shared-provider path and configured/free fallbacks; source, observation time, currency, freshness, attempts, and sanitized failures are mandatory.
- Peer sets remain candidate/manual-first and never become user-confirmed without explicit user confirmation.
- User-facing cards and bounded evidence omit credentials, auth headers, raw provider diagnostics, exception fragments, endpoint URLs, stack traces, arbitrary file content, and local artifact paths.
- Existing source strings may remain multilingual, but all new code comments, docs, test names, and durable notes are English.

---

## File And Ownership Map

- Create `investment_knowledge_mcp/stock_valuation.py`: pure valuation domain, calculations, five core frames, artifact schema `stock_valuation_packet.v1`, safe persistence/read-back, and card/method rendering.
- Create `investment_knowledge_mcp/valuation_data_provider.py`: target normalization, provider-neutral valuation snapshot assembly, official-source attempts, and market/fundamental source adapters.
- Modify `investment_knowledge_mcp/data_sources/contracts.py`: add only the capabilities required for valuation financial facts and current market snapshots.
- Create `investment_knowledge_mcp/data_sources/valuation.py`: current-pool adapters and source plans for normalized valuation facts/snapshots; provider details stay sanitized by the shared contracts.
- Modify `investment_knowledge_mcp/command_router.py`: valuation create/latest/evidence/method routes, command classification, and repository context loading.
- Modify `investment_knowledge_mcp/command_workbench.py`: four valuation actions and deterministic parsing/normalization without bypassing current access or stock-bootstrap rules.
- Create `tests/test_stock_valuation.py`: pure packet, provider, artifact, route, workbench, safety, and US/HK/KR fixture coverage.
- Modify `tests/test_data_source_contracts.py`: new valuation-capability contract tests.
- Modify `tests/test_command_workbench.py`: current gateway/access regression for valuation preview/execute metadata.
- Update this plan's traceability matrix with final commit/test/deploy/acceptance evidence during implementation and return.

## Locked Interfaces

The implementation may add internal helpers, but these public interfaces and artifact keys are stable for P0:

```python
# investment_knowledge_mcp/valuation_data_provider.py
def normalize_valuation_target(symbol: str, market: str, company_name: str | None = None) -> dict[str, object]: ...
def fetch_valuation_snapshot(symbol: str, market: str, company_name: str | None = None) -> dict[str, object]: ...

# investment_knowledge_mcp/stock_valuation.py
def build_valuation_artifact(
    context: dict[str, object], *, symbol: str, market: str,
    output_dir: Path, command: str,
    provider_snapshot: dict[str, object] | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, object], Path]: ...
def load_latest_valuation_artifact(*, symbol: str, market: str, output_dir: Path) -> dict[str, object] | None: ...
def build_valuation_artifact_evidence(packet: dict[str, object]) -> dict[str, object]: ...
def render_valuation_card(packet: dict[str, object]) -> str: ...
def render_valuation_methods() -> str: ...
```

The saved packet must include these top-level keys:

```json
{
  "schema": "stock_valuation_packet.v1",
  "input": {},
  "stock": {},
  "target_resolution": {},
  "facts": [],
  "assumptions": {},
  "deterministic_calculations": [],
  "internal_frame_scores": [],
  "selected_frames": [],
  "market_implied_bridge": [],
  "interpretation": {},
  "watch_items": [],
  "source_coverage": {},
  "degraded_state": {},
  "safety": {}
}
```

Artifact names are deterministic and stock-scoped:

```text
<output_dir>/valuation/<SYMBOL>_<MARKET>_valuation_<UTC timestamp>.json
<output_dir>/valuation/<SYMBOL>_<MARKET>_valuation_latest.json
```

## Task 1: Domain Engine And Safe Artifact Contract

**Files:** create `investment_knowledge_mcp/stock_valuation.py`; create `tests/test_stock_valuation.py`.

**Produces:** the locked `stock_valuation.py` interfaces; no repository, network, database, or model dependency.

- [ ] Write failing tests for: the eight method definitions (five core plus three specialist-only); 1-3 selected core frames; FCF, net debt, market cap, EV, margins, PE, PS, EV/EBITDA, EV/FCF; negative-ratio meaningfulness; raw/display value preservation; fact-input IDs; `stock_valuation_packet.v1`; timestamped/latest artifact save-load; bounded evidence projection; path-like target rejection; research-aid/no-insight-write safety; and explicit missing-data degradation.
- [ ] Run `.venv/bin/python -m unittest tests.test_stock_valuation -v`; expected result is RED because `investment_knowledge_mcp.stock_valuation` does not exist.
- [ ] Port the historical pure valuation behavior into the locked interfaces. Keep all calculations in small pure helpers and add a deterministic `input_refs` tuple to every calculation. Select at most three core frames after ranking `fit_to_current_market_value`; specialist frames are metadata only unless explicitly triggered and never displace the five-core internal score list.
- [ ] Make `build_valuation_artifact_evidence()` an allow-list projection. It may expose raw/display numeric facts, meaningfulness, source/provider statuses, target mapping, bridge, frame fit, and safety flags; it must never accept a path, read an arbitrary file, or return `artifact_path`, raw provider errors, headers, configuration, or exception text.
- [ ] Run `.venv/bin/python -m unittest tests.test_stock_valuation -v`; expected result is GREEN for all Task 1 tests.
- [ ] Commit Task 1 as `feat: add deterministic stock valuation artifacts`.

## Task 2: Current Shared Provider And Official-Source Attempts

**Files:** modify `investment_knowledge_mcp/data_sources/contracts.py`; create `investment_knowledge_mcp/data_sources/valuation.py`; create `investment_knowledge_mcp/valuation_data_provider.py`; modify `tests/test_data_source_contracts.py`; extend `tests/test_stock_valuation.py`.

**Consumes:** `build_valuation_artifact(..., provider_snapshot=...)` from Task 1 and current `DataRequest`, `SourcePlan`, `DataResult`, `ProviderFailure`, and `DataSourcePool` contracts.

**Produces:** `normalize_valuation_target()` and `fetch_valuation_snapshot()`.

- [ ] Add failing contract tests for `SourceCapability.OFFICIAL_FINANCIAL_FACTS` and `SourceCapability.MARKET_SNAPSHOT`, normalized records with source/period/currency/freshness, fallback attempt order, partial/unavailable states, and redacted failures.
- [ ] Add failing provider tests using injected fixtures for: `US.INTC`/SEC company facts plus shared Yahoo-style market snapshot; `KR.000660` and `000660 KR` -> `000660.KS`, `KRW`, DART/FSS/company-IR attempt; `HK.01888`, `1888 HK`, simplified/traditional Chinese and English Kingboard aliases -> `1888.HK`, `HKD`, HKEXnews/company-report attempt; vendor fallback fundamentals kept distinct from official facts; cache miss triggering attempts before degradation; and no network in tests.
- [ ] Run `.venv/bin/python -m unittest tests.test_data_source_contracts tests.test_stock_valuation -v`; expected result is RED for missing capabilities/adapters.
- [ ] Extend the provider-neutral contract only with the two capabilities. Implement valuation adapters through `DataSourcePool`; reuse the existing official-research transport for US/HK source discovery and add an explicit KR DART/FSS/company-IR attempt adapter. Normalize provider output before the domain engine sees it. Do not restore historical direct provider policy inside the command router.
- [ ] Implement target normalization as a pure allow-listed mapping for the representative fixtures plus generic market-qualified symbols. Fallback fundamentals must use a vendor source type and can never be labeled official, audited, HKEX, SEC, DART, or FSS.
- [ ] Run `.venv/bin/python -m unittest tests.test_data_source_contracts tests.test_data_source_pool tests.test_stock_valuation -v`; expected result is GREEN.
- [ ] Commit Task 2 as `feat: add valuation data source adapters`.

## Task 3: Command Router And Authenticated Workbench

**Files:** modify `investment_knowledge_mcp/command_router.py`; modify `investment_knowledge_mcp/command_workbench.py`; extend `tests/test_stock_valuation.py`; modify `tests/test_command_workbench.py`.

**Consumes:** Tasks 1-2 public interfaces.

**Produces:** actions `stock_valuation`, `stock_valuation_latest`, `stock_valuation_artifact_evidence`, and `valuation_methods`.

- [ ] Add failing tests for `valuation`, `value`, and `估值`; `latest valuation`/`查看估值`; bounded `valuation artifact evidence`/`valuation evidence`/`估值证据`; and `valuation methods`/`估值方法`. Assert preview exact commands, normalized US/HK/KR targets, artifact-write side effect metadata, no confirmation because the only write is a local research artifact, current access recovery, unknown valid symbol bootstrap behavior, and alias consistency.
- [ ] Run `.venv/bin/python -m unittest tests.test_stock_valuation tests.test_command_workbench -v`; expected result is RED because routes/actions are absent.
- [ ] Register the four actions in the current catalog without modifying HTML/access-session code. Parse valuation intent before generic stock bootstrap only when the target is one of the supported name aliases; market-qualified unknown symbols keep the current bounded bootstrap/recovery behavior.
- [ ] Add router handlers that load existing stock context, attempt provider sources, build/save the artifact, return safe cards, load the latest stock-scoped artifact, project bounded evidence, and list methods. Add valuation creation to artifact-write classification but never to candidate/user-insight writes.
- [ ] Run `.venv/bin/python -m unittest tests.test_stock_valuation tests.test_command_workbench tests.test_app_gateway -v`; expected result is GREEN with the existing access/gateway suite unchanged.
- [ ] Commit Task 3 as `feat: expose stock valuation in command workbench`.

## Task 4: Regression, Delivery State, And Release Readiness

**Files:** update `docs/techplans/stock-valuation-research.md`; coordinator later updates `Feature-Registry.md`, `Acceptance-Queue.md`, `Delivery-Queue.md`, and `Coordinator-Context-Packet.md` after accepting the Development return.

- [ ] Run the focused new suite: `.venv/bin/python -m unittest tests.test_stock_valuation tests.test_command_workbench tests.test_app_gateway tests.test_data_source_contracts tests.test_data_source_pool -v`; expected result is all tests GREEN.
- [ ] Run the current-main preservation suite: `.venv/bin/python -m unittest tests.test_command_workbench tests.test_app_gateway tests.test_data_source_pool tests.test_data_source_contracts tests.test_data_source_market_bars tests.test_data_source_market_activity`; baseline before implementation is `Ran 75 tests ... OK`, and the final run must remain GREEN with the added tests.
- [ ] Run the planner's broader gateway/access/frontend/provider suite recorded in the Development report; baseline is `114 tests ... OK`, and the exact final command/output must be returned.
- [ ] Run `.venv/bin/python -m py_compile investment_knowledge_mcp/stock_valuation.py investment_knowledge_mcp/valuation_data_provider.py investment_knowledge_mcp/data_sources/valuation.py investment_knowledge_mcp/command_router.py investment_knowledge_mcp/command_workbench.py`; expected result is exit 0.
- [ ] Run `.venv/bin/python scripts/audit_delivery_state.py --feature "Stock valuation research"`, `.venv/bin/python scripts/audit_agent_flow_health.py --feature "Stock valuation research"`, and `git diff --check`; expected result is no unowned Development/Return-Gate gap and no whitespace error. Acceptance/deploy gaps remain valid until the coordinator performs those gates.
- [ ] Run `.venv/bin/python scripts/classify_deploy_change.py --base-sha origin/main --target-sha HEAD`; use the emitted mode and service set. Because runtime Python modules and the Command Workbench change without dependency/image-layer changes, the expected decision is the classifier's quick/targeted shared workflow, not an ad hoc restart; if the classifier says `full`, follow it.
- [ ] Update every traceability row below to `implemented` or `verified` with exact file/test evidence, commit the documentation/status update, and return a clean branch to the Feature Coordinator for whole-branch review.

## Deploy And Independent Acceptance Contract

After Development and whole-branch review pass, the Feature Coordinator records Deploy Intent with the exact pushed ref, classifier-selected mode, affected `weekly-review-web`/gateway service set, cloud URL `http://47.84.190.191:8010/command`, and this coordinator task as watch owner. Deployment uses only the serialized GitHub Actions/Ops API workflow and the current control-plane version gate.

Coordinator cloud smoke must verify `/command`, the action catalog, authenticated preview/execute for representative US/HK/KR valuation commands, methods, latest read-back, bounded evidence, safe invalid/path-like input, source/freshness labels, and no token/raw-error/path leakage. Then the same Acceptance Queue item moves to `needs_retest` and an independent Quality & Acceptance Lead repeats the black-box user journey. Independent acceptance must not print, store, commit, or summarize token values and must not mark user acceptance accepted.

## Implementation Traceability

| PRD AC | Planned implementation | Planned verification | Initial status |
|---|---|---|---|
| 1 | Four Workbench actions and single normalized target | Command preview/execute tests and cloud catalog smoke | not_started |
| 2 | Five core plus three specialist-only method definitions | Method-library unit test and cloud methods command | not_started |
| 3 | 1-3 selected frames plus versioned saved artifact | Packet/card/save-load tests | not_started |
| 4 | Assumptions, supported market bridge, triggers, failures, confidence, freshness, gaps | Complete/degraded packet fixtures | not_started |
| 5 | Locked `stock_valuation_packet.v1` schema | Exact-key and schema-version tests | not_started |
| 6 | Source/period on facts and `input_refs` on calculations | Traceability assertions | not_started |
| 7 | SEC, HKEX/company, DART/FSS/company source plans | US/HK/KR injected provider fixtures and attempt-order tests | not_started |
| 8 | Shared market snapshot pool, provider/currency/time/freshness, attempts before degradation | Pool fallback/partial/unavailable tests | not_started |
| 9 | Pure calculations and deterministic five-frame scoring | Model-free unit tests | not_started |
| 10 | Separate facts/assumptions/calculations/interpretation/watch layers and provenance | Packet/card section tests | not_started |
| 11 | Candidate/manual peer status only | Missing/stale/candidate peer confidence tests | not_started |
| 12 | Named financial/market/both-missing degraded states | Three degraded-state fixtures | not_started |
| 13 | Stock-scoped allow-list evidence projection | Evidence and path-like rejection/leakage tests plus cloud probe | not_started |
| 14 | Research-aid copy and no direct action instruction | Card safety assertions and cloud scan | not_started |
| 15 | No repository candidate/formal insight write path | Import/call-boundary assertion and code review | not_started |
| 16 | No out-of-scope surface/table/service work | Changed-file review and deploy classifier | not_started |
| 17 | Real deployed Command Workbench independent test | Coordinator smoke plus independent Acceptance Queue pass | not_started |

## Risks And Limits

- Official HK/KR documents are less structured than SEC company facts. A traceable source attempt and explicit missing/extraction status is acceptable; fabricated or silently vendor-labeled official facts are not.
- Local database-backed smoke may be unavailable at `localhost:55432`. Fixture-driven command/router tests remain mandatory, and cloud acceptance remains the real user-surface gate.
- Historical acceptance evidence proves useful behavior but is not evidence for current main. All deployment and independent acceptance evidence must be regenerated against the final current-main ref.
- The feature remains `waiting_for_user_acceptance` after independent acceptance passes; only the Owner can mark user acceptance accepted and close `product_done`.
