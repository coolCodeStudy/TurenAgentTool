from __future__ import annotations

import unittest
from unittest.mock import patch

from investment_knowledge_mcp.events.models import EventPacket, EventScanResult, EventSource, ScanError
from investment_knowledge_mcp.events.renderer import render_muted_event, render_scan_result
from investment_knowledge_mcp.events.sec_client import SecClient, SecDocument, SecFiling, select_event_filings
from investment_knowledge_mcp.events.sec_parsers import parse_form144, parse_form4


class FakeResponse:
    def __init__(self, payload=None, text: str = "", status_code: int = 200) -> None:
        self._payload = payload
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status_code
        self.headers = {"content-type": "application/xml"}

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttpClient:
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses

    def get(self, url: str) -> FakeResponse:
        if url not in self.responses:
            raise AssertionError(f"unexpected url: {url}")
        return self.responses[url]

    def close(self) -> None:
        pass


class PortfolioEventTests(unittest.TestCase):
    def test_lookup_cik_uses_sec_ticker_mapping(self) -> None:
        client = SecClient(
            client=FakeHttpClient(
                {
                    "https://www.sec.gov/files/company_tickers.json": FakeResponse(
                        {"0": {"ticker": "AXTI", "cik_str": 1051627}}
                    )
                }
            )
        )
        self.assertEqual(client.lookup_cik("axti"), "0001051627")

    def test_select_event_filings_filters_supported_forms(self) -> None:
        payload = {
            "name": "Example Inc.",
            "filings": {
                "recent": {
                    "form": ["4", "144", "10-K", "8-K", "S-3", "424B5"],
                    "accessionNumber": ["a1", "a2", "a3", "a4", "a5", "a6"],
                    "filingDate": ["2999-01-06", "2999-01-05", "2999-01-04", "2999-01-03", "2999-01-02", "2999-01-01"],
                    "reportDate": ["", "", "", "", "", ""],
                    "primaryDocument": ["xslF345X06/f4.xml", "xslF345X06/f144.xml", "10k.htm", "8k.htm", "s3.htm", "424.htm"],
                }
            },
        }
        filings = select_event_filings(payload, symbol="AXTI", market="US", cik="0001051627", days=365000)
        self.assertEqual([item.form_type for item in filings], ["4", "144", "8-K", "S-3", "424B5"])
        self.assertTrue(filings[0].filing_url.endswith("/f4.xml"))

    def test_form4_sale_is_high_priority(self) -> None:
        filing = _filing("4")
        source = _source("4")
        xml = """
        <ownershipDocument>
          <reportingOwner><reportingOwnerId><rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId></reportingOwner>
          <nonDerivativeTable>
            <nonDerivativeTransaction>
              <transactionDate><value>2026-06-17</value></transactionDate>
              <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
              <transactionAmounts>
                <transactionShares><value>1200</value></transactionShares>
                <transactionPricePerShare><value>12.50</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
              </transactionAmounts>
            </nonDerivativeTransaction>
          </nonDerivativeTable>
        </ownershipDocument>
        """
        events = parse_form4(xml, filing=filing, source=source)
        self.assertEqual(events[0].event_type, "form_4_insider_transaction")
        self.assertEqual(events[0].priority, "high")
        self.assertEqual(events[0].event_date, "2026-06-17")
        self.assertEqual(events[0].source_facts[0]["total_shares"], 1200)

    def test_form4_grant_is_medium_priority_with_uncertainty(self) -> None:
        filing = _filing("4")
        source = _source("4")
        xml = """
        <ownershipDocument>
          <nonDerivativeTable>
            <nonDerivativeTransaction>
              <transactionDate><value>2026-06-17</value></transactionDate>
              <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
              <transactionAmounts>
                <transactionShares><value>500</value></transactionShares>
                <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
              </transactionAmounts>
            </nonDerivativeTransaction>
          </nonDerivativeTable>
        </ownershipDocument>
        """
        events = parse_form4(xml, filing=filing, source=source)
        self.assertEqual(events[0].priority, "medium")
        self.assertTrue(events[0].uncertainties)

    def test_form144_extracts_sale_notice_fields(self) -> None:
        filing = _filing("144")
        source = _source("144")
        xml = """
        <edgarSubmission>
          <nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>Jane Doe</nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>
          <securitiesToBeSoldShares>2500</securitiesToBeSoldShares>
          <noticeDate>2026-06-08</noticeDate>
          <aggregateMarketValue>100000</aggregateMarketValue>
        </edgarSubmission>
        """
        events = parse_form144(xml, filing=filing, source=source)
        self.assertEqual(events[0].event_type, "form_144_sale_notice")
        self.assertEqual(events[0].priority, "high")
        self.assertEqual(events[0].source_facts[0]["seller"], "Jane Doe")
        self.assertEqual(events[0].source_facts[0]["shares"], 2500)

    def test_renderer_distinguishes_scan_statuses(self) -> None:
        ok = EventScanResult.from_events(scope="portfolio", market="US", symbol=None, events=[], errors=[])
        self.assertIn("今日无高优先级持仓事件", render_scan_result(ok))

        failed = EventScanResult.from_events(
            scope="portfolio",
            market="US",
            symbol=None,
            events=[],
            errors=[ScanError(market="US", symbol="AXTI", stage="sec_submissions", message="boom")],
        )
        rendered_failed = render_scan_result(failed)
        self.assertIn("今日未完成事件扫描", rendered_failed)
        self.assertNotIn("今日无高优先级持仓事件", rendered_failed)

    def test_repository_persist_packet_links_source_id(self) -> None:
        try:
            from investment_knowledge_mcp.events import repository as event_repository
        except ModuleNotFoundError as exc:
            if exc.name == "psycopg":
                self.skipTest("psycopg is not installed in this Python environment")
            raise
        packet = EventPacket(
            market="US",
            symbol="AXTI",
            event_type="material_8k",
            event_title="AXTI 8-K 重大事项候选",
            event_date="2026-06-20",
            priority="medium",
            confidence="medium",
            source=_source("8-K"),
        )
        with (
            patch.object(event_repository, "upsert_event_source", return_value={"id": 7}) as source,
            patch.object(event_repository, "upsert_portfolio_event", return_value={"id": 11}) as event,
        ):
            self.assertEqual(event_repository.persist_event_packet(packet), {"id": 11})
        source.assert_called_once()
        event.assert_called_once_with(packet, source_ids=[7])

    def test_render_muted_event(self) -> None:
        message = render_muted_event(
            {"event": {"symbol": "AXTI", "event_title": "AXTI Form 144 拟出售披露"}},
            symbol="AXTI",
        )
        self.assertIn("已不再主动提醒", message)


def _filing(form_type: str) -> SecFiling:
    return SecFiling(
        market="US",
        symbol="AXTI",
        cik="0001051627",
        company_name="AXT Inc.",
        form_type=form_type,
        accession_number="0000000000-26-000001",
        filing_date="2026-06-20",
        report_date=None,
        primary_document="doc.xml",
        filing_url="https://www.sec.gov/Archives/edgar/data/1051627/000000000026000001/doc.xml",
    )


def _source(form_type: str) -> EventSource:
    return EventSource(
        source_type="sec_filing",
        publisher="SEC",
        url="https://www.sec.gov/Archives/edgar/data/1051627/000000000026000001/doc.xml",
        form_type=form_type,
        accession_number="0000000000-26-000001",
        market="US",
        symbol="AXTI",
    )


if __name__ == "__main__":
    unittest.main()
