"""MultiTimeframeBarEnricher — frames, computes indicators, merges, and adds
features across primary and informative timeframes.

Pure service. The merge uses no-lookahead as-of alignment with interval_offset
(already guaranteed by ``merge_timeframes``), so feeding the closed-bar warmup
window yields correct values even in streaming.
"""

from __future__ import annotations

import pandas as pd

from finbar_strategy_runtime.domain.entities.strategy_definition import (
    StrategyDefinition,
)
from finbar_strategy_runtime.domain.interfaces.bar_frame_converter import (
    BarFrameConverter,
)
from finbar_strategy_runtime.domain.interfaces.indicator_calculator import (
    IndicatorCalculator,
)
from finbar_strategy_runtime.domain.interfaces.strategy_feature_calculator import (
    StrategyFeatureCalculator,
)
from finbar_strategy_runtime.domain.interfaces.timeframe_bar_merger import (
    TimeframeBarMerger,
)


class MultiTimeframeBarEnricher:
    """Frame each timeframe, compute its indicators, merge, then run features.

    Pure service. The caller supplies the per-timeframe indicator split
    (parser output), not re-derived here.
    """

    def __init__(
        self,
        indicator_calculator: IndicatorCalculator,
        bar_converter: BarFrameConverter,
        timeframe_merger: TimeframeBarMerger,
        feature_calculator: StrategyFeatureCalculator | None = None,
    ) -> None:
        """Create the enricher with injected collaborators.

        Args:
            indicator_calculator: Computes indicators on a per-timeframe frame.
            bar_converter: Converts bar dicts to frames and back.
            timeframe_merger: Merges informative columns into the primary frame.
            feature_calculator: Optional derived-feature calculator.
        """
        self._indicator_calculator = indicator_calculator
        self._bar_converter = bar_converter
        self._timeframe_merger = timeframe_merger
        self._feature_calculator = feature_calculator

    def enrich(
        self,
        primary_bars: list[dict],
        informative_bars: dict[str, list[dict]] | list[dict],
        definition: StrategyDefinition,
        primary_required_indicators: list[str],
        informative_required_indicators: dict[str, list[str]],
    ) -> pd.DataFrame:
        """Enrich bars with indicators, merge timeframes, and compute features.

        Args:
            primary_bars: OHLCV bar dicts for the primary timeframe, sorted
                ascending by timestamp.
            informative_bars: Map from timeframe alias to OHLCV bar dicts.
                A flat list is also accepted when there is exactly one
                informative timeframe.
            definition: Parsed strategy definition with ``.timeframes``.
            primary_required_indicators: Indicator names to compute on the
                primary frame.
            informative_required_indicators: Map from alias to indicator
                names to compute on each informative frame.

        Returns:
            A fully enriched DataFrame with all indicator columns, merged
            informative columns (suffixed with the interval, e.g.
            ``poc_slope_5_1h``), and derived feature columns.

        Raises:
            ValueError: If ``informative_bars`` are supplied but the
                strategy declares no timeframes.
            ValueError: If a flat list is supplied when multiple
                informative timeframes are declared.
        """
        # 1. Frame primary bars and compute primary indicators
        primary = self._frame_and_compute(
            primary_bars, primary_required_indicators
        )

        # If primary is empty, skip informative processing
        if len(primary) == 0:
            return primary

        # 2. Handle informative timeframes
        timeframes = definition.timeframes
        if timeframes is None or not timeframes.has_informative():
            self._check_no_informative_supplied(informative_bars)
            return self._compute_features(primary, definition)

        frame = primary
        for item in timeframes.informative:
            bars = self._resolve_informative_bars(
                informative_bars, item, timeframes
            )
            info = self._frame_and_compute(
                bars,
                informative_required_indicators.get(item.alias, []),
            )
            frame = self._timeframe_merger.merge(
                frame, info, item.interval
            )

        # 3. Compute features on the merged frame
        return self._compute_features(frame, definition)

    # -- private step methods ------------------------------------------------

    def _frame_and_compute(
        self, bars: list[dict], indicators: list[str]
    ) -> pd.DataFrame:
        """Convert bars to a frame and compute requested indicators."""
        frame = self._bar_converter.bars_to_frame(bars)
        if indicators:
            frame = self._indicator_calculator.calculate(frame, indicators)
        return frame

    def _compute_features(
        self, frame: pd.DataFrame, definition: StrategyDefinition
    ) -> pd.DataFrame:
        """Apply the feature calculator if features are declared."""
        if self._feature_calculator is not None and definition.features:
            return self._feature_calculator.calculate(
                frame, definition.features
            )
        return frame

    def _resolve_informative_bars(
        self,
        informative_bars: dict[str, list[dict]] | list[dict] | None,
        item,
        timeframes,
    ) -> list[dict]:
        """Resolve informative bars for a single timeframe alias.

        Supports both dict (keyed by alias) and flat list (single
        informative) payload shapes, mirroring the current finbar path.
        """
        raw = informative_bars
        if raw is None:
            raise ValueError(
                f"Missing informative bars for timeframe '{item.alias}'"
            )
        # Validate payload shape upfront when multiple informatives declared
        if isinstance(raw, list) and len(timeframes.informative) > 1:
            raise ValueError(
                "informative_bars must be mapped by timeframe alias"
                " when multiple informative timeframes are declared"
            )
        if isinstance(raw, list):
            return raw
        if item.alias not in raw:
            raise ValueError(
                f"Missing informative bars for timeframe '{item.alias}'"
            )
        return raw[item.alias]

    @staticmethod
    def _check_no_informative_supplied(
        informative_bars: dict[str, list[dict]] | list[dict],
    ) -> None:
        """Raise if informative bars were supplied for a single-TF strategy.

        Both empty dict ``{}`` and empty list ``[]`` are falsy, so they
        pass through without raising — the caller genuinely supplied no
        informative data.
        """
        if informative_bars:
            raise ValueError(
                "informative_bars were supplied but strategy"
                " has no timeframes"
            )
