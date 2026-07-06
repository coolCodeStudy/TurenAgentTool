# Coordinator Context Packet

Use this packet when creating, resuming, or taking over a Feature Coordinator flow. It is the minimum context package a coordinator needs before dispatching role agents or reporting status.

## Packet

```markdown
# Coordinator Context Packet

- Feature:
- Coordinator thread/session:
- Owner intent:
- Operating model source: `docs/product/Agent-Operating-Model.md`
- Feature protocol source: `docs/product/Delivery-Coordinator-Protocol.md`
- Product doc / PRD:
- Technical plan:
- Feature Registry row:
- Acceptance Queue row:
- Delivery Queue rows:
- Current authoritative branch/ref:
- Related coordinator branch/ref:
- Current deployed ref or deploy event:
- User-facing surface:
- Current state:
- Known blockers:
- Active child threads or role sessions:
- Watch contract:
  - Watched item:
  - Wake event or cadence:
  - Expected return artifact:
  - Coordinator action on wake:
- Next owner:
- Next handoff:
- Deploy needed:
- Deploy decision:
- Escalation target:
- User decision needed:
- Completion gate:
- Role learning check:
```

## Usage Rules

- Fill this packet before starting a new Feature Coordinator when the feature already has delivery history.
- Refresh this packet before reading long chat history. Repo-native state is first-line evidence.
- If a child role has returned, the packet must name the returned branch, commit, verification, and queue row before the Coordinator Return Gate begins.
- If the coordinator cannot maintain a runtime watch path, record `Monitoring not active` and the smallest resume action.
- Do not use this packet to route normal feature work to the Global Project Manager. It should clarify why the Feature Coordinator can continue or why a true escalation exists.

## Minimum Sources

Read these sources before filling the packet:

- `AGENTS.md`
- `docs/product/Agent-Operating-Model.md`
- `docs/product/Delivery-Coordinator-Protocol.md`
- `docs/project-management/Feature-Registry.md`
- `docs/project-management/Acceptance-Queue.md`
- `docs/project-management/Delivery-Queue.md`
- Linked PRD and technical plan when present.

Run these scripts when applicable:

- `python3 scripts/audit_delivery_state.py --feature "<feature>"`
- `python3 scripts/audit_agent_flow_health.py --feature "<feature>"`
- `python3 scripts/audit_agent_flow_health.py --compare-ref <coordinator-ref> --feature "<feature>"` when a coordinator branch may be ahead of authoritative state.
