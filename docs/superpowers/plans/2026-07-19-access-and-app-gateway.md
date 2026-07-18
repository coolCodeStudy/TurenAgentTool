# Access Policy And Application Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Command Workbench, Weekly Review, and Daily Market Brief one user-access policy and one command HTTP controller, then retire the standalone command-api service without changing public behavior.

**Architecture:** Extract pure access/config and command-controller modules first. Both legacy handlers delegate to them during compatibility. A compositional app gateway then owns browser routes while focused renderers/controllers remain separate modules.

**Tech Stack:** Python 3.11 stdlib HTTP server, dataclasses, hmac, unittest, existing browser JavaScript helper.

**Implementation status (2026-07-19):** Implemented and independently reviewed through Task 6 on `codex/architecture-consolidation`. One typed access contract and command controller now serve the browser routes; `WeeklyReviewWebHandler` is the single production handler; standalone `command-api` is retired from the five-service topology while host port 8001 remains mapped to the gateway. Compose resolves canonical and legacy token names to one configured value and keeps legacy request headers for this compatibility release. The deploy/Ops/gateway review suite passed 298 focused tests. Production verification is tracked by `DQ-2026-07-19-001`.

## Global Constraints

- Never log, render, persist, compare in error text, or expose a token value.
- Keep Ops, DingTalk, GitHub, and provider credentials outside browser access config.
- Preserve `public_read`, `protected`, and `public_read_protected_write` behavior.
- Do not add controller responsibilities to `weekly_review_web.py`.
- Keep legacy headers and environment aliases only through an explicit retirement gate.

---

### Task 1: Browser Access Configuration And Decision Contract

**Files:**
- Create: `investment_knowledge_mcp/web_access.py`
- Modify: `investment_knowledge_mcp/config.py`
- Test: `tests/test_web_access.py`

**Interfaces:**
- Produces: `AccessClass`, `AccessError`, `BrowserAccessConfig.resolve(...)`, `extract_bearer_token(...)`, and `authorize_request(...)`.
- Consumers: command-api and app gateway handlers.

- [ ] **Step 1: Write failing configuration and authorization tests**

```python
def test_canonical_token_is_used_when_legacy_aliases_are_absent(): ...
def test_equal_legacy_aliases_are_compatible(): ...
def test_conflicting_configured_aliases_fail_closed_without_values(): ...
def test_public_read_allows_missing_configuration(): ...
def test_protected_route_distinguishes_not_configured_required_and_rejected(): ...
```

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest tests.test_web_access -v`

- [ ] **Step 3: Implement the pure decision API**

```python
class AccessClass(str, Enum):
    PUBLIC_READ = "public_read"
    PROTECTED = "protected"
    PUBLIC_READ_PROTECTED_WRITE = "public_read_protected_write"

@dataclass(frozen=True)
class BrowserAccessConfig:
    token: str | None
    source: str | None
    conflict: bool = False

def authorize_request(
    access_class: AccessClass,
    method: str,
    configured: BrowserAccessConfig,
    supplied_tokens: tuple[str, ...],
) -> AccessDecision: ...
```

Read `APP_ACCESS_TOKEN` as canonical and the two current token variables as
temporary aliases. Configuration conflicts return a code, not values.

- [ ] **Step 4: Verify GREEN and config tests**

Run: `python3 -m unittest tests.test_web_access tests.test_config -v`

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/web_access.py investment_knowledge_mcp/config.py tests/test_web_access.py
git commit -m "feat: unify browser access policy"
```

### Task 2: Shared Command HTTP Controller

**Files:**
- Create: `investment_knowledge_mcp/command_http.py`
- Modify: `investment_knowledge_mcp/command_api.py`
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Test: `tests/test_command_http.py`
- Test: `tests/test_web_experience.py`

**Interfaces:**
- Produces: `CommandHttpRequest`, `CommandHttpResponse`, `execute_command_request(...)`, and `execute_workbench_request(...)`.
- Consumes: `handle_command`, Workbench preview/execute functions, and repository event recording.

- [ ] **Step 1: Add failing response-parity tests for legacy command-api and weekly command paths**

Cover valid command, missing input, unauthorized request, parser recovery,
execution failure, event recording failure, and sanitized public errors.

- [ ] **Step 2: Verify RED for the missing shared controller**

Run: `python3 -m unittest tests.test_command_http -v`

- [ ] **Step 3: Implement transport-neutral command functions**

```python
@dataclass(frozen=True)
class CommandHttpRequest:
    body: Mapping[str, object]
    source: str
    sender: str | None = None

@dataclass(frozen=True)
class CommandHttpResponse:
    status: int
    payload: dict[str, object]

def execute_command_request(request: CommandHttpRequest) -> CommandHttpResponse: ...
```

Handlers remain responsible only for HTTP parsing/writing and access-policy
application.

- [ ] **Step 4: Delegate both handlers and remove duplicated helper ownership**
- [ ] **Step 5: Run parity tests and commit**

