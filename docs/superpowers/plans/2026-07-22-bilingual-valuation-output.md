# Bilingual Stock Valuation Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Make Stock Valuation create/latest cards and the valuation method library Chinese-first while preserving the exact canonical English Markdown at the bottom, without changing artifacts, access boundaries, or unrelated surfaces.

**Architecture:** Keep `stock_valuation_packet.v1` and `build_valuation_artifact_evidence()` unchanged. Split the existing valuation renderers into canonical English line builders and a deterministic valuation-only presentation composer that maps controlled English labels/copy to Chinese while visibly falling back to original English for unknown dynamic text. The router continues to call the public renderers, so no gateway or Workbench access code changes are needed.

**Tech Stack:** Python 3, `unittest`, existing `investment_knowledge_mcp.stock_valuation` pure functions, command-router fixtures, repository-native delivery audits, GitHub serialized quick deploy.

## Global Constraints

- Chinese presentation is first; the exact canonical English body follows under `## English original (原文)`.
- The English body must be byte-for-byte identical to the canonical renderer output for the same validated projection.
- Preserve symbols, market-qualified targets, source/provider IDs, fact IDs, numbers, units, currencies, dates, timestamps, URLs, formula names, and input references verbatim.
- Unknown/free-form English text must stay visible in the Chinese section with an explicit original/fallback marker.
- `stock_valuation_packet.v1`, bounded evidence JSON, artifact persistence, and no-write safety contracts remain unchanged.
- No LLM, translation service, locale negotiation, auth, ingress, Compose, public-port, Weekly, Daily, decision-card, or messaging changes.
- Do not expose or request token values. The existing protected acceptance fixture/session blocker remains separate.
- Use TDD: each production change is preceded by a focused failing test and followed by the focused and preservation suites.

---

### Task 1: Add failing renderer contract tests

**Files:**
- Modify: `tests/test_stock_valuation.py` near the existing renderer and method-library tests.
- Modify: `tests/test_command_workbench.py` only if a router-level response assertion cannot be kept in `tests/test_stock_valuation.py`.

**Interfaces:**
- Consumes existing `render_valuation_card(packet)`, `render_valuation_methods()`, `build_valuation_artifact()`, and `command_router.handle_command()`.
- Produces executable acceptance tests for the bilingual presentation contract.

- [ ] **Step 1: Add a failing card parity test.**

Add a test that builds the existing complete fixture packet, calls `render_valuation_card(packet)`, and asserts:

```python
def test_card_is_chinese_first_with_exact_english_original(self) -> None:
    packet = self._build(snapshot=self._snapshot())
    rendered = render_valuation_card(packet)
    chinese, english = rendered.split("\n\n## English original (原文)\n\n", 1)

    self.assertTrue(chinese.startswith("估值研究卡"))
    self.assertIn("状态", chinese)
    self.assertIn("事实", chinese)
    self.assertIn("计算", chinese)
    self.assertIn("US.ACME", chinese)
    self.assertIn("$", chinese)
    self.assertIn("2026-07-19", chinese)
    self.assertEqual(
        english,
        stock_valuation._render_valuation_card_english(
            stock_valuation._checked_public_projection(packet)
        ),
    )
```

Import the module as `from investment_knowledge_mcp import stock_valuation` alongside the existing direct function imports. The private canonical helper is intentionally a normal module-level function so the test compares the exact production English body without adding a test-only hook.

- [ ] **Step 2: Add a failing method-library bilingual test.**

```python
def test_method_library_is_chinese_first_and_preserves_order(self) -> None:
    rendered = render_valuation_methods()
    chinese, english = rendered.split("\n\n## English original (原文)\n\n", 1)

    self.assertTrue(chinese.startswith("估值方法库"))
    self.assertIn("专业方法", chinese)
    self.assertLess(chinese.index("Free Cash Flow"), chinese.index("Comparable Multiples"))
    self.assertIn("Free Cash Flow", english)
    self.assertIn("Residual Income / ROE-PB", english)
```

- [ ] **Step 3: Add a failing fallback and safety test.**

Inject an unknown controlled phrase into a bounded fixture field that the public renderer already exposes, then assert the Chinese section includes `原文回退` (or the exact chosen fallback marker) and the original phrase. Assert the combined card still excludes `authorization`, `bearer`, `token=`, `traceback`, filesystem paths, and URLs where the existing safety tests require exclusion.

- [ ] **Step 4: Run the focused tests and verify RED.**

Run:

```bash
.venv/bin/python -m unittest tests.test_stock_valuation.StockValuationTests.test_card_is_chinese_first_with_exact_english_original -v
.venv/bin/python -m unittest tests.test_stock_valuation.StockValuationTests.test_method_library_is_chinese_first_and_preserves_order -v
```

