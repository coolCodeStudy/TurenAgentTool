from __future__ import annotations

import fnmatch
import json
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

try:
    from scripts.deploy_support import CommandRunner
except ModuleNotFoundError:  # Direct execution through scripts/classify_deploy_change.py.
    from deploy_support import CommandRunner


APPLICATION_SERVICES = (
    "account-snapshot-scheduler",
    "command-api",
    "daily-market-brief-scheduler",
    "dingtalk-api",
    "dingtalk-stream-bot",
    "ipo-reminder-scheduler",
    "mcp",
    "weekly-review-web",
)


class DeployMode(str, Enum):
    NO_DEPLOY = "no_deploy"
    TARGETED_QUICK = "targeted_quick"
    CONFIG_RESTART = "config_restart"
    FULL_IMAGE = "full_image"


MODE_RANK = {
    DeployMode.NO_DEPLOY: 0,
    DeployMode.TARGETED_QUICK: 1,
    DeployMode.CONFIG_RESTART: 2,
    DeployMode.FULL_IMAGE: 3,
}


@dataclass(frozen=True)
class DeploymentPlan:
    mode: DeployMode
    targets: tuple[str, ...]
    changed_files: tuple[str, ...]
    image_input_files: tuple[str, ...]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", tuple(sorted(set(self.targets))))
        object.__setattr__(self, "changed_files", tuple(sorted(set(self.changed_files))))
        object.__setattr__(self, "image_input_files", tuple(sorted(set(self.image_input_files))))
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons))))


@dataclass(frozen=True)
class PathRule:
    pattern: str
    mode: DeployMode
    targets: tuple[str, ...]
    reason: str
    image_input: bool = False


