from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
import ssl
from typing import Any
from urllib import request as urlrequest

from investment_knowledge_mcp.events.models import EVENT_FORMS


SEC_BASE_URL = "https://www.sec.gov"
SEC_DATA_URL = "https://data.sec.gov"
DEFAULT_SEC_TIMEOUT_SECONDS = 30.0
DEFAULT_SEC_USER_AGENT = "InvestmentKnowledgeBot/0.1 contact=investment-knowledge-local"


class SecClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class SecFiling:
    market: str
    symbol: str
    cik: str
    company_name: str
    form_type: str
    accession_number: str
    filing_date: str
    report_date: str | None
    primary_document: str
    filing_url: str


@dataclass(frozen=True)
class SecDocument:
    filing: SecFiling
    text: str
    raw_hash: str
    content_type: str | None = None


class SecClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_SEC_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_SEC_USER_AGENT,
        client: Any | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self._client = client

    def __enter__(self) -> "SecClient":
        if self._client is None:
            self._client = self._new_client()
        return self

    def __exit__(self, *_args: object) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def lookup_cik(self, symbol: str) -> str | None:
        payload = self._get_json(f"{SEC_BASE_URL}/files/company_tickers.json")
        normalized = normalize_symbol(symbol)
        items = payload.values() if isinstance(payload, dict) else payload
        for item in items:
            if str(item.get("ticker") or "").upper() == normalized:
                return str(item.get("cik_str")).zfill(10)
        return None

    def fetch_recent_filings(self, *, symbol: str, market: str = "US", days: int = 30) -> list[SecFiling]:
        symbol = normalize_symbol(symbol)
        cik = self.lookup_cik(symbol)
        if not cik:
            raise SecClientError(f"SEC CIK not found for {symbol}")
        return self.fetch_recent_filings_by_cik(symbol=symbol, market=market, cik=cik, days=days)

    def fetch_recent_filings_by_cik(self, *, symbol: str, market: str, cik: str, days: int) -> list[SecFiling]:
        url = f"{SEC_DATA_URL}/submissions/CIK{str(cik).zfill(10)}.json"
        payload = self._get_json(url)
        return select_event_filings(payload=payload, symbol=symbol, market=market, cik=str(cik).zfill(10), days=days)

    def fetch_document(self, filing: SecFiling) -> SecDocument:
        response = self._client_or_new().get(filing.filing_url)
        try:
            response.raise_for_status()
        except Exception as exc:
            raise SecClientError(f"SEC document fetch failed: {filing.filing_url}: {exc}") from exc
        text = response.text
        raw_hash = hashlib.sha256(response.content).hexdigest()
        return SecDocument(
            filing=filing,
            text=text,
            raw_hash=raw_hash,
            content_type=response.headers.get("content-type"),
        )

    def _get_json(self, url: str) -> Any:
        response = self._client_or_new().get(url)
        try:
            response.raise_for_status()
        except Exception as exc:
            raise SecClientError(f"SEC request failed: {url}: {exc}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise SecClientError(f"SEC response is not JSON: {url}") from exc

    def _client_or_new(self) -> Any:
        if self._client is None:
            self._client = self._new_client()
        return self._client

    def _new_client(self) -> Any:
        try:
            import httpx

            return httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            )
        except ModuleNotFoundError:
            return _UrllibClient(timeout_seconds=self.timeout_seconds, user_agent=self.user_agent)


def normalize_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().upper()
    if "." in value:
        value = value.split(".")[-1]
    return value


def select_event_filings(payload: dict[str, Any], *, symbol: str, market: str, cik: str, days: int) -> list[SecFiling]:
    company_name = str(payload.get("name") or f"CIK {cik}")
    recent = payload.get("filings", {}).get("recent", {})
    cutoff = date.today() - timedelta(days=max(0, int(days)))
    rows = zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("filingDate", []),
        recent.get("reportDate", []),
        recent.get("primaryDocument", []),
    )
    filings: list[SecFiling] = []
    for form, accession, filing_date, report_date, primary_document in rows:
        form_type = str(form or "").strip().upper()
        if form_type not in EVENT_FORMS:
            continue
        filing_date_text = str(filing_date or "")
        if filing_date_text and _parse_date(filing_date_text) < cutoff:
            continue
        accession_text = str(accession or "").strip()
        primary_document_text = str(primary_document or "").strip()
        if not accession_text or not primary_document_text:
            continue
        accession_clean = accession_text.replace("-", "")
        document_path = _raw_document_path(form_type=form_type, primary_document=primary_document_text)
        filing_url = f"{SEC_BASE_URL}/Archives/edgar/data/{int(str(cik))}/{accession_clean}/{document_path}"
        filings.append(
            SecFiling(
                market=market.upper(),
                symbol=normalize_symbol(symbol),
                cik=str(cik).zfill(10),
                company_name=company_name,
                form_type=form_type,
                accession_number=accession_text,
                filing_date=filing_date_text,
                report_date=str(report_date or "") or None,
                primary_document=primary_document_text,
                filing_url=filing_url,
            )
        )
    return sorted(filings, key=lambda item: item.filing_date, reverse=True)


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return date.min


def _raw_document_path(*, form_type: str, primary_document: str) -> str:
    if form_type in {"4", "144"} and "/" in primary_document:
        prefix, basename = primary_document.split("/", 1)
        if prefix.upper().startswith("XSLF345"):
            return basename
    return primary_document


class _UrllibResponse:
    def __init__(self, *, url: str, status_code: int, headers: Any, content: bytes) -> None:
        self.url = url
        self.status_code = status_code
        self.headers = dict(headers)
        self.content = content
        encoding = "utf-8"
        content_type = self.headers.get("Content-Type") or self.headers.get("content-type") or ""
        if "charset=" in content_type:
            encoding = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
        self.text = content.decode(encoding or "utf-8", errors="replace")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise SecClientError(f"HTTP {self.status_code} for {self.url}")

    def json(self) -> Any:
        return json.loads(self.text)


class _UrllibClient:
    def __init__(self, *, timeout_seconds: float, user_agent: str) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def get(self, url: str) -> _UrllibResponse:
        req = urlrequest.Request(url, headers={"User-Agent": self.user_agent})
        with urlrequest.urlopen(req, timeout=self.timeout_seconds, context=_ssl_context()) as response:
            return _UrllibResponse(
                url=url,
                status_code=int(response.status),
                headers=response.headers,
                content=response.read(),
            )

    def close(self) -> None:
        return None


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None
