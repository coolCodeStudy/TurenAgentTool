from __future__ import annotations

from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.weekly_review import build_weekly_review, save_weekly_review_report


MAX_BODY_BYTES = 64 * 1024
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class WeeklyReviewWebHandler(BaseHTTPRequestHandler):
    server_version = "InvestmentKnowledgeWeeklyReviewWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/weekly-review"}:
            self._write_html(HTTPStatus.OK, render_weekly_review_workbench_html())
            return
        if parsed.path == "/health":
            self._write_json(HTTPStatus.OK, {"ok": True})
            return
        if parsed.path == "/api/weekly-review":
            if not self._authorized():
                return
            self._handle_weekly_review_api(parse_qs(parsed.query), save=False)
            return
        if parsed.path == "/api/candidate-insights":
            if not self._authorized():
                return
            self._handle_candidate_insights(parse_qs(parsed.query))
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._authorized():
            return
        if parsed.path == "/api/weekly-review/save":
            payload = self._read_json_body()
            if payload is None:
                return
            self._handle_weekly_review_api(payload, save=True)
            return

        candidate_match = re.fullmatch(r"/api/candidate-insights/(\d+)/(confirm|reject)", parsed.path)
        if candidate_match:
            self._handle_candidate_decision(candidate_id=int(candidate_match.group(1)), action=candidate_match.group(2))
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_weekly_review_api(self, payload: dict[str, Any], *, save: bool) -> None:
        try:
            start, end = _resolve_request_range(payload)
            run_schema()
            result = build_weekly_review(start=start, end=end, save=False)
            saved_report = None
            markdown = _first_query_value(payload, "markdown") or result.markdown
            if save:
                saved_report = save_weekly_review_report(context=result.context, markdown=markdown)
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return

        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "context": result.context,
                "markdown": markdown,
                "saved_report": saved_report,
            },
        )

    def _handle_candidate_insights(self, query: dict[str, Any]) -> None:
        status = _first_query_value(query, "status") or "pending"
        if status == "all":
            status = None
        target_type = _first_query_value(query, "target_type") or None
        try:
            run_schema()
            rows = repository.list_candidate_insights(status=status, target_type=target_type)
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return
        self._write_json(HTTPStatus.OK, {"ok": True, "items": rows})

    def _handle_candidate_decision(self, candidate_id: int, action: str) -> None:
        try:
            run_schema()
            if action == "confirm":
                result = repository.confirm_candidate_insight(candidate_id)
            else:
                result = repository.reject_candidate_insight(candidate_id)
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return
        self._write_json(HTTPStatus.OK, {"ok": True, "result": result})

    def _authorized(self) -> bool:
        token = get_config().weekly_review_web_token
        if not token:
            return True
        authorization = self.headers.get("Authorization")
        web_token = self.headers.get("X-Weekly-Review-Token")
        supplied = ""
        if authorization and authorization.startswith("Bearer "):
            supplied = authorization.removeprefix("Bearer ").strip()
        elif web_token:
            supplied = web_token.strip()
        if hmac.compare_digest(supplied, token):
            return True
        self._write_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
        return False

    def _read_json_body(self) -> dict[str, Any] | None:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            return {}
        try:
            length = int(content_length)
        except ValueError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid Content-Length"})
            return None
        if length > MAX_BODY_BYTES:
            self._write_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "request too large"})
            return None
        raw_body = self.rfile.read(length)
        if not raw_body:
            return {}
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid JSON body"})
            return None
        if not isinstance(payload, dict):
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "JSON body must be an object"})
            return None
        return payload

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, status: HTTPStatus, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def render_weekly_review_workbench_html() -> str:
    start, end = _default_week_range()
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InvestmentKnowledge 周复盘</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #20242a;
      --muted: #657180;
      --line: #dce2ea;
      --accent: #1769aa;
      --good: #126a3a;
      --bad: #a33a32;
      --warn: #966200;
      --chip: #eef3f8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    .shell {{
      display: grid;
      grid-template-columns: 232px minmax(0, 1fr) 220px;
      min-height: 100vh;
    }}
    .sidebar {{
      border-right: 1px solid var(--line);
      background: #ffffff;
      padding: 22px 16px;
      position: sticky;
      top: 0;
      height: 100vh;
    }}
    .brand {{
      font-size: 18px;
      font-weight: 700;
      margin: 0 0 20px;
    }}
    .nav {{
      display: grid;
      gap: 4px;
    }}
    .nav a {{
      color: var(--muted);
      text-decoration: none;
      padding: 9px 10px;
      border-radius: 6px;
      font-size: 14px;
    }}
    .nav a.active {{
      color: var(--accent);
      background: #e8f1fa;
      font-weight: 650;
    }}
    main {{
      padding: 22px 24px 42px;
      min-width: 0;
    }}
    .topbar {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 16px;
      align-items: end;
      margin-bottom: 16px;
    }}
    h1 {{
      font-size: 26px;
      margin: 0 0 8px;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .controls {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    input, select, button {{
      font: inherit;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
    }}
    input {{ padding: 0 8px; }}
    button {{
      padding: 0 12px;
      cursor: pointer;
      font-weight: 650;
    }}
    button.primary {{
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }}
    button:disabled {{ opacity: .55; cursor: not-allowed; }}
    .status-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(110px, 1fr));
      gap: 8px;
      margin-bottom: 16px;
    }}
    .status {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      min-height: 66px;
    }}
    .status strong {{
      display: block;
      font-size: 13px;
      margin-bottom: 5px;
    }}
    .status span {{
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 16px;
      margin-bottom: 14px;
    }}
    section h2 {{
      margin: 0 0 12px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      text-align: left;
      padding: 9px 8px;
      border-bottom: 1px solid #edf1f5;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 650;
      white-space: nowrap;
    }}
    .money {{ text-align: right; white-space: nowrap; }}
    .pos {{ color: var(--good); }}
    .neg {{ color: var(--bad); }}
    .chips {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }}
    .chip {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--chip);
      padding: 5px 9px;
      font-size: 12px;
      color: var(--muted);
    }}
    .story-list {{
      display: grid;
      gap: 8px;
      margin: 0;
      padding-left: 18px;
    }}
    .markdown {{
      min-height: 180px;
      width: 100%;
      resize: vertical;
      line-height: 1.5;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
    }}
    .aside {{
      border-left: 1px solid var(--line);
      background: #ffffff;
      padding: 22px 16px;
      position: sticky;
      top: 0;
      height: 100vh;
    }}
    .aside a {{
      display: block;
      color: var(--muted);
      text-decoration: none;
      font-size: 13px;
      padding: 6px 0;
    }}
    .notice {{
      border-left: 3px solid var(--warn);
      background: #fff8e8;
      padding: 10px 12px;
      font-size: 13px;
      color: #6b4b00;
      margin-bottom: 14px;
    }}
    .empty {{
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 1100px) {{
      .shell {{ grid-template-columns: 180px minmax(0, 1fr); }}
      .aside {{ display: none; }}
      .status-grid {{ grid-template-columns: repeat(3, minmax(110px, 1fr)); }}
    }}
    @media (max-width: 760px) {{
      .shell {{ display: block; }}
      .sidebar {{ position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }}
      main {{ padding: 16px; }}
      .topbar {{ grid-template-columns: 1fr; }}
      .controls {{ justify-content: flex-start; }}
      .status-grid {{ grid-template-columns: 1fr 1fr; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <p class="brand">InvestmentKnowledge</p>
      <nav class="nav" aria-label="主导航">
        <a class="active" href="/weekly-review">本周复盘</a>
        <a href="#holdings">当前持仓</a>
        <a href="#markdown">交易复盘</a>
        <a href="#candidates">心得确认</a>
        <a href="#markdown">研究队列</a>
        <a href="#source-status">数据源状态</a>
      </nav>
    </aside>
    <main>
      <div class="topbar">
        <div>
          <h1>本周复盘</h1>
          <p class="subtitle">基于交易记录、账户快照、当前持仓、IPO 和知识库生成草稿。</p>
        </div>
        <div class="controls">
          <input id="start" type="date" value="{start.isoformat()}" aria-label="开始日期">
          <input id="end" type="date" value="{end.isoformat()}" aria-label="结束日期">
          <input id="api-token" type="password" placeholder="访问令牌" aria-label="访问令牌">
          <button id="generate" class="primary">生成复盘</button>
          <button id="save">保存报告</button>
        </div>
      </div>
      <div id="message" class="notice">尚未生成。选择日期后点击生成复盘。</div>
      <div id="source-status" class="status-grid" aria-live="polite"></div>
      <section id="highlights"><h2>1. 高光时刻</h2><div data-slot="highlights"></div></section>
      <section id="blowups"><h2>2. 炸裂时刻</h2><div data-slot="blowups"></div></section>
      <section id="indexes"><h2>3. 指数</h2><div class="empty">指数数据源未接入，本周不做指数归因。</div></section>
      <section id="story"><h2>4. 整体故事</h2><div data-slot="story"></div></section>
      <section id="next-week"><h2>5. 下周展望</h2><div data-slot="next-week"></div></section>
      <section id="holdings"><h2>6. 当前持仓分析</h2><div class="chips"><select id="market-filter"><option value="">全部市场</option></select><select id="status-filter"><option value="">全部状态</option><option value="待处理">待处理</option><option value="补研究">补研究</option><option value="高波动">高波动</option><option value="历史拖累">历史拖累</option></select></div><div data-slot="holdings"></div></section>
      <section id="markdown"><h2>报告草稿</h2><textarea id="markdown-text" class="markdown" spellcheck="false"></textarea></section>
      <section id="candidates"><h2>候选心得</h2><div data-slot="candidates" class="empty">保存报告后可在这里确认或拒绝候选心得。</div></section>
    </main>
    <aside class="aside" aria-label="复盘目录">
      <a href="#highlights">1. 高光时刻</a>
      <a href="#blowups">2. 炸裂时刻</a>
      <a href="#indexes">3. 指数</a>
      <a href="#story">4. 整体故事</a>
      <a href="#next-week">5. 下周展望</a>
      <a href="#holdings">6. 当前持仓分析</a>
      <a href="#source-status">数据源状态</a>
    </aside>
  </div>
  <script>
    const state = {{ context: null, markdown: "", holdings: [] }};
    const $ = (selector) => document.querySelector(selector);
    const slot = (name) => document.querySelector(`[data-slot="${{name}}"]`);
    const message = $("#message");

    $("#generate").addEventListener("click", () => loadReview(false));
    $("#save").addEventListener("click", () => loadReview(true));
    $("#market-filter").addEventListener("change", renderHoldings);
    $("#status-filter").addEventListener("change", renderHoldings);
    $("#api-token").value = localStorage.getItem("weekly_review_web_token") || "";

    async function loadReview(save) {{
      setBusy(true);
      message.textContent = save ? "正在保存正式复盘..." : "正在生成复盘草稿...";
      try {{
        const payload = {{ start: $("#start").value, end: $("#end").value, markdown: $("#markdown-text").value }};
        const headers = authHeaders();
        const response = save
          ? await fetch("/api/weekly-review/save", {{ method: "POST", headers: {{ ...headers, "Content-Type": "application/json" }}, body: JSON.stringify(payload) }})
          : await fetch(`/api/weekly-review?start=${{encodeURIComponent(payload.start)}}&end=${{encodeURIComponent(payload.end)}}`, {{ headers }});
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || "生成失败");
        persistToken();
        state.context = data.context;
        state.markdown = data.markdown || "";
        state.holdings = data.context.holdings_table || [];
        renderAll();
        message.textContent = save && data.saved_report
          ? `已保存正式复盘：review_reports #${{data.saved_report.id}}`
          : "草稿已生成，保存前请检查故事、下周展望和数据缺口。";
        if (save) loadCandidates();
      }} catch (error) {{
        message.textContent = `生成失败：${{error.message}}`;
      }} finally {{
        setBusy(false);
      }}
    }}

    async function loadCandidates() {{
      try {{
        const response = await fetch("/api/candidate-insights?status=pending", {{ headers: authHeaders() }});
        const data = await response.json();
        if (data.ok) renderCandidates(data.items || []);
      }} catch (error) {{
        slot("candidates").textContent = `候选心得读取失败：${{error.message}}`;
      }}
    }}

    async function decideCandidate(id, action) {{
      const response = await fetch(`/api/candidate-insights/${{id}}/${{action}}`, {{ method: "POST", headers: authHeaders() }});
      const data = await response.json();
      if (!data.ok) {{
        message.textContent = `候选心得操作失败：${{data.error || "unknown"}}`;
        return;
      }}
      loadCandidates();
    }}

    function renderAll() {{
      renderStatus(state.context.source_status || {{}});
      slot("highlights").innerHTML = rankedTable(state.context.highlights || [], true);
      slot("blowups").innerHTML = rankedTable(state.context.blowups || [], false);
      slot("story").innerHTML = storyBlock(state.context.story || {{}}, state.context.warnings || []);
      slot("next-week").innerHTML = nextWeekTable(state.context.next_week || []);
      $("#markdown-text").value = state.markdown;
      renderMarketOptions();
      renderHoldings();
    }}

    function renderStatus(sourceStatus) {{
      const entries = [
        ["交易记录", sourceStatus.trades],
        ["持仓快照", sourceStatus.account_snapshots],
        ["当前持仓", sourceStatus.positions],
        ["港股新股", sourceStatus.ipo],
        ["指数", sourceStatus.indexes],
        ["外部事件", sourceStatus.events],
      ];
      $("#source-status").innerHTML = entries.map(([label, item]) => `
        <div class="status"><strong>${{escapeHtml(label)}}</strong><span>${{escapeHtml(statusText(item))}}</span></div>
      `).join("");
    }}

    function rankedTable(items, positive) {{
      if (!items.length) return `<div class="empty">${{positive ? "暂未识别到明显高光。" : "暂未识别到明显拖累。"}}</div>`;
      return `<table><thead><tr><th>标的</th><th>类型</th><th class="money">金额</th><th>发生了什么</th><th>复盘问题</th></tr></thead><tbody>
        ${{items.map((item) => {{
          const amount = item.amount ?? item.pl_val_delta;
          return `<tr><td>${{escapeHtml(item.name)}} ${{escapeHtml(item.code)}}</td><td>${{escapeHtml(item.type)}}</td><td class="money ${{moneyClass(amount)}}">${{formatMoney(amount, item.currency)}}</td><td>${{escapeHtml(item.movement)}} / ${{escapeHtml(item.confidence)}}</td><td>${{escapeHtml(item.review_question)}}</td></tr>`;
        }}).join("")}}
      </tbody></table>`;
    }}

    function storyBlock(story, warnings) {{
      const items = [
        ["主线", story.mainline || "待观察"],
        ["加速因素", "本周暂未接入外部事件源，不做新闻/社媒/公告归因。"],
        ["负向信号", story.negative_signals || "待观察"],
        ["和我组合的关系", story.portfolio_relation || "待观察"],
        ["下周验证点", story.next_validation || "待观察"],
      ];
      const warningHtml = warnings.length ? `<div class="notice">${{escapeHtml(warnings.slice(0, 4).join("；"))}}</div>` : "";
      return `${{warningHtml}}<ul class="story-list">${{items.map(([k, v]) => `<li><strong>${{escapeHtml(k)}}：</strong>${{escapeHtml(v)}}</li>`).join("")}}</ul>`;
    }}

    function nextWeekTable(items) {{
      if (!items.length) return `<div class="empty">暂无下周事项。</div>`;
      return `<table><thead><tr><th>类型</th><th>事项</th><th>为什么重要</th><th>需要决定</th></tr></thead><tbody>
        ${{items.map((item) => `<tr><td>${{escapeHtml(item.type)}}</td><td>${{escapeHtml(item.item)}}</td><td>${{escapeHtml(item.reason)}}</td><td>${{escapeHtml(item.needs_decision)}}</td></tr>`).join("")}}
      </tbody></table>`;
    }}

    function renderMarketOptions() {{
      const current = $("#market-filter").value;
      const markets = [...new Set(state.holdings.map((row) => row.market).filter(Boolean))].sort();
      $("#market-filter").innerHTML = `<option value="">全部市场</option>${{markets.map((market) => `<option value="${{escapeAttr(market)}}">${{escapeHtml(market)}}</option>`).join("")}}`;
      $("#market-filter").value = markets.includes(current) ? current : "";
    }}

    function renderHoldings() {{
      const market = $("#market-filter").value;
      const status = $("#status-filter").value;
      const rows = state.holdings.filter((row) => (!market || row.market === market) && (!status || String(row.status || "").includes(status)));
      if (!rows.length) {{
        slot("holdings").innerHTML = `<div class="empty">当前没有符合条件的持仓。</div>`;
        return;
      }}
      slot("holdings").innerHTML = `<table><thead><tr><th>市场</th><th>标的</th><th>主题</th><th class="money">市值</th><th class="money">盈亏</th><th>状态</th><th>知识库观点</th><th>下周节奏</th></tr></thead><tbody>
        ${{rows.map((row) => `<tr><td>${{escapeHtml(row.market)}}</td><td>${{escapeHtml(row.name)}} ${{escapeHtml(row.code)}}</td><td>${{escapeHtml(row.theme)}}</td><td class="money">${{formatMoney(row.market_val, row.currency)}}</td><td class="money ${{moneyClass(row.current_pl_val)}}">${{formatMoney(row.current_pl_val, row.currency)}}${{ratioText(row.current_pl_ratio)}}</td><td>${{escapeHtml(row.status)}}</td><td>${{escapeHtml(row.knowledge_note)}}</td><td>${{escapeHtml(row.next_step)}}</td></tr>`).join("")}}
      </tbody></table>`;
    }}

    function renderCandidates(items) {{
      if (!items.length) {{
        slot("candidates").innerHTML = `<div class="empty">暂无待确认候选心得。</div>`;
        return;
      }}
      slot("candidates").innerHTML = `<table><thead><tr><th>心得</th><th>标签</th><th>操作</th></tr></thead><tbody>
        ${{items.map((item) => `<tr><td>${{escapeHtml(item.insight)}}</td><td>${{escapeHtml((item.tags || []).join("、"))}}</td><td><button onclick="decideCandidate(${{item.id}}, 'confirm')">确认</button> <button onclick="decideCandidate(${{item.id}}, 'reject')">拒绝</button></td></tr>`).join("")}}
      </tbody></table>`;
    }}

    function setBusy(busy) {{
      $("#generate").disabled = busy;
      $("#save").disabled = busy;
    }}
    function authHeaders() {{
      const token = $("#api-token").value.trim();
      return token ? {{ "Authorization": `Bearer ${{token}}` }} : {{}};
    }}
    function persistToken() {{
      const token = $("#api-token").value.trim();
      if (token) localStorage.setItem("weekly_review_web_token", token);
    }}
    function statusText(item) {{
      if (!item) return "missing";
      const status = item.status || "unknown";
      const count = item.count === undefined ? "" : `，${{item.count}} 条`;
      const reason = item.reason ? `，${{item.reason}}` : "";
      return `${{status}}${{count}}${{reason}}`;
    }}
    function formatMoney(value, currency) {{
      const number = Number(value || 0);
      return `${{number.toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }})}}${{currency && currency !== "UNKNOWN" ? " " + currency : ""}}`;
    }}
    function ratioText(value) {{
      if (value === null || value === undefined || value === "") return "";
      const number = Math.abs(Number(value)) > 1 ? Number(value) : Number(value) * 100;
      return ` / ${{number.toFixed(2)}}%`;
    }}
    function moneyClass(value) {{ return Number(value || 0) < 0 ? "neg" : "pos"; }}
    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[char]));
    }}
    function escapeAttr(value) {{ return escapeHtml(value).replace(/`/g, "&#96;"); }}
  </script>
</body>
</html>"""


def _resolve_request_range(payload: dict[str, Any]) -> tuple[date, date]:
    start_text = _first_query_value(payload, "start")
    end_text = _first_query_value(payload, "end")
    if start_text and end_text:
        start = date.fromisoformat(str(start_text).replace("/", "-"))
        end = date.fromisoformat(str(end_text).replace("/", "-"))
        if end < start:
            start, end = end, start
        return start, end
    return _default_week_range()


def _default_week_range() -> tuple[date, date]:
    today = datetime.now(SHANGHAI_TZ).date()
    start = today - timedelta(days=today.weekday())
    return start, today


def _first_query_value(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def main() -> None:
    config = get_config()
    server = ThreadingHTTPServer((config.weekly_review_web_host, config.weekly_review_web_port), WeeklyReviewWebHandler)
    print(
        f"Weekly Review Web listening on {config.weekly_review_web_host}:{config.weekly_review_web_port}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
