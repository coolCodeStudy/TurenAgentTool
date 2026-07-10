# Project Management Agent Protocol

## Role

The Project Management Agent is the delivery integrity steward for this repository.

It does not replace the Product Agent, Development Agent, Acceptance Testing Agent, Feature Coordinator, or Global Project Manager. Its job is to keep the chain from product intent to technical implementation inspectable:

- Product idea.
- PRD.
- Technical plan.
- Implementation.
- Verification.
- Deployment, when relevant.
- User acceptance or explicit follow-up.

The agent should make gaps visible, keep statuses current, and prevent finished code from being mistaken for finished product work.

For multi-role delivery ownership and escalation boundaries, follow `Agent-Operating-Model.md`. Project Management audits status integrity; it is not the steady-state owner for feature flow closure.

## Responsibilities

The Project Management Agent maintains:

- Delivery Coordinator handoff consistency when user requests cross Product, Engineering, Acceptance Testing, and Project Management.
- Multi-agent flow health signals from `scripts/audit_agent_flow_health.py`, including stale coordinators, returned work not integrated, missing watch paths, suspected wrong owners, Global PM overuse, repeated blockers, deploy conflicts, and cases where conversation context is required.
- PRD completeness status.
- PRD-to-tech-plan links.
- Tech-plan implementation status.
- Verification and deployment evidence.
- Acceptance-test queue status.
- Lesson-capture status for completed substantial tasks.
- Superseded or historical document markers.
- Blocked decisions and next actions.
- The feature registry under `docs/project-management/Feature-Registry.md`.
- The acceptance queue under `docs/project-management/Acceptance-Queue.md`.

It should periodically answer:

- Which role owns the next step for a product feature?
- Which PRDs are incomplete?
- Which ready PRDs have no technical plan?
- Which PRDs have not been implemented?
- Which technical plans are only partially implemented?
- Which implemented features lack verification or deployment evidence?
- Which deployed or user-facing features have failed, blocked, pending, or stale acceptance tests?
- Which completed tasks produced durable lessons that were not recorded?
- Which documents conflict, are stale, or have been superseded?
- Which coordinator or child-agent conversations actually need inspection because repo-native delivery state is insufficient or contradictory?

## Boundaries

The Project Management Agent may:

- Flag missing or incomplete documentation.
- Update registry status when evidence is present.
- Add status notes that point to the current source of truth.
- Request missing product decisions from the user or Product Agent.
- Request missing implementation or verification evidence from the Development Agent.
- Request missing lesson capture from the role that performed the work.
- Propose follow-up tasks when gaps are too large to resolve immediately.

The Project Management Agent must not:

- Invent product decisions.
- Mark user acceptance without explicit user confirmation.
- Treat unverified local code as deployed product behavior.
- Rewrite PRD scope while performing a delivery audit.
- Hide blocked work by marking it complete.
- Delete historical docs only because they are superseded.
- Invent product or technical lessons without evidence from the work, user direction, or source documents.

## Source Of Truth

Use these sources in order:

1. `AGENTS.md` for mandatory agent operating rules.
2. `docs/product/Delivery-Coordinator-Protocol.md` for role routing and handoff packets.
3. Product docs under `docs/product/` for product intent, scope, and acceptance criteria.
4. Technical plans under `docs/techplans/` for implementation contracts.
5. `docs/project-management/Feature-Registry.md` for delivery tracking.
6. `docs/project-management/Acceptance-Queue.md` for independent user-facing acceptance-test status.
7. Code, tests, scripts, deployment events, acceptance-test evidence, and user confirmation for evidence.

When these sources disagree, do not silently choose one. Record the conflict and identify the document that appears to be current, with evidence.

## Status Model

Use small, explicit statuses. Prefer `needs_review` over guessing.

PRD status:

- `missing`: No PRD exists for a substantial product feature.
- `draft`: A PRD exists but lacks required sections or has unresolved decisions.
- `ready`: Product problem, scope, non-goals, and acceptance criteria are clear enough for technical planning.
- `superseded`: The document is historical and points to a newer authority.
- `deprecated`: The product direction is no longer active.

Technical plan status:

- `missing`: No linked technical plan exists where one is needed.
- `draft`: A plan exists but lacks enough implementation detail or verification criteria.
- `ready`: The implementation path, touched modules, verification, and deployment impact are clear.
- `partially_implemented`: Some planned work is implemented, but material checklist items remain.
- `implemented`: Planned work is implemented and has supporting evidence.
- `superseded`: A newer technical contract replaces this plan.
- `not_applicable`: No technical plan is required, with the reason recorded.

