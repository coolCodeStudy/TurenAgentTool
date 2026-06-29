from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.analysis_provider import propose_command_workbench_parse_with_openai
from investment_knowledge_mcp.command_router import (
    PORTFOLIO_ANALYSIS_COMMANDS,
    PORTFOLIO_POSITION_COMMANDS,
    RECENT_ERRORS_COMMANDS,
    RESEARCH_JOB_CREATE_COMMANDS,
    RESEARCH_JOB_LIST_COMMANDS,
    SYSTEM_STATUS_COMMANDS,
    WEEKLY_REVIEW_COMMANDS,
    WORKER_STATUS_COMMANDS,
)

COMMAND_WORKBENCH_AUTH_RECOVERY_MESSAGE = (
    "Enter the private Command Workbench access token and preview again. "
    "The token is stored only in this browser and is required for private previews and runs."
)


COMMAND_WORKBENCH_AUTH_RECOVERY_MESSAGE = (
    "Enter the private Command Workbench access token and preview again. "
    "The token is stored only in this browser and is required for private previews and runs."
)


def command_workbench_auth_error_payload() -> dict[str, Any]:
    return {
        "ok": False,
        "error": "unauthorized",
        "message": COMMAND_WORKBENCH_AUTH_RECOVERY_MESSAGE,
        "recovery": {
            "title": "Access token required",
            "next_action": "Enter the private access token and preview again.",
            "storage": "Stored only in this browser localStorage key command_workbench_token.",
        },
    }


@dataclass(frozen=True)
class CommandAction:
    id: str
    action_family: str
    label: str
    description: str
    aliases: tuple[str, ...]
    required_fields: tuple[dict[str, Any], ...]
    optional_fields: tuple[dict[str, Any], ...]
    template: str
    safety_level: str
    confirmation_required: bool
    result_type: str
    side_effects: str
    data_sources: tuple[str, ...]
    expected_output: str
    supports_execution: bool = True
    pinned: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_family": self.action_family,
            "label": self.label,
            "description": self.description,
            "aliases": list(self.aliases),
            "required_fields": list(self.required_fields),
            "optional_fields": list(self.optional_fields),
            "template": self.template,
            "safety_level": self.safety_level,
            "confirmation_required": self.confirmation_required,
            "result_type": self.result_type,
            "side_effects": self.side_effects,
            "data_sources": list(self.data_sources),
            "expected_output": self.expected_output,
            "supports_execution": self.supports_execution,
            "pinned": self.pinned,
        }


@dataclass
class ParseContext:
    raw_input: str
    action_id: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    selected_target: dict[str, Any] | None = None
    parse_source: str = "deterministic"
    confidence: float = 0.0
    recovery_message: str = ""


STOCK_FIELD = ({"id": "stock", "label": "Stock", "type": "stock", "placeholder": "Intel, 英特尔, US.INTC"},)
SERVICE_FIELD = (
    {
        "id": "service",
        "label": "Service",
        "type": "select",
        "options": ["mcp", "command-api", "codex-worker", "research-agent-worker", "dingtalk-stream-bot"],
    },
)

