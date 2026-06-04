"""Proxy indicator library — pure, stateless functions.

These indicators allow backtesting with daily OHLCV when intraday data
is unavailable. Each function takes raw price data and returns a single
numeric value or enriched dict/DataFrame.

All functions are pure — no state, no I/O, no external dependencies
beyond ``math`` and ``numpy``.

Validated against:
- Pagonidis 2013 (IBS on ETFs)
- BestEx Research (Parkinson vs ATR)
- PortfolioOptimizer.io (Garman-Klass, Yang-Zhang, Rogers-Satchell)
- QuantInsti (VWAP / Typical Price)
- Auction Market Theory literature (IB proxy)
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# VWAP proxies
# ---------------------------------------------------------------------------


def typical_price(high: float, low: float, close: float) -> float:
    """VWAP proxy: (H + L + C) / 3."""
    return (high + low + close) / 3


def ohlc4(open_price: float, high: float, low: float, close: float) -> float:
    """Alternative VWAP proxy with open context: (O + H + L + C) / 4."""
    return (open_price + high + low + close) / 4


# ---------------------------------------------------------------------------
# Initial Balance proxies
# ---------------------------------------------------------------------------


def ib_proxy_high(open_price: float, atr: float, mult: float = 0.1) -> float:
    """IB high proxy: Open + (mult * ATR)."""
    return open_price + (mult * atr)


def ib_proxy_low(open_price: float, atr: float, mult: float = 0.1) -> float:
    """IB low proxy: Open - (mult * ATR)."""
    return open_price - (mult * atr)


# ---------------------------------------------------------------------------
# IBS (Internal Bar Strength) — mean-reversion indicator
# ---------------------------------------------------------------------------


def ibs(high: float, low: float, close: float) -> float:
    """Internal Bar Strength: (C - L) / (H - L).

    Returns 0.5 when bar range is zero (doji / no movement).
    """
    bar_range = high - low
    if bar_range <= 0:
        return 0.5
    return (close - low) / bar_range


# ---------------------------------------------------------------------------
# RVOL (Relative Volume)
# ---------------------------------------------------------------------------


def rvol(volume: float, avg_volume: float) -> float:
    """Relative Volume: current volume / SMA(volume, N).

    Returns 1.0 when avg_volume is zero or negative (neutral signal).
    """
    if avg_volume <= 0:
        return 1.0
    return volume / avg_volume


# ---------------------------------------------------------------------------
# Volatility estimators
# ---------------------------------------------------------------------------


def parkinson_vol(high: float, low: float) -> float:
    """Parkinson (1980) range-based volatility for a single bar.

    Uses the log range: ln(H/L)^2 / (4 * ln(2)).
    Returns 0.0 when high or low is non-positive.
    """
    if low <= 0 or high <= 0:
        return 0.0
    log_ratio = math.log(high / low)
    return log_ratio**2 / (4.0 * math.log(2))


def garman_klass_vol(open_price: float, high: float, low: float, close: float) -> float:
    """Garman-Klass (1980) OHLC-based volatility for a single bar.

    0.5 * ln(H/L)^2 - (2*ln(2) - 1) * ln(C/O)^2.
    Returns 0.0 when low or open is non-positive.
    """
    if low <= 0 or open_price <= 0:
        return 0.0
    hl = math.log(high / low)
    co = math.log(close / open_price)
    return 0.5 * hl**2 - (2.0 * math.log(2) - 1.0) * co**2


def rogers_satchell_vol(
    open_price: float, high: float, low: float, close: float
) -> float:
    """Rogers-Satchell (1991) volatility — handles drift.

    ln(H/C) * ln(H/O) + ln(L/C) * ln(L/O).
    Returns 0.0 when any input is non-positive.
    """
    if any(v <= 0 for v in (open_price, high, low, close)):
        return 0.0
    return math.log(high / close) * math.log(high / open_price) + math.log(
        low / close
    ) * math.log(low / open_price)


def yang_zhang_vol(
    bars: Sequence[dict[str, float]],
    period: int = 20,
) -> float:
    """Yang-Zhang (2000) volatility estimator — best for stocks with gaps.

    Combines overnight, open-to-close, and Rogers-Satchell volatility.
    Requires at least ``period + 1`` bars for computation.

    Args:
        bars: Sequence of OHLCV dicts with keys open, high, low, close.
        period: Lookback window (default 20).

    Returns:
        Annualised volatility as a decimal (e.g. 0.25 for 25%).
    """
    if len(bars) < period + 1:
        return 0.0

    window = bars[-(period + 1) :]

    overnight: list[float] = []
    for i in range(1, len(window)):
        prev_close = window[i - 1]["close"]
        curr_open = window[i]["open"]
        if prev_close > 0 and curr_open > 0:
            overnight.append(math.log(curr_open / prev_close))

    oc: list[float] = []
    for i in range(1, len(window)):
        o = window[i]["open"]
        c = window[i]["close"]
        if o > 0 and c > 0:
            oc.append(math.log(c / o))

    rs: list[float] = []
    for i in range(1, len(window)):
        o = window[i]["open"]
        h = window[i]["high"]
        l = window[i]["low"]  # noqa: E741
        c = window[i]["close"]
        rs.append(rogers_satchell_vol(o, h, l, c))

    n = len(overnight)
    if n < 2:
        return 0.0

    mean_on = sum(overnight) / n
    var_on = sum((x - mean_on) ** 2 for x in overnight) / (n - 1)

    mean_oc = sum(oc) / n
    var_oc = sum((x - mean_oc) ** 2 for x in oc) / (n - 1)

    mean_rs = sum(rs) / n

    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    sigma_sq = var_on + k * var_oc + (1 - k) * mean_rs

    return math.sqrt(max(sigma_sq, 0.0) * TRADING_DAYS_PER_YEAR)


# ---------------------------------------------------------------------------
# Expected move & misc
# ---------------------------------------------------------------------------


def daily_expected_move(price: float, atr: float) -> float:
    """Expected daily move: 0.8 * ATR."""
    return 0.8 * atr


def round_number_proximity(price: float) -> dict[str, Any]:
    """Distance to nearest round-number cluster (optional filter).

    Returns dict with keys: round_number, distance, distance_pct.
    """
    if price <= 0:
        return {"round_number": 0, "distance": 0, "distance_pct": 0}

    if price < 10:
        step = 1.0
    elif price < 100:
        step = 5.0
    elif price < 500:
        step = 10.0
    elif price < 1000:
        step = 25.0
    else:
        step = 50.0

    nearest = round(price / step) * step
    distance = abs(price - nearest)
    distance_pct = distance / price if price > 0 else 0

    return {
        "round_number": nearest,
        "distance": distance,
        "distance_pct": distance_pct,
    }


def slippage_estimate(size: int, avg_volume: float) -> float:
    """Linear slippage model — sqrt(participation) * 0.1, capped at 5%.

    Args:
        size: Absolute trade size (shares/contracts).
        avg_volume: Average volume over the lookback period.

    Returns:
        Slippage as a decimal fraction (e.g. 0.005 for 0.5%).
    """
    if avg_volume <= 0:
        return 0.01
    participation = abs(size) / avg_volume
    return min(math.sqrt(participation) * 0.1, 0.05)


# ---------------------------------------------------------------------------
# IV proxy from ATR
# ---------------------------------------------------------------------------


def atr_to_iv_proxy(atr: float, price: float) -> float:
    """Convert 14-period ATR to implied volatility proxy.

    Annualises the daily ATR percentage: (ATR / price) * sqrt(252).
    """
    if price <= 0 or atr <= 0:
        return 0.0
    daily_pct = atr / price
    return daily_pct * math.sqrt(TRADING_DAYS_PER_YEAR)


# ---------------------------------------------------------------------------
# Bar-level enrichment
# ---------------------------------------------------------------------------


def enrich_bar_with_proxies(bar: dict[str, Any]) -> dict[str, Any]:
    """Compute all proxy indicators for one bar and return a new dict."""
    o = bar.get("open", 0)
    h = bar.get("high", 0)
    l = bar.get("low", 0)  # noqa: E741
    c = bar.get("close", 0)
    atr_val = bar.get("atr", 0) or 0

    enriched = dict(bar)  # shallow copy

    enriched["proxy_typical_price"] = typical_price(h, l, c)
    enriched["proxy_ohlc4"] = ohlc4(o, h, l, c)
    enriched["proxy_ibs"] = ibs(h, l, c)

    if atr_val > 0:
        enriched["proxy_ib_high"] = ib_proxy_high(o, atr_val)
        enriched["proxy_ib_low"] = ib_proxy_low(o, atr_val)
        enriched["proxy_expected_move"] = daily_expected_move(c, atr_val)
        enriched["proxy_iv"] = atr_to_iv_proxy(atr_val, c)

    enriched["proxy_parkinson"] = parkinson_vol(h, l)
    enriched["proxy_garman_klass"] = garman_klass_vol(o, h, l, c)
    enriched["proxy_rogers_satchell"] = rogers_satchell_vol(o, h, l, c)

    return enriched


def enrich_dataframe_with_proxies(df: pd.DataFrame) -> pd.DataFrame:
    """Batch-compute proxy indicators for an entire DataFrame.

    Requires columns: open, high, low, close, volume.
    If ``atr`` column is present, also computes IB proxies, expected move,
    and IV proxy.
    """
    result = df.copy()

    h = result["high"]
    l = result["low"]  # noqa: E741
    c = result["close"]
    o = result["open"]

    result["proxy_typical_price"] = (h + l + c) / 3
    result["proxy_ohlc4"] = (o + h + l + c) / 4

    bar_range = h - l
    result["proxy_ibs"] = np.where(bar_range > 0, (c - l) / bar_range, 0.5)

    if "atr" in result.columns:
        atr_col = result["atr"].fillna(0)
        result["proxy_ib_high"] = o + 0.1 * atr_col
        result["proxy_ib_low"] = o - 0.1 * atr_col
        result["proxy_expected_move"] = 0.8 * atr_col
        result["proxy_iv"] = np.where(
            c > 0,
            (atr_col / c) * math.sqrt(TRADING_DAYS_PER_YEAR),
            0.0,
        )

    # Parkinson: ln(H/L)^2 / (4 * ln(2))
    log_hl = np.where(
        (h > 0) & (l > 0),
        np.log(h / l),
        0.0,
    )
    result["proxy_parkinson"] = log_hl**2 / (4.0 * math.log(2))

    # Garman-Klass: 0.5 * ln(H/L)^2 - (2*ln(2)-1) * ln(C/O)^2
    log_co = np.where(
        (c > 0) & (o > 0),
        np.log(c / o),
        0.0,
    )
    result["proxy_garman_klass"] = (
        0.5 * log_hl**2 - (2.0 * math.log(2) - 1.0) * log_co**2
    )

    # Rogers-Satchell: ln(H/C)*ln(H/O) + ln(L/C)*ln(L/O)
    log_hc = np.where((h > 0) & (c > 0), np.log(h / c), 0.0)
    log_ho = np.where((h > 0) & (o > 0), np.log(h / o), 0.0)
    log_lc = np.where((l > 0) & (c > 0), np.log(l / c), 0.0)
    log_lo = np.where((l > 0) & (o > 0), np.log(l / o), 0.0)
    result["proxy_rogers_satchell"] = log_hc * log_ho + log_lc * log_lo

    return result
