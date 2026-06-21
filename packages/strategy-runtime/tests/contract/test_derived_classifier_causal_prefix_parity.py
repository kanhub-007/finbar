"""Contract tests for derived classifier causal prefix parity.

Scenario 9 from all-metrics causal streaming parity: derived classifiers must
match the prefix oracle as logical strings/bools, without misleading float
coercion or default values while dependencies warm up.
"""

from __future__ import annotations

import pytest

from tests.contract.conftest import load_parity_bars, needs_parity_fixtures
from tests.support.causal_metric_oracle import assert_metric_matches_prefix_oracle


@needs_parity_fixtures
class TestDerivedClassifierCausalPrefixParity:
    """Black-box parity tests for profile-shape derived classifiers."""

    @pytest.mark.parametrize(
        "metric",
        ["profile_shape", "is_b_shape", "is_neutral_shape"],
    )
    def test_derived_classifier_matches_prefix_oracle(self, metric):
        """Streaming classifier equals batch-on-prefix values and type semantics."""
        bars = load_parity_bars("30min")

        assert_metric_matches_prefix_oracle(
            metric,
            bars,
            sample_indices=[120, 300, 499],
            rel_tol=1e-7,
            abs_tol=1e-9,
        )
