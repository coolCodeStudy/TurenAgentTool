# Agent Collaboration Workflow Standard

This file is the top-level collaboration protocol for Codex and other agents working in this repository. Its purpose is not ceremony; it gives each session a clear role, expected artifacts, verification standard, and knowledge-retention duty.

## Principles

- Choose the role before acting: do not mix product, architecture, engineering, operations, and research work into one blurry flow.
- Documentation is the source of truth: product decisions go under `docs/product/`, technical plans go under `docs/techplans/` or architecture docs, and current engineering facts go in `docs/当前工程状态.md`.
- Repository documentation must be written in English. Do not add new Chinese prose to docs except for command examples, user-facing product phrases, source quotes, filenames, or domain terms that must stay as-is.
- Engineering work should close the loop by default: code, local tests, commit, deploy, remote test, and fix again if remote validation fails, unless the user explicitly asks only for design or local edits.
- Both the business system and the development agent should become smarter over time. Every task must end with a decision about whether to preserve knowledge, lessons, state, or milestones.
- Do not treat model inference as a confirmed user view. Explicit user preferences may become formal insights; model-inferred views must go through candidate insights.

## Session Routing

For every non-trivial task, the agent should:

1. Run `.venv/bin/python scripts/agent_preflight.py`.
2. Check `git status --short` and identify existing dirty changes.
3. Decide which workflow applies.
4. Read the relevant product docs, tech plans, or current-state docs.
5. Briefly tell the user which workflow will be used.

If the right document is unclear, start with `docs/Repo知识库索引.md`.

| User Intent | Default Workflow | Main Artifact |
| --- | --- | --- |
| Product direction, UX, requirements, pages, or workflows | Product design | PRD, product doc, product decision |
| Module boundaries, data model, APIs, deployment shape, async tasks | Technical architecture | Tech plan, architecture diagram, data/API contract |
| Implement a feature, fix a bug, optimize behavior | Engineering execution | Code, tests, commit, deployment, remote validation |
| Check production status, logs, or deployment failures | Ops diagnosis | Status summary, root cause, fix plan or fix commit |
| Add stock, sector, portfolio, or investment knowledge | Research/knowledge base | Sources, facts, candidate insights, or formal insights |

If the user asks for a complete engineering loop, full execution, launch, deploy, or deployment validation, default to the engineering execution workflow.

## Workflow 1: Product Design

Use this when:

- The user proposes a new product capability, experience, page, entrypoint, or review flow.
- The user is dissatisfied with the current product direction and wants it redefined.
- Engineering would be premature because goals, scope, or acceptance criteria are unclear.

Required reading:

- `docs/product/产品Agent工作协议.md`
- `docs/product/产品战略与路线图.md`
- Any directly related PRD or product document

Default steps:

1. Restate the real user problem and target scenario.
2. Judge whether the idea serves the current product strategy and north-star goal.
3. Define goals, non-goals, user stories, and the core flow.
4. Break down scope, priority, and acceptance criteria.
5. Clarify data needs, entrypoints, permissions, and risk warnings.
6. Update or create product documentation.
7. If the work is ready for implementation, produce a tech plan or engineering task.

Standard product doc locations:

- Product strategy: `docs/product/产品战略与路线图.md`
- Product agent protocol: `docs/product/产品Agent工作协议.md`
- Feature PRDs: `docs/product/PRD-*.md`
- Page/workbench docs: `docs/product/*产品文档.md`
- Product decisions: `docs/product/产品决策记录.md`

Completion standard:

- The user problem and product goal are clear.
- Scope and non-goals are clear.
- Acceptance criteria can be verified by engineering.
- It is clear which conclusions need to flow into a technical plan.

## Workflow 2: Technical Architecture

Use this when:

- The product direction is mostly clear, but implementation path, module boundaries, or data contracts are not.
- The work touches database schema, MCP tools, HTTP APIs, workers, deployment, permissions, or security boundaries.
- A technical plan will reduce rework before implementation.

Default steps:

1. Read the related PRD, existing tech plans, data model, and relevant code entrypoints.
2. Write the background, goals, non-goals, and constraints.
3. Define module boundaries, data flow, API contracts, error handling, and permission boundaries.
4. Clarify migration, compatibility, deployment, and rollback strategy.
5. Define local validation, remote validation, and acceptance checks.
6. Update or create `docs/techplans/*.md`.
7. If implementation can begin, provide the engineering execution order.

