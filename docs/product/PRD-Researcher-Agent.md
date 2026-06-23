# PRD: Researcher Agent

## 1. Background

InvestmentKnowledge already has product, development, project-management, stock research, and weekly review workflows. The missing role is a standing Researcher Agent that watches the outside world for technology, market, institutional, and agent-system developments that may matter to the user's investment practice.

The user wants this role to behave like an internal company researcher: it can be asked to investigate a topic on demand, and it can also run a weekly research routine. Unlike the existing cloud stock research worker, the Researcher Agent may run on the user's local computer in V1.

## 2. User Problem

The user currently has to manually scan many sources:

- AI technology releases from OpenAI, Anthropic, Claude Code, GitHub projects, engineering blogs, and research papers.
- Investment-bank, broker, fund, and institutional research reports.
- New investment-related agent products, frameworks, and workflows.
- Public signals that may become relevant to current portfolio themes, watchlist ideas, or future product features.

The problem is not only information discovery. The user needs the system to turn external signals into traceable, reviewable research artifacts that can be handed to the Product Agent, Development Agent, or InvestmentKnowledge memory workflow without pretending that every observation is already a user-confirmed belief.

## 3. Product Positioning

The Researcher Agent is:

> A local-first external research role that gathers high-signal technology and investment intelligence, summarizes it with sources, and hands off candidate implications to the right internal role.

It is not:

- A fully automated investment decision maker.
- A trade recommendation engine.
- A replacement for the Product Agent's product judgment.
- A replacement for the Development Agent's implementation work.
- A channel for importing copyrighted research report content verbatim.
- A writer of formal user insights without user confirmation.

## 4. Goals

### V1 Goals

- Support on-demand local research runs triggered by the user.
- Support a weekly local research routine that can be started manually first, then scheduled later.
- Cover four initial research lanes:
  - AI technology radar.
  - GitHub and open-source agent tooling radar.
  - OpenAI, Anthropic, Claude Code, and other AI product release radar.
  - Investment institution and broker research report radar.
- Produce a structured Markdown report with source links, source quality labels, freshness, confidence, and action handoffs.
- Separate facts, synthesis, candidate implications, and user-confirmed beliefs.
- Hand off product ideas to the Product Agent, implementation ideas to the Development Agent, and memory candidates to the candidate-insight review flow.
- Run locally by default in V1, without requiring cloud worker deployment.

### Later Goals

- Add first-class scheduled jobs with run history and status.
- Add source connectors for authorized report repositories, RSS feeds, GitHub search, official release pages, and saved web sources.
- Add a web review surface for weekly researcher reports.
- Add deduplication and trend tracking across weeks.
- Add optional cloud syncing of local research artifacts.
- Add portfolio-aware relevance scoring.

## 5. Non-Goals

- Do not trade or prepare trade orders.
- Do not provide direct buy, sell, hold, stop-loss, or target-price instructions.
- Do not scrape or store full paid research reports without permission.
- Do not paste large copyrighted report excerpts into durable storage.
- Do not run the V1 researcher workload on the cloud by default.
- Do not automatically import inferred conclusions as formal user insights.
- Do not replace the existing stock research job pipeline.

## 6. Target Users

Primary user:

- The investment system owner who wants a weekly and on-demand intelligence function for AI technology, investment research, and agent-product developments.

Internal role users:

- Product Agent: receives product opportunities, product risks, and requirement candidates.
- Development Agent: receives technical implementation opportunities, provider backlog, and automation ideas.
- Project Management Agent: tracks whether accepted Researcher Agent scope has PRD, plan, implementation, and verification evidence.

## 7. Core User Stories

1. As a user, I can say "run the researcher" and receive a concise weekly research report.
2. As a user, I can ask the researcher to investigate a specific topic such as Claude Code releases, OpenAI releases, GitHub agent repos, broker AI reports, or investment-agent products.
3. As a user, I can see which sources were used and how fresh or reliable they are.
4. As a user, I can distinguish raw facts from the agent's synthesis and from candidate implications.
5. As a user, I can ask the Product Agent to turn a research finding into a PRD.
6. As a user, I can ask the Development Agent to turn a research finding into a technical task.
7. As a user, I can confirm or reject candidate investment insights before they enter durable memory.

## 8. Core Flow

```text
User trigger or weekly schedule
  -> choose research lanes and time window
  -> run local source discovery and retrieval
  -> normalize source metadata and short excerpts
  -> summarize facts and changes
  -> synthesize implications by lane
  -> generate handoffs for Product Agent, Development Agent, and memory review
  -> save local artifact
  -> optionally sync approved summaries or candidate insights to InvestmentKnowledge
```

## 9. Initial Research Lanes

### 9.1 AI Technology Radar

Purpose:

- Track major AI model, tool, API, agent runtime, coding-agent, infrastructure, and research developments.

Example sources:

- Official OpenAI and Anthropic release pages.
- Claude Code, Codex, and other coding-agent documentation.
- Engineering blogs from known AI infrastructure companies.
- Relevant papers or technical reports.

### 9.2 GitHub And Open-Source Radar

Purpose:

- Find high-signal or fast-growing repositories related to agents, coding tools, RAG, evaluation, context engineering, MCP, model routing, and investment-agent workflows.

Example metrics:

- Stars, recent star growth when available, commit recency, release recency, contributor activity, issue quality, and whether the project solves a real workflow problem.

### 9.3 Institutional And Broker Report Radar

Purpose:

- Surface new institutional views that may affect AI infrastructure, semiconductors, software, China internet, macro liquidity, market structure, and other portfolio themes.

Boundaries:

- Store source metadata, report title, publisher, date, topic tags, short compliant excerpts when allowed, and paraphrased summaries.
- Do not store full paid reports or long verbatim passages.
- Label source access limitations clearly.

### 9.4 Investment-Agent Product Radar

Purpose:

- Track products, workflows, and architectures that could improve InvestmentKnowledge itself.

Example outputs:

- Product ideas for the Product Agent.
- Provider or connector ideas for the Development Agent.
- Risks around reliability, compliance, source quality, or over-automation.

## 10. Output Contract

Default report:

```text
# Researcher Report: <date range or topic>

## Executive Summary
## AI Technology Radar
## GitHub And Open-Source Radar
## Institutional And Broker Report Radar
## Investment-Agent Product Radar
## Portfolio And Watchlist Relevance
## Product-Agent Handoffs
## Development-Agent Handoffs
## Candidate Memory Items
## Source Coverage And Caveats
```

Each finding should include:

- Title.
- Source URL or source identifier.
- Publisher or repository owner.
- Published or observed date.
- Lane.
- One-sentence fact summary.
- Why it matters.
- Confidence: `high`, `medium`, or `low`.
- Suggested handoff: `none`, `product`, `development`, `candidate_memory`, or `follow_up_research`.

## 11. Local Runtime Requirement

V1 must run on the user's local computer by default.

Local runtime means:

- Source discovery, retrieval, summarization, artifact generation, and manual review can run inside the local Codex/workspace environment.
- The feature does not require the cloud research worker to be deployed.
- Local artifacts are saved under the repository or an ignored local artifact directory.
- Any durable database write remains explicit and controlled.
- Cloud sync is optional and must be a separate user-approved action.

This requirement applies to the Researcher Agent's external topic research. It does not change the existing cloud-first expectation for the current stock research job pipeline unless a later product decision explicitly changes that pipeline.

## 12. Command And Entrypoint Impact

Candidate commands:

```text
researcher run
researcher weekly
researcher ai-tech
researcher github-agents
researcher reports
researcher investment-agents
researcher topic <free text>
researcher status
```

Chinese command aliases can be added after the English command contract is stable.

## 13. Data And Storage Impact

V1 can start with local artifacts and no database migration:

```text
drafts/researcher_runs/<run_id>/
  run.json
  report.md
  sources.json
  handoffs.json
```

Later database tables may include:

```text
researcher_runs
researcher_sources
researcher_findings
researcher_handoffs
```

Durable user beliefs must still use the existing candidate-insight confirmation path before becoming formal `user_insights`.

## 14. Permission And Safety Boundaries

- Network access is expected for real research runs and must be visible to the user.
- Paid or access-controlled reports require user-provided access and should not be redistributed.
- Source snippets must remain short and compliant.
- Formal memory writes require explicit user confirmation.
- Development tasks should be created as tasks, not directly implemented by the Researcher Agent.
- Product decisions should be routed to the Product Agent.

## 15. Acceptance Criteria

1. The user can trigger at least one local Researcher Agent run.
2. The run generates a Markdown report and structured source metadata.
3. The report separates facts, synthesis, candidate implications, and caveats.
4. The report includes at least one handoff section for Product Agent, Development Agent, or candidate memory review.
5. The feature can run without cloud worker deployment.
6. The feature does not write formal user insights without confirmation.
7. The feature does not store full paid reports or long copyrighted excerpts.
8. Project registry tracks PRD, technical plan, implementation, and verification state.

## 16. Risks And Open Decisions

- Source access for broker and institutional reports may require credentials, subscriptions, or manual uploads.
- GitHub trend detection may require API tokens or rate-limit handling.
- Weekly scheduling mechanism is not decided for V1; manual local trigger is acceptable first.
- The report may become too broad unless lanes and time windows are explicit.
- Product and development handoffs need a lightweight review loop so the researcher does not flood the backlog.

