"""Contract tests for statistical/regime metric causal prefix parity.

Scenario 7 from all-metrics causal streaming parity: large-lookback statistical
metrics and regime classifiers must retain sufficient causal history and match
the prefix oracle, including string-valued classifiers.
"""

from __future__ import annotations

import pytest

from tests.contract.conftest import load_parity_bars, needs_parity_fixtures
from tests.support.causal_metric_oracle import assert_metric_matches_prefix_oracle


@needs_parity_fixtures
class TestStatisticalAndRegimeCausalPrefixParity:
    """Black-box parity tests for large-history metrics."""

    @pytest.mark.parametrize(
        "metric",
        [
            "hurst_exponent",
            "bipower_variation",
            "realized_kurtosis",
            "realized_skewness",
            "return_volume_correlation",
            "market_regime",
            "fractal_regime",
            "day_type_classification",
            "breakout_quality",
            "breakout_signal",
            "premium_discount_zone",
            "price_vs_sma20",
            "balance_status",
        ],
    )
    def test_stat_or_regime_metric_matches_prefix_oracle(self, metric):
        """Streaming stat/regime metric equals batch-on-prefix values."""
        bars = load_parity_bars("30min")

        assert_metric_matches_prefix_oracle(
            metric,
            bars,
            sample_indices=[300, 499],
            rel_tol=1e-7,
            abs_tol=1e-9,
        )
