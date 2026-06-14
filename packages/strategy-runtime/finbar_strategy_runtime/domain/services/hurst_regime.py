"""Hurst exponent and fractal regime detection.

Pure (stateless) domain services.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def hurst_exponent(
    close: pd.Series,
    min_bars: int = 100,
    max_lag: int | None = None,
) -> float | None:
    """Estimate Hurst exponent via R/S analysis.

    H > 0.55 → trending (persistent)
    H ≈ 0.50 → random walk
    H < 0.45 → mean-reverting (anti-persistent)

    Args:
        close: Series of closing prices.
        min_bars: Minimum bars required.
        max_lag: Maximum lag for R/S. Defaults to min(50, len(close)//4).

    Returns:
        Hurst exponent estimate, or None if insufficient data.
    """
    if len(close) < min_bars:
        return None

    ret = close.pct_change().dropna()
    if len(ret) < min_bars:
        return None

    n = len(ret)
    if max_lag is None:
        max_lag = min(50, n // 4)
    if max_lag < 4:
        return None

    lags = range(4, max_lag + 1)
    rs_values = []

    for lag in lags:
        # Split into chunks of size `lag`
        n_chunks = n // lag
        if n_chunks < 2:
            break

        rs_chunk = []
        for c in range(n_chunks):
            chunk = ret.iloc[c * lag : (c + 1) * lag]
            if len(chunk) < lag:
                continue
            mean = chunk.mean()
            dev = chunk - mean
            cum_dev = dev.cumsum()
            r = cum_dev.max() - cum_dev.min()
            s = chunk.std()
            if s > 1e-10:
                rs_chunk.append(r / s)

        if rs_chunk:
            rs_values.append(np.mean(rs_chunk))

    if len(rs_values) < 4:
        return None

    # log(R/S) = H * log(lag) + C
    log_lags = np.log(list(lags)[: len(rs_values)])
    log_rs = np.log(rs_values)

    # Linear regression
    slope = np.polyfit(log_lags, log_rs, 1)[0]
    return float(slope)


def fractal_regime(
    close: pd.Series,
    min_bars: int = 100,
) -> str:
    """Classify market regime from Hurst exponent.

    Args:
        close: Series of closing prices.
        min_bars: Minimum bars for Hurst estimation.

    Returns:
        'TRENDING', 'RANDOM', 'MEAN_REVERTING', or 'unknown'.
    """
    h = hurst_exponent(close, min_bars=min_bars)
    if h is None:
        return "unknown"
    if h > 0.55:
        return "TRENDING"
    if h < 0.45:
        return "MEAN_REVERTING"
    return "RANDOM"
