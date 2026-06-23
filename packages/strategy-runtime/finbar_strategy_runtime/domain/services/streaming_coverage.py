"""Streaming coverage service for causal enrichment safety checks."""

from __future__ import annotations

from finbar_strategy_runtime.domain.entities.streaming_coverage_report import (
    StreamingCoverageReport,
)
from finbar_strategy_runtime.domain.entities.unknown_metric_error import (
    UnknownMetricError,
)
from finbar_strategy_runtime.indicators._streaming_classifier import (
    UnsupportedStreamingIndicatorError,
    classify_indicator,
)
from finbar_strategy_runtime.parser.streaming_coverage_loader import (
    load_default_streaming_coverage_matrix,
)


def classify_streaming_coverage(metric_names: list[str]) -> StreamingCoverageReport:
    """Classify whether metrics are safe for causal streaming today.

    Args:
        metric_names: Concrete indicator/metric names required by a strategy.

    Returns:
        StreamingCoverageReport with correct and unsupported metric names.

    Raises:
        UnknownMetricError: If a metric is neither in the matrix nor accepted
            by the streaming classifier.
    """
    matrix = load_default_streaming_coverage_matrix()
    correct: list[str] = []
    unsupported: list[str] = []
    silent_wrong: list[str] = []
    loud_nan_mismatch: list[str] = []

    for raw_name in sorted({name.lower() for name in metric_names}):
        try:
            entry = matrix.entry_for(raw_name)
        except UnknownMetricError:
            _classify_dynamic_or_raise(raw_name)
            correct.append(raw_name)
            continue
        if entry.label == "STREAMING_CORRECT":
            correct.append(raw_name)
            continue
        unsupported.append(raw_name)
        if entry.reason == "silent_wrong_value":
            silent_wrong.append(raw_name)
        elif entry.reason == "nan_or_raise_mismatch":
            loud_nan_mismatch.append(raw_name)
    return StreamingCoverageReport(
        correct=correct,
        unsupported=unsupported,
        silent_wrong=silent_wrong,
        loud_nan_mismatch=loud_nan_mismatch,
    )


def _classify_dynamic_or_raise(metric_name: str) -> None:
    """Validate dynamic/period metrics not listed in the finite matrix."""
    try:
        classify_indicator(metric_name)
    except UnsupportedStreamingIndicatorError as exc:
        raise UnknownMetricError(
            f"Unknown metric '{metric_name}' in streaming coverage classifier"
        ) from exc


__all__ = ["UnknownMetricError", "classify_streaming_coverage"]
