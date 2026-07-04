# Stock Valuation Research P0 Technical Plan

Status: implemented through P0.2 local verification on branch `codex/stock-valuation-coordinator-dispatch`; cloud deploy and independent P0.2 acceptance retest are pending.

Linked PRD: [`docs/product/PRD-Stock-Valuation-Research.md`](../product/PRD-Stock-Valuation-Research.md)

## Scope

P0 implements a single-stock valuation research command flow. It does not implement portfolio valuation, batch refresh, provider crawling, dedicated valuation database tables, cloud/web UI, target-price automation, or formal user-insight writes.

The implementation is intentionally artifact-backed before schema expansion. Each command run builds a deterministic valuation packet from existing stock context, local knowledge/source metadata, parseable valuation facts, and P0.1 provider snapshots when available, then saves a JSON artifact under the command output directory.

P0.1 addresses user acceptance feedback from 2026-07-04: a cloud valuation result that only says local financial and market facts are missing is not enough for real valuation review. For US stocks, the command now attempts a provider-backed packet using SEC EDGAR company facts for official financial metrics and Yahoo quote data for a low-cost market snapshot before rendering the final valuation card.

P0.2 addresses the accepted P0.1 follow-up: the command card must render readable investment values, avoid treating negative ratios as normal valuation multiples, classify provider gaps without contradicting available data, and bridge current market cap or enterprise value to the assumptions each selected frame would need.

## Touched Modules

- `investment_knowledge_mcp/stock_valuation.py`: valuation method library, deterministic fact extraction, calculations, display formatting, provider-gap taxonomy, market-implied bridge, frame-fit ranking, artifact writing, latest-artifact loading, and card rendering.
- `investment_knowledge_mcp/valuation_data_provider.py`: P0.1 US provider snapshot fetcher for SEC company facts and Yahoo quote fields, returning structured facts, sources, and provider errors without raising through the command path.
- `investment_knowledge_mcp/command_router.py`: command entrypoints for `valuation SYMBOL MARKET`, `value SYMBOL MARKET`, `估值 SYMBOL MARKET`, `查看估值 SYMBOL MARKET`, and `估值方法`.
- `investment_knowledge_mcp/command_workbench.py`: Workbench registry and deterministic parsing for valuation commands.
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
- `market_implied_bridge`: deterministic bridge lines such as sales anchor, EV/sales anchor, FCF yield or required future FCF margin, and cycle-normalized earnings placeholder when current earnings are negative.
- `selected_frames[].fit_to_current_market_value`: P0.2 fit ranking fields: fit status, why the frame fits or not, implied assumptions, assumptions that must become true, main data gaps, and confidence.
- `degraded_state`: explicit degraded reasons and data gaps.
- `safety`: no direct investment advice and no formal user-insight writes.

## Command/API Entrypoints

- `valuation US.INTC`, `value US.INTC`, `估值 US.INTC`: create and save a new valuation artifact, then return a concise valuation card.
- `查看估值 US.INTC`, `latest valuation US.INTC`: read the latest saved valuation artifact for the stock.
- `估值方法`, `valuation methods`: list the five P0 internal core frames.
- Existing `scripts/ikg.py` and MCP/HTTP command wrappers can use these because they call `command_router.handle_command(...)`.
- Command Workbench can preview/execute the same exact commands through the registry action `stock_valuation`.

## Deterministic Calculations

P0 extracts parseable values from existing stock knowledge text using conservative metric labels such as `revenue=`, `net income=`, `operating cash flow=`, `capex=`, `price=`, `shares outstanding=`, `market cap=`, `EBITDA=`, and Chinese equivalents where practical.

P0.1 also fetches a provider snapshot for US stocks:

- SEC EDGAR companyfacts for revenue, net income, operating cash flow, capex, cash, debt, and shares outstanding when available.
- Yahoo quote for latest price, market cap, shares outstanding, currency, and quote timestamp.
- Each provider fact carries source ID, source type, confidence, timestamp, period end when known, and provider name.
- Provider errors are preserved as degraded reasons rather than surfaced as stack traces.

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
- partial provider gap when Yahoo price, market cap, or shares are available but another Yahoo quote/detail field fails;
- complete missing provider data when no usable category data exists;
- stale or unknown freshness when a market snapshot exists without timestamp/freshness evidence.

When degraded, the output presents frame research scaffolding rather than target-price precision.

## Deployment Impact

No service startup, database migration, external credential, or new provider integration is required for P0.2 local command verification. Because the accepted user surface is the cloud Command Workbench at `http://47.84.190.191:8010/command`, P0.2 still needs a standard cloud deploy of the returned branch or integrated release ref, then independent cloud-IP retest using the private token route.

## Verification Plan

- `python3 -m unittest tests.test_stock_valuation`
- `python3 scripts/smoke_test.py`
- `python3 scripts/ikg.py valuation TEST.SMOKE001` or an equivalent local fixture command after smoke data exists.
- `python3 scripts/audit_delivery_state.py --feature "Stock valuation research"`
- `python3 scripts/audit_agent_flow_health.py --feature "Stock valuation research"`
- `git diff --check`

Current P0.2 verification on 2026-07-04 SGT:

- Passed `python3 -m unittest tests.test_stock_valuation`, including regression coverage for readable values, negative-multiple meaningfulness, provider partial-gap taxonomy, market-implied bridge lines, frame-fit fields, and raw numeric preservation.
- `.venv/bin/python` was unavailable in this isolated workspace, so tests and audits used system `python3` where dependencies permitted.

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
| P0.2 negative/meaningless ratio handling | local_verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Negative PE, FCF yield, and EV/FCF render as `not meaningful` with reasons while raw values remain in artifact diagnostics. |
| P0.2 market-implied bridge | local_verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Includes P/S and EV/sales anchors, required future FCF margin lines for negative FCF, cycle-normalized earnings placeholder for negative earnings, and no target-price precision. |
| P0.2 frame fit ranking | local_verified | `stock_valuation.py`, `tests/test_stock_valuation.py` | Selected frames are ranked by `fit_to_current_market_value` with assumptions, must-become-true items, gaps, and confidence. |
| Do not present direct investment advice or write valuation inference into formal user insights | verified | `stock_valuation.py` | Safety flags and no repository insight-write calls. |
| Valuation method listing | verified | `render_valuation_methods()`, Workbench action `valuation_methods` | Lists five P0 core frames without exposing specialist frames as defaults. |
