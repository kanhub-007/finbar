"""check_metric dependency-warning tests — spec 2026-06-16 Scenario 5.

A metric whose handler ``requires`` columns beyond OHLCV (e.g. ``atr``,
``vp_poc``, ``rvol``) silently produces NaN if those dependencies are
not computed in the same batch. ``check_metric`` must warn about these
non-OHLCV dependencies so users know to co-request them.

Covers the reclassified Scenario 9 root cause (poc_rejection /
edge_volume_building dependency gap) plus vol_buffer_high and friends.

Classical school: real ``UnifiedMetricCatalog``, assert on warnings.
"""

import pytest

from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog


@pytest.fixture
def catalog() -> UnifiedMetricCatalog:
    return UnifiedMetricCatalog()


class TestCheckMetricWarnsOnNonOhlcvRequires:
    """check_metric surfaces non-OHLCV handler dependencies as warnings."""

    def test_vol_buffer_high_warns_about_atr(self, catalog):
        result = catalog.check("vol_buffer_high", "daily_ohlcv")
        assert any("atr" in w for w in result.warnings), result.warnings

    def test_poc_rejection_warns_about_vp_poc_and_atr(self, catalog):
        result = catalog.check("poc_rejection", "daily_ohlcv")
        text = " ".join(result.warnings)
        assert "vp_poc" in text
        assert "atr" in text

    def test_edge_volume_building_warns_about_rvol(self, catalog):
        result = catalog.check("edge_volume_building", "daily_ohlcv")
        text = " ".join(result.warnings)
        assert "rvol" in text

    def test_proxy_ib_high_no_longer_warns_about_atr(self, catalog):
        """proxy_ib_high derives ATR internally via the cache helper, so it
        no longer declares requires={"atr"} and produces no dep warning."""
        result = catalog.check("proxy_ib_high", "daily_ohlcv")
        # Should NOT warn about atr — the handler is self-contained.
        assert not any("atr" in w for w in result.warnings), (
            "proxy_ib_high should not warn about atr: it derives ATR internally"
        )

    def test_pure_ohlcv_metric_has_no_dependency_warning(self, catalog):
        """A metric requiring only OHLCV columns gets no dep warning."""
        result = catalog.check("fong_holden_tran_spread", "daily_ohlcv")
        # fong_holden_tran requires open/high/low/close — all OHLCV.
        assert not any("requires" in w.lower() and "column" in w.lower()
                       for w in result.warnings)
