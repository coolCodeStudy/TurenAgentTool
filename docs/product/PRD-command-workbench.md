# PRD: Command Workbench

## 1. Background

The current `/command` page is useful for operators who already know exact InvestmentKnowledge command syntax, but it is confusing for normal product usage.

The failure case is simple:

```text
决策 英特尔
```

The user intent is clear: they want a decision workflow for Intel. The system fails because the command router expects a narrower syntax such as:

```text
决策 US.INTC
```

This creates a poor middle state:

- If `/command` is an intelligent input surface, its supported intent and entity understanding are too narrow.
- If `/command` is a traditional command interface, it does not provide clear structured fields, command syntax, usage hints, or selectable objects.

The product should stop presenting `/command` as a raw text box that sometimes behaves intelligently. It should become a command workbench: a command-palette-style surface with entity resolution, structured fallbacks, and explicit confirmation before execution.

## 2. Industry Research Summary

### 2.1 Command Palettes: Fast But Discoverable

Microsoft PowerToys Command Palette positions itself as a fast single interface for launching apps, running commands, searching files, browsing the web, and using extensions. Its documentation emphasizes typed invocation, discoverable capabilities, pinned/home commands, prefixes for special modes, and extensibility.

Source: [PowerToys Command Palette overview](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/overview)

Raycast follows a similar pattern: incremental search predicts the intended action, results can be lists or detail views, and each result can expose more than one action.