Expected: both tests fail because the current renderers begin with English and do not contain the English-original delimiter. Fix any test import/name errors until the failures are specifically about the missing bilingual behavior.

---

### Task 2: Implement deterministic bilingual valuation renderers

**Files:**
- Modify: `investment_knowledge_mcp/stock_valuation.py` at `render_valuation_methods()` and `render_valuation_card()`.
- Test: `tests/test_stock_valuation.py` from Task 1.

**Interfaces:**
- Consumes `_checked_public_projection(packet)` and the existing valuation method definitions.
- Produces the same public signatures, with bilingual Markdown strings.

- [ ] **Step 1: Extract canonical English builders without changing content.**

Move the current body of `render_valuation_methods()` into a private helper with an explicit typed return:

```python
def _render_valuation_methods_english() -> str:
    ...
```

Move the current body of `render_valuation_card()` after public projection into:

```python
def _render_valuation_card_english(public: dict[str, object]) -> str:
    ...
```

The helpers must emit the current English lines in the current order. `render_valuation_card(packet)` still validates the packet and obtains exactly one public projection, then passes it to the helper. `build_valuation_artifact_evidence()` is not modified.

- [ ] **Step 2: Add an allow-listed presentation mapper.**

Implement a small side-effect-free helper in the same module:

```python
_ENGLISH_ORIGINAL_HEADER = "## English original (原文)"

def _compose_bilingual_markdown(chinese_lines: list[str], english: str) -> str:
    return "\n".join(chinese_lines) + "\n\n" + _ENGLISH_ORIGINAL_HEADER + "\n\n" + english
```

Build Chinese lines from canonical English lines using explicit controlled prefix/phrase mappings for headings, status, gap/recovery copy, metric labels, source/freshness labels, frame labels, method-library labels, specialist markers, and safety copy. Preserve dynamic suffixes after the controlled prefix byte-for-byte. For a line not covered by the mapping, emit `原文回退: {original_line}` in the Chinese section. Do not use regex replacements that can alter symbols, numbers, dates, IDs, URLs, or formula references.

- [ ] **Step 3: Wire both public renderers to the composer.**

```python
def render_valuation_methods() -> str:
    english = _render_valuation_methods_english()
    return _compose_bilingual_markdown(_translate_method_lines(english.splitlines()), english)


def render_valuation_card(packet: dict[str, object]) -> str:
    if not isinstance(packet, dict):
        raise TypeError("packet must be a mapping")
    public = _checked_public_projection(packet)
    english = _render_valuation_card_english(public)
    return _compose_bilingual_markdown(_translate_card_lines(english.splitlines()), english)
```

The canonical English string must be computed once per public call and reused as the appended body. No artifact field or evidence projection may contain the translated string.

- [ ] **Step 4: Run focused tests and verify GREEN.**

Run:

```bash
.venv/bin/python -m unittest tests.test_stock_valuation.StockValuationTests.test_card_is_chinese_first_with_exact_english_original tests.test_stock_valuation.StockValuationTests.test_method_library_is_chinese_first_and_preserves_order -v
.venv/bin/python -m unittest tests.test_stock_valuation -v
```

Expected: the two new tests and all existing valuation tests pass with no artifact/evidence schema changes.

- [ ] **Step 5: Refactor only after green.**

Deduplicate phrase mappings or line-prefix translation helpers while keeping the focused suite green. Do not broaden the mapper to generic Command Workbench output.

---

### Task 3: Verify router behavior and update product/technical state

**Files:**
- Modify: `tests/test_stock_valuation.py` latest/create/method route assertions.
- Modify: `docs/product/PRD-Stock-Valuation-Research.md` with the approved bilingual presentation addendum and acceptance criteria.
- Modify: `docs/techplans/stock-valuation-research.md` with the bilingual renderer traceability rows and implementation evidence.
- Modify: `docs/project-management/Feature-Registry.md` to show the enhancement as implemented pending release while preserving `AT-2026-07-19-001=blocked`.
- Modify: `docs/project-management/Delivery-Queue.md` to close the Product design blocker and create one Development dispatch row with exact branch/ref and watch owner.
- Modify: `docs/project-management/Coordinator-Context-Packet.md` with the Development watch contract.

**Interfaces:**
- Consumes the bilingual renderers from Task 2 and existing router actions.
- Produces a ready-to-deploy feature branch plus authoritative traceability.

- [ ] **Step 1: Add route-level assertions.**

Update existing create/latest/method tests so every affected result satisfies:

```python
self.assertTrue(result.ok)
self.assertTrue(result.message.startswith("估值"))
self.assertIn("## English original (原文)", result.message)
self.assertIn("Valuation research card:", result.message)
```

Keep evidence routes JSON-only and assert that their parsed schema and keys are unchanged. Keep all no-insight-write and query/research-write classifier assertions unchanged.

