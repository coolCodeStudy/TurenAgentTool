from __future__ import annotations

from datetime import date
import re
from typing import Any
from xml.etree import ElementTree

from investment_knowledge_mcp.events.models import EventPacket, EventSource
from investment_knowledge_mcp.events.sec_client import SecDocument, SecFiling


SALE_CODES = {"S", "F"}
LOW_PRIORITY_FORM4_CODES = {"A", "M", "G", "J"}


def parse_sec_document(document: SecDocument) -> list[EventPacket]:
    filing = document.filing
    source = _source_from_document(document)
    form_type = filing.form_type.upper()
    if form_type == "4":
        return parse_form4(document.text, filing=filing, source=source)
    if form_type == "144":
        return parse_form144(document.text, filing=filing, source=source)
    if form_type in {"424B5", "S-3"}:
        return [_candidate_event(filing=filing, source=source, event_type="offering_candidate")]
    if form_type == "8-K":
        return [_candidate_event(filing=filing, source=source, event_type="material_8k")]
    return []


def parse_form4(text: str, *, filing: SecFiling, source: EventSource) -> list[EventPacket]:
    root = _parse_xml(text)
    if root is None:
        return [
            _candidate_event(
                filing=filing,
                source=source,
                event_type="form_4_insider_transaction",
                uncertainty="Form 4 XML 解析失败，只能作为候选事件。",
            )
        ]
    owner = _text(root, "rptOwnerName")
    relationship = _owner_relationship(root)
    transactions = []
    for node in _iter_tags(root, "nonDerivativeTransaction"):
        code = (_text(node, "transactionCode") or "").upper()
        shares = _text(node, "transactionShares")
        price = _text(node, "transactionPricePerShare")
        transaction_date = _text(node, "transactionDate") or filing.filing_date
        acquired_disposed = (_text(node, "transactionAcquiredDisposedCode") or "").upper()
        plan = _text(node, "is10b5-1")
        transactions.append(
            {
                "transaction_date": transaction_date,
                "transaction_code": code,
                "shares": _number_or_text(shares),
                "price": _number_or_text(price),
                "acquired_disposed": acquired_disposed,
                "is_10b5_1": _bool_or_none(plan),
            }
        )
    if not transactions:
        return [
            _candidate_event(
                filing=filing,
                source=source,
                event_type="form_4_insider_transaction",
                uncertainty="Form 4 未解析到非衍生交易明细。",
            )
        ]

    sale_transactions = [
        item for item in transactions if item.get("transaction_code") in SALE_CODES and item.get("acquired_disposed") == "D"
    ]
    important = sale_transactions or transactions
    total_shares = _sum_numeric(item.get("shares") for item in important)
    transaction_date = str(important[0].get("transaction_date") or filing.filing_date)[:10]
    high_priority = bool(sale_transactions)
    code_summary = ", ".join(sorted({str(item.get("transaction_code")) for item in important if item.get("transaction_code")}))
    title_action = "内部人卖出披露" if high_priority else "内部人交易披露"
    uncertainties = []
    if not high_priority:
        uncertainties.append("Form 4 未识别为直接卖出；可能是授予、行权或其他交易代码。")
    return [
        EventPacket(
            market=filing.market,
            symbol=filing.symbol,
            event_type="form_4_insider_transaction",
            event_title=f"{filing.symbol} Form 4 {title_action}",
            event_date=transaction_date,
            priority="high" if high_priority else "medium",
            confidence="high",
            source=source,
            source_facts=[
                {
                    "source_type": "sec_filing",
                    "form": "4",
                    "filed_at": filing.filing_date,
                    "owner": owner,
                    "relationship": relationship,
                    "transaction_codes": code_summary,
                    "total_shares": total_shares,
                    "transactions": important,
                }
            ],
            uncertainties=uncertainties,
        )
    ]


