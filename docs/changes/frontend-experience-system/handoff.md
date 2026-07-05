# Frontend Experience System Handoff

## Coordinator Packet

- Change ID: `frontend-experience-system`
- Current owner: Feature Coordinator / Product Experience Owner for inventory phase
- Next owner: Product/Frontend Experience owner for PRD, then Development Agent for technical plan
- Source PRD: `not_applicable` for inventory phase
- Technical plan: `needed_after_PRD`
- Feature Registry row: `Frontend experience system` exists with Product context and technical plan still missing; inventory phase does not change implementation or acceptance status
- Acceptance Queue row: `not_required` for inventory phase
- Delivery Queue row: `DQ-2026-07-04-020`
- Scope: inventory current frontend surfaces, define shared experience direction, and recommend the first implementation slice
- Out of scope: full redesign, framework migration, product-feature user acceptance
- Completion gate: inventory and first-slice recommendation are recorded in this package and Delivery Queue is updated through the Coordinator Return Gate
- Deploy needed: no
- Deploy decision: `not_required` for inventory phase
- Return target: source Global Project Manager / Owner thread for review of this completed inventory return
- Escalation target: Global Project Manager only for cross-feature conflict, deploy conflict, stale coordinator recovery, or operating-model defect

## Inventory Return

- Surfaces inventoried: `/weekly-review`, `/`, `/command`, embedded Candidate Insights, command-generated result cards, and pending Daily Market Brief references.
- Implementation locations found:
  - `investment_knowledge_mcp/weekly_review_web.py` owns Weekly Review routing, inline page rendering, Weekly Review APIs, Candidate Insights APIs, and public `/command` mirroring.
  - `investment_knowledge_mcp/command_workbench.py` owns Command Workbench inline page rendering, action catalog UI, local history, and client-side decision-card formatting.
  - `investment_knowledge_mcp/command_api.py` owns internal `command-api` `/command` and workbench API routes.
  - `investment_knowledge_mcp/weekly_review.py` owns Weekly Review generated Markdown and structured report data.
- Daily Market Brief status: pending only. No route, PRD, package, renderer, or static asset exists in this worktree.
- Frontend architecture finding: active pages are Python-rendered self-contained HTML/CSS/JS strings. No shared template directory, static asset directory, frontend build pipeline, or common component module was found.
- UX risks: navigation islands, mismatched page shells, duplicate inline CSS variables/components, mobile density risk around tables/control bars/catalogs, incomplete shared focus/live-region policy, inconsistent bilingual UI copy, and no safe Daily Market Brief affordance yet.
- First implementation slice: shared server-rendered app shell/navigation/design-token contract, applied to `/weekly-review` and `/command` if Product accepts the two-surface release gate. Lower-risk fallback is Weekly Review first, with a link to the existing `/command` route.
- Non-goals for first slice: no framework migration, no Daily Market Brief implementation, no auth/token behavior change, no API contract change, no result semantics rewrite, no weekly-review data/model change, no product-feature user acceptance.
- PRD needed: yes. Product context is missing and the next slice changes information architecture and primary navigation.
- Technical plan needed: yes. Implementation will touch shared render helpers, route owners, tests, and user-facing acceptance evidence.
- Reviewer gates applied: Frontend Experience Reviewer self-review applied for inventory. Release Reviewer not required for inventory; required if the next implementation touches both `/weekly-review` and `/command`. Acceptance Reviewer not required until a deployed slice exists. Security/Access Reviewer not required unless auth/token/private route behavior changes.

## Watch Contract

- Watched item: `DQ-2026-07-04-020` and branch `codex/frontend-experience-inventory`
- Wake event or cadence: source coordinator/Owner reviews the pushed inventory return or explicitly approves the recommended first slice
- Expected artifact: accepted inventory package plus either a concise Product/Frontend PRD for shared app shell/navigation or a recorded product decision choosing the lower-risk Weekly Review-only fallback
- Coordinator action on wake: open the next Delivery Queue row for Product/Frontend PRD work, then route Development for a technical plan; require Frontend Experience Reviewer before implementation dispatch and Release Reviewer before deploy if both `/weekly-review` and `/command` are changed

## Return Gate

- Branch: `codex/frontend-experience-inventory`
- Commit: see final return summary for the commit SHA
- Verification: `scripts/verify_change_package.py docs/changes/frontend-experience-system`, `scripts/audit_agent_flow_health.py --feature "Frontend experience system"`, and `git diff --check` passed in the inventory worktree
- Delivery-state updates: `DQ-2026-07-04-020` is closed because the inventory output is complete and deploy is not required
- Remaining gaps: no Daily Market Brief product package exists; PRD and technical plan are still needed before implementation; no browser screenshots were taken because this phase did not run or change a web surface
- Recommended next owner: Product/Frontend Experience owner for concise PRD, then Development Agent for technical plan
