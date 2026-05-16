from __future__ import annotations

from abc import ABC, abstractmethod
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx

from investment_knowledge_mcp.research.models import (
    ResearchBundle,
    SourceDocument,
    merge_research_bundles,
)


class ResearchProvider(ABC):
    @abstractmethod
    def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
        """Collect research source documents for a stock."""


class ManualResearchProvider(ResearchProvider):
    """Load user-curated source documents from a local JSON file."""

    def __init__(self, source_file: Path) -> None:
        self.source_file = source_file

    def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
        payload = json.loads(self.source_file.read_text(encoding="utf-8"))
        stock = payload.get("stock") or {}
        bundle_symbol = symbol or stock.get("symbol")
        bundle_market = market or stock.get("market")
        if not bundle_symbol or not bundle_market:
            raise ValueError("symbol and market are required")

        sources = [
            SourceDocument(
                key=item["key"],
                source_type=item.get("source_type", "web"),
                title=item["title"],
                url=item.get("url"),
                publisher=item.get("publisher"),
                published_at=item.get("published_at"),
                notes=item.get("notes"),
                content_excerpt=item.get("content_excerpt"),
            )
            for item in payload.get("sources", [])
        ]

        return ResearchBundle(
            symbol=bundle_symbol,
            market=bundle_market,
            company_name=company_name or stock.get("name"),
            sources=sources,
            notes=payload.get("notes", []),
        )


class EmptyResearchProvider(ResearchProvider):
    """Create a skeleton bundle when no external provider has been configured."""

    def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
        return ResearchBundle(symbol=symbol, market=market, company_name=company_name)


class WebPageResearchProvider(ResearchProvider):
    """Fetch public web pages and convert them into source documents."""

    def __init__(
        self,
        source_urls: list[str],
        timeout_seconds: float = 20,
        max_excerpt_chars: int = 4000,
    ) -> None:
        self.source_urls = source_urls
        self.timeout_seconds = timeout_seconds
        self.max_excerpt_chars = max_excerpt_chars

    def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
        sources: list[SourceDocument] = []
        notes: list[str] = []

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; InvestmentKnowledgeBot/0.1; "
                    "+https://localhost)"
                )
            },
        ) as client:
            for index, source_url in enumerate(self.source_urls, start=1):
                key, url = parse_source_url(source_url, index)
                response = client.get(url)
                response.raise_for_status()

                title, text = extract_html_title_and_text(response.text)
                sources.append(
                    SourceDocument(
                        key=key,
                        source_type="web",
                        title=title or url,
                        url=str(response.url),
                        publisher=urlparse(str(response.url)).netloc,
                        content_excerpt=trim_text(text, self.max_excerpt_chars),
                    )
                )

        if sources:
            notes.append("web_page provider fetched public webpages and stored text excerpts.")

        return ResearchBundle(
            symbol=symbol,
            market=market,
            company_name=company_name,
            sources=sources,
            notes=notes,
        )


def collect_with_optional_providers(
    symbol: str,
    market: str,
    company_name: str | None = None,
    manual_source_file: Path | None = None,
    source_urls: list[str] | None = None,
) -> ResearchBundle:
    provider: ResearchProvider = (
        ManualResearchProvider(manual_source_file)
        if manual_source_file
        else EmptyResearchProvider()
    )
    bundle = provider.collect(symbol=symbol, market=market, company_name=company_name)

    if source_urls:
        web_bundle = WebPageResearchProvider(source_urls).collect(
            symbol=bundle.symbol,
            market=bundle.market,
            company_name=bundle.company_name,
        )
        bundle = merge_research_bundles(bundle, web_bundle)

    return bundle


def parse_source_url(value: str, index: int) -> tuple[str, str]:
    if "=" not in value:
        return f"web_{index}", value

    key, url = value.split("=", 1)
    key = key.strip()
    url = url.strip()
    if not key or not url:
        raise ValueError("--source-url must be KEY=URL or URL")
    return key, url


def trim_text(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + "..."


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text or self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(text)
        else:
            self.text_parts.append(text)


def extract_html_title_and_text(html: str) -> tuple[str, str]:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    title = " ".join(parser.title_parts).strip()
    text = " ".join(parser.text_parts).strip()
    return title, text
