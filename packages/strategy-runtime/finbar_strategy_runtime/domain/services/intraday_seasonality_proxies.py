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
