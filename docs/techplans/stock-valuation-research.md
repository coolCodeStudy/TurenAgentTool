# Stock Valuation Research P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task by task, with a task-scoped review after each task and a whole-branch review before release.

**Status:** implementation_complete_pending_release

**Linked PRD:** [`PRD-Stock-Valuation-Research.md`](../product/PRD-Stock-Valuation-Research.md)

**Goal:** Deliver traceable, deterministic, single-stock valuation research through the authenticated Command Workbench for representative US, HK, and KR stocks, with saved versioned artifacts and bounded evidence read-back.

**Architecture:** Recover the proven valuation domain logic from historical ref `origin/codex/release-kline-stock-valuation-p03@acd9856` as evidence, but port it onto current `origin/main@957220a` through new focused modules and narrow registrations. Semantic reconciliation against the latest `origin/main@c58c41a` found only unrelated frontend/financial-workspace documentation changes and no stock-valuation runtime overlap. `stock_valuation.py` owns pure packet construction, calculations, scoring, rendering, and artifact safety. `valuation_data_provider.py` owns stock normalization plus official-source and shared-market-data acquisition; it must use current source contracts and existing official-research/source transports rather than restore an old application stack.

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

- [x] Write failing tests for: the eight method definitions (five core plus three specialist-only); 1-3 selected core frames; FCF, net debt, market cap, EV, margins, PE, PS, EV/EBITDA, EV/FCF; negative-ratio meaningfulness; raw/display value preservation; fact-input IDs; `stock_valuation_packet.v1`; timestamped/latest artifact save-load; bounded evidence projection; path-like target rejection; research-aid/no-insight-write safety; and explicit missing-data degradation. Final coverage is in `tests/test_stock_valuation.py` through `dd88c2e`.
- [x] Run `.venv/bin/python -m unittest tests.test_stock_valuation -v`; historical RED was retained because `investment_knowledge_mcp.stock_valuation` did not yet exist.
- [x] Port the historical pure valuation behavior into the locked interfaces. `investment_knowledge_mcp/stock_valuation.py` keeps the deterministic calculation/provenance and core-frame constraints; final Task 1 correction is `dd88c2e`.
- [x] Make `build_valuation_artifact_evidence()` an allow-list projection. It is covered by typed-projection and leakage tests in `tests/test_stock_valuation.py` through `dd88c2e`.
- [x] Run `.venv/bin/python -m unittest tests.test_stock_valuation -v`; the whole-branch fix wave passed 71 valuation tests, including complete/stale/missing semantic states, confirmation, provider budget, official-family, exact-name, and atomic-persistence regressions.
- [x] Commit Task 1 as `feat: add deterministic stock valuation artifacts` (`8ae5b91`), with accepted corrections through `dd88c2e`.

## Task 2: Current Shared Provider And Official-Source Attempts

**Files:** modify `investment_knowledge_mcp/data_sources/contracts.py`; create `investment_knowledge_mcp/data_sources/valuation.py`; create `investment_knowledge_mcp/valuation_data_provider.py`; modify `tests/test_data_source_contracts.py`; extend `tests/test_stock_valuation.py`.

**Consumes:** `build_valuation_artifact(..., provider_snapshot=...)` from Task 1 and current `DataRequest`, `SourcePlan`, `DataResult`, `ProviderFailure`, and `DataSourcePool` contracts.

**Produces:** `normalize_valuation_target()` and `fetch_valuation_snapshot()`.

- [x] Add failing contract tests for `SourceCapability.OFFICIAL_FINANCIAL_FACTS` and `SourceCapability.MARKET_SNAPSHOT`, normalized records with source/period/currency/freshness, fallback attempt order, partial/unavailable states, and redacted failures. Final coverage is in `tests/test_data_source_contracts.py` and `tests/test_stock_valuation.py`.
- [x] Add failing provider tests using injected fixtures for: `US.INTC`/SEC company facts plus shared Yahoo-style market snapshot; `KR.000660` and `000660 KR` -> `000660.KS`, `KRW`, DART/FSS/company-IR attempt; `HK.01888`, `1888 HK`, simplified/traditional Chinese and English Kingboard aliases -> `1888.HK`, `HKD`, HKEXnews/company-report attempt; vendor fallback fundamentals kept distinct from official facts; cache miss triggering attempts before degradation; and no network in tests. The final focused suite passed 130 tests.
- [x] Run `.venv/bin/python -m unittest tests.test_data_source_contracts tests.test_stock_valuation -v`; historical RED was retained for the intentionally missing capabilities/adapters.
- [x] Extend the provider-neutral contract only with the two capabilities. `investment_knowledge_mcp/data_sources/contracts.py`, `investment_knowledge_mcp/data_sources/valuation.py`, and `investment_knowledge_mcp/valuation_data_provider.py` implement current-pool adapters through `a653725`.
- [x] Implement target normalization as a pure allow-listed mapping for the representative fixtures plus generic market-qualified symbols. Final provider normalization and source-family protections are covered in `tests/test_stock_valuation.py` through `a653725`.
- [x] Run `.venv/bin/python -m unittest tests.test_data_source_contracts tests.test_data_source_pool tests.test_stock_valuation -v`; the final required focused gate below includes these modules and passed 144/144.
- [x] Commit Task 2 as `feat: add valuation data source adapters` (`310b572`), with accepted source-truthfulness correction `a653725`.

