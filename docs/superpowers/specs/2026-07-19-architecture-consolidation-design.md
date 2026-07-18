# Architecture Consolidation Design

**Status:** Approved for compatibility-first implementation by the Owner on 2026-07-19.

## Decision

Consolidate cross-feature data-source execution, browser access policy, HTTP
application routing, and background scheduling through bounded shared
contracts. Preserve compatibility while each consumer migrates, then remove
the corresponding duplicate path immediately after its explicit retirement
gate passes.

The design does not introduce a data-source microservice or a new cache
service. It reduces always-on Python application processes only where runtime
evidence and contract tests show that failure isolation remains adequate.

## Evidence And Problem Statement

The architecture audit reports seven P1 responsibility-concentration signals
and no admitted P0 blockers. Manual inspection found three related boundaries:

1. Weekly Review, Daily Market Brief, and historical generation select data
   providers and express fallback, retry, source status, and errors locally.
2. `command_api.py` and `weekly_review_web.py` both expose command execution
   but resolve access tokens and access failures differently.
3. Production Compose defines nine long-lived Python application containers.
   Prior production evidence recorded about 656 MiB aggregate memory for those
   nine containers on a memory-constrained host.

Static repository evidence cannot prove current production callers, per-service
RSS, or whether the DingTalk HTTP callback is still used. Those decisions
require sanitized runtime diagnostics and must not be inferred from source
alone.

## Goals

- Give product features one declarative external-data-source contract.
- Centralize provider selection, fallback, retry, timeout, rate, cache, and
  provenance semantics without creating another service.
- Give all user-facing Web/API routes one access-policy implementation while
  keeping operational and third-party credentials in separate trust domains.
- Replace duplicate command HTTP controllers with a compositional application
  gateway, not a larger `weekly_review_web.py` module.
- Reduce idle Python interpreter overhead through evidence-backed service
  retirement and a scheduler supervisor.
- Keep every migration independently testable, deployable, observable, and
  reversible.

## Non-Goals

- A repository-wide module rewrite.
- A Redis deployment or data-source network service.
- One token for browser, Ops, DingTalk, GitHub, and provider credentials.
- Moving the Ops API into the business application process.
- Claiming memory savings from container count without RSS measurements.
- Removing a live HTTP or background path without caller and behavior evidence.

## Target Boundaries

```text
User ingress
  Web / HTTP -> app gateway -> application controllers
  DingTalk   -> selected DingTalk transport adapter -> command application
  MCP        -> MCP adapter -> application services

Application services
  Command Application
  Weekly Review
  Daily Market Brief
  Shared Access Policy

External data
  Feature SourcePlan -> DataSourcePool -> ExternalDataSource adapters

Background execution
  scheduler-host
    scheduled job definitions
    per-job health and overlap policy
    history queue supervisor -> on-demand history child process

Control plane
  independent Ops API
```

## External Data Source Contract

### Responsibilities

Features declare required capabilities and evidence requirements. They do not
implement provider loops. The pool owns selection and execution policy. An
adapter owns transport and provider-specific normalization. Product evidence
code decides whether a complete or partial result is admissible in a report.

### Core Types

- `SourceCapability`: stable capability IDs such as `market_bars`,
  `market_leaders`, `official_events`, `news_events`, `positions`, and
  `trades`.
- `DataRequest`: capability, market, symbol set, date/range, freshness, and
  required fields.
- `SourcePlan`: required/optional capability, preferred sources, allowed
  fallbacks, and partial-result policy.
- `ProviderDescriptor`: provider ID, capabilities, markets, timeout, retry,
  rate group, and default TTL.
- `DataResult`: `ok`, `partial`, or `unavailable`; normalized records; selected
  and attempted sources; coverage; fetch time; cache state; and standardized
  failures.

### Execution Semantics

1. Filter registered providers by capability and market.
2. Apply the feature's allow-list and preference without allowing the feature
   to execute its own fallback loop.
3. Read the normalized-result cache.
4. Retry only transient failures within the current adapter policy.
5. Fall back only for explicitly admitted failure classes.
6. Return partial coverage explicitly; never convert it to full success.
7. Record every attempted provider without logging credentials or raw secret
   request material.

The first implementation uses an in-process registry and cache interface.
If runtime evidence shows cross-process quota or duplicate-fetch pressure, a
PostgreSQL-backed coordination implementation may be added without changing
feature contracts.

### Migration Order

1. Market bars shared by Weekly Review and Daily Market Brief.
2. Market leaders.
3. Official events.
4. News events.
5. Account positions and trades where provider duplication remains.

Each capability migration includes old/new characterization fixtures and
deletes the migrated feature-local fallback after equivalence and degradation
tests pass.

## Access And Application Gateway Contract

### Access Classes

Keep the architecture contract's browser access classes:

- `public_read`
- `protected`
- `public_read_protected_write`

`BrowserAccessConfig` resolves one canonical user-access token plus temporary
legacy aliases. Multiple configured aliases that disagree fail closed. Logs
and errors may report configuration state but never token values.