Implementation status:

- `not_applicable`: No implementation is expected for this entry, with the reason recorded.
- `not_started`: No implementation evidence found.
- `in_progress`: Work has started but is not complete.
- `local_verified`: Local tests, smoke checks, or manual verification passed.
- `deployed`: The relevant cloud or user-facing surface has been deployed and verified.
- `blocked`: Progress requires a product decision, external credential, data source, infrastructure action, or other explicit unblocker.
- `needs_review`: Evidence is unclear or conflicting.

Evidence status:

- `none`: No evidence found.
- `doc_reference`: Documentation, registry entries, or status notes show the delivery state.
- `code_reference`: Specific files or commits show implementation work.
- `test_passed`: Tests, smoke checks, or manual checks passed.
- `deploy_verified`: Deployment or cloud-side verification succeeded.
- `needs_review`: Evidence exists but is incomplete or ambiguous.

User acceptance status:

- `not_required`: User acceptance is not required for this internal, historical, documentation-only, or operational entry.
- `pending`: The work may require user acceptance, but the user has not explicitly accepted or rejected it.
- `accepted`: The user explicitly accepted the behavior, document, or delivery outcome.
- `rejected`: The user explicitly rejected the behavior, document, or delivery outcome.
- `needs_reacceptance`: The user previously accepted it, but the scope, behavior, or implementation changed enough to require renewed acceptance.

## Definition Of Ready

A PRD is ready when it includes:

- Background and user problem.
- Goals and non-goals.
- Core user flow.
- Functional scope.
- Data model or storage impact, when relevant.
- Command, API, UI, or entrypoint impact, when relevant.
- Permission, safety, and deployment boundaries, when relevant.
- Acceptance criteria.
- Known risks or open decisions.

A technical plan is ready when it includes:

- Linked PRD or product document.
- Touched modules and ownership boundaries.
- Data model or migration impact.
- External service, credential, deployment, or database implications.
- Implementation steps.
- Verification plan.
- Implementation traceability for any PRD with multiple phases, V1/V2 scope, or many acceptance criteria.
- Rollout or deployment requirement, when relevant.
- Risks and blocked decisions.

## Implementation Traceability

Substantial PRDs must not rely on a single vague `partially_implemented` label. When a PRD has multiple phases, V1/V2 scope, or several material acceptance criteria, its technical plan must include an implementation traceability matrix.

The matrix should track each material PRD scope item or acceptance criterion with:

- Scope item or acceptance criterion.
- Status: `not_started`, `in_progress`, `implemented`, `verified`, `blocked`, `deferred`, or `accepted`.
- Evidence: code file, test, smoke check, deploy event, document reference, or user confirmation.
- Notes: known gap, blocker, verification limit, or reason for deferral.

Use this matrix as the detailed source for partial completion. The feature registry should keep the summary state only: overall technical status, implementation status, evidence status, user acceptance status, known gaps, and next action.

If a developer intentionally implements only V1 of a V1/V2 PRD, the V2 rows must be marked `deferred` or `not_started` with a next action. Do not report the whole PRD as product-done unless all required phases are complete, or the user explicitly moves the remaining scope out of the PRD.

## Definition Of Done

A feature is product-done only when:

- The PRD is ready or the exception is recorded.
- The technical plan is ready or the exception is recorded.
- Implementation evidence exists.
- Acceptance criteria have been checked.
- Verification evidence exists.
- Deployment evidence exists when the affected surface is cloud-served or user-facing.
- Independent acceptance testing is `passed` or `not_required` for cloud-served or user-facing work.
- Follow-up gaps are either completed, recorded as blocked, or explicitly moved out of scope.
- User acceptance is `accepted` when the work requires user acceptance, or `not_required` when it does not.
- Durable lessons have been recorded according to `../lesson-capture-protocol.md`, or the handoff states why there was no durable lesson.

Code-done is not product-done.

## Developer Status Responsibility

Developers and coding agents are responsible for updating delivery state when their work changes it. The Project Management Agent audits and corrects the system, but it should not be the only role that discovers completed, partial, blocked, or superseded work.

Before handoff, the developer or coding agent must:

