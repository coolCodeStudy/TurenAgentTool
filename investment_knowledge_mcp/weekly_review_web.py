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
from investment_knowledge_mcp.command_router import handle_command
from investment_knowledge_mcp.command_workbench import (
    command_workbench_auth_error_payload,
    execution_blocker,
    list_workbench_actions,
    parse_workbench_command,
    render_command_workbench_html,
)
from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.frontend_shell import ShellPage, render_app_shell
from investment_knowledge_mcp.repository import record_command_event
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
        if parsed.path == "/command":
            self._write_html(HTTPStatus.OK, render_command_workbench_html())
            return
        if parsed.path == "/api/command-workbench/actions":
            self._write_json(HTTPStatus.OK, {"ok": True, "actions": list_workbench_actions()})
            return
        if parsed.path == "/api/weekly-review":
            if not self._authorized():
                return
            self._handle_weekly_review_read(parse_qs(parsed.query))
            return
        if parsed.path == "/api/candidate-insights":
            if not self._authorized():
                return
            self._handle_candidate_insights(parse_qs(parsed.query))
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/api/command-workbench/parse", "/api/command-workbench/execute"}:
            if not self._authorized_for_command_workbench():
                return
            payload = self._read_json_body()
            if payload is None:
                return
            if parsed.path == "/api/command-workbench/parse":
                self._handle_workbench_parse(payload)
            else:
                self._handle_workbench_execute(payload)
            return

        if not self._authorized():
            return
        if parsed.path == "/api/weekly-review/generate":
            payload = self._read_json_body()
            if payload is None:
                return
            self._handle_weekly_review_generate(payload, force=False)
            return
        if parsed.path == "/api/weekly-review/refresh":
            payload = self._read_json_body()
            if payload is None:
                return
            self._handle_weekly_review_generate(payload, force=True)
            return
        if parsed.path == "/api/weekly-review/save":
            payload = self._read_json_body()
            if payload is None:
                return
            self._handle_weekly_review_save(payload)
            return

        candidate_match = re.fullmatch(r"/api/candidate-insights/(\d+)/(confirm|reject)", parsed.path)
        if candidate_match:
            self._handle_candidate_decision(candidate_id=int(candidate_match.group(1)), action=candidate_match.group(2))
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_workbench_parse(self, payload: dict[str, Any]) -> None:
        raw_input = str(payload.get("text") or "").strip()
        action_id = _clean_optional_text(payload.get("action_id"))
        fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
        selected_target = payload.get("selected_target") if isinstance(payload.get("selected_target"), dict) else None
        preview = parse_workbench_command(
            raw_input,
            action_id=action_id,
            fields=fields,
            selected_target=selected_target,
        )
        event = _record_workbench_event(
            command=raw_input or f"[action] {action_id or 'unknown'}",
            ok=preview.get("status") == "parsed",
            message=f"parse status={preview.get('status')} action={preview.get('action_id')}",
            source="weekly-review-web.command-workbench.parse",
        )
        self._write_json(HTTPStatus.OK, {"ok": True, "preview": preview, "event_id": event.get("id") if event else None})

    def _handle_workbench_execute(self, payload: dict[str, Any]) -> None:
        raw_input = str(payload.get("text") or "").strip()
        action_id = _clean_optional_text(payload.get("action_id"))
        fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
        selected_target = payload.get("selected_target") if isinstance(payload.get("selected_target"), dict) else None
        confirmed = bool(payload.get("confirmed"))
        preview = parse_workbench_command(
            raw_input,
            action_id=action_id,
            fields=fields,
            selected_target=selected_target,
        )
        blocker = execution_blocker(preview, confirmed=confirmed)
        if blocker:
            self._write_json(HTTPStatus.CONFLICT, {"ok": False, "error": blocker, "preview": preview})
            return

        exact_command = str(preview.get("exact_command") or "").strip()
        try:
            run_schema()
            result = handle_command(exact_command)
            event = record_command_event(
                command=exact_command,
                ok=result.ok,
                message=result.message,
                sender=_clean_optional_text(payload.get("sender")),
                source="weekly-review-web.command-workbench.execute",
            )
        except Exception as exc:
            message = f"command failed: {exc}"
            event = _record_workbench_event(
                command=exact_command,
                ok=False,
                message=message,
                source="weekly-review-web.command-workbench.execute",
            )
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "ok": False,
                    "error": message,
                    "preview": preview,
                    "event_id": event.get("id") if event else None,
                    "executed_command": exact_command,
                    "raw_input": raw_input,
                },
            )
            return

        status = HTTPStatus.OK if result.ok else HTTPStatus.BAD_REQUEST
        self._write_json(
            status,
            {
                "ok": result.ok,
                "message": result.message,
                "preview": preview,
                "event_id": event.get("id"),
                "executed_command": exact_command,
                "raw_input": raw_input,
            },
        )

    def _handle_weekly_review_read(self, payload: dict[str, Any]) -> None:
        try:
            start, end = _resolve_week_request(payload)
            run_schema()
            report = repository.get_review_report("weekly", start.isoformat(), end.isoformat())
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": _public_weekly_error(exc)})
            return

        if report:
            self._write_json(HTTPStatus.OK, _report_response(report, start=start, end=end, status="existing"))
            return

        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "status": "missing",
                "week": _week_payload(start, end),
                "context": _empty_week_context(start, end),
                "markdown": "",
                "saved_report": None,
            },
        )

    def _handle_weekly_review_generate(self, payload: dict[str, Any], *, force: bool) -> None:
        try:
            start, end = _resolve_week_request(payload)
            if force and not _truthy(_first_query_value(payload, "force")):
                self._write_json(
                    HTTPStatus.CONFLICT,
                    {"ok": False, "error": "请先确认强制刷新。本操作会重新读取数据并覆盖本周自动生成内容。"},
                )
                return
            run_schema()
            existing = repository.get_review_report("weekly", start.isoformat(), end.isoformat())
            if existing and not force:
                self._write_json(
                    HTTPStatus.OK,
                    _report_response(existing, start=start, end=end, status="existing", already_exists=True),
                )
                return
            result = build_weekly_review(start=start, end=end, save=True)
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": _public_weekly_error(exc)})
            return

        status = "refreshed" if force else "generated"
        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "status": status,
                "week": _week_payload(start, end),
                "context": result.context,
                "markdown": result.markdown,
                "saved_report": result.saved_report,
            },
        )

    def _handle_weekly_review_save(self, payload: dict[str, Any]) -> None:
        try:
            start, end = _resolve_week_request(payload)
            markdown = _first_query_value(payload, "markdown")
            if not markdown:
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "请先生成或填写报告内容，再保存。"})
                return
            run_schema()
            existing = repository.get_review_report("weekly", start.isoformat(), end.isoformat())
            context = payload.get("context") if isinstance(payload.get("context"), dict) else None
            if context is None and existing:
                context = existing.get("portfolio_snapshot") if isinstance(existing.get("portfolio_snapshot"), dict) else None
            if context is None:
                self._write_json(HTTPStatus.CONFLICT, {"ok": False, "error": "请先生成本周复盘，再保存报告。"})
                return
            context = _normalize_report_context(context, start=start, end=end)
            saved_report = save_weekly_review_report(context=context, markdown=markdown)
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": _public_weekly_error(exc, saving=True)})
            return

        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "status": "saved",
                "week": _week_payload(start, end),
                "context": context,
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

    def _authorized_for_command_workbench(self) -> bool:
        config = get_config()
        supplied = _authorization_token(self.headers.get("Authorization"))
        command_token = self.headers.get("X-Command-Token")
        weekly_token = self.headers.get("X-Weekly-Review-Token")
        candidates = [
            (supplied, config.command_api_token),
            (command_token, config.command_api_token),
            (supplied, config.weekly_review_web_token),
            (weekly_token, config.weekly_review_web_token),
        ]
        if any(
            expected and supplied_token and hmac.compare_digest(supplied_token.strip(), expected)
            for supplied_token, expected in candidates
        ):
            return True
        if not config.command_api_token and not config.weekly_review_web_token:
            self._write_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "command workbench token is not configured"})
            return False
        self._write_json(HTTPStatus.UNAUTHORIZED, command_workbench_auth_error_payload())
        return False

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
    page_css = """
    .weekly-page {
      --bg: var(--app-bg);
      --panel: var(--app-surface);
      --ink: var(--app-ink);
      --muted: var(--app-muted);
      --line: var(--app-line);
      --accent: var(--app-accent);
      --good: var(--app-good);
      --bad: var(--app-bad);
      --warn: var(--app-warn);
      --chip: var(--app-surface-muted);
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
    .weekly-page {{
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
    .token-field {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
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
    .attribution-grid {{
      display: grid;
      gap: 10px;
    }}
    .attribution-card {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      overflow: hidden;
    }}
    .attribution-card summary {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      padding: 12px;
      cursor: pointer;
      list-style: none;
    }}
    .attribution-card summary::-webkit-details-marker {{ display: none; }}
    .attribution-title {{
      min-width: 0;
      font-weight: 700;
    }}
    .attribution-meta {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
    }}
    .badge {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--chip);
      padding: 5px 8px;
      font-size: 12px;
      color: var(--muted);
      white-space: nowrap;
    }}
    .badge.rumor {{ color: var(--warn); border-color: #e7c069; background: #fff8e8; }}
    .attribution-body {{
      border-top: 1px solid #edf1f5;
      padding: 12px;
    }}
    .candidate {{
      border-left: 3px solid var(--line);
      padding: 8px 10px;
      margin-bottom: 8px;
      background: #fbfcfd;
    }}
    .candidate strong {{ display: block; margin-bottom: 4px; }}
    .candidate p {{
      margin: 4px 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .gap-list {{
      margin: 8px 0 0;
      padding-left: 18px;
      color: var(--muted);
      font-size: 13px;
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
      background: #ffffff;
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
      .aside {{ display: none; }}
      .status-grid {{ grid-template-columns: repeat(3, minmax(110px, 1fr)); }}
    }}
    @media (max-width: 760px) {{
      .sidebar {{ position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }}
      .topbar {{ grid-template-columns: 1fr; }}
      .controls {{ justify-content: flex-start; }}
      .status-grid {{ grid-template-columns: 1fr 1fr; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
    """
    main_html = f"""
      <div class="topbar">
        <div class="controls">
          <button id="prev-week" type="button">上一周</button>
          <button id="this-week" type="button">本周</button>
          <input id="week-date" type="date" value="{start.isoformat()}" aria-label="复盘周">
          <label class="token-field"><span>访问令牌</span><input id="api-token" type="password" autocomplete="off" placeholder="用于保存和私有访问" aria-label="访问令牌"></label>
          <button id="generate" class="primary">生成复盘</button>
          <button id="refresh">强制刷新</button>
          <button id="save">保存报告</button>
        </div>
      </div>
      <div id="message" class="app-notice notice" role="status" aria-live="polite">正在读取本周复盘状态。</div>
      <div id="source-status" class="status-grid" aria-live="polite"></div>
      <section id="highlights"><h2>1. 高光时刻</h2><div data-slot="highlights"></div></section>
      <section id="blowups"><h2>2. 炸裂时刻</h2><div data-slot="blowups"></div></section>
      <section id="indexes"><h2>3. 指数</h2><div data-slot="indexes"></div></section>
      <section id="story"><h2>4. 整体故事</h2><div data-slot="story"></div></section>
      <section id="next-week"><h2>5. 下周展望</h2><div data-slot="next-week"></div></section>
      <section id="holdings"><h2>6. 当前持仓分析</h2><div class="chips"><select id="market-filter"><option value="">全部市场</option></select><select id="status-filter"><option value="">全部状态</option><option value="待处理">待处理</option><option value="补研究">补研究</option><option value="高波动">高波动</option><option value="历史拖累">历史拖累</option></select></div><div data-slot="holdings"></div></section>
      <section id="attribution"><h2>7. 持仓归因卡</h2><div data-slot="attribution"></div></section>
      <section id="markdown"><h2>报告草稿</h2><textarea id="markdown-text" class="markdown" spellcheck="false"></textarea></section>
      <section id="candidates"><h2>候选心得</h2><div data-slot="candidates" class="empty">保存报告后可在这里确认或拒绝候选心得。</div></section>
    """
    aside_html = """
    <div class="app-panel aside" aria-label="复盘目录">
      <a href="#highlights">1. 高光时刻</a>
      <a href="#blowups">2. 炸裂时刻</a>
      <a href="#indexes">3. 指数</a>
      <a href="#story">4. 整体故事</a>
      <a href="#next-week">5. 下周展望</a>
      <a href="#holdings">6. 当前持仓分析</a>
      <a href="#attribution">7. 持仓归因卡</a>
      <a href="#source-status">数据源状态</a>
    </div>
    """
    page_js = """
  <script>
    const state = {{ context: null, markdown: "", holdings: [], week: null, reportStatus: "loading" }};
    const $ = (selector) => document.querySelector(selector);
    const slot = (name) => document.querySelector(`[data-slot="${{name}}"]`);
    const message = $("#message");

    $("#generate").addEventListener("click", () => loadReview("generate"));
    $("#refresh").addEventListener("click", () => loadReview("refresh"));
    $("#save").addEventListener("click", () => loadReview("save"));
    $("#prev-week").addEventListener("click", () => shiftWeek(-7));
    $("#this-week").addEventListener("click", () => setThisWeek());
    $("#week-date").addEventListener("change", () => loadReview("read"));
    $("#market-filter").addEventListener("change", renderHoldings);
    $("#status-filter").addEventListener("change", renderHoldings);
    $("#api-token").value = localStorage.getItem("weekly_review_web_token") || "";
    loadReview("read");

    async function loadReview(action) {{
      setBusy(true);
      if (action === "refresh") {{
        const weekText = state.week ? `${{state.week.week}}（${{state.week.start}} 至 ${{state.week.end}}）` : "当前选择周";
        if (!window.confirm(`强制刷新 ${{weekText}}？\\n\\n系统会重新读取数据并覆盖这一周的自动生成内容。`)) {{
          setBusy(false);
          return;
        }}
      }}
      message.textContent = {{
        read: "正在读取复盘状态...",
        generate: "正在生成并保存本周复盘...",
        refresh: "正在强制刷新本周复盘...",
        save: "正在保存当前报告..."
      }}[action] || "正在处理...";
      try {{
        const payload = {{ week_start: $("#week-date").value, markdown: $("#markdown-text").value, context: state.context }};
        const headers = authHeaders();
        let response;
        if (action === "read") {{
          response = await fetch(`/api/weekly-review?week_start=${{encodeURIComponent(payload.week_start)}}`, {{ headers }});
        }} else if (action === "generate") {{
          response = await fetch("/api/weekly-review/generate", {{ method: "POST", headers: {{ ...headers, "Content-Type": "application/json" }}, body: JSON.stringify({{ week_start: payload.week_start }}) }});
        }} else if (action === "refresh") {{
          response = await fetch("/api/weekly-review/refresh", {{ method: "POST", headers: {{ ...headers, "Content-Type": "application/json" }}, body: JSON.stringify({{ week_start: payload.week_start, force: true }}) }});
        }} else {{
          response = await fetch("/api/weekly-review/save", {{ method: "POST", headers: {{ ...headers, "Content-Type": "application/json" }}, body: JSON.stringify(payload) }});
        }}
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || "处理失败");
        persistToken();
        state.week = data.week || state.week;
        if (state.week && state.week.start) $("#week-date").value = state.week.start;
        state.reportStatus = data.status || "existing";
        state.context = data.context;
        state.markdown = data.markdown || "";
        state.holdings = data.context ? data.context.holdings_table || [] : [];
        renderAll();
        message.textContent = statusMessage(action, data);
        if (action === "save") loadCandidates();
      }} catch (error) {{
        message.textContent = `处理失败：${{error.message}}`;
      }} finally {{
        setBusy(false);
      }}
    }}

    function statusMessage(action, data) {{
      if (data.status === "missing") return "这一周还没有复盘。点击生成复盘会创建并保存一条周复盘记录。";
      if (data.already_exists) return "这一周已有复盘，已读取现有内容，没有重新生成。";
      if (action === "save" && data.saved_report) return "报告已保存。";
      if (action === "refresh") return "强制刷新完成，已覆盖这一周的自动生成内容。";
      if (action === "generate") return "复盘已生成并保存，请检查故事、下周展望和数据缺口。";
      return "已读取这一周的复盘内容。";
    }}

    function shiftWeek(days) {{
      const current = parseDateInput($("#week-date").value) || new Date();
      current.setDate(current.getDate() + days);
      $("#week-date").value = formatDateInput(current);
      loadReview("read");
    }}

    function setThisWeek() {{
      $("#week-date").value = formatDateInput(new Date());
      loadReview("read");
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
      if (!state.context) {{
        renderStatus({{}});
        return;
      }}
      renderStatus(state.context.source_status || {{}});
      slot("highlights").innerHTML = rankedTable(state.context.highlights || [], true);
      slot("blowups").innerHTML = rankedTable(state.context.blowups || [], false);
      slot("indexes").innerHTML = indexTable(state.context.index_summary || [], (state.context.source_status || {{}}).indexes);
      slot("story").innerHTML = storyBlock(state.context.story || {{}}, state.context.warnings || []);
      slot("next-week").innerHTML = nextWeekTable(state.context.next_week || []);
      slot("attribution").innerHTML = attributionCards(state.context.holder_attribution || []);
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
        ["本地知识", sourceStatus.local_knowledge],
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
        ["市场环境", story.market_environment || "待观察"],
        ["组合归因", story.portfolio_attribution || "待观察"],
        ["事件/主题证据", story.event_evidence || "待补"],
        ["负向信号", story.negative_signals || "待观察"],
        ["和我组合的关系", story.portfolio_relation || "待观察"],
        ["下周验证点", story.next_validation || "待观察"],
      ];
      const claims = story.claims || [];
      const claimHtml = claims.length ? `<div class="notice">${{claims.slice(0, 4).map((claim) => `${{claim.type || "证据"}}：${{claim.text || ""}}`).map(escapeHtml).join("；")}}</div>` : "";
      const warningHtml = warnings.length ? `<div class="notice">${{escapeHtml(warnings.slice(0, 4).join("；"))}}</div>` : "";
      return `${{warningHtml}}${{claimHtml}}<ul class="story-list">${{items.map(([k, v]) => `<li><strong>${{escapeHtml(k)}}：</strong>${{escapeHtml(v)}}</li>`).join("")}}</ul>`;
    }}

    function indexTable(items, status) {{
      if (!items.length) {{
        return `<div class="empty">${{escapeHtml(statusText(status))}}</div>`;
      }}
      return `<table><thead><tr><th>指数</th><th>市场</th><th class="money">本周涨跌</th><th>最大单日波动</th><th>环境</th><th>组合影响</th></tr></thead><tbody>
        ${{items.map((item) => {{
          const move = item.largest_daily_move || {{}};
          const moveText = move.date ? `${{move.date}} ${{formatPercent(move.change_pct)}}` : "待补";
          return `<tr><td>${{escapeHtml(item.name)}}</td><td>${{escapeHtml(item.market)}}</td><td class="money ${{moneyClass(item.weekly_change_pct)}}">${{formatPercent(item.weekly_change_pct)}}</td><td>${{escapeHtml(moveText)}}</td><td>${{escapeHtml(item.environment_label || "待观察")}}</td><td>${{escapeHtml(item.portfolio_relevance || "待观察")}}</td></tr>`;
        }}).join("")}}
      </tbody></table>`;
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

    function attributionCards(cards) {{
      if (!cards.length) return `<div class="empty">暂无持仓归因卡。</div>`;
      return `<div class="attribution-grid">${{cards.map((card) => {{
        const confidence = card.confidence || "low";
        const badgeClass = confidence === "rumor_watch" ? "badge rumor" : "badge";
        const candidates = card.cause_candidates || [];
        const candidateHtml = candidates.length ? candidates.map((candidate) => `
          <div class="candidate">
            <strong>${{escapeHtml(candidate.title || candidate.lens || "Cause candidate")}}</strong>
            <p>${{escapeHtml(candidate.claim || candidate.evidence || "")}}</p>
            <p>Evidence: ${{escapeHtml([candidate.source_type, candidate.source_name, candidate.source_date].filter(Boolean).join(" / "))}}${{candidate.url ? ` / ${{escapeHtml(candidate.url)}}` : candidate.source_id ? ` / ${{escapeHtml(candidate.source_id)}}` : ""}}</p>
            <p>Confidence: ${{escapeHtml(candidate.confidence || "low")}}；Thesis impact: ${{escapeHtml(candidate.thesis_impact || "needs_research")}}；Lens: ${{escapeHtml(candidate.lens || "待确认")}}</p>
            <p>Next validation: ${{escapeHtml(candidate.next_validation || "待补")}}</p>
          </div>
        `).join("") : `<div class="empty">No supported cause found from current structured sources.</div>`;
        const gaps = card.source_gaps || [];
        const gapHtml = gaps.length ? `<ul class="gap-list">${{gaps.map((gap) => `<li>${{escapeHtml(gap)}}</li>`).join("")}}</ul>` : "";
        const validation = (card.next_validation || []).join("；");
        return `<details class="attribution-card">
          <summary>
            <div>
              <div class="attribution-title">${{escapeHtml(card.code)}} ${{escapeHtml(card.name)}}</div>
              <div class="attribution-meta">${{formatMoney(card.weekly_pl, card.currency)}}；${{escapeHtml(card.movement || "仓位变化待确认")}}；${{escapeHtml(card.attribution_verdict || "unexplained")}}</div>
            </div>
            <span class="${{badgeClass}}">${{escapeHtml(card.dominant_lens || "mixed")}} / ${{escapeHtml(confidence)}}</span>
          </summary>
          <div class="attribution-body">
            ${{candidateHtml}}
            ${{gapHtml}}
            <div class="notice">Thesis impact: ${{escapeHtml(card.thesis_impact || "needs_research")}}；${{escapeHtml(card.thesis_relationship || "")}}${{validation ? "；Next: " + escapeHtml(validation) : ""}}</div>
          </div>
        </details>`;
      }}).join("")}}</div>`;
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
    function authHeaders() {{
      const token = $("#api-token").value.trim();
      return token ? {{ "Authorization": `Bearer ${{token}}` }} : {{}};
    }}
    function persistToken() {{
      const token = $("#api-token").value.trim();
      if (token) localStorage.setItem("weekly_review_web_token", token);
    }}
    function statusText(item) {{
      if (!item) return "缺失";
      const status = item.status || "unknown";
      const labels = {{
        ok: "已读取",
        partial: "部分可用",
        checked_empty: "已检查无材料",
        missing: "缺失",
        provider_unavailable: "数据源暂不可用",
        source_blocked: "源数据阻塞",
        realtime: "实时读取",
        snapshot: "来自快照",
        backfilled: "已回补",
        fallback: "降级可用"
      }};
      const count = item.count === undefined ? "" : `，${{item.count}} 条`;
      const reason = readableReason(item.reason);
      return `${{labels[status] || "状态待确认"}}${{count}}${{reason ? "，" + reason : ""}}`;
    }}
    function readableReason(reason) {{
      if (!reason) return "";
      const text = String(reason);
      return text;
    }}
    function parseDateInput(value) {{
      if (!value) return null;
      const parts = value.split("-").map(Number);
      if (parts.length !== 3 || parts.some((item) => Number.isNaN(item))) return null;
      return new Date(parts[0], parts[1] - 1, parts[2]);
    }}
    function formatDateInput(date) {{
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      return `${{year}}-${{month}}-${{day}}`;
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
    function formatPercent(value) {{
      const number = Number(value || 0);
      return `${{number >= 0 ? "+" : ""}}${{number.toFixed(2)}}%`;
    }}
    function moneyClass(value) {{ return Number(value || 0) < 0 ? "neg" : "pos"; }}
    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[char]));
    }}
    function escapeAttr(value) {{ return escapeHtml(value).replace(/`/g, "&#96;"); }}
  </script>
"""
    page_css = page_css.replace("{{", "{").replace("}}", "}")
    page_js = page_js.replace("{{", "{").replace("}}", "}")
    return render_app_shell(
        ShellPage(
            title="InvestmentKnowledge 周复盘",
            lang="zh-CN",
            active_nav="weekly-review",
            page_class="weekly-page",
            heading="本周复盘",
            subtitle="基于交易记录、账户快照、当前持仓、IPO 和知识库生成草稿。",
            main_html=main_html,
            aside_html=aside_html,
            page_css=page_css,
            page_js=page_js,
        )
    )


