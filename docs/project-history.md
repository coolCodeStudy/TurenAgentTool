# Project History

This file preserves durable milestones extracted from the retired daily records.
It is intentionally not a day-by-day log.

## MVP And Messaging

- The local MVP established PostgreSQL/pgvector, stock profiles, sectors, knowledge items, user insights, candidate insights, OpenAI analysis, and DingTalk Stream bot integration.
- DingTalk Stream bot became the main group-message entry because ordinary outgoing webhooks can send messages but are not enough for receiving interactive commands.
- DingTalk write commands were restricted behind sender allowlists; query commands remained broadly available.

## Cloud Runtime

- The first cloud deployment path used GitHub Actions to package source and build/upload Docker images to ECS, avoiding unreliable direct pulls from ECS.
- Production database connection moved from hand-built `DATABASE_URL` strings to structured PostgreSQL environment variables after special characters in passwords caused host parsing failures.
- The primary runtime later moved to Singapore ECS because it could reach OpenAI reliably; the older domestic ECS path was not kept as the main runtime.
- The current main ops path is `Codex App -> InvestmentKnowledge MCP /mcp -> ECS internal Ops API`; the legacy Hermes Gateway path was removed.
- The 2026-07-19 architecture consolidation introduced shared external-data contracts, one browser command gateway/token policy, and a consolidated scheduler host with an on-demand history child. Production moved from nine application containers to five plus PostgreSQL, reducing measured application-container memory from about 431.16 MiB to 278.36 MiB while preserving the compatibility ports and serialized deploy/rollback gates.

## Futu/OpenD

- Futu OpenD was stabilized with a simple systemd setup: OpenD listens on `127.0.0.1:11111`, with a host/Docker bridge proxy exposed on `11112`.
- Container access uses `host.docker.internal` so app containers can reach the host OpenD proxy.
- Futu position queries are read-only and SDK-call parameters are filtered against the installed SDK signature.

## Portfolio And Review

- Portfolio display and analysis were adjusted for multi-currency holdings: HKD and USD should not be naively summed when FX conversion is unavailable.
- The product direction shifted away from daily long reports toward lower-friction portfolio review, weekly review, account snapshots, cash-flow adjustment, and knowledge-assisted interpretation.
- Account snapshots and trade records are the intended foundation for stricter monthly/weekly return attribution.

## Research Pipeline

- A Codex-first research job pipeline was introduced for queued stock research, artifacts, review/audit, import status, and worker observability.
- Cloud research worker execution became the default path, with execution metadata such as `execution_location`, `worker`, artifact flags, warnings, token usage, and import status visible in job lists.
- Task 2 was validated with a real cloud research sample: ASML US completed queueing, claiming, source expansion, draft, audit/review, artifact writeback, and import.
- Task 3 changed default stock display to Level 1 decision cards while keeping full evidence and artifacts available through explicit detail/verbose paths.

## Delivery System

- Delivery Coordinator became the single front door for product-feature delivery questions, with handoff packets routing work across Product, Development, Acceptance Testing, and Project Management.
- Delivery-state tooling was added through `scripts/audit_delivery_state.py`, covering broad audits, feature-specific checks, handoff-packet generation, acceptance queue gaps, routine daily-log detection, and pre-handoff strict gates.
- Delivery Coordinator was upgraded from handoff-only guidance to dispatch-first coordination, with `Delivery-Queue.md` for active dispatch tracking and `--dispatch-prompt` for next-role prompts.
- The first coordinator workflow exercise classified Kline Agent as ready for technical planning, Command Workbench as pending independent acceptance testing, and Weekly Review Web as blocked by failed acceptance testing.

## Known Open Items

- `/mcp` public access protection remains a security TODO; short-term deployments rely on network/security-group restrictions.
- Research worker stability, retry behavior, artifact access, and queue capacity remain ongoing control-plane concerns.
- Weekly/monthly performance review still needs a stronger data foundation around account snapshots, trades, cash flow, and FX.