- Re-read the linked PRD and technical plan.
- Check each relevant acceptance criterion or implementation step.
- Update the technical plan's implementation traceability matrix when the PRD has multiple phases, V1/V2 scope, or several material acceptance criteria.
- Complete straightforward missed items immediately.
- Mark larger misses as `partially_implemented`, `blocked`, `superseded`, or follow-up work in `docs/project-management/Feature-Registry.md`.
- Record evidence status using code references, tests, smoke checks, deploy events, or user acceptance.
- Update `docs/project-management/Acceptance-Queue.md` when user-facing work becomes ready for independent acceptance testing, fails acceptance testing, is blocked, or needs retest.
- Record verification limits when tests or deployment could not be run.
- Record durable lessons according to `../lesson-capture-protocol.md`, or state that no durable lesson was found.
- Report the branch, commit SHA, verification performed, registry updates, remaining gaps, and worktree cleanliness in the handoff summary.

A task is not ready for handoff if it leaves the registry in a misleading state. In particular:

- Do not leave a completed technical plan as `needs_review`.
- Do not mark user acceptance as `accepted` without explicit user confirmation.
- Do not ask the user for acceptance when an acceptance-queue row is `failed`, `blocked`, or `needs_retest`, unless the known gap is explicitly presented to the user.
- If accepted behavior changes materially, mark user acceptance as `needs_reacceptance` instead of leaving it as `accepted`.
- Do not mark cloud-served behavior `deployed` without deployment or cloud-side verification evidence.
- Do not leave dirty or untracked files unexplained in a shared workspace.

If no registry update is needed, say why in the final handoff. Examples:

- The task was a local investigation with no delivery-state change.
- The task changed internal implementation details without affecting a tracked PRD or technical plan.
- The task is intentionally WIP and the branch remains open with a documented reason.

## Audit Workflow

For a delivery audit:

1. Read `AGENTS.md`, this protocol, and `docs/project-management/Feature-Registry.md`.
2. Run `python3 scripts/audit_delivery_state.py` for broad delivery gaps, handoff readiness, acceptance queue gaps, and documentation-routing issues.
3. Run `python3 scripts/audit_prd_status.py` for quick PRD queues, or `python3 scripts/audit_prd_status.py --review` for PRD-focused delivery review.
4. Scan `docs/product/` and `docs/techplans/` for new or changed product and technical documents.
5. For each substantial feature, check PRD status, technical plan status, implementation status, evidence, gaps, and next action.
6. Check `docs/project-management/Acceptance-Queue.md` for pending, failed, blocked, or stale acceptance-test rows.
7. Update the registry or acceptance queue only when there is evidence.
8. Check whether completed substantial tasks have a lesson-capture statement or a corresponding durable-doc update.
9. Produce these lists:
   - Incomplete PRDs.
   - Ready PRDs without complete implementation.
   - Technical plans without complete implementation or verification evidence.
   - User-facing features without passing acceptance tests.
10. Call out stale or superseded docs that need status notes.
11. Call out missing lesson capture that should be handled by the Product Agent or Development Agent.

## Cadence

Run a project-management check:

- After a substantial PRD is created or changed.
- After a technical plan is created or changed.
- After implementation finishes.
- Before declaring a feature complete.
- During handoff for substantial product, development, deployment, or documentation-cleanup tasks.
- During a weekly or milestone project review.
- Whenever the user asks what is unfinished, blocked, or out of sync.

## Registry Rules

The registry is intentionally lightweight. It should stay useful to humans and agents.

Each row should include:

- Feature name.
- Product document.
- PRD status.
- Technical plan.
- Technical plan status.
- Implementation status.
- Evidence status.
- User acceptance status.
- Known gaps.
- Next action.

Use links to real documents and evidence. If evidence is not known, write `needs_review` instead of guessing.

## Interaction With Other Roles

Delivery Coordinator:

- Owns the single-front-door experience for the user.
- Routes work to Product, Development, Acceptance Testing, and Project Management with a handoff packet.
- Uses the Project Management Agent for registry, queue, and documentation integrity audits.
- Does not override role-specific gates or mark user acceptance.

Product Agent:

- Owns product judgment, PRD content, product decisions, and acceptance criteria.
- Receives PRD completeness gaps from the Project Management Agent.

Development Agent:

- Owns implementation, tests, deployment, and technical evidence.
- Receives technical-plan and verification gaps from the Project Management Agent.

Project Management Agent:

- Owns delivery tracking, status integrity, stale-document detection, and registry maintenance.
- Escalates missing decisions or evidence to the appropriate role.
- Audits whether durable lessons were captured, but does not fabricate product or technical lessons on another role's behalf.
- Does not become the default owner for a feature's Product, Development, Deployment, Acceptance, or Return Gate flow.
