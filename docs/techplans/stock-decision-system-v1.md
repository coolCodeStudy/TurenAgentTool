# Tech Plan: Stock Decision System V1

## Source PRD

This plan implements `docs/product/PRD-Stock-Decision-System.md`.

The core product distinction is:

- Stock Evidence Card: compact summary of what the graph knows about a stock.
- Decision Ticket: portfolio-aware decision-support output with scores, gates, position boundaries, and review triggers.

V1 is complete only when `决策 SYMBOL MARKET` can produce and save a traceable Decision Ticket with:

- Composite score and component scores.
- Recommendation category.
- Confidence and freshness status.
- Suggested initial position range and max position cap.
- Reasons, veto conditions, entry conditions, add conditions, reduce or exit review conditions, and next review trigger.
- Evidence summary linked back to graph objects, source records, observations, inferences, or user-confirmed preferences.
- Clear separation of facts, time-sensitive observations, model inferences, user preferences, candidate insights, and decision snapshots.

## Current System Baseline

Existing usable pieces:

- `repository.get_stock_context(symbol, market)` builds graph context for stock, sector, user insights, candidate insights, and sources.
- `display.build_stock_decision_card(...)` currently builds the compact first-screen card. Product-facing terminology should rename this to Stock Evidence Card while keeping function names stable until a safe rename.
- `research_jobs` stores research pipeline state, artifacts, source discovery, and audit status.
- `account_snapshots`, `trade_records`, `futu_provider`, and `portfolio_analysis` provide portfolio and holdings inputs.
- `candidate_insights` and `user_insights` already separate pending model/user lessons from confirmed memory.
- `analysis_provider.py` already has the OpenAI response pattern and conservative prompts for analysis tasks.

Important implementation constraint:

- Do not turn the Decision System into another long stock analysis command. The decision workflow must run the stock analysis workflow first, then add user constraints, portfolio exposure, observations, freshness planning, deterministic scoring, gates, and model synthesis.

## Target Architecture

```text
command_router / MCP tool
  -> decision_engine.decide_stock(symbol, market, mode)
      -> load stock graph context
      -> build Stock Evidence Card
      -> load user constraint profile
      -> load portfolio exposure pack
      -> load latest observations and regime packs
      -> run freshness planner
      -> refresh only required packs when allowed by mode
      -> build compact decision context pack
      -> deterministic pre-scoring
      -> deterministic gates and caps
      -> model synthesis on compact pack
      -> validate model output against schema and gates
      -> save immutable stock_decisions snapshot
      -> propose candidate insights when appropriate
      -> render default or detailed Decision Ticket
```

## Module Design

### `investment_knowledge_mcp/decision_engine.py`

Owns orchestration.

Public functions:

- `decide_stock(symbol: str, market: str, mode: str = "focused", save: bool = True) -> dict`
- `get_decision_detail(decision_id: int) -> dict | None`
- `list_decision_history(symbol: str, market: str, limit: int = 20) -> list[dict]`
- `refresh_decision_data(symbol: str, market: str, mode: str = "focused") -> dict`

Responsibilities:

- Resolve stock.
- Call stock evidence workflow first.
- Call context builder.
- Call scoring and gates.
- Call synthesis provider when enabled.
- Persist final snapshot.
- Return a normalized Decision Ticket dict.

### `investment_knowledge_mcp/decision_context.py`

Builds structured packs, not raw database dumps.

Public functions:

- `build_decision_context_pack(symbol: str, market: str, mode: str) -> dict`
- `build_portfolio_exposure_pack(...) -> dict`
- `build_user_constraint_pack(...) -> dict`
- `build_observation_packs(...) -> dict`
- `build_freshness_report(...) -> dict`
- `context_hash(context_pack: dict) -> str`

Output shape:

```json
{
  "stock": {},
  "user_constraints": {},
  "portfolio_exposure": {},
  "stock_card": {},
  "valuation_pack": {},
  "technical_pack": {},
  "chip_event_pack": {},
  "sector_pack": {},
  "market_pack": {},
  "freshness_report": {},
  "open_questions": [],
  "evidence_index": []
}
```

### `investment_knowledge_mcp/decision_scoring.py`

Pure deterministic scoring and gating.

Public functions:

