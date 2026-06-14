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
