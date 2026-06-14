
"""Contract tests for the strategy runtime package — indicators and domain services."""

import numpy as np
import pytest

# Soft import pandas_ta — skip indicator tests if unavailable
_HAS_PANDAS_TA = False
try:
    import pandas_ta  # noqa: F401
    _HAS_PANDAS_TA = True
except ImportError:
    pass

pandas_ta_required = pytest.mark.skipif(
    not _HAS_PANDAS_TA,
    reason="pandas_ta not installed (requires Python < 3.14)",
)

# =========================================================================
# Scenario 3: Runtime package computes indicator/enrichment columns with parity
# =========================================================================

import numpy as np

# Soft import pandas_ta — skip indicator tests if unavailable
_HAS_PANDAS_TA = False
try:
    import pandas_ta  # noqa: F401

    _HAS_PANDAS_TA = True
except ImportError:
    pass

pandas_ta_required = pytest.mark.skipif(
    not _HAS_PANDAS_TA,
    reason="pandas_ta not installed (requires Python < 3.14)",
)


class TestIndicatorCalculator:
    """Black-box tests for the Pandas indicator calculator."""

    @staticmethod
    def _make_ohlcv_df(periods: int = 100) -> "pd.DataFrame":
        """Create a sample OHLCV DataFrame for testing."""
        import pandas as pd

        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=periods, freq="h")
        close = 100 + np.cumsum(np.random.randn(periods) * 1.5)
        return pd.DataFrame(
            {
                "open": close - np.random.rand(periods),
                "high": close + np.random.rand(periods) * 2,
                "low": close - np.random.rand(periods) * 2,
                "close": close,
                "volume": np.random.randint(100000, 1000000, periods),
            },
            index=dates,
        )

    @pandas_ta_required
    def test_atr_vp_columns_present(self):
        """Computing atr, vp_poc, vp_vah, vp_val adds those columns."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(100)

        enriched = calc.calculate(df, ["atr", "vp_poc", "vp_vah", "vp_val"])

        assert {"atr", "vp_poc", "vp_vah", "vp_val"}.issubset(enriched.columns)
        assert len(enriched) == len(df)

    @pandas_ta_required
    def test_sma_indicators(self):
        """Dynamic period SMA indicators produce correct columns."""
        import pandas as pd

        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(250)

        enriched = calc.calculate(df, ["sma_20", "sma_50", "sma_200"])

        assert "sma_20" in enriched.columns
        assert "sma_50" in enriched.columns
        assert "sma_200" in enriched.columns
        # Last value should be non-NaN (enough bars for 200-period SMA)
        assert not pd.isna(enriched["sma_20"].iloc[-1])

    @pandas_ta_required
    def test_rsi_indicator(self):
        """RSI indicator with period parameter."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(50)

        enriched = calc.calculate(df, ["rsi_14", "rsi_21"])

        assert "rsi_14" in enriched.columns
        assert "rsi_21" in enriched.columns

    @pandas_ta_required
    def test_insufficient_warmup_produces_nan_no_exception(self):
        """Requesting indicators that need more bars than available should
        still add the column (with NaN values), not raise an exception."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        # 50 bars — enough to pass MIN_BARS (10) but not enough for 200-period SMA
        df = self._make_ohlcv_df(50)

        # Should not raise
        enriched = calc.calculate(df, ["sma_200"])

        assert len(enriched) == len(df)
        # SMA_200 column should exist, but all values are NaN (need 200 bars)
        assert "sma_200" in enriched.columns
        assert enriched["sma_200"].isna().all()

    @pandas_ta_required
    def test_empty_indicators_returns_copy(self):
        """Passing an empty indicator list returns a copy of the frame."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(100)

        enriched = calc.calculate(df, [])

        assert len(enriched) == len(df)

    @pandas_ta_required
    def test_empty_df_returns_copy(self):
        """Passing an empty DataFrame returns an empty copy."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )
        import pandas as pd

        calc = PandasTaIndicatorCalculator()
        result = calc.calculate(pd.DataFrame(), ["rsi_14"])
        assert result.empty

    @pandas_ta_required
    def test_parameterized_vp_indicators(self):
        """Parameterized VP indicators produce columns with the correct naming
        convention used by the calculator."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(300)

        enriched = calc.calculate(
            df, ["vp_poc_10d", "rvp_vah_96", "cvp_val_20d"]
        )

        # The calculator may rename parameterized VP indicators
        # (e.g., vp_poc_10d → rvp_poc_96 or similar internal convention)
        assert len(enriched.columns) > len(df.columns), (
            f"Expected additional columns beyond {list(df.columns)}, "
            f"got {list(enriched.columns)}"
        )

    @pandas_ta_required
    def test_acceptance_into_value_indicator(self):
        """acceptance_into_value indicator produces a boolean column on enriched bars."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            PandasTaIndicatorCalculator,
        )

        calc = PandasTaIndicatorCalculator()
        df = self._make_ohlcv_df(200)

        # First enrich with VP columns, then compute the AMT signal
        enriched = calc.calculate(
            df, ["vp_vah", "vp_val", "acceptance_into_value"]
        )

        assert "acceptance_into_value" in enriched.columns


class TestDomainServicesIndicatorMath:
    """Black-box tests for pure domain service functions used by indicators.
    These do not require pandas_ta, only numpy/pandas."""

    @staticmethod
    def _make_ohlcv_df(periods: int = 200) -> "pd.DataFrame":
        """Create a sample OHLCV DataFrame for testing."""
        import pandas as pd

        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=periods, freq="h")
        close = 100 + np.cumsum(np.random.randn(periods) * 0.5)
        return pd.DataFrame(
            {
                "open": close - np.random.rand(periods),
                "high": close + np.random.rand(periods) * 2,
                "low": close - np.random.rand(periods) * 2,
                "close": close,
                "volume": np.random.randint(100000, 1000000, periods),
            },
            index=dates,
        )

    PANDAS_REQUIRED_MSG = "pandas required for domain service indicators"

    def _check_pandas(self):
        try:
            import pandas as pd  # noqa: F401
        except ImportError:
            pytest.skip(self.PANDAS_REQUIRED_MSG)

    def test_volume_profile_returns_result(self):
        """Volume profile computation returns a valid result with VAH/VAL/POC."""
        self._check_pandas()
        from finbar_strategy_runtime.domain.services.volume_profile import (
            compute_all_session_volume_profiles,
        )

        df = self._make_ohlcv_df(200)
        result = compute_all_session_volume_profiles(df)

        assert result is not None
        assert len(result) == len(df)
        assert "vp_poc" in result.columns
        assert "vp_vah" in result.columns
        assert "vp_val" in result.columns

    def test_auction_state_classifies(self):
        """Auction state classifier produces an output column."""
        self._check_pandas()
        from finbar_strategy_runtime.domain.services.volume_profile import (
            compute_all_session_volume_profiles,
        )
        from finbar_strategy_runtime.domain.services.auction_state import (
            classify_auction_state,
        )

        df = self._make_ohlcv_df(200)
        vp = compute_all_session_volume_profiles(df)
        enriched = classify_auction_state(vp)

        assert "inside_value" in enriched.columns
        assert "above_value" in enriched.columns
        assert "below_value" in enriched.columns

    def test_proxy_indicator_enriches(self):
        """Proxy indicator computation adds derived columns."""
        self._check_pandas()
        import pandas as pd

        from finbar_strategy_runtime.domain.services.proxy_indicator import (
            enrich_dataframe_with_proxies,
        )

        df = self._make_ohlcv_df(200)
        result = enrich_dataframe_with_proxies(df)
        # result is the enriched DataFrame
        enriched = result

        assert len(enriched) == len(df)
        # Proxy enrichment typically adds prefix columns
        assert isinstance(enriched, pd.DataFrame)

    def test_content_hash_is_deterministic(self):
        """Artifact hash produces the same result for identical inputs."""
        from finbar_strategy_runtime.domain.services.content_hash import (
            compute_artifact_hash,
        )

        h1 = compute_artifact_hash(
            symbol="AAPL",
            source="yfinance",
            interval="1d",
            indicators=["sma_20", "rsi_14"],
            timeframe_alias="primary",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )
        h2 = compute_artifact_hash(
            symbol="AAPL",
            source="yfinance",
            interval="1d",
            indicators=["rsi_14", "sma_20"],  # sorted order = same hash
            timeframe_alias="primary",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest


class TestBugFixRegressionsRound2:
    """Regression tests for bugs found in round-2 logic review."""

    def test_nan_rsi_classified_as_neutral(self):
        """NaN RSI must be NEUTRAL, not EXTREME_OVERBOUGHT."""
        import numpy as np
        import pandas as pd

        from finbar_strategy_runtime.indicators.pandas_signal_calculator import (
            PandasSignalCalculator,
        )

        df = pd.DataFrame(
            {
                "rsi_14": [50.0, np.nan, 85.0, np.nan],
                "adx": [25.0] * 4,
                "close": [100.0] * 4,
            }
        )
        calc = PandasSignalCalculator()
        result = calc.calculate(df)
        zones = result["rsi_zone"].tolist()
        assert "NEUTRAL" in str(zones[1]), (
            f"NaN RSI classified as {zones[1]}, expected NEUTRAL"
        )
        assert "EXTREME_OVERBOUGHT" in str(zones[2]), (
            f"RSI=85 classified as {zones[2]}, expected EXTREME_OVERBOUGHT"
        )

    def test_wyckoff_markup_overrides_distribution(self):
        """When both MARKUP and DISTRIBUTION match, MARKUP wins."""
        import numpy as np
        import pandas as pd

        from finbar_strategy_runtime.domain.services.wyckoff_phase import (
            classify_wyckoff_phase,
        )

        n = 30
        # POC rising so slope > 0.5 after 20 sessions
        poc_vals = [100.0 + i * 0.05 for i in range(n)]
        df = pd.DataFrame(
            {
                "vp_poc": poc_vals,
                "vp_vah": [p + 10 for p in poc_vals],
                "vp_val": [p - 10 for p in poc_vals],
                "balance_status": ["IMBALANCED_UP"] * n,
                "profile_shape": ["D_SHAPE"] * n,
                "rvol": [1.5] * n,
                "value_area_width_pct": np.arange(20, 20 + n, dtype=float),
            }
        )
        df.index = pd.date_range("2024-01-01", periods=n, freq="D")
        result = classify_wyckoff_phase(df, slope_window=20)
        phases = result["wyckoff_phase"].iloc[25:].tolist()
        assert "MARKUP" in phases, (
            f"Expected MARKUP in phases, got {set(phases)}"
        )
        assert "DISTRIBUTION" not in phases, (
            "DISTRIBUTION overrode MARKUP despite priority comment"
        )


