"""Contract tests for the package streaming coverage matrix.

Scenario 1 from all-metrics causal streaming parity: every strategy-accepted
metric must be classified by a package-owned coverage matrix, and unknown names
must fail closed with a clear error.
"""

import pytest

from finbar_strategy_runtime.parser.unified_metric_catalog import UnifiedMetricCatalog


class TestStreamingCoverageMatrix:
    """Black-box tests for catalog-wide streaming coverage classification."""

    def test_default_matrix_classifies_every_catalog_metric(self):
        """The default coverage matrix has exactly one entry per catalog metric."""
        from finbar_strategy_runtime.parser.streaming_coverage_loader import (
            load_default_streaming_coverage_matrix,
        )

        catalog_names = UnifiedMetricCatalog().supported_concrete_names()
        matrix = load_default_streaming_coverage_matrix()

        assert set(matrix.names()) == set(catalog_names)
        for name in catalog_names:
            entry = matrix.entry_for(name)
            assert entry.label in {"STREAMING_CORRECT", "STREAMING_UNSUPPORTED"}
            if entry.label == "STREAMING_UNSUPPORTED":
                assert entry.reason

    def test_entry_lookup_accepts_metric_name_case_used_by_parser(self):
        """Mixed-case accepted metric names resolve to their catalog entry."""
        from finbar_strategy_runtime.parser.streaming_coverage_loader import (
            load_default_streaming_coverage_matrix,
        )

        matrix = load_default_streaming_coverage_matrix()

        assert matrix.entry_for("ABOVE_VALUE").metric_name == "above_value"

    def test_unknown_metric_raises_clear_error(self):
        """A metric name outside the catalog raises a clear UnknownMetricError."""
        from finbar_strategy_runtime.domain.services.streaming_coverage import (
            UnknownMetricError,
        )
        from finbar_strategy_runtime.parser.streaming_coverage_loader import (
            load_default_streaming_coverage_matrix,
        )

        matrix = load_default_streaming_coverage_matrix()

        with pytest.raises(UnknownMetricError, match="not_a_metric"):
            matrix.entry_for("not_a_metric")
