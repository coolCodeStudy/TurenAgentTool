# Architecture & Code Health Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a durable Architecture & Code Health Agent role with a repository-owned skill, deterministic read-only audit, and accountable delivery handoff.

**Architecture:** Keep the role contract in the operating model, the workflow in a compact versioned skill, and structural facts in a standalone Python AST audit. The audit reports baseline P1 findings as Markdown and JSON; it does not modify product state, call the network, inspect environment values, or block CI in V1.

**Tech Stack:** Python 3 standard library (`ast`, `argparse`, `json`, `pathlib`, `unittest`), Markdown, existing project-management state.

## Global Constraints

- This is operating-model infrastructure, not a Feature Registry product feature.
- The V1 audit is read-only, deterministic, credential-free, and `no_deploy`.
- No architectural finding may become a blocking rule without the rule-admission gate in the architecture contract.
- Findings must name evidence, severity, owner, bounded implementation slice, and verification.
- The Architecture Agent does not change product access policy, tokens, deployment targets, acceptance status, or unrelated feature code.

---

## File Structure

- Create: `docs/architecture/architecture-contract.md` — stable principles, current route inventory, rule-admission gate, baseline exception format.
- Create: `skills/architecture-code-health/SKILL.md` — concise trigger and audit-to-handoff workflow.
- Create: `docs/project-management/prompt-templates/Architecture-Code-Health.md` — repeatable role dispatch contract.
- Create: `scripts/audit_architecture_health.py` — deterministic source inventory, import-cycle and route-contract audit, Markdown/JSON output.
- Create: `tests/test_architecture_health_audit.py` — fixture-based unit coverage for passing and failing structures and CLI JSON output.
- Create: `scripts/install_architecture_code_health_skill.py` — checks a local installed skill against the tracked source without copying or reading secrets.
- Modify: `docs/product/Agent-Operating-Model.md` — add the role and its escalation boundary.
- Modify: `docs/project-management/Agent-Operating-Model-Roadmap.md` — record V1 as active operating-model work and its rollout decision.
- Modify: `docs/project-management/Delivery-Queue.md` — record this dispatch and its explicit closure/watch path.

## Task 1: Establish the role contract and routing surface

**Files:**
- Create: `docs/architecture/architecture-contract.md`
- Create: `docs/project-management/prompt-templates/Architecture-Code-Health.md`
- Modify: `docs/product/Agent-Operating-Model.md`
- Modify: `docs/project-management/Agent-Operating-Model-Roadmap.md`
- Modify: `docs/project-management/Delivery-Queue.md`

**Consumes:** the approved design at `docs/superpowers/specs/2026-07-16-architecture-code-health-design.md`.

**Produces:** one explicit specialist role whose findings return to Feature Coordinators and whose governance state stays outside the Feature Registry.

- [ ] **Step 1: Add the architecture contract**

Define these exact V1 route declarations:

```markdown
| Route | Owner module | Access class | Contract test |
|---|---|---|---|
| `/command` | `investment_knowledge_mcp.command_workbench` | protected | `tests/test_web_experience.py` |
| `/weekly-review` | `investment_knowledge_mcp.weekly_review_web` | public_read_protected_write | `tests/test_weekly_review_web_auth.py` |
| `/daily-market-brief` | `investment_knowledge_mcp.weekly_review_web` | public_read | `tests/test_daily_market_brief.py` |
```

State that V1 only reports rule failures and that a P0 gate requires a passing baseline, fixture coverage, named owner, bounded remediation, no credentials/network, and a demonstrated regression class.

- [ ] **Step 2: Add the operating-model role**

Add an `Architecture & Code Health Agent` bullet to the organization with this responsibility: inspect cross-feature technical structure, run the harness, and produce bounded evidence-backed slices. Add an escalation sentence: Feature Coordinators receive and close feature-specific findings; Global PM prioritizes systemic debt; Owner is asked only for cross-feature tradeoffs or priority.

- [ ] **Step 3: Add the dispatch template**

Use this mandatory return shape:

```text
- Audit ref and command:
- Findings (ID, evidence, severity):
- Affected boundary:
- Recommended Feature Coordinator:
- Smallest safe slice:
- Required verification and deploy decision:
- Rule-admission recommendation:
- Escalation target:
- Role learning:
```

- [ ] **Step 4: Track V1 in Roadmap and Delivery Queue**

Add a P1 roadmap subsection titled `Architecture And Code Health` with the V1 role, skill, report-only audit, baseline, and later P0-admission criteria. Add a single Delivery Queue row marked `in_progress`, with this task as its source and the Global PM as the V1 integration owner. Its wake event is the harness baseline and tests passing; its next action is to close the row and let the role run only when dispatched by the Global PM or a Feature Coordinator.

