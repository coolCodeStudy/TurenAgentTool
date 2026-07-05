# Stock Valuation Research P0 Technical Plan

Status: P0, P0.1, and P0.2 are accepted and must not be reopened. P0.3 non-US valuation provider coverage is implemented locally on branch `codex/stock-valuation-coordinator-dispatch` for the first KR/HK fixtures and needs Coordinator Return Gate review, cloud deploy of an integrated ref, and independent cloud-IP retest before any P0.3 user acceptance request.

Linked PRD: [`docs/product/PRD-Stock-Valuation-Research.md`](../product/PRD-Stock-Valuation-Research.md)

## Scope

P0 implements a single-stock valuation research command flow. It does not implement portfolio valuation, batch refresh, provider crawling, dedicated valuation database tables, cloud/web UI, target-price automation, or formal user-insight writes.

The implementation is intentionally artifact-backed before schema expansion. Each command run builds a deterministic valuation packet from existing stock context, local knowledge/source metadata, parseable valuation facts, and P0.1 provider snapshots when available, then saves a JSON artifact under the command output directory.

P0.1 addresses user acceptance feedback from 2026-07-04: a cloud valuation result that only says local financial and market facts are missing is not enough for real valuation review. For US stocks, the command now attempts a provider-backed packet using SEC EDGAR company facts for official financial metrics and Yahoo quote data for a low-cost market snapshot before rendering the final valuation card.

P0.2 addresses the accepted P0.1 follow-up: the command card must render readable investment values, avoid treating negative ratios as normal valuation multiples, classify provider gaps without contradicting available data, and bridge current market cap or enterprise value to the assumptions each selected frame would need.

P0.2 artifact evidence addresses the 2026-07-04 independent acceptance blocker: visible Workbench behavior passed, but black-box Acceptance Testing could not verify saved artifact raw-value preservation from the allowed cloud surface. The implementation adds a bounded latest-artifact evidence command for a stock target rather than exposing direct filesystem reads. A later P0.2 copy fix keeps card-facing provider gaps on taxonomy copy such as `Market snapshot: partial provider gap` and sanitized degraded-state summaries while preserving raw provider errors only in saved artifact internals when needed for debugging.

P0.3 addresses the 2026-07-05 Product addendum for non-US valuation provider coverage. It is not broad global coverage. The implementation adds fixture-scoped KR/HK ticker/entity mapping, Yahoo/yfinance-style market snapshot attempts, HKD/KRW currency behavior, category-level official/company source attempts, vendor-labeled fallback fundamentals when quote payloads expose operating anchors, and recovery behavior that names missing source families instead of stopping at a US-only provider gap.

## Touched Modules

- `investment_knowledge_mcp/stock_valuation.py`: valuation method library, deterministic fact extraction, calculations, display formatting, provider-gap taxonomy, market-implied bridge, frame-fit ranking, artifact writing, latest-artifact loading, and card rendering.
- `investment_knowledge_mcp/stock_valuation.py`: P0.2 artifact evidence projection for black-box read-back of raw numeric values, display values, calculation meaningfulness, and frame-fit fields without exposing local paths or raw provider errors.
- `investment_knowledge_mcp/stock_valuation.py`: P0.2 provider-gap copy fix so card degraded-state lines summarize provider taxonomy and never render raw HTTP/provider diagnostics.
- `investment_knowledge_mcp/valuation_data_provider.py`: P0.1 US provider snapshot fetcher for SEC company facts and Yahoo quote fields, plus P0.3 fixture-scoped non-US target resolution for `KR.000660` / `000660.KS` and `HK.01888` / `1888.HK`.
- `investment_knowledge_mcp/command_router.py`: command entrypoints for `valuation SYMBOL MARKET`, `value SYMBOL MARKET`, `估值 SYMBOL MARKET`, `查看估值 SYMBOL MARKET`, and `估值方法`, with KR/HK target normalization before repository lookup.
- `investment_knowledge_mcp/command_workbench.py`: Workbench registry and deterministic parsing for valuation commands, with the same KR/HK normalization used by the router.
- `scripts/smoke_test.py`: end-to-end command smoke path using local fixture data.
- `tests/test_stock_valuation.py`: provider-free unit coverage for calculations, degraded behavior, artifact save/load, and method listing.

## Data And Artifact Model

No database migration is introduced in P0.

