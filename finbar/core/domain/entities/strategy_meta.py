"""Metadata describing a trading strategy.

Pure dataclass — no behavior, no ORM, no framework dependencies.
"""

from dataclasses import dataclass, field

from finbar.core.domain.entities.data_mode import DataMode


@dataclass(frozen=True)
class StrategyMeta:
    """Static metadata for a trading strategy.

    Used by the backtest engine and by discovery tools to describe
    what a strategy does, what data it needs, and what parameters
    it accepts.
    """

    name: str
    """Unique strategy name, e.g. "sma_crossover"."""

    variant: DataMode
    """Whether this strategy uses proxy or real indicator data."""

    description: str
    """Human-readable one-liner describing the strategy."""

    required_indicators: list[str]
    """Indicator names this strategy needs, e.g. ["sma_20", "rsi_14"]."""

    params: dict = field(default_factory=dict)
    """Default parameter values, e.g. {"fast_period": 20, "slow_period": 50}."""
