"""MetricCapabilityResult — result of checking whether a metric can be computed."""

from dataclasses import dataclass, field

from finbar_strategy_runtime.domain.entities.metric_confidence import MetricConfidence
from finbar_strategy_runtime.domain.entities.metric_resolution_path import (
    MetricResolutionPath,
)


@dataclass
class MetricCapabilityResult:
    """Result of a metric capability check.

    Tells the caller whether a metric is supported, computable with the
    available data, what confidence level applies, and what paths are
    available or data is missing.
    """

    metric: str
    supported: bool
    computable: bool
    confidence: MetricConfidence = MetricConfidence.UNAVAILABLE
    selected_metric: str = ""
    available_paths: tuple[MetricResolutionPath, ...] = ()
    missing_data_classes: tuple[str, ...] = ()
    missing_providers: tuple[str, ...] = ()
    proxy_candidates: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