Saved artifacts live under:

```text
<output_dir>/valuation/<SYMBOL>_<MARKET>_valuation_<timestamp>.json
<output_dir>/valuation/<SYMBOL>_<MARKET>_valuation_latest.json
```

Artifact packet fields:

- `input`: symbol, market, and command text.
- `stock`: stock profile identity and key descriptive fields.
- `facts`: parsed local valuation facts with `knowledge_id`, `source_id`, confidence, confirmation flag, timestamp, and source text snippet.
- `assumptions`: user-confirmed valuation-case state and P0 assumptions.
- `deterministic_calculations`: inspectable formulas and input metrics.
- `internal_frame_scores`: all five core frames with deterministic scores and degradation reasons.
- `selected_frames`: the 1-3 user-facing frames selected from the internal scores.
- `interpretation`: non-advisory frame interpretation.
- `watch_items`: triggers and failure checks per selected frame.
- `source_coverage`: fact count, source count, official-source count, market-snapshot status, peer-data status, and user-confirmed-case state.
- `source_coverage.provider_statuses`: P0.2 provider taxonomy for official financial facts and low-cost market snapshots: `complete_missing`, `partial_provider_gap`, `fallback_used`, or `stale_or_unknown_freshness` where applicable, plus human-readable explanation.
- `target_resolution`: P0.3 mapping evidence for supported non-US fixtures: user-entered command, normalized internal target, company name, provider market ticker, provider, currency, mapping confidence, and mapping source.
- `source_coverage.source_attempts`: P0.3 category-level attempts for provider mapping, Yahoo/yfinance market snapshot, official/company financial source families, and vendor-labeled fallback fundamentals.
- `market_implied_bridge`: deterministic bridge lines such as sales anchor, EV/sales anchor, FCF yield or required future FCF margin, and cycle-normalized earnings placeholder when current earnings are negative.
- `selected_frames[].fit_to_current_market_value`: P0.2 fit ranking fields: fit status, why the frame fits or not, implied assumptions, assumptions that must become true, main data gaps, and confidence.
- `degraded_state`: explicit degraded reasons and data gaps.
- `safety`: no direct investment advice and no formal user-insight writes.

## Command/API Entrypoints

- `valuation US.INTC`, `value US.INTC`, `估值 US.INTC`: create and save a new valuation artifact, then return a concise valuation card.
- `valuation KR.000660`, `valuation 000660 KR`: create and save a P0.3 non-US valuation artifact for SK hynix with normalized target `KR.000660`, provider ticker `000660.KS`, and `KRW` labeling.
- `valuation 建滔积层板 HK`, `valuation HK.01888`, `valuation 1888 HK`: create and save a P0.3 non-US valuation artifact for Kingboard Laminates with normalized target `HK.01888`, provider ticker `1888.HK`, and `HKD` labeling.
- `查看估值 US.INTC`, `latest valuation US.INTC`: read the latest saved valuation artifact for the stock.
- `valuation artifact evidence US.INTC`, `valuation evidence US.INTC`, `估值证据 US.INTC`: read a bounded JSON evidence summary from the latest saved valuation artifact for the stock.
- `估值方法`, `valuation methods`: list the five P0 internal core frames.
- Existing `scripts/ikg.py` and MCP/HTTP command wrappers can use these because they call `command_router.handle_command(...)`.
- Command Workbench can preview/execute the same exact commands through the registry actions `stock_valuation`, `stock_valuation_latest`, `stock_valuation_artifact_evidence`, and `valuation_methods`.

The artifact evidence command is intentionally not a file browser. It accepts only a parsed stock target, resolves the latest artifact through the existing `<output_dir>/valuation/<SYMBOL>_<MARKET>_valuation_latest.json` convention, and has no path or filename field. Its JSON omits the local artifact path, raw provider errors, auth headers, token configuration, stack traces, and arbitrary file contents. It exposes only the P0.2 acceptance fields needed for black-box verification: facts, deterministic calculations, source coverage provider statuses, market-implied bridge lines, frame-fit ranking fields, and safety flags. Saved valuation artifacts may retain raw `source_coverage.provider_errors` for debugging, but rendered cards and bounded evidence read-back must not expose HTTP diagnostics, exception class fragments, URLs, auth-ish text, or local paths.

## Deterministic Calculations

