# Agent Lessons

This file is the compact learning ledger for future agents. It is not a diary.
Add only lessons that should change future behavior.

## Local Verification Scope

- Do not expand a local feature verification into a full prod-style compose startup.
- For command-router or display behavior, validate with `scripts/smoke_test.py` and `scripts/ikg.py` first.
- `command-api` is only an HTTP wrapper around `handle_command(...)`; it is not required for normal local feature verification.
- Start `command-api`, `dingtalk-api`, schedulers, or broad compose profiles only when the user explicitly asks to test those surfaces or approves the exact service list.

## Service Startup Preflight

- Before any service action, state the service names, database target, exposed ports, and external integrations.
- Verify `POSTGRES_HOST` and `POSTGRES_PORT` before starting containers. A compose stack may silently connect to a fresh empty database.
- If a service should use the existing local knowledge base, point it at the established local DB instead of a newly created prod-compose DB.

## Secrets And HTTP Entrypoints

- `COMMAND_API_TOKEN` is required only when running the HTTP command API.
- Use strong tokens for command-api. Do not write temporary tokens, secrets, or credentials into docs, commits, logs, or summaries.
- If HTTP auth or gateway integration is not part of the task, prefer CLI/MCP verification over command-api verification.

## Daily Records Retired

- Do not create routine daily work logs by default.
- Durable project state belongs in `docs/当前工程状态.md`.
- Durable lessons belong in this file and `AGENTS.md`.
- Task plans belong in `docs/techplans/`.
- Historical milestones belong in `docs/project-history.md`.