ACTIONS: dict[str, CommandAction] = {
    "decision_card": CommandAction(
        id="decision_card",
        action_family="Decision",
        label="Create decision",
        description="Show the Level 1 stock decision card.",
        aliases=("决策", "decision", "看一下", "分析"),
        required_fields=STOCK_FIELD,
        optional_fields=(),
        template="决策 {market}.{symbol}",
        safety_level="read_only",
        confirmation_required=False,
        result_type="stock_decision_card",
        side_effects="No trade. Reads stock profile, knowledge, insights, and latest research-job metadata.",
        data_sources=("stock profile", "knowledge base", "research jobs"),
        expected_output="Level 1 decision card with thesis, drivers, risks, watch items, and evidence counts.",
        pinned=True,
    ),
    "decision_detail": CommandAction(
        id="decision_detail",
        action_family="Decision",
        label="Decision detail",
        description="Show the fuller stock analysis context.",
        aliases=("决策详情", "股票详情", "analysis detail"),
        required_fields=STOCK_FIELD,
        optional_fields=(),
        template="分析详情 {symbol} {market}",
        safety_level="read_only",
        confirmation_required=False,
        result_type="stock_analysis_detail",
        side_effects="Writes an analysis-context artifact under the configured drafts directory.",
        data_sources=("stock profile", "knowledge base", "research jobs"),
        expected_output="Detailed stock context and a path to the generated context artifact.",
    ),
    "decision_refresh": CommandAction(
        id="decision_refresh",
        action_family="Decision",
        label="Refresh decision data",
        description="Generate a fresh research draft for a stock without importing it.",
        aliases=("刷新决策", "刷新研究草稿", "research draft"),
        required_fields=STOCK_FIELD,
        optional_fields=(),
        template="研究草稿 {symbol} {market}",
        safety_level="writes_durable_record",
        confirmation_required=True,
        result_type="research_draft",
        side_effects="Generates local draft artifacts. Does not trade and does not auto-import facts.",
        data_sources=("stock profile", "research pipeline"),
        expected_output="Research draft generation summary and artifact paths.",
    ),
    "decision_history": CommandAction(
        id="decision_history",
        action_family="Decision",
        label="Decision history",
        description="Decision-ticket history is not implemented in the current router.",
        aliases=("决策历史", "history"),
        required_fields=STOCK_FIELD,
        optional_fields=(),
        template="",
        safety_level="unsupported",
        confirmation_required=False,
        result_type="unsupported",
        side_effects="No action is executed.",
        data_sources=(),
        expected_output="Recovery message explaining that decision history is not available yet.",
        supports_execution=False,
    ),
    "portfolio_positions": CommandAction(
        id="portfolio_positions",
        action_family="Portfolio",
        label="Current positions",
        description="Show current Futu positions.",
        aliases=("当前持仓", "看当前持仓", "positions"),
        required_fields=(),
        optional_fields=(),
        template="我的持仓",
        safety_level="read_only",
        confirmation_required=False,
        result_type="portfolio_positions",
        side_effects="Reads Futu positions. Does not write portfolio records.",
        data_sources=("Futu OpenD",),
        expected_output="Current positions table rendered as text.",
        pinned=True,
    ),
    "portfolio_analysis": CommandAction(
        id="portfolio_analysis",
        action_family="Portfolio",
        label="Portfolio analysis",
        description="Analyze current portfolio structure and risks.",
        aliases=("持仓分析", "组合分析", "portfolio analysis"),
        required_fields=(),
        optional_fields=(),
        template="持仓分析",
        safety_level="read_only",
        confirmation_required=False,
        result_type="portfolio_analysis",
        side_effects="Reads positions and knowledge context. Downstream analysis may call an LLM if configured.",
        data_sources=("Futu OpenD", "knowledge base"),
        expected_output="Portfolio structure, risks, and follow-up analysis.",
        pinned=True,
    ),
    "weekly_current": CommandAction(
        id="weekly_current",
        action_family="Weekly Review",
        label="This week review",
        description="Generate this week's review through the command router.",
        aliases=("本周复盘", "weekly review"),
        required_fields=(),
        optional_fields=(),
        template="本周复盘",
        safety_level="writes_durable_record",
        confirmation_required=True,
        result_type="weekly_review",
        side_effects="May save or update a weekly review report row through the current router behavior.",
        data_sources=("trades", "snapshots", "positions", "knowledge base"),
        expected_output="Weekly review markdown and save status.",
        pinned=True,
    ),
    "weekly_previous": CommandAction(
        id="weekly_previous",
        action_family="Weekly Review",
        label="Previous week review",
        description="Generate previous week's review.",
        aliases=("上周复盘", "复盘 上周"),
        required_fields=(),
        optional_fields=(),
        template="复盘 上周",
        safety_level="writes_durable_record",
        confirmation_required=True,
        result_type="weekly_review",
        side_effects="May save or update a weekly review report row through the current router behavior.",
        data_sources=("trades", "snapshots", "positions", "knowledge base"),
        expected_output="Weekly review markdown and save status.",
    ),
    "weekly_source_diagnostics": CommandAction(
        id="weekly_source_diagnostics",
        action_family="Weekly Review",
        label="Weekly source diagnostics",
        description="Dedicated weekly source diagnostics are not implemented in the current router.",
        aliases=("周复盘数据源诊断", "weekly source diagnostics"),
        required_fields=(),
        optional_fields=(),
        template="",
        safety_level="unsupported",
        confirmation_required=False,
        result_type="unsupported",
        side_effects="No action is executed.",
        data_sources=(),
        expected_output="Recovery message explaining available weekly-review actions.",
        supports_execution=False,
    ),
    "research_create_stock_job": CommandAction(
        id="research_create_stock_job",
        action_family="Research",
        label="Create stock research job",
        description="Queue a Codex-first research job for one stock.",
        aliases=("创建研究任务", "create research job"),
        required_fields=STOCK_FIELD,
        optional_fields=(),
        template="创建研究任务 {symbol} {market}",
        safety_level="writes_durable_record",
        confirmation_required=True,
        result_type="research_job",
        side_effects="Creates or reuses a durable async research job. Does not trade.",
        data_sources=("research job queue", "Codex worker"),
        expected_output="Queued job id, provider, source policy, and execution location.",
    ),
    "research_list_jobs": CommandAction(
        id="research_list_jobs",
        action_family="Research",
        label="List research jobs",
        description="Show recent research job statuses.",
        aliases=("查看研究任务", "列出研究任务", "research jobs"),
        required_fields=(),
        optional_fields=(),
        template="查看研究任务",
        safety_level="read_only",
        confirmation_required=False,
        result_type="research_jobs",
        side_effects="Reads research job metadata only.",
        data_sources=("research job queue",),
        expected_output="Recent research job status summary.",
    ),
    "research_portfolio_jobs": CommandAction(
        id="research_portfolio_jobs",
        action_family="Research",
        label="Create portfolio research jobs",
        description="Queue research jobs for current holdings.",
        aliases=("创建持仓研究任务", "全持仓研究任务"),
        required_fields=(),
        optional_fields=(),
        template="创建持仓研究任务",
        safety_level="writes_durable_record",
        confirmation_required=True,
        result_type="research_job",
        side_effects="Reads current positions and creates durable async research jobs. Does not trade.",
        data_sources=("Futu OpenD", "research job queue", "Codex worker"),
        expected_output="Created, skipped, invalid, and queued research-job summary.",
    ),
    "system_status": CommandAction(
        id="system_status",
        action_family="System",
        label="System status",
        description="Run local system status diagnostics.",
        aliases=("系统状态", "status", "health"),
        required_fields=(),
        optional_fields=(),
        template="系统状态",
        safety_level="read_only",
        confirmation_required=False,
        result_type="system_status",
        side_effects="Reads local diagnostic state.",
        data_sources=("local config", "database", "service checks"),
        expected_output="System status summary.",
        pinned=True,
    ),
    "recent_errors": CommandAction(
        id="recent_errors",
        action_family="System",
        label="Recent errors",
        description="Show recent cloud/control-plane errors.",
        aliases=("最近错误", "recent errors"),
        required_fields=(),
        optional_fields=(),
        template="最近错误",
        safety_level="read_only",
        confirmation_required=False,
        result_type="system_errors",
        side_effects="Reads cloud/control-plane diagnostics.",
        data_sources=("Ops API",),
        expected_output="Recent error summary.",
    ),
    "worker_status": CommandAction(
        id="worker_status",
        action_family="System",
        label="Worker status",
        description="Show Codex worker status.",
        aliases=("worker状态", "codex状态", "worker status"),
        required_fields=(),
        optional_fields=(),
        template="worker状态",
        safety_level="read_only",
        confirmation_required=False,
        result_type="worker_status",
        side_effects="Reads worker status only.",
        data_sources=("Ops API",),
        expected_output="Worker queue and health summary.",
    ),
    "service_logs": CommandAction(
        id="service_logs",
        action_family="System",
        label="Service logs",
        description="Show recent logs for one allowed service.",
        aliases=("服务日志", "查看日志", "logs"),
        required_fields=SERVICE_FIELD,
        optional_fields=(),
        template="服务日志 {service}",
        safety_level="read_only",
        confirmation_required=False,
        result_type="service_logs",
        side_effects="Reads recent service logs.",
        data_sources=("Ops API",),
        expected_output="Recent log lines for the selected service.",
    ),
}


