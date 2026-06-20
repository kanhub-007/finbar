"""Contract tests for MultiTimeframeBarEnricher.

Scenario S1: Enricher produces the same merged frame as finbar's current
backtest path.

The golden reference is computed inline using the same primitives
(PandasTaIndicatorCalculator, PandasBarFrameConverter,
PandasTimeframeBarMerger, PandasStrategyFeatureCalculator) orchestrated
the same way the current finbar path does — indicator jobs per timeframe,
then framing + merge + features.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from finbar_strategy_runtime.parser.strategy_definition_parser import (
    StrategyDefinitionParser,
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

# ---------------------------------------------------------------------------
# Paths to finbar project data (the package is a subdirectory of the repo)
# ---------------------------------------------------------------------------
# Path(__file__) = .../packages/strategy-runtime/tests/contract/test_...
# .parents[2]    = .../packages/strategy-runtime/  (package root)
# .parents[3]    = .../packages/                    (monorepo packages dir)
# .parents[4]    = .../finbar/                      (repo root)
_REPO_ROOT = Path(__file__).resolve().parents[4]
_FINBAR_ROOT = _REPO_ROOT
_DB_PATH = _FINBAR_ROOT / "data" / "finbar.db"
_STRATEGY_YAML = (
    _FINBAR_ROOT
    / "strategies"
    / "intraday_scalper"
    / "14_amt_value_reject_30m_1h_mtf.yaml"
)

# Minimum required columns for a valid OHLCV bar dict
_OHLCV_COLS = {"open", "high", "low", "close", "volume", "timestamp"}


def _load_raw_bars(interval: str, limit: int | None = None) -> list[dict]:
    """Load raw OHLCV bars (only base columns, no indicators) from the DB."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    query = "SELECT timestamp, open, high, low, close, volume FROM price_bar WHERE symbol = 'SOL' AND interval = ? ORDER BY timestamp ASC"
    if limit is not None:
        query += f" LIMIT {limit}"
    rows = conn.execute(query, (interval,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _parse_strategy() -> tuple:
    """Parse the production MTF strategy and return definition + indicator splits."""
    yaml_text = _STRATEGY_YAML.read_text(encoding="utf-8")
    parser = StrategyDefinitionParser()
    validation = parser.parse(yaml_text, {})
    assert validation.valid, f"Strategy parse failed: {validation.errors}"
    definition = validation.definition
    assert definition is not None
    return (
        definition,
        list(validation.primary_required_indicators),
        dict(validation.informative_required_indicators),
    )


def _current_path_merged_frame(
    primary_bars: list[dict],
    info_bars: dict[str, list[dict]],
    definition,
    primary_req: list[str],
    info_req: dict[str, list[str]],
) -> pd.DataFrame:
    """Replicate what the current finbar path produces.

    This is the same orchestration as:
      1. Per-timeframe indicator jobs (indicator_calculator on each frame)
      2. _prepare_frame (framing + merge)
      3. _resolve_and_compute_signals (features, if any)

    The enricher should produce the exact same output from the same inputs.
    """
    converter = PandasBarFrameConverter()
    calculator = PandasTaIndicatorCalculator()
    merger = PandasTimeframeBarMerger()
    feature_calc = PandasStrategyFeatureCalculator()

    # Step 1: Frame primary bars + compute primary indicators
    primary_df = converter.bars_to_frame(primary_bars)
    if primary_req:
        primary_df = calculator.calculate(primary_df, primary_req)

    # Step 2: For each informative timeframe, frame + compute + merge
    timeframes = definition.timeframes
    if timeframes is None or not timeframes.has_informative():
        # No informative — just features on the primary frame
        return _apply_features(feature_calc, primary_df, definition)

    frame = primary_df
    for item in timeframes.informative:
        alias = item.alias
        bars = info_bars.get(alias)
        if bars is None:
            raise ValueError(f"Missing informative bars for timeframe '{alias}'")
        info_df = converter.bars_to_frame(bars)
        indicators = info_req.get(alias, [])
        if indicators:
            info_df = calculator.calculate(info_df, indicators)
        frame = merger.merge(frame, info_df, item.interval)

    # Step 3: Compute features on the merged frame
    return _apply_features(feature_calc, frame, definition)


def _apply_features(feature_calc, frame, definition) -> pd.DataFrame:
    """Apply feature calculator if features are declared."""
    if definition.features:
        return feature_calc.calculate(frame, definition.features)
    return frame


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sol_primary_bars() -> list[dict]:
    """Load SOL 30min raw bars from the DB."""
    return _load_raw_bars("30min")


@pytest.fixture(scope="module")
def sol_info_bars() -> dict[str, list[dict]]:
    """Load SOL 1h raw bars from the DB."""
    bars = _load_raw_bars("1h")
    return {"h1": bars}


@pytest.fixture(scope="module")
def strategy_context() -> tuple:
    """Parse the production strategy and return (definition, primary_req, info_req)."""
    return _parse_strategy()


# ---------------------------------------------------------------------------
# Scenario S1: Enricher = current path
# ---------------------------------------------------------------------------


class TestMultiTimeframeBarEnricher:
    """Black-box tests for the enricher — assert on outcomes, never interactions."""

    def test_s1_enricher_equals_current_path_mtf(
        self, sol_primary_bars, sol_info_bars, strategy_context
    ):
        """The enricher produces the same merged frame as the current finbar path."""
        definition, primary_req, info_req = strategy_context

        # Golden reference: current orchestration
        golden = _current_path_merged_frame(
            sol_primary_bars, sol_info_bars, definition, primary_req, info_req
        )

        # Enricher with same dependencies
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

        # Assert: column-for-column and value-for-value equal
        pd.testing.assert_frame_equal(result, golden, check_like=True)

    def test_s1_enricher_single_tf_no_informative(self, strategy_context):
        """Single-timeframe strategy: enricher computes primary + features only."""
        definition, primary_req, _ = strategy_context

        # Create a single-TF definition (no informative)
        from dataclasses import replace

        from finbar_strategy_runtime.domain.entities.timeframe_declaration import (
            TimeframeDeclaration,
        )

        single_tf_def = replace(
            definition,
            timeframes=TimeframeDeclaration(primary="30min", informative=[]),
        )

        # Use a small subset of bars for speed
        bars = _load_raw_bars("30min", limit=500)

        # Golden: current path (primary-only, no merge)
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

    # -- Edge cases from spec "Also test" ---------------------------------

    def test_empty_primary_bars_returns_empty_frame(self, strategy_context):
        """Empty primary bars: returns an empty frame (parity with current path)."""
        definition, primary_req, _ = strategy_context
        from dataclasses import replace

        from finbar_strategy_runtime.domain.entities.timeframe_declaration import (
            TimeframeDeclaration,
        )

        # Use a single-TF definition to avoid needing informative bars
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
        """Missing informative bars for a declared timeframe raises ValueError."""
        definition, primary_req, info_req = strategy_context

        bars = _load_raw_bars("30min", limit=100)
        enricher = MultiTimeframeBarEnricher(
            indicator_calculator=PandasTaIndicatorCalculator(),
            bar_converter=PandasBarFrameConverter(),
            timeframe_merger=PandasTimeframeBarMerger(),
        )

        with pytest.raises(ValueError, match="Missing informative bars"):
            enricher.enrich(
                primary_bars=bars,
                informative_bars={},  # empty — no "h1" key
                definition=definition,
                primary_required_indicators=primary_req,
                informative_required_indicators=info_req,
            )

    def test_informative_supplied_for_single_tf_raises_valueerror(
        self, strategy_context
    ):
        """Supplying informative_bars for a single-TF strategy raises ValueError."""
        definition, primary_req, _ = strategy_context
        from dataclasses import replace

        from finbar_strategy_runtime.domain.entities.timeframe_declaration import (
            TimeframeDeclaration,
        )

        single_tf_def = replace(
            definition,
            timeframes=TimeframeDeclaration(primary="30min", informative=[]),
        )

        bars = _load_raw_bars("30min", limit=100)
        enricher = MultiTimeframeBarEnricher(
            indicator_calculator=PandasTaIndicatorCalculator(),
            bar_converter=PandasBarFrameConverter(),
            timeframe_merger=PandasTimeframeBarMerger(),
        )

        with pytest.raises(ValueError, match="has no timeframes"):
            enricher.enrich(
                primary_bars=bars,
                informative_bars={"h1": _load_raw_bars("1h", limit=50)},
                definition=single_tf_def,
                primary_required_indicators=primary_req,
                informative_required_indicators={},
            )

    def test_features_computed_when_no_informative(self, strategy_context):
        """Features are computed on the primary frame when no informative declared."""
        definition, primary_req, _ = strategy_context
        from dataclasses import replace

        from finbar_strategy_runtime.domain.entities.feature_spec import FeatureSpec
        from finbar_strategy_runtime.domain.entities.timeframe_declaration import (
            TimeframeDeclaration,
        )

        # Create a single-TF definition with features
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

        bars = _load_raw_bars("30min", limit=200)

        # Golden: current path (primary + features)
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