- `pre_score_decision(context_pack: dict) -> dict`
- `apply_decision_gates(context_pack: dict, score: dict) -> dict`
- `derive_position_range(context_pack: dict, score: dict, gates: dict) -> dict`

Default weights:

| Component | Weight |
| --- | ---: |
| Portfolio fit | 20 |
| Fundamental quality | 18 |
| Valuation setup | 16 |
| Sector regime | 14 |
| Market regime and leadership fit | 10 |
| Technical setup | 9 |
| Chip and event structure | 8 |
| Evidence quality and freshness | 5 |

Gate examples:

- Missing critical user constraints caps confidence and blocks high-conviction output.
- Stale portfolio or technical data caps recommendation to `watch` or `wait`.
- Theme or market concentration caps max position.
- Major unlock or binary event caps recommendation unless the risk is explicitly accepted.
- Unsupported valuation frame caps valuation score.
- Technical breakdown blocks immediate `starter` or `normal position`.
- User-confirmed constraints override model synthesis.

### `investment_knowledge_mcp/decision_synthesis.py`

Calls the model only after deterministic context and gates are ready.

Public functions:

- `generate_decision_synthesis(context_pack: dict, pre_score: dict, gates: dict) -> dict | None`
- `build_decision_synthesis_prompt(...) -> str`
- `validate_decision_synthesis(value: dict) -> dict`

Rules:

- The prompt receives compact packs only.
- The prompt must not include raw filings or raw database dumps.
- The model cannot increase recommendation strength beyond deterministic gates.
- The model must label facts, observations, inferences, user-confirmed preferences, and open questions.
- If no API key or model synthesis is disabled, return a deterministic fallback ticket.

### `investment_knowledge_mcp/decision_repository.py`

Repository layer for new decision objects.

Public functions:

- `upsert_default_constraint_profile(...) -> dict`
- `get_active_constraint_profile() -> dict | None`
- `create_constraint_profile_change(...) -> dict`
- `confirm_constraint_profile_change(change_id: int) -> dict`
- `add_stock_observation(...) -> dict`
- `list_latest_observations(stock_id: int, types: list[str]) -> list[dict]`
- `add_inference_item(...) -> dict`
- `save_stock_decision(ticket: dict) -> dict`
- `get_stock_decision(decision_id: int) -> dict | None`
- `list_stock_decisions(symbol: str, market: str, limit: int) -> list[dict]`
- `add_decision_evidence_links(decision_id: int, links: list[dict]) -> list[dict]`

### `investment_knowledge_mcp/decision_rendering.py`

User-facing rendering.

Public functions:

- `render_decision_ticket(ticket: dict) -> str`
- `render_decision_detail(ticket: dict) -> str`
- `render_decision_history(decisions: list[dict]) -> str`
- `render_decision_profile(profile: dict) -> str`

Default output sections:

- Recommendation, composite score, confidence.
- Suggested position range and max cap.
- Component score table.
- Why.
- Veto conditions.
- Entry conditions.
- Add conditions.
- Reduce or exit review conditions.
- Next review trigger.
- Evidence and freshness summary.

## Persistence Plan

### `user_constraint_profiles`

Stores active machine-readable decision constraints.

Recommended columns:

- `id BIGSERIAL PRIMARY KEY`
- `profile_name TEXT NOT NULL DEFAULT 'default'`
- `status TEXT NOT NULL DEFAULT 'active'`
- `max_single_stock_position_pct NUMERIC(6, 3)`
- `preferred_starter_position_pct NUMERIC(6, 3)`
- `cash_reserve_min_pct NUMERIC(6, 3)`
- `max_positions_target INTEGER`
- `max_positions_hard_cap INTEGER`
- `daily_monitoring_minutes INTEGER`
- `weekly_research_hours NUMERIC(6, 2)`
- `max_theme_exposure_pct NUMERIC(6, 3)`
- `max_market_exposure_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `volatility_tolerance TEXT`
- `drawdown_tolerance TEXT`
- `missed_opportunity_vs_drawdown_bias TEXT`
- `event_stock_allowed BOOLEAN`
- `source_insight_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `confirmed_by_user BOOLEAN NOT NULL DEFAULT false`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

V1 should seed a conservative default profile when none exists, but missing user-confirmed constraints must be shown in the Decision Ticket and must cap confidence.

