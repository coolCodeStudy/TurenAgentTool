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
    "dingtalk-api",
    "dingtalk-stream-bot",
    "mcp",
    "scheduler-host",
    "weekly-review-web",
)

# Explicit one-time topology migrations. These names are intentionally not
# inferred from Compose or removed with ``--remove-orphans``: deployment must
# only retire application containers whose replacement contract is admitted.
OBSOLETE_SCHEDULER_SERVICES = (
    "ipo-reminder-scheduler",
    "account-snapshot-scheduler",
    "daily-market-brief-scheduler",
    "daily-market-brief-history-worker",
)
OBSOLETE_GATEWAY_SERVICES = ("command-api",)
OBSOLETE_APPLICATION_SERVICES = (
    *OBSOLETE_SCHEDULER_SERVICES,
    *OBSOLETE_GATEWAY_SERVICES,
)

OPS_CONTROL_PLANE_FILES = frozenset(
    {
        "scripts/bootstrap_deploy_baseline.py",
        "scripts/bootstrap_ops_api_v2_on_ecs.sh",
        "scripts/deploy_contract.py",
        "scripts/deploy_preflight.py",
        "scripts/deploy_release.py",
        "scripts/deploy_retention.py",
        "scripts/deploy_state.py",
        "scripts/deploy_support.py",
        "scripts/ecs_ops_api.py",
        "scripts/install_ops_api_on_ecs.sh",
    }
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
    PathRule(".env.example", DeployMode.NO_DEPLOY, (), "production environment template"),
    PathRule("AGENTS.md", DeployMode.NO_DEPLOY, (), "agent governance"),
    PathRule("README.md", DeployMode.NO_DEPLOY, (), "repository documentation"),
    PathRule("DEPLOYMENT.md", DeployMode.NO_DEPLOY, (), "repository documentation"),
    PathRule("系统设计.md", DeployMode.NO_DEPLOY, (), "repository documentation"),
    PathRule("docs/**", DeployMode.NO_DEPLOY, (), "repository documentation"),
    PathRule("skills/**", DeployMode.NO_DEPLOY, (), "repository agent skill"),
    PathRule("prompts/**", DeployMode.NO_DEPLOY, (), "repository prompt"),
    PathRule("tests/**", DeployMode.NO_DEPLOY, (), "tests"),
    PathRule("e2e/**", DeployMode.NO_DEPLOY, (), "browser acceptance tests"),
    PathRule(".github/workflows/codex-worker.yml", DeployMode.NO_DEPLOY, (), "workflow governance"),
    PathRule(".github/workflows/cloud-e2e.yml", DeployMode.NO_DEPLOY, (), "browser acceptance workflow"),
    PathRule(".github/workflows/deploy.yml", DeployMode.NO_DEPLOY, (), "workflow governance"),
    PathRule(".github/workflows/ops-api.yml", DeployMode.NO_DEPLOY, (), "workflow governance"),
    PathRule("scripts/agent_preflight.py", DeployMode.NO_DEPLOY, (), "local audit"),
    PathRule("scripts/audit_agent_flow_health.py", DeployMode.NO_DEPLOY, (), "local audit"),
    PathRule("scripts/audit_architecture_health.py", DeployMode.NO_DEPLOY, (), "local architecture audit"),
    PathRule("scripts/audit_delivery_state.py", DeployMode.NO_DEPLOY, (), "local audit"),
    PathRule("scripts/audit_prd_status.py", DeployMode.NO_DEPLOY, (), "local audit"),
    PathRule("scripts/classify_deploy_change.py", DeployMode.NO_DEPLOY, (), "local deploy classifier"),
    PathRule("scripts/evaluate_agent_flow_cases.py", DeployMode.NO_DEPLOY, (), "local evaluation"),
    PathRule("scripts/install_architecture_code_health_skill.py", DeployMode.NO_DEPLOY, (), "local skill installer"),
    PathRule(
        "scripts/generate_prod_env.py",
        DeployMode.NO_DEPLOY,
        (),
        "production environment provisioning",
    ),
    PathRule("scripts/smoke_test.py", DeployMode.NO_DEPLOY, (), "local smoke verification"),
    PathRule("scripts/verify_change_package.py", DeployMode.NO_DEPLOY, (), "local change-package verification"),
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
        "scripts/daily_market_brief_history_worker.py",
        DeployMode.TARGETED_QUICK,
        ("scheduler-host",),
        "daily market brief history worker runtime",
    ),
    PathRule(
        "scripts/dingtalk_stream_bot.py",
        DeployMode.TARGETED_QUICK,
        ("dingtalk-stream-bot",),
        "DingTalk stream bot runtime",
    ),
    PathRule(
        "scripts/init_db.py",
        DeployMode.TARGETED_QUICK,
        (
            "dingtalk-api",
            "dingtalk-stream-bot",
            "mcp",
            "scheduler-host",
            "weekly-review-web",
        ),
        "database initialization runtime",
    ),
    PathRule(
        "investment_knowledge_mcp/dingtalk_api.py",
        DeployMode.TARGETED_QUICK,
        ("dingtalk-api",),
        "DingTalk HTTP adapter",
    ),
    PathRule(
        "investment_knowledge_mcp/app_gateway.py",
        DeployMode.TARGETED_QUICK,
        ("weekly-review-web",),
        "application gateway",
    ),
    PathRule(
        "investment_knowledge_mcp/weekly_review_controller.py",
        DeployMode.TARGETED_QUICK,
        ("weekly-review-web",),
        "weekly review gateway controller",
    ),
    PathRule(
        "investment_knowledge_mcp/daily_market_brief_controller.py",
        DeployMode.TARGETED_QUICK,
        ("weekly-review-web",),
        "daily market brief gateway controller",
    ),
    PathRule(
        "investment_knowledge_mcp/command_http.py",
        DeployMode.TARGETED_QUICK,
        ("weekly-review-web",),
        "shared command HTTP controller",
    ),
    PathRule(
        "investment_knowledge_mcp/http_access.py",
        DeployMode.TARGETED_QUICK,
        ("weekly-review-web",),
        "shared HTTP access adapter",
    ),
    PathRule(
        "investment_knowledge_mcp/web_access.py",
        DeployMode.TARGETED_QUICK,
        ("weekly-review-web",),
        "shared browser access contract",
    ),
    PathRule("investment_knowledge_mcp/weekly_review_web.py", DeployMode.TARGETED_QUICK, ("weekly-review-web",), "weekly review web"),
    PathRule(
        "investment_knowledge_mcp/command_workbench.py",
        DeployMode.TARGETED_QUICK,
        ("weekly-review-web",),
        "command workbench",
    ),
    PathRule(
        "investment_knowledge_mcp/command_router.py",
        DeployMode.TARGETED_QUICK,
        ("dingtalk-api", "dingtalk-stream-bot", "mcp", "weekly-review-web"),
        "shared command logic",
    ),
    PathRule(
        "investment_knowledge_mcp/daily_market_brief.py",
        DeployMode.TARGETED_QUICK,
        (
            "dingtalk-api",
            "dingtalk-stream-bot",
            "mcp",
            "scheduler-host",
            "weekly-review-web",
        ),
        "shared command logic",
    ),
    PathRule(
        "investment_knowledge_mcp/weekly_review.py",
        DeployMode.TARGETED_QUICK,
        ("dingtalk-api", "dingtalk-stream-bot", "mcp", "weekly-review-web"),
        "shared command logic",
    ),
    PathRule("investment_knowledge_mcp/command_api.py", DeployMode.TARGETED_QUICK, ("weekly-review-web",), "legacy command API adapter"),
    PathRule("investment_knowledge_mcp/server.py", DeployMode.TARGETED_QUICK, ("mcp",), "MCP server"),
    PathRule(
        "investment_knowledge_mcp/account_snapshots.py",
        DeployMode.TARGETED_QUICK,
        ("scheduler-host",),
        "account snapshot scheduler",
    ),
    PathRule(
        "investment_knowledge_mcp/ipo_reminders.py",
        DeployMode.TARGETED_QUICK,
        ("scheduler-host",),
        "IPO reminder scheduler",
    ),
    PathRule(
        "investment_knowledge_mcp/scheduler_host.py",
        DeployMode.TARGETED_QUICK,
        ("scheduler-host",),
        "scheduler host runtime",
    ),
    PathRule(
        "investment_knowledge_mcp/scheduler_jobs.py",
        DeployMode.TARGETED_QUICK,
        ("scheduler-host",),
        "scheduler job composition",
    ),
    PathRule(
        "investment_knowledge_mcp/scheduler_service.py",
        DeployMode.TARGETED_QUICK,
        ("scheduler-host",),
        "scheduler service runtime",
    ),
    PathRule(
        "investment_knowledge_mcp/daily_market_jobs.py",
        DeployMode.TARGETED_QUICK,
        ("dingtalk-api", "dingtalk-stream-bot", "mcp", "scheduler-host", "weekly-review-web"),
        "shared daily market history queue",
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
        "control_plane_update_required": requires_control_plane_update(
            plan.changed_files
        ),
    }


