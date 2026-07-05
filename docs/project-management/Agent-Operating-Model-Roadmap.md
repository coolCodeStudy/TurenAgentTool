# Agent Operating Model Roadmap

Date: 2026-07-05

This roadmap tracks delivery-system improvements. It is not a product feature backlog.
Product-facing capabilities stay in `docs/project-management/Feature-Registry.md`.
Active operating-model execution is tracked in `docs/project-management/Delivery-Queue.md`.

## Purpose

Reduce Owner coordination load while improving multi-agent delivery quality.
The Owner should set direction, make product trade-offs, approve sensitive permissions, and provide final user acceptance.
Feature Coordinators should close ordinary Product, Development, Deploy, Acceptance, and Learning loops without requiring the Owner to notice stalled handoffs.

## Source Inputs

- Local delivery incidents: Stock valuation, Kline Agent, Command Workbench, Weekly Review.
- `docs/project-management/open-source-agent-methodology-study.md`
- Superpowers: controller/subagent/reviewer discipline and durable ledgers.
- OpenSpec: change-package discipline.
- agent-skills: lifecycle skills, anti-rationalization checks, context engineering, reviewer personas, and ship/launch checklists.

## P0: Coordinator Closure Hardening

Status: completed on 2026-07-05

Goal: A child role/session returning work should automatically produce a coordinator decision, not a user reminder.

Scope:

- Add hard watch-contract language to the Delivery Coordinator protocol.
- Add an anti-rationalization gate for vague handoffs such as `after deploy`, `I will wait`, `Coordinator/Ops`, or `branch pushed`.
- Extend flow-health audit checks for:
  - returned child work not integrated;
  - passive watch paths;
  - deploy needed with no deploy decision;
  - cloud/browser work using vague `after deploy` handoff language;
  - release compatibility missing from deploy-intent rows.

Acceptance:

- `python3 scripts/audit_agent_flow_health.py` can surface coordinator failures from repo-native state.
- Coordinator protocol explicitly requires a watch contract and Return Gate closure before stopping.
- Delivery Queue has one operating-model row for this execution, not a fake product feature.

## P1: Change Package Discipline

Status: completed on 2026-07-05

Goal: Substantial feature work should be resumable from files instead of chat.

Scope:

- Introduce `docs/changes/` as a lightweight repo-native change-package area.
- Add a reusable template:
  - `proposal.md`
  - `requirements.md`
  - `design.md`
  - `tasks.md`
  - `handoff.md`
- Add a verifier script for required files and basic links.

Acceptance:

- `python3 scripts/verify_change_package.py --all` runs without requiring external dependencies.
- The template explains how it relates to PRD, tech plan, Feature Registry, Acceptance Queue, and Delivery Queue.
- Change packages do not replace current truth; accepted changes must be folded back into authoritative docs.

## P2: Risk-Based Reviewer Gates

Status: completed on 2026-07-05

Goal: Add reviewer discipline only at risk points, not as ceremony for every small task.

Scope:

- Define reviewer gates for:
  - Release Reviewer;
  - Frontend Experience Reviewer;
  - Acceptance Reviewer;
  - Security/Access Reviewer.
- Add trigger conditions and expected outputs.
- Connect reviewer gates to Coordinator Return Gate and deploy decisions.

Acceptance:

- Coordinator protocol names when reviewer gates are required or optional.
- Reviewer gates are role checks, not new always-on roles.
- Small docs/status edits remain lightweight.

## Operating Rules

- Do not put operating-model tasks in `Feature-Registry.md` unless they create a user-facing product feature.
- Use `Delivery-Queue.md` for currently active operating-model work and blockers.
- Use this roadmap for plan state and sequencing.
- Commit and push roadmap updates when execution state changes materially.
- Do not create routine daily logs for this work.

## Next Execution Order

1. Use Frontend Experience System as the first real change-package trial.
2. Use the new flow-health audit when a coordinator appears stalled.
3. Add stricter script checks only after another real coordinator failure appears; avoid overfitting from one case.