P0 extracts parseable values from existing stock knowledge text using conservative metric labels such as `revenue=`, `net income=`, `operating cash flow=`, `capex=`, `price=`, `shares outstanding=`, `market cap=`, `EBITDA=`, and Chinese equivalents where practical.

P0.1 also fetches a provider snapshot for US stocks:

- SEC EDGAR companyfacts for revenue, net income, operating cash flow, capex, cash, debt, and shares outstanding when available.
- Yahoo quote for latest price, market cap, shares outstanding, currency, and quote timestamp.
- Each provider fact carries source ID, source type, confidence, timestamp, period end when known, and provider name.
- Provider errors are preserved in saved artifact internals when needed for debugging, while card-facing degraded reasons use sanitized provider taxonomy rather than raw HTTP errors, exception fragments, URLs, local paths, or auth-ish text.

P0.3 also fetches provider snapshots for the first supported non-US fixtures:

- `KR.000660` and `000660 KR` normalize to SK hynix, internal target `KR.000660`, provider ticker `000660.KS`, and currency `KRW`.
- `HK.01888`, `1888 HK`, and `建滔积层板 HK` normalize to Kingboard Laminates Holdings Limited, internal target `HK.01888`, provider ticker `1888.HK`, and currency `HKD`.
- Yahoo/yfinance-style quote data is treated as vendor market data for price, market cap, shares, currency, and timestamp.
- Yahoo/yfinance operating anchors such as revenue, net income, operating cash flow, capex, cash, debt, free cash flow, and EBITDA are used only when exposed by the quote payload and are labeled `yahoo_fallback_fundamentals`, not HKEXnews, DART/FSS, FSS, company IR, audited, or official facts.
- Official/company financial extraction is represented as explicit source-attempt status. HK attempts are labeled `HKEXnews and official company reports`; KR attempts are labeled `DART/FSS and company IR`. Structured official extraction is still missing in this P0.3 slice.

P0 computes:

- `free_cash_flow = operating_cash_flow - abs(capex)`
- `net_debt = debt - cash`
- `market_cap = price * shares_outstanding`
- `enterprise_value = market_cap + net_debt`
- `fcf_margin = free_cash_flow / revenue`
- `fcf_yield = free_cash_flow / market_cap`
- `pe = market_cap / net_income`
- `ps = market_cap / revenue`
- `ev_ebitda = enterprise_value / ebitda`
- `ev_fcf = enterprise_value / free_cash_flow`

P0.2 rendering and meaningfulness rules:

- Facts and calculations keep raw numeric values in the artifact and add deterministic `display_value`, `display_kind`, and currency metadata when known.
- Headline currency values render as compact investment values such as `$601.1B`, `$52.6B`, and `-$4.9B`.
- Percentages render as one-decimal values such as `-9.4%`.
- Multiples render as one-decimal values such as `11.4x`.
- Negative operating facts and margins remain visible.
- Negative PE, FCF yield, EV/FCF, and EV/EBITDA are marked `not meaningful` with the reason, while `raw_value` remains available for audit.

## P0.2 Market-Implied Bridge

The bridge is deterministic and intentionally bounded. It does not create target prices, peer-set estimates, or analyst-style forecasts.

When inputs exist, the card and artifact include:

- Market cap / revenue as current P/S sales anchor.
- Enterprise value / revenue as EV/sales anchor.
- FCF yield when FCF is positive.
- Required future FCF margin for illustrative 3%, 5%, and 7% market-cap yield assumptions when current FCF is negative.
- A cycle-normalized earnings placeholder when net income is negative.

Frame fit is ranked against current market value, not only generic relevance:

- `fits`: current facts directly bridge market value to the frame.
- `partial_fit`: the frame can explain current value only with visible expectation or normalization assumptions.
- `does_not_fit`: current facts contradict the frame as a direct market-value explanation, such as negative FCF for current EV/FCF.
- `insufficient_data`: core inputs for the frame are missing.

The selected 1-3 frames come from this fit-ranked list, so a frame may be relevant to the stock but rank lower if it cannot explain current market value with available facts.

LLM/model calls are not used for calculations or frame scoring.

## Frame Scoring

P0 always scores the five internal core frames:

- Free Cash Flow
- Comparable Multiples
- SOTP / Asset Value
- Cyclical
- Growth / Scenario

Scoring combines available deterministic inputs with keyword evidence from the stock profile, knowledge, sector context, and user insights. The card shows only the top 1-3 frames.