def _resolve_week_request(payload: dict[str, Any]) -> tuple[date, date]:
    week_text = _first_query_value(payload, "week")
    if week_text:
        match = re.fullmatch(r"(\d{4})-?W(\d{1,2})", week_text, flags=re.IGNORECASE)
        if not match:
            raise ValueError("周格式应为 YYYY-Www，例如 2026-W25。")
        year = int(match.group(1))
        week = int(match.group(2))
        try:
            start = date.fromisocalendar(year, week, 1)
        except ValueError as exc:
            raise ValueError("周格式无效，请选择一个有效自然周。") from exc
        return start, start + timedelta(days=6)

    date_text = (
        _first_query_value(payload, "week_start")
        or _first_query_value(payload, "date")
        or _first_query_value(payload, "start")
    )
    if date_text:
        try:
            selected = date.fromisoformat(str(date_text).replace("/", "-"))
        except ValueError as exc:
            raise ValueError("日期格式应为 YYYY-MM-DD。") from exc
        start = selected - timedelta(days=selected.weekday())
        return start, start + timedelta(days=6)
    return _default_week_range()


def _resolve_request_range(payload: dict[str, Any]) -> tuple[date, date]:
    return _resolve_week_request(payload)


def _report_response(
    report: dict[str, Any],
    *,
    start: date,
    end: date,
    status: str,
    already_exists: bool = False,
) -> dict[str, Any]:
    context = report.get("portfolio_snapshot") if isinstance(report.get("portfolio_snapshot"), dict) else {}
    context = _normalize_report_context(context, start=start, end=end)
    return {
        "ok": True,
        "status": status,
        "already_exists": already_exists,
        "week": _week_payload(start, end),
        "context": context,
        "markdown": report.get("summary") or "",
        "saved_report": report,
    }


