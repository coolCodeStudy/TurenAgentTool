# Product Decision Records

## 2026-06-18: Build Stock Decision System V1 Above Stock Evidence Cards

### Decision

Build Stock Decision System V1 as a full decision-support product layer, not as a lightweight prototype.

The existing "Level 1 decision card" should be renamed in product language to Stock Evidence Card. It remains the first-screen stock evidence summary. The new Stock Decision System sits above it and combines:

- User constraints.
- Current portfolio state.
- Stock evidence.
- Valuation frames.
- Technical setup.
- Chip and event structure.
- Sector regime.
- Market regime and market-sector leadership fit.
- Evidence quality and freshness.

The output should be a traceable Decision Ticket with score, recommendation, position-size range, decision gates, review triggers, stale data, confidence, and source links.

### Rationale

The user needs a system that answers whether a stock is suitable for the current portfolio and attention budget, not only whether the stock has attractive qualities.

The user also expects the system to evolve as new thoughts are captured over time. That requires strict separation between:

- Confirmed user preferences.
- Candidate user insights.
- Durable facts.
- Time-sensitive observations.
- Model inferences.
- Decision snapshots.

### Consequences

- V1 must include data-source strategy, storage design, freshness policy, token budget design, and knowledge graph integration from the start.
- The evidence card and the Decision Ticket should coexist: the evidence card summarizes graph evidence, while the Decision Ticket adds user constraints, portfolio state, fresh market/sector packs, scoring, gates, and review triggers.
- Strong recommendations require portfolio-fit reasoning and explicit veto conditions.
- The system should degrade to watch/wait when critical data is missing or stale.
- Candidate insights produced by decisions must remain pending until user confirmation.
