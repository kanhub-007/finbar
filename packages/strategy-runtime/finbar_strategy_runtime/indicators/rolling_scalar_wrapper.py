"""Convert a scalar calculator into a per-bar Series via rolling window.

About 10 of the new metric calculators return a single scalar (not a Series):
``roll_spread``, ``liu_illiq``, ``bao_pan_zhou_cost``, ``resiliency_autocorr``,
``hurst_exponent``, ``effective_tick_spread``, ``lot_zero_return_spread``.

For a backtest, strategies need a value **per bar**. Broadcasting the scalar
as a constant is useless (the market changes over time). This wrapper applies
the scalar calculator over a trailing ``window``-bar slice at each bar,
returning a ``pd.Series`` with ``NaN`` for the warm-up period.
"""

import numpy as np
import pandas as pd


def rolling_scalar_series(
    calculator,
    close: pd.Series,
    window: int = 20,
    **kwargs,
) -> pd.Series:
    """Apply a scalar calculator over a trailing window at each bar.

    Args:
        calculator: A function returning a scalar (``float | None``)
            given a slice of ``close``.
        close: The primary input series (used for index + slicing).
        window: Trailing bar count (>= 2).
        **kwargs: Extra keyword args passed to the calculator.

    Returns:
        A ``pd.Series`` aligned to ``close.index``. The first
        ``window - 1`` bars are ``NaN`` (not enough data yet).
    """
    n = len(close)
    result = pd.Series(np.nan, index=close.index, dtype="float64")
    if window < 2:
        return result
    for i in range(window - 1, n):
        slice_ = close.iloc[i - window + 1 : i + 1]
        result.iloc[i] = _safe_scalar(calculator, slice_, **kwargs)
    return result


def _safe_scalar(calculator, slice_: pd.Series, **kwargs) -> float:
    """Call calculator, returning NaN on None / exception / non-finite."""
    try:
        value = calculator(slice_, **kwargs)
    except Exception:
        return np.nan
    if value is None:
        return np.nan
    try:
        result = float(value)
    except (TypeError, ValueError):
        return np.nan
    if np.isnan(result):
        return np.nan
    return result
