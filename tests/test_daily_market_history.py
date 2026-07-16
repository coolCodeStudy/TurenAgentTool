from __future__ import annotations

from datetime import date
import json
import threading
import time
import unittest

from investment_knowledge_mcp.daily_market_history import (
    HistoricalActivityCancelled,
    load_historical_market_activity,
)


class FakeFrame:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict]:
        if orient != "records":
            raise AssertionError(f"unexpected orient: {orient}")
        return self.rows


class FakeHistoricalAkshare:
    def __init__(
        self,
        *,
        universe: list[dict],
        histories: dict[str, list[dict]],
        market_cap_default: float | None = 10_000_000_000,
    ) -> None:
        self.universe = [
            {
                **row,
                **(
                    {"总市值": market_cap_default}
                    if market_cap_default is not None
                    and not any(
                        key in row
                        for key in ("总市值", "Total Market Value", "Market Cap", "market_cap", "mktcap")
                    )
                    else {}
                ),
            }
            for row in universe
        ]
        self.histories = histories
        self.history_calls: list[tuple[str, dict[str, object]]] = []

    def stock_zh_a_spot_em(self) -> FakeFrame:
        return FakeFrame(self.universe)

    def stock_hk_main_board_spot_em(self) -> FakeFrame:
        return FakeFrame(self.universe)

    def stock_us_spot_em(self) -> FakeFrame:
        return FakeFrame(self.universe)

    def stock_zh_a_hist(
        self,
        symbol: str,
        period: str,
        start_date: str,
        end_date: str,
        adjust: str,
        timeout: float | None = None,
    ) -> FakeFrame:
        return self._history(
            "stock_zh_a_hist",
            symbol=symbol,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            timeout=timeout,
        )

    def stock_hk_hist(
        self, symbol: str, period: str, start_date: str, end_date: str, adjust: str
    ) -> FakeFrame:
        return self._history(
            "stock_hk_hist",
            symbol=symbol,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )

    def stock_us_hist(
        self, symbol: str, period: str, start_date: str, end_date: str, adjust: str
    ) -> FakeFrame:
        return self._history(
            "stock_us_hist",
            symbol=symbol,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )

    def _history(self, method: str, **kwargs: object) -> FakeFrame:
        self.history_calls.append((method, kwargs))
        return FakeFrame(self.histories.get(str(kwargs["symbol"]), []))


def history_rows(
    *, previous_date: str = "2026-07-08", market_date: str = "2026-07-09", turnover: float = 100_000_000
) -> list[dict]:
    return [
        {"日期": previous_date, "收盘": 10, "成交额": turnover},
        {"日期": market_date, "收盘": 11, "成交额": turnover},
    ]


class SequencedUniverseAkshare(FakeHistoricalAkshare):
    def __init__(self, *, outcomes: list[object]) -> None:
        universe = [{"代码": "000001", "名称": "甲", "成交额": 100_000_000, "总市值": 10_000_000_000}]
        super().__init__(universe=universe, histories={"000001": history_rows()})
        self.outcomes = list(outcomes)
        self.universe_calls = 0

    def stock_zh_a_spot_em(self) -> FakeFrame:
        self.universe_calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return FakeFrame(outcome)


