"""RuleBasedStrategy — executes user-defined rule-based strategy definitions.

Implements the TradingStrategy(ABC) domain interface. Reads a
StrategyDefinition at runtime and evaluates entry/exit rules against
each bar. Supports cross-indicator comparisons and crossover detection.

This enables the AI to define strategies via MCP without writing Python.
"""

from __future__ import annotations

import logging

from finbar.core.domain.entities.signal_result import SignalResult
from finbar.core.domain.entities.strategy_definition import (
    Rule,
    StrategyDefinition,
)
from finbar.core.domain.entities.strategy_meta import DataMode, StrategyMeta
from finbar.core.domain.interfaces.trading_strategy import TradingStrategy

logger = logging.getLogger(__name__)

# Crossover tracking: per strategy instance, track previous bar values
# for indicators that use "crosses_above" / "crosses_below".
_PREV_VALUES: dict[int, dict[str, float]] = {}


class RuleBasedStrategy(TradingStrategy):
    """Executes a user-defined StrategyDefinition rule-by-rule.

    Entry rules use AND logic (all must pass) by default.
    Exit rules use OR logic (any triggers exit).
    Supports stop-loss and take-profit via ATR multiples.
    """

    def __init__(self, definition: StrategyDefinition):
        """Initialise with a StrategyDefinition.

        Args:
            definition: The user-defined strategy to execute.
        """
        self._def = definition
        self._id = id(self)

    def meta(self) -> StrategyMeta:
        """Return metadata from the stored definition."""
        indicators: list[str] = []
        for rule in self._def.entry_rules + self._def.exit_rules:
            if rule.indicator not in indicators:
                indicators.append(rule.indicator)
        # Always include ATR if stop/target is set
        if self._def.stop_loss_atr_mult > 0 or self._def.take_profit_atr_mult > 0:
            if "atr" not in indicators:
                indicators.append("atr")

        return StrategyMeta(
            name=self._def.name,
            variant=DataMode.REAL,
            description=self._def.description,
            required_indicators=indicators,
            params={"definition": self._def.name},
        )

    def on_bar(self, bar: dict, position: dict) -> SignalResult:
        """Evaluate rules against one bar.

        Args:
            bar: Bar dict with OHLCV + indicator columns.
            position: Current position state.

        Returns:
            SignalResult with buy/sell/hold + optional stop/target.
        """
        pos_size = position.get("size", 0)

        # If in position, check exit rules
        if pos_size != 0:
            if self._should_exit(bar, position):
                return SignalResult(
                    action="sell",
                    direction="exit",
                    confidence=0.8,
                )
            return SignalResult(action="hold")

        # If flat, check entry rules
        if self._should_enter(bar):
            close = bar.get("close", 0)
            atr = bar.get("atr", 0)
            stop = 0.0
            target = 0.0
            if atr > 0:
                if self._def.stop_loss_atr_mult > 0:
                    if self._def.direction == "short":
                        stop = close + atr * self._def.stop_loss_atr_mult
                    else:
                        stop = close - atr * self._def.stop_loss_atr_mult
                if self._def.take_profit_atr_mult > 0:
                    if self._def.direction == "short":
                        target = close - atr * self._def.take_profit_atr_mult
                    else:
                        target = close + atr * self._def.take_profit_atr_mult

            direction = self._def.direction if self._def.direction != "both" else "long"
            return SignalResult(
                action="buy" if direction == "long" else "sell",
                direction=direction,
                stop_price=round(stop, 2),
                target_price=round(target, 2),
                confidence=0.7,
            )

        return SignalResult(action="hold")

    def on_reset(self) -> None:
        """Reset crossover tracking for a new backtest run."""
        _PREV_VALUES.pop(self._id, None)

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    def _should_enter(self, bar: dict) -> bool:
        """Check if all entry rules pass."""
        if not self._def.entry_rules:
            return False

        results = [
            _evaluate_rule(rule, bar, self._id) for rule in self._def.entry_rules
        ]
        if self._def.require_all_entry_rules:
            return all(results)
        return any(results)

    def _should_exit(self, bar: dict, position: dict) -> bool:
        """Check if any exit rule triggers."""
        if not self._def.exit_rules:
            return False

        return any(_evaluate_rule(rule, bar, self._id) for rule in self._def.exit_rules)


# ---------------------------------------------------------------------------
# Rule evaluation engine
# ---------------------------------------------------------------------------


def _evaluate_rule(rule: Rule, bar: dict, strategy_id: int) -> bool:
    """Evaluate a single rule against a bar.

    Supports:
    - Numeric comparisons: "<", ">", "<=", ">=", "==", "!="
    - Cross-indicator comparisons (value is another indicator name)
    - Crossover detection: "crosses_above", "crosses_below"
    """
    current = _resolve_value(rule.indicator, bar)
    threshold = _resolve_value(rule.value, bar)

    if current is None:
        return False

    op = rule.operator

    if op in ("<", ">", "<=", ">=", "==", "!="):
        if threshold is None:
            return False
        return _compare(current, op, threshold)

    if op in ("crosses_above", "crosses_below"):
        if threshold is None:
            return False
        return _check_crossover(strategy_id, rule.indicator, current, op, threshold)

    logger.warning("Unknown operator '%s' in rule", op)
    return False


def _resolve_value(value: str | float | int, bar: dict) -> float | None:
    """Resolve a rule value — literal number or indicator column name."""
    if isinstance(value, (int, float)):
        return float(value)
    # String: could be an indicator name
    val = bar.get(str(value))
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            pass
    # Try parsing as a numeric string
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return None


def _compare(a: float, op: str, b: float) -> bool:
    """Compare two numeric values."""
    if op == "<":
        return a < b
    if op == ">":
        return a > b
    if op == "<=":
        return a <= b
    if op == ">=":
        return a >= b
    if op == "==":
        return abs(a - b) < 1e-9
    if op == "!=":
        return abs(a - b) >= 1e-9
    return False


def _check_crossover(
    strategy_id: int,
    indicator: str,
    current: float,
    op: str,
    threshold: float,
) -> bool:
    """Check if indicator crossed above/below threshold since last bar."""
    key = f"{indicator}"
    prev_map = _PREV_VALUES.setdefault(strategy_id, {})
    prev = prev_map.get(key)

    # Store current for next bar
    prev_map[key] = current

    if prev is None:
        return False  # First bar, no crossover possible

    if op == "crosses_above":
        return prev <= threshold and current > threshold
    if op == "crosses_below":
        return prev >= threshold and current < threshold
    return False
