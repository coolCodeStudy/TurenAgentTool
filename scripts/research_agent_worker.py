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
from datetime import UTC, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    skip_codex_when_seed_passes: bool
    seed_min_sources_for_skip: int
    seed_min_knowledge_items_for_skip: int
    concurrency: int


def main() -> None:
    parser = argparse.ArgumentParser(description="Run queued research jobs with Codex CLI.")
    parser.add_argument("--once", action="store_true", help="Process one job and exit.")
    parser.add_argument("--loop", action="store_true", help="Poll forever.")
    parser.add_argument("--concurrency", type=int, help="Number of research jobs to process concurrently.")
    args = parser.parse_args()

    if not args.once and not args.loop:
        args.once = True

    config = load_config()
    concurrency = max(1, args.concurrency or config.concurrency)
    run_schema()
    ensure_codex_available(config)

    while True:
        jobs = _claim_jobs(config, concurrency)
        if not jobs:
            if args.once:
                print("No queued research job.", flush=True)
                return
            time.sleep(config.poll_seconds)
            continue

        if len(jobs) == 1:
            _process_claimed_job(config, jobs[0])
        else:
            with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
                futures = [executor.submit(_process_claimed_job, config, job) for job in jobs]
                for future in as_completed(futures):
                    future.result()

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
        skip_codex_when_seed_passes=_env_bool("RESEARCH_SKIP_CODEX_WHEN_SEED_PASSES", default=True),
        seed_min_sources_for_skip=int(os.getenv("RESEARCH_SEED_MIN_SOURCES_FOR_SKIP", "3")),
        seed_min_knowledge_items_for_skip=int(os.getenv("RESEARCH_SEED_MIN_KNOWLEDGE_ITEMS_FOR_SKIP", "1")),
        concurrency=max(1, int(os.getenv("RESEARCH_WORKER_CONCURRENCY", "1"))),
    )


def _claim_jobs(config: ResearchWorkerConfig, limit: int) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for _ in range(max(1, limit)):
        job = claim_next_research_job(worker_name=config.worker_name)
        if job is None:
            break
        jobs.append(job)
    return jobs


def _process_claimed_job(config: ResearchWorkerConfig, job: dict[str, Any]) -> None:
    try:
        process_job(config, job)
    except Exception as exc:
        message = f"research job failed: {exc}"
        print(message, flush=True)
        _record_task_event(
            "research",
            int(job["id"]),
            "failed",
            status="failed",
            message=message,
            metadata={"worker": config.worker_name},
        )
        update_research_job(
            job_id=int(job["id"]),
            status="failed",
            error=message,
            worker_log=message,
        )


def process_job(config: ResearchWorkerConfig, job: dict[str, Any]) -> None:
    job_id = int(job["id"])
    symbol = str(job["symbol"])
    market = str(job["market"])
    name = job.get("name")
    provider = str(job.get("provider") or "codex")
    artifact_dir = config.artifact_root / f"job_{job_id}_{symbol}_{market}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(UTC).isoformat()
    execution_location = str(job.get("execution_location") or "cloud_worker")
    print(
        f"Processing research job #{job_id}: {symbol} {market} provider={provider} "
        f"execution_location={execution_location} worker={config.worker_name}",
        flush=True,
    )
    _record_task_event(
        "research",
        job_id,
        "started",
        status="running",
        message=f"{symbol} {market} provider={provider}",
        metadata={"worker": config.worker_name, "execution_location": execution_location},
    )
    if provider == "openai":
        _record_task_event("research", job_id, "openai_started", status="running")
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
            artifact_location=str(artifact_dir),
            artifacts={
                **result.to_summary(),
                "execution": _execution_metadata(
                    job=job,
                    config=config,
                    artifact_dir=artifact_dir,
                    started_at=started_at,
                ),
                "import_status": _import_status_from_result(result),
            },
            worker_log=f"openai provider finished with status={result.status} audit={result.audit_status}",
        )
        _record_task_event(
            "research",
            job_id,
            "openai_finished",
            status=_job_status_from_pipeline_result(result),
            message=result.message,
            metadata={"audit_status": result.audit_status, "errors": result.errors, "warnings": result.warnings},
        )
        return

    _record_task_event("research", job_id, "seed_started", status="running")
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
            artifact_location=str(artifact_dir),
            artifacts={
                **seed.to_summary(),
                "execution": _execution_metadata(
                    job=job,
                    config=config,
                    artifact_dir=artifact_dir,
                    started_at=started_at,
                ),
                "artifact_location": str(artifact_dir),
                "import_status": "not_imported",
            },
            worker_log="official-source seed stage failed",
        )
        _record_task_event(
            "research",
            job_id,
            "seed_failed",
            status="failed",
            message=seed.message,
            metadata=seed.to_summary(),
        )
        return
    _record_task_event(
        "research",
        job_id,
        "seed_finished",
        status=seed.status,
        message=seed.message,
        metadata={"audit_status": seed.audit_status, "errors": seed.errors, "warnings": seed.warnings},
    )

    discovery_path = artifact_dir / f"{symbol}_{market}_source_discovery_notes.md"
    _write_initial_discovery_notes(discovery_path, job=job, seed=seed)

    if provider == "codex":
        if _seed_is_sufficient_for_codex_skip(config, seed):
            _record_task_event(
                "research",
                job_id,
                "codex_skipped",
                status="running",
                message="seed passed audit and met skip thresholds",
            )
            _append_discovery_note(
                discovery_path,
                "## Codex Skip",
                "- official-source seed passed audit and met minimum source/fact thresholds; Codex enrichment skipped by budget gate.",
            )
        else:
            output_path = artifact_dir / "codex_final.txt"
            prompt = build_codex_research_prompt(
                job=job,
                draft_path=seed.draft_path,
                source_facts_path=seed.source_facts_path,
                audit_path=seed.audit_path,
                review_path=seed.review_path,
                discovery_path=discovery_path,
            )
            _record_task_event("research", job_id, "codex_started", status="running")
            run_codex(config, prompt=prompt, output_path=output_path)
            _record_task_event("research", job_id, "codex_finished", status="running")
    elif provider != "none":
        raise ValueError(f"unsupported research provider: {provider}")

    final = finalize_research_artifacts(
        job=job,
        artifact_dir=artifact_dir,
        draft_path=seed.draft_path,
        discovery_path=discovery_path,
        execution_metadata=_execution_metadata(
            job=job,
            config=config,
            artifact_dir=artifact_dir,
            started_at=started_at,
        ),
    )
    update_research_job(
        job_id=job_id,
        status=final["status"],
        result_summary=final["summary"],
        error=final.get("error"),
        artifact_dir=str(artifact_dir),
        artifact_location=str(artifact_dir),
        artifacts=final["artifacts"],
        source_discovery=final["source_discovery"],
        worker_log=final["worker_log"],
    )
    _record_task_event(
        "research",
        job_id,
        "finalized",
        status=final["status"],
        message=final["summary"],
        metadata={"error": final.get("error"), "artifact_dir": str(artifact_dir)},
    )


