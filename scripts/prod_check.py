from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOKEN = "prod-check-token"


class CheckFailed(RuntimeError):
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a pre-production health check.")
    parser.add_argument("--host", default="localhost", help="Service host to check.")
    parser.add_argument("--mcp-port", type=int, default=int(os.getenv("MCP_HOST_PORT", "8000")))
    parser.add_argument("--command-port", type=int, default=int(os.getenv("COMMAND_API_HOST_PORT", "8001")))
    parser.add_argument("--dingtalk-port", type=int, default=int(os.getenv("DINGTALK_API_HOST_PORT", "8002")))
    parser.add_argument("--command-token", default=os.getenv("COMMAND_API_TOKEN", DEFAULT_TOKEN))
    parser.add_argument(
        "--analysis-command",
        default=None,
        help="Optional natural-language analysis command to validate, for example: 怎么看海力士.",
    )
    parser.add_argument(
        "--command-text",
        dest="analysis_command",
        help="Deprecated alias for --analysis-command.",
    )
    parser.add_argument("--start-prod", action="store_true", help="Start docker-compose.prod.yml before checks.")
    parser.add_argument("--down-after", action="store_true", help="Stop the prod compose stack after checks.")
    parser.add_argument("--skip-mcp", action="store_true", help="Skip MCP HTTP reachability check.")
    parser.add_argument(
        "--project-name",
        default=os.getenv("PROD_CHECK_PROJECT_NAME", "investment-kg-prod-check"),
        help="Docker Compose project name used by --start-prod.",
    )
    args = parser.parse_args()

    env = _compose_env(args.command_token)
    env["COMPOSE_PROJECT_NAME"] = args.project_name
    checks: list[tuple[str, bool, str]] = []

    try:
        _check_compose_config(env)
        checks.append(("compose config", True, "docker-compose.prod.yml can be parsed"))

        if args.start_prod:
            _compose(["up", "-d", "--build"], env=env)
            _wait_for_http(f"http://{args.host}:{args.command_port}/health")
            _wait_for_http(f"http://{args.host}:{args.dingtalk_port}/health")
            checks.append(("compose up", True, "prod stack started"))

        if not args.skip_mcp:
            status = _check_mcp_endpoint(f"http://{args.host}:{args.mcp_port}/mcp")
            checks.append(("mcp endpoint", True, f"reachable with HTTP {status}"))

        _expect_json(
            "command health",
            checks,
            _http_get_json(f"http://{args.host}:{args.command_port}/health"),
            lambda status, body: status == 200 and body.get("ok") is True,
        )
        _expect_json(
            "command unauthorized",
            checks,
            _http_post_json(
                f"http://{args.host}:{args.command_port}/command",
                {"text": "查看候选心得", "sender": "prod-check", "source": "prod-check"},
            ),
            lambda status, body: status == 401 and body.get("error") == "unauthorized",
        )
        _expect_json(
            "command authorized query",
            checks,
            _http_post_json(
                f"http://{args.host}:{args.command_port}/command",
                {"text": "帮助", "sender": "prod-check", "source": "prod-check"},
                headers={"Authorization": f"Bearer {args.command_token}"},
            ),
            lambda status, body: status == 200 and body.get("ok") is True and "支持的指令" in body.get("message", ""),
        )
        _expect_json(
            "dingtalk health",
            checks,
            _http_get_json(f"http://{args.host}:{args.dingtalk_port}/health"),
            lambda status, body: status == 200 and body.get("ok") is True,
        )
        _expect_json(
            "dingtalk query",
            checks,
            _http_post_json(
                f"http://{args.host}:{args.dingtalk_port}/dingtalk/webhook",
                {"msgtype": "text", "text": {"content": "查看候选心得"}, "senderNick": "prod-check"},
            ),
            lambda status, body: status == 200 and body.get("msgtype") == "text" and "候选心得" in _text_content(body),
        )
        _expect_json(
            "dingtalk write guard",
            checks,
            _http_post_json(
                f"http://{args.host}:{args.dingtalk_port}/dingtalk/webhook",
                {"msgtype": "text", "text": {"content": "确认候选心得 5"}, "senderNick": "prod-check"},
            ),
            lambda status, body: status == 200 and "只开放查询类指令" in _text_content(body),
        )
        if args.analysis_command:
            _expect_json(
                "command natural analysis",
                checks,
                _http_post_json(
                    f"http://{args.host}:{args.command_port}/command",
                    {"text": args.analysis_command, "sender": "prod-check", "source": "prod-check"},
                    headers={"Authorization": f"Bearer {args.command_token}"},
                ),
                lambda status, body: status == 200
                and body.get("ok") is True
                and "核心判断" in body.get("message", ""),
            )
    except Exception as exc:
        checks.append(("failed", False, str(exc)))
        _print_checks(checks)
        raise SystemExit(1) from exc
    finally:
        if args.start_prod and args.down_after:
            _compose(["down"], env=env)

    _print_checks(checks)


