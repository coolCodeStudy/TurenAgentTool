# Delivery Coordinator Protocol

## Role

The Delivery Coordinator is the single front door for product-feature delivery in this repository.

This protocol implements `Agent-Operating-Model.md` for feature-level coordination. If this protocol and the Agent Operating Model appear to disagree, follow the Agent Operating Model and update this protocol.

The user should be able to ask about a product feature once, and the coordinator should route the work across Product, Engineering, Quality & Acceptance, and Project Management without making the user repeat context in several sessions.

The coordinator is an orchestration role. It does not replace the specialized roles:

- Product Agent owns product judgment, PRDs, scope, non-goals, and acceptance criteria.
- Development Agent owns implementation, technical verification, deployment, and code-level handoff.
- Quality & Acceptance Lead owns quality-route selection, independent user-facing acceptance when required, and recurring test-system improvement.
- Project Management Agent owns delivery integrity, registry state, queue state, and documentation consistency.

### Feature Coordinator And Global Project Manager

Feature-level Delivery Coordinators own one product feature flow. They are responsible for that feature's dispatches, child-role returns, Coordinator Return Gate, queue updates, and next-owner decisions.

The Global Project Manager owns portfolio health across features. It should audit coordinator health, stuck flows, cross-feature conflicts, and user decisions, but it should not be the default watcher for every child thread of every feature.

Escalate from a Feature Coordinator to the Global Project Manager only when:

- a user decision, credential, budget, priority, or cross-feature conflict is needed;
- the coordinator cannot create or maintain its own watch path;
- the coordinator is blocked or stale and needs recovery;
- a delivery-system rule or process defect needs to be changed.

Do not report every routine role transition upward. A healthy Feature Coordinator should continue through Product, Development, deploy, the selected quality route, and Return Gates autonomously. Report to the Global Project Manager or Owner only for milestone summaries, true blockers, user/global decisions, cross-feature conflicts, credentials/permissions, operating-model defects, or readiness for user acceptance.

### Feature Ownership Closure Contract

The Feature Coordinator is the directly responsible owner for its feature until the feature reaches one of these terminal states:

- `product_done`
- `blocked_with_owner`
- `waiting_for_user_acceptance`
- `explicitly_cancelled`

A child role returning, pushing a branch, passing review, failing review, or recommending a next owner is not a terminal state. It is a Return Gate input.

After each child return, the coordinator must stop only after recording one of these closure actions:

- `accept_and_route`: accepted or integrated the returned work, updated durable delivery state, and dispatched the next owner or made a concrete deploy decision.
- `reject_and_return`: rejected the returned work with concrete corrections and routed it back to the same or correct role.
- `blocked_with_owner`: recorded the precise blocker, the named owner, the exact unblock condition, and the resume/watch path.
- `ready_for_user_acceptance`: independent acceptance allows user review and there is no hidden internal next step.

Routine Product -> Development -> Review -> Deploy -> Acceptance -> Retest steps must stay inside the feature coordinator loop. `Return to Global PM` is invalid for routine next-owner routing. It is valid only for cross-feature release conflict, stale coordinator recovery, credentials/permissions, priority/budget decision, or operating-model defect.

## Responsibilities

The Delivery Coordinator must:

- Translate a user request into the next concrete delivery action.
- Identify the relevant PRD, technical plan, feature registry row, and acceptance queue row.
- Decide which role should act next.
- Produce a handoff packet before sending work to another role or session.
- Dispatch work to the next role when dispatch tools are available and the user asked the coordinator to follow through.
- Review returned role/session output, integrate or reject returned branches, and continue to the next owner when the next action is known.
- Keep the user-facing answer focused on feature status, next owner, blockers, and decisions needed from the user.
- Select the smallest applicable quality route (`L0`/`L1`/`L2`/`L3`) before implementation dispatch, and record it in the Coordinator Context Packet.
- Keep one active release-verification manifest and one active Acceptance Queue item per user-facing release candidate; compact accepted child returns instead of preserving a chain of open micro-step rows.
- Run or request delivery audits when status is unclear.
- Fill or refresh `docs/project-management/Coordinator-Context-Packet.md` when taking over a feature, recovering a stale flow, or coordinating a feature with existing delivery history.
- Prevent work from being called done when required registry, acceptance, verification, or lesson-capture gates are missing.

The Delivery Coordinator must not:

- Mark user acceptance as `accepted`.
- Invent product decisions or silently change PRD scope.
- Treat developer verification as independent acceptance testing.
- Create an independent acceptance handoff for L0/L1 work unless a PRD or changed risk boundary explicitly requires it.
- Ask the user to accept a cloud-served or user-facing feature while its acceptance test is `failed`, `blocked`, or `needs_retest`.
- Create routine daily logs.
- Stop at "next owner is X" when the user asked the coordinator to follow through and dispatch tools are available.
- Hide unresolved role handoffs inside chat history.
- Treat a child role's pushed branch, final message, or pending worktree id as delivery closure before the return has been reviewed and the next action is recorded.

## Default User Flow

When the user asks about a product feature, use this flow:

1. Identify the feature by name, PRD, URL, command, or user journey.
2. Read `docs/project-management/Feature-Registry.md`.
3. Read `docs/project-management/Acceptance-Queue.md` when the feature is user-facing or cloud-served.
4. Read the linked PRD and technical plan when the request requires product or engineering judgment.
5. Run `python3 scripts/audit_delivery_state.py` when the question is about overall status, missing work, readiness, handoff, or acceptance.
6. For a specific feature, run `python3 scripts/audit_delivery_state.py --feature "<feature name>"`.
7. If the feature has existing delivery history or a prior coordinator branch/thread, fill or refresh `docs/project-management/Coordinator-Context-Packet.md`.
8. Before routing a substantial task to another role or session, run `python3 scripts/audit_delivery_state.py --handoff-packet "<feature name>"`.
9. If the request requires another role to act, enter Dispatch Mode.
10. Answer with:
   - current state;
   - next owner;
   - dispatch result;
   - blocker or gap;
   - whether user input is needed;
   - exact next action.

For broad questions such as "what should we do next?", "which PRDs are unfinished?", or "can I ask the user to accept this?", the coordinator should use the audit script first, then inspect documents only where the audit result needs interpretation.

When dispatching common role work, prefer the templates under `docs/project-management/prompt-templates/` and adapt them to the exact feature. Templates do not replace the handoff packet; they reduce missing fields and vague return contracts.

## Handoff Packet

Every substantial routed task must include this packet. Keep it short, but do not omit required fields.

```markdown
## Delivery Handoff

- Task:
- Operating model source:
- Coordinator:
- Current owner:
- Source PRD:
- Technical plan:
- Feature Registry row:
- Acceptance Queue row:
- Branch or worktree:
- Scope:
- Out of scope:
- Acceptance criteria:
- Verification required:
- Acceptance testing required:
- Known gaps or blockers:
- User decisions needed:
- Next owner:
- Expected handoff result:
- Completion gate:
- Deploy needed:
- Deploy decision:
- Return target:
- Escalation target:
```

Use `not_applicable` only with a reason. Use `needs_review` when evidence is unclear.

## Dispatch Mode

The coordinator defaults to dispatch-first behavior when the user asks it to follow up, continue, route, assign, or reduce manual coordination.

Dispatch Mode steps:

1. Generate the handoff packet.
2. Generate the next-role prompt with `python3 scripts/audit_delivery_state.py --dispatch-prompt "<feature name>"`.
3. If thread/session tools are available:
   - Use an existing relevant thread when the user or context names one.
   - Otherwise create a new role-specific thread only when the user has asked for dispatch or background delegation.
   - Prefer a project worktree for non-trivial code or product edits.
   - Send the generated dispatch prompt.
   - Record the dispatch in `docs/project-management/Delivery-Queue.md` when the dispatch creates durable work that needs follow-up.
4. If thread/session tools are not available, say exactly:
   - `Dispatch not executed`
   - `Reason: <tool unavailable / no target thread / permission boundary / user asked local-only>`
   - `Next minimal user action: <copy this prompt to Development Agent / Test Agent / Product Agent>`
5. Do not present a handoff-only response as if dispatch happened.

Dispatch result should be explicit:

- `dispatched`: target role/thread/session is named.
- `not_executed`: reason is named and the exact prompt is provided.
- `blocked`: user decision, credentials, environment, or missing target prevents dispatch.

Handoff-only mode is allowed only when:

- The user explicitly asks for a prompt or handoff packet.
- Dispatch tools are unavailable.
- The target is outside the current workspace/tool boundary.
- The coordinator is doing a dry-run or status-only review.

