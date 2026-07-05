# Frontend Experience System Handoff

## Coordinator Packet

- Change ID: `frontend-experience-system`
- Current owner: Development Agent for technical-plan phase
- Next owner: Feature Coordinator for Return Gate, then Frontend Experience Reviewer before implementation handoff
- Source PRD: `docs/product/PRD-Frontend-Experience-System.md`
- Technical plan: `docs/techplans/frontend-experience-system.md`
- Feature Registry row: `Frontend experience system` links the PRD and technical plan; implementation remains not started
- Acceptance Queue row: `not_required` for docs/planning; required after a deployed user-facing implementation slice exists
- Delivery Queue row: `DQ-2026-07-05-003`
- Scope: define the first implementation slice for shared server-rendered app shell, primary navigation, and design-token contract across `/weekly-review`, `/`, and `/command`
- Out of scope: full redesign, framework migration, product-feature user acceptance, deploy, and implementation code in this phase
- Completion gate: technical plan identifies shared shell/render-helper design, module boundaries, route ownership, regression constraints, test strategy, screenshot evidence, deploy strategy, reviewer gates, rollout plan, and non-goals
- Deploy needed: no
- Deploy decision: `not_required` for technical-plan docs; implementation will need Release Reviewer and a concrete deploy decision after code changes
- Return target: source Feature Coordinator thread for Return Gate review
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

## PRD Return

- PRD path: `docs/product/PRD-Frontend-Experience-System.md`
- Chosen first slice: shared server-rendered app shell, primary navigation, and design-token contract for both `/weekly-review` and `/command`.
- Rejected fallback: Weekly Review-only shell first, because it leaves Command Workbench as a separate page island and does not prove the shared frontend system across active standalone pages.
- User journeys defined: Weekly Review user, Command Workbench user, cross-surface navigation, and mobile check.
- Non-goals defined: no frontend framework migration, no Daily Market Brief link or implementation, no Candidate Insights standalone nav, no API/auth/token behavior changes, no result-card semantic redesign, no Weekly Review data/model changes, no deploy behavior changes, and no user acceptance marking.
- Acceptance summary: shared shell/tokens/nav across `/weekly-review`, `/`, and `/command`; active nav only for active routes; Daily Market Brief omitted until Product package/PRD and route exist; Weekly Review and Command Workbench behaviors preserved; both `/command` route owners verified; desktop/mobile and keyboard/status evidence required.
- Reviewer gates required: Frontend Experience Reviewer before implementation handoff; Release Reviewer before deploy for the chosen two-surface release; Acceptance Reviewer after deployed user-facing slice; Security/Access Reviewer only if auth/token/private route behavior changes.

## Technical Plan Return

- Technical plan path: `docs/techplans/frontend-experience-system.md`
- Implementation slice summary: one Development pass to add `investment_knowledge_mcp/frontend_shell.py`, refactor Weekly Review and Command Workbench renderers to consume it, preserve route/API/token/result semantics, add renderer/smoke assertions, and capture desktop/mobile evidence.
- Files likely to change:
  - `investment_knowledge_mcp/frontend_shell.py`
  - `investment_knowledge_mcp/weekly_review_web.py`
  - `investment_knowledge_mcp/command_workbench.py`
  - `scripts/smoke_test.py`
- Route ownership: `/` and `/weekly-review` stay in `weekly_review_web.py`; public `/command` stays mirrored through `weekly_review_web.py`; internal `/command` stays in `command_api.py` through the same `render_command_workbench_html()` import.
- Regression constraints: preserve Weekly Review APIs, Command Workbench APIs, Candidate Insights APIs, `weekly_review_web_token`, `command_workbench_token`, `command_workbench_recent`, `command_workbench_pinned`, confirmation guards, command result-card parser semantics, and Weekly Review generation/persistence behavior.
- Tests/verification plan: Python compile checks for affected modules, `python3 scripts/smoke_test.py`, `git diff --check`, and desktop/mobile browser evidence for `/weekly-review` and `/command` during implementation.
- Reviewer gates: Frontend Experience Reviewer next, Release Reviewer before deploy, Acceptance Reviewer after deploy; Security/Access Reviewer only if implementation needs auth/token/private-route changes.

## Watch Contract

- Watched item: `DQ-2026-07-05-003` and branch `codex/frontend-experience-techplan`
- Wake event or cadence: Development technical-plan branch push and final return to the Feature Coordinator
- Expected artifact: pushed technical-plan commit, verified change package, updated Feature Registry and Delivery Queue, and explicit next-owner recommendation
- Coordinator action on wake: apply Coordinator Return Gate; if accepted, dispatch Frontend Experience Reviewer to review the technical plan against the PRD before any implementation handoff

## Return Gate

- Branch: `codex/frontend-experience-techplan`
- Commit: see final return summary for the commit SHA
- Verification: `scripts/verify_change_package.py docs/changes/frontend-experience-system`, `scripts/audit_agent_flow_health.py --feature "Frontend experience system"`, `scripts/audit_delivery_state.py --feature "Frontend experience system"`, and `git diff --check`
- Delivery-state updates: `DQ-2026-07-05-003` records Development technical-plan completion and next Feature Coordinator Return Gate owner; Feature Registry links the technical plan and keeps implementation not started
- Remaining gaps: no implementation, deployment, independent acceptance test, or user acceptance exists; no Daily Market Brief product package exists; browser screenshots are implementation evidence and were not expected for docs-only planning
- Recommended next owner: Feature Coordinator for Return Gate, then Frontend Experience Reviewer for pre-implementation plan review