def finalize_research_artifacts(
    job: dict[str, Any],
    artifact_dir: Path,
    draft_path: Path | None,
    discovery_path: Path,
    execution_metadata: dict[str, Any],
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
    audit_markdown = build_audit_markdown(draft, source_facts, audit)
    review_markdown = build_review_markdown(draft, draft_path)
    _write_json(source_facts_path, source_facts)
    audit_path.write_text(audit_markdown, encoding="utf-8")
    review_path.write_text(review_markdown, encoding="utf-8")

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
        "execution": execution_metadata,
        "draft_path": str(draft_path),
        "source_facts_path": str(source_facts_path),
        "audit_path": str(audit_path),
        "review_path": str(review_path),
        "artifact_location": str(artifact_dir),
        "imported_stock_id": imported_stock_id,
        "import_status": "imported" if imported_stock_id is not None else ("pending_review" if status == "needs_review" else "not_imported"),
        "audit_status": audit.status,
        "draft_json": draft,
        "source_facts_json": source_facts,
        "audit_json": audit.to_dict(),
        "audit_markdown": audit_markdown,
        "review_markdown": review_markdown,
        "errors": errors,
        "warnings": list(validation.warnings) + list(audit.warnings),
    }
    return {
        "status": status,
        "summary": summary,
        "error": "; ".join(errors) if errors else None,
        "artifacts": artifacts,
        "source_discovery": _source_discovery_payload(discovery_path),
        "worker_log": f"research finalized status={status} audit={audit.status}",
    }


def _execution_metadata(
    job: dict[str, Any],
    config: ResearchWorkerConfig,
    artifact_dir: Path,
    started_at: str,
) -> dict[str, Any]:
    return {
        "execution_location": job.get("execution_location") or "cloud_worker",
        "worker_name": config.worker_name,
        "created_from": job.get("created_from"),
        "requested_by": job.get("requested_by") or job.get("sender"),
        "artifact_location": str(artifact_dir),
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "provider": job.get("provider") or "codex",
        "source_policy": job.get("source_policy") or "broad_search",
    }


def _import_status_from_result(result: Any) -> str:
    if getattr(result, "imported_stock_id", None) is not None:
        return "imported"
    if getattr(result, "status", None) == "needs_review":
        return "pending_review"
    if getattr(result, "status", None) == "imported":
        return "imported"
    return "not_imported"


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


def _append_discovery_note(path: Path, heading: str, line: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(existing.rstrip() + f"\n\n{heading}\n{line}\n", encoding="utf-8")


def _seed_is_sufficient_for_codex_skip(config: ResearchWorkerConfig, seed: Any) -> bool:
    if not config.skip_codex_when_seed_passes or seed.audit_status != "pass" or seed.draft_path is None:
        return False
    try:
        draft = json.loads(Path(seed.draft_path).read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(draft, dict):
        return False
    sources = draft.get("sources") if isinstance(draft.get("sources"), list) else []
    knowledge_items = draft.get("knowledge_items") if isinstance(draft.get("knowledge_items"), list) else []
    return (
        len(sources) >= config.seed_min_sources_for_skip
        and len(knowledge_items) >= config.seed_min_knowledge_items_for_skip
    )


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


def _record_task_event(
    task_type: str,
    task_id: int,
    event_type: str,
    status: str | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        repository.add_task_event(
            task_type=task_type,
            task_id=task_id,
            event_type=event_type,
            status=status,
            message=message,
            metadata=metadata,
        )
    except Exception as exc:
        print(f"task event write failed: {exc}", flush=True)


if __name__ == "__main__":
    main()
