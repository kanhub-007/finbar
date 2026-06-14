"""Contract tests for StaticMarketMetricCatalog — capability checks.

Only tests metrics that have data sources we can support.
Removed metrics (TAQ, L2, order events, external sentiment, Elliott Wave)
are no longer catalogued — see _metric_registry.py.
"""

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


class TestCatalogCapabilityChecks:
    """Verify the catalog correctly reports metric capabilities."""

    def test_ohclv_proxy_returns_computable(self, catalog):
        """corwin_schultz_spread with daily_ohlcv → computable, confidence=proxy."""
        result = catalog.check("corwin_schultz_spread", "daily_ohlcv")
        assert result.supported is True
        assert result.computable is True
        assert result.confidence == MetricConfidence.PROXY

    def test_unknown_metric_reports_not_supported(self, catalog):
        """Unknown metric name → supported=False with clear diagnostic."""
        result = catalog.check("nonexistent_metric_xyz", "daily_ohlcv")
        assert result.supported is False
        assert result.computable is False
        assert result.confidence == MetricConfidence.UNAVAILABLE
        assert any("unknown" in w.lower() for w in result.warnings)

    def test_amihud_illiq_computable_from_daily(self, catalog):
        """amihud_illiq is computable from daily_ohlcv."""
        result = catalog.check("amihud_illiq", "daily_ohlcv")
        assert result.supported is True
        assert result.computable is True
        assert result.confidence == MetricConfidence.PROXY

    def test_intraday_metric_computable(self, catalog):
        """realized_vol_5m is now implemented and computable on intraday."""
        d = catalog.get("realized_vol_5m")
        assert d is not None
        assert d.implemented is True
        result = catalog.check("realized_vol_5m", "intraday_ohlcv")
        assert result.supported is True
        assert result.computable is True

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
        assert len(all_metrics) >= 50, f"Expected ≥50 metrics, got {len(all_metrics)}"
        assert "corwin_schultz_spread" in names
        assert "amihud_illiq" in names
        assert "yang_zhang_vol" in names
        assert "funding_rate" in names

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


class TestDualPathResolution:
    """resolve_best() auto-selects highest-confidence path for available data."""

    def test_volatility_intraday_selects_actual(self, catalog):
        """With intraday 5-min data → realized_vol_5m (actual)."""
        result = catalog.resolve_best("volatility", "intraday_ohlcv", interval="5min")
        assert result.computable is True
        assert result.selected_metric == "realized_vol_5m"
        assert result.confidence.value == "actual"

    def test_volatility_1h_selects_approximation(self, catalog):
        """With intraday 1h data → realized_vol_1h (approximation)."""
        result = catalog.resolve_best("volatility", "intraday_ohlcv", interval="1h")
        assert result.computable is True
        assert result.selected_metric == "realized_vol_1h"
        assert result.confidence.value == "approximation"

    def test_volatility_daily_selects_proxy(self, catalog):
        """With daily data only → yang_zhang_vol (proxy)."""
        result = catalog.resolve_best("volatility", "daily_ohlcv", interval="1d")
        assert result.computable is True
        assert result.selected_metric == "yang_zhang_vol"
        assert result.confidence.value == "proxy"

    def test_force_proxy_overrides(self, catalog):
        """force_proxy=True skips actual paths even when data is available."""
        result = catalog.resolve_best(
            "volatility", "intraday_ohlcv", interval="5min", force_proxy=True
        )
        assert result.computable is True
        assert result.selected_metric == "yang_zhang_vol"
        assert result.confidence.value == "proxy"

    def test_unknown_concept_returns_unsupported(self, catalog):
        """Unknown conceptual metric returns supported=False."""
        result = catalog.resolve_best("nonexistent_concept", "daily_ohlcv")
        assert result.supported is False

    def test_multiple_paths_in_available_paths(self, catalog):
        """available_paths lists all resolution paths for the concept."""
        result = catalog.resolve_best("volatility", "daily_ohlcv")
        assert len(result.available_paths) >= 2
        path_names = [p.metric_name for p in result.available_paths]
        assert "yang_zhang_vol" in path_names


class TestDerivativesMetricsCatalogued:
    """Derivatives metrics are catalogued with provider requirements."""

    @pytest.mark.parametrize(
        "metric_name",
        [
            "funding_rate",
            "open_interest",
            "open_interest_delta_1h",
            "open_interest_delta_24h",
            "cumulative_volume_delta",
            "long_short_ratio",
            "liquidations_long_1h",
            "liquidations_short_1h",
            "liquidations_long_24h",
            "liquidations_short_24h",
            "funding_rate_annualised",
        ],
    )
    def test_derivatives_present(self, catalog, metric_name):
        """Every derivatives metric is in the catalog."""
        result = catalog.check(metric_name, "daily_ohlcv")
        assert result.supported is True, f"{metric_name} not found!"

    def test_funding_rate_requires_coinglass(self, catalog):
        """funding_rate reports missing providers without CoinGlass."""
        result = catalog.check("funding_rate", "daily_ohlcv")
        assert result.computable is False
        assert any("coinglass" in p.lower() for p in result.missing_providers)
