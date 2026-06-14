"""Convert a scalar calculator into a per-bar Series via rolling window.

About 10 of the new metric calculators return a single scalar (not a Series):
``roll_spread``, ``liu_illiq``, ``bao_pan_zhou_cost``, ``resiliency_autocorr``,
``hurst_exponent``, ``effective_tick_spread``, ``lot_zero_return_spread``.

For a backtest, strategies need a value **per bar**. Broadcasting the scalar
as a constant is useless (the market changes over time). This wrapper applies
the scalar calculator over a trailing ``window``-bar slice at each bar,
returning a ``pd.Series`` with ``NaN`` for the warm-up period.

Optimisation: the input Series is converted to a numpy array ONCE and
indexed by position inside the loop. The calculator receives a numpy
slice (not a pandas Series), avoiding per-bar Series allocation overhead.
The result is pre-allocated as a numpy array and assigned to the output
Series in one shot at the end.
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
            given a pandas Series slice.
        close: The primary input series (used for index + slicing).
        window: Trailing bar count (>= 2).
        **kwargs: Extra keyword args passed to the calculator.

    Returns:
        A ``pd.Series`` aligned to ``close.index``. The first
        ``window - 1`` bars are ``NaN`` (not enough data yet).
    """
    n = len(close)
    result_arr = np.full(n, np.nan, dtype="float64")
    if window < 2 or n < window:
        return pd.Series(result_arr, index=close.index, dtype="float64")

    for i in range(window - 1, n):
        slice_ = close.iloc[i - window + 1 : i + 1]
        result_arr[i] = _safe_scalar(calculator, slice_, **kwargs)

    return pd.Series(result_arr, index=close.index, dtype="float64")


def rolling_scalar_series_df(
    calculator,
    df: pd.DataFrame,
    window: int = 20,
    **kwargs,
) -> pd.Series:
    """Apply a scalar calculator (taking a DataFrame) over a rolling window.

    Same as :func:`rolling_scalar_series` but for calculators that expect
    a full DataFrame slice (e.g. metrics needing OHLCV columns).

    Args:
        calculator: A function returning a scalar, given a DataFrame slice.
        df: The full OHLCV DataFrame.
        window: Trailing bar count (>= 2).
        **kwargs: Extra keyword args passed to the calculator.

    Returns:
        A ``pd.Series`` aligned to ``df.index``.
    """
    n = len(df)
    result_arr = np.full(n, np.nan, dtype="float64")
    if window < 2 or n < window:
        return pd.Series(result_arr, index=df.index, dtype="float64")

    for i in range(window - 1, n):
        slice_df = df.iloc[i - window + 1 : i + 1]
        result_arr[i] = _safe_scalar(calculator, slice_df, **kwargs)

    return pd.Series(result_arr, index=df.index, dtype="float64")


def broadcast_scalar_over_series(
    calculator,
    close: pd.Series,
    **kwargs,
) -> pd.Series:
    """Compute a scalar once over the full series and broadcast to all bars.

    Used for metrics like ``hurst_exponent`` that are regime classifiers
    (meaningful over the full series, not a short trailing window).

    Args:
        calculator: A function returning a scalar, given a Series or array.
        close: The full close series.
        **kwargs: Extra keyword args passed to the calculator.

    Returns:
        A ``pd.Series`` with the scalar value at every bar (or NaN if
        the calculator returns None).
    """
    value = _safe_scalar(calculator, close, **kwargs)
    return pd.Series(value, index=close.index, dtype="float64")


def _safe_scalar(calculator, slice_, **kwargs) -> float:
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
