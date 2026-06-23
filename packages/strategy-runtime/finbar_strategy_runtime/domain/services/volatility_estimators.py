"""Volatility estimators from OHLCV data.

Pure (stateless) domain services — no framework dependencies.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Close-to-close (naive)
# ---------------------------------------------------------------------------


def close_to_close_vol(
    close: pd.Series,
    lookback: int = 20,
    annualize: bool = False,
    trading_days: int = 252,
) -> pd.Series:
    """Naive close-to-close return volatility.

    Args:
        close: Series of closing prices.
        lookback: Rolling window for std dev.
        annualize: If True, multiply by sqrt(trading_days).
        trading_days: Days per year for annualization.

    Returns:
        Series of volatility estimates (std dev of returns).
    """
    if len(close) < lookback:
        return pd.Series(np.nan, index=close.index)

    ret = close.pct_change()
    vol = ret.rolling(lookback).std()

    if annualize:
        vol *= np.sqrt(trading_days)

    return vol


# ---------------------------------------------------------------------------
# Parkinson (1980)
# ---------------------------------------------------------------------------


def parkinson_vol(
    high: pd.Series,
    low: pd.Series,
    lookback: int = 20,
    annualize: bool = False,
    trading_days: int = 252,
) -> pd.Series:
    """Parkinson high-low range volatility estimator.

    Parkinson (1980): 'The Extreme Value Method for Estimating the Variance
    of the Rate of Return.'  Journal of Business 53(1), 61-65.

    Args:
        high: Series of high prices.
        low: Series of low prices.
        lookback: Rolling window.
        annualize: If True, multiply by sqrt(trading_days).

    Returns:
        Series of volatility estimates.
    """
    if len(high) < lookback:
        return pd.Series(np.nan, index=high.index)

    # σ² = (1 / (4 * ln(2))) * mean(log(H/L)²)
    factor = 1.0 / (4.0 * np.log(2.0))
    hl_sq = np.log(high / low) ** 2
    var = factor * hl_sq.rolling(lookback).mean()
    vol = np.sqrt(var)

    if annualize:
        vol *= np.sqrt(trading_days)

    return vol


# ---------------------------------------------------------------------------
# Garman-Klass (1980)
# ---------------------------------------------------------------------------


def garman_klass_vol(
    ohlc: pd.DataFrame,
    lookback: int = 20,
    annualize: bool = False,
    trading_days: int = 252,
) -> pd.Series:
    """Garman-Klass OHLC volatility estimator.

    Garman & Klass (1980): 'On the Estimation of Security Price Volatilities
    from Historical Data.'  Journal of Business 53(1), 67-78.

    Args:
        ohlc: DataFrame with 'open', 'high', 'low', 'close' columns.
        lookback: Rolling window.
        annualize: If True, multiply by sqrt(trading_days).

    Returns:
        Series of volatility estimates.
    """
    if len(ohlc) < lookback:
        return pd.Series(np.nan, index=ohlc.index)

    open_ = ohlc["open"].astype(float)
    high = ohlc["high"].astype(float)
    low = ohlc["low"].astype(float)
    close = ohlc["close"].astype(float)

    log_ho = np.log(high / open_)
    log_lo = np.log(low / open_)
    log_co = np.log(close / open_)

    # GK variance: 0.5 * log(H/L)² - (2*log(2) - 1) * log(C/O)²
    term1 = 0.5 * np.log(high / low) ** 2
    term2 = (2.0 * np.log(2.0) - 1.0) * log_co**2
    var = term1 - term2
    var = var.clip(lower=0)
    vol = np.sqrt(var.rolling(lookback).mean())

    if annualize:
        vol *= np.sqrt(trading_days)

    return vol


# ---------------------------------------------------------------------------
# Rogers-Satchell (1991)
# ---------------------------------------------------------------------------


def rogers_satchell_vol(
    ohlc: pd.DataFrame,
    lookback: int = 20,
    annualize: bool = False,
    trading_days: int = 252,
) -> pd.Series:
    """Rogers-Satchell OHLC volatility estimator (drift-independent).

    Rogers & Satchell (1991): 'Estimating Variance from High, Low and
    Closing Prices.'  Journal of Applied Probability 23.

    Args:
        ohlc: DataFrame with 'open', 'high', 'low', 'close' columns.
        lookback: Rolling window.
        annualize: If True, multiply by sqrt(trading_days).

    Returns:
        Series of volatility estimates.
    """
    if len(ohlc) < lookback:
        return pd.Series(np.nan, index=ohlc.index)

    high = ohlc["high"].astype(float)
    low = ohlc["low"].astype(float)
    open_ = ohlc["open"].astype(float)
    close = ohlc["close"].astype(float)

    # RS variance: log(H/C)*log(H/O) + log(L/C)*log(L/O)
    var = (
        np.log(high / close) * np.log(high / open_)
        + np.log(low / close) * np.log(low / open_)
    )
    var = var.clip(lower=0)
    vol = np.sqrt(var.rolling(lookback).mean())

    if annualize:
        vol *= np.sqrt(trading_days)

    return vol


# ---------------------------------------------------------------------------
# Yang-Zhang (2000)
# ---------------------------------------------------------------------------


def yang_zhang_vol(
    ohlc: pd.DataFrame,
    lookback: int = 20,
    annualize: bool = False,
    trading_days: int = 252,
) -> pd.Series:
    """Yang-Zhang drift-independent OHLC volatility estimator.

    Yang & Zhang (2000): 'Drift-Independent Volatility Estimation Based on
    High, Low, Open, and Close Prices.'  Journal of Business 73(2), 477-496.

    Args:
        ohlc: DataFrame with 'open', 'high', 'low', 'close' columns.
        lookback: Rolling window.
        annualize: If True, multiply by sqrt(trading_days).

    Returns:
        Series of volatility estimates.
    """
    if len(ohlc) < lookback + 1:
        return pd.Series(np.nan, index=ohlc.index)

    open_ = ohlc["open"].astype(float)
    high = ohlc["high"].astype(float)
    low = ohlc["low"].astype(float)
    close = ohlc["close"].astype(float)

    # Overnight (close-to-open) returns
    overnight_ret = np.log(open_ / close.shift(1))
    vo = overnight_ret.rolling(lookback).var()

    # Open-to-close returns
    open_close_ret = np.log(close / open_)
    vc = open_close_ret.rolling(lookback).var()

    # Rogers-Satchell component
    rs_var = (
        np.log(high / close) * np.log(high / open_)
        + np.log(low / close) * np.log(low / open_)
    )
    rs_var = rs_var.clip(lower=0)
    vrs = rs_var.rolling(lookback).mean()

    k = 0.34 / (1.34 + (lookback + 1) / (lookback - 1))
    var = vo + k * vc + (1 - k) * vrs
    vol = np.sqrt(var.clip(lower=0))

    if annualize:
        vol *= np.sqrt(trading_days)

    return vol


# ---------------------------------------------------------------------------
# Garman-Klass + Overnight
# ---------------------------------------------------------------------------


def gk_plus_overnight_vol(
    ohlc: pd.DataFrame,
    lookback: int = 20,
    annualize: bool = False,
    trading_days: int = 252,
) -> pd.Series:
    """Garman-Klass volatility with overnight gap component."""
    if len(ohlc) < lookback:
        return pd.Series(np.nan, index=ohlc.index)
    open_ = ohlc["open"].astype(float)
    high = ohlc["high"].astype(float)
    low = ohlc["low"].astype(float)
    close = ohlc["close"].astype(float)
    term1 = 0.5 * np.log(high / low) ** 2
    term2 = (2.0 * np.log(2.0) - 1.0) * np.log(close / open_) ** 2
    gk_var = (term1 - term2).clip(lower=0)
    overnight_ret = np.log(open_ / close.shift(1))
    on_var = overnight_ret**2
    combined = gk_var + on_var
    vol = np.sqrt(combined.rolling(lookback).mean())
    if annualize:
        vol *= np.sqrt(trading_days)
    return vol


def meilijson_vol(
    ohlc: pd.DataFrame,
    lookback: int = 20,
    annualize: bool = False,
    trading_days: int = 252,
) -> pd.Series:
    """Meilijson (2009) OHLC volatility estimator."""
    if len(ohlc) < lookback:
        return pd.Series(np.nan, index=ohlc.index)
    high = ohlc["high"].astype(float)
    low = ohlc["low"].astype(float)
    close = ohlc["close"].astype(float)
    open_ = ohlc["open"].astype(float)
    hl = np.log(high / low)
    ho = np.log(high / open_)
    hc = np.log(high / close)
    lc = np.log(low / close)
    lo = np.log(low / open_)
    co = np.log(close / open_)
    var = hl * co + ho * hc + lc * lo
    var = var.clip(lower=0)
    vol = np.sqrt(var.rolling(lookback).mean())
    if annualize:
        vol *= np.sqrt(trading_days)
    return vol


def daily_return_skewness(
    close: pd.Series,
    lookback: int = 60,
) -> pd.Series:
    """Rolling skewness of daily returns."""
    if len(close) < lookback:
        return pd.Series(np.nan, index=close.index)
    return close.pct_change().rolling(lookback).skew()


def daily_return_kurtosis(
    close: pd.Series,
    lookback: int = 60,
) -> pd.Series:
    """Rolling kurtosis of daily returns (excess)."""
    if len(close) < lookback:
        return pd.Series(np.nan, index=close.index)
    return close.pct_change().rolling(lookback).kurt()