- [ ] **Step 2: Run the router and preservation suites.**

Run:

```bash
.venv/bin/python -m unittest tests.test_stock_valuation tests.test_command_workbench tests.test_app_gateway -v
```

Expected: all tests pass; only the two valuation Markdown surfaces contain the bilingual delimiter.

- [ ] **Step 3: Update the PRD and technical-plan traceability.**

Add the approved Chinese-first/English-original contract to the existing PRD as a bounded presentation addendum. Add exact file/test evidence and a separate release/independent-acceptance row to the technical plan. Do not rewrite the original 17 P0 valuation criteria or change artifact/access boundaries.

- [ ] **Step 4: Reconcile registry and queue state.**

Advance the enhancement registry fields to implementation `implemented`, verification `verified`, deployment `needs_deploy`, and user acceptance `pending`, while keeping the original protected acceptance row blocked. Close `DQ-2026-07-22-001` as the accepted Product Return Gate, add one current-date Development dispatch row with the exact pushed candidate ref, and record the feature-owned watch path and expected return evidence.

---

### Task 4: Development Return Gate, integration, deploy, and independent acceptance

**Files:**
- Modify: `docs/project-management/Delivery-Queue.md` after each role return.
- Modify: `docs/project-management/Coordinator-Context-Packet.md` after each handoff.
- Modify: `docs/project-management/Acceptance-Queue.md` only to update the same `AT-2026-07-19-001` row; never create a duplicate row.
- Modify: `docs/project-management/Feature-Registry.md` after verification/deploy/acceptance state changes.

**Interfaces:**
- Consumes the pushed implementation ref from Task 3.
- Produces one integrated authoritative release ref, one serialized deploy decision, and one independent acceptance dispatch.

- [ ] **Step 1: Apply the Development Return Gate.**

Inspect the returned diff, tests, branch ancestry, and changed-file scope. Reject any change to artifacts, evidence JSON, auth, ingress, Compose, public ports, or unrelated feature state. Integrate only the validated implementation and docs into the coordinator branch, preserving newer `origin/main` state.

- [ ] **Step 2: Run the complete pre-deploy verification.**

Run:

```bash
.venv/bin/python -m unittest tests.test_stock_valuation tests.test_command_workbench tests.test_app_gateway tests.test_data_source_contracts tests.test_data_source_pool tests.test_data_source_market_bars tests.test_data_source_market_activity -v
.venv/bin/python -m py_compile investment_knowledge_mcp/stock_valuation.py investment_knowledge_mcp/command_router.py
git diff --check
.venv/bin/python scripts/audit_delivery_state.py --feature "Stock valuation research"
.venv/bin/python scripts/audit_agent_flow_health.py --feature "Stock valuation research"
python3 scripts/classify_deploy_change.py --base-sha "$(git merge-base origin/main HEAD)" --target-sha HEAD
```

The classifier must select one serialized quick release targeting the existing shared service; if it selects a different mode, record the exact reason and do not improvise a deploy path.

- [ ] **Step 3: Record Deploy Intent and use the shared workflow.**

Record feature, immutable integrated ref, `quick` mode, affected `weekly-review-web`/existing gateway service set, verification URL `http://47.84.190.191:8010/command`, and this coordinator as watch owner. Use only the approved serialized Ops/GitHub deploy workflow. Do not recreate services, modify ingress, or use ad hoc SSH/restarts.

- [ ] **Step 4: Perform coordinator smoke on the deployed ref.**

Verify `/health`, `/command`, catalog presence, public/local-first recovery, and representative valuation create/latest/method outputs. Confirm the Chinese-first header, exact English-original body, US/HK/KR values, artifact latest read-back, bounded evidence JSON, no path/token/raw-error leakage, and stable service health.

- [ ] **Step 5: Dispatch the same acceptance item to independent testing.**

Keep `AT-2026-07-19-001` as the sole acceptance row. Route it to the independent Quality & Acceptance Lead with the exact deployed ref, URL, required journeys, and protected fixture/session blocker. Do not request user acceptance while the row is blocked.

- [ ] **Step 6: Apply the independent return gate and reconcile authoritative main.**

Inspect independent evidence, update the same Acceptance Queue row, close or block the corresponding Delivery Queue row with a named owner and resume condition, compare coordinator ref against `origin/main`, run both delivery audits, push the final state, and report the exact immutable ref, deploy decision, acceptance state, watch path, and remaining blocker.

---

## Self-review checklist

- Every design requirement maps to Task 1, 2, 3, or 4.
- No task changes the packet/evidence schema or access topology.
- All tests use existing Python `unittest` fixtures and exact commands.
- The only unresolved product acceptance gap is the already-recorded protected fixture/session requirement; the bilingual feature itself has a deterministic public/local-first verification path.
