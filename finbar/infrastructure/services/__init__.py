"""Infrastructure services — concrete implementations of domain interfaces.

Includes data fetchers, rate limiters, indicator calculators, and
backtest engines.
"""

__all__ = [
    "BacktestRunner",
    "PandasTaIndicatorCalculator",
]


def __getattr__(name: str):
    """Lazily import optional infrastructure services on demand."""
    if name == "BacktestRunner":
        from finbar.infrastructure.services.backtest_runner import BacktestRunner

        return BacktestRunner
    if name == "PandasTaIndicatorCalculator":
        from finbar.infrastructure.services.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        return PandasTaIndicatorCalculator
    raise AttributeError(name)
