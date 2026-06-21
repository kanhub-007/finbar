"""Coverage-matrix sweep helpers for full-catalog causal parity tests."""

from __future__ import annotations

from finbar_strategy_runtime.domain.entities.streaming_coverage_matrix import (
    StreamingCoverageMatrix,
)
from tests.support.causal_streaming_sweep_report import CausalStreamingSweepReport


def run_causal_streaming_sweep(metric_names: list[str]) -> CausalStreamingSweepReport:
    """Return unsupported classifications for a catalog metric set.

    Args:
        metric_names: Concrete metric names to check against the package matrix.

    Returns:
        CausalStreamingSweepReport summarising any non-green classifications.
    """
    matrix = StreamingCoverageMatrix.load_default()
    unsupported: list[str] = []
    silent_wrong: list[str] = []
    loud_nan_mismatch: list[str] = []
    for name in sorted(metric_names):
        entry = matrix.entry_for(name)
        if entry.label != "STREAMING_UNSUPPORTED":
            continue
        unsupported.append(name)
        if entry.reason == "silent_wrong_value":
            silent_wrong.append(name)
        elif entry.reason == "nan_or_raise_mismatch":
            loud_nan_mismatch.append(name)
    return CausalStreamingSweepReport(
        unsupported=unsupported,
        silent_wrong=silent_wrong,
        loud_nan_mismatch=loud_nan_mismatch,
    )
