"""Information share proxy calculators from OHLCV data."""

from __future__ import annotations

import numpy as np
import pandas as pd


def cross_price_leadership(
    price_a: pd.Series,
    price_b: pd.Series,
    lookback: int = 60,
) -> float | None:
    """Cross-price leadership: which asset's returns lead the other's.

    Measures the sum of positive cross-lag correlations minus sum of
    negative auto-lead. Positive = A leads B, negative = B leads A.

    Args:
        price_a: Series of closing prices for asset A.
        price_b: Series of closing prices for asset B.
        lookback: Lookback window.

    Returns:
        Scalar leadership score, or None.
    """
    if len(price_a) < lookback or len(price_b) < lookback:
        return None

    ret_a = price_a.pct_change().dropna()
    ret_b = price_b.pct_change().dropna()

    min_len = min(len(ret_a), len(ret_b))
    if min_len < lookback:
        return None

    # Align to common length
    ret_a = ret_a.iloc[-min_len:]
    ret_b = ret_b.iloc[-min_len:]

    recent_a = ret_a.iloc[-lookback:]
    recent_b = ret_b.iloc[-lookback:]

    # Lead-lag correlations
    corr_a_leads_b = recent_a.iloc[:-1].corr(recent_b.iloc[1:])
    corr_b_leads_a = recent_b.iloc[:-1].corr(recent_a.iloc[1:])

    if pd.isna(corr_a_leads_b) and pd.isna(corr_b_leads_a):
        return 0.0

    return float(corr_a_leads_b - corr_b_leads_a)


def volume_weighted_is(
    volume_a: pd.Series,
    volume_b: pd.Series,
    lookback: int = 20,
) -> float | None:
    """Information share proxy: proportion of total volume in venue A.

    Args:
        volume_a: Series of volume for venue A.
        volume_b: Series of volume for venue B.
        lookback: Lookback window.

    Returns:
        Scalar IS fraction (0 to 1), or None.
    """
    if len(volume_a) < lookback or len(volume_b) < lookback:
        return None

    total_a = volume_a.iloc[-lookback:].sum()
    total_b = volume_b.iloc[-lookback:].sum()
    total = total_a + total_b

    if total <= 0:
        return None

    return float(total_a / total)


def opening_price_leadership(
    open_a: pd.Series,
    open_b: pd.Series,
    lookback: int = 60,
) -> float | None:
    """Opening price leadership: correlation of overnight gaps.

    Args:
        open_a: Series of opening prices for asset A.
        open_b: Series of opening prices for asset B.
        lookback: Lookback window.

    Returns:
        Scalar correlation, or None.
    """
    if len(open_a) < lookback or len(open_b) < lookback:
        return None

    overnight_a = open_a.pct_change().dropna()
    overnight_b = open_b.pct_change().dropna()

    min_len = min(len(overnight_a), len(overnight_b))
    if min_len < lookback:
        return None

    return float(overnight_a.iloc[-min_len:].corr(overnight_b.iloc[-min_len:]))


def daily_cross_correlation(
    close_a: pd.Series,
    close_b: pd.Series,
    lookback: int = 60,
) -> pd.Series:
    """Rolling cross-correlation of returns between two assets.

    Args:
        close_a: Series of closing prices for asset A.
        close_b: Series of closing prices for asset B.
        lookback: Rolling window.

    Returns:
        Series of correlation coefficients.
    """
    if len(close_a) < lookback or len(close_b) < lookback:
        length = min(len(close_a), len(close_b))
        return pd.Series(np.nan, index=close_a.index[:length])

    ret_a = close_a.pct_change()
    ret_b = close_b.pct_change()

    return ret_a.rolling(lookback).corr(ret_b)


def daily_beta_ols(
    asset: pd.Series,
    benchmark: pd.Series,
    lookback: int = 60,
) -> pd.Series:
    """Rolling OLS beta of asset returns on benchmark returns.

    Args:
        asset: Series of closing prices for the asset.
        benchmark: Series of closing prices for the benchmark.
        lookback: Rolling window.

    Returns:
        Series of beta values.
    """
    if len(asset) < lookback or len(benchmark) < lookback:
        length = min(len(asset), len(benchmark))
        return pd.Series(np.nan, index=asset.index[:length])

    ret_a = asset.pct_change()
    ret_b = benchmark.pct_change()

    # Rolling covariance / variance
    cov = ret_a.rolling(lookback).cov(ret_b)
    var = ret_b.rolling(lookback).var()

    return cov / var.replace(0, np.nan)
