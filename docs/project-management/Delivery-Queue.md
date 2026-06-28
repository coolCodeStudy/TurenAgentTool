# Delivery Queue

This queue tracks Delivery Coordinator dispatches across Product, Development, Acceptance Testing, and Project Management.

Use `docs/product/Delivery-Coordinator-Protocol.md` for role boundaries, dispatch rules, and fallback behavior.

This file is not a daily log. Add a row only when work is actively dispatched, returned, blocked, or closed.

## Status Values

- `ready_to_dispatch`: The coordinator has identified the next owner and prepared a dispatch prompt.
- `dispatched`: Work was sent to a role/thread/session.
- `in_progress`: The receiving role has started work.
- `returned`: The receiving role returned output for coordinator review; the coordinator must still integrate, reject, close, block, or dispatch the next owner.
- `blocked`: Dispatch or execution is blocked.
- `closed`: The coordinator reviewed the returned work and no further dispatch is needed for this queue item.

## Queue

| ID | Feature | Target Role | Dispatch Status | Thread Or Branch | Source | Expected Result | Next Action |
|---|---|---|---|---|---|---|---|
| DQ-2026-06-28-001 | Weekly review generator | Development Agent | closed | thread `019f09ec-9eae-7b90-a87e-a3626cb2fe1d`; branch `origin/codex/weekly-review-generator-fix`; dev commit `44b48f3`; main integration `445a892` | `scripts/audit_delivery_state.py --dispatch-prompt "Weekly review generator"` from main commit `febac51` | Fix Weekly Review Web acceptance blocker, update registry/traceability, and move `AT-2026-06-25-001` to `needs_retest` when ready. | Closed after main commit `2b376b7` deployed and cloud acceptance retest passed. |
| DQ-2026-06-28-002 | Weekly review web | Acceptance Testing Agent | closed | thread `019f09fb-9bfc-77d1-b479-1d16a392d3bc`; worktree `/Users/lishaocheng/.codex/worktrees/4b40/TurenAgentTool` | Main commit `b3a228d`; GitHub Actions deploy run `28295470409`; Acceptance Queue row `AT-2026-06-25-001` | Retest the real cloud Weekly Review Web URL and update acceptance state without marking user acceptance accepted. | Closed by coordinator retest evidence `/tmp/weekly-review-acceptance-retest-20260628-v2.json` and `/tmp/weekly-review-acceptance-generate-20260628.json`; user acceptance remains pending. |
| DQ-2026-06-28-003 | Weekly review generator | Product Agent | closed | pending worktree `local:9876462c-7554-4133-8445-60bf3b47d14e`; returned branch `origin/codex/weekly-review-source-criteria`; returned commit `c9e6652` | Coordinator dispatch from main commit `0e3400a`; Acceptance Queue row `AT-2026-06-28-001` | Define the minimum acceptable index context, external event/news/theme context, and source-backed overall-story bar before Engineering updates the technical plan and implements the fix. | Closed by Coordinator Return Gate after integrating the Product acceptance criteria into main-state docs; Engineering follow-up is tracked by `DQ-2026-06-28-004`. |
| DQ-2026-06-28-004 | Weekly review generator | Development Agent | blocked | development thread `019f0c3b-8f37-74a3-b0d9-030a69bdbacc`; returned branch `origin/codex/weekly-review-source-completeness`; returned commit `ce36764`; integrated on `main` through `8147cb8`; full deploy run `28326192300` | Product resolution for failed `AT-2026-06-28-001`; PRD addendum in `docs/product/PRD-每周复盘.md`; registry and acceptance-queue updates in main; Coordinator Return Gate accepted and integrated the returned branch | Update `docs/techplans/weekly-review.md` before implementation, covering source providers, fallback/source-status semantics, story-generation inputs, verification, and acceptance criteria; then implement source-backed story generation for indexes, external events/news/themes, and user knowledge inputs. | Full deploy succeeded and cloud force-refresh on `2026-06-22` generated the new story structure, but cloud source verification is still blocked: `source_status.indexes.status=provider_unavailable`, `source_status.events.status=source_blocked`, `index_summary=[]`, `event_summary=[]`, and only local knowledge evidence is present. Do not route to Acceptance Testing until Engineering/Ops makes index and external-event/provider evidence available or Product explicitly changes the acceptance bar. |

## Rules

- If dispatch tools are available and the user asked the coordinator to follow through, the coordinator should dispatch instead of only producing a handoff.
- If dispatch tools are unavailable, the coordinator must state `Dispatch not executed`, give the reason, and provide the exact next-role prompt.
- When dispatch succeeds, add or update a row with the target role, thread or branch when known, source handoff, expected result, and next action.
- When a role returns a branch or final result, update the existing row through the Coordinator Return Gate before creating or dispatching the next row.
- Do not use this queue for routine status notes. Long-lived delivery truth remains in `Feature-Registry.md` and `Acceptance-Queue.md`.
