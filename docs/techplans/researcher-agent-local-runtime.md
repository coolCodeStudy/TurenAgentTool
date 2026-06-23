# Tech Plan: Researcher Agent Local Runtime

## Linked Product Document

- Product document: [`PRD-Researcher-Agent.md`](../product/PRD-Researcher-Agent.md)

## Summary

Build a local-first Researcher Agent that can run on the user's computer, gather external AI technology and investment research signals, generate structured reports, and hand off candidate work to Product Agent, Development Agent, or memory review. V1 should not require cloud deployment.

## Current Context

Existing related pieces:

- `investment_knowledge_mcp/research/jobs.py` and `scripts/research_agent_worker.py` manage stock research jobs.
- `docs/个股研究草稿协议.md` defines the stock research draft protocol.
- `docs/Agent工作模式演进计划.md` describes future agent tasks and cron-like execution.
- `docs/product/Product-Agent-Working-Protocol.md` defines Product Agent responsibility.
- `docs/product/Project-Management-Agent-Protocol.md` defines delivery tracking.

Important boundary:

- The Researcher Agent is a broader external intelligence role, not the same thing as the existing stock research job pipeline.
- V1 should run locally and persist local artifacts.
- Durable writes to InvestmentKnowledge remain explicit and reviewable.

## Touched Areas

Likely V1 modules and files:

- New local runner script:
  - `scripts/researcher_run.py`
- New package:
  - `investment_knowledge_mcp/researcher/__init__.py`
  - `investment_knowledge_mcp/researcher/models.py`
  - `investment_knowledge_mcp/researcher/sources.py`
  - `investment_knowledge_mcp/researcher/report.py`
  - `investment_knowledge_mcp/researcher/pipeline.py`
- Optional command router integration:
  - `investment_knowledge_mcp/command_router.py`
- Optional tests:
  - `tests` if present, or smoke coverage in `scripts/smoke_test.py`
- Local artifacts:
  - `drafts/researcher_runs/<run_id>/`

## Data Model

V1 can avoid a schema migration by writing JSON and Markdown artifacts locally.

Suggested local artifact contract:

```text
drafts/researcher_runs/<run_id>/
  run.json
  sources.json
  findings.json
  handoffs.json
  report.md
```

Suggested `run.json` fields:

```json
{
  "run_id": "2026-06-23-weekly",
  "trigger": "manual",
  "mode": "weekly",
  "lanes": ["ai_tech", "github_agents", "institution_reports", "investment_agents"],
  "time_window": {"start": "2026-06-16", "end": "2026-06-23"},
  "execution_location": "local",
  "created_at": "...",
  "status": "completed"
}
```

Suggested finding fields:

```json
{
  "title": "...",
  "lane": "ai_tech",
  "source_keys": ["openai_release_1"],
  "fact_summary": "...",
  "synthesis": "...",
  "why_it_matters": "...",
  "confidence": "medium",
  "handoff": "development"
}
```

## Source Providers

Start with provider interfaces, then implement narrow providers.

Provider interface:

```text
discover(query, time_window) -> list[SourceRecord]
fetch(source) -> SourceContent
summarize(source_content) -> SourceSummary
```

Initial providers:

- `OfficialReleaseProvider`: user-provided or configured URLs for OpenAI, Anthropic, Claude Code, and other official release pages.
- `GitHubSearchProvider`: GitHub repository search and repository metadata.
- `BlogRssProvider`: RSS or configured blogs for trusted AI/product engineering sources.
- `ManualReportProvider`: local files or user-provided report metadata for broker/institution reports.

V1 can ship with mock or manual provider support first, then add network providers behind explicit flags.

## Local Runtime

The runner should default to local execution:

```bash
.venv/bin/python scripts/researcher_run.py --mode weekly
.venv/bin/python scripts/researcher_run.py --lane ai-tech --days 7
.venv/bin/python scripts/researcher_run.py --topic "Claude Code latest release and investment workflow impact"
```

Runtime rules:

- Do not require ECS, Docker Compose, or cloud worker services.
- Do not start `command-api`, `dingtalk-api`, schedulers, or prod compose for V1 validation.
- If network access is required, make that explicit before running the command.
- If an external API token is missing, degrade to manual-source or configured-source mode instead of failing the whole run.

## Command Router Integration

After the local script works, add optional command aliases:

```text
researcher weekly
researcher ai-tech
researcher github-agents
researcher reports
researcher topic <text>
研究员 周报
研究员 AI技术
研究员 GitHub Agent
研究员 研报
研究员 研究 <text>
```

Command behavior:

- Query-like commands generate or read local artifacts.
- Commands that create candidate memory must show the candidate and require confirmation before formal memory writes.
- Commands that create development tasks should use the existing coding-task workflow.

## Implementation Steps

1. Add PRD and tech plan.
2. Add local artifact directory convention.
3. Implement data models for run, source, finding, and handoff.
4. Implement report rendering from structured findings.
5. Implement a manual-source provider so the pipeline can be verified without network.
6. Implement a local runner script that can generate a weekly or topic report from manual/configured sources.
7. Add optional network providers:
   - official release pages or RSS;
   - GitHub search;
   - configured blogs;
   - manual broker/institution report metadata.
8. Add command router aliases after the script contract is stable.
9. Add smoke checks for report generation and artifact structure.
10. Update project registry when implementation and verification evidence exists.

## Verification Plan

Local verification:

```bash
.venv/bin/python scripts/researcher_run.py --mode weekly --provider manual --fixture examples/researcher/manual_sources.json
.venv/bin/python scripts/smoke_test.py
```

Expected checks:

- A run directory is created under `drafts/researcher_runs/`.
- `run.json`, `sources.json`, `findings.json`, `handoffs.json`, and `report.md` exist.
- `report.md` includes executive summary, source coverage, caveats, and handoff sections.
- Formal `user_insights` are not written during report generation.
- No cloud service is required for the local run.

Network verification, only after explicit approval:

```bash
.venv/bin/python scripts/researcher_run.py --lane github-agents --days 7 --allow-network
```

Expected checks:

- Network providers label source timestamps and coverage.
- Missing tokens or rate limits are reported as caveats.
- The report remains useful when one provider fails.

## Deployment Impact

V1 has no required cloud deployment.

If command router integration is added later and the user wants DingTalk or cloud-served access, then the normal release path applies. Until then, this is a local Codex/workspace capability.

## Risks

- Broker and institution report sources may require credentials or manual uploads.
- GitHub API limits may require a token for reliable weekly runs.
- The researcher could produce too many handoffs; reports should rank and cap recommendations.
- Mixing local researcher artifacts with cloud stock research artifacts could confuse users; use separate paths and `execution_location=local`.
- Copyright and licensing boundaries must be kept explicit for paid reports.

## Open Decisions

- Which weekly schedule should be used once scheduling is automated.
- Which sources are trusted enough to include by default.
- Whether local artifacts should later sync to the cloud database.
- Whether the first command surface should be CLI only, command router, or DingTalk.

