# Open-Source Agent Methodology Study: Superpowers And OpenSpec

Date: 2026-07-05

## Purpose

This note reviews two open-source agent-delivery projects and extracts what is useful for TurenAgentTool's repo-native Agent Operating Model:

- [`obra/superpowers`](https://github.com/obra/superpowers)
- [`Fission-AI/OpenSpec`](https://github.com/Fission-AI/OpenSpec)

The goal is not to replace the current `AGENTS.md`, Delivery Coordinator, Feature Registry, Acceptance Queue, and Delivery Queue system. The goal is to identify practices that can reduce owner attention cost, prevent feature-flow drift, and improve multi-agent delivery quality.

## Executive Summary

Both projects validate the direction of this repository's current operating model:

- Work should be artifact-backed, not chat-memory-backed.
- Agents need explicit workflow gates, not vague "do the work" prompts.
- Fresh task context and review gates reduce overbuilding, context pollution, and missed acceptance criteria.
- A change should remain independently understandable after the chat is gone.

The most useful adoption path is hybrid:

- Borrow Superpowers' controller/subagent/reviewer discipline for execution quality.
- Borrow OpenSpec's change-folder and delta-spec discipline for product/technical traceability.
- Keep this repo's existing Feature Registry, Acceptance Queue, Delivery Queue, deploy gate, and user-acceptance model as the authoritative delivery state.

The main repo-specific takeaway is sharper: this repository does not need more agent roles first. It needs better feature/change packaging and stronger return-gate bookkeeping so that multiple coordinators can work in parallel without leaving truth split across branches, chat, and queues.

## Current Repo Fit

### What The Repo Already Has

This repository already has several pieces that overlap with Superpowers and OpenSpec:

- `AGENTS.md` is the mandatory operating guide.
- `docs/product/Agent-Operating-Model.md` defines Owner, Global Project Manager, Feature Coordinator, Product, Development, Acceptance Testing, and Project Management boundaries.
- `docs/product/Delivery-Coordinator-Protocol.md` defines Dispatch Mode, Active Watch Rule, Deploy Intent, Deploy Decision Gate, and Coordinator Return Gate.
- `docs/project-management/Feature-Registry.md` is intended to be the feature truth table.
- `docs/project-management/Acceptance-Queue.md` is intended to be the independent acceptance truth table.
- `docs/project-management/Delivery-Queue.md` is intended to be the active dispatch and return ledger.
- `scripts/audit_delivery_state.py` and `scripts/audit_agent_flow_health.py` are early automation for status and coordinator-health checks.

That means the right move is not a wholesale migration to either open-source system. The current repo already has the organization model. The missing layer is a tighter "change package" and "coordinator ledger" that makes each active feature resumable and reviewable without reading several long chat threads.

### Current Gaps Observed In This Repo

The repo has recently shown several operating-model failure modes:

- Feature Coordinators sometimes dispatch a child role but stop after the child returns instead of applying the Return Gate, deploying, retesting, or dispatching the next owner.
- Feature branches can be pushed and even deployed while omitting another active feature's behavior, causing Kline/Stock/Command Workbench release-line clobbers.
- Some coordinator returns contain the right evidence but leave the next deploy/retest owner vague.
- Portfolio truth can become branch-dependent. In the current checked-out branch, `Feature-Registry.md` still shows Kline Agent and Stock valuation research as much less advanced than the recent coordinator/release work, while active release branches contain newer truth. This is a concrete example of why accepted changes need to be folded back into the shared truth quickly.
- The Delivery Queue is useful but long rows are doing too much: dispatch record, return ledger, deploy intent, release notes, and next action are collapsed into a single table cell.
- The user still has to notice when coordinators are idle, when returns are not closed, or when deploy/retest is the obvious next step.

### What Superpowers Teaches For This Repo

Superpowers' strongest fit is not "install these skills". It is the controller discipline:

- The Feature Coordinator should act like the controller for one feature.
- Child Product/Development/Test agents should get focused task briefs, not the whole project history.
- Every child return should be reviewed for two things:
  - spec/acceptance compliance;
  - delivery-system completeness, including registry, acceptance queue, deploy decision, and next owner.
- A child return that says "branch pushed" should be treated as input to the Return Gate, not as closure.
- Coordinator progress needs a durable ledger that survives context compaction.

In repo terms, this suggests adding a coordinator-owned `handoff.md` or ledger per substantial feature, rather than relying on the Delivery Queue row plus chat memory.

### What OpenSpec Teaches For This Repo

OpenSpec's strongest fit is the change artifact model:

- Current truth and proposed change should be separate.
- A change should have one folder.
- Proposal, requirements, design, and tasks should be easy to review together.
- Verification should compare implementation against those artifacts.
- When done, the change should be archived and folded into current truth.

In repo terms, this suggests adding `docs/changes/<change-id>/` for substantial product work, but keeping `docs/product`, `docs/techplans`, `Feature-Registry.md`, and `Acceptance-Queue.md` as the current source-of-truth layer.

### Where This Repo Should Be More Opinionated Than OpenSpec

OpenSpec intentionally treats artifacts as enablers, not gates. This repo needs some hard gates because it has cloud deploys, private token access, user acceptance, and multiple parallel coordinators.

Hard gates this repo should keep:

- No user acceptance request while acceptance is `failed`, `blocked`, or `needs_retest`.
- No cloud-served feature closure without deploy decision and real-surface acceptance path.
- No direct deploy of a feature branch that can clobber another active feature.
- No routine daily logs.
- No final Product Done without registry, acceptance, user-acceptance, and learning checks.

So the adaptation should be "OpenSpec-like artifacts plus TurenAgentTool delivery gates", not pure OpenSpec.

## Superpowers

### What It Is

Superpowers describes itself as a complete software development methodology for coding agents, built from composable skills and initial instructions that make the agent use those skills. Its README emphasizes a flow where the agent clarifies intent before coding, writes an implementation plan after design approval, then executes via subagent-driven development.

Its basic workflow is:

1. Brainstorming before code.
2. Git worktree isolation.
3. Detailed implementation plans.
4. Subagent-driven development or executing plans.
5. Test-driven development.
6. Code review.
7. Finishing the development branch.

Important implementation ideas from the public docs:

- Subagents should receive fresh, task-specific context rather than inheriting the controller's whole chat history.
- Every task gets review for spec compliance and code quality.
- The controller should not pause between every task just to ask whether to continue when the user already approved execution.
- Progress should be tracked in a durable ledger so compaction or resume does not cause duplicate dispatch.
- Review inputs should be passed as files or focused artifacts instead of giant pasted summaries.

### What Is Useful For This Repo

Superpowers is especially relevant to the recent problems in this repo:

- Feature Coordinators returned "code fixed and pushed" but did not close deploy/retest loops.
- Multiple feature releases clobbered each other's cloud behavior.
- The Global PM had to reconstruct state from chat snippets because child sessions did not always provide a complete return contract.
- Some tasks took too much owner attention because the next owner was named but not actually dispatched or watched.

Recommended adaptations:

- Add an explicit "feature coordinator ledger" concept to `Delivery-Queue.md` or a lightweight generated status file. The coordinator should know which child task was dispatched, what return is expected, and whether return gate was applied.
- Require child role prompts to include a short report contract and a return target. This repo already does part of this; the lesson from Superpowers is to make it strict and small.
- Add a reviewer gate for high-blast-radius or multi-feature changes. The reviewer should check spec compliance, delivery-state updates, and deploy/retest consequences.
- Prefer file-backed handoffs for large plans, evidence, and review packages. Avoid growing one prompt with all previous history.
- Use model/tooling strength proportional to role complexity: cheap/fast for mechanical tasks, stronger reasoning for coordinator/release/review tasks.

### What Not To Adopt Directly

- Do not make every small documentation update go through full Superpowers ceremony. The repo already learned that lightweight project-management doc edits should stay lightweight.
- Do not force strict TDD for every project-management or status-only change.
- Do not let the controller create many independent subagents for tasks that share the same files, deploy channel, or acceptance row.

## OpenSpec

### What It Is

OpenSpec is a lightweight spec-driven development framework for AI coding assistants. Its core model is:

- `openspec/specs/` is the current source of truth.
- `openspec/changes/<change-name>/` holds one proposed change.
- Each change can contain `proposal.md`, delta specs, `design.md`, and `tasks.md`.
- When complete, the change is archived and folded back into the truth.

OpenSpec's docs emphasize "agree first, then build confidently", but also treat artifacts as enablers rather than rigid gates. It supports an exploratory path (`/opsx:explore`), a proposal path (`/opsx:propose`), implementation (`/opsx:apply`), verification (`/opsx:verify`), and archive/sync flows.

OpenSpec also has a beta "stores" idea: planning can live in a separate git repo when work spans multiple repos or when requirements are owned separately from code.

### What Is Useful For This Repo

OpenSpec maps cleanly to our current PRD/techplan/registry problem:

- A feature needs one change package that collects product intent, requirements, design/tech approach, task checklist, and acceptance scenarios.
- Specs should describe current truth, while changes describe what is being modified.
- Changes should be archivable after implementation and acceptance, leaving durable current-state docs behind.
- Verification should compare implementation against artifacts, not only run tests.

Recommended adaptations:

- Introduce a repo-native `docs/changes/<feature-or-change>/` shape for substantial new product work. This can be lighter than full OpenSpec and can coexist with current PRDs and tech plans.
- For each substantial feature, keep:
  - `proposal.md`: why and scope.
  - `requirements.md`: acceptance criteria and scenarios.
  - `design.md`: technical approach or links to `docs/techplans/`.
  - `tasks.md`: implementation and validation checklist.
  - `handoff.md`: latest coordinator packet and return contract.
- After acceptance, archive the change folder and update `Feature-Registry.md`, `Acceptance-Queue.md`, and current docs. Do not keep stale active change folders.
- Add a verification script or checklist that asks: are all tasks checked, are requirements covered by implementation/evidence, are acceptance rows updated, and has user acceptance been preserved as pending until the user accepts?

### What Not To Adopt Directly

- Do not introduce a new `openspec/` root immediately. The repo already has `docs/product`, `docs/techplans`, and `docs/project-management`; duplicating truth would create confusion.
- Do not install OpenSpec CLI as a required dependency until there is a concrete workflow experiment.
- Do not archive automatically without coordinator judgment. This repo needs explicit acceptance and user-acceptance semantics.

## Comparison

| Area | Superpowers | OpenSpec | Best Repo Adaptation |
|---|---|---|---|
| Primary strength | Agent execution discipline | Spec/change artifact discipline | Use both: artifact-backed feature packages plus strict coordinator/reviewer return gates |
| Main unit | Skill/task/subagent workflow | Change folder and delta specs | Feature delivery flow and acceptance item |
| Quality gate | Task review and final review | Verify implementation against artifacts | Coordinator Return Gate plus optional reviewer gate |
| Context strategy | Fresh subagent context and file handoffs | Specs and changes live in repo | Avoid giant prompts; store handoffs/evidence in repo artifacts |
| Parallelism | Fresh subagent per task, but avoid conflicting implementation | Multiple changes can exist in parallel | Use feature coordinators, but serialize deploys and shared files |
| Completion model | Finish branch after tests/review | Archive change into source of truth | Product done only after deploy, acceptance, user acceptance, and learning gate |

## Recommended Changes For TurenAgentTool

### P0: Clarify Existing System Without New Frameworks

1. Add a "Coordinator Ledger" section or generated view that links each active feature to:
   - coordinator thread,
   - child role thread,
   - expected return contract,
   - deploy owner,
   - acceptance row,
   - current blocker.

   Minimal version: add a `Coordinator ledger` block to substantial `Delivery-Queue.md` rows or a companion file under `docs/project-management/coordinator-ledger.md`. Better version: generate it from structured Delivery Queue fields later.

2. Strengthen `Delivery-Coordinator-Protocol.md` with a Superpowers-style rule:
   - dispatch is not closed until return gate is applied;
   - reviewer/return gate must check spec compliance and next delivery state;
   - large child reports should be file-backed or summarized against a fixed schema.

3. Add an optional "reviewer gate" for:
   - combined release refs,
   - deploy-impacting changes,
   - multi-feature changes,
   - changes that update Feature Registry or Acceptance Queue in non-trivial ways.

4. Keep the current lightweight path for small docs/status edits.

5. Add a "fold back to truth" rule for accepted substantial changes:
   - after a feature is accepted or a release ref becomes the valid combined line, update the shared Feature Registry / Acceptance Queue / current docs on the branch intended to become main;
   - do not leave the newest truth only in a feature coordinator branch or chat return.

### P1: Add Change Packages For Substantial Features

Introduce `docs/changes/` only for substantial work, not every small bug:

```text
docs/changes/<change-id>/
  proposal.md
  requirements.md
  design.md
  tasks.md
  handoff.md
```

The Feature Coordinator owns the package. Product, Development, Test, and PM update the relevant artifact instead of scattering truth across chat.

Suggested first use in this repo:

- `docs/changes/frontend-experience-system/` because the feature is currently only queued and mostly planning-oriented.
- `docs/changes/daily-market-brief/` because it is a new product feature that will need product scope, data-source decisions, scheduling design, implementation tasks, and acceptance scenarios.

Avoid starting with Stock valuation or Kline because those flows are already in-flight and release-conflict-heavy; use the new format first on a cleaner feature.

### P2: Add Script Support

Extend repo scripts to support:

- `audit_agent_flow_health.py`: detect active features with missing coordinator ledger/watch path.
- `audit_delivery_state.py`: include active change package status when present.
- A new lightweight `scripts/verify_change_package.py` that checks required files, checked tasks, registry links, acceptance links, and open blockers.

### P3: Optional Framework Installation Trial

Only after one repo-native change-package experiment succeeds, consider whether to install OpenSpec or keep the lightweight local convention.

Superpowers is already conceptually close to the Codex skills available in this environment, so the more valuable work is to copy its operating discipline into our protocols and scripts rather than add another mandatory plugin dependency.

## How This Applies To Current Pain Points

### Coordinators Not Closing Loops

Superpowers' key lesson is that the controller must own the review loop. A child result is not done because it is pushed. The coordinator must inspect, accept/reject, update state, and dispatch deploy/retest or the next owner.

Repo action: make the Return Gate stricter and ledger-backed.

### Cross-Feature Deploy Conflicts

OpenSpec's "one change, one folder" helps feature-level clarity, but this repo also needs release-level integration. A combined release ref should be treated as its own change package or at least its own Delivery Queue item with explicit preserved behaviors.

Repo action: combined release rows should list preserved features and required smoke checks.

### Too Much User Attention Cost

Superpowers says not to ask "should I continue?" after the user approved execution. OpenSpec says artifacts keep everyone looking at the same plan.

Repo action: the user's job should remain product priority, product decisions, permissions, and final acceptance. Routine routing, return gate, deploy decision, and retest dispatch should be coordinator-owned.

### Spec Drift

OpenSpec's archive model is useful: after a change lands, fold the accepted behavior into current truth and archive the change. This repo can do the same by updating Feature Registry/current docs and closing Delivery Queue rows.

Repo action: add an explicit "archive or fold into truth" step for accepted substantial changes.

## Proposed Next Experiment

Do not install or migrate to either framework yet. Instead, run one repo-native experiment:

Feature: Frontend experience system or Daily Market Brief.

Process:

1. Create `docs/changes/<feature>/`.
2. Use the four-artifact shape: proposal, requirements, design, tasks.
3. Coordinator dispatches Product/Development/Test from `handoff.md`.
4. Add reviewer gate before deploy or acceptance.
5. Archive/fold the change after acceptance.

Success criteria:

- The owner does not need to repeat context across sessions.
- The coordinator can resume after compaction without reading chat history.
- Development knows exactly when deploy/retest is required.
- Acceptance can verify against explicit scenarios.
- Feature Registry and Acceptance Queue stay current.

## Sources Reviewed

- Superpowers README: https://github.com/obra/superpowers
- Superpowers subagent-driven development skill: https://github.com/obra/superpowers/blob/main/skills/subagent-driven-development/SKILL.md
- Superpowers writing-plans skill: https://github.com/obra/superpowers/blob/main/skills/writing-plans/SKILL.md
- OpenSpec README: https://github.com/Fission-AI/OpenSpec
- OpenSpec Getting Started: https://github.com/Fission-AI/OpenSpec/blob/main/docs/getting-started.md
- OpenSpec Core Concepts: https://github.com/Fission-AI/OpenSpec/blob/main/docs/overview.md
- OpenSpec Workflows: https://github.com/Fission-AI/OpenSpec/blob/main/docs/workflows.md
- OpenSpec Stores beta guide: https://github.com/Fission-AI/OpenSpec/blob/main/docs/stores-beta/user-guide.md
