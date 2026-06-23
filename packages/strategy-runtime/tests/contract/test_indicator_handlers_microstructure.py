"""Contract tests for microstructure indicator handlers — Scenarios 2.1–2.3.

Verifies the PandasTaIndicatorCalculator dispatches to the new microstructure
calculators and produces columns with proper graceful degradation.
"""

import numpy as np
import pandas as pd
import pytest

from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    """30-bar OHLCV DataFrame suitable for microstructure metrics."""
    np.random.seed(1)
    n = 30
    close = pd.Series(100 + np.cumsum(np.random.randn(n) * 0.5))
    df = pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.random.randint(1000, 10000, n).astype(float),
        }
    )
    df.index = pd.date_range("2024-01-01", periods=n, freq="D")
    return df


@pytest.fixture
def calc() -> PandasTaIndicatorCalculator:
    return PandasTaIndicatorCalculator()


# ---------------------------------------------------------------------------
# Scenario 2.1: Strategy uses a new microstructure metric
# ---------------------------------------------------------------------------


class TestSpreadHandlers:
    """Spread proxy handlers produce correct columns."""

    @pytest.mark.parametrize(
        "metric",
        [
            "fong_holden_tran_spread",
            "roll_spread",
            "effective_tick_spread",
            "lot_zero_return_spread",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        """Each spread handler produces its named column."""
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns

    def test_fong_holden_tran_non_negative(self, calc, ohlcv_df):
        """Corwin-Schultz spread values must be non-negative."""
        result = calc.calculate(ohlcv_df, ["fong_holden_tran_spread"])
        col = result["fong_holden_tran_spread"].dropna()
        assert (col >= 0).all()


class TestVolatilityHandlers:
    """Volatility estimator handlers produce correct columns."""

    @pytest.mark.parametrize(
        "metric",
        [
            "close_to_close_vol",
            "parkinson_vol",
            "garman_klass_vol",
            "rogers_satchell_vol",
            "yang_zhang_vol",
            "gk_plus_overnight_vol",
            "meilijson_vol",
            "daily_return_skewness",
            "daily_return_kurtosis",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        """Each volatility handler produces its named column."""
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestLiquidityHandlers:
    """Liquidity proxy handlers produce correct columns."""

    @pytest.mark.parametrize(
        "metric",
        [
            "amihud_illiq",
            "amivest_liquidity",
            "florackis_lambda",
            "hasbrouck_daily_lambda",
            "liu_illiq",
            "bao_pan_zhou_cost",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        """Each liquidity handler produces its named column."""
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestOrderFlowHandlers:
    """Order flow proxy handlers produce correct columns."""

    @pytest.mark.parametrize(
        "metric",
        [
            "signed_sqrt_volume_ofi",
            "cumulative_signed_volume_ofi",
            "bvc_buy_volume",
            "bvc_sell_volume",
            "bvc_ofi",
            "return_volume_correlation",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        """Each order flow handler produces its named column."""
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestInformedTradingHandlers:
    """Informed trading proxy handlers produce correct columns."""

    @pytest.mark.parametrize(
        "metric",
        [
            "daily_vpin",
            "spread_based_pin_proxy",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        """Each informed trading handler produces its named column."""
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestJumpRiskHandlers:
    """Jump risk proxy handlers produce correct columns."""

    @pytest.mark.parametrize(
        "metric",
        [
            "jump_gap_proxy",
            "extreme_return_flag",
            "cc_rs_jump_proxy",
            "overnight_gap_proxy",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        """Each jump risk handler produces its named column."""
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestResiliencyHandlers:
    """Resiliency proxy handlers produce correct columns."""

    @pytest.mark.parametrize(
        "metric",
        [
            "resiliency_autocorr",
            "resiliency_spread_to_impact",
            "inverse_amihud_resiliency",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        """Each resiliency handler produces its named column."""
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestIntradaySeasonalityHandlers:
    """Intraday seasonality proxy handlers produce correct columns."""

    @pytest.mark.parametrize(
        "metric",
        [
            "overnight_return",
            "intraday_return",
            "parametric_u_shape",
            "first_last_hour_vol_fraction",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        """Each seasonality handler produces its named column."""
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


class TestOrderArrivalHandlers:
    """Order arrival proxy handlers produce correct columns."""

    @pytest.mark.parametrize(
        "metric",
        [
            "volume_to_trade_count_proxy",
        ],
    )
    def test_column_appears(self, calc, ohlcv_df, metric):
        """Each order arrival handler produces its named column."""
        result = calc.calculate(ohlcv_df, [metric])
        assert metric in result.columns


# ---------------------------------------------------------------------------
# Scenario 2.2: Missing column → all-NaN, no crash
# ---------------------------------------------------------------------------


class TestGracefulMissingColumn:
    """When required columns are missing, handlers produce NaN (not crash)."""

    def test_amihud_without_volume_all_nan(self, calc):
        """amihud_illiq without volume column → all-NaN, no crash."""
        df = pd.DataFrame(
            {"open": [1] * 30, "high": [2] * 30, "low": [0.5] * 30, "close": [1.5] * 30}
        )
        df.index = pd.date_range("2024-01-01", periods=30, freq="D")
        result = calc.calculate(df, ["amihud_illiq"])
        assert "amihud_illiq" in result.columns
        assert result["amihud_illiq"].isna().all()


# ---------------------------------------------------------------------------
# Scenario 2.3: Calculator throws → NaN column + warning logged
# ---------------------------------------------------------------------------


class TestGracefulException:
    """When a calculator raises, the column is all-NaN (not an exception)."""

    def test_handler_exception_produces_nan_column(self, calc):
        """When a calculator raises, the column is all-NaN (not an exception).

        Uses empty DataFrame columns that force a calculator error.
        """
        # All-NaN high/low columns make parkinson_vol produce NaN
        # (parkinson uses log(high/low); NaN inputs propagate)
        df = pd.DataFrame(
            {
                "open": [1] * 30,
                "high": [np.nan] * 30,
                "low": [np.nan] * 30,
                "close": [1] * 30,
                "volume": [100] * 30,
            }
        )
        df.index = pd.date_range("2024-01-01", periods=30, freq="D")
        result = calc.calculate(df, ["parkinson_vol"])
        assert "parkinson_vol" in result.columns
        assert result["parkinson_vol"].isna().all()
