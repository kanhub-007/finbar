"""Contract tests for MultiTimeframeBarEnricher.

Scenario S1: Enricher produces the same merged frame as finbar's current
backtest path.

The golden reference is computed inline using the same primitives
(PandasTaIndicatorCalculator, PandasBarFrameConverter,
PandasTimeframeBarMerger, PandasStrategyFeatureCalculator) orchestrated
the same way the current finbar path does --- indicator jobs per timeframe,
then framing + merge + features.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from finbar_strategy_runtime.domain.entities.feature_spec import FeatureSpec
from finbar_strategy_runtime.domain.entities.timeframe_declaration import (
    TimeframeDeclaration,
)
from finbar_strategy_runtime.indicators.multi_timeframe_bar_enricher import (
    MultiTimeframeBarEnricher,
)
from finbar_strategy_runtime.indicators.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar_strategy_runtime.indicators.pandas_strategy_feature_calculator import (
    PandasStrategyFeatureCalculator,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)
from finbar_strategy_runtime.indicators.pandas_timeframe_bar_merger import (
    PandasTimeframeBarMerger,
)

from .conftest import load_raw_bars, needs_finbar_data


def _current_path_merged_frame(
    primary_bars: list[dict],
    info_bars: dict[str, list[dict]],
    definition,
    primary_req: list[str],
    info_req: dict[str, list[str]],
) -> pd.DataFrame:
    """Replicate what the current finbar path produces."""
    converter = PandasBarFrameConverter()
    calculator = PandasTaIndicatorCalculator()
    merger = PandasTimeframeBarMerger()
    feature_calc = PandasStrategyFeatureCalculator()

    primary_df = converter.bars_to_frame(primary_bars)
    if primary_req:
        primary_df = calculator.calculate(primary_df, primary_req)

    timeframes = definition.timeframes
    if timeframes is None or not timeframes.has_informative():
        return _apply_features(feature_calc, primary_df, definition)

    frame = primary_df
    for item in timeframes.informative:
        bars = info_bars.get(item.alias)
        if bars is None:
            raise ValueError(
                f"Missing informative bars for timeframe '{item.alias}'"
            )
        info_df = converter.bars_to_frame(bars)
        indicators = info_req.get(item.alias, [])
        if indicators:
            info_df = calculator.calculate(info_df, indicators)
        frame = merger.merge(frame, info_df, item.interval)

    return _apply_features(feature_calc, frame, definition)


def _apply_features(feature_calc, frame, definition) -> pd.DataFrame:
    if definition.features:
        return feature_calc.calculate(frame, definition.features)
    return frame


# ---------------------------------------------------------------------------
# Scenario S1: Enricher = current path
# ---------------------------------------------------------------------------


@needs_finbar_data
class TestMultiTimeframeBarEnricher:
    """Black-box tests for the enricher --- assert on outcomes, never interactions."""

    def test_s1_enricher_equals_current_path_mtf(
        self, sol_primary_bars, sol_info_bars, strategy_context
    ):
        definition, primary_req, info_req, _ = strategy_context

        golden = _current_path_merged_frame(
            sol_primary_bars, sol_info_bars, definition, primary_req, info_req
        )

        enricher = MultiTimeframeBarEnricher(
            indicator_calculator=PandasTaIndicatorCalculator(),
            bar_converter=PandasBarFrameConverter(),
            timeframe_merger=PandasTimeframeBarMerger(),
            feature_calculator=PandasStrategyFeatureCalculator(),
        )
        result = enricher.enrich(
            primary_bars=sol_primary_bars,
            informative_bars=sol_info_bars,
            definition=definition,
            primary_required_indicators=primary_req,
            informative_required_indicators=info_req,
        )

        pd.testing.assert_frame_equal(result, golden, check_like=True)

        # Non-silent assertion: verify MTF columns are actually present
        # and non-NaN — guards against the tautology where both enricher
        # and golden miss the same columns due to undeclared dependencies.
        _mtf_cols = ["poc_slope_5_1h", "above_value_1h", "below_value_1h"]
        for col in _mtf_cols:
            assert col in result.columns, f"Missing MTF column: {col}"
            assert result[col].notna().any(), (
                f"MTF column {col} is all-NaN"
            )

    def test_s1_enricher_single_tf_no_informative(self, strategy_context):
        definition, primary_req, _, _ = strategy_context

        single_tf_def = replace(
            definition,
            timeframes=TimeframeDeclaration(primary="30min", informative=[]),
        )

        bars = load_raw_bars("30min", limit=500)

        golden = _current_path_merged_frame(
            bars, {}, single_tf_def, primary_req, {}
        )

        enricher = MultiTimeframeBarEnricher(
            indicator_calculator=PandasTaIndicatorCalculator(),
            bar_converter=PandasBarFrameConverter(),
            timeframe_merger=PandasTimeframeBarMerger(),
            feature_calculator=PandasStrategyFeatureCalculator(),
        )
        result = enricher.enrich(
            primary_bars=bars,
            informative_bars={},
            definition=single_tf_def,
            primary_required_indicators=primary_req,
            informative_required_indicators={},
        )

        pd.testing.assert_frame_equal(result, golden, check_like=True)

    # -- Edge cases -------------------------------------------------------

    def test_empty_primary_bars_returns_empty_frame(self, strategy_context):
        definition, primary_req, _, _ = strategy_context

        single_tf_def = replace(
            definition,
            timeframes=TimeframeDeclaration(primary="30min", informative=[]),
        )

        enricher = MultiTimeframeBarEnricher(
            indicator_calculator=PandasTaIndicatorCalculator(),
            bar_converter=PandasBarFrameConverter(),
            timeframe_merger=PandasTimeframeBarMerger(),
            feature_calculator=PandasStrategyFeatureCalculator(),
        )
        result = enricher.enrich(
            primary_bars=[],
            informative_bars={},
            definition=single_tf_def,
            primary_required_indicators=primary_req,
            informative_required_indicators={},
        )

        assert result.empty

    def test_missing_informative_bars_raises_valueerror(self, strategy_context):
        definition, primary_req, info_req, _ = strategy_context

        bars = load_raw_bars("30min", limit=100)
        enricher = MultiTimeframeBarEnricher(
            indicator_calculator=PandasTaIndicatorCalculator(),
            bar_converter=PandasBarFrameConverter(),
            timeframe_merger=PandasTimeframeBarMerger(),
        )

        with pytest.raises(ValueError, match="Missing informative bars"):
            enricher.enrich(
                primary_bars=bars,
                informative_bars={},
                definition=definition,
                primary_required_indicators=primary_req,
                informative_required_indicators=info_req,
            )

    def test_informative_supplied_for_single_tf_raises_valueerror(
        self, strategy_context
    ):
        definition, primary_req, _, _ = strategy_context

        single_tf_def = replace(
            definition,
            timeframes=TimeframeDeclaration(primary="30min", informative=[]),
        )

        bars = load_raw_bars("30min", limit=100)
        enricher = MultiTimeframeBarEnricher(
            indicator_calculator=PandasTaIndicatorCalculator(),
            bar_converter=PandasBarFrameConverter(),
            timeframe_merger=PandasTimeframeBarMerger(),
        )

        with pytest.raises(ValueError, match="has no timeframes"):
            enricher.enrich(
                primary_bars=bars,
                informative_bars={"h1": load_raw_bars("1h", limit=50)},
                definition=single_tf_def,
                primary_required_indicators=primary_req,
                informative_required_indicators={},
            )

    def test_features_computed_when_no_informative(self, strategy_context):
        definition, primary_req, _, _ = strategy_context

        feature = FeatureSpec(
            name="close_gt_open",
            type="formula",
            raw_expr={"operator": ">", "left": "close", "right": "open"},
        )
        single_tf_def = replace(
            definition,
            timeframes=TimeframeDeclaration(primary="30min", informative=[]),
            features=[feature],
        )

        bars = load_raw_bars("30min", limit=200)

        golden = _current_path_merged_frame(
            bars, {}, single_tf_def, primary_req, {}
        )

        enricher = MultiTimeframeBarEnricher(
            indicator_calculator=PandasTaIndicatorCalculator(),
            bar_converter=PandasBarFrameConverter(),
            timeframe_merger=PandasTimeframeBarMerger(),
            feature_calculator=PandasStrategyFeatureCalculator(),
        )
        result = enricher.enrich(
            primary_bars=bars,
            informative_bars={},
            definition=single_tf_def,
            primary_required_indicators=primary_req,
            informative_required_indicators={},
        )

        assert "close_gt_open" in result.columns
        pd.testing.assert_frame_equal(result, golden, check_like=True)

    # -- Scenario S4: Sliding warmup window ---------------------------------

    def test_s4_sliding_warmup_window_matches_full_enrich(
        self, sol_primary_bars, strategy_context
    ):
        """Latest row of windowed enrich = corresponding row of full enrich.

        Uses a simple SMA strategy (no session-dependent VP indicators) so
        the result is independent of window size.
        """
        definition, _, _, _ = strategy_context

        simple_def = replace(
            definition,
            features=[],
            timeframes=TimeframeDeclaration(primary="30min", informative=[]),
        )

        enricher = MultiTimeframeBarEnricher(
            indicator_calculator=PandasTaIndicatorCalculator(),
            bar_converter=PandasBarFrameConverter(),
            timeframe_merger=PandasTimeframeBarMerger(),
            feature_calculator=PandasStrategyFeatureCalculator(),
        )

        primary_req = ["sma_20"]
        full = enricher.enrich(
            primary_bars=sol_primary_bars,
            informative_bars={},
            definition=simple_def,
            primary_required_indicators=primary_req,
            informative_required_indicators={},
        )

        window_size = 500
        windowed_primary = sol_primary_bars[-window_size:]
        windowed = enricher.enrich(
            primary_bars=windowed_primary,
            informative_bars={},
            definition=simple_def,
            primary_required_indicators=primary_req,
            informative_required_indicators={},
        )

        assert set(windowed.columns) == set(full.columns)

        for col in ["open", "high", "low", "close", "volume"]:
            assert windowed[col].iloc[-1] == full[col].iloc[-1]

        assert (
            abs(windowed["sma_20"].iloc[-1] - full["sma_20"].iloc[-1]) < 1e-6
        )
