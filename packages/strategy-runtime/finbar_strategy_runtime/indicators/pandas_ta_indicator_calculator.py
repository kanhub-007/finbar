"""PandasTaIndicatorCalculator — pandas_ta implementation of IndicatorCalculator.

This module is the public entry point. It contains only the calculator
class (the Facade/Dispatcher) and the proxy-indicator batch helper.

All indicator handler functions live in ``handlers/`` sub-modules and
register themselves into ``_INDICATOR_HANDLERS`` at import time.
Dynamic-period dispatch logic lives in ``_dynamic_dispatch``.
"""

from __future__ import annotations

import logging
from collections import deque

import numpy as np
import pandas as pd

from finbar_strategy_runtime.domain.interfaces.indicator_calculator import IndicatorCalculator
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
FAILED_INDICATORS_ATTR = "failed_indicators"


def _topological_sort(
    names: list[str],
    handlers: dict[str, tuple],
) -> list[str]:
    """Sort indicator names so dependencies precede dependents.

    Uses Kahn's algorithm (BFS). Dynamic indicators (not in handlers)
    and those with no inter-indicator dependencies are placed first.

    Args:
        names: Requested indicator names in any order.
        handlers: Registry dict mapping name → (handler_fn, requires_set).

    Returns:
        Sorted list with the same elements; dependencies before dependents.
    """
    if len(names) <= 1:
        return list(names)

    names_set = set(names)

    in_degree: dict[str, int] = {}
    adjacency: dict[str, list[str]] = {}

    for name in names:
        if name not in handlers:
            continue
        _, requires = handlers[name]
        for dep in requires:
            if dep in names_set:
                adjacency.setdefault(dep, []).append(name)
                in_degree[name] = in_degree.get(name, 0) + 1

    # Start with all nodes that have no unmet dependencies within the request
    queue: deque[str] = deque(
        name for name in names if in_degree.get(name, 0) == 0
    )
    sorted_names: list[str] = []

    while queue:
        node = queue.popleft()
        sorted_names.append(node)
        for dependent in adjacency.get(node, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Append any unprocessed nodes (unknown names, circular deps)
    processed = set(sorted_names)
    for name in names:
        if name not in processed:
            sorted_names.append(name)

    return sorted_names


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

        sorted_indicators = _topological_sort(indicators, _INDICATOR_HANDLERS)
        for name in sorted_indicators:
            if name in _INDICATOR_HANDLERS:
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

