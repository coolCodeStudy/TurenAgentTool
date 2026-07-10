from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

try:
    from scripts.deploy_contract import APPLICATION_SERVICES, DeployMode, DeploymentPlan, classify_deployment, classify_paths, serialize_plan
    from scripts.deploy_support import SubprocessRunner
except ModuleNotFoundError:  # Direct execution from the repository root.
    from deploy_contract import APPLICATION_SERVICES, DeployMode, DeploymentPlan, classify_deployment, classify_paths, serialize_plan
    from deploy_support import SubprocessRunner


LegacyDeployMode = Literal["no_deploy", "quick", "full"]


@dataclass(frozen=True)
class ClassificationResult:
    deploy_mode: LegacyDeployMode
    changed_files: tuple[str, ...]
    plan: DeploymentPlan


def classify_changed_files(files: Iterable[str]) -> ClassificationResult:
    plan = classify_paths(files, compose_image_changed=False)
    return ClassificationResult(
        deploy_mode=_legacy_mode(plan.mode),
        changed_files=plan.changed_files,
        plan=plan,
    )


def _legacy_mode(mode: DeployMode) -> LegacyDeployMode:
    if mode is DeployMode.NO_DEPLOY:
        return "no_deploy"
    if mode is DeployMode.FULL_IMAGE:
        return "full"
    return "quick"


def _manual_plan(mode: str) -> DeploymentPlan:
    mode_by_name = {
        "no_deploy": DeployMode.NO_DEPLOY,
        "quick": DeployMode.TARGETED_QUICK,
        "full": DeployMode.FULL_IMAGE,
        "targeted_quick": DeployMode.TARGETED_QUICK,
        "config_restart": DeployMode.CONFIG_RESTART,
        "full_image": DeployMode.FULL_IMAGE,
    }
    selected = mode_by_name[mode]
    return DeploymentPlan(
        mode=selected,
        targets=() if selected is DeployMode.NO_DEPLOY else APPLICATION_SERVICES,
        changed_files=(f"manual-{mode}",),
        image_input_files=(),
        reasons=(f"manual deployment mode: {mode}",),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify changed files for production deployment.")
    parser.add_argument("files", nargs="*", help="Changed files to classify.")
    parser.add_argument("--changed-files-file", type=Path, help="Read newline-delimited changed files from this file.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository used with --base-sha and --target-sha.")
    parser.add_argument("--base-sha", help="Base Git ref for automatic diff classification.")
    parser.add_argument("--target-sha", help="Target Git ref for automatic diff classification.")
    parser.add_argument(
        "--manual-mode",
        choices=("auto", "no_deploy", "quick", "full", "targeted_quick", "config_restart", "full_image"),
        default="auto",
        help="Manual workflow_dispatch override.",
    )
    parser.add_argument("--format", choices=("text", "json", "github-output"), default="text", help="Output format.")
    args = parser.parse_args()

    files = list(args.files)
    if args.changed_files_file:
        files.extend(args.changed_files_file.read_text(encoding="utf-8").splitlines())
    if bool(args.base_sha) != bool(args.target_sha):
        parser.error("--base-sha and --target-sha must be provided together")
    if args.manual_mode == "auto" and args.base_sha and args.target_sha:
        plan = classify_deployment(args.repo, args.base_sha, args.target_sha, SubprocessRunner())
        result = ClassificationResult(
            deploy_mode=_legacy_mode(plan.mode),
            changed_files=plan.changed_files,
            plan=plan,
        )
    elif args.manual_mode == "auto":
        result = classify_changed_files(files)
    else:
        plan = _manual_plan(args.manual_mode)
        result = ClassificationResult(
            deploy_mode=_legacy_mode(plan.mode),
            changed_files=plan.changed_files,
            plan=plan,
        )
    print_result(result, args.format)


def print_result(result: ClassificationResult, output_format: str) -> None:
    if output_format == "json":
        payload = serialize_plan(result.plan)
        payload["deploy_mode"] = result.deploy_mode
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if output_format == "github-output":
        print(f"deploy_mode={result.deploy_mode}")
        print("changed_files<<EOF")
        for path in result.changed_files:
            print(path)
        print("EOF")
        return
    print(f"Selected deployment mode: {result.plan.mode.value}")
    print(f"Workflow-compatible mode: {result.deploy_mode}")
    print("Targets:")
    for target in result.plan.targets:
        print(f"- {target}")


if __name__ == "__main__":
    main()