## Degraded Behavior

The command remains usable without provider credentials, fresh market data, peer data, model access, or user-confirmed valuation cases. It explicitly reports degraded reasons and P0.2 provider status, including:

- missing latest price or market cap;
- missing enterprise value inputs;
- missing revenue, free cash flow, or net income;
- missing source metadata;
- missing official financial source coverage;
- missing user-confirmed valuation case;
- minimal stock profile needing research import.
- partial provider gap when Yahoo price, market cap, or shares are available but another Yahoo quote/detail field fails, without exposing the raw provider diagnostic in the card;
- complete missing provider data when no usable category data exists;
- stale or unknown freshness when a market snapshot exists without timestamp/freshness evidence.

When degraded, the output presents frame research scaffolding rather than target-price precision.

P0.3 degraded behavior adds category-level recovery:

- If market snapshot exists but official/company financial facts are missing, the card still shows the currency-labeled market snapshot and any vendor-labeled fallback anchors, but marks official/company financials as `complete_missing`.
- If fallback fundamentals are available, deterministic ratios and market-implied bridge lines can be computed provisionally and the card labels them as vendor fallback, not official facts.
- If market snapshot and operating anchors are both missing, the card is a recovery card: it lists attempted source families, missing categories, provider mapping, market snapshot, official/company financials, fallback fundamentals, peer/estimate gaps, and valuation-case status. It must not present `unknown currency` as a usable report for supported fixtures.
- User-facing copy must not include raw HTTP/provider diagnostics, endpoint URLs, exception fragments, auth/header text, stack traces, arbitrary file-read content, or local artifact paths. Raw provider errors may remain only in saved artifact internals.

## P0.3 Acceptance Matrix

| Fixture / form | Expected behavior | Evidence target |
|---|---|---|
| `valuation KR.000660` | Resolves to SK hynix, normalized `KR.000660`, provider ticker `000660.KS`, currency `KRW`, DART/FSS/company-IR source attempt, Yahoo/yfinance market snapshot status, fallback-fundamentals status, no raw diagnostics. | `tests.test_stock_valuation.StockValuationTests.test_p0_3_kr_provider_snapshot_maps_ticker_currency_and_source_categories` |
| `valuation 000660 KR` | Same normalized target and Workbench exact command as `KR.000660`. | `tests.test_stock_valuation.StockValuationTests.test_p0_3_hk_and_kr_command_forms_normalize_in_workbench_and_router` |
| `valuation 建滔积层板 HK` | Resolves to Kingboard Laminates Holdings Limited, normalized `HK.01888`, provider ticker `1888.HK`, currency `HKD`, HKEXnews/company-report source attempt, fallback-fundamentals status, no raw diagnostics. | `tests.test_stock_valuation.StockValuationTests.test_p0_3_hk_alias_maps_to_kingboard_and_evidence_preserves_mapping` |
| `valuation HK.01888` / `valuation 1888 HK` | Normalize to `HK.01888`; Workbench preview and router lookup use the same normalized symbol. | `tests.test_stock_valuation.StockValuationTests.test_p0_3_hk_and_kr_command_forms_normalize_in_workbench_and_router` |
| Artifact evidence read-back | Preserves target mapping, source attempts, provider statuses, raw/display calculation fields, meaningfulness, market-implied bridge, and safety flags without exposing raw provider diagnostics. | `build_valuation_artifact_evidence()` fixture assertions |
| Existing US/Kline behavior | P0/P0.1/P0.2 remain accepted; existing US `US.INTC` tests and Kline preservation checks must continue to pass in focused verification. | `tests.test_stock_valuation`, Kline-focused tests or audit when available |

## Deployment Impact

No service startup, database migration, external credential, or new provider account is required for P0.3 local command verification. Because the accepted user surface is the cloud Command Workbench at `http://47.84.190.191:8010/command`, P0.3 still needs cloud deploy of an integrated release ref and independent cloud-IP retest using the private token route before user acceptance. The Coordinator should decide whether this branch can be deployed directly or must be combined with any newer Kline/Command Workbench lineage to avoid clobbering accepted behavior.

## Verification Plan

