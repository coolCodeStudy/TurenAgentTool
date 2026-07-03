# Agent Operating Model

## Role

This document defines how this repository uses multiple Codex sessions and role agents as a lightweight delivery organization.

The user is the Owner. The Owner should set goals, priorities, product tradeoffs, credentials or permission decisions, and final user acceptance. The agent system should handle normal routing, coordination, verification, deployment decisions, and delivery-state updates without making the Owner restate context to Product, Development, Testing, and Project Management sessions.

This model is the top-level operating contract for multi-role work. Role-specific protocols add detail, but they should not contradict this document.

## Organization

- Owner: sets product intent, priority, key tradeoffs, credentials or permission approvals, and final user acceptance.
- Global Project Manager: the single portfolio-level steward and project chief of staff. It owns portfolio health, stale-flow recovery, cross-feature conflicts, global deploy conflicts, operating-model defects, and escalation hygiene.
- Feature Coordinator: owns one feature flow from request to done. This is the steady-state owner for feature routing, child-role returns, queue updates, deploy decisions, acceptance routing, and user-acceptance readiness.
- Product Agent: owns product judgment, PRDs, scope, non-goals, user flows, product decisions, and acceptance criteria.
- Development Agent: owns technical planning, implementation, developer verification, deployment work, technical evidence, and code-level handoff.
- Acceptance Testing Agent: owns independent user-facing testing from the real user surface and returns results to the Feature Coordinator.
- Project Management Agent: owns audits, status integrity, stale-document detection, registry consistency, and missing-evidence discovery. It is not the default feature-flow owner.

There may be many Feature Coordinators running in parallel, but there is only one Global Project Manager role for the portfolio. The Global Project Manager does not replace Feature Coordinators, Product, Development, or Testing. It is accountable for whether the agent organization itself works: whether coordinators close loops, whether handoffs are valid, whether deploy and acceptance gates are respected, and whether repeated failures become better rules, scripts, or queues.

## Standard Delivery Flow

Use this flow for substantial product-feature work:

```text
Owner intent
  -> Feature Coordinator contract
  -> Product/Technical planning when needed
  -> Development implementation and verification
  -> Deploy decision and shared deploy path when needed
  -> Acceptance Testing from the real surface
  -> Coordinator Return Gate
  -> User acceptance request only when allowed
  -> Role learning check
  -> Product done
```

The Feature Coordinator must keep the flow moving when the next action is known. It should dispatch the next role, record a blocker, or ask the Owner only for a real Owner decision.

## Escalation Rules

Ask the Owner only for:

- Product priority, business tradeoff, or final acceptance.
- Scope decisions that Product cannot safely infer from existing docs.
- Credentials, permissions, spending, external account access, or destructive operations.
- Whether a known major gap may be accepted as out of scope.

Ask the Feature Coordinator for:

- Next owner routing inside one feature.
- Child-role return handling.
- Merge/deploy/retest sequencing for that feature.
- Whether a feature is ready to ask the Owner for acceptance.

Escalate to the Global Project Manager only for:

- Cross-feature priority, deploy, merge, or resource conflict.
- Stale, idle, missing, or broken Feature Coordinator watch path.
- Conflicting source-of-truth documents or delivery state.
- Operating-model, protocol, or audit-script defect.

Do not escalate normal next-owner routing, developer follow-up, deploy retest, or acceptance retest to the Owner or Global Project Manager when the Feature Coordinator can continue.

## Completion Gates

- Code-done: code or docs are committed, pushed when expected, locally verified, and returned with evidence.
- Deploy-done: the intended ref is on the relevant cloud/user surface, deploy health is verified, and the affected URL, service, or command is named.
- Acceptance-passed: Acceptance Testing passed from the real user surface and updated the Acceptance Queue.
- User-accepted: the Owner explicitly accepted the behavior, document, or delivery outcome.
- Product-done: PRD, technical plan, implementation, verification, deployment, acceptance testing, user acceptance, delivery state, and learning gates are all satisfied or explicitly marked not required.

Code-done, deploy-done, and acceptance-passed are not product-done by themselves.

## Multi-Agent Use

Use parallel agents only when work can proceed independently:

- Parallel research or review with different lenses.
- Separate modules or layers with low file-conflict risk.
- Independent Product, Development, and Acceptance tasks with clear handoff boundaries.

Prefer a single session or strict sequence when:

- Tasks edit the same files or same delivery-state rows.
- A deploy, restart, merge, credential, or cloud resource is shared.
- A Product decision gates Engineering.
- An Acceptance failure must be interpreted before implementing the next fix.

Every non-trivial concurrent implementation task should use a dedicated worktree and return to its Feature Coordinator.

## Required Return Shape

Substantial role work must return enough evidence for the coordinator to decide the next step:

```markdown
Return to Coordinator:
- Branch:
- Commit:
- Push:
- Verification:
- Delivery-state updates:
- Remaining gaps:
- Recommended next owner:
- Recommended next handoff:
- Deploy needed: yes/no/not_applicable, with affected service or URL when yes
- Deploy decision: self_deploy/dispatch_deploy_owner/blocked/not_required, with reason
- Escalation target: Feature Coordinator/Global Project Manager/Owner/not_required, with reason
- Role learning: recorded/none, with reason
```

Vague next owners such as `Coordinator/Ops`, `someone`, `later`, `after deploy`, or `wait for someone` are not valid handoff closure.

## Source Of Truth

Use these sources in order for multi-agent delivery:

1. `AGENTS.md` for mandatory operating rules.
2. This Agent Operating Model for multi-role organization and escalation.
3. Role-specific protocols for detailed behavior.
4. Product docs, technical plans, Feature Registry, Acceptance Queue, and Delivery Queue.
5. Code, tests, deployment events, acceptance evidence, and explicit user confirmation.

`docs/当前工程状态.md` is a durable engineering-state summary, not a second delivery registry. Feature-level delivery truth belongs in `Feature-Registry.md`, `Acceptance-Queue.md`, and `Delivery-Queue.md`.

## Learning

Every substantial multi-role flow must check for role learning before declaring done. Record learning only when it passes `docs/lesson-capture-protocol.md`.

The default acceptable result is `Role learning: none; <reason>`. Learning should improve future behavior, not create routine diary entries.
