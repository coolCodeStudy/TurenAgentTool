from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Any
from urllib.parse import quote_plus, urljoin

import httpx

from investment_knowledge_mcp.research.models import ResearchBundle, SourceDocument
from investment_knowledge_mcp.research.providers import ResearchProvider, trim_text


DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_EXCERPT_CHARS = 12000
HKEX_STOCK_ID_CACHE: dict[str, str] = {
    # Observed from successful Codex research jobs. HKEX title search is much
    # more reliable with stockId than ticker text for some issuers.
    "00532": "1131",
    "01810": "190371",
    "81810": "190371",
    "03690": "198419",
}

HK_ISSUER_IR_PAGES: dict[str, list[str]] = {
    # Observed from completed research-agent jobs. These issuer pages expose
    # static PDF report links and are useful when HKEX title search misses.
    "02367": [
        "https://ir.xajuzi.com/list-l3s05l87/index.html/1/10",
        "https://ir.xajuzi.com/list-8q4um8rx/index.html/1/10",
    ],
}

HK_ISSUER_STATIC_SOURCES: dict[str, list[SourceDocument]] = {
    "02367": [
        SourceDocument(
            key="company_ir_homepage",
            source_type="company_ir",
            title="Giant Biogene Investor Relations",
            url="https://ir.xajuzi.com/",
            publisher="巨子生物",
        )
    ],
    "03690": [
        SourceDocument(
            key="company_about_us",
            source_type="company_profile",
            title="Meituan About Us",
            url="https://about.meituan.com/en-US/about-us",
            publisher="Meituan",
        ),
    ],
}

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
            hk_max_sources = max(self.max_sources, 4)
            for candidate in candidates[:hk_max_sources]:
                sources.append(_fetch_source_document(client, candidate, self.max_excerpt_chars))
            notes.append("HKEX title search returned official announcement candidates.")
        else:
            notes.append("HKEX title search returned no candidates; no HK official sources collected.")

        static_sources = HK_ISSUER_STATIC_SOURCES.get(symbol, [])
        if static_sources:
            sources.extend(_fetch_static_sources(client, static_sources, self.max_excerpt_chars))
            notes.append("curated issuer static sources collected.")

        ir_candidates = _fetch_hk_issuer_ir_candidates(client, symbol=symbol)
        if ir_candidates:
            remaining_slots = max(self.max_sources + 2, 5) - len(sources)
            for candidate in ir_candidates[: max(0, remaining_slots)]:
                sources.append(_fetch_source_document(client, candidate, self.max_excerpt_chars))
            notes.append("issuer IR report-list provider returned report candidates.")

        sources = _dedupe_source_documents(sources)
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
    search_urls = _hkex_title_search_urls(symbol=symbol, company_name=company_name)
    seen_urls: set[str] = set(search_urls)
    rows: list[dict[str, Any]] = []
    for search_url in search_urls:
        try:
            response = client.get(search_url)
            response.raise_for_status()
        except Exception:
            continue

        stock_ids = _extract_hkex_stock_ids(response.text)
        for stock_id in stock_ids:
            stock_id_url = _hkex_title_search_url(stock_id=stock_id)
            if stock_id_url not in seen_urls:
                seen_urls.add(stock_id_url)
                search_urls.append(stock_id_url)

        payload = _extract_hkex_json(response.text)
        if not payload:
            continue
        payload_rows = payload.get("result") or payload.get("records") or []
        if isinstance(payload_rows, list):
            rows.extend(row for row in payload_rows if isinstance(row, dict))

    candidates: list[tuple[int, FilingCandidate]] = []
    for index, row in enumerate(rows):
        title = _clean_hkex_title(row.get("TITLE") or row.get("title") or row.get("headline") or "")
        if not title:
            continue
        classification = _classify_hkex_title(title)
        if not classification:
            continue
        url = _hkex_row_url(row)
        if not url:
            continue
        date_text = str(row.get("DATE") or row.get("date") or row.get("releaseDate") or "").strip()
        published_at = _parse_hkex_date(date_text)
        source_type, priority = classification
        key = f"hkex_{source_type}_{published_at[:10] if published_at else index}".replace("-", "_")
        candidates.append(
            (
                priority,
                FilingCandidate(
                    key=key,
                    source_type=source_type,
                    title=title,
                    url=url,
                    publisher="HKEXnews",
                    published_at=published_at,
                ),
            )
        )
    candidates.sort(key=lambda item: item[1].published_at or "", reverse=True)
    candidates.sort(key=lambda item: item[0])
    return _dedupe_hkex_candidates([candidate for _priority, candidate in candidates])