- `python3 -m unittest tests.test_stock_valuation`
- `python3 scripts/smoke_test.py`
- `python3 scripts/ikg.py valuation TEST.SMOKE001` or an equivalent local fixture command after smoke data exists.
- `python3 scripts/audit_delivery_state.py --feature "Stock valuation research"`
- `python3 scripts/audit_agent_flow_health.py --feature "Stock valuation research"`
- `git diff --check`

Current P0.3 verification on 2026-07-05 SGT:

- Planned focused checks: `.venv/bin/python -m unittest tests.test_stock_valuation`, targeted Kline preservation tests if present, `.venv/bin/python -m py_compile` for touched modules, `git diff --check`, `python3 scripts/audit_delivery_state.py --feature "Stock valuation research"`, and `python3 scripts/audit_agent_flow_health.py --feature "Stock valuation research"`.

Current P0.2 verification on 2026-07-04 SGT:

- Passed `.venv/bin/python -m unittest tests.test_stock_valuation`, including regression coverage for the new `valuation artifact evidence US.INTC` read-back path, raw/display/meaningfulness/frame-fit evidence fields, Workbench parsing, and path-like input rejection.
- Passed `python3 -m unittest tests.test_stock_valuation`, including regression coverage for readable values, negative-multiple meaningfulness, provider partial-gap taxonomy, market-implied bridge lines, frame-fit fields, and raw numeric preservation.
- The isolated worktree initially had no `.venv`; it was created with `python3 -m venv .venv` and dependencies were installed from `requirements.txt` before the focused verification run.

Current verification on 2026-07-01 SGT:

- Passed `.venv/bin/python -m unittest tests.test_stock_valuation`.
- Passed `.venv/bin/python -m py_compile investment_knowledge_mcp/stock_valuation.py investment_knowledge_mcp/command_router.py investment_knowledge_mcp/command_workbench.py scripts/smoke_test.py`.
- Passed an in-process fixture command check through `command_router.handle_command("valuation US.FIX")`, `handle_command("查看估值 US.FIX")`, and `handle_command("估值方法")`, verifying command routing, artifact writing, latest-artifact retrieval, and card rendering without DB access.
- Passed a Workbench fixture parser check for `估值 FIX US`, `查看估值 FIX US`, and `估值方法`; also observed the existing absent-stock recovery path routes unknown symbols to `bootstrap_stock_profile`.
- Passed `.venv/bin/python scripts/audit_delivery_state.py --feature "Stock valuation research"` with only independent acceptance pending.
- Passed `git diff --check`.
- Blocked `.venv/bin/python scripts/smoke_test.py` and `.venv/bin/python scripts/ikg.py 估值方法` because the configured local database target `127.0.0.1:55432` refused connections. The DB check was retried outside the sandbox and still failed with connection refused, so this is an environment limitation rather than a code-path failure.

P0 originally did not verify provider-backed market or financial statement fetches. P0.1 adds fixture-backed provider tests and still requires cloud-IP retest before user acceptance.

## Risks And Follow-Ups

- Regex extraction from knowledge text is a bridge until dedicated financial-fact tables exist.
- Peer multiples, analyst estimates, dedicated normalized financial-fact tables, async refresh, and valuation-case confirmation need later provider/schema work.
- Workbench execution writes an artifact; the action is safe but not purely read-only.
- P0 artifact paths are local to the command runtime unless a future cloud artifact storage path is added.
- Independent acceptance testing is still required before asking for user acceptance.

## Implementation Traceability