- [ ] **Step 5: Verify documentation coherence**

Run:

```bash
git diff --check
python3 scripts/evaluate_agent_flow_cases.py
```

Expected: no whitespace errors; all agent-flow evaluation cases pass.

- [ ] **Step 6: Commit**

```bash
git add docs/architecture/architecture-contract.md docs/product/Agent-Operating-Model.md docs/project-management/Agent-Operating-Model-Roadmap.md docs/project-management/Delivery-Queue.md docs/project-management/prompt-templates/Architecture-Code-Health.md
git commit -m "docs: add architecture code health role"
```

## Task 2: Write and validate the versioned role skill

**Files:**
- Create: `skills/architecture-code-health/SKILL.md`
- Create: `scripts/install_architecture_code_health_skill.py`
- Test: `tests/test_architecture_health_audit.py`

**Consumes:** the architecture contract and prompt template from Task 1.

**Produces:** a concise repository source-of-truth skill plus a non-mutating stale-copy check.

- [ ] **Step 1: Write failing installer-check tests**

Add tests that create a temporary tracked source and local destination, then assert:

```python
self.assertEqual(0, check_skill(source, matching_destination).exit_code)
self.assertEqual(1, check_skill(source, stale_destination).exit_code)
self.assertIn("stale", check_skill(source, stale_destination).message)
self.assertEqual(1, check_skill(source, missing_destination).exit_code)
```

- [ ] **Step 2: Run the focused test to confirm it fails**

```bash
.venv/bin/python -m unittest tests.test_architecture_health_audit.ArchitectureSkillCheckTests -v
```

Expected: failure because `check_skill` is not importable.

- [ ] **Step 3: Implement the read-only installer check**

Expose:

```python
@dataclass(frozen=True)
class SkillCheck:
    exit_code: int
    message: str

def check_skill(source: Path, destination: Path) -> SkillCheck:
    if not destination.is_file():
        return SkillCheck(1, "local skill is missing")
    if source.read_bytes() != destination.read_bytes():
        return SkillCheck(1, "local skill is stale")
    return SkillCheck(0, "local skill matches tracked source")
```

Provide CLI options `--source` and `--destination`, defaulting only to the repository source and `$CODEX_HOME/skills/architecture-code-health/SKILL.md`. Never copy files, read env values other than the path, or print source contents.

- [ ] **Step 4: Write the skill**

Keep `SKILL.md` below 250 lines. Its workflow must run the audit first, inspect only implicated files, distinguish fact from recommendation, write the exact dispatch return shape, and prohibit direct broad refactors or secret/access-policy changes. Link to the contract and prompt template rather than duplicating them.

- [ ] **Step 5: Run focused tests**

```bash
.venv/bin/python -m unittest tests.test_architecture_health_audit.ArchitectureSkillCheckTests -v
python3 scripts/install_architecture_code_health_skill.py --source skills/architecture-code-health/SKILL.md --destination /private/tmp/architecture-code-health-missing/SKILL.md
```

Expected: tests pass; CLI reports a missing local skill and exits `1` without creating files.

- [ ] **Step 6: Commit**

```bash
git add skills/architecture-code-health/SKILL.md scripts/install_architecture_code_health_skill.py tests/test_architecture_health_audit.py
git commit -m "feat: add architecture code health skill"
```

## Task 3: Build the deterministic architecture audit

**Files:**
- Create: `scripts/audit_architecture_health.py`
- Modify: `tests/test_architecture_health_audit.py`

**Consumes:** `docs/architecture/architecture-contract.md` and Python source rooted at `investment_knowledge_mcp`.

**Produces:** stable Markdown/JSON findings without network or credential access.

- [ ] **Step 1: Write failing audit tests using a temporary repository fixture**

Cover these exact cases:

```python
self.assertEqual([], find_import_cycles({"a": {"b"}, "b": set()}))
self.assertEqual([("a", "b", "a")], find_import_cycles({"a": {"b"}, "b": {"a"}}))
self.assertEqual("P1", route_finding("/command", route_inventory)["severity"])
self.assertEqual("missing_contract_test", route_finding("/new", route_inventory)["kind"])
self.assertIn("format_version", json.loads(render_json(report)))
```

Include one fixture whose Python AST imports form a cycle and one route declaration with no matching test path. Assert finding IDs and sorted ordering rather than source-line incidental text.

- [ ] **Step 2: Run the audit tests to confirm failure**

```bash
.venv/bin/python -m unittest tests.test_architecture_health_audit.ArchitectureAuditTests -v
```

Expected: failure because audit functions are absent.

- [ ] **Step 3: Implement source inventory and cycle detection**

Expose only these serializable types and functions:

