# Frontend Experience System Handoff

## Coordinator Packet

- Change ID: `frontend-experience-system`
- Current owner: Product/Frontend Experience owner for PRD phase
- Next owner: Feature Coordinator for Return Gate, then Development Agent for technical plan
- Source PRD: `docs/product/PRD-Frontend-Experience-System.md`
- Technical plan: `needed_after_PRD`
- Feature Registry row: `Frontend experience system` points to the PRD; technical plan is still missing; implementation remains not started
- Acceptance Queue row: `not_required` for PRD docs; required after a deployed user-facing slice exists
- Delivery Queue row: `DQ-2026-07-05-002`
- Scope: define Product/UX scope for the first visible frontend implementation slice
- Out of scope: full redesign, framework migration, product-feature user acceptance
- Completion gate: PRD records the first-slice decision, user journeys, non-goals, acceptance criteria, accessibility/responsive criteria, regression constraints, and reviewer gates
- Deploy needed: no
- Deploy decision: `not_required` for PRD docs; implementation will need a deploy decision after code changes
- Return target: source Global Project Manager / Feature Coordinator thread for Return Gate review
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
- First implementation slice recommendation from inventory: shared server-rendered app shell/navigation/design-token contract, applied to `/weekly-review` and `/command` if Product accepts the two-surface release gate. Lower-risk fallback is Weekly Review first, with a link to the existing `/command` route.
- PRD needed: completed in `docs/product/PRD-Frontend-Experience-System.md`.
- Technical plan needed: yes. Implementation will touch shared render helpers, route owners, tests, release review, and user-facing acceptance evidence.

## PRD Return

- PRD path: `docs/product/PRD-Frontend-Experience-System.md`
- Chosen first slice: shared server-rendered app shell, primary navigation, and design-token contract for both `/weekly-review` and `/command`.
- Rejected fallback: Weekly Review-only shell first, because it leaves Command Workbench as a separate page island and does not prove the shared frontend system across active standalone pages.
- User journeys defined: Weekly Review user, Command Workbench user, cross-surface navigation, and mobile check.
- Non-goals defined: no frontend framework migration, no Daily Market Brief link or implementation, no Candidate Insights standalone nav, no API/auth/token behavior changes, no result-card semantic redesign, no Weekly Review data/model changes, no deploy behavior changes, and no user acceptance marking.
- Acceptance summary: shared shell/tokens/nav across `/weekly-review`, `/`, and `/command`; active nav only for active routes; Daily Market Brief omitted until Product package/PRD and route exist; Weekly Review and Command Workbench behaviors preserved; both `/command` route owners verified; desktop/mobile and keyboard/status evidence required.
- Reviewer gates required: Frontend Experience Reviewer before implementation handoff; Release Reviewer before deploy for the chosen two-surface release; Acceptance Reviewer after deployed user-facing slice; Security/Access Reviewer only if auth/token/private route behavior changes.

## Watch Contract

- Watched item: `DQ-2026-07-05-002` and branch `codex/frontend-experience-prd`
- Wake event or cadence: Product/Frontend PRD branch push and final return to the source Feature Coordinator / Global Project Manager thread
- Expected artifact: pushed PRD commit plus verified updates to change package, Feature Registry, and Delivery Queue
- Coordinator action on wake: apply Coordinator Return Gate, then dispatch Development Agent to create the technical plan for `docs/product/PRD-Frontend-Experience-System.md`; require Frontend Experience Reviewer before implementation handoff, Release Reviewer before deploy if both active pages change, and Acceptance Reviewer after deployment

## Return Gate

- Branch: `codex/frontend-experience-prd`
- Commit: see final return summary for the commit SHA
- Verification: `scripts/verify_change_package.py docs/changes/frontend-experience-system`, `scripts/audit_agent_flow_health.py --feature "Frontend experience system"`, `scripts/audit_delivery_state.py --feature "Frontend experience system"`, and `git diff --check`
- Delivery-state updates: Feature Registry product doc/PRD status updated; Delivery Queue row `DQ-2026-07-05-002` records Product PRD return and next Development technical-plan owner
- Remaining gaps: no Daily Market Brief product package exists; technical plan, implementation, deployment, independent acceptance test, and user acceptance are still missing
- Recommended next owner: Feature Coordinator for Return Gate, then Development Agent for technical plan
