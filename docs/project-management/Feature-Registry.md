# Feature Registry

This registry tracks delivery state across product documents, technical plans, implementation, verification, deployment, and acceptance.

Use `docs/product/Project-Management-Agent-Protocol.md` for status definitions and audit rules. Update this file when a PRD, technical plan, implementation state, verification state, deployment state, or next action changes.

## Status Values

PRD status:

- `missing`
- `draft`
- `ready`
- `superseded`
- `deprecated`

Technical plan status:

- `missing`
- `draft`
- `ready`
- `partially_implemented`
- `implemented`
- `superseded`
- `not_applicable`

Implementation status:

- `not_applicable`
- `not_started`
- `in_progress`
- `local_verified`
- `deployed`
- `blocked`
- `needs_review`

Evidence status:

- `none`
- `doc_reference`
- `code_reference`
- `test_passed`
- `deploy_verified`
- `needs_review`

User acceptance status:

- `not_required`
- `pending`
- `accepted`
- `rejected`
- `needs_reacceptance`

## Registry

| Feature | Product Doc | PRD Status | Technical Plan | Technical Status | Implementation | Evidence | User Acceptance | Known Gaps | Next Action |
|---|---|---|---|---|---|---|---|---|---|
| Product strategy and product-agent protocol | [`Product-Strategy-and-Roadmap.md`](../product/Product-Strategy-and-Roadmap.md), [`Product-Agent-Working-Protocol.md`](../product/Product-Agent-Working-Protocol.md) | ready | not_applicable | not_applicable | not_applicable | doc_reference | accepted | No active technical implementation expected. | Keep updated when product direction changes. |
| Delivery coordination system | [`Agent-Operating-Model.md`](../product/Agent-Operating-Model.md), [`Delivery-Coordinator-Protocol.md`](../product/Delivery-Coordinator-Protocol.md) | ready | not_applicable | not_applicable | local_verified | test_passed | pending | Agent Operating Model, Coordinator protocol, feature-specific audit, handoff packet generation, dispatch prompt generation, Delivery Queue, and delivery audit script are in place. Current V1 is repo-native docs plus script constraints; future automation can turn frequent coordinator actions into hooks, skills, or commands. | Use `python3 scripts/audit_delivery_state.py`, `--feature`, `--handoff-packet`, and `--dispatch-prompt` for delivery coordination; record actual dispatches in Delivery Queue; use Agent Operating Model for multi-role escalation and completion gates. |
| Project management agent protocol | [`Project-Management-Agent-Protocol.md`](../product/Project-Management-Agent-Protocol.md) | ready | not_applicable | not_applicable | local_verified | test_passed | pending | PM protocol is linked to the delivery audit script and current registry/acceptance queues; future audits may still refine individual feature statuses. | Use `python3 scripts/audit_delivery_state.py` and `python3 scripts/audit_prd_status.py --review` for PM audits. |
| Weekly review generator | [`PRD-每周复盘.md`](../product/PRD-每周复盘.md) | ready | [`weekly-review.md`](../techplans/weekly-review.md) | partially_implemented | deployed | test_passed | needs_reacceptance | Core weekly review generation, persistence, command path, and web surface exist. 2026-06-28 source-completeness branch `origin/codex/weekly-review-source-completeness` at `ce36764` was integrated into `main` through `8147cb8`; follow-up cloud-source branch `origin/codex/weekly-review-cloud-sources` at `31aa130` was integrated through `9381a1a` and full-deployed by GitHub Actions run `28326950490`. Acceptance retest `AT-2026-06-28-001` failed on 2026-06-28 because event/story evidence was still reference-only rather than dated external company/theme/macro evidence. Development branch `origin/codex/weekly-review-dated-events` at `f40718baebca90dbbc909c44a0f0c208b866f8f4` was integrated into `main` as `4fd1008`, full-deployed by GitHub Actions run `28328183696`, and force-refreshed with evidence at `/private/tmp/weekly-review-cloud-dated-events-20260622.json`. Independent Acceptance retest on 2026-06-29 passed `AT-2026-06-28-001`. A later user correction found the live report had old missing-source output after subsequent main pushes, so Coordinator full-deployed latest `main` commit `37c1060` with run `28383104668` and force-refreshed week `2026-06-22` again; evidence `/private/tmp/weekly-review-20260622-after-full-deploy-refresh.json` has source-backed Yahoo index fallback, 10 dated Yahoo Finance RSS company/theme event rows, source-to-claim citations, and the required seven-part story. `macro_calendar` remains visible as partial, Futu index data remains unavailable, `ChiNext Index`/`STAR 50` are missing, and full-context Web save may need a payload-size follow-up. User requested P1 holder-level attribution on 2026-06-30 because P/L-only drag/contribution rows do not explain likely stock-specific causes, such as Shenghong Technology `HK.02476` rumor and upstream-cost-pressure candidates. Product scope is now defined in the 2026-06-30 PRD addendum: top contributors/laggards need cause candidates, evidence/source/date, confidence labels, thesis impact, next validation, and rumor/social handling that does not launder rumors into facts. Development/Ops branch `codex/weekly-review-holder-attribution` was integrated to `main` as `e9d6c85`, automatic push deploy run `28387773202` and manual full deploy run `28388039486` both succeeded, and independent Acceptance retest `AT-2026-06-30-001` passed with minor severity on 2026-06-30 SGT. Cloud evidence includes `/private/tmp/weekly-review-at-holder-read-20260630.json`, `/private/tmp/weekly-review-at-holder-page-20260630.html`, and `/private/tmp/weekly-review-at-holder-summary-20260630.json`; `HK.02476` shows source gaps instead of invented Q2-miss or cost-pressure causes when real cloud sources are absent. Minor gap: Markdown position/trade evidence exposes the source label `account_snapshots_and_trade_records`; change it to product-language copy in a follow-up if Product wants a clean user-facing source label before P1 user review. | User accepted Weekly Review V1 on 2026-06-29 with known minor gaps; do not treat that as user acceptance for the P1 holder-attribution follow-up. Next owner is user reacceptance: ask the user to review P1 holder-level attribution with the minor Markdown source-label gap disclosed; route the source-label cleanup later if Product keeps it in scope. Track the full-context Web save payload-size issue as a separate Web-flow follow-up if Product keeps it in scope. |
| Weekly review web workbench | [`周复盘Web工作台产品文档.md`](../product/周复盘Web工作台产品文档.md) | superseded | [`weekly-review-web-workbench.md`](../techplans/weekly-review-web-workbench.md) | superseded | deployed | deploy_verified | not_required | Historical arbitrary-range and draft/finalized wording should not be implemented as written; current authority is the natural-week force-refresh contract. | Do not implement the historical plan verbatim; use it only for layout/product-shape context. |
| Weekly review natural week and force refresh | [`PRD-weekly-review-week-scope-and-force-refresh.md`](../product/PRD-weekly-review-week-scope-and-force-refresh.md) | superseded | [`weekly-review-week-scope-force-refresh.md`](../techplans/weekly-review-week-scope-force-refresh.md) | partially_implemented | deployed | test_passed | pending | P0 natural-week Web contract is deployed and acceptance-tested for read existing, generate missing, explicit force refresh, and save without regeneration. Token usage metadata columns exist, but provider-level token accounting and external source integrations remain follow-up scope. | User acceptance remains pending for the deployed P0 Web flow; keep P1 external data providers and token-cost views as separate follow-up work. |
| Command Workbench | [`PRD-command-workbench.md`](../product/PRD-command-workbench.md) | ready | [`command-workbench.md`](../techplans/command-workbench.md) | implemented | deployed | deploy_verified | pending | Bounded V1 is implemented for registry-backed parsing, preview, candidate selection, confirmation guards, `/command` UI, workbench APIs, Level 1 decision-card execution, and P0 missing-stock bootstrap for valid symbols absent from stock profiles. Cloud acceptance is served at `:8010/command` because `command-api` runs internally but `:8001` is not publicly reachable. User feedback on 2026-06-30 found `MSTR`/`US.LRCX` dead-ended because they were not in stock profiles; main commit `24888e8` added confirmed minimal stock-profile initialization and deployed through GitHub Actions run `28444397520`. Coordinator cloud evidence `/tmp/command-workbench-bootstrap-cloud-20260630.json` verified `/command` 200, missing/invalid token 401 recovery, `决策 MSTR`/`决策 US.LRCX` bootstrap previews before initialization, successful initialization events #164/#165, and successful post-bootstrap decision executions #168/#169. Independent Acceptance retest `AT-2026-06-25-002` on 2026-06-30 failed major because `决策 阿里` silently selected `HK.09988` instead of showing ambiguous Alibaba candidates required by the PRD; main commit `5c87850` restored ambiguous alias candidates, deployed through GitHub Actions run `28445609707`, and Coordinator cloud evidence `/tmp/command-workbench-alibaba-fix-cloud-20260630.json` verified `决策 阿里` returns `ambiguous_entity` with `HK.09988` and `US.BABA` while `MSTR`/`US.LRCX` still parse to decision cards. Passing retest coverage included browser rendering, auth recovery, token secrecy, Intel decision preview/run, initialized MSTR/LRCX decision preview/run, fresh-symbol bootstrap preview, confirmation guard for weekly review, read-only system status, and unsupported free-text guard. Full local smoke remains limited in this coordinator worktree because `.venv/bin/python` is unavailable. User acceptance is still pending. User feedback on 2026-06-30 found that bootstrap-only stocks such as `US.LRCX` can still show a technically successful but low-information decision card; main commit `d978704` deployed through GitHub Actions run `28449368020` and evidence `/tmp/command-workbench-thin-profile-cloud-20260630.json` verified these now route to confirmed research-job creation. Coordinator cloud execution then exposed and fixed a downstream research-worker blocker: commits `f05e86c` and `4b39382` deployed through GitHub Actions runs `28450414955` and `28451026306`; LRCX job #44 imported with audit pass, and `/tmp/command-workbench-lrcx-decision-after-import-20260630.json` verified post-import `决策 US.LRCX` returns a research-backed decision card with `Evidence: 3 sources, 14 facts, audit pass` and no minimal-profile placeholder. Independent Acceptance retest `AT-2026-06-25-002` passed on 2026-06-30 SGT against deployed main commit `4b39382`; evidence includes `/tmp/command-workbench-at2-api-summary-20260630-at2.json`, `/tmp/command-workbench-at2-page-20260630.html`, `/tmp/command-workbench-at2-token-leak-scan-20260630.txt`, and `/tmp/command-workbench-at2-internal-string-scan-20260630.txt`. User acceptance remains pending. | Next owner is Delivery Coordinator for Coordinator Return Gate: accept the passed independent retest, disclose the in-app screenshot tooling limitation if needed, and ask the user for Command Workbench acceptance only after preserving user acceptance as pending until the user explicitly accepts. |
| Stock valuation research | [`PRD-Stock-Valuation-Research.md`](../product/PRD-Stock-Valuation-Research.md) | ready | [`stock-valuation-research.md`](../techplans/stock-valuation-research.md) | implemented | deployed | deploy_verified | needs_reacceptance | P0 single-stock command flow is implemented and cloud-deployed through combined release `658bbfc` / Ops deploy event `#41`; independent cloud-IP acceptance previously passed `AT-2026-07-01-001`. User acceptance feedback on 2026-07-04 showed the `US.INTC` valuation card was too thin because the implemented P0 only used existing local stock context and did not fetch fresh provider data. P0.1 now adds a US provider-backed valuation packet in this branch: SEC EDGAR company facts for official financial metrics and Yahoo quote data for low-cost market snapshots, merged into deterministic calculations and saved artifacts with source labels and provider-gap degraded behavior. Provider-backed official filings and fresh market snapshots are no longer pure follow-up for US stocks; peer multiples, analyst estimates, normalized valuation tables, async refresh, and user-confirmed valuation-case workflow remain follow-up scope. | Next owner is Global Project Manager via `DQ-2026-07-04-010`: produce a combined release ref that preserves Command Workbench access setup, Kline behavior, and the Stock valuation P0.1 provider-backed packet. Do not deploy this coordinator branch directly. After combined release deploy, keep `AT-2026-07-01-001` at `needs_retest` and redispatch independent cloud-IP Acceptance Testing before asking for final user acceptance. |
| Kline Agent | [`PRD-Kline-Agent.md`](../product/PRD-Kline-Agent.md) | ready | missing | missing | not_started | none | pending | PRD exists; no technical plan or implementation evidence is registered. | Create a technical plan for V1 single-stock Kline investigation before implementation. |
| Research display Level 1 decision card | Product context needs review | needs_review | [`task3-research-display-decision-card.md`](../techplans/task3-research-display-decision-card.md) | implemented | deployed | deploy_verified | pending | Product source should still be linked explicitly, but the technical plan itself is implemented: default stock display is Level 1 and verbose/detail paths preserve evidence. | Add/identify the product source if this becomes a product-facing roadmap item; no implementation follow-up is currently blocking. |
| Cloud worker execution location | Product context needs review | needs_review | [`task2-cloud-worker-execution-location.md`](../techplans/task2-cloud-worker-execution-location.md) | implemented | deployed | deploy_verified | not_required | Product source should still be linked explicitly, but the technical plan is implemented and project history records a real ASML cloud-worker validation sample. | Keep worker health and queue observability under normal operations; no implementation follow-up is currently blocking. |
| Cloud pull deploy | Product context needs review | needs_review | [`cloud-pull-deploy-plan.md`](../techplans/cloud-pull-deploy-plan.md) | implemented | deployed | deploy_verified | not_required | Pull-based Ops API deploy is the current daily deploy path; remaining lessons are operational hardening rather than the original plan being unfinished. | Keep using `/ops/deploy quick` as the default release path; track future Ops API hardening separately. |
| Control plane and throughput | Product context needs review | needs_review | [`control-plane-and-throughput-plan.md`](../techplans/control-plane-and-throughput-plan.md) | partially_implemented | deployed | code_reference | not_required | P0/P1 control-plane pieces exist (`system_overview`, coding tasks, task events, deploy events, worker status), but later task-event depth, research concurrency/layering, and structural refactors remain open. | Split remaining P2-P5 work into narrower tech plans before implementation. |