### `user_constraint_profile_changes`

Stores pending and confirmed structured preference changes.

Reason:

- The PRD requires preference changes to keep history because they directly affect scoring and position sizing.

Recommended columns:

- `id BIGSERIAL PRIMARY KEY`
- `profile_id BIGINT REFERENCES user_constraint_profiles(id) ON DELETE CASCADE`
- `field_name TEXT NOT NULL`
- `old_value_json JSONB`
- `new_value_json JSONB NOT NULL`
- `status TEXT NOT NULL DEFAULT 'pending'`
- `source_channel TEXT`
- `source_text TEXT`
- `reason TEXT`
- `source_candidate_insight_id BIGINT REFERENCES candidate_insights(id) ON DELETE SET NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `decided_at TIMESTAMPTZ`

Status values:

- `pending`
- `confirmed`
- `rejected`
- `applied`

### `candidate_insights` source metadata extension

V1 decision and review workflows need to propose candidate insights without losing where they came from.

Add nullable metadata columns to the existing `candidate_insights` table:

- `source_workflow TEXT`
- `source_object_type TEXT`
- `source_object_id BIGINT`
- `source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb`

Expected values:

- `source_workflow`: `decision`, `weekly_review`, `manual_command`, or `system_proposal`
- `source_object_type`: `stock_decision`, `review_report`, `command_event`, or `none`
- `source_object_id`: id of the saved decision, review report, or command event when available

This avoids storing workflow provenance only inside free-text `reason` fields.

### `stock_observations`

Stores time-sensitive stock observations separate from durable facts.

Recommended columns:

- `id BIGSERIAL PRIMARY KEY`
- `stock_id BIGINT NOT NULL REFERENCES stocks(id) ON DELETE CASCADE`
- `observation_type TEXT NOT NULL`
- `observed_at TIMESTAMPTZ NOT NULL`
- `period_start TIMESTAMPTZ`
- `period_end TIMESTAMPTZ`
- `value_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `source_id BIGINT REFERENCES sources(id) ON DELETE SET NULL`
- `confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.500`
- `stale_after TIMESTAMPTZ`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Initial observation types:

- `technical_snapshot`
- `valuation_snapshot`
- `chip_event_snapshot`
- `sector_relative_strength`
- `market_relative_strength`
- `latest_quote_snapshot`

### `inference_items`

Stores model-inferred investment logic separately from facts and user insights.

Recommended columns:

- `id BIGSERIAL PRIMARY KEY`
- `target_type TEXT NOT NULL`
- `target_id BIGINT`
- `inference_type TEXT NOT NULL`
- `content TEXT NOT NULL`
- `supporting_source_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `supporting_knowledge_item_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.500`
- `stale_after TIMESTAMPTZ`
- `status TEXT NOT NULL DEFAULT 'candidate'`
- `promoted_to_knowledge_item_id BIGINT REFERENCES knowledge_items(id) ON DELETE SET NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Status values:

- `candidate`
- `active`
- `superseded`
- `rejected`
- `promoted`

### `stock_decisions`

Stores immutable Decision Ticket snapshots.

Recommended columns:

- `id BIGSERIAL PRIMARY KEY`
- `stock_id BIGINT NOT NULL REFERENCES stocks(id) ON DELETE CASCADE`
- `symbol TEXT NOT NULL`
- `market TEXT NOT NULL`
- `requested_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `decision_type TEXT NOT NULL DEFAULT 'single_stock'`
- `mode TEXT NOT NULL DEFAULT 'focused'`
- `recommendation TEXT NOT NULL`
- `composite_score NUMERIC(5, 2) NOT NULL`
- `confidence TEXT NOT NULL`
- `freshness_status TEXT NOT NULL`
- `suggested_initial_position_min_pct NUMERIC(6, 3)`
- `suggested_initial_position_max_pct NUMERIC(6, 3)`
- `suggested_max_position_pct NUMERIC(6, 3)`
- `position_class TEXT`
- `score_components_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `gates_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `veto_conditions_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `entry_conditions_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `add_conditions_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `reduce_conditions_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `next_review_trigger_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `evidence_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `stale_components_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `unresolved_questions_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `stock_card_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `context_pack_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `input_context_hash TEXT`
- `model_name TEXT`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### `stock_decision_evidence_links`

Stores traceability from ticket sections to graph/source/observation/inference objects.

Recommended columns:

- `id BIGSERIAL PRIMARY KEY`
- `decision_id BIGINT NOT NULL REFERENCES stock_decisions(id) ON DELETE CASCADE`
- `section TEXT NOT NULL`
- `component TEXT`
- `evidence_type TEXT NOT NULL`
- `evidence_id BIGINT`
- `evidence_ref TEXT`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Evidence types:

- `source`
- `knowledge_item`
- `user_insight`
- `candidate_insight`
- `stock_observation`
- `inference_item`
- `research_job`
- `review_report`
- `external_ref`

## Recommendation Categories

Use decision-support language, not imperative trading language.

Allowed recommendations:

- `avoid`
- `watch`
- `wait`
- `starter`
- `normal_position`
- `high_conviction_candidate`
- `review_existing_holding`
- `trim`
- `reduce`

Rendering may display friendlier text, but stored values should use stable codes.

## Position Sizing Rules

V1 position sizing should be range-based.

Inputs:

- User max single-stock position.
- Preferred starter position.
- Existing holding weight.
- Cash reserve requirement.
- Market exposure cap.
- Theme exposure cap.
- Volatility tolerance.
- Event risk.
- Data freshness and confidence.

Default behavior:

- If user profile is missing, use conservative defaults and mark them as unconfirmed.
- If stock is not currently held, `starter` should usually use the starter range, capped by cash and theme constraints.
- If stock is already held, output review/add/reduce ranges relative to current exposure.
- If critical data is stale, output `watch` or `wait` and avoid specific add sizing beyond max cap.
- Never output a false-precision single number such as `2.7%`; use ranges such as `2%-3%`.

## Freshness Planner

The freshness planner decides whether to run quick, focused, or deep path.

Modes:

- `quick`: no external refresh; uses graph and latest stored observations.
- `focused`: refreshes only stale critical packs if local adapters are available.
- `deep`: queues or runs broader research refresh before allowing high-conviction output.

Initial freshness targets:

| Pack | V1 target |
| --- | --- |
| Portfolio holdings and cash | 1 trading day |
| Quote and technical snapshot | 1 trading day |
| Market and sector relative strength | 1-3 trading days |
| Chip/event structure | Refresh before decision when missing |
| Valuation snapshot | 1-7 days depending on source |
| Company filings | Until next filing or major announcement |
| Sector thesis inference | 7-30 days |
| User confirmed profile | Durable until changed |
| Decision ticket | Snapshot only |

V1 does not need to implement every external refresh adapter immediately. Missing adapters must produce explicit stale or missing components and confidence caps.

## Data Source Strategy

Initial V1 source order:

1. Internal graph: `stocks`, `knowledge_items`, `sources`, `user_insights`, `candidate_insights`, `research_jobs`.
2. Portfolio state: latest `account_snapshots` and Futu read-only position access where explicitly used by the command path.
3. Stored observations: `stock_observations`.
4. Official-source research artifacts already created by the research pipeline.
5. Model inference, labeled and persisted separately.

Do not make every `决策` command perform broad web search. If source coverage is weak, save unresolved questions and optionally queue a research job.

### External Data Source Fallback Plan

The cloud probe for `KR.000660` showed that the current Futu OpenD quote APIs reject Korean-stock codes such as `KR.000660`, `KS.000660`, and `KRX.000660` with a code-format error, while the same probe succeeds for supported markets such as `US.AAPL`. Therefore, Futu should remain the read-only source for portfolio/account/trade data, but it must not be the primary V1 source for Korean stock quote, technical, valuation, or analyst data.

For Korean stocks, V1 should use an adapter ladder instead of a single provider:

1. `internal_graph`: durable facts, source-backed research, sector links, user insights, and saved observations.
2. `futu_portfolio`: holdings, cash, trade records, and account state only.
3. `naver_finance_kr`: first KR market-data fallback for `latest_quote_snapshot`, `valuation_snapshot`, financial summary, peer comparison, foreign/institution flow, and compact company overview. Naver Finance exposes a usable SK hynix page for code `000660`, including KRX-close quote fields, price/volume, company overview, financial table, valuation metrics, peer comparison, and foreign ownership/trading data. Because this is page extraction rather than a stable contract API, the adapter must be low-QPS, cached, parser-tested, attributed, and fail closed.
4. `yahoo_finance`: auxiliary source for historical OHLCV, technical indicators, and market-relative strength when available. Map `KR.000660` to Yahoo ticker `000660.KS`; use `^KS11` for KOSPI market-relative strength and a configured semiconductor basket for sector-relative strength. Direct Yahoo chart probing can hit `Too Many Requests`, so this adapter must use backoff, caching, and freshness reuse; it should not be the only critical source for a high-conviction ticket.
5. `krx_data_marketplace`: preferred official-source path for later hardening. KRX Data Marketplace lists individual stock price trend, stock basic information, investor trading, short-selling, index data, and PER/PBR/dividend-yield screens. It should be used when the integration contract is stable enough, but V1 should not block on reverse-engineering CSV/OTP flows.
6. `company_ir_and_newsroom`: official SK hynix IR earnings releases, ownership structure, and newsroom releases for `chip_event_snapshot` and major company event evidence.
7. `investing_or_other_web`: manual research fallback only. Do not make it a default automated adapter in V1 unless a stable, licensed, and testable data access path is confirmed.

Provider selection should be explicit in every observation:

```json
{
  "provider": "naver_finance_kr",
  "provider_symbol": "000660",
  "source_url": "https://finance.naver.com/item/main.naver?code=000660",
  "retrieved_at": "2026-06-22T00:00:00Z",
  "coverage": ["latest_quote_snapshot", "valuation_snapshot", "peer_comparison"],
  "license_status": "page_extraction_review_required",
  "quality": "usable_for_v1_with_attribution"
}
```

Required V1 behavior:

- Add a `market_symbol_map` resolver that can map canonical internal symbols to provider symbols, for example `KR.000660 -> naver:000660` and `KR.000660 -> yahoo:000660.KS`.
- Add a source-probe command or script that reports provider coverage per stock before an adapter is trusted for scoring.
- Store provider diagnostics in observation `value_json` or a dedicated adapter diagnostics field so the Decision Ticket can explain why a pack is missing or stale.
- Never silently substitute a US ADR, OTC ticker, or similarly named company for a Korean listing.
- If all external adapters fail, continue producing a Decision Ticket, but cap confidence and show the missing packs.

Initial source ownership by pack:

| Pack | Primary V1 source | Fallback | Notes |
| --- | --- | --- | --- |
| `latest_quote_snapshot` | `naver_finance_kr` | `yahoo_finance`, stored observation | Futu is not expected to support KR quote codes in the current environment. |
| `technical_snapshot` | `yahoo_finance` OHLCV | Naver daily price table, stored observation | Compute locally from OHLCV; do not rely on provider prose. |
| `valuation_snapshot` | `naver_finance_kr` financial and valuation table | company IR, research job artifact | Separate historical actuals, consensus estimates, and provider-derived ratios. |
| `market_relative_strength` | `yahoo_finance` `^KS11` or KRX index data | stored observation | Compare stock return to KOSPI over configured windows. |
| `sector_relative_strength` | configured peer basket via Yahoo or Naver peer table | stored observation | V1 basket can start with Samsung Electronics, Micron, and semiconductor ETFs/indices where available. |
| `chip_event_snapshot` | SK hynix IR/newsroom, saved research artifact | curated web research job | This remains semi-structured and should be evidence-linked, not scraped as a score directly. |

## Context Pack Budget

The model synthesis prompt should be bounded:

- Top 5-10 relevant facts per pack.
- No raw filings.
- No raw source dumps.
- Evidence ids and compact summaries only.
- Candidate insights shown as pending, not confirmed preferences.
- Missing or stale packs listed explicitly.
- Pre-score and gates passed into the model as constraints.

## Command Routing

Add to `command_router.py`:

```text
决策 SYMBOL MARKET
决策详情 SYMBOL MARKET
刷新决策数据 SYMBOL MARKET
查看决策历史 SYMBOL MARKET
设置决策偏好
查看决策偏好
```

English aliases:

```text
decide SYMBOL MARKET
decision-detail SYMBOL MARKET
refresh-decision-data SYMBOL MARKET
decision-history SYMBOL MARKET
set-decision-profile
show-decision-profile
```

Behavior:

- `决策`: focused mode, save snapshot, render default ticket.
- `决策详情`: either latest saved decision for stock or newly generated decision with expanded trace, depending on command syntax chosen during implementation.
- `刷新决策数据`: refresh or mark observation packs without forcing model synthesis.
- `查看决策历史`: list saved decisions with recommendation, score, confidence, freshness, and created time.
- `查看决策偏好`: show active profile and pending profile changes.
- `设置决策偏好`: first version may return guided instructions and record candidate changes; full interactive editing belongs to web workbench.

## MCP Tools

Add to `server.py`:

- `decide_stock(symbol: str, market: str, mode: str = "focused") -> dict`
- `get_stock_decision_detail(decision_id: int) -> dict`
- `list_stock_decision_history(symbol: str, market: str, limit: int = 20) -> list[dict]`
- `refresh_stock_decision_data(symbol: str, market: str, mode: str = "focused") -> dict`
- `get_decision_profile() -> dict`
- `propose_decision_profile_change(field_name: str, value: Any, reason: str | None = None) -> dict`

Keep existing `inspect_stock_decision_card` for compatibility, but future user-facing language should call it Stock Evidence Card.

## Candidate Insight Capture Boundary

This section is a runtime feature boundary for Stock Decision System V1, not a replacement for the repository-wide agent operating rules. The current agent development convention should live in `AGENTS.md` and `docs/agent-lessons.md`: ordinary technical discussion, planning, debugging, or user pushback must not be written as memory unless the user explicitly asks for that write.

The Decision System should implement the same boundary in product code:

- No ambient conversation capture in V1.
- No candidate insight write from ordinary chat text, technical planning discussion, or assistant interpretation alone.
- Candidate insight writes are allowed only from explicit product entrypoints or bounded product workflows.
- If the system thinks a non-entrypoint user sentence might be worth preserving, it may ask whether to save it, but must not write first.
- Anything that can affect scoring, position sizing, risk limits, cash reserve, theme caps, or market exposure must remain pending until explicit user confirmation.

Allowed V1 write entrypoints:

- Explicit memory commands such as `记录策略心得 ...`, `记录组合心得 ...`, `提出策略候选心得 ...`, and existing stock or sector memory commands.
- Explicit decision profile commands such as `设置决策偏好` and future profile-change confirmation commands.
- Bounded decision workflow output from `决策 SYMBOL MARKET`, where proposed lessons are shown as pending candidate proposals tied to that saved Decision Ticket.
- Bounded weekly-review workflow output, where proposed lessons are shown as pending candidate proposals tied to that review.

Deferred from V1:

- General "natural conversation capture" from arbitrary chat.
- Background monitoring of Codex conversation for possible memory.
- DingTalk direct writes of nuanced lessons or structured decision preferences.

Implementation requirements:

- Command routing should use an explicit allowlist for memory-write commands.
- Decision and review workflows should tag generated candidates with `source_workflow`, `source_decision_id` or `source_review_report_id` where available.
- Candidate proposals created by decision or review workflows must be rendered back to the user as pending, not silently hidden.
- Tests should cover that a normal non-capture command does not create `candidate_insights`.

## Candidate Insight Flow

Decision synthesis may propose:

- Candidate stock insight.
- Candidate sector insight.
- Candidate portfolio insight.
- Candidate strategy insight.
- Candidate structured profile change.

Rules:

- Model-inferred lessons from allowed decision or review workflows always go to `candidate_insights`, never directly to `user_insights`.
- Structured profile changes remain pending until confirmed.
- Explicit user commands such as `记录策略心得 ...` can continue writing confirmed user insights through existing paths.
- Pending candidate insights can influence context as pending context, but cannot change hard scoring constraints.

## Weekly Review Integration

V1 decision system should expose enough saved data for weekly review, but weekly review wiring can be the final slice.

Weekly review should later:

- List current holdings with missing or stale Decision Tickets.
- Compare trades against prior Decision Tickets.
- Identify whether veto conditions occurred.
- Propose candidate lessons from validated or invalidated decisions.
- Never auto-confirm lessons.

## Web Workbench Follow-up

The first web surface should be Decision Preference Review, not the full decision workbench.

First web slice:

- Pending candidate insights.
- Confirm, reject, or edit candidate insight.
- Current decision profile.
- Pending structured profile changes.
- Profile change history.

Second web slice:

- Full Decision Ticket workbench.
- Decision history.
- Evidence freshness and source trace.
- Weekly-review validation links.

This split is due to safety and input quality. Decision scores and position ranges depend on confirmed constraints.

## Build Slices

### Slice 1: Persistence and Repository

Reason for slice:

- The feature needs durable snapshots and traceability before command behavior becomes useful.

Work:

- Add schema tables and indexes.
- Add repository functions.
- Add serialization helpers for Decision Ticket rows.
- Add smoke fixtures for one stock and one profile.

Acceptance:

- Can create active default profile.
- Can save and fetch stock decision snapshot.
- Can list decision history.
- Can save evidence links.

### Slice 2: Context Pack Builder

Reason for slice:

- The model and scoring layer must consume compact structured packs, not raw graph dumps.

Work:

- Build Stock Evidence Card as input.
- Build portfolio exposure pack from latest account snapshot or read-only Futu snapshot when available.
- Build constraint pack from active profile.
- Build observation packs from stored observations.
- Build freshness report.
- Build evidence index.

Acceptance:

- `build_decision_context_pack("000660", "KR")` returns stable structured JSON.
- Missing portfolio/profile/observation inputs are explicit, not silent.
- Context hash is stable for unchanged inputs.

### Slice 2A: External Data Probes and KR Fallback Adapters

Reason for slice:

- The first end-to-end target is `000660 KR`, and the cloud Futu probe proved that Futu quote APIs do not accept the Korean listing code in the current environment. The decision system cannot improve confidence for this target without a market-data adapter ladder.

Work:

- Add `market_symbol_map` utilities for provider-specific symbols.
- Extend `decision_data_probe` into a provider coverage probe that can test Futu, Naver Finance, Yahoo Finance, KRX availability, and company IR reachability without writing observations.
- Add `naver_finance_kr` read-only adapter for SK hynix quote, financial table, valuation metrics, peer comparison, and foreign/institution flow.
- Add `yahoo_finance` read-only adapter for OHLCV-driven technical snapshots and market/sector relative-strength inputs, with cache and backoff handling for rate limits.
- Add observation writers that persist successful adapter results as `stock_observations` with provider metadata and stale-after timestamps.
- Keep KRX Data Marketplace and Investing.com as non-blocking research items unless a stable API or licensed access path is confirmed.

Acceptance:

- `decision_data_probe 000660 KR` reports Futu as unsupported for KR quotes and reports Naver/Yahoo/KRX/company-IR coverage separately.
- `refresh_decision_data("000660", "KR", mode="focused")` can produce at least `latest_quote_snapshot`, `valuation_snapshot`, `technical_snapshot`, and `market_relative_strength` from non-Futu sources when network access is available.
- Adapter failures are rendered as provider diagnostics and do not crash `决策 000660 KR`.
- No provider result is used without storing `provider`, `provider_symbol`, `source_url`, `retrieved_at`, and `stale_after`.

### Slice 3: Deterministic Scoring and Gates

Reason for slice:

- Deterministic pre-scoring prevents model prose from inventing unsupported conviction.

Work:

- Implement score component calculation.
- Implement gate engine.
- Implement position range derivation.
- Implement deterministic fallback ticket.

Acceptance:

- Missing profile caps confidence.
- Stale technical or portfolio data lowers confidence and caps recommendation.
- Theme or market exposure cap reduces position max.
- Component scores sum to composite score with documented weights.

### Slice 4: Model Synthesis and Validation

Reason for slice:

- The model should synthesize reasons and conditions only after deterministic constraints exist.

Work:

- Add synthesis prompt and response schema.
- Validate model JSON.
- Enforce deterministic gates after model output.
- Store inferences separately.
- Fall back cleanly when model is disabled.

Acceptance:

- Model output cannot override a gate.
- Facts and inferences are labeled.
- Inferred user lessons go to candidate insights only.
- Prompt is compact and excludes raw dumps.

### Slice 5: Commands and MCP Tools

Reason for slice:

- CLI/MCP validation is the safest first product surface before web.

Work:

- Add command router paths.
- Add MCP tools.
- Add renderers.
- Add `scripts/ikg.py` smoke examples if needed.

Acceptance:

- `决策 000660 KR` returns a saved Decision Ticket.
- `决策详情 000660 KR` shows component evidence and freshness.
- `查看决策历史 000660 KR` lists saved snapshots.
- Existing `分析 000660 KR` still returns Stock Evidence Card behavior.

### Slice 6: Weekly Review Hooks

Reason for slice:

- Weekly review should consume saved decisions after the snapshot format is stable.

Work:

- Add repository query for decisions in review period.
- Add weekly review context section for decision coverage.
- Add candidate insight proposals for decision lessons.

Acceptance:

- Weekly review can see decisions made during the period.
- It can identify missing or stale Decision Tickets for holdings.
- It does not auto-confirm lessons.

## First End-to-End Scenario

Use `000660 KR`.

Expected demonstration:

- Evidence card comes from graph context.
- Portfolio pack is present or explicitly stale/missing; Futu is used only for account/holding inputs.
- KR market-data packs come from the adapter ladder: Naver/Yahoo/KRX/company IR before falling back to missing or stale stored observations.
- User constraint profile is present or confidence is capped.
- HBM and memory-cycle context appears through stock/sector/user insights.
- Provider diagnostics explain any missing or stale quote, valuation, technical, market-relative, sector-relative, or chip-event pack.
- Composite score and gates are produced.
- Position range is range-based.
- Decision snapshot is saved.
- Candidate insights are proposed only if appropriate.

## Test Plan

Unit tests:

- Context pack builder with missing profile and missing observations.
- Score weights and composite score.
- Gate caps for stale critical data, concentration, event risk, and missing confirmed constraints.
- Position range derivation.
- Model output validation and gate enforcement.
- Repository save/fetch/history/evidence links.

Smoke tests:

- Run schema.
- Seed one profile, one stock, and stock facts.
- Run `决策 000660 KR`.
- Run `决策详情 000660 KR`.
- Run `查看决策历史 000660 KR`.

Manual checks:

- Default output is concise enough for first-screen use.
- Detail output is traceable enough for audit.
- Missing data is visible.
- Existing `分析` and `分析详情` behavior remains intact.

Do not start command-api, schedulers, dingtalk-api, or compose for normal local validation.

## Deployment Notes

- This is a schema and command-router feature. It should be validated locally with schema/smoke checks first.
- If deployed to cloud, use the normal pull-based deploy flow after changes are committed and pushed.
- No trading API write path is introduced.
- Futu usage remains read-only.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| The model overweights narrative. | Deterministic scoring and gates run before synthesis and are enforced after synthesis. |
| Stale technical or portfolio data creates false confidence. | Freshness report is first-class and gates recommendations. |
| User interprets score as a trading command. | Use decision-support recommendation categories and always show veto/review triggers. |
| Too many inputs make the command slow. | Use quick/focused/deep modes and compact context packs. |
| Inferred user preferences overwrite confirmed preferences. | Store inferred lessons as candidate insights or pending profile changes only. |
| Source licensing or availability varies by market. | Adapter-based source ladder; missing data is disclosed instead of fabricated. |
| Web-derived KR market data becomes brittle or rate-limited. | Cache observations, render provider diagnostics, keep KRX and company IR as hardening paths, and cap confidence when live refresh fails. |

## V1 Engineering Defaults

These defaults remove ambiguity for the first implementation. Revisit them only after the first end-to-end scenario works.

- `决策详情 SYMBOL MARKET` should default to the latest saved decision for that stock. A future explicit refresh flag or separate command can generate a new decision.
- Quote and technical refresh should start with stored or missing/stale observation packs plus the KR adapter ladder for Korean listings. Add Futu quote/technical refresh only for markets confirmed by source probes.
- CLI profile editing should be minimal in V1: show the active profile, propose pending profile changes, and confirm or reject them. Rich editing belongs to the Decision Preference Review web page.
- Sector and market regime should be stored in the decision `context_pack_json` and observation packs for the first migration. Promote to shared `sector_regime_snapshots` and `market_regime_snapshots` only after reuse across decisions or weekly reviews is proven.
