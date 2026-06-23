"""Spec 2026-06-23 Scenario 9 — unknown interval annualization does not silently
compute 1d metrics.

Backtest metrics fall back to 1d (252/day) annualization for unknown intervals
with a warning. In strict mode unknown/missing interval must mark annualized
metrics as unavailable (NaN/0) and record the error.

Classical school, black-box: real BacktestRunner, real bars, non-zero-return
strategy so the annualized value clearly reveals any fallback.
"""

from __future__ import annotations

import math

import pandas as pd
from finbar_strategy_runtime.domain.entities.signal_result import SignalResult
from finbar_strategy_runtime.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar_strategy_runtime.domain.interfaces.trading_strategy import TradingStrategy

from finbar.infrastructure.services.backtest_runner import BacktestRunner


class _LongStrategy(TradingStrategy):
    """Enters a small long at bar 10 and holds to end — non-zero return."""
    def __init__(self):
        self._entered = False

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="long", variant=DataMode.REAL, description="Long hold",
            required_indicators=[],
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        if not self._entered and float(bar.get("close", 0)) > 0:
            self._entered = True
            return SignalResult(
                action="buy", direction="long", position_size=10,
                stop_price=0, target_price=0,
            )
        return SignalResult(action="hold")

    def on_reset(self) -> None:
        pass


def _bars(count: int = 80) -> list[dict]:
    """Bars with ~10% upward drift so the strategy has non-zero total return."""
    return [
        {"timestamp": f"2026-01-{(i // 24) + 1:02d}T{i % 24:02d}:00:00Z",
         "open": 100.0 + i * 0.12, "high": 101.0 + i * 0.12,
         "low": 99.0 + i * 0.12, "close": 100.5 + i * 0.12,
         "volume": 1000.0 + i}
        for i in range(count)
    ]


def _frame(bars: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(bars).set_index(
        pd.DatetimeIndex(
            pd.to_datetime([b["timestamp"] for b in bars], utc=True)
        )
    )[["open", "high", "low", "close", "volume"]]


class TestUnknownIntervalAnnualization:
    def test_unknown_interval_annualized_return_is_zero(self):
        """Unknown interval → annualized metrics set to 0, not 1d fallback."""
        result = BacktestRunner().run(_frame(_bars()), _LongStrategy(),
                                       interval="weird")
        annualized = result["annualized_return"]
        # Must not produce a misleading 1d-annualized non-zero value.
        assert annualized == 0.0 or math.isnan(float(annualized))
        assert "unknown interval" in (
            result.get("annualization_warning", "") or ""
        ).lower()

    def test_known_interval_produces_real_annualized(self):
        """Known intervals still compute real annualized metrics."""
        result = BacktestRunner().run(_frame(_bars()), _LongStrategy(),
                                       interval="1d")
        assert result["annualization_warning"] == ""
        assert result["annualization_factor"] == 252.0
        assert result["annualized_return"] != 0.0

    def test_trust_diagnostics_disclose_annualization_error(self):
        result = BacktestRunner().run(_frame(_bars()), _LongStrategy(),
                                       interval="weird")
        diag = result["trust_diagnostics"]
        assert "unknown interval" in (diag.get("annualization_warning", "") or "").lower()
