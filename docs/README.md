# Documentation Map

This directory contains product decisions, technical plans, operating notes, and historical reference material for InvestmentKnowledge.

The documentation is intentionally split by decision type:

- `docs/product/`: product strategy, role protocols, and PRDs. Use this for product intent, scope, non-goals, user flows, and acceptance criteria.
- `docs/techplans/`: implementation plans. Use this for module-level design, rollout constraints, verification, and deployment impact.
- `docs/project-management/`: delivery tracking. Use this for PRD readiness, technical-plan links, implementation status, evidence status, and next actions.
- Root `docs/*.md`: durable reference documents, operational notes, historical architecture, data model notes, and workflow guides.

## Current Source Of Truth

| Topic | Current document |
|---|---|
| Agent operating rules | [`../AGENTS.md`](../AGENTS.md) |
| Product strategy | [`product/Product-Strategy-and-Roadmap.md`](product/Product-Strategy-and-Roadmap.md) |
| Delivery-coordinator protocol | [`product/Delivery-Coordinator-Protocol.md`](product/Delivery-Coordinator-Protocol.md) |
| Product-agent protocol | [`product/Product-Agent-Working-Protocol.md`](product/Product-Agent-Working-Protocol.md) |
| Project-management protocol | [`product/Project-Management-Agent-Protocol.md`](product/Project-Management-Agent-Protocol.md) |
| Acceptance-testing protocol | [`product/Acceptance-Testing-Agent-Protocol.md`](product/Acceptance-Testing-Agent-Protocol.md) |
| Feature delivery registry | [`project-management/Feature-Registry.md`](project-management/Feature-Registry.md) |
| Acceptance queue | [`project-management/Acceptance-Queue.md`](project-management/Acceptance-Queue.md) |
| Current engineering state | [`当前工程状态.md`](当前工程状态.md) |
| Durable project milestones | [`project-history.md`](project-history.md) |
| Lesson capture protocol | [`lesson-capture-protocol.md`](lesson-capture-protocol.md) |
| Durable agent lessons | [`agent-lessons.md`](agent-lessons.md) |
| Multi-session Codex workflow | [`codex-session-workflow.md`](codex-session-workflow.md) |
| Cloud pull deploy contract | [`techplans/cloud-pull-deploy-plan.md`](techplans/cloud-pull-deploy-plan.md) |
| Weekly-review current implementation contract | [`techplans/weekly-review-week-scope-force-refresh.md`](techplans/weekly-review-week-scope-force-refresh.md) |

## Product Documents

Product docs should be used before technical planning. They answer what the product should do and how it will be accepted.

Active product references:

- [`product/Product-Strategy-and-Roadmap.md`](product/Product-Strategy-and-Roadmap.md)
- [`product/Delivery-Coordinator-Protocol.md`](product/Delivery-Coordinator-Protocol.md)
- [`product/Product-Agent-Working-Protocol.md`](product/Product-Agent-Working-Protocol.md)
- [`product/Project-Management-Agent-Protocol.md`](product/Project-Management-Agent-Protocol.md)
- [`product/Acceptance-Testing-Agent-Protocol.md`](product/Acceptance-Testing-Agent-Protocol.md)
- [`product/PRD-command-workbench.md`](product/PRD-command-workbench.md)
- [`product/PRD-Stock-Valuation-Research.md`](product/PRD-Stock-Valuation-Research.md)
- [`product/PRD-Kline-Agent.md`](product/PRD-Kline-Agent.md)
- [`product/PRD-每周复盘.md`](product/PRD-每周复盘.md)

Historical or partially superseded product context:

- [`product/周复盘Web工作台产品文档.md`](product/周复盘Web工作台产品文档.md)
- [`product/PRD-weekly-review-week-scope-and-force-refresh.md`](product/PRD-weekly-review-week-scope-and-force-refresh.md)

These weekly-review documents are intentionally kept because they preserve product reasoning. Read their status notes before using them as implementation authority.

## Technical Plans

Technical plans should be used after product scope is clear. They answer how the product should be implemented and verified.

Current or active implementation contracts:

- [`techplans/weekly-review-week-scope-force-refresh.md`](techplans/weekly-review-week-scope-force-refresh.md)
- [`techplans/cloud-pull-deploy-plan.md`](techplans/cloud-pull-deploy-plan.md)
- [`techplans/control-plane-and-throughput-plan.md`](techplans/control-plane-and-throughput-plan.md)
- [`techplans/task2-cloud-worker-execution-location.md`](techplans/task2-cloud-worker-execution-location.md)
- [`techplans/task3-research-display-decision-card.md`](techplans/task3-research-display-decision-card.md)

Historical implementation context:

- [`techplans/weekly-review.md`](techplans/weekly-review.md)
- [`techplans/weekly-review-web-workbench.md`](techplans/weekly-review-web-workbench.md)

## Root Reference Docs

Root-level docs are not all equal. Some are current durable references; others are historical foundation documents. Status notes at the top of individual files should clarify whether they are current authority or background context.

Current durable references:

- [`当前工程状态.md`](当前工程状态.md)
- [`project-history.md`](project-history.md)
- [`lesson-capture-protocol.md`](lesson-capture-protocol.md)
- [`agent-lessons.md`](agent-lessons.md)
- [`codex-session-workflow.md`](codex-session-workflow.md)
- [`Ops诊断与CodexApp接入方案.md`](Ops诊断与CodexApp接入方案.md)
- [`富途持仓接入.md`](富途持仓接入.md)
- [`个股研究草稿协议.md`](个股研究草稿协议.md)
- [`个股录入工作流.md`](个股录入工作流.md)

Historical or foundational references:

- [`MVP路线图.md`](MVP路线图.md)
- [`技术方案.md`](技术方案.md)
- [`数据模型.md`](数据模型.md)
- [`MCP工具设计.md`](MCP工具设计.md)
- [`消息入口设计.md`](消息入口设计.md)
- [`阿里云最小部署清单.md`](阿里云最小部署清单.md)
- [`Agent工作模式演进计划.md`](Agent工作模式演进计划.md)

These files are useful for context, but current implementation decisions should be checked against `AGENTS.md`, `docs/product/`, `docs/techplans/`, `docs/project-management/Feature-Registry.md`, code, and deployment evidence.

## Cleanup Rules

- Do not delete historical docs only because they are superseded.
- Prefer adding status notes and source-of-truth links before moving files.
- Move files only when links and references are updated in the same change.
- New substantial product work should have a PRD under `docs/product/`.
- New substantial implementation work should have a technical plan under `docs/techplans/`.
- Delivery state should be tracked in `docs/project-management/Feature-Registry.md`.
- Broad delivery-state, readiness, handoff, and acceptance gaps should be checked with `python3 scripts/audit_delivery_state.py`.
- Completed substantial tasks should follow `lesson-capture-protocol.md` and either record durable lessons in the right document or state why there was no durable lesson.
