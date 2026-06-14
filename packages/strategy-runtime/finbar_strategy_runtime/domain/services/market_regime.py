"""Adaptive Markets regime classification from OHLCV data."""

from __future__ import annotations

import numpy as np
import pandas as pd


def market_regime(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    lookback: int = 200,
) -> pd.Series:
    """Classify market regime: TRENDING_BULL, TRENDING_BEAR, RANGE_BOUND, CRISIS.

    Uses 200-bar SMA position, ADX(14), and volatility as crisis proxy.

    Args:
        close: Series of closing prices.
        high: Series of high prices.
        low: Series of low prices.
        volume: Series of volume values.
        lookback: Lookback for trend detection.

    Returns:
        Series of categorical regime strings.
    """
    n = len(close)
    result = pd.Series("unknown", index=close.index)

    if n < lookback + 20:
        return result

    # 200-bar SMA
    sma = close.rolling(lookback).mean()

    # ADX approximation from directional movement
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(0.0, index=close.index)
    minus_dm = pd.Series(0.0, index=close.index)
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)

    atr = tr.rolling(14).mean()
    atr_smooth = atr.replace(0, np.nan)

    plus_di = 100 * (plus_dm.rolling(14).mean() / atr_smooth)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr_smooth)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)) * 100
    adx = dx.rolling(14).mean()

    # Volatility as crisis proxy
    ret = close.pct_change()
    vol = ret.rolling(20).std() * np.sqrt(252)
    vol_percentile = vol.rolling(lookback).rank(pct=True)

    for i in range(lookback + 20, n):
        if pd.isna(sma.iloc[i]) or pd.isna(adx.iloc[i]):
            continue

        is_crisis = vol_percentile.iloc[i] > 0.9 if pd.notna(vol_percentile.iloc[i]) else False
        trending = adx.iloc[i] > 25
        above_sma = close.iloc[i] > sma.iloc[i]

        if is_crisis:
            result.iloc[i] = "CRISIS"
        elif trending and above_sma:
            result.iloc[i] = "TRENDING_BULL"
        elif trending and not above_sma:
            result.iloc[i] = "TRENDING_BEAR"
        else:
            result.iloc[i] = "RANGE_BOUND"

    return result


def day_type_classification(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    open_: pd.Series | None = None,
    ib_first_bars: int = 3,
) -> pd.Series:
    """Classify Market Profile day types per bar."""
    n = len(close)
    result = pd.Series("NonTrend", index=close.index)
    if n < ib_first_bars + 2:
        return result
    if open_ is not None:
        ib_high = open_.iloc[:ib_first_bars].max()
        ib_low = open_.iloc[:ib_first_bars].min()
    else:
        ib_high = high.iloc[:ib_first_bars].max()
        ib_low = low.iloc[:ib_first_bars].min()
    ib_range = ib_high - ib_low
    total_range = high.max() - low.min()
    for i in range(ib_first_bars, n):
        c = close.iloc[i]
        if ib_range < total_range * 0.15:
            result.iloc[i] = "NormalVariation"
        elif ib_range > total_range * 0.5:
            result.iloc[i] = "Trend"
        elif close.diff().abs().rolling(5).mean().iloc[i] > ib_range * 0.3:
            result.iloc[i] = "DoubleDistribution"
        else:
            result.iloc[i] = "Neutral"
    return result
