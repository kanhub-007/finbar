"""Contract tests for the causal prefix oracle.

Scenario 2 from all-metrics causal streaming parity: a streaming value at row t
is correct only when it equals the batch calculator run on bars[:t+1], taking
that prefix frame's last row. Full-frame batch row t is not a live-parity oracle
for frame/session-dependent metrics.
"""

from __future__ import annotations

import math

import pytest

from finbar_strategy_runtime.indicators.pandas_bar_frame_converter import (
    PandasBarFrameConverter,
)
from finbar_strategy_runtime.indicators.pandas_ta_indicator_calculator import (
    PandasTaIndicatorCalculator,
)

from .conftest import load_parity_bars, needs_parity_fixtures

_ROW = 17


@needs_parity_fixtures
class TestCausalMetricOracle:
    """Black-box tests for prefix-oracle correctness semantics."""

    def test_streaming_vp_vah_matches_prefix_oracle_at_known_row(self):
        """Streaming session VP equals the prefix oracle on row 17."""
        from tests.support.causal_metric_oracle import (
            assert_metric_matches_prefix_oracle,
        )

        bars = load_parity_bars("30min")[:25]

        assert_metric_matches_prefix_oracle("vp_vah", bars, sample_indices=[_ROW])

    def test_full_frame_batch_row_is_not_the_oracle_for_session_vp(self):
        """Full-frame session VP row 17 diverges from the causal prefix value."""
        from tests.support.causal_metric_oracle import expected_prefix_value

        bars = load_parity_bars("30min")[:25]
        frame = PandasBarFrameConverter().bars_to_frame(bars)
        full_frame_value = PandasTaIndicatorCalculator().calculate(
            frame, ["vp_vah"]
        ).iloc[_ROW]["vp_vah"]

        prefix_value = expected_prefix_value("vp_vah", bars, _ROW)

        assert not math.isclose(
            full_frame_value,
            prefix_value,
            rel_tol=1e-9,
            abs_tol=1e-9,
        )

    def test_metric_value_assertion_preserves_bool_and_nan_semantics(self):
        """Comparator handles bools and NaN without coercing everything to float."""
        from tests.support.metric_value_assertions import (
            assert_equivalent_metric_value,
        )

        assert_equivalent_metric_value(True, True, "is_b_shape")
        assert_equivalent_metric_value(float("nan"), float("nan"), "hurst_exponent")

        with pytest.raises(AssertionError):
            assert_equivalent_metric_value(True, 1.0, "is_b_shape")
        with pytest.raises(AssertionError):
            assert_equivalent_metric_value(float("nan"), 1.0, "hurst_exponent")
