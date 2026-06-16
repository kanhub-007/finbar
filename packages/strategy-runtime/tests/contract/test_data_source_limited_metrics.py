"""Data-source-limited metric tests — spec 2026-06-16 Scenario 2.

Some metrics require columns that no OHLCV data source provides
(``opening_volume`` / ``closing_volume``). ``check_metric`` must report
them as not computable and name the missing columns, so users don't
request metrics that can only return NaN.

Classical school: real ``UnifiedMetricCatalog``, assert on outcomes.
"""

from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog


class TestDataSourceLimitedMetrics:
    """Scenario 2 — first_last_hour_vol_fraction needs columns no source has."""

    def test_first_last_hour_vol_fraction_uncomputable_on_daily(self):
        catalog = UnifiedMetricCatalog()
        result = catalog.check("first_last_hour_vol_fraction", "daily_ohlcv")
        assert result.computable is False

    def test_warning_names_the_missing_columns(self):
        catalog = UnifiedMetricCatalog()
        result = catalog.check("first_last_hour_vol_fraction", "daily_ohlcv")
        text = " ".join(result.warnings)
        assert "opening_volume" in text or "closing_volume" in text, result.warnings

    def test_warning_names_missing_columns_on_intraday_too(self):
        """Even intraday OHLCV lacks opening_volume/closing_volume."""
        catalog = UnifiedMetricCatalog()
        result = catalog.check("first_last_hour_vol_fraction", "intraday_ohlcv")
        assert result.computable is False
        text = " ".join(result.warnings)
        assert "opening_volume" in text or "closing_volume" in text
