"""MarketMetricDefinition — describes one computable or unavailable metric."""

from dataclasses import dataclass

from finbar_strategy_runtime.domain.entities.data_class import DataClass
from finbar_strategy_runtime.domain.entities.data_requirement import DataRequirement
from finbar_strategy_runtime.domain.entities.metric_confidence import MetricConfidence
from finbar_strategy_runtime.domain.entities.metric_family import MetricFamily
from finbar_strategy_runtime.domain.entities.metric_resolution_path import (
    MetricResolutionPath,
)


@dataclass(frozen=True)
class MarketMetricDefinition:
    """Describes one market metric: its data requirements, confidence,
    family classification, and available computation paths."""

    name: str
    family: MetricFamily
    description: str = ""
    output_columns: tuple[str, ...] = ()
    required_inputs: tuple[str, ...] = ()
    min_lookback: int = 1
    confidence: MetricConfidence = MetricConfidence.PROXY
    paper_reference: str = ""
    proxy_candidates: tuple[str, ...] = ()
    required_data_classes: tuple[DataClass, ...] = ()
    required_columns: tuple[str, ...] = ()
    required_providers: tuple[str, ...] = ()
    implemented: bool = True
    resolution_paths: tuple[MetricResolutionPath, ...] = ()
    applicable_asset_classes: tuple[str, ...] = ("equity", "crypto")
    condition_note: str = ""
    """Human-readable constraint note for conditional metrics, e.g.
    'Returns null on short histories' or 'Intraday only'. Surfaced in
    ``list_market_metrics`` / ``check_metric`` so users don't request
    metrics that silently fail (spec 2026-06-16 Scenario 3)."""

    @property
    def primary_data_requirement(self) -> DataRequirement:
        """The primary data requirement for computing this metric."""
        return DataRequirement(
            data_class=self.required_data_classes[0]
            if self.required_data_classes
            else DataClass.DAILY_OHLCV,
            required_columns=self.required_columns,
            min_bars=self.min_lookback,
            provider_requirements=self.required_providers,
        )
