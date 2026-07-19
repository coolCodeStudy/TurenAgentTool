# Quality Route Contract

## Purpose

This contract makes quality evidence proportional to delivery risk. It replaces repeated, overlapping test handoffs with one selected route and one authoritative release-verification manifest.

It applies to Feature Coordinators, Development Agents, and the Quality & Acceptance Lead. It does not change Owner final acceptance or the requirement for independent real-surface evidence when a route requires it.

## Default Route Selection

| Route | Default owner | Required close-out |
|---|---|---|
| `L0` | Feature Coordinator | Relevant audit/static evidence; no Acceptance Queue item |
| `L1` | Development Agent, then Feature Coordinator | Focused technical evidence and Return Gate; no Acceptance Queue item unless explicitly required |
| `L2` | Feature Coordinator plus Quality & Acceptance | One release-verification manifest and one independent real-surface acceptance result |
| `L3` | Feature Coordinator plus Quality & Acceptance | One manifest tied to deployed ref, cloud route evidence, and one independent acceptance result |

The Coordinator chooses the route at feature intake or when preparing a release candidate. The Quality & Acceptance Lead is consulted only for L3 work, a disputed L2 route, recurring defects, or test-system debt.

## Release-Verification Manifest

For L2/L3, record the following in the active Delivery Queue row or a linked feature artifact:

```markdown
- Release candidate ref:
- Quality route and rationale:
- Changed user/data/access boundaries:
- Developer evidence:
- Deploy event and target surface (L3 only):
- Independent acceptance command/journey:
- Evidence artifacts:
- Result: passed / failed / blocked / needs_retest:
- Explicit skips or environment exceptions:
- Recovery owner and retest trigger:
```

The manifest is the authority for the release candidate. Queue rows point to it; they do not repeat its content.

## Compaction Rule

At every Coordinator Return Gate:

1. Accept or reject the child result.
2. Close the child Delivery Queue row in the same turn.
3. Append accepted evidence to the manifest.
4. Keep only the next active owner or precise blocker open.

Three or more open `returned` rows for one feature are a coordination-health defect. Compact them before a new role dispatch. A new deploy ref or material scope change creates a new manifest; an ordinary fix/retest updates the existing one.

## Quality Improvement Portfolio

The Quality & Acceptance Lead periodically identifies duplicate assertions, flaky tests, broad suites used for narrow changes, missing contract tests, and repeated environment blockers. It proposes bounded work to the affected Feature Coordinator. It does not directly expand feature scope or centralize routine approvals.
