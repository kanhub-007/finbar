"""JsonRuleBasedStrategy — execute validated v2 JSON strategies."""

from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_definition_v2 import StrategyDefinitionV2
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy
from finbar.infrastructure.services.json_condition_evaluator import (
    PrevValues,
    evaluate_condition_group,
)


class JsonRuleBasedStrategy(TradingStrategy):
    """TradingStrategy implementation for canonical v2 JSON definitions."""

    def __init__(self, definition: StrategyDefinitionV2):
        """Create a fresh executable strategy from a validated definition."""
        self._definition = definition
        self._previous_values: PrevValues = {}

    def meta(self) -> StrategyMeta:
        """Return metadata for the JSON strategy."""
        return StrategyMeta(
            name=self._definition.name,
            variant=DataMode.REAL,
            description=self._definition.description,
            required_indicators=[
                item.concrete_name for item in self._definition.indicators
            ],
            params=self._definition.resolved_params,
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        """Evaluate the strategy rules for one enriched OHLCV bar."""
        direction = str(position.get("direction", ""))
        size = float(position.get("size", 0) or 0)

        if size != 0:
            return self._exit_signal(bar, direction)
        return self._entry_signal(bar)

    def on_reset(self) -> None:
        """Reset crossover state before a backtest run."""
        self._previous_values.clear()

    def _entry_signal(self, bar: dict) -> SignalResult:
        for side in ("long", "short"):
            rules = self._definition.sides.get(side)
            if rules is None:
                continue
            if evaluate_condition_group(rules.entry, bar, self._previous_values):
                return SignalResult(
                    action="buy" if side == "long" else "sell",
                    direction=side,
                    confidence=rules.entry_confidence,
                )
        return SignalResult(action="hold")

    def _exit_signal(self, bar: dict, direction: str) -> SignalResult:
        rules = self._definition.sides.get(direction)
        if rules is None or rules.exit is None:
            return SignalResult(action="hold")
        if not evaluate_condition_group(rules.exit, bar, self._previous_values):
            return SignalResult(action="hold")
        return SignalResult(
            action="sell" if direction == "long" else "buy",
            direction="exit",
            confidence=rules.exit_confidence,
        )
