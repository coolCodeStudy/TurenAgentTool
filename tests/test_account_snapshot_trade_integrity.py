from __future__ import annotations

from datetime import date, datetime, timezone
import unittest
from unittest import mock

from investment_knowledge_mcp import account_snapshots


class AccountSnapshotTradeIntegrityTests(unittest.TestCase):
    def test_snapshot_reads_explicit_trade_reconciliation_range(self) -> None:
        snapshot_date = date(2026, 7, 20)
        trade_start = date(2026, 7, 7)
        trade_snapshot = mock.Mock(
            deals=[{"deal_id": "deal-1"}],
            fetched_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
            account_info={},
            account_error=None,
        )
        position_snapshot = mock.Mock(positions=[])

        with (
            mock.patch.object(account_snapshots, "get_futu_trade_history", return_value=trade_snapshot) as history,
            mock.patch.object(account_snapshots, "get_futu_positions", return_value=position_snapshot),
            mock.patch.object(account_snapshots.repository, "upsert_trade_records", return_value={"synced_count": 1}),
            mock.patch.object(account_snapshots.repository, "upsert_account_snapshot", return_value={"id": 1}),
        ):
            account_snapshots.run_account_snapshot_once(
                snapshot_date=snapshot_date,
                trade_start=trade_start,
            )

        history.assert_called_once_with(start="2026-07-07", end="2026-07-20")
