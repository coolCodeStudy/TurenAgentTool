# Command Workbench Technical Plan

Status: ready for bounded V1 implementation
Linked PRD: `docs/product/PRD-command-workbench.md`

## Product Contract

`/command` becomes a keyboard-first command workbench. Users may type natural shortcuts, but the system only executes registered actions after resolving entities and showing the exact command.

This plan implements the first complete usable version against the command surfaces that actually exist today. The PRD's "Decision" family maps to the existing Level 1 stock decision card path. A separate durable decision-ticket/history workflow does not exist in the current router; the workbench must recover explicitly for ticket/history-only requests instead of pretending those commands are available.

## Current Implementation

Current `/command` behavior lives in `investment_knowledge_mcp/command_api.py`:

- `POST /command` accepts JSON `{ "text": "..." }`.
- It requires `COMMAND_API_TOKEN`.
- It calls `run_schema()`, then `command_router.handle_command(text)`.
- It records one `command_events` row through `repository.record_command_event(...)`.
- It returns `{ ok, message }`.
- `GET /command` is not a web page today; only `GET /health` exists.

Current command execution lives in `investment_knowledge_mcp/command_router.py`:

- It accepts exact commands such as `分析 SYMBOL MARKET`, `查看股票 SYMBOL MARKET`, `研究草稿 SYMBOL MARKET`, `本周复盘`, `系统状态`, `查看研究任务`, and service-log commands.
- It has some natural normalization for stock analysis, portfolio, trade review, and system intent.
- It already includes query/write/maintenance classifiers used by DingTalk and smoke checks.
- It currently has no `决策` command keyword, no `/command` browser UI, no structured preview, and no command registry.

Current entity resolution lives in `repository.resolve_stock_reference(query)`:

- It searches stock profiles by exact symbol, exact name, and partial name.
- It does not currently search aliases, portfolio holdings, or recent execution targets.

Existing telemetry:

- `db/schema.sql` defines `command_events`.
- `repository.record_command_event(...)` stores `source`, `sender`, `command`, `ok`, `message`, and `created_at`.
- There is no separate parse telemetry table.

## Touched Modules

Implementation should stay narrow:

- `investment_knowledge_mcp/command_workbench.py` new registry, parser, preview model, entity resolver, HTML renderer, and execution guard helpers.
- `investment_knowledge_mcp/command_api.py` adds `GET /command`, `GET /api/command-workbench/actions`, `POST /api/command-workbench/parse`, and `POST /api/command-workbench/execute`, while preserving legacy `POST /command`.
- `investment_knowledge_mcp/weekly_review_web.py` also serves `GET /command` and the workbench APIs so the cloud acceptance surface can use the already-public web port `8010`.
- `investment_knowledge_mcp/command_router.py` adds `决策` / `decision` aliases for the existing stock decision card path.
- `investment_knowledge_mcp/analysis_provider.py` may expose a bounded LLM parse-proposal helper.
- `scripts/smoke_test.py` extends local parser/router coverage.
- `docs/project-management/Feature-Registry.md` links this plan and records implementation/verification status.

## Command Registry Design

The web workbench owns a registry of website-safe actions. Each action has:

- `id`
- `action_family`
- `label`
- `description`
- `aliases`
- `required_fields`
- `optional_fields`
- `template`
- `safety_level`: `read_only`, `writes_durable_record`, `maintenance`, or `unsupported`
- `confirmation_required`
- `side_effects`
- `data_sources`
- `expected_output`
- `result_type`
- `supports_execution`

Initial registry scope:

- Decision: Level 1 decision card, full decision/detail context, refresh research draft, decision history/profile recovery.
- Portfolio: current positions, portfolio analysis.
- Weekly review: this week, previous week, source diagnostics recovery.
- Research: single-stock research job, list jobs, portfolio research jobs.
- System: system status, recent errors, worker status, service logs.
- Advanced exact command: only for registered exact patterns; unknown text is never passed through.

The registry is the allowlist. The parser may propose a command only if its action id exists and supports execution.

## Parser Flow

