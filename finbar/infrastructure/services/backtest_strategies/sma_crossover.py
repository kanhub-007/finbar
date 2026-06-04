"""SMA Crossover trading strategy.

Simple moving average crossover: buy when fast SMA crosses above slow SMA,
sell when fast SMA crosses below slow SMA.
"""

from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy


class SmaCrossoverStrategy(TradingStrategy):
    """Buy when fast SMA crosses above slow SMA, sell on opposite cross.

    Requires sma_{fast} and sma_{slow} indicator columns in bar data.
    Default: SMA 20 crosses SMA 50.
    """

    def __init__(self, fast_period: int = 20, slow_period: int = 50):
        """Initialize with configurable SMA periods.

        Args:
            fast_period: Period for the fast SMA (default 20).
            slow_period: Period for the slow SMA (default 50).
        """
        self._fast = fast_period
        self._slow = slow_period
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def meta(self) -> StrategyMeta:
        return StrategyMeta(
            name="sma_crossover",
            variant=DataMode.REAL,
            description=(
                "Buy when fast SMA crosses above slow SMA, "
                "sell on opposite cross. Classic trend-following strategy."
            ),
            required_indicators=[f"sma_{self._fast}", f"sma_{self._slow}"],
            params={"fast_period": self._fast, "slow_period": self._slow},
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        """Evaluate SMA crossover signal.

        Args:
            bar: Bar dict with sma_{fast} and sma_{slow} columns.
            position: Current position state dict.

        Returns:
            SignalResult with buy/sell/hold.
        """
        fast_key = f"sma_{self._fast}"
        slow_key = f"sma_{self._slow}"
        fast_val = bar.get(fast_key)
        slow_val = bar.get(slow_key)

        if fast_val is None or slow_val is None:
            return SignalResult(action="hold")

        # On first bar, store previous values
        if self._prev_fast is None:
            self._prev_fast = fast_val
            self._prev_slow = slow_val
            return SignalResult(action="hold")

        signal = SignalResult(action="hold")

        # Bullish crossover: fast crosses above slow
        if self._prev_fast <= self._prev_slow and fast_val > slow_val:
            if position.get("size", 0) == 0:
                signal = SignalResult(
                    action="buy",
                    direction="long",
                    confidence=0.6,
                )
            # Exit short if in short position
            elif position.get("direction") == "short":
                signal = SignalResult(
                    action="sell",
                    direction="exit",
                    confidence=0.6,
                )

        # Bearish crossover: fast crosses below slow
        elif self._prev_fast >= self._prev_slow and fast_val < slow_val:
            if position.get("direction") == "long":
                signal = SignalResult(
                    action="sell",
                    direction="exit",
                    confidence=0.6,
                )
            elif position.get("size", 0) == 0:
                signal = SignalResult(
                    action="sell",
                    direction="short",
                    confidence=0.6,
                )

        self._prev_fast = fast_val
        self._prev_slow = slow_val
        return signal

    def on_reset(self) -> None:
        """Reset internal state for a new backtest run."""
        self._prev_fast = None
        self._prev_slow = None
