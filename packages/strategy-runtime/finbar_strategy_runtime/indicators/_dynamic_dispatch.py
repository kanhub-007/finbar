"""Dynamic indicator dispatch — handles parameterized indicator names.

Resolves names like ``sma_37``, ``rsi_21``, ``rvp_poc_100``,
``vp_poc_10d``, ``cvp_poc_5d`` by parsing the period from the name
and dispatching to the appropriate compute function.
"""

from collections.abc import Callable

import pandas as pd
import pandas_ta as ta

from finbar_strategy_runtime.indicators._handler_registry import _safe_ta
from finbar_strategy_runtime.indicators.handlers import volume_profile as _vp

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

_DYNAMIC_PREFIXES: dict[str, tuple[Callable, str]] = {
    f"{prefix}_": (func, source)
    for prefix, (func, source) in _DYNAMIC_HANDLERS.items()
}

_ROLLING_VP_PREFIXES = {"vp_poc_", "vp_vah_", "vp_val_"}
_RVP_PREFIXES = {"rvp_poc_", "rvp_vah_", "rvp_val_"}
_CVP_PREFIXES = {"cvp_poc_", "cvp_vah_", "cvp_val_"}


def _resolve_dynamic(name: str) -> tuple[Callable, str, int, str] | None:
    """Try to resolve a dynamic indicator name like sma_37.

    Returns (func, source_col, period, prefix) or None.
    """
    for prefix_key, (func, source_col) in _DYNAMIC_PREFIXES.items():
        if name.startswith(prefix_key):
            period_str = name[len(prefix_key):]
            if period_str.isdigit():
                period = int(period_str)
                if period >= 2:
                    prefix = prefix_key[:-1]
                    return func, source_col, period, prefix
            return None
    return None


def _is_dynamic(name: str) -> bool:
    """Return True when a name matches a dynamic indicator like sma_37."""
    return _resolve_dynamic(name) is not None


def _compute_dynamic(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Compute a dynamic period indicator and add its column."""
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


def _is_rolling_vp(name: str) -> bool:
    """Return True when name matches rvp_poc_N, vp_poc_Nd, or cvp_poc_Nd."""
    all_prefixes = _ROLLING_VP_PREFIXES | _RVP_PREFIXES | _CVP_PREFIXES
    for prefix in all_prefixes:
        if prefix in _RVP_PREFIXES and name.startswith(prefix):
            inner = name[len(prefix):]
            if inner.isdigit() and int(inner) >= 1:
                return True
        if prefix in (_ROLLING_VP_PREFIXES | _CVP_PREFIXES) and name.startswith(prefix) and name.endswith("d"):
            inner = name[len(prefix):-1]
            if inner.isdigit() and int(inner) >= 1:
                return True
    return False


def _compute_rolling_vp_dynamic(df: pd.DataFrame, name: str, cache: dict) -> pd.DataFrame:
    """Compute a parameterized rolling VP or RVP indicator."""
    for prefix in _RVP_PREFIXES:
        if name.startswith(prefix):
            inner = name[len(prefix):]
            if inner.isdigit():
                window_bars = int(inner)
                return _vp._compute_rolling_window_vp(df, cache, window_bars)

    for prefix in _CVP_PREFIXES:
        if name.startswith(prefix) and name.endswith("d"):
            inner = name[len(prefix):-1]
            if inner.isdigit():
                window = int(inner)
                return _vp._compute_composite_vp(df, cache, window)

    for prefix in _ROLLING_VP_PREFIXES:
        if name.startswith(prefix) and name.endswith("d"):
            inner = name[len(prefix):-1]
            window = int(inner)
            if "vp_poc" not in df.columns or "vp_vah" not in df.columns:
                return df
            return _vp._compute_rolling_vp(df, cache, window)

    return df
