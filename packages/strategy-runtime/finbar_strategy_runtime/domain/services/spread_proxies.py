"""Spread proxy estimators from OHLCV data.

All functions are pure (stateless) and operate on pandas DataFrames/Series.
No framework dependencies, no I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Corwin-Schultz (2012) spread
# ---------------------------------------------------------------------------


def corwin_schultz_spread(
    ohlc: pd.DataFrame,
    lookback: int = 20,
    overnight_adjust: bool = True,
) -> pd.Series:
    """Estimate bid-ask spread from daily OHLC data.

    Corwin & Schultz (2012): 'A Simple Way to Estimate Bid-Ask Spreads from
    Daily High and Low Prices.'  JF 67(2), 719-760.

    Args:
        ohlc: DataFrame with 'open', 'high', 'low', 'close' columns.
        lookback: Rolling window for beta/gamma estimation.
        overnight_adjust: Whether to adjust for overnight return component.

    Returns:
        Series of spread estimates (same index as input). NaN for
        insufficient data.
    """
    if len(ohlc) < lookback:
        return pd.Series(np.nan, index=ohlc.index)

    high = ohlc["high"].astype(float)
    low = ohlc["low"].astype(float)
    close = ohlc["close"].astype(float)

    # Day t: log(H_t / L_t)^2
    beta = np.log(high / low) ** 2
    # Day t+1: log(H_{t+1} / L_{t+1})^2
    beta_next = beta.shift(-1)

    # Two-day: log(H_{t,t+1} / L_{t,t+1})^2
    high_2d = high.rolling(2).max()
    low_2d = low.rolling(2).min()
    gamma = np.log(high_2d / low_2d) ** 2

    # Rolling means over lookback windows
    beta_mean = beta.rolling(lookback).mean()
    gamma_mean = gamma.rolling(lookback).mean()

    # alpha = (sqrt(2*beta) - sqrt(beta)) / (3 - 2*sqrt(2))  -  sqrt(gamma / (3 - 2*sqrt(2)))
    # Simplified: spread = 2 * (exp(alpha) - 1) / (1 + exp(alpha))
    sqrt2 = np.sqrt(2)
    denom = 3.0 - 2.0 * sqrt2

    alpha = (
        (np.sqrt(2.0 * beta_mean) - np.sqrt(beta_mean)) / denom
        - np.sqrt(gamma_mean / denom)
    )

    # Prevent negative alpha (can happen with noisy data)
    alpha = alpha.clip(lower=0)

    spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))

    if overnight_adjust:
        # Overnight gap adjustment
        overnight_ret = np.log(ohlc["open"].astype(float) / close.shift(1))
        gamma_o = overnight_ret**2
        gamma_o_mean = gamma_o.rolling(lookback).mean()
        alpha -= np.sqrt(gamma_o_mean / denom)
        alpha = alpha.clip(lower=0)
        spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))

    return spread


# ---------------------------------------------------------------------------
# Roll (1984) spread
# ---------------------------------------------------------------------------


def roll_spread(
    close: pd.Series,
    lookback: int = 20,
) -> float | None:
    """Estimate effective spread from serial covariance of price changes.

    Roll (1984): 'A Simple Implicit Measure of the Effective Bid-Ask Spread
    in an Efficient Market.'  JF 39(4), 1127-1139.

    Args:
        close: Series of closing prices.
        lookback: Rolling window for covariance estimation.

    Returns:
        Scalar spread estimate, or None if insufficient data.
    """
    if len(close) < lookback:
        return None

    ret = close.pct_change().dropna()
    if len(ret) < 2:
        return None

    # Serial covariance of returns
    cov = ret.rolling(lookback - 1).apply(
        lambda x: np.cov(x[:-1], x[1:])[0, 1] if len(x) >= 2 else np.nan,
        raw=False,
    )

    last_cov = cov.iloc[-1]
    if pd.isna(last_cov):
        return None

    # Spread = 2 * sqrt(-cov) when cov < 0
    if last_cov < 0:
        return 2.0 * np.sqrt(-last_cov)
    return 0.0


# ---------------------------------------------------------------------------
# Abdi-Ranaldo (2017) spread
# ---------------------------------------------------------------------------


def abdi_ranaldo_spread(
    ohlc: pd.DataFrame,
    lookback: int = 20,
) -> pd.Series:
    """Estimate spread from mid-price and close.

    Abdi & Ranaldo (2017): 'A Simple Estimation of Bid-Ask Spreads from
    Daily Close, High, and Low Prices.'  RFS 30(12), 4437-4480.

    Args:
        ohlc: DataFrame with 'open', 'high', 'low', 'close' columns.
        lookback: Rolling window.

    Returns:
        Series of spread estimates.
    """
    if len(ohlc) < lookback:
        return pd.Series(np.nan, index=ohlc.index)

    high = ohlc["high"].astype(float)
    low = ohlc["low"].astype(float)
    close = ohlc["close"].astype(float)

    # Mid-range = (H + L) / 2
    mid = (high + low) / 2.0
    # Efficient price proxy η_t = close_t - mid_t
    eta = close - mid

    # Covariance of η_t and η_{t-1}
    eta_t = eta.iloc[1:].reset_index(drop=True)
    eta_tm1 = eta.iloc[:-1].reset_index(drop=True)
    common_idx = min(len(eta_t), len(eta_tm1))

    if common_idx < lookback:
        return pd.Series(np.nan, index=ohlc.index)

    # Rolling covariance
    cov_series = pd.Series(np.nan, index=ohlc.index)
    for i in range(lookback - 1, common_idx):
        cov = np.cov(eta_tm1.iloc[i - lookback + 1 : i + 1], eta_t.iloc[i - lookback + 1 : i + 1])[0, 1]
        cov_series.iloc[i + 1] = cov  # offset for alignment

    # Spread = 2 * sqrt(-cov) when cov < 0
    result = pd.Series(np.nan, index=ohlc.index)
    for i in range(len(result)):
        c = cov_series.iloc[i]
        if pd.notna(c) and c < 0:
            result.iloc[i] = 2.0 * np.sqrt(-c)
        elif pd.notna(c):
            result.iloc[i] = 0.0

    return result
