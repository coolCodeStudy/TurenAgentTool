---
name: architecture-code-health
description: Audit repository architecture and code health when reviewing cross-feature structure, dependency boundaries, route ownership, access contracts, recurring delivery failures, or a proposed broad refactor. Produces evidence-backed bounded slices for Feature Coordinators without directly changing product code or policy.
---

# Architecture & Code Health

## When To Use

Use for a cross-feature architecture audit, dependency-direction review,
route/access-contract review, or recurring implementation failure. Do not use
for ordinary feature implementation, product decisions, deployment execution,
or user acceptance.

## Workflow

1. Read `docs/architecture/architecture-contract.md` and the relevant
   Coordinator context packet if supplied.
2. Run `python3 scripts/audit_architecture_health.py --repo . --format markdown`.
3. Inspect only modules and tests implicated by the report.
4. Separate observed evidence from a recommendation. Do not infer runtime
   security, tokens, performance, or cloud health from static analysis.
5. Return each actionable finding to the requesting Feature Coordinator using
   `docs/project-management/prompt-templates/Architecture-Code-Health.md`.

## Guardrails

- The audit is read-only and must not access credentials, environment values,
  cloud services, or private endpoints.
- Do not silently begin a broad refactor or change product access policy.
- A report finding is not a CI gate. Propose a blocking rule only through the
  rule-admission gate in the architecture contract.
- Every actionable finding needs evidence, severity, accountable coordinator,
  smallest safe slice, and verification. Otherwise report it as an observation
  or omit it.
