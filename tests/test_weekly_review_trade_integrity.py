from __future__ import annotations

from datetime import date, datetime, timezone
import unittest
from unittest import mock

from investment_knowledge_mcp import weekly_review
from investment_knowledge_mcp.futu_provider import FutuProviderError


class WeeklyReviewTradeIntegrityTests(unittest.TestCase):
    def test_partial_cached_week_is_reconciled_with_broker_deals(self) -> None:
        cached = {
            "deal_id": "cached-1",
            "code": "US.DRAM",
            "trade_date": "2026-07-19",
            "create_time": "2026-07-19 20:10:43",
        }
        recovered = {
            "deal_id": "broker-2",
            "code": "US.SPCX",
            "trade_date": "2026-07-15",
            "create_time": "2026-07-15 12:27:31",
        }
        snapshot = mock.Mock(
            deals=[cached, recovered],
            fetched_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
        )
        source_status: dict[str, object] = {}
        warnings: list[str] = []

        with (
            mock.patch.object(
                weekly_review.repository,
                "list_trade_records",
                side_effect=([cached], [cached, recovered]),
            ) as records,
            mock.patch.object(weekly_review, "get_futu_trade_history", return_value=snapshot) as fetch,
            mock.patch.object(weekly_review.repository, "upsert_trade_records") as upsert,
        ):
            result = weekly_review._load_trade_records(
                start=date(2026, 7, 13),
                end=date(2026, 7, 19),
                source_status=source_status,
                warnings=warnings,
            )

        self.assertEqual(result, [cached, recovered])
        fetch.assert_called_once_with(start="2026-07-13", end="2026-07-19")
        upsert.assert_called_once_with([cached, recovered])
        self.assertEqual(records.call_count, 2)
        self.assertEqual(source_status["trades"]["status"], "reconciled")
        self.assertEqual(warnings, [])

    def test_broker_reconciliation_failure_preserves_cached_week(self) -> None:
        cached = {
            "deal_id": "cached-1",
            "code": "US.DRAM",
            "trade_date": "2026-07-19",
            "create_time": "2026-07-19 20:10:43",
        }
        source_status: dict[str, object] = {}
        warnings: list[str] = []

        with (
            mock.patch.object(weekly_review.repository, "list_trade_records", return_value=[cached]),
            mock.patch.object(
                weekly_review,
                "get_futu_trade_history",
                side_effect=FutuProviderError("private provider detail"),
            ),
            mock.patch.object(weekly_review.repository, "upsert_trade_records") as upsert,
        ):
            result = weekly_review._load_trade_records(
                start=date(2026, 7, 13),
                end=date(2026, 7, 19),
                source_status=source_status,
                warnings=warnings,
            )

        self.assertEqual(result, [cached])
        upsert.assert_not_called()
        self.assertEqual(source_status["trades"], {"status": "partial", "count": 1})
        self.assertEqual(warnings, ["交易记录未能完成富途对账，正在显示已保存的数据。"])