Ops API, DingTalk transport, GitHub, and provider credentials remain separate.

### Application Composition

The gateway composes focused controllers:

```text
app_gateway.py
  command_controller.py
  weekly_review_controller.py
  daily_market_brief_controller.py
  access_policy.py
```

The first deployment may preserve the `weekly-review-web` service name and
legacy `/command` request/response contract. It must not move more controller
logic into `weekly_review_web.py`. After caller inventory and compatibility
tests pass, the standalone `command-api` service is removed.

## DingTalk Transport Decision

`dingtalk-api` is an inbound HTTP callback adapter. `dingtalk-stream-bot` is an
outbound long-connection adapter. The repository indicates Stream is the main
group-message path, but production usage is not yet proven.

The HTTP adapter emits one sanitized usage event only after its validation and
payload parsing path accepts a webhook. It records message type and boolean
presence metadata, never message text, sender identifiers, signatures, or
secrets.

Retirement requires both:

- no configured DingTalk callback or other documented HTTP caller; and
- no accepted HTTP usage during one complete operational observation window.

If HTTP is unused, remove `dingtalk-api`. If both transports are required,
compose them behind a single DingTalk gateway supervisor only after shared
command authorization tests exist. Deletion is preferred to merging an unused
transport.

## Scheduler And History Execution

One `scheduler-host` owns schedule calculation, per-job overlap rules, and
per-job health for IPO reminders, account snapshots, and current Daily Market
Brief generation.

Historical brief generation remains a separate code and execution boundary but
not a separate always-on container. The scheduler host polls durable history
queue state and starts at most one on-demand history child process when work is
available. The child drains a bounded workload and exits when idle.

The child preserves the current lease, heartbeat, cancellation, deadline,
stale-item recovery, and report-finalization rules. This avoids running the
blocking, main-thread-signal-based history implementation in the scheduler
main process and prevents a history failure from terminating scheduled jobs.

## Expected Runtime Topology

If DingTalk HTTP is unused, the steady business application topology is:

1. app gateway
2. MCP
3. DingTalk Stream bot
4. scheduler host

If DingTalk HTTP remains required, the steady topology has five business
containers. The history child exists only while queued work is processed.

PostgreSQL and the independent Ops API are outside this business-container
count. Host Codex and research workers must be included in the resource audit;
their consolidation is not assumed by this design.

## Compatibility-First Migration

Every slice follows the same sequence:

1. Add characterization tests for the existing path.
2. Add the shared contract behind existing public behavior.
3. Migrate one consumer or capability.
4. Compare success, partial, error, and authorization behavior.
5. Deploy only the affected services and observe stability.
6. Remove the old responsibility after its retirement gate passes.
7. Re-run architecture and deployment-contract audits.

Compatibility aliases and old paths have explicit expiry gates; they are not
permanent dual architecture.

## Resource Evidence And Success Measures

Before service consolidation, collect sanitized idle and load snapshots for:

- every application container RSS and restart count;
- host Python systemd processes;
- host `MemAvailable`;
- Weekly/Daily generation;
- history generation;
- DingTalk message handling.

Success is not a fixed container count. It requires:

- no duplicate command controller or user-access policy;
- no migrated feature-local provider fallback;
- no missed or overlapping scheduled jobs during the observation window;
- no regression in browser, API, MCP, or active DingTalk behavior;
- measured idle RSS reduction or an evidence-backed decision to keep an
  isolation boundary;
- the existing deployment memory reserve remains satisfied.

## Deploy And Rollback

Contract-only and consumer migrations use the narrow deploy classification
supported by the executable deploy contract. Compose service removal or rename
uses the classifier's required full/config path and the serialized production
deploy lock.

Each production-changing slice records feature, pushed ref, deploy mode,
affected services, reason, verification path, and watch owner. Rollback is the
previous pushed release ref plus the corresponding previous Compose topology.
No overlapping deploy channels are permitted.

## Architecture Rule Admission

The following remain P1 report-only until the rule-admission gate passes:

- feature-local multi-provider fallback;
- duplicate access validators for one user route;
- provider results without source provenance;
- undeclared runtime service ownership;
- unknown application modules that expand targeted deploy scope.

Candidates for deterministic admission are unique route owner/access class,
conflicting legacy token aliases fail closed, and every registered provider has
capability/result fixtures. Runtime memory and caller-use rules remain
observational and cannot become static P0 gates.

## Acceptance Criteria

- Architecture design and three independently executable subsystem plans are
  reviewed against this document.
- Data-source consumers use the shared capability/result contract for the
  admitted migration scope.
- Browser command routes share one access-policy and command-controller path.
- Standalone `command-api` is removed only after compatibility evidence.
- DingTalk HTTP is retained, merged, or removed based on sanitized runtime
  evidence, not static assumption.
- Three scheduled services become one supervisor without job-health loss.
- History work is on-demand and retains lease/cancel/deadline semantics.
- Deploy classifier, Compose, health checks, and operational documentation
  match the final topology.
- Local tests, architecture audit, delivery audit, serialized deployment, and
  production verification complete or name one genuine external blocker.
