"""Liquidity and price-impact proxy calculators from OHLCV data.

Pure (stateless) domain services.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Amihud (2002) illiquidity
# ---------------------------------------------------------------------------


def amihud_illiq(
    df: pd.DataFrame,
    lookback: int = 20,
) -> pd.Series:
    """Amihud illiquidity: average of |return| / dollar_volume.

    Amihud (2002): 'Illiquidity and Stock Returns: Cross-Section and
    Time-Series Effects.'  Journal of Financial Markets 5(1), 31-56.

    Args:
        df: DataFrame with 'close' and 'volume' columns.
        lookback: Rolling window for averaging.

    Returns:
        Series of illiquidity values. NaN where volume=0 or data insufficient.
    """
    if len(df) < lookback:
        return pd.Series(np.nan, index=df.index)

    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    ret = close.pct_change().abs()
    dollar_vol = close * volume

    # Avoid division by zero
    daily_illiq = pd.Series(np.nan, index=df.index)
    mask = dollar_vol > 0
    daily_illiq[mask] = ret[mask] / dollar_vol[mask]

    return daily_illiq.rolling(lookback).mean()


# ---------------------------------------------------------------------------
# Amivest liquidity (inverse Amihud)
# ---------------------------------------------------------------------------


def amivest_liquidity(
    df: pd.DataFrame,
    lookback: int = 20,
) -> pd.Series:
    """Amivest liquidity: average of dollar_volume / |return|.

    Inverse of Amihud — larger values = more liquid.

    Args:
        df: DataFrame with 'close' and 'volume' columns.
        lookback: Rolling window.

    Returns:
        Series of liquidity values.
    """
    if len(df) < lookback:
        return pd.Series(np.nan, index=df.index)

    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    ret = close.pct_change().abs()
    dollar_vol = close * volume

    daily_liq = pd.Series(np.nan, index=df.index)
    mask = ret > 0
    daily_liq[mask] = dollar_vol[mask] / ret[mask]

    return daily_liq.rolling(lookback).mean()


# ---------------------------------------------------------------------------
# Florackis lambda
# ---------------------------------------------------------------------------


def florackis_lambda(
    df: pd.DataFrame,
    lookback: int = 20,
) -> pd.Series:
    """Florackis-Gregoriou-Kostakis lambda: return-to-volume ratio.

    Florackis, Gregoriou & Kostakis (2011): 'Trading Frequency and Asset
    Pricing on the London Stock Exchange.'

    Args:
        df: DataFrame with 'close' and 'volume' columns.
        lookback: Rolling window.

    Returns:
        Series of lambda values.
    """
    if len(df) < lookback:
        return pd.Series(np.nan, index=df.index)

    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    ret = close.pct_change().abs()
    turnover = volume / volume.rolling(lookback).mean()
    turnover = turnover.replace(0, np.nan)

    daily_lambda = ret / turnover
    return daily_lambda.rolling(lookback).mean()


# ---------------------------------------------------------------------------
# Hasbrouck daily lambda
# ---------------------------------------------------------------------------


def hasbrouck_daily_lambda(
    df: pd.DataFrame,
    lookback: int = 20,
) -> pd.Series:
    """Hasbrouck daily price impact proxy.

    Hasbrouck (2009): 'Trading Costs and Returns for US Equities.'
    Lambda = |return| / sqrt(dollar_volume).

    Args:
        df: DataFrame with 'close' and 'volume' columns.
        lookback: Rolling window.

    Returns:
        Series of lambda values.
    """
    if len(df) < lookback:
        return pd.Series(np.nan, index=df.index)
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
    ret = close.pct_change().abs()
    dollar_vol = close * volume
    daily = pd.Series(np.nan, index=df.index)
    mask = dollar_vol > 0
    daily[mask] = ret[mask] / np.sqrt(dollar_vol[mask])
    return daily.rolling(lookback).mean()


# ---------------------------------------------------------------------------
# Liu illiquidity
# ---------------------------------------------------------------------------


def liu_illiq(
    volume: pd.Series,
    lookback: int = 21,
) -> float | None:
    """Liu illiquidity: proportion of zero-volume days.

    Liu (2006): 'A Liquidity-Augmented Capital Asset Pricing Model.'

    Args:
        volume: Series of volume values.
        lookback: Lookback window.

    Returns:
        Scalar proportion of zero-volume days, or None.
    """
    if len(volume) < lookback:
        return None
    recent = volume.iloc[-lookback:]
    zero_days = (recent == 0).sum()
    return zero_days / lookback


# ---------------------------------------------------------------------------
# Turnover
# ---------------------------------------------------------------------------


def turnover(
    volume: pd.Series,
    shares_outstanding: float,
) -> pd.Series:
    """Daily turnover: volume / shares_outstanding.

    Args:
        volume: Series of volume values.
        shares_outstanding: Total shares outstanding (constant).

    Returns:
        Series of turnover ratios.
    """
    if shares_outstanding <= 0:
        return pd.Series(np.nan, index=volume.index)
    return volume.astype(float) / shares_outstanding


# ---------------------------------------------------------------------------
# Bao-Pan-Zhou cost
# ---------------------------------------------------------------------------


def bao_pan_zhou_cost(
    close: pd.Series,
    lookback: int = 20,
) -> float | None:
    """Bao-Pan-Zhou trading cost proxy from return reversal.

    BPZ (2011): 'The Volcker Rule and Market-Making in Times of Stress.'
    Cost = -Cov(r_t, r_{t-1}) when negative.

    Args:
        close: Series of closing prices.
        lookback: Lookback window.

    Returns:
        Scalar cost estimate, or None.
    """
    if len(close) < lookback:
        return None
    ret = close.pct_change().dropna()
    recent = ret.iloc[-lookback:]
    if len(recent) < 2:
        return None
    cov = np.cov(recent.iloc[:-1], recent.iloc[1:])[0, 1]
    if cov < 0:
        return -cov
    return 0.0
