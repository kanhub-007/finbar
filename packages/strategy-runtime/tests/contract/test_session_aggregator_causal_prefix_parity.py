"""Contract tests for session/daily aggregator causal prefix parity.

Scenario 6 from all-metrics causal streaming parity: session and daily
aggregators must reset/roll exactly as the batch-on-prefix oracle does.
"""

from __future__ import annotations

import pytest

from tests.contract.conftest import load_parity_bars, needs_parity_fixtures
from tests.support.causal_metric_oracle import assert_metric_matches_prefix_oracle


@needs_parity_fixtures
class TestSessionAggregatorCausalPrefixParity:
    """Black-box parity tests for session/daily aggregation metrics."""

    @pytest.mark.parametrize(
        "metric",
        [
            "vwap",
            "daily_vpin",
            "intraday_volume_curve",
            "empirical_volume_curve",
            "cumulative_signed_volume_ofi",
            "daily_return_kurtosis",
            "daily_return_skewness",
            "realized_vol_5m",
        ],
    )
    def test_session_or_daily_metric_matches_prefix_oracle(self, metric):
        """Streaming session/daily metric equals batch-on-prefix values."""
        bars = load_parity_bars("30min")

        assert_metric_matches_prefix_oracle(
            metric,
            bars,
            sample_indices=[96, 240, 499],
            rel_tol=1e-7,
            abs_tol=1e-9,
        )
