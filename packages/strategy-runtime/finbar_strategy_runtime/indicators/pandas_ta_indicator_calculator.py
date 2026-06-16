"""PandasTaIndicatorCalculator — pandas_ta implementation of IndicatorCalculator.

This module is the public entry point. It contains only the calculator
class (the Facade/Dispatcher) and the proxy-indicator batch helper.

All indicator handler functions live in ``handlers/`` sub-modules and
register themselves into ``_INDICATOR_HANDLERS`` at import time.
Dynamic-period dispatch logic lives in ``_dynamic_dispatch``.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from finbar_strategy_runtime.domain.interfaces.indicator_calculator import IndicatorCalculator
from finbar_strategy_runtime.domain.services.proxy_indicator import (
    enrich_dataframe_with_proxies,
)
from finbar_strategy_runtime.indicators.handlers import (  # noqa: F401
    core_ta,
    derivatives,
    intraday_realized,
    market_profile_amt,
    microstructure,
    price_action,
    profile_classifiers,
    trend_breakout,
    inside_bar,
    vwap_bands,
    volume_profile,
)
from finbar_strategy_runtime.indicators._handler_registry import (
    _INDICATOR_HANDLERS,
)
from finbar_strategy_runtime.indicators._dynamic_dispatch import (
    _compute_dynamic,
    _compute_rolling_vp_dynamic,
    _is_dynamic,
    _is_rolling_vp,
)

logger = logging.getLogger(__name__)

MIN_BARS = 10
_PROXY_CACHE_KEY = "__proxies_done"

#: pandas DataFrame ``attrs`` key carrying the per-call list of indicators
#: that failed during ``calculate``. Each entry is a ``(name, error)``
#: tuple. Surfaced so job runners can report silent failures instead of
#: swallowing them as NaN (spec 2026-06-16 Scenario 4 / ADR-6).
FAILED_INDICATORS_ATTR = "failed_indicators"


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

        cache: dict[str, pd.DataFrame] = {}
        present_cols = set(result.columns)
        failed: list[tuple[str, str]] = []

        for name in indicators:
            if name.startswith("proxy_"):
                result = _compute_proxies(result, cache)
                present_cols = set(result.columns)
            elif name in _INDICATOR_HANDLERS:
                handler, requires = _INDICATOR_HANDLERS[name]
                if requires and requires - present_cols:
                    result[name] = np.nan
                    missing = sorted(requires - present_cols)
                    failed.append(
                        (
                            name,
                            f"Missing required columns: {missing}",
                        )
                    )
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
                except Exception as exc:
                    result[name] = np.nan
                    failed.append((name, str(exc)))
                    present_cols = set(result.columns)
                    logger.warning(
                        "Failed to compute indicator '%s'", name, exc_info=True
                    )
            elif _is_dynamic(name):
                try:
                    result = _compute_dynamic(result, name)
                    present_cols = set(result.columns)
                except Exception as exc:
                    failed.append((name, str(exc)))
                    logger.warning(
                        "Failed to compute dynamic indicator '%s'",
                        name,
                        exc_info=True,
                    )
            elif _is_rolling_vp(name):
                try:
                    result = _compute_rolling_vp_dynamic(result, name, cache)
                    present_cols = set(result.columns)
                except Exception as exc:
                    failed.append((name, str(exc)))
                    logger.warning(
                        "Failed to compute rolling VP '%s'",
                        name,
                        exc_info=True,
                    )
            else:
                failed.append((name, "Unknown indicator name"))
                logger.warning("Unknown indicator: '%s'", name)

        # Surface per-call failures on the returned frame so the job runner
        # can report them (ADR-6). Attached AFTER the loop so handlers that
        # reassign ``result`` (e.g. proxy enrichment copies) cannot drop it.
        result.attrs[FAILED_INDICATORS_ATTR] = failed
        return result


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
