"""Tests for PandasSignalCalculator — confidence scoring and risk flags.

Behavioural coverage for the row-wise confidence path, which previously
allocated a pd.Series per row via df.iloc[i].
"""

import pandas as pd

from finbar.infrastructure.services.pandas_signal_calculator import (
    PandasSignalCalculator,
)


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class TestConfidenceScoring:
    def test_strong_trend_volume_boosts_score(self):
        df = _frame(
            [
                {
                    "close": 100.0,
                    "adx": 30.0,
                    "trend_direction": "BULLISH",
                    "rvol": 3.5,
                    "is_power_zone": True,
                }
            ]
        )
        result = PandasSignalCalculator().calculate(df)
        assert result["confidence_score"].iloc[0] >= 50

    def test_missing_columns_does_not_crash(self):
        df = _frame([{"close": 100.0}])
        result = PandasSignalCalculator().calculate(df)
        assert len(result) == 1
        # With no trend/volume info, score is just the base.
        assert result["confidence_score"].iloc[0] >= 0

    def test_rsi_zero_is_extreme_oversold_in_confidence(self):
        """A legitimate rsi_14 == 0.0 is an extreme oversold value, not missing
        data. The confidence path must preserve 0.0 (rather than the old
        `or 50` default that treated it as neutral) so it incurs the same
        OVEREXTENDED_DOWN penalty as rsi=10. Only NaN (missing) should fall
        back to the neutral default. Note: the separate is_extreme_oversold
        column uses rsi<20 directly and is unaffected."""
        calc = PandasSignalCalculator()
        df_zero = _frame([{"close": 100.0, "rsi_14": 0.0}])
        df_mid = _frame([{"close": 100.0, "rsi_14": 50.0}])
        df_low = _frame([{"close": 100.0, "rsi_14": 10.0}])
        df_nan = _frame([{"close": 100.0, "rsi_14": float("nan")}])
        score_zero = calc.calculate(df_zero)["confidence_score"].iloc[0]
        score_mid = calc.calculate(df_mid)["confidence_score"].iloc[0]
        score_low = calc.calculate(df_low)["confidence_score"].iloc[0]
        score_nan = calc.calculate(df_nan)["confidence_score"].iloc[0]
        # rsi=0 is an extreme oversold (same penalty bucket as rsi=10); both
        # score below the neutral rsi=50.
        assert score_zero == score_low
        assert score_zero < score_mid
        # NaN (missing) still falls back to the neutral default.
        assert score_nan == score_mid

    def test_weak_trend_risk_factor_lowers_score(self):
        df_strong = _frame(
            [{"close": 100.0, "adx": 30.0, "trend_direction": "BULLISH"}]
        )
        df_weak = _frame([{"close": 100.0, "adx": 10.0, "trend_direction": "BULLISH"}])
        calc = PandasSignalCalculator()
        strong = calc.calculate(df_strong)["confidence_score"].iloc[0]
        weak = calc.calculate(df_weak)["confidence_score"].iloc[0]
        assert weak < strong

    def test_results_match_length_and_index(self):
        df = _frame(
            [{"close": 100.0 + i, "adx": 25.0} for i in range(50)]
        )
        result = PandasSignalCalculator().calculate(df)
        assert len(result) == 50
        assert result.index.equals(df.index)

    def test_no_per_row_series_allocation(self):
        """The hot loop must not call df.iloc[i) (which allocates a Series)."""
        import pandas as pd

        df = _frame([{"close": 100.0, "adx": 25.0} for _ in range(5)])
        calc = PandasSignalCalculator()
        iloc_calls = []
        original_iloc = pd.DataFrame.iloc

        class Spy:
            def __init__(self, frame):
                self._frame = frame

            def __getitem__(self, key):
                iloc_calls.append(key)
                return original_iloc.__get__(self._frame)[key]

        # Monkeypatch iloc property to detect per-row access.
        original_property = pd.DataFrame.iloc
        try:
            pd.DataFrame.iloc = property(  # type: ignore[misc]
                lambda self: Spy(self)
            )
            calc.calculate(df)
        finally:
            pd.DataFrame.iloc = original_property  # type: ignore[misc]
        # Integer-indexed iloc calls (the old pattern) must not occur.
        assert not any(isinstance(c, int) for c in iloc_calls)
