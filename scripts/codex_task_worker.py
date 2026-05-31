#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus, urlparse
from urllib.request import Request, urlopen

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


VALID_TERMINAL_STATUSES = {"done", "needs_user", "rejected", "cancelled"}


@dataclass(frozen=True)
class WorkerConfig:
    database_url: str
    repo_url: str
    work_dir: Path
    base_branch: str
    worker_name: str
    codex_bin: str
    codex_model: str | None
    danger_full_access: bool
    poll_seconds: int
    task_timeout_seconds: int
    test_command: str | None
    auto_push: bool
    auto_deploy: bool
    local_deploy: bool
    local_deploy_command: str | None
    local_deploy_build: bool
    deploy_workflow: str
    deploy_mode: str
    github_api_url: str
    github_token: str | None
    git_user_name: str
    git_user_email: str
    dingtalk_webhook: str | None
    dingtalk_secret: str | None
    notify_state_dir: Path
    startup_error_notify_cooldown_seconds: int


def main() -> None:
    parser = argparse.ArgumentParser(description="Run pending InvestmentKnowledge coding tasks with Codex CLI.")
    parser.add_argument("--once", action="store_true", help="Process at most one task and exit.")
    parser.add_argument("--loop", action="store_true", help="Poll forever.")
    args = parser.parse_args()

    if not args.once and not args.loop:
        args.once = True

    config = load_config()
    try:
        ensure_schema(config)
        record_worker_status(config, "starting", metadata={"pid": os.getpid()})
        ensure_codex_available(config.codex_bin)
        record_worker_status(config, "started", metadata={"pid": os.getpid()})
    except Exception as exc:
        message = f"worker startup failed: {exc}"
        print(message, flush=True)
        try:
            record_worker_status(config, "error", last_error=message, metadata={"pid": os.getpid()})
        except Exception:
            pass
        notify_dingtalk_once(
            config,
            dedupe_key=f"startup:{message}",
            content=f"Codex worker 启动失败。\n\n原因：{message}",
            cooldown_seconds=config.startup_error_notify_cooldown_seconds,
        )
        raise

    while True:
        try:
            record_worker_status(config, "idle")
            task = claim_next_task(config)
        except Exception as exc:
            message = f"claim task failed: {exc}"
            print(message, flush=True)
            try:
                record_worker_status(config, "error", last_error=message)
            except Exception:
                pass
            if args.once:
                raise
            time.sleep(config.poll_seconds)
            continue

        if task is None:
            if args.once:
                print("No pending coding task.", flush=True)
                return
            time.sleep(config.poll_seconds)
            continue

        try:
            record_worker_status(config, "running", metadata={"task_id": task["id"]})
            process_task(config, task)
            record_worker_status(config, "idle", metadata={"last_task_id": task["id"]})
        except Exception as exc:
            message = f"Codex worker failed: {exc}"
            notify_dingtalk(config, f"开发任务 #{task['id']} 处理失败。\n\n原因：{message}")
            record_worker_status(config, "error", last_error=message, metadata={"task_id": task["id"]})
            update_task(
                config,
                task_id=task["id"],
                status="needs_user",
                result=message,
                worker_log=message,
            )
            print(message, flush=True)

        if args.once:
            return


