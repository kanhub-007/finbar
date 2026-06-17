"""Resiliency proxy calculators from OHLCV data.

Pure (stateless) domain services.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def resiliency_autocorr(
    close: pd.Series,
    lookback: int = 20,
    lag: int = 1,
) -> float | None:
    """Resiliency via return autocorrelation.

    Resilient markets mean-revert after trades → negative autocorrelation.
    Illiquid markets have positive autocorrelation (momentum from slow
    price discovery).

    Args:
        close: Series of closing prices.
        lookback: Window for autocorrelation computation.
        lag: Autocorrelation lag.

    Returns:
        Scalar autocorrelation, or None if insufficient data.
    """
    if len(close) < lookback + lag:
        return None

    ret = close.pct_change().dropna()
    recent = ret.iloc[-lookback:]
    if len(recent) < lag + 1:
        return None

    return recent.autocorr(lag=lag)


def resiliency_spread_to_impact(
    df: pd.DataFrame,
    cs_spread_col: str | None = None,
    lookback: int = 20,
) -> pd.Series:
    """Resiliency proxy: spread / price impact.

    Higher spread relative to impact = market absorbs trades well = resilient.

    Args:
        df: DataFrame with OHLCV columns.
        cs_spread_col: Pre-computed CS spread column name.
        lookback: Window for internal spread computation.

    Returns:
        Series of resiliency values.
    """
    if len(df) < lookback:
        return pd.Series(np.nan, index=df.index)

    if cs_spread_col and cs_spread_col in df.columns:
        spread = df[cs_spread_col]
    else:
        from finbar_strategy_runtime.domain.services.spread_proxies import (
            fong_holden_tran_spread,
        )

        spread = fong_holden_tran_spread(df, lookback=lookback)

    from finbar_strategy_runtime.domain.services.liquidity_proxies import (
        amihud_illiq,
    )

    impact = amihud_illiq(df, lookback=lookback)

    return spread / (impact.replace(0, np.nan) + 1e-10)


def inverse_amihud_resiliency(
    df: pd.DataFrame,
    lookback: int = 20,
) -> pd.Series:
    """Inverse Amihud as a rough resiliency proxy.

    Higher values = more liquid/resilient to price impact.

    Args:
        df: DataFrame with 'close' and 'volume' columns.
        lookback: Rolling window.

    Returns:
        Series of resiliency values.
    """
    if len(df) < lookback:
        return pd.Series(np.nan, index=df.index)

    from finbar_strategy_runtime.domain.services.liquidity_proxies import (
        amihud_illiq,
    )

    illiq = amihud_illiq(df, lookback=lookback)
    return 1.0 / (illiq.replace(0, np.nan) + 1e-15)
