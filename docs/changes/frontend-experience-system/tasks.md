# Frontend Experience System Tasks

## Checklist

- [x] Inventory current user-facing surfaces and entrypoints.
  - `/weekly-review` and `/` are active Weekly Review Web surfaces on `weekly-review-web`.
  - `/command` is active through both `command-api` and the public `weekly-review-web` mirror.
  - Candidate Insights is embedded inside Weekly Review; it is not a separate page.
  - Daily Market Brief is planning-only in this worktree; no route, PRD, package, or renderer was found.
- [x] Identify implementation files for each surface.
  - `investment_knowledge_mcp/weekly_review_web.py` owns Weekly Review routing, inline HTML/CSS/JS rendering, Weekly Review APIs, Candidate Insights APIs, and the public `/command` mirror.
  - `investment_knowledge_mcp/command_workbench.py` owns the Command Workbench inline HTML/CSS/JS renderer and client-side result-card formatting.
  - `investment_knowledge_mcp/command_api.py` owns the internal `/command` route and workbench APIs for the command API service.
  - `investment_knowledge_mcp/weekly_review.py` owns generated Weekly Review Markdown and structured report data consumed by the Web page.
- [x] Record UX consistency risks.
  - Recorded in `design.md`: navigation, layout/responsive, component/code ownership, and accessibility risks.
- [x] Recommend the first implementation slice.
  - Recommended slice: shared server-rendered app shell/navigation/design-token contract, applied to `/weekly-review` and `/command` if Product accepts the two-surface release gate.
  - Lower-risk fallback: apply the shared shell to `/weekly-review` first and link to existing `/command`, leaving Command Workbench rendering for slice two.
- [x] Produce Product PRD for the first visible frontend slice.
  - PRD path: `docs/product/PRD-Frontend-Experience-System.md`.
  - Product decision: choose the recommended two-surface slice for `/weekly-review` and `/command`.
  - The Weekly Review-only fallback is rejected for this slice because it would leave the core cross-surface inconsistency unresolved.
- [x] Define frontend acceptance criteria for the first slice.
  - Both active pages expose the same primary nav labels and active-route state.
  - Daily Market Brief is omitted or clearly disabled until its PRD/package exists.
  - Existing API routes, auth headers, token keys, command parsing, weekly-review generation, and candidate-insight behavior remain unchanged.
  - Desktop and mobile screenshots show no overlapping controls, inaccessible horizontal navigation, or hidden primary actions.
  - Keyboard users can reach primary nav, main content, token field, primary actions, generated results, and action catalog without pointer-only controls.
  - Status/error/result updates have a documented live-region or focus-management rule.
- [x] Define reviewer gates for implementation and release.
  - Frontend Experience Reviewer is required before implementation handoff.
  - Release Reviewer is required before deploy if both `/weekly-review` and `/command` are changed in one release.
  - Acceptance Reviewer is required after deployment and before user acceptance request.
  - Security/Access Reviewer is required only if auth/token/private route behavior changes.
- [x] Decide whether a PRD or technical plan is needed before implementation.
  - PRD needed: completed in `docs/product/PRD-Frontend-Experience-System.md`.
  - Technical plan needed: yes. The implementation will touch server-rendered HTML/CSS/JS, shared UI helpers, route owners, tests, release review, and acceptance evidence.
- [x] Update Delivery Queue with the next owner and watch contract.
  - `DQ-2026-07-04-020` updated through Coordinator Return Gate after this inventory output.
  - `DQ-2026-07-05-002` records the Product PRD return and the next Development technical-plan owner.
- [x] Keep deploy decision `not_required` until implementation begins.
  - Deploy decision for this inventory phase remains `not_required`; no code or cloud surface changed.

## Next Owner Packet

- Next owner: Development Agent.
- Task: create the technical plan for the shared server-rendered shell/navigation/design-token slice across `/weekly-review` and `/command`, then return to the Feature Coordinator before implementation.
- Recommended first implementation branch shape: one bounded server-rendered shell/navigation slice; no framework migration and no auth/token/API behavior changes.
- Release gate note: if implementation updates both `/weekly-review` and `/command`, Release Reviewer is required before deploy because two active cloud surfaces are affected.
- Acceptance gate note: independent Acceptance Reviewer is required only after a deployed user-facing slice exists.
- Frontend gate note: Frontend Experience Reviewer is required before implementation handoff.

## Verification Commands

```bash
python3 scripts/verify_change_package.py docs/changes/frontend-experience-system
```

Expected outcome: package passes required-file, required-heading, and project-link checks.

```bash
python3 scripts/audit_agent_flow_health.py --feature "Frontend experience system"
```

Expected outcome: active queue state is visible; any missing watch or stale coordinator state is actionable.

```bash
python3 scripts/audit_delivery_state.py --feature "Frontend experience system"
```

Expected outcome: Feature Registry and Delivery Queue reflect PRD readiness and the next Development technical-plan owner.
