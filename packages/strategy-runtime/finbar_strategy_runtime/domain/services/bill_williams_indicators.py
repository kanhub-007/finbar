"""Bill Williams chaos theory indicators.

Pure (stateless) domain services.
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Awesome Oscillator
# ---------------------------------------------------------------------------


def awesome_oscillator(
    high: pd.Series,
    low: pd.Series,
) -> pd.Series:
    """Awesome Oscillator: SMA(median, 5) - SMA(median, 34).

    Args:
        high: Series of high prices.
        low: Series of low prices.

    Returns:
        Series of AO values.
    """
    median = (high + low) / 2.0
    ao = median.rolling(5).mean() - median.rolling(34).mean()
    return ao


# ---------------------------------------------------------------------------
# Accelerator Oscillator
# ---------------------------------------------------------------------------


def accelerator_oscillator(
    high: pd.Series,
    low: pd.Series,
) -> pd.Series:
    """Accelerator Oscillator: AO - SMA(AO, 5).

    Args:
        high: Series of high prices.
        low: Series of low prices.

    Returns:
        Series of AC values.
    """
    ao = awesome_oscillator(high, low)
    return ao - ao.rolling(5).mean()


# ---------------------------------------------------------------------------
# Alligator
# ---------------------------------------------------------------------------


def _smma(series: pd.Series, period: int) -> pd.Series:
    """Smoothed Moving Average."""
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def alligator_lines(
    high: pd.Series,
    low: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Alligator lines: Jaw (13/8), Teeth (8/5), Lips (5/3).

    Each line is an SMMA of the median price, shifted forward.

    Returns:
        (jaw, teeth, lips) Series.
    """
    median = (high + low) / 2.0

    jaw = _smma(median, 13).shift(8)
    teeth = _smma(median, 8).shift(5)
    lips = _smma(median, 5).shift(3)

    return jaw, teeth, lips


def alligator_status(
    jaw: pd.Series,
    teeth: pd.Series,
    lips: pd.Series,
    threshold: float = 0.002,
) -> pd.Series:
    """Classify alligator state: sleeping, waking, or eating.

    Sleeping: lines intertwined (max spread < threshold * price).
    Waking: one line crosses another.
    Eating: lines ordered and spreading (lips > teeth > jaw or opposite).

    Args:
        jaw, teeth, lips: Alligator lines.
        threshold: Spread threshold for sleeping detection.

    Returns:
        Series of categorical states.
    """
    result = pd.Series("unknown", index=jaw.index)

    for i in range(len(jaw)):
        j, t, l = jaw.iloc[i], teeth.iloc[i], lips.iloc[i]
        if pd.isna(j) or pd.isna(t) or pd.isna(l):
            continue

        vals = [j, t, l]
        max_val = max(vals)
        min_val = min(vals)
        avg_val = (j + t + l) / 3.0

        if avg_val > 0 and (max_val - min_val) / avg_val < threshold:
            result.iloc[i] = "sleeping"
        elif l > t > j or l < t < j:
            result.iloc[i] = "eating"
        else:
            result.iloc[i] = "waking"

    return result


# ---------------------------------------------------------------------------
# Williams Fractals
# ---------------------------------------------------------------------------


def williams_fractal_high(
    high: pd.Series,
    window: int = 2,
) -> pd.Series:
    """Buy fractal: highest bar in 5-bar window (2 each side)."""
    n = len(high)
    result = pd.Series(pd.NA, index=high.index, dtype="boolean")
    for i in range(window, n - window):
        val = high.iloc[i]
        left = high.iloc[i - window : i]
        right = high.iloc[i + 1 : i + window + 1]
        if val > left.max() and val > right.max():
            signal_idx = i + window
            if signal_idx < n:
                result.iloc[signal_idx] = True
    return result


def williams_fractal_low(
    low: pd.Series,
    window: int = 2,
) -> pd.Series:
    """Sell fractal: lowest bar in 5-bar window (2 each side)."""
    n = len(low)
    result = pd.Series(pd.NA, index=low.index, dtype="boolean")
    for i in range(window, n - window):
        val = low.iloc[i]
        left = low.iloc[i - window : i]
        right = low.iloc[i + 1 : i + window + 1]
        if val < left.min() and val < right.min():
            signal_idx = i + window
            if signal_idx < n:
                result.iloc[signal_idx] = True
    return result


# ---------------------------------------------------------------------------
# Zone Signal (AO + AC combination)
# ---------------------------------------------------------------------------


def zone_signal(
    high: pd.Series,
    low: pd.Series,
) -> pd.Series:
    """Zone signal from AO and AC combination.

    Green: AO positive and rising, AC positive and rising.
    Red: AO negative and falling, AC negative and falling.
    Gray: everything else (mixed signals).

    Args:
        high: Series of high prices.
        low: Series of low prices.

    Returns:
        Series of categorical signals ('green', 'red', 'gray').
    """
    ao = awesome_oscillator(high, low)
    ac = accelerator_oscillator(high, low)

    ao_up = ao.diff() > 0
    ac_up = ac.diff() > 0

    result = pd.Series("gray", index=high.index)

    green = (ao > 0) & ao_up & (ac > 0) & ac_up
    red = (ao < 0) & (~ao_up) & (ac < 0) & (~ac_up)

    result[green] = "green"
    result[red] = "red"

    return result