ALIAS_STOCKS: dict[str, list[dict[str, Any]]] = {
    "英特尔": [{"symbol": "INTC", "market": "US", "name": "Intel Corporation", "confidence": 0.98}],
    "intel": [{"symbol": "INTC", "market": "US", "name": "Intel Corporation", "confidence": 0.98}],
    "intel corporation": [{"symbol": "INTC", "market": "US", "name": "Intel Corporation", "confidence": 0.98}],
    "海力士": [{"symbol": "000660", "market": "KR", "name": "SK Hynix", "confidence": 0.98}],
    "sk hynix": [{"symbol": "000660", "market": "KR", "name": "SK Hynix", "confidence": 0.98}],
    "sk海力士": [{"symbol": "000660", "market": "KR", "name": "SK Hynix", "confidence": 0.98}],
    "阿里": [
        {"symbol": "09988", "market": "HK", "name": "Alibaba-W", "confidence": 0.88},
        {"symbol": "BABA", "market": "US", "name": "Alibaba Group", "confidence": 0.86},
    ],
    "alibaba": [
        {"symbol": "09988", "market": "HK", "name": "Alibaba-W", "confidence": 0.86},
        {"symbol": "BABA", "market": "US", "name": "Alibaba Group", "confidence": 0.88},
    ],
    "baba": [{"symbol": "BABA", "market": "US", "name": "Alibaba Group", "confidence": 0.96}],
    "南方两倍做多海力士": [{"symbol": "07709", "market": "HK", "name": "南方两倍做多海力士", "confidence": 0.98}],
    "腾讯": [{"symbol": "00700", "market": "HK", "name": "Tencent Holdings", "confidence": 0.95}],
}

SERVICE_ALIASES = {
    "mcp": "mcp",
    "command": "command-api",
    "command-api": "command-api",
    "codex": "codex-worker",
    "codex-worker": "codex-worker",
    "worker": "codex-worker",
    "research": "research-agent-worker",
    "research-agent-worker": "research-agent-worker",
    "dingtalk": "dingtalk-stream-bot",
    "钉钉": "dingtalk-stream-bot",
    "futu": "futu-opend",
    "opend": "futu-opend",
    "postgres": "postgres",
}


def list_workbench_actions() -> list[dict[str, Any]]:
    return [action.public_dict() for action in ACTIONS.values()]


def parse_workbench_command(
    raw_input: str = "",
    *,
    action_id: str | None = None,
    fields: dict[str, Any] | None = None,
    selected_target: dict[str, Any] | None = None,
    allow_llm: bool = True,
) -> dict[str, Any]:
    context = ParseContext(
        raw_input=raw_input.strip(),
        action_id=action_id,
        fields={
            key: value
            for key, value in (fields or {}).items()
            if value is not None and str(value).strip() != ""
        },
        selected_target=selected_target,
    )

    if context.action_id:
        return _preview_from_action(context)

    if not context.raw_input:
        return _recovery(
            "needs_field",
            raw_input="",
            recovery_message="Start with an action, stock, or supported command.",
        )

    deterministic = _parse_deterministic(context)
    if deterministic["status"] != "unsupported" or not allow_llm:
        return deterministic

    llm_proposal = _parse_with_llm(context.raw_input)
    if llm_proposal is not None:
        return llm_proposal

    return deterministic


def preview_requires_confirmation(preview: dict[str, Any]) -> bool:
    return bool(preview.get("confirmation_required"))


def execution_blocker(preview: dict[str, Any], *, confirmed: bool) -> str | None:
    if preview.get("status") != "parsed":
        return str(preview.get("recovery_message") or "Command preview is not executable.")
    if not preview.get("supports_execution", False):
        return str(preview.get("recovery_message") or "This action is not available from the workbench.")
    if not preview.get("exact_command"):
        return "No exact command was generated from the registry."
    if preview_requires_confirmation(preview) and not confirmed:
        return "Confirmation is required before running this command."
    return None


def command_workbench_auth_error_payload() -> dict[str, Any]:
    return {
        "ok": False,
        "error": "unauthorized",
        "message": COMMAND_WORKBENCH_AUTH_RECOVERY_MESSAGE,
        "recovery": {
            "title": "Access token required",
            "next_action": "Enter the private access token and preview again.",
            "storage": "Stored only in this browser localStorage key command_workbench_token.",
        },
    }


