"""Integration test: IntervalAwareWindowResolver wired through the causal enricher.

When a ``market_calendar`` is passed to the enricher, session-count metrics on
both primary and informative timeframes get interval-aware streaming windows
(poc_slope_20 gets 960 bars on 30min crypto instead of 500). The enrichment
must still produce correct causal results (match the prefix oracle).

Classical school, black-box: real enricher, real bars, real strategy definition
with session-count metrics. We assert the enrichment produces non-empty results
and the internal engines use the resolver.
"""

from __future__ import annotations

import pandas as pd
import pytest

from finbar_strategy_runtime.domain.entities.informative_timeframe import (
    InformativeTimeframe,
)
from finbar_strategy_runtime.domain.entities.strategy_definition import (
    StrategyDefinition,
)
from finbar_strategy_runtime.domain.entities.timeframe_declaration import (
    TimeframeDeclaration,
)
from finbar_strategy_runtime.indicators.causal_multi_timeframe_streaming_enricher import (
    CausalMultiTimeframeStreamingEnricher,
)


def _bars(count: int, step_min: int, off: int = 0) -> list[dict]:
    base = pd.Timestamp("2026-01-05 00:00", tz="UTC")
    return [
        {
            "timestamp": int((base + pd.Timedelta(minutes=off + i * step_min)).timestamp()),
            "open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
            "close": 100.5 + i, "volume": 1000.0 + i,
        }
        for i in range(count)
    ]


@pytest.fixture
def mtf_definition() -> StrategyDefinition:
    return StrategyDefinition(
        name="mtf-session",
        schema_version="2.0",
        parameters={}, resolved_params={},
        indicators=[], features=[],
        timeframes=TimeframeDeclaration(
            primary="30min",
            informative=[InformativeTimeframe(alias="h1", interval="1h")],
        ),
        risk=None, sides=None, metadata={},
    )


class TestEnricherWithIntervalAwareResolver:
    def test_enrich_with_session_count_metrics_succeeds(self, mtf_definition):
        """Enrichment completes when market_calendar is provided."""
        primary = _bars(500, 30)
        info = {"h1": _bars(400, 60, off=15)}

        frame = CausalMultiTimeframeStreamingEnricher.causal_enrich_bars(
            primary_bars=primary,
            informative_bars=info,
            definition=mtf_definition,
            primary_indicators=["poc_slope_5", "atr"],
            informative_indicators={"h1": ["poc_slope_5"]},
            market_calendar="crypto_24_7",
        )
        assert len(frame) == len(primary)
        assert "poc_slope_5" in frame.columns
        assert "poc_slope_5_1h" in frame.columns

    def test_engine_gets_interval_aware_window(self, mtf_definition):
        """The primary engine uses the resolver for session-count metrics."""
        enricher = CausalMultiTimeframeStreamingEnricher(
            definition=mtf_definition,
            primary_indicators=["poc_slope_20"],
            informative_indicators={},
            market_calendar="crypto_24_7",
        )
        # The engine should resolve poc_slope_20 with interval-aware sizing
        # (960 bars at 30min crypto) instead of the hardcoded 500.
        window = enricher._primary_engine._resolve_window("poc_slope_20")
        assert window >= 960

    def test_informative_engine_gets_resolver(self, mtf_definition):
        """The informative engine also uses interval-aware windows."""
        enricher = CausalMultiTimeframeStreamingEnricher(
            definition=mtf_definition,
            primary_indicators=[],
            informative_indicators={"h1": ["poc_slope_5"]},
            market_calendar="crypto_24_7",
        )
        h1_engine = enricher._info_engines["h1"]
        window = h1_engine._resolve_window("poc_slope_5")
        assert window == 120  # 5 sessions × 24 bars/session

    def test_without_calendar_keeps_existing_behavior(self, mtf_definition):
        """When no market_calendar is given, session-count uses the old 500."""
        enricher = CausalMultiTimeframeStreamingEnricher(
            definition=mtf_definition,
            primary_indicators=["poc_slope_20"],
            informative_indicators={},
        )
        window = enricher._primary_engine._resolve_window("poc_slope_20")
        assert window == 500  # existing fixed window