Source: [Raycast overview](https://en.wikipedia.org/wiki/Raycast_%28software%29)

Product implication for InvestmentKnowledge:

- A command surface should show likely actions while the user types.
- The user should not need to memorize exact syntax.
- Repeated commands should be visible as recent/pinned actions.
- A selected result should expose the exact action that will run.

### 2.2 Slash Commands: Structured But Less Forgiving

Slack slash commands intentionally require a structure: a command name plus a text payload. Slack's developer documentation also highlights usage hints, command descriptions, and interactive responses such as buttons or menus. It also warns that slash commands are less universally usable than other entry points because of their required invocation structure.

Source: [Slack slash command documentation](https://docs.slack.dev/interactivity/implementing-slash-commands/)

Product implication for InvestmentKnowledge:

- If a command requires syntax, the UI must show usage hints before execution.
- The system should acknowledge and respond with helpful next steps instead of a dead-end error.
- Interactive follow-up is part of the command experience, not an afterthought.

### 2.3 Menu And Command Design: Put Known Actions Where Users Can Find Them

Menu-system research suggests that command hierarchies should reduce time spent searching in irrelevant areas and make group labels predictive of what users will find inside them.

Source: [Foraging-based Optimization of Menu Systems](https://arxiv.org/abs/2005.01292)

Product implication for InvestmentKnowledge:

- `/command` needs grouped action discovery, not only a blank text area.
- Common investment actions should be grouped by user goal: decision, portfolio, weekly review, system status, research.
- Recent and suggested actions should adapt to the user's actual workflow.

## 3. Product Positioning

`/command` should be:

> A keyboard-first operation workbench for InvestmentKnowledge that accepts natural shortcuts, resolves investment entities, previews the exact command, and requires confirmation for risky actions.

It should not be:

- A general AI chat box.
- A raw CLI wrapper.
- A place where unknown free text is executed.
- A replacement for dedicated pages such as weekly review or portfolio analysis.

## 4. User Problem

The user wants to operate the investment system quickly without remembering exact command syntax.

Common examples:

```text
决策 英特尔
刷新海力士决策
看一下阿里
本周复盘
系统状态
```

Today the page handles exact commands but fails on common human phrasing. The failure message explains that the website command console will not execute unknown text, but it does not help the user complete the task.

## 5. Product Goals

1. Let the user execute common InvestmentKnowledge actions without memorizing exact command syntax.
2. Resolve common stock names, aliases, and symbols into canonical `market.symbol` targets.
3. Use deterministic parsing and LLM-assisted semantic parsing together so natural input feels intelligent without becoming unsafe.
4. Make the exact command preview visible before execution.
5. Keep safety boundaries: write-like, maintenance, or high-impact actions must require explicit confirmation.
6. Preserve the command console's operator value for advanced users.

## 6. Non-Goals

- Do not build a general-purpose investment chatbot in this feature.
- Do not allow arbitrary unknown text to reach command execution.
- Do not replace the command router's controlled allowlist.
- Do not let LLM output execute directly. LLM output is only a structured parse proposal that must pass registry, entity resolution, preview, and confirmation checks.
- Do not hide entity ambiguity by guessing silently.

## 7. Product Principles

### 7.1 Parse, Preview, Confirm

Every natural input should move through:

```text
raw input -> intent parse -> entity resolution -> command preview -> confirmation -> execution
```

### 7.2 Intelligent Input Must Declare Its Limits

The page can accept natural shortcuts, but it must show supported action families and examples. The product should not imply that any sentence can be understood.

### 7.3 Traditional Entry Must Exist Beside Smart Input

Users should be able to choose an action from a visible catalog, then fill required fields. Natural input is a shortcut, not the only way to operate.

### 7.4 Unknown Text Is A Recovery Moment

Failure states should help the user recover:

- If intent is unknown, show supported actions.
- If intent is known but required fields are missing, ask for the missing field.
- If entity resolution is ambiguous, show candidates.
- If the action is unsupported on the website, explain where it can be done.

### 7.5 Dangerous Actions Are Never One-Shot Natural Language

Natural language can prepare a risky action, but execution needs a confirmation step with the target, source data, side effects, and expected result.

## 8. Target Users

Primary user:

- The investment system owner who wants quick operation without memorizing exact command syntax.

Secondary users:

- Future agents or operators using the web surface for controlled diagnostics.
- Developers validating command-router behavior through a web UI.

## 9. Core Experience

### 9.1 Page Layout

The `/command` page should be redesigned into four main areas:

| Area | Purpose |
| --- | --- |
| Smart command input | Accepts natural shortcuts and exact commands. |
| Parsed preview | Shows recognized intent, target entity, safety level, and exact command. |
| Action catalog | Provides clickable structured entry points grouped by user goal. |
| Execution result | Shows result, diagnostics, event id, and recovery actions. |

Recommended layout:

```text
Command Workbench

[ Smart input: "决策 英特尔"                         ]

Parsed Preview
- Action: Decision
- Target: Intel Corporation / US.INTC
- Exact command: 决策 US.INTC
- Safety: Read-only decision ticket generation
[Run] [Edit target] [Cancel]

Action Catalog
- Decision: Create decision, refresh decision data, decision detail, decision history
- Portfolio: Portfolio analysis, current positions
- Review: This week review, weekly source diagnostics
- Research: Create research job, list research jobs
- System: System status, recent errors, service logs

Execution Result
...
```

### 9.2 Smart Input Behavior

The smart input should support:

- Exact commands: `决策 000660 KR`
- Human stock-name commands: `决策 英特尔`
- Chinese or English stock aliases: `看一下 阿里`, `decision Intel`
- Abbreviated actions: `刷新海力士`, `系统状态`
- Week shortcuts: `本周复盘`, `上周复盘`, `周复盘数据源诊断`

The input should not execute immediately on Enter unless a unique parsed command is already visible and the action is safe. For consistency, Enter should select/confirm the highlighted preview; high-impact actions still require explicit confirmation.

### 9.3 Entity Resolution

The entity resolver should turn human text into canonical targets.

Examples:

| Input | Expected candidates |
| --- | --- |
| `英特尔` | `Intel Corporation / US.INTC` |
| `海力士` | `SK Hynix / KR.000660` |
| `阿里` | `Alibaba-W / HK.09988`, `Alibaba / US.BABA` |
| `南方两倍做多海力士` | `HK.07709` |

Resolution states:

| State | UI behavior |
| --- | --- |
| Unique match | Show one target in preview. |
| Multiple matches | Show candidate list with market, symbol, name, and recent usage. |
| No match | Ask the user to enter a symbol or search by market. |
| Low confidence | Show "possible match" and require target confirmation. |

### 9.4 Action Catalog

The right-side "common commands" list should become an action catalog. It should not only paste raw text.

Each action should define:

- User-facing label.
- Description.
- Required fields.
- Optional fields.
- Safety level.
- Result type.
- Exact command template.

Example:

```text
Action: Create decision
Required field: Stock
Optional field: Mode
Template: 决策 {symbol} {market}
Safety: Read-only / ticket save, no trade
```

For actions with required fields, clicking the action opens a structured mini-form instead of inserting an incomplete command into the textarea.

### 9.5 Confirmation Model

Confirmation is required when:

- The action writes durable records.
- The action refreshes or overwrites generated content.
- The action triggers external services, schedulers, deployment, or maintenance.
- The parser has low-confidence entity resolution.

Confirmation card should show:

- Action.
- Canonical target.
- Exact command.
- Side effects.
- Data sources involved.
- Expected output.

### 9.6 Result Model

Execution results should be structured, not only plain text.

Minimum result fields:

- Status: success, failed, blocked, needs input.
- Event id or command id.
- Executed exact command.
- Target entity.
- Main result body.
- Diagnostics or missing data.
- Suggested next actions.

Failure examples:

| Failure | Current behavior | Required behavior |
| --- | --- | --- |
| `决策 英特尔` cannot parse | "Cannot recognize command" | "I recognized Decision but need to resolve stock. Did you mean Intel / US.INTC?" |
| `决策 阿里` ambiguous | Failure or wrong guess | Candidate list: HK.09988, US.BABA. |
| Unknown intent | Generic error | Show supported action families and examples. |
| Missing token | Execution failed | Ask for access token and explain where it is used. |

## 10. Supported Action Families

### 10.1 Decision

Complete-version commands:

- Create decision ticket.
- Refresh decision data.
- View decision detail.
- View decision history.
- View decision profile.

Example natural inputs:

```text
决策 英特尔
刷新海力士决策
查看阿里决策历史
decision Intel
```

### 10.2 Portfolio

Complete-version commands:

- Current positions.
- Portfolio analysis.

Example natural inputs:

```text
持仓分析
看当前持仓
```

### 10.3 Weekly Review

Complete-version commands:

- This week review.
- Previous week review.
- Weekly source diagnostics.
- Weekly index diagnostics.

Example natural inputs:

```text
本周复盘
上周复盘
周复盘数据源诊断
```

### 10.4 Research

Complete-version commands:

- Create single-stock research job.
- List research jobs.
- Create portfolio research jobs.

Research commands can enqueue longer asynchronous work, so the command workbench must show the provider, source policy, expected side effect, and confirmation step before creating jobs.

### 10.5 System Diagnostics

Complete-version commands:

- System status.
- Recent errors.
- Worker status.
- Service logs with service selector.

Example natural inputs:

```text
系统状态
最近错误
查看 mcp 日志
```

## 11. Complete Usable Version

This PRD should be implemented as one complete usable version. The product issue is not solved if only one part is delivered: a smart input without structured fallback remains confusing, while a structured command form without natural shortcuts remains a raw operator console.

The complete version includes:

1. Rename the page from raw "Command Console" to "Command Workbench".
2. Replace the large default textarea-first experience with a smart input plus parsed preview.
3. Add a visible action catalog with grouped actions.
4. Add hybrid parser coverage for all supported action families in this PRD: deterministic first for exact and high-confidence paths, LLM-assisted parsing for natural phrasing and low-confidence paths.
5. Add entity resolution for stock names, aliases, and symbols.
6. Add candidate selection for ambiguous entities.
7. Add command preview before execution.
8. Add confirmation cards for write-like or low-confidence actions.
9. Replace generic failures with recovery states.
10. Preserve exact command execution for advanced users.
11. Add structured mini-forms for required fields such as stock, week, service name, provider, or source policy.
12. Add recent and pinned actions.
13. Add result cards for each supported action family, even if the card wraps the existing plain-text command result.
14. Add safe LLM-assisted parsing with a small bounded prompt, structured output, parser confidence, and preview-before-execution.
15. Add token/cost disclosure for commands that may call LLMs or enqueue asynchronous work.
16. Add telemetry for parse outcome, ambiguity, confirmation, execution, and recovery.
17. Keep unsupported or high-risk actions blocked with an explicit explanation.

The version is complete only when a user can finish common tasks from natural input or structured selection without knowing exact command syntax.

## 12. Token And Cost Policy

The command workbench can use LLMs, but the design must keep token use intentional and bounded. The parsing layer should choose the cheapest reliable path:

1. Exact command path: no LLM.
2. Alias/entity path: no LLM when local data gives a high-confidence match.
3. LLM-assisted parse path: use a small prompt when phrasing is natural, incomplete, or low-confidence.
4. Downstream execution path: token use depends on the command being run and must be shown separately.

| Interaction | Expected extra LLM tokens |
| --- | ---: |
| `决策 英特尔` to decision preview | 0 |
| `决策 阿里` to candidate list | 0 |
| Click action catalog and select target | 0 |
| Show command preview and confirmation | 0 |
| Natural phrasing such as `帮我看一下英特尔要不要做` | 400-1,500 |
| Unknown command recovery with semantic explanation | 300-1,000 |

LLM-assisted parsing is part of the complete version. It must use a small bounded context:

- Raw user input.
- Supported action registry summary.
- Candidate entities from local search.
- No full portfolio, full knowledge base, full reports, or long histories.

The LLM output must be a parse proposal, not an executed command. The proposal still goes through registry validation, entity resolution, preview, and confirmation.

Expected parser cost:

| Parser case | Expected prompt size | Expected completion size |
| --- | ---: | ---: |
| Natural phrasing with clear entity | 300-900 tokens | 100-250 tokens |
| Ambiguous command family | 500-1,400 tokens | 100-350 tokens |
| Unsupported request explanation | 300-700 tokens | 100-250 tokens |

Commands that execute downstream LLM work, such as research drafts or generated summaries, must show their own estimated cost separately. The command workbench should not hide downstream token use inside the input experience.

## 13. Functional Requirements

### 13.1 Command Registry

The system must maintain a registry of supported web commands. Each command should include:

- `id`
- `action_family`
- `label`
- `aliases`
- `required_fields`
- `optional_fields`
- `template`
- `safety_level`
- `confirmation_required`
- `result_renderer`

### 13.2 Parser

The parser must return:

- `status`: parsed, needs_entity, ambiguous_entity, needs_field, unsupported.
- `intent`
- `confidence`
- `entities`
- `candidate_commands`
- `recovery_message`

### 13.3 Entity Resolver

The resolver must search:

- Known stock profiles.
- Portfolio holdings.
- Recently used stocks.
- Alias map.
- Exact symbols.
- Market-specific symbols.

### 13.4 Execution Guard

The execution layer must only execute a command if:

- It maps to a registered command.
- Required fields are resolved.
- Confirmation requirements are satisfied.
- The access token, if required, is valid.

Unknown free text must never be sent directly to the command router.

### 13.5 Result Persistence

Recent execution history should store:

- Raw input.
- Parsed intent.
- Exact command.
- Status.
- Timestamp.
- Event id.
- Target entity.

It should not store access tokens.

## 14. UX Copy

### 14.1 Page Subtitle

```text
Type a stock name, symbol, or supported command. The workbench will resolve the target and show the exact command before running it.
```

### 14.2 Empty State

```text
Start with an action or a target.

Examples:
- 决策 英特尔
- 刷新海力士决策
- 本周复盘
- 系统状态
```

### 14.3 Ambiguous Entity

```text
I found multiple matches for "阿里". Choose one target before running the command.
```

### 14.4 Unsupported Command

```text
I cannot run this as a website command yet. Try one of the supported actions below.
```

### 14.5 Confirmation

```text
Run this command?

Action: Create decision ticket
Target: Intel Corporation / US.INTC
Exact command: 决策 US.INTC
Side effect: saves a traceable decision ticket; does not trade.
```

## 15. Safety And Permission Boundaries

- No trading action can be executed from `/command`.
- Durable writes must require explicit confirmation.
- Maintenance actions must show affected service and environment.
- Deployment actions are out of scope for the public command workbench unless protected by a separate admin flow.
- Access tokens must not appear in recent history, logs, or result cards.
- Owner access should optimize for speed: local tooling should provision, sync, and inject the access token automatically. Manual token lookup or copy/paste is only a fallback path.
- Parser confidence must be visible when a command was inferred from natural text.

## 16. Metrics

Product success metrics:

- Parse success rate for supported command families.
- Recovery success rate after ambiguous or incomplete input.
- Percentage of commands run through preview instead of raw exact syntax.
- Number of generic "unknown command" failures per week.
- Time from input to successful execution for common actions.
- Repeat usage of recent/pinned actions.

Quality metrics:

- Wrong-target execution count: should be zero.
- Unconfirmed write execution count: should be zero.
- Unsupported command rate by action family, used to prioritize new actions.

## 17. Acceptance Criteria

1. `决策 英特尔` resolves to Intel / `US.INTC`, shows a preview, and can run the exact decision command after confirmation if required.
2. `决策 阿里` shows candidate targets instead of silently choosing.
3. `本周复盘` routes to the weekly review command or page without requiring exact syntax.
4. `系统状态` runs as a safe read-only command.
5. Clicking "Create decision" in the action catalog opens a structured target input, not an incomplete raw command.
6. Unknown input shows supported action families and examples.
7. Recent executions show raw input, exact command, status, and timestamp.
8. Access token input remains separate from command history.
9. Existing exact commands still work for advanced users.
10. No unsupported free text reaches command execution.
11. A valid market-qualified or uppercase US stock symbol that is not yet in stock profiles, such as `US.MSTR` or `MSTR`, does not dead-end as an unknown command. The workbench offers a confirmed stock-profile initialization path, then lets the user preview the decision command again.
12. A decision command for a stock with only a minimal bootstrap profile and no imported facts/sources must not present an empty decision card as success. It should recover by offering a confirmed research-job creation path and explain that the decision card should be rerun after facts are imported.

## 18. Open Questions

1. Should stock alias management be editable in the UI, or maintained only through stock profiles and code?
2. Should `/command` automatically navigate to dedicated pages such as weekly review, or render all results inline?
3. Should decision-ticket creation require confirmation every time, or only when the target was inferred from natural language?
4. Should the command workbench share the same parser with DingTalk, or should web support richer structured recovery states?

## 19. Product Decision

The command page should evolve from a raw text console into a command workbench.

The key product contract is:

```text
The user can type naturally, but the system only executes registered actions after resolving entities and showing the exact command.
```

This keeps the speed of a command palette, the clarity of structured forms, and the safety required for an investment system.
