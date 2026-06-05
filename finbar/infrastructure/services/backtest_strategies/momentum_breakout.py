"""Momentum Breakout trading strategy.

Buy when price breaks above a recent high with trend alignment
(close > SMA_200). Exit on SMA crossover or stop-loss.
"""

from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy


class MomentumBreakoutStrategy(TradingStrategy):
    """Buy when close breaks above N-period high while above SMA_200.

    Sell when close drops below SMA_50 (trend broken) or hits stop.
    Uses ATR-based stop-loss for risk management.
    """

    def __init__(
        self,
        breakout_period: int = 20,
        trend_sma: int = 200,
        exit_sma: int = 50,
        stop_atr_mult: float = 2.0,
    ):
        self._breakout_period = breakout_period
        self._trend_sma = trend_sma
        self._exit_sma = exit_sma
        self._stop_atr_mult = stop_atr_mult
        self._high_history: list[float] = []

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="momentum_breakout",
            variant=DataMode.REAL,
            description=(
                f"Buy on break above {self._breakout_period}-period high "
                f"above SMA_{self._trend_sma}. Exit below "
                f"SMA_{self._exit_sma} or ATR stop."
            ),
            required_indicators=[
                f"sma_{self._trend_sma}",
                f"sma_{self._exit_sma}",
                "atr",
            ],
            params={
                "breakout_period": self._breakout_period,
                "trend_sma": self._trend_sma,
                "exit_sma": self._exit_sma,
                "stop_atr_mult": self._stop_atr_mult,
            },
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        close = bar.get("close")
        high = bar.get("high")
        trend_key = f"sma_{self._trend_sma}"
        exit_key = f"sma_{self._exit_sma}"
        atr = bar.get("atr", 0)

        if close is None or high is None:
            return SignalResult(action="hold")

        trend_sma_val = bar.get(trend_key)
        exit_sma_val = bar.get(exit_key)
        pos_size = position.get("size", 0)
        pos_dir = position.get("direction", "")

        signal = SignalResult(action="hold")

        # Exit long: close below exit SMA
        if pos_dir == "long" and exit_sma_val is not None and close < exit_sma_val:
            signal = SignalResult(
                action="sell",
                direction="exit",
                metadata={"reason": "sma_exit"},
            )
        elif pos_size == 0 and trend_sma_val is not None and close > trend_sma_val:
            signal = self._entry_signal(bar, close, atr)

        self._high_history.append(float(high))
        return signal

    def on_reset(self) -> None:
        """Reset rolling high state for a new backtest run."""
        self._high_history.clear()

    def _entry_signal(self, bar: dict, close: float, atr: float) -> SignalResult:
        """Build an entry signal when close breaks above a prior high."""
        breakout_level = bar.get(f"swing_high_{self._breakout_period}")
        confidence = 0.7
        reason = "momentum_breakout"

        if breakout_level is None and self._high_history:
            lookback = self._high_history[-self._breakout_period :]
            breakout_level = max(lookback)
            confidence = 0.5
            reason = "momentum_breakout_rolling_high"

        if breakout_level is None or close <= breakout_level:
            return SignalResult(action="hold")

        stop = close - atr * self._stop_atr_mult if atr else 0
        return SignalResult(
            action="buy",
            direction="long",
            stop_price=round(stop, 2) if stop else 0.0,
            position_size=0,
            confidence=confidence,
            metadata={"reason": reason},
        )
