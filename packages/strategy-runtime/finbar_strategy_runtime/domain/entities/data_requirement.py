"""DataRequirement — what data is needed to compute a metric."""

from dataclasses import dataclass, field

from finbar_strategy_runtime.domain.entities.data_class import DataClass


@dataclass(frozen=True)
class DataRequirement:
    """Describes the data that must be available to compute a metric."""

    data_class: DataClass
    required_columns: tuple[str, ...] = ()
    min_bars: int = 1
    provider_requirements: tuple[str, ...] = ()
    interval_min: str = ""  # e.g. "5min", "1h", "" for daily