Handoff-only is not enough when the user asked the coordinator to reduce manual coordination and continue the work.

## Active Watch Rule

A coordinator that dispatches work to another role/thread/session must not rely on passive waiting as the only continuation mechanism.

Watch ownership belongs to the feature-level coordinator that dispatched the role. The Global Project Manager may supervise portfolio health, but it is not the normal watch owner for feature-level child threads.

Immediately after dispatch, the coordinator must do one of:

- keep an active watch on the child thread/session until it returns;
- create a feature-scoped heartbeat/monitor owned by the feature coordinator;
- explicitly record `Monitoring not active` with the reason and the smallest user or project-manager action required to resume the flow.

The handoff is incomplete if the coordinator only says "I will wait" without a concrete wake-up path.

Do not use a Global Project Manager heartbeat as the normal watch path for a feature dispatch. A Global Project Manager monitor is allowed only as an escalation or portfolio audit mechanism, such as detecting stale coordinators, missing watch paths, or returned child work that the feature coordinator failed to process.

Global Project Manager portfolio audits should use `python3 scripts/audit_agent_flow_health.py` before reading individual coordinator or child-agent conversation context. The audit may mark `context_required: yes` for missing Return Gates, contradictory status, repeated escalation, or unclear blockers. If it does not, prefer repo-native state and returned summaries over reading full conversations.

When a child role returns and the feature coordinator is idle, the Global Project Manager may send the returned result back to the feature coordinator and instruct it to apply the Coordinator Return Gate. That is a recovery path, not the designed steady state.

## Deploy Intent And Serialization

Production deploy or service restart is a shared global resource. A Feature Coordinator may request or trigger deploy, but it must use the shared GitHub Actions deploy workflow or Ops API deploy path and must not bypass the deploy lock with ad hoc SSH, direct `docker compose up`, or service restarts unless the user explicitly asks for urgent manual recovery.

Before requesting or triggering production deploy, the coordinator must record or report:

```markdown
Deploy Intent:
- Feature:
- Ref or commit:
- Deploy mode: quick | full | restart-only
- Affected services:
- Reason:
- Verification URL or command:
- Watch owner/path:
```

The deploy request is incomplete if the affected services, verification target, or watch owner is unknown.

GitHub Actions production deploys use the `production-deploy` concurrency group. If another deploy is already running or queued, do not launch a second deploy channel for the same ref. Wait, record the blocker, or let the shared deploy path serialize the request.

The current Ops API already has an in-process mutex and file lock for `/ops/deploy`. P0 does not add a separate deploy queue; use `Delivery-Queue.md` to record deploy intent, deploy completion, or `blocked` state. Add a dedicated Deploy Queue only if Delivery Queue becomes too noisy.

## Deploy Decision Gate

## Standing Owner Delivery Authority

When an Owner has explicitly directed a Feature Coordinator to autonomously close a feature (for example, "do not ask routine questions" or "carry this through deployment and acceptance"), the coordinator must treat normal, project-approved delivery mechanics as already authorized for that feature flow. This includes pushing a verified non-force branch through the repository's approved credential mechanism and triggering the documented serialized deployment path.

The coordinator must not interrupt the Owner for a second confirmation for each routine push, merge, or standard deploy. It must still escalate before acting when any of the following is true:

- a new secret type, storage location, external recipient, or credential scope is required;
- the approved credential mechanism fails, is ambiguous, or would expose a secret value;
- a force-push, history rewrite, destructive data operation, permission change, or non-standard production access is proposed;
- a live cross-feature release conflict or an explicit Owner pause exists.

This authority never permits printing, committing, logging, or transmitting a credential value. The coordinator records only the ref, deploy intent, outcome, and non-secret evidence.

Every coordinator return involving a cloud-served or browser-tested feature must make a concrete deploy decision before the coordinator stops.

Allowed deploy decisions:

- `self_deploy`: the feature coordinator has the required permission, no active deploy conflict is known, Deploy Intent is complete, and it will trigger the shared deploy path itself.
- `dispatch_deploy_owner`: deployment needs another role/session; the coordinator dispatches a named owner with the exact ref or commit, deploy path, affected service or URL, verification target, and watch path.
- `blocked`: deployment cannot proceed; the coordinator records the exact blocker, such as missing credentials, active deploy conflict, merge conflict, unpushed ref, unknown service, or user pause.
- `not_required`: no cloud deploy is needed; the coordinator records why, such as docs-only change, local-only fixture, rejected branch, or acceptance not tied to the cloud surface.