The parser follows this order:

1. Exact command detection
   - Recognize registered exact commands such as `决策 US.INTC`, `决策 INTC US`, `分析 INTC US`, `查看股票 INTC US`, `本周复盘`, `系统状态`, `服务日志 mcp`, and research-job commands.
   - Return a preview without using an LLM.

2. Deterministic aliases
   - Match common shortcuts such as `决策 英特尔`, `decision Intel`, `刷新海力士决策`, `看一下 阿里`, `本周复盘`, `上周复盘`, `系统状态`, `最近错误`, and `查看 mcp 日志`.
   - Extract intent and unresolved target text.

3. Entity resolution
   - Parse `market.symbol`, `symbol market`, and exact symbol forms.
   - Parse uppercase US ticker shorthand such as `MSTR` as `US.MSTR`.
   - Search a small code alias map for high-value aliases from the PRD: Intel, SK Hynix, Alibaba, and the South CSOP SK Hynix 2x product.
   - Search `repository.resolve_stock_reference(...)`.
   - If a syntactically valid symbol is not present in stock profiles, return a confirmed "Initialize stock profile" action instead of executing a stale or impossible decision command.
   - If a stock resolves but only has the minimal bootstrap profile and no imported facts/sources, return a confirmed single-stock research-job action instead of a low-information decision card.
   - Merge duplicate candidates and sort by confidence.
   - Return:
     - `parsed` for one high-confidence candidate.
     - `ambiguous_entity` for multiple candidates.
     - `needs_entity` when no candidate is found.
     - `needs_field` for action forms with missing required fields.

4. LLM-assisted parse proposal
   - Only runs if deterministic parsing cannot produce a preview and OpenAI is configured.
   - Prompt includes raw input, registry summary, and local candidate entities only.
   - Output is a proposal with action id, fields, confidence, and reason.
   - Output must pass registry validation and entity resolution before preview.
   - LLM output is never executed directly.

5. Recovery
   - Unknown intent returns supported action families and examples.
   - Unsupported registered actions return an explicit unsupported state.
   - Ambiguous stocks return selectable candidates.

## Preview And Confirmation Model

Every parsed action returns a preview:

- Raw input.
- Action label and family.
- Target entity, when present.
- Parser source and confidence.
- Exact command that will run.
- Safety level.
- Confirmation requirement.
- Side effects.
- Data sources.
- Expected output.
- Token/cost disclosure.

Execution is allowed only when:

- `status == "parsed"`.
- `supports_execution == true`.
- Required fields are resolved.
- The exact command was generated from a registered action.
- Confirmation has been supplied when required.
- API token authorization has passed.

Confirmation is required for:

- Research job creation.
- Portfolio research job creation.
- Research draft refresh / generated artifact actions.
- Maintenance actions.
- Low-confidence entity matches.
- Any future durable write command.

Read-only high-confidence actions can run from the preview.

## Structured Fallback Forms

The page provides grouped action cards. Clicking an action opens a structured mini-form instead of inserting incomplete raw syntax.

Initial field forms:

- Stock target text for decision, detail, refresh, and single-stock research job.
- Week selector for this week / previous week.
- Service selector for logs.
- Provider/source-policy display for research-job creation.

If required fields are missing, the parser returns `needs_field` and the UI keeps the form open.

## Safety Boundaries

- No trading actions are registered.
- Unknown free text is blocked.
- LLM parse proposals cannot execute.
- Access tokens stay in the browser input/local storage only and are never stored in command history.
- The server recomputes the preview during execute; the browser cannot submit an arbitrary exact command hidden in a preview.
- Write-like and maintenance actions require explicit confirmation.
- Deployment actions remain out of scope.
- Current `POST /command` remains as the operator API; the workbench API is safer and registry-gated.

## UI And Result Cards

`GET /command` renders a self-contained HTML page served by `command_api`. In cloud production, the same page and APIs are mirrored by `weekly_review_web` on the public web port because `command-api` can run internally while port `8001` may not be externally reachable.

V1 layout:

- Smart input and token field.
- Parsed preview card.
- Candidate picker for ambiguous stocks.
- Grouped action catalog.
- Structured form panel.
- Result card with status, event id, exact command, target, body, diagnostics, and suggested next actions.
- Recent and pinned actions stored in browser localStorage.

Result cards initially wrap existing plain-text router output while adding structured metadata around it.

## Telemetry

No schema migration is required in V1.

- Parse attempts record `command_events` rows with source `command-workbench.parse`.
- Executions record `command_events` rows with source `command-workbench.execute`.
- Legacy `POST /command` continues to record rows with the caller-provided source.
- Event id returned from `record_command_event(...)` is shown in the result card.

Future analytics can query command text prefixes and source values for parse success, ambiguity, unsupported requests, confirmations, and execution failures.

## Implementation Steps

1. Add `command_workbench.py` registry, parser, resolver, preview serialization, HTML renderer, and execute eligibility helpers.
2. Add `决策` / `decision` aliases to `command_router.py` and query classification.
3. Add optional bounded OpenAI parse proposal helper in `analysis_provider.py`.
4. Extend `command_api.py` with workbench HTML, action catalog, parse, and execute endpoints.
5. Add smoke coverage for:
   - `决策 <stock>` router alias.
   - `决策 英特尔` preview.
   - `决策 阿里` ambiguity.
   - catalog/form parse for Create decision.
   - confirmation requirement for research job creation.
   - unsupported free text blocked before execution.
6. Update `Feature-Registry.md`.

## Verification Plan

Local checks:

- `python3 scripts/audit_prd_status.py`
- `.venv/bin/python scripts/smoke_test.py`
- Targeted Python checks for `parse_workbench_command(...)` and `render_command_workbench_html()`.
- If the HTTP entrypoint is changed, run a local `command_api` smoke against `GET /command`, parse endpoint, and execute guard without starting broad compose services.

Manual browser verification is useful but not required for code-done unless a local server is started explicitly.

Acceptance checks:

- `决策 英特尔` resolves to Intel / `US.INTC` and shows a decision preview.
- `决策 MSTR` or `决策 US.LRCX` offers a confirmed minimal stock-profile initialization path when the symbol is absent, then supports re-previewing the decision command after the profile exists.
- `决策 MSTR` or `决策 US.LRCX` must not show a successful empty decision card when only the minimal bootstrap profile exists; it should offer a confirmed stock research job and explain that the decision card becomes useful after facts are imported.
- `决策 阿里` returns candidate targets.
- `本周复盘` previews/runs the weekly review command.
- `系统状态` previews/runs as read-only.
- Create Decision catalog opens a target field.
- Unknown input returns supported actions.
- Recent executions are browser-local and do not include tokens.
- Existing exact `POST /command` remains compatible.

## Deployment Impact

- No database migration is required.
- No new service is required.
- The changed surfaces are the existing `command-api` service and the public `weekly-review-web` service.
- `command-api` should be included in `scripts/deploy_from_local_checkout.sh` so quick and full deploys actually start the service.
- Cloud user acceptance should use `http://47.84.190.191:8010/command` unless port `8001` is explicitly opened for `command-api`.

## Risks And Follow-Ups

- Decision tickets/history are product scope but not implemented in the current router. V1 exposes the existing decision-card workflow and returns explicit recovery for ticket/history-only requests.
- Alias management is code-based in V1. A future product decision can add editable aliases.
- Recent/pinned actions are browser-local in V1. Server-side history can be added later if multi-device recency becomes important.
- LLM-assisted parsing depends on `OPENAI_API_KEY`; local verification should cover deterministic behavior and the LLM-disabled fallback.
- Missing-stock bootstrap intentionally creates only a minimal stock profile. It solves the command-entry dead end for valid symbols; richer company metadata, source facts, and research drafts remain follow-up work through the research-job/import pipeline.
- Low-information decision cards are not acceptable output. When the system can identify the stock but has only bootstrap placeholders, the workbench should route to the research-job/import pipeline before presenting a decision card as useful.
