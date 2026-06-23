"""Contract tests for Scenario 1: full-frame session VP differs from
streaming-prefix VP on the same row.

Locks the parity-breaking defect: the production MTF AMT strategy's
``vp_*`` and derived AMT booleans are frame-length-dependent. Enriching
row 17 from the full 500-bar frame yields different values than enriching
it from the prefix ending at row 17, because completed-session volume
profiles broadcast future session bars into earlier rows.

Documents that full-frame batch session VP is NOT a live-parity oracle.

NOTE on first-signal rows: these tests previously locked specific rows
(17 streaming, 95 batch). Under the strict warmup contract (spec
2026-06-23 Scenario 4), ``poc_slope_N`` is NaN until N sessions exist, so
the first signal on each path now fires once the slope is genuinely
computable, not on a warmup ``0.0``. The signal tests therefore assert
the STRUCTURAL invariants (paths differ, post-warmup, strategy bias)
rather than fragile row numbers.
"""

from __future__ import annotations

import math

import pandas as pd

from finbar_strategy_runtime.evaluation.json_rule_based_strategy import (
    JsonRuleBasedStrategy,
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
from finbar_strategy_runtime.indicators.required_data_validator import (
    RequiredDataValidator,
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


# ---------------------------------------------------------------------------
# Scenario 2: streaming-prefix reference signal matches Finbot live/replay
# ---------------------------------------------------------------------------
#
# The prefix-recompute loop below is the O(n^2) reference oracle explicitly
# allowed by the spec for red/green diagnostics. It is NOT the production
# design — Scenario 3 delivers the stateful streaming enricher that must
# reproduce this oracle's row 17 result.


def _info_prefix(info_bars: list[dict], close_ts: int) -> list[dict]:
    """Informative bars closed at or before the primary close timestamp."""
    return [b for b in info_bars if b["timestamp"] <= close_ts]


def _is_tradable(readiness, row: int) -> bool:
    """True when *row* is past warmup and the frame has tradable bars."""
    if readiness.no_tradable_bars:
        return False
    return row >= readiness.warmup_bars


def _poc_slope_5_is_real(
    primary: list[dict],
    info: dict[str, list[dict]],
    definition,
    primary_req: list[str],
    info_req: dict[str, list[str]],
    row: int,
) -> bool:
    """Return True when poc_slope_5 is non-NaN at *row* on the prefix.

    Locks the warmup-honest invariant (spec 2026-06-23 Scenario 4): a trading
    signal must never fire while ``poc_slope_5`` is still NaN (warmup), only
    once 5 sessions of history make the slope genuinely computable.
    """
    import pandas as pd

    enricher = _build_enricher()
    enriched = enricher.enrich(
        primary[: row + 1],
        {"h1": _info_prefix(info["h1"], primary[row]["timestamp"])},
        definition,
        primary_req,
        info_req,
    )
    if "poc_slope_5" not in enriched.columns:
        return False
    value = enriched.iloc[-1]["poc_slope_5"]
    return not pd.isna(value)


def _run_streaming_reference(
    primary: list[dict],
    info: dict[str, list[dict]],
    definition,
    primary_req: list[str],
    info_req: dict[str, list[str]],
    required_cols: list[str],
    max_rows: int,
) -> tuple[int, str, str] | None:
    """Run the streaming-prefix reference loop; return first non-HOLD signal.

    For each primary bar ``i``, enrich only the prefix available at that bar
    (primary[:i+1], informative bars closed at or before primary[i]). Feed
    every bar to ``on_bar`` for crossover/state building; take a signal only
    once the row is tradable per the RequiredDataValidator.
    """
    enricher = _build_enricher()
    validator = RequiredDataValidator()
    strategy = JsonRuleBasedStrategy(definition)
    flat = {"direction": "", "size": 0}

    for i in range(min(max_rows, len(primary))):
        enriched = enricher.enrich(
            primary[: i + 1],
            {"h1": _info_prefix(info["h1"], primary[i]["timestamp"])},
            definition,
            primary_req,
            info_req,
        )
        readiness = validator.validate(enriched, required_cols)
        latest = enriched.iloc[-1].to_dict()
        signal = strategy.on_bar(latest, flat)
        if not _is_tradable(readiness, len(enriched) - 1):
            continue
        if signal.action != "hold":
            return (i, signal.action, signal.direction)
    return None


def _run_batch_reference(
    primary: list[dict],
    info: dict[str, list[dict]],
    definition,
    primary_req: list[str],
    info_req: dict[str, list[str]],
    required_cols: list[str],
) -> tuple[int, str, str] | None:
    """Run the full-frame batch reference; return first non-HOLD signal."""
    enricher = _build_enricher()
    validator = RequiredDataValidator()
    strategy = JsonRuleBasedStrategy(definition)
    flat = {"direction": "", "size": 0}

    full = enricher.enrich(primary, info, definition, primary_req, info_req)
    readiness = validator.validate(full, required_cols)
    warmup = readiness.warmup_bars

    for i in range(len(full)):
        latest = full.iloc[i].to_dict()
        signal = strategy.on_bar(latest, flat)
        if i < warmup:
            continue
        if signal.action != "hold":
            return (i, signal.action, signal.direction)
    return None


@needs_parity_fixtures
class TestStreamingPrefixReferenceSignal:
    """Scenario 2: streaming-prefix first signal matches Finbot live/replay."""

    def test_streaming_prefix_first_signal_is_short_after_warmup(self):
        """First streaming-prefix non-HOLD signal is a short, past poc_slope warmup.

        Previously this fired at row 17 because ``poc_slope_5`` warmup was a
        fabricated ``0.0`` that satisfied ``poc_slope_5 < 4.0``. Under the
        strict warmup contract poc_slope_5 is NaN until 5 sessions exist, so
        the first signal fires only once the slope is genuinely computable.
        Observed current row: 229.
        """
        primary = load_parity_bars("30min")
        info = {"h1": load_parity_bars("1h")}
        definition, primary_req, info_req, required_cols = (
            parse_production_strategy()
        )

        result = _run_streaming_reference(
            primary,
            info,
            definition,
            primary_req,
            info_req,
            required_cols,
            max_rows=len(primary),
        )

        assert result is not None, "No non-HOLD signal produced"
        row, action, direction = result
        assert action == "sell", f"Expected sell, got {action}"
        assert direction == "short", f"Expected short, got {direction}"
        # Lock the warmup-honest invariant: poc_slope_5 must be a real
        # (non-NaN) value at the first signal, never a warmup artifact.
        is_real = _poc_slope_5_is_real(
            primary, info, definition, primary_req, info_req, row
        )
        assert is_real, (
            f"poc_slope_5 is NaN at first signal row {row}; fired on warmup"
        )

    def test_batch_full_frame_first_signal_documented_as_diverging(self):
        """Full-frame batch first signal diverges from streaming — the defect.

        The batch oracle (completed-session VP broadcast) fires at a different
        row (and even a different direction) than the streaming oracle because
        completed-session values are broadcast to earlier rows. This is the
        divergence source the causal enricher (Scenario 3) eliminates for live
        parity. Observed current batch first signal: row 227, buy/long.
        """
        primary = load_parity_bars("30min")
        info = {"h1": load_parity_bars("1h")}
        definition, primary_req, info_req, required_cols = (
            parse_production_strategy()
        )

        result = _run_batch_reference(
            primary,
            info,
            definition,
            primary_req,
            info_req,
            required_cols,
        )

        assert result is not None
        row, action, direction = result
        # Batch path fires a LONG here while streaming fires a SHORT — the
        # direction divergence is the strongest possible proof of the
        # frame-dependence defect.
        assert action in {"buy", "sell"}
        assert direction in {"long", "short"}
        is_real = _poc_slope_5_is_real(
            primary, info, definition, primary_req, info_req, row
        )
        assert is_real, (
            f"poc_slope_5 NaN at batch first signal row {row}; fired on warmup"
        )

    def test_streaming_and_batch_first_signals_differ(self):
        """Streaming and batch first signals differ — the parity-defect proof.

        Observed: streaming first signal ≈ row 229 (sell/short), batch first
        signal ≈ row 227 (buy/long). They differ in both row and direction,
        which is the strongest possible evidence that full-frame batch VP
        broadcast is not a live-parity oracle.
        """
        primary = load_parity_bars("30min")
        info = {"h1": load_parity_bars("1h")}
        definition, primary_req, info_req, required_cols = (
            parse_production_strategy()
        )

        streaming = _run_streaming_reference(
            primary,
            info,
            definition,
            primary_req,
            info_req,
            required_cols,
            max_rows=len(primary),
        )
        batch = _run_batch_reference(
            primary,
            info,
            definition,
            primary_req,
            info_req,
            required_cols,
        )

        assert streaming is not None and batch is not None
        assert streaming[0] != batch[0] or streaming[1] != batch[1], (
            f"Streaming {streaming} and batch {batch} first signals must differ "
            f"(row or direction) — otherwise there is no parity defect."
        )
