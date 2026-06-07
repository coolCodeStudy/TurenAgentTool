#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.research.audit import audit_research_draft, build_audit_markdown
from investment_knowledge_mcp.research.jobs import claim_next_research_job, update_research_job
from investment_knowledge_mcp.research.pipeline import ResearchPipelineOptions, run_single_stock_research
from investment_knowledge_mcp.research.source_facts import extract_source_facts
from investment_knowledge_mcp.research.validation import validate_research_draft
from scripts.review_research_draft import build_review_markdown


@dataclass(frozen=True)
class ResearchWorkerConfig:
    worker_name: str
    work_dir: Path
    artifact_root: Path
    codex_bin: str
    codex_model: str | None
    codex_timeout_seconds: int
    poll_seconds: int
    danger_full_access: bool


def main() -> None:
    parser = argparse.ArgumentParser(description="Run queued research jobs with Codex CLI.")
    parser.add_argument("--once", action="store_true", help="Process one job and exit.")
    parser.add_argument("--loop", action="store_true", help="Poll forever.")
    args = parser.parse_args()

    if not args.once and not args.loop:
        args.once = True

    config = load_config()
    run_schema()
    ensure_codex_available(config)

    while True:
        job = claim_next_research_job(worker_name=config.worker_name)
        if job is None:
            if args.once:
                print("No queued research job.", flush=True)
                return
            time.sleep(config.poll_seconds)
            continue

        try:
            process_job(config, job)
        except Exception as exc:
            message = f"research job failed: {exc}"
            print(message, flush=True)
            update_research_job(
                job_id=int(job["id"]),
                status="failed",
                error=message,
                worker_log=message,
            )

        if args.once:
            return


def load_config() -> ResearchWorkerConfig:
    return ResearchWorkerConfig(
        worker_name=os.getenv("RESEARCH_WORKER_NAME", "research-agent-worker"),
        work_dir=Path(os.getenv("RESEARCH_WORK_DIR", str(PROJECT_ROOT))),
        artifact_root=Path(os.getenv("RESEARCH_ARTIFACT_ROOT", str(PROJECT_ROOT / "drafts" / "research_jobs"))),
        codex_bin=os.getenv("CODEX_BIN", "codex"),
        codex_model=os.getenv("RESEARCH_CODEX_MODEL") or os.getenv("CODEX_WORKER_MODEL") or None,
        codex_timeout_seconds=int(os.getenv("RESEARCH_CODEX_TIMEOUT_SECONDS", "3600")),
        poll_seconds=int(os.getenv("RESEARCH_WORKER_POLL_SECONDS", "30")),
        danger_full_access=_env_bool("RESEARCH_WORKER_DANGER_FULL_ACCESS", default=True),
    )


