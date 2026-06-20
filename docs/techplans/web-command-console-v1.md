# Tech Plan: Web Command Console V1

## Background

The current product has a powerful unified command layer:

```text
scripts/ikg.py
DingTalk Stream bot
DingTalk webhook adapter
MCP run_investment_command
command-api
  -> command_router.handle_command(...)
```

Stock Decision System V1 makes this more important because `决策 SYMBOL MARKET`, decision history, decision profile, weekly review, candidate insights, portfolio analysis, and operational status are all already command-shaped workflows.

The user expectation is clear: commands available through DingTalk should also be usable from the website. The first web implementation should therefore be a Web Command Console, not a separate page for every command.

## Product Goal

Add a website command surface where the user can run the same InvestmentKnowledge commands that they can send in DingTalk, with better rendering, history, and guardrails.

The first screen should be an actual usable command console:

- Command input.
- Execute button.
- Common command templates.
- Result panel.
- Recent command history.
- Explicit write confirmation for commands that persist data.

This is the bridge between chat-style commands and future productized workbenches.

## Non-Goals

V1 does not build a full UI for every command.

Deferred:

- Full Stock Decision workbench with forms, charts, and editable tickets.
- Full operations dashboard replacement.
- Full auth/user system.
- Multi-user permission management.
- Rich Markdown editor for every command result.
- General natural-language memory capture.

## Current Baseline

Existing pieces:

- `command_router.handle_command(command, ...)` is the canonical business command entrypoint.
- `scripts/ikg.py` invokes `handle_command(...)`.
- DingTalk Stream bot invokes `handle_command(...)`, but its write allowlist currently has its own logic.
- `investment_knowledge_mcp/command_api.py` exposes `POST /command`, but only as an authenticated HTTP API.
- `investment_knowledge_mcp/weekly_review_web.py` already serves a no-build HTML page and JSON APIs.
- `command_events` already records executed commands.
- Command classifier helpers already exist:
  - `is_query_command`
  - `is_candidate_write_command`
  - `is_decision_write_command`
  - `is_coding_task_command`
  - `is_maintenance_command`
  - `is_research_write_command`

Important issue to fix:

- DingTalk Stream write guard should use the same command categories as the website. Stock decision commands are write commands because `决策 SYMBOL MARKET` saves a `stock_decisions` snapshot, but the Stream guard currently does not include `is_decision_write_command`.

## Target Architecture

```text
Browser
  -> GET /command
  -> POST /api/command
       -> command_access.classify_command(command)
       -> optional write confirmation check
       -> run_schema()
       -> command_router.handle_command(command, include_artifact_path=false)
       -> repository.record_command_event(...)
       -> JSON response

DingTalk Stream
  -> same command_access.classify_command(command)
  -> same write category policy
  -> command_router.handle_command(...)
```

The console should use the existing Python standard-library HTTP server pattern first. Do not add a frontend build chain for V1.

## Module Design

### `investment_knowledge_mcp/command_access.py`

New shared command access classifier.

Public functions:

- `classify_command(command: str) -> dict`
- `is_write_command(command: str) -> bool`
- `is_high_risk_command(command: str) -> bool`

Suggested output:

```json
{
  "category": "query|decision_write|candidate_write|research_write|maintenance|coding_task|ops|unknown",
  "requires_confirmation": true,
  "requires_sender_allowlist": true,
  "allowed_from_web": true,
  "allowed_from_dingtalk": true,
  "reason": "..."
}
```

Initial classification:

| Category | Examples | Web Behavior | DingTalk Behavior |
| --- | --- | --- | --- |
| `query` | `分析 000660 KR`, `决策详情 000660 KR`, `查看决策历史 000660 KR`, `本周复盘` | Run directly | Run directly |
| `decision_write` | `决策 000660 KR`, `设置决策偏好 ...`, `确认决策偏好 ...` | Require confirmation | Require sender allowlist/write mode |
| `candidate_write` | `提出策略候选心得 ...`, `确认候选心得 6` | Require confirmation | Require sender allowlist/write mode |
| `research_write` | `创建研究任务 ...`, `取消研究任务 ...` | Require confirmation | Require sender allowlist/write mode |
| `maintenance` | `富途验证码 ...`, `富途登录` | Require confirmation and admin mode | Require sender allowlist/write mode |
| `coding_task` | `创建开发任务 ...` | Require confirmation | Require sender allowlist/write mode |
| `ops` | cloud deploy, service restart, logs where sensitive | Admin-only, hidden by default | Admin-only |
| `unknown` | unrecognized text | Block with help | Block with help |

