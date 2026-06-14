"""Supply/demand zone detection from OHLCV data.

Pure (stateless) domain services.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _find_base_candles(
    high: pd.Series,
    low: pd.Series,
    lookback: int = 3,
) -> list[int]:
    """Find base candles: small range relative to neighbors."""
    n = len(high)
    rng = high - low
    avg_range = rng.rolling(lookback * 2 + 1, center=True).mean()
    bases = []
    for i in range(lookback, n - lookback):
        if rng.iloc[i] < avg_range.iloc[i] * 0.6:
            bases.append(i)
    return bases


def demand_zone_low(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = 5,
) -> pd.Series:
    """Demand zone bottom: low of base candle in RBR/DBR pattern."""
    n = len(close)
    result = pd.Series(np.nan, index=close.index)

    for i in range(lookback * 2, n):
        window_low = low.iloc[i - lookback * 2 : i]
        min_idx = window_low.idxmin()
        min_loc = window_low.index.get_loc(min_idx)
        # Demand zone = below current price after a rally
        if close.iloc[i] > low.iloc[i - lookback * 2 : i].max():
            result.iloc[i] = window_low.min()

    return result


def demand_zone_high(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = 5,
) -> pd.Series:
    """Demand zone top: high of base candle in RBR/DBR pattern."""
    n = len(close)
    result = pd.Series(np.nan, index=close.index)

    for i in range(lookback * 2, n):
        # Zone top is the high of the lowest candle in lookback
        window = high.iloc[i - lookback * 2 : i]
        if close.iloc[i] > low.iloc[i - lookback * 2 : i].max():
            result.iloc[i] = window.max()

    return result


def demand_zone_score(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    lookback: int = 5,
) -> pd.Series:
    """Demand zone quality score (0-6)."""
    n = len(close)
    result = pd.Series(0, index=close.index)

    avg_vol = volume.rolling(20).mean()
    rng = high - low
    avg_range = rng.rolling(20).mean()

    for i in range(lookback * 2, n):
        score = 0
        # Departure strength
        if i >= 1 and close.iloc[i] > close.iloc[i - 1] * 1.01:
            score += 2
        elif close.iloc[i] > close.iloc[i - 1]:
            score += 1
        # Volume at zone
        if volume.iloc[i] > avg_vol.iloc[i]:
            score += 1
        # Range compression
        if rng.iloc[i] < avg_range.iloc[i]:
            score += 1
        # Close position
        if close.iloc[i] > (high.iloc[i] + low.iloc[i]) / 2:
            score += 1
        # Continuation
        if i >= 2 and close.iloc[i - 1] > close.iloc[i - 2]:
            score += 1
        result.iloc[i] = min(score, 6)

    return result


def supply_zone_low(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = 5,
) -> pd.Series:
    """Supply zone bottom."""
    n = len(close)
    result = pd.Series(np.nan, index=close.index)
    for i in range(lookback * 2, n):
        if close.iloc[i] < high.iloc[i - lookback * 2 : i].min():
            result.iloc[i] = low.iloc[i - lookback * 2 : i].min()
    return result


def supply_zone_high(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = 5,
) -> pd.Series:
    """Supply zone top."""
    n = len(close)
    result = pd.Series(np.nan, index=close.index)
    for i in range(lookback * 2, n):
        if close.iloc[i] < high.iloc[i - lookback * 2 : i].min():
            result.iloc[i] = high.iloc[i - lookback * 2 : i].max()
    return result


def supply_zone_score(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    lookback: int = 5,
) -> pd.Series:
    """Supply zone quality score (0-6)."""
    n = len(close)
    result = pd.Series(0, index=close.index)
    avg_vol = volume.rolling(20).mean()
    rng = high - low
    avg_range = rng.rolling(20).mean()
    for i in range(lookback * 2, n):
        score = 0
        if i >= 1 and close.iloc[i] < close.iloc[i - 1] * 0.99:
            score += 2
        elif close.iloc[i] < close.iloc[i - 1]:
            score += 1
        if volume.iloc[i] > avg_vol.iloc[i]:
            score += 1
        if rng.iloc[i] < avg_range.iloc[i]:
            score += 1
        if close.iloc[i] < (high.iloc[i] + low.iloc[i]) / 2:
            score += 1
        if i >= 2 and close.iloc[i - 1] < close.iloc[i - 2]:
            score += 1
        result.iloc[i] = min(score, 6)
    return result


def zone_failure_bullish(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    lookback: int = 10,
) -> pd.Series:
    """Supply zone broken above + volume → bullish failure."""
    n = len(close)
    result = pd.Series(False, index=close.index)
    avg_vol = volume.rolling(20).mean()
    for i in range(lookback * 2, n):
        prev_high = high.iloc[i - lookback : i].max()
        if close.iloc[i] > prev_high and volume.iloc[i] > avg_vol.iloc[i] * 1.2:
            result.iloc[i] = True
    return result


def zone_failure_bearish(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    lookback: int = 10,
) -> pd.Series:
    """Demand zone broken below + volume → bearish failure."""
    n = len(close)
    result = pd.Series(False, index=close.index)
    avg_vol = volume.rolling(20).mean()
    for i in range(lookback * 2, n):
        prev_low = low.iloc[i - lookback : i].min()
        if close.iloc[i] < prev_low and volume.iloc[i] > avg_vol.iloc[i] * 1.2:
            result.iloc[i] = True
    return result
