"""StrategyDefinition — user-defined trading strategy as composable rules.

Stored in SQLite, managed via MCP CRUD tools. A RuleBasedStrategy
engine reads these definitions and executes them at runtime.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rule:
    """A single condition in a strategy's entry or exit rule set.

    Example: {"indicator": "rsi_14", "operator": "<", "value": 30}
    """

    indicator: str
    """Indicator column name (e.g. "rsi_14", "close", "sma_50")."""

    operator: str
    """Comparison operator: "<", ">", "<=", ">=", "==", "!=", "crosses_above",
    "crosses_below"."""

    value: str | float | int
    """Threshold value. Can be a literal number or an indicator name
    for cross-indicator comparisons (e.g. "sma_50")."""


@dataclass(frozen=True)
class StrategyDefinition:
    """A user-defined trading strategy composed of entry and exit rules.

    Stored in the strategy_definitions SQLite table. Used by the
    RuleBasedStrategy engine to generate signals at runtime.
    """

    name: str
    """Unique strategy name (e.g. "trend_pullback")."""

    direction: str
    """Trade direction: "long", "short", or "both"."""

    description: str = ""
    """Human-readable description of the strategy."""

    entry_rules: list[Rule] = field(default_factory=list)
    """Rules that must ALL be true to enter a trade (AND logic)."""

    exit_rules: list[Rule] = field(default_factory=list)
    """Rules — if ANY is true, exit the position (OR logic)."""

    stop_loss_atr_mult: float = 0.0
    """Stop-loss as multiple of ATR (0 = no stop)."""

    take_profit_atr_mult: float = 0.0
    """Take-profit as multiple of ATR (0 = no target)."""

    require_all_entry_rules: bool = True
    """If True, ALL entry rules must pass. If False, ANY entry rule triggers."""

    created_at: str = ""
    """ISO timestamp of creation."""

    updated_at: str = ""
    """ISO timestamp of last update."""
