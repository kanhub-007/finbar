"""PandasTaIndicatorCalculator — pandas_ta implementation of IndicatorCalculator.

Calculates technical indicators (RSI, SMA, MACD, ATR, etc.) on OHLCV
DataFrames using the pandas_ta library. Also delegates proxy indicators
to the domain proxy_indicator module.

Implements the IndicatorCalculator domain interface via the Strategy pattern.
Uses the Pipeline pattern — the calculate() dispatcher stays under 30 lines,
each indicator group is its own private method.

TODO(refactor): Split into sub-modules by indicator category (trend, momentum,
volatility, VP/profile, auction/AMT, Wyckoff, dynamic). Currently ~1400 lines
because handler functions reference shared helpers (_safe_ta, _compute_true_ib,
_compute_vwap_bands) and each other, making naive extraction cause circular
imports. Extract shared helpers to a _shared.py module first, then split.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pandas as pd
import pandas_ta as ta
import numpy as np

from finbar_strategy_runtime.domain.interfaces.indicator_calculator import IndicatorCalculator
from finbar_strategy_runtime.domain.services.proxy_indicator import (
    enrich_dataframe_with_proxies,
)
from finbar_strategy_runtime.domain.services.vwap_bands import compute_vwap_session_bands
from finbar_strategy_runtime.domain.services.volume_profile import (
    compute_all_session_volume_profiles,
    compute_rolling_vp,
    compute_rolling_window_vp,
)
from finbar_strategy_runtime.domain.services.composite_vp import (
    compute_composite_vp,
)
from finbar_strategy_runtime.domain.services.market_profile import (
    compute_all_session_market_profiles,
)
from finbar_strategy_runtime.domain.services.auction_state import (
    classify_auction_state,
)
from finbar_strategy_runtime.domain.services.coil_detector import (
    detect_coil,
)
from finbar_strategy_runtime.domain.services.profile_shape import (
    classify_all_profile_shapes,
)
from finbar_strategy_runtime.domain.services.wyckoff_phase import (
    classify_wyckoff_phase,
)
from finbar_strategy_runtime.domain.services.wyckoff_wrappers import (
    compute_is_accumulation,
    compute_is_markup,
    compute_is_distribution,
    compute_is_markdown,
    compute_is_wyckoff_neutral,
)
from finbar_strategy_runtime.domain.services.profile_shape_wrappers import (
    compute_is_normal_shape,
    compute_is_b_shape,
    compute_is_p_shape,
    compute_is_d_shape,
    compute_is_neutral_shape,
)
from finbar_strategy_runtime.domain.services.amt_signals import (
    compute_amt_signals,
)

logger = logging.getLogger(__name__)

# Minimum bars for meaningful indicator output.
MIN_BARS = 10


# ---------------------------------------------------------------------------
# Safe pandas_ta wrapper
# ---------------------------------------------------------------------------


def _safe_ta(func: Callable, *args, **kwargs) -> pd.Series | None:
    """Call a pandas_ta function and return None-safe result.

    pandas_ta returns None when there are fewer bars than the requested
    period length. This helper converts None to a NaN-filled Series.
    """
    try:
        result = func(*args, **kwargs)
    except Exception:
        result = None
    if result is None:
        series = args[0] if args else kwargs.get("close")
        if series is not None and isinstance(series, pd.Series):
            return pd.Series(float("nan"), index=series.index, dtype="float64")
        return None
    return result


# ---------------------------------------------------------------------------
# Indicator dispatch table
# ---------------------------------------------------------------------------

# Each entry maps an indicator name to a (handler, requires_columns) tuple.
# The dispatcher calls the handler only if all required columns are present.
_INDICATOR_HANDLERS: dict[str, tuple[Callable, set[str]]] = {}


def _register(name: str, requires: set[str] | None = None):
    """Decorator to register an indicator handler.

    Populates ``_INDICATOR_HANDLERS`` which ``UnifiedMetricCatalog`` reads
    at construction time to determine which metrics are computable.
    """

    def decorator(func: Callable):
        _INDICATOR_HANDLERS[name] = (func, requires or set())
        return func

    return decorator


# ---------------------------------------------------------------------------
# PandasTaIndicatorCalculator
# ---------------------------------------------------------------------------


class PandasTaIndicatorCalculator(IndicatorCalculator):
    """pandas_ta-backed technical indicator calculator.

    Implements the IndicatorCalculator domain interface. Supports:
    - Real indicators: rsi_7, rsi_14, sma_20, sma_50, sma_200, macd, etc.
    - Proxy indicators: proxy_ibs, proxy_parkinson, proxy_typical_price, etc.
    - Trend indicators: trend_direction, trend_strength, trend_status
    - Support/resistance: swing_high_20, breakout_signal, breakout_quality
    """

    def calculate(self, df: pd.DataFrame, indicators: list[str]) -> pd.DataFrame:
        """Apply requested indicators and return enriched DataFrame.

        Args:
            df: DataFrame with columns [open, high, low, close, volume]
                and a datetime index.
            indicators: List of indicator names to compute.

        Returns:
            DataFrame with original columns plus requested indicator columns.
        """
        if df.empty or not indicators:
            return df.copy()

        result = df.copy()

        if len(result) < MIN_BARS:
            logger.warning(
                "Only %d bars (minimum %d), skipping indicators",
                len(result),
                MIN_BARS,
            )
            return result

        # Cache for compound indicators that share computation
        cache: dict[str, pd.DataFrame] = {}
        # Compute column set once to avoid per-indicator set construction
        present_cols = set(result.columns)

        for name in indicators:
            if name.startswith("proxy_"):
                result = _compute_proxies(result, cache)
                present_cols = set(result.columns)
            elif name in _INDICATOR_HANDLERS:
                handler, requires = _INDICATOR_HANDLERS[name]
                if requires and requires - present_cols:
                    # Invariant #2: column must exist (all-NaN), not be absent
                    result[name] = np.nan
                    logger.debug(
                        "Missing columns for '%s': %s, wrote NaN",
                        name,
                        requires - present_cols,
                    )
                    present_cols = set(result.columns)
                    continue
                try:
                    result = handler(result, name, cache)
                    present_cols = set(result.columns)
                except Exception:
                    # Invariant #2: column must exist (all-NaN), not be absent
                    result[name] = np.nan
                    present_cols = set(result.columns)
                    logger.warning(
                        "Failed to compute indicator '%s'", name, exc_info=True
                    )
            elif _is_dynamic(name):
                try:
                    result = _compute_dynamic(result, name)
                    present_cols = set(result.columns)
                except Exception:
                    logger.warning(
                        "Failed to compute dynamic indicator '%s'",
                        name,
                        exc_info=True,
                    )
            elif _is_rolling_vp(name):
                try:
                    result = _compute_rolling_vp_dynamic(result, name, cache)
                    present_cols = set(result.columns)
                except Exception:
                    logger.warning(
                        "Failed to compute rolling VP '%s'",
                        name,
                        exc_info=True,
                    )
            else:
                logger.warning("Unknown indicator: '%s'", name)

        return result


# ---------------------------------------------------------------------------
# Proxy indicators — delegates to domain service
# ---------------------------------------------------------------------------

_PROXY_CACHE_KEY = "__proxies_done"


def _compute_proxies(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Compute all proxy indicators in one batch (delegates to domain module).

    Uses a sentinel key in the per-call cache to avoid recomputing
    across multiple proxy indicator requests in the same calculate() call.
    """
    if _PROXY_CACHE_KEY in cache:
        return df
    result = enrich_dataframe_with_proxies(df)
    cache[_PROXY_CACHE_KEY] = True
    return result


# ---------------------------------------------------------------------------
# Individual indicator handlers (registered via @_register)
# ---------------------------------------------------------------------------


