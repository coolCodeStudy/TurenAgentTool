from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceDocument:
    key: str
    source_type: str
    title: str
    url: str | None = None
    publisher: str | None = None
    published_at: str | None = None
    notes: str | None = None
    content_excerpt: str | None = None

    def to_draft_source(self) -> dict[str, Any]:
        source: dict[str, Any] = {
            "key": self.key,
            "source_type": self.source_type,
            "title": self.title,
        }
        if self.url:
            source["url"] = self.url
        if self.publisher:
            source["publisher"] = self.publisher
        if self.published_at:
            source["published_at"] = self.published_at
        if self.notes:
            source["notes"] = self.notes
        if self.content_excerpt:
            source["content_excerpt"] = self.content_excerpt
        return source


@dataclass(frozen=True)
class ResearchBundle:
    symbol: str
    market: str
    company_name: str | None = None
    sources: list[SourceDocument] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def merge_research_bundles(primary: ResearchBundle, *others: ResearchBundle) -> ResearchBundle:
    sources = list(primary.sources)
    notes = list(primary.notes)
    company_name = primary.company_name

    for bundle in others:
        sources.extend(bundle.sources)
        notes.extend(bundle.notes)
        company_name = company_name or bundle.company_name

    return ResearchBundle(
        symbol=primary.symbol,
        market=primary.market,
        company_name=company_name,
        sources=sources,
        notes=notes,
    )
