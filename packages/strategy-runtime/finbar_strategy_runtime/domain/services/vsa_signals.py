"""VSA / Volume Spread Analysis signals from OHLCV data."""

from __future__ import annotations

import pandas as pd


def no_demand(close: pd.Series, volume: pd.Series, lookback: int = 5) -> pd.Series:
    """Small up bar on low volume."""
    n = len(close)
    result = pd.Series(False, index=close.index)
    avg_vol = volume.rolling(20).mean()
    for i in range(lookback, n):
        up = close.iloc[i] > close.iloc[i - 1]
        small_range = (close.iloc[i] - close.iloc[i - 1]) / close.iloc[i - 1] < 0.005
        low_vol = volume.iloc[i] < avg_vol.iloc[i] * 0.7
        if up and small_range and low_vol:
            result.iloc[i] = True
    return result


def no_supply(close: pd.Series, volume: pd.Series, lookback: int = 5) -> pd.Series:
    """Small down bar on low volume."""
    n = len(close)
    result = pd.Series(False, index=close.index)
    avg_vol = volume.rolling(20).mean()
    for i in range(lookback, n):
        down = close.iloc[i] < close.iloc[i - 1]
        small_range = (close.iloc[i - 1] - close.iloc[i]) / close.iloc[i - 1] < 0.005
        low_vol = volume.iloc[i] < avg_vol.iloc[i] * 0.7
        if down and small_range and low_vol:
            result.iloc[i] = True
    return result


def stopping_volume(
    high: pd.Series, low: pd.Series, volume: pd.Series, lookback: int = 20
) -> pd.Series:
    """High volume + narrow spread at range lows."""
    n = len(high)
    result = pd.Series(False, index=high.index)
    rng = high - low
    avg_rng = rng.rolling(lookback).mean()
    avg_vol = volume.rolling(lookback).mean()
    for i in range(lookback, n):
        near_low = low.iloc[i] <= low.iloc[i - lookback : i].quantile(0.2)
        narrow = rng.iloc[i] < avg_rng.iloc[i] * 0.8
        hi_vol = volume.iloc[i] > avg_vol.iloc[i] * 1.5
        if near_low and narrow and hi_vol:
            result.iloc[i] = True
    return result


def climax_volume(
    high: pd.Series, low: pd.Series, volume: pd.Series, lookback: int = 20
) -> pd.Series:
    """Extreme volume + wide spread."""
    n = len(high)
    result = pd.Series(False, index=high.index)
    rng = high - low
    avg_rng = rng.rolling(lookback).mean()
    avg_vol = volume.rolling(lookback).mean()
    for i in range(lookback, n):
        wide = rng.iloc[i] > avg_rng.iloc[i] * 1.5
        extreme_vol = volume.iloc[i] > avg_vol.iloc[i] * 2.0
        if wide and extreme_vol:
            result.iloc[i] = True
    return result


def effort_to_rise(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
    lookback: int = 20,
) -> pd.Series:
    """Wide up bar on high volume, closes middle."""
    n = len(high)
    result = pd.Series(False, index=high.index)
    rng = high - low
    avg_rng = rng.rolling(lookback).mean()
    avg_vol = volume.rolling(lookback).mean()
    for i in range(lookback, n):
        up = close.iloc[i] > close.iloc[i - 1]
        wide = rng.iloc[i] > avg_rng.iloc[i] * 1.3
        hi_vol = volume.iloc[i] > avg_vol.iloc[i] * 1.3
        mid_close = abs(close.iloc[i] - (high.iloc[i] + low.iloc[i]) / 2) < rng.iloc[i] * 0.3
        if up and wide and hi_vol and mid_close:
            result.iloc[i] = True
    return result


def effort_to_fall(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
    lookback: int = 20,
) -> pd.Series:
    """Wide down bar on high volume, closes middle."""
    n = len(high)
    result = pd.Series(False, index=high.index)
    rng = high - low
    avg_rng = rng.rolling(lookback).mean()
    avg_vol = volume.rolling(lookback).mean()
    for i in range(lookback, n):
        down = close.iloc[i] < close.iloc[i - 1]
        wide = rng.iloc[i] > avg_rng.iloc[i] * 1.3
        hi_vol = volume.iloc[i] > avg_vol.iloc[i] * 1.3
        mid_close = abs(close.iloc[i] - (high.iloc[i] + low.iloc[i]) / 2) < rng.iloc[i] * 0.3
        if down and wide and hi_vol and mid_close:
            result.iloc[i] = True
    return result


def effort_result_divergence(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
    lookback: int = 20,
) -> pd.Series:
    """High effort (volume) + small result (range) = divergence."""
    n = len(high)
    result = pd.Series(False, index=high.index)
    rng = high - low
    avg_rng = rng.rolling(lookback).mean()
    avg_vol = volume.rolling(lookback).mean()
    for i in range(lookback, n):
        vol_ratio = volume.iloc[i] / max(avg_vol.iloc[i], 1)
        range_ratio = rng.iloc[i] / max(avg_rng.iloc[i], 0.01)
        if vol_ratio > 1.5 and range_ratio < 0.7:
            result.iloc[i] = True
    return result


def bag_holding(
    close: pd.Series, volume: pd.Series, lookback: int = 5
) -> pd.Series:
    """High-volume up bar after decline, next bar down."""
    n = len(close)
    result = pd.Series(False, index=close.index)
    avg_vol = volume.rolling(20).mean()
    for i in range(lookback + 2, n):
        decline = close.iloc[i - 2] < close.iloc[i - 3]
        up_bar = close.iloc[i - 1] > close.iloc[i - 2]
        hi_vol = volume.iloc[i - 1] > avg_vol.iloc[i - 1] * 1.3
        down_bar = close.iloc[i] < close.iloc[i - 1]
        if decline and up_bar and hi_vol and down_bar:
            result.iloc[i] = True
    return result


def shakeout(
    low: pd.Series, close: pd.Series, volume: pd.Series, lookback: int = 10
) -> pd.Series:
    """Drop below support on high volume, then immediate rally."""
    n = len(close)
    result = pd.Series(False, index=close.index)
    avg_vol = volume.rolling(20).mean()
    for i in range(lookback + 2, n):
        support = low.iloc[i - lookback : i - 1].min()
        break_down = low.iloc[i - 1] < support
        hi_vol = volume.iloc[i - 1] > avg_vol.iloc[i - 1] * 1.5
        rally = close.iloc[i] > close.iloc[i - 1] and close.iloc[i] > support
        if break_down and hi_vol and rally:
            result.iloc[i] = True
    return result


def vsa_test_signal(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
    lookback: int = 20,
) -> pd.Series:
    """Low-volume retest of prior stopping volume area."""
    n = len(close)
    result = pd.Series(False, index=close.index)
    avg_vol = volume.rolling(lookback).mean()
    rng = high - low
    avg_rng = rng.rolling(lookback).mean()
    for i in range(lookback + 5, n):
        low_vol = volume.iloc[i] < avg_vol.iloc[i] * 0.5
        narrow = rng.iloc[i] < avg_rng.iloc[i] * 0.6
        near_support = close.iloc[i] <= low.iloc[i - 5 : i].quantile(0.3)
        if low_vol and narrow and near_support:
            result.iloc[i] = True
    return result
