from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import inspect
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from investment_knowledge_mcp import command_router
from investment_knowledge_mcp.command_workbench import parse_workbench_command
from investment_knowledge_mcp.data_sources.contracts import SourceCapability
from investment_knowledge_mcp.data_sources.pool import DataSourcePool, MemoryResultCache
from investment_knowledge_mcp.data_sources.valuation import (
    ValuationDataSourcePool,
    ValuationFactsSource,
)
from investment_knowledge_mcp.research.models import ResearchBundle, SourceDocument

from investment_knowledge_mcp.stock_valuation import (
    CORE_FRAMES,
    SPECIALIST_FRAMES,
    build_valuation_artifact,
    build_valuation_artifact_evidence,
    load_latest_valuation_artifact,
    render_valuation_card,
    render_valuation_methods,
    valuation_method_library,
)
from investment_knowledge_mcp.valuation_data_provider import (
    _fetch_valuation_snapshot,
    _official_attempt_loader,
    _official_document_matches,
    default_valuation_pool,
    fetch_valuation_snapshot,
    normalize_valuation_target,
)


class StockValuationTests(unittest.TestCase):
    def _context(self) -> dict[str, object]:
        return {
            "stock": {
                "id": 7,
                "symbol": "ACME",
                "market": "US",
                "name": "Acme Semiconductor",
                "core_business": "Cyclical semiconductor business with growth optionality.",
                "stock_character": "Cyclical growth.",
            },
            "stock_knowledge": [],
            "stock_insights": [{"confirmed_by_user": True, "content": "Track cash flow and cycle."}],
            "sources": [{"id": "sec:ACME", "source_type": "sec_companyfacts"}],
        }

    def _snapshot(self) -> dict[str, object]:
        return {
            "facts": [
                {"metric": "revenue", "value": 1000.0, "source_id": "sec:revenue", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "gross_profit", "value": 450.0, "source_id": "sec:gross", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "operating_income", "value": 200.0, "source_id": "sec:op", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "net_income", "value": -50.0, "source_id": "sec:income", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "operating_cash_flow", "value": 250.0, "source_id": "sec:ocf", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "capex", "value": 100.0, "source_id": "sec:capex", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "cash", "value": 75.0, "source_id": "sec:cash", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "debt", "value": 275.0, "source_id": "sec:debt", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "price", "value": 10.0, "source_id": "quote:price", "source_type": "market_snapshot", "currency": "USD", "timestamp": "2026-07-19T00:00:00+00:00"},
                {"metric": "shares_outstanding", "value": 100.0, "source_id": "quote:shares", "source_type": "market_snapshot", "currency": "USD"},
                {"metric": "ebitda", "value": 300.0, "source_id": "sec:ebitda", "source_type": "sec_companyfacts", "currency": "USD"},
            ],
            "sources": [{"id": "sec:ACME", "source_type": "sec_companyfacts"}],
            "errors": ["Authorization: secret https://provider.example/error"],
            "target_resolution": {"normalized_target": "US.ACME", "provider_market_ticker": "ACME", "currency": "USD"},
            "market_snapshot_status": "present",
            "financial_fact_status": "present",
        }

    def _build(self, context: dict[str, object] | None = None, snapshot: dict[str, object] | None = None) -> dict[str, object]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        packet, _ = build_valuation_artifact(
            context or self._context(),
            symbol="ACME",
            market="US",
            output_dir=Path(temporary.name),
            command="valuation US.ACME",
            provider_snapshot=snapshot or self._snapshot(),
            now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
        )
        return packet

    def _provider_pool(
        self,
        loaders: dict[str, tuple[SourceCapability, str, str, object]],
        *,
        cache: MemoryResultCache | None = None,
    ) -> ValuationDataSourcePool:
        pool = ValuationDataSourcePool(cache=cache, now=lambda: datetime(2026, 7, 19, tzinfo=timezone.utc))
        for source_id, (capability, source_type, provider, loader) in loaders.items():
            pool.register(ValuationFactsSource(
                source_id,
                capability,
                source_type,
                provider,
                loader,
            ))
        return pool

    def test_valuation_provider_public_signatures_and_target_normalization(self) -> None:
        self.assertEqual(
            list(inspect.signature(normalize_valuation_target).parameters),
            ["symbol", "market", "company_name"],
        )
        self.assertEqual(
            list(inspect.signature(fetch_valuation_snapshot).parameters),
            ["symbol", "market", "company_name"],
        )
        cases = (
            (("US.INTC", "US", None), ("US.INTC", "INTC", "USD")),
            (("KR.000660", "KR", None), ("KR.000660", "000660.KS", "KRW")),
            (("000660 KR", "KR", None), ("KR.000660", "000660.KS", "KRW")),
            (("HK.01888", "HK", None), ("HK.01888", "1888.HK", "HKD")),
            (("1888 HK", "HK", None), ("HK.01888", "1888.HK", "HKD")),
            (("建滔积层板", "HK", None), ("HK.01888", "1888.HK", "HKD")),
            (("建滔積層板", "HK", None), ("HK.01888", "1888.HK", "HKD")),
            (("Kingboard Laminates", "HK", None), ("HK.01888", "1888.HK", "HKD")),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                target = normalize_valuation_target(*arguments)
                self.assertEqual(target["normalized_target"], expected[0])
                self.assertEqual(target["provider_market_ticker"], expected[1])
                self.assertEqual(target["currency"], expected[2])
        known = normalize_valuation_target("INTC", "US", "Spoofed name")
        generic = normalize_valuation_target("AAPL", "US", "  Apple   Inc.  ")
        self.assertEqual(known["company_name"], "Intel Corporation")
        self.assertEqual(generic["company_name"], "Apple Inc.")

    def test_default_kr_pool_runs_distinct_regulator_and_configured_company_ir_probes(self) -> None:
        calls: list[str] = []

        class Response:
            text = "no structured financial facts"

            def raise_for_status(self) -> None:
                return None

        class Client:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def get(self, url: str, **kwargs):
                del kwargs
                calls.append(url)
                return Response()

        target = normalize_valuation_target("KR.000660", "KR")
        pool = default_valuation_pool(
            target,
            http_client_factory=lambda timeout: Client(),
            market_loader=lambda symbol, market: [{
                "metric": "price", "value": 250_000.0, "currency": "KRW",
                "timestamp": "2026-07-19T00:00:00Z",
            }],
        )

        snapshot = _fetch_valuation_snapshot(target, pool)

        self.assertEqual(len([url for url in calls if url.startswith("https://dart.fss.or.kr/")]), 1)
        self.assertEqual(len([url for url in calls if url.startswith("https://englishdart.fss.or.kr/")]), 1)
        self.assertEqual(len([url for url in calls if "skhynix.com" in url]), 1)
        self.assertEqual(
            [attempt["status"] for attempt in snapshot["source_attempts"][:4]],
            ["complete_missing", "complete_missing", "complete_missing", "not_attempted"],
        )
        self.assertNotIn("http", json.dumps(snapshot).lower())

    def test_generic_kr_target_does_not_call_unconfigured_company_or_vendor_source(self) -> None:
        calls: list[str] = []

        class Response:
            text = "empty search"

            def raise_for_status(self) -> None:
                return None

        class Client:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def get(self, url: str, **kwargs):
                del kwargs
                calls.append(url)
                return Response()

        target = normalize_valuation_target("005930", "KR", "Samsung Electronics")
        pool = default_valuation_pool(
            target,
            http_client_factory=lambda timeout: Client(),
            market_loader=lambda symbol, market: [],
        )

        snapshot = _fetch_valuation_snapshot(target, pool)

        self.assertFalse(any("skhynix.com" in url for url in calls))
        statuses = {attempt["source_type"]: attempt["status"] for attempt in snapshot["source_attempts"]}
        self.assertEqual(statuses["company_ir"], "not_attempted")
        self.assertEqual(statuses["vendor_financial"], "not_attempted")

    def test_official_document_categories_cannot_be_cross_labeled(self) -> None:
        hkex_report = SourceDocument(
            key="hkex_annual_report_2025",
            source_type="annual_report",
            title="Annual Report 2025",
            publisher="HKEXnews",
        )
        hkex_result = SourceDocument(
            key="hkex_annual_results_2025",
            source_type="annual_results",
            title="Annual Results 2025",
            publisher="HKEXnews",
        )
        company_report = SourceDocument(
            key="issuer_ir_annual_report_2025",
            source_type="annual_report",
            title="Annual Report 2025",
            publisher="Kingboard Laminates",
        )
        company_ir = SourceDocument(
            key="company_ir_homepage",
            source_type="company_ir",
            title="Investor Relations",
            publisher="Kingboard Laminates",
        )
        sec_report = SourceDocument(
            key="sec_10k_2025",
            source_type="annual_report",
            title="Form 10-K",
            publisher="SEC",
        )

        self.assertTrue(_official_document_matches("hkex_filing", hkex_report))
        self.assertFalse(_official_document_matches("hkexnews", hkex_report))
        self.assertFalse(_official_document_matches("company_report", hkex_report))
        self.assertTrue(_official_document_matches("hkexnews", hkex_result))
        self.assertFalse(_official_document_matches("hkex_filing", hkex_result))
        self.assertTrue(_official_document_matches("company_report", company_report))
        self.assertFalse(_official_document_matches("company_ir", company_report))
        self.assertTrue(_official_document_matches("company_ir", company_ir))
        self.assertFalse(_official_document_matches("company_report", company_ir))
        self.assertTrue(_official_document_matches("sec_filing", sec_report))
        self.assertFalse(_official_document_matches("company_report", sec_report))

    def test_bounded_caller_and_known_company_name_reach_official_collector(self) -> None:
        calls: list[tuple[str, str, str | None]] = []

        class Provider:
            def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
                calls.append((symbol, market, company_name))
                return ResearchBundle(symbol=symbol, market=market, company_name=company_name)

        for target in (
            normalize_valuation_target("AAPL", "US", "  Apple   Inc.  "),
            normalize_valuation_target("INTC", "US", "Spoofed name"),
        ):
            loader = _official_attempt_loader(
                Provider(),
                "sec_filing",
                company_name=str(target["company_name"]),
            )
            loader(str(target["normalized_symbol"]), str(target["normalized_market"]))

        self.assertEqual(calls, [
            ("AAPL", "US", "Apple Inc."),
            ("INTC", "US", "Intel Corporation"),
        ])

    def test_attempt_statuses_and_task1_projection_are_truthful_and_sanitized(self) -> None:
        pool = ValuationDataSourcePool(now=lambda: datetime(2026, 7, 19, tzinfo=timezone.utc))
        pool.register(ValuationFactsSource(
            "dart_filing", SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "dart_filing", "dart",
            lambda symbol, market: {"facts": [], "attempt_status": "complete_missing"},
        ))

        def failed(symbol: str, market: str) -> object:
            raise RuntimeError("Authorization: Bearer secret https://private.example/raw")

        pool.register(ValuationFactsSource(
            "fss_filing", SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "fss_filing", "fss", failed,
        ))
        pool.register(ValuationFactsSource(
            "yahoo", SourceCapability.MARKET_SNAPSHOT,
            "market_snapshot", "yahoo",
            lambda symbol, market: [{
                "metric": "price", "value": 250_000.0, "currency": "KRW",
                "timestamp": "2026-07-19T00:00:00Z",
            }],
        ))
        target = normalize_valuation_target("005930", "KR", "Samsung Electronics")

        snapshot = _fetch_valuation_snapshot(target, pool)

        self.assertEqual(
            [(attempt["source_type"], attempt["status"]) for attempt in snapshot["source_attempts"][:4]],
            [
                ("dart_filing", "complete_missing"),
                ("fss_filing", "failed"),
                ("company_ir", "not_attempted"),
                ("vendor_financial", "not_attempted"),
            ],
        )
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                {"stock": {"symbol": "005930", "market": "KR"}},
                symbol="005930", market="KR", output_dir=Path(temporary),
                command="valuation KR.005930", provider_snapshot=snapshot,
                now=datetime(2026, 7, 19, tzinfo=timezone.utc),
            )
        evidence = build_valuation_artifact_evidence(packet)
        attempts = evidence["source_coverage"]["source_attempts"]
        self.assertEqual(
            [attempt["status"] for attempt in attempts[:4]],
            ["complete_missing", "failed", "not_attempted", "not_attempted"],
        )
        serialized = json.dumps({"snapshot": snapshot, "evidence": evidence}).lower()
        for unsafe in ("authorization", "bearer", "secret", "private.example", "http://", "https://"):
            self.assertNotIn(unsafe, serialized)

    def test_dart_hkex_and_company_ir_facts_count_as_official_in_stored_and_public_coverage(self) -> None:
        cases = (
            ("KR", "000660", "dart_filing", "KRW"),
            ("HK", "01888", "hkexnews", "HKD"),
            ("HK", "01888", "company_ir", "HKD"),
        )
        for market, symbol, source_type, currency in cases:
            snapshot = {
                "facts": [
                    {
                        "metric": "revenue", "value": 100.0, "source_type": source_type,
                        "currency": currency, "period_end": "2025-12-31",
                        "freshness": "latest_filing",
                    },
                    {
                        "metric": "price", "value": 10.0, "source_type": "market_snapshot",
                        "currency": currency, "timestamp": "2026-07-19T00:00:00+00:00",
                        "freshness": "latest_market_session",
                    },
                ],
                "target_resolution": {"normalized_target": f"{market}.{symbol}", "currency": currency},
                "financial_fact_status": "present",
                "market_snapshot_status": "present",
            }
            with self.subTest(source_type=source_type), tempfile.TemporaryDirectory() as temporary:
                packet, _ = build_valuation_artifact(
                    {"stock": {"symbol": symbol, "market": market, "core_business": "Cyclical business."}},
                    symbol=symbol, market=market, output_dir=Path(temporary),
                    command=f"valuation {market}.{symbol}", provider_snapshot=snapshot,
                    now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
                )
                evidence = build_valuation_artifact_evidence(packet)
                for artifact in (packet, evidence):
                    coverage = artifact["source_coverage"]
                    self.assertEqual(coverage.get("official_source_count"), 1)
                    self.assertNotIn("official_financial_facts", coverage.get("missing_categories", []))
                    self.assertNotIn("missing_official_source", artifact["degraded_state"]["reason_codes"])

    def test_us_snapshot_uses_sec_facts_and_shared_yahoo_market_source(self) -> None:
        calls: list[tuple[str, str]] = []

        def sec(symbol: str, market: str) -> list[dict[str, object]]:
            calls.append(("sec_companyfacts", symbol))
            return [{
                "metric": "revenue", "value": 52_600_000_000,
                "currency": "USD", "period_end": "2025-12-31",
            }]

        def yahoo(symbol: str, market: str) -> list[dict[str, object]]:
            calls.append(("yahoo", symbol))
            return [{
                "metric": "price", "value": 31.5, "currency": "USD",
                "timestamp": "2026-07-19T00:00:00+00:00",
            }]

        pool = self._provider_pool({
            "sec_companyfacts": (SourceCapability.OFFICIAL_FINANCIAL_FACTS, "sec_companyfacts", "sec", sec),
            "yahoo": (SourceCapability.MARKET_SNAPSHOT, "market_snapshot", "yahoo", yahoo),
        })
        with patch("investment_knowledge_mcp.valuation_data_provider.default_valuation_pool", return_value=pool):
            snapshot = fetch_valuation_snapshot("US.INTC", "US")

        self.assertEqual(calls, [("sec_companyfacts", "INTC"), ("yahoo", "INTC")])
        self.assertEqual(snapshot["financial_fact_status"], "partial")
        self.assertEqual(snapshot["market_snapshot_status"], "partial")
        self.assertEqual(
            {(fact["metric"], fact["source_type"], fact["provider"]) for fact in snapshot["facts"]},
            {("revenue", "sec_companyfacts", "sec"), ("price", "market_snapshot", "yahoo")},
        )
        self.assertEqual(
            {fact.get("freshness") for fact in snapshot["facts"]},
            {"latest_filing", "latest_market_session"},
        )
        fetched_times = [datetime.fromisoformat(str(fact.get("fetched_at"))) for fact in snapshot["facts"]]
        self.assertTrue(all(value.tzinfo is not None and value.utcoffset() is not None for value in fetched_times))
        self.assertNotIn("errors", snapshot)

    def test_kr_snapshot_attempts_dart_fss_company_ir_then_distinct_vendor(self) -> None:
        calls: list[str] = []

        def missing(source_id: str):
            def loader(symbol: str, market: str) -> list[dict[str, object]]:
                calls.append(source_id)
                return []
            return loader

        def vendor(symbol: str, market: str) -> list[dict[str, object]]:
            calls.append("vendor_financial")
            return [{"metric": "revenue", "value": 10.0, "currency": "KRW", "period_end": "2025-12-31"}]

        def yahoo(symbol: str, market: str) -> list[dict[str, object]]:
            calls.append("yahoo")
            return [{"metric": "price", "value": 250_000.0, "currency": "KRW", "timestamp": "2026-07-19T00:00:00Z"}]

        pool = self._provider_pool({
            "dart_filing": (SourceCapability.OFFICIAL_FINANCIAL_FACTS, "dart_filing", "dart", missing("dart_filing")),
            "fss_filing": (SourceCapability.OFFICIAL_FINANCIAL_FACTS, "fss_filing", "fss", missing("fss_filing")),
            "company_ir": (SourceCapability.OFFICIAL_FINANCIAL_FACTS, "company_ir", "company_ir", missing("company_ir")),
            "vendor_financial": (SourceCapability.OFFICIAL_FINANCIAL_FACTS, "vendor_financial", "vendor", vendor),
            "yahoo": (SourceCapability.MARKET_SNAPSHOT, "market_snapshot", "yahoo", yahoo),
        })
        with patch("investment_knowledge_mcp.valuation_data_provider.default_valuation_pool", return_value=pool):
            snapshot = fetch_valuation_snapshot("000660 KR", "KR")

        self.assertEqual(calls, ["dart_filing", "fss_filing", "company_ir", "vendor_financial", "yahoo"])
        self.assertEqual(
            [attempt["source_type"] for attempt in snapshot["source_attempts"][:4]],
            ["dart_filing", "fss_filing", "company_ir", "vendor_financial"],
        )
        revenue = next(fact for fact in snapshot["facts"] if fact["metric"] == "revenue")
        self.assertEqual(revenue["source_type"], "vendor_financial")
        self.assertEqual(revenue["provider"], "vendor")
        self.assertNotIn("official", json.dumps(revenue).lower())

        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                {"stock": {"symbol": "000660", "market": "KR"}},
                symbol="000660",
                market="KR",
                output_dir=Path(temporary),
                command="valuation KR.000660",
                provider_snapshot=snapshot,
                now=datetime(2026, 7, 19, tzinfo=timezone.utc),
            )
        registry = packet["source_coverage"]["source_registry"]
        self.assertIn("vendor_financial", {source["source_type"] for source in registry})
        self.assertIn("market_snapshot", {source["source_type"] for source in registry})

    def test_hk_alias_snapshot_attempts_hkexnews_then_company_report(self) -> None:
        calls: list[str] = []

        def hkex(symbol: str, market: str) -> list[dict[str, object]]:
            calls.append("hkexnews")
            return []

        def company_report(symbol: str, market: str) -> list[dict[str, object]]:
            calls.append("company_report")
            return [{"metric": "revenue", "value": 20.0, "currency": "HKD", "period_end": "2025-12-31"}]

        def yahoo(symbol: str, market: str) -> list[dict[str, object]]:
            calls.append("yahoo")
            return [{"metric": "price", "value": 8.8, "currency": "HKD", "timestamp": "2026-07-19T00:00:00Z"}]

        pool = self._provider_pool({
            "hkexnews": (SourceCapability.OFFICIAL_FINANCIAL_FACTS, "hkexnews", "hkex", hkex),
            "company_report": (SourceCapability.OFFICIAL_FINANCIAL_FACTS, "company_report", "official_research", company_report),
            "yahoo": (SourceCapability.MARKET_SNAPSHOT, "market_snapshot", "yahoo", yahoo),
        })
        with patch("investment_knowledge_mcp.valuation_data_provider.default_valuation_pool", return_value=pool):
            snapshot = fetch_valuation_snapshot("Kingboard Laminates Holdings Limited", "HK")

        self.assertEqual(calls, ["hkexnews", "company_report", "yahoo"])
        self.assertEqual(snapshot["target_resolution"]["normalized_target"], "HK.01888")
        revenue = next(fact for fact in snapshot["facts"] if fact["metric"] == "revenue")
        self.assertEqual((revenue["source_type"], revenue["provider"]), ("company_report", "official_research"))

    def test_one_hk_snapshot_collects_one_official_bundle_for_all_categories(self) -> None:
        calls = 0

        class Provider:
            def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
                nonlocal calls
                calls += 1
                return ResearchBundle(
                    symbol=symbol,
                    market=market,
                    company_name=company_name,
                    sources=[
                        SourceDocument(
                            key="hkex_annual_results_2025", source_type="annual_results",
                            title="Annual Results", publisher="HKEXnews",
                        ),
                        SourceDocument(
                            key="issuer_ir_annual_report_2025", source_type="annual_report",
                            title="Annual Report", publisher="Kingboard Laminates",
                        ),
                    ],
                )

        target = normalize_valuation_target("01888", "HK")
        pool = default_valuation_pool(
            target,
            official_provider=Provider(),
            market_loader=lambda symbol, market: [],
        )

        snapshot = _fetch_valuation_snapshot(target, pool)

        self.assertEqual(calls, 1)
        self.assertEqual(
            [item["source_type"] for item in snapshot["source_attempts"][:3]],
            ["hkexnews", "hkex_filing", "company_report"],
        )

    def test_empty_hk_official_discovery_is_cached_across_pool_fetches(self) -> None:
        calls = 0

        class Provider:
            def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
                nonlocal calls
                calls += 1
                return ResearchBundle(symbol=symbol, market=market, company_name=company_name)

        target = normalize_valuation_target("01888", "HK")
        pool = default_valuation_pool(
            target,
            official_provider=Provider(),
            market_loader=lambda symbol, market: [],
        )

        first = _fetch_valuation_snapshot(target, pool)
        second = _fetch_valuation_snapshot(target, pool)

        self.assertEqual(first["facts"], [])
        self.assertEqual(second["facts"], [])
        self.assertEqual(calls, 1)

    def test_slow_hk_official_provider_returns_safe_degradation_within_total_budget(self) -> None:
        from investment_knowledge_mcp import valuation_data_provider

        self.assertIn("official_budget_seconds", inspect.signature(default_valuation_pool).parameters)
        declared_budget = getattr(valuation_data_provider, "VALUATION_OFFICIAL_PROVIDER_TOTAL_BUDGET_SECONDS", None)
        self.assertIsInstance(declared_budget, float)

        calls = 0

        class SlowProvider:
            def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
                nonlocal calls
                calls += 1
                time.sleep(0.25)
                return ResearchBundle(symbol=symbol, market=market, company_name=company_name)

        target = normalize_valuation_target("01888", "HK")
        pool = default_valuation_pool(
            target,
            official_provider=SlowProvider(),
            official_budget_seconds=0.02,
            market_loader=lambda symbol, market: [],
        )

        started = time.monotonic()
        snapshot = _fetch_valuation_snapshot(target, pool)
        elapsed = time.monotonic() - started

        self.assertLess(declared_budget, 15.0)
        self.assertLess(elapsed, 0.15)
        self.assertEqual(calls, 1)
        self.assertEqual(snapshot["financial_fact_status"], "unavailable")
        self.assertTrue(all(item["status"] == "complete_missing" for item in snapshot["source_attempts"][:3]))
        serialized = json.dumps(snapshot).lower()
        for unsafe in ("timeout", "exception", "traceback", "thread", "http://", "https://"):
            self.assertNotIn(unsafe, serialized)

    def test_cache_miss_attempts_every_source_before_safe_degradation(self) -> None:
        calls: list[str] = []

        def missing(source_id: str):
            def loader(symbol: str, market: str) -> list[dict[str, object]]:
                calls.append(source_id)
                return []
            return loader

        pool = self._provider_pool({
            "dart_filing": (SourceCapability.OFFICIAL_FINANCIAL_FACTS, "dart_filing", "dart", missing("dart_filing")),
            "fss_filing": (SourceCapability.OFFICIAL_FINANCIAL_FACTS, "fss_filing", "fss", missing("fss_filing")),
            "company_ir": (SourceCapability.OFFICIAL_FINANCIAL_FACTS, "company_ir", "company_ir", missing("company_ir")),
            "vendor_financial": (SourceCapability.OFFICIAL_FINANCIAL_FACTS, "vendor_financial", "vendor", missing("vendor_financial")),
            "yahoo": (SourceCapability.MARKET_SNAPSHOT, "market_snapshot", "yahoo", missing("yahoo")),
        }, cache=MemoryResultCache(clock=lambda: 0.0))
        with patch("investment_knowledge_mcp.valuation_data_provider.default_valuation_pool", return_value=pool):
            snapshot = fetch_valuation_snapshot("KR.000660", "KR")

        self.assertEqual(calls, ["dart_filing", "fss_filing", "company_ir", "vendor_financial", "yahoo"])
        self.assertEqual(snapshot["facts"], [])
        self.assertEqual(snapshot["financial_fact_status"], "unavailable")
        self.assertEqual(snapshot["market_snapshot_status"], "unavailable")
        serialized = json.dumps(snapshot).lower()
        for unsafe in ("authorization", "bearer", "token=", "http://", "https://"):
            self.assertNotIn(unsafe, serialized)

    def _assert_public_refs_resolve(self, public: dict[str, object]) -> None:
        facts = public.get("facts")
        self.assertIsInstance(facts, list)
        fact_ids = {item["id"] for item in facts if isinstance(item, dict)}
        source_coverage = public.get("source_coverage")
        self.assertIsInstance(source_coverage, dict)
        registry = source_coverage.get("source_registry")
        self.assertIsInstance(registry, list)
        source_ids = {item["id"] for item in registry if isinstance(item, dict)}
        for fact in facts:
            self.assertIn(fact["source_id"], source_ids)
        stock = public.get("stock") if isinstance(public.get("stock"), dict) else {}
        signals = stock.get("scoring_signals") if isinstance(stock.get("scoring_signals"), dict) else {}
        packet_refs = {f"packet:method_library:{item['id']}" for item in CORE_FRAMES}
        packet_refs.update(
            f"packet:stock:scoring_signals:{field}:{frame_id}"
            for field, frame_ids in signals.items() if isinstance(frame_ids, list)
            for frame_id in frame_ids
        )
        def assert_refs(records: object) -> None:
            self.assertIsInstance(records, list)
            for record in records:
                for reference in record.get("input_refs", []):
                    self.assertTrue(reference in fact_ids or reference in packet_refs, reference)
        for section in ("deterministic_calculations", "internal_frame_scores", "selected_frames"):
            assert_refs(public.get(section))
        bridge = public.get("market_implied_bridge")
        self.assertIsInstance(bridge, dict)
        assert_refs(bridge.get("bridge_lines"))
        assert_refs(bridge.get("frame_fit_ranking"))

    def _assert_finite_json_tree(self, value: object) -> None:
        if isinstance(value, float):
            self.assertTrue(math.isfinite(value), value)
        elif isinstance(value, dict):
            for item in value.values():
                self._assert_finite_json_tree(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self._assert_finite_json_tree(item)
        elif isinstance(value, str):
            self.assertNotRegex(value.lower(), r"(?:^|[^a-z])(inf|nan)(?:[^a-z]|$)")

    def test_public_interfaces_and_eight_method_definitions(self) -> None:
        for function in (
            build_valuation_artifact,
            load_latest_valuation_artifact,
            build_valuation_artifact_evidence,
            render_valuation_card,
            render_valuation_methods,
        ):
            self.assertTrue(callable(function))
        self.assertEqual(len(CORE_FRAMES), 5)
        self.assertEqual(len(SPECIALIST_FRAMES), 3)
        methods = valuation_method_library()
        self.assertEqual(len(methods), 8)
        self.assertEqual(
            [item["name"] for item in methods],
            [
                "Free Cash Flow", "Comparable Multiples", "SOTP / Asset Value", "Cyclical",
                "Growth / Scenario", "Dividend", "Residual Income / ROE-PB", "Event-Driven",
            ],
        )
        self.assertEqual(list(inspect.signature(load_latest_valuation_artifact).parameters), ["symbol", "market", "output_dir"])

    def test_complete_packet_preserves_freshness_and_renders_frame_semantics(self) -> None:
        snapshot = self._snapshot()
        snapshot["source_attempts"] = [
            {"family": "official_financial", "status": "available"},
            {"family": "market_snapshot", "status": "available"},
        ]
        for fact in snapshot["facts"]:
            if fact["source_type"] == "market_snapshot":
                fact.update({
                    "freshness": "latest_market_session",
                    "fetched_at": "2026-07-19T00:05:00+00:00",
                })
            else:
                fact.update({
                    "period_end": "2025-12-31",
                    "freshness": "latest_filing",
                    "fetched_at": "2026-07-18T00:05:00+00:00",
                })

        packet = self._build(snapshot=snapshot)
        evidence = build_valuation_artifact_evidence(packet)
        card = render_valuation_card(packet)

        price = next(item for item in evidence["facts"] if item["metric"] == "price")
        self.assertEqual(price["timestamp"], "2026-07-19T00:00:00+00:00")
        self.assertEqual(price.get("fetched_at"), "2026-07-19T00:05:00+00:00")
        self.assertEqual(price.get("freshness"), "latest_market_session")
        coverage = evidence["source_coverage"]
        self.assertEqual(coverage.get("financials_as_of"), "2025-12-31")
        self.assertEqual(coverage.get("market_data_as_of"), "2026-07-19T00:00:00+00:00")
        self.assertEqual(coverage.get("stale_fields"), [])
        self.assertEqual(coverage.get("attempted_source_families"), ["market_snapshot", "official_financial"])
        self.assertEqual(coverage.get("missing_categories"), [])
        self.assertEqual(evidence["degraded_state"].get("source_state"), "complete")

        for frame in evidence["selected_frames"]:
            self.assertGreater(len(frame["assumptions"]), 0)
            self.assertGreater(len(frame["rerating_triggers"]), 0)
            self.assertGreater(len(frame["failure_conditions"]), 0)
            self.assertIn(frame["confidence"], {"low", "medium"})
            self.assertEqual(frame["provenance"]["type"], "deterministic_rule")
            self.assertEqual(frame["provenance"]["rule_id"], "stock_valuation_frame_score.v1")
        self.assertEqual(
            evidence["interpretation"]["provenance"],
            {"type": "deterministic_rule", "rule_id": "stock_valuation_frame_selection.v1"},
        )
        self.assertEqual(
            evidence["interpretation"]["optional_narrative"],
            {"status": "unavailable", "provenance": "model_unavailable"},
        )
        self.assertGreater(len(evidence["market_implied_bridge"]["bridge_lines"]), 0)
        for expected in (
            "Market-implied bridge:", "P/S: 1.0x anchors current market value.",
            "Financials as of: 2025-12-31", "Market data as of: 2026-07-19T00:00:00+00:00",
            "Rerating triggers:", "Failure conditions:", "Rule provenance: stock_valuation_frame_score.v1",
            "Optional narrative: unavailable (model unavailable)",
        ):
            self.assertIn(expected, card)

    def test_year_2000_market_observation_is_derived_as_stale_and_visible(self) -> None:
        snapshot = self._snapshot()
        snapshot["source_attempts"] = [
            {"family": "official_financial", "status": "available"},
            {"family": "market_snapshot", "status": "available"},
        ]
        for fact in snapshot["facts"]:
            if fact["source_type"] == "market_snapshot":
                fact.update({
                    "timestamp": "2000-01-03T00:00:00+00:00",
                    "freshness": "latest_market_session",
                    "fetched_at": "2026-07-19T00:05:00+00:00",
                })
            else:
                fact["period_end"] = "2025-12-31"

        packet = self._build(snapshot=snapshot)
        evidence = build_valuation_artifact_evidence(packet)
        card = render_valuation_card(packet)

        self.assertEqual(evidence["source_coverage"].get("market_data_as_of"), "2000-01-03T00:00:00+00:00")
        self.assertEqual(evidence["source_coverage"].get("stale_fields"), ["price", "shares_outstanding"])
        self.assertEqual(evidence["source_coverage"]["market_snapshot_status"], "stale")
        self.assertEqual(evidence["degraded_state"].get("source_state"), "stale")
        self.assertIn("Stale fields: price, shares_outstanding", card)
        comparable = next(
            item for item in evidence["market_implied_bridge"]["frame_fit_ranking"]
            if item["id"] == "comparable_multiples"
        )
        self.assertEqual(comparable["confidence"], "low")

    def test_financial_missing_state_names_attempted_families_and_recovery(self) -> None:
        snapshot = {
            "facts": [{
                "metric": "price", "value": 10.0, "source_type": "market_snapshot",
                "currency": "USD", "timestamp": "2026-07-19T00:00:00+00:00",
                "freshness": "latest_market_session", "fetched_at": "2026-07-19T00:05:00+00:00",
            }],
            "target_resolution": {"normalized_target": "US.ACME", "currency": "USD"},
            "market_snapshot_status": "present",
            "financial_fact_status": "unavailable",
            "source_attempts": [
                {"family": "regulator_filing", "status": "complete_missing"},
                {"family": "company_ir", "status": "complete_missing"},
                {"family": "market_snapshot", "status": "available"},
            ],
        }

        evidence = build_valuation_artifact_evidence(self._build(snapshot=snapshot))
        card = render_valuation_card(self._build(snapshot=snapshot))

        self.assertEqual(evidence["degraded_state"].get("source_state"), "financial_missing")
        self.assertEqual(evidence["source_coverage"].get("missing_categories"), ["official_financial_facts"])
        self.assertEqual(
            evidence["source_coverage"]["attempted_source_families"],
            ["company_ir", "market_snapshot", "regulator_filing"],
        )
        self.assertIn("Recovery: official financial facts are missing", card)
        self.assertIn("Attempted source families: company_ir, market_snapshot, regulator_filing", card)

    def test_market_missing_state_suppresses_bridge_and_names_recovery(self) -> None:
        snapshot = self._snapshot()
        snapshot["facts"] = [fact for fact in snapshot["facts"] if fact["source_type"] != "market_snapshot"]
        for fact in snapshot["facts"]:
            fact.update({"period_end": "2025-12-31", "freshness": "latest_filing"})
        snapshot.update({
            "market_snapshot_status": "unavailable",
            "financial_fact_status": "present",
            "source_attempts": [
                {"family": "official_financial", "status": "available"},
                {"family": "market_snapshot", "status": "complete_missing"},
            ],
        })

        evidence = build_valuation_artifact_evidence(self._build(snapshot=snapshot))
        card = render_valuation_card(self._build(snapshot=snapshot))

        self.assertEqual(evidence["degraded_state"].get("source_state"), "market_missing")
        self.assertEqual(evidence["source_coverage"].get("missing_categories"), ["market_data"])
        self.assertEqual(evidence["market_implied_bridge"]["bridge_lines"], [])
        self.assertIn("Recovery: current market data is missing", card)
        self.assertNotIn("P/S:", card)

    def test_both_missing_state_is_recovery_oriented_without_fabricated_semantics(self) -> None:
        snapshot = {
            "facts": [],
            "target_resolution": {"normalized_target": "US.ACME", "currency": "USD"},
            "market_snapshot_status": "unavailable",
            "financial_fact_status": "unavailable",
            "source_attempts": [
                {"family": "official_financial", "status": "complete_missing"},
                {"family": "company_ir", "status": "complete_missing"},
                {"family": "market_snapshot", "status": "complete_missing"},
            ],
        }

        evidence = build_valuation_artifact_evidence(self._build(snapshot=snapshot))
        card = render_valuation_card(self._build(snapshot=snapshot))

        self.assertEqual(evidence["degraded_state"].get("source_state"), "both_missing")
        self.assertEqual(
            evidence["source_coverage"]["missing_categories"],
            ["market_data", "official_financial_facts"],
        )
        self.assertEqual(evidence["market_implied_bridge"]["bridge_lines"], [])
        self.assertIn("Recovery: official financial facts and current market data are missing", card)
        self.assertIn("Missing categories: market_data, official_financial_facts", card)

    def test_builds_deterministic_packet_with_all_metrics_and_fact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, path = build_valuation_artifact(
                self._context(), symbol="acme", market="us", output_dir=Path(temporary), command="valuation US.ACME",
                provider_snapshot=self._snapshot(), now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
            )
            self.assertTrue(path.name.startswith("ACME_US_valuation_20260719T010203Z"))
            self.assertTrue((Path(temporary) / "valuation" / "ACME_US_valuation_latest.json").exists())
            self.assertEqual(packet["schema"], "stock_valuation_packet.v1")
            self.assertEqual(set(packet), {
                "schema", "input", "stock", "target_resolution", "facts", "assumptions", "deterministic_calculations",
                "internal_frame_scores", "selected_frames", "market_implied_bridge", "interpretation", "watch_items",
                "source_coverage", "degraded_state", "safety",
            })
            self.assertEqual(len(packet["internal_frame_scores"]), 5)
            self.assertGreaterEqual(len(packet["selected_frames"]), 1)
            self.assertLessEqual(len(packet["selected_frames"]), 3)
            self.assertTrue(set(item["id"] for item in packet["selected_frames"]).issubset({item["id"] for item in CORE_FRAMES}))
            facts = {item["metric"]: item for item in packet["facts"]}
            self.assertEqual(facts["revenue"]["value"], 1000.0)
            self.assertIn("display_value", facts["revenue"])
            self.assertRegex(facts["revenue"]["source_id"], r"^source:[0-9a-f]{16}$")
            calculations = {item["metric"]: item for item in packet["deterministic_calculations"]}
            for metric in ("free_cash_flow", "net_debt", "market_cap", "enterprise_value", "gross_margin", "operating_margin", "fcf_margin", "pe", "ps", "ev_ebitda", "ev_fcf"):
                self.assertIn(metric, calculations)
                self.assertIsInstance(calculations[metric]["input_refs"], tuple)
            self.assertEqual(calculations["free_cash_flow"]["value"], 150.0)
            self.assertEqual(calculations["net_debt"]["value"], 200.0)
            self.assertEqual(calculations["market_cap"]["value"], 1000.0)
            self.assertEqual(calculations["enterprise_value"]["value"], 1200.0)
            self.assertFalse(calculations["pe"]["meaningful"])
            self.assertEqual(calculations["pe"]["raw_value"], -20.0)
            self.assertIn("negative earnings", calculations["pe"]["display_value"])
            self.assertFalse(calculations["ev_fcf"]["meaningful"] is False)
            self.assertEqual(load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=Path(temporary))["schema"], "stock_valuation_packet.v1")

    def test_evidence_is_an_allow_list_without_paths_or_provider_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=self._snapshot(),
            )
        evidence = build_valuation_artifact_evidence(packet)
        serialized = json.dumps(evidence).lower()
        self.assertIn("display_value", serialized)
        self.assertIn("meaningful", serialized)
        self.assertEqual(evidence["source_coverage"]["market_snapshot_status"], "present")
        self.assertEqual(evidence["source_coverage"]["financial_fact_status"], "present")
        for unsafe in ("artifact_path", "authorization", "secret", "provider.example", "exception", "traceback"):
            self.assertNotIn(unsafe, serialized)
        with self.assertRaises((TypeError, ValueError)):
            build_valuation_artifact_evidence(Path("../../etc/passwd"))  # type: ignore[arg-type]
        card = render_valuation_card(packet)
        self.assertIn("no formal user insight was written", card)
        self.assertNotIn("provider.example", card)

    def test_evidence_recursively_projects_hostile_provider_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=self._snapshot(),
            )
        coverage = packet["source_coverage"]
        assert isinstance(coverage, dict)
        coverage["provider_statuses"] = {
            "market_snapshot": {
                "status": "available",
                "headers": {"Authorization": "Bearer provider-secret"},
                "exception": "provider exception detail",
                "endpoint": "https://provider.example/diagnostic",
                "configuration": {"api_key": "configuration-secret"},
                "diagnostics": {"nested": {"raw": "nested-provider-diagnostic"}},
            },
        }
        coverage["source_attempts"] = {
            "official_financial": {
                "family": "official_financial",
                "status": "unavailable",
                "headers": {"X-Api-Key": "attempt-secret"},
                "exception_text": "attempt exception detail",
                "endpoint_url": "https://attempt.example/raw",
                "configuration": {"token": "attempt-configuration"},
                "diagnostics": {"raw": "attempt-diagnostic"},
            },
        }

        evidence = build_valuation_artifact_evidence(packet)
        serialized = json.dumps(evidence).lower()

        self.assertEqual(
            evidence["source_coverage"]["provider_statuses"],
            {"market_snapshot": {"status": "available"}},
        )
        self.assertEqual(
            evidence["source_coverage"]["source_attempts"],
            [{"family": "official_financial", "status": "unavailable"}],
        )
        for unsafe in (
            "authorization", "provider-secret", "exception detail", "provider.example",
            "configuration-secret", "nested-provider-diagnostic", "attempt-secret",
            "attempt.example", "attempt-configuration", "attempt-diagnostic",
        ):
            self.assertNotIn(unsafe, serialized)

    def test_evidence_preserves_safe_stale_source_status(self) -> None:
        snapshot = self._snapshot()
        snapshot["market_snapshot_status"] = "stale"
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=snapshot,
            )
        evidence = build_valuation_artifact_evidence(packet)
        self.assertEqual(evidence["source_coverage"]["market_snapshot_status"], "stale")

    def test_derived_calculations_flatten_all_upstream_fact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=self._snapshot(),
            )
        calculations = {item["metric"]: item for item in packet["deterministic_calculations"]}
        self.assertEqual(
            calculations["free_cash_flow"]["input_refs"],
            ("fact:operating_cash_flow", "fact:capex"),
        )
        self.assertEqual(
            calculations["fcf_margin"]["input_refs"],
            ("fact:operating_cash_flow", "fact:capex", "fact:revenue"),
        )
        self.assertEqual(
            calculations["ev_fcf"]["input_refs"],
            (
                "fact:price", "fact:shares_outstanding",
                "fact:debt", "fact:cash",
                "fact:operating_cash_flow", "fact:capex",
            ),
        )

    def test_evidence_projects_every_branch_through_typed_safe_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=self._snapshot(),
            )
        hostile = json.loads(json.dumps(packet))
        hostile["target_resolution"].update({
            "company_name": "Bearer evidence-secret",
            "endpoint": "https://evil.example/target",
        })
        hostile["stock"].update({
            "name": "Authorization: evidence-secret",
            "path": "/private/stock",
        })
        hostile["facts"].append({
            "id": {"headers": "evidence-secret"}, "metric": "revenue", "value": {"raw": 1},
            "display_value": ["https://evil.example/fact"], "source_id": "Bearer evidence-secret",
            "provider": "https://evil.example/provider",
        })
        hostile["deterministic_calculations"].append({
            "metric": "ps", "value": {"raw": 1}, "raw_value": [1],
            "display_value": "https://evil.example/calculation", "formula": {"config": "evidence-secret"},
            "inputs": [{"metric": "revenue"}], "input_refs": [{"traceback": "evidence-secret"}],
        })
        hostile["market_implied_bridge"]["bridge_lines"].append({
            "type": {"header": "evidence-secret"}, "display": "https://evil.example/bridge",
            "input_refs": ["/private/bridge"],
        })
        hostile["market_implied_bridge"]["frame_fit_ranking"].append({
            "id": "fcf", "name": "https://evil.example/frame", "score": {"raw": 1},
            "fit_to_current_market_value": ["fits"], "why_it_fits_or_not": "Bearer evidence-secret",
            "main_data_gaps": [{"exception": "evidence-secret"}], "confidence": {"raw": "medium"},
        })
        hostile["source_coverage"].update({
            "fact_count": {"raw": 1}, "market_snapshot_status": "https://evil.example/status",
            "provider_statuses": {"market_snapshot": {"status": "Bearer evidence-secret"}},
            "source_attempts": {"secret": {"family": "https://evil.example/family", "status": "Bearer evidence-secret"}},
        })
        hostile["degraded_state"] = {
            "degraded": "yes", "reasons": ["safe gap", {"path": "/private/gap"}],
            "data_gaps": ["https://evil.example/gap", "safe data gap", "../relative/path"],
        }
        hostile["safety"] = {
            "direct_investment_advice": "yes", "writes_formal_user_insight": {"raw": True},
            "research_aid_only": True,
        }
        hostile["input"] = {
            "symbol": "ACME", "market": "US", "created_at": ["evidence-secret"],
            "endpoint": "https://evil.example/input",
        }

        evidence = build_valuation_artifact_evidence(hostile)
        serialized = json.dumps(evidence).lower()

        revenue = next(item for item in evidence["facts"] if item.get("id") == "fact:revenue")
        self.assertEqual(revenue["value"], 1000.0)
        self.assertEqual(revenue["display_value"], "$1.0K")
        self.assertEqual(evidence["target"]["currency"], "USD")
        self.assertNotIn("safe gap", json.dumps(evidence["degraded_state"]))
        self.assertNotIn("safe data gap", json.dumps(evidence["degraded_state"]))
        self.assertEqual(evidence["safety"]["research_aid_only"], True)
        self.assertFalse(evidence["safety"]["direct_investment_advice"])
        for unsafe in ("evil.example", "evidence-secret", "authorization", "bearer", "private/", "relative/path", "traceback", "headers", "config"):
            self.assertNotIn(unsafe, serialized)

    def test_bridge_lines_and_frame_scores_have_bounded_input_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=self._snapshot(),
            )
        bridge_lines = {item["type"]: item for item in packet["market_implied_bridge"]["bridge_lines"]}
        self.assertEqual(
            bridge_lines["sales_anchor"]["input_refs"],
            ("fact:price", "fact:shares_outstanding", "fact:revenue"),
        )
        self.assertEqual(
            bridge_lines["ev_sales_anchor"]["input_refs"],
            (
                "fact:price", "fact:shares_outstanding",
                "fact:debt", "fact:cash", "fact:revenue",
            ),
        )
        self.assertEqual(
            bridge_lines["fcf_yield"]["input_refs"],
            (
                "fact:operating_cash_flow", "fact:capex",
                "fact:price", "fact:shares_outstanding",
            ),
        )
        scores = {item["id"]: item for item in packet["internal_frame_scores"]}
        self.assertEqual(
            scores["fcf"]["input_refs"],
            ("packet:method_library:fcf", "fact:operating_cash_flow", "fact:capex"),
        )
        self.assertIn("packet:stock:scoring_signals:core_business:cyclical", scores["cyclical"]["input_refs"])
        self.assertNotIn("Cyclical semiconductor business", json.dumps(packet["internal_frame_scores"]))

    def test_negative_fcf_multiples_are_explicitly_not_meaningful(self) -> None:
        snapshot = self._snapshot()
        facts = snapshot["facts"]
        assert isinstance(facts, list)
        for fact in facts:
            if fact["metric"] == "operating_cash_flow":
                fact["value"] = 50.0
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=snapshot,
            )
        calculations = {item["metric"]: item for item in packet["deterministic_calculations"]}
        for metric in ("fcf_yield", "ev_fcf"):
            self.assertFalse(calculations[metric]["meaningful"])
            self.assertIsNotNone(calculations[metric]["raw_value"])
            self.assertIn("negative FCF", calculations[metric]["display_value"])

    def test_path_like_targets_are_rejected_without_file_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                build_valuation_artifact(
                    {}, symbol="../../etc/passwd", market="US", output_dir=Path(temporary), command="valuation ../../etc/passwd",
                )
            with self.assertRaises(ValueError):
                load_latest_valuation_artifact(symbol="../../etc/passwd", market="US", output_dir=Path(temporary))

    def test_missing_data_degrades_explicitly_without_fabricating_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                {"stock": {"symbol": "EMPTY", "market": "US"}}, symbol="EMPTY", market="US", output_dir=Path(temporary), command="valuation US.EMPTY",
            )
        self.assertTrue(packet["degraded_state"]["degraded"])
        self.assertEqual(packet["facts"], [])
        self.assertIn("missing_revenue", packet["degraded_state"]["reason_codes"])
        self.assertFalse(packet["safety"]["writes_formal_user_insight"])

    def test_explicit_target_identity_cannot_be_overridden_by_context_or_snapshot(self) -> None:
        context = self._context()
        context["stock"] = {
            "id": 7,
            "symbol": "EVIL",
            "market": "HK",
            "name": "Wrong identity",
            "core_business": "Semiconductor manufacturing.",
            "stock_character": "Cyclical.",
        }
        snapshot = self._snapshot()
        snapshot["target_resolution"] = {
            "normalized_target": "KR.000660",
            "normalized_symbol": "000660",
            "normalized_market": "KR",
            "provider_market_ticker": "../wrong/path",
            "company_name": "Wrong identity",
            "currency": "USD",
        }

        packet = self._build(context, snapshot)

        self.assertEqual(packet["input"]["symbol"], "ACME")
        self.assertEqual(packet["input"]["market"], "US")
        self.assertEqual(packet["stock"]["symbol"], "ACME")
        self.assertEqual(packet["stock"]["market"], "US")
        self.assertEqual(packet["target_resolution"]["normalized_target"], "US.ACME")
        self.assertEqual(packet["target_resolution"]["normalized_symbol"], "ACME")
        self.assertEqual(packet["target_resolution"]["normalized_market"], "US")
        self.assertNotIn("provider_market_ticker", packet["target_resolution"])
        self.assertNotIn("EVIL", json.dumps(packet))
        self.assertNotIn("000660", json.dumps(packet))

        invalid_context = self._context()
        invalid_context["stock"]["symbol"] = "../wrong-stock"
        invalid_snapshot = self._snapshot()
        invalid_snapshot["target_resolution"] = {"normalized_target": "https://evil.example/wrong"}
        invalid = self._build(invalid_context, invalid_snapshot)
        self.assertEqual(invalid["facts"], [])
        self.assertNotIn("core_business", invalid["stock"])
        self.assertIn("context_identity_mismatch", invalid["degraded_state"]["reason_codes"])
        self.assertIn("snapshot_identity_mismatch", invalid["degraded_state"]["reason_codes"])

    def test_every_supplied_snapshot_identity_field_must_be_valid_and_consistent(self) -> None:
        identity_cases = (
            ("ACME", "US", "HK.EVIL"), ("EVIL", "US", "US.ACME"), ("ACME", "HK", "US.ACME"),
            (["ACME"], "US", "US.ACME"), ("ACME", ["US"], "US.ACME"), ("ACME", "US", ["US.ACME"]),
        )
        for normalized_symbol, normalized_market, normalized_target in identity_cases:
            snapshot = self._snapshot()
            snapshot["target_resolution"] = {"normalized_symbol": normalized_symbol, "normalized_market": normalized_market, "normalized_target": normalized_target}
            with self.subTest(identity=snapshot["target_resolution"]):
                packet = self._build(snapshot=snapshot)
                self.assertEqual(packet["facts"], [])
                self.assertIn("snapshot_identity_mismatch", packet["degraded_state"]["reason_codes"])

        matching = self._snapshot()
        matching["target_resolution"] = {
            "normalized_symbol": "ACME", "normalized_market": "US", "normalized_target": "US.ACME",
        }
        self.assertGreater(len(self._build(snapshot=matching)["facts"]), 0)

    def test_untrusted_ingress_is_normalized_before_packet_persistence(self) -> None:
        context = self._context()
        context["command_context"] = {
            "private_key": "PRIVATE-KEY-SENTINEL",
            "endpoint": "https://evil.example/context",
            "local_path": "../context/private.json",
        }
        context["stock"]["core_business"] = "Semiconductor notes in reports/private.json"
        context["stock_insights"].append({"content": "Bearer RAW-CONTEXT-SENTINEL"})
        snapshot = self._snapshot()
        snapshot["errors"] = ["PRIVATE-KEY-SENTINEL https://evil.example/provider"]
        snapshot["source_attempts"] = {
            "bad": {
                "family": "official_financial",
                "status": "failed",
                "diagnostic": "../provider/debug.log",
            },
        }
        snapshot["sources"] = [{
            "id": "https://evil.example/source/PRIVATE-KEY-SENTINEL",
            "source_type": "sec_companyfacts",
            "local_path": "reports/source.json",
        }]
        snapshot["facts"][0]["provider"] = "https://evil.example/PRIVATE-KEY-SENTINEL"

        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                context,
                symbol="ACME",
                market="US",
                output_dir=Path(temporary),
                command="valuation US.ACME --token PRIVATE-KEY-SENTINEL ../command.txt",
                provider_snapshot=snapshot,
                now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
            )
        persisted = json.dumps(packet, allow_nan=False)

        for unsafe in (
            "PRIVATE-KEY-SENTINEL", "RAW-CONTEXT-SENTINEL", "evil.example",
            "../context", "../provider", "reports/source.json", "reports/private.json",
        ):
            self.assertNotIn(unsafe, persisted)
        self.assertEqual(packet["input"]["command"], "valuation US.ACME")
        self.assertGreater(len(packet["facts"]), 0)

    def test_bool_nan_inf_and_numeric_strings_are_rejected_before_calculation(self) -> None:
        snapshot = self._snapshot()
        snapshot["facts"] = [
            {"metric": "revenue", "value": "1000", "source_id": "raw-revenue", "source_type": "sec_companyfacts"},
            {"metric": "net_income", "value": True, "source_id": "raw-income", "source_type": "sec_companyfacts"},
            {"metric": "ebitda", "value": float("nan"), "source_id": "raw-ebitda", "source_type": "sec_companyfacts"},
            {"metric": "debt", "value": float("inf"), "source_id": "raw-debt", "source_type": "sec_companyfacts"},
            {"metric": "price", "value": 10, "source_id": "raw-price", "source_type": "market_snapshot", "currency": "USD"},
            {"metric": "shares_outstanding", "value": 100, "source_id": "raw-shares", "source_type": "market_snapshot"},
        ]

        packet = self._build(snapshot=snapshot)

        fact_metrics = {fact["metric"] for fact in packet["facts"]}
        self.assertEqual(fact_metrics, {"price", "shares_outstanding"})
        calculations = {item["metric"]: item for item in packet["deterministic_calculations"]}
        self.assertIn("market_cap", calculations)
        for metric in ("ps", "pe", "ev_ebitda", "enterprise_value"):
            self.assertNotIn(metric, calculations)
        json.dumps(packet, allow_nan=False)

    def test_single_utc_timestamp_drives_packet_and_filename(self) -> None:
        supplied = datetime(2026, 7, 19, 9, 2, 3, 987654, tzinfo=timezone(timedelta(hours=8)))
        with tempfile.TemporaryDirectory() as temporary:
            packet, path = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary),
                command="valuation US.ACME", provider_snapshot=self._snapshot(), now=supplied,
            )
            self.assertEqual(packet["input"]["created_at"], "2026-07-19T01:02:03+00:00")
            self.assertEqual(path.name, "ACME_US_valuation_20260719T010203Z.json")

    def test_persistence_uses_validated_atomic_writes_instead_of_path_write_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(Path, "write_text", side_effect=AssertionError("direct write_text is forbidden")):
                try:
                    packet, path = build_valuation_artifact(
                        self._context(), symbol="ACME", market="US", output_dir=Path(temporary),
                        command="valuation US.ACME", provider_snapshot=self._snapshot(),
                        now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
                    )
                except AssertionError as exc:
                    self.fail(str(exc))

            expected = json.loads(json.dumps(packet))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)
            latest = Path(temporary) / "valuation" / "ACME_US_valuation_latest.json"
            self.assertEqual(json.loads(latest.read_text(encoding="utf-8")), expected)
            self.assertEqual(list(latest.parent.glob("*.tmp")), [])

    def test_same_stock_same_second_collision_has_one_winner_and_one_explicit_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            barrier = threading.Barrier(2)
            instant = datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc)

            def build(core_business: str) -> tuple[str, dict[str, object] | None]:
                context = self._context()
                context["stock"]["core_business"] = core_business
                barrier.wait()
                try:
                    packet, _ = build_valuation_artifact(
                        context, symbol="ACME", market="US", output_dir=output_dir,
                        command="valuation US.ACME", provider_snapshot=self._snapshot(), now=instant,
                    )
                except FileExistsError:
                    return "collision", None
                return "ok", packet

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(build, ("Cyclical semiconductor business.", "AI growth platform.")))

            self.assertEqual(sorted(status for status, _ in results), ["collision", "ok"])
            winner = next(packet for status, packet in results if status == "ok")
            self.assertIsNotNone(winner)
            latest = load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=output_dir)
            self.assertEqual(latest, json.loads(json.dumps(winner)))
            self.assertEqual(list((output_dir / "valuation").glob("*.tmp")), [])

    def test_interrupted_latest_replace_keeps_previous_latest_valid_and_cleans_temps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            previous, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=output_dir,
                command="valuation US.ACME", provider_snapshot=self._snapshot(),
                now=datetime(2026, 7, 19, 1, 2, 2, tzinfo=timezone.utc),
            )
            real_replace = os.replace
            replace_count = 0

            def interrupt_second_replace(source: object, destination: object) -> None:
                nonlocal replace_count
                replace_count += 1
                if replace_count == 2:
                    raise OSError("simulated replace interruption")
                real_replace(source, destination)

            with patch("os.replace", side_effect=interrupt_second_replace):
                with self.assertRaises(OSError):
                    build_valuation_artifact(
                        self._context(), symbol="ACME", market="US", output_dir=output_dir,
                        command="valuation US.ACME", provider_snapshot=self._snapshot(),
                        now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
                    )

            self.assertEqual(
                load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=output_dir),
                json.loads(json.dumps(previous)),
            )
            interrupted_timestamp = output_dir / "valuation" / "ACME_US_valuation_20260719T010203Z.json"
            self.assertEqual(json.loads(interrupted_timestamp.read_text(encoding="utf-8"))["schema"], "stock_valuation_packet.v1")
            self.assertEqual(list((output_dir / "valuation").glob("*.tmp")), [])
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                build_valuation_artifact(
                    self._context(), symbol="ACME", market="US", output_dir=Path(temporary),
                    command="valuation US.ACME", provider_snapshot=self._snapshot(),
                    now=datetime(2026, 7, 19, 1, 2, 3),
                )

    def test_fact_and_source_ids_are_stable_opaque_and_all_refs_resolve(self) -> None:
        first_snapshot = self._snapshot()
        second_snapshot = self._snapshot()
        for index, fact in enumerate(first_snapshot["facts"]):
            fact["source_id"] = f"Bearer secret/{index}"
        for index, fact in enumerate(second_snapshot["facts"]):
            fact["source_id"] = f"https://evil.example/raw/{index}"

        first = self._build(snapshot=first_snapshot)
        second = self._build(snapshot=second_snapshot)
        first_facts = {item["metric"]: item for item in first["facts"]}
        second_facts = {item["metric"]: item for item in second["facts"]}

        self.assertEqual(
            {metric: item["id"] for metric, item in first_facts.items()},
            {metric: item["id"] for metric, item in second_facts.items()},
        )
        self.assertEqual(
            {metric: item["source_id"] for metric, item in first_facts.items()},
            {metric: item["source_id"] for metric, item in second_facts.items()},
        )
        for fact in first_facts.values():
            self.assertRegex(fact["id"], r"^fact:[a-z_]+$")
            self.assertRegex(fact["source_id"], r"^source:[0-9a-f]{16}$")
        self._assert_public_refs_resolve(build_valuation_artifact_evidence(first))

    def test_evidence_preserves_resolvable_provenance_for_hostile_raw_source_ids(self) -> None:
        snapshot = self._snapshot()
        for index, fact in enumerate(snapshot["facts"]):
            fact["source_id"] = f"../private/{index}/Bearer-PROVENANCE-SENTINEL"

        evidence = build_valuation_artifact_evidence(self._build(snapshot=snapshot))
        serialized = json.dumps(evidence)

        self._assert_public_refs_resolve(evidence)
        self.assertIn("source_registry", evidence["source_coverage"])
        self.assertNotIn("PROVENANCE-SENTINEL", serialized)
        self.assertNotIn("../private", serialized)

    def test_scoring_reads_only_declared_stock_fields_and_cites_exact_field(self) -> None:
        context = self._context()
        context["stock"]["core_business"] = "A cyclical memory manufacturer."
        context["stock"]["stock_character"] = "Established cash generator."
        context["untrusted_notes"] = "growth TAM asset holding segment AI"

        packet = self._build(context=context)
        scores = {item["id"]: item for item in packet["internal_frame_scores"]}

        self.assertIn("packet:stock:scoring_signals:core_business:cyclical", scores["cyclical"]["input_refs"])
        self.assertNotIn("packet:stock:scoring_signals:stock_character:cyclical", scores["cyclical"]["input_refs"])
        for frame in ("growth_scenario", "sotp_asset_value"):
            self.assertFalse(any(ref.startswith("packet:stock:") for ref in scores[frame]["input_refs"]))

    def test_card_and_evidence_share_the_same_safe_public_projection(self) -> None:
        packet = self._build()
        calculation = next(item for item in packet["deterministic_calculations"] if item["metric"] == "ps")
        calculation["display_value"] = "https://evil.example/PRIVATE-CARD-SENTINEL"
        packet["stock"]["name"] = "Bearer PRIVATE-CARD-SENTINEL"

        evidence = build_valuation_artifact_evidence(packet)
        card = render_valuation_card(packet)
        projected_ps = next(item for item in evidence["deterministic_calculations"] if item["metric"] == "ps")

        self.assertEqual(projected_ps["display_value"], "1.0x")
        self.assertIn("P/S: 1.0x", card)
        self.assertNotIn("PRIVATE-CARD-SENTINEL", json.dumps(evidence))
        self.assertNotIn("PRIVATE-CARD-SENTINEL", card)
        self.assertNotIn("evil.example", card)
        self.assertNotIn("Cyclical semiconductor business with growth optionality", json.dumps(evidence))
        self.assertNotIn("Cyclical semiconductor business with growth optionality", card)

    def test_public_projection_preserves_assumptions_interpretation_watch_and_degraded_sections(self) -> None:
        context = self._context()
        context["valuation_cases"] = [{
            "schema": "stock_valuation_case.v1",
            "symbol": "ACME",
            "market": "US",
            "confirmed_by_user": True,
        }]
        packet = self._build(context=context)

        evidence = build_valuation_artifact_evidence(packet)
        card = render_valuation_card(packet)

        for key in ("assumptions", "interpretation", "watch_items", "degraded_state", "selected_frames", "internal_frame_scores"):
            self.assertIn(key, evidence)
        self.assertEqual(evidence["assumptions"]["user_confirmed_valuation_case"], True)
        self.assertGreater(len(evidence["interpretation"]), 0)
        self.assertGreater(len(evidence["watch_items"]), 0)
        for heading in ("Assumptions:", "Interpretation:", "Watch items:", "Data gaps:"):
            self.assertIn(heading, card)

    def test_latest_loader_rejects_nonfinite_or_unresolved_packet_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=output_dir,
                command="valuation US.ACME", provider_snapshot=self._snapshot(),
                now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
            )
            latest = output_dir / "valuation" / "ACME_US_valuation_latest.json"
            unsafe_number = json.loads(json.dumps(packet))
            unsafe_number["facts"][0]["value"] = float("nan")
            latest.write_text(json.dumps(unsafe_number), encoding="utf-8")
            self.assertIsNone(load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=output_dir))

            unresolved = json.loads(json.dumps(packet))
            unresolved["deterministic_calculations"][0]["input_refs"] = ["fact:not_emitted"]
            latest.write_text(json.dumps(unresolved), encoding="utf-8")
            self.assertIsNone(load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=output_dir))

            unsafe = json.loads(json.dumps(packet))
            unsafe["facts"][0]["provider_explanation"] = "https://evil.example/../raw-diagnostic"
            latest.write_text(json.dumps(unsafe), encoding="utf-8")
            self.assertIsNone(load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=output_dir))

    def test_untrusted_source_and_degradation_tokens_are_canonicalized(self) -> None:
        context = self._context()
        context["stock"]["name"] = "reports.json"
        context["stock"]["core_business"] = "Cyclical diagnostic prose status 403"
        context["sources"] = [{"source_type": "status_403"}]
        snapshot = self._snapshot()
        snapshot["sources"] = [{"source_type": "status_403"}]
        for fact in snapshot["facts"]:
            fact["source_type"] = "status_403"
            fact["provider"] = "reports.json"
        snapshot["target_resolution"]["mapping_source"] = "diagnostic"
        snapshot["target_resolution"]["company_name"] = "api_key"

        packet = self._build(context, snapshot)
        persisted = json.dumps(packet)
        registry = packet["source_coverage"]["source_registry"]

        self.assertTrue(registry)
        self.assertTrue(all(source["source_type"] == "unknown" for source in registry))
        self.assertTrue(all("provider" not in source for source in registry))
        self.assertNotIn("mapping_source", packet["target_resolution"])
        self.assertNotIn("name", packet["stock"])
        self.assertNotIn("core_business", packet["stock"])
        self.assertIn("cyclical", packet["stock"]["scoring_signals"]["core_business"])
        for hostile in ("PRIVATE-KEY-SENTINEL", "api_key", "reports.json", "diagnostic prose", "status 403", "status_403"):
            self.assertNotIn(hostile, persisted)

        hostile_packet = json.loads(json.dumps(packet))
        hostile_packet["degraded_state"] = {
            "degraded": True,
            "reason_codes": ["PRIVATE-KEY-SENTINEL", "api_key", "reports.json"],
            "gap_codes": ["diagnostic prose status 403"],
        }
        evidence = build_valuation_artifact_evidence(hostile_packet)
        public_text = json.dumps(evidence) + render_valuation_card(hostile_packet)
        for hostile in ("PRIVATE-KEY-SENTINEL", "api_key", "reports.json", "diagnostic prose", "status 403"):
            self.assertNotIn(hostile, public_text)

    def test_loader_recomputes_canonical_packet_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=output_dir,
                command="valuation US.ACME", provider_snapshot=self._snapshot(),
                now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
            )
            latest = output_dir / "valuation" / "ACME_US_valuation_latest.json"
            mutations: dict[str, dict[str, object]] = {}

            forged_source = json.loads(json.dumps(packet))
            original_source = forged_source["source_coverage"]["source_registry"][0]["id"]
            forged_source["source_coverage"]["source_registry"][0]["id"] = "source:0000000000000000"
            for fact in forged_source["facts"]:
                if fact["source_id"] == original_source:
                    fact["source_id"] = "source:0000000000000000"
            mutations["forged source id"] = forged_source

            altered_calculation = json.loads(json.dumps(packet))
            ps = next(item for item in altered_calculation["deterministic_calculations"] if item["metric"] == "ps")
            ps["value"] = 999.0
            ps["display_value"] = "999.0x"
            mutations["altered calculation"] = altered_calculation

            missing_ref = json.loads(json.dumps(packet))
            ps = next(item for item in missing_ref["deterministic_calculations"] if item["metric"] == "ps")
            ps["input_refs"].remove("fact:revenue")
            mutations["missing calculation ancestry"] = missing_ref

            dropped_calculation = json.loads(json.dumps(packet))
            dropped_calculation["deterministic_calculations"] = [
                item for item in dropped_calculation["deterministic_calculations"] if item["metric"] != "ps"
            ]
            dropped_calculation["market_implied_bridge"]["bridge_lines"] = [
                item for item in dropped_calculation["market_implied_bridge"]["bridge_lines"] if item["type"] != "sales_anchor"
            ]
            mutations["dropped calculation"] = dropped_calculation

            missing_score = json.loads(json.dumps(packet))
            missing_score["internal_frame_scores"] = [
                item for item in missing_score["internal_frame_scores"] if item["id"] != "sotp_asset_value"
            ]
            mutations["missing core score"] = missing_score

            inconsistent_selected = json.loads(json.dumps(packet))
            inconsistent_selected["selected_frames"] = [
                inconsistent_selected["market_implied_bridge"]["frame_fit_ranking"][-1]
            ]
            mutations["inconsistent selected frame"] = inconsistent_selected

            four_selected = json.loads(json.dumps(packet))
            four_selected["selected_frames"] = four_selected["market_implied_bridge"]["frame_fit_ranking"][:4]
            mutations["four selected frames"] = four_selected

            for label, mutation in mutations.items():
                with self.subTest(label=label):
                    latest.write_text(json.dumps(mutation), encoding="utf-8")
                    self.assertIsNone(load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=output_dir))

    def test_public_projection_uses_canonical_identity_and_static_safety(self) -> None:
        packet = self._build()
        packet["stock"]["symbol"] = "EVIL"
        packet["stock"]["market"] = "HK"
        packet["target_resolution"].update({
            "normalized_symbol": "000660",
            "normalized_market": "KR",
            "normalized_target": "KR.000660",
            "input_target": "KR.000660",
        })
        packet["safety"] = {
            "direct_investment_advice": True,
            "writes_formal_user_insight": True,
            "research_aid_only": False,
        }

        evidence = build_valuation_artifact_evidence(packet)
        card = render_valuation_card(packet)

        self.assertEqual(evidence["stock"]["symbol"], "ACME")
        self.assertEqual(evidence["stock"]["market"], "US")
        self.assertEqual(evidence["target"]["normalized_target"], "US.ACME")
        self.assertEqual(evidence["target"]["normalized_symbol"], "ACME")
        self.assertEqual(evidence["target"]["normalized_market"], "US")
        self.assertEqual(evidence["safety"], {
            "direct_investment_advice": False,
            "writes_formal_user_insight": False,
            "research_aid_only": True,
            "omits_local_path": True,
            "provider_error_detail_omitted": True,
        })
        self.assertIn("US.ACME", card)
        for hostile in ("EVIL", "HK.EVIL", "KR.000660"):
            self.assertNotIn(hostile, json.dumps(evidence) + card)

    def test_public_projection_drops_foreign_branches_instead_of_relabeling_them(self) -> None:
        snapshot = self._snapshot()
        snapshot["facts"][0]["provider"] = "OfficialResearchProvider"
        snapshot["target_resolution"]["mapping_source"] = "provider"
        packet = json.loads(json.dumps(self._build(snapshot=snapshot)))
        packet["stock"].update({
            "symbol": "EVIL", "market": "HK", "profile_present": True,
            "scoring_signals": {"core_business": ["growth_scenario"]},
        })
        packet["target_resolution"].update({
            "input_target": "HK.EVIL", "normalized_target": "HK.EVIL",
            "normalized_symbol": "EVIL", "normalized_market": "HK",
        })

        evidence = build_valuation_artifact_evidence(packet)
        card = render_valuation_card(packet)
        serialized = json.dumps(evidence) + card

        self.assertEqual(evidence["stock"], {"symbol": "ACME", "market": "US"})
        self.assertEqual(evidence["target"]["normalized_target"], "US.ACME")
        self.assertNotIn("mapping_category", evidence["target"])
        self.assertEqual(evidence["facts"], [])
        self.assertEqual(evidence["source_coverage"]["source_registry"], [])
        self.assertEqual(evidence["source_coverage"]["provider_statuses"], {})
        self.assertEqual(evidence["source_coverage"]["source_attempts"], [])
        self.assertIn("context_identity_mismatch", evidence["degraded_state"]["reason_codes"])
        self.assertIn("snapshot_identity_mismatch", evidence["degraded_state"]["reason_codes"])
        for foreign in ("HK.EVIL", "EVIL", "official_research", "generic_provider"):
            self.assertNotIn(foreign, serialized)

    def test_public_projection_drops_foreign_confirmation_on_stock_mismatch(self) -> None:
        context = self._context()
        context["valuation_cases"] = [{
            "schema": "stock_valuation_case.v1",
            "symbol": "ACME",
            "market": "US",
            "confirmed_by_user": True,
        }]
        packet = json.loads(json.dumps(self._build(context=context)))
        self.assertTrue(packet["assumptions"]["user_confirmed_valuation_case"])
        packet["stock"].update({"symbol": "EVIL", "market": "HK"})

        evidence = build_valuation_artifact_evidence(packet)

        self.assertFalse(evidence["assumptions"]["user_confirmed_valuation_case"])
        self.assertNotIn("missing_confirmed_case", evidence["degraded_state"]["reason_codes"])

    def test_unrelated_confirmed_stock_records_do_not_confirm_a_valuation_case(self) -> None:
        context = self._context()
        context["stock_insights"] = [{"confirmed_by_user": True, "content": "Unrelated confirmed note."}]
        context["stock_knowledge"] = [{"confirmed_by_user": True, "content": "Unrelated confirmed fact."}]

        evidence = build_valuation_artifact_evidence(self._build(context=context))

        self.assertFalse(evidence["assumptions"]["user_confirmed_valuation_case"])
        self.assertNotIn("missing_confirmed_case", evidence["degraded_state"]["reason_codes"])
        self.assertNotIn("missing_confirmed_case", evidence["degraded_state"]["gap_codes"])

    def test_only_exact_typed_target_matched_valuation_case_can_be_confirmed(self) -> None:
        cases = (
            ({"schema": "stock_valuation_case.v1", "symbol": "ACME", "market": "US", "confirmed_by_user": True}, True),
            ({"schema": "stock_valuation_case.v0", "symbol": "ACME", "market": "US", "confirmed_by_user": True}, False),
            ({"schema": "stock_valuation_case.v1", "symbol": "OTHER", "market": "US", "confirmed_by_user": True}, False),
            ({"schema": "stock_valuation_case.v1", "symbol": "ACME", "market": "HK", "confirmed_by_user": True}, False),
            ({"schema": "stock_valuation_case.v1", "symbol": "ACME", "market": "US", "confirmed_by_user": False}, False),
        )
        for valuation_case, expected in cases:
            context = {
                "stock": {"symbol": "ACME", "market": "US"},
                "valuation_cases": [valuation_case],
                "stock_insights": [],
                "stock_knowledge": [],
            }
            with self.subTest(valuation_case=valuation_case):
                evidence = build_valuation_artifact_evidence(self._build(context=context))
                self.assertEqual(evidence["assumptions"]["user_confirmed_valuation_case"], expected)
                self.assertNotIn("missing_confirmed_case", evidence["degraded_state"]["gap_codes"])

    def test_public_projection_drops_records_with_incomplete_required_refs(self) -> None:
        packet = json.loads(json.dumps(self._build()))
        ps = next(item for item in packet["deterministic_calculations"] if item["metric"] == "ps")
        ps["input_refs"].remove("fact:revenue")
        fcf = next(item for item in packet["selected_frames"] if item["id"] == "fcf")
        fcf["input_refs"].remove("fact:capex")
        sales = next(item for item in packet["market_implied_bridge"]["bridge_lines"] if item["type"] == "sales_anchor")
        sales["input_refs"].remove("fact:revenue")

        evidence = build_valuation_artifact_evidence(packet)
        card = render_valuation_card(packet)

        self.assertNotIn("ps", {item["metric"] for item in evidence["deterministic_calculations"]})
        self.assertNotIn("fcf", {item["id"] for item in evidence["selected_frames"]})
        self.assertNotIn("sales_anchor", {item["type"] for item in evidence["market_implied_bridge"]["bridge_lines"]})
        self.assertNotIn("P/S:", card)
        self._assert_public_refs_resolve(evidence)

    def test_sparse_single_facts_do_not_create_supported_frame_fit(self) -> None:
        context = {"stock": {"symbol": "ACME", "market": "US"}}
        sparse_cases = {
            "capex": ("fcf", 0.15),
            "revenue": ("comparable_multiples", 0.2),
        }
        for metric, (frame_id, expected_score) in sparse_cases.items():
            snapshot = {
                "facts": [{
                    "metric": metric,
                    "value": 100.0,
                    "source_id": f"raw:{metric}",
                    "source_type": "sec_companyfacts",
                    "currency": "USD",
                }],
                "target_resolution": {"normalized_target": "US.ACME", "currency": "USD"},
            }
            with self.subTest(metric=metric), tempfile.TemporaryDirectory() as temporary:
                packet, _ = build_valuation_artifact(
                    context, symbol="ACME", market="US", output_dir=Path(temporary),
                    command="valuation US.ACME", provider_snapshot=snapshot,
                    now=datetime(2026, 7, 19, tzinfo=timezone.utc),
                )
                score = next(item for item in packet["internal_frame_scores"] if item["id"] == frame_id)
                fit = next(item for item in packet["market_implied_bridge"]["frame_fit_ranking"] if item["id"] == frame_id)
                self.assertEqual(score["score"], expected_score)
                self.assertEqual(fit["fit_to_current_market_value"], "insufficient_data")
                self.assertEqual(fit["confidence"], "low")

    def test_huge_integer_is_omitted_without_overflow(self) -> None:
        snapshot = {
            "facts": [{
                "metric": "revenue",
                "value": 10 ** 10000,
                "source_id": "raw:revenue",
                "source_type": "sec_companyfacts",
                "currency": "USD",
            }],
            "target_resolution": {"normalized_target": "US.ACME", "currency": "USD"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                {"stock": {"symbol": "ACME", "market": "US"}},
                symbol="ACME", market="US", output_dir=Path(temporary),
                command="valuation US.ACME", provider_snapshot=snapshot,
                now=datetime(2026, 7, 19, tzinfo=timezone.utc),
            )
        self.assertNotIn("revenue", {fact["metric"] for fact in packet["facts"]})
        self.assertIn("missing_revenue", packet["degraded_state"]["reason_codes"])

    def test_build_total_boundary_omits_malformed_scalar_categories(self) -> None:
        context = {
            "stock": {"symbol": "ACME", "market": "US", "core_business": "Detailed industrial profile."},
            "facts": [
                {"metric": [], "value": 1.0, "source_type": {}},
                {"metric": {"revenue": True}, "value": 2.0, "source_type": []},
                {"metric": {"non_json"}, "value": float("inf"), "source_type": {"bad"}},
            ],
            "sources": [{"source_type": ["sec_companyfacts"], "provider": {"SEC": True}}],
        }
        snapshot = {
            "source_attempts": [
                {"family": [], "status": {}},
                {"family": {"official_financial": True}, "status": ["failed"]},
            ],
            "market_snapshot_status": [],
            "financial_fact_status": {},
            "target_resolution": {"normalized_target": "US.ACME", "mapping_source": []},
        }

        packet = self._build(context, snapshot)

        self.assertEqual(packet["facts"], [])
        self.assertEqual(packet["source_coverage"]["source_attempts"], [])
        json.dumps(packet, allow_nan=False)

    def test_evidence_and_card_total_boundary_for_malformed_nested_json(self) -> None:
        packet = json.loads(json.dumps(self._build()))
        packet["facts"][0]["metric"] = []
        packet["stock"]["scoring_signals"]["core_business"] = [["cyclical"], {"growth": True}]
        packet["source_coverage"]["source_registry"][0]["source_type"] = []
        packet["source_coverage"]["source_registry"][0]["family"] = {"official": True}
        packet["source_coverage"]["source_attempts"] = [{"family": [], "status": {}}]
        packet["deterministic_calculations"][0]["metric"] = {}
        packet["internal_frame_scores"][0]["id"] = []
        packet["market_implied_bridge"]["bridge_lines"][0]["type"] = {}

        evidence = build_valuation_artifact_evidence(packet)
        card = render_valuation_card(packet)

        json.dumps(evidence, allow_nan=False)
        self._assert_public_refs_resolve(evidence)
        self.assertIn("Valuation research card", card)

        non_json = self._build()
        non_json["deterministic_calculations"][0]["input_refs"] = {"fact:revenue"}
        with self.assertRaises(ValueError):
            build_valuation_artifact_evidence(non_json)
        with self.assertRaises(ValueError):
            render_valuation_card(non_json)

    def test_latest_loader_returns_none_for_malformed_nested_json_categories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=output_dir,
                command="valuation US.ACME", provider_snapshot=self._snapshot(),
                now=datetime(2026, 7, 19, tzinfo=timezone.utc),
            )
            malformed = json.loads(json.dumps(packet))
            malformed["facts"][0]["metric"] = []
            malformed["stock"]["scoring_signals"]["core_business"] = [{"cyclical": True}]
            malformed["source_coverage"]["source_registry"][0]["family"] = []
            malformed["source_coverage"]["source_attempts"] = [{"family": {}, "status": []}]
            latest = output_dir / "valuation" / "ACME_US_valuation_latest.json"
            latest.write_text(json.dumps(malformed), encoding="utf-8")

            self.assertIsNone(load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=output_dir))

    def test_extreme_ratios_and_percent_displays_fail_closed(self) -> None:
        cases = {
            "multiple_overflow": [
                {"metric": "market_cap", "value": 1e308, "source_type": "market_snapshot", "currency": "USD"},
                {"metric": "revenue", "value": 1e-308, "source_type": "sec_companyfacts", "currency": "USD"},
            ],
            "percent_display_overflow": [
                {"metric": "gross_profit", "value": 1e308, "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "revenue", "value": 10.0, "source_type": "sec_companyfacts", "currency": "USD"},
            ],
        }
        for label, facts in cases.items():
            snapshot = {"facts": facts, "target_resolution": {"normalized_target": "US.ACME"}}
            with self.subTest(label=label):
                packet = self._build(snapshot=snapshot)
                evidence = build_valuation_artifact_evidence(packet)
                card = render_valuation_card(packet)
                calculation_metrics = {item["metric"] for item in packet["deterministic_calculations"]}
                bridge_types = {item["type"] for item in packet["market_implied_bridge"]["bridge_lines"]}

                if label == "multiple_overflow":
                    self.assertNotIn("ps", calculation_metrics)
                    self.assertNotIn("sales_anchor", bridge_types)
                else:
                    self.assertNotIn("gross_margin", calculation_metrics)
                self._assert_finite_json_tree(packet)
                self._assert_finite_json_tree(evidence)
                self._assert_finite_json_tree(card)
                json.dumps(packet, allow_nan=False)
                json.dumps(evidence, allow_nan=False)

    def test_recognized_provider_and_mapping_provenance_survives_canonically(self) -> None:
        provider_categories = {
            "SEC": "sec",
            "OfficialResearchProvider": "official_research",
            "HKEX": "hkex",
            "DART": "dart",
            "FSS": "fss",
            "company_ir": "company_ir",
            "yahoo_chart": "yahoo",
            "shared_market": "shared_market",
            "vendor_financial": "vendor",
            "manual": "manual",
            "provider": "generic_provider",
        }
        snapshot = self._snapshot()
        snapshot["facts"][0]["provider"] = "OfficialResearchProvider"
        snapshot["sources"] = [
            {"source_type": "vendor_financial", "provider": raw}
            for raw in provider_categories
        ]
        snapshot["target_resolution"]["mapping_source"] = "provider"

        packet = self._build(snapshot=snapshot)
        evidence = build_valuation_artifact_evidence(packet)
        revenue = next(item for item in packet["facts"] if item["metric"] == "revenue")
        public_revenue = next(item for item in evidence["facts"] if item["metric"] == "revenue")
        registry_categories = {
            item["provider_category"]
            for item in packet["source_coverage"]["source_registry"]
            if "provider_category" in item
        }

        self.assertEqual(revenue["provider_category"], "official_research")
        self.assertEqual(public_revenue["provider_category"], "official_research")
        self.assertEqual(registry_categories, set(provider_categories.values()))
        self.assertEqual(packet["target_resolution"]["mapping_category"], "generic_provider")
        self.assertEqual(evidence["target"]["mapping_category"], "generic_provider")
        for source in packet["source_coverage"]["source_registry"]:
            self.assertRegex(source["id"], r"^source:[0-9a-f]{16}$")

    def test_hostile_provider_and_mapping_provenance_is_omitted(self) -> None:
        snapshot = self._snapshot()
        for fact in snapshot["facts"]:
            fact["provider"] = "reports.json"
        snapshot["sources"] = [{"source_type": "sec_companyfacts", "provider": "PRIVATE-KEY"}]
        snapshot["target_resolution"]["mapping_source"] = "api_key"

        packet = self._build(snapshot=snapshot)
        evidence = build_valuation_artifact_evidence(packet)
        serialized = json.dumps({"packet": packet, "evidence": evidence})

        self.assertNotIn("provider_category", serialized)
        self.assertNotIn("mapping_category", serialized)
        for hostile in ("reports.json", "PRIVATE-KEY", "api_key"):
            self.assertNotIn(hostile, serialized)

    def test_comparable_support_requires_positive_market_value_and_denominator(self) -> None:
        cases = {
            "zero_market_cap": (("market_cap", 0.0), ("revenue", 100.0)),
            "negative_market_cap": (("market_cap", -100.0), ("revenue", 100.0)),
            "zero_revenue": (("market_cap", 100.0), ("revenue", 0.0)),
            "negative_earnings": (("market_cap", 100.0), ("net_income", -10.0)),
            "negative_ebitda": (("market_cap", 100.0), ("ebitda", -10.0)),
        }
        for label, facts in cases.items():
            snapshot = {
                "facts": [
                    {"metric": metric, "value": value, "source_type": "market_snapshot" if metric == "market_cap" else "sec_companyfacts", "currency": "USD"}
                    for metric, value in facts
                ],
                "target_resolution": {"normalized_target": "US.ACME"},
                "market_snapshot_status": "present",
            }
            with self.subTest(label=label):
                packet = self._build(context={"stock": {"symbol": "ACME", "market": "US"}}, snapshot=snapshot)
                score = next(item for item in packet["internal_frame_scores"] if item["id"] == "comparable_multiples")
                fit = next(item for item in packet["market_implied_bridge"]["frame_fit_ranking"] if item["id"] == "comparable_multiples")
                self.assertEqual(score["score"], 0.2)
                self.assertEqual(fit["fit_to_current_market_value"], "insufficient_data")
                self.assertEqual(fit["confidence"], "low")

    def test_stale_market_status_caps_comparable_fit_and_confidence(self) -> None:
        snapshot = {
            "facts": [
                {"metric": "market_cap", "value": 100.0, "source_type": "market_snapshot", "currency": "USD"},
                {"metric": "revenue", "value": 50.0, "source_type": "sec_companyfacts", "currency": "USD"},
            ],
            "target_resolution": {"normalized_target": "US.ACME"},
            "market_snapshot_status": "stale",
        }

        packet = self._build(context={"stock": {"symbol": "ACME", "market": "US"}}, snapshot=snapshot)
        score = next(item for item in packet["internal_frame_scores"] if item["id"] == "comparable_multiples")
        fit = next(item for item in packet["market_implied_bridge"]["frame_fit_ranking"] if item["id"] == "comparable_multiples")

        self.assertEqual(score["score"], 0.65)
        self.assertEqual(fit["fit_to_current_market_value"], "partial_fit")
        self.assertEqual(fit["confidence"], "low")

    def test_comparable_market_status_policy_fails_closed(self) -> None:
        omitted = object()
        base_snapshot = {
            "facts": [
                {"metric": "market_cap", "value": 100.0, "source_type": "market_snapshot", "currency": "USD"},
                {"metric": "revenue", "value": 50.0, "source_type": "sec_companyfacts", "currency": "USD"},
            ],
            "target_resolution": {"normalized_target": "US.ACME"},
        }
        cases = (
            (("present", "available", "success"), 0.65, "fits"),
            (("stale", "partial"), 0.65, "partial_fit"),
            (("attempted", "unknown", "missing", "unavailable", "failed", "omitted", "absent", None, [], omitted), 0.2, "insufficient_data"),
        )
        for statuses, expected_score, expected_fit in cases:
            for status in statuses:
                snapshot = dict(base_snapshot)
                if status is not omitted:
                    snapshot["market_snapshot_status"] = status
                with self.subTest(status="omitted" if status is omitted else status):
                    packet = self._build(context={"stock": {"symbol": "ACME", "market": "US"}}, snapshot=snapshot)
                    evidence = build_valuation_artifact_evidence(packet)
                    for artifact in (packet, evidence):
                        score = next(item for item in artifact["internal_frame_scores"] if item["id"] == "comparable_multiples")
                        fit = next(item for item in artifact["market_implied_bridge"]["frame_fit_ranking"] if item["id"] == "comparable_multiples")
                        self.assertEqual(score["score"], expected_score)
                        self.assertEqual(fit["fit_to_current_market_value"], expected_fit)
                        if expected_fit != "fits":
                            self.assertEqual(fit["confidence"], "low")

    def test_profile_presence_is_distinct_from_canonical_scoring_signal(self) -> None:
        detailed = self._context()
        detailed["stock"]["name"] = "Acme Retail"
        detailed["stock"]["core_business"] = "Detailed retail operations for specialist customers."
        detailed["stock"]["stock_character"] = "Established retail operator with extensive disclosures."
        packet = self._build(context=detailed)

        self.assertTrue(packet["stock"]["profile_present"])
        self.assertNotIn("scoring_signals", packet["stock"])
        self.assertIn("no_canonical_scoring_signal", packet["degraded_state"]["reason_codes"])
        self.assertNotIn("missing_stock_profile", packet["degraded_state"]["reason_codes"])
        public = build_valuation_artifact_evidence(packet)
        self.assertTrue(public["stock"]["profile_present"])
        self.assertIn(
            "no canonical valuation scoring signal was derived from the stock profile",
            public["degraded_state"]["reasons"],
        )

        empty = self._build(context={"stock": {"symbol": "ACME", "market": "US"}})
        self.assertIn("missing_stock_profile", empty["degraded_state"]["reason_codes"])

        standalone_ai = self._build(context={"stock": {
            "symbol": "ACME", "market": "US", "core_business": "AI platform for enterprise customers.",
        }})
        self.assertEqual(standalone_ai["stock"]["scoring_signals"], {"core_business": ["growth_scenario"]})

        cjk_substring = self._build(context={"stock": {
            "symbol": "ACME", "market": "US", "core_business": "服务细分市场空间需求。",
        }})
        self.assertEqual(cjk_substring["stock"]["scoring_signals"], {"core_business": ["growth_scenario"]})


class StockValuationCommandRouterTests(unittest.TestCase):
    def _context(self) -> dict[str, object]:
        return {
            "stock": {
                "id": 1,
                "symbol": "INTC",
                "market": "US",
                "name": "Intel Corporation",
                "core_business": "Semiconductor manufacturing with cyclical demand.",
                "stock_character": "Cyclical semiconductor company.",
            },
            "stock_knowledge": [],
            "stock_insights": [],
            "sources": [],
        }

    def _snapshot(self) -> dict[str, object]:
        return {
            "target_resolution": {
                "normalized_symbol": "INTC",
                "normalized_market": "US",
                "normalized_target": "US.INTC",
                "currency": "USD",
                "mapping_source": "sec",
            },
            "facts": [
                {
                    "metric": "revenue",
                    "value": 10_000.0,
                    "currency": "USD",
                    "period_end": "2025-12-31",
                    "source_type": "sec_companyfacts",
                    "provider": "sec",
                },
                {
                    "metric": "price",
                    "value": 25.0,
                    "currency": "USD",
                    "timestamp": "2026-07-19T00:00:00+00:00",
                    "source_type": "market_snapshot",
                    "provider": "yahoo",
                },
            ],
            "sources": [
                {"source_type": "sec_companyfacts", "provider": "sec"},
                {"source_type": "market_snapshot", "provider": "yahoo"},
            ],
            "financial_fact_status": "partial",
            "market_snapshot_status": "partial",
            "source_attempts": [],
        }

    def test_creation_aliases_write_only_a_local_research_artifact(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(command_router.repository, "get_stock_context", return_value=self._context()) as get_context,
            patch.object(
                command_router,
                "fetch_valuation_snapshot",
                return_value=self._snapshot(),
            ) as fetch_snapshot,
            patch.object(command_router.repository, "record_user_insight") as record_insight,
            patch.object(command_router.repository, "propose_candidate_insight") as propose_candidate,
        ):
            for command in ("valuation US.INTC", "value US.INTC", "估值 US.INTC"):
                with self.subTest(command=command):
                    result = command_router.handle_command(command, output_dir=Path(temporary))
                    self.assertTrue(result.ok)
                    self.assertIn("Valuation research card: US.INTC", result.message)
                    self.assertNotIn(temporary, result.message)

            self.assertTrue((Path(temporary) / "valuation" / "INTC_US_valuation_latest.json").is_file())
            self.assertEqual(get_context.call_count, 3)
            self.assertEqual(fetch_snapshot.call_count, 3)
            fetch_snapshot.assert_called_with("INTC", "US", company_name="Intel Corporation")
            record_insight.assert_not_called()
            propose_candidate.assert_not_called()

        self.assertTrue(command_router.is_research_write_command("valuation US.INTC"))
        self.assertFalse(command_router.is_candidate_write_command("valuation US.INTC"))

    def test_latest_evidence_and_methods_are_safe_read_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            build_valuation_artifact(
                self._context(),
                symbol="INTC",
                market="US",
                output_dir=output_dir,
                command="valuation US.INTC",
                provider_snapshot=self._snapshot(),
                now=datetime(2026, 7, 19, tzinfo=timezone.utc),
            )

            latest = command_router.handle_command("latest valuation US.INTC", output_dir=output_dir)
            latest_zh = command_router.handle_command("查看估值 US.INTC", output_dir=output_dir)
            evidence = command_router.handle_command("valuation artifact evidence US.INTC", output_dir=output_dir)
            evidence_alias = command_router.handle_command("估值证据 US.INTC", output_dir=output_dir)
            methods = command_router.handle_command("valuation methods", output_dir=output_dir)
            methods_zh = command_router.handle_command("估值方法", output_dir=output_dir)

        for result in (latest, latest_zh):
            self.assertTrue(result.ok)
            self.assertIn("Valuation research card: US.INTC", result.message)
        for result in (evidence, evidence_alias):
            self.assertTrue(result.ok)
            public = json.loads(result.message)
            self.assertEqual(public["schema"], "stock_valuation_evidence.v1")
            self.assertNotIn("artifact_path", result.message)
        for result in (methods, methods_zh):
            self.assertTrue(result.ok)
            self.assertIn("Valuation method library", result.message)
        for command in (
            "latest valuation US.INTC",
            "valuation artifact evidence US.INTC",
            "valuation methods",
        ):
            self.assertTrue(command_router.is_query_command(command), command)
            self.assertFalse(command_router.is_research_write_command(command), command)

    def test_normal_missing_profile_commands_require_bounded_bootstrap_without_writes(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(command_router.repository, "get_stock_context", return_value={"stock": None}),
            patch.object(command_router.repository, "upsert_stock_profile") as upsert_profile,
            patch.object(command_router, "fetch_valuation_snapshot") as fetch_snapshot,
            patch.object(command_router, "build_valuation_artifact") as build_artifact,
        ):
            results = [
                command_router.handle_command(command, output_dir=Path(temporary))
                for command in ("valuation KR.000660", "valuation US.MSTR")
            ]

        self.assertTrue(all(not result.ok for result in results))
        self.assertTrue(all("Command Workbench" in result.message for result in results))
        fetch_snapshot.assert_not_called()
        build_artifact.assert_not_called()
        upsert_profile.assert_not_called()

    def test_supported_name_alias_preview_executes_trusted_degraded_artifact_without_other_writes(self) -> None:
        snapshot = {
            "target_resolution": {
                "normalized_symbol": "000660",
                "normalized_market": "KR",
                "normalized_target": "KR.000660",
                "currency": "KRW",
                "mapping_source": "dart",
            },
            "facts": [],
            "sources": [],
            "financial_fact_status": "unavailable",
            "market_snapshot_status": "unavailable",
            "source_attempts": [],
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch(
                "investment_knowledge_mcp.command_workbench.repository.resolve_stock_reference",
                return_value=[],
            ),
            patch.object(command_router.repository, "get_stock_context", return_value={"stock": None}),
            patch.object(command_router.repository, "upsert_stock_profile") as upsert_profile,
            patch.object(command_router.repository, "record_user_insight") as record_insight,
            patch.object(command_router.repository, "propose_candidate_insight") as propose_candidate,
            patch.object(command_router, "fetch_valuation_snapshot", return_value=snapshot) as fetch_snapshot,
        ):
            preview = parse_workbench_command("valuation SK Hynix", allow_llm=False)
            result = command_router.handle_command(
                preview["exact_command"],
                output_dir=Path(temporary),
            )
            packet = load_latest_valuation_artifact(
                symbol="000660",
                market="KR",
                output_dir=Path(temporary),
            )

        self.assertEqual("stock valuation KR.000660", preview["exact_command"])
        self.assertTrue(result.ok)
        self.assertIsNotNone(packet)
        self.assertIn("missing_stock_profile", packet["degraded_state"]["reason_codes"])
        fetch_snapshot.assert_called_once_with(
            "000660",
            "KR",
            company_name="SK hynix Inc.",
        )
        upsert_profile.assert_not_called()
        record_insight.assert_not_called()
        propose_candidate.assert_not_called()

    def test_trusted_valuation_form_rejects_non_allowlisted_target_without_writes(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(command_router.repository, "get_stock_context") as get_context,
            patch.object(command_router.repository, "upsert_stock_profile") as upsert_profile,
            patch.object(command_router, "fetch_valuation_snapshot") as fetch_snapshot,
            patch.object(command_router, "build_valuation_artifact") as build_artifact,
        ):
            result = command_router.handle_command(
                "stock valuation US.MSTR",
                output_dir=Path(temporary),
            )

        self.assertFalse(result.ok)
        get_context.assert_not_called()
        fetch_snapshot.assert_not_called()
        build_artifact.assert_not_called()
        upsert_profile.assert_not_called()

    def test_valuation_write_classifier_matches_only_executable_creation_forms(self) -> None:
        rejected = command_router.handle_command("valuation INTC")

        self.assertFalse(rejected.ok)
        for command in ("valuation INTC", "valuation CN.600000", "stock valuation US.MSTR"):
            with self.subTest(command=command):
                self.assertFalse(command_router.is_research_write_command(command))
                self.assertFalse(command_router.is_candidate_write_command(command))
        for command in (
            "valuation US.INTC",
            "value INTC US",
            "估值 KR.000660",
            "stock valuation US.INTC",
            "stock valuation KR.000660",
            "stock valuation HK.01888",
        ):
            with self.subTest(command=command):
                self.assertTrue(command_router.is_research_write_command(command))
                self.assertFalse(command_router.is_candidate_write_command(command))

    def test_router_failures_are_bounded_and_do_not_echo_paths_or_raw_exceptions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            with patch.object(
                command_router.repository,
                "get_stock_context",
                side_effect=RuntimeError("postgresql://user:secret@private-db/internal"),
            ):
                repository_failure = command_router.handle_command("valuation US.INTC", output_dir=output_dir)

            missing = command_router.handle_command("latest valuation US.INTC", output_dir=output_dir)
            path_like = command_router.handle_command(
                "valuation artifact evidence ../../etc/passwd",
                output_dir=output_dir,
            )

        self.assertFalse(repository_failure.ok)
        self.assertFalse(missing.ok)
        self.assertFalse(path_like.ok)
        public_text = "\n".join((repository_failure.message, missing.message, path_like.message)).lower()
        for unsafe in ("postgresql://", "secret", "private-db", "/etc/passwd", "traceback"):
            self.assertNotIn(unsafe, public_text)


if __name__ == "__main__":
    unittest.main()