Standard technical doc locations:

- Feature tech plans: `docs/techplans/*.md`
- Long-lived architecture: `docs/技术方案.md`, `docs/MCP工具设计.md`, `docs/数据模型.md`
- Deployment and ops: `DEPLOYMENT.md`, `docs/阿里云最小部署清单.md`
- Current factual state: `docs/当前工程状态.md`

Completion standard:

- An engineer can implement from the document without guessing product intent.
- Database, APIs, permissions, failure paths, and verification are explicit.
- Non-goals are stated so scope does not quietly expand.

## Workflow 3: Engineering Execution Loop

Use this when:

- The user asks to implement, fix, optimize, launch, or "just do it."
- Existing PRDs or tech plans are sufficient to guide development.
- The user explicitly asks for execution through deployment validation.

Default loop:

1. Preflight: run preflight and confirm git status and database target.
2. Context: read relevant PRDs, tech plans, current state, and touched code.
3. Plan: for larger tasks, write a short plan; for small tasks, proceed directly.
4. Code: follow existing repository patterns and protect user-owned dirty changes.
5. Local test: run narrow checks first, then `scripts/smoke_test.py` or the touched entrypoint when appropriate.
6. Commit: after local validation, commit only task-related changes with a clear message.
7. Deploy: if the user requested a complete engineering loop or explicit launch, deploy within the documented service boundaries.
8. Remote test: inspect cloud status, logs, health checks, or the user-specified entrypoint.
9. Fix loop: if remote validation fails, repeat code, test, commit, deploy, and remote test until it passes or a real blocker is reached.
10. Closeout: preserve knowledge and summarize the result.

Engineering boundaries:

- The default deployment path is MCP `cloud_deploy(ref=<commit_sha>, mode="quick"|"full")` calling ECS Ops API `/ops/deploy`. GitHub Actions is a formal release, full rebuild backup, and disaster-recovery path unless the user explicitly requests it.
- If the user asks for deploy validation after a change, including phrases such as "deploy after fixing", "deploy validate", or `改完部署验证`, treat it as standing authorization for low-risk task-scoped commit, push, `/ops/deploy`, and remote validation. Do not ask again unless the change is high-risk, destructive, touches secrets, changes production data, or expands service/database scope.
- Do not treat "verify" as permission to start the full production compose stack. Service startup must follow `AGENTS.md`.
- Before deployment, state the services, database, ports, and external integrations involved.
- Remote push, remote deployment, and credential-sensitive operations need explicit user authorization, the standing low-risk deploy-validation authorization, or approved controlled tools.
- If the database lacks data, record it as an environment limitation instead of expanding scope into imports.
- If the user asked only for local implementation, do not deploy by default.

### Git Push And Credential Flow

When the engineering loop needs to push code to a remote:

1. Confirm `git status --short` and stage/commit only task-related files.
2. Create the commit after local validation passes.
3. State the branch/ref that will be pushed and whether it may trigger GitHub Actions or deployment side effects.
4. Run `git push` if the user has requested push/deploy/deploy-validation in this task, if the standing low-risk deploy-validation rule applies, or if the user explicitly approves it.
5. If deployment is needed after push, use `cloud_deploy(ref=<commit_sha>, mode="quick"|"full")` and ECS Ops API `/ops/deploy` by default. Use GitHub Actions only when the user requests it or the change requires the formal/full-rebuild release path.
6. Validate remote status, logs, or entrypoints after deployment.

Credential rules:

- Never display or commit tokens, PATs, SSH private keys, or `.env` secrets.
- The GitHub PAT file for this machine is `/Users/lishaocheng/code/github_pat`.
- Do not search the user's home directory for token files. Use only the explicitly documented `/Users/lishaocheng/code/github_pat` path when PAT auth is needed.
- When this task has authorized `git push` or deploy, and the remote Git operation needs GitHub authentication, `/Users/lishaocheng/code/github_pat` may be read ephemerally for that single operation.
- Never use one-shot or inline Git credential helpers such as `git -c credential.helper=...`, `GIT_ASKPASS`, or helper shell functions to pass the PAT.
- Never trigger or rely on `git-credential-osxkeychain` / macOS Keychain prompts for repository pushes. If a push asks for Keychain access or an interactive GitHub username/password, stop and fix the non-interactive PAT push flow instead.
- Never write a PAT into a Git remote URL, documentation, logs, commit messages, command output, or chat summaries.
- Prefer configured Git credential helpers, `gh` auth state, deploy keys, GitHub Actions secrets, or controlled deployment tools; read `/Users/lishaocheng/code/github_pat` only when those are unavailable or the local push flow specifically needs it.