def render_command_workbench_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Command Workbench</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --ink: #1f252d;
      --muted: #637083;
      --line: #d8e0e8;
      --accent: #146c74;
      --accent-soft: #e7f4f3;
      --warn: #8a5a00;
      --warn-bg: #fff7df;
      --bad: #a33b35;
      --good: #176b43;
      --chip: #edf2f6;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 340px;
    }
    main {
      min-width: 0;
      padding: 24px;
    }
    aside {
      border-left: 1px solid var(--line);
      background: #fff;
      padding: 24px 18px;
      min-width: 0;
    }
    h1 {
      font-size: 26px;
      margin: 0 0 6px;
      letter-spacing: 0;
    }
    h2 {
      font-size: 16px;
      margin: 0 0 12px;
      letter-spacing: 0;
    }
    h3 {
      font-size: 14px;
      margin: 16px 0 8px;
      letter-spacing: 0;
    }
    p {
      margin: 0;
    }
    .subtitle {
      color: var(--muted);
      font-size: 14px;
      margin-bottom: 18px;
    }
    .input-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 150px 92px;
      gap: 8px;
      margin-bottom: 14px;
    }
    input, select, button, textarea {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
    }
    input, select {
      height: 38px;
      padding: 0 10px;
      min-width: 0;
    }
    button {
      min-height: 34px;
      padding: 0 11px;
      cursor: pointer;
      font-weight: 650;
    }
    button.primary {
      color: #fff;
      border-color: var(--accent);
      background: var(--accent);
    }
    button.secondary {
      color: var(--accent);
      border-color: var(--accent);
      background: #fff;
    }
    button:disabled {
      opacity: .55;
      cursor: not-allowed;
    }
    section, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 14px;
    }
    .preview-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      font-size: 13px;
    }
    .item {
      min-width: 0;
    }
    .label {
      color: var(--muted);
      font-size: 12px;
      display: block;
      margin-bottom: 3px;
    }
    code {
      overflow-wrap: anywhere;
    }
    .notice {
      border-left: 3px solid var(--warn);
      background: var(--warn-bg);
      color: #604000;
      padding: 10px 12px;
      border-radius: 6px;
      font-size: 13px;
      margin-bottom: 12px;
    }
    .result {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      line-height: 1.5;
      margin: 10px 0 0;
    }
    .actions {
      display: grid;
      gap: 8px;
    }
    .action {
      text-align: left;
      width: 100%;
      min-height: 58px;
      padding: 9px 10px;
      background: #fff;
    }
    .action strong {
      display: block;
      font-size: 13px;
      margin-bottom: 3px;
    }
    .action span {
      color: var(--muted);
      font-size: 12px;
      display: block;
      line-height: 1.35;
    }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }
    .chip {
      border: 1px solid var(--line);
      background: var(--chip);
      color: var(--muted);
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
    }
    .candidates {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }
    .candidate {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
    }
    .form-grid {
      display: grid;
      gap: 8px;
    }
    .form-row {
      display: grid;
      gap: 5px;
    }
    .history {
      display: grid;
      gap: 8px;
      font-size: 12px;
    }
    .history button {
      text-align: left;
      font-weight: 500;
      padding: 8px;
      height: auto;
    }
    .ok { color: var(--good); }
    .bad { color: var(--bad); }
    @media (max-width: 980px) {
      .shell { display: block; }
      aside { border-left: 0; border-top: 1px solid var(--line); }
    }
    @media (max-width: 680px) {
      main, aside { padding: 16px; }
      .input-row { grid-template-columns: 1fr; }
      .preview-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <main>
      <h1>Command Workbench</h1>
      <p class="subtitle">Type a stock name, symbol, or supported command. The workbench resolves the target and shows the exact command before running it.</p>
      <div class="input-row">
        <input id="smart-input" autocomplete="off" placeholder="决策 英特尔, 本周复盘, 系统状态">
        <input id="api-token" type="password" autocomplete="off" placeholder="Access token">
        <button id="parse" class="primary">Preview</button>
      </div>
      <section id="preview-section">
        <h2>Parsed Preview</h2>
        <div id="preview"><div class="notice">Start with an action or a target: 决策 英特尔, 刷新海力士决策, 本周复盘, 系统状态.</div></div>
      </section>
      <section id="form-section" hidden>
        <h2 id="form-title">Action</h2>
        <div id="form" class="form-grid"></div>
      </section>
      <section>
        <h2>Execution Result</h2>
        <div id="result"><span class="label">No command has run in this session.</span></div>
      </section>
    </main>
    <aside>
      <h2>Action Catalog</h2>
      <div id="catalog" class="actions"></div>
      <h3>Pinned</h3>
      <div id="pinned" class="history"></div>
      <h3>Recent</h3>
      <div id="recent" class="history"></div>
    </aside>
  </div>
  <script>
    const $ = (selector) => document.querySelector(selector);
    const state = { actions: [], preview: null, activeAction: null, selectedTarget: null };
    const storage = {
      recent: "command_workbench_recent",
      pinned: "command_workbench_pinned",
      token: "command_workbench_token"
    };

    $("#api-token").value = localStorage.getItem(storage.token) || "";
    $("#parse").addEventListener("click", () => parseSmartInput());
    $("#smart-input").addEventListener("keydown", (event) => {
      if (event.key === "Enter") parseSmartInput();
    });

    loadActions();
    renderHistory();

    async function loadActions() {
      const response = await fetch("/api/command-workbench/actions");
      const data = await response.json();
      state.actions = data.actions || [];
      renderCatalog();
      renderHistory();
    }

    async function parseSmartInput(extra = {}) {
      persistToken();
      setBusy(true);
      try {
        const payload = {
          text: $("#smart-input").value,
          action_id: extra.action_id || null,
          fields: extra.fields || {},
          selected_target: extra.selected_target || state.selectedTarget || null
        };
        const data = await postJson("/api/command-workbench/parse", payload);
        state.preview = data.preview;
        state.activeAction = payload.action_id;
        renderPreview(data.preview);
      } catch (error) {
        showResult({ ok: false, error: error.message });
      } finally {
        setBusy(false);
      }
    }

    async function runPreview() {
      if (!state.preview) return;
      persistToken();
      setBusy(true);
      try {
        const data = await postJson("/api/command-workbench/execute", {
          text: state.preview.raw_input || $("#smart-input").value,
          action_id: state.preview.action_id,
          fields: state.preview.fields || {},
          selected_target: state.preview.target || state.selectedTarget || null,
          confirmed: true
        });
        state.preview = data.preview || state.preview;
        showResult(data);
        addRecent(data);
      } catch (error) {
        showResult({ ok: false, error: error.message });
      } finally {
        setBusy(false);
      }
    }

    async function postJson(url, payload) {
      const response = await fetch(url, {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok && !data.preview) throw new Error(data.error || "Request failed");
      return data;
    }

    function renderCatalog() {
      const byFamily = new Map();
      for (const action of state.actions) {
        if (!byFamily.has(action.action_family)) byFamily.set(action.action_family, []);
        byFamily.get(action.action_family).push(action);
      }
      $("#catalog").innerHTML = [...byFamily.entries()].map(([family, actions]) => `
        <h3>${escapeHtml(family)}</h3>
        ${actions.map((action) => `
          <button class="action" onclick="openAction('${escapeAttr(action.id)}')">
            <strong>${escapeHtml(action.label)}</strong>
            <span>${escapeHtml(action.description)}</span>
          </button>
        `).join("")}
      `).join("");
    }

    window.openAction = function(actionId) {
      const action = state.actions.find((item) => item.id === actionId);
      if (!action) return;
      state.activeAction = action.id;
      state.selectedTarget = null;
      $("#form-section").hidden = false;
      $("#form-title").textContent = action.label;
      const fields = action.required_fields || [];
      if (!fields.length) {
        $("#form").innerHTML = `<button class="primary" onclick="submitActionForm('${escapeAttr(action.id)}')">Preview ${escapeHtml(action.label)}</button>`;
        submitActionForm(action.id);
        return;
      }
      $("#form").innerHTML = fields.map((field) => formControl(field)).join("")
        + `<button class="primary" onclick="submitActionForm('${escapeAttr(action.id)}')">Preview ${escapeHtml(action.label)}</button>`;
    };

    window.submitActionForm = function(actionId) {
      const action = state.actions.find((item) => item.id === actionId);
      const fields = {};
      for (const field of action.required_fields || []) {
        const node = document.querySelector(`[data-field="${field.id}"]`);
        fields[field.id] = node ? node.value : "";
      }
      parseSmartInput({ action_id: actionId, fields, selected_target: null });
    };

    function formControl(field) {
      if (field.type === "select") {
        return `<label class="form-row"><span class="label">${escapeHtml(field.label)}</span><select data-field="${escapeAttr(field.id)}">${(field.options || []).map((value) => `<option value="${escapeAttr(value)}">${escapeHtml(value)}</option>`).join("")}</select></label>`;
      }
      return `<label class="form-row"><span class="label">${escapeHtml(field.label)}</span><input data-field="${escapeAttr(field.id)}" placeholder="${escapeAttr(field.placeholder || "")}"></label>`;
    }

    function renderPreview(preview) {
      if (!preview) return;
      state.selectedTarget = preview.target || null;
      const runnable = preview.status === "parsed" && preview.supports_execution;
      const confirmation = preview.confirmation_required ? "Explicit confirmation required" : "No extra confirmation";
      const actionLine = preview.action ? `${preview.action.label} / ${preview.action.action_family}` : "Unrecognized";
      const targetText = preview.target ? `${preview.target.name || ""} / ${preview.target.market}.${preview.target.symbol}` : "None";
      const candidateHtml = preview.candidates && preview.candidates.length ? `
        <div class="candidates">
          ${preview.candidates.map((candidate, index) => `
            <div class="candidate">
              <div><strong>${escapeHtml(candidate.name || candidate.symbol)}</strong><br><span class="label">${escapeHtml(candidate.market)}.${escapeHtml(candidate.symbol)} confidence ${Number(candidate.confidence || 0).toFixed(2)}</span></div>
              <button onclick="chooseCandidate(${index})">Choose</button>
            </div>
          `).join("")}
        </div>` : "";
      const runButton = runnable ? `<button class="primary" onclick="runPreview()">${preview.confirmation_required ? "Confirm and Run" : "Run"}</button>` : "";
      $("#preview").innerHTML = `
        ${preview.recovery_message ? `<div class="notice">${escapeHtml(preview.recovery_message)}</div>` : ""}
        <div class="preview-grid">
          <div class="item"><span class="label">Action</span><strong>${escapeHtml(actionLine)}</strong></div>
          <div class="item"><span class="label">Target</span>${escapeHtml(targetText)}</div>
          <div class="item"><span class="label">Exact command</span><code>${escapeHtml(preview.exact_command || "None")}</code></div>
          <div class="item"><span class="label">Safety</span>${escapeHtml(preview.safety_level || "unknown")} · ${escapeHtml(confirmation)}</div>
          <div class="item"><span class="label">Parser</span>${escapeHtml(preview.parse_source || "unknown")} · confidence ${Number(preview.confidence || 0).toFixed(2)}</div>
          <div class="item"><span class="label">Expected output</span>${escapeHtml(preview.expected_output || "No output")}</div>
        </div>
        <div class="chips">
          ${(preview.data_sources || []).map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}
          <span class="chip">${escapeHtml(preview.token_cost || "Parser: 0 extra LLM tokens")}</span>
        </div>
        ${candidateHtml}
        <div style="margin-top: 12px;">${runButton}</div>
      `;
    }

    window.chooseCandidate = function(index) {
      const candidate = state.preview.candidates[index];
      state.selectedTarget = candidate;
      parseSmartInput({
        action_id: state.preview.action_id,
        fields: state.preview.fields || {},
        selected_target: candidate
      });
    };

    function showResult(data) {
      const status = data.ok ? `<span class="ok">success</span>` : `<span class="bad">failed</span>`;
      const event = data.event_id ? `Event #${data.event_id}` : "No event id";
      const exact = data.executed_command || (data.preview && data.preview.exact_command) || "";
      const message = data.message || data.error || "";
      $("#result").innerHTML = `
        <div><span class="label">Status</span>${status} · ${escapeHtml(event)}</div>
        <div><span class="label">Executed command</span><code>${escapeHtml(exact)}</code></div>
        <pre class="result">${escapeHtml(message)}</pre>
      `;
    }

    function addRecent(data) {
      if (!data.executed_command) return;
      const current = readJson(storage.recent, []);
      current.unshift({
        raw_input: data.raw_input || "",
        exact_command: data.executed_command,
        ok: Boolean(data.ok),
        event_id: data.event_id || null,
        timestamp: new Date().toISOString()
      });
      localStorage.setItem(storage.recent, JSON.stringify(current.slice(0, 10)));
      renderHistory();
    }

    function renderHistory() {
      const recent = readJson(storage.recent, []);
      const pinnedIds = readJson(storage.pinned, []);
      const pinned = state.actions.filter((action) => action.pinned || pinnedIds.includes(action.id));
      $("#recent").innerHTML = recent.length ? recent.map((item) => `
        <button onclick="rerunRecent('${escapeAttr(item.exact_command)}')">${escapeHtml(item.exact_command)}<br><span class="label">${escapeHtml(item.timestamp)} · ${item.ok ? "ok" : "failed"}</span></button>
      `).join("") : `<span class="label">No recent executions.</span>`;
      $("#pinned").innerHTML = pinned.length ? pinned.map((action) => `
        <button onclick="openAction('${escapeAttr(action.id)}')">${escapeHtml(action.label)}<br><span class="label">${escapeHtml(action.action_family)}</span></button>
      `).join("") : `<span class="label">No pinned actions.</span>`;
    }

    window.rerunRecent = function(command) {
      $("#smart-input").value = command;
      state.selectedTarget = null;
      parseSmartInput();
    };

    function authHeaders() {
      const token = $("#api-token").value.trim();
      return token ? { "Authorization": `Bearer ${token}` } : {};
    }
    function persistToken() {
      const token = $("#api-token").value.trim();
      if (token) localStorage.setItem(storage.token, token);
    }
    function setBusy(busy) {
      $("#parse").disabled = busy;
    }
    function readJson(key, fallback) {
      try { return JSON.parse(localStorage.getItem(key) || ""); } catch { return fallback; }
    }
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
    }
    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, "&#96;");
    }
  </script>
