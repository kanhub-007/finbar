"""Informed trading proxy calculators from OHLCV data.

Pure (stateless) domain services.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def daily_vpin(
    df: pd.DataFrame,
    lookback: int = 50,
    n_buckets: int = 8,
) -> pd.Series:
    """Daily VPIN — volume-synchronized probability of informed trading.

    Easley, Lopez de Prado & O'Hara (2012): 'Flow Toxicity and Liquidity
    in a High-Frequency World.'  Review of Financial Studies.

    VPIN approximates PIN by bucketing volume into equal-sized bins and
    measuring the imbalance between buy and sell volume within each bin.

    Args:
        df: DataFrame with 'close' and 'volume' columns.
        lookback: Number of bars for rolling VPIN computation.
        n_buckets: Number of volume buckets per VPIN window.

    Returns:
        Series of VPIN values (0 to 1). NaN for insufficient data.
    """
    if len(df) < lookback:
        return pd.Series(np.nan, index=df.index)

    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    # Buy/sell classification via tick rule: up → buy, down → sell
    delta = close.diff()
    buy_vol = volume.copy()
    sell_vol = volume.copy()
    buy_vol[delta < 0] = 0.0
    sell_vol[delta > 0] = 0.0
    # Flat bars (delta == 0 or NaN): split volume 50/50 to avoid
    # double-counting (which inflates the denominator)
    flat = (delta == 0) | delta.isna()
    buy_vol[flat] = volume[flat] / 2.0
    sell_vol[flat] = volume[flat] / 2.0

    result = pd.Series(np.nan, index=df.index)

    # Vectorised rolling sums — avoids the previous O(n × lookback) loop.
    rolling_buy = buy_vol.rolling(lookback).sum()
    rolling_sell = sell_vol.rolling(lookback).sum()
    rolling_total = rolling_buy + rolling_sell

    mask = rolling_total > 0
    result[mask] = (rolling_buy[mask] - rolling_sell[mask]).abs() / rolling_total[mask]

    return result


def spread_based_pin_proxy(
    df: pd.DataFrame,
    cs_spread_col: str | None = None,
    lookback: int = 20,
) -> pd.Series:
    """Spread-based PIN proxy using Corwin-Schultz spread and price reversal.

    Derived proxy: PIN ∝ spread / (spread + reversal).

    Args:
        df: DataFrame with OHLC columns.
        cs_spread_col: Column name of pre-computed CS spread, or None to
            compute internally.
        lookback: Window for internal CS spread computation.

    Returns:
        Series of PIN proxy values.
    """
    if len(df) < lookback:
        return pd.Series(np.nan, index=df.index)

    if cs_spread_col and cs_spread_col in df.columns:
        spread = df[cs_spread_col]
    else:
        from finbar_strategy_runtime.domain.services.spread_proxies import (
            corwin_schultz_spread,
        )

        spread = corwin_schultz_spread(df, lookback=lookback)

    # Reversal proxy: negative of 1-bar return autocorrelation
    close = df["close"].astype(float)
    ret = close.pct_change()
    reversal = -ret.rolling(lookback).apply(
        lambda x: x.autocorr() if len(x) > 1 else np.nan,
        raw=False,
    )
    reversal = reversal.clip(lower=0)

    pin = spread / (spread + reversal + 1e-10)
    return pin
