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
- Delivery Queue rows: Product recovery `DQ-2026-07-19-002`, technical planning `DQ-2026-07-19-003`, and prior release row `DQ-2026-07-19-004` are closed; current bilingual-output Product discovery is tracked in `DQ-2026-07-22-001`.
- Current authoritative branch/ref: latest main `b534c972be80b3a32f154cf24d3efc2c8020f1ec`; deployed shared-service runtime `main@88df3fd7e8eeeebc43e1758b5c3471a41993e593` (serialized run `29847396363`, event `1784650393858`) contains Stock runtime `main@48930c1e56ea377e7fb65fb44279e172e36b054d`. Runtime integration parent is `46639d2`; stock implementation review is `61e950f`; exact Frontend runtime ref is `017d91c6cc8ad613ab07a2b9093bb7b32850abba`. No ingress/Compose/port changes are present. Latest main descendants are docs/classifier-only and classified `no_deploy`; coordinator smoke and 35/35 local public checks pass, while authenticated valuation acceptance remains blocked only for the protected Stock P0 checks.
- Related coordinator branch/ref: `codex/stock-valuation-research`; historical recovery source `origin/codex/release-kline-stock-valuation-p03@acd9856`
- Current deployed ref or deploy event: shared-service runtime `main@88df3fd7e8eeeebc43e1758b5c3471a41993e593`, serialized deployment run `29847396363`, event `1784650393858`; latest public action catalog and tokenless protected-boundary checks are current. `/health` retains historical release metadata, so the immutable deploy event is provenance.
- User-facing surface: Cloud Command Workbench at `http://47.84.190.191:8010/command`
- Quality route: `L3`
- Route rationale: The feature changes an authenticated cloud Command Workbench, external data-source behavior, saved evidence, and the deployed release boundary.
- Release-verification manifest (ref, route, surface, evidence, unresolved exceptions): deployed `main@88df3fd7e8eeeebc43e1758b5c3471a41993e593`, route `L3`, surface `http://47.84.190.191:8010/command`; serialized run `29847396363`, event `1784650393858`; runtime parent `46639d2`, stock review `61e950f`, and Frontend runtime `017d91c6cc8ad613ab07a2b9093bb7b32850abba`; stock gates, Frontend runtime tests, coordinator smoke, tokenless protected-boundary checks, and 35/35 local public checks pass. Authenticated valuation acceptance is blocked only for the explicitly protected Stock P0 fixture/session; `/health` exposes stale release metadata; no protected credential value may enter evidence.
- Current state: Product-ready PRD `91b741b` plus the approved bilingual presentation addendum; technical plan `implementation_complete_pending_release`; bilingual release source `7bcce77` is deployed through authoritative state `main@5a94ee6` by workflow run `29934200517` (`targeted_quick`/workflow-compatible `quick`). Coordinator public/tokenless smoke passed; the independent protected Stock P0 evidence blocker remains unchanged.
- Known blockers: No code blocker remains. Deployment and independent acceptance are the next gates. Protected P0 acceptance still requires an approved secure fixture/session contract, never a token value. Frontend confirms no ingress/Compose/public-port change is active.
- Active child threads or role sessions: Product Agent `/root/product_bilingual_output` returned the bilingual valuation-output decision at `425e8cae4fbf5e182a4dcf798a8bc200c6d1d01a`; inline Development returned candidate `68aae6f`; Independent Acceptance `/root/bilingual_valuation_acceptance` is dispatched for `AT-2026-07-19-001`. This Feature Coordinator owns the release and acceptance watch.
- Watch contract:
  - Watched item: Independent Acceptance `/root/bilingual_valuation_acceptance` return for `AT-2026-07-19-001` after deployed release source `7bcce77` / workflow run `29934200517`.
  - Wake event or cadence: This coordinator polls each child role until return; no Global PM heartbeat is the normal watcher.
  - Expected return artifact: Exact independent evidence matrix, deployed immutable ref/run, bilingual card/method parity and safety results, and protected fixture/session result; no token values.
  - Coordinator action on wake: Apply the Coordinator Return Gate, update registry/queues, then accept-and-route, reject-and-return, block with a named owner, or declare ready for user acceptance.
- Next owner: Independent Quality & Acceptance Agent `/root/bilingual_valuation_acceptance` for `AT-2026-07-19-001`; this Coordinator watches the return and preserves the protected fixture/session blocker.
- Next handoff: `dispatched`: independent acceptance is active against `http://47.84.190.191:8010/command`, release source `7bcce77`, authoritative state `main@5a94ee6`, workflow run `29934200517`; on return apply the Return Gate and route only a concrete retest or `blocked_with_owner` outcome.
- Deploy needed: No; the single serialized deploy completed and public/tokenless smoke passed.
- Deploy decision: `self_deploy` completed once through the shared workflow; no competing deploy, ingress, Compose, or public-port action is authorized.
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
