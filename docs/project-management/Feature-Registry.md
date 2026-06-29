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
| Delivery coordination system | [`Delivery-Coordinator-Protocol.md`](../product/Delivery-Coordinator-Protocol.md) | ready | not_applicable | not_applicable | local_verified | test_passed | pending | Coordinator protocol, feature-specific audit, handoff packet generation, dispatch prompt generation, Delivery Queue, and delivery audit script are in place; future automation can turn frequent coordinator actions into skills or commands. | Use `python3 scripts/audit_delivery_state.py`, `--feature`, `--handoff-packet`, and `--dispatch-prompt` for delivery coordination; record actual dispatches in Delivery Queue. |
| Project management agent protocol | [`Project-Management-Agent-Protocol.md`](../product/Project-Management-Agent-Protocol.md) | ready | not_applicable | not_applicable | local_verified | test_passed | pending | PM protocol is linked to the delivery audit script and current registry/acceptance queues; future audits may still refine individual feature statuses. | Use `python3 scripts/audit_delivery_state.py` and `python3 scripts/audit_prd_status.py --review` for PM audits. |
| Weekly review generator | [`PRD-每周复盘.md`](../product/PRD-每周复盘.md) | ready | [`weekly-review.md`](../techplans/weekly-review.md) | partially_implemented | deployed | test_passed | accepted | Core weekly review generation, persistence, command path, and web surface exist. 2026-06-28 source-completeness branch `origin/codex/weekly-review-source-completeness` at `ce36764` was integrated into `main` through `8147cb8`; follow-up cloud-source branch `origin/codex/weekly-review-cloud-sources` at `31aa130` was integrated through `9381a1a` and full-deployed by GitHub Actions run `28326950490`. Acceptance retest `AT-2026-06-28-001` failed on 2026-06-28 because event/story evidence was still reference-only rather than dated external company/theme/macro evidence. Development branch `origin/codex/weekly-review-dated-events` at `f40718baebca90dbbc909c44a0f0c208b866f8f4` was integrated into `main` as `4fd1008`, full-deployed by GitHub Actions run `28328183696`, and force-refreshed with evidence at `/private/tmp/weekly-review-cloud-dated-events-20260622.json`. Independent Acceptance retest on 2026-06-29 passed `AT-2026-06-28-001`. A later user correction found the live report had old missing-source output after subsequent main pushes, so Coordinator full-deployed latest `main` commit `37c1060` with run `28383104668` and force-refreshed week `2026-06-22` again; evidence `/private/tmp/weekly-review-20260622-after-full-deploy-refresh.json` has source-backed Yahoo index fallback, 10 dated Yahoo Finance RSS company/theme event rows, source-to-claim citations, and the required seven-part story. `macro_calendar` remains visible as partial, Futu index data remains unavailable, `ChiNext Index`/`STAR 50` are missing, and full-context Web save may need a payload-size follow-up. User requested P1 holder-level attribution on 2026-06-30 because P/L-only drag/contribution rows do not explain likely stock-specific causes, such as Shenghong Technology `HK.02476` rumor and upstream-cost-pressure candidates. Product scope is now defined in the 2026-06-30 PRD addendum: top contributors/laggards need cause candidates, evidence/source/date, confidence labels, thesis impact, next validation, and rumor/social handling that does not launder rumors into facts. Development/Ops returned branch `codex/weekly-review-holder-attribution` with a tech-plan update, structured `holder_attribution[]`, source/confidence classification, Markdown/Web attribution cards, and local fixture coverage for `HK.02476` rumor/cost-driver separation plus provider-missing fallback. | User accepted Weekly Review V1 on 2026-06-29 with known minor gaps. Next owner is Coordinator: inspect and integrate `codex/weekly-review-holder-attribution`, deploy/force-refresh Weekly Review, then move `AT-2026-06-30-001` to `needs_retest` and dispatch Acceptance Testing if cloud evidence is adequate. Track the full-context Web save payload-size issue as a separate Web-flow follow-up if Product keeps it in scope. |
| Weekly review web workbench | [`周复盘Web工作台产品文档.md`](../product/周复盘Web工作台产品文档.md) | superseded | [`weekly-review-web-workbench.md`](../techplans/weekly-review-web-workbench.md) | superseded | deployed | deploy_verified | not_required | Historical arbitrary-range and draft/finalized wording should not be implemented as written; current authority is the natural-week force-refresh contract. | Do not implement the historical plan verbatim; use it only for layout/product-shape context. |
| Weekly review natural week and force refresh | [`PRD-weekly-review-week-scope-and-force-refresh.md`](../product/PRD-weekly-review-week-scope-and-force-refresh.md) | superseded | [`weekly-review-week-scope-force-refresh.md`](../techplans/weekly-review-week-scope-force-refresh.md) | partially_implemented | deployed | test_passed | pending | P0 natural-week Web contract is deployed and acceptance-tested for read existing, generate missing, explicit force refresh, and save without regeneration. Token usage metadata columns exist, but provider-level token accounting and external source integrations remain follow-up scope. | User acceptance remains pending for the deployed P0 Web flow; keep P1 external data providers and token-cost views as separate follow-up work. |
| Command Workbench | [`PRD-command-workbench.md`](../product/PRD-command-workbench.md) | ready | [`command-workbench.md`](../techplans/command-workbench.md) | implemented | deployed | deploy_verified | pending | Bounded V1 is implemented for registry-backed parsing, preview, candidate selection, confirmation guards, `/command` UI, workbench APIs, and Level 1 decision-card execution. Cloud acceptance is served at `:8010/command` because `command-api` runs internally but `:8001` is not publicly reachable. Decision-ticket/history actions recover explicitly because only Level 1 decision cards exist today. Full smoke test was blocked by local PostgreSQL `localhost:55432` being unavailable. User acceptance is still pending; do not mark accepted until the user verifies the behavior. | Keep cloud `:8010/command` available for user acceptance; revisit separate decision-ticket/history scope if product still requires it. |
| Stock valuation research | [`PRD-Stock-Valuation-Research.md`](../product/PRD-Stock-Valuation-Research.md) | draft | missing | missing | not_started | none | pending | PRD includes unresolved provider and implementation decisions. | Resolve open product/source decisions, then create technical plan. |
| Kline Agent | [`PRD-Kline-Agent.md`](../product/PRD-Kline-Agent.md) | ready | missing | missing | not_started | none | pending | PRD exists; no technical plan or implementation evidence is registered. | Create a technical plan for V1 single-stock Kline investigation before implementation. |
| Research display Level 1 decision card | Product context needs review | needs_review | [`task3-research-display-decision-card.md`](../techplans/task3-research-display-decision-card.md) | implemented | deployed | deploy_verified | pending | Product source should still be linked explicitly, but the technical plan itself is implemented: default stock display is Level 1 and verbose/detail paths preserve evidence. | Add/identify the product source if this becomes a product-facing roadmap item; no implementation follow-up is currently blocking. |
| Cloud worker execution location | Product context needs review | needs_review | [`task2-cloud-worker-execution-location.md`](../techplans/task2-cloud-worker-execution-location.md) | implemented | deployed | deploy_verified | not_required | Product source should still be linked explicitly, but the technical plan is implemented and project history records a real ASML cloud-worker validation sample. | Keep worker health and queue observability under normal operations; no implementation follow-up is currently blocking. |
| Cloud pull deploy | Product context needs review | needs_review | [`cloud-pull-deploy-plan.md`](../techplans/cloud-pull-deploy-plan.md) | implemented | deployed | deploy_verified | not_required | Pull-based Ops API deploy is the current daily deploy path; remaining lessons are operational hardening rather than the original plan being unfinished. | Keep using `/ops/deploy quick` as the default release path; track future Ops API hardening separately. |
| Control plane and throughput | Product context needs review | needs_review | [`control-plane-and-throughput-plan.md`](../techplans/control-plane-and-throughput-plan.md) | partially_implemented | deployed | code_reference | not_required | P0/P1 control-plane pieces exist (`system_overview`, coding tasks, task events, deploy events, worker status), but later task-event depth, research concurrency/layering, and structural refactors remain open. | Split remaining P2-P5 work into narrower tech plans before implementation. |

## Audit Queues

### Incomplete PRDs

- Stock valuation research: PRD exists but provider and implementation decisions remain open.
- Research display Level 1 decision card: product source needs explicit linkage, but implementation is not currently blocking.
- Cloud worker execution location: product source needs explicit linkage, but implementation is not currently blocking.
- Cloud pull deploy: product context needs explicit linkage, but implementation is not currently blocking.
- Control plane and throughput: product context needs explicit linkage and remaining P2-P5 scope should be split.

### Ready PRDs Without Registered Implementation Completion

- Weekly review natural week and force refresh.
- Command Workbench.
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
