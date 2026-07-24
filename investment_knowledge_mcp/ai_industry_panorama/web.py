from __future__ import annotations

from investment_knowledge_mcp.web_experience import (
    render_experience_css,
    render_primary_navigation,
)


def render_panorama_html() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Industry Panorama</title>
  <style>
  {render_experience_css()}
  .panorama-layout {{ display: grid; gap: 18px; }}
  .panorama-meta, .panorama-controls, .panorama-panel, .panorama-drawer {{
    background: var(--experience-surface);
    border: 1px solid var(--experience-border);
    border-radius: var(--experience-radius);
    padding: 16px;
  }}
  .panorama-controls {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
  .panorama-controls label {{ display: grid; gap: 6px; color: var(--experience-muted); font-size: 13px; }}
  .panorama-controls input, .panorama-controls select, .panorama-controls button {{ min-height: 40px; }}
  .panorama-view-switch {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .panorama-view-switch button[aria-pressed="true"] {{
    color: #ffffff;
    background: var(--experience-accent);
  }}
  .panorama-views {{ display: grid; grid-template-columns: minmax(0, 3fr) minmax(300px, 2fr); gap: 18px; }}
  .panorama-panel {{ min-width: 0; overflow: hidden; }}
  .panorama-graph-scroll {{ max-width: 100%; overflow-x: auto; overflow-y: hidden; }}
  #panorama-graph {{ display: block; width: 1460px; min-width: 1460px; overflow: hidden; }}
  #panorama-graph g[role="button"] {{ cursor: pointer; }}
  #panorama-graph text {{ fill: var(--experience-ink); font-size: 12px; }}
  .panorama-drawers {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }}
  .panorama-error {{ color: var(--experience-danger); }}
  .panorama-legend {{ display: flex; flex-wrap: wrap; gap: 12px; color: var(--experience-muted); }}
  @media (max-width: 900px) {{ .panorama-views {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body class="experience-shell" data-experience-ready="true">
  <a class="experience-skip-link" href="#panorama-main">Skip to panorama</a>
  {render_primary_navigation("ai_industry_panorama")}
  <main id="panorama-main" class="experience-main panorama-layout">
    <header class="page-header">
      <p>Evidence-backed industry learning surface</p>
      <h1>AI Industry Panorama</h1>
      <p>Trace disclosed and inferred relationships from demand to physical infrastructure.</p>
    </header>

    <section class="panorama-meta" aria-labelledby="release-heading">
      <h2 id="release-heading">Release</h2>
      <dl>
        <div><dt>Graph release</dt><dd id="release-id">Loading…</dd></div>
        <div><dt>Taxonomy</dt><dd id="taxonomy-version">Loading…</dd></div>
        <div><dt>Evidence cutoff</dt><dd id="evidence-cutoff">Loading…</dd></div>
      </dl>
      <div><h3>What changed</h3><ul id="change-summary"></ul></div>
    </section>

    <section class="panorama-controls" aria-label="Panorama filters">
      <label>Search
        <input id="panorama-search" type="search" placeholder="Entity, project, capability, or alias">
      </label>
      <label>Capability layer<select id="layer-filter"><option value="">All layers</option></select></label>
      <label>Geography<select id="geography-filter"><option value="">All geographies</option></select></label>
      <label>Time horizon<select id="time-filter"><option value="">All time horizons</option></select></label>
      <label>Lifecycle<select id="lifecycle-filter"><option value="">All lifecycle states</option></select></label>
      <label>Evidence<select id="evidence-filter"><option value="">All evidence tiers</option></select></label>
      <label>Confidence<select id="confidence-filter"><option value="">All confidence levels</option></select></label>
      <label><span>Assertion scope</span><span><input id="disclosed-only" type="checkbox"> Disclosed only</span></label>
      <label>Focus depth
        <select id="hop-depth"><option value="1">One hop</option><option value="2" selected>Two hops</option></select>
      </label>
      <button id="reset-panorama" type="button">Reset panorama</button>
    </section>

    <p id="panorama-status" role="status" aria-live="polite">Loading panorama…</p>
    <p id="panorama-error" class="panorama-error" role="alert" hidden>
      The panorama could not be loaded. Refresh the page to try again.
    </p>

    <div class="panorama-view-switch" role="group" aria-label="Panorama view">
      <button id="graph-view" type="button" aria-controls="graph-panel" aria-pressed="false">Graph</button>
      <button id="table-view" type="button" aria-controls="table-panel" aria-pressed="false">Table</button>
      <button id="both-view" type="button" aria-controls="graph-panel table-panel" aria-pressed="true">Both</button>
    </div>

    <section class="panorama-views">
      <div id="graph-panel" class="panorama-panel">
        <h2>Layered relationship map</h2>
        <div id="panorama-graph-scroll" class="panorama-graph-scroll" tabindex="0" aria-label="Scrollable relationship map">
          <svg id="panorama-graph" role="group" aria-label="AI industry relationship graph"></svg>
        </div>
      </div>
      <div id="table-panel" class="panorama-panel">
        <h2>Equivalent relationship table</h2>
        <div class="table-scroll">
          <table id="relationship-table">
            <caption>Relationships matching the same search, focus, and filters as the graph.</caption>
            <thead><tr><th>From</th><th>Relationship</th><th>To</th><th>Kind</th><th>Confidence</th><th>Evidence</th></tr></thead>
            <tbody id="relationship-table-body"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section aria-labelledby="legend-heading">
      <h2 id="legend-heading">Legend</h2>
      <div class="panorama-legend">
        <span>Disclosed fact, company guidance, or management claim — a sourced company assertion</span>
        <span>Inference — derived from cited disclosed premises</span>
        <span>Owner hypothesis — user-supplied thesis, not disclosed evidence</span>
      </div>
    </section>

    <section class="panorama-drawers" aria-label="Panorama details">
      <aside id="entity-drawer" class="panorama-drawer" aria-label="Entity details" tabindex="-1">
        <h2>Entity details</h2><p>Select a company or project.</p>
      </aside>
      <aside id="capability-drawer" class="panorama-drawer" aria-label="Capability details" tabindex="-1">
        <h2>Capability details</h2><p>Select a capability.</p>
      </aside>
      <aside id="relationship-drawer" class="panorama-drawer" aria-label="Relationship evidence" tabindex="-1">
        <h2>Relationship evidence</h2><p>Select a relationship.</p>
      </aside>
    </section>
  </main>
  <script src="/assets/ai-industry-panorama.js" defer></script>
</body>
</html>"""


def render_panorama_script() -> str:
    return r"""
(() => {
  "use strict";

  const API_PATH = "/api/ai-industry-panorama";
  const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;
  const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
  const byId = (id) => document.getElementById(id);
  const state = {
    projection: null,
    mode: "curated",
    viewMode: "both",
    focusEntityId: null,
    hopDepth: 2,
    search: "",
    filters: {
      layer: "",
      geography: "",
      time: "",
      lifecycle: "",
      evidence: "",
      confidence: "",
      disclosedOnly: false,
    },
    visibleRelationships: [],
    indexes: null,
  };
  const DISCLOSED_ASSERTION_KINDS = new Set([
    "disclosed_fact",
    "company_guidance",
    "management_claim",
  ]);
  const ASSERTION_KIND_PRIORITY = {
    disclosed_fact: 0,
    company_guidance: 1,
    management_claim: 2,
    inferred_exposure: 3,
    user_hypothesis: 4,
  };
  const SENSITIVE_QUERY_NAMES = new Set([
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "credential",
    "key",
    "password",
    "private_key",
    "secret",
    "sig",
    "signature",
    "token",
  ]);
  const asciiLower = (value) => String(value).replace(
    /[A-Z]/g,
    (character) => character.toLowerCase()
  );
  const stableCompare = (left, right) => (
    left < right ? -1 : left > right ? 1 : 0
  );

  const makeElement = (tagName, text = "") => {
    const element = document.createElement(tagName);
    element.textContent = text;
    return element;
  };

  const makeSvg = (tagName, attributes = {}) => {
    const element = document.createElementNS(SVG_NAMESPACE, tagName);
    for (const [name, value] of Object.entries(attributes)) {
      element.setAttribute(name, String(value));
    }
    return element;
  };

  const setText = (id, value) => {
    const element = byId(id);
    if (element) element.textContent = value == null ? "Unknown" : String(value);
  };

  const appendDetail = (container, label, value) => {
    const line = makeElement("p");
    line.append(makeElement("strong", `${label}: `), makeElement("span", value || "Unknown"));
    container.append(line);
  };

  const makeList = (heading, values, emptyText = "None in this release.") => {
    const wrapper = makeElement("section");
    wrapper.append(makeElement("h3", heading));
    const list = makeElement("ul");
    const admitted = values && values.length ? values : [emptyText];
    list.append(...admitted.map((value) => makeElement("li", value)));
    wrapper.append(list);
    return wrapper;
  };

  const activateWithKeyboard = (element, callback) => {
    element.addEventListener("click", callback);
    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        if (event.preventDefault) event.preventDefault();
        callback();
      }
    });
  };

  const safeExternalUrl = (value) => {
    try {
      const parsed = new URL(String(value));
      if (parsed.protocol !== "https:" || parsed.username || parsed.password) return null;
      for (const name of parsed.searchParams.keys()) {
        if (SENSITIVE_QUERY_NAMES.has(asciiLower(name))) return null;
      }
      return parsed.href;
    } catch (_error) {
      return null;
    }
  };

  const safeInternalPath = (value) => value === "/command" ? value : null;

  const makeExternalLink = (label, value) => {
    const href = safeExternalUrl(value);
    if (!href) return null;
    const link = makeElement("a", label);
    link.setAttribute("href", href);
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener noreferrer");
    return link;
  };

  const focusDetails = (drawer, announcement) => {
    drawer.setAttribute("tabindex", "-1");
    drawer.focus();
    setText("panorama-status", announcement);
  };

  const renderMetadata = (projection) => {
    const release = projection.release || {};
    setText("release-id", release.release_id);
    setText("taxonomy-version", release.taxonomy_version);
    setText("evidence-cutoff", release.evidence_cutoff);
    const summary = byId("change-summary");
    summary.replaceChildren(
      ...(release.change_summary || []).map((item) => makeElement("li", item))
    );
  };

  const buildIndexes = (projection) => ({
    entities: new Map(
      projection.entities.map((entity) => [entity.entity_id, entity])
    ),
    taxonomy: new Map(
      projection.taxonomy.map((item) => [item.taxonomy_id, item])
    ),
    geography: new Map(
      projection.facets.geography.map((item) => [item.id, item.label])
    ),
    evidence: new Map(
      projection.evidence.map((item) => [item.evidence_id, item])
    ),
    sources: new Map(
      projection.sources.map((item) => [item.source_id, item])
    ),
    assertionRelationships: new Map(
      projection.relationships.map((item) => [item.assertion_id, item])
    ),
  });

  const relationshipEvidenceTiers = (relationship) => new Set(
    relationship.evidence_ids
      .map((id) => state.indexes.evidence.get(id))
      .filter(Boolean)
      .map((evidence) => state.indexes.sources.get(evidence.source_id))
      .filter(Boolean)
      .map((source) => source.tier)
  );

  const relationshipLayers = (relationship) => {
    const endpointIds = [relationship.source_entity_id, relationship.target_entity_id];
    return new Set(
      endpointIds
        .map((id) => state.indexes.entities.get(id))
        .filter(Boolean)
        .flatMap((entity) => entity.taxonomy_ids)
        .map((taxonomyId) => state.indexes.taxonomy.get(taxonomyId))
        .filter(Boolean)
        .map((taxonomy) => taxonomy.layer)
    );
  };

  const focusedRelationshipIds = (relationships) => {
    if (!state.focusEntityId) return null;
    let frontier = new Set([state.focusEntityId]);
    const visitedEntities = new Set(frontier);
    const admitted = new Set();
    for (let depth = 0; depth < state.hopDepth; depth += 1) {
      const next = new Set();
      for (const relationship of relationships) {
        const sourceSeen = frontier.has(relationship.source_entity_id);
        const targetSeen = frontier.has(relationship.target_entity_id);
        if (!sourceSeen && !targetSeen) continue;
        admitted.add(relationship.relationship_id);
        const other = sourceSeen
          ? relationship.target_entity_id
          : relationship.source_entity_id;
        if (!visitedEntities.has(other)) next.add(other);
      }
      next.forEach((id) => visitedEntities.add(id));
      frontier = next;
    }
    return admitted;
  };

  const searchMatches = (relationship) => {
    const query = asciiLower(state.search.trim());
    if (!query) return true;
    const endpointMatches = [
      relationship.source_entity_id,
      relationship.target_entity_id,
    ].some((id) => {
      const entity = state.indexes.entities.get(id);
      return [
        entity.label,
        entity.kind,
        entity.summary,
        ...(entity.aliases || []),
        ...(entity.capability_roles || []),
      ].some((value) => asciiLower(value).includes(query));
    });
    return endpointMatches || [
      relationship.relationship_type,
      relationship.text,
      relationship.assertion_kind,
    ].some((value) => asciiLower(value).includes(query));
  };

  const periodBounds = (value) => {
    if (!value) return null;
    const match = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/.exec(value);
    if (!match) return null;
    const [, year, month, day] = match;
    return {
      start: `${year}-${month || "01"}-${day || "01"}`,
      end: `${year}-${month || "12"}-${day || "31"}`,
    };
  };

  const relationshipOverlapsPeriod = (relationship, selected) => {
    const hasReportingPeriod = Boolean(
      relationship.reporting_period_start || relationship.reporting_period_end
    );
    const startValue = hasReportingPeriod
      ? relationship.reporting_period_start
      : relationship.effective_from;
    const endValue = hasReportingPeriod
      ? relationship.reporting_period_end
      : relationship.effective_to;
    if (selected === "unknown") return !startValue && !endValue;
    if (!startValue && !endValue) return false;
    const years = selected.split("-");
    const selectedStart = `${years[0]}-01-01`;
    const selectedEnd = `${years[1] || years[0]}-12-31`;
    const relationshipStart = periodBounds(startValue)?.start || "0000-01-01";
    const relationshipEnd = periodBounds(endValue)?.end || "9999-12-31";
    return relationshipStart <= selectedEnd && relationshipEnd >= selectedStart;
  };

  const passesNonFocusFilters = (relationship) => {
      if (!searchMatches(relationship)) return false;
      if (
        state.filters.layer
        && !relationshipLayers(relationship).has(state.filters.layer)
      ) return false;
      if (
        state.filters.geography
        && !relationship.geography_roles.some(
          ([geographyId]) => geographyId === state.filters.geography
        )
      ) return false;
      if (
        state.filters.time
        && !relationshipOverlapsPeriod(relationship, state.filters.time)
      ) {
        return false;
      }
      if (
        state.filters.lifecycle
        && relationship.lifecycle_state !== state.filters.lifecycle
      ) return false;
      if (
        state.filters.evidence
        && !relationshipEvidenceTiers(relationship).has(state.filters.evidence)
      ) return false;
      if (
        state.filters.confidence
        && relationship.confidence_label !== state.filters.confidence
      ) return false;
      if (
        state.filters.disclosedOnly
        && !DISCLOSED_ASSERTION_KINDS.has(relationship.assertion_kind)
      ) return false;
      return true;
  };

  const curatedRelationships = () => {
    const selected = new Map();
    const anchors = state.projection.entities
      .filter((entity) => entity.is_demand_anchor)
      .sort((left, right) => stableCompare(left.entity_id, right.entity_id));
    for (const anchor of anchors) {
      const candidates = state.projection.relationships
        .filter(
          (relationship) => relationship.source_entity_id === anchor.entity_id
            || relationship.target_entity_id === anchor.entity_id
        )
        .sort((left, right) => {
          const otherEntity = (relationship) => state.indexes.entities.get(
            relationship.source_entity_id === anchor.entity_id
              ? relationship.target_entity_id
              : relationship.source_entity_id
          );
          const leftKind = otherEntity(left)?.kind;
          const rightKind = otherEntity(right)?.kind;
          const kindDifference = (
            (leftKind === "organization" || leftKind === "project" ? 0 : 1)
            - (rightKind === "organization" || rightKind === "project" ? 0 : 1)
          );
          if (kindDifference) return kindDifference;
          const assertionDifference = (
            (ASSERTION_KIND_PRIORITY[left.assertion_kind] ?? 9)
            - (ASSERTION_KIND_PRIORITY[right.assertion_kind] ?? 9)
          );
          if (assertionDifference) return assertionDifference;
          return stableCompare(right.observed_at, left.observed_at)
            || stableCompare(left.relationship_id, right.relationship_id);
        });
      candidates.slice(0, 2).forEach(
        (relationship) => selected.set(relationship.relationship_id, relationship)
      );
    }
    return [...selected.values()].sort(
      (left, right) => stableCompare(left.relationship_id, right.relationship_id)
    );
  };

  const deriveVisibleRelationships = () => {
    const base = state.mode === "curated"
      ? curatedRelationships()
      : state.projection.relationships;
    const admitted = base.filter(passesNonFocusFilters);
    const focusedIds = focusedRelationshipIds(admitted);
    return admitted.filter(
      (relationship) => !focusedIds || focusedIds.has(relationship.relationship_id)
    ).sort(
      (left, right) => stableCompare(left.relationship_id, right.relationship_id)
    );
  };

  const entityLayer = (entity) => {
    if (entity.is_demand_anchor) return 1;
    const orders = entity.taxonomy_ids
      .map((id) => state.indexes.taxonomy.get(id))
      .filter(Boolean)
      .map((item) => item.sort_order);
    return orders.length ? Math.min(...orders) : 6;
  };

  const renderEntityDrawer = (entity) => {
    const drawer = byId("entity-drawer");
    const related = state.projection.relationships.filter(
      (relationship) => relationship.source_entity_id === entity.entity_id
        || relationship.target_entity_id === entity.entity_id
    );
    const sentence = (relationship) => {
      const source = state.indexes.entities.get(relationship.source_entity_id);
      const target = state.indexes.entities.get(relationship.target_entity_id);
      return `${source?.label || "Unknown"} ${relationship.relationship_type} `
        + `${target?.label || "Unknown"} — ${relationship.assertion_kind}; `
        + `observed ${relationship.observed_at}.`;
    };
    const disclosed = related
      .filter((item) => DISCLOSED_ASSERTION_KINDS.has(item.assertion_kind))
      .map(sentence);
    const inferred = related
      .filter((item) => item.assertion_kind === "inferred_exposure")
      .map(sentence);
    const hypotheses = related.filter(
      (item) => item.assertion_kind === "user_hypothesis"
    );
    const latestEvidenceDate = related
      .flatMap((item) => item.evidence_ids)
      .map((id) => state.indexes.evidence.get(id))
      .filter(Boolean)
      .map((evidence) => state.indexes.sources.get(evidence.source_id))
      .filter(Boolean)
      .flatMap((source) => [source.publication_date, source.retrieval_date])
      .filter(Boolean)
      .sort()
      .slice(-1)[0];
    const geographies = entity.geography_ids.map(
      (id) => state.indexes.geography.get(id) || id
    );
    const fragments = [makeElement("h2", entity.label), makeElement("p", entity.summary)];
    const identity = makeElement("section");
    appendDetail(identity, "Entity type", entity.kind);
    appendDetail(identity, "Aliases", entity.aliases.join(", ") || "None");
    appendDetail(identity, "Geography", geographies.join(", "));
    appendDetail(identity, "Capability roles", entity.capability_roles.join(", "));
    appendDetail(identity, "Last reviewed", entity.last_reviewed_at);
    appendDetail(identity, "Latest evidence date", latestEvidenceDate);
    appendDetail(identity, "Freshness", entity.freshness_state);
    appendDetail(identity, "Coverage gaps", entity.coverage_gaps);
    fragments.push(identity);
    fragments.push(makeList("Disclosed relationships", disclosed));
    fragments.push(makeList("Inferred exposures", inferred));
    const hypothesisSection = makeElement("section");
    hypothesisSection.append(makeElement("h3", "Owner hypotheses"));
    if (!hypotheses.length) {
      hypothesisSection.append(makeElement("p", "No owner hypotheses."));
    }
    for (const hypothesis of hypotheses) {
      const item = makeElement("article");
      appendDetail(item, "Hypothesis", hypothesis.text);
      appendDetail(item, "Limitations", hypothesis.limitations);
      appendDetail(item, "Observed", hypothesis.observed_at);
      appendDetail(item, "Reviewed", hypothesis.reviewed_at);
      hypothesisSection.append(item);
    }
    fragments.push(hypothesisSection);
    fragments.push(
      makeList(
        "Dated facts and guidance",
        related
          .filter((item) => DISCLOSED_ASSERTION_KINDS.has(item.assertion_kind))
          .map(
            (item) => `${item.assertion_kind}: ${item.text} `
              + `(observed ${item.observed_at}; reviewed ${item.reviewed_at})`
          )
      )
    );
    const links = makeElement("section");
    links.append(makeElement("h3", "Research and valuation"));
    if (!entity.research_links.length) {
      links.append(makeElement("p", "No admitted research or valuation link."));
    }
    for (const item of entity.research_links) {
      appendDetail(links, "Listing", item.canonical_stock_id);
      const path = safeInternalPath(item.internal_path);
      if (path) {
        const link = makeElement("a", item.label);
        link.setAttribute("href", path);
        links.append(link);
      } else {
        links.append(makeElement("p", item.label));
      }
      links.append(makeElement("p", `Command hint (not executed): ${item.command_hint}`));
    }
    fragments.push(links);
    drawer.replaceChildren(...fragments);
    focusDetails(drawer, `Entity details opened: ${entity.label}.`);
  };

  const renderCapabilityDrawer = (entity) => {
    const drawer = byId("capability-drawer");
    const taxonomy = entity.taxonomy_ids
      .map((id) => state.indexes.taxonomy.get(id))
      .filter(Boolean);
    const upstream = state.projection.relationships
      .filter((item) => item.target_entity_id === entity.entity_id)
      .map((item) => {
        const source = state.indexes.entities.get(item.source_entity_id);
        return `${source?.label || "Unknown"} — ${item.relationship_type}`;
      });
    const downstream = state.projection.relationships
      .filter((item) => item.source_entity_id === entity.entity_id)
      .map((item) => {
        const target = state.indexes.entities.get(item.target_entity_id);
        return `${item.relationship_type} — ${target?.label || "Unknown"}`;
      });
    const details = makeElement("section");
    appendDetail(
      details,
      "Definition",
      taxonomy.map((item) => item.definition).join(" ")
    );
    appendDetail(
      details,
      "Standards context",
      taxonomy.map((item) => item.standards_context).join(" ")
    );
    appendDetail(
      details,
      "Geography",
      entity.geography_ids
        .map((id) => state.indexes.geography.get(id) || id)
        .join(", ")
    );
    appendDetail(
      details,
      "Coverage gaps",
      [entity.coverage_gaps, ...taxonomy.map((item) => item.coverage_gaps)].join(" ")
    );
    drawer.replaceChildren(
      makeElement("h2", entity.label),
      makeElement("p", entity.summary),
      details,
      makeList("Upstream roles", upstream),
      makeList("Downstream roles", downstream),
    );
    focusDetails(drawer, `Capability details opened: ${entity.label}.`);
  };

  const renderRelationshipDrawer = (relationship) => {
    const drawer = byId("relationship-drawer");
    const sourceEntity = state.indexes.entities.get(relationship.source_entity_id);
    const targetEntity = state.indexes.entities.get(relationship.target_entity_id);
    const details = makeElement("section");
    appendDetail(details, "Direction", `${sourceEntity?.label || "Unknown"} → ${targetEntity?.label || "Unknown"}`);
    appendDetail(details, "Relationship type", relationship.relationship_type);
    appendDetail(details, "Assertion", relationship.text);
    appendDetail(details, "Assertion kind", relationship.assertion_kind);
    appendDetail(details, "Lifecycle", relationship.lifecycle_state);
    appendDetail(
      details,
      "Valid time",
      `${relationship.effective_from || "unknown"} to ${relationship.effective_to || "unknown"}`
    );
    appendDetail(details, "Observed", relationship.observed_at);
    appendDetail(details, "Reviewed", relationship.reviewed_at);
    appendDetail(
      details,
      "Geography",
      relationship.geography_roles.map(
        ([id, role]) => `${state.indexes.geography.get(id) || id} (${role})`
      ).join(", ")
    );
    appendDetail(details, "Confidence", relationship.confidence_label);
    appendDetail(details, "Confidence inputs", relationship.confidence_rationale);
    appendDetail(details, "Limitations", relationship.limitations);
    const appendCitation = (container, evidence, source, premiseLink) => {
      const item = makeElement("article");
      item.append(makeElement("h4", source.document_title));
      appendDetail(item, "Publisher", source.publisher);
      appendDetail(item, "Publication", source.publication_date || "Undated");
      appendDetail(item, "Retrieved", source.retrieval_date);
      appendDetail(item, "Tier", source.tier);
      appendDetail(item, "Locator", evidence.locator);
      appendDetail(item, "Stable source locator", source.immutable_locator);
      appendDetail(item, "Evidence excerpt", evidence.bounded_excerpt);
      appendDetail(item, "Review state", evidence.review_state);
      const link = makeExternalLink("Open official source", source.url);
      if (link) {
        if (premiseLink) link.setAttribute("data-premise-source-link", "true");
        item.append(link);
      }
      container.append(item);
    };
    const premiseSection = makeElement("section");
    premiseSection.append(makeElement("h3", "Inference derivation"));
    if (!relationship.premise_assertion_ids.length) {
      premiseSection.append(makeElement("p", "No inference premises."));
    }
    for (const premiseId of relationship.premise_assertion_ids) {
      const premise = state.indexes.assertionRelationships.get(premiseId);
      const premiseItem = makeElement("article");
      premiseItem.setAttribute("data-premise-assertion-id", premiseId);
      premiseItem.append(makeElement("h4", premiseId));
      if (!premise) {
        premiseItem.append(makeElement("p", "Premise unavailable."));
        premiseSection.append(premiseItem);
        continue;
      }
      appendDetail(premiseItem, "Premise assertion", premise.text);
      appendDetail(premiseItem, "Assertion kind", premise.assertion_kind);
      appendDetail(premiseItem, "Limitations", premise.limitations);
      for (const evidenceId of new Set(premise.evidence_ids)) {
        const evidence = state.indexes.evidence.get(evidenceId);
        const source = evidence && state.indexes.sources.get(evidence.source_id);
        if (evidence && source) appendCitation(premiseItem, evidence, source, true);
      }
      premiseSection.append(premiseItem);
    }
    const evidenceSection = makeElement("section");
    evidenceSection.append(makeElement("h3", "Evidence and sources"));
    for (const evidenceId of new Set(relationship.evidence_ids)) {
      const evidence = state.indexes.evidence.get(evidenceId);
      const source = evidence && state.indexes.sources.get(evidence.source_id);
      if (!evidence || !source) continue;
      appendCitation(evidenceSection, evidence, source, false);
    }
    drawer.replaceChildren(
      makeElement("h2", "Relationship evidence"),
      details,
      premiseSection,
      evidenceSection,
    );
    focusDetails(
      drawer,
      `Relationship evidence opened: ${sourceEntity?.label || "Unknown"} to `
        + `${targetEntity?.label || "Unknown"}.`
    );
  };

  const selectEntity = (entity) => {
    state.mode = "complete";
    state.focusEntityId = entity.entity_id;
    state.search = "";
    byId("panorama-search").value = "";
    renderAll();
    if (entity.kind === "capability") renderCapabilityDrawer(entity);
    else renderEntityDrawer(entity);
  };

  const renderGraph = (relationships) => {
    const graph = byId("panorama-graph");
    const entityIds = new Set(
      relationships.flatMap(
        (relationship) => [
          relationship.source_entity_id,
          relationship.target_entity_id,
        ]
      )
    );
    if (state.mode === "curated") {
      state.projection.entities
        .filter((entity) => entity.is_demand_anchor)
        .forEach((entity) => entityIds.add(entity.entity_id));
    }
    if (state.focusEntityId) entityIds.add(state.focusEntityId);
    const entities = [...entityIds]
      .map((id) => state.indexes.entities.get(id))
      .filter(Boolean)
      .sort((left, right) => (
        entityLayer(left) - entityLayer(right)
        || stableCompare(left.label, right.label)
        || stableCompare(left.entity_id, right.entity_id)
      ));
    const layers = new Map();
    for (const entity of entities) {
      const layer = entityLayer(entity);
      if (!layers.has(layer)) layers.set(layer, []);
      layers.get(layer).push(entity);
    }
    const positions = new Map();
    for (const [layer, items] of layers) {
      items.forEach((entity, index) => {
        positions.set(entity.entity_id, {
          x: 110 + (layer - 1) * 250,
          y: 60 + index * 78,
        });
      });
    }
    const maxRows = Math.max(1, ...[...layers.values()].map((items) => items.length));
    graph.setAttribute("width", "1460");
    graph.setAttribute("height", String(Math.max(560, maxRows * 78 + 80)));
    const marker = makeSvg("marker", {
      id: "panorama-arrow",
      markerWidth: 8,
      markerHeight: 8,
      refX: 7,
      refY: 3,
      orient: "auto",
      markerUnits: "strokeWidth",
    });
    marker.append(makeSvg("path", {d: "M0,0 L0,6 L8,3 z", fill: "#617286"}));
    const definitions = makeSvg("defs");
    definitions.append(marker);
    const headings = [...state.projection.taxonomy]
      .sort((left, right) => left.sort_order - right.sort_order)
      .map((item) => {
        const heading = makeSvg("text", {
          x: 110 + (item.sort_order - 1) * 250,
          y: 20,
          "text-anchor": "middle",
        });
        heading.textContent = item.label;
        return heading;
      });

    const edges = relationships.map((relationship) => {
      const sourcePosition = positions.get(relationship.source_entity_id);
      const targetPosition = positions.get(relationship.target_entity_id);
      const source = state.indexes.entities.get(relationship.source_entity_id);
      const target = state.indexes.entities.get(relationship.target_entity_id);
      const label = `${source?.label || "Unknown"} ${relationship.relationship_type} `
        + `${target?.label || "Unknown"}`;
      const group = makeSvg("g", {
        "data-relationship-id": relationship.relationship_id,
        "data-assertion-kind": relationship.assertion_kind,
        tabindex: "0",
        role: "button",
        "aria-label": label,
      });
      const edgeStyle = relationship.assertion_kind === "user_hypothesis"
        ? {stroke: "#7a3e9d", dash: "2 3"}
        : relationship.assertion_kind === "inferred_exposure"
          ? {stroke: "#a86600", dash: "6 5"}
          : {stroke: "#617286", dash: "0"};
      group.append(
        makeSvg("line", {
          x1: sourcePosition?.x || 0,
          y1: sourcePosition?.y || 0,
          x2: targetPosition?.x || 0,
          y2: targetPosition?.y || 0,
          stroke: edgeStyle.stroke,
          "stroke-width": 2,
          "marker-end": "url(#panorama-arrow)",
          "stroke-dasharray": edgeStyle.dash,
        })
      );
      activateWithKeyboard(group, () => renderRelationshipDrawer(relationship));
      return group;
    });

    const nodes = entities.map((entity) => {
      const position = positions.get(entity.entity_id);
      const group = makeSvg("g", {
        "data-entity-id": entity.entity_id,
        tabindex: "0",
        role: "button",
        "aria-label": `${entity.kind}: ${entity.label}`,
      });
      group.append(
        makeSvg("rect", {
          x: position.x - 88,
          y: position.y - 22,
          width: 176,
          height: 44,
          rx: 8,
          fill: entity.entity_id === state.focusEntityId ? "#dbeafe" : "#fffdf8",
          stroke: entity.is_demand_anchor ? "#2369a8" : "#9cabbc",
        })
      );
      const label = makeSvg("text", {
        x: position.x,
        y: position.y + 4,
        "text-anchor": "middle",
      });
      label.textContent = entity.label.length > 27
        ? `${entity.label.slice(0, 26)}…`
        : entity.label;
      group.append(label);
      activateWithKeyboard(group, () => selectEntity(entity));
      return group;
    });
    graph.replaceChildren(definitions, ...headings, ...edges, ...nodes);
  };

  const renderTable = (relationships) => {
    const table = byId("relationship-table-body");
    const rows = relationships.map((relationship) => {
      const source = state.indexes.entities.get(relationship.source_entity_id);
      const target = state.indexes.entities.get(relationship.target_entity_id);
      const row = makeElement("tr");
      row.setAttribute("data-relationship-id", relationship.relationship_id);
      for (const value of [
        source?.label || "Unknown",
        relationship.relationship_type,
        target?.label || "Unknown",
        relationship.assertion_kind,
        relationship.confidence_label,
      ]) {
        row.append(makeElement("td", value));
      }
      const actionCell = makeElement("td");
      const action = makeElement("button", "View evidence");
      action.setAttribute("type", "button");
      action.addEventListener("click", () => renderRelationshipDrawer(relationship));
      actionCell.append(action);
      row.append(actionCell);
      return row;
    });
    table.replaceChildren(...rows);
  };

  const renderAll = () => {
    if (!state.projection) return;
    state.visibleRelationships = deriveVisibleRelationships();
    renderGraph(state.visibleRelationships);
    renderTable(state.visibleRelationships);
    const focus = state.focusEntityId
      ? state.indexes.entities.get(state.focusEntityId)?.label
      : null;
    setText(
      "panorama-status",
      `${state.mode === "curated" ? "Curated start" : "Complete V1"}: `
        + `${state.visibleRelationships.length} relationships shown`
        + `${focus ? ` around ${focus} (${state.hopDepth} hop).` : "."}`
    );
  };

  const derivePeriodFacets = (projection) => {
    const years = new Set();
    for (const relationship of projection.relationships) {
      for (const value of [
        relationship.reporting_period_start,
        relationship.reporting_period_end,
        relationship.effective_from,
        relationship.effective_to,
      ]) {
        const match = /^(\d{4})/.exec(value || "");
        if (match) years.add(Number(match[1]));
      }
    }
    const cutoffYear = Number(String(projection.release.evidence_cutoff).slice(0, 4));
    years.add(cutoffYear);
    years.add(cutoffYear + 1);
    const items = [...years]
      .sort((left, right) => left - right)
      .map((year) => ({id: String(year), label: String(year)}));
    items.push({
      id: `${cutoffYear}-${cutoffYear + 1}`,
      label: `${cutoffYear}–${cutoffYear + 1}`,
    });
    items.push({id: "unknown", label: "Unknown valid period"});
    return items;
  };

  const populateSelect = (id, allLabel, items) => {
    const select = byId(id);
    const all = makeElement("option", allLabel);
    all.value = "";
    const options = items.map((item) => {
      const option = makeElement("option", item.label);
      option.value = item.id;
      return option;
    });
    select.replaceChildren(all, ...options);
    select.value = "";
  };

  const populateControls = (projection) => {
    populateSelect("layer-filter", "All layers", projection.facets.layer);
    populateSelect(
      "geography-filter",
      "All geographies",
      projection.facets.geography
    );
    populateSelect(
      "time-filter",
      "All valid periods",
      derivePeriodFacets(projection)
    );
    populateSelect(
      "lifecycle-filter",
      "All lifecycle states",
      projection.facets.lifecycle
    );
    populateSelect(
      "evidence-filter",
      "All evidence tiers",
      projection.facets.evidence_tier
    );
    populateSelect(
      "confidence-filter",
      "All confidence levels",
      projection.facets.confidence
    );
  };

  const setViewMode = (mode) => {
    state.viewMode = mode;
    byId("graph-panel").hidden = mode === "table";
    byId("table-panel").hidden = mode === "graph";
    for (const [id, value] of [
      ["graph-view", "graph"],
      ["table-view", "table"],
      ["both-view", "both"],
    ]) {
      byId(id).setAttribute("aria-pressed", String(mode === value));
    }
  };

  const resetState = () => {
    state.mode = "complete";
    state.focusEntityId = null;
    state.hopDepth = 2;
    state.search = "";
    state.filters = {
      layer: "",
      geography: "",
      time: "",
      lifecycle: "",
      evidence: "",
      confidence: "",
      disclosedOnly: false,
    };
    byId("panorama-search").value = "";
    for (const id of [
      "layer-filter",
      "geography-filter",
      "time-filter",
      "lifecycle-filter",
      "evidence-filter",
      "confidence-filter",
    ]) byId(id).value = "";
    byId("disclosed-only").checked = false;
    byId("hop-depth").value = "2";
    renderAll();
  };

  const wireControls = () => {
    byId("panorama-search").addEventListener("input", (event) => {
      state.mode = "complete";
      state.search = event.target.value;
      renderAll();
    });
    const bindings = {
      "layer-filter": "layer",
      "geography-filter": "geography",
      "time-filter": "time",
      "lifecycle-filter": "lifecycle",
      "evidence-filter": "evidence",
      "confidence-filter": "confidence",
    };
    for (const [id, field] of Object.entries(bindings)) {
      byId(id).addEventListener("change", (event) => {
        state.mode = "complete";
        state.filters[field] = event.target.value;
        renderAll();
      });
    }
    byId("disclosed-only").addEventListener("change", (event) => {
      state.mode = "complete";
      state.filters.disclosedOnly = Boolean(event.target.checked);
      renderAll();
    });
    byId("hop-depth").addEventListener("change", (event) => {
      state.mode = "complete";
      state.hopDepth = event.target.value === "1" ? 1 : 2;
      renderAll();
    });
    byId("graph-view").addEventListener("click", () => setViewMode("graph"));
    byId("table-view").addEventListener("click", () => setViewMode("table"));
    byId("both-view").addEventListener("click", () => setViewMode("both"));
    byId("reset-panorama").addEventListener("click", resetState);
  };

  const responseByteLength = (text) => new TextEncoder().encode(text).byteLength;

  const readBoundedBody = async (response) => {
    const rawDeclaredLength = response.headers.get("content-length");
    if (rawDeclaredLength !== null && !/^\d+$/.test(rawDeclaredLength)) {
      throw new Error("The panorama response length is invalid.");
    }
    const declaredLength = rawDeclaredLength === null
      ? null
      : Number(rawDeclaredLength);
    if (declaredLength !== null && declaredLength > MAX_RESPONSE_BYTES) {
      if (response.body && typeof response.body.cancel === "function") {
        try {
          await response.body.cancel();
        } catch (_error) {
          // Preserve the user-facing size error if stream cancellation itself fails.
        }
      }
      throw new Error("The panorama response is larger than 2 MiB.");
    }

    if (response.body && typeof response.body.getReader === "function") {
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8", {fatal: true});
      const chunks = [];
      let receivedBytes = 0;
      let cancelled = false;
      try {
        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          receivedBytes += value.byteLength;
          if (receivedBytes > MAX_RESPONSE_BYTES) {
            cancelled = true;
            try {
              await reader.cancel();
            } catch (_error) {
              // Preserve the user-facing size error if stream cancellation itself fails.
            }
            throw new Error("The panorama response is larger than 2 MiB.");
          }
          chunks.push(decoder.decode(value, {stream: true}));
        }
        chunks.push(decoder.decode());
        return chunks.join("");
      } catch (error) {
        if (!cancelled && typeof reader.cancel === "function") {
          await reader.cancel();
        }
        throw error;
      }
    }

    if (declaredLength === null) {
      throw new Error(
        "The panorama response cannot be bounded because bounded streaming is unavailable."
      );
    }
    const text = await response.text();
    if (responseByteLength(text) > MAX_RESPONSE_BYTES) {
      throw new Error("The panorama response is larger than 2 MiB.");
    }
    return text;
  };

  const loadProjection = async () => {
    const response = await fetch(API_PATH, {headers: {Accept: "application/json"}});
    if (!response.ok) throw new Error("The panorama service returned an error.");
    const text = await readBoundedBody(response);
    const projection = JSON.parse(text);
    if (!projection || projection.schema_version !== "ai_industry_panorama_public.v1") {
      throw new Error("The panorama response format is not supported.");
    }
    return projection;
  };

  const init = async () => {
    try {
      const projection = await loadProjection();
      state.projection = projection;
      state.indexes = buildIndexes(projection);
      renderMetadata(projection);
      populateControls(projection);
      wireControls();
      setViewMode("both");
      renderAll();
      byId("panorama-error").hidden = true;
    } catch (error) {
      setText("panorama-status", "Panorama unavailable.");
      const failure = byId("panorama-error");
      failure.hidden = false;
      failure.textContent = error instanceof Error
        ? error.message
        : "The panorama could not be loaded.";
    }
  };

  window.AIIndustryPanorama = {
    state,
    renderAll,
    safeExternalUrl,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, {once: true});
  } else {
    init();
  }
})();
"""