# Ordered from the narrowest, explicitly-owned paths to conservative fallbacks.
PATH_RULES = (
    PathRule("AGENTS.md", DeployMode.NO_DEPLOY, (), "agent governance"),
    PathRule("README.md", DeployMode.NO_DEPLOY, (), "repository documentation"),
    PathRule("DEPLOYMENT.md", DeployMode.NO_DEPLOY, (), "repository documentation"),
    PathRule("系统设计.md", DeployMode.NO_DEPLOY, (), "repository documentation"),
    PathRule("docs/**", DeployMode.NO_DEPLOY, (), "repository documentation"),
    PathRule("prompts/**", DeployMode.NO_DEPLOY, (), "repository prompt"),
    PathRule("tests/**", DeployMode.NO_DEPLOY, (), "tests"),
    PathRule(".github/workflows/codex-worker.yml", DeployMode.NO_DEPLOY, (), "workflow governance"),
    PathRule(".github/workflows/deploy.yml", DeployMode.NO_DEPLOY, (), "workflow governance"),
    PathRule(".github/workflows/ops-api.yml", DeployMode.NO_DEPLOY, (), "workflow governance"),
    PathRule("scripts/agent_preflight.py", DeployMode.NO_DEPLOY, (), "local audit"),
    PathRule("scripts/audit_agent_flow_health.py", DeployMode.NO_DEPLOY, (), "local audit"),
    PathRule("scripts/audit_delivery_state.py", DeployMode.NO_DEPLOY, (), "local audit"),
    PathRule("scripts/audit_prd_status.py", DeployMode.NO_DEPLOY, (), "local audit"),
    PathRule("scripts/classify_deploy_change.py", DeployMode.NO_DEPLOY, (), "local deploy classifier"),
    PathRule("scripts/evaluate_agent_flow_cases.py", DeployMode.NO_DEPLOY, (), "local evaluation"),
    PathRule("scripts/bootstrap_deploy_baseline.py", DeployMode.NO_DEPLOY, (), "ECS Ops API control plane"),
    PathRule("scripts/bootstrap_ops_api_v2_on_ecs.sh", DeployMode.NO_DEPLOY, (), "ECS Ops API control plane"),
    PathRule("scripts/deploy_contract.py", DeployMode.NO_DEPLOY, (), "ECS Ops API control plane"),
    PathRule("scripts/deploy_preflight.py", DeployMode.NO_DEPLOY, (), "ECS Ops API control plane"),
    PathRule("scripts/deploy_release.py", DeployMode.NO_DEPLOY, (), "ECS Ops API control plane"),
    PathRule("scripts/deploy_retention.py", DeployMode.NO_DEPLOY, (), "ECS Ops API control plane"),
    PathRule("scripts/deploy_state.py", DeployMode.NO_DEPLOY, (), "ECS Ops API control plane"),
    PathRule("scripts/deploy_support.py", DeployMode.NO_DEPLOY, (), "ECS Ops API control plane"),
    PathRule("scripts/install_ops_api_on_ecs.sh", DeployMode.NO_DEPLOY, (), "ECS Ops API control plane"),
    PathRule(
        "scripts/deploy_from_local_checkout.sh",
        DeployMode.NO_DEPLOY,
        (),
        "ECS deployment control plane",
    ),
    PathRule("scripts/ecs_ops_api.py", DeployMode.NO_DEPLOY, (), "ECS Ops API control plane"),
    PathRule(
        "scripts/dingtalk_stream_bot.py",
        DeployMode.TARGETED_QUICK,
        ("dingtalk-stream-bot",),
        "DingTalk stream bot runtime",
    ),
    PathRule(
        "scripts/init_db.py",
        DeployMode.TARGETED_QUICK,
        ("command-api", "dingtalk-api", "dingtalk-stream-bot", "mcp", "weekly-review-web"),
        "database initialization runtime",
    ),
    PathRule("investment_knowledge_mcp/weekly_review_web.py", DeployMode.TARGETED_QUICK, ("weekly-review-web",), "weekly review web"),
    PathRule(
        "investment_knowledge_mcp/command_workbench.py",
        DeployMode.TARGETED_QUICK,
        ("command-api", "weekly-review-web"),
        "command workbench",
    ),
    PathRule(
        "investment_knowledge_mcp/command_router.py",
        DeployMode.TARGETED_QUICK,
        ("command-api", "dingtalk-api", "dingtalk-stream-bot", "mcp", "weekly-review-web"),
        "shared command logic",
    ),
    PathRule(
        "investment_knowledge_mcp/daily_market_brief.py",
        DeployMode.TARGETED_QUICK,
        ("command-api", "daily-market-brief-scheduler", "dingtalk-api", "dingtalk-stream-bot", "mcp", "weekly-review-web"),
        "shared command logic",
    ),
    PathRule(
        "investment_knowledge_mcp/weekly_review.py",
        DeployMode.TARGETED_QUICK,
        ("command-api", "dingtalk-api", "dingtalk-stream-bot", "mcp", "weekly-review-web"),
        "shared command logic",
    ),
    PathRule("investment_knowledge_mcp/command_api.py", DeployMode.TARGETED_QUICK, ("command-api",), "command API"),
    PathRule("investment_knowledge_mcp/server.py", DeployMode.TARGETED_QUICK, ("mcp",), "MCP server"),
    PathRule(
        "investment_knowledge_mcp/account_snapshots.py",
        DeployMode.TARGETED_QUICK,
        ("account-snapshot-scheduler",),
        "account snapshot scheduler",
    ),
    PathRule(
        "investment_knowledge_mcp/ipo_reminders.py",
        DeployMode.TARGETED_QUICK,
        ("ipo-reminder-scheduler",),
        "IPO reminder scheduler",
    ),
    PathRule("investment_knowledge_mcp/**", DeployMode.TARGETED_QUICK, APPLICATION_SERVICES, "unknown application runtime module"),
    PathRule("db/**", DeployMode.TARGETED_QUICK, APPLICATION_SERVICES, "database runtime input"),
    PathRule("Dockerfile", DeployMode.FULL_IMAGE, APPLICATION_SERVICES, "Docker image input", True),
    PathRule("Dockerfile.*", DeployMode.FULL_IMAGE, APPLICATION_SERVICES, "Docker image input", True),
    PathRule("requirements*.txt", DeployMode.FULL_IMAGE, APPLICATION_SERVICES, "dependency image input", True),
    PathRule("pyproject.toml", DeployMode.FULL_IMAGE, APPLICATION_SERVICES, "package image input", True),
    PathRule("poetry.lock", DeployMode.FULL_IMAGE, APPLICATION_SERVICES, "package image input", True),
    PathRule("package.json", DeployMode.FULL_IMAGE, APPLICATION_SERVICES, "package image input", True),
    PathRule("package-lock.json", DeployMode.FULL_IMAGE, APPLICATION_SERVICES, "package image input", True),
    PathRule("docker-compose.prod.yml", DeployMode.CONFIG_RESTART, APPLICATION_SERVICES, "runtime Compose configuration"),
)


