"""Regression tests for bugs found during correctness review."""

import numpy as np
import pandas as pd
import pytest

from finbar.core.domain.services.volume_profile import compute_rolling_window_vp
from finbar.core.domain.entities.leverage_config import LeverageConfig
from finbar.core.domain.entities.param_range import ParamRange
from finbar.infrastructure.services.bar_validator import validate_bar
from finbar.infrastructure.services.coinglass_client import (
    _first_not_none,
    _parse_cvd,
    _parse_funding,
    _parse_oi,
)
from finbar_strategy_runtime.indicators.pandas_formula_feature_calculator import (
    _parse_operand,
)


class TestRollingVpConstantPrice:
    def test_constant_price_returns_constant_poc(self):
        """Regression: constant-price data returned all NaN for rolling VP."""
        n = 10
        df = pd.DataFrame(
            {
                "high": [100] * n,
                "low": [100] * n,
                "close": [100] * n,
                "volume": [10] * n,
            }
        )
        res = compute_rolling_window_vp(df, window_bars=5)
        poc = res["rvp_poc_5"]
        # First 4 are NaN (warmup), the rest should be 100.0
        assert poc.iloc[:4].isna().all()
        assert (poc.iloc[4:] == 100.0).all()


class TestBarValidator:
    def test_high_below_open_rejected(self):
        assert not validate_bar("X", "t", open_price=100, high=90, low=80, close=95, volume=1)

    def test_low_above_close_rejected(self):
        assert not validate_bar("X", "t", open_price=50, high=100, low=60, close=55, volume=1)

    def test_negative_high_rejected(self):
        assert not validate_bar("X", "t", open_price=80, high=-10, low=70, close=85, volume=1)

    def test_valid_bar_accepted(self):
        assert validate_bar("X", "t", open_price=80, high=100, low=70, close=85, volume=1)


class TestCoinGlassZeroMetrics:
    def test_first_not_none_preserves_zero(self):
        assert _first_not_none({"close": 0}, "close", "fundingRate") == 0
        assert _first_not_none({"close": 0.0}, "close", "fundingRate") == 0.0

    def test_first_not_none_falls_back(self):
        assert _first_not_none({"close": None, "fundingRate": 5}, "close", "fundingRate") == 5

    def test_parse_funding_with_zero_close(self):
        """Regression: zero funding rate was converted to None."""
        result = _parse_funding([{"time": 0, "close": 0.0}], "BTC", "1h")
        assert result[0].funding_rate == 0.0

    def test_parse_cvd_with_zero_close(self):
        result = _parse_cvd([{"time": 0, "close": 0.0}], "BTC", "1h")
        assert result[0].cumulative_volume_delta == 0.0

    def test_parse_oi_with_zero_close(self):
        result = _parse_oi([{"time": 0, "close": 0.0}], "BTC", "1h")
        assert result[0].open_interest == 0.0


class TestFormulaBooleanParsing:
    def test_bool_parsed_as_bool_not_float(self):
        """Regression: True was parsed as 1.0 (float) because bool is a subclass of int."""
        node = _parse_operand(True)
        assert node.kind == "literal"
        assert isinstance(node.value, bool)
        assert node.value is True

        node = _parse_operand(False)
        assert isinstance(node.value, bool)
        assert node.value is False


class TestLeverageZeroSafety:
    def test_zero_leverage_returns_entry(self):
        """Regression: multiplier=0 caused ZeroDivisionError in liquidation_price."""
        assert LeverageConfig(0).liquidation_price(100, "long") == 100
        assert LeverageConfig(0).liquidation_price(100, "short") == 100

    def test_spot_leverage_returns_entry(self):
        assert LeverageConfig(1.0).liquidation_price(100, "long") == 100
        assert LeverageConfig(1.0).liquidation_price(100, "short") == 100


class TestParamRangeSafety:
    def test_zero_step_returns_min(self):
        r = ParamRange(min=10, max=20, step=0)
        assert r.values() == [10]

    def test_negative_step_returns_min(self):
        r = ParamRange(min=10, max=20, step=-1)
        assert r.values() == [10]