class HistoricalActivityProviderTests(unittest.TestCase):
    def test_cn_historical_gainers_rank_exact_date_bars(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[
                {"代码": "000001", "名称": "甲", "成交额": 90_000_000},
                {"代码": "000002", "名称": "乙", "成交额": 100_000_000},
            ],
            histories={
                "000001": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 80_000_000},
                    {"日期": "2026-07-09", "收盘": 11, "成交额": 90_000_000},
                ],
                "000002": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 90_000_000},
                    {"日期": "2026-07-09", "收盘": 12, "成交额": 100_000_000},
                ],
            },
        )

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake, max_workers=1)

        self.assertEqual("000002", result.gainers[0]["code"])
        self.assertEqual(20.0, result.gainers[0]["change_pct"])
        self.assertEqual(100_000_000, result.gainers[0]["turnover"])
        self.assertEqual("2026-07-09", result.gainers[0]["session_date"])
        self.assertEqual("current_liquid_common_equity_market_cap_top_200", result.source_status["gainers"]["universe_basis"])

    def test_exact_akshare_signatures_and_cn_remaining_timeout(self) -> None:
        cn = FakeHistoricalAkshare(
            universe=[{"代码": "000001", "名称": "甲", "成交额": 100_000_000}],
            histories={"000001": history_rows()},
        )
        hk = FakeHistoricalAkshare(
            universe=[{"代码": "00700", "名称": "Tencent", "成交额": 30_000_000}],
            histories={"00700": history_rows(turnover=30_000_000)},
        )
        us = FakeHistoricalAkshare(
            universe=[{"代码": "105.MSFT", "名称": "Microsoft", "成交额": 20_000_000}],
            histories={"105.MSFT": history_rows(turnover=20_000_000)},
        )

        load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=cn, max_workers=1)
        load_historical_market_activity("HK", date(2026, 7, 9), akshare_module=hk, max_workers=1)
        load_historical_market_activity("US", date(2026, 7, 9), akshare_module=us, max_workers=1)

        self.assertEqual("stock_zh_a_hist", cn.history_calls[0][0])
        self.assertGreater(cn.history_calls[0][1]["timeout"], 0)
        self.assertLessEqual(cn.history_calls[0][1]["timeout"], 90.0)
        self.assertEqual("stock_hk_hist", hk.history_calls[0][0])
        self.assertNotIn("timeout", hk.history_calls[0][1])
        self.assertEqual("stock_us_hist", us.history_calls[0][0])
        self.assertNotIn("timeout", us.history_calls[0][1])
        for call in (cn.history_calls[0], hk.history_calls[0], us.history_calls[0]):
            self.assertEqual("daily", call[1]["period"])
            self.assertEqual("20260709", call[1]["end_date"])
            self.assertEqual("", call[1]["adjust"])

    def test_history_without_requested_row_cannot_use_a_later_bar(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[{"代码": "000001", "名称": "甲", "成交额": 100_000_000}],
            histories={
                "000001": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 90_000_000},
                    {"日期": "2026-07-10", "收盘": 15, "成交额": 100_000_000},
                ]
            },
        )

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake, max_workers=1)

        self.assertEqual([], result.gainers)
        self.assertEqual(1, result.source_status["gainers"]["requested"])
        self.assertEqual(1, result.source_status["gainers"]["queried"])
        self.assertEqual(0, result.source_status["gainers"]["usable"])

    def test_partial_coverage_records_requested_queried_and_usable_counts(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[
                {"代码": "000001", "名称": "甲", "成交额": 100_000_000},
                {"代码": "000002", "名称": "乙", "成交额": 90_000_000},
                {"代码": "000003", "名称": "丙", "成交额": 80_000_000},
            ],
            histories={
                "000001": history_rows(),
                "000002": [{"日期": "2026-07-09", "收盘": 12, "成交额": 90_000_000}],
                "000003": history_rows(turnover=40_000_000),
            },
        )

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake, max_workers=1)

        self.assertEqual(3, result.source_status["gainers"]["requested"])
        self.assertEqual(3, result.source_status["gainers"]["queried"])
        self.assertEqual(1, result.source_status["gainers"]["usable"])
        self.assertEqual("partial", result.source_status["gainers"]["status"])
        self.assertEqual(["000001"], [row["code"] for row in result.gainers])

    def test_transient_universe_connection_error_succeeds_on_retry(self) -> None:
        universe = [{"代码": "000001", "名称": "甲", "成交额": 100_000_000, "总市值": 10_000_000_000}]
        fake = SequencedUniverseAkshare(outcomes=[ConnectionError("transient"), universe])

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake)

        self.assertEqual(2, fake.universe_calls)
        self.assertEqual(2, result.source_status["gainers"]["universe_attempts"])
        self.assertEqual("ok", result.source_status["gainers"]["status"])

    def test_transient_universe_json_decode_error_succeeds_on_retry(self) -> None:
        universe = [{"代码": "000001", "名称": "甲", "成交额": 100_000_000, "总市值": 10_000_000_000}]
        decode_error = json.JSONDecodeError("invalid response", "", 0)
        fake = SequencedUniverseAkshare(outcomes=[decode_error, universe])

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake)

        self.assertEqual(2, fake.universe_calls)
        self.assertEqual(2, result.source_status["gainers"]["universe_attempts"])
        self.assertEqual("ok", result.source_status["gainers"]["status"])

    def test_empty_universe_response_succeeds_on_retry(self) -> None:
        universe = [{"代码": "000001", "名称": "甲", "成交额": 100_000_000, "总市值": 10_000_000_000}]
        fake = SequencedUniverseAkshare(outcomes=[[], universe])

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake)

        self.assertEqual(2, fake.universe_calls)
        self.assertEqual(2, result.source_status["gainers"]["universe_attempts"])
        self.assertEqual("ok", result.source_status["gainers"]["status"])

    def test_rate_limited_universe_succeeds_on_retry(self) -> None:
        universe = [{"代码": "000001", "名称": "甲", "成交额": 100_000_000, "总市值": 10_000_000_000}]
        fake = SequencedUniverseAkshare(outcomes=[RuntimeError("429 too many requests"), universe])

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake)

        self.assertEqual(2, fake.universe_calls)
        self.assertEqual(2, result.source_status["gainers"]["universe_attempts"])
        self.assertEqual("ok", result.source_status["gainers"]["status"])

    def test_exhausted_universe_retries_return_safe_unavailable_status(self) -> None:
        fake = SequencedUniverseAkshare(
            outcomes=[ConnectionError("private first error"), ConnectionError("private second error")]
        )

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake)

        status = result.source_status["gainers"]
        self.assertEqual(2, fake.universe_calls)
        self.assertEqual(2, status["universe_attempts"])
        self.assertEqual("provider_unavailable", status["status"])
        self.assertEqual(0, status["requested"])
        self.assertEqual(0, status["queried"])
        self.assertEqual(0, status["usable"])
        self.assertNotIn("private", status["message"])

    def test_universe_retry_does_not_start_after_deadline(self) -> None:
        release = threading.Event()
        finished = threading.Event()

        class SlowFailingUniverse(FakeHistoricalAkshare):
            def __init__(self) -> None:
                super().__init__(universe=[], histories={})
                self.universe_calls = 0

            def stock_zh_a_spot_em(self) -> FakeFrame:
                self.universe_calls += 1
                release.wait(1)
                finished.set()
                raise ConnectionError("late transient failure")

        fake = SlowFailingUniverse()
        timer = threading.Timer(0.2, release.set)
        timer.daemon = True
        timer.start()
        result = load_historical_market_activity(
            "CN", date(2026, 7, 9), akshare_module=fake, timeout_seconds=0.05
        )

        self.assertEqual("timed_out", result.source_status["gainers"]["status"])
        self.assertEqual(1, result.source_status["gainers"]["universe_attempts"])
        release.set()
        self.assertTrue(finished.wait(1))
        time.sleep(0.05)
        self.assertEqual(1, fake.universe_calls)

    def test_universe_retries_share_global_host_gate(self) -> None:
        lock = threading.Lock()

        class SharedTracker:
            def __init__(self) -> None:
                self.active = 0
                self.maximum = 0

            def enter(self) -> None:
                with lock:
                    self.active += 1
                    self.maximum = max(self.maximum, self.active)

            def leave(self) -> None:
                with lock:
                    self.active -= 1

        tracker = SharedTracker()

        class RetryingTrackedUniverse(FakeHistoricalAkshare):
            def __init__(self) -> None:
                super().__init__(
                    universe=[{"代码": "000001", "名称": "甲", "成交额": 100_000_000}],
                    histories={"000001": history_rows()},
                )
                self.universe_calls = 0

            def stock_zh_a_spot_em(self) -> FakeFrame:
                tracker.enter()
                try:
                    time.sleep(0.02)
                    self.universe_calls += 1
                    if self.universe_calls == 1:
                        raise ConnectionError("transient")
                    return FakeFrame(self.universe)
                finally:
                    tracker.leave()

        fakes = [RetryingTrackedUniverse() for _ in range(4)]
        threads = [
            threading.Thread(
                target=load_historical_market_activity,
                args=("CN", date(2026, 7, 9)),
                kwargs={"akshare_module": fake},
            )
            for fake in fakes
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertTrue(all(fake.universe_calls == 2 for fake in fakes))
        self.assertLessEqual(tracker.maximum, 2)

    def test_universe_load_does_not_return_before_provider_finishes(self) -> None:
        release = threading.Event()
        finished = threading.Event()

        class BlockingUniverse(FakeHistoricalAkshare):
            def stock_zh_a_spot_em(self) -> FakeFrame:
                release.wait(1)
                finished.set()
                return FakeFrame(self.universe)

        fake = BlockingUniverse(universe=[], histories={})
        timer = threading.Timer(0.2, release.set)
        timer.daemon = True
        timer.start()
        started = time.monotonic()
        result = load_historical_market_activity(
            "CN", date(2026, 7, 9), akshare_module=fake, timeout_seconds=0.05
        )
        elapsed = time.monotonic() - started

        self.assertGreaterEqual(elapsed, 0.18)
        self.assertTrue(finished.is_set())
        self.assertEqual("timed_out", result.source_status["gainers"]["status"])
        self.assertEqual(0, result.source_status["gainers"]["requested"])
        self.assertEqual(0, result.source_status["gainers"]["queried"])

    def test_deadline_prevents_new_requests_after_blocking_provider_finishes(self) -> None:
        release = threading.Event()
        finished = threading.Event()
        lock = threading.Lock()

        class BlockingHistory(FakeHistoricalAkshare):
            def __init__(self) -> None:
                super().__init__(
                    universe=[
                        {"代码": f"{index:06d}", "名称": f"样本{index}", "成交额": 100_000_000}
                        for index in range(8)
                    ],
                    histories={},
                )
                self.active = 0

            def stock_zh_a_hist(
                self,
                symbol: str,
                period: str,
                start_date: str,
                end_date: str,
                adjust: str,
                timeout: float | None = None,
            ) -> FakeFrame:
                with lock:
                    self.history_calls.append(("stock_zh_a_hist", {"symbol": symbol, "timeout": timeout}))
                    self.active += 1
                release.wait(1)
                with lock:
                    self.active -= 1
                    if self.active == 0:
                        finished.set()
                return FakeFrame(history_rows())

        fake = BlockingHistory()
        timer = threading.Timer(0.12, release.set)
        timer.daemon = True
        timer.start()
        started = time.monotonic()
        result = load_historical_market_activity(
            "CN", date(2026, 7, 9), akshare_module=fake, timeout_seconds=0.08
        )
        elapsed = time.monotonic() - started

        self.assertGreaterEqual(elapsed, 0.1)
        self.assertTrue(finished.is_set())
        self.assertEqual("timed_out", result.source_status["gainers"]["status"])
        self.assertEqual(8, result.source_status["gainers"]["requested"])
        self.assertEqual(1, result.source_status["gainers"]["queried"])
        self.assertEqual(0, result.source_status["gainers"]["usable"])
        self.assertTrue(result.source_status["gainers"]["incomplete"])
        self.assertEqual(1, len(fake.history_calls))

    def test_history_provider_does_not_create_background_worker_threads(self) -> None:
        fake = FakeHistoricalAkshare(universe=[], histories={})
        for _ in range(10):
            load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake, timeout_seconds=0.02)

        workers = [thread for thread in threading.enumerate() if thread.name.startswith("daily-market-history-")]
        self.assertEqual([], workers)
        self.assertFalse(any(thread.name.startswith("ThreadPoolExecutor") for thread in threading.enumerate()))

    def test_global_host_gate_limits_concurrent_invocations_to_two(self) -> None:
        lock = threading.Lock()

        class TrackingAkshare(FakeHistoricalAkshare):
            def __init__(self) -> None:
                super().__init__(
                    universe=[{"代码": "000001", "名称": "甲", "成交额": 100_000_000}],
                    histories={"000001": history_rows()},
                )
                self.active = 0
                self.maximum = 0

            def _tracked(self, callback):
                with lock:
                    self.active += 1
                    self.maximum = max(self.maximum, self.active)
                try:
                    time.sleep(0.03)
                    return callback()
                finally:
                    with lock:
                        self.active -= 1

            def stock_zh_a_spot_em(self) -> FakeFrame:
                return self._tracked(lambda: FakeFrame(self.universe))

            def stock_zh_a_hist(
                self,
                symbol: str,
                period: str,
                start_date: str,
                end_date: str,
                adjust: str,
                timeout: float | None = None,
            ) -> FakeFrame:
                return self._tracked(lambda: FakeFrame(self.histories[symbol]))

        fake = TrackingAkshare()
        threads = [
            threading.Thread(
                target=load_historical_market_activity,
                args=("CN", date(2026, 7, 9)),
                kwargs={"akshare_module": fake},
            )
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertLessEqual(fake.maximum, 2)

    def test_transient_history_failure_retries_once(self) -> None:
        class RetryingAkshare(FakeHistoricalAkshare):
            def stock_zh_a_hist(
                self,
                symbol: str,
                period: str,
                start_date: str,
                end_date: str,
                adjust: str,
                timeout: float | None = None,
            ) -> FakeFrame:
                self.history_calls.append(("stock_zh_a_hist", {"symbol": symbol, "timeout": timeout}))
                if len(self.history_calls) == 1:
                    raise ConnectionError("transient")
                return FakeFrame(self.histories[symbol])

        fake = RetryingAkshare(
            universe=[{"代码": "000001", "名称": "甲", "成交额": 100_000_000}],
            histories={"000001": history_rows()},
        )

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake, max_workers=1)

        self.assertEqual(2, len(fake.history_calls))
        self.assertEqual(1, result.source_status["gainers"]["queried"])
        self.assertEqual(1, result.source_status["gainers"]["usable"])

    def test_current_universe_is_capped_at_top_200_by_turnover(self) -> None:
        universe = [
            {"代码": f"{index:06d}", "名称": f"样本{index}", "成交额": index}
            for index in range(205)
        ]
        fake = FakeHistoricalAkshare(
            universe=universe,
            histories={row["代码"]: history_rows() for row in universe},
        )

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake)

        requested_codes = {str(call[1]["symbol"]) for call in fake.history_calls}
        self.assertEqual(200, result.source_status["gainers"]["requested"])
        self.assertEqual(200, result.source_status["gainers"]["queried"])
        self.assertEqual(200, len(requested_codes))
        self.assertNotIn("000000", requested_codes)
        self.assertNotIn("000001", requested_codes)
        self.assertNotIn("000002", requested_codes)
        self.assertNotIn("000003", requested_codes)
        self.assertNotIn("000004", requested_codes)

    def test_non_finite_values_are_rejected_and_result_is_strict_json(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[
                {"代码": "000001", "名称": "甲", "成交额": float("nan")},
                {"代码": "000002", "名称": "乙", "成交额": float("inf")},
            ],
            histories={
                "000001": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 100_000_000},
                    {"日期": "2026-07-09", "收盘": float("inf"), "成交额": 100_000_000},
                ],
                "000002": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 100_000_000},
                    {"日期": "2026-07-09", "收盘": 11, "成交额": float("nan")},
                ],
            },
        )

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake)

        self.assertEqual([], result.gainers)
        json.dumps(result.as_dict(), allow_nan=False)

    def test_history_window_covers_prior_session_across_golden_week(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[{"代码": "000001", "名称": "甲", "成交额": 100_000_000}],
            histories={
                "000001": history_rows(
                    previous_date="2026-09-30", market_date="2026-10-09", turnover=100_000_000
                )
            },
        )

        result = load_historical_market_activity("CN", date(2026, 10, 9), akshare_module=fake, max_workers=1)

        self.assertEqual("000001", result.gainers[0]["code"])
        self.assertEqual("20260904", fake.history_calls[0][1]["start_date"])

    def test_historical_candidates_require_current_market_cap_and_common_equity(self) -> None:
        cases = (
            ("CN", 3_500_000_000, 50_000_000, "000001", "示例股份", "Total Market Value"),
            ("HK", 4_000_000_000, 20_000_000, "00700", "Example Holdings", "Market Cap"),
            ("US", 500_000_000, 10_000_000, "106.DOW", "Dow Inc", "总市值"),
        )

        for market, min_market_cap, turnover, ordinary_code, ordinary_name, market_cap_key in cases:
            missing_cap_code = f"{market}.NOCAP"
            low_cap_code = f"{market}.LOWCAP"
            invalid_cap_code = f"{market}.INVALIDCAP"
            nan_cap_code = f"{market}.NANCAP"
            non_common_code = "106.TESTW" if market == "US" else f"{market}.ETF"
            fake = FakeHistoricalAkshare(
                universe=[
                    {
                        "代码": ordinary_code,
                        "名称": ordinary_name,
                        "成交额": turnover,
                        market_cap_key: min_market_cap,
                    },
                    {"代码": missing_cap_code, "名称": "Missing Cap Company", "成交额": turnover},
                    {
                        "代码": low_cap_code,
                        "名称": "Low Cap Company",
                        "成交额": turnover,
                        "Market Cap": min_market_cap - 1,
                    },
                    {
                        "代码": invalid_cap_code,
                        "名称": "Invalid Cap Company",
                        "成交额": turnover,
                        "Market Cap": "invalid",
                    },
                    {
                        "代码": nan_cap_code,
                        "名称": "NaN Cap Company",
                        "成交额": turnover,
                        "Market Cap": "NaN",
                    },
                    {
                        "代码": non_common_code,
                        "名称": "Leveraged ETF" if market != "US" else "Example Holdings",
                        "成交额": turnover,
                        "Market Cap": min_market_cap * 2,
                    },
                ],
                histories={
                    ordinary_code: [
                        {"日期": "2026-07-08", "收盘": 10, "成交额": turnover},
                        {"日期": "2026-07-09", "收盘": 25, "成交额": turnover},
                    ],
                    missing_cap_code: history_rows(turnover=turnover),
                    low_cap_code: history_rows(turnover=turnover),
                    invalid_cap_code: history_rows(turnover=turnover),
                    nan_cap_code: history_rows(turnover=turnover),
                    non_common_code: history_rows(turnover=turnover),
                },
                market_cap_default=None,
            )

            result = load_historical_market_activity(market, date(2026, 7, 9), akshare_module=fake)

            self.assertEqual([ordinary_code], [row["code"] for row in result.gainers])
            self.assertEqual(150.0, result.gainers[0]["change_pct"])
            self.assertEqual(float(turnover), result.gainers[0]["turnover"])
            self.assertEqual(float(min_market_cap), result.gainers[0]["current_market_cap"])
            self.assertEqual([ordinary_code], [call[1]["symbol"] for call in fake.history_calls])
            self.assertEqual("current_liquid_common_equity_market_cap_top_200", result.source_status["gainers"]["universe_basis"])
            self.assertIn("current_market_cap_min_", result.gainers[0]["metric"])
            self.assertIn("current spot market capitalization", result.source_status["gainers"]["message"].lower())

    def test_historical_candidates_reject_non_common_security_types_before_history_query(self) -> None:
        type_labels = ("Warrant", "Right", "Unit", "Preferred", "ETF", "ETN", "Fund", "Leveraged", "Inverse")
        typed_codes = [f"105.TYPE{index:02d}" for index in range(1, len(type_labels) + 1)]
        fake = FakeHistoricalAkshare(
            universe=[
                {"代码": "106.DOW", "名称": "Dow Inc", "成交额": 20_000_000, "总市值": 1_000_000_000},
                *[
                    {
                        "代码": code,
                        "名称": "Example Holdings",
                        "成交额": 20_000_000,
                        "总市值": 1_000_000_000,
                        "证券类型": type_label,
                    }
                    for code, type_label in zip(typed_codes, type_labels)
                ],
            ],
            histories={
                "106.DOW": history_rows(turnover=20_000_000),
                **{code: history_rows(turnover=20_000_000) for code in typed_codes},
            },
        )

        result = load_historical_market_activity("US", date(2026, 7, 9), akshare_module=fake)

        self.assertEqual(["106.DOW"], [row["code"] for row in result.gainers])
        self.assertEqual(["106.DOW"], [call[1]["symbol"] for call in fake.history_calls])

    def test_dow_is_eligible_while_warrant_metadata_is_excluded(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[
                {"代码": "106.DOW", "名称": "Dow Inc", "成交额": 20_000_000},
                {
                    "代码": "105.TEST1",
                    "名称": "Example Holdings",
                    "成交额": 30_000_000,
                    "证券类型": "Warrant",
                },
            ],
            histories={
                "106.DOW": history_rows(turnover=20_000_000),
                "105.TEST1": history_rows(turnover=30_000_000),
            },
        )

        result = load_historical_market_activity("US", date(2026, 7, 9), akshare_module=fake)

        self.assertEqual(["106.DOW"], [row["code"] for row in result.gainers])
        self.assertEqual(["106.DOW"], [call[1]["symbol"] for call in fake.history_calls])

    def test_us_uses_provider_symbol_and_keeps_sections_explicitly_unavailable(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[{"代码": "105.MSFT", "名称": "Microsoft", "成交额": 20_000_000}],
            histories={"105.MSFT": history_rows(turnover=20_000_000)},
        )

        result = load_historical_market_activity("US", date(2026, 7, 9), akshare_module=fake, max_workers=1)

        self.assertEqual("105.MSFT", result.gainers[0]["code"])
        self.assertEqual("105.MSFT", fake.history_calls[0][1]["symbol"])
        self.assertEqual("historical_not_supported", result.source_status["sectors"]["status"])
        self.assertEqual("historical_not_supported", result.source_status["capital_flow"]["status"])

    def test_hk_keeps_historical_sections_explicitly_unavailable(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[{"代码": "00700", "名称": "Tencent", "成交额": 30_000_000}],
            histories={"00700": history_rows(turnover=30_000_000)},
        )

        result = load_historical_market_activity("HK", date(2026, 7, 9), akshare_module=fake, max_workers=1)

        self.assertEqual("stock_hk_hist", fake.history_calls[0][0])
        self.assertEqual("historical_not_supported", result.source_status["sectors"]["status"])
        self.assertEqual("historical_not_supported", result.source_status["capital_flow"]["status"])

    def test_pre_cancelled_provider_stops_before_any_external_call(self) -> None:
        fake = SequencedUniverseAkshare(outcomes=[[]])
        cancel = threading.Event()
        cancel.set()

        with self.assertRaises(HistoricalActivityCancelled):
            load_historical_market_activity(
                "CN",
                date(2026, 7, 9),
                akshare_module=fake,
                cancel_event=cancel,
            )

        self.assertEqual(0, fake.universe_calls)
        self.assertEqual([], fake.history_calls)

    def test_cancellation_stops_before_submitting_the_next_symbol(self) -> None:
        cancel = threading.Event()

        class CancellingAkshare(FakeHistoricalAkshare):
            def _history(self, method: str, **kwargs: object) -> FakeFrame:
                result = super()._history(method, **kwargs)
                cancel.set()
                return result

        fake = CancellingAkshare(
            universe=[
                {"代码": "000001", "名称": "甲", "成交额": 200_000_000},
                {"代码": "000002", "名称": "乙", "成交额": 100_000_000},
            ],
            histories={"000001": history_rows(), "000002": history_rows()},
        )

        with self.assertRaises(HistoricalActivityCancelled):
            load_historical_market_activity(
                "CN",
                date(2026, 7, 9),
                akshare_module=fake,
                max_workers=1,
                cancel_event=cancel,
            )

        self.assertEqual(1, len(fake.history_calls))


if __name__ == "__main__":
    unittest.main()
