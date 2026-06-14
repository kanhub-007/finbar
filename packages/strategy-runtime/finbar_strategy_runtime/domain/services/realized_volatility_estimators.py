"""Realized volatility estimators from intraday OHLCV returns.

Pure (stateless) domain services — no framework dependencies.

These metrics require intraday bar data (5min, 15min, 1h) to produce
meaningful results. On daily data they collapse to simple rolling
volatility and lose the "realized" (high-frequency) advantage.

References:
- Barndorff-Nielsen & Shephard (2004), "Power and Bipower Variation"
- Lee & Mykland (2008), "Jumps in Financial Markets"
- Amaya et al. (2015), "Does Realized Skewness Predict the Cross-Section
  of Equity Returns?"
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Log returns
# ---------------------------------------------------------------------------


def _log_returns(close: pd.Series) -> pd.Series:
    """Compute log returns, handling zero/negative prices gracefully.

    Zero or negative prices produce NaN (no crash). The ``np.errstate``
    context suppresses the RuntimeWarning that ``np.log`` emits for
    invalid inputs.
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        log_price = np.log(close.astype(float).replace(0, np.nan))
    return log_price.diff()


# ---------------------------------------------------------------------------
# Realized volatility (sum of squared returns)
# ---------------------------------------------------------------------------


def realized_volatility(
    close: pd.Series,
    window: int = 78,
) -> pd.Series:
    """Realized volatility: sqrt(sum of squared log returns) over window.

    Args:
        close: Series of closing prices (intraday bars recommended).
        window: Rolling window size (e.g. 78 = ~1 day of 5-min bars).

    Returns:
        Series of realized vol estimates. First ``window`` bars are NaN
        (the ``diff()`` in log returns adds one extra NaN at index 0).
    """
    if len(close) < window:
        return pd.Series(np.nan, index=close.index)
    rets = _log_returns(close)
    rv = rets.rolling(window).apply(lambda x: np.sqrt(np.nansum(x**2)), raw=True)
    return rv


# ---------------------------------------------------------------------------
# Bipower variation (Barndorff-Nielsen & Shephard 2004)
# ---------------------------------------------------------------------------


def bipower_variation(
    close: pd.Series,
    window: int = 78,
) -> pd.Series:
    """Bipower variation: jump-robust volatility estimator.

    BV = (pi/2) * sum(|r_i| * |r_{i-1}|) over the window.
    Unlike RV, a single jump at position k does not inflate BV[k]
    because |r_k| is multiplied by |r_{k-1}|, not |r_k|^2.

    Args:
        close: Series of closing prices.
        window: Rolling window size.

    Returns:
        Series of bipower variation estimates. First ``window`` bars are NaN.
    """
    if len(close) < window:
        return pd.Series(np.nan, index=close.index)
    rets = _log_returns(close)
    abs_r = rets.abs()
    # Cross-product: |r_i| * |r_{i-1}|
    cross = abs_r * abs_r.shift(1)
    bv = cross.rolling(window).apply(
        lambda x: (np.pi / 2) * np.nansum(x), raw=True
    )
    return bv


# ---------------------------------------------------------------------------
# Realized skewness (Amaya et al. 2015)
# ---------------------------------------------------------------------------


def realized_skewness(
    close: pd.Series,
    window: int = 78,
) -> pd.Series:
    """Realized skewness: standardized third moment of returns.

    RS = sqrt(N) * sum(r^3) / (sum(r^2))^(3/2)

    Measures asymmetry of the return distribution within the window.

    Args:
        close: Series of closing prices.
        window: Rolling window size.

    Returns:
        Series of realized skewness estimates. First ``window`` bars are NaN.
    """
    if len(close) < window:
        return pd.Series(np.nan, index=close.index)
    rets = _log_returns(close)

    def _skew(x):
        s2 = np.nansum(x**2)
        if s2 == 0:
            return 0.0
        s3 = np.nansum(x**3)
        return np.sqrt(len(x)) * s3 / (s2**1.5)

    return rets.rolling(window).apply(_skew, raw=True)


# ---------------------------------------------------------------------------
# Realized kurtosis
# ---------------------------------------------------------------------------


def realized_kurtosis(
    close: pd.Series,
    window: int = 78,
) -> pd.Series:
    """Realized kurtosis: standardized fourth moment of returns.

    RK = N * sum(r^4) / (sum(r^2))^2

    Measures tail heaviness of the return distribution.

    Args:
        close: Series of closing prices.
        window: Rolling window size.

    Returns:
        Series of realized kurtosis estimates (always >= 0).
        First ``window`` bars are NaN.
    """
    if len(close) < window:
        return pd.Series(np.nan, index=close.index)
    rets = _log_returns(close)

    def _kurt(x):
        s2 = np.nansum(x**2)
        if s2 == 0:
            return 0.0
        s4 = np.nansum(x**4)
        return len(x) * s4 / (s2**2)

    return rets.rolling(window).apply(_kurt, raw=True)


# ---------------------------------------------------------------------------
# Lee-Mykland jump detection (Lee & Mykland 2008)
# ---------------------------------------------------------------------------


def lee_mykland_jump(
    close: pd.Series,
    window: int = 78,
    threshold: float = 3.09,
) -> pd.Series:
    """Lee-Mykland jump test: flag bars with abnormally large returns.

    Standardizes each return by the rolling bipower-variance and flags
    those exceeding the threshold (default 3.09 = 99.9% normal quantile).

    The bipower variation is used for variance scaling because it is
    jump-robust: a jump at bar k does not inflate the variance estimate
    used to test bar k.

    Args:
        close: Series of closing prices.
        window: Rolling window for bipower variance estimation.
        threshold: Z-score threshold for jump flagging.

    Returns:
        Boolean Series (True = probable jump at that bar).
    """
    if len(close) < window:
        return pd.Series(False, index=close.index)

    rets = _log_returns(close)
    bv = bipower_variation(close, window=window)

    # Instantaneous variance from bipower: BV / (window-1) gives per-bar
    # variance estimate. sigma = sqrt(BV / (window-1)).
    sigma = np.sqrt(bv / (window - 1))

    # Z-score: |r_t| / sigma_t
    z = rets.abs() / sigma.replace(0, np.nan)

    return (z > threshold).fillna(False)
