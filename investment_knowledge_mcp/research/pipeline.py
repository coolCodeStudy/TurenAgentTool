from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.model_providers.base import EnrichmentRequest
from investment_knowledge_mcp.model_providers.factory import create_model_provider
from investment_knowledge_mcp.research.audit import AuditResult, audit_research_draft, build_audit_markdown
from investment_knowledge_mcp.research.draft_builder import build_stock_research_draft
from investment_knowledge_mcp.research.official_sources import OfficialResearchProvider, normalize_symbol
from investment_knowledge_mcp.research.source_facts import extract_source_facts
from investment_knowledge_mcp.research.validation import validate_research_draft
from scripts.build_research_prompt import PROMPT_TEMPLATE_PATH, build_prompt
from scripts.review_research_draft import build_review_markdown


@dataclass(frozen=True)
class ResearchPipelineOptions:
    output_dir: Path
    provider: str = "openai"
    auto_confirm_facts: bool = False
    auto_import: bool = False
    import_needs_review: bool = False
    refresh: bool = False


@dataclass
class ResearchPipelineResult:
    symbol: str
    market: str
    status: str
    draft_path: Path | None = None
    review_path: Path | None = None
    audit_path: Path | None = None
    source_facts_path: Path | None = None
    imported_stock_id: int | None = None
    audit_status: str | None = None
    message: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_summary(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "market": self.market,
            "status": self.status,
            "audit_status": self.audit_status,
            "imported_stock_id": self.imported_stock_id,
            "draft_path": str(self.draft_path) if self.draft_path else None,
            "review_path": str(self.review_path) if self.review_path else None,
            "audit_path": str(self.audit_path) if self.audit_path else None,
            "message": self.message,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def run_single_stock_research(
    symbol: str,
    market: str,
    company_name: str | None,
    options: ResearchPipelineOptions,
) -> ResearchPipelineResult:
    symbol = normalize_symbol(symbol)
    market = market.strip().upper()
    paths = _artifact_paths(options.output_dir, symbol=symbol, market=market)

    if not options.refresh:
        existing = repository.search_stock(symbol=symbol, market=market)
        if existing.get("stock"):
            return ResearchPipelineResult(
                symbol=symbol,
                market=market,
                status="skipped_existing",
                message=f"{symbol} {market} already exists in knowledge base.",
            )

    try:
        provider = OfficialResearchProvider()
        bundle = provider.collect(symbol=symbol, market=market, company_name=company_name)
        draft = build_stock_research_draft(bundle)
        if options.provider != "none":
            draft = _enrich_draft(draft, provider_name=options.provider)
        draft.setdefault("user_insights", [])
        draft["user_insights"] = []

        validation = validate_research_draft(draft)
        source_facts = extract_source_facts(draft)
        audit = audit_research_draft(draft, source_facts=source_facts)

        _write_json(paths["draft"], draft)
        _write_json(paths["source_facts"], source_facts)
        paths["audit"].write_text(build_audit_markdown(draft, source_facts, audit), encoding="utf-8")
        paths["review"].write_text(build_review_markdown(draft, paths["draft"]), encoding="utf-8")

        errors = list(validation.errors) + list(audit.errors)
        warnings = list(validation.warnings) + list(audit.warnings)
        imported_stock_id = None
        status = "drafted"
        if options.auto_import:
            if audit.status == "pass" or (audit.status == "needs_review" and options.import_needs_review):
                imported = repository.import_stock_research_draft(
                    draft=draft,
                    confirmed_by_user=options.auto_confirm_facts,
                )
                imported_stock_id = int(imported["stock"]["id"])
                status = "imported"
            else:
                status = "needs_review" if audit.status == "needs_review" else "failed_audit"

        return ResearchPipelineResult(
            symbol=symbol,
            market=market,
            status=status,
            draft_path=paths["draft"],
            review_path=paths["review"],
            audit_path=paths["audit"],
            source_facts_path=paths["source_facts"],
            imported_stock_id=imported_stock_id,
            audit_status=audit.status,
            message=_status_message(status, audit),
            errors=errors,
            warnings=warnings,
        )
    except Exception as exc:
        return ResearchPipelineResult(
            symbol=symbol,
            market=market,
            status="failed",
            draft_path=paths["draft"],
            review_path=paths["review"],
            audit_path=paths["audit"],
            source_facts_path=paths["source_facts"],
            message=str(exc),
            errors=[str(exc)],
        )


def _enrich_draft(draft: dict[str, Any], provider_name: str) -> dict[str, Any]:
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    prompt = build_prompt(draft=draft, template=template)
    provider = create_model_provider(provider_name)
    return provider.enrich_research_draft(EnrichmentRequest(draft=draft, prompt=prompt))


def _artifact_paths(output_dir: Path, symbol: str, market: str) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{symbol.upper()}_{market.upper()}"
    return {
        "draft": output_dir / f"{stem}_research_draft.json",
        "review": output_dir / f"{stem}_graph_review.md",
        "audit": output_dir / f"{stem}_audit_report.md",
        "source_facts": output_dir / f"{stem}_source_facts.json",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _status_message(status: str, audit: AuditResult) -> str:
    if status == "imported":
        return "draft audited and imported"
    if status == "needs_review":
        return "draft generated but audit needs review"
    if status == "failed_audit":
        return "draft generated but audit failed"
    return f"draft generated with audit_status={audit.status}"
