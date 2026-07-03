from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
import os
import unittest
from unittest.mock import patch

from investment_knowledge_mcp.kline_agent import (
    KlineBar,
    KlineFetchResult,
    KlineMetadata,
    KlineRequest,
    inspect_kline_behavior,
    parse_kline_command,
    render_kline_report,
)


class FakeProvider:
    def __init__(self, bars: list[KlineBar]) -> None:
        self.bars = bars

    def fetch_daily_bars(
        self,
        *,
        symbol: str,
        market: str,
        years: int,
        adjust_type: str,
    ) -> KlineFetchResult:
        return KlineFetchResult(
            metadata=KlineMetadata(
                provider="fixture",
                provider_symbol=f"{market}.{symbol}",
                symbol=symbol,
                market=market,
                currency="USD",
                timezone="America/New_York",
                requested_start=self.bars[0].bar_date,
                requested_end=self.bars[-1].bar_date,
                actual_start=self.bars[0].bar_date,
                actual_end=self.bars[-1].bar_date,
                adjustment_type=adjust_type,
                fetched_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
                raw_bar_count=len(self.bars),
                normalized_bar_count=len(self.bars),
            ),
            bars=self.bars,
            warnings=[],
        )


class KlineAgentTests(unittest.TestCase):
    def test_parse_supported_kline_commands(self) -> None:
        self.assertEqual(parse_kline_command("K线 US.NVDA"), KlineRequest(symbol="NVDA", market="US"))
        self.assertEqual(parse_kline_command("K线 HK.00700"), KlineRequest(symbol="00700", market="HK"))
        self.assertEqual(parse_kline_command("K线 000660 KR"), KlineRequest(symbol="000660", market="KR"))
        self.assertEqual(
            parse_kline_command("K线调查 US.NVDA 5年 前复权"),
            KlineRequest(symbol="NVDA", market="US", years=5, adjust_type="forward_adjusted"),
        )

    def test_fixture_report_contains_metadata_statistics_and_timeframes(self) -> None:
        bars = _fixture_bars(520)
        result = inspect_kline_behavior(
            KlineRequest(symbol="NVDA", market="US", years=5, adjust_type="forward_adjusted"),
            provider=FakeProvider(bars),
        )
        report = render_kline_report(result)

        self.assertIn("Provider: fixture", report)
        self.assertIn("Provider symbol: US.NVDA", report)
        self.assertIn("Currency: USD", report)
        self.assertIn("Timezone: America/New_York", report)
        self.assertIn("Daily", report)
        self.assertIn("Weekly", report)
        self.assertIn("Monthly", report)
        self.assertIn("samples=", report)
        self.assertIn("mean=", report)
        self.assertIn("median=", report)
        self.assertIn("win_rate=", report)
        self.assertIn("adverse=", report)
        self.assertIn("confidence=", report)
        self.assertNotIn("买入", report)
        self.assertNotIn("卖出", report)
        self.assertNotIn("持有", report)
        self.assertNotRegex(report.lower(), r"\bbuy\b")
        self.assertNotRegex(report.lower(), r"\bsell\b")
        self.assertNotRegex(report.lower(), r"\bhold\b")

    def test_insufficient_evidence_is_reported_for_short_history(self) -> None:
        bars = _fixture_bars(18)
        result = inspect_kline_behavior(KlineRequest(symbol="NVDA", market="US"), provider=FakeProvider(bars))
        report = render_kline_report(result)

        self.assertIn("insufficient", report.lower())
        self.assertIn("Daily has only", report)
        self.assertIn("Weekly has only", report)
        self.assertIn("Monthly has only", report)

    def test_command_router_reaches_kline_handler(self) -> None:
        from investment_knowledge_mcp.command_router import handle_command

        with patch(
            "investment_knowledge_mcp.command_router.investigate_kline_behavior",
            return_value="patched kline report",
        ) as mock_handler:
            result = handle_command("K线调查 US.NVDA 5年 前复权")

        self.assertTrue(result.ok)
        self.assertEqual(result.message, "patched kline report")
        self.assertEqual(mock_handler.call_args.args[0], KlineRequest(symbol="NVDA", market="US", years=5, adjust_type="forward_adjusted"))

    def test_disabled_live_provider_is_local_acceptance_safe(self) -> None:
        with patch.dict(os.environ, {"KLINE_PROVIDER": "disabled"}):
            result = inspect_kline_behavior(KlineRequest(symbol="NVDA", market="US"))

        report = render_kline_report(result)

        self.assertIn("Provider: unavailable", report)
        self.assertIn("Kline live provider is disabled", report)
        self.assertNotIn("Futu OpenD is not reachable", report)

    def test_command_router_can_disable_live_provider_for_web_acceptance(self) -> None:
        from investment_knowledge_mcp.command_router import handle_command

        result = handle_command("K线调查 US.NVDA 5年 前复权", disable_kline_live_provider=True)

        self.assertTrue(result.ok)
        self.assertIn("Provider: unavailable", result.message)
        self.assertIn("Kline live provider is disabled", result.message)
        self.assertNotIn("Futu OpenD is not reachable", result.message)


def _fixture_bars(count: int) -> list[KlineBar]:
    bars: list[KlineBar] = []
    current_date = date(2020, 1, 2)
    trading_index = 0
    close = 100.0
    while len(bars) < count:
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        seasonal = math.sin(trading_index / 18) * 3.0
        close = 95.0 + trading_index * 0.12 + seasonal
        if trading_index % 70 in {0, 1, 2, 3} and trading_index > 0:
            close -= 8.0
        if len(bars) == count - 1:
            close += 12.0
        open_price = close * (0.992 if trading_index % 17 else 1.01)
        high = max(open_price, close) * 1.015
        low = min(open_price, close) * 0.985
        volume = 1_000_000 + (trading_index % 30) * 20_000
        if len(bars) == count - 1:
            volume *= 3
        bars.append(
            KlineBar(
                bar_date=current_date,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=float(volume),
                turnover=float(volume * close),
            )
        )
        trading_index += 1
        current_date += timedelta(days=1)
    return bars


if __name__ == "__main__":
    unittest.main()
