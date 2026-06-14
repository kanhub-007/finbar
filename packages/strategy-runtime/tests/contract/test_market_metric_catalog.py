"""Contract tests for MarketMetricCatalog — Scenario 1: capability checks."""

import json

import pytest

from finbar_strategy_runtime.domain.entities.metric_confidence import MetricConfidence
from finbar_strategy_runtime.domain.interfaces.market_metric_catalog import (
    MarketMetricCatalog,
)
from finbar_strategy_runtime.domain.services.static_market_metric_catalog import (
    StaticMarketMetricCatalog,
)


@pytest.fixture
def catalog() -> MarketMetricCatalog:
    return StaticMarketMetricCatalog()


# ---------------------------------------------------------------------------
# Scenario 1: Metric catalog reports support and required data class
# ---------------------------------------------------------------------------


class TestCatalogCapabilityChecks:
    """Verify the catalog correctly reports metric capabilities."""

    def test_ohclv_proxy_returns_computable(self, catalog):
        """corwin_schultz_spread with daily_ohlcv → computable, confidence=proxy."""
        result = catalog.check("corwin_schultz_spread", "daily_ohlcv")

        assert result.supported is True
        assert result.computable is True
        assert result.confidence == MetricConfidence.PROXY

    def test_l2_metric_reports_unavailable_with_proxy(self, catalog):
        """order_book_depth_profile with daily_ohlcv → not computable, L2 missing."""
        result = catalog.check("order_book_depth_profile", "daily_ohlcv")

        assert result.supported is True
        assert result.computable is False
        assert result.confidence == MetricConfidence.UNAVAILABLE
        assert "level_2_order_book" in result.missing_data_classes
        assert "amihud_illiq" in result.proxy_candidates

    def test_unknown_metric_reports_not_supported(self, catalog):
        """Unknown metric name → supported=False with clear diagnostic."""
        result = catalog.check("nonexistent_metric_xyz", "daily_ohlcv")

        assert result.supported is False
        assert result.computable is False
        assert result.confidence == MetricConfidence.UNAVAILABLE
        assert any("unknown" in w.lower() for w in result.warnings)

    def test_effective_spread_taq_requires_trades_and_quotes(self, catalog):
        """effective_spread_taq needs trades_and_quotes, not daily_ohlcv."""
        result = catalog.check("effective_spread_taq", "daily_ohlcv")

        assert result.supported is True
        assert result.computable is False
        assert "trades_and_quotes" in result.missing_data_classes
        assert "corwin_schultz_spread" in result.proxy_candidates

    def test_cont_kukanov_ofi_requires_l2(self, catalog):
        """cont_kukanov_ofi needs level_2_order_book."""
        result = catalog.check("cont_kukanov_ofi", "daily_ohlcv")

        assert result.computable is False
        assert "level_2_order_book" in result.missing_data_classes
        assert len(result.proxy_candidates) > 0

    def test_hasbrouck_information_share_requires_trades(self, catalog):
        """hasbrouck_information_share needs multi-venue tick data."""
        result = catalog.check("hasbrouck_information_share", "daily_ohlcv")

        assert result.computable is False
        assert len(result.proxy_candidates) > 0

    def test_amihud_illiq_computable_from_daily(self, catalog):
        """amihud_illiq is computable from daily_ohlcv."""
        result = catalog.check("amihud_illiq", "daily_ohlcv")

        assert result.supported is True
        assert result.computable is True
        assert result.confidence == MetricConfidence.PROXY

    def test_result_is_json_serializable(self, catalog):
        """MetricCapabilityResult can be serialized to JSON for MCP/API."""
        result = catalog.check("corwin_schultz_spread", "daily_ohlcv")
        d = {
            "metric": result.metric,
            "supported": result.supported,
            "computable": result.computable,
            "confidence": result.confidence.value,
        }
        json_str = json.dumps(d)
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["confidence"] == "proxy"


class TestCatalogListing:
    """Verify catalog.list() returns the expected metrics."""

    def test_list_returns_all_metrics(self, catalog):
        """Every defined metric is accessible via list()."""
        all_metrics = catalog.list()
        names = {m.name for m in all_metrics}
        assert len(all_metrics) >= 20, f"Expected ≥20 metrics, got {len(all_metrics)}"
        assert "corwin_schultz_spread" in names
        assert "amihud_illiq" in names
        assert "yang_zhang_vol" in names
        assert "effective_spread_taq" in names
        assert "order_book_depth_profile" in names
        assert "cont_kukanov_ofi" in names

    def test_list_filtered_by_family(self, catalog):
        """list(family=MetricFamily.SPREAD) returns only spread metrics."""
        from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily

        spreads = catalog.list(family=MetricFamily.SPREAD)
        assert len(spreads) >= 7
        for m in spreads:
            assert m.family == MetricFamily.SPREAD

    def test_get_returns_none_for_unknown(self, catalog):
        """get() returns None for unknown metric names."""
        assert catalog.get("nonexistent") is None

    def test_get_returns_definition_for_known(self, catalog):
        """get() returns the full definition for a known metric."""
        d = catalog.get("corwin_schultz_spread")
        assert d is not None
        assert d.name == "corwin_schultz_spread"
        assert d.min_lookback == 20
        assert "open" in d.required_columns
