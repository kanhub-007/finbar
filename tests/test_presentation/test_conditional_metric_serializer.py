"""Serializer tests for conditional-metric metadata — spec 2026-06-16 Scenario 3.

Verifies ``metric_to_dict`` (used by ``list_market_metrics``) surfaces
``min_lookback`` and ``condition_note`` so users see a metric's real
constraints, and that ``check_metric`` output reflects intraday-only
data-class restrictions.

Classical school: real ``UnifiedMetricCatalog`` + real serializer. No mocks.
"""

import pytest
from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog

from finbar.presentation.dto.metric_serializers import metric_to_dict


@pytest.fixture
def catalog() -> UnifiedMetricCatalog:
    return UnifiedMetricCatalog()


class TestMetricToDictSurfacesConstraints:
    """list_market_metrics entries expose min_lookback + condition_note."""

    def test_hurst_surfaces_min_lookback_and_note(self, catalog):
        d = metric_to_dict(catalog, catalog.get("hurst_exponent"), "daily_ohlcv")
        assert d["min_lookback"] >= 100
        assert "100" in d["condition_note"]

    def test_ib_high_intraday_only_not_computable_on_daily(self, catalog):
        d = metric_to_dict(catalog, catalog.get("ib_high"), "daily_ohlcv")
        assert d["computable"] is False
        assert "intraday" in d["condition_note"].lower()

    def test_ib_high_computable_on_intraday(self, catalog):
        d = metric_to_dict(catalog, catalog.get("ib_high"), "intraday_ohlcv")
        assert d["computable"] is True

    def test_all_entries_carry_min_lookback_and_condition_note_keys(self, catalog):
        """Every serialized entry has the two new keys (even if empty)."""
        for definition in catalog.list():
            d = metric_to_dict(catalog, definition, "daily_ohlcv")
            assert "min_lookback" in d
            assert "condition_note" in d