def load_config() -> WorkerConfig:
    database_url = (
        os.getenv("CODEX_WORKER_DATABASE_URL")
        or _database_url_from_parts()
    )
    if not database_url:
        raise RuntimeError("CODEX_WORKER_DATABASE_URL or POSTGRES_* environment is required")

    return WorkerConfig(
        database_url=database_url,
        repo_url=os.getenv("CODEX_WORKER_REPO_URL", "https://github.com/coolCodeStudy/TurenAgentTool.git"),
        work_dir=Path(os.getenv("CODEX_WORKER_DIR", "/opt/investment-knowledge-codex/repo")),
        base_branch=os.getenv("CODEX_WORKER_BASE_BRANCH", "main"),
        worker_name=os.getenv("CODEX_WORKER_NAME", "ecs-codex-worker"),
        codex_bin=os.getenv("CODEX_BIN", "codex"),
        codex_model=os.getenv("CODEX_WORKER_MODEL") or None,
        danger_full_access=_env_bool("CODEX_WORKER_DANGER_FULL_ACCESS", default=True),
        poll_seconds=int(os.getenv("CODEX_WORKER_POLL_SECONDS", "30")),
        task_timeout_seconds=int(os.getenv("CODEX_WORKER_TASK_TIMEOUT_SECONDS", "3600")),
        test_command=os.getenv("CODEX_WORKER_TEST_COMMAND") or None,
        auto_push=_env_bool("CODEX_WORKER_AUTO_PUSH", default=True),
        auto_deploy=_env_bool("CODEX_WORKER_AUTO_DEPLOY", default=False),
        local_deploy=_env_bool("CODEX_WORKER_LOCAL_DEPLOY", default=True),
        local_deploy_command=os.getenv("CODEX_WORKER_LOCAL_DEPLOY_COMMAND") or None,
        local_deploy_build=_env_bool("CODEX_WORKER_LOCAL_DEPLOY_BUILD", default=False),
        deploy_workflow=os.getenv("CODEX_WORKER_DEPLOY_WORKFLOW", "deploy.yml"),
        deploy_mode=os.getenv("CODEX_WORKER_DEPLOY_MODE", "auto"),
        github_api_url=os.getenv("GITHUB_API_URL", "https://api.github.com"),
        github_token=os.getenv("CODEX_WORKER_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN") or None,
        git_user_name=os.getenv("CODEX_WORKER_GIT_USER_NAME", "InvestmentKnowledge Codex Worker"),
        git_user_email=os.getenv("CODEX_WORKER_GIT_USER_EMAIL", "codex-worker@users.noreply.github.com"),
        dingtalk_webhook=os.getenv("DINGTALK_SEND_WEBHOOK") or None,
        dingtalk_secret=os.getenv("DINGTALK_SEND_SECRET") or None,
        notify_state_dir=Path(os.getenv("CODEX_WORKER_NOTIFY_STATE_DIR", "/var/lib/investment-knowledge-codex")),
        startup_error_notify_cooldown_seconds=int(
            os.getenv("CODEX_WORKER_STARTUP_ERROR_NOTIFY_COOLDOWN_SECONDS", "3600")
        ),
    )


def _database_url_from_parts() -> str | None:
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        return None
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "55432")
    user = os.getenv("POSTGRES_USER", "postgres")
    db = os.getenv("POSTGRES_DB", "investment_kg")
    return f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{quote(db)}"


def _env_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def ensure_codex_available(codex_bin: str) -> None:
    if shutil.which(codex_bin) is None:
        raise RuntimeError(f"Codex CLI is not available: {codex_bin}")


def claim_next_task(config: WorkerConfig) -> dict[str, Any] | None:
    with psycopg.connect(config.database_url, row_factory=dict_row) as conn:
        with conn.transaction():
            return conn.execute(
                """
                WITH next_task AS (
                  SELECT id
                  FROM coding_tasks
                  WHERE status IN ('pending', 'accepted')
                  ORDER BY
                    CASE priority
                      WHEN 'high' THEN 0
                      WHEN 'normal' THEN 1
                      ELSE 2
                    END,
                    created_at ASC
                  LIMIT 1
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE coding_tasks AS task SET
                  status = 'running',
                  worker_started_at = COALESCE(worker_started_at, now()),
                  updated_at = now(),
                  worker_log = concat_ws(E'\n', NULLIF(worker_log, ''), %s)
                FROM next_task
                WHERE task.id = next_task.id
                RETURNING task.*
                """,
                (f"{config.worker_name}: claimed task",),
            ).fetchone()


def ensure_schema(config: WorkerConfig) -> None:
    schema_path = Path(os.getenv("CODEX_WORKER_SCHEMA_PATH", "/opt/investment-knowledge/db/schema.sql"))
    if not schema_path.exists():
        return
    schema_sql = schema_path.read_text(encoding="utf-8")
    with psycopg.connect(config.database_url, row_factory=dict_row) as conn:
        conn.execute(schema_sql)


