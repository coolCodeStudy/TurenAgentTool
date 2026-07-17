from __future__ import annotations

from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
import os
import re
from threading import Lock
import time
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import daily_market_jobs, repository
from investment_knowledge_mcp.command_router import handle_command, safe_public_command_message
from investment_knowledge_mcp.command_workbench import (
    execution_blocker,
    list_workbench_actions,
    parse_workbench_command,
    render_command_workbench_html,
)
from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.daily_market_brief import (
    MARKET_CONFIGS,
    build_daily_market_brief,
    get_daily_market_brief_report,
    list_daily_market_brief_dates,
    resolve_latest_completed_session_date,
)
from investment_knowledge_mcp.daily_market_jobs import (
    get_public_web_history_job,
    list_public_web_history_jobs,
)
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.repository import record_command_event
from investment_knowledge_mcp.weekly_review import build_weekly_review, save_weekly_review_report
from investment_knowledge_mcp.web_experience import (
    access_error_payload,
    render_experience_css,
    render_primary_navigation,
)


MAX_BODY_BYTES = 64 * 1024
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)
PUBLIC_WORKBENCH_FAILURE_MESSAGE = "Command execution failed. Please retry later."


class _DailyBriefGenerationLease:
    def __init__(self, gate: "_DailyBriefGenerationGate", key: tuple[str, str]) -> None:
        self._gate = gate
        self._key = key
        self._released = False

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._gate.release(self._key)