The deploy decision is not valid if it uses a vague owner such as `Coordinator/Ops`, `someone`, `later`, or `after deploy`. If the coordinator itself is the right owner, say `self_deploy` and continue through the shared deploy path. If another owner is required, name the role or thread and dispatch it when tools are available.

## Coordinator Return Gate

Dispatch is not closed when another role/thread/session is created. A dispatched role's final response or pushed branch means the work has returned to the coordinator for review.

When a dispatched role returns, the coordinator must:

1. Inspect the returned response, branch, commit, changed files, verification, queue updates, and lesson statement.
2. Decide whether the returned work should be integrated, rejected, or sent back for correction.
3. If integrating a branch, preserve newer `main` rules and cherry-pick or manually port only the valid returned changes when the branch was based on an older main.
4. Update `docs/project-management/Delivery-Queue.md`:
   - mark the returned role's row as `returned`, `closed`, or `blocked`;
   - record the returned branch or commit when known;
   - create a new row for the next role when more work is required.
5. Update `Feature-Registry.md`, `Acceptance-Queue.md`, PRD, or technical plan state when the returned work changes durable delivery truth.
6. Run the relevant delivery audit and narrow verification.
7. Commit and push the coordinator's verified integration or state update to the relevant delivery/release branch when the target is clear; do not ask the Owner whether to push normal coordinator work.
8. Continue dispatching the next owner when dispatch tools are available and the next action is clear, or record `Dispatch not executed` / `blocked` with the smallest required user action.

The coordinator must not present "role completed" as "feature completed" unless the completion gates are satisfied. A role branch that remains only on `origin/codex/...` is not authoritative project state until it is integrated into `main` or explicitly recorded as rejected/blocked.

The Coordinator Return Gate must end with one of the Feature Ownership Closure Contract actions: `accept_and_route`, `reject_and_return`, `blocked_with_owner`, or `ready_for_user_acceptance`.

If the returned or coordinator branch changes durable delivery state, the coordinator must also apply the State Reconciliation Gate before portfolio status is reported:

1. Compare the returned/coordinator ref with the authoritative project branch for `Feature-Registry.md`, `Acceptance-Queue.md`, `Delivery-Queue.md`, and linked PRD/technical-plan files.
2. Preserve newer authoritative changes from unrelated features; do not merge a stale coordinator branch wholesale if it would revert other project state.
3. Cherry-pick or manually port only the valid feature-specific state and evidence.
4. Run `python3 scripts/audit_agent_flow_health.py --compare-ref <returned-ref> --feature "<feature>"` when a returned ref is known.
5. Record the result as `reconciled`, `rejected`, or `blocked_with_owner`.

For cloud-served or browser-tested features, a Development Agent return that says "code fixed and pushed" is not enough to close the coordinator loop. If the returned fix is not yet merged, deployed, and retested on the real cloud entrypoint, the coordinator must immediately create or dispatch the next owner for that gap:

- `Development Agent` when the returned branch still needs merge conflict resolution, release prep, or deployment implementation work.
- `Release/Deploy owner` when the branch is ready but the cloud service has not been updated.
- `Quality & Acceptance Lead` only when the selected L2/L3 route requires independent acceptance and the relevant cloud service has been deployed or the coordinator has recorded why cloud deployment is not required.

The coordinator's next action must name the exact branch or commit to deploy, the intended deploy path, the affected service or URL, and the retest owner. It must not stop at "after deploy, retest" without either executing the dispatch or recording `Dispatch not executed` with the smallest required user/project-manager action.

Before stopping, the coordinator must pass the Deploy Decision Gate above. A response that says "next step is Coordinator/Ops deploy" has not passed the gate because it does not assign a concrete owner or action.

