from __future__ import annotations

from dataclasses import dataclass
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
from investment_knowledge_mcp.weekly_review_sources import diagnose_default_index_provider


MAX_BODY_BYTES = 1024 * 1024
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class BadRequest(ValueError):
    pass


@dataclass(frozen=True)
class WeekScope:
    label: str
    start: date
    end: date
    is_future: bool


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
            self._handle_weekly_review_read(parse_qs(parsed.query))
            return
        if parsed.path == "/api/weekly-review/diagnostics/indexes":
            if not self._authorized():
                return
            self._handle_weekly_review_index_diagnostics(parse_qs(parsed.query))
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
            self._handle_weekly_review_save(payload)
            return
        if parsed.path == "/api/weekly-review/generate":
            payload = self._read_json_body()
            if payload is None:
                return
            self._handle_weekly_review_generate(payload)
            return
        if parsed.path == "/api/weekly-review/refresh":
            payload = self._read_json_body()
            if payload is None:
                return
            self._handle_weekly_review_refresh(payload)
            return

        candidate_match = re.fullmatch(r"/api/candidate-insights/(\d+)/(confirm|reject)", parsed.path)
        if candidate_match:
            self._handle_candidate_decision(candidate_id=int(candidate_match.group(1)), action=candidate_match.group(2))
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_weekly_review_read(self, payload: dict[str, Any]) -> None:
        try:
            scope = resolve_week_input(payload)
            run_schema()
            report = repository.get_weekly_review_report(scope.start.isoformat(), scope.end.isoformat())
        except BadRequest as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return

        self._write_json(HTTPStatus.OK, _weekly_review_response(scope=scope, report=report))

    def _handle_weekly_review_generate(self, payload: dict[str, Any]) -> None:
        run_id = None
        try:
            scope = resolve_week_input(payload)
            if scope.is_future:
                raise BadRequest("future_week_generation_disabled")
            run_schema()
            existing_report = repository.get_weekly_review_report(scope.start.isoformat(), scope.end.isoformat())
            if existing_report:
                response = _weekly_review_response(scope=scope, report=existing_report)
                response["already_exists"] = True
                self._write_json(HTTPStatus.OK, response)
                return
            run = repository.create_weekly_review_run(
                scope.start.isoformat(),
                scope.end.isoformat(),
                trigger="generate",
            )
            run_id = run["id"]
            result = build_weekly_review(start=scope.start, end=scope.end, save=False, run_id=run_id)
            token_usage = _dict_payload_value(payload, "token_usage")
            saved_report = save_weekly_review_report(
                context=result.context,
                markdown=result.markdown,
                token_usage=token_usage,
            )
            repository.finish_weekly_review_run(
                run_id,
                status="succeeded",
                token_usage=token_usage,
                budget_warnings=saved_report.get("budget_warnings") or [],
                source_summary=result.context.get("external_source_summary") or {},
            )
        except BadRequest as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            if run_id is not None:
                _safe_finish_run(run_id, error=str(exc))
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return

        self._write_json(
            HTTPStatus.OK,
            _weekly_review_response(scope=scope, report=saved_report, saved_report=saved_report),
        )

    def _handle_weekly_review_refresh(self, payload: dict[str, Any]) -> None:
        run_id = None
        try:
            if not _truthy_payload_value(payload, "force"):
                raise BadRequest("force_required")
            scope = resolve_week_input(payload)
            run_schema()
            run = repository.create_weekly_review_run(
                scope.start.isoformat(),
                scope.end.isoformat(),
                trigger="force_refresh",
            )
            run_id = run["id"]
            result = build_weekly_review(
                start=scope.start,
                end=scope.end,
                save=False,
                force_refresh=True,
                run_id=run_id,
            )
            token_usage = _dict_payload_value(payload, "token_usage")
            saved_report = save_weekly_review_report(
                context=result.context,
                markdown=result.markdown,
                refreshed=True,
                token_usage=token_usage,
            )
            repository.finish_weekly_review_run(
                run_id,
                status="succeeded",
                token_usage=token_usage,
                budget_warnings=saved_report.get("budget_warnings") or [],
                source_summary=result.context.get("external_source_summary") or {},
            )
        except BadRequest as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            if run_id is not None:
                _safe_finish_run(run_id, error=str(exc))
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return

        self._write_json(
            HTTPStatus.OK,
            _weekly_review_response(scope=scope, report=saved_report, saved_report=saved_report),
        )

    def _handle_weekly_review_save(self, payload: dict[str, Any]) -> None:
        try:
            scope = resolve_week_input(payload)
            run_schema()
            source_report = repository.get_weekly_review_report(scope.start.isoformat(), scope.end.isoformat())
            context = _dict_payload_value(payload, "context")
            if context is None and source_report is not None:
                context = source_report.get("portfolio_snapshot") or {}
            if not context:
                raise BadRequest("missing_report_context")
            markdown = _first_query_value(payload, "markdown")
            if not markdown and source_report is not None:
                markdown = source_report.get("summary")
            if not markdown:
                raise BadRequest("missing_markdown")
            saved_report = save_weekly_review_report(
                context=context,
                markdown=markdown,
                token_usage=_dict_payload_value(payload, "token_usage"),
            )
        except Exception as exc:
            if isinstance(exc, BadRequest):
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return

        self._write_json(
            HTTPStatus.OK,
            _weekly_review_response(scope=scope, report=saved_report, saved_report=saved_report),
        )

    def _handle_weekly_review_index_diagnostics(self, query: dict[str, Any]) -> None:
        try:
            scope = resolve_week_input(query)
            diagnostics = diagnose_default_index_provider(start=scope.start, end=scope.end)
        except BadRequest as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return
        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "week": _week_scope_payload(scope),
                "diagnostics": diagnostics,
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
    scope = _default_week_scope()
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
    button.danger {{
      border-color: var(--bad);
      color: var(--bad);
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
          <p class="subtitle">按自然周读取、生成和保存复盘；打开页面不会自动重跑数据源。</p>
        </div>
        <div class="controls">
          <button id="prev-week-button" type="button">上一周</button>
          <button id="this-week" type="button">本周</button>
          <button id="next-week-button" type="button">下一周</button>
          <input id="week" type="week" value="{scope.label}" aria-label="选择周">
          <input id="api-token" type="password" placeholder="访问令牌" aria-label="访问令牌">
          <button id="generate" class="primary">生成周复盘</button>
          <button id="refresh" class="danger">强制刷新</button>
          <button id="save">保存正式报告</button>
        </div>
      </div>
      <div id="message" class="notice">正在读取本周复盘状态...</div>
      <div id="source-status" class="status-grid" aria-live="polite"></div>
      <section id="highlights"><h2>1. 高光时刻</h2><div data-slot="highlights"></div></section>
      <section id="blowups"><h2>2. 炸裂时刻</h2><div data-slot="blowups"></div></section>
      <section id="indexes"><h2>3. 指数与外部环境</h2><div data-slot="indexes"></div></section>
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
    const initialWeek = "{scope.label}";
    const state = {{ status: "loading", report: null, context: null, markdown: "", holdings: [], tokenSummary: null, budgetWarnings: [], runs: [], sourceRecords: [] }};
    const $ = (selector) => document.querySelector(selector);
    const slot = (name) => document.querySelector(`[data-slot="${{name}}"]`);
    const message = $("#message");

    $("#generate").addEventListener("click", generateReview);
    $("#refresh").addEventListener("click", refreshReview);
    $("#save").addEventListener("click", saveReview);
    $("#week").addEventListener("change", readReview);
    $("#prev-week-button").addEventListener("click", () => shiftWeek(-1));
    $("#this-week").addEventListener("click", () => {{ $("#week").value = initialWeek; readReview(); }});
    $("#next-week-button").addEventListener("click", () => shiftWeek(1));
    $("#market-filter").addEventListener("change", renderHoldings);
    $("#status-filter").addEventListener("change", renderHoldings);
    $("#api-token").value = localStorage.getItem("weekly_review_web_token") || "";
    readReview();

    async function readReview() {{
      setBusy(true);
      message.textContent = "正在读取周复盘状态...";
      try {{
        const headers = authHeaders();
        const data = await fetchJson(`/api/weekly-review?week=${{encodeURIComponent($("#week").value)}}`, {{ headers }});
        persistToken();
        applyReviewResponse(data);
        renderAll();
        message.textContent = state.status === "missing"
          ? "本周尚未生成。确认需要后点击生成周复盘。"
          : `已读取周复盘：review_reports #${{state.report.id}}`;
      }} catch (error) {{
        message.textContent = `读取失败：${{error.message}}`;
      }} finally {{
        setBusy(false);
      }}
    }}

    async function generateReview() {{
      if ($("#week").value > initialWeek) {{
        message.textContent = "未来周默认不生成交易复盘。";
        return;
      }}
      setBusy(true);
      message.textContent = "正在生成周复盘草稿...";
      try {{
        const data = await fetchJson("/api/weekly-review/generate", {{
          method: "POST",
          headers: {{ ...authHeaders(), "Content-Type": "application/json" }},
          body: JSON.stringify({{ week: $("#week").value }})
        }});
        persistToken();
        applyReviewResponse(data);
        renderAll();
        message.textContent = data.already_exists
          ? `本周已有周复盘，没有重新生成。`
          : `周复盘已生成：review_reports #${{state.report.id}}`;
      }} catch (error) {{
        message.textContent = `生成失败：${{error.message}}`;
      }} finally {{
        setBusy(false);
      }}
    }}

    async function refreshReview() {{
      const ok = window.confirm(`强制刷新 ${{$("#week").value}}？\\n\\n系统会重新读取交易、持仓、指数、宏观、新闻/主题和机会列表，并重新生成周复盘内容。\\n如果已有正式报告，刷新结果会直接覆盖正式报告。`);
      if (!ok) return;
      setBusy(true);
      message.textContent = "正在强制刷新周复盘...";
      try {{
        const data = await fetchJson("/api/weekly-review/refresh", {{
          method: "POST",
          headers: {{ ...authHeaders(), "Content-Type": "application/json" }},
          body: JSON.stringify({{ week: $("#week").value, force: true }})
        }});
        persistToken();
        applyReviewResponse(data);
        renderAll();
        message.textContent = `强制刷新已保存：review_reports #${{state.report.id}}`;
      }} catch (error) {{
        message.textContent = `刷新失败：${{error.message}}`;
      }} finally {{
        setBusy(false);
      }}
    }}

    async function saveReview() {{
      setBusy(true);
      message.textContent = "正在保存正式复盘...";
      try {{
        const data = await fetchJson("/api/weekly-review/save", {{
          method: "POST",
          headers: {{ ...authHeaders(), "Content-Type": "application/json" }},
          body: JSON.stringify({{ week: $("#week").value, markdown: $("#markdown-text").value, context: state.context }})
        }});
        persistToken();
        applyReviewResponse(data);
        renderAll();
        message.textContent = `已保存正式复盘：review_reports #${{data.saved_report.id}}`;
        loadCandidates();
      }} catch (error) {{
        message.textContent = `保存失败：${{error.message}}`;
      }} finally {{
        setBusy(false);
      }}
    }}

    async function fetchJson(url, options) {{
      const response = await fetch(url, options);
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "请求失败");
      return data;
    }}

    function applyReviewResponse(data) {{
      state.status = data.status || "missing";
      state.report = data.report || null;
      state.context = data.context || null;
      state.markdown = data.markdown || "";
      state.holdings = state.context ? (state.context.holdings_table || []) : [];
      state.tokenSummary = data.token_summary || null;
      state.budgetWarnings = data.budget_warnings || [];
      state.runs = data.runs || [];
      state.sourceRecords = data.source_records || [];
      if (data.week && data.week.label) $("#week").value = data.week.label;
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
      renderStatus(state.context ? (state.context.source_status || {{}}) : {{}});
      if (!state.context) {{
        slot("highlights").innerHTML = `<div class="empty">尚未生成。</div>`;
        slot("blowups").innerHTML = `<div class="empty">尚未生成。</div>`;
        slot("indexes").innerHTML = `<div class="empty">尚未生成。</div>`;
        slot("story").innerHTML = `<div class="empty">尚未生成。</div>`;
        slot("next-week").innerHTML = `<div class="empty">尚未生成。</div>`;
      }} else {{
        slot("highlights").innerHTML = rankedTable(state.context.highlights || [], true);
        slot("blowups").innerHTML = rankedTable(state.context.blowups || [], false);
        slot("indexes").innerHTML = externalEnvironmentBlock(state.context);
        slot("story").innerHTML = storyBlock(state.context.story || {{}}, state.context.warnings || []);
        slot("next-week").innerHTML = nextWeekTable(state.context.next_week || []);
      }}
      $("#markdown-text").value = state.markdown;
      renderMarketOptions();
      renderHoldings();
      updateButtons();
    }}

    function renderStatus(sourceStatus) {{
      const entries = [
        ["Review week", {{ status: $("#week").value }}],
        ["Report status", {{ status: statusLabel(state.status) }}],
        ["Generated at", {{ status: state.report ? state.report.generated_at || "unknown" : "none" }}],
        ["Last refreshed", {{ status: state.report ? state.report.refreshed_at || "none" : "none" }}],
        ["Sources", {{ status: sourceSummary(sourceStatus) }}],
        ["LLM", {{ status: llmSummary(state.report ? state.report.token_usage : null) }}],
        ["Token spend", {{ status: tokenSpendSummary(state.tokenSummary) }}],
        ["Budget", {{ status: budgetSummary(state.budgetWarnings) }}],
        ["Runs", {{ status: runSummary(state.runs) }}],
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
        ["外部环境", story.external_context || "外部环境源未配置。"],
        ["负向信号", story.negative_signals || "待观察"],
        ["和我组合的关系", story.portfolio_relation || "待观察"],
        ["下周验证点", story.next_validation || "待观察"],
      ];
      const warningHtml = warnings.length ? `<div class="notice">${{escapeHtml(warnings.slice(0, 4).join("；"))}}</div>` : "";
      return `${{warningHtml}}<ul class="story-list">${{items.map(([k, v]) => `<li><strong>${{escapeHtml(k)}}：</strong>${{escapeHtml(v)}}</li>`).join("")}}</ul>`;
    }}

    function externalEnvironmentBlock(context) {{
      const indexes = context.index_summary || [];
      const macroEvents = context.macro_events || [];
      const newsThemes = context.news_themes || [];
      const opportunities = context.opportunity_items || [];
      const html = [
        indexThermometer(indexes),
        compactExternalList("宏观", macroEvents),
        compactExternalList("新闻/主题", newsThemes),
        compactExternalList("机会列表", opportunities),
      ].filter(Boolean).join("");
      const warnings = state.budgetWarnings.length
        ? `<div class="notice">${{escapeHtml(state.budgetWarnings.map((item) => item.message || item.type).join("；"))}}</div>`
        : "";
      return warnings + html;
    }}

    function indexThermometer(items) {{
      if (!items.length) return `<div class="empty">指数数据源未接入，本周不做指数归因。</div>`;
      const groups = groupByMarket(items);
      const rows = items.map((item) => {{
        const move = Number(item.weekly_change_pct);
        const proxy = item.instrument_type === "proxy_etf" ? "ETF proxy" : "index";
        return `<tr>
          <td>${{escapeHtml(marketLabel(item.market))}}</td>
          <td>${{escapeHtml(item.name || item.code || "未命名")}} <span class="chip">${{escapeHtml(proxy)}}</span></td>
          <td class="money ${{moneyClass(move)}}">${{escapeHtml(item.weekly_change || formatPct(move))}}</td>
          <td>${{escapeHtml(compactDailyMove(item.max_daily_move) || "n/a")}}</td>
          <td>${{escapeHtml(indexRead(item))}}</td>
        </tr>`;
      }}).join("");
      return `<div class="chips">${{groups.map((group) => `<span class="chip">${{escapeHtml(group)}}</span>`).join("")}}</div>
        <table><thead><tr><th>市场</th><th>指数</th><th class="money">周变化</th><th>最大单日</th><th>怎么读</th></tr></thead><tbody>${{rows}}</tbody></table>`;
    }}

    function compactExternalList(title, items) {{
      if (!items.length) return "";
      return `<h3>${{escapeHtml(title)}}</h3><ul class="story-list">${{items.slice(0, 5).map((item) => `<li><strong>${{escapeHtml(item.name || item.title || item.theme || item.symbol || "未命名")}}：</strong>${{escapeHtml(item.summary || item.note || item.change || item.reason || "")}}</li>`).join("")}}</ul>`;
    }}

    function groupByMarket(items) {{
      const order = ["US", "HK", "CN"];
      const byMarket = new Map();
      for (const item of items) {{
        const market = item.market || "OTHER";
        const value = Number(item.weekly_change_pct);
        if (!byMarket.has(market)) byMarket.set(market, []);
        if (!Number.isNaN(value)) byMarket.get(market).push(value);
      }}
      const rank = (market) => order.includes(market) ? order.indexOf(market) : 99;
      return [...byMarket.entries()].sort((a, b) => rank(a[0]) - rank(b[0])).map(([market, values]) => {{
        const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
        return `${{marketLabel(market)}} ${{marketDirection(avg)}}`;
      }});
    }}

    function indexRead(item) {{
      const relevance = item.portfolio_relevance || "";
      const note = item.instrument_type === "proxy_etf" ? "代理口径。" : "";
      return `${{note}}${{relevance}}`;
    }}

    function compactDailyMove(value) {{
      return String(value || "").replace(/\\b(\\d{{4}}-\\d{{2}}-\\d{{2}})\\s+00:00:00\\b/g, "$1");
    }}

    function marketLabel(market) {{
      if (market === "US") return "美股";
      if (market === "HK") return "港股";
      if (market === "CN" || market === "SH" || market === "SZ") return "A股";
      return market || "其他";
    }}

    function marketDirection(value) {{
      if (value === null || Number.isNaN(value)) return "数据不足";
      if (value >= 1) return "偏强";
      if (value > 0) return "小幅偏强";
      if (value <= -1) return "承压";
      return "震荡偏弱";
    }}

    function formatPct(value) {{
      if (value === null || Number.isNaN(value)) return "N/A";
      return `${{value > 0 ? "+" : ""}}${{value.toFixed(2)}}%`;
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
      $("#refresh").disabled = busy;
      $("#save").disabled = busy;
    }}
    function updateButtons() {{
      const future = $("#week").value > initialWeek;
      $("#generate").disabled = state.status !== "missing" || future;
      $("#refresh").disabled = future;
      $("#save").disabled = !state.context;
    }}
    function shiftWeek(step) {{
      $("#week").stepUp(step);
      readReview();
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
    function statusLabel(status) {{
      return ({{ missing: "Missing", existing: "Existing", loading: "Loading" }})[status] || status || "Unknown";
    }}
    function sourceSummary(sourceStatus) {{
      if (!sourceStatus || !Object.keys(sourceStatus).length) return "none";
      return Object.entries(sourceStatus).map(([key, item]) => `${{key}}:${{item.status || "unknown"}}`).join(" / ");
    }}
    function llmSummary(tokenUsage) {{
      if (!tokenUsage || !Object.keys(tokenUsage).length) return "Not used";
      const model = tokenUsage.model || tokenUsage.provider || "recorded";
      const input = tokenUsage.input_tokens === undefined ? "?" : tokenUsage.input_tokens;
      const output = tokenUsage.output_tokens === undefined ? "?" : tokenUsage.output_tokens;
      return `${{model}} in:${{input}} out:${{output}}`;
    }}
    function tokenSpendSummary(summary) {{
      if (!summary) return "Not recorded";
      const tokens = summary.total_tokens === undefined ? 0 : summary.total_tokens;
      const cost = summary.estimated_cost === null || summary.estimated_cost === undefined ? "" : ` / cost:${{summary.estimated_cost}}`;
      return `${{tokens}} tokens${{cost}}`;
    }}
    function budgetSummary(warnings) {{
      if (!warnings || !warnings.length) return "No warnings";
      return warnings.map((item) => item.message || item.type || "warning").join(" / ");
    }}
    function runSummary(runs) {{
      if (!runs || !runs.length) return "No runs";
      const latest = runs[0];
      return `${{latest.trigger || "run"}}:${{latest.status || "unknown"}}`;
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
    scope = resolve_week_input(payload)
    return scope.start, scope.end


def resolve_week_input(payload: dict[str, Any]) -> WeekScope:
    today = datetime.now(SHANGHAI_TZ).date()
    current_week_start = today - timedelta(days=today.weekday())
    week_text = _first_query_value(payload, "week")
    week_start_text = _first_query_value(payload, "week_start")
    date_text = _first_query_value(payload, "date")
    start_text = _first_query_value(payload, "start")
    end_text = _first_query_value(payload, "end")
    if week_text:
        start = _parse_week_label(week_text)
    elif week_start_text:
        start = _parse_iso_date(week_start_text)
        if start.weekday() != 0:
            raise BadRequest("invalid_week_start")
    elif date_text:
        selected = _parse_iso_date(date_text)
        start = selected - timedelta(days=selected.weekday())
    elif start_text:
        selected = _parse_iso_date(start_text)
        start = selected - timedelta(days=selected.weekday())
    elif end_text:
        selected = _parse_iso_date(end_text)
        start = selected - timedelta(days=selected.weekday())
    else:
        start = current_week_start
    end = start + timedelta(days=6)
    return WeekScope(
        label=_format_week_label(start),
        start=start,
        end=end,
        is_future=start > current_week_start,
    )


def _default_week_range() -> tuple[date, date]:
    scope = _default_week_scope()
    return scope.start, scope.end


def _default_week_scope() -> WeekScope:
    today = datetime.now(SHANGHAI_TZ).date()
    start = today - timedelta(days=today.weekday())
    return WeekScope(label=_format_week_label(start), start=start, end=start + timedelta(days=6), is_future=False)


def _parse_week_label(value: str) -> date:
    cleaned = value.strip()
    match = re.fullmatch(r"(\d{4})-W(\d{2})", cleaned)
    if not match:
        parsed_date = _parse_iso_date(cleaned)
        return parsed_date - timedelta(days=parsed_date.weekday())
    year = int(match.group(1))
    week = int(match.group(2))
    try:
        return date.fromisocalendar(year, week, 1)
    except ValueError as exc:
        raise BadRequest("invalid_week") from exc


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip().replace("/", "-"))
    except ValueError as exc:
        raise BadRequest("invalid_date") from exc


def _format_week_label(week_start: date) -> str:
    iso = week_start.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _weekly_review_response(
    *,
    scope: WeekScope,
    report: dict[str, Any] | None,
    saved_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = "existing" if report else "missing"
    context = report.get("portfolio_snapshot") if report else None
    markdown = report.get("summary") if report else ""
    source_records = repository.list_weekly_review_sources(scope.start.isoformat(), scope.end.isoformat())
    runs = repository.list_weekly_review_runs(scope.start.isoformat(), scope.end.isoformat(), limit=5)
    return {
        "ok": True,
        "status": status,
        "week": {
            "label": scope.label,
            "start": scope.start.isoformat(),
            "end": scope.end.isoformat(),
            "is_future": scope.is_future,
        },
        "context": context,
        "markdown": markdown,
        "report": report,
        "saved_report": saved_report,
        "source_records": source_records,
        "runs": runs,
        "token_summary": repository.summarize_weekly_review_token_usage(),
        "budget_warnings": report.get("budget_warnings") if report else [],
    }


def _safe_finish_run(run_id: int, *, error: str) -> None:
    try:
        repository.finish_weekly_review_run(run_id, status="failed", error=error)
    except Exception:
        return


def _dict_payload_value(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = payload.get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, dict) else None


def _truthy_payload_value(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


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
