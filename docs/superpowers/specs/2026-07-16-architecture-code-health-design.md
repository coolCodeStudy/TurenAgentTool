# Architecture And Code Health Design

## Decision

Introduce a repo-native Architecture & Code Health system with two layers:

1. A versioned agent skill that turns a broad architecture concern into
   evidence-backed findings and narrow delivery slices.
2. A deterministic harness that measures agreed structural invariants and
   prevents confirmed high-risk regressions.

The system complements Feature Coordinators. It does not implement unrelated
product code, mark user acceptance, replace code review, or become a second
deployment control plane.

## Problem

The repository has grown through feature-local delivery. This has produced
useful products, but several cross-cutting concerns now span too many modules:

- Web route, authentication, API, renderer, and error responsibilities are
  concentrated in large modules.
- Command Workbench and Weekly Review have duplicated or divergent browser
  access and rendering behavior.
- Deployment, control-plane, and release integration rules need mechanical
  verification rather than rediscovery during a coordinator return.
- Existing delivery audits validate process state, but do not expose module
  ownership, dependency direction, duplicated boundaries, or architectural
  drift.

## Considered Approaches

### 1. Report-only architecture reviews

An architecture agent periodically writes findings. This has low rollout risk,
but suggestions can be forgotten and the same regressions can recur.

### 2. Hard architecture gate from day one

A strict linter blocks every oversized module, cross-module import, or
duplication signal. This is unsuitable for the current repository because
known debt would stop routine work before a safe migration path exists.

### 3. Graduated skill and harness

Use a read-only architecture audit to establish a baseline. Rules are report
only until they have a stable baseline, fixture coverage, a named owner, and a
safe remediation path. Confirmed P0 invariants then become no-deploy CI gates.
Other findings become Feature Coordinator-owned slices. This is the selected
approach.

## Architecture Agent Contract

The Architecture & Code Health Agent is a specialist review role. It may:

- inspect repository structure, import relationships, route ownership, access
  boundaries, tests, deployment contracts, and prior delivery evidence;
- run the architecture harness and classify findings by severity and evidence;
- propose narrow slices with an owner, affected files, acceptance criteria,
  expected verification, and migration risk;
- update architecture documentation and harness rules only after evidence
  supports the rule.

It must not:

- directly rewrite unrelated business features or silently start a broad
  refactor;
- change product access policy, credentials, deployment targets, or user
  acceptance status;
- expose token values, environment contents, or private service endpoints;
- return a generic "refactor the codebase" recommendation without a concrete
  owner and bounded follow-up.

The agent returns findings to the relevant Feature Coordinator. The Global PM
uses it for portfolio-level debt prioritization and rule evolution.

## Versioned Skill

The canonical skill source will be committed under:

```text
skills/architecture-code-health/
```

It will contain a concise `SKILL.md`, a coordinator handoff template, and only
the references needed to interpret the harness output. A small installer/check
script will materialize the skill into the local Codex skill directory when
needed, while the repository remains the source of truth. This avoids a
machine-local skill drifting away from the delivery rules checked into Git.

The skill triggers for architecture audit, code-health audit, module-boundary
review, dependency-direction review, large refactor planning, and recurring
cross-feature implementation failures.

Its workflow is:

1. Read the current architecture contract and run the harness.
2. Inspect only the modules and evidence implicated by findings.
3. Distinguish an observed fact from a design recommendation.
4. Produce a ranked finding table with evidence, risk, owner, and an
   independently deliverable next slice.
5. Dispatch or return the slice to the correct Feature Coordinator; do not
   implement it by default.
6. Propose a new blocking rule only when it passes the rule-admission gate.

## Harness

The first implementation will add:

```text
docs/architecture/architecture-contract.md
docs/project-management/prompt-templates/Architecture-Code-Health.md
skills/architecture-code-health/SKILL.md
scripts/audit_architecture_health.py
scripts/install_architecture_code_health_skill.py
tests/test_architecture_health_audit.py
```

`audit_architecture_health.py` will use Python AST and repository metadata. It
will emit human-readable Markdown and machine-readable JSON. It must be safe
to run locally, require no credentials or network access, and classify as
`no_deploy`.

The initial report will include:

- module size and responsibility concentration;
- import graph and cycles within `investment_knowledge_mcp`;
- route-to-owner and public/private access inventory;
- duplicate browser access storage keys and renderer ownership markers;
- test coverage mapping for public/protected route contracts;
- explicit baseline exceptions with a named remediation Feature Coordinator.

The harness will not infer runtime security, performance, or product quality
from static data. Such findings need service evidence or independent
acceptance evidence.

## Rule Admission And Severity

Every rule has an ID, evidence source, severity, baseline state, owner, and
remediation path.

### P0 blocking rules

A rule can block CI only after all of the following are true:

- it passes on the authoritative baseline, or has a tightly scoped approved
  exception;
- the harness has fixture tests proving both pass and fail behavior;
- the affected boundary and remediation owner are unambiguous;
- it does not require a network call, secret, or production access;
- it prevents a demonstrated delivery, access-boundary, or release-integrity
  regression.

Initial candidates are cycle-free application imports, declared access class
for every public user route, and a single declared owner for each deployed
browser route. They become blocking only after the baseline proves stable.

### P1 report rules

Large modules, responsibility concentration, duplicated renderer/access code,
missing route-contract tests, and undeclared architectural exceptions are
reported but do not block delivery. They must be emitted as a ranked backlog,
not as vague technical-debt prose.

## Integration With Delivery

Architecture audit work is operating-model infrastructure and belongs in the
Agent Operating Model Roadmap, with precise Delivery Queue entries for active
work. User-facing implementation slices remain normal features in the Feature
Registry, Acceptance Queue, and Delivery Queue.

For a reported finding, the harness output must name:

- finding ID and observed evidence;
- affected module or route;
- severity and why it has that severity;
- current owner and recommended Feature Coordinator;
- smallest safe implementation slice;
- required tests, deploy decision, and regression check.

This keeps the architecture role from becoming a parallel feature manager.

## Rollout

1. Create the skill, harness, architecture contract, prompt template, and
   deterministic tests.
2. Run the harness on current `main` and commit an explicit baseline report.
3. Admit only stable P0 rules as no-deploy CI checks.
4. Dispatch the first two highest-leverage P1 findings as ordinary feature
   slices, after the Infrastructure & Release Reliability Expert stabilizes
   the release path.
5. Add a recurring code-health audit only after the first two slices prove the
   findings are actionable and the Coordinator Return Gate processes them.

## Acceptance Criteria

- A coordinator can invoke one command and receive stable Markdown and JSON
  architecture findings without credentials or network access.
- The skill produces findings with evidence, owner, slice, and verification;
  it does not produce an unbounded refactor request.
- The harness has deterministic pass/fail fixture coverage.
- Existing known debt is visible as P1 report output and does not block normal
  work on day one.
- Any P0 blocker is baseline-safe, tested, and connected to a demonstrated
  regression class.
- The installer detects a stale local skill copy without copying secrets or
  modifying tracked repository files.
- The feature does not add a second deploy path, change public access policy,
  or alter product behavior.

## Non-Goals

- Adopting an external architecture SaaS, API key, or MCP server in P0.
- Replacing existing Feature Coordinators, delivery audits, or deployment
  controls.
- A whole-repository refactor.
- Runtime profiling, security scanning, or dependency vulnerability scanning
  beyond exporting clear handoff inputs to their dedicated tools.