def classify_paths(
    changed_files: Iterable[str], *, compose_image_changed: bool
) -> DeploymentPlan:
    """Return the smallest safe deterministic plan or raise on an unknown control path."""
    paths = tuple(sorted({_normalize_path(path) for path in changed_files if _normalize_path(path)}))
    if not paths:
        return DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=APPLICATION_SERVICES,
            changed_files=(),
            image_input_files=(),
            reasons=("empty change set requires a conservative full image deploy",),
        )

    mode = DeployMode.NO_DEPLOY
    targets: set[str] = set()
    image_inputs: set[str] = set()
    reasons: set[str] = set()
    for path in paths:
        rule = _rule_for(path)
        if rule is None:
            if _is_deployment_sensitive(path):
                raise ValueError(f"unclassified deployment-sensitive path: {path}")
            rule = PathRule(path, DeployMode.FULL_IMAGE, APPLICATION_SERVICES, "unclassified image/package path", True)

        selected_mode = rule.mode
        image_input = rule.image_input
        if path == "docker-compose.prod.yml" and compose_image_changed:
            selected_mode = DeployMode.FULL_IMAGE
            image_input = True
            reasons.add(f"{path}: normalized Compose image input changed")

        if MODE_RANK[selected_mode] > MODE_RANK[mode]:
            mode = selected_mode
        targets.update(rule.targets)
        if image_input:
            image_inputs.add(path)
        reasons.add(f"{path}: {rule.reason}")

    return DeploymentPlan(
        mode=mode,
        targets=tuple(targets),
        changed_files=paths,
        image_input_files=tuple(image_inputs),
        reasons=tuple(reasons),
    )


def classify_deployment(
    repo: Path, base_sha: str, target_sha: str, runner: CommandRunner
) -> DeploymentPlan:
    """Read git diff and normalized Compose config at both SHAs, then classify."""
    changed_files = _read_changed_files(repo, base_sha, target_sha, runner)
    compose_image_changed = False
    if "docker-compose.prod.yml" in changed_files:
        compose_image_changed = _compose_image_inputs_changed(repo, base_sha, target_sha, runner)
    return classify_paths(changed_files, compose_image_changed=compose_image_changed)


def serialize_plan(plan: DeploymentPlan) -> dict[str, object]:
    return {
        "mode": plan.mode.value,
        "targets": list(plan.targets),
        "changed_files": list(plan.changed_files),
        "image_input_files": list(plan.image_input_files),
        "reasons": list(plan.reasons),
    }


def _read_changed_files(repo: Path, base_sha: str, target_sha: str, runner: CommandRunner) -> tuple[str, ...]:
    result = runner.run(("git", "-C", str(repo), "diff", "--name-only", base_sha, target_sha))
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return tuple(line for line in result.stdout.splitlines() if line.strip())


def _compose_image_inputs_changed(repo: Path, base_sha: str, target_sha: str, runner: CommandRunner) -> bool:
    base_compose = _git_show(repo, base_sha, runner)
    target_compose = _git_show(repo, target_sha, runner)
    with tempfile.TemporaryDirectory(prefix="deploy-compose-") as directory:
        base_path = Path(directory) / "base.yml"
        target_path = Path(directory) / "target.yml"
        base_path.write_text(base_compose, encoding="utf-8")
        target_path.write_text(target_compose, encoding="utf-8")
        return _compose_image_inputs(_compose_config(base_path, runner)) != _compose_image_inputs(
            _compose_config(target_path, runner)
        )


def _git_show(repo: Path, sha: str, runner: CommandRunner) -> str:
    result = runner.run(("git", "-C", str(repo), "show", f"{sha}:docker-compose.prod.yml"))
    if result.returncode != 0:
        raise RuntimeError(f"git show failed for {sha}: {result.stderr.strip()}")
    return result.stdout


def _compose_config(path: Path, runner: CommandRunner) -> dict[str, object]:
    result = runner.run(("docker", "compose", "-f", str(path), "config", "--format", "json"))
    if result.returncode != 0:
        raise RuntimeError(f"docker compose config failed: {result.stderr.strip()}")
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("docker compose config did not return JSON") from error
    if not isinstance(parsed, dict):
        raise RuntimeError("docker compose config returned a non-object JSON value")
    return parsed


def _compose_image_inputs(compose_config: dict[str, object]) -> tuple[tuple[str, str], ...]:
    services = compose_config.get("services", {})
    if not isinstance(services, dict):
        raise RuntimeError("docker compose config services must be an object")
    inputs: list[tuple[str, str]] = []
    for name, service in services.items():
        if not isinstance(name, str) or not isinstance(service, dict):
            raise RuntimeError("docker compose config service entries must be objects")
        image_input = {key: service.get(key) for key in ("image", "build", "platform") if key in service}
        inputs.append((name, json.dumps(image_input, sort_keys=True, separators=(",", ":"))))
    return tuple(sorted(inputs))


def _rule_for(path: str) -> PathRule | None:
    return next((rule for rule in PATH_RULES if fnmatch.fnmatchcase(path, rule.pattern)), None)


def _is_deployment_sensitive(path: str) -> bool:
    return path.startswith(("docs/", "scripts/", "deploy/", ".github/", "docker-compose", "Dockerfile")) or path.endswith(
        (".md", ".markdown", ".mdx")
    )


def _normalize_path(path: str) -> str:
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized
