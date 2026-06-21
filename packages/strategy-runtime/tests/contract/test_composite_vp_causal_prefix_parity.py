"""Contract tests for composite and multi-day VP causal prefix parity.

Scenario 5 from all-metrics causal streaming parity: `cvp_*` and `vp_*Nd`
metrics must compute dependencies causally and match the batch-on-prefix oracle.
"""

from __future__ import annotations

import pytest

from tests.contract.conftest import load_parity_bars, needs_parity_fixtures
from tests.support.causal_metric_oracle import assert_metric_matches_prefix_oracle


@needs_parity_fixtures
class TestCompositeVolumeProfileCausalPrefixParity:
    """Black-box parity tests for composite and multi-day VP metrics."""

    @pytest.mark.parametrize(
        ("metric", "sample_indices"),
        [
            ("cvp_poc_5d", [140, 260, 599]),
            ("cvp_vah_10d", [260, 420, 599]),
            ("cvp_val_20d", [500, 560, 599]),
            ("vp_poc_5d", [140, 260, 599]),
            ("vp_vah_20d", [500, 560, 599]),
            ("vp_val_5d", [140, 260, 599]),
        ],
    )
    def test_composite_or_multi_day_vp_matches_prefix_oracle(
        self,
        metric,
        sample_indices,
    ):
        """Streaming VP-derived metric equals batch-on-prefix at sampled rows."""
        bars = load_parity_bars("1h")

        assert_metric_matches_prefix_oracle(
            metric,
            bars,
            sample_indices=sample_indices,
            rel_tol=1e-7,
            abs_tol=1e-9,
        )
