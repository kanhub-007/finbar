"""Full-catalog causal streaming coverage sweep.

Scenario 10 from all-metrics causal streaming parity: after fixing the metric
families, the package coverage matrix must report every catalog metric as
streaming-correct, with no unsupported, silent-wrong, or loud-NaN entries.
"""

from __future__ import annotations

from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog
from tests.support.causal_streaming_sweep import run_causal_streaming_sweep


class TestFullCatalogCausalStreamingSweep:
    """Black-box regression guard for the all-metrics coverage matrix."""

    def test_full_catalog_coverage_matrix_is_green(self):
        """Every catalog metric is now classified as streaming-correct."""
        catalog_names = UnifiedMetricCatalog().supported_concrete_names()

        report = run_causal_streaming_sweep(catalog_names)

        assert report.unsupported == []
        assert report.silent_wrong == []
        assert report.loud_nan_mismatch == []
