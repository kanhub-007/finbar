"""RSI Mean Reversion trading strategy.

Buy when RSI drops below oversold threshold, sell when RSI rises above
overbought threshold. Classic mean-reversion strategy.
"""

from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy


class RsiMeanReversionStrategy(TradingStrategy):
    """Buy when RSI is oversold (< 30), sell when overbought (> 70).

    Requires the rsi_{period} indicator column in bar data.
    Default: RSI 14, thresholds 30/70.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: int = 30,
        overbought: int = 70,
    ):
        """Initialize with configurable RSI parameters.

        Args:
            rsi_period: RSI lookback period (default 14).
            oversold: Oversold threshold (default 30).
            overbought: Overbought threshold (default 70).
        """
        self._period = rsi_period
        self._oversold = oversold
        self._overbought = overbought

    @staticmethod
    def meta() -> StrategyMeta:
        return StrategyMeta(
            name="rsi_mean_reversion",
            variant=DataMode.REAL,
            description=(
                "Buy when RSI crosses below oversold threshold, "
                "sell when RSI crosses above overbought threshold. "
                "Classic mean-reversion strategy."
            ),
            required_indicators=["rsi_14"],
            params={"rsi_period": 14, "oversold": 30, "overbought": 70},
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        """Evaluate RSI mean-reversion signal.

        Args:
            bar: Bar dict with rsi_{period} column.
            position: Current position state dict.

        Returns:
            SignalResult with buy/sell/hold.
        """
        rsi_key = f"rsi_{self._period}"
        rsi_val = bar.get(rsi_key)

        if rsi_val is None:
            return SignalResult(action="hold")

        pos_size = position.get("size", 0)
        pos_dir = position.get("direction", "")

        # Entry: RSI oversold → buy
        if rsi_val < self._oversold and pos_size == 0:
            return SignalResult(
                action="buy",
                direction="long",
                confidence=0.7,
            )

        # Exit long: RSI overbought → sell
        if rsi_val > self._overbought and pos_dir == "long":
            return SignalResult(
                action="sell",
                direction="exit",
                confidence=0.7,
            )

        # Entry short: RSI overbought → sell short
        if rsi_val > self._overbought and pos_size == 0:
            return SignalResult(
                action="sell",
                direction="short",
                confidence=0.5,
            )

        # Exit short: RSI oversold → buy to cover
        if rsi_val < self._oversold and pos_dir == "short":
            return SignalResult(
                action="buy",
                direction="exit",
                confidence=0.5,
            )

        return SignalResult(action="hold")

    def on_reset(self) -> None:
        """No internal state to reset for this stateless strategy."""
        pass
