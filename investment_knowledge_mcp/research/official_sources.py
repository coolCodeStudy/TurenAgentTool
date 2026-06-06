from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

from investment_knowledge_mcp.research.models import ResearchBundle, SourceDocument
from investment_knowledge_mcp.research.providers import ResearchProvider, trim_text


DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_EXCERPT_CHARS = 12000

ETF_ISSUER_SOURCES: dict[str, list[SourceDocument]] = {
    "TLT": [
        SourceDocument(
            key="ishares_product_page",
            source_type="fund_page",
            title="iShares 20+ Year Treasury Bond ETF",
            url="https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf",
            publisher="iShares",
        )
    ],
    "DRAM": [
        SourceDocument(
            key="roundhill_product_page",
            source_type="fund_page",
            title="Roundhill Memory ETF",
            url="https://www.roundhillinvestments.com/etf/dram/",
            publisher="Roundhill Investments",
        )
    ],
    "PSLV": [
        SourceDocument(
            key="sprott_product_page",
            source_type="fund_page",
            title="Sprott Physical Silver Trust",
            url="https://sprott.com/investment-strategies/physical-bullion-trusts/silver/",
            publisher="Sprott",
        )
    ],
}


@dataclass(frozen=True)
class FilingCandidate:
    key: str
    source_type: str
    title: str
    url: str
    publisher: str
    published_at: str | None = None


class OfficialResearchProvider(ResearchProvider):
    """Collect official-ish sources from HKEX, SEC, issuer pages, and company IR pages.

    The provider intentionally collects sources and excerpts only. It does not make
    investment claims; model enrichment and audit happen later.
    """

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
        max_sources: int = 3,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_excerpt_chars = max_excerpt_chars
        self.max_sources = max_sources

    def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
        symbol = normalize_symbol(symbol)
        market = market.strip().upper()
        with _http_client(self.timeout_seconds) as client:
            if market == "US":
                bundle = self._collect_us(client, symbol=symbol, company_name=company_name)
            elif market == "HK":
                bundle = self._collect_hk(client, symbol=symbol, company_name=company_name)
            else:
                bundle = ResearchBundle(
                    symbol=symbol,
                    market=market,
                    company_name=company_name,
                    notes=[f"official provider does not support market={market}; source collection skipped."],
                )
        return bundle

    def _collect_us(self, client: httpx.Client, symbol: str, company_name: str | None) -> ResearchBundle:
        sources: list[SourceDocument] = []
        notes: list[str] = []

        if symbol in ETF_ISSUER_SOURCES:
            sources.extend(_fetch_static_sources(client, ETF_ISSUER_SOURCES[symbol], self.max_excerpt_chars))
            notes.append("issuer provider selected known ETF issuer page.")
            return ResearchBundle(symbol=symbol, market="US", company_name=company_name, sources=sources, notes=notes)

        cik = _lookup_sec_cik(client, symbol)
        if cik:
            notes.append(f"SEC CIK resolved: {cik}.")
            filings = _fetch_sec_recent_filings(client, cik=cik)
            for candidate in filings[: self.max_sources]:
                sources.append(_fetch_source_document(client, candidate, self.max_excerpt_chars))
        else:
            notes.append("SEC CIK lookup failed; no SEC sources collected.")

        if company_name:
            ir_source = _guess_company_ir_source(client, symbol=symbol, company_name=company_name, max_chars=self.max_excerpt_chars)
            if ir_source:
                sources.append(ir_source)
                notes.append("company IR source guessed from company name.")

        return ResearchBundle(symbol=symbol, market="US", company_name=company_name, sources=sources, notes=notes)

    def _collect_hk(self, client: httpx.Client, symbol: str, company_name: str | None) -> ResearchBundle:
        sources: list[SourceDocument] = []
        notes: list[str] = []
        candidates = _fetch_hkex_title_search(client, symbol=symbol, company_name=company_name)
        if candidates:
            for candidate in candidates[: self.max_sources]:
                sources.append(_fetch_source_document(client, candidate, self.max_excerpt_chars))
            notes.append("HKEX title search returned official announcement candidates.")
        else:
            notes.append("HKEX title search returned no candidates; no HK official sources collected.")
        return ResearchBundle(symbol=symbol, market="HK", company_name=company_name, sources=sources, notes=notes)


def normalize_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if "." in value:
        value = value.split(".")[-1]
    if value.startswith("HK") and value[2:].isdigit():
        value = value[2:]
    return value.zfill(5) if value.isdigit() and len(value) <= 5 else value


def _http_client(timeout_seconds: float) -> httpx.Client:
    return httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; InvestmentKnowledgeBot/0.1; "
                "official-source-ingestion)"
            )
        },
    )


def _fetch_static_sources(
    client: httpx.Client,
    sources: list[SourceDocument],
    max_chars: int,
) -> list[SourceDocument]:
    fetched: list[SourceDocument] = []
    for source in sources:
        fetched.append(_fetch_source_document(client, _source_to_candidate(source), max_chars))
    return fetched


def _source_to_candidate(source: SourceDocument) -> FilingCandidate:
    return FilingCandidate(
        key=source.key,
        source_type=source.source_type,
        title=source.title,
        url=source.url or "",
        publisher=source.publisher or "",
        published_at=source.published_at,
    )


def _fetch_source_document(client: httpx.Client, candidate: FilingCandidate, max_chars: int) -> SourceDocument:
    excerpt = ""
    notes = None
    try:
        response = client.get(candidate.url)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if "pdf" in content_type or candidate.url.lower().endswith(".pdf"):
            excerpt = _extract_pdf_text(response.content)
        else:
            excerpt = _extract_html_text(response.text)
    except Exception as exc:  # pragma: no cover - defensive network fallback
        notes = f"fetch failed: {exc}"

    return SourceDocument(
        key=candidate.key,
        source_type=candidate.source_type,
        title=candidate.title,
        url=candidate.url,
        publisher=candidate.publisher,
        published_at=candidate.published_at,
        notes=notes,
        content_excerpt=trim_text(excerpt, max_chars) if excerpt else None,
    )


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return ""
    try:
        import io

        reader = PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages[:20]:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)
    except Exception:
        return ""


def _extract_html_text(html: str) -> str:
    try:
        from investment_knowledge_mcp.research.providers import extract_html_title_and_text

        _title, text = extract_html_title_and_text(html)
        return text
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)


def _lookup_sec_cik(client: httpx.Client, symbol: str) -> str | None:
    response = client.get("https://www.sec.gov/files/company_tickers.json")
    response.raise_for_status()
    payload = response.json()
    for item in payload.values():
        if str(item.get("ticker", "")).upper() == symbol.upper():
            return str(item.get("cik_str")).zfill(10)
    return None


def _fetch_sec_recent_filings(client: httpx.Client, cik: str) -> list[FilingCandidate]:
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = client.get(url)
    response.raise_for_status()
    payload = response.json()
    company_name = payload.get("name") or f"CIK {cik}"
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    docs = recent.get("primaryDocument", [])

    priority = {"10-K": 0, "20-F": 0, "10-Q": 1, "8-K": 2, "6-K": 2}
    candidates: list[tuple[int, FilingCandidate]] = []
    for form, accession, filing_date, doc in zip(forms, accession_numbers, dates, docs):
        if form not in priority or not accession or not doc:
            continue
        accession_clean = str(accession).replace("-", "")
        filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_clean}/{doc}"
        source_type = "annual_report" if form in {"10-K", "20-F"} else "quarterly_results" if form == "10-Q" else "announcement"
        key = f"sec_{form.lower().replace('-', '')}_{filing_date}".replace("-", "_")
        candidates.append(
            (
                priority[form],
                FilingCandidate(
                    key=key,
                    source_type=source_type,
                    title=f"{company_name} {form} filed {filing_date}",
                    url=filing_url,
                    publisher="SEC",
                    published_at=f"{filing_date}T00:00:00-04:00" if filing_date else None,
                ),
            )
        )
    candidates.sort(key=lambda item: item[1].published_at or "", reverse=True)
    candidates.sort(key=lambda item: item[0])
    return [candidate for _priority, candidate in candidates]


def _guess_company_ir_source(
    client: httpx.Client,
    symbol: str,
    company_name: str,
    max_chars: int,
) -> SourceDocument | None:
    del client, max_chars
    # Keep v1 conservative: do not scrape search engines. Future versions can add
    # a curated IR-domain map. SEC/issuer sources remain the official default.
    return None


def _fetch_hkex_title_search(
    client: httpx.Client,
    symbol: str,
    company_name: str | None,
) -> list[FilingCandidate]:
    del company_name
    # HKEX title search endpoint is official and stable enough for v1. It returns
    # JSON inside an HTML-compatible title-search service.
    search_url = (
        "https://www1.hkexnews.hk/search/titlesearch.xhtml"
        f"?lang=en&category=0&market=SEHK&stock={quote_plus(symbol)}"
    )
    try:
        response = client.get(search_url)
        response.raise_for_status()
    except Exception:
        return []

    text = response.text
    payload = _extract_hkex_json(text)
    if not payload:
        return []

    rows = payload.get("result") or payload.get("records") or []
    if not isinstance(rows, list):
        return []

    title_priority = [
        ("annual_report", re.compile(r"annual report", re.I), 0),
        ("annual_results", re.compile(r"annual results|final results", re.I), 1),
        ("interim_results", re.compile(r"interim results|interim report", re.I), 2),
        ("prospectus", re.compile(r"prospectus|listing document", re.I), 3),
    ]
    candidates: list[tuple[int, FilingCandidate]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        title = str(row.get("TITLE") or row.get("title") or row.get("headline") or "").strip()
        if not title:
            continue
        matched = None
        for source_type, pattern, priority in title_priority:
            if pattern.search(title):
                matched = (source_type, priority)
                break
        if not matched:
            continue
        url = _hkex_row_url(row)
        if not url:
            continue
        date_text = str(row.get("DATE") or row.get("date") or row.get("releaseDate") or "").strip()
        published_at = _parse_hkex_date(date_text)
        key = f"hkex_{matched[0]}_{published_at[:10] if published_at else index}".replace("-", "_")
        candidates.append(
            (
                matched[1],
                FilingCandidate(
                    key=key,
                    source_type=matched[0],
                    title=title,
                    url=url,
                    publisher="HKEXnews",
                    published_at=published_at,
                ),
            )
        )
    candidates.sort(key=lambda item: item[1].published_at or "", reverse=True)
    candidates.sort(key=lambda item: item[0])
    return [candidate for _priority, candidate in candidates]


def _extract_hkex_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("{"):
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            return None
    match = re.search(r"(\{.*\"result\".*\})", text, flags=re.S)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _hkex_row_url(row: dict[str, Any]) -> str | None:
    for key in ("FILE_LINK", "fileLink", "url", "URL"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            link = value.strip()
            if link.startswith("http"):
                return link
            if link.startswith("/"):
                return "https://www1.hkexnews.hk" + link
            return "https://www1.hkexnews.hk/" + link.lstrip("./")
    return None


def _parse_hkex_date(value: str) -> str | None:
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:10], fmt).strftime("%Y-%m-%dT00:00:00+08:00")
        except ValueError:
            continue
    return None
