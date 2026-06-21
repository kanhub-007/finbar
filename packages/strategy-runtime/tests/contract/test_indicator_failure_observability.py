"""Observability regression tests — spec 2026-06-16 Scenario 4 (ADR-6).

The indicator dispatch catches every handler exception and writes NaN
(``except Exception: result[name] = np.nan``). That silent swallowing is
WHY every bug in this spec went undetected. These tests pin the fix:
the calculator must collect failures and expose them so the job runner
can surface them to users (instead of silent nulls).

Classical school: real ``PandasTaIndicatorCalculator``, a real crashing
handler injected into the live registry (no mocks), assert on the
outcome (the ``failed_indicators`` list on the returned frame).
"""

import numpy as np
import pandas as pd
import pytest

from finbar_strategy_runtime.indicators._handler_registry import (
    _INDICATOR_HANDLERS,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    FAILED_INDICATORS_ATTR,
    PandasTaIndicatorCalculator,
)


@pytest.fixture
def daily_ohlcv() -> pd.DataFrame:
    """30-bar daily OHLCV frame."""
    n = 30
    close = pd.Series(np.linspace(100.0, 130.0, n))
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000.0,
        }
    )
    df.index = pd.date_range("2026-01-01", periods=n, freq="D")
    return df


@pytest.fixture
def crashing_handler():
    """Register a handler that always raises, then deregister on teardown.

    Uses the real registry + real dispatch — no mocks. The handler raises
    ``TypeError`` to mirror the original ``demand_zone_score`` bug class.
    """
    sentinel = "__test_always_crashes__"

    def _handler(df, _name, _cache):
        raise TypeError("boom: missing required positional argument 'volume'")

    _INDICATOR_HANDLERS[sentinel] = (_handler, set())
    try:
        yield sentinel
    finally:
        _INDICATOR_HANDLERS.pop(sentinel, None)


class TestCalculatorSurfacesFailedIndicators:
    """Scenario 4 — failures must be collected and exposed, not swallowed."""

    def test_failed_indicators_attr_present_on_result(self, daily_ohlcv):
        """The returned frame always carries a failed_indicators list."""
        calc = PandasTaIndicatorCalculator()
        result = calc.calculate(daily_ohlcv, ["sma_20"])
        assert FAILED_INDICATORS_ATTR in result.attrs
        assert result.attrs[FAILED_INDICATORS_ATTR] == []

    def test_crashing_handler_recorded_with_name_and_error(
        self, daily_ohlcv, crashing_handler
    ):
        """A handler that raises is recorded as (name, error_message)."""
        calc = PandasTaIndicatorCalculator()
        result = calc.calculate(daily_ohlcv, ["sma_20", crashing_handler])

        failed = result.attrs[FAILED_INDICATORS_ATTR]
        assert len(failed) == 1
        name, error = failed[0]
        assert name == crashing_handler
        assert "volume" in error  # the TypeError message is surfaced

    def test_crashing_handler_still_writes_nan_for_column(
        self, daily_ohlcv, crashing_handler
    ):
        """Backwards-compat: the NaN column behaviour is preserved."""
        calc = PandasTaIndicatorCalculator()
        result = calc.calculate(daily_ohlcv, [crashing_handler])
        assert crashing_handler in result.columns
        assert result[crashing_handler].isna().all()

    def test_healthy_handler_not_recorded_as_failed(
        self, daily_ohlcv, crashing_handler
    ):
        """Only the crashing handler appears; sma_20 does not."""
        calc = PandasTaIndicatorCalculator()
        result = calc.calculate(daily_ohlcv, ["sma_20", crashing_handler])
        failed_names = [name for name, _ in result.attrs[FAILED_INDICATORS_ATTR]]
        assert "sma_20" not in failed_names

    def test_missing_required_columns_recorded_as_failed(
        self, daily_ohlcv, crashing_handler
    ):
        """A handler whose requires set is unsatisfied is also surfaced.

        Uses a synthetic handler that depends on a column that is neither
        present in the frame nor a known indicator name, so transitive
        expansion cannot auto-satisfy it. The dispatch writes NaN when
        truly unresolvable dependencies are absent.
        """
        _INDICATOR_HANDLERS["__test_needs_absent__"] = (
            lambda df, _n, _c: df,
            {"absent_column_xyz"},  # not a known indicator; cannot be auto-computed
        )
        try:
            calc = PandasTaIndicatorCalculator()
            result = calc.calculate(
                daily_ohlcv, ["__test_needs_absent__"]
            )
            failed = result.attrs[FAILED_INDICATORS_ATTR]
            # Expect at least the synthetic handler to be reported as failed.
            # The unresolved dep may also appear as "Unknown indicator name".
            assert any(
                name == "__test_needs_absent__" for name, _ in failed
            ), f"Expected __test_needs_absent__ in failed list, got: {failed}"
        finally:
            _INDICATOR_HANDLERS.pop("__test_needs_absent__", None)
