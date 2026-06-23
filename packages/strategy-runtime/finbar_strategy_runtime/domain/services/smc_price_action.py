"""SMC / Smart Money Concepts approximations from OHLCV data."""

from __future__ import annotations

import pandas as pd


def bullish_fvg(high: pd.Series, low: pd.Series) -> pd.Series:
    """Bullish Fair Value Gap: candle-1 high < candle-3 low."""
    n = len(high)
    result = pd.Series(False, index=high.index)
    for i in range(2, n):
        if high.iloc[i - 2] < low.iloc[i]:
            result.iloc[i] = True
    return result


def bearish_fvg(high: pd.Series, low: pd.Series) -> pd.Series:
    """Bearish Fair Value Gap: candle-1 low > candle-3 high."""
    n = len(high)
    result = pd.Series(False, index=high.index)
    for i in range(2, n):
        if low.iloc[i - 2] > high.iloc[i]:
            result.iloc[i] = True
    return result


def bullish_order_block(close: pd.Series, lookback: int = 5) -> pd.Series:
    """Last bearish candle before strong bullish impulse."""
    n = len(close)
    result = pd.Series(False, index=close.index)
    for i in range(lookback + 1, n):
        impulse = close.iloc[i] - close.iloc[i - 1]
        avg_move = close.diff().abs().rolling(lookback).mean().iloc[i]
        if impulse > avg_move * 2 and close.iloc[i - 1] < close.iloc[i - 2]:
            result.iloc[i] = True
    return result


def bearish_order_block(close: pd.Series, lookback: int = 5) -> pd.Series:
    """Last bullish candle before strong bearish impulse."""
    n = len(close)
    result = pd.Series(False, index=close.index)
    for i in range(lookback + 1, n):
        impulse = close.iloc[i] - close.iloc[i - 1]
        avg_move = close.diff().abs().rolling(lookback).mean().iloc[i]
        if -impulse > avg_move * 2 and close.iloc[i - 1] > close.iloc[i - 2]:
            result.iloc[i] = True
    return result


def breaker_block_bullish(
    high: pd.Series, low: pd.Series, close: pd.Series, lookback: int = 10
) -> pd.Series:
    """Failed bearish OB that flips to support."""
    n = len(close)
    result = pd.Series(False, index=close.index)
    for i in range(lookback + 2, n):
        ob_idx = i - 2
        if close.iloc[ob_idx] < close.iloc[ob_idx - 1] and close.iloc[i] > high.iloc[ob_idx]:
            result.iloc[i] = True
    return result


def breaker_block_bearish(
    high: pd.Series, low: pd.Series, close: pd.Series, lookback: int = 10
) -> pd.Series:
    """Failed bullish OB that flips to resistance."""
    n = len(close)
    result = pd.Series(False, index=close.index)
    for i in range(lookback + 2, n):
        ob_idx = i - 2
        if close.iloc[ob_idx] > close.iloc[ob_idx - 1] and close.iloc[i] < low.iloc[ob_idx]:
            result.iloc[i] = True
    return result


def liquidity_sweep_high(
    high: pd.Series, low: pd.Series, close: pd.Series, lookback: int = 5
) -> pd.Series:
    """Break above prior high then immediate reversal below it."""
    n = len(high)
    result = pd.Series(False, index=high.index)
    for i in range(lookback + 2, n):
        prev_high = high.iloc[i - lookback : i - 1].max()
        if high.iloc[i - 1] > prev_high and close.iloc[i] < prev_high:
            result.iloc[i] = True
    return result


def liquidity_sweep_low(
    high: pd.Series, low: pd.Series, close: pd.Series, lookback: int = 5
) -> pd.Series:
    """Break below prior low then immediate reversal above it."""
    n = len(low)
    result = pd.Series(False, index=low.index)
    for i in range(lookback + 2, n):
        prev_low = low.iloc[i - lookback : i - 1].min()
        if low.iloc[i - 1] < prev_low and close.iloc[i] > prev_low:
            result.iloc[i] = True
    return result


def _find_swings(high: pd.Series, low: pd.Series, window: int = 5):
    """Return swing high/low indices."""
    n = min(len(high), len(low))
    sh, sl = [], []
    for i in range(window, n - window):
        if high.iloc[i] > high.iloc[i - window : i].max() and high.iloc[i] > high.iloc[i + 1 : i + window + 1].max():
            sh.append(i)
        if low.iloc[i] < low.iloc[i - window : i].min() and low.iloc[i] < low.iloc[i + 1 : i + window + 1].min():
            sl.append(i)
    return sh, sl


def bos(high: pd.Series, low: pd.Series, window: int = 5) -> pd.Series:
    """Break of Structure: breaks prior swing in trend direction.

    Fires once when price first exceeds the most recent confirmed swing high.
    """
    sh, sl = _find_swings(high, low, window)
    n = len(high)
    result = pd.Series(False, index=high.index)
    last_broken_sh = -1

    for i in range(window * 2, n):
        confirmed_highs = [s for s in sh if s + window <= i]
        if not confirmed_highs:
            continue
        recent_sh = confirmed_highs[-1]
        # Fire only on first break of this swing high
        if recent_sh != last_broken_sh and high.iloc[i] > high.iloc[recent_sh]:
            result.iloc[i] = True
            last_broken_sh = recent_sh
    return result


def choch(high: pd.Series, low: pd.Series, window: int = 5) -> pd.Series:
    """Change of Character: breaks prior swing against trend.

    Fires once when price first breaks below the most recent confirmed
    swing low (reversing an uptrend structure).
    """
    sh, sl = _find_swings(high, low, window)
    n = len(high)
    result = pd.Series(False, index=high.index)
    last_broken_sl = -1

    for i in range(window * 2, n):
        confirmed_highs = [s for s in sh if s + window <= i]
        confirmed_lows = [s for s in sl if s + window <= i]
        # Need an established uptrend structure to reverse
        if len(confirmed_highs) < 2 or len(confirmed_lows) < 1:
            continue
        recent_sl = confirmed_lows[-1]
        # Fire only on first break of this swing low
        if recent_sl != last_broken_sl and low.iloc[i] < low.iloc[recent_sl]:
            result.iloc[i] = True
            last_broken_sl = recent_sl
    return result


def premium_discount_zone(
    high: pd.Series, low: pd.Series, lookback: int = 10
) -> pd.Series:
    """Classify price as premium (upper half) or discount (lower half) of range."""
    n = len(high)
    result = pd.Series("equilibrium", index=high.index)
    for i in range(lookback, n):
        h = high.iloc[i - lookback : i + 1].max()
        l = low.iloc[i - lookback : i + 1].min()
        mid = (h + l) / 2
        upper = (h + mid) / 2
        lower = (mid + l) / 2
        c = (high.iloc[i] + low.iloc[i]) / 2
        if c > upper:
            result.iloc[i] = "premium"
        elif c < lower:
            result.iloc[i] = "discount"
    return result
