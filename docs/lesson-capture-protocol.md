# Lesson Capture Protocol

This repository treats learning as part of delivery. Product managers, developers, and project-management agents should preserve durable lessons in the repository so future sessions do not relearn the same thing from chat history.

This protocol is not a daily log system. Capture only lessons that should change future product decisions, engineering behavior, verification practice, project tracking, or operating rules.

## When To Capture A Lesson

Check for durable lessons before handoff whenever a task includes any of these:

- A product decision, scope correction, rejected direction, or user preference that should shape future PRDs.
- A PRD, technical plan, implementation, deployment, verification, or acceptance milestone.
- A bug, failed assumption, missed requirement, broken workflow, or repeated confusion.
- A verification limit, cloud/local environment difference, data-source limitation, or service-boundary discovery.
- A documentation cleanup, stale-doc discovery, superseded plan, or delivery-status correction.
- A user correction about how the team should work.

If there is no durable lesson, say so in the handoff summary with a short reason.

## Where Lessons Go

Choose the narrowest durable home. Do not create a new dated log unless the user explicitly asks for one.

| Lesson type | Destination |
|---|---|
| Cross-task agent behavior, recurring mistakes, safety, verification, Git, deployment, or operating discipline | `docs/agent-lessons.md` |
| Mandatory operating rule that all agents must follow before changing code, docs, services, Git, or deployment state | `AGENTS.md` |
| Product positioning, user preference, product principle, roadmap direction, or product acceptance learning | The relevant PRD under `docs/product/`, `docs/product/Product-Strategy-and-Roadmap.md`, or a future product decision record |
| Technical design or implementation learning for a feature | The relevant technical plan under `docs/techplans/` |
| Delivery-status, PRD/tech-plan linkage, implementation evidence, verification evidence, or next-action learning | `docs/project-management/Feature-Registry.md` |
| Current runtime, environment, deployment, or architecture state | `docs/当前工程状态.md` |
| Durable milestone already completed | `docs/project-history.md` |
| Documentation ownership or stale-document routing rule | `docs/README.md` or the document's status note |

When a lesson applies to more than one destination, update the highest-authority rule and add links from lower-level documents only when needed.

## Quality Bar

A good lesson is:

- Durable: it should still matter in a later session.
- Actionable: it changes a decision, workflow, check, or standard.
- Scoped: it names the area where it applies.
- Evidence-aware: it distinguishes observed facts from inference.
- Short: one concise bullet is usually enough.

A poor lesson is:

- A diary entry.
- A transcript summary.
- A blame note.
- A raw secret, token, credential, private account detail, or unredacted customer data.
- An unverified guess written as a rule.
- A vague reminder such as "be careful" without a concrete trigger or action.

## Required Handoff Statement

Every substantial task handoff should include one of these:

- `Lessons recorded: <files updated and short reason>.`
- `Lessons: none; <short reason>.`

Do this after verification and before declaring the task complete.

## Role Responsibilities

Product Agent:

- Captures product decisions, product principles, acceptance learning, and user preference changes in product docs.
- Does not leave important product decisions only in chat.

Development Agent:

- Captures implementation, verification, deployment, environment, and source-gap lessons in the relevant technical or operating docs.
- Updates delivery state when a lesson changes implementation or verification status.

Project Management Agent:

- Checks whether completed work captured required lessons.
- Flags missing lesson capture during audits.
- Updates registry or documentation routing when evidence is present.
- Does not invent product or technical lessons without source evidence.

## Examples

Good examples:

- `Cloud-served UI fixes require cloud verification after local tests pass; localhost is not user acceptance evidence.`
- `A feature with implementation evidence but no acceptance-criteria check remains product-incomplete.`
- `If a source gap affects the user-facing decision card, keep the diagnostic visible until the source is implemented or explicitly out of scope.`
- `When several Codex sessions are active, non-trivial edits must happen in a task worktree based on origin/main.`

Bad examples:

- `Worked on the weekly review today.`
- `The deployment was annoying.`
- `Need to be more careful.`
- `Maybe the API is flaky.`
