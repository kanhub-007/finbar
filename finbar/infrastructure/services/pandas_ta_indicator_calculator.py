"""PandasTaIndicatorCalculator — pandas_ta implementation of IndicatorCalculator.

Calculates technical indicators (RSI, SMA, MACD, ATR, etc.) on OHLCV
DataFrames using the pandas_ta library. Also delegates proxy indicators
to the domain proxy_indicator module.

Implements the IndicatorCalculator domain interface via the Strategy pattern.
Uses the Pipeline pattern — the calculate() dispatcher stays under 30 lines,
each indicator group is its own private method.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pandas as pd
import pandas_ta as ta

from finbar.core.domain.interfaces.indicator_calculator import IndicatorCalculator
from finbar.core.domain.services.proxy_indicator import (
    enrich_dataframe_with_proxies,
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
    """Decorator to register an indicator handler."""

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

        for name in indicators:
            if name.startswith("proxy_"):
                result = _compute_proxies(result, cache)
            elif name in _INDICATOR_HANDLERS:
                handler, requires = _INDICATOR_HANDLERS[name]
                if requires and requires - set(result.columns):
                    logger.debug(
                        "Skipping '%s': missing columns %s",
                        name,
                        requires - set(result.columns),
                    )
                    continue
                try:
                    result = handler(result, name, cache)
                except Exception:
                    logger.warning(
                        "Failed to compute indicator '%s'", name, exc_info=True
                    )
            elif _is_dynamic(name):
                try:
                    result = _compute_dynamic(result, name)
                except Exception:
                    logger.warning(
                        "Failed to compute dynamic indicator '%s'",
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

    date_series = pd.to_datetime(df.index).strftime("%Y-%m-%d")

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


# ---------------------------------------------------------------------------
# Dynamic period indicators — handles any period within supported ranges
# ---------------------------------------------------------------------------

_DYNAMIC_HANDLERS: dict[str, tuple[Callable, str]] = {
    "sma": (ta.sma, "close"),
    "ema": (ta.ema, "close"),
    "rsi": (ta.rsi, "close"),
}


def _is_dynamic(name: str) -> bool:
    """Return True when a name matches a dynamic indicator like sma_37."""
    for prefix in _DYNAMIC_HANDLERS:
        if name.startswith(f"{prefix}_"):
            rest = name[len(prefix) + 1 :]
            return rest.isdigit() and int(rest) >= 2
    return False


def _compute_dynamic(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Compute a dynamic period indicator and add its column to the frame."""
    for prefix, (func, source_col) in _DYNAMIC_HANDLERS.items():
        if name.startswith(f"{prefix}_"):
            period = int(name[len(prefix) + 1 :])
            df[name] = _safe_ta(func, df[source_col], length=period)
            return df
    return df
