from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from investment_knowledge_mcp.events.models import EventPacket, EventScanResult, ScanError
from investment_knowledge_mcp.events.sec_client import SecClient, SecClientError, normalize_symbol
from investment_knowledge_mcp.events.sec_parsers import parse_sec_document


def scan_stock_events(
    *,
    symbol: str,
    market: str = "US",
    days: int = 90,
    persist: bool = True,
    sec_client: SecClient | None = None,
) -> EventScanResult:
    started_at = datetime.now(timezone.utc)
    market = market.upper()
    symbol = normalize_symbol(symbol)
    events: list[EventPacket] = []
    errors: list[ScanError] = []
    filings = []
    client = sec_client or SecClient()
    close_client = sec_client is None
    try:
        if close_client:
            client.__enter__()
        try:
            filings = client.fetch_recent_filings(symbol=symbol, market=market, days=days)
        except Exception as exc:
            errors.append(ScanError(market=market, symbol=symbol, stage="sec_submissions", message=str(exc)))
            filings = []
        for filing in filings:
            try:
                document = client.fetch_document(filing)
                events.extend(parse_sec_document(document))
            except Exception as exc:
                errors.append(
                    ScanError(
                        market=market,
                        symbol=symbol,
                        stage=f"sec_document:{filing.form_type}:{filing.accession_number}",
                        message=str(exc),
                    )
                )
    finally:
        if close_client:
            client.__exit__(None, None, None)

    persisted = _persist_scan_outputs(
        persist=persist,
        events=events,
        filings=filings,
        scope="stock",
        market=market,
        symbol=symbol,
        errors=errors,
        started_at=started_at,
        symbols_total=1,
        symbols_scanned=1 if filings or not errors else 0,
    )
    return persisted


def scan_symbols_events(
    *,
    symbols: list[str],
    market: str = "US",
    days: int = 30,
    persist: bool = True,
    sec_client: SecClient | None = None,
) -> EventScanResult:
    started_at = datetime.now(timezone.utc)
    market = market.upper()
    normalized_symbols = [normalize_symbol(symbol) for symbol in symbols if str(symbol or "").strip()]
    all_events: list[EventPacket] = []
    all_errors: list[ScanError] = []
    symbols_scanned = 0
    client = sec_client or SecClient()
    close_client = sec_client is None
    try:
        if close_client:
            client.__enter__()
        for symbol in normalized_symbols:
            result = scan_stock_events(
                symbol=symbol,
                market=market,
                days=days,
                persist=False,
                sec_client=client,
            )
            all_events.extend(result.events)
            all_errors.extend(result.errors)
            symbols_scanned += result.symbols_scanned
    finally:
        if close_client:
            client.__exit__(None, None, None)
    result = EventScanResult.from_events(
        scope="portfolio",
        market=market,
        symbol=None,
        events=all_events,
        errors=all_errors,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        symbols_total=len(normalized_symbols),
        symbols_scanned=symbols_scanned,
    )
    if persist:
        from investment_knowledge_mcp.events import repository as event_repository

        persisted_events = [event_repository.persist_event_packet(packet) for packet in all_events]
        event_repository.record_event_scan_run(result)
        result = EventScanResult(
            **{**result.__dict__, "persisted_events": persisted_events}
        )
    return result


def scan_portfolio_events(*, days: int = 30, persist: bool = True) -> EventScanResult:
    started_at = datetime.now(timezone.utc)
    try:
        from investment_knowledge_mcp.futu_provider import get_futu_positions

        snapshot = get_futu_positions()
    except Exception as exc:
        result = EventScanResult.from_events(
            scope="portfolio",
            market="US",
            symbol=None,
            events=[],
            errors=[ScanError(market="US", symbol=None, stage="futu_positions", message=str(exc))],
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )
        if persist:
            from investment_knowledge_mcp.events import repository as event_repository

            event_repository.record_event_scan_run(result)
        return result
    symbols = _us_symbols_from_positions(snapshot.positions)
    return scan_symbols_events(symbols=symbols, market="US", days=days, persist=persist)


def _persist_scan_outputs(
    *,
    persist: bool,
    events: list[EventPacket],
    filings: list[Any],
    scope: str,
    market: str,
    symbol: str,
    errors: list[ScanError],
    started_at: datetime,
    symbols_total: int,
    symbols_scanned: int,
) -> EventScanResult:
    result = EventScanResult.from_events(
        scope=scope,
        market=market,
        symbol=symbol,
        events=events,
        errors=errors,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        symbols_total=symbols_total,
        symbols_scanned=symbols_scanned,
    )
    if not persist:
        return result
    from investment_knowledge_mcp.events import repository as event_repository

    persisted_events = [event_repository.persist_event_packet(packet) for packet in events]
    event_repository.record_event_scan_run(result)
    if filings:
        event_repository.update_scan_checkpoint(
            market=market,
            symbol=symbol,
            last_filing_date=max(str(filing.filing_date) for filing in filings if filing.filing_date),
            last_accession_numbers=[str(filing.accession_number) for filing in filings],
        )
    return EventScanResult(
        **{**result.__dict__, "persisted_events": persisted_events}
    )


def _us_symbols_from_positions(positions: list[dict[str, Any]]) -> list[str]:
    symbols: list[str] = []
    for position in positions:
        try:
            qty = float(position.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            continue
        code = str(position.get("code") or "").strip().upper()
        if "." in code:
            market, symbol = code.split(".", 1)
        else:
            market, symbol = "", code
        if market == "US" and symbol:
            symbols.append(symbol)
    return sorted(set(symbols))
