"""Spec 2026-06-23 Scenario 8 — session-count streaming windows are interval-aware.

Session-count metrics (``poc_slope_N``, ``wyckoff_phase``,
``value_area_migration``) previously used a hardcoded 500-bar window for
every interval. That is too short for ``poc_slope_20`` on 30min crypto
(20 sessions × 48 bars = 960 bars), so the metric could be silently wrong,
and wastefully long for fast intervals. The resolver computes the window
from ``lookback_sessions × bars_per_session`` for the actual interval and
market calendar.

Classical school, black-box: assert on resolver return values and on the
engine's resolved window when given interval context.
"""

from __future__ import annotations

import pytest

from finbar_strategy_runtime.domain.entities.interval_context import (
    IntervalContext,
)
from finbar_strategy_runtime.domain.services.interval_aware_window_resolver import (
    IntervalAwareWindowResolver,
)


class TestIntervalAwareWindowResolver:
    def test_poc_slope_5_30min_crypto_is_240(self):
        resolver = IntervalAwareWindowResolver(
            interval="30min", market_calendar="crypto_24_7"
        )
        assert resolver.resolve("poc_slope_5") == 240

    def test_poc_slope_20_30min_crypto_at_least_960(self):
        resolver = IntervalAwareWindowResolver(
            interval="30min", market_calendar="crypto_24_7"
        )
        assert resolver.resolve("poc_slope_20") >= 960

    def test_poc_slope_5_1h_crypto_is_120(self):
        resolver = IntervalAwareWindowResolver(
            interval="1h", market_calendar="crypto_24_7"
        )
        assert resolver.resolve("poc_slope_5") == 120

    def test_poc_slope_5_5min_crypto_uses_288_bars_per_session(self):
        resolver = IntervalAwareWindowResolver(
            interval="5min", market_calendar="crypto_24_7"
        )
        # 5 sessions × (24*60/5 = 288 bars/session) = 1440
        assert resolver.resolve("poc_slope_5") == 1440

    def test_wyckoff_phase_window_covers_slow_slope(self):
        """wyckoff_phase uses poc_slope_20, so it needs the 20-session window."""
        resolver = IntervalAwareWindowResolver(
            interval="30min", market_calendar="crypto_24_7"
        )
        assert resolver.resolve("wyckoff_phase") >= 960

    def test_value_area_migration_has_session_window(self):
        resolver = IntervalAwareWindowResolver(
            interval="30min", market_calendar="crypto_24_7"
        )
        # Needs previous-session context; at least one full session.
        assert resolver.resolve("value_area_migration") >= 48

    def test_non_session_metric_not_handled(self):
        """The resolver only owns session-count metrics; others return None."""
        resolver = IntervalAwareWindowResolver(
            interval="30min", market_calendar="crypto_24_7"
        )
        assert resolver.resolve("sma_20") is None
        assert resolver.resolve("bearish_fvg") is None

    def test_equity_regular_hours_calendar(self):
        """Equity regular hours: 30min → 13 bars/session (6.5h day)."""
        resolver = IntervalAwareWindowResolver(
            interval="30min", market_calendar="equity_regular_hours"
        )
        # 5 sessions × 13 bars = 65
        assert resolver.resolve("poc_slope_5") == 65


class TestIntervalContextBarsPerSession:
    def test_crypto_30min_is_48(self):
        ctx = IntervalContext(interval="30min", market_calendar="crypto_24_7")
        assert ctx.bars_per_session == 48

    def test_crypto_1h_is_24(self):
        ctx = IntervalContext(interval="1h", market_calendar="crypto_24_7")
        assert ctx.bars_per_session == 24

    def test_equity_30min_is_13(self):
        ctx = IntervalContext(
            interval="30min", market_calendar="equity_regular_hours"
        )
        assert ctx.bars_per_session == 13


class TestUnknownIntervalHandling:
    def test_unknown_interval_session_metric_raises(self):
        """A genuinely unknown interval must not silently use a fixed window."""
        resolver = IntervalAwareWindowResolver(
            interval="3x", market_calendar="crypto_24_7"
        )
        with pytest.raises(ValueError, match="interval"):
            resolver.resolve("poc_slope_5")

    def test_sessionless_interval_raises(self):
        """A valid interval that doesn't divide a session also fails loudly."""
        resolver = IntervalAwareWindowResolver(
            interval="3d", market_calendar="crypto_24_7"
        )
        with pytest.raises(ValueError, match="session"):
            resolver.resolve("poc_slope_5")

    def test_unknown_interval_on_engine_fails_loudly(self):
        """The streaming engine given an unknown interval raises at construction.

        The engine sizes its buffers at ``__init__``, so an unknown interval
        for a session-count metric fails immediately rather than silently
        using 500 bars.
        """
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        resolver = IntervalAwareWindowResolver(
            interval="3x", market_calendar="crypto_24_7"
        )
        with pytest.raises(ValueError, match="interval"):
            StreamingIndicatorEngine(
                indicators=["poc_slope_5"], window_resolver=resolver
            )


class TestEngineUsesIntervalAwareResolver:
    def test_engine_resolves_interval_aware_window(self):
        """When given a resolver, the engine uses it for session-count metrics."""
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        resolver = IntervalAwareWindowResolver(
            interval="30min", market_calendar="crypto_24_7"
        )
        engine = StreamingIndicatorEngine(
            indicators=["poc_slope_20"], window_resolver=resolver
        )
        assert engine._resolve_window("poc_slope_20") >= 960

    def test_engine_without_resolver_keeps_existing_behaviour(self):
        """No resolver injected → existing resolution path unchanged (compat)."""
        from finbar_strategy_runtime.indicators.streaming.streaming_indicator_engine import (
            StreamingIndicatorEngine,
        )

        engine = StreamingIndicatorEngine(indicators=["poc_slope_5"])
        # Still resolves (no crash) without an interval context.
        window = engine._resolve_window("poc_slope_5")
        assert isinstance(window, int)
        assert window > 0