</body>
</html>"""


def _parse_deterministic(context: ParseContext) -> dict[str, Any]:
    text = _strip_punctuation(context.raw_input)
    exact = _parse_exact_command(text)
    if exact is not None:
        return exact

    unsupported_weekly = {"周复盘数据源诊断", "weekly source diagnostics", "weekly diagnostics"}
    if text.lower() in unsupported_weekly:
        return _preview_from_action(
            ParseContext(
                raw_input=context.raw_input,
                action_id="weekly_source_diagnostics",
                parse_source="deterministic_alias",
                confidence=0.98,
                recovery_message="Weekly source diagnostics are not available as a registered router command yet. Use This week review or Previous week review.",
            )
        )

    if text in WEEKLY_REVIEW_COMMANDS:
        return _preview_from_action(_action_context(context, "weekly_current", "deterministic_alias", 0.99))
    if text in {"上周复盘", "复盘 上周", "上星期复盘", "上个星期复盘"}:
        return _preview_from_action(_action_context(context, "weekly_previous", "deterministic_alias", 0.99))
    if text in SYSTEM_STATUS_COMMANDS:
        return _preview_from_action(_action_context(context, "system_status", "deterministic_alias", 0.99))
    if text in RECENT_ERRORS_COMMANDS:
        return _preview_from_action(_action_context(context, "recent_errors", "deterministic_alias", 0.99))
    if text in WORKER_STATUS_COMMANDS:
        return _preview_from_action(_action_context(context, "worker_status", "deterministic_alias", 0.99))
    if text in PORTFOLIO_POSITION_COMMANDS:
        return _preview_from_action(_action_context(context, "portfolio_positions", "deterministic_alias", 0.99))
    if text in PORTFOLIO_ANALYSIS_COMMANDS:
        return _preview_from_action(_action_context(context, "portfolio_analysis", "deterministic_alias", 0.99))
    if text in RESEARCH_JOB_LIST_COMMANDS:
        return _preview_from_action(_action_context(context, "research_list_jobs", "deterministic_alias", 0.99))
    if text in RESEARCH_JOB_CREATE_COMMANDS:
        return _preview_from_action(_action_context(context, "research_portfolio_jobs", "deterministic_alias", 0.99))

    service = _extract_service_log(text)
    if service:
        return _preview_from_action(
            _action_context(
                context,
                "service_logs",
                "deterministic_alias",
                0.95,
                fields={"service": service},
            )
        )

    history_target = _match_first(
        text,
        [
            r"^查看\s*(.+?)\s*决策历史$",
            r"^(.+?)\s*决策历史$",
        ],
    )
    if history_target:
        return _preview_from_action(
            _action_context(
                context,
                "decision_history",
                "deterministic_alias",
                0.92,
                fields={"stock": history_target},
                recovery_message="Decision history is not implemented in the current router. You can run the Level 1 decision card instead.",
            )
        )

    refresh_target = _match_first(
        text,
        [
            r"^刷新\s*(.+?)\s*决策$",
            r"^刷新\s*(.+?)\s*研究草稿$",
        ],
    )
    if refresh_target:
        return _preview_from_action(
            _action_context(
                context,
                "decision_refresh",
                "deterministic_alias",
                0.95,
                fields={"stock": refresh_target},
            )
        )

    research_target = _match_first(
        text,
        [
            r"^创建\s*(.+?)\s*研究任务$",
            r"^create research job\s+(.+)$",
        ],
        flags=re.IGNORECASE,
    )
    if research_target:
        return _preview_from_action(
            _action_context(
                context,
                "research_create_stock_job",
                "deterministic_alias",
                0.93,
                fields={"stock": research_target},
            )
        )

    decision_target = _match_first(
        text,
        [
            r"^决策\s*(.+)$",
            r"^decision\s+(.+)$",
            r"^看一下\s*(.+)$",
            r"^分析一下\s*(.+)$",
            r"^分析\s*(.+)$",
            r"^(.+?)\s*(?:怎么看|如何看|怎么样|咋样)$",
        ],
        flags=re.IGNORECASE,
    )
    if decision_target:
        return _preview_from_action(
            _action_context(
                context,
                "decision_card",
                "deterministic_alias",
                0.94,
                fields={"stock": decision_target},
            )
        )

    return _recovery(
        "unsupported",
        raw_input=context.raw_input,
        recovery_message="I cannot run this as a website command yet. Try one of the supported actions below.",
    )


def _parse_exact_command(text: str) -> dict[str, Any] | None:
    stock_exact = _match_first(
        text,
        [
            r"^(?:决策|decision)\s+(.+)$",
            r"^(?:查看股票|inspect|stock inspect)\s+(.+)$",
            r"^(?:分析|analyze)\s+(.+)$",
        ],
        flags=re.IGNORECASE,
    )
    if stock_exact:
        parsed = _parse_stock_target(stock_exact)
        if parsed is not None:
            symbol, market = parsed
            return _preview_from_action(
                ParseContext(
                    raw_input=text,
                    action_id="decision_card",
                    selected_target=_candidate(symbol=symbol, market=market, name="", confidence=1.0, source="exact"),
                    parse_source="exact_command",
                    confidence=1.0,
                )
            )

    detail_exact = _match_first(
        text,
        [r"^(?:分析详情|查看详情|股票详情|inspect detail|analyze detail)\s+(.+)$"],
        flags=re.IGNORECASE,
    )
    if detail_exact:
        parsed = _parse_stock_target(detail_exact)
        if parsed is not None:
            symbol, market = parsed
            return _preview_from_action(
                ParseContext(
                    raw_input=text,
                    action_id="decision_detail",
                    selected_target=_candidate(symbol=symbol, market=market, name="", confidence=1.0, source="exact"),
                    parse_source="exact_command",
                    confidence=1.0,
                )
            )

    draft_exact = _match_first(text, [r"^(?:研究草稿|图谱草稿|research draft)\s+(.+)$"], flags=re.IGNORECASE)
    if draft_exact:
        parsed = _parse_stock_target(draft_exact)
        if parsed is not None:
            symbol, market = parsed
            return _preview_from_action(
                ParseContext(
                    raw_input=text,
                    action_id="decision_refresh",
                    selected_target=_candidate(symbol=symbol, market=market, name="", confidence=1.0, source="exact"),
                    parse_source="exact_command",
                    confidence=1.0,
                )
            )

    job_exact = _match_first(text, [r"^(?:创建研究任务|create research job)\s+(.+)$"], flags=re.IGNORECASE)
    if job_exact:
        parsed = _parse_stock_target(job_exact)
        if parsed is not None:
            symbol, market = parsed
            return _preview_from_action(
                ParseContext(
                    raw_input=text,
                    action_id="research_create_stock_job",
                    selected_target=_candidate(symbol=symbol, market=market, name="", confidence=1.0, source="exact"),
                    parse_source="exact_command",
                    confidence=1.0,
                )
            )

    simple_exact = {
        "本周复盘": "weekly_current",
        "weekly review": "weekly_current",
        "上周复盘": "weekly_previous",
        "复盘 上周": "weekly_previous",
        "我的持仓": "portfolio_positions",
        "当前持仓": "portfolio_positions",
        "持仓分析": "portfolio_analysis",
        "组合分析": "portfolio_analysis",
        "查看研究任务": "research_list_jobs",
        "列出研究任务": "research_list_jobs",
        "创建持仓研究任务": "research_portfolio_jobs",
        "系统状态": "system_status",
        "status": "system_status",
        "最近错误": "recent_errors",
        "worker状态": "worker_status",
    }
    action_id = simple_exact.get(text) or simple_exact.get(text.lower())
    if action_id:
        return _preview_from_action(ParseContext(raw_input=text, action_id=action_id, parse_source="exact_command", confidence=1.0))

    service = _match_first(text, [r"^(?:服务日志|查看服务日志|service logs?)\s+([a-zA-Z0-9_-]+)$"], flags=re.IGNORECASE)
    if service:
        return _preview_from_action(
            ParseContext(
                raw_input=text,
                action_id="service_logs",
                fields={"service": _normalize_service(service)},
                parse_source="exact_command",
                confidence=1.0,
            )
        )
    return None


def _preview_from_action(context: ParseContext) -> dict[str, Any]:
    action = ACTIONS.get(context.action_id or "")
    if action is None:
        return _recovery(
            "unsupported",
            raw_input=context.raw_input,
            recovery_message="This action is not registered in the command workbench.",
        )

    fields = dict(context.fields)
    target = _clean_selected_target(context.selected_target)
    candidates: list[dict[str, Any]] = []
    status = "parsed"
    exact_command = ""
    recovery_message = context.recovery_message
    confidence = context.confidence or 0.9

    needs_stock = any(field.get("type") == "stock" for field in action.required_fields)
    if needs_stock and target is None:
        stock_query = str(fields.get("stock") or "").strip()
        if not stock_query:
            status = "needs_field"
            recovery_message = "Choose a stock target before running this action."
        else:
            candidates = resolve_stock_candidates(stock_query)
            if not candidates:
                status = "needs_entity"
                recovery_message = f'I recognized {action.label}, but could not resolve "{stock_query}" to a stock. Enter a symbol such as US.INTC or 000660 KR.'
            elif len(candidates) == 1:
                target = candidates[0]
                confidence = min(confidence, float(target.get("confidence") or confidence))
            else:
                status = "ambiguous_entity"
                recovery_message = f'I found multiple matches for "{stock_query}". Choose one target before running the command.'

    if action.id == "service_logs":
        service = _normalize_service(str(fields.get("service") or ""))
        fields["service"] = service
        if not service:
            status = "needs_field"
            recovery_message = "Choose a service before reading logs."

    if not action.supports_execution:
        status = "unsupported"
        recovery_message = recovery_message or "I cannot run this as a website command yet. Try one of the supported actions below."

    if status == "parsed":
        exact_command = _build_exact_command(action, target=target, fields=fields)
        if not exact_command:
            status = "unsupported"
            recovery_message = "No exact command is registered for this action."

    confirmation_required = action.confirmation_required or (target is not None and float(target.get("confidence") or 1.0) < 0.9)
    return {
        "status": status,
        "raw_input": context.raw_input,
        "action_id": action.id,
        "action": action.public_dict(),
        "intent": action.id,
        "confidence": round(float(confidence), 3),
        "parse_source": context.parse_source,
        "fields": fields,
        "target": target,
        "entities": [target] if target else [],
        "candidates": candidates if status == "ambiguous_entity" else [],
        "candidate_commands": [_candidate_command(action, candidate, fields) for candidate in candidates],
        "exact_command": exact_command,
        "safety_level": action.safety_level,
        "confirmation_required": bool(confirmation_required),
        "supports_execution": action.supports_execution,
        "side_effects": action.side_effects,
        "data_sources": list(action.data_sources),
        "expected_output": action.expected_output,
        "result_type": action.result_type,
        "recovery_message": recovery_message,
        "token_cost": _token_cost(context.parse_source),
        "downstream_cost": _downstream_cost(action),
    }


def resolve_stock_candidates(query: str) -> list[dict[str, Any]]:
    cleaned = _clean_stock_text(query)
    if not cleaned:
        return []

    candidates: list[dict[str, Any]] = []
    parsed = _parse_stock_target(cleaned)
    if parsed is not None:
        symbol, market = parsed
        candidates.append(_candidate(symbol=symbol, market=market, name="", confidence=1.0, source="symbol"))

    alias_key = cleaned.lower()
    if alias_key in ALIAS_STOCKS:
        for item in ALIAS_STOCKS[alias_key]:
            candidates.append(_candidate(source="alias", **item))

    try:
        for row in repository.resolve_stock_reference(cleaned):
            candidates.append(
                _candidate(
                    symbol=str(row.get("symbol") or ""),
                    market=str(row.get("market") or ""),
                    name=str(row.get("name") or ""),
                    confidence=0.94,
                    source="stock_profile",
                )
            )
    except Exception:
        pass

    return _dedupe_candidates(candidates)


def _parse_with_llm(raw_input: str) -> dict[str, Any] | None:
    candidates = _alias_candidates_in_text(raw_input)
    proposal = propose_command_workbench_parse_with_openai(
        raw_input,
        registry_summary=[
            {
                "id": action.id,
                "family": action.action_family,
                "label": action.label,
                "aliases": list(action.aliases),
                "required_fields": action.required_fields,
                "supports_execution": action.supports_execution,
            }
            for action in ACTIONS.values()
        ],
        entity_candidates=candidates,
    )
    if not proposal:
        return None
    action_id = str(proposal.get("action_id") or "")
    if action_id not in ACTIONS:
        return None
    fields = proposal.get("fields") if isinstance(proposal.get("fields"), dict) else {}
    confidence = float(proposal.get("confidence") or 0.6)
    return _preview_from_action(
        ParseContext(
            raw_input=raw_input,
            action_id=action_id,
            fields=fields,
            parse_source="llm_proposal",
            confidence=min(confidence, 0.84),
            recovery_message=str(proposal.get("reason") or ""),
        )
    )


def _alias_candidates_in_text(raw_input: str) -> list[dict[str, Any]]:
    lower = raw_input.lower()
    candidates: list[dict[str, Any]] = []
    for alias, items in ALIAS_STOCKS.items():
        if alias in lower:
            candidates.extend(_candidate(source="alias", **item) for item in items)
    return _dedupe_candidates(candidates)


def _candidate(
    *,
    symbol: str,
    market: str,
    name: str,
    confidence: float,
    source: str,
) -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "market": market.upper(),
        "name": name,
        "confidence": confidence,
        "source": source,
        "canonical": f"{market.upper()}.{symbol.upper()}",
    }


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in candidates:
        symbol = str(candidate.get("symbol") or "").upper()
        market = str(candidate.get("market") or "").upper()
        if not symbol or not market:
            continue
        key = (market, symbol)
        existing = by_key.get(key)
        if existing is None or float(candidate.get("confidence") or 0) > float(existing.get("confidence") or 0):
            by_key[key] = {**candidate, "symbol": symbol, "market": market, "canonical": f"{market}.{symbol}"}
        elif not existing.get("name") and candidate.get("name"):
            existing["name"] = candidate["name"]
    return sorted(by_key.values(), key=lambda item: (-float(item.get("confidence") or 0), item["market"], item["symbol"]))[:6]


def _build_exact_command(action: CommandAction, *, target: dict[str, Any] | None, fields: dict[str, Any]) -> str:
    if target:
        values = {
            "symbol": str(target.get("symbol") or "").upper(),
            "market": str(target.get("market") or "").upper(),
        }
        values["target"] = f"{values['market']}.{values['symbol']}"
        return action.template.format(**values)
    if action.id == "service_logs":
        return action.template.format(service=_normalize_service(str(fields.get("service") or "")))
    return action.template


def _candidate_command(action: CommandAction, candidate: dict[str, Any], fields: dict[str, Any]) -> str:
    return _build_exact_command(action, target=candidate, fields=fields)


def _parse_stock_target(value: str) -> tuple[str, str] | None:
    cleaned = _clean_stock_text(value)
    market_symbol_match = re.fullmatch(r"([A-Za-z]{1,5})\.([A-Za-z0-9._-]+)", cleaned)
    if market_symbol_match:
        market, symbol = market_symbol_match.groups()
        return symbol.upper(), market.upper()
    symbol_market_match = re.fullmatch(r"(\S+)\s+(\S+)", cleaned)
    if symbol_market_match:
        symbol, market = symbol_market_match.groups()
        if re.fullmatch(r"[A-Za-z]{1,5}", market):
            return symbol.upper(), market.upper()
    return None


def _clean_selected_target(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    symbol = str(value.get("symbol") or "").strip()
    market = str(value.get("market") or "").strip()
    if not symbol or not market:
        return None
    return _candidate(
        symbol=symbol,
        market=market,
        name=str(value.get("name") or ""),
        confidence=float(value.get("confidence") or 1.0),
        source=str(value.get("source") or "selected"),
    )


def _extract_service_log(text: str) -> str | None:
    match = re.fullmatch(r"(?:查看\s*)?([a-zA-Z0-9_-]+|钉钉)\s*日志", text, flags=re.IGNORECASE)
    if match:
        return _normalize_service(match.group(1))
    return None


def _normalize_service(value: str) -> str:
    cleaned = value.strip()
    return SERVICE_ALIASES.get(cleaned.lower(), cleaned)


def _action_context(
    base: ParseContext,
    action_id: str,
    parse_source: str,
    confidence: float,
    *,
    fields: dict[str, Any] | None = None,
    recovery_message: str = "",
) -> ParseContext:
    return ParseContext(
        raw_input=base.raw_input,
        action_id=action_id,
        fields=fields or {},
        selected_target=base.selected_target,
        parse_source=parse_source,
        confidence=confidence,
        recovery_message=recovery_message,
    )


def _recovery(status: str, *, raw_input: str, recovery_message: str) -> dict[str, Any]:
    return {
        "status": status,
        "raw_input": raw_input,
        "action_id": None,
        "action": None,
        "intent": None,
        "confidence": 0.0,
        "parse_source": "recovery",
        "fields": {},
        "target": None,
        "entities": [],
        "candidates": [],
        "candidate_commands": [],
        "exact_command": "",
        "safety_level": "unsupported",
        "confirmation_required": False,
        "supports_execution": False,
        "side_effects": "No action is executed.",
        "data_sources": [],
        "expected_output": "",
        "result_type": "recovery",
        "recovery_message": recovery_message,
        "token_cost": "Parser: 0 extra LLM tokens",
        "downstream_cost": "No downstream command cost.",
    }


def _match_first(text: str, patterns: list[str], *, flags: re.RegexFlag = re.RegexFlag(0)) -> str | None:
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=flags)
        if match:
            return _clean_stock_text(match.group(1))
    return None


def _clean_stock_text(value: str) -> str:
    cleaned = _strip_punctuation(value)
    cleaned = re.sub(r"^(?:一下|下|这个|这只|这家公司|股票)\s*", "", cleaned)
    cleaned = re.sub(r"\s*(?:这个|这只|这家公司|股票)$", "", cleaned)
    return cleaned.strip()


def _strip_punctuation(value: str) -> str:
    return value.strip().strip("？?。.!！,， ")


def _token_cost(parse_source: str) -> str:
    if parse_source == "llm_proposal":
        return "Parser: estimated 400-1,500 LLM tokens."
    return "Parser: 0 extra LLM tokens."


def _downstream_cost(action: CommandAction) -> str:
    if action.id in {"portfolio_analysis", "decision_detail", "decision_refresh", "research_create_stock_job", "research_portfolio_jobs"}:
        return "Downstream command may use LLM tokens or enqueue async work depending on provider settings."
    return "No expected downstream LLM cost from the workbench itself."
