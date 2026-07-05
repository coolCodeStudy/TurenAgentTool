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
- [x] Define frontend acceptance criteria for the first slice.
  - Both active pages expose the same primary nav labels and active-route state.
  - Daily Market Brief is omitted or clearly disabled until its PRD/package exists.
  - Existing API routes, auth headers, token keys, command parsing, weekly-review generation, and candidate-insight behavior remain unchanged.
  - Desktop and mobile screenshots show no overlapping controls, inaccessible horizontal navigation, or hidden primary actions.
  - Keyboard users can reach primary nav, main content, token field, primary actions, generated results, and action catalog without pointer-only controls.
  - Status/error/result updates have a documented live-region or focus-management rule.
- [x] Decide whether a PRD or technical plan is needed before implementation.
  - PRD needed: yes. The slice changes product information architecture and primary navigation across user-facing surfaces, and the Feature Registry currently says Product context is missing.
  - Technical plan needed: yes. The implementation will touch server-rendered HTML/CSS/JS, shared UI helpers, route owners, tests, and acceptance evidence.
- [x] Update Delivery Queue with the next owner and watch contract.
  - `DQ-2026-07-04-020` updated through Coordinator Return Gate after this inventory output.
- [x] Keep deploy decision `not_required` until implementation begins.
  - Deploy decision for this inventory phase remains `not_required`; no code or cloud surface changed.

## Next Owner Packet

- Next owner: Product/Frontend Experience owner.
- Task: write or approve a concise PRD for the shared app shell/navigation first slice, then route Engineering to create a technical plan.
- Recommended first implementation branch shape: one bounded server-rendered shell/navigation slice; no framework migration.
- Release gate note: if implementation updates both `/weekly-review` and `/command`, Release Reviewer is required before deploy because two active cloud surfaces are affected.
- Acceptance gate note: independent Acceptance Reviewer is required only after a deployed user-facing slice exists.

## Verification Commands

```bash
python3 scripts/verify_change_package.py docs/changes/frontend-experience-system
```

Expected outcome: package passes required-file, required-heading, and project-link checks.

```bash
python3 scripts/audit_agent_flow_health.py --feature "Frontend experience system"
```

Expected outcome: active queue state is visible; any missing watch or stale coordinator state is actionable.