Completion standard:

- Code is implemented.
- Test commands and outcomes are clear.
- Commit, deployment, and remote validation are done when required.
- Failures and environment limitations are explicit.
- Documentation and knowledge retention are complete.

## Workflow 4: Learning And Knowledge Retention

Before ending any non-trivial task, perform a closeout decision. The goal is to make both the business system and future development sessions smarter.

### What The Development Agent Learned

Write durable development knowledge to:

- Operating rules: `AGENTS.md`
- Reusable lessons: `docs/agent-lessons.md`
- Current engineering facts: `docs/当前工程状态.md`
- Phase milestones: `docs/project-history.md`
- Active implementation plans: `docs/techplans/*.md`
- Repository knowledge map: `docs/Repo知识库索引.md`

Language rule:

- Write new or substantially edited documentation in English.
- If touching an older Chinese document, translate the touched section or add the new content in English.
- Keep Chinese only when it is a command example, user-facing phrase, source quote, filename, or required domain term.

Preserve a lesson when:

- The task reveals a repeatable verification, deployment, database, permission, or tooling pitfall.
- The task completes an engineering capability that changes future development paths.
- Product direction, architecture direction, or recommended next steps change.
- A tech plan's status, scope, or acceptance result changes.

Do not preserve:

- Ordinary formatting tweaks.
- One-off logs or temporary command output.
- Debugging details with no long-term value.

### What The Business System Learned

Write durable business knowledge to:

- Stock/sector facts: sources plus `add_knowledge_item`-style tools.
- Explicit user investment preferences: `record_user_insight` or the formal insight flow.
- Model-inferred views: candidate insights only, pending user confirmation.
- Research drafts: the research draft review and import flow.

Preserve business knowledge when:

- The user explicitly states an investment principle, risk preference, position-sizing rule, or view on a security.
- The task produces sourced facts about a company, sector, industry, or market.
- A review creates a judgment that should be checked again next time.
- A candidate insight is confirmed or rejected in a way that affects future analysis.

Do not:

- Write model guesses as formal user insights.
- Write unsourced market facts into formal knowledge.
- Create routine diary-style work logs just to show activity.

## Closeout Checklist

Before ending, check each question:

| Question | Action If Yes |
| --- | --- |
| Did product direction or requirements change? | Update `docs/product/` |
| Did the technical plan, API, or data model change? | Update `docs/techplans/` or architecture docs |
| Did the current engineering state change? | Update `docs/当前工程状态.md` |
| Did we learn a reusable lesson? | Update `docs/agent-lessons.md`, and `AGENTS.md` if needed |
| Did we reach a phase milestone? | Update `docs/project-history.md` |
| Did the user express a formal investment view? | Record a formal user insight |
| Did the model produce an investment judgment that needs confirmation? | Create a candidate insight |
| Is there a new sourced fact? | Write it to the knowledge base and link the source |

Final responses should include:

- What changed.
- How it was verified.
- Whether commit/deploy/remote validation happened.
- Which docs or knowledge were preserved.
- Remaining risks or next steps.

## Role Switching Rules

- Product design may produce engineering tasks, but do not jump into code unless the user asks to continue.
- Technical architecture may surface product questions, but should not expand product scope for the user.
- If engineering execution discovers a product or architecture gap, fill the smallest necessary documentation gap before continuing.
- Ops diagnosis may enter the engineering execution loop if it finds a code defect.
- Research/knowledge tasks must distinguish formal insights from candidate insights when user views are involved.

## Recommended Commands

Prefer narrow local validation:

```bash
.venv/bin/python scripts/smoke_test.py
.venv/bin/python scripts/ikg.py "分析 000660 KR"
.venv/bin/python scripts/ikg.py "查看候选心得"
```

Remote and service validation should run only when the user explicitly requests it or the affected surface requires it.
