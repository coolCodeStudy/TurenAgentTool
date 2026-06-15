# Repository Knowledge Index

This file helps agents quickly find the repository's durable knowledge. It is not a new source of truth; it is a reading and maintenance map.

## Required Entry Points

| Purpose | Read First |
| --- | --- |
| Start any non-trivial task | `AGENTS.md`, `docs/Agent协作工作流规范.md` |
| Understand current system state | `docs/当前工程状态.md` |
| Understand product direction | `docs/product/产品战略与路线图.md`, `docs/product/产品Agent工作协议.md` |
| Understand the main technical architecture | `docs/技术方案.md`, `docs/MCP工具设计.md`, `docs/数据模型.md` |
| Understand a specific planned feature | `docs/techplans/*.md` and the related `docs/product/*.md` |
| Understand deployment and cloud runtime | `DEPLOYMENT.md`, `docs/阿里云最小部署清单.md`, `docs/Ops诊断与CodexApp接入方案.md` |
| Understand git push, deployment loop, and credential boundaries | `docs/Agent协作工作流规范.md`, `docs/agent-lessons.md`, `docs/techplans/cloud-pull-deploy-plan.md` |
| Understand why the project evolved this way | `docs/project-history.md` |
| Avoid repeated agent mistakes | `docs/agent-lessons.md` |

## Documentation Language

All repository documentation should be written in English. New docs and substantive edits must use English, including product docs, tech plans, status updates, project history, and agent lessons.

Allowed exceptions:

- Chinese command examples or user-facing product phrases that are part of actual system behavior.
- Source quotes or source titles that were originally Chinese.
- Existing filenames and domain terms that would become less clear if translated.
- Legacy Chinese docs only until they are translated or substantially edited.

## Product Knowledge

Product knowledge answers: why build it, for whom, and to what level of completeness.

Canonical locations:

- `docs/product/产品战略与路线图.md`
- `docs/product/产品Agent工作协议.md`
- `docs/product/PRD-*.md`
- `docs/product/*产品文档.md`

Maintenance rules:

- When product direction changes, update product strategy or product decisions.
- Before a new feature enters development, it should have a PRD, product doc, or a tech plan with clear product scope.
- Do not confuse technical feasibility with product value.

## Technical Knowledge

Technical knowledge answers: how the system works, where the boundaries are, and how to verify it.

Canonical locations:

- `docs/技术方案.md`
- `docs/MCP工具设计.md`
- `docs/数据模型.md`
- `docs/techplans/*.md`
- `db/schema.sql`

Maintenance rules:

- Update the relevant document when data models, API contracts, or deployment shape change.
- Tech plans should preserve goals, non-goals, architecture, validation, risks, and follow-ups.
- Runtime facts should go into the database or current-state docs, not into stale tech plans.

## Engineering And Operations Knowledge

Engineering knowledge answers: what currently runs, how to validate locally, and how to deploy.

Canonical locations:

- `docs/当前工程状态.md`
- `DEPLOYMENT.md`
- `docs/阿里云最小部署清单.md`
- `docs/Ops诊断与CodexApp接入方案.md`
- `docker-compose.yml`
- `docker-compose.prod.yml`

Maintenance rules:

- Current capabilities, recommended next steps, and known limits belong in `docs/当前工程状态.md`.
- Update deployment docs when deployment methods or service boundaries change.
- Important completed capabilities belong in `docs/project-history.md`.

## Agent Experience Knowledge

Agent experience knowledge answers: how future Codex sessions should work faster and more safely.

Canonical locations:

- `AGENTS.md`
- `docs/Agent协作工作流规范.md`
- `docs/agent-lessons.md`

Maintenance rules:

- Hard operating rules belong in `AGENTS.md`.
- Workflow, role boundaries, and closeout rules belong in `docs/Agent协作工作流规范.md`.
- Reusable lessons belong in `docs/agent-lessons.md`.
- Git push and PAT handling are remote credential boundaries. Approved push/deploy flows may read `/Users/lishaocheng/code/github_pat` ephemerally, but agents must not search the user's home directory for token files, must never use one-shot Git credential helpers or Keychain prompts, and must never display, persist, or write the PAT into docs, logs, or remotes.
- Do not create routine diary logs.

## Business Knowledge Base

Business knowledge answers: what the user, portfolio, securities, sectors, sources, and insights are.

Canonical locations:

- PostgreSQL knowledge base.
- Research draft review and import flow.
- `candidate_insights` and `user_insights`.
- `docs/个股研究草稿协议.md`
- `docs/个股录入工作流.md`

Maintenance rules:

- Sourced market facts may enter formal knowledge.
- Explicit user views may enter formal user insights.
- Model-inferred views must go through candidate insights.
- Missing data should be recorded as a limitation; do not silently expand scope into imports.

## End-Of-Task Index Update Check

Before ending any non-trivial task, ask:

- Did this task change which document future agents should read? If yes, update this index.
- Did this task add durable product or technical facts? If yes, update the relevant source of truth.
- Did this task create a working rule future agents should follow? If yes, update the workflow standard or agent lessons.
- Did this task create business knowledge useful for future analysis? If yes, write it to the knowledge base, formal insights, or candidate insights.