## Task 3: Command Router And Authenticated Workbench

**Files:** modify `investment_knowledge_mcp/command_router.py`; modify `investment_knowledge_mcp/command_workbench.py`; extend `tests/test_stock_valuation.py`; modify `tests/test_command_workbench.py`.

**Consumes:** Tasks 1-2 public interfaces.

**Produces:** actions `stock_valuation`, `stock_valuation_latest`, `stock_valuation_artifact_evidence`, and `valuation_methods`.

- [x] Add failing tests for `valuation`, `value`, and `估值`; `latest valuation`/`查看估值`; bounded `valuation artifact evidence`/`valuation evidence`/`估值证据`; and `valuation methods`/`估值方法`. Exact command, target, side-effect, confirmation, recovery, bootstrap, and alias coverage is in `tests/test_stock_valuation.py` and `tests/test_command_workbench.py`.
- [x] Run `.venv/bin/python -m unittest tests.test_stock_valuation tests.test_command_workbench -v`; historical RED was retained because routes/actions were absent.
- [x] Register the four actions in the current catalog without modifying HTML/access-session code. `investment_knowledge_mcp/command_workbench.py` implements the bounded alias parsing through `4166469`.
- [x] Add router handlers that load existing stock context, attempt provider sources, build/save the artifact, return safe cards, load the latest stock-scoped artifact, project bounded evidence, and list methods. `investment_knowledge_mcp/command_router.py` and the focused tests verify only local-artifact writes and no candidate/user-insight writes through `4166469`.
- [x] Run `.venv/bin/python -m unittest tests.test_stock_valuation tests.test_command_workbench tests.test_app_gateway -v`; the final required focused gate below includes these modules and passed 144/144.
- [x] Commit Task 3 as `feat: expose stock valuation in command workbench` (`d0e1cb1`), with accepted alias trust-boundary correction `4166469`.

## Task 4: Regression, Delivery State, And Release Readiness

**Files:** update `docs/techplans/stock-valuation-research.md`; coordinator later updates `Feature-Registry.md`, `Acceptance-Queue.md`, `Delivery-Queue.md`, and `Coordinator-Context-Packet.md` after accepting the Development return.

- [x] Run the focused new suite: `.venv/bin/python -m unittest tests.test_stock_valuation tests.test_command_workbench tests.test_app_gateway tests.test_data_source_contracts tests.test_data_source_pool -v`; final gate exited 0, `Ran 161 tests`, `OK`.
- [x] Run the current-main preservation suite: `.venv/bin/python -m unittest tests.test_command_workbench tests.test_app_gateway tests.test_data_source_pool tests.test_data_source_contracts tests.test_data_source_market_bars tests.test_data_source_market_activity`; final gate exited 0, `Ran 89 tests`, `OK`.
- [x] Run the planner's broader gateway/access/frontend/provider suite: `.venv/bin/python -m unittest tests.test_command_workbench tests.test_app_gateway tests.test_command_http tests.test_web_experience tests.test_data_source_pool tests.test_data_source_contracts tests.test_data_source_market_bars tests.test_data_source_market_activity -v`; final gate exited 0, `Ran 129 tests`, `OK`.
- [x] Run `.venv/bin/python -m py_compile investment_knowledge_mcp/stock_valuation.py investment_knowledge_mcp/valuation_data_provider.py investment_knowledge_mcp/data_sources/valuation.py investment_knowledge_mcp/command_router.py investment_knowledge_mcp/command_workbench.py`; exit 0.
- [x] Run `.venv/bin/python scripts/audit_delivery_state.py --feature "Stock valuation research"`, `.venv/bin/python scripts/audit_agent_flow_health.py --feature "Stock valuation research"`, and `git diff --check`; no whitespace error. The delivery audit has no unowned Development/Return-Gate gap: it names this completed Task 4 under `DQ-2026-07-19-004`; its coordinator-owned deploy and independent-acceptance gaps remain pending. Flow-health emitted only the unrelated seven-cell `DQ-2026-07-04-020` warning.
- [x] Run `.venv/bin/python scripts/classify_deploy_change.py --base-sha origin/main --target-sha HEAD`; selected deployment mode `targeted_quick`, workflow-compatible mode `quick`, targets `dingtalk-api`, `dingtalk-stream-bot`, `mcp`, `scheduler-host`, and `weekly-review-web`. This is a release input only; no deployment was started.
- [x] Update every traceability row below to `implemented` or `verified` with exact file/test evidence, commit the documentation/status update, and return a clean branch to the Feature Coordinator for whole-branch review.

