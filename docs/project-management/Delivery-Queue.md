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
| DQ-2026-06-28-001 | Weekly review generator | Development Agent | dispatched | `pendingWorktreeId=local:1fd65d59-fd91-4207-a6f6-e1d255397556` | `scripts/audit_delivery_state.py --dispatch-prompt "Weekly review generator"` from main commit `febac51` | Fix Weekly Review Web acceptance blocker, update registry/traceability, and move `AT-2026-06-25-001` to `needs_retest` when ready. | Wait for Development Agent result, then coordinator reviews and dispatches Acceptance Testing retest if ready. |

## Rules

- If dispatch tools are available and the user asked the coordinator to follow through, the coordinator should dispatch instead of only producing a handoff.
- If dispatch tools are unavailable, the coordinator must state `Dispatch not executed`, give the reason, and provide the exact next-role prompt.
- When dispatch succeeds, add or update a row with the target role, thread or branch when known, source handoff, expected result, and next action.
- Do not use this queue for routine status notes. Long-lived delivery truth remains in `Feature-Registry.md` and `Acceptance-Queue.md`.
