# Tech Plans Index

Start here before implementing from a tech plan.

## Active Plans

| Plan | Purpose | Status |
| --- | --- | --- |
| `weekly-review.md` | Weekly review generator and data methodology | Active |
| `weekly-review-web-workbench.md` | Local Web workbench for weekly review | Active |
| `cloud-pull-deploy-plan.md` | `/ops/deploy` cloud pull deployment path | Active, has known control-plane debt |
| `control-plane-and-throughput-plan.md` | Codex/Ops control plane and task throughput | Active roadmap |
| `task2-cloud-worker-execution-location.md` | Cloud worker as default research execution location | Active/partially implemented |
| `task3-research-display-decision-card.md` | Default research display as Level 1 decision card | Active/partially implemented |

## How To Use Tech Plans

1. Read `../README.md` to confirm the plan is the right source.
2. Read the related product doc.
3. Check `../当前工程状态.md` for current implementation facts.
4. Implement narrowly.
5. Update the plan status when scope or acceptance changes.

## Maintenance Rules

- Tech plans should not be daily logs.
- Keep runtime facts in the database or `../当前工程状态.md`.
- If a plan is fully implemented, mark it `implemented` and link the current state.
- If a new plan replaces an old one, mark the old one `superseded`.
- Keep examples and command strings exact, even if they contain Chinese user-facing commands.

