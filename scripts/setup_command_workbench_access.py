#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import time
from typing import Any
from urllib import error, parse, request


DEFAULT_REPO = "coolCodeStudy/TurenAgentTool"
DEFAULT_WORKFLOW = "deploy.yml"
DEFAULT_REF = "main"
DEFAULT_CLOUD_BASE_URL = "http://47.84.190.191:8010"
DEFAULT_TOKEN_PATH = Path("~/.config/turen-agent/command_workbench_token").expanduser()
DEFAULT_GITHUB_TOKEN_FILES = (
    Path("/Users/lishaocheng/code/github_pat_only"),
    Path("/Users/lishaocheng/code/github_pat"),
)


class SetupError(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create local Command Workbench access and sync it to the cloud deployment secret."
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"GitHub repo, default: {DEFAULT_REPO}")
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW, help=f"Deploy workflow file, default: {DEFAULT_WORKFLOW}")
    parser.add_argument("--ref", default=DEFAULT_REF, help=f"Git ref to deploy, default: {DEFAULT_REF}")
    parser.add_argument("--cloud-base-url", default=DEFAULT_CLOUD_BASE_URL, help=f"Cloud base URL, default: {DEFAULT_CLOUD_BASE_URL}")
    parser.add_argument(
        "--token-file",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help=f"Local token cache path, default: {DEFAULT_TOKEN_PATH}",
    )
    parser.add_argument(
        "--github-token-file",
        type=Path,
        default=None,
        help="GitHub PAT file for gh; defaults to the repo's local PAT file convention when GH_TOKEN is unset.",
    )
    parser.add_argument("--rotate", action="store_true", help="Generate a new token even if the local token file exists.")
    parser.add_argument("--skip-secret", action="store_true", help="Do not update GitHub secret.")
    parser.add_argument("--skip-deploy", action="store_true", help="Do not trigger the deploy workflow.")
    parser.add_argument("--skip-verify", action="store_true", help="Do not verify cloud parse after deploy.")
    parser.add_argument("--no-wait", action="store_true", help="Do not wait for the deploy workflow to finish.")
    parser.add_argument("--open", action="store_true", help="Open the workbench URL and inject the token through a URL fragment.")
    args = parser.parse_args()

    token = ensure_token(args.token_file.expanduser(), rotate=args.rotate)
    github_env = build_github_env(args.github_token_file.expanduser() if args.github_token_file else None)
    print(f"local token: saved at {args.token_file.expanduser()}")

    if not args.skip_secret:
        set_github_secret(repo=args.repo, token=token, env=github_env)
        print("github secret: COMMAND_API_TOKEN updated")

    run_id: int | None = None
    if not args.skip_deploy:
        run_id = trigger_deploy(repo=args.repo, workflow=args.workflow, ref=args.ref, env=github_env)
        print(f"deploy: triggered {args.workflow} on {args.ref}")
        if not args.no_wait:
            run = wait_for_run(repo=args.repo, run_id=run_id, env=github_env)
            print(f"deploy: {run.get('conclusion') or run.get('status')} ({run.get('url') or 'no url'})")
            if run.get("conclusion") != "success":
                raise SetupError("deploy workflow did not succeed")

    if not args.skip_verify:
        verify_cloud_parse(base_url=args.cloud_base_url, token=token)
        print("cloud verify: command workbench parse accepted the local token")

    if args.open:
        open_workbench(base_url=args.cloud_base_url, token=token)
        print("browser: opened command workbench with local token bootstrap")
    else:
        print("browser: run again with --open to inject the token into the Command Workbench page")

    return 0


def ensure_token(path: Path, *, rotate: bool) -> str:
    if path.exists() and not rotate:
        token = path.read_text(encoding="utf-8").strip()
        if token:
            tighten_file_mode(path)
            return token

    token = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"{token}\n")
    tighten_file_mode(path)
    return token