def _compose_env(command_token: str) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("COMMAND_API_TOKEN", command_token)
    env.setdefault("POSTGRES_PASSWORD", "postgres")
    env.setdefault("POSTGRES_DB", "investment_kg")
    env.setdefault("POSTGRES_USER", "postgres")
    return env


def _check_compose_config(env: dict[str, str]) -> None:
    _compose(["config"], env=env)


def _compose(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose", "-p", env["COMPOSE_PROJECT_NAME"], "-f", "docker-compose.prod.yml", *args]
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def _wait_for_http(url: str, timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            status, _ = _http_get(url, timeout_seconds=3)
            if 200 <= status < 500:
                return
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    raise CheckFailed(f"timed out waiting for {url}: {last_error}")


def _check_mcp_endpoint(url: str, timeout_seconds: int = 30) -> int:
    expected_statuses = {200, 400, 404, 405, 406}
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            status, _ = _http_get(url, timeout_seconds=3)
            if status in expected_statuses:
                return status
            last_error = CheckFailed(f"unexpected MCP status: {status}")
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    raise CheckFailed(f"MCP endpoint was not ready: {last_error}")


def _http_get_json(url: str) -> tuple[int, dict[str, Any]]:
    status, body = _http_get(url)
    return status, _decode_json(body)


def _http_get(url: str, timeout_seconds: int = 10) -> tuple[int, str]:
    request = Request(url, method="GET")
    return _open(request, timeout_seconds=timeout_seconds)


def _http_post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=data, headers=request_headers, method="POST")
    status, body = _open(request)
    return status, _decode_json(body)


def _open(request: Request, timeout_seconds: int = 10) -> tuple[int, str]:
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except URLError as exc:
        raise CheckFailed(f"{request.full_url} unreachable: {exc}") from exc
    except OSError as exc:
        raise CheckFailed(f"{request.full_url} connection failed: {exc}") from exc


def _decode_json(body: str) -> dict[str, Any]:
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CheckFailed(f"response is not JSON: {body[:200]}") from exc
    if not isinstance(value, dict):
        raise CheckFailed(f"response JSON is not an object: {value!r}")
    return value


def _expect_json(
    name: str,
    checks: list[tuple[str, bool, str]],
    response: tuple[int, dict[str, Any]],
    predicate: Any,
) -> None:
    status, body = response
    if not predicate(status, body):
        raise CheckFailed(f"{name} failed: status={status}, body={body}")
    checks.append((name, True, f"HTTP {status}"))


def _text_content(body: dict[str, Any]) -> str:
    text = body.get("text")
    if isinstance(text, dict):
        return str(text.get("content") or "")
    return ""


def _print_checks(checks: list[tuple[str, bool, str]]) -> None:
    print("Production readiness check:")
    for name, ok, detail in checks:
        mark = "OK" if ok else "FAIL"
        print(f"- [{mark}] {name}: {detail}")


if __name__ == "__main__":
    main()
