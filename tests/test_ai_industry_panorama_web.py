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
    response_ok: bool = True,
    response_body_bytes: int | None = None,
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
  focus() {}
}

const ids = [
  "panorama-app", "panorama-status", "panorama-error", "release-id",
  "taxonomy-version", "evidence-cutoff", "change-summary", "panorama-search",
  "layer-filter", "geography-filter", "time-filter", "lifecycle-filter",
  "evidence-filter", "confidence-filter", "disclosed-only", "hop-depth",
  "reset-panorama", "panorama-graph", "relationship-table-body",
  "entity-drawer", "capability-drawer", "relationship-drawer",
];
const nodes = new Map(ids.map((id) => [id, new ElementStub("div", id)]));
nodes.get("panorama-search").value = "";
nodes.get("hop-depth").value = "2";

global.document = {
  readyState: "complete",
  getElementById(id) { return nodes.get(id) || null; },
  createElement(tagName) { return new ElementStub(tagName); },
  createElementNS(_namespace, tagName) { return new ElementStub(tagName); },
  addEventListener() {},
};
global.window = {location: {href: "https://example.test/ai-industry-panorama"}};
const projection = __PROJECTION__;
const response = {
  ok: __RESPONSE_OK__,
  headers: {get(name) { return name.toLowerCase() === "content-length" ? __CONTENT_LENGTH__ : null; }},
  async text() {
    global.responseTextCalls = (global.responseTextCalls || 0) + 1;
    return __RESPONSE_BODY_BYTES__ == null
      ? JSON.stringify(projection)
      : "x".repeat(__RESPONSE_BODY_BYTES__);
  },
};
global.fetch = async (...args) => {
  global.fetchCalls = (global.fetchCalls || []).concat([args]);
  return response;
};

const source = __SCRIPT__;
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
            .replace("__RESPONSE_BODY_BYTES__", json.dumps(response_body_bytes))
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

    def test_initial_render_uses_only_api_and_keeps_svg_table_ids_equal(self) -> None:
        _run_panorama_script(
            """
assert.equal(global.fetchCalls.length, 1);
assert.equal(global.fetchCalls[0][0], "/api/ai-industry-panorama");
const graphIds = relationshipIds(nodes.get("panorama-graph"));
const tableIds = relationshipIds(nodes.get("relationship-table-body"));
assert.ok(graphIds.length > 0);
assert.deepEqual(graphIds, tableIds);
assert.equal(nodes.get("panorama-error").hidden, true);
assert.equal(nodes.get("release-id").textContent, projection.release.release_id);
assert.equal(nodes.get("taxonomy-version").textContent, projection.release.taxonomy_version);
assert.equal(nodes.get("evidence-cutoff").textContent, projection.release.evidence_cutoff);
assert.match(textTree(nodes.get("change-summary")), /Initial bounded release/);
assert.match(textTree(nodes.get("panorama-graph")), /Demand and capital formation/);
assert.match(textTree(nodes.get("panorama-graph")), /Physical infrastructure/);
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

    def test_keyboard_nodes_and_drawers_expose_entity_capability_and_evidence(self) -> None:
        _run_panorama_script(
            """
const graph = nodes.get("panorama-graph");
const corning = findByAttribute(graph, "data-entity-id", "entity:ENT-ORG-CORNING");
assert.equal(corning.attributes.tabindex, "0");
assert.equal(corning.attributes.role, "button");
trigger(corning, "keydown", {key: "Enter", preventDefault() {}});
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
                "internal_path": "/command?stock=NASDAQ%3AGOOGL",
                "command_hint": "View valuation NASDAQ:GOOGL",
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
  .find((node) => node.attributes.href === "/command?stock=NASDAQ%3AGOOGL");
assert.ok(internalLink);
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
assert.equal(global.attack, undefined);
""",
            projection=projection,
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
assert.equal(global.responseTextCalls, 1);
assert.equal(relationshipIds(nodes.get("panorama-graph")).length, 0);
assert.equal(nodes.get("panorama-error").hidden, false);
assert.match(nodes.get("panorama-error").textContent, /larger than 2 MiB/);
""",
            declared_length=0,
            response_body_bytes=2 * 1024 * 1024 + 1,
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

    def test_script_uses_deterministic_safe_dom_contract(self) -> None:
        script = render_panorama_script()

        self.assertNotIn("innerHTML", script)
        self.assertNotIn("forceSimulation", script)
        self.assertNotIn("eval(", script)
        self.assertIn("textContent", script)
        self.assertIn("createElementNS", script)
        self.assertIn('"marker-end"', script)
        self.assertIn("MAX_RESPONSE_BYTES", script)
        self.assertIn('rel", "noopener noreferrer"', script)
        self.assertEqual(1, script.count('"/api/ai-industry-panorama"'))


if __name__ == "__main__":
    unittest.main()
