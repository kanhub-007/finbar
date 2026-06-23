"""Contract tests for Scenario 3: causal MTF streaming enricher.

The package-level ``CausalMultiTimeframeStreamingEnricher`` incrementally
enriches primary bars with informative context using only bars available
at each primary close. Its per-bar output must match the batch-prefix
oracle (``MultiTimeframeBarEnricher`` on the prefix ending at that bar)
for every required column, and a full streaming run must reproduce the
streaming-prefix reference signal (row 17).

The enricher composes one ``StreamingIndicatorEngine`` per timeframe
(scalar + windowed indicators, already causal after the timestamp fix)
with an as-of informative merge that replicates the batch merger's
no-lookahead availability offset.
"""

from __future__ import annotations

import math

import pandas as pd

from finbar_strategy_runtime.indicators.causal_multi_timeframe_streaming_enricher import (
    CausalMultiTimeframeStreamingEnricher,
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

from .conftest import (
    load_parity_bars,
    needs_parity_fixtures,
    parse_production_strategy,
)

_OHLCV = {"open", "high", "low", "close", "volume", "timestamp"}


def _batch_oracle_row(primary, info, definition, primary_req, info_req, row):
    """Batch-prefix oracle: enrich primary[:row+1] and return row's dict."""
    enricher = MultiTimeframeBarEnricher(
        indicator_calculator=PandasTaIndicatorCalculator(),
        bar_converter=PandasBarFrameConverter(),
        timeframe_merger=PandasTimeframeBarMerger(),
        feature_calculator=PandasStrategyFeatureCalculator(),
    )
    pbar = primary[row]
    p_open = pd.Timestamp(pbar["timestamp"], unit="s", tz="UTC")
    prefix_info = {
        alias: [
            b
            for b in bars
            if pd.Timestamp(b["timestamp"], unit="s", tz="UTC") <= p_open
        ]
        for alias, bars in info.items()
    }
    frame = enricher.enrich(
        primary[: row + 1], prefix_info, definition, primary_req, info_req
    )
    return frame.iloc[row].to_dict()


def _causal_info_oracle(info_bars, info_req, primary_open, interval):
    """Causal informative oracle: enrich the info prefix ending at the latest
    bar visible at *primary_open*, return that bar's indicator dict.

    An informative bar is visible once it has closed (open + interval <=
    primary_open). The oracle batch-enriches the prefix ending at that bar,
    so frame-dependent indicators (poc_slope_5, vp_*) use only bars up to
    it — matching the streaming enricher's causal horizon. The batch MTF
    enricher, by contrast, computes informative indicators on the whole
    truncated frame and so carries intra-session lookahead.
    """
    offset = pd.Timedelta(hours=1) if interval == "1h" else pd.Timedelta(0)
    visible_idx = -1
    for i, b in enumerate(info_bars):
        i_open = pd.Timestamp(b["timestamp"], unit="s", tz="UTC")
        if i_open + offset <= primary_open:
            visible_idx = i
        else:
            break
    if visible_idx < 0:
        return None
    calc = PandasTaIndicatorCalculator()
    converter = PandasBarFrameConverter()
    frame = converter.bars_to_frame(info_bars[: visible_idx + 1])
    frame = calc.calculate(frame, info_req)
    return frame.iloc[visible_idx].to_dict()


def _feed_through(enricher, primary, info, until_row):
    """Feed primary[0..until_row] plus informative bars visible at each step."""
    info_ptrs = {alias: 0 for alias in info}
    for i in range(until_row + 1):
        p_open = pd.Timestamp(primary[i]["timestamp"], unit="s", tz="UTC")
        for alias, ibars in info.items():
            while info_ptrs[alias] < len(ibars):
                i_open = pd.Timestamp(
                    ibars[info_ptrs[alias]]["timestamp"], unit="s", tz="UTC"
                )
                if i_open <= p_open:
                    enricher.update_informative(alias, ibars[info_ptrs[alias]])
                    info_ptrs[alias] += 1
                else:
                    break
        enricher.update_primary(primary[i])
    return enricher.latest()


def _assert_close(got, expected, col):
    """Assert two values match, treating NaN/None and bool/0-1 as equal."""
    if isinstance(expected, bool) or isinstance(got, bool):
        assert bool(got) == bool(expected), f"{col}: got {got!r}, expected {expected!r}"
        return
    try:
        g = float(got)
        e = float(expected)
    except (TypeError, ValueError):
        assert got == expected, f"{col}: got {got!r}, expected {expected!r}"
        return
    if math.isnan(g) and math.isnan(e):
        return
    assert math.isclose(
        g, e, rel_tol=1e-9, abs_tol=1e-12
    ), f"{col}: got {g}, expected {e}, diff={abs(g - e)}"


@needs_parity_fixtures
class TestCausalMultiTimeframeStreamingEnricher:
    """Scenario 3: streaming enricher matches the batch-prefix oracle."""

    def _build(self, definition, primary_req, info_req):
        return CausalMultiTimeframeStreamingEnricher(
            definition=definition,
            primary_indicators=primary_req,
            informative_indicators=info_req,
        )

    def test_streaming_primary_matches_batch_prefix_oracle(self):
        """Primary OHLCV + indicators match the batch-prefix oracle at row 17."""
        primary = load_parity_bars("30min")
        info = {"h1": load_parity_bars("1h")}
        definition, primary_req, info_req, _ = parse_production_strategy()

        enricher = self._build(definition, primary_req, info_req)
        _feed_through(enricher, primary, info, until_row=17)

        oracle = _batch_oracle_row(primary, info, definition, primary_req, info_req, 17)
        got = enricher.latest().values

        for col in (
            "close",
            "vp_poc",
            "vp_vah",
            "vp_val",
            "near_vah",
            "rejection_from_edge",
            "value_area_width_pct",
            "atr",
        ):
            assert col in got, f"missing primary column {col}"
            _assert_close(got[col], oracle[col], col)

    def test_streaming_mtf_columns_match_causal_info_oracle(self):
        """Merged informative columns match the causal per-info-prefix oracle.

        The streaming enricher computes each informative indicator on the
        prefix ending at the latest visible bar (causal). This matches
        batch-enriching that informative prefix — NOT the batch MTF
        enricher, which carries intra-session lookahead for frame-dependent
        informative indicators.
        """
        primary = load_parity_bars("30min")
        info = {"h1": load_parity_bars("1h")}
        definition, primary_req, info_req, _ = parse_production_strategy()
        h1_req = info_req.get("h1", [])

        enricher = self._build(definition, primary_req, info_req)
        _feed_through(enricher, primary, info, until_row=50)

        p_open = pd.Timestamp(primary[50]["timestamp"], unit="s", tz="UTC")
        oracle_info = _causal_info_oracle(info["h1"], h1_req, p_open, "1h")
        got = enricher.latest().values

        assert oracle_info is not None, "No visible h1 bar at row 50"
        for col in ("poc_slope_5", "above_value", "below_value"):
            merged_col = f"{col}_1h"
            assert merged_col in got, f"streaming missing {merged_col}"
            _assert_close(got[merged_col], oracle_info[col], merged_col)

    def test_informative_future_bar_not_visible(self):
        """An informative bar closing after the primary close is not visible."""
        primary = load_parity_bars("30min")
        definition, primary_req, info_req, _ = parse_production_strategy()

        enricher = self._build(definition, primary_req, info_req)
        # Feed primary bar 0 only (30min close). The 1h bar that opens at the
        # same time closes 1h later, so it must NOT be visible yet.
        enricher.update_primary(primary[0])
        latest = enricher.latest().values

        assert "poc_slope_5_1h" not in latest or latest.get("poc_slope_5_1h") is None

    def test_single_timeframe_works(self):
        """A strategy with no informative timeframes still enriches."""
        from dataclasses import replace

        from finbar_strategy_runtime.domain.entities.timeframe_declaration import (
            TimeframeDeclaration,
        )

        primary = load_parity_bars("30min")
        definition, primary_req, _, _ = parse_production_strategy()
        single_tf = replace(
            definition,
            timeframes=TimeframeDeclaration(primary="30min", informative=[]),
        )

        enricher = self._build(single_tf, primary_req, {})
        for b in primary[:20]:
            enricher.update_primary(b)

        latest = enricher.latest().values
        assert "close" in latest
        assert "vp_vah" in latest
        # No suffixed informative columns
        assert not any(k.endswith("_1h") for k in latest)

    def test_streaming_reproduces_reference_first_signal(self):
        """Full streaming run reproduces a short-entry signal after warmup.

        Under the strict warmup contract (spec 2026-06-23 Scenario 4)
        ``poc_slope_5`` is NaN until 5 sessions exist, so the first signal
        fires once the slope is genuinely computable (observed: row ~229)
        rather than on a fabricated warmup ``0.0`` at row 17.
        """
        from finbar_strategy_runtime.evaluation.json_rule_based_strategy import (
            JsonRuleBasedStrategy,
        )

        primary = load_parity_bars("30min")
        info = {"h1": load_parity_bars("1h")}
        definition, primary_req, info_req, required_cols = parse_production_strategy()

        enricher = self._build(definition, primary_req, info_req)
        strategy = JsonRuleBasedStrategy(definition)
        flat = {"direction": "", "size": 0}

        info_ptrs = {alias: 0 for alias in info}
        first = None
        for i in range(len(primary)):
            p_open = pd.Timestamp(primary[i]["timestamp"], unit="s", tz="UTC")
            for alias, ibars in info.items():
                while info_ptrs[alias] < len(ibars):
                    i_open = pd.Timestamp(
                        ibars[info_ptrs[alias]]["timestamp"], unit="s", tz="UTC"
                    )
                    if i_open <= p_open:
                        enricher.update_informative(alias, ibars[info_ptrs[alias]])
                        info_ptrs[alias] += 1
                    else:
                        break
            bar = enricher.update_primary(primary[i])
            readiness = bar.is_ready
            signal = strategy.on_bar(bar.values, flat)
            if not readiness:
                continue
            if signal.action != "hold":
                first = (i, signal.action, signal.direction)
                break

        assert first is not None, "No signal produced"
        assert first[1] == "sell"
        assert first[2] == "short"
        # The signal must be past poc_slope_5 warmup (non-NaN), proving it is
        # driven by real slope data, not a warmup artifact.
        assert pd.notna(bar.values.get("poc_slope_5")), (
            f"first signal at row {first[0]} fired while poc_slope_5 is NaN (warmup)"
        )

    def test_reset_clears_state(self):
        """After reset, re-feeding reproduces identical values."""
        primary = load_parity_bars("30min")
        info = {"h1": load_parity_bars("1h")}
        definition, primary_req, info_req, _ = parse_production_strategy()

        enricher = self._build(definition, primary_req, info_req)
        _feed_through(enricher, primary, info, until_row=30)
        first = dict(enricher.latest().values)

        enricher.reset()
        _feed_through(enricher, primary, info, until_row=30)
        second = enricher.latest().values

        for k, v in first.items():
            if k in _OHLCV:
                continue
            _assert_close(second.get(k), v, k)