Every returned role should make the coordinator's next step obvious by ending with:

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
```

## Routing Rules

Route to Product Agent when:

- PRD scope, non-goals, acceptance criteria, or product priority is unclear.
- A feature has no PRD but appears substantial.
- A remaining gap may be moved out of scope only by product decision.

Route to Development Agent when:

- The PRD and technical plan are ready enough for implementation.
- A failed acceptance test requires a code, data, service, or deployment fix.
- A technical plan needs implementation traceability or verification evidence.

Route to Quality & Acceptance Lead when:

- The selected L2/L3 route requires an independent real-surface result.
- A repeated defect, flaky test, or duplicate-suite concern needs test-system stewardship.
- A failed or blocked acceptance queue item has been fixed and needs retest.
- The user asks whether a feature is ready for acceptance.

Route to Project Management Agent when:

- Registry, acceptance queue, PRD, or technical-plan status is missing, stale, or conflicting.
- A delivery audit is needed.
- Old documents may be superseded or misleading.
- Completed work may have missed lesson capture.

## Completion Gates

A feature is not ready to present as done unless:

- PRD status is `ready`, `not_applicable` with reason, or the exception is explicit.
- Technical plan status is `ready`, `implemented`, `not_applicable` with reason, or the exception is explicit.
- Implementation and evidence statuses match the actual state.
- User-facing or cloud-served features have an acceptance queue row with `passed` or `not_required`.
- User acceptance is `accepted` only when the user explicitly accepted it.
- Durable lessons were recorded in the right place, or the handoff says `Lessons: none` with a reason.
- The branch or worktree is clean, or every remaining dirty file is explained.
- Any dispatched role result that affects the feature has passed the Coordinator Return Gate, and no open `dispatched` or `returned` queue item has a clear next action left unhandled.

## Audit And Automation

Use `python3 scripts/audit_delivery_state.py` for delivery-system checks.

Use it before:

- answering broad product-delivery status questions;
- handing off substantial work;
- asking the user for acceptance;
- weekly or milestone project review;
- cleaning documentation state.

Common commands:

- `python3 scripts/audit_delivery_state.py`: full delivery gap audit.
- `python3 scripts/audit_delivery_state.py --feature "Kline Agent"`: feature-specific delivery status.
- `python3 scripts/audit_delivery_state.py --handoff-packet "Kline Agent"`: coordinator handoff packet.
- `python3 scripts/audit_delivery_state.py --dispatch-prompt "Kline Agent"`: next-role prompt suitable for dispatching to a role/thread.
- `python3 scripts/audit_delivery_state.py --handoff --strict`: pre-handoff gate including worktree cleanliness.

The audit script is not the final authority. It finds likely gaps. The coordinator must still read the linked PRD, technical plan, registry row, acceptance queue row, and evidence before making a high-impact claim.

## Learning Gate

The coordinator should check lesson capture at handoff, but it should not write lessons as a diary.

Record a lesson only when it is:

- based on user correction, repeated workflow failure, or concrete delivery evidence;
- reusable for future tasks;
- written to the narrowest durable document.

Routine progress notes belong nowhere by default. Durable state goes to `docs/当前工程状态.md`, milestones go to `docs/project-history.md`, delivery state goes to `docs/project-management/Feature-Registry.md`, and acceptance state goes to `docs/project-management/Acceptance-Queue.md`.

## Role Learning Loop

For every substantial delivery flow that routes work across Product, Development, Quality & Acceptance, or Project Management, the coordinator must close the loop on role learning before declaring the flow done.

The coordinator must check and report:

- Product learning: whether a product scope decision, acceptance standard, user preference, or rejected direction should update the PRD or product protocol.
- Engineering learning: whether an implementation assumption, source constraint, verification limit, deployment lesson, or technical follow-up should update the technical plan or engineering handoff.
- Testing learning: whether a new acceptance dimension, blind spot, failure mode, browser/tooling limit, or evidence standard should update the Quality & Acceptance protocol or queue.
- Coordinator learning: whether routing, dispatch, state tracking, or handoff behavior should update this protocol, `AGENTS.md`, `docs/agent-lessons.md`, or project-management state.

The coordinator must apply the quality bar and anti-overlearning guardrail from `../lesson-capture-protocol.md`.

The operating rule is: check always, record rarely, place narrowly, and review stale lessons. A role learning item should be recorded only when it comes from user correction, repeated workflow failure, or concrete delivery evidence and will improve future delivery. The coordinator must not write lessons merely to show that the system is evolving.

If an existing lesson becomes stale, too broad, contradicted by later evidence, or replaced by a clearer higher-authority rule, the coordinator may route or perform cleanup by merging, replacing, marking it superseded, or removing it from the narrowest durable document.

Every final coordinator summary for a substantial flow must include one of:

- `Role learning recorded: <files updated and short reason>.`
- `Role learning: none; <short reason>.`