class _DailyBriefGenerationGate:
    def __init__(self, *, cooldown_seconds: int, clock: Any = time.monotonic) -> None:
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._lock = Lock()
        self._active: set[tuple[str, str]] = set()
        self._completed_at: dict[tuple[str, str], float] = {}

    def try_acquire(self, key: tuple[str, str]) -> _DailyBriefGenerationLease | None:
        with self._lock:
            now = self._clock()
            if key in self._active or now - self._completed_at.get(key, float("-inf")) < self._cooldown_seconds:
                return None
            self._active.add(key)
        return _DailyBriefGenerationLease(self, key)

    def release(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._active.discard(key)
            self._completed_at[key] = self._clock()


_DAILY_BRIEF_GENERATION_GATE = _DailyBriefGenerationGate(cooldown_seconds=60)
_MAX_ACTIVE_WEB_HISTORY_JOBS = 3


class WeeklyReviewWebHandler(BaseHTTPRequestHandler):
    server_version = "InvestmentKnowledgeWeeklyReviewWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/weekly-review"}:
            self._write_html(HTTPStatus.OK, render_weekly_review_workbench_html())
            return
        if parsed.path == "/daily-market-brief":
            self._write_html(HTTPStatus.OK, render_daily_market_brief_html())
            return
        if parsed.path == "/health":
            self._write_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "app_release_sha": os.getenv("APP_RELEASE_SHA") or "",
                    "daily_market_brief_route": True,
                },
            )
            return
        if parsed.path == "/command":
            self._write_html(HTTPStatus.OK, render_command_workbench_html())
            return
        if parsed.path == "/api/command-workbench/actions":
            self._write_json(HTTPStatus.OK, {"ok": True, "actions": list_workbench_actions()})
            return
        if parsed.path == "/api/weekly-review":
            self._handle_weekly_review_read(parse_qs(parsed.query))
            return
        if parsed.path == "/api/daily-market-brief":
            self._handle_daily_market_brief_read(parse_qs(parsed.query))
            return
        if parsed.path == "/api/daily-market-brief/dates":
            self._handle_daily_market_brief_dates(parse_qs(parsed.query))
            return
        if parsed.path == "/api/daily-market-brief/history-jobs":
            self._handle_daily_market_brief_history_jobs_read(parse_qs(parsed.query))
            return
        if parsed.path == "/api/candidate-insights":
            if not self._authorized(require_configured=True):
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

        if parsed.path == "/api/weekly-review/generate":
            if not self._authorized(require_configured=True):
                return
            payload = self._read_json_body()
            if payload is None:
                return
            self._handle_weekly_review_generate(payload, force=False)
            return
        if parsed.path == "/api/weekly-review/refresh":
            if not self._authorized(require_configured=True):
                return
            payload = self._read_json_body()
            if payload is None:
                return
            self._handle_weekly_review_generate(payload, force=True)
            return
        if parsed.path == "/api/weekly-review/save":
            if not self._authorized(require_configured=True):
                return
            payload = self._read_json_body()
            if payload is None:
                return
            self._handle_weekly_review_save(payload)
            return
        if parsed.path == "/api/daily-market-brief/generate":
            payload = self._read_json_body()
            if payload is None:
                return
            self._handle_daily_market_brief_generate(payload)
            return
        if parsed.path == "/api/daily-market-brief/history-jobs":
            payload = self._read_json_body()
            if payload is None:
                return
            self._handle_daily_market_brief_history_job_create(payload)
            return

        candidate_match = re.fullmatch(r"/api/candidate-insights/(\d+)/(confirm|reject)", parsed.path)
        if candidate_match:
            if not self._authorized(require_configured=True):
                return
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
            response_message = safe_public_command_message(result, PUBLIC_WORKBENCH_FAILURE_MESSAGE)
            event = record_command_event(
                command=exact_command,
                ok=result.ok,
                message=response_message,
                sender=_clean_optional_text(payload.get("sender")),
                source="weekly-review-web.command-workbench.execute",
            )
        except Exception:
            logger.exception("Command Workbench execution failed")
            event = _record_workbench_event(
                command=exact_command,
                ok=False,
                message=PUBLIC_WORKBENCH_FAILURE_MESSAGE,
                source="weekly-review-web.command-workbench.execute",
            )
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "ok": False,
                    "error": PUBLIC_WORKBENCH_FAILURE_MESSAGE,
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
                "message": response_message,
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

    def _handle_daily_market_brief_read(self, payload: dict[str, Any]) -> None:
        try:
            market = _resolve_daily_market(payload)
            market_date = _resolve_optional_date(payload)
            report = get_daily_market_brief_report(market=market, market_date=market_date)
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": _public_daily_market_brief_error(exc)})
            return

        if report:
            self._write_json(HTTPStatus.OK, _daily_market_brief_response(report, status="existing"))
            return

        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "status": "missing",
                "market": market,
                "market_date": market_date.isoformat() if market_date else None,
                "context": _empty_daily_market_brief_context(market, market_date),
                "markdown": "",
                "saved_report": None,
            },
        )

    def _handle_daily_market_brief_dates(self, payload: dict[str, Any]) -> None:
        try:
            market = _resolve_daily_market(payload)
            dates = list_daily_market_brief_dates(market)
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": _public_daily_market_brief_error(exc)})
            return

        self._write_json(HTTPStatus.OK, {"ok": True, "market": market, "dates": dates})

    def _handle_daily_market_brief_history_jobs_read(self, payload: dict[str, Any]) -> None:
        try:
            job_id_text = _first_query_value(payload, "id")
            if job_id_text:
                job_id = int(job_id_text)
                if job_id < 1:
                    raise ValueError("任务 ID 无效。")
                job = get_public_web_history_job(job_id)
                if job is None:
                    self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "未找到该历史简报任务。"})
                    return
                self._write_json(HTTPStatus.OK, {"ok": True, "job": _public_history_job(job)})
                return

            limit_text = _first_query_value(payload, "limit") or "10"
            limit = int(limit_text)
            if limit < 1 or limit > 50:
                raise ValueError("任务列表数量应在 1 到 50 之间。")
            jobs = list_public_web_history_jobs(limit=limit)
        except (TypeError, ValueError) as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "历史简报任务暂时无法读取。"})
            return

        self._write_json(HTTPStatus.OK, {"ok": True, "jobs": [_public_history_job(job) for job in jobs]})

    def _handle_daily_market_brief_history_job_create(self, payload: dict[str, Any]) -> None:
        try:
            if set(payload) != {"market", "date"}:
                raise ValueError("历史简报任务只接受 market 和 date。")
            if not isinstance(payload.get("market"), str) or not isinstance(payload.get("date"), str):
                raise ValueError("历史简报任务仅支持单个市场和单个日期。")
            market = _resolve_daily_market(payload)
            market_date = _resolve_optional_date(payload)
            if market_date is None:
                raise ValueError("请选择历史市场日期。")
            market_date = _validate_public_daily_market_brief_date(
                market,
                market_date,
                now=datetime.now(SHANGHAI_TZ),
            )
            try:
                job = daily_market_jobs.create_web_history_job(
                    market,
                    market_date,
                    max_active_jobs=_MAX_ACTIVE_WEB_HISTORY_JOBS,
                )
            except daily_market_jobs.WebHistoryJobCapacityError:
                self._write_json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    {"ok": False, "error": "已有 3 个历史简报任务等待处理，请稍后再试。"},
                )
                return
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "历史简报任务暂时无法创建。"})
            return

        self._write_json(
            HTTPStatus.ACCEPTED,
            {
                "ok": True,
                "status": job.get("status") or "queued",
                "market": market,
                "market_date": market_date.isoformat(),
                "job": _public_history_job(job),
            },
        )

    def _handle_daily_market_brief_generate(self, payload: dict[str, Any]) -> None:
        lease: _DailyBriefGenerationLease | None = None
        request_now = datetime.now(SHANGHAI_TZ)
        try:
            allowed_fields = {"market", "date", "market_date", "fixture"}
            if not set(payload).issubset(allowed_fields):
                raise ValueError("公开生成不支持 force、batch 或其他工作量控制参数。")
            market = _resolve_daily_market(payload)
            market_date = _resolve_optional_date(payload)
            use_fixture = _truthy(_first_query_value(payload, "fixture"))
            if use_fixture:
                raise ValueError("公开页面不支持 fixture 生成。")
            market_date = _validate_public_daily_market_brief_date(market, market_date, now=request_now)
            latest_completed = resolve_latest_completed_session_date(market, now=request_now)
            if market_date < latest_completed:
                self._handle_daily_market_brief_history_job_create(
                    {"market": market, "date": market_date.isoformat()}
                )
                return
            lease = _DAILY_BRIEF_GENERATION_GATE.try_acquire((market, market_date.isoformat()))
            if lease is None:
                self._write_json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    {"ok": False, "error": "该市场简报正在生成或刚刚生成，请稍后再试。"},
                )
                return
            result = build_daily_market_brief(
                market=market,
                market_date=market_date,
                save=True,
                now=request_now,
                use_fixture=False,
            )
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": _public_daily_market_brief_error(exc)})
            return
        finally:
            if lease is not None:
                lease.release()

        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "status": "generated",
                "market": result.context.get("market") or {},
                "market_date": result.context.get("market_date"),
                "context": result.context,
                "markdown": result.markdown,
                "saved_report": result.saved_report,
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
        configured_tokens = [
            token for token in (config.command_api_token, config.weekly_review_web_token) if token
        ]
        supplied_tokens = [
            token for token in (supplied, command_token, weekly_token) if token
        ]
        if not configured_tokens:
            self._write_json(HTTPStatus.SERVICE_UNAVAILABLE, access_error_payload("access_not_configured"))
            return False
        if not supplied_tokens:
            self._write_json(HTTPStatus.UNAUTHORIZED, access_error_payload("access_required"))
            return False
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
        self._write_json(HTTPStatus.UNAUTHORIZED, access_error_payload("access_rejected"))
        return False

    def _authorized(self, *, require_configured: bool = False) -> bool:
        config = get_config()
        tokens = [token for token in (config.weekly_review_web_token, config.command_api_token) if token]
        if not tokens:
            if require_configured:
                self._write_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "web write token is not configured"})
                return False
            return True
        authorization = self.headers.get("Authorization")
        web_token = self.headers.get("X-Weekly-Review-Token")
        command_token = self.headers.get("X-Command-Token")
        supplied = ""
        if authorization and authorization.startswith("Bearer "):
            supplied = authorization.removeprefix("Bearer ").strip()
        elif web_token:
            supplied = web_token.strip()
        elif command_token:
            supplied = command_token.strip()
        if supplied and any(hmac.compare_digest(supplied, token) for token in tokens):
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
        if length < 0:
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
    {render_experience_css()}
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
    .read-only-badge {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--chip);
      color: var(--muted);
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 650;
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
  <div class="experience-shell">
    {render_primary_navigation("weekly_review")}
    <div class="experience-main">
      <div class="shell">
    <aside class="sidebar">
      <p class="brand">InvestmentKnowledge</p>
      <nav class="nav" aria-label="主导航">
        <a class="active" href="/weekly-review">本周复盘</a>
        <a href="/daily-market-brief">每日市场简报</a>
        <a href="#holdings">当前持仓</a>
        <a href="#markdown">报告原文</a>
        <a href="#source-status">数据源状态</a>
      </nav>
    </aside>
    <main>
      <div class="topbar">
        <div>
          <h1>本周复盘</h1>
          <p class="subtitle">只读查看基于交易记录、账户快照、当前持仓、IPO 和知识库生成的周复盘。</p>
        </div>
        <div class="controls">
          <button id="prev-week" type="button">上一周</button>
          <button id="this-week" type="button">本周</button>
          <input id="week-date" type="date" value="{start.isoformat()}" aria-label="复盘周">
          <span class="read-only-badge">公开只读</span>
        </div>
      </div>
      <div id="message" class="notice">正在读取本周复盘状态。</div>
      <div id="source-status" class="status-grid" aria-live="polite"></div>
      <section id="highlights"><h2>1. 高光时刻</h2><div data-slot="highlights"></div></section>
      <section id="blowups"><h2>2. 炸裂时刻</h2><div data-slot="blowups"></div></section>
      <section id="indexes"><h2>3. 指数</h2><div data-slot="indexes"></div></section>
      <section id="story"><h2>4. 整体故事</h2><div data-slot="story"></div></section>
      <section id="next-week"><h2>5. 下周展望</h2><div data-slot="next-week"></div></section>
      <section id="holdings"><h2>6. 当前持仓分析</h2><div class="chips"><select id="market-filter"><option value="">全部市场</option></select><select id="status-filter"><option value="">全部状态</option><option value="待处理">待处理</option><option value="补研究">补研究</option><option value="高波动">高波动</option><option value="历史拖累">历史拖累</option></select></div><div data-slot="holdings"></div></section>
      <section id="attribution"><h2>7. 持仓归因卡</h2><div data-slot="attribution"></div></section>
      <section id="markdown"><h2>报告原文</h2><textarea id="markdown-text" class="markdown" spellcheck="false" readonly></textarea></section>
    </main>
    <aside class="aside" aria-label="复盘目录">
      <a href="#highlights">1. 高光时刻</a>
      <a href="#blowups">2. 炸裂时刻</a>
      <a href="#indexes">3. 指数</a>
      <a href="#story">4. 整体故事</a>
      <a href="#next-week">5. 下周展望</a>
      <a href="#holdings">6. 当前持仓分析</a>
      <a href="#attribution">7. 持仓归因卡</a>
      <a href="#source-status">数据源状态</a>
    </aside>
      </div>
    </div>
  </div>
  <script>
    const state = {{ context: null, markdown: "", holdings: [], week: null, reportStatus: "loading" }};
    const $ = (selector) => document.querySelector(selector);
    const slot = (name) => document.querySelector(`[data-slot="${{name}}"]`);
    const message = $("#message");

    $("#prev-week").addEventListener("click", () => shiftWeek(-7));
    $("#this-week").addEventListener("click", () => setThisWeek());
    $("#week-date").addEventListener("change", loadReview);
    $("#market-filter").addEventListener("change", renderHoldings);
    $("#status-filter").addEventListener("change", renderHoldings);
    loadReview();

    async function loadReview() {{
      message.textContent = "正在读取复盘状态...";
      try {{
        const weekStart = $("#week-date").value;
        const response = await fetch(`/api/weekly-review?week_start=${{encodeURIComponent(weekStart)}}`);
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || "处理失败");
        state.week = data.week || state.week;
        if (state.week && state.week.start) $("#week-date").value = state.week.start;
        state.reportStatus = data.status || "existing";
        state.context = data.context;
        state.markdown = data.markdown || "";
        state.holdings = data.context ? data.context.holdings_table || [] : [];
        renderAll();
        message.textContent = statusMessage(data);
      }} catch (error) {{
        message.textContent = `处理失败：${{error.message}}`;
      }}
    }}

    function statusMessage(data) {{
      if (data.status === "missing") return "这一周还没有已生成的复盘。";
      if (data.already_exists) return "这一周已有复盘，已读取现有内容，没有重新生成。";
      return "已读取这一周的复盘内容。";
    }}

    function shiftWeek(days) {{
      const current = parseDateInput($("#week-date").value) || new Date();
      current.setDate(current.getDate() + days);
      $("#week-date").value = formatDateInput(current);
      loadReview();
    }}

    function setThisWeek() {{
      $("#week-date").value = formatDateInput(new Date());
      loadReview();
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
</body>
</html>"""


def render_daily_market_brief_html() -> str:
    today = ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InvestmentKnowledge 每日市场简报</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7f9;
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
      grid-template-columns: 220px minmax(0, 1fr);
      min-height: 100vh;
    }}
    .sidebar {{
      border-right: 1px solid var(--line);
      background: #fff;
      padding: 22px 16px;
    }}
    .brand {{
      font-size: 18px;
      font-weight: 700;
      margin: 0 0 20px;
    }}
    .nav {{ display: grid; gap: 4px; }}
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
      min-width: 0;
      padding: 22px 24px 42px;
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
      gap: 8px;
      align-items: center;
      justify-content: flex-end;
      flex-wrap: wrap;
    }}
    input, select, button {{
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }}
    input, select {{ padding: 0 8px; }}
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
    .tabs {{
      display: flex;
      gap: 6px;
      margin: 0 0 14px;
      flex-wrap: wrap;
    }}
    .tabs button {{
      min-width: 72px;
      background: #fff;
    }}
    .tabs button.active {{
      border-color: var(--accent);
      background: #e8f1fa;
      color: var(--accent);
    }}
    .notice {{
      border-left: 3px solid var(--warn);
      background: #fff8e8;
      color: #6b4b00;
      padding: 10px 12px;
      font-size: 13px;
      margin-bottom: 14px;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 1fr));
      gap: 8px;
      margin-bottom: 14px;
    }}
    .summary-card, section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
    }}
    .summary-card {{
      min-height: 72px;
      padding: 11px;
    }}
    .summary-card strong {{
      display: block;
      font-size: 13px;
      margin-bottom: 5px;
    }}
    .summary-card span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    section {{
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
      white-space: nowrap;
    }}
    .money {{ text-align: right; white-space: nowrap; }}
    .pos {{ color: var(--good); }}
    .neg {{ color: var(--bad); }}
    .empty {{
      color: var(--muted);
      font-size: 13px;
    }}
    .markdown {{
      width: 100%;
      min-height: 260px;
      resize: vertical;
      line-height: 1.5;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
    }}
    @media (max-width: 900px) {{
      .shell {{ display: block; }}
      .sidebar {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      main {{ padding: 16px; }}
      .topbar {{ grid-template-columns: 1fr; }}
      .controls {{ justify-content: flex-start; }}
      .summary-grid {{ grid-template-columns: 1fr 1fr; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <p class="brand">InvestmentKnowledge</p>
      <nav class="nav" aria-label="主导航">
        <a href="/weekly-review">本周复盘</a>
        <a class="active" href="/daily-market-brief">每日市场简报</a>
        <a href="/command">Command</a>
      </nav>
    </aside>
    <main>
      <div class="topbar">
        <div>
          <h1>每日市场简报</h1>
          <p class="subtitle">按市场查看收盘后的核心指数、领涨方向、个股、资金流和数据缺口。</p>
        </div>
        <div class="controls">
          <input id="market-date" type="date" value="{today}" aria-label="市场日期">
          <select id="saved-date" aria-label="已保存日期"><option value="">已保存日期</option></select>
          <button id="read" type="button">读取</button>
          <button id="generate" class="primary" type="button">生成</button>
        </div>
      </div>
      <div class="tabs" aria-label="市场">
        <button data-market="CN" class="active" type="button">A股</button>
        <button data-market="HK" type="button">港股</button>
        <button data-market="US" type="button">美股</button>
      </div>
      <div id="message" class="notice" role="status" aria-live="polite" aria-atomic="true">正在读取每日市场简报。</div>
      <section><h2>历史生成任务</h2><div id="history-jobs" class="empty">暂无历史生成任务。</div></section>
      <div id="summary" class="summary-grid"></div>
      <section><h2>简报摘要</h2><div id="narrative" class="empty"></div></section>
      <section><h2>核心指数</h2><div id="indexes"></div></section>
      <section><h2>领涨行业/板块</h2><div id="sectors"></div></section>
      <section><h2>领涨个股</h2><div id="gainers"></div></section>
      <section><h2>资金流</h2><div id="capital-flow"></div></section>
      <section><h2>数据状态</h2><div id="source-status"></div></section>
      <section><h2>Markdown 原文</h2><textarea id="markdown" class="markdown" spellcheck="false"></textarea></section>
    </main>
  </div>
  <script>
    const state = {{
      market: "CN",
      context: null,
      markdown: "",
      jobId: null,
      pollTimer: null,
      pollGeneration: 0,
      loadGeneration: 0,
      loadController: null
    }};
    const $ = (selector) => document.querySelector(selector);
    const message = $("#message");

    document.querySelectorAll("[data-market]").forEach((button) => {{
      button.addEventListener("click", () => {{
        stopHistoryJobPolling();
        state.market = button.dataset.market;
        $("#market-date").value = "";
        document.querySelectorAll("[data-market]").forEach((item) => item.classList.toggle("active", item === button));
        loadSavedDates();
        loadBrief("read");
      }});
    }});
    $("#read").addEventListener("click", () => loadBrief("read"));
    $("#generate").addEventListener("click", () => loadBrief("generate"));
    $("#market-date").addEventListener("change", () => {{
      stopHistoryJobPolling();
      loadBrief("read");
    }});
    $("#saved-date").addEventListener("change", (event) => {{
      stopHistoryJobPolling();
      if (!event.target.value) return;
      $("#market-date").value = event.target.value;
      loadBrief("read");
    }});
    loadSavedDates();
    loadRecentHistoryJobs();
    loadBrief("read");

    async function loadSavedDates() {{
      const savedDate = $("#saved-date");
      savedDate.innerHTML = '<option value="">已保存日期</option>';
      try {{
        const response = await fetch(`/api/daily-market-brief/dates?market=${{encodeURIComponent(state.market)}}`);
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || "读取已保存日期失败");
        (data.dates || []).forEach((value) => {{
          const option = document.createElement("option");
          option.value = value;
          option.textContent = `已保存 ${{value}}`;
          savedDate.appendChild(option);
        }});
        if (!(data.dates || []).length) savedDate.options[0].textContent = "尚未生成";
      }} catch (error) {{
        savedDate.options[0].textContent = "尚未生成";
      }}
    }}

    async function loadBrief(action) {{
      cancelBriefLoad();
      const generation = state.loadGeneration;
      const controller = new AbortController();
      state.loadController = controller;
      setBusy(true);
      const date = $("#market-date").value;
      message.textContent = action === "read" ? "正在读取简报..." : "正在生成并保存简报...";
      try {{
        let response;
        if (action === "read") {{
          const query = new URLSearchParams({{ market: state.market, date }});
          response = await fetch(`/api/daily-market-brief?${{query.toString()}}`, {{
            signal: controller.signal
          }});
        }} else {{
          response = await fetch("/api/daily-market-brief/generate", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ market: state.market, date }}),
            signal: controller.signal
          }});
        }}
        const data = await response.json();
        if (generation !== state.loadGeneration || controller.signal.aborted) return;
        if (!data.ok) throw new Error(data.error || "处理失败");
        if (data.market_date) $("#market-date").value = data.market_date;
        if (data.job) {{
          state.jobId = data.job.id;
          renderHistoryJob(data.job);
          message.textContent = "历史简报任务已加入队列，页面会自动更新进度。";
          loadRecentHistoryJobs();
          startHistoryJobPolling(data.job.id, data.market_date);
          return;
        }}
        state.context = data.context || null;
        state.markdown = data.markdown || "";
        renderAll(data);
        if (action === "generate") {{
          loadSavedDates();
          loadRecentHistoryJobs();
        }}
        message.textContent = statusMessage(action, data);
      }} catch (error) {{
        if (generation !== state.loadGeneration || error.name === "AbortError") return;
        message.textContent = `处理失败：${{error.message}}`;
      }} finally {{
        if (generation === state.loadGeneration) {{
          if (state.loadController === controller) state.loadController = null;
          setBusy(false);
        }}
      }}
    }}

    function cancelBriefLoad() {{
      state.loadGeneration += 1;
      if (state.loadController) state.loadController.abort();
      state.loadController = null;
    }}

    async function loadRecentHistoryJobs() {{
      try {{
        const response = await fetch("/api/daily-market-brief/history-jobs?limit=10");
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || "读取任务失败");
        renderRecentHistoryJobs(data.jobs || []);
      }} catch (error) {{
        $("#history-jobs").textContent = "历史生成任务暂时无法读取。";
      }}
    }}

    function startHistoryJobPolling(jobId, marketDate) {{
      stopHistoryJobPolling(false);
      state.jobId = jobId;
      const generation = state.pollGeneration;
      pollHistoryJob(jobId, marketDate, generation);
    }}

    async function pollHistoryJob(jobId, marketDate, generation) {{
      try {{
        const response = await fetch(`/api/daily-market-brief/history-jobs?id=${{encodeURIComponent(jobId)}}`);
        const data = await response.json();
        if (generation !== state.pollGeneration || state.jobId !== jobId) return;
        if (!data.ok) throw new Error(data.error || "读取任务失败");
        const job = data.job;
        renderHistoryJob(job);
        if (["completed", "partial", "failed", "cancelled"].includes(job.status)) {{
          state.jobId = null;
          loadRecentHistoryJobs();
          if (["completed", "partial"].includes(job.status)) {{
            message.textContent = job.status === "partial"
              ? "历史简报已部分生成，缺失项已在数据状态中说明。"
              : "历史简报已生成并保存。";
            await loadSavedDates();
            if (state.market === job.items?.[0]?.market && $("#market-date").value === marketDate) {{
              await loadBrief("read");
            }}
          }} else {{
            const failures = (job.items || []).map((item) => item.error_summary).filter(Boolean);
            message.textContent = failures[0] || (job.status === "cancelled" ? "历史简报任务已取消。" : "历史简报生成失败，请稍后重试。");
          }}
          return;
        }}
        message.textContent = historyJobProgress(job);
        state.pollTimer = setTimeout(() => pollHistoryJob(jobId, marketDate, generation), 2000);
      }} catch (error) {{
        if (generation !== state.pollGeneration || state.jobId !== jobId) return;
        message.textContent = `任务进度读取失败：${{error.message}}`;
        state.pollTimer = setTimeout(() => pollHistoryJob(jobId, marketDate, generation), 5000);
      }}
    }}

    function stopHistoryJobPolling(clearJob = true) {{
      state.pollGeneration += 1;
      if (state.pollTimer) clearTimeout(state.pollTimer);
      state.pollTimer = null;
      if (clearJob) state.jobId = null;
    }}

    function historyJobProgress(job) {{
      const current = job.current_market_date
        ? `，当前 ${{job.current_market || ""}} ${{job.current_market_date}}`
        : "";
      return `历史简报任务 #${{job.id}}：已处理 ${{job.completed_count || 0}}/${{job.total_count || 0}}${{current}}。`;
    }}

    function renderHistoryJob(job) {{
      const failures = (job.items || []).map((item) => item.error_summary).filter(Boolean);
      $("#history-jobs").innerHTML = `<strong>任务 #${{escapeHtml(job.id)}}</strong><br>${{escapeHtml(historyJobProgress(job))}}${{failures.length ? `<br>${{escapeHtml(failures.join("；"))}}` : ""}}`;
    }}

    function renderRecentHistoryJobs(jobs) {{
      if (!jobs.length) {{
        $("#history-jobs").textContent = "暂无历史生成任务。";
        return;
      }}
      $("#history-jobs").innerHTML = jobs.map((job) => {{
        const item = (job.items || [])[0] || {{}};
        return `<div><strong>#${{escapeHtml(job.id)}}</strong> ${{escapeHtml(item.market || "-")}} ${{escapeHtml(item.market_date || "-")}}：${{escapeHtml(job.status || "-")}}，${{escapeHtml(job.completed_count || 0)}}/${{escapeHtml(job.total_count || 0)}}</div>`;
      }}).join("");
    }}

    function statusMessage(action, data) {{
      if (data.status === "missing") return "当前市场和日期还没有简报，可以点击生成。";
      if (action === "generate") return "简报已生成并保存，请检查数据状态和是否存在缺口。";
      return "已读取已保存的每日市场简报。";
    }}

    function renderAll(data) {{
      const context = state.context;
      if (data.status === "missing") {{
        renderEmpty("尚未生成");
        return;
      }}
      if (!context) {{
        renderEmpty();
        return;
      }}
      $("#market-date").value = context.market_date || $("#market-date").value;
      $("#summary").innerHTML = [
        ["市场", `${{context.market?.name || state.market}}（${{context.market?.code || state.market}}）`],
        ["市场日期", context.market_date || "-"],
        ["生成时间", context.generated_at?.asia_singapore || "-"],
        ["模式", context.provider_mode === "fixture" ? "fixture 验收样例" : "live / degraded"],
        ["生成类型", context.generation_kind === "historical_reconstruction" ? "历史重建" : (context.generation_kind === "live_rerun" ? "收盘生成" : "尚未生成")]
      ].map(([label, value]) => `<div class="summary-card"><strong>${{escapeHtml(label)}}</strong><span>${{escapeHtml(value)}}</span></div>`).join("");
      $("#narrative").textContent = context.narrative || "暂无摘要。";
      $("#indexes").innerHTML = indexTable(context.indexes || []);
      $("#sectors").innerHTML = rankTable(context.sectors || [], "板块/行业");
      $("#gainers").innerHTML = rankTable(context.gainers || [], "标的");
      $("#capital-flow").innerHTML = rankTable(context.capital_flow || [], "名称/分组", true);
      $("#source-status").innerHTML = statusTable(context.source_status || {{}});
      $("#markdown").value = state.markdown;
    }}

    function renderEmpty(stateLabel = "") {{
      $("#summary").innerHTML = stateLabel
        ? `<div class="summary-card"><strong>状态</strong><span>${{escapeHtml(stateLabel)}}</span></div>`
        : "";
      $("#narrative").textContent = "暂无简报。";
      $("#indexes").innerHTML = `<div class="empty">暂无核心指数数据。</div>`;
      $("#sectors").innerHTML = `<div class="empty">暂无行业/板块数据。</div>`;
      $("#gainers").innerHTML = `<div class="empty">暂无个股数据。</div>`;
      $("#capital-flow").innerHTML = `<div class="empty">暂无资金流数据。</div>`;
      $("#source-status").innerHTML = "";
      $("#markdown").value = "";
    }}

    function indexTable(rows) {{
      if (!rows.length) return `<div class="empty">暂无核心指数数据。</div>`;
      return `<table><thead><tr><th>指数</th><th>代码</th><th class="money">收盘</th><th class="money">涨跌幅</th><th class="money">较前日量能</th><th class="money">较5日均量</th><th class="money">较20日均量</th></tr></thead><tbody>
        ${{rows.map((row) => {{
          const previousVolume = relativePct(row.volume, row.baseline?.previous);
          const avg5Volume = relativePct(row.volume, row.baseline?.avg_5);
          const avg20Volume = relativePct(row.volume, row.baseline?.avg_20);
          return `<tr><td>${{escapeHtml(row.name)}}</td><td>${{escapeHtml(row.code)}}</td><td class="money">${{fmt(row.close)}}</td><td class="money ${{numClass(row.change_pct)}}">${{pct(row.change_pct)}}</td><td class="money ${{numClass(previousVolume)}}">${{pct(previousVolume)}}</td><td class="money ${{numClass(avg5Volume)}}">${{pct(avg5Volume)}}</td><td class="money ${{numClass(avg20Volume)}}">${{pct(avg20Volume)}}</td></tr>`;
        }}).join("")}}
      </tbody></table>`;
    }}

    function rankTable(rows, firstLabel, flow = false) {{
      if (!rows.length) return `<div class="empty">当前数据源未提供可用明细，见数据状态。</div>`;
      return `<table><thead><tr><th>${{escapeHtml(firstLabel)}}</th><th>代码/提供方</th><th class="money">涨跌/数值</th><th class="money">成交额/说明</th></tr></thead><tbody>
        ${{rows.map((row) => {{
          const numericValue = row.flow_value ?? row.value ?? row.change_pct;
          const valueText = flow ? fmt(numericValue) : pct(row.change_pct);
          const noteText = row.turnover !== undefined ? formatMarketAmount(row.turnover, state.context?.market?.code || state.market) : (row.message || row.metric || "-");
          return `<tr><td>${{escapeHtml(row.name || row.segment || row.provider || "-")}}</td><td>${{escapeHtml(row.code || row.provider || "-")}}</td><td class="money ${{numClass(numericValue)}}">${{escapeHtml(valueText)}}</td><td class="money">${{escapeHtml(noteText)}}</td></tr>`;
        }}).join("")}}
      </tbody></table>`;
    }}

    function statusTable(sourceStatus) {{
      const rows = Object.entries(sourceStatus);
      if (!rows.length) return `<div class="empty">暂无数据状态。</div>`;
      return `<table><thead><tr><th>模块</th><th>状态</th><th>来源</th><th>说明</th></tr></thead><tbody>
        ${{rows.map(([key, item]) => `<tr><td>${{escapeHtml(sourceLabel(key))}}</td><td>${{escapeHtml(statusLabel(item?.status))}}</td><td>${{escapeHtml(item?.provider || item?.taxonomy || "-")}}</td><td>${{escapeHtml(item?.message || item?.reason || "-")}}</td></tr>`).join("")}}
      </tbody></table>`;
    }}

    function setBusy(busy) {{
      $("#read").disabled = busy;
      $("#generate").disabled = busy;
    }}
    function sourceLabel(key) {{
      return {{ indexes: "核心指数", sectors: "行业/板块", gainers: "领涨个股", capital_flow: "资金流", session: "交易日" }}[key] || key;
    }}
    function statusLabel(status) {{
      return {{ ok: "可用", partial: "部分可用", missing: "暂缺", provider_unavailable: "数据源暂不可用", not_available: "未提供", no_session: "无常规交易", unverified: "交易日未确认", historical_not_supported: "不支持历史榜单", timed_out: "历史数据获取超时，已保留可用结果" }}[status] || status || "未知";
    }}
    function pct(value) {{
      if (value === null || value === undefined || value === "") return "-";
      const number = Number(value);
      return `${{number >= 0 ? "+" : ""}}${{number.toFixed(2)}}%`;
    }}
    function fmt(value) {{
      if (value === null || value === undefined || value === "") return "-";
      return Number(value).toLocaleString(undefined, {{ maximumFractionDigits: 2 }});
    }}
    function formatMarketAmount(value, market) {{
      if (value === null || value === undefined || value === "") return "-";
      const number = Number(value);
      const currencies = {{
        CN: {{ code: "CNY", unit: "元" }},
        HK: {{ code: "HKD", unit: "港元" }},
        US: {{ code: "USD", unit: "美元" }}
      }};
      const currency = currencies[market] || currencies.CN;
      const absolute = Math.abs(number);
      if (absolute >= 100000000) return `${{(number / 100000000).toFixed(2)}} 亿${{currency.unit}} ${{currency.code}}`;
      if (absolute >= 10000) return `${{(number / 10000).toFixed(2)}} 万${{currency.unit}} ${{currency.code}}`;
      return `${{number.toFixed(2)}} ${{currency.unit}} ${{currency.code}}`;
    }}
    function relativePct(current, baseline) {{
      if (!current || !baseline) return null;
      return ((Number(current) - Number(baseline)) / Number(baseline)) * 100;
    }}
    function numClass(value) {{ return Number(value || 0) < 0 ? "neg" : "pos"; }}
    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[char]));
    }}
  </script>
</body>
</html>"""


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


def _resolve_daily_market(payload: dict[str, Any]) -> str:
    market = (_first_query_value(payload, "market") or "CN").upper()
    if market not in {"CN", "HK", "US"}:
        raise ValueError("市场只支持 CN、HK、US。")
    return market


def _resolve_optional_date(payload: dict[str, Any]) -> date | None:
    date_text = _first_query_value(payload, "date") or _first_query_value(payload, "market_date")
    if not date_text:
        return None
    try:
        return date.fromisoformat(str(date_text).replace("/", "-"))
    except ValueError as exc:
        raise ValueError("日期格式应为 YYYY-MM-DD。") from exc


def _validate_public_daily_market_brief_date(
    market: str,
    market_date: date | None,
    *,
    now: datetime | None = None,
) -> date:
    current = now or datetime.now(SHANGHAI_TZ)
    current_date = current.astimezone(MARKET_CONFIGS[market].timezone).date()
    resolved_date = market_date or resolve_latest_completed_session_date(market, now=current)
    if resolved_date > current_date:
        raise ValueError("不能生成未来日期的市场简报。")
    latest_completed = resolve_latest_completed_session_date(market, now=current)
    if resolved_date > latest_completed and resolved_date.weekday() < 5:
        raise ValueError(f"不能生成未来日期的市场简报；最近已收盘交易日为 {latest_completed.isoformat()}。")
    return resolved_date


def _public_history_job(job: dict[str, Any]) -> dict[str, Any]:
    job_fields = (
        "id",
        "request_type",
        "source",
        "status",
        "total_count",
        "completed_count",
        "succeeded_count",
        "skipped_count",
        "failed_count",
        "cancelled_count",
        "current_market",
        "current_market_date",
        "summary",
        "created_at",
        "updated_at",
        "completed_at",
    )
    item_fields = (
        "id",
        "market",
        "market_date",
        "status",
        "report_id",
        "skip_reason",
        "error_code",
        "error_summary",
        "finished_at",
    )
    public_job = {field: job.get(field) for field in job_fields if field in job}
    public_job["items"] = [
        {field: item.get(field) for field in item_fields if field in item}
        for item in (job.get("items") or [])
        if isinstance(item, dict)
    ]
    return public_job


def _daily_market_brief_response(report: dict[str, Any], *, status: str) -> dict[str, Any]:
    context = report.get("portfolio_snapshot") if isinstance(report.get("portfolio_snapshot"), dict) else {}
    return {
        "ok": True,
        "status": status,
        "market": context.get("market") or {},
        "market_date": context.get("market_date") or str(report.get("report_date") or ""),
        "context": _normalize_daily_market_brief_context(context),
        "markdown": report.get("summary") or "",
        "saved_report": report,
    }


def _normalize_daily_market_brief_context(context: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(context)
    normalized.setdefault("market", {})
    normalized.setdefault("market_date", "")
    normalized.setdefault("generated_at", {})
    normalized.setdefault("source_status", {})
    normalized.setdefault("indexes", [])
    normalized.setdefault("sectors", [])
    normalized.setdefault("gainers", [])
    normalized.setdefault("capital_flow", [])
    normalized.setdefault("warnings", [])
    normalized.setdefault("narrative", "")
    normalized.setdefault("provider_mode", "live")
    return normalized


def _empty_daily_market_brief_context(market: str, market_date: date | None) -> dict[str, Any]:
    return {
        "market": {"code": market, "name": {"CN": "A股", "HK": "港股", "US": "美股"}.get(market, market)},
        "market_date": market_date.isoformat() if market_date else "",
        "generated_at": {},
        "source_status": {},
        "indexes": [],
        "sectors": [],
        "gainers": [],
        "capital_flow": [],
        "warnings": [],
        "narrative": "",
        "provider_mode": "missing",
        "generation_kind": "missing",
    }


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


def _public_daily_market_brief_error(exc: Exception) -> str:
    return "每日市场简报处理失败：数据源或数据库暂时不可用，请稍后重试；维护者可查看服务日志定位具体原因。"


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
