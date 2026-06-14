"""Dow Theory trend structure indicators.

Pure (stateless) domain services.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Swing detection (generalized from existing swing_high_20 / swing_low_20)
# ---------------------------------------------------------------------------


def swing_high_n(
    high: pd.Series,
    n: int = 5,
) -> pd.Series:
    """Detect swing highs: highest bar in an n-bar window on each side.

    Args:
        high: Series of high prices.
        n: Window size on each side (default 5 → 11-bar window).

    Returns:
        Boolean Series (True = swing high confirmed).
    """
    length = len(high)
    result = pd.Series(False, index=high.index)

    for i in range(n, length - n):
        val = high.iloc[i]
        left = high.iloc[i - n : i]
        right = high.iloc[i + 1 : i + n + 1]
        if val > left.max() and val > right.max():
            result.iloc[i] = True

    return result


def swing_low_n(
    low: pd.Series,
    n: int = 5,
) -> pd.Series:
    """Detect swing lows: lowest bar in an n-bar window on each side.

    Args:
        low: Series of low prices.
        n: Window size on each side.

    Returns:
        Boolean Series (True = swing low confirmed).
    """
    length = len(low)
    result = pd.Series(False, index=low.index)

    for i in range(n, length - n):
        val = low.iloc[i]
        left = low.iloc[i - n : i]
        right = low.iloc[i + 1 : i + n + 1]
        if val < left.min() and val < right.min():
            result.iloc[i] = True

    return result


# ---------------------------------------------------------------------------
# HH/HL and LH/LL patterns
# ---------------------------------------------------------------------------


def hh_hl_pattern(
    high: pd.Series,
    low: pd.Series,
    lookback: int = 20,
) -> pd.Series:
    """Uptrend confirmation: higher highs and higher lows.

    Checks that the latest swing high > prior swing high AND
    latest swing low > prior swing low.

    Args:
        high: Series of high prices.
        low: Series of low prices.
        lookback: Window for detecting recent swings.

    Returns:
        Boolean Series (True = uptrend confirmed on that bar).
    """
    sh = swing_high_n(high, n=max(3, lookback // 4))
    sl = swing_low_n(low, n=max(3, lookback // 4))

    result = pd.Series(False, index=high.index)

    for i in range(lookback, len(high)):
        recent_highs = high.iloc[i - lookback : i + 1][sh.iloc[i - lookback : i + 1]]
        recent_lows = low.iloc[i - lookback : i + 1][sl.iloc[i - lookback : i + 1]]

        if len(recent_highs) >= 2 and len(recent_lows) >= 2:
            if recent_highs.iloc[-1] > recent_highs.iloc[-2] and recent_lows.iloc[-1] > recent_lows.iloc[-2]:
                result.iloc[i] = True

    return result


def lh_ll_pattern(
    high: pd.Series,
    low: pd.Series,
    lookback: int = 20,
) -> pd.Series:
    """Downtrend confirmation: lower highs and lower lows.

    Args:
        high: Series of high prices.
        low: Series of low prices.
        lookback: Window for detecting recent swings.

    Returns:
        Boolean Series.
    """
    sh = swing_high_n(high, n=max(3, lookback // 4))
    sl = swing_low_n(low, n=max(3, lookback // 4))

    result = pd.Series(False, index=high.index)

    for i in range(lookback, len(high)):
        recent_highs = high.iloc[i - lookback : i + 1][sh.iloc[i - lookback : i + 1]]
        recent_lows = low.iloc[i - lookback : i + 1][sl.iloc[i - lookback : i + 1]]

        if len(recent_highs) >= 2 and len(recent_lows) >= 2:
            if recent_highs.iloc[-1] < recent_highs.iloc[-2] and recent_lows.iloc[-1] < recent_lows.iloc[-2]:
                result.iloc[i] = True

    return result


# ---------------------------------------------------------------------------
# Volume confirmation
# ---------------------------------------------------------------------------


def volume_trend_confirmation(
    close: pd.Series,
    volume: pd.Series,
    lookback: int = 20,
) -> pd.Series:
    """Volume confirms trend when volume > average on trend-direction bars.

    Args:
        close: Series of closing prices.
        volume: Series of volume values.
        lookback: Rolling window.

    Returns:
        Boolean Series.
    """
    if len(close) < lookback:
        return pd.Series(False, index=close.index)

    trend_dir = close.diff().apply(np.sign)
    avg_vol = volume.rolling(lookback).mean()

    # Volume above average when price moves in consistent direction
    above_avg = volume > avg_vol
    consistent_dir = trend_dir.rolling(lookback).apply(
        lambda x: 1 if (x > 0).sum() > len(x) * 0.6 else (-1 if (x < 0).sum() > len(x) * 0.6 else 0),
        raw=False,
    )

    result = pd.Series(False, index=close.index)
    result[(consistent_dir > 0) & above_avg] = True
    result[(consistent_dir < 0) & above_avg] = True

    return result


# ---------------------------------------------------------------------------
# Trend phase (Accumulation / Markup / Distribution)
# ---------------------------------------------------------------------------


def trend_phase(
    close: pd.Series,
    volume: pd.Series,
    lookback: int = 20,
) -> pd.Series:
    """Classify trend phase: Accumulation, Markup, or Distribution.

    Accumulation: low volume, sideways price, gradual price firming.
    Markup: rising prices with expanding volume.
    Distribution: high volume, sideways to declining prices.

    Args:
        close: Series of closing prices.
        volume: Series of volume values.
        lookback: Rolling window.

    Returns:
        Series of categorical strings.
    """
    if len(close) < lookback:
        return pd.Series("unknown", index=close.index)

    ret = close.pct_change()
    ret_ma = ret.rolling(lookback).mean()
    vol_ratio = volume / volume.rolling(lookback).mean()
    range_pct = (close.rolling(lookback).max() - close.rolling(lookback).min()) / close

    result = pd.Series("unknown", index=close.index)

    for i in range(lookback, len(close)):
        r = ret_ma.iloc[i]
        vr = vol_ratio.iloc[i]
        rp = range_pct.iloc[i]

        if pd.isna(r) or pd.isna(vr) or pd.isna(rp):
            continue

        if r > 0.001 and vr > 1.0:
            result.iloc[i] = "markup"
        elif vr > 1.2 and rp < 0.02 and r < 0.001:
            result.iloc[i] = "distribution"
        elif vr < 0.7 and rp < 0.015:
            result.iloc[i] = "accumulation"
        else:
            result.iloc[i] = "markup"  # default if unclear

    return result
