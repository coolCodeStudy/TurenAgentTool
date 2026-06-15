# Documentation Map

This is the front door for repository documentation. Start here before reading individual docs.

## How To Use This Map

1. Read `AGENTS.md` first for repository operating rules.
2. Read this file to choose the right document path.
3. Read `docs/DOCUMENTATION-GOVERNANCE.md` before creating, moving, renaming, or retiring docs.
4. Update this map when adding a new long-lived document or changing which document is canonical.

## Canonical Project State

| Need | Canonical Source |
| --- | --- |
| Current implementation state and recommended next steps | `docs/当前工程状态.md` |
| Durable milestones and historical turns | `docs/project-history.md` |
| Reusable agent lessons | `docs/agent-lessons.md` |
| Documentation lifecycle and anti-rot rules | `docs/DOCUMENTATION-GOVERNANCE.md` |

## Product Documents

Read `docs/product/README.md` first for product docs.

| Need | Canonical Source |
| --- | --- |
| Product strategy and roadmap | `docs/product/Product-Strategy-and-Roadmap.md` |
| Product-agent behavior | `docs/product/Product-Agent-Working-Protocol.md` |
| Stock valuation research product | `docs/product/PRD-Stock-Valuation-Research.md` |
| Weekly review product | `docs/product/PRD-每周复盘.md` and `docs/product/周复盘Web工作台产品文档.md` |

Notes:

- English product docs are preferred.
- Existing Chinese filenames may remain until a deliberate rename/migration pass updates all references.
- Chinese command examples and user-facing product phrases may remain when they are actual system behavior.

## Architecture And Domain Design

| Need | Source |
| --- | --- |
| Overall technical architecture | `docs/技术方案.md` |
| Data model | `docs/数据模型.md` |
| MCP tool design | `docs/MCP工具设计.md` |
| Message entrypoints | `docs/消息入口设计.md` |
| Stock research draft protocol | `docs/个股研究草稿协议.md` |
| Stock onboarding workflow | `docs/个股录入工作流.md` |
| Futu holdings integration | `docs/富途持仓接入.md` |

## Operations And Deployment

| Need | Source |
| --- | --- |
| Deployment guide | `DEPLOYMENT.md` |
| Minimal Alibaba Cloud setup | `docs/阿里云最小部署清单.md` |
| Ops diagnostics and Codex App integration | `docs/Ops诊断与CodexApp接入方案.md` |
| Cloud pull deploy plan | `docs/techplans/cloud-pull-deploy-plan.md` |
| Hermes integration plan | `docs/Hermes接入方案.md` |
| Agent runtime evolution plan | `docs/Agent工作模式演进计划.md` |

## Tech Plans

Read `docs/techplans/README.md` first for tech-plan status.

| Plan | Status |
| --- | --- |
| `docs/techplans/weekly-review.md` | Active/product feature plan |
| `docs/techplans/weekly-review-web-workbench.md` | Active/Web workbench plan |
| `docs/techplans/cloud-pull-deploy-plan.md` | Active/deployment-control-plane plan |
| `docs/techplans/control-plane-and-throughput-plan.md` | Active/control-plane roadmap |
| `docs/techplans/task2-cloud-worker-execution-location.md` | Worker/research-pipeline plan |
| `docs/techplans/task3-research-display-decision-card.md` | Display-layer plan |

## Retired Or Lower-Priority Areas

| Area | How To Treat |
| --- | --- |
| Daily work logs | Retired. Do not create routine daily logs. |
| Hermes-first runtime | Not the current primary runtime path; keep as reference unless revived. |
| Broad docs translation | Do incrementally. Do not mass-edit docs without a focused branch and review. |

## Anti-Rot Checklist

When finishing non-trivial work, decide whether to update:

- `docs/当前工程状态.md` for current facts.
- `docs/project-history.md` for durable milestones.
- `docs/agent-lessons.md` for reusable mistakes and operating lessons.
- A product doc if product behavior changed.
- A tech plan if implementation scope, status, or acceptance changed.
- This `docs/README.md` if the canonical reading path changed.

