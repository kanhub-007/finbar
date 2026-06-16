"""Data-source-limited metric tests — spec 2026-06-16 Scenario 2.

``first_last_hour_vol_fraction`` originally required ``opening_volume`` /
``closing_volume`` columns that no OHLCV data source provides. Scenario 2
marked it unavailable; Scenario 12 (Slice 3) then added an intraday
UTC-day-grouping proxy. This test pins the FINAL state: the metric is
uncomputable on daily OHLCV (cannot subdivide a daily bar into
first/last hour) but computable on intraday via the proxy.

Classical school: real ``UnifiedMetricCatalog``, assert on outcomes.
"""

from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog


class TestFirstLastHourVolFractionAvailability:
    """Final state after Scenario 2 (mark unavailable) + Scenario 12 (proxy)."""

    def test_uncomputable_on_daily(self):
        """Daily bars cannot be subdivided into first/last hour."""
        catalog = UnifiedMetricCatalog()
        result = catalog.check("first_last_hour_vol_fraction", "daily_ohlcv")
        assert result.computable is False

    def test_computable_on_intraday_via_proxy(self):
        """On intraday data the proxy makes it computable."""
        catalog = UnifiedMetricCatalog()
        result = catalog.check("first_last_hour_vol_fraction", "intraday_ohlcv")
        assert result.computable is True

    def test_condition_note_documents_intraday_only(self):
        catalog = UnifiedMetricCatalog()
        d = catalog.get("first_last_hour_vol_fraction")
        assert d is not None
        assert "intraday" in d.condition_note.lower()
        # No longer claims it needs opening_volume/closing_volume.
        assert "opening_volume" not in d.condition_note.lower()
