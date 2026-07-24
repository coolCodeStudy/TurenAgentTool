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
- Technical plan: `docs/techplans/stock-valuation-research.md`, implemented and deployed with the P0.1 valuation-conclusion addendum; the future sourced-scenario calculator remains a separate source-validation contract.
- Feature Registry row: `Stock valuation research`
- Acceptance Queue row: `AT-2026-07-19-001` is the single active current-main release-candidate item. Historical rows on stale refs are context only and are not parallel gates.
- Delivery Queue rows: Product recovery `DQ-2026-07-19-002`, technical planning `DQ-2026-07-19-003`, and prior bilingual release rows are closed; current deployed P0.1 and the protected-acceptance watch are tracked in `DQ-2026-07-23-001`.
- Current authoritative branch/ref: deployed `main@afcda50dd2e8ec14e814b457ec71a2f7301556f5` from serialized workflow `30018619840` (`targeted_quick`/`quick`). No ingress, Compose, or public-port change occurred.
- Related coordinator branch/ref: `codex/stock-valuation-research`; historical recovery source `origin/codex/release-kline-stock-valuation-p03@acd9856`
- Current deployed ref or deploy event: `main@afcda50dd2e8ec14e814b457ec71a2f7301556f5`, serialized deployment workflow `30018619840`; stable public `/health`, `/command`, and action-catalog smoke pass. `/health` may retain historical release metadata, so workflow/ref is provenance.
- User-facing surface: Cloud Command Workbench at `http://47.84.190.191:8010/command`
- Quality route: `L3`
- Route rationale: The feature changes an authenticated cloud Command Workbench, external data-source behavior, saved evidence, and the deployed release boundary.
- Release-verification manifest (ref, route, surface, evidence, unresolved exceptions): deployed `main@afcda50dd2e8ec14e814b457ec71a2f7301556f5`, route `L3`, surface `http://47.84.190.191:8010/command`, workflow `30018619840`. P0.1 local valuation/Workbench/gateway suite passed 125 tests; merged Weekly authorization suite passed 16/16; stable tokenless health/page/catalog smoke and protected-boundary recovery pass. Authenticated valuation acceptance is blocked only for the explicitly protected fixture/session; no protected credential value may enter evidence.
- Current state: Product-ready PRD with bilingual and valuation-conclusion addenda; P0.1 is deployed. Current market valuation is explicit, while a fair-value range truthfully remains unavailable until a typed source-validated scenario bundle exists.
- Known blockers: No code or deploy blocker remains. The protected acceptance workflow `29936409580` completed successfully but skipped because no protected fixture was configured. Protected P0 acceptance still requires an approved secure fixture/session contract, never a token value. No ingress/Compose/public-port change is active.
- Active child threads or role sessions: Prior Product and Acceptance returns are historical. Inline Development returned P0.1 at `472daaa`; this Feature Coordinator accepted, integrated, deployed, and owns the protected-fixture watch for `AT-2026-07-19-001`.
- Watch contract:
  - Watched item: Approved secure non-production fixture/session location and calling contract for the blocked protected P0, then the same independent retest.
  - Wake event or cadence: This coordinator polls each child role until return; no Global PM heartbeat is the normal watcher.
  - Expected return artifact: Approved fixture/session contract, then exact independent evidence matrix for live protected method/create/latest/evidence and deployed Chinese/English P0.1 card parity; no token values.
  - Coordinator action on wake: Apply the Coordinator Return Gate, update registry/queues, then accept-and-route, reject-and-return, block with a named owner, or declare ready for user acceptance.
- Next owner: Owner / secure fixture administrator for an approved non-production protected fixture location and session calling contract; this Coordinator then reruns the same independent acceptance path.
- Next handoff: `blocked_with_owner`: P0.1 deployed public/local-first checks pass, but protected workflow `29936409580` still has no fixture. Do not request a token value; resume only when the named secure fixture/session contract is available.
- Deploy needed: No; P0.1 deployed through workflow `30018619840` and stable public/tokenless smoke passed.
- Deploy decision: `self_deploy` completed once through the shared workflow; no redeploy is required for the fixture blocker, and no competing deploy, ingress, Compose, or public-port action is authorized.
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
