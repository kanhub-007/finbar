"""Core technical-analysis handlers — RSI, SMA, EMA, MACD, ATR, ADX, BB.

This module is imported by ``handlers/__init__.py`` which triggers
registration of all ``@_register`` decorators at import time.
"""

import pandas as pd
import pandas_ta as ta

from finbar_strategy_runtime.indicators._handler_registry import _register, _safe_ta


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