@_register("rsi_7")
def _rsi_7(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["rsi_7"] = _safe_ta(ta.rsi, df["close"], length=7)
    return df


@_register("rsi_14")
def _rsi_14(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["rsi_14"] = _safe_ta(ta.rsi, df["close"], length=14)
    return df


@_register("sma_10")
def _sma_10(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["sma_10"] = _safe_ta(ta.sma, df["close"], length=10)
    return df


@_register("sma_20")
def _sma_20(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["sma_20"] = _safe_ta(ta.sma, df["close"], length=20)
    return df


@_register("sma_30")
def _sma_30(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["sma_30"] = _safe_ta(ta.sma, df["close"], length=30)
    return df


@_register("sma_50")
def _sma_50(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["sma_50"] = _safe_ta(ta.sma, df["close"], length=50)
    return df


@_register("sma_200")
def _sma_200(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["sma_200"] = _safe_ta(ta.sma, df["close"], length=200)
    return df


@_register("ema_12")
def _ema_12(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["ema_12"] = _safe_ta(ta.ema, df["close"], length=12)
    return df


@_register("ema_26")
def _ema_26(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["ema_26"] = _safe_ta(ta.ema, df["close"], length=26)
    return df


@_register("macd")
def _macd(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    """Compute MACD, signal line, and histogram in one call.

    Caches the result so subsequent requests for macd_signal / macd_hist
    don't recompute.
    """
    if "macd" in cache:
        macd_df = cache["macd"]
    else:
        macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd_df is None:
            return df
        cache["macd"] = macd_df
    df["macd"] = macd_df.get("MACD_12_26_9")
    return df


@_register("macd_signal")
def _macd_signal(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    if "macd" not in cache:
        macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd_df is None:
            return df
        cache["macd"] = macd_df
    df["macd_signal"] = cache["macd"].get("MACDs_12_26_9")
    return df


@_register("macd_hist")
def _macd_hist(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    if "macd" not in cache:
        macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd_df is None:
            return df
        cache["macd"] = macd_df
    df["macd_hist"] = cache["macd"].get("MACDh_12_26_9")
    return df


@_register("atr")
def _atr(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["atr"] = _safe_ta(ta.atr, df["high"], df["low"], df["close"], length=14)
    return df


@_register("adx")
def _adx(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    if adx_df is not None and "ADX_14" in adx_df.columns:
        df["adx"] = adx_df["ADX_14"]
    return df


@_register("vwap")
def _vwap(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["vwap"] = _safe_ta(ta.vwap, df["high"], df["low"], df["close"], df["volume"])
    return df


@_register("bb_upper", requires={"close"})
def _bb_upper(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    if "bb" not in cache:
        cache["bb"] = ta.bbands(df["close"], length=20, std=2)
        if cache["bb"] is None:
            cache["bb"] = pd.DataFrame()
    bb = cache["bb"]
    if not bb.empty:
        bb_cols = [c for c in bb.columns if c.startswith("BBU_")]
        if bb_cols:
            df["bb_upper"] = bb[bb_cols[0]]
    return df


@_register("bb_middle", requires={"close"})
def _bb_middle(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    if "bb" not in cache:
        cache["bb"] = ta.bbands(df["close"], length=20, std=2)
        if cache["bb"] is None:
            cache["bb"] = pd.DataFrame()
    bb = cache["bb"]
    if not bb.empty:
        bb_cols = [c for c in bb.columns if c.startswith("BBM_")]
        if bb_cols:
            df["bb_middle"] = bb[bb_cols[0]]
    return df


@_register("bb_lower", requires={"close"})
def _bb_lower(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    if "bb" not in cache:
        cache["bb"] = ta.bbands(df["close"], length=20, std=2)
        if cache["bb"] is None:
            cache["bb"] = pd.DataFrame()
    bb = cache["bb"]
    if not bb.empty:
        bb_cols = [c for c in bb.columns if c.startswith("BBL_")]
        if bb_cols:
            df["bb_lower"] = bb[bb_cols[0]]
    return df


@_register("ibs")
def _ibs(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    price_range = df["high"] - df["low"]
    df["ibs"] = (df["close"] - df["low"]) / price_range.replace(0, pd.NA)
    return df


@_register("rvol")
def _rvol(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    vol_sma = _safe_ta(ta.sma, df["volume"], length=20)
    if vol_sma is not None:
        df["rvol"] = df["volume"] / vol_sma.replace(0, pd.NA)
    return df


@_register("ker")
def _ker(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["ker"] = _safe_ta(ta.er, df["close"], length=10)
    return df


@_register("kama")
def _kama(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["kama"] = _safe_ta(ta.kama, df["close"], length=10)
    return df


# ---------------------------------------------------------------------------
# Trend indicators (require SMA columns to be computed first)
# ---------------------------------------------------------------------------


@_register("price_vs_sma20", requires={"sma_20"})
def _price_vs_sma20(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["price_vs_sma20"] = "AT"
    mask = df["sma_20"].notna()
    df.loc[mask & (df["close"] > df["sma_20"]), "price_vs_sma20"] = "ABOVE"
    df.loc[mask & (df["close"] < df["sma_20"]), "price_vs_sma20"] = "BELOW"
    return df


@_register(
    "trend_direction",
    requires={"sma_20", "sma_50", "sma_200"},
)
def _trend_direction(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["trend_direction"] = "NEUTRAL"
    mask = df["sma_200"].notna()
    bull = (
        mask
        & (df["sma_20"] > df["sma_50"])
        & (df["sma_50"] > df["sma_200"])
        & (df["close"] > df["sma_20"])
    )
    bear = (
        mask
        & (df["sma_20"] < df["sma_50"])
        & (df["sma_50"] < df["sma_200"])
        & (df["close"] < df["sma_20"])
    )
    df.loc[bull, "trend_direction"] = "BULLISH"
    df.loc[bear, "trend_direction"] = "BEARISH"
    return df


@_register("trend_strength", requires={"adx"})
def _trend_strength(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["trend_strength"] = "MODERATE"
    df.loc[df["adx"] > 25, "trend_strength"] = "STRONG"
    df.loc[df["adx"] < 20, "trend_strength"] = "WEAK"
    return df


@_register("trend_status", requires={"adx", "trend_direction"})
def _trend_status(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["trend_status"] = "TRANSITION"
    trending = (df["adx"] > 25) & df["trend_direction"].isin(["BULLISH", "BEARISH"])
    ranging = (df["adx"] < 20) | (df["trend_direction"] == "NEUTRAL")
    df.loc[trending, "trend_status"] = "TRENDING"
    df.loc[ranging, "trend_status"] = "RANGING"
    return df


# ---------------------------------------------------------------------------
# Support / resistance indicators
# ---------------------------------------------------------------------------


@_register("swing_high_20")
def _swing_high_20(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["swing_high_20"] = df["high"].rolling(window=20, min_periods=5).max()
    return df


@_register("swing_low_20")
def _swing_low_20(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["swing_low_20"] = df["low"].rolling(window=20, min_periods=5).min()
    return df


@_register("breakout_level", requires={"swing_high_20"})
def _breakout_level(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    if "bb_upper" in df.columns and df["bb_upper"].notna().any():
        df["breakout_level"] = df["bb_upper"].fillna(df["swing_high_20"])
        df["breakout_level_type"] = "BB_UPPER"
    else:
        df["breakout_level"] = df["swing_high_20"]
        df["breakout_level_type"] = "SWING_HIGH"
    return df


@_register("breakout_signal", requires={"breakout_level", "swing_low_20"})
def _breakout_signal(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["breakout_signal"] = "NONE"
    df.loc[df["close"] > df["breakout_level"], "breakout_signal"] = "BREAKOUT_UP"
    df.loc[df["close"] < df["swing_low_20"], "breakout_signal"] = "BREAKOUT_DOWN"
    return df


@_register("is_power_zone", requires={"swing_high_20"})
def _is_power_zone(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    if "bb_upper" in df.columns:
        safe_swing = df["swing_high_20"].replace(0, pd.NA)
        diff = (df["swing_high_20"] - df["bb_upper"]).abs() / safe_swing
        df["is_power_zone"] = (diff <= 0.005).fillna(False)
    else:
        df["is_power_zone"] = False
    return df


@_register("breakout_quality", requires={"rvol", "ibs", "breakout_signal"})
def _breakout_quality(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["breakout_quality"] = "LOW"
    high_q = (
        (df["rvol"] > 1.5)
        & (df["ibs"] > 0.7)
        & (df["breakout_signal"] == "BREAKOUT_UP")
    )
    medium_q = (
        (df["rvol"] > 1.0)
        & (df["ibs"] > 0.5)
        & (df["breakout_signal"] == "BREAKOUT_UP")
    )
    df.loc[medium_q, "breakout_quality"] = "MEDIUM"
    df.loc[high_q, "breakout_quality"] = "HIGH"
    return df


# ---------------------------------------------------------------------------
# Volatility buffer
# ---------------------------------------------------------------------------


@_register("vol_buffer_high", requires={"atr"})
def _vol_buffer_high(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["vol_buffer_high"] = df["open"] + (df["atr"] * 0.1)
    return df


@_register("vol_buffer_low", requires={"atr"})
def _vol_buffer_low(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    df["vol_buffer_low"] = df["open"] - (df["atr"] * 0.1)
    return df


# ---------------------------------------------------------------------------
# True Initial Balance — grouped by date from intraday bars
# ---------------------------------------------------------------------------

# Bars per initial balance period for common intervals.
# 5min: 12 bars = 1 hour. 15min: 4 bars. 30min: 2 bars. 1h: 1 bar.
_IB_BARS_MAP = {"5min": 12, "15min": 4, "30min": 2, "1h": 1}
_DEFAULT_IB_BARS = 2
_IB_MINUTES_MAP = {"5min": 5, "15min": 15, "30min": 30, "1h": 60}


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


@_register("proxy_atr")
def _proxy_atr(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    """Wilder RMA ATR from high/low/close."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1).fillna(close)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    df["proxy_atr"] = atr
    return df


@_register("proxy_vwap")
def _proxy_vwap(df: pd.DataFrame, _name: str, _cache: dict) -> pd.DataFrame:
    """Typical price as VWAP proxy."""
    df["proxy_vwap"] = (df["high"] + df["low"] + df["close"]) / 3.0
    return df


# ---------------------------------------------------------------------------
# VWAP Standard Deviation Bands — session-scoped (Auction Market Theory)
# ---------------------------------------------------------------------------

_VWAP_BANDS_CACHE_KEY = "__vwap_bands_done"


@_register("vwap_upper_1")
def _vwap_upper_1(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_vwap_bands(df, cache)


@_register("vwap_lower_1")
def _vwap_lower_1(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_vwap_bands(df, cache)


@_register("vwap_upper_2")
def _vwap_upper_2(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_vwap_bands(df, cache)


@_register("vwap_lower_2")
def _vwap_lower_2(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_vwap_bands(df, cache)


def _compute_vwap_bands(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Compute session-scoped VWAP and its SD bands (cached across calls)."""
    if _VWAP_BANDS_CACHE_KEY in cache:
        return df
    result = compute_vwap_session_bands(df)
    cache[_VWAP_BANDS_CACHE_KEY] = True
    # Copy columns back to original df
    for col in (
        "vwap_session",
        "vwap_upper_1",
        "vwap_lower_1",
        "vwap_upper_2",
        "vwap_lower_2",
    ):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Proxy Volume Profile — POC/VAH/VAL (Auction Market Theory)
# ---------------------------------------------------------------------------

_VP_CACHE_KEY = "__volume_profile_done"


@_register("vp_poc")
def _vp_poc(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_volume_profile(df, cache)


@_register("vp_vah")
def _vp_vah(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_volume_profile(df, cache)


@_register("vp_val")
def _vp_val(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_volume_profile(df, cache)


def _compute_volume_profile(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Compute session Volume Profile (POC/VAH/VAL), cached across calls."""
    if _VP_CACHE_KEY in cache:
        return df
    result = compute_all_session_volume_profiles(df)
    cache[_VP_CACHE_KEY] = True
    for col in ("vp_poc", "vp_vah", "vp_val"):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Rolling / Composite Volume Profile
# ---------------------------------------------------------------------------

_ROLLING_VP_CACHE_KEY = "__rolling_vp_done"

# Parameterized rolling VP prefixes for dynamic resolution
_ROLLING_VP_PREFIXES = {"vp_poc_", "vp_vah_", "vp_val_"}
# Rolling-window VP prefixes (bar-based, for crypto/24-7 markets)
_RVP_PREFIXES = {"rvp_poc_", "rvp_vah_", "rvp_val_"}
_CVP_PREFIXES = {"cvp_poc_", "cvp_vah_", "cvp_val_"}


@_register("vp_poc_5d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_poc_5d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 5)
    return df


@_register("vp_vah_5d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_vah_5d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 5)
    return df


@_register("vp_val_5d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_val_5d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 5)
    return df


@_register("vp_poc_20d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_poc_20d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 20)
    return df


@_register("vp_vah_20d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_vah_20d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 20)
    return df


@_register("vp_val_20d", requires={"vp_poc", "vp_vah", "vp_val"})
def _vp_val_20d(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_vp(df, cache, 20)
    return df


def _compute_rolling_vp(df: pd.DataFrame, cache: dict, window: int) -> pd.DataFrame:
    """Compute rolling VP composites for a specific window (cached)."""
    cache_key = f"{_ROLLING_VP_CACHE_KEY}_{window}"
    if cache_key in cache:
        return df
    result = compute_rolling_vp(df, window=window)
    cache[cache_key] = True
    for col in (f"vp_poc_{window}d", f"vp_vah_{window}d", f"vp_val_{window}d"):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Rolling-window Volume Profile — bar-based windows (crypto / 24-7 markets)
# ---------------------------------------------------------------------------

_RVP_CACHE_KEY = "__rolling_window_vp_done"


@_register("rvp_poc_48")
def _rvp_poc_48(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 48)
    return df


@_register("rvp_vah_48")
def _rvp_vah_48(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 48)
    return df


@_register("rvp_val_48")
def _rvp_val_48(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 48)
    return df


@_register("rvp_poc_96")
def _rvp_poc_96(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 96)
    return df


@_register("rvp_vah_96")
def _rvp_vah_96(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 96)
    return df


@_register("rvp_val_96")
def _rvp_val_96(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 96)
    return df


@_register("rvp_poc_336")
def _rvp_poc_336(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 336)
    return df


@_register("rvp_vah_336")
def _rvp_vah_336(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 336)
    return df


@_register("rvp_val_336")
def _rvp_val_336(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    _compute_rolling_window_vp(df, cache, 336)
    return df


def _compute_rolling_window_vp(
    df: pd.DataFrame, cache: dict, window_bars: int
) -> pd.DataFrame:
    """Compute rolling-window VP for a specific bar count (cached)."""
    cache_key = f"{_RVP_CACHE_KEY}_{window_bars}"
    if cache_key in cache:
        return df
    result = compute_rolling_window_vp(df, window_bars=window_bars)
    cache[cache_key] = True
    for col in (
        f"rvp_poc_{window_bars}",
        f"rvp_vah_{window_bars}",
        f"rvp_val_{window_bars}",
    ):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Composite Volume Profile
# ---------------------------------------------------------------------------

_CVP_CACHE_KEY = "__composite_vp_done"


@_register("cvp_poc_5d")
def _cvp_poc_5d(df, _name, cache):
    _compute_composite_vp(df, cache, 5)
    return df


@_register("cvp_vah_5d")
def _cvp_vah_5d(df, _name, cache):
    _compute_composite_vp(df, cache, 5)
    return df


@_register("cvp_val_5d")
def _cvp_val_5d(df, _name, cache):
    _compute_composite_vp(df, cache, 5)
    return df


@_register("cvp_poc_10d")
def _cvp_poc_10d(df, _name, cache):
    _compute_composite_vp(df, cache, 10)
    return df


@_register("cvp_vah_10d")
def _cvp_vah_10d(df, _name, cache):
    _compute_composite_vp(df, cache, 10)
    return df


@_register("cvp_val_10d")
def _cvp_val_10d(df, _name, cache):
    _compute_composite_vp(df, cache, 10)
    return df


@_register("cvp_poc_20d")
def _cvp_poc_20d(df, _name, cache):
    _compute_composite_vp(df, cache, 20)
    return df


@_register("cvp_vah_20d")
def _cvp_vah_20d(df, _name, cache):
    _compute_composite_vp(df, cache, 20)
    return df


@_register("cvp_val_20d")
def _cvp_val_20d(df, _name, cache):
    _compute_composite_vp(df, cache, 20)
    return df


def _compute_composite_vp(df, cache, window):
    cache_key = f"{_CVP_CACHE_KEY}_{window}"
    if cache_key in cache:
        return df
    result = compute_composite_vp(df, window=window)
    cache[cache_key] = True
    for col in (f"cvp_poc_{window}d", f"cvp_vah_{window}d", f"cvp_val_{window}d"):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Profile Shape Classifier
# ---------------------------------------------------------------------------


@_register("profile_shape")
def _profile_shape(df, _name, cache):
    if "__profile_shape_done" in cache:
        return df
    result = classify_all_profile_shapes(df)
    cache["__profile_shape_done"] = True
    if "profile_shape" in result.columns:
        df["profile_shape"] = result["profile_shape"]
    return df


# ---------------------------------------------------------------------------
# Coil / Squeeze Detector
# ---------------------------------------------------------------------------


@_register("is_coiled")
def _is_coiled(df, _name, cache):
    return _compute_coil(df, cache)


@_register("coil_intensity")
def _coil_intensity(df, _name, cache):
    return _compute_coil(df, cache)


def _compute_coil(df, cache):
    if "__coil_done" in cache:
        return df
    result = detect_coil(df)
    cache["__coil_done"] = True
    for col in ("is_coiled", "coil_intensity"):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Wyckoff Phase Classifier
# ---------------------------------------------------------------------------


@_register("wyckoff_phase", requires={"profile_shape"})
def _wyckoff_phase(df, _name, cache):
    return _compute_wyckoff(df, cache)


@_register("poc_slope_5", requires={"vp_poc"})
def _poc_slope_5(df, _name, cache):
    return _compute_wyckoff(df, cache)


@_register("poc_slope_20", requires={"vp_poc"})
def _poc_slope_20(df, _name, cache):
    return _compute_wyckoff(df, cache)


def _compute_wyckoff(df, cache):
    if "__wyckoff_done" in cache:
        return df
    if "__profile_shape_done" not in cache and "profile_shape" not in df.columns:
        df = _profile_shape(df, "profile_shape", cache)
    result = classify_wyckoff_phase(df)
    cache["__wyckoff_done"] = True
    for col in ("wyckoff_phase", "poc_slope_5", "poc_slope_20"):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Wyckoff Phase Boolean Wrappers
# ---------------------------------------------------------------------------


@_register("is_accumulation")
def _is_accumulation(df, _name, cache):
    return _compute_wyckoff_wrappers(df, cache)


@_register("is_markup")
def _is_markup(df, _name, cache):
    return _compute_wyckoff_wrappers(df, cache)


@_register("is_distribution")
def _is_distribution(df, _name, cache):
    return _compute_wyckoff_wrappers(df, cache)


@_register("is_markdown")
def _is_markdown(df, _name, cache):
    return _compute_wyckoff_wrappers(df, cache)


@_register("is_wyckoff_neutral")
def _is_wyckoff_neutral(df, _name, cache):
    return _compute_wyckoff_wrappers(df, cache)


def _compute_wyckoff_wrappers(df, cache):
    if "__wyckoff_wrappers_done" in cache:
        return df
    if "__wyckoff_done" not in cache and "wyckoff_phase" not in df.columns:
        df = _wyckoff_phase(df, "wyckoff_phase", cache)
    result = compute_is_accumulation(df)
    result = compute_is_markup(result)
    result = compute_is_distribution(result)
    result = compute_is_markdown(result)
    result = compute_is_wyckoff_neutral(result)
    cache["__wyckoff_wrappers_done"] = True
    for col in (
        "is_accumulation",
        "is_markup",
        "is_distribution",
        "is_markdown",
        "is_wyckoff_neutral",
    ):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Profile Shape Boolean Wrappers
# ---------------------------------------------------------------------------


@_register("is_normal_shape")
def _is_normal_shape(df, _name, cache):
    return _compute_shape_wrappers(df, cache)


@_register("is_b_shape")
def _is_b_shape(df, _name, cache):
    return _compute_shape_wrappers(df, cache)


@_register("is_p_shape")
def _is_p_shape(df, _name, cache):
    return _compute_shape_wrappers(df, cache)


@_register("is_d_shape")
def _is_d_shape(df, _name, cache):
    return _compute_shape_wrappers(df, cache)


@_register("is_neutral_shape")
def _is_neutral_shape(df, _name, cache):
    return _compute_shape_wrappers(df, cache)


def _compute_shape_wrappers(df, cache):
    if "__shape_wrappers_done" in cache:
        return df
    if "__profile_shape_done" not in cache and "profile_shape" not in df.columns:
        df = _profile_shape(df, "profile_shape", cache)
    result = compute_is_normal_shape(df)
    result = compute_is_b_shape(result)
    result = compute_is_p_shape(result)
    result = compute_is_d_shape(result)
    result = compute_is_neutral_shape(result)
    cache["__shape_wrappers_done"] = True
    for col in (
        "is_normal_shape",
        "is_b_shape",
        "is_p_shape",
        "is_d_shape",
        "is_neutral_shape",
    ):
        if col in result.columns:
            df[col] = result[col]
    return df

# ---------------------------------------------------------------------------
# Market Profile — TPO-based POC/VAH/VAL (Auction Market Theory)
# ---------------------------------------------------------------------------

_MP_CACHE_KEY = "__market_profile_done"


@_register("mp_poc")
def _mp_poc(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_market_profile(df, cache)


@_register("mp_vah")
def _mp_vah(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_market_profile(df, cache)


@_register("mp_val")
def _mp_val(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_market_profile(df, cache)


def _compute_market_profile(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Compute session Market Profile (TPO-based POC/VAH/VAL), cached."""
    if _MP_CACHE_KEY in cache:
        return df
    result = compute_all_session_market_profiles(df)
    cache[_MP_CACHE_KEY] = True
    for col in ("mp_poc", "mp_vah", "mp_val"):
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Auction State Classifiers (Auction Market Theory)
# ---------------------------------------------------------------------------

_AUCTION_STATE_CACHE_KEY = "__auction_state_done"


@_register("inside_value", requires={"vp_vah", "vp_val"})
def _inside_value(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("above_value", requires={"vp_vah"})
def _above_value(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("below_value", requires={"vp_val"})
def _below_value(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("at_poc", requires={"vp_poc", "vp_vah", "vp_val"})
def _at_poc(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("near_vah", requires={"vp_vah", "vp_val"})
def _near_vah(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("near_val", requires={"vp_vah", "vp_val"})
def _near_val(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("distance_to_vah_pct", requires={"vp_vah"})
def _distance_to_vah_pct(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("distance_to_val_pct", requires={"vp_val"})
def _distance_to_val_pct(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("value_area_width_pct", requires={"vp_vah", "vp_val"})
def _value_area_width_pct(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


@_register("balance_status", requires={"vp_vah", "vp_val"})
def _balance_status(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_auction_state(df, cache)


def _compute_auction_state(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Compute all auction state classifiers (cached across calls)."""
    if _AUCTION_STATE_CACHE_KEY in cache:
        return df
    result = classify_auction_state(df)
    cache[_AUCTION_STATE_CACHE_KEY] = True
    auction_cols = [
        "inside_value",
        "above_value",
        "below_value",
        "at_poc",
        "near_vah",
        "near_val",
        "distance_to_vah_pct",
        "distance_to_val_pct",
        "value_area_width_pct",
        "balance_status",
    ]
    for col in auction_cols:
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# AMT Rule Signals (Auction Market Theory)
# ---------------------------------------------------------------------------

_AMT_SIGNALS_CACHE_KEY = "__amt_signals_done"


@_register("acceptance_into_value", requires={"vp_vah", "vp_val"})
def _acceptance_into_value(
    df: pd.DataFrame, _name: str, cache: dict
) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


@_register("rejection_from_edge", requires={"vp_vah", "vp_val"})
def _rejection_from_edge(
    df: pd.DataFrame, _name: str, cache: dict
) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


@_register("acceptance_outside_value", requires={"vp_vah", "vp_val"})
def _acceptance_outside_value(
    df: pd.DataFrame, _name: str, cache: dict
) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


@_register("poc_rejection", requires={"vp_poc", "atr"})
def _poc_rejection(df: pd.DataFrame, _name: str, cache: dict) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


@_register("edge_volume_building", requires={"vp_vah", "vp_val", "rvol"})
def _edge_volume_building(
    df: pd.DataFrame, _name: str, cache: dict
) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


@_register("value_area_migration", requires={"vp_poc"})
def _value_area_migration(
    df: pd.DataFrame, _name: str, cache: dict
) -> pd.DataFrame:
    return _compute_amt_signals(df, cache)


def _compute_amt_signals(df: pd.DataFrame, cache: dict) -> pd.DataFrame:
    """Compute all AMT rule signals (cached across calls).

    Ensures auction state columns are computed first as dependencies.
    """
    if _AMT_SIGNALS_CACHE_KEY in cache:
        return df

    # Ensure auction state dependencies are satisfied
    if _AUCTION_STATE_CACHE_KEY not in cache:
        df = _compute_auction_state(df, cache)

    result = compute_amt_signals(df)
    cache[_AMT_SIGNALS_CACHE_KEY] = True

    amt_cols = [
        "acceptance_into_value",
        "rejection_from_edge",
        "acceptance_outside_value",
        "poc_rejection",
        "edge_volume_building",
        "value_area_migration",
    ]
    for col in amt_cols:
        if col in result.columns:
            df[col] = result[col]
    return df


# ---------------------------------------------------------------------------
# Dynamic period indicators — handles any period within supported ranges
# ---------------------------------------------------------------------------

_DYNAMIC_HANDLERS: dict[str, tuple[Callable, str]] = {
    "sma": (ta.sma, "close"),
    "ema": (ta.ema, "close"),
    "rsi": (ta.rsi, "close"),
    "atr": (ta.atr, "hlc"),
    "adx": (ta.adx, "hlc"),
    "bb_upper": (ta.bbands, "bb"),
    "bb_middle": (ta.bbands, "bb"),
    "bb_lower": (ta.bbands, "bb"),
}

# Precomputed prefix→(func, source) map to avoid per-call f-string allocations.
_DYNAMIC_PREFIXES: dict[str, tuple[Callable, str]] = {
    f"{prefix}_": (func, source)
    for prefix, (func, source) in _DYNAMIC_HANDLERS.items()
}


def _resolve_dynamic(
    name: str,
) -> tuple[Callable, str, int, str] | None:
    """Try to resolve a dynamic indicator name like sma_37.

    Returns (func, source_col, period, prefix) or None.
    The prefix is the matched key without trailing underscore (e.g. 'bb_upper').
    """
    for prefix_key, (func, source_col) in _DYNAMIC_PREFIXES.items():
        if name.startswith(prefix_key):
            period_str = name[len(prefix_key):]
            if period_str.isdigit():
                period = int(period_str)
                if period >= 2:
                    # Strip trailing underscore from prefix key
                    prefix = prefix_key[:-1]
                    return func, source_col, period, prefix
            return None
    return None


def _is_dynamic(name: str) -> bool:
    """Return True when a name matches a dynamic indicator like sma_37."""
    return _resolve_dynamic(name) is not None


def _compute_dynamic(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Compute a dynamic period indicator and add its column to the frame."""
    resolved = _resolve_dynamic(name)
    if resolved is None:
        return df

    func, source_col, period, prefix = resolved
    if source_col == "hlc":
        result = func(df["high"], df["low"], df["close"], length=period)
        if result is None:
            return df
        if isinstance(result, pd.Series):
            df[name] = result
        else:
            # ta.adx returns a DataFrame — extract the named column
            col = f"{prefix.upper()}_{period}"
            if col in result.columns:
                df[name] = result[col]
    elif source_col == "bb":
        result_df = func(df["close"], length=period, std=2)
        if result_df is not None:
            bb_col = _extract_bb_column(result_df, prefix, period)
            if bb_col:
                df[name] = result_df[bb_col]
    else:
        df[name] = _safe_ta(func, df[source_col], length=period)
    return df


def _extract_bb_column(result_df, prefix: str, period: int) -> str | None:
    """Extract the correct Bollinger Band column from a pandas_ta result."""
    mapping = {"bb_upper": "BBU", "bb_middle": "BBM", "bb_lower": "BBL"}
    bb_prefix = mapping.get(prefix, "")
    if not bb_prefix:
        return None
    for col in result_df.columns:
        if col.startswith(f"{bb_prefix}_{period}"):
            return col
    return None


# ---------------------------------------------------------------------------
# Parameterized Rolling Volume Profile — vp_poc_Nd, vp_vah_Nd, vp_val_Nd
# ---------------------------------------------------------------------------


def _is_rolling_vp(name: str) -> bool:
    """Return True when name matches rvp_poc_N, rvp_vah_N, or rvp_val_N.

    Accepts any positive integer N >= 1 (e.g. rvp_poc_48, rvp_vah_100).
    Also handles session-based vp_poc_Nd, vp_vah_Nd, vp_val_Nd.
    """
    all_prefixes = _ROLLING_VP_PREFIXES | _RVP_PREFIXES | _CVP_PREFIXES
    for prefix in all_prefixes:
        # Bar-based: rvp_poc_48
        if prefix in _RVP_PREFIXES and name.startswith(prefix):
            inner = name[len(prefix):]
            if inner.isdigit() and int(inner) >= 1:
                return True
        # Session-based / composite: vp_poc_10d, cvp_poc_10d
        if prefix in (_ROLLING_VP_PREFIXES | _CVP_PREFIXES) and name.startswith(prefix) and name.endswith("d"):
            inner = name[len(prefix):-1]
            if inner.isdigit() and int(inner) >= 1:
                return True
    return False


def _compute_rolling_vp_dynamic(
    df: pd.DataFrame, name: str, cache: dict
) -> pd.DataFrame:
    """Compute a parameterized rolling VP or RVP indicator.

    Parses the window from the indicator name:
    - rvp_poc_48 → rolling-window VP with 48 bars
    - vp_poc_10d → session-based rolling VP with 10 sessions
    """
    # Rolling-window VP (bar-based, crypto)
    for prefix in _RVP_PREFIXES:
        if name.startswith(prefix):
            inner = name[len(prefix):]
            if inner.isdigit():
                window_bars = int(inner)
                return _compute_rolling_window_vp(df, cache, window_bars)

    # Composite VP (true stacked, cvp_poc_10d)
    for prefix in _CVP_PREFIXES:
        if name.startswith(prefix) and name.endswith("d"):
            inner = name[len(prefix):-1]
            if inner.isdigit():
                window = int(inner)
                return _compute_composite_vp(df, cache, window)

    # Session-based rolling VP (vp_poc_10d)
    for prefix in _ROLLING_VP_PREFIXES:
        if name.startswith(prefix) and name.endswith("d"):
            inner = name[len(prefix):-1]
            window = int(inner)
            if "vp_poc" not in df.columns or "vp_vah" not in df.columns:
                return df
            return _compute_rolling_vp(df, cache, window)

    return df


# ===========================================================================
# Microstructure handlers — spread, volatility, liquidity, order flow,
# informed trading, jump risk, resiliency, seasonality, order arrival.
# Each handler wraps a pure domain-service calculator function.
# ===========================================================================

from finbar_strategy_runtime.domain.services.spread_proxies import (  # noqa: E402
    abdi_ranaldo_spread as _ar_calc,
    chung_zhang_spread as _cz_calc,
    corwin_schultz_spread as _cs_calc,
    effective_tick_spread as _et_calc,
    fong_holden_tran_spread as _fht_calc,
    lot_zero_return_spread as _lot_calc,
    roll_spread as _roll_calc,
)
from finbar_strategy_runtime.domain.services.volatility_estimators import (  # noqa: E402
    close_to_close_vol as _cc_vol,
    daily_return_kurtosis as _dr_kurt,
    daily_return_skewness as _dr_skew,
    garman_klass_vol as _gk_vol,
    gk_plus_overnight_vol as _gko_vol,
    meilijson_vol as _mj_vol,
    parkinson_vol as _pk_vol,
    rogers_satchell_vol as _rs_vol,
    yang_zhang_vol as _yz_vol,
)
from finbar_strategy_runtime.domain.services.liquidity_proxies import (  # noqa: E402
    amihud_illiq as _amihud,
    amivest_liquidity as _amivest,
    bao_pan_zhou_cost as _bpz,
    florackis_lambda as _flor,
    hasbrouck_daily_lambda as _hasb,
    liu_illiq as _liu,
)
from finbar_strategy_runtime.domain.services.order_flow_proxies import (  # noqa: E402
    bvc_buy_volume as _bvc_buy,
    bvc_ofi as _bvc_ofi,
    bvc_sell_volume as _bvc_sell,
    cumulative_signed_volume_ofi as _csv_ofi,
    return_volume_correlation as _rvc,
    signed_sqrt_volume_ofi as _ssq_ofi,
)
from finbar_strategy_runtime.domain.services.informed_trading_proxies import (  # noqa: E402
    daily_vpin as _vpin,
    spread_based_pin_proxy as _pin,
)
from finbar_strategy_runtime.domain.services.jump_risk_proxies import (  # noqa: E402
    cc_rs_jump_proxy as _cc_jump,
    extreme_return_flag as _ext_ret,
    jump_gap_proxy as _jump_gap,
    overnight_gap_proxy as _on_gap,
)
from finbar_strategy_runtime.domain.services.resiliency_proxies import (  # noqa: E402
    inverse_amihud_resiliency as _inv_amihud,
    resiliency_autocorr as _res_auto,
    resiliency_spread_to_impact as _res_si,
)
from finbar_strategy_runtime.domain.services.intraday_seasonality_proxies import (  # noqa: E402
    first_last_hour_vol_fraction as _flhvf,
    overnight_intraday_decomp as _oid,
    parametric_u_shape as _u_shape,
)
from finbar_strategy_runtime.domain.services.order_arrival_proxies import (  # noqa: E402
    trade_count_daily as _tc_daily,
    volume_to_trade_count_proxy as _vtc,
)
from finbar_strategy_runtime.indicators.rolling_scalar_wrapper import (  # noqa: E402
    rolling_scalar_series,
)


# --- Spread proxies (7) ---

@_register("corwin_schultz_spread", requires={"open", "high", "low", "close"})
def _h_corwin_schultz(df, _name, _cache):
    df["corwin_schultz_spread"] = _cs_calc(df)
    return df

@_register("roll_spread", requires={"close"})
def _h_roll_spread(df, _name, _cache):
    df["roll_spread"] = rolling_scalar_series(_roll_calc, df["close"])
    return df

@_register("abdi_ranaldo_spread", requires={"open", "high", "low", "close"})
def _h_abdi_ranaldo(df, _name, _cache):
    df["abdi_ranaldo_spread"] = _ar_calc(df)
    return df

@_register("effective_tick_spread", requires={"close"})
def _h_effective_tick(df, _name, _cache):
    df["effective_tick_spread"] = rolling_scalar_series(_et_calc, df["close"])
    return df

@_register("fong_holden_tran_spread", requires={"open", "high", "low", "close"})
def _h_fht_spread(df, _name, _cache):
    df["fong_holden_tran_spread"] = _fht_calc(df)
    return df

@_register("chung_zhang_spread", requires={"open", "high", "low", "close"})
def _h_chung_zhang(df, _name, _cache):
    df["chung_zhang_spread"] = _cz_calc(df)
    return df

@_register("lot_zero_return_spread", requires={"close"})
def _h_lot_spread(df, _name, _cache):
    df["lot_zero_return_spread"] = rolling_scalar_series(_lot_calc, df["close"])
    return df


# --- Volatility estimators (9) ---

@_register("close_to_close_vol", requires={"close"})
def _h_cc_vol(df, _name, _cache):
    df["close_to_close_vol"] = _cc_vol(df["close"])
    return df

@_register("parkinson_vol", requires={"high", "low"})
def _h_parkinson(df, _name, _cache):
    df["parkinson_vol"] = _pk_vol(df["high"], df["low"])
    return df

@_register("garman_klass_vol", requires={"open", "high", "low", "close"})
def _h_gk_vol(df, _name, _cache):
    df["garman_klass_vol"] = _gk_vol(df)
    return df

@_register("rogers_satchell_vol", requires={"open", "high", "low", "close"})
def _h_rs_vol(df, _name, _cache):
    df["rogers_satchell_vol"] = _rs_vol(df)
    return df

@_register("yang_zhang_vol", requires={"open", "high", "low", "close"})
def _h_yz_vol(df, _name, _cache):
    df["yang_zhang_vol"] = _yz_vol(df)
    return df

@_register("gk_plus_overnight_vol", requires={"open", "high", "low", "close"})
def _h_gko_vol(df, _name, _cache):
    df["gk_plus_overnight_vol"] = _gko_vol(df)
    return df

@_register("meilijson_vol", requires={"open", "high", "low", "close"})
def _h_mj_vol(df, _name, _cache):
    df["meilijson_vol"] = _mj_vol(df)
    return df

@_register("daily_return_skewness", requires={"close"})
def _h_dr_skew(df, _name, _cache):
    df["daily_return_skewness"] = _dr_skew(df["close"])
    return df

@_register("daily_return_kurtosis", requires={"close"})
def _h_dr_kurt(df, _name, _cache):
    df["daily_return_kurtosis"] = _dr_kurt(df["close"])
    return df


# --- Liquidity / impact (6; turnover excluded) ---

@_register("amihud_illiq", requires={"close", "volume"})
def _h_amihud(df, _name, _cache):
    df["amihud_illiq"] = _amihud(df)
    return df

@_register("amivest_liquidity", requires={"close", "volume"})
def _h_amivest(df, _name, _cache):
    df["amivest_liquidity"] = _amivest(df)
    return df

@_register("florackis_lambda", requires={"close", "volume"})
def _h_florackis(df, _name, _cache):
    df["florackis_lambda"] = _flor(df)
    return df

@_register("hasbrouck_daily_lambda", requires={"close", "volume"})
def _h_hasbrouck(df, _name, _cache):
    df["hasbrouck_daily_lambda"] = _hasb(df)
    return df

@_register("liu_illiq", requires={"volume"})
def _h_liu(df, _name, _cache):
    df["liu_illiq"] = rolling_scalar_series(_liu, df["volume"])
    return df

@_register("bao_pan_zhou_cost", requires={"close"})
def _h_bpz(df, _name, _cache):
    df["bao_pan_zhou_cost"] = rolling_scalar_series(_bpz, df["close"])
    return df


# --- Order flow (6) ---

@_register("signed_sqrt_volume_ofi", requires={"close", "volume"})
def _h_ssq_ofi(df, _name, _cache):
    df["signed_sqrt_volume_ofi"] = _ssq_ofi(df)
    return df

@_register("cumulative_signed_volume_ofi", requires={"close", "volume"})
def _h_csv_ofi(df, _name, _cache):
    df["cumulative_signed_volume_ofi"] = _csv_ofi(df)
    return df

@_register("bvc_buy_volume", requires={"close", "volume"})
def _h_bvc_buy(df, _name, _cache):
    df["bvc_buy_volume"] = _bvc_buy(df)
    return df

@_register("bvc_sell_volume", requires={"close", "volume"})
def _h_bvc_sell(df, _name, _cache):
    df["bvc_sell_volume"] = _bvc_sell(df)
    return df

@_register("bvc_ofi", requires={"close", "volume"})
def _h_bvc_ofi(df, _name, _cache):
    df["bvc_ofi"] = _bvc_ofi(df)
    return df

@_register("return_volume_correlation", requires={"close", "volume"})
def _h_rvc(df, _name, _cache):
    df["return_volume_correlation"] = _rvc(df)
    return df


# --- Informed trading (2) ---

@_register("daily_vpin", requires={"close", "volume"})
def _h_daily_vpin(df, _name, _cache):
    df["daily_vpin"] = _vpin(df)
    return df

@_register("spread_based_pin_proxy", requires={"close", "volume"})
def _h_pin_proxy(df, _name, _cache):
    df["spread_based_pin_proxy"] = _pin(df)
    return df



# --- Jump risk (4) ---

@_register("jump_gap_proxy", requires={"open", "high", "low", "close"})
def _h_jump_gap(df, _name, _cache):
    df["jump_gap_proxy"] = _jump_gap(df)
    return df

@_register("extreme_return_flag", requires={"close"})
def _h_ext_ret(df, _name, _cache):
    df["extreme_return_flag"] = _ext_ret(df["close"])
    return df

@_register("cc_rs_jump_proxy", requires={"open", "high", "low", "close"})
def _h_cc_jump(df, _name, _cache):
    df["cc_rs_jump_proxy"] = _cc_jump(df)
    return df

@_register("overnight_gap_proxy", requires={"open", "high", "low", "close"})
def _h_on_gap(df, _name, _cache):
    df["overnight_gap_proxy"] = _on_gap(df)
    return df


# --- Resiliency (3) ---

@_register("resiliency_autocorr", requires={"close"})
def _h_res_auto(df, _name, _cache):
    df["resiliency_autocorr"] = rolling_scalar_series(_res_auto, df["close"])
    return df

@_register("resiliency_spread_to_impact", requires={"close", "volume"})
def _h_res_si(df, _name, _cache):
    df["resiliency_spread_to_impact"] = _res_si(df)
    return df

@_register("inverse_amihud_resiliency", requires={"close", "volume"})
def _h_inv_amihud(df, _name, _cache):
    df["inverse_amihud_resiliency"] = _inv_amihud(df)
    return df


# --- Intraday seasonality (4) ---

@_register("overnight_return", requires={"open", "high", "low", "close"})
def _h_overnight_return(df, _name, _cache):
    overnight, _intraday = _oid(df)
    df["overnight_return"] = overnight
    return df

@_register("intraday_return", requires={"open", "high", "low", "close"})
def _h_intraday_return(df, _name, _cache):
    _overnight, intraday = _oid(df)
    df["intraday_return"] = intraday
    return df

@_register("parametric_u_shape", requires={"volume"})
def _h_u_shape(df, _name, _cache):
    df["parametric_u_shape"] = _u_shape(df["volume"])
    return df

@_register("first_last_hour_vol_fraction", requires={"close", "volume"})
def _h_flhvf(df, _name, _cache):
    df["first_last_hour_vol_fraction"] = _flhvf(df)
    return df


# --- Order arrival (2) ---

@_register("volume_to_trade_count_proxy", requires={"volume"})
def _h_vtc(df, _name, _cache):
    df["volume_to_trade_count_proxy"] = _vtc(df["volume"])
    return df

@_register("trade_count_daily", requires={"trade_count"})
def _h_tc_daily(df, _name, _cache):
    df["trade_count_daily"] = _tc_daily(df)
    return df


# ===========================================================================
# Price-action handlers — Fibonacci, Bill Williams, trend structure, SMC,
# VSA, supply/demand zones, Hurst regime, market regime.
# ===========================================================================

from finbar_strategy_runtime.domain.services.fibonacci_levels import (  # noqa: E402
    fib_1618_extension as _fib_ext,
    fib_382_retrace as _fib382,
    fib_500_retrace as _fib500,
    fib_618_retrace as _fib618,
    fib_confluence_score as _fib_conf,
)
from finbar_strategy_runtime.domain.services.bill_williams_indicators import (  # noqa: E402
    accelerator_oscillator as _ac_osc,
    alligator_lines as _alig_lines,
    alligator_status as _alig_status,
    awesome_oscillator as _ao_osc,
    williams_fractal_high as _frac_high,
    williams_fractal_low as _frac_low,
    zone_signal as _bw_zone,
)
from finbar_strategy_runtime.domain.services.trend_structure import (  # noqa: E402
    hh_hl_pattern as _hh_hl,
    lh_ll_pattern as _lh_ll,
    swing_high_n as _swing_h,
    swing_low_n as _swing_l,
    trend_phase as _trend_phase,
    volume_trend_confirmation as _vol_trend,
)
from finbar_strategy_runtime.domain.services.smc_price_action import (  # noqa: E402
    bearish_fvg as _bear_fvg,
    bearish_order_block as _bear_ob,
    bos as _bos,
    breaker_block_bearish as _breaker_bear,
    breaker_block_bullish as _breaker_bull,
    bullish_fvg as _bull_fvg,
    bullish_order_block as _bull_ob,
    choch as _choch,
    liquidity_sweep_high as _sweep_high,
    liquidity_sweep_low as _sweep_low,
    premium_discount_zone as _pd_zone,
)
from finbar_strategy_runtime.domain.services.vsa_signals import (  # noqa: E402
    bag_holding as _bag_hold,
    climax_volume as _climax,
    effort_result_divergence as _er_div,
    effort_to_fall as _eff_fall,
    effort_to_rise as _eff_rise,
    no_demand as _no_dem,
    no_supply as _no_sup,
    shakeout as _shakeout,
    stopping_volume as _stop_vol,
    vsa_test_signal as _vsa_test,
)
from finbar_strategy_runtime.domain.services.supply_demand_zones import (  # noqa: E402
    demand_zone_high as _dz_high,
    demand_zone_low as _dz_low,
    demand_zone_score as _dz_score,
    supply_zone_high as _sz_high,
    supply_zone_low as _sz_low,
    supply_zone_score as _sz_score,
    zone_failure_bearish as _zf_bear,
    zone_failure_bullish as _zf_bull,
)
from finbar_strategy_runtime.domain.services.hurst_regime import (  # noqa: E402
    fractal_regime as _frac_regime,
    hurst_exponent as _hurst,
)
from finbar_strategy_runtime.domain.services.market_regime import (  # noqa: E402
    day_type_classification as _day_type,
    market_regime as _mkt_regime,
)


# --- Fibonacci (5) ---

@_register("fib_382_retrace", requires={"close"})
def _h_fib382(df, _name, _cache):
    df["fib_382_retrace"] = _fib382(df["close"])
    return df

@_register("fib_500_retrace", requires={"close"})
def _h_fib500(df, _name, _cache):
    df["fib_500_retrace"] = _fib500(df["close"])
    return df

@_register("fib_618_retrace", requires={"close"})
def _h_fib618(df, _name, _cache):
    df["fib_618_retrace"] = _fib618(df["close"])
    return df

@_register("fib_1618_extension", requires={"close"})
def _h_fib_ext(df, _name, _cache):
    df["fib_1618_extension"] = _fib_ext(df["close"])
    return df

@_register("fib_confluence_score", requires={"close"})
def _h_fib_conf(df, _name, _cache):
    df["fib_confluence_score"] = _fib_conf(df["close"])
    return df


# --- Bill Williams (9: 6 single + alligator 3) ---

@_register("awesome_oscillator", requires={"high", "low"})
def _h_ao(df, _name, _cache):
    df["awesome_oscillator"] = _ao_osc(df["high"], df["low"])
    return df

@_register("accelerator_oscillator", requires={"high", "low"})
def _h_ac(df, _name, _cache):
    df["accelerator_oscillator"] = _ac_osc(df["high"], df["low"])
    return df

@_register("alligator_jaw", requires={"high", "low"})
def _h_alig_jaw(df, _name, _cache):
    jaw, _teeth, _lips = _alig_lines(df["high"], df["low"])
    df["alligator_jaw"] = jaw
    return df

@_register("alligator_teeth", requires={"high", "low"})
def _h_alig_teeth(df, _name, _cache):
    _jaw, teeth, _lips = _alig_lines(df["high"], df["low"])
    df["alligator_teeth"] = teeth
    return df

@_register("alligator_lips", requires={"high", "low"})
def _h_alig_lips(df, _name, _cache):
    _jaw, _teeth, lips = _alig_lines(df["high"], df["low"])
    df["alligator_lips"] = lips
    return df

@_register("alligator_status", requires={"high", "low"})
def _h_alig_status(df, _name, _cache):
    jaw, teeth, lips = _alig_lines(df["high"], df["low"])
    df["alligator_status"] = _alig_status(jaw, teeth, lips)
    return df

@_register("williams_fractal_high", requires={"high"})
def _h_frac_high(df, _name, _cache):
    df["williams_fractal_high"] = _frac_high(df["high"])
    return df

@_register("williams_fractal_low", requires={"low"})
def _h_frac_low(df, _name, _cache):
    df["williams_fractal_low"] = _frac_low(df["low"])
    return df

@_register("zone_signal", requires={"high", "low"})
def _h_bw_zone(df, _name, _cache):
    df["zone_signal"] = _bw_zone(df["high"], df["low"])
    return df


# --- Trend structure (6) ---

@_register("swing_high_n", requires={"high"})
def _h_swing_h(df, _name, _cache):
    df["swing_high_n"] = _swing_h(df["high"])
    return df

@_register("swing_low_n", requires={"low"})
def _h_swing_l(df, _name, _cache):
    df["swing_low_n"] = _swing_l(df["low"])
    return df

@_register("hh_hl_pattern", requires={"high", "low"})
def _h_hh_hl(df, _name, _cache):
    df["hh_hl_pattern"] = _hh_hl(df["high"], df["low"])
    return df

@_register("lh_ll_pattern", requires={"high", "low"})
def _h_lh_ll(df, _name, _cache):
    df["lh_ll_pattern"] = _lh_ll(df["high"], df["low"])
    return df

@_register("volume_trend_confirmation", requires={"close", "volume"})
def _h_vol_trend(df, _name, _cache):
    df["volume_trend_confirmation"] = _vol_trend(df["close"], df["volume"])
    return df

@_register("trend_phase", requires={"close", "volume"})
def _h_trend_phase(df, _name, _cache):
    df["trend_phase"] = _trend_phase(df["close"], df["volume"])
    return df


# --- SMC (11) ---

@_register("bullish_fvg", requires={"high", "low"})
def _h_bull_fvg(df, _name, _cache):
    df["bullish_fvg"] = _bull_fvg(df["high"], df["low"])
    return df

@_register("bearish_fvg", requires={"high", "low"})
def _h_bear_fvg(df, _name, _cache):
    df["bearish_fvg"] = _bear_fvg(df["high"], df["low"])
    return df

@_register("bullish_order_block", requires={"close"})
def _h_bull_ob(df, _name, _cache):
    df["bullish_order_block"] = _bull_ob(df["close"])
    return df

@_register("bearish_order_block", requires={"close"})
def _h_bear_ob(df, _name, _cache):
    df["bearish_order_block"] = _bear_ob(df["close"])
    return df

@_register("breaker_block_bullish", requires={"high", "low", "close"})
def _h_breaker_bull(df, _name, _cache):
    df["breaker_block_bullish"] = _breaker_bull(df["high"], df["low"], df["close"])
    return df

@_register("breaker_block_bearish", requires={"high", "low", "close"})
def _h_breaker_bear(df, _name, _cache):
    df["breaker_block_bearish"] = _breaker_bear(df["high"], df["low"], df["close"])
    return df

@_register("liquidity_sweep_high", requires={"high", "low", "close"})
def _h_sweep_high(df, _name, _cache):
    df["liquidity_sweep_high"] = _sweep_high(df["high"], df["low"], df["close"])
    return df

@_register("liquidity_sweep_low", requires={"high", "low", "close"})
def _h_sweep_low(df, _name, _cache):
    df["liquidity_sweep_low"] = _sweep_low(df["high"], df["low"], df["close"])
    return df

@_register("bos", requires={"high", "low"})
def _h_bos(df, _name, _cache):
    df["bos"] = _bos(df["high"], df["low"])
    return df

@_register("choch", requires={"high", "low"})
def _h_choch(df, _name, _cache):
    df["choch"] = _choch(df["high"], df["low"])
    return df

@_register("premium_discount_zone", requires={"high", "low"})
def _h_pd_zone(df, _name, _cache):
    df["premium_discount_zone"] = _pd_zone(df["high"], df["low"])
    return df


# --- VSA (10) ---

@_register("no_demand", requires={"close", "volume"})
def _h_no_dem(df, _name, _cache):
    df["no_demand"] = _no_dem(df["close"], df["volume"])
    return df

@_register("no_supply", requires={"close", "volume"})
def _h_no_sup(df, _name, _cache):
    df["no_supply"] = _no_sup(df["close"], df["volume"])
    return df

@_register("stopping_volume", requires={"high", "low", "volume"})
def _h_stop_vol(df, _name, _cache):
    df["stopping_volume"] = _stop_vol(df["high"], df["low"], df["volume"])
    return df

@_register("climax_volume", requires={"high", "low", "volume"})
def _h_climax(df, _name, _cache):
    df["climax_volume"] = _climax(df["high"], df["low"], df["volume"])
    return df

@_register("effort_to_rise", requires={"high", "low", "close", "volume"})
def _h_eff_rise(df, _name, _cache):
    df["effort_to_rise"] = _eff_rise(df["high"], df["low"], df["close"], df["volume"])
    return df

@_register("effort_to_fall", requires={"high", "low", "close", "volume"})
def _h_eff_fall(df, _name, _cache):
    df["effort_to_fall"] = _eff_fall(df["high"], df["low"], df["close"], df["volume"])
    return df

@_register("effort_result_divergence", requires={"high", "low", "close", "volume"})
def _h_er_div(df, _name, _cache):
    df["effort_result_divergence"] = _er_div(df["high"], df["low"], df["close"], df["volume"])
    return df

@_register("bag_holding", requires={"close", "volume"})
def _h_bag_hold(df, _name, _cache):
    df["bag_holding"] = _bag_hold(df["close"], df["volume"])
    return df

@_register("shakeout", requires={"low", "close", "volume"})
def _h_shakeout(df, _name, _cache):
    df["shakeout"] = _shakeout(df["low"], df["close"], df["volume"])
    return df

@_register("vsa_test_signal", requires={"high", "low", "close", "volume"})
def _h_vsa_test(df, _name, _cache):
    df["vsa_test_signal"] = _vsa_test(df["high"], df["low"], df["close"], df["volume"])
    return df


# --- Supply/demand zones (8) ---

@_register("demand_zone_low", requires={"high", "low", "close"})
def _h_dz_low(df, _name, _cache):
    df["demand_zone_low"] = _dz_low(df["high"], df["low"], df["close"])
    return df

@_register("demand_zone_high", requires={"high", "low", "close"})
def _h_dz_high(df, _name, _cache):
    df["demand_zone_high"] = _dz_high(df["high"], df["low"], df["close"])
    return df

@_register("demand_zone_score", requires={"high", "low", "close"})
def _h_dz_score(df, _name, _cache):
    df["demand_zone_score"] = _dz_score(df["high"], df["low"], df["close"])
    return df

@_register("supply_zone_low", requires={"high", "low", "close"})
def _h_sz_low(df, _name, _cache):
    df["supply_zone_low"] = _sz_low(df["high"], df["low"], df["close"])
    return df

@_register("supply_zone_high", requires={"high", "low", "close"})
def _h_sz_high(df, _name, _cache):
    df["supply_zone_high"] = _sz_high(df["high"], df["low"], df["close"])
    return df

@_register("supply_zone_score", requires={"high", "low", "close"})
def _h_sz_score(df, _name, _cache):
    df["supply_zone_score"] = _sz_score(df["high"], df["low"], df["close"])
    return df

@_register("zone_failure_bullish", requires={"high", "low", "close"})
def _h_zf_bull(df, _name, _cache):
    df["zone_failure_bullish"] = _zf_bull(df["high"], df["low"], df["close"])
    return df

@_register("zone_failure_bearish", requires={"high", "low", "close"})
def _h_zf_bear(df, _name, _cache):
    df["zone_failure_bearish"] = _zf_bear(df["high"], df["low"], df["close"])
    return df


# --- Hurst regime (2) ---

@_register("hurst_exponent", requires={"close"})
def _h_hurst(df, _name, _cache):
    df["hurst_exponent"] = rolling_scalar_series(_hurst, df["close"])
    return df

@_register("fractal_regime", requires={"close"})
def _h_frac_regime(df, _name, _cache):
    # fractal_regime returns a scalar string, not a Series.
    # Broadcast it as a constant for all bars.
    regime = _frac_regime(df["close"])
    df["fractal_regime"] = pd.Series(regime, index=df.index, dtype="object")
    return df


# --- Market regime (2) ---

@_register("market_regime", requires={"close", "high", "low", "volume"})
def _h_mkt_regime(df, _name, _cache):
    df["market_regime"] = _mkt_regime(df["close"], df["high"], df["low"], df["volume"])
    return df

@_register("day_type_classification", requires={"high", "low", "close"})
def _h_day_type(df, _name, _cache):
    df["day_type_classification"] = _day_type(df["high"], df["low"], df["close"])
    return df


# ===========================================================================
# Derivatives metric handlers — these pass through pre-merged columns.
# The actual data comes from merge_derivatives_asof (called by the job
# runner before calculate()). The handler just ensures the column exists
# (Invariant #2) and registers the name for catalog/handler name-sync.
# ===========================================================================

"""Constants for derivatives metrics shared across the runtime package.

This module defines the canonical list of derivatives field names.
Both the indicator calculator (pass-through handlers) and any future
merge logic in the package reference this list.
"""

# All nullable float field names for derivatives metrics that can be
# merged onto OHLCV frames and used as indicator columns.
DERIVATIVES_FIELDS: tuple[str, ...] = (
    "open_interest",
    "open_interest_delta_1h",
    "open_interest_delta_24h",
    "cumulative_volume_delta",
    "funding_rate",
    "funding_rate_annualised",
    "long_short_ratio",
    "liquidations_long_1h",
    "liquidations_short_1h",
    "liquidations_long_24h",
    "liquidations_short_24h",
)


# Alias for backward compat within this module.
_DERIV_HANDLER_NAMES = list(DERIVATIVES_FIELDS)


def _register_derivatives_handlers() -> None:
    """Register pass-through handlers for derivatives metrics."""

    def _make_handler(col_name: str):
        @_register(col_name)
        def _handler(df, _name, _cache):
            if col_name not in df.columns:
                df[col_name] = np.nan
            return df
        return _handler

    for name in _DERIV_HANDLER_NAMES:
        _make_handler(name)


_register_derivatives_handlers()


# ===========================================================================
# Realized volatility + intraday volume curve handlers
# ===========================================================================

from finbar_strategy_runtime.domain.services.realized_volatility_estimators import (  # noqa: E402
    bipower_variation as _bpv,
    lee_mykland_jump as _lm_jump,
    realized_kurtosis as _r_kurt,
    realized_skewness as _r_skew,
    realized_volatility as _r_vol,
)
from finbar_strategy_runtime.domain.services.intraday_seasonality_proxies import (  # noqa: E402
    empirical_volume_curve as _emp_vc,
    intraday_volume_curve as _intra_vc,
)


@_register("realized_vol_5m", requires={"close"})
def _h_rv_5m(df, _name, _cache):
    df["realized_vol_5m"] = _r_vol(df["close"], window=78)
    return df

@_register("realized_vol_15m", requires={"close"})
def _h_rv_15m(df, _name, _cache):
    df["realized_vol_15m"] = _r_vol(df["close"], window=26)
    return df

@_register("realized_vol_1h", requires={"close"})
def _h_rv_1h(df, _name, _cache):
    df["realized_vol_1h"] = _r_vol(df["close"], window=7)
    return df

@_register("bipower_variation", requires={"close"})
def _h_bpv(df, _name, _cache):
    df["bipower_variation"] = _bpv(df["close"], window=78)
    return df

@_register("realized_skewness", requires={"close"})
def _h_rskew(df, _name, _cache):
    df["realized_skewness"] = _r_skew(df["close"], window=78)
    return df

@_register("realized_kurtosis", requires={"close"})
def _h_rkurt(df, _name, _cache):
    df["realized_kurtosis"] = _r_kurt(df["close"], window=78)
    return df

@_register("lee_mykland_jump", requires={"close"})
def _h_lm_jump(df, _name, _cache):
    df["lee_mykland_jump"] = _lm_jump(df["close"], window=78)
    return df

@_register("intraday_volume_curve", requires={"volume"})
def _h_intra_vc(df, _name, _cache):
    df["intraday_volume_curve"] = _intra_vc(df)
    return df

@_register("empirical_volume_curve", requires={"volume"})
def _h_emp_vc(df, _name, _cache):
    df["empirical_volume_curve"] = _emp_vc(df)
    return df
