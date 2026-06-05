"""Rule domain entity for user-defined trading strategies."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    """A single condition in a strategy's entry or exit rule set.

    Example: {"indicator": "rsi_14", "operator": "<", "value": 30}.
    """

    indicator: str
    """Indicator column name, e.g. ``rsi_14``, ``close``, or ``sma_50``."""

    operator: str
    """Comparison operator: <, >, <=, >=, ==, !=, crosses_above, crosses_below."""

    value: str | float | int
    """Threshold value, either a literal number or another indicator name."""