def parse_form144(text: str, *, filing: SecFiling, source: EventSource) -> list[EventPacket]:
    root = _parse_xml(text)
    plain_text = _plain_text(text)
    seller = _first_text(root, ["nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold", "sellerName"]) if root is not None else None
    shares = _first_text(root, ["securitiesToBeSoldShares", "noOfShares", "numberOfShares"]) if root is not None else None
    notice_date = _first_text(root, ["noticeDate", "dateOfNotice", "approxSaleDate"]) if root is not None else None
    market_value = _first_text(root, ["aggregateMarketValue", "marketValue"]) if root is not None else None
    if not seller:
        seller = _regex_after(plain_text, r"(?:name of person|seller)[^\n:]*[:\s]+(.{2,80})")
    if not shares:
        shares = _regex_after(plain_text, r"(?:shares|number of shares)[^\n:]*[:\s]+([0-9,]+)")
    if not notice_date:
        notice_date = _regex_after(plain_text, r"(?:notice date|approximate date of sale)[^\n:]*[:\s]+(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})")
    event_date = _normalize_date(notice_date) or filing.filing_date
    facts = {
        "source_type": "sec_filing",
        "form": "144",
        "filed_at": filing.filing_date,
        "seller": seller,
        "shares": _number_or_text(shares),
        "notice_date": notice_date,
        "market_value": _number_or_text(market_value),
    }
    uncertainties = []
    if not seller:
        uncertainties.append("Form 144 未解析到拟售人。")
    if not shares:
        uncertainties.append("Form 144 未解析到拟售股数。")
    return [
        EventPacket(
            market=filing.market,
            symbol=filing.symbol,
            event_type="form_144_sale_notice",
            event_title=f"{filing.symbol} Form 144 拟出售披露",
            event_date=event_date,
            priority="high",
            confidence="medium" if uncertainties else "high",
            source=source,
            source_facts=[facts],
            uncertainties=uncertainties,
        )
    ]


def _candidate_event(
    *,
    filing: SecFiling,
    source: EventSource,
    event_type: str,
    uncertainty: str | None = None,
) -> EventPacket:
    if event_type == "offering_candidate":
        title = f"{filing.symbol} {filing.form_type} 发行/增发候选"
    elif event_type == "material_8k":
        title = f"{filing.symbol} 8-K 重大事项候选"
    else:
        title = f"{filing.symbol} {filing.form_type} 事件候选"
    uncertainties = ["复杂 SEC 文件需要后续解析确认具体条款。"]
    if uncertainty:
        uncertainties.insert(0, uncertainty)
    return EventPacket(
        market=filing.market,
        symbol=filing.symbol,
        event_type=event_type,
        event_title=title,
        event_date=filing.filing_date,
        priority="medium",
        confidence="medium",
        source=source,
        source_facts=[
            {
                "source_type": "sec_filing",
                "form": filing.form_type,
                "filed_at": filing.filing_date,
                "accession_number": filing.accession_number,
                "primary_document": filing.primary_document,
            }
        ],
        uncertainties=uncertainties,
        needs_research=True,
    )


def _source_from_document(document: SecDocument) -> EventSource:
    filing = document.filing
    return EventSource(
        source_type="sec_filing",
        publisher="SEC",
        url=filing.filing_url,
        title=f"{filing.company_name} {filing.form_type} filed {filing.filing_date}",
        published_at=f"{filing.filing_date}T00:00:00-04:00" if filing.filing_date else None,
        market=filing.market,
        symbol=filing.symbol,
        accession_number=filing.accession_number,
        cik=filing.cik,
        form_type=filing.form_type,
        raw_hash=document.raw_hash,
        excerpt=document.text[:2000],
        parsed_facts={"form_type": filing.form_type, "filing_date": filing.filing_date},
    )


def _parse_xml(text: str) -> ElementTree.Element | None:
    try:
        return ElementTree.fromstring(text.encode("utf-8"))
    except ElementTree.ParseError:
        return None


def _iter_tags(root: ElementTree.Element, local_name: str) -> list[ElementTree.Element]:
    return [node for node in root.iter() if _local_name(node.tag) == local_name]


def _text(root: ElementTree.Element, local_name: str) -> str | None:
    for node in root.iter():
        if _local_name(node.tag) == local_name:
            text = "".join(node.itertext()).strip()
            return text or None
    return None


def _first_text(root: ElementTree.Element | None, names: list[str]) -> str | None:
    if root is None:
        return None
    for name in names:
        value = _text(root, name)
        if value:
            return value
    return None


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _owner_relationship(root: ElementTree.Element) -> dict[str, Any]:
    return {
        "is_director": _bool_or_none(_text(root, "isDirector")),
        "is_officer": _bool_or_none(_text(root, "isOfficer")),
        "is_ten_percent_owner": _bool_or_none(_text(root, "isTenPercentOwner")),
        "officer_title": _text(root, "officerTitle"),
    }


def _plain_text(text: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "\n", text)
    cleaned = re.sub(r"(?s)<[^>]+>", "\n", cleaned)
    cleaned = re.sub(r"&nbsp;?", " ", cleaned)
    return re.sub(r"[ \t]+", " ", cleaned)


def _regex_after(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.I)
    if not match:
        return None
    return match.group(1).strip().splitlines()[0].strip()


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if match:
        month, day, year = match.groups()
        return date(int(year), int(month), int(day)).isoformat()
    return value[:10]


def _number_or_text(value: Any) -> float | str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return text


def _sum_numeric(values: Any) -> float | None:
    total = 0.0
    found = False
    for value in values:
        if isinstance(value, (int, float)):
            total += float(value)
            found = True
    return total if found else None


def _bool_or_none(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None