def _hkex_title_search_urls(symbol: str, company_name: str | None) -> list[str]:
    candidates = [symbol]
    if symbol.isdigit():
        candidates.append(str(int(symbol)))
    if company_name:
        candidates.append(company_name)

    urls: list[str] = []
    stock_id = HKEX_STOCK_ID_CACHE.get(symbol)
    if stock_id:
        urls.append(_hkex_title_search_url(stock_id=stock_id))
    for stock in candidates:
        cleaned = stock.strip()
        if cleaned:
            urls.append(_hkex_title_search_url(stock=cleaned))
    return _dedupe_strings(urls)


def _hkex_title_search_url(stock: str | None = None, stock_id: str | None = None) -> str:
    base = "https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en&category=0&market=SEHK"
    if stock_id:
        return f"{base}&stockId={quote_plus(stock_id)}"
    if stock:
        return f"{base}&stock={quote_plus(stock)}"
    return base


def _extract_hkex_stock_ids(text: str) -> list[str]:
    return _dedupe_strings(re.findall(r"stockId[\"'=:\s]+(\d+)", text, flags=re.I))


def _clean_hkex_title(value: Any) -> str:
    title = str(value or "")
    title = re.sub(r"<[^>]+>", " ", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def _classify_hkex_title(title: str) -> tuple[str, int] | None:
    checks: list[tuple[str, re.Pattern[str], int]] = [
        ("annual_report", re.compile(r"annual report|年报|年報", re.I), 0),
        ("annual_results", re.compile(r"annual results|final results|年度业绩|年度業績", re.I), 1),
        ("quarterly_results", re.compile(r"quarterly results|three months ended|季度业绩|季度業績", re.I), 2),
        ("interim_results", re.compile(r"interim results|interim report|half-year|中期报告|中期報告", re.I), 3),
        (
            "announcement",
            re.compile(
                r"repurchase|buy-?back|profit alert|profit warning|inside information|business update|"
                r"major transaction|acquisition|盈利警告|主要交易|收购|收購",
                re.I,
            ),
            4,
        ),
        ("prospectus", re.compile(r"prospectus|listing document|全球发售|全球發售|招股", re.I), 5),
    ]
    for source_type, pattern, priority in checks:
        if pattern.search(title):
            return source_type, priority
    return None


def _dedupe_hkex_candidates(candidates: list[FilingCandidate]) -> list[FilingCandidate]:
    deduped: list[FilingCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.url or f"{candidate.title}:{candidate.published_at or ''}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _dedupe_source_documents(sources: list[SourceDocument]) -> list[SourceDocument]:
    deduped: list[SourceDocument] = []
    seen: set[str] = set()
    for source in sources:
        key = source.url or source.key
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


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


def _fetch_hk_issuer_ir_candidates(client: httpx.Client, symbol: str) -> list[FilingCandidate]:
    pages = HK_ISSUER_IR_PAGES.get(symbol, [])
    candidates: list[tuple[int, FilingCandidate]] = []
    for page_url in pages:
        try:
            response = client.get(page_url)
            response.raise_for_status()
        except Exception:
            continue
        for index, item in enumerate(_extract_pdf_links(response.text, base_url=page_url)):
            classification = _classify_issuer_ir_title(item["title"])
            if not classification:
                continue
            source_type, priority = classification
            published_at = _parse_issuer_date(item["title"]) or _parse_issuer_date(item["url"])
            key = _issuer_ir_key(source_type=source_type, title=item["title"], url=item["url"], fallback_index=index)
            candidates.append(
                (
                    priority,
                    FilingCandidate(
                        key=key,
                        source_type=source_type,
                        title=item["title"],
                        url=item["url"],
                        publisher=_issuer_publisher(symbol),
                        published_at=published_at,
                    ),
                )
            )
    candidates.sort(key=lambda item: item[1].published_at or "", reverse=True)
    candidates.sort(key=lambda item: item[0])
    return _dedupe_hkex_candidates([candidate for _priority, candidate in candidates])


def _extract_pdf_links(html: str, base_url: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    anchor_pattern = re.compile(
        r"<a\b[^>]*href=[\"'](?P<href>[^\"']+\.pdf(?:\?[^\"']*)?)[\"'][^>]*>(?P<label>.*?)</a>",
        re.I | re.S,
    )
    for match in anchor_pattern.finditer(html):
        href = match.group("href").strip()
        label = _extract_html_text(match.group("label")).strip()
        url = urljoin(base_url, href)
        title = label or _title_from_pdf_url(url)
        links.append({"title": _clean_hkex_title(title), "url": url})

    for url in re.findall(r"https?://[^\s\"'<>]+\.pdf(?:\?[^\s\"'<>]+)?", html, flags=re.I):
        cleaned_url = url.rstrip(").,;")
        title = _title_from_pdf_url(cleaned_url)
        links.append({"title": title, "url": cleaned_url})

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        deduped.append(link)
    return deduped


def _title_from_pdf_url(url: str) -> str:
    filename = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[_-]+", " ", filename).removesuffix(".pdf").strip() or url


def _issuer_ir_key(source_type: str, title: str, url: str, fallback_index: int) -> str:
    report_year = _extract_report_year(title) or _extract_report_year(url)
    fingerprint = _pdf_fingerprint(url) or hashlib.sha1(f"{title}|{url}".encode("utf-8")).hexdigest()[:10]
    year_or_index = report_year or f"item_{fallback_index}"
    return _slug_key(f"issuer_ir_{source_type}_{year_or_index}_{fingerprint}")


def _extract_report_year(value: str) -> str | None:
    match = re.search(r"(20\d{2}|19\d{2})", value)
    if match:
        return match.group(1)

    normalized = value.translate(str.maketrans({"零": "〇", "○": "〇", "Ｏ": "〇", "O": "〇"}))
    match = re.search(r"([一二三四五六七八九〇]{4})年", normalized)
    if not match:
        return None
    digits = {"〇": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
    year = "".join(digits.get(char, "") for char in match.group(1))
    if re.fullmatch(r"(20|19)\d{2}", year):
        return year
    return None


def _pdf_fingerprint(url: str) -> str | None:
    stem = url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]
    stem = stem.removesuffix(".pdf").removesuffix(".PDF")
    match = re.search(r"(\d{8,})", stem)
    if match:
        return match.group(1)[-24:]
    slug = _slug_key(stem)
    return slug[:24] if slug else None


def _slug_key(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
    return re.sub(r"_+", "_", slug)


def _classify_issuer_ir_title(title: str) -> tuple[str, int] | None:
    checks: list[tuple[str, re.Pattern[str], int]] = [
        ("annual_report", re.compile(r"annual report|年报|年報", re.I), 0),
        ("interim_results", re.compile(r"interim report|interim results|中期报告|中期報告", re.I), 2),
        ("quarterly_results", re.compile(r"quarterly results|three months ended|季度业绩|季度業績", re.I), 3),
        ("prospectus", re.compile(r"prospectus|global offering|全球发售|全球發售|招股", re.I), 4),
        ("announcement", re.compile(r"results|业绩|業績|公告|announcement", re.I), 5),
    ]
    for source_type, pattern, priority in checks:
        if pattern.search(title):
            return source_type, priority
    return None


def _issuer_publisher(symbol: str) -> str:
    publishers = {
        "02367": "巨子生物",
        "03690": "Meituan",
    }
    return publishers.get(symbol, "Issuer IR")


def _parse_issuer_date(value: str) -> str | None:
    for pattern, fmt in (
        (r"(20\d{2})[-_/](\d{1,2})[-_/](\d{1,2})", "%Y-%m-%d"),
        (r"(20\d{2})(\d{2})(\d{2})", "%Y%m%d"),
    ):
        match = re.search(pattern, value)
        if not match:
            continue
        raw = "-".join(match.groups()) if fmt == "%Y-%m-%d" else "".join(match.groups())
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%dT00:00:00+08:00")
        except ValueError:
            continue
    return None


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
