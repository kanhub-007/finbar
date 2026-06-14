"""Contract tests for UnifiedMetricCatalog — Scenario 1.1 + 1.3.

Verifies the unified catalog serves both parser validation
(IndicatorCapabilityProvider) and capability checks (MarketMetricCatalog).
"""

import pytest

from finbar_strategy_runtime.domain.entities.metric_confidence import (
    MetricConfidence,
)
from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily
from finbar_strategy_runtime.domain.interfaces.indicator_capability_provider import (
    IndicatorCapabilityProvider,
)
from finbar_strategy_runtime.domain.interfaces.market_metric_catalog import (
    MarketMetricCatalog,
)


@pytest.fixture
def catalog():
    """Build a UnifiedMetricCatalog.

    The catalog auto-imports the indicator calculator on construction,
    so all @_register handlers are populated automatically.
    """
    from finbar_strategy_runtime.parser.unified_metric_catalog import (
        UnifiedMetricCatalog,
    )

    return UnifiedMetricCatalog()


# ---------------------------------------------------------------------------
# Scenario 1.1: Unified catalog serves both parser validation and capability
# ---------------------------------------------------------------------------


class TestUnifiedCatalogDualRole:
    """The catalog must implement both interfaces and answer consistently."""

    def test_implements_both_interfaces(self, catalog):
        """UnifiedMetricCatalog is both an IndicatorCapabilityProvider
        and a MarketMetricCatalog."""
        assert isinstance(catalog, IndicatorCapabilityProvider)
        assert isinstance(catalog, MarketMetricCatalog)

    def test_parser_indicator_supported_and_computable(self, catalog):
        """An existing parser indicator (vwap) is supported + computable."""
        assert catalog.supports_concrete("vwap") is True

        result = catalog.check("vwap", "daily_ohlcv")
        assert result.supported is True
        assert result.computable is True

    def test_old_period_based_name_still_works(self, catalog):
        """sma_20 (period-based) is still recognised by the parser side."""
        assert catalog.supports_concrete("sma_20") is True

    def test_new_metric_supported_and_computable(self, catalog):
        """A catalogued OHLCV metric with a registered handler is computable."""
        assert catalog.supports_concrete("corwin_schultz_spread") is True

        result = catalog.check("corwin_schultz_spread", "daily_ohlcv")
        assert result.supported is True
        assert result.computable is True
        assert result.confidence == MetricConfidence.PROXY

    def test_unknown_name_not_supported(self, catalog):
        """An unknown metric name is not supported."""
        assert catalog.supports_concrete("nonexistent_metric") is False

        result = catalog.check("nonexistent_metric", "daily_ohlcv")
        assert result.supported is False
        assert result.computable is False

    def test_implemented_false_metric_not_computable(self, catalog):
        """A metric with implemented=False (e.g. Elliott Wave) is not computable."""
        assert catalog.supports_concrete("elliott_wave_count") is True

        result = catalog.check("elliott_wave_count", "daily_ohlcv")
        assert result.supported is True
        assert result.computable is False
        assert result.confidence == MetricConfidence.UNAVAILABLE

    def test_check_returns_confidence_for_computable(self, catalog):
        """A computable parser indicator returns a confidence level."""
        result = catalog.check("vwap", "daily_ohlcv")
        assert result.confidence is not None

    def test_proxy_indicator_reports_proxy_confidence(self, catalog):
        """A proxy_-prefixed indicator reports PROXY confidence, not ACTUAL."""
        result = catalog.check("proxy_atr", "daily_ohlcv")
        assert result.supported is True
        assert result.computable is True
        assert result.confidence == MetricConfidence.PROXY

    def test_get_returns_definition(self, catalog):
        """get() returns the MarketMetricDefinition for a catalogued name."""
        definition = catalog.get("corwin_schultz_spread")
        assert definition is not None
        assert definition.name == "corwin_schultz_spread"
        assert definition.family == MetricFamily.SPREAD

    def test_get_returns_none_for_unknown(self, catalog):
        """get() returns None for an unknown name."""
        assert catalog.get("nonexistent") is None

    def test_list_returns_all_metrics(self, catalog):
        """list() returns a non-empty sequence of definitions."""
        items = catalog.list()
        assert len(items) > 50  # we have ~110 entries

    def test_list_filtered_by_family(self, catalog):
        """list(family=...) filters by MetricFamily."""
        items = catalog.list(family=MetricFamily.SPREAD)
        assert len(items) > 0
        assert all(m.family == MetricFamily.SPREAD for m in items)

    def test_resolve_best_for_volatility_concept(self, catalog):
        """resolve_best('volatility', ...) selects yang_zhang_vol for daily."""
        result = catalog.resolve_best("volatility", "daily_ohlcv", interval="1d")
        assert result.supported is True
        assert result.computable is True
        assert result.selected_metric == "yang_zhang_vol"
        assert result.confidence == MetricConfidence.PROXY

    def test_supported_concrete_names_includes_old_indicators(self, catalog):
        """supported_concrete_names() includes existing parser indicators."""
        names = catalog.supported_concrete_names()
        assert "vwap" in names
        assert "atr" in names


# ---------------------------------------------------------------------------
# Scenario 1.3: Handler registration enforces name-sync invariant
# ---------------------------------------------------------------------------


class TestNameSyncInvariant:
    """Every handler name must be catalogued; catalogued names without
    handlers must report computable=False."""

    def test_every_handler_accepted_by_parser(self, catalog):
        """Every registered handler name must be accepted by supports_concrete().

        This is the name-sync invariant: if a handler exists for a name,
        the parser must accept that name. Otherwise the handler computes
        a column the parser would reject as unknown_operand.
        """
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            _INDICATOR_HANDLERS,
        )

        handler_names = set(_INDICATOR_HANDLERS.keys())
        unaccepted = {
            name for name in handler_names if not catalog.supports_concrete(name)
        }
        assert unaccepted == set(), (
            f"Handlers not accepted by parser: {unaccepted}"
        )

    def test_catalogued_without_handler_not_computable(self, catalog):
        """Catalogued names that lack a handler report computable=False."""
        from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
            _INDICATOR_HANDLERS,
        )

        catalog_names = catalog.all_metric_names()
        handler_names = set(_INDICATOR_HANDLERS.keys())

        for name in catalog_names - handler_names:
            result = catalog.check(name, "daily_ohlcv")
            assert result.computable is False or not result.supported, (
                f"'{name}' has no handler but check() returned computable=True"
            )