## Deploy And Independent Acceptance Contract

After Development and whole-branch review pass, the Feature Coordinator records Deploy Intent with the immutable deployed ref (`main@48930c1e56ea377e7fb65fb44279e172e36b054d`, including runtime integration parent `46639d2` and Frontend runtime ref `017d91c6cc8ad613ab07a2b9093bb7b32850abba`), GitHub Actions run `29710198994`, classifier-selected `targeted_quick`/`quick` mode, affected `weekly-review-web`/gateway service set, cloud URL `http://47.84.190.191:8010/command`, and this coordinator task as watch owner. Deployment uses only the serialized GitHub Actions/Ops API workflow and the current control-plane version gate; independent acceptance remains the next gate.

Coordinator cloud smoke must verify `/command`, the action catalog, authenticated preview/execute for representative US/HK/KR valuation commands, methods, latest read-back, bounded evidence, safe invalid/path-like input, source/freshness labels, and no token/raw-error/path leakage. Then the same Acceptance Queue item moves to `needs_retest` and an independent Quality & Acceptance Lead repeats the black-box user journey. Independent acceptance must not print, store, commit, or summarize token values and must not mark user acceptance accepted.

## Implementation Traceability

| PRD AC | Planned implementation | Planned verification | Status and exact local evidence |
|---|---|---|---|
| 1 | Four Workbench actions and single normalized target | Command preview/execute tests and cloud catalog smoke | **verified** — `investment_knowledge_mcp/command_workbench.py`, `investment_knowledge_mcp/command_router.py`; `StockValuationWorkbenchTests` and `StockValuationCommandRouterTests` in `tests/test_command_workbench.py`/`tests/test_stock_valuation.py`; commits `d0e1cb1`, `4166469`; whole-branch focused suite 144/144. |
| 2 | Five core plus three specialist-only method definitions | Method-library unit test and cloud methods command | **verified** — `test_public_interfaces_and_eight_method_definitions` asserts all eight exact Product names, including `Residual Income / ROE-PB`; whole-branch focused suite 144/144. |
| 3 | 1-3 selected frames plus versioned saved artifact | Packet/card/save-load tests | **verified** — final `61e950f` cleanup catches `BaseException`, closes the locally owned descriptor, and removes the hidden temp on interruption; the new interruption regression and full valuation suite pass. |
| 4 | Assumptions, supported market bridge, triggers, failures, confidence, freshness, gaps | Complete/degraded packet fixtures | **verified** — complete, stale, financial-missing, market-missing, and both-missing semantic fixtures assert as-of/freshness, per-frame assumptions/triggers/failures/confidence/provenance, bridge rendering, and recovery semantics; whole-branch focused suite 144/144. |
| 5 | Locked `stock_valuation_packet.v1` schema | Exact-key and schema-version tests | **verified** — `investment_knowledge_mcp/stock_valuation.py`; `test_builds_deterministic_packet_with_all_metrics_and_fact_refs` and loader canonicalization tests; commits `8ae5b91..dd88c2e`; 130/130. |
| 6 | Source/period on facts and `input_refs` on calculations | Traceability assertions | **verified** — `investment_knowledge_mcp/stock_valuation.py`, `investment_knowledge_mcp/data_sources/valuation.py`; `test_bridge_lines_and_frame_scores_have_bounded_input_provenance`, `test_derived_calculations_flatten_all_upstream_fact_provenance`, `test_fact_and_source_ids_are_stable_opaque_and_all_refs_resolve`; commits `dd88c2e`, `a653725`; 130/130. |
| 7 | SEC, HKEX/company, DART/FSS/company source plans | US/HK/KR injected provider fixtures and attempt-order tests | **verified** — `investment_knowledge_mcp/valuation_data_provider.py` collects one typed official-source outcome and fans it out once per request; `test_official_collection_outcomes_distinguish_every_bounded_terminal_state`, `test_hk_typed_timeout_outcome_is_collected_once_and_fanned_out_safely`, and the existing one-collection tests pass in the fresh 85-test valuation suite. |
| 8 | Shared market snapshot pool, provider/currency/time/freshness, attempts before degradation | Pool fallback/partial/unavailable tests | **verified** — timeout now remains `timeout`, complete-empty discovery remains `complete_missing`, and saturation/submission/provider/invalid results become safe retryable failures without diagnostics; `test_official_attempt_loader_projects_typed_outcomes_truthfully` passes, as do the fresh 88-test provider preservation and 128-test broader gateway/provider gates. |
| 9 | Pure calculations and deterministic five-frame scoring | Model-free unit tests | **verified** — `investment_knowledge_mcp/stock_valuation.py`; calculation, meaningfulness, fit, and score tests in `tests/test_stock_valuation.py`, including `test_scoring_reads_only_declared_stock_fields_and_cites_exact_field`; commits `8ae5b91..dd88c2e`; 130/130. |
| 10 | Separate facts/assumptions/calculations/interpretation/watch layers and provenance | Packet/card section tests | **verified** — `render_valuation_card()` exposes distinct bounded `Facts:` and `Calculations:` sections with canonical source/period and input references while preserving bridge, relevant frames, assumptions, interpretation, watch items, freshness, and source coverage; `test_card_exposes_separate_safe_fact_and_calculation_layers` passes. |
| 11 | Candidate/manual peer status only | Missing/stale/candidate peer confidence tests | **verified** — durable user confirmation now fails closed because P0 has no trusted verifier; peer evidence is canonical candidate-only metadata, with missing/stale gaps capping Comparable Multiples while unrelated frames remain useful. Confirmation-tamper and four peer-evidence adversarial tests pass in the fresh 85-test valuation suite. |
| 12 | Named financial/market/both-missing degraded states | Three degraded-state fixtures | **verified** — existing degraded-state matrices remain green, and typed official outcomes now distinguish complete-empty discovery, timeout, saturation, submission failure, provider failure, and invalid results with truthful safe recovery copy; the fresh focused gate passed 158/158. |
| 13 | Stock-scoped allow-list evidence projection | Evidence and path-like rejection/leakage tests plus cloud probe | **verified** — direct projections and latest-artifact loading enforce byte, depth, node, container, scalar, and recursion bounds before recursive copying/validation, and tampered confirmation cannot survive the public projection. Deep/malformed/oversized/router containment tests pass in the fresh 85-test valuation suite. |
| 14 | Research-aid copy and no direct action instruction | Card safety assertions and cloud scan | **verified** — `investment_knowledge_mcp/stock_valuation.py`; `test_card_and_evidence_share_the_same_safe_public_projection` and research-write classifier coverage; commits `dd88c2e`, `4166469`; 130/130. Cloud scan remains release work. |
| 15 | No repository candidate/formal insight write path | Import/call-boundary assertion and code review | **verified** — `investment_knowledge_mcp/command_router.py`; `test_creation_aliases_write_only_a_local_research_artifact`, `test_valuation_write_classifier_matches_only_executable_creation_forms`; commit `4166469`; 130/130. |
| 16 | No out-of-scope surface/table/service work | Changed-file review and deploy classifier | **verified** — valuation implementation commits `8ae5b91..dd88c2e`, `310b572..a653725`, and `d0e1cb1..4166469` are limited to the planned modules/tests; `git diff --check` passed; classifier selected `targeted_quick`/`quick` with five existing service targets. |
| 17 | Real deployed Command Workbench independent test | Coordinator smoke plus independent Acceptance Queue pass | **implemented_pending_release** — router/Workbench implementation and in-process tests are complete through `61e950f`; focused 161/161 and broader 129/129 pass. Serialized deploy, coordinator cloud smoke, and the independent Acceptance Queue result remain pending. |

## Risks And Limits

- Official HK/KR documents are less structured than SEC company facts. A traceable source attempt and explicit missing/extraction status is acceptable; fabricated or silently vendor-labeled official facts are not.
- Local database-backed smoke may be unavailable at `localhost:55432`. Fixture-driven command/router tests remain mandatory, and cloud acceptance remains the real user-surface gate.
- Historical acceptance evidence proves useful behavior but is not evidence for current main. All deployment and independent acceptance evidence must be regenerated against the final current-main ref.
- The feature remains `waiting_for_user_acceptance` after independent acceptance passes; only the Owner can mark user acceptance accepted and close `product_done`.
- A provider call that exceeds the six-second interactive ceiling may continue inside the globally bounded two-worker executor until its own two-second transport operations unwind; additional saturated calls fail closed without spawning more workers or leaking diagnostics.
- If interruption occurs after the timestamped atomic replace but before the latest replace, the new timestamped artifact remains valid while `latest` remains the previous valid packet; a retry reconciles latest without exposing a partial file.
- Release remains coordinator-owned: use the recorded `targeted_quick`/workflow `quick` decision and its five service targets only after whole-branch review, push, serialized deploy intent, cloud smoke, and independent acceptance routing. No Task 4 deployment was performed.
