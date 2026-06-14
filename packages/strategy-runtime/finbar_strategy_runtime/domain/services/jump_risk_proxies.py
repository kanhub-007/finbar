"""Jump and tail-risk proxy calculators from OHLCV data.

Pure (stateless) domain services.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def jump_gap_proxy(
    ohlc: pd.DataFrame,
    lookback: int = 20,
) -> pd.Series:
    """Jump gap proxy: absolute overnight gap relative to rolling range.

    Args:
        ohlc: DataFrame with 'open', 'high', 'low', 'close' columns.
        lookback: Window for rolling average range.

    Returns:
        Series of gap ratios (positive).
    """
    if len(ohlc) < lookback:
        return pd.Series(np.nan, index=ohlc.index)

    open_ = ohlc["open"].astype(float)
    close = ohlc["close"].astype(float)
    high = ohlc["high"].astype(float)
    low = ohlc["low"].astype(float)

    # Overnight gap: |open_t - close_{t-1}|
    gap = (open_ - close.shift(1)).abs()

    # Rolling average range
    avg_range = (high - low).rolling(lookback).mean()

    result = gap / avg_range.replace(0, np.nan)
    result.iloc[:lookback] = np.nan
    return result


def extreme_return_flag(
    close: pd.Series,
    lookback: int = 20,
    n_sigma: float = 3.0,
) -> pd.Series:
    """Flag bars where return exceeds n_sigma from rolling mean.

    Args:
        close: Series of closing prices.
        lookback: Rolling window for mean and std.
        n_sigma: Number of standard deviations for the threshold.

    Returns:
        Boolean Series (True = extreme return).
    """
    if len(close) < lookback + 1:
        return pd.Series(False, index=close.index)

    ret = close.pct_change()
    mean = ret.rolling(lookback).mean()
    std = ret.rolling(lookback).std()

    upper = mean + n_sigma * std
    lower = mean - n_sigma * std

    return (ret > upper) | (ret < lower)


def cc_rs_jump_proxy(
    ohlc: pd.DataFrame,
    lookback: int = 20,
    threshold: float = 2.5,
) -> pd.Series:
    """Corsi-Reno style jump proxy from OHLC range.

    Compares current range to rolling average range. Flags jumps when
    range exceeds threshold * rolling_median(range).

    Args:
        ohlc: DataFrame with 'high' and 'low' columns.
        lookback: Rolling window for median range.
        threshold: Multiplier for jump detection.

    Returns:
        Boolean Series (True = probable jump).
    """
    if len(ohlc) < lookback:
        return pd.Series(False, index=ohlc.index)

    high = ohlc["high"].astype(float)
    low = ohlc["low"].astype(float)
    rng = high - low

    median_range = rng.rolling(lookback).median()
    return rng > threshold * median_range


def overnight_gap_proxy(
    ohlc: pd.DataFrame,
    lookback: int = 20,
) -> pd.Series:
    """Overnight gap magnitude as fraction of daily range.

    Args:
        ohlc: DataFrame with 'open', 'high', 'low', 'close' columns.
        lookback: Rolling window for smoothing.

    Returns:
        Series of gap fractions (0 to 1 typically, can exceed 1).
    """
    if len(ohlc) < 2:
        return pd.Series(np.nan, index=ohlc.index)

    open_ = ohlc["open"].astype(float)
    close = ohlc["close"].astype(float)
    high = ohlc["high"].astype(float)
    low = ohlc["low"].astype(float)

    overnight_ret = (open_ - close.shift(1)) / close.shift(1)
    daily_range = (high - low) / close

    gap_ratio = (overnight_ret.abs() / daily_range.replace(0, np.nan)).abs()
    return gap_ratio.rolling(lookback).mean()
