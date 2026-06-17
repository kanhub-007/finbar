"""Inside-bar handlers and proxy ATR/VWAP.

This module is imported by ``handlers/__init__.py`` which triggers
registration of all ``@_register`` decorators at import time.
"""

import math

import numpy as np
import pandas as pd

from finbar_strategy_runtime.domain.services.proxy_indicator import (
    compute_proxy_atr,
    ensure_proxy_atr,
)
from finbar_strategy_runtime.domain.services.vwap_bands import compute_vwap_session_bands
from finbar_strategy_runtime.indicators._handler_registry import _register


@_register("ib_high")
def _ib_high(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    _compute_true_ib(df, _get_ib_bars(df))
    return df


@_register("ib_low")
def _ib_low(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    _compute_true_ib(df, _get_ib_bars(df))
    return df


@_register("ib_range")
def _ib_range(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    _compute_true_ib(df, _get_ib_bars(df))
    return df


@_register("ib_midpoint")
def _ib_midpoint(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    _compute_true_ib(df, _get_ib_bars(df))
    return df


def _get_ib_bars(df: pd.DataFrame) -> int:
    """Determine how many bars make up the initial balance period.

    Tries to infer from the index frequency, falls back to 2 bars.
    """
    if len(df) < 2:
        return 1
    delta = df.index[1] - df.index[0]
    minutes = delta.total_seconds() / 60
    for key, bars in _IB_BARS_MAP.items():
        if abs(minutes - _IB_MINUTES_MAP[key]) < 2:
            return bars
    return _DEFAULT_IB_BARS


def _compute_true_ib(df: pd.DataFrame, ib_bars: int) -> None:
    """Compute true Initial Balance levels grouped by date.

    Takes the first ``ib_bars`` bars of each day, computes IB high/low/
    range/midpoint, and broadcasts to all bars in that day.

    Results are cached in the 'ib_cache' sentinel so multiple IB
    indicator requests in the same calculate() call are a no-op.
    """
    if "ib_cache" in df.attrs:
        return
    df.attrs["ib_cache"] = True

    date_series = pd.Series(df.index.date, index=df.index)

    ib_highs: dict[str, float] = {}
    ib_lows: dict[str, float] = {}
    ib_ranges: dict[str, float] = {}
    ib_mids: dict[str, float] = {}

    for date, group in df.groupby(date_series):
        if len(group) >= ib_bars:
            first = group.iloc[:ib_bars]
            h = float(first["high"].max())
            lo = float(first["low"].min())
            ib_highs[date] = h
            ib_lows[date] = lo
            ib_ranges[date] = h - lo
            ib_mids[date] = (h + lo) / 2

    df["ib_high"] = date_series.map(ib_highs)
    df["ib_low"] = date_series.map(ib_lows)
    df["ib_range"] = date_series.map(ib_ranges)
    df["ib_midpoint"] = date_series.map(ib_mids)


@_register("proxy_atr", requires={"high", "low", "close"})
def _h_proxy_atr(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    """Wilder RMA ATR (14-period) from high/low/close."""
    df["proxy_atr"] = ensure_proxy_atr(df, cache)
    return df


@_register("proxy_vwap", requires={"high", "low", "close"})
def _h_proxy_vwap(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    """Typical price as VWAP proxy: (H+L+C)/3."""
    df["proxy_vwap"] = (df["high"] + df["low"] + df["close"]) / 3.0
    return df


@_register("proxy_ibs", requires={"high", "low", "close"})
def _h_proxy_ibs(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    """Internal Bar Strength proxy: (C-L)/(H-L)."""
    bar_range = df["high"] - df["low"]
    df["proxy_ibs"] = np.where(
        bar_range > 0, (df["close"] - df["low"]) / bar_range, 0.5
    )
    return df


@_register("proxy_ib_high", requires={"open", "high", "low", "close"})
def _h_proxy_ib_high(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    """Initial Balance high proxy: open + 0.1 * ATR."""
    atr = ensure_proxy_atr(df, cache).fillna(0)
    df["proxy_ib_high"] = df["open"] + 0.1 * atr
    return df


@_register("proxy_ib_low", requires={"open", "high", "low", "close"})
def _h_proxy_ib_low(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    """Initial Balance low proxy: open - 0.1 * ATR."""
    atr = ensure_proxy_atr(df, cache).fillna(0)
    df["proxy_ib_low"] = df["open"] - 0.1 * atr
    return df


@_register("proxy_expected_move", requires={"open", "high", "low", "close"})
def _h_proxy_expected_move(
    df: pd.DataFrame, _name: str, cache: dict
) -> pd.DataFrame:
    """Expected daily move proxy: 0.8 * ATR."""
    atr = ensure_proxy_atr(df, cache).fillna(0)
    df["proxy_expected_move"] = 0.8 * atr
    return df


@_register("proxy_iv", requires={"high", "low", "close"})
def _h_proxy_iv(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    """Implied volatility proxy: (ATR / close) * sqrt(252)."""
    atr = ensure_proxy_atr(df, cache).fillna(0)
    c = df["close"]
    df["proxy_iv"] = np.where(c > 0, (atr / c) * math.sqrt(252), 0.0)
    return df


@_register("proxy_parkinson", requires={"high", "low"})
def _h_proxy_parkinson(
    df: pd.DataFrame, _name: str, _cache: dict
) -> pd.DataFrame:
    """Parkinson high-low volatility proxy: ln(H/L)^2 / (4*ln(2))."""
    log_hl = np.where(
        (df["high"] > 0) & (df["low"] > 0),
        np.log(df["high"] / df["low"]),
        0.0,
    )
    df["proxy_parkinson"] = log_hl**2 / (4.0 * math.log(2))
    return df


@_register("proxy_garman_klass", requires={"open", "high", "low", "close"})
def _h_proxy_garman_klass(
    df: pd.DataFrame, _name: str, _cache: dict
) -> pd.DataFrame:
    """Garman-Klass OHLC volatility proxy."""
    hl = np.where(
        (df["high"] > 0) & (df["low"] > 0),
        np.log(df["high"] / df["low"]),
        0.0,
    )
    co = np.where(
        (df["close"] > 0) & (df["open"] > 0),
        np.log(df["close"] / df["open"]),
        0.0,
    )
    df["proxy_garman_klass"] = 0.5 * hl**2 - (2.0 * math.log(2) - 1.0) * co**2
    return df


@_register("proxy_rogers_satchell", requires={"open", "high", "low", "close"})
def _h_proxy_rogers_satchell(
    df: pd.DataFrame, _name: str, _cache: dict
) -> pd.DataFrame:
    """Rogers-Satchell drift-independent volatility proxy."""
    hc = np.where(
        (df["high"] > 0) & (df["close"] > 0),
        np.log(df["high"] / df["close"]), 0.0
    )
    ho = np.where(
        (df["high"] > 0) & (df["open"] > 0),
        np.log(df["high"] / df["open"]), 0.0
    )
    lc = np.where(
        (df["low"] > 0) & (df["close"] > 0),
        np.log(df["low"] / df["close"]), 0.0
    )
    lo = np.where(
        (df["low"] > 0) & (df["open"] > 0),
        np.log(df["low"] / df["open"]), 0.0
    )
    df["proxy_rogers_satchell"] = hc * ho + lc * lo
    return df


@_register("proxy_typical_price", requires={"high", "low", "close"})
def _h_proxy_typical_price(
    df: pd.DataFrame, _name: str, _cache: dict
) -> pd.DataFrame:
    """VWAP proxy: (H+L+C)/3."""
    df["proxy_typical_price"] = (
        df["high"] + df["low"] + df["close"]
    ) / 3.0
    return df


@_register("proxy_ohlc4", requires={"open", "high", "low", "close"})
def _h_proxy_ohlc4(
    df: pd.DataFrame, _name: str, _cache: dict
) -> pd.DataFrame:
    """VWAP proxy with open context: (O+H+L+C)/4."""
    df["proxy_ohlc4"] = (
        df["open"] + df["high"] + df["low"] + df["close"]
    ) / 4.0
    return df


# ---------------------------------------------------------------------------
# VWAP Standard Deviation Bands — session-scoped (Auction Market Theory)
# ---------------------------------------------------------------------------

_VWAP_BANDS_CACHE_KEY = "__vwap_bands_done"
