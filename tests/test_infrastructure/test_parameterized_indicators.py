"""Tests for parameterized indicator enrichment and catalog resolution."""

import pandas as pd
import pytest

from finbar.core.application.services.strategy_definition_parser import (
    StrategyDefinitionParser,
)
from finbar.core.application.services.strategy_indicator_catalog import (
    StrategyIndicatorCatalog,
)
from finbar.infrastructure.services.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)


def _bars_frame(close_values: list[float]) -> pd.DataFrame:
    n = len(close_values)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": close_values,
            "high": [c + 1 for c in close_values],
            "low": [c - 1 for c in close_values],
            "close": close_values,
            "volume": [1000] * n,
        },
        index=idx,
    )


class TestParameterizedIndicatorCatalog:
    def test_resolves_arbitrary_sma_period(self):
        """Any sma period within range resolves to a concrete column."""
        catalog = StrategyIndicatorCatalog()

        assert catalog.resolve("sma", 37) == "sma_37"

    def test_resolves_arbitrary_rsi_period(self):
        """Any rsi period within range resolves to a concrete column."""
        catalog = StrategyIndicatorCatalog()

        assert catalog.resolve("rsi", 21) == "rsi_21"

    def test_rejects_out_of_range_period(self):
        """Periods outside the supported range are rejected."""
        catalog = StrategyIndicatorCatalog()

        assert catalog.resolve("sma", 1000) is None

    def test_supports_concrete_recognises_dynamic_names(self):
        """Dynamic concrete column names are recognised as supported."""
        catalog = StrategyIndicatorCatalog()

        assert catalog.supports_concrete("sma_37") is True

    def test_reports_parameterized_enabled_in_as_dict(self):
        """Capability discovery now advertises parameterized indicators."""
        result = StrategyIndicatorCatalog().as_dict()

        assert result["parameterized_indicators_enabled"] is True
        assert "period_ranges" in result


class TestParameterizedIndicatorsCalculator:
    def test_computes_arbitrary_sma_period(self):
        """A dynamic sma name like sma_37 is computed by the calculator."""
        frame = _bars_frame([100.0] * 50)
        calc = PandasTaIndicatorCalculator()

        result = calc.calculate(frame.copy(), ["sma_37"])

        assert "sma_37" in result.columns
        assert result["sma_37"].iloc[-1] == pytest.approx(100.0, rel=0.01)

    def test_computes_arbitrary_rsi_period(self):
        """A dynamic rsi name like rsi_21 is computed by the calculator."""
        frame = _bars_frame([100.0 + i * 0.5 for i in range(30)])
        calc = PandasTaIndicatorCalculator()

        result = calc.calculate(frame.copy(), ["rsi_21"])

        assert "rsi_21" in result.columns
        assert result["rsi_21"].notna().any()

    def test_handles_too_few_bars_for_dynamic_period(self):
        """Dynamic indicators handle insufficient bars gracefully."""
        frame = _bars_frame([100.0] * 5)
        calc = PandasTaIndicatorCalculator()

        result = calc.calculate(frame.copy(), ["sma_37"])

        # Column exists but all NaN (skip-warning from min_bars check)
        assert "sma_37" not in result.columns or result["sma_37"].isna().all()


@pytest.mark.parametrize(
    "indicator_type,period,expect",
    [
        ("sma", 20, "sma_20"),
        ("sma", 50, "sma_50"),
        ("sma", 37, "sma_37"),
        ("ema", 12, "ema_12"),
        ("ema", 100, "ema_100"),
        ("rsi", 7, "rsi_7"),
        ("rsi", 14, "rsi_14"),
        ("rsi", 21, "rsi_21"),
    ],
)
def test_catalog_resolves_known_and_arbitrary_periods(indicator_type, period, expect):
    """Previously hardcoded periods and new arbitrary periods all resolve."""
    assert StrategyIndicatorCatalog().resolve(indicator_type, period) == expect


class TestParameterizedStrategyValidation:
    def test_strategy_with_arbitrary_sma_period_validates(self):
        """A strategy declaring sma 37 is now valid."""
        strategy = {
            "schema_version": "2.0",
            "name": "custom_sma_test",
            "indicators": [
                {"name": "fast", "type": "sma", "period": 37},
                {"name": "slow", "type": "sma", "period": 120},
            ],
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "all": [
                                {
                                    "left": "fast",
                                    "operator": "crosses_above",
                                    "right": "slow",
                                }
                            ]
                        }
                    }
                }
            },
        }

        result = StrategyDefinitionParser().parse(strategy)

        assert result.valid is True
        assert result.required_indicators == ["sma_37", "sma_120"]

    def test_strategy_with_out_of_range_period_is_rejected(self):
        """Periods outside supported ranges produce validation errors."""
        strategy = {
            "schema_version": "2.0",
            "name": "bad_sma",
            "indicators": [{"name": "fast", "type": "sma", "period": 1000}],
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "all": [
                                {
                                    "left": "fast",
                                    "operator": ">",
                                    "right": "close",
                                }
                            ]
                        }
                    }
                }
            },
        }

        result = StrategyDefinitionParser().parse(strategy)

        assert result.valid is False
        assert any(error.code == "unsupported_indicator" for error in result.errors)

    def test_strategy_with_arbitrary_rsi_period_validates(self):
        """A strategy declaring rsi 21 is now valid."""
        strategy = {
            "schema_version": "2.0",
            "name": "custom_rsi_test",
            "indicators": [{"name": "my_rsi", "type": "rsi", "period": 21}],
            "sides": {
                "long": {
                    "entry": {
                        "condition": {
                            "all": [
                                {
                                    "left": "my_rsi",
                                    "operator": "<",
                                    "right": 40,
                                }
                            ]
                        }
                    }
                }
            },
        }

        result = StrategyDefinitionParser().parse(strategy)

        assert result.valid is True
        assert result.required_indicators == ["rsi_21"]
