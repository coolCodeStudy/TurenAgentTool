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
| Weekly review generator | [`PRD-每周复盘.md`](../product/PRD-每周复盘.md) | ready | [`weekly-review.md`](../techplans/weekly-review.md) | needs_review | needs_review | needs_review | Current implementation and cloud/product acceptance state need review against the original PRD and later weekly-review docs. | Audit implementation evidence and update status. |
| Weekly review web workbench | [`周复盘Web工作台产品文档.md`](../product/周复盘Web工作台产品文档.md) | superseded | [`weekly-review-web-workbench.md`](../techplans/weekly-review-web-workbench.md) | superseded | needs_review | needs_review | Historical date-range and draft/finalized wording is superseded by the natural-week force-refresh contract. | Keep historical status notes; audit current web implementation against current contract. |
| Weekly review natural week and force refresh | [`PRD-weekly-review-week-scope-and-force-refresh.md`](../product/PRD-weekly-review-week-scope-and-force-refresh.md) | superseded | [`weekly-review-week-scope-force-refresh.md`](../techplans/weekly-review-week-scope-force-refresh.md) | ready | needs_review | needs_review | Product PRD is historical; accepted current behavior is in the tech plan status note. Implementation evidence still needs audit. | Verify current behavior and update implementation/evidence status. |
| Command Workbench | [`PRD-command-workbench.md`](../product/PRD-command-workbench.md) | ready | missing | missing | not_started | none | PRD exists; technical plan and implementation evidence are not registered. | Create a technical plan before implementation. |
| Daily market review | [`PRD-Daily-Market-Review.md`](../product/PRD-Daily-Market-Review.md) | ready | missing | missing | not_started | none | PRD now includes product-level provider requirements and an initial provider ladder; live coverage, credentials, and technical plan are not registered. | Hand off to the technical owner or Development Agent for provider coverage checks and technical planning. |
| Researcher Agent local runtime | [`PRD-Researcher-Agent.md`](../product/PRD-Researcher-Agent.md) | ready | [`researcher-agent-local-runtime.md`](../techplans/researcher-agent-local-runtime.md) | ready | not_started | none | Product and technical contracts exist; implementation has not started. V1 is explicitly local-first and does not require cloud worker deployment. | Implement local runner, artifact contract, manual provider, and smoke verification. |
| Stock valuation research | [`PRD-Stock-Valuation-Research.md`](../product/PRD-Stock-Valuation-Research.md) | draft | missing | missing | not_started | none | PRD includes unresolved provider and implementation decisions. | Resolve open product/source decisions, then create technical plan. |
| Research display Level 1 decision card | Product context needs review | needs_review | [`task3-research-display-decision-card.md`](../techplans/task3-research-display-decision-card.md) | ready | needs_review | needs_review | Technical plan exists, but linked PRD/product source is not explicit in the registry. | Link to product source and audit implementation evidence. |
| Cloud worker execution location | Product context needs review | needs_review | [`task2-cloud-worker-execution-location.md`](../techplans/task2-cloud-worker-execution-location.md) | ready | needs_review | needs_review | Technical plan exists; product document and implementation evidence need audit. | Link product source and verify worker execution evidence. |
| Cloud pull deploy | Product context needs review | needs_review | [`cloud-pull-deploy-plan.md`](../techplans/cloud-pull-deploy-plan.md) | needs_review | needs_review | needs_review | Deployment-control-plane work has multiple durable lessons and may be partially implemented. | Audit current Ops API behavior, deploy events, and docs. |
| Control plane and throughput | Product context needs review | needs_review | [`control-plane-and-throughput-plan.md`](../techplans/control-plane-and-throughput-plan.md) | needs_review | needs_review | needs_review | Scope and implementation status need audit. | Review plan checklist and current MCP/Ops capabilities. |

## Audit Queues

### Incomplete PRDs

- Stock valuation research: PRD exists but provider and implementation decisions remain open.
- Research display Level 1 decision card: product source needs explicit linkage.
- Cloud worker execution location: product source needs explicit linkage.
- Cloud pull deploy: product context needs explicit linkage.
- Control plane and throughput: product context needs explicit linkage.

### Ready PRDs Without Registered Implementation Completion

- Weekly review generator.
- Weekly review natural week and force refresh.
- Command Workbench.
- Daily market review.
- Researcher Agent local runtime.

### Technical Plans Without Registered Implementation Completion

- `docs/techplans/weekly-review.md`
- `docs/techplans/weekly-review-week-scope-force-refresh.md`
- `docs/techplans/task3-research-display-decision-card.md`
- `docs/techplans/task2-cloud-worker-execution-location.md`
- `docs/techplans/cloud-pull-deploy-plan.md`
- `docs/techplans/control-plane-and-throughput-plan.md`
- `docs/techplans/researcher-agent-local-runtime.md`

### Stale Or Superseded Documents To Watch

- `docs/product/周复盘Web工作台产品文档.md`
- `docs/techplans/weekly-review-web-workbench.md`
- `docs/product/PRD-weekly-review-week-scope-and-force-refresh.md`

These documents already contain status notes. Keep them as historical context unless a future audit identifies missing or misleading status notes.