| PRD P0 item / acceptance criterion | Status | Evidence | Notes |
|---|---|---|---|
| Single-stock valuation first, not portfolio/batch | verified | `command_router.py`, `stock_valuation.py`, `tests/test_stock_valuation.py` | Only stock-target commands are registered. |
| Primary command/MCP surface `value` / `valuation` returns concise valuation card | verified | `command_router.py`, `scripts/smoke_test.py` | `valuation`, `value`, and `估值` aliases are implemented. |
| Save valuation artifact | verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Saves timestamped JSON plus latest pointer. |
| Preserve source IDs, timestamps, input fields, calculations, frames, assumptions, coverage, degraded state | verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Packet includes these fields; source IDs are preserved when local knowledge has them. |
| Five internal core frames | verified | `stock_valuation.py` | All five frames are scored. |
| User-facing output shows only 1-3 most relevant frames | verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Selection caps at three frames. |
| Deterministic calculations and frame scoring work without LLM/model calls | verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | No model provider is imported or called. |
| Separate facts, assumptions, deterministic calculations, interpretation, and watch items | verified | `render_valuation_card()` | Card has separate sections. |
| Missing facts, market data, stale peer data, missing model, no user-confirmed case degrade explicitly | verified | `tests/test_stock_valuation.py` | Missing model is not a blocker because no model call is used; peer data is explicitly missing in source coverage. |
| P0.1 US provider-backed valuation packet | accepted | `valuation_data_provider.py`, `stock_valuation.py`, `tests/test_stock_valuation.py`, cloud evidence in Acceptance Queue | SEC EDGAR fixture facts and Yahoo quote fixture facts merge into the artifact and enable deterministic PE/FCF calculations. P0.1 cloud acceptance passed and user accepted it on 2026-07-04. |
| P0.2 readable number formatting | local_verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Card uses compact currency, percent, per-share, and multiple displays; artifact preserves raw numeric values plus display metadata. |
| P0.2 provider-gap taxonomy | local_verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Market snapshot status can report `partial_provider_gap` when Yahoo price/market-cap facts exist but another Yahoo call fails. |
| P0.2 user-facing provider-gap copy sanitization | local_verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Card degraded-state lines now use provider taxonomy summaries and regression coverage verifies raw HTTP diagnostics, exception fragments, URLs, and auth-ish text stay out of rendered cards and bounded evidence read-back while saved artifact internals may retain raw provider errors. Needs combined release deploy and Acceptance retest. |
| P0.2 negative/meaningless ratio handling | local_verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Negative PE, FCF yield, and EV/FCF render as `not meaningful` with reasons while raw values remain in artifact diagnostics. |
| P0.2 market-implied bridge | local_verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Includes P/S and EV/sales anchors, required future FCF margin lines for negative FCF, cycle-normalized earnings placeholder for negative earnings, and no target-price precision. |
| P0.2 frame fit ranking | local_verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Selected frames are ranked by `fit_to_current_market_value` with assumptions, must-become-true items, gaps, and confidence. |
| P0.2 black-box-safe artifact evidence path | needs_retest_after_deploy | `stock_valuation.py`, `command_router.py`, `command_workbench.py`, `tests/test_stock_valuation.py`, cloud evidence in `AT-2026-07-04-002` | `valuation artifact evidence US.INTC` returns bounded JSON evidence from the latest stock valuation artifact and passed the raw/display/meaningfulness/provider/bridge/frame-fit checks on superseding release `801136fa9b3ed023d300effb3fd9fa3770693059`; the same retest failed because the fresh valuation card exposed raw provider error text. The user-facing provider-gap copy fix is local-verified and needs combined release deploy plus Acceptance retest before user acceptance. |
| P0.3 non-US fixture ticker/entity mapping | local_verified | `valuation_data_provider.py`, `command_router.py`, `command_workbench.py`, `tests/test_stock_valuation.py` | `KR.000660` / `000660 KR` map to SK hynix and `000660.KS`; `HK.01888` / `1888 HK` / `建滔积层板 HK` map to Kingboard Laminates and `1888.HK`. |
| P0.3 HKD/KRW currency behavior | local_verified | `stock_valuation.py`, `valuation_data_provider.py`, `tests/test_stock_valuation.py` | Supported fixtures render `KRW` and `HK$` values instead of `unknown currency`. |
| P0.3 official/company source attempts | local_verified | `valuation_data_provider.py`, `stock_valuation.py`, `tests/test_stock_valuation.py` | HK source attempt labels HKEXnews/company reports; KR labels DART/FSS/company IR; fallback Yahoo/yfinance fundamentals are separated from official facts. |
| P0.3 market-implied bridge or recovery behavior | local_verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | When fallback operating anchors and market cap exist, deterministic bridge lines are produced. If inputs are missing, source attempts and missing categories remain visible as recovery evidence. |
| P0.3 no raw diagnostics in user-facing cards/evidence | local_verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Card/evidence omit raw HTTP/provider diagnostics while saved artifact internals may retain raw errors. |
| Do not present direct investment advice or write valuation inference into formal user insights | verified | `stock_valuation.py` | Safety flags and no repository insight-write calls. |
| Valuation method listing | verified | `render_valuation_methods()`, Workbench action `valuation_methods` | Lists five P0 core frames without exposing specialist frames as defaults. |
