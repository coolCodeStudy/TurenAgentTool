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
        return source


@dataclass(frozen=True)
class ResearchBundle:
    symbol: str
    market: str
    company_name: str | None = None
    sources: list[SourceDocument] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

