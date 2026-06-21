"""Contract tests for rolling-window VP causal prefix parity.

Scenario 4 from all-metrics causal streaming parity: `rvp_poc_N`, `rvp_vah_N`,
and `rvp_val_N` must stream one bar at a time and match the causal prefix
oracle for the same rolling window definition.
"""

from __future__ import annotations

import pytest

from tests.contract.conftest import load_parity_bars, needs_parity_fixtures
from tests.support.causal_metric_oracle import assert_metric_matches_prefix_oracle


@needs_parity_fixtures
class TestRollingVolumeProfileCausalPrefixParity:
    """Black-box parity tests for RVP streaming values."""

    @pytest.mark.parametrize(
        ("metric", "sample_indices"),
        [
            ("rvp_poc_48", [48, 96, 240]),
            ("rvp_vah_96", [96, 240, 360]),
            ("rvp_val_336", [336, 420, 499]),
        ],
    )
    def test_rvp_metric_matches_prefix_oracle(self, metric, sample_indices):
        """Streaming RVP equals batch-on-prefix at sampled rows."""
        bars = load_parity_bars("30min")

        assert_metric_matches_prefix_oracle(
            metric,
            bars,
            sample_indices=sample_indices,
            rel_tol=1e-7,
            abs_tol=1e-9,
        )
