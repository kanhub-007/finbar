"""StrategyFeatureCalculator interface for v2 derived features."""

from abc import ABC, abstractmethod
from typing import Any

from finbar.core.domain.entities.feature_spec import FeatureSpec


class StrategyFeatureCalculator(ABC):
    """Calculate derived strategy feature columns on an already-enriched frame."""

    @abstractmethod
    def calculate(self, frame: Any, features: list[FeatureSpec]) -> Any:
        """Return a frame with requested derived feature columns added."""
