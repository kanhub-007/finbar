"""Fibonacci retracement and extension levels from swing detection.

Pure (stateless) domain services.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _detect_swings(
    close: pd.Series,
    window: int = 5,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Detect swing highs and lows using a rolling window.

    Returns lists of (index, price) for swing highs and swing lows.
    """
    n = len(close)
    if n < window * 2 + 1:
        return [], []

    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []

    for i in range(window, n - window):
        val = close.iloc[i]
        left = close.iloc[i - window : i]
        right = close.iloc[i + 1 : i + window + 1]

        if val > left.max() and val > right.max():
            swing_highs.append((i, val))
        elif val < left.min() and val < right.min():
            swing_lows.append((i, val))

    return swing_highs, swing_lows


def _last_completed_swing(
    close: pd.Series,
    window: int = 5,
) -> tuple[float, float, int, bool] | None:
    """Return (low_price, high_price, end_index) of last completed swing move.

    A swing move is the range from the last swing point (high or low) to
    the prior opposite swing point. Both points must be fully closed
    (no look-ahead).

    Returns None if no completed swing is detected.
    """
    highs, lows = _detect_swings(close, window)
    all_swings = sorted(
        [(idx, price, "high") for idx, price in highs]
        + [(idx, price, "low") for idx, price in lows],
        key=lambda x: x[0],
    )

    if len(all_swings) < 2:
        return None

    # Last two swings define the move
    s1_idx, s1_price, s1_kind = all_swings[-2]
    s2_idx, s2_price, s2_kind = all_swings[-1]

    if s1_kind == s2_kind:
        return None  # Same type — no valid move

    is_uptrend = s1_kind == "low" and s2_kind == "high"
    low_price = min(s1_price, s2_price)
    high_price = max(s1_price, s2_price)
    return low_price, high_price, s2_idx, is_uptrend


def _fib_levels(
    low: float,
    high: float,
    end_idx: int,
    length: int,
) -> dict[str, pd.Series]:
    """Compute all Fibonacci levels for a given swing range."""
    rng = high - low
    nan_series = pd.Series(np.nan, index=range(length))

    levels = {
        "fib_236_retrace": high - 0.236 * rng,
        "fib_382_retrace": high - 0.382 * rng,
        "fib_500_retrace": high - 0.500 * rng,
        "fib_618_retrace": high - 0.618 * rng,
        "fib_786_retrace": high - 0.786 * rng,
        "fib_1272_extension": high + 0.272 * rng,
        "fib_1618_extension": high + 0.618 * rng,
        "fib_2000_extension": high + 1.000 * rng,
        "fib_2618_extension": high + 1.618 * rng,
    }

    result: dict[str, pd.Series] = {}
    for name, level in levels.items():
        s = nan_series.copy()
        s.iloc[end_idx:] = level
        result[name] = s

    return result


# ---- Public API ----


def fib_382_retrace(
    close: pd.Series,
    swing_window: int = 5,
) -> pd.Series:
    swing = _last_completed_swing(close, swing_window)
    if swing is None:
        return pd.Series(np.nan, index=close.index)
    low, high, end_idx, is_uptrend = swing
    rng = high - low
    result = pd.Series(np.nan, index=close.index)
    if is_uptrend:
        level = high - 0.382 * rng
    else:
        level = low + 0.382 * rng
    result.iloc[end_idx:] = level
    return result


def fib_500_retrace(
    close: pd.Series,
    swing_window: int = 5,
) -> pd.Series:
    swing = _last_completed_swing(close, swing_window)
    if swing is None:
        return pd.Series(np.nan, index=close.index)
    low, high, end_idx, is_uptrend = swing
    rng = high - low
    result = pd.Series(np.nan, index=close.index)
    if is_uptrend:
        level = high - 0.500 * rng
    else:
        level = low + 0.500 * rng
    result.iloc[end_idx:] = level
    return result


def fib_618_retrace(
    close: pd.Series,
    swing_window: int = 5,
) -> pd.Series:
    swing = _last_completed_swing(close, swing_window)
    if swing is None:
        return pd.Series(np.nan, index=close.index)
    low, high, end_idx, is_uptrend = swing
    rng = high - low
    result = pd.Series(np.nan, index=close.index)
    if is_uptrend:
        level = high - 0.618 * rng
    else:
        level = low + 0.618 * rng
    result.iloc[end_idx:] = level
    return result


def fib_1618_extension(
    close: pd.Series,
    swing_window: int = 5,
) -> pd.Series:
    swing = _last_completed_swing(close, swing_window)
    if swing is None:
        return pd.Series(np.nan, index=close.index)
    low, high, end_idx, is_uptrend = swing
    rng = high - low
    result = pd.Series(np.nan, index=close.index)
    if is_uptrend:
        level = high + 0.618 * rng
    else:
        level = low - 0.618 * rng
    result.iloc[end_idx:] = level
    return result


def fib_confluence_score(
    close: pd.Series,
    swing_window: int = 5,
    tick_zone: float = 0.005,
) -> pd.Series:
    """0-4 score counting Fib levels clustering near current price."""
    swing = _last_completed_swing(close, swing_window)
    if swing is None:
        return pd.Series(0, index=close.index)

    low, high, end_idx, is_uptrend = swing
    rng = high - low
    ratios = [0.236, 0.382, 0.500, 0.618, 0.786]
    if is_uptrend:
        levels = [high - r * rng for r in ratios]
    else:
        levels = [low + r * rng for r in ratios]

    result = pd.Series(0, index=close.index)
    for i in range(max(end_idx, swing_window), len(close)):
        price = close.iloc[i]
        cluster_count = sum(
            1 for l in levels if abs(price - l) / price < tick_zone
        )
        result.iloc[i] = min(cluster_count, 4)

    return result
