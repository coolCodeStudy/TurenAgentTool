# Coordinator Context Packet

Use this packet when creating, resuming, or taking over a Feature Coordinator flow. It is the minimum context package a coordinator needs before dispatching role agents or reporting status.

## Active Packet: Stock valuation research

```markdown
# Coordinator Context Packet

- Feature: Stock valuation research
- Coordinator thread/session: Codex feature-coordinator task delegated from `019f3821-3e6c-79b3-96b3-a5e91aaaa184`
- Owner intent: Completely close the feature; make ordinary product and technical choices autonomously and escalate only irreducible decisions or cross-feature conflicts.
- Operating model source: `docs/product/Agent-Operating-Model.md`
- Feature protocol source: `docs/product/Delivery-Coordinator-Protocol.md`
- Product doc / PRD: `docs/product/PRD-Stock-Valuation-Research.md`
- Technical plan: `docs/techplans/stock-valuation-research.md`, ready at coordinator commit `fc07ebc`; it replaces the stale historical plan for current-main delivery.
- Feature Registry row: `Stock valuation research`
- Acceptance Queue row: `AT-2026-07-19-001` is the single active current-main release-candidate item. Historical rows on stale refs are context only and are not parallel gates.
- Delivery Queue rows: Product recovery `DQ-2026-07-19-002` and technical planning `DQ-2026-07-19-003` are closed; current implementation/release-candidate ownership is compacted into `DQ-2026-07-19-004`.
- Current authoritative branch/ref: coordinator branch merge `bddfa0f`, including `origin/main@ba49ccf`; the exact 117-test valuation/preservation suite passed after reconciliation.
- Related coordinator branch/ref: `codex/stock-valuation-research`; historical recovery source `origin/codex/release-kline-stock-valuation-p03@acd9856`
- Current deployed ref or deploy event: Latest repo-native production evidence is architecture deploy `main@86652e4`; current cloud valuation action availability must be rechecked after integration.
- User-facing surface: Cloud Command Workbench at `http://47.84.190.191:8010/command`
- Quality route: `L3`
- Route rationale: The feature changes an authenticated cloud Command Workbench, external data-source behavior, saved evidence, and the deployed release boundary.
- Release-verification manifest (ref, route, surface, evidence, unresolved exceptions): Release ref pending Development; route `L3`; surface `http://47.84.190.191:8010/command`; accepted evidence is Task 1 review plus 40 valuation tests, the 759-passed/1-skipped repository run, the post-reconciliation 117-test preservation suite, and accepted Task 2 head `a653725` with 110/110 coordinator tests and clean independent re-review; plan traceability covers all 17 PRD criteria; deploy event and independent result are pending; no protected credential value may enter evidence.
- Current state: Product-ready PRD commit `91b741b`, ready current-main technical plan commit `fc07ebc`, Task 1 domain/artifact range `fc9ab36..dd88c2e`, and Task 2 provider/source range `47b69c1..a653725` are accepted. Task 2's initial return was rejected for false official-attempt provenance; the corrected default path now performs distinct DART/FSS/SK hynix probes, preserves bounded company identity, distinguishes truthful attempt states, passes 110 coordinator tests, and is independently approved. Task 3 router/Workbench integration is active.
- Known blockers: No product blocker and no current cross-feature integration blocker. One non-blocking Task 2 review item remains for final triage: HK official collection is redundantly repeated per source category.
- Active child threads or role sessions: One fresh Task 3 Development Agent for Command Router and authenticated Workbench actions. This Feature Coordinator owns the active polling/watch path and will apply the Return Gate immediately on completion.
- Watch contract:
  - Watched item: Development implementation/review return, serialized deploy, and one Quality & Acceptance return for release candidate `AT-2026-07-19-001`.
  - Wake event or cadence: This coordinator polls each child role until return; no Global PM heartbeat is the normal watcher.
  - Expected return artifact: Exact decisions or commit, verification evidence, remaining gaps, deploy decision, and role-learning statement.
  - Coordinator action on wake: Apply the Coordinator Return Gate, update registry/queues, then accept-and-route, reject-and-return, block with a named owner, or declare ready for user acceptance.
- Next owner: Task 3 Development Agent for Command Router and authenticated Workbench actions, watched by this Feature Coordinator.
- Next handoff: Return deterministic no-network router/Workbench tests for the four actions, exact preview commands, safe artifact create/latest/evidence/method behavior, preserved stock-bootstrap/access contracts, and a clean `feat: expose stock valuation in command workbench` commit for independent review.
- Deploy needed: Yes after current-main integration because the accepted surface is cloud Command Workbench.
- Deploy decision: `blocked` until a current-main-compatible implementation ref passes Development and review gates; then `self_deploy` through the shared workflow if no serialized deploy conflict exists.
- Escalation target: Global Project Manager only if current-main integration exposes a real cross-feature release conflict; Owner only for final user acceptance or an irreducible decision.
- User decision needed: None for Product/technical delivery; final user acceptance remains explicit and cannot be inferred.
- Completion gate: Independent cloud acceptance must pass before `ready_for_user_acceptance`; `product_done` additionally requires explicit Owner acceptance.
- Role learning check: Pending completion evidence; record only reusable lessons that pass `docs/lesson-capture-protocol.md`.
```

## Reusable Packet Template

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
- Quality route: `L0` / `L1` / `L2` / `L3`
- Route rationale:
- Release-verification manifest (ref, route, surface, evidence, unresolved exceptions):
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
- Select the smallest quality route before dispatch. Do not add an independent acceptance handoff to L0/L1 work unless the PRD or changed risk boundary requires it.
- Keep one active release-verification manifest and one active Acceptance Queue row per user-facing release candidate. Close accepted micro-return rows rather than preserving them as open coordination work.
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
