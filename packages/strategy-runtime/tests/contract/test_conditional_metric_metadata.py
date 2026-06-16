"""Conditional-metric metadata tests — spec 2026-06-16 Scenario 3.

The catalog must surface the real constraints of conditional metrics
(minimum bar counts, intraday-only data classes, condition notes) so
users don't request metrics that silently fail. Also enforces Invariant
#5: check_metric must not claim a metric is computable on a data class
that cannot support it (e.g. ``ib_high`` on daily OHLCV).

Classical school: real ``UnifiedMetricCatalog``, assert on outcomes.
"""

import pytest

from finbar_strategy_runtime.domain.entities.data_class import DataClass
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog


@pytest.fixture
def catalog() -> UnifiedMetricCatalog:
    return UnifiedMetricCatalog()


class TestMinLookbackMatchesHandlerRequirement:
    """min_lookback must reflect the handler's true minimum bar count."""

    def test_hurst_exponent_requires_100_bars(self, catalog):
        d = catalog.get("hurst_exponent")
        assert d is not None
        assert d.min_lookback >= 100
        assert "100" in d.description or "100" in (d.condition_note or "")

    def test_market_regime_requires_220_bars(self, catalog):
        d = catalog.get("market_regime")
        assert d is not None
        assert d.min_lookback >= 220
        assert "220" in d.description or "220" in (d.condition_note or "")

    def test_effective_tick_spread_lookback_60(self, catalog):
        d = catalog.get("effective_tick_spread")
        assert d is not None
        assert d.min_lookback >= 60

    def test_lot_zero_return_spread_lookback_60(self, catalog):
        d = catalog.get("lot_zero_return_spread")
        assert d is not None
        assert d.min_lookback >= 60


class TestIntradayOnlyMetrics:
    """ib_* and vwap_session must be intraday-only and check_metric honest."""

    @pytest.mark.parametrize(
        "name",
        ["ib_high", "ib_low", "ib_midpoint", "ib_range", "vwap_session"],
    )
    def test_metric_is_in_catalog(self, catalog, name):
        """Intraday-only metrics must be discoverable in the catalog."""
        assert catalog.get(name) is not None, f"{name} missing from catalog"

    @pytest.mark.parametrize(
        "name",
        ["ib_high", "ib_low", "ib_midpoint", "ib_range", "vwap_session"],
    )
    def test_check_metric_reports_uncomputable_on_daily(self, catalog, name):
        """Invariant #5: ib_*/vwap_session on daily → computable=False."""
        result = catalog.check(name, "daily_ohlcv")
        assert result.computable is False, (
            f"{name} must not be computable from daily OHLCV (intraday only)"
        )

    @pytest.mark.parametrize(
        "name",
        ["ib_high", "ib_low", "ib_midpoint", "ib_range", "vwap_session"],
    )
    def test_check_metric_computable_on_intraday(self, catalog, name):
        """On intraday data the metric IS computable (handler exists)."""
        result = catalog.check(name, "intraday_ohlcv")
        assert result.computable is True


class TestConditionNotes:
    """Conditional metrics carry a human-readable condition_note."""

    @pytest.mark.parametrize(
        "name, fragment",
        [
            ("trend_phase", "unknown"),
            ("williams_fractal_high", "null"),
            ("williams_fractal_low", "null"),
        ],
    )
    def test_condition_note_describes_constraint(self, catalog, name, fragment):
        d = catalog.get(name)
        assert d is not None
        note = (d.condition_note or "").lower()
        desc = (d.description or "").lower()
        assert fragment in note or fragment in desc, (
            f"{name} should mention '{fragment}' in condition_note/description"
        )
