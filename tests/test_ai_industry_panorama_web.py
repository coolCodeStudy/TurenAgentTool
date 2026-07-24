from __future__ import annotations

import copy
import json
import shutil
import subprocess
import unittest

from investment_knowledge_mcp.ai_industry_panorama.release import (
    build_public_projection,
    load_release,
)
from investment_knowledge_mcp.ai_industry_panorama.web import (
    render_panorama_html,
    render_panorama_script,
)


def _run_panorama_script(
    assertions: str,
    *,
    projection: dict[str, object] | None = None,
    declared_length: int | None = None,
    declared_length_present: bool = True,
    response_ok: bool = True,
    response_body_bytes: int | None = None,
    streaming: bool = True,
    stream_chunk_bytes: int = 262_144,
) -> None:
    node = shutil.which("node")
    if node is None:
        raise AssertionError("Node.js is required to verify panorama browser behavior")

    projection = projection or build_public_projection(load_release())
    encoded_projection = json.dumps(projection)
    content_length = (
        len(encoded_projection.encode("utf-8"))
        if declared_length is None
        else declared_length
    )
    harness = r"""
const assert = require("node:assert/strict");

class ElementStub {
  constructor(tagName, id = "") {
    this.tagName = tagName;
    this.id = id;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.listeners = {};
    this.textContent = "";
    this.value = "";
    this.checked = false;
    this.hidden = false;
    this.className = "";
  }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = [...children]; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name.startsWith("data-")) {
      const key = name.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase());
      this.dataset[key] = String(value);
    }
  }
  removeAttribute(name) { delete this.attributes[name]; }
  focus() { document.activeElement = this; }
}

const ids = [
  "panorama-app", "panorama-status", "panorama-error", "release-id",
  "taxonomy-version", "evidence-cutoff", "change-summary", "panorama-search",
  "layer-filter", "geography-filter", "time-filter", "lifecycle-filter",
  "evidence-filter", "confidence-filter", "disclosed-only", "hop-depth",
  "reset-panorama", "panorama-graph", "relationship-table-body",
  "entity-drawer", "capability-drawer", "relationship-drawer",
  "graph-view", "table-view", "both-view", "graph-panel", "table-panel",
  "panorama-graph-scroll",
];
const nodes = new Map(ids.map((id) => [id, new ElementStub("div", id)]));
nodes.get("panorama-search").value = "";
nodes.get("hop-depth").value = "2";

global.document = {
  readyState: "complete",
  activeElement: null,
  getElementById(id) { return nodes.get(id) || null; },
  createElement(tagName) { return new ElementStub(tagName); },
  createElementNS(_namespace, tagName) { return new ElementStub(tagName); },
  addEventListener() {},
};
global.window = {location: {href: "https://example.test/ai-industry-panorama"}};
const projection = __PROJECTION__;
const responseText = __RESPONSE_BODY_BYTES__ == null
  ? JSON.stringify(projection)
  : "x".repeat(__RESPONSE_BODY_BYTES__);
const responseBytes = new TextEncoder().encode(responseText);
let streamOffset = 0;
const streamReader = {
  async read() {
    global.streamReadCalls = (global.streamReadCalls || 0) + 1;
    if (streamOffset >= responseBytes.byteLength) return {done: true};
    const end = Math.min(streamOffset + __STREAM_CHUNK_BYTES__, responseBytes.byteLength);
    const value = responseBytes.slice(streamOffset, end);
    streamOffset = end;
    return {done: false, value};
  },
  async cancel() {
    global.streamCancelCalls = (global.streamCancelCalls || 0) + 1;
  },
};
const response = {
  ok: __RESPONSE_OK__,
  headers: {get(name) {
    return name.toLowerCase() === "content-length" && __DECLARED_LENGTH_PRESENT__
      ? __CONTENT_LENGTH__
      : null;
  }},
  body: __STREAMING__ ? {
    getReader() { return streamReader; },
    async cancel() {
      global.streamCancelCalls = (global.streamCancelCalls || 0) + 1;
    },
  } : null,
  async text() {
    global.responseTextCalls = (global.responseTextCalls || 0) + 1;
    return responseText;
  },
};
global.fetch = async (...args) => {
  global.fetchCalls = (global.fetchCalls || []).concat([args]);
  return response;
};

const source = __SCRIPT__;
const nativeJsonParse = JSON.parse.bind(JSON);
JSON.parse = (...args) => {
  global.jsonParseCalls = (global.jsonParseCalls || 0) + 1;
  return nativeJsonParse(...args);
};
eval(source);

const flush = () => new Promise((resolve) => setImmediate(resolve));
const descendants = (root) => [
  root,
  ...root.children.flatMap((child) => descendants(child)),
];
const textTree = (root) => [root.textContent, ...root.children.map(textTree)].join(" ");
const findByAttribute = (root, name, value) => descendants(root)
  .find((node) => node.attributes[name] === value);
const relationshipIds = (root) => descendants(root)
  .map((node) => node.attributes["data-relationship-id"])
  .filter(Boolean)
  .sort();
const entityIds = (root) => descendants(root)
  .map((node) => node.attributes["data-entity-id"])
  .filter(Boolean)
  .sort();
const trigger = (node, type, details = {}) => {
  assert.equal(typeof node.listeners[type], "function", `${node.id || node.tagName} lacks ${type}`);
  return node.listeners[type]({target: node, currentTarget: node, ...details});
};

(async () => {
  await flush();
  await flush();
  __ASSERTIONS__
  process.stdout.write(JSON.stringify({ok: true}));
})().catch((error) => {
  process.stderr.write(String(error && error.stack ? error.stack : error));
  process.exitCode = 1;
});
"""
    completed = subprocess.run(
        [
            node,
            "-e",
            harness.replace("__PROJECTION__", encoded_projection)
            .replace("__SCRIPT__", json.dumps(render_panorama_script()))
            .replace("__RESPONSE_OK__", json.dumps(response_ok))
            .replace("__CONTENT_LENGTH__", json.dumps(str(content_length)))
            .replace(
                "__DECLARED_LENGTH_PRESENT__",
                json.dumps(declared_length_present),
            )
            .replace("__RESPONSE_BODY_BYTES__", json.dumps(response_body_bytes))
            .replace("__STREAMING__", json.dumps(streaming))
            .replace("__STREAM_CHUNK_BYTES__", json.dumps(stream_chunk_bytes))
            .replace("__ASSERTIONS__", assertions),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "Panorama browser behavior check failed with status "
            f"{completed.returncode}: {completed.stderr.strip()}"
        )
    self_result = json.loads(completed.stdout)
    if self_result != {"ok": True}:
        raise AssertionError("Panorama browser behavior returned an invalid status")


class PanoramaWebTests(unittest.TestCase):
    def test_page_exposes_equivalent_graph_table_controls_and_drawers(self) -> None:
        html = render_panorama_html()

        for fragment in (
            'data-experience-ready="true"',
            'id="panorama-graph"',
            'id="relationship-table"',
            'id="panorama-search"',
            'id="layer-filter"',
            'id="geography-filter"',
            'id="time-filter"',
            'id="lifecycle-filter"',
            'id="evidence-filter"',
            'id="confidence-filter"',
            'id="disclosed-only"',
            'id="hop-depth"',
            'id="graph-view"',
            'id="table-view"',
            'id="both-view"',
            'id="graph-panel"',
            'id="table-panel"',
            'id="panorama-graph-scroll"',
            'id="entity-drawer"',
            'id="capability-drawer"',
            'aria-label="Relationship evidence"',
            'id="panorama-status"',
            'id="panorama-error"',
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)
        self.assertIn("AI Industry Panorama", html)
        self.assertIn("/assets/ai-industry-panorama.js", html)
        self.assertIn('aria-label="主导航"', html)
        self.assertIn("--experience-canvas", html)
        self.assertIn("Loading panorama", html)
        self.assertIn("<th>Evidence</th>", html)
        self.assertIn('role="group" aria-label="Panorama view"', html)
        self.assertIn('aria-pressed="true"', html)
        self.assertIn('class="panorama-graph-scroll"', html)
        self.assertIn("overflow-x: auto", html)
        self.assertIn("grid-template-columns: 1fr", html)

    def test_initial_render_uses_only_api_and_keeps_svg_table_ids_equal(self) -> None:
        _run_panorama_script(
            """
assert.equal(global.fetchCalls.length, 1);
assert.equal(global.fetchCalls[0][0], "/api/ai-industry-panorama");
const graphIds = relationshipIds(nodes.get("panorama-graph"));
const tableIds = relationshipIds(nodes.get("relationship-table-body"));
assert.deepEqual(graphIds, [
  "relationship:REL-AIP-0002",
  "relationship:REL-AIP-0004",
  "relationship:REL-AIP-0006",
  "relationship:REL-AIP-0008",
  "relationship:REL-AIP-0009",
  "relationship:REL-AIP-0010",
  "relationship:REL-AIP-0015",
  "relationship:REL-AIP-0016",
  "relationship:REL-AIP-0017",
  "relationship:REL-AIP-0021",
  "relationship:REL-AIP-0026",
]);
assert.deepEqual(graphIds, tableIds);
assert.deepEqual(
  entityIds(nodes.get("panorama-graph")).filter((id) => id.includes("ENT-ORG-")).filter(
    (id) => ["ALPHABET", "AMAZON", "ANTHROPIC", "META", "MICROSOFT", "OPENAI"]
      .some((anchor) => id.endsWith(anchor))
  ),
  [
    "entity:ENT-ORG-ALPHABET",
    "entity:ENT-ORG-AMAZON",
    "entity:ENT-ORG-ANTHROPIC",
    "entity:ENT-ORG-META",
    "entity:ENT-ORG-MICROSOFT",
    "entity:ENT-ORG-OPENAI",
  ],
);
assert.equal(window.AIIndustryPanorama.state.mode, "curated");
assert.match(nodes.get("panorama-status").textContent, /Curated start/);
assert.equal(nodes.get("panorama-error").hidden, true);
assert.equal(nodes.get("release-id").textContent, projection.release.release_id);
assert.equal(nodes.get("taxonomy-version").textContent, projection.release.taxonomy_version);
assert.equal(nodes.get("evidence-cutoff").textContent, projection.release.evidence_cutoff);
assert.match(textTree(nodes.get("change-summary")), /Initial bounded release/);
assert.match(textTree(nodes.get("panorama-graph")), /Demand and capital formation/);
assert.match(textTree(nodes.get("panorama-graph")), /Physical infrastructure/);
"""
        )

    def test_valid_period_filter_uses_overlap_and_explicit_unknown(self) -> None:
        _run_panorama_script(
            """
trigger(nodes.get("reset-panorama"), "click");
const periodValues = nodes.get("time-filter").children.map((option) => option.value);
assert.ok(periodValues.includes("2026-2027"));
assert.ok(periodValues.includes("unknown"));

nodes.get("time-filter").value = "2026-2027";
trigger(nodes.get("time-filter"), "change");
const excluded = new Set([
  "relationship:REL-AIP-0002",
  "relationship:REL-AIP-0003",
  "relationship:REL-AIP-0012",
  "relationship:REL-AIP-0013",
  "relationship:REL-AIP-0044",
  "relationship:REL-AIP-0045",
]);
const expectedPeriod = projection.relationships
  .map((item) => item.relationship_id)
  .filter((id) => !excluded.has(id))
  .sort();
assert.deepEqual(relationshipIds(nodes.get("panorama-graph")), expectedPeriod);
assert.deepEqual(
  relationshipIds(nodes.get("relationship-table-body")),
  expectedPeriod,
);
assert.ok(expectedPeriod.includes("relationship:REL-AIP-0015"));
assert.ok(expectedPeriod.includes("relationship:REL-AIP-0028"));

nodes.get("time-filter").value = "unknown";
trigger(nodes.get("time-filter"), "change");
assert.deepEqual(relationshipIds(nodes.get("panorama-graph")), [
  "relationship:REL-AIP-0044",
  "relationship:REL-AIP-0045",
]);
"""
        )

    def test_search_filters_alias_project_company_and_capability_from_one_set(self) -> None:
        _run_panorama_script(
            """
const initialCount = relationshipIds(nodes.get("panorama-graph")).length;
for (const query of ["Google parent", "Stargate I", "Corning", "Advanced semiconductor packaging"]) {
  nodes.get("panorama-search").value = query;
  trigger(nodes.get("panorama-search"), "input");
  const graphIds = relationshipIds(nodes.get("panorama-graph"));
  const tableIds = relationshipIds(nodes.get("relationship-table-body"));
  assert.ok(graphIds.length > 0, query);
  assert.ok(graphIds.length < initialCount, query);
  assert.deepEqual(graphIds, tableIds, query);
}
"""
        )

    def test_graph_table_view_switch_preserves_shared_state_and_focus(self) -> None:
        _run_panorama_script(
            """
trigger(nodes.get("reset-panorama"), "click");
const graph = nodes.get("panorama-graph");
const microsoft = findByAttribute(graph, "data-entity-id", "entity:ENT-ORG-MICROSOFT");
trigger(microsoft, "click");
const focusedId = window.AIIndustryPanorama.state.focusEntityId;
const sharedIds = relationshipIds(graph);

trigger(nodes.get("graph-view"), "click");
assert.equal(nodes.get("graph-panel").hidden, false);
assert.equal(nodes.get("table-panel").hidden, true);
assert.equal(nodes.get("graph-view").attributes["aria-pressed"], "true");
assert.equal(nodes.get("table-view").attributes["aria-pressed"], "false");

trigger(nodes.get("table-view"), "click");
assert.equal(nodes.get("graph-panel").hidden, true);
assert.equal(nodes.get("table-panel").hidden, false);
assert.equal(nodes.get("table-view").attributes["aria-pressed"], "true");
assert.deepEqual(relationshipIds(nodes.get("relationship-table-body")), sharedIds);
assert.equal(window.AIIndustryPanorama.state.focusEntityId, focusedId);

trigger(nodes.get("both-view"), "click");
assert.equal(nodes.get("graph-panel").hidden, false);
assert.equal(nodes.get("table-panel").hidden, false);
assert.equal(nodes.get("both-view").attributes["aria-pressed"], "true");
assert.equal(window.AIIndustryPanorama.state.focusEntityId, focusedId);
"""
        )

    def test_one_and_two_hop_focus_and_all_filters_keep_graph_table_equal(self) -> None:
        _run_panorama_script(
            """
const graph = nodes.get("panorama-graph");
nodes.get("panorama-search").value = "Microsoft";
trigger(nodes.get("panorama-search"), "input");
const searchCount = relationshipIds(graph).length;
const microsoft = findByAttribute(graph, "data-entity-id", "entity:ENT-ORG-MICROSOFT");
assert.ok(microsoft);
trigger(microsoft, "click");
assert.equal(window.AIIndustryPanorama.state.search, "");
assert.equal(nodes.get("panorama-search").value, "");
assert.ok(relationshipIds(graph).length > searchCount);
nodes.get("hop-depth").value = "1";
trigger(nodes.get("hop-depth"), "change");
const oneHop = relationshipIds(graph);
nodes.get("hop-depth").value = "2";
trigger(nodes.get("hop-depth"), "change");
const twoHop = relationshipIds(graph);
assert.ok(oneHop.length > 0);
assert.ok(twoHop.length > oneHop.length);
nodes.get("layer-filter").value = "layer-02";
trigger(nodes.get("layer-filter"), "change");
assert.equal(
  window.AIIndustryPanorama.state.focusEntityId,
  "entity:ENT-ORG-MICROSOFT",
);
assert.ok(findByAttribute(graph, "data-entity-id", "entity:ENT-ORG-MICROSOFT"));
assert.deepEqual(
  relationshipIds(graph),
  relationshipIds(nodes.get("relationship-table-body")),
);

const filters = [
  ["layer-filter", "layer-02"],
  ["geography-filter", "geography:us"],
  ["time-filter", "day"],
  ["lifecycle-filter", "operating"],
  ["evidence-filter", "T2"],
  ["confidence-filter", "medium"],
];
for (const [id, value] of filters) {
  trigger(nodes.get("reset-panorama"), "click");
  nodes.get(id).value = value;
  trigger(nodes.get(id), "change");
  assert.deepEqual(
    relationshipIds(graph),
    relationshipIds(nodes.get("relationship-table-body")),
    id,
  );
}
trigger(nodes.get("reset-panorama"), "click");
nodes.get("disclosed-only").checked = true;
trigger(nodes.get("disclosed-only"), "change");
assert.ok(window.AIIndustryPanorama.state.visibleRelationships.every(
  (relationship) => relationship.assertion_kind !== "inferred_exposure"
));
assert.deepEqual(
  relationshipIds(graph),
  relationshipIds(nodes.get("relationship-table-body")),
);
trigger(nodes.get("reset-panorama"), "click");
assert.equal(window.AIIndustryPanorama.state.focusEntityId, null);
assert.equal(window.AIIndustryPanorama.state.search, "");
assert.equal(window.AIIndustryPanorama.state.filters.disclosedOnly, false);
assert.equal(
  window.AIIndustryPanorama.state.visibleRelationships.length,
  projection.relationships.length,
);
"""
        )

    def test_disclosed_only_filters_before_focus_bfs_and_uses_allowlist(self) -> None:
        _run_panorama_script(
            """
trigger(nodes.get("reset-panorama"), "click");
const graph = nodes.get("panorama-graph");
const meta = findByAttribute(graph, "data-entity-id", "entity:ENT-ORG-META");
trigger(meta, "click");
nodes.get("hop-depth").value = "2";
trigger(nodes.get("hop-depth"), "change");
nodes.get("disclosed-only").checked = true;
trigger(nodes.get("disclosed-only"), "change");
const visible = relationshipIds(graph);
assert.ok(visible.includes("relationship:REL-AIP-0045"));
for (const hidden of [
  "relationship:REL-AIP-0011",
  "relationship:REL-AIP-0042",
  "relationship:REL-AIP-0043",
]) assert.ok(!visible.includes(hidden), hidden);
"""
        )

        hypothesis_projection = copy.deepcopy(build_public_projection(load_release()))
        hypothesis = next(
            item
            for item in hypothesis_projection["relationships"]
            if item["relationship_id"] == "relationship:REL-AIP-0004"
        )
        hypothesis["assertion_kind"] = "user_hypothesis"
        _run_panorama_script(
            """
trigger(nodes.get("reset-panorama"), "click");
nodes.get("disclosed-only").checked = true;
trigger(nodes.get("disclosed-only"), "change");
assert.ok(!relationshipIds(nodes.get("panorama-graph")).includes(
  "relationship:REL-AIP-0004"
));
assert.ok(window.AIIndustryPanorama.state.visibleRelationships.every(
  (item) => ["disclosed_fact", "company_guidance", "management_claim"]
    .includes(item.assertion_kind)
));
""",
            projection=hypothesis_projection,
        )

    def test_owner_hypothesis_is_distinct_from_disclosure_and_inference(self) -> None:
        projection = copy.deepcopy(build_public_projection(load_release()))
        hypothesis = next(
            item
            for item in projection["relationships"]
            if item["relationship_id"] == "relationship:REL-AIP-0004"
        )
        hypothesis["assertion_kind"] = "user_hypothesis"
        hypothesis["text"] = (
            '<script>global.ownerAttack=1</script> OWNER-HYPOTHESIS-TEXT'
        )
        hypothesis["limitations"] = "OWNER-HYPOTHESIS-LIMITATIONS"

        html = render_panorama_html()
        self.assertIn("Owner hypothesis", html)
        self.assertIn("user-supplied thesis, not disclosed evidence", html)

        _run_panorama_script(
            """
trigger(nodes.get("reset-panorama"), "click");
const graph = nodes.get("panorama-graph");
const hypothesisEdge = findByAttribute(
  graph,
  "data-relationship-id",
  "relationship:REL-AIP-0004",
);
const inferenceEdge = findByAttribute(
  graph,
  "data-relationship-id",
  "relationship:REL-AIP-0011",
);
const disclosedEdge = findByAttribute(
  graph,
  "data-relationship-id",
  "relationship:REL-AIP-0002",
);
assert.equal(hypothesisEdge.attributes["data-assertion-kind"], "user_hypothesis");
assert.equal(inferenceEdge.attributes["data-assertion-kind"], "inferred_exposure");
assert.equal(disclosedEdge.attributes["data-assertion-kind"], "disclosed_fact");
const hypothesisLine = descendants(hypothesisEdge).find((node) => node.tagName === "line");
const inferenceLine = descendants(inferenceEdge).find((node) => node.tagName === "line");
const disclosedLine = descendants(disclosedEdge).find((node) => node.tagName === "line");
assert.notEqual(hypothesisLine.attributes.stroke, inferenceLine.attributes.stroke);
assert.notEqual(hypothesisLine.attributes.stroke, disclosedLine.attributes.stroke);
assert.notEqual(
  hypothesisLine.attributes["stroke-dasharray"],
  inferenceLine.attributes["stroke-dasharray"],
);
assert.notEqual(
  hypothesisLine.attributes["stroke-dasharray"],
  disclosedLine.attributes["stroke-dasharray"],
);

const alphabet = findByAttribute(
  graph,
  "data-entity-id",
  "entity:ENT-ORG-ALPHABET",
);
trigger(alphabet, "click");
const drawer = nodes.get("entity-drawer");
const sectionByHeading = (heading) => drawer.children.find(
  (section) => section.children.some(
    (node) => node.tagName === "h3" && node.textContent === heading
  )
);
const disclosed = sectionByHeading("Disclosed relationships");
const datedFacts = sectionByHeading("Dated facts and guidance");
const ownerHypotheses = sectionByHeading("Owner hypotheses");
assert.ok(disclosed);
assert.ok(datedFacts);
assert.ok(ownerHypotheses);
assert.doesNotMatch(textTree(disclosed), /OWNER-HYPOTHESIS-TEXT/);
assert.doesNotMatch(textTree(datedFacts), /OWNER-HYPOTHESIS-TEXT/);
assert.match(textTree(ownerHypotheses), /OWNER-HYPOTHESIS-TEXT/);
assert.match(textTree(ownerHypotheses), /OWNER-HYPOTHESIS-LIMITATIONS/);
assert.equal(global.ownerAttack, undefined);

trigger(nodes.get("reset-panorama"), "click");
nodes.get("disclosed-only").checked = true;
trigger(nodes.get("disclosed-only"), "change");
const graphIds = relationshipIds(graph);
const tableIds = relationshipIds(nodes.get("relationship-table-body"));
assert.deepEqual(graphIds, tableIds);
assert.ok(!graphIds.includes("relationship:REL-AIP-0004"));
assert.ok(window.AIIndustryPanorama.state.visibleRelationships.every(
  (item) => ["disclosed_fact", "company_guidance", "management_claim"]
    .includes(item.assertion_kind)
));
""",
            projection=projection,
        )

    def test_keyboard_nodes_and_drawers_expose_entity_capability_and_evidence(self) -> None:
        _run_panorama_script(
            """
const graph = nodes.get("panorama-graph");
const corning = findByAttribute(graph, "data-entity-id", "entity:ENT-ORG-CORNING");
assert.equal(corning.attributes.tabindex, "0");
assert.equal(corning.attributes.role, "button");
trigger(corning, "keydown", {key: "Enter", preventDefault() {}});
assert.equal(document.activeElement, nodes.get("entity-drawer"));
assert.equal(nodes.get("entity-drawer").attributes.tabindex, "-1");
assert.match(nodes.get("panorama-status").textContent, /Entity details opened/);
const entityText = textTree(nodes.get("entity-drawer"));
assert.match(entityText, /Corning Incorporated/);
assert.match(entityText, /Aliases/);
assert.match(entityText, /Disclosed relationships/);
assert.match(entityText, /Inferred exposures/);
assert.match(entityText, /Coverage gaps/);
assert.match(entityText, /Freshness/);
assert.match(entityText, /Latest evidence date/);

trigger(nodes.get("reset-panorama"), "click");
const capability = findByAttribute(
  graph,
  "data-entity-id",
  "entity:ENT-CAP-ADVANCED-PACKAGING",
);
trigger(capability, "click");
assert.equal(document.activeElement, nodes.get("capability-drawer"));
assert.match(nodes.get("panorama-status").textContent, /Capability details opened/);
const capabilityText = textTree(nodes.get("capability-drawer"));
assert.match(capabilityText, /Advanced semiconductor packaging/);
assert.match(capabilityText, /Definition/);
assert.match(capabilityText, /Standards context/);
assert.match(capabilityText, /Upstream roles/);
assert.match(capabilityText, /Downstream roles/);
assert.match(capabilityText, /Coverage gaps/);

trigger(nodes.get("reset-panorama"), "click");
const relationship = findByAttribute(
  graph,
  "data-relationship-id",
  "relationship:REL-AIP-0017",
);
trigger(relationship, "click");
assert.equal(document.activeElement, nodes.get("relationship-drawer"));
assert.match(nodes.get("panorama-status").textContent, /Relationship evidence opened/);
const evidenceText = textTree(nodes.get("relationship-drawer"));
for (const text of [
  "Amazon.com, Inc.", "Corning Incorporated", "buys_from",
  "disclosed_fact", "committed", "Confidence inputs", "Limitations",
  "Corning Incorporated", "Publication", "Retrieved", "Locator",
]) {
  assert.match(evidenceText, new RegExp(text));
}
assert.match(evidenceText, /Stable source locator/);
const sourceLink = descendants(nodes.get("relationship-drawer"))
  .find((node) => node.tagName === "a");
assert.ok(sourceLink);
assert.match(sourceLink.attributes.href, /^https:/);
assert.equal(sourceLink.attributes.rel, "noopener noreferrer");
assert.equal(sourceLink.attributes.target, "_blank");

trigger(nodes.get("reset-panorama"), "click");
const inferred = findByAttribute(
  graph,
  "data-relationship-id",
  "relationship:REL-AIP-0011",
);
trigger(inferred, "click");
const inferenceText = textTree(nodes.get("relationship-drawer"));
assert.match(inferenceText, /Inference derivation/);
assert.match(inferenceText, /assertion:AST-AIP-0010/);
assert.match(inferenceText, /assertion:AST-AIP-0045/);
assert.match(inferenceText, /Meta Investor Relations/);
assert.match(inferenceText, /Meta Reports First Quarter 2026 Results/);
assert.match(inferenceText, /Open Compute Project Foundation/);
assert.match(inferenceText, /Open Data Centers for AI/);
assert.match(inferenceText, /No site, supplier, megawatt capacity/);
assert.match(inferenceText, /Page is undated and generic/);
assert.deepEqual(
  descendants(nodes.get("relationship-drawer"))
    .map((node) => node.attributes["data-premise-assertion-id"])
    .filter(Boolean)
    .sort(),
  ["assertion:AST-AIP-0010", "assertion:AST-AIP-0045"],
);
const premiseLinks = descendants(nodes.get("relationship-drawer"))
  .filter((node) => node.attributes["data-premise-source-link"] === "true");
assert.equal(premiseLinks.length, 2);
assert.ok(premiseLinks.every(
  (node) => node.attributes.rel === "noopener noreferrer"
    && node.attributes.target === "_blank"
    && String(node.attributes.href).startsWith("https:")
));
"""
        )

    def test_hostile_projection_is_text_only_and_unsafe_links_never_execute(self) -> None:
        projection = copy.deepcopy(build_public_projection(load_release()))
        hostile = '<img src=x onerror="global.attack=1"><script>global.attack=2</script>'
        projection["entities"][0]["label"] = hostile
        projection["entities"][0]["aliases"] = [hostile]
        projection["entities"][0]["research_links"] = [
            {
                "kind": "research",
                "label": hostile,
                "canonical_stock_id": "NASDAQ:GOOGL",
                "internal_path": "javascript:global.attack=3",
                "command_hint": hostile,
            },
            {
                "kind": "valuation",
                "label": "Open reviewed valuation",
                "canonical_stock_id": "NASDAQ:GOOGL",
                "internal_path": "/command",
                "command_hint": "View valuation NASDAQ:GOOGL",
            },
            {
                "kind": "research",
                "label": "Unsafe trailing command path",
                "canonical_stock_id": "NASDAQ:GOOGL",
                "internal_path": "/command?stock=NASDAQ%3AGOOGL",
                "command_hint": "Do not execute",
            }
        ]
        first_evidence_id = projection["relationships"][0]["evidence_ids"][0]
        evidence = next(
            item
            for item in projection["evidence"]
            if item["evidence_id"] == first_evidence_id
        )
        evidence["bounded_excerpt"] = hostile
        source = next(
            item
            for item in projection["sources"]
            if item["source_id"] == evidence["source_id"]
        )
        source["url"] = "javascript:global.attack=4"
        inferred = next(
            item
            for item in projection["relationships"]
            if item["relationship_id"] == "relationship:REL-AIP-0011"
        )
        for premise_id in inferred["premise_assertion_ids"]:
            premise = next(
                item
                for item in projection["relationships"]
                if item["assertion_id"] == premise_id
            )
            premise["text"] = hostile
            premise["limitations"] = hostile
            for premise_evidence_id in premise["evidence_ids"]:
                premise_evidence = next(
                    item
                    for item in projection["evidence"]
                    if item["evidence_id"] == premise_evidence_id
                )
                premise_evidence["bounded_excerpt"] = hostile
                premise_source = next(
                    item
                    for item in projection["sources"]
                    if item["source_id"] == premise_evidence["source_id"]
                )
                premise_source["document_title"] = hostile
                premise_source["publisher"] = hostile
                premise_source["url"] = "javascript:global.attack=5"

        _run_panorama_script(
            """
assert.equal(global.attack, undefined);
const graph = nodes.get("panorama-graph");
const hostileEntity = findByAttribute(graph, "data-entity-id", "entity:ENT-ORG-ALPHABET");
trigger(hostileEntity, "click");
assert.match(textTree(nodes.get("entity-drawer")), /global.attack=1/);
assert.equal(
  descendants(nodes.get("entity-drawer")).some(
    (node) => String(node.attributes.href || "").startsWith("javascript:")
  ),
  false,
);
const internalLink = descendants(nodes.get("entity-drawer"))
  .find((node) => node.attributes.href === "/command");
assert.ok(internalLink);
assert.deepEqual(
  descendants(nodes.get("entity-drawer"))
    .map((node) => node.attributes.href)
    .filter(Boolean),
  ["/command"],
);
assert.match(textTree(nodes.get("entity-drawer")), /NASDAQ:GOOGL/);
assert.match(textTree(nodes.get("entity-drawer")), /not executed/);
assert.equal(global.fetchCalls.length, 1);
const hostileRelationship = findByAttribute(
  graph,
  "data-relationship-id",
  "relationship:REL-AIP-0001",
);
trigger(hostileRelationship, "click");
assert.match(textTree(nodes.get("relationship-drawer")), /global.attack=2/);
assert.equal(
  descendants(nodes.get("relationship-drawer")).some(
    (node) => String(node.attributes.href || "").startsWith("javascript:")
  ),
  false,
);
trigger(nodes.get("reset-panorama"), "click");
const hostileInference = findByAttribute(
  graph,
  "data-relationship-id",
  "relationship:REL-AIP-0011",
);
trigger(hostileInference, "click");
assert.match(textTree(nodes.get("relationship-drawer")), /global.attack=2/);
assert.equal(
  descendants(nodes.get("relationship-drawer")).some(
    (node) => String(node.attributes.href || "").startsWith("javascript:")
  ),
  false,
);
assert.equal(global.attack, undefined);
""",
            projection=projection,
        )

    def test_client_url_safety_matches_backend_sensitive_query_contract(self) -> None:
        _run_panorama_script(
            """
for (const name of [
  "token", "api_key", "apikey", "access_token", "auth", "authorization",
  "client_secret", "password", "private_key", "secret", "signature", "sig",
  "key", "credential",
]) {
  assert.equal(
    window.AIIndustryPanorama.safeExternalUrl(`https://example.test/source?${name}=x`),
    null,
    name,
  );
  assert.equal(
    window.AIIndustryPanorama.safeExternalUrl(
      `https://example.test/source?${name.toUpperCase()}=x`
    ),
    null,
    `${name} uppercase`,
  );
}
assert.equal(
  window.AIIndustryPanorama.safeExternalUrl(
    "https://example.test/source?market=key"
  ),
  "https://example.test/source?market=key",
);
"""
        )

    def test_oversized_response_is_rejected_before_body_parse_or_render(self) -> None:
        _run_panorama_script(
            """
assert.equal(global.responseTextCalls || 0, 0);
assert.equal(relationshipIds(nodes.get("panorama-graph")).length, 0);
assert.equal(relationshipIds(nodes.get("relationship-table-body")).length, 0);
assert.equal(nodes.get("panorama-error").hidden, false);
assert.match(nodes.get("panorama-error").textContent, /larger than 2 MiB/);
""",
            declared_length=2 * 1024 * 1024 + 1,
        )

    def test_actual_oversized_body_and_http_failure_are_readable_and_do_not_render(
        self,
    ) -> None:
        _run_panorama_script(
            """
assert.equal(global.responseTextCalls || 0, 0);
assert.equal(global.streamReadCalls, 3);
assert.equal(global.streamCancelCalls, 1);
assert.equal(global.jsonParseCalls || 0, 0);
assert.equal(relationshipIds(nodes.get("panorama-graph")).length, 0);
assert.equal(nodes.get("panorama-error").hidden, false);
assert.match(nodes.get("panorama-error").textContent, /larger than 2 MiB/);
""",
            declared_length=0,
            response_body_bytes=2 * 1024 * 1024 + 1,
            stream_chunk_bytes=700_000,
        )
        _run_panorama_script(
            """
assert.equal(global.responseTextCalls || 0, 0);
assert.equal(relationshipIds(nodes.get("panorama-graph")).length, 0);
assert.equal(nodes.get("panorama-status").textContent, "Panorama unavailable.");
assert.equal(nodes.get("panorama-error").hidden, false);
assert.match(nodes.get("panorama-error").textContent, /service returned an error/);
""",
            response_ok=False,
        )

    def test_stream_fallback_requires_bounded_content_length(self) -> None:
        _run_panorama_script(
            """
assert.equal(global.responseTextCalls || 0, 0);
assert.equal(global.jsonParseCalls || 0, 0);
assert.equal(relationshipIds(nodes.get("panorama-graph")).length, 0);
assert.equal(nodes.get("panorama-error").hidden, false);
assert.match(nodes.get("panorama-error").textContent, /bounded streaming is unavailable/);
""",
            streaming=False,
            declared_length_present=False,
        )
        _run_panorama_script(
            """
assert.equal(global.responseTextCalls, 1);
assert.equal(global.jsonParseCalls, 1);
assert.ok(relationshipIds(nodes.get("panorama-graph")).length > 0);
assert.equal(nodes.get("panorama-error").hidden, true);
""",
            streaming=False,
            declared_length_present=True,
        )

    def test_script_uses_deterministic_safe_dom_contract(self) -> None:
        script = render_panorama_script()

        self.assertNotIn("innerHTML", script)
        self.assertNotIn("forceSimulation", script)
        self.assertNotIn('setAttribute("viewBox"', script)
        self.assertNotIn("eval(", script)
        self.assertNotIn("localeCompare", script)
        self.assertNotIn("toLocaleLowerCase", script)
        self.assertIn("textContent", script)
        self.assertIn("createElementNS", script)
        self.assertIn("getReader", script)
        self.assertIn("TextDecoder", script)
        self.assertIn("cancel", script)
        self.assertIn('setAttribute("width", "1460")', script)
        self.assertIn('setAttribute("height"', script)
        self.assertIn('"marker-end"', script)
        self.assertIn("MAX_RESPONSE_BYTES", script)
        self.assertIn('rel", "noopener noreferrer"', script)
        self.assertEqual(1, script.count('"/api/ai-industry-panorama"'))


if __name__ == "__main__":
    unittest.main()