def requires_control_plane_update(paths: Iterable[str]) -> bool:
    return any(path in OPS_CONTROL_PLANE_FILES for path in paths)


def _read_changed_files(repo: Path, base_sha: str, target_sha: str, runner: CommandRunner) -> tuple[str, ...]:
    result = runner.run(
        (
            "git",
            "-C",
            str(repo),
            "diff",
            "--no-renames",
            "--name-only",
            "-z",
            base_sha,
            target_sha,
        )
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return tuple(path for path in result.stdout.split("\0") if path)


def _compose_image_inputs_changed(repo: Path, base_sha: str, target_sha: str, runner: CommandRunner) -> bool:
    base_compose = _git_show(repo, base_sha, runner)
    target_compose = _git_show(repo, target_sha, runner)
    with tempfile.TemporaryDirectory(prefix="deploy-compose-") as directory:
        base_path = Path(directory) / "base.yml"
        target_path = Path(directory) / "target.yml"
        base_path.write_text(base_compose, encoding="utf-8")
        target_path.write_text(target_compose, encoding="utf-8")
        base_inputs = dict(_compose_image_inputs(_compose_config(base_path, runner)))
        target_inputs = dict(_compose_image_inputs(_compose_config(target_path, runner)))
        common_services = set(base_inputs) & set(target_inputs)
        if any(base_inputs[name] != target_inputs[name] for name in common_services):
            return True
        known_recipes = set(base_inputs.values())
        return any(
            target_inputs[name] not in known_recipes
            for name in set(target_inputs) - set(base_inputs)
        )


def _git_show(repo: Path, sha: str, runner: CommandRunner) -> str:
    result = runner.run(("git", "-C", str(repo), "show", f"{sha}:docker-compose.prod.yml"))
    if result.returncode != 0:
        raise RuntimeError(f"git show failed for {sha}: {result.stderr.strip()}")
    return result.stdout


def _compose_config(path: Path, runner: CommandRunner) -> dict[str, object]:
    result = runner.run(
        ("docker", "compose", "-f", str(path), "config", "--no-interpolate", "--format", "json")
    )
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
