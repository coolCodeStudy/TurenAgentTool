# Architecture Contract

## Purpose

This contract records the system boundaries that make the repository legible
and safe for humans and agents to change. It is intentionally small: stable
principles belong here, while implementation-specific reports belong in the
Architecture & Code Health audit output.

## Principles

- Each browser route has one declared owner module and access class.
- Cross-feature architecture findings are evidence-backed, bounded, and routed
  to a Feature Coordinator; the Architecture & Code Health Agent does not take
  over product delivery.
- Import-cycle, route, and test signals are initially report-only. They become
  blocking only through the rule-admission gate below.
- The audit must not read credentials, environment values, cloud state, or
  private endpoints.

## Browser Route Inventory

| Route | Owner module | Access class | Contract test |
|---|---|---|---|
| `/command` | `investment_knowledge_mcp.command_workbench` | protected | `tests/test_web_experience.py` |
| `/weekly-review` | `investment_knowledge_mcp.weekly_review_web` | public_read_protected_write | `tests/test_weekly_review_web_auth.py` |
| `/daily-market-brief` | `investment_knowledge_mcp.weekly_review_web` | public_read | `tests/test_daily_market_brief.py` |

Allowed access classes are `public_read`, `protected`, and
`public_read_protected_write`. This table declares intent; its contract tests
remain the behavioral source of truth.

## Rule Admission Gate

A rule can become a P0 blocking rule only when all of the following are true:

1. It passes on authoritative `main`, or has a narrowly scoped approved
   exception.
2. The harness has deterministic fixture tests for its pass and fail cases.
3. The boundary, owner, smallest remediation slice, and verification are
   explicit.
4. The check requires neither network access, a credential, nor production
   state.
5. It prevents a demonstrated release-integrity, delivery, or access-boundary
   regression.

Until admitted, every result is a P1 report finding and must not block normal
feature delivery.

## Baseline Exceptions

An exception must list its finding ID, affected boundary, accountable Feature
Coordinator, remediation trigger, and expiry/review event. V1 has no admitted
blocking rules and no approved baseline exceptions.

## V1 Report Baseline

The initial local audit establishes seven report-only P1 concentration signals:

- `ARCH-SIZE-001:investment_knowledge_mcp.command_router`
- `ARCH-SIZE-001:investment_knowledge_mcp.command_workbench`
- `ARCH-SIZE-001:investment_knowledge_mcp.daily_market_brief`
- `ARCH-SIZE-001:investment_knowledge_mcp.repository`
- `ARCH-SIZE-001:investment_knowledge_mcp.research.official_sources`
- `ARCH-SIZE-001:investment_knowledge_mcp.weekly_review`
- `ARCH-SIZE-001:investment_knowledge_mcp.weekly_review_web`

Each identifies a module responsibility-concentration boundary. These are
prioritization inputs, not release blockers or an instruction to refactor the
whole module. The Architecture Agent must choose a bounded responsibility and
route it through the named coordinator before implementation begins.
