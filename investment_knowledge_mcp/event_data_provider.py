from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
import html
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


class EventDataProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class NewsEventSnapshot:
    events: list[dict[str, Any]]
    fetched_at: datetime
    source: str = "yahoo_finance_rss"


def get_yahoo_finance_news_events(
    symbols: list[str],
    *,
    start: date,
    end: date,
    timeout_seconds: float = 5.0,
    max_items_per_symbol: int = 8,
) -> NewsEventSnapshot:
    cleaned_symbols = _clean_symbols(symbols)
    if not cleaned_symbols:
        return NewsEventSnapshot(events=[], fetched_at=datetime.now(timezone.utc))

    events: list[dict[str, Any]] = []
    errors: list[str] = []
    for symbol in cleaned_symbols:
        try:
            events.extend(
                _fetch_yahoo_finance_rss(
                    symbol=symbol,
                    start=start,
                    end=end,
                    timeout_seconds=timeout_seconds,
                    max_items=max_items_per_symbol,
                )
            )
        except EventDataProviderError as exc:
            errors.append(f"{symbol}: {exc}")
            continue

    if not events and errors:
        raise EventDataProviderError("Yahoo Finance RSS returned no usable dated events: " + "; ".join(errors[:6]))
    return NewsEventSnapshot(events=_dedupe_events(events), fetched_at=datetime.now(timezone.utc))


def _clean_symbols(symbols: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        value = str(symbol or "").strip().upper()
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned[:16]


def _fetch_yahoo_finance_rss(
    *,
    symbol: str,
    start: date,
    end: date,
    timeout_seconds: float,
    max_items: int,
) -> list[dict[str, Any]]:
    params = urlencode({"s": symbol, "region": "US", "lang": "en-US"})
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?{params}"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; InvestmentKnowledgeBot/0.1)",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds, context=_ssl_context()) as response:
            payload = response.read()
    except HTTPError as exc:
        raise EventDataProviderError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise EventDataProviderError(str(exc)) from exc

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise EventDataProviderError(f"invalid RSS XML: {exc}") from exc

    parsed_events: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        event = _event_from_item(item=item, query_symbol=symbol, start=start, end=end)
        if event is None:
            continue
        parsed_events.append(event)
        if len(parsed_events) >= max_items:
            break
    return parsed_events


def _event_from_item(
    *,
    item: ET.Element,
    query_symbol: str,
    start: date,
    end: date,
) -> dict[str, Any] | None:
    title = _text(item, "title")
    link = _text(item, "link")
    description = _text(item, "description")
    published = _parse_rss_date(_text(item, "pubDate"))
    if not title or not link or published is None:
        return None
    published_date = published.date()
    if published_date < start or published_date > end:
        return None
    guid = _text(item, "guid")
    return {
        "query_symbol": query_symbol,
        "source_name": "Yahoo Finance",
        "source_type": "financial_news_rss",
        "source_id": f"yahoo_finance_rss:{query_symbol}:{guid or link}",
        "published_at": published.isoformat(),
        "title": title,
        "url": link,
        "summary": description,
        "raw": {"guid": guid},
    }


def _text(item: ET.Element, tag: str) -> str:
    element = item.find(tag)
    if element is None or element.text is None:
        return ""
    return html.unescape(element.text).strip()


def _parse_rss_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi
    except Exception:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        key = "|".join(str(event.get(part) or "") for part in ("url", "title", "published_at"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped
