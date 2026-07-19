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
- Quality & Acceptance Lead: owns the risk-based quality route, independent user-facing acceptance from the real user surface, and recurring test-quality improvement. It returns results to the Feature Coordinator; it does not become an approval bottleneck for routine low-risk work.
- Project Management Agent: owns audits, status integrity, stale-document detection, registry consistency, and missing-evidence discovery. It is not the default feature-flow owner.
- Architecture & Code Health Agent: owns read-only cross-feature architecture review. It runs the repository harness, identifies structural risks with evidence, and proposes bounded implementation slices; it does not replace Feature Coordinators, directly start broad refactors, or decide product access policy.

There may be many Feature Coordinators running in parallel, but there is only one Global Project Manager role for the portfolio. The Global Project Manager does not replace Feature Coordinators, Product, Development, or Testing. It is accountable for whether the agent organization itself works: whether coordinators close loops, whether handoffs are valid, whether deploy and acceptance gates are respected, and whether repeated failures become better rules, scripts, or queues.

The Global Project Manager should use `python3 scripts/audit_agent_flow_health.py` as the default portfolio-health check before opening individual coordinator or child-agent conversation context. Conversation context is second-line evidence, not the primary operating record. Read it when the health audit reports `context_required: yes`, or when Delivery Queue, Acceptance Queue, Feature Registry, commits, and returned summaries contradict each other.

Operating-model infrastructure is tracked in `docs/project-management/Agent-Operating-Model-Roadmap.md`. When this model, the coordinator protocol, prompt templates, or flow-health audit rules change, run `python3 scripts/evaluate_agent_flow_cases.py` before handoff so known multi-agent failure patterns stay covered.

## Standard Delivery Flow

Use this flow for substantial product-feature work:

```text
Owner intent
  -> Feature Coordinator contract
  -> Product/Technical planning when needed
  -> Development implementation and verification
  -> Deploy decision and shared deploy path when needed
  -> Quality route and, when required, acceptance from the real surface
  -> Coordinator Return Gate
  -> User acceptance request only when allowed
  -> Role learning check
  -> Product done
```

The Feature Coordinator must keep the flow moving when the next action is known. It should dispatch the next role, record a blocker, or ask the Owner only for a real Owner decision.

For substantial new work, the Feature Coordinator should use a lightweight change package under `docs/changes/<change-id>/` when the feature needs a resumable proposal, requirements, design, tasks, and handoff. Change packages are working artifacts; they do not replace PRDs, technical plans, Feature Registry, Acceptance Queue, or Delivery Queue.

When a feature already has delivery history, the Feature Coordinator should fill or refresh `docs/project-management/Coordinator-Context-Packet.md` before dispatching roles or reading long conversation history. The packet keeps context narrow: source docs, registry rows, acceptance rows, delivery rows, refs, watch contract, deploy decision, and escalation boundary.

## Feature Coordinator Ownership

The Feature Coordinator is the directly responsible owner for one feature until the feature reaches a terminal state:

- `product_done`: all required product, implementation, deploy, acceptance, user-acceptance, state, and learning gates are satisfied or explicitly marked not required.
- `blocked_with_owner`: the blocker is precise, the next real owner is named, and the smallest unblock action is recorded.
- `waiting_for_user_acceptance`: independent acceptance has passed or known gaps are explicitly disclosed, and no internal role work remains before asking the Owner.
- `explicitly_cancelled`: the Owner or Product decision cancels or parks the feature.

The coordinator does not lose ownership when a Product, Development, Release Reviewer, Deploy Owner, or Quality & Acceptance Lead returns. A returned branch or final message is input to the Coordinator Return Gate, not closure.

After every child-role return, the coordinator must choose one closure action before stopping:

- `accept_and_route`: accept or integrate the return, update delivery state, and dispatch the next owner.
- `reject_and_return`: reject the return with concrete corrections and send it back to the same or correct role.
- `blocked_with_owner`: record the blocker, named owner, exact ref/service/decision needed, and watch or resume path.
- `ready_for_user_acceptance`: ask the Owner only after acceptance state allows it.

Normal Product -> Development -> Review -> Deploy -> Acceptance -> Retest routing stays inside the feature coordinator loop. The coordinator should not return routine next steps to the Global Project Manager or Owner.

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
- Repeated blocker patterns that suggest a protocol, lesson, or script improvement is needed.

Architecture & Code Health findings return to the affected Feature Coordinator
for feature-level closure. The Global Project Manager prioritizes systemic
debt and rule evolution. Ask the Owner only for a true cross-feature tradeoff
or priority decision.

Do not escalate normal next-owner routing, developer follow-up, deploy retest, or acceptance retest to the Owner or Global Project Manager when the Feature Coordinator can continue.

When the Global Project Manager recovers a stale or broken feature flow, the recovery action should normally hand the result back to the same Feature Coordinator with an instruction to apply the Return Gate. The Global Project Manager should not become the steady-state feature coordinator unless the original coordinator is missing, cancelled, or explicitly replaced.

## State Reconciliation Gate

Feature-level delivery state is not authoritative merely because it was updated on a coordinator or child-agent branch. When a feature coordinator reaches a terminal state on any branch that is not the current authoritative project branch, the coordinator or Global Project Manager must run a state reconciliation gate before using that result in portfolio status.

The reconciliation gate checks:

- `docs/project-management/Feature-Registry.md`
- `docs/project-management/Acceptance-Queue.md`
- `docs/project-management/Delivery-Queue.md`
- linked PRDs, technical plans, and implementation traceability rows
- release/deploy refs and acceptance evidence mentioned by the returned branch

The result must be one of:

- `reconciled`: valid state has been cherry-picked or manually ported to the authoritative branch and verified.
- `rejected`: the returned state is stale, superseded, or contradicted by newer authoritative state.
- `blocked_with_owner`: a conflict, missing ref, or permission prevents reconciliation; the exact owner and unblock action are recorded.

The Global Project Manager should not report a feature as not started or unfinished when a known coordinator branch records that it is implemented, acceptance-passed, or user-accepted. First run `python3 scripts/audit_agent_flow_health.py --compare-ref <coordinator-ref> --feature "<feature>"`, then reconcile or reject the returned state.

## Completion Gates

- Code-done: code or docs are committed, pushed when expected, locally verified, and returned with evidence.
- Deploy-done: the intended ref is on the relevant cloud/user surface, deploy health is verified, and the affected URL, service, or command is named.
- Acceptance-passed: the required quality route completed, including independent real-surface acceptance when the route requires it, and the Acceptance Queue is updated when applicable.
- User-accepted: the Owner explicitly accepted the behavior, document, or delivery outcome.
- Product-done: PRD, technical plan, implementation, verification, deployment, acceptance testing, user acceptance, delivery state, and learning gates are all satisfied or explicitly marked not required.

Code-done, deploy-done, and acceptance-passed are not product-done by themselves.

Feature Coordinators and the Global Project Manager should self-push verified commits on their own delivery, state, and release branches. They should not ask the Owner whether to push a completed, verified commit when the target branch/ref is clear. Escalate only for direct `main` pushes that may trigger production automation without prior approval, force-pushes, credential or permission blockers, unresolved merge or deploy conflicts, or an explicit user pause.

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
