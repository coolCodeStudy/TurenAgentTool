# Agent Operating Model Roadmap

This roadmap tracks improvements to the repo-native agent delivery system. It is for operating-model infrastructure, not product-feature delivery. Product features still belong in `Feature-Registry.md`, `Acceptance-Queue.md`, and `Delivery-Queue.md`.

## Goal

Make the agent organization behave more like a small accountable delivery team:

- The Owner sets direction, priority, key tradeoffs, credentials or permission decisions, and final user acceptance.
- Feature Coordinators own single-feature closure.
- The Global Project Manager owns portfolio health, operating-model defects, stale-flow recovery, and cross-feature conflicts.
- Role agents return evidence in a shape the coordinator can act on.
- Delivery flow quality is measured by repo-native evals, not inferred from chat confidence.

## Current Baseline

Already implemented:

- `AGENTS.md` as mandatory operating preflight.
- `docs/product/Agent-Operating-Model.md` as the top-level multi-role contract.
- `docs/product/Delivery-Coordinator-Protocol.md` as the feature-level coordination protocol.
- `scripts/audit_delivery_state.py` for registry, PRD, tech-plan, acceptance, and daily-log checks.
- `scripts/audit_agent_flow_health.py` for coordinator health, stale rows, deploy conflicts, Global PM overuse, and state reconciliation.
- Feature Registry, Acceptance Queue, and Delivery Queue as repo-native delivery state.
- Lesson capture protocol and anti-overlearning guardrail.

## P0: Closure And Evaluation

Status: active.

Purpose: stop repeated coordinator non-closure and make regressions measurable.

Deliverables:

- Agent-flow eval cases based on real historical failure patterns.
- A local eval runner that validates `audit_agent_flow_health.py` against those cases.
- Coordinator context packet template for takeover, dispatch, return gate, and recovery.
- Source-of-truth links in `AGENTS.md`, `docs/README.md`, and role protocols.

Success criteria:

- A future change to coordinator rules can run a deterministic eval before handoff.
- A Feature Coordinator takeover prompt has enough context to act without re-asking the Owner.
- Global PM can distinguish normal feature routing from true escalations.

## P1: Role Skills And Review Lanes

Status: active.

Purpose: make common role handoffs repeatable without forcing the Owner to rewrite prompts.

Deliverables:

- Prompt templates for:
  - Feature Coordinator.
  - Release Integration.
  - Acceptance Testing.
  - Deploy Conflict Resolution.
  - Frontend Review.
- Template guidance that each prompt must name inputs, source docs, expected return shape, deploy decision, and escalation boundary.
- Reviewer lanes for release compatibility, UX/frontend consistency, and acceptance evidence.
- Deploy classification extracted from workflow shell into `scripts/classify_deploy_change.py`, backed by `tests/test_deploy_change_classifier.py` and documented in `docs/project-management/Deploy-Classification.md`.

Success criteria:

- A coordinator can dispatch normal next-owner work from a template.
- A returned role result is easy to accept, reject, or route onward.
- Global PM intervention is reserved for stale coordinators, missing watch paths, credentials/permissions, user decisions, and cross-feature conflicts.
- Governance/docs/tests-only changes can push through `main` with a successful `no_deploy` job instead of restarting production or getting stranded on a feature branch.

## P1.1: Deploy Admission Reliability

Status: P0 merged to authoritative `main@08ce339`; credential-precedence hotfix in progress.

This is operating-model/control-plane infrastructure, not a Feature Registry item.
It addresses the confirmed 2026-07-16 release failures: GitHub Actions runs
`29511640343` and `29512741489` reached the private Ops API but were rejected
before activation because `MemAvailable` was below the 512 MiB quick/config
reserve. The failure was neither a GitHub-token nor a deploy-lock failure.

P0 delivered and merged locally reviewed controls for forward-only authoritative refs,
one GitHub Actions coordinator channel with an internal Ops executor, durable
event/health/service/route evidence, mode-specific memory gates, isolated
full-image artifacts, and separate browser, command, and Ops credentials.
The serialized independent Ops API bootstrap using a distinct `OPS_API_TOKEN`
completed in run `29624982764`; an ordinary app release cannot update
`/opt/investment-ops`. The first deploy-plan retries correctly stopped before
activation with 401 because a stale business `.env` overwrote the explicitly
passed control-plane credential during install. The narrow follow-up preserves
the explicit credential and adds a regression test before the next bootstrap.

P1 follow-up: collect memory, PSI, cgroup, swap, and full-image phase telemetry
from successful and rejected deploys, then calibrate target-aware reserves.
Consider registry/digest delivery only after provenance, retention, rollback,
and credential ownership are specified; do not replace the verified archive
path opportunistically.

## P2: Context Retrieval And Memory

Status: deferred.

Purpose: improve context quality after repo-native docs and evals prove useful.

Deferred items:

- SQLite or other local memory store for task outcomes and eval results.
- RAG over product docs, tech plans, lessons, and project-management state.
- LLM judge for review assistance.
- Automatic hooks that block invalid handoffs or routine daily-log creation.
- GitHub `environment: production` protection and stricter deploy queue semantics, after confirming they will not reintroduce Owner approval friction for normal releases.

Deferral reason:

The current repository can still get high leverage from deterministic docs, scripts, and templates. Heavy memory/RAG/judge infrastructure should wait until the failure modes are stable enough to measure.

## Operating Principles

- Process control and result evaluation both matter.
- A pushed branch is an input to a return gate, not delivery closure.
- Context should be packed narrowly for the current role and feature.
- Lessons are checked every substantial flow and recorded rarely.
- Eval failures should improve scripts, protocols, or templates rather than create more chat instructions.
