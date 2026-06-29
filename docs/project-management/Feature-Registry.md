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
| Weekly review generator | [`PRD-每周复盘.md`](../product/PRD-每周复盘.md) | ready | [`weekly-review.md`](../techplans/weekly-review.md) | partially_implemented | deployed | test_passed | rejected | Core weekly review generation, persistence, command path, and web surface exist. 2026-06-28 fixes align Weekly Review Web read/generate/refresh/save with the natural-week contract, hide internal provider/table strings, and harden weekly save persistence for legacy `report_key`; however user acceptance failed because index and external-event sources are still missing and the overall story remains too thin without source-backed market/event context. The PRD now includes a 2026-06-28 source-completeness addendum defining minimum required index coverage, event/news/theme coverage, evidence freshness, degraded behavior, and story-quality acceptance criteria for `AT-2026-06-28-001`. | Engineering must update `docs/techplans/weekly-review.md` before implementation to cover source providers, fallback/source-status semantics, story-generation inputs, verification, and acceptance criteria; then implement, deploy, and route to Acceptance Testing for a focused `AT-2026-06-28-001` retest. |
| Weekly review web workbench | [`周复盘Web工作台产品文档.md`](../product/周复盘Web工作台产品文档.md) | superseded | [`weekly-review-web-workbench.md`](../techplans/weekly-review-web-workbench.md) | superseded | deployed | deploy_verified | not_required | Historical arbitrary-range and draft/finalized wording should not be implemented as written; current authority is the natural-week force-refresh contract. | Do not implement the historical plan verbatim; use it only for layout/product-shape context. |
| Weekly review natural week and force refresh | [`PRD-weekly-review-week-scope-and-force-refresh.md`](../product/PRD-weekly-review-week-scope-and-force-refresh.md) | superseded | [`weekly-review-week-scope-force-refresh.md`](../techplans/weekly-review-week-scope-force-refresh.md) | partially_implemented | deployed | test_passed | pending | P0 natural-week Web contract is deployed and acceptance-tested for read existing, generate missing, explicit force refresh, and save without regeneration. Token usage metadata columns exist, but provider-level token accounting and external source integrations remain follow-up scope. | User acceptance remains pending for the deployed P0 Web flow; keep P1 external data providers and token-cost views as separate follow-up work. |
| Command Workbench | [`PRD-command-workbench.md`](../product/PRD-command-workbench.md) | ready | [`command-workbench.md`](../techplans/command-workbench.md) | implemented | deployed | deploy_verified | pending | Bounded V1 is implemented for registry-backed parsing, preview, candidate selection, confirmation guards, `/command` UI, workbench APIs, and Level 1 decision-card execution. Cloud acceptance is served at `:8010/command` because `command-api` runs internally but `:8001` is not publicly reachable. Decision-ticket/history actions recover explicitly because only Level 1 decision cards exist today. Full smoke test was blocked by local PostgreSQL `localhost:55432` being unavailable. 2026-06-28 acceptance retest `AT-2026-06-25-002` is blocked, not failed: the page and action catalog are reachable and missing/invalid auth returns 401, but no approved valid cloud command token was available to run token-bearing parse/preview/execute checks. 2026-06-29 product decision: P0 may use one fixed private owner/test token configured outside the repo, stored only in browser localStorage by the `/command` page; multi-user login, OAuth, short-lived token issuance, rotation UI, and separate read/write tokens are P1 follow-ups. User acceptance is still pending; do not mark accepted until the user verifies the behavior after acceptance passes. | Engineering should make the `/command` token UX recoverable for P0 by explaining browser-local token storage and replacing raw missing/invalid-token 401 copy with user-facing recovery text; then the coordinator must provide or route approved command-token access and rerun `AT-2026-06-25-002`. Keep cloud `:8010/command` available for user acceptance after acceptance testing passes. |
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