```python
@dataclass(frozen=True)
class Finding:
    id: str
    severity: str
    kind: str
    evidence: tuple[str, ...]
    owner: str
    slice: str
    verification: str

def collect_python_modules(package_root: Path) -> dict[str, set[str]]: ...
def find_import_cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]: ...
def audit_repository(repo: Path) -> list[Finding]: ...
def render_markdown(findings: list[Finding]) -> str: ...
def render_json(findings: list[Finding]) -> str: ...
```

Parse only `*.py` below the package root with `ast.parse`. Resolve only absolute imports beginning with `investment_knowledge_mcp`; treat parse errors as P1 `unparseable_module` findings. Sort all paths, modules, edges, cycles, and findings.

- [ ] **Step 4: Implement contract and route-test checks**

Parse the Markdown route table with a narrow table-row parser. Emit P1 findings for an invalid access class, a missing owner module, a missing contract-test file, or a declared owner module absent from the package. Do not attempt runtime route discovery and do not infer token values or authorization behavior.

- [ ] **Step 5: Implement the CLI**

Provide:

```bash
python3 scripts/audit_architecture_health.py --repo . --format markdown
python3 scripts/audit_architecture_health.py --repo . --format json
```

The CLI returns `0` for reports containing P1 findings and `2` only for invalid arguments or an unreadable repository/contract. JSON output is a single object with `format_version`, `summary`, and `findings` keys.

- [ ] **Step 6: Run baseline and all focused tests**

```bash
.venv/bin/python -m unittest tests.test_architecture_health_audit -v
python3 scripts/audit_architecture_health.py --repo . --format json
python3 scripts/audit_architecture_health.py --repo . --format markdown
```

Expected: all tests pass; both audit outputs are deterministic, contain no environment values, and report only P1 findings for current debt.

- [ ] **Step 7: Commit**

```bash
git add scripts/audit_architecture_health.py tests/test_architecture_health_audit.py
git commit -m "feat: add architecture health audit"
```

## Task 4: Integrate the baseline and close the operating-model dispatch

**Files:**
- Modify: `docs/architecture/architecture-contract.md`
- Modify: `docs/project-management/Agent-Operating-Model-Roadmap.md`
- Modify: `docs/project-management/Delivery-Queue.md`

**Consumes:** passing audit and its authoritative-main output.

**Produces:** an explicit V1 baseline and a closed implementation dispatch, without creating product feature rows.

- [ ] **Step 1: Run and capture the baseline**

```bash
python3 scripts/audit_architecture_health.py --repo . --format markdown
```

Record only finding IDs, affected boundaries, and their report-only status in the contract. Do not paste generated output or secret-like content.

- [ ] **Step 2: Close the Delivery Queue row**

Set the V1 row to `closed`, record the committed ref, the baseline command, and this next action: “Architecture audits are dispatchable report-only reviews; findings enter a Feature Coordinator flow only after Global PM prioritization or a feature-specific request.”

- [ ] **Step 3: Mark Roadmap V1 delivered**

Retain later rule admission as active follow-up, explicitly stating that there are no blocking architecture rules in V1.

- [ ] **Step 4: Run final verification**

```bash
git diff --check
.venv/bin/python -m unittest tests.test_architecture_health_audit tests.test_agent_flow_health_audit -v
python3 scripts/evaluate_agent_flow_cases.py
python3 scripts/classify_deploy_change.py --format json docs/architecture/architecture-contract.md docs/product/Agent-Operating-Model.md docs/project-management/Agent-Operating-Model-Roadmap.md docs/project-management/Delivery-Queue.md docs/project-management/prompt-templates/Architecture-Code-Health.md skills/architecture-code-health/SKILL.md scripts/audit_architecture_health.py scripts/install_architecture_code_health_skill.py tests/test_architecture_health_audit.py
```

Expected: all tests/evals pass; classifier returns `no_deploy`.

- [ ] **Step 5: Commit and push**

```bash
git add docs/architecture/architecture-contract.md docs/project-management/Agent-Operating-Model-Roadmap.md docs/project-management/Delivery-Queue.md
git commit -m "docs: baseline architecture health role"
git push origin <implementation-branch>
```

## Plan Self-Review

- Spec coverage: Tasks 1-4 cover the approved role contract, versioned skill, deterministic harness, tests, baseline, delivery integration, and non-blocking rollout.
- Deferred deliberately: CI P0 gates and recurring automation require baseline evidence and are not implemented in V1.
- Placeholder scan: no unresolved implementation placeholders; all created files, interfaces, expected commands, and behavior are specified.
- Type consistency: `Finding`, `SkillCheck`, `audit_repository`, and `check_skill` are defined before their tests or CLI consumers.