def _normalize_report_context(context: dict[str, Any], *, start: date, end: date) -> dict[str, Any]:
    normalized = dict(context)
    normalized["period"] = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "label": f"{start.isoformat()} 至 {end.isoformat()}",
    }
    normalized["source_status"] = _friendly_source_status(normalized.get("source_status") or {})
    normalized.setdefault("highlights", [])
    normalized.setdefault("blowups", [])
    normalized.setdefault("holdings_table", [])
    normalized.setdefault("holder_attribution", [])
    normalized.setdefault("next_week", [])
    normalized.setdefault("story", {})
    normalized.setdefault("candidate_insights", [])
    normalized.setdefault("warnings", [])
    return normalized


def _friendly_source_status(source_status: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    reason_replacements = {
        "index provider not configured": "指数数据源未接入",
        "external event provider not implemented": "外部事件源未接入",
    }
    for key, value in source_status.items():
        if not isinstance(value, dict):
            result[key] = value
            continue
        item = dict(value)
        reason = item.get("reason")
        if isinstance(reason, str):
            item["reason"] = reason_replacements.get(reason, reason)
        result[key] = item
    return result


def _empty_week_context(start: date, end: date) -> dict[str, Any]:
    return {
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "label": f"{start.isoformat()} 至 {end.isoformat()}",
        },
        "source_status": {
            "account_snapshots": {"status": "missing", "count": 0},
            "trades": {"status": "missing", "count": 0},
            "positions": {"status": "missing"},
            "ipo": {"status": "missing", "count": 0},
            "indexes": {"status": "missing", "provider": "futu", "count": 0},
            "events": {"status": "missing", "providers": ["official_sources"], "count": 0},
            "local_knowledge": {"status": "missing", "count": 0},
        },
        "highlights": [],
        "blowups": [],
        "holdings_table": [],
        "holder_attribution": [],
        "next_week": [],
        "story": {},
        "candidate_insights": [],
        "warnings": [],
    }


def _week_payload(start: date, end: date) -> dict[str, str]:
    calendar = start.isocalendar()
    return {
        "week": f"{calendar.year}-W{calendar.week:02d}",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "label": f"{start.isoformat()} 至 {end.isoformat()}",
    }


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _public_weekly_error(exc: Exception, *, saving: bool = False) -> str:
    if saving:
        return "保存失败：数据库结构或连接暂时不可用，请稍后重试；维护者可查看服务日志定位具体原因。"
    return "周复盘处理失败：数据源或数据库暂时不可用，请稍后重试；维护者可查看服务日志定位具体原因。"


def _default_week_range() -> tuple[date, date]:
    today = datetime.now(SHANGHAI_TZ).date()
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def _first_query_value(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _authorization_token(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return None


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _record_workbench_event(command: str, ok: bool, message: str, source: str) -> dict[str, Any] | None:
    try:
        return record_command_event(
            command=command,
            ok=ok,
            message=message,
            source=source,
            sender=None,
        )
    except Exception:
        return None


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