def process_job(config: ResearchWorkerConfig, job: dict[str, Any]) -> None:
    job_id = int(job["id"])
    symbol = str(job["symbol"])
    market = str(job["market"])
    name = job.get("name")
    provider = str(job.get("provider") or "codex")
    artifact_dir = config.artifact_root / f"job_{job_id}_{symbol}_{market}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    print(f"Processing research job #{job_id}: {symbol} {market} provider={provider}", flush=True)
    if provider == "openai":
        result = run_single_stock_research(
            symbol=symbol,
            market=market,
            company_name=name,
            options=ResearchPipelineOptions(
                output_dir=artifact_dir,
                provider="openai",
                auto_confirm_facts=True,
                auto_import=bool(job.get("auto_import")),
                import_needs_review=bool(job.get("import_needs_review")),
                refresh=bool(job.get("refresh")),
            ),
        )
        update_research_job(
            job_id=job_id,
            status=_job_status_from_pipeline_result(result),
            result_summary=result.message,
            error="; ".join(result.errors) if result.errors else None,
            artifact_dir=str(artifact_dir),
            artifacts=result.to_summary(),
            worker_log=f"openai provider finished with status={result.status} audit={result.audit_status}",
        )
        return

    seed = run_single_stock_research(
        symbol=symbol,
        market=market,
        company_name=name,
        options=ResearchPipelineOptions(
            output_dir=artifact_dir,
            provider="none",
            auto_confirm_facts=False,
            auto_import=False,
            refresh=bool(job.get("refresh")),
        ),
    )
    if seed.status == "failed":
        update_research_job(
            job_id=job_id,
            status="failed",
            error=seed.message,
            artifact_dir=str(artifact_dir),
            artifacts=seed.to_summary(),
            worker_log="official-source seed stage failed",
        )
        return

    discovery_path = artifact_dir / f"{symbol}_{market}_source_discovery_notes.md"
    _write_initial_discovery_notes(discovery_path, job=job, seed=seed)

    if provider == "codex":
        output_path = artifact_dir / "codex_final.txt"
        prompt = build_codex_research_prompt(
            job=job,
            draft_path=seed.draft_path,
            source_facts_path=seed.source_facts_path,
            audit_path=seed.audit_path,
            review_path=seed.review_path,
            discovery_path=discovery_path,
        )
        run_codex(config, prompt=prompt, output_path=output_path)
    elif provider != "none":
        raise ValueError(f"unsupported research provider: {provider}")

    final = finalize_research_artifacts(
        job=job,
        artifact_dir=artifact_dir,
        draft_path=seed.draft_path,
        discovery_path=discovery_path,
    )
    update_research_job(
        job_id=job_id,
        status=final["status"],
        result_summary=final["summary"],
        error=final.get("error"),
        artifact_dir=str(artifact_dir),
        artifacts=final["artifacts"],
        source_discovery=final["source_discovery"],
        worker_log=final["worker_log"],
    )


def finalize_research_artifacts(
    job: dict[str, Any],
    artifact_dir: Path,
    draft_path: Path | None,
    discovery_path: Path,
) -> dict[str, Any]:
    if draft_path is None or not draft_path.exists():
        return {
            "status": "failed",
            "summary": "draft file missing after research worker run",
            "error": "draft file missing",
            "artifacts": {},
            "source_discovery": _source_discovery_payload(discovery_path),
            "worker_log": "draft file missing",
        }

    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        raise ValueError("research draft must be a JSON object")
    draft["user_insights"] = []
    _write_json(draft_path, draft)

    source_facts = extract_source_facts(draft)
    validation = validate_research_draft(draft)
    audit = audit_research_draft(draft, source_facts=source_facts)

    symbol = str(job["symbol"]).upper()
    market = str(job["market"]).upper()
    source_facts_path = artifact_dir / f"{symbol}_{market}_source_facts.json"
    audit_path = artifact_dir / f"{symbol}_{market}_audit_report.md"
    review_path = artifact_dir / f"{symbol}_{market}_graph_review.md"
    _write_json(source_facts_path, source_facts)
    audit_path.write_text(build_audit_markdown(draft, source_facts, audit), encoding="utf-8")
    review_path.write_text(build_review_markdown(draft, draft_path), encoding="utf-8")

    errors = list(validation.errors) + list(audit.errors)
    imported_stock_id = None
    status = "drafted"
    summary = f"draft generated with audit_status={audit.status}"
    if errors:
        status = "failed"
        summary = "draft failed validation/audit"
    elif bool(job.get("auto_import")) and audit.status == "pass":
        imported = repository.import_stock_research_draft(draft=draft, confirmed_by_user=True)
        imported_stock_id = int(imported["stock"]["id"])
        status = "imported"
        summary = "draft audited and imported"
    elif bool(job.get("auto_import")) and audit.status == "needs_review" and bool(job.get("import_needs_review")):
        imported = repository.import_stock_research_draft(draft=draft, confirmed_by_user=True)
        imported_stock_id = int(imported["stock"]["id"])
        status = "imported"
        summary = "needs_review draft imported by job setting"
    elif audit.status == "needs_review":
        status = "needs_review"
        summary = "draft generated but needs review"

    artifacts = {
        "draft_path": str(draft_path),
        "source_facts_path": str(source_facts_path),
        "audit_path": str(audit_path),
        "review_path": str(review_path),
        "imported_stock_id": imported_stock_id,
        "audit_status": audit.status,
        "errors": errors,
        "warnings": list(validation.warnings) + list(audit.warnings),
    }
    return {
        "status": status,
        "summary": summary,
        "error": "; ".join(errors) if errors else None,
        "artifacts": artifacts,
        "source_discovery": _source_discovery_payload(discovery_path),
        "worker_log": f"codex research finalized status={status} audit={audit.status}",
    }


