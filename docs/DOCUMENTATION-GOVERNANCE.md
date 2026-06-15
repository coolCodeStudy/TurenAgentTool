# Documentation Governance

This file defines how documentation should stay understandable and avoid decay.

## Goals

- Give agents and humans one reliable starting point.
- Make canonical docs easy to identify.
- Prevent stale implementation plans from pretending to be current truth.
- Keep documentation useful without creating routine diary logs.

## Language

- Repository documentation should be written in English.
- Chinese command examples, user-facing product phrases, source quotes, existing filenames, and domain terms may remain when they are part of actual system behavior or source material.
- Do not do broad translation in an unrelated implementation branch.

## Required Metadata For New Long-Lived Docs

Add this block near the top of new long-lived docs:

```text
Status: draft | active | implemented | superseded | archived
Owner: product | architecture | engineering | operations | agent
Last reviewed: YYYY-MM-DD
Canonical: yes | no
Supersedes: path or none
```

Existing docs do not need an immediate mass update. Add metadata when a doc is substantially edited.

## Status Meanings

| Status | Meaning | Maintenance Rule |
| --- | --- | --- |
| `draft` | Still being shaped | Keep scope explicit; do not treat as implementation truth. |
| `active` | Current source for ongoing work | Keep acceptance criteria and next steps current. |
| `implemented` | Work mostly landed | Link to current state and keep as historical implementation record. |
| `superseded` | Replaced by another doc | Add a link to the replacement; avoid editing except for pointers. |
| `archived` | Kept for history only | Do not use for planning. |

## Canonical Sources

- Current system facts: `docs/当前工程状态.md`.
- Durable milestones: `docs/project-history.md`.
- Reusable agent lessons: `docs/agent-lessons.md`.
- Product strategy: `docs/product/Product-Strategy-and-Roadmap.md`.
- Product-agent rules: `docs/product/Product-Agent-Working-Protocol.md`.
- Documentation map: `docs/README.md`.

If two documents disagree, prefer the canonical source above and update or mark the stale one.

## Update Rules

Update docs when:

- Product behavior, product scope, or acceptance criteria changes.
- API contracts, database schema, worker behavior, or deployment behavior changes.
- A tech plan moves from draft to active, implemented, or superseded.
- A new lesson would prevent future agents from repeating a mistake.
- The recommended next step changes.

Do not update docs for:

- Temporary command output.
- One-off debugging details.
- Routine daily progress notes.
- Unreviewed model speculation.

## File Placement

| Type | Location |
| --- | --- |
| Product strategy and PRDs | `docs/product/` |
| Implementation plans | `docs/techplans/` |
| Architecture and data model | `docs/` top level until a future architecture folder migration |
| Operations and deployment | `DEPLOYMENT.md` and ops/deployment docs under `docs/` |
| Agent lessons | `docs/agent-lessons.md` |
| Milestones | `docs/project-history.md` |

## Rename And Move Rules

- Prefer adding indexes before moving many files.
- Before renaming a doc, run `rg` for all references to the old path.
- Rename/move docs in a dedicated branch.
- Update `docs/README.md`, local references, scripts, prompts, and AGENTS references in the same commit.
- Do not rename Chinese filenames opportunistically; do it only as a deliberate migration.

## Tech Plan Lifecycle

Every tech plan should answer:

- What product or operational problem does it solve?
- What is in scope and out of scope?
- What modules, schema, APIs, jobs, or services change?
- How is it locally verified?
- How is it remotely verified if cloud behavior is involved?
- What is the rollback or fallback path?
- What status is it in now?

When implementation finishes, either:

- Mark the plan `implemented` and link to current state, or
- Move the remaining work into a new active plan and mark the old one superseded.

## Product Doc Lifecycle

Every product doc should answer:

- Who is the user?
- What problem is being solved?
- What is explicitly not being solved?
- What is the user flow?
- What are acceptance criteria?
- What is the metric or review signal?

Product docs should not become engineering design dumps. Link to tech plans for implementation detail.

## Closeout Rule

At the end of a non-trivial task, the agent must state whether documentation was updated or why no documentation update was needed.

