"""Contract tests for warmup-sensitive metric causal prefix parity.

Scenario 8 from all-metrics causal streaming parity: recursive/proxy metrics
must use enough causal history to match the prefix oracle within tolerance.
"""

from __future__ import annotations

import pytest

from tests.contract.conftest import load_parity_bars, needs_parity_fixtures
from tests.support.causal_metric_oracle import assert_metric_matches_prefix_oracle


@needs_parity_fixtures
class TestWarmupSensitiveCausalPrefixParity:
    """Black-box parity tests for warmup-sensitive proxy metrics."""

    @pytest.mark.parametrize(
        "metric",
        [
            "alligator_jaw",
            "alligator_teeth",
            "alligator_lips",
            "proxy_atr",
            "proxy_iv",
            "proxy_expected_move",
            "parametric_u_shape",
        ],
    )
    def test_warmup_sensitive_metric_matches_prefix_oracle(self, metric):
        """Streaming warmup-sensitive metric equals batch-on-prefix values."""
        bars = load_parity_bars("30min")

        assert_metric_matches_prefix_oracle(
            metric,
            bars,
            sample_indices=[100, 300, 499],
            rel_tol=1e-7,
            abs_tol=1e-9,
        )