def build_codex_research_prompt(
    job: dict[str, Any],
    draft_path: Path | None,
    source_facts_path: Path | None,
    audit_path: Path | None,
    review_path: Path | None,
    discovery_path: Path,
) -> str:
    return f"""你是 InvestmentKnowledge 的云端研究 agent。请处理 research job #{job['id']}。

目标股票：{job['symbol']} {job['market']} {job.get('name') or ''}
来源策略：{job.get('source_policy') or 'broad_search'}

现有产物：
- draft: {draft_path}
- source_facts: {source_facts_path}
- audit: {audit_path}
- review: {review_path}
- source_discovery_notes: {discovery_path}

任务：
1. 先阅读 draft/source_facts/audit，判断官方源脚本资料是否足够。
2. 如果资料不足，可以继续用脚本、curl、公开网页、公司 IR、SEC/HKEX/ETF issuer、可靠新闻稿等方式寻找新来源。
3. 找到新来源后，把来源追加到 draft 的 `sources`，必须包含 key/title/url/publisher/source_type，能摘录正文时写 `content_excerpt`。
4. 补全 draft 的 stock/sectors/knowledge_items。不要写用户心得，`user_insights` 必须保持空数组。
5. 每条 knowledge_items 必须引用已有 source_key。不要把推断写成事实，低置信内容写 watch_item。
6. 更新 source_discovery_notes，记录：
   - 脚本已找到的来源
   - Codex 额外找到的来源
   - 哪些来源模式值得沉淀成 provider
   - 如果值得优化脚本，写出具体 provider backlog
7. 最终把完整 JSON 写回 draft 文件，不要只在回答里输出 JSON。

完成后用中文简短说明你改了什么。"""


def run_codex(config: ResearchWorkerConfig, prompt: str, output_path: Path) -> None:
    args = [
        config.codex_bin,
        "exec",
        "--cd",
        str(config.work_dir),
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
    subprocess.run(args, cwd=config.work_dir, check=True, timeout=config.codex_timeout_seconds)


def ensure_codex_available(config: ResearchWorkerConfig) -> None:
    if shutil.which(config.codex_bin) is None:
        raise RuntimeError(f"Codex CLI is not available: {config.codex_bin}")


def _write_initial_discovery_notes(path: Path, job: dict[str, Any], seed: Any) -> None:
    lines = [
        f"# Source Discovery Notes: {job['symbol']} {job['market']}",
        "",
        "## Script Seed",
        f"- status: {seed.status}",
        f"- audit_status: {seed.audit_status or 'n/a'}",
        f"- draft: {seed.draft_path}",
        f"- source_facts: {seed.source_facts_path}",
        f"- audit: {seed.audit_path}",
        "",
        "## Codex Extra Sources",
        "- pending",
        "",
        "## Provider Backlog",
        "- pending",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _source_discovery_payload(path: Path) -> dict[str, Any]:
    return {
        "notes_path": str(path),
        "notes": path.read_text(encoding="utf-8") if path.exists() else "",
    }


def _job_status_from_pipeline_result(result: Any) -> str:
    if result.status == "imported":
        return "imported"
    if result.status in {"needs_review", "failed_audit"}:
        return "needs_review" if result.status == "needs_review" else "failed"
    if result.status == "drafted":
        return "drafted"
    if result.status == "skipped_existing":
        return "drafted"
    return "failed"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _env_bool(key: str, default: bool) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    main()