This module should wrap the existing classifier helpers first rather than replacing them wholesale.

### `investment_knowledge_mcp/command_web.py`

New web server module, or a new route inside `weekly_review_web.py`.

Preferred V1 option:

- Add `command_web.py` as a separate server if the page is independent.
- If product wants a single local website immediately, mount `/command` into `weekly_review_web.py`.

Because the existing deployed web service is `weekly-review-web`, the fastest path is:

- Add `/command` and `/api/command` to `weekly_review_web.py`.
- Rename product-facing nav label from "weekly review only" to an InvestmentKnowledge workbench shell.
- Keep the module name for deployment compatibility until a later safe rename.

Routes:

```text
GET /command
POST /api/command
GET /api/command/history?limit=20
```

`POST /api/command` request:

```json
{
  "command": "决策 000660 KR",
  "confirmed": false,
  "sender": "web"
}
```

If the command requires confirmation and `confirmed=false`, return:

```json
{
  "ok": false,
  "requires_confirmation": true,
  "classification": {},
  "preview": "This command will save a Decision Ticket snapshot."
}
```

The frontend then shows a confirmation dialog and resubmits with `confirmed=true`.

Successful response:

```json
{
  "ok": true,
  "message": "...",
  "classification": {},
  "command_event_id": 123
}
```

### Frontend Page

No build chain.

Use server-rendered HTML with inline CSS/JS, consistent with `weekly_review_web.py`.

Page layout:

- Left nav:
  - Weekly Review
  - Command Console
  - Candidate Insights
- Main:
  - Command input textarea.
  - Run button.
  - Confirmation state.
  - Result panel with monospace/Markdown-like text.
- Right rail:
  - Common command templates.
  - Recent commands.
  - DB/source status.

Common templates:

- `决策 000660 KR`
- `决策详情 000660 KR`
- `查看决策历史 000660 KR`
- `刷新决策数据 000660 KR`
- `查看决策偏好`
- `持仓分析`
- `本周复盘`
- `查看候选心得`
- `系统状态`

## Permission And Safety Rules

The website must not become a silent write surface.

Rules:

- Query commands run directly.
- Write commands require a visible confirmation dialog.
- Unknown commands are blocked and return help.
- General chat text must not create candidate insights.
- Candidate/user insight writes only happen through explicit command entrypoints.
- Decision profile changes remain pending unless the command is an explicit confirmation command.
- High-risk ops commands are hidden from templates and require admin mode.

V1 auth:

- Reuse `WEEKLY_REVIEW_WEB_TOKEN` for `/command` and `/api/command`.
- If token is empty, bind only to `127.0.0.1` for local use.
- Do not write tokens into docs, logs, command output, or command events.

## Rendering Rules

V1 can render command output as text.

Minimum:

- Preserve line breaks.
- Use a scrollable result panel.
- Show command status: success/failure.
- Show whether the command was saved to `command_events`.
- Show confirmation warning for writes.

P1:

- Markdown rendering for tables and sections.
- Decision Ticket visual card.
- Links from Decision Ticket to decision detail/history.
- Candidate insight action buttons.

## Data Model

No new table is required for V1 if `command_events` is sufficient.

Use:

- `command_events.command`
- `command_events.ok`
- `command_events.message`
- `command_events.sender = 'web'`
- `command_events.source = 'web-command-console'`

Optional schema extension only if needed later:

- `command_events.classification_json`
- `command_events.requires_confirmation`
- `command_events.confirmed_by_user`

Avoid schema changes in V1 unless the existing event table cannot support the history panel.

## DingTalk Alignment

Update DingTalk Stream command guard to use the same shared classifier.

Acceptance:

- `决策 000660 KR` is treated as `decision_write`.
- If Stream write mode or sender allowlist is missing, DingTalk blocks it with an accurate message.
- Query commands still run directly.
- Website and DingTalk disagree only when the configured surface policy intentionally differs.

## Implementation Plan

### Step 1: Shared Command Classification

Work:

- Add `command_access.py`.
- Move surface policy decisions out of DingTalk-specific code.
- Keep existing helper functions stable for compatibility.

Acceptance:

- Existing query/write classifier tests continue passing.
- `决策 000660 KR` is classified as write.
- Ordinary natural conversation is `unknown`, not candidate write.

### Step 2: Web Command API

Work:

- Add `POST /api/command`.
- Run `handle_command(..., include_artifact_path=false)`.
- Record command event with `source='web-command-console'`.
- Implement confirmation-required response for write commands.

Acceptance:

- Query command returns a result immediately.
- Write command returns `requires_confirmation` unless confirmed.
- Confirmed `决策 SYMBOL MARKET` saves a Decision Ticket.

### Step 3: Command Console Page

Work:

- Add `GET /command`.
- Add input, templates, result panel, recent commands.
- Add confirmation modal for write commands.

Acceptance:

- User can run `决策 000660 KR` from the website after confirmation.
- User can run `决策详情 000660 KR` without confirmation.
- Result panel can display long Decision Ticket output without layout breaking.

### Step 4: Weekly Review Navigation Integration

Work:

- Add Command Console link to existing web shell.
- Keep Weekly Review behavior unchanged.
- Optionally add "Open in Command Console" links from weekly review missing-decision prompts.

Acceptance:

- Existing `/weekly-review` tests still pass.
- `/command` is reachable from the web nav.

### Step 5: DingTalk Guard Alignment

Work:

- Replace duplicated DingTalk Stream write guard with shared classification.
- Update blocked-command message to include decision commands.

Acceptance:

- DingTalk and Web classify command types consistently.
- Decision write commands are not accidentally blocked as "unknown" or allowed as query.

## Verification

Local validation:

```bash
POSTGRES_PORT=55433 .venv/bin/python -B scripts/smoke_test.py
```

Add smoke coverage:

- `/command` HTML contains command input and templates.
- `/api/command` query command succeeds.
- `/api/command` write command returns `requires_confirmation` when not confirmed.
- `/api/command` confirmed decision command succeeds and can be found in decision history.
- Ordinary natural text does not create candidate insight.
- DingTalk Stream classification includes decision write commands.

Manual acceptance:

1. Open `/command`.
2. Run `决策详情 000660 KR`; it should execute immediately.
3. Run `决策 000660 KR`; it should ask for confirmation.
4. Confirm; it should save a Decision Ticket.
5. Run `查看决策历史 000660 KR`; the new ticket should appear.
6. Open `/weekly-review`; decision ticket coverage should reflect saved decisions.

## Rollout

Local:

- Start the existing web service.
- Visit `http://127.0.0.1:8010/command`.

Cloud:

- Deploy behind the existing weekly-review web service.
- Require token if exposed beyond localhost.
- Do not expose high-risk operations in templates.

## Risks

| Risk | Mitigation |
| --- | --- |
| Website becomes an unguarded write surface. | Confirmation gate and shared command classification. |
| DingTalk and Web behavior diverge. | Shared `command_access.py`. |
| Long command output breaks layout. | Scrollable preformatted result panel. |
| User expects every command to have a polished UI. | Label this as Command Console V1 and expose templates first. |
| Sensitive ops commands are too easy to run. | Hide ops templates and require admin mode. |
| Ordinary chat text becomes memory. | Keep ambient capture disabled and test it. |

## Open Questions

- Should `/command` live inside `weekly_review_web.py` for speed, or become a renamed broader `workbench_web.py` service?
- Should confirmed write commands require only a frontend confirmation, or should some commands require token/admin mode as well?
- Should command history show failed commands by default?
- Should command outputs be rendered as Markdown in V1, or kept as safe plain text first?

## Recommendation

Implement this in one pass.

Reason:

- The core command engine already exists.
- The web server pattern already exists.
- The safety classifiers already mostly exist.
- The scope is bounded if V1 stays a console with templates and confirmation, not a full bespoke UI for every workflow.
