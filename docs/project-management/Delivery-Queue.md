# Delivery Queue

This queue tracks Delivery Coordinator dispatches across Product, Development, Acceptance Testing, and Project Management.

Use `docs/product/Delivery-Coordinator-Protocol.md` for role boundaries, dispatch rules, and fallback behavior.

This file is not a daily log. Add a row only when work is actively dispatched, returned, blocked, or closed.

## Status Values

- `ready_to_dispatch`: The coordinator has identified the next owner and prepared a dispatch prompt.
- `dispatched`: Work was sent to a role/thread/session.
- `in_progress`: The receiving role has started work.
- `returned`: The receiving role returned output for coordinator review.
- `blocked`: Dispatch or execution is blocked.
- `closed`: The coordinator reviewed the returned work and no further dispatch is needed for this queue item.

## Queue

| ID | Feature | Target Role | Dispatch Status | Thread Or Branch | Source | Expected Result | Next Action |
|---|---|---|---|---|---|---|---|
| DQ-2026-06-28-001 | Weekly review generator | Development Agent | returned | thread `019f09ec-9eae-7b90-a87e-a3626cb2fe1d`; branch `origin/codex/weekly-review-generator-fix`; dev commit `44b48f3` | `scripts/audit_delivery_state.py --dispatch-prompt "Weekly review generator"` from main commit `febac51` | Fix Weekly Review Web acceptance blocker, update registry/traceability, and move `AT-2026-06-25-001` to `needs_retest` when ready. | Coordinator cherry-picked the fix to local `main` as `445a892`; push `main`, deploy the cloud weekly-review Web surface, then dispatch Acceptance Testing retest if deployment verification passes. |
| DQ-2026-06-28-002 | Weekly review web | Acceptance Testing Agent | dispatched | thread `019f09fb-9bfc-77d1-b479-1d16a392d3bc`; worktree `/Users/lishaocheng/.codex/worktrees/4b40/TurenAgentTool` | Main commit `b3a228d`; GitHub Actions deploy run `28295470409`; Acceptance Queue row `AT-2026-06-25-001` | Retest the real cloud Weekly Review Web URL and update acceptance state without marking user acceptance accepted. | Wait for Acceptance Testing result; if passed, coordinator reviews the queue update and surfaces the feature for user acceptance; if failed, route the precise blocker to the next owner. |

## Rules

- If dispatch tools are available and the user asked the coordinator to follow through, the coordinator should dispatch instead of only producing a handoff.
- If dispatch tools are unavailable, the coordinator must state `Dispatch not executed`, give the reason, and provide the exact next-role prompt.
- When dispatch succeeds, add or update a row with the target role, thread or branch when known, source handoff, expected result, and next action.
- Do not use this queue for routine status notes. Long-lived delivery truth remains in `Feature-Registry.md` and `Acceptance-Queue.md`.
