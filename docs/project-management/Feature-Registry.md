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

- `not_started`
- `in_progress`
- `local_verified`
- `deployed`
- `accepted`
- `blocked`
- `needs_review`

Evidence status:

- `none`
- `code_reference`
- `test_passed`
- `deploy_verified`
- `user_accepted`
- `needs_review`

## Registry

| Feature | Product Doc | PRD Status | Technical Plan | Technical Status | Implementation | Evidence | Known Gaps | Next Action |
|---|---|---|---|---|---|---|---|---|
| Product strategy and product-agent protocol | [`Product-Strategy-and-Roadmap.md`](../product/Product-Strategy-and-Roadmap.md), [`Product-Agent-Working-Protocol.md`](../product/Product-Agent-Working-Protocol.md) | ready | not_applicable | not_applicable | accepted | user_accepted | No active technical implementation expected. | Keep updated when product direction changes. |
| Project management agent protocol | [`Project-Management-Agent-Protocol.md`](../product/Project-Management-Agent-Protocol.md) | ready | not_applicable | not_applicable | in_progress | code_reference | Registry is newly created and has not completed a full repository audit. | Run the first full project-management audit and refine statuses. |
| Weekly review generator | [`PRD-每周复盘.md`](../product/PRD-每周复盘.md) | ready | [`weekly-review.md`](../techplans/weekly-review.md) | partially_implemented | deployed | deploy_verified | Core weekly review generation, persistence, command path, and web surface exist; external index, macro, news/theme, and opportunity sources remain incomplete. | Keep current implementation; track missing external-source integrations as follow-up product/tech work. |
| Weekly review web workbench | [`周复盘Web工作台产品文档.md`](../product/周复盘Web工作台产品文档.md) | superseded | [`weekly-review-web-workbench.md`](../techplans/weekly-review-web-workbench.md) | superseded | deployed | deploy_verified | Historical arbitrary-range and draft/finalized wording should not be implemented as written; current authority is the natural-week force-refresh contract. | Do not implement the historical plan verbatim; use it only for layout/product-shape context. |
| Weekly review natural week and force refresh | [`PRD-weekly-review-week-scope-and-force-refresh.md`](../product/PRD-weekly-review-week-scope-and-force-refresh.md) | superseded | [`weekly-review-week-scope-force-refresh.md`](../techplans/weekly-review-week-scope-force-refresh.md) | partially_implemented | in_progress | code_reference | Current web API still regenerates through `build_weekly_review(...)` instead of fully separating read, generate, force refresh, and save-without-regeneration semantics. | Finish the natural-week read/generate/refresh/save API contract before treating weekly-review web as product-done. |
| Command Workbench | [`PRD-command-workbench.md`](../product/PRD-command-workbench.md) | ready | missing | missing | not_started | none | PRD exists; technical plan and implementation evidence are not registered. | Create a technical plan before implementation. |
| Stock valuation research | [`PRD-Stock-Valuation-Research.md`](../product/PRD-Stock-Valuation-Research.md) | draft | missing | missing | not_started | none | PRD includes unresolved provider and implementation decisions. | Resolve open product/source decisions, then create technical plan. |
| Kline Agent | [`PRD-Kline-Agent.md`](../product/PRD-Kline-Agent.md) | ready | missing | missing | not_started | none | PRD exists; no technical plan or implementation evidence is registered. | Create a technical plan for V1 single-stock Kline investigation before implementation. |
| Research display Level 1 decision card | Product context needs review | needs_review | [`task3-research-display-decision-card.md`](../techplans/task3-research-display-decision-card.md) | implemented | deployed | deploy_verified | Product source should still be linked explicitly, but the technical plan itself is implemented: default stock display is Level 1 and verbose/detail paths preserve evidence. | Add/identify the product source if this becomes a product-facing roadmap item; no implementation follow-up is currently blocking. |
| Cloud worker execution location | Product context needs review | needs_review | [`task2-cloud-worker-execution-location.md`](../techplans/task2-cloud-worker-execution-location.md) | implemented | deployed | deploy_verified | Product source should still be linked explicitly, but the technical plan is implemented and project history records a real ASML cloud-worker validation sample. | Keep worker health and queue observability under normal operations; no implementation follow-up is currently blocking. |
| Cloud pull deploy | Product context needs review | needs_review | [`cloud-pull-deploy-plan.md`](../techplans/cloud-pull-deploy-plan.md) | implemented | deployed | deploy_verified | Pull-based Ops API deploy is the current daily deploy path; remaining lessons are operational hardening rather than the original plan being unfinished. | Keep using `/ops/deploy quick` as the default release path; track future Ops API hardening separately. |
| Control plane and throughput | Product context needs review | needs_review | [`control-plane-and-throughput-plan.md`](../techplans/control-plane-and-throughput-plan.md) | partially_implemented | deployed | code_reference | P0/P1 control-plane pieces exist (`system_overview`, coding tasks, task events, deploy events, worker status), but later task-event depth, research concurrency/layering, and structural refactors remain open. | Split remaining P2-P5 work into narrower tech plans before implementation. |

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
