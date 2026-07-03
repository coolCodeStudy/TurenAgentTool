# Stock Valuation Research P0 Technical Plan

Status: implemented for local command/MCP verification on branch `codex/stock-valuation-engineering`.

Linked PRD: [`docs/product/PRD-Stock-Valuation-Research.md`](../product/PRD-Stock-Valuation-Research.md)

## Scope

P0 implements a single-stock valuation research command flow. It does not implement portfolio valuation, batch refresh, provider crawling, dedicated valuation database tables, cloud/web UI, target-price automation, or formal user-insight writes.

The implementation is intentionally artifact-backed before schema expansion. Each command run builds a deterministic valuation packet from existing stock context, local knowledge/source metadata, and parseable valuation facts, then saves a JSON artifact under the command output directory.

## Touched Modules

- `investment_knowledge_mcp/stock_valuation.py`: valuation method library, deterministic fact extraction, calculations, frame scoring, artifact writing, latest-artifact loading, and card rendering.
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

The command remains usable without provider credentials, fresh market data, peer data, model access, or user-confirmed valuation cases. It explicitly reports degraded reasons, including:

- missing latest price or market cap;
- missing enterprise value inputs;
- missing revenue, free cash flow, or net income;
- missing source metadata;
- missing official financial source coverage;
- missing user-confirmed valuation case;
- minimal stock profile needing research import.

When degraded, the output presents frame research scaffolding rather than target-price precision.

## Deployment Impact

No service startup, database migration, external credential, provider integration, or cloud deployment is required for P0 local command verification. If the Coordinator integrates this branch into a cloud-served command surface later, the standard deploy path should be used and acceptance should test the real deployed command surface.

## Verification Plan

- `python3 -m unittest tests.test_stock_valuation`
- `python3 scripts/smoke_test.py`
- `python3 scripts/ikg.py valuation TEST.SMOKE001` or an equivalent local fixture command after smoke data exists.
- `python3 scripts/audit_delivery_state.py --feature "Stock valuation research"`
- `git diff --check`

Current verification on 2026-07-01 SGT:

- Passed `.venv/bin/python -m unittest tests.test_stock_valuation`.
- Passed `.venv/bin/python -m py_compile investment_knowledge_mcp/stock_valuation.py investment_knowledge_mcp/command_router.py investment_knowledge_mcp/command_workbench.py scripts/smoke_test.py`.
- Passed an in-process fixture command check through `command_router.handle_command("valuation US.FIX")`, `handle_command("查看估值 US.FIX")`, and `handle_command("估值方法")`, verifying command routing, artifact writing, latest-artifact retrieval, and card rendering without DB access.
- Passed a Workbench fixture parser check for `估值 FIX US`, `查看估值 FIX US`, and `估值方法`; also observed the existing absent-stock recovery path routes unknown symbols to `bootstrap_stock_profile`.
- Passed `.venv/bin/python scripts/audit_delivery_state.py --feature "Stock valuation research"` with only independent acceptance pending.
- Passed `git diff --check`.
- Blocked `.venv/bin/python scripts/smoke_test.py` and `.venv/bin/python scripts/ikg.py 估值方法` because the configured local database target `127.0.0.1:55432` refused connections. The DB check was retried outside the sandbox and still failed with connection refused, so this is an environment limitation rather than a code-path failure.

P0 intentionally does not verify provider-backed market or financial statement fetches.

## Risks And Follow-Ups

- Regex extraction from knowledge text is a bridge until dedicated financial-fact tables exist.
- Market snapshots, peer multiples, analyst estimates, official filing extraction, and valuation-case confirmation need later provider/schema work.
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
| Do not present direct investment advice or write valuation inference into formal user insights | verified | `stock_valuation.py` | Safety flags and no repository insight-write calls. |
| Valuation method listing | verified | `render_valuation_methods()`, Workbench action `valuation_methods` | Lists five P0 core frames without exposing specialist frames as defaults. |