## Audit Queues

### Incomplete PRDs

- Research display Level 1 decision card: product source needs explicit linkage, but implementation is not currently blocking.
- Cloud worker execution location: product source needs explicit linkage, but implementation is not currently blocking.
- Cloud pull deploy: product context needs explicit linkage, but implementation is not currently blocking.
- Control plane and throughput: product context needs explicit linkage and remaining P2-P5 scope should be split.

### Ready PRDs Without Registered Implementation Completion

- Weekly review natural week and force refresh.
- Command Workbench.
- Stock valuation research.
- Kline Agent.

### Technical Plans Without Registered Implementation Completion

- `docs/techplans/weekly-review-week-scope-force-refresh.md`
- `docs/techplans/control-plane-and-throughput-plan.md`

### Implemented Or Superseded Technical Plans

- `docs/techplans/task2-cloud-worker-execution-location.md`: implemented and deployed; no longer treat as open implementation debt.
- `docs/techplans/task3-research-display-decision-card.md`: implemented and deployed; no longer treat as open implementation debt.
- `docs/techplans/cloud-pull-deploy-plan.md`: implemented and deployed as the current daily release path; future hardening should be tracked separately.
- `docs/techplans/weekly-review-web-workbench.md`: superseded; do not implement its arbitrary-range or draft/finalized workflow wording verbatim.

### Stale Or Superseded Documents To Watch

- `docs/product/周复盘Web工作台产品文档.md`
- `docs/techplans/weekly-review-web-workbench.md`
- `docs/product/PRD-weekly-review-week-scope-and-force-refresh.md`

These documents already contain status notes. Keep them as historical context unless a future audit identifies missing or misleading status notes.