Run: `python3 -m unittest tests.test_command_http tests.test_web_experience tests.test_weekly_review_web_auth -v`

```bash
git add investment_knowledge_mcp/command_http.py investment_knowledge_mcp/command_api.py investment_knowledge_mcp/weekly_review_web.py tests
git commit -m "refactor: share command HTTP controller"
```

### Task 3: Shared Handler Access Adapter

**Files:**
- Create: `investment_knowledge_mcp/http_access.py`
- Modify: `investment_knowledge_mcp/command_api.py`
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Test: `tests/test_http_access.py`
- Test: `tests/test_weekly_review_web_auth.py`

**Interfaces:**
- Produces: `authorize_http(handler, access_class, *, write=False) -> bool` using the pure policy from Task 1.

- [ ] **Step 1: Add failing tests proving identical status/error codes for both handlers**
- [ ] **Step 2: Implement header extraction and response adaptation once**
- [ ] **Step 3: Replace `_require_authorized`, `_authorized_for_command_workbench`, `_authorized`, `_supplied_command_token`, and duplicate bearer parsing**
- [ ] **Step 4: Verify all browser route contract tests**

Run: `python3 -m unittest tests.test_http_access tests.test_web_experience tests.test_weekly_review_web_auth tests.test_daily_market_brief -v`

- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/http_access.py investment_knowledge_mcp/command_api.py investment_knowledge_mcp/weekly_review_web.py tests
git commit -m "refactor: share HTTP access adapter"
```

### Task 4: Compositional App Gateway

**Files:**
- Create: `investment_knowledge_mcp/app_gateway.py`
- Create: `investment_knowledge_mcp/weekly_review_controller.py`
- Create: `investment_knowledge_mcp/daily_market_brief_controller.py`
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Test: `tests/test_app_gateway.py`

**Interfaces:**
- Produces: `AppGatewayHandler` and focused controller functions.
- Preserves: `/health`, `/command`, Workbench API routes, `/weekly-review`, and `/daily-market-brief`.

- [ ] **Step 1: Add route ownership tests for every existing GET/POST path**
- [ ] **Step 2: Extract controller functions without changing renderer output**
- [ ] **Step 3: Compose routing in `AppGatewayHandler`**
- [ ] **Step 4: Keep `weekly_review_web.main()` as a compatibility wrapper that starts the gateway**
- [ ] **Step 5: Run route, auth, renderer, and browser tests**

Run: `python3 -m unittest tests.test_app_gateway tests.test_web_experience tests.test_weekly_review_web_auth tests.test_daily_market_brief -v`

- [ ] **Step 6: Commit**

```bash
git add investment_knowledge_mcp/app_gateway.py investment_knowledge_mcp/*_controller.py investment_knowledge_mcp/weekly_review_web.py tests/test_app_gateway.py
git commit -m "refactor: compose browser routes in app gateway"
```

### Task 5: Deployment Classifier Ownership

**Files:**
- Modify: `scripts/deploy_contract.py`
- Modify: `tests/test_deploy_change_classifier.py`

**Interfaces:**
- Produces deterministic targeted service ownership for new gateway/access/controller modules and DingTalk transport-only code.

- [ ] **Step 1: Add failing classifier tests**

```python
def test_dingtalk_http_adapter_targets_only_dingtalk_api(): ...
def test_app_gateway_targets_only_weekly_review_web_during_compatibility(): ...
def test_shared_access_targets_command_and_gateway_until_command_retirement(): ...
```

- [ ] **Step 2: Verify RED using the current all-service fallback**
- [ ] **Step 3: Add the narrow PathRules before the catch-all rule**
- [ ] **Step 4: Run classifier and deploy-release contract suites**

Run: `python3 -m unittest tests.test_deploy_change_classifier tests.test_deploy_release -v`

- [ ] **Step 5: Commit**

```bash
git add scripts/deploy_contract.py tests/test_deploy_change_classifier.py
git commit -m "fix: declare gateway and transport deploy ownership"
```

### Task 6: Caller Inventory And Command API Retirement

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `scripts/deploy_contract.py`
- Modify: `scripts/deploy_release.py`
- Modify: `scripts/ecs_ops_api.py`
- Modify: `.github/workflows/ops-api.yml` if diagnostics require it
- Modify: relevant deployment tests and docs

**Interfaces:**
- Consumes: runtime caller inventory plus all parity tests.
- Produces: one app-gateway command route and no standalone command-api service.

- [ ] **Step 1: Prove no caller requires the command-api host port or preserve an ingress compatibility mapping**
- [ ] **Step 2: Add failing topology tests expecting command-api removal**
- [ ] **Step 3: Remove command-api from Compose, managed-service inventory, aliases, health checks, and deploy targets**
- [ ] **Step 4: Classify the Compose change and run the full deployment contract suite**
- [ ] **Step 5: Deploy under the production lock, verify browser/API parity, and observe stability**
- [ ] **Step 6: Commit the retirement evidence and remove expired token/header aliases in a later compatible release**
