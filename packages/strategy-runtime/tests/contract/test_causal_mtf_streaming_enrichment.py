"""Contract tests for Scenario 1: full-frame session VP differs from
streaming-prefix VP on the same row.

Locks the parity-breaking defect: the production MTF AMT strategy's
``vp_*`` and derived AMT booleans are frame-length-dependent. Enriching
row 17 from the full 500-bar frame yields different values than enriching
it from the prefix ending at row 17, because completed-session volume
profiles broadcast future session bars into earlier rows.

Documents that full-frame batch session VP is NOT a live-parity oracle.
"""

from __future__ import annotations

import math

import pandas as pd

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

from .conftest import (
    load_parity_bars,
    needs_parity_fixtures,
    parse_production_strategy,
)

# Row documented by the Finbot parity investigation. The committed CSV
# fixture freezes the data snapshot so this index stays deterministic.
_ROW = 17


def _build_enricher() -> MultiTimeframeBarEnricher:
    return MultiTimeframeBarEnricher(
        indicator_calculator=PandasTaIndicatorCalculator(),
        bar_converter=PandasBarFrameConverter(),
        timeframe_merger=PandasTimeframeBarMerger(),
        feature_calculator=PandasStrategyFeatureCalculator(),
    )


def _info_prefix(info_bars: list[dict], close_ts: int) -> list[dict]:
    """Informative bars closed at or before the primary close timestamp."""
    return [b for b in info_bars if b["timestamp"] <= close_ts]


@needs_parity_fixtures
class TestFullFrameVsPrefixDivergence:
    """Black-box: full-frame batch VP/AMT is not a live-parity oracle."""

    def test_int_second_timestamps_parse_to_real_dates(self):
        """Converter parses int-second bar timestamps correctly.

        Guards against the int-seconds-as-nanoseconds misparse: the
        enriched index must match the real fixture timestamps, not 1970.
        """
        primary = load_parity_bars("30min")
        definition, primary_req, info_req, _ = parse_production_strategy()
        info = {"h1": load_parity_bars("1h")}

        full = _build_enricher().enrich(
            primary, info, definition, primary_req, info_req
        )

        assert full.index[_ROW] == pd.Timestamp(
            primary[_ROW]["timestamp"], unit="s", tz="UTC"
        )
        assert str(full.index[0].date()) != "1970-01-01"

    def test_row_17_vp_and_amt_differ_full_vs_prefix(self):
        """vp_vah, near_vah, rejection_from_edge differ at row 17."""
        primary = load_parity_bars("30min")
        info = {"h1": load_parity_bars("1h")}
        definition, primary_req, info_req, _ = parse_production_strategy()
        enricher = _build_enricher()

        close_ts = primary[_ROW]["timestamp"]
        full = enricher.enrich(primary, info, definition, primary_req, info_req)
        prefix = enricher.enrich(
            primary[: _ROW + 1],
            {"h1": _info_prefix(info["h1"], close_ts)},
            definition,
            primary_req,
            info_req,
        )

        assert full.index[_ROW] == prefix.index[_ROW]

        for col in ("vp_vah", "near_vah", "rejection_from_edge"):
            full_val = full[col].iloc[_ROW]
            prefix_val = prefix[col].iloc[_ROW]
            assert full_val != prefix_val, (
                f"{col} should differ at row {_ROW} (full-frame lookahead): "
                f"full={full_val!r}, prefix={prefix_val!r}"
            )

    def test_row_200_vp_still_differs_not_just_warmup(self):
        """Divergence persists past warmup (row 200), proving it is not a
        startup artefact but a structural frame-dependence."""
        primary = load_parity_bars("30min")
        info = {"h1": load_parity_bars("1h")}
        definition, primary_req, info_req, _ = parse_production_strategy()
        enricher = _build_enricher()

        row = 200
        close_ts = primary[row]["timestamp"]
        full = enricher.enrich(primary, info, definition, primary_req, info_req)
        prefix = enricher.enrich(
            primary[: row + 1],
            {"h1": _info_prefix(info["h1"], close_ts)},
            definition,
            primary_req,
            info_req,
        )

        assert full["vp_vah"].iloc[row] != prefix["vp_vah"].iloc[row]

    def test_scalar_causal_indicator_matches_full_vs_prefix(self):
        """Causal scalar indicators (atr) match full vs prefix within tolerance.

        Proves the divergence is isolated to frame-dependent VP/AMT, not a
        general prefix-vs-full mismatch.
        """
        primary = load_parity_bars("30min")
        info = {"h1": load_parity_bars("1h")}
        definition, primary_req, info_req, _ = parse_production_strategy()
        enricher = _build_enricher()

        close_ts = primary[_ROW]["timestamp"]
        full = enricher.enrich(primary, info, definition, primary_req, info_req)
        prefix = enricher.enrich(
            primary[: _ROW + 1],
            {"h1": _info_prefix(info["h1"], close_ts)},
            definition,
            primary_req,
            info_req,
        )

        full_atr = full["atr"].iloc[_ROW]
        prefix_atr = prefix["atr"].iloc[_ROW]
        assert math.isclose(full_atr, prefix_atr, rel_tol=1e-9, abs_tol=1e-12), (
            f"atr should match (causal) at row {_ROW}: "
            f"full={full_atr}, prefix={prefix_atr}"
        )

    def test_prefix_vp_matches_expanding_session_definition(self):
        """Prefix VP equals the expanding current-session definition.

        The prefix enrichment's vp_vah at row 17 must equal the expanding
        current-session profile (Scenario 4), confirming the prefix IS the
        causal reference the live-parity mode must reproduce.
        """
        from finbar_strategy_runtime.domain.services.volume_profile import (
            compute_expanding_session_volume_profiles,
        )

        primary = load_parity_bars("30min")
        info = {"h1": load_parity_bars("1h")}
        definition, primary_req, info_req, _ = parse_production_strategy()
        enricher = _build_enricher()

        close_ts = primary[_ROW]["timestamp"]
        prefix = enricher.enrich(
            primary[: _ROW + 1],
            {"h1": _info_prefix(info["h1"], close_ts)},
            definition,
            primary_req,
            info_req,
        )

        # Build the expanding-session reference on the same primary prefix.
        primary_frame = PandasBarFrameConverter().bars_to_frame(primary[: _ROW + 1])
        expanding = compute_expanding_session_volume_profiles(primary_frame)

        assert math.isclose(
            prefix["vp_vah"].iloc[_ROW],
            expanding["vp_vah"].iloc[_ROW],
            rel_tol=1e-9,
            abs_tol=1e-9,
        )