def record_worker_status(
    config: WorkerConfig,
    status: str,
    last_error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    with psycopg.connect(config.database_url, row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO worker_status (name, status, last_seen_at, last_error, metadata, updated_at)
                VALUES (%s, %s, now(), %s, %s, now())
                ON CONFLICT (name) DO UPDATE SET
                  status = EXCLUDED.status,
                  last_seen_at = now(),
                  last_error = EXCLUDED.last_error,
                  metadata = EXCLUDED.metadata,
                  updated_at = now()
                """,
                (
                    config.worker_name,
                    status,
                    last_error,
                    Jsonb(metadata or {}),
                ),
            )


def update_task(
    config: WorkerConfig,
    task_id: int,
    status: str,
    result: str | None = None,
    branch_name: str | None = None,
    commit_sha: str | None = None,
    worker_log: str | None = None,
) -> None:
    if status not in {"pending", "accepted", "running", "needs_user", "done", "rejected", "cancelled"}:
        raise ValueError(f"invalid status: {status}")
    finished = status in VALID_TERMINAL_STATUSES
    with psycopg.connect(config.database_url, row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute(
                """
                UPDATE coding_tasks SET
                  status = %s,
                  result = COALESCE(%s, result),
                  branch_name = COALESCE(%s, branch_name),
                  commit_sha = COALESCE(%s, commit_sha),
                  worker_log = concat_ws(E'\n', NULLIF(worker_log, ''), NULLIF(%s, '')),
                  worker_finished_at = CASE
                    WHEN %s THEN now()
                    ELSE worker_finished_at
                  END,
                  updated_at = now()
                WHERE id = %s
                """,
                (
                    status,
                    result,
                    branch_name,
                    commit_sha,
                    worker_log,
                    finished,
                    task_id,
                ),
            )


def process_task(config: WorkerConfig, task: dict[str, Any]) -> None:
    task_id = int(task["id"])
    branch_name = build_branch_name(task)
    print(f"Processing task #{task_id}: {task['title']}", flush=True)

    prepare_repo(config, branch_name)

    with tempfile.TemporaryDirectory(prefix=f"codex-task-{task_id}-") as tmp:
        output_path = Path(tmp) / "codex-final.txt"
        prompt = build_codex_prompt(task, branch_name)
        run_codex(config, prompt=prompt, output_path=output_path)
        codex_final = output_path.read_text(encoding="utf-8") if output_path.exists() else ""

    changed = git_status_changed(config.work_dir)
    if not changed:
        update_task(
            config,
            task_id=task_id,
            status="needs_user",
            result=(codex_final or "Codex finished but produced no file changes.")[:4000],
            branch_name=branch_name,
            worker_log="Codex produced no file changes.",
        )
        return

    if config.test_command:
        run_shell(config.test_command, cwd=config.work_dir, timeout=config.task_timeout_seconds)

    commit_sha = commit_changes(config, task, branch_name)
    pushed = False
    if config.auto_push:
        push_branch(config, branch_name)
        pushed = True

    deploy_triggered = False
    deploy_message = ""
    local_deployed = False
    local_deploy_message = ""
    if config.local_deploy:
        local_deploy_message = deploy_locally(config)
        local_deployed = True
    if pushed and config.auto_deploy:
        deploy_message = trigger_deploy_workflow(config, branch_name)
        deploy_triggered = True

    result = render_result(
        task,
        branch_name,
        commit_sha,
        pushed,
        local_deployed,
        local_deploy_message,
        deploy_triggered,
        deploy_message,
        codex_final,
    )
    update_task(
        config,
        task_id=task_id,
        status="done",
        result=result,
        branch_name=branch_name,
        commit_sha=commit_sha,
        worker_log="Codex task completed.",
    )
    notify_dingtalk(config, result)


def prepare_repo(config: WorkerConfig, branch_name: str) -> None:
    remote_url = authenticated_repo_url(config)
    config.work_dir.parent.mkdir(parents=True, exist_ok=True)

    if not (config.work_dir / ".git").exists():
        run(["git", "clone", remote_url, str(config.work_dir)], cwd=config.work_dir.parent)
    else:
        run(["git", "remote", "set-url", "origin", remote_url], cwd=config.work_dir)

    run(["git", "fetch", "origin", config.base_branch], cwd=config.work_dir)
    run(["git", "checkout", "-B", branch_name, f"origin/{config.base_branch}"], cwd=config.work_dir)
    run(["git", "reset", "--hard", f"origin/{config.base_branch}"], cwd=config.work_dir)
    run(["git", "clean", "-fd"], cwd=config.work_dir)
    run(["git", "config", "user.name", config.git_user_name], cwd=config.work_dir)
    run(["git", "config", "user.email", config.git_user_email], cwd=config.work_dir)


def authenticated_repo_url(config: WorkerConfig) -> str:
    if not config.github_token or not config.repo_url.startswith("https://github.com/"):
        return config.repo_url
    return config.repo_url.replace("https://github.com/", f"https://x-access-token:{quote(config.github_token)}@github.com/", 1)


def build_branch_name(task: dict[str, Any]) -> str:
    title = re.sub(r"[^a-zA-Z0-9]+", "-", str(task["title"]).lower()).strip("-")
    if not title:
        title = "task"
    return f"codex/task-{task['id']}-{title[:36]}"


def build_codex_prompt(task: dict[str, Any], branch_name: str) -> str:
    return f"""你是 InvestmentKnowledge/TurenAgentTool 的云端 Codex worker。

任务 #{task['id']}: {task['title']}

描述:
{task.get('description') or task['title']}

执行要求:
- 直接在当前仓库完成实现，保持改动聚焦。
- 先读相关代码，再修改；不要改动无关文件。
- 不要读取或打印任何真实密钥、token、密码、webhook。
- 不要执行破坏性 git 操作影响 origin/main；当前分支是 {branch_name}。
- 完成后运行你认为必要的轻量验证；如果无法验证，在最终说明里写清楚。
- 不要自己 git commit / git push，worker 会统一提交和推送。
- 用中文给出最终摘要，包含改了什么、如何验证、剩余风险。
"""


def run_codex(config: WorkerConfig, prompt: str, output_path: Path) -> None:
    args = [
        config.codex_bin,
        "exec",
        "--cd",
        str(config.work_dir),
        "--ask-for-approval",
        "never",
        "--output-last-message",
        str(output_path),
    ]
    if config.danger_full_access:
        args.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        args.extend(["--sandbox", "workspace-write"])
    if config.codex_model:
        args.extend(["--model", config.codex_model])
    args.append(prompt)
    run(args, cwd=config.work_dir, timeout=config.task_timeout_seconds)


def git_status_changed(work_dir: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=work_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return bool(result.stdout.strip())


def commit_changes(config: WorkerConfig, task: dict[str, Any], branch_name: str) -> str:
    run(["git", "add", "-A"], cwd=config.work_dir)
    title = str(task["title"]).strip()
    run(["git", "commit", "-m", f"Task #{task['id']}: {title[:68]}"], cwd=config.work_dir)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=config.work_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


def push_branch(config: WorkerConfig, branch_name: str) -> None:
    run(["git", "push", "-u", "origin", branch_name], cwd=config.work_dir, timeout=config.task_timeout_seconds)


def deploy_locally(config: WorkerConfig) -> str:
    if config.local_deploy_command:
        run_shell(config.local_deploy_command, cwd=config.work_dir, timeout=config.task_timeout_seconds)
        return f"Ran local deploy command: {config.local_deploy_command}"

    script_path = config.work_dir / "scripts" / "deploy_from_local_checkout.sh"
    if not script_path.exists():
        raise RuntimeError(f"local deploy script not found: {script_path}")

    env = os.environ.copy()
    env["SOURCE_DIR"] = str(config.work_dir)
    env.setdefault("APP_DIR", "/opt/investment-knowledge")
    env["BUILD_IMAGE"] = "true" if config.local_deploy_build else "false"
    run([str(script_path)], cwd=config.work_dir, timeout=config.task_timeout_seconds, env=env)
    return f"Deployed locally to {env['APP_DIR']} (build_image={env['BUILD_IMAGE']})"


def trigger_deploy_workflow(config: WorkerConfig, branch_name: str) -> str:
    if not config.github_token:
        raise RuntimeError("CODEX_WORKER_GITHUB_TOKEN is required to trigger deployment")

    owner, repo = parse_github_repo(config.repo_url)
    url = (
        f"{config.github_api_url.rstrip('/')}/repos/{owner}/{repo}"
        f"/actions/workflows/{quote(config.deploy_workflow, safe='')}/dispatches"
    )
    payload = json.dumps(
        {
            "ref": branch_name,
            "inputs": {
                "deploy_mode": config.deploy_mode,
            },
        }
    ).encode("utf-8")
    request = Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {config.github_token}",
            "Content-Type": "application/json",
            "User-Agent": "investment-knowledge-codex-worker",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=30) as response:
        if response.status != 204:
            raise RuntimeError(f"GitHub workflow dispatch returned HTTP {response.status}")
    return f"Triggered {config.deploy_workflow} on {branch_name} with deploy_mode={config.deploy_mode}"


def parse_github_repo(repo_url: str) -> tuple[str, str]:
    if repo_url.startswith("git@github.com:"):
        path = repo_url.removeprefix("git@github.com:")
    else:
        parsed = urlparse(repo_url)
        path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"cannot parse GitHub repo url: {repo_url}")
    return parts[-2], parts[-1]


def render_result(
    task: dict[str, Any],
    branch_name: str,
    commit_sha: str,
    pushed: bool,
    local_deployed: bool,
    local_deploy_message: str,
    deploy_triggered: bool,
    deploy_message: str,
    codex_final: str,
) -> str:
    lines = [
        f"开发任务 #{task['id']} 已完成。",
        f"- 分支: {branch_name}",
        f"- commit: {commit_sha}",
        f"- 已推送: {'是' if pushed else '否'}",
        f"- 已本机部署: {'是' if local_deployed else '否'}",
        f"- 已触发 GitHub 部署: {'是' if deploy_triggered else '否'}",
    ]
    if local_deploy_message:
        lines.append(f"- 本机部署: {local_deploy_message}")
    if deploy_message:
        lines.append(f"- GitHub 部署: {deploy_message}")
    if codex_final.strip():
        lines.extend(["", "Codex 摘要:", codex_final.strip()[:3000]])
    return "\n".join(lines)


def notify_dingtalk(config: WorkerConfig, content: str) -> None:
    if not config.dingtalk_webhook:
        return
    payload = json.dumps(
        {
            "msgtype": "text",
            "text": {"content": truncate_text(content, 3500)},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        signed_dingtalk_webhook(config.dingtalk_webhook, config.dingtalk_secret),
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status >= 300:
                print(f"DingTalk notify failed: HTTP {response.status} {body[:300]}", flush=True)
    except Exception as exc:
        print(f"DingTalk notify failed: {exc}", flush=True)


def notify_dingtalk_once(
    config: WorkerConfig,
    dedupe_key: str,
    content: str,
    cooldown_seconds: int,
) -> None:
    if not config.dingtalk_webhook:
        return
    if cooldown_seconds <= 0:
        notify_dingtalk(config, content)
        return

    digest = hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()
    state_path = config.notify_state_dir / f"notify-{digest}.json"
    now = time.time()
    try:
        config.notify_state_dir.mkdir(parents=True, exist_ok=True)
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            last_sent_at = float(state.get("last_sent_at") or 0)
            if now - last_sent_at < cooldown_seconds:
                print("DingTalk notify skipped by cooldown.", flush=True)
                return
        notify_dingtalk(config, content)
        state_path.write_text(
            json.dumps({"last_sent_at": now, "dedupe_key": dedupe_key}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"DingTalk notify cooldown failed: {exc}", flush=True)
        notify_dingtalk(config, content)


def signed_dingtalk_webhook(webhook: str, secret: str | None) -> str:
    if not secret:
        return webhook
    timestamp = str(int(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    sign = quote_plus(base64.b64encode(digest).decode("utf-8"))
    separator = "&" if "?" in webhook else "?"
    return f"{webhook}{separator}timestamp={timestamp}&sign={sign}"


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n...内容过长，已截断。"


def run(args: list[str], cwd: Path, timeout: int = 3600, env: dict[str, str] | None = None) -> None:
    display = sanitize_command(args)
    print(f"$ {' '.join(display)}", flush=True)
    subprocess.run(args, cwd=cwd, check=True, timeout=timeout, env=env)


def run_shell(command: str, cwd: Path, timeout: int = 3600) -> None:
    print(f"$ {command}", flush=True)
    subprocess.run(command, cwd=cwd, shell=True, check=True, timeout=timeout)


def sanitize_command(args: list[str]) -> list[str]:
    return [re.sub(r"x-access-token:[^@]+@", "x-access-token:<redacted>@", item) for item in args]


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