def tighten_file_mode(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except PermissionError as exc:
        raise SetupError(f"cannot set token file permissions: {path}") from exc


def build_github_env(token_file: Path | None) -> dict[str, str]:
    env = os.environ.copy()
    if env.get("GH_TOKEN") or env.get("GITHUB_TOKEN"):
        return env

    candidates = [token_file] if token_file else list(DEFAULT_GITHUB_TOKEN_FILES)
    for candidate in candidates:
        if not candidate:
            continue
        if candidate.exists():
            lines = candidate.read_text(encoding="utf-8").splitlines()
            token = lines[0].strip() if lines else ""
            if token:
                env["GH_TOKEN"] = token
                return env
    return env


def set_github_secret(*, repo: str, token: str, env: dict[str, str]) -> None:
    run(
        ["gh", "secret", "set", "COMMAND_API_TOKEN", "--repo", repo, "--body-file", "-"],
        input_text=token,
        env=env,
        secret_safe_error="failed to set GitHub secret COMMAND_API_TOKEN",
    )


def trigger_deploy(*, repo: str, workflow: str, ref: str, env: dict[str, str]) -> int | None:
    started_at = time.time()
    run(["gh", "workflow", "run", workflow, "--repo", repo, "--ref", ref, "-f", "deploy_mode=quick"], env=env)
    time.sleep(5)
    runs = gh_json(
        [
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            workflow,
            "--branch",
            ref,
            "--event",
            "workflow_dispatch",
            "--limit",
            "10",
            "--json",
            "databaseId,createdAt,headBranch,status,conclusion,url",
        ],
        env=env,
    )
    if not isinstance(runs, list):
        raise SetupError("GitHub run list returned an unexpected payload")
    for item in runs:
        created_at = parse_github_time(str(item.get("createdAt") or ""))
        if created_at and created_at + 120 >= started_at:
            run_id = item.get("databaseId")
            return int(run_id) if run_id is not None else None
    return None


def wait_for_run(*, repo: str, run_id: int | None, env: dict[str, str], timeout_seconds: int = 900) -> dict[str, Any]:
    if run_id is None:
        raise SetupError("could not identify deploy workflow run")
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        data = gh_json(["run", "view", str(run_id), "--repo", repo, "--json", "status,conclusion,url"], env=env)
        if isinstance(data, dict) and data.get("status") == "completed":
            return data
        time.sleep(20)
    raise SetupError("timed out waiting for deploy workflow")


def verify_cloud_parse(*, base_url: str, token: str) -> None:
    endpoint = f"{base_url.rstrip('/')}/api/command-workbench/parse"
    body = json.dumps({"text": "决策 英特尔"}, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise SetupError(f"cloud parse returned HTTP {exc.code}: {redact_token(message, token)}") from exc
    except (TimeoutError, error.URLError, json.JSONDecodeError) as exc:
        raise SetupError(f"cloud parse verification failed: {exc}") from exc
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise SetupError("cloud parse returned an unexpected response")


def open_workbench(*, base_url: str, token: str) -> None:
    fragment = parse.urlencode({"access_token": token})
    url = f"{base_url.rstrip('/')}/command#{fragment}"
    import webbrowser

    if not webbrowser.open(url):
        raise SetupError("failed to open browser")


def gh_json(args: list[str], *, env: dict[str, str]) -> Any:
    result = run(["gh", *args], capture_output=True, env=env)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SetupError("gh returned invalid JSON") from exc


def run(
    args: list[str],
    *,
    input_text: str | None = None,
    capture_output: bool = False,
    env: dict[str, str] | None = None,
    secret_safe_error: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            input=input_text,
            text=True,
            check=True,
            capture_output=capture_output,
            env=env,
        )
    except FileNotFoundError as exc:
        raise SetupError(f"required command not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        if secret_safe_error:
            raise SetupError(secret_safe_error) from exc
        detail = (exc.stderr or exc.stdout or "").strip()
        raise SetupError(f"command failed: {' '.join(args)}{f': {detail}' if detail else ''}") from exc


def parse_github_time(value: str) -> float | None:
    if not value:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def redact_token(value: str, token: str) -> str:
    return value.replace(token, "<redacted>")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SetupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
