"""Intraday seasonality proxy calculators from OHLCV data."""

from __future__ import annotations

import numpy as np
import pandas as pd


def overnight_intraday_decomp(
    ohlc: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    """Decompose daily return into overnight and intraday components.

    Args:
        ohlc: DataFrame with 'open', 'high', 'low', 'close' columns.

    Returns:
        Tuple of (overnight_return, intraday_return) Series.
    """
    open_ = ohlc["open"].astype(float)
    close = ohlc["close"].astype(float)

    overnight_ret = (open_ - close.shift(1)) / close.shift(1)
    intraday_ret = (close - open_) / open_

    return overnight_ret, intraday_ret


def parametric_u_shape(
    volume: pd.Series,
    bars_per_day: int = 78,
    a: float = 1.0,
    b: float = 0.3,
) -> pd.Series:
    """Parametric U-shape volume curve (Admati-Pfleiderer style).

    Models intraday volume as: V(t) = a + b * ((t - mid)^2), where
    t is normalized to [0, 1] within each day.

    Args:
        volume: Series of volume values (used only for index/length).
        bars_per_day: Number of bars in a trading day.
        a: Base volume level.
        b: Curvature parameter (higher = stronger U-shape).

    Returns:
        Series of expected relative volume at each bar position.
    """
    n = len(volume)
    result = pd.Series(np.nan, index=volume.index)

    for i in range(n):
        bar_in_day = i % bars_per_day
        t = bar_in_day / max(bars_per_day - 1, 1)
        mid = 0.5
        result.iloc[i] = a + b * (t - mid) ** 2

    return result


def first_last_hour_vol_fraction(
    df: pd.DataFrame,
    open_vol_col: str = "opening_volume",
    close_vol_col: str = "closing_volume",
    total_vol_col: str = "volume",
) -> pd.Series:
    """Fraction of volume in first and last hour of the trading day.

    Args:
        df: DataFrame with opening_volume, closing_volume, volume columns.
        open_vol_col: Column name for opening-hour volume.
        close_vol_col: Column name for closing-hour volume.
        total_vol_col: Column name for total daily volume.

    Returns:
        Series of fractions (0 to 1). NaN if columns missing.
    """
    for col in (open_vol_col, close_vol_col, total_vol_col):
        if col not in df.columns:
            return pd.Series(np.nan, index=df.index)

    open_vol = df[open_vol_col].astype(float)
    close_vol = df[close_vol_col].astype(float)
    total_vol = df[total_vol_col].astype(float)

    fraction = (open_vol + close_vol) / total_vol.replace(0, np.nan)
    return fraction


def first_last_hour_vol_fraction_proxy(df: pd.DataFrame) -> pd.Series:
    """Proxy: fraction of volume in the first and last hour of each UTC day.

    Replaces the ``opening_volume``/``closing_volume`` requirement (no OHLCV
    data source provides those columns) by grouping intraday bars by UTC date
    and summing the volume of the first and last hour within each day.

    Vectorised implementation:
      1. group bars by calendar date
      2. daily total volume via ``groupby.transform('sum')``
      3. flag the first-hour and last-hour bar of each day
      4. edge volume / daily total

    Args:
        df: OHLCV DataFrame with a ``DatetimeIndex`` and a ``volume`` column.

    Returns:
        Series aligned to ``df.index`` with values in ``[0, 1]``. Returns
        NaN where the day has fewer than 2 bars (daily data cannot be
        subdivided into first/last hour) or where daily volume is zero.

    See:
        spec 2026-06-16 Scenario 12 (ADR-4: proxy from intraday grouping).
    """
    if "volume" not in df.columns:
        return pd.Series(np.nan, index=df.index)

    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        return pd.Series(np.nan, index=idx)

    volume = df["volume"].astype(float)
    dates = pd.Series(idx.date, index=idx)
    hours = pd.Series(idx.hour, index=idx)

    # Bars per day: days with < 2 bars cannot define a first/last hour.
    bars_in_day = dates.groupby(dates).transform("size")
    daily_total = volume.groupby(dates).transform("sum")

    # First/last hour within each calendar day (robust to partial days).
    first_hour = hours.groupby(dates).transform("min")
    last_hour = hours.groupby(dates).transform("max")
    is_edge = (hours == first_hour) | (hours == last_hour)

    # Daily edge volume (first + last hour) broadcast to every bar in the
    # day, matching the original daily-metric semantic: each bar reports
    # its day's first/last-hour fraction.
    edge_volume_per_bar = volume.where(is_edge, 0.0)
    daily_edge_volume = edge_volume_per_bar.groupby(dates).transform("sum")
    fraction = daily_edge_volume / daily_total.replace(0.0, np.nan)

    # Only meaningful when the day has at least 2 bars (subdividable).
    return fraction.where(bars_in_day >= 2)


# ---------------------------------------------------------------------------
# Empirical volume curves (intraday seasonality)
# ---------------------------------------------------------------------------


def intraday_volume_curve(
    df: pd.DataFrame,
    volume_col: str = "volume",
) -> pd.Series:
    """Empirical intraday volume curve: mean volume per time-of-day.

    Groups bars by their time-of-day and computes the expanding mean
    volume. Each bar gets the mean of all *prior* bars with the same
    time-of-day (no lookahead: bar T cannot see itself).

    Args:
        df: DataFrame with a DatetimeIndex and a volume column.
        volume_col: Name of the volume column.

    Returns:
        Series aligned to ``df.index``. First occurrence of each
        time-of-day is NaN (no prior data).
    """
    if volume_col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    volume = df[volume_col].astype(float)
    time_of_day = volume.index.time

    # Expanding mean per time-of-day group, shifted by 1 (no lookahead)
    result = volume.groupby(time_of_day).transform(
        lambda x: x.shift(1).expanding().mean()
    )
    return result


def empirical_volume_curve(
    df: pd.DataFrame,
    volume_col: str = "volume",
) -> pd.Series:
    """Alias for intraday_volume_curve (same computation).

    Some references distinguish 'empirical' (raw mean) from 'parametric'
    (model-fit) volume curves. This implementation uses the empirical
    expanding mean per time-of-day.
    """
    return intraday_volume_curve(df, volume_col=volume_col)
