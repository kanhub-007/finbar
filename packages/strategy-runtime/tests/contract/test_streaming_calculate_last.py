"""Contract tests for Scenario 9: calculate_last() batch fallback.

Verifies that PandasTaIndicatorCalculator.calculate_last() returns only
the latest-row dict, equal to the last row of calculate().
"""

import math

from .test_streaming_sma_parity import _bars_to_frame, _make_deterministic_bars


class TestCalculateLast:
    """Scenario 9: calculate_last() returns latest row only."""

    def test_calculate_last_matches_calculate_last_row(self):
        """calculate_last() equals iloc[-1] of calculate()."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        bars = _make_deterministic_bars(80, seed=6)
        df = _bars_to_frame(bars)
        indicators = ["sma_20", "rsi_14"]

        calc = PandasTaIndicatorCalculator()
        full = calc.calculate(df, indicators).iloc[-1].to_dict()
        last = calc.calculate_last(df, indicators)

        for name in indicators:
            full_val = full[name]
            last_val = last.get(name, float("nan"))
            if math.isnan(full_val) and math.isnan(last_val):
                continue
            assert math.isclose(
                last_val, full_val, rel_tol=1e-12, abs_tol=1e-15
            ), (
                f"{name}: calculate_last={last_val}, calculate={full_val}, "
                f"diff={abs(last_val - full_val)}"
            )

    def test_calculate_last_empty_indicators(self):
        """Passing empty indicator list returns empty dict."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        bars = _make_deterministic_bars(50, seed=1)
        df = _bars_to_frame(bars)

        calc = PandasTaIndicatorCalculator()
        result = calc.calculate_last(df, [])
        assert result == {}

    def test_calculate_last_empty_df(self):
        """Passing empty DataFrame returns empty dict."""
        import pandas as pd

        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        result = calc.calculate_last(pd.DataFrame(), ["rsi_14"])
        assert result == {}
